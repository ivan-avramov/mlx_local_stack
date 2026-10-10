"""O40 live engagement smoke @ submodule 05a41b1b (2026-08-24, operator-directed:
through fork push + submodule bump, no cross-repo path hacks).

FUNCTION smoke, not a measurement: the per-request thinking_budget here is tiny (64)
BY DESIGN — it is the test vector for the forced-close mechanism, not a serving config.

Checks:
  A. F2 fail-loud: draft_kind mtp with NO draft_model must refuse the worker start.
  B. Batched path (MLX_VLM_CACHE_SESSION_MAX=0): budget+mtp request returns 200,
     timings carry engaged draft counters, output leaves thinking and answers.
  C. Cached/inline path (MLX_VLM_CACHE_SESSION_MAX=2): same assertions.

Router configs are runtime overlays in this directory (never repo edits — draft_model
is an absolute local path, same PII class as hf_path dirt).
"""
import json, os, re, signal, subprocess, sys, time, urllib.request

STACK = "$STACK_REPO"
W = os.path.expanduser("~/ws/mlx_local_stack_workdir/o40_smoke")
MODEL = "Qwen3.6-27B-Opus-Distill-OptiQ-4bit"
DRAFTER = os.path.expanduser(
    "~/ws/mlx_local_stack_workdir/scratch/m6a/Qwen3.6-27B-Opus-Distill-OptiQ-4bit-mtp-drafter")
PORT = 8093  # never the daily :8000; passed as --port (a CLI flag — the yaml "port" key is IGNORED
             # by mlx-serve start; first smoke attempt bound :8000 and died on the daily router)
WORKER_LOG = os.path.expanduser(f"~/.mlx-serve/logs/{MODEL}.log")  # worker stderr lands HERE, not the router log


def make_overlay(name, with_drafter):
    import yaml
    with open(os.path.join(STACK, "main_models.yaml")) as f:
        cfg = yaml.safe_load(f)
    models = [m for m in cfg["models"] if m.get("name") == MODEL]
    assert models, MODEL
    m = models[0]
    m["draft_kind"] = "mtp"
    if with_drafter:
        m["draft_model"] = DRAFTER
    else:
        m.pop("draft_model", None)
    m["on_demand"] = False  # load at start so refusal is visible immediately
    cfg["models"] = [m]
    cfg["port"] = PORT
    p = os.path.join(W, name)
    with open(p, "w") as f:
        yaml.safe_dump(cfg, f)
    return p


def start_router(overlay, session_max):
    env = {**os.environ,
           "MLX_VLM_CACHE_SESSION_MAX": str(session_max),
           "MLX_SERVE_CONFIG": overlay}
    env.pop("APC_ENABLED", None)
    log = open(os.path.join(W, f"router_{os.path.basename(overlay)}_{session_max}.log"), "w")
    p = subprocess.Popen(
        [os.path.join(STACK, ".venv/bin/mlx-serve"), "start", "--port", str(PORT)],
        stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        preexec_fn=os.setsid, cwd=STACK, env=env)
    return p, log.name


def stop_router(p):
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    except ProcessLookupError:
        pass
    for _ in range(30):
        if p.poll() is not None:
            break
        time.sleep(1)
    if p.poll() is None:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    time.sleep(2)


def wait_ready(deadline_s):
    t0 = time.time()
    while time.time() - t0 < deadline_s:
        try:
            with urllib.request.urlopen(f"http://localhost:{PORT}/v1/models", timeout=5) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(3)
    return False


