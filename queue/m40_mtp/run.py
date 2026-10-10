"""M40 MTP-ON certification chain: math500 + cjudge + vision_gate + reasoning-depth-128K for both
picks, plus humanevalplus/mbppplus (pick B only, no matched OFF row exists at the deployed medium
tune). Spec: $STACK_WORKDIR/queue/m40_mtp/SPEC.md.

Cold-review fixes (this file): D1-D16 + NEW, see README "Cold review fixes" section for the full
list with rationale; each is also called out inline at its fix site below.
"""
import argparse, fcntl, json, os, subprocess, threading, time
from pathlib import Path
import yaml
import helpers as h

R = Path(os.environ['STACK_REPO'])
Q = Path(os.environ['STACK_WORKDIR']) / 'queue'
D = Q / 'm40_mtp'
RES = Q / 'resolution'          # standing native-ARM64 EvalPlus grading path (C58); shared, not ours
OUT = h.OUT

PICK_A = 'Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed'
PICK_B = 'Qwen3.8-27B-mlx-uniform-4bit'
PICKS = [PICK_A, PICK_B]
EXPECT_TEMP = {PICK_A: 0.5, PICK_B: 0.6}
EXPECT_EFFORT = {PICK_A: 'medium', PICK_B: 'medium'}
# D5: depth was 4h < 3 samples * 9600s request-timeout (=8h); a budget-hitting draw at depth is a
# real, expected outcome, not evidence of a stuck driver. D4: vision gets an explicit bound too
# (previously unbounded d.wait()).
BOUND_H = {'math500': 12, 'cjudge': 8, 'coding': 12, 'depth': 8, 'vision': 2}  # F2: coding 6->12 (right-tailed pilots must not abort the block)
MATH_N = 100
CODING_N = 100
CJUDGE_FULL_N = 40
CJUDGE_PILOT_N = 5

# D2: only the process that actually started the router may stop it in the FATAL handler --
# never on a flock/idle-precheck failure, which happen before any router is touched.
_router_owned = False


# --------------------------------------------------------------------------- overlays (§2)
def load_registry():
    return yaml.safe_load((R / 'main_models.yaml').read_text())


def assert_pick_defaults(entry, pick):
    # D16: explicit if/h.fail, not bare `assert` (stripped under python -O; these are load-bearing
    # provenance checks, not debug aids).
    gd = entry['generation_defaults']
    if gd['enable_thinking'] is not True:
        h.fail(f'{pick}: enable_thinking is not True')
    if gd['thinking_budget'] != 81920:
        h.fail(f'{pick}: thinking_budget != 81920 (got {gd.get("thinking_budget")})')
    if gd['max_tokens'] != 102400:
        h.fail(f'{pick}: max_tokens != 102400 (got {gd.get("max_tokens")})')
    if not (entry['kv_prealloc_tokens'] == entry['max_kv_cache_size'] == 262144):
        h.fail(f'{pick}: kv_prealloc_tokens/max_kv_cache_size != 262144 '
              f'(got {entry.get("kv_prealloc_tokens")}/{entry.get("max_kv_cache_size")})')
    if gd['temperature'] != EXPECT_TEMP[pick]:
        h.fail(f'{pick}: temperature {gd.get("temperature")} != expected {EXPECT_TEMP[pick]}')
    if gd.get('reasoning_effort') != EXPECT_EFFORT[pick]:
        h.fail(f'{pick}: reasoning_effort {gd.get("reasoning_effort")} != expected {EXPECT_EFFORT[pick]}')


