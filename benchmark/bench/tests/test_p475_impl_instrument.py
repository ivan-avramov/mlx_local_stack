"""P475 stage 1 (implementer tests): the KV line (R2, R22), strict rungs (R21) and `run_capacity --p475-strict`."""
from __future__ import annotations

import json
import os

import pytest

import bench.run_capacity as R
from bench import kv_line as KV
from bench.capacity_ladder import rung_problems
from bench.tests.test_p475_impl_support import kv_log_line, ladder_row

pytestmark_mtp = pytest.mark.usefixtures("pin_mtp_scan")


# ------------------------------------------------------------------------------------------------ KV line
@pytest.mark.parametrize("arm", KV.ARM_FORMATS)
def test_the_real_line_format_parses_and_matches_its_arm(arm):
    parsed = KV.parse_kv_line(kv_log_line(arm))
    assert list(parsed) == list(KV.FIELDS)
    assert KV.kv_line_problems(parsed, arm) == []


def test_parse_takes_a_string_or_a_list_and_the_last_line_wins():
    text = kv_log_line("TQ4") + "noise\n" + kv_log_line("AF8")
    assert KV.parse_kv_line(text)["kv_quant_scheme"] == "uniform"
    assert KV.parse_kv_line(text.splitlines())["kv_bits"] == 8.0
    assert KV.parse_kv_line(text.splitlines(keepends=True)) == KV.parse_kv_line(text)


@pytest.mark.parametrize("bad", ["", "no line here\n", "KV cache resolved: kv_bits=4.0\n",
                                 kv_log_line("AF8").replace("kv_group_size=64", "kv_group_size=<object>"),
                                 kv_log_line("AF8").replace("kv_bits=8.0", "kv_bits=8.0 kv_bits=4.0")])
def test_parse_refuses_absent_or_malformed(bad):
    with pytest.raises(KV.KVLineError):
        KV.parse_kv_line(bad)


@pytest.mark.parametrize("over, arm, match", [
    (dict(kv_bits=4.0), "AF8", "kv_bits"),
    (dict(kv_quant_scheme="turboquant"), "AF8", "kv_quant_scheme"),
    (dict(kv_key_bits=4), "TQ4", "kv_key_bits"),
    (dict(kv_value_scheme="uniform"), "AF4", "kv_value_scheme"),
    (dict(kv_group_size=32), "AF4", "kv_group_size"),
    (dict(quantized_kv_start=5000), "TQ8", "quantized_kv_start"),
    (dict(TQ_KV_QUANT_MODE="prod"), "TQ8", "TQ_KV_QUANT_MODE"),
    (dict(kv_bits=8.0, kv_quant_scheme="uniform"), "N16", "kv_bits"),
])
def test_kv_line_problems_catch_every_field(over, arm, match):
    problems = KV.kv_line_problems(KV.parse_kv_line(kv_log_line(arm, **over)), arm)
    assert any(match in p for p in problems), problems


def test_numeric_comparisons_accept_either_type_but_not_bool():
    p = KV.parse_kv_line(kv_log_line("AF8", kv_bits=8, quantized_kv_start=0.0))
    assert KV.kv_line_problems(p, "AF8") == []
    assert KV.kv_line_problems(KV.parse_kv_line(kv_log_line("N16", kv_bits=0)), "N16") == []
    assert KV.kv_line_problems(KV.parse_kv_line(kv_log_line("N16", kv_bits=None, kv_quant_scheme="turboquant")), "N16") == []
    assert KV.kv_line_problems(KV.parse_kv_line(kv_log_line("N16", kv_bits=False)), "N16")
    assert KV.kv_line_problems(KV.parse_kv_line(kv_log_line("AF8", quantized_kv_start=False)), "AF8")


def test_tq_mode_is_not_compared_on_affine_arms():
    assert KV.kv_line_problems(KV.parse_kv_line(kv_log_line("AF4", TQ_KV_QUANT_MODE="prod")), "AF4") == []
    assert KV.expected_kv("TQ4-OFF") == KV.expected_kv("TQ4")


# ------------------------------------------------------------------------------------------------ rung_problems (R21)
def test_a_good_rung_has_no_problem_on_and_off():
    assert rung_problems(ladder_row(8192, "on", "p"), "on") == []
    assert rung_problems(ladder_row(8192, "off", "p"), "off") == []
    off = ladder_row(8192, "off", "p")
    for k in ("draft_kind", "draft_n", "draft_n_accepted", "draft_rounds"):
        off.pop(k)
    assert rung_problems(off, "off") == []                        # absent keys are fine OFF