def chat(budget, timeout_s=600):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content":
                      "Think carefully step by step: what is 17*23? Explain your reasoning at length."}],
        "max_tokens": 1024,
        "temperature": 0.3,
        "thinking_budget": budget,
        "enable_thinking": True,
        "presence_penalty": 0.0,
    }).encode()
    req = urllib.request.Request(
        f"http://localhost:{PORT}/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_s) as r:
        return r.status, json.loads(r.read())


def worker_cmdline():
    out = subprocess.run(["pgrep", "-f", "mlx_vlm.*server|mlx-vlm"], capture_output=True, text=True)
    for pid in out.stdout.split():
        cmd = subprocess.run(["ps", "-o", "command=", "-p", pid], capture_output=True, text=True).stdout
        if "--draft-kind" in cmd:
            return cmd.strip()
    # broader: any child holding --draft-kind
    out = subprocess.run(["pgrep", "-f", "--", "--draft-kind"], capture_output=True, text=True)
    for pid in out.stdout.split():
        cmd = subprocess.run(["ps", "-o", "command=", "-p", pid], capture_output=True, text=True).stdout
        return cmd.strip()
    return ""


def find_counters(obj):
    """Recursively find draft_* counters anywhere in the response JSON."""
    hits = {}
    def rec(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(k, str) and k.startswith("draft_"):
                    hits[k] = v
                rec(v)
        elif isinstance(o, list):
            for x in o:
                rec(x)
    rec(obj)
    return hits


results = {}

# ---- A: fail-loud ----------------------------------------------------------
print("== A: fail-loud (draft_kind mtp, no draft_model) ==", flush=True)
ov = make_overlay("overlay_no_drafter.yaml", with_drafter=False)
w0 = os.path.getsize(WORKER_LOG) if os.path.exists(WORKER_LOG) else 0  # daily router shares this log; scan only what THIS start appends
p, logp = start_router(ov, 2)
ready = wait_ready(240)
# The worker may only spawn (and refuse) at the first request, so the chat
# attempt comes FIRST and the logs are read AFTER it — reading before the chat
# was the ordering bug that made phase A unconcludable on the first two runs.
chat_ok = None
if ready:
    try:
        st, resp = chat(64, timeout_s=120)
        chat_ok = True
        results["A_note"] = "chat unexpectedly succeeded"
    except Exception as e:
        chat_ok = False
        results["A_note"] = f"chat refused as expected: {type(e).__name__}"
time.sleep(10)  # let the doomed worker finish writing its traceback
err_txt = open(logp).read() if os.path.exists(logp) else ""
if os.path.exists(WORKER_LOG):
    with open(WORKER_LOG) as f:
        f.seek(w0)
        err_txt += f.read()
refused = ("requires a drafter path" in err_txt)
# PASS = the refusal is LOUD (message in a log) AND the model is not servable.
ok_A = refused and chat_ok is not True
results["A_fail_loud"] = {"pass": bool(ok_A), "refusal_in_log": refused,
                          "model_unservable": chat_ok is not True}
print(json.dumps(results["A_fail_loud"]), flush=True)
stop_router(p)

# ---- B/C: engagement + budget ---------------------------------------------
for label, session_max in (("B_batched", 0), ("C_cached_inline", 2)):
    print(f"== {label} (MLX_VLM_CACHE_SESSION_MAX={session_max}) ==", flush=True)
    ov = make_overlay("overlay_with_drafter.yaml", with_drafter=True)
    p, logp = start_router(ov, session_max)
    if not wait_ready(600):
        results[label] = {"pass": False, "note": "router never ready"}
        stop_router(p); continue
    time.sleep(5)
    cmd = worker_cmdline()
    st, resp = chat(64)
    text = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
    reasoning = (resp.get("choices") or [{}])[0].get("message", {}).get("reasoning", "") or ""
    counters = find_counters(resp)
    engaged = counters.get("draft_kind") == "mtp" and (counters.get("draft_n") or 0) > 0
    left_thinking = bool(text.strip())
    results[label] = {
        "pass": bool(st == 200 and engaged and left_thinking),
        "http": st,
        "worker_has_draft_flags": ("--draft-kind mtp" in cmd and "--draft-model" in cmd),
        "counters": counters,
        "answer_len": len(text), "reasoning_len": len(reasoning),
    }
    print(json.dumps(results[label], default=str), flush=True)
    stop_router(p)

print("== SUMMARY ==", flush=True)
print(json.dumps(results, indent=2, default=str))
ok = all(v.get("pass") for k, v in results.items() if isinstance(v, dict) and "pass" in v)
print("SMOKE:", "PASS" if ok else "FAIL", flush=True)
sys.exit(0 if ok else 1)
