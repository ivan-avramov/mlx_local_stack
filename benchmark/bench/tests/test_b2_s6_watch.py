"""B2 slice s6: the P426 watcher (spec 8, 16.1, 16.2), the speed-validity verdict, the pair rule, the decode-rate estimator
as the B6 / B8 input, and P469 (`Chain.watch_rows`).

Hermetic: `power=` / `clock=` / `sleep=` are injected, the driver is a throw-away `python -c` sleeper, the real `pmset` is never
called, and no stack process is started.
"""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "m1"))
import bench_watch as W  # noqa: E402

from bench import chain_core as cc  # noqa: E402
from bench import p426_reconcile as pr  # noqa: E402

INTERVAL = 300.0
T0 = 1_000_000.0
SESSION, LANG = "s1", "python"
BASE = f"tg1-p426|oc|MODEL|{SESSION}|{LANG}"


def good(**kw):
    return dict(dict(watts=140, volts=28, battery=80, on_battery_intervals=[]), **kw)


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def driver():
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    yield p
    if p.poll() is None:
        p.kill()
    p.wait()


def slot(item):
    return f"{BASE}|{item}"


def write_chain(root, *, ledger=(), dnf=(), invocations=(), rows=None):
    """A leg out-root: chain.json (the §16.5 keys) + the rows files the invocations name."""
    root = Path(root)
    (root / SESSION).mkdir(parents=True, exist_ok=True)
    for rel, rws in (rows or {}).items():
        (root / rel).write_text("".join(json.dumps(r) + "\n" for r in rws))
    doc = dict(status="running", p426_ledger=list(ledger), p426_dnf=list(dnf), p426_invalid=[],
               progress=dict(invocations=list(invocations)))
    (root / "chain.json").write_text(json.dumps(doc))
    return root / "chain.json"


def ledger_entry(item, kind="row", index=0):
    return dict(slot=slot(item), kind=kind, invocation="x", index=index)


def row(item, wall=100.0, **kw):
    return dict(dict(id=f"{LANG}/{item}", wall_s=wall, passed=True, converged=True,
                     gate=dict(output_tokens_completed=1000)), **kw)


def run_watcher(tmp_path, driver, *, power, steps=2, chain=None, extra=(), hook=None, clock=None):
    """Run the P426 watcher until `steps` sleeps have passed, then the driver is killed (its exit ends the watcher)."""
    clock = clock or Clock()
    chain = chain or write_chain(tmp_path / "leg")
    out = Path(chain).parent / "watch.jsonl"
    seen = []

    def sleep(s):
        seen.append(s)
        clock.t += s
        if hook:
            hook(len(seen), clock)
        if len(seen) >= steps:
            driver.kill()
            driver.wait()

    rc = W.main(["--chain-json", str(chain), "--driver-pid", str(driver.pid), "--out", str(out),
                 "--interval", str(INTERVAL), *extra], power=power, clock=clock, sleep=sleep)
    lines = [json.loads(x) for x in out.read_text().splitlines()] if out.exists() else []
    return rc, lines, out


# ---------------------------------------------------------------------------------------------- the tick journal
def test_one_journal_line_per_tick_with_the_section_8_fields(tmp_path, driver):
    rows_rel = f"{SESSION}/m.pilot.a1.jsonl"
    chain = write_chain(
        tmp_path / "leg",
        ledger=[ledger_entry("a", index=0), ledger_entry("b", "dnf", 1)], dnf=[dict(slot=slot("b"))],
        invocations=[dict(file=rows_rel, status="running", expected_slots=[slot(i) for i in "abcde"], phase="pilot")],
        rows={rows_rel: [row("a", 120.0), row("c", 80.0, error="boom", converged=False)]},
    )
    rc, lines, _ = run_watcher(tmp_path, driver, power=lambda: good(), steps=2, chain=chain)
    ticks = [x for x in lines if "exit_state" not in x]
    assert rc == 0 and len(ticks) == 3                     # t0, +300, +600 (driver killed during the last sleep)
    t = ticks[0]
    assert (t["watts"], t["volts"], t["battery"]) == (140, 28, 80)
    assert t["driver_alive"] is True and t["driver"]["pid"] == driver.pid and t["driver"]["start"]
    assert t["t"] == T0 and ticks[1]["t"] == T0 + INTERVAL and t["interval_s"] == INTERVAL
    assert t["progress"] == dict(done=2, planned=5) and t["rows"] == 1 and t["dnf"] == 1
    assert t["current_item"] == "c"                        # the first planned slot not in the ledger
    assert t["errors"] == 1 and t["convergence"] == 0.5
    assert t["tokens"] == dict(p50=1000, p90=1000, max=1000) and t["budget_hits"] == 0
    assert t["eta"]["mean_item_wall_s"] == pytest.approx(100.0)
    assert t["eta"]["eta_s"] == pytest.approx(300.0) and t["eta"]["pred_item_s"] > 0 and "ratio" in t["eta"]
    assert isinstance(t["note"], str) and t["note"] and t["correction"] in (True, False)
    assert ticks[-1]["driver_alive"] is False


