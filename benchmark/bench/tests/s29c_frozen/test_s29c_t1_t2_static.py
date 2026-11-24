"""S29c T1 (without docker, over the WHOLE tg2 universe) and T2 (the prompt names the command).

Classes: [FIX] fails on the baseline and passes when the spec is met; [INV] holds on the baseline and must keep holding; [NEW] a
requirement with no baseline counterpart.

T1 without docker: for every valid item the production preparation (`Tg2Corpus.prepare`) builds the tree the agent gets, the
production prompt names the command the agent runs, and the tests that command executes in that tree are enumerated statically:
they must be exactly the grader's graded leaves (`entry["leaves"]` minus `tg2_grade.OPTIONAL_LEAVES`). The command is the
backtick-quoted command(s) in the prompt's helper tail (T2); when the prompt names none, the language's canonical command
(`s29c_support.CANONICAL`) is used, so the baseline shows what a plain `cargo test` / `./gradlew test` / `npm test` /
cmake build runs today. Mechanism is free: enabling in the tree, a flag in the stated command, or a build default all count.
Static limits: rust is compared by (test file, fn name) for the top-level `tests/*.rs` leaves (leaves of `src/` unit tests (allow-shorthand: a C++ / English word, not a model name)
live in the solution file and are out of scope); cpp by TEST_CASE name; javascript and java by the absence of skip forms
(`xtest` / `@Disabled` / ...) beyond the frozen optional leaves, the same rule `tg2_grade.skip_form_violations` enforces.
The real parity (names and counts reported by the tools themselves) is in test_s29c_t1_docker.py."""
from __future__ import annotations

import pytest

from bench import tg2_grade as tg
from bench.tests.s29c_frozen import s29c_support as S


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    corpus = S.make_corpus()
    base = tmp_path_factory.mktemp("s29c-static")
    cache = {}

    def get(item):
        if item not in cache:
            prepared = S.prepare(corpus, item, base / item.replace("/", "__"))
            cache[item] = (prepared, S.prompt_of(corpus, prepared))
        return cache[item]
    return get


def _slug(item):
    return item.split("/", 1)[1]


# ------------------------------------------------------------------------------------------------------------- T1
@pytest.mark.parametrize("item", S.items_of("rust"))
def test_t1_rust_the_stated_command_runs_every_graded_test(item, world):
    """[FIX] rust: shipped tests are `#[ignore]`d; `cargo test` must run exactly the graded `tests/*.rs` leaves (none ignored)."""
    prepared, prompt = world(item)
    command = S.stated_or_canonical("rust", _slug(item), prompt)
    enabled, ignored = S.rust_enabled(prepared.work, command)
    graded = S.rust_graded(item)
    assert enabled == graded, (f"{item}: `{command}` runs {len(enabled)} of {len(graded)} graded tests; "
                               f"missing {sorted(graded - enabled)[:6]}, extra {sorted(enabled - graded)[:6]}, "
                               f"still ignored {len(ignored - enabled)}")


@pytest.mark.parametrize("item", S.items_of("cpp"))
def test_t1_cpp_the_stated_command_runs_every_graded_test(item, world):
    """[FIX] cpp: later TEST_CASEs sit behind EXERCISM_RUN_ALL_TESTS; the stated build+run must run exactly the graded cases."""
    prepared, prompt = world(item)
    command = S.stated_or_canonical("cpp", _slug(item), prompt)
    enabled, disabled, every = S.cpp_enabled(prepared.work, _slug(item), command)
    graded = {leaf.split("#", 1)[1] for leaf in S.graded_leaves(item)}
    unmatched, uncovered = S.cpp_cover(enabled, graded)
    assert not unmatched and not uncovered, (f"{item}: `{command}` runs {len(enabled)} test cases; graded leaves it does not run "
                                             f"{unmatched[:4]} ({len(unmatched)}), cases that grade nothing {uncovered[:4]}, "
                                             f"disabled by the macro {len(disabled)}")


@pytest.mark.parametrize("item", S.items_of("javascript"))
def test_t1_javascript_no_graded_test_is_skipped_in_the_tree(item, world):
    """[INV on the baseline: the materializer already rewrites xtest/xit/xdescribe] javascript: `npm test` skips only the grader's
    frozen optional leaves (their `test.skip` stays), never a graded one."""
    prepared, _prompt = world(item)
    skips = S.js_skips(prepared.work)
    assert tg.skip_form_violations(prepared.work, "javascript") == []
    assert sum(skips.values()) == len(S.optional_of(item)), (item, skips, sorted(S.optional_of(item)))


@pytest.mark.parametrize("item", S.items_of("java"))
def test_t1_java_no_graded_test_is_disabled_in_the_tree(item, world):
    """[INV on the baseline: the materializer already strips @Disabled] java: `gradle test` runs every graded test."""
    prepared, _prompt = world(item)
    assert S.java_skips(prepared.work) == {}
    assert tg.skip_form_violations(prepared.work, "java") == []


