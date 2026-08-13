"""The determinism probe must call the SAME reproducibility question the Tier-0 anomaly posed.

The anomaly (2026-08-12): two Tier-0 cells with byte-identical params produced 2,941 vs 2,841
completion tokens on a HARDCODED prompt, while three cells differing only in inert knobs were
exactly equal. Every cell that reproduced had tail truncation active; the diverging pair had all
three truncation knobs off. So the probe's job is to make truncation a FACTOR alongside suffix
state -- a probe that holds truncation at the deployed value would reproduce under both suffix
states and falsely exonerate suffix decoding.

These tests pin the properties that make the probe's verdict mean something:
  - it varies truncation, and the OFF cell really is untruncated
  - it sends NO seed (a seed would answer a question nobody asked)
  - it sends presence_penalty 0.0 (nonzero disables suffix = a different serving path)
  - byte-identity is decided on the returned TEXT, not on token counts
"""
import json

import pytest

import bench.probe_determinism as PD


class FakeDriver:
    """Records requests; returns scripted texts so identity/divergence is controllable."""

    def __init__(self, texts):
        self.texts = list(texts)
        self.requests = []
        self.preloaded = []

    def preload(self, model, timeout=900):
        self.preloaded.append(model)
        return 1.0

    def complete(self, model, messages, params, timeout=3600, tools=None):
        self.requests.append({"model": model, "messages": messages, "params": params})
        reasoning, content = self.texts[(len(self.requests) - 1) % len(self.texts)]
        return {"content": content, "reasoning": reasoning,
                "completion_tokens": len(content) + len(reasoning),
                "finish_reason": "stop", "wall_s": 1.0, "decode_tps": 100.0}


IDENTICAL = [("think", "code")]


# ------------------------------------------------------------------ the factor under test
def test_truncation_off_cell_disables_all_three_tail_knobs():
    """If any knob still clips the tail, the cell is not the anomalous config."""
    off = PD.TRUNCATION["off"]
    assert off["top_p"] == 1.0
    assert off["top_k"] == 0
    assert off["min_p"] == 0.0


def test_truncation_on_cell_matches_the_deployed_tail_knobs():
    on = PD.TRUNCATION["on"]
    assert (on["top_p"], on["top_k"]) == (0.95, 20)


def test_probe_runs_both_truncation_states_by_default():
    d = FakeDriver(IDENTICAL)
    out = PD.run_cell(d, "M", "off", reps=2, timeout=10)
    assert out["truncation"] == "off"
    assert len(out["draws"]) == 2


# ------------------------------------------------------------------ request hygiene
def test_no_seed_is_ever_sent():
    """The unseeded path IS the question: it is what every row and every client uses."""
    d = FakeDriver(IDENTICAL)
    PD.run_cell(d, "M", "on", reps=2, timeout=10)
    for r in d.requests:
        assert "seed" not in r["params"]


def test_presence_penalty_is_zero_so_suffix_decoding_stays_engaged():
    """A nonzero presence_penalty trips the fallback -> we would measure a different path."""
    d = FakeDriver(IDENTICAL)
    for state in ("on", "off"):
        PD.run_cell(d, "M", state, reps=1, timeout=10)
    for r in d.requests:
        assert r["params"]["presence_penalty"] == 0.0


def test_thinking_stays_enabled():
    """AGENTS.md: thinking is enabled for ALL tests, never disabled to make one work."""
    d = FakeDriver(IDENTICAL)
    PD.run_cell(d, "M", "on", reps=1, timeout=10)
    assert d.requests[0]["params"]["enable_thinking"] is True


def test_each_rep_gets_its_own_params_dict():
    """A shared dict mutated downstream would silently couple the reps."""
    d = FakeDriver(IDENTICAL)
    PD.run_cell(d, "M", "on", reps=3, timeout=10)
    ids = {id(r["params"]) for r in d.requests}
    assert len(ids) == 3


# ------------------------------------------------------------------ the verdict
def test_identical_text_is_reported_byte_identical():
    d = FakeDriver(IDENTICAL)
    out = PD.run_cell(d, "M", "off", reps=3, timeout=10)
    assert out["byte_identical"] is True
    assert out["distinct_text_signatures"] == 1


def test_differing_text_is_reported_as_divergence():
    d = FakeDriver([("think", "codeA"), ("think", "codeB"), ("think", "codeA")])
    out = PD.run_cell(d, "M", "off", reps=3, timeout=10)
    assert out["byte_identical"] is False
    assert out["distinct_text_signatures"] == 2


def test_divergence_in_reasoning_alone_still_counts():
    """Tier-0 saw reasoning_chars move by 36k. Hashing content only would have missed it."""
    d = FakeDriver([("thinkA", "code"), ("thinkB", "code")])
    out = PD.run_cell(d, "M", "off", reps=2, timeout=10)
    assert out["byte_identical"] is False


def test_equal_token_counts_with_different_text_are_flagged():
    """Tier-0 inferred identity from token counts. This is where that proxy would LIE."""
    d = FakeDriver([("think", "codeA"), ("think", "codeB")])   # same lengths, different bytes
    out = PD.run_cell(d, "M", "off", reps=2, timeout=10)
    assert out["distinct_token_counts"] == 1        # the proxy says "identical"
    assert out["byte_identical"] is False           # the text says otherwise
    assert out["token_count_agrees_with_text"] is False


def test_token_proxy_agreement_is_true_when_it_does_agree():
    d = FakeDriver(IDENTICAL)
    out = PD.run_cell(d, "M", "off", reps=2, timeout=10)
    assert out["token_count_agrees_with_text"] is True


# ------------------------------------------------------------------ output contract
def test_main_writes_a_labelled_result_with_both_cells(tmp_path, monkeypatch):
    d = FakeDriver(IDENTICAL)
    monkeypatch.setattr(PD, "MlxServeDriver", lambda: d)
    out = tmp_path / "det.json"
    rc = PD.main(["--model", "M", "--label", "suffix_off", "--reps", "2",
                  "--out", str(out)])
    assert rc == 0
    got = json.loads(out.read_text())
    assert got["suffix_label"] == "suffix_off"       # provenance of the registry state
    assert got["model"] == "M"
    assert [c["truncation"] for c in got["cells"]] == ["on", "off"]


def test_label_is_required_so_a_result_can_never_be_ambiguous(monkeypatch):
    """A determinism result with no suffix state recorded is uninterpretable."""
    d = FakeDriver(IDENTICAL)
    monkeypatch.setattr(PD, "MlxServeDriver", lambda: d)
    with pytest.raises(SystemExit):
        PD.main(["--model", "M", "--reps", "1"])


def test_uses_the_same_hardcoded_prompt_as_the_tier0_anomaly():
    """The anomaly was on run_convergence's CODING_PROMPT -- a constant string, which is why
    neither cpt nor a task seed can explain the divergence. Reuse it, don't retype it."""
    import bench.run_convergence as RC
    d = FakeDriver(IDENTICAL)
    PD.run_cell(d, "M", "on", reps=1, timeout=10)
    assert d.requests[0]["messages"][0]["content"] == RC.CODING_PROMPT
