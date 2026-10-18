"""P371 phase 2b (plan 3.1 / 3.4 step 4, R23 / R25, A8-A9): the item barrier driven by the evidence policy through the
core. `ready(k)` after the env is built and BEFORE `receipts.start`; `done(k, record)` after the row is written; a `.stop`
at ready exits cleanly before the spawn (`hook_stop: {before_slot}`), a `.stop` at done exits cleanly after that row
(`hook_stop: {after_slot, disposition}`); `--expect-items` is satisfied by the prefix in either case. With the barrier off
(tg1) there are no files and no waits."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import pytest

from bench import arm_runner
from bench import item_barrier as ib
from bench.tests.arm_neutral import NeutralArm
from bench.tests.p371_world import evidence, manifest, rows, run_core, world      # noqa: F401  (fixture)
from bench.tests.test_p371_a3_core import Played, REQUIRED, source

BARRIER = dict(item_barrier="on")


class FakeChain(threading.Thread):
    """The chain side of the barrier: answers `ready` with `go` (or `stop`) and `done` with `continue` (or `stop`), and
    records what the probe had done at each moment."""

    def __init__(self, world, adapter, *, stem="rows", items=2, stop_ready=None, stop_done=None, payload=None,
                 receipts=None):
        super().__init__(daemon=True)
        self.world, self.adapter, self.stem, self.items = world, adapter, world.tmp / stem, items
        self.stop_ready, self.stop_done, self.payload = stop_ready, stop_done, payload
        self.receipts = receipts
        self.seen, self.failure = [], None

    def wait_for(self, path, timeout=8):
        end = time.monotonic() + timeout
        while not Path(path).exists():
            if time.monotonic() > end:
                raise AssertionError(f"{Path(path).name} never appeared")
            time.sleep(0.01)

    def run(self):
        try:
            for k in range(self.items):
                self.wait_for(f"{self.stem}.item{k}.ready")
                self.seen.append(("ready", k, len(rows(self.world)), len(self.adapter.env_attempts),
                                  len(self.receipts.calls) if self.receipts else None))
                if self.stop_ready == k:
                    Path(f"{self.stem}.item{k}.stop").write_text(json.dumps(self.payload or {}))
                    return
                Path(f"{self.stem}.item{k}.go").write_text("")
                self.wait_for(f"{self.stem}.item{k}.done")
                record = json.loads(Path(f"{self.stem}.item{k}.done").read_text())
                self.seen.append(("done", k, len(rows(self.world)), record))
                if self.stop_done == k:
                    Path(f"{self.stem}.item{k}.stop").write_text(json.dumps(self.payload or {}))
                    return
                Path(f"{self.stem}.item{k}.continue").write_text("")
        except BaseException as exc:      # noqa: BLE001 — reported by the test
            self.failure = exc


def drive(world, chain_kw=None, *, receipts=False, a=None, **kw):
    adapter = NeutralArm(world.host)
    src = source(world) if receipts else None
    chain = FakeChain(world, adapter, receipts=src, **(chain_kw or {}))
    chain.start()
    ev = evidence(**BARRIER, **(REQUIRED if receipts else {}))
    try:
        result = run_core(world, adapter=adapter, receipts=src, evidence_=ev, a=dict(items="one,two", **(a or {})), **kw)
    finally:
        chain.join(12)
    assert chain.failure is None, chain.failure
    return result, chain, src


def test_with_the_barrier_on_every_item_waits_for_go_and_continue(world):
    (rc_, _), chain, _ = drive(world)
    assert rc_ == 0 and [r["id"] for r in rows(world)] == ["fake/one", "fake/two"]
    kinds = [(e[0], e[1]) for e in chain.seen]
    assert kinds == [("ready", 0), ("done", 0), ("ready", 1), ("done", 1)]
    assert "hook_stop" not in manifest(world)


def test_ready_is_after_the_env_is_built_and_before_receipts_start(world):
    (_, adapter), chain, src = drive(world, receipts=True)
    ready0, done0, ready1, done1 = chain.seen
    # discovery + this item's env were built; the receipt source had not been touched for THIS item yet
    assert ready0[3] == 2 and ready0[4] == 0 and ready0[2] == 0
    assert ready1[3] == 3 and ready1[4] == 4 and ready1[2] == 1                  # item one's start/admit/admit/fence = 4 calls
    assert [c[0] for c in src.calls] == ["start", "admit", "admit", "fence"] * 2


def test_done_is_written_after_the_row_with_the_row_key_and_evidence_hashes(world):
    (_, _), chain, _ = drive(world, receipts=True)
    done0 = chain.seen[1]
    assert done0[2] == 1                                       # the row was already on disk when `.done` appeared
    record = done0[3]
    (row, _second) = rows(world)
    assert record["id"] == "fake/one" and record["attempt_id"] == "fake/one#a1.r0" and record["passed"] is True
    path = Path(row["events_path"].replace("$STACK_WORKDIR", str(world.tmp)))
    assert record["evidence"]["events"] == dict(path=row["events_path"], sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    assert record["receipts"] == row["receipts"] and record["final_tree"]["manifest_sha256"] == row["final_tree"][
        "manifest_sha256"]


def test_barrier_files_are_named_after_the_rows_file_and_the_item_index(world):
    drive(world)
    names = sorted(p.name for p in world.tmp.glob("rows.item*"))
    assert names == [f"rows.item{k}.{kind}" for k in (0, 1) for kind in ("continue", "done", "go", "ready")]


def test_a_stop_at_ready_exits_cleanly_before_the_spawn_with_the_slot_in_the_manifest(world):
    (rc_, adapter), chain, src = drive(world, dict(stop_ready=1), receipts=True,
                                       a=dict(expect_items="fake/one"))
    assert rc_ == 0 and [r["id"] for r in rows(world)] == ["fake/one"]
    assert manifest(world)["hook_stop"] == dict(before_slot="fake/two")
    assert [c[0] for c in src.calls] == ["start", "admit", "admit", "fence"]       # no start for the stopped slot
    assert len(list((world.tmp / "neutral_evidence").rglob("fake__two*"))) == 0       # nothing spawned or reserved
    assert "transport_abort" not in manifest(world)


def test_a_stop_at_done_exits_cleanly_after_that_row_with_the_disposition(world):
    (rc_, _), chain, src = drive(world, dict(stop_done=0, payload=dict(disposition="rerun_same_slot")), receipts=True,
                                 a=dict(expect_items="fake/one"))
    assert rc_ == 0 and [r["id"] for r in rows(world)] == ["fake/one"]
    assert manifest(world)["hook_stop"] == dict(after_slot="fake/one", disposition="rerun_same_slot")
    assert len(src.calls) == 4


def test_a_stop_without_a_payload_records_a_null_disposition(world):
    drive(world, dict(stop_done=0), a=dict(expect_items="fake/one"))
    assert manifest(world)["hook_stop"] == dict(after_slot="fake/one", disposition=None)


def test_expect_items_is_checked_against_the_prefix_through_the_stopped_slot(world):
    drive(world, dict(stop_done=0), a=dict(expect_items="fake/one,fake/two"))            # the full list: prefix satisfies
    assert [r["id"] for r in rows(world)] == ["fake/one"]


def test_expect_items_still_refuses_a_prefix_that_differs(world):
    with pytest.raises(SystemExit, match="expect-items"):
        drive(world, dict(stop_done=0), a=dict(expect_items="fake/two,fake/one"))
    with pytest.raises(SystemExit, match="expect-items"):
        drive(world, dict(stop_ready=0), a=dict(expect_items="fake/one"))                # nothing ran, one was expected


def test_a_stop_at_the_first_ready_runs_nothing_and_satisfies_an_empty_prefix(world):
    (rc_, _), _, _ = drive(world, dict(stop_ready=0), a=dict(expect_items="fake/one,fake/two"))
    assert rc_ == 0 and rows(world) == [] and manifest(world)["hook_stop"] == dict(before_slot="fake/one")


def test_the_barrier_ack_timeout_aborts(world, monkeypatch):
    monkeypatch.setattr(arm_runner, "ACK_TIMEOUT_S", 0.3)
    monkeypatch.setattr(arm_runner, "ACK_POLL_S", 0.05)
    with pytest.raises(SystemExit, match="not acknowledged"):
        run_core(world, evidence_=evidence(**BARRIER))
    assert rows(world) == []
    assert "not acknowledged" in manifest(world)["transport_abort"]["error"]


def test_a_cooperative_cancel_while_waiting_at_the_barrier_is_honoured(world):
    cancel = world.tmp / "cancel"

    def later():
        end = time.monotonic() + 10
        while not (world.tmp / "rows.item0.ready").exists() and time.monotonic() < end:
            time.sleep(0.01)
        cancel.write_text("")

    t = threading.Thread(target=later, daemon=True)
    t.start()
    with pytest.raises(SystemExit, match="cancelled by runner"):
        run_core(world, evidence_=evidence(**BARRIER), a=dict(cancel_file=str(cancel)))
    t.join(10)
    assert rows(world) == []


def test_a_replayed_item_index_is_refused(world):
    (world.tmp / "rows.item0.ready").write_text("")
    with pytest.raises(SystemExit, match="already exists"):
        run_core(world, evidence_=evidence(**BARRIER))


# ---------------------------------------------------------------- off: no files, no waits
def test_with_the_barrier_off_there_are_no_files_and_no_waits(world, monkeypatch):
    monkeypatch.setattr(ib.time, "sleep", lambda s: (_ for _ in ()).throw(AssertionError("the barrier waited")))
    assert run_core(world, a=dict(items="one,two"))[0] == 0
    assert [r["id"] for r in rows(world)] == ["fake/one", "fake/two"]
    assert list(world.tmp.glob("rows.item*")) == [] and "hook_stop" not in manifest(world)


def test_the_tg1_and_m64_evidence_policies_bind_the_barrier_as_the_plan_says():
    from bench import arm_opencode as ao
    from bench import tg1_runner
    assert tg1_runner.TG1_EVIDENCE.item_barrier == "off"
    assert ao.m64_evidence().item_barrier == "off"                      # production stays off until the chain core drives it
    assert ao.m64_evidence(item_barrier="on").item_barrier == "on"
