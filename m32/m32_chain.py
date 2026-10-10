"""M32 (PLAN row; queued 2026-09-03): opencode python leg for Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed @t0.5.
M3 22-item python set, O39 protocol (opencode 1.18.15 pinned binary, TMPDIR=scratch/octmp, progress gate 300/3600/2,
`deployed` profile, draft-OFF overlay, fresh worker session), paired by construction against the existing python arms.
Pre-registered read (PLAN M32): >=18/22 with stall-kills <=3 -> enters the B contest; <=15/22 -> closed for B on evidence.
Per the standing pilot rule: 5-item SEEDED pilot (random.Random(0).sample of the 22) -> PILOT SIZING logged, no abort on
the mean -> the remaining 17 items append to the same rows file -> SUMMARY + paired discordants vs the reference arms.

DRAFTED 2026-09-05 (box busy with M33). NOT LAUNCHED. Prerequisites (each verified by a fail-fast precheck below):
  M32_OVERLAY  a bench overlay whose mixed-checkpoint entry says temperature 0.5 (the M21 overlay says 0.6 -> the
               manifest's `deployed` sampling would lie; regenerate from HEAD main_models.yaml after the submodule bumps)
  M32_PIN      the src/mlx-vlm short sha the leg must run at (post-bump: 420c01e1)
  ~/.config/opencode/opencode.json is ABSENT since 2026-09-01 (brew opencode 1.18.20 re-initialised the dir); the chain
               installs benchmark/opencode_bench.json there for the leg and restores the prior state on exit."""
import atexit, json, math, os, random, shutil, subprocess, sys, threading, time
WD = os.environ["STACK_WORKDIR"]; REPO = os.environ["STACK_REPO"]
src = open(f"{WD}/m21/arms_chain.py").read().split("# ---------------------------------------------------------------- main")[0]
exec(src)  # noqa: S102  — log/sh/listeners/stop_router/start_router/overlay_sha/fatal/mem_sampler
OUT = f"{WD}/m32"; LOG = open(f"{OUT}/m32.log", "a", buffering=1)
OVERLAY = os.environ.get("M32_OVERLAY") or fatal("M32_OVERLAY unset")
PIN = os.environ.get("M32_PIN") or fatal("M32_PIN unset")
MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"; TUNE_T = 0.5
REFS = ["Qwen3.8-27B-mlx-uniform-4bit", "Ornith-1.0-35B-mlx-uniform-4bit",
        "Qwen3.6-27B-Opus-Distill-OptiQ-4bit", "Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit"]
PY_ITEMS = ("affine-cipher,beer-song,book-store,bottle-song,bowling,connect,dominoes,dot-dsl,food-chain,forth,go-counting,"
            "grade-school,grep,hangman,list-ops,paasio,phone-number,pig-latin,poker,pov,proverb,react").split(",")
PILOT = sorted(random.Random(0).sample(PY_ITEMS, 5))          # seed-0 draw across the corpus, never the first items
REST = [i for i in PY_ITEMS if i not in PILOT]
OC_BIN_DIR = f"{WD}/o39/opencode-1.18.15"; OC_PIN = "1.18.15"
OC_USER_CFG = os.path.expanduser("~/.config/opencode/opencode.json")
BENCH_CFG = f"{REPO}/benchmark/opencode_bench.json"
ROWS = f"{REPO}/benchmark/results/{MODEL}/opencode.jsonl"; MAN = ROWS.replace(".jsonl", ".manifest.json")
LEG_BOUND_S = 5 * 3600   # 22 items x 600 s stall bound = 3.7 h worst case; hard ceiling 3600 s only on a live-progress session

