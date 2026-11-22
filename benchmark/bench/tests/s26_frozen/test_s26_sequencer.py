"""S26 frozen tests, the Wave 2 sequencer's host guard (spec §2; acceptance 1: baseline written once, pre-launch refusal, post-leg
INVALID with reason and class, exception-path check, end-of-run check on both exits before publishing, a resumed run with a changed
host, an exception inside the leg region, `host_env.json` published (run) / kept (rehearsal), fakes without the seam unchanged,
`BoxSeqOps.host_env` exists).

Classes: [FIX] reproduces a failure the spec fixes (a leg that changed the host went unnoticed and its row was graded); [INV]
preserves an invariant; [NEW] new behaviour. Driver: the frozen B2 sequencer driver (`b2_frozen_add_support.SeqOps` fakes, fake
clock) + the `host_env` seam over a temp `HostWorld`; "a leg mutates the host" = the fake mutates the temp Cellar right after the
chain launch (inside the leg region). On the baseline the guard does not exist, so the [FIX] / [NEW] tests fail there."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.tests import b2_frozen_add_support as A
from bench.tests.s26_frozen import s26_support as X

OFF_PILOT, ON_PILOT = "tg1-p426-off-pilot", "tg1-p426-on-pilot"
LAST_LEG = "tg1-p426-off-reload"
ADDED = "Homebrew Cellar: added openjdk@17/17.0.9"


def mutate(world):
    world.formula("openjdk@17", "17.0.9")


def revert(world):
    world.rm_formula("openjdk@17", "17.0.9")


def at(attr, leg, action):
    """`before=` hook: run `action(world)` at the named seam of the named leg (`on_launch` / `on_harvest`)."""
    def before(ops, clock):
        setattr(ops, attr, lambda name: action(ops.world) if name == leg else None)
    return before


def host_json(r):
    return json.loads((r["base"] / "host_env.json").read_text())


# ---------------------------------------------------------------------------------------------------- baseline
def test_new_the_baseline_is_written_before_the_first_leg(tmp_path, monkeypatch):
    """[NEW] §2 Baseline: at `Sequencer.run()` entry, before the first leg: `<out-base>/host_env.json` =
    `{kind: "host_env", fingerprint, created}`."""
    seen = []

    def before(ops, clock):
        launch = ops.launch

        def spy(argv, **kw):
            seen.append((tmp_path / "wd/p426/wave2/host_env.json").exists())
            return launch(argv, **kw)
        ops.launch = spy
    r = X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT, before=before)
    assert r["rc"] == 0, r["err"]
    assert seen and seen[0] is True
    doc = host_json(r)
    assert doc["kind"] == "host_env" and doc["fingerprint"] == r["world"].fingerprint() and doc["created"]


def test_new_a_resumed_run_keeps_the_first_baseline_byte_for_byte(tmp_path, monkeypatch):
    """[NEW] §2: the first run of an out-base writes it (exclusive); a resume compares and never rewrites."""
    r1 = X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT)
    first = (r1["base"] / "host_env.json").read_bytes()
    r2 = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT, world=r1["world"], records=False)
    assert r2["rc"] == 0, r2["err"]
    assert (r2["base"] / "host_env.json").read_bytes() == first
    assert X.legs_run(r2) == [ON_PILOT]


def test_inv_an_unchanged_host_marks_no_leg_and_adds_no_reason(tmp_path, monkeypatch):
    """[INV] no false positive: every leg of a clean run is VALID with an empty reason; the guard calls the seam around each leg."""
    r = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT)
    assert r["rc"] == 0, r["err"]
    for leg in (OFF_PILOT, ON_PILOT):
        rec = X.leg_json(r, leg)
        assert rec["state"] == "VALID" and rec["reason"] == ""
    assert "host environment" not in (r["base"] / "sequence.json").read_text()
    assert r["ops"].host_calls >= 4                      # a check before and after each of the two legs


@pytest.mark.parametrize("content", ["{not json", ""], ids=["garbage", "empty"])
def test_new_an_unreadable_baseline_stops_with_rc_1_before_any_launch(tmp_path, monkeypatch, content):
    """[NEW] §2: an unreadable baseline stops (rc 1); nothing launched."""
    def damaged(ops, clock):
        base = tmp_path / "wd/p426/wave2"
        base.mkdir(parents=True)
        (base / "host_env.json").write_text(content)
    r = X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT, before=damaged)
    assert r["rc"] == 1 and not r["ops"].launches


# ---------------------------------------------------------------------------------------------------- before every launch
def test_fix_a_host_change_between_legs_refuses_the_next_launch(tmp_path, monkeypatch):
    """[FIX] §2: a difference before a launch -> `Stop(1)`, the exact message, nothing launched. S29 H1 (C384): changed — the
    difference is logged and recorded with the leg (its sequence entry and leg.json), and the leg launches."""
    r = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT, before=at("on_harvest", OFF_PILOT, mutate))
    assert r["rc"] == 0 and X.legs_run(r) == [OFF_PILOT, ON_PILOT]
    assert f"host environment differs from the baseline before {ON_PILOT}: {ADDED}" in X.seq_log(r)
    assert [e.get("host_env_before") for e in X.sequence(r)["legs"] if e["leg"] == ON_PILOT] == [[ADDED]]
    assert X.leg_json(r, ON_PILOT)["host_env_before"] == [ADDED]
    assert X.leg_json(r, OFF_PILOT)["state"] == "VALID"       # the first leg ended before the change (the post-leg check was clean)


def test_inv_the_pre_launch_check_comes_after_the_power_check(tmp_path, monkeypatch):
    """[INV] §2: "after the power check": with bad power and a changed host the power refusal is the one reported."""
    def before(ops, clock):
        def after_first(leg):
            mutate(ops.world)
            ops.power = lambda: dict(A.GOOD_POWER, watts=100)
        ops.on_harvest = lambda leg: after_first(leg) if leg == OFF_PILOT else None
    r = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT, before=before)
    assert r["rc"] == 1 and X.legs_run(r) == [OFF_PILOT]
    log = X.seq_log(r)
    assert "STOP: power" in log and "differs from the run's baseline" not in log


def test_fix_a_resumed_run_on_a_changed_host_stops_before_launching(tmp_path, monkeypatch):
    """[FIX] §2: a resumed run compares the live fingerprint to the baseline first and stops on a difference (the message as the
    pre-launch refusal, the leg = the next leg); once the host equals the baseline again it goes on. S29 H3 (C384): changed —
    the resumed run records and logs the difference and launches the next leg on the changed host."""
    r1 = X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT)
    mutate(r1["world"])
    r2 = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT, world=r1["world"], records=False)
    assert r2["rc"] == 0 and X.legs_run(r2) == [ON_PILOT]
    assert f"host environment differs from the baseline at the run's start (next: {ON_PILOT}): {ADDED}" in X.seq_log(r2)
    assert [e["changes"] for e in X.sequence(r2)["host_env_events"]] == [[ADDED]]
    revert(r1["world"])


# ---------------------------------------------------------------------------------------------------- after every leg
def test_fix_a_leg_that_changed_the_host_is_invalid_systemic_with_the_diff_as_reason(tmp_path, monkeypatch):
    """[FIX] §2 / the traced case "a leg runs `brew install openjdk@17`": INVALID, class systemic, the reason, in `leg.json` and
    `sequence.json`; the leg is harvested as INVALID legs are; the run stops (rc 1) before the next leg. S29 H2 (C384): changed —
    the state is the classifier's (VALID), the change is recorded in leg.json (`host_env_during`), harvested, the run goes on."""
    r = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT, before=at("on_launch", OFF_PILOT, mutate))
    assert r["rc"] == 0 and X.legs_run(r) == [OFF_PILOT, ON_PILOT]
    rec = X.leg_json(r, OFF_PILOT)
    assert rec["state"] == "VALID" and rec["class"] == "valid" and rec["reason"] == ""
    assert rec["host_env_during"] == [ADDED]
    assert [e["state"] for e in X.sequence(r)["legs"] if e["leg"] == OFF_PILOT] == ["VALID"]
    assert "host environment changed during the leg" not in (r["base"] / "sequence.json").read_text()
    assert r["ops"].harvested[0] == str(r["base"] / f"{OFF_PILOT}.a1")
    assert any(h["attempt"] == f"{OFF_PILOT}.a1" for h in X.sequence(r)["harvested"])


