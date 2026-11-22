"""S29 frozen tests, the Wave 2 sequencer records a host change and never stops for it (spec docs/specs/s29-record-not-block.md H1, H2,
H3; acceptance 1; C384: "note and record the versions of what we care about, never be blocked when an update occurs").

Classes: [FIX] reproduces a failure the spec fixes (today a host change refuses the next launch, makes a leg in flight INVALID and
stops the run, C360); [INV] preserves an invariant; [NEW] exercises new behaviour. Driver: the frozen B2 sequencer driver
(`b2_frozen_add_support.SeqOps` fakes, fake clock) + the `host_env` seam over a temp `HostWorld` that the REAL
`host_env.fingerprint()` / `diff()` read; "a leg upgrades the host" = the fake mutates the temp Cellar / npm dir right after the chain
launch (inside the leg region). The sequencer code under test is the shared one (tg1 / tg2); the fake chain writes tg1 roots.

ASSUMPTIONS where the spec leaves a mechanism free: the change lists are asserted by the text `host_env.diff` produces for them
(`Homebrew Cellar: added openjdk@17/17.0.9`), found ANYWHERE in the record, never under a field name; "the record tells before from
during" = the two diffs sit in different containers of `leg.json` (no single field holds both)."""
from __future__ import annotations

import json

import pytest

from bench import p426_wave2 as W2
from bench.tests import b2_frozen_add_support as A
from bench.tests.s26_frozen import s26_support as X
from bench.tests.s29_frozen import s29_support as S

OFF_PILOT, ON_PILOT, LAST_LEG = S.OFF_PILOT, S.ON_PILOT, S.LAST_LEG
ADDED, JEST, JDK = S.ADDED, S.JEST, S.JDK


def leg_text(r, leg, attempt=1):
    return (r["base"] / f"{leg}.a{attempt}" / "leg.json").read_text()


# ---------------------------------------------------------------------------------------------------- H1: before a launch
def test_fix_h1_a_host_change_before_a_launch_is_logged_recorded_and_the_leg_launches(tmp_path, monkeypatch):
    """[FIX] H1 / the success trace: the host gains a formula between two legs -> the sequencer logs `host environment differs from
    the baseline before <leg>: <changes>`, LAUNCHES the leg, and the leg's `leg.json` and its sequence entry carry the diff; the
    leg's state is VALID (a host change decides nothing about a leg)."""
    r = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT, before=S.at("on_harvest", OFF_PILOT, S.add_jdk))
    assert r["rc"] == 0, r["err"]
    assert X.legs_run(r) == [OFF_PILOT, ON_PILOT]
    log = X.seq_log(r)
    assert f"host environment differs from the baseline before {ON_PILOT}: " in log and ADDED in log
    assert "STOP: the host environment differs" not in log
    rec = X.leg_json(r, ON_PILOT)
    assert rec["state"] == "VALID" and rec["class"] == "valid" and rec["reason"] == ""
    assert ADDED in leg_text(r, ON_PILOT)
    assert ADDED in json.dumps(S.entry_of(r, ON_PILOT))
    assert S.entry_of(r, ON_PILOT)["state"] == "VALID"
    assert JDK not in leg_text(r, OFF_PILOT)                       # the first leg launched on the baseline host: nothing to record


def test_fix_h1_a_resumed_run_on_a_changed_host_logs_the_diff_and_goes_on(tmp_path, monkeypatch):
    """[FIX] H1 on resume (`host_env_start`): the host differs from the baseline when the sequencer is started again -> logged, the
    next leg launches, its record carries the diff; the run's baseline file is not rewritten."""
    r1 = X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT)
    baseline = (r1["base"] / "host_env.json").read_bytes()
    S.add_jdk(r1["world"])
    r2 = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT, world=r1["world"], records=False)
    assert r2["rc"] == 0, r2["err"]
    assert X.legs_run(r2) == [ON_PILOT]
    assert ADDED in X.seq_log(r2) and "STOP" not in X.seq_log(r2)
    assert ADDED in leg_text(r2, ON_PILOT) and X.leg_json(r2, ON_PILOT)["state"] == "VALID"
    assert (r2["base"] / "host_env.json").read_bytes() == baseline


