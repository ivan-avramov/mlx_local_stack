"""B2 fix round 5 (the strict change review, round 3; spec 16.8 "after the strict verify round 3"): one failing-first test per item.
Hermetic: every tree is under `tmp_path`, every credential is a fake; no router, worker, model, network or GPU."""
from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

import pytest

from bench import p426_freeze as fz
from bench import p426_harvest as H
from bench import p426_hooks as ph
from bench import p426_wave2 as w2
from bench.tests import b2_s8_support as S8
from bench.tests import test_b2_s8_wave2 as T8
from bench.tests import test_b2_s9_harvest as T9

FAKE = "Qk9" + "m2Rz" * 9 + "T"                                   # a fake 40-char opaque credential value
OPERATOR = "op.erator@corp-mail.example"
world = T8.world                                                    # the sequencer fixture (fake ops, fake clock)


def put_json(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc))
    return path


# ------------------------------------------------------------------------------------------------ 1. republication re-verifies
def after_the_pilots(world, *, unpublished):
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 0
    if unpublished:                                                 # a record whose publication failed earlier
        doc = json.loads(world.seq.read_text())
        for rec in doc["pairs"]:
            rec.pop("published")
        world.seq.write_text(json.dumps(doc))
    world.ops.events.clear()
    world.ops.launches.clear()
    world.ops.published_dossiers.clear()
    world.clock.t += 3600


def change_a_pilot_receipt(world):
    root = world.out / "tg1-p426-off-pilot.a1"
    (root / "receipt.json").write_text(json.dumps(ph.seal(S8.receipt("off", env_extra={"MLX_X": "1"}))))


@pytest.mark.parametrize("unpublished", [True, False], ids=["unpublished", "published"])
def test_1_a_receipt_changed_after_the_pair_was_recorded_makes_makeup_refuse_publishing_nothing(world, unpublished):
    after_the_pilots(world, unpublished=unpublished)
    change_a_pilot_receipt(world)
    f = T8.write_occurrences(world.wd / "occ.jsonl", T8.MK)
    assert T8.go(world, "--occurrences", str(f), cmd="makeup") == 1
    assert world.ops.published_dossiers == [] and not world.ops.names()
    assert "receipt_sha256" in (world.out / "sequence.log").read_text().splitlines()[-1]


def test_1_the_amendment_check_needs_the_freshly_verified_dossier_not_only_its_file_hash(world):
    after_the_pilots(world, unpublished=False)                      # the pair is recorded PASS and published: only the receipt moves
    change_a_pilot_receipt(world)
    assert T8.go(world) == 1
    assert not world.ops.names()
    assert "receipt_sha256" in (world.out / "sequence.log").read_text().splitlines()[-1]


def test_1_republication_re_verifies_before_publishing_even_without_the_amendment_check(world, monkeypatch):
    after_the_pilots(world, unpublished=True)
    change_a_pilot_receipt(world)
    monkeypatch.setattr(w2.Sequencer, "verify_existing_amendment", lambda self: None)
    assert T8.go(world, "--through", "tg1-p426-on-pilot") == 1
    assert world.ops.published_dossiers == []


def test_1_an_untouched_recorded_dossier_is_still_republished_and_the_amendment_accepted(world):
    after_the_pilots(world, unpublished=True)
    f = T8.write_occurrences(world.wd / "occ.jsonl", T8.MK)
    assert T8.go(world, "--occurrences", str(f), cmd="makeup") == 0
    assert len(world.ops.published_dossiers) >= 1


# ------------------------------------------------------------------------------------------------ 2. a DNF's ready record
def dnf_leg(tmp_path, arm="off"):
    root = S8.write_leg_root(tmp_path / f"tg1-p426-{arm}-s1.a1", arm=arm, leg=f"tg1-p426-{arm}-s1", state="VALID_WITH_DNF", klass="dnf",
                             items=4, dnf=1)
    ledger = json.loads((root / "chain.json").read_text())["p426_ledger"]
    return root, ledger[-1]["slot"], ledger[0]["slot"]


def items_path(root, slot, suffix):
    return root / "items" / (S8.cr.slot_file(slot) + suffix)


def reseal_file(path, **changes):
    doc = {k: v for k, v in json.loads(path.read_text()).items() if k != "sha256"}
    doc.update(changes)
    path.write_text(json.dumps(ph.seal(doc)))


def test_2_a_good_dnf_leg_is_valid_with_dnf(tmp_path):
    root, _dnf, _row = dnf_leg(tmp_path)
    assert fz.leg_items_problems(root, "off") == []
    assert w2.classify_leg(root, 0, arm="off")["state"] == "VALID_WITH_DNF"


def test_2_a_dnf_without_its_ready_record_is_not_valid_with_dnf(tmp_path):
    root, dnf, _row = dnf_leg(tmp_path)
    items_path(root, dnf, ".ready.json").unlink()
    got = w2.classify_leg(root, 0, arm="off")
    assert got["state"] == "INVALID" and "ready" in got["reason"]
    assert any("ready" in p for p in fz.leg_items_problems(root, "off"))


