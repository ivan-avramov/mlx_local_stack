"""M76 B4b-2 change review r1 (ledger `change-ledger-r1.md`): one red test per adopted finding (B1–B10, B14–B16).

`conform(w)` brings a frozen-suite `World` to the recorded facts the r1 fixes bind and the real records carry: the rows'
`sampler_seed` is `rowschema.sample_seed(id, 0, plan seed)` (B10) and the v8 record carries the invocation manifests' identity
(B4); every record that binds a changed file is re-hashed / re-sealed.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import time
from pathlib import Path

import pytest

from bench import chain_rows as cr
from bench import p426_hooks as ph
from bench import p426_signals as S
from bench import p426_verify as V
from bench import rowschema
from bench import schedules
from bench.tests import test_m76_b4b2_fe_support as W
from bench.tests.p613.a7world import dumps, sealed, sha_bytes

M76 = W.REPO / "benchmark" / "results" / "m76"


# ------------------------------------------------------------------------------------------------------------- helpers
def _rewrite_rows(w, arm, session, fn):
    """Apply `fn(row)` to every row of the attempt; re-hash each invocation record and re-seal each accounting sidecar."""
    att = w.adir(arm, session)
    chain = json.loads((att / "chain.json").read_text())
    for inv in chain["progress"]["invocations"]:
        f = att / inv["file"]
        rows = [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
        for r in rows:
            fn(r)
        f.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
        inv["sha256"] = sha_bytes(f.read_bytes())
        for r in rows:
            side = att / "items" / ph.record_name(w.slot(session, r["id"]), inv.get("rerun_index", 0), "accounting.json")
            if side.is_file():
                doc = json.loads(side.read_text())
                side.write_text(dumps(ph.seal(dict(doc, row_sha256=ph.row_sha256(r)))))
    (att / "chain.json").write_text(dumps(chain))


def _write_v8(w, **patch):
    v8 = json.loads(w.p(w.ns, "run", "v8_base.json").read_text())
    v8.pop("sha256", None)
    v8 = sealed(dict(v8, **patch))
    w.p(w.ns, "run", "v8_base.json").write_text(dumps(v8))
    w.v8 = v8
    for s in w.sessions:
        for arm in ("n16", "x"):
            w.edit_chain(arm, s, lambda d: d["frozen_record"].__setitem__("sha256", v8["sha256"]))
    w.publish_amendment()                    # S29 rule 3.6: the deciders run on the amendment binding this v8 base


def conform(w):
    rt = W.pinned_manifest("n16", "rust")["runtime"]
    _write_v8(w, probe_code_sha256=rt["probe_code_sha256"], scaffold_policy_sha256=rt["scaffold_policy_sha256"],
              generation_identity_sha256=rt["generation_identity_sha256"], tg2_image_id=rt["policy"]["corpus_identity"]["image"],
              grader_image_id=rt["policy"]["toolchain"]["grader_image_id"])
    for s in w.sessions:
        base = schedules.TG2_P426_LEGS[s][1]
        for arm in ("n16", "x"):
            _rewrite_rows(w, arm, s, lambda r: r.__setitem__("sampler_seed", rowschema.sample_seed(r["id"], 0, base)))
    return w


def world(tmp_path, **kw):
    kw.setdefault("sessions", ("pilot",))
    return conform(W.World(tmp_path, corpus="tg2", **kw))


def by_session(doc):
    return {p["pair"]: p for p in doc["pairs"]}


def a8(w):
    """B8-A8 with the base sha passed explicitly (the call form both candidates accept; B1's own tests use the short form)."""
    return V.verify_a8_kv(w.root, w.base_b8_sha())


def ids(session):
    return W.schedule_ids(W.tg2_schedule(session))


def test_conformed_world_is_accepted(tmp_path):
    rec = by_session(a8(world(tmp_path)))["pilot"]
    assert rec["accepted"], rec["reasons"]


# ------------------------------------------------------------------------------------------------------------- B1
def test_b1_verify_a8_kv_takes_the_base_b8_from_the_results_root(tmp_path):
    w = world(tmp_path)
    doc = V.verify_a8_kv(w.root)
    assert doc["base_b8_sha256"] == hashlib.sha256((w.root / "B8.json").read_bytes()).hexdigest()
    assert doc == V.verify_a8_kv(w.root, w.base_b8_sha())                  # the explicit value is a seam, same record


def test_b1_a_missing_b8_json_refuses(tmp_path):
    w = world(tmp_path)
    (w.root / "B8.json").unlink()
    with pytest.raises(V.RefusalError, match="B8.json"):
        V.verify_a8_kv(w.root)


# ------------------------------------------------------------------------------------------------------------- B2
def test_b2_a_transport_dnf_record_beside_a_row_refuses(tmp_path):
    w = world(tmp_path)
    rid = ids("pilot")[1]
    lang, item = rid.split("/", 1)
    w.edit_chain("x", "pilot", lambda d: d["p426_dnf"].append(dict(slot=w.slot("pilot", rid), item=item, session="pilot",
                                                                     language=lang, arm="x", pick=W.MODEL, attempt=1,
                                                                     abort=dict(cause="transport", error="x", evidence=None))))
    with pytest.raises(V.RefusalError, match="transport DNF"):
        a8(w)


def test_b2_a_rows_file_changed_after_validation_refuses(tmp_path):
    w = world(tmp_path)
    # r3 E3: the bytes change behind the invocation record (`World.edit_row` re-hashes the record since the v3 support)
    rid = ids("pilot")[1]
    f = next(f for f in sorted(w.adir("x", "pilot", "pilot").glob("*.jsonl"))
             if any(json.loads(x)["id"] == rid for x in f.read_text().splitlines() if x.strip()))
    rows = [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
    for r in rows:
        if r["id"] == rid:
            r["wall_s"] = 1.0
    f.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    with pytest.raises(V.RefusalError, match="sha256 differs"):
        a8(w)


def _hdnf_world(tmp_path):
    rid = ids("reload")[2]
    w = world(tmp_path, sessions=("reload",), hdnf={("x", "reload"): {rid: "harness_fault_dnf"}})
    return w, rid


def test_b2_a_chain_harness_dnf_record_differing_from_its_sidecar_refuses(tmp_path):
    w, rid = _hdnf_world(tmp_path)

    def edit(chain):                                    # the content changes, the recorded sha256 stays the sidecar's
        chain["p426_harness_dnf"][0]["reason"] = "another reason"
    w.edit_chain("x", "reload", edit)
    with pytest.raises(V.RefusalError, match="harness DNF sidecar"):
        a8(w)


def test_b2_a_harness_dnf_without_a_reason_refuses(tmp_path):
    w, rid = _hdnf_world(tmp_path)
    side = w.adir("x", "reload", "items", cr.slot_file(w.slot("reload", rid)) + ".harness_dnf.json")
    rec = ph.seal(dict(json.loads(side.read_text()), reason=""))
    side.write_text(dumps(rec))
    w.edit_chain("x", "reload", lambda d: d.__setitem__("p426_harness_dnf", [rec]))
    with pytest.raises(V.RefusalError, match="malformed"):
        a8(w)


# ------------------------------------------------------------------------------------------------------------- B3
def _rerun_world(tmp_path):
    rid = ids("reload")[0]                               # rust: the language's other four items stay in its main invocation
    w = world(tmp_path, sessions=("reload",), reruns={("x", "reload"): [rid]})
    att = w.adir("x", "reload")
    chain = json.loads((att / "chain.json").read_text())
    main = next(i for i in chain["progress"]["invocations"] if i["phase"] == "full" and i["leg_key"][1] == "rust")
    run = json.loads((att / main["manifest"]).read_text())["run_id"]
    for a in chain["progress"]["slot_attempts"]:
        if a["disposition"] == "harness_fault":
            a["invocation"] = main["file"]               # as chain_core records it (`p426_record_fault`)
    chain["progress"]["seen_run_ids"] = sorted(set(chain["progress"]["seen_run_ids"]) | {run})
    (att / "chain.json").write_text(dumps(chain))
    return w, rid, run


def test_b3_the_discarded_attempts_own_run_is_not_an_orphan(tmp_path):
    w, rid, run = _rerun_world(tmp_path)
    w.publish_extra_manifest("x", "reload", rid, run=run)
    rec = by_session(a8(w))["reload"]
    assert rec["accepted"], rec["reasons"]


def test_b3_another_seen_run_of_a_discarded_slot_is_an_orphan(tmp_path):
    w, rid, _run = _rerun_world(tmp_path)
    other = w.runs[("x", "reload", "javascript")]        # in seen_run_ids, but not this slot's discarded attempt
    w.publish_extra_manifest("x", "reload", rid, run=other)
    rec = by_session(a8(w))["reload"]
    assert not rec["accepted"] and any("orphan" in r for r in rec["reasons"]), rec["reasons"]


# ------------------------------------------------------------------------------------------------------------- B4
@pytest.mark.parametrize("key", ["probe_code_sha256", "scaffold_policy_sha256", "generation_identity_sha256", "tg2_image_id",
                                 "grader_image_id"])
def test_b4_a_leg_not_carrying_the_v8_identity_is_rejected(key, tmp_path):
    w = world(tmp_path)
    _write_v8(w, **{key: "sha256:" + "0" * 64 if "image" in key else "0" * 64})
    rec = by_session(a8(w))["pilot"]
    assert not rec["accepted"] and any(f"v8_base {key}" in r for r in rec["reasons"]), rec["reasons"]


@pytest.mark.parametrize("key", ["tg2_draw_sha256", "tg2_universe_sha256"])
def test_b4_a_v8_whose_tg2_pins_are_not_the_committed_ones_is_rejected(key, tmp_path):
    w = world(tmp_path)
    _write_v8(w, **{key: "0" * 64})
    rec = by_session(a8(w))["pilot"]
    assert not rec["accepted"] and any(key in r for r in rec["reasons"]), rec["reasons"]


def test_b4_a_manifest_naming_another_model_is_rejected(tmp_path):
    w = world(tmp_path, manifest_hook=lambda arm, s, lang, m: dict(m, model="another-model"))
    conform(w)
    rec = by_session(a8(w))["pilot"]
    assert not rec["accepted"] and any("model 'another-model'" in r for r in rec["reasons"]), rec["reasons"]


# ------------------------------------------------------------------------------------------------------------- B5
def _acct_world(tmp_path):
    rid = ids("pilot")[1]
    return world(tmp_path, accounting={("x", "pilot"): [rid]}), rid


def test_b5_a_row_marker_contradicting_the_other_records_refuses(tmp_path):
    w = world(tmp_path)
    rid = ids("pilot")[1]                               # no slot state, ledger entry or sidecar says accounting fault
    _rewrite_rows(w, "x", "pilot", lambda r: r.__setitem__("accounting_fault", True) if r["id"] == rid else None)
    with pytest.raises(V.RefusalError, match="accounting-fault records disagree"):
        a8(w)


def test_b5_an_accounting_row_without_a_row_marker_stands_on_the_runners_records(tmp_path):
    w, rid = _acct_world(tmp_path)                      # the runner never writes a row marker (chain_core: slot, ledger, list)
    _rewrite_rows(w, "x", "pilot", lambda r: r.pop("accounting_fault", None) if r["id"] == rid else None)
    slot = w.slot("pilot", rid)
    w.edit_chain("x", "pilot", lambda d: d.__setitem__("p426_accounting_faults", [dict(
        slot=slot, rerun_index=0, sidecar=f"items/{ph.record_name(slot, 0, 'accounting.json')}")]))
    rec = by_session(a8(w))["pilot"]
    assert rec["accepted"] and rec["faults"]["x"]["accounting_faults"] == [rid], rec["reasons"]


def test_b5_the_chains_accounting_list_must_agree(tmp_path):
    w, rid = _acct_world(tmp_path)
    w.edit_chain("x", "pilot", lambda d: d.__setitem__("p426_accounting_faults", []))
    with pytest.raises(V.RefusalError, match="accounting-fault records disagree|accounting record is incomplete"):  # r3 E2
        a8(w)
    other = ids("pilot")[2]
    w.edit_chain("x", "pilot", lambda d: d.__setitem__("p426_accounting_faults", [
        dict(slot=s, rerun_index=0, sidecar=f"items/{ph.record_name(s, 0, 'accounting.json')}")
        for s in (w.slot("pilot", rid), w.slot("pilot", other))]))
    with pytest.raises(V.RefusalError, match="(disagree|no accounting-fault row|accounting record is incomplete)"):  # r3 E2
        a8(w)


def test_b5_an_accounting_slot_state_missing_refuses(tmp_path):
    w, rid = _acct_world(tmp_path)

    def edit(chain):
        for a in chain["progress"]["slot_attempts"]:
            a.pop("accounting_fault", None)
    w.edit_chain("x", "pilot", edit)
    with pytest.raises(V.RefusalError, match="accounting-fault records disagree"):
        a8(w)


def test_b5_an_orphan_accounting_sidecar_refuses(tmp_path):
    w = world(tmp_path)
    rid = ids("pilot")[2]
    slot = w.slot("pilot", rid)
    side = w.adir("x", "pilot", "items", ph.record_name(slot, 0, "accounting.json"))
    side.write_text(dumps(ph.seal(dict(slot=slot, rerun_index=0, row_sha256="0" * 64, item_record_sha256=None,
                                       failed_checks=["boundary_count"], disposition="accounting_fault"))))
    with pytest.raises(V.RefusalError, match="(orphan|no accounting-fault row|disagree)"):
        a8(w)


def test_b5_an_accounting_fault_marks_its_leg_speed_invalid():
    rec = dict(speed_valid=True, arms=["n16", "x"], legs={}, faults=dict(n16={}, x=dict(accounting_faults=["rust/a"])))
    assert any("accounting" in r for r in S._a8_speed_invalid(rec))


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    from bench.tests.test_m76_b4b2_fe_signals import Scenario

    def build(**kw):
        sc = Scenario(tmp_path, monkeypatch, with_a8=False, **kw)
        conform(sc.w)
        sc.rebuild()
        return sc
    return build


def test_b5_an_accounting_fault_row_leaves_the_runaway_tax(scenario):
    rid = ids("s1")[5]
    sc = scenario(accounting={("x", "s1"): [rid]},
                  outcomes={("x", "s1"): {rid: dict(passed=False, converged=False, nonconv_kind="budget_hit")}})
    sig, md = sc.sheet()
    tax = sig["axes"]["A8"]["tax"]["s1"]
    assert rid in tax["accounting_excluded"] and rid not in tax["x"]["union_items"]
    assert "runaway tax s1" in md
    assert "accounting fault" in json.dumps(sig["decode"]["A8"]["s1"]["speed_invalid"])


# ------------------------------------------------------------------------------------------------------------- B6
def test_b6_b8_json_is_written_when_b8_a8_refuses(tmp_path, monkeypatch):
    rows = tmp_path / "results"
    (rows / "m76").mkdir(parents=True)
    out = rows / "m76" / "B8.json"
    monkeypatch.setattr(V, "verify_all_kv", lambda *a, **k: {"stand_in": True})
    monkeypatch.setattr(V, "a8_applies", lambda root: True)

    def refuse(*a, **k):
        raise V.RefusalError("synthetic B8-A8 refusal")
    monkeypatch.setattr(V, "verify_a8_kv", refuse)
    rc = V.main(["--lever", "kv", "all", "--results-root", str(rows / "m76"), "--rows-root", str(rows), "--repo", str(tmp_path),
                 "--out", str(out), "--pair", "n16,x"])
    assert rc == 2
    assert out.read_text() == V.dumps({"stand_in": True}) and not (rows / "m76" / "B8-A8.json").exists()


# ------------------------------------------------------------------------------------------------------------- B7
@pytest.fixture
def new_york(monkeypatch):
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_b7_latency_times_are_utc_not_local(new_york):
    assert S._a8_time("2026-11-20T01:00:00Z") == calendar.timegm((2026, 11, 20, 1, 0, 0))


@pytest.mark.parametrize("bad", [dict(fresh_ms=-1.0), dict(repeat_ms="30"), dict(true_ms=float("inf")), dict(t="yesterday"),
                                 dict(threatlocker_cpu=True)])
def test_b7_a_latency_row_that_is_not_finite_non_negative_refuses(bad, tmp_path):
    w = world(tmp_path)
    w.write_latency(rows=[dict(dict(t="2026-11-20T00:00:00Z", fresh_ms=120.0, repeat_ms=30.0, true_ms=25.0,
                                    threatlocker_cpu=1.5), **bad)])
    with pytest.raises(V.RefusalError, match="exec_latency"):
        a8(w)


# ------------------------------------------------------------------------------------------------------------- B8
def test_b8_the_tg1_golden_allows_only_pinned_input_paths():
    from bench.tests import test_m76_b4b1_impl_golden_tg1 as G

    pinned = G.B4B2_CHANGED_INPUTS
    assert pinned and all(isinstance(p, str) and p.startswith(".b8.inputs.") and "*" not in p for p in pinned)


# ------------------------------------------------------------------------------------------------------------- B9
def test_b9_a_rejected_confirmatory_session_leaves_the_record_incomplete(tmp_path):
    w = W.World(tmp_path, corpus="tg2")
    w.write_rechecks(ack=True)
    conform(w)
    w.edit_chain("x", "s1", lambda d: d["frozen_record"].__setitem__("sha256", "f" * 64))
    doc = a8(w)
    got = by_session(doc)
    assert got["s1"]["accepted"] is False and got["s2"]["accepted"], got["s2"]["reasons"]
    assert doc["status"] == "incomplete"


# ------------------------------------------------------------------------------------------------------------- B10
def test_b10_a_row_seed_not_the_plans_rejects_the_session(tmp_path):
    w = world(tmp_path)
    rid = ids("pilot")[1]
    for arm in ("n16", "x"):                             # equal across the arms (pair_keys holds); only the plan binding fails
        _rewrite_rows(w, arm, "pilot", lambda r: r.__setitem__("sampler_seed", 12345) if r["id"] == rid else None)
    rec = by_session(a8(w))["pilot"]
    assert not rec["accepted"] and any("sampler_seed" in r and rid in r for r in rec["reasons"]), rec["reasons"]


def test_b10_the_real_pilot_rows_carry_the_plans_seeds():
    files = sorted((M76 / "wave2.tg2").glob("tg2-m76-*-pilot.a*/pilot/*.jsonl"))
    assert files
    for f in files:
        for row in cr.read_rows(f):
            assert row["sampler_seed"] == rowschema.sample_seed(row["id"], 0, schedules.TG2_P426_LEGS["pilot"][1]), f.name


# ------------------------------------------------------------------------------------------------------------- B14
def test_b14_check_b8_a8_takes_the_repo_root_explicitly(tmp_path):
    w = world(tmp_path)
    doc = a8(w)
    V.check_b8_a8(w.root.parent, doc, w.base_b8_sha(), V.STACK_REPO)
    empty = tmp_path / "empty-repo"
    empty.mkdir()
    with pytest.raises(V.RefusalError, match=r"repo input benchmark/m65/tg2_draw\.json is missing"):
        V.check_b8_a8(w.root.parent, doc, w.base_b8_sha(), empty)


# ------------------------------------------------------------------------------------------------------------- B15
def test_b15_v8_arms_other_than_the_pair_is_a_reason_not_inapplicable(tmp_path):
    w = world(tmp_path)
    _write_v8(w, arms=["x", "n16"])
    assert V.a8_applies(w.root)
    rec = by_session(a8(w))["pilot"]
    assert not rec["accepted"] and any("arms" in r for r in rec["reasons"]), rec["reasons"]


# ------------------------------------------------------------------------------------------------------------- B16
def test_b16_the_sheet_needs_b8_a8s_file_sha(scenario):
    sc = scenario(sessions=("pilot",))
    with pytest.raises(V.RefusalError, match="file sha256"):
        S.compute_kv(sc.rows, sc.b8, b8_sha256=sc.b8_sha, b8_a8=sc.doc)
    sig, _md = sc.sheet()
    assert sig["header"]["b8_a8_sha256"] == sc.doc_sha
