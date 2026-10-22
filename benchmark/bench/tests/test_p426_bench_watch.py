"""P426 B5: the 5-minute watcher fails closed on power (plan §2 S8) and follows the P426 file names.

Every tick logs watts / volts / battery; anything but 140 W / 28 V / battery > 20 % — or an unreadable reading — is a POWER
FAIL that stays sticky (a later good tick never hides it) and is written once to a receipt the leg wrapper reads. `--rows-file`
watches an explicit file (vision outputs, the reasoning journal, whose rung records are flattened to draws).
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "m1"))
import bench_watch as W  # noqa: E402

GOOD = {"watts": 140, "volts": 28, "batt": 80}


@pytest.mark.parametrize(
    "reading, ok",
    [
        (GOOD, True),
        (dict(GOOD, watts=96), False),
        (dict(GOOD, volts=20), False),
        (dict(GOOD, batt=20), False),
        (dict(GOOD, batt=None), False),
        (None, False),
    ],
)
def test_power_ok_is_exactly_140_w_28_v_and_battery_above_20(reading, ok):
    assert W.power_ok(reading) is ok


def test_a_power_failure_is_sticky_and_receipted_once(tmp_path):
    receipt = tmp_path / "power.json"
    state = W.PowerState(receipt)
    assert "POWER ok" in state.tick(GOOD, at="10:00:00")
    bad = state.tick(dict(GOOD, watts=96), at="10:05:00")
    assert "POWER FAIL" in bad and "ACT" in bad
    later = state.tick(GOOD, at="10:10:00")
    assert "POWER FAIL (sticky since 10:05:00)" in later
    doc = json.loads(receipt.read_text())
    assert doc == {"first_failure_at": "10:05:00", "reading": dict(GOOD, watts=96)}
    state.tick(None, at="10:15:00")
    assert json.loads(receipt.read_text())["first_failure_at"] == "10:05:00"


def test_rows_file_overrides_the_tune_path(tmp_path):
    f = tmp_path / "vision_gate.p426-off-b1.jsonl"
    f.write_text("\n".join(json.dumps({"id": i, "wall_s": 1.0}) for i in "ab") + "\n")
    rep, n, *_ = W.assess("m", "vision_gate", 10, None, 0, [], rows_file=f)
    assert n == 2 and "n=2/10" in rep


def test_a_reasoning_journal_is_flattened_to_draws(tmp_path):
    f = tmp_path / "reasoning.p426-on-b1.partial.jsonl"
    rec = {"ctx": 128000, "rows": [{"wall_s": 400.0, "converged": True}] * 3}
    f.write_text(json.dumps({"key": "k", "record": rec}) + "\n")
    rep, n, *_ = W.assess("m", "reasoning", 3, None, 0, [], rows_file=f)
    assert n == 3


def test_flat_escalation_is_configurable(tmp_path):
    f = tmp_path / "x.jsonl"
    f.write_text(json.dumps({"id": "a", "wall_s": 1.0}) + "\n")
    rep, _, flat, _ = W.assess("m", "b", 5, 1, 2, [], rows_file=f, flat_escalate=8)
    assert flat == 3 and "INVESTIGATE" not in rep
    rep, *_ = W.assess("m", "b", 5, 1, 2, [], rows_file=f)
    assert "INVESTIGATE" in rep


def test_cli_takes_the_p426_options():
    a = W._parse_args(
        ["--models", "m", "--bench", "b", "--total", "1", "--driver-pattern", "x", "--out", "o",
         "--rows-file", "r.jsonl", "--power-receipt", "p.json", "--flat-escalate", "8"]
    )
    assert (a.rows_file, a.power_receipt, a.flat_escalate) == ("r.jsonl", "p.json", 8)
