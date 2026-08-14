"""AGENTS.md: ALWAYS the FULL registry name in reports, results and docs — never a shorthand.

The rule exists because the candidate field is full of near-collisions across architecture, bit-width
and packager — `gemma-4-26B-A4B-it-QAT-MLX-4bit` (MoE, 4-bit, lmstudio) vs `gemma-4-31B-it-qat-6bit`
(dense, 6-bit, mlx-community), multiple OptiQ-4bit/6bit variants across two families — so a shorthand
is genuinely ambiguous rather than merely terse. A "QAT < OptiQ" reading was already conflated this way.

"the distill" was the live violation: 58 occurrences across six docs, 24 of them written on
2026-08-13 alone, referring to Qwen3.6-27B-Opus-Distill-OptiQ-4bit. RUN TAGS keep their shorthand
(`distill/java`, `distill-diff-t03`, `distill-kv3`) because those name directories and result files,
not models — hence the boundary check below.
"""
import re
from pathlib import Path

import pytest

_DOCS = Path(__file__).resolve().parents[3] / "docs"
# Bare shorthand, but NOT when followed by - or / (a run tag / result-dir name such as
# `distill/java` or `distill-kv3`, which name directories and files rather than models).
_BARE = re.compile(r"\bthe distill\b(?![-/])", re.IGNORECASE)
_FULL_NAME = "Qwen3.6-27B-Opus-Distill-OptiQ-4bit"
# A SECTION heading like "the DISTILL SCAN" names a document section, not a model.
_SECTION = re.compile(r"\bthe distill\s+scan\b", re.IGNORECASE)


def _violations(text: str):
    """A line is compliant when it already carries the full registry name — the rule exists to
    DISAMBIGUATE, so `the DISTILL (\`Qwen3.6-27B-Opus-Distill-OptiQ-4bit\`, ...)` is fine."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        if not _BARE.search(line):
            continue
        if _FULL_NAME in line or _SECTION.search(line):
            continue
        out.append((i, line.strip()[:90]))
    return out


def _markdown_files():
    return sorted(p for p in _DOCS.rglob("*.md"))


@pytest.mark.parametrize("doc", _markdown_files(), ids=lambda p: p.name)
def test_no_bare_distill_shorthand(doc):
    hits = _violations(doc.read_text())
    assert not hits, (
        f"{doc.relative_to(_DOCS.parent)} uses the shorthand 'the distill' at "
        f"{[h[0] for h in hits]} — use the full registry name "
        f"Qwen3.6-27B-Opus-Distill-OptiQ-4bit. First: {hits[0][1] if hits else ''}")


def test_run_tags_are_still_allowed():
    """The rule must not force `distill/java` (a results directory) to be renamed."""
    assert not _violations("distill/java had 22 files for a batch that ran 1")
    assert not _violations("the distill-kv3 registry variant")
    assert _violations("the distill wins on repair"), "a real violation must still be caught"


def test_a_line_carrying_the_full_name_is_compliant():
    """The rule is about DISAMBIGUATION, not about banning a word."""
    assert not _violations("the DISTILL (`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`) at its op-temp")


def test_a_section_heading_is_not_a_model_reference():
    assert not _violations("- Claude-Opus community distills -> see the DISTILL SCAN above")