def test_inv_h1_an_unchanged_host_records_no_host_change_anywhere(tmp_path, monkeypatch):
    """[INV] no false positive: a clean two-leg run has VALID legs and no host change in any leg record, the sequence or the log."""
    r = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT)
    assert r["rc"] == 0, r["err"]
    for leg in (OFF_PILOT, ON_PILOT):
        rec = X.leg_json(r, leg)
        assert rec["state"] == "VALID" and rec["reason"] == "" and "Homebrew" not in leg_text(r, leg)
    assert "Homebrew" not in (r["base"] / "sequence.json").read_text() and "differs" not in X.seq_log(r)


# ---------------------------------------------------------------------------------------------------- H2: during a leg
def test_fix_h2_a_change_during_a_leg_is_recorded_in_leg_json_and_the_leg_stays_valid(tmp_path, monkeypatch):
    """[FIX] H2 / the success trace: a leg during which the host is upgraded is VALID when `classify_leg` says VALID, its sealed
    `leg.json` carries the during-diff, the diff is logged, the leg is harvested and the run goes on to the next leg."""
    r = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT, before=S.at("on_launch", OFF_PILOT, S.add_jdk))
    assert r["rc"] == 0, r["err"]
    assert X.legs_run(r) == [OFF_PILOT, ON_PILOT]
    rec = X.leg_json(r, OFF_PILOT)
    assert rec["state"] == "VALID" and rec["class"] == "valid" and rec["reason"] == ""
    assert ADDED in leg_text(r, OFF_PILOT)
    assert ADDED in X.seq_log(r)
    assert S.entry_of(r, OFF_PILOT)["state"] == "VALID"
    assert r["ops"].harvested[0] == str(r["base"] / f"{OFF_PILOT}.a1")
    from bench import p426_hooks as ph
    assert ph.sealed_ok(json.loads(leg_text(r, OFF_PILOT)))


def test_new_h2_leg_json_tells_what_differed_at_launch_from_what_changed_during_the_leg(tmp_path, monkeypatch):
    """[NEW] H2: "A reader of `leg.json` alone can tell (a) what differed from the run baseline at launch and (b) what changed
    during the leg." The host gains the JDK before the second leg launches and jest during it: the two changes are in `leg.json`,
    in different containers (the during-diff is launch -> end, so it does NOT list the JDK; the launch diff does not list jest)."""
    before = S.at_both(on_harvest=(OFF_PILOT, S.add_jdk), on_launch=(ON_PILOT, S.add_jest))
    r = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT, before=before)
    assert r["rc"] == 0, r["err"]
    doc = X.leg_json(r, ON_PILOT)
    assert doc["state"] == "VALID" and doc["reason"] == ""
    a, b = S.containers(doc, JDK), S.containers(doc, JEST)
    assert a and b, f"the leg record must carry both changes: {doc}"
    assert not (a & b), f"before- and during-leg changes share a field: {a & b}"


@pytest.mark.parametrize("script,state,klass,reason", [
    ({OFF_PILOT: {"rc": 2}}, "INVALID", "systemic", "chain rc 2, status 'finished'"),
    ({OFF_PILOT: {"dnf": 1}}, "VALID_WITH_DNF", "dnf", "1 transport DNF, settled"),
], ids=["crashed-chain-stays-invalid", "settled-dnf-stays-valid-with-dnf"])
def test_fix_h2_the_state_reason_and_class_come_only_from_classify_leg(tmp_path, monkeypatch, script, state, klass, reason):
    """[FIX] H2 + "failure path kept": with the host upgraded during the leg, `state` / `reason` / `class` are `classify_leg`'s: a
    crashed chain stays INVALID with ITS reason (no host phrase, no `(prior: ...)` wrapper), a settled-DNF leg stays VALID_WITH_DNF;
    the during-diff is recorded beside it."""
    r = X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT, script=script, before=S.at("on_launch", OFF_PILOT, S.add_jdk))
    rec = X.leg_json(r, OFF_PILOT)
    assert (rec["state"], rec["class"], rec["reason"]) == (state, klass, reason)
    assert ADDED in leg_text(r, OFF_PILOT)
    assert S.entry_of(r, OFF_PILOT)["state"] == state
    assert S.HOST_REASON not in json.dumps(S.entry_of(r, OFF_PILOT))


