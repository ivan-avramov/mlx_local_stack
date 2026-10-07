"""C136 (operator, 2026-10-07): the progress gate's first-write allowance is denominated in TOKENS, not
seconds. Two flat 300 s ticks were a wall-clock cap on time-to-first-write (~13-14K tokens at pick 1's
24 tok/s) that scored long single-turn thinking as a stall and gave faster setups more tokens before the
cut. The v2 probe converts a fixed allowance (default 16000 tokens) into a per-model window from the
documented draft-OFF decode rate in benchmark/decode_rates.json: tick_s = ceil(tokens / (2 * rate)),
stall after 2 flat ticks (= the window), loop detection at 3 identical ticks, hard ceiling unchanged."""
from __future__ import annotations
import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import run_opencode_probe_v2 as P2  # noqa: E402

PICK1 = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
PICK2 = "Qwen3.8-27B-mlx-uniform-4bit"


def test_rate_table_entries_carry_positive_rates_and_sources():
    doc = json.loads(P2.DECODE_RATES.read_text())
    assert set(doc["models"]) >= {PICK1, PICK2}
    for name, entry in doc["models"].items():
        assert entry["tok_s"] > 0 and "campaign-results" in entry["source"], name


@pytest.mark.parametrize("model,rate", [(PICK1, 24.2), (PICK2, 25.4)])
def test_window_is_token_denominated_per_model(model, rate):
    w = P2._gate_window(model, 16000, None)
    assert w["tick_s"] == math.ceil(16000 / (2 * rate))
    assert w["stall_ticks"] == 2
    assert w["first_write_tokens"] == 16000
    assert w["decode_tok_s"] == rate
    assert abs(w["first_write_window_s"] - 2 * w["tick_s"]) < 2
    assert "campaign-results" in w["decode_tok_s_source"]


def test_faster_model_gets_the_same_tokens_not_the_same_seconds():
    a, b = P2._gate_window(PICK1, 16000, None), P2._gate_window(PICK2, 16000, None)
    assert a["tick_s"] > b["tick_s"]                      # slower decode -> longer window
    assert abs(a["tick_s"] * a["decode_tok_s"] - b["tick_s"] * b["decode_tok_s"]) < 2 * max(a["decode_tok_s"], b["decode_tok_s"])


def test_unknown_model_refuses_without_an_explicit_tick():
    with pytest.raises(SystemExit, match="REFUSED: no documented draft-OFF decode rate"):
        P2._gate_window("no-such-model", 16000, None)


def test_explicit_tick_overrides_and_is_recorded_as_manual():
    w = P2._gate_window("no-such-model", 16000, 300)
    assert w["tick_s"] == 300 and w["decode_tok_s"] is None
    assert w["decode_tok_s_source"] == "manual:--tick-s"


def test_identity_includes_the_allowance_and_rate():
    for key in ("first_write_tokens", "decode_tok_s"):
        assert key in P2.RESUME_IDENTITY_KEYS_V2


def test_pick2_rate_is_the_in_situ_measurement_not_the_short_context_screen():
    """2026-10-07: the M36 short-context screen's 28.7 tok/s overstated pick 2's decode under agentic load
    (in-situ s1 median 25.4 over 51 requests of >= 500 tokens; 22.5 at >= 15K context), so its window
    allowed ~14K tokens vs pick 1's ~16K and all eight of its s1 misses were stalls."""
    entry = json.loads(P2.DECODE_RATES.read_text())["models"][PICK2]
    assert entry["tok_s"] == 25.4
    assert "in-situ" in entry["source"] and "M59 s1" in entry["source"]
    assert P2._gate_window(PICK2, 16000, None)["tick_s"] == 315
