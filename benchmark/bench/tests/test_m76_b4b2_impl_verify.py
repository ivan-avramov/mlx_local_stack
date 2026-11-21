"""M76 B4b-2 B8-A8 (`p426_verify`): the axis table, A8 names / namespace / worktree guard, the per-row final-tree rule on both
axes, the plan binding, the S27 slot records (harness DNFs, reruns, accounting faults), PAUSED legs and partial deciders, the
re-check labels, the launch-latency record and the consumers' B8-A8 check (spec v1.5 §3, §5, §7.4, §9)."""
from __future__ import annotations

import json

import pytest

from bench import p426_hooks as ph
from bench import p426_verify as V
from bench.tests.test_m76_b3_impl_a7 import KVWorld
from bench.tests.test_m76_b4b2_impl_world import A8World, attempt, dumps, sealed, sha, slot_of

RUST = "rust/{}"


def first(w, s, lang="rust", n=0):
    return [i for i in w.ids(s) if i.startswith(lang + "/")][n]


# ------------------------------------------------------------------------------------------------ §3.1 axis table / names
def test_the_axis_table_names_both_wave2_axes():
    assert V.KV_AXES["A7"]["namespace"] == "wave2" and V.KV_AXES["A8"]["namespace"] == "wave2.tg2"
    assert V.KV_AXES["A7"]["corpus"] == "tg1" and V.KV_AXES["A8"]["corpus"] == "tg2"
    assert V.KV_AXES["A7"]["worktrees"] == ("m76-f45", "m76-q") and V.KV_AXES["A8"]["worktrees"] == ("m76-g2",)
    assert V.KV_AXES["A8"]["attempt_re"].match("tg2-m76-x-reload.a2")
    assert not V.KV_AXES["A8"]["attempt_re"].match("tg2-m76-v-s1.a1") and not V.KV_AXES["A8"]["attempt_re"].match("tg2-m76-x-s3.a1")


@pytest.mark.parametrize("name,axis", [("tg1-m76-n16-s1.a1", "A8"), ("tg2-m76-n16-s1.a1", "A7"), ("tg2-m76-n16-smoke.a1", "A8"),
                                       ("tg2-m76-n16-s1.a1/..", "A8")])
def test_a8_and_a7_member_names_never_cross(name, axis):
    with pytest.raises(V.RefusalError):
        V._kv_check_member(name, "w", ("n16", "x"), axis=axis)


def test_the_worktree_guard_takes_the_axis_prefix():
    """An A8 manifest naming the OTHER arm's `m76-g2-<arm>` worktree is a problem under A8's prefix; A7's guard (f45 / q) does
    not normalise `m76-g2` (its own outputs unchanged)."""
    from bench.tests.test_m76_b4b2_impl_world import manifest
    a, b = manifest("n16", "s1", "rust"), manifest("x", "s1", "rust")
    assert V.kv_provenance_problems(V.kv_normalise(a), V.kv_normalise(b), "n16", "x", ("m76-g2",)) == []
    b["runtime"]["worktree"] = "$STACK_WORKDIR/worktrees/m76-g2-n16"
    probs = V.kv_provenance_problems(V.kv_normalise(a), V.kv_normalise(b), "n16", "x", ("m76-g2",))
    assert any("another arm's worktree" in p for p in probs)
    assert V._kv_path_re("x").search("m76-g2-x") is None and V._kv_path_re("x", ("m76-g2",)).search("m76-g2-x")


def test_kv_normalise_is_corpus_neutral_and_keeps_the_a7_name():
    assert V.kv_a7_normalise is V.kv_normalise and V.kv_a7_provenance_reasons is V.kv_provenance_reasons


def test_a8_namespace_is_read(tmp_path):
    """A8 reads only `wave2.tg2/`: a stray `wave2/` directory is never touched; B8-A8's inputs are all wave2.tg2 files."""
    w = A8World(tmp_path, sessions=("pilot",))
    (w.root / "wave2").mkdir()
    doc = w.b8_a8()
    assert all(k.startswith("m76/wave2.tg2/") for k in doc["inputs"])


