"""S29 (spec docs/specs/s29-tg2-testable.md): the tg2 carrier's permission decision as opencode 2.0.20 makes it, the full-suite
commands the agent may run (T3) and the lookups that stay denied (T4), and the two positives records (acceptance 6): per
language whether the agent ran the full suite, and the lookup denies on the live carrier.

`wildcard_match` is a port of opencode 2.0.20 `util/wildcard.ts` (the same port as `tests/test_m61_round7.match`): `*` any run,
`?` one character, every other character literal, a trailing ` *` optional, case-sensitive, `.` matches newlines. A rule set
is evaluated LAST-match-wins; no matching rule = allow (the carrier's default for `shell`). A shell command is decided on the
whole text and on each parsed command (`split_commands`); any deny denies (opencode matches each parsed command)."""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TG2_CARRIER = REPO / "benchmark/opencode_bench_v2_web_tg2.json"
LANGS = ("rust", "javascript", "java", "cpp")


def wildcard_match(text, pattern):
    e = re.sub(r"[.+^${}()|\[\]\\]", lambda m: "\\" + m.group(0), pattern.replace("\\", "/"))
    e = e.replace("*", ".*").replace("?", ".")
    if e.endswith(" .*"):
        e = e[:-3] + "( .*)?"
    return re.match("^" + e + "$", text.replace("\\", "/"), re.S) is not None


def decide(permissions, action, resource):
    """The effect of the last rule of `action` whose pattern matches `resource`; `allow` when none does."""
    effect = "allow"
    for rule in permissions:
        if rule.get("action") == action and wildcard_match(resource, rule.get("resource", "")):
            effect = rule.get("effect")
    return effect


def split_commands(command):
    """The simple commands of a shell line: split on unquoted `&&`, `||`, `;`, `|`, `&` and newlines; the bodies of `$(...)` and
    backticks are commands too. A superset of opencode's parsed commands (the whole line is decided as well)."""
    out, cur, quote, i, n = [], [], None, 0, len(command)
    subs = re.findall(r"\$\(([^()]*)\)|`([^`]*)`", command)
    while i < n:
        c = command[i]
        if quote:
            cur.append(c)
            if c == quote:
                quote = None
            elif c == "\\" and quote == '"' and i + 1 < n:
                cur.append(command[i + 1])
                i += 1
        elif c in "'\"":
            quote = c
            cur.append(c)
        elif command.startswith(("&&", "||"), i):
            out.append("".join(cur))
            cur = []
            i += 1
        elif c in ";|&\n":
            out.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    out.append("".join(cur))
    for a, b in subs:
        out += split_commands(a or b)
    return [c.strip() for c in out if c.strip()]


def shell_decision(permissions, command):
    """`deny` when the whole command or any of its parsed commands is denied, else `allow`."""
    return "deny" if any(decide(permissions, "shell", c) == "deny" for c in [command, *split_commands(command)]) else "allow"


def load_permissions(carrier=None):
    return json.loads(Path(carrier or TG2_CARRIER).read_text())["permissions"]


# -------------------------------------------------------------------------------------------------- T3: never denied
# The full-suite command (`corpus_tg2.FULL_SUITE_COMMANDS`) and its ordinary variants (build only, one test, rebuild), per
# language; `{slug}` / `{test}` are filled per item. The words below are local flags, files and paths (allowed).
FULL_SUITE_VARIANTS = {
    "rust": ("cargo test", "cargo build", "cargo test --no-run", "cargo test {test}", "cargo test -- --include-ignored",
             "cargo test -- --nocapture", "cargo clean && cargo test", "cargo test 2>&1 | tail -40",
             "cargo test --offline", "cd $WORK && cargo test"),
    "java": ("./gradlew test", "./gradlew compileJava", "./gradlew compileTestJava", "./gradlew test --tests {test}",
             "./gradlew clean test", "./gradlew test --offline", "bash ./gradlew --offline --no-daemon test",
             "./gradlew test --console=plain 2>&1 | tail -60", "gradle test"),
    "javascript": ("npm install && npm test", "npm install", "npm test", "npm ci && npm test", "npx jest",
                   "npx jest {slug}.spec.js", "npx jest -t \"{test}\"", "npm test -- --watchAll=false 2>&1 | tail -40"),
    "cpp": ("cmake -S . -B build && cmake --build build", "cmake -S . -B build", "cmake --build build", "./build/{slug}",
            "./build/{slug} \"{test}\"", "rm -rf build && cmake -S . -B build && cmake --build build",
            "cmake -S . -B build -DEXERCISM_RUN_ALL_TESTS=ON && cmake --build build && ./build/{slug}",
            "mkdir -p build && cd build && cmake .. -DEXERCISM_RUN_ALL_TESTS=ON && make",
            "clang++ -std=c++17 -I. -Itest -DEXERCISM_RUN_ALL_TESTS *.cpp test/tests-main.cpp -o /tmp/t && /tmp/t",
            "cmake -S . -B build -DEXERCISM_TEST_SUITE=OFF && cmake --build build 2>&1 | tail -40"),
}
LOCAL_WORD_COMMANDS = ("grep -n EXERCISM *_test.cpp", "grep -rn exercism .", "cat exercism-notes.txt", "ls ~/exercism",
                       "cat /tmp/Exercism/README.md", "echo EXERCISM_RUN_ALL_TESTS", "sed -n 1,20p CMakeLists.txt",
                       "./gradlew test -Dexercism.local=true", "cat exercism.log", "ls exercism.local",  # allow-pii-pattern
                       "ls problem-specifications-notes", "cat ~/problem-specifications/README.md",
                       "cargo test && ls problem-specifications-notes", "cmake --build build && cat exercism.log")