def test_fix_several_changes_are_joined_with_semicolons(tmp_path, monkeypatch):
    """S29 H2 (C384): changed — the changes are the recorded list (and the log line joins them with semicolons)."""
    def both(world):
        mutate(world)
        world.npm_pkg("jest", "29.7.0")
    r = X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT, before=at("on_launch", OFF_PILOT, both))
    rec = X.leg_json(r, OFF_PILOT)
    assert rec["reason"] == "" and ADDED in rec["host_env_during"] and "npm -g jest: absent -> 29.7.0" in rec["host_env_during"]
    line = next(x for x in X.seq_log(r).splitlines() if f"host environment changed during {OFF_PILOT}.a1: " in x)
    assert ADDED in line and "npm -g jest: absent -> 29.7.0" in line and "; " in line


def test_fix_a_prior_reason_is_kept_in_parentheses(tmp_path, monkeypatch):
    """[FIX] §2 (GLM F2, F13): ` (prior: <reason>)` when the leg already had a reason (a chain rc 2 leg). S29 H2 (C384): changed —
    the classifier's reason is the reason; the host change is recorded beside it."""
    r = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT, script={OFF_PILOT: {"rc": 2}},
                before=at("on_launch", OFF_PILOT, mutate))
    rec = X.leg_json(r, OFF_PILOT)
    assert rec["state"] == "INVALID"
    assert rec["reason"] == "chain rc 2, status 'finished'" and rec["host_env_during"] == [ADDED]


