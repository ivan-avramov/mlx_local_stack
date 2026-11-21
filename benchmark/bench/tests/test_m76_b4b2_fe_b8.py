"""M76 B4b-2 (spec v1.5) — B8 / B8-A8 (`bench.p426_verify`): the per-row final-tree rule on both axes, the A8 axis table and guards, the
plan binding, partial deciders, provenance, re-check labels, and the S27 additions (harness DNFs, reruns, accounting faults, PAUSED).

Class of each test (comment above it): (a) reproduces a failure the spec fixes, (b) preserves an invariant, (c) new behaviour.
Interface assumptions (also in the report): `V.verify_a8_kv(results_root)` -> B8-A8 document with `pairs` (per-session records:
`pair`, `accepted`, `status`, `reasons`, `keys`), a document `status` ("complete" iff every confirmatory session is accepted),
`corpus`, `recheck`, `latency`, `base_b8_sha256`, `inputs`; `V.KV_AXES[axis]` has the keys named in spec §3.1. "Rejected" = the
session record `accepted is False` with a reason; "incomplete" = the session record `status == "incomplete"`, never a refusal.
"""
from __future__ import annotations

import hashlib
import json
import re

import pytest

from bench import p426_verify as V
from bench import schedules
from bench.tests import test_m76_b4b2_fe_support as W
from bench.tests.p613.a7world import dumps, sealed, sha_bytes

PAIR = ("n16", "x")


def A8(w):
    """The candidate's interface: `verify_a8_kv(results_root, base_b8_sha256, draw_path=None)` (p426_verify.py `verify_a8_kv`)."""
    return V.verify_a8_kv(w.root, w.base_b8_sha())


# ------------------------------------------------------------------------------------------------------------------ helpers
def verify(axis, w):
    return V.verify_a7_kv(w.root, PAIR) if axis == "A7" else A8(w)


def by_session(doc):
    return {p["pair"]: p for p in doc["pairs"]}


def outcome(fn):
    """('refused', exc) | ('record', doc): the spec says "rejects the session" in §3.6 and "refuses" in §9.7 for the same kind of fault."""
    try:
        return "record", fn()
    except V.RefusalError as exc:
        return "refused", exc


def assert_rejected(axis, w, session, pattern=None):
    kind, got = outcome(lambda: verify(axis, w))
    if kind == "refused":
        return
    rec = by_session(got)[session]
    assert rec["accepted"] is False, "the session was accepted"
    assert rec["reasons"], "rejected without a reason"
    if pattern:
        assert any(re.search(pattern, r, re.I) for r in rec["reasons"]), rec["reasons"]


def assert_rejected_in_record(fn, session="pilot", pattern=None):
    """§3.6: "any mismatch rejects the session" — the session record is `accepted False` with a matching reason; a refusal is a defect."""
    rec = by_session(fn())[session]
    assert rec["accepted"] is False and rec["status"] != "incomplete", rec["status"]
    assert any(re.search(pattern, r, re.I) for r in rec["reasons"]), rec["reasons"]


def assert_rejected_or_refused(fn, session="pilot", pattern=None):
    kind, got = outcome(fn)
    if kind == "record":
        rec = by_session(got)[session]
        assert rec["accepted"] is False and rec["reasons"]
        if pattern:
            assert any(re.search(pattern, r, re.I) for r in rec["reasons"]), rec["reasons"]


AXES = ("A7", "A8")


def make(axis, tmp_path, **kw):
    if axis == "A7":
        return W.World(tmp_path, corpus="tg1", **kw)
    return W.World(tmp_path, corpus="tg2", sessions=kw.pop("sessions", ("pilot",)), **kw)


def target(axis):
    """(session, a row id) of the session the per-row tests damage."""
    if axis == "A7":
        return "s1", "python/a2"
    return "pilot", W.schedule_ids(W.tg2_schedule("pilot"))[1]


def all_ids(axis):
    session, _ = target(axis)
    return list(W.TG1_ITEMS) if axis == "A7" else W.schedule_ids(W.tg2_schedule(session))


FINAL_TREE = r"final.?tree|manifest"


# ------------------------------------------------------------------------------------------- per-row final-tree rule (§3.3, §7.4)
# (b) a clean world is accepted and every key carries both manifest shas
@pytest.mark.parametrize("axis", AXES)
def test_clean_session_is_accepted_with_both_manifest_shas(axis, tmp_path):
    w = make(axis, tmp_path)
    session, _ = target(axis)
    rec = by_session(verify(axis, w))[session]
    assert rec["accepted"], rec["reasons"]
    assert rec["keys"] and all(k["manifest_sha256"][a] for k in rec["keys"] for a in PAIR)


