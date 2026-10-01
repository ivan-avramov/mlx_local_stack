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
import time
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
    interrupted -- OR (5th cold review P13) the process was killed (SIGKILL, power loss) in the
    narrow window AFTER `f.write(json.dumps(row) + "\\n")` fully landed on disk but BEFORE... no --
    actually the gap this guards is simpler and real: a write that completed the JSON body but was
    cut off before its own trailing `\\n` could be flushed. That dangling content may be a
    COMPLETE, valid JSON object missing only its newline -- deleting a fully-written row just
    because the newline didn't make it would silently drop real data. Only a content that is NOT
    valid JSON on its own is an actually-torn (truly unrecoverable) fragment; truncate only that."""
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
        dangling = content[last_nl + 1:]
        try:
            json.loads(dangling.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            f.seek(0)
            f.truncate(last_nl + 1 if last_nl >= 0 else 0)
        else:
            # P13: a complete row, just missing its trailing newline -- preserve it, add the
            # newline so the NEXT append starts a clean new line.
            f.seek(0, os.SEEK_END)
            f.write(b"\n")


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


# --------------------------------------------------------------------------- transcripts
def transcripts_dir_for(args) -> Path:
    """`--transcripts-dir`, else `<STACK_WORKDIR>/m54/transcripts/<model>/` (quality-inspection
    artifacts; genuinely optional output, so STACK_WORKDIR is REQUIRED when not given explicitly
    rather than silently falling back to a cache dir -- AGENTS.md: no filesystem pollution outside
    STACK_WORKDIR)."""
    if args.transcripts_dir:
        return Path(args.transcripts_dir)
    return paths.stack_workdir(required=True) / "m54" / "transcripts" / args.model


def write_transcript(transcripts_dir: Path, task: dict, model: str, turns: list, row: dict) -> Path:
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    doc = {"id": task["id"], "model": model, "system": AB.SYSTEM_PROMPT,
          "task_description": task.get("description", ""), "turns": turns,
          "submitted_via": row.get("submitted_via"), "answer": row.get("answer"),
          "gold_prepare": row.get("gold_prepare"), "gold_live": row.get("gold_live"),
          "passed": row.get("passed"), "outcome": row.get("outcome")}
    path = transcripts_dir / f"{task['id']}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


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


# 4th cold review G3 + 5th cold review P7: a --resume must refuse rather than silently continue a
# run under DIFFERENT conditions than the one that produced the existing rows -- any of these
# changing invalidates apples-to-apples comparison within the same rows file.
RESUME_IDENTITY_KEYS = ("model", "round_limit", "exec_timeout_s", "deadline_s", "sampling_profile",
                       "image_ids", "corpus_sha256", "exclusions_sha256")


def _check_resume_identity(mp: Path, current: dict) -> str | None:
    """None if `mp` doesn't exist yet (nothing to compare against) or its `runtime` block matches
    `current` on every key in RESUME_IDENTITY_KEYS; else a refusal reason. P7: a manifest that
    already recorded a `served_config_drift` from a PRIOR exit is refused outright -- that prior
    run's results are suspect and must not be silently built upon."""
    if not mp.exists():
        return None
    try:
        prev_doc = json.loads(mp.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- _load_previous_manifest already surfaces this
        return None
    if prev_doc.get("served_config_drift"):
        return (f"{mp} recorded a served_config_drift from a previous exit -- that run's results "
               "are suspect; investigate before resuming (or start a fresh --out)")
    prev_runtime = prev_doc.get("runtime") or {}
    for key in RESUME_IDENTITY_KEYS:
        if key not in prev_runtime:
            continue
        if prev_runtime[key] != current.get(key):
            return (f"resume refused: {key} changed since the previous manifest ({mp}): "
                   f"{prev_runtime[key]!r} -> {current.get(key)!r}")
    return None


def _stamp_manifest_exit(mp: Path, router: dict, base_url: str) -> None:
    """P7: best-effort FORENSIC C106 exit stamp for an EXCEPTIONAL exit (TransportFailure,
    ContainerCleanupError, KeyboardInterrupt, a SIGTERM SystemExit). Never raises and never masks
    the original exception -- call ONLY from an `except BaseException: ...; raise` handler."""
    if not mp.exists():
        return
    try:
        doc = json.loads(mp.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return
    try:
        doc["router_exit"] = provenance.assert_served_config_unchanged(router, base_url)
    except provenance.ServedConfigError as e:
        doc["served_config_drift"] = {"entry_sha256": router.get("config_sha256"),
                                      "exit_sha256": _exit_sha(base_url), "error": str(e)}
    except Exception:  # noqa: BLE001 -- forensic only
        return
    try:
        mp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _write_manifest(mp: Path, model: str, *, profile: str, runtime: dict, router: dict,
                    history: list, segments: list | None = None) -> None:
    # cold-review F15: the manifest must record the PROFILE ACTUALLY USED (which may be an
    # --allow-profile override), not a hardcoded "deployed".
    man = provenance.gather(model, profile=profile, runtime=runtime, router=router)
    if history:
        man["router_history"] = history
    # P7: segments accumulate across resumes (one entry per process start) -- the caller is
    # responsible for reading any PRIOR segments off the existing manifest and passing the full
    # list back in; this function never reads the old file itself (it may legitimately not exist).
    if segments:
        man["segments"] = segments
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
    # 5th cold review P11: AGENTS.md -- acc_strict@<budget> (passed AND converged, DNF counts in
    # the denominator) is the RANKING KEY; conv_rate and nonconv_kinds are reported alongside it,
    # never folded into a composite. All three share the SAME denominator as `acc` (graded_n --
    # setup/infra failures are excluded exactly as they are from `acc`).
    converged_n = sum(1 for r in graded_rows if r.get("converged") is True)
    passed_and_converged = sum(1 for r in graded_rows
                               if r.get("passed") is True and r.get("converged") is True)
    nonconv_kind_counts: dict = {}
    for r in graded_rows:
        for k in (r.get("nonconv_kinds") or []):
            nonconv_kind_counts[k] = nonconv_kind_counts.get(k, 0) + 1
    return {
        # cold-review F1: setup/evaluate infra failures are EXCLUDED from the acc denominator and
        # reported separately, rather than silently counted as ordinary fails.
        "n": n, "setup_error_count": len(setup_error_rows), "graded_n": graded_n,
        "passed": passed, "acc": round(passed / graded_n, 3) if graded_n else None,
        "acc_strict": round(passed_and_converged / graded_n, 3) if graded_n else None,
        "conv_rate": round(converged_n / graded_n, 3) if graded_n else None,
        "nonconv_kind_counts": nonconv_kind_counts,
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
        # R5/D2-rule-v2 (operator 2026-09-30): a row where the D2-prepare-time gold and the gold
        # observed live at grading disagree -- only meaningful when BOTH are known (a gold slot
        # exists AND grading actually ran it). RENAMED from gold_drift: for a randomized-init task
        # ($RANDOM/shuf) this is EXPECTED, not necessarily an error -- the D2 probe already excludes
        # tasks whose example disagrees across two in-container runs (gold_mismatch), so any row
        # reaching here with a cached gold_prepare came from a task that agreed at prepare time;
        # live disagreement still means the environment realized differently this time.
        "gold_prepare_differs_count": sum(1 for r in _gold_prepare_differs_rows(rows)),
        "gold_prepare_differs_ids": [r["id"] for r in _gold_prepare_differs_rows(rows)],
    }


def _gold_prepare_differs_rows(rows: list) -> list:
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


# --------------------------------------------------------------------------- timeout derivation (F8/P14)
def _derive_llm_timeout(model: str, thinking_budget, explicit):
    """Returns (timeout_s, source, msg, derivation: dict).

    5th cold review P14: `budget_timeout.derive_timeout`'s 7200s CEILING_S exists for the
    convergence benchmark's own (differently justified: "a pathological draw shouldn't run
    unbounded") axis. An AgentBench OS episode calls the model MANY times across up to
    `--round-limit` turns, each needing a per-turn timeout actually sized to THIS model's thinking
    budget and measured floor decode rate -- silently capping it at that shared ceiling would
    truncate every turn on a large-budget/slow-decode model long before it could legitimately hit
    its own budget, every single turn, which is exactly the "client gives up before the model does"
    defect `budget_timeout.py` itself documents (just at a different scale). So the value here is
    computed UNCAPPED; `observable=False` (no measured rate, no budget, or the value is simply
    unknown) is recorded and the caller refuses to start rather than silently falling back to a
    ceiling whose only honest meaning is "uninterpretable", unless `--llm-timeout` was given
    explicitly."""
    if explicit:
        derivation = {"thinking_budget": thinking_budget, "floor_decode_tps": None,
                     "safety_headroom": None, "source": "explicit", "observable": True,
                     "reason": "explicit --llm-timeout override"}
        return explicit, "explicit", f"{explicit:.0f}s (EXPLICIT --llm-timeout)", derivation
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
    if not thinking_budget or not tps or tps <= 0:
        timeout_s = budget_timeout.CEILING_S
        observable = False
        reason = ("no measured decode rate or no thinking budget -- a per-turn timeout cannot be "
                 "SIZED (not just 'cannot be interpreted as a budget hit')")
    else:
        budget_time_s = thinking_budget / tps
        timeout_s = max(budget_timeout.FLOOR_S, budget_time_s * budget_timeout.SAFETY)
        observable = True
        reason = (f"budget {thinking_budget} tok at {tps:.1f} tok/s floor = "
                 f"{budget_time_s / 60:.1f} min; x{budget_timeout.SAFETY} headroom, UNCAPPED "
                 "(P14: no 7200s ceiling for this per-turn axis)")
    derivation = {"thinking_budget": thinking_budget, "floor_decode_tps": tps,
                 "safety_headroom": budget_timeout.SAFETY, "source": source,
                 "observable": observable, "reason": reason}
    return (round(timeout_s, 1), source,
           f"{timeout_s:.0f}s (DERIVED, timeout_source={source}) -- {reason}", derivation)


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
    # P10: the artifact fingerprints the vendored scripts too, and carries a full per-task
    # disposition map (match/kept/excluded:<reason>) so `validate_exclusions_artifact` can refuse
    # on ANY missing corpus id, not just a drifted sha.
    scripts_sha = AB.scripts_root_sha256(args.scripts_root)
    disposition = AB.build_disposition_map(tasks, args.scripts_root, golds, exclusions)
    artifact_path = AB.exclusions_artifact_path(corpus_path)
    AB.write_exclusions_artifact(artifact_path, corpus_sha256=_sha256_file(corpus_path),
                                 image_ids=image_ids, golds=golds, exclusions=exclusions,
                                 complete=True, manual_exclusions_sha256=manual_sha,
                                 scripts_root=str(args.scripts_root), scripts_sha256=scripts_sha,
                                 disposition=disposition)
    gold_mismatch_n = sum(1 for e in exclusions if e.get("reason") == "gold_mismatch")
    print(f"[agentbench_os] D2 prepare: {len(tasks)} task(s), {len(exclusions)} excluded "
         f"({len(manual)} manual, {gold_mismatch_n} gold_mismatch -- EXPECTED for randomized-init "
         f"tasks, see docs), {len(golds)} gold(s) cached")
    print(f"[agentbench_os] wrote {artifact_path}")
    return 0


# --------------------------------------------------------------------------- SIGTERM (F12/N12)
def _make_sigterm_handler(current: dict, runner):
    def _handler(signum, frame):
        name = current.get("container")
        if name:
            # P16: a SIGTERM teardown reports an unverified removal too -- we're about to exit
            # regardless, but the next operator to look at this box needs to know whether a
            # container was left behind.
            verified = AB.remove_container(name, runner, verify=True)
            if not verified:
                print(f"[agentbench_os] WARNING: container {name} removal UNVERIFIED on SIGTERM "
                     "teardown -- check `docker ps -a` before starting another run",
                     file=sys.stderr, flush=True)
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
    all_tasks = AB.load_corpus(corpus_path)
    artifact_path = AB.exclusions_artifact_path(corpus_path)
    excl_doc = AB.read_exclusions_artifact(artifact_path)
    manual_path = AB.manual_exclusions_path(corpus_path)
    manual_sha = _sha256_file(manual_path) if manual_path.exists() else None
    refusal = AB.validate_exclusions_artifact(
        excl_doc, corpus_sha256=_sha256_file(corpus_path), image_ids=image_ids,
        manual_exclusions_sha256=manual_sha, scripts_sha256=AB.scripts_root_sha256(args.scripts_root),
        all_task_ids=[t["id"] for t in all_tasks])
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

    # 4th cold review G4: --limit truncates the candidate list to its FIRST N -- the corpus is
    # ordered easy-first (see the "no job at n>=40 without a seeded pilot" rule), so combining it
    # with --pilot-seed would draw a random sample from an already-biased, already-truncated
    # subset, silently defeating the whole point of a seeded random pilot.
    if args.limit and args.pilot_seed is not None:
        print("[agentbench_os] REFUSED: --limit and --pilot-seed are mutually exclusive -- "
             "--limit truncates to the corpus's (easy-first) head, which would bias any pilot "
             "drawn from it.", file=sys.stderr, flush=True)
        return 2

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

    llm_timeout, timeout_source, timeout_msg, timeout_derivation = _derive_llm_timeout(
        args.model, params.get("thinking_budget"), args.llm_timeout)
    print(f"[agentbench_os] per-turn LLM timeout = {timeout_msg}")
    # P14: a per-turn timeout that cannot be SIZED (no measured rate, no budget) is not merely
    # imprecise -- it is uninterpretable, and AGENTS.md forbids silently running on a number that
    # is. Refuse rather than falling back to the shared ceiling, unless the operator overrode it.
    if not timeout_derivation["observable"] and not args.llm_timeout:
        print(f"[agentbench_os] REFUSED: cannot derive a per-turn LLM timeout "
             f"({timeout_derivation['reason']}) -- pass --llm-timeout explicitly to override.",
             file=sys.stderr, flush=True)
        return 2
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

    # 4th cold review G3 + 5th cold review P7: a resume (done_ids nonzero) must refuse rather than
    # silently continue under conditions that changed since the manifest it's building on.
    runtime_identity = {"model": args.model, "round_limit": args.round_limit,
                        "exec_timeout_s": args.exec_timeout, "deadline_s": round(deadline_s, 1),
                        "sampling_profile": args.sampling_profile, "image_ids": image_ids,
                        "corpus_sha256": _sha256_file(corpus_path),
                        "exclusions_sha256": _sha256_file(artifact_path)}
    if done_ids:
        identity_refusal = _check_resume_identity(mp, runtime_identity)
        if identity_refusal:
            print(f"[agentbench_os] REFUSED: {identity_refusal}", file=sys.stderr, flush=True)
            return 2

    AB.sweep_stale_containers(AB.GENERATE_CONTAINER_PREFIX, runner)

    tdir = transcripts_dir_for(args)
    prev_segments = []
    if mp.exists():
        try:
            prev_segments = json.loads(mp.read_text(encoding="utf-8")).get("segments") or []
        except Exception:  # noqa: BLE001
            prev_segments = []
    segments = prev_segments + [{"started_at": time.time(), "router_pid": router.get("pid"),
                                 "rows_before": len(done_ids)}]
    if todo:
        _write_manifest(mp, args.model, profile=args.sampling_profile,
                        runtime={"client": "run_agentbench_os", "bench": BENCH_NAME, "tune": TUNE,
                                 "corpus": str(corpus_path), "exclusions_path": str(artifact_path),
                                 "limit": args.limit, "llm_timeout_s": round(llm_timeout, 1),
                                 "timeout_source": timeout_source,
                                 "timeout_derivation": timeout_derivation,
                                 "n_todo": len(todo), "n_done_before": len(done_ids),
                                 "n_excluded": len(exclusions),
                                 "pilot_seed": args.pilot_seed, "pilot_n": args.pilot_n,
                                 "pilot_ids": pilot_ids, "transcripts_dir": str(tdir),
                                 **runtime_identity},
                        router=router, history=history, segments=segments)
    base_driver = driver_mod.MlxServeDriver()
    current = {"container": None}
    old_handler = signal.signal(signal.SIGTERM, _make_sigterm_handler(current, runner))
    try:
        try:
            for i, task in enumerate(todo):
                print(f"[agentbench_os] {args.model} {task['id']} ({i + 1}/{len(todo)})", flush=True)
                current["container"] = AB.container_name(AB.GENERATE_CONTAINER_PREFIX, task["id"])
                item_params = {**params, "seed": rowschema.sample_seed(task["id"], 0)}
                # TransportFailure propagates OUT of this loop uncaught (cold-review F1): a
                # transport failure ESCALATES, it is never graded, and no row -- and so no
                # transcript either -- is written for the in-flight task.
                row = AB.run_task(args.model, task, args.scripts_root, base_driver, item_params,
                                  container_prefix=AB.GENERATE_CONTAINER_PREFIX,
                                  exec_timeout=args.exec_timeout, llm_timeout=llm_timeout,
                                  max_turns=args.round_limit, deadline_s=deadline_s,
                                  context_limit=context_limit, gold_prepare=golds.get(task["id"]),
                                  runner=runner)
                current["container"] = None
                turns = row.pop("_transcript_turns", [])
                transcript_path = write_transcript(tdir, task, args.model, turns, row)
                row["transcript_path"] = str(transcript_path)
                append_row(out, row)
                print(f"[agentbench_os]   -> passed={row['passed']} outcome={row['outcome']} "
                     f"turns={row['turns']} setup_error={row['setup_error']}", flush=True)
                # 5th cold review P16: the row is now durably written -- ONLY NOW does an unverified
                # container removal stop the run (never before the row itself is safe).
                if row.get("container_removed_verified") is False:
                    raise AB.ContainerCleanupError(
                        f"container for task {task['id']} was not verifiably removed (docker rm -f "
                        "failed or `docker ps -a` still shows it) -- stopping rather than creating "
                        "another container on a box that may be silently accumulating live ones")
        finally:
            signal.signal(signal.SIGTERM, old_handler)
    except BaseException:
        # P7: an exceptional exit (TransportFailure, ContainerCleanupError, KeyboardInterrupt, or
        # the SystemExit our own SIGTERM handler raises) still gets a best-effort C106 exit stamp,
        # WITHOUT masking the original exception -- re-raise unconditionally.
        _stamp_manifest_exit(mp, router, client.BASE)
        raise

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
    ap.add_argument("--transcripts-dir", default=None,
                    help="per-task transcript JSON directory (quality inspection). Default: "
                         "<STACK_WORKDIR>/m54/transcripts/<model>/")
    return ap


def main(argv=None) -> int:
    args = build_argparser().parse_args(argv)
    args.scripts_root = Path(args.scripts_root)
    out = (Path(args.out) if args.out
          else paths.default_results_root() / args.model / f"{BENCH_NAME}.{TUNE}.jsonl")
    # 5th cold review P19: --out and the transcripts dir are the only USER-STEERABLE write targets
    # here -- confine both to the repo or STACK_WORKDIR before anything is written.
    refusal = paths.confine_path(out, what="--out")
    if refusal:
        print(f"[agentbench_os] REFUSED: {refusal}", file=sys.stderr, flush=True)
        return 2
    if not args.prepare:
        tdir_refusal = paths.confine_path(transcripts_dir_for(args), what="--transcripts-dir")
        if tdir_refusal:
            print(f"[agentbench_os] REFUSED: {tdir_refusal}", file=sys.stderr, flush=True)
            return 2
    if args.prepare:
        return run_prepare(args, out)
    return run_generate(args, out)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 -- transport/dataset/registry failures ESCALATE
        print(f"[agentbench_os] FATAL: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
