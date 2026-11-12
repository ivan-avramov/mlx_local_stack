"""M76 B1 (test-writer): the f45 mode proof on every leg (Interfaces "Mode proof" + Errata v1.1) and the draft-environment rules.

Source: the driver's manifest — `manifest["tq4_route_counts_at_creation"]` and `manifest["router_exit"]["tq4_route_counts_at_exit"]`
as `bench.provenance.tq4_route_counts` shapes them ({"mode", "route_counts", "source"}) — and the worker log's
`tq4_attention=<mode> self-test:` line (secondary). Errata v1.1: the table's rules apply to the EXIT snapshot's ABSOLUTE counters
(a fresh worker per leg; the creation snapshot is gathered after the ladder, so on a real leg it equals the exit one); the creation
block stays recorded and only its MODE is checked (null counters with the right mode are fine); both blocks are kept in the receipt /
dossier. A failure after load -> INVALID before the driver; after the driver -> INVALID.
The fake box makes creation == exit, so a delta reading (exit − creation) would refuse every healthy leg.
All tests are class (c) new behaviour unless marked (b).
"""
from __future__ import annotations

import json
import re

import pytest

from bench import p475_kv as K
from bench.tests.test_m76_b1_fe_support import (F45_MODE, MUST_GROW, MUST_STAY, find_dicts, good_exit, prepared_texts,  # noqa: F401
                                                route_block, selftest_line, world)

TQ4_ARMS = ("X", "V", "XO")
WRONG_MODE = {"X": "m72_v1", "V": "m72_exact", "XO": "m72_v1"}
DRAFT_NAMES = ("MLX_VLM_DRAFT_KIND", "MLX_VLM_DRAFT_MODEL")


def creation_block(man):
    return man["tq4_route_counts_at_creation"]


def exit_block(man):
    return man["router_exit"]["tq4_route_counts_at_exit"]


def edit(w, arm, fn):
    w.ops.manifest_edit[arm] = fn


def invalid_after_the_driver(w, arm, reason=None, block=1):
    """The leg ran its driver, was harvested as evidence, and is INVALID (with a reason matching `reason` when given)."""
    name, r = w.run_leg(arm, block)
    assert r["verdict"] == "INVALID", (arm, r["problems"], r["speed_problems"])
    assert len(w.ops.spawned) == 1 and r["_harvest"] == "harvested" and w.cfg.dossier(name).is_dir()
    if reason is not None:
        assert any(re.search(reason, p, re.I) for p in r["problems"]), r["problems"]
    return name, r


# ================================================================================================ the healthy legs
def test_an_n16_leg_has_mode_off_no_counters_and_no_self_test_line(world):
    """(b)/(c) N16: mode `off`, no counters, no self-test line: VALID; the worker log really has no self-test line."""
    w = world
    name, r = w.run_leg("N16")
    assert r["verdict"] == "VALID", r["problems"]
    assert "self-test" not in (w.wd / "worktrees" / "m76-f45-n16" / "logs" / "mlx_vlm.log").read_text()
    assert not find_dicts(r, ["p2s"])


def test_an_n16_manifest_with_an_explicit_off_block_is_valid(world):
    """(c) What provenance records for mode `off` — {"mode": "off", "route_counts": None, "source": …} — is no counter and no mismatch."""
    w = world

    def off_blocks(man):
        man["tq4_route_counts_at_creation"] = route_block("off", None)
        man["router_exit"]["tq4_route_counts_at_exit"] = route_block("off", None)
    edit(w, "N16", off_blocks)
    _, r = w.run_leg("N16")
    assert r["verdict"] == "VALID", r["problems"]


