"""Adapter that drives the official BFCL harness (`bfcl-eval`) against our mlx-serve
OpenAI-compatible endpoint and normalizes its scores. Single-turn AST categories only.
`bfcl-eval` is an optional heavy dependency: detected lazily, graceful-degrade if absent."""
import json
import os
import shutil
import subprocess

AST_CATEGORIES = ("simple", "multiple", "parallel", "parallel_multiple")


def _read_summary(path: str) -> dict | None:
    """BFCL score files are JSONL; line 0 is the summary {accuracy, correct_count, total_count}."""
    try:
        with open(path, encoding="utf-8") as f:
            first = f.readline().strip()
        if not first:
            return None
        obj = json.loads(first)
        if "accuracy" not in obj:
            return None
        return obj
    except (OSError, json.JSONDecodeError):
        return None


def parse_scores(score_dir: str, model: str, categories=AST_CATEGORIES) -> dict:
    """Read BFCL per-category score files and normalize to one record. `acc` is the
    count-weighted overall accuracy (0-1) across the categories that produced a score;
    a missing/malformed category maps to None and is excluded from the overall."""
    per_category: dict = {}
    correct = total = 0
    for cat in categories:
        path = os.path.join(score_dir, model, f"BFCL_v3_{cat}_score.json")
        summ = _read_summary(path)
        if summ is None:
            per_category[cat] = None
            continue
        c = int(summ.get("correct_count", 0))
        t = int(summ.get("total_count", 0))
        per_category[cat] = {"accuracy": summ.get("accuracy"), "correct": c, "total": t}
        correct += c
        total += t
    acc = round(correct / total, 4) if total else None
    return {"per_category": per_category, "acc": acc, "n": total}


def bfcl_available() -> bool:
    return shutil.which("bfcl") is not None


def _cli(phase, model, categories, result_dir, score_dir, limit):
    cmd = ["bfcl", phase, "--model", model,
           "--test-category", ",".join(categories)]
    if phase == "generate":
        cmd += ["--num-threads", "1", "--skip-server-setup",
                "--result-dir", result_dir]
        if limit is not None:
            cmd += ["--num-tests", str(limit)]
    else:  # evaluate
        cmd += ["--result-dir", result_dir, "--score-dir", score_dir]
    return cmd


def run_bfcl(model, categories=AST_CATEGORIES, endpoint="localhost", port=8000,
             result_dir="bfcl_runs/result", score_dir="bfcl_runs/score",
             limit=None, runner=subprocess.run) -> dict:
    """Drive bfcl-eval against the local mlx-serve endpoint for the AST single-turn
    categories, then normalize the scores. `runner` is injectable for tests. Lazy-detected;
    graceful-degrade if `bfcl` is absent or a phase exits non-zero."""
    base = {"model": model, "axis": "tool_calling", "categories": list(categories)}
    if not bfcl_available():
        return {**base, "acc": None, "n": 0, "skipped": True,
                "note": "bfcl CLI not found; pip install bfcl-eval where BFCL runs (see README)"}
    env = {**os.environ, "LOCAL_SERVER_ENDPOINT": endpoint, "LOCAL_SERVER_PORT": str(port)}
    for phase in ("generate", "evaluate"):
        proc = runner(_cli(phase, model, categories, result_dir, score_dir, limit),
                      env=env, capture_output=True, text=True)
        if getattr(proc, "returncode", 0) != 0:
            return {**base, "acc": None, "n": 0, "skipped": False,
                    "note": f"bfcl {phase} failed rc={proc.returncode}: {(proc.stderr or '')[:160]}"}
    return {**base, **parse_scores(score_dir, model, categories), "skipped": False}
