"""M35: DeepSeek Harness (dsh) headless adapter (`run_dsh_probe.py`), a second agentic scaffold
beside opencode.

Box-free per AGENTS.md — the GPU is busy serving a live benchmark on :8000, so NOTHING here ever
sends a request there. Unit tests below never spawn a subprocess or talk to a network. The single
integration test spawns the REAL pinned `@deepseek-ai/dsh@0.1.2-rc.1` binary (installed under
`$STACK_WORKDIR/dsh`, per the M35 spec's install recipe) against a throwaway fake OpenAI-compatible
HTTP server on a random localhost port — never :8000, never a real model.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # benchmark/ on sys.path
import run_dsh_probe as P


# --------------------------------------------------------------------------- _stack_workdir / _dsh_bin

def test_dsh_bin_defaults_under_stack_workdir(monkeypatch):
    monkeypatch.delenv("DSH_BIN", raising=False)
    monkeypatch.setenv("STACK_WORKDIR", "$STACK_WORKDIR")  # allow-pii-pattern
    assert P._dsh_bin() == Path("$STACK_WORKDIR/dsh/node_modules/.bin/dsh")  # allow-pii-pattern


def test_dsh_bin_honors_override_env(monkeypatch):
    monkeypatch.setenv("DSH_BIN", "/somewhere/else/dsh")
    assert P._dsh_bin() == Path("/somewhere/else/dsh")


def test_stack_workdir_missing_exits(monkeypatch):
    monkeypatch.delenv("STACK_WORKDIR", raising=False)
    monkeypatch.delenv("DSH_BIN", raising=False)
    with pytest.raises(SystemExit):
        P._dsh_bin()


# --------------------------------------------------------------------------- version pin refusal

def test_dsh_version_check_reads_dash_v(monkeypatch):
    captured = {}

    def _fake_check_output(cmd, **kw):
        captured["cmd"] = cmd
        return "0.1.2-rc.1\n"
    monkeypatch.setattr(subprocess, "check_output", _fake_check_output)

    v = P._dsh_version(Path("/x/dsh"))
    assert v == "0.1.2-rc.1"
    assert captured["cmd"] == ["/x/dsh", "--version"]


def test_dsh_version_check_failure_refuses_to_run_unversioned(monkeypatch):
    def _boom(cmd, **kw):
        raise FileNotFoundError("no dsh")
    monkeypatch.setattr(subprocess, "check_output", _boom)

    with pytest.raises(SystemExit):
        P._dsh_version(Path("/x/dsh"))


def test_main_refuses_version_drift_without_the_escape_hatch(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv",
                        ["run_dsh_probe.py", "--model", "m", "--tune", "t0.5", "--items", "x"])
    monkeypatch.setattr(P, "_dsh_bin", lambda: Path("/x/dsh"))
    monkeypatch.setattr(P, "_dsh_version", lambda b: "9.9.9")
    with pytest.raises(SystemExit) as e:
        P.main()
    assert "9.9.9" in str(e.value) and P.PINNED_DSH_VERSION in str(e.value)


# --------------------------------------------------------------------------- _dsh_env

def test_dsh_env_redirects_home_and_sets_provider_and_safety_vars(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    home = tmp_path / "dsh-home"
    env = P._dsh_env(home, "http://127.0.0.1:12345/v1")

    assert env["HOME"] == str(home)
    assert env["XDG_CONFIG_HOME"] == str(home / ".config")
    assert env["XDG_DATA_HOME"] == str(home / ".local/share")
    assert env["XDG_CACHE_HOME"] == str(home / ".cache")
    assert env["DEEPSEEK_BASE_URL"] == "http://127.0.0.1:12345/v1"
    assert env["DEEPSEEK_API_KEY"] == "local"
    assert env["DSH_TELEMETRY_MODE"] == "DISABLED"
    assert env["DSH_PERMISSION_MODE"] == "danger-full-access"
    # M1: DEEPSEEK_SEARCH_BASE_URL is a SEPARATE hard default (web_search's own base URL, not
    # covered by DEEPSEEK_BASE_URL) -- must be redirected off the real DeepSeek endpoint too.
    assert env["DEEPSEEK_SEARCH_BASE_URL"] != "https://api.deepseek.com/anthropic/v1"
    assert "127.0.0.1" in env["DEEPSEEK_SEARCH_BASE_URL"]
    # the redirect target itself must exist for dsh to write into
    assert home.is_dir()


def test_dsh_env_inherits_path_from_the_caller(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/some/marker/bin:/usr/bin")
    env = P._dsh_env(tmp_path / "h", "http://127.0.0.1:1/v1")
    assert env["PATH"] == "/some/marker/bin:/usr/bin"


def test_dsh_env_hardcodes_api_key_ignoring_caller_env(tmp_path, monkeypatch):
    """L5: this probe only ever talks to a fake or local router, never DeepSeek's real API -- a
    real DEEPSEEK_API_KEY sitting in the caller's environment (e.g. exported for other tooling)
    must NEVER be forwarded into this subprocess or its logs."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-a-real-looking-secret")  # allow-pii-pattern
    env = P._dsh_env(tmp_path / "h", "http://127.0.0.1:1/v1")
    assert env["DEEPSEEK_API_KEY"] == "local"


