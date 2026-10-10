"""M32b — B-contest legs for Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed @t0.5 (operator GO 2026-09-06 "go across the board", C49 = contest
legs first). Legs, in order:
  A. opencode GO leg (O39 22-item set), pilot 5 seeded -> rest 17; paired vs the four go reference rows (workdir m9/o39).
  B. humanevalplus n=164 tune `m32b`: the checkpoint @t0.5 (pilot 5 -> 164), then the B 3rd choice Qwen3.8-27B-mlx-uniform-4bit @t0.6
     re-measured in the SAME session on the SAME serving path (420c01e1 — its n=164 reference sits at 920efc38 and `compare` refuses across);
     grade both; compare (+intersect). Gate for the contest: not below the B 3rd choice's cell on acc_strict.
  C. predictor SPEED probe (M6a/M6d gate 1.3x) with the checkpoint's own MTP sidecar re-packed as a drafter dir; runs only if the dir exists
     (built box-free while A/B run); stops the campaign router first (the probe refuses a live :8000 and brings its own). The quality OFAT
     (n=164 mtp-ON vs the leg-B rows) is a follow-up launch if the gate passes.
Provenance: MLX_SERVE_CONFIG=<m32 overlay> on every driver, C35 on the first manifest of each arm, worktree pin checked, APC absent."""
import atexit, json, math, os, random, shutil, subprocess, sys, threading, time
WD = os.environ["STACK_WORKDIR"]; REPO = os.environ["STACK_REPO"]
src = open(f"{WD}/m21/arms_chain.py").read().split("# ---------------------------------------------------------------- main")[0]
exec(src)  # noqa: S102
OUT = f"{WD}/m32b"; LOG = open(f"{OUT}/m32b.log", "a", buffering=1)
OVERLAY = f"{WD}/m32/bench_overlay_m32.yaml"; PIN = "420c01e1"
MX = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"; U4 = "Qwen3.8-27B-mlx-uniform-4bit"; TUNE_T = 0.5
GO_ITEMS = ("counter,dnd-character,forth,alphametics,crypto-square,beer-song,book-store,bottle-song,bowling,connect,dominoes,error-handling,"
            "food-chain,hexadecimal,kindergarten-garden,ledger,markdown,matrix,octal,paasio,palindrome-products,pig-latin").split(",")
GO_PILOT = sorted(random.Random(0).sample(GO_ITEMS, 5)); GO_REST = [i for i in GO_ITEMS if i not in GO_PILOT]
GO_REFS = {U4: f"{WD}/m9/{U4}.opencode_go.jsonl", "Qwen3.8-27B-OptiQ-4.5bpw-mixed": f"{WD}/m9/Qwen3.8-27B-OptiQ-4.5bpw-mixed.opencode_go.jsonl",
           "Ornith-1.0-35B-mlx-uniform-4bit": f"{WD}/o39/Ornith-1.0-35B-mlx-uniform-4bit.opencode_go.jsonl",
           "Qwen3.6-27B-Opus-Distill-OptiQ-4bit": f"{WD}/o39/Qwen3.6-27B-Opus-Distill-OptiQ-4bit.opencode_go.jsonl"}
OC_BIN_DIR = f"{WD}/o39/opencode-1.18.15"; OC_PIN = "1.18.15"; OC_USER_CFG = os.path.expanduser("~/.config/opencode/opencode.json")
BENCH_CFG = f"{REPO}/benchmark/opencode_bench.json"; SHIPPED_CFG = f"{REPO}/opencode_config/opencode.json"
GO_ROWS = f"{REPO}/benchmark/results/{MX}/opencode_go.jsonl"; GO_MAN = GO_ROWS.replace(".jsonl", ".manifest.json")
DRAFTER = f"{WD}/scratch/m6a/{MX}-mtp-drafter"
BENCH = "humanevalplus"; TUNE = "m32b"; N_FULL = 164; N_PILOT = 5

