"""B2 slice s2 (spec docs/specs/p426-b2-tg1-wave2.md v3.1, section 2 "Probe-code edits"): the tg1 probe's P426 evidence policy
(`TG1_P426_EVIDENCE`, item barrier on), `--evidence p426`, the chain passing it only in P426 mode, the P426 transport-cause stamp and the
P426 abort manifest (full `request_usage`, `session_id`, the in-flight message id, the termination evidence). Every default and every
non-P426 behaviour is unchanged."""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

from bench import arm_opencode as ao
from bench import chain_core as core
from bench import tg1_runner
from bench.token_turn_gate import TransportAbort
from bench.tests.test_b2_s1_cli import run_p426, invocations, pinned_off_registry
from bench.tests.test_c147_chain_runner import R, arg, chain_json, env, run, PICK1       # noqa: F401  (fixture: env)
from bench.tests.test_opencode_v2_probe import tg1_probe as probe                          # noqa: F401  (fixture)
from bench.tests.p371_world import world                                                   # noqa: F401  (fixture)
from bench.tests.test_tg1_integration import tg_fixture
from bench.tests.test_token_turn_gate import event, usage

OLD_TG1_EVIDENCE = dict(namespace="opencode_transcripts", web_evidence=True, final_tree=True, worker_receipts="absent",
                        item_barrier="off")


# ---------------------------------------------------------------- the policy and the flag
def test_the_default_tg1_evidence_policy_is_unchanged_and_the_p426_one_differs_only_in_the_barrier():
    assert tg1_runner.TG1_EVIDENCE.as_dict() == OLD_TG1_EVIDENCE
    assert tg1_runner.TG1_P426_EVIDENCE.as_dict() == dict(OLD_TG1_EVIDENCE, item_barrier="on")


def test_the_probe_parser_takes_evidence_p426_and_defaults_to_nothing(probe):
    base = ["--model", "m", "--items", "a", "--seed-base", "1"]
    assert probe._parser().parse_args(base).evidence is None
    assert probe._parser().parse_args(base + ["--evidence", "p426"]).evidence == "p426"
    with pytest.raises(SystemExit):
        probe._parser().parse_args(base + ["--evidence", "other"])


def test_evidence_selects_the_policy_and_the_adapter_mode_in_tg1_main(probe, monkeypatch):
    seen = {}
    monkeypatch.setattr(tg1_runner.core, "main", lambda p, adapter, a, **kw: seen.update(adapter=adapter, **kw) or 0)
    tg1_runner.main(probe, type("A", (), {"evidence": None, "universe": None})())
    assert seen["evidence"] is tg1_runner.TG1_EVIDENCE and seen["adapter"].p426 is False
    tg1_runner.main(probe, type("A", (), {"evidence": "p426", "universe": None})())
    assert seen["evidence"] is tg1_runner.TG1_P426_EVIDENCE and seen["adapter"].p426 is True
    assert seen["adapter"].mode == "tg1" and not seen["adapter"].m64


def answer_barrier(stem, items, stop):
    """The chain's side of the item barrier, for a probe run directly: `.go` after `.ready`, `.continue` after `.done`."""
    def run_():
        for k in range(items):
            for kind, answer in (("ready", "go"), ("done", "continue")):
                end = time.monotonic() + 30
                while not Path(f"{stem}.item{k}.{kind}").exists() and not stop.is_set():
                    assert time.monotonic() < end, f"{kind} {k} never appeared"
                    time.sleep(0.01)
                Path(f"{stem}.item{k}.{answer}").write_text("")
    t = threading.Thread(target=run_, daemon=True)
    t.start()
    return t


def manifest_of(f):
    return json.loads(f["out"].with_suffix(".manifest.json").read_text())


def test_a_probe_run_with_evidence_p426_records_the_policy_and_keeps_the_generation_identity(probe, monkeypatch, tmp_path):
    runtimes = []
    for name, flag in (("plain", False), ("control", False), ("p426", True)):
        sub = tmp_path / name
        sub.mkdir()
        f = tg_fixture(probe, monkeypatch, sub)
        stop = threading.Event()
        thread = answer_barrier(f["out"].with_suffix(""), 1, stop) if flag else None
        try:
            assert f["run"]("one", extra=["--evidence", "p426"] if flag else []) == 0
        finally:
            stop.set()
        if thread:
            thread.join(10)
        runtimes.append(manifest_of(f)["runtime"])
        if flag:
            assert Path(f"{f['out'].with_suffix('')}.item0.done").exists()           # the barrier is really on
        else:
            assert not list(sub.glob("*.item0.*"))
    plain, control, p426 = runtimes
    assert plain["evidence_policy"] == control["evidence_policy"] == OLD_TG1_EVIDENCE
    assert p426["evidence_policy"] == tg1_runner.TG1_P426_EVIDENCE.as_dict()
    # the fixture's per-directory fake binary / carrier make some fields differ between ANY two runs (the control); the flag
    # changes nothing beyond that and the evidence policy, and the composite is the unchanged P311 recipe over the same fields
    def changed(a, b):
        return {k for k in set(a) | set(b) if a.get(k) != b.get(k)}
    assert changed(plain, p426) - {"evidence_policy"} <= changed(plain, control)
    assert p426["generation_identity_sha256"] == tg1_runner.generation_identity_sha256(p426)
    assert changed(ao.generation_fields(plain), ao.generation_fields(p426)) <= changed(ao.generation_fields(plain),
                                                                                        ao.generation_fields(control))
    assert p426["config_id"] == plain["config_id"] == "tg1"


