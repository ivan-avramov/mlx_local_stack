"""tg2 step 2: per-language reference materializer (path mapping from .meta/config.json, T4/T17/T27/T24)."""

import json
import os
from pathlib import Path
import shutil

import pytest

from bench import structured_grade as sg
from bench import tg2_grade as tg
from bench import tg2_materialize as mat

POLYGLOT = Path(os.environ.get("POLYGLOT_DIR") or Path(os.environ.get("STACK_WORKDIR", "")) / "polyglot-benchmark")
HAVE_CORPUS = (POLYGLOT / "rust/exercises/practice").is_dir()
TEST_ROOT = (Path(os.environ["STACK_WORKDIR"]) / "m65/test-tmp") if os.environ.get("STACK_WORKDIR") else (
    Path(__file__).resolve().parents[3] / ".tg2-test-tmp")


@pytest.fixture
def tmp_path():
    import uuid
    TEST_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEST_ROOT / ("m-" + uuid.uuid4().hex[:10])
    path.mkdir()
    yield path
    shutil.rmtree(path, ignore_errors=True)


def make_corpus(root, lang, slug, config, files):
    ex = Path(root) / lang / "exercises/practice" / slug
    (ex / ".meta").mkdir(parents=True)
    (ex / ".meta/config.json").write_text(json.dumps({"files": config}))
    for rel, text in files.items():
        p = ex / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return root


# ---------------------------------------------------------------------------------------------------- plan mapping
def test_rust_single_example_maps_to_src_lib_rs_and_cargo_toml_stays_protected(tmp_path):
    c = make_corpus(tmp_path / "c", "rust", "x", dict(solution=["src/lib.rs", "Cargo.toml"], test=["tests/x.rs"],
                                                      example=[".meta/example.rs"]),
                    {"src/lib.rs": "stub", "Cargo.toml": "m", "tests/x.rs": "t", ".meta/example.rs": "ref"})
    plan = mat.read_plan(c, "rust", "x")
    assert plan.mapping == [(".meta/example.rs", "src/lib.rs")] and plan.solutions == ["src/lib.rs"]
    tree = mat.prepare_tree(c, "rust", "x", tmp_path / "t").tree
    mat.apply_reference(c, plan, tree)
    assert (tree / "src/lib.rs").read_text() == "ref" and (tree / "Cargo.toml").read_text() == "m"


def test_cpp_maps_by_file_type_and_header_only_references_keep_the_stub_cpp(tmp_path):
    cfg = dict(solution=["a.cpp", "a.h"], test=["a_test.cpp"], example=[".meta/example.cpp", ".meta/example.h"])
    files = {"a.cpp": "stub", "a.h": "stubh", "a_test.cpp": "t", ".meta/example.cpp": "refc", ".meta/example.h": "refh"}
    c = make_corpus(tmp_path / "c", "cpp", "a", cfg, files)
    assert mat.read_plan(c, "cpp", "a").mapping == [(".meta/example.cpp", "a.cpp"), (".meta/example.h", "a.h")]
    cfg2 = dict(cfg, example=[".meta/example.h"])
    c2 = make_corpus(tmp_path / "c2", "cpp", "a", cfg2, files)
    plan = mat.read_plan(c2, "cpp", "a")
    tree = mat.prepare_tree(c2, "cpp", "a", tmp_path / "t2").tree
    mat.apply_reference(c2, plan, tree)
    assert (tree / "a.h").read_text() == "refh" and (tree / "a.cpp").read_text() == "stub"      # stub .cpp kept


@pytest.mark.parametrize("solution,example", [
    (["a.cpp", "b.cpp"], [".meta/example.cpp"]),                      # ambiguous destination
    (["a.h"], [".meta/example.cpp", ".meta/example.h"]),              # missing .cpp destination
])
def test_cpp_ambiguous_or_missing_destinations_are_freeze_errors(tmp_path, solution, example):
    files = {s: "x" for s in solution}
    files.update({e: "x" for e in example})
    files["a_test.cpp"] = "t"
    c = make_corpus(tmp_path / "c", "cpp", "a", dict(solution=solution, test=["a_test.cpp"], example=example), files)
    with pytest.raises(mat.FreezeError):
        mat.read_plan(c, "cpp", "a")


