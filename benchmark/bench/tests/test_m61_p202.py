"""P202 offline cheat recovery acceptance."""
import hashlib
import json
from pathlib import Path

import pytest

from bench import answer_key, provenance
from bench.tests.test_opencode_v2_probe import probe, fixture_probe, real_binary, real_fixture, MODEL
from bench.tests.test_session_pinning_a4_v2 import gate, FakeLogTail, row as log_row
from bench.tests.opencode_v2_mock import MockServer
import web_audit


@pytest.fixture(autouse=True)
def fake_auditor_version(monkeypatch):
    monkeypatch.setattr(web_audit, 'auditor_version', lambda: 'fake')


def write_rows(path, rows):
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))


def decision(path, row, label, kind='web_fetches'):
    e = row[kind][0]
    record = dict(row_id=row['id'], sample=0, session_id=row['session_id'], kind=kind, index=0,
                  path=e.get('path'), sha256=e.get('sha256'), bytes=e.get('bytes'), label=label,
                  auditor=web_audit.AUDITOR, auditor_version='fake',
                  prompt_sha256=hashlib.sha256(web_audit.PROMPT.read_bytes()).hexdigest())
    with Path(str(path) + '.webaudit.jsonl').open('a') as f:
        f.write(json.dumps(record) + '\n')


def attempt(session, **kw):
    return dict(id='python/one', model=MODEL, sample=0, session_id=session,
                sampler_seed=123, passed=True, **({'scaffold': 'opencode-v2-web'} | kw))


def test_partial_and_prompt_revision():
    assert web_audit.parse_answer('{"label":"partial","reason":"Only an algorithm hint."}')['label'] == 'partial'
    prompt = web_audit.PROMPT.read_text()
    assert 'near-complete' in prompt and 'required API' in prompt and 'not a working answer' in prompt


@pytest.mark.parametrize('url,expected', [
    ('https://GitHub.com/Owner/Repo/blob/main/a.py?q=1', [
        '*github.com/owner/repo', '*github.com/Owner/Repo/*',
        '*raw.githubusercontent.com/owner/repo/*', '*raw.githubusercontent.com/Owner/Repo/*']),
    ('https://raw.githubusercontent.com/Owner/Repo/main/a.py', [
        '*github.com/owner/repo', '*github.com/Owner/Repo/*',
        '*raw.githubusercontent.com/owner/repo/*', '*raw.githubusercontent.com/Owner/Repo/*']),
    ('https://RAW.GITHUBUSERCONTENT.COM/OWNER/REPO/main/a.py', [
        '*raw.githubusercontent.com/OWNER/REPO/*',
        '*raw.githubusercontent.com/owner/repo/*', '*github.com/owner/repo']),
    ('https://GitLab.com/Owner/Repo/-/blob/main/a.py', [
        '*gitlab.com/owner/repo', '*gitlab.com/Owner/Repo/*']),
    ('https://Docs.invalid/topic/answer.html?q=1', [
        '*docs.invalid/topic/answer.html', '*Docs.invalid/topic/answer.html',
        '*docs.invalid/topic/answer.html#*']),
])

def test_deny_patterns(url, expected):
    patterns = answer_key.deny_patterns_for([url, url])
    assert set(expected) <= set(patterns)
    assert len(patterns) == len(set(patterns))


def test_extra_deny_composition_and_m50(probe, tmp_path):
    deny = tmp_path / 'deny.json'
    deny.write_text(json.dumps(['https://fixture.invalid/repo/*']))
    selected = probe._carrier_selection('opencode-v2-web', None, extra_deny_file=deny)
    original = json.loads(probe.BENCH_OPENCODE_WEB_CONFIG.read_bytes())
    expected = original['permissions'] + [
        dict(action='webfetch', resource='https://fixture.invalid/repo/*', effect='deny'),
        dict(action='shell', resource='*https://fixture.invalid/repo/*', effect='deny')]
    assert json.loads(selected['bytes'])['permissions'] == expected
    assert selected['fields']['extra_deny'] == json.loads(deny.read_text())
    assert selected['fields']['extra_deny_sha256'] == hashlib.sha256(deny.read_bytes()).hexdigest()
    assert selected['fields']['scaffold'] == 'opencode-v2-web'
    run = probe._make_run_dir(tmp_path, 'deny', selected)
    overlay = probe._seed_overlay(MODEL, 1)
    env = probe._opencode_env(run, tmp_path, overlay)
    check = lambda: provenance.opencode_v2_env_check(env, run, selected['fields']['opencode_bench_config_sha256'],
                                                    probe._sha_of(probe.NORETRY_PLUGIN), overlay)
    check()
    config = run / 'cfg/opencode/opencode.json'
    doc = json.loads(config.read_bytes()); doc['permissions'].append(dict(action='webfetch', resource='*', effect='allow'))
    config.write_text(json.dumps(doc))
    with pytest.raises(provenance.ServedConfigError, match='sha256'):
        check()


