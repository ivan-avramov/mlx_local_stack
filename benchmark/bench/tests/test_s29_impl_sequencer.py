"""S29 (C384) implementer tests, the Wave 2 sequencer: a host change is recorded, never blocking (H1 before a launch, H2 during a
leg, H3 run entry / exit / exception, `after_leg`), and H5: a leg recorded INVALID by the C360 host guard (no prior, unharvested)
takes the state its own records give on resume. Hermetic B2 s8 world (fake ops, fake clock) + the `host_env` seam; the host
changes are real `host_env.diff()` output over fingerprint-shaped dicts."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from bench import host_env as he
from bench import p426_freeze as fz
from bench import p426_hooks as ph
from bench import p426_wave2 as w2
from bench.tests.test_b2_s8_wave2 import LEGS, go, leg_doc, seq, world, rehearsal, go_rehearsal  # noqa: F401  (fixtures)
from bench.tests.test_s26_impl_sequencer import BASE, JDK17, install_jdk17, log_of, seam

OFF_S1 = "tg1-p426-off-s1"


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ----------------------------------------------------------------------------------------------- H1: before a launch
def test_h1_a_change_between_legs_is_logged_recorded_and_the_next_leg_launches(world):
    state = seam(world)
    harvest = world.ops.harvest

    def harvest_then_install(root, *, emails):
        res = harvest(root, emails=emails)
        if Path(root).name == "tg1-p426-off-pilot.a1":
            install_jdk17(state)
        return res
    world.ops.harvest = harvest_then_install
    assert go(world) == 0
    assert world.ops.names() == LEGS                                        # every leg launched
    log = log_of(world)
    assert "host environment differs from the baseline before tg1-p426-on-pilot: " + JDK17 in log
    entries = {e["leg"]: e for e in seq(world)["legs"]}
    assert "host_env_before" not in entries["tg1-p426-off-pilot"]
    assert entries["tg1-p426-on-pilot"]["host_env_before"] == [JDK17]
    d = leg_doc(world, "tg1-p426-on-pilot.a1")
    assert d["state"] == "VALID" and d["reason"] == "" and d["host_env_before"] == [JDK17] and d["host_env_during"] == []
    assert ph.sealed_ok(d)
    first = leg_doc(world, "tg1-p426-off-pilot.a1")
    assert first["host_env_before"] == [] and first["host_env_during"] == []
    assert "STOP" not in log


# ----------------------------------------------------------------------------------------------- H2: during a leg
def test_h2_a_change_during_a_leg_is_recorded_in_its_leg_json_and_the_state_is_the_classifiers(world):
    state = seam(world)
    world.ops.on_launch = lambda ops, name, root: install_jdk17(state) if name == OFF_S1 else None
    assert go(world) == 0
    assert world.ops.names() == LEGS and world.ops.names("harvest") == LEGS
    d = leg_doc(world, f"{OFF_S1}.a1")
    assert d["state"] == "VALID" and d["class"] == "valid" and d["reason"] == ""
    assert d["host_env_before"] == [] and d["host_env_during"] == [JDK17] and ph.sealed_ok(d)
    assert f"host environment changed during {OFF_S1}.a1: {JDK17}" in log_of(world)
    entry = [e for e in seq(world)["legs"] if e["leg"] == OFF_S1][-1]
    assert entry["state"] == "VALID" and entry["host_env_during"] == [JDK17] and "reason" not in entry
    nxt = leg_doc(world, "tg1-p426-on-s1.a1")                                # the change stays: the next leg's before-diff
    assert nxt["host_env_before"] == [JDK17] and nxt["host_env_during"] == []


def test_h2_the_classifiers_invalid_keeps_its_own_reason_with_the_host_change_beside_it(world):
    state = seam(world)
    world.ops.scenario[OFF_S1] = dict(rc=2, status="invalidated", invalid=[dict(stage="done", slot="s", reason="engagement", at="t")])
    world.ops.on_launch = lambda ops, name, root: install_jdk17(state) if name == OFF_S1 else None
    assert go(world) == 1                                                    # the classifier's INVALID still stops
    d = leg_doc(world, f"{OFF_S1}.a1")
    assert d["state"] == "INVALID" and d["class"] == "systemic" and d["reason"] == "engagement"
    assert d["host_env_during"] == [JDK17]
    assert f"STOP: {OFF_S1}.a1 is INVALID (a rerun is an operator decision)" in log_of(world)


def test_h2_without_the_seam_the_leg_record_is_as_before(world):
    assert go(world, "--through", "1") == 0
    d = leg_doc(world, "tg1-p426-off-pilot.a1")
    assert "host_env_before" not in d and "host_env_during" not in d
    assert seq(world)["legs"][-1] == dict(leg="tg1-p426-off-pilot", attempt=1, state="VALID")


# ----------------------------------------------------------------------------------------------- H3: entry / exit / exception
def test_h3_a_resumed_run_on_a_changed_host_records_logs_and_launches(world):
    state = seam(world)
    assert go(world, "--through", "1") == 0
    baseline = (world.out / w2.HOST_ENV_FILE).read_bytes()
    install_jdk17(state)
    world.clock.t += 3600
    assert go(world, "--through", "2") == 0
    assert world.ops.names() == LEGS[:2]
    assert (world.out / w2.HOST_ENV_FILE).read_bytes() == baseline          # the first-check baseline is never rewritten
    events = seq(world)["host_env_events"]
    assert [e["changes"] for e in events] == [[JDK17]] and "run's start" in events[0]["where"]
    assert "host environment differs from the baseline at the run's start" in log_of(world)


@pytest.mark.parametrize("through", [None, "2"], ids=["done-exit", "through-exit"])
def test_h3_a_change_after_the_last_leg_is_recorded_before_publication_and_the_run_ends_normally(world, through):
    state = seam(world)
    last = "tg1-p426-on-pilot.a1" if through else "tg1-p426-off-reload.a1"
    harvest = world.ops.harvest

    def harvest_then_install(root, *, emails):
        res = harvest(root, emails=emails)
        if Path(root).name == last:
            install_jdk17(state)
        return res
    world.ops.harvest = harvest_then_install
    seen = []
    publish = world.ops.publish_run_files

    def snap(paths, *, emails):
        seen.append(json.loads((world.out / "sequence.json").read_text()))
        return publish(paths, emails=emails)
    world.ops.publish_run_files = snap
    assert go(world, *(("--through", through) if through else ())) == 0
    assert seq(world)["host_env_after_last_leg"] == [JDK17]
    assert seen and all(s.get("host_env_after_last_leg") == [JDK17] for s in seen)
    log = log_of(world)
    assert "host environment differs from the baseline after the last leg: " + JDK17 in log
    assert ("DONE:" in log) if through is None else ("stopping as asked" in log)


def test_h3_an_exception_with_a_changed_host_is_logged_recorded_and_propagates(world):
    state = seam(world)

    def wait(handle):
        install_jdk17(state)
        raise RuntimeError("boom in wait")
    world.ops.wait = wait
    with pytest.raises(RuntimeError, match="boom in wait"):
        go(world)
    assert "tg1-p426-off-pilot.a1: an exception left the leg; the host environment changed: " + JDK17 in log_of(world)
    (event,) = seq(world)["host_env_events"]
    assert event["changes"] == [JDK17] and "exception" in event["where"]


def test_h3_a_rehearsal_leg_expected_invalid_continues_after_a_host_change(rehearsal):
    w = rehearsal.w
    state = seam(w)
    w.ops.scenario["tg1-p426-rehearsal-mismatch"] = dict(rc=2, status="invalidated", items=1,
                                                         invalid=[dict(stage="done", slot="s", reason="injected", at="t")])
    w.ops.on_launch = lambda ops, name, root: install_jdk17(state) if name == "tg1-p426-rehearsal-mismatch" else None
    assert go_rehearsal(rehearsal) == 0
    assert w.ops.names()[-1] == "tg1-p426-rehearsal-kill"                    # R3 launched
    assert "as the rehearsal expects" in log_of(w)


def test_h3_an_unreadable_baseline_still_stops(world):
    """Not a host change: the run's own baseline record no longer verifies (sealed records stay verifiable)."""
    seam(world)
    assert go(world, "--through", "1") == 0
    (world.out / w2.HOST_ENV_FILE).write_text("{")
    n = len(world.ops.launches)
    assert go(world) == 1 and len(world.ops.launches) == n


