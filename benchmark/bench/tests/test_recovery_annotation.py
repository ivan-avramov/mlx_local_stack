"""Loop-recovery must ANNOTATE, not silently substitute — and not silently score either.

The original behaviour: when an item failed to converge, `probe_with_recovery` restarted the
router and re-probed ONCE, then returned the SECOND probe as the item's result. That grants an
extra draw selectively to failures, which inflates conv% for exactly the loop-prone models under
investigation — the measurement moves in the direction of the hypothesis being tested.

The obvious fix (score the first probe) trades that for a different error: the first probe is a
KNOWN stale-router artifact, so scoring it puts a corrupted generation into pass@1.

Both are biased, in opposite directions. So: the FIRST probe is the convergence datum (it is what
the model did under the config as it stood), the second is retained under `recovery_probe` for
diagnosis, and the row is flagged `contaminated` so grading can EXCLUDE it from pass@1 with a
reported count. Nothing is silently substituted and nothing known-bad is silently scored.
"""
import bench.convergence as CV
import bench.generate as G

from .conftest import probe_result


def _looping():
    """A non-converged probe whose trace looks like a degenerate repetition loop (which is the
    only case a router restart could plausibly fix)."""
    line = "the value of x is definitely computed here and now\n"
    return probe_result(content="partial", reasoning=line * 40,
                        completion_tokens=17000, finish_reason="stop")


def _clean():
    return probe_result(content="done", completion_tokens=100, finish_reason="stop")


PARAMS = {"thinking_budget": 16384}


def test_no_restart_fn_returns_the_single_probe_unchanged():
    p, recovery, second = G.probe_with_recovery(
        "m", [], PARAMS, probe_fn=lambda *a: _clean(), restart_fn=None)
    assert p["content"] == "done" and recovery is None and second is None


def test_converged_item_never_triggers_a_restart():
    restarts = []
    G.probe_with_recovery("m", [], PARAMS, probe_fn=lambda *a: _clean(),
                          restart_fn=lambda: restarts.append(1))
    assert restarts == []


def test_first_probe_stays_the_datum_and_second_is_nested():
    """The bias fix: a restart-retry must not replace the recorded generation."""
    seq = [_looping(), _clean()]
    p, recovery, second = G.probe_with_recovery(
        "m", [], PARAMS, probe_fn=lambda *a: seq.pop(0), restart_fn=lambda: None)
    assert p["content"] == "partial", "the FIRST probe is the datum"
    assert recovery == "recovered"
    assert second is not None and second["content"] == "done"


def test_persisted_row_marks_contamination_and_keeps_both_probes(monkeypatch, tmp_results):
    import json

    import bench.benchmarks as B
    import bench.client as C

    seq = [_looping(), _clean()]
    monkeypatch.setattr(B, "load", lambda b, lim, seed: [{"id": "i0", "prompt": "p"}])
    monkeypatch.setattr(C, "preload", lambda m, **k: 0.0)
    monkeypatch.setattr(C, "probe", lambda *a, **k: seq.pop(0))
    G.run(["m"], ["aime"], {}, restart_fn=lambda: None,
          overrides={"thinking_budget": 16384})

    row = json.loads(G.result_path("m", "aime").read_text().splitlines()[0])
    assert row["content"] == "partial"                 # first probe recorded
    assert row["converged"] is False
    assert row["recovery"] == "recovered"
    assert row["contaminated"] == "stale_router"
    assert row["recovery_probe"]["completion_tokens"] == 100
    assert row["recovery_probe"]["converged"] is True   # the retry's own verdict, kept separately


def test_a_genuine_budget_hit_is_not_retried():
    """A clean budget-hit is long reasoning, not a stale router. Retrying burns another full
    generation on a slow model for nothing, and would hand a second draw to the very items whose
    convergence is in question."""
    calls = []

    def probe(*a):
        calls.append(1)
        return probe_result(content="x", reasoning="genuine varied reasoning\n" * 3,
                            completion_tokens=17000, finish_reason="stop")

    p, recovery, second = G.probe_with_recovery("m", [], PARAMS, probe_fn=probe,
                                               restart_fn=lambda: None)
    assert recovery == "genuine_nonconvergence"
    assert len(calls) == 1 and second is None


def test_loop_persisting_across_a_restart_is_labelled():
    seq = [_looping(), _looping()]
    p, recovery, second = G.probe_with_recovery(
        "m", [], PARAMS, probe_fn=lambda *a: seq.pop(0), restart_fn=lambda: None)
    assert recovery == "loop_persisted"
    assert CV.is_converged({"finish_reason": p["finish_reason"],
                            "completion_tokens": p["completion_tokens"],
                            "thinking_budget": 16384}) is False


def test_audit_counts_primaries_only(write_rows):
    """conv% must be computed from primary probes, so the recovery path cannot move it."""
    rows = [
        {"id": "a", "sample": 0, "finish_reason": "stop", "completion_tokens": 100,
         "thinking_budget": 16384},
        {"id": "b", "sample": 0, "finish_reason": "stop", "completion_tokens": 17000,
         "thinking_budget": 16384, "contaminated": "stale_router",
         "recovery_probe": {"finish_reason": "stop", "completion_tokens": 100,
                            "thinking_budget": 16384, "converged": True}},
    ]
    audit = CV.audit(rows)
    assert audit["convergence_rate"] == 0.5, \
        "the nested recovery probe must not be counted as a second, converged item"
    assert audit["n_generated"] == 2


def test_generation_row_persists_compressed_trace_and_classification(monkeypatch, tmp_results):
    """The trace itself is dropped (an 82K-token meander would bloat the jsonl ~40x) but the
    head/tail and the repetition/novelty statistics are kept, so a non-convergence can be typed
    offline instead of by re-running the model under a bespoke probe."""
    import json

    import bench.benchmarks as B
    import bench.client as C

    meander = "\n".join(f"step {i}: consider the case where x equals {i} and re-derive it"
                        for i in range(400))
    monkeypatch.setattr(B, "load", lambda b, lim, seed: [{"id": "i0", "prompt": "p"}])
    monkeypatch.setattr(C, "preload", lambda m, **k: 0.0)
    monkeypatch.setattr(C, "probe", lambda *a, **k: probe_result(
        content="ans", reasoning=meander, completion_tokens=17000, finish_reason="stop"))
    G.run(["m"], ["aime"], {}, overrides={"thinking_budget": 16384})

    row = json.loads(G.result_path("m", "aime").read_text().splitlines()[0])
    assert row["reasoning_chars"] == len(meander)
    assert row["truncated"] is True
    assert len(row["reasoning_head"]) <= 4096 and len(row["reasoning_tail"]) <= 4096
    assert row["reasoning_stats"]["ngram8_unique"] > 0.8
    assert row["nonconv_kind"] == "meander", "a budget-hit with high novelty is a meander"
    assert "reasoning" not in row, "the full trace must NOT be persisted"
