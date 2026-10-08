"""Round six: fail-closed audit recovery, bounded denies and load identity."""
import json
from pathlib import Path

import pytest

from bench import answer_key
from bench.tests.test_opencode_v2_probe import probe, fixture_probe, real_binary, real_fixture, MODEL
from bench.tests.test_m61_p202 import decision, write_rows, attempt
from bench.tests.opencode_v2_mock import MockServer
import web_audit


@pytest.fixture(autouse=True)
def version(monkeypatch):
    monkeypatch.setattr(web_audit, 'auditor_version', lambda: 'fake')


def web_row(**kw):
    return attempt('a', scaffold='opencode-v2-web',
                   web_fetches=[{'url': 'https://GitHub.com/Owner/Repo/blob/main/a.py'}], **kw)


@pytest.mark.parametrize('stale', ['absent', 'prompt_sha256', 'auditor_version'])
def test_missing_audit_refuses_driver_and_provisional_report(tmp_path, stale):
    path = tmp_path / 'rows.jsonl'
    row = web_row()
    write_rows(path, [row])
    sidecar = Path(str(path) + '.webaudit.jsonl')
    if stale != 'absent':
        decision(path, row, 'docs')
        record = json.loads(sidecar.read_text())
        record[stale] = 'stale'
        sidecar.write_text(json.dumps(record) + '\n')
    state, = answer_key.audit_states([row], audit_sidecar=sidecar)
    assert state['labels'] == ['missing']
    with pytest.raises(web_audit.AuditMissing, match='audit first: missing/stale audit for python/one'):
        web_audit.cheats_to_rerun(path)
    report = answer_key.report_rows([row], audit_sidecar=sidecar)
    assert report['provisional'] and report['missing_audits'] == 1 and report['strict_n'] == 0


def test_missing_audit_resume_message(probe, monkeypatch, tmp_path):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    args = ['--scaffold', 'opencode-v2-web']
    assert f['run']('one', extra=args) == 0
    row = json.loads(f['out'].read_text())
    row['web_fetches'] = web_row()['web_fetches']
    write_rows(f['out'], [row])
    calls = f['calls'].read_bytes()
    with pytest.raises(SystemExit, match='audit first: missing/stale audit for python/one'):
        f['run']('one', extra=args)
    assert f['calls'].read_bytes() == calls


@pytest.mark.parametrize('host', ['GitHub.com', 'raw.githubusercontent.com', 'GitLab.com'])
def test_repository_patterns_match_roots_clones_and_casing(host):
    from bench.tests.test_m61_round7 import denied
    route = '-/blob/main/a.py' if host == 'GitLab.com' else 'blob/main/a.py'
    patterns = answer_key.deny_patterns_for([f'https://{host}/Owner/Repo/{route}'])
    host = host.lower()
    page = 'github.com' if host == 'raw.githubusercontent.com' else host
    hosts = [host, page] + ([] if host == 'gitlab.com' else ['raw.githubusercontent.com'])
    for domain in hosts:
        assert f'*{domain}/Owner/Repo/*' in patterns
        for scheme in ('https://', 'http://', 'https://www.'):
            for suffix in ('/main/a.py',) if domain == 'raw.githubusercontent.com' else ('', '.git', '/main/a.py'):
                url = f'{scheme}{domain}/Owner/Repo{suffix}'
                for resource in (url, url.lower(), 'git clone ' + url, 'curl ' + url):
                    assert denied(resource, patterns), resource


@pytest.mark.parametrize('url,expected', [
    ('https://example.com/answer?q=1', [
        '*example.com/answer', '*example.com/answer/', '*example.com/answer#*', '*example.com/answer/#*']),
    ('https://example.com/a/file', [
        '*example.com/a/file', '*example.com/a/file/', '*example.com/a/file#*', '*example.com/a/file/#*']),
    ('https://Example.com/a/b/file?q=1', [
        '*Example.com/a/b/file', '*Example.com/a/b/file/', '*Example.com/a/b/file#*',
        '*Example.com/a/b/file/#*', '*Example.com/a/b/file/*',
        '*example.com/a/b/file', '*example.com/a/b/file/', '*example.com/a/b/file#*',
        '*example.com/a/b/file/#*', '*example.com/a/b/file/*']),
    ('https://example.com/', []), ('https://github.com/Owner', []),
    ('https://github.com/Owner/*', []), ('https://github.com/Owner/Re%3Fpo/file', []),
    ('https://example.com/a*/b', []),
])
def test_narrow_patterns_and_wildcard_sanitizing(url, expected):
    assert answer_key.deny_patterns_for([url]) == expected


