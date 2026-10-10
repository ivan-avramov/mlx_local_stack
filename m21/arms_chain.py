"""M21 arms chain (2026-09-01). Waits for the conversion chain, verifies both artifacts, restarts the
bench router on the M21 TEMP overlay, then per arm: 5-item seeded pilot -> n=50 hep at the certified
t0.6 tune (same items/seeds as the Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit reference) -> grade ->
compare vs the reference. C35: every driver carries MLX_SERVE_CONFIG=<overlay>; the first manifest of
each model is checked for runtime.draft_kind == off and registry.sha256 == sha256(overlay) or the
driver is killed. bench_watch + swap sampler run alongside."""
import glob, hashlib, json, os, re, signal, statistics, subprocess, sys, threading, time
WD = os.environ["STACK_WORKDIR"]; REPO = os.environ["STACK_REPO"]
OUT = f"{WD}/m21"; OVERLAY = f"{OUT}/bench_overlay_m21.yaml"
PY = f"{REPO}/.venv-bench/bin/python"
REF = "Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit"
INT8 = "Qwen3.8-27B-Fable-Distill-mlx-uniform-8bit"
OPT = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
INT8_DIR = f"{WD}/models/{INT8}"; OPT_ROOT = f"{WD}/optiq_out/{OPT}"
BENCH = "humanevalplus"; TUNE = "t0.6"; BUDGET = 81920; N_FULL = 50; N_PILOT = 5
LOG = open(f"{OUT}/arms.log", "a", buffering=1)
def log(m): LOG.write(f"[{time.strftime('%m-%d %H:%M:%S')}] {m}\n")
def sh(cmd, **kw): return subprocess.run(cmd, capture_output=True, text=True, **kw)
def listeners():
    return [int(x) for x in sh(["lsof","-nP","-iTCP:8000","-sTCP:LISTEN","-t"]).stdout.split()]
def swap_used_mb():
    s = sh(["sysctl","-n","vm.swapusage"]).stdout
    try: return float(s.split("used =")[1].split("M")[0])
    except Exception: return -1.0
STOP = threading.Event(); base_swap = swap_used_mb()
def mem_sampler():
    with open(f"{OUT}/mem_arms.log","a",buffering=1) as mf:
        while not STOP.is_set():
            s = swap_used_mb(); flag = "  ALARM-SWAP-GROWTH" if s - base_swap > 8192 else ""
            mf.write(f"[{time.strftime('%H:%M:%S')}] swap_used_mb={s:.0f} (base {base_swap:.0f}){flag}\n")
            if flag: log(f"ALARM: swap {s:.0f} MB (base {base_swap:.0f})")
            STOP.wait(30)
def fatal(m): log(f"FATAL: {m}"); STOP.set(); sys.exit(2)

# ---------------------------------------------------------------- 0. wait for the conversion chain
def wait_chain(bound=8*3600):
    t0 = time.time()
    while time.time() - t0 < bound:
        txt = open(f"{OUT}/chain.log").read()
        pid = int(open(f"{OUT}/chain.pid").read().strip() or 0)
        alive = sh(["ps","-p",str(pid)]).returncode == 0
        if "=== m21 chain DONE ===" in txt and not alive: log("chain DONE observed"); return
        if not alive and "DONE" not in txt: log("WARN: chain pid dead WITHOUT DONE — verifying artifacts anyway"); return
        time.sleep(60)
    fatal("conversion chain did not finish within bound")

# ---------------------------------------------------------------- 1. verify artifacts
def shards_ok(d):
    cfg = f"{d}/config.json"
    if not os.path.isfile(cfg): return False, "no config.json"
    c = json.load(open(cfg)); idx = f"{d}/model.safetensors.index.json"
    st = sorted(glob.glob(f"{d}/*.safetensors"))
    if not st: return False, "no shards"
    if os.path.isfile(idx):
        # index names may live in SUBDIRS (optiq writes the vision sidecar as optiq/optiq_vision.safetensors)
        want = set(json.load(open(idx))["weight_map"].values())
        missing = [n for n in want if not os.path.isfile(os.path.join(d, n))]
        if missing: return False, f"index names {len(missing)} missing shard(s): {missing[:3]}"
    q = c.get("quantization") or c.get("quantization_config")
    gb = float(sh(["du","-sk",d]).stdout.split()[0]) / 1048576
    return True, f"size_gb={gb:.1f} model_type={c.get('model_type')} vision={'vision_config' in c} quant={str(q)[:120]} shards={len(st)} size={sh(['du','-sh',d]).stdout.split()[0]}"
