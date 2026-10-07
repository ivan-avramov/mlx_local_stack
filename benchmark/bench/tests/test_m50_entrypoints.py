"""M50: every bench driver / probe REFUSES before its first request when the process owning the
router port serves a different `MLX_SERVE_CONFIG` than the driver's `paths.registry_path()`, or when
nothing owns the port — nonzero exit, nothing recorded. On a match the `router` block
({pid, config, ...}) is stamped into the tool's result.

The conftest autouse fixture makes the tripwire PASS by default for the rest of the suite; these tests
override `provenance.router_owner` explicitly.
"""
import json
import sys
from pathlib import Path

import pytest

import bench.provenance as P

pytestmark = pytest.mark.usefixtures("pin_mtp_scan")   # M58: synthetic models


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "benchmark"))


def _refusing(monkeypatch):
    monkeypatch.setattr(P, "router_owner", lambda port: None)


def _passing(monkeypatch, tmp_path, pid=999):
    from bench import paths
    monkeypatch.setattr(P, "router_owner", lambda port: {
        "pid": pid, "cmdline": "mlx-serve start", "cwd": str(tmp_path),
        "env": {"MLX_SERVE_CONFIG": str(paths.registry_path())}})


# --------------------------------------------------------------------------- run.py generate
def test_generate_run_refuses_before_precheck_and_writes_nothing(tmp_path, monkeypatch):
    import bench.generate as G
    import bench.benchmarks as B
    import bench.client as C
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    monkeypatch.setattr(B, "load", lambda b, lim, seed: [{"id": "t1", "prompt": "p"}])
    called = {"preload": 0, "precheck": 0}
    monkeypatch.setattr(C, "preload", lambda m, **k: called.__setitem__("preload", 1))
    real = G.provenance_precheck
    monkeypatch.setattr(G, "provenance_precheck",
                        lambda *a, **k: (called.__setitem__("precheck", 1), real(*a, **k))[1])
    _refusing(monkeypatch)
    with pytest.raises(RuntimeError, match="M50"):
        G.run(["m"], ["aime"], {})
    assert called == {"preload": 0, "precheck": 0}
    assert list(tmp_path.rglob("*")) == []


def test_generate_run_stamps_router_into_the_manifest(tmp_path, monkeypatch):
    import bench.generate as G
    import bench.benchmarks as B
    import bench.client as C
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    monkeypatch.setattr(B, "load", lambda b, lim, seed: [{"id": "t1", "prompt": "p"}])
    monkeypatch.setattr(C, "preload", lambda m, **k: 0.0)
    monkeypatch.setattr(C, "probe", lambda m, msgs, params, timeout=3600, tools=None: {
        "content": "ok", "reasoning": "", "tool_calls": [], "prompt_tokens": 1,
        "completion_tokens": 10, "decode_tps": 1.0, "peak_mem_gb": 1.0,
        "finish_reason": "stop", "wall_s": 0.1, "raw_timings": {}})
    _passing(monkeypatch, tmp_path, pid=31337)
    G.run(["m"], ["aime"], {})
    man = json.loads((tmp_path / "m" / "aime.manifest.json").read_text())
    assert man["router"]["pid"] == 31337 and man["router"]["config"]


# --------------------------------------------------------------------------- stack_smoke
def test_stack_smoke_refuses_with_exit_2_and_no_file(tmp_path, monkeypatch, capsys):
    from bench import stack_smoke as S
    monkeypatch.setattr(S, "params_for", lambda m, profile: {"max_tokens": 10, "thinking_budget": 5})
    monkeypatch.setattr(S.client, "preload", lambda m, **k: pytest.fail("preload before tripwire"))
    _refusing(monkeypatch)
    out = tmp_path / "smoke.json"
    monkeypatch.setattr(sys, "argv", ["stack_smoke", "--model", "m", "--tag", "t", "--out", str(out)])
    assert S.main() == 2
    assert not out.exists()
    assert "M50" in capsys.readouterr().err


