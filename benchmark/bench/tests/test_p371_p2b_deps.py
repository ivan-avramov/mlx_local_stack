"""P371 phase 2b (plan 3.1 dependency rule, plan 4 R30): the core imports no corpus / client / grader module (the 2a
leftovers: `structured_grade`, `datefreeze`), the join timeout and grader constants come from the corpus identity, the
frozen-date shape is the adapter's, and web-evidence extraction rules are arm-spec data, not an adapter method."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from bench import arm_adapter as aa
from bench import arm_opencode as ao
from bench import arm_runner
from bench import arm_specs
from bench import corpus as cp
from bench import corpus_tg1
from bench import structured_grade as sg
from bench import web_evidence as we
from bench.tests.arm_neutral import NeutralArm, NeutralCorpus
from bench.tests.p371_world import MODEL, manifest, rows, run_core, world      # noqa: F401  (fixture)

BENCH = Path(__file__).resolve().parents[1]


def static_imports(path):
    """Every bench module the file imports ANYWHERE (module level or inside a function)."""
    found = set()
    for node in ast.walk(ast.parse(Path(path).read_text())):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "bench" and len(parts) > 1:
                    found.add(parts[1])
        elif isinstance(node, ast.ImportFrom):
            if node.level and not node.module:
                found |= {a.name for a in node.names}
            elif node.level:
                found.add(node.module.split(".")[0])
            elif (node.module or "").startswith("bench."):
                found.add(node.module.split(".")[1])
            elif node.module == "bench":
                found |= {a.name for a in node.names}
    return found


BANNED = {"structured_grade", "datefreeze", "arm_opencode", "corpus_tg1", "m64_search", "tg1_runner", "chain_hooks",
          "web_evidence", "chain_core", "schedules", "chain_rows", "tg1_score", "row_scores", "answer_key",
          "opencode_v2_core", "opencode_export", "toolwindows"}


def test_the_core_static_imports_contain_no_corpus_client_or_grader_module():
    got = static_imports(BENCH / "arm_runner.py")
    assert not (got & BANNED), sorted(got & BANNED)
    assert not [m for m in got if m.startswith(("tg2", "opencode_"))], sorted(got)


def test_the_static_import_scan_sees_function_level_imports(tmp_path):
    sample = tmp_path / "x.py"
    sample.write_text("def f():\n    from . import structured_grade as sg\n    import bench.datefreeze\n")
    assert {"structured_grade", "datefreeze"} <= static_imports(sample)


def test_the_corpus_contract_owns_snapshot_and_manifest():
    assert {"snapshot", "manifest"} <= cp.Corpus.__abstractmethods__


def test_the_tg1_corpus_delegates_snapshot_and_manifest_to_the_grader(tmp_path):
    work, private = tmp_path / "w", tmp_path / "p"
    work.mkdir(), private.mkdir()
    (work / "a.py").write_text("x = 1\n")
    corpus = corpus_tg1.Tg1Corpus(tmp_path / "universe.json")
    assert corpus.manifest(work) == sg.manifest(work)
    with corpus.snapshot(work, private, 3) as snap, sg.snapshot(work, private, boundary=3) as ref:
        assert snap.boundary == 3 and snap.manifest == ref.manifest == sg.manifest(work)
        assert (Path(snap.path) / "a.py").read_text() == "x = 1\n" and Path(snap.path) != work


def test_the_join_timeout_is_a_pure_function_of_the_grader_timeouts(monkeypatch):
    assert arm_runner.grade_join_timeout_s({"python": 300, "go": 300}) == 660
    assert arm_runner.grade_join_timeout_s({"fake": 9}) == 2 * 9 + arm_runner.GRADE_JOIN_OVERHEAD_S
    monkeypatch.setattr(arm_runner, "GRADE_JOIN_OVERHEAD_S", 1)
    assert arm_runner.grade_join_timeout_s({"a": 4, "b": 2}) == 9


def test_the_policy_takes_grader_constants_and_the_join_timeout_from_the_corpus_identity(world, monkeypatch):
    seen = []
    real = arm_runner.GradeWorker
    monkeypatch.setattr(arm_runner, "GradeWorker", lambda *a, **k: (seen.append(k.get("join_timeout_s")),
                                                                      real(*a, **k))[1])
    corpus = NeutralCorpus(world.tmp, timeouts={"fake": 9}, grader_version="neutral-grade-2")
    assert run_core(world, corpus=corpus)[0] == 0
    policy = manifest(world)["runtime"]["policy"]
    assert policy["grader_timeout_s"] == {"fake": 9} and policy["grader_version"] == "neutral-grade-2"
    assert policy["grade_join_timeout_s"] == 2 * 9 + arm_runner.GRADE_JOIN_OVERHEAD_S == 78
    assert seen == [78]


def test_the_frozen_date_shape_is_the_adapters_not_a_datefreeze_import(world):
    assert run_core(world, a=dict(frozen_prompt_date="2026-01-05"))[0] == 0       # the neutral client's own shape
    assert rows(world)[0]["prompt_date"] == "2026-01-05"


def test_an_adapter_refusing_the_date_refuses_the_run_before_any_spawn(world):
    class Strict(NeutralArm):
        def valid_frozen_date(self, date):
            return date == "D1"

    with pytest.raises(SystemExit, match="REFUSED.*frozen-prompt-date"):
        run_core(world, adapter=Strict(world.host))
    assert rows(world) == []


def test_opencode_keeps_its_own_date_shape():
    arm = ao.OpencodeArm(None, mode="tg1")
    assert arm.valid_frozen_date("Mon Jan 05 2026") and not arm.valid_frozen_date("2026-01-05")
    assert not arm.valid_frozen_date(None) and not arm.valid_frozen_date("Mon Jan 5 2026")


# ---------------------------------------------------------------- R30: web-evidence rules are arm-spec data
def test_no_adapter_extracts_web_evidence():
    assert not hasattr(aa.ArmAdapter, "web_evidence") and "web_evidence" not in aa.ArmAdapter.__abstractmethods__
    assert not hasattr(ao.OpencodeArm, "web_evidence")


def test_the_opencode_rules_are_the_arm_specs_data():
    spec = arm_specs.spec_for("oc")
    assert json.loads(json.dumps(spec.web_evidence_rules)) == spec.web_evidence_rules
    assert we.validate_rules(spec.web_evidence_rules) is spec.web_evidence_rules
    assert we.OPENCODE_RULES is spec.web_evidence_rules or we.OPENCODE_RULES == spec.web_evidence_rules
    assert spec.web_evidence_rules["client"] == "opencode"


def test_an_arm_spec_without_rules_is_refused():
    with pytest.raises(ValueError, match="web_evidence_rules"):
        arm_specs.ArmSpec(arm_id="oc", label="x", probe="p", generation_fields=("a",), runtime_pinned=(),
                          sha_fields=(), version_field="v", web_evidence_rules={})


def test_extraction_by_the_specs_rules_selects_exactly_what_the_adapter_method_selected(tmp_path):
    from bench.tests.test_p371_web_evidence import DOC, lines, write
    path, sha = write(tmp_path)
    out = we.extract(arm_specs.spec_for("oc").web_evidence_rules, path, sha, tmp_path / "w.jsonl")
    # the (request, tool, id, status, input) tuples the removed `OpencodeArm.web_evidence` returned for DOC
    assert [(r["request"], r["tool"], r["id"], r["status"], r["input"]) for r in lines(out["path"])] == [
        (1, "websearch", "c1", "completed", {"query": "rust borrow checker"}),
        (2, "webfetch", "c3", "completed", {"url": "https://example.test/doc"}),
        (2, "shell", "c4", "error", {"command": "curl -s https://example.test"}),
        (2, "mcp_searxng_search", "c5", "running", {"q": "x"})]
    assert DOC
