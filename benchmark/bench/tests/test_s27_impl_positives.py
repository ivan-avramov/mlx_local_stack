"""S27 §4.3 / §4.5: order-tolerant positives (`PASS_NO_INFLIGHT` for stall / loop, never for the interrupt), the deterministic
interrupt positive, and every consumer of the verdict strings (inject_verify, the v8 rule, the drivers)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from bench import p426_freeze as fz
from bench.tests import test_c147_inject_verify as T

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from m62 import inject_verify as iv                           # noqa: E402

NO_INFLIGHT = dict(in_flight_at_kill=0,
                   worker_summary_before=dict(in_flight=0, requests_started=4, requests_completed=4, requests_failed=0),
                   worker_summary_after=dict(in_flight=0, requests_started=4, requests_completed=4, requests_failed=0))


def no_inflight(r, m):
    r["termination"].update(json.loads(json.dumps(NO_INFLIGHT)))
    r["reconciliation"]["trailing"] = "none"


def test_a_stall_with_nothing_in_flight_is_pass_no_inflight(tmp_path):
    v, code, lines = T.verdict(tmp_path, "stall", no_inflight)
    assert v == iv.PASS_NO_INFLIGHT and code == 0 and lines[-1] == "RESULT stall PASS_NO_INFLIGHT"


def test_a_loop_with_nothing_in_flight_needs_its_descendant_kill(tmp_path):
    v, _, _ = T.verdict(tmp_path, "loop", no_inflight)
    assert v == iv.PASS_NO_INFLIGHT

    def no_descendant(r, m):
        no_inflight(r, m)
        r["termination"]["killed"] = [k for k in r["termination"]["killed"] if k["role"] != "model"]
    v2, code, _ = T.verdict(tmp_path / "b" if (tmp_path / "b").mkdir() is None else tmp_path, "loop", no_descendant)
    assert v2 == "not_observed:descendant" and code == 4


@pytest.mark.parametrize("edit", [
    lambda r: r["termination"]["worker_summary_after"].update(requests_started=5),     # a request started meanwhile
    lambda r: r["termination"]["worker_summary_after"].update(in_flight=1),
    lambda r: r["reconciliation"].update(trailing="interrupted"),
])
def test_pass_no_inflight_needs_every_condition(tmp_path, edit):
    def mutate(r, m):
        no_inflight(r, m)
        edit(r)
    v, _, _ = T.verdict(tmp_path, "stall", mutate)
    assert v != iv.PASS_NO_INFLIGHT


def test_the_interrupt_positive_passes_only_with_the_in_flight_proof(tmp_path):
    v, code, lines = T.verdict(tmp_path, "interrupt")
    assert v == "PASS" and code == 0 and "cancellation_consistent" in "\n".join(lines)
    v2, _, _ = T.verdict(tmp_path / "n" if (tmp_path / "n").mkdir() is None else tmp_path, "interrupt", no_inflight)
    assert v2 != "PASS" and v2 != iv.PASS_NO_INFLIGHT
    v3, _, _ = T.verdict(tmp_path / "c" if (tmp_path / "c").mkdir() is None else tmp_path, "interrupt",
                         lambda r, m: r["termination"]["worker_summary_after"].update(requests_completed=4))
    assert v3 == "not_observed:cancellation"                    # completed rose: natural completion, not a cancellation


def test_the_suite_passes_only_with_the_interrupt_pass(tmp_path):
    T.full_run(tmp_path, stall=no_inflight, loop=no_inflight)
    code, lines = T.run_suite(tmp_path)
    assert code == 0 and lines[-1] == "RESULT PASS", lines
    T.write_attempt(tmp_path, "interrupt", 2, no_inflight)
    code, lines = T.run_suite(tmp_path)
    assert code != 0 and any("interrupt" in x for x in lines if x.startswith("suite:"))


# -------------------------------------------------------------------------------- the v8 rule (consumers)
def entry(kind, verdict, lang="rust"):
    return dict(language=lang, kind=kind, verdict=verdict)


def test_pass_no_inflight_is_accepted_for_stall_and_loop_only():
    assert fz.inject_accepted(entry("stall", "PASS_NO_INFLIGHT")) and fz.inject_accepted(entry("loop", "PASS_NO_INFLIGHT"))
    assert not fz.inject_accepted(entry("alloc", "PASS_NO_INFLIGHT"))
    assert not fz.inject_accepted(entry("interrupt", "PASS_NO_INFLIGHT"))
    assert fz.inject_accepted(entry("interrupt", "PASS"))


def record(**over):
    from bench import schedules, tg2_grade
    injects = [entry(k, "PASS", lang) for lang in fz.TG2_LANGS for k in fz.POSITIVE_KINDS]
    injects[0]["verdict"] = "PASS_NO_INFLIGHT"                   # a stall with nothing in flight
    # X12: the interrupt is the cancellation proof: v8 requires its inject_verify PASS, probe rc 0 and row sha256
    injects.insert(0, dict(entry("interrupt", "PASS", fz.TG2_LANGS[0]), verify_verdict="PASS", probe_rc=0, row_sha256="b" * 64))
    grades = [dict(language=lang, variant=v, passed=v == "reference") for lang in fz.TG2_LANGS for v in fz.POSITIVE_VARIANTS]
    doc = dict(kind=fz.KIND_POSITIVES, verdict="PASS", problems=[], arm="n16", n16_commit="c" * 40,
               scaffold="opencode-v2-web-tg2", draw_sha256=schedules.TG2_DRAW_SHA256,
               universe_sha256=schedules.TG2_UNIVERSE_SHA256, image_id="img", frozen_prompt_date="Fri Nov 20 2026",
               grades=grades, injects=injects, **{k: "a" * 64 for k in fz.IDENTITY_KEYS})
    doc.update(over)
    from bench import p426_hooks as ph
    return ph.seal(doc), tg2_grade


def problems_of(doc):
    return fz.positives_problems(doc, arm="n16", commit="c" * 40, identity={k: "a" * 64 for k in fz.IDENTITY_KEYS},
                                 frozen_prompt_date="Fri Nov 20 2026", image_id="img")


def test_a_record_with_pass_no_inflight_freezes_in_v8():
    doc, _ = record()
    assert problems_of(doc) == []


def test_a_record_freezes_only_with_one_interrupt_pass():
    doc, _ = record()
    no_interrupt = [e for e in doc["injects"] if e["kind"] != "interrupt"]
    bad, _ = record(injects=no_interrupt)
    assert any("interrupt" in p for p in problems_of(bad))
    failed = [dict(e, verdict="not_observed:trailing") if e["kind"] == "interrupt" else e for e in doc["injects"]]
    bad2, _ = record(injects=failed)
    assert any("interrupt" in p for p in problems_of(bad2))


def test_the_proof_each_record_used_is_stated():
    assert fz.proof_of(entry("interrupt", "PASS")) == "in_flight"
    assert fz.proof_of(entry("stall", "PASS_NO_INFLIGHT")) == "detection_no_inflight"
    assert fz.proof_of(entry("loop", "PASS")) == "detection_in_flight"


def test_the_tg1_driver_runs_the_interrupt_on_the_stall_item_and_reads_the_new_verdict():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "chains" / "c147"))
    import run_inject as RI
    assert RI.KINDS[-1] == "interrupt" and RI.verdict_for("stall.attempt1: PASS_NO_INFLIGHT", "stall.attempt1") == "PASS"


def test_the_c366_transfer_is_not_used_on_the_new_identity():
    """§4.3: the stop / cancel path changed, so its digest is no longer the reference commit's (the transfer refuses)."""
    here = Path(__file__).resolve().parents[3]
    assert fz.worktree_cancel_path_sha256(here) != fz.CANCEL_PATH_SHA256
