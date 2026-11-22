"""S29 frozen tests, H5: legs already recorded INVALID by the host change take the state their recorded facts give (spec
docs/specs/s29-record-not-block.md H5, "Resume trace", acceptance 1 "the a3 shape"; scope item 4: today `tg2-m76-x-s1.a3`).

The situation (the recorded a3): the leg's chain finished cleanly (`chain_rc` 0, chain.json finished, every item reconciled), the
host was upgraded during it, so `leg.json` says INVALID with a reason that starts `host environment changed during the leg` and
carries no `(prior: ...)`; the leg is NOT harvested (its harvest was refused). The sequencer is started again WITHOUT `--rerun`.

Classes: [FIX] reproduces a failure the spec fixes (today the resumed run stops: "is INVALID ... a rerun is an operator decision");
[INV] preserves an invariant; [NEW] exercises new behaviour.

Driver: the frozen B2 sequencer driver + `HostWorld` (see `s29_support.make_a3`, which writes the a3-shaped `leg.json` with the
sequencer's own sealing writer). The shared sequencer code is under test (tg1 roots stand in for the tg2 roots: the a3 shape is
the same; the fake chain writes tg1 ledgers).

ASSUMPTIONS (mechanism free): (1) the original `leg.json` is kept under SOME other name in the leg root, found by its bytes
(sha256 = the recorded original's), never by name; (2) "the record every consumer reads for the state" is `<leg root>/leg.json`
(what the sequencer, `p426_freeze.read_leg`, `p426_signals` and `p426_verify` read); (3) the host changes and the supersession
(the original's sha256) are found as text inside that record, never by field name; (4) on harvest the original's file must
match a harvest rule (`p426_harvest.classify`), because P6b would otherwise list it as unrecognised and NOT copy it."""
from __future__ import annotations

import json
from pathlib import Path

from bench import p426_freeze as fz
from bench import p426_harvest as H
from bench import p426_hooks as ph
from bench import p426_signals as SG
from bench import p426_verify as V
from bench.tests.s26_frozen import s26_support as X
from bench.tests.s29_frozen import s29_support as S

OFF_PILOT, ON_PILOT = S.OFF_PILOT, S.ON_PILOT
VIM = S.VIM_NEW


def snapshot_at_harvest(snaps):
    """`before=` hook: copy every file of the harvested leg root as the sequencer asks for its harvest."""
    def before(ops, clock):
        def seen(leg):
            root = Path(ops.harvested[-1])
            snaps.append(({k: v.read_bytes() for k, v in S.files_under(root).items()}, leg))
        ops.on_harvest = seen
    return before


# ---------------------------------------------------------------------------------------------------- the instrument
def test_inv_h5_the_consumer_checks_accept_a_plain_valid_leg(tmp_path, monkeypatch):
    """[INV] the instruments the H5 tests use (freeze, verify, signals readers) accept a plain VALID leg root of this driver, so a
    refusal in the H5 tests is the record's, not the fixture's."""
    r = X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT)
    root = r["base"] / f"{OFF_PILOT}.a1"
    assert consumers_see(r["base"], root, OFF_PILOT, "VALID") == []


