"""B2 final fix round: one failing-first test per queued item (`docs/reviews/p426-b2/final-fix-queue.md`, §16.8).
Hermetic: no router, worker, model, network or GPU."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import chain_core as core
from bench import chain_ops as co
from bench import chain_rows as cr
from bench.tests import b2_frozen_add_support as A
from bench.tests import b2_frozen_support as S

PILOT = S.p426_order([f"p{i}" for i in range(1, 7)], 1001)[:5]


def p426_leg(tmp_path, monkeypatch, probe_env=None):
    env = A.world(tmp_path, monkeypatch)
    env["ops"].extra_env.update(probe_env or {})
    argv, r = S.p426_argv(env, ("pilot",))
    try:
        rc = S.run_p426(env, argv, rfd=r)
    finally:
        env["ops"].cancel()
    cj = Path(env["out"]) / "chain.json"
    return rc, (json.loads(cj.read_text()) if cj.exists() else {}), env


# ------------------------------------------------------------------------------------------------ 1. flat-layout DNF refusal
def flat_chain(tmp_path, monkeypatch, *, per_arm):
    """A bare chain whose `validate_partial` is the real method: a flat tg1 leg (manifest runtime `arm: "oc"`, `epoch_id`
    None, rows without `arm` / `epoch_id`)."""
    from bench.tests.test_b2_s3_core import bare
    monkeypatch.setattr(co, "validate_leg", lambda *a, **k: [])
    c = bare(tmp_path)
    c.per_arm, c.epoch_id, c.snapshots, c.arms, c.frozen = per_arm, None, {}, {}, "Tue Oct 27 2026"
    c.arm_key, c.pinned_for, c.policy_for, c.spec_of = (lambda leg: "k"), (lambda arm: {}), (lambda arm: "p"), (lambda arm: None)
    c.ops.wd = tmp_path
    out = tmp_path / "o.jsonl"
    out.write_text(json.dumps({"id": "python/a"}) + "\n")
    out.with_suffix(".manifest.json").write_text(json.dumps({"runtime": {"arm": "oc", "epoch_id": None}}))
    leg = dict(session="s1", model="M", lang="python", seed_base=1001, arm="A", out=str(out))
    return c, leg, out


def test_validate_partial_of_a_flat_leg_does_not_apply_the_per_arm_row_checks(tmp_path, monkeypatch):
    c, leg, out = flat_chain(tmp_path, monkeypatch, per_arm=False)
    c.validate_partial(leg, out, ["python/a"], who="DNF")             # no ChainAbort


def test_validate_partial_of_a_per_arm_leg_still_applies_them(tmp_path, monkeypatch):
    c, leg, out = flat_chain(tmp_path, monkeypatch, per_arm=True)
    with pytest.raises(co.ChainAbort, match="row_arm"):
        c.validate_partial(leg, out, ["python/a"], who="DNF")


def test_a_real_p426_dnf_is_accepted_and_writes_its_item_record_path_string(tmp_path, monkeypatch):
    rc, cj, env = p426_leg(tmp_path, monkeypatch, {"B2_ABORTS": json.dumps({PILOT[1]: "boundary"})})
    assert rc == 0, "\n".join(env["lines"][-6:])
    d, = cj["p426_dnf"]
    slot_file = cr.slot_file(d["slot"])
    assert d["item_record"] == f"items/{slot_file}.dnf.json" and isinstance(d["item_record"], str)
    assert (Path(env["out"]) / "items" / f"{slot_file}.dnf.json").exists()


def test_the_dnf_limit_counts_the_whole_leg_across_languages_through_the_real_validation(tmp_path, monkeypatch):
    from bench.tests.test_b2_s3_core import BASE, incomplete
    c, leg, out = flat_chain(tmp_path, monkeypatch, per_arm=False)
    c.p426_dnf = [dict(slot=f"{BASE}|x", session="s1", language="go", arm="A"),
                  dict(slot=f"{BASE}|y", session="s2", language="python", arm="B")]
    with pytest.raises(co.ChainAbort, match="more than"):
        incomplete(c, tmp_path)


# ------------------------------------------------------------------------------------------------ 7. P44 kill detection
def test_killed_processes_without_a_kill_marker_do_not_make_a_completed_item_a_kill():
    from bench import p426_reconcile as prc
    from bench.tests.test_b2_s4_reconcile import BEFORE, after_of, lines_of, req, row_of
    ls = lines_of(*req())
    row = row_of([(100, 10)], termination=dict(killed=[dict(pid=1, create_time=1.0, role="client")], in_flight_at_kill=None,
                                               reason=None))
    rep = prc.reconcile_item(row, ls, dict(BEFORE), after_of(ls))
    assert rep.ok and rep.case == "completed"


def test_a_kill_marker_still_makes_a_kill():
    from bench import p426_reconcile as prc
    from bench.tests.test_b2_s4_reconcile import BEFORE, after_of, lines_of, req, row_of
    ls = lines_of(*req())
    row = row_of([(100, 10)], at_kill=1, kind="budget_hit_kill",
                 termination=dict(killed=[dict(pid=1, create_time=1.0, role="client")], in_flight_at_kill=0, reason="x"))
    assert prc.reconcile_item(row, ls, dict(BEFORE), after_of(ls)).case == "kill_boundary"


# ------------------------------------------------------------------------------------------------ 2. P39 record before /metrics
def test_done_with_unreadable_metrics_still_writes_an_invalid_item_record_and_invalidates(tmp_path):
    from bench.tests import test_b2_s4_reconcile as T
    ops, hooks, out = T.make_hooks(tmp_path)
    assert hooks.before_attempt(T.SLOT, T.ctx()).kind == "accept"
    ops.serve(*T.req(prompt=100, gen=10, draft=T.ON_DRAFT))
    ops.unreadable = True
    d = hooks.after_attempt(T.SLOT, dict(id="python/a"), T.ctx(T.row_of([(100, 10)])))
    assert d.kind == "invalidate" and "metrics" in d.reason
    rec = json.loads((out / "items" / f"{T.SLOT_FILE}.json").read_text())
    assert rec["verdict"] == "invalid" and rec["worker_after"] is None and any("metrics" in p for p in rec["problems"])


# ------------------------------------------------------------------------------------------------ 3. P40 stderr REFUSED:
def run_main_in_process(env, argv):
    t1c = S._t1c()
    R = t1c.R
    try:
        return R.main(list(argv), ops=env["ops"], timers=R.Timers(**t1c.TIMERS), log_out=env["lines"].append,
                      campaign=S.fake_campaign(env["commit"]))
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2


def test_an_entry_refusal_inside_the_chain_run_also_prints_the_stderr_refused_line(tmp_path, monkeypatch, capsys):
    env = A.world(tmp_path, monkeypatch)
    env["ops"].snapshot_hashes = lambda model: {"target": {}, "drafter": None}        # the snapshots differ from the pins
    argv, r = S.p426_argv(env, ("pilot",))
    try:
        rc = run_main_in_process(env, argv)
    finally:
        env["ops"].cancel()
    err = [ln for ln in capsys.readouterr().err.splitlines() if ln.startswith("REFUSED: ")]
    assert rc == 2 and len(err) == 1 and "snapshots at entry" in err[0]
    assert not env["ops"].names("start_router")


# ------------------------------------------------------------------------------------------------ 4. P41 settle bound
def test_the_settle_bound_does_not_swallow_a_record_error(tmp_path):
    bad = tmp_path / "amendment.json"
    bad.write_text("{not json")
    args = SimpleNamespace(frozen_record=str(bad), mode="chain", rehearsal=False, settle_bound_s=None)
    with pytest.raises(SystemExit) as e:
        core.Chain.p426_settle_bound(args)
    assert e.value.code == 2 and str(e.value.args[0]).startswith("REFUSED: ")


# ------------------------------------------------------------------------------------------------ 5. P42 seam signatures
def test_interpreter_inventory_takes_a_pid_never_a_path():
    import inspect
    params = inspect.signature(co.ChainOps.interpreter_inventory).parameters
    assert list(params) == ["self", "pid", "site_packages"] and params["site_packages"].kind is inspect.Parameter.KEYWORD_ONLY
    ops = co.ChainOps.__new__(co.ChainOps)
    with pytest.raises((TypeError, co.ChainAbort)):
        ops.interpreter_inventory("/some/venv/bin/python")


def test_an_interpreter_without_a_process_has_its_own_seam():
    import inspect
    assert list(inspect.signature(co.ChainOps.interpreter_inventory_at).parameters) == ["self", "exe"]
    assert "interpreter_inventory_at" in core.P426_SEAMS


def test_the_receipt_asks_the_pid_seam_only_with_pids_and_the_path_seam_for_the_probes_launch_interpreter(tmp_path):
    from bench.tests.test_b2_s5_receipt import ProcOps
    seen = []

    class Ops(ProcOps):
        def interpreter_inventory(self, pid, **kw):
            seen.append(("pid", pid))
            return super().interpreter_inventory(pid, **kw)

        def interpreter_inventory_at(self, exe):
            seen.append(("path", exe))
            return dict(self.interp)
    ops = Ops("off", str(tmp_path))
    from bench import p426_receipt as pr
    pr.arm_receipt(ops, worktree=ops.wt, out_root=ops.out, pids=dict(router=10, worker=20, probe=None), model="Some-Model",
                   probe_launch=ops.launch)
    assert seen == [("pid", 10), ("pid", 20), ("path", ops.launch["argv"][0])]


def test_worktree_state_takes_the_worktree_path_and_the_chain_passes_it(tmp_path, monkeypatch):
    import inspect
    assert list(inspect.signature(co.ChainOps.worktree_state).parameters) == ["self", "path"]
    env = A.world(tmp_path, monkeypatch)
    ops, asked = env["ops"], []
    base = ops.worktree_state

    def worktree_state(*a):
        asked.append(a)
        return base(*a)
    ops.worktree_state = worktree_state
    argv, r = S.p426_argv(env, ("pilot",))
    try:
        assert S.run_p426(env, argv, rfd=r) == 0
    finally:
        ops.cancel()
    assert asked and all(len(a) == 1 and Path(a[0]) == Path(env["wt"]) for a in asked)


# ------------------------------------------------------------------------------------------------ 9. P530 fake probe environment
def test_the_fake_probe_environment_never_inherits_mlx_serve_config(tmp_path, monkeypatch):
    from bench.tests.test_c147_chain_runner import FakeOps
    monkeypatch.setenv("MLX_SERVE_CONFIG", "/somewhere/else.yaml")
    inherited = "MLX_SERVE_CONFIG" in FakeOps(tmp_path).env_base()          # a bool: a failure never renders the environment
    assert not inherited


# ------------------------------------------------------------------------------------------------ 6. P43 dossier verdict consistency
def dossier_inputs(tmp_path, *, break_on=False):
    from bench import p426_receipt as pr
    off, on = S.arm_receipt_doc("off"), S.arm_receipt_doc("on")
    if break_on:
        body = {k: v for k, v in on.items() if k != "sha256"}
        on = S.self_hashed(dict(body, probe_entry="<WT>/benchmark/other_probe.py"))
    assert bool(pr.pair_problems(off, on)) is break_on
    ro = S.write_record(tmp_path / "off.a1/receipt.json", off)
    rn = S.write_record(tmp_path / "on.a1/receipt.json", on)
    ho = S.write_record(tmp_path / "off.a1/HARVEST.json", S.self_hashed({"leg": "tg1-p426-off-pilot", "attempt": 1}))
    hn = S.write_record(tmp_path / "on.a1/HARVEST.json", S.self_hashed({"leg": "tg1-p426-on-pilot", "attempt": 1}))
    return dict(pair="pilot", off=dict(attempt="tg1-p426-off-pilot.a1", receipt=ro, harvest=ho),
                on=dict(attempt="tg1-p426-on-pilot.a1", receipt=rn, harvest=hn), differences=[])


def test_a_passing_dossier_whose_receipts_have_pair_problems_is_refused(tmp_path):
    from bench import p426_receipt as pr
    kw = dossier_inputs(tmp_path, break_on=True)
    path = tmp_path / "pairs" / "pilot__off-a1__on-a1.json"
    with pytest.raises(ValueError, match="PASS"):
        pr.write_dossier(path, verdict="PASS", **kw)
    assert not path.exists()
    assert pr.write_dossier(path, verdict="FAIL", **kw)["verdict"] == "FAIL"        # a failing dossier records the failure


def test_a_passing_dossier_of_consistent_receipts_is_written(tmp_path):
    from bench import p426_receipt as pr
    path = tmp_path / "pairs" / "pilot__off-a1__on-a1.json"
    assert pr.write_dossier(path, verdict="PASS", **dossier_inputs(tmp_path))["verdict"] == "PASS"


# ------------------------------------------------------------------------------------------------ 8. the s6 watcher
import subprocess  # noqa: E402
import sys  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "m1"))
import bench_watch as W  # noqa: E402

from bench.tests import test_b2_s6_watch as T6  # noqa: E402

driver = T6.driver                                       # the throw-away `python -c` sleeper fixture
INTERVAL, T0, good = T6.INTERVAL, T6.T0, T6.good


def test_the_driver_start_time_is_proc_guards_never_ps_lstart(tmp_path, driver, monkeypatch):
    import psutil
    from bench import proc_guard
    real_run = subprocess.run

    def run(cmd, *a, **k):
        assert "lstart=" not in cmd, "the driver start time was read from `ps -o lstart`"
        return real_run(cmd, *a, **k)
    monkeypatch.setattr(W.subprocess, "run", run)
    expected = proc_guard.start_time(psutil.Process(driver.pid))
    _, lines, _ = T6.run_watcher(tmp_path, driver, power=lambda: good(), steps=1)
    assert lines[0]["driver"]["start"] == expected and isinstance(expected, float)


@pytest.mark.parametrize("intervals", [[["2026-10-27T00:00:00Z", "2026-10-27T00:01:00Z"]], [[1.0]], ["junk"], [{"from": 1}], "x"],
                         ids=["iso-strings", "short-pair", "not-a-pair", "dict", "not-a-list"])
def test_p510_a_malformed_on_battery_interval_leaves_the_window_unproven(tmp_path, driver, intervals):
    rc, lines, out = T6.run_watcher(tmp_path, driver, power=lambda: good(on_battery_intervals=intervals), steps=1)
    assert rc == 0 and sum("exit_state" in x for x in lines) == 1 and lines[-1]["battery_intervals"] is None
    v = W.speed_verdict(out)
    assert v["valid"] is False and "battery" in v["reason"]


def test_p47_a_liveness_read_failure_is_not_an_exit(tmp_path, driver, monkeypatch):
    real, calls = W._pid_start, []

    def flaky(pid):
        calls.append(pid)
        return None if len(calls) == 2 else real(pid)            # the bind works; the first tick's read fails
    monkeypatch.setattr(W, "_pid_start", flaky)
    _, lines, _ = T6.run_watcher(tmp_path, driver, power=lambda: good(), steps=2)
    ticks = [x for x in lines if "exit_state" not in x]
    assert len(ticks) == 3 and ticks[0]["driver_alive"] is None and ticks[1]["driver_alive"] is True


def test_p47_a_driver_that_could_not_be_bound_at_start_is_bound_on_a_later_tick(tmp_path, driver, monkeypatch):
    real, calls = W._pid_start, []

    def late(pid):
        calls.append(pid)
        return None if len(calls) == 1 else real(pid)
    monkeypatch.setattr(W, "_pid_start", late)
    _, lines, out = T6.run_watcher(tmp_path, driver, power=lambda: good(), steps=2)
    ticks = [x for x in lines if "exit_state" not in x]
    assert len(ticks) == 3 and ticks[0]["driver_alive"] is True and ticks[0]["driver"]["start"] is not None
    assert W.speed_verdict(out)["valid"] is True


@pytest.mark.parametrize("alive", [False, None], ids=["gone", "unknown"])
def test_p47_speed_valid_needs_a_tick_with_the_driver_bound_and_alive_and_power_observed(tmp_path, alive):
    v = W.speed_verdict(T6.journal(tmp_path, [dict(driver_alive=alive), dict(driver_alive=alive)]))
    assert v["valid"] is False and "driver" in v["reason"]
    unobserved = W.speed_verdict(T6.journal(tmp_path, [dict(watts=None, volts=None, battery=None), dict(driver_alive=False)]))
    assert unobserved["valid"] is False


PMLOG = T6.PMLOG                                            # lines from 2026-10-27 09:00 -0700 on


def test_p48_no_source_line_at_or_before_the_window_start_leaves_the_intervals_unproven():
    import datetime as dt
    tz = dt.timezone(dt.timedelta(hours=-7))
    at = lambda h, m=0: dt.datetime(2026, 10, 27, h, m, tzinfo=tz).timestamp()  # noqa: E731
    now = at(12)
    assert W.parse_battery_log(PMLOG, now=now, since=at(8)) is None               # the log starts after the window did
    assert W.parse_battery_log(PMLOG, now=now, since=at(9)) == [[at(10), at(11)]]    # a source line at the window start proves it
    assert W.parse_battery_log(PMLOG, now=now, since=at(9, 30)) == [[at(10), at(11)]]
    assert W.parse_battery_log("no source lines here\n", now=now, since=at(9)) is None
    assert W.parse_battery_log(PMLOG, now=now) == [[at(10), at(11)]]                 # without a window: as before


def pmset_fake(monkeypatch, log_text):
    real_run, seen = subprocess.run, []

    def run(cmd, *a, **k):
        if cmd[:1] == ["pmset"]:
            seen.append(cmd[1:])
            text = {"ac": "Wattage = 140W\nVoltage = 28V\n", "batt": "Now drawing from 'AC Power'\n 80%; charging\n",
                    "log": log_text}[cmd[2]]
            return subprocess.CompletedProcess(cmd, 0, stdout=text, stderr="")
        return real_run(cmd, *a, **k)
    monkeypatch.setattr(W.subprocess, "run", run)
    return seen


def test_p50_the_default_power_reads_pmset_log_once_at_exit_not_per_tick(tmp_path, driver, monkeypatch):
    seen = pmset_fake(monkeypatch, PMLOG)
    clock = T6.Clock(T0)
    chain = T6.write_chain(tmp_path / "leg")
    out = Path(chain).parent / "watch.jsonl"
    stops = []

    def sleep(s):
        stops.append(s)
        clock.t += s
        if len(stops) >= 3:
            driver.kill()
            driver.wait()
    W.main(["--chain-json", str(chain), "--driver-pid", str(driver.pid), "--out", str(out), "--interval", str(INTERVAL)],
           clock=clock, sleep=sleep)
    ticks = [json.loads(x) for x in out.read_text().splitlines() if "exit_state" not in x]
    assert len(ticks) == 4 and sum(c[:2] == ["-g", "log"] for c in seen) == 1
    assert sum(c[:2] == ["-g", "ac"] for c in seen) >= 4                    # the meter itself is read every tick
    assert all("on_battery_intervals" not in t for t in ticks)


def test_p48_the_default_exit_reading_with_a_log_that_starts_after_the_window_is_unproven(tmp_path, driver, monkeypatch):
    pmset_fake(monkeypatch, PMLOG)                          # the log starts 2026-10-27; the fake clock's window is 1970
    _, lines, out = T6.run_watcher(tmp_path, driver, power=None, steps=1)
    assert lines[-1]["battery_intervals"] is None and W.speed_verdict(out)["valid"] is False


def test_p51_the_planned_slots_come_from_the_frozen_schedule_and_planned_only_overrides(tmp_path, driver):
    from bench import schedules
    root = tmp_path / "leg"
    chain = T6.write_chain(root, ledger=[T6.ledger_entry("a"), T6.ledger_entry("b", index=1)])
    sched = dict(blocks=[dict(legs=[dict(invocations=[dict(names=["a", "b", "c"]), dict(names=["d", "e"])]),
                                    dict(invocations=[dict(names=["f", "g"])])])])
    (root / "schedule.json").write_text(json.dumps(sched))
    doc = json.loads(chain.read_text())
    chain.write_text(json.dumps(dict(doc, schedule_sha256=schedules.schedule_sha256(sched))))
    _, lines, _ = T6.run_watcher(tmp_path, driver, power=lambda: good(), steps=1, chain=chain)
    assert lines[0]["progress"] == dict(done=2, planned=7)
    (root / "watch.jsonl").unlink()
    driver2 = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    try:
        _, lines, _ = T6.run_watcher(tmp_path, driver2, power=lambda: good(), steps=1, chain=chain, extra=["--planned", "9"])
    finally:
        driver2.kill()
        driver2.wait()
    assert lines[0]["progress"] == dict(done=2, planned=9)


def test_p51_a_schedule_that_is_not_the_frozen_one_is_not_used(tmp_path, driver):
    root = tmp_path / "leg"
    chain = T6.write_chain(root, ledger=[T6.ledger_entry("a")])
    (root / "schedule.json").write_text(json.dumps(dict(blocks=[dict(legs=[dict(invocations=[dict(names=list("abcdef"))])])])))
    doc = json.loads(chain.read_text())
    chain.write_text(json.dumps(dict(doc, schedule_sha256="0" * 64)))                 # differs from the file
    _, lines, _ = T6.run_watcher(tmp_path, driver, power=lambda: good(), steps=1, chain=chain)
    assert lines[0]["progress"]["planned"] != 6


def test_p52_a_tick_carries_epoch_seconds_and_the_exit_line_has_no_verdict(tmp_path, driver):
    import time
    before = time.time()
    chain = T6.write_chain(tmp_path / "leg")
    out = Path(chain).parent / "watch.jsonl"
    stops = []

    def sleep(s):
        stops.append(s)
        driver.kill()
        driver.wait()
    W.main(["--chain-json", str(chain), "--driver-pid", str(driver.pid), "--out", str(out), "--interval", "0.01"],
           power=lambda: good(), sleep=sleep)
    lines = [json.loads(x) for x in out.read_text().splitlines()]
    assert all(isinstance(x["t"], float) and before - 1 <= x["t"] <= time.time() + 1 for x in lines)
    assert "exit_state" in lines[-1] and "speed_valid" not in lines[-1] and "speed_reason" not in lines[-1]
    assert W.speed_verdict(out)["valid"] is True


# ------------------------------------------------------------------------------------------------ 11. P67 the R3 stall is a real kill
def test_the_fake_probes_stall_is_a_real_kill_record(tmp_path, monkeypatch):
    from bench.tests.test_b2_s8c_chain import run_fake_probe
    rc, rows = run_fake_probe(tmp_path, monkeypatch, ["--inject-stall-item", "python/b", "--inject-stall-s", "30"])
    assert rc == 0
    by = {r["id"]: r for r in rows}
    b = by["python/b"]
    assert b["termination"]["killed"] and b["termination"]["reason"] == "stalled" and b["termination"]["in_flight_at_kill"] == 0
    assert b["gate"]["requests_completed_at_kill"] == b["gate"]["requests_completed"] and b["stop_reason"] == "stalled"
    for other in ("python/a", "python/c"):
        assert not by[other].get("termination") and by[other]["gate"].get("requests_completed_at_kill") is None


def test_the_stall_kill_item_is_reconciled_as_a_kill_boundary_record(tmp_path, monkeypatch):
    """The fake probe in P426 mode (item barrier, server log, worker counters) under the real `P426Hooks`: the injected stall
    item's record is `kill_boundary` and reconciled; its neighbours stay `completed`."""
    import threading
    import time
    from bench.tests import test_b2_s4_reconcile as T4
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "chains" / "c147"))
    import fake_probe as fp
    ops, hooks, out = T4.make_hooks(tmp_path, arm="OFF")
    metrics = tmp_path / "metrics.json"
    ops.worker_metrics = lambda: json.loads(metrics.read_text()) if metrics.exists() else dict(summary=dict(T4.BEFORE))
    metrics.write_text(json.dumps(dict(summary=dict(T4.BEFORE, in_flight=0, decode_s=0.0))))
    state = tmp_path / "fstate"
    state.mkdir()
    for k, v in dict(FAKE_PROBE_STATE=str(state), STACK_WORKDIR=str(tmp_path), FAKE_ITEM_S="0.01", FAKE_HB_S="0.01", FAKE_TICK_S="0.005",
                     FAKE_SERVER_LOG=str(ops.log), FAKE_METRICS_FILE=str(metrics)).items():
        monkeypatch.setenv(k, v)
    ack, cancel = tmp_path / "ack", tmp_path / "cancel"
    rows_out = tmp_path / "rows" / "x.jsonl"
    rows_out.parent.mkdir()
    threading.Timer(0.2, lambda: ack.write_text("")).start()                 # the chain's manifest acknowledgement
    items = ["a", "b", "c"]
    argv = ["--model", T4.MODEL, "--items", ",".join(items), "--lang", "python", "--seed-base", "1001", "--out", str(rows_out),
            "--scaffold", "opencode-v2-web-tg1", "--expect-items", ",".join(f"python/{i}" for i in items), "--a4-v2-receipt", "r",
            "--sampling-profile", "deployed", "--cancel-file", str(cancel), "--manifest-ack", str(ack),
            "--frozen-prompt-date", "Mon Jan 05 2026", "--evidence", "p426", "--inject-stall-item", "python/b", "--inject-stall-s", "30"]
    base = str(rows_out.with_suffix(""))
    cases, failures = {}, []

    def wait(path):
        end = time.time() + 30
        while not Path(path).exists():
            assert time.time() < end, f"the fake probe never wrote {path}"
            time.sleep(0.005)

    def chain_side():                                       # the chain's barrier answers (the probe runs on the main thread: signals)
        try:
            for k, name in enumerate(items):
                slot = f"0|A|{T4.MODEL}|s1|python|{name}"
                wait(f"{base}.item{k}.ready")
                assert hooks.before_attempt(slot, T4.ctx(None, k=k, slot=slot, item=name)).kind == "accept"
                Path(f"{base}.item{k}.go").write_text("")
                wait(f"{base}.item{k}.done")
                row = [json.loads(x) for x in rows_out.read_text().splitlines()][-1]
                d = hooks.after_attempt(slot, dict(id=f"python/{name}"), T4.ctx(row, k=k, slot=slot, item=name))
                rec = json.loads((out / "items" / f"{cr.slot_file(slot)}.json").read_text())
                cases[name] = (rec["case"], rec["verdict"], d.kind)
                Path(f"{base}.item{k}.continue").write_text("")
        except BaseException as exc:  # noqa: BLE001
            failures.append(exc)
            cancel.write_text("")                           # the probe leaves its barrier wait (a cancelled run), never hangs
    th = threading.Thread(target=chain_side, daemon=True)
    th.start()
    rc = fp.main(argv)
    th.join(30)
    assert not failures, failures
    assert rc == 0
    assert cases == {"a": ("completed", "reconciled", "accept"), "b": ("kill_boundary", "reconciled", "accept"),
                     "c": ("completed", "reconciled", "accept")}


