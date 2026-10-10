"""M62-only orchestration. The legacy v2 runner never constructs these components."""

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
from . import (
    token_turn_gate as tg,
    structured_grade as sg,
    proc_guard as pg,
    provenance,
)
from m62 import universe_preflight

SCAFFOLD = "opencode-v2-web-tg1"
REPO = Path(__file__).resolve().parents[2]
CARRIER = REPO / "benchmark/opencode_bench_v2_web_tg1.json"
PLUGIN = REPO / "benchmark/opencode_plugins/toolbounds.js"


GRADE_JOIN_OVERHEAD_S = 60
HEARTBEAT_INTERVAL_S = 30
GRACEFUL_CLIENT_S = 15
ACK_TIMEOUT_S = 300
ACK_POLL_S = 0.5
CAMPAIGN_POLICY_SHA256 = "ba86ba16e40e5e7b3535d64de2de9e95b323158049358b1f41b2ed26a83bb15c"

# C147 §2: frozen injected-positive policy. Each kind lowers exactly ONE constant; every other constant stays at the
# campaign value (derived at call time by `effective_policy`). No CLI override exists.
INJECT_POLICY = {
    "stall": {"gate": {"no_progress_requests": 4}, "hygiene": {}},
    "loop": {"gate": {"identical_calls": 3}, "hygiene": {}},
    "alloc": {"gate": {}, "hygiene": {"per_process": 512 * 1024**2}},
}
INJECT_ADDENDA = {
    "stall": "Before anything else, run the shell command `ls` four separate times, one tool call per message, "
             "and only then start the task.",
    "loop": "Before anything else, run the shell command `sleep 600 >/dev/null 2>&1 & sleep 1` three times in a row "
            "as three separate tool calls with exactly the same arguments (same command text, same working "
            "directory, no other fields), and only then start the task.",
    "alloc": "Before anything else, run exactly this shell command once: "
             "`python3 -c \"import time; b = bytearray(1024 * 1024 * 1024); time.sleep(90)\"` "
             "and only then start the task.",
}


def inject_label(kind):
    return SCAFFOLD + "-inject:" + kind


def inject_addendum_sha256(kind):
    return hashlib.sha256(INJECT_ADDENDA[kind].encode()).hexdigest()


def effective_policy(kind=None):
    """(gate, hygiene) dicts in force: the campaign constants, with the inject kind's single override applied."""
    gate, hygiene = dict(tg.POLICY), dict(pg.POLICY)
    if kind is not None:
        gate.update(INJECT_POLICY[kind]["gate"])
        hygiene.update(INJECT_POLICY[kind]["hygiene"])
    return gate, hygiene


class RunnerCancelled(tg.TransportAbort):
    """The runner's cooperative cancel was honoured; carries the evidence for the manifest's `cancelled_item`."""

    def __init__(self, message="cancelled by runner", item=None):
        super().__init__(message)
        self.item = item or {}


def grade_reports(keep, portable=None):
    """Hashed report index of every grade taken for an item, from the `seq-*/index.json` files (C147 §5)."""
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


def grade_join_timeout_s():
    """Grader timeouts are per grade; a terminal drain may hold the active grade plus one queued capture."""
    return 2 * max(sg.TIMEOUTS.values()) + GRADE_JOIN_OVERHEAD_S


class GradeWorker:
    """One grader, one coalesced capture; ingestion never waits on a grade."""

    def __init__(self, gate, lock, work, private, grade):
        self.gate = gate
        self.lock = lock
        self.work = work
        self.private = private
        self.grade_fn = grade
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
                current = sg.manifest(self.work)
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
                with sg.snapshot(self.work, self.private, boundary=boundary) as snap:
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
        self.thread.join(grade_join_timeout_s())
        if self.thread.is_alive():
            raise tg.TransportAbort(
                "grading worker did not finish within grader timeout"
            )
        self.check()


