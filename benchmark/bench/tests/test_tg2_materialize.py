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
from bench.tests.tg2_test_root import tg2_root  # noqa: E402  P445: never inside the repo's git tree

TEST_ROOT = tg2_root()


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
                                        prepared_cargo_toml=(stub / "Cargo.toml").read_text() if lang == "rust" else None,
                                        extra_crates=mat.reference_extra_crates(POLYGLOT, lang, slug))
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
                             solutions=["src/lib.rs"], prepared_cargo_toml=(prep.tree / "Cargo.toml").read_text(),
                             extra_crates=mat.reference_extra_crates(c, "rust", "x")) == []


@pytest.mark.skipif(not HAVE_CORPUS, reason="polyglot corpus not found")
def test_every_real_reference_manifest_passes_the_structural_allowlist_check(tmp_path):
    for slug in mat.list_items(POLYGLOT)["rust"]:
        plan = mat.read_plan(POLYGLOT, "rust", slug)
        prep = mat.prepare_tree(POLYGLOT, "rust", slug, tmp_path / ("s-" + slug))
        ref = tmp_path / ("r-" + slug)
        shutil.copytree(prep.tree, ref)
        mat.apply_reference(POLYGLOT, plan, ref)
        assert tg.cargo_manifest_reasons((prep.tree / "Cargo.toml").read_text(), (ref / "Cargo.toml").read_text(),
                                         mat.reference_extra_crates(POLYGLOT, "rust", slug)) == [], slug


# ------------------------------------------------------------------------- S1: allow-listed prepared tree, leakage
UNIVERSE = Path(__file__).resolve().parents[2] / "m65/tg2_universe.json"
LEAK_CHUNK = 200
LEAK_FLOOR = 40
REFERENCE_ROOTS = (".meta", ".approaches", ".articles")


def _norm(text):
    return " ".join(text.split())


def leaked_chunks(reference_files, tree, root=None, chunk=LEAK_CHUNK, floor=LEAK_FLOOR):
    """{(prepared file, reference path): (sha256 of the prepared file, sha256 of the reference)} for every pair where a
    `min(chunk, len)`-char run of the reference (whitespace-normalized; references shorter than `floor` chars carry no
    signal and are skipped) occurs in the prepared file: a reference shorter than `chunk` must be contained whole."""
    import hashlib
    prepared = {}
    for path in sorted(Path(tree).rglob("*")):
        if path.is_file():
            prepared[path.relative_to(tree).as_posix()] = (_norm(path.read_text(errors="replace")), path.read_bytes())
    windows = {}
    leaks = {}
    for ref in reference_files:
        raw = ref.read_bytes()
        text = _norm(raw.decode(errors="replace"))
        if len(text) < floor:
            continue
        w = min(chunk, len(text))
        hashes = {hash(text[i:i + w]) for i in range(len(text) - w + 1)}
        for rel, (ptext, pbytes) in prepared.items():
            if (rel, w) not in windows:
                windows[(rel, w)] = {hash(ptext[i:i + w]) for i in range(max(0, len(ptext) - w + 1))}
            if hashes & windows[(rel, w)]:
                name = ref.relative_to(root).as_posix() if root else ref.name
                leaks[(rel, name)] = (hashlib.sha256(pbytes).hexdigest(), hashlib.sha256(raw).hexdigest())
    return leaks


