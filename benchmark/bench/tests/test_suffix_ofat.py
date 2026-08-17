"""The suffix ON/OFF analyser must be validated against KNOWN POSITIVES before a zero from it
is believed. That is not a general principle here, it is a scar: this session found a watcher whose
glob was wrong by two directory levels and would have reported a healthy run as stalled, and a
history grep that returned an empty set because zsh does not word-split `$var`. Both looked like
clean results.

So: an arm compared with ITSELF must report exactly zero on every difference endpoint, and an arm
compared with a KNOWN perturbation must report exactly the perturbation.
"""
import json

from m1 import suffix_ofat as S


def _row(i, *, content="def f():\n    return 1\n", ct=1000, wall=30.0, tps=100.0,
         kind=None, ngram20=0.94, ulr=0.86, mlr=9):
    return {"id": i, "sample": 0, "content": content, "completion_tokens": ct,
            "wall_s": wall, "decode_tps": tps, "nonconv_kind": kind,
            "reasoning_stats": {"ngram8_unique": 0.87, "ngram20_unique": ngram20,
                                "unique_line_ratio": ulr, "max_line_repeat": mlr}}


def _arm(n=20, **kw):
    return [_row(f"i{j}", **kw) for j in range(n)]


def test_an_arm_against_ITSELF_is_zero_on_every_difference_endpoint():
    arm = _arm()
    r = S.analyse(arm, arm, iters=200, seed=0)
    assert r["n_paired"] == 20
    assert r["divergence"]["rate"] == 0.0
    assert r["tokens"]["mean_diff"] == 0.0
    for k, v in r["repetition"].items():
        assert v["mean_diff"] == 0.0, (k, v)


def test_a_KNOWN_perturbation_is_reported_exactly():
    on = _arm(ct=1000, content="A")
    off = _arm(ct=1200, content="B")          # every item differs, every item +200 tokens
    r = S.analyse(on, off, iters=200, seed=0)
    assert r["divergence"]["rate"] == 1.0
    assert r["tokens"]["mean_diff"] == -200.0, r["tokens"]   # on - off
    assert r["n_paired"] == 20


def test_partial_divergence_is_counted_per_item_not_pooled():
    on = _arm(10)
    off = [_row(f"i{j}", content="X" if j < 3 else "def f():\n    return 1\n") for j in range(10)]
    r = S.analyse(on, off, iters=200, seed=0)
    assert r["divergence"]["rate"] == 0.3
    assert sorted(r["divergence"]["diverged_ids"]) == ["i0", "i1", "i2"]


def test_unpaired_items_are_dropped_and_NAMED_never_silently_pooled():
    on = _arm(5)
    off = _arm(5)[:3]
    r = S.analyse(on, off, iters=200, seed=0)
    assert r["n_paired"] == 3
    assert sorted(r["unpaired"]["on_only"]) == ["i3", "i4"]


def test_degeneracy_counts_BOTH_definitions_because_the_corpus_uses_BOTH():
    """`grade.py` persists `degenerate_wall_share` over EOS'd degenerate rows only, while the
    published scoreboard row uses ALL rows with nonconv_kind == degenerate_repetition. Measured
    2026-08-16, the two differ by up to ~10x on the same rows (Ornith-1.0-35B-mlx-uniform-4bit
    mbppplus: 0.0% vs 63.1%). Reporting one number under that name is how the ambiguity spreads."""
    on = [_row("a", wall=10.0), _row("b", wall=90.0, kind="degenerate_repetition")]
    off = [_row("a", wall=10.0), _row("b", wall=10.0)]
    r = S.analyse(on, off, iters=200, seed=0)
    assert r["degeneracy"]["on"]["n_degenerate_repetition"] == 1
    assert r["degeneracy"]["off"]["n_degenerate_repetition"] == 0
    assert abs(r["degeneracy"]["on"]["broad_wall_share"] - 0.9) < 1e-9


def test_accuracy_endpoint_reports_the_MEASURED_pd_not_the_default():
    """The gate question. stats.mde defaults to p_d=0.20 — a BETWEEN-MODELS guess — which is what
    produced "628 items to resolve 5pp". A within-model paired lever has a far lower discordance,
    and the n it implies must come from the MEASURED value or the design is sized on a guess."""
    on = {f"i{j}": [1.0] for j in range(100)}
    off = dict(on)
    off["i0"] = [0.0]
    off["i1"] = [0.0]                                  # 2 discordant of 100 -> p_d = 0.02
    r = S.accuracy(on, off, iters=200, seed=0)
    assert abs(r["p_d"] - 0.02) < 1e-9
    assert r["n_for_5pp_at_measured_pd"] == 63, r       # vs 628 at the p_d=0.20 default
    assert r["mde_at_measured_pd"] < r["mde_at_default_pd"]


def test_speed_is_reported_but_LABELLED_as_the_expected_mechanical_effect():
    on = _arm(5, tps=100.0, wall=24.0)
    off = _arm(5, tps=77.0, wall=30.0)
    r = S.analyse(on, off, iters=200, seed=0)
    assert r["speed"]["decode_tps"]["mean_diff"] > 0
    assert "mechanical" in r["speed"]["note"].lower()


def test_it_refuses_to_analyse_empty_input_rather_than_reporting_zeros():
    """An empty arm must not read as "no difference" — the failure mode this whole file guards."""
    try:
        S.analyse([], [], iters=10, seed=0)
    except ValueError as e:
        assert "no paired items" in str(e).lower()
    else:
        raise AssertionError("empty input silently produced a result")


def test_an_ERROR_stub_is_excluded_from_pairing_and_NAMED_but_a_DNF_row_is_not():
    """Operator ruling 2026-08-17. An error stub (the request never completed — no content, no
    tokens) must not be zero-coerced into a paired delta: Mbpp/430's OFF-arm `timed out` stub was
    charged against a 102,401-token ON truncation, which alone more than doubled that cell's token
    delta. But a DNF (budget_hit / max_tokens / degenerate_repetition) IS a real draw and STAYS in
    every denominator — a model that converges on 1 of 100 items scores 1%, not 100%.
    """
    on = _arm(6)
    off = _arm(6)
    # i0: OFF arm errored — no draw exists on that side.
    off[0] = {"id": "i0", "sample": 0, "error": "timed out"}
    # i1: OFF arm is a genuine DNF (real content, ran away) — a real draw, must stay paired.
    off[1] = _row("i1", content="loop " * 500, ct=102401, wall=900.0, tps=90.0,
                  kind="degenerate_repetition")
    r = S.analyse(on, off, iters=200, seed=0)
    assert r["n_paired"] == 5, "the error-stub pair is excluded, the DNF pair is not"
    excl = r["excluded_error_rows"]
    assert excl["off"] == ["i0"] and excl["on"] == []
    # The DNF still counts: its degeneracy appears in the OFF arm's counts (denominator intact).
    assert r["degeneracy"]["off"]["n_rows"] == 5
    assert r["degeneracy"]["off"]["n_degenerate_repetition"] == 1
    # And the token delta reflects the DNF pair but NOT the error stub's zero-coercion.
    assert r["tokens"]["n"] == 5