# ----------------------------------------------------------------------------------------------- H5: legs recorded INVALID by C360
A3_BEFORE = dict(BASE, cellar=["harfbuzz/15.1.0", "nbytes/0.1.4", "openjdk@21/21.0.4", "rust/1.80.0", "vim/9.2.1373"],
                 bin_dirs={"/opt/homebrew/bin": ["cargo -> ../Cellar/rust", "ex -> ../Cellar/vim/9.2.1373/bin/ex",
                                                 "hb-view -> ../Cellar/harfbuzz/15.1.0/bin/hb-view"]})
A3_AFTER = dict(BASE, cellar=["harfbuzz/15.2.0", "nbytes/0.1.5", "openjdk@21/21.0.4", "rust/1.80.0", "vim/9.2.1380"],
                bin_dirs={"/opt/homebrew/bin": ["cargo -> ../Cellar/rust", "ex -> ../Cellar/vim/9.2.1380/bin/ex",
                                                "hb-view -> ../Cellar/harfbuzz/15.2.0/bin/hb-view"]})
A3_CHANGES = he.diff(A3_BEFORE, A3_AFTER)


def c360_record(world, attempt, *, prior=None, overrun=None):
    """Rewrite `attempt`'s leg.json / sequence entry to what the C360 sequencer recorded for a host change during the leg (the a3
    shape: state INVALID, class systemic, the joined diff as the reason, no host fields), sealed, and the attempt unharvested."""
    path = world.out / attempt / "leg.json"
    doc = {k: v for k, v in json.loads(path.read_text()).items() if k not in ("sha256", "host_env_before", "host_env_during")}
    reason = w2.HOST_ENV_REASON + ": " + "; ".join(A3_CHANGES) + (f" (prior: {prior})" if prior else "")
    doc.update(state="INVALID", reason=reason, **{"class": "systemic"})
    if overrun is not None:
        doc["overrun"] = overrun
    path.unlink()
    ph.write_exclusive(path, doc)
    s = seq(world)
    leg, n = attempt.rsplit(".a", 1)
    for e in s["legs"]:
        if e["leg"] == leg and e["attempt"] == int(n):
            e.clear()
            e.update(leg=leg, attempt=int(n), state="INVALID", reason=reason)
    s["harvested"] = [h for h in s["harvested"] if h["attempt"] != attempt]
    w2.write_sequence(world.out, {k: v for k, v in s.items() if k != "previous_sha256"})
    return path.read_bytes()


