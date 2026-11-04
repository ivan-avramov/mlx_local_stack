"""The hermetic worlds are what the tests say they are (no code under test is used).

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.
"""
from __future__ import annotations

import json

from bench.tests.p613s4 import s4world as W


def parse(text):
    return [json.loads(l) for l in text.splitlines() if l.strip()]


# class: invariant (the expected-count tables the other tests rely on: 22 accepted keys; A has 4 generation, B none)
def test_expected_tables():
    a, b = W.counts_of(W.EXPECT_A), W.counts_of(W.EXPECT_B)
    assert a == {"s1": {"identical": 4, "environment": 3, "generation": 2, "cutoff": 1},
                 "s2": {"identical": 7, "environment": 2, "generation": 2, "cutoff": 1}}
    assert b == {"s1": {"identical": 6, "environment": 3, "generation": 0, "cutoff": 1},
                 "s2": {"identical": 9, "environment": 2, "generation": 0, "cutoff": 1}}


# class: invariant (world A: B8 accepts 10 + 12 keys, the rejected key go/psi is not among them; evidence commit has the events)
def test_world_a_is_accepted_and_has_events(world_a):
    a7 = world_a.b8["axes"]["A7"]
    keys = {(p["pair"], tuple(k["key"])[1]) for p in a7["pairs"] if p["role"] == "pair" for k in p["keys"]}
    assert ("s1", "go/psi") not in keys
    assert {(s, r) for (s, r) in W.EXPECT_A} == keys
    for (s, r) in W.EXPECT_A:
        for arm in ("off", "on"):
            data = W.S.git(world_a.repo, "show", f"{world_a.evidence_ref}:{W.events_rel(world_a, arm, s, r)}")
            assert data.count("\n") >= 3


# class: invariant (the arms differ in everything an implementation must ignore, and the raw file != the scrubbed file)
def test_arms_differ_in_noise(world_a):
    off = parse(W.S.git(world_a.repo, "show", f"{world_a.evidence_ref}:{W.events_rel(world_a, 'off', 's1', 'python/alpha')}"))
    on = parse(W.S.git(world_a.repo, "show", f"{world_a.evidence_ref}:{W.events_rel(world_a, 'on', 's1', 'python/alpha')}"))
    assert {e["part"]["messageID"] for e in off}.isdisjoint({e["part"]["messageID"] for e in on})
    assert [e["timestamp"] for e in off] != [e["timestamp"] for e in on]
    assert "reasoning" in {e["type"] for e in off}
    assert any("<scratch>" in json.dumps(e) for e in off)       # the evidence branch holds the SCRUBBED copy