# Inspected overlaps between a prepared file and a reference file: (item, prepared path, reference path, sha256 of the
# prepared file, sha256 of the reference). Each is the stub's own shipped scaffolding (API skeleton, helper class the
# reference re-includes, test data / lyrics shared with a test file), never solution code. A changed reference or prepared
# file, or an overlap not listed here, fails the test; a listed pair that no longer overlaps fails it too.
# Kinds: identical shipped helper classes / empty stubs the reference re-includes; stub skeletons that are a subset of the
# reference file (Java editor helpers, Rust API skeletons, one Cargo manifest); test / spec files sharing data with the
# reference (lyrics, verses, a jsdoc skeleton).
LEAK_EXCEPTIONS = {
    ('cpp/linked-list', 'linked_list.cpp', '.meta/example.cpp',
     'c2a1037879464329f7393e7e65d3b244c9a793ad9245678838043faf1ce485c0',
     '177a389c4d9adaeeba281bfe3fa7265b8aee4ce9576246a0b29d8063e88ba7f6'),
    ('java/alphametics', 'src/main/java/UnsolvablePuzzleException.java', '.meta/src/reference/java/UnsolvablePuzzleException.java',
     '65f42f548edde4d4e5d07fa0ae85a86cb4375c13240224fc4bbbd4a5fed057c4',
     '65f42f548edde4d4e5d07fa0ae85a86cb4375c13240224fc4bbbd4a5fed057c4'),
    ('java/bottle-song', 'src/test/java/BottleSongTest.java', '.meta/src/reference/java/BottleSong.java',
     '69f7d3a679d95582e14f23de933919ea3d8760bfe2dca57050ee26384070b60d',
     '3fc42f15abf784be7e2a58f005814dad8c583d1d634bd1cca875f8584a6ffd90'),
    ('java/circular-buffer', 'src/main/java/BufferIOException.java', '.meta/src/reference/java/BufferIOException.java',
     'b4add2b98eb2caa74c0893ddc38f657afc7f5972966fb78958d2184812ad2173',
     'b4add2b98eb2caa74c0893ddc38f657afc7f5972966fb78958d2184812ad2173'),
    ('java/connect', 'src/main/java/Winner.java', '.meta/src/reference/java/Winner.java',
     '08e73fc94c76f0dcb0f7af6b362dda5ad8f985a3377703febe43ee4e6c77456a',
     '043186d01486603b1b2b86c840c4ef5eac2e789062be9aa6cee4f4794922311b'),
    ('java/dominoes', 'src/main/java/ChainNotFoundException.java', '.meta/src/reference/java/ChainNotFoundException.java',
     '75a56632fa0e875533d6e547c530bbb3072d0d3a72b68dc09a439ade947bea70',
     'e604f65f21da5daade5593d39faf7b185c55eba20df165d26a42381343c9a545'),
    ('java/dominoes', 'src/main/java/Domino.java', '.meta/src/reference/java/Domino.java',
     '279b0fc32b4f92ceb72c75a34eb5b4d2bd54c798b6dc349a38fe4271747bd0a7',
     '8bf9501a18b5cbdeea04070b0af6c341cb6ba48d8dc9fc0ab10634422a3a523b'),
    ('java/hangman', 'src/main/java/Output.java', '.meta/src/reference/java/Output.java',
     '16c1f523a8618ffe4d748a5b80869aeac5a241f1ca15822eeb78c1adef5e3db1',
     '8fceb39c5cd8ee2280989eee095ca5821c50d1817cbbe48ea5244fcc27d26327'),
    ('java/hangman', 'src/main/java/Part.java', '.meta/src/reference/java/Part.java',
     'ae845f517974bc814c6788bcf564b2f591654965373c59d5c74bd78087d79f1a',
     'ae845f517974bc814c6788bcf564b2f591654965373c59d5c74bd78087d79f1a'),
    ('java/kindergarten-garden', 'src/main/java/Plant.java', '.meta/src/reference/java/Plant.java',
     'a2d6406f19bae36bba03dd440c8e2a9e3d91052871ac4f9ab91d69ad0d40b943',
     'a2d6406f19bae36bba03dd440c8e2a9e3d91052871ac4f9ab91d69ad0d40b943'),
    ('java/mazy-mice', 'src/test/java/MazeGeneratorTest.java', '.meta/src/reference/java/MazeGenerator.java',
     '177e2b8d61fe688fa91587e716e2e54d64e987ae1c36459a07c34897d077eeea',
     '5abc434e312fadf2e426a93095f24a96a270ea069740ba1b9d73b8ef106b373a'),
    ('java/pov', 'src/main/java/Tree.java', '.meta/src/reference/java/Tree.java',
     '371f40f997c4a819d4c5f0fc787d6567dc88771367bc2a68767a941ce8c99ebb',
     '0e99fa705a791680ae335b6cde73d8be1586913ac4ae78a34f5539ab4a7f2130'),
    ('java/rest-api', 'src/main/java/Iou.java', '.meta/src/reference/java/Iou.java',
     '8dd9a6531a234a1f022eb23d63fe103ed5272ed312e9fc4fd375f98e78cebf93',
     '8dd9a6531a234a1f022eb23d63fe103ed5272ed312e9fc4fd375f98e78cebf93'),
    ('java/rest-api', 'src/main/java/User.java', '.meta/src/reference/java/User.java',
     '5b44e305cb569f2814fe23b56c0e5bb0519508c5d418a53afda76c5eccbcaa7b',
     '7e12f32920c17147a7c3f8afcc9610b226d736c34963cd017232673c766cde16'),
    ('java/satellite', 'src/main/java/Tree.java', '.meta/src/reference/java/Tree.java',
     'ff6f866afc8169992696087cee86693b6183444eaf8a0b39c3e7b407e7ab0a92',
     'ff6f866afc8169992696087cee86693b6183444eaf8a0b39c3e7b407e7ab0a92'),
    ('java/sgf-parsing', 'src/main/java/SgfNode.java', '.meta/src/reference/java/SgfNode.java',
     '949ebdb780fa4c4e8fb92288784162cc79cbabf41cb01ef883860820d395ba17',
     '949ebdb780fa4c4e8fb92288784162cc79cbabf41cb01ef883860820d395ba17'),
    ('java/sgf-parsing', 'src/main/java/SgfParsingException.java', '.meta/src/reference/java/SgfParsingException.java',
     'b6778f9dc1b2a7152ad583a8652c5760f89024dad7fc7ac6062a18af26c6d606',
     'b6778f9dc1b2a7152ad583a8652c5760f89024dad7fc7ac6062a18af26c6d606'),
    ('java/word-search', 'src/main/java/Pair.java', '.meta/src/reference/java/Pair.java',
     'b3d84904f7562dc37dc1ca673e602d83592a5910fc152200179672e1858caf25',
     'c3f9fa1e5302bdacf533856043df7de9550ffd36237d00d0c8cc5db30b437363'),
    ('java/word-search', 'src/main/java/WordLocation.java', '.meta/src/reference/java/WordLocation.java',
     '910b41fa8899b212b00fc0d4bafef5c269f0b7b912aaac5a938b1cf771678cc2',
     '2b8ae6061c1947bc6ca2cc240e96f800e91cdbb087af4ca893580155373a1530'),
    ('javascript/food-chain', 'food-chain.spec.js', '.meta/proof.ci.js',
     '66f0265b44464c3c6bdf10c827300753c22e48353854310a8134fd46987e41e2',
     'f8f20c92a38b32f4568d3c72f4cd55a439328c0ed868922adddc88ff9a860229'),
    ('javascript/grep', 'grep.js', '.meta/proof.ci.js',
     '6ff666434b41c2516d4de8d5f80cf834d3be6147584a6bbc101bb138c0a3b5e6',
     'f24944268ea9d0de187709e742b186868da2d66c570799fa190e9dc49b7bfd84'),
    ('rust/book-store', 'Cargo.toml', '.meta/Cargo-example.toml',
     '13736df23fe8988b854e8bb0cd90ea4408550a3e5bb8cfe54b2831f1afe22408',
     '13736df23fe8988b854e8bb0cd90ea4408550a3e5bb8cfe54b2831f1afe22408'),
    ('rust/poker', 'src/lib.rs', '.meta/example.rs',
     '25ad2cded77de195e65fe757b0be1577bd26f8b1cf2f036cfcbce534809c3801',
     '9b0f1528fc4759665e4cff1204107fd7788aa2a923c2ca30838ee520e45f9a6e'),
    ('rust/react', 'src/lib.rs', '.meta/example.rs',
     '46547887d9457fcff323c996e59ad359e0444c04b070146c25e920c36dff0f69',
     '2164b2d739786c6ff8691db83372a9d74b53ed3d3100f1c7960fcfa46379706f'),
    ('rust/two-bucket', 'src/lib.rs', '.meta/example.rs',
     'ccb5816343303fed8499b59bca874d75e263b357d101ef12eea76bb672d84da9',
     'c053a0852c1c99771b38d00300f3a476dcc2e2c413b73caec4387755911e4e68'),
    ('rust/xorcism', 'src/lib.rs', '.meta/example.rs',
     '58c5c4aae92708dd1e156c57ced968062fe28d6d7c477890f4d05b065cb69c5b',
     '7247e93dc6e2f8c38704993f6b84ff75c62f3734474997a4a88d2e7884c2bd75'),
}


