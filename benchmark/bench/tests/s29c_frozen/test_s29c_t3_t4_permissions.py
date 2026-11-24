"""S29c T3 (the full-suite command and its ordinary variants are never denied) and T4 (a solution lookup stays denied).

Evaluated through the carrier's own rule set (`benchmark/opencode_bench_v2_web_tg2.json`, `permissions`). The repo exposes no
production matcher, so the rule set is evaluated as opencode 2.0.20 documents it (wildcard port of `util/wildcard.ts`, the one
`tests/test_m61_round7.py` verifies against the pinned binary) under every reading the repo cannot settle: last-matching-rule-wins
and any-deny-wins, a shell command taken whole and node by node (see s29c_support). "Denied" holds only if every reading denies;
"allowed" only if every reading allows. The real-opencode check (acceptance 2 "or a real opencode session") is not made here.
Classes: [FIX] fails on the baseline (`*xercism*` / `*XERCISM*` shell denies block the cpp build flag and any local path with the
word); [INV] holds on the baseline and must keep holding; [NEW] has no baseline counterpart."""
from __future__ import annotations

import json

import pytest

from bench.tests.s29c_frozen import s29c_support as S

SLUG = "zebra-puzzle"

# ordinary commands per language: the canonical suite command, build only, run one test, rebuild
ORDINARY = {
    "rust": ["cargo test", "cargo test -- --include-ignored", "cargo test --offline", "cargo build", "cargo build --release",
             "cargo test accumulate_empty", "cargo test -- --nocapture", "cargo clean && cargo test", "cargo check"],
    "java": ["./gradlew test", "gradle test", "./gradlew --offline test", "./gradlew test --tests ZebraPuzzleTest",
             "./gradlew build", "./gradlew compileJava", "./gradlew clean test", "bash ./gradlew --offline --no-daemon test"],
    "javascript": ["npm test", "npm run test", "npm install && npm test", "npx jest", "npx jest zebra-puzzle.spec.js",
                   "npm test -- -t 'resident who owns zebra'", "npm ci && npm test"],
    "cpp": ["cmake -S . -B build && cmake --build build && ./build/zebra-puzzle",
            "cmake -S . -B build -DEXERCISM_RUN_ALL_TESTS=ON && cmake --build build && ./build/zebra-puzzle",
            "cmake -B build -DEXERCISM_RUN_ALL_TESTS=ON", "cmake -B build -DEXERCISM_RUN_ALL_TESTS=ON -DCMAKE_BUILD_TYPE=Release",
            "cmake --build build", "cmake --build build --target zebra-puzzle -j8", "./build/zebra-puzzle",
            "./build/zebra-puzzle \"resident who owns zebra\"", "rm -rf build && cmake -B build && cmake --build build",
            "cmake -B build -DCMAKE_BUILD_TYPE=Release >/dev/null && cmake --build build -j8 2>&1 | tail -5 && ./build/zebra-puzzle",
            "cmake -DEXERCISM_RUN_ALL_TESTS=1 -S . -B build && cmake --build build 2>&1 | tail -20"],
}

# a local flag / file / path that merely contains the word is not a lookup
LOCAL_WITH_THE_WORD = [
    "cmake -B build -DEXERCISM_RUN_ALL_TESTS=ON", "cmake -B build -Dexercism_run_all_tests=ON",
    "grep -n EXERCISM_RUN_ALL_TESTS CMakeLists.txt", "echo $EXERCISM_RUN_ALL_TESTS", "cat zebra_puzzle_test.cpp | grep -c TEST_CASE",
    "cd /Users/me/exercism/cpp/zebra-puzzle && cmake -B build", "ls ~/exercism/rust", "ls /home/me/Exercism/java",
    "cat ./Exercism-notes.md", "cargo test --features exercism-local", "./gradlew test -Dexercism.local=true",
    "npm test --exercism-local", "ls problem-specifications-notes", "cat ~/problem-specifications/README.md",
    "cmake -B build -DEXERCISM_RUN_ALL_TESTS=ON && cmake --build build && ./build/zebra-puzzle",
]

