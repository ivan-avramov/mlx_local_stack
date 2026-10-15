"""M62 best-effort process attribution, memory monitoring and durable artifacts.

A fork that detaches and leaves scratch between samples can escape attribution.
New same-uid orphans are diagnostic only and are never killed without attribution.
"""

from __future__ import annotations
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import shlex
import signal
import stat
import subprocess
import sys
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


def start_time(proc):
    """Process identity start time. On macOS psutil's create_time() shifts by INIT_BOOT_TIME - boot_time() once a
    wall-clock correction moves whole-second boot time (C151), so read the unadjusted kernel value; objects without
    a psutil implementation (test fakes) keep their own create_time()."""
    if sys.platform == "darwin":
        import psutil

        if isinstance(proc, psutil.Process):
            impl = getattr(proc, "_proc", None)
            if impl is None or not hasattr(impl, "create_time"):
                raise TransportAbort("psutil lost the unadjusted start-time path (C151); refusing identity")
            return impl.create_time(monotonic=True)
    return proc.create_time()


_DARWIN = {}


def _darwin_lib():
    """ctypes handles for proc_pid_rusage / mach_absolute_time (lazy, macOS only)."""
    if not _DARWIN:
        import ctypes
        import ctypes.util

        class RusageInfoV0(ctypes.Structure):
            _fields_ = [("uuid", ctypes.c_uint8 * 16)] + [(n, ctypes.c_uint64) for n in (
                "user_time", "system_time", "pkg_idle_wkups", "interrupt_wkups", "pageins", "wired_size",
                "resident_size", "phys_footprint", "proc_start_abstime", "proc_exit_abstime")]
        libproc = ctypes.CDLL(ctypes.util.find_library("proc"), use_errno=True)
        libproc.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(RusageInfoV0)]
        libc = ctypes.CDLL(None)
        libc.mach_absolute_time.restype = ctypes.c_uint64
        _DARWIN.update(ctypes=ctypes, libproc=libproc, libc=libc, info=RusageInfoV0)
    return _DARWIN


def clock_order():
    """Monotonic 'now' in start_order() units: mach_absolute_time on macOS, None elsewhere (wall-clock fallback)."""
    if sys.platform != "darwin":
        return None
    return int(_darwin_lib()["libc"].mach_absolute_time())


