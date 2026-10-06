"""M58 (AC10, S7): capacity and `generate` rows persist EVERY `verify_*` counter the server sends
(same pattern as the M57 `sdpa` counters); rows under `per_query` (no counters) are unchanged."""
import json
import re

import bench.benchmarks as B
import bench.capacity_ladder as L
import bench.client as C
import bench.generate as G

from bench.tests.test_capacity_ladder import DraftDriver, FakeDriver, FakeSampler, _PARAMS
import pytest

pytestmark = pytest.mark.usefixtures("pin_mtp_scan")   # M58: synthetic models


_VERIFY = {"verify_blocks_joint_v1": 120, "verify_blocks_per_query": 3,
           "verify_blocks_straddle": 2, "verify_blocks_len1": 40,
           "verify_fallback_reasons": {"mask_form": 3},
           "verify_ab_blocks": 118, "verify_ab_mismatch": 0,
           "verify_ab_straddle_blocks": 2, "verify_ab_straddle_mismatch": 2}


class VerifyDriver(DraftDriver):
    """A joint_v1(+ab) server adds `verify_*` to the timings block."""
    def complete(self, model, messages, params, timeout=3600):
        out = super().complete(model, messages, params, timeout)
        out["raw_timings"] = {**out["raw_timings"], **_VERIFY, "unrelated": 1}
        return out


def _ladder(driver):
    return L.run_ladder(driver, "m", chars_per_token=4.0, idle_baseline_gb=0.0, model_pid=99999,
                        params=_PARAMS, grid=(160000,), sampler_factory=FakeSampler)


def test_capacity_rows_carry_every_verify_counter_when_the_server_sends_them():
    (row,) = _ladder(VerifyDriver())
    assert row["verify"] == _VERIFY                      # every key, nested histogram included
    assert "unrelated" not in row["verify"]


def test_capacity_rows_verify_is_none_without_counters_and_on_error_rungs():
    assert _ladder(DraftDriver())[0]["verify"] is None
    assert _ladder(FakeDriver([30.0]))[0]["verify"] is None

    class OOMDriver:
        def complete(self, model, messages, params, timeout=3600):
            raise RuntimeError("HTTP Error 500: Internal Server Error")
    (row,) = _ladder(OOMDriver())
    assert row["execution_status"] == "error" and row["verify"] is None


def test_capacity_rows_keep_the_sdpa_and_draft_fields_unchanged():
    (row,) = _ladder(VerifyDriver())
    assert row["draft"]["draft_kind"] == "mtp" and row["sdpa"] is None


def _one_item_run(tmp_path, monkeypatch, raw_timings):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    monkeypatch.setattr(B, "load", lambda b, lim, seed: [{"id": "t1", "prompt": "p"}])
    monkeypatch.setattr(C, "preload", lambda m, **k: 0.0)
    r = {"content": "ok", "reasoning": "", "tool_calls": [], "prompt_tokens": 1,
         "completion_tokens": 10, "decode_tps": 1.0, "peak_mem_gb": 1.0, "finish_reason": "stop",
         "wall_s": 0.1, "raw_timings": raw_timings}
    monkeypatch.setattr(C, "probe", lambda *a, **k: r)
    G.run(["m"], ["aime"], {})
    return json.loads((tmp_path / "m" / "aime.jsonl").read_text().splitlines()[0])


def test_generate_row_keeps_every_verify_counter_when_the_server_sends_them(tmp_path, monkeypatch):
    row = _one_item_run(tmp_path, monkeypatch, {**_VERIFY, "sdpa_forced": 1, "sdpa_auto": 2})
    assert row["verify"] == _VERIFY
    assert row["sdpa"] == {"sdpa_forced": 1, "sdpa_auto": 2}


def test_generate_row_has_no_verify_key_when_the_server_omits_them(tmp_path, monkeypatch):
    row = _one_item_run(tmp_path, monkeypatch, {})
    assert "verify" not in row


def test_client_probe_keeps_verify_counters_in_raw_timings(monkeypatch):
    body = {"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 7},
            "timings": {"prompt_n": 5, "predicted_per_second": 9.0, **_VERIFY}}
    monkeypatch.setattr(C, "_post", lambda path, payload, timeout=3600: body)
    out = C.probe("m", [{"role": "user", "content": "p"}], {})
    assert {k: out["raw_timings"][k] for k in _VERIFY} == _VERIFY