# ------------------------------------------------------------------------------------------------ 12. s9 data boundary (§16.8, after 3f)
from bench import p426_harvest as H  # noqa: E402
from bench import p426_wave2 as w2  # noqa: E402
from bench.tests import test_b2_s8_wave2 as T8  # noqa: E402
from bench.tests import test_b2_s9_harvest as T9  # noqa: E402

world = T8.world                                           # the sequencer fixture (fake ops, fake clock)
OPERATOR = "op.erator@corp-mail.example"


def main_record(w, rel="s1/rows.manifest.json", **extra):
    p = w.root / rel
    p.write_text(json.dumps(dict(json.loads(p.read_text()), **extra)))


@pytest.mark.parametrize("address", ["maintainer@corp-mail.example.co", "someone@gmail.com", "a.b@sub.corp.io"])
def test_a_foreign_email_in_a_main_bound_file_quarantines_it_and_fails_the_harvest(tmp_path, address):
    w = T9.World(tmp_path)
    main_record(w, contact=address)
    with pytest.raises(H.HarvestError, match=r"rows\.manifest\.json") as exc:
        w.harvest(emails=(OPERATOR,))
    assert address not in str(exc.value)                                           # the address itself is never echoed
    T9.nothing_published(w)


@pytest.mark.parametrize("address", ["x@example.com", "x@example.net", "x@example.org", "x@mail.example.org", "x@host.example",
                                     "x@mail.test", "x@something.invalid"])
