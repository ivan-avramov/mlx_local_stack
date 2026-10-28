"""P426 T3 frozen tests — the frozen record under `s2` (spec §4 "Expected build per label", "The frozen record under b",
"Order of checks", failure paths (1) and (3), §6): the expected-build refusal of a self-consistent record of another build,
the per-label record path (a missing `frozen.s2.json` refuses for the missing file), the lock shas, the venv-version check at
the sequencer, at leg entry and at leg exit, and validation before the run-file harvest.

Classes: [N] exercises new behaviour; [I] preserves an invariant; [R] reproduces a failure the specification fixes."""

import shutil

import pytest

from bench.tests import t3_frozen_support as T
from bench.tests.t3_frozen_support import box  # noqa: F401 — the fake-box fixture

S_VERSIONS = dict(T.S2_VERSIONS, mlx="0.32.3", **{"mlx-metal": "0.32.3"})


def _make_it_s2(w):
    """Remove the 'another build' defect: both arms' checkouts and venvs at S′'s pins, the record rewritten from them."""
    w.pins = dict(T.S2_PINS)
    for root in (w.off, w.on):
        T.populate_untracked(root, vlm=w.pins["mlx_vlm"], serve=w.pins["mlx_serve"], versions=T.S2_VERSIONS)
    T.write_frozen_s2(w)


@pytest.mark.parametrize("case", ["mlx_vlm", "mlx_serve", "production_ref", "venvs"])
# POST-REVEAL tw-3: control twin — the same world moved to S′'s pins runs, so the refusal is the expected-build check's.
# POST-REVEAL tw-5: C242 pin move (docstring names the new S′ pins; the pins come from `T.S2_PINS`).
def test_a_self_consistent_record_of_another_build_is_refused(tmp_path, monkeypatch, box, case):
    """[N] §4: the record's pins must equal the label's expected build (`s2` → 1c7c8fa1 / 1ddf6f84 / b26fa7c9 after C242, mlx 0.32.4 in
    both venvs) even when the record matches the tree; refused before any leg or harvest."""
    pins = dict(T.S2_PINS, **({case: T.S_PINS[case]} if case in T.S_PINS else {}))
    w = T.make_arms_world(tmp_path, pins=pins, versions=S_VERSIONS if case == "venvs" else T.S2_VERSIONS)
    run = T.run_sequencer(w, box, T.s2_argv(w, axes=["m1"]), monkeypatch)
    T.assert_refused_before_launch(run)
    text = T.text_of(run.text, w.out / "sequence.log")
    want = ("0.32.3", "0.32.4") if case == "venvs" else (T.S_PINS[case][:8], T.S2_PINS[case][:8])
    assert any(v in text for v in want), text
    T.assert_twin_runs(w, box, monkeypatch, lambda: _make_it_s2(w))


# POST-REVEAL tw-3: the refusal names the copied record's own pin (S's `mlx_vlm`); control twin with S′'s record runs.
def test_frozen_json_copied_as_frozen_s2_json_refuses_before_any_harvest(tmp_path, monkeypatch, box):
    """[N] failure path (1) + "Order of checks": S's record copied as `frozen.s2.json` → refused for the expected-build
    mismatch before any harvest, nothing launched, rc 1, nothing of S touched."""
    s = T.make_s_world(tmp_path)
    w = T.make_arms_world(tmp_path)
    shutil.copyfile(s.frozen, w.frozen)
    before = T.snapshot(s.frozen, s.overlay, s.root / "benchmark", w.main)
    run = T.run_sequencer(w, box, T.s2_argv(w), monkeypatch)
    T.assert_refused_before_launch(run)
    assert run.rc == 1, run.why()
    assert T.S_PINS["mlx_vlm"][:8] in T.text_of(run.text, w.out / "sequence.log"), run.text
    assert T.snapshot(s.frozen, s.overlay, s.root / "benchmark", w.main) == before
    assert not (w.main / "benchmark" / "results" / "p426").exists()
    T.assert_twin_runs(w, box, monkeypatch, lambda: T.write_frozen_s2(w))
    assert T.snapshot(s.frozen, s.overlay, s.root / "benchmark") == {k: v for k, v in before.items()
                                                                       if not k.startswith(str(w.main))}


# POST-REVEAL tw-3: control twin — the same world with its record present runs.
def test_a_missing_frozen_s2_json_refuses_for_the_missing_file(tmp_path, monkeypatch, box):
    """[N] §4: the sequencer under `s2` reads `<workdir>/p426/frozen.s2.json` and no other (S's `frozen.json` beside it)."""
    T.make_s_world(tmp_path)
    w = T.make_arms_world(tmp_path)
    w.frozen.unlink()
    run = T.run_sequencer(w, box, T.s2_argv(w, axes=["m1"]), monkeypatch)
    T.assert_refused_before_launch(run)
    assert "frozen.s2.json" in T.text_of(run.text, w.out / "sequence.log"), run.text
    T.assert_twin_runs(w, box, monkeypatch, lambda: T.write_frozen_s2(w))


def test_the_leg_reads_only_frozen_s2_json(tmp_path, monkeypatch, box):
    """[N] §4: a leg under `s2` reads that path and no other — its record removed after the sequencer's check → the leg is
    NOT_STARTED for the missing file, though S's `frozen.json` is present."""
    s = T.make_s_world(tmp_path)
    w = T.make_arms_world(tmp_path)
    box.before_leg["m1-p426s2-off-smoke"] = w.frozen.unlink
    run = T.run_sequencer(w, box, T.s2_argv(w, axes=["m1"]), monkeypatch)
    assert run.rc not in (0, None) and T.launched_names(box) == ["m1-p426s2-off-smoke"], run.why()
    docs = T.all_receipts(w.out / "receipts", "m1-p426s2-off-smoke")
    assert docs and docs[0]["verdict"] == "NOT_STARTED", run.why()
    assert any("frozen.s2.json" in p for d in docs for p in d["problems"]), docs
    assert box.drivers == [] and s.frozen.exists()