def reference_files(corpus, lang, slug):
    src = mat.exercise_dir(corpus, lang, slug)
    # test-generation templates / data (`*.tera`, `*.j2`, tests.toml, config.json) restate the visible tests, not a solution
    files = [p for root in REFERENCE_ROOTS if (src / root).is_dir() for p in sorted((src / root).rglob("*"))
             if p.is_file() and p.suffix not in (".tera", ".j2") and p.name not in ("tests.toml", "config.json")]
    files += [src / e for e in mat.read_plan(corpus, lang, slug).config["example"]]
    return sorted(set(files))


def valid_items():
    doc = json.loads(UNIVERSE.read_text())
    return [i for entry in doc["languages"].values() for i in entry["valid"]]


def test_prepared_tree_drops_the_reference_roots_and_fails_on_an_undeclared_directory(tmp_path):
    cfg = dict(solution=["lib/a.js"], test=["a.spec.js"], example=[".meta/proof.ci.js"])
    files = {"lib/a.js": "s", "a.spec.js": "t", ".meta/proof.ci.js": "r", ".approaches/x/snippet.txt": "SOLUTION",
             ".articles/p/a.md": "ARTICLE", "package.json": "p", ".docs/i.md": "d", "lib/.approaches/deep.md": "DEEP"}
    c = make_corpus(tmp_path / "c", "javascript", "a", cfg, files)
    tree = mat.prepare_tree(c, "javascript", "a", tmp_path / "t").tree
    assert sorted(p.relative_to(tree).as_posix() for p in tree.rglob("*") if p.is_file()) == ["a.spec.js", "lib/a.js", "package.json"]
    c2 = make_corpus(tmp_path / "c2", "javascript", "a", cfg, dict(files, **{"notes/n.md": "NOTES"}))
    with pytest.raises(mat.FreezeError, match=r"notes/n\.md"):
        mat.prepare_tree(c2, "javascript", "a", tmp_path / "t2")
    assert not (tmp_path / "t2").exists()


