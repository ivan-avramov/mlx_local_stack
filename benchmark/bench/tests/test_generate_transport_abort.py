"""C119: only a full client timeout is a scoreable error row."""
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from datetime import datetime
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from unittest.mock import Mock

import pytest

from bench import benchmarks as B, client as C, generate as G, model_params, provenance as P
from .conftest import FrozenClock, probe_result


def _setup(monkeypatch, root):
    clock = FrozenClock()
    state = SimpleNamespace(calls=[], clock=clock, failure=URLError(ConnectionRefusedError()),
                            delay=1.0, fail_at=2, workdir=os.environ.get("STACK_WORKDIR"))
    monkeypatch.setattr(G, "RESULTS", root)
    monkeypatch.setenv("STACK_WORKDIR", str(root))
    monkeypatch.setattr(G.time, "perf_counter", clock)
    monkeypatch.setattr(B, "load", lambda *a: [{"id": f"i{i}", "prompt": "p"}
                                              for i in range(1, 6)])
    monkeypatch.setattr(model_params, "params_for", lambda *a, **k: {"thinking_budget": 1000})
    router = {"pid": 42, "config": "$CONFIG/registry.yaml", "config_sha256": "fixed"}
    monkeypatch.setattr(P, "assert_served_config", lambda *a: router)
    monkeypatch.setattr(P, "router_block", lambda *a: router)
    monkeypatch.setattr(P, "assert_serving_state", lambda *a: None)
    monkeypatch.setattr(P, "registry_mtp_verify_scan", lambda *a: {"mtp_verify_scan": "per_query"})
    manifest = {"sampling_profile": "deployed", "sampling": {}, "kv": {},
                "router": router, "preserved": {"sentinel": True}}
    monkeypatch.setattr(P, "current_manifest_lite", lambda *a, **k: dict(manifest))

    def write(model, bench, **kwargs):
        path = G.result_path(model, bench, tune=kwargs.get("tune")).with_suffix(".manifest.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest))

    monkeypatch.setattr(P, "write", write)
    state.exit_check = Mock(return_value=router)
    monkeypatch.setattr(P, "assert_served_config_unchanged", state.exit_check)
    state.preload = Mock(return_value=0.0)
    monkeypatch.setattr(C, "preload", state.preload)
    monkeypatch.setattr(C, "_post", Mock(side_effect=AssertionError("unexpected HTTP")))
    monkeypatch.setattr(C, "_get", Mock(side_effect=AssertionError("unexpected HTTP")))

    def probe(model, messages, params, **kwargs):
        state.calls.append(dict(params))
        clock.advance(state.delay)
        if len(state.calls) == state.fail_at:
            if isinstance(state.failure, BaseException):
                raise state.failure
            return state.failure
        return probe_result()

    monkeypatch.setattr(C, "probe", probe)
    return state


@pytest.fixture
def rig(monkeypatch, tmp_path):
    return _setup(monkeypatch, tmp_path)


def _run(**kwargs):
    G.run(["m"], ["aime"], {}, sampling_profile="deployed", probe_timeout=100, **kwargs)


def _manifest(model="m", bench="aime", tune=None):
    return json.loads(G.result_path(model, bench, tune=tune).with_suffix(".manifest.json").read_text())


def _capture_abort(rig, **kwargs):
    caught = None
    try:
        _run(**kwargs)
    except Exception as exc:
        caught = exc
    rows = G._read_rows("m", "aime", tune=kwargs.get("tune"))
    assert caught is not None, f"KNOWN POSITIVE: rows={len(rows)}, probe_calls={len(rig.calls)}; no abort"
    assert isinstance(caught, C.TransportAbort)
    assert isinstance(caught, RuntimeError)
    return caught


def test_refused_item_two_aborts_without_a_row(rig):
    caught = _capture_abort(rig, tune="test")
    assert caught.__cause__ is rig.failure
    assert len(G._read_rows("m", "aime", tune="test")) == 1
    assert len(rig.calls) == 2
    assert rig.preload.call_count == 1
    manifest = _manifest(tune="test")
    assert manifest["preserved"] == {"sentinel": True}
    stamp = manifest["transport_abort"]
    assert stamp == {"item": "i2", "sample": 0, "bench": "aime", "model": "m",
                     "error": "URLError: <urlopen error >", "elapsed_s": 1.0,
                     "rows_on_disk": 1, "ts": stamp["ts"], "served_check": "unchanged"}
    assert isinstance(stamp["elapsed_s"], float)
    assert datetime.fromisoformat(stamp["ts"]).tzinfo is not None
    rig.exit_check.assert_called_once()


@pytest.mark.parametrize("failure", [
    HTTPError("/chat", 500, "server error", {}, None),
    HTTPError("/chat", 400, "bad request", {}, None),
    C.MalformedResponseError("bad envelope"), ConnectionResetError("reset"),
    http.client.RemoteDisconnected("closed"), http.client.IncompleteRead(b"partial", 20),
    URLError("not a timeout"), {}, TypeError("bad row"), ValueError("bad messages"),
    TimeoutError("early"), URLError(socket.timeout("early")),
])
def test_non_outcomes_abort(rig, failure):
    rig.failure = failure
    rig.delay = 10.0
    caught = _capture_abort(rig)
    assert isinstance(caught.__cause__, KeyError) if failure == {} else caught.__cause__ is failure
    assert len(G._read_rows("m", "aime")) == 1
    assert len(rig.calls) == 2
    assert rig.preload.call_count == 1
    assert _manifest()["transport_abort"]["rows_on_disk"] == 1


@pytest.mark.parametrize("failure", [TimeoutError("timed out")])
@pytest.mark.parametrize("elapsed", [90.0, 100.0])
def test_full_client_timeout_remains_dnf_and_resume_skips_it(rig, failure, elapsed):
    rig.failure, rig.delay = failure, elapsed
    _run()
    rows = G._read_rows("m", "aime")
    assert len(rows) == len(rig.calls) == 5
    assert rows[1]["error_kind"] == "probe_timeout"
    assert rows[1]["wall_s"] == elapsed
    assert all(not row.get("error") for row in rows[2:])
    assert "transport_abort" not in _manifest()
    _run()
    assert len(rig.calls) == 5


@pytest.mark.parametrize("failure", [
    ConnectionError("closed"), ConnectionResetError("reset"),
    http.client.IncompleteRead(b"partial", 20), http.client.RemoteDisconnected("closed"),
    HTTPError("/chat", 500, "server error", {}, None),
    HTTPError("/chat", 400, "bad request", {}, None),
    C.MalformedResponseError("bad envelope"), KeyError("missing"), {},
    TypeError("bad row"), ValueError("bad messages"), URLError("not a timeout"),
    URLError(socket.timeout("timed out")),
])
def test_slow_non_timeout_still_aborts(rig, failure):
    rig.failure = failure
    rig.delay = 100.0
    _capture_abort(rig)
    assert len(G._read_rows("m", "aime")) == 1


@pytest.mark.parametrize("where", ["probe", "preload"])
def test_served_config_error_is_unchanged(rig, where):
    error = P.ServedConfigError("M50 refusal")
    rig.failure = error
    if where == "preload":
        rig.preload.side_effect = error
    with pytest.raises(P.ServedConfigError) as caught:
        _run()
    assert caught.value is error
    assert "transport_abort" not in _manifest()


def test_resume_retries_same_seed_and_archives_stamp(rig):
    _capture_abort(rig)
    stamp = _manifest()["transport_abort"]
    aborted_seed = rig.calls[1]["seed"]
    _run()
    rows = G._read_rows("m", "aime")
    assert [row["id"] for row in rows] == [f"i{i}" for i in range(1, 6)]
    assert rows[1]["sampler_seed"] == rig.calls[2]["seed"] == aborted_seed
    assert "transport_abort" not in _manifest()
    assert _manifest()["transport_abort_history"] == [stamp]


def test_repeated_abort_and_incompatible_restamp_preserve_history(rig, monkeypatch):
    _capture_abort(rig)
    first = _manifest()["transport_abort"]
    rig.fail_at = 3
    _capture_abort(rig)
    second = _manifest()["transport_abort"]
    assert _manifest()["transport_abort_history"] == [first]
    monkeypatch.setattr(P, "is_compatible", lambda *a: False)
    _run()
    assert _manifest()["transport_abort_history"] == [first, second]
    assert "transport_abort" not in _manifest()


@pytest.mark.parametrize("benches", [["aime", "math500"], ["aime"]])
def test_completion_archives_stamps_even_for_pairs_without_pending_items(rig, monkeypatch, benches):
    monkeypatch.setattr(B, "load", lambda *a: [{"id": "i1", "prompt": "p"}])
    with pytest.raises(C.TransportAbort):
        G.run(["m"], ["aime", "math500"], {}, probe_timeout=100)
    stamp = _manifest()["transport_abort"]
    G.run(["m"], benches, {}, probe_timeout=100)
    assert "transport_abort" not in _manifest()
    assert _manifest()["transport_abort_history"] == [stamp]


@pytest.mark.parametrize("error", [TypeError("bad messages"), ValueError("bad depth")])
def test_message_building_errors_abort(rig, monkeypatch, error):
    original = B.build_messages

    def messages(bench, item):
        if item["id"] == "i2":
            raise error
        return original(bench, item)

    monkeypatch.setattr(B, "build_messages", messages)
    caught = _capture_abort(rig)
    assert caught.__cause__ is error
    assert len(rig.calls) == 1
    assert len(G._read_rows("m", "aime")) == 1


def test_abort_stamps_all_pairs_before_best_effort_exit_check(rig):
    def failed_check(*args):
        for bench, count in [("aime", 1), ("math500", 0)]:
            assert _manifest(bench=bench)["transport_abort"]["rows_on_disk"] == count
        raise P.ServedConfigError("C106 changed")

    rig.exit_check.side_effect = failed_check
    with pytest.raises(C.TransportAbort) as caught:
        G.run(["m"], ["aime", "math500"], {}, probe_timeout=100)
    assert caught.value.__cause__ is rig.failure
    for bench in ["aime", "math500"]:
        stamp = _manifest(bench=bench)["transport_abort"]
        assert stamp["bench"] == "math500"
        assert stamp["served_check"] == "ServedConfigError: C106 changed"


def test_preload_failure_aborts_and_stamps_all_models(rig):
    rig.clock.advance(5000)
    def failed_load(*args):
        rig.clock.advance(7.5)
        raise URLError("load failed")
    rig.preload.side_effect = failed_load
    with pytest.raises(C.TransportAbort):
        G.run(["m", "n"], ["aime"], {}, probe_timeout=100)
    assert not rig.calls
    assert rig.preload.call_count == 1
    for model in ["m", "n"]:
        stamp = _manifest(model=model)["transport_abort"]
        assert stamp["item"] == "i1" and stamp["model"] == "m"
        assert stamp["rows_on_disk"] == 0
        assert stamp["elapsed_s"] == pytest.approx(7.5)


def test_abort_errors_scrub_home_paths_before_truncation(rig):
    home = str(Path.home())
    rig.failure = ValueError(f"bad file {home}/secret\n" + "x" * 300)
    rig.exit_check.side_effect = P.ServedConfigError(f"changed {home}/registry.yaml")
    caught = _capture_abort(rig)
    stamp = _manifest()["transport_abort"]
    assert home not in json.dumps(stamp)
    assert home not in str(caught)
    assert stamp["error"].startswith("ValueError: bad file $HOME/secret")
    assert len(stamp["error"]) <= 200
    assert "\n" not in str(caught)


@pytest.mark.parametrize("where,expected", [("open", URLError), ("read", TimeoutError)])
def test_post_preserves_timeout_shape_without_network(monkeypatch, where, expected):
    error = socket.timeout("timed out")
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.side_effect = error
    opener = Mock(return_value=response)
    if where == "open":
        opener.side_effect = URLError(error)
    monkeypatch.setattr(C.urllib.request, "urlopen", opener)
    with pytest.raises(expected) as caught:
        C._post("/chat", {}, timeout=100)
    assert caught.value.reason is error if where == "open" else caught.value is error


def test_cli_main_exits_nonzero_and_names_item_and_cause(tmp_path):
    script = """
import sys
from pathlib import Path
from pytest import MonkeyPatch
from bench.tests.test_generate_transport_abort import _setup
import run
patch = MonkeyPatch()
_setup(patch, Path(sys.argv[1]))
sys.argv = ['run.py', 'generate', '--models', 'm', '--benches', 'aime',
            '--sampling-profile', 'deployed', '--probe-timeout', '100']
run.main()
"""
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
                            cwd=Path(__file__).resolve().parents[2],
                            env={**os.environ, "STACK_WORKDIR": str(tmp_path)},
                            capture_output=True, text=True)
    assert result.returncode == 1, result.stdout
    last = result.stderr.splitlines()[-1]
    assert "TransportAbort" in last and "i2" in last and "URLError" in last
    assert len((tmp_path / "m" / "aime.jsonl").read_text().splitlines()) == 1