# -------------------------------------------------------------------------------------------------- T4: lookups denied
# Per deny class: the shell lookups (curl / wget / git clone / gh of the hosts or repos, any case) and the web fetches.
LOOKUP_SHELL = {
    "exercism-host": ("curl https://exercism.org/tracks/rust/exercises/acronym/solutions",
                      "wget -qO- https://EXERCISM.ORG/tracks/cpp/exercises/diamond", "curl -s https://Exercism.org/api/v2/x",
                      "curl https://exercism.io/tracks/java", "curl https://api.exercism.org/v1/solutions/latest"),
    "exercism-github": ("git clone https://github.com/exercism/rust", "git clone https://GitHub.com/Exercism/rust.git",
                        "git clone git@github.com:exercism/cpp.git", "git clone --depth 1 https://GITHUB.COM/EXERCISM/java",
                        "curl https://raw.githubusercontent.com/exercism/rust/main/exercises/practice/acronym/.meta/example.rs",
                        "curl https://api.github.com/repos/exercism/javascript/contents/exercises",
                        "curl https://cdn.jsdelivr.net/gh/exercism/cpp/exercises/practice/diamond/.meta/example.cpp",
                        "gh repo clone exercism/rust", "gh api repos/exercism/java/contents/exercises"),
    "problem-specifications": ("curl https://raw.githubusercontent.com/exercism/problem-specifications/main/exercises/x/canonical-data.json",
                               "git clone https://github.com/someone/Problem-Specifications",
                               "wget https://example.org/PROBLEM-SPECIFICATIONS/canonical-data.json"),
    "exercism-cli": ("exercism download --track=rust --exercise=acronym", "brew install exercism"),
    "code-search": ("curl 'https://grep.app/api/search?q=fn+abbreviate'", "curl 'https://api.github.com/search/code?q=abbreviate'",
                    "curl 'https://github.com/search?q=abbreviate&type=code'", "curl https://sourcegraph.com/search?q=x",
                    "curl https://SourceGraph.com/search?q=x", "curl https://searchcode.com/api/codesearch_I/?q=x",
                    "curl https://GREP.APP/search?q=x", "gh search code abbreviate"),
    "compound": ("cmake -S . -B build -DEXERCISM_RUN_ALL_TESTS=ON && curl https://exercism.org/tracks/cpp",
                 "cargo test; git clone https://github.com/exercism/rust /tmp/r",
                 "./gradlew test && wget https://raw.githubusercontent.com/exercism/java/main/x.java",
                 "npm test || curl -s https://Exercism.org/x | head", "echo $(curl https://exercism.org/x)"),
    "repo-shorthand": ("npx degit exercism/rust /tmp/r", "degit exercism/cpp#main /tmp/c", "npx tiged Exercism/java /tmp/j",
                       "npx giget gh:exercism/rust /tmp/r", "npm install github:exercism/rust", "npm i exercism/javascript",
                       "pnpm add exercism/rust", "yarn add GitHub:Exercism/rust", "npm i exercism", "npm install -g EXERCISM",
                       "npx exercism download --exercise=x", "bunx degit exercism/javascript x",
                       "npx degit someone/problem-specifications /tmp/ps", "npm i github:someone/Problem-Specifications"),
    "github-org-api": ("curl -s https://api.github.com/orgs/exercism/repos", "curl -s https://api.github.com/users/exercism",
                       "curl https://API.GITHUB.COM/ORGS/EXERCISM/repos", "gh api orgs/exercism/repos",
                       "gh api /users/Exercism", "gh repo list exercism --limit 200"),
    "cli-not-first": ("cargo test && gh repo clone exercism/rust", "cd /tmp && gh repo clone exercism/rust",
                      "cargo test; gh api repos/exercism/rust/contents", "npm test && gh search code abbreviate",
                      "cmake --build build && exercism download --track=cpp --exercise=diamond",
                      "(exercism download --exercise=x)", "cd /tmp; Exercism download --exercise=x",
                      "cargo build && gh api orgs/exercism/repos", "true | gh repo list exercism"),
}
LOOKUP_WEB = {
    "exercism-host": ("https://exercism.org/tracks/rust/exercises/acronym", "https://Exercism.org/x", "https://EXERCISM.ORG/x"),
    "exercism-github": ("https://github.com/exercism/rust/tree/main/exercises",
                        "https://raw.githubusercontent.com/exercism/cpp/main/x.cpp"),
    "problem-specifications": ("https://github.com/someone/problem-specifications",
                               "https://example.org/Problem-Specifications/x.json"),
    "code-search": ("https://grep.app/search?q=x", "https://github.com/search?q=x&type=code",
                    "https://api.github.com/search/code?q=x", "https://SourceGraph.com/search?q=x",
                    "https://searchcode.com/?q=x", "https://GREP.APP/search?q=x"),
}