@pytest.mark.parametrize("arm", TQ4_ARMS)
@pytest.mark.parametrize("block", [1, 2])
def test_a_healthy_tq4_leg_is_valid_and_records_both_blocks_in_receipt_and_dossier(world, arm, block):
    """(c) Errata v1.1: each arm's counter rule holds on the exit snapshot's absolute counters (creation == exit in the fake, so
    exit − creation is 0 everywhere: a delta reading would refuse); the receipt and the dossier keep BOTH blocks — the exit
    counters (equal to the required values) and the creation block."""
    w = world
    name, r = w.run_leg(arm, block)
    assert r["verdict"] == "VALID", r["problems"]
    want = good_exit(arm, block)
    on_disk = json.loads(w.cfg.receipt_path(name).read_text())
    for doc in (r, on_disk, json.loads((w.results / name / "receipt.json").read_text())):
        hits = [d for d in find_dicts(doc, list(want)) if all(d[k] == v for k, v in want.items())]
        assert hits, f"no recorded counter block equal to {want}"
        blocks = [b for b in find_dicts(doc, ["mode", "route_counts"]) if b["mode"] == F45_MODE[arm]]
        assert len(blocks) >= 2, "the creation and the exit block are both recorded"


def test_the_two_blocks_of_one_arm_record_their_own_exit_counters(world):
    """(c) b1 and b2 legs of X: different exit counters recorded (the proof is per leg, not once per arm)."""
    w = world
    got = []
    for block in (1, 2):
        name, r = w.run_leg("X", block)
        assert r["verdict"] == "VALID", r["problems"]
        want = good_exit("X", block)
        assert [d for d in find_dicts(r, list(want)) if all(d[k] == v for k, v in want.items())]
        w.ops.t += 700
        got.append(want["d2_verify"])
    assert got == [900, 1800]


# ================================================================================================ counter rules (absolute, at exit)
@pytest.mark.parametrize("variant", ["zero", "negative"])
@pytest.mark.parametrize("arm, key", [(a, k) for a in TQ4_ARMS for k in MUST_GROW[a]])
def test_a_required_counter_that_is_not_above_zero_at_exit_is_invalid(world, arm, key, variant):
    """(c) X: p2s, d2_verify, native:prefill, native:verify > 0; V: p2s, mma, native:prefill, native:verify > 0; XO: p2s, d2,
    native:prefill, native:decode > 0 — at exit; a zero (or negative) counter is INVALID with the counter named."""
    w = world
    edit(w, arm, lambda man: exit_block(man)["route_counts"].__setitem__(key, 0 if variant == "zero" else -1))
    invalid_after_the_driver(w, arm, re.escape(key))


@pytest.mark.parametrize("arm, key", [(a, k) for a in TQ4_ARMS for k in MUST_STAY[a]])
def test_a_counter_that_must_be_zero_at_exit_but_is_not_is_invalid(world, arm, key):
    """(c) X: mma == 0; V: d2_verify == 0; XO: mma, d2_verify, native:verify == 0; every fallback:* == 0 — at exit."""
    w = world
    edit(w, arm, lambda man: exit_block(man)["route_counts"].__setitem__(key, 1))
    invalid_after_the_driver(w, arm, re.escape(key))


@pytest.mark.parametrize("arm", TQ4_ARMS)
def test_a_fallback_counter_above_zero_at_exit_is_invalid(world, arm):
    """(c) Any `fallback:*` key (also one this fake never lists) above zero at exit."""
    w = world
    edit(w, arm, lambda man: exit_block(man)["route_counts"].update({"fallback:oom": 3}))
    invalid_after_the_driver(w, arm, "fallback")


@pytest.mark.parametrize("arm", TQ4_ARMS)
def test_a_fallback_counter_at_zero_at_exit_is_fine(world, arm):
    """(c) Boundary: a `fallback:*` key present at exit with value 0 is no fallback."""
    w = world
    edit(w, arm, lambda man: exit_block(man)["route_counts"].update({"fallback:oom": 0}))
    _, r = w.run_leg(arm)
    assert r["verdict"] == "VALID", r["problems"]