# --------------------------------------------------------------------------- _write_model_patch

def test_write_model_patch_overrides_agent_default_model(tmp_path):
    patch = P._write_model_patch(tmp_path, "Qwen3.8-27B-mlx-uniform-4bit")
    text = patch.read_text()
    assert patch.parent == tmp_path
    assert "id: agent-default-model" in text
    assert "provider: deepseek-official" in text
    assert "model: Qwen3.8-27B-mlx-uniform-4bit" in text


def test_write_model_patch_disables_web_and_subagent_and_ralph_tools(tmp_path):
    """M1: web_search/web_fetch (network egress against public exercises) and
    subagent/subagent_fork/ralph (parallel LLM fan-out against the single-worker router) must be
    turned off in the SAME overlay that sets the model."""
    patch = P._write_model_patch(tmp_path, "some-model")
    text = patch.read_text()
    for tool_id in ("tool-web", "tool-subagent", "tool-subagent-fork", "tool-ralph"):
        assert f"id: {tool_id}" in text
    assert text.count("disabled: true") == len(P._DISABLED_TOOL_IDS)


# --------------------------------------------------------------------------- _ProcGroup

class _FakePopen:
    def __init__(self, pid=4242):
        self.pid = pid
        self.returncode = None
        self.waited = False

    def poll(self):
        return self.returncode

    def wait(self, *a, **kw):
        self.waited = True
        return self.returncode


def test_procgroup_kill_targets_the_process_group(monkeypatch):
    calls = []
    monkeypatch.setattr(P.os, "getpgid", lambda pid: 9999)
    monkeypatch.setattr(P.os, "killpg", lambda pgid, sig: calls.append((pgid, sig)))
    wrapped = P._ProcGroup(_FakePopen(pid=4242))

    wrapped.kill()

    assert calls == [(9999, P.signal.SIGKILL)]


def test_procgroup_kill_swallows_process_lookup_error(monkeypatch):
    def _boom(pid):
        raise ProcessLookupError()
    monkeypatch.setattr(P.os, "getpgid", _boom)
    wrapped = P._ProcGroup(_FakePopen())

    wrapped.kill()  # must not raise


def test_procgroup_delegates_poll_wait_returncode():
    fake = _FakePopen()
    fake.returncode = 0
    wrapped = P._ProcGroup(fake)
    assert wrapped.poll() == 0
    assert wrapped.returncode == 0
    wrapped.wait()
    assert fake.waited is True


# --------------------------------------------------------------------------- _run_dsh (Popen fake)

