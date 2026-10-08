"""P201 offline acceptance; all auditor calls are fakes."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from bench.tests.test_opencode_v2_probe import probe, real_binary, real_fixture
from bench.tests.opencode_v2_mock import MockServer

FIXTURES = Path(__file__).parent / 'fixtures'
PATTERNS = ['api.github.com/search/code', 'github.com/search?q=code', 'grep.app/api/search',
            'sourcegraph.com/search', 'searchcode.com/api']


def test_evidence_verbatim_hashes_and_portable_paths(probe, tmp_path, monkeypatch):
    monkeypatch.setenv('STACK_WORKDIR', str(tmp_path))
    target = tmp_path / 'opencode_transcripts/model/leg/python__bowling.json'
    contents = ['é\r\nfirst\n', 'last\n']
    parts = [{'type': 'tool', 'name': name, 'state': {
        'status': 'completed', 'input': inputs,
        'content': [{'type': 'text', 'text': text} for text in contents]}}
        for name, inputs in [('webfetch', {'url': 'https://docs.invalid'}),
                             ('shell', {'command': 'curl https://docs.invalid'})]]
    result = probe._web_audit({'messages': [{'content': parts}]}, tmp_path, target)
    for index, entry in enumerate(result['web_fetches'] + result['net_shell']):
        assert entry['path'] == f'$STACK_WORKDIR/opencode_transcripts/model/leg/python__bowling.web/{index}.txt'
        data = Path(entry['path'].replace('$STACK_WORKDIR', str(tmp_path))).read_bytes()
        assert data == ''.join(contents).encode()
        assert entry['sha256'] == hashlib.sha256(data).hexdigest()
        assert entry['bytes'] == len(data)


@pytest.mark.parametrize('destination', PATTERNS)
@pytest.mark.parametrize('kind', ['webfetch', 'shell'])
def test_real_code_search_denied(probe, real_binary, monkeypatch, tmp_path, destination, kind):
    with MockServer() as site:
        url = site.base + '/' + destination
        inputs = {'url': url, 'format': 'text'} if kind == 'webfetch' else {
            'command': 'curl ' + url, 'description': 'deny fixture'}
        with MockServer({1: {'name': kind, 'input': inputs}}) as mock:
            f = real_fixture(probe, monkeypatch, tmp_path, real_binary, mock)
            doc = json.loads(probe.BENCH_OPENCODE_WEB_CONFIG.read_text())
            doc['providers'] = json.loads(f['carrier'].read_text())['providers']
            carrier = tmp_path / 'web.json'
            carrier.write_text(json.dumps(doc))
            monkeypatch.setattr(probe, 'BENCH_OPENCODE_WEB_CONFIG', carrier)
            assert f['run']('one', extra=['--scaffold', 'opencode-v2-web']) == 0
            row = json.loads(f['out'].read_text())
            assert site.requests == []
            entry = row['web_fetches' if kind == 'webfetch' else 'net_shell'][0]
            assert entry['status'] == 'denied'
            assert entry['bytes'] == 0
            assert entry['sha256'] == hashlib.sha256(b'').hexdigest()


def fixture_rows(tmp_path, monkeypatch):
    monkeypatch.setenv('STACK_WORKDIR', str(tmp_path))
    corpus = tmp_path / 'corpus'
    rows = []
    for number, (item, filename) in enumerate([
        ('go/matrix', 'known_positive_go_matrix_fetch.txt'),
        ('python/bowling', 'community_python_bowling.txt'),
        ('go/matrix', 'go_stdlib_docs.txt'),
    ]):
        language, name = item.split('/')
        dest = corpus / language / 'exercises/practice' / name
        dest.mkdir(parents=True, exist_ok=True)
        ext = 'go' if language == 'go' else 'py'
        (dest / f'{name}.{ext}').write_bytes((FIXTURES / f'answer_key/{name}/{name}.{ext}').read_bytes())
        data = (FIXTURES / filename).read_bytes()
        evidence = tmp_path / f'opencode_transcripts/fixture/{number}.web/0.txt'
        evidence.parent.mkdir(parents=True)
        evidence.write_bytes(data)
        rows.append({'id': item, 'sample': 0, 'session_id': f'fixture-{number}', 'passed': True,
                     'web_fetches': [{'url': 'https://fixture.invalid/content', 'status': 'completed',
                                     'path': '$STACK_WORKDIR/' + evidence.relative_to(tmp_path).as_posix(),
                                     'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}]})
    path = tmp_path / 'rows.jsonl'
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    return path, corpus, rows


def test_fake_auditor_sidecar_reporting_and_idempotence(tmp_path, monkeypatch):
    import web_audit as audit
    from bench.answer_key import report_rows
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    original = path.read_bytes()
    answers = iter(json.loads((FIXTURES / 'web_audit_answers.json').read_text()))
    prompts = []
    def fake(prompt):
        prompts.append(prompt)
        return json.dumps(next(answers))
    sidecar = audit.audit_rows(path, polyglot_root=corpus, auditor=fake)
    records = [json.loads(line) for line in sidecar.read_text().splitlines()]
    assert [r['label'] for r in records] == ['solution', 'solution', 'docs']
    assert all(r['auditor'] == 'codex:gpt-6-astra' for r in records)
    assert all(r['prompt_sha256'] == hashlib.sha256(audit.PROMPT.read_bytes()).hexdigest() for r in records)
    assert all('passed' not in prompt and 'answer_key_contact' not in prompt for prompt in prompts)
    assert records[0]['preflag'] is True
    assert records[1]['preflag'] is False  # only one top-level public identifier
    report = report_rows(rows, audit_sidecar=sidecar)
    assert report['strict_n'] == 1 and report['flagged: web contact'] == 2
    assert report['strict_items'] == {'go/matrix': [1]}  # session-specific joins
    assert path.read_bytes() == original
    before = sidecar.read_bytes()
    audit.audit_rows(path, polyglot_root=corpus, auditor=lambda _: pytest.fail('duplicate audit'))
    assert sidecar.read_bytes() == before
    new_prompt = tmp_path / 'prompt.md'
    new_prompt.write_bytes(audit.PROMPT.read_bytes() + b'\n')
    audit.audit_rows(path, polyglot_root=corpus, auditor=lambda _: '{"label":"tests","reason":"fixture tests"}',
                     prompt_file=new_prompt)
    assert len(sidecar.read_text().splitlines()) == 6
    report = report_rows(rows, audit_sidecar=sidecar, prompt_sha256=hashlib.sha256(new_prompt.read_bytes()).hexdigest())
    assert report['strict_n'] == 3 and report['web contact: tests'] == 3


@pytest.mark.parametrize('answer', ['docs', '```json\n{"label":"docs","reason":"ok"}\n```',
    '{"label":"docs","reason":"ok"} trailing', '{"label":["docs","solution"],"reason":"ok"}',
    '{"label":"docs","reason":"first\\nsecond"}', '{"label":"docs","reason":""}',
    '{"label":"docs","label":"solution","reason":"ok"}', '{"label":"other","reason":"ok"}',
    '{"label":"docs","reason":"ok","extra":1}'])
def test_malformed_is_unclear(answer):
    import web_audit as audit
    assert audit.parse_answer(answer)['label'] == 'unclear'


@pytest.mark.parametrize('failure', [subprocess.TimeoutExpired('codex', 1), OSError('no codex'),
                                     subprocess.CalledProcessError(1, ['codex'])])
def test_audit_failures_and_operator_resolution(tmp_path, monkeypatch, failure):
    import web_audit as audit
    from bench.answer_key import report_rows
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    def fail(_):
        raise failure
    sidecar = audit.audit_rows(path, polyglot_root=corpus, auditor=fail)
    records = [json.loads(line) for line in sidecar.read_text().splitlines()]
    assert all(r['label'] == 'audit_error' for r in records)
    assert report_rows(rows, audit_sidecar=sidecar)['strict_n'] == 0
    assert report_rows(rows)['strict_n'] == 0  # pending is unresolved
    with sidecar.open('a') as stream:
        for record in records:
            stream.write(json.dumps({**record, 'operator_label': 'generic', 'operator_reason': 'Reviewed locally.'}) + '\n')
    assert report_rows(rows, audit_sidecar=sidecar)['strict_n'] == 3
    rows[0]['answer_key_contact'] = True
    assert report_rows(rows, audit_sidecar=sidecar)['strict_n'] == 2


def test_evidence_tamper_is_unresolved(tmp_path, monkeypatch):
    import web_audit as audit
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    Path(rows[0]['web_fetches'][0]['path'].replace('$STACK_WORKDIR', str(tmp_path))).write_text('tampered')
    sidecar = audit.audit_rows(path, polyglot_root=corpus, auditor=lambda _: '{"label":"docs","reason":"docs"}')
    assert json.loads(sidecar.read_text().splitlines()[0])['label'] == 'audit_error'


def test_codex_subprocess_stdin_timeout_and_output(tmp_path, monkeypatch):
    import web_audit as audit
    monkeypatch.setenv('STACK_WORKDIR', str(tmp_path))
    def run(argv, **kw):
        assert argv[:8] == ['codex', 'exec', '-m', 'gpt-6-astra', '-s', 'read-only', '--skip-git-repo-check', '-o']
        assert argv[-1] == '-' and 'secret fetched text' not in argv
        assert kw['input'] == 'secret fetched text'
        assert kw['timeout'] == 17 and kw['check'] is True
        assert Path(argv[8]).is_relative_to(tmp_path)
        Path(argv[8]).write_text('{"label":"docs","reason":"API reference."}')
    monkeypatch.setattr(audit.subprocess, 'run', run)
    assert json.loads(audit.codex_auditor('secret fetched text', timeout=17))['label'] == 'docs'


def test_public_identifiers_and_language_gate(tmp_path):
    import web_audit as audit
    (tmp_path / 'stub.py').write_text('class Public:\n def method(self): pass\ndef alpha(): pass\nasync def beta(): pass\ndef _private(): pass\n')
    (tmp_path / 'stub_test.py').write_text('def test_noise(): pass\n')
    assert audit.public_identifiers(tmp_path, 'python') == ['Public', 'alpha', 'beta']
    (tmp_path / 'stub.go').write_text('package fixture\ntype Public struct{}\nfunc Alpha() {}\nfunc (p Public) Beta() {}\nfunc private() {}\n')
    assert audit.public_identifiers(tmp_path, 'go') == ['Alpha', 'Beta', 'Public']
    assert audit.preflag('package fixture\nfunc Alpha() { Beta(Public{}) }', 'go', ['Alpha', 'Beta', 'Public'])
    assert not audit.preflag('Read about Alpha Beta Public.', 'go', ['Alpha', 'Beta', 'Public'])
    assert not audit.preflag('package fixture\nfunc Alpha() { Beta(NotPublic{}) }', 'go', ['Alpha', 'Beta', 'Public'])


def test_community_solution_evades_overlap():
    from bench.answer_key import contact, normalize, _overlap
    item = FIXTURES / 'answer_key/bowling'
    text = (FIXTURES / 'community_python_bowling.txt').read_text()
    assert not contact(item, [{'source': 'community', 'text': text}])['flag']
    reference = normalize((item / '.meta/example.py').read_text())
    matched, run = _overlap(reference, normalize(text))
    print(f'community bowling: {matched}/{len(reference)} lines, run={run}')


def test_network_shell_unclear_resolution_and_prompt_limit(tmp_path, monkeypatch):
    import web_audit as audit
    from bench.answer_key import report_rows
    path, corpus, rows = fixture_rows(tmp_path, monkeypatch)
    row = rows[1]
    entry = row.pop('web_fetches')[0]
    entry['command'] = 'curl https://fixture.invalid/community'
    entry.pop('url')
    data = ('x' * 6000 + 'INVISIBLE_SUFFIX').encode()
    Path(entry['path'].replace('$STACK_WORKDIR', str(tmp_path))).write_bytes(data)
    entry.update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
    row['net_shell'] = [entry]
    path.write_text(json.dumps(row) + '\n')
    def fake(prompt):
        payload = json.loads(prompt.split('\nINPUT_JSON\n', 1)[1])
        assert len(payload['text']) == 6000 and 'INVISIBLE_SUFFIX' not in prompt
        assert payload['command'] == entry['command']
        assert payload['public_identifiers'] == ['BowlingGame']
        return '{"label":"unclear","reason":"Needs review."}'
    sidecar = audit.audit_rows(path, polyglot_root=corpus, auditor=fake)
    record = json.loads(sidecar.read_text())
    assert record['kind'] == 'net_shell'
    assert report_rows([row], audit_sidecar=sidecar)['flagged: web contact'] == 1
    with sidecar.open('a') as stream:
        stream.write(json.dumps({**record, 'operator_label': 'tests', 'operator_reason': 'Canonical cases.'}) + '\n')
    report = report_rows([row], audit_sidecar=sidecar)
    assert report['strict_n'] == 1 and report['web contact: tests'] == 1


def test_trailing_newline_in_reason_is_malformed():
    import web_audit as audit
    assert audit.parse_answer('{"label":"docs","reason":"ok\\n"}')['label'] == 'unclear'