# (a) a non-DNF row with no `final_tree` block is a REASON, never `identical: false` with null shas
@pytest.mark.parametrize("axis", AXES)
def test_row_without_final_tree_block_rejects_the_session(axis, tmp_path):
    session, rid = target(axis)
    w = make(axis, tmp_path)
    w.drop_final_tree_block("x", session, rid)
    assert_rejected(axis, w, session, FINAL_TREE)


# (a) the row names a manifest HARVEST never published (no match)
@pytest.mark.parametrize("axis", AXES)
def test_row_whose_manifest_was_not_published_rejects_the_session(axis, tmp_path):
    session, rid = target(axis)
    w = make(axis, tmp_path)
    w.unpublish_manifest("n16", session, rid)
    assert_rejected(axis, w, session, FINAL_TREE)


# (a) two HARVEST destination-main manifests for the row's run id and item (several matches)
@pytest.mark.parametrize("axis", AXES)
def test_two_published_manifests_for_one_row_reject_the_session(axis, tmp_path):
    session, rid = target(axis)
    w = make(axis, tmp_path)
    w.duplicate_harvest_entry("x", session, rid)
    assert_rejected(axis, w, session, FINAL_TREE)


# (a) the row's sha differs from the published one (the binding itself)
@pytest.mark.parametrize("axis", AXES)
def test_row_sha_differing_from_the_published_manifest_rejects_the_session(axis, tmp_path):
    session, rid = target(axis)
    w = make(axis, tmp_path)
    w.edit_row("x", session, rid, final_tree=dict(manifest=_manifest_path(w, "x", session, rid), manifest_sha256="d" * 64, files={},
                                                   missing=[]))
    assert_rejected(axis, w, session, FINAL_TREE)


def _manifest_path(w, arm, session, rid):
    lang, item = rid.split("/", 1)
    run = w.runs[(arm, session, lang)]
    fname = f"{W.MODEL}.{session}.opencode_{lang}.L0.full.a1"
    return f"$STACK_WORKDIR/opencode_transcripts/{W.MODEL}/{fname}.{run}/{lang}__{item}.final_tree/manifest.json"


# (a) a published manifest for an item that HAS a row, naming another run id, is an orphan
@pytest.mark.parametrize("axis", AXES)
def test_orphan_manifest_of_another_run_rejects_the_session(axis, tmp_path):
    session, rid = target(axis)
    w = make(axis, tmp_path)
    w.publish_extra_manifest("x", session, rid, run="20261120T000000-orphanrun0000")
    assert_rejected(axis, w, session, r"orphan|run")


# (c) ... unless the chain records that run id as a discarded rerun slot (slot_attempts harness_fault + seen_run_ids). A8 only: the
# S27 rerun-keyed records (`<slot>.r1.json`) exist on the tg2 identity; the tg1 (A7) tree has none.
def test_manifest_of_a_discarded_rerun_attempt_is_not_an_orphan(tmp_path):
    # B3: the discarded attempt's OWN run = the `run_id` of the manifest of the invocation the harness_fault attempt names. The
    # reload session (5 items / language) keeps the language's main invocation alive beside the rerun.
    session, rid = "reload", W.schedule_ids(W.tg2_schedule("reload"))[0]
    w = make("A8", tmp_path, sessions=("reload",), reruns={("x", session): [rid]})
    chain = json.loads(w.adir("x", session, "chain.json").read_text())
    fault = next(a for a in chain["progress"]["slot_attempts"] if a["disposition"] == "harness_fault")
    assert "invocation" in fault
    inv = next(i for i in chain["progress"]["invocations"] if i["file"] == fault["invocation"])
    faulted_run = json.loads(w.adir("x", session, inv["manifest"]).read_text())["run_id"]
    w.publish_extra_manifest("x", session, rid, run=faulted_run)
    rec = by_session(verify("A8", w))[session]
    assert rec["accepted"], rec["reasons"]


# (c) all-DNF attempt: DNF slots are exempt, the session pair is not rejected for want of manifests
@pytest.mark.parametrize("axis", AXES)
def test_all_dnf_attempt_passes_the_final_tree_rule(axis, tmp_path):
    session, _ = target(axis)
    w = make(axis, tmp_path, dnf={("x", session): all_ids(axis)})
    rec = by_session(verify(axis, w))[session]
    assert not [r for r in rec["reasons"] if re.search(FINAL_TREE, r, re.I)], rec["reasons"]
    assert rec["accepted"], rec["reasons"]


