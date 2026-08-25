"""PII checker for ADDED lines of a staged diff — the repo is PUBLIC.

WHY THIS EXISTS, concretely. AGENTS.md forbids absolute home paths, usernames, hostnames and
tokens in committed content, and says to "sanity-check the staged diff before every commit".
That was carried by the author, and it failed: 11 tracked provenance manifests under
`benchmark/results/` reached the public remote with a real username in their `hf_path`, imported
in bulk with 286 other result files where no one reads every line. The naming hook that already
scans the staged diff was not looking for this. Now something is.

SCOPE, and what is deliberately NOT checked. A hook that blocks commits must have a near-zero
false-positive rate or it gets bypassed, so this checks only patterns that are unambiguous:

  * absolute home paths — `/Users/<name>/`, `/home/<name>/`. The placeholder vocabulary
    (`$HOME`, `$STACK_REPO`, `$REMOTE_REPO`, `remoteuser`, …) is allowed by name.
  * secret-shaped tokens — `hf_…`, `sk-…`, `ghp_…`, `AKIA…`.
  * mDNS hostnames — `<host>.local`.

EMAILS ARE NOT CHECKED, on purpose. The benchmark corpus is full of them: IFEval and BFCL items
embed fake addresses in prompts (`alex.chen@email.com`, `firstname.lastname@gmail.com`), and the
committed result rows quote those prompts verbatim. A blocking email rule would flag hundreds of
legitimate data lines, and the first thing a blocked author does to a noisy hook is delete it.
Real addresses in prose remain the author's responsibility, as they were.

Like `bench.modelnames`, this raises the floor rather than implementing the rule.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# A line whose PURPOSE is to document or test these patterns must be able to contain them.
ALLOW_MARKER = "allow-pii-pattern"

# This module and its test necessarily carry example PII; exempting by path beats inline markers.
EXEMPT_PATHS = (
    "benchmark/bench/piicheck.py",
    "benchmark/bench/tests/test_pii_check.py",
)

# The sanctioned placeholder vocabulary. A path segment from this set is a template, not a person:
# `config.example.sh` ships `/home/remoteuser/...` on purpose, and the scrubbed manifests read
# `$HOME/models/...`. Shell-variable forms never match the path patterns below at all (they do not
# start with /Users or /home); this list covers the LITERAL placeholder usernames.
PLACEHOLDER_USERS = frozenset({"remoteuser", "user", "username", "youruser", "me", "REDACTED",
                               # BFCL corpus fiction (/user/home/datasets/…), quoted verbatim in
                               # committed result rows — a dataset directory, not a person.
                               "datasets"})

_PATTERNS: tuple[tuple[str, str], ...] = (
    # An absolute home path. The username is captured so the message can name what leaked.
    (r"/(?:Users|home)/([A-Za-z0-9_][A-Za-z0-9_.-]*)/", "absolute home path with a username"),
    (r"\bhf_[A-Za-z0-9]{20,}", "Hugging Face token"),
    (r"\bsk-[A-Za-z0-9_-]{20,}", "API key"),
    (r"\bghp_[A-Za-z0-9]{20,}", "GitHub token"),
    (r"\bAKIA[A-Z0-9]{16}\b", "AWS access key id"),
    (r"\b[a-z0-9][a-z0-9-]{2,}\.local\b", "mDNS hostname"),
)
_COMPILED = tuple((re.compile(p), why) for p, why in _PATTERNS)


def is_exempt(path: str) -> bool:
    """True for a file whose PURPOSE is to define or test these patterns. Callers that scan whole
    files (the corpus regression test) must consult this, exactly as `diff_violations` does —
    otherwise this module and its test flag themselves."""
    return path.endswith(EXEMPT_PATHS)


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    why: str
    match: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.why} — {self.match}"


def violations(text: str, *, path: str = "<text>", line: int = 0) -> list[Violation]:
    """PII findings in `text`. `line` is the number of its FIRST line (0 for a bare string)."""
    out: list[Violation] = []
    for offset, raw in enumerate(text.splitlines() or [text]):
        if ALLOW_MARKER in raw:
            continue
        for rx, why in _COMPILED:
            for m in rx.finditer(raw):
                if m.groups() and m.group(1) in PLACEHOLDER_USERS:
                    continue
                out.append(Violation(path, line + offset, why, m.group(0)))
    return out


def diff_violations(diff: str) -> list[Violation]:
    """Findings on ADDED lines of a unified diff, at their NEW-file line number.

    Only `+` content is scanned. A commit that REMOVES a leak must never be blocked — otherwise
    the scrub commit is itself unmergeable. `+++` headers begin with `+` but are not content.
    """
    out: list[Violation] = []
    path, new_line = "<unknown>", 0
    for raw in diff.splitlines():
        if raw.startswith("+++ b/"):
            path = raw[6:].strip()
            continue
        if raw.startswith(("--- ", "+++ ", "diff --git", "index ", "similarity ", "rename ",
                           "new file", "deleted file", "old mode", "new mode", "Binary ")):
            continue
        if raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            new_line = int(m.group(1)) if m else 0
            continue
        if raw.startswith("+"):
            if not is_exempt(path):
                out.extend(violations(raw[1:], path=path, line=new_line))
            new_line += 1
        elif raw.startswith("-"):
            continue
        else:
            new_line += 1
    return out


def _main(argv: list[str]) -> int:
    import subprocess
    import sys

    diff = subprocess.run(["git", "diff", "--cached", "--unified=0"],
                          capture_output=True, text=True).stdout
    found = diff_violations(diff)
    if not found:
        return 0
    print(f"\nAGENTS.md: the repo is PUBLIC — no absolute home paths, usernames, hostnames or "
          f"tokens. {len(found)} in staged changes:\n", file=sys.stderr)
    for v in found:
        print(f"  {v}", file=sys.stderr)
    print("\nUse a placeholder ($HOME, $STACK_REPO, $REMOTE_REPO, $REMOTE_HOST, $REMOTE_HOME) or a "
          f"relative path. A line that must SHOW a pattern may carry '{ALLOW_MARKER}'. "
          f"Bypass once: git commit --no-verify\n", file=sys.stderr)
    return 1


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
