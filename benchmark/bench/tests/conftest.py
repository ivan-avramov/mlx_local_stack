"""Shared test fakes and fixtures.

Two things make harness tests silently useless, and both are addressed here.

1. TWO DISTINCT SEAMS, easily conflated. `generate.run` calls the module-level
   `client.probe` through a closure and indexes its result dict directly
   (`p["prompt_tokens"]`, `p["decode_tps"]`, `p["peak_mem_gb"]`, `p["wall_s"]`) inside a bare
   `except Exception` that records an ERROR row. So a fake missing one key does not fail the
   test — it turns every item into an error row and the assertions pass over an empty result
   set. `FakeProbe` therefore mirrors `client.probe`'s shape COMPLETELY. `Driver.complete`
   (used by the ladder runners) has a different shape again — `FakeDriver` mirrors that one,
   and has no `probe` method precisely so the two cannot be swapped by accident.

2. SILENT SCRIPT EXHAUSTION. A fake that keeps returning its last response lets a test assert
   "3 turns happened" when the loop actually ran 12. Both fakes raise `AssertionError` when
   their script runs out.
"""
import json

import pytest

import bench.generate as G


# --------------------------------------------------------------------------- results tree
@pytest.fixture
def tmp_results(tmp_path, monkeypatch):
    """Point the results tree at tmp_path. Patches the module constant (not the env var) so it
    also wins over a stray MLX_BENCH_RESULTS in the operator's shell — see results_root()."""
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    return tmp_path


@pytest.fixture
def write_rows(tmp_results):
    """Write generation rows to results/<model>/<bench>.jsonl and return the path."""
    def _write(model, bench, rows):
        p = G.result_path(model, bench)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return p
    return _write


# --------------------------------------------------------------------------- client.probe seam
def probe_result(content="ok", *, reasoning="", tool_calls=None, completion_tokens=10,
                 prompt_tokens=1, finish_reason="stop", decode_tps=1.0, peak_mem_gb=1.0,
                 wall_s=0.1, raw_timings=None):
    """A COMPLETE `client.probe` return value. Build fakes from this, never from a literal —
    a missing key becomes an error row instead of a test failure (see module docstring)."""
    return {"content": content, "reasoning": reasoning, "tool_calls": tool_calls or [],
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "decode_tps": decode_tps, "peak_mem_gb": peak_mem_gb,
            "finish_reason": finish_reason, "wall_s": wall_s,
            "raw_timings": raw_timings if raw_timings is not None else {}}


class FakeProbe:
    """Scriptable stand-in for `client.probe`. Records every call; refuses to over-serve.

    `script` is a list of probe_result dicts, or callables (model, messages, params) -> dict
    for responses that depend on the request.
    """

    def __init__(self, script=None, default=None):
        self.script = list(script or [])
        self.default = default          # dict -> return for every call once the script is empty
        self.calls = []

    def __call__(self, model, messages, params, timeout=3600, tools=None):
        self.calls.append({"model": model, "messages": messages, "params": dict(params),
                           "timeout": timeout, "tools": tools})
        if self.script:
            nxt = self.script.pop(0)
            return nxt(model, messages, params) if callable(nxt) else dict(nxt)
        if self.default is not None:
            return dict(self.default)
        raise AssertionError(
            f"FakeProbe script exhausted after {len(self.calls)} call(s) — the code under test "
            f"made more requests than the test expected. Lengthen `script` or set `default` "
            f"deliberately.")

    @property
    def n_calls(self):
        return len(self.calls)


# --------------------------------------------------------------------------- Driver seam
def complete_result(content="ok", *, reasoning="", tool_calls=None, prompt_tokens=100,
                    completion_tokens=10, decode_tps=50.0, prefill_s=0.5, prefill_tps=200,
                    peak_mem_gb=20.0, wall_s=1.0, finish_reason="stop"):
    """A COMPLETE `Driver.complete` return value (different shape from probe_result: it adds
    prefill_s/prefill_tps and has no raw_timings)."""
    return {"content": content, "reasoning": reasoning, "tool_calls": tool_calls or [],
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "decode_tps": decode_tps, "prefill_s": prefill_s, "prefill_tps": prefill_tps,
            "peak_mem_gb": peak_mem_gb, "wall_s": wall_s, "finish_reason": finish_reason}


class FakeDriver:
    """Scriptable `Driver`. Deliberately has NO `probe` method: the probe and complete shapes
    differ, and a fake that answers both invites testing against the wrong contract."""

    def __init__(self, script=None, default=None):
        self.script = list(script or [])
        self.default = default
        self.calls = []
        self.preloaded = []

    def preload(self, model, timeout=900):
        self.preloaded.append(model)
        return 1.0

    def complete(self, model, messages, params, timeout=3600, tools=None):
        self.calls.append({"model": model, "messages": messages, "params": dict(params),
                           "tools": tools})
        if self.script:
            nxt = self.script.pop(0)
            return nxt(model, messages, params) if callable(nxt) else dict(nxt)
        if self.default is not None:
            return dict(self.default)
        raise AssertionError(
            f"FakeDriver script exhausted after {len(self.calls)} call(s) — the code under test "
            f"made more turns than the test expected (a silently-repeating fake would let a "
            f"turn-count assertion pass while the real loop ran on).")

    @property
    def n_calls(self):
        return len(self.calls)


def tool_call(name, args, call_id="c1"):
    """An OpenAI-shaped tool call, as the driver returns it. `args` is JSON-encoded because
    that is what real servers send (and _parse_args must cope with both)."""
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


# --------------------------------------------------------------------------- subprocess seam
class FakeRunner:
    """Stand-in for `subprocess.run`. Records argv/env; returns canned results in order."""

    class Proc:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode, self.stdout, self.stderr = returncode, stdout, stderr

    def __init__(self, results=None, default=None):
        self.results = list(results or [])
        self.default = default if default is not None else self.Proc()
        self.calls = []

    def __call__(self, cmd, *a, **kw):
        self.calls.append({"cmd": cmd, "args": a, "kwargs": kw})
        if self.results:
            nxt = self.results.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt
        return self.default

    @property
    def last_cmd(self):
        return self.calls[-1]["cmd"] if self.calls else None


# --------------------------------------------------------------------------- clock seam
class FrozenClock:
    """A monotonic clock that advances only when told. For deadlines and wall-clock metrics:
    a test must never depend on real elapsed time."""

    def __init__(self, start=0.0):
        self.t = float(start)

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += float(seconds)
        return self.t

    def ticking(self, per_call):
        """A clock callable that advances `per_call` seconds on every read — for code that
        measures an interval by calling the clock twice."""
        def _tick():
            now = self.t
            self.t += float(per_call)
            return now
        return _tick


@pytest.fixture
def frozen_clock():
    return FrozenClock()


@pytest.fixture
def fake_runner():
    return FakeRunner()
