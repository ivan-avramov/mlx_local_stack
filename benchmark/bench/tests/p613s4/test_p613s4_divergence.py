"""`a7_divergence(results_root, b8, evidence_ref, repo)` on the hermetic worlds (C284 rule, contract "The divergence section").

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.
(No `reproduces-failure` test exists: step 4 adds a feature, there is no bug to reproduce; on the baseline every test below
fails because the interface does not exist yet.)

World A: 22 accepted keys (s1 10, s2 12) with every kind; the REJECTED key `go/psi` carries a generation difference that must
never be read or counted. World B: no accepted key is `generation`. Expected tables: `s4world.EXPECT_A` / `EXPECT_B`.

Readings tested (see dview.py for the tolerant lookups): `k` is the 0-based index of the first differing message; for `cutoff`
`k` is not asserted (the contract does not fix it); `environment` records the first differing tool name.
"""
from __future__ import annotations

import json

import pytest

from bench.tests.p613s3 import s3world as S
from bench.tests.p613s4 import dview as D
from bench.tests.p613s4 import s4world as W


@pytest.fixture(scope="module")
def div_a(divmod_, world_a):
    return D.a7_div(divmod_, world_a)


@pytest.fixture(scope="module")
def div_b(divmod_, world_b):
    return D.a7_div(divmod_, world_b)


def mismatches(got, exp, *, with_k=True, with_tool=True):
    bad = []
    for key, (kind, k, tool) in sorted(exp.items()):
        g = got.get(key)
        if g is None:
            bad.append((key, "missing"))
            continue
        if g[0] != kind:
            bad.append((key, f"kind {g[0]} != {kind}"))
        elif with_k and kind in ("environment", "generation") and g[1] != k:
            bad.append((key, f"k {g[1]} != {k}"))
        elif with_tool and kind == "environment" and g[2] != tool:
            bad.append((key, f"tool {g[2]!r} != {tool!r}"))
    return bad


# class: new-behaviour (every kind, world A: kind of each of the 22 accepted keys)
def test_kinds_world_a(div_a):
    assert mismatches(D.items(div_a), W.EXPECT_A, with_k=False, with_tool=False) == []


# class: new-behaviour (k = first differing message, 0-based, for generation / environment)
def test_k_world_a(div_a):
    assert mismatches(D.items(div_a), W.EXPECT_A, with_tool=False) == []


# class: new-behaviour (environment records the first differing tool name, also when the message holds two tools)
def test_environment_tool_names(div_a):
    got = D.items(div_a)
    assert {key: got[key][2] for key, v in W.EXPECT_A.items() if v[0] == "environment"} == \
        {key: v[2] for key, v in W.EXPECT_A.items() if v[0] == "environment"}


# class: new-behaviour (exactly the 22 accepted keys: nothing missing, nothing extra; the rejected key is not read)
def test_exactly_the_accepted_keys(div_a):
    got = D.items(div_a)
    assert set(got) == set(W.EXPECT_A) and len(got) == 22
    assert ("s1", "go/psi") not in got


# class: new-behaviour (every planned key: one-arm-pass and neither-pass keys are included, not only both-pass ones)
def test_includes_one_arm_and_neither_pass_keys(div_a):
    got = D.items(div_a)
    for s, rid in (("s1", "python/delta"), ("s1", "go/theta"), ("s1", "python/epsilon"), ("s2", "go/upsilon"), ("s2", "go/phi")):
        assert (s, rid) in got


# class: new-behaviour (per-session counts per kind, and the pooled "both")
def test_counts_world_a(div_a):
    c = D.counts(div_a)
    exp = W.counts_of(W.EXPECT_A)
    assert c["s1"] == exp["s1"] and c["s2"] == exp["s2"]
    assert c["both"] == D.pooled(exp)


# class: new-behaviour (world B: no generation item; counts)
def test_counts_world_b(div_b):
    c = D.counts(div_b)
    exp = W.counts_of(W.EXPECT_B)
    assert c["s1"] == exp["s1"] and c["s2"] == exp["s2"] and c["both"] == D.pooled(exp)
    assert all(v[0] != "generation" for v in D.items(div_b).values())


# class: new-behaviour (world B kinds + k + tool)
def test_kinds_world_b(div_b):
    assert mismatches(D.items(div_b), W.EXPECT_B) == []


