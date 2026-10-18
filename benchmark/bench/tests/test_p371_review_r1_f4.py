"""P371 review r1 F4: archive / quarantine moves are a two-phase TRANSACTION persisted in chain.json (`progress.txns`): the
intent (every src -> dst with its sha256, the record repoints and attempt archivals) is fsynced BEFORE the first move; the moves
are idempotent; the commit repoints the records. A resume completes (rolls forward) a transaction a crash left open: no file is
lost, no record points at a missing file, every sha256 is verified."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bench import chain_core
from bench import chain_rows as cr
from bench.tests.m64_support import (  # noqa: F401  (fixture: env)
    FAP, PICK1, SMOKE, Crash, chain_json, env, kill_probes, log_has, run)
from bench.tests.test_p371_m64_resume import LEG3_SLOT2, CrashAt, crash_run


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def running_files(env):
    """(record, {name: sha256}) of the one `running` invocation a crash left, and every file of its base."""
    rec = next(i for i in chain_json(env)["progress"]["invocations"] if i["status"] == "running")
    path = env["out"] / rec["file"]
    base = path.name[:-len(".jsonl")] + "."
    return rec, {f.name: sha(f) for f in sorted(path.parent.iterdir()) if f.is_file() and f.name.startswith(base)}


class MoveCrash:
    """Crashes the n-th `shutil.move` of the chain (a process death in the middle of the move phase)."""

    def __init__(self, monkeypatch, n):
        self.n, self.calls, self.real = n, 0, chain_core.shutil.move
        monkeypatch.setattr(chain_core.shutil, "move", self)

    def __call__(self, src, dst):
        self.calls += 1
        if self.calls == self.n:
            raise Crash()
        return self.real(src, dst)


def quarantined(env, rec_file):
    return next(i for i in chain_json(env)["progress"]["invocations"] if i["file"].endswith(Path(rec_file).name)
                or Path(i["file"]).name == Path(rec_file).name)


@pytest.mark.parametrize("after", [0, 1, "all_but_last"])
def test_a_crash_mid_quarantine_resumes_to_one_complete_quarantine_with_no_file_lost(env, monkeypatch, after):
    crash_run(env, CrashAt(LEG3_SLOT2))
    rec, before = running_files(env)
    assert len(before) >= 3 and rec["file"].endswith(".jsonl")
    k = len(before) - 1 if after == "all_but_last" else after
    mover = MoveCrash(monkeypatch, k + 1)
    with pytest.raises(Crash):
        run(env, SMOKE)
    assert mover.calls == k + 1
    monkeypatch.setattr(chain_core.shutil, "move", mover.real)
    assert run(env, SMOKE) == 0
    cj = chain_json(env)
    got = quarantined(env, rec["file"])
    assert got["status"] == "quarantined"
    dest = (env["out"] / got["file"]).parent
    # every file the crashed invocation had is in ONE quarantine directory with its recorded sha256, the manifest names them
    assert {f.name: sha(f) for f in dest.iterdir() if f.name != "MANIFEST.json"} == before
    assert json.loads((dest / "MANIFEST.json").read_text())["files"] == before
    assert (env["out"] / got["file"]).is_file() and sha(env["out"] / got["file"]) == before[Path(rec["file"]).name]
    assert (env["out"] / got["manifest"]).is_file()
    leftovers = [f.name for f in (env["out"] / "s1").iterdir() if f.name in before]
    assert leftovers == [] and len(list((env["out"] / "quarantine").iterdir())) == 1
    assert [t["status"] for t in cj["progress"]["txns"]] == ["committed"]
    assert len(cr.load_slots(cj, env["out"]).scored) == 16


def test_the_intent_is_durable_before_the_first_file_moves(env, monkeypatch):
    crash_run(env, CrashAt(LEG3_SLOT2))
    rec, before = running_files(env)
    seen = []
    real = chain_core.shutil.move

    def spy(src, dst):
        if not seen:
            txns = chain_json(env)["progress"]["txns"]
            seen.append([(t["status"], sorted(f["sha256"] for f in t["files"])) for t in txns])
        return real(src, dst)
    monkeypatch.setattr(chain_core.shutil, "move", spy)
    assert run(env, SMOKE) == 0
    assert seen == [[("intent", sorted(before.values()))]]


def test_a_changed_file_or_a_vanished_file_aborts_the_recovery_instead_of_guessing(env, monkeypatch):
    crash_run(env, CrashAt(LEG3_SLOT2))
    rec, before = running_files(env)
    mover = MoveCrash(monkeypatch, 2)
    with pytest.raises(Crash):
        run(env, SMOKE)
    monkeypatch.setattr(chain_core.shutil, "move", mover.real)
    base = (env["out"] / rec["file"]).name[:-len(".jsonl")] + "."
    left = [f for f in (env["out"] / "s1").iterdir() if f.name.startswith(base)]
    assert left
    left[0].write_text("tampered\n")
    assert run(env, SMOKE) == 2 and log_has(env, "transaction")
