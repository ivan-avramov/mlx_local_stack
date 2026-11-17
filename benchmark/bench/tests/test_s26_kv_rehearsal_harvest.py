"""S26-P8 (session 26, found on the first real M76 tg1 KV rehearsal, `20261117a`): two defects stopped R1's harvest.

1. `p426_harvest` could not resolve the arm worktree of a KV tg1 rehearsal leg: `_arm_of` reads `tg1-m76-rehearsal-<arm>` as no arm
   and the negative legs (`-mismatch`, `-kill`) as P426's `on` / `off`, which a KV record does not name. The KV table (`kv_legs`)
   runs R1 on each arm, R2 (mismatch) on the treatment and R3 (kill) on the reference: `leg_worktree` maps those names through the
   record's KV arms (reference, treatment); every other name keeps `_arm_of`.
2. The Wave 2 sequencer launched `benchmark/m1/bench_watch.py` without `PYTHONPATH`, so the watcher died on `import bench` (the leg
   is speed-invalid). `BoxSeqOps.launch` puts the launched worktree's `benchmark/` first on the watcher's `PYTHONPATH` (P444's rule,
   as `p426_leg._watcher_for`); other launches (the chain) keep the inherited environment.
"""
import json
import os
import sys
from pathlib import Path

import pytest

from bench import p426_harvest as H
from bench import p426_wave2 as w2


def _kv_leg(tmp_path, name, arms=("n16", "x")):
    wd = tmp_path / "wd"
    trees = {a: wd / "worktrees" / f"arm-{a}" for a in arms}
    for t in trees.values():
        t.mkdir(parents=True)
    rec = wd / "m76" / "p426" / "rehearsal" / "manifest.json"
    rec.parent.mkdir(parents=True, exist_ok=True)
    rec.write_text(json.dumps(dict(kind="p426_rehearsal", lever="kv", arms=list(arms),
                                   **{f"{a}_worktree": f"$STACK_WORKDIR/worktrees/arm-{a}" for a in arms})))
    leg = rec.parent / "r" / f"{name}.a1"
    leg.mkdir(parents=True)
    (leg / "chain.json").write_text(json.dumps(dict(argv=["run_tg1_chain.py", "chain", "s1", "--frozen-record",
                                                          "$STACK_WORKDIR/m76/p426/rehearsal/manifest.json"])))
    return leg, wd, trees


@pytest.mark.parametrize("name,arm", [("tg1-m76-rehearsal-n16", "n16"), ("tg1-m76-rehearsal-x", "x"),
                                      ("tg1-m76-rehearsal-mismatch", "x"), ("tg1-m76-rehearsal-kill", "n16")])
def test_a_kv_tg1_rehearsal_leg_resolves_its_arm_worktree(tmp_path, name, arm):
    leg, wd, trees = _kv_leg(tmp_path, name)
    assert H.leg_worktree(leg, wd) == trees[arm]


def test_the_kv_rehearsal_negatives_follow_the_pair_order_not_the_arm_names(tmp_path):
    leg, wd, trees = _kv_leg(tmp_path, "tg1-m76-rehearsal-mismatch", arms=("x", "v"))
    assert H.leg_worktree(leg, wd) == trees["v"]


@pytest.mark.parametrize("name,arm", [("tg1-m76-n16-pilot", "n16"), ("tg1-m76-x-s1", "x"), ("tg2-m76-x-rehearsal-r2", "x"),
                                      ("tg2-m76-n16-rehearsal-r3", "n16")])
def test_kv_session_and_tg2_legs_resolve_as_before(tmp_path, name, arm):
    leg, wd, trees = _kv_leg(tmp_path, name)
    assert H._arm_of(name) == arm and H.leg_worktree(leg, wd) == trees[arm]


def _kv_pairs():
    from bench import p426_plan
    return [tuple(p) for p in p426_plan.KV_PAIRS]


@pytest.mark.parametrize("pair", _kv_pairs())
def test_every_kv_tg1_leg_of_every_pair_resolves_the_arm_that_runs_it(tmp_path, pair):
    table = w2.kv_legs(*pair)
    for spec in table["run"] + table["makeup"] + table["rehearsal"]:
        leg, wd, trees = _kv_leg(tmp_path / spec["name"], spec["name"], arms=pair)
        assert H.leg_worktree(leg, wd) == trees[spec["arm"]], spec["name"]


def test_every_tg2_leg_resolves_the_arm_that_runs_it(tmp_path):
    table = w2.kv_tg2_legs("n16", "x")
    for spec in [s for rows in table.values() for s in rows]:
        leg, wd, trees = _kv_leg(tmp_path / spec["name"], spec["name"])
        assert H.leg_worktree(leg, wd) == trees[spec["arm"]], spec["name"]


