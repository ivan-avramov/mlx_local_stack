"""`p475_kv.run` (contract "Run control"): ABBA order, idle gap, INVALID stops, replacements (R13), NOT_STARTED retries (R14), a refusing
preflight (R15), the instability rule -> one deciding block (R16), resume. Every test drives the whole `run` through the fake Ops."""
import json

import pytest

from . import helpers as H
from .fakes import ARMS, GOOD_POWER, FakeOps, arm_lower

BLOCK1 = list(ARMS)
BLOCK2 = list(reversed(ARMS))


@pytest.fixture
def w(tmp_path, monkeypatch):
    w = H.world(tmp_path, monkeypatch)
    H.ready(w)
    return w


def legs(w):
    """Names of the legs that STARTED (a stack was built; NOT_STARTED excluded), in start order: the canonical receipts by write
    time (a leg that is INVALID before its driver has no driver, so the driver out-tags alone would miss it)."""
    rows = [(p.stat().st_mtime_ns, p.parent.name) for p in (w.wd / "p475/legs").glob("*/receipt.json")
            if json.loads(p.read_text())["verdict"] != "NOT_STARTED"]
    return [name for _, name in sorted(rows)]


def arm_blocks(w):
    import re
    out = []
    for name in legs(w):
        m = re.match(r"u4-(.+?)-b(\d+)\.a\d+$", name)
        out.append((next(a for a in ARMS if a.lower() == m.group(1)), int(m.group(2))))
    return out


def expected_names(order, block):
    return [f"u4-{arm_lower(a)}-b{block}.a1" for a in order]


# ------------------------------------------------------------------------------------------- order, names, idle
def test_a_clean_run_is_abba_in_twelve_legs_and_exits_zero(w):
    # class: exercises new behaviour (block 1 N16 -> TQ4-OFF; block 2 the reverse)
    assert H.run_all(w) == 0
    assert legs(w) == expected_names(BLOCK1, 1) + expected_names(BLOCK2, 2)


def test_every_leg_of_a_clean_run_has_a_valid_receipt_and_a_dossier(w):
    # class: exercises new behaviour
    H.run_all(w)
    rcs = H.receipts(w)
    assert len(rcs) == 12 and all(r["verdict"] == "VALID" and r["speed_valid"] is True for r in rcs.values())
    assert all(H.dossier(w, n).is_dir() for n in rcs)


def test_a_clean_run_writes_the_canonical_matrix_not_the_partial(w):
    # class: exercises new behaviour (R20)
    H.run_all(w)
    assert H.matrix_path(w).is_file() and not H.matrix_path(w, partial=True).exists()


def test_the_idle_gap_runs_from_the_end_of_each_leg(w):
    # class: exercises new behaviour (R8, resolution P10: >= 600 s from the previous leg's HARVEST completion, i.e. from the
    # `LAST_LEG_END` it wrote; the fake clock moves only by sleep / wait and `now()` carries a 1 ms-per-call jitter, hence 0.5 s of slack)
    H.run_all(w)
    stacks = [k["t"] for e, k in w.events if e == "stack"]
    stops = [k["t"] for e, k in w.events if e == "stop_stack"]
    assert len(stacks) == 12 == len(stops)
    for start, prev_stop in zip(stacks[1:], stops[:-1]):
        assert start - prev_stop >= 600.0 - 0.5


def test_a_run_never_starts_a_leg_while_another_is_up(w):
    # class: exercises new behaviour (one resident model, serial legs)
    H.run_all(w)
    depth = 0
    for e, _ in w.events:
        depth += (e == "stack") - (e == "stop_stack")
        assert 0 <= depth <= 1


def test_the_smoke_run_is_n16_then_tq4_and_writes_no_matrix(w):
    # class: exercises new behaviour (v1.2: `u4-n16-smoke.a<n>` then `u4-tq4-smoke.a<n>`)
    assert H.run_all(w, smoke=True) == 0
    assert legs(w) == ["u4-n16-smoke.a1", "u4-tq4-smoke.a1"]
    assert not list((w.main / "benchmark/results/p475").glob("MATRIX*"))


# ------------------------------------------------------------------------------------------- INVALID stops the run
def test_an_invalid_leg_stops_the_run_with_a_nonzero_exit(w):
    # class: exercises new behaviour
    w.kv_text = lambda arm, n: "" if n == 2 else None
    assert H.run_all(w) != 0
    assert legs(w) == ["u4-n16-b1.a1", "u4-af8-b1.a1"]
    assert not H.matrix_path(w).exists()


def test_the_invalid_leg_is_not_replaced_or_retried(w):
    # class: exercises new behaviour
    w.kv_text = lambda arm, n: "" if n == 3 else None
    H.run_all(w, max_replacements=9, max_not_started=9)
    assert [n for n in legs(w) if "tq8" in n] == ["u4-tq8-b1.a1"]