# class: new-behaviour (the rejected key's generation difference does not leak into world B's counts)
def test_rejected_key_not_counted(div_b):
    assert ("s1", "go/psi") not in D.items(div_b)
    assert D.counts(div_b)["s1"]["generation"] == 0


# class: invariant (parallel tool calls completing in a different order -> identical; also text before/after the tools)
def test_parallel_calls_other_completion_order_identical(div_a):
    got = D.items(div_a)
    assert got[("s1", "python/beta")][0] == "identical"
    assert got[("s2", "go/xi")][0] == "identical"          # distinct per-call outputs, order swapped: env multiset equal


# class: invariant (tool-input key order is not a difference: `state.input` is dumped with sorted keys)
def test_input_key_order_identical(div_a):
    assert D.items(div_a)[("s1", "python/gamma")][0] == "identical"


# class: invariant (message events interleaved in one arm are grouped by messageID in order of first appearance)
def test_interleaved_message_events_identical(div_a):
    assert D.items(div_a)[("s1", "python/epsilon")][0] == "identical"


# class: invariant (ids, timestamps, step / reasoning events, tokens, metadata differ between arms and never matter: the plain
# pairs are identical)
def test_noise_never_matters(div_a):
    got = D.items(div_a)
    for key in (("s1", "python/alpha"), ("s2", "python/iota"), ("s2", "go/pi"), ("s2", "python/sigma"), ("s2", "go/tau")):
        assert got[key][0] == "identical", key


# class: new-behaviour (first divergence wins: environment at k=0 although a generation difference follows in message 1)
def test_first_divergence_wins(div_a):
    kind, k, tool = D.items(div_a)[("s1", "python/delta")]
    assert (kind, k, tool) == ("environment", 0, "read")


# class: new-behaviour (gen is a MULTISET: one tool call more -> generation, same text)
def test_duplicated_tool_call_is_generation(div_a):
    assert D.items(div_a)[("s2", "go/rho")][:2] == ("generation", 0)


# class: new-behaviour (a tool input differing at message 2 while messages 0-1 are equal -> generation, k=2)
def test_tool_input_difference_is_generation(div_a):
    assert D.items(div_a)[("s1", "go/eta")][:2] == ("generation", 2)


# class: new-behaviour (strict prefix, either arm shorter -> cutoff)
def test_cutoff_either_arm_shorter(div_a):
    got = D.items(div_a)
    assert got[("s1", "go/zeta")][0] == "cutoff"           # OFF shorter
    assert got[("s2", "python/nu")][0] == "cutoff"         # ON shorter


# class: invariant (deterministic: two calls give equal records, and the record is JSON-serialisable)
def test_deterministic(divmod_, world_a, div_a):
    again = D.a7_div(divmod_, world_a)
    assert json.dumps(again, sort_keys=True) == json.dumps(div_a, sort_keys=True)


# class: invariant (no checkout: the evidence branch is read with `git show`; HEAD, branch and the work tree are untouched)
def test_no_checkout(divmod_, clone_a):
    case = clone_a()
    before = (S.git(case.repo, "rev-parse", "HEAD"), S.git(case.repo, "symbolic-ref", "-q", "HEAD"),
              S.git(case.repo, "status", "--porcelain"), sorted(p.name for p in case.repo.iterdir()))
    D.a7_div(divmod_, case)
    after = (S.git(case.repo, "rev-parse", "HEAD"), S.git(case.repo, "symbolic-ref", "-q", "HEAD"),
             S.git(case.repo, "status", "--porcelain"), sorted(p.name for p in case.repo.iterdir()))
    assert before == after
    evidence_dir = case.repo / "benchmark" / "results" / "p426" / "wave2" / "tg1-p426-on-s1.a1" / "evidence"
    assert not list(evidence_dir.glob("*/*.events.jsonl"))          # the events files exist only on the evidence ref


# class: invariant (the same bytes on a different evidence commit give the same record: the ref is only the reader)
def test_same_content_other_ref_same_record(divmod_, clone_a, div_a):
    case = clone_a()
    ref2 = case.tamper_evidence(lambda files: None)         # a new commit, identical files
    assert ref2 != case.evidence_ref
    assert json.dumps(D.a7_div(divmod_, case, ref=ref2), sort_keys=True).replace(ref2, "REF") == \
        json.dumps(div_a, sort_keys=True).replace(case.evidence_ref, "REF")
