"""Self-evaluating benchmark monitor — writes a CRITICAL assessment every 5 minutes, unattended.

WHY THIS EXISTS. AGENTS.md requires every benchmark run to be reported AND critically evaluated every
5 minutes. The previous monitor wrote a row counter, which satisfies "reported" and not "evaluated" —
and the agent driving the run only executes when the operator sends a message, so relying on the agent
to do the evaluating produced hour-long gaps twice. The cadence has to live in a daemon, not in a
conversation.

So this answers AGENTS.md's four questions on its own, every tick, into a file the operator can
`tail -f`:

  1 PROGRESSING?  the item counter vs ITS OWN previous value — never worker busyness. ("worker=
                  GENERATING" was once reported as on-track for 13 minutes while the worker was
                  finishing an ABANDONED request.) A flat tick is named as such; N consecutive flat
                  ticks with a live driver is escalated to STALL SUSPECTED with the evidence needed
                  to tell it apart from a long-tail item.
  2 RATE?         items/tick and an ETA from the MEAN, because these distributions are heavily
                  right-tailed (IFEval: mean 38.6s vs median 22.5s, ~40% of wall in the top decile),
                  so a median-based ETA flatters. A rate change vs the run's own trailing average is
                  flagged with the most likely cause attached: the longest item since the last tick.
  3 OUTPUT SANE?  errors, convergence, nonconv kinds, and the degeneracy diagnostic — a verbatim loop
                  that self-terminates under budget is scored CONVERGED and is invisible in conv%.
  4 CORRECTION?   an explicit verdict line, so a tick that needs action cannot read like one that
                  does not.

Reads only persisted results, so it never perturbs the run.

  PYTHONPATH=benchmark nohup .venv-bench/bin/python benchmark/m1/bench_watch.py \
      --models Ornith-1.0-35B-mlx-uniform-4bit,Qwen3.6-27B-Opus-Distill-OptiQ-4bit \
      --bench ifeval --total 541 --driver-pattern ifeval_run \
      --out /tmp/ifeval_watch.log &

A run launched with `run.py --tune tX` writes `{bench}.{tune}.jsonl`, not `{bench}.jsonl` --
pass the matching `--tune` here or this watcher polls the wrong file and reports a healthy run
as QUEUED forever. Once a QUEUED reading survives 2+ ticks while a sibling `.jsonl` DOES exist
in that model's results dir, it escalates to an explicit `SUSPECT WRONG FILE` line naming both
the path being polled and the sibling file(s) found -- the instrument-validation rule: a monitor
that cannot tell "healthy" from "not looking" is worse than none.
"""
import argparse
import datetime
import json
import os
import re
import statistics as st
import subprocess
import time
from pathlib import Path

from bench import paths, traces
from bench.chain_ops import parse_power

FLAT_TICKS_TO_ESCALATE = 3


def _results_root() -> Path:
    """Same override generate.py honors, so a probe tree ($MLX_BENCH_RESULTS) is watchable."""
    env = os.environ.get("MLX_BENCH_RESULTS")
    return Path(env) if env else paths.default_results_root()


def _row_path(model: str, bench: str, tune: str = None) -> Path:
    """Same filename rule `run.py --tune` writes under: `{bench}.jsonl` normally, or
    `{bench}.{tune}.jsonl` for a tuned run. A watcher given only `--bench` for a tuned run polls
    the wrong file forever -- see `_sibling_jsonls` and the SUSPECT WRONG FILE diagnostic below."""
    fname = f"{bench}.{tune}.jsonl" if tune else f"{bench}.jsonl"
    return _results_root() / model / fname


def _rows(model: str, bench: str, tune: str = None, rows_file=None) -> list:
    p = Path(rows_file) if rows_file else _row_path(model, bench, tune)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and isinstance(row.get("record"), dict):  # P426 B5: a reasoning journal rung
            out.extend(row["record"].get("rows") or [])
        else:
            out.append(row)
    return out


def power_ok(reading) -> bool:
    """P426 B5 (plan §2 S8): exactly 140 W / 28 V and battery > 20 %; an unreadable reading is NOT ok."""
    return bool(
        reading
        and reading.get("watts") == 140
        and reading.get("volts") == 28
        and reading.get("batt") is not None
        and reading["batt"] > 20
    )


def read_power():
    try:
        ac = subprocess.run(["pmset", "-g", "ac"], capture_output=True, text=True, timeout=30).stdout
        batt = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_power(ac, batt)


