"""NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit temperature ladder (2026-08-31 night, P7 step 2).
Phase A: temperature OFAT on the M11 cliff rung (24K vartrack), t1.0 baseline re-measured alongside
         0.7/0.5/0.3, 5 draws each, tagged outputs (reasoning.t<T>.json) -- deployed reasoning.json untouched.
         PRE-REGISTERED PICK: highest temp with acc >= 0.85 AND budget_hits == 0 at 24K; none -> STOP axis.
Phase C: full ladder at the pick (M11 deep design: 8K..64K x5, 96K/128K/156K x3, early stop 2).
Phase D: humanevalplus n=15 seed-39 draw at the pick (--tune t<T>), graded (pass@1 hard constraint screen).
Fail-loud; SIGTERM this parent only (subprocess timeout kills the child)."""
import json, os, subprocess, sys, time, urllib.request
WD = os.environ["STACK_WORKDIR"]; REPO = os.environ["STACK_REPO"]
OUT = f"{WD}/nemo_ladder"; MODEL = "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit"
PY = f"{REPO}/.venv-bench/bin/python"
GRID = "8000,16000,24000,32000,48000,64000,96000,128000,156000"
TEMPS = [1.0, 0.7, 0.5, 0.3]
BOUND_A = 2 * 3600; BOUND_C = 12 * 3600; BOUND_D = 4 * 3600   # worst case = draws x 102400 tok / 138 tok/s (12.4 min)
env = dict(os.environ); env["MLX_SERVE_CONFIG"] = f"{WD}/m6b/bench_overlay_draft_off.yaml"; env.pop("APC_ENABLED", None)
LOG = open(f"{OUT}/orchestrator.log", "a", buffering=1)
def log(m): LOG.write(f"[{time.strftime('%m-%d %H:%M:%S')}] {m}\n")
def worker_cmd():
    return subprocess.run(["pgrep", "-fl", "mlx_vlm.server"], capture_output=True, text=True).stdout.strip()
def unload():
    if not worker_cmd(): log("no worker resident"); return True
    try: urllib.request.urlopen(urllib.request.Request("http://localhost:8000/v1/models/unload", method="POST", data=b""), timeout=120).read(); log("unload POST ok")
    except Exception as e: log(f"unload POST: {e}")
    for _ in range(24):
        if not worker_cmd(): log("worker gone (pgrep verified)"); return True
        time.sleep(5)
    log("FATAL: worker still alive after unload"); return False
def run(cmd, logname, bound, cwd):
    log(f"RUN {' '.join(cmd)}")
    with open(f"{OUT}/{logname}", "a") as lf:
        try: rc = subprocess.run(cmd, cwd=cwd, env=env, stdout=lf, stderr=subprocess.STDOUT, timeout=bound).returncode
        except subprocess.TimeoutExpired: log(f"FATAL: {logname} exceeded {bound}s"); sys.exit(4)
    log(f"END {logname} rc={rc}")
    if rc != 0: log("FATAL: nonzero rc"); sys.exit(rc)
def verify_worker():
    cmd = worker_cmd()
    ok = MODEL in cmd and "--draft" not in cmd
    log(f"worker cmdline check: model_present={MODEL in cmd} draft_flags={'--draft' in cmd} -> {'OK' if ok else 'FATAL'}")
    if not ok: sys.exit(7)
def ladder(temp, grid, tag, extra, bound):
    run([PY, "-m", "bench.run_reasoning", "--model", MODEL, "--grid", grid, "--sampling-profile", "deployed",
         "--request-timeout", "9600", "--temp", str(temp), "--out-tag", tag] + extra, f"ladder_{tag}.log", bound, f"{REPO}/benchmark")
    verify_worker()
    return json.load(open(f"{REPO}/benchmark/results/{MODEL}/reasoning.{tag}.json"))

log("=== START nemo_ladder ===")
if not unload(): sys.exit(3)
# Phase A
resA = {}
for t in TEMPS:
    tag = f"t{t}"
    rec = ladder(t, "24000", f"a24k.{tag}", ["--samples", "5", "--threshold", "0.0"], BOUND_A)["records"][0]
    resA[t] = rec; log(f"PHASE A t={t}: acc={rec['accuracy']} budget_hits={rec['budget_hits']} rows={[(r['completion_tokens'], r['score']) for r in rec['rows']]}")
passing = [t for t in TEMPS if resA[t]["accuracy"] >= 0.85 and resA[t]["budget_hits"] == 0]
json.dump({"phaseA": {str(t): resA[t] for t in TEMPS}, "passing": passing}, open(f"{OUT}/phaseA.json", "w"), indent=1)
if not passing:
    log("PHASE A: NO temp passes (acc>=0.85 AND 0 budget hits) -> STOP axis (temperature is not the lever at this rung)"); log("=== DONE (stopped at A) ==="); sys.exit(0)
pick = max(passing); log(f"PHASE A PICK t={pick} (highest passing; all passing={passing})")
# Phase C
tag = f"t{pick}"
resC = ladder(pick, GRID, tag, ["--samples", "5", "--deep-from", "96000", "--deep-samples", "3", "--early-stop-budget-hits", "2"], BOUND_C)
log(f"PHASE C t={pick}: reasoning_effective_ctx={resC['reasoning_effective_ctx']} records={[(r['ctx'], r['accuracy'], r['budget_hits']) for r in resC['records']]}")
# Phase D
gen = ["uv", "run", "python", "benchmark/run.py", "generate", "--models", MODEL, "--benches", "humanevalplus", "--limit", "humanevalplus=15",
       "--seed", "39", "--temp", str(pick), "--tune", tag, "--sampling-profile", "deployed", "--order", "roundrobin"]
run(gen, f"hep_{tag}.log", BOUND_D, REPO); verify_worker()
run(["uv", "run", "python", "benchmark/run.py", "grade", "--models", MODEL, "--benches", "humanevalplus", "--tune", tag], f"grade_{tag}.log", 3600, REPO)
try:
    sc = json.load(open(f"{REPO}/benchmark/results/{MODEL}/humanevalplus.{tag}.score.json")); log(f"PHASE D t={pick}: {json.dumps({k: sc.get(k) for k in ('n','acc','conv_rate','nonconv_kinds','loop_ids')})}")
except Exception as e: log(f"PHASE D score read failed: {e}")
json.dump({"pick": pick, "phaseA": {str(t): resA[t] for t in TEMPS}, "phaseC_effective_ctx": resC["reasoning_effective_ctx"]}, open(f"{OUT}/summary.json", "w"), indent=1)
log("=== DONE ===")
