"""Convergence guard.

A thinking model that hits its ``thinking_budget`` is FORCED to emit an end-of-thinking
token and answer, so ``finish_reason`` becomes ``"stop"`` — a FALSE pass. Likewise a
``max_tokens`` hit gives ``finish_reason=="length"``. Neither is convergence.

Real convergence = the model decided to stop on its own, strictly under the budget:
    converged = (finish_reason == "stop") AND (completion_tokens < thinking_budget)

A benchmark run containing ANY non-converged (looped / truncated) item is flagged INVALID
so those items are never silently scored as zeros — a loop is a failure to INVESTIGATE
(stale router? quant fragility?), not a data point. See AGENTS.md measurement discipline.
"""


def is_converged(row: dict):
    """True/False for a generated item; None when the row isn't a usable generation
    (error, or missing completion_tokens)."""
    if row.get("error"):
        return None
    ct = row.get("completion_tokens")
    if ct is None:
        return None
    fr = row.get("finish_reason")
    if fr == "length":
        return False                      # max_tokens truncation
    tb = row.get("thinking_budget")
    if tb is not None and ct >= tb:
        return False                      # thinking-budget hit forced the stop
    return fr == "stop"


def audit(rows) -> dict:
    """Summarize convergence over a list of generation rows.

    Returns n_generated (non-error rows), n_converged, loop_ids (non-converged ids),
    convergence_rate, and valid (True iff every generated item converged)."""
    generated = [r for r in rows if is_converged(r) is not None]
    loops = [r for r in generated if not is_converged(r)]
    loop_ids = [r.get("id") for r in loops]
    n = len(generated)
    return {
        "n_generated": n,
        "n_converged": n - len(loops),
        "loop_ids": loop_ids,
        "convergence_rate": (n - len(loops)) / n if n else None,
        "valid": len(loops) == 0,
    }