def test_b8_a8_is_built_only_for_the_tg2_kv_pair(tmp_path):
    w = A8World(tmp_path, sessions=("pilot",))
    assert V.a8_applies(w.root)
    # change review r1 B15: applicability is lever + corpus; other arms are a REASON on the record (§3.6), never "not applicable"
    v8 = dict(w.v8, arms=["x", "v"])
    (w.ns / "run" / "v8_base.json").write_text(dumps(sealed(v8)))
    assert V.a8_applies(w.root)
    assert any("arms" in r for r in w.by()[1]["pilot"]["reasons"])
    (w.ns / "run" / "v8_base.json").write_text(dumps(sealed(dict(w.v8, corpus="tg1"))))
    assert not V.a8_applies(w.root)
    with pytest.raises(V.RefusalError, match="not the tg2 KV pair"):
        w.b8_a8()
    assert not V.a8_applies(tmp_path / "nothing")


def test_kv_a8_sessions_come_from_b7s_plan():
    assert V.kv_a8_sessions() == ("s1", "s2")


# ------------------------------------------------------------------------------------------------ §3.3 per-row final tree (A8)
def _rejected_with(w, s, needle):
    _doc, by = w.by()
    assert by[s]["accepted"] is False and by[s]["status"] == "rejected"
    assert any(needle in r for r in by[s]["reasons"]), by[s]["reasons"]
    assert all(k["manifest_sha256"]["n16"] or k["manifest_sha256"]["x"] for k in by[s]["keys"])


def test_a8_missing_final_tree_block_is_a_reason(tmp_path):
    w = A8World(tmp_path, sessions=("pilot",))
    rid = w.ids("pilot")[0]
    w2 = A8World(tmp_path / "b", sessions=("pilot",), rows={("x", "pilot"): {rid: dict(final_tree=None)}})
    _rejected_with(w2, "pilot", "no final_tree.manifest")
    assert w.by()[1]["pilot"]["accepted"]


def test_a8_no_harvest_match_is_a_reason(tmp_path):
    w = A8World(tmp_path, sessions=("pilot",))
    h = w.harvest("n16", "pilot")
    h["files"] = h["files"][1:]
    w.put_harvest("n16", "pilot", h)
    _rejected_with(w, "pilot", "0 HARVEST main final-tree manifests")


def test_a8_two_harvest_matches_is_a_reason(tmp_path):
    w = A8World(tmp_path, sessions=("pilot",))
    h = w.harvest("x", "pilot")
    h["files"].append(dict(h["files"][0]))
    w.put_harvest("x", "pilot", h)
    _rejected_with(w, "pilot", "2 HARVEST main final-tree manifests")


def _orphan(w, arm, s, rid, run):
    lang, item = rid.split("/", 1)
    rel = f"wave2.tg2/{attempt(arm, s)}/evidence/{run}/{lang}__{item}.final_tree/manifest.json"
    p = w.root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dumps(dict(files={}, missing=["x"])))
    h = w.harvest(arm, s)
    h["files"].append(dict(destination="main", published=f"benchmark/results/m76/{rel}", published_sha256=sha(p.read_bytes()),
                           sha256=sha(p.read_bytes()), source="x", compression=None, exclusion_reason=None))
    w.put_harvest(arm, s, h)


def test_a8_orphan_manifest_is_a_reason(tmp_path):
    w = A8World(tmp_path, sessions=("pilot",))
    _orphan(w, "x", "pilot", w.ids("pilot")[1], "20261120T999999-other")
    _rejected_with(w, "pilot", "orphan")


def test_a8_a_discarded_rerun_run_is_never_an_orphan(tmp_path):
    w = A8World(tmp_path, sessions=("pilot",))
    rid = w.ids("pilot")[2]
    w2 = A8World(tmp_path / "b", sessions=("pilot",), rows={("x", "pilot"): {rid: dict(_rerun=True)}})
    # change review r1 B3: the faulted attempt's own run — the run id of the invocation its slot attempt names
    _orphan(w2, "x", "pilot", rid, f"run-x-pilot-{rid.split('/')[0]}")
    _doc, by = w2.by()
    assert by["pilot"]["accepted"], by["pilot"]["reasons"]
    assert w.by()[1]["pilot"]["accepted"]


def test_a8_all_dnf_attempt_passes_the_final_tree_rule(tmp_path):
    ids = A8World(tmp_path / "probe", sessions=("pilot",)).ids("pilot")
    dnf = {i: dict(_dnf="transport") for i in ids}
    w = A8World(tmp_path / "w", sessions=("pilot",), rows={("n16", "pilot"): dnf, ("x", "pilot"): dnf})
    _doc, by = w.by()
    assert by["pilot"]["accepted"], by["pilot"]["reasons"]
    assert by["pilot"]["faults"]["n16"]["transport_dnf"] == sorted(ids)


