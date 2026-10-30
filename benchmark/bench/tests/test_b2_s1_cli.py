"""B2 slice s1 (spec docs/specs/p426-b2-tg1-wave2.md v3.1, sections 2 / 6.1 / 6.2 / 6.3 / 6.7 / 7, C221, C235): the tg1 chain's
`--p426` CLI and refusals, the C221 changes for EVERY tg1 mode (required `--models`, the committed registry served verbatim,
no overlay generation, `--predictor` as an assertion, generic per-model predictions) and the P426 schedule (seeded order
without a later sort, s2 Go first, frozen schedule). Legacy tg1 / M63 behaviour is pinned by goldens recorded from the base
commit f1e47df9 BEFORE the code changed."""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import pytest

from bench import chain_core as core
from bench import chain_ops as co
from bench import schedules
from bench.tests.test_c147_chain_runner import (  # noqa: F401  (fixtures: env)
    C147, PICK1, PICK2, R, REPO, TIMERS, arg, chain_json, env, invocations, log_has, pinned_off_registry, run)
from bench.tests.test_p371_chain_core import FakeCampaign

X64 = "9" * 64
POLICY = "c" * 64                                    # the fake probe's own policy value
DATE = "Mon Jan 05 2026"
THIRD = "Some-Third-27B-test-model"
MODELS = f"{PICK1},{PICK2}"

# ---- legacy goldens, recorded from the base commit f1e47df9 (the unchanged tg1 chain) --------------------------------
# `schedules.tg1(mode, sessions, R.load_universe(), smoke=False, predictor=...)`: schedule_sha256 per argv shape, and the sha256
# of json.dumps([(session, model, lang, [invocation names ...]) ...]) = the item order the probe is launched with.
GOLDEN_M63_SHA = "3ed3936d8765d420808056735e4ccd487aa3891355b28f96648741d8749fe70f"      # chain s1 s2 reload --predictor mtp
GOLDEN_P223_SHA = "e8c981f37b04ee90e79f1f2b004da4c828031df7785324e7b2bb0601e754b1d7"     # chain s1 s2 reload (predictor off)
GOLDEN_PILOT_SHA = "41b40fd160b3e398b718a5241a4d39732c7aa00a6ddc577160d64f059b9d3143"    # pilot
GOLDEN_CHAIN_ORDER_SHA = "cd11c7dde1f4877707615831ff12f6e9a7802e66c098df782c6d58d4d7889a79"   # same for M63 and P223
GOLDEN_PILOT_ORDER_SHA = "0676a1695cbe09f24652ab2d7c3d73482bd43fb3617bcbce8ee1ac2f54fce88b"

# The serialized `tg1` ChainConfig of `chain s1 --probe-code-sha 99..9` (predictor off). OLD = the base commit's canonical JSON
# (sha256 0377014c0e4752cfcf3c64e2db5ec73fcb7b7d86cfe996a4058838ffc9a23d76); NEW (C221) adds exactly two schedule.params
# fields, `models` (the recorded --models list) and `generic_pred_s` (the recorded generic prediction default), and nothing
# else; the new sha256 is NEW_TG1_CONFIG_SHA (predictor mtp: old 601a6c6b280e76443961acf1adaf7d4049a70f8bbc07285c373b2acc97d273ba
# -> new d63c478da1e46927abe30bffa978b4770c371d045a33e6e168a08adfc9fc9fb3).
OLD_TG1_CONFIG_JSON = (
    '{"arm_switch_ops":[],"arms":[{"arm":"oc","arm_spec":"oc","label":"opencode-v2-web-tg1","probe":"benchmark/run_tg1_probe.py",'
    '"probe_data":["benchmark/opencode_plugins/toolbounds.js","benchmark/opencode_plugins/noretry.js",'
    '"benchmark/opencode_plugins/datefreeze.js","benchmark/opencode_bench_v2_web_tg1.json"]}],"config_id":"tg1",'
    '"contract_artifacts":[],"out_root_family":"c147","predictor":"off","resume_policy":"restart_load","schedule":{"builder":"tg1",'
    '"params":{"legs":{"reload":[["Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed","python"]],"s1":[["Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed",'
    '"python"],["Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed","go"],["Qwen3.8-27B-mlx-uniform-4bit","python"],["Qwen3.8-27B-mlx-uniform-4bit","go"]],'
    '"s2":[["Qwen3.8-27B-mlx-uniform-4bit","python"],["Qwen3.8-27B-mlx-uniform-4bit","go"],["Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed","python"],'
    '["Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed","go"]]},"pilot_n":5,"seeds":{"reload":1001,"s1":1001,"s2":2002},"smoke_full_n":2,'
    '"smoke_pilot_n":1}},"snapshot_complete_required":false,"transport_policy":"abort_restart"}')