def test_progress_is_the_ledger_length_over_the_explicit_plan(tmp_path, driver):
    chain = write_chain(tmp_path / "leg", ledger=[ledger_entry("a"), ledger_entry("b", index=1)])
    _, lines, _ = run_watcher(tmp_path, driver, power=lambda: good(), steps=1, chain=chain, extra=["--planned", "43"])
    assert lines[0]["progress"] == dict(done=2, planned=43)


def test_an_eta_far_above_the_prediction_says_correction_may_beat_finishing(tmp_path, driver):
    rows_rel = f"{SESSION}/m.pilot.a1.jsonl"
    chain = write_chain(
        tmp_path / "leg", ledger=[ledger_entry(i, index=k) for k, i in enumerate("abcde")],
        invocations=[dict(file=rows_rel, status="validated", expected_slots=[slot(i) for i in "abcde"], phase="pilot")],
        rows={rows_rel: [row(i, 900.0) for i in "abcde"]})
    _, lines, _ = run_watcher(tmp_path, driver, power=lambda: good(), steps=1, chain=chain,
                              extra=["--planned", "20", "--pred-s", "250"])
    t = lines[0]
    assert t["eta"]["ratio"] > 1.5 and t["correction"] is True and "CORRECTION" in t["note"]


def test_the_driver_is_bound_by_pid_and_start_time(tmp_path, driver, monkeypatch):
    """A pid whose start time is not the bound one is a different process: the driver is gone."""
    starts = iter(["Mon Jan  1 00:00:00 2026", "Tue Feb  2 00:00:00 2026"])
    monkeypatch.setattr(W, "_pid_start", lambda pid: next(starts, "Tue Feb  2 00:00:00 2026"))
    rc, lines, _ = run_watcher(tmp_path, driver, power=lambda: good(), steps=5)
    ticks = [x for x in lines if "exit_state" not in x]
    assert ticks[0]["driver"]["start"] == "Mon Jan  1 00:00:00 2026"
    assert len(ticks) == 1 and ticks[0]["driver_alive"] is False                # reuse detected at the first tick
    assert lines[-1]["exit_state"] == "driver_exited"


def test_the_watcher_never_signals_the_driver_and_a_bad_tick_never_stops_a_leg(tmp_path, driver):
    """C235 G2: in-run power is recorded, never acted on; the watcher exits 0 only because the driver exited."""
    killed = []
    rc, lines, out = run_watcher(tmp_path, driver, power=lambda: good(watts=96), steps=3,
                                 hook=lambda k, c: killed.append(driver.poll()))
    assert killed[:2] == [None, None]                      # alive through the bad ticks: nothing stopped it
    assert rc == 0
    end = lines[-1]
    assert end["exit_state"] == "driver_exited" and "speed_valid" not in end            # P52: the verdict is the sequencer's
    assert W.speed_verdict(out)["valid"] is False and "140" in W.speed_verdict(out)["reason"]


# ---------------------------------------------------------------------------------------------- exit_state
def test_exit_state_carries_only_the_battery_intervals_over_the_leg_window(tmp_path, driver):
    inside = [T0 + 100, T0 + 200]
    power = lambda: good(on_battery_intervals=[[T0 - 5000, T0 - 4000], inside, [T0 + 9e6, T0 + 9e6 + 5]])
    _, lines, out = run_watcher(tmp_path, driver, power=power, steps=2)
    end = lines[-1]
    assert end["exit_state"] == "driver_exited" and end["battery_intervals"] == [dict(start=inside[0], end=inside[1])]
    assert (end["window"]["start"], end["window"]["end"]) == (T0, T0 + 2 * INTERVAL)
    assert W.speed_verdict(out)["valid"] is False and "battery" in W.speed_verdict(out)["reason"]
    assert end["ticks"] == 3 and end["interval_s"] == INTERVAL


