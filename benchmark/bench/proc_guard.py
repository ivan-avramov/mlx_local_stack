"""M62 best-effort process attribution, memory monitoring and durable artifacts.

A fork that detaches and leaves scratch between samples can escape attribution.
New same-uid orphans are diagnostic only and are never killed without attribution.
"""

from __future__ import annotations
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from .token_turn_gate import TransportAbort

POLICY = dict(
    silence_s=1200,
    silence_sample_s=60,
    idle_samples=3,
    idle_min_spacing_s=30,
    cancel_s=300,
    prefill_floor_tok_s=300,
    tracker_s=0.5,
    per_process=8 * 1024**3,
    aggregate=16 * 1024**3,
    client_limit=16 * 1024**3,
    container_memory="4g",
    container_swap="4g",
)


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fp:
            fp.write(data)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        if path.read_bytes() != data:
            raise TransportAbort("atomic write verification failed")
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_rows(path):
    path = Path(path)
    if not path.exists():
        return []
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise TransportAbort("torn rows file")
    try:
        rows = [json.loads(line) for line in raw.splitlines()]
        if any(not isinstance(r, dict) or "id" not in r for r in rows):
            raise ValueError()
        return rows
    except (ValueError, UnicodeError):
        raise TransportAbort("torn/invalid rows file") from None


