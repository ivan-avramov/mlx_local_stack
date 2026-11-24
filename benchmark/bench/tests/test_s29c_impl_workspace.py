"""S29 T1 / T2 / tamper (spec docs/specs/s29-tg2-testable.md v1.1), without docker, over EVERY valid item of the frozen tg2
universe: the prepared (testable) workspace keeps no form the language's standard test command would skip, the rewrite touches
only protected test-side files (never a solution, a build file or the file set), the enabled test cases name the graded
leaves, the prepared tree and the reference tree are not tampered, and the prompt's helper sentence names the full-suite
command."""
from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path

import pytest

from bench import structured_grade as sg
from bench import tg2_grade as tg
from bench.token_turn_gate import TransportAbort

BENCH = Path(__file__).resolve().parents[1].parent
UNIVERSE = json.loads((BENCH / "m65/tg2_universe.json").read_text())
LANGS = ("rust", "javascript", "java", "cpp")
VALID = sorted(i for i, e in UNIVERSE["items"].items() if e.get("status") == "valid")


def _polyglot():
    from bench import opencode_v2_core as core
    try:
        return core._polyglot_root()
    except SystemExit:
        pytest.skip("the pinned polyglot checkout is not on this box")


@pytest.fixture(scope="module")
def corpus():
    from bench import corpus_tg2
    c = corpus_tg2.Tg2Corpus(polyglot_root=_polyglot)
    c.load_universe()
    return c


@pytest.fixture
def scratch():
    from bench.tests.tg2_test_root import tg2_root
    d = tg2_root() / f"s29c-{uuid.uuid4().hex[:10]}"
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _frozen_tree(corpus, item, dest):
    from bench import tg2_materialize as mat
    lang, slug = item.split("/", 1)
    mat.prepare_tree(corpus.polyglot_root(), lang, slug, dest)
    return dest


# ----------------------------------------------------------------------------------------- static test-case extraction  # allow-shorthand
def _cpp_cases(text):
    """TEST_CASE names a build without EXERCISM_INCLUDE_BENCHMARK compiles (the grader defines no other macro now)."""
    names, skip = [], 0
    for line in text.splitlines():
        s = line.strip()
        if re.match(r"#\s*if\s+defined\s*\(\s*EXERCISM_INCLUDE_BENCHMARK", s):
            skip += 1
        elif skip and re.match(r"#\s*if", s):
            skip += 1
        elif skip and re.match(r"#\s*endif", s):
            skip -= 1
        elif not skip:
            names.append(line)
    body = "\n".join(names)
    return re.findall(r'TEST_CASE\(\s*(?://[^\n]*\s*)*"([^"]*)"', body)


def _rust_fns(text):
    return set(re.findall(r"#\[test\]\s*(?:(?:#\[[^\]]*\]|//[^\n]*)\s*)*(?:pub\s+)?fn\s+(\w+)", text))


