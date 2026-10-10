"""Runs when the queue runner exits: (1) KNOWN-POSITIVE MTP control — Qwen3.8-27B-mlx-uniform-4bit with its CERTIFIED drafter on the
bumped serving path (M6d: 1.60x, acceptance 0.674); (2) re-probe the re-packed Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed sidecar.
The 2026-09-07 01:49 probe of the mixed sidecar accepted 0 of ~48k draft tokens — a zero the instrument has not been validated for since
the 420c01e1 bump. Leaves the router DOWN (probe brings its own); restart on queue/bench_overlay_q.yaml before any new arm."""
import json, os, subprocess, time
WD = os.environ["STACK_WORKDIR"]; REPO = os.environ["STACK_REPO"]; PY = f"{REPO}/.venv-bench/bin/python"
LOG = open(f"{WD}/queue/after_queue.log", "a", buffering=1)
def log(m): LOG.write(f"[{time.strftime('%m-%d %H:%M:%S')}] {m}\n")
pid = int(open(f"{WD}/queue/queue.pid").read().strip()); log(f"waiting on queue runner pid {pid}")
while True:
    try: os.kill(pid, 0)
    except OSError: break
    time.sleep(120)
log("runner exited")
def stop_router():
    for p in subprocess.run(["lsof", "-nP", "-iTCP:8000", "-sTCP:LISTEN", "-t"], capture_output=True, text=True).stdout.split():
        subprocess.run(["kill", p]); log(f"killed router listener {p}")
    time.sleep(10)
    for _ in range(60):
        if not subprocess.run(["pgrep", "-f", "mlx_vlm.server"], capture_output=True, text=True).stdout.strip(): break
        time.sleep(2)
stop_router()
env = dict(os.environ); env.pop("APC_ENABLED", None); env["MLX_SERVE_CONFIG"] = f"{WD}/queue/bench_overlay_q.yaml"; env["PYTHONPATH"] = "."
for model, drafter, tag in (("Qwen3.8-27B-mlx-uniform-4bit", f"{WD}/scratch/m6a/Qwen3.8-27B-mlx-uniform-4bit-mtp-drafter", "control_u4_certified"),
                            ("Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", f"{WD}/scratch/m6a/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter", "mixed_sidecar_reprobe")):
    cmd = [PY, "-m", "m1.mtp_probe", "--model", model, "--workdir", WD, "--draft-model", drafter, "--json-out", f"{WD}/queue/mtp_{tag}.json"]
    log(f"RUN {tag}: {' '.join(cmd)}")
    p = subprocess.run(cmd, cwd=f"{REPO}/benchmark", env=env, stdout=open(f"{WD}/queue/mtp_{tag}.log", "a"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=3 * 3600)
    try:
        j = json.load(open(f"{WD}/queue/mtp_{tag}.json")); g = j.get("gate") or {}; on = (j.get("arms") or {}).get("on") or {}
        acc = [(r.get("draft_n_accepted") or 0, r.get("draft_n") or 0) for r in on.get("rows", [])]
        log(f"MTP {tag}: rc={p.returncode} ratio={g.get('ratio')} verdict={g.get('verdict')} accepted/proposed={acc}")
    except Exception as ex: log(f"WARN {tag}: {ex}")
log("=== AFTER-QUEUE DONE === (router DOWN; restart on queue/bench_overlay_q.yaml)")
