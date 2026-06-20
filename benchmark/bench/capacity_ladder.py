"""Incremental-fill capacity + retrieval ladder. Grows the context in 32K steps,
captures the model process's peak RSS each step, scores multi-needle retrieval, and
stops at the 46GB RSS gate. One completion per rung (one prefill), so cost is bounded."""
from dataclasses import asdict
from .instrument import MemorySampler, PerfRecord
from .retrieval import build_context, make_question, score

DEFAULT_GRID = (160_000, 192_000, 224_000, 256_000)
GATE_GB = 46.0


def run_ladder(driver, model: str, chars_per_token: float,
               idle_baseline_gb: float, model_pid: int | None,
               grid=DEFAULT_GRID, gate_gb: float = GATE_GB,
               sampler_factory=MemorySampler, max_tokens: int = 256) -> list[dict]:
    """Run the capacity ladder.

    GATE METRIC = the model server process's peak RSS (model_pid), sampled live during
    each rung. fits = peak_rss_gb <= gate_gb -- i.e. "the model's actual resident memory
    is under the budget". system_peak_gb and model_footprint_gb (system-used minus the
    pre-preload idle_baseline_gb) are recorded as a secondary cross-check only.
    """
    records: list[dict] = []
    for ctx in grid:
        context, needles = build_context(ctx, chars_per_token)
        messages = [{"role": "user", "content": context + "\n\n" + make_question(needles)}]
        with sampler_factory(pid=model_pid) as sampler:
            out = driver.complete(model, messages,
                                  {"max_tokens": max_tokens, "temperature": 0.0})
        system_peak = sampler.system_peak_gb
        rec = PerfRecord(
            ctx=ctx,
            peak_rss_gb=sampler.peak_rss_gb,          # GATE METRIC: model process RSS
            model_footprint_gb=round(system_peak - idle_baseline_gb, 2),  # secondary
            system_peak_gb=system_peak,               # secondary
            # server_peak_gb is the server's lifetime high-water mark (never reset by the
            # server), recorded for reference only and NOT used for the gate.
            server_peak_gb=out.get("peak_mem_gb"),
            prefill_s=out.get("prefill_s"),
            prefill_tps=out.get("prefill_tps"),
            decode_tps=out.get("decode_tps"),
            prompt_tokens=out.get("prompt_tokens"),
        )
        fits = rec.peak_rss_gb <= gate_gb             # actual process RSS under budget
        row = {**asdict(rec),
               "retrieval_acc": score(out.get("content", ""), needles),
               "fits": fits}
        records.append(row)
        if not fits:
            break  # stop the ladder once the RSS gate is tripped
    return records