def test_the_rfc_2606_reserved_names_are_allowed_in_main_files(tmp_path, address):
    w = T9.World(tmp_path)
    main_record(w, contact=address)
    assert w.harvest(emails=(OPERATOR,))["state"] == "VALID"


def test_a_foreign_email_in_an_evidence_bound_file_still_goes_to_the_review_file(tmp_path):
    w = T9.World(tmp_path)
    T9.put(w.root / "RUNLOG.md", "the model wrote maintainer@corp-mail.example.co into a comment\n")
    doc = w.harvest(emails=(OPERATOR,))
    assert doc["review"]["emails_count"] == 1 and T9.entry(doc, "leg:RUNLOG.md")["destination"] == "evidence"


def test_a_valid_leg_without_watch_jsonl_fails_the_harvest(tmp_path):
    for state in ("VALID", "VALID_WITH_DNF"):
        w = T9.World(tmp_path / state, state=state, dnf=state == "VALID_WITH_DNF")
        (w.root / "watch.jsonl").unlink()
        with pytest.raises(H.HarvestError, match="watch.jsonl"):
            w.harvest(emails=(OPERATOR,))
        T9.nothing_published(w)


def test_log_bounds_not_finalized_say_so_and_not_that_they_record_problems(tmp_path):
    w = T9.World(tmp_path, log=True)
    bounds = json.loads((w.root / "log_bounds.json").read_text())
    for value in (False, None):
        (w.root / "log_bounds.json").write_text(json.dumps(dict(bounds, finalized=value)))
        with pytest.raises(H.HarvestError) as exc:
            w.harvest(worktree=w.wt, emails=(OPERATOR,))
        assert "not finalized" in str(exc.value) and "records problems" not in str(exc.value), value
    (w.root / "log_bounds.json").write_text(json.dumps(dict(bounds, problems=["x was replaced"])))
    with pytest.raises(H.HarvestError) as exc:
        w.harvest(worktree=w.wt, emails=(OPERATOR,))
    assert "records problems" in str(exc.value) and "not finalized" not in str(exc.value)


