"""`await_model_pid` — one seam for the best-effort model-server PID hunt.

Five run_*.py CLIs each inlined the same loop:

    for _ in range(10):
        model_pid = find_model_server_pid()
        if model_pid is not None:
            break
        time.sleep(1)

With no live model server (i.e. in every unit test) that burns the full 10 s, which cost the
suite ~220 s of pure sleeping across ~22 tests. Consolidating it gives one place to test the
retry semantics and one seam for tests to bypass.
"""
import bench.instrument as I


def test_returns_immediately_when_found():
    slept = []
    pid = I.await_model_pid(finder=lambda: 4242, sleeper=slept.append)
    assert pid == 4242
    assert slept == [], "must not sleep when the pid is found on the first look"


def test_retries_then_succeeds():
    seq = [None, None, 99]
    slept = []
    pid = I.await_model_pid(finder=lambda: seq.pop(0), sleeper=slept.append, attempts=5)
    assert pid == 99
    assert slept == [1, 1], "one sleep per failed look, none after the success"


def test_gives_up_and_returns_none():
    slept = []
    pid = I.await_model_pid(finder=lambda: None, sleeper=slept.append, attempts=3)
    assert pid is None
    assert len(slept) == 3


def test_attempts_zero_never_calls_the_finder():
    calls = []

    def finder():
        calls.append(1)
        return 7

    assert I.await_model_pid(finder=finder, sleeper=lambda s: None, attempts=0) is None
    assert calls == []


def test_finder_exception_is_not_fatal():
    """psutil can raise mid-iteration; a best-effort probe must degrade, not kill the run."""
    def finder():
        raise RuntimeError("psutil blew up")

    assert I.await_model_pid(finder=finder, sleeper=lambda s: None, attempts=2) is None
