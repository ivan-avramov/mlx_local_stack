"""P155: native v2 probe, transport aborts, continuation and real wire captures."""

from __future__ import annotations
import ast
import hashlib
import importlib
import importlib.util
import io
import tokenize
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

import pytest
from bench import provenance, progress_gate

MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"


@pytest.fixture
def probe(monkeypatch, tmp_path):
    """Probe."""
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    assert importlib.util.find_spec(
        "run_opencode_probe_v2"
    ), "v2 probe is missing: transport failures cannot abort and resume identity is unchecked"
    return importlib.import_module("run_opencode_probe_v2")


def events(kind="ok"):
    """Events."""
    start = {"type": "step_start", "sessionID": "ses_test"}
    finish = {"type": "step_finish", "sessionID": "ses_test"}
    if kind == "retry":
        return [start, start, finish, start, {"type": "text", "sessionID": "ses_test"}]
    if kind == "ok":
        return [
            start,
            {"type": "tool_use"},
            finish,
            start,
            {"type": "text", "sessionID": "ses_test"},
        ]
    if kind == "empty":
        return []
    if kind == "no_error":
        return [start]
    types = {
        "http500": "provider.internal",
        "drop": "provider.invalid-output",
        "refuse": "provider.transport",
        "ctx400": "provider.invalid-request",
        "other400": "provider.invalid-request",
    }
    error = {
        "type": types[kind],
        "status": 400 if "400" in kind else 500,
        "message": "bad request",
        "response": {
            "body": (
                json.dumps(
                    {
                        "error": {
                            "message": "This model's maximum context length is 4096 tokens. However, your messages resulted in 9999 tokens. Please reduce the length of the messages.",
                            "code": "context_length_exceeded",
                        }
                    }
                )
                if kind == "ctx400"
                else "broken"
            )
        },
    }
    return [start, {"type": "error", "sessionID": "ses_test", "error": error}]


def fixture_probe(probe, monkeypatch, tmp_path, kind="ok"):
    """Fixture probe."""
    p = probe
    root = tmp_path / "polyglot"
    for name in ("one", "two"):
        d = root / "python/exercises/practice" / name
        (d / ".docs").mkdir(parents=True)
        (d / ".docs/instructions.md").write_text("Set answer = 42.\n")
        (d / "solution.py").write_text("answer = 0\n")
        (d / "solution_test.py").write_text(
            "from solution import answer\ndef test_answer(): assert answer == 42\n"
        )
    monkeypatch.setenv("POLYGLOT_DIR", str(root))
    carrier = tmp_path / "carrier.json"
    carrier.write_bytes(p.BENCH_OPENCODE_CONFIG.read_bytes())
    plugin = tmp_path / "noretry.js"
    plugin.write_bytes(p.NORETRY_PLUGIN.read_bytes())
    monkeypatch.setattr(p, "BENCH_OPENCODE_CONFIG", carrier)
    monkeypatch.setattr(p, "NORETRY_PLUGIN", plugin)
    canned = tmp_path / "events.jsonl"
    rc = tmp_path / "rc"
    export = tmp_path / "export.json"
    calls = tmp_path / "calls"
    export.write_text(
        json.dumps(
            {
                "info": {"id": "ses_test"},
                "messages": [
                    {
                        "type": "assistant",
                        "tokens": {"input": 100, "output": 10},
                        "content": [
                            {
                                "type": "tool",
                                "name": "write",
                                "state": {
                                    "input": {"path": str(tmp_path / "solution.py")},
                                    "status": "completed",
                                },
                            }
                        ],
                    },
                    {"type": "assistant", "tokens": {"input": 110, "output": 5}, "content": []},
                ],
            }
        )
    )
    binary = tmp_path / "opencode"
    q = shlex.quote
    binary.write_text(
        '#!/bin/sh\ncase "$1" in\n--version) echo 2.0.20;;\nrun)\n'
        + f'echo "$OPENCODE_CONFIG_CONTENT" >> {q(str(calls))}\n'
        + 'printf "answer = 42\\n" > solution.py\n'
        + f'cat {q(str(canned))}\nexit "$(cat {q(str(rc))})";;\n'
        + f"session) cat {q(str(export))};;\n*) exit 2;;\nesac\n"
    )
    binary.chmod(0o755)
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(binary))
    router = {"pid": 123, "config": "$STACK_WORKDIR/registry.yaml", "config_sha256": "registry-sha"}
    monkeypatch.setattr(provenance, "assert_served_config", lambda *a, **k: dict(router))
    monkeypatch.setattr(provenance, "assert_served_config_unchanged", lambda *a, **k: dict(router))
    monkeypatch.setattr(
        provenance, "opencode_v2_destination", lambda *a, **k: "http://127.0.0.1:12345/v1"
    )
    monkeypatch.setattr(provenance, "_git_shas", lambda: {"serving_path": "serving-sha"})
    monkeypatch.setattr(
        provenance,
        "gather",
        lambda model, **kw: {"model": model, "git": {"serving_path": "serving-sha"}, **kw},
    )
    grades = []
    monkeypatch.setattr(p, "_grade_python", lambda *a: (grades.append(True) or (True, "passed")))
    out = tmp_path / "rows.jsonl"

    def set_kind(k):
        """Set kind."""
        canned.write_text("not json\n" + "\n".join(json.dumps(e) for e in events(k)) + "\n")
        rc.write_text("0" if k in ("ok", "retry", "empty") else "1")

    def run(items="one,two", limit=5, extra=()):
        """Run."""
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "probe",
                "--model",
                MODEL,
                "--items",
                items,
                "--seed-base",
                "77",
                "--poll-s",
                "0.01",
                "--out",
                str(out),
            ]
            + ([] if limit is None else ["--limit", str(limit)])
            + list(extra),
        )
        return p.main()

    set_kind(kind)
    return dict(
        run=run,
        set_kind=set_kind,
        out=out,
        mp=out.with_suffix(".manifest.json"),
        calls=calls,
        export=export,
        carrier=carrier,
        plugin=plugin,
        grades=grades,
        router=router,
    )


