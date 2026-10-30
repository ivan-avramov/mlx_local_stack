"""P426 B2 frozen tests, delivery 1d: the Wave-2 sequencer (spec v3.2 §1, §5.5, §6.5, §8, §9, §10.3, §16.4-16.5).

Classes: [FIX] reproduces a failure the spec fixes; [INV] preserves an invariant; [NEW] exercises new behaviour (all NEW here).
`p426_wave2.main(argv, ops=<SeqOps>, clock=…, sleep=…)` with the §16.5 CLI (`run` / `makeup` / `rehearsal`, `--pause-file`,
`<out-base>/sequence.json`); the ops are `b2_frozen_add_support.SeqOps`: a fake chain writes each leg's artifacts in the frozen
formats, a fake watcher its `watch.jsonl`; time is a fake clock (the 600 s idle gaps cost nothing)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.tests import b2_frozen_add_support as A
from bench.tests import b2_frozen_support as S

LEGS = ["tg1-p426-off-pilot", "tg1-p426-on-pilot", "tg1-p426-off-s1", "tg1-p426-on-s1", "tg1-p426-on-s2",
        "tg1-p426-off-s2", "tg1-p426-on-reload", "tg1-p426-off-reload"]
FIRST_OF = {"tg1-p426-on-pilot": "tg1-p426-off-pilot", "tg1-p426-on-s1": "tg1-p426-off-s1",
            "tg1-p426-off-s2": "tg1-p426-on-s2", "tg1-p426-off-reload": "tg1-p426-on-reload"}


def W2():
    from bench import p426_wave2
    return p426_wave2


def seq(tmp_path, monkeypatch, cmd="run", *extra, script=None, on_sleep=None, records=True, before=None,
        emails=("op.erator@corp-mail.example",)):
    """post-reveal 3d (§16.8): the ops carry the sequencer seams (`operator_emails`, `worktree_state`, `identity`,
    `harvest_path` under `<tmp>/main`)."""
    wd = tmp_path / "wd"
    wd.mkdir(parents=True, exist_ok=True)                           # post-reveal 3e: a nested tmp root (the planned-slots test)
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    if records:
        A.sequencer_records(tmp_path)
    argv, wts = A.seq_argv(tmp_path, cmd, *extra)
    clock = A.Clock(on_sleep=on_sleep)
    ops = A.SeqOps(clock, script, main_root=tmp_path / "main", emails=emails)
    if before:
        before(ops, clock)
    W2()                                                            # the module must exist (not an ImportError 'refusal')
    rc, err = A.run_sequencer(argv, ops, clock)
    base = wd / ("p426/rehearsal" if cmd == "rehearsal" else "p426/wave2")
    return dict(rc=rc, err=err, ops=ops, clock=clock, wts=wts, base=base, rec=tmp_path / "records", wd=wd)


def legs_run(r):
    return [r["ops"]._leg_of(h.argv) for h in r["ops"].chain_launches()]


def sequence(r):
    return json.loads((r["base"] / "sequence.json").read_text())


def state_of(r, leg):
    return [x["state"] for x in sequence(r)["legs"] if x["leg"] == leg]


def strip(argv, *flags):
    out, skip = [], 0
    for x in argv:
        if skip:
            skip -= 1
            continue
        if x in flags:
            skip = 1
            continue
        out.append(x)
    return out


# ------------------------------------------------------------------------------------------------ the pilot pair
def test_new_the_pilot_pair_runs_each_legs_argv_with_the_first_receipt(tmp_path, monkeypatch):
    r = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-pilot")
    assert r["rc"] == 0, r["err"]
    assert legs_run(r) == LEGS[:2]
    off_h, on_h = r["ops"].chain_launches()
    for leg, h in zip(LEGS[:2], (off_h, on_h)):
        want = W2().leg_argv(leg, 1, worktrees=r["wts"], record_path=r["rec"] / "v8_base.json", out_base=r["base"])
        assert A.is_subsequence(want, strip(h.argv, "--pair-receipt")), (want, h.argv)
        assert "--hmac-fd" not in h.argv                                  # C238: no pair key
    assert A.arg(on_h.argv, "--pair-receipt") == str(r["base"] / "tg1-p426-off-pilot.a1" / "receipt.json")
    assert "--pair-receipt" not in off_h.argv
    assert state_of(r, "tg1-p426-off-pilot") == ["VALID"] and state_of(r, "tg1-p426-on-pilot") == ["VALID"]


def test_new_each_leg_gets_a_watcher_bound_to_its_chain_and_a_harvest(tmp_path, monkeypatch):
    r = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-pilot")
    assert r["rc"] == 0
    chains = r["ops"].chain_launches()
    watchers = [h for h in r["ops"].launches if h.kind == "watcher"]
    assert len(watchers) == 2
    for c, w in zip(chains, watchers):
        root = Path(A.arg(c.argv, "--out-root"))
        assert A.arg(w.argv, "--chain-json") == str(root / "chain.json") and A.arg(w.argv, "--driver-pid") == str(c.pid)
        assert A.arg(w.argv, "--out") == str(root / "watch.jsonl")
    assert r["ops"].harvested == [str(r["base"] / f"{leg}.a1") for leg in LEGS[:2]]


def test_new_legs_are_separated_by_600_s_and_last_leg_end_is_recorded(tmp_path, monkeypatch):
    r = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-pilot")
    assert r["rc"] == 0
    a, b = r["ops"].chain_launches()
    assert b.start >= a.end + 600.0
    end = float((r["wd"] / "p426" / "LAST_LEG_END").read_text().strip())
    assert end >= b.end - 1.0


def test_new_the_pair_dossier_is_per_pair_attempt_keyed_by_arm_published_and_selected(tmp_path, monkeypatch):
    """[d2] §6.5 / §16.1 / §16.6: `<out-base>/pairs/<pair>__off-a<n>__on-a<m>.json`, keyed by arm, carrying each harvest's
    sha256 as `ops.harvest` returned it; published by `ops.publish_dossier`; named in `sequence.json`."""
    r = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-pilot")
    assert r["rc"] == 0
    (dossier,) = list((r["base"] / "pairs").glob("*.json"))
    assert dossier.name == "pilot__off-a1__on-a1.json"                  # §16.7: <pair> = pilot
    doc = json.loads(dossier.read_text())
    assert S.self_hashed(doc)["sha256"] == doc["sha256"] and doc["verdict"] and doc["pair"] == "pilot"
    assert all(set(e) == {"process", "field", "off", "on"} and e["process"] in ("router", "worker", "probe", "-")
               for e in doc["differences"])                              # §16.7 entry format
    arms = doc["arms"]
    assert set(arms) == {"off", "on"}
    assert (arms["off"]["attempt"], arms["on"]["attempt"]) == ("tg1-p426-off-pilot.a1", "tg1-p426-on-pilot.a1")
    for arm, leg in (("off", "tg1-p426-off-pilot"), ("on", "tg1-p426-on-pilot")):
        assert arms[arm]["receipt_sha256"] == S.sha256_file(r["base"] / f"{leg}.a1/receipt.json")
        assert arms[arm]["harvest_sha256"] == S.sha256_file(r["ops"].harvest_path(f"{leg}.a1") / "HARVEST.json")   # 3d (§16.8)
    assert [d for d, _ in r["ops"].dossiers] == [str(dossier)]
    assert dossier.name in (r["base"] / "sequence.json").read_text()


def test_new_the_run_files_are_published_with_the_record_dir_and_sequence_json(tmp_path, monkeypatch):
    """[d2] §16.6 / §16.7: `ops.publish_run_files(paths, *, emails)` gets files only — the frozen-record directory expanded
    to its files, and `sequence.json`."""
    r = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-pilot")
    assert r["rc"] == 0 and r["ops"].run_files
    published = {Path(p) for paths, _ in r["ops"].run_files for p in paths}
    assert r["base"] / "sequence.json" in published and r["rec"] / "v8_base.json" in published
    assert r["rec"] not in published and all(not p.is_dir() for p in published)


def test_new_each_sequence_json_version_records_the_sha256_of_the_previous_one(tmp_path, monkeypatch):
    """[d2] §16.1 / §16.7: `sequence.json` is a state journal, replaced atomically; each version carries `previous_sha256`,
    the sha256 of the version it replaces (null for the first). Every version is captured at its atomic replace."""
    import hashlib
    import os
    target = tmp_path / "wd/p426/wave2/sequence.json"
    versions = []
    real_replace, real_rename = os.replace, os.rename

    def capture(move):
        def wrapped(src, dst, *a, **kw):
            out = move(src, dst, *a, **kw)
            if Path(dst) == target:
                versions.append(target.read_bytes())
            return out
        return wrapped
    monkeypatch.setattr(os, "replace", capture(real_replace))
    monkeypatch.setattr(os, "rename", capture(real_rename))
    r = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-pilot")
    assert r["rc"] == 0, r["err"]
    assert len(versions) >= 2, "sequence.json was not replaced atomically at least twice"
    assert versions[-1] == target.read_bytes()
    docs = [json.loads(v) for v in versions]
    assert docs[0]["previous_sha256"] is None
    for prev, doc in zip(versions, docs[1:]):
        assert doc["previous_sha256"] == hashlib.sha256(prev).hexdigest()


def test_new_the_sequencer_holds_its_own_lock_and_never_the_leg_lock(tmp_path, monkeypatch):
    seen = []

    def spy(ops, clock):
        original = ops.launch

        def launch(argv, **kw):
            seen.append((S.is_flocked(tmp_path / "wd/p426/SEQUENCER.lock"), S.is_flocked(tmp_path / "wd/p426/LEG.lock")))
            return original(argv, **kw)
        ops.launch = launch
    r = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-pilot", before=spy)
    assert r["rc"] == 0 and seen and all(s == (True, False) for s in seen)


# ------------------------------------------------------------------------------------------------ the pilot gate (§1)
def _stopped_after_pilots(r):
    assert r["rc"] == 1 and legs_run(r) == LEGS[:2]                   # post-reveal 3d (§16.8): 1 = stopped (the gate)
    assert not (r["rec"] / "amendment.json").exists()


def test_new_the_pilot_gate_stops_on_a_pilot_dnf(tmp_path, monkeypatch):
    _stopped_after_pilots(seq(tmp_path, monkeypatch, script={"tg1-p426-on-pilot": {"dnf": 1}}))


def test_new_the_pilot_gate_stops_when_on_engagement_is_not_proven(tmp_path, monkeypatch):
    _stopped_after_pilots(seq(tmp_path, monkeypatch, script={"tg1-p426-on-pilot": {"engaged": False}}))


def test_new_the_pilot_gate_stops_when_a_pilot_is_speed_invalid(tmp_path, monkeypatch):
    r = seq(tmp_path, monkeypatch, script={"tg1-p426-off-pilot": {"watcher_dies": True}})
    _stopped_after_pilots(r)
    rec = json.loads((r["base"] / "tg1-p426-off-pilot.a1" / "leg.json").read_text())
    assert rec["speed_valid"] is False and rec["speed_reason"] and rec["state"] == "VALID"     # quality continues (§8)


def test_new_a_speed_valid_leg_records_it(tmp_path, monkeypatch):
    r = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-off-pilot")
    assert r["rc"] == 0
    rec = json.loads((r["base"] / "tg1-p426-off-pilot.a1" / "leg.json").read_text())
    assert rec["speed_valid"] is True and rec["leg"] == "tg1-p426-off-pilot" and rec["attempt"] == 1


def test_new_each_harvest_gets_the_main_checkouts_operator_email(tmp_path, monkeypatch):
    """post-reveal 3d (§16.8): the address comes from `ops.operator_emails()` (the box ops read `git config user.email`)."""
    r = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-pilot", emails=("op.erator@corp-mail.example",))
    assert r["rc"] == 0 and len(r["ops"].harvest_emails) == 2
    assert all("op.erator@corp-mail.example" in e for e in r["ops"].harvest_emails)
    assert all("op.erator@corp-mail.example" in e for _, e in r["ops"].dossiers)


def test_new_the_pilot_gate_stops_on_an_invalid_pilot(tmp_path, monkeypatch):
    _stopped_after_pilots(seq(tmp_path, monkeypatch, script={"tg1-p426-on-pilot": {"rc": 2}}))


def test_new_a_passed_pilot_gate_writes_the_amendment_and_the_session_legs_use_it(tmp_path, monkeypatch):
    r = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-s1")
    assert r["rc"] == 0, r["err"]
    assert legs_run(r) == LEGS[:4]
    am = json.loads((r["rec"] / "amendment.json").read_text())
    v8 = json.loads((r["rec"] / "v8_base.json").read_text())
    assert am["kind"] == "p426_timeout_amendment" and am["v8_base_sha256"] == v8["sha256"]
    assert S.self_hashed(am)["sha256"] == am["sha256"] and am["w_python_s"] >= 500.0       # the pilots' largest wall
    for h in r["ops"].chain_launches()[2:]:
        assert A.arg(h.argv, "--frozen-record") == str(r["rec"] / "amendment.json")


def test_new_the_full_run_goes_through_legs_1_to_8_in_order_with_their_pairs(tmp_path, monkeypatch):
    r = seq(tmp_path, monkeypatch, "run")
    assert r["rc"] == 0, r["err"]
    assert legs_run(r) == LEGS
    hs = {r["ops"]._leg_of(h.argv): h for h in r["ops"].chain_launches()}
    for second, first in FIRST_OF.items():
        assert A.arg(hs[second].argv, "--pair-receipt") == str(r["base"] / f"{first}.a1/receipt.json")
    assert all("--hmac-fd" not in h.argv for h in hs.values())          # C238: no pair key
    names = {p.name for p in (r["base"] / "pairs").glob("*.json")}
    assert names == {f"{p}__off-a1__on-a1.json" for p in ("pilot", "s1", "s2", "reload")}   # §16.7 labels, one per pair attempt
    assert all(state_of(r, leg) == ["VALID"] for leg in LEGS)


# ------------------------------------------------------------------------------------------------ systemic / overrun / pause
def test_new_an_invalid_leg_stops_the_sequencer(tmp_path, monkeypatch):
    r = seq(tmp_path, monkeypatch, script={"tg1-p426-off-s1": {"rc": 2}})
    assert r["rc"] == 1 and legs_run(r) == LEGS[:3]                     # post-reveal 3d (§16.8): 1 = stopped (a leg)
    assert state_of(r, "tg1-p426-off-s1") == ["INVALID"]
    rec = json.loads((r["base"] / "tg1-p426-off-s1.a1" / "leg.json").read_text())
    assert rec["state"] == "INVALID" and rec["chain_rc"] == 2 and rec["attempt"] == 1


def test_new_an_overrun_pauses_never_kills_and_stops_for_the_operator(tmp_path, monkeypatch):
    """post-reveal 3d (§16.8): a leg past its deadline that then ends by itself is classified normally and its leg record
    carries `overrun: true`; the sequencer stops with 3 (overrun pause) after the harvest."""
    r = seq(tmp_path, monkeypatch, script={"tg1-p426-off-pilot": {"runtime_s": 5000.0}})     # v8 pilot deadline 4000 s
    o = json.loads((r["base"] / "OVERRUN_PAUSED").read_text())       # §16.6: <out-base>/OVERRUN_PAUSED
    assert (o["leg"], o["attempt"], o["deadline_s"]) == ("tg1-p426-off-pilot", 1, 4000.0) and o["at"]
    (h,) = r["ops"].chain_launches()
    assert h.waited and r["clock"].t >= h.end                            # waited out, never signalled
    assert legs_run(r) == LEGS[:1] and state_of(r, "tg1-p426-off-pilot") == ["VALID"]
    rec = json.loads((r["base"] / "tg1-p426-off-pilot.a1" / "leg.json").read_text())
    assert rec["state"] == "VALID" and rec["overrun"] is True
    assert r["ops"].harvested == [str(r["base"] / "tg1-p426-off-pilot.a1")] and r["rc"] == 3


def test_new_an_overrun_leg_the_operator_stopped_during_the_pause_is_overrun_and_never_paired(tmp_path, monkeypatch):
    """post-reveal 3d (§16.8): the state `OVERRUN` is a leg that did not end by itself (stopped by the operator during
    `OVERRUN_PAUSED`: the chain exits by signal before `chain.json` says finished) — never paired; exit 3."""
    r = seq(tmp_path, monkeypatch,
            script={"tg1-p426-off-pilot": {"runtime_s": 5000.0, "rc": -15, "status": "running"}})
    assert state_of(r, "tg1-p426-off-pilot") == ["OVERRUN"] and r["rc"] == 3
    rec = json.loads((r["base"] / "tg1-p426-off-pilot.a1" / "leg.json").read_text())
    assert rec["state"] == "OVERRUN" and rec["overrun"] is True
    assert legs_run(r) == LEGS[:1] and not list(r["base"].glob("pairs/*.json"))          # never paired


def test_new_a_failed_harvest_stops_with_4_and_keeps_the_leg(tmp_path, monkeypatch):
    """post-reveal 3d (§16.8): 4 = harvest failure; the leg's root, leg record and `sequence.json` entry are kept."""
    r = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-pilot", script={"__harvest_rc__": 1})
    assert r["rc"] == 4 and legs_run(r) == LEGS[:1]
    assert (r["base"] / "tg1-p426-off-pilot.a1" / "leg.json").is_file() and state_of(r, "tg1-p426-off-pilot") == ["VALID"]


