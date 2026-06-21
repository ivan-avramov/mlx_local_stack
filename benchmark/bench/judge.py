"""Mixed-family LLM judge panel for the SUBJECTIVE code-quality rubric. Scores only
execution-PASSING coding outputs; the judge is never a correctness oracle. Backends
(Anthropic Sonnet/Opus, GPT-5.5 via the codex CLI) are optional + lazy + graceful-degrade;
the panel aggregates by per-axis median and reports per-judge scores."""
import json
import re

# The 10 subjective code-quality axes (correctness-of-reasoning is advisory; binding
# correctness is execution, not the judge).
RUBRIC_AXES = ["reasoning", "robustness", "readability", "maintainability", "design",
               "performance", "security", "testability", "portability", "operational"]

_ANCHORS = ("Score each axis 1-5: 1=poor, 2=below average, 3=adequate, 4=good, "
            "5=excellent. 'reasoning' is advisory only (correctness is verified separately "
            "by execution).")


def build_judge_prompt(task: str, output: str, reference: str | None = None) -> tuple[str, str]:
    """Blind judge prompt — never names the producing model. Returns (system, user)."""
    system = ("You are a senior code reviewer scoring the SUBJECTIVE quality of a code "
              "solution that has ALREADY passed its tests. Judge only quality, not whether "
              "it works. " + _ANCHORS + " Axes: " + ", ".join(RUBRIC_AXES) + ". "
              'Reply with ONLY a JSON object: {"scores": {<axis>: <1-5 int>, ...}, '
              '"rationale": "<one paragraph>"}. No prose outside the JSON.')
    parts = [f"## Task\n{task}\n", f"## Candidate solution\n{output}\n"]
    if reference:
        parts.append(f"## Reference solution (for comparison)\n{reference}\n")
    parts.append("Score every axis. Output only the JSON object.")
    return system, "\n".join(parts)


def parse_scores(text: str) -> dict | None:
    """Extract the first JSON object from `text` and return {axis: int in 1..5} for the
    recognized RUBRIC_AXES (clamped). None if nothing valid parses."""
    if not text:
        return None
    # Find the first {...} block (greedy enough for a single flat scores object).
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    raw = obj.get("scores") if isinstance(obj, dict) else None
    if not isinstance(raw, dict):
        return None
    out = {}
    for axis in RUBRIC_AXES:
        v = raw.get(axis)
        if isinstance(v, (int, float)):
            out[axis] = max(1, min(5, int(round(v))))
    return out or None
