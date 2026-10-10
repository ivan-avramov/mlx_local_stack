import json, os, subprocess, sys, time, urllib.request
WD = "$STACK_WORKDIR"
REPO = "$STACK_REPO"
PY_ITEMS = "affine-cipher,beer-song,book-store,bottle-song,bowling,connect,dominoes,dot-dsl,food-chain,forth,go-counting,grade-school,grep,hangman,list-ops,paasio,phone-number,pig-latin,poker,pov,proverb,react"
JS_ITEMS = ",".join(json.load(open(f"{WD}/m9/c37_draws.json"))["javascript"])
MODELS = ["Qwen3.8-27B-mlx-uniform-4bit", "Qwen3.6-27B-Opus-Distill-OptiQ-4bit",
          "Ornith-1.0-35B-mlx-uniform-4bit"]
env = dict(os.environ)
env["PATH"] = f"{WD}/o39/opencode-1.18.15:" + env["PATH"]
env["TMPDIR"] = f"{WD}/scratch/octmp"
env["MLX_SERVE_CONFIG"] = f"{WD}/m6b/bench_overlay_draft_off.yaml"
LOG = open(f"{WD}/m9/m26_orchestrator.log", "a", buffering=1)
def log(m): LOG.write(f"[{time.strftime('%m-%d %H:%M:%S')}] {m}\n")

def unload():
    r = subprocess.run(["pgrep", "-f", "mlx_vlm.server"], capture_output=True)
    if r.returncode != 0:
        log("no worker resident"); return True
    req = urllib.request.Request("http://localhost:8000/v1/models/unload", method="POST", data=b"")
    try:
        urllib.request.urlopen(req, timeout=120).read(); log("unload POST ok")
    except Exception as e:
        log(f"unload POST: {e}")
    for _ in range(24):
        r = subprocess.run(["pgrep", "-f", "mlx_vlm.server"], capture_output=True)
        if r.returncode != 0:
            log("worker gone (pgrep verified)"); return True
        time.sleep(5)
    log("FATAL: worker still alive after unload"); return False

if not unload(): sys.exit(3)   # session-2 discipline: every model gets a FRESH worker session
for mi, model in enumerate(MODELS):
    if mi > 0 and not unload(): sys.exit(3)
    for lang, items in (("python", PY_ITEMS), ("javascript", JS_ITEMS)):
        out = f"{WD}/m9/{model}.opencode_{lang}.s2.jsonl"
        log(f"START {model} {lang} s2 (22 items)")
        with open(f"{WD}/m9/m26_{model}.{lang}.log", "a") as lf:
            try:
                rc = subprocess.run(
                    [f"{REPO}/.venv-bench/bin/python", f"{REPO}/benchmark/run_opencode_probe.py",
                     "--model", model, "--items", items, "--lang", lang, "--out", out],
                    cwd=REPO, env=env, stdout=lf, stderr=subprocess.STDOUT,
                    timeout=18000).returncode
            except subprocess.TimeoutExpired:
                log(f"TIMEOUT {model} {lang} — ABORT"); sys.exit(2)
        log(f"END {model} {lang} rc={rc}")
        if rc != 0:
            log(f"FATAL leg rc={rc} — ABORT"); sys.exit(1)
log("M26 ALL 6 LEGS DONE")
