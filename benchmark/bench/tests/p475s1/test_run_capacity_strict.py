"""`bench.run_capacity --p475-strict` (contract component 2): backend telemetry persisted, session ids, the decode carrier, the
256-token cap, rung problems -> nonzero; and without the flag the default output is unchanged (an invariant)."""
import json
import os
from pathlib import Path

import pytest

import bench.run_capacity as R
from bench.retrieval import make_question

from .fakes import PICK

pytestmark = pytest.mark.usefixtures("pin_mtp_scan")

CARRIER = Path(R.__file__).parent / "data" / "p475_decode_carrier.txt"
BASELINE_KEYS = {
    "ctx", "peak_rss_gb", "model_footprint_gb", "system_peak_gb", "server_peak_gb", "prefill_s", "prefill_tps", "decode_tps",
    "prompt_tokens", "bottleneck", "schema_version", "memory_target_gb", "execution_status", "elapsed_s", "finish_reason",
    "completion_tokens", "retrieval_acc", "within_memory_target", "memory_telemetry_note", "draft", "acceptance", "sdpa",
    "verify", "thinking_budget", "resolved_thinking_budget", "converged"}
STRICT_KEYS = {"prompt_ms", "prompt_per_second", "prompt_n", "cache_n", "predicted_n", "predicted_per_second",
               "peak_memory_gb_cumulative", "session_id"}
DEPLOYED = {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 0.0, "max_tokens": 32768,
            "enable_thinking": True, "thinking_budget": 4096}


class Sampler:
    system_peak_gb, peak_rss_gb = 45.0, 35.0
    def __init__(self, **kw): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass


class Driver:
    """A backend that answers like the stack: server timings in `raw_timings`, a session id per request."""
    def __init__(self, *, on=True, finish="length", completion=256, session=None, raw=None, prefix="p475-leg"):
        self.calls, self.on, self.finish, self.completion, self.raw_over = [], on, finish, completion, raw or {}
        self.session, self.prefix = session, prefix

    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600, tools=None):
        i = len(self.calls)
        self.calls.append({"messages": messages, "params": dict(params)})
        sid = (self.session(i) if callable(self.session) else self.session) if self.session is not None else f"{self.prefix}-{i:04d}"
        if params.get("max_tokens") == 1:                    # the chars-per-token calibration request
            return {"content": "", "prompt_tokens": 1000, "completion_tokens": 1, "finish_reason": "length",
                    "prefill_s": 1.0, "prefill_tps": 1000, "decode_tps": 10.0, "peak_mem_gb": 20.0, "raw_timings": {},
                    "session_id": sid}
        raw = {"prompt_n": 40000, "cache_n": 0, "predicted_n": 256, "prompt_ms": 100000.0, "prompt_per_second": 400.0,
               "predicted_per_second": 38.5, "peak_memory": 33.5}
        if self.on:
            raw.update(draft_kind="mtp", draft_rounds=100, draft_n=200, draft_n_accepted=140)
        raw.update(self.raw_over)
        return {"content": "x" * 10, "prompt_tokens": 40000, "completion_tokens": self.completion, "finish_reason": self.finish,
                "prefill_s": 100.0, "prefill_tps": 400, "decode_tps": 38.5, "peak_mem_gb": raw.get("peak_memory"),
                "raw_timings": raw, "session_id": sid}


def setup(tmp_path, monkeypatch, driver, *, prefix="p475-leg", off_registry=False):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: driver)
    monkeypatch.setattr(R, "MemorySampler", Sampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path / "results"))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "await_model_pid", lambda: 12345)
    monkeypatch.setattr(R, "params_for", lambda model, profile="production", registry_path=None: dict(DEPLOYED))
    if prefix is None:
        monkeypatch.delenv("MLX_BENCH_SESSION_PREFIX", raising=False)
    else:
        monkeypatch.setenv("MLX_BENCH_SESSION_PREFIX", prefix)
    if off_registry:                       # the committed registry with the entry's MTP lines commented (the OFF arm)
        from bench import paths
        text = (paths.repo_root() / "main_models.yaml").read_text()
        i = text.index(f"  - name: {PICK}")
        head, tail = text[:i], text[i:]
        tail = tail.replace("\n    draft_kind: mtp", "\n    # draft_kind: mtp", 1)
        tail = tail.replace("\n    draft_model: ", "\n    # draft_model: ", 1)
        reg = tmp_path / "off_registry.yaml"
        reg.write_text(head + tail)
        monkeypatch.setenv("MLX_SERVE_CONFIG", str(reg))
    return tmp_path / "results" / PICK


