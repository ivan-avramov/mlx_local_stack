"""M41 chain runner: capacity + retrieval-depth + reasoning-depth ladders for pick
Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed, predictor-ON (registry draft_kind: mtp,
M40-certified). Spec: $STACK_WORKDIR/queue/m41_ladders/SPEC.md. Patterns copied
verbatim (per spec) from queue/m40_mtp/run.py: router_start/router_stop,
worker_cmdline_for_check, _force_load, draft_counter_probe, run_depth's
heartbeat/bound/provenance block, idle_precheck, parse_args --dry-run/--from-step,
logging grammar.

helpers.py is the M40 helpers module with ONE edit: OUT points at this directory
(queue/m41_ladders), so queue.log, per-tag .log/.pid and the lock/pid pair land here.
Benchmark outputs are written under $STACK_REPO/benchmark/results/<model>/ via absolute
paths built from R.
"""
import argparse, fcntl, json, os, re, signal, subprocess, threading, time
from pathlib import Path
import helpers as h

R = Path(os.environ['STACK_REPO'])
Q = Path(os.environ['STACK_WORKDIR']) / 'queue'
D = Q / 'm41_ladders'                    # this directory (holds SPEC.md, the overlay, README.md)
OUT = h.OUT                              # queue/m41_ladders (helpers.OUT, edited from the M40 copy)
RESULTS = R / 'benchmark/results'

PICK = 'Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed'
OVERLAY = D / f'on_{PICK}.yaml'
TUNE = 'm41on'
PROFILE = 'deployed'
BOUND_H = {'capacity': 2, 'retrieval': 5, 'reasoning': 10}
STEPS = ['capacity', 'retrieval', 'reasoning']

OUT_JSON = {
    'capacity': RESULTS / PICK / f'capacity_retrieval.{TUNE}.json',
    'retrieval': RESULTS / PICK / f'retrieval.{TUNE}.json',
    'reasoning': RESULTS / PICK / f'reasoning.{TUNE}.json',
}
PROV_JSON = {
    'capacity': RESULTS / PICK / f'capacity_retrieval.{TUNE}.provenance.json',
    'retrieval': RESULTS / PICK / f'retrieval.{TUNE}.provenance.json',
    'reasoning': RESULTS / PICK / f'reasoning.{TUNE}.provenance.json',
}
# R9 (SPEC_FIX1): the bench-tooling-written manifest per ladder (C35 tripwire), distinct from
# PROV_JSON above (this runner's own chain provenance).
MANIFEST_JSON = {
    'capacity': RESULTS / PICK / f'capacity_ladder.{TUNE}.manifest.json',
    'retrieval': RESULTS / PICK / f'retrieval.{TUNE}.manifest.json',
    'reasoning': RESULTS / PICK / f'reasoning.{TUNE}.manifest.json',
}
# R4 (SPEC_FIX1): the flag precheck now runs under --dry-run too (no server needed for --help),
# so this list is checked on EVERY invocation, dry or real. capacity's --request-timeout is added
# per R2 (7200 s, threaded to capacity_ladder.run_ladder's OOM/disconnect catch).
CLI_FLAGS = {
    'capacity': ['--sampling-profile', '--out-tag', '--request-timeout'],
    'retrieval': ['--sampling-profile', '--out-tag', '--request-timeout'],
    'reasoning': ['--sampling-profile', '--out-tag', '--request-timeout', '--deep-from', '--deep-samples'],
}
MODULE = {'capacity': 'bench.run_capacity', 'retrieval': 'bench.run_retrieval', 'reasoning': 'bench.run_reasoning'}
# R1 (SPEC_FIX1): the driver-log substring the heartbeat greps for the LAST matching line, per step.
PROGRESS_MARK = {'capacity': '[capacity] rung', 'retrieval': '[retrieval] ctx=', 'reasoning': '[reasoning] ctx='}
# R8 (SPEC_FIX1): the live driver Popen, if any, so a SIGTERM/SIGINT handler can kill+wait it.
_current_driver = None

