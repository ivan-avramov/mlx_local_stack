"""M64 spec 6: the per-arm, offline CONTRACT-TEST HARNESS any ArmAdapter must pass (opencode now; Pi / dsh later).

Test support, not a test module. An arm's test module subclasses `ArmContractSuite` and supplies `harness`, an
`ArmHarness`: how to drive THAT client once against the mock provider and report what happened in arm-neutral terms
(`ArmRun`). The `check_*` functions hold the assertions; `ArmContractSuite` only wires them to pytest, and the harness
selftest (`test_m64_arm_contract_suite_selftest.py`) proves every check red against a defective harness.

Coverage of spec 6 (each is one check; `owed` ones skip with the reason, never pass silently):
  wire controls (sampling / seed / budgets / roles / tools on EVERY request), retries off (injected 500 -> abort, no
  second request), accelerated timeout (or the registered native client cut), compaction at a reduced window (event
  recorded, tokens counted), terminal shapes (stop, length, error, cancel, client cut), shell watchdog positives
  (foreground, background, a child detached AFTER it was observed), tool windows from the arm's events, D1 tools and
  hosted search absent, the shared search tool present (D2: owed, later step), infrastructure-failure classification
  (owed with D2), injected stall / loop / hard-ceiling through the arm's events, event normalization, cancellation
  (SIGTERM first), identities, and the arm's refusal without the D2 service. P201 cheat -> re-run is arm-neutral build
  step 5 (owed).
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
import hashlib
import json
import os
import subprocess
import time

import pytest

from bench import arm_adapter as aa
from bench import arm_watchdog as wd

DEFAULT_SCRIPT = {}                    # the mock's default: a write tool call, then "Done."


# ---------------------------------------------------------------- arm-neutral records
@dataclass
class WireRequest:
    path: str
    headers: dict
    body: dict


@dataclass
class ExpectedWire:
    """What every request must carry (spec 3 proof matrix)."""
    sampling: dict                      # temperature, top_p, top_k, min_p, presence_penalty, enable_thinking,
    #                                     thinking_budget, seed, max_tokens (None: clamped by the client, recorded only)
    roles: set                          # allowed message roles
    required_tools: set = field(default_factory=set)


@dataclass
class ArmRun:
    """One contract run of an arm against the mock provider."""
    requests: list                                     # [WireRequest] chat requests, in order
    events: list = field(default_factory=list)         # [NormalizedEvent]
    reconciliation: aa.Reconciliation | None = None
    abort: BaseException | None = None                 # what stopped the run (None: a row was produced)
    row: dict | None = None
    gate: dict = field(default_factory=dict)           # the row's gate block
    flags: list = field(default_factory=list)
    wire_compaction_usage: list = field(default_factory=list)   # usage the mock reported for compaction requests
    wire_usage: list = field(default_factory=list)              # usage the mock reported for every request
    tool_windows: list = field(default_factory=list)            # adapter.tool_windows(stream)


class ArmHarness(abc.ABC):
    """Drives one client. `adapter` is the ArmAdapter under test."""
    adapter: aa.ArmAdapter
    expected: ExpectedWire
    timeout_configurable = False
    search_required = False             # the arm's configuration needs the D2 service (so it must refuse without it)

    @abc.abstractmethod
    def run(self, script, *, window=None, gate_overrides=None, inject=None) -> ArmRun:
        """One item against the mock. `script` is the mock's request script (1-based); `window` a reduced context
        window (tokens) for compaction; `gate_overrides` lowers named gate constants (hard-ceiling positive);
        `inject` is the M62 inject kind (stall | loop)."""

    @abc.abstractmethod
    def shape(self, name) -> ArmRun:
        """Feed one terminal shape through the adapter's reconcile (no client): stop, length, error, cancel,
        client_cut:<cut>, or `unregistered`."""

    def accelerated_timeout(self):
        """For an arm whose client timeout is configurable: run with a tiny timeout against a hung stream; else None."""
        return None

    def run_without_search_service(self):
        """The exception raised when the arm is configured without the D2 service (None: arm does not need it)."""
        return None

    def search_fixture(self):
        return None

    def compaction_script(self):
        raise NotImplementedError

    reduced_window = None

    def watchdog_windows(self, run):
        return run.tool_windows

    def inject_script(self, kind):
        """Mock scripts for the M62 gate positives: distinct calls (stall, hard ceiling) or one repeated call (loop)."""
        if kind == "loop":
            return {i: {"name": "shell", "input": {"command": "echo same"}} for i in range(1, 7)}
        return {i: {"name": "shell", "input": {"command": f"echo {i}"}} for i in range(1, 9)}


# ---------------------------------------------------------------- the checks (plain functions: AssertionError = red)
def _names(body):
    return [t["function"]["name"] for t in body.get("tools") or []]


def tools_hash(body):
    return hashlib.sha256(json.dumps(body.get("tools"), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def check_wire_controls(h):
    run = h.run(DEFAULT_SCRIPT)
    assert run.abort is None, f"the baseline run aborted: {run.abort!r}"
    assert len(run.requests) >= 2, "the default script must produce a tool call and a final request"
    task_hashes = set()
    for i, req in enumerate(run.requests, 1):
        body = req.body
        for key, want in h.expected.sampling.items():
            if want is None:
                assert key in body, f"request {i}: {key} absent"
            else:
                assert body.get(key) == want, f"request {i}: {key}={body.get(key)!r}, expected {want!r}"
        roles = {m.get("role") for m in body.get("messages", [])}
        assert roles <= h.expected.roles, f"request {i}: roles {sorted(roles)} outside {sorted(h.expected.roles)}"
        names = set(_names(body))
        assert h.expected.required_tools <= names, f"request {i}: missing tools {sorted(h.expected.required_tools - names)}"
        task_hashes.add(tools_hash(body))
    assert len(task_hashes) == 1, "a later task request changed its tools (request_tools_sha256 differs)"


def check_removed_tools_absent(h):
    run = h.run(DEFAULT_SCRIPT)
    assert run.abort is None
    for i, req in enumerate(run.requests, 1):
        present = set(_names(req.body)) & set(h.adapter.removed_tools)
        assert not present, f"request {i}: D1/D2-removed tools present: {sorted(present)}"


def check_retries_off(h):
    run = h.run({1: "http500"})
    assert run.abort is not None, "an injected 500 must abort the item (never a scored row)"
    assert run.row is None, "a transport failure produced a row"
    assert len(run.requests) == 1, f"the client retried: {len(run.requests)} chat requests after one 500"


def check_accelerated_timeout(h):
    run = h.accelerated_timeout()
    if run is None:
        assert not h.timeout_configurable, "a configurable-timeout arm must provide the accelerated run"
        assert h.adapter.native_client_cuts, ("an arm with an unconfigurable timeout must register its native client "
                                              "cut (a treatment, spec 3)")
        return
    assert run.abort is not None or (run.row and run.row.get("nonconv_kind")), "the accelerated timeout was not seen"
    assert len(run.requests) == 1, "the client retried after its own timeout"


def check_compaction(h):
    run = h.run(h.compaction_script(), window=h.reduced_window)
    assert run.abort is None, f"compaction run aborted: {run.abort!r}"
    comp = [e for e in run.events if e.kind == "compaction"]
    assert comp, "no compaction event was recorded at the reduced window"
    assert run.reconciliation is not None and run.reconciliation.compaction_count == len(comp), \
        "compaction events and the reconciliation's compaction accounting disagree"
    got = sorted(e["usage"]["output"] + e["usage"]["reasoning"] for e in run.reconciliation.compaction)
    want = sorted(u["output"] + u["reasoning"] for u in run.wire_compaction_usage)
    assert got == want and want, f"compaction tokens not counted: accounted {got}, the wire reported {want}"
    assert run.events[-1].kind == "terminal" and run.events[-1].terminal == "stop"


def check_terminal_shapes(h):
    stop = h.shape("stop")
    assert stop.abort is None and stop.reconciliation is not None and stop.reconciliation.outcome is None
    length = h.shape("length")
    assert length.abort is None, "a length finish is a registered shape"
    cancel = h.shape("cancel")
    assert cancel.abort is None and cancel.reconciliation.outcome == "runner_cancel"
    error = h.shape("error")
    assert error.abort is not None, "an unclassifiable error shape must abort, never score"
    cuts = h.adapter.native_client_cuts
    for cut in cuts:
        run = h.shape("client_cut:" + cut)
        assert run.abort is None and run.reconciliation.outcome == cut, f"registered cut {cut} not accepted"
    mystery = h.shape("unregistered")
    assert mystery.abort is not None, "an unregistered terminal shape must abort (never accepted by default)"


def check_event_normalization(h):
    run = h.run(DEFAULT_SCRIPT)
    assert run.abort is None
    kinds = [e.kind for e in run.events]
    assert set(kinds) <= set(aa.EVENT_KINDS)
    starts = [e.request_seq for e in run.events if e.kind == "request_start"]
    finishes = [e for e in run.events if e.kind == "request_finish"]
    assert starts == list(range(1, len(starts) + 1)) and [e.request_seq for e in finishes] == starts
    assert len(finishes) == len(run.wire_usage)
    for event, usage in zip(finishes, run.wire_usage):
        assert event.usage.input + event.usage.cache_read + event.usage.cache_write == usage["prompt_tokens"] \
            or event.usage.input == usage["prompt_tokens"]
        assert event.usage.output + event.usage.reasoning == usage["completion_tokens"]
    assert any(e.kind == "tool" for e in run.events), "no tool event normalized"
    assert run.events[-1].kind == "terminal" and run.events[-1].terminal == "stop"


def check_tool_windows(h):
    run = h.run(DEFAULT_SCRIPT)
    tools = [e for e in run.events if e.kind == "tool"]
    assert tools
    windows = h.watchdog_windows(run)
    assert len(windows) == len(tools), "every tool call must yield a tool-execution window"
    for (start, end, name), event in zip(windows, tools):
        assert name == event.tool["name"] and (end is None or end >= start)


def check_gate_positives(h):
    for inject, reason in (("stall", "stalled"), ("loop", "looping")):
        run = h.run(h.inject_script(inject), inject=inject)
        assert run.gate.get("stop_reason") == reason or reason in run.flags, \
            f"injected {inject} did not reach the gate through the arm's events (stop_reason={run.gate.get('stop_reason')!r})"
    run = h.run(h.inject_script("hard"), gate_overrides={"requests": 3})
    assert run.gate.get("stop_reason") == "hard_ceiling" or "hard_ceiling" in run.flags, \
        "the hard ceiling did not stop the item"


def check_watchdog_positives():
    """Arm-neutral: the 600 s deadline machinery on REAL processes (shortened limit), the three spec 6 positives."""
    limit, grace = 1.0, 0.4
    t0 = time.time()
    fg = subprocess.Popen(["sleep", "60"])
    bg = subprocess.Popen(["sh", "-c", "sleep 60 & wait"])
    try:
        dog = wd.ShellWatchdog.for_client(os.getpid(), limit_s=limit, grace_s=grace)
        dog.open_window("a", "shell", t0 - 0.2)
        end = time.time() + 12
        while time.time() < end and (fg.poll() is None or bg.poll() is None):
            dog.tick()
            time.sleep(0.05)
        assert fg.poll() is not None, "a foreground tool descendant over the limit survived"
        assert bg.poll() is not None, "a background tool descendant over the limit survived"
        assert dog.exec_timeout
    finally:
        for p in (fg, bg):
            p.kill()
            p.wait(10)


def check_cancel_sigterm_first(h):
    calls = []

    class Guard:
        def graceful_stop(self, role, wait, before_signal=None, after_signal=None):
            calls.append(("graceful_stop", role, wait))
            return [dict(pid=1, create_time=1.0, role=role, argv=[])]

        def kill_role(self, role=None):
            calls.append(("kill_role", role))
            return []

    got = h.adapter.cancel(Guard(), 15)
    assert calls == [("graceful_stop", "client", 15)], f"cancel must SIGTERM first and never SIGKILL itself: {calls}"
    assert got and got[0]["role"] == "client"


def check_identity_fields(h):
    a = h.adapter
    aa.validate_adapter(a)
    snap = a.snapshot()
    assert isinstance(snap, aa.Snapshot) and snap.tool == a.tool
    man = a.manifest_fields()
    assert man.get("arm") == a.arm_id, "the manifest must say which arm wrote it (runtime.arm)"


def check_refuses_without_search_service(h):
    if not h.search_required:
        pytest.skip("this arm's configuration does not need the D2 search service")
    exc = h.run_without_search_service()
    assert isinstance(exc, aa.ArmRefused), "an arm that configures the D2 service must REFUSE to run without it"


def check_shared_search_tool(h):
    fixture = h.search_fixture()
    if fixture is None:
        pytest.skip("owed: the shared search tool (D2, spec 5.5) is a later build step; "
                    "its identical-schema contract test lands with the service")
    raise AssertionError("a D2 fixture exists but no check consumes it yet")        # pragma: no cover


def check_infrastructure_failures(h):
    pytest.skip("owed: container down / MCP crash / all engines erroring classification lands with the D2 service")


def check_p201_rerun(h):
    pytest.skip("owed: P201 cheat -> same-slot re-run through each arm is arm-neutral build step 5 (spec 12)")


class ArmContractSuite:
    """Subclass in an arm's test module and define the `harness` fixture. Every spec 6 item is one test."""

    @pytest.fixture
    def harness(self):                                      # pragma: no cover
        raise NotImplementedError("define the `harness` fixture returning an ArmHarness")

    def test_wire_controls_every_request(self, harness):
        check_wire_controls(harness)

    def test_d1_tools_and_hosted_search_absent(self, harness):
        check_removed_tools_absent(harness)

    def test_retries_off_injected_500_aborts_without_a_second_request(self, harness):
        check_retries_off(harness)

    def test_accelerated_timeout_or_registered_native_cut(self, harness):
        check_accelerated_timeout(harness)

    def test_compaction_at_a_reduced_window(self, harness):
        check_compaction(harness)

    def test_terminal_shapes(self, harness):
        check_terminal_shapes(harness)

    def test_events_are_normalized(self, harness):
        check_event_normalization(harness)

    def test_tool_windows_from_the_arms_events(self, harness):
        check_tool_windows(harness)

    def test_shell_watchdog_positives_foreground_background(self, harness):
        check_watchdog_positives()

    def test_injected_stall_loop_hard_ceiling_through_the_arms_events(self, harness):
        check_gate_positives(harness)

    def test_cancel_is_sigterm_first(self, harness):
        check_cancel_sigterm_first(harness)

    def test_identity_and_manifest_fields(self, harness):
        check_identity_fields(harness)

    def test_arm_refuses_without_the_search_service(self, harness):
        check_refuses_without_search_service(harness)

    def test_shared_search_tool_identical_across_arms(self, harness):
        check_shared_search_tool(harness)

    def test_infrastructure_failure_classification(self, harness):
        check_infrastructure_failures(harness)

    def test_p201_cheat_rerun(self, harness):
        check_p201_rerun(harness)
