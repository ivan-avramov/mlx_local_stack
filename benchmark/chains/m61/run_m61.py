# FROZEN copy (P229, 2026-10-10) of $STACK_WORKDIR/m61/run_m61.py, the driver behind the opencode_v2_*.m61* / .rr.* (M61) rows.
# Only change: absolute home paths -> $STACK_WORKDIR / $STACK_REPO. See benchmark/chains/README.md.
"""M61 runner (spec docs/specs/m61-web-audit-and-prompt-ab.md). Reuses the M59 runner's router/load/A4/leg/watcher machinery
with OUT=$STACK_WORKDIR/m61.
  smoke : `--limit 5` of --scaffold opencode-v2-web on Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed, 5 seeded-random Python items, run twice.
  ab    : P198 — 2 picks x 2 sessions (fresh instance each) x arms A/B (A->B in s1, B->A in s2) x the 5 pre-registered items.
Usage: run_m61.py smoke | ab [s1 s2]      (detached; exit code in run_m61.rc)
"""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "m59"))
import run_m59 as R

R.OUT = R.WD / "m61"
PICK1, PICK2 = R.PICK1, R.PICK2
SYS118 = "benchmark/opencode_prompts/opencode-1.18.15-default.txt"
AB_ITEMS = {"go": ["forth"], "python": ["connect", "pov", "bowling", "hangman"]}   # P198 pre-registered 2026-10-08
AB_SEEDS = {"s1": 6101, "s2": 6202}
ARMS = {"A": ("--scaffold", "opencode-v2"), "B": ("--scaffold", "opencode-v2", "--agent-system-file", SYS118)}
ARM_ORDER = {"s1": ["A", "B"], "s2": ["B", "A"]}
MODEL_ORDER = {"s1": [PICK1, PICK2], "s2": [PICK2, PICK1]}
SMOKE_ITEMS = random.Random(20261008).sample(sorted(R.ITEMS["python"]), 5)


def a4_gate(model, tag, gate_args):
    """A4 v2 gate whose receipt carries the carrier this arm writes (scaffold / system file)."""
    import json, subprocess
    env = R.env_base()
    logf = R.OUT / f"a4_{tag}.log"
    R.log(f"RUN A4 v2 gate ({model}, {' '.join(gate_args)}) -> {logf.name}")
    with logf.open("w") as lf:
        rc = subprocess.run([str(R.PY), str(R.GATE), "--model", model, "--opencode", "v2", "--skip-owui",
                             "--log", str(R.REPO / "logs/mlx_vlm.log"), *gate_args], cwd=str(R.REPO), env=env,
                            stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=1800).returncode
    rec = json.loads(R.RECEIPT.read_text()) if R.RECEIPT.exists() else {}
    R.log(f"A4 v2 rc={rc} pass={rec.get('pass')} carrier_sha256={str(rec.get('carrier_sha256'))[:12]} run_id={rec.get('run_id')}")
    if rec.get("pass") is not True:
        raise SystemExit(f"A4 v2 gate FAILED (rc={rc}) -- stop")


def smoke():
    R.log(f"START m61 smoke opencode-v2-web items={SMOKE_ITEMS}")
    R.start_router()
    try:
        R.load(PICK1)
        a4_gate(PICK1, "m61_smoke", ("--scaffold", "opencode-v2-web"))
        for tag in ("p1", "p2"):
            R.run_leg(PICK1, "python", SMOKE_ITEMS, 7001, R.OUT / "smoke" / f"{PICK1}.web.python.{tag}.jsonl", limit=5,
                      extra_args=("--scaffold", "opencode-v2-web"))
        R.unload(PICK1)
    finally:
        R.stop_stack()
    R.log("M61 SMOKE DONE")


def ab(sessions):
    R.log(f"START m61 ab sessions={sessions} items={AB_ITEMS}")
    R.start_router()
    try:
        prev = None
        for s in sessions:
            (R.OUT / "ab").mkdir(parents=True, exist_ok=True)
            for model in MODEL_ORDER[s]:
                outs = {(arm, lang): R.OUT / "ab" / f"{model}.m61ab.{s}.{arm}.opencode_{lang}.jsonl"
                        for arm in ARM_ORDER[s] for lang in AB_ITEMS}
                if all(len(R.rows(o)) >= len(AB_ITEMS[l]) for (a, l), o in outs.items()):
                    R.log(f"SKIP {s} {model}: complete")
                    continue
                if prev is not None and not R.unload(prev):      # fresh instance per (model, session)
                    raise SystemExit(3)
                R.load(model)
                prev = model
                for arm in ARM_ORDER[s]:
                    a4_gate(model, f"m61_{s}_{model}_{arm}", ARMS[arm])      # receipt carrier == this arm's carrier
                    for lang in ("python", "go"):
                        R.run_leg(model, lang, AB_ITEMS[lang], AB_SEEDS[s], outs[(arm, lang)], chain_total=40,
                                  extra_args=ARMS[arm])
        if prev:
            R.unload(prev)
    finally:
        R.stop_stack()
    R.log("M61 AB DONE")


if __name__ == "__main__":
    (R.OUT / "smoke").mkdir(parents=True, exist_ok=True)
    mode = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    if mode == "smoke":
        smoke()
    elif mode == "ab":
        ab(sys.argv[2:] or ["s1", "s2"])
    else:
        raise SystemExit(f"unknown mode {mode}")
