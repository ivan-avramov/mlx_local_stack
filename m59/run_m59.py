"""M59 runner: `smoke` (pilot-twice, 5 seeded-random Python items on pick 1) and `chain` (P161 re-baseline:
s1/s2 order-balanced over the two B picks x python/go, plus the same-seed reload control).
Lean router on the draft-OFF overlay, MLX_VLM_CACHE_SESSION_MAX=1, M50/C106 inside the probe, A4-on-v2 gate per
router start, five-minute watcher, RUNLOG.md. Fail-loud; leg-resumable (a leg whose out file is complete is skipped).
Usage: run_m59.py smoke | chain [s1 s2 reload]      (detached: nohup ... & ; exit code preserved in run_m59.rc)
"""
import json, os, random, subprocess, sys, threading, time, urllib.request
from pathlib import Path

WD = Path(os.environ.get("STACK_WORKDIR") or (Path.home() / "ws/mlx_local_stack_workdir"))
REPO = Path(os.environ.get("STACK_REPO") or (Path.home() / "ws/mlx_local_stack"))
OUT = WD / "m59"
OVERLAY = Path(os.environ.get("M59_OVERLAY") or (OUT / "overlay_m59_draft_off.yaml"))
PY = REPO / ".venv-bench/bin/python"
PROBE = REPO / "benchmark/run_opencode_probe_v2.py"
GATE = REPO / "scripts/session_pinning_gate.py"
RECEIPT = WD / "session_gate/a4_v2_latest.json"
BASE = "http://localhost:8000"
PICK1 = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
PICK2 = "Qwen3.8-27B-mlx-uniform-4bit"
ITEMS = json.loads((OUT / "items_python_go.json").read_text())        # the 22-item python/go sets of the 1.18 rows
SMOKE_ITEMS = random.Random(20261006).sample(sorted(ITEMS["python"]), 5)
SEEDS = {"s1": 1001, "s2": 2002, "reload": 1001}
LEGS = {"s1": [(PICK1, "python"), (PICK1, "go"), (PICK2, "python"), (PICK2, "go")],
        "s2": [(PICK2, "python"), (PICK2, "go"), (PICK1, "python"), (PICK1, "go")],
        "reload": [(PICK1, "python")]}
PRED_S = {("python", PICK1): 244, ("go", PICK1): 300, ("python", PICK2): 267, ("go", PICK2): 360}   # RCA 2026-10-07: 1.18-medium means x 1.08 (v2/1.18 ratio); the smoke draw is heavy, so early running means read high
BUSY = ("mlx_vlm.server", "mlx_vlm/server", "mlx-serve start", "session_cache_probe", "opencode run",
        "run.py generate", "run_opencode_probe", "run_agentbench_os", "runserver.sh")
LEG_TIMEOUT_S = 6 * 3600


def log(msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
    print(line, flush=True)
    with (OUT / "RUNLOG.md").open("a") as f:
        f.write("- " + line + "\n")


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, **kw)


def env_base():
    env = {k: v for k, v in os.environ.items() if k != "APC_ENABLED"}
    dotenv = REPO / ".env"
    if dotenv.is_file():
        for line in dotenv.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.replace("export ", "").strip()] = v.strip().strip('"').strip("'")
    env.pop("APC_ENABLED", None)
    env["STACK_WORKDIR"] = str(WD)
    env["MLX_SERVE_CONFIG"] = str(OVERLAY)
    env["MLX_VLM_CACHE_SESSION_MAX"] = "1"
    env["MLX_VLM_LOG_FILE"] = "logs/mlx_vlm.log"       # as runserver.sh: the worker's request log (A4 instrument)
    env["MLX_VLM_LOG_LEVEL"] = "INFO"
    env["TMPDIR"] = str(OUT / "tmp")
    (OUT / "tmp").mkdir(parents=True, exist_ok=True)
    return env