def build_overlays(pick):
    """Fresh from the CURRENT worktree registry, re-read per pick (main_models.yaml is the
    record). on_<pick>.yaml keeps draft_kind/draft_model on the pick only; off_<pick>.yaml strips
    draft_*/moe_expand from every entry (the m38 fresh_overlay recipe)."""
    data_on = load_registry()
    pick_entry_on = None
    for e in data_on['models']:
        if e['name'] == pick:
            pick_entry_on = e
            continue
        for key in list(e):
            if key.startswith('draft_') or key == 'moe_expand':
                e.pop(key)
    if pick_entry_on is None:
        h.fail(f'{pick} not found in main_models.yaml')
    if pick_entry_on.get('draft_kind') != 'mtp':
        h.fail(f'{pick}: ON overlay draft_kind != mtp (got {pick_entry_on.get("draft_kind")!r})')
    draft_model = pick_entry_on.get('draft_model')
    if not draft_model or not os.path.isdir(draft_model):
        h.fail(f'{pick}: draft_model dir missing or not a directory: {draft_model!r}')
    assert_pick_defaults(pick_entry_on, pick)
    on_path = Path(OUT) / f'on_{pick}.yaml'
    on_path.write_text(yaml.safe_dump(data_on, sort_keys=False))

    data_off = load_registry()
    for e in data_off['models']:
        for key in list(e):
            if key.startswith('draft_') or key == 'moe_expand':
                e.pop(key)
    pick_entry_off = next(e for e in data_off['models'] if e['name'] == pick)
    if 'draft_kind' in pick_entry_off or 'draft_model' in pick_entry_off:  # D16
        h.fail(f'{pick}: OFF overlay still carries draft fields')
    assert_pick_defaults(pick_entry_off, pick)
    off_path = Path(OUT) / f'off_{pick}.yaml'
    off_path.write_text(yaml.safe_dump(data_off, sort_keys=False))

    h.log(f'overlay {on_path.name} sha256={h.sha(str(on_path))}')
    h.log(f'overlay {off_path.name} sha256={h.sha(str(off_path))}')
    return str(on_path), str(off_path)


# --------------------------------------------------------------------------- ids (§3)
def load_ids(bench):
    d = json.loads((RES / 'ids.json').read_text())[bench]
    ids, pilot = d['ids'], d['pilot']
    if len(ids) != MATH_N:  # D16
        h.fail(f'resolution/ids.json[{bench}][ids] has {len(ids)} ids, expected {MATH_N}')
    if not set(pilot) <= set(ids):  # D16
        h.fail(f'resolution/ids.json[{bench}][pilot] is not a subset of [ids]')
    return ids, pilot


# --------------------------------------------------------------------------- D8: pilot-projection guard
def check_pilot_projection(tag, summary, full_n, bound_h):
    """After every pilot: WARN at 60% of budget, FATAL over 100% -- a pilot that already projects
    past the bound must not be allowed to silently run into the run_generate TIMEOUT hours later."""
    mean_s = summary.get('wall_mean_s')
    if mean_s is None:
        return
    projected_h = mean_s * full_n / 3600
    bound_s = bound_h * 3600
    if mean_s * full_n > bound_s:
        h.fail(f'{tag}: pilot projects {projected_h:.2f} h for the full arm, exceeding bound_h={bound_h} h')
    if mean_s * full_n > 0.6 * bound_s:
        h.log(f'WARN pilot projects {projected_h:.2f} h vs bound {bound_h} h ({tag}, mean_s={mean_s}, n={full_n})')


# --------------------------------------------------------------------------- D6b: coding re-grade guard
def check_no_stale_archive(model, bench, tune):
    """resolution/native_grade.py does `archive.mkdir(parents=True, exist_ok=False)` -- a second
    invocation for the same (model, bench, tune) crashes with a raw FileExistsError. Detect that
    up front and FATAL with the fix, instead of a bare traceback hours into a rerun."""
    archive_dir = RES / 'native_grade_archive' / model / f'{bench}.{tune}'
    if archive_dir.exists():
        h.fail(f'{model} {bench}.{tune}: native_grade archive dir already exists ({archive_dir}) -- '
              f'a re-grade will crash with FileExistsError. If this is an intentional re-grade, '
              f'delete it first: rm -rf {archive_dir!s}')


# --------------------------------------------------------------------------- D11: draft-engagement evidence
def draft_counter_probe():
    """Best-effort read of a router-side cumulative draft/speculative-decode counter, for the
    provenance json. Verified against source (cold review D11): mlx-serve's own /metrics
    (src/mlx-serve/src/mlx_serve/metrics.py RequestMetrics dataclass) carries no draft_n /
    draft_n_accepted field at all -- only per-request TTFT/TPS/token counts. mlx_vlm's per-worker
    /metrics (mlx_vlm/server/app.py) does carry draft_n/draft_n_accepted per *recent* request, but
    it lives on the worker's own port (not the router's :8000 this harness talks to) and is gated
    by a management API key we do not provision for this chain. So there is currently no reachable
    CUMULATIVE draft counter -- this always returns None; callers log a WARN and record
    `"draft_counters": null` so the analysis knows certification of that arm rests on the worker
    cmdline `--draft-kind` check alone, not on an acceptance-rate delta."""
    return None


