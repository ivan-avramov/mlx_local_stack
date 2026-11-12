"""M76 B1 acceptance 1 (implementer tests, mocked ops, real argv / receipt / log / manifest formats): the `f45` campaign of
`bench.p475_kv` — its table, arm registries from the real committed entry, names, ABBA order, the `tq4_attention` mode proof,
the S18-P13 floor, V / X ratios and the stage-4 trigger, and campaign isolation."""
from __future__ import annotations

import difflib
import json
import shutil

import pytest
import yaml

from bench import kv_line
from bench import p475_kv as K
from bench.tests import test_m76_b1_impl_support as S

REAL = (S.REPO / "main_models.yaml").read_text()


# ---------------------------------------------------------------------------------------------- the campaign table
def test_the_f45_campaign_table():
    c = K.CAMPAIGNS["f45"]
    assert c.pick == "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed" and c.short == "f45"
    assert c.arms == ("N16", "X", "V", "XO") and c.base_arm == "N16" and c.reference_arm == "N16"
    assert c.off_arms == ("XO",) and c.smoke_arms == ("N16", "X") and c.block1_order == ("N16", "X", "V", "XO")
    assert K.branch_name("X", c) == "m76-f45-x" and K.branch_name("XO", "f45") == "m76-f45-xo"
    assert c.comment == "PROVISIONAL M76 arm" and c.scratch == "m76/p475" and c.results == "benchmark/results/m76/matrix"
    assert c.matrix_label == "M76 stage 1 (P475 instrument)" and c.instability_floor == 0.02
    assert set(c.idle_sources) == {"p475", "p426", "m76/p475"} and set(K.CAMPAIGNS["u4"].idle_sources) == set(c.idle_sources)
    assert [K.predictor_of(a, c) for a in c.arms] == ["on", "on", "on", "off"]
    assert K.kinds_for("XO", c) == ("off",) and K.kinds_for("V", c) == ("off", "engagement")
    u4 = K.CAMPAIGNS["u4"]
    assert (u4.pick, u4.short, u4.base_arm, u4.instability_floor, u4.results, u4.scratch) == (
        "Qwen3.8-27B-mlx-uniform-4bit", "u4", "TQ4", None, "benchmark/results/p475", "p475")


def test_the_config_defaults_to_u4_and_takes_the_campaign(tmp_path):
    u = K.Config(repo=tmp_path / "r", workdir=tmp_path / "w", base="b" * 40)
    f = K.Config(repo=tmp_path / "r", workdir=tmp_path / "w", base="b" * 40, campaign="f45")
    assert u.campaign.name == "u4" and u.model == "Qwen3.8-27B-mlx-uniform-4bit"
    assert f.model == "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed" and set(f.expected) == {"N16", "X", "V", "XO"}
    assert u.p475 == tmp_path / "w" / "p475" and f.p475 == tmp_path / "w" / "m76" / "p475"
    assert u.results == tmp_path / "r" / "benchmark" / "results" / "p475"
    assert f.results == tmp_path / "r" / "benchmark" / "results" / "m76" / "matrix"
    assert f.worktree("V") == tmp_path / "w" / "worktrees" / "m76-f45-v"
    assert f.receipt_path("f45-v-b1.a1") == tmp_path / "w" / "m76" / "p475" / "legs" / "f45-v-b1.a1" / "receipt.json"


def test_the_cli_takes_campaign_before_and_after_the_subcommand():
    assert K.parse_args(["matrix"]).campaign == "u4"
    assert K.parse_args(["--campaign", "f45", "matrix"]).campaign == "f45"
    assert K.parse_args(["run", "--campaign", "f45", "--smoke"]).campaign == "f45"
    assert K.parse_args(["preflight", "--campaign", "f45", "--arm", "XO"]).arm == "XO"
    with pytest.raises(SystemExit):
        K.parse_args(["preflight", "--arm", "XO"])                       # XO is not a u4 arm
    with pytest.raises(SystemExit):
        K.parse_args(["--campaign", "f45", "preflight", "--arm", "TQ4"])
    with pytest.raises(SystemExit):
        K.parse_args(["--campaign", "p999", "matrix"])


