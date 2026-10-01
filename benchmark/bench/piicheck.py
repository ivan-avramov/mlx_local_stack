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
  * dash-flattened absolute home paths — `-Users-<name>-`, `-home-<name>-`. Tools like dsh turn
    an absolute path into a filename/session-log id by replacing every `/` with `-`; same
    username whitelist. An ordinary hyphenated word that happens to fit the shape (`-home-page-`)
    is accepted residual risk, same as the slash form already accepts `/home/page/` — use
    `allow-pii-pattern` for a genuine false positive.
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

import fnmatch
import re
from dataclasses import dataclass

# A line whose PURPOSE is to document or test these patterns must be able to contain them.
ALLOW_MARKER = "allow-pii-pattern"

# This module and its test necessarily carry example PII; exempting by path beats inline markers.
EXEMPT_PATHS = (
    "benchmark/bench/piicheck.py",
    "benchmark/bench/tests/test_pii_check.py",
    # M54: THUDM/AgentBench os-std task descriptions are GUEST-OS Linux sysadmin scenarios quoted
    # verbatim from upstream (Apache-2.0) — "/home/user1/", "/home/student/", etc. name fictional
    # accounts INSIDE the task's docker sandbox, never a path on this (or any real) host. One
    # vendored jsonl with no per-line comment syntax available; same class as the BFCL/IFEval
    # corpus exemptions above (`datasets`, fake emails) — exempt the file, not the pattern.
    "benchmark/corpora/agentbench_os_v1.jsonl",
)

# The sanctioned placeholder vocabulary. A path segment from this set is a template, not a person:
# `config.example.sh` ships `/home/remoteuser/...` on purpose, and the scrubbed manifests read
# `$HOME/models/...`. Shell-variable forms never match the path patterns below at all (they do not
# start with /Users or /home); this list covers the LITERAL placeholder usernames.
PLACEHOLDER_USERS = frozenset({"remoteuser", "user", "username", "youruser", "me", "REDACTED",
                               # BFCL corpus fiction (/user/home/datasets/…), quoted verbatim in
                               # committed result rows — a dataset directory, not a person.
                               "datasets"})

# A line whose PURPOSE is this check's own pattern name, kept separate from the `why` string a
# reader sees — used ONLY to selectively suppress the `/home/` pattern (and no other) in the
# narrow set of files matched by `_GUEST_OS_HOME_EXEMPT_GLOBS` below.
_HOME_PATH_WHY = "absolute home path with a username (/home/)"

_PATTERNS: tuple[tuple[str, str], ...] = (
    # Split from a single `(?:Users|home)` alternation (pre-17th-round) so `/home/` can be
    # exempted PATH-SCOPED without also exempting `/Users/` in the same files — see
    # `_GUEST_OS_HOME_EXEMPT_GLOBS`. The username is captured so the message can name what leaked.
    (r"/Users/([A-Za-z0-9_][A-Za-z0-9_.-]*)/", "absolute home path with a username"),
    (r"/home/([A-Za-z0-9_][A-Za-z0-9_.-]*)/", _HOME_PATH_WHY),
    # The flattened form uses `-` as the (former) path separator, so the username capture must
    # stop at the next `-` rather than allowing one through, unlike the slash form above.
    (r"-(?:Users|home)-([A-Za-z0-9_.]+)-", "dash-flattened absolute home path with a username"),
    (r"\bhf_[A-Za-z0-9]{20,}", "Hugging Face token"),
    (r"\bsk-[A-Za-z0-9_-]{20,}", "API key"),
    (r"\bghp_[A-Za-z0-9]{20,}", "GitHub token"),
    (r"\bAKIA[A-Z0-9]{16}\b", "AWS access key id"),
    (r"\b[a-z0-9][a-z0-9-]{2,}\.local\b", "mDNS hostname"),
)
_COMPILED = tuple((re.compile(p), why) for p, why in _PATTERNS)

# 17th cold review round: AgentBench os-std RESULT/compare artifacts (model answers and tool
# output from a Linux guest-OS sandbox, THUDM/AgentBench corpus, Apache-2.0) quote the SAME
# fictional `/home/<name>/` guest accounts as the corpus itself (e.g. `/home/user1/`,
# `/home/jack/`) — never a path on this or any real host. Unlike `EXEMPT_PATHS` (a WHOLE-FILE
# exemption, right for the corpus's own one-row-per-line jsonl with no comment syntax), these
# files are expected to otherwise carry genuine content worth checking — a REAL `/Users/<name>`
# path leaking into a transcript must still be flagged — so only the `/home/` pattern is
# suppressed here, by path glob, never the whole file.
_GUEST_OS_HOME_EXEMPT_GLOBS = (
    "benchmark/results/*/agentbench_os*.jsonl",
    "benchmark/results/agentbench_os_compare*.md",
    "benchmark/results/agentbench_os_compare*.json",
)


def _is_guest_os_home_exempt(path: str) -> bool:
    return any(fnmatch.fnmatchcase(path, g) for g in _GUEST_OS_HOME_EXEMPT_GLOBS)


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
    home_exempt = _is_guest_os_home_exempt(path)
    for offset, raw in enumerate(text.splitlines() or [text]):
        if ALLOW_MARKER in raw:
            continue
        for rx, why in _COMPILED:
            if home_exempt and why == _HOME_PATH_WHY:
                continue
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
