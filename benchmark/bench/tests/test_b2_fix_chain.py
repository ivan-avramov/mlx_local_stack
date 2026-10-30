"""B2 fix pass (C239): tests for the adopted findings of the s1-s5 reviews that the frozen tests do not (or not alone) pin.
Hermetic: the frozen P426 world (`b2_frozen_add_support.world`: FakeOps + the item-barrier fake probe), bare chains and the real
`run_tg1_probe` in-process; no router, worker, model, network or GPU."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import chain_core as core
from bench import chain_hooks as ch
from bench import chain_ops as co
from bench import chain_rows as cr
from bench import p426_hooks as ph
from bench import p426_receipt as pr
from bench import p426_reconcile as prc
from bench.tests import b2_frozen_add_support as A
from bench.tests import b2_frozen_support as S
from bench.tests.test_c147_chain_runner import arg, invocations


# ------------------------------------------------------------------------------------------------ helpers
def run_leg(tmp_path, monkeypatch, mode=("pilot",), *, arm="off", mutate=None, extra_env=None, timeout=240):
    env = A.world(tmp_path, monkeypatch, arm=arm)
    env["ops"].extra_env.update(extra_env or {})
    if mutate:
        mutate(env)
    argv, r = S.p426_argv(env, mode)
    try:
        rc = S.run_p426(env, argv, rfd=r, timeout=timeout)
    finally:
        env["ops"].cancel()
    return rc, env


def after_load(fn):
    """A world mutation that takes effect once the worker is loaded (so no entry check can see it)."""
    def mutate(env):
        ops, original = env["ops"], env["ops"].load

        def load(model):
            ident = original(model)
            fn(env)
            return ident
        ops.load = load
    return mutate


def item_started(env):
    return bool(list(Path(env["out"]).rglob("*.item0.go")))


def said(env, text):
    return any(text in ln for ln in env["lines"])


# ------------------------------------------------------------------------------------------------ the P426 schedule at the probe
def probe_calls(env):
    return [(arg(i["argv"], "--lang"), arg(i["argv"], "--items").split(","), arg(i["argv"], "--limit")) for i in invocations(env)]


def test_the_s1_leg_runs_python_then_go_in_the_seeded_order_and_every_invocation_passes_evidence_p426(tmp_path, monkeypatch):
    rc, env = run_leg(tmp_path, monkeypatch, ("chain", "s1"))
    assert rc == 0, "\n".join(env["lines"][-8:])
    names = {"python": [f"p{i}" for i in range(1, 7)], "go": [f"g{i}" for i in range(1, 7)]}
    py, go = (S.p426_order(names[lang], 1001) for lang in ("python", "go"))
    assert probe_calls(env) == [("python", py[:5], "5"), ("python", py[5:], None), ("go", go, None)]
    assert all(arg(i["argv"], "--evidence") == "p426" for i in invocations(env))
    cj = S.chain_json(env)
    assert cj["chain_config"]["config_id"] == "tg1-p426" and cj["status"] == "finished" and cj["rc"] == 0


def test_the_s2_leg_runs_go_first_at_the_probes_items(tmp_path, monkeypatch):
    rc, env = run_leg(tmp_path, monkeypatch, ("chain", "s2"))
    assert rc == 0, "\n".join(env["lines"][-8:])
    names = {"python": [f"p{i}" for i in range(1, 7)], "go": [f"g{i}" for i in range(1, 7)]}
    go, py = (S.p426_order(names[lang], 2002) for lang in ("go", "python"))
    assert probe_calls(env) == [("go", go[:5], "5"), ("go", go[5:], None), ("python", py, None)]


def test_the_pilot_is_the_first_five_of_s1s_python_order(tmp_path, monkeypatch):
    rc, env = run_leg(tmp_path, monkeypatch, ("pilot",))
    assert rc == 0, "\n".join(env["lines"][-8:])
    py = S.p426_order([f"p{i}" for i in range(1, 7)], 1001)
    assert probe_calls(env) == [("python", py[:5], "5")]


# ------------------------------------------------------------------------------------------------ R3 / P23 / R6 (DNF records)
def test_the_dnf_limit_counts_the_whole_leg_across_languages_and_arms(tmp_path):
    from bench.tests.test_b2_s3_core import BASE, bare, incomplete
    c = bare(tmp_path)
    c.p426_dnf = [dict(slot=f"{BASE}|x", session="s1", language="go", arm="A"),
                  dict(slot=f"{BASE}|y", session="s2", language="python", arm="B")]
    with pytest.raises(co.ChainAbort, match="DNF"):
        incomplete(c, tmp_path)
    assert len(c.p426_dnf) == 2


def test_a_dnf_records_its_item_record_as_the_path_string_and_its_sidecar_by_slot_file(tmp_path):
    from bench.tests.test_b2_s3_core import BASE, bare, incomplete
    c = bare(tmp_path)
    c.p426_dnf_eligible = lambda att, load, leg, cause, slot=None: (setattr(c, "p426_dnf_item", dict(sha256="e" * 64)), None)[1]
    incomplete(c, tmp_path)
    d, = c.p426_dnf
    slot_file = cr.slot_file(d["slot"])
    assert d["item_record"] == f"items/{slot_file}.dnf.json" and isinstance(d["item_record"], str)
    sidecars = [p.name for p in (tmp_path / "s1" / "p426_dnf").iterdir()]
    assert sidecars == [slot_file + ".json"] and not any("|" in n or "/" in n for n in sidecars) and "|" in d["slot"]


# ------------------------------------------------------------------------------------------------ P24 log bounds
def test_log_bounds_are_portable_and_finalized_even_when_the_teardown_raises(tmp_path):
    from bench.tests.test_b2_s4_reconcile import stub_run_chain
    c, log = stub_run_chain(tmp_path, [])
    log.write_bytes(b"abc\ndef\n")

    def boom():
        raise RuntimeError("teardown failed")
    c.ops.stop_stack = boom
    with pytest.raises(RuntimeError, match="teardown"):
        c.run()
    text = (tmp_path / "log_bounds.json").read_text()
    doc = json.loads(text)
    assert doc["finalized"] and [f["offset_end"] for f in doc["files"]] == [8, 5]
    assert [f["path"] for f in doc["files"]] == ["<WT>/logs/mlx_vlm.log", "<WT>/logs/main_model.log"]
    assert str(tmp_path) not in text


# ------------------------------------------------------------------------------------------------ P29 / R4 / P20 seams and router identity
def test_the_chain_uses_only_the_seams_the_spec_names():
    import inspect
    assert set(core.P426_SEAMS) == {"proc_argv", "proc_environ", "interpreter_inventory", "loaded_images", "snapshot_hashes",
                                    "expected_worker_argv", "busy_procs", "descendants", "create_time", "worktree_state",
                                    "interpreter_inventory_at"}
    src = inspect.getsource(core) + inspect.getsource(ph) + inspect.getsource(pr)
    assert "router_identity" not in src and "identity_alive" not in src and "p426_receipt_checks_available" not in src


def test_a_router_replaced_after_load_stops_the_leg_before_item_one(tmp_path, monkeypatch):
    def replace(env):
        base = env["ops"].create_time
        env["ops"].create_time = lambda pid: 99.0 if pid == 1 else base(pid)
    rc, env = run_leg(tmp_path, monkeypatch, mutate=after_load(replace))
    assert rc == 2 and env["ops"].names("load") and not item_started(env)
    assert said(env, "router identity")


def test_the_router_identity_is_the_pid_and_start_time_not_liveness_or_a_config_sha(tmp_path, monkeypatch):
    def liveness_and_config_sha_say_no(env):
        env["ops"].router_ok = lambda: False
    rc, env = run_leg(tmp_path, monkeypatch, mutate=liveness_and_config_sha_say_no)
    assert rc == 0, "\n".join(env["lines"][-8:])                       # `(pid, create_time(pid))` is unchanged


def test_a_router_replaced_between_two_barriers_invalidates_the_item(tmp_path, monkeypatch):
    """The hooks compare the owned router's `(pid, create_time(pid))` at every barrier (spec 3)."""
    def replace_after_the_first_item(env):
        ops, base = env["ops"], env["ops"].create_time
        ops.create_time = lambda pid: (99.0 if list(Path(env["out"]).rglob("*.item0.done")) and pid == 1 else base(pid))
    rc, env = run_leg(tmp_path, monkeypatch, mutate=replace_after_the_first_item)
    assert rc == 2
    assert S.chain_json(env)["p426_invalid"] or said(env, "router identity")