def start_order(proc):
    """Monotonic process start for ORDERING decisions (older than the guard, parent younger than child), which a
    wall-clock step must not reorder (C151 R8). Identity stays start_time(). macOS: proc_pid_rusage
    ri_proc_start_abstime (ESRCH -> NoSuchProcess, EPERM/EACCES -> AccessDenied, anything else -> TransportAbort).
    Objects with their own
    start_order() (test fakes) use it; anything else returns None and callers fall back to wall-clock start."""
    own = getattr(proc, "start_order", None)
    if callable(own):
        return own()
    if sys.platform != "darwin":
        return None
    import psutil

    if not isinstance(proc, psutil.Process):
        return None
    d = _darwin_lib()
    info = d["info"]()
    if d["libproc"].proc_pid_rusage(int(proc.pid), 0, d["ctypes"].byref(info)) != 0:
        err = d["ctypes"].get_errno()
        if err == 3:  # ESRCH
            raise psutil.NoSuchProcess(proc.pid)
        if err in (1, 13):  # EPERM, EACCES
            raise psutil.AccessDenied(proc.pid)
        raise TransportAbort(f"proc_pid_rusage({proc.pid}) failed: errno {err}")
    return int(info.proc_start_abstime)


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
        drift = ([f"{k}: {before.get(k)!r} -> {after.get(k)!r}" for k in keys if before.get(k) != after.get(k)]
                 if isinstance(before, dict) and isinstance(after, dict) else ["not a dict"])
        raise TransportAbort("worker identity missing or drifted (" + "; ".join(drift or ["empty field"]) + ")")


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
    """Block until the worker reports no request in flight; return the elapsed seconds (C147)."""
    bound = max(POLICY["cancel_s"], prompt_tokens / POLICY["prefill_floor_tok_s"])
    started = now()
    deadline = started + (bound if timeout is None else timeout)
    while in_flight(metrics()) != 0:
        if now() >= deadline:
            raise TransportAbort("worker health: did not cancel")
        sleep(0.5)
    return now() - started


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
        scrub=None,
        context=None,
    ):
        import psutil

        self.psutil = psutil
        # A process mid-exit can raise AccessDenied on macOS (sysctl KERN_PROCARGS2 -> EINVAL) instead of
        # NoSuchProcess; either way the monitor skips it for that tick (C148).
        self._transient = (psutil.NoSuchProcess, psutil.AccessDenied)
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
        self.started_order = clock_order()     # C151 R8: ordering is monotonic
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
        # C147: argv recorded in evidence passes through the caller's PII scrubber; `context()` returns
        # {completed_requests: int} at the instant of a memory kill (request linkage).
        self.scrub = scrub or (lambda text: text)
        self.context = context
        self.killed = []
        self._unreadable_overflow = False
        self._unreadable_seen = {}      # C157: unreadable identities (+ listing descendants) noted by tick()/cleanup
        self._status = None

    def container_name(self):
        with self.lock:
            self.container_sequence += 1
            return f"mlxbench-{self.run_id}-{self.item}-{self.container_sequence}"

    def register(self, process, role):
        with self.lock:
            if self._protected(process):
                raise TransportAbort("refused ownership of protected process")
            self.tracked[(process.pid, start_time(process))] = role

    def _older_than_guard(self, process):
        order = start_order(process)
        if order is None or self.started_order is None:
            return start_time(process) < self.started
        return order < self.started_order

    def _protected(self, process):
        return process.pid in self.excluded_pids or self._older_than_guard(process)

    def _same_identity(self, pid, created):
        try:
            return start_time(self.get(pid)) == created
        except (self.psutil.NoSuchProcess, self.psutil.AccessDenied):
            return False

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
            ppids = {}
            edges = self._listing_edges(processes)       # BEFORE any start-order read can see a process exit
            readable = {}
            for p in processes:
                try:
                    try:
                        protected = self._protected(p)
                    except self.psutil.AccessDenied:
                        # C157 (review round 1 P2): keep the identity and the listing's descendants, so a cleanup that
                        # runs after this process exits still knows who its children were
                        self._note_unreadable(self._unreadable_seen, p, edges)
                        continue
                    if not protected:
                        # ppid() re-validates identity; a stale cached entry (pid reused, psutil keeps the old
                        # create_time) raises here and must never become an ancestry authority (V5a P13).
                        ppids[p.pid] = p.ppid()
                        alive[p.pid] = (p, start_time(p), start_order(p))
                    readable[p.pid] = p      # only after EVERY required read succeeded (round 3 P2)
                except self._transient:
                    ppids.pop(p.pid, None)
                    alive.pop(p.pid, None)
            for key in [k for k in self._unreadable_seen          # exact identity only: never a pid wildcard
                        if k[1] is not None and k[0] in readable and self._created_or_none(readable[k[0]]) == k[1]]:
                del self._unreadable_seen[key]      # classified readable now: the ambiguity is resolved (round 2 P4)
            # Follow ancestry until its transitive closure; detachments retain recorded ownership.
            changed = True
            while changed:
                changed = False
                for pid, (p, created, order) in alive.items():
                    key = (pid, created)
                    parent = alive.get(ppids[pid])
                    if parent and (parent[2] > order if None not in (parent[2], order) else parent[1] > created):
                        parent = None   # a parent cannot be younger than its child: pid reuse (monotonic, C151 R8)
                    if parent and not self._same_identity(parent[0].pid, parent[1]):
                        parent = None
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
                        except self._transient:
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
                        self._mem_kill(p, key, role, rss)
                    elif role != "client":
                        memory.append((rss, p, key, role))
                except self._transient:
                    continue
            total = sum(x[0] for x in memory)
            for rss, p, key, role in sorted(memory, key=lambda x: x[0], reverse=True):
                if total <= self.aggregate:
                    break
                try:
                    self._mem_kill(p, key, role, rss)
                except self._transient:
                    pass        # exiting: its memory is being released either way
                total -= rss

    def _argv(self, p):
        try:
            return [self.scrub(str(x)) for x in p.cmdline()]
        except self._transient:
            return []

    def _mem_kill(self, p, key, role, rss=None):
        if self._protected(p) or start_time(p) != key[1]:
            return
        argv = self._argv(p)
        completed = None
        if self.context is not None and role not in ("client", "grader"):
            try:
                completed = self.context().get("completed_requests")
            except Exception:  # noqa: BLE001 — linkage is evidence, never a reason to skip the kill
                completed = None
        p.kill()
        if role == "client":
            self.client_resource = True
        elif role == "grader":
            self.grader_mem_kill = True
        else:
            self.mem_kills.append(dict(
                pid=p.pid, create_time=key[1], role=role, rss=rss, argv=argv,
                tool_call_id=None,
                carrying_request=None if completed is None else completed + 1,
                completed_boundary_at_kill=completed,
            ))

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
        """SIGKILL every tracked live process of `role`; return [{pid, create_time, role, argv}] (C147)."""
        killed = []
        failure = None
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
                        if not self._protected(p) and start_time(p) == created and self._live(p):
                            argv = self._argv(p)
                            p.kill()
                            killed.append(dict(pid=pid, create_time=created, role=actual, argv=argv))
                    except self._transient:   # AccessDenied: the sweep below marks it uncertain
                        pass
                    except TransportAbort as exc:   # unreadable identity/order: kill the rest, then raise (C151 R15)
                        failure = failure or exc
                self.killed.extend(killed)
            if failure is not None:
                raise failure
        return killed

    def graceful_stop(self, role, wait, before_signal=None, after_signal=None):
        """SIGTERM every tracked live process of `role` and wait up to `wait` seconds for them to exit.

        `before_signal()` is called once, after the scan and identity checks and immediately before the first
        SIGTERM, and returns a token (the cutoff, captured but NOT yet committed); `after_signal(token)` is called
        once, only after a `terminate()` has actually succeeded. When nothing is signalled, or every terminate
        raises, neither commits anything (C147 Q22/Q28).

        Returns [{pid, create_time, role, argv}] of the processes signalled; survivors are the caller's to
        SIGKILL (`kill_role`). Ancestry is sampled first, as in `kill_role` (C147)."""
        signalled = []
        with self.lock:
            self.tick()
            targets = []
            for (pid, created), actual in list(self.tracked.items()):
                if actual != role:
                    continue
                try:
                    p = self.get(pid)
                    if not self._protected(p) and start_time(p) == created and self._live(p):
                        targets.append((p, pid, created, actual, self._argv(p)))
                except self._transient:
                    pass
            token = before_signal() if targets and before_signal is not None else None
            for p, pid, created, actual, argv in targets:
                try:
                    p.terminate()
                    if not signalled and after_signal is not None:
                        after_signal(token)
                    signalled.append(dict(pid=pid, create_time=created, role=actual, argv=argv))
                except self._transient:
                    pass
        self.verify_gone(signalled, wait=wait)
        return signalled

    def _identity_state(self, pid, created):
        """"alive" | "gone" | "unknown" for one (pid, create_time) identity. A denied inspection (uids,
        create_time or liveness) is UNKNOWN, never "gone"."""
        try:
            process = self.get(pid)
            process.uids()
            if start_time(process) != created:
                return "gone"            # the pid was reused: our process is not there
            return "alive" if self._live(process) else "gone"
        except (self.psutil.NoSuchProcess, StopIteration):
            return "gone"
        except (self.psutil.AccessDenied, TransportAbort):   # unreadable identity is never "gone" (C151 R16)
            return "unknown"

    def verify_gone(self, killed, wait=0.0):
        """True only when every killed (pid, create_time) is verifiably gone (polled up to `wait` seconds);
        a process whose liveness cannot be determined makes this False."""
        deadline = time.monotonic() + wait
        while True:
            states = [self._identity_state(e["pid"], e["create_time"]) for e in killed]
            if all(state == "gone" for state in states):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    def status(self):
        """Cleanup outcome for abort manifests; `uncertain` until cleanup() has completed (C147)."""
        if self._status is None:
            return dict(survivors=[], containers_remaining=sorted(self.containers),
                        uncertain=True, orphans_unattributed=list(self.orphans_unattributed),
                        unknown=[], completed=False)
        return dict(self._status)

    def descendants_alive(self):
        for p in self._processes():
            if (p.pid, start_time(p)) in self.shell_descendants:
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

    def _created_or_none(self, p):
        try:
            return start_time(p)
        except (*self._transient, TransportAbort):
            return None

    def _listing_edges(self, listing):
        """(children_of {ppid: [process]}, unknown [process]) for one listing, O(N): processes whose parent cannot
        be read (one retry) stay candidate descendants of any unreadable process (C157, round 1 P5)."""
        children_of, unknown = {}, []
        for p in listing:
            for attempt in range(2):
                try:
                    children_of.setdefault(p.ppid(), []).append(p)
                    break
                except self._transient:
                    continue
            else:
                unknown.append(p)
        return children_of, unknown

    def _note_unreadable(self, store, p, edges):
        """Record an eligible process whose start order cannot be read, with the TRANSITIVE descendants of the
        listing (edges read BEFORE any per-process start-order read) and everything of unreadable parentage, closed
        over those edges: a vanished parent proves nothing about them (P297 U1). Candidates are IDENTITIES
        (pid, start time), so a reused pid adds a second candidate instead of masquerading as the first. Bounded:
        at most 32 roots and 2048 identities are ever retained; past either limit nothing more is stored or
        traversed and `_unreadable_overflow` stays set (permanent, fail-closed: cleanup is uncertain)."""
        if self._unreadable_overflow:
            return
        children_of, unknown = edges
        key = (p.pid, self._created_or_none(p))
        if key not in store and len(store) >= 32:
            self._unreadable_overflow = True
            return
        room = 2048 - sum(len(v["children"]) for v in store.values())
        entry = store.setdefault(key, dict(children=set()))

        def add(proc):
            nonlocal room
            identity = (proc.pid, self._created_or_none(proc))
            if identity in entry["children"]:
                return True
            if room <= 0:
                self._unreadable_overflow = True
                return False
            entry["children"].add(identity)
            room -= 1
            return True
        seen, frontier = {p.pid}, [p.pid]
        for q in unknown:
            if q.pid != p.pid:
                if not add(q):
                    return
                frontier.append(q.pid)
        while frontier:
            for child in children_of.get(frontier.pop(), ()):
                if child.pid not in seen:
                    seen.add(child.pid)
                    if not add(child):
                        return
                    frontier.append(child.pid)

    def _existence(self, pid, created):
        """C157: (kind, occupant start time) for a pid whose identity could not be read; kind is "gone" | "readable"
        | "present". Gone is proven only by NoSuchProcess, or - when the original start time was captured - by a
        different start time or a dead state (pid reuse: the original is gone, the replacement must still pass the
        normal scan, so the occupant's identity is part of the observation). "readable": it exists and can be
        classified now, so the next full scan decides it. Anything unreadable is present."""
        try:
            process = self.get(pid)
        except (self.psutil.NoSuchProcess, StopIteration):
            return "gone", None
        except (self.psutil.AccessDenied, TransportAbort):
            return "present", None
        try:
            occupant = self._created_or_none(process)
            if occupant is None:
                return "present", None        # occupied, identity unreadable: never aliased to an absent pid
            if created is not None:
                if occupant != created:
                    return "gone", occupant
                if not self._live(process):
                    return "gone", occupant
            self._protected(process)
            return "readable", occupant
        except self.psutil.NoSuchProcess:
            return "gone", None
        except (self.psutil.AccessDenied, TransportAbort):
            return "present", None

    def _reconcile_unreadable(self, unreadable):
        """C157: resolve every unreadable-identity record against the process table NOW, never from a flag frozen
        earlier. Returns ({key: orphan record} still unresolved, {key: state}). A still-present unreadable
        process stays uncertain (C151 R10). A gone/readable one clears only itself; every state CHANGE since the
        previous reconcile forces another full scan (caller); each descendant listed with a vanished parent must
        itself be gone, protected/pre-existing, or tracked (the tracked audit kills it), otherwise it is unresolved
        (P297 U1)."""
        bad, states = {}, {}
        for key, info in unreadable.items():
            pid, created = key
            state = states[key] = self._existence(pid, created)
            if state[0] == "present":
                bad[(pid, None)] = dict(pid=pid, create_time=None, argv=[], reason="start order unreadable")
                continue
            if state[0] == "readable" and created is not None:
                continue                    # the SAME identity is alive and classifiable: the next scan owns its children
            # gone, or an identity we never captured (a readable occupant may be a replacement): the recorded
            # descendants must each be resolved
            for child_pid, child_created in info["children"]:
                states[(key, child_pid, child_created)] = self._existence(child_pid, child_created)
                reason = dict(pid=child_pid, create_time=child_created, argv=[],
                              reason="child of vanished unreadable process")
                if child_created is None:
                    if self._existence(child_pid, None)[0] != "gone":
                        bad[(child_pid, None)] = reason
                    continue
                child_state = self._identity_state(child_pid, child_created)
                if child_state == "gone" or (child_pid, child_created) in self.tracked:
                    continue
                try:
                    if child_state == "alive" and self._protected(self.get(child_pid)):
                        continue
                except (*self._transient, TransportAbort, StopIteration):
                    pass
                bad[(child_pid, child_created)] = reason
        return bad, states

    def cleanup(self):
        with defer_signals():
            self.done.set()
            if self.thread:
                self.thread.join(5)
            for proc in list(self.acquiring):
                proc.kill()
                proc.wait(timeout=10)
                self.acquiring.discard(proc)
            order_failure = None
            try:
                self.kill_role()
            except TransportAbort as exc:     # e.g. a persistent unexpected start-order errno (C151 R12): finish first
                order_failure = exc
            container_failure = None
            for name in list(self.containers):
                try:
                    self.remove_container(name)
                except TransportAbort as exc:
                    container_failure = container_failure or exc
            survivors = []
            orphans = {}
            uncertain = container_failure is not None or order_failure is not None
            with self.lock:
                unreadable = {k: dict(children=set(v["children"])) for k, v in self._unreadable_seen.items()}
            previous, bad, non_converged = {}, {}, False      # C157: reconciled after every full scan
            for round_ in range(5):
                for attempt in range(3):
                    survivors = []
                    listing = self._processes()
                    edges = self._listing_edges(listing)
                    for p in listing:
                        try:
                            try:
                                protected = self._protected(p)
                            except (self.psutil.AccessDenied, TransportAbort):
                                # an eligible same-uid process whose start/order cannot be read could be ours: it is
                                # resolved against the final process table, not frozen uncertain (C157; C151 R10). The
                                # children of THIS listing are kept: a vanished parent proves nothing about them.
                                self._note_unreadable(unreadable, p, edges)
                                continue
                            if protected:
                                continue
                            key = (p.pid, start_time(p))
                            if key in self.tracked:
                                p.kill()
                                survivors.append(p.pid)
                            elif self._attributed_path(p):
                                uncertain = True
                                orphans[key] = dict(pid=p.pid, create_time=key[1],
                                                    argv=p.cmdline(), reason="path-only attribution")
                            elif self._sweep_excluded(p):
                                continue
                            elif p.ppid() == 1 and not self._older_than_guard(p):
                                orphans[key] = dict(
                                    pid=p.pid, create_time=start_time(p), argv=p.cmdline()
                                )
                        except self.psutil.NoSuchProcess:
                            continue
                        except TransportAbort:      # identity unreadable (C151 R16): could be ours -> uncertain
                            uncertain = True
                            orphans[(p.pid, None)] = dict(pid=p.pid, create_time=None, argv=[],
                                                          reason="identity unreadable")
                            continue
                        except self.psutil.AccessDenied:
                            # macOS denies cwd()/cmdline() for a process mid-exit or one we may not inspect. Untracked:
                            # nothing to clear, skip. Tracked: ownership cannot be shown cleared -> uncertain.
                            if any(k[0] == p.pid for k in self.tracked):
                                uncertain = True
                                orphans[(p.pid, None)] = dict(pid=p.pid, create_time=None, argv=[],
                                                              reason="access denied")
                            continue
                    if not survivors:
                        break
                    time.sleep(0.05)
                # Audit every tracked identity directly, independent of the filtered scan above (which silently drops
                # a process whose uids()/status() is denied). Denied inspection = unknown = uncertain.
                unknown = []
                for attempt in range(3):
                    alive, unknown = [], []
                    for (pid, created) in list(self.tracked):
                        state = self._identity_state(pid, created)
                        if state == "alive":
                            try:
                                if self._protected(self.get(pid)):
                                    continue         # a protected (router/worker/ancestor) pid is never ours to clear
                            except (*self._transient, TransportAbort):
                                state = "unknown"
                        if state == "alive":
                            alive.append((pid, created))
                        if state == "unknown":
                            unknown.append(dict(pid=pid, create_time=created))
                    if not alive:
                        break
                    for pid, created in alive:
                        try:
                            process = self.get(pid)
                            if start_time(process) == created and not self._protected(process):
                                process.kill()
                        except (*self._transient, TransportAbort):
                            pass
                    time.sleep(0.05)
                else:
                    pass
                # C157: every state change (vanished, pid-reused, now readable, readable then gone) needs a full scan
                # AFTER it; a still-present one gets a short settle before it is called uncertain
                for settle in range(3):
                    bad, states = self._reconcile_unreadable(unreadable)
                    changed = any(state != previous.get(key, "present") for key, state in states.items())
                    if changed or not bad:
                        break
                    time.sleep(0.05)
                previous = states
                if not changed:
                    break
                if round_ == 4:
                    non_converged = True
            orphans.update(bad)
            uncertain = uncertain or bool(bad)
            if self._unreadable_overflow:
                uncertain = True
                orphans[(0, "overflow")] = dict(pid=0, create_time=None, argv=[], reason="unreadable records overflowed")
            if non_converged:
                uncertain = True
                orphans[(0, "did not converge")] = dict(pid=0, create_time=None, argv=[], reason="scan did not converge")
            survivors = sorted(set(survivors) | {pid for pid, _ in alive})
            if unknown:
                uncertain = True
            self.orphans_unattributed[:] = list(orphans.values())
            self._status = dict(
                survivors=list(survivors), containers_remaining=sorted(self.containers),
                uncertain=bool(uncertain),
                orphans_unattributed=list(self.orphans_unattributed), unknown=unknown, completed=True,
            )
            if container_failure is not None:
                raise container_failure
            if self.failure:           # C157 (P297 U2): a monitor failure is never hidden behind the uncertainty
                raise TransportAbort("process monitor died: " + str(self.failure))
            if uncertain:
                raise TransportAbort("cleanup uncertain: path-only or uninspectable processes remain " + json.dumps(
                    [dict(pid=p["pid"], create_time=p["create_time"], reason=p.get("reason"))
                     for p in orphans.values()
                     if p.get("reason") in ("path-only attribution", "access denied", "start order unreadable",
                                           "identity unreadable", "child of vanished unreadable process",
                                           "scan did not converge", "unreadable records overflowed")]
                    + [dict(u, reason="tracked identity unknown") for u in unknown]
                ) + (f"; order failure: {order_failure}" if order_failure else ""))
            if survivors:
                raise TransportAbort("attributed processes survived cleanup")
            if self.failure:
                raise TransportAbort("process monitor died: " + str(self.failure))

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.cleanup()