def test_stack_smoke_records_router_on_pass(tmp_path, monkeypatch):
    from bench import stack_smoke as S
    monkeypatch.setattr(S, "params_for", lambda m, profile: {"max_tokens": 10, "thinking_budget": 5})
    monkeypatch.setattr(S.client, "preload", lambda m, **k: 0.0)
    monkeypatch.setattr(S, "CASES", [("noop", lambda m, p: (True, {"finish_reason": "stop", "completion_tokens": 1}, "ok"))])
    _passing(monkeypatch, tmp_path, pid=5150)
    out = tmp_path / "smoke.json"
    monkeypatch.setattr(sys, "argv", ["stack_smoke", "--model", "m", "--tag", "t", "--out", str(out)])
    assert S.main() == 0
    assert json.loads(out.read_text())["router"]["pid"] == 5150


# --------------------------------------------------------------------------- parity_replay
def _stub_parity_state(monkeypatch, R):
    """M58: parity_replay resolves the served scan at entry and records the worker per row."""
    monkeypatch.setattr(R.provenance, "assert_serving_state", lambda m, registry_path=None, expect=None: {
        "mtp_verify_scan": "per_query", "mtp_verify_scan_source": "worker"})
    monkeypatch.setattr(R.provenance, "_runtime_block", lambda *a, **k: {"mtp_verify_scan": "per_query"})
    monkeypatch.setattr(R.provenance, "worker_serving_facts", lambda *a, **k: {"model": "m"})
    monkeypatch.setattr(R.provenance, "_git_shas", lambda: {"serving_path": {"src/mlx-vlm": "c", "src/mlx-serve": "d"}})


def _parity_args(tmp_path, frozen):
    import argparse
    return argparse.Namespace(frozen=str(frozen), models=None, out=str(tmp_path / "rep.json"),
                              resume=False, tag="t")


def test_parity_replay_refuses_and_writes_nothing(tmp_path, monkeypatch, capsys):
    from bench import parity_replay as R
    frozen = tmp_path / "frozen.json"
    monkeypatch.setattr(R, "load_requests", lambda f, models: [
        {"model": "m", "bench": "b", "id": "i", "seed": 1, "payload": {"max_tokens": 10}}])
    monkeypatch.setattr(R.client, "preload", lambda m, **k: pytest.fail("preload before tripwire"))
    _refusing(monkeypatch)
    a = _parity_args(tmp_path, frozen)
    assert R.run(a) == 2
    assert not Path(a.out).exists()
    assert "M50" in capsys.readouterr().err