def test_new_the_planned_slots_come_from_the_legs_frozen_schedule(tmp_path, monkeypatch):
    """post-reveal 3d (§16.8): the sequencer reads each leg's plan from its `chain.json` frozen schedule, never a constant —
    an s1 leg of a 5-item universe whose ledger equals its schedule is VALID; one slot short of its schedule is INVALID."""
    small = dict(shape=[("python", 3), ("go", 2)])
    r = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-off-s1", script={"tg1-p426-off-s1": small})
    assert r["rc"] == 0, r["err"]
    assert state_of(r, "tg1-p426-off-s1") == ["VALID"]
    short = seq(tmp_path / "short", monkeypatch, "run", "--through", "tg1-p426-off-s1",
                script={"tg1-p426-off-s1": dict(small, drop_slots=1)})
    assert short["rc"] == 1 and state_of(short, "tg1-p426-off-s1") == ["INVALID"]


def test_new_a_pause_file_holds_the_next_launch_until_it_is_removed(tmp_path, monkeypatch):
    pause = tmp_path / "wd/p426/wave2/PAUSE"
    pause.parent.mkdir(parents=True)
    pause.write_text("")
    removed = {}

    def on_sleep(c):
        if c.sleeps == 5 and pause.exists():
            pause.unlink()
            removed["t"] = c.t
    r = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-off-pilot", on_sleep=on_sleep)
    assert r["rc"] == 0 and "t" in removed
    assert all(h.start >= removed["t"] for h in r["ops"].chain_launches())


