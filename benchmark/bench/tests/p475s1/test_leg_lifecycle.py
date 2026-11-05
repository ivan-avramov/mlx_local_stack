"""`p475_kv.run_leg` after the pre-check (contract "Leg lifecycle" steps 2-7): router env (R2), worker argv / KV line / predictor
before the driver (R3, R5), the driver's session and teardown order (R6), proven teardown (R7), the watcher's interval and speed
problems (R9-R12), the receipt, arm identity at exit (R1)."""
import json
import signal

import pytest

from . import helpers as H
from .fakes import ARMS, FULL_GRID, KV_NAMES, PICK, kv_line, leg_name, worker_argv

LEG = leg_name("AF8", 1)


@pytest.fixture
def w(tmp_path, monkeypatch):
    w = H.world(tmp_path, monkeypatch)
    H.ready(w)
    return w


def val(argv, flag):
    return argv[argv.index(flag) + 1]


def epoch_of(x):
    from bench.p426_leg import stamp_epoch
    return stamp_epoch(x)


def invalid(w, arm="AF8", **kw):
    rec = H.run_leg(w, arm, **kw)
    assert rec["verdict"] == "INVALID", rec
    assert rec["problems"]
    return rec


# ------------------------------------------------------------------------------------------- the clean leg
def test_a_clean_leg_is_valid_and_speed_valid(w):
    # class: exercises new behaviour
    rec = H.run_leg(w, "AF8")
    assert rec["verdict"] == "VALID" and rec["speed_valid"] is True
    assert rec["problems"] == [] and rec["speed_problems"] == []


def test_the_receipt_is_on_disk_at_the_canonical_path_and_matches(w):
    # class: exercises new behaviour
    rec = H.run_leg(w, "AF8")
    disk = H.read_receipt(w, LEG)
    assert disk["verdict"] == rec["verdict"] == "VALID" and disk["speed_valid"] is True
    assert list((w.wd / "p475/legs" / LEG).glob("receipt.refused-*.json")) == []


def test_the_receipt_records_identity_argv_kv_line_and_preflight(w):
    # class: exercises new behaviour (contract step 7; field names are not fixed, so by content)
    H.run_leg(w, "AF8")
    text = H.receipt_path(w, LEG).read_text()
    head = w.arm_commit["AF8"]
    assert text.count(head[:12]) >= 2, "the arm identity is recorded at entry AND at exit"
    assert "--kv-bits" in text and "uniform" in text
    assert "kv_group_size" in text
    assert "preflight" in text.lower()
    assert str(w.stacks[0].worker["pid"]) in text


@pytest.mark.parametrize("arm", ARMS)
def test_the_router_is_built_from_the_arms_worktree_and_registry_with_its_predictor(w, arm):
    # class: exercises new behaviour (step 2)
    H.run_leg(w, arm)
    (_, kw), = [e for e in w.events if e[0] == "stack"]
    assert kw["wt"] == str(w.wt(arm))
    assert kw["registry"] == str(w.wt(arm) / "main_models.yaml")
    assert kw["predictor"] == ("off" if arm == "TQ4-OFF" else "mtp")


# ------------------------------------------------------------------------------------------- R2: environment stripped
@pytest.fixture
def dirty_env(monkeypatch):
    for n in KV_NAMES:
        monkeypatch.setenv(n, "1")


def test_no_kv_or_tq_name_reaches_the_driver(w, dirty_env):
    # class: reproduces a failure the contract fixes (R2)
    H.run_leg(w, "N16")
    env = w.spawns[0].env
    assert [n for n in env if n in KV_NAMES or n.startswith(("KV_", "TQ_"))] == []


def test_stripping_does_not_remove_unrelated_variables(w, dirty_env, monkeypatch):
    # class: preserves an invariant (only the KV / TQ names go)
    monkeypatch.setenv("HF_HOME", "/somewhere/hf")
    H.run_leg(w, "N16")
    assert w.spawns[0].env.get("HF_HOME") == "/somewhere/hf"


