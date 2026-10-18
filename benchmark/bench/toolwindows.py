"""P371 (plan 4 A4): the Python side of the tool-window receipts the M64 opencode plugin
(`benchmark/opencode_plugins/toolwindows.js`) writes.

Pure helpers, no scoring or process import: the env a spawn carries (`env_for`) and `Receipts`, an incremental, strictly
validating reader of one item's receipt file. A record is exactly
`{attempt_id, session_id, call_id, tool, phase, seq, ms}`: `phase` `start` / `end`, `seq` 1, 2, 3 ... with no gap or
repeat across the file, `ms` the plugin's wall clock in epoch milliseconds, `call_id` the client's tool call id. Every
violation (malformed line, wrong attempt or session, a sequence gap, a second start / end of one call, an end without a
start or before it, a missing file, a torn last line at the final poll) raises `ArmContractError`: the contract is broken,
the attempt aborts, it is never a transport class."""
from __future__ import annotations

import json
import math
from pathlib import Path

from .arm_adapter import ArmContractError

ENV_RECEIPTS = "BENCH_TOOLWINDOW_RECEIPTS"
ENV_ATTEMPT = "BENCH_ATTEMPT_ID"
KEYS = ("attempt_id", "session_id", "call_id", "tool", "phase", "seq", "ms")
PHASES = ("start", "end")


def env_for(attempt_id, receipts):
    """The two env entries the plugin reads (it validates both at setup and on every hook)."""
    if not (isinstance(attempt_id, str) and attempt_id):
        raise ValueError("the attempt id must be a nonempty string")
    path = Path(receipts)
    if not path.is_absolute():
        raise ValueError("the tool-window receipts path must be absolute")
    return {ENV_RECEIPTS: str(path), ENV_ATTEMPT: attempt_id}


def _bad(path, why):
    raise ArmContractError(f"tool-window receipts {Path(path).name}: {why}")


def _text(value):
    return isinstance(value, str) and value != ""


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


class Receipts:
    def __init__(self, path, attempt_id):
        self.path, self.attempt_id = Path(path), attempt_id
        self.offset = 0
        self.seq = 0
        self.calls = {}                 # call_id -> {tool, start_ms, end_ms|None, session}
        self.sessions = set()

    def poll(self, session_id=None, *, final=False):
        """Read what was appended since the last poll and validate it. `session_id` (the live stream's, once known) must
        be the session of every record. `final`: the client is gone, a torn last line is corruption."""
        try:
            with self.path.open("rb") as fp:
                fp.seek(self.offset)
                chunk = fp.read()
        except FileNotFoundError:
            _bad(self.path, "file missing")
        except OSError as exc:
            _bad(self.path, f"unreadable ({type(exc).__name__})")
        *lines, tail = chunk.split(b"\n")
        if tail and final:
            _bad(self.path, "torn last line at the final poll")
        for raw in lines:
            self.offset += len(raw) + 1
            self._accept(raw)
        if session_id is not None and self.sessions - {session_id}:
            _bad(self.path, f"receipts for session {sorted(self.sessions - {session_id})}, the item's is {session_id!r}")

    def _accept(self, raw):
        try:
            record = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError):
            _bad(self.path, f"line {self.seq + 1} is not JSON")
        if not isinstance(record, dict):
            _bad(self.path, f"line {self.seq + 1} is not an object")
        if set(record) != set(KEYS):
            _bad(self.path, f"line {self.seq + 1} keys differ from {KEYS}")
        if not _text(record["attempt_id"]) or not _text(record["session_id"]):
            _bad(self.path, f"line {self.seq + 1}: attempt_id and session_id must be nonempty strings")
        if not _text(record["call_id"]):
            _bad(self.path, f"line {self.seq + 1}: call_id must be a nonempty string")
        if not _text(record["tool"]):
            _bad(self.path, f"line {self.seq + 1}: tool must be a nonempty string")
        if record["phase"] not in PHASES:
            _bad(self.path, f"line {self.seq + 1}: phase must be one of {PHASES}")
        if not _number(record["ms"]):
            _bad(self.path, f"line {self.seq + 1}: ms must be a finite non-negative number")
        if record["attempt_id"] != self.attempt_id:
            _bad(self.path, f"line {self.seq + 1}: attempt {record['attempt_id']!r}, this item's is {self.attempt_id!r}")
        if type(record["seq"]) is not int or record["seq"] != self.seq + 1:
            _bad(self.path, f"sequence {record['seq']!r} where {self.seq + 1} was due (a gap, a repeat or a reorder)")
        call = record["call_id"]
        if record["phase"] == "start":
            if call in self.calls:
                _bad(self.path, f"call {call!r} started twice")
            self.calls[call] = dict(tool=record["tool"], start_ms=record["ms"], end_ms=None, session=record["session_id"])
        else:
            entry = self.calls.get(call)
            if entry is None:
                _bad(self.path, f"call {call!r} ended without a start")
            if entry["end_ms"] is not None:
                _bad(self.path, f"call {call!r} ended twice")
            if record["ms"] < entry["start_ms"]:
                _bad(self.path, f"call {call!r} ended before its start")
            if record["session_id"] != entry["session"] or record["tool"] != entry["tool"]:
                _bad(self.path, f"call {call!r}: the end receipt names another session or tool than its start")
            entry["end_ms"] = record["ms"]
        self.sessions.add(record["session_id"])
        self.seq = record["seq"]
