"""Cold-verification regressions; CPU fakes and local files only."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench.answer_key import report_rows
from bench.tests.test_opencode_v2_probe import probe, fixture_probe, MODEL
from bench.tests.test_session_pinning_a4_v2 import gate, FakeLogTail, row
from bench.tests.test_m61_p201 import fixture_rows


def part(name, inputs=None, *, content=None, rejected=False):
    state = {'input': inputs or {}, 'status': 'error' if rejected else 'completed',
             'content': content}
    if rejected:
        state['error'] = {'type': 'permission.rejected', 'message': 'Permission rejected: fixture'}
    return {'type': 'tool', 'name': name, 'state': state}


def capture(probe, tmp_path, monkeypatch, *parts):
    monkeypatch.setenv('STACK_WORKDIR', str(tmp_path))
    return probe._web_audit({'messages': [{'content': list(parts)}]}, tmp_path,
                            tmp_path / 'opencode_transcripts/round4/item.json')


@pytest.mark.parametrize('scaffold', ['opencode-v2', 'opencode-v2-web'])
def test_subagent_count_and_incomplete_row(probe, tmp_path, monkeypatch, scaffold):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    export = tmp_path / 'export.json'
    doc = json.loads(export.read_text())
    doc['messages'][0]['content'] += [part('subagent'), part('subagent')]
    export.write_text(json.dumps(doc))
    assert f['run']('one', extra=['--scaffold', scaffold]) == 0
    result = json.loads(f['out'].read_text())
    assert result['subagent_calls'] == 2
    assert bool(result.get('web_audit_incomplete')) == (scaffold == 'opencode-v2-web')
    assert report_rows([result])['strict_n'] == (scaffold == 'opencode-v2')


@pytest.mark.parametrize('scaffold,system', [
    ('opencode-v2', None), ('opencode-v2-web', None),
    ('opencode-v2', 'benchmark/opencode_prompts/system.txt')])
def test_a4_receipt_matches_probe_written_carrier(gate, probe, tmp_path, monkeypatch, scaffold, system):
    module, binary, carrier = gate
    web = carrier.with_name('opencode_bench_v2_web.json')
    doc = json.loads(carrier.read_text())
    doc['permissions'] = [{'action': 'webfetch', 'resource': '*', 'effect': 'allow'}]
    web.write_text(json.dumps(doc))
    if system:
        target = module.REPO / system
        target.parent.mkdir()
        target.write_text('Round four system fixture.')
    monkeypatch.setattr(probe, 'REPO', module.REPO)
    monkeypatch.setattr(probe, 'BENCH_OPENCODE_CONFIG', carrier)
    monkeypatch.setattr(probe, 'BENCH_OPENCODE_WEB_CONFIG', web)
    selection = probe._carrier_selection(scaffold, system)
    run = probe._make_run_dir(tmp_path, 'round4', selection)
    result = module.a4_opencode(MODEL, FakeLogTail([row()], [row()]), tmp_path, 10,
                               str(binary), scaffold=scaffold, agent_system_file=system)
    assert result['pass'] is True
    assert result['carrier_sha256'] == hashlib.sha256((run / 'cfg/opencode/opencode.json').read_bytes()).hexdigest()


WEB_MARKERS = [{'scaffold': 'opencode-v2-web'}, {'scaffold': 'opencode-v2-web+sys:12345678'},
               {'web_fetches': []}, {'net_shell': []}, {'web_denied': 0},
               {'answer_key_contact': False}, {'answer_key_evidence': []},
               {'web_audit_incomplete': False}, {'web_audit_error': ''}, {'subagent_calls': 0}]


@pytest.mark.parametrize('marker', WEB_MARKERS)
def test_compare_refuses_web_audit_rows(write_rows, tmp_results, marker):
    from bench import compare
    from bench.tests.test_compare import _rows, _manifest
    models = [MODEL, 'Qwen3.8-27B-mlx-uniform-4bit']
    for model in models:
        write_rows(model, 'math500', [{**r, **marker} for r in _rows(['one'])])
        _manifest(tmp_results, model, 'math500')
    result = compare.compare(*models, 'math500', metric='acc_strict')
    assert result['comparable'] is False
    assert 'report_rows' in result['reason'] and 'web' in result['reason']


@pytest.mark.parametrize('marker', WEB_MARKERS)
def test_scoreboard_refuses_web_audit_rows(tmp_path, monkeypatch, marker):
    from m1 import scoreboard
    monkeypatch.setattr(scoreboard.paths, 'default_results_root', lambda: tmp_path)
    dest = tmp_path / MODEL / 'opencode.jsonl'
    dest.parent.mkdir()
    dest.write_text(json.dumps({'id': 'python/one', 'passed': True, **marker}) + '\n')
    dest.with_suffix('.score.json').write_text('{"acc":1,"acc_strict":1}')
    with pytest.raises(ValueError, match='web.*report_rows'):
        scoreboard.collect()


def test_auditor_hermetic_flags(tmp_path, monkeypatch):
    import web_audit as audit
    monkeypatch.setenv('STACK_WORKDIR', str(tmp_path))
    def run(argv, **kwargs):
        assert argv[:9] == ['codex', 'exec', '--ephemeral', '--ignore-user-config',
                            '-m', 'gpt-6-astra', '-s', 'read-only', '--skip-git-repo-check']
        Path(argv[argv.index('-o') + 1]).write_text('{"label":"docs","reason":"Reference."}')
    monkeypatch.setattr(audit.subprocess, 'run', run)
    audit.codex_auditor('fixture')


def test_auditor_version_records_and_idempotence(tmp_path, monkeypatch):
    import web_audit as audit
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    version = ['codex-cli 0.161.0']
    def run(argv, **kwargs):
        assert argv == ['codex', '--version']
        assert kwargs['check'] and kwargs['timeout'] > 0
        return SimpleNamespace(stdout=version[0] + '\n')
    monkeypatch.setattr(audit.subprocess, 'run', run)
    calls = []
    def fake(prompt):
        calls.append(prompt)
        return '{"label":"docs","reason":"Reference."}'
    sidecar = audit.audit_rows(path, polyglot_root=corpus, auditor=fake)
    records = [json.loads(line) for line in sidecar.read_text().splitlines()]
    assert all(r['auditor_version'] == version[0] for r in records)
    audit.audit_rows(path, polyglot_root=corpus, auditor=fake)
    assert len(calls) == 3
    version[0] = 'codex-cli 0.162.0'
    audit.audit_rows(path, polyglot_root=corpus, auditor=fake)
    assert len(calls) == 6
    assert report_rows(rows, audit_sidecar=sidecar)['strict_n'] == 3


def test_web_denied_only_network_rejections_with_messages(probe, tmp_path, monkeypatch):
    result = capture(probe, tmp_path, monkeypatch,
                     part('shell', {'command': 'cat exercism.txt'}, rejected=True),
                     part('webfetch', {'url': 'https://fixture.invalid'}, rejected=True),
                     part('shell', {'command': 'curl https://fixture.invalid'}, rejected=True))
    assert result['web_denied'] == 2
    for entry in result['web_fetches'] + result['net_shell']:
        assert entry['error']['message'] == 'Permission rejected: fixture'


@pytest.mark.parametrize('failure', [OSError('disk unavailable'), RuntimeError('detector failure')])
def test_web_audit_exception_does_not_abort_leg(probe, tmp_path, monkeypatch, failure):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    def fail(*args):
        raise failure
    monkeypatch.setattr(probe.answer_key, 'contact', fail)
    assert f['run']() == 0
    results = [json.loads(line) for line in f['out'].read_text().splitlines()]
    assert len(results) == 2
    assert all(isinstance(r['web_audit_error'], str) and str(failure) in r['web_audit_error'] for r in results)
    assert report_rows(results)['strict_n'] == 0


def test_web_audit_surrogates_and_null_content(probe, tmp_path, monkeypatch):
    result = capture(probe, tmp_path, monkeypatch,
                     part('webfetch', content='\ud800'), part('webfetch'),
                     {'type': 'tool', 'name': 'webfetch', 'state': {'status': 'completed'}})
    assert not result.get('web_audit_error')
    entries = result['web_fetches']
    assert [e['bytes'] for e in entries] == [3, 0, 0]
    assert entries[0]['sha256'] == hashlib.sha256('\ud800'.encode(errors='surrogatepass')).hexdigest()


def test_preflag_methods_and_small_identifier_sets(tmp_path):
    import web_audit as audit
    (tmp_path / 'stub.py').write_text('class Public:\n def __init__(self): pass\n def method(self): pass\n async def next(self): pass\n')
    assert audit.public_identifiers(tmp_path, 'python') == ['Public', 'method', 'next']
    (tmp_path / 'stub.go').write_text('package fixture\ntype Public struct{}\nfunc (p Public) Method() {}\n')
    assert audit.public_identifiers(tmp_path, 'go') == ['Method', 'Public']
    for names in (['Public'], ['Public', 'method'], ['Public', 'method', 'next']):
        assert audit.preflag('class Public:\n def method(self): return self.next()', 'python', names)
    assert not audit.preflag('class Public: pass', 'python', [])
    assert not audit.preflag('class Public: pass', 'python', ['Public', 'missing'])


NETWORK_COMMANDS = ['pip install pkg', 'pip3 download pkg', 'uv pip install pkg', 'uv add pkg',
                    'go get pkg', 'go install pkg', 'cargo add pkg', 'cargo install pkg',
                    'npx pkg', 'gh api repos', 'brew install pkg', 'git clone repo',
                    'git fetch origin', 'git pull origin']


@pytest.mark.parametrize('command', NETWORK_COMMANDS)
def test_network_package_commands_captured(probe, tmp_path, monkeypatch, command):
    result = capture(probe, tmp_path, monkeypatch, part('shell', {'command': command}, content='output'))
    assert result['net_shell'][0]['command'] == command


@pytest.mark.parametrize('output', ['-o result', '-O', '--output=result', '> result', '>> result', '| tee result'])
def test_network_output_file_incomplete(probe, tmp_path, monkeypatch, output):
    result = capture(probe, tmp_path, monkeypatch,
                     part('shell', {'command': 'curl https://fixture.invalid ' + output}, content=''))
    assert result['web_audit_incomplete'] is True
    assert report_rows([{'id': 'python/one', 'passed': True, **result}])['strict_n'] == 0


def test_retry_errors_uses_latest_record(tmp_path, monkeypatch):
    import web_audit as audit
    path, corpus, _ = fixture_rows(tmp_path, monkeypatch)
    monkeypatch.setattr(audit.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout='codex-cli 0.161.0\n'))
    def fail(_):
        raise OSError('offline fixture')
    sidecar = audit.audit_rows(path, polyglot_root=corpus, auditor=fail)
    records = [json.loads(line) for line in sidecar.read_text().splitlines()]
    with sidecar.open('a') as stream:
        stream.write(json.dumps({**records[0], 'label': 'docs', 'reason': 'Now resolved.'}) + '\n')
    calls = []
    def fake(prompt):
        calls.append(prompt)
        return '{"label":"docs","reason":"Reference."}'
    audit.audit_rows(path, polyglot_root=corpus, auditor=fake)
    assert not calls
    audit.audit_rows(path, polyglot_root=corpus, auditor=fake, retry_errors=True)
    assert len(calls) == 2
    audit.audit_rows(path, polyglot_root=corpus, auditor=fake, retry_errors=True)
    assert len(calls) == 2


def test_retry_errors_cli(tmp_path, monkeypatch):
    import web_audit as audit
    import sys
    calls = []
    monkeypatch.setattr(sys, 'argv', ['web_audit.py', str(tmp_path / 'rows.jsonl'), '--retry-errors'])
    monkeypatch.setattr(audit, 'audit_rows', lambda *a, **k: calls.append(k) or tmp_path)
    audit.main()
    assert calls[0]['retry_errors'] is True
