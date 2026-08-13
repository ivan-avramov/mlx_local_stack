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


# ------------------------------------------------- run_convergence sampling provenance
# run_convergence is the FAST mechanism the temperature-ladder recipe and the campaign-v3 Tier-0
# grid both drive. Two defects would have mis-measured every config in that grid.
def test_run_convergence_uses_the_deployed_profile(monkeypatch):
    """It called params_for(model) with NO profile, so it silently got the DEFAULT 'production'
    table — which AGENTS.md records as DRIFTED from what we ship (QWEN production = temp 0.7 /
    min_p 0.03 / presence_penalty 0.3). A nonzero presence_penalty also DISABLES suffix decoding,
    so the whole grid would have measured a different serving path from the one we deploy."""
    from bench import run_convergence as RC
    import inspect
    src = inspect.getsource(RC.main)
    assert "params_for(args.model)" not in src, (
        "params_for called without a profile -> defaults to the drifted 'production' table")
    assert 'params_for(args.model, args.sampling_profile' in src or \
           'params_for(args.model, "deployed"' in src or \
           "params_for(args.model, DEPLOYED" in src, \
        "the deployed profile (registry generation_defaults) must be used for new axes"


def test_run_convergence_rejects_an_unknown_set_key():
    """`--set` did `params[k] = v` with no validation, so `--set min-p=0.02` (hyphen) or
    `--set minp=0.02` silently added a junk key and left min_p at its default — the run then looks
    entirely healthy. Unknown keys must fail LOUD."""
    from bench import run_convergence as RC
    assert hasattr(RC, "_apply_set"), "--set handling should be a testable function"
    base = {"temperature": 0.4, "min_p": 0.0, "max_tokens": 100}
    out = RC._apply_set(dict(base), ["min_p=0.02"])
    assert out["min_p"] == 0.02, "a valid key must be applied and numerically cast"
    import pytest
    with pytest.raises(Exception) as e:
        RC._apply_set(dict(base), ["min-p=0.02"])
    assert "min-p" in str(e.value), "the offending key must be named in the error"


def test_run_convergence_finds_the_registry_regardless_of_cwd(monkeypatch, tmp_path):
    """The `deployed` profile reads main_models.yaml, but run_convergence's documented invocation
    is `cd benchmark && ...`, so a CWD-relative registry path cannot be found. Making `deployed`
    the default therefore broke the tool from its own documented working directory. The registry
    location must not depend on CWD."""
    from bench import run_convergence as RC
    assert hasattr(RC, "_registry_path"), "registry path must be resolved, not left CWD-relative"
    monkeypatch.chdir(tmp_path)                       # anywhere at all
    p = RC._registry_path()
    import os
    assert os.path.isabs(p), f"registry path must be absolute, got {p!r}"
    assert os.path.exists(p), f"resolved registry does not exist: {p!r}"