# ---------------------------------------------------------------- the chain passes the flag only in P426 mode
def test_build_cmd_appends_evidence_only_when_given():
    leg = dict(model=PICK1, lang="python", seed_base=1001, out="/o/x.jsonl")
    step = dict(kind="pilot", names=["a"], limit=5)
    plain = R.build_cmd("/py", "/probe.py", leg, step, "/r.json", "/c", "/k")
    assert "--evidence" not in plain and plain == core.build_cmd("/py", "/probe.py", leg, step, "/r.json", "/c", "/k",
                                                                 scaffold=R.SCAFFOLD)
    cmd = R.build_cmd("/py", "/probe.py", leg, step, "/r.json", "/c", "/k", evidence="p426")
    assert cmd == plain + ["--evidence", "p426"]
    assert core.build_cmd("/py", "/probe.py", leg, step, "/r.json", "/c", "/k", scaffold=R.SCAFFOLD,
                          evidence="p426") == cmd


def test_the_legacy_chain_never_passes_evidence(env):
    assert run(env, ["chain", "s1", "--probe-code-sha", "9" * 64, "--models", PICK1], registry=pinned_off_registry()) == 0
    calls = invocations(env)
    assert calls and all("--evidence" not in i["argv"] for i in calls)


# ---------------------------------------------------------------- the transport cause
def test_transport_cause_is_stamped_for_m64_and_p426_and_not_for_plain_tg1(probe):
    exc = ao.TransportFailure("dropped_stream", "x")
    assert ao.OpencodeArm(probe, mode="m64").transport_cause(exc) == "dropped_stream"
    assert ao.OpencodeArm(probe, mode="tg1", p426=True).transport_cause(exc) == "dropped_stream"
    assert ao.OpencodeArm(probe, mode="tg1").transport_cause(exc) is None
    assert ao.OpencodeArm(probe, mode="tg1", p426=True).transport_cause(TransportAbort("y")) is None
    assert ao.OpencodeArm(probe, mode="tg1", p426=True).report_gate_on_abort is True
    assert ao.OpencodeArm(probe, mode="tg1").report_gate_on_abort is False
    assert ao.OpencodeArm(probe, mode="m64").report_gate_on_abort is True


def test_p426_is_a_tg1_mode_only(probe):
    from bench import arm_adapter as aa
    with pytest.raises(aa.ArmContractError, match="p426"):
        ao.OpencodeArm(probe, mode="m64", p426=True)


def test_the_generation_composite_does_not_depend_on_the_evidence_mode(probe):
    ident = {k: f"v-{k}" for k in ao.GENERATION_FIELDS}
    plain, p426 = ao.OpencodeArm(probe, mode="tg1"), ao.OpencodeArm(probe, mode="tg1", p426=True)
    assert plain.generation_identity_sha256(ident) == p426.generation_identity_sha256(ident) == \
        tg1_runner.generation_identity_sha256(ident)
    assert plain.label == p426.label == ao.TG1_LABEL and plain.selection()["bytes"] == p426.selection()["bytes"]


# ---------------------------------------------------------------- the abort manifest, real adapter
def failing_run(probe, monkeypatch, tmp_path, *, p426, events, error, rc="1"):
    """A tg1 probe run (real `OpencodeArm`, fake client) whose client stream ends in a transport error event."""
    f = tg_fixture(probe, monkeypatch, tmp_path)
    (tmp_path / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events + [
        dict(type="error", sessionID="s1", error=error)]))
    (tmp_path / "rc").write_text(rc)
    stop = threading.Event()
    thread = answer_barrier(f["out"].with_suffix(""), 1, stop) if p426 else None
    try:
        with pytest.raises(BaseException) as exc:
            f["run"]("one", extra=["--evidence", "p426"] if p426 else [])
    finally:
        stop.set()
    if thread:
        thread.join(10)
    return f, manifest_of(f)["transport_abort"], exc.value