class PowerState:
    """Sticky power verdict: the first failure is receipted once and named on every later tick."""

    def __init__(self, receipt=None):
        self.receipt = Path(receipt) if receipt else None
        self.first_failure = None

    def tick(self, reading, at) -> str:
        shown = (f"{reading.get('watts')}W {reading.get('volts')}V batt={reading.get('batt')}%"
                 if reading else "UNREADABLE")
        if not power_ok(reading) and self.first_failure is None:
            self.first_failure = at
            if self.receipt:
                self.receipt.write_text(json.dumps({"first_failure_at": at, "reading": reading}) + "\n")
            return (f"  0 POWER FAIL {shown} — ACT: this leg's speed block is INVALID "
                    "(140 W / 28 V / battery > 20 % required)")
        if self.first_failure is not None:
            return f"  0 POWER FAIL (sticky since {self.first_failure}) now {shown}"
        return f"  0 POWER ok {shown}"


def _sibling_jsonls(model: str, exclude: Path) -> list:
    """Other `.jsonl` files already sitting in this model's results dir, for the SUSPECT WRONG
    FILE diagnostic. Their presence is exactly the evidence that separates a genuinely-not-started
    model (no files at all) from a watcher polling the wrong filename (rows exist, just not where
    this watcher is looking)."""
    d = _results_root() / model
    if not d.exists():
        return []
    return sorted(p.name for p in d.glob("*.jsonl") if p != exclude)


def _alive(pattern: str) -> bool:
    return subprocess.run(["pgrep", "-f", pattern],
                          capture_output=True).returncode == 0


