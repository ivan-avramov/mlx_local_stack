"""P426 B2 frozen tests, s3 core (spec §2 chain-core edits, §3 hooks, §5.1-5.3).

Classes: [FIX] reproduces a failure the spec fixes; [INV] preserves an invariant; [NEW] exercises new behaviour.
Module level only: a chain-level P426 leg needs a valid frozen record (§1 / §10.1) and the after-load receipt (§6.4), and the
spec names no seam a hermetic fake can satisfy (report, gap list); those tests are owed to a later delivery."""
from __future__ import annotations

import json

import pytest

from bench import chain_hooks as ch
from bench import run_config as rc
from bench.tests import b2_frozen_support as S


# ------------------------------------------------------------------------------------------------ the invalidate disposition
def invalidate(reason="a ready check failed"):
    return ch.Disposition("invalidate", reason=reason)


def test_new_invalidate_joins_every_disposition_vocabulary():
    assert "invalidate" in ch.KINDS and "invalidate" in ch.BEFORE_KINDS and "invalidate" in ch.AFTER_KINDS
    d = invalidate()
    assert d.kind == "invalidate" and d.reason == "a ready check failed" and d.stops_probe is True


def test_new_invalidate_round_trips_through_the_persisted_record():
    d = invalidate("done: reconciliation mismatch")
    assert ch.Disposition.from_dict(d.as_dict()) == d
    with pytest.raises(ValueError):
        ch.Disposition.from_dict({"kind": "invalidate"})             # a reason is required
    with pytest.raises(ValueError):
        ch.Disposition("invalidate", reason="x", cause="connection")  # it carries no cause


def test_new_both_hooks_may_return_invalidate():
    class H(ch.ChainHooks):
        def before_attempt(self, slot):
            return invalidate()

        def after_attempt(self, slot, done):
            return invalidate("done")
    assert H().run_before("s").kind == "invalidate" and H().run_after("s", {}).kind == "invalidate"


def test_inv_legacy_hooks_keep_their_signatures_and_dispositions():
    seen = []

    class Legacy(ch.ChainHooks):
        def before_attempt(self, slot):
            seen.append(("before", slot))
            return ch.Disposition.accept()

        def after_attempt(self, slot, done):
            seen.append(("after", slot, done))
            return ch.Disposition.rerun_same_slot("p201 cheat")
    assert Legacy().run_before("s1").kind == "accept"
    assert Legacy().run_after("s1", {"id": "python/a"}).kind == "rerun_same_slot"
    assert seen == [("before", "s1"), ("after", "s1", {"id": "python/a"})]
    assert ch.ChainHooks().run_before("s").kind == "accept" and ch.ChainHooks().run_after("s", {}).kind == "accept"


def test_inv_a_legacy_hook_infrastructure_error_is_still_a_pre_spawn_incident():
    class Health(ch.ChainHooks):
        def before_attempt(self, slot):
            raise ch.HookInfrastructureError("connection")
    assert Health().run_before("s") == ch.Disposition.pre_spawn_incident("connection")


# ------------------------------------------------------------------------------------------------ the transport policy
def test_new_p426_continue_is_a_third_transport_policy_and_the_others_stay(tmp_path):
    """§5.2: `p426_continue` is the policy of `tg1-p426`, the config `--p426` selects (taken from a real `--p426` parse, never
    built by hand); the legacy tg1 config keeps `abort_restart`."""
    assert set(rc.TRANSPORT_POLICIES) == {"abort_restart", "incident_retry", "p426_continue"}
    R = S.runner_module()
    legacy = R.tg1_config(R.parse_args(["chain", "s1", "--probe-code-sha", S.HEX9, "--models", S.MODEL]))
    p426 = R.tg1_config(R.parse_args([
        "chain", "s1", "--p426", "--models", S.MODEL, "--predictor", "off",
        "--out-root", str(tmp_path / "p426/wave2/tg1-p426-off-s1.a1"), "--probe-code-sha", S.HEX9, "--policy-sha", "c" * 64,
        "--frozen-prompt-date", S.EPOCH_DATE, "--campaign-core", "c" * 40, "--frozen-record", str(tmp_path / "amendment.json")]))
    assert (p426.config_id, p426.transport_policy) == ("tg1-p426", "p426_continue")
    assert legacy.transport_policy == "abort_restart" and p426.sha256() != legacy.sha256()


def test_new_invalidate_has_no_slot_disposition():
    """[d2] §2: like `pre_spawn_incident`, `invalidate` is handled by the chain before any `slot_disposition` call."""
    d = invalidate("done: reconciliation mismatch")                     # a legal disposition (built outside the raises)
    with pytest.raises(ValueError):
        ch.slot_disposition(d)
    with pytest.raises(ValueError):
        ch.slot_disposition(ch.Disposition.pre_spawn_incident("connection"))


# ------------------------------------------------------------------------------------------------ §16.1 slot file names
def test_new_slot_file_maps_a_slot_to_a_flat_file_name():
    from bench import chain_rows as cr
    slot = cr.slot_for(f"tg1-p426|oc|{S.MODEL}|s1|python", "python/beer-song")
    assert cr.slot_file(slot) == f"tg1-p426__oc__{S.MODEL}__s1__python__beer-song"
    assert cr.slot_file("a|b/c|d") == "a__b--c__d"


def test_new_slot_file_keeps_distinct_slots_distinct():
    from bench import chain_rows as cr
    base = f"tg1-p426|oc|{S.MODEL}|s1"
    names = {cr.slot_file(cr.slot_for(f"{base}|{lang}", f"{lang}/{item}")) for lang in ("python", "go")
             for item in ("beer-song", "book-store", "grep")}
    assert len(names) == 6 and not any("|" in n or "/" in n for n in names)
