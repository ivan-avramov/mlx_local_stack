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


# Mirrors mlx-vlm's server-side clamp: `THINKING_BUDGET_CLAMP_RATIO` in
# `mlx_vlm/server/generation.py`. The server caps thinking_budget to this share of the effective
# generation budget so a forced `</think>` still leaves room for a visible answer. Mirrored here
# because the server does NOT log the capped value (its sibling max_tokens clamp does), so the
# harness has no other way to know the budget that was actually in force. Keep the two in step.
THINKING_BUDGET_CLAMP_RATIO = 0.8


def resolved_thinking_budget(row: dict, *, context_limit=None, max_tokens=None):
    """The thinking budget ACTUALLY IN FORCE for a row, or None if it can't be determined.

    The server resolves a request's budget in two steps (both in `_apply_generation_budget`):

        effective       = min(max_tokens, context_limit - prompt_tokens)
        thinking_budget = min(thinking_budget, int(effective * THINKING_BUDGET_CLAMP_RATIO))

    The first step logs a warning; the SECOND IS SILENT. So a run that declares
    `thinking_budget: 81920` against `max_kv_cache_size: 65536` actually ran at ~52,390, and
    comparing completions to 81,920 scores every forced-close as CONVERGED — the exact false pass
    the convergence rule exists to prevent (AGENTS.md).

    Returns None when `context_limit`/`max_tokens` are unknown, so callers keep the declared-budget
    behaviour rather than guessing. That matters: rows from 262144-context runs are already correct
    and must not be "corrected".
    """
    tb = row.get("thinking_budget")
    if tb is None or context_limit is None or max_tokens is None:
        return None
    prompt = row.get("prompt_tokens")
    if prompt is None:
        return None
    effective = min(int(max_tokens), int(context_limit) - int(prompt))
    if effective <= 0:
        return None
    return min(int(tb), max(1, int(effective * THINKING_BUDGET_CLAMP_RATIO)))


def backfill_resolved_budget(rows, *, context_limit, max_tokens):
    """Annotate rows in place with `resolved_thinking_budget` from a run's config.

    Historical rows are re-resolvable — they carry `prompt_tokens`, and the manifest carries
    `kv.max_kv_cache_size` and `sampling.max_tokens` — so correcting convergence for an existing
    run is a RE-GRADE at zero worker time, not a re-run (`docs/regrade-vs-rerun-guideline.md`).
    """
    for row in rows:
        rb = resolved_thinking_budget(row, context_limit=context_limit, max_tokens=max_tokens)
        if rb is not None:
            row["resolved_thinking_budget"] = rb
    return rows


def effective_thinking_budget(row: dict):
    """The budget `is_converged` should judge this row against: the resolved one when known,
    otherwise the declared one."""
    rb = row.get("resolved_thinking_budget")
    return rb if rb is not None else row.get("thinking_budget")


def is_converged(row: dict):
    """True/False for a generated item; None when the row isn't a usable generation
    (error, or missing completion_tokens).

    Judged against `effective_thinking_budget` — the RESOLVED budget when the row carries one,
    because the server silently clamps the declared budget and a clamped forced-close otherwise
    reads as a clean `finish_reason=="stop"`.
    """
    if row.get("error"):
        return None
    ct = row.get("completion_tokens")
    if ct is None:
        return None
    fr = row.get("finish_reason")
    if fr == "length":
        return False                      # max_tokens truncation
    tb = effective_thinking_budget(row)
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
