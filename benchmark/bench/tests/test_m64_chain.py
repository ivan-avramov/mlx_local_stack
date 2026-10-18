"""M64 step 4a: the arm-aware chain runner (spec 8, 4): schedule by (arm, model, lang, session), per-arm identities,
transport incidents (8.3), against the fake arm probe and a fake ChainOps. No router, worker or GPU."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import threading
from pathlib import Path

import pytest

from bench import arm_adapter as aa
from bench import arm_specs
from bench import chain_ops as co
from bench import m64_schedule as ms
from bench.tests.test_c147_chain_runner import FakeOps as BaseFakeOps, TIMERS

REPO = Path(__file__).resolve().parents[3]
M64 = REPO / "benchmark/chains/m64"
PICK1, PICK2 = co.PICK1, co.PICK2
EPOCH = "e" * 64
FROZEN = "Mon Jan 05 2026"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


C147 = REPO / "benchmark/chains/c147"
sys.path.insert(0, str(C147))
R = _load("run_tg1_chain", C147 / "run_tg1_chain.py")           # the base chain the M64 chain extends
M = _load("run_m64_chain", M64 / "run_m64_chain.py")
FAP = M64 / "fake_arm_probe.py"

LABELS = {"oc": arm_specs.OC.label, "pi": "fake-pi-label", "dsh": "fake-dsh-label"}


def fake_specs(monkeypatch):
    """Test-only specs for the arms that have no adapter yet: the oc field set under another arm id and label."""
    for arm in ("pi", "dsh"):
        monkeypatch.setitem(arm_specs.SPECS, arm, arm_specs.ArmSpec(
            arm_id=arm, label=LABELS[arm], probe="benchmark/chains/m64/fake_arm_probe.py",
            generation_fields=arm_specs.OC.generation_fields, runtime_pinned=arm_specs.OC.runtime_pinned,
            sha_fields=arm_specs.OC.sha_fields, version_field="opencode_version",
            web_evidence_rules=arm_specs.OC.web_evidence_rules))


class FakeOps(BaseFakeOps):
    """The c147 fake plus the arm hooks (search restart, cache reset, warm-up) and a per-arm A4 scaffold."""

    def __init__(self, wd):
        super().__init__(wd)
        self.tmpdir = Path(wd) / "m64/tmp"
        self.unload_ok = True

    def a4_gate(self, model, tag, scaffold=None):
        self._c("a4_gate", model, scaffold)
        return str(self.wd / "session_gate/a4_v2_latest.json")

    def require_arm_ops(self):
        self._c("require_arm_ops")

    def search_restart(self, leg):
        self._c("search_restart", leg["arm"], leg["block"])

    def reset_cache_session(self, model):
        self._c("reset_cache_session", model)

    def warmup(self, model):
        self._c("warmup", model)

    def env_base(self):
        env = super().env_base()
        env["FAKE_ARM_LABELS"] = json.dumps({v: k for k, v in LABELS.items()})
        return env

    def unload(self, model):
        self._c("unload", model)
        self.loaded = None
        return self.unload_ok


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    fake_specs(monkeypatch)
    ops = FakeOps(tmp_path)
    uni = tmp_path / "universe.json"
    uni.write_text(json.dumps({"items": {**{f"python/p{i:02d}": {} for i in range(22)},
                                         **{f"go/g{i:02d}": {} for i in range(21)}}}))
    yield dict(wd=tmp_path, ops=ops, uni=uni, lines=[], out=tmp_path / "m64-smoke")
    ops.cancel()


def run(env, argv, *, timers=None, plan=None, extra_env=None, timeout=120, lifecycle=None, fake_all=True,
        epoch=EPOCH, frozen=FROZEN):
    ops = env["ops"]
    if plan is not None:
        ops.extra_env["FAKE_ARM_PLAN"] = json.dumps(plan)
    ops.extra_env.update(extra_env or {})
    full = list(argv) + ["--python", sys.executable, "--out-root", str(env["out"]), "--arm-idle-s", "0",
                         "--universe", str(env["uni"])]
    if fake_all:
        for arm in ("oc", "pi", "dsh"):
            full += ["--probe", f"{arm}={FAP}"]
    if epoch and "--epoch-id" not in argv:
        full += ["--epoch-id", epoch]
    if frozen and not any(x in argv for x in ("--frozen-prompt-date", "--frozen-date-from")):
        full += ["--frozen-prompt-date", frozen]
    tm = M.Timers(**{**TIMERS, **(timers or {})})
    res = {}

    def target():
        try:
            res["rc"] = M.main(full, ops=ops, timers=tm, log_out=env["lines"].append, lifecycle_files=lifecycle)
        except BaseException as e:  # noqa: BLE001
            res["exc"] = e

    th = threading.Thread(target=target, daemon=True)
    th.start()
    th.join(timeout)
    if th.is_alive():
        ops.cancel()
        th.join(10)
        pytest.fail("runner did not finish: " + "\n".join(env["lines"][-15:]))
    if "exc" in res:
        raise res["exc"]
    return res["rc"]


def invocations(env):
    p = env["ops"].state / "invocations.jsonl"
    return [json.loads(ln) for ln in p.read_text().splitlines()] if p.exists() else []


def arg(argv, flag):
    return argv[argv.index(flag) + 1] if flag in argv else None


def chain_json(env):
    return json.loads((env["out"] / "chain.json").read_text())


def log_has(env, text):
    return any(text in ln for ln in env["lines"])


SMOKE = ["chain", "s1", "--smoke", "--arms", "oc", "--probe-code-sha", "oc=" + "9" * 64]
SMOKE3 = ["chain", "s1", "--smoke", "--arms", "oc,pi,dsh", "--probe-code-sha", "oc=" + "9" * 64,
          "--probe-code-sha", "pi=" + "9" * 64, "--probe-code-sha", "dsh=" + "9" * 64]


# ---------------------------------------------------------------- arguments
def test_arguments_need_arms_probe_code_and_a_valid_epoch():
    p = M.parse_args(SMOKE + ["--epoch-id", EPOCH])
    assert p.arms == ["oc"] and p.sessions == ["s1"] and p.smoke is True and p.epoch_id == EPOCH
    assert p.probe_code_sha == {"oc": "9" * 64}
    with pytest.raises(SystemExit):
        M.parse_args(["chain", "--arms", "oc"])                                  # probe code sha required per arm
    with pytest.raises(SystemExit):
        M.parse_args(SMOKE + ["--epoch-id", "short"])
    with pytest.raises(SystemExit):
        M.parse_args(["chain", "--arms", "oc,oc", "--probe-code-sha", "oc=" + "9" * 64])
    with pytest.raises(SystemExit):
        M.parse_args(["chain", "--arms", "oc,pi", "--probe-code-sha", "oc=" + "9" * 64])


def test_an_arm_without_an_adapter_refuses_before_anything_starts(env, monkeypatch):
    monkeypatch.delitem(arm_specs.SPECS, "pi")
    rc = run(env, ["chain", "s1", "--smoke", "--arms", "oc,pi", "--probe-code-sha", "oc=" + "9" * 64,
                   "--probe-code-sha", "pi=" + "9" * 64])
    assert rc == 2 and log_has(env, "no chain spec") and env["ops"].calls == [] and not (env["out"] / "chain.json").exists()


# ---------------------------------------------------------------- end to end, one arm
def test_smoke_chain_with_one_arm_runs_every_leg_and_freezes_the_identities(env):
    assert run(env, SMOKE) == 0
    cj = chain_json(env)
    assert cj["rc"] == 0 and cj["status"] == "finished" and cj["epoch_id"] == EPOCH
    assert set(cj["arm_generations"]) == {"oc"} and len(cj["arm_generations"]["oc"]) == 64
    assert cj["schedule_sha256"] == ms.schedule_sha256(json.loads((env["out"] / "schedule.json").read_text()))
    assert cj["policies"] == {"oc": "d" * 64}
    inv = invocations(env)
    s = json.loads((env["out"] / "schedule.json").read_text())
    legs = [leg for leg in ms.legs(s) if leg["session"] == "s1"]
    assert len(inv) == len(legs) == 2 * 4                                        # 2 picks x (python, go) x blocks [3, 1]
    for call, leg in zip(inv, legs):
        a = call["argv"]
        assert arg(a, "--items").split(",") == leg["items"] and arg(a, "--lang") == leg["lang"]
        assert arg(a, "--scaffold") == arm_specs.OC.label and arg(a, "--epoch-id") == EPOCH
        assert arg(a, "--seed-base") == "1001" and arg(a, "--frozen-prompt-date") == FROZEN
    stems = sorted(p.name for p in (env["out"] / "s1").glob("*.jsonl"))
    assert stems == sorted(f"{pick}.s1.oc_{lang}.jsonl" for pick in (PICK1, PICK2) for lang in ("python", "go"))


def test_rows_accumulate_per_stem_across_blocks_with_cumulative_expect_items(env):
    assert run(env, SMOKE) == 0
    inv = [c for c in invocations(env) if arg(c["argv"], "--model") == PICK1 and arg(c["argv"], "--lang") == "python"]
    assert len(inv) == 2
    first, second = (arg(c["argv"], "--expect-items").split(",") for c in inv)
    assert set(first) < set(second) and len(second) == 4
    rows = (env["out"] / "s1" / f"{PICK1}.s1.oc_python.jsonl").read_text().splitlines()
    assert len(rows) == 4


def test_every_leg_restarts_the_search_service_and_each_arm_switch_resets_the_cache_and_warms_up(env):
    assert run(env, SMOKE3) == 0
    names = [c[0] for c in env["ops"].calls if c[0] in ("search_restart", "reset_cache_session", "warmup", "load", "a4_gate")]
    s = json.loads((env["out"] / "schedule.json").read_text())
    legs = [leg for leg in ms.legs(s) if leg["session"] == "s1"]
    assert names.count("search_restart") == len(legs)
    # a switch = the arm differs from the previous leg's within one worker load (and the first leg of a load)
    switches, last = 0, None
    for leg in legs:
        if last is None or leg["load"] != last["load"] or leg["arm"] != last["arm"]:
            switches += 1
        last = leg
    assert names.count("reset_cache_session") == names.count("warmup") == switches
    a4 = [c for c in env["ops"].calls if c[0] == "a4_gate"]
    assert {c[2] for c in a4} == {LABELS["oc"], LABELS["pi"], LABELS["dsh"]}


def test_a_worker_is_loaded_once_per_pick_and_session_and_shared_by_every_arm(env):
    assert run(env, SMOKE3) == 0
    loads = [c for c in env["ops"].calls if c[0] == "load"]
    assert [c[1] for c in loads] == [PICK1, PICK2]
    cj = chain_json(env)
    assert len(cj["block_workers"]) == 2
    arms = {inv["arm"] for inv in invocations(env)}
    assert arms == {"oc", "pi", "dsh"}


def test_permutation_order_of_the_arms_follows_the_frozen_schedule(env):
    assert run(env, SMOKE3) == 0
    s = json.loads((env["out"] / "schedule.json").read_text())
    legs = [leg for leg in ms.legs(s) if leg["session"] == "s1"]
    assert [inv["arm"] for inv in invocations(env)] == [leg["arm"] for leg in legs]
    assert chain_json(env)["realized"] == [ms.leg_key(leg) for leg in legs]


# ---------------------------------------------------------------- identities (spec 4)
def test_the_chain_freezes_one_generation_composite_per_arm_and_one_worker_identity_for_all(env):
    assert run(env, SMOKE3) == 0
    cj = chain_json(env)
    assert set(cj["arm_generations"]) == {"oc", "pi", "dsh"} and len(set(cj["arm_generations"].values())) == 3
    assert set(cj["arms"]) == {f"{PICK1}|off", f"{PICK2}|off"}               # one worker identity per (model, predictor)
    assert set(cj["policies"]) == {"oc", "pi", "dsh"} and set(cj["pinned"]) == {"oc", "pi", "dsh", "shared"}
    assert cj["pinned"]["shared"]["registry_sha256"] == "a" * 64 and "serving_path" in cj["pinned"]["shared"]
    for arm in ("oc", "pi", "dsh"):
        assert cj["pinned"][arm]["probe_code_sha256"] == "9" * 64 and cj["pinned"][arm]["generation_identity_sha256"] == \
            cj["arm_generations"][arm]


def test_a_manifest_that_disagrees_with_the_frozen_arm_generation_is_a_barrier_mismatch(env):
    # the second oc leg of the pick changes a pinned field: no ack, the chain aborts (rc 2), nothing is rewritten
    plan = [{}, {"runtime.opencode_exe_sha256": "f" * 64}]
    rc = run(env, SMOKE, extra_env={"FAKE_MANIFEST_PLAN": json.dumps(plan)})
    assert rc == 2 and log_has(env, "BARRIER MISMATCH") and log_has(env, "opencode_exe_sha256")
    assert chain_json(env)["arm_generations"]["oc"]


def test_every_manifest_must_name_its_arm_and_the_chains_epoch(env):
    rc = run(env, SMOKE, extra_env={"FAKE_MANIFEST_OVERRIDE": json.dumps({"runtime.arm": "pi"})})
    assert rc == 2 and log_has(env, "arm: 'pi' != 'oc'")
    env["lines"].clear()


def test_an_incomplete_snapshot_is_refused_outside_smoke(env, tmp_path):
    """The fake probe reports snapshot_complete=true; flip it: smoke runs, a real chain refuses at the barrier."""
    assert run(env, SMOKE, extra_env={"FAKE_MANIFEST_OVERRIDE": json.dumps({"runtime.snapshot_complete": False})}) == 0
    small = tmp_path / "small.json"                                     # 3 + 3 items: one block per cell, fast
    small.write_text(json.dumps({"items": {**{f"python/p{i}": {} for i in range(3)}, **{f"go/g{i}": {} for i in range(3)}}}))
    env2 = dict(env, out=tmp_path / "m64", uni=small, lines=[])
    rc = run(env2, ["chain", "s1", "--arms", "oc", "--probe-code-sha", "oc=" + "9" * 64],
             extra_env={"FAKE_MANIFEST_OVERRIDE": json.dumps({"runtime.snapshot_complete": False})})
    assert rc == 2 and any("snapshot_complete" in ln for ln in env2["lines"])


def test_the_epoch_cannot_change_on_resume(env):
    assert run(env, SMOKE) == 0
    rc = run(env, SMOKE, epoch="f" * 64)
    assert rc == 2 and log_has(env, "differs from the chain's frozen epoch")


def test_lifecycle_drift_aborts_and_leaves_the_record_frozen(env, tmp_path):
    files = {k: tmp_path / f"lc_{k}" for k in M.LIFECYCLE}
    for k, f in files.items():
        f.write_text("v1")
    def drift():
        # change a lifecycle file once the first probe is running
        import time
        end = time.time() + 30
        while time.time() < end and not invocations(env):
            time.sleep(0.01)
        files["runner"].write_text("v2")

    t = threading.Thread(target=drift, daemon=True)
    t.start()
    rc = run(env, SMOKE, lifecycle=files, extra_env={"FAKE_ITEM_S": "0.3"})
    assert rc == 2 and log_has(env, "lifecycle drift")
    import hashlib
    assert chain_json(env)["lifecycle"]["runner"] == hashlib.sha256(b"v1").hexdigest()     # the frozen record is not rewritten


# ---------------------------------------------------------------- transport incidents (spec 8.3)
def first_leg(env):
    s = json.loads((env["out"] / "schedule.json").read_text())
    return ms.legs(s)[0]


def cell_items(env, pick, session, lang):
    s = json.loads((env["out"] / "schedule.json").read_text())
    load = next(l for l in s["loads"] if l["pick"] == pick and l["session"] == session)
    return next(c for c in load["cells"] if c["lang"] == lang)["order"]


def test_a_first_transport_failure_recovers_the_worker_and_reruns_the_same_slot_in_a_new_segment(env):
    plan = {"oc": [{"abort_after": 1, "cause": "server_error", "tokens": 700}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 0
    cj = chain_json(env)
    assert len(cj["incidents"]) == 1
    inc = cj["incidents"][0]
    assert inc["cause"] == "server_error" and inc["attempt"] == 1 and inc["output_tokens"] == 700
    assert inc["slot"].startswith(EPOCH + "|oc|" + PICK1 + "|s1|python|") and inc["item"] in inc["slot"]
    names = [c[0] for c in env["ops"].calls]
    i = names.index("unload")                                   # the recovery: unload, reload, cache reset, warm-up
    assert names[i:i + 4] == ["unload", "load", "reset_cache_session", "warmup"]
    loads = [c for c in env["ops"].calls if c[0] == "load"]
    assert len(loads) == 3 and len(cj["block_workers"]) == 3     # PICK1 + its recovery reload, PICK2
    seg = sorted(p.name for p in (env["out"] / "s1").glob(f"{PICK1}.s1.oc_python*.jsonl"))
    assert seg == [f"{PICK1}.s1.oc_python.jsonl", f"{PICK1}.s1.oc_python.w1.jsonl"]
    first = [json.loads(x) for x in (env["out"] / "s1" / seg[0]).read_text().splitlines()]
    second = [json.loads(x) for x in (env["out"] / "s1" / seg[1]).read_text().splitlines()]
    assert len(first) == 1 and first[0]["worker_after"] != second[0]["worker_after"]
    assert sorted(r["id"] for r in first + second) == sorted("python/" + n for n in cell_items(env, PICK1, "s1", "python"))
    assert cj["dnf"] == []


def test_the_failed_attempts_tokens_are_carried_by_the_slot(env):
    plan = {"oc": [{"abort_after": 0, "cause": "dropped_stream", "tokens": 1234}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 0
    inc = chain_json(env)["incidents"][0]
    assert inc["output_tokens"] == 1234 and inc["cause"] == "dropped_stream"
    assert M.slot_tokens(chain_json(env), inc["slot"]) == 1234


def test_a_second_transport_failure_in_the_same_slot_is_a_strict_fail_row_with_both_incidents(env):
    plan = {"oc": [{"abort_after": 0, "cause": "server_error", "tokens": 100},
                   {"abort_after": 0, "cause": "connection", "tokens": 50}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 0
    cj = chain_json(env)
    assert [i["attempt"] for i in cj["incidents"]] == [1, 2] and len(cj["dnf"]) == 1
    row = cj["dnf"][0]
    assert row["nonconv_kind"] == "transport_dnf" and row["passed"] is False and row["synthetic"] is True
    assert [i["cause"] for i in row["incidents"]] == ["server_error", "connection"]
    assert row["failed_attempt_output_tokens"] == 150
    assert M.validate_dnf_row(row, arm="oc", slot=row["slot"]) == []
    sidecar = env["out"] / "s1" / f"{PICK1}.s1.oc_python.dnf.jsonl"
    assert json.loads(sidecar.read_text()) == row
    rows = [json.loads(x) for f in (env["out"] / "s1").glob(f"{PICK1}.s1.oc_python*.jsonl")
            if not f.name.endswith(".dnf.jsonl") for x in f.read_text().splitlines()]
    assert row["id"] not in {r["id"] for r in rows}                    # the DNF slot has no probe row; the schedule continued
    assert len(rows) == len(cell_items(env, PICK1, "s1", "python")) - 1


def test_slot_identity_keys_epoch_arm_pick_session_language_and_item():
    key = M.slot_key(EPOCH, "oc", PICK1, "s1", "python", "p01")
    assert key == "|".join((EPOCH, "oc", PICK1, "s1", "python", "p01"))
    assert M.slot_key(EPOCH, "pi", PICK1, "s1", "python", "p01") != key and M.slot_key(EPOCH, "oc", PICK2, "s1", "python", "p01") != key


def test_two_arms_failing_on_the_same_item_are_two_slots_each_with_its_own_attempt_count(env):
    plan = {"oc": [{"abort_after": 0, "cause": "server_error", "tokens": 1}, "normal"],
            "pi": [{"abort_after": 0, "cause": "server_error", "tokens": 1}, "normal"]}
    assert run(env, ["chain", "s1", "--smoke", "--arms", "oc,pi", "--probe-code-sha", "oc=" + "9" * 64,
                     "--probe-code-sha", "pi=" + "9" * 64], plan=plan) == 0
    cj = chain_json(env)
    slots = [i["slot"] for i in cj["incidents"]]
    assert len(slots) == 2 and len(set(slots)) == 2 and all(i["attempt"] == 1 for i in cj["incidents"]) and cj["dnf"] == []


def test_a_failure_that_is_not_a_classified_transport_cause_is_not_retried_as_an_incident(env):
    plan = {"oc": [{"abort_after": 1, "cause": None, "tokens": 5}]}
    rc = run(env, SMOKE, plan=plan)
    assert rc == 2 and log_has(env, "LOAD INCOMPLETE") and log_has(env, "RESTART load") and log_has(env, "incomplete twice")
    assert chain_json(env)["incidents"] == []
    assert (env["out"] / "s1" / "incomplete").is_dir()


def stub_chain(env, worker=lambda m: {"pid": 1, "create_time": 1.0}):
    chain = M.ArmChain.__new__(M.ArmChain)
    chain.ops = type("O", (), {"worker_ident": staticmethod(worker), "rows": staticmethod(lambda p: []),
                               "wd": env["wd"]})()
    chain.specs = {"oc": arm_specs.OC}
    chain.policies, chain.pinned_by_arm, chain.pinned_shared = {"oc": "d" * 64}, {"oc": {}}, {}
    chain.frozen, chain.arms = FROZEN, {}
    chain.log = lambda *_: None
    return chain


LEG = dict(arm="oc", model=PICK1, session="s1", lang="python", seed_base=1001)
CTX = dict(worker={"pid": 1, "create_time": 1.0})
CLEAN = dict(attempt=1, log="x", cleanup_status={"survivors": [], "containers_remaining": [], "uncertain": False})


def test_a_hung_probe_cancelled_idle_is_a_client_timeout_incident(env):
    chain, leg, ctx, att = stub_chain(env), LEG, CTX, CLEAN
    got = chain.classify_incident(att, dict(state="cancelled", cancel_reason="idle"), {}, leg, env["wd"] / "none.jsonl", ctx)
    assert got["cause"] == "client_timeout"
    assert chain.classify_incident(att, dict(state="cancelled", cancel_reason="STOP"), {}, leg,
                                   env["wd"] / "none.jsonl", ctx) is None


def test_a_transport_failure_while_the_worker_is_gone_or_replaced_is_a_worker_crash(env):
    for worker in (lambda m: None, lambda m: {"pid": 2, "create_time": 9.0}):
        chain = stub_chain(env, worker)
        stamp = {"transport_abort": {"cause": "server_error", "gate": {"output_tokens_completed": 42}}}
        got = chain.classify_incident(CLEAN, dict(state="exited"), stamp, LEG, env["wd"] / "none.jsonl", CTX)
        assert got["cause"] == "worker_crash" and got["output_tokens"] == 42


def test_an_incident_with_uncertain_cleanup_or_invalid_partial_rows_refuses_instead_of_retrying(env):
    chain = stub_chain(env)
    stamp = {"transport_abort": {"cause": "server_error"}}
    dirty = dict(CLEAN, cleanup_status={"survivors": [{"pid": 1}], "containers_remaining": [], "uncertain": False})
    chain.listing = lambda *a: None
    with pytest.raises(co.ChainAbort, match="cleanup uncertain"):
        chain.classify_incident(dirty, dict(state="exited"), stamp, LEG, env["wd"] / "none.jsonl", CTX)


# ---------------------------------------------------------------- out-root, ops, A4, resume
def test_out_roots_default_to_m64_and_m64_smoke_and_refuse_other_chains(tmp_path):
    a = M.parse_args(SMOKE + ["--epoch-id", EPOCH])
    assert M.resolve_out_root(a, tmp_path) == tmp_path / "m64-smoke"
    real = M.parse_args(["chain", "--arms", "oc", "--probe-code-sha", "oc=" + "9" * 64, "--epoch-id", EPOCH])
    assert M.resolve_out_root(real, tmp_path) == tmp_path / "m64"
    bad = M.parse_args(SMOKE + ["--epoch-id", EPOCH, "--out-root", str(tmp_path / "m64")])
    with pytest.raises(M.Refused, match="smoke"):
        M.resolve_out_root(bad, tmp_path)
    for d in ("c147", "m63", "c147-smoke"):
        other = M.parse_args(SMOKE + ["--epoch-id", EPOCH, "--out-root", str(tmp_path / d / "x")])
        with pytest.raises(M.Refused, match="must not write"):
            M.resolve_out_root(other, tmp_path)
    rel = M.parse_args(SMOKE + ["--epoch-id", EPOCH, "--out-root", "rel/out"])
    assert M.resolve_out_root(rel, tmp_path).is_absolute()                       # P340


def test_the_real_ops_refuse_without_the_search_service_and_the_cache_reset_endpoint(tmp_path):
    from bench import arm_ops
    ops = arm_ops.M64ChainOps(REPO, tmp_path, tmp_path / "o.yaml", lambda m: None, out_root=tmp_path / "m64")
    for call in (ops.require_arm_ops, lambda: ops.search_restart({}), lambda: ops.reset_cache_session("m"),
                 lambda: ops.warmup("m")):
        with pytest.raises(arm_ops.ArmOpsUnavailable, match="search_restart"):
            call()


def test_a_stop_latch_exits_3_and_a_rerun_resumes_at_the_first_load_not_completed(env):
    (env["out"]).mkdir(parents=True, exist_ok=True)
    stop_after = {"n": 0}
    ops = env["ops"]
    orig = ops.unload

    def unload(model):
        stop_after["n"] += 1
        if stop_after["n"] == 1:                                     # the first load finished: latch STOP at the boundary
            (env["out"] / "STOP").write_text("x")
        return orig(model)

    ops.unload = unload
    assert run(env, SMOKE) == 3
    cj = chain_json(env)
    assert cj["completed_loads"] == [0] and cj["stop"]["where"]
    (env["out"] / "STOP").unlink()
    ops.unload = orig
    before = len(invocations(env))
    assert run(env, SMOKE) == 0
    cj2 = chain_json(env)
    assert cj2["completed_loads"] == [0, 1] and cj2["epoch_id"] == EPOCH
    s = json.loads((env["out"] / "schedule.json").read_text())
    assert len(invocations(env)) - before == len([leg for leg in ms.legs(s) if leg["load"] == 1])    # load 0 not redone
    assert [r for r in cj2["realized"]] == [ms.leg_key(leg) for leg in ms.legs(s)]