NEW_TG1_CONFIG_SHA = "c57be658fd55f04c971ea9224f2cbecfdbaf4ae73c7f197b65be735da839c7f7"      # --models PICK1,PICK2, predictor off

LEGACY_CHAIN = ["chain", "s1", "s2", "reload", "--probe-code-sha", X64, "--models", MODELS]
P426_ARGV = ["chain", "s1", "--p426", "--models", PICK1, "--predictor", "off", "--probe-code-sha", X64, "--policy-sha", POLICY,
             "--frozen-prompt-date", DATE, "--campaign-core", "campaign-1", "--frozen-record", "/x/v8.json"]


def sha(obj):
    return hashlib.sha256(json.dumps(obj).encode()).hexdigest()


def order_of(sched):
    return [(b["session"], b["model"], leg["lang"], [i["names"] for i in leg["invocations"]])
            for b in sched["blocks"] for leg in b["legs"]]


def p426_order(names, lang, seed):
    return random.Random(seed).sample(sorted(names[lang]), len(names[lang]))


def with_out(tmp_path, argv, name="leg"):
    return list(argv) + ["--out-root", str(tmp_path / "wave2" / name)]


def refused(argv, **kw):
    with pytest.raises(SystemExit) as e:
        R.main(argv, **kw)
    assert e.value.code == 2
    return str(e.value)


def registry(path, models, draft=None):
    """A served-registry stand-in: `models` = names; `draft` = {name: {key: value}} extra keys per entry."""
    import yaml
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    entries = [dict(name=m, hf_path=f"caslca/{m}", **(draft or {}).get(m, {})) for m in models]
    Path(path).write_text(yaml.safe_dump({"mlx_port": 8091, "models": entries}, sort_keys=False))
    return Path(path)


MTP_KEYS = dict(draft_kind="mtp", draft_model="caslca/x-mtp-drafter", mtp_verify_scan="joint_v1")



# =============================================================================================== legacy goldens
@pytest.mark.parametrize("sessions,predictor,schedule_sha", [
    (["s1", "s2", "reload"], "mtp", GOLDEN_M63_SHA), (["s1", "s2", "reload"], "off", GOLDEN_P223_SHA)])
def test_legacy_m63_and_p223_schedule_and_item_order_are_byte_identical_to_the_base_commit(sessions, predictor, schedule_sha):
    names = R.load_universe()
    sched = schedules.tg1("chain", sessions, names, smoke=False, predictor=predictor, picks=(PICK1, PICK2))
    assert schedules.schedule_sha256(sched) == schedule_sha
    assert sha(order_of(sched)) == GOLDEN_CHAIN_ORDER_SHA
    # the same through the runner's own entry, from the (now required) --models list
    a = R.parse_args(LEGACY_CHAIN + ["--predictor", predictor])
    via_runner = schedules.tg1(a.mode, a.sessions, names, smoke=False, predictor=a.predictor, picks=tuple(a.models))
    assert schedules.schedule_sha256(via_runner) == schedule_sha


def test_legacy_pilot_schedule_is_byte_identical_to_the_base_commit():
    sched = schedules.tg1("pilot", [], R.load_universe(), smoke=False, predictor="off", picks=(PICK1, PICK2))
    assert schedules.schedule_sha256(sched) == GOLDEN_PILOT_SHA and sha(order_of(sched)) == GOLDEN_PILOT_ORDER_SHA


