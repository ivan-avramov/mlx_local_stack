"""P475 stage 1 (implementer tests): `run_leg` — pre-check (R1, R4, R8), router + post-load checks (R2, R3, R5), driver (R6),
watcher (R9–R12), teardown (R7), receipt (R17), harvest (R18)."""
from __future__ import annotations

import json
import signal

import pytest

from bench import p475_kv as K
from bench.tests.test_p475_impl_support import FakeOps, make_cfg


@pytest.fixture
def world(tmp_path):
    ops, cfg = FakeOps(tmp_path), make_cfg(tmp_path)
    ops.add_all(cfg)
    return ops, cfg


def leg(ops, cfg, arm="AF8", block=1, n=1):
    name = K.leg_name(arm, block, n)
    return name, K.run_leg(name, arm, ops, cfg)


def started(ops):
    return any(c[0] == "stack" for c in ops.calls)


# ------------------------------------------------------------------------------------------------ the VALID path
def test_a_valid_leg_end_to_end(world):
    ops, cfg = world
    name, r = leg(ops, cfg)
    assert r["verdict"] == "VALID" and r["speed_valid"] is True, (r["problems"], r["speed_problems"])
    assert r["_harvest"] == "harvested"
    on_disk = json.loads(cfg.receipt_path(name).read_text())
    assert on_disk["verdict"] == "VALID" and on_disk["kv_line"]["kv_quant_scheme"] == "uniform"
    assert on_disk["worker_argv"] == on_disk["expected_worker_argv"] and "--kv-bits" in on_disk["worker_argv"]
    assert on_disk["identity_entry"] == on_disk["identity_exit"]
    assert on_disk["power"]["entry"]["watts"] == 140 and on_disk["power"]["exit"]["watts"] == 140
    assert on_disk["driver"]["launch"] < on_disk["driver"]["exit"] and on_disk["watcher"]["valid"] is True
    # the driver: the arm's bench venv, its benchmark/ cwd, own session, strict argv, KV names stripped
    sp = ops.spawned[0]
    wt = cfg.worktree("AF8")
    assert sp["argv"][:3] == [str(wt / ".venv-bench/bin/python"), "-m", "bench.run_capacity"]
    assert sp["cwd"] == str(wt / "benchmark") and sp["session"] is True
    for flag, value in (("--grid", "8192,131072,196608,260096"), ("--sampling-profile", "deployed"), ("--seed", "0"),
                        ("--out-tag", f"p475-{name}"), ("--model", K.PICK)):
        assert sp["argv"][sp["argv"].index(flag) + 1] == value
    assert "--p475-strict" in sp["argv"] and "--expected-rung-seconds" in sp["argv"]
    assert sp["env"]["MLX_SERVE_CONFIG"] == str(cfg.registry("AF8")) and sp["env"]["MLX_BENCH_SESSION_PREFIX"] == f"p475-{name}"
    assert not K.kv_env_names(sp["env"])
    # the watcher: bound to the driver by (pid, create_time), started after the spawn, stopped before the teardown
    order = [c[0] for c in ops.calls if c[0] in ("start_watch", "stop_watch", "stop_stack")]
    assert order == ["start_watch", "stop_watch", "stop_stack"]
    wargv = next(c[1] for c in ops.calls if c[0] == "start_watch")
    assert wargv[wargv.index("--driver-pid") + 1] == "301" and float(wargv[wargv.index("--driver-create-time") + 1]) == 4.0
    assert "--capacity-rows" in wargv and "--expected-rung-seconds" in wargv
    # the router: from the arm worktree with its own registry, predictor ON
    assert ("stack", str(wt), str(cfg.registry("AF8")), "mtp") in ops.calls
    # the lease is held across the leg and released
    assert ops.calls.count(("lease", "acquire")) == 1 and ops.calls.count(("lease", "release")) == 1
    assert ops.calls.index(("lease", "acquire")) < ops.calls.index(("stack", str(wt), str(cfg.registry("AF8")), "mtp"))
    assert ops.calls.index(("stop_stack",)) < ops.calls.index(("lease", "release"))       # R4: held to teardown
    # harvest: the dossier and LAST_LEG_END
    d = cfg.dossier(name)
    assert sorted(p.name for p in d.iterdir()) == sorted(["receipt.json", "watch.jsonl", f"capacity_ladder.p475-{name}.jsonl",
                                                          f"capacity_ladder.p475-{name}.manifest.json", "kv_line.json",
                                                          "worker_argv.json", "SCRUB_MANIFEST.json"])
    assert not d.with_name(f"{name}.stage").exists()
    assert float((cfg.p475 / "LAST_LEG_END").read_text()) == ops.t
    assert str(cfg.workdir) not in (d / "receipt.json").read_text()                  # scrubbed: $STACK_WORKDIR
    assert "$STACK_WORKDIR" in (d / "receipt.json").read_text()


