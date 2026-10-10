"""M54 definitive arms on aac939b (clean capture: quiet box, session max 1): sequential, one resident model, unload between arms, watcher per arm,
bounded resume (max 2) after a nonzero driver exit once the router is healthy again. Writes RUNLOG."""
import os, sys, json, time, subprocess, urllib.request, signal
W = "$STACK_WORKDIR/m54"; WT = f"{W}/wt-aac939b/benchmark"; OUT = f"{W}/arms_aac939b_redo"
PY = "$STACK_REPO/.venv-bench/bin/python"; OV = f"{W}/overlay_m54_draft_off.yaml"
ROUTER_LOG = "$STACK_REPO/logs/main_model.log"
MODELS = sys.argv[1:]
LLM_TIMEOUT = "6000"   # explicit, UNVALIDATED: 102400 tokens / ~17 tok/s floor + headroom; covers a full-budget turn
TOTAL = 142; PRED = {"Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed": 19.0}
def log(msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"; print(line, flush=True)
    with open(f"{OUT}/RUNLOG.md", "a") as f: f.write("- " + line + "\n")
def router_ok():
    try: urllib.request.urlopen("http://localhost:8000/v1/models", timeout=10); return True
    except Exception as e: log(f"router not ok: {e}"); return False
def unload(model):
    req = urllib.request.Request("http://localhost:8000/v1/models/unload", data=json.dumps({"model": model}).encode(), headers={"Content-Type": "application/json"})
    try: log("unload " + model + " -> " + urllib.request.urlopen(req, timeout=120).read().decode()[:120])
    except Exception as e: log(f"unload {model} error: {e}")
def run_arm(model):
    d = f"{OUT}/{model}"; os.makedirs(d, exist_ok=True); out = f"{d}/agentbench_os.v1.jsonl"
    env = dict(os.environ, MLX_SERVE_CONFIG=OV, PYTHONPATH=".")
    for attempt in range(3):
        args = [PY, "-m", "bench.run_agentbench_os", "--model", model, "--llm-timeout", LLM_TIMEOUT, "--out", out, "--transcripts-dir", f"{OUT}/transcripts"] + (["--resume"] if attempt else [])
        with open(f"{d}/driver.log", "a") as lf:
            p = subprocess.Popen(args, cwd=WT, env=env, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        log(f"ARM {model} attempt {attempt} driver pid {p.pid}")
        time.sleep(20)
        wargs = [PY, "-m", "bench.agentbench_watch", "--rows", out, "--manifest", out.replace(".jsonl", ".manifest.json"), "--total", str(TOTAL), "--driver-pid", str(p.pid), "--router-log", ROUTER_LOG, "--out", f"{d}/watch.log", "--interval", "300", "--stall-s", "2700"] + (["--predicted-mean-s", str(PRED[model])] if model in PRED else [])
        with open(f"{d}/watch.stdout", "a") as wf:
            wp = subprocess.Popen(wargs, cwd=WT, env=env, stdout=wf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        rc = p.wait(); log(f"ARM {model} attempt {attempt} driver rc={rc}")
        time.sleep(5); 
        if wp.poll() is None: wp.send_signal(signal.SIGTERM); wp.wait(timeout=30)
        if rc == 0: return True
        if attempt < 2:
            log("unloading the model to drop retained KV sessions, then waiting 120 s before resume"); unload(model); time.sleep(120)
            if not router_ok(): log("router unhealthy; stopping the chain"); return False
    return False
def main():
    log(f"START REDO arms on aac939b after the 2026-10-02 power incident (same router session, clean capture); models={MODELS}; llm_timeout={LLM_TIMEOUT}")
    prev = None
    for m in MODELS:
        if prev: unload(prev); time.sleep(15)
        if not router_ok(): log("router down; abort"); sys.exit(2)
        ok = run_arm(m); prev = m
        s = f"{OUT}/{m}/agentbench_os.v1.summary.json"
        if os.path.exists(s):
            j = json.load(open(s)); log(f"RESULT {m}: " + json.dumps({k: j.get(k) for k in ('n','graded_n','passed','acc','acc_strict','conv_rate','setup_error_count','wall_total_s_mean','wall_total_s_max','completion_tokens_mean')}))
        if not ok: log(f"ARM {m} did not complete; stopping the chain"); sys.exit(1)
    unload(prev); log("ALL ARMS COMPLETE")
main()