def variants(lang, slug="item", test="t"):
    return [v.format(slug=slug, test=test) for v in FULL_SUITE_VARIANTS[lang]]


def lookup_record(permissions):
    """Acceptance 6 (lookup-denied record): every lookup probe of every deny class decided on `permissions`; `all_denied`
    when every one is `deny`, and the full-suite variants / local words of every language `allow`."""
    shell = {cls: {c: shell_decision(permissions, c) for c in cmds} for cls, cmds in LOOKUP_SHELL.items()}
    web = {cls: {u: decide(permissions, "webfetch", u) for u in urls} for cls, urls in LOOKUP_WEB.items()}
    allowed = {c: shell_decision(permissions, c) for lang in LANGS for c in variants(lang)}
    allowed.update({c: shell_decision(permissions, c) for c in LOCAL_WORD_COMMANDS})
    denied_ok = all(v == "deny" for d in (*shell.values(), *web.values()) for v in d.values())
    return dict(shell=shell, webfetch=web, local=allowed, all_denied=denied_ok,
                local_allowed=all(v == "allow" for v in allowed.values()))


# -------------------------------------------------------------------------------------------------- acceptance 6: ran
_FULL_SUITE_RE = {
    "rust": re.compile(r"(?:^|[\s;&|(])cargo\s+test\b"),
    "java": re.compile(r"(?:^|[\s;&|(])(?:\./gradlew|gradlew|gradle)\b[^;&|]*\btest\b"),
    "javascript": re.compile(r"(?:^|[\s;&|(])(?:npm\s+(?:run\s+)?test\b|npx\s+jest\b|jest\b)"),
    "cpp": re.compile(r"(?:^|[\s;&|(])(?:cmake\s+--build\b|make\b|\./build/\S+)"),
}


def _tool_events(events):
    for e in events or []:
        part = e.get("part") if isinstance(e, dict) else None
        if isinstance(e, dict) and e.get("type") == "tool_use" and isinstance(part, dict):
            state = part.get("state") if isinstance(part.get("state"), dict) else {}
            yield part.get("tool"), state


def full_suite_record(events, lang, permissions):
    """Acceptance 6 ("the agent ran the full suite"): the session's shell calls that run the language's full-suite command
    (a `tool_use` event, its command, its recorded status and the carrier's decision); `ran` when one completed and is allowed."""
    calls = []
    for tool, state in _tool_events(events):
        command = (state.get("input") or {}).get("command") if isinstance(state.get("input"), dict) else None
        if tool == "shell" and isinstance(command, str) and _FULL_SUITE_RE[lang].search(command):
            calls.append(dict(command=command[:400], status=state.get("status"), decision=shell_decision(permissions, command)))
    return dict(language=lang, calls=calls,
                ran=any(c["status"] == "completed" and c["decision"] == "allow" for c in calls),
                denied=sum(c["decision"] == "deny" for c in calls))
