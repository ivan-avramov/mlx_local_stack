"""P268 (C150, 2026-10-10): a bare `(( expr ))` command returns status 1 when expr evaluates to 0
(`((i++))` with i=0), and under `set -e` bash >= 4.1 exits on it; /bin/bash 3.2 does not. runserver.sh
aborted on its first spinner tick under Homebrew bash 5.3. Use `i=$((i + 1))` or guard the command."""
import re
import subprocess

from bench import paths

REPO = paths.repo_root()
BARE_ARITH = re.compile(r"^\s*\(\(.*\)\)\s*(;.*)?$")


def test_no_bare_arithmetic_command_in_errexit_scripts():
    files = subprocess.run(["git", "ls-files", "*.sh"], cwd=REPO, capture_output=True, text=True,
                           check=True).stdout.split()
    hits = []
    for f in files:
        if f.startswith("src/"):
            continue
        text = (REPO / f).read_text(errors="replace")
        if not re.search(r"^\s*set -[a-z]*e", text, re.M):
            continue
        hits += [f"{f}:{n}: {line.strip()}" for n, line in enumerate(text.splitlines(), 1)
                 if BARE_ARITH.match(line)]
    assert not hits, "bare (( )) under set -e exits on a zero result in bash >= 4.1:\n" + "\n".join(hits)
