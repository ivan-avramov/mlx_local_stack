"""M11 reasoning ladder: 4 models sequentially, fresh worker session per model, fail-loud."""
import os, subprocess, sys, time, urllib.request
WD = "$STACK_WORKDIR"
REPO = "$STACK_REPO"
MODELS = ["Qwen3.8-27B-mlx-uniform-4bit", "Qwen3.6-27B-Opus-Distill-OptiQ-4bit",
          "Ornith-1.0-35B-mlx-uniform-4bit", "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit"]
GRID = "8000,16000,24000,32000,48000,64000,96000,128000,156000"  # cap-aware: 156000 < 159744 max prompt, budget 81920 unclamped
PER_MODEL_BOUND_S = 43200  # 12h (v2): deep-rung samples can think to budget (~2h each at ~12 tok/s); rungs persist + --resume, so a bound never loses work
env = dict(os.environ)
env["MLX_SERVE_CONFIG"] = f"{WD}/m6b/bench_overlay_draft_off.yaml"
env.pop("APC_ENABLED", None)
LOG = open(f"{WD}/m11/m11_orchestrator.log", "a", buffering=1)
def log(m): LOG.write(f"[{time.strftime('%m-%d %H:%M:%S')}] {m}\n")

def unload():
    if subprocess.run(["pgrep", "-f", "mlx_vlm.server"], capture_output=True).returncode != 0:
        log("no worker resident"); return True
    req = urllib.request.Request("http://localhost:8000/v1/models/unload", method="POST", data=b"")
    try:
        urllib.request.urlopen(req, timeout=120).read(); log("unload POST ok")
    except Exception as e:
        log(f"unload POST: {e}")
    for _ in range(24):
        if subprocess.run(["pgrep", "-f", "mlx_vlm.server"], capture_output=True).returncode != 0:
            log("worker gone (pgrep verified)"); return True
        time.sleep(5)
    log("FATAL: worker still alive after unload"); return False

for model in MODELS:
    if not unload(): sys.exit(3)
    log(f"START {model} grid={GRID}")
    with open(f"{WD}/m11/m11_{model}.log", "a") as lf:
        try:
            rc = subprocess.run(
                [f"{REPO}/.venv-bench/bin/python", "-m", "bench.run_reasoning", "--model", model,
                 "--grid", GRID, "--sampling-profile", "deployed", "--request-timeout", "9600", "--resume",
                 "--deep-from", "96000", "--deep-samples", "3", "--early-stop-budget-hits", "2"],
                cwd=f"{REPO}/benchmark", env=env, stdout=lf, stderr=subprocess.STDOUT,
                timeout=PER_MODEL_BOUND_S).returncode
        except subprocess.TimeoutExpired:
            log(f"FATAL: {model} exceeded {PER_MODEL_BOUND_S}s bound"); sys.exit(4)
    log(f"END {model} rc={rc}")
    if rc != 0:
        log("FATAL: nonzero rc — aborting block"); sys.exit(rc)
log("M11 ALL 4 MODELS DONE")
