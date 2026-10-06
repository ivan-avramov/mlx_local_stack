"""C106 driver-side belt (operator 2026-09-29): the served registry is hashed at ENTRY (in the M50
block, so every manifest carries `config_sha256`) and re-verified at EXIT before a run is declared
complete. A changed file or a changed router pid between the two refuses the completion (rows stay,
nothing is marked clean) — the router reads its registry once at start, so a path comparison alone
cannot see an in-place edit, a symlink retarget or a restart during the run."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

import bench.provenance as P
from bench import paths

pytestmark = pytest.mark.usefixtures("pin_mtp_scan")   # M58: synthetic models


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "benchmark"))


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _tmp_registry(tmp_path, monkeypatch) -> Path:
    reg = tmp_path / "reg.yaml"
    shutil.copy(REPO / "main_models.yaml", reg)
    monkeypatch.setattr(paths, "registry_path", lambda: reg)
    return reg


def _owner(monkeypatch, tmp_path, pid=999):
    state = {"pid": pid}
    monkeypatch.setattr(P, "router_owner", lambda port: {
        "pid": state["pid"], "cmdline": "mlx-serve start", "cwd": str(tmp_path),
        "env": {"MLX_SERVE_CONFIG": str(paths.registry_path())}})
    return state


def _edit(reg: Path):
    reg.write_text(reg.read_text() + "\n# edited during the run\n")


def test_entry_block_carries_the_served_file_sha256(tmp_path, monkeypatch):
    reg = _tmp_registry(tmp_path, monkeypatch); _owner(monkeypatch, tmp_path)
    blk = P.assert_served_config("http://localhost:8000")
    assert blk["config_sha256"] == _sha(reg)


def test_exit_check_passes_when_nothing_changed(tmp_path, monkeypatch):
    reg = _tmp_registry(tmp_path, monkeypatch); _owner(monkeypatch, tmp_path, pid=7)
    entry = P.assert_served_config("http://localhost:8000")
    exit_blk = P.assert_served_config_unchanged(entry, "http://localhost:8000")
    assert exit_blk["config_sha256"] == _sha(reg) and exit_blk["pid"] == 7


def test_exit_check_refuses_when_the_served_file_changed(tmp_path, monkeypatch):
    reg = _tmp_registry(tmp_path, monkeypatch); _owner(monkeypatch, tmp_path)
    entry = P.assert_served_config("http://localhost:8000")
    before = entry["config_sha256"]; _edit(reg); after = _sha(reg)
    with pytest.raises(P.ServedConfigError, match="C106") as ei:
        P.assert_served_config_unchanged(entry, "http://localhost:8000")
    assert before[:12] in str(ei.value) and after[:12] in str(ei.value)


def test_exit_check_refuses_when_the_router_pid_changed(tmp_path, monkeypatch):
    _tmp_registry(tmp_path, monkeypatch); st = _owner(monkeypatch, tmp_path, pid=1)
    entry = P.assert_served_config("http://localhost:8000")
    st["pid"] = 2
    with pytest.raises(P.ServedConfigError, match="C106.*pid"):
        P.assert_served_config_unchanged(entry, "http://localhost:8000")


# --------------------------------------------------------------------------- drivers
def test_generate_run_refuses_to_complete_when_the_served_file_changed_mid_run(tmp_path, monkeypatch, capsys):
    import bench.generate as G
    import bench.benchmarks as B
    import bench.client as C
    reg = _tmp_registry(tmp_path, monkeypatch); _owner(monkeypatch, tmp_path)
    monkeypatch.setattr(G, "RESULTS", tmp_path / "res")
    monkeypatch.setattr(B, "load", lambda b, lim, seed: [{"id": "t1", "prompt": "p"}])
    monkeypatch.setattr(C, "preload", lambda m, **k: 0.0)

    def probe(m, msgs, params, timeout=3600, tools=None):
        _edit(reg)                                   # the runtime changes under the run
        return {"content": "ok", "reasoning": "", "tool_calls": [], "prompt_tokens": 1,
                "completion_tokens": 10, "decode_tps": 1.0, "peak_mem_gb": 1.0,
                "finish_reason": "stop", "wall_s": 0.1, "raw_timings": {}}
    monkeypatch.setattr(C, "probe", probe)
    with pytest.raises(P.ServedConfigError, match="C106"):
        G.run(["m"], ["aime"], {})
    assert "COMPLETE" not in capsys.readouterr().out


def test_vision_gate_refuses_to_summarize_and_records_the_drift_in_the_manifest(tmp_path, monkeypatch, capsys):
    import vision_gate as VG
    from bench.tests.conftest import probe_result
    reg = _tmp_registry(tmp_path, monkeypatch); _owner(monkeypatch, tmp_path)
    out = tmp_path / "results" / "m" / "vision_gate.v1.jsonl"
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(json.dumps({"id": "cocoval2017-000", "image_ref": {"dataset": "d", "revision": "r", "split": "val", "index": 7},
                                  "meta": {"image_format": "JPEG"}, "captions": ["a", "b"]}) + "\n")
    img = tmp_path / "img.jpg"; img.write_bytes(b"\xff\xd8\xff\xe0fake\xff\xd9")
    monkeypatch.setattr(VG, "resolve_image", lambda row, cache: str(img))
    calls = {"n": 0}

    def probe(model, messages, params, timeout=3600, tools=None):
        calls["n"] += 1
        if calls["n"] == 1:
            _edit(reg)
        return probe_result(content="desc" if calls["n"] == 1 else "PASS", completion_tokens=5)
    monkeypatch.setattr(VG.client, "probe", probe)
    monkeypatch.setattr(VG.model_params, "params_for", lambda model, profile: {"thinking_budget": 1000, "max_tokens": 2000})
    monkeypatch.setattr(VG.model_params, "registry_context_limit", lambda model: None)
    monkeypatch.setattr(VG.generate, "rows_for_rate", lambda model, bench: [])
    monkeypatch.setattr(VG.provenance, "gather", lambda model, registry_path=None, profile="production",
                        overrides=None, runtime=None, tune=None, router=None:
                        {"model": model, "runtime": dict(runtime or {}), "router": dict(router)})
    rc = VG.main(["--model", "m", "--corpus", str(corpus), "--out", str(out)])
    assert rc == 2
    assert "C106" in capsys.readouterr().err
    assert not VG.summary_path_for(out).exists()
    man = json.loads(VG.manifest_path_for(out).read_text())
    assert man["served_config_drift"]["entry_sha256"] != man["served_config_drift"]["exit_sha256"]
    assert out.exists()                                   # rows stay; they are just not clean


def test_stack_smoke_aborts_when_the_served_file_changed(tmp_path, monkeypatch, capsys):
    from bench import stack_smoke as S
    reg = _tmp_registry(tmp_path, monkeypatch); _owner(monkeypatch, tmp_path)
    monkeypatch.setattr(S, "params_for", lambda m, profile: {"max_tokens": 10, "thinking_budget": 5})
    monkeypatch.setattr(S.client, "preload", lambda m, **k: None)

    def case(model, params):
        _edit(reg)
        return True, {"finish_reason": "stop", "completion_tokens": 1, "prompt_tokens": 1, "wall_s": 0.1}, "ok"
    monkeypatch.setattr(S, "CASES", [("edit", case)])
    out = tmp_path / "smoke.json"
    monkeypatch.setattr(sys, "argv", ["stack_smoke", "--model", "m", "--tag", "t", "--out", str(out)])
    assert S.main() == 2
    doc = json.loads(out.read_text())
    assert doc["status"] == "aborted" and "C106" in doc["error"]
