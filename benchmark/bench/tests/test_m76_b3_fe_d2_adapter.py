"""Delivery 2 (supplementary, NEW file; the delivery-1 files are frozen): the same behaviours as `test_m76_b3_fe_kv_lever.py`, spelt
with the candidate's actual API (`p426_plan.kv_*`). Real registry texts / real worker argv from the delivery-1 fixtures.
Class (c) = new behaviour for all but the explicit (b) ones."""
from __future__ import annotations

import re

import pytest

from bench import p426_harvest, p426_plan as P
from bench.tests import test_m76_b3_fe_surface as G

E = G.ENTRY


def d(a, b, arm_a, arm_b):
    return P.kv_registry_delta_problems(G.text(a), G.text(b), E, arm_a, arm_b)


# (c)
@pytest.mark.parametrize("a,b", [("n16", "x"), ("x", "v"), ("n16", "v")])
def test_delta_accepted_both_orders(a, b):
    assert d(a, b, a, b) == []
    assert d(b, a, b, a) == []


# (c)
@pytest.mark.parametrize("a,b", [("x", "xo"), ("n16", "xo")])
def test_delta_refuses_mtp_off_arm(a, b):
    assert d(a, b, a, "x" if b == "xo" else b)


# (c)
@pytest.mark.parametrize("old,new", [
    ("mtp_verify_scan: joint_v1", "mtp_verify_scan: per_query"), ("draft_kind: mtp", "draft_kind: none"),
    (f"draft_model: {G.DRAFTER}", "draft_model: other/drafter"),
    ("prefill_step_size: 512", "prefill_step_size: 1024"), ("max_kv_cache_size: 262144", "max_kv_cache_size: 131072"),
    ("kv_quant_scheme: turboquant", "kv_quant_scheme: uniform"), ("attention_policy: fused_v1", "attention_policy: other"),
])
def test_delta_refuses_changed_key(old, new):
    x = G.text("x")
    assert old in x
    assert P.kv_registry_delta_problems(x.replace(old, new, 1), G.text("n16"), E, "x", "n16")


# (c)
def test_delta_refuses_extra_key_dup_key_and_non_yaml():
    x = G.text("x")
    assert P.kv_registry_delta_problems(x.replace("    tq4_attention: m72_exact\n", "    tq4_attention: m72_exact\n    surprise: 1\n"),
                                        G.text("n16"), E, "x", "n16")
    assert P.kv_registry_delta_problems(x.replace("    kv_bits: 4\n", "    kv_bits: 4\n    kv_bits: 4\n"), G.text("n16"), E, "x", "n16")
    assert P.kv_registry_delta_problems("{", G.text("n16"), E, "x", "n16")


# (c) an arm that claims the wrong label is refused (V text as X)
def test_delta_refuses_a_mislabelled_arm():
    assert d("v", "n16", "x", "n16")


# (c) the arm note: a second / missing / foreign note is refused
def test_delta_refuses_a_wrong_arm_note():
    x = G.text("x")
    assert P.kv_registry_delta_problems(x.replace("# PROVISIONAL M76 arm X", "# PROVISIONAL M76 arm V"), G.text("n16"), E, "x", "n16")
    assert P.kv_registry_delta_problems(x.replace("    # PROVISIONAL M76 arm X\n", ""), G.text("n16"), E, "x", "n16")


# (c)
def test_both_arms_predictor_mtp():
    for arm in ("n16", "x", "v"):
        assert P.kv_registry_problems(G.text(arm), E, arm) == []
    assert P.predictor_of("kv", "n16") == "mtp" and P.predictor_of("kv", "x") == "mtp" and P.predictor_of("mtp", "off") == "off"


# (c) real argv
@pytest.mark.parametrize("arm", ["n16", "x", "v"])
def test_argv_of_each_arm(arm):
    assert P.kv_arm_argv_problems(G.worker_argv(arm.upper()), arm) == []


@pytest.mark.parametrize("arm,as_", [("n16", "x"), ("x", "n16"), ("x", "v"), ("v", "x"), ("n16", "v"), ("v", "n16")])
def test_argv_of_another_arm_refused(arm, as_):
    assert P.kv_arm_argv_problems(G.worker_argv(arm.upper()), as_)


# (c)
@pytest.mark.parametrize("a,b", [("n16", "x"), ("x", "v"), ("n16", "v")])
def test_argv_pair_delta_exactly_the_kv_flags(a, b):
    A, B = G.worker_argv(a.upper()), G.worker_argv(b.upper())
    assert P.kv_argv_problems(A, B, a, b) == []
    assert P.kv_argv_problems(A + ["--surprise", "1"], B, a, b)
    i = B.index("--prefill-step-size")
    B2 = list(B)
    B2[i + 1] = "1024"
    assert P.kv_argv_problems(A, B2, a, b)


# (c) no MTP flags -> refused
def test_argv_without_mtp_refused():
    assert P.kv_arm_argv_problems(G.worker_argv("XO"), "x")


# (c)
def test_s3_pins_and_names():
    s3, s2 = P.EXPECTED_BUILDS["s3"], P.EXPECTED_BUILDS["s2"]
    assert s3["mlx_vlm"].startswith("34a21208") and s3["production_ref"].startswith("f9bf743f") and s3["mlx"] == "0.32.4"
    assert s3["mlx_serve"] != s2["mlx_serve"]
    assert P.kv_leg_name("longctx", "x", 1) == "longctx-m76-x-lc-b1"   # AMENDED (delivery 4): erratum v1.2 item 4
    assert P.kv_leg_name("math500", "n16", "smoke") == "math500-m76-n16-smoke"
    assert P.kv_leg_name("math500", "v", 2, tier=2) == "math500-m76-v-t2-b2"
    assert "p426" not in str(P.kv_frozen_path("/WD", "s3")).replace("/m76/p426/", "")
    assert str(P.kv_frozen_path("/WD", "s3")).startswith("/WD/m76/p426/")
    assert str(p426_harvest.wave1_dir("s3", "kv")).endswith("results/m76/wave1")
    with pytest.raises(ValueError):
        P.kv_frozen_path("/WD", "s2")


# (c) fork gitlink consistency: the stack tree's own submodule gitlinks are what s3 records (only when the checkout has them)
def test_s3_gitlinks_match_the_stage3_base():
    import subprocess

    out = subprocess.run(["git", "-C", str(G.REPO), "ls-tree", "89205085", "src/mlx-vlm", "src/mlx-serve"], capture_output=True, text=True)
    found = dict(reversed(l.split()[2:4]) for l in out.stdout.splitlines()) if out.returncode == 0 else {}
    if not found:
        pytest.skip("base commit not present")
    assert found["src/mlx-vlm"] == P.EXPECTED_BUILDS["s3"]["mlx_vlm"]
    assert found["src/mlx-serve"] == P.EXPECTED_BUILDS["s3"]["mlx_serve"]
