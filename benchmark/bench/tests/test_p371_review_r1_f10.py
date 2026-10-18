"""P371 review r1 F10: a crash after an immutable A4 receipt was created but before its worker record was fsynced. The worker
record (with the receipt names it reserves) is persisted BEFORE the gate runs; a resume adopts an orphaned receipt (sha256 and
worker binding verified) instead of aborting on the stale filename, and takes a fresh worker."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bench import chain_core
from bench.tests.m64_support import (  # noqa: F401  (fixture: env)
    PICK1, SMOKE, SMOKE3, Crash, calls, chain_json, env, kill_probes, log_has, run)


def crash_in_bind(monkeypatch, *, after_create, on_call=1):
    real = chain_core.Chain.bind_receipt
    seen = {"n": 0}

    def bind(self, latest, load, wn, arm):
        seen["n"] += 1
        if seen["n"] != on_call:
            return real(self, latest, load, wn, arm)
        if after_create:
            real(self, latest, load, wn, arm)
        raise Crash()
    monkeypatch.setattr(chain_core.Chain, "bind_receipt", bind)
    return real


def test_a_crash_after_the_receipt_was_created_before_its_record_resumes_by_adopting_it(env, monkeypatch):
    real = crash_in_bind(monkeypatch, after_create=True)
    with pytest.raises(Crash):
        run(env, SMOKE)
    monkeypatch.setattr(chain_core.Chain, "bind_receipt", real)
    orphan = env["out"] / "a4" / "0.0.oc.json"
    assert orphan.is_file()
    sha = hashlib.sha256(orphan.read_bytes()).hexdigest()
    assert run(env, SMOKE) == 0
    cj = chain_json(env)
    workers = cj["progress"]["loads"][0]["workers"]
    assert [w["n"] for w in workers] == [0, 1]
    assert workers[0]["a4_receipts"]["oc"] == dict(path="a4/0.0.oc.json", sha256=sha) and workers[0].get("adopted") is True
    assert set(workers[1]["a4_receipts"]) == {"oc"} and workers[1]["pid"] != workers[0]["pid"]
    assert (env["out"] / "a4" / "0.1.oc.json").is_file()


def test_a_crash_before_the_receipt_was_created_resumes_with_the_reserved_worker_empty(env, monkeypatch):
    real = crash_in_bind(monkeypatch, after_create=False)
    with pytest.raises(Crash):
        run(env, SMOKE)
    monkeypatch.setattr(chain_core.Chain, "bind_receipt", real)
    assert not (env["out"] / "a4" / "0.0.oc.json").exists()
    assert run(env, SMOKE) == 0
    workers = chain_json(env)["progress"]["loads"][0]["workers"]
    assert [w["n"] for w in workers] == [0, 1] and workers[0]["a4_receipts"] == {} and workers[1]["a4_receipts"]


def test_an_orphaned_receipt_bound_to_another_arm_or_load_or_tampered_aborts_the_resume(env, monkeypatch):
    real = crash_in_bind(monkeypatch, after_create=True)
    with pytest.raises(Crash):
        run(env, SMOKE)
    monkeypatch.setattr(chain_core.Chain, "bind_receipt", real)
    orphan = env["out"] / "a4" / "0.0.oc.json"
    doc = json.loads(orphan.read_text())
    doc["bench_binding"]["worker_n"] = 7
    orphan.write_text(json.dumps(doc))
    assert run(env, SMOKE) == 2 and log_has(env, "A4 receipt")


def test_a_later_arms_crash_keeps_the_earlier_arms_receipts_referenced(env, monkeypatch):
    real = crash_in_bind(monkeypatch, after_create=True, on_call=2)
    with pytest.raises(Crash):
        run(env, SMOKE3)
    monkeypatch.setattr(chain_core.Chain, "bind_receipt", real)
    assert run(env, SMOKE3) == 0
    first = chain_json(env)["progress"]["loads"][0]["workers"][0]["a4_receipts"]
    assert set(first) == {"oc", "pi"} and all((env["out"] / r["path"]).is_file() for r in first.values())
