"""Framework-agnostic completion driver. MVP backend: the mlx-serve router via the
existing stdlib client. The Driver protocol is the seam llama.cpp slots into later."""
from typing import Protocol
from . import client


class Driver(Protocol):
    def preload(self, model: str, timeout: float = 900) -> float: ...
    def complete(self, model: str, messages: list, params: dict,
                 timeout: float = 3600) -> dict: ...


class MlxServeDriver:
    """Wraps benchmark.bench.client. Derives prefill_s / prefill_tps from the server
    timings the same way needle_256k.py does (wall minus server-reported decode time)."""

    def preload(self, model: str, timeout: float = 900) -> float:
        return client.preload(model, timeout=timeout)

    def complete(self, model: str, messages: list, params: dict,
                 timeout: float = 3600) -> dict:
        r = client.probe(model, messages, params, timeout=timeout)
        tm = r.get("raw_timings") or {}
        wall = r.get("wall_s") or 0.0
        pred_ms = tm.get("predicted_ms") or 0.0
        pt = r.get("prompt_tokens")
        prefill_s = max(wall - pred_ms / 1000, 0.01)
        return {
            "content": r.get("content", ""),
            "reasoning": r.get("reasoning", ""),
            "prompt_tokens": pt,
            "completion_tokens": r.get("completion_tokens"),
            "decode_tps": r.get("decode_tps"),
            "prefill_s": round(prefill_s, 2),
            "prefill_tps": round(pt / prefill_s) if pt else None,
            "peak_mem_gb": r.get("peak_mem_gb"),
            "wall_s": wall,
            "finish_reason": r.get("finish_reason"),
        }