BOUNDARY = [event("step_start"), event("step_finish", tokens=usage(10, 100))]
IN_FLIGHT = BOUNDARY + [event("step_start", "m2")]
CAUSES = [("connection", dict(type="provider.transport", message="reset")),
          ("dropped_stream", dict(type="provider.invalid-output", message="bad stream")),
          ("timeout", dict(type="provider.timeout", message="slow"))]


@pytest.mark.parametrize("cause,error", CAUSES)
def test_a_p426_tg1_abort_stamps_the_transport_cause(probe, monkeypatch, tmp_path, cause, error):
    f, stamp, _ = failing_run(probe, monkeypatch, tmp_path, p426=True, events=IN_FLIGHT, error=error)
    assert stamp["cause"] == cause


@pytest.mark.parametrize("cause,error", CAUSES[:1])
def test_a_plain_tg1_abort_stamps_no_cause_and_no_gate(probe, monkeypatch, tmp_path, cause, error):
    f, stamp, _ = failing_run(probe, monkeypatch, tmp_path, p426=False, events=IN_FLIGHT, error=error)
    assert "cause" not in stamp and "gate" not in stamp and "in_flight" not in stamp and "session_id" not in stamp


def test_a_p426_abort_at_a_request_boundary_carries_the_request_evidence(probe, monkeypatch, tmp_path):
    f, stamp, _ = failing_run(probe, monkeypatch, tmp_path, p426=True, events=BOUNDARY, error=CAUSES[0][1])
    assert stamp["gate"]["requests_completed"] == 1 == len(stamp["gate"]["request_usage"])
    assert stamp["gate"]["request_usage"][0][1:] == [10, 100, 81920]
    assert stamp["session_id"] == "s1"
    assert stamp["in_flight"] == dict(in_flight=False, message_id=None, requests_started=1)
    assert isinstance(stamp["termination"], dict) and "reason" in stamp["termination"] and stamp["cleanup_status"]
    assert stamp["evidence"]["id"] == "python/one"


def test_a_p426_abort_with_a_request_in_flight_names_the_message(probe, monkeypatch, tmp_path):
    f, stamp, _ = failing_run(probe, monkeypatch, tmp_path, p426=True, events=IN_FLIGHT, error=CAUSES[0][1])
    assert stamp["gate"]["requests_completed"] == 1 and len(stamp["gate"]["request_usage"]) == 1
    assert stamp["gate"]["request_usage"][0][1:] == [10, 100, 81920]
    assert stamp["session_id"] == "s1"
    assert stamp["in_flight"] == dict(in_flight=True, message_id="m2", requests_started=2)
    assert isinstance(stamp["termination"], dict) and "in_flight_at_kill" in stamp["termination"] and stamp["cleanup_status"]
    assert stamp["evidence"]["id"] == "python/one" and stamp["error"]


def test_the_request_evidence_of_one_item_never_reaches_the_next_items_abort(probe, monkeypatch, tmp_path):
    """A stale per-item context entry must not label a later abort that fell before its request evidence existed."""
    from bench import arm_runner
    ctx_probe = {}
    f = tg_fixture(probe, monkeypatch, tmp_path)
    real = arm_runner.run_item

    def run_item(p, adapter, **kw):
        ctx_probe["ctx"] = kw["ctx"]
        if len(ctx_probe.setdefault("n", [])) == 1:
            raise TransportAbort("between")
        ctx_probe["n"].append(1)
        return real(p, adapter, **kw)

    monkeypatch.setattr(arm_runner, "run_item", run_item)
    stop = threading.Event()
    answer_barrier(f["out"].with_suffix(""), 2, stop)
    try:
        with pytest.raises(SystemExit):
            f["run"]("one,two", extra=["--evidence", "p426"])
    finally:
        stop.set()
    stamp = manifest_of(f)["transport_abort"]
    assert stamp["gate"] is None and stamp["session_id"] is None and stamp["in_flight"] is None


def test_an_m64_style_abort_stamp_keeps_the_gate_report_without_the_p426_additions(world):
    from bench.tests.arm_neutral import NeutralArm
    from bench.tests.test_p371_a3_core import SEED, abort_of, source

    class Reporting(NeutralArm):
        report_gate_on_abort = True

    _, stamp = abort_of(world, source(world, [dict(cls="task", seed=SEED)]), adapter=Reporting(world.host))
    assert "request_usage" not in stamp["gate"] and not {"session_id", "in_flight"} & set(stamp)

    class P426(Reporting):
        report_requests_on_abort = True

    _, stamp = abort_of(world, source(world, [dict(cls="task", seed=SEED)]), adapter=P426(world.host))
    assert "request_usage" in stamp["gate"] and {"session_id", "in_flight"} <= set(stamp)
