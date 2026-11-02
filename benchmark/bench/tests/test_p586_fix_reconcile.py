"""P586 fix round 1, X1-X3 (red-first): the client-abort close gap, the export's ownership of the row, the validated times."""
from __future__ import annotations

import copy
import dataclasses

import pytest

from bench import p426_reconcile as pr
from bench.tests.test_p586_impl_reconcile import (AFTER, BEFORE, DATA, EXPORT, ROW, COMPLETED_CASE, FAILED_CASE, completed_variant,
                                                  not_ok, run)


def _aborted(export):
    return [m for m in export["messages"] if m["type"] == "assistant"][-1]


# -- X1: the close gap is wall_s - last.elapsed_s, never a local-stamp difference
def test_x1_close_gap_is_the_exports_wall_minus_the_last_telemetry_elapsed():
    ev = pr.client_evidence(EXPORT, True, pr.parse_log(DATA), DATA)
    assert ev.close_gap_s == pytest.approx(3645.065 - 3643.5)


def test_x1_a_dst_fall_back_pause_is_refused():
    """One telemetry line, then a pause of 3622 s real across the fall-back: the local stamps read 22 s apart."""
    lines = DATA.decode().split("\n")
    tel = [i for i, ln in enumerate(lines) if "Stream Telemetry" in ln]
    keep = tel[0]
    first = lines[keep]
    stamped = "2026-11-01 01:16:40,001" + first[23:]                      # 22 s (naive) before the close line's 01:17:02,001
    elapsed_first = float(first.split("elapsed=")[1].split("s")[0])
    new = [ln for i, ln in enumerate(lines) if i not in tel]
    at = [i for i, ln in enumerate(new) if "WARNING" in ln and "01:17:02,001" in ln]
    assert at, "fixture premise"
    new.insert(at[0], stamped)
    data = "\n".join(new).encode()
    ev = pr.client_evidence(EXPORT, True, pr.parse_log(data), data)
    assert ev.close_gap_s == pytest.approx(3645.065 - elapsed_first) and ev.close_gap_s > 3000
    not_ok(run(data=data), "client_abort_continuity")


def test_x1_a_gap_over_the_bound_fails_whatever_the_stamps_say():
    ev = pr.client_evidence(EXPORT, True, pr.parse_log(DATA), DATA)
    for gap in (121.0, -ev.close_gap_s - 6.0):
        not_ok(run(client=dataclasses.replace(ev, close_gap_s=gap)), "client_abort_continuity")
    assert run(client=dataclasses.replace(ev, close_gap_s=-4.9)).ok


def test_x1_wall_s_absent_gives_no_close_gap_and_fails():
    ex = copy.deepcopy(EXPORT)
    del _aborted(ex)["time"]["created"]
    ev = pr.client_evidence(ex, True, pr.parse_log(DATA), DATA)
    assert ev.close_gap_s is None
    not_ok(run(export=ex), "client_abort_continuity")
    assert pr.client_evidence(None, False, pr.parse_log(DATA), DATA).close_gap_s is None


def test_x1_the_completed_variant_uses_the_trailing_assistant_message():
    data, after = completed_variant()
    ev = pr.client_evidence(EXPORT, True, pr.parse_log(data), data)
    assert ev.close_gap_s == pytest.approx(3645.065 - 3643.5)
    r = run(data=data, after=after)
    assert r.ok and r.case == COMPLETED_CASE


# -- X2: the export belongs to the row
def test_x2_a_foreign_export_fails_provenance():
    ex = copy.deepcopy(EXPORT)
    ex["info"]["id"] = "ses_someoneelse"
    not_ok(run(export=ex), "client_abort_provenance")


def test_x2_request_usage_ids_must_appear_in_the_exports_assistant_ids_in_order():
    ex = copy.deepcopy(EXPORT)
    asst = [m for m in ex["messages"] if m["type"] == "assistant"]
    asst[0]["id"], asst[1]["id"] = asst[1]["id"], asst[0]["id"]                  # order swapped
    not_ok(run(export=ex), "client_abort_provenance")
    ex2 = copy.deepcopy(EXPORT)
    [m for m in ex2["messages"] if m["type"] == "assistant"][0]["id"] = "msg_foreign"
    not_ok(run(export=ex2), "client_abort_provenance")
    row = copy.deepcopy(ROW)
    row["request_usage"][0][0] = "msg_not_in_export"
    not_ok(run(row=row), "client_abort_provenance")


def test_x2_the_aborted_message_itself_is_not_a_usage_message():
    row = copy.deepcopy(ROW)
    row["request_usage"][-1][0] = _aborted(EXPORT)["id"]
    not_ok(run(row=row), "client_abort_provenance")


# -- X3: validated times, no exception
def _times(**kw):
    t = dict(_aborted(EXPORT)["time"])
    for k, v in kw.items():
        if v is KeyError:
            del t[k]
        else:
            t[k] = v
    return t


@pytest.mark.parametrize("time", [
    _times(created=KeyError),
    _times(created="1793520977003"),
    _times(created=_aborted(EXPORT)["time"]["completed"] + 1),                   # reversed
    _times(created=_aborted(EXPORT)["time"]["created"] + 0.5),                   # float
    _times(created=True),
    _times(completed=None),
])
def test_x3_a_bad_created_or_completed_fails_provenance_without_an_exception(time):
    ex = copy.deepcopy(EXPORT)
    msg = _aborted(ex)
    msg["time"] = dict(time)
    r = run(export=ex)
    not_ok(r, "client_abort_provenance")
    assert r.client_abort is None


def test_x3_the_block_is_built_from_validated_values_only():
    r = run()
    assert r.ok and r.client_abort["wall_s"] == pytest.approx(3645.065)
    assert isinstance(r.client_abort["wall_s"], float)