def stop_harvest_at(world, attempt):
    """The harvest of `attempt` fails (rc 4) once: the sequencer stops with the leg recorded and unharvested."""
    harvest, done = world.ops.harvest, []

    def h(root, *, emails):
        if Path(root).name == attempt and not done:
            done.append(1)
            world.ops.events.append(("harvest-failed", Path(root).name))
            return dict(rc=2, message="REFUSED: injected")
        return harvest(root, emails=emails)
    world.ops.harvest = h


def recorded_c360(world, **kw):
    seam(world)
    stop_harvest_at(world, f"{OFF_S1}.a1")
    assert go(world) == 4
    assert world.ops.names() == LEGS[:3]
    original = c360_record(world, f"{OFF_S1}.a1", **kw)
    world.clock.t += 3600
    return original


def test_h5_a_c360_host_invalid_leg_takes_the_state_its_records_give_and_the_run_goes_on(world):
    original = recorded_c360(world)
    root = world.out / f"{OFF_S1}.a1"
    assert go(world) == 0                                                    # resume: --rerun NOT given
    assert world.ops.names() == LEGS                                         # harvested, after_leg, the next legs launched
    assert f"{OFF_S1}.a1" in [h["attempt"] for h in seq(world)["harvested"]]
    kept = root / w2.C384_SUPERSEDED
    assert kept.read_bytes() == original                                     # the original, byte-identical
    doc = json.loads((root / "leg.json").read_text())
    assert ph.sealed_ok(doc) and fz.read_leg(root) == doc                    # the record consumers read, its seal verifies
    assert doc["state"] == "VALID" and doc["class"] == "valid" and doc["reason"] == ""
    assert doc["host_env_during"] == A3_CHANGES and doc["host_env_before"] == []
    orig = json.loads(original)
    c = doc["c384"]
    assert c["rule"] == "C384" and c["superseded"] == w2.C384_SUPERSEDED
    assert c["superseded_sha256"] == orig["sha256"] and c["superseded_file_sha256"] == sha(original)
    assert c["superseded_state"] == "INVALID" and c["superseded_reason"] == orig["reason"]
    for k in ("leg", "attempt", "chain_rc", "started", "ended", "speed_valid", "speed_reason", "overrun"):
        assert doc[k] == orig[k], k
    entry = [e for e in seq(world)["legs"] if e["leg"] == OFF_S1][-1]
    assert entry["state"] == "VALID" and "reason" not in entry and entry["c384"]["superseded_sha256"] == orig["sha256"]
    assert entry["host_env_during"] == A3_CHANGES
    assert f"{OFF_S1}.a1: C384: the C360 host INVALID is superseded: state VALID" in log_of(world)
    assert "s1__off-a1__on-a1.json" in [p.name for p in world.ops.published_dossiers]     # the s1 pair dossier