def precheck():
    v = sh([f"{OC_BIN_DIR}/opencode", "--version"]).stdout.strip()
    if v != OC_PIN: fatal(f"pinned opencode reports {v!r}")
    pin = sh(["git", "-C", f"{REPO}/src/mlx-vlm", "rev-parse", "--short=8", "HEAD"]).stdout.strip()
    if pin != PIN: fatal(f"worktree {pin} != {PIN}")
    import yaml
    reg = yaml.safe_load(open(OVERLAY)); ent = {m["name"]: m for m in reg["models"]}
    for name, t in ((MX, 0.5), (U4, 0.6)):
        e = ent.get(name) or fatal(f"{name} missing from overlay")
        if abs(e["generation_defaults"]["temperature"] - t) > 1e-9: fatal(f"overlay {name} temperature != {t}")
        if e.get("draft_kind") or e.get("draft_model"): fatal(f"{name} overlay entry not draft-OFF")
    oc = json.load(open(BENCH_CFG))["provider"]["mlx-local"]["models"].get(MX) or fatal("bench carrier lacks the model")
    if abs(oc["options"]["temperature"] - TUNE_T) > 1e-9: fatal("bench carrier temperature != 0.5")
    busy = sh(["pgrep", "-fl", r"python[^ ]* [^ ]*(run\.py generate|run_opencode_probe\.py|run_dsh_probe\.py|m33_chain\.py|m32_chain\.py|m34_chain\.py|mtp_probe)"]).stdout.strip()
    if busy: fatal(f"another driver is live:\n{busy}")
    if sh(["docker", "info"]).returncode: fatal("docker is down (go grading + evalplus need it)")
    if os.path.isfile(GO_ROWS): fatal(f"{GO_ROWS} exists — archive first")
    for m in (MX, U4):
        if os.path.isfile(f"{REPO}/benchmark/results/{m}/{BENCH}.{TUNE}.jsonl"): fatal(f"{m} {BENCH}.{TUNE} rows exist — archive first")
    log(f"PRECHECK OK: opencode {v}, worktree {pin}, overlay sha256={overlay_sha()}, go pilot={GO_PILOT}, drafter_dir_present={os.path.isdir(DRAFTER)}")

# ---------------------------------------------------------------- opencode leg (pattern from m32_chain.py, with the _installed guard)
_backup = None; _installed = False
def oc_env():
    env = dict(os.environ); env.pop("APC_ENABLED", None)
    env["PATH"] = f"{OC_BIN_DIR}:" + env["PATH"]; env["TMPDIR"] = f"{WD}/scratch/octmp"; env["MLX_SERVE_CONFIG"] = OVERLAY
    return env
def install_bench_cfg():
    global _backup, _installed
    if os.path.exists(OC_USER_CFG):
        _backup = f"{OUT}/opencode.json.user-backup-{time.strftime('%Y%m%d-%H%M%S')}"; shutil.copy2(OC_USER_CFG, _backup); log(f"user opencode.json backed up to {_backup}")
    shutil.copy2(BENCH_CFG, OC_USER_CFG); _installed = True
    r = sh([f"{OC_BIN_DIR}/opencode", "models"], cwd=f"{WD}/scratch/octmp", env=oc_env())
    if f"mlx-local/{MX}" not in r.stdout: fatal(f"opencode does not list the model: {r.stdout[-300:]!r} {r.stderr[-200:]!r}")
    log("bench carrier installed; opencode lists the model")
def restore_cfg():
    if not _installed: return
    try:
        if _backup: shutil.copy2(_backup, OC_USER_CFG)
        else: shutil.copy2(SHIPPED_CFG, OC_USER_CFG)
        log("daily-driver opencode.json restored")
    except Exception as ex: log(f"WARN restore_cfg: {ex}")