def test_an_empty_operator_email_set_is_refused_before_any_leg_with_rc_2(world, capsys):
    world.ops.operator_emails = lambda: []
    assert T8.go(world, "--through", "tg1-p426-off-pilot") == 2
    err = [ln for ln in capsys.readouterr().err.splitlines() if ln.startswith("REFUSED: ")]
    assert len(err) == 1 and "operator" in err[0] and "email" in err[0]
    assert not world.ops.names("launch")


def test_the_box_ops_refuse_when_the_operator_email_cannot_be_read(tmp_path, monkeypatch):
    import subprocess as sp
    from bench import p426_freeze as fz
    ops = w2.BoxSeqOps(tmp_path / "wd", main_root=tmp_path / "main", evidence_stage=tmp_path / "stage")
    for run in (lambda *a, **k: sp.CompletedProcess(a, 0, stdout="", stderr=""),                    # user.email unset: empty
                lambda *a, **k: sp.CompletedProcess(a, 1, stdout="", stderr="fatal"),               # a failing read
                lambda *a, **k: (_ for _ in ()).throw(OSError("no git"))):
        monkeypatch.setattr(w2.subprocess, "run", run)
        with pytest.raises(fz.Refusal, match="email"):
            ops.operator_emails()
    monkeypatch.setattr(w2.subprocess, "run", lambda *a, **k: sp.CompletedProcess(a, 0, stdout=f"{OPERATOR}\n", stderr=""))
    assert ops.operator_emails() == (OPERATOR,)


