"""Verify the polyglot corpus checkout is exactly the pinned revision and clean (for the languages the image uses)."""
import subprocess
import sys
from pathlib import Path

LANG_DIRS = ("rust", "java", "javascript", "cpp")


def verify(corpus, pinned):
    corpus = Path(corpus)
    head = subprocess.run(["git", "-C", str(corpus), "rev-parse", "HEAD"], capture_output=True, text=True)
    if head.returncode or head.stdout.strip() != pinned:
        sys.exit("corpus HEAD %r != pinned polyglot_sha %s" % (head.stdout.strip(), pinned))
    status = subprocess.run(["git", "-C", str(corpus), "status", "--porcelain", "--untracked-files=all", "--",
                             *LANG_DIRS], capture_output=True, text=True)
    if status.returncode or status.stdout.strip():
        sys.exit("corpus checkout is not clean for %s:\n%s" % (LANG_DIRS, status.stdout[:500]))
    return pinned


if __name__ == "__main__":
    print(verify(sys.argv[1], Path(sys.argv[2]).read_text().strip()))
