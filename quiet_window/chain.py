"""Quiet-window chain (2026-08-31 night): waits for the Nemotron ladder orchestrator to exit, then runs
the GPU-needing probes in order. Each step logs to its own file; independent steps continue on failure.
  1. unload (one resident model)            2. na_discriminator.py on mlx 0.32.0 release
  3. prefill_split.py (B 1st choice, 32K)   4. fork-branch GPU equivalence test (MLX_VLM_GPU_TESTS=1)
  5. M6a re-probe: NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit MTP with the one-pass verify (fork branch on
     PYTHONPATH), k=1 (sidecar block 2), pre-registered 1.3x gate.
SIGTERM this parent only."""
import json, os, subprocess, sys, time, urllib.request
WD = os.environ["STACK_WORKDIR"]; REPO = os.environ["STACK_REPO"]; FORK = os.path.join(os.path.dirname(REPO), "mlx-vlm")
OUT = f"{WD}/quiet_window"; MODEL = "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit"
LOG = open(f"{OUT}/chain.log", "a", buffering=1)
def log(m): LOG.write(f"[{time.strftime('%m-%d %H:%M:%S')}] {m}\n")
def alive(pid):
    try: os.kill(pid, 0); return True
    except OSError: return False
def run(name, cmd, cwd, env, bound):
    log(f"RUN {name}: {' '.join(cmd)}")
    with open(f"{OUT}/{name}.log", "a") as lf:
        try: rc = subprocess.run(cmd, cwd=cwd, env=env, stdout=lf, stderr=subprocess.STDOUT, timeout=bound).returncode
        except subprocess.TimeoutExpired: log(f"TIMEOUT {name} after {bound}s"); return None
    log(f"END {name} rc={rc}"); return rc
def unload():
    if subprocess.run(["pgrep", "-f", "mlx_vlm.server"], capture_output=True).returncode != 0: log("no worker resident"); return True
    try: urllib.request.urlopen(urllib.request.Request("http://localhost:8000/v1/models/unload", method="POST", data=b""), timeout=120).read()
    except Exception as e: log(f"unload POST: {e}")
    for _ in range(24):
        if subprocess.run(["pgrep", "-f", "mlx_vlm.server"], capture_output=True).returncode != 0: log("worker gone (pgrep verified)"); return True
        time.sleep(5)
    log("FATAL: worker still alive after unload"); return False

lad = int(open(f"{WD}/nemo_ladder/orchestrator.pid").read())
log(f"=== chain armed; waiting for ladder orchestrator pid {lad} ===")
while alive(lad): time.sleep(60)
tail = open(f"{WD}/nemo_ladder/orchestrator.log").read().strip().splitlines()[-1]
log(f"ladder orchestrator exited; last line: {tail}")
if not unload(): sys.exit(3)
base = dict(os.environ); base.pop("APC_ENABLED", None); base["MLX_SERVE_CONFIG"] = f"{WD}/m6b/bench_overlay_draft_off.yaml"
# 2. NA discriminator
run("na_discriminator", [f"{REPO}/.venv/bin/python", f"{REPO}/benchmark/spikes/na_discriminator.py"], REPO, base, 600)
# 3. prefill split (B 1st choice, 32K) — fork main via the submodule copy (what the campaign serves)
e3 = dict(base); e3["PYTHONPATH"] = f"{REPO}/src/mlx-vlm"
run("prefill_split", [f"{REPO}/.venv/bin/python", f"{WD}/nax_probe/prefill_split.py", "caslca/Qwen3.6-27B-Opus-Distill-OptiQ-4bit", "32768"], REPO, e3, 3600)
# 4. GPU equivalence on the fork branch
e4 = dict(base); e4["MLX_VLM_GPU_TESTS"] = "1"
rc4 = run("gpu_equivalence", [f"{FORK}/.venv/bin/python", "-m", "pytest", "mlx_vlm/tests/test_ssm_with_states.py", "-q"], FORK, e4, 900)
if rc4 != 0: log("GPU equivalence FAILED — skipping the re-probe (pre-registered: correctness before speed)"); log("=== chain DONE (probe skipped) ==="); sys.exit(0)
# 5. M6a re-probe with the one-pass verify
e5 = dict(base); e5["PYTHONPATH"] = f"{FORK}:{REPO}/benchmark"
run("mtp_reprobe_k1", [f"{REPO}/.venv-bench/bin/python", "-m", "m1.mtp_probe", "--model", MODEL, "--arm", "both",
     "--draft-model", f"{WD}/scratch/m6a/{MODEL}-mtp-drafter", "--workdir", f"{WD}/m29/probe_k1",
     "--json-out", f"{WD}/m29/probe_k1/mtp_probe_result.json"], f"{REPO}/benchmark", e5, 5400)
try:
    r = json.load(open(f"{WD}/m29/probe_k1/mtp_probe_result.json")); log(f"REPROBE gate: {json.dumps(r.get('gate'))} sha={r.get('mlx_vlm_sha')}")
except Exception as ex: log(f"REPROBE result read failed: {ex}")
log("=== chain DONE ===")
