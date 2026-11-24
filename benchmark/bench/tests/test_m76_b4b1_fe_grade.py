"""M76 B4b-1 (spec v5 §1 "Grade call (E7, G9)", "Grader mapping", `structured_grade.validate_reports`, the join bound): the grade call's
arguments, the grader mapping for every terminal outcome on the RECORDED real `tg2_grade` trees, the resource flags, the
out-of-universe failing leaf, the report validator and the join bound. Only docker is faked: `tg2_grade.grade_item` /
`tg2_grade.grade` are replaced by recorders returning the recorded results (`GUESSES["grade-seam"]`). Class of each test is in the
comment above it: (a) reproduces a failure the spec fixes, (b) preserves an invariant, (c) new behaviour."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.tests import test_m76_b4b1_fe_support as S

RECORDED = [(lang, v) for lang in S.LANGS for v in ("reference", "stub", "compile", "tampered")] + [
    ("rust", "alloc"), ("rust", "flood")]


def _outcome(result, lang, seq=3, boundary="final", final=True):
    mod = S.bench_mod("corpus_tg2", "grade-outcome")
    fn = S.attr(mod, "grade_outcome", "grade-outcome")
    entry = S.entry_of(S.PILOT[lang])
    return fn(result, entry, seq=seq, boundary=boundary, final=final), entry


# ------------------------------------------------------------------------------------------------ the mapping
# (c) every recorded real outcome maps to a GradeOutcome with outcome "model" and the recorded counts
@pytest.mark.parametrize("lang,variant", RECORDED)
def test_mapping_of_recorded_outcomes(lang, variant):
    summary = S.recorded_summary(lang, variant)
    result = S.recorded_grade(lang, variant)
    out, entry = _outcome(result, lang)
    universe = set(entry["leaves"])
    assert out.outcome == "model"
    assert out.phases == (dict(seq=3, boundary="final", final=True, outcome=result.outcome),)
    assert out.reports == dict(result.artifacts)
    if summary["outcome"] == "tampered":
        assert out.tampered is True and out.failing is None and out.leaves == ()
        assert out.passed is False
        return
    assert out.tampered is False
    if summary["outcome"] == "parsed":
        passing = {k for k, ok in result.leaves.items() if ok}
        assert out.failing == summary["failing"]
        assert set(out.leaves) == universe & passing and list(out.leaves) == sorted(out.leaves)
    else:                                       # compile_failure / oom / output_cap: every leaf failing
        assert out.failing == len(universe) == summary["failing"]
        assert out.leaves == ()
    assert out.passed is (summary["outcome"] == "parsed" and summary["failing"] == 0)
    assert out.resources == dict(grader_oom=(summary["outcome"] == "oom"), grader_mem_kill=False)


# (c) the reference of every language passes with every universe leaf passing; the stub fails every leaf
@pytest.mark.parametrize("lang", S.LANGS)
def test_reference_passes_and_stub_fails(lang):
    ref, entry = _outcome(S.recorded_grade(lang, "reference"), lang)
    stub, _ = _outcome(S.recorded_grade(lang, "stub"), lang)
    assert ref.passed and ref.failing == 0 and list(ref.leaves) == sorted(entry["leaves"])
    assert not stub.passed and stub.failing == len(entry["leaves"]) and stub.leaves == ()


# (c) a collected failure OUTSIDE the universe counts (initialisation / suite-level event): the recorded real javascript compile
# tree collects one failing leaf that is not a universe leaf
def test_out_of_universe_failing_leaf_is_counted_on_the_recorded_tree():
    result = S.recorded_grade("javascript", "compile")
    out, entry = _outcome(result, "javascript")
    outside = [k for k, ok in result.leaves.items() if not ok and k not in set(entry["leaves"])]
    assert outside, "the recorded tree has no out-of-universe failing leaf"
    assert out.failing == len(entry["leaves"]) + len(outside) and out.leaves == ()


# (c) ... and on a passing run with one extra failing leaf: all universe leaves still pass, failing == 1
def test_out_of_universe_failing_leaf_on_a_passing_run():
    result = S.recorded_grade("rust", "reference")
    result.leaves["tests/say.rs::teardown_event"] = False
    out, entry = _outcome(result, "rust")
    assert out.failing == 1 and list(out.leaves) == sorted(entry["leaves"]) and not out.passed


# (c) the outcomes with no recorded real tree (SYNTHETIC results): every leaf failing, flags per outcome
@pytest.mark.parametrize("outcome", ["timeout", "oom", "mem_kill", "crash", "storage_cap", "output_cap", "compile_failure"])
@pytest.mark.parametrize("lang", ["rust", "java"])
def test_mapping_of_nonparsed_outcomes_and_resource_flags(lang, outcome):
    out, entry = _outcome(S.synthetic_grade(lang, outcome, S.PILOT[lang].split("/", 1)[1]), lang, seq=1, boundary="b", final=False)
    assert out.outcome == "model" and out.tampered is False
    assert out.failing == len(entry["leaves"]) and out.leaves == ()
    assert out.resources == dict(grader_oom=(outcome == "oom"), grader_mem_kill=(outcome == "mem_kill"))
    assert out.phases == (dict(seq=1, boundary="b", final=False, outcome=outcome),)


# (c) a transport abort propagates (no GradeOutcome): the recorded real `spin` tree is a TransportAbort
def test_transport_abort_propagates_through_the_mapping_and_the_corpus_grade(tmp_path, monkeypatch):
    from bench import tg2_grade
    from bench.token_turn_gate import TransportAbort
    with pytest.raises(TransportAbort):
        S.recorded_grade("rust", "spin")
    corpus = S.make_corpus()
    prepared = S.prepare_item(corpus, S.PILOT["rust"], tmp_path / "w")

    def abort(*a, **k):
        raise TransportAbort(S.recorded_summary("rust", "spin")["reason"])
    monkeypatch.setattr(tg2_grade, "grade_item", abort)
    private = tmp_path / "run" / "grading-private"
    private.mkdir(parents=True)
    with corpus.snapshot(prepared.work, private, "final") as snap:
        with pytest.raises(TransportAbort):
            corpus.grade(snap, prepared, private, None, None, 1, "final", True)


# ------------------------------------------------------------------------------------------------ the grade call
class Spy:
    def __init__(self, result):
        self.result, self.calls = result, []

    def __call__(self, lang, work, slug, private, **kw):
        self.calls.append(dict(lang=lang, work=Path(work), slug=slug, private=Path(private), **kw))
        return self.result


# (c) `tg2_grade.grade_item(lang, snap.path, slug, private, prepared=, solutions=, prepared_cargo_toml=, extra_crates=(), keep=,
# seq=, boundary=, final=, guard=, timeout=entry["timeout_s"])`, for every language; the snapshot is not inside private
@pytest.mark.parametrize("lang", S.LANGS)
def test_grade_call_arguments(lang, tmp_path, monkeypatch):
    from bench import tg2_grade
    corpus = S.make_corpus()
    item = S.PILOT[lang]
    prepared = S.prepare_item(corpus, item, tmp_path / "w")
    spy = Spy(S.recorded_grade(lang, "reference"))
    monkeypatch.setattr(tg2_grade, "grade_item", spy)
    run = tmp_path / "run"
    private, keep, guard = run / "grading-private", run / (item.replace("/", "__") + ".grades"), object()
    private.mkdir(parents=True)
    with corpus.snapshot(prepared.work, private, "final") as snap:
        out = corpus.grade(snap, prepared, private, guard, keep, 4, "final", True)
        want_work = Path(snap.path)
    (call,) = spy.calls
    entry = S.entry_of(item)
    assert call["lang"] == lang and call["slug"] == item.split("/", 1)[1] and call["work"] == want_work
    assert call["private"] == private
    # S29 T1 (changed): the grader gets the testable tree's manifest (same files as the frozen `prepared`)
    assert call["prepared"] == prepared.prepared and set(call["prepared"]) == set(entry["prepared"])
    assert list(call["solutions"]) == list(entry["solutions"])
    assert call["prepared_cargo_toml"] == entry.get("prepared_cargo_toml")
    assert tuple(call["extra_crates"]) == ()
    assert (call["keep"], call["seq"], call["boundary"], call["final"], call["guard"], call["timeout"]) == (
        keep, 4, "final", True, guard, entry["timeout_s"])
    assert out.passed and out.outcome == "model"


# (c) E7: an unsnapshottable tree (snap None) is the tampered outcome WITHOUT calling the grader
def test_no_snapshot_is_tampered_without_a_grader_call(tmp_path, monkeypatch):
    from bench import tg2_grade
    corpus = S.make_corpus()
    prepared = S.prepare_item(corpus, S.PILOT["rust"], tmp_path / "w")
    spy = Spy(S.recorded_grade("rust", "reference"))
    monkeypatch.setattr(tg2_grade, "grade_item", spy)
    monkeypatch.setattr(tg2_grade, "grade", spy)
    out = corpus.grade(None, prepared, tmp_path / "run" / "grading-private", None, None, 1, "final", True)
    assert out.tampered is True and out.failing is None and out.leaves == () and out.outcome == "model"
    assert not spy.calls
    assert out.phases == (dict(seq=1, boundary="final", final=True, outcome="tampered"),)


# (c) a protected-tree violation never reaches docker: `grade_item` runs for real (strip + tamper check), the inner docker
# grade is never called, and the typed tamper receipt is written under `keep`
@pytest.mark.parametrize("lang", S.LANGS)
def test_protected_tree_violation_runs_no_grader(lang, tmp_path, monkeypatch):
    from bench import tg2_grade
    corpus = S.make_corpus()
    prepared = S.prepare_item(corpus, S.PILOT[lang], tmp_path / "w")
    test_file = prepared.work / prepared.tests[0]
    test_file.write_text(test_file.read_text() + "\n// edited\n")
    inner = Spy(S.recorded_grade(lang, "reference"))
    monkeypatch.setattr(tg2_grade, "grade", inner)
    run = tmp_path / "run"
    private, keep = run / "grading-private", run / "x.grades"
    private.mkdir(parents=True)
    with corpus.snapshot(prepared.work, private, "final") as snap:
        out = corpus.grade(snap, prepared, private, None, keep, 1, "final", True)
    assert out.tampered is True and out.failing is None and out.leaves == () and out.outcome == "model"
    assert not inner.calls
    assert out.resources == dict(grader_oom=False, grader_mem_kill=False)


# (b) an untampered tree reaches the inner grade with the build outputs already stripped by the real `grade_item`
def test_clean_tree_reaches_the_inner_grade_stripped(tmp_path, monkeypatch):
    from bench import tg2_grade
    corpus = S.make_corpus()
    prepared = S.prepare_item(corpus, S.PILOT["rust"], tmp_path / "w")
    (prepared.work / "target").mkdir()
    (prepared.work / "target" / "x").write_text("o")
    (prepared.work / "src" / "lib.rs").write_text("pub fn say(_: u64) -> String { String::new() }\n")
    seen = {}

    def inner(lang, work, slug, private, **kw):
        seen["tops"] = sorted(p.name for p in Path(work).iterdir())
        seen["kw"] = kw
        return S.recorded_grade("rust", "stub")
    monkeypatch.setattr(tg2_grade, "grade", inner)
    run = tmp_path / "run"
    private = run / "grading-private"
    private.mkdir(parents=True)
    with corpus.snapshot(prepared.work, private, "final") as snap:
        out = corpus.grade(snap, prepared, private, None, None, 1, "final", False)
    assert "target" not in seen["tops"] and out.failing == len(S.entry_of("rust/say")["leaves"])


# ------------------------------------------------------------------------------------------------ validate_reports
def _row_reports(lang, variant="reference"):
    """A row's `grade_reports` of the recorded real grade: `arm_runner.grade_reports` over the recorded `<item>.grades` directory
    (the core's own reader), with the integer boundary the core writes (the recording harness named it `final`)."""
    from bench import arm_runner
    reports = arm_runner.grade_reports(S.grades_dir(lang, variant))
    assert len(reports) == 1 and reports[0]["final"] is True
    return [dict(r, boundary=0) for r in reports]


def _problems(reports, lang, test_modified=False):
    from bench import structured_grade as sg
    # AMENDED (delivery 2): the tg2 rules are selected by `grader="tg2"` (both production callers — `chain_ops.validate_leg` and
    # `m62/inject_verify` — pass it for the tg2 scaffold; the M64 fake corpus reuses these language names with Go-shaped receipts)
    return sg.validate_reports(reports, lang, test_modified, **({"grader": "tg2"} if lang in S.LANGS else {}))


# (b) the recorded real parsed report sets of the tg2 languages are valid (the baseline has no rule for these languages and lets most
# pass; the refusals the spec adds are the tests below)
@pytest.mark.parametrize("lang", S.LANGS)
def test_validate_reports_accepts_recorded_parsed_artifacts(lang):
    assert _problems(_row_reports(lang), lang) == []
    assert _problems(_row_reports(lang, "stub"), lang) == []


# (c) the outcome set of `tg2_grade` (compile_failure, output_cap on recorded real trees) is accepted as a final outcome;
# a tampered receipt (no grader ran) carries no artifacts and needs `test_modified`
@pytest.mark.parametrize("lang,variant", [("rust", "compile"), ("rust", "alloc"), ("rust", "flood"), ("cpp", "compile"),
                                          ("java", "compile")])
def test_validate_reports_accepts_the_recorded_nonparsed_outcomes(lang, variant):
    assert _problems(_row_reports(lang, variant), lang) == []


def test_validate_reports_tampered_receipt_rules():
    report = dict(boundary=0, seq=1, final=True, outcome="tampered", artifacts={})
    assert _problems([report], "rust", test_modified=True) == []
    assert _problems([report], "rust", test_modified=False) != []                  # tg1's rule, kept
    assert _problems([dict(report, artifacts=_row_reports("rust")[0]["artifacts"])], "rust", test_modified=True) != []


# (c) a parsed outcome whose language-specific report artifact is missing is refused (the failure path of the same rule)
@pytest.mark.parametrize("lang,pattern", [("java", "junit-"), ("cpp", "report.xml"), ("javascript", "report.json"),
                                          ("rust", "execute.stdout")])
def test_validate_reports_refuses_a_parsed_set_without_its_report(lang, pattern):
    reports = _row_reports(lang)
    reports[0]["artifacts"] = {k: v for k, v in reports[0]["artifacts"].items() if pattern not in k}
    assert _problems(reports, lang), "a parsed tg2 report set without %s was accepted" % pattern


# (c) the `parsed` artifact is matched by PATTERN: a second Java report file is accepted, a renamed one is not
def test_validate_reports_java_report_pattern():
    reports = _row_reports("java")
    arts = reports[0]["artifacts"]
    first = next(k for k in arts if k.startswith("junit-") and k.endswith(".xml"))
    reports[0]["artifacts"] = dict(arts, **{"junit-001.xml": arts[first]})
    assert _problems(reports, "java") == []
    renamed = dict(arts)
    renamed["results.xml"] = renamed.pop(first)
    assert _problems([dict(_row_reports("java")[0], artifacts=renamed)], "java")


# (b) tg1 languages are validated as before: the same inputs, the same reasons
def test_validate_reports_tg1_languages_unchanged():
    art = dict(path="x", sha256="a" * 64)
    ok_py = [dict(boundary=0, seq=1, final=True, outcome="parsed", artifacts={"stdout.txt": art, "stderr.txt": art, "report.xml": art})]
    assert _problems(ok_py, "python") == []
    assert _problems(ok_py, "go") != []                                           # go needs go.jsonl / go.stderr
    assert _problems([dict(ok_py[0], outcome="compile_failure")], "python") != []   # tg1 has no compile_failure outcome


# ------------------------------------------------------------------------------------------------ join bound
def _t_coop(co, tokens, lang, bound, corpus):
    """`chain_ops.t_coop` takes the grader bound from the corpus identity (GUESS: a third positional / keyword)."""
    last = None
    for call in (lambda: co.t_coop(tokens, lang, bound), lambda: co.t_coop(tokens, lang, grader_timeout_s=bound),
                 lambda: co.t_coop(tokens, lang, corpus=corpus), lambda: co.t_coop(tokens, lang, identity=corpus.identity()),
                 lambda: co.t_coop(tokens, lang, timeouts=bound)):
        try:
            return call()
        except TypeError as exc:
            last = exc
    pytest.fail(f"SPELLING GUESS t_coop: no accepted way to pass the corpus grader bound ({last})", pytrace=False)


# (a) the baseline's table has no tg2 language (300 s default): a worst-case tg2 grade outlives the cooperative bound
def test_baseline_t_coop_default_is_too_small_for_a_worst_case_tg2_grade():
    from bench import chain_ops as co
    worst = 2 * max(e["timeout_s"] for e in S.universe_doc()["items"].values() if e.get("status") == "valid") + 300
    for lang in S.LANGS:
        assert worst > co.GRADER_TIMEOUT_S.get(lang, 300)


# (c) t_coop for a tg2 leg = 5 + 660 + max(300, prompt/300) + 120 + <corpus grader bound of the language> + 60 + 20
@pytest.mark.parametrize("lang", S.LANGS)
def test_t_coop_uses_the_corpus_grader_bound(lang):
    from bench import chain_ops as co
    from bench import arm_runner
    corpus = S.make_corpus()
    bound = corpus.identity()["grader_timeout_s"]
    # AMENDED (delivery 2): tg1's 660 s is `grade_join_timeout_s` over tg1's timeouts (2 x 300 + 60); the tg2 term is the same
    # function over the corpus identity, i.e. the join covers the active grade plus one queued capture at the worst-case grade
    join = arm_runner.grade_join_timeout_s(bound)
    assert join == 2 * max(bound.values()) + 60 > 660
    for tokens in (0, 90_000, 250_000):
        want = 5 + join + max(300, tokens / 300) + 120 + bound[lang] + 60 + 20
        assert _t_coop(co, tokens, lang, bound, corpus) == want


# (b) tg1's table is unchanged for tg1
@pytest.mark.parametrize("lang", ["python", "go"])
def test_t_coop_tg1_unchanged(lang):
    from bench import chain_ops as co
    want = 5 + 660 + max(300, 90_000 / 300) + 120 + co.GRADER_TIMEOUT_S.get(lang, 300) + 60 + 20
    assert co.t_coop(90_000, lang) == want


# (c) the terminal join covers the active grade plus one queued capture at the WORST-CASE grade (largest item timeout x2 + 300)
def test_grade_join_covers_a_worst_case_grade_and_tg1_timeouts_would_not():
    from bench import arm_runner, structured_grade as sg
    corpus = S.make_corpus()
    bound = corpus.identity()["grader_timeout_s"]
    worst_item = max(e["timeout_s"] for e in S.universe_doc()["items"].values() if e.get("status") == "valid")
    assert max(bound.values()) >= 2 * worst_item + 300
    assert arm_runner.grade_join_timeout_s(bound) >= 2 * (2 * worst_item + 300) + arm_runner.GRADE_JOIN_OVERHEAD_S
    assert arm_runner.grade_join_timeout_s(dict(sg.TIMEOUTS)) < 2 * (2 * worst_item + 300)       # the failure the identity bound fixes
