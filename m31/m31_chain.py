"""M31 (PLAN row, operator GO 2026-09-03): ifeval arm for Qwen3.8-27B-mlx-uniform-4bit @t0.6 (deployed), paired with a
re-measured Qwen3.6-27B-Opus-Distill-OptiQ-4bit @t0.3 (deployed) — the existing 3.6 row (2026-08-18, fork 0c1c8b17,
serving path 17e0e5a7, 6 pre-C28 timeout DNFs) does not pair with HEAD, so `compare` would refuse; both arms run in
one session under one fingerprint. Draw: the seeded 148-item ifeval set (--seed 0; verified identical to the old row's
item set), --samples 1, bound 7800 s, predictor OFF, M21 draft-OFF overlay, worktree pinned at 7330d3a6.
Per model: 5-item seeded pilot (prefix-nested) -> sizing logged (no abort on the mean) -> full n=148 -> grade (vendored
IFEval verifiers; NLTK_DATA must point under $STACK_WORKDIR) -> compare (+ --intersect). Tune label `m31` on both arms.
Endpoint (pre-registered in PLAN): prompt-level strict; a >=5pp deficit vs the B 1st choice enters the B-menu narrative."""
import os, sys, time
WD = os.environ["STACK_WORKDIR"]
src = open(f"{WD}/m21/arms_chain.py").read().split("# ---------------------------------------------------------------- main")[0]
exec(src)  # noqa: S102
OUT = f"{WD}/m31"; LOG = open(f"{OUT}/m31.log", "a", buffering=1)
BENCH = "ifeval"; TUNE = "m31"; N_FULL = 148; N_PILOT = 5; PIN = "7330d3a6"
BASE = "Qwen3.8-27B-mlx-uniform-4bit"; Q36 = "Qwen3.6-27B-Opus-Distill-OptiQ-4bit"
threading.Thread(target=mem_sampler, daemon=True).start()
log("=== M31 START ===")
nd = os.environ.get("NLTK_DATA", "")
if not nd.startswith(WD): fatal(f"NLTK_DATA={nd!r} is not under STACK_WORKDIR — the IFEval grader would write ~/nltk_data")
if not listeners(): start_router()
else:
    pid = listeners()[0]; e = sh(["ps","-Eww","-o","command=","-p",str(pid)]).stdout
    if ("MLX_SERVE_CONFIG=" + OVERLAY) not in e or "APC_ENABLED" in e: stop_router(); start_router()
    else: log(f"router already up pid={pid} on the M21 overlay (SESSION_MAX2={'MLX_VLM_CACHE_SESSION_MAX=2' in e}, APC absent)")
pin = sh(["git","-C",f"{REPO}/src/mlx-vlm","rev-parse","--short=8","HEAD"]).stdout.strip(); log(f"src/mlx-vlm worktree = {pin} (expect {PIN})")
if pin != PIN: fatal(f"submodule worktree is not at {PIN}")
env = dict(os.environ); env.pop("APC_ENABLED", None); env["MLX_SERVE_CONFIG"] = OVERLAY
ACTUALS = {BASE: "no ifeval row; hep mtpoff n=164 post-C28: 231 s/item at 5.4k tokens mean (20-29 tok/s)",
           Q36: "old ifeval row 2026-08-18: 84 s/item mean over 142 rows (Σ 3.3 h), 1,957 tokens mean, + 6 pre-C28 timeout DNFs"}
def old_dnfs(model):
    p = f"{REPO}/benchmark/results/{model}/{BENCH}.jsonl"
    return [json.loads(l)["id"] for l in open(p) if json.loads(l).get("error")] if os.path.isfile(p) else []
def dnf_followup(model):
    new = {r["id"]: r for r in rows(model)}; out = []
    for i in old_dnfs(model):
        r = new.get(i)
        if r is None: out.append(f"{i}: MISSING"); continue
        st = "ERROR:" + str(r.get("error"))[:40] if r.get("error") else ("converged" if r.get("converged") else f"nonconv:{r.get('nonconv_kind')}")
        out.append(f"{i}: {st} wall={r.get('wall_s')} tok={r.get('completion_tokens')}")
    if out: log(f"DNF FOLLOW-UP {model} ifeval old->m31 ({len(out)} old DNFs): " + " | ".join(out))
    log(f"NEW non-converged/error set {model} ifeval m31: {sorted(i for i, r in new.items() if r.get('error') or not r.get('converged'))}")
def grade(model):
    g = sh([PY, f"{REPO}/benchmark/run.py", "grade", "--models", model, "--benches", BENCH, "--tune", TUNE], cwd=REPO, env=env)
    open(f"{OUT}/grade_{model}.log", "a").write(g.stdout + g.stderr); log(f"END grade {model} rc={g.returncode}")
    try:
        s = json.load(open(f"{REPO}/benchmark/results/{model}/{BENCH}.{TUNE}.score.json"))
        log(f"SCORE {model} ifeval@m31: prompt_strict={s.get('prompt_strict')} acc_strict={s.get('acc_strict')} prompt_loose={s.get('prompt_loose')} inst_strict={s.get('inst_strict')} n={s.get('n')} errors={s.get('errors')} note={s.get('note')}")
        if s.get("acc") is None: log(f"WARN: acc is None for {model} — CHECK THE NOTE")
    except Exception as ex: log(f"WARN: no score for {model}: {ex}")
def compare(pair, tag):
    for extra in ([], ["--intersect"]):
        c = sh([PY, f"{REPO}/benchmark/run.py", "compare", "--models", pair, "--benches", BENCH] + extra, cwd=REPO, env=env)
        open(f"{OUT}/compare_{tag}{'_intersect' if extra else ''}.log", "a").write(c.stdout + c.stderr)
        log(f"END compare {tag}{' --intersect' if extra else ''} rc={c.returncode} :: {(c.stdout.strip().splitlines() or ['<no output>'])[-1][:200]}")
for model in (BASE, Q36):
    rc = run_generate([model], N_PILOT, f"pilot_{model}", probe_timeout=7800, extra=["--samples", "1"])
    s = summarize(model, 5)
    if s.get("n", 0) < 5 or s.get("errors"): fatal(f"pilot incomplete or errored ({model}): {s}")
    log(f"PILOT SIZING {model}: mean {s['wall_mean_s']:.0f} s/item -> {s['wall_mean_s']*148/3600:.1f} h for n=148 (LOWER BOUND; max item {s['wall_max_s']:.0f} s, tok mean {s['tok_mean']}); nearest actual: {ACTUALS[model]}; budget-hit tail ~1 h/item on top. No abort on the pilot mean.")
    rc = run_generate([model], N_FULL, f"full_{model}", probe_timeout=7800, extra=["--samples", "1"])
    if rc != 0: log(f"WARN: driver rc={rc} for {model}")
    rs = rows(model); log(f"ROWS {model} ifeval@m31: {len(rs)} rows, converged={sum(1 for r in rs if r.get('converged'))}, errors={[r['id'] for r in rs if r.get('error')]}")
    summarize(model, N_FULL); dnf_followup(model); grade(model)
compare(f"{BASE}@m31,{Q36}@m31", "m31_pair")
compare(f"{Q36},{Q36}@m31", "q36_old_vs_new")   # expected to REFUSE (serving path 17e0e5a7 vs 920efc38)
STOP.set(); log("=== M31 DONE === (review: prompt-level strict, pre-registered >=5pp deficit rule; B menu does NOT re-rank on this alone)")
