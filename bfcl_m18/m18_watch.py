"""M18 BFCL freshness+progress daemon (2026-08-24).

PRIMARY ALARM IS FRESHNESS, NOT ROW COUNT. Last session a row-counting ticker watched a
75-minute worker wedge and explained it away with hour-stale log lines whose timestamps it
never checked. So tick 1 here is: how old is the newest `metrics ... 200` line in
logs/main_model.log, in seconds, computed from the line's own timestamp. Older than
--stale-secs while the driver is alive => WEDGE SUSPECTED with the kill/restart recipe.

Secondary: per-category result-file line counts (progress vs its own past), rate + ETA from
the MEAN of completion latencies seen in the router log, worker RSS, and driver liveness.
Reads only persisted files; never touches the run.
"""
import argparse, datetime as dt, os, re, subprocess, sys, time
from pathlib import Path

MET = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) .*mlx-serve\.metrics .*/v1/chat/completions 200 .*?\| (\d+)ms \|")


def tail_metrics(log: Path, nbytes=400_000):
    """Newest metrics-200 timestamp + recent latencies, parsed from the LINES' OWN clocks."""
    if not log.exists():
        return None, []
    with log.open("rb") as fh:
        fh.seek(max(0, log.stat().st_size - nbytes))
        chunk = fh.read().decode("utf-8", "replace")
    last, lats = None, []
    for line in chunk.splitlines():
        m = MET.match(line)
        if m:
            last = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            lats.append(int(m.group(2)) / 1000.0)
    return last, lats


def counts(root: Path):
    """Keyed by MODEL/category so one watcher spans the whole multi-model script. Keying by
    category alone silently collides across models and leaves the watcher reporting a finished
    model's frozen counts while the next model runs."""
    out = {}
    for f in sorted(root.rglob("BFCL_v4_*_result.json")):
        cat = f.stem.replace("BFCL_v4_", "").replace("_result", "")
        model = f.parent.parent.name
        try:
            out[f"{model[:14]}/{cat}"] = sum(1 for _ in f.open())
        except OSError:
            pass
    return out


def poisoned(root: Path):
    """Items whose 'response' is an inference/connection ERROR STRING. The bfcl driver does
    NOT fail loud on a dead router: it writes the error text into the result row, which then
    scores as ast_decoder:decoder_failed and is indistinguishable from a real model failure.
    That is exactly how 152/200 parallel_multiple items were poisoned by a router restart on
    2026-08-24. Counted per file every tick so it can never pass unnoticed again."""
    out, kinds = {}, {}
    for f in sorted(root.rglob("BFCL_v4_*_result.json")):
        n, seen = 0, set()
        try:
            for line in f.open():
                if "Error during inference" in line:
                    n += 1
                    # Name the ACTUAL failure. "Connection error." (dead port) and "Request
                    # timed out." (client gave up on a legitimate long generation) demand
                    # OPPOSITE responses; an alarm that guesses the cause misdirects the fix.
                    i = line.find("Error during inference: ")
                    seen.add(line[i + 24:i + 64].split('"')[0].strip() or "unknown")
        except OSError:
            continue
        if n:
            k = f"{f.parent.parent.name[:14]}/{f.stem.replace('BFCL_v4_','').replace('_result','')}"
            out[k], kinds[k] = n, sorted(seen)
    return out, kinds


def alive(pattern):
    r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
    return [p for p in r.stdout.split() if p]


def worker_busy(router_pid):
    """(%cpu, rss_gb) of the resident worker. THE WEDGE/RUNAWAY DISCRIMINATOR: a wedged worker
    is silent AND idle; a worker grinding out a runaway generation is silent AND pinned near
    100% with RSS still growing. Killing the second one throws away real work and the whole
    category's progress. Established 2026-08-24 on Ornith-1.0-35B-mlx-uniform-4bit item 281:
    96% CPU, RSS 19.4->20.3 GB, silent 13 min — a runaway toward the 81920 thinking budget
    (~19.5 min at ~70 tok/s), not a wedge."""
    kids = subprocess.run(["pgrep", "-P", str(router_pid)], capture_output=True, text=True).stdout.split()
    best_rss, cpu = 0, 0.0
    for k in kids:
        r = subprocess.run(["ps", "-o", "rss=,%cpu=", "-p", k], capture_output=True, text=True).stdout.split()
        if len(r) == 2 and r[0].isdigit() and int(r[0]) > best_rss:
            best_rss, cpu = int(r[0]), float(r[1])
    return cpu, (best_rss / 1024 / 1024 if best_rss else float("nan"))


