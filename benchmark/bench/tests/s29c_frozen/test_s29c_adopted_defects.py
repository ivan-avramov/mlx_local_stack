"""S29c delivery 3: tests for the defects adopted from the review of candidate 1 (behaviour, evaluated like test_s29c_t3_t4_permissions:
the carrier's rule set under every reading - last-wins / deny-wins x whole command / each command node).

(a) package-manager / API lookups of the Exercism org stay denied, in case forms, alone and chained after a permitted build;
(b) a local flag / file containing the word `exercism.<anything>` is allowed (alone and chained);
(c) is in test_s29c_k1_kill_boundary.py (uid mismatch).
Classes: [INV] holds on the baseline (the broad `*xercism*` shell deny); [FIX] fails on the baseline."""
from __future__ import annotations

import re

import pytest

from bench.tests.s29c_frozen import s29c_support as S

BUILDS = ["cargo test", "./gradlew test", "npm install && npm test", "cmake -S . -B build && cmake --build build"]

LOOKUPS = [
    "npx degit exercism/rust", "npx tiged exercism/rust", "npm install github:exercism/rust", "npm i github:exercism/rust",
    "pnpm add github:exercism/rust", "pnpm add github:exercism/problem-specifications", "yarn add exercism/rust",
    "yarn add github:exercism/rust", "npm i exercism", "npm install exercism",
    "curl https://api.github.com/orgs/exercism/repos", "curl -s https://api.github.com/users/exercism",
    "curl -sL https://api.github.com/orgs/exercism/repos?per_page=100", "gh api orgs/exercism/repos", "gh api users/exercism",
    "gh api /orgs/exercism/repos --paginate",
]


def _forms(command):
    """As written, Title / UPPER case of the word, and the first letter of the word in the other case (`eXERCISM`)."""
    forms = S.case_variants(command)
    forms.append(re.sub("exercism", "eXERCISM", command, flags=re.I))
    return list(dict.fromkeys(forms))


@pytest.mark.parametrize("lookup", LOOKUPS)
def test_a_the_lookup_is_denied_in_every_case_form(lookup):
    """[INV] a package-manager install / degit / API listing of the Exercism org is denied by itself."""
    for form in _forms(lookup):
        assert S.denied_everywhere("shell", form), S.explain("shell", form)


@pytest.mark.parametrize("lookup", LOOKUPS)
def test_a_the_lookup_is_denied_chained_after_a_permitted_build(lookup):
    """[INV on the baseline] chained with a build / in a pipeline / a subshell, under the whole-line and the per-command readings."""
    for form in _forms(lookup):
        for build in BUILDS:
            for compound in (f"{build} && {form}", f"{form} ; {build}", f"{build} | tee out.log && {form}", f"cd /tmp && {form}",
                             f"( {build} && {form} )", f"{build} || {form}"):
                assert S.denied_everywhere("shell", compound), S.explain("shell", compound)


@pytest.mark.parametrize("command", [
    "npm install", "npm install && npm test", "npm i", "npm install jest", "npm install --save-dev @babel/core",
    "yarn add jest", "yarn install", "pnpm add lodash", "pnpm install", "npx jest", "npx degit someone/rust-template",
    "gh api repos/someone/project/issues", "gh repo clone someone/project", "curl -s https://api.github.com/orgs/someone/repos",
    "curl -s https://api.github.com/users/someone"])
def test_a_ordinary_installs_and_api_calls_stay_allowed(command):
    """[INV on the baseline] the new lookup forms must not take ordinary package installs or other orgs with them."""
    assert S.allowed_everywhere("shell", command), S.explain("shell", command)


@pytest.mark.parametrize("command", [
    "./gradlew test -Dexercism.local=true", "cat exercism.log", "ls exercism.local", "grep -n TODO exercism.local.cfg", "cargo test --features exercism.local", "tail -n 50 exercism.log",  # allow-pii-pattern
    "cat Exercism.log", "cat EXERCISM.LOG"])
def test_b_a_local_name_with_the_word_and_a_suffix_is_allowed(command):
    """[FIX] `exercism.<anything>` as a local flag / file name is not a lookup (the candidate's `?`-first-letter host forms match
    `exercism.lo…`)."""
    assert S.allowed_everywhere("shell", command), S.explain("shell", command)


@pytest.mark.parametrize("command", ["./gradlew test -Dexercism.local=true", "cat exercism.log", "ls exercism.local"])  # allow-pii-pattern
def test_b_the_same_local_names_chained_with_a_build_are_allowed(command):
    """[FIX] ... also inside a compound command, whole line and per command."""
    for build in BUILDS:
        for compound in (f"{build} && {command}", f"{command} ; {build}", f"{build} | tee out.log && {command}"):
            assert S.allowed_everywhere("shell", compound), S.explain("shell", compound)


@pytest.mark.parametrize("url", ["https://exercism.org/tracks/rust", "https://exercism.io/x", "https://api.github.com/orgs/exercism/repos",
                                 "https://api.github.com/users/exercism"])
def test_b_the_real_hosts_stay_denied_next_to_the_local_names(url):
    """[INV] guard against fixing (b) by weakening the host forms: the hosts themselves are still denied by shell and by webfetch."""
    for form in _forms(url):
        assert S.denied_everywhere("webfetch", form), S.explain("webfetch", form)
        assert S.denied_everywhere("shell", f"curl -s {form}"), S.explain("shell", f"curl -s {form}")
        assert S.denied_everywhere("shell", f"cargo test && curl -s {form}"), S.explain("shell", f"cargo test && curl -s {form}")


# ---------------------------------------------------------------------------------- the amended instruments (known positives)
def test_instrument_rust_parser_honours_feature_gating():
    """[INV] cfg(feature) tests - on a fn, on a mod, file-level - are not tests of the default run; the plain ones are."""
    text = '''
#[test]
fn a() {}
#[cfg(feature = "x")]
#[test]
fn gated_fn() {}
#[cfg(feature = "io")]
mod io_tests {
    #[test]
    fn gated_in_mod() {}
    #[test]
    #[ignore]
    fn gated_ignored() {}
}
#[test]
fn after_the_mod() {}
mod plain {
    #[test]
    fn in_plain_mod() {}
}
'''
    assert S.rust_tests(text) == [("a", False), ("after_the_mod", False), ("in_plain_mod", False)]
    assert S.rust_tests('#![cfg(feature = "x")]\n#[test]\nfn a() {}\n') == []


def test_instrument_cpp_parser_joins_adjacent_literals():
    """[INV] a TEST_CASE name split over two literals (on one or two lines) is one name."""
    text = 'TEST_CASE("54 character plaintext, "\n          "the last two with trailing spaces",\n          "[x]") {}\n' \
           'TEST_CASE(\n    "8 chars, "\n    "one space") {}\n'
    assert [n for n, _ in S.cpp_cases(text)] == ["54 character plaintext, the last two with trailing spaces", "8 chars, one space"]
