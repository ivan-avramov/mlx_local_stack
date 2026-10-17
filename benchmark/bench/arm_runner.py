"""The arm-aware item runner and probe main (M64 spec 5): `tg1_runner`'s generation loop, driven through an ArmAdapter.

`tg1_runner.run_item` / `_main` are the frozen tg1 path (their import closure IS the tg1 generation identity, so they
are not edited). This module reproduces their control flow with every client-specific step behind the adapter:
evidence suffixes, spawn command, the event stream, transcript acquisition, reconciliation (and compaction
accounting), receipts, the identity and the row's client-named fields. Runner-owned parts are the tg1 ones, reused from
`tg1_runner` as a library (`GradeWorker`, `PhaseHeartbeat`, the gate, the guard, the worker / router checks, the
terminal grading and the manifest), so `OpencodeArm(mode="tg1")` through this runner writes the rows tg1 writes
(`test_m64_arm_oc_parity.py`). Added for the arms: the shell watchdog (spec 5.4) when the adapter enables it, compaction
accounting, and the arm-identifying row/manifest fields (`arm`, `epoch_id`, `snapshot_sha256`).

Seams the tg1 tests patch (`worker_identity`, `worker_json`, `arm_identity_of`, `CARRIER`) are read from `tg1_runner`
at call time, so one patch serves both paths."""
from __future__ import annotations

import hashlib
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid

from . import arm_adapter as aa
from . import arm_watchdog
from . import datefreeze
from . import proc_guard as pg
from . import provenance
from . import structured_grade as sg
from . import tg1_runner as t1
from . import token_turn_gate as tg
from . import toolchain
from m62 import universe_preflight

REPO = Path(__file__).resolve().parents[2]
WATCHDOG_TICK_S = 1.0


def run_item(p, adapter, *, ctx=None, **kwargs):
    """Run one item. `ctx` (a dict) receives `cleanup_status` on EVERY exit path; a cooperative cancel honoured during
    generation raises `RunnerCancelled` after the full terminal path, carrying the item's evidence (as tg1's)."""
    ctx = {} if ctx is None else ctx
    result = _run_item(p, adapter, ctx=ctx, **kwargs)
    cancel = kwargs.get("cancel")
    if ctx.get("cancelled") or (cancel is not None and cancel()):
        evidence = result["evidence"]
        raise t1.RunnerCancelled(item=dict(
            id=ctx.get("id"),
            evidence_sha256={k: p._sha_of(v) for k, v in evidence.items()} if p else {},
            grade_reports=result["grade_reports"],
            reconciliation=result["reconciliation"],
            termination=result["termination"],
            cleanup_status=ctx.get("cleanup_status"),
        ))
    return result