def test_parity_replay_records_router_on_pass(tmp_path, monkeypatch):
    from bench import parity_replay as R
    monkeypatch.setattr(R, "load_requests", lambda f, models: [
        {"model": "m", "bench": "b", "id": "i", "seed": 1, "payload": {"max_tokens": 10}}])
    monkeypatch.setattr(R.client, "preload", lambda m, **k: 0.0)
    monkeypatch.setattr(R, "_post", lambda payload, timeout: {
        "choices": [{"message": {"content": "x"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1}})   # M58 AC11: usage is required
    _stub_parity_state(monkeypatch, R)
    _passing(monkeypatch, tmp_path, pid=616)
    a = _parity_args(tmp_path, tmp_path / "frozen.json")
    assert R.run(a) == 0
    assert json.loads(Path(a.out).read_text())["router"]["pid"] == 616


# --------------------------------------------------------------------------- session_cache_probe
def test_session_cache_probe_refuses_before_loading(tmp_path, monkeypatch, capsys):
    from bench import session_cache_probe as SCP
    monkeypatch.setattr(SCP, "_post", lambda *a, **k: pytest.fail("request before tripwire"))
    _refusing(monkeypatch)
    out = tmp_path / "scp.json"
    rc = SCP.main(["--model", "m", "--legs", "", "--workdir", str(tmp_path), "--out", str(out),
                   "--log", str(tmp_path / "none.log")])
    assert rc == 2 and not out.exists()
    assert "M50" in capsys.readouterr().err


def test_session_cache_probe_records_router_on_pass(tmp_path, monkeypatch):
    from bench import session_cache_probe as SCP
    monkeypatch.setattr(SCP, "_post", lambda *a, **k: {})
    monkeypatch.setattr(SCP, "worker_pid", lambda m: None)
    monkeypatch.setattr(SCP, "footprint", lambda pid: None)
    _passing(monkeypatch, tmp_path, pid=808)
    out = tmp_path / "scp.json"
    rc = SCP.main(["--model", "m", "--legs", "", "--workdir", str(tmp_path), "--out", str(out),
                   "--log", str(tmp_path / "none.log")])
    assert rc == 0
    assert json.loads(out.read_text())["router"]["pid"] == 808


# --------------------------------------------------------------------------- vision_gate
def test_vision_gate_refuses_before_reading_the_corpus(tmp_path, monkeypatch, capsys):
    import vision_gate as VG
    monkeypatch.setattr(VG, "load_corpus", lambda p, lim: pytest.fail("corpus before tripwire"))
    _refusing(monkeypatch)
    out = tmp_path / "vg.jsonl"
    rc = VG.main(["--model", "m", "--out", str(out), "--corpus", str(tmp_path / "c.jsonl"),
                  "--url", "http://localhost:8000"])
    assert rc == 2 and not out.exists()
    assert "M50" in capsys.readouterr().err


def test_vision_gate_records_router_in_the_summary(tmp_path, monkeypatch):
    import vision_gate as VG
    monkeypatch.setattr(VG, "load_corpus", lambda p, lim: [])
    monkeypatch.setattr(VG.model_params, "params_for", lambda m, profile: {"max_tokens": 10, "thinking_budget": 5})
    monkeypatch.setattr(VG.model_params, "registry_context_limit", lambda m: 1000)
    _passing(monkeypatch, tmp_path, pid=1701)
    out = tmp_path / "vg.jsonl"
    rc = VG.main(["--model", "m", "--out", str(out), "--corpus", str(tmp_path / "c.jsonl"),
                  "--timeout", "5"])
    assert rc == 0
    assert json.loads(VG.summary_path_for(out).read_text())["router"]["pid"] == 1701


# --------------------------------------------------------------------------- round 2 (Codex cold review)
def test_run_py_generate_refuses_before_the_roster_request(tmp_path, monkeypatch, capsys):
    """Without --models, `_resolve` GETs /v1/models — that is the first request and must come AFTER
    the tripwire."""
    import run as R
    import argparse
    monkeypatch.setattr(R.client, "roster", lambda: pytest.fail("roster request before tripwire"))
    _refusing(monkeypatch)
    args = argparse.Namespace(models=None, benches="aime", limit="", tier=None, thinking_budget=None,
                              temp=None, seed=0, chunk_minutes=1.0, chunks="all", order="roundrobin",
                              sampling_profile="deployed", probe_timeout=None, clean_stale=False,
                              samples=1, seed_base=0, ids=None, tune=None, depth_tokens=None,
                              reasoning_effort=None, restart_on_loop=False, presence_penalty=None,
                              frequency_penalty=None, repetition_penalty=None)
    with pytest.raises(RuntimeError, match="M50"):
        R.cmd_generate(args)


def test_stack_smoke_abort_record_carries_router(tmp_path, monkeypatch):
    from bench import stack_smoke as S
    monkeypatch.setattr(S, "params_for", lambda m, profile: {"max_tokens": 10, "thinking_budget": 5})
    monkeypatch.setattr(S.client, "preload", lambda m, **k: 0.0)

    def boom(m, p):
        raise ConnectionError("transport")
    monkeypatch.setattr(S, "CASES", [("boom", boom)])
    _passing(monkeypatch, tmp_path, pid=77)
    out = tmp_path / "smoke.json"
    monkeypatch.setattr(sys, "argv", ["stack_smoke", "--model", "m", "--tag", "t", "--out", str(out)])
    assert S.main() == 2
    assert json.loads(out.read_text())["router"]["pid"] == 77


def test_parity_replay_abort_record_carries_router(tmp_path, monkeypatch):
    from bench import parity_replay as R
    monkeypatch.setattr(R, "load_requests", lambda f, models: [
        {"model": "m", "bench": "b", "id": "i", "seed": 1, "payload": {"max_tokens": 10}}])
    monkeypatch.setattr(R.client, "preload", lambda m, **k: 0.0)

    def boom(payload, timeout):
        raise ConnectionError("transport")
    monkeypatch.setattr(R, "_post", boom)
    _stub_parity_state(monkeypatch, R)
    _passing(monkeypatch, tmp_path, pid=78)
    a = _parity_args(tmp_path, tmp_path / "frozen.json")
    assert R.run(a) == 2
    assert json.loads(Path(a.out).read_text())["router"]["pid"] == 78


def test_refusal_happens_before_the_output_directory_exists(tmp_path, monkeypatch):
    """Codex round 1: mkdir ran before the guard in three tools. Use a NONEXISTENT parent."""
    from bench import stack_smoke as S, parity_replay as R
    _refusing(monkeypatch)
    monkeypatch.setattr(S, "params_for", lambda m, profile: {})
    out = tmp_path / "new" / "deep" / "smoke.json"
    monkeypatch.setattr(sys, "argv", ["stack_smoke", "--model", "m", "--tag", "t", "--out", str(out)])
    assert S.main() == 2 and not out.parent.exists()
    monkeypatch.setattr(R, "load_requests", lambda f, models: pytest.fail("read before tripwire"))
    a = _parity_args(tmp_path / "new2" / "deep", tmp_path / "frozen.json")
    assert R.run(a) == 2 and not Path(a.out).parent.exists()
    from bench import session_cache_probe as SCP
    wd = tmp_path / "new3" / "wd"
    rc = SCP.main(["--model", "m", "--legs", "", "--workdir", str(wd), "--out", str(tmp_path / "x.json"),
                   "--log", str(tmp_path / "none.log")])
    assert rc == 2 and not wd.exists()


def test_session_cache_probe_leg_b_verifies_opencodes_own_destination(tmp_path, monkeypatch, capsys):
    """opencode sends to its config's baseURL, never to MLX_SERVE_BASE: a probe on :8123 with
    opencode still pointed at :8000 must refuse."""
    from bench import session_cache_probe as SCP
    from bench import paths
    monkeypatch.setenv("MLX_SERVE_BASE", "http://localhost:8123")
    monkeypatch.setattr(P, "opencode_router_base", lambda cwd=None, env=None, provider="mlx-local", **_k: "http://localhost:8000/v1")

    def owner(port):
        return {"pid": 100 + port, "cmdline": "mlx-serve start", "cwd": str(tmp_path),
                "env": {"MLX_SERVE_CONFIG": str(paths.registry_path())}}
    monkeypatch.setattr(P, "router_owner", owner)
    monkeypatch.setattr(SCP, "_post", lambda *a, **k: pytest.fail("request before tripwire"))
    # C125: get PAST the pinned-binary preflight so the refusal below is the destination check's
    monkeypatch.setattr(SCP, "_pinned_opencode", lambda: ("/stub/opencode", "1.18.30"))
    rc = SCP.main(["--model", "m", "--legs", "B", "--workdir", str(tmp_path), "--out", str(tmp_path / "o.json"),
                   "--log", str(tmp_path / "none.log")])
    err = capsys.readouterr().err
    assert rc == 2 and "not the router verified at entry" in err and "pinned" not in err


def test_generate_restart_re_verifies_the_new_router(monkeypatch):
    """After an auto-restart the router is a NEW process; traffic must not resume until it is
    verified again."""
    import bench.generate as G
    from bench import convergence
    calls = []
    monkeypatch.setattr(P, "assert_served_config", lambda base, **k: calls.append("verify") or {"pid": 1})
    monkeypatch.setattr(convergence, "is_converged", lambda row: False)
    monkeypatch.setattr(convergence, "looks_like_loop", lambda r: True)
    probe = lambda m, msgs, params: {"content": "", "reasoning": "x", "finish_reason": "length",
                                     "completion_tokens": 5, "prompt_tokens": 1}
    G.probe_with_recovery("m", [], {"thinking_budget": 4, "max_tokens": 8}, probe_fn=probe,
                          restart_fn=lambda: calls.append("restart"),
                          preload_fn=lambda m: calls.append("preload"))
    assert calls[:3] == ["restart", "verify", "preload"]


def test_resume_refreshes_router_and_keeps_history(tmp_path, monkeypatch):
    import bench.generate as G
    mp = tmp_path / "m" / "b.manifest.json"; mp.parent.mkdir()
    existing = {"fingerprint_version": 6, "router": {"pid": 1, "config": "$HOME/x.yaml"}}
    mp.write_text(json.dumps(existing))
    monkeypatch.setattr(P, "router_block", lambda base: {"pid": 2, "config": "$HOME/x.yaml"})
    G._refresh_router(mp, existing, P)
    got = json.loads(mp.read_text())
    assert got["router"]["pid"] == 2 and got["router_history"] == [{"pid": 1, "config": "$HOME/x.yaml"}]
    G._refresh_router(mp, got, P)          # same router again: no duplicate history entry
    assert len(json.loads(mp.read_text())["router_history"]) == 1


# --------------------------------------------------------------------------- round 3 (Codex cold review #2)
def _run_with_restart(tmp_path, monkeypatch, owners):
    """generate.run with auto-restart: `owners` is the sequence of router_owner answers (entry,
    restart-verify, ...). Returns (calls, probe_count)."""
    import bench.generate as G
    import bench.benchmarks as B
    import bench.client as C
    from bench import convergence, paths
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    monkeypatch.setattr(B, "load", lambda b, lim, seed: [{"id": "t1", "prompt": "p"}, {"id": "t2", "prompt": "q"}])
    monkeypatch.setattr(C, "preload", lambda m, **k: 0.0)
    monkeypatch.setattr(convergence, "is_converged", lambda row: False)
    monkeypatch.setattr(convergence, "looks_like_loop", lambda r: True)
    n = {"probe": 0}

    def probe(m, msgs, params, timeout=3600, tools=None):
        n["probe"] += 1
        return {"content": "", "reasoning": "loop loop", "tool_calls": [], "prompt_tokens": 1,
                "completion_tokens": 10, "decode_tps": 1.0, "peak_mem_gb": 1.0,
                "finish_reason": "length", "wall_s": 0.1, "raw_timings": {}}
    monkeypatch.setattr(C, "probe", probe)
    seq = iter(owners)
    monkeypatch.setattr(P, "router_owner", lambda port: next(seq))
    calls = []
    return G, calls, n


def _good(tmp_path, pid):
    from bench import paths
    return {"pid": pid, "cmdline": "python mlx-serve start", "argv": ["python", "mlx-serve", "start"],
            "cwd": str(tmp_path), "env": {"MLX_SERVE_CONFIG": str(paths.registry_path())}}


def test_generate_restart_refusal_is_fatal_not_an_error_row(tmp_path, monkeypatch):
    """Codex #2 P16: a refusal after an auto-restart used to become an ordinary error row and the
    run continued on the wrong router. It must abort the run: no further probes, nonzero exit."""
    G, calls, n = _run_with_restart(tmp_path, monkeypatch, [_good(tmp_path, 1), None])
    with pytest.raises(P.ServedConfigError):
        G.run(["m"], ["aime"], {}, restart_fn=lambda: calls.append("restart"))
    assert calls == ["restart"] and n["probe"] == 1
    rows = (tmp_path / "m" / "aime.jsonl")
    assert not rows.exists() or all("error" not in json.loads(l) for l in rows.read_text().splitlines())


def test_generate_successful_restart_refreshes_manifests_with_history(tmp_path, monkeypatch):
    """Codex #2 P17: rows written after a restart must be attributed to the NEW router."""
    G, calls, n = _run_with_restart(tmp_path, monkeypatch,
                                    [_good(tmp_path, 1), _good(tmp_path, 2), _good(tmp_path, 2),
                                     _good(tmp_path, 3), _good(tmp_path, 3),
                                     _good(tmp_path, 3)])      # C106 exit check: one more lookup
    G.run(["m"], ["aime"], {}, restart_fn=lambda: calls.append("restart"))
    man = json.loads((tmp_path / "m" / "aime.manifest.json").read_text())
    assert man["router"]["pid"] == 3
    assert [h["pid"] for h in man["router_history"]] == [1, 2]
    assert calls == ["restart", "restart"]


def test_stack_smoke_refusal_exit_2_survives_the_exception_class_change(tmp_path, monkeypatch, capsys):
    from bench import stack_smoke as S
    monkeypatch.setattr(S, "params_for", lambda m, profile: {})
    _refusing(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["stack_smoke", "--model", "m", "--tag", "t", "--out", str(tmp_path / "s.json")])
    assert S.main() == 2 and "M50" in capsys.readouterr().err


# --------------------------------------------------------------------------- round 4 (Codex cold review #3)
def test_parity_resume_keeps_prior_router_attribution_and_refuses_config_change(tmp_path, monkeypatch):
    from bench import parity_replay as R
    # M58 AC11: complete only with every frozen key exactly once, so the journal's row is frozen too
    monkeypatch.setattr(R, "load_requests", lambda f, models: [
        {"model": "m", "bench": "b", "id": "i", "seed": 1, "payload": {"max_tokens": 10}}])
    monkeypatch.setattr(R.client, "preload", lambda m, **k: 0.0)
    _stub_parity_state(monkeypatch, R)
    _passing(monkeypatch, tmp_path, pid=2)
    a = _parity_args(tmp_path, tmp_path / "frozen.json"); a.resume = True
    blk = P.router_block("http://localhost:8000")
    prev = {"pid": 1, "config": blk["config"], "config_sha256": blk["config_sha256"], "port": 8000}
    Path(a.out).write_text(json.dumps({"status": "running", "router": prev,
                                       "rows": [{"model": "m", "bench": "b", "id": "i",
                                                 "payload_sha256": R._payload_sha({"max_tokens": 10}, 1),
                                                 "runtime": {"mtp_verify_scan": "per_query"},
                                                 "code": {"src/mlx-vlm": "c", "src/mlx-serve": "d"}}],
                                       "code": {"src/mlx-vlm": "c", "src/mlx-serve": "d"}}))
    assert R.run(a) == 0
    doc = json.loads(Path(a.out).read_text())
    assert doc["router"]["pid"] == 2 and doc["router_history"] == [prev] and len(doc["rows"]) == 1
    Path(a.out).write_text(json.dumps({"status": "running", "router": {"pid": 1, "config": "$HOME/other.yaml"},
                                       "rows": []}))
    assert R.run(a) == 2                                     # served config changed: refuse


def test_generate_restart_manifest_refresh_failure_is_fatal(tmp_path, monkeypatch):
    """Codex #3 P22: a failed refresh used to be logged and the run went on with stale attribution."""
    import os as _os
    G, calls, n = _run_with_restart(tmp_path, monkeypatch, [_good(tmp_path, 1), _good(tmp_path, 2), _good(tmp_path, 2)])
    monkeypatch.setattr(_os, "replace", lambda a, b: (_ for _ in ()).throw(PermissionError("ro")))
    with pytest.raises(P.ServedConfigError, match="cannot refresh router"):
        G.run(["m"], ["aime"], {}, restart_fn=lambda: calls.append("restart"))
    assert n["probe"] == 1
    man = json.loads((tmp_path / "m" / "aime.manifest.json").read_text())
    assert man["router"]["pid"] == 1                          # original manifest intact


def test_stack_smoke_reads_params_only_after_verification(tmp_path, monkeypatch):
    from bench import stack_smoke as S
    monkeypatch.setattr(S, "params_for", lambda m, profile: pytest.fail("params before tripwire"))
    _refusing(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["stack_smoke", "--model", "m", "--tag", "t", "--out", str(tmp_path / "s.json")])
    assert S.main() == 2


# --------------------------------------------------------------------------- C35 through generate.run
def _c35_generate_setup(tmp_path, monkeypatch, served_draft):
    """generate.run against a registry declaring draft_kind=mtp, with a live worker whose cmdline
    says `served_draft`. Returns (G, probes, results) — `probes` collects every request."""
    import yaml
    import bench.generate as G
    import bench.benchmarks as B
    import bench.client as C
    from bench import paths
    reg = tmp_path / "reg.yaml"
    reg.write_text(yaml.safe_dump({"models": [{"name": "m", "hf_path": "caslca/m-4bit",
                                              "draft_kind": "mtp"}]}))
    monkeypatch.setattr(paths, "registry_path", lambda: reg)
    res = tmp_path / "results"
    res.mkdir()
    monkeypatch.setattr(G, "RESULTS", res)
    monkeypatch.setattr(B, "load", lambda b, lim, seed: [{"id": "t1", "prompt": "p"}])
    cmd = f"python -m mlx_vlm.server --model caslca/m-4bit --draft-kind {served_draft}"
    monkeypatch.setattr(P.registry_draft, "__defaults__", (lambda: cmd,))
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [])
    probes = []
    monkeypatch.setattr(C, "preload", lambda m, **k: probes.append("preload") or 0.0)
    monkeypatch.setattr(C, "probe", lambda m, msgs, params, timeout=3600, tools=None: (
        probes.append("probe"), {
            "content": "ok", "reasoning": "", "tool_calls": [], "prompt_tokens": 1,
            "completion_tokens": 10, "decode_tps": 1.0, "peak_mem_gb": 1.0,
            "finish_reason": "stop", "wall_s": 0.1, "raw_timings": {}})[1])
    return G, probes, res


def test_c35_tripwire_is_a_served_config_error_and_still_a_runtime_error():
    assert issubclass(P.ServingStateError, P.ServedConfigError)
    assert issubclass(P.ServedConfigError, RuntimeError)


def test_generate_run_refuses_on_a_draft_kind_disagreement(tmp_path, monkeypatch):
    """C35 must stop a generate run: no request, no manifest, no rows (it used to be swallowed
    by the 'never block a run on provenance' handlers and printed as 'skipped')."""
    G, probes, res = _c35_generate_setup(tmp_path, monkeypatch, served_draft="off")
    with pytest.raises(P.ServedConfigError, match="C35 tripwire"):
        G.run(["m"], ["aime"], {})
    assert probes == []
    assert list(res.rglob("*")) == []


def test_generate_run_proceeds_when_the_worker_draft_kind_matches(tmp_path, monkeypatch):
    G, probes, res = _c35_generate_setup(tmp_path, monkeypatch, served_draft="mtp")
    G.run(["m"], ["aime"], {})
    assert probes == ["preload", "probe"]
    man = json.loads((res / "m" / "aime.manifest.json").read_text())
    assert man["runtime"]["draft_kind"] == "mtp"


# --------------------------------------------------------------------------- capacity / retrieval / reasoning
# (2026-10-04: these three drivers lacked the M50 entry check and the C106 exit re-verification)
from bench.tests import test_serving_state_drivers as _SSD   # noqa: E402  (shared fakes)

_STAT_DRIVERS = list(_SSD.DRIVERS)
_MANIFEST_NAME = {"capacity": "capacity_ladder.manifest.json", "retrieval": "retrieval.manifest.json",
                  "reasoning": "reasoning.manifest.json"}


def _stat_setup(monkeypatch, tmp_path, name):
    mod, lad, canned, extra = _SSD.DRIVERS[name]
    drv, ladder_calls, results = _SSD._setup(monkeypatch, tmp_path, mod, lad, canned, [[_SSD.GOOD]])
    return mod, lad, canned, extra, drv, ladder_calls, results


@pytest.mark.parametrize("name", _STAT_DRIVERS)
def test_stat_drivers_refuse_before_anything_else_when_no_router_owns_the_port(monkeypatch, tmp_path, name):
    mod, lad, canned, extra, drv, ladder_calls, results = _stat_setup(monkeypatch, tmp_path, name)
    monkeypatch.setattr(P, "assert_serving_state",
                        lambda *a, **k: pytest.fail("serving-state precheck ran before the M50 check"))
    monkeypatch.setattr(mod, "MlxServeDriver", lambda: pytest.fail("driver built before the M50 check"))
    monkeypatch.setattr(mod, "await_model_pid", lambda: pytest.fail("worker lookup before the M50 check"))
    _refusing(monkeypatch)
    with pytest.raises(P.ServedConfigError, match="M50"):
        mod.main(_SSD._argv(extra))
    assert drv.calls == [] and ladder_calls == []
    assert list(results.iterdir()) == []              # not even the model directory


@pytest.mark.parametrize("name", _STAT_DRIVERS)
def test_stat_drivers_refuse_on_a_registry_mismatch(monkeypatch, tmp_path, name):
    mod, lad, canned, extra, drv, ladder_calls, results = _stat_setup(monkeypatch, tmp_path, name)
    monkeypatch.setattr(P, "router_owner", lambda port: {
        "pid": 1, "cmdline": "mlx-serve start", "cwd": str(tmp_path),
        "env": {"MLX_SERVE_CONFIG": str(tmp_path / "other.yaml")}})
    with pytest.raises(P.ServedConfigError, match="M50"):
        mod.main(_SSD._argv(extra))
    assert drv.calls == [] and list(results.iterdir()) == []


@pytest.mark.parametrize("name", _STAT_DRIVERS)
def test_stat_drivers_stamp_router_and_exit_block_in_the_manifest(monkeypatch, tmp_path, name):
    mod, lad, canned, extra, drv, ladder_calls, results = _stat_setup(monkeypatch, tmp_path, name)
    _passing(monkeypatch, tmp_path, pid=31337)
    assert mod.main(_SSD._argv(extra)) == 0
    man = json.loads((results / _SSD.MODEL / _MANIFEST_NAME[name]).read_text())
    assert man["router"]["pid"] == 31337 and man["router"]["config"] and man["router"]["config_sha256"]
    assert man["router_exit"]["verified_at"] == "exit" and man["router_exit"]["pid"] == 31337


def _arm_drift(monkeypatch, tmp_path, mod, lad, canned, mode):
    """After the ladder has run, change what the router serves: a new pid or an edited file."""
    from bench import paths
    state = {"drift": False}

    def owner(port):
        pid = 8 if (state["drift"] and mode == "pid") else 7
        return {"pid": pid, "cmdline": "mlx-serve start", "cwd": str(tmp_path),
                "env": {"MLX_SERVE_CONFIG": str(paths.registry_path())}}
    monkeypatch.setattr(P, "router_owner", owner)

    def ladder(*a, **k):
        state["drift"] = True
        if mode == "sha":
            with open(paths.registry_path(), "a") as f:
                f.write("\n# edited while the run was live\n")
        return canned
    monkeypatch.setattr(mod, lad, ladder)


@pytest.mark.parametrize("mode", ["pid", "sha"])
@pytest.mark.parametrize("name", ["retrieval", "reasoning"])
def test_ladder_drivers_quarantine_the_result_on_exit_drift(monkeypatch, tmp_path, name, mode):
    mod, lad, canned, extra, drv, ladder_calls, results = _stat_setup(monkeypatch, tmp_path, name)
    _arm_drift(monkeypatch, tmp_path, mod, lad, canned, mode)
    with pytest.raises(P.ServedConfigError, match="C106"):
        mod.main(_SSD._argv(extra))
    mdir = results / _SSD.MODEL
    assert not (mdir / f"{name}.json").exists() and not (mdir / f"{name}.manifest.json").exists()
    aside = [p for p in mdir.iterdir() if p.name.startswith(f"{name}.json.refused-")]
    assert len(aside) == 1
    assert "served_config_drift" in json.loads(aside[0].read_text())
    assert not [p for p in mdir.iterdir() if ".pending-" in p.name]


@pytest.mark.parametrize("mode", ["pid", "sha"])
def test_capacity_writes_no_manifest_and_stamps_drift_on_exit_drift(monkeypatch, tmp_path, mode):
    mod, lad, canned, extra, drv, ladder_calls, results = _stat_setup(monkeypatch, tmp_path, "capacity")
    _arm_drift(monkeypatch, tmp_path, mod, lad, canned, mode)
    with pytest.raises(P.ServedConfigError, match="C106"):
        mod.main(_SSD._argv(extra))
    mdir = results / _SSD.MODEL
    # Review C2: nothing consumable under a canonical name; the scorecard is set aside stamped.
    assert not (mdir / "capacity_ladder.manifest.json").exists()
    assert not (mdir / "capacity_retrieval.json").exists()
    aside = list(mdir.glob("capacity_retrieval.json.refused-*"))
    assert len(aside) == 1
    assert "C106" in json.loads(aside[0].read_text())["served_config_drift"]["error"]
