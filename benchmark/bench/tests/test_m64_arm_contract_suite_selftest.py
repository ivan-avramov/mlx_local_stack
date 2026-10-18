"""M64 step 4a / P371 phase 4 (A13): the contract-test harness validated against known positives and known defects
(AGENTS.md: validate instruments), on REAL core runs.

Before phase 4 this selftest fed the checks hand-made summaries. Now every `ArmRun` a check sees is built from a real run
of the shared item core (`arm_runner.main`: gate, process guard, grader, reconciliation, row, manifest) with a real client
process (`tests/fake_contract_client.py`) talking HTTP to the scripted mock provider with wire capture. A conforming client
/ adapter passes every check; each injected defect is a switch of one such run (a client behaviour, an adapter switch, a
mock-provider script) and turns exactly the check that should catch it red. The same checks run against the real pinned
opencode 2.0.20 in `test_m64_arm_oc_contract.py`."""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from bench import arm_adapter as aa
from bench.tests import arm_contract_real as real
from bench.tests import arm_contract_suite as cs
from bench.tests.p371_world import world  # noqa: F401  (fixture)

CHECK_NAMES = sorted({spec[1] for spec in real.DEFECTS.values()})


@pytest.fixture
def conforming(world, monkeypatch):                                      # noqa: F811
    return real.FakeClientHarness(world, monkeypatch=monkeypatch)


def harness(world, monkeypatch, defect=None):                            # noqa: F811
    return real.FakeClientHarness(world, defect, monkeypatch=monkeypatch)


# ---------------------------------------------------------------- the runs are real
def test_the_arm_runs_the_checks_consume_come_from_real_core_runs_not_literals():
    """The harness module builds its run record in exactly one place, from a finished core run; this selftest builds none."""
    src = Path(real.__file__).read_text()
    assert len(re.findall(r"cs\.ArmRun\(", src)) == 1 and "arm_runner.main(" in src
    assert not re.search(r"\bArmRun\(", Path(__file__).read_text().split('"""', 2)[2])


def test_a_conforming_run_has_a_wire_capture_a_row_events_and_a_reconciliation(conforming):
    run = conforming.run(cs.DEFAULT_SCRIPT)
    assert run.abort is None and len(run.requests) == 2
    assert all(r.path.endswith("/chat/completions") and "Content-Type" in r.headers for r in run.requests)
    assert run.row["config_id"] == "contract-fake" and run.row["passed"] is True       # the core wrote it
    assert run.reconciliation is not None and [e.kind for e in run.events][-1] == "terminal"
    assert len(run.wire_usage) == 2 and run.tool_windows


def test_the_wire_the_client_sent_is_what_the_checks_read(conforming):
    run = conforming.run(cs.DEFAULT_SCRIPT)
    body = run.requests[0].body
    assert body["seed"] == conforming.expected.sampling["seed"] and body["thinking_budget"] == 81920
    assert {t["function"]["name"] for t in body["tools"]} == set(real.TOOLS)


# ---------------------------------------------------------------- known positives
@pytest.mark.parametrize("name", CHECK_NAMES)
def test_a_conforming_arm_passes_every_check(conforming, name):
    getattr(cs, name)(conforming)


def test_a_conforming_arm_passes_the_checks_without_a_defect_to_catch(conforming):
    cs.check_identity_fields(conforming)
    cs.check_accelerated_timeout(conforming)


# ---------------------------------------------------------------- known defects, each injected into a real run
@pytest.mark.parametrize("defect", sorted(real.DEFECTS))
def test_each_defect_turns_its_check_red(world, monkeypatch, defect):       # noqa: F811
    check = getattr(cs, real.DEFECTS[defect][1])
    with pytest.raises(AssertionError):
        check(harness(world, monkeypatch, defect))


def test_the_seventeen_pre_phase_4_defects_are_all_kept_and_the_new_ones_are_per_class_compaction_defects():
    assert len(real.LEGACY_DEFECTS) == 17 and set(real.LEGACY_DEFECTS) <= set(real.DEFECTS)
    assert {"compaction_wrong_seed", "compaction_wrong_budget", "compaction_no_tools",
            "compaction_bad_role"} == set(real.DEFECTS) - set(real.LEGACY_DEFECTS)