# ------------------------------------------------------------------------------------------------ §3.3 per-row final tree (A7)
def _a7_pairs(w):
    return {p["pair"]: p for p in V.verify_a7_kv(w.root, ("n16", "x"))["pairs"]}


def _a7_harvest(w, arm, s, fn):
    from bench.tests.p613.a7world import sealed as a7_sealed
    att = w.root / "wave2" / f"tg1-m76-{arm}-{s}.a1"
    h = json.loads((att / "HARVEST.json").read_text())
    fn(h)
    (att / "HARVEST.json").write_text(dumps(a7_sealed(h)))
    w.dossier(s)


def test_a7_missing_final_tree_block_is_a_reason(tmp_path):
    rid = "python/a1"
    w = KVWorld(tmp_path, rows={("x", "s2"): {rid: dict(final_tree={"files": {}})}})
    got = _a7_pairs(w)
    assert got["s2"]["accepted"] is False and any("no final_tree.manifest" in r for r in got["s2"]["reasons"])


def test_a7_no_match_and_two_matches_are_reasons(tmp_path):
    w = KVWorld(tmp_path)
    _a7_harvest(w, "n16", "s1", lambda h: h.update(files=h["files"][1:]))
    _a7_harvest(w, "x", "s2", lambda h: h["files"].append(dict(h["files"][0])))
    got = _a7_pairs(w)
    assert any("0 HARVEST main final-tree manifests" in r for r in got["s1"]["reasons"])
    assert any("2 HARVEST main final-tree manifests" in r for r in got["s2"]["reasons"])
    assert got["s3"]["accepted"]


def test_a7_orphan_is_a_reason(tmp_path):
    w = KVWorld(tmp_path)
    att = w.root / "wave2" / "tg1-m76-x-s3.a1"
    rel = "wave2/tg1-m76-x-s3.a1/evidence/20261114T999999-zzz/python__a1.final_tree/manifest.json"
    (w.root / rel).parent.mkdir(parents=True)
    (w.root / rel).write_text("{}\n")
    _a7_harvest(w, "x", "s3", lambda h: h["files"].append(dict(
        destination="main", published=f"benchmark/results/m76/{rel}", published_sha256=sha((w.root / rel).read_bytes()))))
    assert att.is_dir()
    got = _a7_pairs(w)
    assert any("orphan" in r for r in got["s3"]["reasons"])


def test_a7_rows_need_a_run_id_and_an_all_dnf_attempt_passes():
    att = dict(name="tg1-m76-x-s1.a1", rows={}, harvest=dict(files=[]), chain={})
    assert V.final_tree_reasons("x", att) == []                       # an all-DNF attempt (no row) passes
    att["rows"] = {"go/g1": dict(final_tree=dict(manifest="/x/manifest.json", manifest_sha256="0" * 64))}
    assert any("names no run directory" in r for r in V.final_tree_reasons("x", att))


# ------------------------------------------------------------------------------------------------ partial decider / PAUSED
def test_a_partial_decider_is_incomplete_not_a_refusal(tmp_path):
    w = A8World(tmp_path, sessions=("pilot", "s1"))
    doc, by = w.by()
    assert doc["status"] == "incomplete"
    assert by["s1"]["accepted"] and by["pilot"]["accepted"]
    assert by["s2"]["status"] == "incomplete" and "no pair record" in by["s2"]["reasons"][0]
    assert by["reload"]["status"] == "incomplete"
    assert doc["recheck"]["s1"]["status"] == "ok" and doc["recheck"]["s2"]["status"] == "incomplete"


def test_a_harvested_but_unpaired_session_is_incomplete(tmp_path):
    w = A8World(tmp_path, sessions=("pilot", "s1", "s2"), pairs=("pilot", "s1"))
    _doc, by = w.by()
    assert by["s2"]["status"] == "incomplete"


def test_a_paused_leg_is_incomplete(tmp_path):
    w = A8World(tmp_path, sessions=("pilot", "s1"))
    w.seq["legs"].append(dict(leg="tg2-m76-x-s2", attempt=1, state="PAUSED"))
    w.save_seq()
    doc, by = w.by()
    assert by["s2"]["status"] == "incomplete" and "PAUSED" in by["s2"]["reasons"][0] and doc["status"] == "incomplete"


