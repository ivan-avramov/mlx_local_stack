"""Round seven: verifier repros using opencode 2.0.20 permission semantics."""
import json
import re
from types import SimpleNamespace

import pytest

from bench import answer_key as ak
from bench.tests.test_m61_p202 import attempt, decision, write_rows
from bench.tests.test_opencode_v2_probe import probe, MODEL
import web_audit


def match(inp, pat):
    """Faithful POSIX port of opencode 2.0.20 util/wildcard.ts (verify6/deny.py)."""
    e = re.sub(r'[.+^${}()|\[\]\\]', lambda m: '\\' + m.group(0), pat.replace('\\', '/'))
    e = e.replace('*', '.*').replace('?', '.')
    if e.endswith(' .*'):
        e = e[:-3] + '( .*)?'
    return re.match('^' + e + '$', inp.replace('\\', '/'), re.S) is not None


def denied(resource, patterns):
    # Evaluate EVERY pattern, including ones after the first match.
    return any([match(resource, pattern) for pattern in patterns])


@pytest.fixture(autouse=True)
def version(monkeypatch):
    monkeypatch.setattr(web_audit, 'auditor_version', lambda: 'fake')


def rules(probe, tmp_path, url):
    patterns = ak.deny_patterns_for([url])
    path = tmp_path / 'deny.json'
    path.write_text(json.dumps(patterns))
    selected = probe._carrier_selection('opencode-v2-web', None, extra_deny_file=path)
    permissions = json.loads(selected['bytes'])['permissions']
    base = len(json.loads(probe.BENCH_OPENCODE_WEB_CONFIG.read_bytes())['permissions'])
    for permission in permissions[base:]:
        pattern = permission['resource']
        assert match(pattern.strip('*'), pattern), pattern
    return {action: [p['resource'] for p in permissions[base:] if p['action'] == action]
            for action in ('webfetch', 'shell')}


@pytest.mark.parametrize('url,canonical', [
    ('https://pastebin.com/raw/abc?x=1', 'https://pastebin.com/raw/abc'),
    ('https://www.geeksforgeeks.org/solution-x/', 'https://www.geeksforgeeks.org/solution-x'),
    ('https://EXAMPLE.com:443/A/Solution.py', 'https://example.com/A/Solution.py'),
    ('http://EXAMPLE.com:80/A/Solution.py', 'http://example.com/A/Solution.py'),
    ('https://example.com:8443/A/Solution.py', 'https://example.com:8443/A/Solution.py'),
])
def test_page_variants_and_entire_shell_node(probe, tmp_path, url, canonical):
    permissions = rules(probe, tmp_path, url)
    variants = [canonical, canonical + '#frag', canonical + '?q=1', canonical + '/',
                canonical.replace('www.', ''), canonical.lower()]
    for target in variants:
        assert denied(target, permissions['webfetch']), target
        for command in (f'curl {target}', f'curl {target} | python', f'curl {target} -o f',
                        f'echo $(curl "{target}")'):
            assert denied(command, permissions['shell']), command
    for action, patterns in permissions.items():
        for pattern in patterns:
            assert any([match(target, pattern) for target in variants] if action == 'webfetch' else
                       [match(f'curl {target} -o f', pattern) for target in variants]), pattern


@pytest.mark.parametrize('source,roots', [
    ('https://github.com/Foo/Bar/blob/main/x.py', ['github.com/Foo/Bar',
        'raw.githubusercontent.com/Foo/Bar', 'api.github.com/repos/Foo/Bar',
        'cdn.jsdelivr.net/gh/Foo/Bar', 'github.com:Foo/Bar']),
    ('https://GitHub.com:443/Foo/Bar/blob/main/x.py', ['github.com/Foo/Bar']),
    ('https://raw.githubusercontent.com/Foo/Bar/main/x.py', ['github.com/Foo/Bar']),
    ('https://gitlab.com/grp/sub/repo/-/raw/main/x', ['gitlab.com/grp/sub/repo', 'gitlab.com:grp/sub/repo']),
])
def test_repo_boundaries_and_shell_positions(probe, tmp_path, source, roots):
    permissions = rules(probe, tmp_path, source)
    for root in roots:
        for variant in dict.fromkeys((root, root.lower())):
            for suffix in ('', '/', '/main/x.py', '.git', '#frag'):
                if root.startswith('raw.') and not suffix.startswith('/'):
                    continue
                target = 'https://' + variant + suffix
                assert denied(target, permissions['webfetch']), target
                for command in (f'curl {target}', f'curl {target} -o f', f'curl "{target}" | head',
                                f'curl {target}|python', f'git clone {target} && ls'):
                    assert denied(command, permissions['shell']), command
            for sibling in ('-docs', 'SomethingElse'):
                target = 'https://' + variant + sibling + '/wiki'
                assert not denied(target, permissions['webfetch']), target
                assert not denied('curl ' + target + ' -o f', permissions['shell']), target
    if 'gitlab' in source:
        assert not any('raw.githubusercontent' in p for p in permissions['webfetch'])
        assert not denied('https://gitlab.com/grp/sub/other-repo', permissions['webfetch'])
    else:
        for cmd in ('gh repo clone Foo/Bar', 'gh api repos/Foo/Bar', 'git clone git@github.com:Foo/Bar.git'):
            assert denied(cmd, permissions['shell']), cmd
            assert denied(cmd + ' && ls', permissions['shell']), cmd
        for cmd in ('gh repo clone Foo/Bar-docs', 'gh api repos/Foo/Bar-docs'):
            assert not denied(cmd, permissions['shell']), cmd