def _mkfiles(tmp_path, sol_text="def add(a, b):\n    pass\n", test_text="def test_x(): pass\n"):
    scratch = tmp_path / "scratch"
    work = scratch / "work"
    work.mkdir(parents=True)
    sol = work / "sol.py"
    test = work / "sol_test.py"
    sol.write_text(sol_text)
    test.write_text(test_text)
    return work, sol, test


class _FakePopenCompletesImmediately:
    def __init__(self, cmd, cwd=None, env=None, stdout=None, stderr=None, text=None,
                start_new_session=None):
        self.cmd, self.cwd, self.env = cmd, cwd, env
        self.pid = 1
        if stdout is not None:
            stdout.write("fake dsh ran and exited\n")
            stdout.flush()
        self.returncode = None

    def poll(self):
        self.returncode = 0
        return self.returncode

    def wait(self, *a, **kw):
        return self.returncode


def test_run_dsh_writes_the_model_patch_and_targets_the_base_url(tmp_path, monkeypatch):
    captured = {}

    class _Capturing(_FakePopenCompletesImmediately):
        def __init__(self, cmd, **kw):
            captured["cmd"] = cmd
            captured["env"] = kw.get("env")
            captured["cwd"] = kw.get("cwd")
            captured["start_new_session"] = kw.get("start_new_session")
            super().__init__(cmd, **kw)

    monkeypatch.setattr(P.subprocess, "Popen", _Capturing)
    work, sol, test = _mkfiles(tmp_path)

    rc, log, dur, result, session_log = P._run_dsh(
        Path("/x/dsh"), "served-model", work, "do the thing", sol, test,
        lambda w, t: (True, ""), sol.read_text(),
        base_url="http://127.0.0.1:9/v1", dsh_home=tmp_path / "home",
        tick_s=300, hard_ceiling_s=3600, poll_s=1.0, stall_ticks=2, loop_repeats=3)

    assert rc == 0
    assert "fake dsh ran and exited" in log
    assert result.stop_reason == "completed"
    cmd = captured["cmd"]
    assert cmd[0] == "/x/dsh"
    assert cmd[1:3] == ["--profile", "headless"]
    assert "--patch" in cmd
    patch_path = Path(cmd[cmd.index("--patch") + 1])
    assert patch_path.exists()
    assert "served-model" in patch_path.read_text()
    assert cmd[-1] == "do the thing"
    assert captured["env"]["DEEPSEEK_BASE_URL"] == "http://127.0.0.1:9/v1"
    assert captured["env"]["HOME"] == str(tmp_path / "home")
    assert captured["cwd"] == work
    assert captured["start_new_session"] is True


class _FakePopenNeverExits:
    def __init__(self, cmd, cwd=None, env=None, stdout=None, stderr=None, text=None,
                start_new_session=None):
        self.pid = 1
        self.returncode = None
        self.killed_pgid = None
        if stdout is not None:
            stdout.write("fake dsh still running...\n")
            stdout.flush()

    def poll(self):
        return self.returncode

    def wait(self, *a, **kw):
        return self.returncode


def test_run_dsh_stalls_and_kills_the_process_group(tmp_path, monkeypatch):
    monkeypatch.setattr(P.subprocess, "Popen", _FakePopenNeverExits)
    killed = []
    monkeypatch.setattr(P.os, "getpgid", lambda pid: 555)
    monkeypatch.setattr(P.os, "killpg", lambda pgid, sig: killed.append((pgid, sig)))
    work, sol, test = _mkfiles(tmp_path)

    def grade(w, t):
        raise AssertionError("nothing ever changes in this test — grade must not be called")

    t0 = time.time()
    rc, log, dur, result, session_log = P._run_dsh(
        Path("/x/dsh"), "m", work, "do the thing", sol, test, grade, sol.read_text(),
        base_url="http://127.0.0.1:9/v1", dsh_home=tmp_path / "home",
        tick_s=0.05, hard_ceiling_s=5.0, poll_s=0.01, stall_ticks=2, loop_repeats=3)
    wall = time.time() - t0

    assert result.stop_reason == "stalled"
    assert wall < 3.0
    assert killed == [(555, P.signal.SIGKILL)]


