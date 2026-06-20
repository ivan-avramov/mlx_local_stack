"""Aggregate capacity-ladder records into one comparable scorecard (axes 1 + 2a)."""

GATE_GB = 46.0
RETRIEVAL_THRESHOLD = 0.85


def capacity_retrieval_scorecard(model: str, records: list[dict],
                                 gate_gb: float = GATE_GB,
                                 retrieval_threshold: float = RETRIEVAL_THRESHOLD) -> dict:
    fitting = [r for r in records if r.get("fits")]
    max_fitting = max((r["ctx"] for r in fitting), default=None)
    passing = [r["ctx"] for r in fitting if r.get("retrieval_acc", 0) >= retrieval_threshold]
    return {
        "model": model,
        "axis": "capacity_retrieval",
        "gate_metric": "mlx_peak_gb (mx.get_peak_memory, the prefill spike)",
        "gate_gb": gate_gb,
        "retrieval_threshold": retrieval_threshold,
        "records": records,
        "max_fitting_ctx": max_fitting,
        "capacity_gate_pass": any(r["ctx"] >= 256_000 for r in fitting),
        "retrieval_effective_ctx": max(passing, default=None),
    }
