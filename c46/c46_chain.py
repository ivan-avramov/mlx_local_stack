"""C46 (open-questions row, queued 2026-09-02): full n=50 re-measurements of the pre-C28 client-timeout rows.
Leg 1 (O37 evidence): Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit humanevalplus + mbppplus @t0.55 (deployed) and
@t0.6 (--temp 0.6), tunes t0.55-r2 / t0.6-r2. Leg 2 (M25 reference): Qwen3.8-27B-mlx-uniform-4bit vs
Qwen3.8-27B-OptiQ-4.5bpw-mixed humanevalplus + mbppplus @t0.6 (deployed), tune t0.6-r2.
Same seeded 50-item draw as the old rows (--seed 0; verified identical item sets 2026-09-03), --samples 1, bound 7800 s,
predictor OFF, router on the M21 draft-OFF overlay (same registry sha for every manifest), src/mlx-vlm worktree
pinned at 7330d3a6 (serving path 920efc38 == 57177a21 == the M21b arms). Per model: 5-item seeded pilot (first 5 of the
seed-0 shuffle, prefix-nested into the 50 draw, hep + mbpp) -> SIZING LOGGED against the nearest full-run actual, NO
abort on the pilot mean (fatal only on errors / incomplete) -> full n=50 per (bench, tune) -> grade -> compare.
The C46 deliverable per row: DNF FOLLOW-UP — every old 'timed out' item and what it did under the C28 bound.
Env knobs: C46_STOP_AFTER_LEG1=1 stops after leg 1; C46_SKIP_PILOT=1 skips the pilots. Logs: $STACK_WORKDIR/c46/c46.log."""
import os, sys, time
WD = os.environ["STACK_WORKDIR"]
src = open(f"{WD}/m21/arms_chain.py").read().split("# ---------------------------------------------------------------- main")[0]
exec(src)  # noqa: S102  (helpers: listeners/stop_router/start_router/run_generate+C35 check/summarize/mem_sampler)
OUT = f"{WD}/c46"          # helpers read OUT/BENCH/TUNE at call time; OVERLAY stays the M21 draft-OFF overlay
LOG = open(f"{OUT}/c46.log", "a", buffering=1)
PIN = "7330d3a6"
DV2 = "Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit"
BASE = "Qwen3.8-27B-mlx-uniform-4bit"
OPTQ = "Qwen3.8-27B-OptiQ-4.5bpw-mixed"
BENCHES = ("humanevalplus", "mbppplus")
# nearest full-run actuals (Σ wall of converged rows, this box) used for sizing; DNF tail budgeted on top
ACTUALS = {DV2: "old t0.55 rows: hep 1.2 h + mbpp 1.5 h converged (49+45 rows) + 4 holdout runaways ~1 h each at the full budget",
           BASE: "post-C28 mtpoff n=164 hep 10.5 h (231 s/item mean, max 4148 s); old t0.6 rows 2.7 h + 2.8 h converged + 3+6 timeouts",
           OPTQ: "old t0.6 rows: hep 3.1 h (48 rows) + mbpp 2.1 h (50 rows, zero timeouts) + 2 hep timeouts"}
threading.Thread(target=mem_sampler, daemon=True).start()
log("=== C46 START ===")
if not listeners(): start_router()
else:
    pid = listeners()[0]; e = sh(["ps","-Eww","-o","command=","-p",str(pid)]).stdout
    if ("MLX_SERVE_CONFIG=" + OVERLAY) not in e or "APC_ENABLED" in e: stop_router(); start_router()
    else: log(f"router already up pid={pid} on the M21 overlay (SESSION_MAX2={'MLX_VLM_CACHE_SESSION_MAX=2' in e}, APC absent)")
pin = sh(["git","-C",f"{REPO}/src/mlx-vlm","rev-parse","--short=8","HEAD"]).stdout.strip(); log(f"src/mlx-vlm worktree = {pin} (expect {PIN})")
if pin != PIN: fatal(f"submodule worktree is not at {PIN} — rows would carry a different serving-path hash")
env = dict(os.environ); env.pop("APC_ENABLED", None); env["MLX_SERVE_CONFIG"] = OVERLAY

def old_dnfs(model, bench, tune):
    p = f"{REPO}/benchmark/results/{model}/{bench}.{tune}.jsonl"
    return [json.loads(l)["id"] for l in open(p) if json.loads(l).get("error")] if os.path.isfile(p) else []
def dnf_followup(model, bench, old_tune, new_tune):
    """The C46 question, answered mechanically: what each pre-C28 'timed out' item did under the 7800 s bound."""
    global BENCH, TUNE
    BENCH, TUNE = bench, new_tune
    new = {r["id"]: r for r in rows(model)}
    out = []
    for i in old_dnfs(model, bench, old_tune):
        r = new.get(i)
        if r is None: out.append(f"{i}: MISSING"); continue
        st = "ERROR:" + str(r.get("error"))[:40] if r.get("error") else ("converged" if r.get("converged") else f"nonconv:{r.get('nonconv_kind')}")
        out.append(f"{i}: {st} wall={r.get('wall_s')} tok={r.get('completion_tokens')}")
    log(f"DNF FOLLOW-UP {model} {bench} {old_tune}->{new_tune} ({len(out)} old DNFs): " + " | ".join(out))
    new_dnf = [i for i, r in new.items() if r.get("error") or not r.get("converged")]
    log(f"NEW non-converged/error set {model} {bench} {new_tune}: {sorted(new_dnf)}")