# ---------------------------------------------------------------------------------------------------------------
# C147 §4: /tmp escape diagnostic and exact-path cleanup.
# ---------------------------------------------------------------------------------------------------------------

TMP_ROOT = "/tmp"           # injectable for tests (`root=` arguments default to this)
_PRE_UNLINK_HOOK = None     # test seam: runs between the final identity check and the unlink
_PRE_RMDIR_HOOK = None      # test seam: runs after the unlink, before an emptied parent is re-verified and rmdir'd
_MENTION = re.compile(r"(?<![\w.\-/~$])((?:/private)?/tmp/[^\s\"'<>|;&)`,]*)")


def _tmp_norm(path):
    """`/private/tmp` is `/tmp` on macOS; nothing else is rewritten (components stay untouched)."""
    if path == "/private/tmp" or path.startswith("/private/tmp/"):
        return path[len("/private"):]
    return path


def _under(path, directory):
    directory = posixpath.normpath(str(directory))
    path = posixpath.normpath(path)
    return path == directory or path.startswith(directory.rstrip("/") + "/")


def _tmp_escape_path(path, base):
    """Lexically absolute (never resolved) path when it can name something under /tmp, else None."""
    if not isinstance(path, str) or not path:
        return None
    if not path.startswith("/"):
        if not isinstance(base, str) or not base.startswith("/"):
            return None
        path = base.rstrip("/") + "/" + path
    path = _tmp_norm(path)
    if path.startswith("/tmp/"):
        return path
    normal = _tmp_norm(posixpath.normpath(path))
    return path if normal.startswith("/tmp/") else None


