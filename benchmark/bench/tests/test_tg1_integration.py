"""M62 real pinned-client oracles use a mock HTTP model, never inference."""

import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from bench import tg1_runner as runner, structured_grade as sg
from bench.tests.test_opencode_v2_probe import probe, fixture_probe, MODEL
from bench.tests.opencode_v2_mock import MockServer
from m62 import universe_preflight as up


def tg_fixture(probe, monkeypatch, tmp_path, *, binary=None, mock=None):
    p = probe
    destination = runner.provenance.opencode_v2_destination
    f = fixture_probe(p, monkeypatch, tmp_path)
    carrier = json.loads(p.BENCH_OPENCODE_WEB_CONFIG.read_text())
    carrier["permissions"].append(dict(action="subagent", resource="*", effect="deny"))
    if mock:
        carrier["providers"]["mlx-local"]["settings"]["baseURL"] = mock.base
        carrier["providers"]["vllm"]["settings"]["baseURL"] = mock.base.replace(
            "/v1", "/vllm-tripwire/v1"
        )
    f["carrier"].write_text(json.dumps(carrier))
    monkeypatch.setattr(runner, "CARRIER", f["carrier"])
    identity = dict(
        pid=1234, create_time=100, model_path="fixture/model", registry_sha256="sha"
    )
    monkeypatch.setattr(runner, "worker_identity", lambda *a: dict(identity))
    monkeypatch.setattr(
        runner,
        "worker_json",
        lambda endpoint: (
            {
                "configured_context_limit": carrier["providers"]["mlx-local"]["models"][
                    MODEL
                ]["limit"]["context"]
            }
            if endpoint == "health"
            else {"summary": {"in_flight": 0}}
        ),
    )
    doc = {"grader_version": sg.VERSION, "items": {}}
    for name in ("one", "two"):
        src = tmp_path / "polyglot/python/exercises/practice" / name
        prepared = sg.manifest(src)
        doc["items"]["python/" + name] = dict(
            solution="solution.py",
            test="solution_test.py",
            prepared=prepared,
            protected=sg.protected_manifest(prepared, ["solution.py"]),
            leaves=[["solution_test.py", "solution_test", "test_answer"]],
            baseline_failing=1,
            grader_version=sg.VERSION,
        )
    universe = tmp_path / "universe.json"
    up.freeze(universe, doc)
    if binary:
        monkeypatch.setenv("OPENCODE_PROBE_BIN", binary)
        monkeypatch.setattr(runner.provenance, "opencode_v2_destination", destination)
    else:
        export = json.loads(f["export"].read_text())
        for i, m in enumerate(export["messages"]):
            m["id"] = "m" + str(i + 1)
            m["tokens"]["reasoning"] = 0
            m["finish"] = "stop"
            m["tokens"]["cache"] = {"read": 0, "write": 0}
        f["export"].write_text(json.dumps(export))
        from bench.tests.test_token_turn_gate import event, usage

        (tmp_path / "events.jsonl").write_text(
            "".join(
                json.dumps(e) + "\n"
                for e in [
                    event("step_start"),
                    event("step_finish", tokens=usage(10, 100)),
                    event("step_start", "m2"),
                ]
            )
        )

    def run(items="one", extra=()):
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
                "--scaffold",
                "opencode-v2-web-tg1",
                "--limit",
                "5",
                "--out",
                str(f["out"]),
                "--universe",
                str(universe),
                *extra,
            ],
        )
        return p.main()

    f["run"] = run
    f["identity"] = identity
    return f


