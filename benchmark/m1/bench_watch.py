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

  nohup .venv-bench/bin/python benchmark/m1/bench_watch.py \
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
import json
import os
import statistics as st
import subprocess
import time
from pathlib import Path

from bench import paths, traces

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


def _rows(model: str, bench: str, tune: str = None) -> list:
    p = _row_path(model, bench, tune)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


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


def assess(model, bench, total, prev_n, flat_ticks, rate_hist, started=True, tune=None,
          ticks=0) -> tuple[str, int, int, list]:
    """Return (report, n, flat_ticks, rate_hist). Pure enough to test with fake rows."""
    rows = _rows(model, bench, tune)
    path = _row_path(model, bench, tune)
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
    elif flat_ticks >= FLAT_TICKS_TO_ESCALATE:
        verdict = (f"INVESTIGATE: flat for {flat_ticks} ticks. Distinguish a long-tail item from a "
                   f"stall — check the router log for a COMPLETED request since the last tick, and "
                   f"the worker's CPU%. Do NOT read 'worker busy' as 'run progressing'.")
    lines.append(f"  4 CORRECTION {verdict}")
    return "\n".join(lines), n, flat_ticks, rate_hist


def _parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Self-evaluating benchmark monitor.")
    ap.add_argument("--models", required=True, help="comma list, assessed in order")
    ap.add_argument("--bench", required=True)
    ap.add_argument("--tune", default=None,
                    help="tune label a run was launched with (`run.py --tune tX`); composes "
                         "`{bench}.{tune}.jsonl` instead of `{bench}.jsonl`. Omitting this for a "
                         "tuned run silently polls the wrong file -- see SUSPECT WRONG FILE.")
    ap.add_argument("--total", type=int, required=True, help="items expected per model")
    ap.add_argument("--driver-pattern", required=True, help="pgrep pattern for the driver")
    ap.add_argument("--out", required=True)
    ap.add_argument("--interval", type=float, default=300.0)
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)

    models = [m for m in args.models.split(",") if m]
    state = {m: {"prev": None, "flat": 0, "rates": [], "started": False, "ticks": 0} for m in models}
    out = Path(args.out)

    while True:
        alive = _alive(args.driver_pattern)
        blocks = [f"===== {time.strftime('%H:%M:%S')}  driver={'ALIVE' if alive else 'GONE'} ====="]
        for m in models:
            s = state[m]
            ticks = s["ticks"] + 1
            rep, n, flat, rates = assess(m, args.bench, args.total, s["prev"], s["flat"],
                                         s["rates"], started=s["started"], tune=args.tune,
                                         ticks=ticks)
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