def consumers_see(base, root, leg, state):
    """[problem] of the five consumers' view of one leg root: the sequencer's record, `p426_freeze.read_leg` /
    `valid_leg_problems`, `p426_verify` rule 1, `p426_signals` A7 coverage."""
    problems = []
    entry = [e for e in json.loads((base / "sequence.json").read_text())["legs"] if e["leg"] == leg][-1]
    if entry["state"] != state:
        problems.append(f"sequence.json says {entry['state']}")
    try:
        doc = fz.read_leg(root)
    except fz.Refusal as exc:
        return problems + [f"freeze read_leg: {exc}"]
    if doc.get("state") != state:
        problems.append(f"freeze: leg.json says {doc.get('state')}")
    if state == "VALID":
        problems += [f"freeze: {p}" for p in fz.valid_leg_problems(root, "off")]
    name = f"{leg}.a1"
    att = dict(leg=json.loads((root / "leg.json").read_text()), name=name)
    problems += [f"verify: {p}" for p in V._leg_reasons("off", att)] if state == "VALID" else []
    legs = {s: {arm: dict(name=f"tg1-p426-{arm}-{s}.a1", leg=ph.seal(dict(leg=f"tg1-p426-{arm}-{s}", attempt=1, state="VALID")))
                for arm in ("off", "on")} for s in V.SESSIONS}
    legs["pilot"]["off"] = att
    results = base.parent / "results-view"
    (results / V.WAVE).mkdir(parents=True, exist_ok=True)
    cov = SG._coverage(results, json.loads((base / "sequence.json").read_text()), legs,
                       {s: dict(accepted=True, reasons=[]) for s in V.SESSIONS})["A7"]
    mine = [d for d in cov["done"] + cov["rejected"] + cov["invalid"] + cov["pending"] if d["leg"] == leg and d["attempt"] == 1]
    if not mine or mine[0]["state"] != state:
        problems.append(f"signals: A7 says {mine[0]['state'] if mine else None}")
    problems += [f"signals: state mismatch {m}" for m in cov["state_mismatch"] if m["leg"] == name]
    return problems


# ---------------------------------------------------------------------------------------------------- the resume trace
def test_fix_h5_the_resumed_run_rederives_the_state_harvests_and_goes_on_to_the_next_leg(tmp_path, monkeypatch):
    """[FIX] the "Resume trace": `--rerun` NOT given; the latest attempt is INVALID with a host-only reason and unharvested -> its
    state is re-derived (VALID on its records) -> it is harvested -> `after_leg` -> the next leg launches. No new attempt of the
    re-derived leg is launched; the rerun list stays empty."""
    a3 = S.make_a3(tmp_path, monkeypatch)
    r = S.resume(tmp_path, monkeypatch, a3, through=ON_PILOT)
    assert r["rc"] == 0, r["err"]
    assert X.legs_run(r) == [ON_PILOT], "the leg is re-derived, not rerun; only the next leg launches"
    e = S.entry_of(r, OFF_PILOT)
    assert e["state"] == "VALID"
    assert any(h["attempt"] == f"{OFF_PILOT}.a1" for h in X.sequence(r)["harvested"])
    assert r["ops"].harvested[0] == str(a3["root"])
    assert X.sequence(r)["reruns"] == []
    assert not [e for e in X.sequence(r)["legs"] if e["leg"] == OFF_PILOT and e["attempt"] == 2]
    assert "STOP" not in X.seq_log(r)
    assert X.leg_json(r, ON_PILOT)["state"] == "VALID"


def test_new_h5_the_rederived_record_has_the_new_state_the_host_changes_and_the_supersession_and_verifies(tmp_path, monkeypatch):
    """[NEW] H5 invariants on the record every consumer reads: state VALID / class valid / reason "" (what `classify_leg` gives for
    the recorded chain), the host changes the original recorded, the C384 supersession naming the ORIGINAL's sha256, and a seal that
    verifies."""
    a3 = S.make_a3(tmp_path, monkeypatch)
    r = S.resume(tmp_path, monkeypatch, a3)
    assert r["rc"] == 0, r["err"]
    doc = json.loads((a3["root"] / "leg.json").read_text())
    assert ph.sealed_ok(doc)
    assert (doc["state"], doc["class"], doc["reason"]) == ("VALID", "valid", "")
    assert doc["leg"] == OFF_PILOT and doc["attempt"] == 1
    text = json.dumps(doc)
    assert VIM in text and "9.2.1373" in text, "the host changes of the original are not in the record"
    assert a3["orig_sha"] in text, "the supersession does not name the original's sha256"
    assert "C384" in text, "the supersession does not say which decision superseded the state"


