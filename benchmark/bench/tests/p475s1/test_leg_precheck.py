"""`p475_kv.run_leg` pre-check (contract "Leg lifecycle" step 1): any failure -> receipt NOT_STARTED, nothing started; arm identity (R1);
the lease (R4); the idle gap; destinations absent; the arm's preflight PASS."""
import json

import pytest

from . import helpers as H
from .fakes import FakeOps, GOOD_POWER, PICK, leg_name

STARTED = ("stack", "start_router", "load", "spawn", "start_watch")


@pytest.fixture
def w(tmp_path, monkeypatch):
    w = H.world(tmp_path, monkeypatch)
    H.ready(w)
    return w


def not_started(w, arm="AF8", **kw):
    rec = H.run_leg(w, arm, **kw)
    assert rec["verdict"] == "NOT_STARTED", rec
    assert not [n for n in w.names() if n in STARTED], f"something started: {w.names()}"
    assert rec["speed_valid"] is False
    assert rec["problems"]
    return rec


def test_a_clean_precheck_lets_the_leg_start(w):
    # class: exercises new behaviour
    rec = H.run_leg(w, "AF8")
    assert rec["verdict"] == "VALID", rec
    assert "stack" in w.names()


# ------------------------------------------------------------------------------------------- power
@pytest.mark.parametrize("bad", [dict(watts=96.0), dict(watts=139.0), dict(watts=141.0), dict(volts=20.0), dict(volts=27.0),
                                 dict(battery=20), dict(battery=5)])
def test_power_off_spec_refuses(w, bad):
    # class: exercises new behaviour (140 W / 28 V / battery > 20 %)
    w.power_val = dict(GOOD_POWER, **bad)
    not_started(w)


def test_battery_21_is_enough(w):
    # class: exercises new behaviour (boundary: strictly above 20)
    w.power_val = dict(GOOD_POWER, battery=21)
    assert H.run_leg(w, "AF8")["verdict"] == "VALID"


# ------------------------------------------------------------------------------------------- port / busy / lease (R4)
def test_a_listener_on_8000_refuses(w):
    # class: exercises new behaviour
    w.listener[8000] = 4321
    not_started(w)


@pytest.mark.parametrize("busy", [["77 /x/.venv/bin/mlx_vlm.server --model m"], ["88 uv run opencode run foo"],
                                  ["99 python -m bench.run_capacity --model m"]])
def test_a_busy_process_refuses(w, busy):
    # class: exercises new behaviour (ChainOps BUSY + run_capacity)
    w.busy_list = busy
    rec = not_started(w)
    assert any(b.split()[0] in json.dumps(rec) or "busy" in json.dumps(rec).lower() for b in busy)


def test_a_refused_lease_is_not_started_and_nothing_runs(w):
    # class: exercises new behaviour (R4)
    w.lease_refuse = True
    not_started(w)
    assert "lease_enter" not in w.names()


def test_the_lease_is_held_from_before_the_router_until_after_teardown(w):
    # class: exercises new behaviour (R4: held to teardown, released last)
    H.run_leg(w, "AF8")
    n = w.names()
    assert n.index("lease_enter") < n.index("start_router")
    assert n.index("stop_stack") < n.index("lease_exit")
    assert n.count("lease_enter") == n.count("lease_exit") == 1


def test_the_lease_is_released_when_the_leg_ends_invalid(w):
    # class: exercises new behaviour (R4)
    w.kv_text = ""
    assert H.run_leg(w, "AF8")["verdict"] == "INVALID"
    assert w.names().count("lease_enter") == w.names().count("lease_exit") == 1


# ------------------------------------------------------------------------------------------- idle gap (600 s)
def test_less_than_600s_since_the_p475_leg_end_refuses(w):
    # class: exercises new behaviour
    w.write_last_leg_end("p475", w.epoch - 599.0)
    not_started(w)


def test_600s_since_the_p475_leg_end_passes(w):
    # class: exercises new behaviour
    w.write_last_leg_end("p475", w.epoch - 601.0)
    assert H.run_leg(w, "AF8")["verdict"] == "VALID"


