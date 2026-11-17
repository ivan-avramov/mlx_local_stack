"""M76 B4b-1 (spec v5 §1 + acceptance 1): the `Tg2Corpus` contract, the prompt bytes, the normalised view (H2), the snapshot (G1),
the final tree (E8), the pins and the probe entry. Real draw / universe / polyglot checkout; the recorded real trees pin the
fixtures. Class of each test is in the comment above it: (a) reproduces a failure the spec fixes, (b) preserves an invariant,
(c) new behaviour. Name guesses: `test_m76_b4b1_fe_support.GUESSES`."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bench.tests import test_m76_b4b1_fe_support as S


# ------------------------------------------------------------------------------------------------ fixtures and pins
# (b) the copied recorded trees are exactly what was recorded (sha256-pinned, nothing added or lost)
def test_recorded_trees_are_sha256_pinned():
    assert S.sha256_file(S.TREES_MANIFEST) == S.TREES_MANIFEST_SHA256
    files = S.trees_manifest()["files"]
    on_disk = {p.relative_to(S.TREES).as_posix() for p in S.TREES.rglob("*") if p.is_file()}
    assert on_disk == set(files)
    bad = [rel for rel, sha in files.items() if S.sha256_file(S.TREES / rel) != sha]
    assert not bad, bad[:5]


# (b) the committed draw / universe and their sidecars are the pinned artifacts (spec §1 "Pins in code")
def test_committed_draw_and_universe_are_the_pinned_files():
    assert S.sha256_file(S.DRAW_PATH) == S.TG2_DRAW_SHA256
    assert S.sha256_file(S.UNIVERSE_PATH) == S.TG2_UNIVERSE_SHA256
    assert (S.DRAW_PATH.with_name("tg2_draw.json.sha256").read_text().split() or [""])[0] == S.TG2_DRAW_SHA256
    assert (S.UNIVERSE_PATH.with_name("tg2_universe.json.sha256").read_text().split() or [""])[0] == S.TG2_UNIVERSE_SHA256


# (c) the pins are in code, equal to the committed artifacts
def test_pins_in_schedules():
    from bench import schedules
    assert S.attr(schedules, "TG2_DRAW_SHA256", "schedule") == S.TG2_DRAW_SHA256
    assert S.attr(schedules, "TG2_UNIVERSE_SHA256", "schedule") == S.TG2_UNIVERSE_SHA256


# (b) the existing tier machinery still refuses a draw that is not the frozen one (the baseline invariant the pins extend)
def test_baseline_draw_check_refuses_a_redrawn_artifact():
    from bench import schedules
    doc = S.draw_doc()
    doc["languages"]["rust"]["permutation"] = list(reversed(doc["languages"]["rust"]["permutation"]))
    with pytest.raises(schedules.TransportAbort):
        schedules.tg2_tier(doc, S.TG2_DRAW_SHA256, "decider")


# ------------------------------------------------------------------------------------------------ the contract
# (c) every method of `bench.corpus.Corpus` is implemented; the class is instantiable and carries the tg2 identity of the corpus
def test_corpus_implements_the_contract():
    from bench.corpus import Corpus
    corpus = S.make_corpus(load=False)
    assert isinstance(corpus, Corpus)
    assert corpus.corpus_id == "tg2"
    assert set(corpus.languages) == set(S.LANGS)
    assert all(corpus.needs_docker(lang) is True for lang in S.LANGS)


# (c) load_universe returns (doc, sha256) and the sha is the pinned one; the failure path: a changed universe does not load
def test_load_universe_returns_the_pinned_sha_and_refuses_a_changed_file(tmp_path):
    corpus = S.make_corpus(load=False)
    doc, sha = corpus.load_universe()
    assert sha == S.TG2_UNIVERSE_SHA256 and doc["items"] == S.universe_doc()["items"]
    bad = S.universe_doc()
    bad["items"]["rust/say"]["leaves"] = bad["items"]["rust/say"]["leaves"][:-1]
    path = tmp_path / "universe.json"
    path.write_text(json.dumps(bad, sort_keys=True, indent=1) + "\n")
    other = S.make_corpus(load=False)
    with pytest.raises(Exception):                                                  # not the pinned universe (spec: the pins in code)
        other.load_universe(path)


# (c) items(lang): sorted, language-prefixed, containing the draw's frozen permutation; excluded is a collection of item ids
@pytest.mark.parametrize("lang", S.LANGS)
def test_items_cover_the_frozen_draw(lang):
    corpus = S.make_corpus()
    items = corpus.items(lang)
    assert items == sorted(items) and all(i.startswith(lang + "/") for i in items)
    perm = S.draw_doc()["languages"][lang]["permutation"]
    assert set(perm) <= set(items)
    assert not (set(perm) & set(corpus.excluded))


# (c) source_root(lang) is `<polyglot checkout>/<lang>/exercises/practice` (the corpus-root seam)
@pytest.mark.parametrize("lang", S.LANGS)
def test_source_root(lang):
    corpus = S.make_corpus()
    assert Path(corpus.source_root(lang)) == S.polyglot() / lang / "exercises/practice"


# (c) prepare: the pilot item of every language prepares to exactly the universe's frozen tree (editable = the declared solutions,
# tests = the declared tests); an item the universe does not hold is refused
@pytest.mark.parametrize("lang", S.LANGS)
def test_prepare_pilot_item_matches_the_frozen_universe(lang, tmp_path):
    corpus = S.make_corpus()
    item = S.PILOT[lang]
    entry = S.entry_of(item)
    prepared = S.prepare_item(corpus, item, tmp_path / "work")
    assert prepared.item_id == item and prepared.lang == lang and prepared.name == item.split("/", 1)[1]
    assert set(prepared.editable) == set(entry["solutions"])
    assert set(prepared.tests) == set(entry["tests"])
    assert corpus.manifest(prepared.work) == entry["prepared"]
    assert prepared.prepared == entry["prepared"]
    assert not corpus.changed(prepared)                                       # an untouched stub is "unchanged" (it fails)


def test_prepare_refuses_an_item_outside_the_universe(tmp_path):
    corpus = S.make_corpus()
    with pytest.raises(Exception):
        corpus.prepare("rust/not-an-exercise", tmp_path / "work")


# (c) identity: grader VERSION, image digest, universe + draw sha256, grader_timeout_s[lang] = 2 × max_entries(timeout_s) + 300
def test_identity_carries_grader_image_universe_draw_and_timeouts():
    from bench import tg2_grade
    ident = S.make_corpus().identity()
    assert ident["universe_sha256"] == S.TG2_UNIVERSE_SHA256
    flat = json.dumps(ident, sort_keys=True)
    assert tg2_grade.VERSION in flat and S.TG2_DRAW_SHA256 in flat
    assert tg2_grade.pinned_image_id() in flat or tg2_grade.IMAGE_TAG in flat
    items = S.universe_doc()["items"]
    for lang in S.LANGS:
        worst = max(e["timeout_s"] for k, e in items.items() if k.startswith(lang + "/") and e.get("status") == "valid")
        assert ident["grader_timeout_s"][lang] == 2 * worst + 300, lang


# ------------------------------------------------------------------------------------------------ the prompt (E1)
# (c) exact bytes per language: the entry's solutions / tests joined by ", ", the instructions (+ append), the one helper clause last
@pytest.mark.parametrize("lang", S.LANGS)
def test_prompt_exact_bytes(lang, tmp_path):
    corpus = S.make_corpus()
    item = S.PILOT[lang]
    prepared = S.prepare_item(corpus, item, tmp_path / "w")
    got = corpus.prompt(prepared)
    want = S.expected_prompts(S.entry_of(item), lang, item.split("/", 1)[1])
    assert got in want, got[-300:]
    assert got.endswith(S.HELPER_TEXT[lang]) and not got.endswith("\n")
    assert sum(got.count(h) for h in S.HELPER_TEXT.values()) == 1                  # exactly one H


# (c) every item of every language's frozen draw prefix builds its prompt from the SOURCE docs (never the materialised tree,
# which excludes `.docs`): the instructions text is present
@pytest.mark.parametrize("lang", S.LANGS)
def test_prompt_uses_the_source_docs_for_every_decider_item(lang, tmp_path):
    corpus = S.make_corpus()
    for n, item in enumerate(S.draw_doc()["languages"][lang]["decider"]):
        prepared = S.prepare_item(corpus, item, tmp_path / ("w%d" % n))
        assert corpus.prompt(prepared) in S.expected_prompts(S.entry_of(item), lang, item.split("/", 1)[1]), item


# (c) an inject kind appends " " + tg1's addendum, byte for byte, after H
@pytest.mark.parametrize("kind", S.KINDS)
@pytest.mark.parametrize("lang", S.LANGS)
def test_prompt_inject_tails(lang, kind, tmp_path):
    corpus = S.make_corpus()
    item = S.PILOT[lang]
    prepared = S.prepare_item(corpus, item, tmp_path / "w")
    got = corpus.prompt(prepared, inject=kind)
    assert got in S.expected_prompts(S.entry_of(item), lang, item.split("/", 1)[1], inject=kind)
    assert got.startswith(corpus.prompt(prepared)) and got.endswith(" " + __import__("bench.corpus_tg1", fromlist=["x"]).INJECT_ADDENDA[kind])


# (b) the addendum digest is tg1's (the same texts); an unknown kind is refused
def test_inject_addendum_sha256_equals_tg1_and_unknown_kind_refuses(tmp_path):
    from bench import corpus_tg1
    corpus = S.make_corpus()
    for kind in S.KINDS:
        assert corpus.inject_addendum_sha256(kind) == corpus_tg1.inject_addendum_sha256(kind)
    prepared = S.prepare_item(corpus, S.PILOT["rust"], tmp_path / "w")
    with pytest.raises(Exception):
        corpus.prompt(prepared, inject="bogus")


# ------------------------------------------------------------------------------------------------ the normalised view (H2)
def _agent_tree(corpus, lang, tmp_path, name="work"):
    """A prepared pilot tree after an agent ran the language's own build / test commands: every STRIP_TOP_LEVEL directory with a
    nested file and a SYMLINK in it, plus a changed solution."""
    item = S.PILOT[lang]
    prepared = S.prepare_item(corpus, item, tmp_path / name)
    work = prepared.work
    for top in ("build", "target", "node_modules", ".gradle"):
        (work / top / "out").mkdir(parents=True)
        (work / top / "out" / "artifact.bin").write_bytes(b"\x00\x01" + top.encode())
        os.symlink("artifact.bin", work / top / "out" / "link")
    sol = work / prepared.editable[0]
    sol.write_text(sol.read_text() + "\n// agent edit\n")
    return prepared


# (a) the baseline's manifest raises on a symlink anywhere (a build output with one), which made such an item tampered
def test_baseline_manifest_cannot_read_a_tree_with_a_symlinked_build_output(tmp_path):
    from bench import structured_grade as sg, tg2_materialize as mat
    work = mat.prepare_tree(S.polyglot(), "rust", "say", tmp_path / "work").tree
    (work / "target" / "debug").mkdir(parents=True)
    (work / "target" / "debug" / "a.o").write_bytes(b"\x00")
    os.symlink("a.o", work / "target" / "debug" / "link")
    with pytest.raises(ValueError):
        sg.manifest(work)


# (a) the tg2 view omits the build outputs: the manifest reads, lists no STRIP_TOP_LEVEL path and does not call the item tampered
@pytest.mark.parametrize("lang", S.LANGS)
def test_normalised_view_omits_build_outputs(lang, tmp_path):
    corpus = S.make_corpus()
    prepared = _agent_tree(corpus, lang, tmp_path)
    m = corpus.manifest(prepared.work)
    assert not [p for p in m if p.split("/")[0] in ("build", "target", "node_modules", ".gradle")]
    assert m[prepared.editable[0]] != prepared.baseline[prepared.editable[0]]
    private = tmp_path / "run" / "grading-private"
    private.mkdir(parents=True)
    with corpus.snapshot(prepared.work, private, "final") as snap:
        assert snap is not None
        assert not corpus.tampered(snap, prepared)
        assert snap.manifest == m
    assert corpus.changed(prepared)


# (a) G1: the snapshot is captured OUTSIDE `grading-private` (tg2_grade refuses a work tree inside its private dir), in the run
# dir's sibling `grading-snap/`
def test_snapshot_lives_beside_grading_private_not_inside(tmp_path):
    corpus = S.make_corpus()
    prepared = S.prepare_item(corpus, S.PILOT["rust"], tmp_path / "w")
    run = tmp_path / "run"
    private = run / "grading-private"
    private.mkdir(parents=True)
    with corpus.snapshot(prepared.work, private, "boundary-1") as snap:
        assert snap is not None
        path = Path(snap.path).resolve()
        assert (run / "grading-snap").resolve() in path.parents
        assert private.resolve() not in path.parents and path != private.resolve()
        assert snap.boundary == "boundary-1"


# (b) a protected file edit is a tamper; an unsnapshottable tree (None) is a tamper; they agree with `tg2_grade`'s own verdict
@pytest.mark.parametrize("lang", S.LANGS)
def test_tamper_agrees_with_tg2_grade(lang, tmp_path):
    from bench import tg2_grade
    corpus = S.make_corpus()
    prepared = S.prepare_item(corpus, S.PILOT[lang], tmp_path / "w")
    assert corpus.tampered(None, prepared) is True
    test_file = prepared.work / prepared.tests[0]
    test_file.write_text(test_file.read_text() + "\n// cheat\n")
    private = tmp_path / "run" / "grading-private"
    private.mkdir(parents=True)
    with corpus.snapshot(prepared.work, private, "final") as snap:
        verdict = corpus.tampered(snap, prepared)
        reasons = tg2_grade.tamper_reasons(
            snap.path, tg2_grade.protected_manifest(prepared.prepared, prepared.entry["solutions"]), prepared.prepared, lang,
            solutions=prepared.entry["solutions"], prepared_cargo_toml=prepared.entry.get("prepared_cargo_toml"))
    assert verdict is True and reasons


# (a) a symlink outside the build outputs is NOT hidden by the view: the item is a tamper (or unsnapshottable)
def test_symlink_in_the_sources_is_still_a_tamper(tmp_path):
    corpus = S.make_corpus()
    prepared = S.prepare_item(corpus, S.PILOT["rust"], tmp_path / "w")
    os.symlink("/etc/hosts", prepared.work / "src" / "evil.rs")
    private = tmp_path / "run" / "grading-private"
    private.mkdir(parents=True)
    try:
        view = corpus.manifest(prepared.work)
    except (OSError, ValueError):
        view = None
    with corpus.snapshot(prepared.work, private, "final") as snap:
        assert snap is None or corpus.tampered(snap, prepared)
    assert view is None or "src/evil.rs" not in view or snap is None


# (b) `changed`: only a DECLARED editable path counts (a helper alone leaves the stub "untouched")
def test_changed_counts_only_declared_editable_paths(tmp_path):
    corpus = S.make_corpus()
    prepared = S.prepare_item(corpus, S.PILOT["rust"], tmp_path / "w")
    (prepared.work / "src" / "helper.rs").write_text("pub fn h() {}\n")
    assert not corpus.changed(prepared)
    (prepared.work / "src" / "lib.rs").write_text("pub fn say(_: u64) -> String { String::new() }\n")
    assert corpus.changed(prepared)


# ------------------------------------------------------------------------------------------------ the final tree (E8)
def _helper_for(lang, prepared):
    sol = prepared.editable[0]
    d = Path(sol).parent.as_posix()
    d = "" if d == "." else d
    if lang == "rust":
        return "src/helper.rs", "pub fn helper() {}\n"
    if lang == "javascript":
        return (d + "/" if d else "") + "helper.js", "module.exports = {};\n"
    if lang == "cpp":
        return (d + "/" if d else "") + "helper.h", "#pragma once\n"
    pkg = ".".join(p for p in d.removeprefix("src/main/java").split("/") if p)
    return d + "/Helper.java", (("package %s;\n" % pkg) if pkg else "") + "class Helper {}\n"


# (c) the final tree of an agent run: the declared solutions + every new / changed file the tamper check accepts (a helper, a
# changed Cargo.toml); never the build outputs, the tests or the unchanged scaffold; content-addressed objects + manifest.json
@pytest.mark.parametrize("lang", S.LANGS)
def test_final_tree_has_solutions_and_accepted_helpers(lang, tmp_path):
    corpus = S.make_corpus()
    prepared = _agent_tree(corpus, lang, tmp_path)
    rel, text = _helper_for(lang, prepared)
    (prepared.work / rel).parent.mkdir(parents=True, exist_ok=True)
    (prepared.work / rel).write_text(text)
    final = corpus.final_tree(prepared, tmp_path / "out" / "x.final_tree")
    assert set(final.files) == set(prepared.editable) | {rel}, final.files
    assert not final.missing
    for path, sha in final.files.items():
        assert S.sha256_bytes((prepared.work / path).read_bytes()) == sha
        assert (final.root / "objects" / sha).read_bytes() == (prepared.work / path).read_bytes()
    doc = json.loads(final.manifest_path.read_text())
    assert doc == dict(files=final.files, missing=[]) and S.sha256_file(final.manifest_path) == final.manifest_sha256


# (c) a changed Cargo.toml (an allowlisted crate) is part of the final tree; the unchanged one is not
def test_final_tree_has_a_changed_cargo_toml(tmp_path):
    from bench import tg2_grade
    from bench.token_turn_gate import TransportAbort
    try:
        crate = tg2_grade.RUST_ALLOWLIST[0]
        version = tg2_grade.vendored_versions()[crate][0]
    except (TransportAbort, KeyError, IndexError) as exc:
        pytest.skip(f"no vendored crate version available: {exc}")
    corpus = S.make_corpus()
    prepared = S.prepare_item(corpus, S.PILOT["rust"], tmp_path / "w")
    (prepared.work / "src" / "lib.rs").write_text("pub fn say(_: u64) -> String { String::new() }\n")
    before = corpus.final_tree(prepared, tmp_path / "o1.final_tree")
    assert "Cargo.toml" not in before.files
    text = (prepared.work / "Cargo.toml").read_text()
    (prepared.work / "Cargo.toml").write_text(text.rstrip("\n") + '\n\n[dependencies]\n%s = "%s"\n' % (crate, version))
    private = tmp_path / "run" / "grading-private"
    private.mkdir(parents=True)
    with corpus.snapshot(prepared.work, private, "final") as snap:
        assert not corpus.tampered(snap, prepared)
    after = corpus.final_tree(prepared, tmp_path / "o2.final_tree")
    assert set(after.files) == {"src/lib.rs", "Cargo.toml"}


# (c) a declared solution that is gone is listed under `missing`; evidence is immutable (a second tree at the same place aborts)
def test_final_tree_missing_and_immutable(tmp_path):
    from bench.token_turn_gate import TransportAbort
    corpus = S.make_corpus()
    prepared = S.prepare_item(corpus, S.PILOT["rust"], tmp_path / "w")
    (prepared.work / "src" / "lib.rs").unlink()
    final = corpus.final_tree(prepared, tmp_path / "o.final_tree")
    assert list(final.missing) == ["src/lib.rs"] and "src/lib.rs" not in final.files
    with pytest.raises(TransportAbort):
        corpus.final_tree(prepared, tmp_path / "o.final_tree")


# ------------------------------------------------------------------------------------------------ the probe entry
# (c) `--scaffold` accepts only the tg2 scaffold; `--lang` only the four tg2 languages (the probe refuses tg1's python / go)
def test_probe_parser_scaffold_and_languages():
    probe = S.probe_module()
    parser = S.attr(probe, "_parser", "chain-entry")()
    ns = parser.parse_args(["--model", "m", "--items", "a", "--seed-base", "1001", "--lang", "rust"])
    assert ns.scaffold == S.SCAFFOLD
    for bad in (["--scaffold", "opencode-v2-web-tg1"], ["--lang", "python"], ["--lang", "go"]):
        with pytest.raises(SystemExit):
            parser.parse_args(["--model", "m", "--items", "a", "--seed-base", "1001", *bad])
    ns = parser.parse_args(["--model", "m", "--items", "a", "--seed-base", "1001", "--lang", "cpp", "--tg2-inject", "alloc"])
    assert getattr(ns, "tg2_inject", None) == "alloc" or ns.tg1_inject == "alloc"      # AMENDED: the shared core reads one inject dest
    with pytest.raises(SystemExit):
        parser.parse_args(["--model", "m", "--items", "a", "--seed-base", "1001", "--tg2-inject", "bogus"])


def _probe_identity(tmp_path, *extra):
    env = dict(os.environ, PYTHONPATH=str(S.BENCH), STACK_WORKDIR=os.environ.get("STACK_WORKDIR", str(tmp_path)))
    return subprocess.run([sys.executable, str(S.BENCH / "run_tg2_probe.py"), "--print-identity", *extra], cwd=S.REPO,
                          capture_output=True, text=True, timeout=300, env=env)


# (a) a tg2 probe WITHOUT `--universe` uses the tg2 universe (tg1's `benchmark/m62/universe.json` was the shared default)
def test_probe_without_universe_defaults_to_the_tg2_universe(tmp_path):
    S.polyglot()
    proc = _probe_identity(tmp_path)
    assert proc.returncode == 0, (proc.stderr or proc.stdout)[-800:]
    doc = json.loads(proc.stdout)
    # AMENDED (delivery 2): like tg1's, `--print-identity` carries the universe only through `scaffold_policy_sha256` (the generation
    # policy embeds the universe sha), so the default is observed by equality with an explicit `--universe <tg2 universe>` and
    # inequality with tg1's universe
    assert doc["config_id"] == "tg2" and doc["scaffold"] == S.SCAFFOLD
    explicit = json.loads(_probe_identity(tmp_path, "--universe", str(S.UNIVERSE_PATH)).stdout)
    assert doc["scaffold_policy_sha256"] == explicit["scaffold_policy_sha256"]
    other = _probe_identity(tmp_path, "--universe", str(S.BENCH / "m62" / "universe.json"))
    assert other.returncode != 0 or json.loads(other.stdout)["scaffold_policy_sha256"] != doc["scaffold_policy_sha256"]


# (c) with the inject flag the identity carries the addendum's digest (tg1's text); a bogus kind is refused
def test_probe_identity_with_an_inject_kind(tmp_path):
    from bench import corpus_tg1
    S.polyglot()
    proc = _probe_identity(tmp_path, "--tg2-inject", "loop")
    assert proc.returncode == 0, (proc.stderr or proc.stdout)[-800:]
    # AMENDED (delivery 2): the addendum digest enters `scaffold_policy_sha256` (policy), not the printed summary: the inject kinds
    # give three distinct policies, all different from the plain one
    plain = json.loads(_probe_identity(tmp_path).stdout)["scaffold_policy_sha256"]
    seen = {plain}
    for kind in S.KINDS:
        p = _probe_identity(tmp_path, "--tg2-inject", kind)
        assert p.returncode == 0, (p.stderr or p.stdout)[-400:]
        seen.add(json.loads(p.stdout)["scaffold_policy_sha256"])
    assert len(seen) == 4
    assert _probe_identity(tmp_path, "--tg2-inject", "bogus").returncode != 0
