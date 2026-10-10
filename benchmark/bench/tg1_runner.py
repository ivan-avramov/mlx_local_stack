"""M62-only orchestration. The legacy v2 runner never constructs these components."""

from __future__ import annotations
import hashlib
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
            print(json.dumps(dict(m62_watch=self.report, phase=self.phase,
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


def identity(p, selection, universe_sha, version, binary):
    policy = dict(
        gate=tg.POLICY,
        hygiene=pg.POLICY,
        toolbounds_sha256=p._sha_of(PLUGIN),
        noretry_sha256=p._sha_of(p.NORETRY_PLUGIN),
        carrier_sha256=selection["fields"]["opencode_bench_config_sha256"],
        universe_sha256=universe_sha,
        grader_version=sg.VERSION,
        grader_timeout_s=sg.TIMEOUTS,
        grade_join_timeout_s=grade_join_timeout_s(),
        plugin_proof="GET /api/integration awaits Plugin.awaitActivation",
        env=p.SCAFFOLD_ENV_POLICY_V2,
        scaffold=SCAFFOLD,
    )
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
    return dict(
        scaffold=SCAFFOLD,
        policy=policy,
        scaffold_policy_sha256=hashlib.sha256(
            json.dumps(policy, sort_keys=True).encode()
        ).hexdigest(),
        probe_code_sha256=digest.hexdigest(),
        opencode_version=version,
        opencode_exe_sha256=p._sha_of(binary),
    )


def run_item(
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
):
    gate = tg.TokenTurnGate(
        entry["baseline_failing"],
        context_limit=limit,
        universe_size=len(entry["leaves"]),
    )
    lock = threading.RLock()
    observations = []
    termination = {}
    silence_observer = pg.SilenceObserver()
    exit_hang = False
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
    started = time.monotonic()
    stop = threading.Event()
    ingest_failure = []
    guard = pg.ProcessGuard(
        [work, env["TMPDIR"], private],
        run_id=Path(private).parent.name,
        item=entry.get("id", work.name),
        protected_pids=(*protected_pids, router.get("pid")),
    )

    def grade(snap):
        modified = sg.tampered(
            snap.path, entry["protected"], entry["prepared"], entry["lang"]
        )
        if modified:
            return None, True
        result = sg.grade(entry["lang"], snap.path, entry["test"], private, guard=guard)
        resources["grader_mem_kill"] |= result.grader_mem_kill
        resources["grader_oom"] |= result.grader_oom
        return result.failing({tuple(x) for x in entry["leaves"]}), False

    worker = GradeWorker(gate, lock, work, private, grade)
    stream = tg.EventStream(gate, worker.notify)
    proc = None
    client_launch_attempted = False
    ingester = None
    killed = False
    final_result = None
    cancellation_attempted = False
    heartbeat = PhaseHeartbeat(gate, lock, started)

    def terminate_client(reason=None):
        nonlocal killed, cancellation_attempted
        if cancellation_attempted:
            return
        with lock:
            if reason and reason != "client_exit_hang":
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
        errors = []
        for role in ("client", "model"):
            try:
                guard.kill_role(role)
            except Exception as exc:  # noqa: BLE001 — cancellation must still run (V5a P14)
                errors.append(exc)
        cancellation_attempted = True
        pg.wait_cancel(lambda: worker_json("metrics"),
                       prompt_tokens=gate.request_usage[-1][2] if gate.request_usage else 0)
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
            tg.reconcile(
                stream,
                export,
                proc.returncode,
                "client_exit_hang" if exit_hang and not gate.stop_reason else
                gate.stop_reason if killed or guard.client_resource else None,
            )
        except tg.TransportAbort as exc:
            if exit_hang:
                raise tg.TransportAbort("client silent, worker idle: " + str(exc)) from exc
            raise
        final_boundary_actual = len(gate.request_usage)
        if final_boundary != final_boundary_actual:
            gate.pending.discard(final_boundary)
            gate.pending.add(final_boundary_actual)
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
                    entry["lang"], snap.path, entry["test"], private, guard=guard
                )
                resources["grader_mem_kill"] |= final_result.grader_mem_kill
                resources["grader_oom"] |= final_result.grader_oom
                failing = final_result.failing({tuple(x) for x in entry["leaves"]})
            gate.terminal(None, (final_boundary_actual, failing, failing is not None, modified))
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
            termination=termination,
            client_exit_hang=exit_hang,
            torn_tail=stream.torn_tail,
            event_types_seen=stream.event_types_seen,
            evidence=paths,
            mem_kills=guard.mem_kills,
            orphans_unattributed=guard.orphans_unattributed,
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
                        guard.cleanup()
                        if proc and proc.poll() is None:
                            proc.wait(timeout=10)
        finally:
            heartbeat.close()


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


def _main(p, a, names):
    selection = p._carrier_selection(SCAFFOLD, a.agent_system_file, source=CARRIER)
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

    with p._scratch_dir("tg1-discovery") as scratch:
        p._git_init_scratch(scratch)
        overlay = p._seed_overlay(
            a.model, p._item_seed(a.lang + "/" + names[0], a.seed_base)
        )
        env = p._opencode_env(run_dir, scratch, overlay)
        p._fresh_tmpdir(env)
        check_env(env, overlay)
        with pg.ProcessGuard([scratch, env["TMPDIR"]],
                             protected_pids=(router.get("pid"), before["pid"])) as discovery_guard:
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
    ident = identity(p, selection, universe_sha, version, binary)
    ident.update(
        seed_base=a.seed_base,
        lang=a.lang,
        polyglot_sha=p._polyglot_sha(p._polyglot_root()),
        a4_v2_pass=bool(receipt),
        **selection["fields"],
    )
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
        for name in names:
            item = a.lang + "/" + name
            if any(r["id"] == item for r in rows):
                continue
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
                with pg.ProcessGuard([work, env["TMPDIR"]],
                                     protected_pids=(router.get("pid"), before["pid"])) as discovery_guard:
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
        man["transport_abort"] = dict(error=p._scrub_error(exc))
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
