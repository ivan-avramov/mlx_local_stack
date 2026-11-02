"""P586 / P593 at the done hook (implementer's red-first tests): the hook builds the client evidence and writes the item record."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from bench import p426_hooks as ph
from bench.tests import test_b2_s4_reconcile as T

FIX = Path(__file__).parent / "fixtures" / "p586"
ROW = json.loads((FIX / "row.json").read_text())
REC = json.loads((FIX / "item_record_baseline.json").read_text())
DATA = (FIX / "window.log").read_bytes()
SLOT = ROW["id"]
SLOT_FILE = "0__A__m__s1__go__crypto-square"
SLOT = "0|A|m|s1|go|crypto-square"


def setup(tmp_path, *, export_bytes=None, row_edit=None, workdir=None):
    ops, hooks, out = T.make_hooks(tmp_path, arm="OFF")
    ops.summary = dict(REC["worker_before"])
    hooks.before_attempt(SLOT, T.ctx(slot=SLOT, item="go/crypto-square"))
    export = tmp_path / "export.json"
    raw = (FIX / "export.json").read_bytes() if export_bytes is None else export_bytes
    export.write_bytes(raw)
    row = copy.deepcopy(ROW)
    row["transcript_path"] = str(export)
    row["evidence_sha256"]["export"] = hashlib.sha256((FIX / "export.json").read_bytes()).hexdigest()
    if row_edit:
        row_edit(row)
    with open(ops.log, "ab") as f:
        f.write(DATA)
    ops.summary = dict(REC["worker_after"])
    return ops, hooks, out, row


def record(out):
    return json.loads((out / "items" / f"{SLOT_FILE}.json").read_text())


def done(hooks, row):
    ctx = T.ctx(row, slot=SLOT, item="go/crypto-square")
    return hooks.after_attempt(SLOT, dict(id="go/crypto-square"), ctx)


def test_the_leg3_item_is_accepted_and_its_record_carries_the_client_abort_block(tmp_path):
    ops, hooks, out, row = setup(tmp_path)
    assert done(hooks, row).kind == "accept"
    rec = record(out)
    assert rec["verdict"] == "reconciled" and rec["case"] == "kill_client_aborted"
    b = rec["client_abort"]
    assert b["request_index"] == 2 and b["telemetry_lines"] == 155 and b["cap_s"] == 3600
    assert rec["totals"]["decode_rate_source"] == "completed requests (spec 8)"
    assert ph.sealed_ok(rec)


def test_an_export_that_differs_from_the_rows_sha_invalidates(tmp_path):
    ops, hooks, out, row = setup(tmp_path, export_bytes=(FIX / "export.json").read_bytes() + b" ")
    d = done(hooks, row)
    assert d.kind == "invalidate" and "client_abort_provenance" in d.reason
    assert record(out)["verdict"] == "invalid"


def test_an_unreadable_export_is_a_problem_not_an_exception(tmp_path):
    ops, hooks, out, row = setup(tmp_path)
    row["transcript_path"] = str(tmp_path / "gone.json")
    d = done(hooks, row)
    assert d.kind == "invalidate" and "client_abort_provenance" in d.reason


def test_an_export_that_is_not_json_is_a_problem_not_an_exception(tmp_path):
    ops, hooks, out, row = setup(tmp_path, export_bytes=b"not json")
    row["evidence_sha256"]["export"] = hashlib.sha256(b"not json").hexdigest()
    assert done(hooks, row).kind == "invalidate"


def test_a_stock_workdir_transcript_path_resolves_through_ops_wd(tmp_path):
    ops, hooks, out, row = setup(tmp_path)
    ops.wd = tmp_path
    row["transcript_path"] = "$STACK_WORKDIR/export.json"
    assert done(hooks, row).kind == "accept"


def test_a_normal_item_has_the_decode_rate_source_and_no_client_abort_block(tmp_path):
    ops, hooks, out = T.make_hooks(tmp_path)
    hooks.before_attempt(T.SLOT, T.ctx())
    ops.serve(*T.req(prompt=100, gen=10, draft=T.ON_DRAFT))
    assert hooks.after_attempt(T.SLOT, dict(id="python/a"), T.ctx(T.row_of([(100, 10)]))).kind == "accept"
    rec = json.loads((out / "items" / f"{T.SLOT_FILE}.json").read_text())
    assert rec["totals"]["decode_rate_source"] == "completed requests (spec 8)" and "client_abort" not in rec