def test_dropped_url_recorded_and_requires_review(tmp_path):
    path = tmp_path / 'rows.jsonl'
    row = web_row()
    row['web_fetches'][0]['url'] = 'https://github.com/Owner/*'
    write_rows(path, [row]); decision(path, row, 'solution')
    job, = web_audit.cheats_to_rerun(path)
    assert job['dropped_urls'] == [row['web_fetches'][0]['url']]
    assert job['needs_operator'] and job['extra_deny'] == []


@pytest.mark.parametrize('flags', [dict(web_audit_incomplete=True), dict(answer_key_contact=True),
                                    dict(answer_key_contact=True, answer_key_evidence=[{'flag': True, 'source': None}]),
                                    dict(answer_key_contact=True, answer_key_evidence=[{'flag': True, 'source': 'pip install package'}])])
def test_unknown_source_does_not_deny_clean_urls(tmp_path, flags):
    path = tmp_path / 'rows.jsonl'
    row = web_row(**flags)
    write_rows(path, [row]); decision(path, row, 'docs')
    job, = web_audit.cheats_to_rerun(path)
    assert job['needs_operator'] and job['extra_deny'] == []
    report = answer_key.report_rows([dict(row, rerun_index=2)], audit_sidecar=str(path) + '.webaudit.jsonl')
    assert report['strict_n'] == 0 and report['cheat_review'] == 1
    assert report['per_model'][MODEL]['cheat_review'] == 1


def test_pending_per_model_and_provisional(tmp_path):
    path = tmp_path / 'rows.jsonl'
    dirty = web_row()
    clean = attempt('b'); clean['model'] = 'Qwen3.8-27B-mlx-uniform-4bit'
    decision(path, dirty, 'solution')
    report = answer_key.report_rows([dirty, clean], audit_sidecar=str(path) + '.webaudit.jsonl')
    assert report['pending_reruns'] == 1 and report['provisional']
    assert report['per_model'][MODEL]['pending_reruns'] == 1
    assert report['per_model'][MODEL]['provisional']
    assert report['per_model'][clean['model']]['pending_reruns'] == 0
    assert not report['per_model'][clean['model']]['provisional']


@pytest.mark.parametrize('index', [0, 1, 2])
def test_non_web_contact_is_flagged_never_rerun(tmp_path, index):
    path = tmp_path / 'rows.jsonl'
    row = attempt('a', scaffold='opencode-v2', answer_key_contact=True, rerun_index=index)
    write_rows(path, [row])
    assert web_audit.cheats_to_rerun(path) == []
    report = answer_key.report_rows([row])
    assert report['strict_n'] == 0 and report['flagged: answer-key contact'] == 1
    assert report['cheat_review'] == 1 and report['provisional']


@pytest.mark.parametrize('empty', [True, False])
def test_operator_review_blocks_probe_rerun(probe, monkeypatch, tmp_path, empty):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    args = ['--scaffold', 'opencode-v2-web']
    assert f['run']('one', extra=args) == 0
    row = json.loads(f['out'].read_text())
    row['web_audit_incomplete'] = True
    write_rows(f['out'], [row])
    deny = tmp_path / 'deny.json'
    deny.write_text(json.dumps([] if empty else ['*github.com/Owner/Repo*']))
    calls = f['calls'].read_bytes()
    with pytest.raises(SystemExit, match='needs_operator|cheat_review'):
        f['run']('one', extra=args + ['--rerun-of', row['session_id'], '--rerun-index', '1',
                                    '--extra-deny-file', str(deny)])
    assert f['calls'].read_bytes() == calls


@pytest.mark.parametrize('change', ['pid', 'model_path', 'missing'])
def test_worker_reload_refuses_same_router_rerun(probe, monkeypatch, tmp_path, change):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    worker = {'pid': 456, 'model_path': 'fixture/' + MODEL}
    monkeypatch.setattr(probe, '_worker_load_identity', lambda *a: dict(worker), raising=False)
    args = ['--scaffold', 'opencode-v2-web']
    assert f['run']('one', extra=args) == 0
    row = json.loads(f['out'].read_text())
    row['web_fetches'] = web_row()['web_fetches']
    write_rows(f['out'], [row]); decision(f['out'], row, 'solution')
    if change == 'missing':
        worker.clear()
    else:
        worker[change] = 789 if change == 'pid' else 'fixture/other'
    deny = tmp_path / 'deny.json'; deny.write_text(json.dumps(answer_key.deny_patterns_for([row['web_fetches'][0]['url']])))
    calls = f['calls'].read_bytes()
    with pytest.raises(SystemExit, match='worker.*identity|worker.*instance'):
        f['run']('one', extra=args + ['--rerun-of', row['session_id'], '--rerun-index', '1',
                                    '--extra-deny-file', str(deny)])
    assert f['calls'].read_bytes() == calls


