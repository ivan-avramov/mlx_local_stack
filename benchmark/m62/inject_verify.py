#!/usr/bin/env python3
"""C147 §2 verifier: the single, authoritative contract for injected-positive rows.

    inject_verify.py --run <$STACK_WORKDIR/m62/inject> [--kind stall|loop|alloc|interrupt] [--workdir DIR]

Reads every `<kind>.attempt<n>.jsonl` (+ `.manifest.json`) and prints one line per row, always led by the attempt
stem:  `<stem>: PASS | PASS_NO_INFLIGHT | FAIL:<why> | not_observed[:what] | competing_trigger:<reason>`.
S27 §4.3 / §4.5: `PASS_NO_INFLIGHT` (stall / loop) is detection proven with no request in flight at the kill; the suite
passes only with the `interrupt` positive's in-flight PASS.
`--kind` limits the run to one kind and skips the suite-level rules (the driver's per-leg call).

Cancellation proof: see `cancellation_consistent` (no cancelled counter exists on the worker; completed must not rise).
`--kind X` with no attempt file for X exits 1 (`FAIL:missing`); the numerically latest attempt of a kind is the
retained one even when unreadable (`FAIL:unreadable`, exit 1).

Exit codes: 0 only when every suite-level check holds; 1 when any FAIL exists in a retained (last) attempt or a
suite check; 4 (retryable) otherwise, including partial run directories. Earlier attempts are listed as retries and
never count as clearance evidence. Live checks (docker, processes) only list; nothing is ever killed or removed.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "benchmark"))
from bench.run_config import ALL_INJECT_KINDS as KINDS  # noqa: E402 — S27 X1: the one shared kind list (+ interrupt, C373)
T_TOKENS = 81920
RUN_ID = re.compile(r"^\d{8}T\d{6}-[0-9a-f]{12}$")          # the probe's `<YYYYMMDDTHHMMSS>-<12 hex>`
ATTEMPT = re.compile(r"^(stall|loop|alloc|interrupt)\.attempt(\d+)\.jsonl$")
# S27 §4.3: stall / loop detection proven with NOTHING in flight at the kill (no cancellation to prove): a distinct verdict, so
# a consumer that requires a cancellation proof can tell it apart. The interrupt positive (§4.5) never takes it.
PASS_NO_INFLIGHT = "PASS_NO_INFLIGHT"
PASSING = ("PASS", PASS_NO_INFLIGHT)
INTERRUPTED_KINDS = ("interrupted", "interrupted_charged")
EVIDENCE_PATHS = {"events": "events_path", "export": "transcript_path", "stderr": "stderr_path"}
# M76 B4b-1 (change review L1): a v2 row (`arm_opencode.row_fields`) also records its date-freeze receipts and, when present,
# its tool-window receipts; each recorded artifact has its path field and its digest. tg2 rows are always date-frozen.
V2_EVIDENCE_PATHS = {"datefreeze": "datefreeze_path", "toolwindows": "toolwindows_path"}
REQUIRED_EVIDENCE = {"opencode-v2-web-tg2": ("datefreeze",)}


def evidence_paths(row, scaffold="opencode-v2-web-tg1"):
    """{artifact: row path field} of the artifacts the row records (the base three, plus each v2 artifact whose path field
    the row carries); None when a required one of the scaffold is not recorded."""
    paths = dict(EVIDENCE_PATHS)
    paths.update({k: field for k, field in V2_EVIDENCE_PATHS.items() if field in row})
    if not set(REQUIRED_EVIDENCE.get(scaffold, ())) <= set(paths):
        return None
    return paths


class Result:
    def __init__(self, stem, kind, attempt, verdict, notes=()):
        self.stem, self.kind, self.attempt, self.verdict, self.notes = stem, kind, attempt, verdict, list(notes)

    @property
    def category(self):
        return self.verdict.split(":", 1)[0]


def workdir_default():
    sys.path.insert(0, str(REPO / "benchmark"))
    from bench import paths
    return paths.stack_workdir()


def resolve(path, workdir):
    return Path(str(path).replace("$STACK_WORKDIR", str(workdir)))


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_events(path):
    events = []
    for line in Path(path).read_text().splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def derive(events):
    """(finish_count, tool_calls) with tool_calls = [(request_index, part_id, tool, canonical_input, state)]."""
    finished = 0
    calls = []
    for e in events:
        if e.get("type") == "step_finish":
            finished += 1
        elif e.get("type") == "tool_use":
            part = e.get("part", {})
            calls.append((finished + 1, part.get("id"), part.get("tool"),
                          json.dumps(part.get("state", {}).get("input"), sort_keys=True), part.get("state", {})))
    return finished, calls


def last_progress_boundary(gate):
    best, boundary = gate["baseline_failing"], 0
    for b, failing, tampered in gate.get("failing_trajectory", []):
        if failing is not None and not tampered and failing < best:
            best, boundary = failing, max(boundary, b)
    return boundary


def check_files(row, manifest, workdir, scaffold="opencode-v2-web-tg1"):
    sha = row.get("evidence_sha256")
    paths = evidence_paths(row, scaffold)
    if not isinstance(sha, dict) or paths is None or set(sha) != set(paths):
        return "FAIL:evidence_sha256_keys"
    for name, field in paths.items():
        path = resolve(row.get(field, ""), workdir)
        if not sha[name] or not path.is_file() or sha_file(path) != sha[name]:
            return f"FAIL:evidence_sha:{name}"
    sys.path.insert(0, str(REPO / "benchmark"))
    from bench import structured_grade as sg
    lang = str(row.get("id", "")).split("/", 1)[0]
    reasons = sg.validate_reports(row.get("grade_reports"), lang, row.get("test_modified"),
                                  **({"grader": "tg2"} if scaffold == "opencode-v2-web-tg2" else {}))
    if reasons:
        return "FAIL:grade_reports:" + reasons[0]
    for report in row.get("grade_reports") or []:
        if not report.get("artifacts"):
            continue
        for name, meta in report["artifacts"].items():
            path = resolve(meta.get("path", ""), workdir)
            if not meta.get("sha256") or not path.is_file() or sha_file(path) != meta["sha256"]:
                return f"FAIL:grade_report_sha:{report.get('seq')}:{name}"
    return None


def killed_state_ok(state):
    """The frozen killed-command shape (fixtures/opencode_2.0.20_killed_tool_part.json): an error, or a
    completed call whose metadata carries a nonzero exit or a signal. Events nest metadata one level deeper."""
    if state.get("status") == "error":
        return True
    meta = state.get("metadata") or {}
    for m in (meta, meta.get("metadata") or {}):
        if state.get("status") == "completed" and (m.get("signal") or m.get("exit") not in (0, None)):
            return True
    return False


def never_executed(state):
    """A tool call that never ran: `state.status` is `error` and `state.metadata.providerCall.executed` is false (the
    tool-bounds plugin rejected it before execution; S26 erratum 2)."""
    if not isinstance(state, dict) or state.get("status") != "error":
        return False
    meta = state.get("metadata")
    call = meta.get("providerCall") if isinstance(meta, dict) else None
    return isinstance(call, dict) and call.get("executed") is False


def cancellation_consistent(term):
    """Cancellation CONSISTENCY (Q6/Q18), not proof: the worker exposes no request- or session-correlated cancel
    receipt (tracked as C149), so an independently failed request would look the same. The worker's /metrics `summary` (mlx_vlm/server/generation.py, `snapshot`) has
    requests_started / requests_completed / requests_failed / in_flight and NO cancelled or aborted counter, so the
    strongest available rule applies: the request was in flight at the kill (`in_flight_at_kill >= 1`), `in_flight`
    reached 0, and `requests_completed` did NOT increase between the samples. An increase is natural completion,
    not cancellation. (`requests_failed` may rise: a disconnect is recorded there when the worker notices.)
    If the worker ever exposes a `requests_cancelled`/`requests_aborted` counter, it must rise by exactly 1."""
    before, after = term.get("worker_summary_before"), term.get("worker_summary_after")
    if not (isinstance(term.get("in_flight_at_kill"), int) and term["in_flight_at_kill"] >= 1
            and isinstance(before, dict) and isinstance(after, dict)
            and isinstance(before.get("in_flight"), int) and before["in_flight"] >= 1
            and after.get("in_flight") == 0):
        return False
    for name in ("requests_cancelled", "requests_aborted"):
        if name in before or name in after:
            return after.get(name, 0) - before.get(name, 0) == 1
    done_before, done_after = before.get("requests_completed"), after.get("requests_completed")
    if not isinstance(done_before, int) or not isinstance(done_after, int):
        return False
    return done_after == done_before


def no_inflight_consistent(term, row):
    """S27 §4.3: the order-tolerant link with NO request in flight at the kill: `in_flight_at_kill == 0`, the worker's
    `requests_started` unchanged from before to after, `after.in_flight == 0`, and the trailing message not an interrupted
    kind."""
    before, after = term.get("worker_summary_before"), term.get("worker_summary_after")
    return (type(term.get("in_flight_at_kill")) is int and term["in_flight_at_kill"] == 0
            and isinstance(before, dict) and isinstance(after, dict)
            and type(before.get("requests_started")) is int and before.get("requests_started") == after.get("requests_started")
            and after.get("in_flight") == 0
            and (row.get("reconciliation") or {}).get("trailing") not in INTERRUPTED_KINDS)


def causal(kind, row, notes, *, strict=False):
    """None when the live stop -> kill -> cancel -> reconcile chain is evidenced; `PASS_NO_INFLIGHT` when (stall / loop) the kill
    found nothing in flight (S27 §4.3); else a verdict string. `strict` (the interrupt positive): the in-flight proof only."""
    term, gate = row.get("termination") or {}, row["gate"]
    killed = term.get("killed") or []
    if term.get("reason") != gate["stop_reason"] or not any(k.get("role") == "client" for k in killed):
        return "not_observed:kill"          # the item ended before the stop path ran
    if term.get("killed_verified") is not True:
        return "FAIL:causal:killed_verified"
    usage = row.get("request_usage") or []
    bound = max(300, (usage[-1][2] if usage else 0) / 300)
    wait = term.get("cancel_wait_s")
    if not isinstance(wait, (int, float)) or isinstance(wait, bool) or wait > bound:
        return "FAIL:causal:cancel_wait_s"
    if not strict and term.get("in_flight_at_kill") == 0 and type(term.get("in_flight_at_kill")) is int \
            and no_inflight_consistent(term, row):
        # S27 §4.3: order-tolerant — nothing was in flight at the kill (worker counters unchanged, trailing not interrupted);
        # the loop's descendant kill is still required. Anything else takes the existing in-flight proof below.
        if kind == "loop" and not any(k.get("role") == "model" and k.get("argv", [])[-2:] == ["sleep", "600"]
                                      for k in killed):
            return "not_observed:descendant"
        notes.append("no_request_in_flight")
        return PASS_NO_INFLIGHT
    if (row.get("reconciliation") or {}).get("trailing") not in (
            INTERRUPTED_KINDS if strict else ("interrupted", "unpublished", "interrupted_charged")):
        return "not_observed:trailing"      # the kill landed after the in-flight message was settled
    if kind == "loop" and not any(k.get("role") == "model" and k.get("argv", [])[-2:] == ["sleep", "600"]
                                  for k in killed):
        return "not_observed:descendant"
    if cancellation_consistent(term):
        notes.append("cancellation_consistent")
    elif kind in ("loop", "interrupt"):
        return "not_observed:cancellation"
    else:
        notes.append("cancellation_not_shown")
    return None


SCAFFOLDS = ("opencode-v2-web-tg1", "opencode-v2-web-tg2")          # M76 B4b-1: the tg2 probe's injected positives too


def verify_row(kind, row, manifest, workdir, scaffold="opencode-v2-web-tg1"):
    notes = []
    label = scaffold + "-inject:" + kind
    runtime = (manifest or {}).get("runtime") or {}
    if row.get("scaffold") != label or runtime.get("scaffold") != label or \
            (runtime.get("inject") or {}).get("kind") != kind:
        return "FAIL:label", notes
    if manifest.get("transport_abort"):
        return "FAIL:transport_abort", notes
    if not isinstance(manifest.get("run_id"), str) or not RUN_ID.match(manifest["run_id"]):
        return "FAIL:run_id", notes
    if row.get("worker_before") != row.get("worker_after") or not row.get("worker_before"):
        return "FAIL:worker_drift", notes
    bad = check_files(row, manifest, workdir, **({"scaffold": scaffold} if scaffold != "opencode-v2-web-tg1" else {}))
    if bad:
        return bad, notes
    gate = row["gate"]
    finished, calls = derive(load_events(resolve(row["events_path"], workdir)))
    stop = gate.get("stop_reason")
    if kind == "interrupt":
        # S27 §4.5 (C373): the harness stopped the item while the worker reported a generation in flight; PASS needs the
        # existing in-flight proof (trailing interrupted, cancellation consistent, client kill verified, cancel_wait_s bound)
        if stop and stop != "interrupt":
            return f"competing_trigger:{stop}", notes
        if stop != "interrupt":
            return "not_observed", notes
        failure = causal(kind, row, notes, strict=True)
        return (failure or "PASS"), notes
    if kind == "stall":
        if stop == "stalled" and gate["no_progress_tokens"] >= T_TOKENS:
            return "competing_trigger:T", notes
        if stop and stop != "stalled":
            return f"competing_trigger:{stop}", notes
        if stop != "stalled":
            return "not_observed", notes
        if gate["no_progress_requests"] < 4:
            return "FAIL:stall_threshold", notes
        if finished - last_progress_boundary(gate) < 4:
            return "FAIL:events_rederivation", notes
        failure = causal(kind, row, notes)
        return (failure or "PASS"), notes
    if kind == "loop":
        if stop and stop != "looping":
            return f"competing_trigger:{stop}", notes
        if stop != "looping":
            return "not_observed", notes
        if gate["max_identical_run_live"] < 3:
            return "FAIL:loop_threshold", notes
        sigs = [(tool, inputs) for (_, _, tool, inputs, _) in calls]
        if not any(len(set(sigs[i:i + 3])) == 1 for i in range(len(sigs) - 2)):
            return "FAIL:events_rederivation", notes
        failure = causal(kind, row, notes)
        return (failure or "PASS"), notes
    # alloc
    kills = row.get("mem_kills") or []
    if not kills:
        return "not_observed:kill", notes
    if len(kills) != 1:
        return "FAIL:multiple_kills", notes
    kill = kills[0]
    if kill.get("role") != "model" or not any("bytearray(" in a for a in kill.get("argv") or []):
        return "FAIL:unrelated_kill", notes
    per_process = ((runtime["inject"].get("policy") or {}).get("hygiene") or {}).get("per_process")
    if not isinstance(kill.get("rss"), int) or not isinstance(per_process, int) or kill["rss"] <= per_process:
        return "FAIL:rss", notes
    # S26 erratum 2: only EXECUTED shell calls carrying the alloc command count (a call the tool-bounds plugin rejected never ran)
    shell = [c for c in calls if c[2] == "shell" and "bytearray(" in c[3] and not never_executed(c[4])]
    if len(shell) != 1:
        return "FAIL:no_shell_part", notes
    request, part_id, _, _, state = shell[0]
    if kill.get("tool_call_id") != part_id:
        return "FAIL:tool_call_id", notes
    if kill.get("carrying_request") != request or kill.get("completed_boundary_at_kill") != request - 1:
        return "FAIL:request_linkage", notes
    if not killed_state_ok(state):
        return "FAIL:killed_part_shape", notes
    if gate["requests_completed"] <= request:
        return "not_observed:continuation", notes
    return "PASS", notes


def docker_names():
    out = subprocess.run(["docker", "ps", "-a", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=30)
    if out.returncode:
        raise RuntimeError("docker ps failed: " + out.stderr[-200:])
    return out.stdout.split()


def list_processes():
    import psutil
    found = []
    for p in psutil.process_iter():
        try:
            if p.uids().real == os.getuid():
                found.append((p.pid, p.cwd(), p.cmdline()))
        except (psutil.Error, OSError):
            continue
    return found


def live_checks(run_id, workdir, docker_ps, process_lister):
    """FAIL strings for containers named with this run's exact registered prefix / processes under its roots."""
    problems = []
    # Grader containers are named `mlxbench-<guard run_id>-<item>-<n>`, and the guard's run_id is the run directory
    # name (`run-<id>`); the bare form is accepted too. Unrelated containers: neither fail nor target.
    prefixes = (f"mlxbench-run-{run_id}-", f"mlxbench-{run_id}-")
    mine = [n for n in docker_ps() if n.startswith(prefixes)]
    if mine:
        problems.append("FAIL:containers:" + ",".join(mine))
    roots = [str(Path(workdir) / "opencode-probe-v2" / f"run-{run_id}"),
             str(Path(workdir) / "scratch/octmp.noindex")]
    me = {os.getpid(), os.getppid()}
    hits = [(pid, argv[:3]) for pid, cwd, argv in process_lister()
            if pid not in me and any(cwd == r or cwd.startswith(r + "/") or any(r + "/" in a for a in argv)
                                     for r in roots)]
    if hits:
        problems.append("FAIL:processes:" + json.dumps(hits))
    return problems


