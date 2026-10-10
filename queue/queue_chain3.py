"""QUEUE RUNNER (operator 2026-09-06 20:55: "keep going with tests — don't leave the machine idle; follow the queue"). Waits for M32b,
then runs, in order, continuing past any stage failure (router restored to the draft-OFF overlay between stages):
  S1  predictor quality OFAT for Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed IF the M32b MTP speed probe said GO (>=1.3x):
      draft-ON overlay (own sidecar drafter), hep n=164 tune `m32b-mtpon`, paired vs the `m32b` draft-OFF rows (paired_ofat.py).
  S2  M24 medium reasoning_effort arm on Qwen3.8-27B-mlx-uniform-4bit @t0.6: hep n=164 `t0.6-effmed` (paired vs the `m32b` xhigh rows,
      same serving path, same day), mbpp n=50 k=3 medium `t0.6-effmed` AND xhigh `m24x` (both fresh, same session). The opencode python leg
      at medium is DEFERRED: run_opencode_probe.py has no effort knob/manifest field (an unrecorded effort is an O36 hazard) — operator item.
  S3  M34 OFAT on Ornith-1.0-35B-mlx-uniform-4bit: native (`m34nat`, m32 overlay) vs expanded (`m34exp`, overlay with
      moe_expand 27-39:20:0.8:0.5): hep n=50 k=3, mbpp n=50 k=3, math500 n=100 k=1 (native re-run: the M33 row is at the old serving path).
  S4  M35 dsh: smoke (affine-cipher) -> 5-item seeded pilot -> remaining 17, tune `m35`, on Qwen3.8-27B-mlx-uniform-4bit; McNemar vs its
      opencode python row (20/22). The 8-point smoke checklist is for the operator/session to read in dsh_smoke.log.
Every driver: MLX_SERVE_CONFIG=<overlay>, APC absent, C35 on the first fresh manifest (expected draft state per arm), 5-item seeded pilot
before every n>=40 job (no abort on the pilot mean), bench_watch alongside, worker cmdline verified for draft/moe flags."""
import hashlib, json, math, os, random, re, shutil, signal, statistics, subprocess, sys, threading, time
WD = os.environ["STACK_WORKDIR"]; REPO = os.environ["STACK_REPO"]; PY = f"{REPO}/.venv-bench/bin/python"
OUT = f"{WD}/queue"; LOG = open(f"{OUT}/queue.log", "a", buffering=1)  # runner 2 (2026-09-07 13:15): resumes S2b, adds S2c low-effort legs, then S3/S4
def log(m): LOG.write(f"[{time.strftime('%m-%d %H:%M:%S')}] {m}\n")
def sh(cmd, **kw): return subprocess.run(cmd, capture_output=True, text=True, **kw)
def listeners(): return [int(x) for x in sh(["lsof", "-nP", "-iTCP:8000", "-sTCP:LISTEN", "-t"]).stdout.split()]
class StageFail(Exception): pass
def fail(m): log(f"FATAL: {m}"); raise StageFail(m)
OFF_OVERLAY = f"{WD}/queue/bench_overlay_q2.yaml"   # HEAD registry incl. the -MED and -LOW effort entries, draft-OFF
MX = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"; U4 = "Qwen3.8-27B-mlx-uniform-4bit"; U4MED = U4 + "-MED"; ORN = "Ornith-1.0-35B-mlx-uniform-4bit"
DRAFTER = f"{WD}/scratch/m6a/{MX}-mtp-drafter"; MOE = "27-39:20:0.8:0.5"
PY_ITEMS = ("affine-cipher,beer-song,book-store,bottle-song,bowling,connect,dominoes,dot-dsl,food-chain,forth,go-counting,grade-school,grep,"
            "hangman,list-ops,paasio,phone-number,pig-latin,poker,pov,proverb,react").split(",")
PY_PILOT = sorted(random.Random(0).sample(PY_ITEMS, 5)); PY_REST = [i for i in PY_ITEMS if i not in PY_PILOT]
# ---------------------------------------------------------------- router
def stop_router():
    for p in listeners():
        try: os.kill(p, signal.SIGTERM)
        except OSError: pass
    for _ in range(30):
        if not listeners(): break
        time.sleep(1)
    for p in listeners():
        try: os.kill(p, signal.SIGKILL)
        except OSError: pass
    time.sleep(2)
    if listeners(): fail(":8000 still busy")
    for _ in range(60):
        if not sh(["pgrep", "-f", "mlx_vlm.server|mlx_vlm/server"]).stdout.split(): break
        time.sleep(2)
    log("router stopped; 0 listeners; worker gone")
