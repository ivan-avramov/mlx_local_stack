"""M64 step 4a: chain_ops parametrised by an arm spec (validate_leg, identity checks); defaults stay the tg1 values."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from bench import arm_adapter as aa
from bench import arm_opencode as ao
from bench import arm_specs
from bench import chain_ops as co

REPO = Path(__file__).resolve().parents[3]
PICK1 = co.PICK1
WORKER = {"pid": 4242, "create_time": 1700000000.5, "model_path": "caslca/" + PICK1, "registry_sha256": "a" * 64}
FROZEN = "Mon Jan 05 2026"
OC = arm_specs.OC


def fap():
    spec = importlib.util.spec_from_file_location("fake_arm_probe_t", REPO / "benchmark/chains/m64/fake_arm_probe.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["fake_arm_probe_t"] = m
    sys.path.insert(0, str(REPO / "benchmark/chains/c147"))
    spec.loader.exec_module(m)
    return m


FAP = fap()


def pinned_for(out, spec):
    man = json.loads(out.with_suffix(".manifest.json").read_text())
    ident = co.runtime_identity(man, spec.runtime_pinned)
    return {**ident, "serving_path": man["git"]["serving_path"], "registry_sha256": man["registry"]["sha256"]}, man


@pytest.fixture
def leg(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    ids = ["python/alpha", "python/beta"]
    out = tmp_path / "m64/s1" / f"{PICK1}.s1.oc_python.jsonl"
    FAP.write_leg(out, "oc", OC.label, PICK1, "python", 1001, ids, WORKER, tmp_path, frozen=FROZEN)
    pinned, man = pinned_for(out, OC)
    leg = dict(session="s1", model=PICK1, lang="python", seed_base=1001, expected_ids=ids, out=str(out), rc=0,
               draft_kind="off")
    return leg, pinned, man, out, tmp_path


def test_the_oc_spec_equals_its_adapter():
    assert OC.label == ao.M64_LABEL and OC.arm_id == ao.OpencodeArm.arm_id
    assert OC.generation_fields == ao.OpencodeArm.GENERATION_FIELDS
    assert (REPO / OC.probe).is_file() and OC.evidence_dir == "transcripts/oc"
    assert OC.evidence_policy == ao.m64_evidence().as_dict() and OC.evidence_policy["namespace"] == OC.evidence_dir
    assert set(OC.generation_fields) <= set(OC.runtime_pinned) | {"sampling_profile"}
    assert ao.OpencodeArm(None, mode="m64").evidence_root(Path("/w")) == Path("/w") / OC.evidence_dir
    rt = {k: k for k in OC.generation_fields}
    assert OC.composite(rt) == aa.arm_generation_sha256("oc", rt, OC.generation_fields)
    with pytest.raises(aa.ArmRefused, match="no chain spec"):
        arm_specs.spec_for("pi")


def test_a_valid_arm_leg_validates_under_its_spec(leg):
    lg, pinned, man, out, wd = leg
    assert co.validate_leg(lg, pinned, wd, policy_sha=man["runtime"]["scaffold_policy_sha256"], frozen_prompt_date=FROZEN,
                           spec=OC) == []
    assert co.malformed_identity(man, OC) == []


def test_the_tg1_defaults_do_not_accept_an_arm_leg(leg):
    lg, pinned, man, out, wd = leg
    why = co.validate_leg(lg, pinned, wd, policy_sha=man["runtime"]["scaffold_policy_sha256"], frozen_prompt_date=FROZEN)
    assert any(w.startswith("runtime_scaffold") for w in why) and any(w.startswith("row_scaffold") for w in why)
    assert "runtime_generation_identity_sha256_inconsistent" in co.malformed_identity(man)      # the tg1 recipe has no arm


def test_a_row_of_another_arm_label_or_a_tampered_composite_is_caught_under_the_spec(leg):
    lg, pinned, man, out, wd = leg
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    rows[0]["scaffold"] = "opencode-v2-web-tg1"
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert any(w.startswith("row_scaffold") for w in co.validate_leg(
        lg, pinned, wd, policy_sha=man["runtime"]["scaffold_policy_sha256"], frozen_prompt_date=FROZEN, spec=OC))
    man["runtime"]["generation_identity_sha256"] = "0" * 64
    out.with_suffix(".manifest.json").write_text(json.dumps(man))
    assert "runtime_generation_identity_sha256_inconsistent" in co.malformed_identity(man, OC)


def test_the_spec_decides_which_manifest_fields_are_pinned(leg):
    lg, pinned, man, out, wd = leg
    narrow = arm_specs.ArmSpec(**{**OC.__dict__, "runtime_pinned": ("scaffold_policy_sha256", "probe_code_sha256",
                                                                    "generation_identity_sha256")})
    assert set(co.runtime_identity(man, narrow.runtime_pinned)) == set(narrow.runtime_pinned)
    assert set(co.runtime_identity(man)) == set(co.RUNTIME_PINNED)                          # the default is unchanged


def test_chain_ops_defaults_are_the_tg1_values():
    assert co.SCAFFOLD == "opencode-v2-web-tg1"
    import inspect
    assert inspect.signature(co.validate_leg).parameters["spec"].default is None
    assert inspect.signature(co.ChainOps.a4_gate).parameters["scaffold"].default == co.SCAFFOLD
    assert "run_oc_probe" in co.BUSY and "run_m64_chain.py" in co.SELF_MARKERS


from bench.tests.test_chain_ops import ops, Sh      # noqa: E402,F401  (fixture reuse)


def test_a4_gate_takes_the_scaffold_of_the_arm_being_gated(ops):
    ops.a4_gate(PICK1, "t", scaffold=OC.label)
    cmd = [c for c in ops._sh.calls if "session_pinning_gate" in " ".join(c)][-1]
    assert cmd[cmd.index("--scaffold") + 1] == "opencode-v2-web-tg1c"