def test_a_stack_defined_name_is_stripped_from_the_driver(w, monkeypatch):
    # class: exercises new behaviour (R2: p426_secrets.STACK_DEFINED_KV_TQ_NAMES, e.g. TQ_PREFILL_IMPL / TQ_FUSED_PREFILL)
    from bench import p426_secrets
    for n in p426_secrets.STACK_DEFINED_KV_TQ_NAMES:
        monkeypatch.setenv(n, "x")
    H.run_leg(w, "N16")
    assert not (set(w.spawns[0].env) & set(p426_secrets.STACK_DEFINED_KV_TQ_NAMES))


def test_a_name_the_router_handle_hands_out_is_stripped_from_the_driver(w):
    # class: exercises new behaviour (R2: the driver env is the router's env minus every KV / TQ name)
    w.router_env_extra = dict([("KV_BITS", "8"), ("TQ_KV_QUANT_MODE", "prod"), ("KV_SOMETHING_NEW", "1")])
    H.run_leg(w, "N16")
    assert [n for n in w.spawns[0].env if n.startswith(("KV_", "TQ_"))] == []
    assert w.spawns[0].env["MLX_SERVE_CONFIG"] == str(w.wt("N16") / "main_models.yaml")


def test_realops_stack_hands_out_a_router_environment_without_kv_or_tq_names(tmp_path, monkeypatch):
    # class: exercises new behaviour (P1: `RealOps.stack` builds the stripped router environment; no live box needed)
    from bench import p426_secrets
    wd, repo = tmp_path / "wd", tmp_path / "repo"
    wt = wd / "worktrees" / "p475-u4-n16"
    wt.mkdir(parents=True)
    repo.mkdir()
    (wt / ".env").write_text("KV_BITS=4\nTQ_PREFILL_IMPL=x\nHF_HOME=/hf\n")             # a KV name in the worktree's own .env
    for n in list(p426_secrets.STACK_DEFINED_KV_TQ_NAMES) + ["KV_SOMETHING_NEW", "TQ_SOMETHING_NEW"]:
        monkeypatch.setenv(n, "1")
    monkeypatch.setenv("OTHER_VAR", "keep")
    handle = H.K().RealOps(wd, repo).stack(wt, wt / "main_models.yaml", "mtp")
    env = handle.env_base()
    assert [n for n in env if n.startswith(("KV_", "TQ_")) or n in p426_secrets.STACK_DEFINED_KV_TQ_NAMES] == []
    assert env.get("OTHER_VAR") == "keep" and env.get("HF_HOME") == "/hf"
    assert env["MLX_SERVE_CONFIG"] == str(wt / "main_models.yaml")


@pytest.mark.parametrize("name", ["KV_BITS", "KV_GROUP_SIZE", "TQ_KV_QUANT_MODE", "TQ_PREFILL_IMPL", "KV_SOMETHING_NEW",
                                  "TQ_SOMETHING_NEW"])
def test_a_kv_name_in_the_workers_environment_is_invalid_before_the_driver(w, name):
    # class: exercises new behaviour (step 3 / P1: a worker whose environment carries a stripped name is INVALID before the driver)
    w.worker_env_extra = dict([(name, "8")])
    invalid(w, "N16")
    assert "spawn" not in w.names() and "stop_stack" in w.names()


# ------------------------------------------------------------------------------------------- R3 / R5: argv, KV line, predictor
def test_the_expected_argv_is_asked_for_the_arm_registry_and_the_pick(w):
    # class: exercises new behaviour (step 3)
    H.run_leg(w, "AF8")
    (_, kw), = [e for e in w.events if e[0] == "expected_worker_argv"]
    assert kw["registry"] == str(w.wt("AF8") / "main_models.yaml") and kw["model"] == PICK


def _tweaks():
    return {
        "extra_flag": lambda a: a + ["--kv-group-size", "32"],
        "wrong_bits": lambda a: [("4" if (i and a[i - 1] == "--kv-bits") else t) for i, t in enumerate(a)],
        "scheme_dropped": lambda a: [t for i, t in enumerate(a) if t != "--kv-quant-scheme" and not (i and a[i - 1] == "--kv-quant-scheme")],
        "scheme_flipped": lambda a: [("turboquant" if (i and a[i - 1] == "--kv-quant-scheme") else t) for i, t in enumerate(a)],
        "draft_dropped": lambda a: a[:a.index("--draft-kind")],
        "reordered": lambda a: a[:1] + a[3:5] + a[1:3] + a[5:],
        "extra_prefill": lambda a: a + ["--prefill-step-size", "2048"],
    }


