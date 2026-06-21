"""TDD tests for bench.aggregation — RULER-style common-words extraction probe."""
import re

import bench.aggregation as AG


def test_build_cwe_targets_are_most_frequent():
    ctx, targets, q = AG.build_cwe(4000, chars_per_token=4.0, k=5, freq_common=30,
                                   freq_uncommon=3, seed=1)
    assert len(targets) == 5 and len(set(targets)) == 5
    counts = {t: len(re.findall(rf"\b{re.escape(t)}\b", ctx)) for t in targets}
    # every target appears freq_common times
    assert all(c == 30 for c in counts.values()), counts
    # question mentions how many words to return
    assert "5" in q


def test_build_cwe_deterministic():
    assert AG.build_cwe(3000, 4.0, seed=7) == AG.build_cwe(3000, 4.0, seed=7)


def test_build_cwe_targets_beat_distractors():
    ctx, targets, _ = AG.build_cwe(6000, 4.0, k=3, freq_common=40, freq_uncommon=2, seed=3)
    words = re.findall(r"\b[a-z]+\b", ctx)
    from collections import Counter
    freq = Counter(words)
    top3 = {w for w, _ in freq.most_common(3)}
    assert set(targets) == top3      # the targets are exactly the 3 most frequent


def test_score_cwe_fraction():
    targets = ["alpha", "bravo", "charlie", "delta", "echo"]
    assert AG.score_cwe("alpha, bravo, charlie, delta, echo", targets) == 1.0
    assert AG.score_cwe("ALPHA and BRAVO only", targets) == 2 / 5
    assert AG.score_cwe("none here", targets) == 0.0


def test_score_cwe_whole_word_only():
    # 'alpha' should not match inside 'alphabet'
    assert AG.score_cwe("alphabet soup", ["alpha"]) == 0.0


class _FakeSampler:
    def __init__(self, pid=None, interval=0.2):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class _OKDriver:
    def complete(self, model, messages, params, timeout=3600):
        return {"content": "x", "prompt_tokens": 100, "decode_tps": 1.0, "peak_mem_gb": 1.0,
                "prefill_s": 0.1, "prefill_tps": 1, "wall_s": 0.1}


def test_aggregation_ladder_stops_at_cliff(monkeypatch):
    """Climb-to-cliff: a rung below threshold stops the ladder. The scorer is stubbed by a
    call counter (samples=2): the first rung passes, the second fails."""
    calls = {"n": 0}

    def stub(resp, targets):
        calls["n"] += 1
        return 1.0 if calls["n"] <= 2 else 0.0

    monkeypatch.setattr(AG, "score_cwe", stub)
    recs = AG.run_aggregation_ladder(_OKDriver(), "m", 4.0, model_pid=1, params={},
                                     grid=(1000, 2000, 3000), threshold=0.85, samples=2,
                                     sampler_factory=_FakeSampler)
    assert [r["ctx"] for r in recs] == [1000, 2000]      # stopped at the cliff (rung2 never run)
    assert recs[0]["accuracy"] == 1.0 and recs[1]["accuracy"] == 0.0


def test_aggregation_ladder_auto_extends_past_grid(monkeypatch):
    """If the top planned rung still passes, the ladder extends in +extend_step steps up to
    max_ctx, then stops."""
    monkeypatch.setattr(AG, "score_cwe", lambda resp, targets: 1.0)   # always pass
    recs = AG.run_aggregation_ladder(_OKDriver(), "m", 4.0, model_pid=1, params={},
                                     grid=(1000,), threshold=0.85, samples=1,
                                     extend_step=1000, max_ctx=3000, sampler_factory=_FakeSampler)
    assert [r["ctx"] for r in recs] == [1000, 2000, 3000]   # extended to max_ctx