@pytest.mark.parametrize("lang", S.LANGS)
def test_t1_optional_leaves_stay_optional(lang, world):
    """[INV] the grader's frozen optional leaves are unchanged (T1 does not change what is graded)."""
    assert dict(tg.OPTIONAL_LEAVES) == {
        ("javascript", "palindrome-products"): frozenset(
            {"palindrome-products.spec.js::Palindromes largest palindrome from four digit factors"}),
        ("javascript", "robot-name"): frozenset({"robot-name.spec.js::Robot all the names can be generated"})}
    for item in S.items_of(lang):
        entry = S.universe_doc()["items"][item]
        assert S.optional_of(item) == set(entry["optional_excluded"]), item
        assert not (S.optional_of(item) & set(entry["leaves"])), item


# ------------------------------------------------------------------------------------------------------------- T2
@pytest.mark.parametrize("item", S.universe_items())
def test_t2_the_prompt_names_the_full_suite_command(item, world):
    """[FIX] every item's prompt helper tail names (in backticks) the command that runs the full suite."""
    prepared, prompt = world(item)
    found = S.stated_commands(prepared.lang, prompt)
    assert found, f"{item}: the prompt's helper tail names no `{prepared.lang}` build/test command in backticks: {S.helper_tail(prompt)[-400:]!r}"


@pytest.mark.parametrize("lang", S.LANGS)
def test_t2_the_prompt_keeps_its_existing_instructions(lang, world):
    """[INV] the specification, the editable / test file sentence and the tamper sentence stay; the helper sentence is extended, not dropped."""
    item = S.items_of(lang)[0]
    prepared, prompt = world(item)
    entry = prepared.entry
    assert f"Implement the solution in {', '.join(entry['solutions'])} so that the tests in {', '.join(entry['tests'])} pass." in prompt
    assert "Do NOT modify the tests or the build files except as stated below." in prompt
    assert "Do not create new files unless the specification requires them;" in prompt
    assert {"rust": "OFFLINE_CRATES.md", "java": "solution's package", "javascript": ".js files", "cpp": ".h / .cpp"}[lang] in prompt


@pytest.mark.parametrize("lang", S.LANGS)
def test_t2_the_stated_command_is_one_command_for_every_item_of_the_language(lang, world):
    """[NEW] the stated command does not depend on the item except through its slug (one rule per language)."""
    shapes = set()
    for item in S.items_of(lang)[:6]:
        prepared, prompt = world(item)
        shapes.add(tuple(c.replace(_slug(item), "<slug>").replace(prepared.name, "<slug>") for c in S.stated_commands(lang, prompt)))
    assert len(shapes) == 1 and next(iter(shapes)), shapes


@pytest.mark.parametrize("item", S.universe_items())
def test_t3_the_stated_command_is_allowed_by_the_carrier(item, world):
    """[FIX for cpp / needs T2 for the others] every command the prompt states, alone and chained as stated, is allowed by the carrier."""
    prepared, prompt = world(item)
    found = S.stated_commands(prepared.lang, prompt)
    assert found, f"{item}: the prompt states no command (T2)"
    for command in [*found, " && ".join(found)]:
        assert S.allowed_everywhere("shell", command), S.explain("shell", command)


# ------------------------------------------------------------------------------ instrument self-checks (known positives)
def test_instrument_rust_parser_known_positive():
    """[INV] the static Rust enumerator on a known text: attributes over several lines, `ignore` with a reason, a string holding `ignore`."""  # allow-shorthand
    text = '''
#[test]
fn a() {}
#[test]
#[ignore]
fn b() {}
#[test]
#[ignore = "slow"]
fn c() {}
#[test]
#[should_panic(
    expected = "ignore this"
)]
fn d() {}
fn helper() {}
'''
    assert S.rust_tests(text) == [("a", False), ("b", True), ("c", True), ("d", False)]


def test_instrument_cpp_parser_known_positive():
    """[INV] the static C++ enumerator: guard by EXERCISM_RUN_ALL_TESTS, nesting, an unrelated #ifdef."""  # allow-shorthand
    text = '''
#ifdef EXERCISM_TEST_SUITE
#include <x>
#endif
TEST_CASE("one") {}
#if defined(EXERCISM_RUN_ALL_TESTS)
TEST_CASE("two") {}
#ifdef OTHER
TEST_CASE("three") {}
#endif
#endif
TEST_CASE("four", "[tag]") {}
'''
    assert S.cpp_cases(text) == [("one", False), ("two", True), ("three", True), ("four", False)]
    assert S.cpp_default_on("if(${EXERCISM_RUN_ALL_TESTS})\n add_definitions(-DEXERCISM_RUN_ALL_TESTS)\nendif()", "cmake -B build") is False
    assert S.cpp_default_on("x", "cmake -B build -DEXERCISM_RUN_ALL_TESTS=ON") is True
    assert S.cpp_default_on("add_definitions(-DEXERCISM_RUN_ALL_TESTS)", "cmake -B build") is True
