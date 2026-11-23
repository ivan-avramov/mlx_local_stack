"""S29 (spec `docs/specs/s29-a8-frozen-record.md` v1.2) — B8-A8 rule 3.6 accepts the decider legs' frozen record (the amendment).

R1: a decider attempt (s1, s2, reload) naming the amendment's sha256 passes rule 3.6 when the amendment is sealed, valid, names this
v8 base and the byte sha256 of the pilot dossier the sequencer recorded in `sequence.json` (whether or not B8-A8 accepts the pilot
pair); the pilot still needs the v8 base. R2: anything else is a rule-3.6 REASON, never a crash — including (v1.2) a decider
attempt naming the v8 base. R3: the amendment is a hashed B8-A8 input. R4 (end-to-end, on a copy of the real records): complete, all four
pairs accepted.

Unit tests use the real `amendment.json` / `v8_base.json` / chain `frozen_record` blocks; tampered copies for R2.
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from bench import p426_hooks as ph
from bench import p426_verify as V

BENCH = Path(__file__).resolve().parents[2]
M76 = BENCH / "results" / "m76"
TG2 = M76 / "wave2.tg2"
RUN = TG2 / "run"
PILOT_DOSSIER = TG2 / "pairs" / "pilot__n16-a1__x-a1.json"
DECIDER = ("s1", "s2", "reload")
ATTEMPTS = {("n16", "pilot"): "tg2-m76-n16-pilot.a1", ("x", "pilot"): "tg2-m76-x-pilot.a1",
            ("n16", "s1"): "tg2-m76-n16-s1.a1", ("x", "s1"): "tg2-m76-x-s1.a3",
            ("n16", "s2"): "tg2-m76-n16-s2.a2", ("x", "s2"): "tg2-m76-x-s2.a1",
            ("n16", "reload"): "tg2-m76-n16-reload.a1", ("x", "reload"): "tg2-m76-x-reload.a1"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


@pytest.fixture(scope="module")
def real():
    v8, am = load(RUN / "v8_base.json"), load(RUN / "amendment.json")
    atts = {k: dict(name=n, chain=dict(frozen_record=load(TG2 / n / "chain.json")["frozen_record"])) for k, n in ATTEMPTS.items()}
    return dict(v8=v8, amendment=am, atts=atts, pilot_sha=sha(PILOT_DOSSIER))


def reasons(real, arm, session, amendment="real", pilot_sha="real", v8=None, frozen_sha=None):
    att = copy.deepcopy(real["atts"][(arm, session)])
    if frozen_sha is not None:
        att["chain"]["frozen_record"]["sha256"] = frozen_sha
    am = real["amendment"] if amendment == "real" else amendment
    ps = real["pilot_sha"] if pilot_sha == "real" else pilot_sha
    return V.a8_frozen_record_reasons(arm, att, session, v8 or real["v8"], am, ps)


def resealed(doc, **changes):
    return ph.seal(dict({k: v for k, v in doc.items() if k != "sha256"}, **changes))


# premises: the real records have the shape the spec describes
def test_premises_on_the_real_records(real):
    v8, am = real["v8"], real["amendment"]
    assert ph.sealed_ok(am) and ph.sealed_ok(v8)
    assert am["v8_base_sha256"] == v8["sha256"] and am["pilot_dossier_sha256"] == real["pilot_sha"]
    for (arm, session), att in real["atts"].items():
        want = v8["sha256"] if session == "pilot" else am["sha256"]
        assert att["chain"]["frozen_record"]["sha256"] == want, (arm, session)


# R1: every real decider attempt passes on the amendment; the real pilot passes on the v8 base
@pytest.mark.parametrize("arm,session", sorted(ATTEMPTS))
def test_r1_real_attempts_pass_rule_3_6(real, arm, session):
    assert reasons(real, arm, session) == []


# R1: the pilot still needs the v8 base — a pilot naming the amendment is a reason (R2)
@pytest.mark.parametrize("arm", ("n16", "x"))
def test_r2_pilot_naming_the_amendment_is_a_reason(real, arm):
    got = reasons(real, arm, "pilot", frozen_sha=real["amendment"]["sha256"])
    assert got and all(r.startswith("rule 3.6") for r in got) and "amendment" in " ".join(got)


# R2: no amendment published while a decider attempt names one
@pytest.mark.parametrize("session", DECIDER)
def test_r2_no_amendment_published(real, session):
    got = reasons(real, "x", session, amendment=None)
    assert got and all(r.startswith("rule 3.6") for r in got) and "amendment" in " ".join(got)


# R2: an unsealed / tampered amendment (content changed, seal kept)
@pytest.mark.parametrize("change", [dict(leg_deadline_s={"reload": 1.0, "s1": 1.0, "s2": 1.0}), dict(w_rust_s=1.0)])
def test_r2_tampered_amendment(real, change):
    am = dict(real["amendment"], **change)                      # its `sha256` field still the one the chains name
    assert not ph.sealed_ok(am)
    for session in DECIDER:
        got = reasons(real, "n16", session, amendment=am)
        assert got and all(r.startswith("rule 3.6") for r in got)


# R2: a malformed amendment (not an object) is a reason, never a crash
@pytest.mark.parametrize("am", [[], "x", 3])
def test_r2_malformed_amendment(real, am):
    got = reasons(real, "n16", "s1", amendment=am)
    assert got and all(r.startswith("rule 3.6") for r in got)


# R2: a resealed amendment naming another v8 base / another pilot dossier / of another kind; the decider attempts name its sha
@pytest.mark.parametrize("change", [dict(v8_base_sha256="0" * 64), dict(v8_base_sha256=None), dict(pilot_dossier_sha256="0" * 64),
                                    dict(pilot_dossier_sha256=None), dict(kind="p426_v8_base"), dict(corpus="tg1")])
def test_r2_amendment_naming_another_identity(real, change):
    am = resealed(real["amendment"], **change)
    assert ph.sealed_ok(am)
    for session in DECIDER:
        got = reasons(real, "x", session, amendment=am, frozen_sha=am["sha256"])
        assert got and all(r.startswith("rule 3.6") for r in got), (change, session)


# R1 (v1.1): no recorded pilot dossier (missing record / dossier → no sha) is a rule-3.6 reason for the deciders
def test_r2_no_recorded_pilot_dossier(real):
    for session in DECIDER:
        got = reasons(real, "n16", session, pilot_sha=None)
        assert got and all(r.startswith("rule 3.6") for r in got)
        got = V.a8_frozen_record_reasons("n16", real["atts"][("n16", session)], session, real["v8"], real["amendment"], None,
                                         "the recorded pilot dossier m76/wave2.tg2/pairs/x.json is missing")
        assert got and all(r.startswith("rule 3.6") and "is missing" in r for r in got)


# R2: the amendment is valid but names another v8 base than the one B8-A8 read
def test_r2_amendment_of_another_v8_base_read(real):
    v8 = dict(real["v8"], sha256="1" * 64)
    got = reasons(real, "x", "s2", v8=v8)
    assert got and all(r.startswith("rule 3.6") for r in got)


# R2: a decider attempt naming a sha that is neither the v8 base's nor the amendment's; a missing frozen_record block
@pytest.mark.parametrize("session", DECIDER)
def test_r2_decider_naming_neither(real, session):
    got = reasons(real, "x", session, frozen_sha="f" * 64)
    assert got and all(r.startswith("rule 3.6") for r in got)
    att = dict(name="a", chain={})
    got = V.a8_frozen_record_reasons("x", att, session, real["v8"], real["amendment"], real["pilot_sha"])
    assert got and all(r.startswith("rule 3.6") for r in got)


# R2 (v1.2, Sol P1): a decider attempt naming the v8 base is a rule-3.6 reason — with the valid amendment published, with none
# published, and with a tampered one (the v8 base never bypasses the amendment checks)
@pytest.mark.parametrize("session", DECIDER)
@pytest.mark.parametrize("amendment", ["real", None, "tampered"])
def test_r2_decider_naming_the_v8_base_is_a_reason(real, session, amendment):
    am = dict(real["amendment"], w_rust_s=1.0) if amendment == "tampered" else amendment
    for arm in ("n16", "x"):
        got = reasons(real, arm, session, amendment=am, frozen_sha=real["v8"]["sha256"])
        assert got and all(r.startswith("rule 3.6") for r in got), (arm, session, got)
        assert any("v8 base" in r for r in got), got


# R2: a pilot naming a sha that is neither; a pilot when no amendment is published still passes on the v8 base
def test_pilot_rules(real):
    assert reasons(real, "n16", "pilot", frozen_sha="f" * 64)
    assert reasons(real, "n16", "pilot", amendment=None, pilot_sha=None) == []


# --------------------------------------------------------------------------------------------- end-to-end on a copy (R1–R4)
@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("s29a8") / "benchmark" / "results" / "m76"
    shutil.copytree(TG2, root / "wave2.tg2")
    shutil.copy(M76 / "B8.json", root / "B8.json")
    return root


def run_a8(root):
    return V.verify_a8_kv(root, sha(root / "B8.json"))


def by_session(doc):
    return {p["pair"]: p for p in doc["pairs"]}


# R1 / R3 / R4: on the real records every pair is accepted, the status complete and the amendment a hashed input
def test_e2e_real_records_complete_and_amendment_is_an_input(world):
    doc = run_a8(world)
    got = by_session(doc)
    for s in ("pilot", *DECIDER):
        assert got[s]["status"] == "accepted" and got[s]["reasons"] == [], (s, got[s]["reasons"][:3])
    assert doc["status"] == "complete"
    assert doc["inputs"]["m76/wave2.tg2/run/amendment.json"] == sha(RUN / "amendment.json")
    assert doc["inputs"]["m76/wave2.tg2/run/v8_base.json"] == sha(RUN / "v8_base.json")


# R3: a later change to the amendment is detected by the consumer's input check (as the v8 base's is)
def test_e2e_consumer_detects_a_changed_amendment(world, tmp_path):
    doc = run_a8(world)
    rows_root = world.parent
    path = world / "wave2.tg2" / "run" / "amendment.json"
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"\n")
        with pytest.raises(V.RefusalError, match="amendment"):
            V.check_b8_a8(rows_root, doc, sha(world / "B8.json"), V.STACK_REPO)
    finally:
        path.write_bytes(original)


# R2 end-to-end: no amendment published / a tampered one → every decider pair rejected with a rule-3.6 reason; the pilot accepted
@pytest.mark.parametrize("variant", ["absent", "tampered"])
def test_e2e_amendment_absent_or_tampered(world, variant):
    path = world / "wave2.tg2" / "run" / "amendment.json"
    original = path.read_bytes()
    try:
        if variant == "absent":
            path.unlink()
        else:
            am = json.loads(original)
            am["leg_deadline_s"]["s1"] = 1.0
            path.write_text(json.dumps(am, indent=1, sort_keys=True) + "\n")
        doc = run_a8(world)
    finally:
        path.write_bytes(original)
    got = by_session(doc)
    assert got["pilot"]["status"] == "accepted"
    for s in DECIDER:
        assert got[s]["status"] == "rejected" and any(r.startswith("rule 3.6") and "amendment" in r for r in got[s]["reasons"]), s
    assert doc["status"] == "incomplete"
    if variant == "absent":
        assert "m76/wave2.tg2/run/amendment.json" not in doc["inputs"]


# R1 (v1.1): a pilot pair B8-A8 rejects (here: rule 3.6 tg2_leg on one pilot chain) leaves the decider pairs accepted — the
# amendment binds the dossier the sequencer recorded, not B8-A8's pilot verdict
def test_e2e_rejected_pilot_leaves_the_deciders_accepted(world):
    path = world / "wave2.tg2" / ATTEMPTS[("x", "pilot")] / "chain.json"
    original = path.read_bytes()
    try:
        chain = json.loads(original)
        chain["tg2_leg"] = "s9"
        path.write_text(json.dumps(chain, indent=1, sort_keys=True) + "\n")
        doc = run_a8(world)
    finally:
        path.write_bytes(original)
    got = by_session(doc)
    assert got["pilot"]["status"] == "rejected" and any("tg2_leg" in r for r in got["pilot"]["reasons"])
    for s in DECIDER:
        assert got[s]["status"] == "accepted" and got[s]["reasons"] == [], (s, got[s]["reasons"][:3])
    assert doc["inputs"]["m76/wave2.tg2/pairs/" + PILOT_DOSSIER.name] == sha(PILOT_DOSSIER)


# R2 end-to-end (v1.2, Sol P1): one decider attempt re-pointed at the v8 base → that pair rejected with a rule-3.6 reason naming
# the attempt and the v8 base; the other pairs untouched
@pytest.mark.parametrize("session", DECIDER)
def test_e2e_decider_naming_the_v8_base_is_rejected(world, session):
    victim = ATTEMPTS[("n16", session)]
    path = world / "wave2.tg2" / victim / "chain.json"
    original = path.read_bytes()
    try:
        chain = json.loads(original)
        chain["frozen_record"]["sha256"] = load(RUN / "v8_base.json")["sha256"]
        path.write_text(json.dumps(chain, indent=1, sort_keys=True) + "\n")
        doc = run_a8(world)
    finally:
        path.write_bytes(original)
    got = by_session(doc)
    assert got[session]["status"] == "rejected"
    assert any(r.startswith("rule 3.6") and victim in r and "v8 base" in r for r in got[session]["reasons"]), got[session]["reasons"][:3]
    for s in ("pilot", *DECIDER):
        if s != session:
            assert got[s]["status"] == "accepted" and got[s]["reasons"] == [], (s, got[s]["reasons"][:3])
    assert doc["status"] == ("complete" if session == "reload" else "incomplete")


# R1 (v1.1): the recorded pilot dossier missing, or its bytes not the ones the amendment names → every decider pair rejected (3.6)
@pytest.mark.parametrize("variant", ["missing", "changed"])
def test_e2e_recorded_pilot_dossier_missing_or_wrong(world, variant):
    path = world / "wave2.tg2" / "pairs" / PILOT_DOSSIER.name
    original = path.read_bytes()
    try:
        if variant == "missing":
            path.unlink()
        else:
            path.write_bytes(original + b"\n")
        doc = run_a8(world)
    finally:
        path.write_bytes(original)
    got = by_session(doc)
    for s in DECIDER:
        assert got[s]["status"] == "rejected", s
        assert any(r.startswith("rule 3.6") and "pilot dossier" in r for r in got[s]["reasons"]), (s, got[s]["reasons"][:3])
    assert doc["status"] == "incomplete"


# R1 (v1.1): no pilot pair record in sequence.json → no recorded dossier → a reason, never a crash; the real record → its byte sha
def test_recorded_pilot_dossier_without_a_pilot_record(world):
    seq = json.loads((world / "wave2.tg2" / "run" / "sequence.json").read_text())
    got, why = V.a8_recorded_pilot_dossier_sha256(V.Reader(world), seq, "n16", "x")
    assert got == sha(PILOT_DOSSIER) and why is None
    seq["pairs"] = [p for p in seq["pairs"] if p.get("pair") != "pilot"]
    got, why = V.a8_recorded_pilot_dossier_sha256(V.Reader(world), seq, "n16", "x")
    assert got is None and "pilot pair record" in why