def tmp_escapes(export, env, *, scratch=None):
    """Candidates the session may have written under /tmp: exact write/edit paths, best-effort shell mentions.

    `read` parts are ignored; `filePath` is not an alias on 2.0.20. Paths inside the item's TMPDIR or scratch are
    dropped. Each entry: {path, source: write|edit|shell, exact, token, status}."""
    scratch = scratch or env.get("PWD")
    own = [d for d in (env.get("TMPDIR"), scratch) if d]
    found = []
    seen = set()

    def add(path, source, exact, token, status, content_sha256=None):
        if any(_under(_tmp_norm(posixpath.normpath(path)), _tmp_norm(posixpath.normpath(d))) for d in own):
            return
        key = (path, source, token)
        if key in seen:
            return
        seen.add(key)
        entry = dict(path=path, source=source, exact=exact, token=token, status=status)
        if source == "write":
            entry["content_sha256"] = content_sha256      # what OUR client wrote: the only proof of ownership
        found.append(entry)

    for message in export.get("messages", []) if isinstance(export, dict) else []:
        for part in message.get("content", []) if isinstance(message, dict) else []:
            if not isinstance(part, dict) or part.get("type") != "tool":
                continue
            state = part.get("state") if isinstance(part.get("state"), dict) else {}
            inputs = state.get("input") if isinstance(state.get("input"), dict) else {}
            status = state.get("status")
            name = part.get("name")
            if name in ("write", "edit"):
                workdir = inputs.get("workdir")
                base = workdir if isinstance(workdir, str) and workdir.startswith("/") else scratch
                raw = inputs.get("path")
                path = _tmp_escape_path(raw, base)
                if path:
                    content = inputs.get("content") if name == "write" else None
                    add(path, name, True, raw, status,
                        hashlib.sha256(content.encode("utf-8")).hexdigest() if isinstance(content, str) else None)
            elif name == "shell":
                command = inputs.get("command")
                if not isinstance(command, str):
                    continue
                try:
                    tokens = shlex.split(command)
                except ValueError:
                    tokens = [command]
                for token in tokens:
                    if "/tmp/" not in token:
                        continue
                    for match in _MENTION.findall(token):
                        add(_tmp_norm(match), "shell", False, token, status)
    return found