# ---------------------------------------------------------------------------------------------- names and order
def test_leg_names_and_the_leg_regex():
    assert K.leg_name("XO", 2, 1, "f45") == "f45-xo-b2.a1" and K.leg_name("X", "smoke", 3, "f45") == "f45-x-smoke.a3"
    assert K.parse_leg("f45-v-b3.a2", "f45") == dict(arm="V", block=3, attempt=2)
    assert K.parse_leg("f45-n16-smoke.a1", "f45") == dict(arm="N16", block="smoke", attempt=1)
    rx = K.CAMPAIGNS["f45"].leg_re
    for bad in ("u4-tq4-b1.a1", "f45-tq4-b1.a1", "f45-x-b0.a1", "f45-x-b1.a0", "f45-xo-b1", "m76-f45-x-b1.a1"):
        assert not rx.match(bad), bad
    with pytest.raises(ValueError):
        K.parse_leg("u4-n16-b1.a1", "f45")
    with pytest.raises(ValueError):
        K.parse_leg("f45-n16-b1.a1")                                     # the default campaign is u4
    assert K.foreign_campaign("u4-n16-b1.a1", "f45") == "u4" and K.foreign_campaign("f45-x-b1.a1", "u4") == "f45"


def test_abba_order():
    assert K.block_order(1, "f45") == ("N16", "X", "V", "XO") == K.block_order(3, "f45")
    assert K.block_order(2, "f45") == ("XO", "V", "X", "N16")


# ---------------------------------------------------------------------------------------------- arm registries (R1)
@pytest.mark.parametrize("arm", ["X", "V", "XO"])
def test_arm_registry_from_the_real_entry(arm):
    got = K.arm_registry_text(REAL, arm, campaign="f45")
    assert got == S.expected_arm_text(REAL, arm)
    assert K.registry_diff_problems(REAL, got, arm, campaign="f45") == []
    diff = [ln for ln in difflib.unified_diff(REAL.splitlines(), got.splitlines(), lineterm="", n=0)
            if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]
    mode = "m72_v1" if arm == "V" else "m72_exact"
    want = {"-    kv_bits: 0  # C81: native16 KV is the operator-approved default; quantization disabled.",
            "+    kv_bits: 4", f"+    tq4_attention: {mode}", f"+    # PROVISIONAL M76 arm {arm}"}
    if arm == "XO":
        want |= {"-    draft_kind: mtp", "+    # draft_kind: mtp", "-    mtp_verify_scan: joint_v1", "+    # mtp_verify_scan: joint_v1",
                 "-    draft_model: caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter",
                 "+    # draft_model: caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter"}
    assert set(diff) == want and len(diff) == len(want)
    entry = next(m for m in yaml.safe_load(got)["models"] if m["name"] == S.F45)
    assert entry["kv_bits"] == 4 and entry["tq4_attention"] == mode and entry["kv_quant_scheme"] == "turboquant"
    if arm == "XO":
        assert not {"draft_kind", "draft_model", "mtp_verify_scan"} & set(entry)
    else:
        assert entry["draft_kind"] == "mtp" and entry["mtp_verify_scan"] == "joint_v1"
    others = [m for m in yaml.safe_load(got)["models"] if m["name"] != S.F45]
    assert others == [m for m in yaml.safe_load(REAL)["models"] if m["name"] != S.F45]


def test_the_n16_arm_is_the_base_itself():
    assert K.arm_registry_text(REAL, "N16", campaign="f45") == REAL
    assert K.registry_diff_problems(REAL, REAL, "N16", campaign="f45") == []
    assert K.registry_diff_problems(REAL, REAL + "# x\n", "N16", campaign="f45") == ["N16: the registry differs from the base"]


def _in_entry(text, fn):
    lines = text.splitlines(keepends=True)
    s, e = S.entry_range(lines, S.F45)
    return "".join(lines[:s + 1] + fn(lines[s + 1:e]) + lines[e:])


def test_adding_a_key_the_entry_already_has_refuses():
    base = _in_entry(REAL, lambda body: ["    tq4_attention: off\n"] + body)
    for arm in ("X", "V", "XO"):
        with pytest.raises(ValueError, match="already has"):
            K.arm_registry_text(base, arm, campaign="f45")


@pytest.mark.parametrize("key,arms", [("kv_bits", ("X", "V", "XO")), ("mtp_verify_scan", ("XO",)), ("draft_model", ("XO",))])
def test_editing_a_key_the_entry_lacks_refuses(key, arms):
    base = _in_entry(REAL, lambda body: [ln for ln in body if not ln.startswith(f"    {key}:")])
    for arm in arms:
        with pytest.raises(ValueError, match="lacks"):
            K.arm_registry_text(base, arm, campaign="f45")


