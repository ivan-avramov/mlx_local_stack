"""THE item core (P371, plan 3.1 / 3.4): one `run_item`, one probe `main` and one `print_identity` for every
configuration (tg1, M64 `oc`, tg2 later).

Everything configuration-specific is INJECTED by the probe entry (entry -> core), never imported here (dependency
rule): the host module `p` (checked with `host.require_host`), the `PolicyTemplate` (static generation policy), the
`EvidencePolicy`, the `ArmAdapter` (client), the `Corpus` (items, prompt, grade, tamper, final tree) and an optional
worker-receipt source. This module imports no corpus, adapter or client module.

The library parts of the pre-P371 tg1 loop live here: `GradeWorker`, `PhaseHeartbeat`, the worker / router checks,
`RunnerCancelled`, `_DiscoveryGuard`, `grade_reports`, `_link_mem_kills`. Phase 2a: worker receipts stay `absent`
(a `required` policy refuses before any spawn), the item barrier, the A4 watchdog receipts and the A2 compaction
changes are phase 2b; today's M64 watchdog / compaction code paths run when the generation policy turns them on."""
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
import urllib.request
import uuid

from . import arm_adapter as aa
from . import arm_identity
from . import arm_watchdog
from . import host as hostmod
from . import item_barrier as ib
from . import proc_guard as pg
from . import provenance
from . import rowschema
from . import run_config as rc
from . import token_turn_gate as tg
from . import toolchain
from . import worker_receipts as wr

REPO = Path(__file__).resolve().parents[2]
WATCHDOG_TICK_S = 1.0
GRADE_JOIN_OVERHEAD_S = rc.GRADE_JOIN_OVERHEAD_S
HEARTBEAT_INTERVAL_S = 30
GRACEFUL_CLIENT_S = 15
ACK_TIMEOUT_S = 300
ACK_POLL_S = 0.5
CLEAN_STATUS = dict(survivors=[], containers_remaining=[], uncertain=False, orphans_unattributed=[], unknown=[],
                    completed=True)
DEFAULT_UNIVERSE = REPO / "benchmark/m62/universe.json"


def effective_policy(kind=None):
    """(gate, hygiene) dicts in force: the campaign constants, with the inject kind's single override applied (C147 2)."""
    gate, hygiene = dict(tg.POLICY), dict(pg.POLICY)
    if kind is not None:
        gate.update(rc.INJECT_POLICY[kind]["gate"])
        hygiene.update(rc.INJECT_POLICY[kind]["hygiene"])
    return gate, hygiene


class RunnerCancelled(tg.TransportAbort):
    """The runner's cooperative cancel was honoured; carries the evidence for the manifest's `cancelled_item`."""

    def __init__(self, message="cancelled by runner", item=None):
        super().__init__(message)
        self.item = item or {}


def grade_reports(keep, portable=None):
    """Hashed report index of every grade taken for an item, from the `seq-*/index.json` files (C147 section 5)."""
    keep = Path(keep)
    portable = portable or str
    reports = []
    if not keep.is_dir():
        return reports
    for directory in sorted(d for d in keep.iterdir() if d.is_dir() and d.name.startswith("seq-")):
        try:
            seq = int(directory.name.split("-", 1)[1])
        except ValueError:
            continue
        try:
            doc = json.loads((directory / "index.json").read_text())
            artifacts = {
                name: dict(path=portable(str(keep / meta["path"])), sha256=meta["sha256"])
                for name, meta in doc["artifacts"].items()
            }
            reports.append(dict(boundary=doc["boundary"], seq=doc["seq"], final=doc["final"],
                                outcome=doc["outcome"], artifacts=artifacts))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            reports.append(dict(boundary=None, seq=seq, final=None, outcome="unreadable_index", artifacts={}))
    return sorted(reports, key=lambda r: r["seq"])


class PhaseHeartbeat:
    """Keep reporting while the main thread waits for cancellation or grading."""

    def __init__(self, gate, lock, started, *, interval=None):
        self.gate, self.lock, self.started = gate, lock, started
        self.interval = HEARTBEAT_INTERVAL_S if interval is None else interval
        self.phase = "client"
        self.report = {}
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._run, name="m62-heartbeat", daemon=True)

    def start(self):
        self.thread.start()

    def set_phase(self, phase):
        self.phase = phase

    def _run(self):
        while not self.done.wait(self.interval):
            # A slow main-thread operation must not block the heartbeat.
            if self.lock.acquire(blocking=False):
                try:
                    self.report = self.gate.report()
                finally:
                    self.lock.release()
            usage = self.gate.request_usage
            last_prompt = usage[-1][2] if usage else 0
            report = {**self.report, "last_prompt_tokens": last_prompt}
            print(json.dumps(dict(m62_watch=report, last_prompt_tokens=last_prompt, phase=self.phase,
                                  elapsed_s=time.monotonic() - self.started)), flush=True)

    def close(self):
        self.done.set()
        self.thread.join(5)


def grade_join_timeout_s(timeouts):
    """Grader timeouts are per grade; a terminal drain may hold the active grade plus one queued capture. `timeouts`
    is the corpus identity's `grader_timeout_s` (the core knows no grader)."""
    return 2 * max(timeouts.values()) + GRADE_JOIN_OVERHEAD_S