# ------------------------------------------------------------------------------------------------ P31 the before-invocation checks
@pytest.mark.parametrize("what, change, text", [
    ("head", lambda env: env["state"].update(head="f" * 40), "worktree HEAD"),
    ("dirty", lambda env: env["state"].update(clean=False), "not clean"),
    ("registry", lambda env: setattr(env["ops"], "overlay_sha", lambda: "0" * 64), "registry"),
    ("probe identity", lambda env: env["ops"].extra_env.update(FAKE_PRINT_POLICY_SHA="d" * 64), "probe identity"),
    ("record", lambda env: Path(env["records"]["v8"]).write_text(
        json.dumps(dict(json.loads(Path(env["records"]["v8"]).read_text()), pilot_deadline_s=1.0))), "frozen record"),
])
def test_the_before_invocation_checks_stop_the_leg_before_item_one(tmp_path, monkeypatch, what, change, text):
    rc, env = run_leg(tmp_path, monkeypatch, mutate=after_load(change))
    assert rc == 2 and env["ops"].names("load") and not item_started(env), "\n".join(env["lines"][-6:])
    assert said(env, text), (what, env["lines"][-4:])


# ------------------------------------------------------------------------------------------------ P18 the settle bound
def test_the_settle_bound_comes_from_the_frozen_record_amendment_else_v8_base(tmp_path):
    v8 = S.write_record(tmp_path / "r" / "v8_base.json", S.v8_base(settle_bound_s=777.0))
    am = S.write_record(tmp_path / "r" / "timeout_amendment.json", S.timeout_amendment(v8, settle_bound_s=1234.0))
    reh = S.write_record(tmp_path / "r2" / "rehearsal.json", S.rehearsal_manifest(tmp_path / "p426/rehearsal/x"))
    cfg = SimpleNamespace(transport_policy="p426_continue")

    def bound(path, mode, **kw):
        args = SimpleNamespace(predictor="off", frozen_record=str(path), mode=mode, rehearsal=kw.get("rehearsal", False))
        return core.Chain.default_hooks(cfg, args, SimpleNamespace(), tmp_path / "o").settle_bound_s
    assert bound(am, "chain") == 1234.0
    assert bound(v8, "pilot") == 777.0
    assert bound(reh, "chain", rehearsal=True) == core.P426_SETTLE_BOUND_S


