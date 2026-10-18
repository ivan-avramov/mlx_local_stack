"""P371 phase 2a: the shared item core (`bench.arm_runner`) driven by a NON-opencode adapter and corpus, the dependency
rule (plan 3.1), the absorbed library surface and the new row / manifest fields."""
from __future__ import annotations

import ast
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import arm_runner
from bench import opencode_v2_core as core
from bench import provenance, toolchain
from bench import run_config as rc
from bench import worker_receipts as wr
from bench.tests.arm_neutral import LABEL, NeutralArm, NeutralCorpus

BENCH = Path(__file__).resolve().parents[1]
MODEL = "neutral/model"


def local_imports(path):
    found = set()
    for node in ast.walk(ast.parse(Path(path).read_text())):
        if isinstance(node, ast.ImportFrom):
            if node.level and not node.module:
                found |= {a.name for a in node.names}
            elif node.level:
                found.add(node.module.split(".")[0])
            elif (node.module or "").startswith("bench."):
                found.add(node.module.split(".")[1])
            elif node.module == "bench":
                found |= {a.name for a in node.names}
    return found


def test_the_core_imports_no_corpus_adapter_or_client_module():
    got = local_imports(BENCH / "arm_runner.py")
    banned = {"corpus_tg1", "arm_opencode", "m64_search", "opencode_v2_core", "tg1_runner", "opencode_export",
              "chain_hooks", "web_evidence", "chain_core", "schedules", "chain_rows", "tg1_score", "row_scores",
              "answer_key", "web_audit", "web_scan"}
    assert not (got & banned), sorted(got & banned)
    assert not [m for m in got if m.startswith("tg2")], got


def test_the_core_carries_the_absorbed_library():
    for name in ("GradeWorker", "PhaseHeartbeat", "grade_join_timeout_s", "validate_worker", "worker_json",
                 "worker_identity", "arm_identity_of", "RunnerCancelled", "_DiscoveryGuard", "_wait_for_ack",
                 "grade_reports", "_link_mem_kills", "CLEAN_STATUS", "HEARTBEAT_INTERVAL_S", "GRACEFUL_CLIENT_S",
                 "ACK_TIMEOUT_S", "ACK_POLL_S", "GRADE_JOIN_OVERHEAD_S", "effective_policy", "run_item", "main",
                 "print_identity"):
        assert hasattr(arm_runner, name), name


def test_validate_worker_takes_its_budgets_from_the_policy():
    model = dict(body=dict(thinking_budget=10, max_tokens=20), limit=dict(context=5))
    health, metrics = dict(configured_context_limit=5), dict(summary=dict(in_flight=0))
    with pytest.raises(Exception, match="thinking_budget"):
        arm_runner.validate_worker(model, health, metrics)
    assert arm_runner.validate_worker(model, health, metrics, budgets=dict(thinking_budget=10, max_tokens=20)) == 5


# ---------------------------------------------------------------- the neutral run
@pytest.fixture
def world(monkeypatch, tmp_path):
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
    return SimpleNamespace(host=host, tmp=tmp_path)


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


def run(world, **kw):
    adapter = NeutralArm(world.host)
    return arm_runner.main(world.host, adapter, args(world.tmp, **kw.pop("a", {})), template=kw.pop("template", template()),
                           evidence=kw.pop("evidence", evidence()), corpus=NeutralCorpus(world.tmp),
                           **kw), adapter


def test_a_neutral_adapter_and_corpus_run_the_core_end_to_end(world):
    rc_, _ = run(world)
    assert rc_ == 0
    (row,) = [json.loads(x) for x in (world.tmp / "rows.jsonl").read_text().splitlines()]
    assert row["passed"] is True and row["file_changed"] is True and row["id"] == "fake/one"
    assert row["config_id"] == "neutral-cfg" and row["arm"] == "dsh" and row["epoch_id"] is None
    assert len(row["snapshot_sha256"]) == 64 and row["token_accounting"] == "client"
    assert row["final_tree"]["manifest_sha256"] and Path(str(row["final_tree"]["manifest"]).replace(
        "$STACK_WORKDIR", str(world.tmp))).is_file()
    assert "compaction" not in row and "receipts" not in row and "shell_watchdog" not in row
    assert row["overlay_sha256"] and row["sampler_seed"] and row["seed_base"] == 77


