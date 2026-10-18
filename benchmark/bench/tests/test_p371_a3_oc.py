"""P371 phase 2b, plan 4 A3 for opencode: the correlation header in the generated provider config (only when receipts
are required), `request_classes` from the finalized export, `overlay_sha` unchanged by the header, and the REAL pinned
client against the mock provider with a `FakeReceiptSource` that plays the worker FROM THE WIRE (every request the mock
saw becomes a receipt, header / seed / sampling / roles / tools read off the request)."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from bench import arm_adapter as aa
from bench import arm_opencode as ao
from bench import chain_ops
from bench import token_turn_gate as tg
from bench import worker_receipts as wr
from bench.tests.arm_entry import m64_main
from bench.tests.opencode_v2_mock import MockServer
from bench.tests.test_m64_arm_oc_contract import OcHarness, entry_parser
from bench.tests.test_opencode_v2_probe import MODEL, tg1_probe as probe          # noqa: F401  (fixture)
from bench.tests.test_tg1_integration import FROZEN, pinned_binary                 # noqa: F401  (fixture)

HEADER = "X-Bench-Attempt"
WORKER = dict(pid=1234, create_time=100)


def m64_arm(p):
    return ao.OpencodeArm(p, mode="m64", search=ao.OfflineTestSearchService())


def tg1_arm(p):
    return ao.OpencodeArm(p, mode="tg1")


# ---------------------------------------------------------------- the header
def test_opencode_supports_the_attempt_header_and_the_base_contract_does_not():
    assert aa.ArmAdapter.supports_attempt_header is False
    assert ao.OpencodeArm.supports_attempt_header is True


def test_the_overlay_carries_the_header_only_when_an_attempt_is_passed(probe):
    arm = m64_arm(probe)
    ctx = wr.AttemptContext.make("python/one", 2, rerun_index=1)
    plain = arm.seed_overlay(MODEL, 7)
    assert plain == probe._seed_overlay(MODEL, 7)
    headed = arm.seed_overlay(MODEL, 7, attempt=ctx)
    assert headed["providers"]["mlx-local"]["settings"]["headers"] == {HEADER: "python/one#a2.r1"}
    assert headed["providers"]["mlx-local"]["models"] == plain["providers"]["mlx-local"]["models"]
    assert arm.seed_overlay(MODEL, 7, attempt=None) == plain


def test_the_row_overlay_sha_is_the_pure_seed_overlay_with_or_without_the_header(probe, tmp_path):
    arm = m64_arm(probe)
    run = arm.make_run_dir(tmp_path, "r1", arm.selection())
    scratch = tmp_path / "s"
    scratch.mkdir()
    ctx = wr.AttemptContext.make("python/one", 1)
    plain = arm.build_env(run, scratch, arm.seed_overlay(MODEL, 7), receipts=tmp_path / "d.jsonl", frozen_date=FROZEN,
                          attempt=ctx)
    headed = arm.build_env(run, scratch, arm.seed_overlay(MODEL, 7, attempt=ctx), receipts=tmp_path / "d.jsonl",
                           frozen_date=FROZEN, attempt=ctx)
    assert plain["OPENCODE_CONFIG_CONTENT"] != headed["OPENCODE_CONFIG_CONTENT"]
    assert arm.overlay_sha(plain) == arm.overlay_sha(headed) == chain_ops.seed_overlay_sha(MODEL, 7)


def test_the_tg1_env_is_unchanged_by_the_attempt_seam(probe, tmp_path):
    arm = tg1_arm(probe)
    run = arm.make_run_dir(tmp_path, "r1", arm.selection())
    scratch = tmp_path / "s"
    scratch.mkdir()
    overlay = arm.seed_overlay(MODEL, 7)
    got = arm.build_env(run, scratch, overlay, receipts=tmp_path / "r.jsonl", frozen_date=FROZEN,
                        attempt=wr.AttemptContext.make("python/one", 1))
    assert got == probe._opencode_env(run, scratch, overlay, frozen_date=FROZEN, receipts=tmp_path / "r.jsonl")


# ---------------------------------------------------------------- request classes from the finalized export
def assistant(mid="m1", **kw):
    return dict(id=mid, type="assistant", finish="stop", content=[], tokens=dict(
        input=100, output=10, reasoning=0, cache=dict(read=0, write=0)), **kw)


def compaction(status="completed", **kw):
    return dict(type="compaction", id="c1", status=status, reason="auto", tokens=dict(
        input=300, output=40, reasoning=0, cache=dict(read=0, write=0)), **kw)


def classes(arm, *messages):
    return arm.request_classes(None, aa.Transcript(raw="", doc=dict(messages=[dict(type="user"), *messages])))


def test_task_requests_are_the_assistant_messages_in_order(probe):
    assert classes(m64_arm(probe), assistant("m1"), assistant("m2")) == [dict(cls="task"), dict(cls="task")]


def test_a_completed_compaction_is_one_or_two_tool_less_requests_between_the_tasks(probe):
    got = classes(m64_arm(probe), assistant("m1"), compaction(), assistant("m2"))
    assert got == [dict(cls="task"), dict(cls="compaction", repeat=(1, 2)), dict(cls="task")]


def test_a_failed_compaction_is_exactly_two_requests(probe):
    err = dict(type="compaction.failed", message="Compaction summary did not match the required template")
    got = classes(m64_arm(probe), assistant("m1"), compaction("failed", error=err), dict(type="idle", outcome="failed"))
    assert got == [dict(cls="task"), dict(cls="compaction", repeat=(2, 2))]


def test_there_are_no_auxiliary_requests_because_the_title_agent_is_disabled(probe):
    assert all(c["cls"] != "auxiliary" for c in classes(m64_arm(probe), assistant(), compaction(), assistant("m2")))


def test_a_compaction_message_in_a_configuration_without_compaction_is_not_a_known_request_class(probe):
    with pytest.raises(tg.TransportAbort, match="compaction"):
        classes(tg1_arm(probe), assistant(), compaction())


# ---------------------------------------------------------------- the real client, worker receipts played from the wire
def is_summary(body):
    last = (body.get("messages") or [{}])[-1].get("content")
    return isinstance(last, str) and last.startswith("You MUST summarize the conversation above")


class MockWorker(wr.FakeReceiptSource):
    """Plays the worker from what the mock provider received: one receipt per chat request, in arrival order."""

    def __init__(self, mock, script, *, mutate=None):
        super().__init__(dict(WORKER))
        self.mock, self.script, self.mutate = mock, script, mutate
        self.requests_at_start = 0

    def start(self, ctx):
        self.requests_at_start = len(self.mock.chats)
        return super().start(ctx)

    def fence(self, ctx):
        for i, chat in enumerate(self.mock.chats[self.requests_at_start:], self.requests_at_start + 1):
            body, headers = chat["body"], {k.lower(): v for k, v in chat["headers"].items()}
            kind = self.script.get(i)
            usage = kind["usage"] if isinstance(kind, dict) and "usage" in kind else dict(prompt_tokens=100,
                                                                                         completion_tokens=10)
            self.admit("compaction" if is_summary(body) else "task", header=headers.get(HEADER.lower()),
                       tools=bool(body.get("tools")), seed=body["seed"], thinking_budget=body["thinking_budget"],
                       max_tokens=body["max_tokens"], sampling={k: body[k] for k in wr.SAMPLING_FIELDS},
                       roles=[m["role"] for m in body["messages"]], prompt_tokens=usage["prompt_tokens"],
                       completion_tokens=usage["completion_tokens"])
        if self.mutate:
            self.mutate(self)
        return super().fence(ctx)


def run_oc(probe, pinned_binary, monkeypatch, tmp_path, script, *, window=None, mutate=None, receipts="required",
           extra=()):
    (Path(os.environ["STACK_WORKDIR"]) / "m62/inject").mkdir(parents=True, exist_ok=True)
    h = OcHarness(probe, pinned_binary, monkeypatch, tmp_path)
    with MockServer(script) as mock:
        f, sub = h._setup(mock, window)
        out = sub / "rows.jsonl"
        argv = h._argv(sub, out, list(extra))
        monkeypatch.setattr(sys, "argv", argv)
        a = entry_parser().parse_args(argv[1:])
        worker = MockWorker(mock, script, mutate=mutate)
        adapter = ao.OpencodeArm(probe, mode="m64", search=ao.OfflineTestSearchService())
        abort = None
        try:
            m64_main(probe, adapter, a, receipts_policy=receipts, receipt_source=worker)
        except SystemExit as exc:
            abort = exc if exc.code not in (0, None) else None
        row = json.loads(out.read_text().splitlines()[0]) if out.exists() else None
        manifest = json.loads(out.with_suffix(".manifest.json").read_text())
        return dict(row=row, abort=abort, mock=mock, worker=worker, manifest=manifest, h=h, sub=sub)


def test_the_real_client_runs_with_required_receipts_and_every_request_carries_the_header(
        probe, pinned_binary, monkeypatch, tmp_path):
    got = run_oc(probe, pinned_binary, monkeypatch, tmp_path, {})
    assert got["abort"] is None, got["abort"]
    row, mock = got["row"], got["mock"]
    assert row["token_accounting"] == "receipts" and row["passed"] is True and row["nonconv_kind"] is None
    assert len(mock.chats) == 2
    for chat in mock.chats:
        assert {k.lower(): v for k, v in chat["headers"].items()}[HEADER.lower()] == "python/one#a1.r0"
    path = Path(row["receipts"]["path"].replace("$STACK_WORKDIR", os.environ["STACK_WORKDIR"]))
    assert row["receipts"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert row["task_tokens"]["receipts"]["requests"] == 2 and row["task_tokens"]["receipts"]["completion_tokens"] == 20


def test_the_header_and_the_row_overlay_hash_are_exactly_what_a_receipts_free_run_records(
        probe, pinned_binary, monkeypatch, tmp_path):
    got = run_oc(probe, pinned_binary, monkeypatch, tmp_path, {})
    assert got["row"]["overlay_sha256"] == chain_ops.seed_overlay_sha(MODEL, got["row"]["sampler_seed"])


def test_an_absent_policy_sends_no_header_and_writes_no_receipt_file(probe, pinned_binary, monkeypatch, tmp_path):
    got = run_oc(probe, pinned_binary, monkeypatch, tmp_path, {}, receipts="absent")
    assert got["abort"] is None and got["row"]["token_accounting"] == "client" and "receipts" not in got["row"]
    assert all(HEADER.lower() not in {k.lower() for k in c["headers"]} for c in got["mock"].chats)
    assert got["worker"].calls == []


def test_a_compaction_run_joins_its_summary_request_as_a_tool_less_compaction_class(
        probe, pinned_binary, monkeypatch, tmp_path):
    got = run_oc(probe, pinned_binary, monkeypatch, tmp_path, OcHarness.compaction_script(None),
                 window=OcHarness.reduced_window)
    assert got["abort"] is None, got["abort"]
    row = got["row"]
    receipts = row["task_tokens"]["receipts"]
    assert receipts["by_class"]["compaction"]["requests"] == 1 and receipts["requests"] == 4
    assert row["compaction"]["accounting"] == "receipts" and row["compaction"]["count"] == 1
    assert row["compaction"]["completion_tokens"] == 10 and row["compaction"]["receipts"] == 1
    summary = [c for c in got["mock"].chats if is_summary(c["body"])]
    assert len(summary) == 1 and {k.lower(): v for k, v in summary[0]["headers"].items()}[HEADER.lower()]
    assert row["task_tokens"]["compaction_completion_tokens"] == 10


def test_a_receipt_with_the_wrong_seed_aborts_the_real_run(probe, pinned_binary, monkeypatch, tmp_path):
    got = run_oc(probe, pinned_binary, monkeypatch, tmp_path, {},
                 mutate=lambda s: s._receipts[0].update(seed=1))
    assert got["abort"] is not None and "seed" in str(got["abort"]) and got["row"] is None


def test_a_receipt_naming_another_worker_is_a_worker_crash_for_the_real_run(
        probe, pinned_binary, monkeypatch, tmp_path):
    got = run_oc(probe, pinned_binary, monkeypatch, tmp_path, {},
                 mutate=lambda s: s._receipts[1].update(worker=dict(pid=9, create_time=1.0)))
    assert got["abort"] is not None and got["manifest"]["transport_abort"]["cause"] == "worker_crash"
