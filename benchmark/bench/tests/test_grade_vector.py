"""Grading v2: per-(item, sample) results, the convergence VECTOR, and per-sample coding grades.

THE METRIC VECTOR (replaces run-level INVALID). The old rule set `valid = every item converged`,
so one budget-hit in fifteen voided the run — ~40 rows in campaign-results.md are INVALID and
were then read anyway with asterisks. But the obvious replacement (a single "strict" pass@1 where
a truncated item counts as failed) cannot be the headline either: strict pass@1 is weakly monotone
increasing in `thinking_budget`, and the campaign holds rows at 16384 / 32768 / 81920, so a 5x
budget spread would masquerade as capability — making the budget a knob on the ranking metric,
which the measurement discipline explicitly forbids. It also fuses two mechanisms with different
fixes: a wrong answer is capability, external truncation is config x verbosity.

So grading reports a VECTOR and pre-registers how to read it:
    conv_rate >= 0.90 is a GATE;  pass@1 | converged RANKS within it.
`acc_strict@<budget>` is reported as a derived, budget-annotated deployment number, never the
ranking key. `acc` keeps its historical meaning so the existing rows stay comparable.

PER-SAMPLE CODING GRADES. `grade_evalplus` keyed its solutions dict by task_id
(`{r["id"]: code}`), so with k samples the LAST one silently won: pass@1 would be computed from
1/k of the data while CIs and reliability were reported over k. That is a wrong-number bug, not a
missing feature, and it is the reason --samples could not ship before this.
"""
import json

import pytest

import bench.grade as GR


def _row(id_, sample=0, *, ok=True, ct=100, budget=16384, finish="stop", **extra):
    """A reasoning row: content carries the boxed answer so grade_reasoning can score it."""
    return {"id": id_, "sample": sample, "schema_version": 2,
            "content": r"the answer is \boxed{42}" if ok else r"\boxed{7}",
            "answer_gold": "42", "completion_tokens": ct, "thinking_budget": budget,
            "finish_reason": finish, **extra}


# ------------------------------------------------------------------ per-item output
def test_every_grader_reports_per_item_id_and_sample(write_rows):
    write_rows("m", "math500", [_row("a", 0), _row("a", 1, ok=False), _row("b", 0)])
    s = GR.grade("math500", "m")
    keys = {(i["id"], i["sample"]) for i in s["items"]}
    assert keys == {("a", 0), ("a", 1), ("b", 0)}
    assert all("ok" in i and "score" in i for i in s["items"])


def test_score_is_binary_when_the_grader_has_no_partial_credit(write_rows):
    write_rows("m", "math500", [_row("a", 0)])
    assert GR.grade("math500", "m")["items"][0]["score"] == 1.0


# ------------------------------------------------------------------ the vector
def test_vector_separates_capability_from_truncation(write_rows):
    """A: right + converged. B: right but budget-hit. C: wrong + converged."""
    write_rows("m", "math500", [
        _row("A", ok=True, ct=100),
        _row("B", ok=True, ct=17000),          # >= budget -> did not self-terminate
        _row("C", ok=False, ct=100),
    ])
    s = GR.grade("math500", "m")
    assert s["conv_rate"] == 2 / 3
    assert s["pass_at_1_converged"] == 0.5      # A and C only: 1 of 2
    assert s["acc_strict"] == pytest.approx(1 / 3, abs=1e-4)   # B counts as failed
    assert s["acc_strict_budget"] == 16384      # ...annotated with the budget that produced it
    assert s["nonconv_kinds"]["budget_hit"] == 1


def test_acc_keeps_its_historical_meaning(write_rows):
    """`acc` must NOT be silently redefined: ~40 published rows were produced under the old
    definition (correctness, convergence-blind)."""
    write_rows("m", "math500", [_row("A", ok=True, ct=17000), _row("C", ok=False)])
    s = GR.grade("math500", "m")
    assert s["acc"] == 0.5, "acc = plain correctness over generated items, as before"
    assert s["acc_strict"] == 0.0


def test_valid_now_means_harness_clean_not_converged(write_rows):
    write_rows("m", "math500", [_row("A", ct=17000), _row("B", ct=17000)])
    s = GR.grade("math500", "m")
    assert s["conv_rate"] == 0.0
    assert s["valid"] is True, "non-convergence is a reported outcome, not a voided run"
    assert s["all_converged"] is False