# (b) a DNF slot beside rows is exempt from the rule
@pytest.mark.parametrize("axis", AXES)
def test_a_dnf_slot_is_exempt(axis, tmp_path):
    # A8 uses the reload session (5 items per language): a pilot language has one item, and a language whose only slot is a DNF
    # has no rows file / provenance manifest (the A7 rule, which the candidate keeps), which is not what this test is about
    session, rid = target(axis) if axis == "A7" else ("reload", W.schedule_ids(W.tg2_schedule("reload"))[1])
    w = make(axis, tmp_path, dnf={("x", session): [rid]}, **({} if axis == "A7" else {"sessions": ("reload",)}))
    rec = by_session(verify(axis, w))[session]
    assert rec["accepted"], rec["reasons"]


# (b) A7's committed B8.json has no null manifest sha (the rule changes nothing it recorded)
def test_committed_b8_has_no_null_manifest_sha():
    doc = json.loads((W.REPO / "benchmark" / "results" / "m76" / "B8.json").read_text())
    found = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("manifest_sha256", "off_manifest_sha256", "on_manifest_sha256"):
                    found.append(v)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(doc["axes"]["A7"])
    nulls = [v for v in found if v is None or (isinstance(v, dict) and None in v.values())]
    assert found and not nulls


# ------------------------------------------------------------------------------------------- A8 axis table, names, guards (§3.1, §3.2)
# (c) the axis table carries both axes with the spec's fields
def test_axis_table_names_both_axes():
    ax = V.KV_AXES
    assert set(ax) >= {"A7", "A8"}
    assert ax["A7"]["namespace"] == "wave2" and ax["A7"]["corpus"] == "tg1"
    assert ax["A8"]["namespace"] == "wave2.tg2" and ax["A8"]["corpus"] == "tg2"

    def match(axis, name):
        pat = ax[axis]["attempt_re"]
        pat = re.compile(pat) if isinstance(pat, str) else pat
        return bool(pat.match(name))
    for arm in ("n16", "x"):
        for s in ("pilot", "s1", "s2", "reload"):
            assert match("A8", f"tg2-m76-{arm}-{s}.a1") and match("A8", f"tg2-m76-{arm}-{s}.a12")
    assert not match("A8", "tg2-m76-v-s1.a1") and not match("A8", "tg1-m76-n16-s1.a1") and not match("A8", "tg2-m76-n16-s3.a1")
    assert match("A7", "tg1-m76-v-s3.a1") and match("A7", "tg1-m76-n16-reload.a2") and not match("A7", "tg2-m76-n16-s1.a1")
    assert "m76-g2" in str(ax["A8"]["worktrees"]) and "m76-f45" in str(ax["A7"]["worktrees"]) and "m76-g2" not in str(ax["A7"]["worktrees"])


# (c) an A8 pair naming a tg1 attempt (or the V arm) is refused: the member-name guard is the axis'
@pytest.mark.parametrize("hit", ["tg1-m76-n16-pilot.a1", "tg2-m76-v-pilot.a1", "tg2-m76-n16-s3.a1", "tg2-m76-n16-pilot.a1/../x"])
def test_a8_refuses_a_member_name_outside_its_axis(hit, tmp_path):
    w = make("A8", tmp_path)
    seq = w.load("wave2.tg2", "run", "sequence.json")
    seq["pairs"][0]["n16"] = hit
    w.write_sequence(extra=dict(pairs=seq["pairs"]))
    with pytest.raises(V.RefusalError):
        A8(w)


# (b) A7 still refuses a tg2 attempt name (the A7 table is unchanged)
def test_a7_refuses_a_tg2_attempt_name(tmp_path):
    w = make("A7", tmp_path)
    seq = w.load("wave2", "run", "sequence.json")
    seq["pairs"][0]["n16"] = "tg2-m76-n16-s1.a1"
    w.write_sequence(extra=dict(pairs=seq["pairs"]))
    with pytest.raises(V.RefusalError):
        V.verify_a7_kv(w.root, PAIR)


def _with_note(own_arm_token):
    def hook(arm, session, lang, man):
        man = json.loads(json.dumps(man))
        man.setdefault("runtime", {})["probe_note"] = own_arm_token(arm)
        return man
    return hook


# (c) the foreign-worktree guard takes the axis' worktree prefix: the arm's OWN `m76-g2-<arm>` component is normalised ...
def test_a8_normalises_the_arms_own_g2_worktree(tmp_path):
    w = make("A8", tmp_path, manifest_hook=_with_note(lambda arm: f"$STACK_WORKDIR/worktrees/m76-g2-{arm}/main_models.yaml"))
    rec = by_session(A8(w))["pilot"]
    assert rec["accepted"], rec["reasons"]


