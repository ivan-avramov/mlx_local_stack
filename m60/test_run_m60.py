"""Pure-helper tests for run_m60.py (no router, no request, no model).

  . "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
  cd "$STACK_WORKDIR/m60" && "$STACK_REPO/.venv-bench/bin/python" -m pytest test_run_m60.py -q -p no:cacheprovider
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import run_m60 as R  # noqa: E402

sys.path.insert(0, str(R.REPO / "benchmark"))


def _row(i, content="answer", toks=100, fin="stop", seed=7, rsha="r1", **kw):
    return {"id": i, "sample": 0, "content": content, "completion_tokens": toks, "finish_reason": fin,
            "sampler_seed": seed, "reasoning_sha256": rsha, **kw}


# ------------------------------------------------------------------ pilot twice
def test_pilot_twice_identical_generations_have_no_diff():
    a = [_row("x"), _row("y")]
    assert R.pilot_twice_diff(a, [dict(r) for r in a], ["x", "y"]) == []


@pytest.mark.parametrize("field,kw", [("content", {"content": "other"}), ("completion_tokens", {"toks": 101}),
                                      ("finish_reason", {"fin": "length"}), ("reasoning", {"rsha": "r2"}),
                                      ("sampler_seed", {"seed": 8})])
def test_pilot_twice_flags_each_field(field, kw):
    probs = R.pilot_twice_diff([_row("x")], [_row("x", **kw)], ["x"])
    assert len(probs) == 1 and field in probs[0]


def test_pilot_twice_flags_a_missing_item_and_an_error_row():
    assert "missing in second" in R.pilot_twice_diff([_row("x")], [], ["x"])[0]
    assert "error row" in R.pilot_twice_diff([_row("x")], [{"id": "x", "error": "timed out"}], ["x"])[0]


def test_pilot_twice_falls_back_to_the_compressed_trace_when_no_sha():
    a = {"id": "x", "content": "c", "completion_tokens": 1, "finish_reason": "stop", "sampler_seed": 1,
         "reasoning_head": "h", "reasoning_tail": "t", "reasoning_chars": 10}
    assert R.pilot_twice_diff([a], [dict(a)], ["x"]) == []
    assert "reasoning" in R.pilot_twice_diff([a], [dict(a, reasoning_chars=11)], ["x"])[0]


# ------------------------------------------------------------------ row guard
def test_row_guard_allows_probe_timeout_dnf_and_clean_rows_only():
    rows = [_row("ok"), {"id": "dnf", "error": "timed out", "error_kind": "probe_timeout"},
            {"id": "bad", "error": "HTTP Error 500"}, {"id": "bad2", "error": "x", "error_kind": "other"}]
    assert [b["id"] for b in R.row_guard(rows)] == ["bad", "bad2"]
    assert R.row_guard(rows[:2]) == []


# ------------------------------------------------------------------ go / no-go
def test_go_no_go_arithmetic():
    g = R.go_no_go([43.3] * 5, 100)                      # the m40on mean: 1.20 h
    assert g["go"] and g["projected_h"] == pytest.approx(1.203, abs=1e-3)
    assert R.go_no_go([144.0] * 5, 100)["go"]            # exactly 4.0 h is still go
    assert not R.go_no_go([150.0] * 5, 100)["go"]        # 4.17 h
    assert not R.go_no_go([], 100)["go"]                 # no evidence is not a go
    assert R.go_no_go([10, 10, 10, 10, 500], 40)["max_s"] == 500


# ------------------------------------------------------------------ verdict
@pytest.mark.parametrize("delta,lo,hi,want", [
    (0.0, 0.0, 0.0, "PASS"), (0.01, -0.02, 0.04, "PASS"),
    (-0.03, -0.04, -0.01, "PASS"),            # significant but sub-margin: PASS is evaluated first
    (-0.02, -0.05, 0.0, "INCONCLUSIVE"),      # lower bound AT the margin is not above it
    (-0.02, -0.06, -0.005, "FAIL"),           # CI upper bound below 0
    (-0.05, -0.10, 0.0, "FAIL"),              # point at -margin
    (-0.06, -0.11, -0.02, "FAIL"), (-0.01, -0.07, 0.03, "INCONCLUSIVE")])
def test_m60_verdict(delta, lo, hi, want):
    assert R.m60_verdict(delta, lo, hi) == want


# ------------------------------------------------------------------ paired read (known answers)
def _per(n, wrong=()):
    return {f"i{k}": [0.0 if k in wrong else 1.0] for k in range(n)}


def test_paired_read_identical_arms_is_zero_and_passes():
    r = R.paired_read(_per(100, wrong={3}), _per(100, wrong={3}), iters=2000)
    assert (r["delta"], r["lo"], r["hi"]) == (0.0, 0.0, 0.0) and r["m60_verdict"] == "PASS"
    assert r["new_only_wins"] == [] and r["ref_only_wins"] == []


def test_paired_read_ten_losses_in_a_hundred_fails():
    r = R.paired_read(_per(100, wrong=set(range(10))), _per(100), iters=2000)
    assert r["delta"] == pytest.approx(-0.10) and r["hi"] < 0 and r["m60_verdict"] == "FAIL"
    assert len(r["ref_only_wins"]) == 10 and r["new_only_wins"] == []


def test_paired_read_sign_is_new_minus_ref_and_counts_discordance():
    r = R.paired_read(_per(100, wrong={0}), _per(100, wrong={1, 2, 3}), iters=2000)
    assert r["delta"] == pytest.approx(0.02) and len(r["new_only_wins"]) == 3 and len(r["ref_only_wins"]) == 1
    assert r["m60_verdict"] == "PASS"


def test_paired_read_refuses_different_item_sets():
    with pytest.raises(ValueError):
        R.paired_read(_per(10), _per(9))


# ------------------------------------------------------------------ power / processes
def test_power_parse_and_problems():
    p = R.parse_power(" Wattage = 140W\n Current = 4990mA\n Voltage = 28000mV\n", "-InternalBattery-0\t100%; charged;")
    assert p == {"watt": 140, "mv": 28000, "batt": 100} and R.power_problems(p) == []
    assert len(R.power_problems({"watt": 100, "mv": 20000, "batt": 15})) == 3
    assert R.power_problems(R.parse_power("", ""))  # unreadable is a problem, never a pass


def test_busy_processes_matches_serving_and_drivers_but_not_self():
    lines = ["  10 /x/python -m mlx_vlm.server --model m", "  11 uv run mlx-serve start", "  12 vim notes.md",
             "  13 python run.py generate --models m", "  14 python bench_watch.py --driver-pattern [r]un.py generate"]
    got = R.busy_processes(lines, {11})
    assert [g.split()[0] for g in got] == ["10", "13"]


# ------------------------------------------------------------------ registry / worker / manifest
GOOD_CMD = ("python mlx_vlm.server --model caslca/M --max-kv-size 262144 --kv-prealloc-tokens 262144 "
            "--cache-session-shrink on --attention-policy fused_v1 --lazy-prompt-embeddings "
            "--mtp-verify-scan joint_v1 --kv-quant-scheme turboquant --draft-kind mtp --draft-model d")


def test_worker_cmdline_check():
    assert R.worker_cmdline_problems(GOOD_CMD) == []
    assert R.worker_cmdline_problems(GOOD_CMD.replace("--draft-kind mtp", ""))
    assert R.worker_cmdline_problems(GOOD_CMD.replace("joint_v1", "per_query"))
    assert R.worker_cmdline_problems(GOOD_CMD + " --kv-bits 4")
    assert R.worker_cmdline_problems(GOOD_CMD + " --kv-bits 0") == []
    assert R.worker_cmdline_problems(GOOD_CMD + " --mtp-verify-ab")


def _entry(**over):
    e = {"kv_bits": 0, "attention_policy": "fused_v1", "lazy_prompt_embeddings": True, "mtp_verify_scan": "joint_v1",
         "draft_kind": "mtp", "draft_model": "d", "max_kv_cache_size": 262144, "kv_prealloc_tokens": 262144,
         "generation_defaults": dict(R.EXPECT_SAMPLING)}
    e.update(over)
    return e


def test_registry_entry_check():
    assert R.registry_entry_problems(_entry()) == []
    assert R.registry_entry_problems(_entry(kv_bits=4))
    assert R.registry_entry_problems(_entry(mtp_verify_scan=None))
    assert R.registry_entry_problems(_entry(generation_defaults=dict(R.EXPECT_SAMPLING, temperature=0.6)))


def _man(**over):
    m = {"runtime": {"draft_kind": "mtp", "attention_policy": "fused_v1", "lazy_prompt_embeddings": True,
                     "mtp_verify_scan": "joint_v1"},
         "kv": {"kv_bits": 0, "max_kv_cache_size": 262144, "kv_prealloc_tokens": 262144},
         "sampling": dict(R.EXPECT_SAMPLING), "registry": {"sha256": "S"}, "fingerprint_version": 8,
         "sampling_profile": "deployed", "router": {"pid": 5, "config_sha256": "S"}}
    m.update(over)
    return m


def test_manifest_check():
    assert R.manifest_problems(_man(), "S", 8, router_pid=5) == []
    assert R.manifest_problems(_man(), "OTHER", 8)                                  # registry drift
    assert R.manifest_problems(_man(), "S", 8, router_pid=6)                        # another router
    assert R.manifest_problems(_man(router=None), "S", 8)                           # no M50 attribution
    assert R.manifest_problems(_man(fingerprint_version=7), "S", 8)
    bad = _man(); bad["runtime"]["draft_kind"] = "off"
    assert any("draft_kind" in p for p in R.manifest_problems(bad, "S", 8))


def test_manifest_diff_lists_only_real_differences():
    a, b = _man(), _man()
    b["kv"]["kv_bits"] = 4; b["router"]["pid"] = 9; b["timestamp"] = 1
    assert R.manifest_diff(a, b) == {"kv.kv_bits": [0, 4]}


# ------------------------------------------------------------------ summaries
def test_summarize_rows_counts_and_counters():
    rows = [dict(_row("a"), wall_s=10.0, decode_tps=40.0, converged=True,
                 draft={"draft_kind": "mtp", "draft_n": 10, "draft_n_accepted": 8},
                 verify={"verify_blocks_joint_v1": 3, "verify_fallback_reasons": {"straddle": 1}},
                 sdpa={"sdpa_forced": 2}),
            dict(_row("b"), wall_s=30.0, decode_tps=20.0, converged=False, nonconv_kind="budget_hit",
                 draft={"draft_kind": "mtp", "draft_n": 10, "draft_n_accepted": 4}),
            {"id": "c", "error": "timed out", "error_kind": "probe_timeout", "wall_s": 7000.0}]
    s = R.summarize_rows(rows)
    assert s["n"] == 3 and s["converged"] == 1 and s["non_converged"] == 2
    assert s["nonconv_kinds"] == {"budget_hit": 1} and s["draft_acceptance_pooled"] == 0.6
    assert s["draft_rows_engaged"] == 2 and s["wall_max_s"] == 7000.0
    assert s["counters"]["verify_blocks_joint_v1"] == 3 and s["counters"]["verify_fallback_reasons"] == {"straddle": 1}


def test_length_ratio_band():
    new = [{"id": "a", "completion_tokens": 130}, {"id": "b", "completion_tokens": 130}]
    ref = [{"id": "a", "completion_tokens": 100}, {"id": "b", "completion_tokens": 100}]
    r = R.length_ratio(new, ref)
    assert r["ratio"] == 1.3 and r["in_band"] is False
    assert R.length_ratio(ref, ref)["in_band"] is True