def _run_item(p, adapter, *, model, work, prompt, env, binary, evidence, entry, limit, private, router, base,
              protected_pids=(), policy=None, cancel=None, ctx=None, frozen_date=None, gate_overrides=None):
    gate_policy, hygiene = policy if policy is not None else t1.effective_policy()
    if gate_overrides:
        gate_policy = {**gate_policy, **gate_overrides}
    scrub = p._scrub_pii if p is not None else (lambda text: text)
    portable = p._portable if p is not None else str
    gate = tg.TokenTurnGate(entry["baseline_failing"], context_limit=limit, universe_size=len(entry["leaves"]),
                            policy=gate_policy)
    lock = threading.RLock()
    observations = []
    termination = dict(reason=None, killed=[], killed_verified=None, cancel_wait_s=None, in_flight_at_kill=None,
                       worker_summary_before=None, worker_summary_after=None, client_stop=None, graceful_wait_s=None)
    if ctx is not None:
        ctx.update(termination=termination)      # abort manifests carry whatever the kill path recorded
    silence_observer = pg.SilenceObserver()
    exit_hang = False
    cancelled = False
    resources = dict(grader_mem_kill=False, grader_oom=False)
    paths = {key: evidence.with_suffix(suffix) for key, suffix in adapter.evidence_suffixes().items()
             if key != "datefreeze" or frozen_date is not None}
    if frozen_date is not None:
        # P364: one receipt file per item, in the item's evidence directory (never the config directory); the env the
        # client is spawned with must name exactly this file and this date.
        if (env.get(datefreeze.ENV_DATE) != frozen_date
                or env.get(datefreeze.ENV_RECEIPTS) != str(paths["datefreeze"])):
            raise tg.TransportAbort("P364: the spawn env does not name this item's frozen date and receipt file")
    for path in paths.values():
        pg.reserve_evidence(path)
    keep = Path(str(evidence) + ".grades")
    try:
        keep.mkdir(parents=True)
    except FileExistsError:
        raise tg.TransportAbort("immutable grade report directory exists: " + keep.name) from None
    sequence = itertools.count(1)
    sequence_lock = threading.Lock()

    def next_seq():
        with sequence_lock:
            return next(sequence)

    started = time.monotonic()
    stop = threading.Event()
    ingest_failure = []
    guard = pg.ProcessGuard(
        adapter.guard_roots(work, env, private),
        run_id=Path(private).parent.name,
        item=entry.get("id", work.name),
        protected_pids=(*protected_pids, router.get("pid")),
        per_process=hygiene["per_process"],
        aggregate=hygiene["aggregate"],
        client_limit=hygiene["client_limit"],
        scrub=scrub,
        context=lambda: dict(completed_requests=len(gate.request_usage)),
    )

    def grade(snap):
        modified = sg.tampered(snap.path, entry["protected"], entry["prepared"], entry["lang"])
        if modified:
            return None, True
        result = sg.grade(entry["lang"], snap.path, entry["test"], private, guard=guard, keep=keep, seq=next_seq(),
                          boundary=snap.boundary, final=False)
        resources["grader_mem_kill"] |= result.grader_mem_kill
        resources["grader_oom"] |= result.grader_oom
        return result.failing({tuple(x) for x in entry["leaves"]}), False

    worker = t1.GradeWorker(gate, lock, work, private, grade)
    stream = adapter.new_stream(gate, worker.notify)
    stream.base_url = base
    proc = None
    client_launch_attempted = False
    ingester = None
    killed = False
    final_result = None
    cancellation_attempted = False
    heartbeat = t1.PhaseHeartbeat(gate, lock, started)
    reconciliation = None
    tmp_before = None
    tmp_window_start = time.time()
    dog = None
    try:
        tmp_before = pg.tmp_listing()
    except OSError:
        tmp_before = None

    def terminate_client(reason=None):
        nonlocal killed, cancellation_attempted
        if cancellation_attempted:
            return
        with lock:
            if reason and reason not in ("client_exit_hang", "runner_cancel"):
                gate.stop(reason)
            if not killed:
                gate.requests_at_kill = len(gate.request_usage)
                gate.inflight_s_at_stop = (time.monotonic() - stream.started_at if stream.started_at else None)
                termination.update(reason=reason, requests_at_kill=gate.requests_at_kill,
                                   inflight_s_at_stop=gate.inflight_s_at_stop)
        killed = True
        heartbeat.set_phase("cancellation")
        if reason:
            # The summary immediately before the kill: proves the worker was serving this session's request.
            try:
                before = t1.worker_json("metrics")
                termination.update(in_flight_at_kill=pg.in_flight(before), worker_summary_before=before.get("summary"))
            except Exception:  # noqa: BLE001 — evidence only; the kill must still run
                pass
        errors = []
        killed_entries = []

        def capture_cutoff():
            # Raw events-file position immediately before the actual SIGTERM; committed only once a signal was
            # really delivered (`commit_cutoff`), so a failed signal leaves the tolerance disabled.
            try:
                return paths["events"].stat().st_size
            except OSError:
                return None

        def commit_cutoff(size):
            stream.signal_offset = size

        # C147: the client gets SIGTERM first so its own abort path can persist the in-flight assistant message;
        # survivors after GRACEFUL_CLIENT_S are SIGKILLed. Model-role processes are always SIGKILLed.
        graceful = getattr(guard, "graceful_stop", None)
        if graceful is not None:
            began = time.monotonic()
            try:
                killed_entries.extend(adapter.cancel(guard, t1.GRACEFUL_CLIENT_S, before_signal=capture_cutoff,
                                                     after_signal=commit_cutoff) or [])
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            termination["graceful_wait_s"] = time.monotonic() - began
        forced = []
        for role in ("client", "model"):
            try:
                got = guard.kill_role(role) or []
                forced.extend(got if role == "client" else [])
                killed_entries.extend(got)
            except Exception as exc:  # noqa: BLE001 — cancellation must still run (V5a P14)
                errors.append(exc)
        if graceful is not None:
            termination["client_stop"] = "sigkill" if forced else "sigterm"
        seen_keys = set()
        unique = []
        for killed_entry in killed_entries:
            key = (killed_entry["pid"], killed_entry["create_time"])
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(killed_entry)
        killed_entries = unique
        termination["killed"] = killed_entries
        verify = getattr(guard, "verify_gone", None)
        if verify is not None and killed_entries:
            termination["killed_verified"] = bool(verify(killed_entries, wait=2.0))
        cancellation_attempted = True
        last_metrics = {}

        def metrics():
            last_metrics["value"] = t1.worker_json("metrics")
            return last_metrics["value"]

        elapsed = pg.wait_cancel(metrics, prompt_tokens=gate.request_usage[-1][2] if gate.request_usage else 0)
        termination["cancel_wait_s"] = elapsed
        if "value" in last_metrics:
            termination["worker_summary_after"] = last_metrics["value"].get("summary")
        if errors:
            raise errors[0]

    heartbeat.start()
    try:
        guard.start()
        worker.start()
        with paths["events"].open("wb") as stdout, paths["stderr"].open("wb") as stderr:
            client_launch_attempted = True
            # P17/C170: the date the client prints into the system prompt, read immediately before the spawn (a
            # midnight-crossing item must record the date the model was shown, not the date it finished).
            prompt_date_real = p._prompt_date() if p is not None else time.strftime("%a %b %d %Y")
            prompt_date = frozen_date if frozen_date is not None else prompt_date_real
            proc = guard.spawn(adapter.command(binary, model, prompt), cwd=work, env=env, stdin=subprocess.DEVNULL,
                               stdout=stdout, stderr=stderr)
            if adapter.watchdog_enabled:
                dog = arm_watchdog.ShellWatchdog.for_client(
                    proc.pid, limit_s=getattr(adapter, "watchdog_limit_s", arm_watchdog.LIMIT_S),
                    grace_s=getattr(adapter, "watchdog_grace_s", arm_watchdog.GRACE_S))
            last_dog = 0.0

            def ingest():
                try:
                    with paths["events"].open("rb") as fp:
                        while True:
                            data = fp.read(65536)
                            if data:
                                with lock:
                                    stream.feed(data)
                            elif stop.is_set():
                                with lock:
                                    stream.finish(killed=killed or guard.client_resource)
                                return
                            else:
                                stop.wait(0.05)
                except BaseException as exc:
                    ingest_failure.append(exc)

            ingester = threading.Thread(target=ingest, name="m62-ingestion", daemon=True)
            ingester.start()
            last_silence = 0
            while proc.poll() is None:
                guard.check()
                worker.check()
                if ingest_failure:
                    raise ingest_failure[0]
                now = time.monotonic()
                if dog is not None and now - last_dog >= WATCHDOG_TICK_S:
                    last_dog = now
                    with lock:
                        dog.set_windows(adapter.tool_windows(stream))
                    if dog.tick():
                        with lock:
                            gate.flags.add("exec_timeout")        # spec 5.4: the row gets the flag; the client sees the tool fail
                with lock:
                    if guard.client_resource:
                        gate.stop("client_resource")
                    if (now - stream.last_event >= pg.POLICY["silence_s"]
                            and now - last_silence >= pg.POLICY["silence_sample_s"]):
                        metrics = t1.worker_json("metrics")
                        descendant = guard.descendants_alive()
                        size = paths["events"].stat().st_size
                        observed_reason = silence_observer.sample(now, size, metrics, descendant)
                        observations.append(dict(
                            sampled_at_s=now - started, event_bytes=size, idle_samples=silence_observer.idle,
                            silent_s=now - stream.last_event, in_flight=pg.in_flight(metrics),
                            tracked_descendant_alive=descendant))
                        last_silence = now
                        if observed_reason == "client_exit_hang":
                            exit_hang = True
                        elif observed_reason:
                            gate.stop(observed_reason)
                    reason = gate.stop_reason or ("client_exit_hang" if exit_hang else None)
                    if not reason and cancel is not None and cancel():
                        # Cooperative cancel (C147 §3c): a gate stop decided at the same tick takes precedence.
                        reason = "runner_cancel"
                        cancelled = True
                if reason:
                    provenance.assert_served_config_unchanged(router, base)
                    terminate_client(reason)
                    break
                stop.wait(0.1)
            # The watchdog may kill the client before the loop ever observes it alive.
            if guard.client_resource or proc.returncode is not None and proc.returncode < 0:
                terminate_client("client_resource" if guard.client_resource else None)
            proc.wait(timeout=10)
        heartbeat.set_phase("terminal_drain")
        stop.set()
        ingester.join(5)
        if ingester.is_alive():
            raise tg.TransportAbort("ingestion thread did not drain")
        if ingest_failure:
            raise ingest_failure[0]
        heartbeat.set_phase("terminal_grading")
        worker.finish()
        if guard.client_resource:
            gate.stop("client_resource")
        # Transcript acquisition is tracked, and the raw native IDs remain intact.
        heartbeat.set_phase("export")
        transcript = adapter.transcript(guard, env, work, stream, binary, raw_sink=paths["export"].write_text)
        paths["export"].write_text(transcript.raw)
        export = transcript.doc
        # The final grade must have a chance to credit its boundary before a T/N stop.
        final_boundary = adapter.final_boundary(transcript)
        gate.pending.add(final_boundary)
        try:
            outcome = ("client_exit_hang" if exit_hang and not gate.stop_reason else
                       (gate.stop_reason or ("runner_cancel" if cancelled else None))
                       if killed or guard.client_resource else None)
            rec = adapter.reconcile(stream, transcript, None, proc.returncode, outcome)
            reconciliation = rec.row_reconciliation()
        except tg.TransportAbort as exc:
            if exit_hang:
                raise tg.TransportAbort("client silent, worker idle: " + str(exc)) from exc
            raise
        date_summary = None
        if frozen_date is not None:
            # P364: every request of the item must have been masked: exact reconciliation, any mismatch aborts (no row).
            date_summary = adapter.receipts_reconcile(
                paths["datefreeze"], frozen=frozen_date, session_id=stream.session_id,
                requests_observed=len(stream.starts), killed=bool(killed or guard.client_resource))
            adapter.merge_receipts(rec, date_summary)
        final_boundary_actual = len(gate.request_usage)
        if final_boundary != final_boundary_actual:
            gate.pending.discard(final_boundary)
            gate.pending.add(final_boundary_actual)
        # C147 §4: /tmp escape diagnostic and exact-path cleanup, after the client is gone.
        tmp_found, tmp_cleaned, tmp_kept, tmp_window = [], [], [], None
        tmp_found = adapter.tmp_escapes(transcript, env)
        try:
            tmp_after = pg.tmp_listing()
        except OSError:
            tmp_after = None
        tmp_window = (tmp_window_start, time.time())
        if tmp_before is None or tmp_after is None:
            tmp_kept = [[c["path"], "ambiguous"] for c in tmp_found if c["exact"]]
        else:
            tmp_cleaned, tmp_kept = pg.tmp_clean(tmp_found, tmp_before, tmp_after, tmp_window)
        print("%s: tmp_escapes=%d exact=%d shell=%d cleaned=%d not_removed=%s" % (
            entry.get("id", work.name), len(tmp_found), sum(c["exact"] for c in tmp_found),
            sum(not c["exact"] for c in tmp_found), len(tmp_cleaned), json.dumps(tmp_kept)), flush=True)
        heartbeat.set_phase("terminal_grading")
        with sg.snapshot(work, private, boundary=final_boundary_actual) as snap:
            modified = (True if snap is None else sg.tampered(snap.path, entry["protected"], entry["prepared"],
                                                              entry["lang"]))
            failing = None
            if snap is not None and not modified:
                final_result = sg.grade(entry["lang"], snap.path, entry["test"], private, guard=guard, keep=keep,
                                        seq=next_seq(), boundary=final_boundary_actual, final=True)
                resources["grader_mem_kill"] |= final_result.grader_mem_kill
                resources["grader_oom"] |= final_result.grader_oom
                failing = final_result.failing({tuple(x) for x in entry["leaves"]})
            if final_result is None:
                # No final grade ran (protected input tampered / unsnapshottable): still leave a typed final receipt.
                sg.write_receipt(keep, next_seq(), final_boundary_actual, True, "tampered")
            gate.terminal(None, (final_boundary_actual, failing, failing is not None, modified))
        if cancelled:
            ctx["cancelled"] = True
        termination_out = dict(termination)
        result = dict(
            gate=gate.report(),
            request_usage=gate.request_usage,
            nonconv_kind=gate.primary,
            converged=gate.primary is None,
            nonconv_flags=[f for f in tg.PRECEDENCE if f in gate.flags],
            test_modified=modified,
            passed=bool(failing == 0 and not modified),
            rc=proc.returncode,
            wall_s=time.monotonic() - started,
            export=export,
            transcript=transcript,
            prompt_date=prompt_date,
            prompt_date_real=prompt_date_real,
            prompt_date_update_removed=None if date_summary is None else date_summary["update_removed"],
            session_id=stream.session_id,
            requests_observed=len(stream.starts),
            silence_observations=observations,
            termination=termination_out,
            reconciliation=reconciliation,
            client_exit_hang=exit_hang,
            torn_tail=stream.torn_tail,
            event_types_seen=stream.event_types_seen,
            evidence=paths,
            mem_kills=t1._link_mem_kills(guard.mem_kills, stream),
            orphans_unattributed=guard.orphans_unattributed,
            tmp_escapes=tmp_found,
            tmp_cleaned=tmp_cleaned,
            tmp_not_removed=tmp_kept,
            tmp_window=list(tmp_window),
            grade_reports=t1.grade_reports(keep, portable),
            reconciled=rec,
            normalized_events=adapter.events(stream),
            tool_windows=adapter.tool_windows(stream),
            **resources,
        )
        if adapter.account_compaction:
            result["compaction"] = dict(
                count=rec.compaction_count, completion_tokens=rec.compaction_completion_tokens,
                requests=list(rec.compaction),
                receipts=rec.extra.get("compaction_receipts"),
                accounting_complete=rec.extra.get("compaction_accounting_complete"))
        if adapter.watchdog_enabled:
            result["shell_watchdog"] = dict(
                limit_s=dog.limit_s if dog else None, kills=list(dog.kills) if dog else [],
                window_overruns=list(dog.window_overruns) if dog else [])
        return result
    finally:
        try:
            with pg.defer_signals():
                try:
                    if client_launch_attempted and (sys.exc_info()[0] is not None or proc and proc.poll() is None):
                        terminate_client()
                finally:
                    stop.set()
                    if ingester:
                        ingester.join(5)
                    if sys.exc_info()[0] is not None:
                        try:
                            guard.kill_role("grader")
                        except Exception:  # noqa: BLE001 — cleanup() below re-audits every tracked identity and
                            pass           # fails closed (survivors/uncertain); it must still run (C151 R18)
                    try:
                        heartbeat.set_phase("terminal_grading")
                        if worker.thread.is_alive():
                            worker.finish()
                    finally:
                        heartbeat.set_phase("cleanup")
                        try:
                            guard.cleanup()
                        finally:
                            status = getattr(guard, "status", None)
                            if ctx is not None and status is not None:
                                ctx["cleanup_status"] = status()
                            if ctx is not None:
                                ctx["grade_reports"] = t1.grade_reports(keep, portable)
                        if proc and proc.poll() is None:
                            proc.wait(timeout=10)
        finally:
            heartbeat.close()