def tmp_listing(root=None):
    """Read-only top-level listing: name -> (inode, device)."""
    listing = {}
    with os.scandir(TMP_ROOT if root is None else root) as entries:
        for entry in entries:
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            listing[entry.name] = (st.st_ino, st.st_dev)
    return listing


def _birth(st):
    return getattr(st, "st_birthtime", None) or st.st_ctime


class _Refuse(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _qualify(st, window, uid):
    if st.st_uid != uid:
        raise _Refuse("not_owned")
    if not (window[0] <= _birth(st) <= window[1]):
        raise _Refuse("outside_window")


def _open_dir_nofollow(name, dir_fd):
    try:
        return os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY, dir_fd=dir_fd)
    except FileNotFoundError:
        raise _Refuse("missing") from None
    except OSError:
        try:
            st = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        except OSError:
            raise _Refuse("missing") from None
        raise _Refuse("symlink" if stat.S_ISLNK(st.st_mode) else "not_regular") from None


def _unlink_checked(name, fd, identity):
    st = os.stat(name, dir_fd=fd, follow_symlinks=False)
    if (st.st_ino, st.st_dev) != identity or not stat.S_ISREG(st.st_mode):
        raise _Refuse("replaced")
    if _PRE_UNLINK_HOOK:
        _PRE_UNLINK_HOOK()
        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if (st.st_ino, st.st_dev) != identity:
            raise _Refuse("replaced")
    os.unlink(name, dir_fd=fd)