def test_java_maps_every_example_by_class_path_and_editor_files_are_editable(tmp_path):
    cfg = dict(solution=["src/main/java/Connect.java"], editor=["src/main/java/Winner.java"],
               test=["src/test/java/ConnectTest.java"],
               example=[".meta/src/reference/java/Connect.java", ".meta/src/reference/java/Board.java",
                        ".meta/src/reference/java/Winner.java"])
    files = {"src/main/java/Connect.java": "stub", "src/main/java/Winner.java": "w", "src/test/java/ConnectTest.java":
             "@Test void t() {}", ".meta/src/reference/java/Connect.java": "rc", ".meta/src/reference/java/Board.java": "rb",
             ".meta/src/reference/java/Winner.java": "rw"}
    c = make_corpus(tmp_path / "c", "java", "connect", cfg, files)
    plan = mat.read_plan(c, "java", "connect")
    assert sorted(plan.solutions) == ["src/main/java/Connect.java", "src/main/java/Winner.java"]
    assert ("." + "meta/src/reference/java/Board.java", "src/main/java/Board.java") in plan.mapping
    tree = mat.prepare_tree(c, "java", "connect", tmp_path / "t").tree
    mat.apply_reference(c, plan, tree)
    assert (tree / "src/main/java/Board.java").read_text() == "rb" and (tree / "src/main/java/Winner.java").read_text() == "rw"


@pytest.mark.parametrize("example", ["../evil.java", "other/Evil.java", "/abs/Evil.java"])
def test_java_example_outside_the_reference_root_is_a_freeze_error(tmp_path, example):
    cfg = dict(solution=["src/main/java/A.java"], test=["src/test/java/ATest.java"], example=[example])
    c = make_corpus(tmp_path / "c", "java", "a", cfg, {"src/main/java/A.java": "s", "src/test/java/ATest.java": "t"})
    with pytest.raises(mat.FreezeError):
        mat.read_plan(c, "java", "a")


def test_javascript_maps_the_single_example_to_the_solution(tmp_path):
    c = make_corpus(tmp_path / "c", "javascript", "x", dict(solution=["x.js"], test=["x.spec.js"],
                                                           example=[".meta/proof.ci.js"]),
                    {"x.js": "stub", "x.spec.js": "xtest('a', () => {}); xit('b', () => {}); xdescribe('c', () => {});",
                     ".meta/proof.ci.js": "ref"})
    prep = mat.prepare_tree(c, "javascript", "x", tmp_path / "t")
    spec = (prep.tree / "x.spec.js").read_text()
    assert "xtest" not in spec and "xit(" not in spec and "xdescribe" not in spec and prep.rewrites == {"x.spec.js": 3}
    assert tg.skip_form_violations(prep.tree, "javascript") == []
    plan = mat.read_plan(c, "javascript", "x")
    mat.apply_reference(c, plan, prep.tree)
    assert (prep.tree / "x.js").read_text() == "ref"


def test_java_disabled_is_removed_in_both_forms_and_recorded(tmp_path):
    cfg = dict(solution=["src/main/java/A.java"], test=["src/test/java/ATest.java"],
               example=[".meta/src/reference/java/A.java"])
    body = "@Test\n@Disabled\nvoid a() {}\n@Test\n@Disabled(\"Remove to run test\")\nvoid b() {}\n"
    c = make_corpus(tmp_path / "c", "java", "a", cfg, {"src/main/java/A.java": "s", "src/test/java/ATest.java": body,
                                                       ".meta/src/reference/java/A.java": "r"})
    prep = mat.prepare_tree(c, "java", "a", tmp_path / "t")
    assert "@Disabled" not in (prep.tree / "src/test/java/ATest.java").read_text()
    assert prep.rewrites == {"src/test/java/ATest.java": 2}


