"""`bench.capacity_ladder.rung_problems(row, predictor)` (R21): strict rung validity from the backend's own telemetry."""
import pytest

from .fakes import strict_row


def rp(row, on):
    import bench.capacity_ladder as L
    return L.rung_problems(row, "mtp" if on else "off")


def good(on=True, **over):
    # prompt_n 40000, prompt_ms 100000 -> the reference rate is exactly 400.0 tok/s
    row = strict_row("TQ4" if on else "TQ4-OFF", 39943)
    row.update(prompt_n=40000, prompt_tokens=40000, prompt_ms=100000.0, prompt_per_second=400.0)
    row.update(over)
    return row


# ------------------------------------------------------------------------------------------- the accepted shapes
def test_a_good_on_row_has_no_problems():
    # class: exercises new behaviour
    assert rp(good(), True) == []


def test_a_good_off_row_has_no_problems():
    # class: exercises new behaviour
    assert rp(good(on=False), False) == []


def test_the_result_is_a_list_of_strings_and_never_raises_on_an_empty_row():
    # class: exercises new behaviour
    out = rp({}, True)
    assert out and all(isinstance(x, str) for x in out)


# ------------------------------------------------------------------------------------------- token counts / finish
@pytest.mark.parametrize("n", [255, 257, 0, 512])
def test_completion_tokens_must_be_exactly_256(n):
    # class: exercises new behaviour (255 / 256 / 257 boundary)
    assert rp(good(completion_tokens=n), True)


@pytest.mark.parametrize("n", [255, 257])
def test_predicted_n_must_be_exactly_256(n):
    # class: exercises new behaviour
    assert rp(good(predicted_n=n), True)


def test_completion_tokens_and_predicted_n_must_agree():
    # class: reproduces a failure the contract fixes (R21: token counts agree; a client count off the backend's)
    assert rp(good(completion_tokens=256, predicted_n=255), True)
    assert rp(good(completion_tokens=255, predicted_n=256), True)


@pytest.mark.parametrize("fr", ["stop", None, "error", ""])
def test_finish_reason_must_be_length(fr):
    # class: exercises new behaviour
    assert rp(good(finish_reason=fr), True)


# ------------------------------------------------------------------------------------------- cache_n (R21, r2-glm-6)
@pytest.mark.parametrize("v", [0, 0.0])
def test_cache_n_accepts_numeric_zero_of_either_json_type(v):
    # class: reproduces a failure the contract fixes (r2-glm-6: `0.0` from a JSON float is a cold prefill too)
    assert rp(good(cache_n=v), True) == []


@pytest.mark.parametrize("v", [1, 0.5, 4096, -1, None, "0", True])
def test_cache_n_otherwise_refused(v):
    # class: exercises new behaviour (a warm prefix means the prefill rate is not a cold rate)
    assert rp(good(cache_n=v), True)


def test_a_missing_cache_n_is_refused():
    # class: exercises new behaviour
    row = good()
    del row["cache_n"]
    assert rp(row, True)


# ------------------------------------------------------------------------------------------- prefill reconciliation (2 %)
@pytest.mark.parametrize("pps", [400.0, 408.0, 392.5, 399.9])
def test_prompt_per_second_within_two_percent_passes(pps):
    # class: exercises new behaviour (the tolerance edge: 408.0 is exactly +2 % of the 400.0 reference)
    assert rp(good(prompt_per_second=pps), True) == []


@pytest.mark.parametrize("pps", [409.0, 391.0, 800.0, 200.0, 0.0])
def test_prompt_per_second_beyond_two_percent_is_refused(pps):
    # class: reproduces a failure the contract fixes (R21: wall - decode derivation vs the backend's own rate)
    assert rp(good(prompt_per_second=pps), True)


@pytest.mark.parametrize("key", ["prompt_ms", "prompt_per_second", "prompt_n"])
def test_missing_prefill_telemetry_is_refused_not_a_crash(key):
    # class: exercises new behaviour
    row = good()
    del row[key]
    assert rp(row, True)