@pytest.mark.parametrize("key,hidden", [("solution", ".approaches/h.rs"), ("test", ".meta/h.rs"), ("editor", ".meta/h.rs")])
def test_s13_every_declared_file_must_be_present_in_the_prepared_tree(tmp_path, key, hidden):
    cfg = dict(solution=["src/lib.rs", "Cargo.toml"], test=["tests/x.rs"], example=[".meta/example.rs"])
    cfg[key] = cfg.get(key, []) + [hidden] if key == "solution" else ([hidden] if key == "test" else [hidden])
    files = {"src/lib.rs": "s", "Cargo.toml": STUB, "tests/x.rs": "t", ".meta/example.rs": "r", ".meta/h.rs": "x",
             ".approaches/h.rs": "x"}
    c = make_corpus(tmp_path / "c", "rust", "x", cfg, files)
    with pytest.raises(mat.FreezeError, match="declared"):
        mat.prepare_tree(c, "rust", "x", tmp_path / "t")
    assert not (tmp_path / "t").exists()


@pytest.mark.skipif(not (HAVE_CORPUS and UNIVERSE.is_file()), reason="polyglot corpus / frozen universe not found")
def test_every_valid_item_prepared_tree_has_nothing_from_an_excluded_root_and_no_reference_chunk(tmp_path):
    bad, seen = {}, set()
    for item in valid_items():
        lang, slug = item.split("/")
        tree = mat.prepare_tree(POLYGLOT, lang, slug, tmp_path / item.replace("/", "-")).tree
        top = {p.relative_to(tree).parts[0] for p in tree.rglob("*")}
        if top & set(REFERENCE_ROOTS + (".docs",)):
            bad[item] = ("excluded root present", sorted(top & set(REFERENCE_ROOTS + (".docs",))))
            continue
        for (rel, ref), (psha, rsha) in leaked_chunks(reference_files(POLYGLOT, lang, slug), tree,
                                                      mat.exercise_dir(POLYGLOT, lang, slug)).items():
            seen.add((item, rel, ref, psha, rsha))
        shutil.rmtree(tree)
    assert bad == {}, bad
    assert seen == LEAK_EXCEPTIONS, ("unlisted", sorted(seen - LEAK_EXCEPTIONS), "stale", sorted(LEAK_EXCEPTIONS - seen))


