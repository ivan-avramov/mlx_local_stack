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
    """A shared dict mutated downstream would silently couple requests. Asserted against the ACTUAL
    request count, not a literal: the positive control legitimately adds two requests of its own."""
    d = FakeDriver()
    monkeypatch.setattr(AP, "MlxServeDriver", lambda: d)
    AP.main(["--model", "M", "--label", "apc_on", "--requests", "3", "--out", "/dev/null"])
    assert len(d.requests) >= 3
    assert len({id(r["params"]) for r in d.requests}) == len(d.requests)


# ------------------------------------------------------------ the positive control (added after
# the probe's first run nearly reported an inert-APC zero as a cheap-APC zero)
class RatioDriver(FakeDriver):
    """Scripted prefill times so the control's verdict is controllable."""

    def __init__(self, prefills):
        super().__init__()
        self.prefills = prefills

    def complete(self, model, messages, params, timeout=3600, tools=None):
        r = super().complete(model, messages, params, timeout, tools)
        r["prefill_s"] = self.prefills[(len(self.requests) - 1) % len(self.prefills)]
        return r


def test_positive_control_detects_reuse_when_warm_prefill_collapses():
    d = RatioDriver([6.0, 0.2])
    c = AP.positive_control(d, "M", 9000, 10)
    assert c["reuse_detected"] is True
    assert c["prefill_speedup"] == 30.0


def test_positive_control_reports_NO_reuse_when_prefill_is_flat():
    """The 2026-08-13 reality: 3.10s then 3.00s. APC enabled, doing nothing."""
    d = RatioDriver([3.10, 3.00])
    c = AP.positive_control(d, "M", 9000, 10)
    assert c["reuse_detected"] is False


def test_control_threshold_is_conservative_against_the_recorded_win():
    """Recorded win is 34-147x, so 2x cannot false-negative a working cache."""
    d = RatioDriver([4.0, 1.0])          # 4x -- far below 34x but well above the threshold
    assert AP.positive_control(d, "M", 9000, 10)["reuse_detected"] is True


def test_memory_number_is_flagged_UNINTERPRETABLE_when_no_reuse(tmp_path, monkeypatch):
    """THE regression this pair of tests exists for: a memory delta measured while APC is inert is
    not a measurement of APC's cost, and must never be recorded as though it were."""
    d = RatioDriver([3.10, 3.00])
    monkeypatch.setattr(AP, "MlxServeDriver", lambda: d)
    out = tmp_path / "r.json"
    AP.main(["--model", "M", "--label", "apc_on", "--requests", "2", "--out", str(out)])
    got = json.loads(out.read_text())
    assert got["memory_number_interpretable"] is False
    assert got["positive_control"]["reuse_detected"] is False


def test_memory_number_is_interpretable_when_reuse_is_demonstrated(tmp_path, monkeypatch):
    d = RatioDriver([6.0, 0.2])
    monkeypatch.setattr(AP, "MlxServeDriver", lambda: d)
    out = tmp_path / "r.json"
    AP.main(["--model", "M", "--label", "apc_on", "--requests", "2", "--out", str(out)])
    assert json.loads(out.read_text())["memory_number_interpretable"] is True


def test_apc_off_arm_may_skip_the_control_since_no_reuse_is_EXPECTED(tmp_path, monkeypatch):
    d = FakeDriver()
    monkeypatch.setattr(AP, "MlxServeDriver", lambda: d)
    out = tmp_path / "r.json"
    AP.main(["--model", "M", "--label", "apc_off", "--skip-positive-control",
             "--requests", "2", "--out", str(out)])
    got = json.loads(out.read_text())
    assert got["positive_control"] is None
    assert got["memory_number_interpretable"] is True