@pytest.mark.parametrize("over, predictor, match", [
    (dict(completion_tokens=255), "on", "completion_tokens"),
    (dict(predicted_n=200), "on", "predicted_n"),
    (dict(finish_reason="stop"), "on", "finish_reason"),
    (dict(cache_n=12), "on", "cache_n"),
    (dict(cache_n=None), "on", "cache_n"),
    (dict(cache_n=False), "on", "cache_n"),
    (dict(prompt_per_second=600.0), "on", "2 %"),
    (dict(prompt_ms=None), "on", "prefill telemetry"),
    (dict(prompt_n=1), "on", "prompt_n"),
    (dict(draft_kind="suffix"), "on", "draft_kind"),
    (dict(draft_n=0), "on", "draft_n"),
    (dict(draft_n_accepted=500), "on", "draft_n_accepted"),
    (dict(draft_n_accepted=-1), "on", "draft_n_accepted"),
    (dict(draft_rounds=0), "on", "draft_rounds"),
    (dict(draft_kind=None, draft_n=None, draft_n_accepted=None, draft_rounds=None), "on", "draft_kind"),
    (dict(draft_kind="mtp"), "off", "drafter"),
    (dict(draft_n=3), "off", "drafter"),
    (dict(execution_status="error", error="Timeout"), "on", "execution_status"),
])
def test_every_rung_refusal(over, predictor, match):
    row = ladder_row(8192, predictor, "p", **over)
    problems = rung_problems(row, predictor)
    assert any(match in p for p in problems), problems


def test_cache_n_float_zero_and_two_percent_edge():
    row = ladder_row(8192, "on", "p", cache_n=0.0)
    assert rung_problems(row, "on") == []
    derived = row["prompt_n"] / (row["prompt_ms"] / 1000)
    assert rung_problems(dict(row, prompt_per_second=derived * 1.019), "on") == []
    assert rung_problems(dict(row, prompt_per_second=derived * 1.021), "on")


# ------------------------------------------------------------------------------------------------ run_capacity
class StrictDriver:
    """A driver returning what MlxServeDriver returns for the fork's timings block."""

    def __init__(self, predictor="on", draft_keys=True, session_ids=True, bad_ctx=None):
        self.predictor, self.draft_keys, self.session_ids, self.bad_ctx = predictor, draft_keys, session_ids, bad_ctx
        self.calls = []

    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        self.calls.append(dict(messages=messages, params=dict(params)))
        prompt = messages[0]["content"]
        n = max(1, len(prompt) // 4)
        first = len(self.calls) == 1
        ct = 1 if first else 256
        raw = dict(prompt_n=n, prompt_ms=n / 400 * 1000, prompt_per_second=400.0, cache_n=0, predicted_n=ct,
                   predicted_per_second=31.5, predicted_ms=ct / 31.5 * 1000, peak_memory=22.5 + len(self.calls))
        if self.predictor == "on" and self.draft_keys:
            raw.update(draft_kind="mtp", draft_n=180, draft_n_accepted=120, draft_rounds=90)
        elif self.draft_keys:
            raw.update(draft_kind=None, draft_n=None, draft_n_accepted=None, draft_rounds=None)
        if self.bad_ctx and not first and str(self.bad_ctx) == "all":
            raw["cache_n"] = 4096
        prefix = os.environ.get("MLX_BENCH_SESSION_PREFIX")
        return {"content": "def pop(self):", "reasoning": "", "prompt_tokens": n, "completion_tokens": ct,
                "finish_reason": "length", "prefill_s": 1.0, "prefill_tps": 100, "decode_tps": 31.5, "peak_mem_gb": 22.5,
                "raw_timings": raw, "session_id": (f"{prefix}-{len(self.calls):016x}" if self.session_ids else None)}


class FakeSampler:
    def __init__(self, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    system_peak_gb = 45.0
    peak_rss_gb = 35.0


def _world(tmp_path, monkeypatch, driver, predictor="on"):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: driver)
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "await_model_pid", lambda: 12345)
    monkeypatch.setattr(R, "served_predictor", lambda model: predictor)


def _rows(tmp_path, model, tag):
    return [json.loads(x) for x in open(os.path.join(tmp_path, model, f"capacity_ladder.{tag}.jsonl"))]


@pytest.mark.usefixtures("pin_mtp_scan")
def test_strict_rows_persist_backend_telemetry_and_the_carrier(tmp_path, monkeypatch):
    drv = StrictDriver()
    _world(tmp_path, monkeypatch, drv)
    monkeypatch.setenv("MLX_BENCH_SESSION_PREFIX", "p475-u4-n16-b1.a1")
    rc = R.main(["--model", "m", "--grid", "1000,2000", "--sampling-profile", "production", "--out-tag", "t",
                 "--p475-strict"])
    assert rc == 0
    rows = _rows(tmp_path, "m", "t")
    carrier = R.P475_CARRIER.read_text()
    assert all(c["messages"][0]["content"].endswith("\n\n" + carrier) for c in drv.calls[1:])
    assert drv.calls[1]["params"]["max_tokens"] == 256
    assert "thinking_budget" not in drv.calls[1]["params"] or drv.calls[1]["params"]["thinking_budget"] != 256
    for r in rows:
        for k in ("prompt_ms", "prompt_per_second", "prompt_n", "cache_n", "predicted_n", "predicted_per_second",
                  "peak_memory_gb_cumulative", "draft_kind", "draft_n", "draft_n_accepted", "draft_rounds", "session_id"):
            assert k in r, k
        assert r["retrieval_acc"] is None and r["rung_problems"] == [] and r["predictor"] == "on"
    assert rows[0]["peak_memory_gb_cumulative"] == 24.5          # the cumulative peak of the request, not the prefill spike
    man = json.load(open(os.path.join(tmp_path, "m", "capacity_ladder.t.manifest.json")))
    strict = man["runtime"]["p475_strict"]
    assert strict["calibration_session_id"].startswith("p475-u4-n16-b1.a1-") and strict["rung_problems"] == []