def test_a_compaction_request_with_a_wrong_seed_is_red_while_the_task_requests_stay_clean(world, monkeypatch):   # noqa: F811
    h = harness(world, monkeypatch, "compaction_wrong_seed")
    run = h.run(h.compaction_script(), window=h.reduced_window)
    assert run.abort is None
    summary = [r for r in run.requests if h.request_class(r) == "compaction"]
    task = [r for r in run.requests if h.request_class(r) == "task"]
    assert summary and all(r.body["seed"] == 1 for r in summary)
    assert all(r.body["seed"] == h.expected.sampling["seed"] for r in task)
    with pytest.raises(AssertionError, match=r"\(compaction\): seed=1"):
        cs.check_request_contract(h, run)
    cs.check_wire_controls(h)                                           # the plain task run of the same client is clean


def test_the_tools_rule_is_per_class_from_the_adapter(world, monkeypatch):    # noqa: F811
    """opencode's compaction class carries tools (P378); a client whose adapter says the class is tool-less is red when
    the summary request carries them, and one that must carry them is red when it does not."""
    h = harness(world, monkeypatch)
    run = h.run(h.compaction_script(), window=h.reduced_window)
    cs.check_request_contract(h, run)
    h.adapter.receipt_class_rules = dict(task="required", compaction="forbidden", auxiliary="forbidden")
    with pytest.raises(AssertionError, match=r"\(compaction\): a compaction request must carry no tools"):
        cs.check_request_contract(h, run)
    h2 = harness(world, monkeypatch, "compaction_no_tools")
    run2 = h2.run(h2.compaction_script(), window=h2.reduced_window)
    with pytest.raises(AssertionError, match=r"\(compaction\): missing tools"):
        cs.check_request_contract(h2, run2)


def test_the_other_checks_do_not_fire_on_an_unrelated_defect(world, monkeypatch):      # noqa: F811
    """A defect is caught by its own check, not by every check (a check that always fails proves nothing)."""
    cs.check_retries_off(harness(world, monkeypatch, "wrong_seed"))
    cs.check_compaction(harness(world, monkeypatch, "retry"))
    cs.check_terminal_shapes(harness(world, monkeypatch, "extra_tool"))
    cs.check_wire_controls(harness(world, monkeypatch, "compaction_wrong_seed"))


def test_the_real_cancel_run_records_what_the_client_process_saw(world, monkeypatch):       # noqa: F811
    run = harness(world, monkeypatch).cancel_run()
    assert run.client_signals == ["SIGTERM"] and run.row is None
    assert run.cancelled_item["termination"]["reason"] == "runner_cancel"
    killed = harness(world, monkeypatch, "cancel_kills").cancel_run()
    assert killed.client_signals == [] and killed.row is None       # SIGKILLed: it never saw SIGTERM


# ---------------------------------------------------------------- the rest of the instrument's own tests
def test_timeout_check_demands_the_native_cut_for_an_unconfigurable_client(conforming):
    h = conforming
    cs.check_accelerated_timeout(h)                      # unconfigurable + a registered cut: fine
    h.adapter.__class__ = type("NoCut", (type(h.adapter),), {"native_client_cuts": ()})
    with pytest.raises(AssertionError, match="native client cut"):
        cs.check_accelerated_timeout(h)
    h2 = real.FakeClientHarness.__new__(real.FakeClientHarness)
    h2.adapter, h2.timeout_configurable = real.ContractFakeArm(), True
    with pytest.raises(AssertionError, match="accelerated run"):
        cs.check_accelerated_timeout(h2)


def test_owed_checks_skip_with_their_reason_and_never_pass_silently(conforming):
    for check, text in ((cs.check_shared_search_tool, "owed"), (cs.check_infrastructure_failures, "owed"),
                        (cs.check_p201_rerun, "owed")):
        with pytest.raises(pytest.skip.Exception, match=text):
            check(conforming)


def test_refusal_check_requires_the_arm_to_refuse_when_it_needs_the_service(conforming):
    h = conforming
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


def test_identity_check_requires_the_runtime_arm_field(conforming):
    h = conforming
    cs.check_identity_fields(h)
    h.adapter.manifest_fields = lambda: {}
    with pytest.raises(AssertionError, match="runtime.arm"):
        cs.check_identity_fields(h)


def test_the_suite_class_runs_green_on_the_fake_client(world, monkeypatch):               # noqa: F811
    """Every spec 6 test method of `ArmContractSuite` passes (or skips with its owed / not-needed reason) on the real
    core runs of a conforming client."""
    suite = cs.ArmContractSuite()
    h = harness(world, monkeypatch)
    ran = []
    for name, method in inspect.getmembers(suite, inspect.ismethod):
        if not name.startswith("test_"):
            continue
        try:
            method(h)
        except pytest.skip.Exception as skip:
            assert "owed" in str(skip) or "does not need" in str(skip), (name, str(skip))
        ran.append(name)
    assert len(ran) == 16
