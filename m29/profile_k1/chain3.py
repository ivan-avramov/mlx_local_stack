"""Chain 3 (M29 H1 profile run, 2026-08-31 late night): stop the campaign router by pid -> m1.mtp_probe
--arm on with the fork profiler branch on PYTHONPATH and MLX_VLM_MTP_PROFILE(+_HEAD)=1 (the probe runs its
own router; server path only) -> copy the worker stderr log (mlx-serve writes it to
$TMPDIR/mlx-manager-logs/<model>.log, mode "w" per load) into the workdir -> cleanup -> restart the bench
router on the draft-OFF overlay. Strictly sequential. Samples swap/free memory every 15 s to mem.log."""
import json, os, signal, subprocess, sys, tempfile, threading, time
WD = os.environ["STACK_WORKDIR"]; REPO = os.environ["STACK_REPO"]; FORK = os.path.join(os.path.dirname(REPO), "mlx-vlm")
OUT = f"{WD}/m29/profile_k1"; MODEL = "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit"
LOG = open(f"{OUT}/chain3.log", "a", buffering=1)
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
            log(f"kill {p} ({pat})")
            try: os.kill(p, signal.SIGTERM)
            except OSError: pass
    for _ in range(30):
        if not listeners() and not pids("mlx_vlm.server"): log("0 listeners on :8000, no worker (verified)"); return True
        time.sleep(2)
    for p in listeners() + pids("mlx_vlm.server"):
        log(f"SIGKILL {p}")
        try: os.kill(p, signal.SIGKILL)
        except OSError: pass
    time.sleep(3); ok = not listeners() and not pids("mlx_vlm.server"); log(f"after SIGKILL: clean={ok}"); return ok
def run(name, cmd, cwd, env, bound):
    log(f"RUN {name}: {' '.join(cmd)}")
    with open(f"{OUT}/{name}.log", "a") as lf:
        try: rc = subprocess.run(cmd, cwd=cwd, env=env, stdout=lf, stderr=subprocess.STDOUT, timeout=bound).returncode
        except subprocess.TimeoutExpired: log(f"TIMEOUT {name} after {bound}s"); return None
    log(f"END {name} rc={rc}"); return rc
STOP = threading.Event()
def mem_sampler():
    with open(f"{OUT}/mem.log", "a", buffering=1) as mf:
        while not STOP.is_set():
            sw = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True).stdout.strip()
            vs = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout.splitlines()
            free = next((l.split()[-1].rstrip(".") for l in vs if l.startswith("Pages free")), "?")
            mf.write(f"[{time.strftime('%H:%M:%S')}] free_pages={free} swap: {sw}\n"); STOP.wait(15)
base = dict(os.environ); base.pop("APC_ENABLED", None)
log("=== chain3 START ===")
branch = subprocess.run(["git", "-C", FORK, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True).stdout.strip()
sha = subprocess.run(["git", "-C", FORK, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
log(f"fork on PYTHONPATH: {FORK} branch={branch} sha={sha}")
if branch != "nemotron-h-mtp-profile": log("FATAL: fork is not on nemotron-h-mtp-profile"); sys.exit(4)
threading.Thread(target=mem_sampler, daemon=True).start()
if not stop_all(): log("FATAL: could not clear :8000"); sys.exit(3)
e5 = dict(base); e5["PYTHONPATH"] = f"{FORK}:{REPO}/benchmark"; e5["MLX_VLM_MTP_PROFILE"] = "1"; e5["MLX_VLM_MTP_PROFILE_HEAD"] = "1"
worker_log = os.path.join(tempfile.gettempdir(), "mlx-manager-logs", f"{MODEL}.log")
log(f"worker stderr log expected at {worker_log}")
rc = run("mtp_profile_on", [f"{REPO}/.venv-bench/bin/python", "-m", "m1.mtp_probe", "--model", MODEL, "--arm", "on",
     "--draft-model", f"{WD}/scratch/m6a/{MODEL}-mtp-drafter", "--workdir", OUT,
     "--json-out", f"{OUT}/mtp_probe_result.json"], f"{REPO}/benchmark", e5, 3600)
try:
    subprocess.run(["/bin/cp", "-f", worker_log, f"{OUT}/worker_on.log"], check=True)
    n = sum(1 for l in open(f"{OUT}/worker_on.log") if "[mtp_profile" in l)
    log(f"worker log copied -> {OUT}/worker_on.log ({n} [mtp_profile*] lines)")
except Exception as ex: log(f"worker log copy failed: {ex}")
try:
    r = json.load(open(f"{OUT}/mtp_probe_result.json")); log(f"probe status={r.get('status')} gate={json.dumps(r.get('gate'))}")
    for row in r["arms"]["on"]["rows"]:
        log(f"  on {row['id']} tps={row['decode_tps']:.1f} ct={row['completion_tokens']} rounds={row.get('draft_rounds')} n={row.get('draft_n')} acc={row.get('draft_n_accepted')}")
except Exception as ex: log(f"probe result read failed: {ex}")
if not stop_all(): log("FATAL: probe left :8000 busy"); sys.exit(3)
STOP.set()
env_r = dict(base); env_r["MLX_VLM_CACHE_SESSION_MAX"] = "2"; env_r["MLX_SERVE_CONFIG"] = f"{WD}/m6b/bench_overlay_draft_off.yaml"
for k in ("MLX_VLM_MTP_PROFILE", "MLX_VLM_MTP_PROFILE_HEAD", "PYTHONPATH"): env_r.pop(k, None)
lf = open(f"{REPO}/logs/main_model.log", "a")
p = subprocess.Popen(["uv", "run", "mlx-serve", "start"], cwd=REPO, env=env_r, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
for _ in range(60):
    if listeners(): break
    time.sleep(2)
open(f"{WD}/m29/router_off.pid", "w").write(str(listeners()[0]) if listeners() else str(p.pid))
log(f"bench router restarted uv-pid={p.pid} listeners={listeners()} overlay=draft-off SESSION_MAX=2 APC={'APC_ENABLED' in env_r}")
log("=== chain3 DONE ===")