class GradeWorker:
    """One grader, one coalesced capture; ingestion never waits on a grade. `grade(snap) -> (failing, tampered)`."""

    def __init__(self, gate, lock, work, private, grade, join_timeout_s, *, corpus):
        self.corpus = corpus
        self.gate = gate
        self.lock = lock
        self.work = work
        self.private = private
        self.grade_fn = grade
        self.join_timeout_s = join_timeout_s
        self.condition = threading.Condition(lock)
        self.queued = None
        self.closed = False
        self.failure = None
        self.last_manifest = None
        self.thread = threading.Thread(target=self._run, name="m62-grader", daemon=True)

    def start(self):
        self.thread.start()

    def notify(self, boundary):
        with self.condition:
            try:
                current = self.corpus.manifest(self.work)
            except (OSError, ValueError):
                current = None
            if current is not None and current == self.last_manifest:
                return
            if self.queued is not None:
                # Preserve a capture already in the threshold's frozen wait cohort.
                if self.gate.stall_wait is not None and self.queued in self.gate.stall_wait:
                    return
                self.gate.pending.discard(self.queued)
            self.queued = boundary
            self.gate.on_capture(boundary)
            self.condition.notify()

    def _run(self):
        try:
            while True:
                with self.condition:
                    self.condition.wait_for(
                        lambda: self.queued is not None or self.closed
                    )
                    if self.queued is None:
                        return
                    queued = self.queued
                    self.gate.pending.discard(queued)
                    if self.gate.stop_reason in ("looping", "hard_ceiling"):
                        self.queued = None
                        continue
                    boundary = len(self.gate.request_usage)
                    self.gate.on_capture(boundary)
                    if self.gate.stall_wait is not None and queued in self.gate.stall_wait:
                        self.gate.stall_wait.remove(queued)
                        self.gate.stall_wait.add(boundary)
                    self.queued = None
                # Capture began at the recorded completed-request observation, not an atomic step.
                with self.corpus.snapshot(self.work, self.private, boundary) as snap:
                    failing = None
                    tampered = False
                    if snap is not None and snap.manifest != self.last_manifest:
                        failing, tampered = self.grade_fn(snap)
                    with self.lock:
                        if snap is not None and failing is not None and not tampered:
                            self.last_manifest = snap.manifest
                        self.gate.on_grade(boundary, failing, failing is not None, tampered)
        except BaseException as exc:
            self.failure = exc

    def check(self):
        if self.failure or (self.thread.ident is not None and not self.closed and not self.thread.is_alive()):
            raise tg.TransportAbort(
                "grading worker failed: " + str(self.failure)
            ) from self.failure

    def finish(self):
        with self.condition:
            self.closed = True
            self.condition.notify()
        self.thread.join(self.join_timeout_s)
        if self.thread.is_alive():
            raise tg.TransportAbort(
                "grading worker did not finish within grader timeout"
            )
        self.check()


def validate_worker(model, health, metrics, budgets=None):
    """The declared model carries the policy's budgets and the worker's configured context equals the declared one."""
    budgets = rc.DEFAULT_BUDGETS if budgets is None else budgets
    body = model.get("body", {})
    if body.get("thinking_budget") != budgets["thinking_budget"] or body.get("max_tokens") != budgets["max_tokens"]:
        raise tg.TransportAbort(
            "tg1 requires thinking_budget=%d and max_tokens=%d" % (budgets["thinking_budget"], budgets["max_tokens"])
        )
    limit = health.get("configured_context_limit")
    if type(limit) is not int or limit != model.get("limit", {}).get("context"):
        raise tg.TransportAbort("worker configured_context_limit differs from carrier")
    pg.in_flight(metrics)
    return limit


def worker_json(endpoint):
    doc = provenance.yaml.safe_load(provenance.paths.registry_path().read_text())
    url = f'http://127.0.0.1:{int(doc["mlx_port"])}/{endpoint}'
    headers = {}
    key = os.environ.get("MLX_VLM_SERVER_API_KEY")
    if key:
        headers["Authorization"] = "Bearer " + key
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=10
        ) as response:
            return json.load(response)
    except Exception as exc:
        raise tg.TransportAbort("unreadable worker " + endpoint) from exc


def http_receipt_source():
    """F2: the production `HttpReceiptSource`, pointed at the registry's worker (the control endpoint's host, like
    `worker_json`), with the worker's bearer key when one is configured."""
    doc = provenance.yaml.safe_load(provenance.paths.registry_path().read_text())
    return wr.HttpReceiptSource(f'http://127.0.0.1:{int(doc["mlx_port"])}', api_key=os.environ.get("MLX_VLM_SERVER_API_KEY") or None)


def worker_identity(p, model, router):
    import psutil

    observed = p._worker_load_identity(model, router)
    if not observed:
        raise tg.TransportAbort("worker identity unavailable")
    try:
        observed.update(
            create_time=pg.start_time(psutil.Process(observed["pid"])),   # C151
            registry_sha256=hashlib.sha256(
                provenance.paths.registry_path().read_bytes()
            ).hexdigest(),
        )
    except (OSError, psutil.Error) as exc:
        raise tg.TransportAbort("worker creation time unavailable") from exc
    pg.require_identity(observed, observed)
    return observed


def arm_identity_of(p, model, router):
    """(fingerprint, sha256) of the observed worker (`bench.arm_identity.observe`); a seam for tests, like
    `worker_identity`."""
    return arm_identity.observe(model, router)


def _link_mem_kills(mem_kills, stream):
    """Resolve each model-process memory kill to the shell `tool_use` of its carrying request.

    The killed call's own `tool_use` event is published after the kill (the tool then errors), so linkage is
    resolved from the stream once it is drained: among shell calls of request `carrying_request`, the one whose
    command contains an argv token of the killed process; a single shell call of that request is taken as is."""
    linked = []
    for kill in mem_kills:
        entry = dict(kill)
        request = entry.get("carrying_request")
        candidates = [(pid, command) for (j, pid, tool, command) in getattr(stream, "tool_events", [])
                      if tool == "shell" and j == request]
        chosen = None
        if len(candidates) == 1:
            chosen = candidates[0][0]
        elif candidates:
            tokens = [t for t in entry.get("argv", []) if len(t) >= 6]
            for pid, command in candidates:
                if any(t in command for t in tokens):
                    chosen = pid
                    break
        entry["tool_call_id"] = chosen
        linked.append(entry)
    return linked