def test_new_a_custom_pause_file_is_honoured(tmp_path, monkeypatch):
    pause = tmp_path / "hold"
    pause.write_text("")
    removed = {}

    def on_sleep(c):
        if c.sleeps == 3 and pause.exists():
            pause.unlink()
            removed["t"] = c.t
    r = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-off-pilot", "--pause-file", str(pause), on_sleep=on_sleep)
    assert r["rc"] == 0 and all(h.start >= removed["t"] for h in r["ops"].chain_launches())


# ------------------------------------------------------------------------------------------------ resume
def test_new_resume_skips_valid_harvested_legs(tmp_path, monkeypatch):
    first = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-pilot")
    assert first["rc"] == 0
    again = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-pilot", records=False)
    assert again["rc"] == 0 and legs_run(again) == []


def _reseal(path, **change):
    doc = {k: v for k, v in json.loads(Path(path).read_text()).items() if k != "sha256"}
    doc.update(change)
    Path(path).write_text(json.dumps(S.self_hashed(doc), sort_keys=True, indent=1))


@pytest.mark.parametrize("tamper", ["receipt_sha256", "verdict", "seal"])
def test_new_a_pair_dossier_found_on_resume_is_reverified_never_trusted(tmp_path, monkeypatch, capsys, tamper):
    """post-reveal 3h (§16.8 after the strict verify round 1): a pair dossier found on resume is re-verified against the
    current receipts / harvests (never its stored verdict); a mismatch stops (1) before any further leg."""
    first = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-pilot")
    assert first["rc"] == 0, first["err"]
    (dossier,) = list((first["base"] / "pairs").glob("*.json"))
    doc = json.loads(dossier.read_text())
    if tamper == "receipt_sha256":
        _reseal(dossier, arms=dict(doc["arms"], off=dict(doc["arms"]["off"], receipt_sha256="0" * 64)))
    elif tamper == "verdict":
        _reseal(dossier, verdict="FAIL" if doc["verdict"] == "PASS" else "PASS")
    else:
        dossier.write_text(json.dumps(dict(doc, differences=doc["differences"] + [
            dict(process="-", field="x", off=None, on=None)])))                 # changed without re-sealing
    capsys.readouterr()
    again = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-off-s1", records=False)
    said = again["err"] + capsys.readouterr().out                      # the sequencer's log stream is the candidate's choice
    assert again["rc"] == 1, said
    assert legs_run(again) == [] and any("STOP" in ln and dossier.name in ln for ln in said.splitlines()), said


