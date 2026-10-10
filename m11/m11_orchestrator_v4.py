"""M11 reasoning ladder v4 (2026-08-30 23:xx, P7 swap): adopt the orphaned model-1 ladder child
(v3 parent SIGTERMed because its 12 h bound would have killed the child inside the 156K rung),
then run models 2-4 with the same flags under a 20 h bound. Fail-loud throughout."""
import os, subprocess, sys, time, urllib.request
WD = "$STACK_WORKDIR"
REPO = "$STACK_REPO"
ADOPT_PID = 32064                      # bench.run_reasoning --model Qwen3.8-27B-mlx-uniform-4bit (v3 child)
ADOPT_MODEL = "Qwen3.8-27B-mlx-uniform-4bit"
MODELS = ["Qwen3.6-27B-Opus-Distill-OptiQ-4bit",
          "Ornith-1.0-35B-mlx-uniform-4bit", "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit"]
GRID = "8000,16000,24000,32000,48000,64000,96000,128000,156000"
PER_MODEL_BOUND_S = 72000  # 20h: 6 shallow rungs (~1.5h) + 3 deep rungs x up to 3 budget samples (~2h10m each)
ADOPT_BOUND_S = 43200      # 12h from now for the adopted child (128K began 23:01; worst case ~10:30)
env = dict(os.environ)
env["MLX_SERVE_CONFIG"] = f"{WD}/m6b/bench_overlay_draft_off.yaml"
env.pop("APC_ENABLED", None)
LOG = open(f"{WD}/m11/m11_orchestrator.log", "a", buffering=1)
def log(m): LOG.write(f"[{time.strftime('%m-%d %H:%M:%S')}] v4 {m}\n")

def alive(pid):
    try: os.kill(pid, 0); return True
    except OSError: return False

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

# --- adopt model 1 ---
cmd = subprocess.run(["ps", "-o", "command=", "-p", str(ADOPT_PID)], capture_output=True, text=True).stdout
if "bench.run_reasoning" not in cmd or ADOPT_MODEL not in cmd:
    log(f"FATAL: pid {ADOPT_PID} is not the {ADOPT_MODEL} ladder: {cmd!r}"); sys.exit(5)
log(f"ADOPT {ADOPT_MODEL} pid={ADOPT_PID} bound={ADOPT_BOUND_S}s")
t0 = time.time()
while alive(ADOPT_PID):
    if time.time() - t0 > ADOPT_BOUND_S:
        log(f"FATAL: adopted {ADOPT_MODEL} exceeded {ADOPT_BOUND_S}s"); sys.exit(4)
    time.sleep(30)
mlog = open(f"{WD}/m11/m11_{ADOPT_MODEL}.log").read()
done = "REASONING_EFFECTIVE_CTX=" in mlog and os.path.exists(f"{REPO}/benchmark/results/{ADOPT_MODEL}/reasoning.json")
log(f"END {ADOPT_MODEL} (adopted) ok={done}")
if not done:
    log("FATAL: adopted child exited without REASONING_EFFECTIVE_CTX/reasoning.json — aborting block"); sys.exit(6)

# --- models 2-4 ---
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
