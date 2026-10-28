"""P426 T3 frozen tests — arms as commits (spec §4 "Arms as commits", C218, §6): `--registry-on` refused under `s2`; the
restore diff asserted at patch level before the first leg; tracked-only cleanliness; both heads equal to the record; every
leg (cwd, router, driver, server log) and M1 from its own arm's worktree, serving that worktree's committed registry; the M1
ON overlay's sha256 equal to the ON worktree's `main_models.yaml` (P504).

Classes: [N] exercises new behaviour; [I] preserves an invariant; [R] reproduces a failure the specification fixes."""

from pathlib import Path

import pytest

from bench.tests import t3_frozen_support as T
from bench.tests.t3_frozen_support import box, s2_full_run  # noqa: F401 — fixtures


# ------------------------------------------------------------------ each leg from its own worktree (the success path)
def _arm_root(run, name):
    return run.world.on if "-on-" in name else run.world.off


def test_every_launch_runs_from_its_arms_worktree(s2_full_run):
    """[N] the leg process (interpreter and cwd) is its arm's worktree's."""
    assert s2_full_run.rc == 0, s2_full_run.why()
    for x, n in zip(s2_full_run.box.launches, T.s2_leg_names()):
        root = _arm_root(s2_full_run, n)
        assert Path(x["argv"][0]).is_relative_to(root), (n, x["argv"][0])
        assert x["cwd"] is not None and Path(x["cwd"]).is_relative_to(root), (n, x["cwd"])


def test_every_router_serves_its_arms_committed_registry(s2_full_run):
    """[N] C218: the router of an OFF leg serves `WT_off/main_models.yaml`, of an ON leg `WT_on/main_models.yaml`."""
    assert s2_full_run.rc == 0, s2_full_run.why()
    by_prefix = {d["prefix"][len("p426-"):]: d for d in s2_full_run.box.drivers if d["prefix"]}
    for n, d in by_prefix.items():
        root = _arm_root(s2_full_run, n)
        assert d["serving"] == str(root), (n, d["serving"])
        assert Path(d["served_config"]).resolve() == (root / "main_models.yaml").resolve(), (n, d["served_config"])
        assert Path(d["argv"][0]).is_relative_to(root) and Path(d["cwd"]).is_relative_to(root), (n, d)


def test_m1_runs_from_its_arms_worktree(s2_full_run):
    """[N] P472: qualify runs in-process from its arm's worktree (stack root, fork root, interpreter)."""
    w = s2_full_run.world
    m1 = [d for d in s2_full_run.box.drivers if not d["prefix"]]
    assert len(m1) == 6, s2_full_run.why()
    for d in m1:
        arm = T._flag(d["argv"], "--predictor")
        root = w.on if arm == "on" else w.off
        assert T._flag(d["argv"], "--stack-root") == str(root) and T._flag(d["argv"], "--fork-root") == str(root / "src/mlx-vlm")
        assert Path(d["argv"][0]).is_relative_to(root)


def test_every_dossier_slices_its_arms_server_log(s2_full_run):
    """[N] the server-log slice harvested for a router leg is that leg's (its arm's `logs/mlx_vlm.log`)."""
    dossiers = s2_full_run.world.main / "benchmark/results/p426/wave1.s2"
    for n in [n for n in T.s2_leg_names() if not n.startswith("m1-")]:
        p = dossiers / n / "server_log_slice.log"
        assert p.exists() and f"session=p426-{n}-1 " in p.read_text(), n


# ------------------------------------------------------------------ refusals before the first leg
def _run(tmp_path, monkeypatch, box, mutate=None, extra=(), axes=("m1",)):
    w = T.make_arms_world(tmp_path)
    if mutate:
        mutate(w)
    return T.run_sequencer(w, box, T.s2_argv(w, axes=list(axes), extra=extra), monkeypatch)