@pytest.mark.parametrize("tamper", [
    lambda t: t.replace("tq4_attention: m72_exact", "tq4_attention: m72_v1"),                   # the other arm's mode
    lambda t: t.replace("# PROVISIONAL M76 arm X\n", "# PROVISIONAL P475 arm X\n"),               # u4's comment
    lambda t: t.replace("# PROVISIONAL M76 arm X\n", ""),                                         # no comment
    lambda t: t.replace("    attention_policy: fused_v1\n", "    attention_policy: auto\n"),       # a key outside the arm's
    lambda t: t.replace("    tq4_attention: m72_exact\n", ""),                                    # the mode line missing
])
def test_a_tampered_x_registry_is_refused(tamper):
    good = K.arm_registry_text(REAL, "X", campaign="f45")
    assert K.registry_diff_problems(REAL, tamper(good), "X", campaign="f45")


# ---------------------------------------------------------------------------------------------- kv line
@pytest.mark.parametrize("arm", ["X", "V", "XO"])
def test_the_tq4_arms_expect_todays_tq4_line(arm):
    assert kv_line.expected_kv(arm, "f45") == kv_line.expected_kv("TQ4")
    good = kv_line.parse_kv_line(S.F.kv_line("TQ4"))
    assert kv_line.kv_line_problems(good, arm, "f45") == []
    assert kv_line.kv_line_problems(kv_line.parse_kv_line(S.F.kv_line("N16")), arm, "f45")


def test_n16_expects_the_native_line():
    assert kv_line.kv_line_problems(kv_line.parse_kv_line(S.F.kv_line("N16")), "N16", "f45") == []
    assert kv_line.kv_line_problems(kv_line.parse_kv_line(S.F.kv_line("TQ4")), "N16", "f45")


def test_selftest_lines_are_parsed():
    text = "\n".join(["noise", S.selftest_line("m72_exact"), "mtp_verify_scan=joint_v1 self-test: 2 cells",
                      "x tq4_attention='m72_v1' self-test: 1 cell"])
    assert kv_line.parse_tq4_selftests(text) == ["m72_exact", "m72_v1"]
    assert kv_line.parse_tq4_selftests("") == []


# ---------------------------------------------------------------------------------------------- the mode proof
@pytest.mark.parametrize("arm", ["X", "V", "XO"])
def test_good_counters_prove_the_mode(arm):
    rec, problems = K.route_proof(S.manifest_for(arm), S.MODES[arm], arm)
    assert problems == []
    assert {k for k, v in rec["exit_counts"].items() if v > 0} == set(S.GOOD_MOVES[arm])
    assert rec["creation"]["route_counts"] == rec["exit"]["route_counts"]      # both blocks recorded


@pytest.mark.parametrize("arm", ["X", "V", "XO"])
def test_the_rules_read_the_exit_absolutes_not_deltas(arm):
    """Errata v1.1: creation == exit (a zero delta everywhere) is a healthy leg; a creation block whose counters differ does
    not change the verdict (only its mode is checked)."""
    c, e = S.good_counts(arm)
    assert K.route_proof(S.manifest_for(arm, c, e), S.MODES[arm], arm)[1] == []
    assert K.route_proof(S.manifest_for(arm, {k: 999 for k in c}, e), S.MODES[arm], arm)[1] == []
    assert K.route_proof(S.manifest_for(arm, {}, e), S.MODES[arm], arm)[1] == []


@pytest.mark.parametrize("arm", ["X", "V", "XO"])
def test_a_creation_block_of_another_mode_is_refused(arm):
    other = "m72_v1" if S.MODES[arm] == "m72_exact" else "m72_exact"
    man = S.manifest_for(arm)
    man["tq4_route_counts_at_creation"]["mode"] = other
    problems = K.route_proof(man, S.MODES[arm], arm)[1]
    assert any("at creation" in p and "mode" in p for p in problems), problems


def test_n16_proves_mode_off():
    assert K.route_proof(S.manifest_for("N16"), "off", "N16")[1] == []
    man = S.manifest_for("N16")
    man["tq4_route_counts_at_creation"] = {"mode": "m72_exact", "route_counts": {"p2s": 1}, "source": "worker-health"}
    assert K.route_proof(man, "off", "N16")[1]
    assert K.route_proof(dict(S.manifest_for("N16"), runtime={"tq4_attention": "m72_v1"}), "off", "N16")[1]
    assert K.selftest_problems(["m72_exact"], "off") and K.selftest_problems([], "off") == []


