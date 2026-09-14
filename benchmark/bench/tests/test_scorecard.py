from bench.scorecard import capacity_retrieval_scorecard


def test_completed_above_target_retains_coscore():
    rows = [{"ctx": 160000, "server_peak_gb": 30, "retrieval_acc": 1.0},
            {"ctx": 192000, "server_peak_gb": 49, "retrieval_acc": 0.8},
            {"ctx": 256000, "server_peak_gb": 50, "retrieval_acc": 0.9}]
    sc = capacity_retrieval_scorecard("m", rows)
    assert sc["execution_status"] == "completed"
    assert sc["max_completed_ctx"] == 256000
    assert sc["max_within_memory_target_ctx"] == 160000
    assert sc["retrieval_coscore_max_passing_ctx"] == 256000


def test_empty_is_not_completed():
    sc = capacity_retrieval_scorecard("m", [])
    assert sc["execution_status"] == "empty"
    assert sc["max_completed_ctx"] is None
    assert sc["retrieval_coscore_max_passing_ctx"] is None