def test_2_a_dnf_whose_ready_sha256_is_not_its_ready_records_is_not_valid_with_dnf(tmp_path):
    root, dnf, _row = dnf_leg(tmp_path)
    reseal_file(items_path(root, dnf, ".dnf.json"), ready_sha256="0" * 64)
    got = w2.classify_leg(root, 0, arm="off")
    assert got["state"] == "INVALID" and "ready_sha256" in got["reason"]


def test_2_a_dnf_with_a_ready_record_whose_self_hash_is_wrong_is_not_valid_with_dnf(tmp_path):
    root, dnf, _row = dnf_leg(tmp_path)
    p = items_path(root, dnf, ".ready.json")
    p.write_text(json.dumps(dict(json.loads(p.read_text()), at="changed")))
    assert w2.classify_leg(root, 0, arm="off")["state"] == "INVALID"


def test_2_a_row_whose_ready_sha256_is_not_its_ready_records_is_not_valid(tmp_path):
    root, _dnf, row = dnf_leg(tmp_path)
    reseal_file(items_path(root, row, ".json"), ready_sha256="0" * 64)
    got = w2.classify_leg(root, 0, arm="off")
    assert got["state"] == "INVALID" and "ready_sha256" in got["reason"]


def test_2_the_harvest_fails_a_dnf_without_its_ready_record_or_with_a_wrong_ready_sha256(tmp_path):
    dsf = f"e__off__{T9.MODEL}__s1__python__zzz"
    ok = T9.World(tmp_path / "ok", state="VALID_WITH_DNF", dnf=True)
    assert ok.harvest(emails=(OPERATOR,))["state"] == "VALID_WITH_DNF"
    gone = T9.World(tmp_path / "gone", state="VALID_WITH_DNF", dnf=True)
    (gone.root / "items" / f"{dsf}.ready.json").unlink()
    with pytest.raises(H.HarvestError, match="ready"):
        gone.harvest(emails=(OPERATOR,))
    T9.nothing_published(gone)
    wrong = T9.World(tmp_path / "wrong", state="VALID_WITH_DNF", dnf=True)
    reseal_file(wrong.root / "items" / f"{dsf}.dnf.json", ready_sha256="0" * 64)
    with pytest.raises(H.HarvestError, match="ready_sha256"):
        wrong.harvest(emails=(OPERATOR,))
    T9.nothing_published(wrong)


# ------------------------------------------------------------------------------------------------ 3. staging never follows a link
def sealed_run_file(tmp_path, name="v8_base.json"):
    return put_json(tmp_path / "run" / name, ph.seal({"kind": "p426_v8_base"}))


def scrub_for(tmp_path):
    return T9.scrub_for(tmp_path, emails=(OPERATOR,))


def test_3_a_stage_symlink_is_never_followed_and_the_destination_is_not_a_link(tmp_path):
    main = tmp_path / "main"
    src = sealed_run_file(tmp_path)
    victim = tmp_path / "elsewhere.txt"
    victim.write_text("untouched")
    stage = main / H.WAVE2 / "run" / "v8_base.json.stage"
    stage.parent.mkdir(parents=True)
    os.symlink(victim, stage)
    with pytest.raises(H.HarvestError, match="stage"):
        H.publish_run_files([src], main_root=main, scrub=scrub_for(tmp_path))
    assert victim.read_text() == "untouched" and os.path.islink(stage)
    assert not (main / H.WAVE2 / "run" / "v8_base.json").exists()


def test_3_an_existing_regular_stage_file_is_refused_not_reused(tmp_path):
    main = tmp_path / "main"
    src = sealed_run_file(tmp_path)
    stage = main / H.WAVE2 / "run" / "v8_base.json.stage"
    stage.parent.mkdir(parents=True)
    stage.write_text("left by something")
    with pytest.raises(H.HarvestError, match="stage"):
        H.publish_run_files([src], main_root=main, scrub=scrub_for(tmp_path))
    assert stage.read_text() == "left by something" and not (main / H.WAVE2 / "run" / "v8_base.json").exists()


def test_3_a_stage_dangling_symlink_is_refused_too(tmp_path):
    main = tmp_path / "main"
    src = sealed_run_file(tmp_path)
    stage = main / H.WAVE2 / "run" / "v8_base.json.stage"
    stage.parent.mkdir(parents=True)
    os.symlink(tmp_path / "nowhere", stage)
    with pytest.raises(H.HarvestError, match="stage"):
        H.publish_run_files([src], main_root=main, scrub=scrub_for(tmp_path))
    assert not (tmp_path / "nowhere").exists()


def test_3_a_destination_that_is_not_a_regular_file_after_the_rename_is_refused(tmp_path, monkeypatch):
    main = tmp_path / "main"
    src = sealed_run_file(tmp_path)
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text("{}")

    def swap(stage, dest):                                         # a racing process puts a link where the record should land
        os.unlink(stage)
        os.symlink(elsewhere, dest)
    monkeypatch.setattr(H, "_rename", swap)
    with pytest.raises(H.HarvestError, match="regular file"):
        H.publish_run_files([src], main_root=main, scrub=scrub_for(tmp_path))