@pytest.mark.parametrize("arm", TQ4_ARMS)
def test_a_nonzero_creation_snapshot_does_not_rescue_or_refuse_the_exit_rules(world, arm):
    """(c) Absolute reading: counters at creation are not subtracted — a creation block with every counter at 0 and a healthy exit
    is VALID, and a zero exit counter with a healthy creation block is INVALID."""
    w = world
    edit(w, arm, lambda man: creation_block(man).update(route_counts={k: 0 for k in creation_block(man)["route_counts"]}))
    _, r = w.run_leg(arm)
    assert r["verdict"] == "VALID", r["problems"]
    w.ops.t += 700
    key = MUST_GROW[arm][0]
    edit(w, arm, lambda man: exit_block(man)["route_counts"].__setitem__(key, 0))
    name, r2 = w.run_leg(arm, attempt=2)
    assert r2["verdict"] == "INVALID" and any(key in p for p in r2["problems"]), r2["problems"]


@pytest.mark.parametrize("arm, key", [(a, k) for a in TQ4_ARMS for k in MUST_GROW[a]])
def test_a_required_counter_absent_at_exit_is_invalid(world, arm, key):
    """(c) "Counters absent where required" -> INVALID with the reason."""
    w = world
    edit(w, arm, lambda man: exit_block(man)["route_counts"].pop(key))
    invalid_after_the_driver(w, arm, re.escape(key) + "|absent|missing|route")


# ================================================================================================ blocks absent / unusable
@pytest.mark.parametrize("arm", TQ4_ARMS)
def test_a_creation_block_with_null_counters_and_the_right_mode_is_valid(world, arm):
    """(c) Errata v1.1: the creation block is recorded and only its mode is checked — `route_counts: None` (source `unavailable: …`)
    with the arm's mode, next to a healthy exit block, is VALID."""
    w = world
    edit(w, arm, lambda man: man.__setitem__("tq4_route_counts_at_creation",
                                             {"mode": F45_MODE[arm], "route_counts": None, "source": "unavailable: ConnectionRefusedError"}))
    name, r = w.run_leg(arm)
    assert r["verdict"] == "VALID", r["problems"]
    assert find_dicts(r, ["mode", "route_counts"]), "the blocks stay recorded"


@pytest.mark.parametrize("arm", TQ4_ARMS)
@pytest.mark.parametrize("what", ["creation-absent", "exit-absent", "exit-null", "exit-null-both-blocks"])
def test_a_missing_or_unusable_route_counter_block_is_invalid(world, arm, what):
    """(c) No exit block (`router_exit` without `tq4_route_counts_at_exit`), an exit block whose counters could not be read
    (`route_counts: None`), or no creation block at all (its mode cannot be checked) -> INVALID."""
    w = world

    def damage(man):
        unavailable = {"mode": F45_MODE[arm], "route_counts": None, "source": "unavailable: ConnectionRefusedError"}
        if what == "creation-absent":
            del man["tq4_route_counts_at_creation"]
        elif what == "exit-absent":
            del man["router_exit"]["tq4_route_counts_at_exit"]
        else:
            man["router_exit"]["tq4_route_counts_at_exit"] = dict(unavailable)
            if what == "exit-null-both-blocks":
                man["tq4_route_counts_at_creation"] = dict(unavailable)
    edit(w, arm, damage)
    invalid_after_the_driver(w, arm, "route|counter|tq4|mode")


@pytest.mark.parametrize("arm", TQ4_ARMS)
def test_a_manifest_without_the_router_exit_block_is_invalid(world, arm):
    """(c) The exit snapshot rides `router_exit`: a manifest lacking it cannot prove the mode."""
    w = world
    edit(w, arm, lambda man: man.pop("router_exit"))
    invalid_after_the_driver(w, arm)


# ================================================================================================ mode mismatch
@pytest.mark.parametrize("where", ["creation", "exit"])
@pytest.mark.parametrize("arm", TQ4_ARMS)
def test_a_recorded_mode_other_than_the_arms_is_invalid(world, arm, where):
    """(c) X and XO: `m72_exact`; V: `m72_v1` — a snapshot recorded under another mode (counters otherwise healthy), at either block."""
    w = world

    def relabel(man):
        (creation_block(man) if where == "creation" else exit_block(man))["mode"] = WRONG_MODE[arm]
    edit(w, arm, relabel)
    invalid_after_the_driver(w, arm, "mode")