# ---------------------------------------------------------------- prechecks (fail-fast, touch nothing)
def precheck():
    v = sh([f"{OC_BIN_DIR}/opencode", "--version"]).stdout.strip()
    if v != OC_PIN: fatal(f"pinned opencode binary reports {v!r}, want {OC_PIN}")
    pin = sh(["git", "-C", f"{REPO}/src/mlx-vlm", "rev-parse", "--short=8", "HEAD"]).stdout.strip()
    if pin != PIN: fatal(f"src/mlx-vlm worktree is {pin}, want {PIN}")
    import yaml
    reg = yaml.safe_load(open(OVERLAY)); ent = [m for m in reg["models"] if m["name"] == MODEL]
    if not ent: fatal(f"{MODEL} missing from overlay {OVERLAY}")
    ent = ent[0]; t = ent["generation_defaults"]["temperature"]
    if abs(t - TUNE_T) > 1e-9: fatal(f"overlay temperature for {MODEL} is {t}, record says {TUNE_T} (manifest would lie)")
    if ent.get("draft_kind") or ent.get("draft_model"): fatal("overlay entry carries an active draft_* field (must be draft-OFF)")
    if not os.path.isdir(ent["hf_path"]) and "/" not in ent["hf_path"]: fatal(f"hf_path not resolvable: {ent['hf_path']}")
    oc = json.load(open(BENCH_CFG))["provider"]["mlx-local"]["models"].get(MODEL)
    if not oc: fatal(f"{MODEL} missing from {BENCH_CFG}")
    if abs(oc["options"]["temperature"] - TUNE_T) > 1e-9: fatal(f"opencode_bench.json temperature {oc['options']['temperature']} != {TUNE_T}")
    busy = sh(["pgrep", "-fl", r"python[^ ]* [^ ]*(run\.py generate|run_opencode_probe\.py|run_dsh_probe\.py|m33_chain\.py|m34_chain\.py)"]).stdout.strip()  # python drivers only — a monitor shell quoting the name is not a driver
    if busy: fatal(f"another bench driver is live:\n{busy}")
    if not os.path.isdir(os.environ.get("POLYGLOT_DIR", "")): fatal("POLYGLOT_DIR unset/missing")
    os.makedirs(f"{WD}/scratch/octmp", exist_ok=True)
    if os.path.isfile(ROWS): fatal(f"{ROWS} already exists — archive it first (rows must not mix runs)")
    log(f"PRECHECK OK: opencode {v}, worktree {pin}, overlay {OVERLAY} sha256={overlay_sha()} t={t}, pilot={PILOT}")

# ---------------------------------------------------------------- opencode user config (third-party default path: the escape hatch)
_backup = None; _installed = False
def install_bench_cfg():
    global _backup, _installed
    os.makedirs(os.path.dirname(OC_USER_CFG), exist_ok=True)
    if os.path.exists(OC_USER_CFG):
        _backup = f"{OUT}/opencode.json.user-backup-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(OC_USER_CFG, _backup); log(f"user opencode.json backed up to {_backup}")
    else: log("no user opencode.json present (absent since 2026-09-01) — installing the bench carrier for the leg")
    shutil.copy2(BENCH_CFG, OC_USER_CFG); _installed = True
    env = oc_env(); r = sh([f"{OC_BIN_DIR}/opencode", "models"], cwd=f"{WD}/scratch/octmp", env=env)
    ok = f"mlx-local/{MODEL}" in r.stdout
    log(f"opencode models sees mlx-local/{MODEL}: {ok}")
    if not ok: fatal(f"opencode does not list the model; stdout tail: {r.stdout[-400:]!r} stderr: {r.stderr[-300:]!r}")
def restore_cfg():
    if not _installed: return   # never touch a config this run did not install (bit 2026-09-06: removed the daily-driver config on a precheck FATAL)
    try:
        if _backup: shutil.copy2(_backup, OC_USER_CFG); log("user opencode.json restored")
        elif os.path.exists(OC_USER_CFG): os.remove(OC_USER_CFG); log("bench opencode.json removed (none existed before)")
    except Exception as ex: log(f"WARN restore_cfg: {ex}")