def test_a_clean_leg_is_speed_valid_and_the_journal_finalized(tmp_path, driver):
    _, lines, out = run_watcher(tmp_path, driver, power=lambda: good(), steps=2)
    assert lines[-1]["exit_state"] == "driver_exited" and "speed_valid" not in lines[-1]
    assert W.speed_verdict(out) == dict(valid=True, reason="ok")
    assert sum("exit_state" in x for x in lines) == 1 and "exit_state" in lines[-1]


def test_an_unreadable_battery_log_is_not_a_clean_window(tmp_path, driver):
    _, lines, out = run_watcher(tmp_path, driver, power=lambda: good(on_battery_intervals=None), steps=1)
    assert W.speed_verdict(out)["valid"] is False and "unreadable" in W.speed_verdict(out)["reason"]


def test_power_raising_is_an_unreadable_reading_not_a_crash(tmp_path, driver):
    def boom():
        raise OSError("pmset gone")
    rc, lines, out = run_watcher(tmp_path, driver, power=boom, steps=1)
    assert rc == 0 and lines[0]["watts"] is None and W.speed_verdict(out)["valid"] is False


# ---------------------------------------------------------------------------------------------- the verdict
def journal(tmp_path, ticks, *, exit_line=True, interval=INTERVAL, battery=()):
    path = Path(tmp_path) / "watch.jsonl"
    lines = [dict(dict(t=T0 + i * interval, at=f"t{i}", interval_s=interval, watts=140, volts=28, battery=80,
                       driver_alive=True), **kw)
             for i, kw in enumerate(ticks)]
    if exit_line:
        lines.append(dict(exit_state="driver_exited", battery_intervals=list(battery), interval_s=interval,
                          t=T0 + len(ticks) * interval))
    path.write_text("".join(json.dumps(x) + "\n" for x in lines))
    return path


@pytest.mark.parametrize("kw, word", [
    (dict(watts=96), "watts"), (dict(volts=20), "volts"), (dict(battery=20), "battery"),
    (dict(battery=None), "battery"), (dict(watts=None), "watts"),
])
def test_a_tick_off_140_w_28_v_or_battery_not_above_20_is_speed_invalid(tmp_path, kw, word):
    v = W.speed_verdict(journal(tmp_path, [{}, kw, {}]))
    assert v["valid"] is False and word in v["reason"]


def test_a_good_journal_is_speed_valid(tmp_path):
    assert W.speed_verdict(journal(tmp_path, [{}, {}, {}])) == dict(valid=True, reason="ok")


def test_a_tick_gap_over_twice_the_interval_is_speed_invalid_exactly_at_the_bound(tmp_path):
    ok = journal(tmp_path, [{}, {}], interval=INTERVAL)
    lines = [json.loads(x) for x in ok.read_text().splitlines()]
    lines[1]["t"] = lines[0]["t"] + 2 * INTERVAL                          # exactly 2x: allowed
    ok.write_text("".join(json.dumps(x) + "\n" for x in lines))
    assert W.speed_verdict(ok)["valid"] is True
    lines[1]["t"] += 1                                                     # beyond 2x
    ok.write_text("".join(json.dumps(x) + "\n" for x in lines))
    v = W.speed_verdict(ok)
    assert v["valid"] is False and "gap" in v["reason"]


def test_an_on_battery_interval_in_the_window_is_speed_invalid(tmp_path):
    v = W.speed_verdict(journal(tmp_path, [{}, {}], battery=[dict(start=T0 + 10, end=T0 + 20)]))
    assert v["valid"] is False and "battery" in v["reason"]


def test_a_journal_without_exit_state_is_not_finalized(tmp_path):
    v = W.speed_verdict(journal(tmp_path, [{}, {}], exit_line=False))
    assert v["valid"] is False and "final" in v["reason"]