def _bump(arm, key, by=1, where="exit"):
    c, e = S.good_counts(arm)
    (e if where == "exit" else c)[key] = (e if where == "exit" else c).get(key, 0) + by
    return S.manifest_for(arm, c, e)


@pytest.mark.parametrize("arm,key", [(a, k) for a in ("X", "V", "XO") for k in S.GOOD_MOVES[a]])
def test_each_required_counter_must_move(arm, key):
    c, e = S.good_counts(arm)
    e[key] = 0
    problems = K.route_proof(S.manifest_for(arm, c, e), S.MODES[arm], arm)[1]
    assert any(repr(key) in p and "need > 0" in p for p in problems), problems


@pytest.mark.parametrize("arm,key", [("X", "mma"), ("V", "d2_verify"), ("XO", "mma"), ("XO", "d2_verify"),
                                     ("XO", "native:verify"), ("X", "fallback:mask"), ("V", "fallback:dtype"),
                                     ("XO", "fallback:new_route")])
def test_each_forbidden_counter_must_stay(arm, key):
    problems = K.route_proof(_bump(arm, key), S.MODES[arm], arm)[1]
    assert any(repr(key) in p and "need 0" in p for p in problems), problems


@pytest.mark.parametrize("arm", ["X", "V", "XO"])
def test_a_mode_mismatch_is_refused(arm):
    other = "m72_v1" if S.MODES[arm] == "m72_exact" else "m72_exact"
    assert K.route_proof(S.manifest_for(arm, mode=other), S.MODES[arm], arm)[1]
    assert K.selftest_problems([other], S.MODES[arm]) and K.selftest_problems([S.MODES[arm]], S.MODES[arm]) == []


def test_a_creation_block_without_counters_but_of_the_mode_is_fine():
    """Errata v1.1: the creation block is recorded and its mode checked; its counters do not enter the rules."""
    man = S.manifest_for("X")
    man["tq4_route_counts_at_creation"] = {"mode": "m72_exact", "route_counts": None, "source": "health-without-tq4-block"}
    assert K.route_proof(man, "m72_exact", "X")[1] == []


@pytest.mark.parametrize("drop", ["creation", "exit", "counts_exit", "manifest"])
def test_missing_counters_are_refused(drop):
    man = S.manifest_for("X")
    if drop == "creation":
        del man["tq4_route_counts_at_creation"]
    elif drop == "exit":
        del man["router_exit"]["tq4_route_counts_at_exit"]
    elif drop == "counts_creation":
        man["tq4_route_counts_at_creation"] = {"mode": "m72_exact", "route_counts": None, "source": "health-without-tq4-block"}
    elif drop == "counts_exit":
        man["router_exit"]["tq4_route_counts_at_exit"] = {"mode": None, "route_counts": None, "source": "refused: x"}
    else:
        man = None
    assert K.route_proof(man, "m72_exact", "X")[1]


# ---------------------------------------------------------------------------------------------- legs (mocked ops)
def test_an_x_leg_is_valid_and_records_the_proof(tmp_path, monkeypatch):
    w = S.world45(tmp_path, monkeypatch)
    ops = S.ready45(w)
    r = S.run_leg45(w, "X", ops=ops)
    assert r["verdict"] == "VALID", r["problems"]
    assert r["campaign"] == "f45" and r["model"] == S.F45 and r["leg"] == "f45-x-b1.a1"
    assert r["mode_proof"]["expected_mode"] == "m72_exact" and r["mode_proof"]["selftest_modes"] == ["m72_exact"]
    assert r["mode_proof"]["exit_counts"]["d2_verify"] == 11 and r["mode_proof"]["exit_counts"]["mma"] == 0
    assert r["mode_proof"]["creation"]["mode"] == "m72_exact" and r["mode_proof"]["exit"]["mode"] == "m72_exact"
    assert r["paths"]["worktree"] == str(w.wd / "worktrees" / "m76-f45-x")
    assert r["paths"]["rows"].startswith(str(w.wd / "m76" / "p475" / "legs" / "f45-x-b1.a1"))
    assert r["driver_argv"][r["driver_argv"].index("--model") + 1] == S.F45
    assert r["driver_argv"][r["driver_argv"].index("--out-tag") + 1] == "p475-f45-x-b1.a1"
    dossier = w.main / "benchmark" / "results" / "m76" / "matrix" / "f45-x-b1.a1"
    stored = json.loads((dossier / "receipt.json").read_text())
    assert stored["campaign"] == "f45" and stored["mode_proof"]["exit_counts"]["p2s"] == 11
    assert stored["mode_proof"]["creation"] and stored["mode_proof"]["exit"]
    assert (w.wd / "m76" / "p475" / "LAST_LEG_END").is_file()
    assert not (w.main / "benchmark" / "results" / "p475").exists()