@pytest.mark.parametrize(
    "kind", ["http500", "drop", "refuse", "no_error", "other400", "retry", "empty"]
)
def test_transport_matrix_aborts_before_grade(probe, monkeypatch, tmp_path, kind):
    """Verify transport matrix aborts before grade."""
    f = fixture_probe(probe, monkeypatch, tmp_path, kind)
    with pytest.raises(SystemExit) as exc:
        f["run"]()
    assert exc.value.code != 0
    assert not f["out"].exists(), "transport failure was written as a graded row"
    assert f["grades"] == [], "transport failure reached the grader"
    assert len(f["calls"].read_text().splitlines()) == 1, "probe continued after transport abort"
    stamp = json.loads(f["mp"].read_text())["transport_abort"]
    assert set(stamp) == {"item", "rc", "stop_reason", "signature", "error"}
    assert stamp["item"] == "python/one"
    artifacts = list((tmp_path / "opencode-probe-v2/aborted").rglob("*"))
    assert any(p.name == "events.jsonl" for p in artifacts)
    assert any(p.name == "stderr.txt" for p in artifacts)
    assert any(p.name == "export.json" for p in artifacts)


def test_context_overflow_is_failed_row(probe, monkeypatch, tmp_path):
    """Verify context overflow is failed row."""
    f = fixture_probe(probe, monkeypatch, tmp_path, "ctx400")
    assert f["run"]("one") == 0
    row = json.loads(f["out"].read_text())
    assert row["nonconv_kind"] == "context_overflow" and row["passed"] is False and row["acc"] == 0
    assert row["requests_observed"] == 1


def test_normal_events_export_and_row(probe, monkeypatch, tmp_path):
    """Verify normal events export and row."""
    f = fixture_probe(probe, monkeypatch, tmp_path)
    assert f["run"]() == 0
    rows = [json.loads(s) for s in f["out"].read_text().splitlines()]
    assert len(rows) == 2 and rows[0]["sampler_seed"] != rows[1]["sampler_seed"]
    for row in rows:
        assert row["schema_version"] == 3 and row["scaffold"] == "opencode-v2"
        assert row["requests_observed"] == 2 and row["session_id"] == "ses_test"
        assert row["passed"] and row["acc"] == 1 and row["nonconv_kind"] is None
        assert row["traffic"]["output_tokens"] == 15 and row["loop_metrics"]["tool_calls"] == 1
        transcript = Path(row["transcript_path"].replace("$STACK_WORKDIR", str(tmp_path)))
        assert transcript.is_relative_to(tmp_path / "opencode_transcripts")
        assert str(Path.home()) not in transcript.read_text()
        assert probe._login_name() not in transcript.read_text()
        assert Path(row["events_path"].replace("$STACK_WORKDIR", str(tmp_path))).is_file()
        assert row["max_tokens_semantics"] == "fixed-by-carrier"
        assert row["prompt_date"] == probe._prompt_date()
    overlays = [json.loads(s) for s in f["calls"].read_text().splitlines()]
    for row, overlay in zip(rows, overlays):
        assert overlay == probe._seed_overlay(MODEL, row["sampler_seed"])
        assert (
            row["overlay_sha256"]
            == hashlib.sha256(json.dumps(overlay, sort_keys=True).encode()).hexdigest()
        )


@pytest.mark.parametrize(
    "mutation", ["same", "carrier", "plugin", "transport_abort", "served_config_drift"]
)
def test_resume_identity_and_abort_retry(probe, monkeypatch, tmp_path, mutation):
    """Verify resume identity and abort retry."""
    f = fixture_probe(
        probe, monkeypatch, tmp_path, "http500" if mutation == "transport_abort" else "ok"
    )
    if mutation == "transport_abort":
        with pytest.raises(SystemExit):
            f["run"]()
        assert not f[
            "out"
        ].exists(), "abort must leave the item unrecorded for same-seed continuation"
        f["set_kind"]("ok")
    else:
        assert f["run"]("one") == 0
    if mutation in ("carrier", "plugin"):
        with f[mutation].open("a") as fp:
            fp.write("\n")
    if mutation == "served_config_drift":
        doc = json.loads(f["mp"].read_text())
        doc["served_config_drift"] = {"error": "changed"}
        f["mp"].write_text(json.dumps(doc))
    before = f["calls"].read_text().splitlines()
    if mutation in ("carrier", "plugin", "served_config_drift"):
        with pytest.raises(SystemExit, match="REFUSED"):
            f["run"]()
        assert f["calls"].read_text().splitlines() == before
    else:
        assert f["run"]() == 0
        after = f["calls"].read_text().splitlines()
        assert len(after) == (3 if mutation == "transport_abort" else 2)
        if mutation == "transport_abort":
            assert after[0] == after[1], "aborted item changed seed on resume"
        else:
            assert len([json.loads(s) for s in f["out"].read_text().splitlines()]) == 2


