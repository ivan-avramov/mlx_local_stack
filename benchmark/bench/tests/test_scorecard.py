from bench.scorecard import capacity_retrieval_scorecard

def _rec(ctx, fp, acc, fits):
    return {"ctx": ctx, "model_footprint_gb": fp, "retrieval_acc": acc, "fits": fits}

def test_full_pass():
    recs = [_rec(160000, 30, 1.0, True), _rec(192000, 33, 1.0, True),
            _rec(224000, 36, 0.8, True), _rec(256000, 40, 0.9, True)]
    sc = capacity_retrieval_scorecard("m", recs)
    assert sc["capacity_gate_pass"] is True
    assert sc["max_fitting_ctx"] == 256000
    # 224K had acc 0.8 (<0.85) but 256K is 0.9 -> effective is the largest passing
    assert sc["retrieval_effective_ctx"] == 256000

def test_gate_fail_midway():
    recs = [_rec(160000, 30, 1.0, True), _rec(192000, 48, 0.0, False)]
    sc = capacity_retrieval_scorecard("m", recs)
    assert sc["capacity_gate_pass"] is False
    assert sc["max_fitting_ctx"] == 160000
    assert sc["retrieval_effective_ctx"] == 160000