def bpw_line(logf, phase_marker=None):
    """bpw reported by the conversion. For OptiQ the log holds SEVERAL phases (uniform baseline first);
    with `phase_marker` the value is read from the segment after the LAST line containing it."""
    txt = open(logf, errors="replace").read().replace("\r","\n")
    if phase_marker:
        seg = [l for l in txt.split("\n")]
        idx = [i for i, l in enumerate(seg) if phase_marker in l and "Converting" in l]
        if idx: txt = "\n".join(seg[idx[-1]:])
        else: log(f"WARN: phase marker {phase_marker!r} not found in {logf}; using last bpw line")
    m = re.findall(r"Quantized model with ([0-9.]+) bits per weight", txt); return float(m[0] if phase_marker else m[-1]) if m else None
def optiq_done_dir(logf):
    txt = open(logf, errors="replace").read().replace("\r","\n")
    m = re.findall(r"Done! OptiQ model saved to: (\S+)", txt); return m[-1] if m else None
def verify():
    models = []
    ok, why = shards_ok(INT8_DIR); bpw = bpw_line(f"{OUT}/convert_int8.log")
    log(f"int8 artifact: ok={ok} {why} bpw={bpw}")
    gb = float(sh(["du","-sk",INT8_DIR]).stdout.split()[0]) / 1048576 if ok else 0
    if ok and bpw and 8.0 <= bpw <= 9.0 and 25 <= gb <= 31: models.append(INT8)
    else: log("int8 arm DROPPED (verification failed)")
    done = optiq_done_dir(f"{OUT}/convert_optiq.log"); log(f"optiq 'Done! saved to' dir: {done}")
    # ONLY the mixed-recipe output is admissible: the converter also writes uniform_4bit and
    # static_mixed byproducts, and falling through to one of those served the WRONG recipe (19:47).
    cands = [c for c in ([done] if done else []) + [f"{OPT_ROOT}/optiq_mixed"] if c.rstrip("/").endswith("optiq_mixed")]
    opt_dir = None
    for d in cands:
        d = d.rstrip("/"); ok, why = shards_ok(d)
        if ok: opt_dir = d; log(f"optiq artifact @ {d}: {why}"); break
        log(f"optiq candidate {d}: {why}")
    bpw = bpw_line(f"{OUT}/convert_optiq.log", phase_marker="optiq_mixed"); log(f"optiq bpw line (optiq_mixed phase): {bpw}")
    gb = float(sh(["du","-sk",opt_dir]).stdout.split()[0]) / 1048576 if opt_dir else 0
    log(f"optiq size_gb={gb:.1f} (precedent recipe: 17.6 GB at 5.485 bpw reported incl. bf16 vision sidecar)")
    if opt_dir and bpw and 4.0 <= bpw <= 6.0 and 12 <= gb <= 20:
        y = open(OVERLAY).read()
        if opt_dir not in y:
            y2 = re.sub(r"(hf_path: )\S+(  # M21 TEMP OVERLAY — local artifact, OptiQ-mixed[^\n]*)", rf"\g<1>{opt_dir}\2", y)
            if y2 == y: fatal("could not rewrite the OptiQ hf_path in the overlay")
            open(OVERLAY,"w").write(y2); log(f"overlay OptiQ hf_path -> {opt_dir}")
        models.insert(0, OPT)   # deployable treatment first
    else: log("OptiQ arm DROPPED (verification failed) — int8 diagnostic only")
    if not models: fatal("no verified artifact")
    return models

# ---------------------------------------------------------------- 2. router on the TEMP overlay
def stop_router():
    for p in listeners():
        log(f"kill router listener {p}")
        try: os.kill(p, signal.SIGTERM)
        except OSError: pass
    for _ in range(30):
        if not listeners(): break
        time.sleep(1)
    for p in listeners():
        log(f"SIGKILL router listener {p}")
        try: os.kill(p, signal.SIGKILL)
        except OSError: pass
    time.sleep(2)
    if listeners(): fatal(":8000 still busy")
    for _ in range(60):   # let the worker subprocess exit (its Metal memory must be gone first)
        w = sh(["pgrep","-f","mlx_vlm.server|mlx_vlm/server"]).stdout.split()
        if not w: break
        time.sleep(2)
    else: log(f"WARN: worker pids still alive after 120s: {w}")
    log("0 listeners verified; worker gone")