# ------------------------------------------------------------------------------------------- R13: replacements
def speed_bad(arm_n):
    return lambda arm, n: "power_fail" if (arm, n) in arm_n else "ok"


def test_a_speed_invalid_leg_is_replaced_after_the_blocks_ordered_legs(w):
    # class: exercises new behaviour (R13: queued after the block, block order preserved)
    w.watch_mode = speed_bad({("AF4", 4)})
    assert H.run_all(w) == 0
    got = legs(w)
    assert got[:6] == expected_names(BLOCK1, 1)
    assert got[6] == "u4-af4-b1.a2"
    assert got[7:] == expected_names(BLOCK2, 2)


def test_the_speed_invalid_leg_stays_as_evidence_and_the_replacement_is_the_reported_one(w):
    # class: exercises new behaviour
    w.watch_mode = speed_bad({("AF4", 4)})
    H.run_all(w)
    rcs = H.receipts(w)
    assert rcs["u4-af4-b1.a1"]["verdict"] == "VALID" and rcs["u4-af4-b1.a1"]["speed_valid"] is False
    assert rcs["u4-af4-b1.a2"]["speed_valid"] is True
    assert H.dossier(w, "u4-af4-b1.a1").is_dir()
    text = H.matrix_path(w).read_text()
    assert "u4-af4-b1.a1" in text, "the replaced leg is listed"


def test_a_replacement_that_is_itself_speed_invalid_is_replaced_again_within_the_cap(w):
    # class: exercises new behaviour
    w.watch_mode = speed_bad({("AF4", 4), ("AF4", 7)})
    assert H.run_all(w) == 0
    assert legs(w)[6:8] == ["u4-af4-b1.a2", "u4-af4-b1.a3"]


def test_the_replacement_cap_is_the_option(w):
    # class: exercises new behaviour (R13: --max-replacements explicit; cap 1, two speed-invalid legs -> the second is not replaced)
    w.watch_mode = speed_bad({("AF4", 4), ("AF8", 2)})
    rc = H.run_all(w, max_replacements=1)
    assert rc != 0
    assert len([n for n in legs(w) if n.endswith(".a2")]) == 1
    assert not H.matrix_path(w).exists() and H.matrix_path(w, partial=True).is_file()


def test_a_zero_cap_means_no_replacement_at_all(w):
    # class: exercises new behaviour (boundary)
    w.watch_mode = speed_bad({("AF4", 4)})
    assert H.run_all(w, max_replacements=0) != 0
    assert not [n for n in legs(w) if n.endswith(".a2")]


def test_replacement_counts_are_monotonic_across_a_resume(w):
    # class: reproduces a failure the contract fixes (R13: caps monotonic on resume; a reset would grant a fresh allowance)
    w.watch_mode = speed_bad({("AF4", 4), ("AF8", 2)})
    assert H.run_all(w, max_replacements=1) != 0
    n = len(w.stacks)
    w.watch_mode = "ok"
    H.run_all(w, max_replacements=1)
    started_again = [x for x in legs(w)[n:] if x.endswith((".a2", ".a3"))]
    assert started_again == [], "the one replacement the cap allows was already spent"


# ------------------------------------------------------------------------------------------- R14: NOT_STARTED
def first_refusal_only(w):
    """Power is bad until the first receipt exists, i.e. exactly the first pre-check refuses."""
    return lambda cur: dict(GOOD_POWER, watts=96.0) if not list((w.wd / "p475/legs").glob("*/receipt.json")) else dict(GOOD_POWER)


def test_a_not_started_leg_is_retried_after_its_own_idle(w):
    # class: exercises new behaviour (R14)
    w.power_val = first_refusal_only(w)
    assert H.run_all(w) == 0
    rcs = H.receipts(w)
    assert rcs["u4-n16-b1.a1"]["verdict"] == "NOT_STARTED" and rcs["u4-n16-b1.a2"]["verdict"] == "VALID"
    assert sum(k["s"] for e, k in w.events if e == "sleep" and k["t"] <= w.events[w.index("stack")][1]["t"]) >= 600


def test_a_not_started_leg_is_never_evidence(w):
    # class: exercises new behaviour (R14)
    w.power_val = first_refusal_only(w)
    H.run_all(w)
    assert not H.dossier(w, "u4-n16-b1.a1").exists()
    assert [d.tag for d in w.drivers].count("p475-u4-n16-b1.a1") == 0


def test_a_not_started_leg_is_listed_in_the_matrix(w):
    # class: exercises new behaviour (R20: replaced, refused and NOT_STARTED legs listed)
    w.power_val = first_refusal_only(w)
    H.run_all(w)
    assert "u4-n16-b1.a1" in H.matrix_path(w).read_text()