def test_h5_a_second_resume_leaves_the_superseded_record_alone(world):
    recorded_c360(world)
    stop_harvest_at(world, "tg1-p426-on-s1.a1")
    assert go(world) == 4
    root = world.out / f"{OFF_S1}.a1"
    snap = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    world.clock.t += 3600
    assert go(world) == 0
    assert {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()} == snap


def test_h5_a_stop_between_keeping_the_original_and_replacing_leg_json_resumes(world):
    original = recorded_c360(world)
    root = world.out / f"{OFF_S1}.a1"
    (root / w2.C384_SUPERSEDED).write_bytes(original)                       # the first write landed, the replace did not
    assert go(world) == 0
    assert (root / w2.C384_SUPERSEDED).read_bytes() == original
    assert json.loads((root / "leg.json").read_text())["state"] == "VALID"


def test_h5_a_stop_after_the_replace_before_sequence_json_resumes_from_the_leg_record(world):
    recorded_c360(world)
    real = w2.Sequencer.save
    calls = []

    def failing_save(self):
        if any("c384" in e for e in self.seq["legs"]) and not calls:
            calls.append(1)
            raise RuntimeError("crash before save")
        return real(self)
    import unittest.mock as um
    with um.patch.object(w2.Sequencer, "save", failing_save):
        with pytest.raises(RuntimeError, match="crash before save"):
            go(world)
    root = world.out / f"{OFF_S1}.a1"
    assert json.loads((root / "leg.json").read_text())["state"] == "VALID"
    assert [e for e in seq(world)["legs"] if e["leg"] == OFF_S1][-1]["state"] == "INVALID"
    world.clock.t += 3600
    assert go(world) == 0
    entry = [e for e in seq(world)["legs"] if e["leg"] == OFF_S1][-1]
    assert entry["state"] == "VALID" and "c384" in entry


def test_h5_a_kept_file_that_is_not_the_original_stops(world):
    recorded_c360(world)
    root = world.out / f"{OFF_S1}.a1"
    (root / w2.C384_SUPERSEDED).write_text("{}")
    before = (root / "leg.json").read_bytes()
    assert go(world) == 1
    assert (root / "leg.json").read_bytes() == before
    assert w2.C384_SUPERSEDED in log_of(world)


def test_h5_a_leg_with_a_prior_classification_is_left_as_recorded(world):
    original = recorded_c360(world, prior="chain rc 2, status 'finished'")
    root = world.out / f"{OFF_S1}.a1"
    assert go(world) == 1
    assert (root / "leg.json").read_bytes() == original and not (root / w2.C384_SUPERSEDED).exists()
    log = log_of(world)
    assert f"{OFF_S1}.a1: INVALID by the host change with a prior classification; left as recorded" in log
    assert f"STOP: {OFF_S1}.a1 is INVALID; a rerun is an operator decision" in log