def worker_rss_gb(router_pid):
    """Largest child of the router = the resident worker. Never guess the pid by offset."""
    kids = subprocess.run(["pgrep", "-P", str(router_pid)], capture_output=True, text=True).stdout.split()
    best = 0
    for k in kids:
        r = subprocess.run(["ps", "-o", "rss=", "-p", k], capture_output=True, text=True).stdout.strip()
        if r.isdigit():
            best = max(best, int(r))
    return best / 1024 / 1024 if best else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="logs/main_model.log")
    ap.add_argument("--results", required=True)
    ap.add_argument("--driver-pattern", default="run_bfcl_fc")
    ap.add_argument("--router-pid", type=int, required=True)
    ap.add_argument("--interval", type=int, default=300)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--stale-secs", type=int, default=720)
    # Contention makes a runaway's later attempts far slower than budget/tok-per-s alone
    # (measured: attempt #1 20.7 min, attempt #3 42.3 min). Past THIS, "busy" stops being a
    # sufficient excuse and the wedge diagnosis returns even with a hot worker.
    ap.add_argument("--escalate-secs", type=int, default=3000)
    a = ap.parse_args()

    prev, prev_t = None, None
    flat = 0
    while True:
        now = dt.datetime.now()
        drv = alive(a.driver_pattern)
        last, lats = tail_metrics(Path(a.log))
        age = (now - last).total_seconds() if last else None
        wcpu, wrss = worker_busy(a.router_pid)
        prev_rss = getattr(main, "_prev_rss", None)
        rss_trend = "" if prev_rss is None else (" (growing)" if wrss > prev_rss + 0.05
                                                 else " (steady)" if abs(wrss - prev_rss) <= 0.05 else " (shrank)")
        main._prev_rss = wrss
        cur = counts(Path(a.results))
        total = sum(cur.values())
        pois, pois_kinds = poisoned(Path(a.results))

        lines = [f"=== {now:%Y-%m-%d %H:%M:%S} ==="]
        lines.append(f"1 FRESH?     newest metrics-200 = {last:%H:%M:%S} ({age/60:.1f} min ago)"
                     if last else "1 FRESH?     NO metrics-200 line found in tail — SUSPECT WRONG LOG")
        lines.append(f"  driver     {'ALIVE pid ' + ','.join(drv) if drv else 'GONE'}"
                     f" | router pid {a.router_pid} {'up' if alive('mlx-serve start') else 'DOWN'}"
                     f" | worker {wcpu:.0f}% CPU, RSS {wrss:.1f} GB{rss_trend}")

        delta = (total - prev) if prev is not None else None
        secs = (now - prev_t).total_seconds() if prev_t else None
        lines.append(f"2 PROGRESS   rows={total} {cur}" + (f" | +{delta} in {secs/60:.1f} min" if delta is not None else " | first tick"))
        if lats:
            mean = sum(lats) / len(lats)
            lines.append(f"3 RATE       mean item {mean:.1f}s over last {len(lats)} logged calls"
                         f" (max {max(lats):.0f}s) -> {3600/mean:.0f} items/h")
        else:
            lines.append("3 RATE       no latencies in tail")

        # Seed on the first tick: poison already on disk is a KNOWN, already-reported wound,
        # not a live incident. Alarming on it at every watcher restart would train the reader
        # to ignore the line that matters.
        first = not hasattr(main, "_prev_pois")
        prev_pois = getattr(main, "_prev_pois", pois)
        new_pois = {} if first else {k: v for k, v in pois.items() if v > prev_pois.get(k, 0)}
        main._prev_pois = pois

        if pois:
            lines.append(f"  POISON     items with inference-error responses{' (pre-existing)' if first else ''}: {pois}"
                         f" kinds={pois_kinds}"
                         f"  <- no usable model output; re-grade cannot recover them")

        if new_pois:
            kinds = {k: pois_kinds.get(k) for k in new_pois}
            timeout_only = all("timed out" in " ".join(v or []).lower() for v in kinds.values())
            lines.append(
                f"4 VERDICT    *** POISONED ITEMS APPEARING NOW *** {new_pois} kinds={kinds} — the driver "
                f"wrote an error string into the result row, where it scores as a wrong ANSWER. " +
                ("CAUSE=TIMEOUT: a legitimate long generation outran the 600 s SDK client timeout; the "
                 "worker does NOT cancel, so it is still grinding the abandoned attempts and following "
                 "items queue behind them. Do NOT kill the router — this is O41.0, fix the timeout. "
                 "Affected items are re-runnable surgically via run_ids."
                 if timeout_only else
                 "CAUSE=CONNECTION: the port was dead while the driver kept posting. Fix the router, then "
                 "RE-RUN the affected items (re-grade cannot recover them)."))
        elif drv and age is not None and age > a.stale_secs:
            flat += 1
            # Busy threshold is 10%, not 50: dense-model decode is memory-bound and
            # legitimately reads ~35% CPU (measured on Qwen3.6-27B-Opus-Distill-OptiQ-4bit
            # 12:22, misclassified as IDLE by the old 50% cut calibrated on an MoE's
            # 90%+ profile). A truly wedged worker reads ~0-2%.
            busy = wcpu > 10 and age < a.escalate_secs
            kind = "RUNAWAY SUSPECTED (worker BUSY)" if busy else "WEDGE SUSPECTED (worker IDLE)"
            advice = ("worker is pinned at %.0f%% CPU — it is GENERATING, not stuck. Do NOT kill: that "
                      "discards the category's progress. Most likely a single item running away toward "
                      "the thinking budget (bound it: budget/tok-per-s). Escalate only if silence exceeds "
                      "that bound." % wcpu) if busy else (
                      "worker is IDLE and silent — this is the wedge signature. Kill worker+router BY PID, "
                      "verify 0 listeners on :8000, restart lean router detached with "
                      "MLX_VLM_CACHE_SESSION_MAX=2, then relaunch the category.")
            # Alarm ONCE per episode. A repeat alarm every 5 min for an hour-long incident
            # already diagnosed is noise, and noise is how a real alarm gets ignored. An
            # episode ends when a completion lands (freshness resets), so `last` is its key.
            episode = last.isoformat() if last else "none"
            repeat = getattr(main, "_episode", None) == episode
            main._episode = episode
            if repeat and busy:
                quiet = "runaway episode" if busy else "quiet episode"
                lines.append(f"  ongoing    known {quiet} continues, {age/60:.0f} min silent, "
                             f"worker {wcpu:.0f}% — within bound ({a.escalate_secs/60:.0f} min), no new alarm")
                lines.append("4 VERDICT    ok — known runaway episode in progress; no correction needed.")
            else:
                lines.append(f"4 VERDICT    *** {kind} *** driver alive, router silent {age/60:.0f} min "
                             f"(> {a.stale_secs/60:.0f}). Both look HEALTHY from /health. {advice}")
        elif not drv:
            lines.append("4 VERDICT    driver GONE — run finished or died; check run_m18_detached.log for '=== M18 DONE'.")
        elif delta == 0 and secs and secs > 60:
            flat += 1
            lines.append(f"4 VERDICT    flat tick #{flat} but router fresh ({age/60:.1f} min) — long-tail item, not a wedge. Watch.")
        else:
            flat = 0
            lines.append("4 VERDICT    ok — progressing and fresh; no correction needed.")

        print("\n".join(lines) + "\n", flush=True)
        prev, prev_t = total, now
        if not drv or a.once:
            return
        time.sleep(a.interval)


if __name__ == "__main__":
    os.chdir(os.environ.get("STACK_REPO", str(Path(__file__).resolve().parents[2] / "mlx_local_stack")))
    main()