def test_a_missing_or_empty_journal_is_speed_invalid(tmp_path):
    assert W.speed_verdict(tmp_path / "nope.jsonl")["valid"] is False
    (tmp_path / "e.jsonl").write_text("")
    assert W.speed_verdict(tmp_path / "e.jsonl")["valid"] is False
    (tmp_path / "bad.jsonl").write_text("{not json\n")
    assert W.speed_verdict(tmp_path / "bad.jsonl")["valid"] is False


# ---------------------------------------------------------------------------------------------- pmset log
PMLOG = """\
2026-10-27 09:00:00 -0700 Sleep   Entering Sleep state due to 'Idle Sleep' Using AC (Charge:100%) 5 secs
2026-10-27 10:00:00 -0700 Wake    Wake from Normal Sleep [CDNVA] : due to SMC.OutboxNotEmpty Using BATT (Charge:91%) 3 secs
2026-10-27 10:30:00 -0700 Assertions   PID 1(x) Created InternalPreventSleep Using BATT (Charge:88%)
2026-10-27 11:00:00 -0700 Wake    Wake from Normal Sleep due to EC.LidOpen Using AC (Charge:87%) 3 secs
"""


def test_the_battery_log_parser_yields_the_on_battery_runs():
    import datetime as dt
    iv = W.parse_battery_log(PMLOG, now=dt.datetime(2026, 10, 27, 12, 0, 0, tzinfo=dt.timezone(dt.timedelta(hours=-7))).timestamp())
    tz = dt.timezone(dt.timedelta(hours=-7))
    t = lambda h, m=0: dt.datetime(2026, 10, 27, h, m, tzinfo=tz).timestamp()
    assert iv == [[t(10), t(11)]]


def test_a_battery_run_still_open_at_the_end_runs_to_now():
    import datetime as dt
    tz = dt.timezone(dt.timedelta(hours=-7))
    now = dt.datetime(2026, 10, 27, 12, 0, tzinfo=tz).timestamp()
    iv = W.parse_battery_log(PMLOG.rsplit("\n", 2)[0] + "\n", now=now)
    assert iv == [[dt.datetime(2026, 10, 27, 10, tzinfo=tz).timestamp(), now]]


# ---------------------------------------------------------------------------------------------- the pair rule
def test_both_sessions_valid_is_an_order_balanced_inference():
    out = W.pair_speed({"s1": {"off": True, "on": True}, "s2": {"off": True, "on": True}})
    assert out["mode"] == "inference" and out["valid_sessions"] == ["s1", "s2"] and out["note"] is None


@pytest.mark.parametrize("bad", [("s1", "off"), ("s1", "on"), ("s2", "off"), ("s2", "on")])
def test_one_invalid_leg_removes_that_sessions_comparison_and_leaves_a_descriptive_ratio(bad):
    legs = {"s1": {"off": True, "on": True}, "s2": {"off": True, "on": True}}
    legs[bad[0]][bad[1]] = dict(speed_valid=False, speed_reason="gap")           # a leg record is accepted as well
    out = W.pair_speed(legs)
    keep = "s2" if bad[0] == "s1" else "s1"
    assert out["mode"] == "descriptive" and out["valid_sessions"] == [keep] and out["excluded"] == [bad[0]]
    assert out["note"] == "not order-balanced"


def test_no_valid_session_leaves_no_speed_comparison_and_a_missing_leg_is_invalid():
    assert W.pair_speed({"s1": {"off": False, "on": True}, "s2": {"off": True, "on": False}})["mode"] == "none"
    assert W.pair_speed({"s1": {"off": True}, "s2": {"off": True, "on": True}})["valid_sessions"] == ["s2"]


# ---------------------------------------------------------------------------------------------- decode estimator
def rq(generated, **kw):
    return dict(dict(generated_tokens=generated, error=None), **kw)


def item_rate(requests, before, after):
    return pr.decode_rate(requests, pr.decode_time(after) - pr.decode_time(before))


def test_the_item_rate_is_tokens_minus_one_per_request_over_the_workers_delta_d():
    before = dict(generated_tokens_total=1000, avg_decode_tok_s=50.0)           # D = 20 s
    after = dict(generated_tokens_total=1300, avg_decode_tok_s=50.0)            # D = 26 s
    rate = item_rate([rq(101), rq(201)], before, after)
    assert rate == pytest.approx((100 + 200) / 6.0)


