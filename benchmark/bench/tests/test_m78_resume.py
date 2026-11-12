"""M78 (S22-P16, C327): the two resume gaps of `bench.p475_kv`.

(1) An interruption between `git worktree add` and the arm's registry commit leaves an arm worktree at the base commit; the next
`prepare` must complete it (submodules + the arm commit), not refuse it as divergent. A dirty or unrelated worktree still refuses.
(2) An interruption between the dossier's publication and `LAST_LEG_END` must never leave a published dossier with a stale idle
marker (a resumed run would start the next leg without the 600 s idle): the marker is written before the dossier's single atomic
rename, so an interruption leaves either nothing published (resume replays the harvest and rewrites the marker) or both.
"""
from __future__ import annotations

import os
import shutil

import pytest

from bench import p475_kv as K
from bench.tests.test_m76_b1_fe_support import PrepOps, cli
from bench.tests.test_p475_impl_fixes import leg
from bench.tests.test_p475_impl_support import BASE, FakeOps, base_registry, make_cfg


# ------------------------------------------------------------------ (1) prepare after an interruption
def _interrupted(tmp_path, arm="AF8"):
    wd, repo = tmp_path / "wd", tmp_path / "repo"
    repo.mkdir()
    wd.mkdir()
    ops = PrepOps(base_registry())
    br = f"p475-u4-{arm.lower()}"
    path = str(wd / "worktrees" / br)
    os.makedirs(path)                                  # `git worktree add -b <br>` ran; the arm commit did not
    ops.branches[br], ops.heads[path], ops.wt_branch[path] = BASE, BASE, br
    return ops, wd, repo, br


def test_an_arm_worktree_left_at_the_base_by_an_interruption_is_completed(tmp_path):
    # class: reproduces the failure S22-P16 (1) fixes
    ops, wd, repo, br = _interrupted(tmp_path)
    assert cli(["--workdir", str(wd), "--repo", str(repo), "--base", BASE, "prepare"], ops) == 0
    want = K.arm_registry_text(base_registry(), "AF8", K.PICK)
    assert ops.committed(br) == want


def test_a_dirty_interrupted_arm_worktree_still_refuses(tmp_path):
    # class: preserves an invariant (never repair a dirty arm)
    ops, wd, repo, br = _interrupted(tmp_path)
    real = ops.worktree_state

    def dirty(wt):
        s = real(wt)
        return dict(s, clean=False) if str(wt).endswith(br) else s
    ops.worktree_state = dirty
    assert cli(["--workdir", str(wd), "--repo", str(repo), "--base", BASE, "prepare"], ops) != 0
    assert ops.committed(br) is None


def test_the_base_arm_worktree_at_the_base_gets_no_commit(tmp_path):
    # class: preserves an invariant (the base arm is the base commit itself)
    ops, wd, repo, br = _interrupted(tmp_path, arm="TQ4")
    assert cli(["--workdir", str(wd), "--repo", str(repo), "--base", BASE, "prepare"], ops) == 0
    assert ops.committed(br) is None


# ------------------------------------------------------------------ (2) harvest interrupted at the idle marker
@pytest.fixture
def world(tmp_path):
    ops, cfg = FakeOps(tmp_path), make_cfg(tmp_path)
    ops.add_all(cfg)
    return ops, cfg


def test_an_interruption_at_the_idle_marker_never_leaves_a_published_dossier_with_a_stale_marker(world, monkeypatch):
    # class: reproduces the failure S22-P16 (2) fixes
    ops, cfg = world
    name, r = leg(ops, cfg)
    assert r["_harvest"] == "harvested"
    shutil.rmtree(cfg.dossier(name))                   # replay the harvest from the canonical receipt
    marker = cfg.p475 / "LAST_LEG_END"
    before = marker.read_text()
    ops.t += 5000.0
    real_replace = os.replace

    def interrupted(src, dst, *a, **kw):
        if str(dst) == str(marker):
            raise KeyboardInterrupt("interrupted at the idle marker")
        return real_replace(src, dst, *a, **kw)
    monkeypatch.setattr(K.os, "replace", interrupted)
    with pytest.raises(KeyboardInterrupt):
        K.harvest(name, ops, cfg)
    monkeypatch.setattr(K.os, "replace", real_replace)
    published = cfg.dossier(name).exists()
    stale = marker.read_text() == before
    assert not (published and stale), "a published dossier with a stale LAST_LEG_END lets a resumed leg skip the idle"
    done, problems = K.replay_harvests(ops, cfg)    # the resume path
    assert problems == []
    assert cfg.dossier(name).exists() and marker.read_text() != before
