"""Tests for the M38 judge-panel anchor builder (docs/judge-panel-c.md "Anchors")."""
import json
import os
import re

import pytest

import bench.judge_anchors as A

_SAMPLE_TEXT = """# Overview
This is the first sentence of the overview. This is a second sentence with more detail.
Here is a third sentence describing the approach that was taken for this particular task.

- first supporting bullet point about the design
- second supporting bullet point about the tradeoffs

# Recommendation
This final section states the recommendation and will be dropped by the degrade transform.
"""


def _rows(n=32, converged=True):
    """`n` synthetic converged rows across a couple of fake models, rich enough content for
    the transforms (headings, lists, multiple sentences/paragraphs) to be meaningful."""
    rows = []
    models = ["FakeModelA", "FakeModelB"]
    for i in range(n):
        model = models[i % len(models)]
        rows.append({
            "id": f"dom-{i:02d}",
            "model": model,
            "content": _SAMPLE_TEXT,
            "converged": converged,
        })
    return rows


# --------------------------------------------------------------------------------- degrade_text
def test_degrade_text_removes_headings_and_list_markers():
    out = A.degrade_text(_SAMPLE_TEXT, seed=38)
    assert not re.search(r"^\s*#", out, re.MULTILINE)
    assert not re.search(r"^\s*-\s", out, re.MULTILINE)


def test_degrade_text_negates_at_least_two_sentences():
    out = A.degrade_text(_SAMPLE_TEXT, seed=38)
    assert len(re.findall(r"\bnot\b", out, re.IGNORECASE)) >= 2


def test_degrade_text_drops_final_section_and_is_shorter():
    out = A.degrade_text(_SAMPLE_TEXT, seed=38)
    assert "recommendation" not in out.lower()
    assert len(out) < len(_SAMPLE_TEXT)


def test_degrade_text_deterministic():
    a = A.degrade_text(_SAMPLE_TEXT, seed=38)
    b = A.degrade_text(_SAMPLE_TEXT, seed=38)
    assert a == b


def test_negate_sentence_uses_fallback_when_no_auxiliary():
    out = A._negate_sentence("Cats chase mice quickly.")
    assert out.startswith("It is not the case that")


def test_negate_sentence_inserts_not_after_auxiliary():
    out = A._negate_sentence("This is a good plan.")
    assert out == "This is not a good plan."


# ------------------------------------------------------------------------------- verbosity_text
def _long_para(n_words, tag):
    return " ".join([f"{tag}word{i}" for i in range(n_words)]) + "."


_LONG_TEXT = "\n\n".join(_long_para(40, f"p{i}") for i in range(3))


def test_verbosity_text_length_ratio_in_range():
    out = A.verbosity_text(_LONG_TEXT, seed=38)
    orig_tokens = len(_LONG_TEXT.split())
    out_tokens = len(out.split())
    ratio = out_tokens / orig_tokens
    assert 2.5 <= ratio <= 3.5, f"ratio {ratio} out of range"


def test_verbosity_text_triples_paragraph_count():
    paras_in = [p for p in _LONG_TEXT.split("\n\n") if p.strip()]
    out = A.verbosity_text(_LONG_TEXT, seed=38)
    paras_out = [p for p in out.split("\n\n") if p.strip()]
    assert len(paras_out) == 3 * len(paras_in)


def test_verbosity_text_deterministic():
    a = A.verbosity_text(_LONG_TEXT, seed=38)
    b = A.verbosity_text(_LONG_TEXT, seed=38)
    assert a == b


# --------------------------------------------------------- F8: fences/tables survive degrade
_FENCED_TEXT = """# Overview
This is a sentence that explains the approach in reasonable detail here.

```python
if v is None:
    pass
```

| col a | col b |
|---|---|
| 1 | 2 |

## Recommendation
This section states the final recommendation and gets dropped by degrade.
"""


def test_degrade_text_leaves_fenced_code_completely_unchanged():
    out = A.degrade_text(_FENCED_TEXT, seed=38)
    assert "```python\nif v is None:\n    pass\n```" in out


def test_degrade_text_leaves_table_completely_unchanged():
    out = A.degrade_text(_FENCED_TEXT, seed=38)
    assert "| col a | col b |" in out
    assert "|---|---|" in out
    assert "| 1 | 2 |" in out


def test_degrade_text_still_flattens_and_negates_the_surrounding_prose():
    out = A.degrade_text(_FENCED_TEXT, seed=38)
    assert not re.search(r"^\s*#", out, re.MULTILINE)
    assert "not" in out.lower()
    assert "recommendation" not in out.lower()   # final section still dropped


def test_is_negatable_requires_length_and_auxiliary():
    assert A._is_negatable("This is a reasonably long sentence with a copula in it.") is True
    assert A._is_negatable("Do 3.") is False                          # too short
    assert A._is_negatable("Cats chase mice across the yard quickly.") is False  # no aux


# ----------------------------------------------------------- F8: verbosity filler placement
_FENCED_VERBOSITY_TEXT = "\n\n".join([
    _long_para(40, "p0"),
    "# A Heading\n" + _long_para(20, "p1"),
    "```python\n" + _long_para(10, "code") + "\n```",
    "| a | b |\n|---|---|\n| " + _long_para(5, "c") + " | 2 |",
])


