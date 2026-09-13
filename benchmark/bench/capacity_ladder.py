"""Incremental-fill capacity + retrieval ladder. Grows the context in 32K steps,
captures BOTH the model's MLX peak memory (the prefill SPIKE = OOM trigger, the gate)
and its steady-state RSS (resident cost), scores multi-needle retrieval, and stops at
the 46GB peak gate. One completion per rung (one prefill), so cost is bounded."""
from dataclasses import asdict
from .instrument import MemorySampler, PerfRecord
from .retrieval import build_context, make_question, score

DEFAULT_GRID = (160_000, 192_000, 224_000, 256_000)
GATE_GB = 46.0


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
            f"fits={row.get('fits')} prefill_s={row.get('prefill_s')} "
            f"error={row.get('error')}")


def run_ladder(driver, model: str, chars_per_token: float,
               idle_baseline_gb: float, model_pid: int | None,
               params: dict,
               grid=DEFAULT_GRID, gate_gb: float = GATE_GB,
               sampler_factory=MemorySampler,
               request_timeout: float = 7200.0) -> list[dict]:
    """Run the capacity ladder.

    GATE METRIC = the model's MLX peak memory (mx.get_peak_memory, reported by the
    server as peak_mem_gb -> recorded as server_peak_gb). This is the prefill SPIKE,
    which is what actually triggers OOM. fits = server_peak_gb <= gate_gb.

    Reported alongside (NOT the gate): peak_rss_gb = the model process's steady-state
    resident memory (~the decode-time cost; psutil RSS under-counts the spike on Apple
    Silicon, hence it is not the gate). system_peak_gb / model_footprint_gb (system-used
    minus the pre-preload idle_baseline_gb) are coarse cross-checks.

    A hard OOM -- the request 500s / disconnects before returning -- is caught, recorded
    as a non-fitting rung with an `error` + `error_kind` ("timeout" when the exception is
    a client-side request timeout, else "oom_or_disconnect"), and stops the ladder (so the
    gate registers "does not fit here" instead of crashing the run).

    `params` carries the production sampling params plus bounded generation limits
    (max_tokens=256, thinking_budget=256). The gate is the MLX-peak (prefill spike),
    which is independent of decode length, so generation is intentionally bounded here;
    `retrieval_acc` is a ROUGH co-signal only (thinking-bounded) — authoritative
    retrieval is a dedicated probe.
    """
    records: list[dict] = []
    for ctx in grid:
        context, needles = build_context(ctx, chars_per_token)
        messages = [{"role": "user", "content": context + "\n\n" + make_question(needles)}]
        sampler = sampler_factory(pid=model_pid)
        try:
            with sampler:
                out = driver.complete(model, messages, params, timeout=request_timeout)
        except Exception as e:  # hard OOM / server error at this context -> does not fit
            sp = sampler.system_peak_gb
            rec = PerfRecord(ctx=ctx, peak_rss_gb=sampler.peak_rss_gb,
                             system_peak_gb=sp,
                             model_footprint_gb=round(sp - idle_baseline_gb, 2))
            row = {**asdict(rec), "retrieval_acc": 0.0, "fits": False,
                   "draft": None, "acceptance": None,
                   "error": f"{type(e).__name__}: {str(e)[:160]}",
                   "error_kind": "timeout" if _is_timeout_error(e) else "oom_or_disconnect"}
            records.append(row)
            print(_progress_line(row), flush=True)
            break
        system_peak = sampler.system_peak_gb
        mlx_peak = out.get("peak_mem_gb")
        rec = PerfRecord(
            ctx=ctx,
            server_peak_gb=mlx_peak,                  # GATE METRIC: MLX peak (the spike)
            peak_rss_gb=sampler.peak_rss_gb,          # steady-state / resident (no spike)
            system_peak_gb=system_peak,               # coarse cross-check
            model_footprint_gb=round(system_peak - idle_baseline_gb, 2),  # coarse
            prefill_s=out.get("prefill_s"),
            prefill_tps=out.get("prefill_tps"),
            decode_tps=out.get("decode_tps"),
            prompt_tokens=out.get("prompt_tokens"),
        )
        fits = (mlx_peak is not None) and (mlx_peak <= gate_gb)   # spike under budget
        draft = _draft_from_raw(out.get("raw_timings") or {})
        row = {**asdict(rec),
               "retrieval_acc": score(out.get("content", ""), needles),
               "fits": fits, "draft": draft,
               "acceptance": _acceptance_from_draft(draft)}
        records.append(row)
        print(_progress_line(row), flush=True)
        if not fits:
            break  # stop the ladder once the peak gate is tripped
    return records
