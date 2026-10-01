#!/usr/bin/env python3
"""M54: AgentBench `os-std` probe (144-task THUDM/AgentBench corpus, Apache-2.0, pinned commit in
`benchmark/corpora/agentbench_os_v1.manifest.json`) against the mlx-serve router, with our own
tool loop (`bench.agent_loop.run_agent`) and one docker container per task.

Two modes:

  --prepare   D2 exclusion pass (C107): for every CHECK task (never `match`), run
              `evaluation.example.code` to completion in TWO fresh containers and compare. No
              model calls. Writes `<out stem>.exclusions.json` and a gold cache under
              `$STACK_WORKDIR`. Must be run (and succeed) before the generate mode below will
              start at all.

  (default)   Generate mode: one container per (non-excluded) task, `bash_action`/`finish_action`/
              `answer_action` over the router, grade inside the container, `docker rm -f`. M50/C106
              served-config discipline (same pattern as `vision_gate.py`): refuse before the first
              request, refuse to declare the run complete if the served registry changed underneath
              it.

Usage:
  cd benchmark && uv run python -m bench.run_agentbench_os --model <full-registry-name> --prepare
  cd benchmark && uv run python -m bench.run_agentbench_os --model <full-registry-name> [--limit N]
      [--pilot-seed S --pilot-n 5] [--resume]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
from pathlib import Path

from . import agentbench_adapter as AB
from . import budget_timeout, driver as driver_mod, generate, model_params, paths, provenance, rowschema

BENCH_NAME = "agentbench_os"
TUNE = "v1"
DEFAULT_CORPUS = paths.repo_root() / "benchmark" / "corpora" / "agentbench_os_v1.jsonl"
DEFAULT_SCRIPTS_ROOT = paths.repo_root() / "benchmark" / "corpora" / "agentbench_os_v1" / "scripts"
CONTAINER_PREFIX = "agentbench-os"
ALLOWED_PROFILES = ("deployed",)


# --------------------------------------------------------------------------- I/O helpers
def read_rows(out_path: Path) -> list:
    if not out_path.exists():
        return []
    rows = []
    for line in out_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def append_row(path: Path, row: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
        f.flush()


def _stem(out: Path) -> str:
    return out.name[:-len(".jsonl")] if out.name.endswith(".jsonl") else out.name


def summary_path_for(out: Path) -> Path:
    return out.parent / f"{_stem(out)}.summary.json"


def manifest_path_for(out: Path) -> Path:
    return out.parent / f"{_stem(out)}.manifest.json"


def exclusions_path_for(out: Path) -> Path:
    return out.parent / f"{_stem(out)}.exclusions.json"


def _sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _gold_cache_path(corpus_sha256: str) -> Path:
    workdir = paths.stack_workdir(required=False)
    base = Path(workdir) if workdir else Path(
        os.path.expanduser("~/.cache/huggingface/mlx_local_stack_agentbench_os_golds"))
    return base / "agentbench_os_golds" / f"{corpus_sha256[:16]}.json"


def _load_previous_manifest(mp: Path, router: dict):
    """Same M50 shape as the other drivers (see vision_gate.py)."""
    if not mp.exists():
        return [], None
    try:
        prev_doc = json.loads(mp.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return [], f"M50 unreadable existing manifest {mp}: {e}"
    prev = prev_doc.get("router")
    history = list(prev_doc.get("router_history") or [])
    if isinstance(prev, dict) and prev.get("config") and prev.get("config") != router.get("config"):
        return history, (f"M50 {mp} was produced under served config {prev['config']!r}; this router "
                         f"serves {router.get('config')!r}. Use a different --out.")
    if isinstance(prev, dict) and prev.get("pid") is not None and prev.get("pid") != router.get("pid"):
        history.append(prev)
    return history, None


def _exit_sha(base: str):
    try:
        return provenance.assert_served_config(base).get("config_sha256")
    except Exception:  # noqa: BLE001
        return None


def _write_manifest(mp: Path, model: str, *, runtime: dict, router: dict, history: list) -> None:
    man = provenance.gather(model, profile="deployed", runtime=runtime, router=router)
    if history:
        man["router_history"] = history
    tmp = mp.with_suffix(mp.suffix + ".tmp")
    tmp.write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, mp)


# --------------------------------------------------------------------------- summary
def summarize(rows: list) -> dict:
    n = len(rows)
    passed = sum(1 for r in rows if r.get("passed") is True)
    outcome_counts: dict = {}
    label_counts: dict = {}
    for r in rows:
        outcome_counts[r.get("outcome")] = outcome_counts.get(r.get("outcome"), 0) + 1
        for lbl in (r.get("labels") or []):
            label_counts[lbl] = label_counts.get(lbl, 0) + 1
    walls = [r["wall_s"] for r in rows if isinstance(r.get("wall_s"), (int, float))]
    toks = [r["completion_tokens_total"] for r in rows
           if isinstance(r.get("completion_tokens_total"), (int, float))]
    return {
        "n": n, "passed": passed, "acc": round(passed / n, 3) if n else None,
        "outcome_counts": outcome_counts,
        "label_counts_diagnostic": label_counts,
        "wall_s_mean": round(statistics.mean(walls), 1) if walls else None,
        "wall_s_max": round(max(walls), 1) if walls else None,
        "completion_tokens_mean": round(statistics.mean(toks), 1) if toks else None,
        "completion_tokens_max": round(max(toks), 1) if toks else None,
        "fail_ids": [r["id"] for r in rows if r.get("passed") is not True],
    }


# --------------------------------------------------------------------------- degrade checks
def _degrade_reason(corpus_path: Path, runner) -> str | None:
    if not corpus_path.exists():
        return f"corpus not found: {corpus_path}"
    if not AB.docker_available(runner):
        return "docker is not available (not installed, not running, or unresponsive)"
    avail = AB.images_available(runner=runner)
    missing = [k for k, v in avail.items() if not v]
    if missing:
        return (f"local-os images missing: {missing} -- run scripts/build_agentbench_images.sh "
               f"first")
    return None


def _write_skipped(out: Path, note: str) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"skipped": True, "note": note}) + "\n", encoding="utf-8")
    print(f"[agentbench_os] SKIPPED: {note}", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- prepare (D2)
def run_prepare(args, out: Path) -> int:
    import subprocess
    corpus_path = Path(args.corpus)
    runner = subprocess.run
    reason = _degrade_reason(corpus_path, runner)
    if reason:
        return _write_skipped(out, reason)

    tasks = AB.load_corpus(corpus_path, args.limit)
    golds, exclusions = AB.prepare_exclusions(tasks, args.scripts_root, runner,
                                              timeout=args.exec_timeout,
                                              prefix=CONTAINER_PREFIX + "-prep")
    exclusions_path_for(out).write_text(json.dumps(exclusions, indent=2) + "\n", encoding="utf-8")
    gold_cache = _gold_cache_path(_sha256_file(corpus_path))
    gold_cache.parent.mkdir(parents=True, exist_ok=True)
    gold_cache.write_text(json.dumps(golds, indent=2) + "\n", encoding="utf-8")
    print(f"[agentbench_os] D2 prepare: {len(tasks)} task(s), {len(exclusions)} excluded, "
         f"{len(golds)} gold(s) cached")
    print(f"[agentbench_os] wrote {exclusions_path_for(out)}")
    print(f"[agentbench_os] wrote {gold_cache}")
    return 0


# --------------------------------------------------------------------------- generate
def run_generate(args, out: Path) -> int:
    import subprocess
    runner = subprocess.run

    if args.url:
        from . import client
        client.BASE = args.url
    from . import client
    try:  # M50: refuse before anything is read or requested
        router = provenance.assert_served_config(client.BASE)
    except RuntimeError as e:
        print(f"[agentbench_os] REFUSED: {e}", file=sys.stderr, flush=True)
        return 2

    corpus_path = Path(args.corpus)
    reason = _degrade_reason(corpus_path, runner)
    if reason:
        return _write_skipped(out, reason)

    excl_path = exclusions_path_for(out)
    if not excl_path.exists():
        print(f"[agentbench_os] REFUSED: {excl_path} does not exist -- run --prepare first "
             f"(D2 exclusion pass, AC2). Generate mode never starts without it.",
             file=sys.stderr, flush=True)
        return 2
    exclusions = json.loads(excl_path.read_text(encoding="utf-8"))

    if args.sampling_profile not in ALLOWED_PROFILES and not args.allow_profile:
        print(f"[agentbench_os] REFUSED: --sampling-profile {args.sampling_profile!r} is not "
             f"{ALLOWED_PROFILES}; pass --allow-profile to override.", file=sys.stderr, flush=True)
        return 2

    out.parent.mkdir(parents=True, exist_ok=True)
    existing = read_rows(out)
    done_ids = {r["id"] for r in existing}
    if done_ids and not args.resume:
        print(f"[agentbench_os] {out} already has {len(done_ids)} row(s); pass --resume to "
             "continue, or use a different --out", file=sys.stderr)
        return 2

    mp = manifest_path_for(out)
    history, refusal = _load_previous_manifest(mp, router)
    if refusal:
        print(f"[agentbench_os] REFUSED: {refusal}", file=sys.stderr, flush=True)
        return 2

    all_tasks = AB.load_corpus(corpus_path)
    candidates = AB.apply_exclusions(all_tasks, exclusions)
    if args.limit:
        candidates = candidates[:args.limit]
    pilot_ids = None
    if args.pilot_seed is not None:
        pilot_ids = AB.pilot_draw([t["id"] for t in candidates], args.pilot_seed, args.pilot_n)
        wanted = set(pilot_ids)
        candidates = [t for t in candidates if t["id"] in wanted]

    todo = [t for t in candidates if t["id"] not in done_ids] if args.resume else candidates

    params = model_params.params_for(args.model, profile=args.sampling_profile)
    context_limit = model_params.registry_context_limit(args.model)

    if args.llm_timeout:
        llm_timeout = args.llm_timeout
        print(f"[agentbench_os] per-turn LLM timeout = {llm_timeout:.0f}s (EXPLICIT --llm-timeout)")
    else:
        rate_rows = generate.rows_for_rate(args.model, BENCH_NAME)
        tps = budget_timeout.floor_decode_tps(rate_rows)
        d = budget_timeout.derive_timeout(params.get("thinking_budget"), tps)
        llm_timeout = d["timeout_s"]
        print(f"[agentbench_os] per-turn LLM timeout = {llm_timeout:.0f}s (DERIVED) -- {d['reason']}")

    print(f"[agentbench_os] {args.model}: {len(todo)} item(s) to run "
         f"({len(done_ids)} already done, {len(exclusions)} excluded)")

    AB.sweep_stale_containers(CONTAINER_PREFIX, runner)

    if todo:
        _write_manifest(mp, args.model,
                        runtime={"client": "run_agentbench_os", "bench": BENCH_NAME, "tune": TUNE,
                                 "corpus": str(corpus_path), "corpus_sha256": _sha256_file(corpus_path),
                                 "limit": args.limit, "llm_timeout_s": round(llm_timeout, 1),
                                 "exec_timeout_s": args.exec_timeout, "round_limit": args.round_limit,
                                 "n_todo": len(todo), "n_done_before": len(done_ids),
                                 "n_excluded": len(exclusions),
                                 "pilot_seed": args.pilot_seed, "pilot_n": args.pilot_n,
                                 "pilot_ids": pilot_ids},
                        router=router, history=history)

    base_driver = driver_mod.MlxServeDriver()
    for i, task in enumerate(todo):
        print(f"[agentbench_os] {args.model} {task['id']} ({i + 1}/{len(todo)})", flush=True)
        item_params = {**params, "seed": rowschema.sample_seed(task["id"], 0)}
        row = AB.run_task(args.model, task, args.scripts_root, base_driver, item_params,
                          container_prefix=CONTAINER_PREFIX, exec_timeout=args.exec_timeout,
                          llm_timeout=llm_timeout, max_turns=args.round_limit,
                          context_limit=context_limit, runner=runner)
        append_row(out, row)
        print(f"[agentbench_os]   -> passed={row['passed']} outcome={row['outcome']} "
             f"turns={row['turns']}", flush=True)

    try:
        exit_blk = provenance.assert_served_config_unchanged(router, client.BASE)
    except provenance.ServedConfigError as e:
        if mp.exists():
            doc = json.loads(mp.read_text(encoding="utf-8"))
            doc["served_config_drift"] = {"entry_sha256": router.get("config_sha256"),
                                          "exit_sha256": _exit_sha(client.BASE), "error": str(e)}
            mp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        print(f"[agentbench_os] REFUSED: {e}", file=sys.stderr, flush=True)
        return 2
    if mp.exists():
        doc = json.loads(mp.read_text(encoding="utf-8")); doc["router_exit"] = exit_blk
        mp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    summary = summarize(read_rows(out))
    summary["router"] = router
    summary["router_exit"] = exit_blk
    summary_path_for(out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"[agentbench_os] RESULT {args.model}: {summary['passed']}/{summary['n']} pass "
         f"acc={summary['acc']}")
    print(f"[agentbench_os] wrote {out}")
    print(f"[agentbench_os] wrote {summary_path_for(out)}")
    return 0


# --------------------------------------------------------------------------- CLI
def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="full registry name (main_models.yaml)")
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    ap.add_argument("--scripts-root", default=str(DEFAULT_SCRIPTS_ROOT))
    ap.add_argument("--out", default=None,
                    help="default: <results_root>/<model>/agentbench_os.v1.jsonl")
    ap.add_argument("--prepare", action="store_true",
                    help="D2 exclusion pass only (AC2); no model calls")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--pilot-seed", type=int, default=None,
                    help="seeded random pilot subset over the non-excluded corpus")
    ap.add_argument("--pilot-n", type=int, default=5)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--sampling-profile", default="deployed")
    ap.add_argument("--allow-profile", action="store_true")
    ap.add_argument("--round-limit", type=int, default=AB.ROUND_LIMIT)
    ap.add_argument("--exec-timeout", type=float, default=AB.DEFAULT_EXEC_TIMEOUT_S,
                    help="per `docker exec` command timeout, seconds")
    ap.add_argument("--llm-timeout", type=float, default=None,
                    help="per-turn LLM HTTP timeout, seconds. Default: DERIVED from the model's "
                         "measured decode rate + thinking budget (never an SDK default)")
    return ap


def main(argv=None) -> int:
    args = build_argparser().parse_args(argv)
    args.scripts_root = Path(args.scripts_root)
    out = (Path(args.out) if args.out
          else paths.default_results_root() / args.model / f"{BENCH_NAME}.{TUNE}.jsonl")
    if args.prepare:
        return run_prepare(args, out)
    return run_generate(args, out)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 -- transport/dataset/registry failures ESCALATE
        print(f"[agentbench_os] FATAL: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