# ---------------------------------------------------------------- the probe main
def print_identity(p, adapter, a):
    """`--print-identity`: the arm probe's provenance identity as JSON; never touches the router or a worker."""
    selection = adapter.selection(a.agent_system_file)
    universe_path = a.universe or REPO / "benchmark/m62/universe.json"
    _, universe_sha = universe_preflight.load(universe_path)
    binary, exists = adapter.identity_binary()
    ident = adapter.identity(selection=selection, universe_sha=universe_sha, version=adapter.pinned_version,
                             binary=binary, inject=getattr(a, "tg1_inject", None))
    out = dict(
        arm=adapter.arm_id,
        scaffold=ident["scaffold"],
        scaffold_policy_sha256=ident["scaffold_policy_sha256"],
        probe_code_sha256=ident["probe_code_sha256"],
        toolchain=ident["policy"]["toolchain"],
        **adapter.identity_summary(ident, exists),
    )
    try:
        polyglot_sha = p._polyglot_sha(p._polyglot_root())
    except SystemExit:
        polyglot_sha = None
    out["polyglot_sha"] = polyglot_sha
    if exists and polyglot_sha:
        full = {**ident, **selection["fields"], "polyglot_sha": polyglot_sha,
                "sampling_profile": getattr(a, "sampling_profile", None) or "deployed"}
        out["generation_identity_sha256"] = aa.arm_generation_sha256(adapter.arm_id, full, adapter.GENERATION_FIELDS)
    else:
        out["generation_identity_sha256"] = None      # needs the pinned binary and the polyglot corpus
    print(json.dumps(out, sort_keys=True), flush=True)
    return 0


