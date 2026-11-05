"""`p475_kv prepare` (idempotent, refuses a dirty or diverged arm) and `preflight --arm` (qualify `--kv-arm`, PASS rule, retry cap: R15)."""
import pytest

from . import helpers as H
from .fakes import ARMS, FakeOps, PICK

MUTATING = {"commit", "checkout", "reset", "add", "submodule", "update-ref", "rebase", "merge", "clean", "stash", "switch",
            "apply", "cherry-pick", "restore", "rm", "mv", "tag"}


def mutating(calls):
    out = []
    for wt, args in calls:
        if args and (args[0] in MUTATING or args[:2] == ("worktree", "add") or args[:2] == ("worktree", "remove")
                     or (args[0] == "branch" and not any(a in ("--list", "-l", "--show-current", "--contains", "-a", "-r") for a in args))):
            out.append((wt, args))
    return out


@pytest.fixture
def w(tmp_path, monkeypatch):
    return H.world(tmp_path, monkeypatch)


# ------------------------------------------------------------------------------------------- prepare
def test_prepare_verifies_consistent_arm_worktrees(w):
    # class: exercises new behaviour
    assert H.prepare(w) == []


def test_prepare_is_idempotent_and_the_second_run_changes_nothing(w):
    # class: exercises new behaviour
    ops = FakeOps(w)
    assert H.prepare(w, ops) == []
    w.git_calls.clear()
    assert H.prepare(w, ops) == []
    assert mutating(w.git_calls) == []


@pytest.mark.parametrize("arm", ["N16", "TQ4", "TQ4-OFF"])
def test_prepare_refuses_a_dirty_arm(w, arm):
    # class: exercises new behaviour
    w.arm_clean[arm] = False
    assert H.prepare(w)


@pytest.mark.parametrize("what", ["head", "parent"])
def test_prepare_refuses_a_diverged_arm(w, what):
    # class: exercises new behaviour
    if what == "head":
        w.arm_head["AF4"] = "e" * 40
    else:
        w.arm_parent["AF4"] = "f" * 40
    assert H.prepare(w)


def test_prepare_never_repairs_a_dirty_arm(w):
    # class: exercises new behaviour (refuse, do not reset / clean)
    w.arm_clean["AF8"] = False
    H.prepare(w)
    assert mutating(w.git_calls) == []


def test_prepare_refuses_an_arm_commit_that_is_not_its_arm(w):
    # class: exercises new behaviour (R1 at prepare: a quantized arm's registry committed on the N16 branch)
    w.arm_registry_override["N16"] = w.arm_registry("TQ4")
    assert H.prepare(w)


# ------------------------------------------------------------------------------------------- preflight
def test_preflight_runs_the_forks_qualify_with_kv_arm_for_the_pick(w):
    # class: exercises new behaviour
    assert H.preflight_ok(w, "AF8")
    (call,) = w.run_calls
    a = call.argv
    assert a[0] == str(w.wt("AF8") / ".venv/bin/python")
    assert any(t.endswith("p369_phase2/qualify.py") for t in a)
    assert "--kv-arm" in a
    assert a[a.index("--predictor") + 1] == "off"
    assert a[a.index("--entry") + 1] == PICK
    assert a[a.index("--stack-root") + 1] == str(w.wt("AF8"))
    assert a[a.index("--fork-root") + 1] == str(w.wt("AF8") / "src" / "mlx-vlm")


@pytest.mark.parametrize("arm", ARMS)
def test_preflight_uses_predictor_off_even_for_on_arms(w, arm):
    # class: exercises new behaviour (the engagement check is the kv manifest, taken predictor-off)
    assert H.preflight_ok(w, arm)
    a = w.run_calls[-1].argv
    assert a[a.index("--predictor") + 1] == "off"
    assert a[a.index("--stack-root") + 1] == str(w.wt(arm))


def test_a_pass_writes_the_record_under_the_workdir(w):
    # class: exercises new behaviour
    assert H.preflight_ok(w, "TQ8")
    recs = list((w.wd / "p475" / "preflight").glob("*.json"))
    assert len(recs) == 1 and "tq8" in recs[0].name.lower()
    assert PICK in recs[0].read_text()


def test_a_first_time_pass_runs_qualify_once(w):
    # class: exercises new behaviour
    H.preflight(w, "AF4")
    assert len(w.run_calls) == 1


@pytest.mark.parametrize("mode", ["refuse", "wrong_entry", "no_report"])
def test_a_report_that_is_not_completed_for_the_pick_does_not_pass(w, mode):
    # class: exercises new behaviour (PASS needs status COMPLETED and kv_arm.entry == the pick)
    w.preflight_plan["AF8"] = [mode] * 5
    assert not H.preflight_ok(w, "AF8")


def test_a_refusal_is_retried_twice_by_default_so_three_attempts(w):
    # class: exercises new behaviour (R15: "retried at most --max-preflight (default 2) times" = 1 + 2 attempts)
    w.preflight_plan["AF8"] = ["refuse"] * 9
    rec = H.preflight(w, "AF8")
    assert rec["status"] == "REFUSED"
    assert w.preflight_calls["AF8"] == 3


def test_a_retry_that_passes_is_a_pass(w):
    # class: exercises new behaviour
    w.preflight_plan["AF8"] = ["refuse", "pass"]
    assert H.preflight_ok(w, "AF8")
    assert w.preflight_calls["AF8"] == 2


@pytest.mark.parametrize("cap,plan,ok,calls", [(0, ["refuse", "pass"], False, 1), (1, ["refuse", "pass"], True, 2),
                                               (1, ["refuse", "refuse", "pass"], False, 2), (2, ["refuse", "refuse", "pass"], True, 3),
                                               (3, ["refuse"] * 9, False, 4)])
def test_the_retry_cap_is_the_option(w, cap, plan, ok, calls):
    # class: exercises new behaviour (R15: boundaries of --max-preflight N = up to 1 + N attempts)
    w.preflight_plan["AF8"] = plan
    assert H.preflight_ok(w, "AF8", max_retries=cap) is ok
    assert w.preflight_calls["AF8"] == calls

