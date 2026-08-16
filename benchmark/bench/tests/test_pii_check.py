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
                  'repo at $REMOTE_HOME/ws/stack'):
        assert piicheck.diff_violations(_diff("config.example.sh", added)) == [], added


def test_removed_lines_are_never_flagged():
    """A commit that DELETES a leak must not be blocked, or the scrub itself is unmergeable."""
    d = ("diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n"
         '-  "hf_path": "/Users/someone/models/x"\n'
         '+  "hf_path": "$HOME/models/x"\n')
    assert piicheck.diff_violations(d) == []


def test_the_committed_corpus_is_clean():
    """Regression: run the checker over every tracked file. It must be silent — otherwise the
    scrub was incomplete, or the pattern is too broad to live in a blocking hook."""
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    files = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True,
                           text=True).stdout.split()
    hits = []
    for f in files:
        if piicheck.is_exempt(f):
            continue
        p = root / f
        try:
            text = p.read_text(errors="replace")
        except (OSError, IsADirectoryError):
            continue
        hits += piicheck.violations(text, path=f)
    assert hits == [], hits[:10]
