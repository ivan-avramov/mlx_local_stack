"""P371 review r1 F7: the RESOLVED probe entry (repo-relative) and its data files are part of the `ChainConfig` (hence of
chain.json and the lifecycle) and of the campaign closure spec; a resume with another `--probe` refuses."""
from __future__ import annotations

import pytest

from bench import arm_specs, tg1_runner
from bench import campaign_core as cc
from bench.tests.m64_support import (  # noqa: F401  (fixture: env)
    FAP_PATH, M, REPO, SMOKE, chain_json, env, log_has, run)
from bench.tests.test_c147_chain_runner import C147, R

TG1 = ["chain", "s1", "--probe-code-sha", "9" * 64, "--models", "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"]   # C221: required
FAKE_TG1 = str(C147 / "fake_probe.py")


def test_tg1_binds_the_resolved_probe_entry_and_its_data_files_in_the_config():
    default = R.tg1_config(R.parse_args(TG1))
    over = R.tg1_config(R.parse_args(TG1 + ["--probe", FAKE_TG1]))
    assert default.arms[0].probe == "benchmark/run_tg1_probe.py"
    assert over.arms[0].probe == "benchmark/chains/c147/fake_probe.py"
    assert default.arms[0].probe_data == tuple(tg1_runner.GENERATION_DATA) == over.arms[0].probe_data
    assert default.sha256() != over.sha256()
    assert over.as_dict()["arms"][0]["probe_data"] == list(tg1_runner.GENERATION_DATA)


def test_a_relative_probe_is_the_repository_relative_one_the_chain_spawns():
    a = R.parse_args(TG1 + ["--probe", "benchmark/chains/c147/fake_probe.py"])
    assert R.tg1_config(a).arms[0].probe == "benchmark/chains/c147/fake_probe.py"


def test_a_probe_outside_the_repository_is_refused(tmp_path):
    outside = tmp_path / "p.py"
    outside.write_text("pass\n")
    with pytest.raises(R.Refused, match="inside the repository"):
        R.tg1_config(R.parse_args(TG1 + ["--probe", str(outside)]))
    with pytest.raises(M.Refused, match="inside the repository"):
        M.m64_config(M.parse_args(SMOKE + ["--probe", f"oc={outside}"]))


def test_the_campaign_core_names_the_overridden_probe_tg1():
    default, over = R.parse_args(TG1), R.parse_args(TG1 + ["--probe", FAKE_TG1])
    assert R.core_specs(default) == R.CORE_SPECS
    assert R.core_specs(over)["probe_entry"] == "benchmark/chains/c147/fake_probe.py"
    assert R.core_specs(over)["probe_data"] == R.CORE_SPECS["probe_data"]
    assert cc.closure_shas(REPO, **R.core_specs(default)) != cc.closure_shas(REPO, **R.core_specs(over))


def test_m64_binds_the_resolved_probe_entry_and_data_per_arm():
    default = M.m64_config(M.parse_args(SMOKE))
    over = M.m64_config(M.parse_args(SMOKE + ["--probe", f"oc={FAP_PATH}"]))
    assert default.arms[0].probe == arm_specs.OC.probe == "benchmark/run_oc_probe.py"
    assert over.arms[0].probe == "benchmark/chains/m64/fake_arm_probe.py"
    assert default.arms[0].probe_data == tuple(arm_specs.OC.generation_data) == over.arms[0].probe_data
    assert default.sha256() != over.sha256()


def test_the_campaign_core_names_the_overridden_probe_m64():
    over = M.parse_args(SMOKE + ["--probe", f"oc={FAP_PATH}"])
    assert M.core_specs(["oc"])["probes"]["oc"]["entry"] == "benchmark/run_oc_probe.py"
    assert M.core_specs(["oc"], over)["probes"]["oc"]["entry"] == "benchmark/chains/m64/fake_arm_probe.py"
    assert M.core_specs(["oc"], over)["probes"]["oc"]["data"] == tuple(arm_specs.OC.generation_data)


def test_a_resume_with_another_probe_refuses(env):
    assert run(env, SMOKE) == 0                                       # frozen with oc = the fake arm probe
    frozen = chain_json(env)["chain_config"]["arms"][0]["probe"]
    assert frozen == "benchmark/chains/m64/fake_arm_probe.py"
    assert run(env, SMOKE, fake_all=False) == 2                       # the default oc probe is another entry
    assert log_has(env, "chain_config differs")
