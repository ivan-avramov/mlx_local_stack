"""M64 step 4a: the A4-equivalent gate leg for the oc arm (carrier opencode-v2-web-tg1c): the receipt it writes names the
SAME carrier sha the arm probe will run (the adapter's selection), and the leg refuses while the D2 service is the stub."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bench import arm_adapter as aa
from bench import arm_opencode as ao
from bench import tg1_runner
from bench.tests.test_c147_a4_gate import fake, run, run_root, config_tree     # noqa: F401  (fixtures and helpers)
from bench.tests.test_session_pinning_a4_v2 import gate, FakeLogTail, row     # noqa: F401

TG1C = "opencode-v2-web-tg1c"


@pytest.fixture
def tg1c(fake, monkeypatch):
    module, binary, repo = fake
    doc = json.loads((repo / "benchmark/opencode_bench_v2_web_tg1.json").read_text())
    doc["compaction"] = {"auto": False}
    doc["permissions"] = [dict(action="websearch", resource="*", effect="deny")]
    (repo / "benchmark/opencode_bench_v2_web_tg1.json").write_text(json.dumps(doc, sort_keys=True) + "\n")
    monkeypatch.setattr(tg1_runner, "CARRIER", repo / "benchmark/opencode_bench_v2_web_tg1.json")
    (repo / "benchmark/opencode_plugins/datefreeze.js").write_text("// fake datefreeze\n")
    return module, binary, repo


def test_the_gate_offers_the_m64_scaffold():
    import importlib.util
    spec = importlib.util.spec_from_file_location("gate_choices", Path(__file__).resolve().parents[3] / "scripts/session_pinning_gate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    src = (Path(__file__).resolve().parents[3] / "scripts/session_pinning_gate.py").read_text()
    assert '"opencode-v2-web-tg1c"' in src


def test_the_tg1c_gate_refuses_while_the_search_service_is_the_stub(tg1c, tmp_path):
    module, binary, repo = tg1c
    with pytest.raises(aa.ArmRefused, match="shared search service"):
        run(module, binary, tmp_path, TG1C)


def test_the_tg1c_gate_runs_the_carrier_the_arm_probe_will_run(tg1c, tmp_path, monkeypatch):
    from bench import m64_search
    module, binary, repo = tg1c
    monkeypatch.setattr(m64_search, "service", lambda: ao.OfflineTestSearchService())
    result = run(module, binary, tmp_path, TG1C)
    assert result["pass"] is True
    tree = config_tree(run_root(tmp_path))
    import run_opencode_probe_v2 as p
    want = ao.OpencodeArm(p, mode="m64", search=ao.OfflineTestSearchService()).selection()["bytes"]
    assert tree["opencode.json"] == hashlib.sha256(want).hexdigest()
    assert result["carrier_sha256"] == hashlib.sha256(want).hexdigest()
    assert set(tree) == {"opencode.json", "plugins/noretry.js", "plugins/toolbounds.js"}


def test_the_search_service_has_one_named_switch_point():
    from bench import m64_search
    assert isinstance(m64_search.service(), aa.UnavailableSearchService)
    assert isinstance(ao.OpencodeArm(None, mode="m64").search, aa.UnavailableSearchService)