def test_the_neutral_rows_and_manifest_name_no_opencode(world):
    run(world)
    text = (world.tmp / "rows.jsonl").read_text() + (world.tmp / "rows.manifest.json").read_text()
    assert "opencode" not in text.lower() and "OPENCODE" not in text
    man = json.loads((world.tmp / "rows.manifest.json").read_text())
    rt = man["runtime"]
    assert rt["config_id"] == "neutral-cfg" and rt["arm"] == "dsh" and rt["evidence_policy"]["namespace"] == "neutral_evidence"
    assert rt["policy"]["config_id"] == "neutral-cfg" and rt["policy"]["watchdog"] == {"mode": "off"}
    assert rt["snapshot_complete"] is True and rt["snapshot_fields"]["version"] == "1.0"
    assert "arm_config" not in rt


def test_evidence_lives_under_the_policys_namespace_and_the_final_tree_is_reserved_there(world):
    run(world)
    files = sorted(p.name for p in (world.tmp / "neutral_evidence").rglob("*") if p.is_file())
    assert any(n.endswith(".events.jsonl") for n in files) and "manifest.json" in files


def test_the_composite_uses_the_adapters_recipe(world):
    from bench import arm_adapter as aa
    _, adapter = run(world)
    rt = json.loads((world.tmp / "rows.manifest.json").read_text())["runtime"]
    assert rt["generation_identity_sha256"] == aa.arm_generation_sha256("dsh", rt, adapter.GENERATION_FIELDS)


def test_the_policy_hash_is_the_generation_policy_hash(world):
    run(world)
    rt = json.loads((world.tmp / "rows.manifest.json").read_text())["runtime"]
    import hashlib
    assert rt["scaffold_policy_sha256"] == hashlib.sha256(json.dumps(rt["policy"], sort_keys=True).encode()).hexdigest()


def test_required_receipts_without_a_source_refuse_before_any_spawn(world):
    with pytest.raises(SystemExit, match="REFUSED"):
        run(world, evidence=evidence(worker_receipts="required"))
    assert not list((world.tmp / "neutral_evidence").rglob("*.events.jsonl")) if (world.tmp / "neutral_evidence").exists() else True
    assert not (world.tmp / "rows.jsonl").exists()


def test_required_receipts_with_an_unavailable_source_refuse(world):
    with pytest.raises(SystemExit, match="REFUSED"):
        run(world, evidence=evidence(worker_receipts="required"), receipts=wr.UnavailableReceiptSource())


def test_a_language_outside_the_policy_is_refused(world):
    with pytest.raises(SystemExit, match="REFUSED"):
        run(world, a=dict(lang="rust"))


def test_an_adapter_that_disagrees_with_the_policy_on_compaction_is_refused(world):
    with pytest.raises(SystemExit, match="REFUSED"):
        run(world, template=template(compaction="on_accounted"))


def test_a_second_invocation_on_an_existing_rows_file_is_refused_not_resumed(world):
    """P371 phase 3a (plan 4 A8 / R6): probe-level resume is gone. Every invocation writes a fresh rows file (the chain
    names it `<stem>.L<leg>.<phase>.a<n>.jsonl`); a pre-existing rows file at the target path refuses, nothing appended."""
    assert run(world)[0] == 0
    before = (world.tmp / "rows.jsonl").read_bytes()
    with pytest.raises(SystemExit, match="REFUSED.*rows file"):
        run(world)
    assert (world.tmp / "rows.jsonl").read_bytes() == before and len(before.splitlines()) == 1


def test_a_stray_manifest_without_a_rows_file_also_refuses(world):
    (world.tmp / "rows.manifest.json").write_text("{}")
    with pytest.raises(SystemExit, match="REFUSED"):
        run(world)
    assert not (world.tmp / "rows.jsonl").exists()


def test_print_identity_runs_without_a_router(world, capsys):
    adapter = NeutralArm(world.host)
    a = args(world.tmp)
    assert arm_runner.print_identity(world.host, adapter, a, template=template(), corpus=NeutralCorpus(world.tmp)) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["arm"] == "dsh" and out["config_id"] == "neutral-cfg" and "opencode" not in json.dumps(out).lower()
    assert out["polyglot_sha"] == "7" * 40 and len(out["generation_identity_sha256"]) == 64


def test_the_host_is_checked_at_entry(world):
    bad = SimpleNamespace()
    with pytest.raises(Exception, match="Host helper"):
        arm_runner.main(bad, NeutralArm(bad), args(world.tmp), template=template(), evidence=evidence(),
                        corpus=NeutralCorpus(world.tmp))


def test_policy_template_builds_a_generation_policy():
    t = template()
    assert t.config_id == "neutral-cfg" and t.langs == ("fake",) and t.compaction == "off"
    with pytest.raises(ValueError):
        template(compaction="bogus")
    _ = sys
