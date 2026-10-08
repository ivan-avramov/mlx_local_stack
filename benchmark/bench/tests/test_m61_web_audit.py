"""M61 acceptance: legacy identity, web capture, system overlay, leakage and resume."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench.tests.test_opencode_v2_probe import (
    probe, real_binary, fixture_probe, real_fixture, MODEL,
)
from bench.tests.opencode_v2_mock import MockServer

FIXTURES = Path(__file__).parent / 'fixtures'
SYSTEM = 'benchmark/opencode_prompts/opencode-1.18.15-default.txt'
FIELDS = ('scaffold', 'carrier_source', 'carrier_source_sha256', 'agent_system_file',
          'agent_system_sha256', 'opencode_bench_config_sha256')


def test_m59_identity_recipe_and_carrier_bytes(probe, tmp_path):
    fixture = json.loads((FIXTURES / 'm59_policy.json').read_text())
    binary = tmp_path / 'binary'
    binary.write_bytes(b'M59 fixed executable fixture\n')
    selection = probe._carrier_selection('opencode-v2', None)
    run = probe._make_run_dir(tmp_path, 'legacy', selection)
    written = (run / 'cfg/opencode/opencode.json').read_bytes()
    assert written == probe.BENCH_OPENCODE_CONFIG.read_bytes()
    assert hashlib.sha256(written).hexdigest() == fixture['policy']['opencode_bench_config_sha256']
    a = SimpleNamespace(seed_base=77, lang='python', tick_s=10, hard_ceiling_s=3600,
                        stall_ticks=2, loop_repeats=3, poll_s=5, carrier_selection=selection,
                        gate_window=dict(first_write_tokens=48000, decode_tok_s=24,
                                         decode_tok_s_source='fixture', first_write_window_s=20))
    identity = probe._identity(a, '2.0.20', binary, run, 'fixture-polyglot')
    assert {k: identity[k] for k in fixture['policy']} == fixture['policy']
    assert identity['scaffold_policy_sha256'] == fixture['scaffold_policy_sha256']


@pytest.mark.parametrize('scaffold', ['opencode-v2', 'opencode-v2-web'])
@pytest.mark.parametrize('system', [None, SYSTEM])
def test_identity_fields_on_manifest_and_every_row(probe, monkeypatch, tmp_path, scaffold, system):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    args = ['--scaffold', scaffold] + (['--agent-system-file', system] if system else [])
    assert f['run'](extra=args) == 0
    runtime = json.loads(f['mp'].read_text())['runtime']
    rows = [json.loads(line) for line in f['out'].read_text().splitlines()]
    for row in rows:
        assert {k: row[k] for k in FIELDS} == {k: runtime[k] for k in FIELDS}
        assert row['scaffold'].startswith(scaffold)
        assert ('+sys:' in row['scaffold']) == bool(system)
        assert row['web_fetches'] == [] and row['net_shell'] == [] and row['web_denied'] == 0
        assert row['answer_key_contact'] is False
    policy = json.loads((FIXTURES / 'm59_policy.json').read_text())['policy']
    expected = {k: runtime[k] for k in policy}
    if scaffold == 'opencode-v2-web' or system:
        expected.update({k: runtime[k] for k in FIELDS})
    assert runtime['scaffold_policy_sha256'] == hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()


@pytest.mark.parametrize('scaffold', ['opencode-v2', 'opencode-v2-web'])
@pytest.mark.parametrize('key', FIELDS)
def test_resume_checks_every_new_field(probe, monkeypatch, tmp_path, scaffold, key):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    args = ['--scaffold', scaffold]
    assert f['run']('one', extra=args) == 0
    man = json.loads(f['mp'].read_text())
    man['runtime'][key] = 'changed'
    f['mp'].write_text(json.dumps(man))
    calls = f['calls'].read_text()
    with pytest.raises(SystemExit, match='resume identity ' + key):
        f['run'](extra=args)
    assert f['calls'].read_text() == calls


@pytest.mark.parametrize('path', ['/tmp/outside.txt', '../outside.txt', 'README.md',
                                  'benchmark/opencode_prompts/../../README.md'])
def test_system_path_refuses_before_spawn(probe, monkeypatch, tmp_path, path):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(probe, '_spawn', lambda *a, **k: calls.append(a))
    with pytest.raises(SystemExit, match='agent-system-file'):
        f['run'](extra=['--agent-system-file', path])
    assert calls == []


def test_detector_known_positive_and_negatives():
    from bench.answer_key import contact
    item = FIXTURES / 'answer_key/matrix'
    positive = contact(item, [{'source': 'matrix fetch', 'text': (FIXTURES / 'known_positive_go_matrix_fetch.txt').read_text()}])
    assert positive['flag']
    assert positive['evidence'][0]['matched_lines'] == 31
    assert positive['evidence'][0]['reference_lines'] == 32
    assert positive['evidence'][0]['run_length'] == 31
    for file in [item / 'matrix.go', item / 'matrix_test.go', FIXTURES / 'answer_key/other.go']:
        result = contact(item, [{'source': file.name, 'text': file.read_text()}])
        assert result['flag'] is False, result
        print(file.name, json.dumps(result))
    print('positive', json.dumps(positive))


def test_report_excludes_flagged_rows_without_changing_grades():
    from bench.answer_key import report_rows
    rows = [{'id': 'clean-pass', 'passed': True}, {'id': 'clean-dnf', 'passed': False},
            {'id': 'leak', 'passed': True, 'answer_key_contact': True}]
    report = report_rows(rows)
    assert report['acc_strict'] == 0.5
    assert report['strict_n'] == 2
    assert report['flagged: answer-key contact'] == 1
    assert report['strict_items'] == {'clean-pass': [1], 'clean-dnf': [0]}
    assert rows[-1]['passed'] is True


@pytest.mark.parametrize('kind', ['allowed', 'denied-fetch', 'denied-shell'])
def test_real_web_capture(probe, real_binary, monkeypatch, tmp_path, kind):
    with MockServer() as site:
        url = site.base + ('/docs' if kind == 'allowed' else '/exercism/x')
        tool = {'name': 'shell', 'input': {'command': 'curl ' + url, 'description': 'fetch fixture'}} if kind == 'denied-shell' else {'name': 'webfetch', 'input': {'url': url, 'format': 'text'}}
        with MockServer({1: tool}) as mock:
            f = real_fixture(probe, monkeypatch, tmp_path, real_binary, mock)
            doc = json.loads(probe.BENCH_OPENCODE_WEB_CONFIG.read_text())
            doc['providers'] = json.loads(f['carrier'].read_text())['providers']
            web = tmp_path / 'web.json'; web.write_text(json.dumps(doc))
            monkeypatch.setattr(probe, 'BENCH_OPENCODE_WEB_CONFIG', web)
            original_export = probe._export_session
            def capture(*args, **kwargs):
                result = original_export(*args, **kwargs)
                print('CAPTURE', kind, json.dumps([p for m in result['messages'] for p in m.get('content', []) if p.get('type') == 'tool'], sort_keys=True))
                return result
            monkeypatch.setattr(probe, '_export_session', capture)
            assert f['run']('one', extra=['--scaffold', 'opencode-v2-web']) == 0
            row = json.loads(f['out'].read_text())
            transcript = Path(row['transcript_path'].replace('$STACK_WORKDIR', str(tmp_path)))
            export = json.loads(transcript.read_text())
            parts = [p for m in export['messages'] for p in m.get('content', []) if p.get('type') == 'tool']
            print(kind, json.dumps(parts, sort_keys=True))
            assert len(site.requests) == (1 if kind == 'allowed' else 0)
            assert row['web_denied'] == (0 if kind == 'allowed' else 1)
            if kind == 'denied-shell':
                assert row['net_shell'][0]['command'] == 'curl ' + url
                assert row['net_shell'][0]['status'] == 'denied'
            else:
                assert [{k: e[k] for k in ('url', 'status', 'bytes')} for e in row['web_fetches']] == [{'url': url, 'status': 'completed' if kind == 'allowed' else 'denied', 'bytes': len(b'{"status": "ok"}') if kind == 'allowed' else 0}]


def test_real_system_override(probe, real_binary, monkeypatch, tmp_path):
    with MockServer() as mock:
        f = real_fixture(probe, monkeypatch, tmp_path, real_binary, mock)
        assert f['run']('one', extra=['--agent-system-file', SYSTEM]) == 0
        system = '\n'.join(m['content'] for m in mock.chats[0]['body']['messages'] if m['role'] == 'system')
        assert system.startswith((probe.REPO / SYSTEM).read_text())
        assert 'Working directory:' in system
        assert "Today's date:" in system
        assert 'You are an AI agent running in OpenCode, a coding agent harness.' not in system
        run = next((tmp_path / 'opencode-probe-v2').glob('run-*'))
        doc = json.loads((run / 'cfg/opencode/opencode.json').read_text())
        assert doc['agents']['title']['disabled'] is True


def test_flagged_row_is_graded_retained_and_reported(probe, monkeypatch, tmp_path, capsys):
    from bench.answer_key import report_rows
    f = fixture_probe(probe, monkeypatch, tmp_path)
    item = tmp_path / 'polyglot/python/exercises/practice/one'
    (item / '.meta').mkdir()
    (item / '.meta/example.py').write_bytes((FIXTURES / 'answer_key/matrix/.meta/example.go').read_bytes())
    text = (FIXTURES / 'known_positive_go_matrix_fetch.txt').read_text()
    doc = json.loads(f['export'].read_text())
    doc['messages'][0]['content'].append({'type': 'tool', 'name': 'shell', 'state': {
        'input': {'command': 'curl https://mirror.invalid/reference'}, 'status': 'completed',
        'content': [{'type': 'text', 'text': text}]}})
    f['export'].write_text(json.dumps(doc))
    assert f['run']('one') == 0
    row = json.loads(f['out'].read_text())
    assert row['answer_key_contact'] is True and row['passed'] is True
    assert f['grades']
    assert 'python/one: flagged: answer-key contact' in capsys.readouterr().out
    assert report_rows([row])['acc_strict'] is None
    assert row['answer_key_evidence'][0]['source'] == 'curl https://mirror.invalid/reference'


def test_audit_bytes_errors_and_all_network_commands(probe, tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    parts = [
        {'type': 'tool', 'name': 'webfetch', 'state': {'status': 'completed',
         'input': {'url': 'https://docs.invalid'}, 'content': [{'type': 'text', 'text': 'é'},
         {'type': 'text', 'text': 'x'}]}},
        {'type': 'tool', 'name': 'webfetch', 'state': {'status': 'error',
         'input': {'url': 'https://error.invalid'},
         'error': {'type': 'tool.failure', 'message': 'permission denied by server'}}},
        {'type': 'tool', 'name': 'webfetch', 'state': {'status': 'error',
         'input': {'url': 'https://exercism.invalid'},
         'error': {'type': 'permission.rejected', 'message': 'Permission denied: webfetch'}}},
    ]
    commands = ['curl docs.invalid', 'wget docs.invalid', 'git clone repo', 'go get package',
                'pip download package', 'pip install package', 'npm view package',
                'npm install package', 'python fetch.py https://docs.invalid']
    for command in commands + ['echo scurlish']:
        parts.append({'type': 'tool', 'name': 'shell', 'state': {
            'status': 'completed', 'input': {'command': command}, 'content': []}})
    audit = probe._web_audit({'messages': [{'content': parts}]}, tmp_path,
                             tmp_path / 'opencode_transcripts/fixture/item.json')
    assert [{k: e[k] for k in ('url', 'status', 'bytes')} for e in audit['web_fetches']] == [
        {'url': 'https://docs.invalid', 'status': 'completed', 'bytes': 3},
        {'url': 'https://error.invalid', 'status': 'error', 'bytes': 0},
        {'url': 'https://exercism.invalid', 'status': 'denied', 'bytes': 0}]
    assert [e['command'] for e in audit['net_shell']] == commands
    assert audit['web_denied'] == 1


def test_detector_thresholds_recursive_references_and_comments(tmp_path):
    from bench.answer_key import contact, normalize
    reference = [f'unique_reference_line_{i:02}' for i in range(20)]
    meta = tmp_path / '.meta/nested'; meta.mkdir(parents=True)
    (meta / 'proof.txt').write_text('\n'.join(reference))
    (meta / 'ignored.txt').write_text('unrelated long reference')
    assert normalize('// long comment only\n/*\nlong comment body\n*/\n# another comment\nshort\n  real_source_line  ') == ['real_source_line']
    assert normalize('*long_pointer = value;') == ['*long_pointer = value;']
    def check(lines):
        return contact(tmp_path, [{'source': 'fixture', 'text': '\n'.join(lines)}])['flag']
    assert check(reference[:5])
    assert not check(reference[:4])
    assert check(reference[:16:2])  # exactly 40%, without a 5-line run
    assert not check(reference[:14:2])
    assert not check(['unrelated long reference'])


def test_default_scaffold_and_real_identity_changes(probe, monkeypatch, tmp_path):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    # fixture explicitly selects M59 for old tests; remove that selection to exercise the CLI default.
    original_parse = probe.argparse.ArgumentParser.parse_args
    def parse(parser, *args, **kwargs):
        import sys
        index = sys.argv.index('--scaffold')
        del sys.argv[index:index + 2]
        return original_parse(parser, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(probe.argparse.ArgumentParser, 'parse_args', parse)
        assert f['run']('one') == 0
    assert json.loads(f['out'].read_text())['scaffold'] == 'opencode-v2-web'
    with pytest.raises(SystemExit, match='resume identity scaffold'):
        f['run']()
    with pytest.raises(SystemExit, match='resume identity scaffold'):
        f['run'](extra=['--scaffold', 'opencode-v2-web', '--agent-system-file', SYSTEM])


def test_system_overlay_is_exact_and_keeps_other_agent_fields(probe):
    selection = probe._carrier_selection('opencode-v2', SYSTEM)
    old = json.loads(probe.BENCH_OPENCODE_CONFIG.read_bytes())
    old.setdefault('agents', {}).setdefault('build', {})['system'] = (probe.REPO / SYSTEM).read_bytes().decode()
    assert selection['bytes'] == json.dumps(old, sort_keys=True, indent=2).encode()
    assert selection['fields']['agent_system_sha256'] == hashlib.sha256((probe.REPO / SYSTEM).read_bytes()).hexdigest()
    assert selection['fields']['agent_system_sha256'] == '962fbf3cb3ec659c9a5244425ee2e7bb141ad4428f489a630a7738566880dc6a'


def test_system_symlink_escape_refuses_before_spawn(probe, monkeypatch, tmp_path):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    repo = tmp_path / 'repo'
    prompts = repo / 'benchmark/opencode_prompts'; prompts.mkdir(parents=True)
    outside = tmp_path / 'outside.txt'; outside.write_text('external prompt')
    (prompts / 'escape.txt').symlink_to(outside)
    monkeypatch.setattr(probe, 'REPO', repo)
    calls = []
    monkeypatch.setattr(probe, '_spawn', lambda *a, **k: calls.append(a))
    with pytest.raises(SystemExit, match='agent-system-file'):
        f['run'](extra=['--agent-system-file', 'benchmark/opencode_prompts/escape.txt'])
    assert not calls