def test_the_off_arm_runs_predictor_off(world):
    ops, cfg = world
    name, r = leg(ops, cfg, "TQ4-OFF", 1)
    assert r["verdict"] == "VALID", r["problems"]
    assert ("stack", str(cfg.worktree("TQ4-OFF")), str(cfg.registry("TQ4-OFF")), "off") in ops.calls
    assert "--draft-kind" not in r["worker_argv"]
    assert all(v == "null" for shape in r["drafter_keys"] for v in shape.values())


# ------------------------------------------------------------------------------------------------ pre-check -> NOT_STARTED
@pytest.mark.parametrize("setup, match", [
    (lambda o, c: o.power_reading.update(watts=96), "power"),
    (lambda o, c: o.power_reading.update(volts=20), "power"),
    (lambda o, c: o.power_reading.update(battery=20), "power"),
    (lambda o, c: setattr(o, "listener", 4242), ":8000"),
    (lambda o, c: o.busy_list.append("4242 python -m bench.run_capacity --model x"), "busy"),
    (lambda o, c: setattr(o, "lock_refused", True), "lease"),
    (lambda o, c: (c.p475.mkdir(parents=True, exist_ok=True), (c.p475 / "LAST_LEG_END").write_text(f"{o.t - 100}\n")), "since"),
    (lambda o, c: ((c.workdir / "p426").mkdir(parents=True, exist_ok=True),
                   (c.workdir / "p426" / "LAST_LEG_END").write_text(f"{o.t - 599}\n")), "since"),
    (lambda o, c: ((c.workdir / "p426").mkdir(parents=True, exist_ok=True),
                   (c.workdir / "p426" / "LAST_LEG_END").write_text("garbage")), "LAST_LEG_END"),
    (lambda o, c: K._atomic_json(c.preflight_record("AF8"), dict(status="REFUSED")), "preflight"),
    (lambda o, c: c.preflight_record("AF8").unlink(), "preflight"),
    (lambda o, c: o.arms["AF8"].update(clean=False), "not clean"),
    (lambda o, c: o.arms["AF8"].update(parent="9" * 40), "parent"),
    (lambda o, c: (c.capacity_outputs("AF8", "u4-af8-b1.a1")["rows"].parent.mkdir(parents=True),
                   c.capacity_outputs("AF8", "u4-af8-b1.a1")["rows"].write_text("")), "destinations"),
    (lambda o, c: (c.dossier("u4-af8-b1.a1").mkdir(parents=True)), "destinations"),
])
def test_a_pre_check_refusal_starts_nothing(world, setup, match):
    ops, cfg = world
    setup(ops, cfg)
    name, r = leg(ops, cfg)
    assert r["verdict"] == "NOT_STARTED" and any(match in p for p in r["problems"]), r["problems"]
    assert not started(ops) and not ops.spawned
    assert json.loads(cfg.receipt_path(name).read_text())["verdict"] == "NOT_STARTED"
    assert r["_harvest"] is None and not (cfg.dossier(name) / "receipt.json").exists()


def test_idle_is_measured_from_the_later_last_leg_end(world):
    ops, cfg = world
    cfg.p475.mkdir(parents=True, exist_ok=True)
    (cfg.p475 / "LAST_LEG_END").write_text(f"{ops.t - 5000}\n")
    (cfg.workdir / "p426").mkdir()
    (cfg.workdir / "p426" / "LAST_LEG_END").write_text(f"{ops.t - 600}\n")
    assert leg(ops, cfg)[1]["verdict"] == "VALID"


