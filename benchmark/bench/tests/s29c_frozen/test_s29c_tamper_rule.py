"""S29c: the tamper rule still holds for everything that is not the solution (spec 'Settled constraints'), while the full suite is
runnable. Host-only (no docker): the production `Tg2Corpus.snapshot` + `Tg2Corpus.tamper_reasons` over the production preparation
with the reference solution overlaid.
Classes: [INV] all of them hold on the baseline and must keep holding (the agent may edit its solution files and nothing else the
grader protects)."""
from __future__ import annotations

from pathlib import Path

import pytest

from bench.tests.s29c_frozen import s29c_support as S

FIRST = {lang: S.items_of(lang)[0] for lang in S.LANGS}


def _reasons(corpus, prepared, tmp_path):
    with corpus.snapshot(prepared.work, tmp_path / "run" / "grading-private", 0) as snap:
        return corpus.tamper_reasons(snap, prepared)


@pytest.fixture
def made(tmp_path):
    corpus = S.make_corpus()

    def make(lang, *, reference=True):
        item = FIRST[lang]
        prepared = S.prepare(corpus, item, tmp_path / "work")
        if reference:
            S.apply_reference(prepared.work, lang, item.split("/", 1)[1])
        return prepared
    return corpus, make


@pytest.mark.parametrize("lang", S.LANGS)
def test_a_prepared_tree_with_the_reference_solution_is_clean(lang, made, tmp_path):
    """[INV]"""
    corpus, make = made
    assert _reasons(corpus, make(lang), tmp_path) == []


@pytest.mark.parametrize("lang", S.LANGS)
def test_editing_a_test_file_is_tampering(lang, made, tmp_path):
    """[INV] enabling / disabling tests by editing the test files stays `tampered` (the grader runs the shipped tests)."""
    corpus, make = made
    prepared = make(lang)
    target = Path(prepared.work) / prepared.tests[0]
    target.write_text(target.read_text() + "\n// edited by the agent\n")
    reasons = _reasons(corpus, prepared, tmp_path)
    assert reasons and any(prepared.tests[0] in r for r in reasons), reasons


@pytest.mark.parametrize("lang", S.LANGS)
def test_editing_the_build_configuration_is_tampering(lang, made, tmp_path):
    """[INV] the build files stay protected (Cargo.toml outside [dependencies], build.gradle, package.json, CMakeLists.txt)."""
    corpus, make = made
    prepared = make(lang)
    name = {"rust": "Cargo.toml", "java": "build.gradle", "javascript": "package.json", "cpp": "CMakeLists.txt"}[lang]
    path = Path(prepared.work) / name
    path.write_text(path.read_text() + ("\n[profile.dev]\nopt-level = 3\n" if lang == "rust" else "\n# edited\n"))
    reasons = _reasons(corpus, prepared, tmp_path)
    assert reasons and any(name in r for r in reasons), reasons


@pytest.mark.parametrize("lang", S.LANGS)
def test_editing_the_solution_is_not_tampering(lang, made, tmp_path):
    """[INV] the solution files the agent may edit are unchanged in what they allow."""
    corpus, make = made
    prepared = make(lang)
    target = Path(prepared.work) / prepared.editable[0]
    target.write_text(target.read_text() + "\n")
    assert _reasons(corpus, prepared, tmp_path) == []


@pytest.mark.parametrize("lang", S.LANGS)
def test_a_new_test_file_is_tampering(lang, made, tmp_path):
    """[INV] a new test file (the other way to widen or narrow what runs) is refused."""
    corpus, make = made
    prepared = make(lang)
    new = {"rust": "tests/extra.rs", "java": "src/test/java/ExtraTest.java", "javascript": "extra.spec.js",
           "cpp": "extra_test.cpp"}[lang]
    path = Path(prepared.work) / new
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("// x\n")
    reasons = _reasons(corpus, prepared, tmp_path)
    assert reasons and any(new in r for r in reasons), reasons
