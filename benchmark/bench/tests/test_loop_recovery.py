"""Tests for generate.probe_with_recovery — auto-restart-on-loop, repsig-gated.

A non-converged item is only worth a router-restart retry if its thinking trace looks like a
DEGENERATE repetition loop (which a fresh router may clear — the stale-router cause). A clean
budget-hit (genuine long reasoning that didn't finish) won't be helped by a restart and would
just double the cost on a slow model, so it's flagged 'genuine_nonconvergence' and NOT retried.
If a loop is retried: converges on the fresh router -> 'recovered' (stale-router state);
loops again -> 'loop_persisted' (genuine quant/model loop).

The retry is DIAGNOSTIC ONLY. `probe_with_recovery` returns (primary, recovery, secondary) with
`primary` always the FIRST probe: returning the retry as the datum would grant an extra draw
selectively to failures and inflate conv% for the loop-prone models under investigation. See
test_recovery_annotation.py for the full argument and the contamination flag.
"""
import bench.generate as G

LOOP = "\n".join(["this is the same repeated reasoning line, over and over again"] * 40)
GENUINE = "\n".join(f"distinct reasoning step number {i}, with its own unique content here"
                    for i in range(60))


def _p(finish, ct, reasoning=""):
    return {"finish_reason": finish, "completion_tokens": ct, "content": "x", "reasoning": reasoning}


def test_converged_first_no_restart():
    calls = {"restart": 0, "probe": 0}

    def probe_fn(m, msg, p):
        calls["probe"] += 1
        return _p("stop", 1000)

    def restart_fn():
        calls["restart"] += 1

    p, rec, retry = G.probe_with_recovery("m", [], {"thinking_budget": 16384},
                                          probe_fn=probe_fn, restart_fn=restart_fn)
    assert rec is None and retry is None
    assert calls["restart"] == 0 and calls["probe"] == 1


def test_loop_then_recovered():
    seq = iter([_p("stop", 17000, LOOP), _p("stop", 3000, GENUINE)])  # loop, then converge
    calls = {"restart": 0, "preload": 0}

    p, rec, retry = G.probe_with_recovery(
        "m", [], {"thinking_budget": 16384},
        probe_fn=lambda *_: next(seq),
        restart_fn=lambda: calls.__setitem__("restart", calls["restart"] + 1),
        preload_fn=lambda m: calls.__setitem__("preload", calls["preload"] + 1))
    assert rec == "recovered"
    assert calls["restart"] == 1 and calls["preload"] == 1
    assert p["completion_tokens"] == 17000, "the FIRST (looped) probe stays the datum"
    assert retry["completion_tokens"] == 3000, "the recovered retry is returned separately"


def test_loop_persists_on_fresh_router():
    seq = iter([_p("stop", 17000, LOOP), _p("stop", 16500, LOOP)])  # loops both times -> genuine
    p, rec, retry = G.probe_with_recovery("m", [], {"thinking_budget": 16384},
                                          probe_fn=lambda *_: next(seq),
                                          restart_fn=lambda: None)
    assert rec == "loop_persisted"
    assert p["completion_tokens"] == 17000 and retry["completion_tokens"] == 16500


def test_genuine_budget_hit_is_not_retried():
    # conv=False (ct >= budget) but the trace is genuine long reasoning, not a loop ->
    # a restart wouldn't help (it'd just burn another ~full generation). Flag, don't retry.
    calls = {"restart": 0, "probe": 0}

    def probe_fn(m, msg, p):
        calls["probe"] += 1
        return _p("stop", 80000, GENUINE)

    p, rec, retry = G.probe_with_recovery(
        "m", [], {"thinking_budget": 16384}, probe_fn=probe_fn,
        restart_fn=lambda: calls.__setitem__("restart", calls["restart"] + 1))
    assert rec == "genuine_nonconvergence"
    assert calls["restart"] == 0 and calls["probe"] == 1   # NOT re-run
    assert p["completion_tokens"] == 80000 and retry is None


def test_no_restart_fn_means_no_recovery():
    p, rec, retry = G.probe_with_recovery("m", [], {"thinking_budget": 16384},
                                          probe_fn=lambda *_: _p("stop", 17000, LOOP),
                                          restart_fn=None)
    assert rec is None and retry is None
    assert p["completion_tokens"] == 17000   # looped result returned as-is