@pytest.mark.parametrize("name", list(_tweaks()))
def test_a_worker_argv_that_differs_from_the_builders_in_any_way_is_invalid_before_the_driver(w, name):
    # class: reproduces a failure the contract fixes (R3: every KV flag; R5: before the driver)
    w.argv_tweak = _tweaks()[name]
    invalid(w, "AF8")
    assert "spawn" not in w.names() and "start_watch" not in w.names()
    assert "stop_stack" in w.names()


def test_the_kv_group_size_flag_is_covered_by_the_argv_check(w):
    # class: reproduces a failure the contract fixes (R3: `--kv-group-size` incl.)
    w.argv_group = 32
    invalid(w, "TQ4")
    assert "spawn" not in w.names()


def test_the_off_arm_must_not_carry_a_draft_flag(w):
    # class: exercises new behaviour (predictor OFF: no draft flag)
    w.argv_tweak = lambda a: a + ["--draft-kind", "mtp"]
    invalid(w, "TQ4-OFF")
    assert "spawn" not in w.names()


@pytest.mark.parametrize("text", ["", kv_line("TQ4"), kv_line("AF8", scheme="turboquant"), kv_line("AF8", bits=4.0),
                                  kv_line("AF8", group=32), kv_line("AF8", start=4096),
                                  kv_line("AF8", extra={"kv_key_bits": 8.0}),
                                  "KV cache resolved: kv_bits=8.0"],
                         ids=["no_line", "tq4_line", "wrong_scheme", "wrong_bits", "group32", "start4096", "split_key_bits",
                              "truncated"])
def test_a_kv_line_that_disagrees_or_is_absent_is_invalid_before_the_driver(w, text):
    # class: exercises new behaviour (R2 / R5)
    w.kv_text = text
    invalid(w, "AF8")
    assert "spawn" not in w.names() and "stop_stack" in w.names()


def test_only_the_log_text_written_since_the_load_counts(w):
    # class: reproduces a failure the contract fixes (the worker log is append-only across legs: a stale RIGHT line must not
    # certify a load that wrote nothing, a stale WRONG line must not condemn one that wrote the right line)
    log = w.wt("AF8") / "logs" / "mlx_vlm.log"
    log.write_text(kv_line("AF8") + "\n")                       # a previous leg's correct line
    w.kv_text = ""                                               # this load logs no line at all
    invalid(w, "AF8")


def test_a_stale_wrong_line_does_not_condemn_a_load_that_logged_the_right_one(w):
    # class: reproduces a failure the contract fixes
    log = w.wt("AF8") / "logs" / "mlx_vlm.log"
    log.write_text(kv_line("AF4") + "\n")
    assert H.run_leg(w, "AF8")["verdict"] == "VALID"


def test_the_last_kv_line_since_the_load_decides(w):
    # class: exercises new behaviour (R22: the LAST line; a wrong line followed by the right one is the live state)
    w.kv_text = kv_line("AF4") + "\n" + kv_line("AF8")
    assert H.run_leg(w, "AF8")["verdict"] == "VALID"


def test_an_n16_arm_with_a_native_kv_line_is_valid(w):
    # class: exercises new behaviour
    assert H.run_leg(w, "N16")["verdict"] == "VALID"


def test_the_checks_all_precede_the_driver_in_order(w):
    # class: exercises new behaviour (R5)
    H.run_leg(w, "AF8")
    n = w.names()
    assert n.index("expected_worker_argv") < n.index("spawn")
    assert n.index("load") < n.index("spawn")
    assert n.index("start_router") < n.index("load")


def test_a_load_failure_is_invalid_and_tears_down(w):
    # class: exercises new behaviour
    w.load_raises = True
    invalid(w, "AF8")
    assert "spawn" not in w.names() and "stop_stack" in w.names()