@pytest.mark.parametrize("arm", ["N16", "V", "XO"])
def test_the_other_arms_are_valid(tmp_path, monkeypatch, arm):
    w = S.world45(tmp_path, monkeypatch)
    ops = S.ready45(w)
    r = S.run_leg45(w, arm, ops=ops)
    assert r["verdict"] == "VALID", r["problems"]
    assert r["predictor"] == ("off" if arm == "XO" else "on")


@pytest.mark.parametrize("case", ["mma_on_x", "fallback", "no_counters", "mode_mismatch"])
def test_a_failed_route_proof_after_the_driver_is_invalid(tmp_path, monkeypatch, case):
    w = S.world45(tmp_path, monkeypatch)
    ops = S.ready45(w)
    man = {"mma_on_x": _bump("X", "mma"), "fallback": _bump("X", "fallback:mask", 3),
           "no_counters": {k: v for k, v in S.manifest_for("X").items() if k != "tq4_route_counts_at_creation"},
           "mode_mismatch": S.manifest_for("X", mode="m72_v1")}[case]
    w.manifest_override["X"] = man
    r = S.run_leg45(w, "X", ops=ops)
    assert r["verdict"] == "INVALID" and any(p.startswith("mode proof:") for p in r["problems"]), r["problems"]
    assert w.spawns                                                  # the driver ran: the proof is the after-driver half


@pytest.mark.parametrize("arm,line", [("X", S.selftest_line("m72_v1")), ("N16", S.selftest_line("m72_exact"))])
def test_a_selftest_mismatch_after_load_refuses_before_the_driver(tmp_path, monkeypatch, arm, line):
    w = S.world45(tmp_path, monkeypatch)
    ops = S.ready45(w)
    w.selftest = line
    r = S.run_leg45(w, arm, ops=ops)
    assert r["verdict"] == "INVALID" and any(p.startswith("mode proof:") for p in r["problems"]), r["problems"]
    assert not w.spawns                                              # R5: no driver


@pytest.mark.parametrize("name", K.DRAFT_ENV_NAMES)
def test_an_xo_worker_with_a_draft_variable_is_invalid_before_the_driver(tmp_path, monkeypatch, name):
    """Errata v1.1: an MTP-OFF arm's worker carrying a draft variable -> INVALID, named, before the driver."""
    w = S.world45(tmp_path, monkeypatch)
    ops = S.ready45(w)
    w.worker_env_extra = {name: "x"}
    r = S.run_leg45(w, "XO", ops=ops)
    assert r["verdict"] == "INVALID" and any(name in p for p in r["problems"]), r["problems"]
    assert not w.spawns and "stop_stack" in w.names()


@pytest.mark.parametrize("name", K.DRAFT_ENV_NAMES)
def test_an_on_arm_worker_with_a_draft_variable_is_not_refused_for_it(tmp_path, monkeypatch, name):
    w = S.world45(tmp_path, monkeypatch)
    ops = S.ready45(w)
    w.worker_env_extra = {name: "x"}
    r = S.run_leg45(w, "X", ops=ops)
    assert not any(name in p for p in r["problems"]), r["problems"]


@pytest.mark.parametrize("arm", S.ARMS45)
def test_the_f45_driver_env_carries_no_draft_variable(tmp_path, monkeypatch, arm):
    w = S.world45(tmp_path, monkeypatch)
    ops = S.ready45(w)
    w.router_env_extra = {n: "x" for n in K.DRAFT_ENV_NAMES}
    assert S.run_leg45(w, arm, ops=ops)["verdict"] == "VALID"
    assert not any(n in w.spawns[0].env for n in K.DRAFT_ENV_NAMES)