@pytest.mark.parametrize('value', [{}, [''], [1], [dict(action='webfetch', resource='*', effect='allow')]])
def test_invalid_deny_file(probe, tmp_path, value):
    path = tmp_path / 'deny.json'; path.write_text(json.dumps(value))
    with pytest.raises(SystemExit, match='extra-deny-file'):
        probe._carrier_selection('opencode-v2-web', None, extra_deny_file=path)


def test_deny_legacy_refused(probe, tmp_path):
    with pytest.raises(SystemExit, match='opencode-v2-web'):
        probe._carrier_selection('opencode-v2', None, extra_deny_file=tmp_path / 'absent.json')


def test_report_superseded_unresolved_partial_and_models(tmp_path):
    path = tmp_path / 'rows.jsonl'
    fetch = [{'url': 'https://fixture.invalid/answer'}]
    rows = [attempt('a', web_fetches=fetch), attempt('b', rerun_of='a', rerun_index=1),
            attempt('c', answer_key_contact=True),
            attempt('d', rerun_of='c', rerun_index=1, web_audit_incomplete=True),
            attempt('e', rerun_of='d', rerun_index=2, web_fetches=fetch),
            attempt('f', web_fetches=fetch)]
    for r in rows[2:5]: r['id'] = 'python/two'
    rows[5]['id'] = 'python/three'
    rows.append(dict(rows[5], model='Qwen3.8-27B-mlx-uniform-4bit', session_id='g'))
    for r, label in [(rows[0], 'solution'), (rows[4], 'unclear'), (rows[5], 'partial'), (rows[6], 'docs')]:
        decision(path, r, label)
    report = answer_key.report_rows(rows, audit_sidecar=str(path) + '.webaudit.jsonl')
    assert report['strict_n'] == 4
    assert report['acc_strict'] == .75
    assert report['per_model'][MODEL] == dict(cheat_attempts=4, reruns=3, unresolved=1, partial_lookups=1,
                                                    pending_reruns=0, missing_audits=0, cheat_review=0, provisional=False)
    assert report['per_model']['Qwen3.8-27B-mlx-uniform-4bit']['cheat_attempts'] == 0
    scored = report['scored_rows']
    assert next(r for r in scored if r['session_id'] == 'e')['cheat_unresolved'] is True
    assert next(r for r in scored if r['session_id'] == 'e')['passed'] is False
    assert rows[4]['passed'] is True  # immutable evidence


@pytest.mark.parametrize('flag', ['answer_key_contact', 'web_audit_incomplete', 'web_audit_error', 'audit_error'])
def test_driver_contract_and_two_retry_limit(tmp_path, flag):
    path = tmp_path / 'rows.jsonl'
    r = attempt('a', **{flag: True}, net_shell=[{'command': 'curl https://GitHub.com/Owner/Repo/a.py'}])
    write_rows(path, [r])
    decision(path, r, 'docs', 'net_shell')
    work, = web_audit.cheats_to_rerun(path)
    assert {k: work[k] for k in ('item', 'session_id', 'seed', 'rerun_index')} == dict(
        item='python/one', session_id='a', seed=123, rerun_index=1)
    assert work['urls'] == [] and work['needs_operator'] and work['extra_deny'] == []
    assert work['extra_deny'] == answer_key.deny_patterns_for(work['urls'])
    r2 = dict(r, session_id='b', rerun_of='a', rerun_index=1, extra_deny=work['extra_deny'])
    write_rows(path, [r, r2])
    decision(path, r2, 'docs', 'net_shell')
    work2, = web_audit.cheats_to_rerun(path)
    assert work2['rerun_index'] == 2
    assert set(work['extra_deny']) <= set(work2['extra_deny'])
    r3 = dict(r2, session_id='c', rerun_of='b', rerun_index=2)
    write_rows(path, [r, r2, r3])
    decision(path, r3, 'docs', 'net_shell')
    assert web_audit.cheats_to_rerun(path) == []