def test_mocked_tg1_rows_evidence_resume_and_worker_drift(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    assert f["run"]("one", extra=["--expect-items", "python/one"]) == 0
    row = json.loads(f["out"].read_text())
    assert (
        row["passed"]
        and row["gate"]["requests_completed"] == 2
        and row["nonconv_kind"] is None
    )
    assert row["worker_before"] == row["worker_after"] == f["identity"]
    assert row["request_usage"][0][1:] == [10, 100, 81920]
    assert all(row["evidence_sha256"].values())
    path = Path(row["events_path"].replace("$STACK_WORKDIR", str(tmp_path)))
    assert path.is_relative_to(tmp_path / "opencode_transcripts") and f[
        "out"
    ].stem + "." in str(path)
    assert f["run"]("one") == 0
    f["identity"]["create_time"] = 101
    with pytest.raises(SystemExit, match="identity"):
        f["run"]("two")


def test_tg1_protected_final_edit_fails(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    binary = Path(os.environ["OPENCODE_PROBE_BIN"])
    binary.write_text(
        binary.read_text().replace("run)\n", "run)\necho hacked > solution_test.py\n")
    )
    assert f["run"]() == 0
    row = json.loads(f["out"].read_text())
    assert row["test_modified"] and not row["passed"]


def test_resume_accepts_gather_runtime_observations(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    gather = runner.provenance.gather

    def with_observations(*args, **kwargs):
        doc = gather(*args, **kwargs)
        doc["runtime"] = {**doc["runtime"], "draft_kind": "off", "apc_enabled": False}
        return doc

    monkeypatch.setattr(runner.provenance, "gather", with_observations)
    assert f["run"]() == 0
    assert f["run"]("two") == 0


def test_driver_registry_export_does_not_leak_to_caller(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    monkeypatch.delenv("MLX_SERVE_CONFIG", raising=False)
    assert f["run"]() == 0
    assert os.environ.get("MLX_SERVE_CONFIG") is None


@pytest.fixture
def pinned_binary(probe, tmp_path):
    from bench.tests.test_opencode_v2_probe import INSTALLED_BIN
    path = INSTALLED_BIN
    if not path.is_file():
        if not os.environ.get("OPENCODE_PROBE_BIN"):
            pytest.skip("bench opencode 2.0.20 not installed (scripts/install_bench_opencode.sh)")
        pytest.fail("OPENCODE_PROBE_BIN missing")
    env = probe._opencode_env(tmp_path, tmp_path, probe._seed_overlay(MODEL, 1))
    try:
        r = subprocess.run(
            [str(path), "--version"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except PermissionError as exc:
        pytest.skip("diagnosed sandbox start denial: " + str(exc))
    if r.returncode and any(
        x in r.stderr
        for x in ("EPERM", "EACCES", "Operation not permitted", "Permission denied")
    ):
        pytest.skip("diagnosed sandbox start denial: " + r.stderr)
    assert r.returncode == 0 and probe._parse_version(r.stdout) == "2.0.20"
    return str(path.resolve())


@pytest.mark.parametrize(
    "inputs,bound",
    [
        ({"background": True}, "background must be false"),
        ({"timeout": 0}, "between 1 and 600000"),
        ({"timeout": 600001}, "between 1 and 600000"),
    ],
)
def test_real_toolbounds_feedback_continuation_and_exact_count(
    probe, pinned_binary, monkeypatch, tmp_path, inputs, bound
):
    with MockServer(
        {1: dict(name="shell", input={"command": "echo forbidden", **inputs})}
    ) as mock:
        f = tg_fixture(probe, monkeypatch, tmp_path, binary=pinned_binary, mock=mock)
        # Isolate execution from the separately tested config-endpoint activation race.
        monkeypatch.setattr(
            runner.provenance, "opencode_v2_destination", lambda *a, **k: mock.base
        )
        assert f["run"]() == 0
        row = json.loads(f["out"].read_text())
        assert row["tool_bounds_rejections"] == 1 and len(mock.chats) == 2
        assert bound in json.dumps(mock.chats[1]["body"]["messages"])
        assert row["nonconv_kind"] is None and row["gate"]["requests_completed"] == 2
        body = mock.chats[0]["body"]
        tools = [x["function"]["name"] for x in body["tools"]]
        assert "subagent" not in tools and "execute" not in tools
        assert "title generator" not in json.dumps(body["messages"]).lower()
        assert mock.tripwire_hits == 0


@pytest.mark.parametrize("tool", ["subagent", "execute"])
def test_real_subagent_and_code_mode_denied(
    probe, pinned_binary, monkeypatch, tmp_path, tool
):
    with MockServer({1: dict(name=tool, input={})}) as mock:
        f = tg_fixture(probe, monkeypatch, tmp_path, binary=pinned_binary, mock=mock)
        monkeypatch.setattr(
            runner.provenance, "opencode_v2_destination", lambda *a, **k: mock.base
        )
        assert f["run"]() == 0
        assert len(mock.chats) == 2
        assert tool not in [
            x["function"]["name"] for x in mock.chats[0]["body"]["tools"]
        ]
        feedback = [
            m for m in mock.chats[1]["body"]["messages"] if m.get("role") == "tool"
        ]
        assert feedback and any(
            "error" in json.dumps(m).lower() or "not found" in json.dumps(m).lower()
            for m in feedback
        )


def test_real_tg1_preflight_proves_both_plugins(
    probe, pinned_binary, monkeypatch, tmp_path
):
    with MockServer() as mock:
        f = tg_fixture(probe, monkeypatch, tmp_path, binary=pinned_binary, mock=mock)
        assert f["run"]() == 0


def test_f6_structured_final_success_ignores_helper_package_failure(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    # A Go helper package may fail even though every reference leaf passed.
    monkeypatch.setattr(sg, 'grade', lambda *a, **k: sg.Grade(
        passing={('solution_test.py','solution_test','test_answer')}, returncode=1))
    monkeypatch.setattr(probe, '_grade', lambda *a, **k: pytest.fail('legacy grader called'), raising=False)
    assert f['run']() == 0
    assert json.loads(f['out'].read_text())['passed']


@pytest.mark.parametrize('reconciles', [True, False])
def test_f1_client_exit_hang_terminal_path(probe, monkeypatch, tmp_path, reconciles):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    binary = Path(os.environ['OPENCODE_PROBE_BIN'])
    binary.write_text(binary.read_text().replace('\nexit "$(cat ', '\nsleep 10\nexit "$(cat '))
    monkeypatch.setitem(runner.pg.POLICY, 'silence_s', 0.05)
    monkeypatch.setitem(runner.pg.POLICY, 'silence_sample_s', 0.1)
    monkeypatch.setitem(runner.pg.POLICY, 'idle_min_spacing_s', 0.05)
    monkeypatch.setattr(runner.pg.ProcessGuard, 'descendants_alive', lambda self: False)
    if not reconciles:
        exported = json.loads(f['export'].read_text())
        exported['messages'][-1]['error'] = {'type':'aborted'}
        f['export'].write_text(json.dumps(exported))
        with pytest.raises(SystemExit, match='client silent, worker idle'):
            f['run']()
        assert not f['out'].exists()
    else:
        assert f['run']() == 0
        row = json.loads(f['out'].read_text())
        assert row['passed'] and row['client_exit_hang'] and row['nonconv_kind'] is None
        assert row['silence_observations'][-1]['idle_samples'] == 3


def test_untouched_solution_fails_even_when_stub_passes(probe, monkeypatch, tmp_path):
    """go/ledger and go/markdown stubs pass every test (refactoring exercises; V1b 2026-10-10): the M59/M61 rule
    "solution file untouched -> fail" stays under tg1 (F6 removed only the second grader)."""
    f = tg_fixture(probe, monkeypatch, tmp_path)
    binary = Path(os.environ['OPENCODE_PROBE_BIN'])
    binary.write_text(binary.read_text().replace('printf "answer = 42\\n" > solution.py', ':'))
    monkeypatch.setattr(sg, 'grade', lambda *a, **k: sg.Grade(
        passing={('solution_test.py','solution_test','test_answer')}, returncode=0))
    assert f['run']() == 0
    row = json.loads(f['out'].read_text())
    assert not row['file_changed'] and not row['passed'] and row['acc'] == 0 and not row['test_modified']