def test_3_a_normal_publication_leaves_no_stage_and_a_regular_file(tmp_path):
    main = tmp_path / "main"
    src = sealed_run_file(tmp_path)
    H.publish_run_files([src], main_root=main, scrub=scrub_for(tmp_path))
    dest = main / H.WAVE2 / "run" / "v8_base.json"
    assert dest.is_file() and not dest.is_symlink() and not list(dest.parent.glob("*.stage"))


# ------------------------------------------------------------------------------------------------ 4. exit code 4
def test_4_a_failing_run_file_publication_after_a_pair_gate_stop_makes_the_exit_4_and_logs_both(world):
    world.ops.scenario["tg1-p426-on-pilot"] = dict(env_extra={"MLX_X": "1"})                  # the pair gate fails: exit 1

    def boom(paths, *, emails):
        raise OSError("disk full")
    world.ops.publish_run_files = boom
    assert T8.go(world) == 4
    log = (world.out / "sequence.log").read_text()
    assert "pair gate failed" in log and "run files NOT published" in log and "OSError" in log


def test_4_a_failing_run_file_publication_at_a_clean_end_is_exit_4_and_no_done_line(world):
    def boom(paths, *, emails):
        raise OSError("disk full")
    world.ops.publish_run_files = boom
    assert T8.go(world, "--through", "tg1-p426-off-pilot") == 4
    log = (world.out / "sequence.log").read_text()
    assert "DONE" not in log and "run files were NOT published" in log


def test_4_without_a_publication_failure_the_original_stop_code_stays(world):
    world.ops.scenario["tg1-p426-on-pilot"] = dict(env_extra={"MLX_X": "1"})
    assert T8.go(world) == 1


# ------------------------------------------------------------------------------------------------ 5. credential sources from the frozen record
def test_5_the_box_ops_take_the_env_files_from_the_frozen_v8_base_not_from_the_worktree_arguments(tmp_path, monkeypatch):
    wd = tmp_path / "wd"
    frozen_off, frozen_on = wd / "p426" / "stack-p426-off", wd / "p426" / "stack-p426-on"
    elsewhere = tmp_path / "elsewhere"
    for d in (frozen_off, frozen_on, elsewhere):
        d.mkdir(parents=True)
    (frozen_off / ".env").write_text(f"MY_API_KEY={FAKE}\n")                                   # a secret only the frozen worktree has
    (elsewhere / ".env").write_text("OTHER_API_KEY=not-this-one-1234567890\n")
    rec = wd / "p426" / "record"
    put_json(rec / "v8_base.json", ph.seal(dict(kind="p426_v8_base", off_worktree="$STACK_WORKDIR/p426/stack-p426-off",
                                                on_worktree="$STACK_WORKDIR/p426/stack-p426-on")))
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    a = w2.parse_args(["run", "--record-dir", str(rec), "--worktree-off", str(elsewhere), "--worktree-on", str(elsewhere),
                       "--out-base", str(wd / "p426" / "wave2"), "--main-root", str(tmp_path / "main"),
                       "--evidence-stage", str(tmp_path / "stage")])
    ops = w2.build_box_ops(a, wd)
    assert [Path(p) for p in ops.env_files] == [frozen_off / ".env"]
    seq = put_json(tmp_path / "wave2" / "sequence.json", {"rerun_reason": f"pasted {FAKE}", "legs": []})
    with pytest.raises(H.HarvestError):
        ops.publish_run_files([seq], emails=(OPERATOR,))
    assert not (tmp_path / "main").exists() or not any(p.is_file() for p in (tmp_path / "main").rglob("*"))


def test_5_a_rehearsal_takes_them_from_its_manifest(tmp_path, monkeypatch):
    wd = tmp_path / "wd"
    off = wd / "p426" / "stack-p426-off"
    off.mkdir(parents=True)
    (off / ".env").write_text(f"MY_API_KEY={FAKE}\n")
    manifest = put_json(wd / "p426" / "rehearsal" / "manifest.json",
                        ph.seal(dict(kind="p426_rehearsal", off_worktree="$STACK_WORKDIR/p426/stack-p426-off",
                                     on_worktree="$STACK_WORKDIR/p426/stack-p426-on")))
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    a = w2.parse_args(["rehearsal", "--manifest", str(manifest), "--frozen-prompt-date", "Tue Oct 27 2026", "--worktree-off", str(tmp_path),
                       "--worktree-on", str(tmp_path), "--out-base", str(wd / "p426" / "rehearsal" / "o")])
    assert [Path(p) for p in w2.frozen_env_files(a, wd)] == [off / ".env"]


def test_5_an_unreadable_frozen_record_gives_no_env_files(tmp_path, monkeypatch):
    wd = tmp_path / "wd"
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    a = w2.parse_args(["run", "--record-dir", str(tmp_path / "none"), "--worktree-off", "x", "--worktree-on", "y",
                       "--out-base", str(wd / "p426" / "wave2")])
    assert list(w2.frozen_env_files(a, wd)) == []