def main(argv=None, *, docker_ps=None, process_lister=None, out=print):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, type=Path)
    ap.add_argument("--kind", choices=KINDS)
    ap.add_argument("--workdir", type=Path)
    ap.add_argument("--scaffold", choices=SCAFFOLDS, default=SCAFFOLDS[0],
                    help="the probe's scaffold label (default tg1; tg2: run_tg2_probe.py --tg2-inject)")
    a = ap.parse_args(argv)
    workdir = a.workdir or workdir_default()
    attempts = {}
    for path in sorted(a.run.glob("*.attempt*.jsonl")):
        m = ATTEMPT.match(path.name)
        if m and (a.kind is None or m.group(1) == a.kind):
            attempts.setdefault(m.group(1), {})[int(m.group(2))] = path
    results, retained = [], {}
    for kind in KINDS:
        if a.kind and kind != a.kind:
            continue
        files = attempts.get(kind, {})
        for n in sorted(files):
            path = files[n]
            stem = path.name[:-len(".jsonl")]
            try:
                rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
                manifest = json.loads(path.with_suffix(".manifest.json").read_text())
            except (OSError, ValueError):
                # An unreadable attempt is still an attempt: if it is the latest it IS the retained one.
                r = Result(stem, kind, n, "FAIL:unreadable")
                results.append(r)
                retained[kind] = r
                continue
            if len(rows) != 1:
                verdict, notes = ("FAIL:transport_abort" if manifest.get("transport_abort") else "FAIL:no_row"), []
            else:
                try:
                    verdict, notes = verify_row(kind, rows[0], manifest, workdir, scaffold=a.scaffold)
                except (KeyError, TypeError, ValueError, OSError) as exc:
                    verdict, notes = f"FAIL:malformed:{type(exc).__name__}:{exc}", []
                for entry in rows[0].get("orphans_unattributed") or []:
                    notes.append("orphan_unattributed:" + json.dumps(entry, default=str))
            r = Result(stem, kind, n, verdict, notes)
            r.run_id = manifest.get("run_id")
            results.append(r)
            retained[kind] = r
    last = {k: max(v) for k, v in attempts.items()}
    if a.kind and a.kind not in attempts:
        out(f"{a.kind}: FAIL:missing (no {a.kind}.attempt<n>.jsonl in {a.run})")
        out("RESULT FAIL")
        return 1
    suite = []
    for r in results:
        tag = "" if r.attempt == last.get(r.kind) else "  [retry: not clearance evidence]"
        out(f"{r.stem}: {r.verdict}{tag}")
        for note in r.notes:
            out(f"{r.stem}:   note {note}")
    if a.kind is None:
        for kind in KINDS:
            if kind not in retained:
                suite.append(f"not_observed:{kind}:absent")
        loop = retained.get("loop")
        if loop and loop.verdict == "PASS" and "cancellation_consistent" in loop.notes:
            out("suite: loop cancellation consistent, not correlated \u2014 see C149")
        if loop and loop.verdict == "PASS" and "cancellation_consistent" not in loop.notes:
            suite.append("not_observed:loop:cancellation")
        interrupt = retained.get("interrupt")
        if interrupt and interrupt.verdict != "PASS":
            # S27 §4.5: the record passes only with the interrupt positive's in-flight proof; stall / loop prove detection
            suite.append(f"not_observed:interrupt:{interrupt.verdict}")
        docker_ps = docker_ps or docker_names
        process_lister = process_lister or list_processes
        for kind, r in retained.items():
            if r.verdict in PASSING:
                try:
                    suite += [f"{kind}:{p}" for p in live_checks(r.run_id, workdir, docker_ps, process_lister)]
                except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
                    suite.append(f"FAIL:live_check_unavailable:{exc}")
        for line in suite:
            out(f"suite: {line}")
    verdicts = [r.verdict for r in retained.values()] + suite
    if any(v.split(":", 1)[0] == "FAIL" or ":FAIL" in v for v in verdicts):
        out("RESULT FAIL")
        return 1
    if any(v not in PASSING for v in verdicts) or (a.kind is None and not retained):
        out("RESULT retryable (exit 4)")
        return 4
    if a.kind is not None and retained[a.kind].verdict == PASS_NO_INFLIGHT:
        out(f"RESULT {a.kind} {PASS_NO_INFLIGHT}")          # S27 §4.3: detection proven, nothing in flight at the kill
        return 0
    out("RESULT PASS" if a.kind is None else f"RESULT {a.kind} PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
