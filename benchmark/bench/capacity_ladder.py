"""Incremental-fill capacity + retrieval ladder. Grows the context in 32K steps,
captures peak memory each step, scores multi-needle retrieval, and stops at the
46GB footprint gate. One completion per rung (one prefill), so cost is bounded."""
from dataclasses import asdict
from .instrument import MemorySampler, PerfRecord
from .retrieval import build_context, make_question, score

DEFAULT_GRID = (160_000, 192_000, 224_000, 256_000)
GATE_GB = 46.0


def run_ladder(driver, model: str, chars_per_token: float,
               grid=DEFAULT_GRID, gate_gb: float = GATE_GB,
               sampler_factory=MemorySampler, max_tokens: int = 256) -> list[dict]:
    records: list[dict] = []
    for ctx in grid:
        context, needles = build_context(ctx, chars_per_token)
        messages = [{"role": "user", "content": context + "\n\n" + make_question(needles)}]
        with sampler_factory() as sampler:
            out = driver.complete(model, messages,
                                  {"max_tokens": max_tokens, "temperature": 0.0})
        rec = PerfRecord(
            ctx=ctx,
            model_footprint_gb=sampler.model_footprint_gb,
            system_peak_gb=sampler.system_peak_gb,
            peak_rss_gb=sampler.peak_rss_gb,
            server_peak_gb=out.get("peak_mem_gb"),
            prefill_s=out.get("prefill_s"),
            prefill_tps=out.get("prefill_tps"),
            decode_tps=out.get("decode_tps"),
            prompt_tokens=out.get("prompt_tokens"),
        )
        fits = rec.model_footprint_gb <= gate_gb
        row = {**asdict(rec),
               "retrieval_acc": score(out.get("content", ""), needles),
               "fits": fits}
        records.append(row)
        if not fits:
            break  # stop the ladder once the footprint gate is tripped
    return records