def _clean_one(path, before, after, window, root, uid, expected_sha=None):
    """Remove one recorded file (and now-empty new parents), or an empty directory.
    Returns (removed_parent_dirs, [[parent, reason], ...]) for parents that stayed."""
    parts = path[len("/tmp/"):].split("/")
    if not path.startswith("/tmp/") or any(c in ("", ".", "..") for c in parts):
        raise _Refuse("traversal")
    first = parts[0]
    if before is not None and first in before:
        raise _Refuse("pre_existing")
    if after is not None and first not in after:
        raise _Refuse("missing")
    cursor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    opened = [cursor]
    identities = []                # (st_dev, st_ino) of parts[i] as seen through its opened dir_fd (Q27)
    try:
        for index, name in enumerate(parts):
            last = index == len(parts) - 1
            try:
                st = os.stat(name, dir_fd=cursor, follow_symlinks=False)
            except FileNotFoundError:
                raise _Refuse("missing") from None
            if stat.S_ISLNK(st.st_mode):
                raise _Refuse("symlink")
            if index == 0 and after is not None and (st.st_ino, st.st_dev) != tuple(after[first]):
                raise _Refuse("replaced")
            _qualify(st, window, uid)
            if not last:
                cursor = _open_dir_nofollow(name, cursor)
                opened.append(cursor)
                if (os.fstat(cursor).st_ino, os.fstat(cursor).st_dev) != (st.st_ino, st.st_dev):
                    raise _Refuse("replaced")
                identities.append((st.st_dev, st.st_ino))
                continue
            if stat.S_ISDIR(st.st_mode):
                # The recorded WRITE must itself still be a regular file with matching content (Q20): a name that
                # now resolves to a directory was replaced and is kept. Directories are only ever rmdir'd as
                # parents emptied by the removal of their recorded files.
                raise _Refuse("replaced")
            elif stat.S_ISREG(st.st_mode):
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=cursor)
                try:
                    if (os.fstat(fd).st_ino, os.fstat(fd).st_dev) != (st.st_ino, st.st_dev):
                        raise _Refuse("replaced")
                    if expected_sha is not None:
                        # The bytes on disk must be exactly what our write tool was asked to write.
                        digest = hashlib.sha256()
                        while True:
                            block = os.read(fd, 1 << 20)
                            if not block:
                                break
                            digest.update(block)
                        if digest.hexdigest() != expected_sha:
                            raise _Refuse("modified")
                finally:
                    os.close(fd)
                _unlink_checked(name, cursor, (st.st_ino, st.st_dev))
                # Parents that became empty go too (every component was qualified on the way down); a parent that
                # still holds anything else is reported, never emptied.
                removed, kept = [], []
                if _PRE_RMDIR_HOOK:
                    _PRE_RMDIR_HOOK()
                for idx in range(len(parts) - 2, -1, -1):
                    where = "/tmp/" + "/".join(parts[:idx + 1])
                    try:
                        # The parent must still be the very directory walked into (a rename + new directory at
                        # the old name must not be rmdir'd), re-read by name from ITS parent fd.
                        now = os.stat(parts[idx], dir_fd=opened[idx], follow_symlinks=False)
                        if (now.st_dev, now.st_ino) != identities[idx] or not stat.S_ISDIR(now.st_mode):
                            kept.append([where, "replaced"])
                            break
                        os.rmdir(parts[idx], dir_fd=opened[idx])
                        removed.append(where)
                    except OSError:
                        kept.append([where, "dir_mixed"])
                        break
                return removed, kept
            else:
                raise _Refuse("not_regular")
    finally:
        for fd in opened:
            os.close(fd)