def test_fix_a_settled_dnf_leg_is_not_spared(tmp_path, monkeypatch):
    """[FIX] a VALID_WITH_DNF leg whose host changed is INVALID too (the check is on the normal path of every state), prior kept.
    S29 H2 (C384): changed — it stays VALID_WITH_DNF (the classifier's state), the change recorded."""
    r = X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT, script={OFF_PILOT: {"dnf": 1}},
                before=at("on_launch", OFF_PILOT, mutate))
    rec = X.leg_json(r, OFF_PILOT)
    assert rec["state"] == "VALID_WITH_DNF" and rec["class"] == "dnf"
    assert rec["host_env_during"] == [ADDED]


def test_fix_a_rerun_after_an_invalid_host_leg_refuses_until_the_host_equals_the_baseline(tmp_path, monkeypatch):
    """[FIX] traced case: "a rerun first refuses before launch until the host equals the baseline again". S29 H1 / H2 (C384):
    changed — no leg is INVALID by a host change and no launch is refused; the leg ends VALID and the run goes on."""
    r1 = X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT, before=at("on_launch", OFF_PILOT, mutate))
    assert r1["rc"] == 0 and X.leg_json(r1, OFF_PILOT)["state"] == "VALID"
    r2 = X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT, "--rerun", OFF_PILOT, "--rerun-reason", "host drift",
                 world=r1["world"], records=False)
    assert r2["rc"] == 0 and X.legs_run(r2) == [OFF_PILOT] and "differs from the baseline before" in X.seq_log(r2)
    assert X.leg_json(r2, OFF_PILOT, attempt=2)["state"] == "VALID"


# ---------------------------------------------------------------------------------------------------- the exception path
def _boom_in_the_leg_region(monkeypatch):
    from bench import p426_wave2

    def boom(root, rc, *, arm):
        raise RuntimeError("classify boom")
    monkeypatch.setattr(p426_wave2, "classify_leg", boom)