@pytest.mark.parametrize("item", VALID)
def test_t1_the_prepared_workspace_runs_every_graded_leaf(corpus, scratch, item):
    from bench import tg2_materialize as mat
    lang, slug = item.split("/", 1)
    entry = UNIVERSE["items"][item]
    frozen_dir = _frozen_tree(corpus, item, scratch / "frozen" / slug)
    prepared = corpus.prepare(item, scratch / "work" / slug)
    work = prepared.work
    # nothing the standard command skips is left; JS `test.skip` only for the frozen optional leaves
    assert mat.full_suite_violations(work, lang, entry["solutions"]) == []
    assert tg.skip_form_violations(work, lang) == []
    # the rewrite: protected test-side files only; the file set, the solutions and the build files are the frozen ones
    assert set(prepared.prepared) == set(entry["prepared"])
    changed = {rel for rel in prepared.prepared if prepared.prepared[rel] != entry["prepared"][rel]}
    assert not changed & set(entry["solutions"])
    assert all(rel in prepared.protected for rel in changed)
    assert not {r for r in changed if Path(r).name.casefold() in ("cargo.toml", "cmakelists.txt", "build.gradle",
                                                                   "package.json")}
    assert prepared.protected == sg.protected_manifest(prepared.prepared, entry["solutions"])
    leaves = set(entry["leaves"])
    if lang == "rust":
        frozen_ignores = sum(len(re.findall(r"^[ \t]*#\[ignore\]", (frozen_dir / r).read_text(), re.M))
                             for r in entry["prepared"] if r.endswith(".rs") and r not in entry["solutions"])
        now = sum(len(re.findall(r"#\s*\[\s*(?:cfg_attr\([^\]]*)?ignore\b", (work / r).read_text()))
                  for r in prepared.prepared if r.endswith(".rs") and r not in entry["solutions"])
        assert now == 0 and (frozen_ignores == 0) == (not changed)
        for leaf in leaves:                                        # every graded leaf of a test target is a #[test] there
            binary, name = leaf.split("::", 1)
            if binary.startswith("tests/"):
                text = (work / binary).read_text()
                fn = name.split("::")[-1]
                assert fn in _rust_fns(text) or re.search(r"\b%s\b" % re.escape(fn), text), leaf    # (macro-made tests)
    elif lang == "cpp":
        assert changed == set(entry["tests"]) - {t for t in entry["tests"] if "EXERCISM_RUN_ALL_TESTS" not in
                                                 (frozen_dir / t).read_text()}
        names = {n for t in entry["tests"] for n in _cpp_cases((work / t).read_text())}
        assert all(leaf.startswith(f"{slug}.global#") for leaf in leaves)
        graded = [leaf.split("#", 1)[1] for leaf in leaves]       # Catch2 SECTION leaves: `case -> section` / `case/section`
        of = lambda g: [n for n in names if g == n or g.startswith(n + " -> ") or g.startswith(n + "/")]  # noqa: E731
        assert all(of(g) for g in graded), [g for g in graded if not of(g)]          # every graded leaf is an enabled case
        assert all(any(n in of(g) for g in graded) for n in names), sorted(n for n in names if not any(n in of(g) for g in graded))
        assert all("EXERCISM_RUN_ALL_TESTS" not in (work / t).read_text() for t in entry["tests"])
    elif lang == "javascript":
        assert not changed                                         # `prepare_tree` already enabled every test (freeze)
        text = "".join((work / t).read_text() for t in entry["tests"])
        assert len(re.findall(r"\b(?:test|it)(?:\.skip)?\s*\(", text)) == len(leaves) + len(entry["optional_excluded"])
        assert len(re.findall(r"\b(?:test|it)\.skip\s*\(", text)) == len(entry["optional_excluded"])
        assert set(entry["optional_excluded"]) == set(tg.OPTIONAL_LEAVES.get((lang, slug), ()))
    else:
        assert not changed
        tests = [r for r in prepared.prepared if r.startswith("src/test/") and r.endswith(".java")]
        count = sum(len(re.findall(r"@(?:Test|ParameterizedTest)\b", (work / t).read_text())) for t in tests)
        assert count == len(leaves)
    # the tamper rule: the fresh workspace and the reference tree are clean
    assert tg.tamper_reasons(work, prepared.protected, prepared.prepared, lang, solutions=list(prepared.editable),
                             prepared_cargo_toml=entry.get("prepared_cargo_toml")) == []
    mat.apply_reference(corpus.polyglot_root(), mat.read_plan(corpus.polyglot_root(), lang, slug), work)
    ref_reasons = tg.tamper_reasons(work, prepared.protected, prepared.prepared, lang, solutions=list(prepared.editable),
                                    prepared_cargo_toml=entry.get("prepared_cargo_toml"),
                                    extra_crates=tuple(entry.get("reference_extra_crates") or ()))
    assert ref_reasons == []


def test_t1_the_frozen_check_still_runs_first(corpus, scratch, monkeypatch):
    """The universe's recorded `prepared` is checked on the frozen tree, before the rewrite (a changed frozen tree refuses)."""
    from bench import tg2_materialize as mat
    real = mat.prepare_tree

    def drift(root, lang, slug, dest):
        out = real(root, lang, slug, dest)
        (Path(dest) / "OFFLINE_CRATES.md").write_text("changed\n")
        return out
    monkeypatch.setattr(mat, "prepare_tree", drift)
    with pytest.raises(TransportAbort, match="differs from frozen universe"):
        corpus.prepare("rust/acronym", scratch / "acronym")