def test_the_sequencer_logs_the_harvests_refused_line_on_an_rc_4_stop(world):
    line = "REFUSED: quarantined leg:s1/rows.manifest.json: email"
    base = world.ops.harvest

    def failing(root, *, emails):
        return dict(base(root, emails=emails), rc=2, message=line)
    world.ops.harvest = failing
    assert T8.go(world, "--through", "tg1-p426-off-pilot") == 4
    log = (world.out / "sequence.log").read_text()
    assert line in log and "harvest of tg1-p426-off-pilot.a1 failed" in log


def test_the_box_harvest_returns_the_refused_or_error_line_and_nothing_else(tmp_path, monkeypatch):
    import subprocess as sp
    ops = w2.BoxSeqOps(tmp_path / "wd", main_root=tmp_path / "main", evidence_stage=tmp_path / "stage")
    err = "Traceback noise\nREFUSED: quarantined leg:x.json: email\nmore noise\n"
    monkeypatch.setattr(w2.subprocess, "run", lambda *a, **k: sp.CompletedProcess(a, 2, stdout="stdout noise", stderr=err))
    res = ops.harvest(tmp_path / "wd" / "tg1-p426-off-pilot.a1", emails=(OPERATOR,))
    assert res["rc"] == 2 and res["message"] == "REFUSED: quarantined leg:x.json: email"
    monkeypatch.setattr(w2.subprocess, "run", lambda *a, **k: sp.CompletedProcess(a, 1, stdout="", stderr="ERROR: harvest I/O failure (OSError)\n"))
    assert ops.harvest(tmp_path / "wd" / "tg1-p426-off-pilot.a1", emails=(OPERATOR,))["message"].startswith("ERROR: harvest I/O failure")


