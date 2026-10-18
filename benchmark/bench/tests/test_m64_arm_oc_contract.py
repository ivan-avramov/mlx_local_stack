"""M64 spec 6: the opencode arm (M64 configuration, real pinned client, mock provider) through the contract suite, plus
the opencode-specific controls of C165 2b / 2c / 2d."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest

from bench import arm_adapter as aa
from bench import arm_opencode as ao
from bench import arm_opencode, arm_runner, model_params, rowschema
from bench.tests.arm_entry import m64_main
from bench import token_turn_gate as tg
from bench.tests import arm_contract_suite as cs
from bench.tests.opencode_v2_mock import MockServer
from bench.tests.test_opencode_v2_probe import MODEL, tg1_probe as probe          # noqa: F401  (fixture)
from bench.tests.test_tg1_integration import FROZEN, pinned_binary, tg_fixture      # noqa: F401  (fixtures)
from bench.tests.test_token_turn_gate import event, usage

REPO = Path(__file__).resolve().parents[3]
DEFAULT_USAGE = dict(prompt_tokens=100, completion_tokens=10)


def entry_parser():
    """The M64 oc entry's own argument parser (its label, `--epoch-id`); the tg1 entry module stays the namespace the
    fixtures patch."""
    import importlib
    return importlib.import_module("run_oc_probe")._parser()


class OcHarness(cs.ArmHarness):
    """The real pinned opencode against the scripted mock, driven through `arm_runner.main` (the full pipeline)."""
    timeout_configurable = False
    search_required = True
    reduced_window = 20000

    def __init__(self, probe, binary, monkeypatch, tmp_path):
        self.p, self.binary, self.mp, self.tmp = probe, binary, monkeypatch, tmp_path
        self.n = 0
        monkeypatch.setenv("OPENCODE_PROBE_BIN", str(binary))
        self.adapter = ao.OpencodeArm(probe, mode="m64", search=ao.OfflineTestSearchService())
        deployed = {k: v for k, v in model_params.params_for(MODEL, profile="deployed").items()
                    if k != "reasoning_effort"}                     # the wire never carries it (opencode body)
        self.expected = cs.ExpectedWire(
            sampling={**deployed, "seed": rowschema.sample_seed("python/one", 0, 77)},
            roles={"system", "user", "assistant", "tool"}, required_tools={"shell", "write", "read", "edit"})

    # -- fixture plumbing
    def _carrier(self, mock, window):
        doc = json.loads((REPO / "benchmark/opencode_bench_v2_web_tg1.json").read_text())
        mlx = doc["providers"]["mlx-local"]
        mlx["settings"]["baseURL"] = mock.base
        doc["providers"]["vllm"]["settings"]["baseURL"] = mock.base.replace("/v1", "/vllm-tripwire/v1")
        if window:
            mlx["models"][MODEL]["limit"] = dict(context=window, input=window - 1000, output=1000)
        path = self.tmp / f"carrier-{self.n}.json"
        path.write_text(json.dumps(doc))
        return path, mlx["models"][MODEL]["limit"]["context"]

    def _setup(self, mock, window):
        self.n += 1
        sub = self.tmp / f"run{self.n}"
        sub.mkdir()
        f = tg_fixture(self.p, self.mp, sub, binary=self.binary, mock=mock)
        carrier, context = self._carrier(mock, window)
        self.mp.setattr(arm_opencode, "CARRIER", carrier)
        self.mp.setattr(arm_runner, "worker_json", lambda endpoint: ({"configured_context_limit": context}
                                                             if endpoint == "health" else {"summary": {"in_flight": 0}}))
        return f, sub

    def _argv(self, sub, out, extra):
        limit = ["--limit", "1" if "--tg1-inject" in extra else "5"]           # an inject run is exactly one item
        return ["probe", "--model", MODEL, "--items", "one", "--seed-base", "77", "--scaffold", "opencode-v2-web-tg1c",
                *limit, "--out", str(out), "--universe", str(self.tmp / f"run{self.n}" / "universe.json"),
                "--frozen-prompt-date", FROZEN, *extra]

    def run(self, script, *, window=None, gate_overrides=None, inject=None):
        with MockServer(script) as mock:
            f, sub = self._setup(mock, window)
            out = sub / "rows.jsonl"
            extra = []
            if inject:
                out = Path(os.environ["STACK_WORKDIR"]) / "m62/inject" / f"rows{self.n}.jsonl"
                extra = ["--tg1-inject", inject, "--expect-items", "python/one"]
            argv = self._argv(sub, out, extra)
            self.mp.setattr(sys, "argv", argv)
            a = entry_parser().parse_args(argv[1:])
            a.gate_overrides = gate_overrides
            adapter = ao.OpencodeArm(self.p, mode="m64", search=ao.OfflineTestSearchService())
            abort, row = None, None
            try:
                m64_main(self.p, adapter, a)
            except SystemExit as exc:
                abort = exc if exc.code not in (0, None) else None
            if out.exists():
                row = json.loads(out.read_text().splitlines()[0])
            seen = adapter.observed or {}
            wire = [(c["body"], self._usage_of(script, i)) for i, c in enumerate(mock.chats, 1)]
            compaction = [u for body, u in wire if self._is_compaction(body)]
            task = [u for body, u in wire if not self._is_compaction(body)]
            return cs.ArmRun(
                requests=[cs.WireRequest(c["path"], c["headers"], c["body"]) for c in mock.chats],
                events=seen.get("events", []), reconciliation=seen.get("reconciliation"), abort=abort, row=row,
                gate=(row or {}).get("gate", {}), flags=(row or {}).get("nonconv_flags", []),
                wire_compaction_usage=[self._tokens(u) for u in compaction], wire_usage=task,
                tool_windows=seen.get("tool_windows", []))

    @staticmethod
    def _is_compaction(body):
        last = (body.get("messages") or [{}])[-1].get("content")
        return isinstance(last, str) and last.startswith("You MUST summarize the conversation above")

    @staticmethod
    def _usage_of(script, i):
        kind = script.get(i)
        return kind["usage"] if isinstance(kind, dict) and "usage" in kind else DEFAULT_USAGE

    @staticmethod
    def _tokens(u):
        return dict(input=u["prompt_tokens"], cache_read=0, cache_write=0, output=u["completion_tokens"], reasoning=0)

    def compaction_script(self):
        return {1: {"name": "write", "input": {"path": "solution.py", "content": "answer = 42\n"},
                    "usage": {"prompt_tokens": 19500, "completion_tokens": 10, "total_tokens": 19510}}}

    # -- terminal shapes without a client: the stream/export pairs the registered shapes produce
    def shape(self, name):
        gate = tg.TokenTurnGate(3)
        stream = self.adapter.new_stream(gate, lambda n: None)
        base = [event("step_start"), event("step_finish", tokens=usage(10, 100))]

        def assistant(mid, finish="stop", **kw):
            return dict(id=mid, type="assistant", finish=finish, content=[], tokens=dict(
                input=100, output=10, reasoning=0, cache=dict(read=0, write=0)), **kw)

        def feed(evs):
            stream.feed("".join(json.dumps(e) + "\n" for e in evs).encode())

        rc, outcome = 0, None
        if name in ("stop", "length"):
            feed(base)
            export = {"messages": [assistant("m1", finish=name)]}
        elif name == "cancel":
            feed(base + [event("step_start", "m2")])
            stream.signal_offset = 0
            export = {"messages": [assistant("m1", finish="tool-calls"), dict(
                id="m2", type="assistant", finish="error", tokens=None, error=dict(type="aborted"), content=[])]}
            rc, outcome = 143, "runner_cancel"
        elif name.startswith("client_cut:"):
            feed(base + [event("step_start", "m2"), dict(type="error", sessionID="s1", error=dict(
                type="aborted", message="Session interrupted: inactivity"))])
            export = {"messages": [assistant("m1", finish="tool-calls"), dict(
                id="m2", type="assistant", finish="error", tokens=None, error=dict(
                    type="aborted", message="Step interrupted"), content=[],
                time=dict(created=1_000, streamed=3_634_000, completed=3_634_070))]}
            rc = 1
        elif name == "error":
            feed([event("step_start"), dict(type="error", sessionID="s1", error=dict(type="mystery.failure"))])
            export = {"messages": [assistant("m1")]}
            rc = 1
        else:                                    # unregistered: a nonzero exit that no registered shape explains
            feed(base)
            export = {"messages": [assistant("m1")]}
            rc = 7
        try:
            rec = self.adapter.reconcile(stream, ao.Transcript(raw="", doc=export), None, rc, outcome)
            return cs.ArmRun(requests=[], reconciliation=rec, events=self.adapter.events(stream))
        except tg.TransportAbort as exc:
            return cs.ArmRun(requests=[], abort=exc)

    def run_without_search_service(self):
        try:
            ao.OpencodeArm(self.p, mode="m64").selection()                  # the default: the D2 stub
        except aa.ArmRefused as exc:
            return exc
        return None


@pytest.fixture
def stack_workdir_inject(tmp_path):
    (Path(os.environ["STACK_WORKDIR"]) / "m62/inject").mkdir(parents=True, exist_ok=True)


class TestOpencodeArmContract(cs.ArmContractSuite):
    @pytest.fixture
    def harness(self, probe, pinned_binary, monkeypatch, tmp_path):
        (Path(os.environ["STACK_WORKDIR"]) / "m62/inject").mkdir(parents=True, exist_ok=True)
        return OcHarness(probe, pinned_binary, monkeypatch, tmp_path)


# ---------------------------------------------------------------- opencode-specific controls (C165 2b / 2c / 2d)
@pytest.fixture
def harness(probe, pinned_binary, monkeypatch, tmp_path):
    (Path(os.environ["STACK_WORKDIR"]) / "m62/inject").mkdir(parents=True, exist_ok=True)
    return OcHarness(probe, pinned_binary, monkeypatch, tmp_path)


def test_compaction_runs_end_to_end_into_the_row_with_receipts_reconciled(harness):
    run = harness.run(harness.compaction_script(), window=harness.reduced_window)
    assert run.abort is None and run.row is not None
    c = run.row["compaction"]
    assert c["count"] == 1 and c["completion_tokens"] == 10 and c["receipts"] == 1 and c["accounting_complete"] is True
    assert run.row["scaffold"] == "opencode-v2-web-tg1c" and run.row["carrier_transform"] == "opencode-v2-web-tg1c"
    assert run.row["nonconv_kind"] is None and run.row["passed"] is True
    summary_requests = [r for r in run.requests if harness._is_compaction(r.body)]
    assert len(summary_requests) == 1 and len(run.requests) == 4     # task, summary, the continued task, its final
    # the summary request carries the same sampling, seed and budgets as a task request (counted, never silent)
    assert summary_requests[0].body["seed"] == run.requests[0].body["seed"]
    assert summary_requests[0].body["thinking_budget"] == 81920


def test_without_a_reduced_window_no_compaction_happens_and_the_block_is_empty(harness):
    run = harness.run({})
    assert run.abort is None and run.row["compaction"]["count"] == 0
    assert run.row["compaction"]["accounting_complete"] is True and run.row["shell_watchdog"]["kills"] == []


def test_the_exposed_context_is_262144_and_checked_against_health(probe, pinned_binary, monkeypatch, tmp_path):
    h = OcHarness(probe, pinned_binary, monkeypatch, tmp_path)
    with MockServer({}) as mock:
        f, sub = h._setup(mock, None)
        monkeypatch.setattr(arm_runner, "worker_json", lambda endpoint: ({"configured_context_limit": 131072}
                                                                 if endpoint == "health" else {"summary": {"in_flight": 0}}))
        a = entry_parser().parse_args(h._argv(sub, sub / "rows.jsonl", [])[1:])
        with pytest.raises(SystemExit, match="configured_context_limit differs from carrier"):
            m64_main(probe, h.adapter, a)
        assert not (sub / "rows.jsonl").exists() and mock.chats == []


def test_the_m64_arm_refuses_before_any_effect_without_the_search_service(probe, pinned_binary, monkeypatch, tmp_path):
    h = OcHarness(probe, pinned_binary, monkeypatch, tmp_path)
    with MockServer({}) as mock:
        f, sub = h._setup(mock, None)
        a = entry_parser().parse_args(h._argv(sub, sub / "rows.jsonl", [])[1:])
        monkeypatch.setattr(sys, "argv", ["probe", *h._argv(sub, sub / "rows.jsonl", [])[1:]])
        before = sorted(p.name for p in Path(os.environ["STACK_WORKDIR"]).iterdir())
        with pytest.raises(SystemExit, match="REFUSED: the shared search service"):
            m64_main(probe, ao.OpencodeArm(probe, mode="m64"), a)
        assert mock.requests == [] and not (sub / "rows.jsonl").exists()
        assert sorted(p.name for p in Path(os.environ["STACK_WORKDIR"]).iterdir()) == before     # no run dir, no manifest


def test_the_probe_entry_exists_and_prints_a_refusal_not_an_identity_without_the_service(monkeypatch, tmp_path):
    import importlib
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    entry = importlib.import_module("run_oc_probe")
    monkeypatch.setattr(sys, "argv", ["run_oc_probe", "--print-identity"])
    with pytest.raises(SystemExit, match="shared search service"):
        entry.main()


def test_a_shell_descendant_past_the_deadline_flags_exec_timeout_in_the_row(probe, monkeypatch, tmp_path):
    """Spec 5.4 through the runner: a background child of the client, started inside a tool window the client reported,
    is killed after the (shortened) deadline and the row carries the flag and the kill record. (opencode 2.0.20 reports
    a tool only when it completes, so the window is learned from its `tool_use` event and the child attributed then.)"""
    import time as _time
    f = tg_fixture(probe, monkeypatch, tmp_path)
    monkeypatch.setattr(arm_opencode, "CARRIER", REPO / "benchmark/opencode_bench_v2_web_tg1.json")
    monkeypatch.setattr(arm_runner, "worker_json", lambda e: (
        {"configured_context_limit": 262144} if e == "health" else {"summary": {"in_flight": 0}}))
    now = _time.time()
    window = dict(start=int((now - 5) * 1000), end=int((now + 600) * 1000))
    (tmp_path / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in [
        event("step_start"),
        dict(type="tool_use", sessionID="s1", part=dict(partID="p-t1", id="t1", messageID="m1", type="tool",
                                                         tool="shell", state=dict(
            status="completed", input={"command": "sleep 311 &"}, output="", title="shell", metadata={},
            time=window))),
        event("step_finish", tokens=usage(10, 100)),
        event("step_start", "m2"),
    ]))
    binary = Path(os.environ["OPENCODE_PROBE_BIN"])
    binary.write_text(binary.read_text().replace("run)\n", "run)\nsleep 311 &\n", 1)
                      .replace('\nexit "$(cat ', '\nsleep 5\nexit "$(cat ', 1))
    adapter = ao.OpencodeArm(probe, mode="m64", search=ao.OfflineTestSearchService())
    import dataclasses
    from bench import run_config as rc
    template = dataclasses.replace(ao.m64_template(), watchdog=rc.watchdog_on(limit_s=1.0, grace_s=0.5, toolwindows_sha256="w" * 64))
    monkeypatch.setattr(adapter, "_prove_plugins", lambda *a, **k: None)      # the fake client has no plugin API
    out = tmp_path / "rows.jsonl"
    argv = ["probe", "--model", MODEL, "--items", "one", "--seed-base", "77", "--scaffold", "opencode-v2-web-tg1c",
            "--limit", "5", "--out", str(out), "--universe", str(tmp_path / "universe.json"),
            "--frozen-prompt-date", FROZEN]
    monkeypatch.setattr(sys, "argv", argv)
    assert m64_main(probe, adapter, entry_parser().parse_args(argv[1:]), template) == 0
    (row,) = [json.loads(line) for line in out.read_text().splitlines()]
    dog = row["shell_watchdog"]
    # the background `sleep 311` and the fake client's own idle `sleep 5` both started inside the reported window
    assert dog["limit_s"] == 1.0 and dog["kills"] and all(k["actions"][0] == "SIGTERM" for k in dog["kills"])
    assert "exec_timeout" in row["nonconv_flags"] and row["nonconv_kind"] == "exec_timeout" and row["converged"] is False
    import subprocess

    def survivors():
        ps = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True).stdout
        return [ln for ln in ps.splitlines() if len(ln.split(None, 2)) == 3 and ln.split(None, 2)[2].startswith("sleep 311")]

    end = _time.time() + 5
    while survivors() and _time.time() < end:
        _time.sleep(0.1)
    assert survivors() == []                                          # nothing survives the item


def test_m64_evidence_lives_under_transcripts_oc_and_tg1_keeps_its_root(probe, tmp_path):
    assert ao.OpencodeArm(probe, mode="m64").evidence_root(tmp_path) == tmp_path / "transcripts/oc"
    assert ao.OpencodeArm(probe, mode="tg1").evidence_root(tmp_path) == tmp_path / "opencode_transcripts"