def test_new_an_existing_amendment_is_reverified_before_use(tmp_path, monkeypatch):
    """post-reveal 3h (§16.8): the amendment records `pilot_dossier_sha256` and an existing amendment is re-verified before use;
    one whose pilot dossier hash is not the selected pilots' dossier stops before the next leg."""
    first = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-off-s1")
    assert first["rc"] == 0, first["err"]
    am = first["rec"] / "amendment.json"
    (dossier,) = [p for p in (first["base"] / "pairs").glob("pilot__*.json")]
    assert json.loads(am.read_text())["pilot_dossier_sha256"] == S.sha256_file(dossier)
    _reseal(am, pilot_dossier_sha256="0" * 64)
    again = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-s1", records=False)
    assert again["rc"] in (1, 2) and legs_run(again) == [], again["err"]      # the exit code is the candidate's (1 or 2)


@pytest.mark.parametrize("dnf_engaged,state,rc", [(True, "VALID_WITH_DNF", 0), (False, "INVALID", 1)],
                         ids=["engaged", "unengaged"])
def test_new_a_dnf_item_record_is_engagement_checked(tmp_path, monkeypatch, dnf_engaged, state, rc):
    """post-reveal 3h (§16.8 after the strict verify round 1): DNF item records are engagement-checked and re-validated — an
    ON leg whose DNF item's completed requests lack the drafter counters is not VALID_WITH_DNF."""
    r = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-s1",
            script={"tg1-p426-on-s1": {"dnf": 1, "dnf_engaged": dnf_engaged}})
    assert r["rc"] == rc, r["err"]
    assert state_of(r, "tg1-p426-on-s1") == [state]


