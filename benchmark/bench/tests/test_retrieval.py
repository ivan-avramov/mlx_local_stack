from bench.retrieval import (
    build_context, score, make_question, hits, DEPTHS, run_retrieval_ladder,
)
import re

def test_build_places_all_needles_in_order():
    ctx, needles = build_context(2000, chars_per_token=4.0)
    assert len(needles) == len(DEPTHS)
    assert len(set(needles)) == len(needles)          # all unique
    positions = [ctx.find(n) for n in needles]
    assert all(p >= 0 for p in positions)             # all present
    assert positions == sorted(positions)             # placed by ascending depth

def test_score_is_fraction_found():
    _, needles = build_context(2000, 4.0)
    assert score(" ".join(needles), needles) == 1.0
    assert score(needles[0], needles) == 1.0 / len(needles)
    assert score("nothing here", needles) == 0.0

def test_question_mentions_count():
    _, needles = build_context(2000, 4.0)
    assert str(len(needles)) in make_question(needles)

def test_build_context_seeded_unique_needles():
    _, n0 = build_context(2000, 4.0, seed=0)
    _, n1 = build_context(2000, 4.0, seed=1)
    assert len(set(n0)) == len(n0)          # unique within a context
    assert n0 != n1                          # different seeds -> different needles


def test_build_context_deterministic():
    assert build_context(2000, 4.0, seed=7) == build_context(2000, 4.0, seed=7)


def test_build_context_needles_fixed_length():
    _, needles = build_context(2000, 4.0, seed=3)
    assert all(len(n) == 8 for n in needles)


def test_hits_per_needle():
    _, needles = build_context(2000, 4.0, seed=0)
    assert hits(", ".join(needles), needles) == [True] * len(needles)
    assert hits(needles[2], needles) == [i == 2 for i in range(len(needles))]
    assert hits("", needles) == [False] * len(needles)
    assert hits(None, needles) == [False] * len(needles)


class FakeSampler:
    def __init__(self, pid=None, interval=0.2):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    system_peak_gb = 30.0
    peak_rss_gb = 20.0


_NEEDLE_RE = re.compile(r"is ([A-Z0-9]{8})\.")
_PROD = {"max_tokens": 256, "temperature": 0.7, "thinking_budget": 128,
         "top_p": 0.95, "enable_thinking": True}


def _ok(content):
    return {"content": content, "prompt_tokens": 100, "decode_tps": 50.0,
            "peak_mem_gb": 20.0, "prefill_s": 0.5, "prefill_tps": 200, "wall_s": 1.0}


class AllNeedlesDriver:
    """Echoes every needle present in the prompt -> accuracy 1.0."""
    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        return _ok(", ".join(_NEEDLE_RE.findall(messages[-1]["content"])))


class NoNeedlesDriver:
    """Returns no codes -> accuracy 0.0, but does NOT raise."""
    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        return _ok("I could not find any codes.")


class ExplodingDriver:
    """Raises on every call -> simulates a hard OOM at this context length."""
    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        raise RuntimeError("server exploded (OOM)")


def test_ladder_full_curve_all_correct():
    recs = run_retrieval_ladder(AllNeedlesDriver(), "m", 4.0, model_pid=1,
                                params=_PROD, grid=(8000, 16000, 24000), samples=3,
                                sampler_factory=FakeSampler)
    assert len(recs) == 3
    assert all(r["accuracy"] == 1.0 for r in recs)
    assert all(len(r["per_depth_acc"]) == len(DEPTHS) for r in recs)


def test_ladder_does_not_stop_on_low_accuracy():
    """KEY DIFFERENCE FROM REASONING: a rung below threshold (no hard error) does not
    stop the full curve."""
    recs = run_retrieval_ladder(NoNeedlesDriver(), "m", 4.0, model_pid=1,
                                params=_PROD, grid=(8000, 16000, 24000),
                                threshold=0.85, samples=3, sampler_factory=FakeSampler)
    assert len(recs) == 3                         # all rungs ran despite acc=0
    assert all(r["accuracy"] == 0.0 for r in recs)
    assert all(r["errors"] == 0 for r in recs)


def test_ladder_exception_escalates():
    """M41 FIX1 F3 (O41): a transport/HTTP failure in complete() ESCALATES -- it is
    never graded as a wrong answer (mirrors bench.reasoning's exception-escalates test).
    A timed-out/disconnected request is not a model failure; the caller must see it."""
    import pytest
    with pytest.raises(Exception):
        run_retrieval_ladder(ExplodingDriver(), "m", 4.0, model_pid=1,
                             params=_PROD, grid=(8000, 16000, 24000), samples=2,
                             sampler_factory=FakeSampler)


def test_ladder_per_depth_breakdown():
    recs = run_retrieval_ladder(AllNeedlesDriver(), "m", 4.0, model_pid=1,
                                params=_PROD, grid=(8000,), samples=2,
                                sampler_factory=FakeSampler)
    assert recs[0]["per_depth_acc"] == [1.0, 1.0, 1.0, 1.0, 1.0]