def power_ok():
    w = sh("pmset -g ac | awk '/Wattage/{print $3}'", shell=True).stdout.strip()
    b = sh("pmset -g batt | grep -oE '[0-9]+%' | head -1", shell=True).stdout.strip().rstrip("%")
    o = sh([str(REPO / "scripts/sweep_orphan_shells.sh")]).stdout
    ok = (w == "140W") and (int(b or 0) >= 20) and ("no orphaned" in o)
    log(f"GATE adapter={w} batt={b}% orphans={'0' if 'no orphaned' in o else 'PRESENT'} -> {'ok' if ok else 'FAIL'}")
    return ok


def listeners():
    out = sh(["lsof", "-nP", "-iTCP:8000", "-sTCP:LISTEN", "-Fp"]).stdout
    return sorted({int(l[1:]) for l in out.splitlines() if l.startswith("p")})


def busy_procs():
    out = sh(["ps", "-axo", "pid=,command="]).stdout
    me = os.getpid()
    return [l.strip() for l in out.splitlines()
            if any(p in l for p in BUSY) and int(l.split()[0]) != me and "run_m59.py" not in l]


def proc_env(pid):
    return sh(["ps", "-o", "command=", "-E", "-p", str(pid)]).stdout


def start_router():
    if listeners():
        raise SystemExit(f"REFUSED: :8000 already bound by {listeners()}")
    if busy_procs():
        raise SystemExit("REFUSED: busy processes present: " + "; ".join(busy_procs())[:600])
    env = env_base()
    cmd = ["uv", "run", "--frozen", "--no-sync", "mlx-serve", "start"]
    log(f"RUN router: MLX_VLM_CACHE_SESSION_MAX=1 MLX_SERVE_CONFIG={OVERLAY} {' '.join(cmd)} (cwd={REPO})")
    (REPO / "logs").mkdir(exist_ok=True)
    subprocess.Popen(cmd, cwd=str(REPO), env=env, stdout=open(REPO / "logs/main_model.log", "a"),
                     stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(120):
        if listeners():
            break
        time.sleep(2)
    ls = listeners()
    if len(ls) != 1:
        raise SystemExit(f"TRIPWIRE: expected one :8000 listener, found {ls}")
    pid = ls[0]
    e = proc_env(pid)
    probs = [p for p, cond in (("not mlx-serve", "mlx-serve" not in e),
                               ("MLX_SERVE_CONFIG", f"MLX_SERVE_CONFIG={OVERLAY}" not in e),
                               ("SESSION_MAX", "MLX_VLM_CACHE_SESSION_MAX=1" not in e),
                               ("APC_ENABLED present", "APC_ENABLED" in e)) if cond]
    cwd = sh(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"]).stdout
    if str(REPO) not in cwd:
        probs.append("cwd not the stack repo")
    log(f"router pid={pid} owns :8000; problems={probs or 'none'}")
    if probs:
        raise SystemExit("TRIPWIRE: router ownership/environment: " + "; ".join(probs))
    return pid


def http(path, body=None, timeout=900):
    req = urllib.request.Request(BASE + path, method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout).read()


def worker_cmdlines(model):
    out = sh(["ps", "-axo", "pid=,command="]).stdout
    return [l for l in out.splitlines() if "mlx_vlm.server" in l and model in l and "uv run" not in l]


def load(model):
    log(f"RUN load {model}")
    http("/v1/models/load", {"model": model, "keep_alive": "240m"})
    for _ in range(60):
        w = worker_cmdlines(model)
        if w:
            break
        time.sleep(5)
    w = worker_cmdlines(model)
    if len(w) != 1:
        raise SystemExit(f"TRIPWIRE: expected one worker for {model}, found {len(w)}")
    if "--draft-kind" in w[0] and "--draft-kind none" not in w[0] and "--draft-kind off" not in w[0]:
        raise SystemExit(f"TRIPWIRE: worker carries a predictor: {w[0][:300]}")
    log(f"worker cmdline: {w[0][:400]}")


def unload(model):
    try:
        http("/v1/models/unload", {"model": model}, timeout=120)
        log(f"unload {model} ok")
    except Exception as e:  # noqa: BLE001
        log(f"unload {model}: {e}")
    for _ in range(120):
        if not worker_cmdlines(model):
            return True
        time.sleep(5)
    log("FATAL worker still alive after unload")
    return False


def a4_gate(model, tag):
    env = env_base()
    logf = OUT / f"a4_{tag}.log"
    log(f"RUN A4 v2 gate ({model}) -> {logf.name}")
    with logf.open("w") as lf:
        rc = subprocess.run([str(PY), str(GATE), "--model", model, "--opencode", "v2", "--skip-owui",
                             "--log", str(REPO / "logs/mlx_vlm.log")], cwd=str(REPO), env=env,
                            stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=1800).returncode
    rec = json.loads(RECEIPT.read_text()) if RECEIPT.exists() else {}
    log(f"A4 v2 rc={rc} pass={rec.get('pass')} router_pid={rec.get('router_pid')} run_id={rec.get('run_id')}")
    if rec.get("pass") is not True:
        raise SystemExit(f"A4 v2 gate FAILED (rc={rc}) -- stop")
    if rc != 0:
        log(f"NOTE gate rc={rc} with A4 PASS (A6/other leg failed?) -- see {logf.name}")


def rows(p):
    try:
        return [json.loads(l) for l in open(p) if l.strip()]
    except FileNotFoundError:
        return []


def watcher(out, total, pred_s, stop):
    t0 = time.time()
    while not stop.wait(300):
        r = rows(out)
        n = len(r)
        done_s = sum(x.get("wall_s", 0) for x in r)
        mean = done_s / n if n else pred_s
        eta = (total - n) * mean / 60
        w = sh("pmset -g ac | awk '/Wattage/{print $3}'", shell=True).stdout.strip()
        b = sh("pmset -g batt | grep -oE '[0-9]+%' | head -1", shell=True).stdout.strip()
        kinds = {}
        for x in r:
            k = x.get("nonconv_kind") or ("ok" if x.get("stop_reason") == "completed" else x.get("stop_reason"))
            kinds[k] = kinds.get(k, 0) + 1
        log(f"WATCH {Path(out).name}: {n}/{total} rows passed={sum(bool(x.get('passed')) for x in r)} "
            f"mean={mean:.0f}s pred={pred_s}s eta={eta:.0f}min elapsed={(time.time()-t0)/60:.0f}min kinds={kinds} "
            f"adapter={w} batt={b}")


def run_leg(model, lang, items, seed_base, out, *, limit=None, chain_total=0, receipt=True, extra_args=()):
    out = Path(out)
    total = limit or len(items)
    if len(rows(out)) >= total:
        log(f"SKIP {out.name} (complete)")
        return
    if not power_ok():
        raise SystemExit("gate FAIL -- ABORT")
    env = env_base()
    cmd = [str(PY), str(PROBE), "--model", model, "--items", ",".join(items), "--lang", lang,
           "--seed-base", str(seed_base), "--out", str(out), "--chain-total", str(chain_total)]
    if limit:
        cmd += ["--limit", str(limit)]
    cmd += list(extra_args)
    if receipt and RECEIPT.exists():
        cmd += ["--a4-v2-receipt", str(RECEIPT)]
    log(f"START {out.name}: {' '.join(cmd[2:])}")
    leg_start_local = time.strftime("%Y-%m-%d %H:%M:%S")
    stop = threading.Event()
    th = threading.Thread(target=watcher, args=(out, total, PRED_S.get((lang, model), 250), stop), daemon=True)
    th.start()
    with (out.with_suffix(".log")).open("a") as lf:
        try:
            rc = subprocess.run(cmd, cwd=str(REPO), env=env, stdout=lf, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, timeout=LEG_TIMEOUT_S).returncode
        except subprocess.TimeoutExpired:
            stop.set()
            log(f"TIMEOUT {out.name} at {LEG_TIMEOUT_S} s -- ABORT")
            raise SystemExit(2)
    stop.set()
    r = rows(out)
    log(f"END {out.name} rc={rc} rows={len(r)} passed={sum(bool(x.get('passed')) for x in r)} "
        f"mean_wall={sum(x.get('wall_s', 0) for x in r) / max(1, len(r)):.0f}s "
        f"requests={[x.get('requests_observed') for x in r]}")
    leg_rate_check(model, leg_start_local, time.strftime("%Y-%m-%d %H:%M:%S"))
    if rc != 0:
        log("FATAL leg rc != 0 -- ABORT")
        raise SystemExit(1)


def leg_rate_check(model, start_local, end_local):
    """Median worker-log decode rate (requests >= 500 generated tokens) during the leg vs the table in
    benchmark/decode_rates.json; logs a FLAG when the gap exceeds 5% (C136 windows assume the table)."""
    import re as _re, statistics as _st
    try:
        table = json.loads((REPO / "benchmark/decode_rates.json").read_text())["models"][model]["tok_s"]
        lines = (REPO / "logs/mlx_vlm.log").read_text(errors="replace").splitlines()
    except Exception as e:  # noqa: BLE001
        log(f"RATE CHECK {model}: unavailable ({type(e).__name__}: {e})")
        return
    tag = model.split("-", 2)[-1]
    rates = []
    for l in lines:
        if not (start_local <= l[:19] <= end_local) or "Request completed" not in l or tag not in l:
            continue
        d = _re.search(r"decode=([\d.]+)", l); g = _re.search(r"generated_tokens=(\d+)", l)
        if d and g and int(g.group(1)) >= 500:
            rates.append(float(d.group(1)))
    if not rates:
        log(f"RATE CHECK {model}: no qualifying requests")
        return
    med = _st.median(rates); gap = (med - table) / table * 100
    log(f"RATE CHECK {model}: measured median {med:.1f} tok/s (n={len(rates)}) vs table {table} -> {gap:+.1f}%"
        + (" FLAG >5%: the C136 window is miscalibrated for this leg" if abs(gap) > 5 else " ok"))


def stop_stack():
    rc = subprocess.run([str(REPO / "scripts/stack_stop.sh")], stdin=subprocess.DEVNULL).returncode
    log(f"stack_stop rc={rc} listeners={listeners()}")


def smoke():
    log(f"START smoke items={SMOKE_ITEMS} seed_base={SEEDS['s1']} overlay={OVERLAY}")
    start_router()
    try:
        load(PICK1)
        a4_gate(PICK1, "smoke")
        for tag in ("p1", "p2"):
            run_leg(PICK1, "python", SMOKE_ITEMS, SEEDS["s1"], OUT / "smoke" / f"{PICK1}.python.{tag}.jsonl", limit=5)
        p1 = {x["id"]: x for x in rows(OUT / "smoke" / f"{PICK1}.python.p1.jsonl")}
        p2 = {x["id"]: x for x in rows(OUT / "smoke" / f"{PICK1}.python.p2.jsonl")}
        diff = [(i, p1[i].get("passed"), p2[i].get("passed"), p1[i]["traffic"].get("output_tokens"),
                 p2[i]["traffic"].get("output_tokens")) for i in p1
                if (p1[i].get("passed"), p1[i]["traffic"].get("output_tokens"))
                != (p2[i].get("passed"), p2[i]["traffic"].get("output_tokens"))]
        dates = {x.get("prompt_date") for x in list(p1.values()) + list(p2.values())}
        if len(dates) > 1:
            log(f"PILOT-TWICE DATE MISMATCH {sorted(dates)}: identity not claimable across local dates (C135)")
        log(f"PILOT-TWICE identical={not diff and len(dates) == 1} differences={diff}")
        subprocess.run([str(PY), str(OUT / "prompt_identity.py"), str(OUT / "smoke" / f"{PICK1}.python.p1.jsonl"),
                        str(OUT / "smoke" / f"{PICK1}.python.p2.jsonl"), str(REPO / "logs/mlx_vlm.log")],
                       stdout=open(OUT / "smoke" / "prompt_identity.txt", "w"), stderr=subprocess.STDOUT)
        log("PROMPT-IDENTITY: " + (OUT / "smoke" / "prompt_identity.txt").read_text().strip().splitlines()[-1])
        unload(PICK1)
    finally:
        stop_stack()
    log("SMOKE DONE")


def chain(sessions):
    log(f"START chain sessions={sessions} overlay={OVERLAY}")
    start_router()
    try:
        prev = None
        for s in sessions:
            (OUT / s).mkdir(parents=True, exist_ok=True)
            if prev is not None:            # every session is an INDEPENDENT loaded instance (AGENTS.md k=2 rule)
                if not unload(prev):
                    raise SystemExit(3)
                prev = None
                log(f"session boundary -> fresh load for {s}")
            def out_for(model, lang):
                # s1 keeps its original names (pick-1 rows exist); later sessions are tagged so their
                # transcripts (keyed by the out stem) never overwrite s1's
                return OUT / s / (f"{model}.opencode_{lang}.jsonl" if s == "s1" else f"{model}.{s}.opencode_{lang}.jsonl")
            for model, lang in LEGS[s]:
                if all(len(rows(out_for(m, l))) >= len(ITEMS[l]) for m, l in LEGS[s] if m == model):
                    log(f"SKIP {s} {model}: all legs complete")
                    continue
                if prev != model:
                    if prev is not None and not unload(prev):
                        raise SystemExit(3)
                    load(model)
                    a4_gate(model, f"{s}_{model}")
                    prev = model
                out = out_for(model, lang)
                # chain pilot: the first 5 items of the loaded instance's first leg must land clean
                if lang == LEGS[s][0][1] and not rows(out):
                    run_leg(model, lang, random.Random(SEEDS[s]).sample(sorted(ITEMS[lang]), 5), SEEDS[s], out, limit=5, chain_total=88)
                run_leg(model, lang, ITEMS[lang], SEEDS[s], out, chain_total=88)
        if prev:
            unload(prev)
    finally:
        stop_stack()
    log("ALL LEGS DONE")


STALLPROBE_TOKENS = 48000   # P182: 3x the C136 allowance; still under the 3600 s hard ceiling at both picks' rates


def chain_out(s, model, lang):
    return OUT / s / (f"{model}.opencode_{lang}.jsonl" if s == "s1" else f"{model}.{s}.opencode_{lang}.jsonl")


def stallprobe():
    """P182: re-run every chain item scored `stalled` with a 48K-token first-write allowance, SAME item seed as its
    session, one fresh loaded instance per model; outputs under stallprobe/, descriptive only, never pooled."""
    groups = {}
    for s in ("s1", "s2"):
        for model, lang in LEGS[s]:
            stalled = [r["id"].split("/", 1)[1] for r in rows(chain_out(s, model, lang)) if r.get("nonconv_kind") == "stalled"]
            if stalled:
                groups.setdefault(model, []).append((s, lang, stalled))
    log(f"START stallprobe tokens={STALLPROBE_TOKENS} groups={ {m: [(s, l, len(i)) for s, l, i in g] for m, g in groups.items()} }")
    if not groups:
        log("stallprobe: no stalled items")
        return
    (OUT / "stallprobe").mkdir(exist_ok=True)
    start_router()
    try:
        prev = None
        for model, legs in groups.items():
            if prev is not None and not unload(prev):
                raise SystemExit(3)
            load(model)
            a4_gate(model, f"stallprobe_{model}")
            prev = model
            for s, lang, items in legs:
                run_leg(model, lang, items, SEEDS[s], OUT / "stallprobe" / f"{model}.{s}.opencode_{lang}.jsonl",
                        chain_total=88, extra_args=("--first-write-tokens", str(STALLPROBE_TOKENS)))
        if prev:
            unload(prev)
    finally:
        stop_stack()
    log("STALLPROBE DONE")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "smoke").mkdir(exist_ok=True)
    mode = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    if mode == "smoke":
        smoke()
    elif mode == "stallprobe":
        stallprobe()
    elif mode == "chain":
        chain(sys.argv[2:] or ["s1", "s2"])   # reload control dropped (C135)
    else:
        raise SystemExit(f"unknown mode {mode}")
