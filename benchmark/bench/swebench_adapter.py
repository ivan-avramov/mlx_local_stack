"""SWE-bench-Verified adapter: stratified subset, an explore-and-patch agent, and a driver
for the official swebench evaluation harness. The harness (docker) + dataset + the model-driven
agent are execution-phase; lazy-imported + graceful-degrade + injectable seams so this builds
and unit-tests with no heavy deps."""
import importlib.util
import json
import os
import random
import subprocess
import sys
from collections import defaultdict

from . import agent_loop


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


AXIS = "agentic_coding"

_AGENT_SYSTEM = ("You are a software engineer. Investigate the repository with the provided "
                 "tools, then submit a single unified-diff patch that resolves the issue. "
                 "Call submit exactly once with the patch.")


def swebench_available() -> bool:
    return importlib.util.find_spec("swebench") is not None


def solve_instance(driver, model, instance, repo_dir, params, max_turns: int = 12) -> str:
    """Minimal explore-and-patch agent: read-only repo tools + submit. Returns the submitted
    unified-diff patch (or ""). The repo checkout into repo_dir is the caller's responsibility."""
    def _safe(rel):  # contain reads within repo_dir
        full = os.path.realpath(os.path.join(repo_dir, rel or "."))
        return full if full.startswith(os.path.realpath(repo_dir)) else repo_dir

    def list_dir(a):
        try:
            return "\n".join(sorted(os.listdir(_safe(a.get("path", ".")))))[:4000]
        except OSError as e:
            return f"ERROR: {e}"

    def read_file(a):
        try:
            with open(_safe(a.get("path", "")), encoding="utf-8", errors="replace") as f:
                return f.read()[:8000]
        except OSError as e:
            return f"ERROR: {e}"

    tools = [
        agent_loop.Tool("list_dir", "list files in a repo subdirectory",
                        {"type": "object", "properties": {"path": {"type": "string"}}}, list_dir),
        agent_loop.Tool("read_file", "read a repo file (first 8000 chars)",
                        {"type": "object", "properties": {"path": {"type": "string"}}}, read_file),
        agent_loop.Tool("submit", "submit the final unified-diff patch",
                        {"type": "object", "properties": {"patch": {"type": "string"}},
                         "required": ["patch"]}, lambda a: "submitted"),
    ]
    task = (f"Issue in repo {instance.get('repo')}:\n\n{instance.get('problem_statement', '')}\n\n"
            f"Explore with list_dir/read_file, then submit a unified diff patch.")
    out = agent_loop.run_agent(driver, model, _AGENT_SYSTEM, task, tools, params, max_turns=max_turns)
    sub = out.get("submitted") or {}
    return sub.get("patch", "") or ""


def _load_verified(dataset: str, instances=None) -> list:
    if instances is not None:
        return instances
    from datasets import load_dataset
    ds = load_dataset(dataset, split="test")
    return [dict(row) for row in ds]


def run_swebench(model, n: int = 40, seed: int = 0, dataset: str = "princeton-nlp/SWE-bench_Verified",
                 run_id: str = "bake", instances=None, driver=None, params=None,
                 repo_provider=None, agent_fn=solve_instance, harness_runner=subprocess.run,
                 predictions_path=None, report_path=None, max_workers: int = 4) -> dict:
    """Produce a patch per stratified-subset instance, run the official swebench harness, and
    report the resolve-rate. Never raises; graceful-degrade. agent_fn/harness_runner injectable."""
    base = {"model": model, "axis": AXIS, "tool": "swebench_verified"}
    if not swebench_available():
        return {**base, "n": 0, "acc": None, "skipped": True,
                "note": "swebench not installed; pip install swebench + docker (see README)"}
    try:
        full = _load_verified(dataset, instances)
    except Exception as e:  # noqa: BLE001 — dataset/datasets unavailable
        return {**base, "n": 0, "acc": None, "skipped": True,
                "note": f"dataset load failed ({type(e).__name__}: {str(e)[:80]})"}
    subset = stratify(full, n, seed)
    params = params or {}
    preds = []
    for inst in subset:
        repo_dir = repo_provider(inst) if repo_provider else ""   # checkout is execution-phase
        try:
            patch = agent_fn(driver, model, inst, repo_dir, params)
        except Exception as e:  # noqa: BLE001 — one agent failure -> empty patch, continue
            patch = ""
        preds.append({"instance_id": inst["instance_id"], "model_name_or_path": model, "model_patch": patch})
    predictions_path = predictions_path or os.path.join(os.getcwd(), f"swebench_preds_{run_id}.jsonl")
    report_path = report_path or os.path.join(os.getcwd(), f"swebench_report_{run_id}.json")
    write_predictions(predictions_path, preds)
    cmd = [sys.executable, "-m", "swebench.harness.run_evaluation",
           "--dataset_name", dataset, "--predictions_path", predictions_path,
           "--run_id", run_id, "--max_workers", str(max_workers)]
    try:
        proc = harness_runner(cmd, capture_output=True, text=True)
    except Exception as e:  # noqa: BLE001 — docker/harness launch failure; degrade
        return {**base, "n": len(subset), "acc": None, "skipped": False,
                "note": f"swebench harness raised: {type(e).__name__}: {str(e)[:120]}"}
    if getattr(proc, "returncode", 1) != 0:
        return {**base, "n": len(subset), "acc": None, "skipped": False,
                "note": f"swebench harness rc={getattr(proc, 'returncode', 1)}: {(getattr(proc, 'stderr', '') or '')[:160]}"}
    try:
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return {**base, "n": len(subset), "acc": None, "skipped": False,
                "note": f"could not read swebench report at {report_path} ({e})"}
    parsed = parse_report(report)
    return {**base, "n": len(subset), "resolved": parsed["resolved"], "total": parsed["total"],
            "resolve_rate": parsed["resolve_rate"], "acc": parsed["resolve_rate"],
            "subset_ids": [i["instance_id"] for i in subset], "skipped": False}
