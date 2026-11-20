"""S27 (spec v1.4, section 4.3, acceptance 10.1) -- blind test-writer, delivery 1: the order-tolerant in-flight link of the
injected positives (`PASS_NO_INFLIGHT`) and its consumers.

Rows, manifests and events are built by `test_c147_inject_verify.make_row` (the real shapes `inject_verify.verify_row` reads);
the tg2 positives record is driven through `p426_wave2.main(["positives", ...])` with the S26 fake ops, as the existing
`test_s27_p6_positives_transfer.py` does.

Class of each test: (a) reproduces a failure the spec fixes, (b) preserves an invariant, (c) exercises new behaviour.

Interface assumptions:
  P1  the verdict string is `PASS_NO_INFLIGHT` (spec 4.3), printed as the first line of `inject_verify.main` like `PASS`;
  P2  `inject_verify.main` exits 0 for it (the suite rule accepts it for stall / loop; the spec says consumers 'gain' it);
  P3  `p426_freeze.inject_accepted(entry)` accepts an entry whose `verdict` is `PASS_NO_INFLIGHT` for kind stall / loop;
  P4  `m62/run_m62_live.py` (the frozen copy under chains/) holds no verdict comparison, so its 'results' consumer is
      `inject_verify.main`'s suite rule: see the report.
"""
from __future__ import annotations

import pytest

from bench import p426_freeze as fz
from bench.tests.s26_frozen import s26_support as X
from bench.tests.test_c147_inject_verify import verdict

NO_INFLIGHT = "PASS_NO_INFLIGHT"
QUIET = dict(in_flight=0, requests_started=4, requests_completed=4, requests_failed=0)


def nothing_in_flight(*, before=None, after=None, trailing="none", in_flight_at_kill=0):
    """A stop whose client kill landed with no request in flight: the worker's counters unchanged around it."""
    def mutate(row, manifest):
        row["reconciliation"]["trailing"] = trailing
        row["termination"].update(in_flight_at_kill=in_flight_at_kill, worker_summary_before=dict(before or QUIET),
                                  worker_summary_after=dict(after or QUIET))
    return mutate


def also(*mutations):
    def mutate(row, manifest):
        for m in mutations:
            m(row, manifest)
    return mutate


# ------------------------------------------------------------------------------------------------ inject_verify
@pytest.mark.parametrize("kind", ["stall", "loop"])
def test_a_stop_with_nothing_in_flight_is_pass_no_inflight(tmp_path, kind):
    """(a) The baseline answers `not_observed:trailing` (the kill landed after the in-flight message was settled)."""
    v, code, lines = verdict(tmp_path, kind, nothing_in_flight())
    assert v == NO_INFLIGHT, lines
    assert code == 0


@pytest.mark.parametrize("kind", ["stall", "loop"])
def test_with_a_request_in_flight_the_verdict_is_still_the_plain_pass(tmp_path, kind):
    """(b) The existing proof is unchanged and the two verdicts stay distinguishable."""
    v, code, _ = verdict(tmp_path, kind)
    assert v == "PASS" and code == 0


def test_the_loop_without_the_descendant_kill_is_not_observed_even_with_nothing_in_flight(tmp_path):
    """(b) 'for loop the model-role `sleep 600` descendant kill' stays required."""
    def drop_descendant(row, manifest):
        row["termination"]["killed"] = [k for k in row["termination"]["killed"] if k.get("role") == "client"]
    v, code, _ = verdict(tmp_path, "loop", also(nothing_in_flight(), drop_descendant))
    assert v.startswith("not_observed") and code == 4


@pytest.mark.parametrize("what, mutation, expected", [
    ("killed_verified is not true", dict(killed_verified=False), "FAIL:causal:killed_verified"),
    ("cancel_wait_s beyond the bound", dict(cancel_wait_s=301), "FAIL:causal:cancel_wait_s"),
    ("cancel_wait_s missing", dict(cancel_wait_s=None), "FAIL:causal:cancel_wait_s"),
])
@pytest.mark.parametrize("kind", ["stall", "loop"])
def test_the_unchanged_checks_stay_with_nothing_in_flight(tmp_path, kind, what, mutation, expected):
    """(b) stop reason, client kill, killed_verified and the cancel_wait_s bound are not weakened by the new verdict."""
    def term(row, manifest):
        row["termination"].update(mutation)
    v, _, _ = verdict(tmp_path, kind, also(nothing_in_flight(), term))
    assert v == expected, what


def test_no_client_kill_with_nothing_in_flight_is_not_observed(tmp_path):
    def no_client(row, manifest):
        row["termination"].update(killed=[], reason=None)
    v, _, _ = verdict(tmp_path, "stall", also(nothing_in_flight(), no_client))
    assert v == "not_observed:kill"


