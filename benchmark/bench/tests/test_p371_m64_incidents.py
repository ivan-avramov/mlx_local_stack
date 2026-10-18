"""P371 phase 3b parts 3, 6 (A6, A7, A9 incident layout): the `incident_retry` transport policy of the shared chain core on
the M64 configuration. A transport incident is classified (router + worker checked independently FIRST, then the client's
cause), requires the EXACT cleanup schema, validates the partial rows (`partial_incident`, accepted prefix), recovers (unload
+ reload, A4 per arm, cache reset, warm-up) and re-runs the same slot in a new `retry` invocation; a second incident in a
slot is a `transport_dnf` row in the sidecar and in chain.json; failed attempts' tokens are carried by the slot."""
from __future__ import annotations

import json

import pytest

from bench import chain_core as core
from bench import chain_rows as cr
from bench.tests.m64_support import (  # noqa: F401  (fixture: env)
    FAP, PICK1, PICK2, SMOKE, SMOKE3, arg, calls, chain_json, env, invocations, log_has, run, schedule)


def first_cell(env, lang="python", pick=PICK1, session="s1"):
    s = schedule(env)
    load = next(l for l in s["loads"] if l["pick"] == pick and l["session"] == session)
    return next(c for c in load["cells"] if c["lang"] == lang)


def rows_of(path):
    return [json.loads(x) for x in path.read_text().splitlines()]


def files(env, pick=PICK1, lang="python", kind="*"):
    return sorted((env["out"] / "s1").glob(f"{pick}.s1.oc_{lang}.L*.{kind}.a*.jsonl"))


def table(env):
    return cr.load_slots(chain_json(env), env["out"])