def test_fix_h2_a_crashed_chain_is_still_stopped_for_its_own_reason_not_the_host(tmp_path, monkeypatch):
    """[FIX] "failure path kept": the operator-decision stop of an INVALID leg stays (a rerun is the operator's call), and it names
    the chain, not the host (today the stop message is "is INVALID: host environment changed ...")."""
    r = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT, script={OFF_PILOT: {"rc": 2}},
                before=S.at("on_launch", OFF_PILOT, S.add_jdk))
    assert r["rc"] == 1 and X.legs_run(r) == [OFF_PILOT]
    log = X.seq_log(r)
    assert "a rerun is an operator decision" in log or "INVALID" in log
    assert "is INVALID: host environment" not in log


def test_fix_h2_a_leg_upgrade_never_makes_the_next_rerun_refuse(tmp_path, monkeypatch):
    """[FIX] (replaces "a rerun refuses until the host equals the baseline again"): after a leg that saw an upgrade, the host stays
    changed and a `--rerun` of a crashed leg launches at once; the new attempt's record carries the diff."""
    r1 = X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT, script={OFF_PILOT: {"rc": 2}},
                 before=S.at("on_launch", OFF_PILOT, S.add_jdk))
    assert r1["rc"] == 1
    r2 = X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT, "--rerun", OFF_PILOT, "--rerun-reason", "crash",
                 world=r1["world"], records=False)
    assert r2["rc"] == 0, r2["err"]
    assert X.legs_run(r2) == [OFF_PILOT]
    assert X.leg_json(r2, OFF_PILOT, attempt=2)["state"] == "VALID" and ADDED in leg_text(r2, OFF_PILOT, 2)


# ---------------------------------------------------------------------------------------------------- H3: entry / exit / exception
def test_fix_h3_a_change_after_the_last_leg_is_recorded_logged_and_the_run_completes(tmp_path, monkeypatch):
    """[FIX] H3 (`host_env_final`, DONE exit): rc 0, `DONE` logged, the change is logged and is in `sequence.json` by the time the run
    files are published; the run files ARE published."""
    r = X.drive(tmp_path, monkeypatch, "run", before=S.at("on_harvest", LAST_LEG, S.add_jdk))
    assert r["rc"] == 0, r["err"]
    assert len(X.legs_run(r)) == 8
    log = X.seq_log(r)
    assert "DONE" in log and ADDED in log and "STOP" not in log
    assert ADDED in (r["base"] / "sequence.json").read_text()
    assert r["ops"].publishes and all(p is not None and ADDED in p for p in r["ops"].publishes)


def test_fix_h3_a_change_after_the_through_leg_is_recorded_and_the_run_stops_as_asked(tmp_path, monkeypatch):
    """[FIX] H3 (`host_env_final`, `--through` exit)."""
    r = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT, before=S.at("on_harvest", ON_PILOT, S.add_jdk))
    assert r["rc"] == 0, r["err"]
    log = X.seq_log(r)
    assert "stopping as asked" in log and ADDED in log and "STOP" not in log
    assert ADDED in (r["base"] / "sequence.json").read_text()
    assert r["ops"].publishes and all(p is not None and ADDED in p for p in r["ops"].publishes)


def test_inv_h3_an_unchanged_end_records_nothing_and_returns_as_before(tmp_path, monkeypatch):
    """[INV] no change after the last leg: rc 0, `DONE`, no host text in the published sequence."""
    r = X.drive(tmp_path, monkeypatch, "run")
    assert r["rc"] == 0 and "DONE" in X.seq_log(r)
    assert r["ops"].publishes and all("Homebrew" not in p for p in r["ops"].publishes)