# (c) ... and a manifest naming the OTHER arm's g2 worktree rejects the session
def test_a8_rejects_a_manifest_naming_the_other_arms_worktree(tmp_path):
    w = make("A8", tmp_path, manifest_hook=_with_note(lambda arm: "$STACK_WORKDIR/worktrees/m76-g2-n16/main_models.yaml"))
    assert_rejected("A8", w, "pilot", r"worktree|provenance")


# ------------------------------------------------------------------------------------------- provenance (§3.4)
def _set(path, value):
    def hook(arm, session, lang, man):
        if (arm, lang) != ("x", "java"):
            return man
        man = json.loads(json.dumps(man))
        d = man
        for k in path[:-1]:
            d = d[k]
        d[path[-1]] = value
        return man
    return hook


# (c) on the real tg2 pilot manifests the provenance passes: only the KV delta, the arm commit and per-invocation identity differ
def test_real_tg2_manifests_pass_provenance(tmp_path):
    rec = by_session(A8(make("A8", tmp_path)))["pilot"]
    assert rec["accepted"], rec["reasons"]
    assert not [r for r in rec["reasons"] if "provenance" in r]


# (c) no tg2-only key is allowed to differ between the arms
@pytest.mark.parametrize("path,value", [
    (("runtime", "policy", "corpus_identity", "draw_sha256"), "e" * 64),
    (("runtime", "policy", "grader_version"), "m65-tg2-v9"),
    (("runtime", "policy", "gate", "requests"), 151),
    (("runtime", "scaffold"), "opencode-v2-web-tg1"),
    (("sampling", "thinking_budget"), 40960),
    (("box",), "another-box"),
])
def test_a_tg2_only_key_differing_between_arms_rejects_the_session(path, value, tmp_path):
    w = make("A8", tmp_path, manifest_hook=_set(path, value))
    assert_rejected("A8", w, "pilot", r"provenance|differs|thinking")


# (c) a missing provenance manifest rejects the session
def test_a_missing_manifest_rejects_the_a8_session(tmp_path):
    w = make("A8", tmp_path)
    next((w.adir("x", "pilot", "pilot")).glob("*.manifest.json")).unlink()
    assert_rejected("A8", w, "pilot", r"provenance|manifest")


# (c) the corpus-neutral normaliser; the A7 spelling stays an alias with the same result
def test_kv_normalise_is_corpus_neutral_and_the_a7_alias_is_kept():
    n16, x = W.pinned_manifest("n16", "rust"), W.pinned_manifest("x", "rust")
    assert V.kv_a7_normalise(n16) == V.kv_normalise(n16)
    assert callable(V.kv_a7_provenance_reasons)
    a, b = V.kv_normalise(n16), V.kv_normalise(x)
    assert V.kv_provenance_problems(a, b, "n16", "x") == []
    for k in ("run_id", "worker", "router_history"):
        assert k not in a


# ------------------------------------------------------------------------------------------- the pair record, inputs, status (§3.2)
# (c) the document's own fields
def test_document_fields_and_inputs(tmp_path):
    w = make("A8", tmp_path)
    doc = A8(w)
    assert doc["corpus"] == "tg2" and doc["base_b8_sha256"] == w.base_b8_sha()
    assert doc["status"] == "incomplete"                                  # only the pilot exists
    for rel, sha in doc["inputs"].items():       # relative to results_root (as verify_a7_kv's) or to rows_root (`m76/` prefixed)
        path = w.root / rel if (w.root / rel).is_file() else w.root.parent / rel
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha, rel
    names = set(doc["inputs"])
    assert names & {"wave2.tg2/run/v8_base.json", "m76/wave2.tg2/run/v8_base.json"}
    assert names & {"wave2.tg2/run/sequence.json", "m76/wave2.tg2/run/sequence.json"}
    assert any(k.endswith("HARVEST.json") for k in doc["inputs"])
    assert doc["latency"] is not None


# (c) a partial decider (nothing of s1 / s2 / reload yet) is incomplete, never a refusal; the pilot stands accepted
def test_partial_decider_is_incomplete_not_a_refusal(tmp_path):
    got = by_session(A8(make("A8", tmp_path)))
    assert got["pilot"]["accepted"] and got["pilot"]["role"] == "diagnostic"
    for s in ("s1", "s2"):
        assert got[s]["status"] == "incomplete" and got[s]["accepted"] is False and got[s]["reasons"]
    assert got["reload"]["status"] == "incomplete"