def main(p, adapter, a):
    forbidden = {"--tick-s", "--first-write-tokens", "--hard-ceiling-s", "--stall-ticks", "--loop-repeats", "--poll-s"}
    if any(s.split("=", 1)[0] in forbidden for s in sys.argv[1:]):
        sys.exit("REFUSED: tg1 does not accept legacy time-gate flags")
    if a.lang not in ("python", "go") or a.rerun_of or a.rerun_index or a.extra_deny_file:
        sys.exit("REFUSED: tg1 supports eligible Python/Go single-pass items only")
    names = [s.strip() for s in a.items.split(",") if s.strip()]
    if not names or len(names) != len(set(names)) or any(Path(n).name != n or n in (".", "..") for n in names):
        sys.exit("REFUSED: invalid or duplicate items")
    if a.limit is not None:
        if a.limit <= 0:
            sys.exit("REFUSED: limit must be positive")
        names = names[: a.limit]
    if a.sampling_profile not in (None, "deployed"):
        sys.exit("REFUSED: --sampling-profile accepts only 'deployed'")
    frozen = getattr(a, "frozen_prompt_date", None)
    if frozen is None:
        sys.exit("REFUSED: --frozen-prompt-date is required (P364: the date the model is shown; never defaulted to today)")
    if not datefreeze.valid(frozen):
        sys.exit("REFUSED: --frozen-prompt-date must be 'Www Mmm DD YYYY' (e.g. 'Sat Oct 17 2026')")
    kind = a.tg1_inject
    if kind:
        if kind not in t1.INJECT_POLICY:
            sys.exit("REFUSED: unknown --tg1-inject kind")
        if len(a.items.split(",")) != 1 or len(names) != 1 or a.limit not in (None, 1):
            sys.exit("REFUSED: --tg1-inject runs exactly one item")
        if not a.expect_items:
            sys.exit("REFUSED: --tg1-inject requires --expect-items")
        workdir = p._stack_workdir().resolve()
        if not a.out or not Path(a.out).resolve().is_relative_to((workdir / "m62/inject").resolve()):
            sys.exit("REFUSED: --tg1-inject requires --out under $STACK_WORKDIR/m62/inject/")
    for flag in ("cancel_file", "manifest_ack"):
        path = getattr(a, flag)
        if path and Path(path).exists():
            sys.exit("REFUSED: stale --" + flag.replace("_", "-") + " file already exists")
    original_registry = os.environ.get("MLX_SERVE_CONFIG")
    try:
        return _main(p, adapter, a, names)
    except aa.ArmRefused as exc:
        sys.exit("REFUSED: " + p._scrub_error(exc))
    except (tg.TransportAbort, OSError, ValueError) as exc:
        sys.exit("REFUSED: " + p._scrub_error(exc))
    finally:
        if original_registry is None:
            os.environ.pop("MLX_SERVE_CONFIG", None)
        else:
            os.environ["MLX_SERVE_CONFIG"] = original_registry