def test_wildcard_contract_cannot_escape_question_or_bound_bare_star():
    # Requirement 6's literal shapes contradict its sibling-allow requirement.
    for pattern in ('*github.com/Foo/Bar?*', '*api.github.com/repos/Foo/Bar*',
                    '*cdn.jsdelivr.net/gh/Foo/Bar*', '*github.com:Foo/Bar*',
                    '*gh repo clone Foo/Bar*', '*gh api repos/Foo/Bar*'):
        assert match(pattern.strip('*').replace('?', '') + '-docs', pattern)
    assert match('git clone x', 'git clone x *')  # optional trailing space-star
    assert match('a/b\nc', 'a*b?c')  # normalized slashes, dotAll
    assert not match('ab', 'a[bc]')  # brackets are literal, not fnmatch classes


@pytest.mark.parametrize('punctuation', list(")]},;:.'\"") + [")]},;:.'\""])
def test_url_punctuation_is_removed_from_extraction_and_patterns(tmp_path, punctuation):
    url = 'https://EXAMPLE.com:443/A/Answer'
    row = attempt('a', net_shell=[{'command': 'echo $(curl ' + url + punctuation}])
    path = tmp_path / 'rows.jsonl'
    write_rows(path, [row]); decision(path, row, 'solution', 'net_shell')
    job, = web_audit.cheats_to_rerun(path)
    assert job['urls'] == [url]
    assert job['extra_deny'] == ak.deny_patterns_for([url + punctuation])
    assert '*example.com/A/Answer*' in job['extra_deny']
    assert '*example.com/a/answer*' in job['extra_deny']


@pytest.mark.parametrize('label', ['SOLUTION', 'Docs', None, 'unknown', '', [], {}])
def test_invalid_labels_are_missing(tmp_path, label):
    row = attempt('a', web_fetches=[{'url': 'https://example.com/answer'}])
    path = tmp_path / 'rows.jsonl'
    write_rows(path, [row]); decision(path, row, label)
    state, = ak.audit_states([row], audit_sidecar=str(path) + '.webaudit.jsonl')
    assert state['labels'] == ['missing']
    with pytest.raises(ak.AuditMissing):
        web_audit.cheats_to_rerun(path)
    report = ak.report_rows([row], audit_sidecar=str(path) + '.webaudit.jsonl')
    assert report['missing_audits'] == 1 and report['provisional'] and report['strict_n'] == 0


@pytest.mark.parametrize('scaffold', ['opencode-v2', 'opencode-v2-web'])
@pytest.mark.parametrize('index', [0, 1, 2])
def test_ineligible_latest_cheat_is_visible_and_provisional(scaffold, index):
    clean = attempt('a')
    dirty = attempt('b', scaffold=scaffold, rerun_index=index, answer_key_contact=True,
                    answer_key_evidence=[{'flag': True, 'source': 'read: fixture'}])
    report = ak.report_rows([clean, dirty])
    assert report['strict_n'] == 0 and report['cheat_review'] == 1 and report['provisional']
    assert report['per_model'][MODEL]['cheat_review'] == 1


@pytest.mark.parametrize('mode', ['unrelated', 'prior_only', 'planned', 'superset'])
def test_resume_requires_source_plan_subset(probe, monkeypatch, tmp_path, mode):
    worker = {'pid': 4242, 'model_path': 'fixture/' + MODEL}
    row = attempt('a', worker=worker, extra_deny=['*previous.invalid/answer*'],
                  web_fetches=[{'url': 'https://github.com/Foo/Bar/blob/main/x.py'}])
    path = tmp_path / 'rows.jsonl'
    decision(path, row, 'solution')
    state, = ak.audit_states([row], audit_sidecar=str(path) + '.webaudit.jsonl')
    plan = ak.rerun_plan(state)['extra_deny']
    deny = {'unrelated': ['*unrelated.example/zzz*'], 'prior_only': row['extra_deny'],
            'planned': plan, 'superset': plan + ['*another.invalid/answer*']}[mode]
    monkeypatch.setattr(probe, '_item_seed', lambda *a: 123)
    monkeypatch.setattr(probe, '_check_resume_v2', lambda *a, **k: None)
    monkeypatch.setattr(probe, '_worker_load_identity', lambda *a: worker)
    args = SimpleNamespace(rerun_of='a', rerun_index=1, lang='python', items='one', model=MODEL, seed_base=0)
    invoke = lambda: probe._rerun_resume(args, [row], path, {'router': {'pid': 1}, 'runtime': {}},
                                        {'extra_deny': deny}, {'pid': 1})
    if mode in ('unrelated', 'prior_only'):
        with pytest.raises(SystemExit, match='planned.*deny'):
            invoke()
    else:
        assert invoke() == set()


@pytest.mark.xfail(strict=True, reason="Operator decision: '?' matches one character; root ?* denies repo siblings")
def test_root_query_and_sibling_contract(probe, tmp_path):
    permissions = rules(probe, tmp_path, 'https://github.com/Foo/Bar/blob/main/x.py')
    for action, resource in (('webfetch', 'https://github.com/Foo/Bar?q=1'),
                             ('shell', 'curl https://github.com/Foo/Bar?q=1 -o f')):
        assert denied(resource, permissions[action])
        assert not denied(resource.replace('?q=1', '-docs'), permissions[action])


@pytest.mark.parametrize('scaffold', ['opencode-v2', 'opencode-v2-web'])
def test_ineligible_cheat_with_missing_audit_still_counts_review(scaffold):
    row = attempt('a', scaffold=scaffold, answer_key_contact=True,
                  web_fetches=[{'url': 'https://example.com/answer'}])
    report = ak.report_rows([row])
    assert report['cheat_review'] == 1 and report['missing_audits'] == 1 and report['provisional']
