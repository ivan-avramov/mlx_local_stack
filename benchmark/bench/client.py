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


class MalformedResponseError(RuntimeError):
    """5th cold review P18: an HTTP 200 whose body is an error envelope or has no usable
    `choices[0].message` must never silently produce an EMPTY completion (the old
    `(r.get("choices") or [{}])[0].get("message", {})` chain defaults all the way down to
    `content=""`/`tool_calls=[]` with no signal anything went wrong). Raise instead -- callers
    that already treat a `driver.complete` exception as a transport-class failure (escalate, never
    grade; see `bench.agent_loop.run_agent`'s broad except around the complete() call) pick this up
    for free."""


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


def probe(model: str, messages: list, params: dict, timeout: float = 3600, tools=None) -> dict:
    """One non-streaming completion using the model's production params (temperature,
    top_p, top_k, min_p, repetition_penalty, presence_penalty, max_tokens,
    enable_thinking, thinking_budget — all forwarded to mlx_vlm). Returns answer text +
    timing/length telemetry."""
    body = {"model": model, "messages": messages, "stream": False, **params}
    if tools:
        body["tools"] = tools
    t0 = time.perf_counter()
    r = _post("/v1/chat/completions", body, timeout=timeout)
    wall = time.perf_counter() - t0
    if not isinstance(r, dict):
        raise MalformedResponseError(f"{model}: HTTP 200 body is not a JSON object "
                                     f"(type={type(r).__name__})")
    if r.get("error"):
        raise MalformedResponseError(f"{model}: HTTP 200 body is an error envelope: {r['error']!r}")
    choices = r.get("choices")
    if not choices or not isinstance(choices, list):
        raise MalformedResponseError(f"{model}: HTTP 200 body has no `choices` "
                                     f"(keys={sorted(r.keys())})")
    if choices[0].get("message") is None:
        raise MalformedResponseError(f"{model}: choices[0] has no `message` key "
                                     f"(keys={sorted(choices[0].keys())})")
    tm = r.get("timings") or {}
    us = r.get("usage") or {}
    msg = choices[0]["message"]
    # 6th cold review round 6 P24 (HIGH): the mlx-serve router ALWAYS returns content-or-
    # tool_calls, a finish_reason, and usage.{prompt,completion}_tokens -- their absence is a
    # SERVING anomaly, never a legitimate "the model produced nothing" signal, and must never
    # silently become a scored failure/non-convergence. Reproduced: `{"choices":[{"message":{}}]}`
    # produced an eight-turn, scored `no_submit` row end-to-end.
    if not msg.get("content") and not msg.get("tool_calls"):
        raise MalformedResponseError(f"{model}: assistant message has neither content nor "
                                     f"tool_calls (keys={sorted(msg.keys())})")
    if choices[0].get("finish_reason") is None:
        raise MalformedResponseError(f"{model}: choices[0] is missing finish_reason")
    prompt_tokens = us.get("prompt_tokens") or tm.get("prompt_n")
    if prompt_tokens is None or us.get("completion_tokens") is None:
        raise MalformedResponseError(f"{model}: usage is missing prompt_tokens/completion_tokens "
                                     f"(usage={us!r}, timings.prompt_n={tm.get('prompt_n')!r})")
    return {
        "content": msg.get("content") or "",
        "reasoning": msg.get("reasoning") or "",
        "tool_calls": msg.get("tool_calls") or [],
        "prompt_tokens": prompt_tokens,
        "completion_tokens": us.get("completion_tokens"),
        "decode_tps": tm.get("predicted_per_second"),
        "peak_mem_gb": tm.get("peak_memory"),
        "finish_reason": (r.get("choices") or [{}])[0].get("finish_reason"),
        "wall_s": round(wall, 1),
        "raw_timings": tm,
    }