def test_zero_and_one_token_requests_add_no_tokens_but_their_time_stays_in_delta_d():
    before = dict(generated_tokens_total=0, avg_decode_tok_s=0.0)
    after = dict(generated_tokens_total=12, avg_decode_tok_s=4.0)               # D = 3 s, 2 requests of 1 and 0 tokens + one of 11
    assert item_rate([rq(11), rq(1), rq(0)], before, after) == pytest.approx(10 / 3.0)
    assert pr.short_requests([rq(11), rq(1), rq(0)]) is not None
    assert item_rate([rq(1), rq(0)], before, after) == 0.0


def test_a_zero_or_negative_delta_d_has_no_rate():
    same = dict(generated_tokens_total=500, avg_decode_tok_s=25.0)
    assert item_rate([rq(11)], same, same) is None
    assert pr.decode_rate([rq(11)], -1.0) is None and pr.decode_rate([], 2.0) == 0.0


# ---------------------------------------------------------------------------------------------- P469
def test_watch_rows_counts_the_earlier_validated_invocations_plus_the_running_one(tmp_path):
    """The rehearsal shape: the validated pilot invocation has 1 row, the running full invocation has none yet: reads 1."""
    files = {"pilot.jsonl": [row("a")], "full.jsonl": []}
    ops = SimpleNamespace(rows=lambda f: files[Path(f).name])
    chain = SimpleNamespace(ops=ops)
    leg = dict(lang=LANG, out="full.jsonl", prior_files=["pilot.jsonl"], prior_ids=["a"])      # prior ids are the bare names
    rows, ids = cc.Chain.watch_rows(chain, leg, dict(names=["b", "c"]))
    assert len(rows) == 1 and ids == [f"{LANG}/a", f"{LANG}/b", f"{LANG}/c"]


def test_watch_rows_accepts_prefixed_prior_ids_and_still_drops_foreign_rows(tmp_path):
    files = {"pilot.jsonl": [row("a"), dict(row("z"), id="go/z")], "full.jsonl": [row("b")]}
    chain = SimpleNamespace(ops=SimpleNamespace(rows=lambda f: files[Path(f).name]))
    leg = dict(lang=LANG, out="full.jsonl", prior_files=["pilot.jsonl"], prior_ids=[f"{LANG}/a"])
    rows, _ = cc.Chain.watch_rows(chain, leg, dict(names=["b"]))
    assert [r["id"] for r in rows] == [f"{LANG}/a", f"{LANG}/b"]


# ---------------------------------------------------------------------------------------------- legacy argv
def test_the_legacy_argv_still_parses_and_still_requires_its_own_flags():
    a = W._parse_args(["--models", "m", "--bench", "b", "--total", "3", "--driver-pid", "7", "--out", "o"])
    assert (a.models, a.bench, a.total, a.driver_pid, a.chain_json) == ("m", "b", 3, 7, None)
    for argv in (["--bench", "b", "--total", "3", "--driver-pid", "7", "--out", "o"],
                 ["--models", "m", "--bench", "b", "--total", "3", "--out", "o"],
                 ["--models", "m", "--bench", "b", "--driver-pid", "7", "--out", "o"]):
        with pytest.raises(SystemExit):
            W._parse_args(argv)


def test_the_p426_argv_needs_only_chain_json_driver_pid_and_out():
    a = W._parse_args(["--chain-json", "c.json", "--driver-pid", "7", "--out", "w.jsonl"])
    assert a.chain_json == "c.json" and a.driver_pid == 7 and a.interval == 300.0
    for argv in (["--chain-json", "c.json", "--out", "w.jsonl"], ["--chain-json", "c.json", "--driver-pid", "7"]):
        with pytest.raises(SystemExit):
            W._parse_args(argv)


def test_the_legacy_monitor_loop_is_untouched_by_the_p426_mode(tmp_path, monkeypatch, capsys):
    out = tmp_path / "w.log"
    monkeypatch.setattr(W, "read_power", lambda: dict(watts=140, volts=28, batt=80))
    monkeypatch.setattr(W, "_pid_alive", lambda pid: False)
    rc = W.main(["--models", "m", "--bench", "b", "--total", "3", "--driver-pid", "7", "--out", str(out),
                 "--rows-file", str(tmp_path / "none.jsonl")])
    text = out.read_text()
    assert rc == 0 and "POWER ok 140W 28V batt=80%" in text and "DRIVER EXITED" in text and "{" not in text.splitlines()[0]