@pytest.mark.parametrize("field", ["uv_lock_sha256", "bench_lock_sha256"])
# POST-REVEAL tw-3: the ruled field names; a well-formed sha that differs from the live lock (not a malformed one, which a
# completeness check would refuse first); control twin — the record rewritten from the live locks runs.
def test_a_lock_sha_that_differs_from_the_record_is_refused(tmp_path, monkeypatch, box, field):
    """[N] §4: the record carries the sha256 of `uv.lock` and `benchmark/requirements-bench.lock`; a difference refuses."""
    w = T.make_arms_world(tmp_path)
    T.write_frozen_s2(w, **{field: "0" * 64})
    T.assert_refused_before_launch(T.run_sequencer(w, box, T.s2_argv(w, axes=["m1"]), monkeypatch))
    T.assert_twin_runs(w, box, monkeypatch, lambda: T.write_frozen_s2(w))


@pytest.mark.parametrize("arm, venv, dist", [("off", ".venv", "mlx"), ("on", ".venv-bench", "transformers"),
                                             ("on", ".venv", "mlx-audio"), ("off", ".venv-bench", "huggingface-hub")])
# POST-REVEAL tw-3: control twin — the venv restored to its recorded version runs.
def test_a_live_venv_that_differs_from_the_record_is_refused_by_the_sequencer(tmp_path, monkeypatch, box, arm, venv, dist):
    """[N] §4 "Order of checks": the sequencer validates the venvs (per worktree, `.venv` and `.venv-bench`) before the first
    leg."""
    w = T.make_arms_world(tmp_path)
    target = (w.on if arm == "on" else w.off) / venv
    T.set_version(target, dist, "0.0.1")
    run = T.run_sequencer(w, box, T.s2_argv(w, axes=["m1"]), monkeypatch)
    T.assert_refused_before_launch(run)
    assert "0.0.1" in T.text_of(run.text, w.out / "sequence.log"), run.text
    T.assert_twin_runs(w, box, monkeypatch, lambda: T.set_version(target, dist, T.S2_VERSIONS[dist]))


def test_a_venv_changed_before_the_leg_is_not_started(tmp_path, monkeypatch, box):
    """[N] failure path (3): a worktree whose `.venv` has mlx 0.32.3 at leg entry → the leg refuses NOT_STARTED (the OFF smoke
    before it VALID), the run stops rc 1."""
    w = T.make_arms_world(tmp_path)
    box.before_leg["math500-p426s2-on-smoke"] = lambda: T.set_version(w.on / ".venv", "mlx", "0.32.3")
    run = T.run_sequencer(w, box, T.s2_argv(w, axes=["math500"]), monkeypatch)
    assert run.rc not in (0, None), run.why()
    assert T.launched_names(box) == ["math500-p426s2-off-smoke", "math500-p426s2-on-smoke"], run.why()
    assert T.receipt(w.out / "receipts", "math500-p426s2-off-smoke")["verdict"] == "VALID"
    doc = T.receipt(w.out / "receipts", "math500-p426s2-on-smoke")
    assert doc["verdict"] == "NOT_STARTED" and any("0.32.3" in p for p in doc["problems"]), doc["problems"]
    assert len(box.drivers) == 1


def test_a_venv_changed_during_the_leg_invalidates_it(tmp_path, monkeypatch, box):
    """[N] §4: every K2 check compares at entry AND exit — a venv change during the leg → INVALID."""
    w = T.make_arms_world(tmp_path)
    box.during_driver["math500-p426s2-off-smoke"] = lambda: T.set_version(w.off / ".venv-bench", "datasets", "4.0.0")
    run = T.run_sequencer(w, box, T.s2_argv(w, axes=["math500"]), monkeypatch)
    assert run.rc not in (0, None) and T.launched_names(box) == ["math500-p426s2-off-smoke"], run.why()
    assert T.receipt(w.out / "receipts", "math500-p426s2-off-smoke")["verdict"] == "INVALID"


# POST-REVEAL tw-3: control twin — the same record with `build: s2` runs.
def test_a_record_with_a_wrong_label_is_refused(tmp_path, monkeypatch, box):
    """[N] §4: the record carries `build`; a `frozen.s2.json` whose `build` is not `s2` is not S′'s record."""
    w = T.make_arms_world(tmp_path)
    T.write_frozen_s2(w, build="s")
    T.assert_refused_before_launch(T.run_sequencer(w, box, T.s2_argv(w, axes=["m1"]), monkeypatch))
    T.assert_twin_runs(w, box, monkeypatch, lambda: T.write_frozen_s2(w))


def test_a_valid_record_harvests_as_the_s2_run_file(tmp_path, monkeypatch, box):
    """[N] §4: after validation the record is harvested to `wave1.s2/run/frozen.s2.json`, byte-equal (no path to scrub)."""
    w = T.make_arms_world(tmp_path)
    run = T.run_sequencer(w, box, T.s2_argv(w, axes=["m1"]), monkeypatch)
    assert run.rc == 0, run.why()
    assert (w.main / "benchmark/results/p426/wave1.s2/run/frozen.s2.json").read_bytes() == w.frozen.read_bytes()
