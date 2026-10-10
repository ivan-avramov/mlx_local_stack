"""Chain 2 (operator go 2026-08-31 ~21:40): stop the campaign router -> M29 re-probe (fork branch on
PYTHONPATH; the probe runs its own router per arm) -> cleanup -> fixed prefill split (lazy) -> restart
the bench router on the draft-OFF overlay. Strictly sequential. SIGTERM this parent only."""
import json, os, signal, subprocess, sys, time
WD = os.environ["STACK_WORKDIR"]; REPO = os.environ["STACK_REPO"]; FORK = os.path.join(os.path.dirname(REPO), "mlx-vlm")
OUT = f"{WD}/quiet_window"; MODEL = "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit"
LOG = open(f"{OUT}/chain2.log", "a", buffering=1)
def log(m): LOG.write(f"[{time.strftime('%m-%d %H:%M:%S')}] {m}\n")
def listeners():
    out = subprocess.run(["lsof", "-nP", "-iTCP:8000", "-sTCP:LISTEN", "-t"], capture_output=True, text=True).stdout.split()
    return [int(x) for x in out]
def pids(pattern):
    out = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True).stdout.split()
    return [int(x) for x in out if int(x) != os.getpid()]
def stop_all():
    for pat in ("mlx-serve start", "mlx_vlm.server"):
        for p in pids(pat):
            log(f"kill {p} ({pat})"); 
            try: os.kill(p, signal.SIGTERM)
            except OSError: pass
    for _ in range(30):
        if not listeners() and not pids("mlx_vlm.server"): log("0 listeners on :8000, no worker (verified)"); return True
        time.sleep(2)
    for p in listeners() + pids("mlx_vlm.server"):
        log(f"SIGKILL {p}"); 
        try: os.kill(p, signal.SIGKILL)
        except OSError: pass
    time.sleep(3); ok = not listeners() and not pids("mlx_vlm.server"); log(f"after SIGKILL: clean={ok}"); return ok
def run(name, cmd, cwd, env, bound):
    log(f"RUN {name}: {' '.join(cmd)}")
    with open(f"{OUT}/{name}.log", "a") as lf:
        try: rc = subprocess.run(cmd, cwd=cwd, env=env, stdout=lf, stderr=subprocess.STDOUT, timeout=bound).returncode
        except subprocess.TimeoutExpired: log(f"TIMEOUT {name} after {bound}s"); return None
    log(f"END {name} rc={rc}"); return rc
base = dict(os.environ); base.pop("APC_ENABLED", None)
log("=== chain2 START ===")
if not stop_all(): log("FATAL: could not clear :8000"); sys.exit(3)
e5 = dict(base); e5["PYTHONPATH"] = f"{FORK}:{REPO}/benchmark"
run("mtp_reprobe_k1", [f"{REPO}/.venv-bench/bin/python", "-m", "m1.mtp_probe", "--model", MODEL, "--arm", "both",
     "--draft-model", f"{WD}/scratch/m6a/{MODEL}-mtp-drafter", "--workdir", f"{WD}/m29/probe_k1",
     "--json-out", f"{WD}/m29/probe_k1/mtp_probe_result.json"], f"{REPO}/benchmark", e5, 5400)
try:
    r = json.load(open(f"{WD}/m29/probe_k1/mtp_probe_result.json")); log(f"REPROBE gate: {json.dumps(r.get('gate'))} status={r.get('status')}")
    for arm in ("off", "on"):
        for row in r["arms"][arm]["rows"]:
            log(f"  {arm} {row['id']} tps={row['decode_tps']:.1f} ct={row['completion_tokens']} rounds={row.get('draft_rounds')} n={row.get('draft_n')} acc={row.get('draft_n_accepted')}")
except Exception as ex: log(f"REPROBE result read failed: {ex}")
if not stop_all(): log("FATAL: probe left :8000 busy"); sys.exit(3)
e3 = dict(base); e3["PYTHONPATH"] = f"{REPO}/src/mlx-vlm"
run("prefill_split_v2", [f"{REPO}/.venv/bin/python", f"{WD}/nax_probe/prefill_split.py", "caslca/Qwen3.6-27B-Opus-Distill-OptiQ-4bit", "32768"], REPO, e3, 1800)
# restart the bench router on the draft-OFF overlay
env_r = dict(base); env_r["MLX_VLM_CACHE_SESSION_MAX"] = "2"; env_r["MLX_SERVE_CONFIG"] = f"{WD}/m6b/bench_overlay_draft_off.yaml"
lf = open(f"{REPO}/logs/main_model.log", "a")
p = subprocess.Popen(["uv", "run", "mlx-serve", "start"], cwd=REPO, env=env_r, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
open(f"{WD}/m29/router_off.pid", "w").write(str(p.pid))
for _ in range(60):
    if listeners(): break
    time.sleep(2)
log(f"bench router restarted pid={p.pid} listeners={listeners()} overlay=draft-off SESSION_MAX=2 APC={'APC_ENABLED' in env_r}")
log("=== chain2 DONE ===")