@pytest.mark.parametrize("where", ["creation", "exit"])
def test_an_n16_leg_whose_manifest_shows_a_tq4_mode_is_invalid(world, where):
    """(c) N16 must be mode `off`: a manifest carrying an engaged mode (counters or not) is a mismatch."""
    w = world

    def engaged(man):
        counts = {"p2s": 99, "native:prefill": 5}
        if where == "creation":
            man["tq4_route_counts_at_creation"] = route_block("m72_exact", dict(counts))
        else:
            man["router_exit"]["tq4_route_counts_at_exit"] = route_block("m72_exact", dict(counts))
    edit(w, "N16", engaged)
    invalid_after_the_driver(w, "N16", "mode|counter|off")


# ================================================================================================ the worker's self-test line (after load)
@pytest.mark.parametrize("arm", TQ4_ARMS)
def test_a_self_test_line_for_another_mode_aborts_before_the_driver(world, arm):
    """(c) R5-style: the worker's `tq4_attention=<mode> self-test:` line names a mode other than the arm's -> INVALID, the driver is
    never launched, the stack is torn down."""
    w = world
    w.ops.selftest[arm] = selftest_line(WRONG_MODE[arm])
    _, r = w.run_leg(arm)
    assert r["verdict"] == "INVALID" and any("mode" in p.lower() or "self-test" in p.lower() for p in r["problems"]), r["problems"]
    assert not w.ops.spawned and ("stop_stack",) in w.ops.calls and r["_harvest"] == "harvested"


def test_an_n16_worker_that_logs_a_self_test_line_is_invalid_before_the_driver(world):
    """(c) "N16: mode off, no counters, no self-test line": an engaged worker under the native arm."""
    w = world
    w.ops.selftest["N16"] = selftest_line("m72_exact")
    _, r = w.run_leg("N16")
    assert r["verdict"] == "INVALID" and not w.ops.spawned and ("stop_stack",) in w.ops.calls


def test_a_self_test_line_of_an_earlier_load_does_not_count(world):
    """(c) Interpretation (the spec says "worker log"): like the KV line, the self-test line is read from THIS load's log text only —
    an earlier load's `m72_v1` line in the same file does not fail an X leg whose own load logged `m72_exact`."""
    w = world
    log = w.wd / "worktrees" / "m76-f45-x" / "logs" / "mlx_vlm.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(selftest_line("m72_v1"))
    _, r = w.run_leg("X")
    assert r["verdict"] == "VALID", r["problems"]


# ================================================================================================ the draft environment (Errata v1.1)
@pytest.mark.parametrize("name", DRAFT_NAMES)
def test_an_xo_worker_carrying_a_draft_variable_is_invalid_before_the_driver_naming_it(world, name):
    """(c) Errata v1.1 (M77 change review): on the MTP-OFF arm the worker environment must not carry `MLX_VLM_DRAFT_KIND` or
    `MLX_VLM_DRAFT_MODEL` (an inherited value would load a drafter) -> INVALID after load, before the driver, the reason names the
    variable; the stack is torn down and the leg is harvested as evidence. (a) fails without the fix round."""
    w = world
    w.ops.worker_env[name] = "inherited"
    leg, r = w.run_leg("XO")
    assert r["verdict"] == "INVALID" and any(name in p for p in r["problems"]), r["problems"]
    assert not w.ops.spawned and ("stop_stack",) in w.ops.calls and r["_harvest"] == "harvested"
    assert "inherited" not in json.dumps(r["problems"]), "the reason names the variable, never its value"


def test_an_xo_worker_without_draft_variables_is_valid(world):
    """(b) The healthy XO leg (no draft variable in the worker environment) is VALID."""
    w = world
    _, r = w.run_leg("XO")
    assert r["verdict"] == "VALID", r["problems"]


@pytest.mark.parametrize("name", DRAFT_NAMES)
def test_the_draft_variable_rule_is_for_the_mtp_off_arm_only(world, name):
    """(c) "On an MTP-OFF arm (XO)": the MTP-ON arms are not refused for those variables."""
    w = world
    w.ops.worker_env[name] = "x"
    _, r = w.run_leg("X")
    assert r["verdict"] == "VALID", r["problems"]