def test_a_router_start_failure_is_invalid_and_runs_no_driver(w):
    # class: exercises new behaviour
    w.start_router_raises = True
    invalid(w, "AF8")
    assert "spawn" not in w.names() and "load" not in w.names()


# ------------------------------------------------------------------------------------------- driver launch
def test_the_driver_command_env_cwd_and_session(w):
    # class: exercises new behaviour (step 4)
    H.run_leg(w, "AF8")
    sp = w.spawns[0]
    a = sp.argv
    assert a[0] == str(w.wt("AF8") / ".venv-bench/bin/python")
    assert "run_capacity" in " ".join(a)
    assert val(a, "--model") == PICK and val(a, "--sampling-profile") == "deployed" and val(a, "--seed") == "0"
    assert val(a, "--grid") == ",".join(map(str, FULL_GRID))
    assert val(a, "--out-tag") == f"p475-{LEG}" and "--p475-strict" in a
    assert [float(x) for x in val(a, "--expected-rung-seconds").split(",")] == [60.0, 400.0, 800.0, 1500.0]
    assert sp.cwd == str(w.wt("AF8") / "benchmark")
    assert sp.session is True
    assert sp.env["MLX_SERVE_CONFIG"] == str(w.wt("AF8") / "main_models.yaml")
    assert sp.env["MLX_BENCH_SESSION_PREFIX"] == f"p475-{LEG}"


def test_a_smoke_leg_runs_only_the_8192_rung(w):
    # class: exercises new behaviour
    rec = H.run_leg(w, "N16", smoke=True)
    assert rec["verdict"] == "VALID"
    assert val(w.spawns[0].argv, "--grid") == "8192"
    assert val(w.spawns[0].argv, "--out-tag") == "p475-u4-n16-smoke.a1"


# ------------------------------------------------------------------------------------------- R6: driver lifecycle
def test_the_watcher_starts_right_after_the_driver_spawns(w):
    # class: exercises new behaviour (step 5)
    H.run_leg(w, "AF8")
    n = w.names()
    assert n.index("spawn") < n.index("start_watch") < n.index("wait")
    assert n.index("spawn") + 1 == n.index("start_watch")


def test_the_order_on_a_normal_exit_is_driver_then_watcher_then_stack(w):
    # class: exercises new behaviour (R6)
    H.run_leg(w, "AF8")
    n = w.names()
    assert n.index("wait") < n.index("stop_watch") < n.index("stop_stack")


def test_a_hung_driver_is_signalled_after_three_times_the_expected_durations(w):
    # class: exercises new behaviour (step 4: timeout = expected durations x 3)
    w.driver_duration = float("inf")
    invalid(w, "AF8")
    spawn_t = next(k["t"] for e, k in w.events if e == "spawn")
    first = next(k["t"] for e, k in w.events if e == "signal_group")
    assert 3 * 2760.0 <= first - spawn_t <= 3 * 2760.0 + 1200.0


def test_a_hung_driver_is_terminated_then_gone_before_watcher_stop_and_teardown(w):
    # class: exercises new behaviour (R6)
    w.driver_duration = float("inf")
    invalid(w, "AF8")
    n = w.names()
    assert w.drivers[0].signals == ["SIGTERM"]
    assert n.index("signal_group") < n.index("stop_watch") < n.index("stop_stack")
    assert not H.FakeOps(w).proc_alive(w.drivers[0].pid, w.drivers[0].ct)


def test_a_driver_that_ignores_sigterm_is_escalated_to_sigkill(w):
    # class: exercises new behaviour (R6: terminated, ESCALATED, reaped)
    w.driver_duration = float("inf")
    w.driver_ignores_term = True
    invalid(w, "AF8")
    sigs = w.drivers[0].signals
    assert sigs[0] == "SIGTERM" and "SIGKILL" in sigs and sigs.index("SIGTERM") < sigs.index("SIGKILL")
    n = w.names()
    assert max(i for i, x in enumerate(n) if x == "signal_group") < n.index("stop_watch")