def test_new_a_dnf_ledger_entry_without_its_ready_record_is_not_valid_with_dnf(tmp_path, monkeypatch):
    """post-reveal 3i (§16.8 after the strict verify round 3): every ledger entry, DNF included, requires its sealed ready
    record (classification); the `engaged` case of the test above is the positive control."""
    r = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-s1",
            script={"tg1-p426-on-s1": {"dnf": 1, "dnf_ready": "missing"}})
    assert r["rc"] == 1, r["err"]
    assert state_of(r, "tg1-p426-on-s1") == ["INVALID"]


def test_new_makeup_reverifies_the_existing_amendment_first(tmp_path, monkeypatch):
    """post-reveal 3i (§16.8): every command consuming an existing amendment (`run`, `makeup`) re-verifies it first — its
    `pilot_dossier_sha256` must be the freshly re-verified pilot dossier's sha256."""
    piloted(tmp_path, monkeypatch)
    _reseal(tmp_path / "records" / "amendment.json", pilot_dossier_sha256="0" * 64)
    occ = tmp_path / "occ.jsonl"
    occ.write_text(json.dumps(S.occurrence("s1", "python", "grep", 1001, "off")) + "\n")
    r = seq(tmp_path, monkeypatch, "makeup", "--occurrences", str(occ), records=False)
    assert r["rc"] in (1, 2) and legs_run(r) == [], r["err"]


