"""Shared surface of today's (lever=mtp) P426 tooling, computed from the code and the committed registry texts. The golden
fixture `fixtures/m76_b3_fe/golden_mtp_surface.json` is this function's output on the BASELINE (run, not guessed)."""
from __future__ import annotations

import json
from pathlib import Path

from bench import p426_leg, p426_plan, p426_wave1

TESTS = Path(__file__).resolve().parent
FIX = TESTS / "fixtures" / "m76_b3_fe"
REPO = TESTS.parents[2]
ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
DRAFTER = "caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter"
AXES = ("math500", "cjudge", "vision", "reasoning", "m1")


def text(name):
    return (FIX / f"{name}_main_models.yaml").read_text()


def worker_argv(arm, wt="/WT"):
    """The real worker argv spelling of an M76 arm (as `test_m76_b1_impl_support.worker_argv45`)."""
    modes = {"X": "m72_exact", "XO": "m72_exact", "V": "m72_v1"}
    argv = [f"{wt}/.venv/bin/mlx_vlm.server", "--model", f"caslca/{ENTRY}", "--host", "127.0.0.1", "--port", "8091",
            "--max-kv-size", "262144", "--kv-prealloc-tokens", "262144"]
    if arm != "N16":
        argv += ["--kv-bits", "4"]
    argv += ["--kv-quant-scheme", "turboquant", "--prefill-step-size", "512", "--attention-policy", "fused_v1"]
    if arm != "N16":
        argv += ["--tq4-attention", modes[arm]]
    argv += ["--generation-defaults", json.dumps({"temperature": 0.5, "top_p": 0.95})]
    if arm != "XO":
        argv += ["--mtp-verify-scan", "joint_v1", "--draft-kind", "mtp", "--draft-model", DRAFTER]
    return argv


def _canon(obj):
    s = json.dumps(obj, sort_keys=True, default=str)
    return json.loads(s.replace(str(REPO), "<REPO>"))


def surface():
    out = {}
    out["expected_builds"] = p426_plan.EXPECTED_BUILDS
    out["schedule_default"] = [list(x) for x in p426_wave1.schedule()]
    out["leg_names"] = {b: [p426_plan.leg_name(a, arm, sel, b) for a in AXES for arm in ("off", "on") for sel in ("smoke", 1, 2)]
                        for b in ("s", "s2")}
    out["tune_prefix"] = {b: p426_plan.tune_prefix(b) for b in ("s", "s2")}
    out["frozen_path"] = {b: str(p426_plan.frozen_path("/WD", b)) for b in ("s", "s2")}
    out["leg_argv"] = {
        b: [p426_wave1.leg_argv("/WT", "/WD", "/REG", "/RC", a, arm, sel, b, stack_root_off="/WTOFF")
            for a in AXES for arm in ("off", "on") for sel in ("smoke", 1, 2)] for b in ("s", "s2")}
    plans = {}
    for b in ("s", "s2"):
        for axis in AXES:
            for arm in ("off", "on"):
                for sel in ("smoke", 1, 2):
                    key = f"{b}/{axis}/{arm}/{sel}"
                    plans[key] = _canon(p426_plan.plan_leg(
                        REPO, axis, arm, None if sel == "smoke" else sel, smoke=sel == "smoke", workdir="/WD",
                        reviewed_head="a" * 40, production_ref="b" * 40, build=b))
    out["plans"] = plans
    out["registry_delta"] = {
        "x_vs_xo": p426_leg.registry_delta_problems(text("x"), text("xo"), ENTRY),
        "x_vs_n16": p426_leg.registry_delta_problems(text("x"), text("n16"), ENTRY),
        "n16_vs_n16": p426_leg.registry_delta_problems(text("n16"), text("n16"), ENTRY),
    }
    out["model_argv"] = {
        f"{arm}/{reg}": p426_leg.model_argv_problems(" ".join(worker_argv(arm)), text(reg.lower()), ENTRY)
        for arm in ("N16", "X", "V", "XO") for reg in ("N16", "X", "V", "XO")}
    return out
