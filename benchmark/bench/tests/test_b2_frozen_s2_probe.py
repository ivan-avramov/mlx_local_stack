"""P426 B2 frozen tests, s2 probe (spec §2 probe-code edits; §13 real-adapter tests).

Classes: [FIX] reproduces a failure the spec fixes; [INV] preserves an invariant; [NEW] exercises new behaviour.
The real `run_tg1_probe` runs in-process over the existing mocked tg1 world (`b2_frozen_support.probe_fixture`)."""
from __future__ import annotations

import dataclasses
import json

import pytest

from bench import arm_opencode as ao
from bench import tg1_runner
from bench.tests import b2_frozen_support as S


def run_rc(f, extra):
    try:
        return f["run"]("one", extra=["--expect-items", "python/one", *extra])
    except SystemExit as e:
        return e.code


# ------------------------------------------------------------------------------------------------ the evidence policy
def test_new_tg1_p426_evidence_is_tg1_evidence_with_the_item_barrier_on():
    assert tg1_runner.TG1_P426_EVIDENCE == dataclasses.replace(tg1_runner.TG1_EVIDENCE, item_barrier="on")


def test_inv_the_tg1_evidence_default_is_unchanged():
    assert tg1_runner.TG1_EVIDENCE.as_dict() == S.evidence_policy("off")


def test_new_evidence_p426_selects_the_p426_policy_and_the_probe_waits_at_the_item_barrier(tmp_path, monkeypatch):
    f = S.probe_fixture(monkeypatch, tmp_path)
    with S.barrier_answerer(f["out"].parent):
        rc = run_rc(f, ["--evidence", "p426"])
    assert rc == 0
    man = S.manifest_of(f["out"])
    assert man["runtime"]["evidence_policy"] == tg1_runner.TG1_P426_EVIDENCE.as_dict()
    names = S.barrier_files(f["out"].parent)
    assert [n.split(".", 1)[1] for n in names] == ["item0.continue", "item0.done", "item0.go", "item0.ready"]


def test_inv_without_the_flag_the_probe_keeps_the_tg1_policy_and_no_barrier(tmp_path, monkeypatch):
    f = S.probe_fixture(monkeypatch, tmp_path)
    assert run_rc(f, []) == 0
    assert S.manifest_of(f["out"])["runtime"]["evidence_policy"] == tg1_runner.TG1_EVIDENCE.as_dict()
    assert S.barrier_files(f["out"].parent) == []


def test_inv_the_evidence_policy_is_not_part_of_the_probe_identity(tmp_path, monkeypatch):
    """§2: `probe_code_sha256` moves once (the code edit), equal across arms; the selected policy never enters the generation
    identity (run_config: EvidencePolicy is verified by the chain, NOT in the generation identity)."""
    f = S.probe_fixture(monkeypatch, tmp_path)
    assert run_rc(f, []) == 0
    base = S.manifest_of(f["out"])["runtime"]
    f["out"].unlink()
    f["out"].with_suffix(".manifest.json").unlink()
    with S.barrier_answerer(f["out"].parent):
        assert run_rc(f, ["--evidence", "p426"]) == 0
    p426 = S.manifest_of(f["out"])["runtime"]
    for k in ("probe_code_sha256", "scaffold_policy_sha256", "generation_identity_sha256"):
        assert p426[k] == base[k], k


# ------------------------------------------------------------------------------------------------ the cause stamp
@pytest.mark.parametrize("cause", ao.TRANSPORT_CAUSES)
def test_new_the_p426_opencode_arm_returns_the_transport_cause(cause):
    arm = ao.OpencodeArm(mode="tg1", p426=True)
    assert arm.transport_cause(ao.TransportFailure(cause, "x")) == cause
    assert arm.transport_cause(RuntimeError("not transport")) is None


def test_inv_the_tg1_and_m64_arms_keep_their_cause_rules():
    exc = ao.TransportFailure("dropped_stream", "x")
    assert ao.OpencodeArm(mode="tg1").transport_cause(exc) is None
    assert ao.OpencodeArm(mode="m64").transport_cause(exc) == "dropped_stream"


@pytest.mark.parametrize("kind,cause", [("drop", "dropped_stream"), ("refuse", "connection")])
def test_new_a_p426_client_abort_manifest_carries_cause_gate_usage_session_and_termination(tmp_path, monkeypatch, kind, cause):
    """§2 [r3]: in P426 mode an abort manifest carries the gate report WITH the full `request_usage` list, the session id,
    whether a request was in flight and the termination evidence (real adapter, through manifest creation)."""
    f = S.probe_fixture(monkeypatch, tmp_path)
    S.set_client_error(f, tmp_path, kind)                        # m1 completed, m2 in flight, then the client error event
    with S.barrier_answerer(f["out"].parent):
        rc = run_rc(f, ["--evidence", "p426"])
    assert rc not in (0, None)
    assert f["out"].with_suffix(".manifest.json").exists(), f"no manifest: the probe refused before item one (rc {rc})"
    man = S.manifest_of(f["out"])
    stamp = man["transport_abort"]
    assert stamp["cause"] == cause
    # §16.1 (ruled): transport_abort = {cause, error, evidence, termination, gate: {…, request_usage}, session_id,
    #                                   in_flight: {in_flight, message_id, requests_started}}
    assert {"cause", "error", "evidence", "termination", "gate", "session_id", "in_flight"} <= set(stamp)
    assert stamp["session_id"] == S.ERROR_SESSION               # the client session of the aborted item (fixture events)
    usage = stamp["gate"].get("request_usage")
    assert isinstance(usage, list) and [u[0] for u in usage] == ["m1"]
    fl = stamp["in_flight"]
    assert fl == {"in_flight": True, "message_id": "m2", "requests_started": 2}


def test_inv_a_tg1_client_abort_manifest_keeps_its_shape(tmp_path, monkeypatch):
    f = S.probe_fixture(monkeypatch, tmp_path)
    S.set_client_error(f, tmp_path, "drop")
    assert run_rc(f, []) not in (0, None)
    stamp = S.manifest_of(f["out"])["transport_abort"]
    assert "cause" not in stamp and "gate" not in stamp
