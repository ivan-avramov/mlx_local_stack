"""The thinking budget we DECLARE is not always the one in FORCE — convergence must check the
resolved one.

MEASURED 2026-08-14, and it invalidated a published number. mlx-vlm's
``_apply_generation_budget`` (server/generation.py) does two things, the second of them SILENTLY:

    effective    = min(max_tokens, context_limit - prompt_tokens)   # logs a WARNING
    headroom_cap = int(effective * THINKING_BUDGET_CLAMP_RATIO)     # 0.8
    thinking_budget = min(thinking_budget, headroom_cap)            # logs NOTHING

The IFEval runs requested ``max_tokens: 102400`` / ``thinking_budget: 81920`` against
``max_kv_cache_size: 65536``. So the budget actually in force was ``int((65536 - prompt) * 0.8)``
≈ 52,390 — NOT 81,920. ``ThinkingBudgetCriteria`` then force-injected ``\\n</think>`` at that cap,
the model wrote its answer, and ``finish_reason`` came back ``"stop"``.

``is_converged`` compared ``completion_tokens`` against the REQUESTED 81,920, so it returned True.
That is exactly the FALSE PASS the convergence rule exists to catch (AGENTS.md: "finish=='stop'
alone is a FALSE PASS — budget-hits force an EOS"). It slipped through because the clamp is
invisible to the harness.

Consequences that these tests pin:
  - Ornith-1.0-35B-mlx-uniform-4bit / ifeval: conv 99.3% published -> 94.6% true (25 rows flip).
  - Qwen3.6-27B-Opus-Distill-OptiQ-4bit / ifeval: 98.6% -> 93.2% (8 rows flip).
  - Of 40 rows flagged as "self-terminating degenerate loops", exactly ONE (Ornith id 3748) was
    genuinely under the resolved budget. The rest are external truncations.

The numbers below are REAL rows from those runs, so this file doubles as a regression corpus: if the
arithmetic ever drifts from the fork's, these fail.
"""
import pytest

import bench.convergence as C


# ---------------------------------------------------------------- the resolved budget itself

def test_clamp_ratio_mirrors_the_fork():
    """If the fork changes its ratio, this constant must change with it — and the mirror is the
    whole reason this is a named constant rather than a magic 0.8."""
    assert C.THINKING_BUDGET_CLAMP_RATIO == 0.8


@pytest.mark.parametrize("prompt,expected", [
    (48, 52390),    # ids 3084 / 1591 / 279-class rows
    (42, 52395),    # id 2849 — the row the M1 ruling turned on
    (224, 52249),   # id 1999 — the longest prompt among the loops
    (87, 52359),    # id 3188
])
def test_resolved_budget_reproduces_the_observed_ifeval_stop_points(prompt, expected):
    """int((65536 - prompt) * 0.8). Pinned against rows whose completions land just above these."""
    assert C.resolved_thinking_budget(
        {"prompt_tokens": prompt, "thinking_budget": 81920},
        context_limit=65536, max_tokens=102400) == expected


def test_no_clamp_when_max_tokens_fits_the_context():
    """The evalplus / math500 / aime rows ran at max_kv_cache_size 262144, where 102400 fits with
    room to spare — so their budget was the declared 81920 and their published convergence STANDS.
    This is the guard that the fix does not retroactively 'correct' sound rows."""
    assert C.resolved_thinking_budget(
        {"prompt_tokens": 150, "thinking_budget": 81920},
        context_limit=262144, max_tokens=102400) == 81920


def test_resolved_budget_never_exceeds_the_requested_one():
    """The clamp only ever SHRINKS. A generous context must not inflate a small declared budget."""
    assert C.resolved_thinking_budget(
        {"prompt_tokens": 10, "thinking_budget": 4096},
        context_limit=262144, max_tokens=102400) == 4096


def test_resolved_budget_is_none_without_the_config():
    """Historical rows carry no context_limit. Returning None (rather than guessing) is what keeps
    is_converged's old behaviour for rows we cannot re-resolve."""
    assert C.resolved_thinking_budget({"prompt_tokens": 48, "thinking_budget": 81920}) is None