def test_the_kv_environment_is_stripped_from_the_router_handle(world):
    """R2: the router handle's own environment strips the names (RealOps' ChainOps subclass)."""
    env = K.strip_kv({"KV_BITS": "4", "KV_GROUP_SIZE": "32", "TQ_KV_QUANT_MODE": "prod", "TQ_PREFILL_IMPL": "x", "PATH": "/bin",
                      "HF_HOME": "/h"})
    assert env == {"PATH": "/bin", "HF_HOME": "/h"}
    from bench import chain_ops
    cls = K._p475_chain_class()
    assert issubclass(cls, chain_ops.ChainOps)


# ------------------------------------------------------------------------------------------------ after load (R5) -> INVALID, no driver
@pytest.mark.parametrize("setup, match", [
    (lambda o: setattr(o, "worker_argv_override", ["/wt/.venv/bin/mlx_vlm.server", "--model", "caslca/x"]), "argv"),
    (lambda o: o.worker_env.update(KV_BITS="8"), "stripped"),
    (lambda o: o.worker_env.update(TQ_KV_QUANT_MODE="prod"), "stripped"),
    (lambda o: o.kv_over.update(kv_bits=4.0), "KV line"),
    (lambda o: o.kv_over.update(kv_group_size=32), "KV line"),
    (lambda o: o.kv_over.update(kv_key_bits=4), "KV line"),
    (lambda o: setattr(o, "kv_line_for", lambda arm: "no kv line\n"), "KV line"),
])
def test_a_post_load_failure_aborts_before_the_driver(world, setup, match):
    ops, cfg = world
    setup(ops)
    name, r = leg(ops, cfg)
    assert r["verdict"] == "INVALID" and any(match in p for p in r["problems"]), r["problems"]
    assert not ops.spawned and ("stop_stack",) in ops.calls
    assert r["_harvest"] == "harvested"                              # INVALID legs are evidence too


def test_the_kv_line_is_read_from_this_loads_log_only(world):
    ops, cfg = world
    log = cfg.worktree("AF8") / "logs" / "mlx_vlm.log"
    log.parent.mkdir(parents=True)
    from bench.tests.test_p475_impl_support import kv_log_line
    log.write_text(kv_log_line("AF8"))                              # an earlier load's line …
    ops.kv_line_for = lambda arm: "nothing logged this time\n"     # … must not satisfy this load
    assert leg(ops, cfg)[1]["verdict"] == "INVALID"


def test_an_off_worker_with_a_draft_flag_is_invalid(world):
    ops, cfg = world
    from bench.tests.test_p475_impl_support import build_argv, base_registry
    on = build_argv(K.arm_registry_text(base_registry(), "TQ4"), K.PICK)
    ops.worker_argv_override = on
    name, r = leg(ops, cfg, "TQ4-OFF")
    assert r["verdict"] == "INVALID" and any("OFF worker" in p for p in r["problems"])


def test_predictor_argv_problems_on():
    assert K.predictor_argv_problems(["--draft-kind", "mtp", "--draft-model", "d"], {"draft_model": "d"}, "on") == []
    assert K.predictor_argv_problems(["--draft-kind", "mtp"], {"draft_model": "d"}, "on")
    assert K.predictor_argv_problems(["--draft-kind", "mtp", "--draft-kind", "mtp", "--draft-model", "d"], {"draft_model": "d"}, "on")
    assert K.predictor_argv_problems([], {}, "off") == []


# ------------------------------------------------------------------------------------------------ driver (R6) and rungs (R21)
def test_a_driver_timeout_is_terminated_escalated_and_invalid(world):
    ops, cfg = world
    ops.driver_hangs = True
    name, r = leg(ops, cfg)
    assert r["verdict"] == "INVALID" and any("timed out" in p for p in r["problems"])
    assert [s for _, s in ops.signals] == [signal.SIGTERM, signal.SIGKILL]
    order = [c[0] for c in ops.calls if c[0] in ("stop_watch", "stop_stack")]
    assert order == ["stop_watch", "stop_stack"]
    assert r["driver_timeout_s"] == 3 * sum(cfg.expected_for("AF8", 1)) + K.DRIVER_OVERHEAD_S