def test_valid_is_false_when_the_harness_itself_failed(write_rows):
    write_rows("m", "math500", [{"id": "a", "sample": 0, "error": "connection reset"},
                                {"id": "b", "sample": 0, "error": "connection reset"},
                                _row("c")])
    s = GR.grade("math500", "m")
    assert s["valid"] is False and "error" in (s.get("note") or "")


def test_pre_registered_decision_rule_is_reported_not_left_to_the_reader(write_rows):
    write_rows("m", "math500", [_row(f"i{i}", ct=100) for i in range(9)] + [_row("x", ct=17000)])
    s = GR.grade("math500", "m")
    assert s["conv_rate"] == 0.9
    assert s["conv_gate_pass"] is True          # >= 0.90
    write_rows("m2", "math500", [_row(f"i{i}", ct=100) for i in range(8)] + [_row("x", ct=17000),
                                                                            _row("y", ct=17000)])
    assert GR.grade("math500", "m2")["conv_gate_pass"] is False


# ------------------------------------------------------------------ contamination
def test_contaminated_rows_are_excluded_from_pass_at_1_and_counted(write_rows):
    write_rows("m", "math500", [
        _row("A", ok=True),
        _row("B", ok=False, ct=17000, contaminated="stale_router",
             recovery_probe={"converged": True}),
    ])
    s = GR.grade("math500", "m")
    assert s["n_contaminated"] == 1
    assert s["acc"] == 1.0, "a known stale-router artifact must not be scored as a wrong answer"
    assert s["conv_rate"] == 0.5, "...but it still counts as the non-convergence it was"


# ------------------------------------------------------------------ multi-sample aggregation
def test_multisample_reports_interval_and_reliability(write_rows):
    """3 samples x 4 items; item d fails every draw, item c fails one."""
    rows = []
    for it in ("a", "b"):
        rows += [_row(it, s, ok=True) for s in range(3)]
    rows += [_row("c", 0, ok=True), _row("c", 1, ok=False), _row("c", 2, ok=True)]
    rows += [_row("d", s, ok=False) for s in range(3)]
    write_rows("m", "math500", rows)
    s = GR.grade("math500", "m")
    assert s["samples"] == 3
    assert s["acc"] == pytest.approx((1 + 1 + 2 / 3 + 0) / 4, abs=1e-4), \
        "items are the unit of analysis, not the pooled draws"
    assert s["ci95"] is not None and s["ci95"][0] <= s["acc"] <= s["ci95"][1]
    assert s["reliability"]["histogram"] == {3: 2, 2: 1, 0: 1}
    assert s["mde"] is not None, "no interval without its resolution"


def test_single_sample_reports_no_reliability(write_rows):
    write_rows("m", "math500", [_row("a"), _row("b")])
    s = GR.grade("math500", "m")
    assert s["samples"] == 1
    assert s["reliability"] is None, "reliability needs k>1; reporting it at k=1 would be a lie"


# ------------------------------------------------------------------ v1 compatibility
def test_v1_rows_grade_to_the_same_acc_and_conv_rate(write_rows):
    """The rows on both boxes have no `sample` and no `schema_version`."""
    v1 = [
        {"id": "a", "content": r"\boxed{42}", "answer_gold": "42", "completion_tokens": 100,
         "thinking_budget": 16384, "finish_reason": "stop"},
        {"id": "b", "content": r"\boxed{7}", "answer_gold": "42", "completion_tokens": 17000,
         "thinking_budget": 16384, "finish_reason": "stop"},
    ]
    write_rows("m", "math500", v1)
    s = GR.grade("math500", "m")
    assert s["acc"] == 0.5                       # unchanged from the v1 harness
    assert s["convergence_rate"] == 0.5          # legacy key preserved for existing readers
    assert s["conv_rate"] == 0.5                 # ...alongside the new name
    assert s["samples"] == 1
    assert {i["sample"] for i in s["items"]} == {0}