class _DiscoveryGuard:
    """A short-lived guard for a discovery spawn; its cleanup outcome lands in `ctx["cleanup_status"]`."""

    def __init__(self, p, roots, protected, ctx):
        self.ctx = ctx
        self.guard = pg.ProcessGuard(roots, protected_pids=protected,
                                     scrub=p._scrub_pii if p is not None else None)

    def __enter__(self):
        return self.guard.__enter__()

    def __exit__(self, *exc):
        try:
            return self.guard.__exit__(*exc)
        finally:
            status = getattr(self.guard, "status", None)
            if status is not None:
                self.ctx["cleanup_status"] = status()


def _wait_for_ack(path, cancel):
    deadline = time.monotonic() + ACK_TIMEOUT_S
    while not Path(path).exists():
        if cancel is not None and cancel():
            raise RunnerCancelled()
        if time.monotonic() >= deadline:
            raise tg.TransportAbort("manifest not acknowledged")
        time.sleep(ACK_POLL_S)


# ---------------------------------------------------------------- the item
def run_item(p, adapter, *, ctx=None, **kwargs):
    """Run one item. `ctx` (a dict) receives `cleanup_status` on EVERY exit path; a cooperative cancel honoured during
    generation raises `RunnerCancelled` after the full terminal path, carrying the item's evidence."""
    ctx = {} if ctx is None else ctx
    result = _run_item(p, adapter, ctx=ctx, **kwargs)
    cancel = kwargs.get("cancel")
    # C147 section 3: a cancel that landed during the terminal phases is honoured here, BEFORE the row is committed.
    if ctx.get("cancelled") or (cancel is not None and cancel()):
        evidence = result["evidence"]
        raise RunnerCancelled(item=dict(
            id=ctx.get("id"),
            evidence_sha256={k: p._sha_of(v) for k, v in evidence.items()} if p else {},
            grade_reports=result["grade_reports"],
            reconciliation=result["reconciliation"],
            termination=result["termination"],
            cleanup_status=ctx.get("cleanup_status"),
        ))
    return result


