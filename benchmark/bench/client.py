"""HTTP client for the mlx-serve router (:8000). Pure stdlib, non-streaming.

Speed/quality facts baked in (see model_eval_plan.md):
- Read the upstream `timings` object from the response body for decode tok/s + peak mem.
- Models think into a separate `reasoning` field; `content` is the answer. We still
  strip any inline <think>...</think> defensively.
- max_tokens must be generous or the thinking trace eats the whole budget.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

BASE = os.environ.get("MLX_SERVE_BASE", "http://localhost:8000")
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _post(path: str, payload: dict, timeout: float = 3600) -> dict:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _get(path: str, timeout: float = 60) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode())


def roster() -> list[str]:
    """Models the live router serves (self-correcting against main_models.yaml)."""
    return [m["id"] for m in _get("/v1/models")["data"]]


def preload(model: str, timeout: float = 900) -> float:
    t0 = time.perf_counter()
    _post("/v1/models/load", {"model": model, "keep_alive": "240m"}, timeout=timeout)
    return round(time.perf_counter() - t0, 1)


def strip_thinking(text: str) -> str:
    return _THINK.sub("", text or "").strip()


def probe(model: str, messages: list, params: dict, timeout: float = 3600) -> dict:
    """One non-streaming completion using the model's production params (temperature,
    top_p, top_k, min_p, repetition_penalty, presence_penalty, max_tokens,
    enable_thinking, thinking_budget — all forwarded to mlx_vlm). Returns answer text +
    timing/length telemetry."""
    body = {"model": model, "messages": messages, "stream": False, **params}
    t0 = time.perf_counter()
    r = _post("/v1/chat/completions", body, timeout=timeout)
    wall = time.perf_counter() - t0
    tm = r.get("timings") or {}
    us = r.get("usage") or {}
    msg = (r.get("choices") or [{}])[0].get("message", {})
    return {
        "content": msg.get("content") or "",
        "reasoning": msg.get("reasoning") or "",
        "prompt_tokens": us.get("prompt_tokens") or tm.get("prompt_n"),
        "completion_tokens": us.get("completion_tokens"),
        "decode_tps": tm.get("predicted_per_second"),
        "peak_mem_gb": tm.get("peak_memory"),
        "finish_reason": (r.get("choices") or [{}])[0].get("finish_reason"),
        "wall_s": round(wall, 1),
    }
