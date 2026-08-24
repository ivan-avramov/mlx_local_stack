"""O41.0 + O41.1 (operator-approved 2026-08-24): transport failures must ESCALATE, never
be graded.

Measured incident behind these tests: the OpenAI SDK's default read timeout (600 s,
max_retries=2) is SHORTER than a legitimate full-budget generation on every campaign pick
(`Ornith-1.0-35B-mlx-uniform-4bit` 20.7 min measured; `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`
66.3 min projected at its measured 20.6 tok/s) — so a budget-hit item was structurally
converted into `"Error during inference: Request timed out."`, written into the result file
by bfcl_eval's `except Exception` in `multi_threaded_inference`, and scored as a WRONG
ANSWER (`ast_decoder:decoder_failed`). The worker does not cancel abandoned requests, so
each such item also burned ~95 min of worker time across 3 attempts and starved one healthy
neighbour into the same fate (2026-08-24 lab-notebook entries).

Contract under test:
  (a) the client timeout is DERIVED from the deployed profile (max generation / floor
      decode rate + headroom), never inherited from SDK defaults; max_retries=0 — retrying
      a deterministic runaway cannot succeed and costs another full budget (rule C5).
  (b) MLX_BFCL_TIMEOUT_S overrides the derivation (operator escape hatch).
  (c) an API-level failure (timeout, connection refused, 5xx) raises SystemExit — a
      BaseException — so bfcl_eval's `except Exception` CANNOT write it into a result row.
  (d) structural guard on (c): bfcl_eval's own multi_threaded_inference must let
      SystemExit propagate (regression canary against bfcl_eval widening its catch).
  (e) grading refuses poisoned inputs: any `"Error during inference"` row in the raw
      result files nulls `acc` and names the poisoned ids, so even a PRE-EXISTING
      contaminated tree (the 152-row incident) can never be summarized silently again.
"""
import json
import os
import tempfile
import types

import pytest

os.environ.setdefault(
    "BFCL_PROJECT_ROOT",
    os.path.join(tempfile.gettempdir(), "mlx_local_stack_bfcl_robustness_test_root"),
)

pytest.importorskip("bfcl_eval")

import httpx  # noqa: E402  (openai dependency, present whenever openai is)
import openai  # noqa: E402

import bench.bfcl_handler as H  # noqa: E402


def _stub_sampling(monkeypatch, **overrides):
    sampling = {
        "temperature": 0.3, "top_p": 0.95, "top_k": 20, "min_p": 0.0,
        "presence_penalty": 0.0, "max_tokens": 102400, "enable_thinking": True,
        "thinking_budget": 81920,
    }
    sampling.update(overrides)
    from bench import model_params
    monkeypatch.setattr(
        model_params, "params_for",
        lambda model, profile, registry_path=None: dict(sampling),
    )
    return sampling


def _build_handler(monkeypatch, **sampling_overrides):
    _stub_sampling(monkeypatch, **sampling_overrides)
    cls = H._handler_class()
    name = "Qwen3.6-27B-Opus-Distill-OptiQ-4bit"
    return cls(model_name=name, temperature=0.001, registry_name=name, is_fc_model=True)


# ------------------------------------------------------------------ (a) derived timeout
def test_client_timeout_derived_from_deployed_profile_not_sdk_default(monkeypatch):
    monkeypatch.delenv("MLX_BFCL_TIMEOUT_S", raising=False)
    handler = _build_handler(monkeypatch, max_tokens=102400, thinking_budget=81920)
    # Worst legitimate generation = max_tokens at the floor decode rate, plus headroom.
    floor = H._FLOOR_DECODE_TOK_S
    assert handler.client.timeout >= 102400 / floor, (
        "timeout must cover a full max_tokens generation at the floor decode rate — the "
        "600 s SDK default is exceeded by EVERY campaign pick's legitimate worst case")
    assert handler.client.max_retries == 0, (
        "a deterministic runaway retried is pure waste (measured ~95 min per item); "
        "max_retries must be 0")


def test_timeout_env_override_wins(monkeypatch):
    monkeypatch.setenv("MLX_BFCL_TIMEOUT_S", "123.5")
    handler = _build_handler(monkeypatch)
    assert handler.client.timeout == 123.5


# ------------------------------------------------------------------ (c) fail loud
def _raising_client(exc):
    completions = types.SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(exc))
    return types.SimpleNamespace(chat=types.SimpleNamespace(completions=completions))


@pytest.mark.parametrize("exc", [
    openai.APITimeoutError(request=httpx.Request("POST", "http://localhost:8000/v1")),
    openai.APIConnectionError(request=httpx.Request("POST", "http://localhost:8000/v1")),
    openai.InternalServerError(
        "boom",
        response=httpx.Response(500, request=httpx.Request("POST", "http://localhost:8000/v1")),
        body=None,
    ),
])
def test_transport_error_escalates_as_systemexit_never_a_row(monkeypatch, exc):
    handler = _build_handler(monkeypatch)
    handler.client = _raising_client(exc)
    with pytest.raises(SystemExit) as si:
        handler._query_FC({"message": [{"role": "user", "content": "hi"}], "tools": []})
    assert si.value.code == H._TRANSPORT_FAILURE_EXIT


# ------------------------------------------------------------------ (d) bfcl_eval canary
def test_bfcl_eval_generation_loop_cannot_swallow_the_escalation():
    from bfcl_eval._llm_response_generation import multi_threaded_inference

    stub = types.SimpleNamespace(
        inference=lambda *a, **kw: (_ for _ in ()).throw(SystemExit(86)))
    with pytest.raises(SystemExit):
        multi_threaded_inference(stub, {"id": "x", "function": []}, False, False)


# ------------------------------------------------------------------ (e) grading refuses poison
def _write_result_tree(root, model, category, rows):
    d = os.path.join(root, model, "non_live")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"BFCL_v4_{category}_result.json"), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_find_poisoned_rows_names_ids(tmp_path):
    from bench.bfcl_adapter import find_poisoned_rows

    model = "Ornith-1.0-35B-mlx-uniform-4bit"
    _write_result_tree(tmp_path, model, "parallel", [
        {"id": "parallel_0", "result": [{"f": {"a": 1}}]},
        {"id": "parallel_1", "result": "Error during inference: Request timed out."},
    ])
    _write_result_tree(tmp_path, model, "multiple", [
        {"id": "multiple_0", "result": [{"g": {}}]},
    ])
    assert find_poisoned_rows(str(tmp_path), model) == {"parallel": ["parallel_1"]}


def test_poison_guard_nulls_acc_and_names_ids(tmp_path):
    from bench.run_bfcl_fc import _apply_poison_guard

    model = "Ornith-1.0-35B-mlx-uniform-4bit"
    _write_result_tree(tmp_path, model, "parallel", [
        {"id": "parallel_1", "result": "Error during inference: Connection error."},
    ])
    result = {"model": model, "acc": 0.9, "n": 200}
    guarded = _apply_poison_guard(result, str(tmp_path), model)
    assert guarded["acc"] is None
    assert guarded["poisoned_items"]["parallel"] == ["parallel_1"]
    assert "re-run" in guarded["note"].lower()


def test_poison_guard_passes_clean_tree_through(tmp_path):
    from bench.run_bfcl_fc import _apply_poison_guard

    model = "Ornith-1.0-35B-mlx-uniform-4bit"
    _write_result_tree(tmp_path, model, "parallel", [
        {"id": "parallel_0", "result": [{"f": {"a": 1}}]},
    ])
    result = {"model": model, "acc": 0.9, "n": 200}
    assert _apply_poison_guard(result, str(tmp_path), model) == result
