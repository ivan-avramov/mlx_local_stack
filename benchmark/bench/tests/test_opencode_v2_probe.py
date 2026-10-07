"""P155: native v2 probe, transport aborts, continuation and real wire captures."""
from __future__ import annotations
import ast
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

import pytest
from bench import provenance, progress_gate

MODEL = 'Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed'


@pytest.fixture
def probe(monkeypatch, tmp_path):
    monkeypatch.setenv('STACK_WORKDIR', str(tmp_path))
    assert importlib.util.find_spec('run_opencode_probe_v2'), 'v2 probe is missing: transport failures cannot abort and resume identity is unchecked'
    return importlib.import_module('run_opencode_probe_v2')


def events(kind='ok'):
    start = {'type': 'step_start', 'sessionID': 'ses_test'}
    finish = {'type': 'step_finish', 'sessionID': 'ses_test'}
    if kind == 'retry': return [start, start, finish, start, {'type': 'text', 'sessionID': 'ses_test'}]
    if kind == 'ok': return [start, {'type': 'tool_use'}, finish, start, {'type': 'text', 'sessionID': 'ses_test'}]
    if kind == 'empty': return []
    if kind == 'no_error': return [start]
    types = {'http500': 'provider.internal', 'drop': 'provider.invalid-output', 'refuse': 'provider.transport', 'ctx400': 'provider.invalid-request', 'other400': 'provider.invalid-request'}
    error = {'type': types[kind], 'status': 400 if '400' in kind else 500,
             'message': 'bad request', 'response': {'body': json.dumps({'error': {'message': "This model's maximum context length is 4096 tokens. However, your messages resulted in 9999 tokens. Please reduce the length of the messages.", 'code': 'context_length_exceeded'}}) if kind == 'ctx400' else 'broken'}}
    return [start, {'type': 'error', 'sessionID': 'ses_test', 'error': error}]


def fixture_probe(probe, monkeypatch, tmp_path, kind='ok'):
    p = probe
    root = tmp_path / 'polyglot'
    for name in ('one', 'two'):
        d = root / 'python/exercises/practice' / name
        (d / '.docs').mkdir(parents=True)
        (d / '.docs/instructions.md').write_text('Set answer = 42.\n')
        (d / 'solution.py').write_text('answer = 0\n')
        (d / 'solution_test.py').write_text('from solution import answer\ndef test_answer(): assert answer == 42\n')
    monkeypatch.setenv('POLYGLOT_DIR', str(root))
    carrier = tmp_path / 'carrier.json'; carrier.write_bytes(p.BENCH_OPENCODE_CONFIG.read_bytes())
    plugin = tmp_path / 'noretry.js'; plugin.write_bytes(p.NORETRY_PLUGIN.read_bytes())
    monkeypatch.setattr(p, 'BENCH_OPENCODE_CONFIG', carrier)
    monkeypatch.setattr(p, 'NORETRY_PLUGIN', plugin)
    canned = tmp_path / 'events.jsonl'
    rc = tmp_path / 'rc'; export = tmp_path / 'export.json'; calls = tmp_path / 'calls'
    export.write_text(json.dumps({'info': {'id': 'ses_test'}, 'messages': [
        {'type': 'assistant', 'tokens': {'input': 100, 'output': 10}, 'content': [{'type': 'tool', 'name': 'write', 'state': {'input': {'path': str(tmp_path / 'solution.py')}, 'status': 'completed'}}]},
        {'type': 'assistant', 'tokens': {'input': 110, 'output': 5}, 'content': []}]}))
    binary = tmp_path / 'opencode'
    q = shlex.quote
    binary.write_text('#!/bin/sh\ncase "$1" in\n--version) echo 2.0.20;;\nrun)\n' +
        f'echo "$OPENCODE_CONFIG_CONTENT" >> {q(str(calls))}\n' +
        'printf "answer = 42\\n" > solution.py\n' +
        f'cat {q(str(canned))}\nexit "$(cat {q(str(rc))})";;\n' +
        f'session) cat {q(str(export))};;\n*) exit 2;;\nesac\n')
    binary.chmod(0o755)
    monkeypatch.setenv('OPENCODE_PROBE_BIN', str(binary))
    router = {'pid': 123, 'config': '$STACK_WORKDIR/registry.yaml', 'config_sha256': 'registry-sha'}
    monkeypatch.setattr(provenance, 'assert_served_config', lambda *a, **k: dict(router))
    monkeypatch.setattr(provenance, 'assert_served_config_unchanged', lambda *a, **k: dict(router))
    monkeypatch.setattr(provenance, 'opencode_v2_destination', lambda *a, **k: 'http://127.0.0.1:12345/v1')
    monkeypatch.setattr(provenance, '_git_shas', lambda: {'serving_path': 'serving-sha'})
    monkeypatch.setattr(provenance, 'gather', lambda model, **kw: {'model': model, 'git': {'serving_path': 'serving-sha'}, **kw})
    grades = []
    monkeypatch.setattr(p, '_grade_python', lambda *a: (grades.append(True) or (True, 'passed')))
    out = tmp_path / 'rows.jsonl'
    def set_kind(k):
        canned.write_text('not json\n' + '\n'.join(json.dumps(e) for e in events(k)) + '\n')
        rc.write_text('0' if k in ('ok', 'retry', 'empty') else '1')
    def run(items='one,two'):
        monkeypatch.setattr(sys, 'argv', ['probe', '--model', MODEL, '--items', items, '--seed-base', '77', '--poll-s', '0.01', '--out', str(out)])
        return p.main()
    set_kind(kind)
    return dict(run=run, set_kind=set_kind, out=out, mp=out.with_suffix('.manifest.json'), calls=calls,
                export=export, carrier=carrier, plugin=plugin, grades=grades, router=router)