def test_the_later_of_the_two_leg_end_files_counts_p426_recent(w):
    # class: exercises new behaviour (p475 old, p426 recent)
    w.write_last_leg_end("p475", w.epoch - 7200.0)
    w.write_last_leg_end("p426", w.epoch - 300.0)
    not_started(w)


def test_the_later_of_the_two_leg_end_files_counts_p475_recent(w):
    # class: exercises new behaviour (p426 old, p475 recent)
    w.write_last_leg_end("p475", w.epoch - 300.0)
    w.write_last_leg_end("p426", w.epoch - 7200.0)
    not_started(w)


def test_no_leg_end_file_at_all_is_a_clean_start(w):
    # class: exercises new behaviour
    (w.wd / "p475" / "LAST_LEG_END").unlink()
    assert H.run_leg(w, "AF8")["verdict"] == "VALID"


# ------------------------------------------------------------------------------------------- destinations absent
@pytest.mark.parametrize("make", [
    lambda w, leg: (w.main / "benchmark/results/p475" / leg).mkdir(parents=True),
    lambda w, leg: (w.main / "benchmark/results/p475" / f"{leg}.stage").mkdir(parents=True),
    lambda w, leg: (w.wt("AF8") / "benchmark/results" / PICK).mkdir(parents=True) or
    (w.wt("AF8") / "benchmark/results" / PICK / f"capacity_ladder.p475-{leg}.jsonl").write_text("{}\n"),
])
def test_an_existing_destination_refuses(w, make):
    # class: exercises new behaviour (never overwrite a harvested or half-harvested leg)
    leg = leg_name("AF8", 1)
    make(w, leg)
    not_started(w)


# ------------------------------------------------------------------------------------------- preflight PASS
def test_an_arm_without_a_preflight_pass_is_not_started(w):
    # class: exercises new behaviour
    import shutil
    shutil.rmtree(w.wd / "p475" / "preflight")
    not_started(w)


def test_a_preflight_pass_of_another_arm_does_not_count(w):
    # class: exercises new behaviour
    files = sorted((w.wd / "p475" / "preflight").glob("*.json"))
    assert len(files) == 6, [p.name for p in files]                      # one record per arm
    mine = [p for p in files if "af8" in p.name.lower()]
    assert len(mine) == 1
    mine[0].unlink()                                                      # the other five stay
    not_started(w)


def test_a_refused_preflight_leaves_the_arm_not_startable(tmp_path, monkeypatch):
    # class: exercises new behaviour
    w = H.world(tmp_path, monkeypatch)
    ops = FakeOps(w)
    assert H.prepare(w, ops) == []
    w.preflight_plan["AF8"] = ["refuse"] * 3
    assert not H.preflight_ok(w, "AF8")
    not_started(w)


# ------------------------------------------------------------------------------------------- R1 arm identity at entry
def test_a_dirty_arm_worktree_refuses(w):
    # class: exercises new behaviour (R1)
    w.arm_clean["AF8"] = False
    not_started(w)


def test_head_not_the_arm_commit_refuses(w):
    # class: exercises new behaviour (R1)
    w.arm_head["AF8"] = "e" * 40
    not_started(w)


def test_parent_not_the_base_refuses(w):
    # class: exercises new behaviour (R1)
    w.arm_parent["AF8"] = "f" * 40
    not_started(w)


def test_tq4_head_must_be_the_base_itself(w):
    # class: exercises new behaviour (R1: the TQ4 arm is the base commit)
    w.arm_head["TQ4"] = "e" * 40
    not_started(w, "TQ4")


def test_the_tq4_base_commit_passes(w):
    # class: exercises new behaviour (R1)
    assert H.run_leg(w, "TQ4")["verdict"] == "VALID"


@pytest.mark.parametrize("arm", ["N16", "AF8", "TQ8", "AF4", "TQ4-OFF"])
def test_each_arms_own_commit_diff_passes(w, arm):
    # class: exercises new behaviour (R1: the diff is exactly the arm's keys + the PROVISIONAL comment)
    assert H.run_leg(w, arm)["verdict"] == "VALID"


def tamper(arm, old, new):
    """The arm's committed registry with one line changed (the contract's R1: the diff may hold the arm's keys + the comment only)."""
    def apply(w):
        text = w.arm_registry(arm)
        assert old in text, old
        w.arm_registry_override[arm] = text.replace(old, new, 1)
    return apply