def test_new_makeup_refuses_an_amendment_whose_pilot_dossier_no_longer_verifies(tmp_path, monkeypatch):
    """post-reveal 3i (§16.8 after the strict verify round 3, C256): amendment verification requires the freshly verified
    pilot dossier — a pilot receipt changed after the dossier stops the make-up before any leg."""
    piloted(tmp_path, monkeypatch)
    receipt = tmp_path / "wd/p426/wave2/tg1-p426-off-pilot.a1/receipt.json"
    _reseal(receipt, note="changed after the dossier")
    occ = tmp_path / "occ.jsonl"
    occ.write_text(json.dumps(S.occurrence("s1", "python", "grep", 1001, "off")) + "\n")
    r = seq(tmp_path, monkeypatch, "makeup", "--occurrences", str(occ), records=False)
    assert r["rc"] in (1, 2) and legs_run(r) == [], r["err"]


def test_new_a_dossier_is_published_before_the_pair_state_records_it(tmp_path, monkeypatch):
    """post-reveal 3i (§16.8 after the strict verify round 2): a dossier publication failure is exit 4 and the pair state
    (`sequence.json` `pairs`) does not record that dossier."""
    def failing(ops, clock):
        def publish_dossier(path, *, emails=()):
            raise OSError("main checkout not writable")
        ops.publish_dossier = publish_dossier
    r = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-pilot", before=failing)
    assert r["rc"] == 4, r["err"]
    assert not sequence(r)["pairs"]


def test_new_a_dossier_whose_publication_failed_is_republished_on_resume(tmp_path, monkeypatch):
    """post-reveal 3i (§16.8 after the strict verify round 2): a dossier is published before the pair state records it and
    republished idempotently on resume — after a failed publication (exit 4, the pair unrecorded) the resumed command
    re-verifies the same dossier, publishes it and only then records the pair."""
    def failing(ops, clock):
        def publish_dossier(path, *, emails=()):
            raise OSError("main checkout not writable")
        ops.publish_dossier = publish_dossier
    first = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-pilot", before=failing)
    assert first["rc"] == 4, first["err"]
    (dossier,) = list((first["base"] / "pairs").glob("*.json"))
    before = dossier.read_bytes()
    again = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-pilot", records=False)
    assert again["rc"] == 0, again["err"]
    assert legs_run(again) == [] and [d for d, _ in again["ops"].dossiers] == [str(dossier)]
    assert dossier.read_bytes() == before and len(sequence(again)["pairs"]) == 1
    assert dossier.name in json.dumps(sequence(again)["pairs"])           # `sequence.json` names the selected dossier (§6.5)


def test_new_a_failed_run_file_publication_after_a_stop_makes_the_exit_4_and_keeps_the_reason(tmp_path, monkeypatch, capsys):
    """post-reveal 3i (§16.8 after the strict verify round 3): any attempted run-file publication that fails makes the exit 4,
    whatever the earlier stop code; the log keeps the original stop reason and adds the publication failure."""
    def failing(ops, clock):
        def publish_run_files(paths, *, emails=()):
            raise OSError("main checkout not writable")
        ops.publish_run_files = publish_run_files
    capsys.readouterr()
    r = seq(tmp_path, monkeypatch, script={"tg1-p426-off-s1": {"rc": 2}}, before=failing)     # a stop (1) at leg 3
    said = r["err"] + capsys.readouterr().out
    assert r["rc"] == 4, said[-1500:]
    assert legs_run(r) == LEGS[:3] and state_of(r, "tg1-p426-off-s1") == ["INVALID"]
    assert any("tg1-p426-off-s1" in ln and "STOP" in ln for ln in said.splitlines()), said[-1500:]


def test_new_a_failure_to_publish_the_run_files_is_exit_4(tmp_path, monkeypatch):
    """post-reveal 3h (§16.8): a failure to publish the run files is exit 4; the legs and their records are kept."""
    def failing(ops, clock):
        def publish_run_files(paths, *, emails=()):
            raise OSError("main checkout not writable")
        ops.publish_run_files = publish_run_files
    r = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-pilot", before=failing)
    assert r["rc"] == 4, r["err"]
    assert legs_run(r) == LEGS[:2] and state_of(r, "tg1-p426-on-pilot") == ["VALID"]


def test_new_a_restart_between_the_legs_of_a_pair_resumes_it_with_the_first_legs_persisted_receipt(tmp_path, monkeypatch):
    """C238 (replaces the voiding test): only the second leg runs, comparing with the first leg's persisted receipt; nothing
    is voided and the first leg is not rerun."""
    def first_leg_done(ops, clock):
        base = tmp_path / "wd/p426/wave2"
        root = base / "tg1-p426-off-pilot.a1"
        A.write_leg(root, "tg1-p426-off-pilot", ["pilot", "--p426", "--predictor", "off", "--out-root", str(root)], {})
        A.write_watch(root / "watch.jsonl", dies=False)
        S.write_record(root / "leg.json", S.self_hashed(dict(                 # post-reveal 3e: the sequencer's sealed leg record
            leg="tg1-p426-off-pilot", attempt=1, state="VALID", reason="", chain_rc=0, started="t0", ended="t1",
            speed_valid=True, speed_reason="ok", overrun=False, **{"class": "valid"})))
        (base / "sequence.json").write_text(json.dumps({"legs": [{"leg": "tg1-p426-off-pilot", "attempt": 1, "state": "VALID"}],
                                                        "pairs": [], "previous_sha256": None}))
    r = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-pilot", before=first_leg_done)
    assert r["rc"] == 0, r["err"]
    (h,) = r["ops"].chain_launches()
    assert Path(A.arg(h.argv, "--out-root")).name == "tg1-p426-on-pilot.a1"
    assert A.arg(h.argv, "--pair-receipt") == str(r["base"] / "tg1-p426-off-pilot.a1" / "receipt.json")
    assert not list(r["base"].rglob("voided")) and not (r["base"] / "tg1-p426-off-pilot.a2").exists()


