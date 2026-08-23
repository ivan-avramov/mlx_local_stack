"""AGENTS.md is loaded into EVERY session's context — its size is a per-session tax.

The 2026-08-23 cleanup moved rationale/history to docs/ (metrics, serving-path, box-notes,
two-box-archive) and cut the file from ~124KB to under 20KB. This guard stops silent regrowth:
new rules go in TERSE (state the rule, point to the doc for the why). If this test fails,
move the essay to the appropriate doc instead of raising the limit.
"""
from pathlib import Path

_AGENTS = Path(__file__).resolve().parents[3] / "AGENTS.md"
_LIMIT_BYTES = 28_000  # ~7k tokens; cleanup landed at ~17KB, leaving real headroom


def test_agents_md_stays_terse():
    size = _AGENTS.stat().st_size
    assert size <= _LIMIT_BYTES, (
        f"AGENTS.md is {size} bytes (limit {_LIMIT_BYTES}). It is loaded every session — "
        "move rationale to docs/metrics.md, docs/serving-path.md, docs/box-notes.md or a new "
        "doc, and keep only the terse rule + pointer here."
    )
