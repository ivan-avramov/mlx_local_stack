"""`bench.p426_panel.a7_select`: the A7 packet set from a B8 record (contract "Packet set"; hermetic A7 world).

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.

Hermetic world (see s3world.py): s1 selected 6 / identical 1 / one-arm-pass 2 (`python/delta` OFF only, `go/theta` ON only) /
neither-pass 1 / rejected key 1 (`go/psi`, moved to `keys_rejected` in the B8 record); s2 selected 8 / identical 2 / one-arm-pass 1 /
neither-pass 1 / rejected 0. Reading tested for `excluded`: `excluded[<session>][<kind>]`, a count (`int`) or a collection of ids
(the kind `one-arm-pass` is a collection of ids); the transposed layout `excluded[<kind>][<session>]` is accepted too.
"""
from __future__ import annotations

import json

import pytest

from bench.tests.p613s3 import s3world as S

SEL = {("s1", r) for r in S.S1_SEL} | {("s2", r) for r in S.S2_SEL}


def exc(excluded, session, kind):
    if session in excluded and isinstance(excluded[session], dict) and kind in excluded[session]:
        return excluded[session][kind]
    return excluded[kind][session]


def n_of(v):
    if isinstance(v, dict):
        return v["n"]
    return v if isinstance(v, int) and not isinstance(v, bool) else len(v)


def ids_of(v):
    if isinstance(v, dict):
        v = v["ids"]
    return {x[-1] if isinstance(x, (list, tuple)) else str(x).split(":")[-1].strip() for x in v}


def pairs(items):
    return {tuple(i) for i in items}


# class: new-behaviour (the packet set = B8-accepted keys, `passed is True` in both arms, `identical` false)
def test_select_items_are_the_both_pass_non_identical_keys(a7, panel):
    items, _ = a7.select(panel)
    assert pairs(items) == SEL
    assert len(items) == len(SEL) == 14


# class: invariant (A7 packets come from the two paired sessions only; the diagnostic pilot / reload pairs are never packets)
def test_select_never_takes_pilot_or_reload(a7, panel):
    items, _ = a7.select(panel)
    assert {tuple(i)[0] for i in items} == {"s1", "s2"}


# class: new-behaviour (exclusions counted per session and kind)
def test_select_excluded_counts_per_session(a7, panel):
    _, excluded = a7.select(panel)
    assert n_of(exc(excluded, "s1", "identical")) == 1 and n_of(exc(excluded, "s2", "identical")) == 2
    assert n_of(exc(excluded, "s1", "neither-pass")) == 1 and n_of(exc(excluded, "s2", "neither-pass")) == 1
    assert n_of(exc(excluded, "s1", "rejected key")) == 1 and n_of(exc(excluded, "s2", "rejected key")) == 0
    assert n_of(exc(excluded, "s1", "one-arm-pass")) == 2 and n_of(exc(excluded, "s2", "one-arm-pass")) == 1


# class: new-behaviour (one-arm-pass is listed with its ids)
def test_select_one_arm_pass_lists_ids(a7, panel):
    _, excluded = a7.select(panel)
    assert ids_of(exc(excluded, "s1", "one-arm-pass")) == {"python/delta", "go/theta"}
    assert ids_of(exc(excluded, "s2", "one-arm-pass")) == {"go/upsilon"}


# class: new-behaviour (a key B8 rejected is excluded as `rejected key` even when both rows pass)
def test_select_rejected_key_is_not_a_packet(a7, panel):
    items, excluded = a7.select(panel)
    assert ("s1", "go/psi") not in pairs(items)
    assert n_of(exc(excluded, "s1", "rejected key")) == 1


# class: invariant (the same inputs select the same set, twice)
def test_select_is_deterministic(a7, panel):
    assert a7.select(panel) == a7.select(panel)


def edit_rows(case, arm, session, fn):
    for f in sorted((case.attempt(arm, session) / session).glob("*.jsonl")):
        rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        for r in rows:
            fn(r)
        f.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))


# class: new-behaviour (the rows decide: an ON row that no longer passes moves the key to one-arm-pass)
def test_select_follows_the_rows(clone, panel):
    case = clone()
    edit_rows(case, "on", "s1", lambda r: r.update(passed=False) if r["id"] == "python/alpha" else None)
    case.reverify()                                       # R3: a changed row needs a fresh B8 (a stale one is refused)
    items, excluded = case.select(panel)
    assert pairs(items) == (SEL - {("s1", "python/alpha")}) | {("s1", "go/psi")}      # B8 no longer rejects go/psi
    assert "python/alpha" in ids_of(exc(excluded, "s1", "one-arm-pass"))


# class: new-behaviour (`passed is True`: a truthy non-bool never counts as a pass)
@pytest.mark.parametrize("value", [1, "True", "yes"])
def test_select_requires_boolean_true(clone, panel, value):
    case = clone()
    edit_rows(case, "off", "s1", lambda r: r.update(passed=value) if r["id"] == "python/beta" else None)
    case.reverify()
    items, _ = case.select(panel)
    assert ("s1", "python/beta") not in pairs(items)


# class: new-behaviour (the B8 record's `identical` flag drives the exclusion)
def test_select_uses_the_b8_identical_flag(clone, panel):
    case = clone()
    for pair in case.b8["axes"]["A7"]["pairs"]:
        for k in pair["keys"]:
            if k["key"] == ["s1", "python/alpha"]:
                k["identical"] = True
    items, excluded = case.select(panel)
    assert ("s1", "python/alpha") not in pairs(items)
    assert n_of(exc(excluded, "s1", "identical")) == 2


# class: invariant (a record without an A7 axis is not a B8 record: refusal, not an empty selection)
def test_select_refuses_a_record_without_a7(a7, panel):
    assert a7.select(panel)                                           # control
    S.refuses(panel.a7_select, a7.results_root, {"axes": {}})


# class: invariant (a B8 record that no longer matches the rows on disk is refused, never silently used)
def test_select_refuses_a_stale_b8(clone, panel):
    case = clone()
    assert case.select(panel)                                          # control
    edit_rows(case, "on", "s1", lambda r: r.update(passed=False) if r["id"] == "python/alpha" else None)
    S.refuses(case.select, panel)
