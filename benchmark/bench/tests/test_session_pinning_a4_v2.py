"""A4 v2: fake executable plus worker-log rows; never contact a model server."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def gate(monkeypatch, tmp_path):
    repo = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location("session_pinning_gate_m59", repo / "scripts/session_pinning_gate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    monkeypatch.setenv("OPENCODE_CONFIG", "inherited-must-not-survive")
    monkeypatch.setenv("OPENCODE_CONFIG_CONTENT", "inherited-must-not-survive")
    monkeypatch.setenv("OPENCODE_SURPRISE", "inherited-must-not-survive")
    from bench import provenance
    monkeypatch.setattr(provenance, "assert_served_config", lambda *a, **k: {"pid": 4321, "config_sha256": "registry-sha"})
    monkeypatch.setattr(provenance, "assert_served_config_unchanged", lambda *a, **k: a[0])
    fake_repo = tmp_path / "repo"
    (fake_repo / "benchmark/opencode_plugins").mkdir(parents=True)
    carrier = fake_repo / "benchmark/opencode_bench_v2.json"
    carrier.write_text(json.dumps({"providers": {"mlx-local": {"settings": {"baseURL": "http://localhost:8000/v1"}}}}) + "\n")
    (fake_repo / "benchmark/opencode_plugins/noretry.js").write_text("// fake plugin\n")
    monkeypatch.setattr(module, "REPO", fake_repo)
    monkeypatch.setattr(module, "time", SimpleNamespace(
        time=module.time.time, strftime=module.time.strftime, sleep=lambda seconds: None))
    binary = tmp_path / "fake-opencode"
    binary.write_text("#!" + sys.executable + "\n" + '''import hashlib, json, os, pathlib, sys
state = pathlib.Path(os.environ["XDG_STATE_HOME"])
carrier = pathlib.Path(os.environ["OPENCODE_CONFIG_DIR"]) / "opencode.json"
with (state / "calls.jsonl").open("a") as f:
    f.write(json.dumps({"args": sys.argv[1:], "env": dict(os.environ), "cwd": os.getcwd(),
                        "stdin": sys.stdin.read(), "carrier_sha256": hashlib.sha256(carrier.read_bytes()).hexdigest()}) + "\\n")
if sys.argv[1:] == ["--version"]:
    print("opencode v2.0.20")
else:
    print(json.dumps({"type": "step_start", "sessionID": "ses_gate"}))
    print(json.dumps({"type": "text", "sessionID": "ses_gate", "part": {"text": "OK"}}))
''')
    binary.chmod(0o755)
    return module, binary, carrier


class FakeLogTail:
    def __init__(self, first, second):
        self.batches = [[], first, [], second, []]

    def new_rows(self):
        return self.batches.pop(0) if self.batches else []


def row(session="ses_gate", cached=0):
    return {"session": session, "cached_tokens": cached, "prompt_tokens": 6000}


def run_gate(gate, tmp_path, first=None, second=None):
    module, binary, _ = gate
    log = FakeLogTail([row()] if first is None else first,
                      [row(cached=5500)] if second is None else second)
    return module.a4_opencode("Test-Model", log, tmp_path / "unused-v1-root", 10, str(binary), opencode="v2")


def test_a4_v2_pass_env_carrier_and_latest(gate, tmp_path):
    result = run_gate(gate, tmp_path)
    assert result["pass"] is True
    assert result["cross_process_reuse"] is True
    assert result["sessions"] == ["ses_gate"]
    assert result["opencode_version"] == "2.0.20"
    assert result["exe_sha256"] == hashlib.sha256(gate[1].read_bytes()).hexdigest()
    assert result["run_id"]
    assert result["router"]["pid"] == 4321
    assert result["router_pid"] == 4321
    assert json.loads((tmp_path / "session_gate/a4_v2_latest.json").read_text()) == result
    calls_file, = (tmp_path / "session_gate").glob("*/state/calls.jsonl")
    calls = [json.loads(line) for line in calls_file.read_text().splitlines()]
    assert calls[0]["args"] == ["--version"]
    assert calls[1]["args"] == ["run", "--standalone", "--model", "mlx-local/Test-Model", "--format", "json", "--title", "gate", "In one sentence, what does hello.py do?"]
    assert calls[2]["args"] == ["run", "--standalone", "--session", "ses_gate", "--format", "json", "--title", "gate", "One line: what does it return for 'x'?"]
    run_root = calls_file.parent.parent
    for call in calls:
        env = call["env"]
        assert call["stdin"] == ""
        assert call["cwd"] == env["PWD"]
        assert (Path(env["PWD"]) / ".git").is_dir()
        assert not Path(env["PWD"]).is_relative_to(Path(env["HOME"]))
        assert env["PATH"] == "/opt/homebrew/bin:/usr/bin:/bin"
        assert env["TERM"] == "dumb" and env["NO_COLOR"] == "1"
        assert {k for k in env if k.startswith("OPENCODE_")} == {
            "OPENCODE_CONFIG_DIR", "OPENCODE_CONFIG_CONTENT", "OPENCODE_DISABLE_PROJECT_CONFIG",
            "OPENCODE_DISABLE_MODELS_FETCH", "OPENCODE_DISABLE_AUTOUPDATE", "OPENCODE_DISABLE_FILEWATCHER",
        }
        for key in ("OPENCODE_DISABLE_PROJECT_CONFIG", "OPENCODE_DISABLE_MODELS_FETCH", "OPENCODE_DISABLE_AUTOUPDATE", "OPENCODE_DISABLE_FILEWATCHER"):
            assert env[key] == "1"
        assert json.loads(env["OPENCODE_CONFIG_CONTENT"]) == {"providers": {"mlx-local": {"models": {"Test-Model": {"body": {"seed": 0}}}}}}
        for key in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "TMPDIR", "OPENCODE_CONFIG_DIR"):
            assert Path(env[key]).is_relative_to(run_root)
        assert call["carrier_sha256"] == hashlib.sha256(gate[2].read_bytes()).hexdigest()
    copied = run_root / "cfg/opencode/plugins/noretry.js"
    assert copied.read_bytes() == (gate[0].REPO / "benchmark/opencode_plugins/noretry.js").read_bytes()


@pytest.mark.parametrize("bad", [None, "", "anon:abc", "ses_other"])
def test_a4_v2_rejects_missing_or_different_session(gate, tmp_path, bad):
    assert run_gate(gate, tmp_path, second=[row(), row(bad)])["pass"] is False


def test_a4_v2_reuse_is_reported_not_gated(gate, tmp_path):
    result = run_gate(gate, tmp_path, second=[row(cached=0)])
    assert result["pass"] is True
    assert result["cross_process_reuse"] is False


def test_a4_v2_client_fallback_is_verbatim(gate, tmp_path, capsys):
    module, _, carrier = gate
    target = module.REPO / "opencode_config/opencode.json"
    target.parent.mkdir()
    carrier.rename(target)
    assert run_gate(gate, tmp_path)["pass"] is True
    assert "WARNING" in capsys.readouterr().out
    copy, = (tmp_path / "session_gate").glob("*/cfg/opencode/opencode.json")
    assert copy.read_bytes() == target.read_bytes()


def test_a4_v2_no_requests_on_either_turn_fails(gate, tmp_path, monkeypatch):
    monkeypatch.setattr(gate[0], "wait_rows", lambda log, *a: log.new_rows())
    result = run_gate(gate, tmp_path, second=[])
    assert result["pass"] is False
    assert result["turns"][1]["requests"] == []


def test_a4_v2_worker_id_must_match_event_id(gate, tmp_path):
    result = run_gate(gate, tmp_path, first=[row("ses_wrong")], second=[row("ses_wrong")])
    assert result["pass"] is False


@pytest.mark.parametrize("event", [{}, {"sessionID": "anon:wrong"}, "not-json"])
def test_a4_v2_missing_first_event_session_refuses_resume(gate, tmp_path, event):
    binary = gate[1]
    original = 'print(json.dumps({"type": "step_start", "sessionID": "ses_gate"}))'
    replacement = 'print(' + repr(json.dumps(event) if isinstance(event, dict) else event) + ')'
    binary.write_text(binary.read_text().replace(original, replacement))
    result = run_gate(gate, tmp_path)
    assert result["pass"] is False
    assert len(result["turns"]) == 1
    assert result["session_id"] is None


def test_a4_v2_nonzero_rc_fails(gate, tmp_path):
    binary = gate[1]
    binary.write_text(binary.read_text() + '\nif "run" in sys.argv: sys.exit(1)\n')
    result = run_gate(gate, tmp_path)
    assert result["pass"] is False
    assert result["turns"][0]["rc"] == 1


def test_a4_v2_turn_two_nonzero_rc_fails(gate, tmp_path):
    binary = gate[1]
    binary.write_text(binary.read_text() + '\nif "--session" in sys.argv: sys.exit(1)\n')
    result = run_gate(gate, tmp_path)
    assert [turn["rc"] for turn in result["turns"]] == [0, 1]
    assert all(turn["requests"] for turn in result["turns"])
    assert result["sessions"] == ["ses_gate"]
    assert result["pass"] is False


def test_a4_v2_carrier_destination_refused(gate, tmp_path):
    carrier = gate[2]
    doc = json.loads(carrier.read_text())
    doc["providers"]["mlx-local"]["settings"]["baseURL"] = "http://127.0.0.1:9/v1"
    carrier.write_text(json.dumps(doc))
    with pytest.raises(SystemExit) as error:
        run_gate(gate, tmp_path)
    assert str(error.value) == "M50 tripwire: A4 v2 carrier destination differs from the verified router"
    assert not list((tmp_path / "session_gate").glob("*/state/calls.jsonl"))
    print(f"REFUSED: {error.value}")


def test_a4_v2_wrong_version_refused(gate, tmp_path):
    binary = gate[1]
    binary.write_text(binary.read_text().replace("opencode v2.0.20", "opencode v2.0.19"))
    with pytest.raises(SystemExit) as error:
        run_gate(gate, tmp_path)
    assert str(error.value) == "REFUSED: A4 v2 requires opencode 2.0.20; got '2.0.19'"
    calls_file, = (tmp_path / "session_gate").glob("*/state/calls.jsonl")
    assert [json.loads(line)["args"] for line in calls_file.read_text().splitlines()] == [["--version"]]
    print(error.value)


def test_a4_v2_latest_records_model(gate, tmp_path):
    run_gate(gate, tmp_path)
    latest = json.loads((tmp_path / "session_gate/a4_v2_latest.json").read_text())
    assert latest["model"] == "Test-Model"


@pytest.mark.parametrize("passing", [True, False])
def test_a4_v2_tmp_removed_only_on_pass(gate, tmp_path, passing):
    binary = gate[1]
    binary.write_text(binary.read_text() + '\n(pathlib.Path(os.environ["TMPDIR"]) / "bun.dylib").write_bytes(b"fixture")\n')
    result = run_gate(gate, tmp_path, second=[row() if passing else row(None)])
    assert result["pass"] is passing
    run_root = tmp_path / "session_gate" / result["run_id"]
    assert (run_root / "tmp").exists() is (not passing)
    if not passing:
        assert (run_root / "tmp/bun.dylib").read_bytes() == b"fixture"


def test_a4_v2_settle_counts_late_turn_two_rows(gate, tmp_path, monkeypatch):
    module, binary, _ = gate
    settled = []
    monkeypatch.setattr(module.time, "sleep", settled.append)

    class LateLog(FakeLogTail):
        def new_rows(self):
            if len(self.batches) == 1:
                return [row(None)] if settled == [5] else []
            return super().new_rows()

    result = module.a4_opencode("Test-Model", LateLog([row()], [row()]),
                                tmp_path, 10, str(binary), opencode="v2")
    assert result["pass"] is False
    assert result["turns"][1]["requests"][-1]["session"] is None
    assert settled == [5]


def test_a4_v2_uses_validated_base_url(gate, tmp_path, monkeypatch):
    from bench import provenance

    module, binary, carrier = gate
    base = "http://127.0.0.1:18000/v1"
    doc = json.loads(carrier.read_text())
    doc["providers"]["mlx-local"]["settings"]["baseURL"] = base
    carrier.write_text(json.dumps(doc))
    observed = []
    monkeypatch.setattr(provenance, "assert_served_config", lambda url, **kw: observed.append(url) or {"pid": 4321})
    monkeypatch.setattr(provenance, "assert_served_config_unchanged", lambda router, url, **kw: observed.append(url))
    result = module.a4_opencode("Test-Model", FakeLogTail([row()], [row()]),
                                tmp_path, 10, str(binary), opencode="v2", base=base)
    assert result["pass"] is True
    assert observed == [base, base]


def test_a4_v2_drift_invalidates_latest_pass(gate, tmp_path, monkeypatch):
    from bench import provenance

    def drift(*args, **kwargs):
        raise provenance.ServedConfigError("router PID changed")

    monkeypatch.setattr(provenance, "assert_served_config_unchanged", drift)
    result = run_gate(gate, tmp_path)
    assert result["pass"] is False
    assert result["served_config_drift"] is True
    assert json.loads((tmp_path / "session_gate/a4_v2_latest.json").read_text())["pass"] is False


def test_a4_v2_m50_refuses_before_creating_run(gate, tmp_path, monkeypatch):
    from bench import provenance

    def refuse(*args, **kwargs):
        raise provenance.ServedConfigError("M50 tripwire: wrong registry")

    monkeypatch.setattr(provenance, "assert_served_config", refuse)
    with pytest.raises(provenance.ServedConfigError, match="M50 tripwire"):
        run_gate(gate, tmp_path)
    assert not (tmp_path / "session_gate").exists()


def test_gate_cli_defaults_to_v2_and_routes_explicit_v2(gate, tmp_path, monkeypatch):
    module, binary, _ = gate
    import run_opencode_probe as oc

    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(binary))
    monkeypatch.setenv("MLX_SERVE_BASE", "http://localhost:8000/v1")
    monkeypatch.setattr(oc, "_sha_of", lambda path: "test-sha")
    monkeypatch.setattr(module, "LogTail", lambda path: object())
    monkeypatch.setattr(module, "a6_bare", lambda *args: {"pass": True})
    choices = []

    def a4(*args, opencode="v2", base=None):
        choices.append((opencode, base))
        return {"pass": True, "sessions": ["ses_gate"], "opencode_version": "2.0.20", "exe_sha256": "test-sha"}

    monkeypatch.setattr(module, "a4_opencode", a4)
    args = ["--model", "Test-Model", "--skip-owui", "--workdir", str(tmp_path / "cli")]
    assert module.main(args) == 0
    monkeypatch.setenv("MLX_SERVE_BASE", "http://127.0.0.1:18000/v1")
    assert module.main(args + ["--opencode", "v2"]) == 0
    assert choices == [("v2", "http://localhost:8000/v1"), ("v2", "http://127.0.0.1:18000/v1")]


@pytest.mark.parametrize("entry", ["cli", "a4"])
def test_gate_v1_refuses_before_io(gate, tmp_path, monkeypatch, entry):
    from bench import provenance

    module, binary, _ = gate
    root = tmp_path / "refused"

    def no_io(*args, **kwargs):
        pytest.fail("frozen gate leg attempted I/O")

    monkeypatch.setattr(provenance, "assert_served_config", no_io)
    monkeypatch.setattr(module.subprocess, "run", no_io)
    monkeypatch.setattr(module.subprocess, "Popen", no_io)
    monkeypatch.setattr(module, "LogTail", no_io)
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(binary))
    with pytest.raises(SystemExit) as error:
        if entry == "cli":
            module.main(["--model", "Test-Model", "--opencode", "1.18", "--workdir", str(root)])
        else:
            module.a4_opencode("Test-Model", None, root, 10, str(binary), opencode="1.18")
    assert error.value.code == (
        "REFUSED: the opencode 1.18 gate leg is frozen (M59, 2026-10-07); use --opencode v2"
    )
    assert not root.exists()


def test_a4_v2_timeout_is_failed_and_recorded(gate, tmp_path):
    module, binary, _ = gate
    binary.write_text(binary.read_text() + '\nif "run" in sys.argv:\n    import time\n    time.sleep(10)\n')
    result = module.a4_opencode("Test-Model", FakeLogTail([row()], [row()]),
                                tmp_path, 0.1, str(binary), opencode="v2")
    assert result["pass"] is False
    assert result["turns"][0]["rc"] == "timeout"


def test_a4_written_receipt_is_consumed_by_probe(gate, tmp_path):
    """Exercise the gate writer and probe reader together, with the actual receipt keys."""
    import run_opencode_probe_v2 as probe

    result = run_gate(gate, tmp_path)
    path = tmp_path / "session_gate/a4_v2_latest.json"
    assert probe._a4_receipt(path, {"pid": 4321}, None, "Test-Model",
                             result["exe_sha256"], result["carrier_sha256"]) == result
