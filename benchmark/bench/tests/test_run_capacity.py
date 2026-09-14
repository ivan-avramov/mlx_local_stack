import json, os
import bench.run_capacity as R
from bench.model_params import params_for

class FakeDriver:
    def preload(self, model, timeout=900): return 1.0
    def complete(self, model, messages, params, timeout=3600):
        # calibration call asks for a known filler; return a prompt_tokens so cpt computes
        return {"content": "XKRZ0A7Q, XKRZ1B7Q, XKRZ2C7Q, XKRZ3D7Q, XKRZ4E7Q",
                "prompt_tokens": 1000, "completion_tokens": 10, "finish_reason": "stop", "prefill_s": 1.0, "prefill_tps": 100,
                "decode_tps": 9.5, "peak_mem_gb": 40.0}

class FakeSampler:
    def __init__(self, **kw): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass
    system_peak_gb = 45.0
    peak_rss_gb = 35.0   # RSS is secondary, not the target metric

def test_calibrate_returns_positive_cpt():
    assert R.calibrate_cpt(FakeDriver(), "m") > 0

def test_main_writes_results(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    # idle=10GB; RSS=35 (secondary); system_peak=45 → sys_footprint=35 (secondary)
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "await_model_pid", lambda: 12345)
    rc = R.main(["--model", "m", "--grid", "160000,192000", "--sampling-profile", "production"])
    assert rc == 0
    sc = json.load(open(os.path.join(tmp_path, "m", "capacity_retrieval.json")))
    assert sc["model"] == "m" and sc["axis"] == "capacity_retrieval"
    assert sc["memory_metric"] == "mlx_peak_gb (mx.get_peak_memory, the prefill spike)"
    assert len(sc["records"]) == 2
    assert sc["idle_baseline_gb"] == 10.0
    # verify capacity_ladder.jsonl has one line per rung
    lines = open(os.path.join(tmp_path, "m", "capacity_ladder.jsonl")).readlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["server_peak_gb"] == 40.0 and first["within_memory_target"] is True  # descriptive target (40<=48)
    assert first["peak_rss_gb"] == 35.0                               # steady-state reported
    assert first["model_footprint_gb"] == round(45.0 - 10.0, 2)       # 35.0 coarse cross-check


def test_main_passes_bounded_params_to_ladder(tmp_path, monkeypatch):
    """main() builds params from params_for, then bounds max_tokens=256, thinking_budget=256."""
    captured = {}

    def fake_ladder(*a, **kw):
        captured["params"] = kw.get("params") or (a[5] if len(a) > 5 else None)
        return [{"ctx": 160000, "server_peak_gb": 40.0, "peak_rss_gb": 35.0,
                 "system_peak_gb": 45.0, "model_footprint_gb": 35.0,
                 "prefill_s": 1.0, "prefill_tps": 200, "decode_tps": 9.5,
                 "prompt_tokens": 1000, "completion_tokens": 10, "finish_reason": "stop", "retrieval_acc": 1.0, "fits": True}]

    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "await_model_pid", lambda: 12345)
    monkeypatch.setattr(R, "run_ladder", fake_ladder)
    R.main(["--model", "gemma-4-26B-A4B-it-QAT-MLX-4bit",
            "--grid", "160000", "--no-preload", "--sampling-profile", "production"])
    assert captured["params"] is not None
    # Must be bounded regardless of model's production max_tokens
    assert captured["params"]["max_tokens"] == 256
    assert captured["params"]["thinking_budget"] == 256
    # Production sampling params must still be present
    base = params_for("gemma-4-26B-A4B-it-QAT-MLX-4bit")
    assert captured["params"]["temperature"] == base["temperature"]
    assert captured["params"]["top_p"] == base["top_p"]

def test_main_writes_a_provenance_manifest_beside_the_ladder(tmp_path, monkeypatch):
    """Operator-approved 2026-08-17: NO capacity artifact in the corpus had a manifest, so every
    published memory-gate number had unrecorded provenance. The manifest must land BESIDE the
    ladder in THIS module's results root — not via provenance.write, which resolves its own
    root and polluted the real benchmark/results/ tree on every full-suite run until the D3
    worker caught it (2026-08-17)."""
    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "await_model_pid", lambda: 12345)
    calls = {}
    import bench.provenance as P

    def fake_gather(model, *a, **kw):
        calls["args"] = (model, kw)
        return {"model": model, "fake": True}
    monkeypatch.setattr(P, "gather", fake_gather)

    def boom(*a, **kw):
        raise AssertionError("provenance.write must NOT be used here — it bypasses RESULTS")
    monkeypatch.setattr(P, "write", boom)

    rc = R.main(["--model", "m", "--grid", "160000", "--sampling-profile", "production"])
    assert rc == 0
    model, kw = calls["args"]
    assert model == "m"
    assert kw["profile"] == "production"
    assert kw["runtime"]["probe"] == "capacity_ladder"
    assert kw["overrides"] == {"max_tokens": 256, "thinking_budget": 256, "seed": 0}
    import json as _json
    man_path = tmp_path / "m" / "capacity_ladder.manifest.json"
    assert man_path.exists(), "manifest must land beside the ladder, inside RESULTS"
    assert _json.loads(man_path.read_text())["fake"] is True


