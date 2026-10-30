"""P426 B2 frozen tests, delivery 1d: the after-load busy census (spec v3.2 §3, §9, §16.5).

Classes: [FIX] reproduces a failure the spec fixes; [INV] preserves an invariant; [NEW] exercises new behaviour (all NEW here).
`ChainOps.busy_procs()` lists `"<pid> <command>"` lines (chain_ops.py:335-347); the chain exempts the owned router / worker by
`(pid, start)` and its descendants by `ChainOps.descendants(pid)`; anything else is foreign → systemic. The listed lines are
data only (no such process exists)."""
from __future__ import annotations

from pathlib import Path

from bench.tests import b2_frozen_add_support as A
from bench.tests import b2_frozen_support as S


def run(tmp_path, monkeypatch, busy_after_load):
    env = A.world(tmp_path, monkeypatch, descendants={9999})
    ops = env["ops"]
    ops.busy_procs = lambda: busy_after_load(ops) if ops.loaded else []
    argv, r = S.p426_argv(env, ("pilot",))
    try:
        rc = S.run_p426(env, argv, rfd=r)
    finally:
        ops.cancel()
    return rc, env


def owned_lines(ops):
    return [f"{ops.ident['pid']} {' '.join(S.served_worker_argv(ops.overlay, S.MODEL))}", "1 mlx-serve start"]


def test_new_the_owned_router_worker_and_the_chains_descendants_are_exempt(tmp_path, monkeypatch):
    rc, env = run(tmp_path, monkeypatch, lambda ops: owned_lines(ops) + ["9999 python benchmark/bench/tests/b2_frozen_support.py"])
    assert rc == 0, "\n".join(env["lines"][-20:])


def test_new_a_foreign_model_worker_after_load_is_systemic(tmp_path, monkeypatch):
    rc, env = run(tmp_path, monkeypatch, lambda ops: owned_lines(ops) + ["4242 python -m mlx_vlm.server --model other"])
    assert rc == 2 and env["ops"].names("load")
    assert not list(Path(env["out"]).rglob("*.item0.go"))


def test_new_a_foreign_benchmark_driver_after_load_is_systemic(tmp_path, monkeypatch):
    rc, env = run(tmp_path, monkeypatch, lambda ops: owned_lines(ops) + ["4343 python benchmark/run_lcb.py --model other"])
    assert rc == 2 and env["ops"].names("load") and not list(Path(env["out"]).rglob("*.item0.go"))