# ------------------------------------------------------------------------------------------------ P21 the item record on every done outcome
def test_an_invalidated_done_still_writes_its_item_record_before_the_answer(tmp_path, monkeypatch):
    rc, env = run_leg(tmp_path, monkeypatch, extra_env={"B2_SKEW_ITEMS": S.p426_order([f"p{i}" for i in range(1, 7)], 1001)[1]})
    assert rc == 2
    records = sorted(p for p in Path(env["out"]).rglob("items/*.json") if not p.name.endswith((".ready.json", ".dnf.json")))
    invalid = [json.loads(p.read_text()) for p in records if json.loads(p.read_text())["verdict"] == "invalid"]
    assert invalid and invalid[0]["checks"] and invalid[0]["ready_sha256"]


def hooks_world(tmp_path, monkeypatch):
    from bench.tests.test_b2_frozen_s4_reconcile import hooks
    return hooks(tmp_path, monkeypatch)


def test_a_done_without_its_ready_record_or_with_a_changed_worker_writes_an_invalid_item_record(tmp_path, monkeypatch):
    h, env, slot, ctx, run_item = hooks_world(tmp_path, monkeypatch)
    try:
        r = run_item()
        done = dict(id="python/p1", attempt_id="python/p1#1.0", passed=True, nonconv_kind=None, evidence={})
        d = h.after_attempt(slot, done, ctx("done", ready=None, row_=r))
        assert d.kind == "invalidate"
        rec = json.loads((Path(env["out"]) / "items" / (cr.slot_file(slot) + ".json")).read_text())
        assert rec["verdict"] == "invalid" and rec["ready_sha256"] is None and not rec["checks"]["preconditions"]["ok"]
    finally:
        env["ops"].cancel()