def test_legacy_item_order_is_still_sorted_and_the_pilot_is_a_sorted_draw():
    names = R.load_universe()
    leg = schedules.tg1("chain", ["s1"], names, picks=(PICK1, PICK2))["blocks"][0]["legs"][0]
    assert leg["full_names"] == sorted(names["python"])
    assert leg["pilot_names"] == sorted(random.Random(1001).sample(sorted(names["python"]), 5))


def test_the_tg1_chain_config_differs_from_the_base_only_in_the_c221_fields():
    cfg = R.tg1_config(R.parse_args(["chain", "s1", "--probe-code-sha", X64, "--models", MODELS]))
    new = cfg.as_dict()
    params = new["schedule"]["params"]
    assert params["models"] == [PICK1, PICK2] and params["generic_pred_s"] == core.GENERIC_PRED_S
    stripped = json.loads(json.dumps(new))
    for k in ("models", "generic_pred_s"):
        stripped["schedule"]["params"].pop(k)
    assert json.dumps(stripped, sort_keys=True, separators=(",", ":")) == OLD_TG1_CONFIG_JSON
    assert cfg.sha256() == NEW_TG1_CONFIG_SHA
    assert (cfg.config_id, cfg.transport_policy, cfg.out_root_family) == ("tg1", "abort_restart", "c147")


def test_the_hard_coded_pick_pair_is_gone_from_the_runner_and_the_tg1_prediction_table():
    for name in ("PICK1", "PICK2", "LEGS", "PRED_S"):
        assert not hasattr(R, name), name
    names = R.load_universe()
    with pytest.raises(TypeError):                    # picks is required: no default pair
        schedules.tg1("chain", ["s1"], names)


# =============================================================================================== --models (C221 / 6.1)
@pytest.mark.parametrize("argv", [["pilot"], ["chain", "--probe-code-sha", X64], ["chain", "s1", "--probe-code-sha", X64, "--predictor", "mtp"],
                                  ["chain", "s1", "--probe-code-sha", X64, "--smoke"]])
def test_models_is_required_in_every_tg1_mode(argv):
    with pytest.raises(SystemExit) as e:
        R.parse_args(argv)
    assert e.value.code == 2


@pytest.mark.parametrize("value,expect", [(PICK1, [PICK1]), (MODELS, [PICK1, PICK2]), (f"{PICK1},{PICK2},{THIRD}", [PICK1, PICK2, THIRD])])
def test_models_takes_one_two_or_three_names_in_the_given_order(value, expect):
    for argv in (["pilot", "--models", value], ["chain", "s1", "--probe-code-sha", X64, "--models", value]):
        assert R.parse_args(argv).models == expect


@pytest.mark.parametrize("value", ["", ",", f"{PICK1},", f",{PICK1}", f"{PICK1},,{PICK2}", f"{PICK1},{PICK1}", f"{PICK1},{PICK2},{PICK1}", " ",
                                   f"{PICK1}, {PICK2}"])
def test_models_refuses_empty_and_duplicate_names(value):
    assert R.parse_args(["pilot", "--models", PICK1]).models == [PICK1]                   # control: the flag exists
    with pytest.raises(SystemExit) as e:
        R.parse_args(["pilot", "--models", value])
    assert e.value.code == 2


def test_an_unknown_model_is_refused_before_anything_is_written(env, tmp_path):
    reg = registry(tmp_path / "reg.yaml", [PICK1])
    msg = refused(["chain", "s1", "--probe-code-sha", X64, "--models", f"{PICK1},{PICK2}", "--out-root", str(env["out"]),
                   "--frozen-prompt-date", DATE], ops=env["ops"], registry=reg)
    assert "REFUSED" in msg and PICK2 in msg and not env["out"].exists()