def test_new_h5_the_original_sealed_leg_json_is_kept_byte_identical_and_is_harvestable(tmp_path, monkeypatch):
    """[NEW] H5: "the original sealed `leg.json` is kept byte-identical and harvested": some other file of the leg root holds exactly
    the original bytes (the a3's), it is there when the harvest is asked for, and the harvest has a rule that COPIES it (a file no
    rule matches is only listed, P6b)."""
    a3 = S.make_a3(tmp_path, monkeypatch)
    seen = []
    r = S.resume(tmp_path, monkeypatch, a3, before=snapshot_at_harvest(seen))
    assert r["rc"] == 0, r["err"]
    kept = [rel for rel, p in S.files_under(a3["root"]).items() if rel != "leg.json" and p.read_bytes() == a3["orig_bytes"]]
    assert len(kept) == 1, f"the original leg.json is not kept byte-identical under another name: {sorted(S.files_under(a3['root']))}"
    assert seen and kept[0] in seen[0][0] and seen[0][0][kept[0]] == a3["orig_bytes"]
    rule = H.classify("leg", kept[0])
    assert rule is not None and rule[0] in ("main", "evidence"), f"no harvest rule copies {kept[0]}"


def test_new_h5_every_consumer_sees_the_new_state(tmp_path, monkeypatch):
    """[NEW] H5: the sequencer (`sequence.json`), harvest's leg state, `p426_freeze`, B8 `p426_verify` rule 1 and `p426_signals` A7
    coverage all read VALID, with no state mismatch between `leg.json` and `sequence.json`."""
    a3 = S.make_a3(tmp_path, monkeypatch)
    r = S.resume(tmp_path, monkeypatch, a3)
    assert r["rc"] == 0, r["err"]
    assert consumers_see(a3["base"], a3["root"], OFF_PILOT, "VALID") == []


def test_inv_h5_the_run_baseline_is_not_rewritten(tmp_path, monkeypatch):
    """[INV] "the run's baseline stays the first-check baseline": a re-derivation leaves `host_env.json` byte-identical."""
    a3 = S.make_a3(tmp_path, monkeypatch)
    assert S.resume(tmp_path, monkeypatch, a3)["rc"] == 0
    assert (a3["base"] / "host_env.json").read_bytes() == a3["baseline_bytes"]


def test_inv_h5_a_second_resume_finds_the_leg_done_and_changes_nothing(tmp_path, monkeypatch):
    """[INV] idempotent: after the re-derivation, harvest and VALID entry, resuming again re-derives nothing (the leg record and the
    kept original are byte-identical, nothing is launched for the leg)."""
    a3 = S.make_a3(tmp_path, monkeypatch)
    assert S.resume(tmp_path, monkeypatch, a3)["rc"] == 0
    before = {k: p.read_bytes() for k, p in S.files_under(a3["root"]).items()}
    r2 = S.resume(tmp_path, monkeypatch, a3)
    assert r2["rc"] == 0, r2["err"]
    assert {k: p.read_bytes() for k, p in S.files_under(a3["root"]).items()} == before
    assert X.legs_run(r2) == [] and r2["ops"].harvested == []


# ---------------------------------------------------------------------------------------------------- what stays as recorded
def assert_stopped_on_the_leg(r):
    """The run stopped on THE LEG (an operator decision about the attempt), not on the host: a host change is no reason to stop, so
    on a box whose host differs from the baseline the only stop is the leg's own INVALID state."""
    log = X.seq_log(r)
    assert f"{OFF_PILOT}.a1" in log, log
    assert "STOP: the host environment differs" not in log


def test_inv_h5_a_leg_with_a_prior_reason_is_left_as_recorded(tmp_path, monkeypatch):
    """[INV] a host reason that carries `(prior: ...)` was ALSO invalid for another reason: not re-derived; the sealed record, the
    sequence state and the files of the leg root are unchanged, nothing is launched; the operator decides (rc 1)."""
    a3 = S.make_a3(tmp_path, monkeypatch, reason_suffix=" (prior: chain rc 2, status 'finished')")
    before = {k: p.read_bytes() for k, p in S.files_under(a3["root"]).items()}
    r = S.resume(tmp_path, monkeypatch, a3)
    assert r["rc"] == 1 and X.legs_run(r) == []
    assert {k: p.read_bytes() for k, p in S.files_under(a3["root"]).items()} == before
    assert S.entry_of(r, OFF_PILOT)["state"] == "INVALID"
    assert (a3["root"] / "leg.json").read_bytes() == a3["orig_bytes"]
    assert_stopped_on_the_leg(r)