def _main(p, adapter, a, names):
    kind = a.tg1_inject
    ctx = dict(cleanup_status=dict(t1.CLEAN_STATUS))
    cancel = (lambda: Path(a.cancel_file).exists()) if a.cancel_file else None
    selection = adapter.selection(a.agent_system_file)          # an arm that needs a missing service refuses HERE
    if kind:
        selection["fields"] = {**selection["fields"], "scaffold": adapter.label + "-inject:" + kind}
    tool0 = toolchain.current()          # P23: lock + interpreter + grader image; a missing one refuses before any spawn
    model, base = adapter.declared_model(selection, a.model)
    router = provenance.assert_served_config(base, env={})
    os.environ["MLX_SERVE_CONFIG"] = str(provenance.paths.registry_path().resolve())
    before = t1.worker_identity(p, a.model, router)
    arm_fp, arm_sha = t1.arm_identity_of(p, a.model, router)       # P16: the effective worker fingerprint; unknown refuses
    limit = t1.validate_worker(model, t1.worker_json("health"), t1.worker_json("metrics"))
    universe_path = a.universe or REPO / "benchmark/m62/universe.json"
    universe, universe_sha = universe_preflight.load(universe_path)
    for name in names:
        item = a.lang + "/" + name
        if item == "go/counter" or item not in universe["items"]:
            raise tg.TransportAbort("item absent/refused in universe: " + item)
    workdir = p._stack_workdir().resolve()
    binary = adapter.require_binary()
    receipt = adapter.preflight(path=a.a4_v2_receipt, router=router, limit=a.limit, model=a.model,
                                exe_sha=p._sha_of(binary),
                                carrier_sha=selection["fields"]["opencode_bench_config_sha256"])
    run_id = time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    run_dir = adapter.make_run_dir(workdir, run_id, selection)
    private = run_dir / "grading-private"
    private.mkdir()
    frozen = a.frozen_prompt_date
    out = Path(a.out) if a.out else REPO / "benchmark/results" / a.model / (adapter.label + ".jsonl")
    evidence_dir = adapter.evidence_root(workdir) / a.model / (out.stem + "." + run_id)

    def check_env(env, overlay):
        adapter.verify_env(env, run_dir, selection, overlay)
        if universe_preflight.load(universe_path)[1] != universe_sha:
            raise tg.TransportAbort("tg1 input provenance drift")
        try:
            toolchain.verify(tool0)
        except toolchain.ToolchainError as exc:
            raise tg.TransportAbort("tg1 " + str(exc)) from exc

    if cancel is not None and cancel():
        raise t1.RunnerCancelled()      # C147 §3a: before the first spawn of any kind
    with p._scratch_dir("tg1-discovery") as scratch:
        p._git_init_scratch(scratch)
        overlay = p._seed_overlay(a.model, p._item_seed(a.lang + "/" + names[0], a.seed_base))
        # discovery runs no session, so the plugin never writes this file (it is named only to satisfy the env contract)
        env = adapter.build_env(run_dir, scratch, overlay, receipts=evidence_dir / "discovery.datefreeze.jsonl",
                                frozen_date=frozen)
        p._fresh_tmpdir(env)
        check_env(env, overlay)
        with t1._DiscoveryGuard(p, [scratch, env["TMPDIR"]], (router.get("pid"), before["pid"]), ctx) as dg:
            version, destination = adapter.discover(scratch, env, model=a.model, run_dir=run_dir, binary=binary,
                                                    overlay=overlay, runner=dg.run_grader, check_version=True)
        provenance.assert_served_config_unchanged(router, destination)
    shutil.rmtree(env["TMPDIR"])
    ident = adapter.identity(selection=selection, universe_sha=universe_sha, version=version, binary=binary, inject=kind)
    if ident["policy"]["toolchain"] != tool0:
        raise tg.TransportAbort("tg1 toolchain drift: changed while the probe started")
    snapshot = adapter.snapshot()
    ident.update(
        seed_base=a.seed_base,
        lang=a.lang,
        frozen_prompt_date=frozen,          # P364: chain metadata and resume identity; NOT in the generation composite
        polyglot_sha=p._polyglot_sha(p._polyglot_root()),
        a4_v2_pass=bool(receipt),
        **selection["fields"],
    )
    ident["sampling_profile"] = a.sampling_profile        # a present None is a value (the composite requires the key)
    ident["generation_identity_sha256"] = aa.arm_generation_sha256(adapter.arm_id, ident, adapter.GENERATION_FIELDS)
    ident.update(arm_identity_sha256=arm_sha, arm_identity=arm_fp, arm=adapter.arm_id,
                 epoch_id=getattr(a, "epoch_id", None), snapshot_sha256=snapshot.sha256,
                 snapshot_complete=snapshot.complete, arm_config=adapter.manifest_fields())
    mp = out.with_suffix(".manifest.json")
    rows = pg.load_rows(out)
    if rows:
        try:
            old = json.loads(mp.read_text())
        except (ValueError, OSError) as exc:
            raise tg.TransportAbort("rows have no intact manifest") from exc
        if old.get("transport_abort"):
            raise tg.TransportAbort("tg1 resume refused: the manifest records a transport abort")
        if any(old.get("runtime", {}).get(key) != value for key, value in ident.items()):
            raise tg.TransportAbort("tg1 resume provenance differs")
        if old.get("served_config_drift") or old.get("git", {}).get("serving_path") != provenance._git_shas().get(
                "serving_path"):
            raise tg.TransportAbort("tg1 resume serving identity differs")
        pg.require_identity(old.get("worker"), before)
        for row in rows:
            pg.require_identity(row.get("worker_after"), before)
        if len({r["id"] for r in rows}) != len(rows):
            raise tg.TransportAbort("duplicate rows")
    man = provenance.gather(a.model, profile="deployed", runtime=ident, router=router)
    man.update(worker=before, run_id=run_id)

    def save_manifest():
        pg.atomic_write(mp, p._scrub_pii(json.dumps(man, indent=2)).encode())

    save_manifest()
    try:
        if a.manifest_ack:
            t1._wait_for_ack(a.manifest_ack, cancel)
        for name in names:
            item = a.lang + "/" + name
            if any(r["id"] == item for r in rows):
                continue
            if cancel is not None and cancel():
                raise t1.RunnerCancelled()
            ctx.update(id=item)
            current = t1.worker_identity(p, a.model, router)
            pg.require_identity(before, current)
            source = p._polyglot_root() / a.lang / "exercises/practice" / name
            entry = {**universe["items"][item], "lang": a.lang, "id": item}
            with p._item_scratch_dir(name) as scratch:
                work = scratch / name
                p._prepare(source, work)
                p._git_init_scratch(work)
                p._freeze_mtimes(work)
                if sg.manifest(work) != entry["prepared"]:
                    raise tg.TransportAbort("prepared exercise differs from frozen universe")
                overlay = p._seed_overlay(a.model, p._item_seed(item, a.seed_base))
                evidence = evidence_dir / (a.lang + "__" + name)
                env = adapter.build_env(run_dir, work, overlay, receipts=evidence.with_suffix(".datefreeze.jsonl"),
                                        frozen_date=frozen)
                p._fresh_tmpdir(env)
                check_env(env, overlay)
                with t1._DiscoveryGuard(p, [work, env["TMPDIR"]], (router.get("pid"), before["pid"]), ctx) as dg:
                    _, destination = adapter.discover(work, env, model=a.model, run_dir=run_dir, binary=binary,
                                                      overlay=overlay, runner=dg.run_grader)
                provenance.assert_served_config_unchanged(router, destination)
                prompt = (
                    f'Implement the solution in {entry["solution"]} so that the tests in {entry["test"]} pass. '
                    "The specification is in .docs/instructions.md — read it first. "
                    f'Do NOT modify {entry["test"]}. Do not create new files unless required by the spec.'
                )
                if kind:
                    prompt += " " + t1.INJECT_ADDENDA[kind]
                initial = (work / entry["solution"]).read_bytes()
                result = run_item(
                    p, adapter, model=a.model, work=work, prompt=prompt, env=env, binary=binary, evidence=evidence,
                    entry=entry, limit=limit, private=private, router=router, base=base,
                    protected_pids=(before["pid"],), policy=t1.effective_policy(kind), cancel=cancel, ctx=ctx,
                    frozen_date=frozen, gate_overrides=getattr(a, "gate_overrides", None))
                after = t1.worker_identity(p, a.model, router)
                pg.require_identity(before, after)
                check_env(env, overlay)
                provenance.assert_served_config_unchanged(router, base)
                export = result.pop("export")
                transcript = result.pop("transcript")
                artifacts = result.pop("evidence")
                rc = result.pop("rc")
                adapter.observed = dict(events=result.pop("normalized_events"), reconciliation=result.pop("reconciled"),
                                        tool_windows=result.pop("tool_windows"))
                changed = (work / entry["solution"]).is_file() and (work / entry["solution"]).read_bytes() != initial
                # M59/M61 rule kept: an untouched solution fails (go/ledger, go/markdown stubs pass every test).
                passed = result.pop("passed") and changed
                row = dict(
                    **adapter.row_identity_fields(),
                    **selection["fields"],
                    id=item,
                    model=a.model,
                    sample=0,
                    passed=passed,
                    acc=int(passed),
                    file_changed=changed,
                    **result,
                    worker_before=current,
                    worker_after=after,
                    stop_reason=result["gate"]["stop_reason"] or "completed",
                    **adapter.row_fields(version=version, rc=rc, artifacts=artifacts, sha_of=p._sha_of,
                                         portable=p._portable),
                    generation_identity_sha256=ident["generation_identity_sha256"],
                    arm_identity_sha256=ident["arm_identity_sha256"],
                    **adapter.metrics(p, transcript, export),
                    **p._seed_row_fields(item, a.seed_base,
                                         hashlib.sha256(env["OPENCODE_CONFIG_CONTENT"].encode()).hexdigest()),
                    arm=adapter.arm_id,
                    epoch_id=getattr(a, "epoch_id", None),
                    snapshot_sha256=snapshot.sha256,
                )
                rows.append(json.loads(p._scrub_pii(json.dumps(row))))
                pg.atomic_write(out, ("".join(json.dumps(r) + "\n" for r in rows)).encode())
                print(f'{item}: passed={passed} nonconv={row["nonconv_kind"]}', flush=True)
        if a.expect_items:
            pg.expect_items(rows, [s.strip() for s in a.expect_items.split(",")])
    except BaseException as exc:
        status = ctx.get("cleanup_status")
        man["cleanup_status"] = status          # the receipt location (top level) on EVERY abort path
        stamp = dict(error=p._scrub_error(exc), cleanup_status=status, grade_reports=ctx.get("grade_reports", []),
                     termination=ctx.get("termination"))
        cause = adapter.transport_cause(exc)
        if cause is not None:
            stamp["cause"] = cause                # spec 8.3: the incident class the chain retries on
        man["transport_abort"] = stamp
        if isinstance(exc, t1.RunnerCancelled) and exc.item:
            man["cancelled_item"] = {**exc.item, "cleanup_status": exc.item.get("cleanup_status") or status}
        save_manifest()
        raise
    finally:
        try:
            man["router_exit"] = provenance.assert_served_config_unchanged(router, base)
        except provenance.ServedConfigError as exc:
            man["served_config_drift"] = dict(error=p._scrub_error(exc))
            save_manifest()
            raise
        save_manifest()
    return 0