def reserve_evidence(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb"):
            pass
    except FileExistsError:
        raise TransportAbort("immutable evidence path exists: " + path.name) from None


def require_identity(before, after):
    keys = ("pid", "create_time", "model_path", "registry_sha256")
    if (
        not isinstance(before, dict)
        or not isinstance(after, dict)
        or any(not before.get(k) or before[k] != after.get(k) for k in keys)
    ):
        raise TransportAbort("worker identity missing or drifted")


def expect_items(rows, expected):
    ids = [r["id"] for r in rows]
    if (
        len(ids) != len(set(ids))
        or len(expected) != len(set(expected))
        or set(ids) != set(expected)
    ):
        raise TransportAbort("expect-items: missing, unexpected or duplicate ids")


def in_flight(metrics):
    try:
        value = metrics["summary"]["in_flight"]
    except (KeyError, TypeError):
        raise TransportAbort("worker summary.in_flight missing") from None
    if type(value) is not int or value < 0:
        raise TransportAbort("invalid worker summary.in_flight")
    return value


class SilenceObserver:
    def __init__(self):
        self.last_sample = None
        self.size = None
        self.idle = 0

    def sample(self, now, size, metrics, descendant_alive):
        busy = in_flight(metrics)
        growth = self.size is not None and size != self.size
        self.size = size
        if busy or growth:
            self.idle = 0
            self.last_sample = now
            return None
        if self.last_sample is not None and now - self.last_sample < POLICY["idle_min_spacing_s"]:
            return None
        self.last_sample = now
        self.idle += 1
        if self.idle < POLICY["idle_samples"]:
            return None
        return "exec_timeout" if descendant_alive else "client_exit_hang"


def silence(metrics, descendant_alive):
    # Classification after the observation window; retained for direct callers.
    if in_flight(metrics) > 0:
        return None
    return "exec_timeout" if descendant_alive else "client_exit_hang"


def wait_cancel(metrics, *, prompt_tokens=0, timeout=None, sleep=time.sleep, now=time.monotonic):
    bound = max(POLICY["cancel_s"], prompt_tokens / POLICY["prefill_floor_tok_s"])
    deadline = now() + (bound if timeout is None else timeout)
    while in_flight(metrics()) != 0:
        if now() >= deadline:
            raise TransportAbort("worker health: did not cancel")
        sleep(0.5)


@contextmanager
def defer_signals(*, deliver=False):
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    pending = []
    try:
        for sig in previous:
            signal.signal(sig, lambda sig, frame: pending.append((sig, frame)))
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if deliver and pending:
            sig, frame = pending[0]
            handler = previous[sig]
            if callable(handler):
                handler(sig, frame)
            elif handler == signal.SIG_DFL:
                signal.raise_signal(sig)


class ProcessGuard:
    def __init__(
        self,
        roots,
        *,
        scan=None,
        get=None,
        per_process=8 * 1024**3,
        aggregate=16 * 1024**3,
        client_limit=16 * 1024**3,
        interval=0.5,
        run_id=None,
        item="grade",
        protected_pids=(),
    ):
        import psutil

        self.psutil = psutil
        self.excluded_pids = {os.getpid(), os.getppid()}
        self.excluded_pids.update(p.pid for p in psutil.Process().parents())
        self.excluded_pids.update(protected_pids)
        self.probe_session = os.getsid(0)
        self.scan = scan or psutil.process_iter
        self.get = get or psutil.Process
        self.roots = [str(Path(p).resolve()) for p in roots]
        self.per_process = per_process
        self.aggregate = aggregate
        self.client_limit = client_limit
        self.interval = interval
        self.started = time.time()
        self.tracked = {}
        self.acquiring = set()
        self.containers = set()
        self.orphans_unattributed = []
        self.shell_descendants = set()
        self.mem_kills = []
        self.grader_mem_kill = False
        self.client_resource = False
        self.failure = None
        self.thread = None
        self.done = threading.Event()
        self.lock = threading.RLock()
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.item = item.replace("/", "-")
        self.container_sequence = 0

    def container_name(self):
        with self.lock:
            self.container_sequence += 1
            return f"mlxbench-{self.run_id}-{self.item}-{self.container_sequence}"

    def register(self, process, role):
        with self.lock:
            if self._protected(process):
                raise TransportAbort("refused ownership of protected process")
            self.tracked[(process.pid, process.create_time())] = role

    def _protected(self, process):
        return process.pid in self.excluded_pids or process.create_time() < self.started

    def _live(self, process):
        return process.status() not in ("zombie", "dead")

    def _processes(self):
        found = []
        for p in self.scan():
            try:
                if p.uids().real == os.getuid() and self._live(p):
                    found.append(p)
            except (self.psutil.NoSuchProcess, self.psutil.AccessDenied):
                continue
        return found

    def _attributed_path(self, p):
        values = [p.cwd(), *p.cmdline()]
        return any(
            v == root or v.startswith(root + "/") or ("=" + root + "/") in v
            for root in self.roots
            for v in values
        )

    def tick(self):
        with self.lock:
            processes = self._processes()
            alive = {}
            for p in processes:
                try:
                    if not self._protected(p):
                        alive[p.pid] = (p, p.create_time())
                except self.psutil.NoSuchProcess:
                    pass
            # Follow ancestry until its transitive closure; detachments retain recorded ownership.
            changed = True
            while changed:
                changed = False
                for pid, (p, created) in alive.items():
                    key = (pid, created)
                    try:
                        parent = alive.get(p.ppid())
                    except self.psutil.NoSuchProcess:
                        continue
                    if key not in self.tracked and parent:
                        role = self.tracked.get((parent[0].pid, parent[1]))
                        if role:
                            self.tracked[key] = "model" if role == "client" else role
                            changed = True
                    if self.tracked.get(key) == "model":
                        try:
                            argv = p.cmdline()
                            is_shell = bool(
                                argv
                                and Path(argv[0]).name
                                in ("sh", "bash", "zsh", "dash", "ksh", "fish")
                            )
                            parent_key = (parent[0].pid, parent[1]) if parent else None
                            if is_shell or parent_key in self.shell_descendants:
                                self.shell_descendants.add(key)
                        except self.psutil.NoSuchProcess:
                            pass
            memory = []
            for key, role in list(self.tracked.items()):
                pair = alive.get(key[0])
                if not pair or pair[1] != key[1]:
                    continue
                p = pair[0]
                try:
                    rss = p.memory_info().rss
                    limit = self.client_limit if role == "client" else self.per_process
                    if rss > limit:
                        self._mem_kill(p, key, role)
                    elif role != "client":
                        memory.append((rss, p, key, role))
                except self.psutil.NoSuchProcess:
                    continue
            total = sum(x[0] for x in memory)
            for rss, p, key, role in sorted(memory, key=lambda x: x[0], reverse=True):
                if total <= self.aggregate:
                    break
                self._mem_kill(p, key, role)
                total -= rss

    def _mem_kill(self, p, key, role):
        if self._protected(p) or p.create_time() != key[1]:
            return
        p.kill()
        if role == "client":
            self.client_resource = True
        elif role == "grader":
            self.grader_mem_kill = True
        else:
            self.mem_kills.append(dict(pid=p.pid, create_time=key[1]))

    def _monitor(self):
        try:
            while not self.done.is_set():
                self.tick()
                self.done.wait(self.interval)
        except BaseException as exc:
            self.failure = exc

    def start(self):
        self.thread = threading.Thread(
            target=self._monitor, name="m62-process-watch", daemon=True
        )
        self.thread.start()
        return self

    def check(self):
        if self.failure or (
            self.thread and not self.done.is_set() and not self.thread.is_alive()
        ):
            raise TransportAbort("process monitor died: " + str(self.failure))

    def spawn(self, cmd, *, role="client", **kwargs):
        self.check()
        if not self.thread:
            self.start()
        # Serialize spawn/registration against samples; the tracker is already running.
        with defer_signals(deliver=True), self.lock:
            proc = subprocess.Popen(cmd, **kwargs)
            self.acquiring.add(proc)
            try:
                try:
                    self.register(self.get(proc.pid), role)
                except self.psutil.NoSuchProcess:
                    if proc.poll() is None:
                        raise
            except BaseException:
                # The Popen handle is ownership evidence even if psutil registration failed.
                proc.kill()
                proc.wait(timeout=10)
                self.acquiring.discard(proc)
                raise
            self.acquiring.discard(proc)
        return proc

    def run_grader(
        self, cmd, *, capture_output=False, text=False, timeout=None, **kwargs
    ):
        if capture_output:
            kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc = self.spawn(cmd, role="grader", text=text, **kwargs)
        try:
            out, err = proc.communicate(timeout=timeout)
            self.check()
            return subprocess.CompletedProcess(cmd, proc.returncode, out, err)
        except subprocess.TimeoutExpired:
            self.kill_role("grader")
            proc.communicate()
            raise

    def kill_role(self, role=None):
        with self.lock:
            try:
                # Capture ancestry before killing the parent reparents its children.
                self.tick()
            finally:
                for (pid, created), actual in list(self.tracked.items()):
                    if role is not None and actual != role:
                        continue
                    try:
                        p = self.get(pid)
                        if not self._protected(p) and p.create_time() == created and self._live(p):
                            p.kill()
                    except self.psutil.NoSuchProcess:
                        pass

    def descendants_alive(self):
        for p in self._processes():
            if (p.pid, p.create_time()) in self.shell_descendants:
                return True
        return False

    def register_container(self, name):
        with self.lock:
            self.containers.add(name)

    def container_oom(self, name):
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.OOMKilled}}", name],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

    def remove_container(self, name):
        subprocess.run(
            ["docker", "rm", "-f", name], capture_output=True, text=True, timeout=30
        )
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                "name=^/" + name + "$",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode or result.stdout.strip():
            raise TransportAbort("container cleanup uncertain")
        self.containers.discard(name)

    def _sweep_excluded(self, p):
        if p.pid in self.excluded_pids:
            return True
        try:
            return os.getsid(p.pid) == self.probe_session
        except ProcessLookupError:
            return False

    def cleanup(self):
        with defer_signals():
            self.done.set()
            if self.thread:
                self.thread.join(5)
            for proc in list(self.acquiring):
                proc.kill()
                proc.wait(timeout=10)
                self.acquiring.discard(proc)
            self.kill_role()
            for name in list(self.containers):
                self.remove_container(name)
            survivors = []
            orphans = {}
            uncertain = False
            for attempt in range(3):
                survivors = []
                for p in self._processes():
                    try:
                        if self._protected(p):
                            continue
                        key = (p.pid, p.create_time())
                        if key in self.tracked:
                            p.kill()
                            survivors.append(p.pid)
                        elif self._attributed_path(p):
                            uncertain = True
                            orphans[key] = dict(pid=p.pid, create_time=key[1],
                                                argv=p.cmdline(), reason="path-only attribution")
                        elif self._sweep_excluded(p):
                            continue
                        elif p.ppid() == 1 and p.create_time() >= self.started:
                            orphans[key] = dict(
                                pid=p.pid, create_time=p.create_time(), argv=p.cmdline()
                            )
                    except self.psutil.NoSuchProcess:
                        continue
                if not survivors:
                    break
                time.sleep(0.05)
            self.orphans_unattributed[:] = list(orphans.values())
            if uncertain:
                raise TransportAbort("cleanup uncertain: path-only processes remain " + json.dumps(
                    [dict(pid=p["pid"], create_time=p["create_time"])
                     for p in orphans.values() if p.get("reason") == "path-only attribution"]
                ))
            if survivors:
                raise TransportAbort("attributed processes survived cleanup")
            if self.failure:
                raise TransportAbort("process monitor died: " + str(self.failure))

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.cleanup()