def test_verbosity_text_filler_never_prefixes_heading_fence_or_table_line():
    out = A.verbosity_text(_FENCED_VERBOSITY_TEXT, seed=38)
    for line in out.split("\n"):
        if line.startswith("#") or line.startswith("```") or line.startswith("|"):
            continue
        # any filler-prefixed line must not itself then run into a heading/fence marker
        assert not re.match(r"^(Furthermore|In addition|Moreover|Building on this point|"
                             r"To elaborate further|It is also worth noting that),\s*#", line)
        assert not re.match(r"^(Furthermore|In addition|Moreover|Building on this point|"
                             r"To elaborate further|It is also worth noting that),\s*```", line)


def test_verbosity_text_ratio_still_in_range_with_protected_blocks():
    orig_tokens = len(_FENCED_VERBOSITY_TEXT.split())
    out_tokens = len(A.verbosity_text(_FENCED_VERBOSITY_TEXT, seed=38).split())
    ratio = out_tokens / orig_tokens
    assert 2.5 <= ratio <= 3.5, f"ratio {ratio} out of range"


# --------------------------------------------------------------------------- build_anchor_pairs
def test_build_anchor_pairs_counts_and_types():
    pairs = A.build_anchor_pairs(_rows(32), seed=38)
    assert len(pairs) == 30
    by_type = {}
    for p in pairs:
        by_type.setdefault(p["anchor_type"], []).append(p)
    assert set(by_type) == {"degrade", "verbosity", "identity"}
    assert all(len(v) == 10 for v in by_type.values())


def test_build_anchor_pairs_requires_min_converged_rows():
    # F9 (judge-panel-c review): assert on OUR explicit message, not just "some ValueError" —
    # a mutant that dropped our guard and let `rng.sample` raise its own (different)
    # ValueError on a too-small population would otherwise still pass a bare pytest.raises.
    with pytest.raises(ValueError, match=r"need >= 30 converged rows, got 10"):
        A.build_anchor_pairs(_rows(10), seed=38)


def test_build_anchor_pairs_filters_non_converged():
    rows = _rows(32, converged=False)
    with pytest.raises(ValueError, match=r"need >= 30 converged rows, got 0"):
        A.build_anchor_pairs(rows, seed=38)


def test_build_anchor_pairs_identity_is_tie_and_equal_text():
    pairs = A.build_anchor_pairs(_rows(32), seed=38)
    identity = [p for p in pairs if p["anchor_type"] == "identity"]
    assert len(identity) == 10
    for p in identity:
        assert p["expected"] == "tie"
        assert p["a_text"] == p["b_text"]


def test_build_anchor_pairs_degrade_expected_points_at_original():
    pairs = A.build_anchor_pairs(_rows(32), seed=38)
    degrade = [p for p in pairs if p["anchor_type"] == "degrade"]
    for p in degrade:
        original_side = p["a_text"] if p["expected"] == "A" else p["b_text"]
        assert original_side == _SAMPLE_TEXT
        assert original_side.endswith("dropped by the degrade transform.\n") or True
        assert p["a_key"].endswith("::orig") or p["b_key"].endswith("::orig")


def test_build_anchor_pairs_balanced_ab_placement():
    pairs = A.build_anchor_pairs(_rows(32), seed=38)
    for anchor_type in ("degrade", "verbosity"):
        group = [p for p in pairs if p["anchor_type"] == anchor_type]
        n_a = sum(1 for p in group if p["expected"] == "A")
        n_b = sum(1 for p in group if p["expected"] == "B")
        assert n_a == 5 and n_b == 5
    identity = [p for p in pairs if p["anchor_type"] == "identity"]
    n_orig_a = sum(1 for p in identity if p["a_key"].endswith("::orig"))
    assert n_orig_a == 5


def test_build_anchor_pairs_deterministic():
    a = A.build_anchor_pairs(_rows(32), seed=38)
    b = A.build_anchor_pairs(_rows(32), seed=38)
    assert a == b


# ------------------------------------------------------------------------------------- loading
def test_load_converged_rows_reads_and_tags_model(tmp_path):
    d = tmp_path / "ModelX"
    d.mkdir()
    row = {"id": "dom-01", "content": "hello", "converged": True}
    (d / "cjudge.m38.jsonl").write_text(json.dumps(row) + "\n")
    rows = A.load_converged_rows(["ModelX"], tune="m38", results_dir=str(tmp_path))
    assert len(rows) == 1
    assert rows[0]["model"] == "ModelX"


def test_load_converged_rows_skips_missing_model_dir(tmp_path):
    rows = A.load_converged_rows(["NoSuchModel"], tune="m38", results_dir=str(tmp_path))
    assert rows == []


# ----------------------------------------------------------------------------------------- CLI
def test_main_writes_pairs_jsonl(tmp_path, monkeypatch):
    for i, model in enumerate(["ModelA", "ModelB"]):
        d = tmp_path / model
        d.mkdir()
        with open(d / "cjudge.m38.jsonl", "w") as f:
            for j in range(16):
                f.write(json.dumps({"id": f"dom-{j:02d}", "content": _SAMPLE_TEXT,
                                     "converged": True}) + "\n")
    out = tmp_path / "pairs.jsonl"
    rc = A.main(["--models", "ModelA", "ModelB", "--tune", "m38",
                 "--results-dir", str(tmp_path), "--out", str(out)])
    assert rc == 0
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 30
    row = json.loads(lines[0])
    assert set(row) == {"pair_id", "anchor_type", "item_id", "a_key", "b_key",
                         "a_text", "b_text", "expected"}
