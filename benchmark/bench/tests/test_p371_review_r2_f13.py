"""P371 review r2 F13: an A4 receipt is written to a temp file in the same directory, fsynced, then linked exclusively into its
reserved destination, so the destination is absent or complete. A resume removes a leftover temp (listed) and adopts a complete
destination (F10); a torn destination (the old O_EXCL-then-write window) still refuses explicitly."""
from __future__ import annotations

import pytest

from bench import chain_core
from bench.tests.m64_support import SMOKE, Crash, chain_json, env, log_has, run      # noqa: F401  (fixture: env)


def crash_on_a4_link(monkeypatch):
    real = chain_core.os.link

    def link(src, dst, *a, **k):
        if "/a4/" in str(dst):
            raise Crash()
        return real(src, dst, *a, **k)
    monkeypatch.setattr(chain_core.os, "link", link)
    return real


def test_a_crash_between_the_temp_write_and_the_link_leaves_no_destination_and_resumes(env, monkeypatch):
    real = crash_on_a4_link(monkeypatch)
    with pytest.raises(Crash):
        run(env, SMOKE)
    monkeypatch.setattr(chain_core.os, "link", real)
    a4 = env["out"] / "a4"
    assert not (a4 / "0.0.oc.json").exists()
    temps = [p for p in a4.iterdir() if p.name.startswith(".")]
    assert len(temps) == 1 and temps[0].stat().st_size > 0
    assert run(env, SMOKE) == 0
    assert not [p for p in a4.iterdir() if p.name.startswith(".")] and log_has(env, "removed leftover")
    workers = chain_json(env)["progress"]["loads"][0]["workers"]
    assert [w["n"] for w in workers] == [0, 1] and workers[1]["a4_receipts"]


def test_a_torn_destination_refuses_explicitly(env, monkeypatch):
    real = crash_on_a4_link(monkeypatch)
    with pytest.raises(Crash):
        run(env, SMOKE)
    monkeypatch.setattr(chain_core.os, "link", real)
    (env["out"] / "a4" / "0.0.oc.json").write_text('{"torn": ')
    assert run(env, SMOKE) == 2 and log_has(env, "orphaned A4 receipt")