@pytest.mark.parametrize("elapsed", [90.0, 100.0])
def test_full_wrapped_timeout_aborts(rig, elapsed):
    rig.failure, rig.delay = URLError(socket.timeout("timed out")), elapsed
    assert _capture_abort(rig).__cause__ is rig.failure
    assert len(G._read_rows("m", "aime")) == 1


@pytest.mark.parametrize("where", ["restart", "preload", "second_probe"])
@pytest.mark.parametrize("error_type", [TimeoutError, ConnectionError])
def test_recovery_failures_never_become_dnf(rig, monkeypatch, where, error_type):
    error = error_type("recovery failed")
    calls = []
    restart = Mock()
    def probe(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            rig.clock.advance(95)
            return probe_result(reasoning="repeat this reasoning line forever\n" * 40, completion_tokens=1000,
                                finish_reason="length")
        rig.clock.advance(100)
        raise error
    def fail(*args):
        rig.clock.advance(1)
        raise error
    monkeypatch.setattr(C, "probe", probe)
    if where == "restart":
        restart.side_effect = fail
    elif where == "preload":
        def preload(*args):
            if rig.preload.call_count == 1:
                return 0.0
            return fail()
        rig.preload.side_effect = preload
    with pytest.raises(C.TransportAbort) as caught:
        _run(restart_fn=restart)
    assert caught.value.__cause__ is error
    assert G._read_rows("m", "aime") == []
    assert len(calls) == (2 if where == "second_probe" else 1)
    restart.assert_called_once()


def test_first_probe_timeout_uses_own_clock_with_restart(rig, monkeypatch):
    rig.failure, rig.delay = TimeoutError("timed out"), 100.0
    original = B.build_messages
    def messages(*args):
        rig.clock.advance(17)
        return original(*args)
    monkeypatch.setattr(B, "build_messages", messages)
    restart = Mock()
    _run(restart_fn=restart)
    rows = G._read_rows("m", "aime")
    assert rows[1]["error_kind"] == "probe_timeout"
    assert rows[1]["wall_s"] == 100.0
    restart.assert_not_called()


def test_early_probe_timeout_cannot_borrow_message_build_time(rig, monkeypatch):
    rig.failure, rig.delay = TimeoutError("early"), 1.0
    original = B.build_messages
    def messages(*args):
        rig.clock.advance(100)
        return original(*args)
    monkeypatch.setattr(B, "build_messages", messages)
    assert _capture_abort(rig).__cause__ is rig.failure


@pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit(2), RuntimeError("check failed")])
def test_abort_exit_check_cannot_mask_original(rig, error):
    rig.exit_check.side_effect = error
    caught = _capture_abort(rig)
    assert caught.__cause__ is rig.failure
    assert _manifest()["transport_abort"]["served_check"].startswith(type(error).__name__)


