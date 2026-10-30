"""P426 B2 frozen tests, s1 cli (spec v3.2 §2 refusals, C221 for every tg1 mode, legacy goldens, §6.1-6.3, §6.7, §16.1
`--frozen-record`, §16 refusal format).

Classes: [FIX] reproduces a failure the spec fixes; [INV] preserves an invariant; [NEW] exercises new behaviour.
Driven through `run_tg1_chain.main(argv, ops=<FakeOps>, timers=…, log_out=…)` and `parse_args` / `tg1_config`, with the existing
fakes and the served registry as `ops.overlay` (§3). A refusal (§16) prints one `REFUSED: <reason>` line naming the offending
flag, file or field, and exits 2."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from bench.tests import b2_frozen_support as S

R = S.runner_module()
PAIR = f"{S.MODEL},{S.MODEL2}"
CAMPAIGN = "campaign-p426"


def leg_root(tmp_path, leg="tg1-p426-off-pilot.a1"):
    return tmp_path / "p426/wave2" / leg


def p426_argv(tmp_path, mode=("pilot",), record=None, **drop_or_set):
    """§6.7's common flags with the values of a scratch leg; `name=None` drops a flag."""
    if record is None:
        record = S.record_dir(tmp_path / "rec")[0]                      # a valid v8 base (pilot)
    flags = {"--models": S.MODEL, "--predictor": "off", "--out-root": str(leg_root(tmp_path)), "--probe-code-sha": S.HEX9,
             "--policy-sha": "c" * 64, "--frozen-prompt-date": S.EPOCH_DATE, "--campaign-core": CAMPAIGN,
             "--frozen-record": str(record)}
    flags.update(drop_or_set)
    argv = list(mode) + ["--p426"]
    for k, v in flags.items():
        if v is not None:
            argv += [k, v]
    return argv                                      # C238: no pair key, no `--hmac-fd`


def refusal(tmp_path, monkeypatch, argv, env_extra=None):
    env = S.chain_env(tmp_path, monkeypatch, registry=S.registry_text((S.MODEL,)))
    for k, v in (env_extra or {}).items():
        monkeypatch.setenv(k, v)
    try:                                            # 1h: the tag resolves (fake campaign), so the refusal under test is seen
        rc, text = S.main_refusal(argv, env["ops"], campaign=S.fake_campaign(CAMPAIGN))
    finally:
        env["ops"].cancel()
    return rc, text, env


def assert_refused_for(rc, text, *names, env=None):
    refused = [ln for ln in text.splitlines() if "REFUSED: " in ln]
    assert rc == 2 and refused, text[-2000:]
    for n in names:
        assert any(n in ln for ln in refused), (n, refused)
    if env is not None:
        assert not env["ops"].names("start_router") and not S.invocations(env)


# ------------------------------------------------------------------------------------------------ §2 refusals (P426 mode)
@pytest.mark.parametrize("extra,name", [
    (["--smoke"], "--smoke"),
    (["--pred-s", f"python:{S.MODEL}=1"], "--pred-s"),
    (["--generation-sha", "d" * 64], "--generation-sha"),
    (["--frozen-date-from", "/nonexistent/chain.json"], "--frozen-date-from"),
])
def test_new_p426_refuses_each_retired_flag_before_anything_is_written(tmp_path, monkeypatch, extra, name):
    over = {"--frozen-prompt-date": None} if name == "--frozen-date-from" else {}
    rc, text, env = refusal(tmp_path, monkeypatch, p426_argv(tmp_path, **over) + extra)
    assert_refused_for(rc, text, name, env=env)
    assert not leg_root(tmp_path).exists()


def test_new_p426_refuses_the_c147_overlay_environment_override(tmp_path, monkeypatch):
    rc, text, env = refusal(tmp_path, monkeypatch, p426_argv(tmp_path), env_extra={"C147_OVERLAY": str(tmp_path / "ov.yaml")})
    assert_refused_for(rc, text, "C147_OVERLAY", env=env)
    assert not leg_root(tmp_path).exists()


