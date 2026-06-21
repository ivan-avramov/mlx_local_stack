"""Adapter that drives the official Aider polyglot benchmark against our mlx-serve
OpenAI-compatible endpoint and normalizes its pass-rate. Aider's harness does its own
edit loop + per-exercise test execution; we only orchestrate + parse. The harness +
exercises install/clone only where this runs (optional); detected lazily, graceful-degrade."""
import os
import re
import subprocess
import sys

AXIS = "agentic_coding"


def aider_available(aider_repo: str) -> bool:
    """The aider benchmark harness lives in the aider REPO (not the pip package)."""
    return bool(aider_repo) and os.path.isfile(os.path.join(aider_repo, "benchmark", "benchmark.py"))


def parse_pass_rate(stdout: str) -> dict:
    """Extract pass_rate_1 / pass_rate_2 (percentages) from aider benchmark stdout."""
    out = {}
    for k in ("pass_rate_1", "pass_rate_2"):
        m = re.search(rf"{k}\s*[:=]\s*([0-9.]+)", stdout or "")
        out[k] = float(m.group(1)) if m else None
    return out