# ------------------------------------------------------------------ per-sample coding grades
def test_evalplus_grades_every_sample_not_just_the_last(write_rows, tmp_results):
    """The bug that made --samples silently grade 1/k of the data."""
    write_rows("m", "humanevalplus", [
        {"id": "HumanEval/0", "sample": 0, "content": "```python\ndef f():\n    return 1\n```"},
        {"id": "HumanEval/0", "sample": 1, "content": "```python\ndef f():\n    return 2\n```"},
        {"id": "HumanEval/1", "sample": 0, "content": "```python\ndef g():\n    return 3\n```"},
        {"id": "HumanEval/1", "sample": 1, "content": "```python\ndef g():\n    return 4\n```"},
    ])
    captured = {}

    def fake_runner(cmd, **kw):
        sdir = tmp_results / "m"
        captured["samples"] = [json.loads(l) for l in
                               (sdir / "humanevalplus_samples.jsonl").read_text().splitlines()]
        (sdir / "humanevalplus_samples_eval_results.json").write_text(json.dumps({"eval": {
            # HumanEval/0: sample 0 passes, sample 1 fails -> item score 0.5
            "HumanEval/0": [{"base_status": "pass", "plus_status": "pass"},
                            {"base_status": "pass", "plus_status": "fail"}],
            # HumanEval/1: both pass -> 1.0
            "HumanEval/1": [{"base_status": "pass", "plus_status": "pass"},
                            {"base_status": "pass", "plus_status": "pass"}],
            "HumanEval/2": [{"base_status": "fail", "plus_status": "fail"}],   # pad, ignored
        }}))
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    s = GR.grade_evalplus("humanevalplus", "m", runner=fake_runner,
                          all_ids=["HumanEval/0", "HumanEval/1", "HumanEval/2"])
    ours = [x for x in captured["samples"] if x["task_id"] in ("HumanEval/0", "HumanEval/1")]
    assert len(ours) == 4, "k solutions per task_id must reach the evaluator, in sample order"
    assert ours[0]["solution"].strip().endswith("return 1")
    assert ours[1]["solution"].strip().endswith("return 2")
    # NB grade_evalplus is called directly here, so the _finalize fields (samples/ci95/...) are
    # not attached — that is grade()'s job. Assert the grader's own contract.
    assert s["n"] == 2
    assert s["acc"] == 0.75                    # (0.5 + 1.0) / 2 — item-mean, then item-average
    assert {(i["id"], i["sample"]) for i in s["items"]} == {
        ("HumanEval/0", 0), ("HumanEval/0", 1), ("HumanEval/1", 0), ("HumanEval/1", 1)}


def test_evalplus_pad_gets_exactly_one_line(write_rows, tmp_results):
    """Padding exists only to satisfy evalplus's all-problems assertion; padding a task k times
    would inflate the evaluator's work with no benefit."""
    write_rows("m", "humanevalplus", [
        {"id": "HumanEval/0", "sample": s, "content": "```python\ndef f():\n    return 1\n```"}
        for s in range(3)])
    captured = {}

    def fake_runner(cmd, **kw):
        sdir = tmp_results / "m"
        captured["lines"] = [json.loads(l) for l in
                             (sdir / "humanevalplus_samples.jsonl").read_text().splitlines()]
        (sdir / "humanevalplus_samples_eval_results.json").write_text(json.dumps({"eval": {
            "HumanEval/0": [{"base_status": "pass", "plus_status": "pass"}] * 3}}))
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    GR.grade_evalplus("humanevalplus", "m", runner=fake_runner,
                      all_ids=["HumanEval/0", "HumanEval/9"])
    pads = [x for x in captured["lines"] if x["task_id"] == "HumanEval/9"]
    assert len(pads) == 1


# ------------------------------------------------------------------ graded outcomes
def test_graded_outcome_is_reported_alongside_binary_not_instead_of_it(write_rows):
    """Per-test pass FRACTION is a continuous per-item score (2-4x cheaper for a given
    resolution), but `acc` must stay the official all-tests-pass pass@1 so published numbers
    remain comparable."""
    items = [
        {"id": "q1", "sample": 0, "ok": False, "score": 0.0, "score_graded": 0.8},
        {"id": "q2", "sample": 0, "ok": True, "score": 1.0, "score_graded": 1.0},
    ]
    rows = [{"id": "q1", "sample": 0, "finish_reason": "stop", "completion_tokens": 10,
             "thinking_budget": 100},
            {"id": "q2", "sample": 0, "finish_reason": "stop", "completion_tokens": 10,
             "thinking_budget": 100}]
    s = GR._finalize({"items": items}, rows)
    assert s["acc"] == 0.5                       # official: 1 of 2 fully passed
    assert s["acc_graded"] == 0.9                # graded: (0.8 + 1.0) / 2
    assert s["ci95_graded"] is not None


def test_graded_is_none_when_the_evaluator_has_no_partial_credit(write_rows):
    items = [{"id": "q1", "sample": 0, "ok": True, "score": 1.0}]
    rows = [{"id": "q1", "sample": 0, "finish_reason": "stop", "completion_tokens": 10,
             "thinking_budget": 100}]
    s = GR._finalize({"items": items}, rows)
    assert s["acc"] == 1.0 and s["acc_graded"] is None