def validate_worker(model, health, metrics):
    if (
        model.get("body", {}).get("thinking_budget") != 81920
        or model.get("body", {}).get("max_tokens") != 102400
    ):
        raise tg.TransportAbort(
            "tg1 requires thinking_budget=81920 and max_tokens=102400"
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


def worker_identity(p, model, router):
    import psutil

    observed = p._worker_load_identity(model, router)
    if not observed:
        raise tg.TransportAbort("worker identity unavailable")
    try:
        observed.update(
            create_time=psutil.Process(observed["pid"]).create_time(),
            registry_sha256=hashlib.sha256(
                provenance.paths.registry_path().read_bytes()
            ).hexdigest(),
        )
    except (OSError, psutil.Error) as exc:
        raise tg.TransportAbort("worker creation time unavailable") from exc
    pg.require_identity(observed, observed)
    return observed


def tool_bounds_rejections(export):
    return sum(
        part.get("type") == "tool"
        and part.get("name") == "shell"
        and part.get("state", {}).get("status") == "error"
        and "M62_TOOL_BOUND:"
        in str(part.get("state", {}).get("error", {}).get("message", ""))
        for message in export["messages"]
        for part in message.get("content", [])
        if isinstance(part, dict)
    )


def identity(p, selection, universe_sha, version, binary, *, inject=None):
    """Probe identity. `inject=None` is the campaign mode and MUST keep the policy dict (hence
    `scaffold_policy_sha256`) byte-identical to the V3/V4 manifests; inject-only keys live in inject mode only."""
    gate, hygiene = effective_policy(inject)
    label = inject_label(inject) if inject else SCAFFOLD
    policy = dict(
        gate=gate,
        hygiene=hygiene,
        toolbounds_sha256=p._sha_of(PLUGIN),
        noretry_sha256=p._sha_of(p.NORETRY_PLUGIN),
        carrier_sha256=selection["fields"]["opencode_bench_config_sha256"],
        universe_sha256=universe_sha,
        grader_version=sg.VERSION,
        grader_timeout_s=sg.TIMEOUTS,
        grade_join_timeout_s=grade_join_timeout_s(),
        plugin_proof="GET /api/integration awaits Plugin.awaitActivation",
        env=p.SCAFFOLD_ENV_POLICY_V2,
        scaffold=label,
    )
    if inject:
        policy["inject"] = dict(kind=inject, prompt_addendum_sha256=inject_addendum_sha256(inject))
    modules = [
        Path(__file__),
        Path(tg.__file__),
        Path(sg.__file__),
        Path(pg.__file__),
        Path(universe_preflight.__file__),
        REPO / "benchmark/m62/replay.py",
        Path(p.__file__),
        Path(provenance.__file__),
        Path(p.opencode_common.__file__),
        # Transitive scoring/accounting: budget clamp, seeds, audit/cheat labels,
        # registry resolution and deployed sampling/provenance. Legacy progress_gate
        # and generate execution are not called by tg1.
        *(REPO / "benchmark" / name for name in (
            "bench/convergence.py", "bench/rowschema.py", "bench/answer_key.py",
            "web_audit.py", "web_audit_prompt.md", "bench/paths.py",
            "bench/model_params.py", "bench/quant_info.py",
        )),
    ]
    digest = hashlib.sha256()
    for path in modules:
        digest.update(path.relative_to(REPO).as_posix().encode() + b"\0")
        digest.update(path.read_bytes())
    result = dict(
        scaffold=label,
        policy=policy,
        scaffold_policy_sha256=hashlib.sha256(
            json.dumps(policy, sort_keys=True).encode()
        ).hexdigest(),
        probe_code_sha256=digest.hexdigest(),
        opencode_version=version,
        opencode_exe_sha256=p._sha_of(binary),
    )
    if inject:
        result["inject"] = dict(kind=inject, policy=dict(gate=gate, hygiene=hygiene),
                                prompt_addendum_sha256=inject_addendum_sha256(inject))
    return result


def print_identity(p, a):
    """`--print-identity`: the probe's provenance identity as JSON; never touches the router or a worker."""
    selection = p._carrier_selection(SCAFFOLD, a.agent_system_file, source=CARRIER)
    universe_path = a.universe or REPO / "benchmark/m62/universe.json"
    _, universe_sha = universe_preflight.load(universe_path)
    exe = Path(os.environ.get("OPENCODE_PROBE_BIN") or p._default_opencode_bin())
    binary = exe if exe.is_file() else Path(p.__file__)
    ident = identity(p, selection, universe_sha, p.PINNED_OPENCODE_VERSION_V2, binary,
                     inject=getattr(a, "tg1_inject", None))
    out = dict(
        scaffold=ident["scaffold"],
        scaffold_policy_sha256=ident["scaffold_policy_sha256"],
        probe_code_sha256=ident["probe_code_sha256"],
        opencode_version=ident["opencode_version"],
    )
    if exe.is_file():
        out["opencode_exe_sha256"] = ident["opencode_exe_sha256"]
    print(json.dumps(out, sort_keys=True), flush=True)
    return 0


def run_item(p, *, ctx=None, **kwargs):
    """Run one item. `ctx` (a dict) receives `cleanup_status` from the guard on EVERY exit path and, when the
    runner's cancel file was honoured during generation, the call raises `RunnerCancelled` after the full terminal
    path (drain, grade join, export, reconcile, final grade, report retention) with the item's evidence."""
    ctx = {} if ctx is None else ctx
    result = _run_item(p, ctx=ctx, **kwargs)
    cancel = kwargs.get("cancel")
    # C147 §3: a cancel that landed during the terminal phases is honoured here, BEFORE the row is committed.
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


def _run_item(
    p,
    *,
    model,
    work,
    prompt,
    env,
    binary,
    evidence,
    entry,
    limit,
    private,
    router,
    base,
    protected_pids=(),
    policy=None,
    cancel=None,
    ctx=None,
):
    gate_policy, hygiene = policy if policy is not None else effective_policy()
    scrub = p._scrub_pii if p is not None else (lambda text: text)
    portable = p._portable if p is not None else str
    gate = tg.TokenTurnGate(
        entry["baseline_failing"],
        context_limit=limit,
        universe_size=len(entry["leaves"]),
        policy=gate_policy,
    )
    lock = threading.RLock()
    observations = []
    termination = dict(reason=None, killed=[], killed_verified=None, cancel_wait_s=None,
                       in_flight_at_kill=None, worker_summary_before=None, worker_summary_after=None,
                       client_stop=None, graceful_wait_s=None)
    if ctx is not None:
        ctx.update(termination=termination)      # abort manifests carry whatever the kill path recorded
    silence_observer = pg.SilenceObserver()
    exit_hang = False
    cancelled = False
    resources = dict(grader_mem_kill=False, grader_oom=False)
    paths = {
        key: evidence.with_suffix(suffix)
        for key, suffix in (
            ("events", ".events.jsonl"),
            ("stderr", ".stderr.txt"),
            ("export", ".json"),
        )
    }
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
        [work, env["TMPDIR"], private],
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
        modified = sg.tampered(
            snap.path, entry["protected"], entry["prepared"], entry["lang"]
        )
        if modified:
            return None, True
        result = sg.grade(entry["lang"], snap.path, entry["test"], private, guard=guard,
                          keep=keep, seq=next_seq(), boundary=snap.boundary, final=False)
        resources["grader_mem_kill"] |= result.grader_mem_kill
        resources["grader_oom"] |= result.grader_oom
        return result.failing({tuple(x) for x in entry["leaves"]}), False

    worker = GradeWorker(gate, lock, work, private, grade)
    stream = tg.EventStream(gate, worker.notify)
    stream.base_url = base
    proc = None
    client_launch_attempted = False
    ingester = None
    killed = False
    final_result = None
    cancellation_attempted = False
    heartbeat = PhaseHeartbeat(gate, lock, started)
    reconciliation = None
    tmp_before = None
    tmp_window_start = time.time()
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
                gate.inflight_s_at_stop = (
                    time.monotonic() - stream.started_at if stream.started_at else None
                )
                termination.update(reason=reason, requests_at_kill=gate.requests_at_kill,
                                   inflight_s_at_stop=gate.inflight_s_at_stop)
        killed = True
        heartbeat.set_phase("cancellation")
        if reason:
            # The summary immediately before the kill: proves the worker was serving this session's request.
            try:
                before = worker_json("metrics")
                termination.update(in_flight_at_kill=pg.in_flight(before),
                                   worker_summary_before=before.get("summary"))
            except Exception:  # noqa: BLE001 — evidence only; the kill must still run
                pass
        errors = []
        killed_entries = []
        # Raw events-file position at the moment of signalling (after the pre-kill metrics call): only error bytes
        # at or after it can be our own abort's, however late the ingester reads them.
        try:
            stream.signal_offset = paths["events"].stat().st_size
        except OSError:
            stream.signal_offset = None
        # C147: the client gets SIGTERM first so opencode's own abort path can persist the in-flight assistant
        # message; survivors after GRACEFUL_CLIENT_S are SIGKILLed. Model-role processes are always SIGKILLed.
        graceful = getattr(guard, "graceful_stop", None)
        if graceful is not None:
            began = time.monotonic()
            try:
                killed_entries.extend(graceful("client", GRACEFUL_CLIENT_S) or [])
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
        for entry in killed_entries:
            key = (entry["pid"], entry["create_time"])
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(entry)
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

        elapsed = pg.wait_cancel(metrics,
                                 prompt_tokens=gate.request_usage[-1][2] if gate.request_usage else 0)
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
            proc = guard.spawn(
                [
                    binary,
                    "run",
                    "--standalone",
                    "--model",
                    "mlx-local/" + model,
                    "--format",
                    "json",
                    "--title",
                    "probe",
                    prompt,
                ],
                cwd=work,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
            )

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

            ingester = threading.Thread(
                target=ingest, name="m62-ingestion", daemon=True
            )
            ingester.start()
            last_silence = 0
            while proc.poll() is None:
                guard.check()
                worker.check()
                if ingest_failure:
                    raise ingest_failure[0]
                now = time.monotonic()
                with lock:
                    if guard.client_resource:
                        gate.stop("client_resource")
                    if (
                        now - stream.last_event >= pg.POLICY["silence_s"]
                        and now - last_silence >= pg.POLICY["silence_sample_s"]
                    ):
                        metrics = worker_json("metrics")
                        descendant = guard.descendants_alive()
                        size = paths["events"].stat().st_size
                        observed_reason = silence_observer.sample(now, size, metrics, descendant)
                        observations.append(
                            dict(
                                sampled_at_s=now - started,
                                event_bytes=size,
                                idle_samples=silence_observer.idle,
                                silent_s=now - stream.last_event,
                                in_flight=pg.in_flight(metrics),
                                tracked_descendant_alive=descendant,
                            )
                        )
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
        # Export acquisition is tracked, and the raw native IDs remain intact.
        heartbeat.set_phase("export")
        exported = guard.run_grader(
            [binary, "session", "export", stream.session_id or "", "--standalone"],
            cwd=work,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
        )
        paths["export"].write_text(exported.stdout or "")
        if exported.returncode:
            raise tg.TransportAbort("session export failed: " + (exported.stderr or ""))
        try:
            export = json.loads(exported.stdout)
        except ValueError as exc:
            raise tg.TransportAbort("unparsable session export") from exc
        # The final grade must have a chance to credit its boundary before a T/N stop.
        final_boundary = len(
            [
                m
                for m in export.get("messages", [])
                if m.get("type") == "assistant" and not m.get("error")
            ]
        )
        gate.pending.add(final_boundary)
        try:
            summary = tg.reconcile(
                stream,
                export,
                proc.returncode,
                "client_exit_hang" if exit_hang and not gate.stop_reason else
                (gate.stop_reason or ("runner_cancel" if cancelled else None))
                if killed or guard.client_resource else None,
            )
            reconciliation = dict(unmatched_export_messages=summary["unmatched_export_messages"],
                                  trailing=summary["trailing"])
        except tg.TransportAbort as exc:
            if exit_hang:
                raise tg.TransportAbort("client silent, worker idle: " + str(exc)) from exc
            raise
        final_boundary_actual = len(gate.request_usage)
        if final_boundary != final_boundary_actual:
            gate.pending.discard(final_boundary)
            gate.pending.add(final_boundary_actual)
        # C147 §4: /tmp escape diagnostic and exact-path cleanup, after the client is gone.
        tmp_found, tmp_cleaned, tmp_kept, tmp_window = [], [], [], None
        tmp_found = pg.tmp_escapes(export, env)
        try:
            tmp_after = pg.tmp_listing()
        except OSError:
            tmp_after = None
        tmp_window = (tmp_window_start, time.time())
        if tmp_before is None or tmp_after is None:
            tmp_kept = [[c["path"], "ambiguous"] for c in tmp_found if c["exact"]]
        else:
            tmp_cleaned, tmp_kept = pg.tmp_clean(tmp_found, tmp_before, tmp_after, tmp_window)
        print(
            "%s: tmp_escapes=%d exact=%d shell=%d cleaned=%d not_removed=%s" % (
                entry.get("id", work.name), len(tmp_found), sum(c["exact"] for c in tmp_found),
                sum(not c["exact"] for c in tmp_found), len(tmp_cleaned), json.dumps(tmp_kept)),
            flush=True)
        heartbeat.set_phase("terminal_grading")
        with sg.snapshot(work, private, boundary=final_boundary_actual) as snap:
            modified = (
                True
                if snap is None
                else sg.tampered(
                    snap.path, entry["protected"], entry["prepared"], entry["lang"]
                )
            )
            failing = None
            if snap is not None and not modified:
                final_result = sg.grade(
                    entry["lang"], snap.path, entry["test"], private, guard=guard,
                    keep=keep, seq=next_seq(), boundary=final_boundary_actual, final=True
                )
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
        return dict(
            gate=gate.report(),
            request_usage=gate.request_usage,
            nonconv_kind=gate.primary,
            converged=gate.primary is None,
            nonconv_flags=[f for f in tg.PRECEDENCE if f in gate.flags],
            test_modified=modified,
            passed=bool(
                failing == 0
                and not modified
            ),
            opencode_rc=proc.returncode,
            wall_s=time.monotonic() - started,
            export=export,
            session_id=stream.session_id,
            requests_observed=len(stream.starts),
            tool_bounds_rejections=tool_bounds_rejections(export),
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
            **resources,
        )
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
                        guard.kill_role("grader")
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


def main(p, a):
    forbidden = {
        "--tick-s",
        "--first-write-tokens",
        "--hard-ceiling-s",
        "--stall-ticks",
        "--loop-repeats",
        "--poll-s",
    }
    if any(s.split("=", 1)[0] in forbidden for s in sys.argv[1:]):
        sys.exit("REFUSED: tg1 does not accept legacy time-gate flags")
    if (
        a.lang not in ("python", "go")
        or a.rerun_of
        or a.rerun_index
        or a.extra_deny_file
    ):
        sys.exit("REFUSED: tg1 supports eligible Python/Go single-pass items only")
    names = [s.strip() for s in a.items.split(",") if s.strip()]
    if (
        not names
        or len(names) != len(set(names))
        or any(Path(n).name != n or n in (".", "..") for n in names)
    ):
        sys.exit("REFUSED: invalid or duplicate items")
    if a.limit is not None:
        if a.limit <= 0:
            sys.exit("REFUSED: limit must be positive")
        names = names[: a.limit]
    if a.sampling_profile not in (None, "deployed"):
        sys.exit("REFUSED: --sampling-profile accepts only 'deployed'")
    kind = a.tg1_inject
    if kind:
        if kind not in INJECT_POLICY:
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
        return _main(p, a, names)
    except (tg.TransportAbort, OSError, ValueError) as exc:
        sys.exit("REFUSED: " + p._scrub_error(exc))
    finally:
        if original_registry is None:
            os.environ.pop("MLX_SERVE_CONFIG", None)
        else:
            os.environ["MLX_SERVE_CONFIG"] = original_registry


CLEAN_STATUS = dict(survivors=[], containers_remaining=[], uncertain=False, orphans_unattributed=[], unknown=[], completed=True)


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


def _main(p, a, names):
    kind = a.tg1_inject
    ctx = dict(cleanup_status=dict(CLEAN_STATUS))
    cancel = (lambda: Path(a.cancel_file).exists()) if a.cancel_file else None
    selection = p._carrier_selection(SCAFFOLD, a.agent_system_file, source=CARRIER)
    if kind:
        selection["fields"] = {**selection["fields"], "scaffold": inject_label(kind)}
    carrier = json.loads(selection["bytes"])
    model = carrier["providers"]["mlx-local"]["models"].get(a.model)
    if model is None:
        raise tg.TransportAbort("model absent from tg1 carrier")
    base = carrier["providers"]["mlx-local"]["settings"]["baseURL"]
    router = provenance.assert_served_config(base, env={})
    os.environ["MLX_SERVE_CONFIG"] = str(provenance.paths.registry_path().resolve())
    before = worker_identity(p, a.model, router)
    limit = validate_worker(model, worker_json("health"), worker_json("metrics"))
    universe_path = a.universe or REPO / "benchmark/m62/universe.json"
    universe, universe_sha = universe_preflight.load(universe_path)
    for name in names:
        item = a.lang + "/" + name
        if item == "go/counter" or item not in universe["items"]:
            raise tg.TransportAbort("item absent/refused in universe: " + item)
    workdir = p._stack_workdir().resolve()
    binary = p._require_opencode_bin()
    receipt = p._a4_receipt(
        a.a4_v2_receipt,
        router,
        a.limit,
        a.model,
        p._sha_of(binary),
        selection["fields"]["opencode_bench_config_sha256"],
    )
    run_id = time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    run_dir = p._make_run_dir(workdir, run_id, selection)
    shutil.copyfile(PLUGIN, run_dir / "cfg/opencode/plugins/toolbounds.js")
    private = run_dir / "grading-private"
    private.mkdir()
    plugin_sha = p._sha_of(PLUGIN)
    noretry_sha = p._sha_of(p.NORETRY_PLUGIN)

    def check_env(env, overlay):
        provenance.opencode_v2_env_check(
            env,
            run_dir,
            selection["fields"]["opencode_bench_config_sha256"],
            noretry_sha,
            overlay,
            scaffold=SCAFFOLD,
            toolbounds_sha=plugin_sha,
        )
        if (
            p._sha_of(CARRIER) != selection["fields"]["carrier_source_sha256"]
            or p._sha_of(PLUGIN) != plugin_sha
            or p._sha_of(p.NORETRY_PLUGIN) != noretry_sha
            or universe_preflight.load(universe_path)[1] != universe_sha
            or selection["system_path"]
            and p._sha_of(selection["system_path"])
            != selection["fields"]["agent_system_sha256"]
        ):
            raise tg.TransportAbort("tg1 input provenance drift")

    if cancel is not None and cancel():
        raise RunnerCancelled()      # C147 §3a: before the first spawn of any kind
    with p._scratch_dir("tg1-discovery") as scratch:
        p._git_init_scratch(scratch)
        overlay = p._seed_overlay(
            a.model, p._item_seed(a.lang + "/" + names[0], a.seed_base)
        )
        env = p._opencode_env(run_dir, scratch, overlay)
        p._fresh_tmpdir(env)
        check_env(env, overlay)
        with _DiscoveryGuard(p, [scratch, env["TMPDIR"]],
                             (router.get("pid"), before["pid"]), ctx) as discovery_guard:
            version_result = discovery_guard.run_grader(
                [binary, "--version"],
                cwd=scratch,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                stdin=subprocess.DEVNULL,
            )
            version = p._parse_version(version_result.stdout)
            if version_result.returncode or version != "2.0.20":
                raise tg.TransportAbort("tg1 requires pinned opencode 2.0.20")
            destination = provenance.opencode_v2_destination(
                scratch,
                {**env, "OPENCODE_PRINT_LOGS": "1"},
                a.model,
                run_dir,
                binary,
                overlay,
                scaffold=SCAFFOLD,
                runner=discovery_guard.run_grader,
            )
        provenance.assert_served_config_unchanged(router, destination)
    shutil.rmtree(env["TMPDIR"])
    ident = identity(p, selection, universe_sha, version, binary, inject=kind)
    ident.update(
        seed_base=a.seed_base,
        lang=a.lang,
        polyglot_sha=p._polyglot_sha(p._polyglot_root()),
        a4_v2_pass=bool(receipt),
        **selection["fields"],
    )
    if a.sampling_profile:
        ident["sampling_profile"] = a.sampling_profile
    out = (
        Path(a.out)
        if a.out
        else REPO / "benchmark/results" / a.model / "opencode-v2-web-tg1.jsonl"
    )
    mp = out.with_suffix(".manifest.json")
    rows = pg.load_rows(out)
    if rows:
        try:
            old = json.loads(mp.read_text())
        except (ValueError, OSError) as exc:
            raise tg.TransportAbort("rows have no intact manifest") from exc
        if old.get("transport_abort"):
            raise tg.TransportAbort("tg1 resume refused: the manifest records a transport abort")
        if any(
            old.get("runtime", {}).get(key) != value for key, value in ident.items()
        ):
            raise tg.TransportAbort("tg1 resume provenance differs")
        if old.get("served_config_drift") or old.get("git", {}).get(
            "serving_path"
        ) != provenance._git_shas().get("serving_path"):
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
            _wait_for_ack(a.manifest_ack, cancel)
        for name in names:
            item = a.lang + "/" + name
            if any(r["id"] == item for r in rows):
                continue
            if cancel is not None and cancel():
                raise RunnerCancelled()
            ctx.update(id=item)
            current = worker_identity(p, a.model, router)
            pg.require_identity(before, current)
            source = p._polyglot_root() / a.lang / "exercises/practice" / name
            entry = {**universe["items"][item], "lang": a.lang, "id": item}
            with p._item_scratch_dir(name) as scratch:
                work = scratch / name
                p._prepare(source, work)
                p._git_init_scratch(work)
                p._freeze_mtimes(work)
                if sg.manifest(work) != entry["prepared"]:
                    raise tg.TransportAbort(
                        "prepared exercise differs from frozen universe"
                    )
                overlay = p._seed_overlay(a.model, p._item_seed(item, a.seed_base))
                env = p._opencode_env(run_dir, work, overlay)
                p._fresh_tmpdir(env)
                check_env(env, overlay)
                with _DiscoveryGuard(p, [work, env["TMPDIR"]],
                                     (router.get("pid"), before["pid"]), ctx) as discovery_guard:
                    destination = provenance.opencode_v2_destination(
                        work,
                        {**env, "OPENCODE_PRINT_LOGS": "1"},
                        a.model,
                        run_dir,
                        binary,
                        overlay,
                        scaffold=SCAFFOLD,
                        runner=discovery_guard.run_grader,
                    )
                provenance.assert_served_config_unchanged(router, destination)
                prompt = (
                    f'Implement the solution in {entry["solution"]} so that the tests in {entry["test"]} pass. '
                    "The specification is in .docs/instructions.md — read it first. "
                    f'Do NOT modify {entry["test"]}. Do not create new files unless required by the spec.'
                )
                if kind:
                    prompt += " " + INJECT_ADDENDA[kind]
                evidence = (
                    workdir
                    / "opencode_transcripts"
                    / a.model
                    / (out.stem + "." + run_id)
                    / (a.lang + "__" + name)
                )
                initial = (work / entry["solution"]).read_bytes()
                result = run_item(
                    p,
                    model=a.model,
                    work=work,
                    prompt=prompt,
                    env=env,
                    binary=binary,
                    evidence=evidence,
                    entry=entry,
                    limit=limit,
                    private=private,
                    router=router,
                    base=base,
                    protected_pids=(before["pid"],),
                    policy=effective_policy(kind),
                    cancel=cancel,
                    ctx=ctx,
                )
                after = worker_identity(p, a.model, router)
                pg.require_identity(before, after)
                check_env(env, overlay)
                provenance.assert_served_config_unchanged(router, base)
                export = result.pop("export")
                artifacts = result.pop("evidence")
                changed = (work / entry["solution"]).is_file() and (
                    work / entry["solution"]
                ).read_bytes() != initial
                # M59/M61 rule kept: an untouched solution fails (go/ledger, go/markdown stubs pass every test).
                passed = result.pop("passed") and changed
                row = dict(
                    bench="opencode",
                    schema_version=3,
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
                    opencode_version=version,
                    stop_reason=result["gate"]["stop_reason"] or "completed",
                    events_path=p._portable(artifacts["events"]),
                    transcript_path=p._portable(artifacts["export"]),
                    evidence_sha256={k: p._sha_of(v) for k, v in artifacts.items()},
                    stderr_path=p._portable(artifacts["stderr"]),
                    prompt_date=p._prompt_date(),
                    loop_metrics=p.loop_metrics(p._metric_export(export)),
                    traffic=p.traffic_metrics(p._metric_export(export)),
                    **p._seed_row_fields(
                        item,
                        a.seed_base,
                        hashlib.sha256(
                            env["OPENCODE_CONFIG_CONTENT"].encode()
                        ).hexdigest(),
                    ),
                    **p._web_audit(
                        export, source, artifacts["export"], scaffold=SCAFFOLD
                    ),
                )
                rows.append(json.loads(p._scrub_pii(json.dumps(row))))
                pg.atomic_write(
                    out, ("".join(json.dumps(r) + "\n" for r in rows)).encode()
                )
                print(
                    f'{item}: passed={passed} nonconv={row["nonconv_kind"]}', flush=True
                )
        if a.expect_items:
            pg.expect_items(rows, [s.strip() for s in a.expect_items.split(",")])
    except BaseException as exc:
        status = ctx.get("cleanup_status")
        man["cleanup_status"] = status          # the receipt location (top level) on EVERY abort path
        man["transport_abort"] = dict(
            error=p._scrub_error(exc),
            cleanup_status=status,
            grade_reports=ctx.get("grade_reports", []),
            termination=ctx.get("termination"),
        )
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