def test_registry_on_is_refused_under_s2(tmp_path, monkeypatch, box):
    """[N] §4: the ON overlay is retired under `s2`; the control without it runs."""
    w = T.make_arms_world(tmp_path)
    overlay = w.wd / "p426" / "registry-on.yaml"
    overlay.write_text(T.overlay_on(T.off_registry()))
    run = T.run_sequencer(w, box, T.s2_argv(w, axes=["m1"], extra=["--registry-on", str(overlay)]), monkeypatch)
    T.assert_refused_before_launch(run, allow_usage=True)
    w.out = w.wd / "p426" / "wave1.s2.control"
    ok = T.run_sequencer(w, box, T.s2_argv(w, axes=["m1"]), monkeypatch)
    assert ok.rc == 0, ok.why()


@pytest.mark.parametrize("missing", ["--stack-root-off", "--stack-root-on"])
def test_both_arm_worktrees_are_required_under_s2(tmp_path, monkeypatch, box, missing):
    """[N] §4: the sequencer takes `--stack-root-off` and `--stack-root-on` under `s2`."""
    w = T.make_arms_world(tmp_path)
    argv = T.s2_argv(w, axes=["m1"])
    i = argv.index(missing)
    run = T.run_sequencer(w, box, argv[:i] + argv[i + 2:], monkeypatch)
    T.assert_refused_before_launch(run, allow_usage=True)
    w.out = w.wd / "p426" / "wave1.s2.control"
    ok = T.run_sequencer(w, box, T.s2_argv(w, axes=["m1"]), monkeypatch)
    assert ok.rc == 0, ok.why()


def _registry_extra_hunk(w):
    T.recommit_on(w, registry=T.restored_registry(T.off_registry()) + "# an extra line\n")


def _registry_other_value(w):
    text = T.restored_registry(T.off_registry()).replace(f"    draft_model: {T.DRAFTER}", "    draft_model: caslca/other-drafter")
    T.recommit_on(w, registry=text)


def _registry_without_note(w):
    T.recommit_on(w, registry=T.overlay_on(T.off_registry()))


def _registry_two_of_three(w):
    T.recommit_on(w, registry=T.restored_registry(T.off_registry()).replace("    mtp_verify_scan: joint_v1\n",
                                                                           "    # mtp_verify_scan: joint_v1\n", 1))


def _seeding_missing(w):
    T.recommit_on(w, seeding=(w.off / T.SEEDING_TEST).read_text())


def _seeding_extra_hunk(w):
    text = T.restored_seeding((w.off / T.SEEDING_TEST).read_text()) + "\n# an extra line\n"
    T.recommit_on(w, seeding=text)


SEED_COMMENT = "    # No fake_model_mtp_scan fixture: the real resolver must leave this model unresolved.\n"  # seeding test, :178


def _seeding_comment_hunk(w):
    """POST-REVEAL tw-3 / tw-4: a comment-only extra hunk (no blank or code line) in the seeding test. tw-4: C241 / P511's
    restore removes the C177 comment, so the edited comment is another one of the file's."""
    text = T.restored_seeding((w.off / T.SEEDING_TEST).read_text())
    assert text.count(SEED_COMMENT) == 1
    T.recommit_on(w, seeding=text.replace(SEED_COMMENT, SEED_COMMENT.replace("fixture:", "fixture (edited):")))


# ------------------------------------------------------------------ POST-REVEAL tw-4: V1 / V2 failing cases (C241 / P511)
def _seeding_c177_comment_kept(w):
    """V1: the two assertions restored, the C177 comment lines kept."""
    text = (w.off / T.SEEDING_TEST).read_text()
    kept = T.SEEDING_OFF.rsplit("\n", 2)[0] + "\n"  # the two comment lines
    T.recommit_on(w, seeding=text.replace(T.SEEDING_OFF, kept + T.SEEDING_ON))


def _seeding_extra_joint_v1_line(w):
    """V1: the exact restore plus one more added code line that contains `joint_v1`."""
    text = T.restored_seeding((w.off / T.SEEDING_TEST).read_text())
    T.recommit_on(w, seeding=text.replace(T.SEEDING_ON, T.SEEDING_ON + '    assert "joint_v1" in str(man)\n'))


