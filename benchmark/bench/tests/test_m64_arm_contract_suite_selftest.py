"""M64 step 4a: the contract-test harness validated against known positives and known defects (AGENTS.md: validate
instruments). A conforming in-memory arm passes every check; each defective variant makes exactly the check that
should catch it fail, so a green suite on a real arm means something."""
from __future__ import annotations

import pytest

from bench import arm_adapter as aa
from bench.tests import arm_contract_suite as cs
from bench.tests.arm_fakes import MinimalAdapter

SAMPLING = dict(temperature=0.6, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=0.0, enable_thinking=True,
                thinking_budget=81920, seed=1234, max_tokens=102400)
TOOLS = ["edit", "read", "shell", "write", "webfetch"]
USAGE = dict(prompt_tokens=100, completion_tokens=10)


class FakeArm(MinimalAdapter):
    native_client_cuts = ("client_inactivity",)
    removed_tools = ("subagent", "execute", "question", "websearch")
    cancel_kills = False

    def cancel(self, guard, wait, **kw):
        if self.cancel_kills:
            guard.kill_role("client")
        return super().cancel(guard, wait, **kw)


def request(n, body_over=None, tools=TOOLS, roles=("system", "user", "assistant", "tool")):
    body = dict(SAMPLING, model="m", stream=True,
                messages=[{"role": r, "content": "x"} for r in roles], tools=[{"type": "function", "function": {"name": t}}
                                                                               for t in tools])
    body.update(body_over or {})
    return cs.WireRequest(path="/v1/chat/completions", headers={}, body=body)


class FakeHarness(cs.ArmHarness):
    """A conforming arm, with one defect switchable by name."""
    expected = cs.ExpectedWire(sampling=SAMPLING, roles={"system", "user", "assistant", "tool"},
                               required_tools={"shell", "write"})
    reduced_window = 4096

    def __init__(self, defect=None):
        self.defect = defect
        self.adapter = FakeArm()
        if defect == "cancel_kills":
            self.adapter.cancel_kills = True

    def _events(self, n, compaction=0):
        ev = []
        for i in range(1, n + 1):
            ev += [aa.NormalizedEvent.request_start(i),
                   aa.NormalizedEvent.tool(i, "write", {"path": "a"}, "completed", start=1.0, end=2.0),
                   aa.NormalizedEvent.request_finish(i, aa.Usage(100, 0, 0, 10, 0))]
        for c in range(compaction):
            ev.append(aa.NormalizedEvent.compaction(n, dict(reason="auto", usage=aa.Usage(100, 0, 0, 7, 0).as_dict())))
        if self.defect != "no_terminal":
            ev.append(aa.NormalizedEvent.terminal("stop"))
        return ev

    def run(self, script, *, window=None, gate_overrides=None, inject=None):
        d = self.defect
        if script.get(1) == "http500":
            n = 2 if d == "retry" else 1
            row = {"id": "x"} if d == "scored_500" else None
            return cs.ArmRun(requests=[request(i) for i in range(n)], abort=None if row else RuntimeError("500"), row=row)
        reqs = [request(1), request(2)]
        if d == "wrong_seed":
            reqs[1] = request(2, dict(seed=1))
        elif d == "extra_tool":
            reqs = [request(i, tools=TOOLS + ["subagent"]) for i in (1, 2)]
        elif d == "tools_change":
            reqs[1] = request(2, tools=TOOLS[:-1] + ["shell2"])
        elif d == "developer_role":
            reqs[1] = request(2, roles=("developer", "user"))
        if script.get("compaction") or window:
            comp_wire = [dict(input=100, cache_read=0, cache_write=0, output=7, reasoning=0)]
            if d == "compaction_uncounted":
                rec = aa.Reconciliation(outcome=None)
            elif d == "compaction_tokens_wrong":
                rec = aa.Reconciliation(outcome=None, compaction=[dict(reason="auto", usage=aa.Usage(1, 0, 0, 1, 0).as_dict())])
            else:
                rec = aa.Reconciliation(outcome=None, compaction=[dict(reason="auto", usage=comp_wire[0])])
            ev = self._events(2, compaction=0 if d == "no_compaction_event" else 1)
            return cs.ArmRun(requests=reqs, events=ev, reconciliation=rec, wire_compaction_usage=comp_wire,
                             wire_usage=[USAGE, USAGE])
        gate = {}
        if inject == "stall" and d != "stall_unseen":
            gate = {"stop_reason": "stalled"}
        if inject == "loop" and d != "loop_unseen":
            gate = {"stop_reason": "looping"}
        if gate_overrides and d != "hard_unseen":
            gate = {"stop_reason": "hard_ceiling"}
        windows = [] if d == "window_missing" else [(1.0, 2.0, "write"), (1.0, 2.0, "write")]
        return cs.ArmRun(requests=reqs, events=self._events(2), reconciliation=aa.Reconciliation(outcome=None),
                         wire_usage=[USAGE, USAGE], gate=gate, tool_windows=windows)

    def compaction_script(self):
        return {"compaction": True}

    def shape(self, name):
        d = self.defect
        if name == "stop" or name == "length":
            return cs.ArmRun(requests=[], reconciliation=aa.Reconciliation(outcome=None))
        if name == "cancel":
            return cs.ArmRun(requests=[], reconciliation=aa.Reconciliation(outcome="runner_cancel"))
        if name == "error":
            return cs.ArmRun(requests=[], abort=RuntimeError("unclassified"))
        if name.startswith("client_cut:"):
            cut = name.split(":", 1)[1]
            if d == "cut_rejected":
                return cs.ArmRun(requests=[], abort=RuntimeError("cut"))
            return cs.ArmRun(requests=[], reconciliation=aa.Reconciliation(outcome=cut))
        if d == "accepts_mystery":
            return cs.ArmRun(requests=[], reconciliation=aa.Reconciliation(outcome=None))
        return cs.ArmRun(requests=[], abort=RuntimeError("unregistered shape"))


