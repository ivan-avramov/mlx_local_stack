import bench.instrument as I

def test_sampler_tracks_absolute_peak(monkeypatch):
    # Sampler now tracks absolute peaks only; footprint-vs-idle is the caller's job.
    seq = iter([10.0, 10.0, 55.0, 30.0])  # seed value then poll values; peak=55
    monkeypatch.setattr(I, "system_used_gb", lambda: next(seq))
    s = I.MemorySampler(interval=0.001)
    with s:
        import time; time.sleep(0.02)
    assert s.system_peak_gb == 55.0

def test_perfrecord_defaults():
    r = I.PerfRecord(ctx=256000)
    assert r.ctx == 256000 and r.bottleneck == "unknown"

def test_find_model_server_pid_picks_highest_rss(monkeypatch):
    import psutil
    class _M:
        def __init__(self, rss): self.rss = rss
    class _P:
        def __init__(self, pid, cmd, rss):
            self.info = {"pid": pid, "cmdline": cmd, "memory_info": _M(rss)}
    procs = [_P(1, ["python", "other"], 10),
             _P(2, ["python", "mlx_vlm.server", "--model", "x"], 5_000_000_000),
             _P(3, ["python", "mlx_vlm.server", "--model", "y"], 20_000_000_000)]
    monkeypatch.setattr(psutil, "process_iter", lambda attrs=None: iter(procs))
    assert I.find_model_server_pid() == 3   # highest-RSS match wins
    monkeypatch.setattr(psutil, "process_iter",
                        lambda attrs=None: iter([_P(1, ["python", "other"], 10)]))
    assert I.find_model_server_pid() is None  # no match


# ------------------------------------------------------------------ EOS'd degenerate loops
# Found on the IFEval run, 2026-08-13: one Ornith row generated 52,503 tokens of a two-line
# alternating loop (unique_line_ratio 0.0093, max_line_repeat 2071, ngram8_unique 0.0123) and was
# scored `converged: True, nonconv_kind: None` — because it EOS'd under the 81,920 budget. The
# repetition detector already existed and was correct; `classify` just never reached it, since it
# early-returns None for anything `convergence.is_converged` accepts. That single row was 4% of
# rows but 32% of wall-clock and 45% of tokens.
def test_a_self_terminating_repetition_loop_is_FLAGGED_even_though_it_converged():
    """The row satisfies the ratified convergence formula, so conv% must keep counting it as
    converged — but the loop must not be invisible."""
    import bench.traces as T
    row = {"finish_reason": "stop", "completion_tokens": 52503, "thinking_budget": 81920,
           "reasoning_stats": {"chars": 171994, "lines": 4179, "unique_line_ratio": 0.0093,
                               "max_line_repeat": 2071, "ngram8_unique": 0.0123}}
    import bench.convergence as C
    assert C.is_converged(row) is True, "the ratified formula is unchanged"
    assert T.classify(row) is None, "nonconv_kind stays None: it did self-terminate"
    assert T.is_degenerate(row) is True, "but the loop must be detectable"


def test_a_healthy_long_trace_is_not_flagged():
    """Every healthy IFEval row measured unique_line_ratio >= 0.44 and max_line_repeat <= 11, so the
    threshold sits in a two-order-of-magnitude gap, not on a boundary."""
    import bench.traces as T
    row = {"finish_reason": "stop", "completion_tokens": 5775, "thinking_budget": 81920,
           "reasoning_stats": {"chars": 20000, "lines": 300, "unique_line_ratio": 0.663,
                               "max_line_repeat": 4, "ngram8_unique": 0.674}}
    assert T.is_degenerate(row) is False


def test_a_short_trace_is_never_flagged():
    """Too few lines to judge — inconclusive must not read as degenerate."""
    import bench.traces as T
    row = {"finish_reason": "stop", "completion_tokens": 50, "thinking_budget": 81920,
           "reasoning_stats": {"chars": 200, "lines": 3, "unique_line_ratio": 0.33,
                               "max_line_repeat": 2, "ngram8_unique": 0.5}}
    assert T.is_degenerate(row) is False


def test_error_rows_and_missing_stats_are_not_flagged():
    import bench.traces as T
    assert T.is_degenerate({"error": "boom"}) is False
    assert T.is_degenerate({"finish_reason": "stop", "completion_tokens": 10}) is False


def test_a_NON_converged_loop_still_classifies_as_degenerate_repetition():
    """The pre-existing path must be untouched: a loop that hit the budget is still non-converged
    AND still named degenerate_repetition."""
    import bench.traces as T
    row = {"finish_reason": "stop", "completion_tokens": 81920, "thinking_budget": 81920,
           "reasoning_stats": {"chars": 300000, "lines": 5000, "unique_line_ratio": 0.01,
                               "max_line_repeat": 3000, "ngram8_unique": 0.01}}
    assert T.classify(row) == "degenerate_repetition"
    assert T.is_degenerate(row) is True


