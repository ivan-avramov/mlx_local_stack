"""Capacity summaries: execution, descriptive memory target and retrieval co-score."""
import math

MEMORY_TARGET_GB = 48.0
RETRIEVAL_THRESHOLD = 0.85


def within_memory_target(peak, target=MEMORY_TARGET_GB):
    """Unknown/invalid telemetry is not evidence of a memory pass or failure."""
    if type(peak) not in (int, float) or not math.isfinite(peak) or peak <= 0:
        return None
    return peak <= target


def completed(record):
    # Legacy rows have no status; their error field distinguishes request failures.
    return not record.get("error") and record.get("execution_status", "completed") == "completed"


def capacity_retrieval_scorecard(model: str, records: list[dict],
                                 memory_target_gb: float = MEMORY_TARGET_GB,
                                 retrieval_threshold: float = RETRIEVAL_THRESHOLD) -> dict:
    successful = [r for r in records if completed(r)]
    within = [r for r in successful
              if within_memory_target(r.get("server_peak_gb"), memory_target_gb) is True]
    passing = [r for r in successful if r.get("retrieval_acc") is not None
               and r["retrieval_acc"] >= retrieval_threshold]
    return {
        "schema_version": 2,
        "model": model,
        "axis": "capacity_retrieval",
        "memory_metric": "mlx_peak_gb (mx.get_peak_memory, the prefill spike)",
        "memory_target_gb": memory_target_gb,
        "memory_policy": "descriptive guideline; no numeric early stopping or eligibility verdict",
        "execution_status": ("empty" if not records else
                             "completed" if len(successful) == len(records) else "error"),
        "stability_note": "Request completion alone does not establish sustained memory-pressure stability.",
        "retrieval_threshold": retrieval_threshold,
        "retrieval_scope": "Bounded-generation co-score; dedicated retrieval-depth curves are authoritative.",
        "records": records,
        "max_completed_ctx": max((r["ctx"] for r in successful), default=None),
        "max_within_memory_target_ctx": max((r["ctx"] for r in within), default=None),
        "retrieval_coscore_max_passing_ctx": max((r["ctx"] for r in passing), default=None),
    }
