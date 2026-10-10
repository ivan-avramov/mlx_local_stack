"""M33 (operator GO 2026-09-03 "let's do the re-run if it will help quality"): math500 re-measure of the C-menu evidence under the
C28 bound. The registry's PROVISIONAL C-pick basis (O38) is the July n=30 math500 pair (acc_strict 81.5 vs 60.0, MDE +/-23pp,
3 pre-C28 timeout errors on the Qwen3.6 arm, fork f0d50c90 — pairs with nothing current). Arms, in order:
Ornith-1.0-35B-mlx-uniform-4bit @t0.4, Qwen3.6-27B-Opus-Distill-OptiQ-4bit @t0.3, NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit @t1.0
(all `deployed`, predictor OFF, M21 draft-OFF overlay, worktree 7330d3a6). Draw: seed-0 100-item math500 set (the old 30 nest in it),
k=1, tune `m33`, bound 7800 s. Per arm: 5-item seeded pilot -> sizing logged (no abort on the mean) -> n=50 -> n=100 (two resumes,
each under the helper's 20 h driver bound) -> grade. Then compare on all three pairs (+ --intersect). Endpoint (pre-registered, PLAN
M33): acc_strict@81920 on the paired n=100, Holm over the three pairs; runaway tax reported alongside; C order stays PROVISIONAL."""
import os, sys, time
WD = os.environ["STACK_WORKDIR"]
src = open(f"{WD}/m21/arms_chain.py").read().split("# ---------------------------------------------------------------- main")[0]
exec(src)  # noqa: S102
OUT = f"{WD}/m33"; LOG = open(f"{OUT}/m33.log", "a", buffering=1)
BENCH = "math500"; TUNE = "m33"; N_PILOT = 5; PIN = "7330d3a6"
ORN = "Ornith-1.0-35B-mlx-uniform-4bit"; Q36 = "Qwen3.6-27B-Opus-Distill-OptiQ-4bit"; NEM = "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit"
ARMS = (ORN, Q36, NEM)
ACTUALS = {ORN: "July n=30: 499 s/item mean (Σ 4.2 h), 35k tokens mean, 9/30 budget hits (each ~13 min at 76 tok/s)",
           Q36: "July n=30: 756 s/item mean over 27 rows (Σ 5.7 h), 13.7k tokens mean, 3 pre-C28 timeouts (a budget hit is ~60 min at 23 tok/s)",
           NEM: "no math500 row; hep n=100: 29 s/item, 3.8k tokens mean at 138 tok/s; M11 a24k reasoning: 4/15 budget hits (~13 min each)"}
threading.Thread(target=mem_sampler, daemon=True).start()
log("=== M33 START ===")
if not listeners(): start_router()
else:
    pid = listeners()[0]; e = sh(["ps","-Eww","-o","command=","-p",str(pid)]).stdout
    if ("MLX_SERVE_CONFIG=" + OVERLAY) not in e or "APC_ENABLED" in e: stop_router(); start_router()
    else: log(f"router already up pid={pid} on the M21 overlay (SESSION_MAX2={'MLX_VLM_CACHE_SESSION_MAX=2' in e}, APC absent)")
pin = sh(["git","-C",f"{REPO}/src/mlx-vlm","rev-parse","--short=8","HEAD"]).stdout.strip(); log(f"src/mlx-vlm worktree = {pin} (expect {PIN})")
if pin != PIN: fatal(f"submodule worktree is not at {PIN}")
env = dict(os.environ); env.pop("APC_ENABLED", None); env["MLX_SERVE_CONFIG"] = OVERLAY
def grade(model):
    g = sh([PY, f"{REPO}/benchmark/run.py", "grade", "--models", model, "--benches", BENCH, "--tune", TUNE], cwd=REPO, env=env)
    open(f"{OUT}/grade_{model}.log", "a").write(g.stdout + g.stderr); log(f"END grade {model} rc={g.returncode}")
    try:
        s = json.load(open(f"{REPO}/benchmark/results/{model}/{BENCH}.{TUNE}.score.json"))
        log(f"SCORE {model} math500@m33: acc={s.get('acc')} acc_strict={s.get('acc_strict')} n={s.get('n')} conv={s.get('conv_rate')} errors={s.get('errors')} note={s.get('note')}")
        if s.get("acc") is None: log(f"WARN: acc is None for {model} — CHECK THE NOTE")
    except Exception as ex: log(f"WARN: no score for {model}: {ex}")
def compare(pair, tag):
    for extra in ([], ["--intersect"]):
        c = sh([PY, f"{REPO}/benchmark/run.py", "compare", "--models", pair, "--benches", BENCH] + extra, cwd=REPO, env=env)
        open(f"{OUT}/compare_{tag}{'_intersect' if extra else ''}.log", "a").write(c.stdout + c.stderr)
        log(f"END compare {tag}{' --intersect' if extra else ''} rc={c.returncode} :: {(c.stdout.strip().splitlines() or ['<no output>'])[-1][:200]}")
for model in ARMS:
    rc = run_generate([model], N_PILOT, f"pilot_{model}", probe_timeout=7800, extra=["--samples", "1"])
    s = summarize(model, 5)
    if s.get("n", 0) < 5 or s.get("errors"): fatal(f"pilot incomplete or errored ({model}): {s}")
    log(f"PILOT SIZING {model}: mean {s['wall_mean_s']:.0f} s/item -> {s['wall_mean_s']*100/3600:.1f} h for n=100 (LOWER BOUND; max item {s['wall_max_s']:.0f} s, tok mean {s['tok_mean']}, max {s['tok_max']}); nearest actual: {ACTUALS[model]}. No abort on the pilot mean.")
    for n in (50, 100):
        rc = run_generate([model], n, f"full{n}_{model}", probe_timeout=7800, extra=["--samples", "1"])
        if rc != 0: log(f"WARN: driver rc={rc} for {model} n={n}")
        rs = rows(model); log(f"ROWS {model} math500@m33 n={n}: {len(rs)} rows, converged={sum(1 for r in rs if r.get('converged'))}, budget_hits={sum(1 for r in rs if r.get('nonconv_kind'))}, errors={[r['id'] for r in rs if r.get('error')]}")
        summarize(model, n)
    grade(model)
for a, b, tag in ((Q36, ORN, "q36_vs_ornith"), (Q36, NEM, "q36_vs_nemotron"), (ORN, NEM, "ornith_vs_nemotron")):
    compare(f"{a}@m33,{b}@m33", tag)
STOP.set(); log("=== M33 DONE === (review: acc_strict@81920 paired n=100, Holm over 3 pairs; runaway tax; C order stays PROVISIONAL until M18 + panel)")