@pytest.mark.parametrize("missing", ["--models", "--out-root", "--campaign-core", "--frozen-prompt-date", "--probe-code-sha",
                                     "--policy-sha", "--frozen-record"])
def test_new_p426_refuses_a_missing_required_flag(tmp_path, monkeypatch, missing):
    rc, text, env = refusal(tmp_path, monkeypatch, p426_argv(tmp_path, **{missing: None}))
    assert_refused_for(rc, text, missing, env=env)


def test_new_p426_refuses_an_out_root_that_exists(tmp_path, monkeypatch):
    leg_root(tmp_path).mkdir(parents=True)
    rc, text, env = refusal(tmp_path, monkeypatch, p426_argv(tmp_path))
    assert_refused_for(rc, text, "--out-root", env=env)
    assert list(leg_root(tmp_path).iterdir()) == []


@pytest.mark.parametrize("name", ["tg1-p426-off-pilot", "tg1-p426-off-pilot.a", "tg1-p426-off-pilot.b1", "tg1-p426-off-pilot.a0x"])
def test_new_p426_requires_an_attempt_out_root_named_leg_dot_a_n(tmp_path, monkeypatch, name):
    """[d2] §16.1: the `p426_dnf` record's `attempt` is the `n` of the out-root's name `<leg>.a<n>`, which P426 mode requires."""
    rc, text, env = refusal(tmp_path, monkeypatch, p426_argv(tmp_path, **{"--out-root": str(tmp_path / "p426/wave2" / name)}))
    assert_refused_for(rc, text, "--out-root", env=env)
    assert not (tmp_path / "p426/wave2" / name).exists()


def test_new_p426_refuses_more_than_one_model(tmp_path, monkeypatch):
    rc, text, env = refusal(tmp_path, monkeypatch, p426_argv(tmp_path, **{"--models": PAIR}))
    assert_refused_for(rc, text, "--models", env=env)
    assert not leg_root(tmp_path).exists()


@pytest.mark.parametrize("inject", ["reconcile-mismatch", "stall-kill"])
def test_new_rehearsal_injections_refuse_without_rehearsal(tmp_path, monkeypatch, inject):
    v8, am = S.record_dir(tmp_path / "rec")
    argv = p426_argv(tmp_path, mode=("chain", "s1"), record=am) + ["--inject", inject]
    rc, text, env = refusal(tmp_path, monkeypatch, argv)
    assert_refused_for(rc, text, "--rehearsal", env=env)


# ------------------------------------------------------------------------------------------------ §16.1 --frozen-record
def _kind_cases(tmp_path):
    v8, am = S.record_dir(tmp_path / "rec")
    reh = S.write_record(tmp_path / "rec2" / "rehearsal.json", S.rehearsal_manifest(tmp_path / "p426/rehearsal/x"))
    return dict(v8=v8, am=am, reh=reh)


@pytest.mark.parametrize("mode,which", [
    (("pilot",), "reh"),                        # legs 1-10 never accept the rehearsal manifest
    (("pilot",), "am"),                         # pilot -> p426_v8_base
    (("chain", "s1"), "v8"),                    # chain -> p426_timeout_amendment
    (("chain", "s1"), "reh"),
    (("chain", "s1", "--rehearsal"), "v8"),     # --rehearsal -> p426_rehearsal
])
def test_new_a_record_of_the_wrong_kind_for_the_mode_refuses(tmp_path, monkeypatch, mode, which):
    rec = _kind_cases(tmp_path)[which]
    # post-reveal 3e: a rehearsal leg's out-root lies under `$STACK_WORKDIR/p426/rehearsal/` (§1), so the record's kind is
    # what refuses it (under `p426/wave2` the out-root rule refuses first)
    out = (tmp_path / "p426/rehearsal/tg1-p426-rehearsal-off.a1") if "--rehearsal" in mode else leg_root(tmp_path)
    rc, text, env = refusal(tmp_path, monkeypatch, p426_argv(tmp_path, mode=mode, record=rec, **{"--out-root": str(out)}))
    assert_refused_for(rc, text, env=env)
    assert any(("kind" in ln or rec.name in ln or "--frozen-record" in ln) for ln in text.splitlines() if "REFUSED: " in ln)
    assert not out.exists()


