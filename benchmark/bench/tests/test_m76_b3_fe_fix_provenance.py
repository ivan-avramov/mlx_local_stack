"""Delivery 3: erratum-v1.2 item 5 — the B8 pair compares the complete normalized provenance (whitelist: KV / mode keys + arm commit).
Uses a REAL committed manifest (P426 S′ ON, math500 b1) as the base and perturbs it. Class (c); the first test is (b)."""
from __future__ import annotations

import copy
import json

import pytest

from bench import p426_verify as V
from bench.tests import test_m76_b3_fe_surface as G

MAN = G.REPO / "benchmark" / "results" / G.ENTRY / "math500.p426s2-on-b1.manifest.json"


@pytest.fixture(scope="module")
def base():
    return json.loads(MAN.read_text())


def problems(a, b):
    return V.kv_provenance_problems(a, b, "n16", "x")


# (b) a manifest against itself: no problem; the excluded volatile keys never matter
def test_identical_and_volatile_only_differences_pass(base):
    assert problems(base, copy.deepcopy(base)) == []
    other = copy.deepcopy(base)
    other["timestamp"] = "1999-01-01T00:00:00Z"
    other["router"] = {"pid": 1}
    other["router_exit"] = {"pid": 2}
    assert problems(base, other) == []


# (c) every top-level block other than the volatile ones is compared: a change in any of them rejects
def test_a_difference_in_any_recorded_block_rejects(base):
    keys = [k for k in base if k not in V.KV_PROVENANCE_EXCLUDED and isinstance(base[k], (dict, str, int, float, bool, list))]
    assert keys, "the real manifest has recorded blocks"
    checked = 0
    for k in keys:
        if k in ("kv", "git", "runtime", "fingerprint_version"):
            continue                              # these carry whitelisted leaves; covered separately
        other = copy.deepcopy(base)
        v = other[k]
        if isinstance(v, dict) and v:
            leaf = next(iter(v))
            other[k][leaf] = ["__changed__"]
        elif isinstance(v, bool):
            other[k] = not v
        elif isinstance(v, (int, float)):
            other[k] = v + 1
        elif isinstance(v, str):
            other[k] = v + "x"
        elif isinstance(v, list):
            other[k] = v + ["x"]
        else:
            continue
        assert problems(base, other), f"a difference in manifest[{k!r}] was accepted"
        checked += 1
    assert checked >= 3


# (c) the whitelist: the KV / mode keys and the arm commit may differ, nothing next to them
def test_the_whitelisted_kv_keys_and_the_arm_commit_may_differ(base):
    other = copy.deepcopy(base)
    other.setdefault("kv", {})["kv_bits"] = 4
    other["kv"]["tq4_attention"] = "m72_exact"
    other.setdefault("git", {})["stack_head"] = "f" * 40
    other.setdefault("runtime", {})["tq4_attention"] = "m72_exact"
    left = problems(base, other)
    assert all("kv_bits" not in p and "tq4_attention" not in p and "stack_head" not in p for p in left), left


@pytest.mark.parametrize("path,value", [
    (("runtime", "mtp_verify_scan"), "per_query"), (("runtime", "draft_kind"), "none"), (("runtime", "apc_enabled"), True),
    (("git", "mlx_vlm"), "0" * 40), (("sampling", "temperature"), 0.123), (("sampling", "thinking_budget"), 1),
    (("sampling_profile",), "other"), (("fingerprint_version",), 999)])
def test_a_difference_outside_the_whitelist_rejects(base, path, value):
    other = copy.deepcopy(base)
    node = other
    for p in path[:-1]:
        node = node.setdefault(p, {})
    if path[-1] not in node and path[0] not in base:
        pytest.skip(f"{'.'.join(path)} is not a recorded key of the real manifest")
    node[path[-1]] = value
    assert problems(base, other), path


# (c) a manifest without a fingerprint version is refused, never compared as equal
def test_a_manifest_without_a_fingerprint_version_is_refused(base):
    a = {k: v for k, v in base.items() if k != "fingerprint_version"}
    assert V.kv_provenance_problems(a, a, "n16", "x")


# (c) the manifest check also pins the thinking budget
def test_the_manifest_reasons_pin_the_thinking_budget(base):
    bad = copy.deepcopy(base)
    bad.setdefault("sampling", {})["thinking_budget"] = 1
    assert V._kv_manifest_reasons(base, bad, "n16", "x")
    assert V._kv_manifest_reasons(base, copy.deepcopy(base), "n16", "x") == []
