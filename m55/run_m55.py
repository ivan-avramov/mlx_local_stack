"""M55 polyglot gap chain: SESSIONS x MODELS x LANGS on the C37 22-item draws (rust/java/javascript). Session = fresh loaded instance
(unload between models; C109). Leg-resumable: a leg whose out file already has 22 rows is skipped. Writes RUNLOG.md. Fail-loud."""
import json, os, subprocess, time, sys, urllib.request
WD = "$STACK_WORKDIR"; REPO = "$STACK_REPO"; OUT = f"{WD}/m55"
draws = json.load(open(f"{WD}/m9/c37_draws.json"))
MODELS = ["Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "Qwen3.8-27B-mlx-uniform-4bit", "Ornith-1.0-35B-mlx-uniform-4bit"]
LANGS = ["rust", "java", "javascript"]
SESSIONS = [s for s in sys.argv[1:]] or ["s1", "s2"]
env = dict(os.environ); env["TMPDIR"] = f"{WD}/scratch/octmp"; env["STACK_WORKDIR"] = WD
env["MLX_SERVE_CONFIG"] = f"{WD}/m54/overlay_m54_draft_off.yaml"
def log(msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"; print(line, flush=True)
    with open(f"{OUT}/RUNLOG.md", "a") as f: f.write("- " + line + "\n")
def gate():
    w = subprocess.run("pmset -g ac | awk '/Wattage/{print $3}'", shell=True, capture_output=True, text=True).stdout.strip()
    b = subprocess.run("pmset -g batt | grep -oE '[0-9]+%' | head -1", shell=True, capture_output=True, text=True).stdout.strip().rstrip('%')
    o = subprocess.run([f"{REPO}/scripts/sweep_orphan_shells.sh"], capture_output=True, text=True).stdout
    ok = (w == "140W") and (int(b or 0) >= 20) and ("no orphaned" in o)
    log(f"GATE adapter={w} batt={b}% orphans={'0' if 'no orphaned' in o else 'PRESENT'} -> {'ok' if ok else 'FAIL'}")
    return ok
def unload(model):
    req = urllib.request.Request("http://localhost:8000/v1/models/unload", method="POST", data=json.dumps({"model": model}).encode(), headers={"Content-Type": "application/json"})
    try: urllib.request.urlopen(req, timeout=120).read(); log(f"unload {model} ok")
    except Exception as e: log(f"unload {model}: {e}")
    for _ in range(120):  # up to 10 min: the native16 worker's teardown exceeded the 2-min window once (2026-10-03 14:48 UTC)
        if subprocess.run(["pgrep", "-f", "mlx_vlm[.]server"], capture_output=True).returncode != 0: return True
        time.sleep(5)
    log("FATAL worker still alive after unload"); return False
def rows(p):
    try: return sum(1 for _ in open(p))
    except FileNotFoundError: return 0
log(f"START M55 sessions={SESSIONS} models={MODELS} langs={LANGS} opencode pinned; overlay={env['MLX_SERVE_CONFIG']}")
prev = None
for s in SESSIONS:
    for model in MODELS:
        if prev is not None and not unload(prev): sys.exit(3)
        prev = model
        for lang in LANGS:
            out = f"{OUT}/{s}/{model}.opencode_{lang}.jsonl"
            if rows(out) >= 22: log(f"SKIP {s} {model} {lang} (complete)"); continue
            if not gate(): log("gate FAIL -- ABORT"); sys.exit(4)
            log(f"START {s} {model} {lang} (22 items, {rows(out)} present)")
            with open(f"{OUT}/{s}/{model}.{lang}.log", "a") as lf:
                try:
                    rc = subprocess.run([f"{REPO}/.venv-bench/bin/python", f"{REPO}/benchmark/run_opencode_probe.py", "--model", model, "--items", ",".join(draws[lang]), "--lang", lang, "--out", out],
                                        cwd=REPO, env=env, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=28800).returncode
                except subprocess.TimeoutExpired: log(f"TIMEOUT {s} {model} {lang} at 28800 s -- ABORT"); sys.exit(2)
            r = [json.loads(l) for l in open(out)] if os.path.exists(out) else []
            log(f"END {s} {model} {lang} rc={rc} rows={len(r)} passed={sum(bool(x.get('passed')) for x in r)} mean_wall={sum(x.get('wall_s',0) for x in r)/max(1,len(r)):.0f}s")
            if rc != 0: log("FATAL leg rc != 0 -- ABORT"); sys.exit(1)
if prev: unload(prev)
log("ALL LEGS DONE")