def test_run_dsh_wires_the_session_log_aware_snapshot_fn(tmp_path, monkeypatch):
    """H2 wiring check: `_run_dsh` must drive the progress gate through `_dsh_snapshot_fn` (the
    session-log-aware wrapper), not the stock opencode `_tick_snapshot_fn` directly."""
    monkeypatch.setattr(P.subprocess, "Popen", _FakePopenNeverExits)
    monkeypatch.setattr(P.os, "getpgid", lambda pid: 1)
    monkeypatch.setattr(P.os, "killpg", lambda pgid, sig: None)
    work, sol, test = _mkfiles(tmp_path)
    dsh_home = tmp_path / "home"
    calls = []

    def _fake_snapshot_fn(cwd, sol_, test_, before, grade, log_path, home):
        calls.append((cwd, sol_, test_, before, log_path, home))

        def _snap(elapsed_s):
            return P.progress_gate.Tick(elapsed_s=elapsed_s, n_failing=0, solution_hash="h",
                                        signature=f"sig{elapsed_s}", file_changed=True)
        return _snap

    monkeypatch.setattr(P, "_dsh_snapshot_fn", _fake_snapshot_fn)

    rc, log, dur, result, session_log = P._run_dsh(
        Path("/x/dsh"), "m", work, "task", sol, test, lambda w, t: (True, ""), sol.read_text(),
        base_url="http://127.0.0.1:9/v1", dsh_home=dsh_home,
        tick_s=0.05, hard_ceiling_s=0.2, poll_s=0.01, stall_ticks=2, loop_repeats=3)

    assert result.stop_reason == "hard_ceiling"
    assert calls, "the fake snapshot fn was never called -- _run_dsh did not wire it in"
    assert calls[0][0] == work
    assert calls[0][5] == dsh_home


# --------------------------------------------------------------------------- CLI language gate (mirrors opencode)

def test_unsupported_lang_exits_with_clear_message(monkeypatch):
    monkeypatch.setattr(sys, "argv",
                        ["run_dsh_probe.py", "--model", "m", "--tune", "t0.5", "--items", "x",
                         "--lang", "cobol"])
    with pytest.raises(SystemExit) as e:
        P.main()
    msg = str(e.value)
    assert "cobol" in msg
    assert "unsupported" in msg


# --------------------------------------------------------------------------- H1: transport escalation

def test_escalate_transport_failure_raises_naming_base_url_and_log(monkeypatch):
    log = "some reasoning\ndsh: TRANSPORT: DeepSeek API request to http://x/v1 failed\n"
    with pytest.raises(SystemExit) as e:
        P._escalate_transport_failure(1, log, "http://x/v1")
    msg = str(e.value)
    assert "http://x/v1" in msg
    assert "TRANSPORT" in msg


def test_escalate_transport_failure_does_not_fire_on_success():
    log = "some reasoning\ndsh: TRANSPORT: this text is here but rc is 0\n"
    P._escalate_transport_failure(0, log, "http://x/v1")  # must not raise


def test_escalate_transport_failure_does_not_fire_on_unrelated_errors():
    log = "dsh: SOME_OTHER_ERROR: the model did something else wrong\n"
    P._escalate_transport_failure(1, log, "http://x/v1")  # must not raise


# --------------------------------------------------------------------------- H2: session-log-based signature

def _mk_session_log(dsh_home: Path, content: str = "event1\n") -> Path:
    session_dir = dsh_home / ".dsh/sessions/proj/session-abc"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_file = session_dir / "session.jsonl"
    session_file.write_text(content)
    return session_file


def test_dsh_session_log_signature_changes_as_the_log_grows(tmp_path):
    dsh_home = tmp_path / "home"
    session_file = _mk_session_log(dsh_home)
    sig1 = P._dsh_session_log_signature(dsh_home)
    session_file.write_text(session_file.read_text() + "event2\n")
    sig2 = P._dsh_session_log_signature(dsh_home)
    assert sig1 != sig2


