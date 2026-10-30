"""P426 B2 frozen tests, delivery 1d: the expected worker argv and the pins (spec v3.2 §3, §6.3, §16.5).

Classes: [FIX] reproduces a failure the spec fixes; [INV] preserves an invariant; [NEW] exercises new behaviour (all NEW here).
Hermetic `--p426` pilot legs (`b2_frozen_add_support.world`). The expected argv comes from `ChainOps.expected_worker_argv`
(mlx-serve's builder); the observed one from `ChainOps.proc_argv(<worker pid>)` and must equal it exactly (§16.7, 1i). The
pins are `<WT>/src/mlx-vlm/dev/p369_phase2/pins.json`."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.tests import b2_frozen_add_support as A
from bench.tests import b2_frozen_support as S

PAIRS = [["--draft-kind", "mtp"], ["--draft-model", S.DRAFTER], ["--mtp-verify-scan", "joint_v1"]]


def run(tmp_path, monkeypatch, arm="off", worker_argv=None, before=None):
    env = A.world(tmp_path, monkeypatch, arm=arm)
    ops = env["ops"]
    if worker_argv is not None:
        base = ops.proc_argv
        ops.proc_argv = lambda pid: worker_argv(ops) if ops.ident and pid == ops.ident["pid"] else base(pid)
    if before:
        before(env)
    argv, r = S.p426_argv(env, ("pilot",))
    try:
        rc = S.run_p426(env, argv, rfd=r)
    finally:
        ops.cancel()
    return rc, env


def off_argv(ops):
    reg = Path(ops.overlay).with_name("off_view.yaml")
    reg.write_text(S.registry_text((S.MODEL,)))
    return S.served_worker_argv(reg, S.MODEL)


def started_items(env):
    return bool(list(Path(env["out"]).rglob("*.item0.go")))


def test_new_an_on_worker_equal_to_the_argv_mlx_serve_builds_passes(tmp_path, monkeypatch):
    """§6.3 / §16.7 (1i): the worker argv equals the expected argv exactly (the world's worker runs mlx-serve's own argv)."""
    rc, env = run(tmp_path, monkeypatch, "on")
    assert rc == 0, "\n".join(env["lines"][-20:])


def test_fix_an_on_worker_with_the_three_pairs_at_another_position_is_systemic(tmp_path, monkeypatch):
    """§16.7 (1i): exact, not position-free — mlx-serve places the pairs mid-argv; the same tokens appended at the end differ.
    (Position-free is the pair gate's rule between the two legs' receipts, §16.5, not the after-load argv check.)"""
    rc, env = run(tmp_path, monkeypatch, "on", worker_argv=lambda ops: off_argv(ops) + [x for p in PAIRS for x in p])
    assert rc == 2 and env["ops"].names("load") and not started_items(env)    # refused after load, before item one


@pytest.mark.parametrize("prefix", [["/usr/bin/arch", "-arm64"], ["/usr/bin/env"]], ids=["arch", "env"])
def test_fix_a_worker_argv_with_extra_leading_tokens_is_systemic(tmp_path, monkeypatch, prefix):
    """§16.7 (1i): no tolerated leading tokens."""
    rc, env = run(tmp_path, monkeypatch, "off", worker_argv=lambda ops: prefix + off_argv(ops))
    assert rc == 2 and env["ops"].names("load") and not started_items(env)


def test_fix_an_on_worker_missing_one_pair_is_systemic(tmp_path, monkeypatch):
    rc, env = run(tmp_path, monkeypatch, "on", worker_argv=lambda ops: off_argv(ops) + [x for p in PAIRS[:2] for x in p])
    assert rc == 2 and env["ops"].names("load") and not started_items(env)    # refused after load, before item one


def test_fix_an_on_worker_whose_off_tokens_are_reordered_is_systemic(tmp_path, monkeypatch):
    def reordered(ops):
        a = S.served_worker_argv(ops.overlay, S.MODEL)
        i, j = a.index("--host"), a.index("--port")
        a[i:i + 2], a[j:j + 2] = a[j:j + 2], a[i:i + 2]
        return a
    rc, env = run(tmp_path, monkeypatch, "on", worker_argv=reordered)
    assert rc == 2 and env["ops"].names("load") and not started_items(env)    # refused after load, before item one


def test_fix_an_off_worker_with_an_extra_flag_is_systemic(tmp_path, monkeypatch):
    rc, env = run(tmp_path, monkeypatch, "off", worker_argv=lambda ops: off_argv(ops) + ["--kv-bits", "4"])
    assert rc == 2 and env["ops"].names("load") and not started_items(env)    # refused after load, before item one


def test_fix_an_off_worker_with_drafter_flags_is_systemic(tmp_path, monkeypatch):
    rc, env = run(tmp_path, monkeypatch, "off", worker_argv=lambda ops: off_argv(ops) + [x for p in PAIRS for x in p])
    assert rc == 2 and env["ops"].names("load") and not started_items(env)    # refused after load, before item one


def test_new_a_snapshot_that_differs_from_the_worktrees_pins_refuses_at_entry(tmp_path, monkeypatch):
    def drift_pins(env):
        p = env["wt"] / "src/mlx-vlm/dev/p369_phase2/pins.json"
        doc = json.loads(p.read_text())
        doc[S.MODEL]["target"]["revision"] = "0" * 40
        p.write_text(json.dumps(doc))
    rc, env = run(tmp_path, monkeypatch, before=drift_pins)
    assert rc == 2 and not env["ops"].names("start_router")
    assert any("REFUSED: " in ln for ln in env["lines"])
