"""SWE-bench-Verified adapter: stratified subset, an explore-and-patch agent, and a driver
for the official swebench evaluation harness. The harness (docker) + dataset + the model-driven
agent are execution-phase; lazy-imported + graceful-degrade + injectable seams so this builds
and unit-tests with no heavy deps."""
import json
import random
from collections import defaultdict


def stratify(instances: list, n: int, seed: int = 0) -> list:
    """Deterministic stratified-by-repo subset of size <= n: round-robin across repos,
    shuffled within each repo by seed."""
    by_repo = defaultdict(list)
    for it in instances:
        by_repo[it.get("repo")].append(it)
    rng = random.Random(seed)
    for repo in by_repo:
        rng.shuffle(by_repo[repo])
    repos = sorted(by_repo)
    out, i = [], 0
    while len(out) < n and any(by_repo[r] for r in repos):
        r = repos[i % len(repos)]
        if by_repo[r]:
            out.append(by_repo[r].pop())
        i += 1
        if i % len(repos) == 0 and not any(by_repo[r] for r in repos):
            break
    return out[:n]


def write_predictions(path: str, preds: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for p in preds:
            f.write(json.dumps(p) + "\n")


def parse_report(report: dict) -> dict:
    """Normalize a swebench report to {resolved, total, resolve_rate}. Defensive about the
    exact key names across swebench versions (resolved_instances list OR a resolved count)."""
    resolved = report.get("resolved_instances", report.get("resolved"))
    if isinstance(resolved, list):
        resolved = len(resolved)
    total = report.get("total_instances", report.get("total"))
    if isinstance(total, list):
        total = len(total)
    rate = (resolved / total) if (isinstance(resolved, int) and isinstance(total, int) and total) else None
    return {"resolved": resolved, "total": total,
            "resolve_rate": round(rate, 4) if rate is not None else None}
