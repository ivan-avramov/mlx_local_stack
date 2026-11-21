"""M76 B4b-2 (spec v1.5) — the A8 panel members (`bench.p426_panel`) and the subjective Holm family (`bench.p426_signals.kv_panel_family`).

Class of each test (comment above it): (a) reproduces a failure the spec fixes, (b) preserves an invariant, (c) new behaviour.

Interface assumptions (also in the report): `kv_members(sessions=None, a8_sessions=None)` is the spec's; `kv_panel_family` /
`kv_expected_members` take the accepted A8 sessions as the keyword `a8_sessions` (spec §6.1: "every caller passes `a8_sessions`") — the
tests pass it only when the callee's signature has that parameter, otherwise they call the callee with the members alone and expect
the A8 members it was given to be in the family. A8 members follow the A7 members in the family order.

NOT covered here (no call signature in the spec; see the report): the A8 packet (`_a8_packet`): prompt equality with the evidence
export's first user message, the protected-path assertion with a grader-accepted Rust `Cargo.toml`, and the A8 export's leak refusal
at export level. The C362 leak rule itself (`_kv_leaks`, `_kv_write_packets`) is exercised below on the baseline functions the A8
export reuses.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from bench import p426_panel as P
from bench import p426_signals as S
from bench import p426_verify as V
from bench import stats

A1_A7 = ("A1", "A2", "A3", "A4", "A5", "A7-s1", "A7-s2", "A7-s3")


def call(fn, *args, a8=None, **kw):
    """`fn(*args, **kw)` passing `a8_sessions=a8` only when `fn` takes it."""
    if a8 is not None and "a8_sessions" in inspect.signature(fn).parameters:
        kw["a8_sessions"] = a8
    return fn(*args, **kw)


# ------------------------------------------------------------------------------------------------------------------ members
# (b) with no A8 sessions the family is exactly today's
def test_members_without_a8_are_unchanged():
    assert P.kv_members() == A1_A7
    assert P.kv_members(None, None) == A1_A7 and P.kv_members(sessions=("s1", "s2", "s3")) == A1_A7


# (c) A8 members are one per accepted confirmatory session, after the A7 members
def test_members_gain_one_a8_member_per_accepted_session():
    got = P.kv_members(a8_sessions=("s1", "s2"))
    assert got[:len(A1_A7)] == A1_A7 and got[len(A1_A7):] == ("A8-s1", "A8-s2")
    assert P.kv_members(a8_sessions=("s2",))[len(A1_A7):] == ("A8-s2",)
    assert P.kv_members(a8_sessions=()) == A1_A7


# (c) A8 packets are judged on the code rubric; the input source is the polyglot start tree
def test_a8_rubric_and_input_source():
    assert P.kv_rubric("A8-s1") == "code" and P.kv_rubric("A8-s2") == "code" and P.kv_rubric("A7-s1") == "code"
    src = P.KV_INPUT_SOURCE["A8"]
    assert isinstance(src, str) and "polyglot" in src.lower()
    assert set(P.KV_INPUT_SOURCE) >= {"A1", "A2", "A3", "A4", "A5", "A7", "A8"}


# (c) the expected members of a record: A8 ones only when its sessions are passed (the accepted ones); never without
def test_expected_members_follow_the_accepted_a8_sessions():
    b8 = {"axes": {"wave1": {"pairs": []}}}
    assert call(P.kv_expected_members, b8) == []
    params = inspect.signature(P.kv_expected_members).parameters
    assert any("a8" in p for p in params), "kv_expected_members has no A8 parameter (the accepted A8 sessions)"
    if "a8_sessions" in params:
        assert call(P.kv_expected_members, b8, a8=("s1", "s2")) == ["A8-s1", "A8-s2"]


# ------------------------------------------------------------------------------------------------------------------ Holm family
def member(vec, judged=None):
    judged = len(vec) if judged is None else judged
    return dict(judged=judged, identical=0, vector=list(vec), mean=0.5 + sum(vec) / len(vec) if vec else None,
                excluded={}, report={}, single_family=None)


def family_members(a8_vectors):
    """Hand-made members: A1 mildly for the treatment, A2 / A3 neutral-ish, A7 sessions slightly for the reference."""
    base = {"A1": member([0.1] * 14 + [-0.1] * 6), "A2": member([0.05, -0.05] * 10), "A3": member([0.2, 0.1, -0.1] * 6),
            "A5": member([0.0, 0.1, -0.1, 0.2] * 5), "A7-s1": member([-0.1] * 12 + [0.1] * 8),
            "A7-s2": member([0.1, -0.2] * 10), "A7-s3": member([0.05] * 10 + [-0.05] * 10)}
    base.update({f"A8-{s}": member(v, judged=len(v)) for s, v in a8_vectors.items()})
    return base


def family(members, a8):
    return call(S.kv_panel_family, members, a8=a8)


# (c) A8 sessions join the family: raw statistics of A1–A7 are unchanged, their Holm-adjusted p is recomputed over the larger family
def test_a8_sessions_join_the_holm_family():
    a8_vec = {"s1": [-0.3, 0.1] * 10, "s2": [0.2, -0.1, -0.2, 0.1] * 5}
    members = family_members(a8_vec)
    without = family({k: v for k, v in members.items() if not k.startswith("A8")}, a8=None)
    with_a8 = family(members, a8=("s1", "s2"))
    assert "A8-s1" in with_a8["members"] and "A8-s2" in with_a8["members"]
    for m in without["members"]:
        a, b = without["members"][m], with_a8["members"][m]
        assert a["permutation_p"] == b["permutation_p"] and a["vector"] == b["vector"] and a["mean"] == b["mean"]
    tested = [m for m in with_a8["members"] if with_a8["members"][m]["tested"]]
    want = stats.holm([with_a8["members"][m]["permutation_p"] for m in tested])
    assert [with_a8["members"][m]["holm_p"] for m in tested] == want
    assert with_a8["m"] == len(tested) == without["m"] + 2
    assert any(with_a8["members"][m]["holm_p"] != without["members"][m]["holm_p"] for m in without["members"] if without["members"][m]["tested"])


# (c) fewer than 5 judged items: reported, not tested (no p, no Holm)
def test_a8_member_with_under_five_judged_items_is_reported_not_tested():
    members = family_members({"s1": [-0.4, -0.3, -0.5], "s2": [0.1, -0.1] * 10})
    got = family(members, a8=("s1", "s2"))
    s1 = got["members"]["A8-s1"]
    assert s1["tested"] is False and s1["holm_p"] is None and s1["permutation_p"] is None and s1["judged"] == 3
    assert "A8-s1" not in got["tested"] and "A8-s2" in got["tested"]


# (c) Holm-adjusted p < .05 favouring N16 → the blocking flag, for an A8 member
def test_an_a8_member_favouring_the_reference_is_flagged():
    members = family_members({"s1": [-0.5] * 20, "s2": [0.1, -0.1] * 10})
    got = family(members, a8=("s1", "s2"))
    flags = S.kv_panel_flags(got)
    hit = [f for f in flags if f["flag"] == "panel_holm_reference_better" and f["member"] == "A8-s1"]
    assert hit and hit[0]["blocking"] is True and hit[0]["value"] < 0.05
    assert not [f for f in flags if f["member"] == "A8-s2"]


# (c) ... and one favouring X is not
def test_an_a8_member_favouring_the_treatment_is_not_flagged():
    got = family(family_members({"s1": [0.5] * 20, "s2": [0.1, -0.1] * 10}), a8=("s1", "s2"))
    assert got["members"]["A8-s1"]["tested"] is True
    assert not [f for f in S.kv_panel_flags(got) if f["member"].startswith("A8")]


# (b) with no A8 members the family is today's, member for member
def test_family_without_a8_is_unchanged():
    members = {k: v for k, v in family_members({}).items()}
    got = S.kv_panel_family(members)
    assert got["family"] == [m for m in P.kv_members() if m in members]
    tested = got["tested"]
    assert [got["members"][m]["holm_p"] for m in tested] == stats.holm([got["members"][m]["permutation_p"] for m in tested])


# ------------------------------------------------------------------------------------------------------------------ the leak rule (C362)
PAIRS = P.kv_make_pairs([("rust/demo", "ref answer", "test answer")], "n16", "x")


def export(tmp_path, ref_text, test_text, prompt="Implement the solution."):
    pairs = P.kv_make_pairs([("rust/demo", ref_text, test_text)], "n16", "x")
    out = tmp_path / "member"
    out.mkdir()
    return out, lambda: P._kv_write_packets(pairs, ["claude", "gpt"], {"rust/demo": prompt}, out, "code")


# (b) a leak that reveals the ARM refuses the export, writes nothing, and reports the pattern only (never the answer text)
@pytest.mark.parametrize("leak,pattern", [("see caslca/some-model", "caslca"), ("kv_bits=4 here", "kv_bits"), ("the n16 arm", "n16"),
                                          ("tq4 attention", "tq4"), ("m76 run", "m76"), ("m72_exact", "m72_")])
def test_an_arm_revealing_text_refuses_the_export(tmp_path, leak, pattern):
    out, run = export(tmp_path, "clean answer", f"SECRET-ANSWER-TEXT {leak}")
    with pytest.raises(V.RefusalError) as exc:
        run()
    assert "SECRET-ANSWER-TEXT" not in str(exc.value)
    assert not list(out.iterdir())


# (b) a leak that reveals the BOX (this machine's real home path) refuses
def test_the_box_home_path_refuses(tmp_path):
    out, run = export(tmp_path, "clean", f"edit {Path.home()}/project/file")
    with pytest.raises(V.RefusalError):
        run()
    assert not list(out.iterdir())


# (b) model-family tokens and generic paths are ANSWER CONTENT under the KV lever, never a leak (C362)
def test_family_tokens_and_generic_paths_are_answer_content(tmp_path):
    ref = "Qwen2.5 and NVIDIA are mentioned; the API route is /home/svc/app and /private/tmp/x"  # allow-shorthand allow-pii-pattern: a leak-rule input (a fake home path the rule must catch)
    out, run = export(tmp_path, ref, "see /Users/example-nobody/workdir for Qwen3 notes")  # allow-pii-pattern: a leak-rule input (a fake home path the rule must catch)
    rows = run()
    assert rows and (out / "manifest.jsonl").is_file()


# ------------------------------------------------------------------------------------------------------------------ the mechanism the protected-path assertion uses
# (b) `protected_manifest` keeps the protected tests, build files and Rust Cargo.toml, drops the editable solutions and `.docs/`:
# the set against which the A8 packet asserts "nothing protected is new or changed except a Rust Cargo.toml"
def test_protected_manifest_holds_cargo_toml_and_the_tests():
    from bench import structured_grade as sg

    prepared = {"Cargo.toml": "a" * 64, "src/lib.rs": "b" * 64, "tests/demo.rs": "c" * 64, ".docs/instructions.md": "d" * 64,
                "OFFLINE_CRATES.md": "e" * 64}
    prot = sg.protected_manifest(prepared, ["src/lib.rs"])
    assert set(prot) == {"Cargo.toml", "tests/demo.rs", "OFFLINE_CRATES.md"}