def test_models_are_recorded_in_the_chain_config_and_chain_json(env):
    assert run(env, ["chain", "s1", "--probe-code-sha", X64, "--models", PICK1], registry=pinned_off_registry()) == 0
    cj = chain_json(env)
    assert cj["chain_config"]["schedule"]["params"]["models"] == [PICK1]
    assert {json.loads(ln)["argv"][json.loads(ln)["argv"].index("--model") + 1] for ln in
            (env["ops"].state / "invocations.jsonl").read_text().splitlines()} == {PICK1}


# ---- the generic schedule: 1 / 2 / 3 models (legacy two-pick semantics) ----------------------------------------------
@pytest.mark.parametrize("picks", [(PICK1,), (PICK1, PICK2), (PICK1, PICK2, THIRD)])
def test_generic_schedule_s1_in_given_order_s2_reversed_reload_the_first(picks):
    names = R.load_universe()
    sched = schedules.tg1("chain", ["s1", "s2", "reload"], names, picks=picks)
    seen = [(b["session"], b["model"], [leg["lang"] for leg in b["legs"]]) for b in sched["blocks"]]
    want = ([("s1", m, ["python", "go"]) for m in picks] + [("s2", m, ["python", "go"]) for m in reversed(picks)]
            + [("reload", picks[0], ["python"])])
    assert seen == want
    assert [b["seed_base"] for b in sched["blocks"]] == [1001] * len(picks) + [2002] * len(picks) + [1001]
    assert sched["picks"] == list(picks)


def test_the_runner_schedule_wrapper_takes_the_models_list():
    blocks = R.schedule("chain", ["s1", "s2"], R.load_universe(), "/o", models=[PICK1, PICK2, THIRD])
    assert [(b["session"], b["model"]) for b in blocks] == [("s1", PICK1), ("s1", PICK2), ("s1", THIRD),
                                                              ("s2", THIRD), ("s2", PICK2), ("s2", PICK1)]
    assert blocks[0]["legs"][0]["out"] == f"/o/s1/{PICK1}.s1.opencode_python.jsonl"


# =============================================================================================== C221 serving
def test_the_served_registry_file_itself_is_the_router_config_in_every_tg1_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    monkeypatch.delenv("C147_OVERLAY", raising=False)
    monkeypatch.setattr(co, "make_overlay", lambda *a, **k: pytest.fail("an overlay was generated"))

    class Stop(Exception):
        pass

    real = co.ChainOps

    def build(argv, **kw):
        built = {}

        def capture(*a, **k):
            built["ops"] = real(*a, **k)
            raise Stop
        monkeypatch.setattr(R.co, "ChainOps", capture)
        with pytest.raises(Stop):
            R.main(argv, **kw)
        return built["ops"]

    base = ["chain", "s1", "--probe-code-sha", X64, "--models", MODELS]
    # an OFF registry (the pinned copy of the committed OFF state): served verbatim, the default OFF out-root family
    off = pinned_off_registry()
    o = build(base, registry=off)
    assert o.predictor == "off" and Path(o.overlay) == off
    assert o.env_base()["MLX_SERVE_CONFIG"] == str(off) and o.a4_log_dir == tmp_path / "c147"
    # an arm worktree's registry that ships the entries' MTP keys: served verbatim, the ON out-root family
    reg = registry(tmp_path / "arm/main_models.yaml", [PICK1, PICK2], {PICK1: MTP_KEYS, PICK2: MTP_KEYS})
    o = build(base + ["--predictor", "mtp"], registry=reg)
    assert o.predictor == "mtp" and Path(o.overlay) == reg and o.env_base()["MLX_SERVE_CONFIG"] == str(reg)
    assert o.a4_log_dir == tmp_path / "m63" and o.tmpdir == tmp_path / "m63/tmp"
    assert not list(tmp_path.glob("**/overlay_*"))


def test_no_overlay_is_generated_and_ensure_overlay_is_not_called(env, monkeypatch):
    monkeypatch.setattr(co, "make_overlay", lambda *a, **k: pytest.fail("an overlay was generated"))
    assert run(env, ["chain", "s1", "--probe-code-sha", X64, "--models", MODELS], registry=pinned_off_registry()) == 0
    assert env["ops"].names("ensure_overlay") == []
    assert not list(env["wd"].glob("**/overlay*"))
    assert chain_json(env)["pinned"]["registry_sha256"] == "a" * 64            # the served file's sha (FakeOps.overlay_sha)


