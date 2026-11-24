"""S29 T3 / T4 (spec docs/specs/s29-tg2-testable.md v1.1, acceptance 2) by the carrier's own matcher (`bench.tg2_testable`, the
opencode 2.0.20 `Wildcard.match` port, last match wins, each parsed command): on the committed tg2 carrier the full-suite command
and its variants are allowed for every language and every item, a lookup of every deny class is denied (any case, compound
commands), a local flag / file / path containing the word is allowed; the recorded denied cpp build commands (the known
positive, `.fe-material/example-denied-cpp-session.md`) are denied by the old carrier and allowed by the new one. The carrier
is generated (configgen, no drift) and differs from tg1's only in its lookup rules."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from bench import tg2_testable as tt

BENCH = Path(__file__).resolve().parents[1].parent
REPO = BENCH.parent
TG1 = BENCH / "opencode_bench_v2_web_tg1.json"
TG2 = BENCH / "opencode_bench_v2_web_tg2.json"
UNIVERSE = json.loads((BENCH / "m65/tg2_universe.json").read_text())
LANGS = ("rust", "javascript", "java", "cpp")
VALID = sorted(i for i, e in UNIVERSE["items"].items() if e.get("status") == "valid")
# the three denied shell calls of the recorded cpp session (tg2-m76 A8, cpp/diamond), verbatim
RECORDED_DENIED = (
    "cmake -S . -B build -DEXERCISM_RUN_ALL_TESTS=ON >/dev/null && cmake --build build >/dev/null && ./build/diamond",
    "cmake -S . -B build -DEXERCISM_RUN_ALL_TESTS=ON",
    "clang++ -std=c++17 -I. -Itest -DEXERCISM_RUN_ALL_TESTS diamond.cpp diamond_test.cpp test/tests-main.cpp -o "
    "$STACK_WORKDIR/opencode-probe-v2/tmp/diamond/diamond-test && $STACK_WORKDIR/opencode-probe-v2/tmp/diamond/diamond-test",
)
RECORDED_ALLOWED = ("cmake -B build -DCMAKE_BUILD_TYPE=Release >/dev/null && cmake --build build -j8 2>&1 | tail -5 && "
                    "./build/diamond-test", "cmake --version")


@pytest.fixture(scope="module")
def new():
    return tt.load_permissions(TG2)


@pytest.fixture(scope="module")
def old():
    return tt.load_permissions(TG1)            # the pre-S29 tg2 carrier was tg1's, byte for byte (baseline test pinned it)


# ------------------------------------------------------------------------------------------------- the matcher itself
def test_the_matcher_is_opencodes_wildcard():
    from bench.tests.test_m61_round7 import match
    cases = [("git clone x", "git clone x *"), ("a/b\nc", "a*b?c"), ("ab", "a[bc]"), ("x.y", "x?y"), ("xay", "x.y"),
             ("curl https://Exercism.org/x", "*xercism*"), ("curl https://EXERCISM.ORG/x", "*xercism*"), ("exercism", "exercism *"),
             ("exercism download", "exercism *"), ("myexercism download", "exercism *")]
    for text, pattern in cases:
        assert tt.wildcard_match(text, pattern) == match(text, pattern), (text, pattern)


def test_last_matching_rule_wins_and_default_allows():
    rules = [dict(action="webfetch", resource="*", effect="allow"), dict(action="webfetch", resource="*bad*", effect="deny")]
    assert tt.decide(rules, "webfetch", "https://bad.example") == "deny"
    assert tt.decide(rules, "webfetch", "https://ok.example") == "allow"
    assert tt.decide(rules[::-1], "webfetch", "https://bad.example") == "allow"
    assert tt.decide(rules, "shell", "anything") == "allow"


def test_compound_commands_are_split():
    assert tt.split_commands("a && b || c; d | e & f\ng") == list("abcdefg")
    assert tt.split_commands("echo 'x && y' && z") == ["echo 'x && y'", "z"]
    assert "curl u" in tt.split_commands("echo $(curl u)")


# ------------------------------------------------------------------------------------------------- the known positive
@pytest.mark.parametrize("command", RECORDED_DENIED)
def test_the_recorded_denied_build_commands_are_denied_by_the_old_carrier_and_allowed_now(old, new, command):
    assert tt.shell_decision(old, command) == "deny"
    assert tt.shell_decision(new, command) == "allow"


@pytest.mark.parametrize("command", RECORDED_ALLOWED)
def test_the_recorded_allowed_commands_stay_allowed(old, new, command):
    assert tt.shell_decision(old, command) == tt.shell_decision(new, command) == "allow"


# ------------------------------------------------------------------------------------------------- T3: never denied
@pytest.mark.parametrize("item", VALID)
def test_t3_the_full_suite_command_and_its_variants_are_allowed_for_every_item(new, item):
    from bench import corpus_tg2
    lang, slug = item.split("/", 1)
    entry = UNIVERSE["items"][item]
    test = entry["leaves"][0].split("::")[-1].split("#")[-1]
    commands = [corpus_tg2.FULL_SUITE_COMMANDS[lang], *tt.variants(lang, slug=slug, test=test)]
    assert corpus_tg2.FULL_SUITE_COMMANDS[lang] in tt.FULL_SUITE_VARIANTS[lang]
    denied = [c for c in commands if tt.shell_decision(new, c) != "allow"]
    assert denied == []


@pytest.mark.parametrize("command", tt.LOCAL_WORD_COMMANDS)
def test_t3_a_local_flag_file_or_path_with_the_word_is_allowed(new, command):
    assert tt.shell_decision(new, command) == "allow"


# ------------------------------------------------------------------------------------------------- T4: lookups denied
@pytest.mark.parametrize("cls, command", [(c, x) for c, xs in tt.LOOKUP_SHELL.items() for x in xs])
def test_t4_a_shell_lookup_of_every_class_is_denied(new, old, cls, command):
    assert tt.shell_decision(new, command) == "deny", (cls, command)


@pytest.mark.parametrize("cls, command", [(c, x) for c, xs in tt.LOOKUP_SHELL.items() for x in xs])
def test_t4_a_shell_lookup_is_denied_whole_line_and_per_command(new, cls, command):
    """TW F-B: denied when the line is taken whole AND when each parsed command is taken alone (any part denies)."""
    assert tt.decide(new, "shell", command) == "deny", ("whole", cls, command)
    assert any(tt.decide(new, "shell", c) == "deny" for c in tt.split_commands(command)), ("per-command", cls, command)


@pytest.mark.parametrize("cli", ["gh repo clone exercism/rust", "gh api repos/exercism/java/contents/x", "gh search code fizz",
                                 "gh api orgs/exercism/repos", "gh repo list exercism", "exercism download --exercise=x",
                                 "npx degit exercism/rust x", "npm i exercism/rust"])
@pytest.mark.parametrize("lead", ["cargo test && ", "cd /tmp && ", "cmake --build build; ", "npm test || ", "true | ",
                                  "( ", "echo $(", "cargo build &\n"])
def test_t4_an_anchored_cli_lookup_is_denied_when_not_the_first_command(new, cli, lead):
    command = lead + cli + (")" if lead.endswith("$(") else " )" if lead == "( " else "")
    assert tt.decide(new, "shell", command) == "deny", ("whole", command)
    assert any(tt.decide(new, "shell", c) == "deny" for c in tt.split_commands(command)), ("per-command", command)


@pytest.mark.parametrize("command", ["./gradlew test -Dexercism.local=true", "cat exercism.log", "ls exercism.local",  # allow-pii-pattern
                                     "cat exercism.json", "ls .exercism/config.json", "ls problem-specifications-notes",
                                     "cat ~/problem-specifications/README.md", "grep -rn problem-specifications .",
                                     "cmake -B build -DEXERCISM_RUN_ALL_TESTS=ON && cat exercism.log",
                                     "npm install --save-dev @exercism/babel-preset-javascript", "npm test --exercism-local",
                                     "cargo test --features exercism-local", "ls ~/exercism/rust", "ls exercism/rust"])
def test_t3_a_local_name_is_allowed_whole_line_and_per_command(new, command):
    """TW F-C + Sol P10: host / repository forms only; a local flag, file or path with the word is allowed under both readings.
    (`@exercism/*` npm packages are the track's lint / babel tooling, not the org's repositories: allowed.)"""
    assert tt.decide(new, "shell", command) == "allow", ("whole", command)
    assert all(tt.decide(new, "shell", c) == "allow" for c in tt.split_commands(command)), ("per-command", command)


@pytest.mark.parametrize("command", ["curl exercism.org/tracks/rust", "wget -qO- 'exercism.io/x'", "curl --url=exercism.org/x",
                                     "curl https://api.exercism.org/v2/x", "git clone git@exercism.org:x/y",
                                     "curl \"https://Exercism.IO/x\"", "curl HTTPS://EXERCISM.ORG/X"])
def test_t4_the_exercism_hosts_in_host_position_are_denied(new, command):
    assert tt.shell_decision(new, command) == "deny"


@pytest.mark.parametrize("command", [c for cls in ("exercism-host", "exercism-github", "problem-specifications", "exercism-cli",
                                                   "code-search", "compound") for c in tt.LOOKUP_SHELL[cls]])
def test_t4_every_lookup_the_candidate_1_carrier_denied_stays_denied(new, command):
    assert tt.shell_decision(new, command) == "deny"


@pytest.mark.parametrize("cls, url", [(c, x) for c, xs in tt.LOOKUP_WEB.items() for x in xs])
def test_t4_a_web_lookup_of_every_class_is_denied(new, cls, url):
    assert tt.decide(new, "webfetch", url) == "deny", (cls, url)


@pytest.mark.parametrize("url", ["https://doc.rust-lang.org/std/", "https://en.cppreference.com/w/cpp/algorithm/sort",
                                 "https://docs.oracle.com/en/java/javase/17/docs/api/", "https://developer.mozilla.org/en-US/"])
def test_t4_ordinary_documentation_stays_fetchable(new, url):
    assert tt.decide(new, "webfetch", url) == "allow"


@pytest.mark.parametrize("command", ["curl https://doc.rust-lang.org/std/", "cargo search serde", "npm view jest version",
                                     "git status", "git diff"])
def test_t4_ordinary_network_and_git_commands_stay_allowed(new, command):
    assert tt.shell_decision(new, command) == "allow"


def test_the_lookup_record_on_the_live_carrier():
    rec = tt.lookup_record(tt.load_permissions(TG2))
    assert rec["all_denied"] is True and rec["local_allowed"] is True
    old_rec = tt.lookup_record(tt.load_permissions(TG1))
    assert old_rec["local_allowed"] is False                        # the old carrier denied the cpp build (the bug)


# ------------------------------------------------------------------------------------------------- the carrier file
def test_the_tg2_carrier_is_tg1s_except_its_lookup_rules():
    a, b = json.loads(TG1.read_text()), json.loads(TG2.read_text())
    assert {k: v for k, v in a.items() if k != "permissions"} == {k: v for k, v in b.items() if k != "permissions"}
    lookup = lambda p: p["action"] in ("webfetch", "shell") and p["effect"] == "deny"  # noqa: E731
    assert [p for p in a["permissions"] if not lookup(p)] == [p for p in b["permissions"] if not lookup(p)]
    assert b["permissions"][-1] == dict(action="subagent", resource="*", effect="deny")
    shell = [p["resource"] for p in b["permissions"] if p["action"] == "shell"]
    assert "*xercism*" not in shell and "*XERCISM*" not in shell
    web = [p["resource"] for p in b["permissions"] if p["action"] == "webfetch"]
    assert web[0] == "*" and {"*xercism*", "*XERCISM*"} <= set(web)
    assert all(p["effect"] == "deny" for p in b["permissions"] if p["action"] == "shell")


def test_the_tg2_carrier_is_generated_without_drift():
    sys.path.insert(0, str(REPO))
    from configgen.__main__ import _render
    from configgen.source import load_source
    rendered = {name: (path, content) for name, path, content in _render(load_source(str(REPO / "main_models.yaml")))}
    path, content = rendered["opencode-bench-v2-web-tg2"]
    assert path == "benchmark/opencode_bench_v2_web_tg2.json" and (REPO / path).read_text() == content
    path, content = rendered["opencode-bench-v2-web-tg1"]
    assert (REPO / path).read_text() == content


def test_the_tg1_carrier_is_unchanged_from_the_baseline():
    try:
        base = subprocess.run(["git", "show", "cd334f773e6bc6d1e2f9f1344755e4df787b4fef:benchmark/opencode_bench_v2_web_tg1.json"],
                              cwd=REPO, capture_output=True, check=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        pytest.skip("the baseline commit is not in this clone")
    assert TG1.read_bytes() == base