# ---------------------------------------------------------------- is_converged uses it

def test_row_carrying_a_resolved_budget_is_judged_against_it():
    """id 279: completion 52409 vs declared 81920 (looks converged) vs resolved 52390 (a HIT)."""
    row = {"finish_reason": "stop", "completion_tokens": 52409,
           "thinking_budget": 81920, "resolved_thinking_budget": 52390}
    assert C.is_converged(row) is False, (
        "a budget hit against the RESOLVED budget must be non-converged — this is the false pass")


def test_the_m1_ruling_row_is_a_budget_hit():
    """id 2849 was ruled 'converged as determined by the MODEL' at '64% of budget'. Against the
    budget actually in force it is 100.2%."""
    row = {"finish_reason": "stop", "completion_tokens": 52503,
           "thinking_budget": 81920, "resolved_thinking_budget": 52395}
    assert C.is_converged(row) is False


def test_the_one_genuinely_self_terminating_loop_still_converges():
    """Ornith id 3748: 8,228 tokens, far under the resolved 52,390. The ONLY one of the 40 flagged
    loops that matches O11's description. It must NOT be swept up by the fix."""
    row = {"finish_reason": "stop", "completion_tokens": 8228,
           "thinking_budget": 81920, "resolved_thinking_budget": 52390}
    assert C.is_converged(row) is True


def test_declared_budget_still_used_when_no_resolved_budget_present():
    """Backwards compatibility: every historical row lacks the field, and the 262144-config rows
    are correct as-is. Absent the field, behaviour is unchanged."""
    assert C.is_converged({"finish_reason": "stop", "completion_tokens": 3000,
                           "thinking_budget": 16384}) is True
    assert C.is_converged({"finish_reason": "stop", "completion_tokens": 17000,
                           "thinking_budget": 16384}) is False


def test_max_tokens_truncation_still_dominates():
    """fr=='length' is non-converged regardless of any budget — the six 65537-total rows."""
    row = {"finish_reason": "length", "completion_tokens": 65489,
           "thinking_budget": 81920, "resolved_thinking_budget": 52390}
    assert C.is_converged(row) is False


# ---------------------------------------------------------------- backfilling historical rows

def test_backfill_annotates_rows_from_a_run_config():
    """Historical rows are re-resolvable because they carry prompt_tokens and the manifest carries
    max_kv_cache_size + max_tokens. Zero worker time — this is a RE-GRADE, not a re-run."""
    rows = [
        {"id": "a", "prompt_tokens": 48, "completion_tokens": 52409,
         "finish_reason": "stop", "thinking_budget": 81920},
        {"id": "b", "prompt_tokens": 42, "completion_tokens": 8228,
         "finish_reason": "stop", "thinking_budget": 81920},
    ]
    out = C.backfill_resolved_budget(rows, context_limit=65536, max_tokens=102400)
    assert out[0]["resolved_thinking_budget"] == 52390
    assert out[1]["resolved_thinking_budget"] == 52395
    assert C.is_converged(out[0]) is False     # was a false pass
    assert C.is_converged(out[1]) is True      # genuinely self-terminated


def test_backfill_is_a_noop_when_no_clamp_would_fire():
    """A 262144-context run must come out byte-identical in its convergence verdicts."""
    rows = [{"id": "a", "prompt_tokens": 150, "completion_tokens": 60000,
             "finish_reason": "stop", "thinking_budget": 81920}]
    out = C.backfill_resolved_budget(rows, context_limit=262144, max_tokens=102400)
    assert out[0]["resolved_thinking_budget"] == 81920
    assert C.is_converged(out[0]) is True