_router_owned = False
_router_pid = None


# --------------------------------------------------------------------------- precheck helpers
def idle_precheck():
    p = h.sh(['pgrep', '-f', '[r]un.py generate|[m]lx_vlm.server|[m]lx-serve|[b]ench.run_'])
    if p.stdout.strip() or h.listeners():
        h.fail('Expected idle driver/worker/router before starting M41 (run.py generate, '
              'mlx_vlm.server, mlx-serve, bench.run_*, or a listener on :8000 is present)')
    h.log('idle precheck OK: no generate driver, no mlx_vlm.server, no mlx-serve, no bench.run_* '
         'driver, 0 listeners on :8000')


def check_cli_flags(step, dry_run):
    """FATAL naming the missing flag if a required flag is absent from `<module> --help`.
    R4 (SPEC_FIX1): runs under --dry-run too -- `<python> -m <module> --help` needs no server
    and no GPU work, so this precheck happens even when --dry-run never starts the router or
    launches a ladder for real."""
    module = MODULE[step]
    env = dict(os.environ)
    env['PYTHONPATH'] = str(R / 'benchmark')
    p = h.sh([h.PY, '-m', module, '--help'], cwd=str(R / 'benchmark'), env=env)
    text = (p.stdout or '') + (p.stderr or '')
    missing = [f for f in CLI_FLAGS[step] if f not in text]
    if missing:
        h.fail(f'{module} --help is missing required flag(s) {missing} -- tooling not ready yet '
              f'(see TOOLING.md); refusing to launch {step}')
    h.log(f'PRECHECK {module} --help OK: {CLI_FLAGS[step]} all present')


def system_used_gb():
    """Best-effort quiet-box record via the SAME instrument the bench modules use
    (bench.instrument.system_used_gb) -- never FATAL on this; it is a diagnostic, not a gate."""
    env = dict(os.environ)
    env['PYTHONPATH'] = str(R / 'benchmark')
    p = h.sh([h.PY, '-c', 'from bench.instrument import system_used_gb; print(system_used_gb())'],
            cwd=str(R / 'benchmark'), env=env)
    try:
        return round(float(p.stdout.strip()), 2)
    except Exception:
        h.log(f'WARN system_used_gb probe failed rc={p.returncode} stdout={p.stdout!r} stderr={p.stderr!r}')
        return None


# --------------------------------------------------------------------------- copied verbatim from m40_mtp/run.py
def _force_load(pick, timeout=900):
    import urllib.request
    body = json.dumps({'model': pick}).encode()
    req = urllib.request.Request('http://localhost:8000/v1/models/load', method='POST', data=body,
                                 headers={'Content-Type': 'application/json'})
    urllib.request.urlopen(req, timeout=timeout).read()


def worker_cmdline_for_check(pick, tag):
    """mlx-serve loads lazily: right after ensure_router(), worker_cmdline() == '' until the first
    request. Force a load via POST /v1/models/load first, then re-read; if it's still empty, FATAL
    rather than certify off an unverified state."""
    c = h.worker_cmdline()
    if not c:
        h.log(f'{tag}: worker not yet loaded (lazy load); forcing via POST /v1/models/load '
             f'{{"model": "{pick}"}}')
        try:
            _force_load(pick)
        except Exception as ex:
            h.fail(f'{tag}: force-load of {pick} failed: {ex!r}')
        for _ in range(120):
            c = h.worker_cmdline()
            if c:
                break
            time.sleep(2)
    if not c:
        h.fail(f'{tag}: worker cmdline still empty after forced load of {pick} -- cannot verify draft state')
    return c


def draft_counter_probe():
    """Best-effort read of a router-side cumulative draft/speculative-decode counter, for the
    provenance json. Verified against source (M40 cold review D11): mlx-serve's own /metrics
    carries no draft_n/draft_n_accepted field at all; mlx_vlm's per-worker /metrics does, but it
    lives on the worker's own port (not the router's :8000) and is gated by a management API key
    we do not provision. So there is currently no reachable CUMULATIVE draft counter -- this
    always returns None; callers log a WARN and record "draft_counters": null so the analysis
    knows certification of that ladder rests on the worker cmdline --draft-kind check alone."""
    return None