def test_the_ready_sha256_is_the_ready_records_self_hash(tmp_path, monkeypatch):
    h, env, slot, ctx, run_item = hooks_world(tmp_path, monkeypatch)
    try:
        assert h.before_attempt(slot, ctx("ready")).kind == "accept"
        ready = Path(env["out"]) / "items" / (cr.slot_file(slot) + ".ready.json")
        r = run_item()
        done = dict(id="python/p1", attempt_id="python/p1#1.0", passed=True, nonconv_kind=None, evidence={})
        h.after_attempt(slot, done, ctx("done", ready=json.loads(ready.read_text()), row_=r))
        rec = json.loads((Path(env["out"]) / "items" / (cr.slot_file(slot) + ".json")).read_text())
        assert rec["ready_sha256"] == json.loads(ready.read_text())["sha256"]          # fix round 3 (item 11)
    finally:
        env["ops"].cancel()


# ------------------------------------------------------------------------------------------------ P16 / P26 / P27 reconcile
def test_a_kill_is_read_from_the_structured_fields_never_from_key_names():
    from bench.tests.test_b2_frozen_s4_reconcile import BEFORE, SESSION, USAGE, after, lines_of, row
    ok = prc.reconcile_item(row(), lines_of(S.item_window(SESSION, USAGE)), BEFORE, after())
    assert ok.ok and ok.case == "completed"                  # a normal row's termination dict HAS keys `killed` / `in_flight_at_kill`
    killed = row(termination=dict(killed=[dict(role="client")], in_flight_at_kill=0, reason="stalled"), nonconv_kind="stalled")
    killed["gate"] = dict(killed["gate"], requests_completed_at_kill=3)
    rep = prc.reconcile_item(killed, lines_of(S.item_window(SESSION, USAGE)), BEFORE, after())
    assert rep.ok and rep.case == "kill_boundary"
    # final fix round P44: the probe fills `killed` only inside its kill path, after the count / reason markers; a list without
    # any marker is no kill (the item reconciles as a completed one, strictly)
    only_killed_values = row(termination=dict(killed=[dict(role="client")], in_flight_at_kill=None))
    assert prc.reconcile_item(only_killed_values, lines_of(S.item_window(SESSION, USAGE)), BEFORE, after()).case == "completed"


def test_the_pairing_check_names_a_failing_position_only_when_it_fails():
    from bench.tests.test_b2_frozen_s4_reconcile import BEFORE, SESSION, USAGE, after, lines_of, row
    ok = prc.reconcile_item(row(), lines_of(S.item_window(SESSION, USAGE)), BEFORE, after())
    assert ok.checks["pairing"]["ok"] and "position" not in ok.checks["pairing"]["detail"]
    bad_usage = [list(u) for u in USAGE]
    bad_usage[1][1] += 1
    bad = prc.reconcile_item(row(bad_usage), lines_of(S.item_window(SESSION, USAGE)), BEFORE, after())
    assert not bad.checks["pairing"]["ok"] and "position 1" in bad.checks["pairing"]["detail"]


def test_log_field_values_stay_strings_as_logged():
    (ln,) = prc.parse_log(S.window([S.completed_line(session="ses_x", prompt_tokens=99, generated_tokens=7,
                                                     draft=S.draft_counters(2, 6, 4))]))
    assert all(isinstance(v, str) for v in ln.fields.values()) and ln.fields["draft_n"] == "6" and ln.fields["elapsed"] == "10.000s"