def start_router(overlay):
    env = dict(os.environ); env.pop("APC_ENABLED", None); env["MLX_VLM_CACHE_SESSION_MAX"] = "2"; env["MLX_SERVE_CONFIG"] = overlay
    subprocess.Popen(["uv", "run", "mlx-serve", "start"], cwd=REPO, env=env, stdout=open(f"{REPO}/logs/main_model.log", "a"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(90):
        if listeners(): break
        time.sleep(2)
    if not listeners(): fail("router did not come up")
    pid = listeners()[0]; e = sh(["ps", "-Eww", "-o", "command=", "-p", str(pid)]).stdout
    ok = ("MLX_SERVE_CONFIG=" + overlay) in e and "APC_ENABLED" not in e and "MLX_VLM_CACHE_SESSION_MAX=2" in e
    log(f"router up pid={pid} overlay={os.path.basename(overlay)} env_ok={ok}")
    if not ok: fail("router env wrong")
def ensure_router(overlay):
    if listeners():
        e = sh(["ps", "-Eww", "-o", "command=", "-p", str(listeners()[0])]).stdout
        if ("MLX_SERVE_CONFIG=" + overlay) in e and "APC_ENABLED" not in e and "MLX_VLM_CACHE_SESSION_MAX=2" in e: log(f"router already on {os.path.basename(overlay)}"); return
        stop_router()
    start_router(overlay)
def unload():
    import urllib.request
    if not sh(["pgrep", "-f", "mlx_vlm.server"]).stdout.strip(): return
    try: urllib.request.urlopen(urllib.request.Request("http://localhost:8000/v1/models/unload", method="POST", data=b""), timeout=120).read()
    except Exception as ex: log(f"unload POST: {ex}")
    for _ in range(24):
        if not sh(["pgrep", "-f", "mlx_vlm.server"]).stdout.strip(): log("worker unloaded (pgrep verified)"); return
        time.sleep(5)
    fail("worker still alive after unload")
def worker_cmdline():
    pids = sh(["pgrep", "-f", "mlx_vlm.server"]).stdout.split()
    return sh(["ps", "-o", "command=", "-p", pids[0]]).stdout if pids else ""
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def make_overlay(name, edits):
    """Copy the draft-OFF overlay and insert extra registry lines right after `    hf_path:` of the named entry."""
    src = open(OFF_OVERLAY).read().splitlines(); out = []; hit = False; inside = False
    for line in src:
        out.append(line)
        if re.match(r"^\s*- name: " + re.escape(name) + r"\s*$", line): inside = True; continue
        if inside and re.match(r"^\s*hf_path:", line):
            for e in edits: out.append("    " + e)
            inside = False; hit = True
    if not hit: fail(f"overlay edit: entry {name} not found")
    p = f"{OUT}/overlay_{name}_{hashlib.sha1(''.join(edits).encode()).hexdigest()[:6]}.yaml"
    open(p, "w").write("# QUEUE OVERLAY — generated from the M32 draft-OFF overlay + " + " | ".join(edits) + " on " + name + "\n" + "\n".join(out) + "\n")
    import yaml; yaml.safe_load(open(p)); return p
# ---------------------------------------------------------------- generate / grade / watch / C35
def rows(model, bench, tune):
    p = f"{REPO}/benchmark/results/{model}/{bench}.{tune}.jsonl"; return [json.loads(l) for l in open(p)] if os.path.isfile(p) else []
def run_generate(model, bench, tune, limit, tag, overlay, expect_draft="off", extra=None, samples=1, bound_h=20):
    env = dict(os.environ); env.pop("APC_ENABLED", None); env["MLX_SERVE_CONFIG"] = overlay
    cmd = [PY, f"{REPO}/benchmark/run.py", "generate", "--models", model, "--benches", bench, "--limit", f"{bench}={limit}", "--seed", "0",
           "--order", "model", "--sampling-profile", "deployed", "--tune", tune, "--chunks", "all", "--probe-timeout", "7800", "--samples", str(samples)] + list(extra or [])
    log(f"RUN {tag}: {' '.join(cmd)}"); s = sha(overlay); log(f"overlay {os.path.basename(overlay)} sha256={s}")
    d = subprocess.Popen(cmd, cwd=REPO, env=env, stdout=open(f"{OUT}/{tag}.log", "a"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    open(f"{OUT}/{tag}.pid", "w").write(str(d.pid)); t0 = time.time()
    wenv = dict(env); wenv["PYTHONPATH"] = f"{REPO}/benchmark"
    w = subprocess.Popen([PY, f"{REPO}/benchmark/m1/bench_watch.py", "--models", model, "--bench", bench, "--tune", tune, "--total", str(limit * samples), "--driver-pattern", "run.py generate", "--out", f"{OUT}/watch_{tag}.json", "--interval", "300"],
                         cwd=REPO, env=wenv, stdout=open(f"{OUT}/watch_{tag}.log", "a"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    man = f"{REPO}/benchmark/results/{model}/{bench}.{tune}.manifest.json"; checked = False; rc = None; cmd_checked = False
    while rc is None:
        rc = d.poll()
        if not checked and os.path.isfile(man) and os.path.getmtime(man) >= t0 - 5:
            try:
                mf = json.load(open(man)); dk = (mf.get("runtime") or {}).get("draft_kind"); rs = (mf.get("registry") or {}).get("sha256"); me = (mf.get("kv") or {}).get("moe_expand")
                ok = dk == expect_draft and rs == s
                log(f"C35 check {model} {tag}: runtime.draft_kind={dk} (expect {expect_draft}) registry.sha256_match={rs == s} kv.moe_expand={me} -> {'OK' if ok else 'MISMATCH'}"); checked = True
                if not ok: d.kill(); w.kill(); fail("provenance mismatch — driver killed; rows are FALSE-PROVENANCE")
            except StageFail: raise
            except Exception: pass
        if not cmd_checked:
            c = worker_cmdline()
            if c:
                log(f"worker cmdline: draft={'--draft-kind' in c} moe={'--moe-expand' in c} :: {c[-160:]}"); cmd_checked = True
                if (expect_draft == "off") == ("--draft-kind" in c): d.kill(); w.kill(); fail(f"worker draft state contradicts expect_draft={expect_draft}")
        if time.time() - t0 > bound_h * 3600: d.kill(); log(f"TIMEOUT {tag} after {bound_h} h"); rc = -9; break
        time.sleep(15)
    w.kill(); log(f"END {tag} rc={rc}"); return rc
def summarize(model, bench, tune, expect, tag):
    rs = rows(model, bench, tune)
    if not rs: log(f"SUMMARY {tag}: NO ROWS"); return {"n": 0, "errors": ["no rows"]}
    w = [r["wall_s"] for r in rs if r.get("wall_s") is not None]; ct = [r.get("completion_tokens") or 0 for r in rs]
    s = {"n": len(rs), "expect": expect, "errors": [(r["id"], str(r.get("error"))[:60]) for r in rs if r.get("error")], "converged": sum(1 for r in rs if r.get("converged")),
         "nonconv_kinds": dict((k, sum(1 for r in rs if r.get("nonconv_kind") == k)) for k in {r.get("nonconv_kind") for r in rs if r.get("nonconv_kind")}),
         "wall_mean_s": round(statistics.mean(w), 1) if w else None, "wall_max_s": round(max(w), 1) if w else None, "wall_sum_h": round(sum(w)/3600, 2) if w else None,
         "tok_mean": round(statistics.mean(ct)) if ct else None, "tok_max": max(ct) if ct else None,
         "draft_engaged": sum(1 for r in rs if (r.get("draft") or {}).get("draft_n")), "acc_rate": (lambda a: round(statistics.mean(a), 3) if a else None)([(r["draft"]["draft_n_accepted"] / r["draft"]["draft_n"]) for r in rs if (r.get("draft") or {}).get("draft_n")])}
    log(f"SUMMARY {tag}: {json.dumps(s)}"); return s
def grade(model, bench, tune, tag):
    g = sh([PY, f"{REPO}/benchmark/run.py", "grade", "--models", model, "--benches", bench, "--tune", tune], cwd=REPO, env={**os.environ, "MLX_SERVE_CONFIG": OFF_OVERLAY})
    open(f"{OUT}/grade_{tag}.log", "a").write(g.stdout + g.stderr); log(f"END grade {tag} rc={g.returncode}")
    try:
        s = json.load(open(f"{REPO}/benchmark/results/{model}/{bench}.{tune}.score.json"))
        log(f"SCORE {tag}: acc={s.get('acc')} acc_strict={s.get('acc_strict')} n={s.get('n')} conv={s.get('conv_rate')} errors={s.get('errors')} note={s.get('note')}")
        if s.get("acc") is None: log(f"WARN: acc None for {tag} (docker?)")
    except Exception as ex: log(f"WARN: no score for {tag}: {ex}")
def paired(bench, a, ta, b, tb, tag):
    p = sh([PY, f"{OUT}/paired_ofat.py", "--bench", bench, "--a", a, ta, "--b", b, tb, "--json", f"{OUT}/paired_{tag}.json"], cwd=f"{REPO}/benchmark", env={**os.environ, "PYTHONPATH": "."})
    open(f"{OUT}/paired_{tag}.log", "w").write(p.stdout + p.stderr)
    for l in (p.stdout or "").strip().splitlines(): log(f"PAIRED {tag}: {l}")
    if p.returncode: log(f"WARN paired {tag} rc={p.returncode}: {p.stderr[-300:]}")
def arm(model, bench, tune, n_full, overlay, tag, expect_draft="off", extra=None, samples=1, actual=""):
    """pilot 5 -> full -> grade. Skips generation if the rows file already holds >= n_full items (resume-safe across runner restarts)."""
    have = len({r["id"] for r in rows(model, bench, tune)})
    if have >= n_full: log(f"SKIP {tag}: {have} items already present"); grade(model, bench, tune, tag); return
    if have < 5:
        if run_generate(model, bench, tune, 5, f"{tag}_pilot", overlay, expect_draft, extra, samples) != 0: fail(f"{tag} pilot rc")
        s = summarize(model, bench, tune, 5 * samples, f"{tag}_pilot")
        if s["n"] < 5 or s["errors"]: fail(f"{tag} pilot gate: {s}")
        log(f"PILOT SIZING {tag}: mean {s['wall_mean_s']} s/row -> {s['wall_mean_s']*n_full*samples/3600:.1f} h for n={n_full} x k={samples} (LOWER BOUND; max {s['wall_max_s']} s); nearest actual: {actual or 'n/a'}. No abort on the pilot mean.")
    if run_generate(model, bench, tune, n_full, f"{tag}_full", overlay, expect_draft, extra, samples) != 0: fail(f"{tag} full rc")
    s = summarize(model, bench, tune, n_full * samples, f"{tag}_full"); rs = rows(model, bench, tune)
    log(f"ROWS {tag} n={n_full}xk{samples}: {len(rs)} rows, converged={sum(1 for r in rs if r.get('converged'))}, errors={[r['id'] for r in rs if r.get('error')]}")
    grade(model, bench, tune, tag)
# ---------------------------------------------------------------- agentic legs (opencode/dsh probes)
OC_BIN_DIR = f"{WD}/o39/opencode-1.18.15"; OC_USER_CFG = os.path.expanduser("~/.config/opencode/opencode.json"); BENCH_CFG = f"{REPO}/benchmark/opencode_bench.json"; SHIPPED_CFG = f"{REPO}/opencode_config/opencode.json"
def probe_env(overlay):
    env = dict(os.environ); env.pop("APC_ENABLED", None); env["PATH"] = f"{OC_BIN_DIR}:" + env["PATH"]; env["TMPDIR"] = f"{WD}/scratch/octmp"; env["MLX_SERVE_CONFIG"] = overlay; return env
def run_probe(script, model, items, tune, out_path, tag, overlay, extra=None, bound_s=5*3600):
    cmd = [PY, f"{REPO}/benchmark/{script}", "--model", model, "--items", ",".join(items), "--lang", "python", "--out", out_path] + list(extra or [])
    log(f"RUN {tag}: {' '.join(cmd)}"); t0 = time.time()
    d = subprocess.Popen(cmd, cwd=REPO, env=probe_env(overlay), stdout=open(f"{OUT}/{tag}.log", "a"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    open(f"{OUT}/{tag}.pid", "w").write(str(d.pid)); rc = None; last_t = time.time(); tick = 0
    def n(): return sum(1 for _ in open(out_path)) if os.path.isfile(out_path) else 0
    n0 = n()
    while rc is None:
        rc = d.poll()
        if time.time() - last_t >= 300:
            tick += 1; rs = [json.loads(l) for l in open(out_path)][n0:] if os.path.isfile(out_path) else []
            log(f"WATCH {tag} t+{tick*5}min: items {len(rs)}/{len(items)} pass={sum(1 for r in rs if r.get('passed'))} stalled={sum(1 for r in rs if r.get('stop_reason') == 'stalled')} driver=ALIVE"); last_t = time.time()
        if time.time() - t0 > bound_s: d.kill(); log(f"TIMEOUT {tag}"); rc = -9; break
        time.sleep(15)
    log(f"END {tag} rc={rc}"); return rc
def mcnemar(b, c):
    n = b + c; k = min(b, c); return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
def probe_summary(out_path, tag, refs):
    rs = [json.loads(l) for l in open(out_path)] if os.path.isfile(out_path) else []
    p = sum(1 for r in rs if r.get("passed")); st = sum(1 for r in rs if r.get("stop_reason") == "stalled"); w = [r["wall_s"] for r in rs]
    log(f"SUMMARY {tag}: n={len(rs)} pass={p} stalled={st} file_unchanged={sum(1 for r in rs if not r.get('file_changed'))} test_modified={sum(1 for r in rs if r.get('test_modified'))} wall_mean={round(sum(w)/len(w),1) if w else None} wall_sum_h={round(sum(w)/3600,2)}")
    mine = {r["id"]: bool(r.get("passed")) for r in rs}
    for ref, rp in refs.items():
        if not os.path.isfile(rp): continue
        theirs = {r["id"]: bool(r.get("passed")) for r in map(json.loads, open(rp)) if r["id"].startswith("python/")}
        common = sorted(set(mine) & set(theirs)); b = sum(1 for i in common if mine[i] and not theirs[i]); c = sum(1 for i in common if theirs[i] and not mine[i])
        log(f"PAIRED {tag} vs {ref}: n={len(common)} mine={sum(mine[i] for i in common)} ref={sum(theirs[i] for i in common)} discordant {b}:{c} p={mcnemar(b, c):.3f} mine-only={[i.split('/')[1] for i in common if mine[i] and not theirs[i]]} ref-only={[i.split('/')[1] for i in common if theirs[i] and not mine[i]]}")
    return p, st
# ---------------------------------------------------------------- stages
def stage(name, fn):
    log(f"=== {name} START ===")
    try: fn(); log(f"=== {name} DONE ===")
    except StageFail as ex: log(f"=== {name} FAILED: {ex} — continuing with the next stage ===")
    except Exception as ex:
        import traceback; log(f"=== {name} CRASHED: {ex!r} — continuing ===\n" + traceback.format_exc()[-1500:])
    try: ensure_router(OFF_OVERLAY)
    except Exception as ex: log(f"WARN: could not restore the draft-OFF router: {ex}")
def s0_wait_m32b():
    pid = int(open(f"{WD}/m32b/m32b.pid").read().strip()); log(f"waiting on m32b_chain pid {pid}")
    while True:
        try: os.kill(pid, 0)
        except OSError: break
        time.sleep(60)
    tail = open(f"{WD}/m32b/m32b.log").read()[-3000:]; log(f"m32b exited; DONE={'=== M32B DONE ===' in tail}"); time.sleep(20)
def s1_predictor_ofat():
    try: j = json.load(open(f"{WD}/m32b/mtp_probe.json")); g = j.get("gate") or {}
    except Exception as ex: fail(f"no mtp_probe.json ({ex}) — predictor OFAT skipped")
    log(f"MTP gate: {json.dumps(g)[:300]}")
    if not str(g.get("verdict", "")).startswith("GO"): log("predictor gate did not pass — no quality OFAT (probe-only stays recorded)"); return
    on = make_overlay(MX, ["draft_kind: mtp", f"draft_model: {DRAFTER}"]); log(f"draft-ON overlay {on}")
    stop_router(); start_router(on)
    arm(MX, "humanevalplus", "m32b-mtpon", 164, on, "S1_mx_hep_mtpon", expect_draft="mtp", actual="m32b draft-OFF: 61 s/item mean, 2.8 h for 164")
    paired("humanevalplus", MX, "m32b-mtpon", MX, "m32b", "S1_mtpon_vs_off")
    stop_router(); start_router(OFF_OVERLAY)
def s2_effort(base, med, hep_ref_tune, xhigh_rate_hint, oc_refs, tag):
    """M24 via the registry route (operator 2026-09-06 P23): the -MED entry carries reasoning_effort=medium in generation_defaults, so every
    client measures it unchanged. xhigh = the base entry (hep reference = its `hep_ref_tune` rows on the current serving path; mbpp xhigh is
    re-measured fresh as `m24x`). Effort READBACK: the xhigh template injects an explicit instruction, so prompt_tokens on the same items must
    DIFFER between the -MED pilot rows and the base rows — checked before spending the full arm."""
    ensure_router(OFF_OVERLAY)
    if run_generate(med, "humanevalplus", "m24", 5, f"{tag}_hep_pilot", OFF_OVERLAY) != 0: fail(f"{tag} pilot rc")
    s = summarize(med, "humanevalplus", "m24", 5, f"{tag}_hep_pilot")
    if s["n"] < 5 or s["errors"]: fail(f"{tag} pilot gate: {s}")
    medr = {r["id"]: r.get("prompt_tokens") for r in rows(med, "humanevalplus", "m24")}; xh = {r["id"]: r.get("prompt_tokens") for r in rows(base, "humanevalplus", hep_ref_tune)}
    pairs = [(i, medr[i], xh.get(i)) for i in medr]; differ = sum(1 for _, a, b in pairs if a and b and a != b)
    medtok = statistics.mean(r.get("completion_tokens") or 0 for r in rows(med, "humanevalplus", "m24")); xhtok = statistics.mean([(r.get("completion_tokens") or 0) for r in rows(base, "humanevalplus", hep_ref_tune) if r["id"] in medr] or [0])
    log(f"EFFORT READBACK {tag}: prompt_tokens differ on {differ}/{len(pairs)} pilot items (MED vs xhigh: {pairs}); completion tokens mean {medtok:.0f} vs {xhtok:.0f} on the same items")
    if differ == 0: fail(f"EFFORT READBACK FAILED {tag}: identical prompt_tokens — the medium template did not engage; arm aborted before spending the box")
    log(f"PILOT SIZING {tag} hep: mean {s['wall_mean_s']} s/item -> {s['wall_mean_s']*164/3600:.1f} h for 164 (LOWER BOUND); xhigh actual: {xhigh_rate_hint}. No abort on the pilot mean.")
    if run_generate(med, "humanevalplus", "m24", 164, f"{tag}_hep_full", OFF_OVERLAY) != 0: fail(f"{tag} hep full rc")
    summarize(med, "humanevalplus", "m24", 164, f"{tag}_hep_full"); grade(med, "humanevalplus", "m24", f"{tag}_hep")
    paired("humanevalplus", med, "m24", base, hep_ref_tune, f"{tag}_hep_med_vs_xhigh")
    arm(med, "mbppplus", "m24", 50, OFF_OVERLAY, f"{tag}_mbpp_med", samples=3, actual=f"xhigh hep: {xhigh_rate_hint}")
    arm(base, "mbppplus", "m24x", 50, OFF_OVERLAY, f"{tag}_mbpp_xhigh", samples=3, actual=f"xhigh hep: {xhigh_rate_hint}")
    paired("mbppplus", med, "m24", base, "m24x", f"{tag}_mbpp_med_vs_xhigh")
    # opencode python leg at medium: the -MED entry is in the bench carrier; opencode omits the effort field -> the worker applies the registry default
    global _installed, _backup
    if os.path.exists(OC_USER_CFG): _backup = f"{OUT}/opencode.json.user-backup-{time.strftime('%Y%m%d-%H%M%S')}"; shutil.copy2(OC_USER_CFG, _backup)
    shutil.copy2(BENCH_CFG, OC_USER_CFG); _installed = True
    r = sh([f"{OC_BIN_DIR}/opencode", "models"], cwd=f"{WD}/scratch/octmp", env=probe_env(OFF_OVERLAY))
    if f"mlx-local/{med}" not in r.stdout: restore_cfg(); fail(f"opencode does not list {med}")
    unload(); outp = f"{REPO}/benchmark/results/{med}/opencode.jsonl"
    try:
        if run_probe("run_opencode_probe.py", med, PY_PILOT, "m24", outp, f"{tag}_oc_pilot", OFF_OVERLAY) != 0: fail(f"{tag} opencode pilot rc")
        probe_summary(outp, f"{tag}_oc_pilot", {})
        if run_probe("run_opencode_probe.py", med, PY_REST, "m24", outp, f"{tag}_oc_rest", OFF_OVERLAY) != 0: fail(f"{tag} opencode rest rc")
        p, st = probe_summary(outp, f"{tag}_oc_full", oc_refs)
        log(f"M24 READ {tag} (pre-registered): strict EQUIVALENT AND tokens ratio CI < 1 AND opencode >= 18/22 with <= 3 stall-kills -> medium becomes a CANDIDATE operating point; got opencode {p}/22, {st} stall-kills — see PAIRED lines")
    finally: restore_cfg()
def s2_m24_medium():
    s2_effort(U4, U4MED, "m32b", "195 s/item, 2 loops, ~9 h for 164 (m32b)", {U4 + " opencode s1": f"{REPO}/benchmark/results/{U4}/opencode.jsonl", U4 + " opencode s2": f"{REPO}/benchmark/results/{U4}/opencode.s2.jsonl"}, "S2_u4med")
def s2b_m24_mixed():
    s2_effort(MX, MX + "-MED", "m32b", "61 s/item, 0 loops, 2.8 h for 164 (m32b)", {MX + " opencode": f"{REPO}/benchmark/results/{MX}/opencode.jsonl"}, "S2b_mxmed")
_backup = None; _installed = False
def restore_cfg():
    global _installed
    if not _installed: return
    try:
        shutil.copy2(_backup if _backup else SHIPPED_CFG, OC_USER_CFG); log("daily-driver opencode.json restored")
    except Exception as ex: log(f"WARN restore_cfg: {ex}")
    _installed = False
def s2c_low():
    """Operator 2026-09-07: ONE hep n=164 leg per checkpoint at reasoning_effort=low (the -LOW entries) — the third point on the effort curve.
    Never a candidate operating point. Readback gate: prompt_tokens must differ from the xhigh rows (and are reported vs the -MED rows)."""
    ensure_router(OFF_OVERLAY)
    for base, hint in ((U4, "xhigh 195 s/item (m32b); medium 28 s/item (m24)"), (MX, "xhigh 61 s/item (m32b); medium ~33 s/item (m24)")):
        low = base + "-LOW"; tag = f"S2c_{'u4' if base == U4 else 'mx'}low"
        if run_generate(low, "humanevalplus", "m24", 5, f"{tag}_hep_pilot", OFF_OVERLAY) != 0: fail(f"{tag} pilot rc")
        s = summarize(low, "humanevalplus", "m24", 5, f"{tag}_hep_pilot")
        if s["n"] < 5 or s["errors"]: fail(f"{tag} pilot gate: {s}")
        lo = {r["id"]: r.get("prompt_tokens") for r in rows(low, "humanevalplus", "m24")}
        xh = {r["id"]: r.get("prompt_tokens") for r in rows(base, "humanevalplus", "m32b")}; md = {r["id"]: r.get("prompt_tokens") for r in rows(base + "-MED", "humanevalplus", "m24")}
        d_xh = sum(1 for i in lo if lo[i] and xh.get(i) and lo[i] != xh[i]); d_md = sum(1 for i in lo if lo[i] and md.get(i) and lo[i] != md[i])
        log(f"EFFORT READBACK {tag}: prompt_tokens differ from xhigh on {d_xh}/{len(lo)} and from medium on {d_md}/{len(lo)} pilot items ({[(i, lo[i], md.get(i), xh.get(i)) for i in lo]})")
        if d_xh == 0: fail(f"EFFORT READBACK FAILED {tag}: identical to xhigh")
        log(f"PILOT SIZING {tag}: mean {s['wall_mean_s']} s/item -> {s['wall_mean_s']*164/3600:.1f} h for 164 (LOWER BOUND); actuals: {hint}. No abort on the pilot mean.")
        if run_generate(low, "humanevalplus", "m24", 164, f"{tag}_hep_full", OFF_OVERLAY) != 0: fail(f"{tag} full rc")
        summarize(low, "humanevalplus", "m24", 164, f"{tag}_hep_full"); grade(low, "humanevalplus", "m24", f"{tag}_hep")
        paired("humanevalplus", low, "m24", base, "m32b", f"{tag}_vs_xhigh"); paired("humanevalplus", low, "m24", base + "-MED", "m24", f"{tag}_vs_medium")
def s3_m34_ofat():
    exp = make_overlay(ORN, [f'moe_expand: "{MOE}"']); log(f"moe-expand overlay {exp}")
    for bench, n, k in (("humanevalplus", 50, 3), ("mbppplus", 50, 3), ("math500", 100, 1)):
        ensure_router(OFF_OVERLAY)
        arm(ORN, bench, "m34nat", n, OFF_OVERLAY, f"S3_orn_{bench}_nat", samples=k, actual="M33 math500: 170 s/item, 4.7 h per 100; M27 hep n=164 OFF: 4.65 h")
        stop_router(); start_router(exp)
        arm(ORN, bench, "m34exp", n, exp, f"S3_orn_{bench}_exp", samples=k, actual="native arm just measured (expect slower per token, memory-bound)")
        stop_router(); start_router(OFF_OVERLAY)
        paired(bench, ORN, "m34exp", ORN, "m34nat", f"S3_{bench}_exp_vs_nat")
def s4_m35_dsh():
    ensure_router(OFF_OVERLAY); unload()
    outp = f"{REPO}/benchmark/results/{U4}/dsh.m35.jsonl"
    if os.path.isfile(outp): fail(f"{outp} exists — archive first")
    if run_probe("run_dsh_probe.py", U4, ["affine-cipher"], "m35", outp, "S4_dsh_smoke", OFF_OVERLAY, extra=["--tune", "m35"], bound_s=3600) != 0: fail("dsh smoke rc != 0 — read S4_dsh_smoke.log against the 8-point checklist")
    rs = [json.loads(l) for l in open(outp)]
    log(f"DSH SMOKE row: {json.dumps({k: rs[-1].get(k) for k in ('id','passed','file_changed','stop_reason','wall_s','harness','harness_version','model')})}")
    if not rs[-1].get("file_changed"): fail("dsh smoke: file_changed=False — checklist item 2 failed; leg not started")
    pilot = [i for i in PY_PILOT if i != "affine-cipher"]; rest = [i for i in PY_ITEMS if i not in pilot and i != "affine-cipher"]
    if run_probe("run_dsh_probe.py", U4, pilot, "m35", outp, "S4_dsh_pilot", OFF_OVERLAY, extra=["--tune", "m35"]) != 0: fail("dsh pilot rc")
    p, st = probe_summary(outp, "S4_dsh_pilot", {})
    log(f"PILOT SIZING dsh: {len(rs)+len(pilot)} rows so far; no abort on the pilot mean")
    if run_probe("run_dsh_probe.py", U4, rest, "m35", outp, "S4_dsh_rest", OFF_OVERLAY, extra=["--tune", "m35"]) != 0: fail("dsh rest rc")
    p, st = probe_summary(outp, "S4_dsh_full", {U4 + " opencode s1": f"{REPO}/benchmark/results/{U4}/opencode.jsonl", U4 + " opencode s2": f"{REPO}/benchmark/results/{U4}/opencode.s2.jsonl"})
    log(f"M35 READ: dsh {p}/22 stall-kills {st} vs opencode 20/22 (2) — pre-registered: dsh >= opencode with fewer stall-kills -> extend to the B 1st/2nd; else close with the number")
# ---------------------------------------------------------------- main
log("=== QUEUE RUNNER 2 START === (resumes S2b behind the orphaned hep driver, then S2c low, S3, S4)")
try:
    opid = int(open(f"{OUT}/S2b_mxmed_hep_full.pid").read().strip()); log(f"waiting on the orphaned S2b hep driver pid {opid}")
    while True:
        try: os.kill(opid, 0)
        except OSError: break
        time.sleep(30)
    log("orphaned driver exited")
except Exception as ex: log(f"WARN: no orphan pid to wait on ({ex})")
for p in sh(["pgrep", "-f", "bench_watch.py"]).stdout.split():
    try: os.kill(int(p), signal.SIGTERM); log(f"killed stray bench_watch {p}")
    except OSError: pass
time.sleep(5)
stage("S2b M24 medium (mixed checkpoint, operator 2026-09-06) [resumed]", s2b_m24_mixed)
stage("S2c low-effort hep legs (operator 2026-09-07)", s2c_low)
stage("S3 M34 OFAT", s3_m34_ofat)
stage("S4 M35 dsh", s4_m35_dsh)
log("=== QUEUE DONE === (box idle; next: M17 / D11 / M18 read / Nemotron ladder — operator)")