def start_router():
    env = dict(os.environ); env.pop("APC_ENABLED", None)
    env["MLX_VLM_CACHE_SESSION_MAX"] = "2"; env["MLX_SERVE_CONFIG"] = OVERLAY
    lf = open(f"{REPO}/logs/main_model.log","a")
    p = subprocess.Popen(["uv","run","mlx-serve","start"], cwd=REPO, env=env, stdout=lf, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(90):
        if listeners(): break
        time.sleep(2)
    if not listeners(): fatal("router did not come up")
    pid = listeners()[0]; open(f"{OUT}/router.pid","w").write(str(pid))
    e = sh(["ps","-Eww","-o","command=","-p",str(pid)]).stdout
    log(f"router up pid={pid} MLX_SERVE_CONFIG_ok={('MLX_SERVE_CONFIG='+OVERLAY) in e} SESSION_MAX2={'MLX_VLM_CACHE_SESSION_MAX=2' in e} APC_absent={'APC_ENABLED' not in e}")
    if ("MLX_SERVE_CONFIG="+OVERLAY) not in e or "APC_ENABLED" in e: fatal("router env wrong")
    try:
        import urllib.request
        ids = [m["id"] for m in json.load(urllib.request.urlopen("http://localhost:8000/v1/models", timeout=30))["data"]]
        log(f"/v1/models has arms: {INT8 in ids}, {OPT in ids} (n={len(ids)})")
    except Exception as ex: log(f"WARN /v1/models: {ex}")

# ---------------------------------------------------------------- 3. driver + watcher + C35 check
def overlay_sha(): return hashlib.sha256(open(OVERLAY,"rb").read()).hexdigest()
def manifest(m): return f"{REPO}/benchmark/results/{m}/{BENCH}.{TUNE}.manifest.json"
def rows(m):
    p = f"{REPO}/benchmark/results/{m}/{BENCH}.{TUNE}.jsonl"
    return [json.loads(l) for l in open(p)] if os.path.isfile(p) else []
def run_generate(models, limit, tag, probe_timeout=None, extra=None):
    env = dict(os.environ); env.pop("APC_ENABLED", None); env["MLX_SERVE_CONFIG"] = OVERLAY
    cmd = [PY, f"{REPO}/benchmark/run.py", "generate", "--models", ",".join(models), "--benches", BENCH,
           "--limit", f"{BENCH}={limit}", "--seed", "0", "--order", "model", "--sampling-profile", "deployed",
           "--tune", TUNE, "--chunks", "all"]
    if probe_timeout: cmd += ["--probe-timeout", str(int(probe_timeout))]
    if extra: cmd += list(extra)
    log(f"RUN {tag}: {' '.join(cmd)}")
    sha = overlay_sha(); log(f"overlay sha256={sha}")
    dl = open(f"{OUT}/{tag}.log","a")
    d = subprocess.Popen(cmd, cwd=REPO, env=env, stdout=dl, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    open(f"{OUT}/{tag}.pid","w").write(str(d.pid))
    time.sleep(3)
    t_launch = time.time()
    e = sh(["ps","-Eww","-o","command=","-p",str(d.pid)]).stdout
    # ps -Eww truncates long command lines before the env block; the env was set by THIS launcher, so
    # only a CONTRARY value is evidence. The manifest's registry.sha256 is the authoritative C35 check.
    log(f"driver pid={d.pid} env MLX_SERVE_CONFIG shown={('MLX_SERVE_CONFIG='+OVERLAY) in e} (ps may truncate) APC_absent={'APC_ENABLED' not in e}")
    wenv = dict(env); wenv["PYTHONPATH"] = f"{REPO}/benchmark"
    wl = open(f"{OUT}/watch_{tag}.log","a")
    w = subprocess.Popen([PY, f"{REPO}/benchmark/m1/bench_watch.py", "--models", ",".join(models), "--bench", BENCH,
                          "--tune", TUNE, "--total", str(limit), "--driver-pattern", "run.py generate",
                          "--out", f"{OUT}/watch_{tag}.json", "--interval", "300"],
                         cwd=REPO, env=wenv, stdout=wl, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    checked = set(); rc = None; t0 = time.time()
    while rc is None:
        rc = d.poll()
        for m in models:
            if m in checked or not os.path.isfile(manifest(m)): continue
            try: mf = json.load(open(manifest(m)))
            except Exception: continue
            dk = (mf.get("runtime") or {}).get("draft_kind"); rs = (mf.get("registry") or {}).get("sha256")
            fresh = os.path.getmtime(manifest(m)) >= t_launch - 5
            # a RESUMED run keeps its original manifest (written under the overlay of that day); the sha
            # check is meaningful only for a manifest this driver wrote. draft_kind is checked either way.
            ok = dk == "off" and (rs == sha or not fresh)
            log(f"C35 check {m}: runtime.draft_kind={dk} registry.sha256_match={rs == sha} manifest_fresh={fresh} -> {'OK' if ok else 'MISMATCH'}")
            checked.add(m)
            if not ok:
                d.kill(); w.kill(); fatal(f"provenance mismatch on {m} — driver killed; rows are FALSE-PROVENANCE, archive + regenerate")
        if time.time() - t0 > 20*3600: d.kill(); log(f"TIMEOUT {tag} after 20h"); break
        time.sleep(15)
    w.kill(); log(f"END {tag} rc={rc}")
    return rc

def summarize(m, expect):
    rs = rows(m)
    if not rs: return {"n": 0}
    w = [r["wall_s"] for r in rs if r.get("wall_s") is not None]
    tps = [r["decode_tps"] for r in rs if r.get("decode_tps")]
    err = [(r["id"], str(r.get("error"))[:60]) for r in rs if r.get("error")]
    conv = sum(1 for r in rs if r.get("converged")); nk = {}
    for r in rs:
        if r.get("nonconv_kind"): nk[r["nonconv_kind"]] = nk.get(r["nonconv_kind"], 0) + 1
    ct = [r.get("completion_tokens") or 0 for r in rs]
    pk = [r.get("peak_mem_gb") for r in rs if r.get("peak_mem_gb")]
    s = {"n": len(rs), "expect": expect, "errors": err, "converged": conv, "nonconv_kinds": nk,
         "wall_mean_s": round(statistics.mean(w),1) if w else None, "wall_max_s": round(max(w),1) if w else None,
         "wall_sum_h": round(sum(w)/3600,2) if w else None, "tok_mean": round(statistics.mean(ct)) if ct else None,
         "tok_max": max(ct) if ct else None, "tps_min": round(min(tps),1) if tps else None,
         "tps_median": round(statistics.median(tps),1) if tps else None, "peak_mem_gb_max": max(pk) if pk else None}
    log(f"SUMMARY {m}: {json.dumps(s)}")
    return s

# ---------------------------------------------------------------- main
threading.Thread(target=mem_sampler, daemon=True).start()
log(f"=== m21 ARMS START === base_swap={base_swap:.0f}MB")
wait_chain()
models = verify()
log(f"arms (in order): {models}")
stop_router(); start_router()
rc = run_generate(models, N_PILOT, "pilot")
if rc != 0: fatal(f"pilot driver rc={rc}")
sums = {m: summarize(m, N_PILOT) for m in models}
bad = [m for m, s in sums.items() if s["n"] < N_PILOT or s["errors"]]
if bad: fatal(f"pilot gate FAILED for {bad} (short rows or transport errors) — not sizing the full run")
# sizing (mean-based lower bound + explicit heavy-tail allowance: 10% DNF at full budget)
pt = 0.0
for m, s in sums.items():
    tps = s["tps_min"] or 10.0
    budget_time = BUDGET / tps; want = budget_time * 1.5 + 300
    est_h = (s["wall_mean_s"] * N_FULL) / 3600; tail_h = 0.10 * N_FULL * budget_time / 3600
    log(f"SIZING {m}: mean {s['wall_mean_s']}s x50 = {est_h:.1f}h (LOWER BOUND) + 10%-DNF tail allowance {tail_h:.1f}h; "
        f"slowest decode {tps} tok/s -> full-budget draw {budget_time/60:.0f} min; bound wanted {want:.0f}s")
    pt = max(pt, want)
probe = int(300 * -(-pt // 300)) if pt > 7200 else None   # only override when the derived ceiling would orphan
log(f"probe timeout for the full run: {'EXPLICIT '+str(probe) if probe else 'DERIVED (harness, from the 5 pilot rows)'}")
rc = run_generate(models, N_FULL, "full", probe_timeout=probe)
if rc != 0: log(f"WARN: full driver rc={rc} — grading whatever exists")
for m in models: summarize(m, N_FULL)
env = dict(os.environ); env["MLX_SERVE_CONFIG"] = OVERLAY
g = sh([PY, f"{REPO}/benchmark/run.py", "grade", "--models", ",".join(models), "--benches", BENCH, "--tune", TUNE], cwd=REPO, env=env)
open(f"{OUT}/grade.log","a").write(g.stdout + g.stderr); log(f"END grade rc={g.returncode}")
for m in models:
    for extra in ([], ["--intersect"]):
        c = sh([PY, f"{REPO}/benchmark/run.py", "compare", "--models", f"{REF},{m}", "--benches", BENCH, "--tune", TUNE] + extra, cwd=REPO, env=env)
        open(f"{OUT}/compare_{m}{'_intersect' if extra else ''}.log","a").write(c.stdout + c.stderr)
        log(f"END compare {REF} vs {m}{' --intersect' if extra else ''} rc={c.returncode}")
STOP.set(); log("=== m21 ARMS DONE ===")
