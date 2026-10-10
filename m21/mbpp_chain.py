"""M21b step 4 (operator GO 2026-09-03): mbppplus n=50 x k=3 on both arms — Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed
@t0.5 and Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit @t0.6-r2 (its existing mbpp row is pre-C28; full re-measure).
Same seeded 50-item draw (--seed 0, prefix-nested), seeds paired per (item, sample), bound 7800 s, predictor OFF,
router already up on the M21 overlay, src/mlx-vlm worktree pinned at 57177a21 (one fingerprint for all of M21b).
Order: 5-item seeded pilot on the mixed arm (first 5 of the seeded shuffle, k=3) -> size -> full n=50 both arms
-> grade -> compare (+ --intersect). Decision at the review: P28 rule on an independent item set. Logs to m21/mbpp.log."""
import os, sys, time
WD = os.environ["STACK_WORKDIR"]
src = open(f"{WD}/m21/arms_chain.py").read().split("# ---------------------------------------------------------------- main")[0]
exec(src)  # noqa: S102
BENCH = "mbppplus"
LOG = open(f"{OUT}/mbpp.log", "a", buffering=1)
threading.Thread(target=mem_sampler, daemon=True).start()
log("=== M21b MBPP START ===")
if not listeners(): start_router()
else:
    pid = listeners()[0]; e = sh(["ps","-Eww","-o","command=","-p",str(pid)]).stdout
    if ("MLX_SERVE_CONFIG=" + OVERLAY) not in e: stop_router(); start_router()
    else: log(f"router already up pid={pid} on the M21 overlay")
pin = sh(["git","-C",f"{REPO}/src/mlx-vlm","rev-parse","--short=8","HEAD"]).stdout.strip(); log(f"src/mlx-vlm worktree = {pin} (expect 57177a21)")
if pin != "57177a21": fatal("submodule worktree is not pinned at 57177a21 — rows would not pair with the hep k=3")
env = dict(os.environ); env["MLX_SERVE_CONFIG"] = OVERLAY
arms = [(OPT, "t0.5", ["--temp", "0.5", "--tune", "t0.5"]), (REF, "t0.6-r2", ["--tune", "t0.6-r2"])]
# ---- pilot: 5 seeded items x 3 draws on the mixed arm (prefix-nested into the 50 draw, so nothing is wasted)
TUNE = "t0.5"
if os.environ.get("MBPP_SKIP_PILOT"):
    log("PILOT SKIPPED by operator (MBPP_SKIP_PILOT set): the seeded first-5 draw holds two heavy cores (Mbpp/306, /620) and over-projects; sizing from the hep k=3 actuals (8.5 h / 300 draws) + this pilot's tail")
    rc = 0
else:
  rc = run_generate([OPT], N_PILOT, f"mbpp_pilot_{OPT}_t0.5", probe_timeout=7800, extra=arms[0][2] + ["--samples", "3"])
  s = summarize(OPT, 15)
  if s.get("n", 0) < 15 or s.get("errors"): fatal(f"pilot incomplete or errored: {s}")
  per_draw = s["wall_mean_s"]; proj_h = per_draw * 150 * 2 / 3600
  log(f"PILOT SIZING: mean {per_draw:.0f}s/draw, max {s['wall_max_s']:.0f}s -> LOWER BOUND {proj_h:.1f} h for both arms; "
      f"hep k=3 tail added ~2.5 h on top (Σ wall 8.5 h for 300 draws). ABORT threshold 24 h projected.")
  if proj_h > 24: fatal("projected run exceeds 24 h — resize with the operator")
# ---- full arms
for model, tune, extra in arms:
    TUNE = tune
    rc = run_generate([model], N_FULL, f"mbpp_{model}_{tune}", probe_timeout=7800, extra=extra + ["--samples", "3"])
    if rc != 0: log(f"WARN: mbpp driver rc={rc} for {model}@{tune}")
    rs = rows(model); log(f"MBPP ROWS {model}@{tune}: {len(rs)} rows, samples={sorted(set(r.get('sample') for r in rs))}, converged={sum(1 for r in rs if r.get('converged'))}, errors={[r['id'] for r in rs if r.get('error')]}")
    summarize(model, 150)
    g = sh([PY, f"{REPO}/benchmark/run.py", "grade", "--models", model, "--benches", BENCH, "--tune", tune], cwd=REPO, env=env)
    open(f"{OUT}/grade_mbpp_{tune}.log", "a").write(g.stdout + g.stderr); log(f"END grade {model}@{tune} rc={g.returncode}")
for extra in ([], ["--intersect"]):
    c = sh([PY, f"{REPO}/benchmark/run.py", "compare", "--models", f"{REF}@t0.6-r2,{OPT}@t0.5", "--benches", BENCH] + extra, cwd=REPO, env=env)
    open(f"{OUT}/compare_mbpp{'_intersect' if extra else ''}.log", "a").write(c.stdout + c.stderr); log(f"END compare mbpp{' --intersect' if extra else ''} rc={c.returncode}")
STOP.set(); log("=== M21b MBPP DONE === (review with the operator; P28 on the independent item set decides the recipe)")
