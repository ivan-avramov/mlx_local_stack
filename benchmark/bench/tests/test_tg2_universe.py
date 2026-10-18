"""tg2 step 2: universe freeze and nested draw (fake grader; no docker)."""

import importlib.util
import json
import os
from pathlib import Path
import shutil

import pytest

from bench import tg2_grade as tg
from bench import tg2_materialize as mat
from bench.token_turn_gate import TransportAbort

M65 = Path(__file__).resolve().parents[2] / "m65"
TEST_ROOT = (Path(os.environ["STACK_WORKDIR"]) / "m65/test-tmp") if os.environ.get("STACK_WORKDIR") else (
    Path(__file__).resolve().parents[3] / ".tg2-test-tmp")


def load(name):
    spec = importlib.util.spec_from_file_location("m65_" + name, M65 / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


U = load("tg2_universe")


@pytest.fixture
def tmp_path():
    import uuid
    TEST_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEST_ROOT / ("u-" + uuid.uuid4().hex[:10])
    path.mkdir()
    yield path
    shutil.rmtree(path, ignore_errors=True)


def corpus(root, lang="javascript", slug="x", extra_docs=None, rust=False):
    ex = Path(root) / lang / "exercises/practice" / slug
    (ex / ".meta").mkdir(parents=True)
    if rust:
        (ex / "src").mkdir()
        (ex / ".meta/config.json").write_text(json.dumps({"files": dict(solution=["src/lib.rs", "Cargo.toml"],
                                                                       test=["tests/x.rs"], example=[".meta/example.rs"])}))
        (ex / "src/lib.rs").write_text("stub")
        (ex / "Cargo.toml").write_text('[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n')
        (ex / "tests").mkdir()
        (ex / "tests/x.rs").write_text("t")
        (ex / ".meta/example.rs").write_text("ref")
        (ex / ".meta/Cargo-example.toml").write_text('[dependencies]\nregex = "0.2"\n')
        return Path(root)
    (ex / ".meta/config.json").write_text(json.dumps({"files": dict(solution=["x.js"], test=["x.spec.js"],
                                                                   example=[".meta/proof.ci.js"])}))
    (ex / "x.js").write_text("stub")
    (ex / "x.spec.js").write_text("test('a')")
    (ex / ".meta/proof.ci.js").write_text("ref")
    if extra_docs:
        (ex / ".docs").mkdir()
        (ex / ".docs/instructions.md").write_text(extra_docs)
    return Path(root)


class Grader:
    """Scripted: reference trees contain `ref` in x.js; stubs contain `stub`."""

    def __init__(self, ref=None, stub=None, abort=False):
        self.ref = ref or (lambda n: dict(a=True, b=True))
        self.stub = stub or (lambda n: dict(a=False, b=False))
        self.abort, self.calls = abort, []

    def __call__(self, lang, tree, slug, private, *, prepared, solutions, timeout, prepared_cargo_toml=None, extra_crates=()):
        if self.abort:
            raise TransportAbort("docker down")
        is_ref = (Path(tree) / "x.js").read_text() == "ref"
        n = sum(1 for k, _ in self.calls if k == is_ref)
        self.calls.append((is_ref, n))
        leaves = (self.ref if is_ref else self.stub)(n)
        outcome = "parsed" if leaves is not None else "compile_failure"
        g = tg.Tg2Grade(lang=lang, outcome=outcome, leaves=leaves or {}, all_failed=leaves is None)
        g.phases = [dict(step="execute", seconds=2.0)]
        return g


def freeze(tmp_path, grader, **kw):
    c = corpus(tmp_path / "c", **kw)
    return U.freeze_item(c, "javascript", "x", tmp_path / "s", grader)


def test_a_clean_item_is_valid_with_three_reference_and_two_stub_runs(tmp_path):
    g = Grader()
    rec = freeze(tmp_path, g)
    assert rec["status"] == "valid" and rec["leaves"] == ["a", "b"] and rec["baseline_failing"] == 2
    assert len(rec["reference_runs"]) == 3 and len(rec["stub_runs"]) == 2 and len(g.calls) == 5
    assert rec["timeout_s"] == 180 and rec["solutions"] == ["x.js"] and rec["mapping"] == [[".meta/proof.ci.js", "x.js"]]


def test_reference_runs_get_the_examples_extra_crates_stub_runs_do_not(tmp_path):
    c = corpus(tmp_path / "c", lang="rust", slug="x", rust=True)
    seen = []

    class Spy(Grader):
        def __call__(self, lang, tree, slug, private, *, extra_crates=(), **k):
            seen.append(tuple(extra_crates))
            return Grader.__call__(self, lang, tree, slug, private, extra_crates=extra_crates, **k) if False else _ok(lang)

    def _ok(lang):
        g = tg.Tg2Grade(lang=lang, outcome="parsed", leaves=dict(a=True, b=True))
        g.phases = [dict(step="execute", seconds=1.0)]
        return g

    U.freeze_item(c, "rust", "x", tmp_path / "s", Spy())
    assert seen[:3] == [("regex",)] * 3 and seen[3:] == [(), ()]


def test_each_run_uses_a_fresh_tree_and_the_trees_are_cleaned_up(tmp_path):
    seen = []
    g = Grader()
    orig = g.__call__

    class Spy(Grader):
        def __call__(self, lang, tree, *a, **k):
            seen.append(str(tree))
            return Grader.__call__(self, lang, tree, *a, **k)

    freeze(tmp_path, Spy())
    assert len(set(seen)) == 5 and not any(Path(t).exists() for t in seen)


def test_reference_compile_failure_excludes_the_item_with_the_reason(tmp_path):
    rec = freeze(tmp_path, Grader(ref=lambda n: None))
    assert rec["status"] == "excluded" and "reference runs did not all parse" in rec["reason"]


def test_nondeterministic_reference_leaves_exclude_the_item(tmp_path):
    rec = freeze(tmp_path, Grader(ref=lambda n: dict(a=True, **({"b": True} if n != 2 else {}))))
    assert rec["status"] == "excluded" and "different leaf sets" in rec["reason"]


def test_a_failing_or_skipped_reference_leaf_excludes_the_item(tmp_path):
    rec = freeze(tmp_path, Grader(ref=lambda n: dict(a=True, b=False)))
    assert rec["status"] == "excluded" and "does not pass every collected leaf" in rec["reason"]


def test_a_stub_that_already_passes_has_zero_baseline_and_is_excluded(tmp_path):
    rec = freeze(tmp_path, Grader(stub=lambda n: dict(a=True, b=True)))
    assert rec["status"] == "excluded" and "baseline_failing == 0" in rec["reason"]


def test_stub_runs_must_collect_identical_leaves(tmp_path):
    rec = freeze(tmp_path, Grader(stub=lambda n: dict(a=False) if n == 0 else dict(a=False, b=False)))
    assert rec["status"] == "excluded" and "stub runs disagree" in rec["reason"]


def test_a_compile_failing_stub_is_a_valid_baseline(tmp_path):
    rec = freeze(tmp_path, Grader(stub=lambda n: None))
    assert rec["status"] == "valid" and rec["baseline_failing"] == 2


def test_js_optional_leaves_are_listed_and_excluded_from_the_universe(tmp_path, monkeypatch):
    monkeypatch.setitem(tg.OPTIONAL_LEAVES, ("javascript", "x"), frozenset({"opt"}))
    rec = freeze(tmp_path, Grader(ref=lambda n: dict(a=True, b=True, opt=False)))
    assert rec["status"] == "valid" and rec["leaves"] == ["a", "b"] and rec["optional_excluded"] == ["opt"]


def test_a_deprecated_item_is_excluded_before_any_grade(tmp_path):
    g = Grader()
    rec = freeze(tmp_path, g, extra_docs="This exercise has been deprecated.")
    assert rec["status"] == "excluded" and rec["reason"].startswith("deprecated") and g.calls == []


def test_a_plan_error_is_an_exclusion_with_its_reason(tmp_path):
    c = corpus(tmp_path / "c")
    cfg = c / "javascript/exercises/practice/x/.meta/config.json"
    cfg.write_text(json.dumps({"files": dict(solution=["x.js"], test=["x.spec.js"], example=[])}))
    rec = U.freeze_item(c, "javascript", "x", tmp_path / "s", Grader())
    assert rec["status"] == "excluded" and rec["reason"].startswith("plan:")


def test_infrastructure_failure_aborts_the_freeze_instead_of_excluding(tmp_path):
    with pytest.raises(TransportAbort):
        freeze(tmp_path, Grader(abort=True))


def test_run_all_caches_finished_items_logs_one_line_each_and_resumes(tmp_path):
    c = corpus(tmp_path / "c")
    for lang in ("rust", "java", "cpp"):
        (c / lang / "exercises/practice").mkdir(parents=True)
    g = Grader()
    log = tmp_path / "freeze.log"
    recs = U.run_all(c, tmp_path / "w", log, g, **ID)
    assert [r["item"] for r in recs] == ["javascript/x"] and len(log.read_text().splitlines()) == 1
    calls = len(g.calls)
    U.run_all(c, tmp_path / "w", log, g, **ID)
    assert len(g.calls) == calls and "cached" in log.read_text().splitlines()[-1]


ID = dict(image_id="sha256:" + "a" * 64, polyglot_sha="p" * 40)


def doc_for(records):
    return U.assemble(records, **ID)


def rec(item, status="valid", reason=""):
    return dict(fingerprint=U.fingerprint(**ID), item=item, status=status, reason=reason, scan=None, reference_runs=[dict(leaf_sha256="x", seconds=3.0)] * 3,
                stub_runs=[dict(leaf_sha256="y")] * 2, rewrites={}, optional_excluded=[])


# --------------------------------------------------------------------- S3: resumable records carry a fingerprint
def test_s3_fingerprint_names_corpus_image_grader_materializer_and_policy():
    fp = U.fingerprint(**ID)
    assert fp == dict(polyglot_sha="p" * 40, image_id="sha256:" + "a" * 64, grader_version=tg.VERSION,
                      materializer_version=mat.VERSION, policy=fp["policy"], cargo_locks_sha256=fp["cargo_locks_sha256"]) and len(fp["policy"]) == 64


def test_s6_fingerprint_carries_the_verified_cargo_locks_hash():
    assert U.fingerprint(**ID)["cargo_locks_sha256"] == tg.image_record()["cargo_locks_sha256"]


@pytest.mark.parametrize("attr,value", [("PIDS_LIMIT", 1), ("NOFILE_LIMIT", 1), ("FSIZE_LIMIT", 1), ("TIMEOUT_FLOOR", 1),
                                        ("OUTPUT_CAP", 1), ("REPORT_CAP", 1), ("TREE_CAP", 1), ("WORK_VOLUME_SIZE", "9g"),
                                        ("OPTIONAL_LEAVES", {})])
def test_s3_policy_covers_the_grader_resource_limits_and_optional_leaves(monkeypatch, attr, value):
    before = U.fingerprint(**ID)["policy"]
    monkeypatch.setattr(tg, attr, value)
    assert U.fingerprint(**ID)["policy"] != before


def test_s3_policy_covers_run_counts_timeout_and_the_allowlist(monkeypatch, tmp_path):
    before = U.fingerprint(**ID)["policy"]
    assert U.fingerprint(**ID, ref_runs=1)["policy"] != before and U.fingerprint(**ID, stub_runs=1)["policy"] != before
    monkeypatch.setattr(U, "GRADE_TIMEOUT", 1)
    assert U.fingerprint(**ID)["policy"] != before
    monkeypatch.undo()
    other = tmp_path / "allow.json"
    other.write_text(tg.ALLOWLIST_FILE.read_text() + " ")
    monkeypatch.setattr(tg, "ALLOWLIST_FILE", other)
    assert U.fingerprint(**ID)["policy"] != before


def _frozen_cache(tmp_path):
    c = corpus(tmp_path / "c")
    for lang in ("rust", "java", "cpp"):
        (c / lang / "exercises/practice").mkdir(parents=True)
    g = Grader()
    U.run_all(c, tmp_path / "w", tmp_path / "log", g, **ID)
    return c, g, len(g.calls)


def test_s3_resume_reuses_only_records_with_the_exact_fingerprint(tmp_path):
    c, g, calls = _frozen_cache(tmp_path)
    cached = json.loads((tmp_path / "w/items/javascript__x.json").read_text())
    assert cached["fingerprint"] == U.fingerprint(**ID)
    recs = U.run_all(c, tmp_path / "w", tmp_path / "log", g, **ID)
    assert len(g.calls) == calls and recs[0]["fingerprint"] == U.fingerprint(**ID)


@pytest.mark.parametrize("change", ["polyglot_sha", "image_id", "grader_version", "materializer_version", "policy"])
def test_s3_resume_refuses_every_fingerprint_mismatch_before_running_anything(tmp_path, monkeypatch, change):
    c, g, calls = _frozen_cache(tmp_path)
    before = (tmp_path / "w/items/javascript__x.json").read_bytes()
    kw = dict(ID)
    if change == "polyglot_sha":
        kw["polyglot_sha"] = "q" * 40
    elif change == "image_id":
        kw["image_id"] = "sha256:" + "b" * 64
    elif change == "grader_version":
        monkeypatch.setattr(tg, "VERSION", "other")
    elif change == "materializer_version":
        monkeypatch.setattr(mat, "VERSION", "other")
    else:
        monkeypatch.setattr(tg, "PIDS_LIMIT", 1)
    with pytest.raises(TransportAbort, match=r"javascript/x.*%s" % change):
        U.run_all(c, tmp_path / "w", tmp_path / "log", g, **kw)
    assert len(g.calls) == calls and (tmp_path / "w/items/javascript__x.json").read_bytes() == before


def test_s3_a_legacy_unfingerprinted_cache_record_is_refused(tmp_path):
    c, g, calls = _frozen_cache(tmp_path)
    path = tmp_path / "w/items/javascript__x.json"
    legacy = json.loads(path.read_text())
    del legacy["fingerprint"]
    path.write_text(json.dumps(legacy))
    with pytest.raises(TransportAbort, match="fingerprint"):
        U.run_all(c, tmp_path / "w", tmp_path / "log", g, **ID)
    assert len(g.calls) == calls


def test_s3_assemble_refuses_records_whose_fingerprint_is_missing_or_differs():
    good = rec("rust/a")
    with pytest.raises(TransportAbort, match="rust/b.*image_id"):
        doc_for([good, dict(rec("rust/b"), fingerprint=U.fingerprint(image_id="sha256:" + "c" * 64, polyglot_sha="p" * 40))])
    stale = rec("rust/c")
    del stale["fingerprint"]
    with pytest.raises(TransportAbort, match="rust/c"):
        doc_for([good, stale])
    doc = doc_for([good])
    assert doc["fingerprint"] == U.fingerprint(**ID) and doc["materializer_version"] == mat.VERSION
    assert "fingerprint" not in doc["items"]["rust/a"]


def test_s3_load_refuses_a_universe_frozen_by_another_materializer(tmp_path, monkeypatch):
    out = tmp_path / "u.json"
    U.freeze(out, doc_for([rec("rust/a")]))
    monkeypatch.setattr(mat, "VERSION", "other")
    with pytest.raises(TransportAbort, match="materializer"):
        U.load(out)


def test_assemble_counts_n_actual_per_language_and_lists_exclusions():
    doc = doc_for([rec("rust/a"), rec("rust/b", "excluded", "ref broken"), rec("java/c")])
    assert doc["languages"]["rust"] == dict(valid=["rust/a"], excluded={"rust/b": "ref broken"}, N_actual=1)
    assert doc["languages"]["java"]["N_actual"] == 1


def test_freeze_writes_a_sidecar_refuses_overwrite_and_load_verifies(tmp_path):
    doc = doc_for([rec("rust/a")])
    out = tmp_path / "u.json"
    sha = U.freeze(out, doc)
    assert (tmp_path / "u.json.sha256").read_text().strip() == sha
    with pytest.raises(TransportAbort, match="already exists"):
        U.freeze(out, doc)
    loaded, lsha = U.load(out)
    assert lsha == sha and loaded["languages"]["rust"]["N_actual"] == 1
    out.write_text(out.read_text() + " ")
    with pytest.raises(TransportAbort):
        U.load(out)


def test_report_lists_counts_exclusions_and_determinism():
    text = U.report(doc_for([rec("rust/a"), rec("rust/grep", "excluded", "reference does not compile")]), "s" * 64)
    assert "| rust | 2 | 1 | 1 |" in text and "`rust/grep`: reference does not compile" in text
    assert "identical leaf sets: 1 of 1" in text


# --------------------------------------------------------------------------------------------------------- draw
D = load("tg2_draw")


def universe_doc(counts):
    recs = []
    for lang, n in counts.items():
        recs += [rec("%s/item%02d" % (lang, i)) for i in range(n)]
    return doc_for(recs)


def test_draw_is_the_seeded_sample_of_the_sorted_valid_ids_per_language_with_nested_prefixes():
    import random
    doc = universe_doc(dict(rust=25, java=30))
    draw = D.make_draw(doc, "u" * 64)
    valid = doc["languages"]["rust"]["valid"]
    assert draw["languages"]["rust"]["permutation"] == random.Random(6501).sample(sorted(valid), 25)
    assert draw["languages"]["rust"]["screen"] == draw["languages"]["rust"]["permutation"][:10]
    assert draw["languages"]["rust"]["decider"] == draw["languages"]["rust"]["permutation"][:20]
    assert draw["languages"]["rust"]["decider"][:10] == draw["languages"]["rust"]["screen"]     # nested
    assert draw["seed"] == 6501 and draw["universe_sha256"] == "u" * 64


def test_languages_below_the_decider_prefix_are_flagged_for_operator_acknowledgement_not_decided():
    draw = D.make_draw(universe_doc(dict(rust=19, java=30, cpp=5)), "u" * 64)
    assert draw["needs_operator_acknowledgement"] == {"cpp": 5, "rust": 19}
    assert len(draw["languages"]["cpp"]["screen"]) == 5 and len(draw["languages"]["cpp"]["decider"]) == 5
    assert "java" not in draw["needs_operator_acknowledgement"]


def test_draw_freezes_canonically_refuses_overwrite_and_load_verifies(tmp_path):
    draw = D.make_draw(universe_doc(dict(rust=25)), "u" * 64)
    out = tmp_path / "d.json"
    sha = D.freeze(out, draw)
    assert (tmp_path / "d.json.sha256").read_text().strip() == sha
    assert out.read_bytes() == (json.dumps(draw, sort_keys=True, indent=1) + "\n").encode()
    with pytest.raises(TransportAbort, match="already exists"):
        D.freeze(out, draw)
    got, gsha = D.load(out)
    assert gsha == sha and got == json.loads(json.dumps(draw))
    out.write_text("{}")
    with pytest.raises(TransportAbort):
        D.load(out)


def test_tier_prefix_verification_refuses_a_mismatch():
    draw = D.make_draw(universe_doc(dict(rust=25)), "u" * 64)
    assert D.tier_items(draw, "rust", "screen") == draw["languages"]["rust"]["screen"]
    with pytest.raises(TransportAbort):
        D.tier_items(draw, "rust", "bogus")