def test_a_driver_nothing_can_kill_is_invalid_and_never_waited_on_forever(w):
    # class: exercises new behaviour (R6: verified gone, bounded; the fake raises on a runaway wait)
    w.driver_duration = float("inf")
    w.driver_unkillable = True
    rec = invalid(w, "AF8")
    assert "SIGKILL" in w.drivers[0].signals
    assert rec["speed_valid"] is False


def test_a_nonzero_driver_exit_is_invalid_even_with_clean_rows(w):
    # class: exercises new behaviour
    w.driver_rc = 1
    invalid(w, "AF8")
    n = w.names()
    assert n.index("wait") < n.index("stop_watch") < n.index("stop_stack")


def test_a_driver_that_cannot_be_spawned_is_invalid_and_the_stack_is_torn_down(w):
    # class: exercises new behaviour (R6 / R7: any exit path)
    w.spawn_raises = True
    invalid(w, "AF8")
    assert "stop_stack" in w.names() and w.procs == {} and w.listener == {}


def test_an_interrupt_during_the_driver_wait_tears_everything_down_and_is_receipted(w):
    # class: exercises new behaviour (R6 / R7: "on timeout or any exit path"; the interrupt is re-raised AFTER the receipt)
    fired = []

    def boom():
        if not fired:
            fired.append(1)
            raise KeyboardInterrupt
    w.wait_hook = boom
    with pytest.raises(KeyboardInterrupt):
        H.run_leg(w, "AF8")
    n = w.names()
    assert w.drivers[0].signals and n.index("signal_group") < n.index("stop_stack")
    assert w.procs == {} and w.listener == {}
    assert H.read_receipt(w, LEG)["verdict"] == "INVALID"
    assert w.names().count("lease_enter") == w.names().count("lease_exit") == 1


# ------------------------------------------------------------------------------------------- rows: R21 end to end
def test_a_bad_rung_makes_the_leg_invalid_and_the_leg_is_still_harvested(w):
    # class: exercises new behaviour (INVALID legs are harvested too)
    w.row_mutate = lambda row, i, arm, n: dict(row, finish_reason="stop") if i == 1 else row
    invalid(w, "AF8")
    assert H.dossier(w, LEG).is_dir()


@pytest.mark.parametrize("name,mut", [
    ("cache_n_1", lambda r, i, a, n: dict(r, cache_n=1)),
    ("short_completion", lambda r, i, a, n: dict(r, completion_tokens=255, predicted_n=255)),
    ("pps_off", lambda r, i, a, n: dict(r, prompt_per_second=r["prompt_per_second"] * 1.05)),
    ("no_draft", lambda r, i, a, n: {k: v for k, v in r.items() if not k.startswith("draft_")}),
    ("accepted_gt_n", lambda r, i, a, n: dict(r, draft_n_accepted=r["draft_n"] + 1)),
    ("foreign_session_prefix", lambda r, i, a, n: dict(r, session_id="other-prefix-0001")),
    ("session_none", lambda r, i, a, n: dict(r, session_id=None)),
])
def test_each_rung_defect_is_invalid(w, name, mut):
    # class: exercises new behaviour
    w.row_mutate = mut
    invalid(w, "AF8")


def test_a_cache_n_of_float_zero_stays_valid(w):
    # class: reproduces a failure the contract fixes (r2-glm-6)
    w.row_mutate = lambda r, i, a, n: dict(r, cache_n=0.0)
    assert H.run_leg(w, "AF8")["verdict"] == "VALID"


def test_duplicate_session_ids_across_rows_are_invalid(w):
    # class: exercises new behaviour
    w.row_mutate = lambda r, i, a, n: dict(r, session_id=f"p475-{LEG}-same")
    invalid(w, "AF8")


def test_an_error_row_is_invalid(w):
    # class: exercises new behaviour (a rung that errored is recorded unscored; the leg cannot be VALID)
    w.row_mutate = lambda r, i, a, n: dict(r, execution_status="error", error="boom") if i == 3 else r
    invalid(w, "AF8")


