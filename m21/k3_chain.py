"""M21b k=3 confirmation (operator GO 2026-09-02 P30): add samples 1,2 to the existing k=1 rows of
Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed @t0.5 and Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit @t0.6-r2
(same 50 items; seeds paired per (item, sample)), then grade both at k=3 and run the paired compare.
Sizing: the k=1 rows at the same config ARE the pilot (~1.1 h per sample per arm + meander tail).
Decision rule (P28, reviewed with the operator before any registry change): pick the mixed recipe iff
mean strict >= 4-bit's - 1 item AND (paired tokens-per-task ratio < 1 with CI excluding 1, OR fewer
meanders at equal accuracy). Logs to m21/k3.log."""
import os, sys, time
WD = os.environ["STACK_WORKDIR"]
src = open(f"{WD}/m21/arms_chain.py").read().split("# ---------------------------------------------------------------- main")[0]
exec(src)  # noqa: S102
LOG = open(f"{OUT}/k3.log", "a", buffering=1)
threading.Thread(target=mem_sampler, daemon=True).start()
log("=== M21b K3 START ===")
if not listeners(): start_router()
else:
    pid = listeners()[0]; e = sh(["ps","-Eww","-o","command=","-p",str(pid)]).stdout
    if ("MLX_SERVE_CONFIG=" + OVERLAY) not in e: stop_router(); start_router()
    else: log(f"router already up pid={pid} on the M21 overlay")
env = dict(os.environ); env["MLX_SERVE_CONFIG"] = OVERLAY
arms = [(OPT, "t0.5", ["--temp", "0.5", "--tune", "t0.5"]), (REF, "t0.6-r2", ["--tune", "t0.6-r2"])]
for model, tune, extra in arms:
    TUNE = tune
    rc = run_generate([model], N_FULL, f"k3_{model}_{tune}", probe_timeout=7800, extra=extra + ["--samples", "3"])
    if rc != 0: log(f"WARN: k3 driver rc={rc} for {model}@{tune}")
    rs = rows(model); log(f"K3 ROWS {model}@{tune}: {len(rs)} rows, samples={sorted(set(r.get('sample') for r in rs))}, converged={sum(1 for r in rs if r.get('converged'))}, errors={[r['id'] for r in rs if r.get('error')]}")
    g = sh([PY, f"{REPO}/benchmark/run.py", "grade", "--models", model, "--benches", BENCH, "--tune", tune], cwd=REPO, env=env)
    open(f"{OUT}/grade_k3_{tune}.log", "a").write(g.stdout + g.stderr); log(f"END grade {model}@{tune} rc={g.returncode}")
for extra in ([], ["--intersect"]):
    c = sh([PY, f"{REPO}/benchmark/run.py", "compare", "--models", f"{REF}@t0.6-r2,{OPT}@t0.5", "--benches", BENCH] + extra, cwd=REPO, env=env)
    open(f"{OUT}/compare_k3{'_intersect' if extra else ''}.log", "a").write(c.stdout + c.stderr); log(f"END compare k3{' --intersect' if extra else ''} rc={c.returncode}")
STOP.set(); log("=== M21b K3 DONE === (review with the operator before any registry change; restore src/mlx-vlm worktree to the stack's pointer afterwards)")
