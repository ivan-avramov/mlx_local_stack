#!/usr/bin/env python3
"""Paired suffix ON/OFF accuracy for the four OFAT cells (handoff THEN-item 1).

ON per-item verdicts come from git HEAD (the 2026-08-14 grade of the then-suffix-ON rows);
OFF verdicts from the working tree (graded 2026-08-17). Restricted to items with a real
completion in BOTH arms (excludes Qwen3.6-27B-Opus-Distill-OptiQ-4bit Mbpp/430, which
timed out in the OFF arm). Headline metric = the stricter plus_status, matching `acc`.
"""
import json
import subprocess
import sys

sys.path.insert(0, "$STACK_REPO/benchmark")
from m1.suffix_ofat import accuracy  # noqa: E402

REPO = "$STACK_REPO"
CELLS = [
    ("Ornith-1.0-35B-mlx-uniform-4bit", "humanevalplus"),
    ("Ornith-1.0-35B-mlx-uniform-4bit", "mbppplus"),
    ("Qwen3.6-27B-Opus-Distill-OptiQ-4bit", "humanevalplus"),
    ("Qwen3.6-27B-Opus-Distill-OptiQ-4bit", "mbppplus"),
]


def per_item(eval_json: dict, keep: set) -> dict:
    out = {}
    for tid, samples in eval_json["eval"].items():
        if tid in keep and samples:
            out[tid] = [1.0 if samples[0]["plus_status"] == "pass" else 0.0]
    return out


def real_ids(jsonl_path: str) -> set:
    ids = set()
    for line in open(jsonl_path):
        r = json.loads(line)
        if not r.get("error"):
            ids.add(r["id"])
    return ids


for model, bench in CELLS:
    rel = f"benchmark/results/{model}/{bench}_samples_eval_results.json"
    on_eval = json.loads(
        subprocess.check_output(["git", "-C", REPO, "show", f"HEAD:{rel}"]).decode()
    )
    off_eval = json.load(open(f"{REPO}/{rel}"))
    on_ids = real_ids(f"{REPO}/benchmark/results/{model}/{bench}.suffixon.jsonl")
    off_ids = real_ids(f"{REPO}/benchmark/results/{model}/{bench}.jsonl")
    keep = on_ids & off_ids
    on_pi, off_pi = per_item(on_eval, keep), per_item(off_eval, keep)
    res = accuracy(on_pi, off_pi)
    print(f"=== {model} / {bench} (paired n={res['n_items']}) ===")
    print(json.dumps(res, indent=2, default=str))
    print()