atexit.register(restore_cfg)
def oc_env():
    env = dict(os.environ); env.pop("APC_ENABLED", None)
    env["PATH"] = f"{OC_BIN_DIR}:" + env["PATH"]; env["TMPDIR"] = f"{WD}/scratch/octmp"; env["MLX_SERVE_CONFIG"] = OVERLAY
    return env

# ---------------------------------------------------------------- worker session discipline (M26: every leg gets a FRESH session)
def unload():
    import urllib.request
    if not sh(["pgrep", "-f", "mlx_vlm.server"]).stdout.strip(): log("no worker resident"); return
    try: urllib.request.urlopen(urllib.request.Request("http://localhost:8000/v1/models/unload", method="POST", data=b""), timeout=120).read(); log("unload POST ok")
    except Exception as ex: log(f"unload POST: {ex}")
    for _ in range(24):
        if not sh(["pgrep", "-f", "mlx_vlm.server"]).stdout.strip(): log("worker gone (pgrep verified)"); return
        time.sleep(5)
    fatal("worker still alive after unload")

# ---------------------------------------------------------------- leg runner + 5-min watch + C35
def rows():
    return [json.loads(l) for l in open(ROWS)] if os.path.isfile(ROWS) else []
def run_leg(items, tag):
    cmd = [PY, f"{REPO}/benchmark/run_opencode_probe.py", "--model", MODEL, "--items", ",".join(items), "--lang", "python", "--out", ROWS]
    log(f"RUN {tag}: {' '.join(cmd)}"); sha = overlay_sha(); log(f"overlay sha256={sha}")
    dl = open(f"{OUT}/{tag}.log", "a"); t_launch = time.time()
    d = subprocess.Popen(cmd, cwd=REPO, env=oc_env(), stdout=dl, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    open(f"{OUT}/{tag}.pid", "w").write(str(d.pid))
    n0 = len(rows()); last = n0; last_t = time.time(); checked = False; rc = None; tick = 0
    while rc is None:
        rc = d.poll()
        if not checked and os.path.isfile(MAN) and os.path.getmtime(MAN) >= t_launch - 5:
            try:
                mf = json.load(open(MAN)); dk = (mf.get("runtime") or {}).get("draft_kind"); rs = (mf.get("registry") or {}).get("sha256")
                smp = (mf.get("sampling") or {}).get("temperature"); ok = dk == "off" and rs == sha and abs((smp or -1) - TUNE_T) < 1e-9
                log(f"C35 check {MODEL}: runtime.draft_kind={dk} registry.sha256_match={rs == sha} sampling.temperature={smp} -> {'OK' if ok else 'MISMATCH'}")
                checked = True
                if not ok: d.kill(); fatal("provenance mismatch — driver killed; rows are FALSE-PROVENANCE, archive + regenerate")
            except Exception: pass
        if time.time() - last_t >= 300:
            tick += 1; rs_ = rows(); n = len(rs_); done = rs_[n0:]
            p = sum(1 for r in done if r.get("passed")); st = sum(1 for r in done if r.get("stop_reason") == "stalled")
            flat = "" if n > last else "  FLAT (a live session may legitimately run to its 600 s stall bound)"
            log(f"WATCH {tag} t+{tick*5}min: items {n - n0}/{len(items)} pass={p} stalled={st} driver=ALIVE{flat}")
            last, last_t = n, time.time()
        if time.time() - t_launch > LEG_BOUND_S: d.kill(); log(f"TIMEOUT {tag} after {LEG_BOUND_S/3600:.1f} h"); rc = -9; break
        time.sleep(15)
    log(f"END {tag} rc={rc}")
    return rc

def leg_summary(tag, expect):
    rs = [r for r in rows() if r["id"].startswith("python/")]
    p = sum(1 for r in rs if r.get("passed")); st = sum(1 for r in rs if r.get("stop_reason") == "stalled")
    nochange = sum(1 for r in rs if not r.get("file_changed")); fast = sum(1 for r in rs if r["wall_s"] < 60 and not r.get("passed"))
    w = [r["wall_s"] for r in rs]; tamper = sum(1 for r in rs if r.get("test_modified"))
    s = {"n": len(rs), "expect": expect, "pass": p, "stalled": st, "file_unchanged": nochange, "fast_giveups_lt60s": fast,
         "test_modified": tamper, "wall_mean_s": round(sum(w) / len(w), 1) if w else None, "wall_max_s": round(max(w), 1) if w else None,
         "wall_sum_h": round(sum(w) / 3600, 2), "opencode_version": rs[0].get("opencode_version") if rs else None}
    log(f"SUMMARY {tag} {MODEL}: {json.dumps(s)}"); return s

def mcnemar_exact(b, c):
    n = b + c
    if n == 0: return 1.0
    k = min(b, c); p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)
