"""P475 stage 1 (implementer tests): without `--p475-strict`, `run_capacity` writes byte-identical output to the pre-P475 code
(baseline `bc3ad13e`), run side by side on the same fake driver. Skipped when the baseline blob is not in this clone."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

BASELINE = "bc3ad13e"
REPO = Path(__file__).resolve().parents[3]


def _blob(rel):
    r = subprocess.run(["git", "-C", str(REPO), "show", f"{BASELINE}:{rel}"], capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip(f"baseline {BASELINE} not available")
    return r.stdout


def _load(name, text, tmp_path):
    path = tmp_path / f"{name.rsplit('.', 1)[-1]}.py"
    path.write_text(text)
    spec = importlib.util.spec_from_file_location(name, path, submodule_search_locations=None)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "bench"
    spec.loader.exec_module(mod)
    return mod


class Driver:
    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        n = max(1, len(messages[0]["content"]) // 4)
        return {"content": "XKRZ0A7Q", "prompt_tokens": n, "completion_tokens": 7, "finish_reason": "stop", "prefill_s": 1.0,
                "prefill_tps": 100, "decode_tps": 9.5, "peak_mem_gb": 40.0,
                "raw_timings": {"draft_kind": "mtp", "draft_n": 9, "draft_n_accepted": 5, "draft_rounds": 4, "prompt_n": n,
                                "cache_n": 0, "peak_memory": 41.0}, "session_id": None}


class Sampler:
    def __init__(self, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    system_peak_gb = 45.0
    peak_rss_gb = 35.0


def _run(mod, tmp_path, monkeypatch, out):
    monkeypatch.setattr(mod, "MlxServeDriver", lambda: Driver())
    monkeypatch.setattr(mod, "MemorySampler", Sampler)
    monkeypatch.setattr(mod, "RESULTS", str(out))
    monkeypatch.setattr(mod, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(mod, "await_model_pid", lambda: 12345)
    import time
    monkeypatch.setattr(time, "monotonic", lambda: 5.0)            # elapsed_s identical in both runs
    rc = mod.main(["--model", "m", "--grid", "1000,2000", "--sampling-profile", "production", "--out-tag", "t",
                   "--expected-rung-seconds", "10,20"])
    files = {p.name: p.read_text() for p in (out / "m").iterdir()}
    return rc, files


@pytest.mark.usefixtures("pin_mtp_scan")
def test_default_output_is_byte_identical_to_the_baseline(tmp_path, monkeypatch):
    import bench.run_capacity as new
    old_cl = _load("bench._p475_baseline_capacity_ladder", _blob("benchmark/bench/capacity_ladder.py"), tmp_path)
    old_rc_text = _blob("benchmark/bench/run_capacity.py")
    with pytest.MonkeyPatch.context() as mp:                  # the baseline run_capacity binds the baseline ladder
        mp.setitem(sys.modules, "bench.capacity_ladder", old_cl)
        old = _load("bench._p475_baseline_run_capacity", old_rc_text, tmp_path)
    rc_old, files_old = _run(old, tmp_path, monkeypatch, tmp_path / "old")
    rc_new, files_new = _run(new, tmp_path, monkeypatch, tmp_path / "new")
    assert rc_old == rc_new
    assert sorted(files_old) == sorted(files_new)

    def norm(name, text):                       # the manifest carries timestamps / code hashes of the module itself
        if name.endswith(".manifest.json"):
            d = json.loads(text)
            return {k: d[k] for k in ("runtime", "sampling") if k in d}
        return text
    for name in files_old:
        assert norm(name, files_old[name]) == norm(name, files_new[name]), name