def _seeding_tuple_form(w):
    """V1: the pre-P511 form (one tuple assertion, the C177 comment kept) — the frozen set's own fixture before tw-4."""
    text = (w.off / T.SEEDING_TEST).read_text()
    old = '    assert man["runtime"]["mtp_verify_scan"] == "per_query"\n'
    T.recommit_on(w, seeding=text.replace(old, '    assert (man["runtime"]["mtp_verify_scan"], man["runtime"]['
                                                '"mtp_verify_scan_source"]) == ("joint_v1", "registry")\n'))


def _on_lines(edit):
    def mutate(w):
        lines = T.restored_registry(T.off_registry()).split("\n")
        start = lines.index(f"  - name: {T.ENTRY}")
        edit(lines, start)
        T.recommit_on(w, registry="\n".join(lines))
    return mutate


def _at(lines, start, text):
    return next(i for i in range(start, len(lines)) if lines[i] == text)


def _trailing_comment(lines, start):
    lines[_at(lines, start, "    draft_kind: mtp")] += "  # restored (P426)"


def _restored_line_moved(lines, start):
    i = _at(lines, start, "    mtp_verify_scan: joint_v1")
    line = lines.pop(i)
    lines.insert(_at(lines, start, f"    draft_model: {T.DRAFTER}") + 1, line)


def _two_notes(lines, start):
    i = _at(lines, start, T.PROVISIONAL_NOTE)
    lines.insert(i + 1, "      # PROVISIONAL P426 a second note")


def _note_outside_generation_defaults(lines, start):
    lines.pop(_at(lines, start, T.PROVISIONAL_NOTE))
    lines.insert(_at(lines, start, f"    draft_model: {T.DRAFTER}") + 1, "    # PROVISIONAL P426 2026-10-27")


def _note_not_first_child(lines, start):
    i = _at(lines, start, T.PROVISIONAL_NOTE)
    lines.insert(i + 2, lines.pop(i))


V_REFUSALS = {
    "V1-seeding-comment-only-hunk": _seeding_comment_hunk, "V1-seeding-c177-comment-kept": _seeding_c177_comment_kept,
    "V1-seeding-extra-joint-v1-line": _seeding_extra_joint_v1_line, "V1-seeding-tuple-form": _seeding_tuple_form,
    "V2-registry-trailing-comment": _on_lines(_trailing_comment), "V2-registry-line-moved": _on_lines(_restored_line_moved),
    "V2-registry-two-notes": _on_lines(_two_notes),
    "V2-registry-note-outside-generation-defaults": _on_lines(_note_outside_generation_defaults),
    "V2-registry-note-not-first-child": _on_lines(_note_not_first_child),
}


def _extra_path(w):
    T.recommit_on(w, files={"README.md": "changed\n"})


def _new_path(w):
    T.recommit_on(w, files={"docs/new.md": "new\n"})


def _mode_change(w):
    T.recommit_on(w, chmod=T.SEEDING_TEST)


def _two_commits(w):
    T.recommit_on(w, commits=2)


def _split_restore(w):
    """The whole restore, but over two commits: `WT_on`'s HEAD^ is not the frozen commit."""
    T.git(w.on, "reset", "-q", "--hard", T.git(w.off, "rev-parse", "HEAD"))
    (w.on / "main_models.yaml").write_text(T.restored_registry(T.off_registry()))
    T.commit_all(w.on, "registry only")
    seed = w.on / T.SEEDING_TEST
    seed.write_text(T.restored_seeding(seed.read_text()))
    T.commit_all(w.on, "seeding only")
    T.write_frozen_s2(w)


DIFF_REFUSALS = {
    "registry-extra-hunk": _registry_extra_hunk, "registry-other-value": _registry_other_value,
    "registry-without-note": _registry_without_note, "registry-two-of-three": _registry_two_of_three,
    "seeding-missing": _seeding_missing, "seeding-extra-hunk": _seeding_extra_hunk, "extra-path": _extra_path,
    # POST-REVEAL tw-4: `seeding-comment-hunk` (tw-3) moved to V_REFUSALS as the V1 comment-only case
    "new-path": _new_path, "mode-change": _mode_change, "two-commits": _two_commits, "split-restore": _split_restore,
}