def test_h5_an_already_harvested_leg_is_left_as_recorded(world):
    original = recorded_c360(world)
    s = seq(world)
    s["harvested"].append(dict(attempt=f"{OFF_S1}.a1", harvest_sha256="0" * 64))
    w2.write_sequence(world.out, {k: v for k, v in s.items() if k != "previous_sha256"})
    root = world.out / f"{OFF_S1}.a1"
    assert go(world) == 1
    assert (root / "leg.json").read_bytes() == original and not (root / w2.C384_SUPERSEDED).exists()
    assert f"{OFF_S1}.a1: INVALID by the host change and already harvested; left as recorded" in log_of(world)


def test_h5_a_rerun_of_the_leg_is_not_superseded(world):
    original = recorded_c360(world)
    root = world.out / f"{OFF_S1}.a1"
    assert go(world, "--rerun", OFF_S1, "--rerun-reason", "operator rerun") == 0
    assert (root / "leg.json").read_bytes() == original and (world.out / f"{OFF_S1}.a2" / "leg.json").is_file()


def test_h5_the_classifiers_invalid_is_kept_with_its_own_reason(world):
    """Failure path kept: a crashed chain stays INVALID with its own reason; the host changes are recorded beside it."""
    recorded_c360(world)
    root = world.out / f"{OFF_S1}.a1"
    chain = json.loads((root / "chain.json").read_text())
    chain["status"] = "running"
    (root / "chain.json").write_text(json.dumps(chain))
    assert go(world) == 1
    doc = json.loads((root / "leg.json").read_text())
    assert doc["state"] == "INVALID" and doc["reason"] == "chain rc 0, status 'running'" and doc["host_env_during"] == A3_CHANGES
    assert ph.sealed_ok(doc) and doc["c384"]["superseded_state"] == "INVALID"


def test_h5_the_overrun_rule_uses_the_recorded_overrun(world):
    recorded_c360(world, overrun=True)
    root = world.out / f"{OFF_S1}.a1"
    chain = json.loads((root / "chain.json").read_text())
    chain["status"] = "running"
    (root / "chain.json").write_text(json.dumps(chain))
    assert go(world) == 1
    assert json.loads((root / "leg.json").read_text())["state"] == "OVERRUN"


def test_h5_the_harvest_keeps_the_original_beside_the_superseding_record():
    from bench import p426_harvest as H
    assert H.classify("leg", w2.C384_SUPERSEDED) == ("main", None)
    assert H._is_immutable(w2.C384_SUPERSEDED)
    assert H.C384_SUPERSEDED == w2.C384_SUPERSEDED


def test_h5_the_reason_split_is_the_diff_list():
    reason = w2.HOST_ENV_REASON + ": " + "; ".join(A3_CHANGES)
    assert w2.c360_changes(reason) == A3_CHANGES
    assert len(A3_CHANGES) == 8                      # the a3 shape: 3 Cellar added, 3 removed, 2 bin links retargeted
    assert sum(c.startswith("Homebrew Cellar: ") for c in A3_CHANGES) == 6


# ----------------------------------------------------------------------------------------------- fix round 1
def test_h5_a_committed_harvest_without_a_harvested_entry_is_left_as_recorded(world):
    """H5 window: the harvest committed (its HARVEST.json is published) but sequence.json did not record it before a stop."""
    original = recorded_c360(world)
    attempt = f"{OFF_S1}.a1"
    committed = Path(world.ops.harvest_path(attempt)) / "HARVEST.json"
    committed.parent.mkdir(parents=True, exist_ok=True)
    committed.write_text(json.dumps(dict(leg=attempt, state="INVALID")))
    root = world.out / attempt
    assert go(world) == 1                                                    # left INVALID: the existing stop applies
    assert (root / "leg.json").read_bytes() == original and not (root / w2.C384_SUPERSEDED).exists()
    assert f"{attempt}: INVALID by the host change and its harvest is already committed; left as recorded" in log_of(world)
    assert [e for e in seq(world)["legs"] if e["leg"] == OFF_S1][-1]["state"] == "INVALID"