def _run_item(p, adapter, *, corpus, prepared, model, prompt, env, binary, evidence, limit, private, router, base,
              protected_pids=(), policy=None, cancel=None, ctx=None, frozen_date=None, gate_overrides=None,
              watchdog=None, compaction=False, join_timeout_s, receipts=None, attempt=None, header_sent=False,
              controls=None, expected_worker=None):
    work, entry = prepared.work, prepared.entry
    gate_policy, hygiene = policy if policy is not None else effective_policy()
    if gate_overrides:
        gate_policy = {**gate_policy, **gate_overrides}
    watchdog_on = bool(watchdog) and watchdog.get("mode") == "on"
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
        ctx.pop("receipt_tokens", None)          # per item: an earlier item's fence totals never reach a later abort stamp
    silence_observer = pg.SilenceObserver()
    exit_hang = False
    cancelled = False
    resources = dict(grader_mem_kill=False, grader_oom=False)
    paths = {key: evidence.with_suffix(suffix) for key, suffix in adapter.evidence_suffixes().items()
             if key != adapter.date_receipt_key or frozen_date is not None}
    adapter.verify_item_env(env, paths, frozen_date)
    if ctx is not None:
        ctx["evidence_paths"] = paths            # F6: an abort before the row commit stamps this item's evidence paths + shas
    for path in paths.values():
        pg.reserve_evidence(path)
    if Path(str(evidence) + ".final_tree").exists():
        raise tg.TransportAbort("immutable evidence path exists: " + Path(str(evidence) + ".final_tree").name)
    receipts_path = Path(str(evidence) + ".receipts.json")
    if receipts is not None and receipts_path.exists():
        raise tg.TransportAbort("immutable evidence path exists: " + receipts_path.name)
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
        if corpus.tampered(snap, prepared):
            return None, True
        outcome = corpus.grade(snap, prepared, private, guard, keep, next_seq(), snap.boundary, False)
        resources["grader_mem_kill"] |= outcome.resources["grader_mem_kill"]
        resources["grader_oom"] |= outcome.resources["grader_oom"]
        return outcome.failing, False

    worker = GradeWorker(gate, lock, work, private, grade, join_timeout_s=join_timeout_s, corpus=corpus)
    stream = adapter.new_stream(gate, worker.notify)
    stream.base_url = base
    if attempt is None:
        attempt = wr.AttemptContext.make(entry.get("id", work.name), 1)       # a direct run_item caller: attempt 1
    adapter.bind_stream(stream, paths=paths, attempt=attempt)
    proc = None
    client_launch_attempted = False
    ingester = None
    killed = False
    cancellation_attempted = False
    heartbeat = PhaseHeartbeat(gate, lock, started)
    reconciliation = None
    mark = None
    fence_attempted = False
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
                before = worker_json("metrics")
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
                killed_entries.extend(adapter.cancel(guard, GRACEFUL_CLIENT_S, before_signal=capture_cutoff,
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
            last_metrics["value"] = worker_json("metrics")
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
            if receipts is not None:
                # A3 / R3: the start mark is taken IMMEDIATELY before the spawn; it must name the worker the probe observed
                mark = receipts.start(attempt)
                if expected_worker is not None and mark.worker != expected_worker:
                    raise wr.WorkerMismatch("the receipt endpoint's worker is not the one the probe observed")
            proc = guard.spawn(adapter.command(binary, model, prompt), cwd=work, env=env, stdin=subprocess.DEVNULL,
                               stdout=stdout, stderr=stderr)
            if watchdog_on:
                dog = arm_watchdog.ShellWatchdog.for_client(proc.pid, limit_s=watchdog["limit_s"],
                                                            grace_s=watchdog["grace_s"])
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
                    dog.tick()
                    if dog.exec_timeout:                          # a kill OR a completed window past the limit (spec 5.4)
                        with lock:
                            gate.flags.add("exec_timeout")        # the row gets the flag; the client sees the tool fail
                with lock:
                    if guard.client_resource:
                        gate.stop("client_resource")
                    if (now - stream.last_event >= pg.POLICY["silence_s"]
                            and now - last_silence >= pg.POLICY["silence_sample_s"]):
                        metrics = worker_json("metrics")
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
                        # Cooperative cancel (C147 section 3c): a gate stop decided at the same tick takes precedence.
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
        if dog is not None:
            # A4: one final watchdog tick after the client exit, before reconcile (a window that completed or overran after
            # the last in-loop tick; a corrupt receipt file aborts here too)
            heartbeat.set_phase("final_watchdog_tick")
            with lock:
                dog.set_windows(adapter.tool_windows(stream, final=True))
            dog.tick()
            if dog.exec_timeout:
                gate.flags.add("exec_timeout")
        fence = owned = receipts_sha = None
        if receipts is not None:
            heartbeat.set_phase("receipt_fence")
            fence_attempted = True
            fence = receipts.fence(attempt)                 # after the client exit and the drain: every admitted request ended
            ctx["receipt_tokens"] = wr.fence_totals(mark, fence)       # reported in any abort stamp from here on
            receipts_sha = wr.write_receipts_file(receipts_path, attempt, mark, fence)    # the raw fenced set, even if the join aborts
            owned = wr.owned_receipts(mark, fence)
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
        if frozen_date is not None and adapter.date_receipt_key:
            # P364: every request of the item must have been masked: exact reconciliation, any mismatch aborts (no row).
            date_summary = adapter.receipts_reconcile(
                paths[adapter.date_receipt_key], frozen=frozen_date, session_id=stream.session_id,
                requests_observed=len(stream.starts), killed=bool(killed or guard.client_resource))
            adapter.merge_receipts(rec, date_summary)
        joined = None
        if receipts is not None:
            joined = wr.join(owned, adapter.request_classes(stream, transcript), supports_header=header_sent, ctx=attempt,
                             controls=controls, mark=mark, fence=fence, class_rules=adapter.receipt_class_rules)
        final_boundary_actual = len(gate.request_usage)
        if final_boundary != final_boundary_actual:
            gate.pending.discard(final_boundary)
            gate.pending.add(final_boundary_actual)
        # C147 section 4: /tmp escape diagnostic and exact-path cleanup, after the client is gone.
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
        with corpus.snapshot(work, private, final_boundary_actual) as snap:
            # A tampered / unsnapshottable tree runs no grader and still leaves a typed final receipt (the corpus).
            final = corpus.grade(snap, prepared, private, guard, keep, next_seq(), final_boundary_actual, True)
            resources["grader_mem_kill"] |= final.resources["grader_mem_kill"]
            resources["grader_oom"] |= final.resources["grader_oom"]
            modified, failing = final.tampered, final.failing
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
            mem_kills=_link_mem_kills(guard.mem_kills, stream),
            orphans_unattributed=guard.orphans_unattributed,
            tmp_escapes=tmp_found,
            tmp_cleaned=tmp_cleaned,
            tmp_not_removed=tmp_kept,
            tmp_window=list(tmp_window),
            grade_reports=grade_reports(keep, portable),
            reconciled=rec,
            normalized_events=adapter.events(stream),
            tool_windows=adapter.tool_windows(stream, final=True),
            **resources,
        )
        if compaction:
            result["compaction"] = dict(
                count=rec.compaction_count, completion_tokens=rec.compaction_completion_tokens,
                requests=list(rec.compaction),
                receipts=rec.extra.get("compaction_receipts"),
                accounting_complete=rec.extra.get("compaction_accounting_complete"),
                accounting="post_hoc")
        if joined is not None:
            result["receipts"] = dict(path=portable(receipts_path), sha256=receipts_sha)
            result["token_accounting"] = "receipts"
            if compaction:
                # A2 / P370: compaction tokens come from the worker's receipts when present (else post hoc from the export)
                result["compaction"].update(
                    export_completion_tokens=rec.compaction_completion_tokens, accounting="receipts",
                    completion_tokens=joined.by_class.get("compaction", {}).get("completion_tokens", 0))
        if compaction or joined is not None:
            gate_tokens = gate.output_tokens
            compaction_tokens = result["compaction"]["completion_tokens"] if compaction else 0
            result["task_tokens"] = dict(
                accounting="receipts" if joined is not None else "client",
                gate_completion_tokens=gate_tokens, compaction_completion_tokens=compaction_tokens,
                # F3 (review r1): receipt accounting makes the task total the worker's own (every task + compaction request it
                # served, a disconnected generation included); the gate's count stays beside it as `gate_completion_tokens`
                completion_tokens=(joined.task_tokens["completion_tokens"] if joined is not None
                                   else gate_tokens + compaction_tokens),
                receipts=None if joined is None else dict(joined.task_tokens, by_class=joined.by_class))
        if watchdog_on:
            result["shell_watchdog"] = dict(
                limit_s=dog.limit_s if dog else None, kills=list(dog.kills) if dog else [],
                window_overruns=list(dog.window_overruns) if dog else [])
        return result
    finally:
        if ctx is not None:
            ctx["gate_report"] = gate.report()           # spec 8.3: a failed attempt's tokens count toward its task
        try:
            with pg.defer_signals():
                try:
                    if client_launch_attempted and (sys.exc_info()[0] is not None or proc and proc.poll() is None):
                        terminate_client()
                    if receipts is not None and mark is not None and not fence_attempted and ctx is not None:
                        _abort_fence(receipts, attempt, mark, receipts_path, ctx, proc)
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
                                ctx["grade_reports"] = grade_reports(keep, portable)
                        if proc and proc.poll() is None:
                            proc.wait(timeout=10)
        finally:
            heartbeat.close()


def _abort_fence(receipts, attempt, mark, receipts_path, ctx, proc):
    """P371 3b / P378 (6): an abort, cancel or transport path that never reached the normal fence takes it NOW, once the
    client is gone, so a failed attempt's tokens are counted. Best effort: nothing here may mask the original error; the
    outcome (totals, or the fence's own error) lands in `ctx["receipt_tokens"]` for the abort stamp."""
    if proc is not None and proc.poll() is None:
        ctx["receipt_tokens"] = dict(fence_taken=False, fence_error="the client was still running; no fence taken")
        return
    try:
        fence = receipts.fence(attempt)
    except BaseException as exc:  # noqa: BLE001 — never masks the original error
        ctx["receipt_tokens"] = dict(fence_taken=False, fence_error=f"{type(exc).__name__}: {exc}"[:300])
        return
    try:
        ctx["receipt_tokens"] = wr.fence_totals(mark, fence)
    except BaseException as exc:  # noqa: BLE001
        ctx["receipt_tokens"] = dict(fence_taken=True, fence_error=f"{type(exc).__name__}: {exc}"[:300])
        return
    try:
        wr.write_receipts_file(receipts_path, attempt, mark, fence)
    except BaseException:  # noqa: BLE001 — evidence only
        pass


def _done_record(p, row, attempt, artifacts):
    """The `.done` barrier record: the row key and every evidence path with its sha256 (the chain hashes and indexes
    them before it decides: accept / re-run / block)."""
    record = dict(id=row["id"], attempt_id=attempt.attempt_id, passed=row["passed"], nonconv_kind=row["nonconv_kind"],
                  evidence={name: dict(path=p._portable(path), sha256=p._sha_of(path)) for name, path in artifacts.items()},
                  receipts=row.get("receipts"), final_tree=row.get("final_tree"))
    return record


def _expected_prefix(expected, hook_stop):
    """`--expect-items` against a hook-stopped invocation: the prefix before the slot stopped at ready, through the slot
    stopped at done; any other list is compared whole."""
    if hook_stop:
        slot = hook_stop.get("before_slot") or hook_stop.get("after_slot")
        if slot in expected:
            cut = expected.index(slot)
            return expected[:cut] if "before_slot" in hook_stop else expected[:cut + 1]
    return expected


def verify_a4_binding(path, worker):
    """A10 (P371 3b): an A4 receipt the chain bound to a worker (`bench_binding.worker`, written when the chain copied the
    gate's receipt for THAT load) must name the CURRENT worker; a receipt from before a reload refuses before any spawn. A raw
    gate receipt without a binding (a hand run) is left to the adapter's own checks."""
    if not path:
        return
    try:
        binding = (json.loads(Path(path).read_text()) or {}).get("bench_binding")
    except (OSError, ValueError, AttributeError):
        return
    if binding is None:
        return
    want = dict(pid=worker["pid"], create_time=worker["create_time"])
    if not isinstance(binding, dict) or binding.get("worker") != want:
        raise tg.TransportAbort("the A4 receipt belongs to another worker than the one this probe observed")


def receipt_controls(adapter, model, seed, budgets):
    """Per-class generation controls a worker receipt must show (A3): the paired seed, the declared sampling (when the
    carrier states all five fields), the thinking budget, a max_tokens bound and the adapter's allowed roles."""
    body = model.get("body", {})
    sampling = {k: body[k] for k in wr.SAMPLING_FIELDS if k in body}
    base = dict(seed=seed, thinking_budget=budgets["thinking_budget"], max_tokens_max=budgets["max_tokens"])
    if set(sampling) == set(wr.SAMPLING_FIELDS):
        base["sampling"] = sampling
    return {cls: dict(base, roles=list(adapter.expected_roles(cls))) for cls in wr.CLASSES}


# ---------------------------------------------------------------- identity
def _identity_inputs(adapter, template, corpus, selection, universe_sha, version, binary, kind):
    """(identity dict, GenerationPolicy): the adapter's pre-P371-shaped identity completed with the generation policy
    (a strict superset of the pre-P371 recipe). `scaffold_policy_sha256` is the generation policy's hash."""
    extra = {} if not kind else dict(inject_addendum_sha256=corpus.inject_addendum_sha256(kind))
    base = adapter.identity(selection=selection, universe_sha=universe_sha, version=version, binary=binary,
                            inject=kind, **extra)
    pol = base["policy"]
    cid = corpus.identity()
    timeouts = dict(cid["grader_timeout_s"])
    policy = template.build(
        scaffold=base["scaffold"], corpus_id=corpus.corpus_id, corpus_identity=corpus.identity(),
        toolbounds_sha256=pol["toolbounds_sha256"], noretry_sha256=pol["noretry_sha256"],
        datefreeze_sha256=pol["datefreeze_sha256"], carrier_sha256=pol["carrier_sha256"],
        universe_sha256=pol["universe_sha256"], env=pol["env"], toolchain=pol["toolchain"], inject=kind,
        gate=pol["gate"], hygiene=pol["hygiene"], grader_version=cid["grader_version"],
        grader_timeout_s=timeouts, grade_join_timeout_s=grade_join_timeout_s(timeouts),
        plugin_proof=pol["plugin_proof"], arm=pol.get("arm"), **extra)
    ident = dict(base)
    ident["policy"] = policy.as_dict()
    ident["scaffold_policy_sha256"] = policy.sha256()
    return ident, policy


def print_identity(p, adapter, a, *, template, corpus, extras=None):
    """`--print-identity`: the probe's provenance identity as JSON; never touches the router or a worker."""
    selection = adapter.selection(a.agent_system_file)
    _, universe_sha = corpus.load_universe()
    binary, exists = adapter.identity_binary()
    kind = getattr(a, "tg1_inject", None)
    ident, policy = _identity_inputs(adapter, template, corpus, selection, universe_sha, adapter.pinned_version,
                                     binary, kind)
    out = dict(
        arm=adapter.arm_id,
        config_id=policy.config_id,
        scaffold=ident["scaffold"],
        scaffold_policy_sha256=ident["scaffold_policy_sha256"],
        probe_code_sha256=ident["probe_code_sha256"],
        toolchain=ident["policy"]["toolchain"],
        **adapter.identity_summary(ident, exists),
    )
    try:
        polyglot_sha = corpus.source_sha()
    except SystemExit:
        polyglot_sha = None
    out["polyglot_sha"] = polyglot_sha
    # A5 (P371 3b): the snapshot the chain computes the epoch from. Without the client binary there is nothing to snapshot.
    try:
        snap = adapter.snapshot() if exists else None
    except SystemExit:                       # a pinned binary that is present but unusable: no snapshot, never a guess
        snap = None
    out.update(snapshot_tool=None if snap is None else snap.tool, snapshot_sha256=None if snap is None else snap.sha256,
               snapshot_complete=None if snap is None else snap.complete,
               snapshot_fields=None if snap is None else snap.fields)
    if extras:
        out.update(extras())
    if exists and polyglot_sha:
        full = {**ident, **selection["fields"], "polyglot_sha": polyglot_sha,
                "sampling_profile": getattr(a, "sampling_profile", None) or "deployed"}
        out["generation_identity_sha256"] = adapter.generation_identity_sha256(full)
    else:
        out["generation_identity_sha256"] = None      # needs the pinned binary and the source corpus
    print(json.dumps(out, sort_keys=True), flush=True)
    return 0


# ---------------------------------------------------------------- the probe main
def main(p, adapter, a, *, template, evidence, corpus, receipts=None):
    hostmod.require_host(p)
    forbidden = {"--tick-s", "--first-write-tokens", "--hard-ceiling-s", "--stall-ticks", "--loop-repeats", "--poll-s"}
    if any(s.split("=", 1)[0] in forbidden for s in sys.argv[1:]):
        sys.exit("REFUSED: tg1 does not accept legacy time-gate flags")
    if a.lang not in template.langs or a.rerun_of or a.rerun_index or a.extra_deny_file:
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
    if not adapter.valid_frozen_date(frozen):
        sys.exit("REFUSED: --frozen-prompt-date must be the date shape the client prints "
                 "(opencode: 'Www Mmm DD YYYY', e.g. 'Sat Oct 17 2026')")
    kind = a.tg1_inject
    if kind:
        if kind not in template.inject_allowed:
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
        return _main(p, adapter, a, names, template=template, evidence=evidence, corpus=corpus, receipts=receipts)
    except aa.ArmRefused as exc:
        sys.exit("REFUSED: " + p._scrub_error(exc))
    except (tg.TransportAbort, OSError, ValueError) as exc:
        sys.exit("REFUSED: " + p._scrub_error(exc))
    finally:
        if original_registry is None:
            os.environ.pop("MLX_SERVE_CONFIG", None)
        else:
            os.environ["MLX_SERVE_CONFIG"] = original_registry


def _main(p, adapter, a, names, *, template, evidence, corpus, receipts):
    aa.validate_adapter(adapter)
    if adapter.account_compaction != (template.compaction == "on_accounted"):
        raise aa.ArmRefused("the adapter and the generation policy disagree on compaction accounting")
    if adapter.watchdog_enabled != (template.watchdog["mode"] == "on"):
        raise aa.ArmRefused("the adapter and the generation policy disagree on the shell watchdog")
    kind = a.tg1_inject
    ctx = dict(cleanup_status=dict(CLEAN_STATUS))
    cancel = (lambda: Path(a.cancel_file).exists()) if a.cancel_file else None
    selection = adapter.selection(a.agent_system_file)          # an arm that needs a missing service refuses HERE
    if kind:
        selection["fields"] = {**selection["fields"], "scaffold": adapter.label + "-inject:" + kind}
    tool0 = toolchain.current()          # P23: lock + interpreter + grader image; a missing one refuses before any spawn
    model, base = adapter.declared_model(selection, a.model)
    router = provenance.assert_served_config(base, env={})
    os.environ["MLX_SERVE_CONFIG"] = str(provenance.paths.registry_path().resolve())
    before = worker_identity(p, a.model, router)
    arm_fp, arm_sha = arm_identity_of(p, a.model, router)       # P16: the effective worker fingerprint; unknown refuses
    limit = validate_worker(model, worker_json("health"), worker_json("metrics"), template.budgets)
    universe_path = a.universe or DEFAULT_UNIVERSE
    _, universe_sha = corpus.load_universe(universe_path)
    known = set(corpus.items(a.lang))
    for name in names:
        item = a.lang + "/" + name
        if item not in known:
            raise tg.TransportAbort("item absent/refused in universe: " + item)
    workdir = p._stack_workdir().resolve()
    binary = adapter.require_binary()
    receipts_required = evidence.worker_receipts == "required"
    wr.require_source(evidence.worker_receipts, receipts if receipts is not None else wr.UnavailableReceiptSource())
    receipt_source = receipts if receipts_required else None
    attempt_n = int(getattr(a, "attempt", None) or 1)
    attempt_rerun = int(getattr(a, "attempt_rerun_index", None) or 0)
    receipt = adapter.preflight(selection=selection, path=a.a4_v2_receipt, router=router, limit=a.limit,
                                model=a.model, exe_sha=p._sha_of(binary))
    verify_a4_binding(a.a4_v2_receipt, before)
    run_id = time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    run_dir = adapter.make_run_dir(workdir, run_id, selection)
    private = run_dir / "grading-private"
    private.mkdir()
    frozen = a.frozen_prompt_date
    out = Path(a.out) if a.out else REPO / "benchmark/results" / a.model / (adapter.label + ".jsonl")
    if adapter.evidence_root(workdir) != workdir / evidence.namespace:
        raise tg.TransportAbort("evidence namespace differs from the adapter's: " + evidence.namespace)
    evidence_dir = workdir / evidence.namespace / a.model / (out.stem + "." + run_id)

    def check_env(env, overlay):
        adapter.verify_env(env, run_dir, selection, overlay)
        if corpus.load_universe(universe_path)[1] != universe_sha:
            raise tg.TransportAbort("tg1 input provenance drift")
        try:
            toolchain.verify(tool0)
        except toolchain.ToolchainError as exc:
            raise tg.TransportAbort("tg1 " + str(exc)) from exc

    def seed_of(item):
        return rowschema.sample_seed(item, 0, base=a.seed_base)

    if cancel is not None and cancel():
        raise RunnerCancelled()      # C147 section 3a: before the first spawn of any kind
    with p._scratch_dir("tg1-discovery") as scratch:
        p._git_init_scratch(scratch)
        overlay = adapter.seed_overlay(a.model, seed_of(a.lang + "/" + names[0]), attempt=None)
        # discovery runs no session, so the plugins never write these files (named only to satisfy the env contract)
        env = adapter.build_env(run_dir, scratch, overlay, receipts=evidence_dir / "discovery.datefreeze.jsonl",
                                frozen_date=frozen,
                                toolwindow_receipts=(evidence_dir / "discovery.toolwindows.jsonl"
                                                     if adapter.watchdog_enabled else None),
                                attempt=wr.AttemptContext.make("discovery", 1))
        p._fresh_tmpdir(env)
        check_env(env, overlay)
        with _DiscoveryGuard(p, [scratch, env["TMPDIR"]], (router.get("pid"), before["pid"]), ctx) as dg:
            version, destination = adapter.discover(scratch, env, model=a.model, run_dir=run_dir, binary=binary,
                                                    overlay=overlay, runner=dg.run_grader, check_version=True)
        provenance.assert_served_config_unchanged(router, destination)
    shutil.rmtree(env["TMPDIR"])
    ident, policy = _identity_inputs(adapter, template, corpus, selection, universe_sha, version, binary, kind)
    if ident["policy"]["toolchain"] != tool0:
        raise tg.TransportAbort("tg1 toolchain drift: changed while the probe started")
    snapshot = adapter.snapshot()
    ident.update(
        seed_base=a.seed_base,
        lang=a.lang,
        frozen_prompt_date=frozen,          # P364: chain metadata and resume identity; NOT in the generation composite
        polyglot_sha=corpus.source_sha(),
        a4_v2_pass=bool(receipt),
        **selection["fields"],
    )
    ident["sampling_profile"] = a.sampling_profile        # a present None is a value (the composite requires the key)
    ident["generation_identity_sha256"] = adapter.generation_identity_sha256(ident)
    ident.update(arm_identity_sha256=arm_sha, arm_identity=arm_fp, arm=adapter.arm_id, config_id=policy.config_id,
                 epoch_id=getattr(a, "epoch_id", None), snapshot_sha256=snapshot.sha256,
                 snapshot_complete=snapshot.complete, snapshot_fields=snapshot.fields,
                 evidence_policy=evidence.as_dict())
    mp = out.with_suffix(".manifest.json")
    rows = []
    if out.exists():
        # P371 phase 3a (plan 4 A8 / R6): probe-level resume is gone. Every invocation writes a FRESH rows file (the chain
        # names it `<stem>.L<leg>.<phase>.a<n>.jsonl`), so a pre-existing rows file at the target path refuses. The old
        # manifest is still read to say WHY (transport abort, provenance, serving or worker drift).
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
        raise tg.TransportAbort("tg1 rows file already exists: every invocation writes a fresh rows file (P371 A8); "
                                "the chain names one per leg attempt")
    man = provenance.gather(a.model, profile="deployed", runtime=ident, router=router)
    man.update(worker=before, run_id=run_id)

    def save_manifest():
        pg.atomic_write(mp, p._scrub_pii(json.dumps(man, indent=2)).encode())

    save_manifest()
    barrier = ib.ItemBarrier(out.with_suffix(""), evidence.item_barrier == "on", ACK_TIMEOUT_S, cancel,
                             cancel_exc=RunnerCancelled, poll_s=ACK_POLL_S)
    try:
        if a.manifest_ack:
            _wait_for_ack(a.manifest_ack, cancel)
        for k, name in enumerate(names):
            item = a.lang + "/" + name
            if cancel is not None and cancel():
                raise RunnerCancelled()
            ctx.update(id=item)
            ctx.pop("evidence_paths", None)              # never a previous item's evidence in this item's abort stamp
            current = worker_identity(p, a.model, router)
            pg.require_identity(before, current)
            with p._item_scratch_dir(name) as scratch:
                prepared = corpus.prepare(item, scratch / name)
                work = prepared.work
                attempt = wr.AttemptContext.make(item, attempt_n, attempt_rerun)       # R3: before the env is generated
                header_ctx = attempt if receipts_required and adapter.supports_attempt_header else None
                overlay = adapter.seed_overlay(a.model, seed_of(item), attempt=header_ctx)
                item_evidence = evidence_dir / (a.lang + "__" + name)
                env = adapter.build_env(run_dir, work, overlay,
                                        receipts=item_evidence.with_suffix(".datefreeze.jsonl"), frozen_date=frozen,
                                        toolwindow_receipts=(item_evidence.with_suffix(".toolwindows.jsonl")
                                                             if adapter.watchdog_enabled else None),
                                        attempt=attempt)
                p._fresh_tmpdir(env)
                check_env(env, overlay)
                with _DiscoveryGuard(p, [work, env["TMPDIR"]], (router.get("pid"), before["pid"]), ctx) as dg:
                    _, destination = adapter.discover(work, env, model=a.model, run_dir=run_dir, binary=binary,
                                                      overlay=overlay, runner=dg.run_grader)
                provenance.assert_served_config_unchanged(router, destination)
                prompt = corpus.prompt(prepared, kind)
                if barrier.ready(k) == "stop":                       # R23 / R25: after the env, before receipts.start and the spawn
                    man["hook_stop"] = dict(before_slot=item)
                    man["cleanup_status"] = ctx.get("cleanup_status")      # A7 (F5): a clean hook stop is its own receipt
                    save_manifest()
                    break
                result = run_item(
                    p, adapter, corpus=corpus, prepared=prepared, model=a.model, prompt=prompt, env=env,
                    binary=binary, evidence=item_evidence, limit=limit, private=private, router=router, base=base,
                    protected_pids=(before["pid"],), policy=(policy.gate, policy.hygiene), cancel=cancel, ctx=ctx,
                    frozen_date=frozen, gate_overrides=getattr(a, "gate_overrides", None),
                    watchdog=policy.watchdog, compaction=policy.compaction == "on_accounted",
                    join_timeout_s=policy.grade_join_timeout_s, receipts=receipt_source, attempt=attempt,
                    header_sent=header_ctx is not None,
                    controls=receipt_controls(adapter, model, seed_of(item), policy.budgets),
                    expected_worker=dict(pid=before["pid"], create_time=before["create_time"]))
                after = worker_identity(p, a.model, router)
                pg.require_identity(before, after)
                check_env(env, overlay)
                provenance.assert_served_config_unchanged(router, base)
                export = result.pop("export")
                transcript = result.pop("transcript")
                artifacts = result.pop("evidence")
                rc_ = result.pop("rc")
                adapter.observed = dict(events=result.pop("normalized_events"), reconciliation=result.pop("reconciled"),
                                        tool_windows=result.pop("tool_windows"))
                accounting = result.pop("token_accounting", "client")
                changed = corpus.changed(prepared)
                # M59/M61 rule kept: an untouched solution fails (go/ledger, go/markdown stubs pass every test).
                passed = result.pop("passed") and changed
                final_tree = None
                if evidence.final_tree:
                    tree = corpus.final_tree(prepared, Path(str(item_evidence) + ".final_tree"))
                    final_tree = dict(manifest=p._portable(tree.manifest_path), manifest_sha256=tree.manifest_sha256,
                                      files=dict(tree.files), missing=list(tree.missing))
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
                    **adapter.row_fields(version=version, rc=rc_, artifacts=artifacts, sha_of=p._sha_of,
                                         portable=p._portable),
                    generation_identity_sha256=ident["generation_identity_sha256"],
                    arm_identity_sha256=ident["arm_identity_sha256"],
                    **adapter.metrics(p, transcript, export),
                    sampler_seed=seed_of(item), seed_base=a.seed_base, overlay_sha256=adapter.overlay_sha(env),
                    arm=adapter.arm_id,
                    config_id=policy.config_id,
                    epoch_id=getattr(a, "epoch_id", None),
                    snapshot_sha256=snapshot.sha256,
                    final_tree=final_tree,
                    token_accounting=accounting,
                )
                rows.append(json.loads(p._scrub_pii(json.dumps(row))))
                pg.atomic_write(out, ("".join(json.dumps(r) + "\n" for r in rows)).encode())
                print(f'{item}: passed={passed} nonconv={row["nonconv_kind"]}', flush=True)
                if barrier.enabled and barrier.done(k, _done_record(p, rows[-1], attempt, artifacts)) == "stop":
                    man["hook_stop"] = dict(after_slot=item, disposition=barrier.stop_payload(k).get("disposition"))
                    man["cleanup_status"] = ctx.get("cleanup_status")      # A7 (F5)
                    save_manifest()
                    break
        if a.expect_items:
            pg.expect_items(rows, _expected_prefix([s.strip() for s in a.expect_items.split(",")], man.get("hook_stop")))
    except BaseException as exc:
        status = ctx.get("cleanup_status")
        man["cleanup_status"] = status          # the receipt location (top level) on EVERY abort path
        stamp = dict(error=p._scrub_error(exc), cleanup_status=status, grade_reports=ctx.get("grade_reports", []),
                     termination=ctx.get("termination"))
        if adapter.report_gate_on_abort:
            stamp["gate"] = ctx.get("gate_report")     # spec 8.3: a failed attempt's tokens count toward its task
        if ctx.get("receipt_tokens") is not None:
            stamp["receipts"] = ctx["receipt_tokens"]  # P371 3b: the fenced worker receipts' totals (the better count)
        if ctx.get("evidence_paths") is not None and ctx.get("id"):
            # F6 (A12): the failing slot's evidence files with their sha256 AT the abort (null: the file does not exist)
            stamp["evidence"] = dict(id=ctx["id"], files={
                k: dict(path=p._portable(v), sha256=p._sha_of(v) if Path(v).is_file() else None)
                for k, v in ctx["evidence_paths"].items()})
        cause = adapter.transport_cause(exc)
        if cause is None and isinstance(exc, wr.ReceiptAbort):
            cause = exc.cause                    # a worker replaced mid-attempt: worker_crash (R21); other receipt faults: none
        if cause is not None:
            stamp["cause"] = cause                # spec 8.3: the incident class the chain retries on
        man["transport_abort"] = stamp
        if isinstance(exc, RunnerCancelled) and exc.item:
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
