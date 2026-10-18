"""P371 phase 2b, plan 4 A4 on the REAL pinned client (opencode 2.0.20 against the scripted mock provider): the
`toolwindows.js` plugin's start / end receipts make a hung shell visible while it runs, so the watchdog kills it at the
(accelerated) limit and the row carries `exec_timeout`. FIRST red test of A4: it needs the tool hooks to fire and to
carry a call id."""
from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from bench import arm_opencode as ao
from bench import run_config as rc
from bench.tests.arm_entry import m64_main
from bench.tests.opencode_v2_mock import MockServer
from bench.tests.test_m64_arm_oc_contract import OcHarness, entry_parser
from bench.tests.test_opencode_v2_probe import MODEL, tg1_probe as probe          # noqa: F401  (fixture)
from bench.tests.test_tg1_integration import FROZEN, pinned_binary                 # noqa: F401  (fixture)

REPO = Path(__file__).resolve().parents[3]
LIMIT_S, GRACE_S = 2.0, 1.0


def oc_run(probe, pinned_binary, monkeypatch, tmp_path, script, *, limit_s=LIMIT_S):
    (Path(os.environ["STACK_WORKDIR"]) / "m62/inject").mkdir(parents=True, exist_ok=True)
    h = OcHarness(probe, pinned_binary, monkeypatch, tmp_path)
    with MockServer(script) as mock:
        f, sub = h._setup(mock, None)
        out = sub / "rows.jsonl"
        argv = h._argv(sub, out, [])
        monkeypatch.setattr(sys, "argv", argv)
        a = entry_parser().parse_args(argv[1:])
        base = ao.m64_template().watchdog
        template = dataclasses.replace(ao.m64_template(), watchdog=rc.watchdog_on(
            limit_s=limit_s, grace_s=GRACE_S, toolwindows_sha256=base["toolwindows_sha256"]))
        adapter = ao.OpencodeArm(probe, mode="m64", search=ao.OfflineTestSearchService())
        abort = None
        try:
            m64_main(probe, adapter, a, template)
        except SystemExit as exc:
            abort = exc if exc.code not in (0, None) else None
        row = json.loads(out.read_text().splitlines()[0]) if out.exists() else None
        return dict(row=row, abort=abort, mock=mock, sub=sub, adapter=adapter)


def receipts_of(row):
    path = Path(row["toolwindows_path"].replace("$STACK_WORKDIR", os.environ["STACK_WORKDIR"]))
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_a_hung_shell_is_killed_at_the_accelerated_limit_and_the_row_is_flagged(probe, pinned_binary, monkeypatch, tmp_path):
    started = time.monotonic()
    got = oc_run(probe, pinned_binary, monkeypatch, tmp_path, {1: dict(name="shell", input={"command": "sleep 30"})})
    assert got["abort"] is None, got["abort"]
    row = got["row"]
    assert time.monotonic() - started < 25, "the watchdog did not end the 30 s sleep"
    assert "exec_timeout" in row["nonconv_flags"] and row["nonconv_kind"] == "exec_timeout" and row["converged"] is False
    dog = row["shell_watchdog"]
    assert dog["limit_s"] == LIMIT_S and dog["kills"] and dog["kills"][0]["actions"][0] == "SIGTERM"
    records = receipts_of(row)
    assert [r["phase"] for r in records] == ["start", "end"] and [r["seq"] for r in records] == [1, 2]
    start, end = records
    assert start["call_id"] == end["call_id"] == "call_write" and start["tool"] == end["tool"] == "shell"
    assert start["attempt_id"] == end["attempt_id"] == "python/one#a1.r0" and start["session_id"] == row["session_id"]
    assert end["ms"] - start["ms"] >= 1500 and set(start) == {"attempt_id", "session_id", "call_id", "tool", "phase",
                                                                "seq", "ms"}
    assert row["gate"]["requests_completed"] == 2          # the client saw the tool fail and finished the item