def test_a_nonzero_driver_exit_is_invalid(world):
    ops, cfg = world
    ops.driver_rc = 1
    assert any("driver exit 1" in p for p in leg(ops, cfg)[1]["problems"])


@pytest.mark.parametrize("over, match", [(dict(cache_n=5), "cache_n"), (dict(finish_reason="stop"), "finish_reason"),
                                         (dict(draft_n=0), "draft_n"), (dict(session_id="other-1"), "session id")])
def test_a_rung_with_problems_makes_the_leg_invalid(world, over, match):
    ops, cfg = world
    ops.row_over = over
    r = leg(ops, cfg)[1]
    assert r["verdict"] == "INVALID" and any(match in p for p in r["problems"]), r["problems"]


# ------------------------------------------------------------------------------------------------ watcher (R9–R11) -> SPEED_INVALID
@pytest.mark.parametrize("mode, match", [("absent", "no watcher report"), ("power_fail", "power"), ("gap", "gap"),
                                         ("early", "early"), ("unfinalized", "finalized"), ("battery", "battery")])
def test_watcher_failures_are_speed_problems_never_invalid(world, mode, match):
    ops, cfg = world
    ops.watch_mode = mode
    r = leg(ops, cfg)[1]
    assert r["verdict"] == "VALID" and r["speed_valid"] is False
    assert any(match in p for p in r["speed_problems"]), r["speed_problems"]


def test_too_few_ticks_is_a_speed_problem():
    text = "".join(json.dumps(x) + "\n" for x in (
        dict(tick=0, t=0.0, driver_alive=True, watts=140, volts=28, battery=90),
        dict(exit_state="driver_exited", t=3000.0, battery_intervals=[])))
    problems, _ = K.watch_speed_problems(text, 0.0, 3000.0, 300.0)
    assert any("ticks 1 < 8" in p for p in problems)


def _stamp(t):
    import datetime
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S +0000")


@pytest.mark.parametrize("text, match", [
    (lambda t: "", "no well-formed"),
    (lambda t: f"{_stamp(t - 3600)} Assertions \tUsing AC (Charge: 90%)\n{_stamp(t + 60)} Assertions \tUsing Batt (Charge: 80%)\n",
     "on battery"),
    (lambda t: f"{_stamp(t + 60)} Assertions \tUsing AC (Charge: 90%)\n", "unproven"),
    (lambda t: f"{_stamp(t - 3600)} Assertions \tUsing AC (Charge: 90%)\n2026-11-04 Using Batt\n", "malformed"),
])
def test_a_pmset_battery_interval_in_the_driver_window_is_a_speed_problem(world, text, match):
    ops, cfg = world
    ops.pmset_text = text(ops.t)
    r = leg(ops, cfg)[1]
    assert r["verdict"] == "VALID" and any(match in p for p in r["speed_problems"]), r["speed_problems"]


def test_power_at_driver_exit_is_a_speed_problem(world):
    ops, cfg = world
    real = ops.power
    calls = []

    def power():
        calls.append(1)
        return real() if len(calls) == 1 else dict(watts=140, volts=28, battery=15)
    ops.power = power
    r = leg(ops, cfg)[1]
    assert r["verdict"] == "VALID" and r["speed_valid"] is False and any("exit" in p for p in r["speed_problems"])


# ------------------------------------------------------------------------------------------------ teardown (R7) and identity at exit (R1)
@pytest.mark.parametrize("setup, match", [
    (lambda o: setattr(o, "unload_result", False), "unload"),
    (lambda o: setattr(o, "stop_rc", 1), "stop_stack"),
    (lambda o: setattr(o, "survivor", True), "survivor"),
])
def test_teardown_must_be_proven(world, setup, match):
    ops, cfg = world
    setup(ops)
    r = leg(ops, cfg)[1]
    assert r["verdict"] == "INVALID" and any(match in p for p in r["problems"]), r["problems"]