# (c) a session whose pair record / harvested legs are missing while the other session stands: incomplete, the rest unaffected
def test_a_session_without_its_pair_record_is_incomplete(tmp_path):
    w = make("A8", tmp_path, sessions=("pilot", "reload"))
    seq = w.load("wave2.tg2", "run", "sequence.json")
    w.write_sequence(extra=dict(pairs=[p for p in seq["pairs"] if p["pair"] != "reload"]))
    got = by_session(A8(w))
    assert got["reload"]["status"] == "incomplete" and got["pilot"]["accepted"]


# (c) the interface the later steps read: `v8` must be the tg2 kv pair, else B8-A8 is not built
def test_a8_is_not_built_for_a_tg1_world(tmp_path):
    w = make("A7", tmp_path, root=tmp_path / "t1" / "m76")
    (w.root / "wave2.tg2" / "run").mkdir(parents=True)
    (w.root / "wave2.tg2" / "run" / "v8_base.json").write_text((w.root / "wave2" / "run" / "v8_base.json").read_text())
    (w.root / "wave2.tg2" / "run" / "sequence.json").write_text((w.root / "wave2" / "run" / "sequence.json").read_text())
    assert_refused_or_not_built(lambda: A8(w))


def assert_refused_or_not_built(fn):
    try:
        got = fn()
    except V.RefusalError:
        return
    assert got is None or all(p.get("accepted") is False for p in got["pairs"])


# (b) corrupted or contradictory records refuse (a harvested attempt that lacks its schedule / chain; an unreadable chain)
@pytest.mark.parametrize("victim", ["schedule.json", "chain.json"])
def test_a_harvested_attempt_missing_schedule_or_chain_refuses(victim, tmp_path):
    w = make("A8", tmp_path)
    w.adir("x", "pilot", victim).unlink()
    with pytest.raises(V.RefusalError):
        A8(w)


def test_an_unreadable_chain_refuses(tmp_path):
    w = make("A8", tmp_path)
    w.adir("n16", "pilot", "chain.json").write_text("{not json")
    with pytest.raises(V.RefusalError):
        A8(w)


# ------------------------------------------------------------------------------------------- plan binding (§3.6, C368 S1)
def _edit_both_schedules(w, fn, session="pilot"):
    for arm in PAIR:
        path = w.adir(arm, session, "schedule.json")
        doc = json.loads(path.read_text())
        fn(doc)
        path.write_text(dumps(doc))


# (c) a schedule that is not the pinned draw's prefix for the session is rejected (`TransportAbort` caught into a reason)
def test_schedule_not_the_pinned_draws_prefix_rejects_the_session(tmp_path):
    w = make("A8", tmp_path)

    def reseed(doc):          # the rows still match the planned slots; only the table differs from the pinned draw's
        doc["blocks"][0]["legs"][0]["seed_base"] = 7
        doc["blocks"][0]["seed_base"] = 7
    _edit_both_schedules(w, reseed)
    assert_rejected_in_record(lambda: A8(w), pattern=r"draw|schedule|tg2")


# (c) the schedule of another leg is not this session's
def test_schedule_of_another_leg_rejects_the_session(tmp_path):
    w = make("A8", tmp_path)
    _edit_both_schedules(w, lambda d: d.__setitem__("tg2_leg", "s1"))
    assert_rejected_in_record(lambda: A8(w), pattern=r"draw|schedule|leg|tg2")


# (c) chain.tg2_leg must be the session
def test_chain_tg2_leg_must_be_the_session(tmp_path):
    w = make("A8", tmp_path)
    w.edit_chain("x", "pilot", lambda d: d.__setitem__("tg2_leg", "s2"))
    assert_rejected_in_record(lambda: A8(w), pattern=r"tg2_leg|leg")


# (c) chain.frozen_record.sha256 must be v8's
def test_chain_frozen_record_must_be_the_v8_record(tmp_path):
    w = make("A8", tmp_path)
    w.edit_chain("n16", "pilot", lambda d: d["frozen_record"].__setitem__("sha256", "f" * 64))
    assert_rejected_in_record(lambda: A8(w), pattern=r"frozen")


# (c) v8.arms must be ["n16", "x"]
def test_v8_arms_must_be_n16_x(tmp_path):
    w = make("A8", tmp_path)
    v8 = json.loads(w.p("wave2.tg2", "run", "v8_base.json").read_text())
    v8["arms"] = ["x", "n16"]
    w.p("wave2.tg2", "run", "v8_base.json").write_text(dumps(sealed(v8)))
    # B15: `a8_applies` decides by corpus / lever only; a v8 whose arms are not (n16, x) is a REASON on the record (not a refusal)
    assert_rejected_in_record(lambda: A8(w), pattern=r"arms")