def test_a_paused_leg_record_is_incomplete(tmp_path):
    w = A8World(tmp_path, sessions=("pilot",))
    p = w.att("x", "pilot") / "leg.json"
    p.write_text(dumps(sealed(dict(json.loads(p.read_text()), state="PAUSED"))))
    _doc, by = w.by()
    assert by["pilot"]["status"] == "incomplete" and "PAUSED" in by["pilot"]["reasons"][0]


def test_a_harvested_attempt_missing_its_schedule_refuses(tmp_path):
    w = A8World(tmp_path, sessions=("pilot",))
    (w.att("n16", "pilot") / "schedule.json").unlink()
    with pytest.raises(V.RefusalError, match="schedule.json"):
        w.b8_a8()


# ------------------------------------------------------------------------------------------------ §3.6 plan binding
def test_a_schedule_off_the_pinned_draw_rejects(tmp_path):
    w = A8World(tmp_path, sessions=("pilot",))
    for arm in ("n16", "x"):
        p = w.att(arm, "pilot") / "schedule.json"
        doc = json.loads(p.read_text())
        doc["blocks"][0]["seed_base"] = 7
        p.write_text(dumps(doc))
    _doc, by = w.by()
    assert any("rule 3.6" in r and "pinned tg2 draw" in r for r in by["pilot"]["reasons"])


@pytest.mark.parametrize("field,value,needle", [("tg2_leg", "s1", "tg2_leg"),
                                                ("frozen_record", {"sha256": "0" * 64}, "frozen_record.sha256")])
def test_the_chain_binding_rejects(tmp_path, field, value, needle):
    w = A8World(tmp_path, sessions=("pilot",))
    c = w.chain("x", "pilot")
    c[field] = value
    w.put_chain("x", "pilot", c)
    _doc, by = w.by()
    assert by["pilot"]["accepted"] is False and any(needle in r for r in by["pilot"]["reasons"])


def test_a_v8_record_that_does_not_verify_rejects_every_session(tmp_path):
    w = A8World(tmp_path, sessions=("pilot",))
    (w.ns / "run" / "v8_base.json").write_text(dumps(dict(w.v8, note="edited after sealing")))
    _doc, by = w.by()
    assert by["pilot"]["accepted"] is False and any("v8_base.json self-hash" in r for r in by["pilot"]["reasons"])


def test_the_reload_key_set_is_the_first_five_of_s1(tmp_path):
    w = A8World(tmp_path, sessions=("reload",))
    _doc, by = w.by()
    assert by["reload"]["accepted"], by["reload"]["reasons"]
    from bench.tests.test_m76_b4b2_impl_world import DRAW
    att = dict(name="tg2-m76-x-reload.a1", planned_ids=w.ids("s1")[:20])
    assert V._a8_reload_reasons({"x": att}, DRAW)


# ------------------------------------------------------------------------------------------------ §9.2 harness DNFs
def test_a_harness_dnf_is_a_dnf_slot(tmp_path):
    w = A8World(tmp_path, sessions=("pilot",))
    rid = w.ids("pilot")[0]
    w = A8World(tmp_path / "h", sessions=("pilot",), rows={("x", "pilot"): {rid: dict(_dnf="harness")}})
    _doc, by = w.by()
    assert by["pilot"]["accepted"], by["pilot"]["reasons"]
    assert by["pilot"]["faults"]["x"]["harness_dnf"] == [rid] and by["pilot"]["keys_accepted"] == 4


def test_a_harness_dnf_sidecar_mismatch_refuses(tmp_path):
    rid = A8World(tmp_path / "p", sessions=("pilot",)).ids("pilot")[0]
    w = A8World(tmp_path / "h", sessions=("pilot",), rows={("x", "pilot"): {rid: dict(_dnf="harness")}})
    from bench import chain_rows as cr
    side = w.att("x", "pilot") / "items" / f"{cr.slot_file(slot_of('pilot', rid))}.harness_dnf.json"
    side.write_text(dumps(ph.seal(dict(json.loads(side.read_text()), reason="edited"))))
    with pytest.raises(V.RefusalError, match="harness DNF sidecar"):
        w.b8_a8()


# ------------------------------------------------------------------------------------------------ §9.3 reruns
def test_a_rerun_slot_reads_its_accepted_attempt(tmp_path):
    rid = A8World(tmp_path / "p", sessions=("pilot",)).ids("pilot")[1]
    w = A8World(tmp_path / "r", sessions=("pilot",), rows={("n16", "pilot"): {rid: dict(_rerun=True, passed=False)}})
    _doc, by = w.by()
    assert by["pilot"]["accepted"], by["pilot"]["reasons"]
    assert by["pilot"]["faults"]["n16"]["reruns"] == [rid]
    att = V._a8_load_attempt(V.Reader(w.root), attempt("n16", "pilot"), "pilot", "t")
    assert att["slots"][rid]["index"] == 1 and att["rows"][rid]["passed"] is False
    assert att["row_files"][rid].endswith(".rerun.a1.jsonl") and att["items"][rid]["slot"] == slot_of("pilot", rid)


