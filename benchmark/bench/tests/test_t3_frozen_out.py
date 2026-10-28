"""P426 T3 frozen tests — the sequencer's `--out` marker, resume per label and isolation (spec §4 "the sequencer's --out",
"Isolation", §6): a `.build` marker on first start; an `--out` of another label, or holding receipts / a `sequence.log` without
a marker, refuses; resume reads only its own label's receipts and dossiers; an `s2` run in a tree holding `s` outputs neither
refuses on them nor changes a byte of them.

Classes: [N] exercises new behaviour; [I] preserves an invariant; [R] reproduces a failure the specification fixes."""

import json
import shutil

import pytest

from bench.tests import t3_frozen_support as T
from bench.tests.t3_frozen_support import box  # noqa: F401 — the fake-box fixture

M1 = [n for n in T.s2_leg_names() if n.startswith("m1-")]


# ------------------------------------------------------------------ the marker
def test_the_first_start_writes_the_build_marker(tmp_path, monkeypatch, box):
    """[N] §4: `<out>/.build` names the label after the first start."""
    w = T.make_arms_world(tmp_path)
    run = T.run_sequencer(w, box, T.s2_argv(w, axes=["m1"]), monkeypatch)
    assert run.rc == 0, run.why()
    assert (w.out / ".build").read_text().strip() == "s2"


def _seed_out(w, what):
    w.out.mkdir(parents=True)
    if what == "marker-s":
        (w.out / ".build").write_text("s\n")
    elif what == "receipts":
        (w.out / "receipts").mkdir()
        (w.out / "receipts" / "math500-p426-off-smoke.receipt.json").write_text(json.dumps({"verdict": "VALID"}))
    elif what == "sequence.log":
        (w.out / "sequence.log").write_text("2026-10-22 10:00:00 sequencer PID 1\n")


@pytest.mark.parametrize("what", ["marker-s", "receipts", "sequence.log"])
# POST-REVEAL tw-3: control twin — the same world into a fresh `--out` runs, so the refusal is the out-marker check's.
def test_an_out_of_another_label_or_unmarked_with_history_is_refused(tmp_path, monkeypatch, box, what):
    """[N] §4: refused before any leg; the out's marker and receipts are unchanged (a refusal line in its log is allowed)."""
    w = T.make_arms_world(tmp_path)
    _seed_out(w, what)

    def kept():
        return {k: v for k, v in T.snapshot(w.out).items() if not k.endswith("sequence.log")}

    before = kept()
    run = T.run_sequencer(w, box, T.s2_argv(w, axes=["m1"]), monkeypatch)
    T.assert_refused_before_launch(run)
    assert kept() == before
    seeded = w.out
    T.assert_twin_runs(w, box, monkeypatch, lambda: None)  # a fresh `--out`: the only difference
    assert {k: v for k, v in T.snapshot(seeded).items() if not k.endswith("sequence.log")} == before


def test_an_existing_empty_out_is_a_first_start(tmp_path, monkeypatch, box):
    """[N] §4: an empty `--out` (no receipts, no `sequence.log`) is not history — the run starts and marks it."""
    w = T.make_arms_world(tmp_path)
    w.out.mkdir(parents=True)
    run = T.run_sequencer(w, box, T.s2_argv(w, axes=["m1"]), monkeypatch)
    assert run.rc == 0 and (w.out / ".build").read_text().strip() == "s2", run.why()


# ------------------------------------------------------------------ resume per label
def test_resume_reads_only_its_own_labels_receipts_and_dossiers(tmp_path, monkeypatch, box):
    """[N] §4: a rerun skips its own VALID + harvested legs; an `s`-named receipt in the out is not its receipt; a VALID
    `s2` receipt whose dossier sits only under S's `wave1/` is not harvested → stop before a launch."""
    w = T.make_arms_world(tmp_path)
    first = T.run_sequencer(w, box, T.s2_argv(w, axes=["m1"]), monkeypatch)
    assert first.rc == 0 and T.launched_names(box) == M1, first.why()
    (w.out / "receipts" / "m1-p426-off-smoke.receipt.json").write_text(json.dumps({"verdict": "INVALID"}))
    again = T.run_sequencer(w, box, T.s2_argv(w, axes=["m1"]), monkeypatch)
    assert again.rc == 0 and T.launched_names(box) == M1, again.why()  # every s2 leg skipped
    dossiers = w.main / "benchmark" / "results" / "p426"
    (dossiers / "wave1").mkdir()
    shutil.move(str(dossiers / "wave1.s2" / M1[0]), str(dossiers / "wave1" / M1[0]))
    stop = T.run_sequencer(w, box, T.s2_argv(w, axes=["m1"]), monkeypatch)
    assert stop.rc == 1 and T.launched_names(box) == M1, stop.why()


# ------------------------------------------------------------------ isolation
def test_an_s2_run_beside_s_outputs_neither_refuses_on_them_nor_touches_them(tmp_path, monkeypatch, box):
    """[N]+[I] §4 "Isolation": S's whole Wave 1 (run under `--build s`, harvested into `main`, committed into the S′ arms as
    `main` carries it) stays byte-identical through a whole `s2` run, which completes VALID."""
    s = T.make_s_world(tmp_path)
    s_run = T.run_sequencer(s, box, T.s_argv(s, build="s"), monkeypatch)
    assert s_run.rc == 0, s_run.why()
    w = T.make_arms_world(tmp_path, extra=T.committed_evidence(s.main))
    s_paths = (s.main / "benchmark" / "results", s.wd / "p426" / "frozen.json", s.wd / "p426" / "registry-on.yaml",
               s.wd / "p426" / "m1", s.out, s.root / "benchmark" / "results", w.off / "benchmark" / "results" / "p426",
               w.on / "benchmark" / "results" / "p426")
    before = T.snapshot(*s_paths)
    run = T.run_sequencer(w, box, T.s2_argv(w), monkeypatch)
    assert run.rc == 0, run.why()
    after = T.snapshot(*s_paths)
    new = sorted(set(after) - set(before))
    assert {k: after[k] for k in before} == before
    assert all(".p426s2-" in k or "/wave1.s2/" in k for k in new), new[:10]
    assert T.git(w.off, "status", "--porcelain", "--untracked-files=no") == ""
