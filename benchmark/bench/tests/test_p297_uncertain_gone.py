"""P297 (2026-10-13): an uncertain cleanup whose only uncertain processes no longer exist authorises the block restart.

The probe's guard marks a same-uid process whose start order cannot be read as uncertain (C151 R10: it could be ours).
The M63 ON chain aborted when a Spotlight mdworker vanished between listing and the read (pid 87652): nothing of ours
survived, but the runner refused its one restart. The runner now re-checks each uncertain pid; only pids that no longer
exist are cleared. A pid that exists (alive or reused), tracked-identity unknowns, survivors, containers or an order
failure still refuse. The probe (identity) is unchanged."""
import json
from pathlib import Path

import pytest

from bench import chain_ops as co
from bench.tests.test_c147_chain_runner import CHAIN, PICK1, R, _chain_for, chain_json, env, log_has, run   # noqa: F401

FX = Path(__file__).parent / "fixtures/p297_real_uncertain_vanished_manifest.json"


def _att(man=None):
    man = man or json.loads(FX.read_text())
    return {"cleanup_status": R.receipt_from_manifest(man), "transport_abort": man["transport_abort"], "rc": 1,
            "outcome": "exited"}


def _block(env):
    ops = env["ops"]
    ops.load(PICK1)
    return {"worker": {"pid": ops.ident["pid"], "create_time": ops.ident["create_time"]}}


def test_real_abort_with_a_vanished_uncertain_pid_authorises_the_restart(env):
    ch, block = _chain_for(env), _block(env)
    ch.check_restart_eligible(_att(), {"model": PICK1}, block)
    assert ("pid_exists", 87652) in env["ops"].calls
    assert log_has(env, "87652") and log_has(env, "no longer exist")


def test_uncertain_pid_still_present_refuses(env):
    env["ops"].alive_pids = {87652}          # alive, or reused: either way it could be ours
    ch, block = _chain_for(env), _block(env)
    with pytest.raises(co.ChainAbort, match="uncertain"):
        ch.check_restart_eligible(_att(), {"model": PICK1}, block)


@pytest.mark.parametrize("mutate", ["unknown", "survivors", "containers", "order_failure", "no_reasoned_pid",
                                    "uncertain_missing"])
def test_everything_else_uncertain_still_refuses(env, mutate):
    man = json.loads(FX.read_text())
    cs = man["cleanup_status"]
    if mutate == "unknown":
        cs["unknown"] = [{"pid": 4, "create_time": 1.0}]
    elif mutate == "survivors":
        cs["survivors"] = [5]
    elif mutate == "containers":
        cs["containers_remaining"] = ["mlxbench-run-x"]
    elif mutate == "order_failure":
        man["transport_abort"]["error"] += "; order failure: start order errno 22"
    elif mutate == "no_reasoned_pid":
        cs["orphans_unattributed"] = [o for o in cs["orphans_unattributed"] if not o.get("reason")]
    elif mutate == "uncertain_missing":
        cs.pop("uncertain")
    man["cleanup_status"] = cs
    ch, block = _chain_for(env), _block(env)
    with pytest.raises(co.ChainAbort, match="restart refused"):
        ch.check_restart_eligible(_att(man), {"model": PICK1}, block)


def test_chain_restarts_the_block_and_completes_when_the_uncertain_pid_is_gone(env):
    rc = run(env, CHAIN, plan=["normal", "abort_after_n", "normal"],
             extra_env={"FAKE_N": "1", "FAKE_CLEANUP_UNCERTAIN": "1", "FAKE_CLEANUP_UNCERTAIN_PIDS": "87652"})
    assert rc == 0 and len(chain_json(env)["restarts"]) == 1
    assert log_has(env, "no longer exist")


def test_chain_still_refuses_when_the_uncertain_pid_is_present(env):
    env["ops"].alive_pids = {87652}
    rc = run(env, CHAIN, plan=["normal", "abort_after_n", "normal"],
             extra_env={"FAKE_N": "1", "FAKE_CLEANUP_UNCERTAIN": "1", "FAKE_CLEANUP_UNCERTAIN_PIDS": "87652"})
    assert rc == 2 and log_has(env, "restart refused")


def test_chain_ops_pid_exists_reads_the_process_table():
    import os
    o = co.ChainOps("/repo", "/wd", "/wd/ov.yaml", co.RunLog(Path("/dev/null"), out=lambda s: None))
    assert o.pid_exists(os.getpid()) is True
    assert o.pid_exists(2 ** 22 + 12345) is False