@pytest.mark.parametrize("bad", [dict(solution=["../x"]), dict(test=["/etc/passwd"]), dict(example=[])])
def test_unsafe_or_empty_config_paths_are_freeze_errors(tmp_path, bad):
    cfg = dict(solution=["x.js"], test=["x.spec.js"], example=[".meta/proof.ci.js"])
    cfg.update(bad)
    c = make_corpus(tmp_path / "c", "javascript", "x", cfg, {"x.js": "s", "x.spec.js": "t", ".meta/proof.ci.js": "r"})
    with pytest.raises(mat.FreezeError):
        mat.read_plan(c, "javascript", "x")


# ------------------------------------------------------------------------------------------------ deprecated scan
def test_deprecated_scan_flags_real_deprecation_notices_and_only_mentions_otherwise(tmp_path):
    c = make_corpus(tmp_path / "c", "javascript", "x", dict(solution=["x.js"], test=["x.spec.js"], example=["e.js"]),
                    {"x.js": "", "x.spec.js": "", "e.js": ""})
    d = Path(c) / "javascript/exercises/practice/x/.docs"
    d.mkdir()
    (d / "instructions.md").write_text("# Counter\\n\\nThis exercise has been deprecated and is an inverted exercise.\\n")
    assert mat.deprecated_scan(c, "javascript", "x").startswith("deprecated")
    (d / "instructions.md").write_text("Use the deprecated API sparingly.\\n")
    assert mat.deprecated_scan(c, "javascript", "x").startswith("mention")
    (d / "instructions.md").write_text("Nothing here.\\n")
    assert mat.deprecated_scan(c, "javascript", "x") is None


# --------------------------------------------------------------------------------------- real corpus: every item
@pytest.mark.skipif(not HAVE_CORPUS, reason="polyglot corpus not found (set POLYGLOT_DIR / STACK_WORKDIR)")
def test_every_real_item_has_a_plan_and_a_reference_tree_that_passes_the_tamper_check(tmp_path):
    items = mat.list_items(POLYGLOT)
    assert {k: len(v) for k, v in items.items()} == {"rust": 30, "java": 47, "javascript": 49, "cpp": 26}
    errors = {}
    for lang, slugs in items.items():
        for slug in slugs:
            try:
                plan = mat.read_plan(POLYGLOT, lang, slug)
            except mat.FreezeError as exc:
                errors[f"{lang}/{slug}"] = str(exc)
                continue
            stub = mat.prepare_tree(POLYGLOT, lang, slug, tmp_path / f"{lang}-{slug}-s").tree
            prepared = sg.manifest(stub)
            ref = tmp_path / f"{lang}-{slug}-r"
            shutil.copytree(stub, ref)
            mat.apply_reference(POLYGLOT, plan, ref)
            reasons = tg.tamper_reasons(ref, sg.protected_manifest(prepared, plan.solutions), prepared, lang,
                                        solutions=plan.solutions,
                                        prepared_cargo_toml=(stub / "Cargo.toml").read_text() if lang == "rust" else None)
            assert reasons == [], (lang, slug, reasons)
            assert tg.skip_form_violations(ref, lang) == [], (lang, slug)
            shutil.rmtree(stub); shutil.rmtree(ref)
    assert errors == {}, errors


@pytest.mark.skipif(not HAVE_CORPUS, reason="polyglot corpus not found")
def test_the_only_deprecated_notice_in_the_four_languages_is_none():
    flagged = {f"{l}/{s}": mat.deprecated_scan(POLYGLOT, l, s) for l, ss in mat.list_items(POLYGLOT).items() for s in ss}
    assert {k: v for k, v in flagged.items() if v and v.startswith("deprecated")} == {}


# ------------------------------------------------------------------------- P366: Cargo-example.toml dependency union
STUB = '[package]\nedition = "2021"\nname = "x"\nversion = "1.0.0"\n'


def test_union_adds_missing_dependencies_to_a_manifest_without_a_dependencies_table():
    out = mat.merge_cargo_dependencies(STUB, '[dependencies]\nregex = "0.2"\nrand = { version = "0.3", features = ["a"] }\n')
    import tomllib
    doc = tomllib.loads(out)
    assert doc["dependencies"] == {"regex": "0.2", "rand": {"version": "0.3", "features": ["a"]}}
    assert doc["package"]["name"] == "x"