def docker_up():
    if sh(["docker","info"]).returncode == 0: return True
    log("WARN: docker down — `open -a OrbStack`"); sh(["open","-a","OrbStack"])
    for _ in range(30):
        time.sleep(3)
        if sh(["docker","info"]).returncode == 0: log("docker back"); return True
    log("FATAL-ish: docker still down after 90 s; grading will return acc:None"); return False
def grade(model, bench, tune):
    global BENCH, TUNE
    BENCH, TUNE = bench, tune
    docker_up()
    g = sh([PY, f"{REPO}/benchmark/run.py", "grade", "--models", model, "--benches", bench, "--tune", tune], cwd=REPO, env=env)
    open(f"{OUT}/grade_{model}_{bench}_{tune}.log", "a").write(g.stdout + g.stderr); log(f"END grade {model} {bench}@{tune} rc={g.returncode}")
    sp = f"{REPO}/benchmark/results/{model}/{bench}.{tune}.score.json"
    try:
        s = json.load(open(sp)); log(f"SCORE {model} {bench}@{tune}: acc={s.get('acc')} acc_strict={s.get('acc_strict')} n={s.get('n')} note={s.get('note')}")
        if s.get("acc") is None: log(f"WARN: acc is None for {model} {bench}@{tune} — CHECK THE NOTE (docker?) before any compare")
    except Exception as ex: log(f"WARN: no score for {model} {bench}@{tune}: {ex}")
def compare(pair, bench, tag):
    for extra in ([], ["--intersect"]):
        c = sh([PY, f"{REPO}/benchmark/run.py", "compare", "--models", pair, "--benches", bench] + extra, cwd=REPO, env=env)
        open(f"{OUT}/compare_{tag}_{bench}{'_intersect' if extra else ''}.log", "a").write(c.stdout + c.stderr)
        log(f"END compare {tag} {bench}{' --intersect' if extra else ''} rc={c.returncode} :: {(c.stdout.strip().splitlines() or ['<no output>'])[-1][:200]}")

def pilot(model, tune, extra):
    global BENCH, TUNE
    TUNE = tune
    if os.environ.get("C46_SKIP_PILOT"): log(f"PILOT SKIPPED (C46_SKIP_PILOT) for {model}@{tune}"); return
    tot = 0.0; mx = 0.0
    for bench in BENCHES:
        BENCH = bench
        rc = run_generate([model], N_PILOT, f"pilot_{model}_{bench}_{tune}", probe_timeout=7800, extra=extra + ["--samples", "1"])
        s = summarize(model, 5)
        if s.get("n", 0) < 5 or s.get("errors"): fatal(f"pilot incomplete or errored ({model} {bench}@{tune}): {s}")
        tot += s["wall_mean_s"]; mx = max(mx, s["wall_max_s"])
    proj = tot * 50 / 3600
    log(f"PILOT SIZING {model}@{tune}: Σ mean {tot:.0f} s/item-pair -> {proj:.1f} h for hep+mbpp n=50 at this tune (LOWER BOUND; "
        f"max item {mx:.0f} s); nearest actual: {ACTUALS[model]}; budget-hit tail ≈ 1 h/item (81920 tok @ 20-26 tok/s) ON TOP. "
        f"No abort on the pilot mean (operator rule 2026-09-03).")

def arm(model, tune, extra, old_tune):
    global BENCH, TUNE
    TUNE = tune
    for bench in BENCHES:
        BENCH = bench
        rc = run_generate([model], N_FULL, f"full_{model}_{bench}_{tune}", probe_timeout=7800, extra=extra + ["--samples", "1"])
        if rc != 0: log(f"WARN: driver rc={rc} for {model} {bench}@{tune}")
        rs = rows(model); log(f"ROWS {model} {bench}@{tune}: {len(rs)} rows, converged={sum(1 for r in rs if r.get('converged'))}, errors={[r['id'] for r in rs if r.get('error')]}")
        summarize(model, 50)
        dnf_followup(model, bench, old_tune, tune)
        grade(model, bench, tune)

# ---------------- LEG 1: O37 evidence
log("--- LEG 1: Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit @t0.55-r2 (deployed) and @t0.6-r2 (--temp 0.6)")
pilot(DV2, "t0.55-r2", [])
arm(DV2, "t0.55-r2", [], "t0.55")
arm(DV2, "t0.6-r2", ["--temp", "0.6"], "t0.6")
for b in BENCHES: compare(f"{DV2}@t0.55-r2,{DV2}@t0.6-r2", b, "leg1_ladder")
for b in BENCHES: compare(f"{DV2}@t0.55,{DV2}@t0.55-r2", b, "leg1_old_vs_new")   # expected to REFUSE (serving path 17e0e5a7 vs 920efc38)
log("=== LEG 1 DONE (O37 re-test: does t0.55 still beat t0.6 on acc_strict@81920 under the C28 bound?) ===")
if os.environ.get("C46_STOP_AFTER_LEG1"): STOP.set(); log("=== C46 STOPPED after leg 1 (C46_STOP_AFTER_LEG1) ==="); sys.exit(0)
# ---------------- LEG 2: M25 reference pair
log("--- LEG 2: Qwen3.8-27B-mlx-uniform-4bit vs Qwen3.8-27B-OptiQ-4.5bpw-mixed @t0.6-r2 (deployed)")
for m in (BASE, OPTQ):
    pilot(m, "t0.6-r2", [])
    arm(m, "t0.6-r2", [], "t0.6")
for b in BENCHES: compare(f"{BASE}@t0.6-r2,{OPTQ}@t0.6-r2", b, "leg2_pair")
STOP.set(); log("=== C46 DONE === (review with the operator: O37 tune verdict, M25 wash, campaign-results dated corrections)")