@pytest.mark.usefixtures("pin_mtp_scan")
def test_strict_off_rows_keep_the_drafter_key_shape(tmp_path, monkeypatch):
    _world(tmp_path, monkeypatch, StrictDriver("off", draft_keys=False), predictor="off")
    monkeypatch.setenv("MLX_BENCH_SESSION_PREFIX", "px")
    assert R.main(["--model", "m", "--grid", "1000", "--sampling-profile", "production", "--out-tag", "t", "--p475-strict"]) == 0
    row = _rows(tmp_path, "m", "t")[0]
    assert "draft_kind" not in row and row["rung_problems"] == []


@pytest.mark.usefixtures("pin_mtp_scan")
def test_a_strict_rung_with_problems_is_recorded_and_the_run_exits_nonzero(tmp_path, monkeypatch):
    _world(tmp_path, monkeypatch, StrictDriver(bad_ctx="all"))
    monkeypatch.setenv("MLX_BENCH_SESSION_PREFIX", "px")
    assert R.main(["--model", "m", "--grid", "1000,2000", "--sampling-profile", "production", "--out-tag", "t",
                   "--p475-strict"]) == 1
    rows = _rows(tmp_path, "m", "t")
    assert len(rows) == 2 and all(any("cache_n" in p for p in r["rung_problems"]) for r in rows)


@pytest.mark.usefixtures("pin_mtp_scan")
def test_strict_needs_a_session_id_on_every_request(tmp_path, monkeypatch):
    _world(tmp_path, monkeypatch, StrictDriver(session_ids=False))
    monkeypatch.setenv("MLX_BENCH_SESSION_PREFIX", "px")
    assert R.main(["--model", "m", "--grid", "1000", "--sampling-profile", "production", "--out-tag", "t", "--p475-strict"]) == 1
    assert any("session id" in p for p in _rows(tmp_path, "m", "t")[0]["rung_problems"])


def test_strict_refuses_without_the_session_prefix(monkeypatch):
    monkeypatch.delenv("MLX_BENCH_SESSION_PREFIX", raising=False)
    with pytest.raises(SystemExit) as e:
        R.main(["--model", "m", "--grid", "1000", "--sampling-profile", "production", "--p475-strict"])
    assert e.value.code == 2


@pytest.mark.usefixtures("pin_mtp_scan")
def test_the_default_output_is_unchanged_without_the_flag(tmp_path, monkeypatch):
    """Without --p475-strict: the retrieval question, thinking_budget 256, no strict field on a row or the manifest."""
    drv = StrictDriver()
    _world(tmp_path, monkeypatch, drv)
    monkeypatch.setenv("MLX_BENCH_SESSION_PREFIX", "px")
    assert R.main(["--model", "m", "--grid", "1000", "--sampling-profile", "production", "--out-tag", "t"]) in (0, 1)
    row = _rows(tmp_path, "m", "t")[0]
    assert drv.calls[1]["params"]["thinking_budget"] == 256 and drv.calls[1]["params"]["max_tokens"] == 256
    assert R.P475_CARRIER.read_text() not in drv.calls[1]["messages"][0]["content"]
    for k in ("prompt_ms", "cache_n", "peak_memory_gb_cumulative", "session_id", "rung_problems", "predictor", "draft_n"):
        assert k not in row, k
    man = json.load(open(os.path.join(tmp_path, "m", "capacity_ladder.t.manifest.json")))
    assert "p475_strict" not in man["runtime"]
    assert set(row) == {"ctx", "server_peak_gb", "peak_rss_gb", "system_peak_gb", "model_footprint_gb", "prefill_s",
                        "prefill_tps", "decode_tps", "prompt_tokens", "schema_version", "memory_target_gb", "execution_status",
                        "elapsed_s", "finish_reason", "completion_tokens", "retrieval_acc", "within_memory_target",
                        "memory_telemetry_note", "draft", "acceptance", "sdpa", "verify", "thinking_budget",
                        "resolved_thinking_budget", "converged", "bottleneck"}


def test_the_carrier_is_committed_code_continuation_text():
    text = R.P475_CARRIER.read_text()
    assert "```python" in text and "class Scheduler" in text and len(text) > 500