def test_s10_a_short_reference_contained_whole_in_a_prepared_file_is_a_hit_and_a_tiny_one_is_not(tmp_path):
    tree = tmp_path / "t"
    tree.mkdir()
    (tree / "stub.rs").write_text("fn  main() {\n  let answer = compute_the_thing(42);   }\n")
    refs = tmp_path / "r"
    refs.mkdir()
    (refs / "short.rs").write_text("let answer = compute_the_thing(42);")           # 35 chars: below the floor
    (refs / "mid.rs").write_text("fn main() { let answer = compute_the_thing(42); }")   # 49 chars, contained after normalizing
    (refs / "tiny.rs").write_text("fn main")
    hits = leaked_chunks(sorted(refs.iterdir()), tree, refs)
    assert set(hits) == {("stub.rs", "mid.rs")}


def test_s10_any_long_run_of_a_reference_is_a_hit_whatever_share_of_the_reference_it_is(tmp_path):
    tree = tmp_path / "t"
    tree.mkdir()
    run = " ".join("word%d" % i for i in range(60))                                  # well over 200 chars
    (tree / "stub.txt").write_text("header " + run + " footer")
    refs = tmp_path / "r"
    refs.mkdir()
    (refs / "partial.txt").write_text(run + " " + " ".join("other%d" % i for i in range(400)))       # run is < 15% of it
    (refs / "unrelated.txt").write_text(" ".join("zzz%d" % i for i in range(100)))
    assert set(leaked_chunks(sorted(refs.iterdir()), tree, refs)) == {("stub.txt", "partial.txt")}


def test_s10_exceptions_are_content_addressed_to_both_files(tmp_path):
    tree = tmp_path / "t"
    tree.mkdir()
    (tree / "a.txt").write_text("x" * 10 + " the shared scaffold sentence that is long enough to count" + "y" * 10)
    refs = tmp_path / "r"
    refs.mkdir()
    (refs / "r.txt").write_text("the shared scaffold sentence that is long enough to count")
    first = leaked_chunks([refs / "r.txt"], tree, refs)
    (refs / "r.txt").write_text("the shared scaffold sentence that is long enough to count, extended")
    (tree / "a.txt").write_text("the shared scaffold sentence that is long enough to count, extended")
    assert leaked_chunks([refs / "r.txt"], tree, refs) != first