@pytest.mark.parametrize("case", sorted(DIFF_REFUSALS))
# POST-REVEAL tw-4: the cases' restores are C241 / P511's bytes (`T.restored_registry` / `T.restored_seeding`); the tw-3
# comment-only case moved to `test_the_restore_is_exactly_the_p511_bytes`.
# POST-REVEAL tw-3: control twin — the same world with the plain restore commit re-made (and its record rewritten) runs, so
# the refusal is the restore-diff assertion's (the record, heads, trees and venvs are self-consistent in both).
def test_an_on_arm_beyond_the_restore_is_refused_before_the_first_leg(tmp_path, monkeypatch, box, case):
    """[N] §4 / failure path (2): `WT_on` = `WT_off` + ONE commit whose patch is exactly the restore (the entry's three C177
    lines + the PROVISIONAL P426 note; the seeding test's §11 change); any other hunk, path, mode or commit refuses, with a
    self-consistent record."""
    run = _run(tmp_path, monkeypatch, box, mutate=DIFF_REFUSALS[case])
    T.assert_refused_before_launch(run)
    w = run.world
    T.assert_twin_runs(w, box, monkeypatch, lambda: T.recommit_on(w))


@pytest.mark.parametrize("case", sorted(V_REFUSALS))
# POST-REVEAL tw-4: [R] V1 / V2 — an ON commit beyond C241 / P511's pinned bytes is refused before the first leg; control twin:
# the same world with the exact restore re-made runs.
def test_the_restore_is_exactly_the_p511_bytes(tmp_path, monkeypatch, box, case):
    """[R] spec §4 (patch level, no other hunk) + C241 / P511: ON `main_models.yaml` = the fork's `overlay_on(OFF)` + one
    `# PROVISIONAL P426` line as the first child of the entry's `generation_defaults:`; ON seeding test = OFF with the exact
    reverse of C177's seeding hunk."""
    run = _run(tmp_path, monkeypatch, box, mutate=V_REFUSALS[case])
    T.assert_refused_before_launch(run)
    w = run.world
    T.assert_twin_runs(w, box, monkeypatch, lambda: T.recommit_on(w))


@pytest.mark.parametrize("note", ["      # PROVISIONAL P426", "      # PROVISIONAL P426 free text: C236, 2026-10-27"])
# POST-REVEAL tw-4: [N] C241 / P511 — the note's free text is optional: a correct restore with either form is never refused.
def test_a_correct_restore_with_or_without_free_text_runs(tmp_path, monkeypatch, box, note):
    run = _run(tmp_path, monkeypatch, box, mutate=lambda w: T.recommit_on(w, registry=T.restored_registry(T.off_registry(),
                                                                                                          note=note)))
    assert run.rc == 0 and len(T.launched_names(box)) == 6, run.why()


def _dirty(arm):
    def mutate(w):
        root = w.on if arm == "on" else w.off
        (root / "README.md").write_text("uncommitted\n")
    return mutate


@pytest.mark.parametrize("arm", ["off", "on"])
# POST-REVEAL tw-3: control twin — the same world with the tracked change reverted runs.
def test_a_tracked_change_in_either_worktree_is_refused(tmp_path, monkeypatch, box, arm):
    """[N] §4: both trees clean (`git status --porcelain --untracked-files=no`) before the first leg."""
    run = _run(tmp_path, monkeypatch, box, mutate=_dirty(arm))
    T.assert_refused_before_launch(run)
    w = run.world
    T.assert_twin_runs(w, box, monkeypatch, lambda: T.git(w.on if arm == "on" else w.off, "checkout", "--", "README.md"))


@pytest.mark.parametrize("field", ["stack_head_off", "stack_head_on"])
# POST-REVEAL tw-3: control twin — the record rewritten with the live heads runs.
def test_a_head_that_differs_from_the_record_is_refused(tmp_path, monkeypatch, box, field):
    """[N] §4: both heads equal to the record before the first leg."""
    def mutate(w):
        T.write_frozen_s2(w, **{field: "f" * 40})
    run = _run(tmp_path, monkeypatch, box, mutate=mutate)
    T.assert_refused_before_launch(run)
    T.assert_twin_runs(run.world, box, monkeypatch, lambda: T.write_frozen_s2(run.world))