def test_the_u4_driver_env_keeps_the_draft_variables(tmp_path, monkeypatch):
    from bench.tests.p475s1 import helpers as H
    w = H.world(tmp_path, monkeypatch)
    ops = H.ready(w)
    w.router_env_extra = {n: "x" for n in K.DRAFT_ENV_NAMES}
    H.run_leg(w, "TQ4", ops=ops)
    assert all(w.spawns[0].env.get(n) == "x" for n in K.DRAFT_ENV_NAMES)


@pytest.mark.parametrize("campaign,stripped", [("f45", True), ("u4", False)])
def test_realops_router_env_strips_the_draft_variables_on_f45(tmp_path, monkeypatch, campaign, stripped):
    wd, repo = tmp_path / "wd", tmp_path / "repo"
    wt = wd / "worktrees" / "wt"
    wt.mkdir(parents=True)
    repo.mkdir()
    (wt / ".env").write_text("MLX_VLM_DRAFT_KIND=mtp\nHF_HOME=/hf\n")                 # a draft name in the worktree's .env
    monkeypatch.setenv("MLX_VLM_DRAFT_MODEL", "caslca/some-drafter")
    monkeypatch.setenv("KV_BITS", "4")
    handle = K.RealOps(wd, repo, campaign).stack(wt, wt / "main_models.yaml", "off")
    env = handle.env_base()
    assert "KV_BITS" not in env and "KV_BITS" not in handle.env_source
    assert (not any(n in env for n in K.DRAFT_ENV_NAMES)) is stripped
    assert stripped or all(n in env for n in K.DRAFT_ENV_NAMES)
    assert env.get("HF_HOME") == "/hf" and env["MLX_SERVE_CONFIG"] == str(wt / "main_models.yaml")
    assert ("MLX_VLM_DRAFT_MODEL" in handle.env_source) is not stripped


def test_the_f45_estimates_are_the_safe_placeholders():
    assert K.CAMPAIGNS["f45"].leg_estimate_min == {"N16": 25, "X": 76, "V": 76, "XO": 76}
    exp = K.default_expected("f45")
    assert sum(exp["X"]) == pytest.approx(76 * 60, abs=1) and sum(exp["N16"]) == pytest.approx(25 * 60, abs=1)


def test_the_u4_leg_has_no_mode_proof(tmp_path, monkeypatch):
    from bench.tests.p475s1 import helpers as H
    w = H.world(tmp_path, monkeypatch)
    ops = H.ready(w)
    r = H.run_leg(w, "TQ4", ops=ops)
    assert r["verdict"] == "VALID" and "mode_proof" not in r and "campaign" not in r


# ---------------------------------------------------------------------------------------------- the floor (S18-P13)
def _vals(arm, n16, other, metric="prefill", ctx=8192):
    return {("N16", b): {ctx: {metric: n16[b - 1]}} for b in (1, 2)} | {(arm, b): {ctx: {metric: other[b - 1]}} for b in (1, 2)}


S18_P13 = [("AF4", (919.85, 927.88), (932.41, 932.77)), ("AF8", (919.85, 927.88), (920.73, 931.87))]


@pytest.mark.parametrize("arm,n16,other", S18_P13)
def test_the_s18_p13_cells_flag_under_u4_only(arm, n16, other):
    v = _vals(arm, n16, other)
    u4 = K.instability(v)[(arm, 8192, "prefill")]
    assert u4["spread"] and u4["flag"]
    floored = K.instability(v, floor=0.02)[(arm, 8192, "prefill")]
    assert not floored["flag"] and abs(floored["mean"] - 1) < 0.02 and abs(floored["r1"] - floored["r2"]) < 0.02


@pytest.mark.parametrize("arm,n16,other", S18_P13)
def test_the_same_ratios_do_not_flag_under_f45(arm, n16, other):
    fl = K.instability(_vals("X", n16, other), campaign="f45")[("X", 8192, "prefill")]
    assert not fl["flag"]


@pytest.mark.parametrize("r1,r2,flag,kind", [
    (1.03, 0.97, True, "reversal"), (1.009, 0.991, False, None), (1.012, 0.995, False, None), (1.03, 0.995, True, "spread"),
    (1.00, 1.025, True, "spread"), (1.10, 1.06, True, "spread"), (1.10, 1.09, False, None), (0.60, 0.61, False, None),
])
def test_the_floor_rule(r1, r2, flag, kind):
    fl = K.instability(_vals("V", (100.0, 100.0), (100.0 * r1, 100.0 * r2), "decode", 131072), campaign="f45")[
        ("V", 131072, "decode")]
    assert fl["flag"] is flag
    if kind:
        assert fl[kind]