@pytest.mark.parametrize("reason", ["stalled", "looping", "hard_ceiling"])
@pytest.mark.parametrize("drift", [False, True])
def test_gate_checks_router_immediately(probe, monkeypatch, tmp_path, reason, drift):
    """Verify gate checks router immediately."""
    f = fixture_probe(probe, monkeypatch, tmp_path)
    order = []

    def run(*args, **kwargs):
        """Run."""
        work = args[1]
        (work / ".opencode_probe_events.jsonl").write_text(json.dumps(events()[0]) + "\n")
        (work / ".opencode_probe_stderr.txt").write_text("")
        (work / "solution.py").write_text("answer = 42\n")
        order.append("kill")
        return 130, "", 1.0, progress_gate.GateResult(reason, [], 1.0, 130)

    def check(*a, **k):
        """Check."""
        order.append("check")
        if drift:
            raise provenance.ServedConfigError("router changed")
        return f["router"]

    monkeypatch.setattr(probe, "_run_opencode", run)
    monkeypatch.setattr(provenance, "assert_served_config_unchanged", check)
    original = probe._export_session

    def export(*a, **k):
        """Export."""
        order.append("export")
        return original(*a, **k)

    monkeypatch.setattr(probe, "_export_session", export)
    if drift:
        with pytest.raises(SystemExit):
            f["run"]("one")
        doc = json.loads(f["mp"].read_text())
        assert doc["served_config_drift"] and doc["transport_abort"]
        assert not f["out"].exists() and not f["grades"]
    else:
        assert f["run"]("one") == 0
        assert json.loads(f["out"].read_text())["nonconv_kind"] == reason
    assert order[:2] == ["kill", "check"]


@pytest.mark.parametrize("export", ["missing", "bad", "error", "retry"])
def test_bad_export_aborts(probe, monkeypatch, tmp_path, export):
    """Verify bad export aborts."""
    f = fixture_probe(probe, monkeypatch, tmp_path)
    if export == "missing":
        f["export"].unlink()
    elif export == "bad":
        f["export"].write_text("not JSON")
    else:
        doc = json.loads(f["export"].read_text())
        doc["messages"][0][export] = {"type": "provider.internal"}
        f["export"].write_text(json.dumps(doc))
    with pytest.raises(SystemExit):
        f["run"]("one")
    assert not f["out"].exists() and not f["grades"]


def test_pwd_assertion_precedes_spawn(probe, monkeypatch, tmp_path):
    """Verify pwd assertion precedes spawn."""
    calls = []
    monkeypatch.setattr(probe.subprocess, "Popen", lambda *a, **k: calls.append(a))
    with pytest.raises(provenance.ServedConfigError, match="PWD"):
        probe._spawn([str(tmp_path / "opencode")], tmp_path, {"PWD": str(tmp_path / "decoy")})
    assert calls == []


def test_hermetic_env_and_verbatim_copies(probe, monkeypatch, tmp_path):
    """Verify hermetic env and verbatim copies."""
    monkeypatch.setenv("OPENCODE_CONFIG", "leak")
    monkeypatch.setenv("SECRET_MARKER", "leak")
    run = probe._make_run_dir(tmp_path, "test")
    overlay = probe._seed_overlay(MODEL, 123)
    env = probe._opencode_env(run, tmp_path, overlay)
    assert set(env) == {
        "PATH",
        "HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "XDG_CACHE_HOME",
        "TMPDIR",
        "OPENCODE_CONFIG_DIR",
        "OPENCODE_DISABLE_PROJECT_CONFIG",
        "OPENCODE_DISABLE_MODELS_FETCH",
        "OPENCODE_DISABLE_AUTOUPDATE",
        "OPENCODE_DISABLE_FILEWATCHER",
        "OPENCODE_CONFIG_CONTENT",
        "PWD",
        "TERM",
        "NO_COLOR",
    }
    assert env["PWD"] == str(tmp_path)
    assert (
        run / "cfg/opencode/opencode.json"
    ).read_bytes() == probe.BENCH_OPENCODE_CONFIG.read_bytes()
    assert (
        run / "cfg/opencode/plugins/noretry.js"
    ).read_bytes() == probe.NORETRY_PLUGIN.read_bytes()


def test_missing_plugin_refused_before_item(probe, monkeypatch, tmp_path):
    """Verify missing plugin refused before item."""
    f = fixture_probe(probe, monkeypatch, tmp_path)
    original = probe._make_run_dir

    def damaged(*a, **k):
        """Damaged."""
        run = original(*a, **k)
        (run / "cfg/opencode/plugins/noretry.js").unlink()
        return run

    monkeypatch.setattr(probe, "_make_run_dir", damaged)
    with pytest.raises(SystemExit, match="M50 tripwire"):
        f["run"]()
    assert not f["calls"].exists() and not f["out"].exists()