def test_inv_h3_an_exception_in_the_leg_region_logs_the_diff_and_still_propagates_as_itself(tmp_path, monkeypatch):
    """[INV] the exception path records and logs; it does not wrap or swallow the exception (an exception is not a host change)."""
    def boom(root, rc, *, arm):
        raise RuntimeError("classify boom")
    monkeypatch.setattr(W2, "classify_leg", boom)
    with pytest.raises(RuntimeError, match="classify boom"):
        X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT, before=S.at("on_launch", OFF_PILOT, S.add_jdk))
    assert ADDED in (tmp_path / "wd/p426/wave2/sequence.log").read_text()


def test_fix_h3_after_leg_no_longer_stops_on_a_host_reason(tmp_path, monkeypatch):
    """[FIX] H3: "`after_leg` no longer stops on a host reason". A rehearsal leg that EXPECTS INVALID, recorded INVALID with the
    host phrase (and a prior reason), used to raise `Stop` ("is INVALID: host environment changed ..."); now it is judged by its own
    expectation like any INVALID leg."""
    argv, wts = A.seq_argv(tmp_path, "rehearsal", "--manifest", str(tmp_path / "m.json"))
    wd = tmp_path / "wd"
    wd.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    clock = A.Clock()
    ops = X.HostSeqOps(clock, None, main_root=tmp_path / "main", emails=("op.erator@corp-mail.example",), world=X.HostWorld(tmp_path / "host"))
    seq = W2.Sequencer(W2.parse_args(argv), ops, clock.clock, clock.sleep, wd)
    (spec,) = [s for s in seq.legs() if s["expect"] == "INVALID"][:1]
    entry = dict(leg=spec["name"], attempt=1, state="INVALID",
                 reason=f"{S.HOST_REASON}: {ADDED} (prior: chain rc 2, status 'finished')")
    seq.after_leg(spec, entry)                                           # must not raise Stop
    assert "as the rehearsal expects" in X.seq_log(dict(base=wd / "p426/rehearsal"))


# ---------------------------------------------------------------------------------------------------- the run baseline
def test_inv_the_baseline_is_first_check_and_never_rewritten_by_a_host_change(tmp_path, monkeypatch):
    """[INV] "the run's baseline stays the first-check baseline; it is not rewritten": after changes before, during and after the
    legs, `host_env.json` is byte-identical to what the first run wrote."""
    r1 = X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT)
    first = (r1["base"] / "host_env.json").read_bytes()
    r2 = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT, world=r1["world"], records=False,
                 before=S.at_both(on_launch=(ON_PILOT, S.add_jdk), on_harvest=(ON_PILOT, S.add_jest)))
    assert r2["rc"] == 0, r2["err"]
    assert (r2["base"] / "host_env.json").read_bytes() == first


@pytest.mark.parametrize("damage", ["garbage", "tampered-fingerprint"])
def test_inv_an_unreadable_or_tampered_baseline_still_stops_before_any_launch(tmp_path, monkeypatch, damage):
    """[INV] a damaged baseline is not a host change (no hand-edited records; sealed records stay verifiable): rc 1, nothing launched."""
    def damaged(ops, clock):
        base = tmp_path / "wd/p426/wave2"
        base.mkdir(parents=True)
        if damage == "garbage":
            (base / "host_env.json").write_text("{not json")
            return
        from bench import p426_hooks as ph
        ph.write_exclusive(base / "host_env.json", dict(kind="host_env", fingerprint=ops.world.fingerprint(), created="t0"))
        doc = json.loads((base / "host_env.json").read_text())
        doc["fingerprint"]["cellar"] = list(doc["fingerprint"]["cellar"]) + ["x/9"]
        (base / "host_env.json").write_text(json.dumps(doc))
    r = X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT, before=damaged)
    assert r["rc"] == 1 and not r["ops"].launches
