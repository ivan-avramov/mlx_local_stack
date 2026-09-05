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
    monkeypatch.setattr(sys, "argv", ["run_dsh_probe.py", "--model", "m", "--items", "x"])
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
    # the redirect target itself must exist for dsh to write into
    assert home.is_dir()


def test_dsh_env_inherits_path_from_the_caller(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/some/marker/bin:/usr/bin")
    env = P._dsh_env(tmp_path / "h", "http://127.0.0.1:1/v1")
    assert env["PATH"] == "/some/marker/bin:/usr/bin"


def test_dsh_env_honors_explicit_deepseek_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-real-not-actually")
    env = P._dsh_env(tmp_path / "h", "http://127.0.0.1:1/v1")
    assert env["DEEPSEEK_API_KEY"] == "sk-real-not-actually"


# --------------------------------------------------------------------------- _write_model_patch

def test_write_model_patch_overrides_agent_default_model(tmp_path):
    patch = P._write_model_patch(tmp_path, "Qwen3.8-27B-mlx-uniform-4bit")
    text = patch.read_text()
    assert patch.parent == tmp_path
    assert "id: agent-default-model" in text
    assert "provider: deepseek-official" in text
    assert "model: Qwen3.8-27B-mlx-uniform-4bit" in text


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

    rc, log, dur, result = P._run_dsh(
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
    rc, log, dur, result = P._run_dsh(
        Path("/x/dsh"), "m", work, "do the thing", sol, test, grade, sol.read_text(),
        base_url="http://127.0.0.1:9/v1", dsh_home=tmp_path / "home",
        tick_s=0.05, hard_ceiling_s=5.0, poll_s=0.01, stall_ticks=2, loop_repeats=3)
    wall = time.time() - t0

    assert result.stop_reason == "stalled"
    assert wall < 3.0
    assert killed == [(555, P.signal.SIGKILL)]


# --------------------------------------------------------------------------- CLI language gate (mirrors opencode)

def test_unsupported_lang_exits_with_clear_message(monkeypatch):
    monkeypatch.setattr(sys, "argv",
                        ["run_dsh_probe.py", "--model", "m", "--items", "x", "--lang", "cobol"])
    with pytest.raises(SystemExit) as e:
        P.main()
    msg = str(e.value)
    assert "cobol" in msg
    assert "unsupported" in msg


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
def test_real_dsh_headless_edits_a_file_against_a_fake_endpoint_and_stays_out_of_real_home(tmp_path, monkeypatch):
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

    handler = type("Handler", (_ScriptedDeepSeekHandler,), {
        "target_path": str(sol), "new_content": new_content,
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
        rc, log, dur, result = P._run_dsh(
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