# --------------------------------------------------------------------------- router (one session for all three ladders)
def router_start(dry_run):
    global _router_owned, _router_pid
    if dry_run:
        h.log(f'PLAN router: ensure_router({OVERLAY.name}) -- sets MLX_VLM_CACHE_SESSION_MAX=2 and '
             f'APC_ENABLED absent (verified on the router pid via ps -Eww after start, per '
             f'helpers.start_router) -- not launched (--dry-run)')
        return
    _router_owned = True  # set BEFORE ensure_router: a router we Popen but fail to validate must still be stopped on FATAL
    h.ensure_router(str(OVERLAY))
    _router_pid = h.listeners()[0] if h.listeners() else None
    e = h.sh(['ps', '-Eww', '-o', 'command=', '-p', str(_router_pid)]).stdout if _router_pid else ''
    h.log(f'router pid={_router_pid} overlay={OVERLAY.name} '
         f'MLX_VLM_CACHE_SESSION_MAX=2 present={"MLX_VLM_CACHE_SESSION_MAX=2" in e} '
         f'APC_ENABLED absent={"APC_ENABLED" not in e}')


def router_stop(dry_run):
    global _router_owned
    if dry_run:
        h.log('PLAN router: unload(); stop_router() -- not launched (--dry-run)')
        return
    h.unload()
    h.stop_router()
    if h.listeners():
        raise RuntimeError('router still listening on :8000 after stop')
    _router_owned = False


def _last_progress_line(logpath, mark):
    """R1 (SPEC_FIX1): the LAST line in the driver log containing `mark`
    ("[capacity] rung"/"[retrieval] ctx="/"[reasoning] ctx="), or "none"."""
    if not logpath.exists():
        return 'none'
    try:
        text = logpath.read_text(errors='replace')
    except OSError:
        return 'none'
    hits = [ln for ln in text.splitlines() if mark in ln]
    return hits[-1] if hits else 'none'