# --------------------------------------------------------------------- S4: references must sit under an excluded root
@pytest.mark.parametrize("lang,cfg,files", [
    ("rust", dict(solution=["src/lib.rs", "Cargo.toml"], test=["tests/x.rs"], example=["examples/ref.rs"]),
     {"src/lib.rs": "s", "Cargo.toml": "m", "tests/x.rs": "t", "examples/ref.rs": "REF"}),
    ("javascript", dict(solution=["x.js"], test=["x.spec.js"], example=["proof.ci.js"]),
     {"x.js": "s", "x.spec.js": "t", "proof.ci.js": "REF"}),
    ("cpp", dict(solution=["a.cpp", "a.h"], test=["a_test.cpp"], example=["example.cpp", "example.h"]),
     {"a.cpp": "s", "a.h": "s", "a_test.cpp": "t", "example.cpp": "REF", "example.h": "REF"}),
    ("java", dict(solution=["src/main/java/A.java"], test=["src/test/java/ATest.java"],
                  example=[".meta/src/reference/java/../../../../src/main/java/Ref.java"]),
     {"src/main/java/A.java": "s", "src/test/java/ATest.java": "t", "src/main/java/Ref.java": "REF"}),
])
def test_an_example_outside_an_excluded_root_is_a_freeze_error(tmp_path, lang, cfg, files):
    c = make_corpus(tmp_path / "c", lang, "x" if lang != "cpp" and lang != "java" else "a", cfg, files)
    with pytest.raises(mat.FreezeError, match="excluded root|unsafe"):
        mat.read_plan(c, lang, "x" if lang not in ("cpp", "java") else "a")


def test_prepare_tree_refuses_a_configured_reference_that_would_land_in_the_tree(tmp_path):
    c = make_corpus(tmp_path / "c", "javascript", "x", dict(solution=["x.js"], test=["x.spec.js"], example=["proof.ci.js"]),
                    {"x.js": "s", "x.spec.js": "t", "proof.ci.js": "REF"})
    with pytest.raises(mat.FreezeError):
        mat.prepare_tree(c, "javascript", "x", tmp_path / "t")
    assert not (tmp_path / "t/proof.ci.js").exists()


@pytest.mark.parametrize("root", [".meta", ".approaches", ".articles"])
def test_an_example_under_any_excluded_root_is_accepted_and_absent_from_the_prepared_tree(tmp_path, root):
    c = make_corpus(tmp_path / "c", "javascript", "x", dict(solution=["x.js"], test=["x.spec.js"],
                                                           example=[root + "/proof.ci.js"]),
                    {"x.js": "s", "x.spec.js": "t", root + "/proof.ci.js": "REF"})
    assert mat.read_plan(c, "javascript", "x").mapping == [(root + "/proof.ci.js", "x.js")]
    tree = mat.prepare_tree(c, "javascript", "x", tmp_path / "t").tree
    assert sorted(p.name for p in tree.rglob("*") if p.is_file()) == ["x.js", "x.spec.js"]
    assert "REF" not in "".join(p.read_text() for p in tree.rglob("*") if p.is_file())


# ------------------------------------------------------------------ S9: audited scaffold allow-list (fail on unknown)
@pytest.mark.parametrize("lang,slug,cfg,files,stray", [
    ("javascript", "x", dict(solution=["x.js"], test=["x.spec.js"], example=[".meta/proof.ci.js"]),
     {"x.js": "s", "x.spec.js": "t", ".meta/proof.ci.js": "r", "package.json": "{}"}, "answer.js"),
    ("javascript", "x", dict(solution=["x.js"], test=["x.spec.js"], example=[".meta/proof.ci.js"]),
     {"x.js": "s", "x.spec.js": "t", ".meta/proof.ci.js": "r"}, "data/solution.txt"),
    ("java", "a", dict(solution=["src/main/java/A.java"], test=["src/test/java/ATest.java"],
                       example=[".meta/src/reference/java/A.java"]),
     {"src/main/java/A.java": "s", "src/test/java/ATest.java": "t", ".meta/src/reference/java/A.java": "r",
      "build.gradle": "g"}, "src/main/java/Answer.java"),
    ("rust", "x", dict(solution=["src/lib.rs", "Cargo.toml"], test=["tests/x.rs"], example=[".meta/example.rs"]),
     {"src/lib.rs": "s", "Cargo.toml": STUB, "tests/x.rs": "t", ".meta/example.rs": "r"}, "src/answer.rs"),
    ("cpp", "a", dict(solution=["a.cpp", "a.h"], test=["test/a_test.cpp"], example=[".meta/example.cpp", ".meta/example.h"]),
     {"a.cpp": "s", "a.h": "s", "test/a_test.cpp": "t", ".meta/example.cpp": "r", ".meta/example.h": "r"}, "test/answer.cpp"),
])
def test_s9_an_undeclared_file_outside_the_scaffold_patterns_is_a_freeze_error_naming_it(tmp_path, lang, slug, cfg, files, stray):
    c = make_corpus(tmp_path / "c", lang, slug, cfg, dict(files, **{stray: "LEAK"}))
    with pytest.raises(mat.FreezeError, match=stray.replace(".", r"\.")):
        mat.prepare_tree(c, lang, slug, tmp_path / "t")
    assert not (tmp_path / "t").exists()


