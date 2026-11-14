"""M76 B7.1 (implementer): spec amendment v1.2 — screen options T3 (sensitive trigger) and TD (always the decider)."""
import json
from pathlib import Path

import pytest

from bench import m76_rule as R
from bench import m76_sim as M

from bench.tests.test_m76_b7_1_impl_screen import _brute

REPORT = Path(M.__file__).resolve().parent.parent / "results" / "m76" / "b7-simulation"


def _committed():
    return json.loads((REPORT / "report.json").read_text())


def _opt(name):
    return next(o for o in M.SCREEN_OPTIONS if o[0] == name)


def test_t3_and_td_are_registered_after_t0_t2():
    assert [o[0] for o in M.SCREEN_OPTIONS] == ["T0", "T1", "T2", "T3", "TD"]
    assert _opt("T3") == ("T3", 0, -10)
    assert _opt("TD") == ("TD", None, None)
    assert set(M.SCREEN_OPTION_TEXT) == {"T0", "T1", "T2", "T3", "TD"}


@pytest.mark.parametrize("sums, t3", [
    ((0, 0, 0, 0), False),          # macro 0 pp: not < 0
    ((-1, 1, 0, 0), False),         # macro 0, one language −10 pp: not < −10
    ((-1, 0, 0, 0), True),          # macro −2.5 pp
    ((-2, 1, 1, 0), True),          # macro 0, one language −20 pp
    ((-2, 2, 1, 1), True),          # macro +5 pp, one language −20 pp
    ((-1, 2, 2, 2), False),         # macro +12.5 pp, worst language −10 pp
    ((5, 5, 5, 5), False),
])
def test_t3_and_td_trigger_boundaries(sums, t3):
    _, mp, lp = _opt("T3")
    assert M.screen_trigger(list(sums), 10, mp, lp) is t3
    _, mp, lp = _opt("TD")
    assert M.screen_trigger(list(sums), 10, mp, lp) is True


@pytest.mark.parametrize("option", ["T3", "TD"])
@pytest.mark.parametrize("losses", [(0.0, 0.0), (0.3, 0.0), (0.2, 0.2)])
def test_t3_td_exact_matches_brute_force(option, losses):
    models = M._screen_models(None, 0.3, 0.0, losses, M.DEFAULT_KAPPA)
    ex = M._screen_exact_models(models, 0.0, 3, *_opt(option)[1:])
    assert ex == pytest.approx(_brute(models, 0.0, 3, option), abs=1e-12)


def test_td_exact_trigger_is_one_and_t3_contains_t0():
    for _, losses in M.SCREEN_SCENARIOS:
        assert M.screen_trigger_exact(0.5, 0.182, M.PRIMARY_SIGMA, losses, "TD") == 1.0
        assert (M.screen_trigger_exact(0.5, 0.182, M.PRIMARY_SIGMA, losses, "T3")
                >= M.screen_trigger_exact(0.5, 0.182, M.PRIMARY_SIGMA, losses, "T0") - 1e-12)
    r = M.simulate_screen(0.5, 0.182, 0.25, (0.0,) * 4, 500)
    rates = M.screen_rates(r["hist"], 500, 10)
    assert rates["T0"]["k"] <= rates["T3"]["k"] <= rates["TD"]["k"] == 500


def _decider_pass_no_flag(hist, hold):
    hp = dict(M.HOLD_THRESHOLDS)[hold]
    return sum(n for key, n in hist.items()
               if key.split("|")[1] == "P" and key.split("|")[2] == "0" and not M.hold_fires(int(key.split("|")[3]), hp))


@pytest.mark.parametrize("hold", [h for h, _ in M.HOLD_THRESHOLDS])
def test_td_trigger_one_and_false_clean_is_decider_pass_no_flag(hold):
    """v1.2 test: TD's trigger rate is 1 and its A8-path clean (false-clean at a macro 10 pp loss) equals the decider's
    PASS ∧ no flag rate (∧ no HOLD at the threshold)."""
    reps = 300
    r = M.simulate_a8_nested(0.5, 0.182, M.PRIMARY_SIGMA, (M.SAFE_LOSS,) * 4, reps, alpha=0.001)
    p = M.a8_path_from(r["hist"], reps, "TD", hold)
    assert p["trigger"]["k"] == reps
    assert p["clean"]["k"] == p["decider_clean"]["k"] == _decider_pass_no_flag(r["hist"], hold)
    assert p["decider_clean_given_no_trigger"] is None


def test_nested_hist_keys_carry_one_bit_per_option_and_t0_t2_unchanged():
    reps = 200
    r = M.simulate_a8_nested(0.5, 0.182, M.PRIMARY_SIGMA, (0.0,) * 4, reps, alpha=0.001)
    assert all(len(k.split("|")[0]) == len(M.SCREEN_OPTIONS) for k in r["hist"])
    assert all(k.split("|")[0][4] == "1" for k in r["hist"])


# ------------------------------------------------------------------------------------------- the report
def test_report_screen_options_have_every_v12_field():
    rep = _committed()
    opts = rep["variants"]["screen_options"]
    assert list(opts) == ["T0", "T1", "T2", "T3", "TD"]
    cells = list(rep["joint"]["cells"])
    for name, o in opts.items():
        for k in ("trigger0", "detect_macro10", "detect_concentrated10", "detect_one_language10",
                  "a8_path_clean_at_loss10", "clean_pass0", "clean_pass0_a5_2l", "hours", "hours_a5_2l"):
            assert k in o, (name, k)
        assert set(o["clean_pass0_by_cell"]) == set(o["clean_pass0_a5_2l_by_cell"]) == set(cells)
        for h in ("expected", "whole_stage_expected"):
            assert h in o["hours"] and h in o["hours_a5_2l"]
    td = opts["TD"]
    assert td["trigger0"]["k"] == td["trigger0"]["n"]
    assert td["detect_macro10"]["k"] == td["detect_macro10"]["n"]
    # TD always runs the decider: expected hours = worst on the A8 leg
    assert td["hours"]["expected"] > opts["T0"]["hours"]["expected"]


def test_report_td_false_clean_equals_decider_pass_no_flag_no_hold():
    rep = _committed()
    n10 = rep["joint"]["a8_nested"][f"loss={M.SAFE_LOSS}"]
    td = rep["variants"]["screen_options"]["TD"]
    for h, _ in M.HOLD_THRESHOLDS:
        assert td["a8_path_clean_at_loss10_by_hold"][h]["k"] == _decider_pass_no_flag(n10["hist"], h)


def test_report_a5_2l_column_equals_a5_2l_variant_for_td():
    rep = _committed()
    t0, a5 = rep["variants"]["screen_options"]["TD"], rep["variants"]["A5-2L"]          # v1.3: TD is committed
    assert t0["clean_pass0_a5_2l_by_cell"] == a5["clean_pass0_by_cell"]
    assert t0["hours_a5_2l"] == a5["hours"]
    assert R.axis_plan("A8")["looks"][0]["alpha"] == 0.001          # nothing adopted


def test_rendered_screen_table_has_t3_td_rows():
    md = (REPORT / "REPORT.md").read_text()
    sec = md[md.index("Screen options (C324"):]
    for name in ("T3", "TD"):
        assert f"| {name}: " in sec
    assert "with A5-2L" in sec