def go(extra=(), grid="8192,131072", tag="p475-t"):
    return R.main(["--model", PICK, "--grid", grid, "--no-preload", "--sampling-profile", "deployed", "--seed", "0",
                   "--out-tag", tag, *extra])


def rows_of(out, tag="p475-t"):
    return [json.loads(x) for x in (out / f"capacity_ladder.{tag}.jsonl").read_text().splitlines()]


# ------------------------------------------------------------------------------------------- accepted run
def test_strict_flag_is_accepted_and_a_good_on_run_exits_zero(tmp_path, monkeypatch):
    # class: exercises new behaviour
    d = Driver()
    out = setup(tmp_path, monkeypatch, d)
    assert go(["--p475-strict"]) == 0
    assert len(rows_of(out)) == 2


def test_each_measured_row_persists_the_backend_telemetry(tmp_path, monkeypatch):
    # class: exercises new behaviour
    out = setup(tmp_path, monkeypatch, Driver())
    go(["--p475-strict"])
    for row in rows_of(out):
        assert STRICT_KEYS <= set(row)
        assert (row["prompt_ms"], row["prompt_per_second"], row["prompt_n"], row["cache_n"], row["predicted_n"]) == \
               (100000.0, 400.0, 40000, 0, 256)
        assert row["predicted_per_second"] == 38.5
        assert row["peak_memory_gb_cumulative"] == 33.5
        assert (row["draft_kind"], row["draft_n"], row["draft_n_accepted"], row["draft_rounds"]) == ("mtp", 200, 140, 100)


def test_rows_carry_the_requests_session_ids_and_they_differ(tmp_path, monkeypatch):
    # class: exercises new behaviour
    d = Driver()
    out = setup(tmp_path, monkeypatch, d)
    go(["--p475-strict"])
    sids = [r["session_id"] for r in rows_of(out)]
    assert sids == ["p475-leg-0001", "p475-leg-0002"]       # calls 1 and 2 (call 0 is the calibration)
    assert len(set(sids)) == len(sids)


def test_retrieval_is_not_scored_in_strict_mode(tmp_path, monkeypatch):
    # class: exercises new behaviour
    out = setup(tmp_path, monkeypatch, Driver())
    go(["--p475-strict"])
    assert all(r["retrieval_acc"] is None for r in rows_of(out))


# ------------------------------------------------------------------------------------------- prompt and parameters
def test_the_decode_carrier_file_is_committed_and_nonempty():
    # class: exercises new behaviour
    assert CARRIER.is_file() and CARRIER.read_text().strip()


def test_measured_prompt_is_context_plus_the_carrier_not_the_retrieval_question(tmp_path, monkeypatch):
    # class: exercises new behaviour
    d = Driver()
    setup(tmp_path, monkeypatch, d)
    go(["--p475-strict"])
    carrier = CARRIER.read_text().strip()
    for call in d.calls[1:]:
        content = call["messages"][-1]["content"]
        assert content.rstrip().endswith(carrier)
        assert "secret codes" not in content and make_question(["a"])[:40] not in content


def test_measured_requests_are_capped_at_256_with_deployed_sampling_and_thinking_as_deployed(tmp_path, monkeypatch):
    # class: exercises new behaviour (contract: max_tokens 256, deployed sampling, thinking as deployed)
    d = Driver()
    setup(tmp_path, monkeypatch, d)
    go(["--p475-strict"])
    for call in d.calls[1:]:
        p = call["params"]
        assert p["max_tokens"] == 256 and p["seed"] == 0
        assert p["thinking_budget"] == DEPLOYED["thinking_budget"] and p["enable_thinking"] is True
        assert (p["temperature"], p["top_p"], p["top_k"]) == (0.6, 0.95, 20)


# ------------------------------------------------------------------------------------------- session ids
def test_strict_requires_the_session_prefix_and_requests_nothing_without_it(tmp_path, monkeypatch):
    # class: exercises new behaviour
    d = Driver()
    setup(tmp_path, monkeypatch, d, prefix="p475-leg")
    assert go(["--p475-strict"], tag="p475-with") == 0           # the flag itself is accepted (an unknown flag would also exit 2)
    before = len(d.calls)
    monkeypatch.delenv("MLX_BENCH_SESSION_PREFIX")
    with pytest.raises(SystemExit) as e:
        raise SystemExit(go(["--p475-strict"], tag="p475-without"))
    assert e.value.code not in (0, None)
    assert len(d.calls) == before                                  # nothing was requested


