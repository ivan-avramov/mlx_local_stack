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