def test_audit_reports_the_corrected_rate():
    """The end-to-end shape of the IFEval correction: 3 rows, one clamped hit."""
    rows = C.backfill_resolved_budget([
        {"id": 1, "prompt_tokens": 48, "completion_tokens": 2400,
         "finish_reason": "stop", "thinking_budget": 81920},
        {"id": 2, "prompt_tokens": 48, "completion_tokens": 52409,
         "finish_reason": "stop", "thinking_budget": 81920},
        {"id": 3, "prompt_tokens": 48, "completion_tokens": 1800,
         "finish_reason": "stop", "thinking_budget": 81920},
    ], context_limit=65536, max_tokens=102400)
    a = C.audit(rows)
    assert a["n_converged"] == 2
    assert a["loop_ids"] == [2]
    assert a["convergence_rate"] == pytest.approx(2 / 3)


# ---------------------------------------------------------------- wired into the grading seam

def test_grade_rows_are_annotated_from_the_manifest(tmp_path, monkeypatch):
    """`grade._rows` is the ONE seam every grader loads through, so annotating there makes conv%,
    nonconv_kinds and acc_strict correct everywhere at once — with no per-grader change.

    Without this, a re-grade of the IFEval runs would reproduce the false pass: the rows carry the
    DECLARED 81920 and nothing else tells the grader the server clamped it.
    """
    import json as _json
    from bench import generate, grade

    mdir = tmp_path / "M"
    mdir.mkdir()
    (mdir / "ifeval.jsonl").write_text("\n".join(_json.dumps(r) for r in [
        {"id": 1, "sample": 0, "prompt_tokens": 48, "completion_tokens": 52409,
         "finish_reason": "stop", "thinking_budget": 81920},
        {"id": 2, "sample": 0, "prompt_tokens": 48, "completion_tokens": 2400,
         "finish_reason": "stop", "thinking_budget": 81920},
    ]))
    (mdir / "ifeval.manifest.json").write_text(_json.dumps({
        "kv": {"max_kv_cache_size": 65536},
        "sampling": {"max_tokens": 102400, "thinking_budget": 81920},
    }))
    monkeypatch.setattr(generate, "results_root", lambda: tmp_path)

    rows = grade._rows("M", "ifeval")
    assert rows[0]["resolved_thinking_budget"] == 52390, "clamp not applied from the manifest"
    assert C.is_converged(rows[0]) is False, "the clamped budget hit must not read as converged"
    assert C.is_converged(rows[1]) is True


def test_grade_rows_unannotated_when_manifest_shows_no_clamp(tmp_path, monkeypatch):
    """262144-context runs: the resolved budget equals the declared one, so verdicts are unchanged
    and every already-published row from those runs stays comparable."""
    import json as _json
    from bench import generate, grade

    mdir = tmp_path / "M"
    mdir.mkdir()
    (mdir / "mbppplus.jsonl").write_text(_json.dumps(
        {"id": 1, "sample": 0, "prompt_tokens": 150, "completion_tokens": 60000,
         "finish_reason": "stop", "thinking_budget": 81920}))
    (mdir / "mbppplus.manifest.json").write_text(_json.dumps({
        "kv": {"max_kv_cache_size": 262144},
        "sampling": {"max_tokens": 102400, "thinking_budget": 81920},
    }))
    monkeypatch.setattr(generate, "results_root", lambda: tmp_path)

    rows = grade._rows("M", "mbppplus")
    assert rows[0]["resolved_thinking_budget"] == 81920
    assert C.is_converged(rows[0]) is True


def test_grade_rows_survive_a_missing_manifest(tmp_path, monkeypatch):
    """Old runs predate manifests entirely. Grading must degrade gracefully, never crash the batch
    (AGENTS.md: bench tooling graceful-degrades)."""
    import json as _json
    from bench import generate, grade

    mdir = tmp_path / "M"
    mdir.mkdir()
    (mdir / "aime.jsonl").write_text(_json.dumps(
        {"id": 1, "sample": 0, "completion_tokens": 500, "finish_reason": "stop",
         "thinking_budget": 16384}))
    monkeypatch.setattr(generate, "results_root", lambda: tmp_path)

    rows = grade._rows("M", "aime")
    assert "resolved_thinking_budget" not in rows[0]
    assert C.is_converged(rows[0]) is True
