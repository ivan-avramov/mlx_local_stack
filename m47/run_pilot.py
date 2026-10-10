"""M47 pilot: 3 temperature arms x seeded 5-item sample per AST category, FC chain, medium effort.
Serialized (one resident model); each arm's bfcl.json lands under $STACK_WORKDIR/m47/<arm>/.
Real subprocess timeouts (macOS has no `timeout`)."""
import os, subprocess, sys, time, json
ROOT = os.environ["STACK_WORKDIR"] + "/m47"
REPO = os.environ["STACK_REPO"]
MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
ARMS = [("t03", 0.3), ("t05", 0.5), ("t07", 0.7)]
SEED = 47
env = dict(os.environ, MLX_SERVE_CONFIG=f"{REPO}/main_models.yaml", PYTHONPATH=f"{REPO}/benchmark")
for name, t in ARMS:
    out = f"{ROOT}/{name}"
    cmd = [f"{REPO}/.venv-bench/bin/python", "-m", "bench.run_bfcl_fc", "--model", MODEL,
           "--limit", "5", "--sample-seed", str(SEED), "--temperature", str(t), "--out", out]
    t0 = time.time()
    print(f"[m47] arm {name} t={t} start {time.strftime('%H:%M:%S')}", flush=True)
    with open(f"{ROOT}/{name}.log", "w") as log:
        try:
            rc = subprocess.run(cmd, cwd=f"{REPO}/benchmark", env=env, stdout=log, stderr=subprocess.STDOUT,
                                timeout=3600).returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
    summ = {}
    try:
        summ = json.load(open(f"{out}/bfcl.json"))
    except Exception as e:
        summ = {"error": str(e)}
    print(f"[m47] arm {name} rc={rc} {time.time()-t0:.0f}s acc={summ.get('acc')} n={summ.get('n')} "
          f"per_category={ {k: v.get('accuracy') for k, v in (summ.get('per_category') or {}).items()} }", flush=True)
    if rc != 0:
        print(f"[m47] arm {name} FAILED rc={rc}; stopping the chain", flush=True); sys.exit(1)
print("[m47] pilot done", flush=True)