def test_the_off_arm_with_a_drafter_row_is_invalid(w):
    # class: exercises new behaviour (predictor-OFF reference: every drafter key absent or null)
    w.row_mutate = lambda r, i, a, n: dict(r, draft_kind="mtp", draft_n=10, draft_n_accepted=5, draft_rounds=3)
    invalid(w, "TQ4-OFF")


def test_the_off_arm_with_null_drafter_keys_is_valid(w):
    # class: exercises new behaviour
    w.row_mutate = lambda r, i, a, n: dict(r, draft_kind=None, draft_n=None, draft_n_accepted=None, draft_rounds=None)
    assert H.run_leg(w, "TQ4-OFF")["verdict"] == "VALID"


# ------------------------------------------------------------------------------------------- R7: proven teardown
def test_teardown_asks_the_stack_to_stop_and_checks_unload(w):
    # class: exercises new behaviour
    H.run_leg(w, "AF8")
    assert "stop_stack" in w.names()


def test_an_unload_refusal_is_invalid(w):
    # class: exercises new behaviour (R7: an unload failure propagates)
    w.unload_ok_value = False
    invalid(w, "AF8")


@pytest.mark.parametrize("who", ["worker", "listener", "router", "wrapper"])
def test_a_survivor_after_the_stop_is_invalid(w, who):
    # class: reproduces a failure the contract fixes (R7: worker, :8000 listener, router, wrapper all verified gone)
    w.survivors = (who,)
    invalid(w, "AF8")


def test_a_clean_teardown_leaves_nothing_alive(w):
    # class: exercises new behaviour
    H.run_leg(w, "AF8")
    assert w.procs == {} and w.listener == {}


# ------------------------------------------------------------------------------------------- R1 at exit
def test_arm_identity_is_read_again_at_exit_and_a_dirty_tree_is_invalid(w):
    # class: exercises new behaviour (R1: entry AND exit)
    w.ws_hook = lambda arm: w.arm_clean.__setitem__(arm, False) if "spawn" in w.names() else None
    invalid(w, "AF8")


def test_a_head_that_moved_during_the_leg_is_invalid(w):
    # class: exercises new behaviour (R1)
    w.ws_hook = lambda arm: w.arm_head.__setitem__(arm, "9" * 40) if "spawn" in w.names() else None
    invalid(w, "AF8")


# ------------------------------------------------------------------------------------------- watcher: argv (R9, R12)
def test_the_watcher_is_bound_to_the_driver_pid_and_create_time(w):
    # class: exercises new behaviour (R12)
    H.run_leg(w, "AF8")
    argv = w.watches[0]["argv"]
    sim = w.drivers[0]
    assert int(val(argv, "--driver-pid")) == sim.pid
    assert float(val(argv, "--driver-create-time")) == sim.ct


def test_the_watcher_gets_the_ladder_rows_and_the_expected_durations(w):
    # class: exercises new behaviour (R9)
    H.run_leg(w, "AF8")
    argv = w.watches[0]["argv"]
    assert val(argv, "--capacity-rows").endswith(f"capacity_ladder.p475-{LEG}.jsonl")
    assert [float(x) for x in val(argv, "--expected-rung-seconds").split(",")] == [60.0, 400.0, 800.0, 1500.0]
    assert "--out" in argv


# ------------------------------------------------------------------------------------------- R10 / R11: speed problems
@pytest.mark.parametrize("mode", ["missing", "no_exit", "early_exit", "power_fail", "few_ticks", "gap"])
def test_a_watcher_or_power_failure_is_a_speed_problem_never_invalid(w, mode):
    # class: reproduces a failure the contract fixes (R11: SPEED_INVALID -> replacement, the quality stands)
    w.watch_mode = mode
    rec = H.run_leg(w, "AF8")
    assert rec["verdict"] == "VALID" and rec["problems"] == []
    assert rec["speed_valid"] is False and rec["speed_problems"]


def test_exactly_the_required_tick_count_passes(w):
    # class: exercises new behaviour (R10: ticks >= (driver interval - 600) // 300 = 7 for a 2760 s driver)
    w.watch_mode = "ticks:7"
    rec = H.run_leg(w, "AF8")
    assert rec["speed_valid"] is True, rec["speed_problems"]


