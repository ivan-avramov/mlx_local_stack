#!/usr/bin/env python3
"""M54: AgentBench `os-std` probe (144-task THUDM/AgentBench corpus, Apache-2.0, pinned commit in
`benchmark/corpora/agentbench_os_v1.manifest.json`) against the mlx-serve router, with our own
tool loop (`bench.agent_loop.run_agent`) and one docker container per task.

Two modes:

  --prepare   D2 exclusion pass (C107, cold-review F6/F7): for every CHECK task (never `match`),
              run `evaluation.example.code` to completion in TWO fresh containers with TWO
              DIFFERENT answer placeholders and compare. No model calls. Writes a CORPUS-level
              artifact, `<corpus stem>.exclusions.json` (sibling of the corpus jsonl, not per
              model/run) with the corpus sha256, the three `local-os` image ids, per-task golds,
              exclusions with reasons, and `complete: true` (only set for a run over the WHOLE
              corpus -- `--limit` is refused with `--prepare`). Generate mode below refuses to
              start unless this file exists, is `complete`, and both the corpus sha256 and image
              ids still match what is live.

  (default)   Generate mode: one container per (non-excluded) task, `bash_action`/`finish_action`/
              `answer_action` over the router, grade inside the container, `docker rm -f`. M50/C106
              served-config discipline (same pattern as `vision_gate.py`): refuse before the first
              request, refuse to declare the run complete if the served registry changed underneath
              it. A `driver.complete` transport failure (HTTP error/timeout/connection error)
              ESCALATES -- the run aborts nonzero with the task id in the message, no row is
              written for that task (AGENTS.md: transport failures are NEVER graded).

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
import signal
import statistics
import subprocess
import sys
from pathlib import Path

from . import agentbench_adapter as AB
from . import budget_timeout, driver as driver_mod, generate, model_params, paths, provenance, rowschema

BENCH_NAME = "agentbench_os"
TUNE = "v1"
DEFAULT_CORPUS = paths.repo_root() / "benchmark" / "corpora" / "agentbench_os_v1.jsonl"
DEFAULT_SCRIPTS_ROOT = paths.repo_root() / "benchmark" / "corpora" / "agentbench_os_v1" / "scripts"
ALLOWED_PROFILES = ("deployed",)
# Fallback decode-rate evidence (cold-review F8) when this axis has no rows of its own yet (a
# fresh model/box). Named explicitly in the manifest (`timeout_source`) so a reader can tell a
# cold-start estimate from one measured on this very axis.
FALLBACK_RATE_BENCHES = ("math500", "convergence")
DEADLINE_MULTIPLIER = 8.0


# --------------------------------------------------------------------------- I/O helpers
class TornRowError(RuntimeError):
    """A malformed row was found somewhere OTHER than the final line of a rows file -- that can
    only mean real corruption (not an interrupted write), so it escalates rather than being
    silently dropped (cold-review F3)."""


def read_rows(out_path: Path) -> list:
    """Every complete, id-bearing row in `out_path`. Tolerates a TORN LAST LINE (the shape an
    interrupted write leaves: `append_row` truncated mid-`json.dumps`) by logging and ignoring
    only that one; any OTHER malformed line is real corruption and escalates (cold-review F3).
    A row with no `id` is skipped (can never be matched for resume/grading)."""
    if not out_path.exists():
        return []
    lines = out_path.read_text(encoding="utf-8").splitlines()
    rows = []
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                print(f"[agentbench_os] {out_path}: ignoring a torn final line (interrupted write)",
                     file=sys.stderr)
                continue
            raise TornRowError(f"{out_path}: malformed row at line {i + 1} (not the last line) -- "
                               "this is not an interrupted write; investigate before resuming")
        if "id" not in row:
            continue
        rows.append(row)
    return rows


def _truncate_torn_tail(path: Path) -> None:
    """cold-review N6: if `path` exists and its last byte is not `\\n`, an earlier write was
    interrupted mid-row. Truncate back to the last complete `\\n` (the torn row is already
    unrecoverable -- `read_rows` would have discarded it anyway) so the NEXT append starts a clean
    new line rather than concatenating onto a half-written one."""
    if not path.exists():
        return
    with open(path, "rb+") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        if size == 0:
            return
        f.seek(size - 1)
        if f.read(1) == b"\n":
            return
        f.seek(0)
        content = f.read()
        last_nl = content.rfind(b"\n")
        f.seek(0)
        f.truncate(last_nl + 1 if last_nl >= 0 else 0)


def append_row(path: Path, row: dict) -> None:
    _truncate_torn_tail(path)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
        f.flush()


def _stem(out: Path) -> str:
    return out.name[:-len(".jsonl")] if out.name.endswith(".jsonl") else out.name


def summary_path_for(out: Path) -> Path:
    return out.parent / f"{_stem(out)}.summary.json"


def manifest_path_for(out: Path) -> Path:
    return out.parent / f"{_stem(out)}.manifest.json"


def skipped_path_for(out: Path) -> Path:
    """cold-review F3: the degrade marker is its OWN file, never the rows file -- writing
    `{"skipped": true}` into `out` would corrupt a resumable rows file and silently discard
    whatever was already there."""
    return out.parent / f"{_stem(out)}.skipped.json"


def _sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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


def _write_manifest(mp: Path, model: str, *, profile: str, runtime: dict, router: dict,
                    history: list) -> None:
    # cold-review F15: the manifest must record the PROFILE ACTUALLY USED (which may be an
    # --allow-profile override), not a hardcoded "deployed".
    man = provenance.gather(model, profile=profile, runtime=runtime, router=router)
    if history:
        man["router_history"] = history
    mp.parent.mkdir(parents=True, exist_ok=True)
    tmp = mp.with_suffix(mp.suffix + ".tmp")
    tmp.write_text(json.dumps(man, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, mp)


# --------------------------------------------------------------------------- summary
def summarize(rows: list) -> dict:
    n = len(rows)
    setup_error_rows = [r for r in rows if r.get("setup_error")]
    graded_rows = [r for r in rows if not r.get("setup_error")]
    graded_n = len(graded_rows)
    passed = sum(1 for r in graded_rows if r.get("passed") is True)
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
        # cold-review F1: setup/evaluate infra failures are EXCLUDED from the acc denominator and
        # reported separately, rather than silently counted as ordinary fails.
        "n": n, "setup_error_count": len(setup_error_rows), "graded_n": graded_n,
        "passed": passed, "acc": round(passed / graded_n, 3) if graded_n else None,
        "outcome_counts": outcome_counts,
        "label_counts_diagnostic": label_counts,
        "wall_s_mean": round(statistics.mean(walls), 1) if walls else None,
        "wall_s_max": round(max(walls), 1) if walls else None,
        "completion_tokens_mean": round(statistics.mean(toks), 1) if toks else None,
        "completion_tokens_max": round(max(toks), 1) if toks else None,
        "fail_ids": [r["id"] for r in graded_rows if r.get("passed") is not True],
        "setup_error_ids": [r["id"] for r in setup_error_rows],
        # cold-review N12: distinct mechanisms, counted explicitly rather than only buried inside
        # outcome_counts/setup_error_count.
        "exec_timeout_count": sum(1 for r in rows if r.get("exec_timeout")),
        "shell_died_count": sum(1 for r in rows if r.get("shell_died")),
        # R5: a row where the D2-prepare-time gold and the gold observed live at grading disagree
        # -- only meaningful when BOTH are known (a gold slot exists AND grading actually ran it).
        "gold_drift_count": sum(1 for r in _gold_drift_rows(rows)),
        "gold_drift_ids": [r["id"] for r in _gold_drift_rows(rows)],
    }


def _gold_drift_rows(rows: list) -> list:
    return [r for r in rows if r.get("gold_prepare") is not None and r.get("gold_live") is not None
           and r["gold_prepare"] != r["gold_live"]]


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
    sp = skipped_path_for(out)
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps({"skipped": True, "note": note}) + "\n", encoding="utf-8")
    print(f"[agentbench_os] SKIPPED: {note}", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- timeout derivation (F8)
def _derive_llm_timeout(model: str, thinking_budget, explicit):
    if explicit:
        return explicit, "explicit", f"{explicit:.0f}s (EXPLICIT --llm-timeout)"
    own_rows = generate.rows_for_rate(model, BENCH_NAME)
    tps = budget_timeout.floor_decode_tps(own_rows)
    source = BENCH_NAME
    if tps is None:
        # cold-review N11: name only the benches that actually contributed rows, not every
        # configured fallback -- "fallback:math500+convergence" would be a lie if convergence had
        # zero rows for this model and math500 alone produced the estimate.
        fb_rows = []
        contributors = []
        for b in FALLBACK_RATE_BENCHES:
            try:
                rows = generate.rows_for_rate(model, b)
            except Exception:  # noqa: BLE001 -- a missing/unreadable bench must not block the run
                rows = []
            if rows:
                contributors.append(b)
            fb_rows += rows
        tps = budget_timeout.floor_decode_tps(fb_rows)
        source = f"fallback:{'+'.join(contributors)}" if tps is not None else "none"
    d = budget_timeout.derive_timeout(thinking_budget, tps)
    return d["timeout_s"], source, f"{d['timeout_s']:.0f}s (DERIVED, timeout_source={source}) -- {d['reason']}"


# --------------------------------------------------------------------------- prepare (D2, F6/F7/F10)
def run_prepare(args, out: Path) -> int:
    runner = subprocess.run
    corpus_path = Path(args.corpus)
    reason = _degrade_reason(corpus_path, runner)
    if reason:
        return _write_skipped(out, reason)

    if args.limit:
        print("[agentbench_os] REFUSED: --prepare does not accept --limit -- the exclusion "
             "artifact's `complete: true` means the WHOLE corpus, never a subset.",
             file=sys.stderr, flush=True)
        return 2

    tasks = AB.load_corpus(corpus_path)
    image_ids = AB.current_image_ids(runner=runner)
    manual_path = AB.manual_exclusions_path(corpus_path)
    manual = AB.load_manual_exclusions(manual_path)
    manual_sha = _sha256_file(manual_path) if manual_path.exists() else None
    # cold-review N12: prepare gets the same SIGTERM discipline as generate -- sweep whatever
    # prepare-prefixed container is still live rather than leaving it behind.
    old_handler = signal.signal(signal.SIGTERM, _make_sigterm_sweep_handler(AB.PREPARE_CONTAINER_PREFIX, runner))
    try:
        golds, exclusions = AB.prepare_exclusions(tasks, args.scripts_root, runner,
                                                  timeout=args.exec_timeout,
                                                  prefix=AB.PREPARE_CONTAINER_PREFIX, manual=manual)
    finally:
        signal.signal(signal.SIGTERM, old_handler)
    artifact_path = AB.exclusions_artifact_path(corpus_path)
    AB.write_exclusions_artifact(artifact_path, corpus_sha256=_sha256_file(corpus_path),
                                 image_ids=image_ids, golds=golds, exclusions=exclusions,
                                 complete=True, manual_exclusions_sha256=manual_sha)
    print(f"[agentbench_os] D2 prepare: {len(tasks)} task(s), {len(exclusions)} excluded "
         f"({len(manual)} manual), {len(golds)} gold(s) cached")
    print(f"[agentbench_os] wrote {artifact_path}")
    return 0


# --------------------------------------------------------------------------- SIGTERM (F12/N12)
def _make_sigterm_handler(current: dict, runner):
    def _handler(signum, frame):
        name = current.get("container")
        if name:
            AB.remove_container(name, runner)
        sys.exit(143)
    return _handler


def _make_sigterm_sweep_handler(prefix: str, runner):
    """Prepare mode doesn't track a single in-flight container name the way generate does (the
    D2 probe creates/removes several in quick succession); sweep the whole prefix instead."""
    def _handler(signum, frame):
        AB.sweep_stale_containers(prefix, runner)
        sys.exit(143)
    return _handler


# --------------------------------------------------------------------------- generate
def run_generate(args, out: Path) -> int:
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

    image_ids = AB.current_image_ids(runner=runner)
    artifact_path = AB.exclusions_artifact_path(corpus_path)
    excl_doc = AB.read_exclusions_artifact(artifact_path)
    manual_path = AB.manual_exclusions_path(corpus_path)
    manual_sha = _sha256_file(manual_path) if manual_path.exists() else None
    refusal = AB.validate_exclusions_artifact(excl_doc, corpus_sha256=_sha256_file(corpus_path),
                                              image_ids=image_ids,
                                              manual_exclusions_sha256=manual_sha)
    if refusal:
        print(f"[agentbench_os] REFUSED: {artifact_path}: {refusal}", file=sys.stderr, flush=True)
        return 2
    exclusions = excl_doc.get("exclusions") or []
    golds = excl_doc.get("golds") or {}   # AC5: populated onto every row below

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

    llm_timeout, timeout_source, timeout_msg = _derive_llm_timeout(
        args.model, params.get("thinking_budget"), args.llm_timeout)
    print(f"[agentbench_os] per-turn LLM timeout = {timeout_msg}")
    if args.deadline_s:
        deadline_s = args.deadline_s
        deadline_reason = "EXPLICIT --deadline-s"
    else:
        # 3rd cold review R3 (architect ruling, AGENTS.md "the thinking budget is external
        # truncation, never tuned"): NO hardcoded cap here -- a slow model legitimately needs a
        # longer deadline, and silently capping it is exactly the kind of truncation AGENTS.md
        # forbids for a budget. 8x the per-turn timeout is the whole rule.
        deadline_s = llm_timeout * DEADLINE_MULTIPLIER
        deadline_reason = f"{DEADLINE_MULTIPLIER:.0f}x per-turn timeout"
    print(f"[agentbench_os] episode deadline = {deadline_s:.0f}s ({deadline_reason})")

    print(f"[agentbench_os] {args.model}: {len(todo)} item(s) to run "
         f"({len(done_ids)} already done, {len(exclusions)} excluded)")

    AB.sweep_stale_containers(AB.GENERATE_CONTAINER_PREFIX, runner)

    if todo:
        _write_manifest(mp, args.model, profile=args.sampling_profile,
                        runtime={"client": "run_agentbench_os", "bench": BENCH_NAME, "tune": TUNE,
                                 "corpus": str(corpus_path), "corpus_sha256": _sha256_file(corpus_path),
                                 "exclusions_path": str(artifact_path),
                                 "exclusions_sha256": _sha256_file(artifact_path),
                                 "image_ids": image_ids,
                                 "limit": args.limit, "llm_timeout_s": round(llm_timeout, 1),
                                 "timeout_source": timeout_source, "deadline_s": round(deadline_s, 1),
                                 "exec_timeout_s": args.exec_timeout, "round_limit": args.round_limit,
                                 "n_todo": len(todo), "n_done_before": len(done_ids),
                                 "n_excluded": len(exclusions),
                                 "pilot_seed": args.pilot_seed, "pilot_n": args.pilot_n,
                                 "pilot_ids": pilot_ids},
                        router=router, history=history)

    base_driver = driver_mod.MlxServeDriver()
    current = {"container": None}
    old_handler = signal.signal(signal.SIGTERM, _make_sigterm_handler(current, runner))
    try:
        for i, task in enumerate(todo):
            print(f"[agentbench_os] {args.model} {task['id']} ({i + 1}/{len(todo)})", flush=True)
            current["container"] = AB.container_name(AB.GENERATE_CONTAINER_PREFIX, task["id"])
            item_params = {**params, "seed": rowschema.sample_seed(task["id"], 0)}
            # TransportFailure propagates OUT of this loop uncaught (cold-review F1): a transport
            # failure ESCALATES, it is never graded, and no row is appended for the in-flight task.
            row = AB.run_task(args.model, task, args.scripts_root, base_driver, item_params,
                              container_prefix=AB.GENERATE_CONTAINER_PREFIX,
                              exec_timeout=args.exec_timeout, llm_timeout=llm_timeout,
                              max_turns=args.round_limit, deadline_s=deadline_s,
                              context_limit=context_limit, gold_prepare=golds.get(task["id"]),
                              runner=runner)
            current["container"] = None
            append_row(out, row)
            print(f"[agentbench_os]   -> passed={row['passed']} outcome={row['outcome']} "
                 f"turns={row['turns']} setup_error={row['setup_error']}", flush=True)
    finally:
        signal.signal(signal.SIGTERM, old_handler)

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
    # cold-review N12: a stale skip marker from an EARLIER degraded attempt at this --out would
    # otherwise sit next to a now-successful run's rows/summary, misleading a later reader.
    sp = skipped_path_for(out)
    if sp.exists():
        sp.unlink()
    print(f"[agentbench_os] RESULT {args.model}: {summary['passed']}/{summary['graded_n']} pass "
         f"acc={summary['acc']} setup_errors={summary['setup_error_count']}")
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
                    help="D2 exclusion pass only (AC2); no model calls; writes a CORPUS-level "
                         "artifact beside the corpus jsonl, not under --out")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--pilot-seed", type=int, default=None,
                    help="seeded random pilot subset over the non-excluded corpus")
    ap.add_argument("--pilot-n", type=int, default=5)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--sampling-profile", default="deployed")
    ap.add_argument("--allow-profile", action="store_true")
    ap.add_argument("--round-limit", type=int, default=AB.ROUND_LIMIT)
    ap.add_argument("--exec-timeout", type=float, default=AB.DEFAULT_EXEC_TIMEOUT_S,
                    help="per `docker exec`/persistent-shell command timeout, seconds")
    ap.add_argument("--llm-timeout", type=float, default=None,
                    help="per-turn LLM HTTP timeout, seconds. Default: DERIVED from this axis's "
                         "own rows' measured decode rate (falling back to math500/convergence "
                         "rows when this axis has none yet), never an SDK default")
    ap.add_argument("--deadline-s", type=float, default=None,
                    help=f"episode wall-clock deadline, seconds. Default: "
                         f"{DEADLINE_MULTIPLIER:.0f}x the per-turn LLM timeout (no hard cap -- "
                         "AGENTS.md: external truncation is never tuned down for convenience)")
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