@pytest.mark.parametrize("where", ["manifest_read", "rows_read", "write", "final_write"])
def test_abort_stamp_failure_isolated_and_reported(rig, monkeypatch, capsys, where):
    bad = G.result_path("m", "aime")
    bad_manifest = bad.with_suffix(".manifest.json")
    original_probe = C.probe
    read_text, write_manifest = Path.read_text, G._write_manifest
    writes = []
    def read(path, *args, **kwargs):
        if path == (bad if where == "rows_read" else bad_manifest):
            if where == "rows_read":
                raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
            if where == "manifest_read":
                raise PermissionError("unreadable")
        return read_text(path, *args, **kwargs)
    def write(path, manifest):
        if path == bad_manifest:
            writes.append(1)
            if where == "write" or (where == "final_write" and len(writes) > 1):
                raise OSError("unwritable")
        return write_manifest(path, manifest)
    def probe(*args, **kwargs):
        if len(rig.calls) == 1:
            monkeypatch.setattr(Path, "read_text", read)
            monkeypatch.setattr(G, "_write_manifest", write)
        return original_probe(*args, **kwargs)
    monkeypatch.setattr(C, "probe", probe)
    with pytest.raises(C.TransportAbort) as caught:
        G.run(["m"], ["aime", "math500", "gsm8k"], {}, probe_timeout=100)
    assert caught.value.__cause__ is rig.failure
    for bench in ["math500", "gsm8k"]:
        stamp = _manifest(bench=bench)["transport_abort"]
        assert stamp["served_check"] == "unchanged"
        assert len(stamp["stamp_errors"]) == 1
        assert "aime" in stamp["stamp_errors"][0]
    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 1 and "aime" in lines[0]
    rig.exit_check.assert_called_once()


