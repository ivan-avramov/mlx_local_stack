"""P371 review r1 F4 on the tg1 configuration (`restart_load`): a crash in the middle of `archive_load`'s file moves, and one after the
last move but before the commit, resume to ONE complete archive (every file with its recorded sha256), the load rerun with
`load_gen + 1`, and no record pointing at a missing file."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from bench import chain_core
from bench import chain_rows as cr
from bench.tests.test_c147_chain_runner import CHAIN, chain_json, env, log_has, run      # noqa: F401  (fixture: env)
from bench.tests.test_p371_chain_core import PLAN_RESTART


class Crash(BaseException):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def crash_in_archive(env, monkeypatch, n):
    calls = {"n": 0}
    real = chain_core.shutil.move

    def mover(src, dst):
        calls["n"] += 1
        if calls["n"] == n:
            raise Crash()
        return real(src, dst)
    monkeypatch.setattr(chain_core.shutil, "move", mover)
    with pytest.raises(Crash):
        run(env, CHAIN, plan=PLAN_RESTART)
    monkeypatch.setattr(chain_core.shutil, "move", real)
    return calls["n"]


@pytest.mark.parametrize("n", [1, 3])
def test_a_crash_mid_archive_load_resumes_to_one_complete_archive(env, monkeypatch, n):
    crash_in_archive(env, monkeypatch, n)
    cj = chain_json(env)
    (txn,) = [t for t in cj["progress"]["txns"] if t["kind"] == "archive_load" and t["status"] == "intent"]
    assert len(txn["files"]) > n
    assert run(env, CHAIN, plan=["normal"]) == 0
    cj = chain_json(env)
    (arch,) = cj["progress"]["loads"][0]["archives"]
    dest = env["out"] / arch["dir"]
    assert {f.name: sha(f) for f in dest.iterdir()} == arch["files"]
    assert all(t["status"] == "committed" for t in cj["progress"]["txns"])
    old = [i for i in cj["progress"]["invocations"] if i["load_gen"] == 0 and i["leg_key"][0] == 0]
    assert old and all(i["status"] == "archived" for i in old)
    assert all((env["out"] / i["file"]).exists() for i in old if Path(i["file"]).name in arch["files"])
    assert cj["progress"]["loads"][0]["load_gen"] == 1 and cj["progress"]["loads"][0]["status"] == "done"
    assert len(cr.load_slots(cj, env["out"]).scored) == 24


def test_a_crash_after_the_last_move_before_the_commit_resumes_without_a_second_archive(env, monkeypatch):
    real = chain_core.Chain.apply_txn_op

    def boom(self, op):
        raise Crash()
    monkeypatch.setattr(chain_core.Chain, "apply_txn_op", boom)
    with pytest.raises(Crash):
        run(env, CHAIN, plan=PLAN_RESTART)
    monkeypatch.setattr(chain_core.Chain, "apply_txn_op", real)
    assert [t["status"] for t in chain_json(env)["progress"]["txns"]] == ["intent"]
    assert run(env, CHAIN, plan=["normal"]) == 0
    cj = chain_json(env)
    assert len(cj["progress"]["loads"][0]["archives"]) == 1 and cj["progress"]["loads"][0]["load_gen"] == 1
    assert len(cr.load_slots(cj, env["out"]).scored) == 24