@pytest.mark.parametrize("predictor", ["off", "mtp"])
def test_the_c147_overlay_environment_override_is_refused_in_every_mode(tmp_path, monkeypatch, predictor):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    monkeypatch.setenv("C147_OVERLAY", str(tmp_path / "anything.yaml"))
    monkeypatch.setattr(R.co, "ChainOps", lambda *a, **k: pytest.fail("ChainOps built"))
    msg = refused(["chain", "s1", "--probe-code-sha", X64, "--models", MODELS, "--predictor", predictor])
    assert "REFUSED" in msg and "C147_OVERLAY" in msg
    assert not (tmp_path / ("m63" if predictor == "mtp" else "c147")).exists()


# ---- --predictor as an assertion of the committed entry ----------------------------------------------------------
@pytest.mark.parametrize("predictor,draft,ok", [
    ("off", {}, True),
    ("off", {PICK1: dict(draft_kind="mtp")}, False),
    ("off", {PICK1: dict(draft_model="caslca/x-mtp-drafter")}, False),
    ("off", {PICK1: dict(mtp_verify_scan="joint_v1")}, False),
    ("off", {PICK1: MTP_KEYS}, False),
    ("mtp", {PICK1: MTP_KEYS}, True),
    ("mtp", {}, False),
    ("mtp", {PICK1: dict(draft_kind="mtp", draft_model="caslca/x")}, False),                     # two of three keys
    ("mtp", {PICK1: dict(draft_model="caslca/x", mtp_verify_scan="joint_v1")}, False),
    ("mtp", {PICK1: dict(MTP_KEYS, draft_kind="suffix")}, False),
])
def test_predictor_is_an_assertion_of_the_served_entry_all_three_keys_or_none(env, tmp_path, predictor, draft, ok):
    reg = registry(tmp_path / "reg.yaml", [PICK1], draft)
    env["out"] = env["wd"] / ("m63" if predictor == "mtp" else "c147")                # an ON arm never writes into c147
    argv = ["chain", "s1", "--probe-code-sha", X64, "--models", PICK1, "--predictor", predictor]
    if ok:
        env["ops"].registry = reg
        assert run(env, argv, registry=reg, extra_env={"FAKE_SERVED_REGISTRY": str(reg)}) == 0      # the probe records the served draft kind
        return
    msg = refused(argv + ["--out-root", str(env["out"]), "--frozen-prompt-date", DATE], ops=env["ops"], registry=reg)
    assert "REFUSED" in msg and "--predictor" in msg and not env["out"].exists()


def test_the_predictor_assertion_covers_every_listed_model(env, tmp_path):
    reg = registry(tmp_path / "reg.yaml", [PICK1, PICK2], {PICK1: MTP_KEYS})                   # PICK2 lacks the keys
    env["out"] = env["wd"] / "m63"
    msg = refused(["chain", "s1", "--probe-code-sha", X64, "--models", MODELS, "--predictor", "mtp", "--out-root", str(env["out"]),
                   "--frozen-prompt-date", DATE], ops=env["ops"], registry=reg)
    assert PICK2 in msg and not env["out"].exists()


# ---- generic per-model predictions (pilot mean, else the recorded default) -----------------------------------------
def test_tg1_predictions_have_no_per_model_table_and_fall_back_to_the_recorded_default(env):
    ops = env["ops"]
    chain = R.Chain(R.parse_args(["chain", "s1", "--probe-code-sha", X64, "--models", f"{PICK1},{THIRD}"]), ops, R.Timers(**TIMERS),
                    lambda m: None, R.load_universe(), env["out"], None, FakeCampaign())
    assert chain.pred == {}
    assert chain.prediction_s(("python", THIRD), []) == core.GENERIC_PRED_S
    assert chain.prediction_s(("go", PICK1), [100.0, 200.0]) == core.GENERIC_PRED_S                      # < 5 rows: the default
    assert chain.prediction_s(("go", PICK1), [100.0, 200.0, 300.0, 400.0, 500.0, 900.0]) == 300.0         # the pilot mean (first 5)
    chain.explicit_pred[("go", PICK1)] = 42.0
    assert chain.prediction_s(("go", PICK1), [1.0] * 9) == 42.0


