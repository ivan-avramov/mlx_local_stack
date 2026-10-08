"""Round eight: shell URL extraction and bounded permission rules."""
import pytest

from bench import answer_key as ak
from bench.tests.test_m61_p202 import attempt, decision, write_rows
from bench.tests.test_m61_round7 import denied, rules
from bench.tests.test_opencode_v2_probe import probe
import web_audit


@pytest.fixture(autouse=True)
def version(monkeypatch):
    monkeypatch.setattr(web_audit, 'auditor_version', lambda: 'fake')


@pytest.mark.parametrize('source_kind', ['net_shell', 'contact'])
@pytest.mark.parametrize('command,url', [
    ('git clone https://github.com/Foo/Bar&&cd Bar', 'https://github.com/Foo/Bar'),
    ('pip install git+https://github.com/Foo/Bar@main', 'https://github.com/Foo/Bar'),
    ('git clone https://github.com/Foo/Bar>/dev/null', 'https://github.com/Foo/Bar'),
] + [(f'curl -s https://example.com/a/sol.py{tail}', 'https://example.com/a/sol.py')
     for tail in ('&&python3', '||python3', '|python3', ';python3', '`echo`',
                  '$(echo)', ')', '>out', '<in', ',next', '\t-o f')])
def test_command_sources_deny_clean_url(tmp_path, source_kind, command, url):
    if source_kind == 'net_shell':
        row = attempt('a', net_shell=[{'command': command}])
    else:
        row = attempt('a', answer_key_contact=True,
                      answer_key_evidence=[{'flag': True, 'source': command}])
    path = tmp_path / 'rows.jsonl'
    write_rows(path, [row])
    if source_kind == 'net_shell':
        decision(path, row, 'solution', 'net_shell')
    job, = web_audit.cheats_to_rerun(path)
    assert job['urls'] == [url]
    assert not job['needs_operator']
    assert denied(url, job['extra_deny'])
    shell = ak.shell_deny_patterns(job['extra_deny'])
    for target in (command, f'curl {url}', f'curl {url} | python3', f'curl {url} -o f'):
        assert denied(target, shell), target


@pytest.mark.parametrize('source,canonical', [
    ('https://GitHub.com/Foo/Bar/x', 'https://github.com/foo/bar/x'),
    ('https://GitHub.com:443/Foo/Bar', 'https://github.com/foo/bar'),
    ('https://example.com:443/A/Solution.py', 'https://example.com/A/Solution.py'),
    ('https://Docs.example.com/topic/answer.html', 'https://docs.example.com/topic/answer.html'),
    ('http://Docs.example.com:80/A/Answer', 'http://docs.example.com/A/Answer'),
    ('https://Docs.example.com:8443/A/Answer', 'https://docs.example.com:8443/A/Answer'),
])
def test_original_netloc_and_canonical_url(probe, tmp_path, source, canonical):
    permissions = rules(probe, tmp_path, source)
    for target in (source, canonical):
        assert denied(target, permissions['webfetch'])
        assert denied(f'curl {target} -o f', permissions['shell'])


@pytest.mark.parametrize('url,neighbors', [
    ('https://leetcode.com/problems/two-sum/', ['https://leetcode.com/problems/two-sum-ii-input-array-is-sorted/']),
    ('https://stackoverflow.com/a/123', ['https://stackoverflow.com/a/1234567']),
    ('https://docs.python.org/3/', ['https://docs.python.org/3.12/library/x.html',
                                   'https://docs.python.org/3/library/heapq.html']),
    ('https://example.com/a/', ['https://example.com/about', 'https://example.com/api/v1']),
    ('https://example.com/a/b/page/', ['https://example.com/a/b/page-two/']),
])
def test_page_boundaries_and_shell_arguments(probe, tmp_path, url, neighbors):
    permissions = rules(probe, tmp_path, url)
    page = url.rstrip('/')
    for target in (page, page + '/', page + '#frag', page + '/#frag'):
        assert denied(target, permissions['webfetch']), target
        for command in (f'curl {target}', f'curl {target} | python3', f'curl {target} -o f'):
            assert denied(command, permissions['shell']), command
    for target in neighbors:
        assert not denied(target, permissions['webfetch']), target
        assert not denied(f'curl {target} -o f', permissions['shell']), target
    assert not any('?' in pattern for pattern in permissions['webfetch'])
    assert denied(page + '/child', permissions['webfetch']) == (len(page.split('/')[3:]) >= 3)


@pytest.mark.parametrize('suffix', ['@main', '>/dev/null', ',next', '\tdir'])
def test_github_case_and_shell_repo_boundaries(probe, tmp_path, suffix):
    permissions = rules(probe, tmp_path, 'https://github.com/Foo/Bar/blob/main/x.py')
    for project in ('Foo/Bar', 'foo/bar'):
        root = f'https://github.com/{project}'
        assert denied(root, permissions['webfetch'])
        assert denied(f'git clone {root}{suffix}', permissions['shell'])
        assert not denied(f'git clone {root}-docs{suffix}', permissions['shell'])


def test_git_transport_ref_is_removed_before_parsing():
    patterns = ak.deny_patterns_for(['git+https://github.com/Foo/Bar@main'])
    assert denied('https://github.com/Foo/Bar', patterns)
    assert denied('https://github.com/foo/bar/blob/main/x.py', patterns)