# --------------------------------------------------------------------------- generic ladder launch/bound/heartbeat
def _launch_and_wait(tag, cmd, bound_h, dry_run, step):
    """Common Popen/bound/heartbeat/draft-check mechanics (copied pattern from m40_mtp/run.py's
    run_depth). Returns a dict of provenance fields on success; raises via h.fail on any failure."""
    global _current_driver
    h.log(f'RUN {tag}: ' + ' '.join(cmd) +
         f' (cwd={R / "benchmark"}, env MLX_SERVE_CONFIG={OVERLAY} PYTHONPATH={R / "benchmark"} '
         f'APC_ENABLED absent)')
    h.log(f'overlay {OVERLAY.name} sha256={h.sha(str(OVERLAY))}')
    if dry_run:
        h.log(f'PLAN {tag}: worker cmdline check (force-load if empty; expect --draft-kind mtp '
             f'present); 5-min heartbeat thread (driver_log_bytes/driver_log_age_s/progress='
             f'last "{PROGRESS_MARK[step]}" line/worker_cmdline_present/driver_alive; WARN if '
             f'driver_log_age_s>5400 -- never kill on it); bound_h={bound_h}; '
             f'draft_counter_probe() before/after -- not launched (--dry-run)')
        return None

    c = worker_cmdline_for_check(PICK, tag)
    has_mtp = bool(re.search(r'--draft-kind\s+mtp\b', c))
    h.log(f"worker cmdline: draft_kind_mtp={has_mtp} :: {c[-160:]}")
    if not has_mtp:
        h.fail(f'{tag}: worker cmdline missing --draft-kind mtp -- predictor-ON not verified :: {c[-200:]}')

    draft_before = draft_counter_probe()
    env = dict(os.environ)
    env.pop('APC_ENABLED', None)
    env['MLX_SERVE_CONFIG'] = str(OVERLAY)
    env['PYTHONPATH'] = str(R / 'benchmark')
    started = time.strftime('%Y-%m-%dT%H:%M:%S')
    started_epoch = time.time()
    logp = Path(f'{OUT}/{tag}.log')
    d = subprocess.Popen(cmd, cwd=str(R / 'benchmark'), env=env, stdout=open(logp, 'a'),
                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    _current_driver = d  # R8: so a SIGTERM/SIGINT handler can kill+wait the live driver
    Path(f'{OUT}/{tag}.pid').write_text(str(d.pid))
    stop_evt = threading.Event()

    def hb():
        while not stop_evt.wait(300):
            size = logp.stat().st_size if logp.exists() else 0
            age = round(time.time() - logp.stat().st_mtime, 1) if logp.exists() else None
            progress = _last_progress_line(logp, PROGRESS_MARK[step])
            h.log(f'HEARTBEAT {tag}: driver_log_bytes={size} driver_log_age_s={age} '
                 f'progress={progress} worker_cmdline_present={bool(h.worker_cmdline())} '
                 f'driver_alive={d.poll() is None}')
            if age is not None and age > 5400:
                h.log(f'WARN {tag}: no driver output for {age} s (a 262K prefill or a runaway '
                     f'may legitimately take this long; check GPU util before acting)')
    threading.Thread(target=hb, daemon=True).start()

    t0 = time.time()
    rc = None
    while rc is None:
        rc = d.poll()
        if time.time() - t0 > bound_h * 3600:
            d.kill()
            d.wait()
            stop_evt.set()
            _current_driver = None
            h.log(f'TIMEOUT {tag} after {bound_h} h')
            h.fail(f'TIMEOUT {tag} after {bound_h} h (state preserved)')
        time.sleep(5)
    stop_evt.set()
    _current_driver = None
    h.log(f'END {tag} rc={rc}')
    if rc:
        resumable = (' -- reasoning ladder is resumable: re-run bench.run_reasoning with --resume '
                    f'(reads reasoning.{TUNE}.partial.jsonl)') if tag == 'reasoning' else ''
        h.fail(f'{tag} failed rc={rc}{resumable}')

    finished = time.strftime('%Y-%m-%dT%H:%M:%S')
    draft_after = draft_counter_probe()
    if draft_before is None and draft_after is None:
        h.log(f'WARN {tag}: no reachable draft/speculative-decode counter (see draft_counter_probe '
             f'docstring) -- certification of this ladder rests on the worker cmdline --draft-kind '
             f'mtp check alone')
    return {'worker_cmdline': c, 'draft_before': draft_before, 'draft_after': draft_after,
           'started': started, 'started_epoch': started_epoch, 'finished': finished}


def _redact_paths(obj):
    """R6 (SPEC_FIX1, PII): replace the literal values of $STACK_WORKDIR and then $STACK_REPO
    (in that order -- STACK_REPO is a PREFIX of STACK_WORKDIR on this box, so replacing it first
    would half-redact STACK_WORKDIR strings) with the placeholder strings $STACK_WORKDIR /
    $STACK_REPO, in every string field, recursively through dicts/lists."""
    wd = os.environ['STACK_WORKDIR']
    repo = os.environ['STACK_REPO']
    if isinstance(obj, str):
        s = obj.replace(wd, '$STACK_WORKDIR')
        s = s.replace(repo, '$STACK_REPO')
        return s
    if isinstance(obj, dict):
        return {k: _redact_paths(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_paths(v) for v in obj]
    return obj


def write_provenance(step, res, idle_gb=None):
    prov = {
        'model': PICK, 'tune': TUNE, 'step': step,
        'overlay': str(OVERLAY), 'overlay_sha256': h.sha(str(OVERLAY)),
        'worker_cmdline': res['worker_cmdline'],
        'router_pid': _router_pid,
        'started': res['started'], 'finished': res['finished'],
        'draft_counters': {'before': res['draft_before'], 'after': res['draft_after']},
        'idle_system_used_gb': idle_gb,
    }
    prov = _redact_paths(prov)
    PROV_JSON[step].parent.mkdir(parents=True, exist_ok=True)
    PROV_JSON[step].write_text(json.dumps(prov, indent=2))
    h.log(f'PROVENANCE {step}: wrote {PROV_JSON[step]}')


def assert_manifest(step, tag, started_epoch=None):
    """R9 (SPEC_FIX1) + re-review defect 3: after each ladder the bench-tooling-written manifest must
    exist, be FRESH (mtime >= this ladder's start), and carry the C35 facts: registry.sha256 == the
    overlay sha and runtime.draft_kind == 'mtp'. Anything else -> FATAL; the rows are UNGRADED."""
    m = MANIFEST_JSON[step]
    if not m.is_file():
        h.fail(f'{tag}: provenance manifest missing (C35 tripwire or gather failure — rows are '
              f'UNGRADED until provenance is established)')
    if started_epoch is not None and m.stat().st_mtime < started_epoch - 5:
        h.fail(f'{tag}: provenance manifest is STALE (mtime before this ladder started) — a previous '
              f'attempt left it; rows are UNGRADED until provenance is established')
    try:
        man = json.loads(m.read_text())
    except Exception as e:  # noqa: BLE001
        h.fail(f'{tag}: provenance manifest unreadable ({e!r})')
    reg_sha = (man.get('registry') or {}).get('sha256')
    dk = (man.get('runtime') or {}).get('draft_kind')
    want = h.sha(str(OVERLAY))
    if reg_sha != want or dk != 'mtp':
        h.fail(f'{tag}: C35 MISMATCH in manifest: registry.sha256={reg_sha} (overlay {want}) '
              f'runtime.draft_kind={dk!r} (expect mtp) — rows are UNGRADED')
    h.log(f'MANIFEST {step}: present, fresh, registry.sha256 match, draft_kind=mtp ({m})')


# --------------------------------------------------------------------------- capacity (gate; CONTINUES on GATE-FAIL)
def do_capacity(dry_run):
    tag = 'm41_capacity'
    check_cli_flags('capacity', dry_run)
    idle_gb = None
    if not dry_run:
        idle_gb = system_used_gb()
        h.log(f'PRECHECK capacity idle_system_used_gb={idle_gb} (quiet-box record)')
    else:
        h.log('PLAN capacity: idle_precheck + system-used GB (quiet-box record) -- not launched (--dry-run)')
    cmd = [h.PY, '-m', 'bench.run_capacity', '--model', PICK,
          '--grid', '131072,196608,262144', '--gate-gb', '46',
          '--sampling-profile', PROFILE, '--out-tag', TUNE, '--request-timeout', '7200']

    res = _launch_and_wait(tag, cmd, BOUND_H['capacity'], dry_run, 'capacity')
    if dry_run:
        return
    data = json.loads(OUT_JSON['capacity'].read_text())
    max_ctx = data.get('max_fitting_ctx')
    gate_pass = data.get('capacity_gate_pass')
    records = data.get('records', [])
    peaks = [(r.get('ctx'), r.get('server_peak_gb'), r.get('fits'), r.get('prefill_s'),
             r.get('decode_tps'), r.get('acceptance'), r.get('error_kind'), r.get('error'))
            for r in records]
    h.log(f'RESULT capacity {TUNE} max_fitting_ctx={max_ctx} capacity_gate_pass={gate_pass} peaks={peaks}')
    # R2 (SPEC_FIX1): a transport/OOM error at a rung is NOT the same finding as a real capacity
    # gate failure -- log both, but GATE-FAIL only fires on a record that truly does not fit.
    for r in records:
        if r.get('error'):
            h.log(f"TRANSPORT-OR-OOM capacity ctx={r.get('ctx')} kind={r.get('error_kind')} err={r.get('error')}")
    for r in records:
        if r.get('server_peak_gb') is None and not r.get('error'):
            h.log(f"WARN capacity ctx={r.get('ctx')}: server_peak_gb missing (no peak telemetry) — not a gate verdict")
    if any(r.get('fits') is False and not r.get('error') and r.get('server_peak_gb') is not None for r in records):
        h.log('GATE-FAIL capacity')
    assert_manifest('capacity', tag, started_epoch=res.get('started_epoch'))
    write_provenance('capacity', res, idle_gb=idle_gb)


# --------------------------------------------------------------------------- retrieval depth
def do_retrieval(dry_run):
    tag = 'm41_retrieval'
    check_cli_flags('retrieval', dry_run)
    cmd = [h.PY, '-m', 'bench.run_retrieval', '--model', PICK,
          '--grid', '8000,32000,64000,96000,128000', '--samples', '5', '--threshold', '0.85',
          '--sampling-profile', PROFILE, '--out-tag', TUNE, '--request-timeout', '9600']

    res = _launch_and_wait(tag, cmd, BOUND_H['retrieval'], dry_run, 'retrieval')
    if dry_run:
        return
    data = json.loads(OUT_JSON['retrieval'].read_text())
    eff_ctx = data.get('retrieval_effective_ctx')
    rungs = [(r.get('ctx'), r.get('accuracy'), r.get('errors'), r.get('decode_tps_mean'),
             r.get('prefill_s_mean'), r.get('acceptance_pooled')) for r in data.get('records', [])]
    h.log(f'RESULT retrieval {TUNE} retrieval_effective_ctx={eff_ctx} rungs={rungs}')
    assert_manifest('retrieval', tag, started_epoch=res.get('started_epoch'))
    write_provenance('retrieval', res)


# --------------------------------------------------------------------------- reasoning depth (M11 design)
def do_reasoning(dry_run):
    tag = 'm41_reasoning'
    check_cli_flags('reasoning', dry_run)
    cmd = [h.PY, '-m', 'bench.run_reasoning', '--model', PICK,
          '--grid', '8000,16000,24000,32000,48000,64000,96000,128000,156000', '--samples', '5',
          '--deep-from', '96000', '--deep-samples', '3', '--chain-len', '4', '--threshold', '0.85',
          '--sampling-profile', PROFILE, '--out-tag', TUNE, '--request-timeout', '9600']
    # R7 (SPEC_FIX1): whether this call is the first attempt, a --from-step reasoning restart, or
    # a FATAL-then-restart, the presence of the partial file on disk is what decides --resume --
    # not which CLI path got us here.
    partial = RESULTS / PICK / f'reasoning.{TUNE}.partial.jsonl'
    if partial.is_file():
        cmd = cmd + ['--resume']
        h.log(f'RESUME reasoning: {partial} exists -- adding --resume to the reasoning command')

    res = _launch_and_wait(tag, cmd, BOUND_H['reasoning'], dry_run, 'reasoning')
    if dry_run:
        return
    data = json.loads(OUT_JSON['reasoning'].read_text())
    eff_ctx = data.get('reasoning_effective_ctx')
    records = data.get('records', [])
    rungs = [(r.get('ctx'), r.get('accuracy'), r.get('budget_hits'), r.get('samples'),
             r.get('decode_tps_mean'), r.get('prefill_s_mean'), r.get('acceptance_pooled')) for r in records]
    h.log(f'RESULT reasoning {TUNE} reasoning_effective_ctx={eff_ctx} rungs={rungs}')
    hit_rows = [row for rec in records for row in rec.get('rows', []) if row.get('budget_hit')]
    n_hits = len(hit_rows)
    tok_sum = sum((row.get('completion_tokens') or 0) for row in hit_rows)
    h.log(f'RUNAWAY draws={n_hits} tokens={tok_sum}')
    assert_manifest('reasoning', tag, started_epoch=res.get('started_epoch'))
    write_provenance('reasoning', res)


DO = {'capacity': do_capacity, 'retrieval': do_retrieval, 'reasoning': do_reasoning}


def step_complete(step):
    return OUT_JSON[step].is_file() and PROV_JSON[step].is_file()


# --------------------------------------------------------------------------- CLI
def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description='M41 capacity + retrieval-depth + reasoning-depth ladder chain runner '
                    f'({PICK}, predictor-ON, tune {TUNE})')
    ap.add_argument('--dry-run', action='store_true',
                    help='print the full command plan (all three ladders) to stdout AND queue.log, '
                         'exit 0; launches nothing but the three `-m bench.run_* --help` flag prechecks (no router, no GPU work)')
    ap.add_argument('--from-step', choices=STEPS, default='capacity',
                    help='resume from this ladder (1..3, per SPEC.md 2); ladders before it are '
                         'logged SKIP if already complete (out json + provenance json both exist), '
                         'else FATAL rather than silently skip incomplete state')
    return ap.parse_args(argv)


def _teardown_for_signal():
    """R8 (SPEC_FIX1): best-effort R3-style teardown (unload BEFORE stop_router) invoked from a
    signal handler -- every step is guarded and logged, never raised, so the handler always
    reaches its exit."""
    if _current_driver is not None and _current_driver.poll() is None:
        try:
            _current_driver.kill()
            _current_driver.wait()
        except Exception as ex:
            h.log(f'signal teardown: failed to kill live driver: {ex!r}')
    if _router_owned:
        try:
            h.unload()
        except Exception as ex:
            h.log(f'signal teardown: unload failed (continuing to stop_router): {ex!r}')
        try:
            h.stop_router()
        except Exception as ex:
            h.log(f'signal teardown: stop_router also failed: {ex!r}')
    else:
        h.log('signal teardown: router not owned by this process -- skipping stop_router()')


def _signal_handler(signum, _frame):
    h.log(f'FATAL signal {signum}')
    _teardown_for_signal()
    os._exit(1)


def _install_signal_handlers():
    """R8 (SPEC_FIX1): SIGTERM/SIGINT log FATAL, kill+wait the live driver, run the R3 teardown,
    exit 1."""
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)