def test_a_slot_with_two_accepted_attempts_refuses(tmp_path):
    rid = A8World(tmp_path / "p", sessions=("pilot",)).ids("pilot")[1]
    w = A8World(tmp_path / "r", sessions=("pilot",), rows={("n16", "pilot"): {rid: dict(_rerun=True)}})
    c = w.chain("n16", "pilot")
    for a in c["progress"]["slot_attempts"]:
        if a["slot"] == slot_of("pilot", rid):
            a["disposition"] = "accepted"
    w.put_chain("n16", "pilot", c)
    # change review r1 B2: the one inventory authority (`chain_rows.load_slots`) refuses it
    with pytest.raises(V.RefusalError, match="earlier attempt of an accepted P426 slot is not a harness_fault"):
        w.b8_a8()


def test_an_earlier_attempt_without_a_reason_is_a_reason(tmp_path):
    rid = A8World(tmp_path / "p", sessions=("pilot",)).ids("pilot")[1]
    w = A8World(tmp_path / "r", sessions=("pilot",), rows={("n16", "pilot"): {rid: dict(_rerun=True)}})
    c = w.chain("n16", "pilot")
    for a in c["progress"]["slot_attempts"]:
        if a["slot"] == slot_of("pilot", rid) and a["disposition"] == "harness_fault":
            a["reason"] = ""
    w.put_chain("n16", "pilot", c)
    # change review r1 B2: `chain_rows.load_slots` (the one inventory authority) refuses a reason-less harness fault
    with pytest.raises(V.RefusalError, match="no recorded reason"):
        w.by()


# ------------------------------------------------------------------------------------------------ §9.4 accounting faults
def test_an_accounting_fault_keeps_its_outcome_and_is_listed(tmp_path):
    rid = A8World(tmp_path / "p", sessions=("pilot",)).ids("pilot")[3]
    w = A8World(tmp_path / "a", sessions=("pilot",), rows={("x", "pilot"): {rid: dict(_accounting=True, passed=False)}})
    _doc, by = w.by()
    assert by["pilot"]["accepted"], by["pilot"]["reasons"]
    assert by["pilot"]["faults"]["x"]["accounting_faults"] == [rid]
    att = V._a8_load_attempt(V.Reader(w.root), attempt("x", "pilot"), "pilot", "t")
    assert att["rows"][rid]["passed"] is False and att["accounting"][rid]["failed_checks"] == ["boundary_count"]


def test_an_accounting_sidecar_that_does_not_stand_refuses(tmp_path):
    rid = A8World(tmp_path / "p", sessions=("pilot",)).ids("pilot")[3]
    w = A8World(tmp_path / "a", sessions=("pilot",), rows={("x", "pilot"): {rid: dict(_accounting=True)}})
    side = w.att("x", "pilot") / "items" / ph.record_name(slot_of("pilot", rid), 0, "accounting.json")
    side.write_text(dumps(ph.seal(dict(json.loads(side.read_text()), row_sha256="0" * 64))))
    with pytest.raises(V.RefusalError, match="accounting-fault sidecar"):
        w.b8_a8()


# ------------------------------------------------------------------------------------------------ §9.1 tampered rows
def test_a_final_tampered_row_is_an_outcome_listed_with_its_receipt(tmp_path):
    rid = [i for i in A8World(tmp_path / "p", sessions=("pilot",)).ids("pilot") if i.startswith("javascript/")][0]
    gr = [dict(final=True, outcome="tampered", seq=2, boundary=4, artifacts={"receipt.json": {"path": "$STACK_WORKDIR/r",
                                                                                              "sha256": "e" * 64}})]
    w = A8World(tmp_path / "t", sessions=("pilot",), rows={("n16", "pilot"): {rid: dict(passed=False, grade_reports=gr)}})
    _doc, by = w.by()
    assert by["pilot"]["accepted"]
    assert by["pilot"]["tampered"]["n16"] == {rid: dict(seq=2, boundary=4, final=True, outcome="tampered",
                                                         artifacts={"receipt.json": "e" * 64})}


