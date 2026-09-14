"""Capacity ladder with a descriptive memory target and independent retrieval co-score.
Continue completed requests across target overruns; stop on actual request failure.
"""
from dataclasses import asdict
import time
import json
from .scorecard import MEMORY_TARGET_GB, within_memory_target
from .instrument import MemorySampler, PerfRecord
from .retrieval import build_context, make_question, score

DEFAULT_GRID = (160_000, 192_000, 224_000, 256_000)


def _draft_from_raw(raw_timings: dict) -> dict | None:
    """Speculative-decoding engagement counters from `out["raw_timings"]`, or None when
    the server reports no drafter (draft_kind absent -> suffix/MTP was not engaged)."""
    if not raw_timings or raw_timings.get("draft_kind") is None:
        return None
    return {k: raw_timings.get(k) for k in
            ("draft_kind", "draft_rounds", "draft_n", "draft_n_accepted")}


def _acceptance_from_draft(draft: dict | None) -> float | None:
    if not draft or not draft.get("draft_n") or draft.get("draft_n_accepted") is None:
        return None
    return round(draft["draft_n_accepted"] / draft["draft_n"], 4)


def _is_timeout_error(e: Exception) -> bool:
    """True when `e` is (or wraps) a client-side request timeout, as opposed to a hard
    OOM/disconnect. `bench/client.py` uses stdlib urllib, whose `urlopen(timeout=...)`
    raises `socket.timeout` -- an alias of `TimeoutError` since Python 3.10 -- either
    directly or wrapped in `urllib.error.URLError.reason`. `requests.exceptions.Timeout`
    / `httpx.TimeoutException` are checked too (F2) in case the client backend changes."""
    if isinstance(e, TimeoutError):
        return True
    reason = getattr(e, "reason", None)
    if isinstance(reason, TimeoutError):
        return True
    try:
        import requests
        if isinstance(e, requests.exceptions.Timeout):
            return True
    except ImportError:
        pass
    try:
        import httpx
        if isinstance(e, httpx.TimeoutException):
            return True
    except ImportError:
        pass
    return False


def _progress_line(row: dict) -> str:
    return (f"[capacity] rung ctx={row['ctx']} server_peak_gb={row.get('server_peak_gb')} "
            f"execution={row.get('execution_status')} "
            f"within_memory_target={row.get('within_memory_target')} prefill_s={row.get('prefill_s')} "
            f"error={row.get('error')}")


def validate_completion(out):
    """Reject normalized HTTP-200 error/malformed bodies before assigning quality."""
    if (not isinstance(out, dict) or out.get("error")
            or not isinstance(out.get("content"), str)
            or out.get("finish_reason") not in ("stop", "length")
            or type(out.get("prompt_tokens")) is not int or out["prompt_tokens"] <= 0
            or type(out.get("completion_tokens")) is not int or out["completion_tokens"] < 0):
        raise ValueError("invalid capacity completion: terminal response and token usage required")
    # Peak alone may be unavailable/invalid and is normalized to unknown below.
    raw = out.get("raw_timings") or {}
    json.dumps({**out, "peak_mem_gb": None,
                "raw_timings": {**raw, "peak_memory": None}}, allow_nan=False)


def run_ladder(driver, model: str, chars_per_token: float,
               idle_baseline_gb: float, model_pid: int | None,
               params: dict,
               grid=DEFAULT_GRID, memory_target_gb: float = MEMORY_TARGET_GB,
               sampler_factory=MemorySampler,
               request_timeout: float = 7200.0,
               on_start=None, on_record=None) -> list[dict]:
    """Measure MLX prefill peak plus sampled RSS/system memory at each requested rung.

    The target flag is descriptive and never stops the ladder. A failed request is
    unscored and terminates the ladder; HTTP failure alone does not identify an OOM.
    Bounded generation makes retrieval a co-signal, not depth certification.
    Callbacks expose rung starts and durable result writes to the CLI monitor.
    """
    records: list[dict] = []
    for ctx in grid:
        started = time.monotonic()
        if on_start:
            on_start(ctx)
        context, needles = build_context(ctx, chars_per_token)
        messages = [{"role": "user", "content": context + "\n\n" + make_question(needles)}]
        sampler = sampler_factory(pid=model_pid)
        try:
            with sampler:
                out = driver.complete(model, messages, params, timeout=request_timeout)
                validate_completion(out)
        except Exception as e:  # stop; transport failures are not quality scores
            sp = sampler.system_peak_gb
            rec = PerfRecord(ctx=ctx, peak_rss_gb=sampler.peak_rss_gb,
                             system_peak_gb=sp,
                             model_footprint_gb=round(sp - idle_baseline_gb, 2))
            row = {**asdict(rec), "schema_version": 2,
                   "memory_target_gb": memory_target_gb, "retrieval_acc": None,
                   "execution_status": "error", "within_memory_target": None,
                   "elapsed_s": time.monotonic() - started,
                   "draft": None, "acceptance": None,
                   "error": f"{type(e).__name__}: {str(e)[:160]}",
                   "error_kind": "timeout" if _is_timeout_error(e) else "request_error"}
            records.append(row)
            if on_record:
                on_record(row)
            print(_progress_line(row), flush=True)
            break
        system_peak = sampler.system_peak_gb
        mlx_peak = out.get("peak_mem_gb")
        target_flag = within_memory_target(mlx_peak, memory_target_gb)
        if target_flag is None:
            mlx_peak = None
        rec = PerfRecord(
            ctx=ctx,
            server_peak_gb=mlx_peak,                  # MLX prefill peak
            peak_rss_gb=sampler.peak_rss_gb,          # steady-state / resident (no spike)
            system_peak_gb=system_peak,               # coarse cross-check
            model_footprint_gb=round(system_peak - idle_baseline_gb, 2),  # coarse
            prefill_s=out.get("prefill_s"),
            prefill_tps=out.get("prefill_tps"),
            decode_tps=out.get("decode_tps"),
            prompt_tokens=out.get("prompt_tokens"),
        )
        draft = _draft_from_raw(out.get("raw_timings") or {})
        row = {**asdict(rec), "schema_version": 2,
               "memory_target_gb": memory_target_gb,
               "execution_status": "completed",
               "elapsed_s": time.monotonic() - started,
               "finish_reason": out.get("finish_reason"),
               "completion_tokens": out.get("completion_tokens"),
               "retrieval_acc": score(out.get("content", ""), needles),
               "within_memory_target": target_flag,
               "memory_telemetry_note": "Missing or invalid MLX peak" if target_flag is None else None,
               "draft": draft,
               "acceptance": _acceptance_from_draft(draft)}
        records.append(row)
        if on_record:
            on_record(row)
        print(_progress_line(row), flush=True)
    return records
