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
import os
import signal
import subprocess
import sys

import pytest

import bench.generate as G


# --------------------------------------------------------------------------- orphan-shell sweep
def pytest_sessionfinish(session, exitstatus):
    """20th cold review round 20 (HIGH, box stability): 71 orphaned `/bin/bash --login`
    processes (ppid 1, no tty, 4-13h old, 15-43% CPU EACH, load average 92) were found
    accumulated on the live box -- real-bash `PersistentShell` test shells left behind whenever a
    pytest run was killed, alarmed, or a test raised before `close()`, slowing MLX decode 2-3x on
    the live arms. `test_agentbench_adapter.py`'s own per-test autouse fixture
    (`_killpg_leaked_real_shells`) is the first line of defence; THIS hook is the session-wide
    backstop for anything that escapes it (a shell built outside that module's `_real_shell()`
    helper, or a process whose per-test cleanup itself never ran because the whole worker
    process was signalled). Scope is deliberately narrow and SAFE: only DIRECT children of THIS
    pytest process (`ppid == os.getpid()`), command exactly containing both `bash` and
    `--login` -- never a system-wide sweep, so a live chain's own worktree processes elsewhere on
    the box are never touched. A leak found here is a TEST BUG, not expected load: it kills the
    survivor(s) AND fails the session loudly (nonzero exit) so the leak shows up as a CI/test
    failure instead of silent box load -- see also `scripts/sweep_orphan_shells.sh` for the
    external, system-wide (ppid==1) backstop this hook does not attempt to replace."""
    pid = os.getpid()
    try:
        out = subprocess.run(["ps", "-eo", "pid=,ppid=,command="],
                              capture_output=True, text=True, timeout=10).stdout
    except Exception:  # noqa: BLE001 -- best-effort; never let the sweep itself break the run
        return
    killed = []
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        cpid_s, ppid_s, command = parts
        try:
            cpid, ppid = int(cpid_s), int(ppid_s)
        except ValueError:
            continue
        if ppid != pid or cpid == pid:
            continue
        if "bash" not in command or "--login" not in command:
            continue
        try:
            os.killpg(cpid, signal.SIGKILL)
        except Exception:  # noqa: BLE001
            try:
                os.kill(cpid, signal.SIGKILL)
            except Exception:  # noqa: BLE001
                pass
        killed.append((cpid, command))
    if killed:
        print(f"\n[conftest] pytest_sessionfinish: killed {len(killed)} leaked real-bash "
              f"PersistentShell process(es) still alive as direct children of this pytest "
              f"session (test bug, not expected load): {killed}", file=sys.stderr)
        session.exitstatus = 1


# --------------------------------------------------------------------------- M58 scan pin
@pytest.fixture
def pin_mtp_scan(monkeypatch):
    """OPT-IN (M58): `assert_serving_state` refuses an unresolved `mtp_verify_scan`, and tests that
    drive synthetic model names no registry declares cannot resolve it. Such a test requests this
    fixture (or `pytestmark = pytest.mark.usefixtures("pin_mtp_scan")`), which resolves ONLY the
    "unresolved" outcome to the default. The production refusal is active in every other test."""
    import bench.provenance as P
    real = P.registry_mtp_verify_scan

    def tolerant(model, registry_path=None, worker_lookup=P._DEFAULT_LOOKUP):
        out = real(model, registry_path, worker_lookup)
        if out["mtp_verify_scan"] == "unknown":
            return {"mtp_verify_scan": "per_query", "mtp_verify_scan_source": "registry"}
        return out

    monkeypatch.setattr(P, "registry_mtp_verify_scan", tolerant)


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
                    peak_mem_gb=20.0, wall_s=1.0, finish_reason="stop", raw_timings=None):
    """A COMPLETE `Driver.complete` return value (different shape from probe_result: it adds
    prefill_s/prefill_tps; raw_timings passes the server timings block through — since
    2026-08-23 it carries the speculative engagement counters)."""
    return {"content": content, "reasoning": reasoning, "tool_calls": tool_calls or [],
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "decode_tps": decode_tps, "prefill_s": prefill_s, "prefill_tps": prefill_tps,
            "peak_mem_gb": peak_mem_gb, "wall_s": wall_s, "finish_reason": finish_reason,
            "raw_timings": raw_timings or {}}


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


# --------------------------------------------------------------------------- M50 served-config
@pytest.fixture(autouse=True)
def _m50_router_matches_registry(monkeypatch, tmp_path):
    """M50 (2026-09-28): every driver refuses to run unless the process owning the router port serves
    the driver's `paths.registry_path()`. Unit tests have no router, so by default the owner lookup
    reports a fake router serving exactly that registry. Tests OF the tripwire pass `lookup=` or
    re-patch `provenance.router_owner` explicitly."""
    import bench.provenance as P
    from bench import paths

    def _fake_owner(port):
        return {"pid": 4242, "cmdline": "python mlx-serve start", "cwd": str(tmp_path),
                "env": {"MLX_SERVE_CONFIG": str(paths.registry_path())}}
    monkeypatch.setattr(P, "_real_router_owner", P.router_owner, raising=False)  # for tests OF it
    monkeypatch.setattr(P, "router_owner", _fake_owner)
    monkeypatch.setattr(P, "_LAST_VERIFIED", {})   # the entry-verified block never leaks across tests


# --------------------------------------------------------------------------- STACK_WORKDIR guard
# 10th cold review (live-pilot finding, between-arms fix 2): a test-suite run wrote INTO the
# operator's REAL $STACK_WORKDIR (m54/transcripts/m/{m2,m7,m18}.json, from a test using model
# name "m" with no per-test STACK_WORKDIR redirection reaching that code path). GLOBAL safety
# net: wrap the REAL paths.stack_workdir so that whatever it resolves to (env var, config.sh, or
# a test's own LATER monkeypatch/monkeypatch.setenv) must be `tmp_path` or a path under it -- any
# other result fails the test LOUDLY instead of quietly writing into the operator's real workdir.
@pytest.fixture(autouse=True)
def _guard_stack_workdir_confined_to_tmp_path(monkeypatch, tmp_path):
    from bench import paths
    real_stack_workdir = paths.stack_workdir

    def _guarded(*, required: bool = True):
        result = real_stack_workdir(required=required)
        if result is not None:
            try:
                result.resolve().relative_to(tmp_path.resolve())
            except ValueError:
                pytest.fail(
                    f"paths.stack_workdir() resolved to {result!r}, which is NOT under this "
                    f"test's tmp_path ({tmp_path!r}) -- a test must NEVER write to the "
                    "operator's real STACK_WORKDIR. Monkeypatch STACK_WORKDIR (env) or "
                    "paths.stack_workdir to redirect under tmp_path before exercising any code "
                    "path that calls it.", pytrace=False)
        return result
    monkeypatch.setattr(paths, "stack_workdir", _guarded)