def test_legacy_moves_are_byte_identical(probe):
    """Verify legacy moves are byte identical."""
    from bench import opencode_common as common

    root = Path(__file__).resolve().parents[3]
    baseline = subprocess.run(
        ["git", "show", "b533fff:benchmark/run_opencode_probe.py"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if baseline.returncode:
        pytest.skip("pre-move base b533fff unavailable in this clone: " + baseline.stderr.strip())
    before = baseline.stdout
    after = Path(common.__file__).read_text()

    def bodies(text):
        """Bodies."""
        lines = text.splitlines(keepends=True)
        return {
            n.name: "".join(
                lines[min([n.lineno] + [d.lineno for d in n.decorator_list]) - 1 : n.end_lineno]
            )
            for n in ast.parse(text).body
            if isinstance(n, ast.FunctionDef)
        }

    old, new = bodies(before), bodies(after)
    for name in common.SHARED_NAMES:
        if name in old:
            baseline = old[name]
            if name in ("loop_metrics", "traffic_metrics"):
                # STYLE explicitly requires splitting these legacy semicolon statements.
                lines = baseline.splitlines(keepends=True)
                rows = {
                    token.start[0] - 1
                    for token in tokenize.generate_tokens(io.StringIO(baseline).readline)
                    if token.type == tokenize.OP and token.string == ";"
                }
                for i in rows:
                    line = lines[i]
                    lines[i] = line.replace("; ", "\n" + line[: len(line) - len(line.lstrip())])
                baseline = "".join(lines)
            assert new[name] == baseline, name
    legacy = importlib.import_module("run_opencode_probe")
    for name in common.SHARED_NAMES:
        assert hasattr(legacy, name)


@pytest.fixture
def real_binary(probe, tmp_path):
    """Real binary."""
    binary = Path("/opt/homebrew/bin/opencode")
    if not binary.is_file():
        pytest.skip("brew opencode unavailable: /opt/homebrew/bin/opencode is missing")
    root = tmp_path / "version-env"
    for d in ("home", "cfg/opencode", "data", "state", "cache", "tmp"):
        (root / d).mkdir(parents=True, exist_ok=True)
    env = probe._opencode_env(root, tmp_path, probe._seed_overlay(MODEL, 1))
    try:
        result = subprocess.run(
            [str(binary), "--version"],
            cwd=tmp_path,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        pytest.skip("brew opencode --version cannot start: " + str(e))
    if result.returncode or probe._parse_version(result.stdout) != "2.0.20":
        pytest.skip(
            f"brew version mismatch/start failure: rc={result.returncode}, stdout={result.stdout!r}, stderr={result.stderr!r}"
        )
    return str(binary.resolve())


def real_fixture(probe, monkeypatch, tmp_path, binary, mock):
    # Keep the actual v2 destination proof; only the mlx router ownership is mocked.
    """Real fixture."""
    destination = provenance.opencode_v2_destination
    f = fixture_probe(probe, monkeypatch, tmp_path)
    monkeypatch.setattr(provenance, "opencode_v2_destination", destination)
    monkeypatch.setenv("OPENCODE_PROBE_BIN", binary)
    doc = json.loads(f["carrier"].read_text())
    doc["providers"]["mlx-local"]["settings"]["baseURL"] = mock.base
    doc["providers"]["vllm"]["settings"]["baseURL"] = mock.base.replace("/v1", "/vllm-tripwire/v1")
    f["carrier"].write_text(json.dumps(doc))
    f["body"] = doc["providers"]["mlx-local"]["models"][MODEL]["body"]
    return f


def run_real(f, items="one"):
    """Run real."""
    try:
        return f["run"](items)
    except SystemExit as e:
        # Only a diagnosed sandbox start denial is skippable; schema/protocol failures stay red.
        text = str(e)
        if any(
            s in text for s in ("Operation not permitted", "EPERM", "Permission denied", "EACCES")
        ):
            pytest.skip("opencode cannot start under sandbox: " + text)
        raise


@pytest.mark.parametrize("dynamic", [False, True])
def test_real_wire_seed_sampling_title_headers_and_export(
    probe, real_binary, monkeypatch, tmp_path, dynamic
):
    """Verify real wire seed sampling title headers and export."""
    from bench.tests.opencode_v2_mock import MockServer

    with MockServer() as mock:
        f = real_fixture(probe, monkeypatch, tmp_path, real_binary, mock)
        doc = json.loads(f["carrier"].read_text())
        doc["providers"]["mlx-local"]["models"][MODEL]["limit"]["output"] = 512
        f["carrier"].write_text(json.dumps(doc))
        if dynamic:
            del doc["providers"]["mlx-local"]["models"][MODEL]["body"]["max_tokens"]
            doc["providers"]["mlx-local"]["models"][MODEL]["limit"]["output"] = 512
            f["carrier"].write_text(json.dumps(doc))
        scratch_calls, real_scratch = [], probe._item_scratch_dir

        def spy_scratch(name):
            scratch_calls.append(name)
            return real_scratch(name)

        monkeypatch.setattr(probe, "_item_scratch_dir", spy_scratch)
        assert run_real(f, "one,two") == 0
        assert scratch_calls == ["one", "two"]      # the main path uses the FIXED per-item scratch dir
        rows = [json.loads(s) for s in f["out"].read_text().splitlines()]
        assert len(rows) == 2 and len(mock.chats) == 4
        assert rows[0]["sampler_seed"] != rows[1]["sampler_seed"]
        for row in rows:
            assert row["requests_observed"] == 2
            requests = [
                r
                for r in mock.chats
                if {k.lower(): v for k, v in r["headers"].items()}.get("x-session-id")
                == row["session_id"]
            ]
            assert len(requests) == 2
            for request in requests:
                body = request["body"]
                assert {k.lower(): v for k, v in request["headers"].items()}[
                    "authorization"
                ] == "Bearer not-needed"
                assert body["seed"] == row["sampler_seed"]
                for key in (
                    "temperature",
                    "top_p",
                    "top_k",
                    "min_p",
                    "presence_penalty",
                    "enable_thinking",
                    "thinking_budget",
                ):
                    assert body[key] == f["body"][key]
                if not dynamic:
                    assert body["max_tokens"] == f["body"]["max_tokens"]
                else:
                    assert body["max_tokens"] == 512
                assert "title generator" not in json.dumps(body["messages"]).lower()
            sent = requests[0]["body"].get("max_tokens")
            assert f["body"]["max_tokens"] == 102400
            assert row["max_tokens_semantics"] == (
                "fixed-by-carrier" if not dynamic else "v2-dynamic"
            )
            assert (
                row["max_tokens_evidence"]
                == "mock-capture:test_real_wire_seed_sampling_title_headers_and_export"
            )
            assert row["traffic"]["output_tokens"] > 0
            transcript = Path(row["transcript_path"].replace("$STACK_WORKDIR", str(tmp_path)))
            assert transcript.is_file() and transcript.is_relative_to(
                tmp_path / "opencode_transcripts"
            )
            assert (
                str(Path.home()) not in transcript.read_text()
                and probe._login_name() not in transcript.read_text()
            )
        manifest = json.loads(f["mp"].read_text())
        assert manifest["runtime"]["noretry_plugin_loaded_from"].endswith(
            "/cfg/opencode/plugins/noretry.js"
        )
        assert manifest["runtime"]["noretry_plugin_loaded_from"].startswith("$STACK_WORKDIR/")
        assert manifest["runtime"]["max_tokens_semantics"] == rows[0]["max_tokens_semantics"]
        assert manifest["runtime"]["max_tokens_evidence"] == rows[0]["max_tokens_evidence"]
        # C136 wiring on the main path: the tick comes from the model's documented rate, not the default 300
        assert manifest["runtime"]["tick_s"] == math.ceil(16000 / (2 * 24.2)) == 331
        assert manifest["runtime"]["first_write_tokens"] == 16000
        assert manifest["runtime"]["first_write_window_s"] == 662
        # fixed per-item scratch path and per-item TMPDIR on the main path (attempts 5-6)
        assert (tmp_path / "opencode-probe-v2" / "tmp" / "one").is_dir()
        assert mock.tripwire_hits == 0


def test_real_instruction_tools_hygiene_and_positive_control(
    probe, real_binary, monkeypatch, tmp_path
):
    """Verify real instruction tools hygiene and positive control."""
    from bench.tests.opencode_v2_mock import MockServer

    homes = [
        Path.home() / p for p in (".config/opencode", ".local/share/opencode", ".cache/opencode")
    ]

    def inventory():
        """Inventory."""
        return {
            str(p): p.stat().st_mtime_ns
            for root in homes
            if root.exists()
            for p in [root, *root.rglob("*")]
            if p.exists()
        }

    before = inventory()
    with MockServer() as mock:
        f = real_fixture(probe, monkeypatch, tmp_path, real_binary, mock)
        assert run_real(f) == 0
        first = mock.chats[0]["body"]
        system = json.dumps(first["messages"][0])
        assert all(s not in system for s in ("Instructions from", "AGENTS.md", "vnote"))
        tools = [t["function"]["name"] for t in first["tools"]]
        assert "execute" not in tools and "question" not in tools
        assert mock.tripwire_hits == 0
        run_dir = next((tmp_path / "opencode-probe-v2").glob("run-*"))
        listing = subprocess.check_output(["ps", "-axo", "command="], text=True)
        assert str(run_dir) not in listing
        assert inventory() == before
        # Positive control deliberately bypasses the probe's refusal to show the switch is causal.
        scratch = tmp_path / "positive"
        scratch.mkdir()
        probe._git_init_scratch(scratch)
        (scratch / "AGENTS.md").write_text("MARKER_PROJECT_INSTRUCTION: use the write tool.\n")
        env = probe._opencode_env(run_dir, scratch, probe._seed_overlay(MODEL, 22))
        del env["OPENCODE_DISABLE_PROJECT_CONFIG"]
        result = probe._capture(
            [
                real_binary,
                "run",
                "--standalone",
                "--model",
                "mlx-local/" + MODEL,
                "--format",
                "json",
                "--title",
                "probe",
                "Write solution.py with answer = 42.",
            ],
            scratch,
            env,
            30,
        )
        assert result.returncode == 0
        assert "Instructions from" in json.dumps(mock.chats[2]["body"]["messages"][0])


@pytest.mark.parametrize("kind", ["http500", "drop", "refuse", "ctx400"])
def test_real_transport_matrix(probe, real_binary, monkeypatch, tmp_path, kind):
    """Verify real transport matrix."""
    from bench.tests.opencode_v2_mock import MockServer

    with MockServer({1: kind}) as mock:
        f = real_fixture(probe, monkeypatch, tmp_path, real_binary, mock)
        start = time.monotonic()
        if kind == "ctx400":
            assert run_real(f) == 0
            row = json.loads(f["out"].read_text())
            assert row["nonconv_kind"] == "context_overflow" and row["passed"] is False
        else:
            with pytest.raises(SystemExit) as exc:
                run_real(f)
            assert exc.value.code != 0 and not f["out"].exists() and not f["grades"]
            doc = json.loads(f["mp"].read_text())
            assert doc["transport_abort"]["rc"] == 1
        if kind == "refuse":
            assert time.monotonic() - start < 10
        else:
            assert len(mock.chats) == 1


def test_real_destination_rejects_project_document(probe, real_binary, monkeypatch, tmp_path):
    """Verify real destination rejects project document."""
    from bench.tests.opencode_v2_mock import MockServer

    with MockServer() as mock:
        f = real_fixture(probe, monkeypatch, tmp_path, real_binary, mock)
        run = probe._make_run_dir(tmp_path, "destination")
        scratch = tmp_path / "project"
        scratch.mkdir()
        probe._git_init_scratch(scratch)
        (scratch / "opencode.json").write_text('{"compaction":{"auto":true}}')
        overlay = probe._seed_overlay(MODEL, 123)
        env = probe._opencode_env(run, scratch, overlay)
        assert (
            provenance.opencode_v2_destination(scratch, env, MODEL, run, real_binary, overlay)
            == mock.base
        )
        env.pop("OPENCODE_DISABLE_PROJECT_CONFIG")
        with pytest.raises(provenance.ServedConfigError, match="document"):
            provenance.opencode_v2_destination(scratch, env, MODEL, run, real_binary, overlay)


def test_brew_version_prefix_is_parsed_without_allowing_drift(probe):
    """Verify brew version prefix is parsed without allowing drift."""
    assert hasattr(probe, "_parse_version"), "brew emits opencode v2.0.20, not a bare version"
    assert probe._parse_version("opencode v2.0.20\n") == "2.0.20"
    assert probe._parse_version("2.0.20\n") == "2.0.20"
    assert probe._parse_version("opencode v2.0.21\n") != "2.0.20"


@pytest.mark.parametrize("what", ["missing_test", "grade_exception"])
def test_harness_grade_failure_aborts(probe, monkeypatch, tmp_path, what):
    """Verify harness grade failure aborts."""
    f = fixture_probe(probe, monkeypatch, tmp_path)
    original = probe._run_opencode

    def run(*args, **kwargs):
        """Run."""
        result = original(*args, **kwargs)
        if what == "missing_test":
            args[4].unlink()
        return result

    monkeypatch.setattr(probe, "_run_opencode", run)
    if what == "grade_exception":

        def broken(*a):
            """Broken."""
            raise RuntimeError("grader crashed")

        monkeypatch.setattr(probe, "_grade_python", broken)
    with pytest.raises(SystemExit):
        f["run"]("one")
    assert not f["out"].exists()
    assert json.loads(f["mp"].read_text())["transport_abort"]


def test_scratch_override_cannot_escape_workdir(probe, monkeypatch, tmp_path):
    """Verify scratch override cannot escape workdir."""
    monkeypatch.setenv("OPENCODE_PROBE_SCRATCH", str(tmp_path.parent / "outside"))
    assert Path(probe._scratch_root()).is_relative_to(tmp_path), "v2 scratch escaped STACK_WORKDIR"


def test_abort_keeps_export_evidence(probe, monkeypatch, tmp_path):
    """Verify abort keeps export evidence."""
    f = fixture_probe(probe, monkeypatch, tmp_path, "http500")
    with pytest.raises(SystemExit):
        f["run"]("one")
    path = next((tmp_path / "opencode-probe-v2/aborted").rglob("export.json"))
    assert path.read_text(), "transport abort discarded the available session export"


@pytest.mark.parametrize("kind", ["carrier", "plugin"])
def test_copy_rechecked_before_every_item(probe, monkeypatch, tmp_path, kind):
    """Verify copy rechecked before every item."""
    f = fixture_probe(probe, monkeypatch, tmp_path)
    original = probe._run_opencode

    def tamper(*args, **kwargs):
        """Tamper."""
        result = original(*args, **kwargs)
        config = Path(kwargs["env"]["OPENCODE_CONFIG_DIR"])
        (config / ("opencode.json" if kind == "carrier" else "plugins/noretry.js")).write_text(
            "changed"
        )
        return result

    monkeypatch.setattr(probe, "_run_opencode", tamper)
    with pytest.raises(SystemExit, match="M50 tripwire"):
        f["run"]()
    assert len(f["calls"].read_text().splitlines()) == 1


def test_unavailable_grader_is_skipped(probe, monkeypatch, tmp_path):
    """Verify unavailable grader is skipped."""
    f = fixture_probe(probe, monkeypatch, tmp_path)
    root = tmp_path / "polyglot"
    import shutil

    shutil.copytree(root / "python", root / "go")
    (root / "go/exercises/practice/one/.meta").mkdir()
    (root / "go/exercises/practice/one/.meta/config.json").write_text(
        json.dumps({"files": {"solution": ["solution.py"], "test": ["solution_test.py"]}})
    )
    monkeypatch.setattr(probe, "_docker_available", lambda: False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "probe",
            "--model",
            MODEL,
            "--items",
            "one",
            "--limit",
            "5",
            "--lang",
            "go",
            "--seed-base",
            "77",
            "--poll-s",
            "0.01",
            "--out",
            str(f["out"]),
        ],
    )
    assert probe.main() == 0
    row = json.loads(f["out"].read_text())
    assert row["acc"] is None and row["passed"] is None and row["skipped"] is True
    assert "docker unavailable" in row["grade_tail"]


@pytest.mark.parametrize("reason", ["stalled", "looping", "hard_ceiling"])
@pytest.mark.parametrize("error_type", ["aborted", "provider.transport"])
@pytest.mark.parametrize("final_assistant", [True, False])
def test_gate_kill_export_signature(
    probe, monkeypatch, tmp_path, reason, error_type, final_assistant
):
    """Only the gate's interrupted-step export is a gradeable kill."""
    f = fixture_probe(probe, monkeypatch, tmp_path, "no_error")
    f["export"].write_text(
        json.dumps(
            {
                "messages": [
                    {
                        "type": "assistant",
                        "finish": "error",
                        "error": {"type": error_type, "message": "Step interrupted"},
                    }
                ]
            }
        )
    )
    if not final_assistant:
        export = json.loads(f["export"].read_text())
        export["messages"].append({"type": "assistant", "content": []})
        f["export"].write_text(json.dumps(export))
    binary = Path(os.environ["OPENCODE_PROBE_BIN"])
    binary.write_text(
        binary.read_text().replace('exit "$(cat ', 'exec /bin/sleep 30\nexit "$(cat ')
    )
    original = progress_gate.run_progress_gated
    grade_result = probe._grade_result
    final_grades = []

    def final_grade(*args, **kwargs):
        """Track final row grading separately from progress-gate snapshot diagnostics."""
        final_grades.append(True)
        return grade_result(*args, **kwargs)

    monkeypatch.setattr(probe, "_grade_result", final_grade)

    def quick_gate(*args, **kwargs):
        """Kill the fake process through the real progress gate with short test bounds."""
        kwargs.update(tick_s=0.05, hard_ceiling_s=2, poll_s=0.01, stall_ticks=2, loop_repeats=100)
        if reason == "looping":
            kwargs.update(stall_ticks=100, loop_repeats=2)
        elif reason == "hard_ceiling":
            kwargs.update(tick_s=2, hard_ceiling_s=0.2)
        return original(*args, **kwargs)

    monkeypatch.setattr(progress_gate, "run_progress_gated", quick_gate)
    if error_type == "aborted" and final_assistant:
        assert f["run"]("one") == 0
        assert json.loads(f["out"].read_text())["nonconv_kind"] == reason
        assert final_grades
    else:
        with pytest.raises(SystemExit, match="assistant error"):
            f["run"]("one")
        assert not f["out"].exists() and not final_grades
        assert json.loads(f["mp"].read_text())["transport_abort"]


@pytest.mark.parametrize("kind", ["ok", "ctx400"])
def test_aborted_export_without_gate_kill_aborts(probe, monkeypatch, tmp_path, kind):
    """An interrupted assistant is invalid on completion and context overflow."""
    f = fixture_probe(probe, monkeypatch, tmp_path, kind)
    export = json.loads(f["export"].read_text())
    export["messages"][-1]["error"] = {"type": "aborted", "message": "Step interrupted"}
    f["export"].write_text(json.dumps(export))
    with pytest.raises(SystemExit, match="ABORT: .*assistant error"):
        f["run"]()
    assert not f["out"].exists() and not f["grades"]
    assert len(f["calls"].read_text().splitlines()) == 1
    assert json.loads(f["mp"].read_text())["transport_abort"]


def test_real_gate_kill_interrupted_export_is_row(probe, real_binary, monkeypatch, tmp_path):
    """Reproduce the reviewer's one-chunk hang using the real binary and gate."""
    from bench.tests.opencode_v2_mock import MockServer

    with MockServer({1: "hang"}) as mock:
        f = real_fixture(probe, monkeypatch, tmp_path, real_binary, mock)
        original = progress_gate.run_progress_gated
        export_session = probe._export_session

        def settled_export(*args, **kwargs):
            """Settled export."""
            deadline = time.monotonic() + 10
            while True:
                export = export_session(*args, **kwargs)
                if any(m.get("error") for m in export["messages"]):
                    return export
                assert time.monotonic() < deadline, "interrupted export did not settle"
                time.sleep(0.1)

        monkeypatch.setattr(probe, "_export_session", settled_export)

        def gate_after_chunk(*args, **kwargs):
            """Gate after chunk."""
            assert mock.stream_started.wait(15), "real binary never started streaming"
            return original(*args, **kwargs)

        monkeypatch.setattr(progress_gate, "run_progress_gated", gate_after_chunk)
        assert (
            f["run"]("one", extra=["--tick-s", "1", "--stall-ticks", "2", "--hard-ceiling-s", "20"])
            == 0
        )
        row = json.loads(f["out"].read_text())
        assert row["nonconv_kind"] == "stalled" and row["opencode_rc"] == -9
        transcript = Path(row["transcript_path"].replace("$STACK_WORKDIR", str(tmp_path)))
        export = json.loads(transcript.read_text())
        assert any(
            m.get("error") == {"type": "aborted", "message": "Step interrupted"}
            and m.get("finish") == "error"
            for m in export["messages"]
        )
        assert not json.loads(f["mp"].read_text()).get("transport_abort")
        assert len(mock.chats) == 1
        print("ROW: real binary gate kill, nonconv_kind=stalled, export=aborted")


@pytest.mark.parametrize(
    "mutation",
    [None, "pass", "run_id", "router", "model", "exe_sha256", "carrier_sha256", "opencode_version"],
)
def test_a4_receipt_exact_writer_shape(probe, tmp_path, mutation):
    """The gate's receipt binds PASS to this router, model, binary and carrier."""
    receipt = {
        "pass": True,
        "model": MODEL,
        "opencode_version": "2.0.20",
        "exe_sha256": "exe",
        "run_id": "gate-run",
        "router": {"pid": 123},
        "router_pid": 123,
        "carrier_sha256": "carrier",
    }
    if mutation:
        receipt[mutation] = {"pid": 456} if mutation == "router" else False
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt))
    args = (path, {"pid": 123}, None, MODEL, "exe", "carrier")
    if mutation:
        with pytest.raises(SystemExit, match="A4"):
            probe._a4_receipt(*args)
    else:
        assert probe._a4_receipt(*args) == receipt