def test_union_inserts_into_an_existing_dependencies_table_and_keeps_stub_entries():
    stub = '[dependencies]\nanyhow = "1.0"\n\n[package]\nname = "g"\nversion = "1.3.0"\n'
    out = mat.merge_cargo_dependencies(stub, '[dependencies]\nanyhow = "1.0"\nthiserror = "1.0"\n')
    import tomllib
    assert tomllib.loads(out)["dependencies"] == {"anyhow": "1.0", "thiserror": "1.0"}
    assert tomllib.loads(out)["package"]["name"] == "g"


def test_union_handles_dev_dependencies_and_is_a_noop_when_nothing_is_missing():
    import tomllib
    out = mat.merge_cargo_dependencies(STUB, '[dev-dependencies]\nfoo = "1"\n')
    assert tomllib.loads(out)["dev-dependencies"] == {"foo": "1"}
    assert mat.merge_cargo_dependencies(STUB, '[package]\nname = "x"\n') == STUB


def test_union_refuses_a_conflicting_version_for_the_same_crate():
    with pytest.raises(mat.FreezeError, match="conflict"):
        mat.merge_cargo_dependencies('[dependencies]\nrand = "0.8"\n', '[dependencies]\nrand = "0.3"\n')


def test_prepare_tree_keeps_the_stub_manifest_and_adds_the_identical_disclosure_file(tmp_path):
    c = make_corpus(tmp_path / "c", "rust", "x", dict(solution=["src/lib.rs", "Cargo.toml"], test=["tests/x.rs"],
                                                      example=[".meta/example.rs"]),
                    {"src/lib.rs": "stub", "Cargo.toml": STUB, "tests/x.rs": "t", ".meta/example.rs": "ref",
                     ".meta/Cargo-example.toml": '[dependencies]\nregex = "0.2"\n'})
    prep = mat.prepare_tree(c, "rust", "x", tmp_path / "t")
    assert (prep.tree / "Cargo.toml").read_text() == STUB and not (prep.tree / ".meta").exists()    # no per-item hint
    assert (prep.tree / "OFFLINE_CRATES.md").read_text() == tg.rust_disclosure_line() + "\n"


def test_the_reference_tree_uses_the_examples_dependencies_but_only_the_reference(tmp_path):
    c = make_corpus(tmp_path / "c", "rust", "x", dict(solution=["src/lib.rs", "Cargo.toml"], test=["tests/x.rs"],
                                                      example=[".meta/example.rs"]),
                    {"src/lib.rs": "stub", "Cargo.toml": STUB, "tests/x.rs": "t", ".meta/example.rs": "ref",
                     ".meta/Cargo-example.toml": '[dependencies]\nregex = "0.2"\n'})
    prep = mat.prepare_tree(c, "rust", "x", tmp_path / "t")
    ref = tmp_path / "r"
    shutil.copytree(prep.tree, ref)
    mat.apply_reference(c, mat.read_plan(c, "rust", "x"), ref)
    assert 'regex = "0.2"' in (ref / "Cargo.toml").read_text() and (ref / "src/lib.rs").read_text() == "ref"
    assert 'regex' not in (prep.tree / "Cargo.toml").read_text()
    prepared = sg.manifest(prep.tree)
    assert tg.tamper_reasons(ref, sg.protected_manifest(prepared, ["src/lib.rs"]), prepared, "rust",
                             solutions=["src/lib.rs"], prepared_cargo_toml=(prep.tree / "Cargo.toml").read_text()) == []


@pytest.mark.skipif(not HAVE_CORPUS, reason="polyglot corpus not found")
def test_every_real_reference_manifest_passes_the_structural_allowlist_check(tmp_path):
    for slug in mat.list_items(POLYGLOT)["rust"]:
        plan = mat.read_plan(POLYGLOT, "rust", slug)
        prep = mat.prepare_tree(POLYGLOT, "rust", slug, tmp_path / ("s-" + slug))
        ref = tmp_path / ("r-" + slug)
        shutil.copytree(prep.tree, ref)
        mat.apply_reference(POLYGLOT, plan, ref)
        assert tg.cargo_manifest_reasons((prep.tree / "Cargo.toml").read_text(), (ref / "Cargo.toml").read_text()) == [], slug
