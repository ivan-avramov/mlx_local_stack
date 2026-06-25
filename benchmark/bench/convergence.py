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


def looks_like_loop(text, *, min_lines=20, max_repeat=20, min_unique_ratio=0.6) -> bool:
    """Heuristic: does a thinking trace look like a DEGENERATE repetition loop (worth a
    router-restart retry) rather than genuine long reasoning (which a restart won't help)?

    Looks at non-trivial lines (>20 chars). A loop = one line repeats >= max_repeat times AND
    the unique-line ratio is below min_unique_ratio (BOTH, so a long genuine trace that merely
    repeats a transitional phrase is not flagged). Needs >= min_lines lines to judge; short or
    empty traces are not loops. Calibrated on campaign data: gemma loops had max-repeat 34-78
    with ~44% unique; genuine Qwen traces had max-repeat <=23 with >=84% unique."""
    import collections
    lines = [ln.strip() for ln in (text or "").splitlines() if len(ln.strip()) > 20]
    if len(lines) < min_lines:
        return False
    max_rep = max(collections.Counter(lines).values())
    unique_ratio = len(set(lines)) / len(lines)
    return max_rep >= max_repeat and unique_ratio < min_unique_ratio


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