# ------------------------------------------------------------------------------------------------ P17 the manifest the real probe writes
@pytest.mark.parametrize("kind", ["refuse", "drop"])
def test_the_dnf_reconciliation_reads_the_abort_manifest_the_real_probe_writes(tmp_path, monkeypatch, kind):
    from bench.tests.test_b2_frozen_s2_probe import run_rc
    f = S.probe_fixture(monkeypatch, tmp_path)
    S.set_client_error(f, tmp_path, kind)                      # m1 completed, m2 in flight, then the client error event
    with S.barrier_answerer(f["out"].parent):
        assert run_rc(f, ["--evidence", "p426"]) not in (0, None)
    manifest = S.manifest_of(f["out"])
    stamp = manifest["transport_abort"]
    usage, session = stamp["gate"]["request_usage"], stamp["session_id"]
    assert [u[0] for u in usage] == ["m1"] and stamp["in_flight"]["message_id"] == "m2"
    before = S.summary(started=4, completed=4, prompt_total=1000, generated_total=400, decode_s=8.0)
    window = S.item_window(session, usage) + [S.started_line(), S.failed_line()]
    rep = prc.reconcile_dnf(manifest, prc.parse_log(S.window(window)), before, S.counters_after(before, usage, failed=1, decode_s=8.0))
    assert rep.ok and rep.case == "dnf_inflight_failed", rep.problems
    boundary = prc.reconcile_dnf(manifest, prc.parse_log(S.window(S.item_window(session, usage))), before,
                                 S.counters_after(before, usage, decode_s=8.0))
    assert boundary.ok and boundary.case == "dnf_boundary"           # the in-flight message does not change what the window shows


# ------------------------------------------------------------------------------------------------ P19 the A4 window is run per load
def test_an_a4_window_that_differs_from_gate_json_stops_the_leg_before_item_one(tmp_path, monkeypatch):
    def corrupt_gate_json(env):
        gate_json = Path(env["wd"]) / S.GATE_JSON
        doc = json.loads(gate_json.read_text())
        doc["A6_bare_anonymous"]["requests"][1]["prompt"] += 5
        gate_json.write_text(json.dumps(doc))
    def wrap(env):
        ops = env["ops"]
        original = ops.a4_gate

        def gate(model, tag, **kw):
            path = original(model, tag, **kw)
            corrupt_gate_json(env)
            return path
        ops.a4_gate = gate
    rc, env = run_leg(tmp_path, monkeypatch, mutate=wrap)
    assert rc == 2 and not item_started(env) and said(env, "A4 window")


# ------------------------------------------------------------------------------------------------ P32 / P33 / P34 receipt
def test_the_receipt_takes_the_probes_environment_from_the_launch_spec_not_from_a_process(tmp_path):
    inventory = lambda target: dict(path=str(target), inventory_sha256="8" * 64, editables={})  # noqa: E731
    ops = SimpleNamespace(wd=tmp_path, interpreter_inventory=inventory, interpreter_inventory_at=inventory,
                          loaded_images=lambda pid: S.LOADED_IMAGES("<WT>"), snapshot_hashes=lambda model: {"target": {}, "drafter": None})
    asked = []

    def proc_environ(pid):
        asked.append(pid)
        return dict(HOME=str(tmp_path / "home"), MLX_VLM_CACHE_SESSION_MAX="1")
    ops.proc_environ, ops.proc_argv = proc_environ, lambda pid: [f"<WT>/p{pid}", "x.py"]
    launch = dict(argv=["/venv/bin/python", "/wt/benchmark/run_tg1_probe.py"], env=dict(HOME=str(tmp_path / "home"), MARK="probe-launch",
                                                                                         HF_TOKEN="Z" * 30))
    doc = pr.arm_receipt(ops, worktree="/wt", out_root=tmp_path / "out", pids=dict(router=1, worker=2, probe=None), probe_launch=launch)
    assert set(asked) == {1, 2}                       # never a probe pid: there is none at this checkpoint
    assert doc["env"]["probe"]["MARK"] == "probe-launch" and doc["credential_keys"]["probe"] == ["HF_TOKEN"]
    assert "HF_TOKEN" not in doc["env"]["probe"] and "Z" * 30 not in json.dumps(doc)


def test_the_worker_argv_must_equal_the_expected_argv_exactly():
    expected = ["/wt/.venv/bin/python", "-m", "mlx_vlm.server", "--model", "m"]
    assert pr.worker_argv_problems(expected, expected, "off") == []
    assert pr.worker_argv_problems(["arch", "-arm64"] + expected, expected, "off")
    assert pr.worker_argv_problems(expected[1:], expected, "off")