def test_one_tick_short_of_the_required_count_fails(w):
    # class: exercises new behaviour (R10)
    w.watch_mode = "ticks:6"
    rec = H.run_leg(w, "AF8")
    assert rec["speed_valid"] is False and rec["speed_problems"]


def test_pmset_history_is_read_over_exactly_the_driver_interval(w):
    # class: exercises new behaviour (R10)
    H.run_leg(w, "AF8")
    (_, kw), = [e for e in w.events if e[0] == "pmset_log"]
    sim = w.drivers[0]
    assert epoch_of(kw["start"]) == pytest.approx(sim.spawn_epoch, abs=2.0)
    assert epoch_of(kw["end"]) == pytest.approx(sim.end_epoch, abs=2.0)


def test_a_battery_interval_inside_the_driver_run_is_a_speed_problem(w):
    # class: exercises new behaviour (R10)
    w.battery_events = [(w.epoch0 + 1000, "Batt"), (w.epoch0 + 1100, "AC")]
    rec = H.run_leg(w, "AF8")
    assert rec["verdict"] == "VALID" and rec["speed_valid"] is False and rec["speed_problems"]


def test_a_battery_interval_before_the_launch_does_not_count(w):
    # class: exercises new behaviour (R10: reconciled over exactly that interval)
    w.battery_events = [(w.epoch0 - 5000, "Batt"), (w.epoch0 - 4000, "AC")]
    assert H.run_leg(w, "AF8")["speed_valid"] is True


def test_a_battery_interval_after_the_driver_exit_does_not_count(w):
    # class: exercises new behaviour (R10)
    w.battery_events = [(w.epoch0 + 4000, "Batt"), (w.epoch0 + 4100, "AC")]
    assert H.run_leg(w, "AF8")["speed_valid"] is True


def test_an_unreadable_power_history_is_a_speed_problem_not_invalid(w):
    # class: exercises new behaviour (an unreadable pmset log never reads as "no outage")
    w.pmset_raises = True
    rec = H.run_leg(w, "AF8")
    assert rec["verdict"] == "VALID" and rec["speed_valid"] is False


def test_the_receipt_keeps_speed_problems_apart_from_problems(w):
    # class: exercises new behaviour
    w.watch_mode = "power_fail"
    H.run_leg(w, "AF8")
    disk = H.read_receipt(w, LEG)
    assert disk["problems"] == [] and disk["speed_problems"] and disk["speed_valid"] is False


# ------------------------------------------------------------------------------------------- R8 / R17 / R18: harvest + receipt files
def test_the_leg_end_is_written_after_the_dossier_is_final(w):
    # class: exercises new behaviour (R8: the 600 s idle starts after harvest completes)
    H.run_leg(w, "AF8")
    written = float((w.wd / "p475" / "LAST_LEG_END").read_text())
    snap = next(s for v, s in w.now_snaps if v == pytest.approx(written, abs=1e-6))
    dossier_exists, stage_exists = snap
    assert dossier_exists and not stage_exists


def test_the_leg_end_is_not_written_by_a_leg_that_never_started(w):
    # class: exercises new behaviour
    before = (w.wd / "p475" / "LAST_LEG_END").read_text()
    w.busy_list = ["1 mlx_vlm.server"]
    H.run_leg(w, "AF8")
    assert (w.wd / "p475" / "LAST_LEG_END").read_text() == before


def test_a_second_write_goes_beside_the_canonical_receipt_and_never_replaces_it(w):
    # class: exercises new behaviour (R17)
    H.run_leg(w, "AF8")
    canonical = H.receipt_path(w, LEG)
    first = canonical.read_bytes()
    again = H.run_leg(w, "AF8")                                  # same leg name: destinations exist -> NOT_STARTED
    assert again["verdict"] == "NOT_STARTED"
    assert canonical.read_bytes() == first
    variants = list(canonical.parent.glob("receipt.refused-*.json"))
    assert len(variants) == 1
    assert json.loads(variants[0].read_text())["verdict"] == "NOT_STARTED"
