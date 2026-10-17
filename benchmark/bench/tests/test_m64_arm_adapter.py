"""M64 step 4a: the ArmAdapter contract as code (spec 5): events, identities, epoch, registry (no client needed)."""
from __future__ import annotations

import hashlib
import json

import pytest

from bench import arm_adapter as aa
from bench.tests.arm_fakes import MinimalAdapter as _Minimal


# ---------------------------------------------------------------- arm ids and registry
def test_arm_ids_are_the_three_scaffolds_of_the_spec():
    assert aa.ARM_IDS == ("oc", "pi", "dsh")
    for arm in aa.ARM_IDS:
        assert aa.valid_arm_id(arm)
    for bad in ("", "OC", "opencode", "o c", "oc/pi", None, 3, "a" * 9):
        assert not aa.valid_arm_id(bad)


def test_the_abstract_members_are_the_spec_5_contract():
    required = {
        "snapshot", "build_env", "command", "preflight", "events", "transcript", "reconcile", "web_evidence",
        "manifest_fields",
    }                                                          # the spec 5 list (cancel is concrete, see below)
    assert required <= aa.ArmAdapter.__abstractmethods__
    assert "cancel" in dir(aa.ArmAdapter) and "cancel" not in aa.ArmAdapter.__abstractmethods__


def test_an_adapter_missing_a_member_cannot_be_instantiated():
    class Broken(_Minimal):
        reconcile = aa.ArmAdapter.reconcile        # re-abstracts reconcile
    with pytest.raises(TypeError, match="reconcile"):
        Broken()
    assert _Minimal().arm_id == "oc"


def test_the_base_class_cannot_be_instantiated():
    with pytest.raises(TypeError):
        aa.ArmAdapter()


def test_validate_adapter_checks_the_declared_class_attributes():
    ok = _Minimal()
    aa.validate_adapter(ok)

    def broken(**attrs):
        return type("B", (_Minimal,), attrs)()

    for attrs, why in [
        (dict(arm_id="zz9999999999"), "arm_id"),
        (dict(arm_id="OC"), "arm_id"),
        (dict(label=""), "label"),
        (dict(label="a b"), "label"),
        (dict(GENERATION_FIELDS=()), "GENERATION_FIELDS"),
        (dict(GENERATION_FIELDS=["a"]), "GENERATION_FIELDS"),
        (dict(GENERATION_FIELDS=("a", "a")), "GENERATION_FIELDS"),
        (dict(native_client_cuts=("nope",)), "native_client_cuts"),
        (dict(removed_tools=["subagent"]), "removed_tools"),
        (dict(removed_tools=("x", "x")), "removed_tools"),
        (dict(tool=""), "tool"),
    ]:
        with pytest.raises(aa.ArmContractError, match=why):
            aa.validate_adapter(broken(**attrs))


# ---------------------------------------------------------------- normalized events
def test_usage_validates_like_the_gate():
    u = aa.Usage(input=10, cache_read=2, cache_write=1, output=5, reasoning=3)
    assert u.as_dict() == dict(input=10, cache_read=2, cache_write=1, output=5, reasoning=3)
    assert u.completion_tokens == 8 and u.prompt_tokens == 13       # output + reasoning ; input + cache read/write
    for bad in (-1, True, 1.5, "3", None):
        with pytest.raises(aa.ArmContractError, match="usage"):
            aa.Usage(input=bad, cache_read=0, cache_write=0, output=0, reasoning=0)


def test_events_are_typed_and_validated():
    u = aa.Usage(1, 0, 0, 2, 0)
    e = aa.NormalizedEvent.request_finish(1, u)
    assert e.kind == "request_finish" and e.request_seq == 1 and e.usage == u
    aa.NormalizedEvent.request_start(1)
    aa.NormalizedEvent.tool(1, "shell", {"command": "ls"}, "completed", start=1.0, end=2.0)
    aa.NormalizedEvent.compaction(2, {"reason": "auto", "usage": u.as_dict()})
    aa.NormalizedEvent.error({"type": "x"})
    aa.NormalizedEvent.terminal("stop")
    with pytest.raises(aa.ArmContractError, match="kind"):
        aa.NormalizedEvent(kind="bogus")
    with pytest.raises(aa.ArmContractError, match="request_seq"):
        aa.NormalizedEvent.request_finish(0, u)
    with pytest.raises(aa.ArmContractError, match="terminal"):
        aa.NormalizedEvent.terminal("exploded")
    with pytest.raises(aa.ArmContractError, match="status"):
        aa.NormalizedEvent.tool(1, "shell", {}, "weird", start=1.0, end=2.0)
    with pytest.raises(aa.ArmContractError, match="end"):
        aa.NormalizedEvent.tool(1, "shell", {}, "completed", start=2.0, end=1.0)
    assert aa.TERMINAL_SHAPES == ("stop", "length", "error", "cancel", "client_cut")


def test_the_event_kinds_are_the_spec_list():
    assert aa.EVENT_KINDS == ("request_start", "request_finish", "tool", "compaction", "error", "terminal")