# ------------------------------------------------------------------------------------------------ make-up / rehearsal
def piloted(tmp_path, monkeypatch):
    """post-reveal 3i (§16.8 after the strict verify rounds 2 / 3): `makeup` re-verifies the existing amendment, which needs its
    pilots recorded in `sequence.json` and a freshly re-verified PASS pilot dossier — so a make-up runs after the real pilot
    pair and its pilot gate (it was a hand-written amendment with no pilots)."""
    first = seq(tmp_path, monkeypatch, "run", "--through", "tg1-p426-on-pilot")
    assert first["rc"] == 0, first["err"]
    assert (tmp_path / "records" / "amendment.json").is_file(), "the pilot gate wrote no amendment"
    return first


def makeup(tmp_path, monkeypatch, occs, **kw):
    piloted(tmp_path, monkeypatch)
    occ = tmp_path / "occ.jsonl"
    occ.write_text("".join(json.dumps(o) + "\n" for o in occs))
    return seq(tmp_path, monkeypatch, "makeup", "--occurrences", str(occ), records=False, **kw)


def test_new_makeup_runs_off_then_on_over_the_occurrences_as_a_pair(tmp_path, monkeypatch):
    r = makeup(tmp_path, monkeypatch, (S.occurrence("s1", "python", "grep", 1001, "off"),
                                       S.occurrence("s2", "go", "ledger", 2002, "on")))
    assert r["rc"] == 0, r["err"]
    assert legs_run(r) == ["tg1-p426-off-makeup", "tg1-p426-on-makeup"]
    off_h, on_h = r["ops"].chain_launches()
    want = {("s1", "python", "grep", 1001), ("s2", "go", "ledger", 2002)}
    for arm, h in (("off", off_h), ("on", on_h)):
        assert "makeup" in h.argv and "--hmac-fd" not in h.argv
        assert A.arg(h.argv, "--occurrences") == str(r["base"] / "makeup" / f"occurrences.{arm}.jsonl")   # §16.7
        assert A.arg(h.argv, "--out-root") == str(r["base"] / f"tg1-p426-{arm}-makeup.a1")   # 3d (§16.8): flat out-roots
        given = occurrences_given(h)
        assert {(o["session"], o["language"], o["item"], o["seed"]) for o in given} == want   # BOTH run the whole union
    assert A.arg(on_h.argv, "--pair-receipt") == str(r["base"] / "tg1-p426-off-makeup.a1/receipt.json")
    assert (r["base"] / "pairs" / "makeup__off-a1__on-a1.json").is_file()


def test_new_a_slot_dnfd_in_both_arms_is_one_canonical_occurrence_with_both_arms(tmp_path, monkeypatch):
    """post-reveal 3d (§16.8): records are de-duplicated per (session, language, item, seed), `arm_of_dnf` merged into a
    sorted list — the slot runs once per make-up leg."""
    r = makeup(tmp_path, monkeypatch, (S.occurrence("s1", "python", "grep", 1001, "on", 3),     # post-reveal 3i: piloted
                                       S.occurrence("s1", "python", "grep", 1001, "off", 3)))
    assert r["rc"] == 0, r["err"]
    for h in r["ops"].chain_launches():
        (o,) = occurrences_given(h)
        assert (o["session"], o["language"], o["item"], o["seed"], o["arm_of_dnf"]) == ("s1", "python", "grep", 1001, ["off", "on"])


def occurrences_given(h):
    """The occurrences a makeup chain was handed: the sequencer's canonical file `--occurrences` names (§16.7)."""
    p = Path(A.arg(h.argv, "--occurrences"))
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def test_new_the_occurrences_file_is_an_unordered_set_the_sequencer_canonicalizes(tmp_path, monkeypatch):
    """[d2] §16.6 / §5.5: two orderings of one occurrence set hand the chains the same occurrences in the canonical order —
    s1 then s2, each session in its original language order (s1 Python then Go; s2 Go then Python, §6.7)."""
    occs = [S.occurrence("s2", "go", "ledger", 2002, "on", 4), S.occurrence("s1", "python", "grep", 1001, "off", 1),
            S.occurrence("s1", "go", "bowling", 1001, "on", 0), S.occurrence("s2", "python", "grep", 2002, "off", 7)]
    seen = []
    for name, order in (("a", occs), ("b", occs[::-1])):
        sub = tmp_path / name
        sub.mkdir()
        r = makeup(sub, monkeypatch, order)                             # post-reveal 3i: after the real pilot pair
        assert r["rc"] == 0, r["err"]
        seen.append([occurrences_given(h) for h in r["ops"].chain_launches()])
    assert seen[0] == seen[1] and seen[0][0]
    for given in seen[0]:
        assert [(o["session"], o["language"]) for o in given] == [("s1", "python"), ("s1", "go"), ("s2", "go"), ("s2", "python")]