# ---------------------------------------------------------------------------------------------- V / X and the trigger
def _vx(v_over_x, blocks=(1, 2)):
    out = {}
    for b in blocks:
        for arm, mul in (("N16", 1.0), ("X", 1.0), ("V", None)):
            out[(arm, b)] = {}
            for ctx in K.GRID:
                f = v_over_x.get((ctx, b), 1.0) if mul is None else mul
                out[(arm, b)][ctx] = {"decode": 20.0 * f, "prefill": 300.0 * f, "peak": 30.0 * f, "acceptance": 0.7}
    return out


def test_vx_ratios():
    r = K.vx_ratios(_vx({(131072, 1): 1.2}))
    assert r[("decode", 131072, 1)] == pytest.approx(1.2) and r[("prefill", 131072, 1)] == pytest.approx(1.2)
    assert r[("peak", 8192, 2)] == pytest.approx(1.0)


def test_the_trigger_is_met():
    met, failing = K.stage4_trigger(_vx({(c, b): 1.06 for c in (131072, 260096) for b in (1, 2)}), set())
    assert met and failing == []


def test_the_trigger_is_not_met_and_names_the_cells():
    vals = _vx({(131072, 1): 1.06, (131072, 2): 1.04, (260096, 1): 1.08, (260096, 2): 1.07})
    met, failing = K.stage4_trigger(vals, set())
    assert not met and failing == ["V / X decode 131072 b2 = 1.040 < 1.05"]
    met, failing = K.stage4_trigger(_vx({(c, b): 1.2 for c in (131072, 260096) for b in (1, 2)}), {("V", 260096, "decode")})
    assert not met and failing == ["unresolved instability: V 260096 decode"]


def test_the_trigger_line_format():
    met = K._f45_sections([], _vx({(c, b): 1.06 for c in (131072, 260096) for b in (1, 2)}), set())
    assert any(ln.startswith("stage-4 trigger: **met** (") for ln in met), met
    vals = _vx({(131072, 1): 1.06, (131072, 2): 1.04, (260096, 1): 1.08, (260096, 2): 1.07})
    lines = K._f45_sections([], vals, set())
    assert "stage-4 trigger: **not met** — V / X decode 131072 b2 = 1.040 < 1.05" in lines, lines
    assert not any("**stage-4 trigger" in ln for ln in met + lines)


# ---------------------------------------------------------------------------------------------- a whole f45 run + matrix
def test_a_full_f45_run_writes_its_own_matrix(tmp_path, monkeypatch):
    w = S.world45(tmp_path, monkeypatch)
    # the fake's decode: N16 40 / 42, X 34 / 36 (blocks 1 / 2); V = 1.10 x X in both blocks; XO held at 0.5 x N16 in both
    w.f45_metric.update({("V", 1): {"dts": 34.0 * 1.10}, ("V", 2): {"dts": 36.0 * 1.10}, ("XO", 1): {"dts": 20.0},
                         ("XO", 2): {"dts": 21.0}})
    rc = K.run(S.parse45(w, "run"), S.FakeOps45(w))
    assert [s.arm for s in w.stacks] == ["N16", "X", "V", "XO", "XO", "V", "X", "N16"]
    out = w.main / "benchmark" / "results" / "m76" / "matrix" / f"MATRIX.{S.F45}.md"
    assert rc == 0 and out.is_file(), w.names()[-5:]
    text = out.read_text()
    assert text.startswith(f"# P475 KV-cache format matrix — {S.F45} — M76 stage 1 (P475 instrument)\n")
    assert "`benchmark/results/m76/matrix/`" in text and "## V / X (same block)" in text
    assert "| decode | 131072 | 1.100 | 1.100 |" in text
    assert "## tq4_attention route counters" in text and "| f45-x-b1.a1 | m72_exact | m72_exact |" in text
    assert "\nstage-4 trigger: **met** (" in text
    state = json.loads((w.wd / "m76" / "p475" / "state.json").read_text())
    assert state["campaign"] == "f45"
    assert not (w.wd / "p475" / "state.json").exists()