@pytest.mark.parametrize("ms", [0.0, -5.0, None])
def test_nonpositive_prompt_ms_is_refused_not_a_crash(ms):
    # class: exercises new behaviour
    assert rp(good(prompt_ms=ms), True)


def test_prompt_n_must_equal_the_rows_prompt_tokens():
    # class: exercises new behaviour (the prompt_n the backend prefilled vs the tokens the request carried)
    assert rp(good(prompt_n=40000, prompt_tokens=40001), True)
    assert rp(good(prompt_n=39999, prompt_tokens=40000), True)


# ------------------------------------------------------------------------------------------- v1.2 (Sol P4): peak and decode rate
@pytest.mark.parametrize("key", ["peak_memory_gb_cumulative", "predicted_per_second"])
@pytest.mark.parametrize("bad", [None, 0, 0.0, -1.0, float("nan"), float("inf"), "12.0", True])
def test_peak_memory_and_decode_rate_must_be_finite_and_positive(key, bad):
    # class: reproduces a failure the contract fixes (v1.2 Sol P4; red on round-1: a rung with no memory number was valid)
    assert rp(good(**{key: bad}), True)
    assert rp(good(on=False, **{key: bad}), False)


@pytest.mark.parametrize("key", ["peak_memory_gb_cumulative", "predicted_per_second"])
def test_a_missing_peak_or_decode_rate_is_refused(key):
    # class: reproduces a failure the contract fixes (v1.2 Sol P4)
    row = good()
    del row[key]
    assert rp(row, True)


# ------------------------------------------------------------------------------------------- predictor ON
@pytest.mark.parametrize("kind", [None, "suffix", "dflash", ""])
def test_on_needs_draft_kind_mtp(kind):
    # class: exercises new behaviour
    assert rp(good(draft_kind=kind), True)


@pytest.mark.parametrize("n", [0, None, -1])
def test_on_needs_positive_draft_n(n):
    # class: exercises new behaviour
    assert rp(good(draft_n=n), True)


@pytest.mark.parametrize("acc,ok", [(0, True), (1, True), (100, True), (200, True), (201, False), (-1, False), (None, False)])
def test_on_accepted_is_between_zero_and_draft_n_inclusive(acc, ok):
    # class: exercises new behaviour (draft_n = 200 in the fixture; 0 and 200 are the inclusive edges)
    assert (rp(good(draft_n_accepted=acc), True) == []) is ok


@pytest.mark.parametrize("r", [0, None, -3])
def test_on_needs_positive_draft_rounds(r):
    # class: exercises new behaviour
    assert rp(good(draft_rounds=r), True)


def test_on_without_any_drafter_keys_is_refused():
    # class: reproduces a failure the contract fixes (an ON arm whose drafter silently did not engage)
    row = good(on=False)
    assert rp(row, True)


# ------------------------------------------------------------------------------------------- predictor OFF
@pytest.mark.parametrize("key,val", [("draft_kind", "mtp"), ("draft_n", 10), ("draft_n_accepted", 3), ("draft_rounds", 2),
                                     ("draft_n", 0)])
def test_off_refuses_any_non_null_drafter_key(key, val):
    # class: exercises new behaviour (an OFF arm carrying drafter counters is an arm mix-up)
    assert rp(good(on=False, **{key: val}), False)


def test_off_accepts_drafter_keys_that_are_null():
    # class: exercises new behaviour (the server may send JSON null on OFF arms)
    row = good(on=False, draft_kind=None, draft_n=None, draft_n_accepted=None, draft_rounds=None)
    assert rp(row, False) == []


def test_off_accepts_drafter_keys_that_are_absent():
    # class: exercises new behaviour
    row = good(on=False)
    for k in ("draft_kind", "draft_n", "draft_n_accepted", "draft_rounds"):
        row.pop(k, None)
    assert rp(row, False) == []


def test_every_strict_check_still_applies_off():
    # class: exercises new behaviour
    assert rp(good(on=False, finish_reason="stop"), False)
    assert rp(good(on=False, cache_n=3), False)