@pytest.mark.parametrize("arm,mutate", [
    ("AF8", tamper("AF8", "max_kv_cache_size: 262144", "max_kv_cache_size: 131072")),          # another key of the entry
    ("AF8", tamper("AF8", "quantized_kv_start: 0", "quantized_kv_start: 4096")),               # the R22 start key
    ("AF8", tamper("AF8", "    draft_kind: mtp", "    # draft_kind: mtp")),                    # MTP changed on a non-OFF arm
    ("AF8", tamper("AF8", "top_p: 0.95", "top_p: 0.9")),                                       # generation defaults
    ("TQ4-OFF", tamper("TQ4-OFF", "kv_bits: 4", "kv_bits: 8")),                                # OFF changes only the two MTP lines
    ("AF8", tamper("AF8", "kv_bits: 8", "kv_bits: 4")),                                        # the wrong value for the arm
    ("AF8", tamper("AF8", "kv_quant_scheme: uniform", "kv_quant_scheme: turboquant")),         # AF8 passing as TQ8
    ("N16", tamper("N16", "kv_bits: 0", "kv_bits: 4")),                                        # a quantized arm passing as N16
], ids=["other_key", "start_key", "mtp_changed_on_non_off_arm", "generation_defaults", "off_touches_kv", "wrong_bits",
        "wrong_scheme", "n16_with_bits"])
def test_an_arm_commit_that_changes_more_or_other_than_its_keys_refuses(w, arm, mutate):
    # class: exercises new behaviour (R1)
    mutate(w)
    not_started(w, arm)


def test_an_arm_commit_that_touches_another_file_refuses(w):
    # class: exercises new behaviour (R1: the arm commit's diff is the registry only)
    w.arm_files["AF8"] = ["main_models.yaml", "benchmark/bench/foo.py"]
    not_started(w)


def test_n16_keeps_the_bases_scheme_line_and_removing_it_refuses(w):
    # class: exercises new behaviour (v1.2, Sol P2: N16 = `kv_bits: 0` only; the fork's `--kv-arm` gate and spec v4 keep the scheme)
    text = w.arm_registry("N16")
    assert "kv_quant_scheme: turboquant" in text and "kv_bits: 0" in text
    assert H.run_leg(w, "N16")["verdict"] == "VALID"                       # the arm as the contract defines it passes


def test_an_n16_commit_that_removes_the_scheme_line_refuses(w):
    # class: exercises new behaviour (v1.2: the v1.1 shape of N16 is refused)
    w.arm_registry_override["N16"] = w.arm_registry("N16").replace("    kv_quant_scheme: turboquant\n", "")
    not_started(w, "N16")


@pytest.mark.parametrize("links", [{"src/mlx-vlm": "0" * 40, "src/mlx-serve": "1ddf6f84" + "0" * 32},
                                   {"src/mlx-vlm": "d94e38a9" + "0" * 32, "src/mlx-serve": "0" * 40},
                                   {"src/mlx-vlm": "d94e38a9" + "0" * 32}])
def test_gitlinks_off_the_base_refuse(w, links):
    # class: exercises new behaviour (R1: submodule commits == the base's pins)
    w.arm_gitlinks["AF8"] = links
    not_started(w)


# ------------------------------------------------------------------------------------------- the receipt of a refusal
def test_a_not_started_receipt_is_written_to_the_canonical_path(w):
    # class: exercises new behaviour
    w.arm_clean["AF8"] = False
    rec = not_started(w)
    on_disk = H.read_receipt(w, leg_name("AF8", 1))
    assert on_disk["verdict"] == "NOT_STARTED" and on_disk["problems"] == rec["problems"]


def test_not_started_leaves_no_dossier_and_no_leg_end(w):
    # class: exercises new behaviour (never evidence; the idle clock is not restarted by a refusal)
    before = (w.wd / "p475" / "LAST_LEG_END").read_text()
    w.arm_clean["AF8"] = False
    not_started(w)
    assert not H.dossier(w, leg_name("AF8", 1)).exists()
    assert (w.wd / "p475" / "LAST_LEG_END").read_text() == before
