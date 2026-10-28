"""P426 T3 frozen tests — the fix round's failing cases (strict verify V3, V4; C241 / P507): the p371 differential accepts only
the pinned toolchain lock pair, and a venv holding two dist-infos of a checked package refuses at the sequencer and at leg
entry. Each case has its control twin. (V1 / V2: `test_t3_frozen_arms.py::test_the_restore_is_exactly_the_p511_bytes`.)

Classes: [N] exercises new behaviour; [I] preserves an invariant; [R] reproduces a failure the specification fixes."""

import json

import pytest

from bench.tests import t3_frozen_support as T
from bench.tests.t3_frozen_support import box  # noqa: F401 — the fake-box fixture

POINTER = "/runs/0/manifest/runtime/policy/toolchain/lock_sha256"  # the one pointer the exception covers (new_side.rederive)


def _golden_lock():
    """The toolchain lock sha the p371 goldens hold (`bench/tests/p371_baseline/golden/*.json`, `runtime.policy.toolchain`)."""
    values = set()
    for p in sorted((T.REPO / "benchmark/bench/tests/p371_baseline/golden").glob("*.json")):
        text = p.read_text()
        for line in text.splitlines():
            if '"lock_sha256"' in line:
                values.add(line.split(":", 1)[1].strip().strip('",'))
    assert len(values) == 1, values
    return values.pop()


def _committed_lock():
    """The sha256 of this tree's committed `benchmark/requirements-bench.lock` (on the candidate: the S′ bench lock)."""
    return T.sha256_file(T.REPO / "benchmark" / "requirements-bench.lock")


def _hook():
    from bench.tests.p371_baseline import new_side

    return new_side.rederive({})


# POST-REVEAL tw-4: [R] V3 / C241 (P507) — a lock pair other than the pinned one is a difference; control twin: the pinned pair
# (the goldens' value → the committed S′ bench-lock sha) is accepted.
@pytest.mark.parametrize("case", ["other-new", "other-old", "reversed", "unchanged-golden", "near-miss"])
def test_a_lock_pair_other_than_the_pinned_one_fails_the_p371_rederive(case):
    golden, committed = _golden_lock(), _committed_lock()
    old, new = {"other-new": (golden, "0" * 64), "other-old": ("1" * 64, committed), "reversed": (committed, golden),
                "unchanged-golden": (golden, golden), "near-miss": (golden, committed[:-1] + ("0" if committed[-1] != "0" else "1"))}[case]
    assert _hook()(POINTER, golden, committed) is True, "control twin: the pinned pair must be accepted"
    assert (old, new) != (golden, committed)
    assert _hook()(POINTER, old, new) is False


def _add_dist_info(venv, name, version):
    """A second dist-info of `name` beside the one the venv already holds (the shape a non-sync install can leave)."""
    d = T.site_packages(venv) / f"{name.replace('-', '_')}-{version}.dist-info"
    d.mkdir()
    (d / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")
    return d


@pytest.mark.parametrize("arm, venv", [("off", ".venv"), ("on", ".venv-bench")])
# POST-REVEAL tw-4: [R] V4 — two dist-infos of `mlx` in one venv refuse at the sequencer (the record holds 0.32.4, the venv holds
# 0.32.4 AND 0.32.3); control twin: the same world with the stale dist-info removed runs.
def test_two_dist_infos_of_mlx_refuse_at_the_sequencer(tmp_path, monkeypatch, box, arm, venv):
    w = T.make_arms_world(tmp_path)
    stale = _add_dist_info((w.on if arm == "on" else w.off) / venv, "mlx", "0.32.3")
    run = T.run_sequencer(w, box, T.s2_argv(w, axes=["m1"]), monkeypatch)
    T.assert_refused_before_launch(run)
    import shutil

    T.assert_twin_runs(w, box, monkeypatch, lambda: shutil.rmtree(stale))


# POST-REVEAL tw-4: [R] V4 — a second `mlx` dist-info appearing after the sequencer's check refuses the leg at entry
# (NOT_STARTED; the OFF smoke before it VALID); control twin: a fresh world of the same shape runs that leg VALID.
def test_two_dist_infos_of_mlx_refuse_at_leg_entry(tmp_path, monkeypatch, box):
    w = T.make_arms_world(tmp_path / "defect")
    leg = "math500-p426s2-on-smoke"
    box.before_leg[leg] = lambda: _add_dist_info(w.on / ".venv-bench", "mlx", "0.32.3")
    run = T.run_sequencer(w, box, T.s2_argv(w, axes=["math500"]), monkeypatch)
    assert run.rc not in (0, None) and T.launched_names(box) == ["math500-p426s2-off-smoke", leg], run.why()
    assert T.receipt(w.out / "receipts", "math500-p426s2-off-smoke")["verdict"] == "VALID"
    doc = T.receipt(w.out / "receipts", leg)
    assert doc["verdict"] == "NOT_STARTED", doc["problems"]
    assert len(box.drivers) == 1
    box.before_leg.pop(leg)  # the twin is the same shape WITHOUT the defect: its hook must not fire again
    twin = T.make_arms_world(tmp_path / "twin")
    ok = T.run_sequencer(twin, box, T.s2_argv(twin, axes=["math500"]), monkeypatch)
    assert ok.rc == 0, ok.why()
    assert T.receipt(twin.out / "receipts", leg)["verdict"] == "VALID"


# POST-REVEAL tw-4: [I] the golden value the V3 cases read is the goldens' one recorded value (a fixture check, both sides).
def test_the_goldens_hold_one_toolchain_lock_value():
    golden = _golden_lock()
    assert len(golden) == 64 and int(golden, 16) >= 0
    assert json.dumps(golden)