def test_dsh_session_log_signature_stable_when_nothing_grows(tmp_path):
    dsh_home = tmp_path / "home"
    _mk_session_log(dsh_home)
    assert P._dsh_session_log_signature(dsh_home) == P._dsh_session_log_signature(dsh_home)


def test_dsh_session_log_signature_handles_missing_dir_gracefully(tmp_path):
    sig = P._dsh_session_log_signature(tmp_path / "nonexistent")
    assert isinstance(sig, str) and sig


def test_dsh_snapshot_signature_tracks_growing_session_log_and_never_false_loops(tmp_path):
    """THE H2 regression test. dsh writes NOTHING to stdout/stderr while streaming (measured), so
    the stock opencode tick signature (a hash of the log tail) is constant every tick; feeding a
    real `ProgressGate` a sequence of ticks built that way would report 'looping' at tick 3
    regardless of genuine progress. `_dsh_snapshot_fn` must key the signature off the growing
    session log instead, so a genuinely progressing session (file changes every tick) is never
    falsely killed."""
    work, sol, test = _mkfiles(tmp_path)
    log_path = work / ".dsh_probe_log.txt"
    log_path.write_text("")  # dsh writes nothing to stdout while streaming (measured 2026-09-05)
    dsh_home = tmp_path / "home"
    session_file = _mk_session_log(dsh_home)

    def grade(w, t):
        return True, "ok"

    snap = P._dsh_snapshot_fn(work, sol, test, sol.read_text(), grade, log_path, dsh_home)
    gate = P.progress_gate.ProgressGate(stall_ticks=2, loop_repeats=3)

    for i in range(1, 6):
        sol.write_text(f"changed {i}")
        session_file.write_text(session_file.read_text() + f"event{i}\n")
        tick = snap(300.0 * i)
        reason = gate.observe(tick)
        assert reason is None, (
            f"tick {i}: false stop {reason!r} — the stock stdout-tail signature would have "
            f"reported 'looping' by now despite genuine, ongoing progress")


def test_dsh_snapshot_still_stops_a_genuinely_wedged_session(tmp_path):
    """The other half of H2: a session whose session log ALSO stops growing (a real stall, not
    just a quiet stdout) must still be stopped — the fix must not turn the gate into a no-op."""
    work, sol, test = _mkfiles(tmp_path)
    log_path = work / ".dsh_probe_log.txt"
    log_path.write_text("")
    dsh_home = tmp_path / "home"
    _mk_session_log(dsh_home)  # never touched again below -- a genuinely flat session log

    def grade(w, t):
        raise AssertionError("solution never changes — must not grade")

    snap = P._dsh_snapshot_fn(work, sol, test, sol.read_text(), grade, log_path, dsh_home)
    gate = P.progress_gate.ProgressGate(stall_ticks=2, loop_repeats=3)

    reasons = [gate.observe(snap(300.0 * i)) for i in range(1, 5)]
    assert any(r is not None for r in reasons), (
        "a wedged session (file AND session log both flat) must still stop somehow")


# --------------------------------------------------------------------------- M3: shared-implementation identity

def test_row_assembly_uses_scrub_then_tail_not_the_broken_slice_then_scrub_order():
    """M2 call-site regression guard, dsh side (mirrors the same check added for opencode)."""
    import inspect
    src = inspect.getsource(P.main)
    assert "_scrub_then_tail(tail, 300)" in src
    assert "_scrub_then_tail(log, 500)" in src
    assert "_scrub_pii(tail[-300:])" not in src
    assert "_scrub_pii(log[-500:])" not in src


def test_integrity_machinery_is_the_opencode_implementation_by_identity():
    """An inlined copy of any of these would silently drift from opencode's (already-hardened)
    behavior and fail loudly here instead of in some future audit."""
    import run_opencode_probe as _oc
    assert P._prepare is _oc._prepare
    assert P._solution_and_test is _oc._solution_and_test
    assert P._grade_result is _oc._grade_result
    assert P._tick_snapshot_fn is _oc._tick_snapshot_fn
    assert P._scrub_pii is _oc._scrub_pii
    assert P._scrub_then_tail is _oc._scrub_then_tail
    assert P._scratch_dir is _oc._scratch_dir


