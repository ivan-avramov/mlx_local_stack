import json, os, subprocess, time, sys, urllib.request
WD = "$STACK_WORKDIR"
REPO = "$STACK_REPO"
draws = json.load(open(f"{WD}/m9/c37_draws.json"))
MODELS = ["Qwen3.8-27B-mlx-uniform-4bit", "Qwen3.6-27B-Opus-Distill-OptiQ-4bit",
          "Ornith-1.0-35B-mlx-uniform-4bit"]
LANGS = ["rust", "java", "javascript"]
env = dict(os.environ)
env["PATH"] = f"{WD}/o39/opencode-1.18.15:" + env["PATH"]
env["TMPDIR"] = f"{WD}/scratch/octmp"
env["MLX_SERVE_CONFIG"] = f"{WD}/m6b/bench_overlay_draft_off.yaml"
LOG = open(f"{WD}/m9/c37_orchestrator.log", "a", buffering=1)
def log(msg): LOG.write(f"[{time.strftime('%m-%d %H:%M:%S')}] {msg}\n")

def unload(model):
    for body in (b"", json.dumps({"model": model}).encode()):
        req = urllib.request.Request("http://localhost:8000/v1/models/unload",
                                     method="POST", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=120).read()
            log(f"unload POST ok (body={len(body)}B)")
        except Exception as e:
            log(f"unload POST ({len(body)}B): {e}")
        for _ in range(24):
            r = subprocess.run(["pgrep", "-f", "mlx_vlm.server"], capture_output=True)
            if r.returncode != 0:
                log("worker gone (pgrep verified)")
                return True
            time.sleep(5)
    log("FATAL: worker still alive after unload attempts")
    return False

prev = None
for model in MODELS:
    if prev is not None and not unload(prev):
        sys.exit(3)
    prev = model
    for lang in LANGS:
        items = ",".join(draws[lang])
        out = f"{WD}/m9/{model}.opencode_{lang}.jsonl"
        log(f"START {model} {lang} (22 items)")
        with open(f"{WD}/m9/c37_{model}.{lang}.log", "a") as lf:
            try:
                rc = subprocess.run(
                    [f"{REPO}/.venv-bench/bin/python",
                     f"{REPO}/benchmark/run_opencode_probe.py",
                     "--model", model, "--items", items, "--lang", lang, "--out", out],
                    cwd=REPO, env=env, stdout=lf, stderr=subprocess.STDOUT,
                    timeout=18000).returncode
            except subprocess.TimeoutExpired:
                log(f"TIMEOUT {model} {lang} at 18000s — ABORT")
                sys.exit(2)
        log(f"END {model} {lang} rc={rc}")
        if rc != 0:
            log(f"FATAL leg rc={rc} — ABORT (fail-loud, no silent skip)")
            sys.exit(1)
log("ALL 9 LEGS DONE")