# =============================================================================================== P426 schedule (7)
def test_p426_order_is_the_seeded_sample_of_the_sorted_pool_with_no_later_sort():
    names = R.load_universe()
    sched = schedules.tg1("chain", ["s1", "s2"], names, picks=(PICK1,), p426=True)
    legs = {(b["session"], leg["lang"]): leg for b in sched["blocks"] for leg in b["legs"]}
    for session, seed in (("s1", 1001), ("s2", 2002)):
        for lang in ("python", "go"):
            want = p426_order(names, lang, seed)
            leg = legs[(session, lang)]
            assert want != sorted(want)                                      # the check is not vacuous
            assert leg["full_names"] == want and leg["seed_base"] == seed
            assert [n for inv in leg["invocations"] for n in inv["names"]] == want
            assert [e for inv in leg["invocations"] for e in inv["expect"]] == [f"{lang}/{n}" for n in want]
    assert legs[("s1", "python")]["full_names"] != legs[("s2", "python")]["full_names"]      # distinct replicates


def test_p426_in_load_pilot_phase_is_the_first_five_of_the_legs_order_then_the_rest_in_order():
    names = R.load_universe()
    sched = schedules.tg1("chain", ["s1", "s2"], names, picks=(PICK1,), p426=True)
    for block in sched["blocks"]:
        first, second = block["legs"]
        want = p426_order(names, first["lang"], block["seed_base"])
        assert [(i["phase"], i["names"], i["limit"]) for i in first["invocations"]] == [
            ("pilot", want[:5], 5), ("full", want[5:], None)]
        assert first["pilot_names"] == want[:5]
        assert [(i["phase"], i["limit"]) for i in second["invocations"]] == [("full", None)]


def test_p426_s2_runs_go_first_and_s1_python_first():
    sched = schedules.tg1("chain", ["s1", "s2", "reload"], R.load_universe(), picks=(PICK1,), p426=True)
    assert [(b["session"], [leg["lang"] for leg in b["legs"]]) for b in sched["blocks"]] == [
        ("s1", ["python", "go"]), ("s2", ["go", "python"]), ("reload", ["python"])]


def test_p426_pilot_and_reload_are_the_first_five_of_s1s_python_order():
    names = R.load_universe()
    want = p426_order(names, "python", 1001)[:5]
    pilot = schedules.tg1("pilot", [], names, picks=(PICK1,), p426=True)["blocks"][0]["legs"][0]
    assert pilot["lang"] == "python" and pilot["seed_base"] == 1001
    assert [(i["phase"], i["names"], i["limit"]) for i in pilot["invocations"]] == [("pilot", want, 5)]
    reload_ = schedules.tg1("chain", ["reload"], names, picks=(PICK1,), p426=True)["blocks"][0]["legs"][0]
    assert reload_["full_names"] == want == reload_["pilot_names"]
    assert [(i["phase"], i["names"]) for i in reload_["invocations"]] == [("pilot", want)]


def test_the_p426_schedule_is_deterministic_and_its_sha_differs_from_the_legacy_one():
    names = R.load_universe()
    a = schedules.tg1("chain", ["s1"], names, picks=(PICK1,), p426=True)
    assert schedules.schedule_sha256(a) == schedules.schedule_sha256(schedules.tg1("chain", ["s1"], names, picks=(PICK1,), p426=True))
    assert schedules.schedule_sha256(a) != schedules.schedule_sha256(schedules.tg1("chain", ["s1"], names, picks=(PICK1,)))