LOOKUP_URLS = [          # exercism / problem-specifications content from outside
    "https://exercism.org/tracks/rust/exercises/accumulate",
    "https://exercism.org/tracks/cpp/exercises/zebra-puzzle/solutions",
    "https://exercism.io/tracks/java",
    "https://github.com/exercism/rust/blob/main/exercises/practice/accumulate/.meta/example.rs",
    "https://github.com/exercism/cpp",
    "https://raw.githubusercontent.com/exercism/rust/main/exercises/practice/accumulate/.meta/example.rs",
    "https://github.com/exercism/problem-specifications",
    "https://github.com/exercism/problem-specifications/blob/main/exercises/zebra-puzzle/canonical-data.json",
    "https://raw.githubusercontent.com/exercism/problem-specifications/main/exercises/two-fer/canonical-data.json",
    "https://api.github.com/repos/exercism/java/contents/exercises",
]
SEARCH_URLS = [          # code-search sites (the other lookup denies)
    "https://api.github.com/search/code?q=zebra+puzzle+language:rust",
    "https://github.com/search?q=zebra-puzzle&type=code",
    "https://grep.app/search?q=zebra",
    "https://sourcegraph.com/search?q=zebra",
    "https://searchcode.com/?q=zebra",
]
DOCS_URLS = [
    "https://doc.rust-lang.org/std/vec/struct.Vec.html", "https://docs.gradle.org/8.7/userguide/java_testing.html",
    "https://cmake.org/cmake/help/latest/command/add_definitions.html", "https://en.wikipedia.org/wiki/Zebra_Puzzle",
    "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/map", "https://github.com/catchorg/Catch2",
]


def shell_lookups(url):
    host_path = url
    return [f"curl -s {url}", f"curl -sL \"{url}\" -o out.txt", f"wget -qO- {url}", f"curl {url} | head -50",
            f"python3 -c \"import urllib.request;print(urllib.request.urlopen('{url}').read())\"",
            f"git clone {url} /tmp/lookup" if "github.com" in host_path else f"curl -fsSL {url}"]


# --------------------------------------------------------------------------------------------------------- T3
@pytest.mark.parametrize("lang,command", [(lang, c) for lang in S.LANGS for c in ORDINARY[lang]])
def test_t3_ordinary_commands_are_allowed(lang, command):
    """[FIX for the cpp commands with EXERCISM_RUN_ALL_TESTS / INV for the rest] the language's suite command and ordinary variants are allowed."""
    assert S.allowed_everywhere("shell", command), S.explain("shell", command)


@pytest.mark.parametrize("command", LOCAL_WITH_THE_WORD)
def test_t3_a_local_flag_file_or_path_with_the_word_is_not_a_lookup(command):
    """[FIX] a build flag / file / path that merely contains `exercism` (any case) is allowed."""
    assert S.allowed_everywhere("shell", command), S.explain("shell", command)


@pytest.mark.parametrize("command", LOCAL_WITH_THE_WORD)
def test_t3_the_same_local_commands_chained_with_an_ordinary_build_are_allowed(command):
    """[FIX] a permitted command chained with a permitted local command stays permitted."""
    for chained in (f"{command} && cmake --build build", f"cd . ; {command} | tee out.txt"):
        assert S.allowed_everywhere("shell", chained), S.explain("shell", chained)


@pytest.mark.parametrize("url", DOCS_URLS)
def test_t3_ordinary_documentation_fetches_are_allowed(url):
    """[INV] webfetch of ordinary documentation stays allowed."""
    assert S.allowed_everywhere("webfetch", url), S.explain("webfetch", url)
    assert S.allowed_everywhere("shell", f"curl -s {url}"), S.explain("shell", f"curl -s {url}")


# --------------------------------------------------------------------------------------------------------- T4
@pytest.mark.parametrize("base", LOOKUP_URLS)
def test_t4_webfetch_of_exercism_and_problem_specifications_stays_denied_in_every_case(base):
    """[INV] webfetch of Exercism / problem-specifications content is denied, as written and in Title / UPPER case."""
    for url in S.case_variants(base):
        assert S.denied_everywhere("webfetch", url), S.explain("webfetch", url)


@pytest.mark.parametrize("base", LOOKUP_URLS)
def test_t4_shell_fetches_of_exercism_and_problem_specifications_stay_denied_in_every_case(base):
    """[INV on the baseline; the guard against the T3 fix opening a hole] curl / wget / git clone / urllib of those hosts or repos
    are denied, any case."""
    for url in S.case_variants(base):
        for command in shell_lookups(url):
            assert S.denied_everywhere("shell", command), S.explain("shell", command)


@pytest.mark.parametrize("command", [
    "git clone git@github.com:exercism/rust.git", "git clone git@github.com:exercism/problem-specifications.git",
    "gh repo clone exercism/rust", "gh repo clone exercism/problem-specifications",
    "gh api repos/exercism/problem-specifications/contents/exercises",
    "gh api repos/exercism/cpp/contents/exercises/practice/zebra-puzzle/.meta/example.cpp",
    "git clone ssh://git@github.com/exercism/java", "git clone https://github.com/exercism/java.git"])
def test_t4_repo_clone_forms_stay_denied(command):
    """[INV] the repository clone / API forms of the lookup stay denied (lower, Title and UPPER case of the word)."""
    for variant in S.case_variants(command):
        assert S.denied_everywhere("shell", variant), S.explain("shell", variant)


