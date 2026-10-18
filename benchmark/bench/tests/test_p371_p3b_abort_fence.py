"""P371 phase 3b part 4 (the 2b leftover, P378 (6)): with worker receipts REQUIRED the fence is also taken after the client
is gone on every abort / cancel / transport path (best effort, never masking the original error), and its token totals are
reported in the abort stamp (`transport_abort.receipts`) so the chain counts a failed attempt's tokens."""
from __future__ import annotations

import threading
import time

import pytest

from bench import token_turn_gate as tg
from bench import worker_receipts as wr
from bench.tests.arm_neutral import NeutralArm
from bench.tests.p371_world import evidence, manifest, rows, run_core, world      # noqa: F401  (fixture)
from bench.tests.test_p371_a3_core import Played, REQUIRED, SEED, go, source


class IngestBoom(NeutralArm):
    """The client's event stream breaks mid-item: the abort happens BEFORE the normal fence point."""

    def new_stream(self, gate, on_complete):
        stream = super().new_stream(gate, on_complete)

        def feed(data):
            raise tg.TransportAbort("ingest boom")
        stream.feed = feed
        return stream


class Sleeper(NeutralArm):
    def command(self, binary, model, prompt):
        return [binary, "-c", "sleep 30"]


def abort(world, src, adapter=None, **kw):
    with pytest.raises(SystemExit, match="REFUSED") as exc:
        go(world, src, adapter=adapter or IngestBoom(world.host), **kw)
    assert rows(world) == []
    return str(exc.value), manifest(world)["transport_abort"]


def test_an_abort_before_the_normal_fence_still_takes_the_fence_and_reports_the_tokens(world):
    admits = [dict(cls="task", seed=SEED, completion_tokens=700), dict(cls="compaction", seed=SEED, completion_tokens=50),
              dict(cls="auxiliary", seed=SEED, completion_tokens=3, tools=False)]
    src = source(world, admits)
    msg, stamp = abort(world, src)
    assert "ingest boom" in msg and [c[0] for c in src.calls].count("fence") == 1 and src.calls[-1][0] == "fence"
    rec = stamp["receipts"]
    assert rec["requests"] == 3 and rec["completion_tokens"] == 753 and rec["fence_taken"] is True
    assert list((world.tmp / "neutral_evidence").rglob("*.receipts.json")), "the raw fenced set is evidence"


def test_a_failing_fence_on_the_abort_path_never_masks_the_original_error(world):
    class Down(Played):
        def fence(self, ctx):
            raise wr.ReceiptTransportError("worker receipt endpoint /bench/attempt/fence failed: URLError")

    msg, stamp = abort(world, Down(dict(pid=1234, create_time=100)))
    assert "ingest boom" in msg and "fence failed" not in msg
    assert stamp["receipts"]["fence_taken"] is False and "fence failed" in stamp["receipts"]["fence_error"]


def test_a_refused_start_mark_means_no_fence(world):
    class NoStart(Played):
        def start(self, ctx):
            raise wr.ReceiptTransportError("start failed")

    src = NoStart(dict(pid=1234, create_time=100))
    msg, stamp = abort(world, src, adapter=NeutralArm(world.host))
    assert "start failed" in msg and [c[0] for c in src.calls] == [] and "receipts" not in stamp


def test_a_join_abort_after_the_normal_fence_does_not_fence_twice_and_still_reports_tokens(world):
    src = source(world, [dict(cls="task", seed=SEED, completion_tokens=11)])          # a missing receipt aborts the join
    msg, stamp = abort(world, src, adapter=NeutralArm(world.host))
    assert "only 1 receipts" in msg and [c[0] for c in src.calls].count("fence") == 1
    assert stamp["receipts"]["completion_tokens"] == 11 and stamp["receipts"]["fence_taken"] is True


def test_a_replaced_worker_still_reports_what_the_fence_listed_and_keeps_the_worker_crash_cause(world):
    other = dict(pid=999, create_time=5.0)
    src = source(world, [dict(cls="task", seed=SEED, completion_tokens=40)] * 2)
    src.foreign_worker = {2: other}
    msg, stamp = abort(world, src, adapter=NeutralArm(world.host))
    assert stamp["cause"] == "worker_crash" and stamp["receipts"]["completion_tokens"] == 80
    assert stamp["receipts"]["worker_ok"] is False


def test_a_cooperative_cancel_reports_the_receipt_tokens_in_the_stamp(world):
    cancel = world.tmp / "CANCEL"
    src = source(world, [dict(cls="task", seed=SEED, completion_tokens=123)])

    def later():
        time.sleep(1.0)
        cancel.write_text("x")
    threading.Thread(target=later, daemon=True).start()
    with pytest.raises(BaseException):
        run_core(world, adapter=Sleeper(world.host), receipts=src, evidence_=evidence(**REQUIRED),
                 a=dict(cancel_file=str(cancel)))
    stamp = manifest(world)["transport_abort"]
    assert [c[0] for c in src.calls].count("fence") == 1 and stamp["receipts"]["completion_tokens"] == 123


def test_absent_receipts_leave_the_abort_stamp_without_a_receipts_key(world):
    with pytest.raises(SystemExit):
        run_core(world, adapter=IngestBoom(world.host))
    assert "receipts" not in manifest(world)["transport_abort"]