def test_a_persistent_refusal_is_bounded_by_max_not_started(w):
    # class: exercises new behaviour (R14: the bound is the option)
    w.power_val = dict(GOOD_POWER, watts=96.0)
    assert H.run_all(w, max_not_started=2) != 0
    n = len(H.receipts(w))
    assert 2 <= n <= 3 and w.stacks == []
    assert all(r["verdict"] == "NOT_STARTED" for r in H.receipts(w).values())


def test_each_not_started_retry_waits_its_own_idle(w):
    # class: exercises new behaviour (R14)
    w.power_val = dict(GOOD_POWER, watts=96.0)
    H.run_all(w, max_not_started=2)
    assert sum(k["s"] for e, k in w.events if e == "sleep") >= 600.0 * (len(H.receipts(w)) - 1)


# ------------------------------------------------------------------------------------------- R15: refusing preflight
def test_a_persistently_refusing_arm_is_marked_and_the_rest_run(tmp_path, monkeypatch):
    # class: exercises new behaviour (R15)
    w = H.world(tmp_path, monkeypatch)
    ops = FakeOps(w)
    assert H.prepare(w, ops) == []
    w.preflight_plan["AF8"] = ["refuse"] * 9
    for a in ARMS:
        assert H.preflight_ok(w, a, ops=ops) is (a != "AF8")
    rc = H.run_all(w, ops=ops)
    assert rc != 0
    assert "af8" not in "".join(legs(w))
    assert {a for a, _ in arm_blocks(w)} == set(ARMS) - {"AF8"}
    assert not H.matrix_path(w).exists() and H.matrix_path(w, partial=True).is_file()
    assert "AF8" in H.matrix_path(w, partial=True).read_text()


# ------------------------------------------------------------------------------------------- R16: instability -> deciding block
def b3(w):
    return [(a, b) for a, b in arm_blocks(w) if b == 3]


def test_a_stable_run_has_no_deciding_block(w):
    # class: exercises new behaviour
    H.run_all(w)
    assert b3(w) == []


def test_a_direction_reversal_triggers_one_deciding_block(w):
    # class: exercises new behaviour (AF8 decode ratio vs N16: 0.9975 in block 1, 1.0024 in block 2)
    w.metric_override = {("AF8", 1): {"dts": 39.9}, ("AF8", 2): {"dts": 42.1}}
    assert H.run_all(w) == 0
    got = [a for a, _ in b3(w)]
    assert {"N16", "AF8"} <= set(got)
    assert got == [a for a in BLOCK1 if a in got], "the deciding block is in block-1 order"


def test_a_spread_beyond_half_the_distance_from_one_triggers(w):
    # class: exercises new behaviour (r1 = 0.95, r2 = 0.972: spread 0.022 > |mean - 1| / 2 = 0.0195)
    w.metric_override = {("AF8", 2): {"dts": 0.972 * 42.0}}
    H.run_all(w)
    assert ("AF8", 3) in b3(w)


def test_a_small_spread_does_not_trigger(w):
    # class: exercises new behaviour (r1 = 0.95, r2 = 0.969: spread 0.019 <= 0.0203; same direction)
    w.metric_override = {("AF8", 2): {"dts": 0.969 * 42.0}}
    H.run_all(w)
    assert b3(w) == []


def test_the_deciding_block_runs_once_even_if_still_unstable(w):
    # class: exercises new behaviour (R16: its own cap, default 1; never a block 4)
    w.metric_override = {("AF8", 1): {"dts": 39.9}, ("AF8", 2): {"dts": 42.1}, ("AF8", 3): {"dts": 30.0}}
    H.run_all(w)
    assert {b for _, b in arm_blocks(w)} == {1, 2, 3}
    assert [a for a, b in arm_blocks(w) if b == 3].count("AF8") == 1


def test_max_deciding_zero_forbids_the_deciding_block(w):
    # class: exercises new behaviour
    w.metric_override = {("AF8", 1): {"dts": 39.9}, ("AF8", 2): {"dts": 42.1}}
    H.run_all(w, max_deciding=0)
    assert b3(w) == []


# ------------------------------------------------------------------------------------------- resume
def test_an_interrupted_run_resumes_without_repeating_a_finished_leg(w):
    # class: exercises new behaviour (resumable from state.json)
    seen = {"n": 0}

    def hook(s):
        seen["n"] += 1
        if seen["n"] == 3:
            raise KeyboardInterrupt

    w.sleep_hook = hook
    with pytest.raises(KeyboardInterrupt):
        H.run_all(w)
    done = len(legs(w))
    assert 2 <= done < 12
    w.sleep_hook = None
    assert H.run_all(w) == 0
    names = legs(w)
    assert len(names) == len(set(names)) == 12
    assert set(names) == set(expected_names(BLOCK1, 1) + expected_names(BLOCK2, 2))