atexit.register(restore_cfg)
def unload():
    import urllib.request
    if not sh(["pgrep", "-f", "mlx_vlm.server"]).stdout.strip(): log("no worker resident"); return
    try: urllib.request.urlopen(urllib.request.Request("http://localhost:8000/v1/models/unload", method="POST", data=b""), timeout=120).read(); log("unload POST ok")
    except Exception as ex: log(f"unload POST: {ex}")
    for _ in range(24):
        if not sh(["pgrep", "-f", "mlx_vlm.server"]).stdout.strip(): log("worker gone (pgrep verified)"); return
        time.sleep(5)
    fatal("worker still alive after unload")
def go_rows(): return [json.loads(l) for l in open(GO_ROWS)] if os.path.isfile(GO_ROWS) else []
def run_oc_leg(items, tag, bound_s=5*3600):
    cmd = [PY, f"{REPO}/benchmark/run_opencode_probe.py", "--model", MX, "--items", ",".join(items), "--lang", "go", "--out", GO_ROWS]
    log(f"RUN {tag}: {' '.join(cmd)}"); sha = overlay_sha(); t_launch = time.time()
    d = subprocess.Popen(cmd, cwd=REPO, env=oc_env(), stdout=open(f"{OUT}/{tag}.log", "a"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    open(f"{OUT}/{tag}.pid", "w").write(str(d.pid)); n0 = len(go_rows()); last = n0; last_t = time.time(); checked = False; rc = None; tick = 0
    while rc is None:
        rc = d.poll()
        if not checked and os.path.isfile(GO_MAN) and os.path.getmtime(GO_MAN) >= t_launch - 5:
            try:
                mf = json.load(open(GO_MAN)); dk = (mf.get("runtime") or {}).get("draft_kind"); rs = (mf.get("registry") or {}).get("sha256"); smp = (mf.get("sampling") or {}).get("temperature")
                ok = dk == "off" and rs == sha and abs((smp or -1) - TUNE_T) < 1e-9
                log(f"C35 check {MX} (go): runtime.draft_kind={dk} registry.sha256_match={rs == sha} sampling.temperature={smp} -> {'OK' if ok else 'MISMATCH'}"); checked = True
                if not ok: d.kill(); fatal("provenance mismatch — driver killed")
            except Exception: pass
        if time.time() - last_t >= 300:
            tick += 1; rs_ = go_rows(); n = len(rs_); done = rs_[n0:]
            log(f"WATCH {tag} t+{tick*5}min: items {n - n0}/{len(items)} pass={sum(1 for r in done if r.get('passed'))} stalled={sum(1 for r in done if r.get('stop_reason') == 'stalled')} skipped={sum(1 for r in done if r.get('note','').startswith('skipped') or r.get('grade_tail','').startswith('skipped'))} driver=ALIVE{'' if n > last else '  FLAT'}")
            last, last_t = n, time.time()
        if time.time() - t_launch > bound_s: d.kill(); log(f"TIMEOUT {tag}"); rc = -9; break
        time.sleep(15)
    log(f"END {tag} rc={rc}"); return rc
def go_summary(tag, expect):
    rs = [r for r in go_rows() if r["id"].startswith("go/")]
    p = sum(1 for r in rs if r.get("passed")); st = sum(1 for r in rs if r.get("stop_reason") == "stalled"); w = [r["wall_s"] for r in rs]
    s = {"n": len(rs), "expect": expect, "pass": p, "stalled": st, "file_unchanged": sum(1 for r in rs if not r.get("file_changed")),
         "fast_giveups_lt60s": sum(1 for r in rs if r["wall_s"] < 60 and not r.get("passed")), "test_modified": sum(1 for r in rs if r.get("test_modified")),
         "wall_mean_s": round(sum(w)/len(w), 1) if w else None, "wall_max_s": round(max(w), 1) if w else None, "wall_sum_h": round(sum(w)/3600, 2)}
    log(f"SUMMARY {tag} {MX} go: {json.dumps(s)}"); return s
def mcnemar(b, c):
    n = b + c; k = min(b, c); return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
def go_paired():
    mine = {r["id"]: bool(r.get("passed")) for r in go_rows() if r["id"].startswith("go/")}
    for ref, p in GO_REFS.items():
        if not os.path.isfile(p): log(f"PAIRED go vs {ref}: no rows"); continue
        theirs = {r["id"]: bool(r.get("passed")) for r in map(json.loads, open(p)) if r["id"].startswith("go/")}
        common = sorted(set(mine) & set(theirs)); b = sum(1 for i in common if mine[i] and not theirs[i]); c = sum(1 for i in common if theirs[i] and not mine[i])
        log(f"PAIRED go vs {ref}: n={len(common)} mine={sum(mine[i] for i in common)} ref={sum(theirs[i] for i in common)} discordant {b}:{c} McNemar exact p={mcnemar(b, c):.3f} mine-only={[i[3:] for i in common if mine[i] and not theirs[i]]} ref-only={[i[3:] for i in common if theirs[i] and not mine[i]]}")

# ---------------------------------------------------------------- hep leg (arms_chain helpers: run_generate/summarize/manifest/rows use BENCH/TUNE)
def grade(model):
    g = sh([PY, f"{REPO}/benchmark/run.py", "grade", "--models", model, "--benches", BENCH, "--tune", TUNE], cwd=REPO, env={**os.environ, "MLX_SERVE_CONFIG": OVERLAY})
    open(f"{OUT}/grade_{model}.log", "a").write(g.stdout + g.stderr); log(f"END grade {model} rc={g.returncode}")
    try:
        s = json.load(open(f"{REPO}/benchmark/results/{model}/{BENCH}.{TUNE}.score.json"))
        log(f"SCORE {model} {BENCH}@{TUNE}: acc={s.get('acc')} acc_strict={s.get('acc_strict')} n={s.get('n')} conv={s.get('conv_rate')} errors={s.get('errors')} note={s.get('note')}")
        if s.get("acc") is None: log(f"WARN: acc is None for {model} — CHECK THE NOTE (docker?)")
    except Exception as ex: log(f"WARN: no score for {model}: {ex}")
def compare(pair, tag):
    for extra in ([], ["--intersect"]):
        c = sh([PY, f"{REPO}/benchmark/run.py", "compare", "--models", pair, "--benches", BENCH, "--tune", TUNE] + extra, cwd=REPO, env={**os.environ, "MLX_SERVE_CONFIG": OVERLAY})
        open(f"{OUT}/compare_{tag}{'_intersect' if extra else ''}.log", "w").write(c.stdout + c.stderr)
        v = [l for l in c.stdout.splitlines() if "VERDICT" in l or "delta" in l or "matched items" in l]
        log(f"END compare {tag}{' --intersect' if extra else ''} rc={c.returncode} :: {' | '.join(x.strip() for x in v)[:400]}")

# ---------------------------------------------------------------- main
threading.Thread(target=mem_sampler, daemon=True).start()
log("=== M32B START ===")
precheck()
if not listeners(): start_router()
else:
    pid = listeners()[0]; e = sh(["ps", "-Eww", "-o", "command=", "-p", str(pid)]).stdout
    if ("MLX_SERVE_CONFIG=" + OVERLAY) not in e or "APC_ENABLED" in e or "MLX_VLM_CACHE_SESSION_MAX=2" not in e: stop_router(); start_router()
    else: log(f"router already up pid={pid} on the m32 overlay")
# ---- A. go leg
install_bench_cfg(); unload()
if run_oc_leg(GO_PILOT, "go_pilot") != 0: fatal("go pilot rc")
s = go_summary("go_pilot", 5)
if s["n"] < 5 or s["test_modified"]: fatal(f"go pilot gate: {s}")
log(f"PILOT SIZING go: mean {s['wall_mean_s']} s/item -> {s['wall_mean_s']*22/3600:.1f} h for n=22 (LOWER BOUND; max {s['wall_max_s']} s; stall bound 600 s -> worst 3.7 h); nearest actuals: go reference arms 1.1–2.2 h per 22 (5–6 stall-kills each). No abort on the pilot mean.")
if run_oc_leg(GO_REST, "go_rest") != 0: fatal("go rest rc")
s = go_summary("go_full", 22); go_paired()
log(f"GO READ: pass={s['pass']}/22 stall-kills={s['stalled']} vs the B 3rd choice's 16/22 (6 stall-kills) — {'NOT BELOW' if s['pass'] >= 16 else 'BELOW'} the B 3rd choice's cell")
restore_cfg(); _installed = False
# ---- B. hep n=164, both arms, one session
for model, actual in ((MX, "M21b t0.5 k=3: 87 s/item mean over 150 rows, max 2043 s, 0 non-converged -> ~4 h for 164"),
                      (U4, "M6d mtpoff n=164 (2026-08-30): 231 s/item mean, max 4148 s, 4 non-converged, 10.5 h")):
    rc = run_generate([model], N_PILOT, f"hep_pilot_{model}", probe_timeout=7800)
    if rc != 0: fatal(f"hep pilot rc={rc} for {model}")
    s = summarize(model, N_PILOT)
    if s["n"] < N_PILOT or s["errors"]: fatal(f"hep pilot gate {model}: {s}")
    log(f"PILOT SIZING {model}: mean {s['wall_mean_s']} s/item -> {s['wall_mean_s']*N_FULL/3600:.1f} h for n={N_FULL} (LOWER BOUND; max {s['wall_max_s']} s); nearest actual: {actual}. No abort on the pilot mean.")
    rc = run_generate([model], N_FULL, f"hep_full_{model}", probe_timeout=7800)
    if rc != 0: fatal(f"hep full rc={rc} for {model}")
    s = summarize(model, N_FULL); rs = rows(model)
    log(f"ROWS {model} {BENCH}@{TUNE} n={N_FULL}: {len(rs)} rows, converged={sum(1 for r in rs if r.get('converged'))}, errors={[r['id'] for r in rs if r.get('error')]}")
    grade(model)
compare(f"{MX},{U4}", "mixed_vs_u4")
# ---- C. predictor speed probe (own router; refuses a live :8000)
if os.path.isdir(DRAFTER):
    stop_router(); unload()
    env = dict(os.environ); env.pop("APC_ENABLED", None); env["MLX_SERVE_CONFIG"] = OVERLAY; env["PYTHONPATH"] = "."
    cmd = [PY, "-m", "m1.mtp_probe", "--model", MX, "--workdir", WD, "--draft-model", DRAFTER, "--json-out", f"{OUT}/mtp_probe.json"]
    log(f"RUN mtp_probe: {' '.join(cmd)}")
    p = subprocess.run(cmd, cwd=f"{REPO}/benchmark", env=env, stdout=open(f"{OUT}/mtp_probe.log", "a"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=3*3600)
    log(f"END mtp_probe rc={p.returncode}")
    try:
        j = json.load(open(f"{OUT}/mtp_probe.json")); g = j.get("gate") or j
        log(f"MTP PROBE {MX}: {json.dumps({k: g.get(k) for k in ('status','ratio','median_off','median_on','verdict','n_matched','acceptance','unengaged_items') if k in g})[:500]}")
    except Exception as ex: log(f"WARN: mtp_probe json unreadable: {ex}")
    log("router left DOWN after the probe (its throwaway router is stopped by the probe); restart on the m32 overlay before the next arm")
else:
    log(f"SKIP mtp_probe: drafter dir {DRAFTER} not present (build it from optiq/mtp.safetensors and launch the probe by hand)")
log("=== M32B DONE ===")