@pytest.mark.parametrize("edit, why", [
    (lambda t: t.replace("#[ignore]\n", "#[ignore] // kept\n", 1), "still skips tests"),
    (lambda t: t.replace("#[test]\n", "#[test] #[ignore]\n", 1), "still skips tests"),
])
def test_t1_a_rust_skip_form_the_rewrite_cannot_remove_refuses(corpus, scratch, monkeypatch, edit, why):
    from bench import tg2_materialize as mat
    real = mat.enable_full_suite

    def plant(tree, lang, solutions):
        path = Path(tree) / "tests/acronym.rs"
        path.write_text(edit(path.read_text()))
        return real(tree, lang, solutions)
    monkeypatch.setattr(mat, "enable_full_suite", plant)
    with pytest.raises(TransportAbort, match=why):
        corpus.prepare("rust/acronym", scratch / "acronym")


def test_t1_a_rewrite_outside_the_test_side_refuses(corpus, scratch, monkeypatch):
    from bench import tg2_materialize as mat

    def touch_solution(tree, lang, solutions):
        (Path(tree) / "src/lib.rs").write_text("// changed\n")
        return {"src/lib.rs": 1}
    monkeypatch.setattr(mat, "enable_full_suite", touch_solution)
    with pytest.raises(TransportAbort, match="testable rewrite touched"):
        corpus.prepare("rust/acronym", scratch / "acronym")


def test_t1_an_unreported_rewrite_refuses(corpus, scratch, monkeypatch):
    from bench import tg2_materialize as mat
    real = mat.enable_full_suite

    def silent(tree, lang, solutions):
        real(tree, lang, solutions)
        return {}
    monkeypatch.setattr(mat, "enable_full_suite", silent)
    with pytest.raises(TransportAbort, match="testable rewrite touched"):
        corpus.prepare("rust/acronym", scratch / "acronym")


@pytest.mark.parametrize("text, err", [
    ("#if defined(EXERCISM_RUN_ALL_TESTS)\nTEST_CASE(\"a\") {}\n#else\n#endif\n", "#else"),
    ("#if defined(EXERCISM_RUN_ALL_TESTS)\nTEST_CASE(\"a\") {}\n", "without its #endif"),
])
def test_t1_a_cpp_guard_of_another_shape_is_never_guessed(tmp_path, text, err):
    from bench import tg2_materialize as mat
    (tmp_path / "x_test.cpp").write_text(text)
    with pytest.raises(mat.FreezeError, match=err):
        mat.enable_full_suite(tmp_path, "cpp", ["x.cpp", "x.h"])


def test_t1_the_cpp_rewrite_keeps_other_conditionals(tmp_path):
    from bench import tg2_materialize as mat
    text = ("#ifdef EXERCISM_TEST_SUITE\n#include <catch2/catch.hpp>\n#else\n#include \"test/catch.hpp\"\n#endif\n"
            "TEST_CASE(\"a\") {}\n#if defined(EXERCISM_RUN_ALL_TESTS)\nTEST_CASE(\"b\") {}\n#if defined(X)\nTEST_CASE(\"c\") {}\n"
            "#endif\n#endif  // EXERCISM_RUN_ALL_TESTS\n")
    (tmp_path / "x_test.cpp").write_text(text)
    assert mat.enable_full_suite(tmp_path, "cpp", ["x.cpp"]) == {"x_test.cpp": 1}
    assert (tmp_path / "x_test.cpp").read_text() == text.replace("#if defined(EXERCISM_RUN_ALL_TESTS)\n", "").replace(
        "#endif  // EXERCISM_RUN_ALL_TESTS\n", "")
    assert mat.full_suite_violations(tmp_path, "cpp", ["x.cpp"]) == []


# ----------------------------------------------------------------------------------------------------- T2: the prompt
@pytest.mark.parametrize("lang", LANGS)
def test_t2_the_helper_sentence_names_the_full_suite_command(corpus, scratch, lang):
    from bench import corpus_tg2
    item = next(i for i in VALID if i.startswith(lang + "/"))
    prompt = corpus.prompt(corpus.prepare(item, scratch / item.split("/", 1)[1]))
    cmd = corpus_tg2.FULL_SUITE_COMMANDS[lang]
    assert prompt.endswith(corpus_tg2.HINTS[lang]) and f"`{cmd}` " in corpus_tg2.HINTS[lang]
    assert "full test suite your solution is graded on" in corpus_tg2.HINTS[lang]
    assert sum(prompt.count(h) for h in corpus_tg2.HINTS.values()) == 1