# (c) B2: rows are read through the chain's inventory: an unregistered rows file that holds rows refuses; an empty one is tolerated
def test_an_unregistered_rows_file_with_rows_refuses(tmp_path):
    w = make("A8", tmp_path, sessions=("reload",))
    src = next(w.adir("x", "reload", "reload").glob("*.jsonl"))
    (src.parent / "stray.L9.full.a1.jsonl").write_text(src.read_text())
    with pytest.raises(V.RefusalError):
        A8(w)


def test_an_unregistered_empty_rows_file_is_tolerated(tmp_path):
    w = make("A8", tmp_path, sessions=("reload",))
    d = w.adir("x", "reload", "reload")
    (d / "stray.L9.full.a1.jsonl").write_text("")
    src = next(d.glob("*.manifest.json"))                  # the provenance rule wants a manifest beside every rows file (A7's rule)
    (d / "stray.L9.full.a1.manifest.json").write_text(src.read_text())
    rec = by_session(A8(w))["reload"]
    assert rec["accepted"], rec["reasons"]


# (c) B4: a leg whose invocation manifest carries another probe-code identity than its sibling arm's / v8's is rejected
def test_a_manifest_with_another_probe_code_is_rejected(tmp_path):
    w = make("A8", tmp_path, manifest_hook=_set(("runtime", "probe_code_sha256"), "0" * 64))
    assert_rejected_in_record(lambda: A8(w), pattern=r"probe_code|provenance|identity")


# (c) B10: a row seed that is another session's plan seed (s2 rows carrying s1's) rejects that session only
def test_a_row_seed_from_another_sessions_plan_rejects_only_that_session(tmp_path):
    from bench import rowschema
    w = make("A8", tmp_path, sessions=("s1", "s2"))
    rid = W.schedule_ids(W.tg2_schedule("s2"))[3]
    for arm in PAIR:
        w.edit_row(arm, "s2", rid, sampler_seed=rowschema.sample_seed(rid, 0, W.SEED["s1"]))
    got = by_session(A8(w))
    assert got["s1"]["accepted"], got["s1"]["reasons"]
    assert got["s2"]["accepted"] is False and any("seed" in r for r in got["s2"]["reasons"]), got["s2"]["reasons"]


# (c) B9: the document is complete only when every confirmatory session is accepted
def test_a_rejected_confirmatory_session_leaves_the_document_incomplete(tmp_path):
    from bench import rowschema
    w = make("A8", tmp_path, sessions=("s1", "s2"))
    rid = W.schedule_ids(W.tg2_schedule("s2"))[3]
    for arm in PAIR:
        w.edit_row(arm, "s2", rid, sampler_seed=7)
    doc = A8(w)
    assert by_session(doc)["s2"]["accepted"] is False and doc["status"] == "incomplete"


# ------------------------------------------------------------------------------------------- re-check labels (§5)
def full_world(tmp_path, **kw):
    w = W.World(tmp_path, corpus="tg2", **kw)
    w.write_rechecks(ack=True)
    return w


@pytest.fixture(scope="module")
def clean_full(tmp_path_factory):
    w = full_world(tmp_path_factory.mktemp("a8clean"))
    return w, A8(w)


# (c) a complete decider: both confirmatory sessions accepted, the document complete, the re-check labelled (never a verdict)
def test_complete_decider_is_accepted(clean_full):
    w, doc = clean_full
    got = by_session(doc)
    assert doc["sessions"] == ["s1", "s2"] and doc["status"] == "complete"
    for s in ("s1", "s2"):
        assert got[s]["accepted"] and got[s]["role"] == "pair" and got[s]["keys_accepted"] == 80, got[s]["reasons"]
    assert got["pilot"]["role"] == "diagnostic" and got["reload"]["role"] == "diagnostic" and got["reload"]["accepted"]


def _recheck_differs(tmp_path, clean_full, mutate):
    w = full_world(tmp_path)
    mutate(w)
    kind, got = outcome(lambda: A8(w))
    return kind == "refused" or got["recheck"] != clean_full[1]["recheck"]


# (c) a missing re-check-s2 (sealed after the reload) makes only the re-check label incomplete
def test_missing_recheck_s2_makes_only_the_label_incomplete(tmp_path, clean_full):
    w = full_world(tmp_path)
    w.p("wave2.tg2", "run", "recheck-s2.json").unlink()
    seq = w.load("wave2.tg2", "run", "sequence.json")
    seq["rechecks"].pop("s2")
    w.write_sequence(extra=dict(rechecks=seq["rechecks"]))
    doc = A8(w)
    assert doc["status"] == "complete" and all(by_session(doc)[s]["accepted"] for s in ("s1", "s2"))
    assert doc["recheck"] != clean_full[1]["recheck"] and "incomplete" in json.dumps(doc["recheck"]).lower()