def _leftovers(root):
    return sorted(p.name for p in root.iterdir() if "c360" in p.name and p.name != w2.C384_SUPERSEDED)


def test_h5_a_crash_while_writing_the_kept_original_leaves_no_partial_file_and_resumes(world, monkeypatch):
    """H5 atomic: a crash before the kept original is installed never leaves a file at its final path; the next resume completes."""
    original = recorded_c360(world)
    root = world.out / f"{OFF_S1}.a1"
    real_fsync, real_check, inside = w2.os.fsync, w2.Sequencer.c384_check_kept, []

    def check(self, *a, **kw):
        inside.append(1)
        return real_check(self, *a, **kw)

    def crash(fd):
        if inside:                                   # the first fsync while the kept original is written
            raise RuntimeError("crash while writing the kept original")
        return real_fsync(fd)
    monkeypatch.setattr(w2.Sequencer, "c384_check_kept", check)
    monkeypatch.setattr(w2.os, "fsync", crash)
    with pytest.raises(RuntimeError, match="crash while writing"):
        go(world)
    monkeypatch.setattr(w2.os, "fsync", real_fsync)
    monkeypatch.setattr(w2.Sequencer, "c384_check_kept", real_check)
    assert not os.path.lexists(root / w2.C384_SUPERSEDED)
    assert (root / "leg.json").read_bytes() == original
    world.clock.t += 3600
    assert go(world) == 0
    assert (root / w2.C384_SUPERSEDED).read_bytes() == original and _leftovers(root) == []
    assert json.loads((root / "leg.json").read_text())["state"] == "VALID"


def test_h5_the_kept_original_is_installed_without_replacement(world, monkeypatch):
    """H5 atomic: installed by an exclusive link from a same-directory temp file (never a rename over the final path)."""
    recorded_c360(world)
    root = world.out / f"{OFF_S1}.a1"
    links, real_link = [], w2.os.link

    def link(src, dst, *a, **kw):
        links.append((Path(src).parent, Path(dst)))
        return real_link(src, dst, *a, **kw)
    monkeypatch.setattr(w2.os, "link", link)
    assert go(world) == 0
    assert (root, root / w2.C384_SUPERSEDED) in links and _leftovers(root) == []


def test_h5_a_crash_after_the_link_before_the_temp_is_removed_resumes(world, monkeypatch):
    original = recorded_c360(world)
    root = world.out / f"{OFF_S1}.a1"
    real_unlink = w2.os.unlink

    def crash(path, *a, **kw):
        if "c360" in str(path):
            raise RuntimeError("crash after the link")
        return real_unlink(path, *a, **kw)
    monkeypatch.setattr(w2.os, "unlink", crash)
    with pytest.raises(RuntimeError, match="crash after the link"):
        go(world)
    monkeypatch.setattr(w2.os, "unlink", real_unlink)
    assert (root / w2.C384_SUPERSEDED).read_bytes() == original             # complete or absent, never partial
    world.clock.t += 3600
    assert go(world) == 0
    assert _leftovers(root) == [] and json.loads((root / "leg.json").read_text())["state"] == "VALID"


def test_h3b_a_resumed_run_that_ends_on_the_baseline_overwrites_an_earlier_final_diff(world):
    state = seam(world)
    harvest = world.ops.harvest

    def harvest_then_install(root, *, emails):
        res = harvest(root, emails=emails)
        if Path(root).name == "tg1-p426-on-pilot.a1":
            install_jdk17(state)
        return res
    world.ops.harvest = harvest_then_install
    assert go(world, "--through", "2") == 0
    assert seq(world)["host_env_after_last_leg"] == [JDK17]
    world.ops.harvest = harvest
    state.fp["cellar"] = list(BASE["cellar"])                               # the JDK is removed before the resume
    world.clock.t += 3600
    assert go(world) == 0
    assert seq(world)["host_env_after_last_leg"] == []