# ---------------------------------------------------------------- the first incident of a slot
def test_a_first_transport_failure_recovers_the_worker_and_retries_the_same_slot_in_a_new_invocation(env):
    plan = {"oc": [{"abort_after": 1, "cause": "server_error", "tokens": 700, "receipt_tokens": 650}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 0
    cj = chain_json(env)
    assert len(cj["incidents"]) == 1
    inc = cj["incidents"][0]
    assert inc["cause"] == "server_error" and inc["attempt"] == 1 and inc["load_gen"] == 0
    assert inc["output_tokens"] == 650 and inc["gate_output_tokens"] == 700 and inc["receipt_output_tokens"] == 650
    assert inc["slot"].startswith(FAP.epoch_for(["oc"]) + "|oc|" + PICK1 + "|s1|python|") and inc["item"] in inc["slot"]
    names = [c[0] for c in env["ops"].calls]
    i = names.index("unload")
    assert [n for n in names[i:i + 5]] == ["unload", "load", "a4_gate", "reset_cache_session", "warmup"]
    assert len(calls(env, "load")) == 3 and len(cj["block_workers"]) == 3        # PICK1 + its recovery reload, PICK2
    cell = first_cell(env)["blocks"][0]["items"]
    block, retry = files(env, kind="block")[0], files(env, kind="retry")[0]
    assert block.name.endswith("L0.block.a1.jsonl") and retry.name.endswith("L0.retry.a2.jsonl")
    first, second = rows_of(block), rows_of(retry)
    assert [r["id"] for r in first] == ["python/" + cell[0]] and [r["id"] for r in second] == ["python/" + n for n in cell[1:]]
    assert first[0]["worker_after"] != second[0]["worker_after"]
    inv = invocations(env)[:2]
    assert arg(inv[1]["argv"], "--items").split(",") == cell[1:] and arg(inv[1]["argv"], "--attempt") == "2"
    assert arg(inv[1]["argv"], "--out").endswith("L0.retry.a2.jsonl") and arg(inv[1]["argv"], "--expect-items") == ",".join(
        "python/" + n for n in cell[1:])
    recs = [r for r in cj["progress"]["invocations"] if r["file"].endswith(("L0.block.a1.jsonl", "L0.retry.a2.jsonl"))]
    assert [(r["phase"], r["status"]) for r in recs] == [("block", "partial_incident"), ("retry", "validated")]
    assert len(recs[0]["accepted_slots"]) == 1 and len(recs[0]["expected_slots"]) == 3 and recs[0]["sha256"]
    t = table(env)
    assert len(t.scored) == 16 and cj["dnf"] == [] and not t.running
    assert {s.source for s in t.scored.values()} == {"row"}


def test_the_recovery_runs_a4_for_every_arm_on_the_new_worker_and_records_each_receipt(env):
    plan = {"oc": [{"abort_after": 1, "cause": "server_error", "tokens": 1}, "normal"]}
    assert run(env, SMOKE3, plan=plan) == 0
    workers = chain_json(env)["progress"]["loads"][0]["workers"]
    assert [w["n"] for w in workers] == [0, 1] and all(set(w["a4_receipts"]) == {"oc", "pi", "dsh"} for w in workers)
    assert workers[0]["pid"] != workers[1]["pid"]
    a4 = [c for c in calls(env, "a4_gate")]
    assert len(a4) == 3 + 3 + 3                                                  # load 0, its recovery, load 1


def test_the_failed_attempts_tokens_are_carried_by_the_slot(env):
    plan = {"oc": [{"abort_after": 0, "cause": "dropped_stream", "tokens": 1234}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 0
    inc = chain_json(env)["incidents"][0]
    assert inc["output_tokens"] == 1234 and inc["cause"] == "dropped_stream"
    assert core.slot_tokens(chain_json(env), inc["slot"]) == 1234
    assert core.slot_tokens(chain_json(env), "nope") == 0


def test_an_incident_before_any_row_leaves_an_empty_partial_record_without_a_rows_file(env):
    plan = {"oc": [{"abort_after": 0, "cause": "connection", "tokens": 3}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 0
    rec = chain_json(env)["progress"]["invocations"][0]
    assert rec["status"] == "partial_incident" and rec["accepted_slots"] == [] and rec["sha256"] is None
    assert not (env["out"] / rec["file"]).exists() and len(table(env).scored) == 16


def test_the_accepted_prefix_of_an_incident_is_sha_checked_like_any_validated_invocation(env):
    plan = {"oc": [{"abort_after": 2, "cause": "server_error", "tokens": 5}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 0
    rec = chain_json(env)["progress"]["invocations"][0]
    path = env["out"] / rec["file"]
    assert len(rows_of(path)) == 2 and len(rec["accepted_slots"]) == 2
    path.write_text(path.read_text() + "\n")
    with pytest.raises(cr.ChainRowsError, match="sha256"):
        table(env)


def test_a_second_transport_failure_in_the_same_slot_is_a_strict_fail_row_with_both_incidents(env):
    plan = {"oc": [{"abort_after": 0, "cause": "server_error", "tokens": 100},
                   {"abort_after": 0, "cause": "connection", "tokens": 50}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 0
    cj = chain_json(env)
    assert [i["attempt"] for i in cj["incidents"]] == [1, 2] and len(cj["dnf"]) == 1
    row = cj["dnf"][0]
    assert row["nonconv_kind"] == "transport_dnf" and row["passed"] is False and row["synthetic"] is True
    assert [i["cause"] for i in row["incidents"]] == ["server_error", "connection"]
    assert row["failed_attempt_output_tokens"] == 150 and row["acc"] == 0 and row["converged"] is False
    assert core.validate_dnf_row(row, arm="oc", slot=row["slot"]) == []
    sidecar = env["out"] / "s1" / f"{PICK1}.s1.oc_python.dnf.jsonl"
    assert json.loads(sidecar.read_text()) == row
    t = table(env)
    assert t.scored[row["slot"]].source == "dnf" and len(t.scored) == 16
    ids = {r["id"] for f in files(env) for r in rows_of(f)}
    assert row["id"] not in ids and len(ids) == 3                                 # the DNF slot has no probe row
    assert core.slot_tokens(cj, row["slot"]) == 150


def test_a_drifted_dnf_sidecar_or_chain_json_copy_is_refused_by_the_loader(env):
    plan = {"oc": [{"abort_after": 0, "cause": "server_error", "tokens": 1}, {"abort_after": 0, "cause": "connection",
                                                                              "tokens": 1}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 0
    sidecar = env["out"] / "s1" / f"{PICK1}.s1.oc_python.dnf.jsonl"
    row = json.loads(sidecar.read_text())
    sidecar.write_text(json.dumps(dict(row, acc=1)) + "\n")
    with pytest.raises(cr.ChainRowsError, match="differs"):
        table(env)


def test_two_failures_in_different_slots_are_each_a_first_incident_not_a_dnf(env):
    plan = {"oc": [{"abort_after": 1, "cause": "server_error", "tokens": 1}, {"abort_after": 1, "cause": "server_error",
                                                                              "tokens": 1}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 0
    cj = chain_json(env)
    items = first_cell(env)["blocks"][0]["items"]
    assert [i["item"] for i in cj["incidents"]] == [items[1], items[2]] and [i["attempt"] for i in cj["incidents"]] == [1, 1]
    assert cj["dnf"] == [] and len(table(env).scored) == 16


def test_two_arms_failing_on_the_same_item_are_two_slots_each_with_its_own_attempt_count(env):
    plan = {"oc": [{"abort_after": 0, "cause": "server_error", "tokens": 1}, "normal"],
            "pi": [{"abort_after": 0, "cause": "server_error", "tokens": 1}, "normal"]}
    assert run(env, ["chain", "s1", "--smoke", "--arms", "oc,pi", "--probe-code-sha", "oc=" + "9" * 64,
                     "--probe-code-sha", "pi=" + "9" * 64], plan=plan) == 0
    cj = chain_json(env)
    slots = [i["slot"] for i in cj["incidents"]]
    assert len(slots) == 2 and len(set(slots)) == 2 and all(i["attempt"] == 1 for i in cj["incidents"]) and cj["dnf"] == []


def test_slot_identity_keys_epoch_arm_pick_session_language_and_item():
    key = core.slot_key("e" * 64, "oc", PICK1, "s1", "python", "p01")
    assert key == "|".join(("e" * 64, "oc", PICK1, "s1", "python", "p01"))
    assert core.slot_key("e" * 64, "pi", PICK1, "s1", "python", "p01") != key
    assert core.slot_key("e" * 64, "oc", PICK2, "s1", "python", "p01") != key


# ---------------------------------------------------------------- A6: classification
def test_a_failure_with_no_classifiable_cause_and_a_healthy_router_and_worker_is_not_an_incident(env):
    plan = {"oc": [{"abort_after": 1, "cause": None, "tokens": 5}]}
    rc = run(env, SMOKE, plan=plan)
    assert rc == 2 and log_has(env, "RESTART block") and log_has(env, "incomplete twice")
    assert chain_json(env)["incidents"] == [] and (env["out"] / "s1" / "incomplete").is_dir()


def test_a_worker_crash_with_an_unrecognized_client_error_is_a_worker_crash(env):
    plan = {"oc": [{"abort_after": 1, "cause": None, "tokens": 9, "kill_worker": True}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 0
    inc = chain_json(env)["incidents"]
    assert [i["cause"] for i in inc] == ["worker_crash"] and inc[0]["output_tokens"] == 9


def test_a_dead_router_is_a_router_error_even_with_a_recognized_client_cause(env):
    plan = {"oc": [{"abort_after": 1, "cause": "server_error", "tokens": 1, "kill_router": True}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 0
    assert [i["cause"] for i in chain_json(env)["incidents"]] == ["router_error"]
    assert env["ops"].restarts == 1 and calls(env, "restart_router")


def test_a_router_error_without_a_router_restart_is_an_operator_action_and_aborts(env):
    env["ops"].restart_router = None
    plan = {"oc": [{"abort_after": 1, "cause": "server_error", "tokens": 1, "kill_router": True}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 2
    assert log_has(env, "router") and [i["cause"] for i in chain_json(env)["incidents"]] == ["router_error"]


def test_the_router_and_worker_checks_run_before_the_clients_cause_is_believed(env):
    plan = {"oc": [{"abort_after": 1, "cause": "connection", "tokens": 1, "kill_worker": True}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 0
    assert [i["cause"] for i in chain_json(env)["incidents"]] == ["worker_crash"]


def test_a_client_timeout_cause_is_an_incident(env):
    plan = {"oc": [{"abort_after": 0, "cause": "client_timeout", "tokens": 0}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 0
    assert [i["cause"] for i in chain_json(env)["incidents"]] == ["client_timeout"]


@pytest.mark.parametrize("cause,idle,worker,router,want", [
    ("server_error", False, True, True, "server_error"),
    ("connection", False, True, True, "connection"),
    ("dropped_stream", False, True, True, "dropped_stream"),
    ("timeout", False, True, True, "timeout"),
    (None, True, True, True, "client_timeout"),                  # an idle-cancelled (hung) probe is a client timeout
    (None, False, True, True, None),                             # both healthy and no cause: not transport
    ("not_a_cause", False, True, True, None),                    # an unknown stamp cause is no cause
    (None, False, False, True, "worker_crash"),                  # the worker is gone / replaced: whatever the client said
    ("server_error", False, False, True, "worker_crash"),
    (None, False, True, False, "router_error"),
    ("server_error", False, True, False, "router_error"),
    ("worker_crash", False, True, True, "worker_crash"),         # the probe itself saw the worker replaced (receipts)
    (None, True, False, True, "worker_crash"),
])
def test_the_classification_truth_table(cause, idle, worker, router, want):
    assert core.classify_incident_cause(stamp_cause=cause, cancelled_idle=idle, worker_ok=worker, router_ok=router) == want


# ---------------------------------------------------------------- A7: the exact cleanup schema
@pytest.mark.parametrize("variant", ["incomplete", "unknown", "orphans", "extra", "missing", "none", "uncertain"])
def test_an_incident_without_the_exact_cleanup_schema_aborts_the_chain_with_a_listing(env, variant):
    plan = {"oc": [{"abort_after": 1, "cause": "server_error", "tokens": 1, "cleanup": variant}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 2
    assert log_has(env, "incident refused") and log_has(env, "cleanup")
    assert len(invocations(env)) == 1 and len(calls(env, "load")) == 1 and chain_json(env)["incidents"] == []
    assert env["ops"].leftover_calls                                             # the listing, never a kill


def test_the_exact_clean_schema_is_accepted(env):
    plan = {"oc": [{"abort_after": 1, "cause": "server_error", "tokens": 1}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 0 and len(chain_json(env)["incidents"]) == 1


def test_the_fake_cleanup_receipt_is_the_real_process_guards_exact_key_set():
    from bench import proc_guard as pg
    guard = pg.ProcessGuard.__new__(pg.ProcessGuard)
    guard._status, guard.containers, guard.orphans_unattributed = None, set(), []
    assert set(guard.status()) == set(FAP.cleanup_status()) == set(core.CLEANUP_KEYS)


def test_a_partial_row_that_disagrees_with_its_manifest_refuses_the_incident(env):
    plan = {"oc": [{"abort_after": 1, "cause": "server_error", "tokens": 1, "row_snapshot": "c" * 64}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 2
    assert log_has(env, "incident refused") and log_has(env, "snapshot_sha256")
    assert chain_json(env)["incidents"] == []
