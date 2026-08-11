"""The fakes must themselves be trustworthy — a lenient fake makes every test built on it
vacuous. Two properties matter most: probe_result/complete_result are COMPLETE (so a fake never
silently produces error rows), and both fakes REFUSE to over-serve (so turn-count assertions
mean something)."""
import pytest

import bench.client as C
import bench.driver as D
from .conftest import (FakeDriver, FakeProbe, FakeRunner, FrozenClock, complete_result,
                       probe_result, tool_call)


def _returned_keys(fn):
    """The dict keys a function's source constructs in its return value. Crude but effective:
    it makes the fake fail the moment a real seam grows a key. Callers MUST also assert the
    extracted set is non-empty, or the guard passes vacuously."""
    import inspect
    return {line.split('"')[1] for line in inspect.getsource(fn).splitlines()
            if line.strip().startswith('"') and '":' in line}


# --------------------------------------------------------------- completeness vs the real seams
def test_probe_result_covers_every_key_client_probe_returns():
    """If client.probe grows a key, this fails — before a half-built fake starts producing
    error rows that look like passing tests."""
    returned = _returned_keys(C.probe)
    assert len(returned) >= 10, "extraction found nothing — the guard would pass vacuously"
    assert returned <= set(probe_result()), f"probe_result is missing {returned - set(probe_result())}"


def test_complete_result_covers_every_key_driver_complete_returns():
    returned = _returned_keys(D.MlxServeDriver.complete)
    assert len(returned) >= 11, "extraction found nothing — the guard would pass vacuously"
    assert returned <= set(complete_result()), \
        f"complete_result is missing {returned - set(complete_result())}"


def test_the_two_shapes_are_genuinely_different():
    """Guards the reason there are two fakes at all."""
    assert "raw_timings" in probe_result() and "raw_timings" not in complete_result()
    assert "prefill_tps" in complete_result() and "prefill_tps" not in probe_result()
    assert not hasattr(FakeDriver(), "probe"), "FakeDriver must not answer the probe contract"


# --------------------------------------------------------------- script discipline
def test_fake_probe_serves_in_order_and_records():
    fp = FakeProbe([probe_result("a"), probe_result("b")])
    assert fp("m", [], {"temperature": 0.4})["content"] == "a"
    assert fp("m", [], {})["content"] == "b"
    assert fp.n_calls == 2 and fp.calls[0]["params"]["temperature"] == 0.4


def test_fake_probe_raises_when_exhausted():
    fp = FakeProbe([probe_result()])
    fp("m", [], {})
    with pytest.raises(AssertionError, match="script exhausted"):
        fp("m", [], {})


def test_fake_probe_default_serves_indefinitely_when_asked():
    fp = FakeProbe(default=probe_result("z"))
    assert [fp("m", [], {})["content"] for _ in range(3)] == ["z", "z", "z"]


def test_fake_probe_callable_entries_see_the_request():
    fp = FakeProbe([lambda model, msgs, params: probe_result(content=model.upper())])
    assert fp("abc", [], {})["content"] == "ABC"


def test_returned_dicts_are_copies():
    """A test that mutates a response must not corrupt the script for the next call."""
    r = probe_result("a")
    fp = FakeProbe(default=r)
    fp("m", [], {})["content"] = "mutated"
    assert fp("m", [], {})["content"] == "a"


def test_fake_driver_raises_when_exhausted():
    fd = FakeDriver([complete_result()])
    fd.complete("m", [], {})
    with pytest.raises(AssertionError, match="script exhausted"):
        fd.complete("m", [], {})


def test_fake_driver_records_preloads():
    fd = FakeDriver(default=complete_result())
    fd.preload("m")
    assert fd.preloaded == ["m"]


def test_tool_call_arguments_are_json_encoded_like_a_real_server():
    tc = tool_call("read_file", {"path": "a.py"})
    assert tc["function"]["name"] == "read_file"
    assert isinstance(tc["function"]["arguments"], str)


# --------------------------------------------------------------- runner + clock
def test_fake_runner_serves_in_order_then_default():
    fr = FakeRunner([FakeRunner.Proc(1, stderr="boom")])
    assert fr(["a"]).returncode == 1
    assert fr(["b"]).returncode == 0            # default
    assert fr.last_cmd == ["b"] and len(fr.calls) == 2


def test_fake_runner_can_raise_to_simulate_a_missing_binary():
    fr = FakeRunner([FileNotFoundError("docker")])
    with pytest.raises(FileNotFoundError):
        fr(["docker", "run"])


def test_frozen_clock_only_moves_when_told():
    c = FrozenClock(100.0)
    assert c() == 100.0 and c() == 100.0
    c.advance(5)
    assert c() == 105.0


def test_ticking_clock_advances_per_read():
    c = FrozenClock()
    tick = c.ticking(6)
    assert [tick(), tick(), tick()] == [0, 6, 12]
