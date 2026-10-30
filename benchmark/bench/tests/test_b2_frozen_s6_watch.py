"""P426 B2 frozen tests, s6 watch (spec v3.2 §8, §16.2 `bench_watch.main(argv, *, power=None, clock=None)`, P469).

Classes: [FIX] reproduces a failure the spec fixes; [INV] preserves an invariant; [NEW] exercises new behaviour.
The decode-rate estimator is `p426_reconcile.decode_rate` (tested in s4). Not covered (no named seam, report): the
speed-valid verdict, the pair rule, the sequencer's watcher-death poll."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from bench.tests import b2_frozen_support as S

sys.path.insert(0, str(S.BENCH / "m1"))
import bench_watch as W  # noqa: E402

PAIR = f"{S.MODEL},{S.MODEL2}"


def test_fix_p469_the_watch_line_counts_the_legs_validated_pilot_rows(tmp_path, monkeypatch):
    """P469 red test (§8): the rehearsal shape — validated pilot invocation with 1 row, full invocation running with 0 —
    reads 1 (the base commit read 0)."""
    env = S.chain_env(tmp_path, monkeypatch, out="c147-smoke")
    t1c = S._t1c()

    def helper():
        t1c.wait_for(lambda: any(" WATCH " in ln and " a2:" in ln for ln in env["lines"]), 30)
        (env["out"] / "STOP").write_text("")
    try:
        rc = S.run_chain(env, ["chain", "s1", "--smoke", "--probe-code-sha", S.HEX9, "--models", PAIR],
                         plan=["normal", "hang_in_item"], timers=dict(watch_s=0.1), helper=helper)
        assert rc == 3
        watch = [ln for ln in env["lines"] if " WATCH " in ln and " a2:" in ln]
        assert watch and all(re.search(r" a2: 1/2 ", ln) for ln in watch), watch[:2]
    finally:
        env["ops"].cancel()


def _chain_json(tmp_path, monkeypatch):
    """A real chain.json: the legacy pilot of the fixture ops (`Chain.write_json`)."""
    env = S.chain_env(tmp_path, monkeypatch)
    try:
        assert S.run_chain(env, ["pilot", "--models", S.MODEL]) == 0
    finally:
        env["ops"].cancel()
    return Path(env["out"]) / "chain.json"


def _watch(tmp_path, monkeypatch, power, sleep_s=0.6):
    cj = _chain_json(tmp_path, monkeypatch)
    out = cj.parent / "watch.jsonl"                          # §16.1: <out-root>/watch.jsonl
    driver = subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({sleep_s})"])
    try:
        rc = W.main(["--chain-json", str(cj), "--driver-pid", str(driver.pid), "--out", str(out), "--interval", "0.1"],
                    power=power)
    finally:
        driver.wait(10)
    return rc, [json.loads(ln) for ln in out.read_text().splitlines() if ln.strip()]


def test_new_the_watcher_writes_one_json_receipt_line_per_tick_then_exit_state(tmp_path, monkeypatch):
    calls = []

    def power():
        calls.append(1)
        return {"watts": 140, "volts": 28, "battery": 80, "on_battery_intervals": []}
    rc, lines = _watch(tmp_path, monkeypatch, power)
    assert rc == 0 and calls
    ticks, last = lines[:-1], lines[-1]
    assert "exit_state" in last and not any("exit_state" in t for t in ticks)
    assert len(ticks) >= 2
    for t in ticks:
        text = json.dumps(t)
        assert "140" in text and "28" in text and "80" in text      # the tick power reading (§8)


def test_new_the_watcher_takes_its_power_reading_only_from_the_injected_source(tmp_path, monkeypatch):
    # post-reveal (P510): `on_battery_intervals` is a list of [start, end] pairs in epoch seconds, the clock of the journal's
    # `t` (the watcher's default clock here is time.time); the fixture's ISO strings were a format §16.2 left open
    import time
    monkeypatch.setattr(W, "read_power", lambda: (_ for _ in ()).throw(AssertionError("pmset read")))
    t0 = time.time()
    rc, lines = _watch(tmp_path, monkeypatch, lambda: {"watts": 96, "volts": 20, "battery": 15,
                                                       "on_battery_intervals": [[t0 - 3600.0, t0 - 3540.0]]})
    assert rc == 0 and "exit_state" in lines[-1]
    assert any("96" in json.dumps(t) for t in lines[:-1])


def test_inv_the_legacy_watcher_invocation_still_requires_its_rows_arguments():
    import pytest
    with pytest.raises(SystemExit):
        W.main(["--driver-pid", "1", "--out", "/dev/null"])