def test_summarize_reports_the_eosed_loop_count_and_its_cost_share():
    """The number that matters is the COST share, not the row count: 1 of 28 rows was 32% of wall."""
    import bench.traces as T
    degen = {"finish_reason": "stop", "completion_tokens": 52503, "thinking_budget": 81920,
             "wall_s": 271.5,
             "reasoning_stats": {"lines": 4179, "unique_line_ratio": 0.0093,
                                 "max_line_repeat": 2071, "ngram8_unique": 0.0123}}
    ok = {"finish_reason": "stop", "completion_tokens": 2500, "thinking_budget": 81920,
          "wall_s": 25.0,
          "reasoning_stats": {"lines": 200, "unique_line_ratio": 0.9,
                              "max_line_repeat": 2, "ngram8_unique": 0.8}}
    s = T.summarize([degen] + [ok] * 27)
    assert s["n_degenerate_eosed"] == 1
    assert 0.28 < s["degenerate_wall_share"] < 0.34
    assert 0.40 < s["degenerate_token_share"] < 0.50


# ------------------------------------------------------------------ n-gram-level degeneracy
# Measured on the live IFEval run at n=106 (2026-08-13): the line-based detector caught 1 of 3
# degenerate items. The two it missed cycle near-identical PHRASINGS, so every line is technically
# unique and line repetition sees nothing:
#   id 279 : 52,409 tok / 446s, unique_line_ratio 1.0000, max_line_repeat 1, ngram8_unique 0.0104
#   id 3608: 54,702 tok / 285s, unique_line_ratio 0.8966, max_line_repeat 2, ngram8_unique 0.0323
# Healthy items on the same run measured ngram8_unique ~0.73, so the gap is 20-70x, not marginal.
# Together the three are 2.8% of items and 29% of wall-clock.
def test_ngram_degeneracy_is_caught_even_when_every_LINE_is_unique():
    """id 279: unique_line_ratio 1.0 and max_line_repeat 1 — line repetition is blind to this."""
    import bench.traces as T
    row = {"finish_reason": "stop", "completion_tokens": 52409, "thinking_budget": 81920,
           "reasoning_stats": {"chars": 180000, "lines": 900, "unique_line_ratio": 1.0,
                               "max_line_repeat": 1, "ngram8_unique": 0.0104}}
    assert T.is_degenerate(row) is True


def test_ngram_degeneracy_with_mostly_unique_lines_is_caught():
    """id 3608: unique_line_ratio 0.8966 — comfortably above the line-repetition threshold."""
    import bench.traces as T
    row = {"finish_reason": "stop", "completion_tokens": 54702, "thinking_budget": 81920,
           "reasoning_stats": {"chars": 190000, "lines": 1200, "unique_line_ratio": 0.8966,
                               "max_line_repeat": 2, "ngram8_unique": 0.0323}}
    assert T.is_degenerate(row) is True


def test_a_healthy_trace_at_the_measured_uniqueness_is_NOT_flagged():
    """Healthy IFEval items measured ngram8_unique ~0.73; the threshold must sit far below that."""
    import bench.traces as T
    for ng in (0.7285, 0.7388, 0.5478, 0.30):
        row = {"finish_reason": "stop", "completion_tokens": 9875, "thinking_budget": 81920,
               "reasoning_stats": {"chars": 30000, "lines": 400, "unique_line_ratio": 0.81,
                                   "max_line_repeat": 3, "ngram8_unique": ng}}
        assert T.is_degenerate(row) is False, f"ngram8_unique={ng} must not be flagged"


def test_a_SHORT_trace_with_low_ngram_uniqueness_is_not_flagged():
    """Low uniqueness is only meaningful over a long trace — a brief answer can legitimately repeat
    a template. Guarding on length keeps a 3-line reply from being called a loop."""
    import bench.traces as T
    row = {"finish_reason": "stop", "completion_tokens": 60, "thinking_budget": 81920,
           "reasoning_stats": {"chars": 200, "lines": 4, "unique_line_ratio": 0.5,
                               "max_line_repeat": 2, "ngram8_unique": 0.02}}
    assert T.is_degenerate(row) is False


def test_meander_still_requires_HIGH_novelty_and_is_unaffected():
    """The meander label means over-exploration (genuinely new text). These low-novelty loops are
    the opposite, and must not be relabelled as meanders."""
    import bench.traces as T
    row = {"finish_reason": "stop", "completion_tokens": 81920, "thinking_budget": 81920,
           "reasoning_stats": {"chars": 180000, "lines": 900, "unique_line_ratio": 1.0,
                               "max_line_repeat": 1, "ngram8_unique": 0.0104}}
    assert T.classify(row) == "degenerate_repetition", "a low-novelty loop is not a meander"