# --------------------------------------------------------------------------- D3: non-vacuous draft-state check
def _force_load(pick, timeout=900):
    import urllib.request
    body = json.dumps({'model': pick}).encode()
    req = urllib.request.Request('http://localhost:8000/v1/models/load', method='POST', data=body,
                                 headers={'Content-Type': 'application/json'})
    urllib.request.urlopen(req, timeout=timeout).read()


def worker_cmdline_for_check(pick, tag):
    """mlx-serve loads lazily: right after ensure_router(), worker_cmdline() == '' until the first
    request. An empty cmdline makes an OFF-arm's `'--draft-kind' not in c` check pass VACUOUSLY --
    it never actually inspected a loaded worker. Force a load via POST /v1/models/load first, then
    re-read; if it's still empty, FATAL rather than certify off an unverified state."""
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


# --------------------------------------------------------------------------- generic id-matched arm
def arm_ids(model, bench, tune, overlay, expect_draft, bound_h, dry_run, use_native_grade=False):
    ids, pilot = load_ids(bench)
    if use_native_grade and not dry_run:
        check_no_stale_archive(model, bench, tune)  # D6b
    existing = h.rows(model, bench, tune)  # pure read; safe (and informative) under --dry-run too
    if existing:
        got = {r['id'] for r in existing}
        if not got <= set(ids):  # D16
            h.fail(f'{model} {bench}.{tune} has existing rows outside the target id set -- stale tune reused, do not resume')
        h.log(f'{bench}.{tune} for {model} resuming from partial: {len(existing)} existing rows')
        phases = [('full', ids)]
    else:
        h.log(f'{bench}.{tune} for {model}: no existing rows, fresh tune')
        phases = [('pilot', pilot), ('full', ids)]
    for label, use_ids in phases:
        tag = f'{model}_{bench}_{tune}_{label}'
        extra = ['--limit', f'{bench}=0', '--ids', f'{bench}=' + ':'.join(use_ids)]
        rc = h.run_generate(model, bench, tune, len(use_ids), tag, overlay, expect_draft=expect_draft,
                            extra=extra, bound_h=bound_h, dry_run=dry_run)
        if dry_run:
            continue
        if rc:
            raise RuntimeError(tag + ' generation failed')
        summary = h.summarize(model, bench, tune, len(use_ids), tag)
        if summary['n'] != len(use_ids) or summary['errors']:
            raise RuntimeError(tag + ' invalid rows')
        if label == 'pilot':
            h.log(f'PILOT projected lower-bound seconds={summary["wall_mean_s"] * len(ids)} max={summary["wall_max_s"]}')
            check_pilot_projection(tag, summary, len(ids), bound_h)  # D8
    gtag = f'{tune}_{bench}'
    if dry_run:
        if use_native_grade:
            h.log(f'PLAN grade {gtag}: {h.PY} {RES / "native_grade.py"} {model} {bench} {tune} '
                  f'(env MLX_SERVE_CONFIG={os.path.basename(overlay)} PYTHONPATH={R / "benchmark"}) '
                  f'-- not launched (--dry-run)')
        else:
            h.log(f'PLAN grade {gtag}: {h.PY} {R / "benchmark/run.py"} grade --models {model} --benches {bench} '
                  f'--tune {tune} (env MLX_SERVE_CONFIG={os.path.basename(overlay)}) -- not launched (--dry-run)')
        return
    if use_native_grade:
        # D1: native_grade.py does `from bench import grade` with no self sys.path insertion --
        # unlike run.py/vision_gate.py it needs PYTHONPATH set explicitly, or it dies with
        # ModuleNotFoundError: bench (verified empirically: fails under env -i without it).
        # D12: pid file, like every other subprocess this runner launches.
        with (Path(OUT) / f'{gtag}_grade.log').open('a') as out:
            p = subprocess.Popen([h.PY, str(RES / 'native_grade.py'), model, bench, tune], cwd=R,
                                 env=dict(os.environ, MLX_SERVE_CONFIG=overlay, PYTHONPATH=str(R / 'benchmark')),
                                 stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            (Path(OUT) / f'{gtag}_grade.pid').write_text(str(p.pid))
            rc = p.wait()
        if rc:
            raise RuntimeError(f'{gtag} native grading failed rc={rc}')
    else:
        h.grade(model, bench, tune, gtag, overlay)
    score = json.loads((R / 'benchmark/results' / model / f'{bench}.{tune}.score.json').read_text())
    if score.get('acc') is None or score.get('errors'):
        raise RuntimeError(f'{gtag} invalid grade: {score}')
    if score.get('n') != len(ids):
        raise RuntimeError(f'{gtag} invalid score n (want {len(ids)}, got {score.get("n")})')
    h.log('RESULT ' + model + ' ' + bench + ' ' + tune + ' ' +
         json.dumps({k: score.get(k) for k in ['n', 'acc', 'acc_strict', 'conv_rate', 'nonconv_kinds']}))
    h.log(f'REVIEW OWED: update README ranking/evidence tables for {model} {bench} {tune}; no automatic promotion')


# --------------------------------------------------------------------------- cjudge arm (no explicit ids, as m38)
def arm_cjudge(model, tune, overlay, expect_draft, bound_h, dry_run):
    bench = 'cjudge'
    existing = h.rows(model, bench, tune)  # pure read; safe (and informative) under --dry-run too
    phases = [('full', CJUDGE_FULL_N)] if existing else [('pilot', CJUDGE_PILOT_N), ('full', CJUDGE_FULL_N)]
    for label, n in phases:
        tag = f'{model}_{bench}_{tune}_{label}'
        rc = h.run_generate(model, bench, tune, n, tag, overlay, expect_draft=expect_draft, bound_h=bound_h,
                            dry_run=dry_run)
        if dry_run:
            continue
        if rc:
            raise RuntimeError(tag + ' generation failed')
        summary = h.summarize(model, bench, tune, n, tag)
        if summary['n'] != n or summary['errors']:
            raise RuntimeError(tag + ' invalid rows')
        if label == 'pilot':
            h.log(f'PILOT projected lower-bound seconds={summary["wall_mean_s"] * CJUDGE_FULL_N} max={summary["wall_max_s"]}')
            check_pilot_projection(tag, summary, CJUDGE_FULL_N, bound_h)  # D8
    gtag = f'{tune}_{bench}'
    if dry_run:
        h.log(f'PLAN grade {gtag}: {h.PY} {R / "benchmark/run.py"} grade --models {model} --benches {bench} '
              f'--tune {tune} (env MLX_SERVE_CONFIG={os.path.basename(overlay)}) -- not launched (--dry-run)')
        return
    h.grade(model, bench, tune, gtag, overlay)
    score = json.loads((R / 'benchmark/results' / model / f'{bench}.{tune}.score.json').read_text())
    # cjudge is `kind: open` (docs/judge-panel-c.md): grade_open ALWAYS returns acc=None by design.
    if score.get('n') != CJUDGE_FULL_N or score.get('errors'):
        raise RuntimeError(f'{gtag} invalid grade: {score}')
    h.log('RESULT ' + model + ' ' + bench + ' ' + tune + ' ' +
         json.dumps({k: score.get(k) for k in ['n', 'acc', 'conv_rate', 'nonconv_kinds', 'errors']}))
    h.log('NOTE acc=null is EXPECTED for cjudge (kind=open; ranking is bench/judge_pairwise.py)')
    h.log(f'REVIEW OWED: judge-panel anchors + pairwise ranking for {model} {tune}; no automatic ranking change')


# --------------------------------------------------------------------------- vision gate (§3.3, NEW step 6b)
def run_vision_gate(pick, overlay, tune, expect_draft, dry_run, watch_total=20):
    out = R / 'benchmark/results' / pick / f'vision_gate.{tune}.jsonl'
    tag = f'vision_gate_{tune}'
    existing_rows = h.rows(pick, 'vision_gate', tune)
    prov_path = out.parent / f'vision_gate.{tune}.provenance.json'
    cmd = [h.PY, str(R / 'benchmark/vision_gate.py'), '--model', pick, '--out', str(out)]
    if existing_rows:
        # F3: never merge two predictor states into one jsonl -- resume only if the existing rows'
        # provenance names THIS overlay (sha); otherwise FATAL with the fix.
        if not prov_path.is_file():
            h.fail(f'{tag}: {len(existing_rows)} existing rows but no provenance json -- unknown predictor state; '
                   f'move {out} aside before rerunning')
        prev = json.loads(prov_path.read_text())
        if prev.get('overlay_sha256') != h.sha(overlay):
            h.fail(f'{tag}: existing rows were produced under overlay sha {prev.get("overlay_sha256")} != current '
                   f'{h.sha(overlay)} -- refusing to resume across predictor states; move {out} aside')
        cmd.append('--resume')  # D6a
    h.log(f'RUN {tag}: ' + ' '.join(cmd) +
         f' (env MLX_SERVE_CONFIG={os.path.basename(overlay)}, APC_ENABLED absent; '
         f'note: vision_gate.py has no --sampling-profile flag, profile=deployed is hardcoded internally)')
    if dry_run:
        h.log(f'PLAN {tag}: worker cmdline check (force-load if empty; expect --draft-kind '
              f'{"present" if expect_draft else "absent"}); bench_watch --bench vision_gate --tune {tune} '
              f'--total {watch_total} (fallback: 5-min heartbeat); bound_h={BOUND_H["vision"]}; '
              f'draft_counter_probe() before/after -- not launched (--dry-run)')
        return
    c = worker_cmdline_for_check(pick, tag)  # D3
    has_draft = '--draft-kind' in c
    h.log(f"worker cmdline: draft={has_draft} :: {c[-160:]}")
    if has_draft != expect_draft:
        raise RuntimeError(f'vision_gate {pick} {tune}: worker draft state {has_draft} != expected {expect_draft}')
    draft_before = draft_counter_probe()  # D11
    env = dict(os.environ)
    env.pop('APC_ENABLED', None)
    env['MLX_SERVE_CONFIG'] = overlay
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.strftime('%Y-%m-%dT%H:%M:%S')
    prov_path.write_text(json.dumps({'model': pick, 'tune': tune, 'overlay': overlay, 'overlay_sha256': h.sha(overlay), 'worker_cmdline': c, 'started': started, 'finished': None, 'resumed': bool(existing_rows), 'draft_counters': None}, indent=2))  # F3: stub before launch
    d = subprocess.Popen(cmd, cwd=str(R), env=env, stdout=open(f'{OUT}/{tag}.log', 'a'),
                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    open(f'{OUT}/{tag}.pid', 'w').write(str(d.pid))
    watch_env = dict(env)
    watch_env['PYTHONPATH'] = str(R / 'benchmark')
    watch_cmd = [h.PY, str(R / 'benchmark/m1/bench_watch.py'), '--models', pick, '--bench', 'vision_gate',
                '--tune', tune, '--total', str(watch_total), '--driver-pattern', '[v]ision_gate.py',  # D14
                '--out', f'{OUT}/watch_{tag}.json', '--interval', '300']
    w = subprocess.Popen(watch_cmd, cwd=str(R), env=watch_env, stdout=open(f'{OUT}/watch_{tag}.log', 'a'),
                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    time.sleep(2)
    heartbeat_stop = None
    if w.poll() is not None:
        h.log(f'bench_watch rejected --bench vision_gate --tune {tune} (rc={w.returncode}); falling back to heartbeat thread')
        w.wait()  # D15
        w = None
        heartbeat_stop = threading.Event()

        def hb():
            while not heartbeat_stop.wait(300):
                n = len(h.rows(pick, 'vision_gate', tune))
                h.log(f'HEARTBEAT {tag}: rows={n}/{watch_total} worker_cmdline_present={bool(h.worker_cmdline())}')
        threading.Thread(target=hb, daemon=True).start()
    # D4: was a bare rc=d.wait() (unbounded); now the same poll+bound loop as run_depth, bound 2h.
    t0 = time.time()
    rc = None
    bound_h = BOUND_H['vision']
    while rc is None:
        rc = d.poll()
        if time.time() - t0 > bound_h * 3600:
            d.kill()
            d.wait()  # D15 (applied to d too, for consistency)
            h.log(f'TIMEOUT {tag} after {bound_h} h')
            rc = -9
            break
        time.sleep(5)
    if w is not None:
        w.kill()
        w.wait()  # D15
    if heartbeat_stop is not None:
        heartbeat_stop.set()
    h.log(f'END {tag} rc={rc}')
    if rc:
        raise RuntimeError(f'{tag} failed rc={rc}')
    finished = time.strftime('%Y-%m-%dT%H:%M:%S')
    draft_after = draft_counter_probe()  # D11
    if draft_before is None and draft_after is None:
        h.log(f'WARN {tag}: no reachable draft/speculative-decode counter (see draft_counter_probe '
             f'docstring) -- certification of this arm rests on the worker cmdline --draft-kind check alone')
    summary = json.loads((out.parent / f'vision_gate.{tune}.summary.json').read_text())
    h.log(f'vision_gate {tune} pass count: {summary.get("pass")}/{summary.get("n")}')
    prov = {'model': pick, 'tune': tune, 'overlay': overlay, 'overlay_sha256': h.sha(overlay), 'worker_cmdline': c,
           'started': started, 'finished': finished, 'resumed': bool(existing_rows),
           'draft_counters': {'before': draft_before, 'after': draft_after}}
    prov_path.write_text(json.dumps(prov, indent=2))


# --------------------------------------------------------------------------- reasoning depth 128K (§3.4/3.6)
def run_depth(pick, overlay, out_tag, expect_draft, dry_run, bound_h):
    env = dict(os.environ)
    env.pop('APC_ENABLED', None)
    env['MLX_SERVE_CONFIG'] = overlay
    env['PYTHONPATH'] = str(R / 'benchmark')
    # NOTE: the spec's literal `benchmark/bench/run_reasoning.py` script path fails at import time
    # (`from .driver import ...` -- a relative import with no package context when run directly;
    # verified). The module's own docstring says `-m bench.run_reasoning`; used here instead.
    cmd = [h.PY, '-m', 'bench.run_reasoning', '--model', pick, '--grid', '128000', '--samples', '3',
          '--chain-len', '4', '--threshold', '0.85', '--sampling-profile', 'deployed', '--out-tag', out_tag]
    tag = f'depth_{out_tag}'
    h.log(f'RUN {tag}: ' + ' '.join(cmd) +
         f' (cwd={R / "benchmark"}, env MLX_SERVE_CONFIG={os.path.basename(overlay)} PYTHONPATH={R / "benchmark"})')
    if dry_run:
        h.log(f'PLAN {tag}: worker cmdline check (force-load if empty; expect --draft-kind '
              f'{"present" if expect_draft else "absent"}); 5-min heartbeat thread; bound_h={bound_h}; '
              f'draft_counter_probe() before/after -- not launched (--dry-run)')
        return
    c = worker_cmdline_for_check(pick, tag)  # D3
    has_draft = '--draft-kind' in c
    h.log(f"worker cmdline: draft={has_draft} :: {c[-160:]}")
    if has_draft != expect_draft:
        raise RuntimeError(f'depth {pick} {out_tag}: worker draft state {has_draft} != expected {expect_draft}')
    draft_before = draft_counter_probe()  # D11
    started = time.strftime('%Y-%m-%dT%H:%M:%S')
    d = subprocess.Popen(cmd, cwd=str(R / 'benchmark'), env=env, stdout=open(f'{OUT}/{tag}.log', 'a'),
                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    open(f'{OUT}/{tag}.pid', 'w').write(str(d.pid))
    partial = R / 'benchmark/results' / pick / f'reasoning.{out_tag}.partial.jsonl'
    stop_evt = threading.Event()

    def hb():
        while not stop_evt.wait(300):
            size = partial.stat().st_size if partial.exists() else 0
            h.log(f'HEARTBEAT {tag}: partial_bytes={size} worker_cmdline_present={bool(h.worker_cmdline())} '
                 f'driver_alive={d.poll() is None}')
    threading.Thread(target=hb, daemon=True).start()
    t0 = time.time()
    rc = None
    while rc is None:
        rc = d.poll()
        if time.time() - t0 > bound_h * 3600:
            d.kill()
            d.wait()  # D15
            h.log(f'TIMEOUT {tag} after {bound_h} h')
            rc = -9
            break
        time.sleep(5)
    stop_evt.set()
    h.log(f'END {tag} rc={rc}')
    if rc:
        raise RuntimeError(f'{tag} failed rc={rc}')
    finished = time.strftime('%Y-%m-%dT%H:%M:%S')
    draft_after = draft_counter_probe()  # D11
    if draft_before is None and draft_after is None:
        h.log(f'WARN {tag}: no reachable draft/speculative-decode counter (see draft_counter_probe '
             f'docstring) -- certification of this arm rests on the worker cmdline --draft-kind check alone')
    result = json.loads((R / 'benchmark/results' / pick / f'reasoning.{out_tag}.json').read_text())
    h.log(f'depth {out_tag} REASONING_EFFECTIVE_CTX={result.get("reasoning_effective_ctx")}')
    prov = {'overlay': overlay, 'overlay_sha256': h.sha(overlay), 'worker_cmdline': c,
           'started': started, 'finished': finished,
           'draft_counters': {'before': draft_before, 'after': draft_after}}
    (R / 'benchmark/results' / pick / f'reasoning.{out_tag}.provenance.json').write_text(json.dumps(prov, indent=2))


# --------------------------------------------------------------------------- per-pick chain (§3)
def router_start(overlay, dry_run, label):
    global _router_owned
    if dry_run:
        h.log(f'PLAN router: ensure_router({os.path.basename(overlay)}) [{label}] -- not launched (--dry-run)')
        return
    _router_owned = True  # F1: set BEFORE ensure_router -- idle precheck guarantees no foreign router; a router we Popen but fail to validate must still be stopped on FATAL
    h.ensure_router(overlay)


def router_stop(dry_run, label):
    global _router_owned
    if dry_run:
        h.log(f'PLAN router: unload(); stop_router() [{label}] -- not launched (--dry-run)')
        return
    h.unload()
    h.stop_router()
    if h.listeners():
        raise RuntimeError(f'router still listening on :8000 after {label} stop')
    _router_owned = False  # F1: clear only after the listener check passed


def run_pick(pick, dry_run, from_step):
    on_overlay, off_overlay = build_overlays(pick)
    is_b = (pick == PICK_B)
    on_steps = [1, 2, 3, 4] + ([5] if is_b else [])
    off_steps = [6] + ([7] if is_b else [])

    if any(s >= from_step for s in on_steps):
        router_start(on_overlay, dry_run, f'{pick} ON')
        if from_step <= 1:
            arm_ids(pick, 'math500', 'm40on', on_overlay, 'mtp', BOUND_H['math500'], dry_run)
            h.log(f'OFF pair for {pick} math500: existing math500.m37med rows (verified separately; not regenerated)')
        else:
            h.log(f'SKIP step 1 (math500 ON) for {pick} (--from-step {from_step})')
        if from_step <= 2:
            arm_cjudge(pick, 'm40on', on_overlay, 'mtp', BOUND_H['cjudge'], dry_run)
            h.log(f'OFF pair for {pick} cjudge: existing cjudge.m38 rows (not regenerated)')
        else:
            h.log(f'SKIP step 2 (cjudge ON) for {pick} (--from-step {from_step})')
        if from_step <= 3:
            run_vision_gate(pick, on_overlay, 'm40on', True, dry_run)
            h.log(f'OFF pair for {pick} vision_gate: NEW step 6b vision_gate.m40off run on the OFF '
                 f'overlay (cold review NEW) -- existing vision_gate.v1 rows have no recorded '
                 f'predictor state and are kept for reference only')
        else:
            h.log(f'SKIP step 3 (vision_gate ON) for {pick} (--from-step {from_step})')
        if from_step <= 4:
            run_depth(pick, on_overlay, 'm40on-d128k', True, dry_run, BOUND_H['depth'])
        else:
            h.log(f'SKIP step 4 (depth ON) for {pick} (--from-step {from_step})')
        if is_b:
            if from_step <= 5:
                for bench in ['humanevalplus', 'mbppplus']:
                    arm_ids(pick, bench, 'm40on', on_overlay, 'mtp', BOUND_H['coding'], dry_run, use_native_grade=True)
            else:
                h.log(f'SKIP step 5 (coding ON) for {pick} (--from-step {from_step})')
        router_stop(dry_run, f'{pick} ON')

    if any(s >= from_step for s in off_steps):
        router_start(off_overlay, dry_run, f'{pick} OFF')
        if from_step <= 6:
            run_depth(pick, off_overlay, 'm40off-d128k', False, dry_run, BOUND_H['depth'])
            # NEW (cold review): step 6b -- vision OFF pair, both picks. vision_gate.v1 (the only
            # prior vision row set) has no recorded predictor state, so it is not a real OFF pair.
            run_vision_gate(pick, off_overlay, 'm40off', False, dry_run)
        else:
            h.log(f'SKIP step 6/6b (depth OFF + vision_gate OFF) for {pick} (--from-step {from_step})')
        if is_b:
            if from_step <= 7:
                for bench in ['humanevalplus', 'mbppplus']:
                    arm_ids(pick, bench, 'm40off', off_overlay, 'off', BOUND_H['coding'], dry_run, use_native_grade=True)
            else:
                h.log(f'SKIP step 7 (coding OFF) for {pick} (--from-step {from_step})')
        router_stop(dry_run, f'{pick} OFF')

    h.log(f'=== M40 {pick} DONE ===')


# --------------------------------------------------------------------------- invariants + CLI (§4)
def docker_precheck():
    """Coordinator addendum (cold review follow-up): the pick-B coding legs (§3 steps 5/7) grade
    through resolution/native_grade.py, which needs a live docker daemon (OrbStack, not Docker
    Desktop, on this box) and the mlx-evalplus-native:recovery image. FATAL here, before any GPU
    work, rather than hours into a chain at the first grade call. Read-only: run for real under
    --dry-run too."""
    p = h.sh(['docker', 'info'])
    if p.returncode != 0:
        h.fail('docker daemon unreachable (`docker info` failed) -- this box runs OrbStack, not '
              f'Docker Desktop; start it with `orb start`. stderr: {p.stderr.strip()[:300]}')
    h.log('PRECHECK docker info OK (OrbStack)')
    p = h.sh(['docker', 'image', 'inspect', 'mlx-evalplus-native:recovery'])
    if p.returncode != 0:
        h.fail('docker image mlx-evalplus-native:recovery missing (`docker image inspect` failed) '
              f'-- required by resolution/native_grade.py for the pick-B coding legs. stderr: {p.stderr.strip()[:300]}')
    h.log('PRECHECK docker image mlx-evalplus-native:recovery present')


def idle_precheck():
    p = h.sh(['pgrep', '-f', '[r]un.py generate|[m]lx_vlm.server'])
    if p.stdout.strip() or h.listeners():
        raise RuntimeError('Expected idle driver/worker/router before starting M40 (run.py generate, '
                           'mlx_vlm.server, or a listener on :8000 is present)')
    h.log('idle precheck OK: no generate driver, no mlx_vlm.server, 0 listeners on :8000')
    docker_precheck()


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description='M40 MTP-ON certification chain runner')
    ap.add_argument('--dry-run', action='store_true',
                    help='build+assert overlays for BOTH picks, print the full command plan to '
                         'stdout AND queue.log, exit 0; launches nothing (no router, no GPU work)')
    ap.add_argument('--pick', choices=['A', 'B'], default=None,
                    help='filter to one pick for a rerun; ignored under --dry-run (acceptance requires '
                         'both picks)')
    ap.add_argument('--from-step', type=int, default=1,
                    help='resume a pick from step N (1..7, per §3); earlier steps are logged as SKIP')
    return ap.parse_args(argv)


def main():
    args = parse_args()
    if args.dry_run:
        h.ECHO_STDOUT = True  # D13: plan must print to stdout too, not just queue.log
    os.makedirs(OUT, exist_ok=True)
    lock = (Path(OUT) / 'queue.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    (Path(OUT) / 'queue.pid').write_text(str(os.getpid()))

    idle_precheck()

    if args.dry_run:
        if args.pick:
            h.log(f'NOTE --pick {args.pick} ignored under --dry-run: acceptance requires overlays '
                 f'+ plan for BOTH picks')
        picks = PICKS
    else:
        picks = PICKS if not args.pick else [PICK_A if args.pick == 'A' else PICK_B]

    for pick in picks:
        run_pick(pick, args.dry_run, args.from_step)

    if picks == PICKS:
        h.log('=== M40 MTP QUEUE DONE ===')
    else:
        h.log(f'=== M40 MTP partial run done (picks={picks}) ===')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        import traceback
        h.log('FATAL ' + repr(e) + '\n' + traceback.format_exc())
        # D2: only stop a router THIS process actually started/owns -- a flock or idle-precheck
        # failure happens before any router is touched and must never kill someone else's router.
        if _router_owned:
            try:
                h.stop_router()
            except Exception as e2:
                h.log('FATAL cleanup stop_router also failed: ' + repr(e2))
        else:
            h.log('FATAL cleanup: router not owned by this process (failed before/without starting '
                 'one) -- skipping stop_router()')
        raise
