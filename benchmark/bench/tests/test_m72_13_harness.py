"""M72 1.3 (stack side): the end-to-end prefill harness gains ``--capacity`` and the ``tq4_m72`` variant; the registry pick is not
changed; the serving-path and box notes record the mode (spec "Scope" item 3, A5 / A8).

The harness's real legs load `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` and are never run here: ``main`` / ``run_all`` are driven with the leg runner and
the subprocess stubbed, and only the command line and namespace they build are asserted.

Every test is classed in its comment: [new] exercises new behaviour, [invariant] preserves an invariant of today's code.
"""

import importlib
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
SPIKES = REPO / "benchmark" / "spikes"
PICK = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.syspath_prepend(str(SPIKES))
    sys.modules.pop("m72_e2e_prefill", None)
    return importlib.import_module("m72_e2e_prefill")


def run_main(harness, monkeypatch, *argv):
    seen = {}
    monkeypatch.setattr(harness, "run_leg", lambda a: seen.setdefault("args", a))
    monkeypatch.setattr(sys, "argv", ["m72_e2e_prefill.py", *argv])
    harness.main()
    return seen["args"]


# ------------------------------------------------------------------ leg arguments
# [invariant] the existing variants still parse
@pytest.mark.parametrize("variant", ("native16", "tq4_prod", "tq4_p2s"))
def test_existing_variants_still_parse(harness, monkeypatch, variant):
    a = run_main(harness, monkeypatch, "--leg", "--variant", variant, "--tokens", "4096")
    assert a.variant == variant and a.tokens == 4096


# [new] the production mode is a variant
def test_tq4_m72_is_a_variant(harness, monkeypatch):
    a = run_main(harness, monkeypatch, "--leg", "--variant", "tq4_m72", "--tokens", "4096")
    assert a.variant == "tq4_m72"


# [new] --capacity defaults to --tokens and is independent of it when given (A5: capacity 262,144 in both legs at 131,072 tokens)
def test_capacity_defaults_to_tokens(harness, monkeypatch):
    a = run_main(harness, monkeypatch, "--leg", "--variant", "tq4_m72", "--tokens", "4096")
    assert (a.capacity or a.tokens) == 4096


def test_capacity_is_independent_of_tokens(harness, monkeypatch):
    a = run_main(harness, monkeypatch, "--leg", "--variant", "tq4_p2s", "--tokens", "131072", "--capacity", "262144")
    assert a.tokens == 131072 and a.capacity == 262144


# ------------------------------------------------------------------ the driver passes both to every leg's own process
def run_driver(harness, monkeypatch, *argv):
    cmds = []

    def fake_run(cmd, **kw):
        cmds.append(list(cmd))
        row = {"prefill_s": 1.0, "tok_per_s": 1.0, "os_peak_GB": 1.0, "os_peak_delta_GB": 1.0, "last_logit_top5": [1]}
        return SimpleNamespace(returncode=0, stdout=json.dumps(row) + "\n", stderr="")

    monkeypatch.setattr(harness, "gates", lambda: ({"ac": True}, {"gpu": True}, True))
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(sys, "argv", ["m72_e2e_prefill.py", *argv])
    harness.main()
    return cmds


def flag_value(cmd, flag):
    return cmd[cmd.index(flag) + 1] if flag in cmd else None


# [new] each leg's process gets its variant and the capacity (a leg's capacity is never silently its token count)
def test_driver_passes_variant_and_capacity_to_each_leg(harness, monkeypatch):
    cmds = run_driver(
        harness, monkeypatch, "--legs", "tq4_p2s:layer", "tq4_m72", "--tokens", "131072", "--capacity", "262144", "--idle", "0"
    )
    assert [flag_value(c, "--variant") for c in cmds] == ["tq4_p2s", "tq4_m72"]
    assert all(flag_value(c, "--capacity") == "262144" for c in cmds)
    assert all(flag_value(c, "--tokens") == "131072" for c in cmds)


# [new] without --capacity a leg's effective capacity is its token count (either omitted or equal)
def test_driver_default_capacity_is_the_token_count(harness, monkeypatch):
    cmds = run_driver(harness, monkeypatch, "--legs", "tq4_m72", "--tokens", "8192", "--idle", "0")
    assert flag_value(cmds[0], "--capacity") in (None, "8192")


# [invariant] the existing leg spec forms keep working in the same driver (variant:eval)
def test_driver_keeps_the_variant_eval_spec(harness, monkeypatch):
    cmds = run_driver(harness, monkeypatch, "--legs", "tq4_p2s:every2", "--tokens", "4096", "--idle", "0")
    assert flag_value(cmds[0], "--variant") == "tq4_p2s" and flag_value(cmds[0], "--eval") == "every2"


# ------------------------------------------------------------------ no registry pick change; notes
def registry():
    return yaml.safe_load((REPO / "main_models.yaml").read_text())


def pick_entry():
    return next(m for m in registry()["models"] if m.get("name") == PICK)


# [invariant] the pick stays native16 until 1.4 certifies: kv_bits 0, no tq4_attention anywhere in the registry
def test_registry_pick_is_unchanged():
    entry = pick_entry()
    assert entry.get("kv_bits", 0) == 0
    assert "tq4_attention" not in entry
    assert not [m["name"] for m in registry()["models"] if "tq4_attention" in m]


# [invariant] the pick still ships fused_v1 + joint_v1 + MTP
def test_registry_pick_keeps_its_native_policies():
    entry = pick_entry()
    assert entry.get("attention_policy") == "fused_v1" and entry.get("mtp_verify_scan") == "joint_v1"
    assert entry.get("draft_kind") == "mtp"


# [new] serving-path and box notes carry the mode (the docs are what the next session reads)
def test_serving_path_documents_the_registry_key_and_values():
    # amended (delivery 3): only what the spec pins — serving-path documents the registry key and its values
    text = (REPO / "docs" / "serving-path.md").read_text()
    assert "tq4_attention" in text and "m72_v1" in text and "m72_exact" in text


def test_box_notes_has_an_m72_1_3_entry():
    assert "M72 1.3" in (REPO / "docs" / "box-notes.md").read_text()
