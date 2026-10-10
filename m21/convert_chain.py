"""M21 conversion chain (operator GO 2026-09-01): quiet window -> re-download TeichAI/Qwen3.8-27B-Fable-Distill
bf16 -> (A) uniform int8 gs64 control via mlx_vlm.convert -> (B) OptiQ-mixed target-bpw 4.0 cand 4,8 gs64
(the recipe that produced Qwen3.8-27B-OptiQ-4.5bpw-mixed; ~4.5 effective bpw; KL calibration phase) ->
restart bench router on the draft-OFF overlay. Serial; mem sampler with swap alarm (+8 GB => ALARM lines)."""
import os, signal, subprocess, sys, threading, time
WD = os.environ["STACK_WORKDIR"]; REPO = os.environ["STACK_REPO"]
OUT = f"{WD}/m21"; SRC = "TeichAI/Qwen3.8-27B-Fable-Distill"
LOG = open(f"{OUT}/chain.log", "a", buffering=1)
def log(m): LOG.write(f"[{time.strftime('%m-%d %H:%M:%S')}] {m}\n")
def listeners():
    return [int(x) for x in subprocess.run(["lsof","-nP","-iTCP:8000","-sTCP:LISTEN","-t"],capture_output=True,text=True).stdout.split()]
def swap_used_mb():
    s = subprocess.run(["sysctl","-n","vm.swapusage"],capture_output=True,text=True).stdout
    try: return float(s.split("used =")[1].split("M")[0])
    except Exception: return -1.0
def stop_router():
    for p in listeners():
        log(f"kill router {p}");
        try: os.kill(p, signal.SIGTERM)
        except OSError: pass
    subprocess.run(["pkill","-f","uv run mlx-serve start"],capture_output=True)
    for _ in range(20):
        if not listeners(): log("0 listeners verified"); return True
        time.sleep(1)
    return not listeners()
def run(name, cmd, env, bound):
    log(f"RUN {name}: {' '.join(cmd)}")
    with open(f"{OUT}/{name}.log","a") as lf:
        try: rc = subprocess.run(cmd, cwd=REPO, env=env, stdout=lf, stderr=subprocess.STDOUT, timeout=bound).returncode
        except subprocess.TimeoutExpired: log(f"TIMEOUT {name} after {bound}s"); return None
    log(f"END {name} rc={rc}"); return rc
STOP = threading.Event(); base_swap = swap_used_mb()
def mem_sampler():
    with open(f"{OUT}/mem.log","a",buffering=1) as mf:
        while not STOP.is_set():
            s = swap_used_mb(); flag = "  ALARM-SWAP-GROWTH" if s - base_swap > 8192 else ""
            mf.write(f"[{time.strftime('%H:%M:%S')}] swap_used_mb={s:.0f} (base {base_swap:.0f}){flag}\n")
            if flag: log(f"ALARM: swap {s:.0f} MB (base {base_swap:.0f})")
            STOP.wait(30)
env = dict(os.environ); env.pop("APC_ENABLED", None)
log(f"=== m21 chain START === base_swap={base_swap:.0f}MB")
threading.Thread(target=mem_sampler, daemon=True).start()
if not stop_router(): log("FATAL: :8000 busy"); sys.exit(3)
rc = run("download", [f"{REPO}/.venv-optiq/bin/hf", "download", SRC], env, 14400)
if rc != 0:
    rc = run("download2", [f"{REPO}/.venv-optiq/bin/hf", "download", SRC], env, 14400)
    if rc != 0: log("FATAL: source download failed"); sys.exit(4)
rc = run("convert_int8", [f"{REPO}/.venv/bin/python","-m","mlx_vlm","convert","--hf-path",SRC,
     "--mlx-path",f"{WD}/models/Qwen3.8-27B-Fable-Distill-mlx-uniform-8bit","-q","--q-bits","8","--q-group-size","64"], env, 14400)
log(f"int8 artifact: rc={rc} " + subprocess.run(["du","-sh",f"{WD}/models/Qwen3.8-27B-Fable-Distill-mlx-uniform-8bit"],capture_output=True,text=True).stdout.strip())
rc2 = run("convert_optiq", [f"{REPO}/.venv-optiq/bin/optiq","convert",SRC,"--target-bpw","4.0","--candidate-bits","4,8",
     "--group-size","64","-o",f"{WD}/optiq_out/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"], env, 43200)
log(f"optiq artifact: rc={rc2} " + subprocess.run(["du","-sh",f"{WD}/optiq_out/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"],capture_output=True,text=True).stdout.strip())
STOP.set()
env_r = dict(env); env_r["MLX_VLM_CACHE_SESSION_MAX"]="2"; env_r["MLX_SERVE_CONFIG"]=f"{WD}/m6b/bench_overlay_draft_off.yaml"
lf = open(f"{REPO}/logs/main_model.log","a")
p = subprocess.Popen(["uv","run","mlx-serve","start"],cwd=REPO,env=env_r,stdout=lf,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
for _ in range(60):
    if listeners(): break
    time.sleep(2)
open(f"{WD}/m12/router_off.pid","w").write(str(listeners()[0]) if listeners() else str(p.pid))
log(f"router restarted listeners={listeners()} overlay=draft-off")
log("=== m21 chain DONE ===")