def test_rerun_append_resume_and_seed_guard(probe, monkeypatch, tmp_path):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    args = ['--scaffold', 'opencode-v2-web']
    assert f['run']('one', extra=args) == 0
    first = json.loads(f['out'].read_text()); first['answer_key_contact'] = True
    first['answer_key_evidence'] = [{'flag': True, 'source': 'https://fixture.invalid/answer'}]
    write_rows(f['out'], [first])
    deny = tmp_path / 'deny.json'
    deny.write_text(json.dumps(answer_key.deny_patterns_for(['https://fixture.invalid/answer'])))
    rerun = args + ['--extra-deny-file', str(deny), '--rerun-of', first['session_id'], '--rerun-index', '1']
    with pytest.raises(SystemExit, match='seed'):
        f['run']('one', extra=rerun + ['--seed-base', '78'])
    f['set_kind']('http500')
    with pytest.raises(SystemExit, match='ABORT'):
        f['run']('one', extra=rerun)
    assert len(f['out'].read_text().splitlines()) == 1
    f['set_kind']('ok')
    assert f['run']('one', extra=rerun) == 0
    rows = [json.loads(l) for l in f['out'].read_text().splitlines()]
    assert len(rows) == 2 and rows[1]['rerun_of'] == first['session_id'] and rows[1]['rerun_index'] == 1
    assert rows[0]['sampler_seed'] == rows[1]['sampler_seed']
    assert f['run']('one', extra=rerun) == 0
    assert len(f['out'].read_text().splitlines()) == 2
    deny.write_text('["https://other.invalid/*"]')
    with pytest.raises(SystemExit, match='identity'):
        f['run']('one', extra=rerun)


def test_gate_receipt_matches_deny(probe, gate, tmp_path):
    module, binary, carrier = gate
    web = carrier.with_name('opencode_bench_v2_web.json')
    doc = json.loads(carrier.read_text()); doc['permissions'] = []
    web.write_text(json.dumps(doc))
    deny = tmp_path / 'deny.json'; deny.write_text('["https://fixture.invalid/*"]')
    result = module.a4_opencode(MODEL, FakeLogTail([log_row()], [log_row()]), tmp_path, 10, str(binary),
                               scaffold='opencode-v2-web', extra_deny_file=deny)
    selected = probe._carrier_selection('opencode-v2-web', None, repo=module.REPO, source=web, extra_deny_file=deny)
    assert result['carrier_sha256'] == selected['fields']['opencode_bench_config_sha256']
    assert result['extra_deny'] == selected['fields']['extra_deny']
    assert result['extra_deny_sha256'] == selected['fields']['extra_deny_sha256']


@pytest.mark.parametrize('kind', ['webfetch', 'shell'])
def test_real_cheat_then_denied_rerun(probe, real_binary, monkeypatch, tmp_path, kind):
    monkeypatch.setattr(web_audit, 'auditor_version', lambda: 'fake')
    with MockServer() as site:
        url = site.base + '/answers/one'
        inputs = {'url': url, 'format': 'text'} if kind == 'webfetch' else {'command': 'curl ' + url, 'description': 'fixture'}
        tool = {'name': kind, 'input': inputs}
        with MockServer({1: tool, 3: tool}) as mock:
            f = real_fixture(probe, monkeypatch, tmp_path, real_binary, mock)
            doc = json.loads(probe.BENCH_OPENCODE_WEB_CONFIG.read_bytes())
            doc['providers'] = json.loads(f['carrier'].read_bytes())['providers']
            web = tmp_path / 'web.json'; web.write_text(json.dumps(doc))
            monkeypatch.setattr(probe, 'BENCH_OPENCODE_WEB_CONFIG', web)
            args = ['--scaffold', 'opencode-v2-web']
            assert f['run']('one', extra=args) == 0
            assert len(site.requests) == 1
            first_row = json.loads(f['out'].read_text())
            evidence = first_row['web_fetches' if kind == 'webfetch' else 'net_shell'][0]
            evidence_path = Path(evidence['path'].replace('$STACK_WORKDIR', str(tmp_path)))
            first_bytes = evidence_path.read_bytes()
            web_audit.audit_rows(f['out'], auditor=lambda _: '{"label":"solution","reason":"Complete answer."}')
            job, = web_audit.cheats_to_rerun(f['out'])
            deny = tmp_path / 'deny.json'; deny.write_text(json.dumps(job['extra_deny']))
            assert f['run']('one', extra=args + ['--extra-deny-file', str(deny), '--rerun-of', job['session_id'],
                                               '--rerun-index', str(job['rerun_index'])]) == 0
            assert len(site.requests) == 1
            rows = [json.loads(l) for l in f['out'].read_text().splitlines()]
            assert len(rows) == 2 and rows[1]['web_denied'] == 1
            assert rows[0]['transcript_path'] != rows[1]['transcript_path']
            assert evidence_path.read_bytes() == first_bytes
            assert rows[0]['sampler_seed'] == rows[1]['sampler_seed']
            web_audit.audit_rows(f['out'], auditor=lambda _: '{"label":"generic","reason":"Denied."}')
            assert web_audit.cheats_to_rerun(f['out']) == []


