"""Tests for bench.convergence — the guard that a thinking-budget hit (which forces an
end-of-thinking token, so finish_reason=='stop') can NEVER be silently counted as a
converged result. converged = (finish=='stop' AND completion_tokens < thinking_budget).
A run containing any non-converged (looped/truncated) item is flagged INVALID rather than
having those items scored as zeros.
"""
import bench.convergence as C


def test_converged_under_budget():
    assert C.is_converged({"finish_reason": "stop", "completion_tokens": 3000,
                           "thinking_budget": 16384}) is True


def test_budget_hit_is_not_converged_even_if_stop():
    # finish=='stop' but comp_tok >= budget -> the budget forced the stop. NOT converged.
    assert C.is_converged({"finish_reason": "stop", "completion_tokens": 16725,
                           "thinking_budget": 16384}) is False


def test_length_truncation_not_converged():
    assert C.is_converged({"finish_reason": "length", "completion_tokens": 32768,
                           "thinking_budget": 16384}) is False


def test_no_thinking_budget_uses_finish_only():
    assert C.is_converged({"finish_reason": "stop", "completion_tokens": 500,
                           "thinking_budget": None}) is True


def test_error_row_is_none():
    assert C.is_converged({"error": "boom"}) is None
    assert C.is_converged({"finish_reason": "stop", "completion_tokens": None,
                           "thinking_budget": 16384}) is None


def test_audit_flags_loops_invalid():
    rows = [
        {"id": "a", "finish_reason": "stop", "completion_tokens": 3000, "thinking_budget": 16384},
        {"id": "b", "finish_reason": "stop", "completion_tokens": 17000, "thinking_budget": 16384},  # loop
        {"id": "c", "finish_reason": "length", "completion_tokens": 32768, "thinking_budget": 16384}, # trunc
        {"id": "d", "error": "net"},                                                                  # skipped
    ]
    a = C.audit(rows)
    assert a["n_generated"] == 3              # excludes the error row
    assert a["n_converged"] == 1
    assert sorted(a["loop_ids"]) == ["b", "c"]
    assert a["valid"] is False                # any loop -> invalid run
    assert abs(a["convergence_rate"] - 1 / 3) < 1e-9


def test_looks_like_loop_flags_degenerate_repetition():
    # Degenerate verbatim loop (gemma-style: high max-repeat AND low unique ratio).
    loop = "\n".join(["this is the same repeated reasoning line, over and over again"] * 40)
    assert C.looks_like_loop(loop) is True


def test_looks_like_loop_passes_genuine_long_reasoning():
    # Genuine long reasoning: many DISTINCT lines (Qwen-style: high unique, low max-repeat).
    genuine = "\n".join(f"distinct reasoning step number {i}, with its own unique content here"
                        for i in range(60))
    assert C.looks_like_loop(genuine) is False


def test_looks_like_loop_needs_enough_lines_and_handles_empty():
    # A short trace can't be judged a loop; empty/None is not a loop.
    assert C.looks_like_loop("") is False
    assert C.looks_like_loop(None) is False
    assert C.looks_like_loop("\n".join(["repeated line that is long enough here"] * 5)) is False


def test_looks_like_loop_mild_repetition_is_not_a_loop():
    # Genuine trace with mild repetition (maxrep ~10 but ~90% unique) must NOT be flagged
    # (the campaign's genuine Qwen traces had maxrep up to ~23 with >84% unique).
    lines = [f"unique reasoning content for step {i} goes right here ok" for i in range(90)]
    lines += ["a recurring transitional phrase that shows up sometimes"] * 10
    assert C.looks_like_loop("\n".join(lines)) is False


def test_audit_all_converged_is_valid():
    rows = [
        {"id": "a", "finish_reason": "stop", "completion_tokens": 3000, "thinking_budget": 16384},
        {"id": "b", "finish_reason": "stop", "completion_tokens": 500, "thinking_budget": None},
    ]
    a = C.audit(rows)
    assert a["valid"] is True
    assert a["loop_ids"] == []
    assert a["convergence_rate"] == 1.0