def test_s9_declared_files_and_the_language_scaffold_are_accepted(tmp_path):
    c = make_corpus(tmp_path / "c", "javascript", "x", dict(solution=["x.js"], test=["x.spec.js"],
                                                           example=[".meta/proof.ci.js"]),
                    {"x.js": "s", "x.spec.js": "t", ".meta/proof.ci.js": "r", "package.json": "{}", "babel.config.js": "b",
                     ".eslintrc": "e", ".npmrc": "n", "LICENSE": "l"})
    assert mat.prepare_tree(c, "javascript", "x", tmp_path / "t").tree.is_dir()


def test_s9_per_item_extras_apply_to_that_item_only(tmp_path):
    cfg = dict(solution=["x.js"], test=["x.spec.js"], example=[".meta/proof.ci.js"])
    files = {"x.js": "s", "x.spec.js": "t", ".meta/proof.ci.js": "r", "data/iliad.txt": "text"}
    ok = make_corpus(tmp_path / "ok", "javascript", "grep", cfg, files)
    assert (mat.prepare_tree(ok, "javascript", "grep", tmp_path / "t1").tree / "data/iliad.txt").is_file()
    other = make_corpus(tmp_path / "other", "javascript", "x", cfg, files)
    with pytest.raises(mat.FreezeError, match="data/iliad.txt"):
        mat.prepare_tree(other, "javascript", "x", tmp_path / "t2")


def test_s9_the_pattern_lists_are_the_audited_minimum_every_pattern_is_used_by_the_pinned_corpus():
    if not HAVE_CORPUS:
        pytest.skip("polyglot corpus not found")
    used = set()
    for lang, slugs in mat.list_items(POLYGLOT).items():
        for slug in slugs:
            try:
                plan = mat.read_plan(POLYGLOT, lang, slug)
            except mat.FreezeError:
                continue
            src = mat.exercise_dir(POLYGLOT, lang, slug)
            declared = set(plan.solutions) | set(plan.tests) | set(plan.config.get("editor", []))
            for path in src.rglob("*"):
                rel = path.relative_to(src).as_posix()
                if path.is_file() and rel.split("/")[0] not in mat.EXCLUDED_ROOTS and rel not in declared:
                    used |= {("scaffold", lang, pat) for pat in mat.SCAFFOLD[lang] if mat.matches_pattern(rel, pat)}
                    used |= {("item", "%s/%s" % (lang, slug), pat) for pat in mat.ITEM_SCAFFOLD.get("%s/%s" % (lang, slug), ())
                             if mat.matches_pattern(rel, pat)}
    every = {("scaffold", lang, pat) for lang, pats in mat.SCAFFOLD.items() for pat in pats}
    every |= {("item", item, pat) for item, pats in mat.ITEM_SCAFFOLD.items() for pat in pats}
    # OFFLINE_CRATES.md is generated into the tree after the copy
    assert every - used == {("scaffold", "rust", "OFFLINE_CRATES.md")}, sorted(every - used)