@pytest.mark.parametrize("arm", ["N16", "X", "V", "XO"])
def test_the_f45_driver_environment_carries_no_draft_variable(world, arm):
    """(c) Errata v1.1: the router environment is stripped of both names on every f45 leg — what the driver inherits from the router
    handle (the fake's handle exports both) carries neither, nor the KV / TQ names. (a) fails without the fix round."""
    w = world
    _, r = w.run_leg(arm)
    assert r["verdict"] == "VALID", r["problems"]
    env = w.ops.spawned[0]["env"]
    assert not any(n in env for n in DRAFT_NAMES), sorted(n for n in DRAFT_NAMES if n in env)
    assert not K.kv_env_names(env)
    assert env["MLX_SERVE_CONFIG"] == str(w.cfg.registry(arm))


def test_a_u4_leg_keeps_its_driver_environment(tmp_path, monkeypatch):
    """(b) `--campaign u4` unchanged: the u4 driver environment is stripped of the KV / TQ names only; the draft variables the
    router handle exports are still inherited (today's behaviour)."""
    from bench.tests.test_p475_impl_support import FakeHandle, FakeOps, make_cfg
    monkeypatch.setattr(FakeHandle, "env_base", lambda self: {"PATH": "/usr/bin", "KV_BITS": "4", "MLX_VLM_DRAFT_KIND": "mtp",
                                                              "MLX_VLM_DRAFT_MODEL": "m"}, raising=True)
    ops, cfg = FakeOps(tmp_path), make_cfg(tmp_path)
    ops.add_all(cfg)
    r = K.run_leg(K.leg_name("TQ4", 1, 1), "TQ4", ops, cfg)
    assert r["verdict"] == "VALID", r["problems"]
    env = ops.spawned[0]["env"]
    assert "KV_BITS" not in env and env["MLX_VLM_DRAFT_KIND"] == "mtp" and env["MLX_VLM_DRAFT_MODEL"] == "m"


@pytest.mark.parametrize("campaign, stripped", [("f45", True), ("u4", False)])
def test_the_real_router_handle_strips_the_draft_variables_on_f45_only(tmp_path, monkeypatch, campaign, stripped):
    """(c)/(b) The router environment (RealOps' ChainOps subclass, never started here), also what the worktree `.env` would add: both
    draft names stripped on f45, kept on u4; KV / TQ names stripped on both. (RealOps takes the campaign as its third argument.)"""
    wd, repo = tmp_path / "wd", tmp_path / "repo"
    wt = wd / "worktrees" / "wt"
    wt.mkdir(parents=True)
    repo.mkdir()
    (wt / ".env").write_text("MLX_VLM_DRAFT_KIND=mtp\nHF_HOME=/hf\n")
    monkeypatch.setenv("MLX_VLM_DRAFT_MODEL", "caslca/some-drafter")
    monkeypatch.setenv("KV_BITS", "4")
    env = K.RealOps(wd, repo, campaign).stack(wt, wt / "main_models.yaml", "off").env_base()
    assert not K.kv_env_names(env)
    assert (not any(n in env for n in DRAFT_NAMES)) is stripped
    assert env.get("HF_HOME") == "/hf" and env["MLX_SERVE_CONFIG"] == str(wt / "main_models.yaml")


# ================================================================================================ the proof does not leak into u4
def test_a_u4_leg_still_needs_no_route_counters(tmp_path):
    """(b) `--campaign u4` legs carry no mode proof (no tq4_attention in the u4 entry): a u4 leg whose manifest holds no counters
    stays VALID."""
    from bench.tests.test_p475_impl_support import FakeOps, make_cfg
    ops, cfg = FakeOps(tmp_path), make_cfg(tmp_path)
    ops.add_all(cfg)
    r = K.run_leg(K.leg_name("TQ4", 1, 1), "TQ4", ops, cfg)
    assert r["verdict"] == "VALID", r["problems"]