def test_new_a_record_with_a_bad_self_hash_refuses(tmp_path, monkeypatch):
    doc = S.v8_base()
    doc["pilot_deadline_s"] = 1.0                                        # changed after hashing
    bad = S.write_record(tmp_path / "bad" / "v8_base.json", doc)
    rc, text, env = refusal(tmp_path, monkeypatch, p426_argv(tmp_path, record=bad))
    assert_refused_for(rc, text, env=env)
    assert any(("sha256" in ln or bad.name in ln or "--frozen-record" in ln) for ln in text.splitlines() if "REFUSED: " in ln)


def test_new_a_missing_record_file_refuses(tmp_path, monkeypatch):
    rc, text, env = refusal(tmp_path, monkeypatch, p426_argv(tmp_path, record=tmp_path / "nope" / "v8_base.json"))
    assert_refused_for(rc, text, env=env)
    assert any(("v8_base.json" in ln or "--frozen-record" in ln) for ln in text.splitlines() if "REFUSED: " in ln)


def test_new_an_amendment_whose_v8_base_differs_from_its_sibling_refuses(tmp_path, monkeypatch):
    v8, _ = S.record_dir(tmp_path / "rec")
    other = S.write_record(tmp_path / "rec" / "other.json", S.v8_base(pilot_deadline_s=5.0))
    am = S.write_record(tmp_path / "rec" / "amendment_other.json", S.timeout_amendment(other))
    rc, text, env = refusal(tmp_path, monkeypatch, p426_argv(tmp_path, mode=("chain", "s1"), record=am))
    assert_refused_for(rc, text, env=env)
    assert any(("v8_base" in ln or am.name in ln) for ln in text.splitlines() if "REFUSED: " in ln)


def test_new_the_p426_chain_config_is_its_own_flat_config(tmp_path):
    a = R.parse_args(p426_argv(tmp_path, mode=("chain", "s1"), record=S.record_dir(tmp_path / "rec")[1]))
    cfg = R.tg1_config(a)
    assert cfg.config_id == "tg1-p426" and cfg.transport_policy == "p426_continue"
    assert cfg.sha256() != R.tg1_config(R.parse_args(["chain", "s1", "--probe-code-sha", S.HEX9, "--models", S.MODEL])).sha256()


# ------------------------------------------------------------------------------------------------ C221, every tg1 mode
@pytest.mark.parametrize("argv", [["pilot"], ["chain", "s1", "--probe-code-sha", S.HEX9]])
def test_fix_models_is_required_in_every_tg1_mode(tmp_path, monkeypatch, argv):
    rc, text, env = refusal(tmp_path, monkeypatch, argv + ["--frozen-prompt-date", S.EPOCH_DATE,
                                                           "--out-root", str(tmp_path / "c147")])
    assert_refused_for(rc, text, "--models", env=env)


@pytest.mark.parametrize("models", [f"{S.MODEL},{S.MODEL}", f"{S.MODEL},", f",{S.MODEL}", ""])
def test_new_models_refuses_duplicates_and_empty_names(tmp_path, monkeypatch, models):
    rc, text, env = refusal(tmp_path, monkeypatch, ["pilot", "--models", models, "--frozen-prompt-date", S.EPOCH_DATE,
                                                    "--out-root", str(tmp_path / "c147")])
    assert_refused_for(rc, text, "--models", env=env)


