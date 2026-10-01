"""The PII checker must catch the leak that actually happened, and stay quiet on the corpus.

The leak it exists to stop: 11 tracked manifests carried an absolute home path with a real
username into a PUBLIC repo (`benchmark/results/**/*.manifest.json`, introduced by the bulk
results import). AGENTS.md already forbade it in prose; nothing enforced it, and the naming
hook does not look for it.
"""
from bench import piicheck


def _diff(path: str, added: str) -> str:
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -0,0 +1 @@\n+{added}\n"


def test_catches_the_leak_that_happened():
    d = _diff("benchmark/results/m/math500.manifest.json",
              '    "hf_path": "/Users/someone/models/Ornith-1.0-35B-mlx-uniform-4bit",')
    found = piicheck.diff_violations(d)
    assert len(found) == 1, found
    assert "someone" in str(found[0])


def test_catches_linux_home_and_tokens_and_hostnames():
    for added in ('path = /home/realuser/ws/stack',
                  'HF_TOKEN=hf_abcdefghijklmnopqrstuvwxyz0123',
                  'ssh mybox.local'):
        assert piicheck.diff_violations(_diff("x.sh", added)), added


def test_placeholders_and_redactions_are_allowed():
    for added in ('export REMOTE_REPO="/home/remoteuser/path/to/mlx_local_stack"',
                  '    "hf_path": "$HOME/models/Ornith-1.0-35B-mlx-uniform-4bit",',
                  'cd $STACK_REPO && ls',
                  'repo at $REMOTE_HOME/ws/stack',
                  # BFCL corpus items ship fictional paths like /user/home/datasets/finance.csv;
                  # result rows quote them verbatim (same class as the corpus's fake emails).
                  '{"dataset_path": "/user/home/datasets/finance.csv"}'):
        assert piicheck.diff_violations(_diff("config.example.sh", added)) == [], added


def test_catches_dash_flattened_home_path():
    """dsh (and similar tools) turn an absolute path into a filename by replacing `/` with `-`,
    e.g. a session-log id derived from `/Users/alice/ws/project`. The slash-based pattern above
    can't see this form at all."""
    for added in ('"log": "--Users-alice-ws-project-session.jsonl.zstd"',
                  'path=--home-bob-ws-project--'):
        found = piicheck.diff_violations(_diff("x.jsonl", added))
        assert found, added
        assert "flattened" in str(found[0]), found


def test_dash_flattened_placeholders_are_allowed():
    for added in ('"log": "--Users-remoteuser-ws-project-session.jsonl.zstd"',
                  '"log": "--home-datasets-ws-project-session.jsonl.zstd"'):
        assert piicheck.diff_violations(_diff("x.jsonl", added)) == [], added


def test_dash_flattened_ordinary_word_is_an_accepted_false_positive():
    """`-home-page-` fits the same shape as a flattened `/home/<name>/` and isn't whitelisted, so
    it DOES flag — same residual risk the slash form already carries for `/home/page/`. Documented
    here rather than silently discovered; a real hit like this uses `allow-pii-pattern`."""
    assert piicheck.diff_violations(_diff("x.sh", "url = site.example/a-home-page-b")), (
        "if this starts passing, the pattern got narrower than the module doc claims")


def test_removed_lines_are_never_flagged():
    """A commit that DELETES a leak must not be blocked, or the scrub itself is unmergeable."""
    d = ("diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n"
         '-  "hf_path": "/Users/someone/models/x"\n'
         '+  "hf_path": "$HOME/models/x"\n')
    assert piicheck.diff_violations(d) == []


def test_agentbench_os_corpus_guest_paths_are_exempt():
    """M54: upstream os-std task descriptions quote guest-OS paths like /home/user1/ verbatim
    (Apache-2.0, THUDM/AgentBench) -- fictional accounts inside the task's own docker sandbox,
    never a path on this host. One row per line with no comment syntax to carry an inline marker,
    so the file is exempted by path (same rationale as the BFCL/IFEval corpus exemptions)."""
    d = _diff("benchmark/corpora/agentbench_os_v1.jsonl",
              '{"id": "std-004-0", "description": "look in /home/user1/os/linux"}')
    assert piicheck.diff_violations(d) == []


def test_agentbench_os_results_guest_home_paths_are_exempt_P17():
    """M54 result/compare artifacts quote the SAME guest-OS `/home/<name>/` paths verbatim,
    inside model answers and tool output -- fictional container accounts, not a real host path.
    Narrower than the corpus exemption above: ONLY the `/home/` pattern is suppressed in these
    files; a real `/Users/<name>` path must still be caught (see the next test)."""
    for path in ("benchmark/results/some-model/agentbench_os.v1.jsonl",
                 "benchmark/results/agentbench_os_compare_2026-09-29.md",
                 "benchmark/results/agentbench_os_compare.json"):
        d = _diff(path, '{"answer": "cd /home/user1/os/linux && ls /home/jack/"}')
        assert piicheck.diff_violations(d) == [], (path, piicheck.diff_violations(d))


def test_agentbench_os_results_real_home_paths_still_flagged_P17():
    """The SAME files must still catch a REAL `/Users/<name>` path leaking into a transcript --
    the exemption above is scoped to `/home/` only, never a blanket per-file exemption."""
    for path in ("benchmark/results/some-model/agentbench_os.v1.jsonl",
                 "benchmark/results/agentbench_os_compare_2026-09-29.md",
                 "benchmark/results/agentbench_os_compare.json"):
        d = _diff(path, '{"answer": "/Users/someone/ws/project"}')
        found = piicheck.diff_violations(d)
        assert found, (path, "real /Users path must still be flagged")
        assert "someone" in str(found[0])


def test_agentbench_os_results_home_exemption_does_not_leak_to_other_files_P17():
    """A file that merely LOOKS similar (wrong directory, wrong stem) gets no exemption -- the
    glob match is narrow on purpose."""
    d = _diff("benchmark/results/some-model/not_agentbench.jsonl", 'cd /home/user1/os/linux')
    assert piicheck.diff_violations(d), "must NOT be exempt outside the narrow glob"


def test_the_committed_corpus_is_clean():
    """Regression: run the checker over every tracked file AS COMMITTED (HEAD content, not
    the working tree). It must be silent — otherwise the scrub was incomplete, or the
    pattern is too broad to live in a blocking hook.

    Committed content is deliberate: the registry carries INTENTIONAL local `hf_path`
    dirt in the working tree by design (swapped out at commit time by
    scripts/registry_commit.sh), so reading the working tree kept this test permanently
    red without guarding anything the pre-commit hook doesn't already guard. What this
    test vouches for is HISTORY: a leak that reached HEAD still fails it."""
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    files = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True,
                           text=True).stdout.split()
    # Only files that differ from HEAD need the (slower) committed-content read; the
    # rest are byte-identical on disk.
    dirty = set(subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=root,
                               capture_output=True, text=True).stdout.split())
    hits = []
    for f in files:
        if piicheck.is_exempt(f):
            continue
        if f in dirty:
            shown = subprocess.run(["git", "show", f"HEAD:{f}"], cwd=root,
                                   capture_output=True, text=True)
            if shown.returncode != 0:
                continue  # tracked but new relative to HEAD — nothing committed to vouch for
            text = shown.stdout
        else:
            try:
                text = (root / f).read_text(errors="replace")
            except (OSError, IsADirectoryError):
                continue
        hits += piicheck.violations(text, path=f)
    assert hits == [], hits[:10]