@pytest.mark.parametrize('kind', ['http500', 'drop', 'refuse', 'no_error', 'other400', 'retry', 'empty'])
def test_transport_matrix_aborts_before_grade(probe, monkeypatch, tmp_path, kind):
    f = fixture_probe(probe, monkeypatch, tmp_path, kind)
    with pytest.raises(SystemExit) as exc:
        f['run']()
    assert exc.value.code != 0
    assert not f['out'].exists(), 'transport failure was written as a graded row'
    assert f['grades'] == [], 'transport failure reached the grader'
    assert len(f['calls'].read_text().splitlines()) == 1, 'probe continued after transport abort'
    stamp = json.loads(f['mp'].read_text())['transport_abort']
    assert set(stamp) == {'item', 'rc', 'stop_reason', 'signature'}
    assert stamp['item'] == 'python/one'
    artifacts = list((tmp_path / 'opencode-probe-v2/aborted').rglob('*'))
    assert any(p.name == 'events.jsonl' for p in artifacts)
    assert any(p.name == 'stderr.txt' for p in artifacts)
    assert any(p.name == 'export.json' for p in artifacts)


def test_context_overflow_is_failed_row(probe, monkeypatch, tmp_path):
    f = fixture_probe(probe, monkeypatch, tmp_path, 'ctx400')
    assert f['run']('one') == 0
    row = json.loads(f['out'].read_text())
    assert row['nonconv_kind'] == 'context_overflow' and row['passed'] is False and row['acc'] == 0
    assert row['requests_observed'] == 1


def test_normal_events_export_and_row(probe, monkeypatch, tmp_path):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    assert f['run']() == 0
    rows = [json.loads(s) for s in f['out'].read_text().splitlines()]
    assert len(rows) == 2 and rows[0]['sampler_seed'] != rows[1]['sampler_seed']
    for row in rows:
        assert row['schema_version'] == 3 and row['scaffold'] == 'opencode-v2'
        assert row['requests_observed'] == 2 and row['session_id'] == 'ses_test'
        assert row['passed'] and row['acc'] == 1 and row['nonconv_kind'] is None
        assert row['traffic']['output_tokens'] == 15 and row['loop_metrics']['tool_calls'] == 1
        transcript = Path(row['transcript_path'].replace('$STACK_WORKDIR', str(tmp_path)))
        assert transcript.is_relative_to(tmp_path / 'opencode_transcripts')
        assert str(Path.home()) not in transcript.read_text()
        assert probe._login_name() not in transcript.read_text()
        assert Path(row['events_path'].replace('$STACK_WORKDIR', str(tmp_path))).is_file()
        assert row['max_tokens_semantics'] == 'fixed'
    overlays = [json.loads(s) for s in f['calls'].read_text().splitlines()]
    for row, overlay in zip(rows, overlays):
        assert overlay == probe._seed_overlay(MODEL, row['sampler_seed'])
        assert row['overlay_sha256'] == hashlib.sha256(json.dumps(overlay, sort_keys=True).encode()).hexdigest()