def test_p532_the_work_queue_tests_leave_no_control_dir_in_the_tree(tmp_path, monkeypatch):
    """The in-repo `benchmark/control` (the default when STACK_WORKDIR is unset) must not appear by running the queue tests."""
    from bench import paths
    control = paths.repo_root() / "benchmark" / "control"
    if control.exists():
        if any(control.iterdir()):
            pytest.skip("benchmark/control holds operator files")
        control.rmdir()                                      # debris of an earlier run
    env = {k: v for k, v in __import__("os").environ.items() if k != "STACK_WORKDIR"}
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", str(paths.repo_root() / "benchmark"),
                        str(Path(__file__).with_name("test_work_queue.py")), "-k", "not watcher and not default_spawn"],
                       cwd=str(paths.repo_root() / "benchmark"), env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-800:]
    assert not control.exists(), "test_work_queue.py created the in-repo benchmark/control"


def test_p52_a_journal_whose_ticks_have_no_epoch_t_cannot_prove_its_gaps(tmp_path):
    path = T6.journal(tmp_path, [{}, {}, {}])
    lines = [json.loads(x) for x in path.read_text().splitlines()]
    for x in lines[:-1]:
        x.pop("t")
        x["at"] = "2026-10-27T00:00:00+00:00"                # an ISO `at` is no longer a fallback for `t`
    path.write_text("".join(json.dumps(x) + "\n" for x in lines))
    v = W.speed_verdict(path)
    assert v["valid"] is False and "tick times" in v["reason"]


