"""P371 phase 2b test support: the neutral world (fake host, patched worker / router seams) and helpers that drive the
shared item core with any adapter / corpus / evidence policy."""
from __future__ import annotations

import json
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import arm_runner
from bench import opencode_v2_core as core
from bench import provenance, toolchain
from bench import run_config as rc
from bench.tests.arm_neutral import LABEL, NeutralArm, NeutralCorpus

BENCH = Path(__file__).resolve().parents[1]
MODEL = "neutral/model"


@pytest.fixture
def world(monkeypatch, tmp_path):
    return neutral_world(monkeypatch, tmp_path)


def neutral_world(monkeypatch, tmp_path):
    """The neutral world as a plain function (the `world` fixture's body): the isolation test builds one per configuration
    inside `monkeypatch.context()` so that nothing it patches survives into the next configuration."""
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    monkeypatch.delenv("MLX_SERVE_CONFIG", raising=False)
    host = types.ModuleType("neutral_host")
    core.bind(host.__dict__)
    host.__file__ = str(BENCH.parent / "run_tg1_probe.py")
    router = dict(pid=123, config="$STACK_WORKDIR/registry.yaml", config_sha256="registry-sha")
    identity = dict(pid=1234, create_time=100, model_path="fixture/model", registry_sha256="sha")
    monkeypatch.setattr(arm_runner, "worker_identity", lambda *a: dict(identity))
    monkeypatch.setattr(arm_runner, "arm_identity_of", lambda *a: ({"flags": {}}, "e" * 64))
    monkeypatch.setattr(arm_runner, "worker_json", lambda ep: dict(configured_context_limit=262144)
                        if ep == "health" else dict(summary=dict(in_flight=0)))
    monkeypatch.setattr(provenance, "assert_served_config", lambda *a, **k: dict(router))
    monkeypatch.setattr(provenance, "assert_served_config_unchanged", lambda *a, **k: dict(router))
    monkeypatch.setattr(provenance, "_git_shas", lambda: {"serving_path": "serving-sha"})
    monkeypatch.setattr(provenance, "gather", lambda model, **kw: {"model": model, "git": {"serving_path": "serving-sha"},
                                                                  **kw})
    monkeypatch.setattr(toolchain, "current", lambda: dict(lock_sha256="l", interpreter="i", grader_image_id="g"))
    monkeypatch.setattr(toolchain, "verify", lambda t: None)
    return SimpleNamespace(host=host, tmp=tmp_path, worker=dict(identity))


def template(**over):
    return rc.PolicyTemplate(**{**dict(config_id="neutral-cfg", langs=("fake",)), **over})


def evidence(**over):
    return rc.EvidencePolicy(**{**dict(namespace="neutral_evidence", web_evidence=True, final_tree=True,
                                       worker_receipts="absent", item_barrier="off"), **over})


def args(tmp, **over):
    base = dict(model=MODEL, items="one", seed_base=77, lang="fake", out=str(tmp / "rows.jsonl"), limit=5,
                universe=None, expect_items=None, agent_system_file=None, tg1_inject=None, cancel_file=None,
                manifest_ack=None, sampling_profile=None, frozen_prompt_date="Mon Jan 05 2026", a4_v2_receipt=None,
                rerun_of=None, rerun_index=None, extra_deny_file=None, scaffold=LABEL)
    return SimpleNamespace(**{**base, **over})


def run_core(world, *, adapter=None, corpus=None, a=None, template_=None, evidence_=None, receipts=None):
    """`arm_runner.main` with the neutral defaults; returns (return code, adapter)."""
    adapter = adapter or NeutralArm(world.host)
    rc_ = arm_runner.main(world.host, adapter, args(world.tmp, **(a or {})), template=template_ or template(),
                          evidence=evidence_ or evidence(), corpus=corpus or NeutralCorpus(world.tmp),
                          receipts=receipts)
    return rc_, adapter


def rows(world):
    path = world.tmp / "rows.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


def manifest(world):
    return json.loads((world.tmp / "rows.manifest.json").read_text())