def test_inv_h5_a_harvested_leg_is_left_as_recorded(tmp_path, monkeypatch):
    """[INV] a leg whose harvest is recorded is final: its state is not re-derived (its HARVEST.json already names the state)."""
    a3 = S.make_a3(tmp_path, monkeypatch, harvested=True)
    before = {k: p.read_bytes() for k, p in S.files_under(a3["root"]).items()}
    r = S.resume(tmp_path, monkeypatch, a3)
    assert r["rc"] == 1 and X.legs_run(r) == []
    assert {k: p.read_bytes() for k, p in S.files_under(a3["root"]).items()} == before
    assert S.entry_of(r, OFF_PILOT)["state"] == "INVALID" and r["ops"].harvested == []
    assert_stopped_on_the_leg(r)


def test_inv_h5_a_reason_that_is_not_the_host_change_is_left_alone(tmp_path, monkeypatch):
    """[INV] only a reason that STARTS with the host phrase is re-derived: an INVALID leg for another reason stays as recorded."""
    a3 = S.make_a3(tmp_path, monkeypatch)
    root = a3["root"]
    doc = {k: v for k, v in json.loads((root / "leg.json").read_text()).items() if k != "sha256"}
    doc["reason"] = "chain rc 2, status 'finished'"
    (root / "leg.json").unlink()
    ph.write_exclusive(root / "leg.json", doc)
    raw = (root / "leg.json").read_bytes()
    r = S.resume(tmp_path, monkeypatch, a3)
    assert r["rc"] == 1 and X.legs_run(r) == []
    assert (root / "leg.json").read_bytes() == raw
    assert_stopped_on_the_leg(r)


# ---------------------------------------------------------------------------------------------------- the state is classify_leg's
def test_fix_h5_when_the_recorded_chain_is_not_clean_the_leg_stays_invalid_with_classify_legs_reason(tmp_path, monkeypatch):
    """[FIX] "failure path kept": the state comes from `classify_leg(root, recorded chain_rc, arm)`, not from the absence of a
    `(prior)`. A chain.json that is not finished classifies INVALID with its own reason; the host changes are recorded beside it,
    the original is kept, and the run does not go on (the operator decides)."""
    a3 = S.make_a3(tmp_path, monkeypatch, chain_status="aborted")
    r = S.resume(tmp_path, monkeypatch, a3)
    assert r["rc"] == 1 and X.legs_run(r) == []
    doc = json.loads((a3["root"] / "leg.json").read_text())
    assert ph.sealed_ok(doc)
    assert doc["state"] == "INVALID" and doc["class"] == "systemic"
    assert doc["reason"] == "chain rc 0, status 'aborted'", doc["reason"]
    assert VIM in json.dumps(doc) and a3["orig_sha"] in json.dumps(doc)
    assert S.entry_of(r, OFF_PILOT)["state"] == "INVALID"
    assert len([p for p in S.files_under(a3["root"]).values() if p.read_bytes() == a3["orig_bytes"]]) == 1


def test_fix_h5_the_recorded_overrun_flag_gives_the_overrun_state_when_the_chain_is_not_clean(tmp_path, monkeypatch):
    """[FIX] "(OVERRUN rule with the recorded `overrun`)": a recorded overrun whose chain is not cleanly finished is OVERRUN (the
    sequencer's existing rule for a deadline overrun), not INVALID."""
    a3 = S.make_a3(tmp_path, monkeypatch, chain_status="aborted", overrun=True)
    r = S.resume(tmp_path, monkeypatch, a3)
    assert r["rc"] != 0 and X.legs_run(r) == []
    assert json.loads((a3["root"] / "leg.json").read_text())["state"] == "OVERRUN"
    assert S.entry_of(r, OFF_PILOT)["state"] == "OVERRUN"
