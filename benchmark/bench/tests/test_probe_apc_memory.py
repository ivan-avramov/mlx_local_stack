"""The APC memory probe must actually FORCE the pool to fill, or its number is meaningless.

The endpoint is APC's high-water mark, i.e. the CEILING the pool can reach -- not whatever a light
session happened to touch. Two ways that silently fails:
  - prefixes that share a head, so APC HITS instead of storing (the pool never fills)
  - total prefill below the pool capacity, so the mark is an under-fill, not the ceiling
Both are pinned here, plus the request hygiene that keeps the measurement on the deployed path.
"""
import json

import pytest

import bench.probe_apc_memory as AP


class FakeDriver:
    def __init__(self, peaks=None):
        self.requests = []
        self.peaks = peaks or [20.0]

    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600, tools=None):
        self.requests.append({"messages": messages, "params": params})
        i = len(self.requests) - 1
        return {"content": "OK", "reasoning": "", "prompt_tokens": 9000,
                "completion_tokens": 8, "peak_mem_gb": self.peaks[i % len(self.peaks)],
                "prefill_s": 5.0, "prefill_tps": 1800, "wall_s": 6.0}


# ------------------------------------------------------------ the pool must actually fill
def test_unique_prefixes_cannot_prefix_match_each_other():
    """APC matches on PREFIXES. A shared head would hit, and the pool would never fill."""
    a, b = AP.unique_prefix(0, 500), AP.unique_prefix(1, 500)
    assert a[:40] != b[:40], "prefixes share a head -> APC would hit instead of storing"
    assert not a.startswith(b[:60]) and not b.startswith(a[:60])


def test_unique_marker_is_at_the_very_front():
    assert AP.unique_prefix(3, 500).startswith("Document 3 ")


def test_prefix_length_scales_with_requested_tokens():
    short, long = AP.unique_prefix(0, 500), AP.unique_prefix(0, 5000)
    assert len(long) > 8 * len(short) / 2      # ~10x tokens -> ~10x chars, allow slack


def test_pool_capacity_matches_the_shipped_apc_constants():
    """2048 blocks x 16 tokens. If runserver.sh's pool size changes, this must be revisited."""
    assert AP.POOL_TOKENS_AT_2048_BLOCKS == 32768


def test_default_run_exceeds_pool_capacity_so_the_mark_is_a_CEILING(tmp_path, monkeypatch):
    d = FakeDriver()
    monkeypatch.setattr(AP, "MlxServeDriver", lambda: d)
    out = tmp_path / "r.json"
    AP.main(["--model", "M", "--label", "apc_on", "--out", str(out)])
    got = json.loads(out.read_text())
    assert got["total_prompt_tokens_prefilled"] > AP.POOL_TOKENS_AT_2048_BLOCKS
    assert got["pool_capacity_exceeded"] is True


def test_under_filling_is_reported_not_hidden(tmp_path, monkeypatch):
    """A run too small to fill the pool must be visibly flagged, not quietly averaged in."""
    d = FakeDriver()
    monkeypatch.setattr(AP, "MlxServeDriver", lambda: d)
    out = tmp_path / "r.json"
    AP.main(["--model", "M", "--label", "apc_on", "--requests", "1", "--out", str(out)])
    assert json.loads(out.read_text())["pool_capacity_exceeded"] is False


# ------------------------------------------------------------ the reported number
def test_headline_is_the_MAX_peak_not_the_last_or_mean(tmp_path, monkeypatch):
    """get_peak_memory is a high-water mark; the ceiling is the max across draws."""
    d = FakeDriver(peaks=[20.0, 26.5, 22.0])
    monkeypatch.setattr(AP, "MlxServeDriver", lambda: d)
    out = tmp_path / "r.json"
    AP.main(["--model", "M", "--label", "apc_on", "--requests", "3", "--out", str(out)])
    assert json.loads(out.read_text())["max_peak_mem_gb"] == 26.5


def test_label_is_required_so_a_result_is_never_ambiguous(monkeypatch):
    d = FakeDriver()
    monkeypatch.setattr(AP, "MlxServeDriver", lambda: d)
    with pytest.raises(SystemExit):
        AP.main(["--model", "M"])


# ------------------------------------------------------------ request hygiene
def test_thinking_stays_enabled():
    """AGENTS.md: never disabled to make a run work. The max_tokens cap is what shortens it."""
    assert AP.PARAMS["enable_thinking"] is True
    assert AP.PARAMS["thinking_budget"] == 81920


def test_presence_penalty_zero_and_deployed_truncation():
    """Stay on the deployed serving path: nonzero presence_penalty disables suffix decoding, and
    the untruncated tail is nondeterministic (see probe_determinism)."""
    assert AP.PARAMS["presence_penalty"] == 0.0
    assert (AP.PARAMS["top_p"], AP.PARAMS["top_k"]) == (0.95, 20)


def test_generation_is_capped_because_the_endpoint_is_prefill_memory():
    assert AP.PARAMS["max_tokens"] <= 16


def test_each_request_gets_its_own_params_dict(monkeypatch):
    d = FakeDriver()
    monkeypatch.setattr(AP, "MlxServeDriver", lambda: d)
    AP.main(["--model", "M", "--label", "apc_on", "--requests", "3", "--out", "/dev/null"])
    assert len({id(r["params"]) for r in d.requests}) == 3
