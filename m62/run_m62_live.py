"""M62 live runs (operator go 2026-10-10), spec docs/specs/m62-token-turn-gate.md §6, scaffold opencode-v2-web-tg1.
  v3 : smoke — Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed, 5 seeded-random Python + 2 Go items (go/counter excluded), seed 1001.
  v4 : P214 — the three M61 thinking stalls, each on a fresh loaded instance, M61 seed bases.
Reuses the M59 runner (router start/ownership checks, power gate, load/unload, 5-min watcher, rate check), OUT=$STACK_WORKDIR/m62.
Usage: run_m62_live.py v3 v4      (detached; exit code in live.rc)"""
import random, sys, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "m59"))
import run_m59 as R

R.OUT = R.WD / "m62"
PICK1, PICK2 = R.PICK1, R.PICK2          # Fable-Distill-OptiQ, mlx-uniform-4bit
TG1 = ("--scaffold", "opencode-v2-web-tg1")
V3 = {"python": random.Random(20261010).sample(sorted(R.ITEMS["python"]), 5),
      "go": random.Random(20261010).sample(sorted(i for i in R.ITEMS["go"] if i != "counter"), 2)}
V4 = [(PICK2, "go", "alphametics", 1001), (PICK2, "go", "alphametics", 2002), (PICK1, "python", "book-store", 2002)]


_rows_watcher = R.watcher


def tg1_watcher(out, total, pred_s, stop):
    """P8: the M59 rows watcher (counts, mean-based ETA vs prediction, nonconv kinds, power) plus, every 5 min, the
    probe's latest in-item gate heartbeat (m62_watch line in the leg log) and its age — a long single item writes no
    rows for hours. A heartbeat older than 15 min is flagged STALE for the operator (never killed: silent/BUSY)."""
    import json, threading, time
    threading.Thread(target=_rows_watcher, args=(out, total, pred_s, stop), daemon=True).start()
    logf = Path(out).with_suffix(".log")
    while not stop.wait(300):
        try:
            lines = [l for l in logf.read_text(errors="replace").splitlines() if '"m62_watch"' in l]
        except OSError:
            lines = []
        if not lines:
            R.log(f"WATCH-GATE {Path(out).name}: no heartbeat yet")
            continue
        age = time.time() - logf.stat().st_mtime
        try:
            hb = json.loads(lines[-1]); g = hb.get("m62_watch", {})
            R.log(f"WATCH-GATE {Path(out).name}: elapsed={hb.get('elapsed_s', 0)/60:.0f}min "
                  f"requests={g.get('requests_completed')} out_tokens={g.get('output_tokens_completed')} "
                  f"np_tokens={g.get('no_progress_tokens')} np_requests={g.get('no_progress_requests')} "
                  f"best/base={g.get('best_failing')}/{g.get('baseline_failing')} stop={g.get('stop_reason')} "
                  f"log_age={age/60:.0f}min{' STALE' if age > 900 else ''}")
        except ValueError:
            R.log(f"WATCH-GATE {Path(out).name}: unparsable heartbeat")


R.watcher = tg1_watcher


def leg(model, lang, items, seed, out):
    expect = ",".join(f"{lang}/{i}" for i in items)
    R.run_leg(model, lang, items, seed, out, limit=len(items), receipt=False,
              extra_args=TG1 + ("--expect-items", expect))


def summary(out):
    for r in R.rows(out):
        g = r.get("gate") or {}
        R.log(f"ROW {r['id']} passed={r.get('passed')} nonconv={r.get('nonconv_kind')} flags={r.get('nonconv_flags')} "
              f"requests={g.get('requests_completed')} out_tokens={g.get('output_tokens_completed')} "
              f"max_req_out={max([u[1] if isinstance(u, (list, tuple)) else u.get('output', 0) for u in r.get('request_usage') or [0]] or [0])} "
              f"best/base={g.get('best_failing')}/{g.get('baseline_failing')} wall={r.get('wall_s')}")


def main(phases):
    R.log(f"START m62 live phases={phases} v3={V3} v4={V4}")
    wd = subprocess.Popen([str(R.PY), str(R.WD / "m59/mem_watchdog.py"), "--limit-gb", "12", "--log",
                           str(R.OUT / "RUNLOG.md"), "--stop-file", str(R.OUT / "live.rc")],
                          stdout=open(R.OUT / "mem_watchdog_live.out", "a"), stderr=subprocess.STDOUT,
                          stdin=subprocess.DEVNULL, start_new_session=True)   # backstop above the probe's own 8 GiB H2
    R.start_router()
    try:
        prev = None
        if "v3" in phases:
            R.load(PICK1)
            prev = PICK1
            for lang in ("python", "go"):
                out = R.OUT / "v3" / f"{PICK1}.v3.{lang}.jsonl"
                out.parent.mkdir(parents=True, exist_ok=True)
                leg(PICK1, lang, V3[lang], 1001, out)
                summary(out)
        if "v4" in phases:
            for model, lang, item, seed in V4:
                if prev is not None and not R.unload(prev):
                    raise SystemExit(3)
                R.load(model)                  # fresh loaded instance per item
                prev = model
                out = R.OUT / "v4" / f"{model}.v4.{lang}.{item}.s{seed}.jsonl"
                out.parent.mkdir(parents=True, exist_ok=True)
                leg(model, lang, [item], seed, out)
                summary(out)
        if prev:
            R.unload(prev)
    finally:
        R.stop_stack()
        wd.terminate()
    R.log("M62 LIVE DONE")


if __name__ == "__main__":
    main(sys.argv[1:] or ["v3", "v4"])