def test_new_a_model_that_is_not_an_entry_of_the_served_registry_refuses_before_the_router(tmp_path, monkeypatch):
    rc, text, env = refusal(tmp_path, monkeypatch, ["pilot", "--models", S.MODEL2, "--frozen-prompt-date", S.EPOCH_DATE,
                                                    "--out-root", str(tmp_path / "c147")])
    assert_refused_for(rc, text, S.MODEL2, env=env)


@pytest.mark.parametrize("models,loads", [
    ((S.MODEL,), [S.MODEL, S.MODEL, S.MODEL]),
    ((S.MODEL, S.MODEL2), [S.MODEL, S.MODEL2, S.MODEL2, S.MODEL, S.MODEL]),
    ((S.MODEL, S.MODEL2, S.MODEL3), [S.MODEL, S.MODEL2, S.MODEL3, S.MODEL3, S.MODEL2, S.MODEL, S.MODEL]),
])
def test_new_the_generic_schedule_follows_the_models_list(tmp_path, monkeypatch, models, loads):
    """§6.1: s1 the models in the given order, s2 reversed, reload the first model (legacy two-pick semantics)."""
    env = S.chain_env(tmp_path, monkeypatch, registry=S.registry_text((S.MODEL, S.MODEL2, S.MODEL3)))
    try:
        rc = S.run_chain(env, ["chain", "s1", "s2", "reload", "--probe-code-sha", S.HEX9, "--models", ",".join(models)],
                         timeout=180)
        assert rc == 0
        assert [c[1] for c in env["ops"].names("load")] == loads
        assert json.dumps(list(models)) in json.dumps(S.chain_json(env))        # recorded in the ChainConfig / chain.json
    finally:
        env["ops"].cancel()


def test_inv_the_p223_argv_with_models_keeps_the_golden_item_order(tmp_path, monkeypatch):
    env = S.chain_env(tmp_path, monkeypatch)
    try:
        rc = S.run_chain(env, ["chain", "s1", "s2", "reload", "--probe-code-sha", S.HEX9, "--models", PAIR], universe=False,
                         timeout=300)
        assert rc == 0
        assert S.order_sha(S.invocation_order(S.invocations(env))) == S.GOLDEN_CHAIN_ORDER_SHA
    finally:
        env["ops"].cancel()


def test_inv_the_m63_argv_with_models_keeps_the_golden_item_order(tmp_path, monkeypatch):
    env = S.chain_env(tmp_path, monkeypatch, registry=S.registry_text((S.MODEL, S.MODEL2), on=(S.MODEL, S.MODEL2)),
                      out="m63")
    env["ops"].extra_env["FAKE_SERVED_REGISTRY"] = env["ops"].overlay
    try:
        rc = S.run_chain(env, ["chain", "s1", "s2", "reload", "--probe-code-sha", S.HEX9, "--models", PAIR, "--predictor",
                               "mtp"], universe=False, timeout=300)
        assert rc == 0
        assert S.order_sha(S.invocation_order(S.invocations(env))) == S.GOLDEN_CHAIN_ORDER_SHA
    finally:
        env["ops"].cancel()


def test_inv_the_legacy_pilot_with_models_keeps_the_golden_item_order(tmp_path, monkeypatch):
    env = S.chain_env(tmp_path, monkeypatch)
    try:
        assert S.run_chain(env, ["pilot", "--models", S.MODEL], universe=False) == 0
        assert S.invocation_order(S.invocations(env)) == S.GOLDEN_PILOT_ORDER
    finally:
        env["ops"].cancel()


def test_inv_the_serialized_tg1_chain_config_differs_only_in_the_c221_fields():
    cfg = R.tg1_config(R.parse_args(["chain", "s1", "--probe-code-sha", S.HEX9, "--models", PAIR])).as_dict()
    assert {k: cfg[k] for k in S.GOLDEN_TG1_CONFIG_STATIC} == S.GOLDEN_TG1_CONFIG_STATIC
    assert cfg["schedule"]["builder"] == "tg1"