def test_pending_and_terminal_resume_status(probe, monkeypatch, tmp_path):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    args = ['--scaffold', 'opencode-v2-web']
    assert f['run']('one', extra=args) == 0
    r = json.loads(f['out'].read_text())
    r['web_audit_incomplete'] = True
    write_rows(f['out'], [r])
    with pytest.raises(SystemExit, match='explicit --rerun-of'):
        f['run']('one', extra=args)
    r['rerun_index'] = 2
    write_rows(f['out'], [r])
    calls = f['calls'].read_bytes()
    assert f['run']('one', extra=args) == 0
    assert f['calls'].read_bytes() == calls


@pytest.mark.parametrize('change', ['source', 'system', 'deny'])
def test_overlay_does_not_relax_ordinary_resume(probe, monkeypatch, tmp_path, change):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    deny = tmp_path / 'deny.json'; deny.write_text('["https://fixture.invalid/*"]')
    args = ['--scaffold', 'opencode-v2-web', '--extra-deny-file', str(deny)]
    assert f['run']('one', extra=args) == 0
    if change == 'deny':
        deny.write_text('["https://other.invalid/*"]')
    elif change == 'source':
        source = tmp_path / 'changed.json'
        source.write_bytes(probe.BENCH_OPENCODE_WEB_CONFIG.read_bytes() + b'\n')
        monkeypatch.setattr(probe, 'BENCH_OPENCODE_WEB_CONFIG', source)
    else:
        args += ['--agent-system-file', 'benchmark/opencode_prompts/opencode-1.18.15-default.txt']
    calls = f['calls'].read_bytes()
    with pytest.raises(SystemExit, match='resume identity'):
        f['run']('one', extra=args)
    assert f['calls'].read_bytes() == calls


def test_latest_noncheat_wins_and_pending_errors_do_not_score(tmp_path):
    rows = [attempt('one'), attempt('two', rerun_of='one', rerun_index=1),
            attempt('three', rerun_of='two', rerun_index=2, audit_error=True)]
    rows[0]['passed'] = False
    report = answer_key.report_rows(rows)
    assert report['strict_n'] == 0 and report['cheat_review'] == 1
    clean = answer_key.report_rows(rows[:2])
    assert clean['strict_n'] == 1 and clean['scored_rows'][0]['session_id'] == 'two'
    assert not answer_key.report_rows([rows[2] | {'rerun_index': 1}])['scored_rows']


def test_driver_only_denies_offending_urls_and_accumulates(tmp_path):
    path = tmp_path / 'rows.jsonl'
    r = attempt('a', web_fetches=[{'url': 'https://bad.invalid/a'}],
                net_shell=[{'command': 'curl https://docs.invalid/a'}], extra_deny=['https://previous.invalid/*'])
    write_rows(path, [r])
    decision(path, r, 'solution')
    decision(path, r, 'docs', 'net_shell')
    job, = web_audit.cheats_to_rerun(path)
    assert job['urls'] == ['https://bad.invalid/a']
    assert job['extra_deny'] == r['extra_deny'] + answer_key.deny_patterns_for(job['urls'])


def test_gate_cli_threads_extra_deny(gate, tmp_path, monkeypatch):
    module, binary, _ = gate
    monkeypatch.setenv('OPENCODE_PROBE_BIN', str(binary))
    monkeypatch.setattr(module, 'LogTail', lambda _: None)
    monkeypatch.setattr(module, 'a6_bare', lambda *a: {'pass': True})
    seen = []
    def a4(*args, **kwargs):
        seen.append(kwargs)
        return {'pass': True, 'sessions': [], 'opencode_version': '2.0.20', 'exe_sha256': 'fixture'}
    monkeypatch.setattr(module, 'a4_opencode', a4)
    deny = tmp_path / 'deny.json'; deny.write_text('[]')
    assert module.main(['--model', MODEL, '--scaffold', 'opencode-v2-web', '--extra-deny-file', str(deny),
                        '--skip-owui', '--workdir', str(tmp_path / 'gate-cli')]) == 0
    assert seen[0]['extra_deny_file'] == deny


def test_audit_error_rows_require_the_web_reporter():
    assert answer_key.needs_web_audit({'id': 'python/one', 'audit_error': True})


def test_driver_contact_evidence_keeps_clean_docs_available(tmp_path):
    path = tmp_path / 'rows.jsonl'
    source = 'https://bad.invalid/answer'
    r = attempt('a', answer_key_contact=True,
                answer_key_evidence=[{'source': source, 'flag': True}],
                web_fetches=[{'url': source}], net_shell=[{'command': 'curl https://docs.invalid/a'}])
    write_rows(path, [r])
    decision(path, r, 'generic')  # detector independently forces cheat status
    decision(path, r, 'docs', 'net_shell')
    job, = web_audit.cheats_to_rerun(path)
    assert job['urls'] == [source]