def tmp_clean(candidates, before, after, window, *, root=None, uid=None):
    """Remove only what the deletion authority of spec §4 / C147 Q13 allows; return (cleaned, [[path, reason]]).

    Automatic removal is for `write` parts ONLY: a completed write whose first /tmp component was absent from the
    pre-item listing, with every identity check (no symlink, our uid, birthtime inside the item window, inode
    unchanged) AND whose on-disk bytes immediately before the unlink equal the part's `state.input.content`
    (`content_sha256`); any difference is `modified`. `edit` needs a pre-existing file so it can never prove
    creation, and shell mentions are best-effort text: both are diagnostic only (`tmp_escapes` lists them). Parents
    that become empty are removed, anything else in them is never touched (`dir_mixed`). `before`/`after` of None
    (operator tool: no listings) skip the listing checks; ownership and the birthtime window always apply.
    Residual: (a) the microseconds between the final fstatat and the unlink; (b) an external process that created
    the same name first and was then fully overwritten by our write tool is indistinguishable from our own file.
    """
    root = TMP_ROOT if root is None else str(root)
    uid = os.getuid() if uid is None else uid
    cleaned, kept, done = [], [], set()
    for candidate in candidates:
        path = candidate["path"]
        if path in done or candidate.get("source") == "shell" or not candidate.get("exact"):
            continue
        done.add(path)
        try:
            parts = path[len("/tmp/"):].split("/") if path.startswith("/tmp/") else []
            if any(c in ("", ".", "..") for c in parts):
                raise _Refuse("traversal")
            if candidate.get("source") != "write" or candidate.get("status") != "completed" \
                    or not isinstance(candidate.get("content_sha256"), str):
                raise _Refuse("ambiguous")
            dirs, parent_kept = _clean_one(path, before, after, window, root, uid, candidate["content_sha256"])
            cleaned.append(path)
            cleaned.extend(dirs)
            kept.extend(parent_kept)
        except _Refuse as refusal:
            kept.append([path, refusal.reason])
        except OSError:
            kept.append([path, "missing"])
    kept = [k for k in kept if not (k[1] == "dir_mixed" and k[0] in cleaned)]
    return cleaned, kept
