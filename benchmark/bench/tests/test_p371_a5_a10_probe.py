"""P371 phase 3b parts 2 and 6, probe side. A5: `--print-identity` emits the snapshot (`snapshot_tool`, `snapshot_sha256`,
`snapshot_complete`, `snapshot_fields`) the chain computes the epoch from. A10: the probe verifies that an A4 receipt the chain
bound to a worker (`bench_binding.worker`) names the CURRENT worker; a receipt from before a reload refuses before any spawn."""
from __future__ import annotations

import json

import pytest

from bench import arm_adapter as aa
from bench import arm_runner
from bench.tests.arm_neutral import NeutralArm, NeutralCorpus
from bench.tests.p371_world import args, manifest, rows, run_core, template, world      # noqa: F401  (fixture)


def last_json(capsys):
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_print_identity_reports_the_snapshot_the_chain_computes_the_epoch_from(world, capsys):
    adapter = NeutralArm(world.host)
    assert arm_runner.print_identity(world.host, adapter, args(world.tmp), template=template(),
                                     corpus=NeutralCorpus(world.tmp)) == 0
    out = last_json(capsys)
    snap = adapter.snapshot()
    assert out["snapshot_tool"] == snap.tool == "neutralclient" and out["snapshot_sha256"] == snap.sha256
    assert out["snapshot_complete"] is True and out["snapshot_fields"] == snap.fields
    assert aa.epoch_id([snap]) and len(out["snapshot_sha256"]) == 64


def test_print_identity_of_an_incomplete_snapshot_says_so(world, capsys):
    class Owed(NeutralArm):
        def snapshot(self):
            return aa.Snapshot(tool="neutralclient", fields=dict(label="x"), complete=False, missing=("bottle_sha256",))

    arm_runner.print_identity(world.host, Owed(world.host), args(world.tmp), template=template(),
                              corpus=NeutralCorpus(world.tmp))
    out = last_json(capsys)
    assert out["snapshot_complete"] is False and len(out["snapshot_sha256"]) == 64


def test_print_identity_without_the_client_binary_has_no_snapshot_not_a_guess(world, capsys):
    class NoBinary(NeutralArm):
        def identity_binary(self):
            return self.binary_path, False

    arm_runner.print_identity(world.host, NoBinary(world.host), args(world.tmp), template=template(),
                              corpus=NeutralCorpus(world.tmp))
    out = last_json(capsys)
    assert out["snapshot_sha256"] is None and out["snapshot_complete"] is None and out["snapshot_fields"] is None


# ---------------------------------------------------------------- A10: the receipt names the current worker
def receipt(tmp, worker, **extra):
    path = tmp / "a4_receipt.json"
    path.write_text(json.dumps(dict(pass_=True, run_id="r", model="neutral/model", bench_binding=dict(
        worker=worker, load=0, worker_n=0, arm="dsh"), **extra)))
    return str(path)


def test_a_receipt_bound_to_another_worker_refuses_before_any_spawn(world):
    old = dict(pid=world.worker["pid"] + 7, create_time=world.worker["create_time"])
    with pytest.raises(SystemExit, match="REFUSED.*another worker"):
        run_core(world, a=dict(a4_v2_receipt=receipt(world.tmp, old)))
    assert rows(world) == [] and not list((world.tmp / "neutral_evidence").rglob("*.events.jsonl"))


def test_a_receipt_bound_to_the_current_worker_runs(world):
    ok = dict(pid=world.worker["pid"], create_time=world.worker["create_time"])
    assert run_core(world, a=dict(a4_v2_receipt=receipt(world.tmp, ok)))[0] == 0
    assert len(rows(world)) == 1


def test_a_raw_gate_receipt_without_a_binding_is_left_to_the_adapters_own_checks(world):
    path = world.tmp / "raw.json"
    path.write_text(json.dumps(dict(run_id="r", model="neutral/model")))
    assert run_core(world, a=dict(a4_v2_receipt=str(path)))[0] == 0


def test_a_receipt_whose_worker_create_time_differs_refuses_too(world):
    old = dict(pid=world.worker["pid"], create_time=world.worker["create_time"] + 1)
    with pytest.raises(SystemExit, match="another worker"):
        run_core(world, a=dict(a4_v2_receipt=receipt(world.tmp, old)))