def test_untracked_files_in_the_worktrees_are_not_a_dirty_tree(tmp_path, monkeypatch, box):
    """[N] §4 [r2]: cleanliness is tracked-only (generated outputs are policed by the stem refusal)."""
    def mutate(w):
        for root in (w.off, w.on):
            (root / "scratch.txt").write_text("untracked\n")
            (root / "benchmark" / "results" / "notes.txt").write_text("untracked\n")
    run = _run(tmp_path, monkeypatch, box, mutate=mutate)
    assert run.rc == 0, run.why()


# ------------------------------------------------------------------ the leg re-asserts its own tree
@pytest.mark.parametrize("leg, arm", [("math500-p426s2-off-smoke", "off"), ("math500-p426s2-on-smoke", "on")])
def test_a_leg_whose_own_head_moved_is_not_started(tmp_path, monkeypatch, box, leg, arm):
    """[N] §4 [r2]: at entry the leg compares its live head with `stack_head_<arm>` of its own worktree; a head that moved
    after the sequencer's check → NOT_STARTED (the legs before it stay VALID: OFF is never compared with a missing
    `stack_head`)."""
    w = T.make_arms_world(tmp_path)
    box.before_leg[leg] = lambda: T.commit_all(w.on if arm == "on" else w.off, "moved")
    run = T.run_sequencer(w, box, T.s2_argv(w, axes=["math500"]), monkeypatch)
    names = T.launched_names(box)
    assert run.rc not in (0, None) and names and names[-1] == leg, run.why()
    for earlier in names[:-1]:
        assert T.receipt(w.out / "receipts", earlier)["verdict"] == "VALID"
    doc = T.receipt(w.out / "receipts", leg)
    assert doc["verdict"] == "NOT_STARTED" and any("head" in p for p in doc["problems"]), doc["problems"]
    assert box.drivers[len(names) - 1:] == []


def test_a_leg_whose_tree_drifts_during_the_driver_is_invalid(tmp_path, monkeypatch, box):
    """[N] §4: re-asserted at exit — a tracked change in the arm's worktree during the leg invalidates it."""
    w = T.make_arms_world(tmp_path)
    box.during_driver["math500-p426s2-on-smoke"] = lambda: (w.on / "README.md").write_text("drift\n")
    run = T.run_sequencer(w, box, T.s2_argv(w, axes=["math500"]), monkeypatch)
    assert run.rc not in (0, None), run.why()
    assert T.receipt(w.out / "receipts", "math500-p426s2-on-smoke")["verdict"] == "INVALID"


# ------------------------------------------------------------------ P504: the M1 ON overlay
def test_the_m1_on_overlay_must_be_the_on_worktrees_registry(tmp_path, monkeypatch, box):
    """[N] §4 [r2] (P504): qualify's `overlay-<entry>.yaml` sha256 == `WT_on/main_models.yaml`; a different one invalidates
    the ON leg (the OFF smoke before it is VALID)."""
    w = T.make_arms_world(tmp_path)
    out = w.wd / "p426" / "s2" / "m1" / "p426s2-on-smoke"
    box.qualify_overlay[str(out)] = T.overlay_on(T.off_registry()).encode()  # S's overlay form, not the committed ON
    run = T.run_sequencer(w, box, T.s2_argv(w, axes=["m1"]), monkeypatch)
    assert run.rc == 1 and T.launched_names(box) == ["m1-p426s2-off-smoke", "m1-p426s2-on-smoke"], run.why()
    assert T.receipt(w.out / "receipts", "m1-p426s2-off-smoke")["verdict"] == "VALID"
    doc = T.receipt(w.out / "receipts", "m1-p426s2-on-smoke")
    assert doc["verdict"] == "INVALID" and any("overlay" in p or "sha256" in p for p in doc["problems"]), doc["problems"]