# (c) a re-check sealed over a superseded attempt (not B8-A8's selected attempts) is not accepted as this decider's
def test_recheck_over_a_superseded_attempt_is_not_the_selected_ones(tmp_path, clean_full):
    assert _recheck_differs(tmp_path, clean_full, lambda w: w.write_rechecks(
        ack=True, s1_attempts={"n16": ["tg2-m76-n16-s1.a2"], "x": ["tg2-m76-x-s1.a1"]}, gates=("s1",)))


# (c) an outside / operator-review s1 re-check without its recorded ack is not accepted
def test_outside_s1_recheck_without_ack_is_not_accepted(tmp_path, clean_full):
    assert _recheck_differs(tmp_path, clean_full, lambda w: w.write_rechecks(inside=False, ack=False))


# (c) a re-check document that does not verify as sealed is not accepted
def test_unsealed_recheck_is_not_accepted(tmp_path, clean_full):
    def tamper(w):
        p = w.p("wave2.tg2", "run", "recheck-s1.json")
        doc = json.loads(p.read_text())
        doc["recheck"]["inside"] = False
        p.write_text(dumps(doc))
    assert _recheck_differs(tmp_path, clean_full, tamper)


# (c) the sealed re-check's sha must be the one sequence.json records
def test_recheck_sha_must_match_sequence_json(tmp_path, clean_full):
    def tamper(w):
        seq = w.load("wave2.tg2", "run", "sequence.json")
        seq["rechecks"]["s1"]["sha256"] = "0" * 64
        w.write_sequence(extra=dict(rechecks=seq["rechecks"]))
    assert _recheck_differs(tmp_path, clean_full, tamper)


# ------------------------------------------------------------------------------------------- launch latency (§4.2)
# (c) absent -> `latency: incomplete`, descriptive only, never a refusal; present -> its sha is an input
def test_latency_absent_is_incomplete_and_present_is_an_input(tmp_path):
    w = make("A8", tmp_path)
    doc = A8(w)
    assert "incomplete" in json.dumps(doc["latency"]).lower() and not [k for k in doc["inputs"] if k.endswith("exec_latency.json")]
    w.write_latency()
    doc = A8(w)
    want = sha_bytes((w.root / "wave2.tg2/run/exec_latency.json").read_bytes())
    assert doc["inputs"].get("wave2.tg2/run/exec_latency.json", doc["inputs"].get("m76/wave2.tg2/run/exec_latency.json")) == want
    assert "incomplete" not in json.dumps(doc["latency"]).lower()


# ------------------------------------------------------------------------------------------- S27 additions (§9, §9.7)
def _pilot_ids():
    return W.schedule_ids(W.tg2_schedule("pilot"))


# (c) a harness DNF slot is a terminal record: the session is accepted, the DNF is counted per arm and session, and has no key manifest
@pytest.mark.parametrize("kind", ["harness_fault_dnf", "grade_fault"])
def test_harness_dnf_slot_is_accepted_and_counted(kind, tmp_path):
    ids = _reload_ids()                      # reload: 5 items per language, so the DNF leaves rows (and a manifest) in its language
    w = make("A8", tmp_path, sessions=("reload",), hdnf={("x", "reload"): {ids[2]: kind}})
    rec = by_session(A8(w))["reload"]
    assert rec["accepted"], rec["reasons"]
    assert W.mentions(W.without_keys(rec), ids[2]) or W.mentions(W.without_keys(rec), kind)


def _reload_ids():
    return W.schedule_ids(W.tg2_schedule("reload"))


# (c) a harness-DNF sidecar that differs from chain.json's record refuses
def test_harness_dnf_sidecar_mismatch_refuses(tmp_path):
    ids = _reload_ids()
    w = make("A8", tmp_path, sessions=("reload",), hdnf={("x", "reload"): {ids[2]: "harness_fault_dnf"}})
    from bench import chain_rows as cr
    from bench import p426_hooks as ph
    side = w.adir("x", "reload", "items", cr.slot_file(w.slot("reload", ids[2])) + ".harness_dnf.json")
    doc = json.loads(side.read_text())
    doc["reason"] = "a different reason"
    side.write_text(dumps(ph.seal(doc)))
    with pytest.raises(V.RefusalError):
        A8(w)


# (c) a missing harness-DNF sidecar refuses (the harvest's own rule)
def test_harness_dnf_without_its_sidecar_refuses(tmp_path):
    ids = _reload_ids()
    w = make("A8", tmp_path, sessions=("reload",), hdnf={("x", "reload"): {ids[2]: "grade_fault"}})
    from bench import chain_rows as cr
    w.adir("x", "reload", "items", cr.slot_file(w.slot("reload", ids[2])) + ".harness_dnf.json").unlink()
    with pytest.raises(V.RefusalError):
        A8(w)