def test_new_an_exception_inside_the_leg_region_is_checked_logged_and_reraised_unchanged(tmp_path, monkeypatch):
    """[NEW] §2 (GLM F1): the `try/finally` spans launch .. `leg.json`; on an exception the `finally` logs "unchanged" and the
    exception propagates as itself (no `Stop`, no wrapping)."""
    _boom_in_the_leg_region(monkeypatch)
    with pytest.raises(RuntimeError, match="classify boom"):
        X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT)
    log = (tmp_path / "wd/p426/wave2/sequence.log").read_text()
    assert "unchanged" in log and "host environment changed" not in log
    assert not (tmp_path / "wd/p426/wave2" / f"{OFF_PILOT}.a1" / "leg.json").exists()


def test_new_an_exception_with_a_changed_host_logs_the_diff_and_still_reraises(tmp_path, monkeypatch):
    _boom_in_the_leg_region(monkeypatch)
    with pytest.raises(RuntimeError, match="classify boom"):
        X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT, before=at("on_launch", OFF_PILOT, mutate))
    assert ADDED in (tmp_path / "wd/p426/wave2/sequence.log").read_text()


# ---------------------------------------------------------------------------------------------------- the end-of-run check
def test_fix_a_change_after_the_last_leg_is_caught_before_the_run_files_are_published(tmp_path, monkeypatch):
    """[FIX] §2 Finalization, DONE exit (Sol P3, GLM F4): the diff is saved as `host_env_after_last_leg`, the run stops rc 1 with
    the message, `DONE` is never logged, and `sequence.json` carries the diff by the time anything is published. S29 H3 (C384):
    changed — recorded before publication and logged; the run ends normally (rc 0, `DONE`)."""
    r = X.drive(tmp_path, monkeypatch, "run", before=at("on_harvest", LAST_LEG, mutate))
    assert r["rc"] == 0 and len(X.legs_run(r)) == 8
    assert X.sequence(r)["host_env_after_last_leg"] == [ADDED]
    log = X.seq_log(r)
    assert f"host environment differs from the baseline after the last leg: {ADDED}" in log and "DONE" in log
    assert all(p is not None and "host_env_after_last_leg" in p for p in r["ops"].publishes)


def test_fix_a_change_after_the_through_leg_is_caught_on_the_through_exit(tmp_path, monkeypatch):
    """[FIX] §2 Finalization, the `--through` exit. S29 H3 (C384): changed — recorded, logged, "stopping as asked", rc 0."""
    r = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT, before=at("on_harvest", ON_PILOT, mutate))
    assert r["rc"] == 0 and X.legs_run(r) == [OFF_PILOT, ON_PILOT]
    assert X.sequence(r)["host_env_after_last_leg"] == [ADDED]
    log = X.seq_log(r)
    assert "host environment differs from the baseline after the last leg" in log and "stopping as asked" in log
    assert all(p is not None and "host_env_after_last_leg" in p for p in r["ops"].publishes)


def test_inv_an_unchanged_end_publishes_logs_and_returns_as_before(tmp_path, monkeypatch):
    """[INV] §2: no difference -> publish, log, return as today (rc 0, `DONE` / "stopping as asked", no `host_env_after_last_leg`)."""
    full = X.drive(tmp_path / "full", monkeypatch, "run")
    assert full["rc"] == 0 and "DONE" in X.seq_log(full) and "host_env_after_last_leg" not in X.sequence(full)
    assert full["ops"].publishes and all("host_env_after_last_leg" not in p for p in full["ops"].publishes)
    part = X.drive(tmp_path / "part", monkeypatch, "run", "--through", OFF_PILOT)
    assert part["rc"] == 0 and "stopping as asked" in X.seq_log(part)


# ---------------------------------------------------------------------------------------------------- publication
def test_new_host_env_json_is_published_with_the_run_files_of_a_run(tmp_path, monkeypatch):
    """[NEW] §2 (r1 P4): `run` publishes `host_env.json` with the other run files."""
    r = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT)
    published = {Path(p) for paths, _ in r["ops"].run_files for p in paths}
    assert r["base"] / "host_env.json" in published and r["base"] / "sequence.json" in published


