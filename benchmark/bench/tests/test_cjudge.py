"""Tests for the cjudge corpus loader and open-kind grading (docs/judge-panel-c.md 'Corpus
cjudge'): 40 committed prompts (18 public, hand-curated from a seeded draw of 30, + 22
verbatim domain), no mechanical grading."""
import json
import os
import re

import pytest

import bench.benchmarks as B
import bench.grade as G

DOC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs", "judge-panel-c.md")


def _spec_dom_prompts():
    text = open(DOC, encoding="utf-8").read()
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r"^(dom-\d\d): (.+)$", text, flags=re.M)}


def test_spec_has_22_domain_prompts():
    # Guards the fixture above against a doc edit silently shrinking the block.
    assert len(_spec_dom_prompts()) == 22


def test_cjudge_spec_entry():
    assert B.SPECS["cjudge"] == {"kind": "open", "answer_type": "none", "gated": False}


def test_cjudge_loads_40_unique_items_with_nonempty_prompts():
    items = B.load("cjudge", limit=None, seed=0)
    assert len(items) == 40
    ids = [it["id"] for it in items]
    assert len(set(ids)) == 40
    for it in items:
        assert it["prompt"].strip()


def test_cjudge_is_18_public_plus_22_domain():
    ids = [it["id"] for it in B.load("cjudge", limit=None, seed=0)]
    pub = [i for i in ids if i.startswith("pub-")]
    dom = [i for i in ids if i.startswith("dom-")]
    assert len(pub) == 18
    assert len(dom) == 22
    assert sorted(dom) == [f"dom-{i:02d}" for i in range(1, 23)]


# The 12 draw-30 items the coordinator excluded on 2026-09-11 as too generic/off-topic for
# role C (research/brainstorming/design in a technical setting) -- must never resurface.
EXCLUDED_PUB_PREFIXES = (
    "pub-666658ee", "pub-1cf362fd", "pub-34690d25", "pub-7956046c", "pub-9cdabaf5",
    "pub-52b9f9d3", "pub-1db228a5", "pub-fdfea302", "pub-c35cf870", "pub-ed3077a3",
    "pub-188f0735", "pub-26d31603",
)


def test_cjudge_excludes_the_12_curated_out_ids():
    ids = [it["id"] for it in B.load("cjudge", limit=None, seed=0)]
    for prefix in EXCLUDED_PUB_PREFIXES:
        assert not any(i.startswith(prefix) for i in ids), prefix


def test_cjudge_limit_is_a_seeded_random_subsample_not_a_prefix():
    first_five_in_file_order = [json.loads(l)["id"] for l in open(B._CJUDGE_PATH)][:5]
    sub = B.load("cjudge", limit=5, seed=0)
    assert len(sub) == 5
    assert [it["id"] for it in sub] != first_five_in_file_order


def test_cjudge_limit_is_deterministic_per_seed():
    a = B.load("cjudge", limit=5, seed=0)
    b = B.load("cjudge", limit=5, seed=0)
    assert [it["id"] for it in a] == [it["id"] for it in b]


def test_cjudge_domain_prompts_match_spec_verbatim():
    spec = _spec_dom_prompts()
    items = {it["id"]: it for it in B.load("cjudge", limit=None, seed=0)}
    assert set(spec) <= set(items)
    for did, text in spec.items():
        row = items[did]
        assert row["prompt"] == text
        assert row["source"] == "operator-domain"


def test_cjudge_no_system_prompt_suffix():
    item = B.load("cjudge", limit=1, seed=0)[0]
    msgs = B.build_messages("cjudge", item)
    assert msgs == [{"role": "user", "content": item["prompt"]}]


def test_grade_open_kind_is_noop_and_never_crashes(write_rows):
    write_rows("m", "cjudge", [
        {"id": "pub-x", "sample": 0, "schema_version": 2, "content": "some open-ended answer",
         "completion_tokens": 50, "thinking_budget": 8192, "finish_reason": "stop"},
        {"id": "dom-01", "sample": 0, "schema_version": 2, "content": "another answer",
         "completion_tokens": 50, "thinking_budget": 8192, "finish_reason": "stop"},
    ])
    score = G.grade("cjudge", "m")
    assert score["acc"] is None
    assert score["n"] == 2
    assert "note" in score