def test_sampling_profile_is_required(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "await_model_pid", lambda: 12345)
    import pytest
    with pytest.raises(SystemExit) as e:
        R.main(["--model", "m", "--grid", "160000", "--no-preload"])
    assert e.value.code == 2


def test_sampling_profile_reaches_params_for(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "await_model_pid", lambda: 12345)
    seen = {}

    def fake_params_for(model, profile="production", registry_path=None):
        seen["profile"] = profile
        return {"temperature": 0.5, "top_p": 0.95}

    monkeypatch.setattr(R, "params_for", fake_params_for)
    R.main(["--model", "m", "--grid", "160000", "--no-preload",
            "--sampling-profile", "deployed"])
    assert seen["profile"] == "deployed"


def test_request_timeout_reaches_ladder(tmp_path, monkeypatch):
    """M41 FIX1 F2: --request-timeout threads through to run_ladder."""
    seen = {}
    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "await_model_pid", lambda: 12345)

    def fake_ladder(*a, **kw):
        seen["request_timeout"] = kw.get("request_timeout")
        return []

    monkeypatch.setattr(R, "run_ladder", fake_ladder)
    R.main(["--model", "m", "--grid", "160000", "--no-preload",
            "--sampling-profile", "production", "--request-timeout", "1234"])
    assert seen["request_timeout"] == 1234


def test_request_timeout_default_is_derived_not_sdk(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "await_model_pid", lambda: 12345)

    def fake_ladder(*a, **kw):
        seen["request_timeout"] = kw.get("request_timeout")
        return []

    monkeypatch.setattr(R, "run_ladder", fake_ladder)
    R.main(["--model", "m", "--grid", "160000", "--no-preload",
            "--sampling-profile", "production"])
    assert seen["request_timeout"] >= 7200.0


def test_out_tag_changes_filenames(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "await_model_pid", lambda: 12345)
    rc = R.main(["--model", "m", "--grid", "160000", "--no-preload",
                "--sampling-profile", "production", "--out-tag", "t07"])
    assert rc == 0
    assert not os.path.exists(os.path.join(tmp_path, "m", "capacity_retrieval.json"))
    assert not os.path.exists(os.path.join(tmp_path, "m", "capacity_ladder.jsonl"))
    assert not os.path.exists(os.path.join(tmp_path, "m", "capacity_ladder.manifest.json"))
    assert os.path.exists(os.path.join(tmp_path, "m", "capacity_retrieval.t07.json"))
    assert os.path.exists(os.path.join(tmp_path, "m", "capacity_ladder.t07.jsonl"))
    assert os.path.exists(os.path.join(tmp_path, "m", "capacity_ladder.t07.manifest.json"))


def test_request_failure_persisted_unscored_and_returns_nonzero(tmp_path, monkeypatch, capsys):
    class Broken(FakeDriver):
        def complete(self, model, messages, params, timeout=3600):
            if params['max_tokens'] != 1:
                raise TimeoutError('timed out')
            return super().complete(model, messages, params, timeout)
    monkeypatch.setattr(R, 'MlxServeDriver', Broken)
    monkeypatch.setattr(R, 'MemorySampler', FakeSampler)
    monkeypatch.setattr(R, 'RESULTS', str(tmp_path))
    monkeypatch.setattr(R, 'system_used_gb', lambda: 10.)
    monkeypatch.setattr(R, 'await_model_pid', lambda: 12345)
    rc = R.main(['--model', 'm', '--grid', '100,200', '--sampling-profile', 'production'])
    assert rc != 0
    rows = [json.loads(x) for x in (tmp_path / 'm/capacity_ladder.jsonl').read_text().splitlines()]
    assert len(rows) == 1 and rows[0]['retrieval_acc'] is None
    assert 'runner-exit' in capsys.readouterr().out


def test_existing_result_refused_before_driver_creation(tmp_path, monkeypatch):
    import pytest
    target = tmp_path / 'm/capacity_retrieval.json'
    target.parent.mkdir()
    target.write_text('historical bytes')
    monkeypatch.setattr(R, 'RESULTS', str(tmp_path))
    def forbidden():
        raise AssertionError('must not load model before overwrite check')
    monkeypatch.setattr(R, 'MlxServeDriver', forbidden)
    with pytest.raises(SystemExit) as exc:
        R.main(['--model', 'm', '--sampling-profile', 'production'])
    assert exc.value.code == 2
    assert target.read_text() == 'historical bytes'


def test_calibration_rejects_invalid_or_implausible_usage():
    import pytest
    for tokens in [None, 0, 1, True, float('inf')]:
        class Calibration:
            def complete(self, *a, **kw):
                return {'prompt_tokens': tokens, 'content': '', 'completion_tokens': 1,
                        'finish_reason': 'length'}
        with pytest.raises(ValueError, match='calibration'):
            R.calibrate_cpt(Calibration(), 'm')


def test_ladder_receives_explicit_seed(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(R, 'MlxServeDriver', FakeDriver)
    monkeypatch.setattr(R, 'RESULTS', str(tmp_path))
    monkeypatch.setattr(R, 'system_used_gb', lambda: 10.)
    monkeypatch.setattr(R, 'await_model_pid', lambda: 12345)
    def fake_ladder(*args, **kw):
        seen.update(kw['params'])
        return []
    monkeypatch.setattr(R, 'run_ladder', fake_ladder)
    R.main(['--model', 'm', '--grid', '100', '--sampling-profile', 'production'])
    assert seen['seed'] == 0
