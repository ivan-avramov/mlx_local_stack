"""M21b: deployed-profile temperature ladder for Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed (operator GO
2026-09-02): per temperature -> 5-item seeded pilot -> hep n=50 (same items/seeds as every other arm) ->
grade -> compare vs itself @t0.6 and vs Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit @t0.6-r2. Reuses the
arms_chain helpers; logs to m21/ladder.log. Usage: ladder_chain.py 0.5,0.7"""
import os, sys, subprocess, time
WD = os.environ["STACK_WORKDIR"]
src = open(f"{WD}/m21/arms_chain.py").read().split("# ---------------------------------------------------------------- main")[0]
exec(src)  # noqa: S102
LOG = open(f"{OUT}/ladder.log", "a", buffering=1)
temps = [t for t in sys.argv[1].split(",") if t]
threading.Thread(target=mem_sampler, daemon=True).start()
log(f"=== M21b LADDER START === temps={temps} model={OPT}")
stop_router(); start_router()
env = dict(os.environ); env["MLX_SERVE_CONFIG"] = OVERLAY
for t in temps:
    TUNE = f"t{t}"
    extra = ["--temp", t, "--tune", TUNE]
    rc = run_generate([OPT], N_PILOT, f"ladder_{TUNE}_pilot", probe_timeout=7800, extra=extra)
    if rc != 0: fatal(f"pilot rc={rc} at {TUNE}")
    s = summarize(OPT, N_PILOT)
    if s["n"] < N_PILOT or s["errors"]: fatal(f"pilot gate failed at {TUNE}: {s}")
    rc = run_generate([OPT], N_FULL, f"ladder_{TUNE}_full", probe_timeout=7800, extra=extra)
    if rc != 0: log(f"WARN: full rc={rc} at {TUNE}")
    summarize(OPT, N_FULL)
    g = sh([PY, f"{REPO}/benchmark/run.py", "grade", "--models", OPT, "--benches", BENCH, "--tune", TUNE], cwd=REPO, env=env)
    open(f"{OUT}/grade_ladder_{TUNE}.log", "a").write(g.stdout + g.stderr); log(f"END grade {TUNE} rc={g.returncode}")
    for pair in (f"{OPT}@t0.6,{OPT}@{TUNE}", f"{REF}@t0.6-r2,{OPT}@{TUNE}"):
        c = sh([PY, f"{REPO}/benchmark/run.py", "compare", "--models", pair, "--benches", BENCH], cwd=REPO, env=env)
        open(f"{OUT}/compare_ladder_{TUNE}.log", "a").write(f"### {pair}\n" + c.stdout + c.stderr); log(f"END compare {pair} rc={c.returncode}")
STOP.set(); log("=== M21b LADDER DONE ===")
