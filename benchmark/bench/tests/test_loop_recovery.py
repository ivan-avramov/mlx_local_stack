"""Tests for generate.probe_with_recovery — auto-restart-on-loop.

If an item loops/truncates mid-run it may be the creeping stale-router state. The harness
restarts the router + re-probes ONCE: if it now converges the loop was stale-router state
(``recovered``); if it loops AGAIN on a fresh router it's a genuine quant/model loop
(``loop_persisted``). This auto-distinguishes the two root causes we found.
"""
import bench.generate as G


def _p(finish, ct):
    return {"finish_reason": finish, "completion_tokens": ct, "content": "x"}


def test_converged_first_no_restart():
    calls = {"restart": 0, "probe": 0}

    def probe_fn(m, msg, p):
        calls["probe"] += 1
        return _p("stop", 1000)

    def restart_fn():
        calls["restart"] += 1

    p, rec = G.probe_with_recovery("m", [], {"thinking_budget": 16384},
                                   probe_fn=probe_fn, restart_fn=restart_fn)
    assert rec is None
    assert calls["restart"] == 0 and calls["probe"] == 1


def test_loop_then_recovered():
    seq = iter([_p("stop", 17000), _p("stop", 3000)])   # loop, then converge after restart
    calls = {"restart": 0, "preload": 0}

    p, rec = G.probe_with_recovery(
        "m", [], {"thinking_budget": 16384},
        probe_fn=lambda *_: next(seq),
        restart_fn=lambda: calls.__setitem__("restart", calls["restart"] + 1),
        preload_fn=lambda m: calls.__setitem__("preload", calls["preload"] + 1))
    assert rec == "recovered"
    assert calls["restart"] == 1 and calls["preload"] == 1
    assert p["completion_tokens"] == 3000


def test_loop_persists_on_fresh_router():
    seq = iter([_p("stop", 17000), _p("stop", 16500)])  # loops both times -> genuine
    p, rec = G.probe_with_recovery("m", [], {"thinking_budget": 16384},
                                   probe_fn=lambda *_: next(seq),
                                   restart_fn=lambda: None)
    assert rec == "loop_persisted"
    assert p["completion_tokens"] == 16500


def test_no_restart_fn_means_no_recovery():
    p, rec = G.probe_with_recovery("m", [], {"thinking_budget": 16384},
                                   probe_fn=lambda *_: _p("stop", 17000),
                                   restart_fn=None)
    assert rec is None
    assert p["completion_tokens"] == 17000   # looped result returned as-is