@pytest.mark.parametrize("limit", [None, 6, 22])
def test_a4_required_outside_explicit_smoke(probe, monkeypatch, tmp_path, limit):
    """Short legs cannot evade A4 through an omitted chain total."""
    f = fixture_probe(probe, monkeypatch, tmp_path)
    with pytest.raises(SystemExit, match="A4"):
        f["run"](",".join("item" + str(i) for i in range(22)), limit=limit)
    assert not f["calls"].exists()


@pytest.mark.parametrize(
    "receipt_sha,entry_sha",
    [("same", "same"), ("stale", "current"), (None, "current"), ("old", None)],
)
def test_a4_receipt_config_hash(probe, tmp_path, receipt_sha, entry_sha):
    """Compare router config hashes when both receipt and entry provide them."""
    receipt = {
        "pass": True,
        "run_id": "gate-run",
        "router": {"pid": 123},
        "router_pid": 123,
        "model": MODEL,
        "opencode_version": "2.0.20",
        "exe_sha256": "exe",
        "carrier_sha256": "carrier",
    }
    router = {"pid": 123}
    if receipt_sha is not None:
        receipt["router"]["config_sha256"] = receipt_sha
    if entry_sha is not None:
        router["config_sha256"] = entry_sha
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt))
    args = (path, router, None, MODEL, "exe", "carrier")
    if receipt_sha is not None and entry_sha is not None and receipt_sha != entry_sha:
        with pytest.raises(SystemExit, match="REFUSED: A4"):
            probe._a4_receipt(*args)
    else:
        assert probe._a4_receipt(*args) == receipt