def test_new_the_rehearsal_runs_r1_as_a_pair_then_r2_and_r3(tmp_path, monkeypatch):
    def manifest(ops, clock):
        S.write_record(tmp_path / "rehearsal.json", S.rehearsal_manifest(tmp_path / "wd/p426/rehearsal"))
    r = seq(tmp_path, monkeypatch, "rehearsal", "--manifest", str(tmp_path / "rehearsal.json"), records=False, before=manifest,
            script={"tg1-p426-rehearsal-mismatch": {"rc": 2}})
    legs = legs_run(r)
    assert legs == ["tg1-p426-rehearsal-off", "tg1-p426-rehearsal-on", "tg1-p426-rehearsal-mismatch", "tg1-p426-rehearsal-kill"]
    hs = dict(zip(legs, r["ops"].chain_launches()))
    assert all("--rehearsal" in h.argv for h in hs.values())
    assert all(A.arg(h.argv, "--frozen-prompt-date") == S.EPOCH_DATE for h in hs.values())   # 3d (§16.8): the operator's date
    assert A.arg(hs["tg1-p426-rehearsal-mismatch"].argv, "--inject") == "reconcile-mismatch"
    assert A.arg(hs["tg1-p426-rehearsal-kill"].argv, "--inject") == "stall-kill"
    assert A.arg(hs["tg1-p426-rehearsal-on"].argv, "--pair-receipt") == str(
        Path(A.arg(hs["tg1-p426-rehearsal-off"].argv, "--out-root")) / "receipt.json")        # R1 is a pair (C238)
    assert all("--hmac-fd" not in h.argv for h in hs.values())
    (r1,) = [p for p in (tmp_path / "wd").rglob("pairs/*.json")]                              # §16.7: <pair> = r1
    assert r1.name == "r1__off-a1__on-a1.json"
    assert json.loads(r1.read_text())["arms"]["on"]["attempt"] == "tg1-p426-rehearsal-on.a1"


# ------------------------------------------------------------------------------------------------ refusals
def test_new_the_sequencer_refuses_while_the_gate_runs(tmp_path, monkeypatch):
    (tmp_path / "wd").mkdir()
    with S.held_flock(tmp_path / "wd" / "gate" / "RUNNING"):
        r = seq(tmp_path, monkeypatch, "run")
    assert r["rc"] == 2 and "REFUSED: " in r["err"] and not r["ops"].launches


def test_new_the_rehearsal_refuses_without_its_frozen_prompt_date(tmp_path, monkeypatch):
    """post-reveal 3d (§16.8): `p426_wave2 rehearsal` requires `--frozen-prompt-date`."""
    def manifest(ops, clock):
        S.write_record(tmp_path / "rehearsal.json", S.rehearsal_manifest(tmp_path / "wd/p426/rehearsal"))
    argv_extra = ["--manifest", str(tmp_path / "rehearsal.json"), "--no-frozen-prompt-date"]
    r = seq(tmp_path, monkeypatch, "rehearsal", *argv_extra, records=False, before=manifest)
    assert r["rc"] == 2 and "REFUSED: " in r["err"] and "--frozen-prompt-date" in r["err"] and not r["ops"].launches


def test_new_the_rehearsal_refuses_a_date_that_differs_from_the_manifests(tmp_path, monkeypatch):
    """post-reveal 3e (designer ruling on §16.8): `p426_wave2 rehearsal --frozen-prompt-date` refuses a date that differs from
    the one the rehearsal manifest recorded."""
    def manifest(ops, clock):
        S.write_record(tmp_path / "rehearsal.json", S.rehearsal_manifest(tmp_path / "wd/p426/rehearsal"))
    r = seq(tmp_path, monkeypatch, "rehearsal", "--manifest", str(tmp_path / "rehearsal.json"), "--no-frozen-prompt-date",
            "--frozen-prompt-date", "Tue Jan 06 2026", records=False, before=manifest)
    assert r["rc"] == 2 and "REFUSED: " in r["err"] and "--frozen-prompt-date" in r["err"] and not r["ops"].launches


def test_new_the_sequencer_refuses_without_its_v8_base(tmp_path, monkeypatch):
    r = seq(tmp_path, monkeypatch, "run", records=False)
    assert r["rc"] == 2 and "REFUSED: " in r["err"] and "v8_base" in r["err"] and not r["ops"].launches
