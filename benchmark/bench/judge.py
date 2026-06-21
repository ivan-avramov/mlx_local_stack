"""Mixed-family LLM judge panel for the SUBJECTIVE code-quality rubric. Scores only
execution-PASSING coding outputs; the judge is never a correctness oracle. Backends
(Anthropic Sonnet/Opus, GPT-5.5 via the codex CLI) are optional + lazy + graceful-degrade;
the panel aggregates by per-axis median and reports per-judge scores."""
import json
import re
import statistics
import subprocess

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


def anthropic_judge(model_id, system, user, max_tokens: int = 4096, client=None) -> str | None:
    """Score via the Anthropic API (Sonnet/Opus). Lazy-imports anthropic; graceful-degrade
    (missing package / no API key / API error) -> None. Adaptive thinking; no sampling params
    (removed on Opus 4.8)."""
    try:
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model_id, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
            thinking={"type": "adaptive"})
        return next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
    except Exception:  # noqa: BLE001 — optional backend; degrade
        return None


def codex_judge(system, user, runner=subprocess.run) -> str | None:
    """Score via GPT-5.5 through a one-shot `codex` CLI invocation. Graceful-degrade if the
    codex CLI is absent (the real subprocess.run raises FileNotFoundError -> caught) or errors.
    The exact invocation is validated on first real run."""
    prompt = f"{system}\n\n{user}"
    try:
        proc = runner(["codex", "exec", prompt], capture_output=True, text=True, timeout=300)
    except Exception:  # noqa: BLE001 — codex absent (FileNotFoundError) / launch error
        return None
    if getattr(proc, "returncode", 1) != 0:
        return None
    return getattr(proc, "stdout", "") or None


DEFAULT_JUDGES = [
    ("sonnet", lambda s, u: anthropic_judge("claude-sonnet-4-6", s, u)),
    ("opus", lambda s, u: anthropic_judge("claude-opus-4-8", s, u)),
    ("gpt-5.5", codex_judge),
]


def judge_one(task, output, reference=None, judge_fns=DEFAULT_JUDGES) -> dict:
    """Run every judge on one (task, output), parse scores, and median across judges.
    Failed/unparseable judges are recorded as None and excluded from the medians."""
    system, user = build_judge_prompt(task, output, reference)
    per_judge, used = {}, []
    for name, fn in judge_fns:
        try:
            raw = fn(system, user)
        except Exception:  # noqa: BLE001 — a judge fn must not break the panel
            raw = None
        scores = parse_scores(raw) if raw else None
        per_judge[name] = scores
        if scores:
            used.append(name)
    median = {}
    for axis in RUBRIC_AXES:
        vals = [per_judge[n][axis] for n in used if axis in per_judge[n]]
        if vals:
            median[axis] = round(statistics.median(vals), 2)
    return {"per_judge": per_judge, "median": median,
            "judges_used": used, "n_judges": len(used)}


def aggregate(records: list) -> dict:
    """Aggregate per-record judge_one outputs: overall = mean across records of each record's
    mean-axis-median; per_axis = mean across records of that axis's median; low_confidence if
    any record had fewer than 2 judges."""
    if not records:
        return {"overall": None, "per_axis": {}, "n_records": 0, "low_confidence": True}
    record_overalls = []
    for r in records:
        med = r.get("median") or {}
        if med:
            record_overalls.append(statistics.mean(med.values()))
    per_axis = {}
    for axis in RUBRIC_AXES:
        vals = [r["median"][axis] for r in records if (r.get("median") or {}).get(axis) is not None]
        if vals:
            per_axis[axis] = round(statistics.mean(vals), 2)
    overall = round(statistics.mean(record_overalls), 2) if record_overalls else None
    low_conf = any((r.get("n_judges", 0) < 2) for r in records)
    return {"overall": overall, "per_axis": per_axis,
            "n_records": len(records), "low_confidence": low_conf}