def test_fix_the_committed_registry_is_served_verbatim_without_overlay_generation(tmp_path, monkeypatch):
    env = S.chain_env(tmp_path, monkeypatch)
    try:
        assert S.run_chain(env, ["pilot", "--models", S.MODEL]) == 0
        assert not env["ops"].names("ensure_overlay")
        cj = S.chain_json(env)
        assert cj["sha256"]["overlay"] == S.sha256_file(env["ops"].overlay) == cj["pinned"]["registry_sha256"]
    finally:
        env["ops"].cancel()


@pytest.mark.parametrize("predictor,on,partial", [
    ("mtp", (), ()),                       # mtp asserted, the served entry has none of the C177 keys
    ("off", (S.MODEL,), ()),               # off asserted, the served entry has all three
    ("mtp", (), (S.MODEL,)),               # a partial entry is neither
    ("off", (), (S.MODEL,)),
])
def test_new_predictor_is_an_assertion_on_the_served_entry(tmp_path, monkeypatch, predictor, on, partial):
    env = S.chain_env(tmp_path, monkeypatch, registry=S.registry_text((S.MODEL, S.MODEL2), on=on, partial=partial))
    try:
        rc, text = S.main_refusal(["pilot", "--models", S.MODEL, "--predictor", predictor, "--frozen-prompt-date",
                                   S.EPOCH_DATE, "--out-root", str(tmp_path / ("m63" if predictor == "mtp" else "c147"))],
                                  env["ops"])
    finally:
        env["ops"].cancel()
    assert_refused_for(rc, text, "--predictor", env=env)


def test_inv_predictor_mtp_with_a_complete_entry_runs_in_the_m63_family(tmp_path, monkeypatch):
    env = S.chain_env(tmp_path, monkeypatch, registry=S.registry_text((S.MODEL, S.MODEL2), on=(S.MODEL,)), out="m63")
    env["ops"].extra_env["FAKE_SERVED_REGISTRY"] = env["ops"].overlay
    try:
        assert S.run_chain(env, ["pilot", "--models", S.MODEL, "--predictor", "mtp"]) == 0
        assert S.chain_json(env)["chain_config"]["out_root_family"] == "m63"
    finally:
        env["ops"].cancel()


# ------------------------------------------------------------------------------------------------ the generic prediction
def _find(doc, key):
    if isinstance(doc, dict):
        if key in doc:
            yield doc[key]
        for v in doc.values():
            yield from _find(v, key)
    elif isinstance(doc, list):
        for v in doc:
            yield from _find(v, key)


def test_new_the_generic_prediction_is_recorded_in_chain_json(tmp_path, monkeypatch):
    env = S.chain_env(tmp_path, monkeypatch)
    try:
        assert S.run_chain(env, ["pilot", "--models", S.MODEL]) == 0
        assert 250 in list(_find(S.chain_json(env), "generic_pred_s"))
    finally:
        env["ops"].cancel()


def test_fix_before_a_pilot_mean_the_watch_prediction_is_the_generic_default_not_the_m59_table(tmp_path, monkeypatch):
    """C221: `chain_core.PRED_S` (244 s for Python / the first pick) is retired from the tg1 path; 250 s until a pilot mean."""
    env = S.chain_env(tmp_path, monkeypatch)
    env["ops"].extra_env.update(FAKE_ITEM_S="0.4", FAKE_HB_S="0.1")
    try:
        assert S.run_chain(env, ["pilot", "--models", S.MODEL], timers=dict(watch_s=0.15)) == 0
    finally:
        env["ops"].cancel()
    early = [ln for ln in env["lines"] if " WATCH " in ln and re.search(r" a1: [0-4]/5 ", ln)]
    assert early and all(" pred=250s " in ln for ln in early), early[:2]