# ---------------------------------------------------------------------------------------------- campaign isolation
def test_a_u4_dossier_under_f45_refuses_and_vice_versa(tmp_path, monkeypatch):
    w = S.world45(tmp_path, monkeypatch)
    ops = S.ready45(w)
    assert S.run_leg45(w, "X", ops=ops)["verdict"] == "VALID"
    f45_res = w.main / "benchmark" / "results" / "m76" / "matrix"
    u4_res = w.main / "benchmark" / "results" / "p475"
    u4_res.mkdir(parents=True)
    shutil.copytree(f45_res / "f45-x-b1.a1", u4_res / "f45-x-b1.a1")                         # an f45 dossier under u4
    u4_cfg = K.Config(repo=w.main, workdir=w.wd, base=w.base)
    _, problems = K.load_dossiers(u4_cfg)
    assert any("f45-x-b1.a1" in p and "f45 dossier" in p for p in problems), problems
    assert K.load_dossier(u4_res / "f45-x-b1.a1")[0] is None
    shutil.copytree(f45_res / "f45-x-b1.a1", f45_res / "u4-tq4-b1.a1")                       # a u4-named dossier under f45
    _, problems = K.load_dossiers(S.cfg45(w))
    assert any("u4-tq4-b1.a1" in p and "u4 dossier" in p for p in problems), problems
    # a dossier whose receipt records another campaign
    shutil.rmtree(f45_res / "u4-tq4-b1.a1")
    rp = f45_res / "f45-x-b1.a1" / "receipt.json"
    doc = json.loads(rp.read_text())
    doc.pop("campaign")
    rp.write_text(json.dumps(doc))
    rec, problems = K.load_dossier(f45_res / "f45-x-b1.a1", "f45")
    assert any("campaign 'u4'" in p for p in problems)


def test_a_state_file_of_another_campaign_refuses(tmp_path, monkeypatch):
    w = S.world45(tmp_path, monkeypatch)
    (w.wd / "m76" / "p475").mkdir(parents=True)
    (w.wd / "m76" / "p475" / "state.json").write_text(json.dumps({"version": 1, "base": w.base}))   # no field: a u4 record
    assert K.run(S.parse45(w, "run"), S.FakeOps45(w)) == 2
    (w.wd / "p475" / "state.json").write_text(json.dumps({"version": 1, "base": w.base, "campaign": "f45"}))
    with pytest.raises(K.P475Error, match="campaign 'f45'"):
        K.load_state(K.Config(repo=w.main, workdir=w.wd, base=w.base))


def test_a_preflight_record_of_another_campaign_is_not_used(tmp_path, monkeypatch):
    w = S.world45(tmp_path, monkeypatch)
    ops = S.ready45(w)
    cfg = S.cfg45(w)
    rec = json.loads(cfg.preflight_record("X").read_text())
    assert rec["campaign"] == "f45"
    rec.pop("campaign")
    cfg.preflight_record("X").write_text(json.dumps(rec))
    assert K.preflight("X", ops, cfg)["status"] == "NOT_STARTED"
    r = S.run_leg45(w, "X", ops=ops)
    assert r["verdict"] == "NOT_STARTED" and any("belongs to campaign 'u4'" in p for p in r["problems"])


def test_a_receipt_of_another_campaign_is_never_harvested(tmp_path, monkeypatch):
    w = S.world45(tmp_path, monkeypatch)
    cfg = S.cfg45(w)
    d = cfg.leg_dir("f45-x-b1.a1")
    d.mkdir(parents=True)
    (d / "receipt.json").write_text(json.dumps({"leg": "f45-x-b1.a1", "verdict": "VALID"}))
    with pytest.raises(K.P475Error, match="campaign 'u4'"):
        K.harvest("f45-x-b1.a1", S.FakeOps45(w), cfg)


def test_idle_spans_both_campaigns(tmp_path, monkeypatch):
    w = S.world45(tmp_path, monkeypatch)
    w.write_last_leg_end("m76/p475", w.epoch0 - 10)                   # an f45 leg just ended: a u4 leg must wait too
    ops = S.FakeOps45(w)
    assert K.last_leg_end(ops, K.Config(repo=w.main, workdir=w.wd, base=w.base)) == w.epoch0 - 10
    assert K.last_leg_end(ops, S.cfg45(w)) == w.epoch0 - 10
