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
