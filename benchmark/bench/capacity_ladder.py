"""Incremental-fill capacity + retrieval ladder. Grows the context in 32K steps,
captures BOTH the model's MLX peak memory (the prefill SPIKE = OOM trigger, the gate)
and its steady-state RSS (resident cost), scores multi-needle retrieval, and stops at
the 46GB peak gate. One completion per rung (one prefill), so cost is bounded."""
from dataclasses import asdict
from .instrument import MemorySampler, PerfRecord
from .retrieval import build_context, make_question, score

DEFAULT_GRID = (160_000, 192_000, 224_000, 256_000)
GATE_GB = 46.0


def run_ladder(driver, model: str, chars_per_token: float,
               idle_baseline_gb: float, model_pid: int | None,
               params: dict,
               grid=DEFAULT_GRID, gate_gb: float = GATE_GB,
               sampler_factory=MemorySampler) -> list[dict]:
    """Run the capacity ladder.

    GATE METRIC = the model's MLX peak memory (mx.get_peak_memory, reported by the
    server as peak_mem_gb -> recorded as server_peak_gb). This is the prefill SPIKE,
    which is what actually triggers OOM. fits = server_peak_gb <= gate_gb.

    Reported alongside (NOT the gate): peak_rss_gb = the model process's steady-state
    resident memory (~the decode-time cost; psutil RSS under-counts the spike on Apple
    Silicon, hence it is not the gate). system_peak_gb / model_footprint_gb (system-used
    minus the pre-preload idle_baseline_gb) are coarse cross-checks.

    A hard OOM -- the request 500s / disconnects before returning -- is caught, recorded
    as a non-fitting rung with an `error`, and stops the ladder (so the gate registers
    "does not fit here" instead of crashing the run).

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
                out = driver.complete(model, messages, params)
        except Exception as e:  # hard OOM / server error at this context -> does not fit
            sp = sampler.system_peak_gb
            rec = PerfRecord(ctx=ctx, peak_rss_gb=sampler.peak_rss_gb,
                             system_peak_gb=sp,
                             model_footprint_gb=round(sp - idle_baseline_gb, 2))
            records.append({**asdict(rec), "retrieval_acc": 0.0, "fits": False,
                            "error": f"{type(e).__name__}: {str(e)[:160]}"})
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
        row = {**asdict(rec),
               "retrieval_acc": score(out.get("content", ""), needles),
               "fits": fits}
        records.append(row)
        if not fits:
            break  # stop the ladder once the peak gate is tripped
    return records