def paired_read():
    mine = {r["id"]: bool(r.get("passed")) for r in rows() if r["id"].startswith("python/")}
    for ref in REFS:
        p = f"{REPO}/benchmark/results/{ref}/opencode.jsonl"
        if not os.path.isfile(p): log(f"PAIRED vs {ref}: no rows"); continue
        theirs = {r["id"]: bool(r.get("passed")) for r in map(json.loads, open(p)) if r["id"].startswith("python/")}
        common = sorted(set(mine) & set(theirs)); b = sum(1 for i in common if mine[i] and not theirs[i]); c = sum(1 for i in common if theirs[i] and not mine[i])
        log(f"PAIRED vs {ref}: n={len(common)} mine={sum(mine[i] for i in common)} ref={sum(theirs[i] for i in common)} "
            f"discordant {b}:{c} McNemar exact p={mcnemar_exact(b, c):.3f}  mine-only={[i[7:] for i in common if mine[i] and not theirs[i]]} "
            f"ref-only={[i[7:] for i in common if theirs[i] and not mine[i]]}")

# ---------------------------------------------------------------- main
log("=== M32 START ===")
precheck()
threading.Thread(target=mem_sampler, daemon=True).start()
if not listeners(): start_router()
else:
    pid = listeners()[0]; e = sh(["ps", "-Eww", "-o", "command=", "-p", str(pid)]).stdout
    if ("MLX_SERVE_CONFIG=" + OVERLAY) not in e or "APC_ENABLED" in e or "MLX_VLM_CACHE_SESSION_MAX=2" not in e: stop_router(); start_router()
    else: log(f"router already up pid={pid} on {OVERLAY} (SESSION_MAX=2, APC absent)")
install_bench_cfg()
unload()
rc = run_leg(PILOT, "pilot")
if rc != 0: fatal(f"pilot rc={rc}")
s = leg_summary("pilot", 5)
if s["n"] < 5 or s["test_modified"]: fatal(f"pilot gate failed: {s}")
proj = s["wall_mean_s"] * 22 / 3600
log(f"PILOT SIZING: mean {s['wall_mean_s']} s/item -> {proj:.1f} h for n=22 (LOWER BOUND; max item {s['wall_max_s']} s; stall bound 600 s/item -> "
    f"worst case 3.7 h); nearest actuals: reference python arms 0.96-2.27 h per 22 (13/22 sibling arm: 2.27 h, 9 stall-kills). No abort on the pilot mean.")
rc = run_leg(REST, "rest")
if rc != 0: fatal(f"rest rc={rc}")
s = leg_summary("full", 22)
read = ("B CONTEST (>=18 pass, <=3 stall-kills) -> go leg n=164 + M6d predictor" if s["pass"] >= 18 and s["stalled"] <= 3
        else "CLOSED for B on evidence (<=15 pass)" if s["pass"] <= 15 else "BETWEEN the pre-registered bands — operator read")
log(f"PRE-REGISTERED READ: pass={s['pass']}/22 stall-kills={s['stalled']} -> {read}")
paired_read()
log("=== M32 DONE ===")
