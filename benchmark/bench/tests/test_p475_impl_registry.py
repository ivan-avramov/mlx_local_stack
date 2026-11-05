"""P475 stage 1 (implementer tests): arm registries and arm identity (R1)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bench import p475_kv as K
from bench.tests.test_p475_impl_support import BASE, FakeOps, make_cfg, base_registry

REPO_REGISTRY = Path(__file__).resolve().parents[3] / "main_models.yaml"


def _entry(text, name=K.PICK):
    return next(m for m in yaml.safe_load(text)["models"] if m["name"] == name)


@pytest.mark.parametrize("text", [base_registry(), REPO_REGISTRY.read_text()], ids=["synthetic", "committed"])
@pytest.mark.parametrize("arm", K.ARMS)
def test_arm_registry_changes_only_the_arms_keys(text, arm):
    out = K.arm_registry_text(text, arm)
    base_doc, arm_doc = yaml.safe_load(text), yaml.safe_load(out)
    others = lambda d: [m for m in d["models"] if m.get("name") != K.PICK]  # noqa: E731
    assert others(base_doc) == others(arm_doc)
    assert {k: v for k, v in base_doc.items() if k != "models"} == {k: v for k, v in arm_doc.items() if k != "models"}
    e, b = _entry(out), _entry(text)
    want = dict(b)
    if arm == "N16":
        want["kv_bits"] = 0                                         # v1.2 (Sol P2): the scheme line stays as in the base
    elif arm in ("AF8", "TQ8", "AF4"):
        want["kv_bits"] = int(arm[-1])
        want["kv_quant_scheme"] = "uniform" if arm.startswith("AF") else "turboquant"
    elif arm == "TQ4-OFF":
        want.pop("draft_kind")
        want.pop("draft_model")
    assert e == want
    if arm == "TQ4":
        assert out == text
    else:
        assert out.count(f"# PROVISIONAL P475 arm {arm}\n") == 1
    assert K.registry_diff_problems(text, out, arm) == []


def test_tq4_off_comments_the_mtp_lines_rather_than_deleting_them():
    out = K.arm_registry_text(REPO_REGISTRY.read_text(), "TQ4-OFF")
    assert "    # draft_kind: mtp\n" in out and "    # draft_model: caslca/Qwen3.8-27B-mlx-uniform-4bit-mtp-drafter" in out


@pytest.mark.parametrize("tamper", [
    lambda t: t.replace("prefill_step_size: 512", "prefill_step_size: 1024", 1),          # another key of the entry
    lambda t: t.replace("# PROVISIONAL P475 arm AF8\n", ""),                              # the comment missing
    lambda t: t.replace("kv_bits: 8", "kv_bits: 6", 1),                                   # a wrong width
    lambda t: t + "# trailing note\n",                                                    # an extra line elsewhere
])
def test_registry_diff_refuses_anything_beyond_the_arm(tamper):
    text = base_registry()
    assert K.registry_diff_problems(text, tamper(K.arm_registry_text(text, "AF8")), "AF8")


def test_arm_identity_accepts_a_prepared_arm(tmp_path):
    ops, cfg = FakeOps(tmp_path), make_cfg(tmp_path)
    for arm in K.ARMS:
        ops.add_arm(cfg, arm)
        ident, problems = K.arm_identity(arm, ops, cfg)
        assert problems == [], (arm, problems)
        assert ident["head"] == ops.arms[arm]["head"]


@pytest.mark.parametrize("break_it, match", [
    (lambda o, a: o.arms[a].update(clean=False), "not clean"),
    (lambda o, a: o.arms[a].update(head="f" * 40), "HEAD"),
    (lambda o, a: o.arms[a].update(parent="e" * 40), "parent"),
    (lambda o, a: o.arms[a].update(files=["main_models.yaml", "README.md"]), "changes"),
    (lambda o, a: o.arms[a].update(gitlinks={"src/mlx-vlm": "1" * 40, "src/mlx-serve": "2" * 40}), "gitlinks"),
    (lambda o, a: o.arms[a].update(text=o.arms[a]["text"].replace("kv_bits: 8", "kv_bits: 4", 1)), "kv_bits|parsed"),
])
def test_arm_identity_refuses_a_dirty_or_diverged_arm(tmp_path, break_it, match):
    import re
    ops, cfg = FakeOps(tmp_path), make_cfg(tmp_path)
    ops.add_arm(cfg, "AF8")
    break_it(ops, "AF8")
    _, problems = K.arm_identity("AF8", ops, cfg)
    assert any(re.search(match, p) for p in problems), problems


def test_tq4_identity_is_the_base_itself(tmp_path):
    ops, cfg = FakeOps(tmp_path), make_cfg(tmp_path)
    ops.add_arm(cfg, "TQ4")
    assert ops.arms["TQ4"]["head"] == BASE
    ops.arms["TQ4"].update(head="c" * 40, branch_tip="c" * 40)
    _, problems = K.arm_identity("TQ4", ops, cfg)
    assert any("base" in p for p in problems)


def test_names_and_abba_order():
    assert K.leg_name("TQ4-OFF", 2, 3) == "u4-tq4-off-b2.a3" and K.leg_name("N16", "smoke", 1) == "u4-n16-smoke.a1"
    assert K.parse_leg("u4-tq4-off-b2.a3") == dict(arm="TQ4-OFF", block=2, attempt=3)
    assert K.block_order(1) == ("N16", "AF8", "TQ8", "AF4", "TQ4", "TQ4-OFF")
    assert K.block_order(2) == tuple(reversed(K.block_order(1)))
    assert K.block_order(3) == K.block_order(1)
    assert K.branch_name("TQ4-OFF") == "p475-u4-tq4-off"
    assert [K.predictor_of(a) for a in K.ARMS] == ["on"] * 5 + ["off"]
    with pytest.raises(ValueError):
        K.parse_leg("u4-n16-b1")