# =============================================================================================== P426 mode (2)
def test_p426_selects_its_own_chain_config():
    a = R.parse_args(P426_ARGV + ["--out-root", "/x/leg"])
    assert a.p426 is True and a.models == [PICK1]
    cfg = R.tg1_config(a)
    legacy = R.tg1_config(R.parse_args(["chain", "s1", "--probe-code-sha", X64, "--models", PICK1]))
    assert cfg.config_id == "tg1-p426" and legacy.config_id == "tg1" and cfg.sha256() != legacy.sha256()
    assert cfg.schedule["builder"] == "tg1" and cfg.schedule["params"]["models"] == [PICK1] and cfg.schedule["params"]["p426"] is True
    assert cfg.schedule["params"]["legs"]["s2"] == [[PICK1, "go"], [PICK1, "python"]]
    assert cfg.transport_policy == "p426_continue" and cfg.predictor == "off"       # s4: the P426 config runs `p426_continue`
    assert legacy.transport_policy == "abort_restart"
    mtp = R.tg1_config(R.parse_args(P426_ARGV + ["--out-root", "/x/leg", "--predictor", "mtp"]))
    assert mtp.out_root_family == "m63" and mtp.sha256() != cfg.sha256()


REQUIRED = ["--models", "--out-root", "--campaign-core", "--frozen-prompt-date", "--probe-code-sha", "--policy-sha", "--frozen-record"]


@pytest.mark.parametrize("flag", REQUIRED)
@pytest.mark.parametrize("mode", ["chain", "pilot"])
def test_p426_refuses_a_missing_required_flag(flag, mode):
    argv = ([mode] + (["s1"] if mode == "chain" else []) + P426_ARGV[2:] + ["--out-root", "/x/leg"])
    assert R.parse_args(argv).p426 is True                                      # the complete argv parses
    i = argv.index(flag)
    with pytest.raises(SystemExit) as e:
        R.parse_args(argv[:i] + argv[i + 2:])
    assert e.value.code == 2


@pytest.mark.parametrize("extra", [["--smoke"], ["--pred-s", f"python:{PICK1}=100"], ["--generation-sha", "a" * 64],
                                   ["--frozen-date-from", "/x/chain.json"]])
def test_p426_refuses_its_excluded_flags(extra):
    assert R.parse_args(P426_ARGV + ["--out-root", "/x/leg"]).p426 is True               # control: the complete argv parses
    with pytest.raises(SystemExit) as e:
        R.parse_args(P426_ARGV + ["--out-root", "/x/leg"] + extra)
    assert e.value.code == 2


def test_p426_refuses_more_than_one_model():
    assert R.parse_args(P426_ARGV + ["--out-root", "/x/leg"]).models == [PICK1]          # control: one model parses
    argv = [x if x != PICK1 else MODELS for x in P426_ARGV]
    with pytest.raises(SystemExit) as e:
        R.parse_args(argv + ["--out-root", "/x/leg"])
    assert e.value.code == 2


@pytest.mark.parametrize("sessions", [[], ["s1", "s2"], ["s1", "reload"]])
def test_p426_chain_runs_exactly_one_session_leg(sessions):
    argv = ["chain"] + sessions + P426_ARGV[2:] + ["--out-root", "/x/leg"]
    assert R.parse_args(["chain", "s1"] + P426_ARGV[2:] + ["--out-root", "/x/leg"]).sessions == ["s1"]     # control: one session
    with pytest.raises(SystemExit) as e:
        R.parse_args(argv)
    assert e.value.code == 2


def test_the_frozen_record_flag_is_only_for_p426():
    assert R.parse_args(P426_ARGV + ["--out-root", "/x/leg"]).frozen_record == "/x/v8.json"      # control: accepted with --p426
    with pytest.raises(SystemExit) as e:
        R.parse_args(["chain", "s1", "--probe-code-sha", X64, "--models", PICK1, "--frozen-record", "/x/v8.json"])
    assert e.value.code == 2