@pytest.mark.parametrize("failure", ["timeout", "malformed_list", "document_mismatch"])
@pytest.mark.parametrize("first_item", [True, False])
def test_destination_failure_is_resumable(probe, monkeypatch, tmp_path, failure, first_item):
    """Destination proof failures abort without poisoning continuation as router drift."""
    f = fixture_probe(probe, monkeypatch, tmp_path)
    original = provenance.opencode_v2_destination
    calls = []
    errors = []

    def destination(*args, **kwargs):
        """Destination."""
        calls.append(args[0])
        if len(calls) == (2 if first_item else 3):
            if failure == "timeout":
                error = subprocess.TimeoutExpired(str(Path.home() / "api/config"), 120)
            else:
                error = provenance.ServedConfigError(
                    "M50 tripwire: " + failure + " " + str(Path.home() / "api/config")
                )
            errors.append(error)
            raise error
        return original(*args, **kwargs)

    monkeypatch.setattr(provenance, "opencode_v2_destination", destination)
    with pytest.raises(SystemExit):
        f["run"]()
    manifest = json.loads(f["mp"].read_text())
    assert manifest["transport_abort"]["signature"] == "destination_check"
    assert manifest["transport_abort"]["error"] == probe._scrub_error(errors[0], 1000)
    assert str(Path.home()) not in manifest["transport_abort"]["error"]
    assert "served_config_drift" not in manifest
    monkeypatch.setattr(provenance, "opencode_v2_destination", original)
    assert f["run"]() == 0
    assert len(f["out"].read_text().splitlines()) == 2


