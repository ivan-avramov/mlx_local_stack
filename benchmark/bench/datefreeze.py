"""P364: the date-freeze contract on the Python side (plugin: `benchmark/opencode_plugins/datefreeze.js`).

Pure helpers, no scoring import (the tg1 generation identity is an import closure): the `Www Mmm DD YYYY` shape, the
env a spawn carries, the WebSocket refusal, and the exact reconciliation of an item's receipts against its observed
requests. Every refusal is a `TransportAbort`: no row is written."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .token_turn_gate import TransportAbort

# JavaScript `Date.toDateString()` (zero-padded day), which is what opencode prints and `time.strftime("%a %b %d %Y")`
# produces in the C/English locale.
SHAPE = re.compile(r"^(Sun|Mon|Tue|Wed|Thu|Fri|Sat) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
                   r"(0[1-9]|[12][0-9]|3[01]) [0-9]{4}\Z")
ENV_DATE = "BENCH_FROZEN_PROMPT_DATE"
ENV_RECEIPTS = "BENCH_DATEFREEZE_RECEIPTS"
KINDS = ("primary", "compaction", "generate", "title")
HEX64 = re.compile(r"^[0-9a-f]{64}\Z")
RECEIPT_KEYS = ("sessionID", "seq", "kind", "frozen", "n_initial_replaced", "n_update_removed", "system_sha256")


def valid(date):
    return isinstance(date, str) and bool(SHAPE.match(date))


def require_valid(date, what="frozen prompt date"):
    if not valid(date):
        raise ValueError(f"{what} must be 'Www Mmm DD YYYY' (zero-padded day), got {date!r}")
    return date


def env_for(frozen_date, receipts):
    """The two env entries a spawn carries (the plugin validates both at setup and on every hook)."""
    path = Path(receipts)
    if not path.is_absolute():
        raise ValueError("the receipts path must be absolute")
    return {ENV_DATE: require_valid(frozen_date), ENV_RECEIPTS: str(path)}


def refuse_websocket(doc):
    """The structured hooks are transport-neutral, but a WebSocket session transport is outside what the wire tests
    cover: a carrier that selects one is refused."""
    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "webSocket" or (key == "transport" and str(value).lower() == "websocket"):
                    raise TransportAbort("P364: the carrier selects a WebSocket transport (not covered by the date freeze)")
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(doc)


def _bad(path, why):
    raise TransportAbort(f"P364 date-freeze receipts {Path(path).name}: {why}")


def reconcile(path, *, frozen, session_id, requests_observed, killed=False, allowed_kinds=("primary",)):
    """Exact reconciliation of one item's receipt file against its observed requests.

    Every line must be a complete receipt for `frozen` (no error line, a replaced date instruction on every request
    that carries one, sha256 of the masked system text), sequences contiguous per (session, kind), only the item's own
    root session and the allowed kinds, and the primary count equal to `requests_observed`. A killed item may differ
    by one in either direction (the request in flight when the client was stopped: its hook may run before or after
    its step event is observed). Returns the summary the row records."""
    receipt_path = Path(path)
    if not receipt_path.is_file():
        _bad(path, "missing")
    try:
        text = receipt_path.read_text()
    except (OSError, UnicodeError) as exc:
        _bad(path, f"unreadable ({type(exc).__name__})")
    records = []
    for number, raw in enumerate(text.splitlines(), 1):
        try:
            record = json.loads(raw)
        except ValueError:
            _bad(path, f"line {number} is not JSON")
        if not isinstance(record, dict):
            _bad(path, f"line {number} is not an object")
        if record.get("error"):
            _bad(path, f"line {number} records a refusal: {str(record['error'])[:120]}")
        missing = [k for k in RECEIPT_KEYS if k not in record]
        if missing:
            _bad(path, f"line {number} lacks {missing}")
        if record["frozen"] != frozen:
            _bad(path, f"line {number} froze {record['frozen']!r}, expected {frozen!r}")
        if record["kind"] not in allowed_kinds:
            _bad(path, f"line {number}: unexpected request kind {record['kind']!r}")
        if not (isinstance(record["seq"], int) and not isinstance(record["seq"], bool) and record["seq"] >= 1):
            _bad(path, f"line {number}: bad seq")
        for key in ("n_initial_replaced", "n_update_removed"):
            if not (isinstance(record[key], int) and not isinstance(record[key], bool) and record[key] >= 0):
                _bad(path, f"line {number}: bad {key}")
        if record["kind"] != "title" and record["n_initial_replaced"] < 1:
            _bad(path, f"line {number}: the {record['kind']} request carried no date instruction")
        if not (isinstance(record["system_sha256"], str) and HEX64.match(record["system_sha256"])):
            _bad(path, f"line {number}: bad system_sha256")
        if record["sessionID"] != session_id:
            _bad(path, f"line {number}: receipt for session {record['sessionID']!r}, the item's is {session_id!r}")
        records.append(record)
    seen = {}
    for record in records:
        key = (record["sessionID"], record["kind"])
        seen[key] = seen.get(key, 0) + 1
        if record["seq"] != seen[key]:
            _bad(path, f"{key[1]} sequence {record['seq']} where {seen[key]} was due (a missing or repeated request)")
    primary = sum(1 for r in records if r["kind"] == "primary")
    slack = 1 if killed else 0
    if not requests_observed - slack <= primary <= requests_observed + slack:
        _bad(path, f"{primary} primary receipts for {requests_observed} observed requests")
    removed = sum(r["n_update_removed"] for r in records)
    return dict(requests=primary, receipts=len(records), n_update_removed=removed, update_removed=removed > 0)
