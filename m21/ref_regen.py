"""M21 follow-on: re-measure the Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit reference on the CURRENT fork
code (compare refuses across src/mlx-vlm shas: reference rows are from 0c1c8b17, the arms from 57177a21).
Same 50 items/seeds, same tune, same explicit 7800 s bound as the arms, label t0.6-r2. Then grade + compare
both arms against it. Reuses arms_chain.py's helpers (pre-main section) and appends to arms.log."""
import os, subprocess, time, sys
WD = os.environ["STACK_WORKDIR"]
src = open(f"{WD}/m21/arms_chain.py").read().split("# ---------------------------------------------------------------- main")[0]
exec(src)  # noqa: S102 — defines log/listeners/start_router/run_generate/summarize/REF/OPT/INT8/...
TUNE = "t0.6-r2"
log("=== m21 REF-REGEN START === (waits for ARMS DONE)")
t0 = time.time()
while True:
    txt = open(f"{OUT}/arms.log").read()
    apid = int(open(f"{OUT}/arms.pid").read().strip() or 0)
    alive = sh(["ps", "-p", str(apid)]).returncode == 0
    if "=== m21 ARMS DONE ===" in txt and not alive: break
    if not alive and "ARMS DONE" not in txt.split("REF-REGEN START")[-1] and "FATAL" in txt.split("RELAUNCH")[-1]:
        fatal("arms chain died with FATAL — not regenerating the reference on top of it")
    if time.time() - t0 > 14 * 3600: fatal("arms chain did not finish within 14h")
    time.sleep(60)
log("arms DONE observed; regenerating the reference under the current code")
if not listeners():
    log("router not up — starting it on the M21 overlay"); start_router()
else:
    pid = listeners()[0]; e = sh(["ps", "-Eww", "-o", "command=", "-p", str(pid)]).stdout
    log(f"router pid={pid} MLX_SERVE_CONFIG_ok={('MLX_SERVE_CONFIG='+OVERLAY) in e}")
    if ("MLX_SERVE_CONFIG=" + OVERLAY) not in e: fatal("router is not on the M21 overlay")
rc = run_generate([REF], N_FULL, "ref_r2", probe_timeout=7800)
if rc != 0: log(f"WARN: ref_r2 driver rc={rc} — grading whatever exists")
summarize(REF, N_FULL)
env = dict(os.environ); env["MLX_SERVE_CONFIG"] = OVERLAY
g = sh([PY, f"{REPO}/benchmark/run.py", "grade", "--models", REF, "--benches", BENCH, "--tune", TUNE], cwd=REPO, env=env)
open(f"{OUT}/grade_ref_r2.log", "a").write(g.stdout + g.stderr); log(f"END grade ref_r2 rc={g.returncode}")
for m in (OPT, INT8):
    for extra in ([], ["--intersect"]):
        c = sh([PY, f"{REPO}/benchmark/run.py", "compare", "--models", f"{REF}@t0.6-r2,{m}@t0.6", "--benches", BENCH] + extra, cwd=REPO, env=env)
        open(f"{OUT}/compare_r2_{m}{'_intersect' if extra else ''}.log", "a").write(c.stdout + c.stderr)
        log(f"END compare {REF}@t0.6-r2 vs {m}@t0.6{' --intersect' if extra else ''} rc={c.returncode}")
STOP.set(); log("=== m21 REF-REGEN DONE ===")