# --------------------------------------------------------------------------- L1: default --out and dedup

def test_default_out_path_includes_the_tune_label(monkeypatch, tmp_path):
    poly = tmp_path / "polyglot"
    ex = poly / "python/exercises/practice/affine-cipher"
    ex.mkdir(parents=True)
    (ex / "affine_cipher.py").write_text("def encode(): ...\n")
    (ex / "affine_cipher_test.py").write_text("def test_encode(): assert True\n")

    monkeypatch.setattr(P, "_polyglot_root", lambda: poly)
    monkeypatch.setattr(P, "_dsh_bin", lambda: Path("/x/dsh"))
    monkeypatch.setattr(P, "_dsh_version", lambda b: P.PINNED_DSH_VERSION)

    def _fake_run_dsh(dsh_bin, model, cwd, prompt, sol, test, grade, before, **kw):
        return (0, "", 1.0,
                P.progress_gate.GateResult(stop_reason="completed", ticks=[], elapsed_s=1.0,
                                           returncode=0),
                None)

    monkeypatch.setattr(P, "_run_dsh", _fake_run_dsh)
    # Point REPO at tmp_path so the default --out path (never given here, on purpose) is
    # verified WITHOUT ever writing under the real repo tree.
    monkeypatch.setattr(P, "REPO", tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "run_dsh_probe.py", "--model", "some-model", "--tune", "t0.7",
        "--items", "affine-cipher", "--dsh-home", str(tmp_path / "home"),
    ])

    rc = P.main()

    assert rc == 0
    expected = tmp_path / "benchmark/results/some-model/dsh.t0.7.jsonl"
    assert expected.exists()