def test_ladder_params_forwarded():
    received = []

    class RecordParamsDriver:
        def complete(self, model, messages, params, timeout=3600):
            received.append(dict(params))
            return _ok(", ".join(_NEEDLE_RE.findall(messages[-1]["content"])))

    custom = {"max_tokens": 512, "temperature": 0.7, "thinking_budget": 999,
              "top_p": 0.95, "enable_thinking": True}
    run_retrieval_ladder(RecordParamsDriver(), "m", 4.0, model_pid=1, params=custom,
                         grid=(8000,), samples=1, sampler_factory=FakeSampler)
    assert received[0]["thinking_budget"] == 999    # not bounded/overridden
    assert received[0]["temperature"] == 0.7


# ---------------------------------------------------------------------------
# M41 T1: request_timeout threading, per-trial rows, draft/acceptance, rung means
# ---------------------------------------------------------------------------

def test_ladder_request_timeout_forwarded_to_driver():
    seen = []

    class TimeoutDriver:
        def complete(self, model, messages, params, timeout=3600):
            seen.append(timeout)
            return _ok("")

    run_retrieval_ladder(TimeoutDriver(), "m", 4.0, model_pid=1, params=_PROD,
                         grid=(8000,), samples=2, sampler_factory=FakeSampler,
                         request_timeout=1234)
    assert seen == [1234, 1234]


class DraftDriver:
    """Echoes needles AND reports speculative-decoding counters in raw_timings."""
    def complete(self, model, messages, params, timeout=3600):
        out = _ok(", ".join(_NEEDLE_RE.findall(messages[-1]["content"])))
        out["completion_tokens"] = 42
        out["finish_reason"] = "stop"
        out["raw_timings"] = {"draft_kind": "mtp", "draft_rounds": 3,
                              "draft_n": 10, "draft_n_accepted": 7}
        return out


def test_ladder_rows_carry_prefill_s_and_draft():
    recs = run_retrieval_ladder(DraftDriver(), "m", 4.0, model_pid=1,
                                params=_PROD, grid=(8000,), samples=2,
                                sampler_factory=FakeSampler)
    rows = recs[0]["rows"]
    assert len(rows) == 2
    assert [r["trial"] for r in rows] == [0, 1]
    assert [r["seed"] for r in rows] == [8000 * 1000, 8000 * 1000 + 1]
    assert rows[0]["prefill_s"] == 0.5
    assert rows[0]["prompt_tokens"] == 100
    assert rows[0]["completion_tokens"] == 42
    assert rows[0]["finish_reason"] == "stop"
    assert rows[0]["decode_tps"] == 50.0
    assert rows[0]["wall_s"] == 1.0
    assert rows[0]["error"] is None
    assert rows[0]["hits"] == [True] * len(DEPTHS)
    assert rows[0]["draft"] == {"draft_kind": "mtp", "draft_rounds": 3,
                                "draft_n": 10, "draft_n_accepted": 7}


def test_ladder_rung_means_and_pooled_acceptance():
    recs = run_retrieval_ladder(DraftDriver(), "m", 4.0, model_pid=1,
                                params=_PROD, grid=(8000,), samples=2,
                                sampler_factory=FakeSampler)
    rec = recs[0]
    assert rec["prefill_s_mean"] == 0.5
    assert rec["decode_tps_mean"] == 50.0
    assert rec["acceptance_pooled"] == round(7 / 10, 4)


def test_ladder_no_draft_means_acceptance_pooled_is_none():
    recs = run_retrieval_ladder(AllNeedlesDriver(), "m", 4.0, model_pid=1,
                                params=_PROD, grid=(8000,), samples=2,
                                sampler_factory=FakeSampler)
    rec = recs[0]
    assert rec["rows"][0]["draft"] is None
    assert rec["acceptance_pooled"] is None


def test_ladder_raising_driver_propagates_before_any_row_completes():
    """M41 FIX1 F3: no graded-zero row is fabricated for a raising driver -- the
    exception reaches the caller on the FIRST trial (no per-trial except-and-continue)."""
    import pytest
    calls = []

    class CountingExplodingDriver:
        def complete(self, model, messages, params, timeout=3600):
            calls.append(1)
            raise RuntimeError("server exploded (OOM)")

    with pytest.raises(RuntimeError):
        run_retrieval_ladder(CountingExplodingDriver(), "m", 4.0, model_pid=1,
                             params=_PROD, grid=(8000, 16000, 24000), samples=2,
                             sampler_factory=FakeSampler)
    assert calls == [1]  # stopped at the FIRST raising trial, no continuation


# ---------------------------------------------------------------------------
# M41 FIX1 F1: one progress line per trial (review defect 1)
# ---------------------------------------------------------------------------

def test_ladder_prints_one_progress_line_per_trial(capsys):
    run_retrieval_ladder(AllNeedlesDriver(), "m", 4.0, model_pid=1,
                         params=_PROD, grid=(8000, 16000), samples=3,
                         sampler_factory=FakeSampler)
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.startswith("[retrieval] ")]
    assert len(lines) == 2 * 3  # 2 rungs * 3 trials
    assert "ctx=8000 trial=0/3" in lines[0]
    assert "hits=" in lines[0]
    assert "prefill_s=" in lines[0]
    assert "decode_tps=" in lines[0]