@pytest.mark.parametrize("lang", S.LANGS)
@pytest.mark.parametrize("lookup", ["curl -s https://exercism.org/tracks/cpp/exercises/zebra-puzzle",
                                    "wget -q https://raw.githubusercontent.com/exercism/problem-specifications/main/exercises/x/canonical-data.json",
                                    "git clone https://github.com/exercism/problem-specifications /tmp/ps",
                                    "curl -s https://EXERCISM.ORG/tracks/cpp", "curl -s https://Exercism.org/tracks/cpp"])
def test_t4_a_lookup_inside_a_compound_command_is_denied(lang, lookup):
    """[INV on the baseline - but VACUOUS there for cpp, whose build flag is itself denied; it bites once T3 is fixed] a permitted build
    command chained with a fetch (before, after, piped, in a subshell) is denied."""
    for command in ORDINARY[lang][:3] + [S.CANONICAL[lang].format(slug=SLUG)]:
        for compound in (f"{command} && {lookup}", f"{lookup} && {command}", f"{command} ; {lookup}",
                         f"{command} | tee build.log && {lookup} -o out.json", f"{command} || {lookup}",
                         f"( {command} && {lookup} )", f"{command} && echo $({lookup})"):
            assert S.denied_everywhere("shell", compound), S.explain("shell", compound)


@pytest.mark.parametrize("url", SEARCH_URLS)
def test_t4_code_search_sites_stay_denied(url):
    """[INV] the other lookup denies (code-search sites) by webfetch and by shell."""
    assert S.denied_everywhere("webfetch", url), S.explain("webfetch", url)
    for command in (f"curl -s '{url}'", f"wget -qO- {url}", f"curl -s {url} && cargo test", f"cargo test && curl -s {url}"):
        assert S.denied_everywhere("shell", command), S.explain("shell", command)


@pytest.mark.parametrize("url", SEARCH_URLS)
def test_t4_code_search_sites_stay_denied_in_upper_case_host(url):
    """[FIX] spec: the lookup denies hold 'for any letter case' - the host in UPPER case (hosts are case-insensitive)."""
    upper = url.replace("https://", "").split("/", 1)
    host = upper[0].upper()
    variant = "https://" + host + ("/" + upper[1] if len(upper) > 1 else "")
    assert S.denied_everywhere("webfetch", variant), S.explain("webfetch", variant)
    assert S.denied_everywhere("shell", f"curl -s {variant}"), S.explain("shell", f"curl -s {variant}")


# --------------------------------------------------------------------------------- the carrier's other rules (invariants)
def test_inv_the_other_carrier_denies_are_unchanged():
    """[INV] question / websearch / external_directory / execute / subagent stay denied; webfetch stays default-allowed."""
    rules = json.loads(S.CARRIER.read_text())["permissions"]
    for action in ("external_directory", "question", "websearch", "execute", "subagent"):
        assert dict(action=action, resource="*", effect="deny") in rules, action
    assert dict(action="webfetch", resource="*", effect="allow") in rules


def test_inv_the_carrier_is_still_the_tg2_carrier():
    doc = json.loads(S.CARRIER.read_text())
    assert doc["compaction"] == {"auto": False} and doc["agents"]["title"] == {"disabled": True}
    assert set(doc["providers"]["mlx-local"]["models"]) >= {"Qwen3.8-27B-mlx-uniform-4bit", "Ornith-1.0-35B-mlx-uniform-4bit"}


# ------------------------------------------------------------------------------------------ instrument known positives
def test_instrument_the_matcher_reproduces_the_recorded_baseline_block():
    """[INV] known positive of the evaluator: the rules of the baseline carrier (git blob at the baseline commit) deny the cpp
    build flag, and allow cargo test - the 39 / 40 sessions' shape."""
    import subprocess
    raw = subprocess.run(["git", "-C", str(S.REPO), "show", f"{S.BASELINE}:benchmark/opencode_bench_v2_web_tg2.json"],
                         capture_output=True, text=True)
    if raw.returncode:
        pytest.skip("the baseline commit is not in this repository")
    old = json.loads(raw.stdout)["permissions"]
    flag = "cmake -B build -DEXERCISM_RUN_ALL_TESTS=ON && cmake --build build"
    assert not S.allowed_everywhere("shell", flag, old)
    assert S.denied_everywhere("shell", "cmake -B build -DEXERCISM_RUN_ALL_TESTS=ON", old)
    assert S.allowed_everywhere("shell", "cargo test", old)
    assert S.denied_everywhere("shell", "curl -s https://exercism.org/x", old)
    assert S.denied_everywhere("webfetch", "https://github.com/exercism/problem-specifications", old)
