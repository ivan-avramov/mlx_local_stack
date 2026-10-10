"""Engagement discriminator for the O40 cached path (C-phase nulls).

Code trace says inline mtp DOES dispatch (ar.py:662 gate is suffix-only) and the
nulls are a reporting gap (chunks carry no draft stats; telemetry reads chunks).
This probe gets runtime evidence with zero fork edits: same box, same model,
same prompt/params/seed, SESSION_MAX=2 both arms —

  arm 1 "mtp":   overlay_with_drafter.yaml  (drafter loaded, inline wiring)
  arm 2 "plain": overlay_plain.yaml         (no draft keys at all)

If arm1 generation_tps ~= arm2, the cached path is a silent no-op (bug).
If arm1 is clearly faster (B-phase acceptance was 87% -> expect ~1.5-1.9x),
engagement is real and only reporting is missing.
"""
import json, os, signal, subprocess, sys, time, urllib.request

STACK = "$STACK_REPO"
W = os.path.expanduser("~/ws/mlx_local_stack_workdir/o40_smoke")
MODEL = "Qwen3.6-27B-Opus-Distill-OptiQ-4bit"
PORT = 8093


def make_plain_overlay():
    import yaml
    with open(os.path.join(STACK, "main_models.yaml")) as f:
        cfg = yaml.safe_load(f)
    m = [x for x in cfg["models"] if x.get("name") == MODEL][0]
    m.pop("draft_kind", None)
    m.pop("draft_model", None)
    m["on_demand"] = False
    cfg["models"] = [m]
    p = os.path.join(W, "overlay_plain.yaml")
    with open(p, "w") as f:
        yaml.safe_dump(cfg, f)
    return p


def start_router(overlay, session_max):
    env = {**os.environ,
           "MLX_VLM_CACHE_SESSION_MAX": str(session_max),
           "MLX_SERVE_CONFIG": overlay}
    env.pop("APC_ENABLED", None)
    log = open(os.path.join(W, f"probe_router_{os.path.basename(overlay)}.log"), "w")
    p = subprocess.Popen(
        [os.path.join(STACK, ".venv/bin/mlx-serve"), "start", "--port", str(PORT)],
        stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        preexec_fn=os.setsid, cwd=STACK, env=env)
    return p


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


def chat(seed):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content":
                      "Think carefully step by step: what is 17*23? Explain your reasoning at length."}],
        "max_tokens": 1024,
        "temperature": 0.3,
        "thinking_budget": 64,
        "enable_thinking": True,
        "presence_penalty": 0.0,
        "seed": seed,
    }).encode()
    req = urllib.request.Request(
        f"http://localhost:{PORT}/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())


def tps_fields(resp):
    out = {}
    def rec(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(k, str) and ("tps" in k or k.startswith("draft_") or "token" in k):
                    if not isinstance(v, (dict, list)):
                        out[f"{path}{k}"] = v
                rec(v, f"{path}{k}.")
        elif isinstance(o, list):
            for x in o:
                rec(x, path)
    rec(resp)
    return out


arms = (("mtp", os.path.join(W, "overlay_with_drafter.yaml")),
        ("plain", make_plain_overlay()))
results = {}
for label, ov in arms:
    print(f"== {label} ({os.path.basename(ov)}) ==", flush=True)
    p = start_router(ov, 2)
    if not wait_ready(600):
        print(f"{label}: router never ready", flush=True)
        stop_router(p)
        sys.exit(2)
    time.sleep(5)
    per = []
    for seed in (11, 12, 13):
        resp = chat(seed)
        f = tps_fields(resp)
        per.append(f)
        print(json.dumps(f, default=str), flush=True)
    results[label] = per
    stop_router(p)

print("== VERDICT-INPUT ==", flush=True)
print(json.dumps(results, indent=1, default=str))