@pytest.mark.parametrize('mutation', ['same', 'carrier', 'plugin', 'transport_abort', 'served_config_drift'])
def test_resume_identity_and_abort_retry(probe, monkeypatch, tmp_path, mutation):
    f = fixture_probe(probe, monkeypatch, tmp_path, 'http500' if mutation == 'transport_abort' else 'ok')
    if mutation == 'transport_abort':
        with pytest.raises(SystemExit): f['run']()
        assert not f['out'].exists(), 'abort must leave the item unrecorded for same-seed continuation'
        f['set_kind']('ok')
    else:
        assert f['run']('one') == 0
    if mutation in ('carrier', 'plugin'):
        with f[mutation].open('a') as fp: fp.write('\n')
    if mutation == 'served_config_drift':
        doc = json.loads(f['mp'].read_text()); doc['served_config_drift'] = {'error': 'changed'}
        f['mp'].write_text(json.dumps(doc))
    before = f['calls'].read_text().splitlines()
    if mutation in ('carrier', 'plugin', 'served_config_drift'):
        with pytest.raises(SystemExit, match='REFUSED'): f['run']()
        assert f['calls'].read_text().splitlines() == before
    else:
        assert f['run']() == 0
        after = f['calls'].read_text().splitlines()
        assert len(after) == (3 if mutation == 'transport_abort' else 2)
        if mutation == 'transport_abort': assert after[0] == after[1], 'aborted item changed seed on resume'
        else: assert len([json.loads(s) for s in f['out'].read_text().splitlines()]) == 2


@pytest.mark.parametrize('reason', ['stalled', 'looping', 'hard_ceiling'])
@pytest.mark.parametrize('drift', [False, True])
def test_gate_checks_router_immediately(probe, monkeypatch, tmp_path, reason, drift):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    order = []
    def run(*args, **kwargs):
        work = args[1]
        (work / '.opencode_probe_events.jsonl').write_text(json.dumps(events()[0]) + '\n')
        (work / '.opencode_probe_stderr.txt').write_text('')
        (work / 'solution.py').write_text('answer = 42\n')
        order.append('kill')
        return 130, '', 1.0, progress_gate.GateResult(reason, [], 1.0, 130)
    def check(*a, **k):
        order.append('check')
        if drift: raise provenance.ServedConfigError('router changed')
        return f['router']
    monkeypatch.setattr(probe, '_run_opencode', run)
    monkeypatch.setattr(provenance, 'assert_served_config_unchanged', check)
    original = probe._export_session
    def export(*a, **k):
        order.append('export'); return original(*a, **k)
    monkeypatch.setattr(probe, '_export_session', export)
    if drift:
        with pytest.raises(SystemExit): f['run']('one')
        doc = json.loads(f['mp'].read_text())
        assert doc['served_config_drift'] and doc['transport_abort']
        assert not f['out'].exists() and not f['grades']
    else:
        assert f['run']('one') == 0
        assert json.loads(f['out'].read_text())['nonconv_kind'] == reason
    assert order[:2] == ['kill', 'check']


@pytest.mark.parametrize('export', ['missing', 'bad', 'error', 'retry'])
def test_bad_export_aborts(probe, monkeypatch, tmp_path, export):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    if export == 'missing': f['export'].unlink()
    elif export == 'bad': f['export'].write_text('not JSON')
    else:
        doc = json.loads(f['export'].read_text()); doc['messages'][0][export] = {'type': 'provider.internal'}
        f['export'].write_text(json.dumps(doc))
    with pytest.raises(SystemExit): f['run']('one')
    assert not f['out'].exists() and not f['grades']