def test_completion_archive_failure_warns_and_continues(rig, monkeypatch, capsys):
    rig.fail_at = -1
    bad_manifest = G.result_path("m", "aime").with_suffix(".manifest.json")
    def completed_check(*args):
        bad_manifest.write_text("not json")
    rig.exit_check.side_effect = completed_check
    _run()
    assert len(G._read_rows("m", "aime")) == 5
    assert "warning" in capsys.readouterr().err.lower()


@pytest.mark.parametrize("pending", [True, False])
def test_completion_exit_check_precedes_archive(rig, monkeypatch, pending):
    monkeypatch.setattr(B, "load", lambda *a: [{"id": "i1", "prompt": "p"}])
    with pytest.raises(C.TransportAbort):
        G.run(["m"], ["aime", "math500"], {}, probe_timeout=100)
    stamp = _manifest()["transport_abort"]
    rig.exit_check.side_effect = P.ServedConfigError("exit drift")
    with pytest.raises(P.ServedConfigError, match="exit drift"):
        G.run(["m"], ["aime", "math500"] if pending else ["aime"], {}, probe_timeout=100)
    assert _manifest()["transport_abort"] == stamp
    assert "transport_abort_history" not in _manifest()


def test_abort_scrubs_login_workdir_and_boundary_before_truncation(rig, monkeypatch):
    login = "fixture_operator"
    monkeypatch.setattr(P, "_login_name", lambda: login)
    workdir = rig.workdir or str(Path.home() / "fixture-workdir")
    monkeypatch.setenv("STACK_WORKDIR", workdir)
    home = str(Path.home())
    prefix = "x" * (195 - len("ValueError: "))
    rig.failure = ValueError(prefix + home + "/secret")
    _capture_abort(rig)
    assert _manifest()["transport_abort"]["error"] == ("ValueError: " + prefix + "$HOME/secret")[:200]
    rig.fail_at = len(rig.calls) + 1
    rig.failure = ValueError(f"middle {home}/secret user {login} work {workdir}/artifact")
    caught = _capture_abort(rig)
    error = _manifest()["transport_abort"]["error"]
    assert error == "ValueError: middle $HOME/secret user $USER work $STACK_WORKDIR/artifact"
    assert home not in error and login not in error and workdir not in str(caught)


def test_abort_missing_manifest_leaves_stderr_record(rig, monkeypatch, capsys):
    monkeypatch.setattr(P, "write", lambda *a, **k: None)
    _capture_abort(rig)
    assert not G.result_path("m", "aime").with_suffix(".manifest.json").exists()
    assert "i2" in capsys.readouterr().err


def test_resume_archives_only_pending_pairs_at_start(rig, monkeypatch):
    monkeypatch.setattr(B, "load", lambda *a: [{"id": "i1", "prompt": "p"}])
    with pytest.raises(C.TransportAbort):
        G.run(["m"], ["aime", "math500"], {}, probe_timeout=100)
    complete_stamp = _manifest()["transport_abort"]
    pending_stamp = _manifest(bench="math500")["transport_abort"]
    def preload(*args):
        assert _manifest()["transport_abort"] == complete_stamp
        assert "transport_abort" not in _manifest(bench="math500")
        assert _manifest(bench="math500")["transport_abort_history"] == [pending_stamp]
        raise rig.failure
    rig.preload.side_effect = preload
    with pytest.raises(C.TransportAbort):
        G.run(["m"], ["aime", "math500"], {}, probe_timeout=100)
    assert _manifest()["transport_abort"] == complete_stamp
