"""P445: the tg2 tests' tree root. It must be neither under TMPDIR (P361: OrbStack bind mounts serve stale sizes) nor inside a
git work tree (`tg2_grade.rust_lock_files` refuses untracked locks there), so it lives under $STACK_WORKDIR; without it the
module SKIPS with this reason (AGENTS.md: an unavailable dependency is skipped with an explanation, never a false failure)."""

import os
from pathlib import Path

import pytest

REASON = "STACK_WORKDIR unset: tg2 tests need a root outside TMPDIR and outside any git work tree (P361 / P445)"


def tg2_root():
    base = os.environ.get("STACK_WORKDIR")
    if not base:
        pytest.skip(REASON, allow_module_level=True)
    root = Path(base) / "m65" / "test-tmp"
    root.mkdir(parents=True, exist_ok=True)
    return root