# (c) a rerun slot reads its accepted attempt (rerun index 1); the rerun is listed per arm
def test_rerun_slot_reads_the_accepted_attempt_and_is_listed(tmp_path):
    ids = _pilot_ids()
    w = make("A8", tmp_path, reruns={("n16", "pilot"): [ids[0]]})
    rec = by_session(A8(w))["pilot"]
    assert rec["accepted"], rec["reasons"]
    assert W.mentions(W.without_keys(rec), ids[0])
    assert all(k["manifest_sha256"][a] for k in rec["keys"] for a in PAIR)


# (c) a slot with two accepted attempts refuses (or is a reason): never silently read
def test_slot_with_two_accepted_attempts_is_not_accepted(tmp_path):
    ids = _pilot_ids()
    w = make("A8", tmp_path, reruns={("n16", "pilot"): [ids[0]]})

    def two_accepted(chain):
        for a in chain["progress"]["slot_attempts"]:
            if a["slot"] == w.slot("pilot", ids[0]) and a["rerun_index"] == 0:
                a["disposition"] = "accepted"
    w.edit_chain("n16", "pilot", two_accepted)
    assert_rejected_or_refused(lambda: A8(w))


# (c) a slot whose earlier attempt is not a recorded harness fault is not accepted
def test_rerun_without_a_recorded_reason_is_not_accepted(tmp_path):
    ids = _pilot_ids()
    w = make("A8", tmp_path, reruns={("n16", "pilot"): [ids[0]]})

    def strip(chain):
        for a in chain["progress"]["slot_attempts"]:
            a.pop("reason", None)
    w.edit_chain("n16", "pilot", strip)
    assert_rejected_or_refused(lambda: A8(w))


# (c) an accounting-fault row keeps its outcome and is listed per arm; its sidecar goes through the shared validator
def test_accounting_fault_row_is_accepted_and_listed(tmp_path):
    ids = _pilot_ids()
    w = make("A8", tmp_path, accounting={("x", "pilot"): [ids[1]]})
    rec = by_session(A8(w))["pilot"]
    assert rec["accepted"], rec["reasons"]
    assert W.mentions(W.without_keys(rec), ids[1])


# (c) a sidecar naming another row fails `p426_hooks.accounting_problems`: refuse / reject
def test_accounting_sidecar_naming_another_row_is_not_accepted(tmp_path):
    ids = _pilot_ids()
    w = make("A8", tmp_path, accounting={("x", "pilot"): [ids[1]]})
    from bench import chain_rows as cr
    from bench import p426_hooks as ph
    side = w.adir("x", "pilot", "items", cr.slot_file(w.slot("pilot", ids[1])) + ".accounting.json")
    doc = json.loads(side.read_text())
    doc["row_sha256"] = "9" * 64
    side.write_text(dumps(ph.seal(doc)))
    assert_rejected_or_refused(lambda: A8(w))


# (c) an accounting-fault ledger entry without any sidecar is not accepted
def test_accounting_fault_without_sidecar_is_not_accepted(tmp_path):
    ids = _pilot_ids()
    w = make("A8", tmp_path, accounting={("x", "pilot"): [ids[1]]})
    from bench import chain_rows as cr
    w.adir("x", "pilot", "items", cr.slot_file(w.slot("pilot", ids[1])) + ".accounting.json").unlink()
    assert_rejected_or_refused(lambda: A8(w))


# (c) a PAUSED leg is never a result: the session is incomplete with the reason
@pytest.mark.parametrize("arm", PAIR)
def test_paused_leg_is_incomplete_never_a_result(arm, tmp_path):
    w = make("A8", tmp_path, legs={(arm, "pilot"): dict(state="PAUSED", speed_valid=False, speed_reason="paused")})
    doc = A8(w)
    rec = by_session(doc)["pilot"]
    assert rec["status"] == "incomplete" and rec["accepted"] is False
    assert any("PAUSED" in r for r in rec["reasons"]), rec["reasons"]


# (b) speed-invalid tiers (an ALERT / hold / accounting fault / watcher gap) leave quality alone: the session stays accepted
def test_speed_invalid_leg_keeps_the_session_accepted(tmp_path):
    w = make("A8", tmp_path, legs={("x", "pilot"): dict(speed_valid=False, speed_reason="ALERT: watcher gap")})
    rec = by_session(A8(w))["pilot"]
    assert rec["accepted"], rec["reasons"]
    assert rec["speed_valid"] is False and "power-invalid" in rec["labels"]