def test_real_missing_print_logs_refuses(probe, real_binary, monkeypatch, tmp_path):
    """Removing the discovery logging request must make plugin proof impossible."""
    from bench.tests.opencode_v2_mock import MockServer

    with MockServer() as mock:
        f = real_fixture(probe, monkeypatch, tmp_path, real_binary, mock)
        original = provenance.opencode_v2_destination

        def without_logging(scratch, env, *args, **kwargs):
            """Without logging."""
            env = dict(env)
            env.pop("OPENCODE_PRINT_LOGS", None)
            return original(scratch, env, *args, **kwargs)

        monkeypatch.setattr(provenance, "opencode_v2_destination", without_logging)
        with pytest.raises(SystemExit, match="plugin") as exc:
            f["run"]("one")
        assert not mock.chats and not f["out"].exists()
        print("REFUSED: real binary discovery without OPENCODE_PRINT_LOGS: " + str(exc.value))


def test_retried_then_stalled_aborts(probe, monkeypatch, tmp_path):
    """The gate cannot hide two consecutive request starts."""
    f = fixture_probe(probe, monkeypatch, tmp_path, "retry")
    original = probe._run_opencode

    def killed(*args, **kwargs):
        """Killed."""
        rc, log, elapsed, gate = original(*args, **kwargs)
        gate.stop_reason = "stalled"
        return -9, log, elapsed, gate

    monkeypatch.setattr(probe, "_run_opencode", killed)
    with pytest.raises(SystemExit, match="consecutive step_start"):
        f["run"]("one")
    assert not f["out"].exists() and not f["grades"]