# ---------------------------------------------------------------- reconcile results
def test_reconciliation_accounts_compaction_tokens_separately():
    c1 = dict(reason="auto", usage=aa.Usage(100, 0, 0, 10, 0).as_dict())
    c2 = dict(reason="auto", usage=aa.Usage(50, 0, 0, 5, 1).as_dict())
    r = aa.Reconciliation(outcome=None, compaction=[c1, c2])
    assert r.compaction_count == 2
    assert r.compaction_completion_tokens == 16
    assert aa.Reconciliation(outcome="client_inactivity").compaction_count == 0
    with pytest.raises(aa.ArmContractError, match="compaction"):
        aa.Reconciliation(outcome=None, compaction=[dict(reason="auto")])


# ---------------------------------------------------------------- identities and the epoch
def test_epoch_id_follows_the_spec_recipe():
    snaps = [aa.Snapshot("pi", {"v": "1.3.0"}, True), aa.Snapshot("opencode", {"v": "2.0.20"}, True)]
    shas = {s.tool: s.sha256 for s in snaps}
    want = hashlib.sha256(json.dumps(
        {"schema_version": 1, "tools": [{"tool": "opencode", "snapshot_sha": shas["opencode"]},
                                        {"tool": "pi", "snapshot_sha": shas["pi"]}]},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert aa.epoch_id(snaps) == want == aa.epoch_id(list(reversed(snaps)))


def test_epoch_id_changes_with_any_snapshot_and_refuses_duplicates():
    a, b = aa.Snapshot("opencode", {"v": "1"}, True), aa.Snapshot("pi", {"v": "1"}, True)
    base = aa.epoch_id([a, b])
    assert aa.epoch_id([aa.Snapshot("opencode", {"v": "2"}, True), b]) != base
    assert aa.epoch_id([a]) != base
    with pytest.raises(aa.ArmContractError, match="duplicate"):
        aa.epoch_id([a, a])
    with pytest.raises(aa.ArmContractError, match="no snapshots"):
        aa.epoch_id([])


def test_snapshot_sha_is_canonical_and_completeness_is_part_of_it():
    s1 = aa.Snapshot("opencode", {"b": 1, "a": 2}, True)
    s2 = aa.Snapshot("opencode", {"a": 2, "b": 1}, True)
    assert s1.sha256 == s2.sha256
    assert aa.Snapshot("opencode", {"a": 2, "b": 1}, False).sha256 != s1.sha256
    assert aa.Snapshot("opencode", {"a": 2, "b": 1}, False, missing=("tool_schemas",)).complete is False
    with pytest.raises(aa.ArmContractError, match="missing"):
        aa.Snapshot("opencode", {}, True, missing=("x",))


def test_arm_generation_sha_covers_every_field_and_the_arm():
    fields = dict(probe_code_sha256="a" * 64, scaffold_policy_sha256="b" * 64)
    base = aa.arm_generation_sha256("oc", fields, ("probe_code_sha256", "scaffold_policy_sha256"))
    assert base == aa.arm_generation_sha256("oc", dict(reversed(list(fields.items()))),
                                            ("probe_code_sha256", "scaffold_policy_sha256"))
    assert aa.arm_generation_sha256("pi", fields, ("probe_code_sha256", "scaffold_policy_sha256")) != base
    assert aa.arm_generation_sha256("oc", {**fields, "probe_code_sha256": "c" * 64},
                                    ("probe_code_sha256", "scaffold_policy_sha256")) != base
    with pytest.raises(ValueError, match="scaffold_policy_sha256"):
        aa.arm_generation_sha256("oc", {"probe_code_sha256": "a" * 64}, ("probe_code_sha256", "scaffold_policy_sha256"))
    # a present None is a value (an absent overlay), an absent key is not
    assert aa.arm_generation_sha256("oc", {**fields, "x": None}, ("probe_code_sha256", "x")) != base


# ---------------------------------------------------------------- registry
def test_registry_refuses_unknown_and_duplicate_arms_and_never_instantiates_unregistered():
    reg = aa.ArmRegistry()
    with pytest.raises(aa.ArmRefused, match="not registered"):
        reg.get("oc")
    reg.register(_Minimal)
    assert isinstance(reg.get("oc"), _Minimal)
    with pytest.raises(aa.ArmContractError, match="already registered"):
        reg.register(_Minimal)
    with pytest.raises(aa.ArmRefused, match="unknown arm"):
        reg.get("zz")
    assert reg.registered() == ("oc",)


def test_registry_refuses_an_adapter_that_fails_validation():
    class Bad(_Minimal):
        label = ""
    with pytest.raises(aa.ArmContractError, match="label"):
        aa.ArmRegistry().register(Bad)


# ---------------------------------------------------------------- the shared search service interface (D2, later step)
def test_search_service_interface_is_stubbed_and_refuses():
    svc = aa.UnavailableSearchService()
    assert svc.available is False
    with pytest.raises(aa.ArmRefused, match="shared search service"):
        svc.require()
    with pytest.raises(aa.ArmRefused, match="shared search service"):
        svc.mcp_entry("opencode")