@pytest.mark.parametrize("what, before, after, kw", [
    ("the worker started a request between the samples", QUIET, dict(QUIET, requests_started=5), {}),
    ("the worker still shows one in flight afterwards", QUIET, dict(QUIET, in_flight=1), {}),
    ("the worker completed a request between the samples", QUIET, dict(QUIET, requests_completed=5, requests_started=5), {}),
    ("a request was in flight at the kill sample", dict(QUIET, in_flight=1), QUIET, dict(in_flight_at_kill=1)),
])
def test_anything_less_than_a_quiet_worker_is_not_the_no_inflight_verdict(tmp_path, what, before, after, kw):
    """(b) in_flight_at_kill == 0, requests_started unchanged and after.in_flight == 0 are ALL required."""
    v, _, _ = verdict(tmp_path, "stall", nothing_in_flight(before=before, after=after, trailing="none", **kw))
    assert v not in (NO_INFLIGHT, "PASS"), what


def test_an_interrupted_trailing_message_is_not_the_no_inflight_case(tmp_path):
    """(b) `trailing` an interrupted kind with in_flight_at_kill == 0 is the baseline's PASS with `cancellation_not_shown`:
    the new verdict is reserved for 'trailing not an interrupted kind'."""
    v, _, lines = verdict(tmp_path, "stall", nothing_in_flight(trailing="interrupted"))
    assert v == "PASS" and any("cancellation_not_shown" in x for x in lines)


# ------------------------------------------------------------------------------------------------ consumers
@pytest.mark.parametrize("kind", ["stall", "loop"])
def test_the_freeze_accepts_a_record_entry_with_the_new_verdict(kind):
    """(a) P3: `p426_freeze.inject_accepted` (the v8 positives rule)."""
    assert fz.inject_accepted(dict(language="rust", kind=kind, verdict=NO_INFLIGHT, row_sha256="0" * 64))


def test_the_freeze_still_refuses_an_unknown_verdict_string():
    """(b)"""
    assert not fz.inject_accepted(dict(language="rust", kind="stall", verdict="PASS_SOMETHING_ELSE"))
    assert not fz.inject_accepted(dict(language="rust", kind="stall", verdict="not_observed:trailing"))


def test_a_tg2_positives_record_with_a_no_inflight_stall_freezes_in_v8(tmp_path, monkeypatch):
    """(a) The record is PASS, the entry keeps its distinguishing verdict, and v8's own check of the record passes."""
    world = X.HostWorld(tmp_path / "host")
    ops = X.PosOps(tmp_path, world, verdicts={("rust", "stall"): NO_INFLIGHT, ("java", "loop"): NO_INFLIGHT})
    rc, out = X.positives(tmp_path, monkeypatch, ops)
    doc = X.record(out)
    assert X.inject_of(doc, "rust", "stall")["verdict"] == NO_INFLIGHT
    assert X.inject_of(doc, "java", "loop")["verdict"] == NO_INFLIGHT
    assert rc == 0 and doc["verdict"] == "PASS" and doc["problems"] == []
    assert fz.positives_problems(doc, arm="n16", commit=X.COMMIT, identity=dict(X.IDENT), frozen_prompt_date=X.DATE,
                                 image_id=doc["image_id"], cancel_path_sha256=fz.CANCEL_PATH_SHA256) == []


def test_a_tg2_positives_record_with_a_failed_stall_still_fails(tmp_path, monkeypatch):
    """(b) PASS_NO_INFLIGHT does not widen what the record accepts."""
    world = X.HostWorld(tmp_path / "host")
    ops = X.PosOps(tmp_path, world, verdicts={("rust", "stall"): "FAIL:causal:killed_verified"})
    rc, out = X.positives(tmp_path, monkeypatch, ops)
    assert rc == 1 and X.record(out)["verdict"] == "FAIL"


# ------------------------------------------------------------------------------------------------ post-reveal: the interrupt positive (spec 4.5, C373)
from bench.tests.test_c147_inject_verify import full_run, run_suite, write_attempt          # noqa: E402


def _frozen_ok(doc):
    return fz.positives_problems(doc, arm="n16", commit=X.COMMIT, identity=dict(X.IDENT), frozen_prompt_date=X.DATE,
                                 image_id=doc["image_id"], cancel_path_sha256=fz.CANCEL_PATH_SHA256)


def test_post_reveal_a_positives_record_holds_one_interrupt_run_on_the_pilot_item_and_is_pass_with_it(tmp_path, monkeypatch):
    """post-reveal (c): every record carries ONE `interrupt` run (the pilot item of the first language); the record is PASS
    when it PASSes (stall / loop PASS or PASS_NO_INFLIGHT)."""
    rc, doc, ops = _tg2_positives_with(tmp_path, monkeypatch, {("rust", "stall"): NO_INFLIGHT})
    interrupts = [e for e in doc["injects"] if e["kind"] == "interrupt"]
    assert len(interrupts) == 1 and interrupts[0]["verdict"] == "PASS"
    assert rc == 0 and doc["verdict"] == "PASS" and _frozen_ok(doc) == []
    assert [r for r in ops.runs if r[1] == "interrupt"] == [(interrupts[0]["language"], "interrupt", 1)]