def test_identity_drift_during_the_leg_is_invalid(world):
    ops, cfg = world
    orig = ops.stack

    def stack(wt, registry, predictor):
        h = orig(wt, registry, predictor)
        stop = h.stop_stack

        def stop_and_dirty():
            ops.arms["AF8"]["clean"] = False
            return stop()
        h.stop_stack = stop_and_dirty
        return h
    ops.stack = stack
    r = leg(ops, cfg)[1]
    assert r["verdict"] == "INVALID" and any("not clean" in p or "identity changed" in p for p in r["problems"])


# ------------------------------------------------------------------------------------------------ receipts (R17) and harvest (R18)
def test_a_receipt_is_never_overwritten_and_the_canonical_wins(tmp_path):
    p = tmp_path / "legs" / "u4-n16-b1.a1" / "receipt.json"
    assert K.write_receipt(p, dict(verdict="VALID")) == p
    second = K.write_receipt(p, dict(verdict="INVALID"))
    assert second != p and second.name.startswith("receipt.refused-")
    assert K.read_receipt(p.parent)["verdict"] == "VALID"


def test_harvest_refuses_pii_and_stages_nothing_final(world):
    ops, cfg = world
    ops.row_over = dict(note="ssh p475fakeuser@p475fakehost.example.org")
    name = K.leg_name("AF8", 1, 1)
    real = K._publish

    def leaky(data, rel, scrub, compressible=False):
        out = real(data, rel, scrub, compressible)
        if "capacity_ladder" in rel:
            out[3].append(f"{rel}: PII after scrub")
        return out
    K._publish = leaky
    try:
        r = K.run_leg(name, "AF8", ops, cfg)
    finally:
        K._publish = real
    assert r["verdict"] == "VALID" and r["_harvest"].startswith("harvest failed")
    assert not cfg.dossier(name).exists() and not cfg.dossier(name).with_name(f"{name}.stage").exists()
    assert not (cfg.p475 / "LAST_LEG_END").exists()                  # R8: the idle starts after a completed harvest
    # resume replays the harvest of a receipt without its dossier
    done, problems = K.replay_harvests(ops, cfg)
    assert done == [name] and problems == [] and cfg.dossier(name).is_dir()


def test_harvest_replaces_a_crashed_stage_and_never_redoes_a_final_dossier(world):
    ops, cfg = world
    name, r = leg(ops, cfg)
    final = cfg.dossier(name)
    before = (final / "receipt.json").read_bytes()
    assert K.harvest(name, ops, cfg) == "exists" and (final / "receipt.json").read_bytes() == before
    import shutil
    shutil.rmtree(final)
    stale = final.with_name(f"{name}.stage")
    stale.mkdir()
    (stale / "junk").write_text("x")
    assert K.harvest(name, ops, cfg) == "harvested" and not stale.exists() and not (final / "junk").exists()


def test_the_evidence_stage_gets_the_scrubbed_logs(world):
    ops, cfg = world
    name, r = leg(ops, cfg)
    ev = cfg.evidence_stage(name)
    assert (ev / "mlx_vlm.log").read_text().count("KV cache resolved:") == 1


def test_realops_router_handle_strips_kv_names_without_starting_anything(tmp_path, monkeypatch):
    """R2 on the real seam: the ChainOps subclass RealOps hands out strips every KV / TQ name from the router environment, also
    the ones `<WT>/.env` would add (ChainOps.env_base overlays it and strips nothing)."""
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".env").write_text("KV_BITS=8\nTQ_KV_QUANT_MODE=prod\nSOMETHING=1\n")
    monkeypatch.setenv("KV_GROUP_SIZE", "32")
    monkeypatch.setenv("TQ_PREFILL_IMPL", "x")
    ops = K.RealOps(tmp_path / "wd", repo=wt)
    handle = ops.stack(wt, wt / "main_models.yaml", "off")
    env = handle.env_base()
    assert not K.kv_env_names(env) and env["SOMETHING"] == "1"
    assert env["MLX_SERVE_CONFIG"] == str(wt / "main_models.yaml") and env["MLX_VLM_CACHE_SESSION_MAX"] == "1"
    assert handle.unload_ok() is True and hasattr(handle, "expected_worker_argv") and hasattr(handle, "stop_stack")