def test_pwd_assertion_precedes_spawn(probe, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(probe.subprocess, 'Popen', lambda *a, **k: calls.append(a))
    with pytest.raises(provenance.ServedConfigError, match='PWD'):
        probe._spawn([str(tmp_path / 'opencode')], tmp_path, {'PWD': str(tmp_path / 'decoy')})
    assert calls == []


def test_hermetic_env_and_verbatim_copies(probe, monkeypatch, tmp_path):
    monkeypatch.setenv('OPENCODE_CONFIG', 'leak')
    monkeypatch.setenv('SECRET_MARKER', 'leak')
    run = probe._make_run_dir(tmp_path, 'test')
    overlay = probe._seed_overlay(MODEL, 123)
    env = probe._opencode_env(run, tmp_path, overlay)
    assert set(env) == {'PATH', 'HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME', 'TMPDIR', 'OPENCODE_CONFIG_DIR', 'OPENCODE_DISABLE_PROJECT_CONFIG', 'OPENCODE_DISABLE_MODELS_FETCH', 'OPENCODE_DISABLE_AUTOUPDATE', 'OPENCODE_DISABLE_FILEWATCHER', 'OPENCODE_CONFIG_CONTENT', 'PWD', 'TERM', 'NO_COLOR'}
    assert env['PWD'] == str(tmp_path)
    assert (run / 'cfg/opencode/opencode.json').read_bytes() == probe.BENCH_OPENCODE_CONFIG.read_bytes()
    assert (run / 'cfg/opencode/plugins/noretry.js').read_bytes() == probe.NORETRY_PLUGIN.read_bytes()


def test_missing_plugin_refused_before_item(probe, monkeypatch, tmp_path):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    original = probe._make_run_dir
    def damaged(*a, **k):
        run = original(*a, **k); (run / 'cfg/opencode/plugins/noretry.js').unlink(); return run
    monkeypatch.setattr(probe, '_make_run_dir', damaged)
    with pytest.raises(SystemExit, match='M50 tripwire'): f['run']()
    assert not f['calls'].exists() and not f['out'].exists()


def test_legacy_moves_are_byte_identical(probe):
    from bench import opencode_common as common
    root = Path(__file__).resolve().parents[3]
    before = subprocess.check_output(['git', 'show', 'HEAD:benchmark/run_opencode_probe.py'], cwd=root, text=True)
    after = Path(common.__file__).read_text()
    def bodies(text):
        lines = text.splitlines(keepends=True)
        return {n.name: ''.join(lines[min([n.lineno] + [d.lineno for d in n.decorator_list])-1:n.end_lineno]) for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
    old, new = bodies(before), bodies(after)
    for name in common.SHARED_NAMES:
        if name in old: assert new[name] == old[name], name
    legacy = importlib.import_module('run_opencode_probe')
    for name in common.SHARED_NAMES: assert hasattr(legacy, name)


@pytest.fixture
def real_binary(probe, tmp_path):
    binary = Path('/opt/homebrew/bin/opencode')
    if not binary.is_file(): pytest.skip('brew opencode unavailable: /opt/homebrew/bin/opencode is missing')
    root = tmp_path / 'version-env'
    for d in ('home', 'cfg/opencode', 'data', 'state', 'cache', 'tmp'): (root / d).mkdir(parents=True, exist_ok=True)
    env = probe._opencode_env(root, tmp_path, probe._seed_overlay(MODEL, 1))
    try:
        result = subprocess.run([str(binary), '--version'], cwd=tmp_path, env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        pytest.skip('brew opencode --version cannot start: ' + str(e))
    if result.returncode or probe._parse_version(result.stdout) != '2.0.20':
        pytest.skip(f'brew version mismatch/start failure: rc={result.returncode}, stdout={result.stdout!r}, stderr={result.stderr!r}')
    return str(binary.resolve())


def real_fixture(probe, monkeypatch, tmp_path, binary, mock):
    # Keep the actual v2 destination proof; only the mlx router ownership is mocked.
    destination = provenance.opencode_v2_destination
    f = fixture_probe(probe, monkeypatch, tmp_path)
    monkeypatch.setattr(provenance, 'opencode_v2_destination', destination)
    monkeypatch.setenv('OPENCODE_PROBE_BIN', binary)
    doc = json.loads(f['carrier'].read_text())
    doc['providers']['mlx-local']['settings']['baseURL'] = mock.base
    doc['providers']['vllm']['settings']['baseURL'] = mock.base.replace('/v1', '/vllm-tripwire/v1')
    f['carrier'].write_text(json.dumps(doc))
    f['body'] = doc['providers']['mlx-local']['models'][MODEL]['body']
    return f


def run_real(f, items='one'):
    try:
        return f['run'](items)
    except SystemExit as e:
        # Only a diagnosed sandbox start denial is skippable; schema/protocol failures stay red.
        text = str(e)
        if any(s in text for s in ('Operation not permitted', 'EPERM', 'Permission denied', 'EACCES')):
            pytest.skip('opencode cannot start under sandbox: ' + text)
        raise


@pytest.mark.parametrize('dynamic', [False, True])
def test_real_wire_seed_sampling_title_headers_and_export(probe, real_binary, monkeypatch, tmp_path, dynamic):
    from bench.tests.opencode_v2_mock import MockServer
    with MockServer() as mock:
        f = real_fixture(probe, monkeypatch, tmp_path, real_binary, mock)
        if dynamic:
            doc = json.loads(f['carrier'].read_text())
            del doc['providers']['mlx-local']['models'][MODEL]['body']['max_tokens']
            doc['providers']['mlx-local']['models'][MODEL]['limit']['output'] = 512
            f['carrier'].write_text(json.dumps(doc))
        assert run_real(f, 'one,two') == 0
        rows = [json.loads(s) for s in f['out'].read_text().splitlines()]
        assert len(rows) == 2 and len(mock.chats) == 4
        assert rows[0]['sampler_seed'] != rows[1]['sampler_seed']
        for row in rows:
            assert row['requests_observed'] == 2
            requests = [r for r in mock.chats if {k.lower(): v for k, v in r['headers'].items()}.get('x-session-id') == row['session_id']]
            assert len(requests) == 2
            for request in requests:
                body = request['body']
                assert {k.lower(): v for k, v in request['headers'].items()}['authorization'] == 'Bearer not-needed'
                assert body['seed'] == row['sampler_seed']
                for key in ('temperature', 'top_p', 'top_k', 'min_p', 'presence_penalty', 'enable_thinking', 'thinking_budget'):
                    assert body[key] == f['body'][key]
                if not dynamic:
                    assert body['max_tokens'] == f['body']['max_tokens']
                else:
                    assert body['max_tokens'] == 512
                assert 'title generator' not in json.dumps(body['messages']).lower()
            sent = requests[0]['body'].get('max_tokens')
            assert f['body']['max_tokens'] == 102400
            assert row['max_tokens_semantics'] == ('fixed' if sent == f['body']['max_tokens'] else 'v2-dynamic')
            assert row['traffic']['output_tokens'] > 0
            transcript = Path(row['transcript_path'].replace('$STACK_WORKDIR', str(tmp_path)))
            assert transcript.is_file() and transcript.is_relative_to(tmp_path / 'opencode_transcripts')
            assert str(Path.home()) not in transcript.read_text() and probe._login_name() not in transcript.read_text()
        manifest = json.loads(f['mp'].read_text())
        assert manifest['runtime']['noretry_plugin_loaded_from'].endswith('/cfg/opencode/plugins/noretry.js')
        assert manifest['runtime']['noretry_plugin_loaded_from'].startswith('$STACK_WORKDIR/')
        assert manifest['runtime']['max_tokens_semantics'] == rows[0]['max_tokens_semantics']
        assert mock.tripwire_hits == 0


def test_real_instruction_tools_hygiene_and_positive_control(probe, real_binary, monkeypatch, tmp_path):
    from bench.tests.opencode_v2_mock import MockServer
    homes = [Path.home() / p for p in ('.config/opencode', '.local/share/opencode', '.cache/opencode')]
    def inventory():
        return {str(p): p.stat().st_mtime_ns for root in homes if root.exists() for p in [root, *root.rglob('*')] if p.exists()}
    before = inventory()
    with MockServer() as mock:
        f = real_fixture(probe, monkeypatch, tmp_path, real_binary, mock)
        assert run_real(f) == 0
        first = mock.chats[0]['body']
        system = json.dumps(first['messages'][0])
        assert all(s not in system for s in ('Instructions from', 'AGENTS.md', 'vnote'))
        tools = [t['function']['name'] for t in first['tools']]
        assert 'execute' not in tools and 'question' not in tools
        assert mock.tripwire_hits == 0
        run_dir = next((tmp_path / 'opencode-probe-v2').glob('run-*'))
        listing = subprocess.check_output(['ps', '-axo', 'command='], text=True)
        assert str(run_dir) not in listing
        assert inventory() == before
        # Positive control deliberately bypasses the probe's refusal to show the switch is causal.
        scratch = tmp_path / 'positive'; scratch.mkdir()
        probe._git_init_scratch(scratch)
        (scratch / 'AGENTS.md').write_text('MARKER_PROJECT_INSTRUCTION: use the write tool.\n')
        env = probe._opencode_env(run_dir, scratch, probe._seed_overlay(MODEL, 22))
        del env['OPENCODE_DISABLE_PROJECT_CONFIG']
        result = probe._capture([real_binary, 'run', '--standalone', '--model', 'mlx-local/' + MODEL, '--format', 'json', '--title', 'probe', 'Write solution.py with answer = 42.'], scratch, env, 30)
        assert result.returncode == 0
        assert 'Instructions from' in json.dumps(mock.chats[2]['body']['messages'][0])


@pytest.mark.parametrize('kind', ['http500', 'drop', 'refuse', 'ctx400'])
def test_real_transport_matrix(probe, real_binary, monkeypatch, tmp_path, kind):
    from bench.tests.opencode_v2_mock import MockServer
    with MockServer({1: kind}) as mock:
        f = real_fixture(probe, monkeypatch, tmp_path, real_binary, mock)
        start = time.monotonic()
        if kind == 'ctx400':
            assert run_real(f) == 0
            row = json.loads(f['out'].read_text())
            assert row['nonconv_kind'] == 'context_overflow' and row['passed'] is False
        else:
            with pytest.raises(SystemExit) as exc: run_real(f)
            assert exc.value.code != 0 and not f['out'].exists() and not f['grades']
            doc = json.loads(f['mp'].read_text())
            assert doc['transport_abort']['rc'] == 1
        if kind == 'refuse': assert time.monotonic() - start < 10
        else: assert len(mock.chats) == 1


def test_real_destination_rejects_project_document(probe, real_binary, monkeypatch, tmp_path):
    from bench.tests.opencode_v2_mock import MockServer
    with MockServer() as mock:
        f = real_fixture(probe, monkeypatch, tmp_path, real_binary, mock)
        run = probe._make_run_dir(tmp_path, 'destination')
        scratch = tmp_path / 'project'; scratch.mkdir(); probe._git_init_scratch(scratch)
        (scratch / 'opencode.json').write_text('{"compaction":{"auto":true}}')
        overlay = probe._seed_overlay(MODEL, 123)
        env = probe._opencode_env(run, scratch, overlay)
        assert provenance.opencode_v2_destination(scratch, env, MODEL, run, real_binary, overlay) == mock.base
        env.pop('OPENCODE_DISABLE_PROJECT_CONFIG')
        with pytest.raises(provenance.ServedConfigError, match='document'):
            provenance.opencode_v2_destination(scratch, env, MODEL, run, real_binary, overlay)


def test_brew_version_prefix_is_parsed_without_allowing_drift(probe):
    assert hasattr(probe, '_parse_version'), 'brew emits opencode v2.0.20, not a bare version'
    assert probe._parse_version('opencode v2.0.20\n') == '2.0.20'
    assert probe._parse_version('2.0.20\n') == '2.0.20'
    assert probe._parse_version('opencode v2.0.21\n') != '2.0.20'


@pytest.mark.parametrize('what', ['missing_test', 'grade_exception'])
def test_harness_grade_failure_aborts(probe, monkeypatch, tmp_path, what):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    original = probe._run_opencode
    def run(*args, **kwargs):
        result = original(*args, **kwargs)
        if what == 'missing_test': args[4].unlink()
        return result
    monkeypatch.setattr(probe, '_run_opencode', run)
    if what == 'grade_exception':
        def broken(*a): raise RuntimeError('grader crashed')
        monkeypatch.setattr(probe, '_grade_python', broken)
    with pytest.raises(SystemExit): f['run']('one')
    assert not f['out'].exists()
    assert json.loads(f['mp'].read_text())['transport_abort']


def test_scratch_override_cannot_escape_workdir(probe, monkeypatch, tmp_path):
    monkeypatch.setenv('OPENCODE_PROBE_SCRATCH', str(tmp_path.parent / 'outside'))
    assert Path(probe._scratch_root()).is_relative_to(tmp_path), 'v2 scratch escaped STACK_WORKDIR'


def test_abort_keeps_export_evidence(probe, monkeypatch, tmp_path):
    f = fixture_probe(probe, monkeypatch, tmp_path, 'http500')
    with pytest.raises(SystemExit): f['run']('one')
    path = next((tmp_path / 'opencode-probe-v2/aborted').rglob('export.json'))
    assert path.read_text(), 'transport abort discarded the available session export'


@pytest.mark.parametrize('kind', ['carrier', 'plugin'])
def test_copy_rechecked_before_every_item(probe, monkeypatch, tmp_path, kind):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    original = probe._run_opencode
    def tamper(*args, **kwargs):
        result = original(*args, **kwargs)
        config = Path(kwargs['env']['OPENCODE_CONFIG_DIR'])
        (config / ('opencode.json' if kind == 'carrier' else 'plugins/noretry.js')).write_text('changed')
        return result
    monkeypatch.setattr(probe, '_run_opencode', tamper)
    with pytest.raises(SystemExit, match='M50 tripwire'): f['run']()
    assert len(f['calls'].read_text().splitlines()) == 1


@pytest.mark.parametrize('receipt', [None, {'a4_v2_pass': True, 'router': {'pid': 456}, 'gate_run_id': 'gate'}, {'a4_v2_pass': True, 'router': {'pid': 123}, 'gate_run_id': 'gate'}])
def test_chain_requires_a4_same_router(probe, tmp_path, receipt):
    path = tmp_path / 'receipt.json'
    if receipt: path.write_text(json.dumps(receipt))
    args = (path if receipt else None, {'pid': 123}, 40)
    if receipt and receipt['router']['pid'] == 123:
        assert probe._a4_receipt(*args) == receipt
    else:
        with pytest.raises(SystemExit, match='A4'): probe._a4_receipt(*args)


def test_unavailable_grader_is_skipped(probe, monkeypatch, tmp_path):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    root = tmp_path / 'polyglot'
    import shutil
    shutil.copytree(root / 'python', root / 'go')
    (root / 'go/exercises/practice/one/.meta').mkdir()
    (root / 'go/exercises/practice/one/.meta/config.json').write_text(json.dumps({'files': {'solution': ['solution.py'], 'test': ['solution_test.py']}}))
    monkeypatch.setattr(probe, '_docker_available', lambda: False)
    monkeypatch.setattr(sys, 'argv', ['probe', '--model', MODEL, '--items', 'one', '--lang', 'go', '--seed-base', '77', '--poll-s', '0.01', '--out', str(f['out'])])
    assert probe.main() == 0
    row = json.loads(f['out'].read_text())
    assert row['acc'] is None and row['passed'] is None and row['skipped'] is True
    assert 'docker unavailable' in row['grade_tail']