def _tg2_positives_with(tmp_path, monkeypatch, verdicts):
    world = X.HostWorld(tmp_path / "host")
    ops = X.PosOps(tmp_path, world, verdicts=verdicts)
    rc, out = X.positives(tmp_path, monkeypatch, ops)
    return rc, X.record(out), ops


@pytest.mark.parametrize("verdict", ["not_observed:trailing", "not_observed", "FAIL:causal:killed_verified", NO_INFLIGHT])
def test_post_reveal_an_interrupt_that_is_not_the_in_flight_pass_makes_the_record_fail(tmp_path, monkeypatch, verdict):
    """post-reveal (c): the record is PASS only if `interrupt` is PASS (the in-flight proof): an interrupt that found nothing in
    flight (`not_observed:*`, or even `PASS_NO_INFLIGHT`) does not pass, whatever stall / loop did."""
    rc, doc, _ = _tg2_positives_with(tmp_path, monkeypatch, {("rust", "interrupt"): verdict, ("rust", "stall"): NO_INFLIGHT})
    assert rc == 1 and doc["verdict"] == "FAIL"
    assert any("interrupt" in p for p in doc["problems"])


def test_post_reveal_v8_refuses_a_record_without_its_interrupt_positive(tmp_path, monkeypatch):
    """post-reveal (c): a sealed record whose interrupt entry is missing is refused by v8's own check, with the interrupt named."""
    from bench import p426_hooks as ph
    rc, doc, _ = _tg2_positives_with(tmp_path, monkeypatch, {})
    assert rc == 0 and _frozen_ok(doc) == []
    body = {k: v for k, v in doc.items() if k != "sha256"}
    body["injects"] = [e for e in body["injects"] if e["kind"] != "interrupt"]
    problems = _frozen_ok(ph.seal(body))
    assert problems and any("interrupt" in p for p in problems)


def test_post_reveal_v8_refuses_an_interrupt_entry_that_is_not_pass(tmp_path, monkeypatch):
    """post-reveal (c)"""
    from bench import p426_hooks as ph
    rc, doc, _ = _tg2_positives_with(tmp_path, monkeypatch, {})
    body = {k: v for k, v in doc.items() if k != "sha256"}
    body["injects"] = [dict(e, verdict=NO_INFLIGHT) if e["kind"] == "interrupt" else e for e in body["injects"]]
    assert _frozen_ok(ph.seal(body))


def test_post_reveal_the_interrupt_positive_accepts_only_pass():
    """post-reveal (b): the freeze's entry rule."""
    assert fz.inject_accepted(dict(language="rust", kind="interrupt", verdict="PASS", row_sha256="0" * 64))
    assert not fz.inject_accepted(dict(language="rust", kind="interrupt", verdict=NO_INFLIGHT, row_sha256="0" * 64))


def test_post_reveal_an_interrupt_with_a_request_in_flight_is_pass(tmp_path):
    """post-reveal (c): the harness stop lands on a generation in flight; the existing in-flight proof holds."""
    v, code, lines = verdict(tmp_path, "interrupt")
    assert v == "PASS" and code == 0, lines


@pytest.mark.parametrize("what, mutation", [
    ("trailing message not interrupted and nothing in flight", nothing_in_flight()),
    ("worker idle at the kill (in_flight_at_kill 0) though the trailing message is interrupted", nothing_in_flight(trailing="interrupted")),
    ("the cancel is not shown consistent (the request completed between the samples)",
     lambda row, m: row["termination"].update(worker_summary_after=dict(in_flight=0, requests_started=4, requests_completed=4, requests_failed=0))),
    ("the client kill is not verified", lambda row, m: row["termination"].update(killed_verified=False)),
    ("the cancel_wait_s bound is exceeded", lambda row, m: row["termination"].update(cancel_wait_s=301)),
])
def test_post_reveal_an_interrupt_without_the_in_flight_proof_is_not_pass(tmp_path, what, mutation):
    """post-reveal (c): the interrupt's PASS needs the in-flight proof; it never takes PASS_NO_INFLIGHT."""
    v, code, _ = verdict(tmp_path, "interrupt", mutation)
    assert v not in ("PASS", NO_INFLIGHT) and code != 0, what


def test_post_reveal_the_inject_suite_requires_the_interrupt_run(tmp_path):
    """post-reveal (c): stall / loop / alloc alone no longer clear the suite."""
    for kind in ("stall", "loop", "alloc"):
        write_attempt(tmp_path, kind, 1)
    code, lines = run_suite(tmp_path)
    assert code != 0 and any("interrupt" in x for x in lines)
    write_attempt(tmp_path, "interrupt", 1)
    assert run_suite(tmp_path)[0] == 0


def test_post_reveal_the_suite_does_not_clear_on_an_interrupt_that_is_not_pass(tmp_path):
    """post-reveal (c)"""
    full_run(tmp_path, interrupt=nothing_in_flight())
    code, lines = run_suite(tmp_path)
    assert code != 0 and "RESULT PASS" not in lines
