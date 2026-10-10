"""M31 finisher: if the Qwen3.6-27B-Opus-Distill-OptiQ-4bit ifeval@m31 rows are short of 148 (the chain's 20 h driver bound
killed the driver mid-run), resume the SAME generate command (same session, same code, same overlay), then re-grade and re-run
the M31 compares. No-op when the rows are complete."""
import os, sys, time, json
WD = os.environ["STACK_WORKDIR"]
src = open(f"{WD}/m21/arms_chain.py").read().split("# ---------------------------------------------------------------- main")[0]
exec(src)  # noqa: S102
OUT = f"{WD}/m31"; LOG = open(f"{OUT}/m31.log", "a", buffering=1)
BENCH = "ifeval"; TUNE = "m31"; N_FULL = 148
BASE = "Qwen3.8-27B-mlx-uniform-4bit"; Q36 = "Qwen3.6-27B-Opus-Distill-OptiQ-4bit"
env = dict(os.environ); env.pop("APC_ENABLED", None); env["MLX_SERVE_CONFIG"] = OVERLAY
rs = rows(Q36); log(f"=== M31 FINISH: {Q36} has {len(rs)} rows (expect {N_FULL}) ===")
if len(rs) < N_FULL:
    if not listeners(): start_router()
    rc = run_generate([Q36], N_FULL, f"resume_{Q36}", probe_timeout=7800, extra=["--samples", "1"])
    rs = rows(Q36); log(f"RESUME END rc={rc}: {len(rs)} rows, converged={sum(1 for r in rs if r.get('converged'))}, errors={[r['id'] for r in rs if r.get('error')]}")
    summarize(Q36, N_FULL)
    g = sh([PY, f"{REPO}/benchmark/run.py", "grade", "--models", Q36, "--benches", BENCH, "--tune", TUNE], cwd=REPO, env=env)
    open(f"{OUT}/grade_{Q36}.log", "a").write(g.stdout + g.stderr); log(f"END re-grade {Q36} rc={g.returncode}")
    s = json.load(open(f"{REPO}/benchmark/results/{Q36}/{BENCH}.{TUNE}.score.json"))
    log(f"SCORE {Q36} ifeval@m31 (after resume): prompt_strict={s.get('prompt_strict')} acc_strict={s.get('acc_strict')} prompt_loose={s.get('prompt_loose')} n={s.get('n')} errors={s.get('errors')}")
    for pair, tag in ((f"{BASE}@m31,{Q36}@m31", "m31_pair"),):
        for extra in ([], ["--intersect"]):
            c = sh([PY, f"{REPO}/benchmark/run.py", "compare", "--models", pair, "--benches", BENCH] + extra, cwd=REPO, env=env)
            open(f"{OUT}/compare_{tag}{'_intersect' if extra else ''}.log", "a").write("\n### after resume\n" + c.stdout + c.stderr)
            log(f"END compare (after resume) {tag}{' --intersect' if extra else ''} rc={c.returncode} :: {(c.stdout.strip().splitlines() or ['<no output>'])[-1][:200]}")
else: log("rows complete — nothing to do")
STOP.set(); log("=== M31 FINISH DONE ===")