def test_inv_a_rehearsal_keeps_host_env_json_in_its_out_base_and_publishes_nothing(tmp_path, monkeypatch):
    """[INV] §2: "A rehearsal keeps it in its out-base"."""
    from bench.tests import b2_frozen_support as S

    def manifest(ops, clock):
        S.write_record(tmp_path / "rehearsal.json", S.rehearsal_manifest(tmp_path / "wd/p426/rehearsal"))
    r = X.drive(tmp_path, monkeypatch, "rehearsal", "--manifest", str(tmp_path / "rehearsal.json"), records=False, before=manifest,
                script={"tg1-p426-rehearsal-mismatch": {"rc": 2}})
    assert r["rc"] in (0, 1), r["err"]
    assert (r["base"] / "host_env.json").is_file() and r["ops"].run_files == [] and r["ops"].chain_launches()


# ---------------------------------------------------------------------------------------------------- the seam
def test_inv_fakes_without_the_seam_run_exactly_as_before(tmp_path, monkeypatch):
    """[INV] §2: "Fakes may omit the seam": the frozen `SeqOps` has no `host_env`; the run is as on the baseline (no guard, no file)."""
    assert not hasattr(A.SeqOps, "host_env")
    r = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT, ops_cls=A.SeqOps)
    assert r["rc"] == 0, r["err"]
    assert X.legs_run(r) == [OFF_PILOT, ON_PILOT]
    assert not (r["base"] / "host_env.json").exists()
    assert all(X.leg_json(r, leg)["state"] == "VALID" for leg in (OFF_PILOT, ON_PILOT))


def test_new_the_real_ops_have_the_seam_and_it_is_the_box_fingerprint(tmp_path, monkeypatch):
    """[NEW] §2: `BoxSeqOps.host_env()` -> `host_env.fingerprint_for_run()` (the real ops always have it)."""
    from bench import host_env
    from bench import p426_wave2 as W2
    sentinel = {"tools": {}, "sentinel": True}
    monkeypatch.setattr(host_env, "fingerprint_for_run", lambda: sentinel)
    ops = W2.BoxSeqOps(tmp_path, main_root=tmp_path / "main", evidence_stage=tmp_path / "ev")
    assert callable(getattr(ops, "host_env", None)) and ops.host_env() is sentinel
    kv = W2.BoxSeqOps(tmp_path, main_root=tmp_path / "main", evidence_stage=tmp_path / "ev", lever="kv", corpus="tg2")
    assert kv.host_env() is sentinel


# ---------------------------------------------------------------------------------------------------- the kv lever (the tg2 / kv path)
def sealed_baseline(path, fingerprint):
    """A baseline as the sequencer writes it: a SEALED record (spec erratum v1.1c 10)."""
    from bench import p426_hooks as ph
    ph.write_exclusive(path, dict(kind="host_env", fingerprint=fingerprint, created="t0"))


def _kv_resume(tmp_path, monkeypatch, write_baseline, *, changed):
    """A resumed lever-kv run whose out-base already holds a baseline written by `write_baseline(path, fingerprint)`; the host is
    mutated first when `changed`. Returns (rc, err, ops, log text)."""
    from bench import p426_freeze as fz
    from bench import p426_hooks as ph
    wd = tmp_path / "wd"
    wd.mkdir()
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    rec = tmp_path / "records"
    rec.mkdir()
    ph.write_exclusive(rec / "v8_base.json", dict(kind=fz.KIND_V8, lever="kv", arms=["n16", "x"], build="s3", n16_commit="1" * 40,
                                                  x_commit="2" * 40, probe_code_sha256="a" * 64, scaffold_policy_sha256="b" * 64,
                                                  frozen_prompt_date="Fri Nov 13 2026"))
    base = wd / "m76" / "p426" / "wave2"
    base.mkdir(parents=True)
    world = X.HostWorld(tmp_path / "host")
    write_baseline(base / "host_env.json", world.fingerprint())
    if changed:
        mutate(world)
    clock = A.Clock()
    ops = X.HostSeqOps(clock, None, main_root=tmp_path / "main", emails=("op.erator@corp-mail.example",), world=world)
    argv = ["run", "--lever", "kv", "--pair", "n16,x", "--arm-worktree", f"n16={wd}/a", "--arm-worktree", f"x={wd}/b", "--out-base",
            str(base), "--record-dir", str(rec)]
    rc, err = A.run_sequencer(argv, ops, clock)
    log = base / "sequence.log"
    return rc, err, ops, log.read_text() if log.exists() else ""