def test_p426_mtp_rehearsal_names_keep_off_on(tmp_path):
    wd = tmp_path / "wd"
    rec = wd / "p426" / "rehearsal" / "manifest.json"
    rec.parent.mkdir(parents=True)
    (wd / "off").mkdir(); (wd / "on").mkdir()
    rec.write_text(json.dumps(dict(kind="p426_rehearsal", off_worktree="$STACK_WORKDIR/off", on_worktree="$STACK_WORKDIR/on")))
    for name, arm in (("tg1-p426-rehearsal-mismatch", "on"), ("tg1-p426-rehearsal-kill", "off"), ("tg1-p426-rehearsal-off", "off")):
        leg = rec.parent / "r" / f"{name}.a1"
        leg.mkdir(parents=True)
        (leg / "chain.json").write_text(json.dumps(dict(argv=["--frozen-record", "$STACK_WORKDIR/p426/rehearsal/manifest.json"])))
        assert H.leg_worktree(leg, wd) == wd / arm


def test_an_unreadable_record_resolves_no_worktree(tmp_path):
    leg = tmp_path / "tg1-m76-rehearsal-kill.a1"
    leg.mkdir()
    assert H.leg_worktree(leg, tmp_path) is None


def _arm_tree(tmp_path):
    wt = tmp_path / "arm"
    (wt / "benchmark" / "bench").mkdir(parents=True)
    (wt / "benchmark" / "bench" / "__init__.py").write_text("MARK = 'arm-bench'\n")
    (wt / "benchmark" / "m1").mkdir()
    probe = ("import json, os, sys\n"
             "out = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else sys.argv[sys.argv.index('--out-root') + 1] + '.json'\n"
             "try:\n    import bench; mark = bench.MARK\nexcept ImportError:\n    mark = None\n"
             "json.dump(dict(mark=mark, pythonpath=os.environ.get('PYTHONPATH')), open(out, 'w'))\n")
    (wt / "benchmark" / "m1" / "bench_watch.py").write_text(probe)
    (wt / "benchmark" / "chain_probe.py").write_text(probe)
    return wt


def _wait(ops, h):
    ops._procs[h.pid].wait(timeout=60)


def test_the_sequencer_launches_the_watcher_with_the_arm_benchmark_importable(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTHONPATH", raising=False)
    wt = _arm_tree(tmp_path)
    ops = w2.BoxSeqOps(tmp_path / "wd", main_root=tmp_path / "main", evidence_stage=tmp_path / "stage")
    out = tmp_path / "leg" / "watch.jsonl"
    out.parent.mkdir()
    h = ops.launch([sys.executable, str(wt / "benchmark/m1/bench_watch.py"), "--out", str(out)], cwd=wt, pass_fds=())
    _wait(ops, h)
    got = json.loads(out.read_text())
    assert got["mark"] == "arm-bench"
    assert got["pythonpath"].split(os.pathsep)[0] == str(wt / "benchmark")


def test_an_inherited_pythonpath_stays_behind_the_arm_benchmark(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/elsewhere")
    wt = _arm_tree(tmp_path)
    ops = w2.BoxSeqOps(tmp_path / "wd", main_root=tmp_path / "main", evidence_stage=tmp_path / "stage")
    out = tmp_path / "leg" / "watch.jsonl"
    out.parent.mkdir()
    _wait(ops, ops.launch([sys.executable, str(wt / "benchmark/m1/bench_watch.py"), "--out", str(out)], cwd=wt, pass_fds=()))
    assert json.loads(out.read_text())["pythonpath"].split(os.pathsep) == [str(wt / "benchmark"), "/elsewhere"]


def test_a_relative_worktree_still_gives_the_watcher_an_absolute_arm_benchmark(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTHONPATH", raising=False)
    wt = _arm_tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    ops = w2.BoxSeqOps(tmp_path / "wd", main_root=tmp_path / "main", evidence_stage=tmp_path / "stage")
    out = tmp_path / "leg" / "watch.jsonl"
    out.parent.mkdir()
    _wait(ops, ops.launch([sys.executable, str(wt / "benchmark/m1/bench_watch.py"), "--out", str(out)], cwd=Path("arm"), pass_fds=()))
    got = json.loads(out.read_text())
    assert got["mark"] == "arm-bench" and got["pythonpath"].split(os.pathsep)[0] == str(wt.resolve() / "benchmark")


@pytest.mark.parametrize("inherited", [None, "/elsewhere"])
def test_a_chain_launch_keeps_the_inherited_environment(tmp_path, monkeypatch, inherited):
    if inherited is None:
        monkeypatch.delenv("PYTHONPATH", raising=False)
    else:
        monkeypatch.setenv("PYTHONPATH", inherited)
    wt = _arm_tree(tmp_path)
    ops = w2.BoxSeqOps(tmp_path / "wd", main_root=tmp_path / "main", evidence_stage=tmp_path / "stage")
    root = tmp_path / "out" / "leg.a1"
    root.parent.mkdir()
    _wait(ops, ops.launch([sys.executable, str(wt / "benchmark/chain_probe.py"), "--out-root", str(root)], cwd=wt, pass_fds=()))
    assert json.loads(Path(str(root) + ".json").read_text())["pythonpath"] == inherited