# ------------------------------------------------------------------------------------------------ §5 re-checks
def test_a_recheck_naming_a_superseded_attempt_refuses(tmp_path):
    w = A8World(tmp_path, sessions=("pilot", "s1"))
    w.recheck("s1", attempts={"n16": ["tg2-m76-n16-s1.a2"], "x": ["tg2-m76-x-s1.a1"]})
    w.save_seq()
    with pytest.raises(V.RefusalError, match="attempts"):
        w.b8_a8()


def test_an_outside_recheck_without_the_ack_refuses(tmp_path):
    w = A8World(tmp_path, sessions=("pilot", "s1"))
    w.recheck("s1", inside=False)
    w.save_seq()
    with pytest.raises(V.RefusalError, match="ack"):
        w.b8_a8()
    w.recheck("s1", inside=False, ack=True)
    w.save_seq()
    assert w.b8_a8()["recheck"]["s1"]["status"] == "ok"


def test_a_review_recheck_needs_the_ack_too(tmp_path):
    w = A8World(tmp_path, sessions=("pilot", "s1"))
    w.recheck("s1", review=True)
    w.save_seq()
    with pytest.raises(V.RefusalError, match="ack"):
        w.b8_a8()


@pytest.mark.parametrize("edit,needle", [("seq", "sequence.json records"), ("report", "simulation report"), ("seal", "sealed")])
def test_the_recheck_binding(tmp_path, edit, needle):
    w = A8World(tmp_path, sessions=("pilot", "s1"))
    if edit == "seq":
        w.seq["rechecks"]["s1"]["sha256"] = "0" * 64
    elif edit == "report":
        w.recheck("s1", report_sha="f" * 64)
    else:
        p = w.ns / "run" / "recheck-s1.json"
        p.write_text(dumps(dict(json.loads(p.read_text()), gate="s1", at="edited")))
    w.save_seq()
    with pytest.raises(V.RefusalError, match=needle):
        w.b8_a8()


def test_a_missing_recheck_s2_labels_only_that_recheck(tmp_path):
    w = A8World(tmp_path)
    (w.ns / "run" / "recheck-s2.json").unlink()
    doc = w.b8_a8()
    assert doc["status"] == "complete" and doc["recheck"]["s2"]["status"] == "incomplete"
    assert doc["recheck"]["s1"]["label"] == V.A8_RECHECK_LABEL


# ------------------------------------------------------------------------------------------------ §4.2 latency record
def test_the_latency_record(tmp_path):
    w = A8World(tmp_path, sessions=("pilot",))
    assert w.b8_a8()["latency"]["status"] == "incomplete"
    w.latency()
    lat = w.b8_a8()["latency"]
    assert lat["status"] == "present" and lat["rows"][0]["fresh_ms"] == 120.0
    assert "m76/wave2.tg2/run/exec_latency.json" in w.b8_a8()["inputs"]
    w.latency(seal=False)
    with pytest.raises(V.RefusalError, match="exec_latency"):
        w.b8_a8()


# ------------------------------------------------------------------------------------------------ §4.4 the consumers' check
def test_check_b8_a8_binds_the_base_b8_and_every_input(tmp_path):
    w = A8World(tmp_path, sessions=("pilot",))
    doc = w.b8_a8("c" * 64)
    rows_root = w.root.parent
    repo = V.STACK_REPO                                   # change review r1 B14: the repo root is passed explicitly
    V.check_b8_a8(rows_root, doc, "c" * 64, repo)
    with pytest.raises(V.RefusalError, match="another B8.json"):
        V.check_b8_a8(rows_root, doc, "d" * 64, repo)
    rel = next(k for k in doc["inputs"] if k.endswith("chain.json"))
    (rows_root / rel).write_text((rows_root / rel).read_text() + " ")
    with pytest.raises(V.RefusalError, match="changed"):
        V.check_b8_a8(rows_root, doc, "c" * 64, repo)


def test_b8_a8_needs_a_base_sha(tmp_path):
    w = A8World(tmp_path, sessions=("pilot",))
    # change review r1 B1: no explicit sha → the sha of `<results_root>/B8.json`; this world has none, so it refuses
    with pytest.raises(V.RefusalError, match="B8.json is missing"):
        V.verify_a8_kv(w.root, None)
    with pytest.raises(V.RefusalError, match="sha256 of the B8.json"):
        V.verify_a8_kv(w.root, "not-a-sha")