# ------------------------------------------------------------------------------------------------ p426_dnf.arm is the predictor arm
@pytest.mark.parametrize("predictor, arm", [("off", "off"), ("mtp", "on")])
def test_the_p426_dnf_record_carries_the_predictor_arm_not_the_scaffold_label(tmp_path, predictor, arm):
    from bench.tests.test_b2_s3_core import bare, incomplete
    c = bare(tmp_path)
    c.a = SimpleNamespace(predictor=predictor)
    incomplete(c, tmp_path)
    d, = c.p426_dnf
    assert (d["pick"], d["attempt"], d["session"], d["language"], d["seed"], d["arm"]) == ("M", 1, "s1", "python", 1001, arm)
    side, = (tmp_path / "s1" / "p426_dnf").iterdir()
    assert json.loads(side.read_text())["arm"] == arm


# ------------------------------------------------------------------------------------------------ p426_dnf.invocation is an index
def test_the_p426_dnf_record_names_its_invocation_by_index_and_load_gen_as_int(tmp_path, monkeypatch):
    rc, cj, env = p426_leg(tmp_path, monkeypatch, {"B2_ABORTS": json.dumps({PILOT[1]: "boundary"})})
    assert rc == 0, "\n".join(env["lines"][-6:])
    d, = cj["p426_dnf"]
    assert type(d["invocation"]) is int and type(d["load_gen"]) is int
    inv = cj["progress"]["invocations"][d["invocation"]]
    assert inv["load_gen"] == d["load_gen"] and d["slot"] in inv["expected_slots"]
    assert d["invocation_file"] == inv["file"]                         # the rows path stays, under its own key
    side, = list(Path(env["out"]).glob("*/p426_dnf/*.json"))
    assert json.loads(side.read_text())["invocation"] == d["invocation"]


