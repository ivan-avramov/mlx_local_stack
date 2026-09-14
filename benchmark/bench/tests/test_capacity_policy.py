"""C83: numeric memory targets must not become execution or quality verdicts."""
import pytest

from bench import capacity_ladder as ladder
from bench.scorecard import capacity_retrieval_scorecard
from bench.tests.test_capacity_ladder import FakeDriver, FakeSampler, _PARAMS


def test_over_target_and_unknown_peaks_do_not_stop_ladder():
    rows = ladder.run_ladder(
        FakeDriver([46.5, 48.21, None, 47.2]), "m", 1.0, 0, 1, _PARAMS,
        grid=(100, 200, 300, 400), sampler_factory=FakeSampler)
    assert len(rows) == 4
    assert [r["within_memory_target"] for r in rows] == [True, False, None, True]
    assert all(r["execution_status"] == "completed" for r in rows)
    assert all(r["retrieval_acc"] == 1.0 for r in rows)
    assert all("fits" not in r for r in rows)


def test_transport_failure_is_unscored_and_stops():
    class Broken:
        def complete(self, *args, **kwargs):
            raise RuntimeError("HTTP 500")
    rows = ladder.run_ladder(Broken(), "m", 1.0, 0, 1, _PARAMS,
                             grid=(100, 200), sampler_factory=FakeSampler)
    assert len(rows) == 1
    assert rows[0]["execution_status"] == "error"
    assert rows[0]["retrieval_acc"] is None
    assert rows[0]["within_memory_target"] is None
    assert rows[0]["error_kind"] == "request_error"


def test_scorecard_retrieval_independent_of_target_and_preserves_input():
    rows = [{"ctx": 196608, "server_peak_gb": 45, "retrieval_acc": 1., "fits": True},
            {"ctx": 262144, "server_peak_gb": 48.21, "retrieval_acc": 1., "fits": False}]
    sc = capacity_retrieval_scorecard("m", rows)
    assert sc["schema_version"] == 2
    assert sc["max_completed_ctx"] == 262144
    assert sc["max_within_memory_target_ctx"] == 196608
    assert sc["retrieval_coscore_max_passing_ctx"] == 262144
    assert "capacity_gate_pass" not in sc
    assert "retrieval_effective_ctx" not in sc
    assert sc["records"] == rows  # historical flags remain historical


def test_error_and_missing_measurement_are_not_memory_passes():
    rows = [{"ctx": 100, "server_peak_gb": None, "retrieval_acc": 1.},
            {"ctx": 200, "server_peak_gb": 40, "retrieval_acc": 0., "error": "timeout"}]
    sc = capacity_retrieval_scorecard("m", rows)
    assert sc["max_completed_ctx"] == 100
    assert sc["max_within_memory_target_ctx"] is None
    assert sc["retrieval_coscore_max_passing_ctx"] == 100
    assert sc["execution_status"] == "error"


@pytest.mark.parametrize("peak", [float("nan"), float("inf"), -1])
def test_invalid_memory_is_unknown(peak):
    rows = ladder.run_ladder(FakeDriver([peak]), "m", 1., 0, 1, _PARAMS,
                             grid=(100,), sampler_factory=FakeSampler)
    assert rows[0]["within_memory_target"] is None


@pytest.mark.parametrize('payload', [{}, {'error': {'message': 'failed'}},
                                    {'content': '', 'prompt_tokens': 10,
                                     'completion_tokens': 0, 'finish_reason': None}])
def test_malformed_completion_is_unscored_error(payload):
    class Driver:
        def complete(self, *args, **kwargs):
            return payload
    rows = ladder.run_ladder(Driver(), 'm', 1., 0, 1, _PARAMS,
                             grid=(100, 200), sampler_factory=FakeSampler)
    assert len(rows) == 1
    assert rows[0]['execution_status'] == 'error'
    assert rows[0]['retrieval_acc'] is None


@pytest.mark.parametrize('peak', [True, False, 0])
def test_nonmeasurement_is_not_a_memory_pass(peak):
    from bench.scorecard import within_memory_target
    assert within_memory_target(peak) is None


def test_invalid_telemetry_can_be_serialized_as_standard_json():
    import json
    rows = ladder.run_ladder(FakeDriver([float('nan')]), 'm', 1., 0, 1, _PARAMS,
                             grid=(100,), sampler_factory=FakeSampler)
    assert rows[0]['server_peak_gb'] is None
    assert rows[0]['memory_telemetry_note']
    json.dumps(rows, allow_nan=False)


def test_nonfinite_timing_is_unscored_and_aborts():
    class Driver(FakeDriver):
        def complete(self, *a, **kw):
            out = super().complete(*a, **kw)
            out['decode_tps'] = float('nan')
            return out
    rows = ladder.run_ladder(Driver([40., 40.]), 'm', 1., 0, 1, _PARAMS,
                             grid=(100, 200), sampler_factory=FakeSampler)
    assert len(rows) == 1
    assert rows[0]['execution_status'] == 'error'
    assert rows[0]['retrieval_acc'] is None


def test_invalid_peak_alias_from_real_driver_remains_unknown():
    class Driver(FakeDriver):
        def complete(self, *a, **kw):
            out = super().complete(*a, **kw)
            out['raw_timings'] = {'peak_memory': float('nan'), 'draft_kind': 'mtp', 'draft_n': 2}
            return out
    rows = ladder.run_ladder(Driver([float('nan'), 40.]), 'm', 1., 0, 1, _PARAMS,
                             grid=(100, 200), sampler_factory=FakeSampler)
    assert len(rows) == 2
    assert rows[0]['execution_status'] == 'completed'
    assert rows[0]['within_memory_target'] is None