def test_pair_problems_and_write_dossier_have_the_spec_16_7_signatures(tmp_path):
    import inspect
    assert list(inspect.signature(pr.pair_problems).parameters) == ["first", "second"]
    assert list(inspect.signature(pr.write_dossier).parameters) == ["path", "pair", "off", "on", "differences", "verdict"]
    off, on = S.arm_receipt_doc("off"), S.arm_receipt_doc("on")
    diffs = pr.observed_differences(off, on)
    assert diffs and all(set(d) == {"process", "field", "off", "on"} for d in diffs)
    assert {d["field"] for d in diffs} == {"argv.worker", "snapshots.drafter"}
    assert all("HF_TOKEN" not in json.dumps(d) for d in diffs)


def test_a_dossier_names_its_pair_and_attempts_and_rejects_a_bad_name(tmp_path):
    a = S.write_record(tmp_path / "off" / "receipt.json", S.arm_receipt_doc("off"))
    b = S.write_record(tmp_path / "on" / "receipt.json", S.arm_receipt_doc("on"))
    ha = S.write_record(tmp_path / "off" / "HARVEST.json", S.self_hashed({"leg": "x"}))
    hb = S.write_record(tmp_path / "on" / "HARVEST.json", S.self_hashed({"leg": "y"}))
    off, on = dict(attempt="tg1-p426-off-s1.a1", receipt=a, harvest=ha), dict(attempt="tg1-p426-on-s1.a2", receipt=b, harvest=hb)
    with pytest.raises(ValueError):
        pr.write_dossier(tmp_path / "pairs" / "s1__off-a1__on-a1.json", pair="s1", off=off, on=on, differences=[], verdict="PASS")
    with pytest.raises(ValueError):
        pr.write_dossier(tmp_path / "pairs" / "s1__off-a1__on-a2.json", pair="s7", off=off, on=on, differences=[], verdict="PASS")
    with pytest.raises(ValueError):
        pr.write_dossier(tmp_path / "pairs" / "s1__off-a1__on-a2.json", pair="s1", off=dict(off, attempt="tg1-p426-off-s1"), on=on,
                         differences=[], verdict="PASS")
    doc = pr.write_dossier(tmp_path / "pairs" / "s1__off-a1__on-a2.json", pair="s1", off=off, on=on, differences=[], verdict="PASS")
    assert doc["arms"]["off"]["attempt"] == "tg1-p426-off-s1.a1" and doc["arms"]["on"]["receipt_sha256"] == S.sha256_file(b)


# ------------------------------------------------------------------------------------------------ R5 served registry
def test_the_served_registry_is_the_ops_overlay_under_injected_ops(tmp_path):
    from bench.tests.test_c147_chain_runner import R
    ops = SimpleNamespace(overlay=str(tmp_path / "WT" / "main_models.yaml"))
    assert R.served_registry(None, ops) == tmp_path / "WT" / "main_models.yaml"
    assert R.served_registry(None, None) == R.REPO / "main_models.yaml"          # production: the worktree's own file


# ------------------------------------------------------------------------------------------------ §16 refusals
@pytest.mark.parametrize("argv", [["chain", "s1"], ["pilot", "--models", "a", "--predictor", "nope"], ["nonsense"]])
def test_every_argparse_refusal_is_one_refused_line_and_rc_2(argv, capsys):
    from bench.tests.test_c147_chain_runner import R
    with pytest.raises(SystemExit) as e:
        R.parse_args(argv)
    assert e.value.code == 2
    lines = [ln for ln in capsys.readouterr().err.splitlines() if ln.strip()]
    assert len(lines) == 1 and lines[0].startswith("REFUSED: ")


def test_rehearsal_and_inject_parse_and_inject_needs_rehearsal(capsys):
    from bench.tests.test_c147_chain_runner import R
    base = ["chain", "s1", "--models", S.MODEL, "--probe-code-sha", S.HEX9]
    a = R.parse_args(base + ["--p426", "--rehearsal", "--inject", "stall-kill", "--out-root", "/x/leg.a1", "--campaign-core", "c",
                             "--frozen-prompt-date", S.EPOCH_DATE, "--policy-sha", "c" * 64, "--frozen-record", "/x/r.json"])
    assert a.rehearsal is True and a.inject == "stall-kill"
    for bad in (base + ["--inject", "stall-kill"], base + ["--rehearsal"]):
        with pytest.raises(SystemExit) as e:
            R.parse_args(bad)
        assert e.value.code == 2
    assert capsys.readouterr().err.count("REFUSED: ") == 2