def main():
    _install_signal_handlers()
    args = parse_args()
    if args.dry_run:
        h.ECHO_STDOUT = True
    os.makedirs(OUT, exist_ok=True)
    lock = (Path(OUT) / 'm41_queue.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    (Path(OUT) / 'm41_queue.pid').write_text(str(os.getpid()))

    if not OVERLAY.is_file():
        h.fail(f'overlay not found: {OVERLAY}')
    h.log(f'M41 pick={PICK} tune={TUNE} profile={PROFILE} overlay={OVERLAY.name} '
         f'sha256={h.sha(str(OVERLAY))}')

    idle_precheck()

    from_idx = STEPS.index(args.from_step)
    for i, step in enumerate(STEPS):
        if i < from_idx:
            if step_complete(step):
                h.log(f'SKIP {step} (--from-step {args.from_step}): '
                     f'{OUT_JSON[step].name} and provenance both present')
            else:
                h.fail(f'--from-step {args.from_step} skips {step}, but {OUT_JSON[step]} and/or '
                      f'{PROV_JSON[step]} are missing -- refusing to skip incomplete state')

    router_start(args.dry_run)
    for i, step in enumerate(STEPS):
        if i < from_idx:
            continue
        DO[step](args.dry_run)
    router_stop(args.dry_run)

    # R5 (SPEC_FIX1): dry-run ends with a DIFFERENT marker -- never the live one.
    h.log('=== M41 DRY-RUN DONE ===' if args.dry_run else '=== M41 DONE ===')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        import traceback
        h.log('FATAL ' + repr(e) + '\n' + traceback.format_exc())
        if _router_owned:
            # R3 (SPEC_FIX1): attempt unload() BEFORE stop_router(), guarded and logged.
            try:
                h.unload()
            except Exception as e3:
                h.log('FATAL cleanup unload failed (continuing to stop_router): ' + repr(e3))
            try:
                h.stop_router()
            except Exception as e2:
                h.log('FATAL cleanup stop_router also failed: ' + repr(e2))
        else:
            h.log('FATAL cleanup: router not owned by this process (failed before/without starting '
                 'one) -- skipping stop_router()')
        raise