def test_transferable_solution_prompt():
    prompt = web_audit.PROMPT.read_text()
    assert 'another language' in prompt.lower()
    assert 'algorithm/structure transfers directly' in prompt
    assert 'would pass most tests after trivial edits' in prompt
    assert 'without code is partial' in prompt


@pytest.mark.parametrize('kind', ['webfetch', 'shell'])
def test_real_repo_root_and_clone_denied_hermetically(probe, real_binary, monkeypatch, tmp_path, kind):
    # Permission resources are full strings. The public host/repo is ONLY in a
    # loopback path: a faulty deny can contact this mock but never the internet.
    with MockServer() as site:
        url = site.base + '/github.com/Owner/Repo'
        inputs = {'url': url, 'format': 'text'} if kind == 'webfetch' else {
            'command': 'git clone ' + url, 'description': 'local repository tripwire'}
        with MockServer({1: {'name': kind, 'input': inputs}}) as mock:
            f = real_fixture(probe, monkeypatch, tmp_path, real_binary, mock)
            doc = json.loads(probe.BENCH_OPENCODE_WEB_CONFIG.read_bytes())
            doc['providers'] = json.loads(f['carrier'].read_bytes())['providers']
            web = tmp_path / 'web.json'; web.write_text(json.dumps(doc))
            monkeypatch.setattr(probe, 'BENCH_OPENCODE_WEB_CONFIG', web)
            deny = tmp_path / 'deny.json'
            deny.write_text(json.dumps(answer_key.deny_patterns_for(['https://github.com/Owner/Repo/blob/main/a.py'])))
            assert f['run']('one', extra=['--scaffold', 'opencode-v2-web', '--extra-deny-file', str(deny)]) == 0
            row = json.loads(f['out'].read_text())
            assert site.requests == []
            entry = row['web_fetches' if kind == 'webfetch' else 'net_shell'][0]
            assert entry['status'] == 'denied' and entry['bytes'] == 0


@pytest.mark.parametrize('change', ['none', 'pid', 'path', 'parent', 'absent'])
def test_worker_identity_uses_attributed_listener(probe, monkeypatch, tmp_path, change):
    registry = tmp_path / 'registry.json'
    registry.write_text(json.dumps({'mlx_port': 1234, 'models': [{'name': MODEL, 'hf_path': 'fixture/' + MODEL}]}))
    monkeypatch.setattr(probe.provenance.paths, 'registry_path', lambda: registry)
    calls = iter([[456], [789] if change == 'pid' else [456]])
    monkeypatch.setattr(probe.provenance, '_port_listener_pids', lambda _: next(calls))
    argv = ['python', '-m', 'mlx_vlm.server', '--model', 'fixture/' + MODEL]
    if change == 'path': argv[-1] = 'fixture/other'
    monkeypatch.setattr(probe.provenance, '_worker_argvs', lambda _: [] if change == 'absent' else [argv])
    monkeypatch.setattr(probe.provenance, '_descends_from', lambda pid, parents: change != 'parent' and parents == {123})
    identity = probe._worker_load_identity(MODEL, {'pid': 123})
    assert identity == ({'pid': 456, 'model_path': 'fixture/' + MODEL} if change == 'none' else None)


def test_superseded_missing_audit_keeps_report_provisional(tmp_path):
    path = tmp_path / 'rows.jsonl'
    old = web_row()
    new = dict(old, session_id='b', web_fetches=[], rerun_index=1)
    report = answer_key.report_rows([old, new])
    assert report['provisional'] and report['missing_audits'] == 1


def test_any_unlocated_contact_requires_operator(tmp_path):
    path = tmp_path / 'rows.jsonl'
    row = web_row(net_shell=[{'command': 'pip install package'}])
    write_rows(path, [row]); decision(path, row, 'solution'); decision(path, row, 'solution', 'net_shell')
    job, = web_audit.cheats_to_rerun(path)
    assert job['needs_operator'] and not job['extra_deny']


def test_www_source_also_denies_canonical_repo_root():
    from bench.tests.test_m61_round7 import denied
    patterns = answer_key.deny_patterns_for(['https://www.GitHub.com/Owner/Repo.git'])
    for resource in ('https://github.com/Owner/Repo', 'git clone http://github.com/owner/repo.git'):
        assert denied(resource, patterns)
    for resource in ('https://github.com/Owner', 'https://github.com/Owner/Other'):
        assert not denied(resource, patterns)
