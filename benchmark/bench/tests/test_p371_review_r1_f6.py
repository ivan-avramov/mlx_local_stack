"""P371 review r1 F6 (A12): an incident or a cancel on the CURRENT item before its row is committed still leaves that slot's
evidence. The probe's abort stamp carries the failing slot's evidence paths + sha256s; the chain extracts the web evidence of the
exported transcript (sha256 re-verified) or records `unavailable` + the reason, in the incident record and in the attempt."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bench import chain_hooks as ch
from bench.tests.m64_support import (  # noqa: F401  (fixture: env)
    PICK1, SMOKE, chain_json, env, log_has, run)
from bench.tests.test_p371_m64_hooks import Script, cell_items, slot


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve(env, portable):
    return Path(portable.replace("$STACK_WORKDIR", str(env["wd"])))


def test_an_incident_before_the_row_commit_extracts_the_web_evidence_of_the_failing_slots_transcript(env):
    plan = {"oc": [{"abort_after": 1, "cause": "server_error", "tokens": 5, "evidence": "export"}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 0
    inc = chain_json(env)["incidents"][0]
    items = cell_items(env)
    assert inc["item"] == items[1] and inc["evidence"]["id"] == "python/" + items[1]
    export = inc["evidence"]["files"]["export"]
    assert export["sha256"] == sha(resolve(env, export["path"]))
    web = inc["web_evidence"]
    assert web["count"] >= 1 and web["sha256"] == sha(web["path"].replace("$STACK_WORKDIR", str(env["wd"])))
    att = chain_json(env)["attempts"][0]
    assert att["abort_evidence"]["slot"] == inc["slot"] and att["abort_evidence"]["web_evidence"] == web


def test_an_incident_whose_transcript_was_never_exported_records_unavailable_with_the_reason(env):
    plan = {"oc": [{"abort_after": 1, "cause": "connection", "tokens": 5, "evidence": "none"}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 0
    inc = chain_json(env)["incidents"][0]
    assert inc["web_evidence"] == dict(web_evidence="unavailable", reason="no transcript")
    assert inc["evidence"]["files"]["export"]["sha256"] is None


def test_an_abort_stamp_without_evidence_is_recorded_unavailable_never_silent(env):
    plan = {"oc": [{"abort_after": 1, "cause": "server_error", "tokens": 5}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 0
    inc = chain_json(env)["incidents"][0]
    assert inc["evidence"] is None
    assert inc["web_evidence"]["web_evidence"] == "unavailable" and "stamp" in inc["web_evidence"]["reason"]


def test_a_cancel_before_the_row_commit_records_the_slots_evidence_state_in_the_attempt(env):
    items = cell_items(env)
    target = slot(items[1])

    def before(sl, n):
        if sl == target:
            (env["out"] / "STOP").write_text("stop\n")
        return ch.Disposition.accept()
    assert run(env, SMOKE, hooks=Script(before=before)) == 3
    att = [a for a in chain_json(env)["attempts"] if a.get("cancelled_item")][-1]
    assert att["cancelled_item"]["id"] == "python/" + items[1]
    ev = att["abort_evidence"]
    assert ev["slot"] == target and ev["web_evidence"]["web_evidence"] == "unavailable" and ev["web_evidence"]["reason"]


def test_a_slot_whose_row_was_committed_before_the_abort_is_covered_by_its_rows_evidence_not_extracted_twice(env):
    plan = {"oc": [{"abort_after": 1, "cause": "server_error", "tokens": 5, "evidence": "export",
                    "evidence_item": "committed"}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 0
    cj = chain_json(env)
    inc = cj["incidents"][0]
    assert inc["evidence"]["id"] == "python/" + cell_items(env)[0] and inc["web_evidence"] is None
    assert cj["attempts"][0]["abort_evidence"]["covered"] == "row"
    assert any(a["slot"] == slot(cell_items(env)[0]) for a in cj["progress"]["slot_attempts"])      # the barrier's record stands
