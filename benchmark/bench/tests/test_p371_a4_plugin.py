"""P371 phase 2b, plan 4 A4: `toolwindows.js` on the REAL pinned client — what its hooks receive (fields, call id), a
write failure makes the tool call FAIL (never silently unwatched), an unset env refuses at plugin load, and the call
rejected by the toolbounds plugin / an unknown tool are visible in the receipts the way the adapter's rules assume."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from bench import arm_opencode as ao
from bench import provenance
from bench import toolwindows as tw
from bench import worker_receipts as wr
from bench.tests.opencode_v2_mock import MockServer
from bench.tests.test_m64_arm_oc_contract import OcHarness
from bench.tests.test_opencode_v2_probe import MODEL, tg1_probe as probe          # noqa: F401  (fixture)
from bench.tests.test_tg1_integration import FROZEN, pinned_binary                 # noqa: F401  (fixture)


def direct(probe, pinned_binary, monkeypatch, tmp_path, script, *, receipts=None, drop_env=False, tag="direct"):
    """One real `opencode run` of the M64 configuration against the mock, outside the runner. Returns
    (events, mock, receipts path)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    h = OcHarness(probe, pinned_binary, monkeypatch, tmp_path)
    with MockServer(script) as mock:
        h._setup(mock, None)
        arm = ao.OpencodeArm(probe, mode="m64", search=ao.OfflineTestSearchService())
        run_dir = arm.make_run_dir(Path(os.environ["STACK_WORKDIR"]), tag, arm.selection())
        work = tmp_path / "work"
        work.mkdir()
        receipts = Path(receipts) if receipts else tmp_path / "ev" / "tw.jsonl"
        (tmp_path / "ev").mkdir(exist_ok=True)
        receipts.parent.mkdir(parents=True, exist_ok=True)
        if not receipts.exists():
            receipts.touch()                                   # the runner reserves the file before the spawn
        env = arm.build_env(run_dir, work, arm.seed_overlay(MODEL, 1), receipts=tmp_path / "ev/dfz.jsonl",
                            frozen_date=FROZEN, toolwindow_receipts=receipts,
                            attempt=wr.AttemptContext.make("python/one", 1))
        if drop_env:
            env.pop(tw.ENV_RECEIPTS)
        probe._fresh_tmpdir(env)
        done = subprocess.run(arm.command(pinned_binary, MODEL, "go"), cwd=work, env=env, capture_output=True,
                              text=True, timeout=120, stdin=subprocess.DEVNULL)
        events = [json.loads(line) for line in done.stdout.splitlines() if line.startswith("{")]
        return dict(events=events, mock=mock, receipts=receipts, run=done, arm=arm, run_dir=run_dir, env=env, work=work)


def tool_uses(events):
    return [e["part"] for e in events if e["type"] == "tool_use"]


def lines(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines()]


def test_the_real_hooks_deliver_the_session_the_tool_and_the_same_call_id_as_the_tool_use_event(
        probe, pinned_binary, monkeypatch, tmp_path):
    got = direct(probe, pinned_binary, monkeypatch, tmp_path, {1: dict(name="shell", input={"command": "echo hi"})})
    (use,) = tool_uses(got["events"])
    start, end = lines(got["receipts"])
    assert (start["phase"], end["phase"], start["seq"], end["seq"]) == ("start", "end", 1, 2)
    assert start["call_id"] == end["call_id"] == use["id"] == "call_write" and start["tool"] == "shell"
    assert start["session_id"] == end["session_id"] == got["events"][0]["sessionID"]
    assert start["attempt_id"] == "python/one#a1.r0" and isinstance(start["ms"], int) and end["ms"] >= start["ms"]
    # the receipt window brackets the event's own execution window
    assert start["ms"] <= use["state"]["time"]["start"] + 50 and end["ms"] >= use["state"]["time"]["end"] - 50


def test_a_failed_receipt_write_fails_the_tool(probe, pinned_binary, monkeypatch, tmp_path):
    sub = tmp_path / "bad"
    sub.mkdir()
    # a directory where the file should be: every append fails
    target = sub / "tw.jsonl"
    target.mkdir()
    got = direct(probe, pinned_binary, monkeypatch, sub, {1: dict(name="shell", input={"command": "echo SHOULD_NOT_RUN"})},
                 receipts=target)
    (use,) = tool_uses(got["events"])
    assert use["state"]["status"] == "error" and "P371_TOOLWINDOWS" in use["state"]["error"]
    assert "SHOULD_NOT_RUN" not in json.dumps(use["state"].get("output", ""))             # the command never ran
    assert "P371_TOOLWINDOWS" in json.dumps(got["mock"].chats[1]["body"]["messages"])      # the model was told
    assert got["run"].returncode == 0 and len(got["mock"].chats) == 2                      # and the item went on


def test_the_plugin_refuses_to_load_without_its_receipt_env(probe, pinned_binary, monkeypatch, tmp_path):
    got = direct(probe, pinned_binary, monkeypatch, tmp_path, {}, drop_env=True)
    logged = {**got["env"], "OPENCODE_PRINT_LOGS": "1"}
    with pytest.raises(provenance.ServedConfigError, match="failed plugin load|load proof missing"):
        got["arm"]._prove_plugins(got["work"], logged, got["run_dir"], pinned_binary, subprocess.run)


def test_the_activation_proof_passes_with_the_four_plugins_and_the_env(probe, pinned_binary, monkeypatch, tmp_path):
    got = direct(probe, pinned_binary, monkeypatch, tmp_path, {})
    logged = {**got["env"], "OPENCODE_PRINT_LOGS": "1"}
    got["arm"]._prove_plugins(got["work"], logged, got["run_dir"], pinned_binary, subprocess.run)


def test_a_call_rejected_by_toolbounds_leaves_no_receipt_and_an_unknown_tool_only_a_start(
        probe, pinned_binary, monkeypatch, tmp_path):
    rejected = direct(probe, pinned_binary, monkeypatch, tmp_path / "a",
                      {1: dict(name="shell", input={"command": "echo x", "background": True})}, tag="a")
    (use,) = tool_uses(rejected["events"])
    assert use["state"]["status"] == "error" and use["state"]["error"].startswith("M62_TOOL_BOUND:")
    assert lines(rejected["receipts"]) == []
    unknown = direct(probe, pinned_binary, monkeypatch, tmp_path / "b", {1: dict(name="subagent", input={})}, tag="b")
    (use,) = tool_uses(unknown["events"])
    assert use["state"]["status"] == "error"
    assert [r["phase"] for r in lines(unknown["receipts"])] == ["start"]                  # the event completes its window