def _pid_alive(pid: int) -> bool:
    """P444: exact liveness for a driver that is this monitor's ANCESTOR (macOS `pgrep` excludes ancestors)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    stat = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return bool(stat) and not stat.startswith("Z")  # an exited, unreaped driver is a zombie: gone


def assess(model, bench, total, prev_n, flat_ticks, rate_hist, started=True, tune=None,
          ticks=0, rows_file=None, flat_escalate=FLAT_TICKS_TO_ESCALATE) -> tuple[str, int, int, list]:
    """Return (report, n, flat_ticks, rate_hist). Pure enough to test with fake rows."""
    rows = _rows(model, bench, tune, rows_file)
    path = Path(rows_file) if rows_file else _row_path(model, bench, tune)
    live = [r for r in rows if not r.get("error")]
    n = len(rows)
    lines = []

    # ---- 1 PROGRESSING
    # A model the driver has not reached yet sits at n=0 for hours. Escalating that to INVESTIGATE
    # every tick — as the first version did — is a false alarm that teaches the reader to ignore the
    # alert, defeating the point of the daemon. "started" is False until the model has ANY rows AND
    # no earlier tick saw rows for it (rows VANISHING would be a real problem, not a queue).
    if not started and n == 0:
        lines.append(f"  1 PROGRESS  n=0/{total}  QUEUED — driver has not reached this model yet")
        # SUSPECT WRONG FILE: a monitor that cannot tell "healthy" from "not looking" is worse
        # than none (AGENTS.md instrument-validation rule). QUEUED is indistinguishable from
        # "polling the wrong --bench/--tune" from n=0 alone -- give it a couple of ticks to rule
        # out early-queue noise, then check whether the driver IS writing, just elsewhere.
        if ticks >= 2:
            siblings = _sibling_jsonls(model, path)
            if siblings:
                lines.append(f"  ⚠ SUSPECT WRONG FILE: polling {path} for {ticks} ticks with "
                             f"nothing written, but sibling jsonl file(s) exist in that model dir: "
                             f"{', '.join(siblings)} — check --bench/--tune")
                lines.append("  4 CORRECTION ACT: verify --bench/--tune resolve to the file the "
                             "driver is actually writing")
                return "\n".join(lines), n, 0, rate_hist
        lines.append("  4 CORRECTION none (queued)")
        return "\n".join(lines), n, 0, rate_hist

    delta = None if prev_n is None else n - prev_n
    if delta is None:
        lines.append(f"  1 PROGRESS  n={n}/{total} (first tick, no delta yet)")
    elif delta > 0:
        flat_ticks = 0
        lines.append(f"  1 PROGRESS  n={n}/{total}  +{delta} since last tick")
    else:
        flat_ticks += 1
        lines.append(f"  1 PROGRESS  n={n}/{total}  FLAT for {flat_ticks} tick(s)")

    # ---- 2 RATE + ETA from the MEAN
    walls = [r["wall_s"] for r in live if r.get("wall_s")]
    if walls:
        mean_w, med_w = st.mean(walls), st.median(walls)
        rem = max(total - n, 0)
        lines.append(f"  2 RATE      mean {mean_w:.1f}s/item (median {med_w:.1f}s) "
                     f"-> ETA {rem * mean_w / 3600:.1f}h for {rem} left")
        if delta is not None:
            rate_hist = (rate_hist + [delta])[-6:]
            if len(rate_hist) >= 3:
                trail = st.mean(rate_hist[:-1])
                if trail > 0 and delta < 0.5 * trail:
                    # name the most likely cause rather than just the symptom
                    recent = sorted(live, key=lambda r: -(r.get("wall_s") or 0))[:1]
                    why = (f"longest item so far {recent[0].get('completion_tokens')} tok / "
                           f"{recent[0].get('wall_s'):.0f}s" if recent else "unknown")
                    lines.append(f"              ⚠ rate {delta}/tick vs trailing {trail:.1f} "
                                 f"— right-tail item likely ({why})")

    # ---- 3 OUTPUT SANE
    errs = len(rows) - len(live)
    nonconv = [r for r in live if r.get("converged") is False]
    degen = [r for r in live if traces.is_degenerate(r)]
    tw = sum(r.get("wall_s") or 0 for r in live) or 1
    kinds = {}
    for r in live:
        k = r.get("nonconv_kind")
        if k:
            kinds[k] = kinds.get(k, 0) + 1
    lines.append(f"  3 OUTPUT    errors={errs} nonconverged={len(nonconv)} kinds={kinds or '{}'} "
                 f"degen={len(degen)} (wall {100 * sum(r.get('wall_s') or 0 for r in degen) / tw:.0f}%)")

    # ---- 4 CORRECTION verdict
    verdict = "none"
    if errs and errs / max(len(rows), 1) > 0.2:
        verdict = f"ACT: {errs}/{len(rows)} rows are harness errors (>20%) — stop and fix"
    elif flat_ticks >= flat_escalate:
        verdict = (f"INVESTIGATE: flat for {flat_ticks} ticks. Distinguish a long-tail item from a "
                   f"stall — check the router log for a COMPLETED request since the last tick, and "
                   f"the worker's CPU%. Do NOT read 'worker busy' as 'run progressing'.")
    lines.append(f"  4 CORRECTION {verdict}")
    return "\n".join(lines), n, flat_ticks, rate_hist


def _parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Self-evaluating benchmark monitor.")
    ap.add_argument("--models", help="comma list, assessed in order (legacy mode)")
    ap.add_argument("--bench", help="legacy mode")
    ap.add_argument("--tune", default=None,
                    help="tune label a run was launched with (`run.py --tune tX`); composes "
                         "`{bench}.{tune}.jsonl` instead of `{bench}.jsonl`. Omitting this for a "
                         "tuned run silently polls the wrong file -- see SUSPECT WRONG FILE.")
    ap.add_argument("--total", type=int, help="items expected per model (legacy mode)")
    drv = ap.add_mutually_exclusive_group()
    drv.add_argument("--driver-pattern", help="pgrep pattern for the driver (never an ancestor of this monitor)")
    drv.add_argument("--driver-pid", type=int, help="P444: the driver's pid (exact; use when the driver is an ancestor)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--chain-json", default=None,
                    help="P426 mode (B2 spec 8): the leg's chain.json; --out is then the append-only watch.jsonl receipt")
    ap.add_argument("--planned", type=int, default=None,
                    help="P426 mode: planned slots of the leg (default: the slots the chain.json has registered so far)")
    ap.add_argument("--pred-s", type=float, default=None,
                    help="P426 mode: predicted seconds per item (default: the first-5 mean once known, else "
                         f"{GENERIC_PRED_S:.0f})")
    ap.add_argument("--interval", type=float, default=300.0)
    ap.add_argument("--rows-file", default=None,
                    help="P426 B5: watch this exact file (vision outputs, reasoning journals) instead of the tune path")
    ap.add_argument("--power-receipt", default=None,
                    help="P426 B5: where the first power failure is receipted (sticky; read by the leg wrapper)")
    ap.add_argument("--flat-escalate", type=int, default=FLAT_TICKS_TO_ESCALATE,
                    help="flat ticks before INVESTIGATE (reasoning rungs persist only when complete)")
    args = ap.parse_args(argv)
    if args.chain_json:
        if args.driver_pid is None:
            ap.error("--chain-json needs --driver-pid")
    else:
        missing = [f for f, v in (("--models", args.models), ("--bench", args.bench), ("--total", args.total)) if v is None]
        if args.driver_pid is None and not args.driver_pattern:
            missing.append("--driver-pattern/--driver-pid")
        if missing:
            ap.error(f"the following arguments are required: {', '.join(missing)}")
    return args


# ---------------------------------------------------------------------------------------------------------------------
# P426 mode (B2 spec 8, 16): a per-tick receipt journal `watch.jsonl`, finalized by one `exit_state` line.
# It only reads: the chain.json the driver persists, the rows files it names, `pmset`. It never signals the driver
# (C235 G2: in-run power is recorded and decides the speed block, never the leg).
# ---------------------------------------------------------------------------------------------------------------------
GENERIC_PRED_S = 250.0           # chain_core.GENERIC_PRED_S: the per-item prediction before a pilot mean exists
PILOT_N = 5
COUNTED_STATUSES = ("validated", "partial_incident", "hook_stopped", "running")   # rows files that hold this leg's rows
CORRECTION_RATIO = 1.5           # the chain's WATCH threshold: ETA over 1.5x the prediction asks "CORRECTION?"


def _pid_start(pid):
    """The process identity start time, `proc_guard.start_time()` (box-notes C151: never `ps -o lstart`, never psutil's
    `create_time()`); None when it cannot be read (no such process, or a failed read: the caller tells them apart)."""
    try:
        import psutil

        from bench import proc_guard
        return proc_guard.start_time(psutil.Process(int(pid)))
    except Exception:  # noqa: BLE001 — an unreadable start time is "unknown", never a crash of the watcher
        return None


_SRC = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d [+-]\d{4})\s.*\bUsing (AC|BATT|Batt)\b")


def parse_battery_log(text, *, now, since=None):
    """`pmset -g log` text -> [[start, end], ...] epoch seconds of the runs on battery: from a `Using BATT` line to the next
    `Using AC` line; a run still open at the end of the log runs to `now`. With `since` (the window start) the log must prove
    the power source at that moment: no recognized source line at or before `since` -> None (the intervals are unproven)."""
    points = []
    for line in (text or "").splitlines():
        m = _SRC.match(line)
        if m:
            when = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S %z").timestamp()
            points.append((when, m.group(2) != "AC"))
    points.sort(key=lambda p: p[0])
    if since is not None and not any(when <= since for when, _batt in points):
        return None
    runs, start = [], None
    for when, batt in points:
        if batt and start is None:
            start = when
        elif not batt and start is not None:
            runs.append([start, when])
            start = None
    if start is not None:
        runs.append([start, now])
    return runs


def pmset_power():
    """The default per-tick `power()`: `{watts, volts, battery}` from `pmset -g ac` / `-g batt` only; the battery log is read
    once, at exit (`pmset_battery_intervals`)."""
    reading = read_power() or {}
    return dict(watts=reading.get("watts"), volts=reading.get("volts"), battery=reading.get("batt"))


def pmset_battery_intervals(lo, hi):
    """The on-battery runs of the window `[lo, hi]` from ONE `pmset -g log` read; None (unproven) when the log cannot be read or
    holds no recognized source line at or before `lo`."""
    try:
        log = subprocess.run(["pmset", "-g", "log"], capture_output=True, text=True, timeout=120)
        if log.returncode == 0:
            return parse_battery_log(log.stdout, now=hi, since=lo)
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return None


def _quantile(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None


def _frozen_planned(root, doc):
    """The leg's plan: the slots of its frozen `schedule.json` (the file whose sha256 `chain.json` records), never a constant
    (spec 16.8); None when it is missing, unreadable, malformed or not the frozen one."""
    try:
        from bench import schedules
        sched = json.loads((Path(root) / "schedule.json").read_text())
        if doc.get("schedule_sha256") != schedules.schedule_sha256(sched):
            return None
        return sum(len(inv["names"]) for block in sched["blocks"] for leg in block["legs"] for inv in leg["invocations"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _chain_view(chain_json, planned=None, pred_s=None):
    """Everything a tick reports from the persisted leg state; a chain.json that is missing or mid-write yields `unreadable`.
    The plan is `planned` (the operator's override), else the frozen schedule's slots, else the slots registered so far."""
    root = Path(chain_json).parent
    try:
        doc = json.loads(Path(chain_json).read_text())
    except (OSError, ValueError):
        return dict(unreadable=True)
    planned = planned or _frozen_planned(root, doc)
    ledger = [e for e in doc.get("p426_ledger") or [] if isinstance(e, dict)]
    done_slots = {e.get("slot") for e in ledger}
    invs = [i for i in (doc.get("progress") or {}).get("invocations") or [] if i.get("status") != "archived"]
    registered = []
    for i in invs:
        registered += [s for s in i.get("expected_slots") or [] if s not in registered]
    registered += [s for s in done_slots if s not in registered]
    current = next((s.split("|")[-1] for i in reversed(invs) if i.get("status") == "running"
                    for s in i.get("expected_slots") or [] if s not in done_slots), None)
    rows = {}
    for i in invs:
        if i.get("status") in COUNTED_STATUSES and i.get("file"):
            for r in _rows(None, None, rows_file=root / i["file"]):
                rows[r.get("id")] = r
    rows = list(rows.values())
    walls = [r["wall_s"] for r in rows if r.get("wall_s")]
    done, total = len(ledger), (planned if planned else len(registered))
    remaining = max(total - done, 0)
    pred = pred_s if pred_s else (sum(walls[:PILOT_N]) / PILOT_N if len(walls) >= PILOT_N else GENERIC_PRED_S)
    mean = sum(walls) / len(walls) if walls else None
    m = mean if mean is not None else pred
    eta, pred_eta = remaining * m, remaining * pred
    ratio = (eta / pred_eta) if remaining else (m / pred)
    errors = sum(1 for r in rows if r.get("error"))
    toks = [((r.get("gate") or {}).get("output_tokens_completed") or 0) for r in rows]
    kinds = {}
    for r in rows:
        k = r.get("nonconv_kind")
        if k:
            kinds[k] = kinds.get(k, 0) + 1
    budget_hits = sum(1 for r in rows if "budget" in str(r.get("nonconv_kind")) or "budget" in str(r.get("nonconv_flags")))
    correction = ratio > CORRECTION_RATIO or (bool(rows) and errors / len(rows) > 0.2)
    note = (f"CORRECTION?: ETA {eta / 60:.0f}min is {ratio:.2f}x the prediction ({pred_eta / 60:.0f}min), errors={errors} — "
            "compare the cost of a corrected re-run against finishing the leg" if correction else
            f"finish: ETA {eta / 60:.0f}min vs prediction {pred_eta / 60:.0f}min (x{ratio:.2f}), errors={errors}")
    return dict(
        unreadable=False, status=doc.get("status"), progress=dict(done=done, planned=total),
        rows=sum(1 for e in ledger if e.get("kind") == "row"), dnf=sum(1 for e in ledger if e.get("kind") == "dnf"),
        current_item=current,
        eta=dict(mean_item_wall_s=mean, pred_item_s=pred, eta_s=eta, pred_eta_s=pred_eta, ratio=ratio, remaining=remaining),
        errors=errors, convergence=(sum(bool(r.get("converged")) for r in rows) / len(rows)) if rows else None,
        nonconv_kinds=kinds, tokens=dict(p50=_quantile(toks, .5), p90=_quantile(toks, .9), max=max(toks) if toks else None),
        budget_hits=budget_hits, correction=correction, note=note)


def _power_problems(tick):
    """The tick-level gate (plan section 2 S8): exactly 140 W / 28 V, battery above 20 %; an unreadable value is a failure."""
    out = []
    if tick.get("watts") != 140:
        out.append(f"watts={tick.get('watts')} (need 140)")
    if tick.get("volts") != 28:
        out.append(f"volts={tick.get('volts')} (need 28)")
    b = tick.get("battery")
    if not (isinstance(b, (int, float)) and b > 20):
        out.append(f"battery={b} (need > 20)")
    return out


def _stamp(line):
    """Epoch seconds of a journal line: its `t` (P52: the one clock; `at` is for humans); None when it is not a number."""
    t = line.get("t")
    if isinstance(t, (int, float)) and not isinstance(t, bool) and t == t and abs(t) != float("inf"):
        return float(t)
    return None


def _observed(tick):
    """P47: a tick with the driver bound and alive and the power meter read (watts, volts and battery all numbers)."""
    bound = (tick.get("driver") or {}).get("start", True) is not None
    return (tick.get("driver_alive") is True and bound and
            all(isinstance(tick.get(k), (int, float)) and not isinstance(tick.get(k), bool) for k in ("watts", "volts", "battery")))


def _verdict(lines, interval_s=None):
    """The speed-validity verdict over parsed journal lines (spec 8): every in-run tick 140 W / 28 V / battery > 20 %, no gap
    over 2 x interval (last tick to the exit line included), no on-battery interval in the window, the journal finalized."""
    ticks = [x for x in lines if "exit_state" not in x]
    ends = [x for x in lines if "exit_state" in x]
    problems = []
    if not ticks:
        return dict(valid=False, reason="journal has no tick")
    if not any(_observed(t) for t in ticks):
        problems.append("no tick with the driver bound and alive and power observed")
    if not (len(ends) == 1 and lines[-1] is ends[0]):
        problems.append("journal not finalized (no single closing exit_state line)")
    elif ends[0].get("exit_state") != "driver_exited":
        problems.append(f"exit_state={ends[0].get('exit_state')!r}, not driver_exited")
    for n, t in enumerate(ticks):
        if t.get("driver_alive") is False:
            continue                                    # a reading after the driver is gone is not in-run
        bad = _power_problems(t)
        if bad:
            problems.append(f"tick {n}: {', '.join(bad)}")
    interval = interval_s or next((x.get("interval_s") for x in ticks + ends if x.get("interval_s")), None)
    stamps = [_stamp(x) for x in ticks + (ends if ends and lines[-1] is ends[0] else [])]
    if None in stamps or interval is None:
        problems.append("tick times or interval missing: gaps unprovable")
    else:
        worst = max((b - a for a, b in zip(stamps, stamps[1:])), default=0.0)
        if worst > 2 * interval:
            problems.append(f"tick gap {worst:.0f}s > 2 x interval {interval:.0f}s")
    if ends and lines[-1] is ends[0]:
        bi = ends[0].get("battery_intervals")
        if not isinstance(bi, list):
            problems.append("battery log unreadable: no on-battery proof for the window")
        elif bi:
            problems.append(f"on-battery interval(s) in the leg window: {len(bi)}")
    return dict(valid=not problems, reason="ok" if not problems else "; ".join(problems[:4]))


def read_journal(path):
    """Parsed lines of a `watch.jsonl`, or None when it is missing, empty or has an unparseable line."""
    try:
        text = Path(path).read_text()
        lines = [json.loads(x) for x in text.splitlines() if x.strip()]
    except (OSError, ValueError):
        return None
    return lines if lines and all(isinstance(x, dict) for x in lines) else None


def speed_verdict(path, *, interval_s=None) -> dict:
    """`{valid, reason}` of a leg's speed block from its `watch.jsonl` alone; watcher death (no `exit_state`) or a missing,
    empty or unparseable journal is speed-invalid."""
    lines = read_journal(path)
    return dict(valid=False, reason=f"watch journal missing or unreadable: {path}") if lines is None else _verdict(lines, interval_s)


def pair_speed(legs) -> dict:
    """The pair rule (spec 8). `legs` = {session: {"off": leg, "on": leg}}, a leg a bool or a record with `speed_valid`; a missing leg is
    invalid. An invalid leg removes its session's speed comparison; with one valid session the ratio is descriptive and "not
    order-balanced"; with none there is no speed comparison."""
    def ok(leg):
        return bool(leg.get("speed_valid")) if isinstance(leg, dict) else leg is True
    valid = sorted(s for s, pair in legs.items() if ok((pair or {}).get("off")) and ok((pair or {}).get("on")))
    excluded = sorted(s for s in legs if s not in valid)
    if valid and not excluded and len(valid) >= 2:
        mode, note = "inference", None
    elif valid:
        mode, note = "descriptive", "not order-balanced"
    else:
        mode, note = "none", None
    return dict(mode=mode, valid_sessions=valid, excluded=excluded, note=note)


def _append(path, doc):
    with Path(path).open("a") as f:
        f.write(json.dumps(doc, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _iso(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat()


def _number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and abs(x) != float("inf")


def _overlap(intervals, lo, hi):
    """The on-battery `[start, end]` pairs (epoch seconds, P510) that overlap the window `[lo, hi]`, as `{start, end}`; None when
    `intervals` is missing or any element is not a pair of ordered finite numbers (the window is then unproven)."""
    if not isinstance(intervals, (list, tuple)):
        return None
    out = []
    for iv in intervals:
        if not (isinstance(iv, (list, tuple)) and len(iv) == 2 and _number(iv[0]) and _number(iv[1]) and iv[0] <= iv[1]):
            return None
        s, e = iv
        if e > lo and s < hi:
            out.append(dict(start=s, end=e))
    return out


def _driver_state(pid, bound):
    """`(state, bound)`: `gone` (no such process, a zombie, or the pid now has another start time), `alive`, or `unknown` (the
    start time cannot be read: a failed read is not an exit, P47). The first readable start time binds the driver."""
    if not _pid_alive(pid):
        return "gone", bound
    cur = _pid_start(pid)
    if cur is None:
        return "unknown", bound
    if bound is None:
        return "alive", cur
    return ("alive" if cur == bound else "gone"), bound


def run_p426(args, *, power, clock, sleep, intervals=None) -> int:
    """The tick loop. `power()` is the per-tick meter reading; the battery log is read once, at exit: by `intervals(lo, hi)` when
    given (the default pmset source), else from the last reading's `on_battery_intervals` (an injected power source)."""
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    bound = _pid_start(args.driver_pid)
    start, lines, n = clock(), [], 0
    last = {}
    while True:
        state, bound = _driver_state(args.driver_pid, bound)
        try:
            reading = power()
        except Exception:  # noqa: BLE001 — an unreadable meter is a failed reading, never a crash of the watcher
            reading = None
        reading = reading if isinstance(reading, dict) else {}
        now = clock()
        tick = dict(tick=n, t=now, at=_iso(now), interval_s=args.interval, watts=reading.get("watts"),
                    volts=reading.get("volts"), battery=reading.get("battery"),
                    power_ok=not _power_problems(dict(watts=reading.get("watts"), volts=reading.get("volts"),
                                                      battery=reading.get("battery"))),
                    driver_alive={"alive": True, "gone": False}.get(state), driver=dict(pid=args.driver_pid, start=bound),
                    **{k: v for k, v in _chain_view(args.chain_json, args.planned, args.pred_s).items()})
        _append(out, tick)
        lines.append(tick)
        last = reading
        n += 1
        if state == "gone":
            break
        sleep(args.interval)
    end = clock()
    try:
        raw = intervals(start, end) if intervals is not None else last.get("on_battery_intervals")
    except Exception:  # noqa: BLE001 — an unreadable battery log leaves the window unproven
        raw = None
    exit_line = dict(exit_state="driver_exited", t=end, at=_iso(end), interval_s=args.interval, ticks=n,
                     window=dict(start=start, end=end), battery_intervals=_overlap(raw, start, end))
    _append(out, exit_line)                       # P52: no verdict here; the sequencer calls `speed_verdict(journal)`
    return 0


def main(argv=None, *, power=None, clock=None, sleep=None) -> int:
    args = _parse_args(argv)
    if args.chain_json:
        return run_p426(args, power=power or pmset_power, clock=clock or time.time, sleep=sleep or time.sleep,
                        intervals=None if power else pmset_battery_intervals)

    models = [m for m in args.models.split(",") if m]
    state = {m: {"prev": None, "flat": 0, "rates": [], "started": False, "ticks": 0} for m in models}
    out = Path(args.out)
    power = PowerState(args.power_receipt)

    while True:
        alive = _pid_alive(args.driver_pid) if args.driver_pid else _alive(args.driver_pattern)
        at = time.strftime('%H:%M:%S')
        blocks = [f"===== {at}  driver={'ALIVE' if alive else 'GONE'} =====", power.tick(read_power(), at)]
        for m in models:
            s = state[m]
            ticks = s["ticks"] + 1
            rep, n, flat, rates = assess(m, args.bench, args.total, s["prev"], s["flat"],
                                         s["rates"], started=s["started"], tune=args.tune,
                                         ticks=ticks, rows_file=args.rows_file,
                                         flat_escalate=args.flat_escalate)
            state[m] = {"prev": n, "flat": flat, "rates": rates,
                        "started": s["started"] or n > 0, "ticks": ticks}
            blocks.append(f"{m}")
            blocks.append(rep)
        with out.open("a") as f:
            f.write("\n".join(blocks) + "\n")
        if not alive:
            with out.open("a") as f:
                f.write("===== DRIVER EXITED — monitor stopping =====\n")
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
