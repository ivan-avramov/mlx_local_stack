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
    STACK_WORKDIR). This is the BASE path used for the early --transcripts-dir confinement check
    in main() (confinement of the base transitively covers any run-id subdirectory nested under
    it -- see `run_transcripts_dir`) and as the fallback when `--transcripts-dir` IS given
    explicitly (an explicit path is used AS-IS, never run-id-nested)."""
    if args.transcripts_dir:
        return Path(args.transcripts_dir)
    return paths.stack_workdir(required=True) / "m54" / "transcripts" / args.model


def run_transcripts_dir(args, mp: Path, is_resume: bool) -> Path:
    """6th cold review round 6 P29: transcripts live under `<base>/<run_id>/`, `run_id` being
    THIS run's own start timestamp, so two DIFFERENT runs of the same model never share
    `<model>/<task>.json` and silently overwrite each other's evidence. A resume REUSES the
    run_id recorded in the manifest it's building on (never mints a new one), so a resumed run's
    later tasks land in the SAME directory as its earlier ones. An explicit `--transcripts-dir`
    is used AS-IS (no run-id nesting -- the operator asked for exactly that path)."""
    if args.transcripts_dir:
        return Path(args.transcripts_dir)
    base = transcripts_dir_for(args)
    if is_resume and mp.exists():
        try:
            prev_td = (json.loads(mp.read_text(encoding="utf-8")).get("runtime") or {}).get("transcripts_dir")
        except Exception:  # noqa: BLE001
            prev_td = None
        if prev_td:
            return Path(prev_td)
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return base / run_id


def write_transcript(transcripts_dir: Path, task: dict, model: str, turns: list, row: dict) -> Path:
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    doc = {"id": task["id"], "model": model, "system": AB.SYSTEM_PROMPT,
          "task_description": task.get("description", ""), "turns": turns,
          "submitted_via": row.get("submitted_via"), "answer": row.get("answer"),
          "gold_prepare": row.get("gold_prepare"), "gold_live": row.get("gold_live"),
          "passed": row.get("passed"), "outcome": row.get("outcome"),
          # Addendum I (round 6): a setup/grading-infra failure still carries the episode's
          # ACTUAL completed turns above -- these two fields explain WHY it failed on top of that.
          "setup_error": row.get("setup_error"), "error": row.get("error"),
          "infra_evidence": row.get("infra_evidence")}
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


def _gather_candidate_manifest(model: str, *, profile: str, runtime: dict, router: dict) -> dict:
    # cold-review F15: the manifest must record the PROFILE ACTUALLY USED (which may be an
    # --allow-profile override), not a hardcoded "deployed". Built EARLY (before the P21 resume-
    # identity check and before any decision to actually write) -- comparing against a FRESHLY
    # gathered candidate, rather than re-deriving ad hoc fields, keeps the identity check and the
    # eventually-written manifest provably in sync.
    return provenance.gather(model, profile=profile, runtime=runtime, router=router)


def _write_manifest(mp: Path, man: dict, *, history: list, segments: list | None = None) -> None:
    man = dict(man)
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


# 4th cold review G3 + 5th cold review P7 + 6th cold review round 6 P21: a --resume must refuse
# rather than silently continue a run under DIFFERENT conditions than the one that produced the
# existing rows. RESUME_IDENTITY_KEYS covers the flat `runtime` block; P21 additionally requires
# the served-file hash, the EFFECTIVE sampling params actually used, and predictor/context/
# scaffold identity (router.config_sha256, the full sampling dict, kv.draft_kind/kv_bits/
# max_kv_cache_size) to match -- read from provenance.gather's own nested blocks, not re-derived
# ad hoc. Addendum B: llm_timeout_s/deadline_s are DELIBERATELY excluded -- they are DERIVED
# numbers that legitimately drift as more rows accumulate on this axis; identity compares the
# derivation RULE and its inputs (already covered above), and a resume REUSES the previous
# manifest's derived values outright rather than re-deriving and comparing them (see run_generate).
RESUME_IDENTITY_KEYS = ("model", "round_limit", "exec_timeout_s", "sampling_profile",
                       "image_ids", "corpus_sha256", "exclusions_sha256")


def _identity_snapshot(doc: dict) -> dict | None:
    """Flatten every P21 identity-relevant field out of a manifest doc (provenance.gather's
    `runtime.draft_kind`, `kv.{kv_bits,max_kv_cache_size}`, `router.config_sha256`, `sampling`).
    None if the doc lacks one of the required STRUCTURAL blocks, or any of the flat
    RESUME_IDENTITY_KEYS, entirely -- an incomplete/legacy manifest can never be resumed against
    silently. A field being STRUCTURALLY PRESENT but legitimately `None`/`0` (e.g. a model with no
    declared `max_kv_cache_size`, or `kv_bits: 0` for native16 KV) is fine -- it's compared as a
    normal value, not treated as missing."""
    runtime = doc.get("runtime")
    router = doc.get("router")
    kv = doc.get("kv")
    if not isinstance(runtime, dict) or not isinstance(router, dict) or not isinstance(kv, dict):
        return None
    if "sampling" not in doc or "config_sha256" not in router or "draft_kind" not in runtime:
        return None
    if any(k not in kv for k in ("kv_bits", "max_kv_cache_size")):
        return None
    if any(k not in runtime for k in RESUME_IDENTITY_KEYS):
        return None
    snap = {k: runtime.get(k) for k in RESUME_IDENTITY_KEYS}
    snap["router_config_sha256"] = router.get("config_sha256")
    snap["sampling"] = doc.get("sampling")
    snap["draft_kind"] = runtime.get("draft_kind")
    snap["kv_bits"] = kv.get("kv_bits")
    snap["max_kv_cache_size"] = kv.get("max_kv_cache_size")
    return snap


def _check_resume_identity(mp: Path, candidate_doc: dict) -> str | None:
    """None if `mp` doesn't exist yet (nothing to compare against) or its FULL identity snapshot
    matches `candidate_doc`'s; else a refusal reason. A manifest that already recorded a
    `served_config_drift` from a PRIOR exit is refused outright -- that prior run's results are
    suspect and must not be silently built upon."""
    if not mp.exists():
        return None
    try:
        prev_doc = json.loads(mp.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- _load_previous_manifest already surfaces this
        return None
    if prev_doc.get("served_config_drift"):
        return (f"{mp} recorded a served_config_drift from a previous exit -- that run's results "
               "are suspect; investigate before resuming (or start a fresh --out)")
    prev_snap = _identity_snapshot(prev_doc)
    if prev_snap is None:
        return (f"resume refused: {mp} is missing one or more required identity fields (served "
               "config hash, effective sampling, predictor/context identity, or scaffold "
               "identity) -- it predates this check or was produced incompletely; start a fresh "
               "--out rather than resuming against it")
    cur_snap = _identity_snapshot(candidate_doc)
    for key, prev_val in prev_snap.items():
        cur_val = cur_snap.get(key) if cur_snap else None
        if prev_val != cur_val:
            return (f"resume refused: {key} changed since the previous manifest ({mp}): "
                   f"{prev_val!r} -> {cur_val!r}")
    return None


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
    # P32: wall_total_s (container create -> verified removal) is the FULL per-task cost --
    # wall_s alone (just the agent loop) understates campaign duration by the grading/cleanup
    # time on top. Falls back to wall_s for rows that predate wall_total_s.
    wall_totals = [r["wall_total_s"] if isinstance(r.get("wall_total_s"), (int, float))
                  else r.get("wall_s") for r in rows]
    wall_totals = [w for w in wall_totals if isinstance(w, (int, float))]
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
        "wall_total_s_mean": round(statistics.mean(wall_totals), 1) if wall_totals else None,
        "wall_total_s_max": round(max(wall_totals), 1) if wall_totals else None,
        "completion_tokens_mean": round(statistics.mean(toks), 1) if toks else None,
        "completion_tokens_max": round(max(toks), 1) if toks else None,
        "fail_ids": [r["id"] for r in graded_rows if r.get("passed") is not True],
        "setup_error_ids": [r["id"] for r in setup_error_rows],
        # P23: the exact set actually IN the acc/acc_strict denominator -- two arms (or a rerun of
        # the same arm) must intersect `graded_ids` before their accuracies are compared; a task
        # excluded via setup_error on one arm but graded on another is NOT the same evaluation.
        "graded_ids": [r["id"] for r in graded_rows],
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
MAX_GENERATION_HEADROOM_TOKENS = 4096   # P30: thinking_budget + this, when larger than max_tokens
TIMEOUT_HEADROOM_S = 300.0              # P30: fixed prefill/load headroom, replacing the x1.5 safety factor


def _min_per_turn_tps(rows: list, native: bool) -> float | None:
    """6th cold review round 6 P30: the SLOW-tail evidence must be the recorded PER-TURN decode
    rate (a turn's prompt grows across the episode, so later turns decode slower -- an
    EPISODE-AVERAGE `decode_tps` hides exactly the turns most likely to time out), not a
    percentile-smoothed aggregate. For this axis's OWN rows (`native=True`, AgentBench OS rows
    carry `per_turn_decode_tps`), flatten every turn's rate across every row and take the TRUE
    minimum. Fallback benches (math500/convergence) are single-turn probes with only one
    `decode_tps` per row -- the minimum ACROSS ROWS is the best available slow-tail evidence
    there."""
    vals = []
    for r in rows:
        if r.get("error"):
            continue
        if native:
            for v in (r.get("per_turn_decode_tps") or []):
                if isinstance(v, (int, float)) and v > 0:
                    vals.append(v)
        else:
            v = r.get("decode_tps")
            if isinstance(v, (int, float)) and v > 0:
                vals.append(v)
    return min(vals) if vals else None


def _derive_llm_timeout(model: str, thinking_budget, max_tokens, explicit):
    """Returns (timeout_s, source, msg, derivation: dict).

    5th cold review P14: `budget_timeout.derive_timeout`'s 7200s CEILING_S exists for the
    convergence benchmark's own (differently justified: "a pathological draw shouldn't run
    unbounded") axis. An AgentBench OS episode calls the model MANY times across up to
    `--round-limit` turns, each needing a per-turn timeout actually sized to THIS model's
    generation length and measured floor decode rate -- silently capping it at that shared
    ceiling would truncate every turn on a large-budget/slow-decode model long before it could
    legitimately finish, every single turn. So the value here is computed UNCAPPED;
    `observable=False` (no measured rate, no generation-length evidence) is recorded and the
    caller refuses to start rather than silently falling back to a ceiling whose only honest
    meaning is "uninterpretable", unless `--llm-timeout` was given explicitly (recorded as
    `observable="override"` -- P30: an EXPLICIT value is not thereby VALIDATED, an arbitrarily
    short override must not be labelled the same as a measured, sized derivation).

    6th cold review round 6 P30: timeout = max_generation_tokens / floor_tps + TIMEOUT_HEADROOM_S
    (a fixed 300s prefill/load headroom, not a multiplicative safety factor). `max_generation_tokens`
    is the LARGER of the deployed `max_tokens` and `thinking_budget + 4096` -- `max_tokens` alone
    can under-count when the model's post-think answer legitimately extends past its thinking
    budget; `floor_tps` is the TRUE per-turn minimum (see `_min_per_turn_tps`), never an
    episode-averaged or percentile-smoothed rate."""
    max_generation_tokens = max(thinking_budget or 0, 0) + MAX_GENERATION_HEADROOM_TOKENS
    if max_tokens:
        max_generation_tokens = max(max_generation_tokens, max_tokens)
    if explicit:
        derivation = {"max_generation_tokens": max_generation_tokens, "floor_decode_tps": None,
                     "headroom_s": None, "source": "explicit", "observable": "override",
                     "reason": "explicit --llm-timeout override -- NOT independently validated"}
        return explicit, "explicit", f"{explicit:.0f}s (EXPLICIT --llm-timeout, UNVALIDATED)", derivation
    own_rows = generate.rows_for_rate(model, BENCH_NAME)
    tps = _min_per_turn_tps(own_rows, native=True)
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
        tps = _min_per_turn_tps(fb_rows, native=False)
        source = f"fallback:{'+'.join(contributors)}" if tps is not None else "none"
    if not tps or tps <= 0:
        timeout_s = budget_timeout.CEILING_S
        observable = False
        reason = "no measured per-turn decode rate -- a per-turn timeout cannot be SIZED"
    else:
        timeout_s = max_generation_tokens / tps + TIMEOUT_HEADROOM_S
        observable = True
        reason = (f"{max_generation_tokens} max generation tokens at {tps:.1f} tok/s floor "
                 f"(TRUE per-turn minimum) = {max_generation_tokens / tps / 60:.1f} min + "
                 f"{TIMEOUT_HEADROOM_S:.0f}s headroom, UNCAPPED (P14: no 7200s ceiling for this "
                 "per-turn axis)")
    derivation = {"max_generation_tokens": max_generation_tokens, "floor_decode_tps": tps,
                 "headroom_s": TIMEOUT_HEADROOM_S, "source": source,
                 "observable": observable, "reason": reason}
    return (round(timeout_s, 1), source,
           f"{timeout_s:.0f}s (DERIVED, timeout_source={source}) -- {reason}", derivation)


# --------------------------------------------------------------------------- prepare (D2, F6/F7/F10)
def run_prepare(args, out: Path) -> int:
    runner = subprocess.run
    corpus_path = Path(args.corpus)
    # 6th cold review round 6 P31: the exclusions artifact is a SIBLING of --corpus (derived, not
    # user-specified directly) -- a --corpus pointed outside the repo/STACK_WORKDIR would write
    # that derived artifact outside approved roots too, unchecked by the generic --out confinement
    # in main() (which only ever looks at --out, never at --corpus's own directory).
    artifact_refusal = paths.confine_path(AB.exclusions_artifact_path(corpus_path),
                                          what="the D2 exclusions artifact (sibling of --corpus)")
    if artifact_refusal:
        print(f"[agentbench_os] REFUSED: {artifact_refusal}", file=sys.stderr, flush=True)
        return 2
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
        # 6th cold review round 6, P17 remainder: execute the pilot in the SAMPLED order, not
        # re-sorted back to corpus (easy-first) order -- a re-sort silently discards the point of
        # drawing a random sample (early signal from a representative mix, not the easy head).
        by_id = {t["id"]: t for t in candidates}
        candidates = [by_id[i] for i in pilot_ids if i in by_id]

    todo = [t for t in candidates if t["id"] not in done_ids] if args.resume else candidates

    params = model_params.params_for(args.model, profile=args.sampling_profile)
    context_limit = model_params.registry_context_limit(args.model)

    # Addendum B (round 6): on a resume, REUSE the previous manifest's llm_timeout_s/deadline_s
    # outright rather than re-deriving and comparing them -- they are DERIVED numbers that
    # legitimately drift as more rows accumulate on this axis (the floor decode rate moves), so
    # comparing the derived VALUE would make a pilot-then-resume workflow refuse itself once this
    # axis has gathered >=5 rows of its own. Identity (P21) already covers the derivation RULE and
    # its inputs; the derived number itself is explicitly NOT part of identity.
    reused_timeout = None
    if done_ids and mp.exists():
        try:
            prev_runtime = (json.loads(mp.read_text(encoding="utf-8")).get("runtime") or {})
            if "llm_timeout_s" in prev_runtime and "deadline_s" in prev_runtime:
                reused_timeout = prev_runtime
        except Exception:  # noqa: BLE001
            reused_timeout = None
    if reused_timeout is not None:
        llm_timeout = reused_timeout["llm_timeout_s"]
        timeout_source = reused_timeout.get("timeout_source", "resumed")
        timeout_derivation = reused_timeout.get("timeout_derivation") or {"observable": True,
                                                                          "source": "resumed"}
        deadline_s = reused_timeout["deadline_s"]
        timeout_msg = f"{llm_timeout:.0f}s (REUSED from the manifest this resume builds on)"
        deadline_reason = "REUSED from the manifest this resume builds on"
    else:
        llm_timeout, timeout_source, timeout_msg, timeout_derivation = _derive_llm_timeout(
            args.model, params.get("thinking_budget"), params.get("max_tokens"), args.llm_timeout)
        # P14: a per-turn timeout that cannot be SIZED (no measured rate, no budget) is not merely
        # imprecise -- it is uninterpretable, and AGENTS.md forbids silently running on a number
        # that is. Refuse rather than falling back to the shared ceiling, unless overridden.
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
            # truncation, never tuned"): NO hardcoded cap here -- a slow model legitimately needs
            # a longer deadline, and silently capping it is exactly the kind of truncation
            # AGENTS.md forbids for a budget. 8x the per-turn timeout is the whole rule.
            deadline_s = llm_timeout * DEADLINE_MULTIPLIER
            deadline_reason = f"{DEADLINE_MULTIPLIER:.0f}x per-turn timeout"
    print(f"[agentbench_os] per-turn LLM timeout = {timeout_msg}")
    print(f"[agentbench_os] episode deadline = {deadline_s:.0f}s ({deadline_reason})")

    print(f"[agentbench_os] {args.model}: {len(todo)} item(s) to run "
         f"({len(done_ids)} already done, {len(exclusions)} excluded)")

    # 4th cold review G3 + 5th cold review P7 + 6th cold review round 6 P21: a resume (done_ids
    # nonzero) must refuse rather than silently continue under conditions that changed since the
    # manifest it's building on -- compared against a FRESHLY gathered candidate manifest (the
    # same one that will be written below if accepted), covering the flat runtime identity AND
    # the served-file hash / effective sampling / predictor-context-scaffold identity.
    # P29: resolved EXACTLY ONCE per invocation -- a resume reuses the run_id recorded in the
    # manifest it's building on; a fresh run mints one new run_id now. Never re-derive this later
    # in the function (a second `time.strftime(...)`-based call would mint a DIFFERENT run_id).
    tdir = run_transcripts_dir(args, mp, bool(done_ids))
    runtime = {"client": "run_agentbench_os", "bench": BENCH_NAME, "tune": TUNE,
              "corpus": str(corpus_path), "exclusions_path": str(artifact_path),
              "limit": args.limit, "llm_timeout_s": round(llm_timeout, 1),
              "timeout_source": timeout_source, "timeout_derivation": timeout_derivation,
              "deadline_s": round(deadline_s, 1), "n_todo": len(todo),
              "n_done_before": len(done_ids), "n_excluded": len(exclusions),
              "pilot_seed": args.pilot_seed, "pilot_n": args.pilot_n, "pilot_ids": pilot_ids,
              "transcripts_dir": str(tdir),
              "model": args.model, "round_limit": args.round_limit,
              "exec_timeout_s": args.exec_timeout, "sampling_profile": args.sampling_profile,
              "image_ids": image_ids, "corpus_sha256": _sha256_file(corpus_path),
              "exclusions_sha256": _sha256_file(artifact_path)}
    candidate_man = _gather_candidate_manifest(args.model, profile=args.sampling_profile,
                                               runtime=runtime, router=router)
    if done_ids:
        identity_refusal = _check_resume_identity(mp, candidate_man)
        if identity_refusal:
            print(f"[agentbench_os] REFUSED: {identity_refusal}", file=sys.stderr, flush=True)
            return 2

    AB.sweep_stale_containers(AB.GENERATE_CONTAINER_PREFIX, runner)

    prev_segments = []
    if mp.exists():
        try:
            prev_segments = json.loads(mp.read_text(encoding="utf-8")).get("segments") or []
        except Exception:  # noqa: BLE001
            prev_segments = []
    # P21: each segment carries the FULL identity snapshot active for that process start, not
    # just pid/row-count -- a reviewer reconstructing a run's history can see exactly what
    # identity each segment ran under.
    segments = prev_segments + [{"started_at": time.time(), "router_pid": router.get("pid"),
                                 "rows_before": len(done_ids),
                                 "identity": _identity_snapshot(candidate_man)}]
    if todo:
        _write_manifest(mp, candidate_man, history=history, segments=segments)
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