def test_main_skips_items_already_present_in_the_output_file(tmp_path, monkeypatch):
    """L1: a retried/resumed invocation, or a duplicate name in --items, must not write a second
    row for the same item id."""
    poly = tmp_path / "polyglot"
    ex = poly / "python/exercises/practice/affine-cipher"
    ex.mkdir(parents=True)
    (ex / "affine_cipher.py").write_text("def encode(): ...\n")
    (ex / "affine_cipher_test.py").write_text("def test_encode(): assert True\n")

    monkeypatch.setattr(P, "_polyglot_root", lambda: poly)
    monkeypatch.setattr(P, "_dsh_bin", lambda: Path("/x/dsh"))
    monkeypatch.setattr(P, "_dsh_version", lambda b: P.PINNED_DSH_VERSION)

    calls = []

    def _fake_run_dsh(dsh_bin, model, cwd, prompt, sol, test, grade, before, **kw):
        calls.append(1)
        return (0, "", 1.0,
                P.progress_gate.GateResult(stop_reason="completed", ticks=[], elapsed_s=1.0,
                                           returncode=0),
                None)

    monkeypatch.setattr(P, "_run_dsh", _fake_run_dsh)

    out = tmp_path / "out.jsonl"
    out.write_text(json.dumps({"id": "python/affine-cipher", "passed": True}) + "\n")

    monkeypatch.setattr(sys, "argv", [
        "run_dsh_probe.py", "--model", "m", "--tune", "t0.5",
        "--items", "affine-cipher,affine-cipher", "--out", str(out),
        "--dsh-home", str(tmp_path / "home"),
    ])

    rc = P.main()

    assert rc == 0
    assert calls == [], "an already-present item must never re-invoke _run_dsh"
    lines = [ln for ln in out.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1, "no duplicate row may be appended"


# =================================================================================================
# INTEGRATION: real pinned dsh headless against a fake OpenAI-compatible server. Network-free
# (127.0.0.1 only), never touches :8000, never loads a model.
# =================================================================================================

def _dsh_available() -> bool:
    try:
        b = P._dsh_bin()
    except SystemExit:
        return False
    return b.exists()


pytestmark_skip_no_dsh = pytest.mark.skipif(
    not _dsh_available(), reason="dsh not installed under $STACK_WORKDIR/dsh (see M35 spec install recipe)")


class _ScriptedDeepSeekHandler(BaseHTTPRequestHandler):
    """Content-keyed scripted responder — NOT a raw per-request counter. dsh fires a parallel
    session-title LLM call (no `tools` field on that request) alongside the main agent-loop call;
    a global counter assigns that call the wrong scripted turn (found live, 2026-09-05: the title
    call intercepted the 'write' turn and the agent's own turn saw the 'final text' turn early,
    so the file was never written despite the run exiting 0). Keying off `n_tool_results` in the
    conversation instead of a raw counter is immune to that interleaving.
    """
    target_path: str = ""
    new_content: str = ""
    seen_tool_names: list = None  # set to a real list on the subclass to capture wire tool names
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep pytest -s output quiet
        pass

    def _sse(self, chunks) -> bytes:
        out = [f"data: {json.dumps(c)}\n\n" for c in chunks]
        out.append("data: [DONE]\n\n")
        return "".join(out).encode()

    def do_GET(self):
        if self.path.startswith("/v1/models"):
            body = json.dumps({"object": "list", "data": [{"id": "test-model", "object": "model"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        req = json.loads(raw)
        messages = req.get("messages", [])
        has_tools = bool(req.get("tools"))
        n_tool_results = sum(1 for m in messages if m.get("role") == "tool")
        if self.seen_tool_names is not None:
            self.seen_tool_names.extend(
                t["function"]["name"] for t in req.get("tools", []) if "function" in t)

        if not has_tools:
            chunks = [
                {"choices": [{"delta": {"content": "Task"}}]},
                {"choices": [{"delta": {}, "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}},
            ]
        elif n_tool_results == 0:
            chunks = [
                {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                    "function": {"name": "read", "arguments": ""}}]}}]},
                {"choices": [{"delta": {"tool_calls": [{"index": 0,
                    "function": {"arguments": json.dumps({"file_path": self.target_path})}}]}}]},
                {"choices": [{"delta": {}, "finish_reason": "tool_calls"}],
                 "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
            ]
        elif n_tool_results == 1:
            chunks = [
                {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_2", "type": "function",
                    "function": {"name": "write", "arguments": ""}}]}}]},
                {"choices": [{"delta": {"tool_calls": [{"index": 0,
                    "function": {"arguments": json.dumps({"file_path": self.target_path,
                                                          "content": self.new_content})}}]}}]},
                {"choices": [{"delta": {}, "finish_reason": "tool_calls"}],
                 "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
            ]
        else:
            chunks = [
                {"choices": [{"delta": {"content": "Done."}}]},
                {"choices": [{"delta": {}, "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
            ]

        body = self._sse(chunks)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytestmark_skip_no_dsh
def test_real_dsh_headless_edits_a_file_disables_risky_tools_and_stays_out_of_real_home(tmp_path, monkeypatch):
    stack_workdir = os.environ.get("STACK_WORKDIR")
    if not stack_workdir:
        pytest.skip("STACK_WORKDIR not set")

    # cwd = dsh's sandboxed workspace root (no --dir flag to fight, unlike opencode).
    work = tmp_path / "work"
    work.mkdir()
    sol = work / "sol.py"
    sol.write_text("def add(a, b):\n    pass\n")
    test = work / "sol_test.py"
    test.write_text("from sol import add\ndef test_add():\n    assert add(2, 3) == 5\n")
    before = sol.read_text()
    new_content = "def add(a, b):\n    return a + b\n"

    seen_tool_names = []
    handler = type("Handler", (_ScriptedDeepSeekHandler,), {
        "target_path": str(sol), "new_content": new_content, "seen_tool_names": seen_tool_names,
    })
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    real_home = Path(os.path.expanduser("~"))
    marker = tmp_path / "marker"
    marker.write_text("x")
    before_home_mtimes = {
        p: p.stat().st_mtime_ns for p in real_home.glob("*")
        if p.name not in (".Trash",)  # noqa: avoid permission-denied noise on unrelated entries
    }

    dsh_home = tmp_path / "dsh-home"  # NOT the real $HOME, NOT $STACK_WORKDIR/dsh/home (test isolation)
    try:
        rc, log, dur, result, session_log = P._run_dsh(
            P._dsh_bin(), "test-model", work,
            "Implement add() in sol.py so it returns a + b", sol, test,
            lambda w, t: (True, ""), before,
            base_url=f"http://127.0.0.1:{port}/v1", dsh_home=dsh_home,
            tick_s=300, hard_ceiling_s=60, poll_s=0.2, stall_ticks=2, loop_repeats=3)
    finally:
        server.shutdown()
        thread.join(timeout=5)

    assert rc == 0, log[-2000:]
    assert result.stop_reason == "completed"
    assert sol.read_text() == new_content, "the file did not land — see log:\n" + log[-2000:]

    # nothing written under the real $HOME's top-level entries changed.
    after_home_mtimes = {
        p: p.stat().st_mtime_ns for p in real_home.glob("*")
        if p.name not in (".Trash",)
    }
    assert after_home_mtimes.keys() == before_home_mtimes.keys(), (
        "dsh created a new entry directly under the real $HOME — this is the M35 blocker "
        f"condition. Before: {sorted(p.name for p in before_home_mtimes)}; "
        f"after: {sorted(p.name for p in after_home_mtimes)}")
    # everything dsh wrote landed under our redirected home instead.
    assert dsh_home.is_dir()
    assert any(dsh_home.rglob("*")), "dsh_home has no content — the redirect may be a no-op"

    # L2: the session log is discoverable and real.
    assert session_log, "no session log discovered"
    assert Path(session_log).exists()
    assert str(dsh_home) in session_log

    # M1: web_search/web_fetch/subagent/subagent_fork/ralph must never reach the wire.
    assert seen_tool_names, "no request carried a tools array — test setup is broken"
    banned = {"web_search", "web_fetch", "subagent", "subagent_fork", "ralph"}
    leaked = banned & set(seen_tool_names)
    assert not leaked, f"disabled tools still reached the wire: {leaked} (seen: {seen_tool_names})"
    # the ordinary fs/bash tools this probe actually needs must still be present.
    assert {"read", "write"} <= set(seen_tool_names)


@pytestmark_skip_no_dsh
def test_real_dsh_closed_port_escalates_transport_failure_and_writes_no_row(tmp_path, monkeypatch):
    """H1, real-dsh evidence: a closed local port makes dsh retry (5x exponential backoff) and
    finally exit 1 with `dsh: TRANSPORT: ...` — main() must escalate (SystemExit), not grade this
    as an ordinary failed row. Takes ~15s wall (dsh's own retry backoff), not mocked, by design."""
    if not os.environ.get("STACK_WORKDIR"):
        pytest.skip("STACK_WORKDIR not set")
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    closed_port = s.getsockname()[1]
    s.close()  # nothing listens here -- every connection attempt is refused

    out = tmp_path / "out.jsonl"
    monkeypatch.setattr(sys, "argv", [
        "run_dsh_probe.py", "--model", "test-model", "--tune", "t0.5",
        "--items", "affine-cipher", "--out", str(out),
        "--dsh-home", str(tmp_path / "home"),
        "--base-url", f"http://127.0.0.1:{closed_port}/v1",
        "--hard-ceiling-s", "60",
    ])

    with pytest.raises(SystemExit) as e:
        P.main()
    msg = str(e.value)
    assert "TRANSPORT" in msg
    assert f"127.0.0.1:{closed_port}" in msg
    assert not out.exists() or out.read_text().strip() == "", "no row may be written on a transport failure"
