"""M76 B4b-1 acceptance 1 (implementer tests): `corpus_tg2.Tg2Corpus` — the `Corpus` contract over the real committed universe and
draw, the prompt's exact bytes per language (the spec's template, the real polyglot `.docs`), the inject tails, the grade call's
arguments, the grader mapping for every terminal outcome (recorded real `tg2_grade` trees), the normalised view after the
language's own build (H2), the final tree (a helper, a changed Cargo.toml), the identity and the join bound."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from bench import arm_runner
from bench import corpus as cp
from bench import corpus_tg1
from bench import structured_grade as sg
from bench import tg2_grade as tg
from bench.token_turn_gate import TransportAbort

BENCH = Path(__file__).resolve().parents[1].parent
FIX = Path(__file__).resolve().parent / "fixtures" / "m76_b4b1_impl" / "tg2-grade-trees"
UNIVERSE = json.loads((BENCH / "m65/tg2_universe.json").read_text())
DRAW = json.loads((BENCH / "m65/tg2_draw.json").read_text())
LANGS = ("rust", "javascript", "java", "cpp")
PILOT = {lang: DRAW["languages"][lang]["permutation"][0] for lang in LANGS}
HINTS = {
    "rust": "Helper modules may go under src/; you may add [dependencies] from the offline crates listed in OFFLINE_CRATES.md "
            "to Cargo.toml.",
    "java": "Helper classes may go only in the solution's package.",
    "javascript": "Helper .js files may go beside the solution.",
    "cpp": "Helper .h / .cpp files may go beside the solution.",
}


def _c2():
    from bench import corpus_tg2
    return corpus_tg2


def _polyglot():
    from bench import opencode_v2_core as core
    try:
        return core._polyglot_root()
    except SystemExit:
        pytest.skip("the pinned polyglot checkout is not on this box")


def _root():
    """A tree root outside TMPDIR and outside the git work tree (P361 / P445)."""
    from bench.tests.tg2_test_root import tg2_root
    return tg2_root()


@pytest.fixture
def corpus():
    c = _c2().Tg2Corpus(polyglot_root=_polyglot)
    c.load_universe()
    return c


@pytest.fixture
def scratch():
    import shutil
    import uuid
    d = _root() / f"b4b1-{uuid.uuid4().hex[:10]}"
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ----------------------------------------------------------------------------------------------- contract and universe
def test_tg2_corpus_implements_the_whole_contract(corpus):
    C = _c2()
    abstract = {n for n, v in vars(cp.Corpus).items() if getattr(v, "__isabstractmethod__", False)}
    assert abstract <= set(dir(C.Tg2Corpus))
    assert isinstance(corpus, cp.Corpus) and corpus.corpus_id == "tg2"
    assert tuple(corpus.languages) == LANGS
    assert all(corpus.needs_docker(lang) for lang in LANGS)
    for lang in LANGS:
        valid = sorted(i for i, e in UNIVERSE["items"].items() if i.startswith(lang + "/") and e["status"] == "valid")
        assert corpus.items(lang) == valid
    assert corpus.excluded == frozenset(i for i, e in UNIVERSE["items"].items() if e["status"] != "valid")
    assert corpus.source_root("rust") == Path(_polyglot()) / "rust/exercises/practice"


def test_the_default_universe_is_the_pinned_one_and_another_refuses(tmp_path):
    from bench import schedules
    C = _c2()
    c = C.Tg2Corpus(polyglot_root=_polyglot)
    _, sha = c.load_universe()
    assert sha == schedules.TG2_UNIVERSE_SHA256 == (BENCH / "m65/tg2_universe.json.sha256").read_text().split()[0]
    assert C.DEFAULT_UNIVERSE == BENCH / "m65/tg2_universe.json"
    other = tmp_path / "u.json"
    other.write_bytes((BENCH / "m65/tg2_universe.json").read_bytes() + b"\n")
    (tmp_path / "u.json.sha256").write_text(hashlib.sha256(other.read_bytes()).hexdigest() + "\n")
    with pytest.raises(TransportAbort):
        C.Tg2Corpus(other, polyglot_root=_polyglot).load_universe()


def test_identity_names_grader_image_universe_draw_and_the_timeout_rule(corpus):
    from bench import schedules
    ident = corpus.identity()
    assert ident["corpus_id"] == "tg2" and ident["grader_version"] == tg.VERSION
    assert ident["image"] == tg.pinned_image_id() and ident["universe_sha256"] == schedules.TG2_UNIVERSE_SHA256
    assert ident["draw_sha256"] == schedules.TG2_DRAW_SHA256
    for lang in LANGS:
        worst = max(e["timeout_s"] for i, e in UNIVERSE["items"].items() if i.startswith(lang + "/") and e["status"] == "valid")
        assert ident["grader_timeout_s"][lang] == 2 * worst + 300


def test_the_join_bound_covers_a_worst_case_grade_plus_a_queued_capture(corpus):
    """The core's terminal drain waits for the active grade and one queued capture: the join bound must exceed two
    worst-case grades of the slowest language (each bounded by its `grader_timeout_s`)."""
    timeouts = corpus.identity()["grader_timeout_s"]
    join = arm_runner.grade_join_timeout_s(timeouts)
    worst_grade = max(timeouts.values())
    assert join == 2 * worst_grade + arm_runner.GRADE_JOIN_OVERHEAD_S and join > 2 * worst_grade
    entry_max = max(e["timeout_s"] for e in UNIVERSE["items"].values() if e["status"] == "valid")
    assert worst_grade >= 2 * entry_max + 300        # one grade = its steps' own bounds, each <= timeout_s, plus slack


# ----------------------------------------------------------------------------------------------- the prompt (E1)
def _spec_text(lang, slug):
    docs = Path(_polyglot()) / lang / "exercises/practice" / slug / ".docs"
    text = (docs / "instructions.md").read_text(encoding="utf-8")
    if (docs / "instructions.append.md").is_file():
        text += "\n\n" + (docs / "instructions.append.md").read_text(encoding="utf-8")
    return text


@pytest.mark.parametrize("lang", LANGS)
def test_the_prompt_is_the_specs_exact_bytes(corpus, scratch, lang):
    item = PILOT[lang]
    slug = item.split("/", 1)[1]
    entry = UNIVERSE["items"][item]
    prepared = corpus.prepare(item, scratch / slug)
    want = (f"Implement the solution in {', '.join(entry['solutions'])} so that the tests in {', '.join(entry['tests'])} pass. "
            f"The specification follows.\n\n{_spec_text(lang, slug)}\n\nDo NOT modify the tests or the build files except as "
            f"stated below. Do not create new files unless the specification requires them; {HINTS[lang]}")
    assert corpus.prompt(prepared) == want
    assert corpus.prompt(prepared).endswith(HINTS[lang])
    for kind, tail in corpus_tg1.INJECT_ADDENDA.items():
        assert corpus.prompt(prepared, kind) == want + " " + tail
        assert corpus.inject_addendum_sha256(kind) == corpus_tg1.inject_addendum_sha256(kind)
    with pytest.raises(ValueError):
        corpus.prompt(prepared, "bogus")
    assert not (prepared.work / ".docs").exists()                   # the spec text comes from the source, never the tree


def test_prepare_is_the_frozen_universe_item(corpus, scratch):
    item = PILOT["rust"]
    prepared = corpus.prepare(item, scratch / "say")
    entry = UNIVERSE["items"][item]
    assert prepared.item_id == item and prepared.lang == "rust" and prepared.name == "say"
    assert sg.manifest(prepared.work) == entry["prepared"] == prepared.prepared
    assert prepared.editable == tuple(entry["solutions"]) and prepared.tests == tuple(entry["tests"])
    assert prepared.protected == sg.protected_manifest(entry["prepared"], entry["solutions"])
    assert prepared.entry["baseline_failing"] == entry["baseline_failing"] and prepared.entry["leaves"] == entry["leaves"]
    assert not corpus.changed(prepared)
    (prepared.work / "src/lib.rs").write_text("pub fn encode(n: u64) -> String { String::new() }\n")
    assert corpus.changed(prepared)


# ----------------------------------------------------------------------------------------------- L2: the live checkout
def _changed_copy(root, lang, slug):
    """A checkout holding one exercise whose `.docs` changed (its recorded `inputs_sha256` no longer holds)."""
    import shutil
    dest = root / lang / "exercises/practice" / slug
    shutil.copytree(Path(_polyglot()) / lang / "exercises/practice" / slug, dest)
    docs = dest / ".docs" / "instructions.md"
    docs.write_text(docs.read_text(encoding="utf-8") + "\nA drifted task.\n", encoding="utf-8")
    return root


def test_l2_the_live_checkout_is_the_universes(corpus):
    assert corpus.source_sha() == UNIVERSE["polyglot_sha"]


def test_l2_a_checkout_at_another_commit_refuses_before_materialisation(scratch):
    c = _c2().Tg2Corpus(polyglot_root=_polyglot, polyglot_sha=lambda root: "0" * 40)
    dest = scratch / "say"
    with pytest.raises(TransportAbort, match="polyglot"):
        c.prepare(PILOT["rust"], dest)
    assert not dest.exists()
    unknown = _c2().Tg2Corpus(polyglot_root=_polyglot, polyglot_sha=lambda root: None)
    with pytest.raises(TransportAbort, match="polyglot"):
        unknown.prepare(PILOT["rust"], dest)
    assert not dest.exists()


def test_l2_a_changed_exercise_refuses_before_materialisation(scratch):
    lang, slug = PILOT["rust"].split("/", 1)
    root = _changed_copy(scratch / "poly", lang, slug)
    c = _c2().Tg2Corpus(polyglot_root=lambda: root, polyglot_sha=lambda r: UNIVERSE["polyglot_sha"])
    dest = scratch / slug
    with pytest.raises(TransportAbort, match="inputs_sha256"):
        c.prepare(PILOT["rust"], dest)
    assert not dest.exists()


def test_l2_the_prompt_never_reads_a_changed_specification(corpus, scratch):
    lang, slug = PILOT["rust"].split("/", 1)
    prepared = corpus.prepare(PILOT["rust"], scratch / slug)
    root = _changed_copy(scratch / "poly", lang, slug)
    drifted = _c2().Tg2Corpus(polyglot_root=lambda: root, polyglot_sha=lambda r: UNIVERSE["polyglot_sha"])
    with pytest.raises(TransportAbort, match="inputs_sha256"):
        drifted.prompt(prepared)


def test_v2_the_prompt_refuses_a_checkout_at_another_commit(corpus, scratch):
    lang, slug = PILOT["rust"].split("/", 1)
    prepared = corpus.prepare(PILOT["rust"], scratch / slug)
    moved = _c2().Tg2Corpus(polyglot_root=_polyglot, polyglot_sha=lambda root: "0" * 40)     # item bytes unchanged
    with pytest.raises(TransportAbort, match="polyglot"):
        moved.prompt(prepared)


# ----------------------------------------------------------------------------------------------- the grader mapping
def _recorded(lang, variant):
    """A `tg2_grade.Tg2Grade` rebuilt from a recorded real tree: its index (outcome, artifacts) and its own reports parsed by
    `tg2_grade`'s parsers (rust: the execute step's output; java: junit-*.xml; javascript: report.json; cpp: report.xml)."""
    item = {"rust": "rust__say", "javascript": "javascript__word-search", "java": "java__zipper", "cpp": "cpp__spiral-matrix"}[lang]
    seq = FIX / lang / variant / f"{item}.grades" / "seq-0001"
    index = json.loads((seq / "index.json").read_text())
    outcome = index["outcome"]
    leaves = {}
    if outcome == "parsed":
        if lang == "rust":
            leaves = tg.parse_rust((seq / "execute.stdout").read_text() + (seq / "execute.stderr").read_text())
        elif lang == "java":
            leaves = tg.merge_leaves(*[tg.parse_junit(p.read_text()) for p in sorted(seq.glob("junit-*.xml"))])
        elif lang == "javascript":
            leaves = tg.parse_jest((seq / "report.json").read_text(), "/work/word-search")
        else:
            leaves = tg.parse_junit((seq / "report.xml").read_text())
    return tg.Tg2Grade(lang=lang, outcome=outcome, leaves=leaves, all_failed=outcome != "parsed",
                       artifacts=index["artifacts"], reason="" if outcome == "parsed" else outcome)


CASES = [(lang, v) for lang in LANGS for v in ("reference", "stub", "compile", "tampered")] + \
        [("rust", "alloc"), ("rust", "flood")]


@pytest.mark.parametrize("lang,variant", CASES)
def test_grade_outcome_of_every_recorded_tree(lang, variant):
    C = _c2()
    item = PILOT[lang]
    entry = UNIVERSE["items"][item]
    summary = json.loads((FIX / lang / variant / "result.json").read_text())
    result = _recorded(lang, variant)
    out = C.grade_outcome(result, entry, seq=1, boundary=7, final=True)
    assert isinstance(out, cp.GradeOutcome) and out.outcome == "model"
    assert out.phases == (dict(seq=1, boundary=7, final=True, outcome=result.outcome),)
    assert out.reports == dict(result.artifacts)
    assert out.resources == dict(grader_oom=result.outcome == "oom", grader_mem_kill=result.outcome == "mem_kill")
    if result.outcome == "tampered":
        assert out.tampered is True and out.failing is None and out.leaves == ()
        return
    assert out.tampered is False
    assert out.failing == summary["failing"] == result.failing(set(entry["leaves"]))
    assert out.leaves == tuple(sorted(set(entry["leaves"]) & result.passing))
    if result.outcome != "parsed":
        assert out.failing == len(set(entry["leaves"]) - result.optional) and out.leaves == ()
    assert out.passed is (variant == "reference")


@pytest.mark.parametrize("outcome", ["compile_failure", "timeout", "oom", "mem_kill", "crash", "storage_cap", "output_cap"])
def test_every_scored_non_parsed_outcome_fails_every_leaf(outcome):
    C = _c2()
    entry = UNIVERSE["items"][PILOT["rust"]]
    res = tg.Tg2Grade(lang="rust", outcome=outcome, all_failed=True, artifacts={"x": {"path": "seq-0001/x", "sha256": "0" * 64}})
    out = C.grade_outcome(res, entry, seq=2, boundary=3, final=False)
    assert out.failing == len(entry["leaves"]) and out.leaves == () and not out.tampered
    assert out.resources == dict(grader_oom=outcome == "oom", grader_mem_kill=outcome == "mem_kill")


def test_an_out_of_universe_failing_leaf_counts_and_an_extra_passing_one_does_not():
    C = _c2()
    entry = UNIVERSE["items"][PILOT["rust"]]
    leaves = {leaf: True for leaf in entry["leaves"]}
    ok = C.grade_outcome(tg.Tg2Grade(lang="rust", leaves=dict(leaves, extra_pass=True)), entry, seq=1, boundary=1, final=True)
    assert ok.failing == 0 and ok.leaves == tuple(sorted(entry["leaves"]))
    bad = C.grade_outcome(tg.Tg2Grade(lang="rust", leaves=dict(leaves, **{"suite::init": False})), entry, seq=1, boundary=1,
                          final=True)
    assert bad.failing == 1 and not bad.passed


def test_a_transport_abort_propagates(corpus, scratch, monkeypatch):
    prepared = corpus.prepare(PILOT["rust"], scratch / "say")
    private = scratch / "run" / "grading-private"
    private.mkdir(parents=True)

    def boom(*a, **k):
        raise TransportAbort("tg2 execute: runner-start marker absent")
    monkeypatch.setattr(tg, "grade_item", boom)
    with corpus.snapshot(prepared.work, private, 1) as snap:
        with pytest.raises(TransportAbort):
            corpus.grade(snap, prepared, private, None, scratch / "keep", 1, 1, True)


def test_the_grade_call_and_its_arguments(corpus, scratch, monkeypatch):
    prepared = corpus.prepare(PILOT["rust"], scratch / "say")
    entry = UNIVERSE["items"][PILOT["rust"]]
    private = scratch / "run" / "grading-private"
    private.mkdir(parents=True)
    seen = {}

    def fake(lang, work, slug, priv, **kw):
        seen.update(lang=lang, work=Path(work), slug=slug, private=Path(priv), **kw)
        return tg.Tg2Grade(lang=lang, leaves={leaf: True for leaf in entry["leaves"]})
    monkeypatch.setattr(tg, "grade_item", fake)
    guard = object()
    with corpus.snapshot(prepared.work, private, 4) as snap:
        assert snap is not None and snap.boundary == 4
        assert not snap.path.resolve().is_relative_to(private.resolve())           # G1: outside grading-private
        assert snap.path.resolve().is_relative_to((private.parent / "grading-snap").resolve())
        out = corpus.grade(snap, prepared, private, guard, scratch / "keep", 3, 4, True)
    assert out.passed
    assert seen == dict(lang="rust", work=snap.path, slug="say", private=private, prepared=entry["prepared"],
                        solutions=entry["solutions"], prepared_cargo_toml=entry["prepared_cargo_toml"], extra_crates=(),
                        keep=scratch / "keep", seq=3, boundary=4, final=True, guard=guard, timeout=entry["timeout_s"])


def test_a_tampered_or_unsnapshottable_tree_never_calls_the_grader(corpus, scratch, monkeypatch):
    prepared = corpus.prepare(PILOT["rust"], scratch / "say")
    private = scratch / "run" / "grading-private"
    private.mkdir(parents=True)
    monkeypatch.setattr(tg, "grade_item", lambda *a, **k: pytest.fail("the grader ran on a tampered tree"))
    keep = scratch / "keep"
    out = corpus.grade(None, prepared, private, None, keep, 1, 2, True)
    assert out.tampered and out.failing is None and out.phases[0]["outcome"] == "tampered"
    assert json.loads((keep / "seq-0001" / "index.json").read_text())["outcome"] == "tampered"
    (prepared.work / "tests/say.rs").write_text("// gutted\n")
    with corpus.snapshot(prepared.work, private, 3) as snap:
        assert corpus.tampered(snap, prepared)
        out = corpus.grade(snap, prepared, private, None, keep, 2, 3, False)
    assert out.tampered and not (keep / "seq-0002").exists()


# ----------------------------------------------------------------------------------------------- the normalised view (H2)
def _cargo_test_residue(work):
    """What `cargo test` leaves in a Rust exercise: `target/` (with a symlink inside) and a fresh `Cargo.lock`."""
    (work / "target/debug/deps").mkdir(parents=True)
    (work / "target/debug/deps/say-0123").write_bytes(b"\x7fELF")
    os.symlink("deps/say-0123", work / "target/debug/say")
    (work / "Cargo.lock").write_text("# This file is automatically @generated by Cargo.\nversion = 4\n")


def test_the_languages_own_build_leaves_the_view_snapshot_and_tamper_check_unchanged(corpus, scratch):
    prepared = corpus.prepare(PILOT["rust"], scratch / "say")
    work = prepared.work
    private = scratch / "run" / "grading-private"
    private.mkdir(parents=True)
    before = corpus.manifest(work)
    _cargo_test_residue(work)
    assert corpus.manifest(work) == before
    (work / "src/lib.rs").write_text("mod helper;\npub fn encode(n: u64) -> String { helper::say(n) }\n")
    (work / "src/helper.rs").write_text("pub fn say(_n: u64) -> String { String::from(\"zero\") }\n")
    view = corpus.manifest(work)
    assert "src/helper.rs" in view and not any(k.startswith("target/") or k == "Cargo.lock" for k in view)
    with corpus.snapshot(work, private, 5) as snap:
        assert snap is not None and snap.manifest == view
        assert sorted(p.relative_to(snap.path).as_posix() for p in snap.path.rglob("*") if p.is_file()) == sorted(view)
        assert not corpus.tampered(snap, prepared)
        assert tg.tamper_reasons(snap.path, prepared.protected, prepared.prepared, "rust", solutions=prepared.editable,
                                 prepared_cargo_toml=prepared.entry["prepared_cargo_toml"]) == []
    assert (work / "target/debug/say").is_symlink()                     # the model's tree itself is never altered


def test_a_symlink_outside_the_build_outputs_is_unsnapshottable(corpus, scratch):
    prepared = corpus.prepare(PILOT["rust"], scratch / "say")
    private = scratch / "run" / "grading-private"
    private.mkdir(parents=True)
    os.symlink("lib.rs", prepared.work / "src/alias.rs")
    with pytest.raises((OSError, ValueError)):
        corpus.manifest(prepared.work)
    with corpus.snapshot(prepared.work, private, 1) as snap:
        assert snap is None
    assert corpus.tampered(None, prepared)


# ----------------------------------------------------------------------------------------------- the final tree (E8)
def test_the_final_tree_holds_solutions_helpers_and_an_accepted_cargo_toml(corpus, scratch):
    prepared = corpus.prepare(PILOT["rust"], scratch / "say")
    work = prepared.work
    _cargo_test_residue(work)
    (work / "src/lib.rs").write_text("mod helper;\npub use helper::encode;\n")
    (work / "src/helper.rs").write_text("pub fn encode(_n: u64) -> String { String::new() }\n")
    toml = prepared.entry["prepared_cargo_toml"] + "\n[dependencies]\n"
    (work / "Cargo.toml").write_text(toml)
    (work / "notes.txt").write_text("a rejected new file\n")
    tree = corpus.final_tree(prepared, scratch / "ev" / "rust__say.final_tree")
    want = {rel: hashlib.sha256((work / rel).read_bytes()).hexdigest() for rel in ("src/lib.rs", "src/helper.rs", "Cargo.toml")}
    assert tree.files == want and tree.missing == ()
    for sha in want.values():
        assert (tree.root / "objects" / sha).is_file()
    doc = json.loads(tree.manifest_path.read_text())
    assert doc == dict(files=want, missing=[])
    assert tree.manifest_sha256 == hashlib.sha256(tree.manifest_path.read_bytes()).hexdigest()
    with pytest.raises(TransportAbort):
        corpus.final_tree(prepared, scratch / "ev" / "rust__say.final_tree")       # immutable


def test_the_final_tree_lists_a_missing_solution(corpus, scratch):
    prepared = corpus.prepare(PILOT["cpp"], scratch / "spiral-matrix")
    (prepared.work / prepared.editable[0]).unlink()
    tree = corpus.final_tree(prepared, scratch / "ev" / "cpp__spiral-matrix.final_tree")
    assert tree.missing == (prepared.editable[0],) and set(tree.files) == set(prepared.editable[1:])