def test_p426_refuses_the_overlay_environment_override_before_any_write(env, monkeypatch):
    monkeypatch.setenv("C147_OVERLAY", "/anywhere.yaml")
    msg = refused(P426_ARGV + ["--out-root", str(env["out"])], ops=env["ops"])
    assert "C147_OVERLAY" in msg and not env["out"].exists()


def p426_leg(env, argv):
    """`argv` with a valid sealed frozen record for its mode and an attempt-named out-root (spec 2 / 16.1)."""
    from bench.tests import b2_frozen_support as S
    v8, am = S.record_dir(env["wd"])
    argv = list(argv)
    argv[argv.index("--frozen-record") + 1] = str(v8 if argv[0] == "pilot" else am)
    env["out"] = env["wd"] / "p426/wave2/tg1-p426-off-s1.a1"
    return argv


def test_p426_refuses_an_out_root_that_exists_and_leaves_it_untouched(env):
    argv = p426_leg(env, P426_ARGV)
    env["out"].mkdir(parents=True)
    (env["out"] / "keep.txt").write_text("x")
    msg = refused(argv + ["--out-root", str(env["out"])], ops=env["ops"])
    assert "REFUSED" in msg and "exists" in msg
    assert sorted(p.name for p in env["out"].iterdir()) == ["keep.txt"]


def test_p426_refuses_an_unknown_model_and_a_predictor_mismatch(env, tmp_path):
    argv = p426_leg(env, P426_ARGV)
    reg = registry(tmp_path / "reg.yaml", [PICK2])
    assert "REFUSED" in refused(argv + ["--out-root", str(env["out"])], ops=env["ops"], registry=reg)
    reg = registry(tmp_path / "reg2.yaml", [PICK1], {PICK1: MTP_KEYS})
    assert "--predictor" in refused(argv + ["--out-root", str(env["out"])], ops=env["ops"], registry=reg)
    assert not env["out"].exists()


# ---- P426 end to end against the fake probe: the frozen schedule reaches the probe as planned -----------------------------
def run_p426(env, session, **kw):
    argv = [x for x in P426_ARGV]
    argv[1] = session
    return run(env, p426_leg(env, argv), campaign=FakeCampaign(), **kw)


def probe_calls(env):
    return [(arg(i["argv"], "--lang"), arg(i["argv"], "--items").split(","), arg(i["argv"], "--limit")) for i in invocations(env)]


def test_the_legacy_chain_does_not_freeze_a_schedule(env):
    assert run(env, ["chain", "s1", "--probe-code-sha", X64, "--models", MODELS], registry=pinned_off_registry()) == 0
    assert "schedule_sha256" not in chain_json(env) and not (env["out"] / "schedule.json").exists()
    names = R.load_universe(env["uni"])
    assert probe_calls(env)[0] == ("python", sorted(random.Random(1001).sample(sorted(names["python"]), 5)), "5")


def test_a_tg1_p426_chain_config_must_be_the_one_model_p426_tg1_shape():
    from bench import run_config as rcfg
    arm = R.tg1_config(R.parse_args(["pilot", "--models", PICK1])).arms
    good = dict(builder="tg1", params=dict(p426=True, models=[PICK1]))

    def make(schedule, config_id=rcfg.P426_CONFIG_ID):
        return rcfg.ChainConfig(config_id=config_id, arms=arm, schedule=schedule, out_root_family="c147", predictor="off",
                                arm_switch_ops=(), transport_policy="abort_restart", resume_policy="restart_load",
                                snapshot_complete_required=False)
    assert make(good).config_id == "tg1-p426"
    for bad in (dict(builder="tg1", params=dict(models=[PICK1])), dict(builder="tg1", params=dict(p426=True, models=[PICK1, PICK2])),
                dict(builder="tg1", params=dict(p426=True, models=[])), dict(builder="blocks", params=dict(p426=True, models=[PICK1]))):
        with pytest.raises(ValueError, match="tg1-p426"):
            make(bad)
    assert make(dict(builder="tg1", params=dict(models=[PICK1, PICK2])), config_id="tg1").config_id == "tg1"       # legacy: any list