def test_instruction_sources_observed(probe, monkeypatch, tmp_path):
    """Record actual scratch ancestors and bench HOME, including unexpected sources."""
    f = fixture_probe(probe, monkeypatch, tmp_path)
    ancestor = tmp_path / "AGENTS.md"
    ancestor.write_text("ancestor marker\n")
    original = probe._make_run_dir
    home_sources = []

    def with_instructions(*args, **kwargs):
        """With instructions."""
        run = original(*args, **kwargs)
        source = run / "home/CLAUDE.md"
        source.write_text("bench home marker\n")
        home_sources.append(source)
        return run

    monkeypatch.setattr(probe, "_make_run_dir", with_instructions)
    assert f["run"]("one") == 0
    sources = json.loads(f["mp"].read_text())["runtime"]["instruction_sources"]
    for path in [ancestor, *home_sources]:
        assert sources[probe._portable(path)] == probe._sha_of(path)


def test_continuation_history_is_slim(probe, monkeypatch, tmp_path):
    """Continuation records never recursively embed previous histories or abort artifacts."""
    f = fixture_probe(probe, monkeypatch, tmp_path)
    assert f["run"]("one") == 0
    old = json.loads(f["mp"].read_text())
    old["continuation_history"] = [{"timestamp": "older"}]
    old["transport_abort"] = {"signature": "old failure"}
    f["mp"].write_text(json.dumps(old))
    assert f["run"]() == 0
    history = json.loads(f["mp"].read_text())["continuation_history"]
    assert history[0] == {"timestamp": "older"}
    assert history[1] == {
        key: old.get(key)
        for key in ("timestamp", "model", "git", "router", "router_exit", "runtime")
    }


@pytest.mark.parametrize("key", ["PATH", "TERM", "NO_COLOR"])
def test_visible_env_values_affect_policy_hash(probe, monkeypatch, tmp_path, key):
    """The policy hash binds all fixed environment values visible to the child."""
    f = fixture_probe(probe, monkeypatch, tmp_path)
    assert f["run"]("one") == 0
    assert key in probe.SCAFFOLD_ENV_POLICY_V2
    monkeypatch.setitem(probe.SCAFFOLD_ENV_POLICY_V2, key, "changed")
    with pytest.raises(SystemExit, match="scaffold_policy_sha256"):
        f["run"]()


def test_a4_receipt_binds_run_and_manifest(probe, monkeypatch, tmp_path):
    """Consume the gate shape through main and preserve its run id in the manifest."""
    f = fixture_probe(probe, monkeypatch, tmp_path)
    receipt = {
        "pass": True,
        "model": MODEL,
        "opencode_version": "2.0.20",
        "exe_sha256": probe._sha_of(Path(os.environ["OPENCODE_PROBE_BIN"])),
        "run_id": "gate-run",
        "router": f["router"],
        "router_pid": f["router"]["pid"],
        "carrier_sha256": probe._sha_of(f["carrier"]),
    }
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt))
    assert f["run"]("one", limit=None, extra=["--a4-v2-receipt", str(path)]) == 0
    runtime = json.loads(f["mp"].read_text())["runtime"]
    assert runtime["a4_v2_pass"] is True and runtime["a4_gate_run_id"] == "gate-run"