def test_fix_the_kv_lever_sequencer_guards_the_host_too(tmp_path, monkeypatch):
    """[FIX] review gap: `Sequencer.run` is shared by the lever-kv (and tg2) runs. A resumed kv run on a changed host stops before
    launching, with the pre-launch message naming the kv leg that was next (the SEALED baseline reads back, so the comparison
    really runs). The kv first-run / post-leg path needs frozen kv records and chain fakes that the frozen test base lacks.
    S29 H3 (C384): changed — the resumed kv run records and logs the difference instead of stopping on it and reaches its first
    leg (`process` is stubbed there: the post-check path needs kv records this frozen base lacks)."""
    from bench import p426_wave2 as W2

    class Reached(Exception):
        pass
    reached = []

    def process(self, spec):
        reached.append(spec["name"])
        raise Reached(spec["name"])
    monkeypatch.setattr(W2.Sequencer, "process", process)
    with pytest.raises(Reached):
        _kv_resume(tmp_path, monkeypatch, sealed_baseline, changed=True)
    assert reached == ["tg1-m76-n16-pilot"]                     # past the host check, at the kv leg that was next
    log = (tmp_path / "wd" / "m76" / "p426" / "wave2" / "sequence.log").read_text()
    assert W2.kv_legs("n16", "x")["run"][0]["name"] == "tg1-m76-n16-pilot"
    assert f"host environment differs from the baseline at the run's start (next: tg1-m76-n16-pilot): {ADDED}" in log
    events = json.loads((tmp_path / "wd" / "m76" / "p426" / "wave2" / "sequence.json").read_text())["host_env_events"]
    assert [e["changes"] for e in events] == [[ADDED]]
    assert "differs from the run's baseline" not in log and "(nothing launched)" not in log
    assert not [line for line in log.splitlines() if "STOP:" in line and "host" in line]


@pytest.mark.parametrize("damage", ["unsealed", "tampered-created", "tampered-fingerprint", "garbage"])
@pytest.mark.parametrize("changed", [False, True], ids=["host-unchanged", "host-changed"])
def test_new_an_unsealed_or_tampered_baseline_stops_with_rc_1(tmp_path, monkeypatch, damage, changed):
    """[NEW] erratum v1.1c 10: the baseline is sealed; one that is unsealed, whose seal does not verify (edited after sealing, even
    to equal the live host), or unreadable stops (rc 1) before any launch - whether or not the host changed."""
    def write(path, fingerprint):
        if damage == "unsealed":
            path.write_text(json.dumps(dict(kind="host_env", fingerprint=fingerprint, created="t0")))
            return
        if damage == "garbage":
            path.write_text("{not json")
            return
        sealed_baseline(path, fingerprint)
        doc = json.loads(path.read_text())
        if damage == "tampered-created":
            doc["created"] = "t1"
        else:
            doc["fingerprint"]["cellar"] = list(doc["fingerprint"]["cellar"]) + ["x/9"]
        path.write_text(json.dumps(doc))
    rc, err, ops, log = _kv_resume(tmp_path, monkeypatch, write, changed=changed)
    assert rc == 1, err
    assert not ops.launches
    assert "host_env.json" in log and "differs from the run's baseline" not in log