@pytest.fixture
def conforming():
    return FakeHarness()


CHECKS = {
    "wrong_seed": cs.check_wire_controls,
    "tools_change": cs.check_wire_controls,
    "developer_role": cs.check_wire_controls,
    "extra_tool": cs.check_removed_tools_absent,
    "retry": cs.check_retries_off,
    "scored_500": cs.check_retries_off,
    "compaction_uncounted": cs.check_compaction,
    "compaction_tokens_wrong": cs.check_compaction,
    "no_compaction_event": cs.check_compaction,
    "accepts_mystery": cs.check_terminal_shapes,
    "cut_rejected": cs.check_terminal_shapes,
    "no_terminal": cs.check_event_normalization,
    "window_missing": cs.check_tool_windows,
    "stall_unseen": cs.check_gate_positives,
    "loop_unseen": cs.check_gate_positives,
    "hard_unseen": cs.check_gate_positives,
    "cancel_kills": cs.check_cancel_sigterm_first,
}


@pytest.mark.parametrize("name", sorted({c.__name__ for c in CHECKS.values()}))
def test_a_conforming_arm_passes_every_check(conforming, name):
    check = getattr(cs, name)
    check(conforming)


@pytest.mark.parametrize("defect,check", sorted(CHECKS.items()))
def test_each_defect_turns_its_check_red(defect, check):
    with pytest.raises(AssertionError):
        check(FakeHarness(defect))


def test_the_other_checks_do_not_fire_on_an_unrelated_defect():
    """A defect is caught by its own check, not by every check (a check that always fails proves nothing)."""
    cs.check_retries_off(FakeHarness("wrong_seed"))
    cs.check_compaction(FakeHarness("retry"))
    cs.check_terminal_shapes(FakeHarness("extra_tool"))


def test_timeout_check_demands_the_native_cut_for_an_unconfigurable_client():
    h = FakeHarness()
    cs.check_accelerated_timeout(h)                      # unconfigurable + a registered cut: fine
    h.adapter.__class__ = type("NoCut", (FakeArm,), {"native_client_cuts": ()})
    with pytest.raises(AssertionError, match="native client cut"):
        cs.check_accelerated_timeout(h)
    h2 = FakeHarness()
    h2.timeout_configurable = True
    with pytest.raises(AssertionError, match="accelerated run"):
        cs.check_accelerated_timeout(h2)


def test_owed_checks_skip_with_their_reason_and_never_pass_silently():
    for check, text in ((cs.check_shared_search_tool, "owed"), (cs.check_infrastructure_failures, "owed"),
                        (cs.check_p201_rerun, "owed")):
        with pytest.raises(pytest.skip.Exception, match=text):
            check(FakeHarness())


def test_refusal_check_requires_the_arm_to_refuse_when_it_needs_the_service():
    h = FakeHarness()
    with pytest.raises(pytest.skip.Exception):           # does not need the service: skipped, not passed
        cs.check_refuses_without_search_service(h)
    h.search_required = True
    h.run_without_search_service = lambda: None
    with pytest.raises(AssertionError, match="REFUSE"):
        cs.check_refuses_without_search_service(h)
    h.run_without_search_service = lambda: aa.ArmRefused("x")
    cs.check_refuses_without_search_service(h)


def test_the_watchdog_positives_run_on_real_processes():
    cs.check_watchdog_positives()


def test_identity_check_requires_the_runtime_arm_field():
    h = FakeHarness()
    cs.check_identity_fields(h)
    h.adapter.manifest_fields = lambda: {}
    with pytest.raises(AssertionError, match="runtime.arm"):
        cs.check_identity_fields(h)