# ------------------------------------------------------------------------------------------------ p426_dnf is an immutable record
def test_the_p426_dnf_record_and_its_sidecar_are_self_hashed_and_the_sidecar_is_exclusive(tmp_path, monkeypatch):
    from bench import p426_hooks as ph
    rc, cj, env = p426_leg(tmp_path, monkeypatch, {"B2_ABORTS": json.dumps({PILOT[1]: "boundary"})})
    assert rc == 0, "\n".join(env["lines"][-6:])
    d, = cj["p426_dnf"]
    assert ph.sealed_ok(d) and d["sha256"] == S.self_hashed(d)["sha256"]
    side, = list(Path(env["out"]).glob("*/p426_dnf/*.json"))
    assert json.loads(side.read_text()) == d
    assert side.name == cr.slot_file(d["slot"]) + ".json"
    with pytest.raises(FileExistsError):                              # exclusive-created: never overwritten
        ph.write_exclusive(side, d)
    # the other immutable records of this leg carry a correct self-hash
    root = Path(env["out"])
    recs = [root / "receipt.json", *sorted((root / "items").glob("*.json"))]
    assert len(recs) > 3 and all(ph.sealed_ok(json.loads(p.read_text())) for p in recs), [p.name for p in recs if not ph.sealed_ok(json.loads(p.read_text()))]


def test_the_p426_dnf_self_hash_is_over_the_portable_form(tmp_path, monkeypatch):
    rc, cj, env = p426_leg(tmp_path, monkeypatch, {"B2_ABORTS": json.dumps({PILOT[1]: "boundary"})})
    text = json.dumps(cj["p426_dnf"])
    assert str(tmp_path) not in text