def test_a_session_id_repeated_between_calibration_and_a_rung_fails_the_run(tmp_path, monkeypatch):
    # class: exercises new behaviour (unique per request, calibration included)
    d = Driver(session=lambda i: "p475-leg-same" if i in (0, 1) else f"p475-leg-{i}")
    setup(tmp_path, monkeypatch, d)
    assert go(["--p475-strict"]) != 0


def test_a_session_id_repeated_between_two_rungs_fails_the_run(tmp_path, monkeypatch):
    # class: exercises new behaviour
    d = Driver(session=lambda i: "p475-leg-same" if i in (1, 2) else f"p475-leg-{i}")
    setup(tmp_path, monkeypatch, d)
    assert go(["--p475-strict"]) != 0


def test_a_missing_session_id_fails_the_run(tmp_path, monkeypatch):
    # class: exercises new behaviour
    d = Driver(session=lambda i: None if i == 1 else f"p475-leg-{i}")
    setup(tmp_path, monkeypatch, d)
    assert go(["--p475-strict"]) != 0


# ------------------------------------------------------------------------------------------- rung problems -> recorded + nonzero
@pytest.mark.parametrize("kw", [dict(finish="stop"), dict(completion=255), dict(raw={"predicted_n": 255}),
                                dict(raw={"cache_n": 7}), dict(raw={"prompt_per_second": 800.0}),
                                dict(raw={"draft_n": 0}), dict(raw={"draft_kind": None})])
def test_a_rung_with_problems_is_recorded_with_them_and_the_run_exits_nonzero(tmp_path, monkeypatch, kw):
    # class: exercises new behaviour
    out = setup(tmp_path, monkeypatch, Driver(**kw))
    rc = go(["--p475-strict"], grid="8192")
    rows = rows_of(out)
    assert rc != 0 and len(rows) == 1
    flagged = [k for k, v in rows[0].items() if "problem" in k and v]
    assert flagged, "the row must carry its problems"


def test_off_run_with_null_drafter_keys_is_clean(tmp_path, monkeypatch):
    # class: exercises new behaviour (OFF: every drafter key absent or null)
    d = Driver(on=False, raw=dict(draft_kind=None, draft_rounds=None, draft_n=None, draft_n_accepted=None))
    setup(tmp_path, monkeypatch, d, off_registry=True)
    assert go(["--p475-strict"]) == 0


def test_off_run_that_reports_a_drafter_fails(tmp_path, monkeypatch):
    # class: exercises new behaviour
    setup(tmp_path, monkeypatch, Driver(on=True), off_registry=True)
    assert go(["--p475-strict"]) != 0


def test_on_run_without_drafter_counters_fails(tmp_path, monkeypatch):
    # class: exercises new behaviour
    setup(tmp_path, monkeypatch, Driver(on=False))
    assert go(["--p475-strict"]) != 0


# ------------------------------------------------------------------------------------------- unchanged default
def test_default_run_has_exactly_the_baseline_row_keys(tmp_path, monkeypatch):
    # class: preserves an invariant (no --p475-strict: byte-identical output shape)
    out = setup(tmp_path, monkeypatch, Driver(), prefix=None)
    assert go() == 0
    for row in rows_of(out):
        assert set(row) == BASELINE_KEYS
        assert not (STRICT_KEYS & set(row))


def test_default_run_keeps_the_retrieval_question_and_the_bounded_budget(tmp_path, monkeypatch):
    # class: preserves an invariant
    d = Driver()
    setup(tmp_path, monkeypatch, d, prefix=None)
    go()
    for call in d.calls[1:]:
        assert "secret codes" in call["messages"][-1]["content"]
        assert call["params"]["max_tokens"] == 256 and call["params"]["thinking_budget"] == 256


def test_default_run_does_not_need_a_session_prefix(tmp_path, monkeypatch):
    # class: preserves an invariant
    setup(tmp_path, monkeypatch, Driver(), prefix=None)
    assert go() == 0


def test_default_run_ignores_rung_problems(tmp_path, monkeypatch):
    # class: preserves an invariant (a `stop` finish is normal for the retrieval ladder)
    setup(tmp_path, monkeypatch, Driver(finish="stop", completion=10), prefix=None)
    assert go() == 0


def test_default_output_files_are_the_same_three(tmp_path, monkeypatch):
    # class: preserves an invariant
    out = setup(tmp_path, monkeypatch, Driver(), prefix=None)
    go()
    assert sorted(p.name for p in out.iterdir()) == [
        "capacity_ladder.p475-t.jsonl", "capacity_ladder.p475-t.manifest.json", "capacity_retrieval.p475-t.json"]
