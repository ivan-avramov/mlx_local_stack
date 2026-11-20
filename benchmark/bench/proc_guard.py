"""M62 best-effort process attribution, memory monitoring and durable artifacts.

A fork that detaches and leaves scratch between samples can escape attribution.
S27 §3 (P12): cleanup kills only what the harness OWNS — tracked identities and their ancestry, the probe's own session when the
probe leads it (or the chain names it), and processes whose readable environment carries the run's hermetic HOME / XDG_*. Every
other new same-uid process is `foreign_new`: recorded, never killed, never a refusal (receipt schema 2). Residual (C372): an agent
child that calls `setsid`, leaves every guard root and clears its environment is `foreign_new`.
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
CLEANUP_SCHEMA = 2                 # S27 §3.5: the receipt gains `schema`, `foreign_new`, `foreign_new_count`, `unreadable_count`
FOREIGN_NEW_CAP = 64               # S27 §3.4: listed entries; the total is `foreign_new_count`
FOREIGN_ARGV0_CAP = 64             # S27 Y6: characters of a listed entry's executable basename
ENV_MARKER_KEYS = ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME")
UNCERTAIN_REASONS = ("access denied", "start order unreadable", "identity unreadable",
                     "child of vanished unreadable process", "scan did not converge", "unreadable records overflowed",
                     "unreadable record unresolved", "session id unreadable", "liveness unreadable", "not verified gone")


class CleanupUncertain(TransportAbort):
    """S27 §5.8: the owned cleanup could not be shown certain; the abort stamp's cause is `cleanup_uncertain`."""


def _cmdline(p):
    """`p.cmdline()`; psutil's macOS `proc_cmdline` can raise SystemError ("returned a result with an exception set") for a
    process mid-exec / mid-exit — the same unreadable state C148 sees as AccessDenied, so it is raised as AccessDenied (P585)."""
    try:
        return p.cmdline()
    except SystemError as exc:
        import psutil

        raise psutil.AccessDenied(getattr(p, "pid", None), msg=f"cmdline: {exc}") from None


def exe_identity(p):
    """S27 Z5: a listed process's identity — (the executable's basename (`Process.exe()`) capped at FOREIGN_ARGV0_CAP, or
    "unknown" when it cannot be read; the argument count, None when unreadable). Never argument text: argv[0] is free text a
    process can set (titles); it is named only when it is an absolute path that resolves to that same executable (an alias
    such as a venv's `python` link: a filesystem name of the binary, not free text). Objects without a psutil
    implementation and without `exe()` (test fakes) name their argv[0]'s basename, as `start_time` lets them keep their own
    create_time()."""
    import psutil
    try:
        argv = _cmdline(p)
    except Exception:  # noqa: BLE001 — evidence only
        argv = None
    argc = len(argv) if argv is not None else None
    if isinstance(p, psutil.Process) or callable(getattr(p, "exe", None)):
        try:
            path = p.exe()
        except Exception:  # noqa: BLE001 — unreadable (AccessDenied, ZombieProcess, SystemError, ...)
            path = ""
        alias = str(argv[0]) if argv else ""
        try:
            if path and os.path.isabs(alias) and os.path.realpath(alias) == os.path.realpath(path):
                path = alias
        except (OSError, ValueError):
            pass
    else:
        path = str(argv[0]) if argv else ""
    return (Path(str(path)).name[:FOREIGN_ARGV0_CAP] or "unknown"), argc


def _lookup(psutil, pid):
    """`psutil.Process(pid)`; its construction reads the start time, so a SystemError there is AccessDenied (P585)."""
    try:
        return psutil.Process(pid)
    except SystemError as exc:
        raise psutil.AccessDenied(pid, msg=f"lookup: {exc}") from None


def _scan(psutil, last, denied=None):
    """Every live process as a `psutil.Process` built per pid (never psutil's shared `process_iter` cache, which a SystemError
    raised inside its generator would end for the whole tick; P585). A process that cannot be constructed (AccessDenied /
    SystemError: mid-exec / mid-exit) is listed through its previous tick's object, so a tracked parent never drops out of
    the ancestry closure (review r3 P1; `process_iter` kept a cached object the same way) and its reads stay denied
    obligations; one never seen before is not listed but reported in `denied` (X11: the guard decides its ownership, never
    a silent drop); a vanished one is forgotten. `last` is the guard's cache."""
    out, seen = [], {}
    if denied is not None:
        denied.clear()
    for pid in psutil.pids():
        try:
            proc = psutil.Process(pid)
        except psutil.NoSuchProcess:
            continue
        except (psutil.AccessDenied, SystemError):
            proc = last.get(pid)
            if proc is None:
                if denied is not None:
                    denied.add(pid)
                continue
        out.append(proc)
        seen[pid] = proc
    last.clear()
    last.update(seen)
    return out


# -- S27 §3.2 ownership tests (b) / (c), shared by the guard's cleanup and the chain's second scan (X10: one rule)
def session_claim(pid, owner):
    """§3.2 (b): True when `pid` is in the probe's session `owner`, False when it is not (or no session ownership applies:
    `owner` None), None when its session id cannot be read; a vanished pid raises ProcessLookupError."""
    if owner is None:
        return False
    try:
        return os.getsid(pid) == owner
    except ProcessLookupError:
        raise
    except OSError:
        return None


def _within(value, roots):
    return isinstance(value, str) and any(value == r or value.startswith(r + "/") for r in roots)


def hermetic_homes(paths):
    """The hermetic roots in BOTH spellings — as given and resolved (macOS: `/var/...` is `/private/var/...`), since a process's
    environment carries the value it was given, never its resolved form."""
    out = set()
    for v in paths:
        if v:
            out.add(str(v).rstrip("/") or "/")
            out.add(str(Path(v).resolve()))
    return sorted(out)


def env_claim(p, homes):
    """§3.2 (c): the readable environment carries a HOME / XDG_* at or under one of the run's hermetic `homes`; a denied read
    raises AccessDenied (psutil's macOS SystemError included)."""
    if not homes:
        return False
    try:
        env = p.environ()
    except SystemError as exc:
        import psutil
        raise psutil.AccessDenied(getattr(p, "pid", None), msg=f"environ: {exc}") from None
    for k in ENV_MARKER_KEYS:
        value = env.get(k)
        if isinstance(value, str) and value and (_within(value, homes) or _within(str(Path(value).resolve()), homes)):
            return True
    return False


def path_claim(p, roots):
    """§3.2 (c): cwd / argv under a guard root (a path match: never ownership on its own); a denied read raises AccessDenied."""
    values = [p.cwd(), *_cmdline(p)]
    return any(v == root or v.startswith(root + "/") or ("=" + root + "/") in v for root in roots for v in values)


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
            try:
                return impl.create_time(monotonic=True)
            except SystemError as exc:                                    # P585: an unreadable identity, as AccessDenied
                raise psutil.AccessDenied(proc.pid, msg=f"create_time: {exc}") from None
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


# G1 (round 4): psutil read sites. Rule: BEFORE same-uid is established a denied read may skip the process; AFTER it, a
# denied read is an unreadable obligation (exact identity when known, else (pid, None)); NoSuchProcess may vanish.
#   site                                       AccessDenied                         NoSuchProcess
#   _processes uids()                          skip (not known same-uid)           skip
#   _processes status() [CHANGED P13]          keep + _live_denied -> obligation    skip
#   tick/cleanup _protected (order/identity)   obligation                          vanish
#   tick ppid() / start_time / start_order     obligation                          vanish
#   cleanup start_time key, ppid, age read     obligation                          vanish
#   cleanup cwd()/cmdline() [CHANGED P12]      obligation (tracked: uncertain)      vanish
#   tick parent validation [CHANGED P11]       child obligation (tri-state)         child obligation; reuse: none
#   _listing_edges ppid()                      candidate child of unreadable roots  same
#   _resolve (all reads)                       unresolved                           gone
#   _existence / _identity_state               present / unknown (never gone)       gone
#   _created_or_none / excluded identity       None (unknown identity)              None / unprotected
#   tick shell cmdline / memory_info (tracked) skipped this tick (already owned)    skipped
#   _argv / _mem_kill context (evidence)       [] / ignored                         []
#   kill_role / graceful_stop / audit kill     pass; the audit marks it unknown     pass
#   descendants_alive start_time [P19]         recorded descendant: True (possibly   vanish
#                                              alive); a stranger: skipped
#   deadline (P9/P10)                          confirmation must start AND finish before it
# KNOWN LIMITATIONS (G3, scope-closed by C170; each is a residual fail-open path, not fixed in G1):
#   P14 a uids()-denied tracked/protected/recorded identity is skipped, so its children miss the ancestry graph
#   P15 status-denied obligations ride the shared `_live_denied` set (protected roots bypass it, a concurrent
#       descendants_alive() can overwrite it) instead of scan-local data
#   P16 _listing_edges forgets a one-shot ppid AccessDenied when its retry succeeds; _refresh_descendants collapses
#       AccessDenied/NoSuchProcess of an exact root to "skip", losing children captured just before it exits
#   P17 process_iter() caches Process objects: after pid reuse uids()/status() can read the replacement while ppid()
#       raises NoSuchProcess for the cached original, so cleanup sees a disappearance and runs no confirming scan


class ProcessGuard:
    RECONCILE_DEADLINE_S = 10.0   # G1: one monotonic deadline for cleanup's whole scan/reconcile loop
    _monotonic = staticmethod(time.monotonic)      # injectable (tests): the deadline clock and its sleep
    _sleep = staticmethod(time.sleep)

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
        env_markers=None,
    ):
        """S27 §3.1: session ownership applies only when this process leads its session at construction (the chain launches
        every probe with `start_new_session=True`); otherwise ownership is tracked ancestry only. `env_markers` — {HOME /
        XDG_*: value} of the run's hermetic environment (§3.2 (c)); only values under a guard root are used."""
        import psutil

        self.psutil = psutil
        # A process mid-exit can raise AccessDenied on macOS (sysctl KERN_PROCARGS2 -> EINVAL) instead of
        # NoSuchProcess; either way the monitor skips it for that tick (C148).
        self._transient = (psutil.NoSuchProcess, psutil.AccessDenied, SystemError)
        # P585: psutil's macOS C extension can raise SystemError ("returned a result with an exception set") for a process
        # mid-exec / mid-exit — the same unreadable state; every handler of a denied read takes it as AccessDenied.
        self._denied = (psutil.AccessDenied, SystemError)
        self.excluded_pids = {os.getpid(), os.getppid()}
        self.excluded_pids.update(p.pid for p in psutil.Process().parents())
        self.excluded_pids.update(protected_pids)
        # G1 (round 3 P8): protection is an IDENTITY (pid, start time), never a bare pid: a reused pid of an exited
        # protected process is not protected. An excluded pid whose start time could not be read stays unprotected
        # here (its age alone can still protect it).
        self._excluded_identity = {}
        for pid in self.excluded_pids:
            try:
                self._excluded_identity[pid] = start_time((get or psutil.Process)(pid))
            except (psutil.NoSuchProcess, psutil.AccessDenied, SystemError, TransportAbort, StopIteration):
                pass
        self.probe_session = os.getsid(0)
        leader = self.probe_session == os.getpid()
        if leader:
            self.session_owner, source = self.probe_session, "leader"
        else:
            self.session_owner, source = None, "ancestry_only"
        self.session = dict(sid=self.probe_session, leader=leader, owner=self.session_owner, source=source)
        self._scan_last = {}                                                         # P585: the previous tick's objects
        self._scan_denied = set()          # X11: pids the scan could not construct (no previous object), per scan
        self._dropped = set()              # X11: those + same-uid-unknown (uids() denied) pids of the last listing
        self.scan = scan or (lambda: _scan(psutil, self._scan_last, self._scan_denied))
        self.get = get or (lambda pid: _lookup(psutil, pid))
        self.roots = [str(Path(p).resolve()) for p in roots]
        self.env_markers = {}
        for key, value in (env_markers or {}).items():
            if key in ENV_MARKER_KEYS and isinstance(value, str) and value:
                resolved = str(Path(value).resolve())
                if any(resolved == r or resolved.startswith(r + "/") for r in self.roots):
                    self.env_markers[key] = value       # a box-wide value (a hand run's real HOME) never claims anything
        self.foreign_new = {}
        self.foreign_new_count = 0
        self._foreign_seen = set()
        self._counted = set()                   # §3.4: unclaimed unreadable identities provably older than the guard
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
        self.reconcile_deadline_s = self.RECONCILE_DEADLINE_S
        self._live_denied = set()       # G1 round 4 P13: same-uid pids of the last listing whose status was denied
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
        return self._excluded(process) or self._older_than_guard(process)

    def _excluded(self, process):
        known = self._excluded_identity.get(process.pid)
        return process.pid in self.excluded_pids and known is not None and start_time(process) == known

    def _proven_older(self, process):
        """G1 (round 3 P8): started before the guard, proven ONLY by the monotonic start-order read (no wall-clock
        fallback, no excluded-pid shortcut)."""
        order = start_order(process)
        return order is not None and self.started_order is not None and order < self.started_order

    def _same_identity(self, pid, created):
        return self._parent_state(pid, created) == "same"

    def _parent_state(self, pid, created):
        """G1 (round 4 P11), tri-state: "same" (this exact identity), "other" (the pid is reused: not that process) or
        "unknown" (denied/raced away: it may still be the process, so a child of it stays an obligation)."""
        try:
            return "same" if start_time(self.get(pid)) == created else "other"
        except (self.psutil.NoSuchProcess, StopIteration):
            return "unknown"
        except (*self._denied, TransportAbort):
            return "unknown"

    def _live(self, process):
        return process.status() not in ("zombie", "dead")

    def _nap(self, seconds, deadline=None):
        """G1 (round 3 P9): every cleanup retry sleep is capped by the time left to the global deadline."""
        self._sleep(seconds if deadline is None else max(0.0, min(seconds, deadline - self._monotonic())))

    def _processes(self):
        """Same-uid live processes. A process whose same-uid cannot be established (uids() denied) or that the scan could not
        construct is not listed but kept in `_dropped` (X11: cleanup claims it when tracked or a probe-session member, else
        counts it); AFTER same-uid (G1 round 4 P13) a process whose liveness is denied is kept and listed in `_live_denied`,
        which tick()/cleanup record as an unreadable obligation unless it is protected."""
        found, self._live_denied = [], set()
        listing = self.scan()
        dropped = set(self._scan_denied)
        for p in listing:
            try:
                if p.uids().real != os.getuid():
                    continue
            except self.psutil.NoSuchProcess:
                continue
            except self._denied:
                dropped.add(p.pid)          # X11: same-uid unknown — the cleanup decides its ownership (`_dropped`)
                continue
            try:
                if self._live(p):
                    found.append(p)
            except self.psutil.NoSuchProcess:
                continue
            except self._denied:
                found.append(p)
                self._live_denied.add(p.pid)
        self._dropped = dropped
        return found

    def _attributed_path(self, p):
        return path_claim(p, self.roots)

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
                    except self._denied:
                        # C157 (review round 1 P2): keep the identity and the listing's descendants, so a cleanup that
                        # runs after this process exits still knows who its children were
                        self._note_unreadable(self._unreadable_seen, p, edges)
                        continue
                    if not protected:
                        if p.pid in self._live_denied:
                            self._note_unreadable(self._unreadable_seen, p, edges)
                            continue
                        # ppid() re-validates identity; a stale cached entry (pid reused, psutil keeps the old
                        # create_time) raises here and must never become an ancestry authority (V5a P13).
                        try:
                            ppids[p.pid] = p.ppid()
                        except self._denied:
                            # G1 (round 3 P7): an eligible process whose parent cannot be read could be ours (its
                            # tracked parent may be killed next): recorded like any other denied read
                            self._note_unreadable(self._unreadable_seen, p, edges)
                            continue
                        try:
                            alive[p.pid] = (p, start_time(p), start_order(p))
                        except self._denied:
                            # G1 (round 2 P1): the identity/order reads AFTER eligibility are recorded like the first
                            # one; only NoSuchProcess may vanish silently
                            ppids.pop(p.pid, None)
                            self._note_unreadable(self._unreadable_seen, p, edges)
                            continue
                    readable[p.pid] = p      # only after EVERY required read succeeded (round 3 P2)
                except self._transient:
                    ppids.pop(p.pid, None)
                    alive.pop(p.pid, None)
            # G1 (round 2 P2): root and descendant obligations are separate. A recorded exact root that reads fine
            # again still collects the descendants of every listing; only the SAME identity proving protected
            # discharges the ROOT obligation (exact identity only: never a pid wildcard), never its children's.
            self._refresh_descendants(self._unreadable_seen, processes, edges)
            for key, info in self._unreadable_seen.items():
                if (info["root"] and key[1] is not None and key[0] in readable
                        and self._created_or_none(readable[key[0]]) == key[1] and self._is_protected(readable[key[0]])):
                    info["root"] = False
            for key in [k for k, info in self._unreadable_seen.items() if self._fully_gone(k, info)]:
                del self._unreadable_seen[key]      # P306: gone with nothing recorded below it - nothing to reconcile
            # Follow ancestry until its transitive closure; detachments retain recorded ownership.
            changed = True
            while changed:
                changed = False
                for pid, (p, created, order) in alive.items():
                    key = (pid, created)
                    parent = alive.get(ppids[pid])
                    if parent and (parent[2] > order if None not in (parent[2], order) else parent[1] > created):
                        parent = None   # a parent cannot be younger than its child: pid reuse (monotonic, C151 R8)
                    if parent and (parent[0].pid, parent[1]) in self.tracked and key not in self.tracked:
                        validity = self._parent_state(parent[0].pid, parent[1])
                        if validity == "unknown":
                            # G1 (round 4 P11): a denied/raced parent check may hide a tracked parent: the captured
                            # child stays a descendant obligation instead of an untracked bystander (S27: claimed, (a))
                            self._note_unreadable(self._unreadable_seen, p, edges)
                            noted = self._unreadable_seen.get((p.pid, self._created_or_none(p)))
                            if noted is not None:
                                noted["claimed"] = True
                        if validity != "same":
                            parent = None
                    elif parent and not self._same_identity(parent[0].pid, parent[1]):
                        parent = None
                    if key not in self.tracked and parent:
                        role = self.tracked.get((parent[0].pid, parent[1]))
                        if role:
                            self.tracked[key] = "model" if role == "client" else role
                            changed = True
                    if self.tracked.get(key) == "model":
                        try:
                            argv = _cmdline(p)
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
            return [self.scrub(str(x)) for x in _cmdline(p)]
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
        except (*self._denied, TransportAbort):   # unreadable identity is never "gone" (C151 R16)
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
            return dict(schema=CLEANUP_SCHEMA, survivors=[], containers_remaining=sorted(self.containers),
                        uncertain=True, orphans_unattributed=list(self.orphans_unattributed),
                        unknown=[], completed=False, foreign_new=self._foreign_list(),
                        foreign_new_count=getattr(self, "foreign_new_count", 0),
                        unreadable_count=len(getattr(self, "_counted", ())))
        return dict(self._status)

    def _foreign_list(self):
        return [dict(v) for v in list(getattr(self, "foreign_new", {}).values())[:FOREIGN_NEW_CAP]]

    @property
    def unreadable_count(self):
        return len(self._counted)

    def _record_foreign(self, p, key, *, path_match, unreadable, pid=None):
        """S27 §3.4: record one `foreign_new` process (never killed); capped list + total count, one entry per identity."""
        pid = p.pid if p is not None else pid
        ident = (pid, key[1] if key else None)
        if ident in self.foreign_new:
            entry = self.foreign_new[ident]
            entry["path_match"] = entry["path_match"] or bool(path_match)
            entry["unreadable"] = entry["unreadable"] or bool(unreadable)
            return
        if ident in self._foreign_seen:
            return
        self._foreign_seen.add(ident)
        try:
            sid = os.getsid(pid)
        except OSError:
            sid = None
        # X8 / Z5 (data boundary: these rows are public): a record-only entry needs the identity, never the content — the
        # executable's basename (`exe_identity`: never argv text, scrubbed, capped) and the argument count; no argument, path
        # or environment value
        name, argc = exe_identity(p) if p is not None else ("unknown", None)
        exe = [self.scrub(name)[:FOREIGN_ARGV0_CAP]]
        self.foreign_new_count += 1
        if len(self.foreign_new) >= FOREIGN_NEW_CAP:
            return
        self.foreign_new[ident] = dict(pid=pid, create_time=ident[1], argv=exe, argc=argc,
                                       sid=sid, path_match=bool(path_match), unreadable=bool(unreadable))

    def _env_match(self, p):
        """§3.2 (c): the readable environment carries the run's hermetic HOME / XDG_* (raises AccessDenied when unreadable)."""
        return env_claim(p, hermetic_homes(self.env_markers.values()))

    def _session_claim(self, pid):
        """§3.2 (b): True / False, or None when the session id cannot be read (uncertain); ProcessLookupError propagates."""
        return session_claim(pid, self.session_owner)

    def _ancestry(self, listing, edges):
        """§3.2 (a): {pid: node} of this listing's tracked identities and their ancestry closure (a child never older than its
        parent: pid reuse); computed before any read that can mark a process unreadable. Z4: each node keeps the identity it
        was claimed with — `starts` (the start read, or for a seed whose read failed the tracked starts of its pid; None for a
        child whose read failed), its `parent` pid and process — so `_ancestry_holds` can refuse a later readable identity
        that differs."""
        children_of, _unknown = edges
        claimed = {}
        frontier = []
        for p in listing:
            created = self._created_or_none(p)
            # the EXACT tracked identity seeds the closure (a reused pid is not ours); an unreadable one by its pid, keeping
            # the tracked starts it must still match
            starts = frozenset(k[1] for k in self.tracked if k[0] == p.pid)
            if (created in starts) if created is not None else starts:
                claimed[p.pid] = dict(starts=frozenset([created]) if created is not None else starts, parent=None, proc=p)
                frontier.append(p)
        while frontier:
            parent = frontier.pop()
            for child in children_of.get(parent.pid, ()):
                if child.pid in claimed:
                    continue
                pc, known = self._created_or_none(parent), claimed[parent.pid]["starts"]
                if pc is None and known:
                    pc = min(known)                                 # an unreadable seed: its tracked start
                cc = self._created_or_none(child)
                younger = True if None in (pc, cc) else cc >= pc    # unreadable: kept as a claim (needs a readable identity)
                if younger:
                    claimed[child.pid] = dict(starts=frozenset([cc]) if cc is not None else None, parent=parent.pid,
                                              proc=child)
                    frontier.append(child)
        return claimed

    def _ancestry_holds(self, ancestry, pid, start):
        """Z4: the ancestry claim on `pid` (current start `start`, None when unreadable) holds only while every node on its
        path to the seed still has the identity it was claimed with: a readable start outside the recorded `starts` (or, for a
        node claimed unreadable, older than its parent) is a different process — the claim does not hold."""
        node, now, seen = pid, start, set()
        while node is not None and node not in seen:
            seen.add(node)
            rec = ancestry[node]
            if node != pid:
                now = self._created_or_none(rec["proc"])
            if now is not None:
                if rec["starts"] is not None and now not in rec["starts"]:
                    return False
                parent = ancestry.get(rec["parent"]) if rec["parent"] is not None else None
                if rec["starts"] is None and parent is not None and parent["starts"]:
                    if now < min(parent["starts"]):
                        return False
            node = rec["parent"]
        return True

    def _classify(self, p, ancestry):
        """S27 §3.2 for one live same-uid process of the cleanup listing: ("skip",) | ("ours", key, claim) |
        ("uncertain", record) | ("foreign",) | ("count",). NoSuchProcess propagates (the process vanished)."""
        try:
            key = (p.pid, start_time(p))
        except (*self._denied, TransportAbort):
            key = None
        claim = None
        if key is not None and key in self.tracked:
            claim = "tracked"
        elif key is None and any(k[0] == p.pid for k in self.tracked):
            claim = "tracked"
        elif p.pid in ancestry and self._ancestry_holds(ancestry, p.pid, key[1] if key else None):
            claim = "ancestry"                              # Z4: a differing readable identity falls through (never owned)
        else:
            session = self._session_claim(p.pid)
            if session is None:
                # an unreadable session id: a possible member, resolved like any unreadable obligation
                return ("uncertain", dict(pid=p.pid, create_time=key[1] if key else None, argv=[], reason=None))
            if session:
                claim = "session"
        if claim:
            if key is None:
                return ("uncertain", dict(pid=p.pid, create_time=None, argv=[], reason="access denied"))
            try:
                protected = self._protected(p)
            except (*self._denied, TransportAbort):
                return ("uncertain", dict(pid=p.pid, create_time=key[1], argv=[], reason="start order unreadable"))
            if protected:
                return ("skip",)
            if p.pid in self._live_denied:
                return ("uncertain", dict(pid=p.pid, create_time=key[1], argv=[], reason="liveness unreadable"))
            return ("ours", key, claim)
        # unclaimed: never killed; its age decides whether it is `foreign_new` at all (ONE start-order read)
        try:
            order = start_order(p)
        except (*self._denied, TransportAbort):
            order = False                                   # unreadable age: listed (never provably older)
        proven_older = order not in (None, False) and self.started_order is not None and order < self.started_order
        if key is None:
            if proven_older:
                return ("count", None)
            return ("foreign_unreadable", None)
        if order is False:
            return ("foreign_unreadable", key)
        try:
            excluded = self._excluded(p)
        except (*self._denied, TransportAbort):
            excluded = False
        older = proven_older if (order is not None and self.started_order is not None) else key[1] < self.started
        if excluded:
            return ("skip",)
        if older:
            # §3.4 (X15): an unclaimed process provably older than the guard is never listed; it is COUNTED when any of the
            # reads §3.2 (c) takes (liveness, cwd / argv, environment) is denied (record only)
            if p.pid in self._live_denied:
                return ("count", key[1])
            try:
                self._attributed_path(p)
                self._env_match(p)
            except self._denied:
                return ("count", key[1])
            return ("skip",)
        unreadable = p.pid in self._live_denied
        try:
            path_match = self._attributed_path(p)
        except self._denied:
            path_match, unreadable = False, True
        try:
            env_match = self._env_match(p)
        except self._denied:
            env_match, unreadable = False, True
        if env_match:
            return ("ours", key, "environment")
        if unreadable:
            return ("foreign_unreadable", key, path_match)
        self._record_foreign(p, key, path_match=path_match, unreadable=False)
        return ("foreign",)

    def descendants_alive(self):
        for p in self._processes():
            try:
                if (p.pid, start_time(p)) in self.shell_descendants:
                    return True
            except self.psutil.NoSuchProcess:
                continue
            except (*self._denied, TransportAbort):
                # G1 (round 5 P19/P354): a denied identity read of a pid we recorded as a shell descendant is
                # "possibly alive"; a denied stranger is not a recorded descendant
                if any(k[0] == p.pid for k in self.shell_descendants):
                    return True
        return False

    def register_container(self, name):
        with self.lock:
            self.containers.add(name)

    def container_oom(self, name):
        """Tri-state (S27 Y2): True / False, or `GraderInfraError(kind="transport")` when the state cannot be verified."""
        from .token_turn_gate import GraderInfraError
        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.OOMKilled}}", name],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise GraderInfraError("container state unverifiable: %s" % exc, kind="transport") from exc
        value = (result.stdout or "").strip()
        if result.returncode != 0 or value not in ("true", "false"):
            raise GraderInfraError("container state unverifiable: rc=%s %r" % (result.returncode, value[:80]),
                                   kind="transport")
        return value == "true"

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

    def _note_unreadable(self, store, p, edges, key=None):
        """Record an eligible process whose start order cannot be read, with the TRANSITIVE descendants of the
        listing (edges read BEFORE any per-process start-order read) and everything of unreadable parentage, closed
        over those edges: a vanished parent proves nothing about them (P297 U1). Candidates are IDENTITIES
        (pid, start time), so a reused pid adds a second candidate instead of masquerading as the first. Bounded:
        at most 32 roots and 2048 identities (roots included) are ever retained; past either limit nothing more is stored or
        traversed and `_unreadable_overflow` stays set (permanent, fail-closed: cleanup is uncertain)."""
        if self._unreadable_overflow:
            return
        children_of, unknown = edges
        key = key or (p.pid, self._created_or_none(p))
        if key not in store and len(store) >= 32:
            self._unreadable_overflow = True
            return
        room = 2048 - sum(len(v["children"]) for v in store.values()) - len(store) - (key not in store)
        entry = store.setdefault(key, dict(children=set(), root=True))     # roots count against the identity budget too

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

    def _detached(self, p, store, edges, key=None):
        """True when `p` is parented to launchd; a denied ppid read is recorded (G1 round 3 P7), never skipped."""
        try:
            return p.ppid() == 1
        except self._denied:
            self._note_unreadable(store, p, edges, key=key)
            return False

    def _refresh_descendants(self, store, listing, edges):
        """G1 (round 2 P2): every exact recorded root present in this listing, readable or not, re-collects its
        transitive descendants (a child spawned after the root last failed to read is still its obligation)."""
        by_pid = {p.pid: p for p in listing}
        for key in list(store):
            p = by_pid.get(key[0])
            if p is None:
                continue
            if key[1] is None:
                # G1 (round 3 P6): an unknown-identity root's occupant may be the original (or a replacement): its
                # descendants are collected conservatively under the recorded key, whatever the occupant proves
                self._note_unreadable(store, p, edges, key=key)
            elif self._created_or_none(p) == key[1]:
                self._note_unreadable(store, p, edges)

    def _fully_gone(self, key, info):
        """P306: the unreadable root is definitively gone AND every recorded descendant identity is gone, so cleanup
        has nothing left to reconcile for it (pruning it is equivalent to keeping it; without pruning, exiting
        processes over a ~60-min item would fill the 32-root cap and fail cleanup closed)."""
        if info["root"] and self._existence(*key)[0] != "gone":      # a discharged (protected) root owes nothing
            return False
        for pid, created in info["children"]:
            if created is None:
                if self._existence(pid, None)[0] != "gone":
                    return False
            elif self._identity_state(pid, created) != "gone":
                return False
        return True

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
        except (*self._denied, TransportAbort):
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
        except (*self._denied, TransportAbort):
            return "present", None

    def _is_protected(self, p):
        """tick() only: True when `p` provably is pre-existing/protected; an inspection failure is False, which keeps
        the record (fail-closed there). Resolution never uses it (see `_resolve`)."""
        try:
            return bool(self._protected(p))
        except (*self._transient, TransportAbort, StopIteration):
            return False

    def _resolve(self, pid, created):
        """G1 (round 2 P3): resolve ONE recorded identity (pid, start time) against the process table NOW. Returns
        (state, occupant start time): "gone" - NoSuchProcess, a dead state, or (known identity) a different start
        time (pid reuse: only the original is gone, the replacement is still scanned independently); "resolved" - the
        SAME identity is protected/pre-existing, tracked (the tracked audit kills it) or path-attributed (the scan
        owns it); "unresolved" - everything else, including every inspection failure. A recorded identity whose start
        time was never captured stays unresolved while its pid is occupied. The identity is revalidated after the
        classification reads, so a pid that changed hands between them is never classified as the original."""
        try:
            process = self.get(pid)
        except (self.psutil.NoSuchProcess, StopIteration):
            return "gone", None
        except (*self._denied, TransportAbort):
            return "unresolved", None
        try:
            if not self._live(process):
                return "gone", None
            occupant = self._created_or_none(process)
            if occupant is None:
                return "unresolved", None       # occupied, identity unreadable: never aliased to an absent pid
            if created is not None and occupant != created:
                return "gone", occupant
            if (self._proven_older(process) if created is None else self._protected(process)):
                # a never-captured identity resolves only through temporal continuity: an occupant PROVEN older than
                # the guard by the monotonic start-order read cannot have been reassigned since the record, so it IS
                # the recorded original (revalidated below). Never via the excluded-pid shortcut or the wall clock.
                state = "resolved"
            elif created is None:
                state = "unresolved"            # the young occupant may be a replacement of an original we cannot name
            else:
                # S27 §3.2: a path match alone owns nothing (no corroboration): only a tracked identity resolves here
                state = "resolved" if (pid, occupant) in self.tracked else "unresolved"
            again_process = self.get(pid)
            again = self._created_or_none(again_process)
            if again == occupant and state == "resolved" and created is None and not self._proven_older(again_process):
                state = "unresolved"
            if again != occupant:
                return ("gone" if created is not None else "unresolved"), again
            return state, occupant
        except (self.psutil.NoSuchProcess, StopIteration):
            return "gone", None
        except (*self._denied, TransportAbort):
            return "unresolved", None

    def _reconcile_unreadable(self, unreadable):
        """C157: resolve every unreadable-identity record against the process table NOW, never from a flag frozen
        earlier. Returns ({key: orphan record} still unresolved, {key: state}). G1 (round 2): the ROOT obligation
        (unless a protected root already discharged it) and EVERY recorded descendant obligation are resolved
        independently, each by `_resolve`; a readable root never discharges its children. A still-present unreadable
        process stays uncertain (C151 R10); every state CHANGE since the previous reconcile forces another full scan
        (caller)."""
        bad, states = {}, {}
        for key, info in unreadable.items():
            pid, created = key
            claimed = bool(info.get("claimed")) or self._claims(pid)
            if info["root"]:
                state = states[key] = self._resolve(pid, created)
                if state[0] == "unresolved":
                    if not claimed:                      # S27 §3.2: unclaimed + unreadable -> foreign_new, never uncertain
                        self._foreign_unresolved(pid, created if created is not None else state[1])
                    elif state[1] is None:
                        bad[(pid, None)] = dict(pid=pid, create_time=None, argv=[],
                                                reason=info.get("reason") or "start order unreadable")
                    else:
                        bad[(pid, created)] = dict(pid=pid, create_time=created, argv=[],
                                                   reason=info.get("reason") or "unreadable record unresolved")
            for child_pid, child_created in info["children"]:
                state = states[(key, child_pid, child_created)] = self._resolve(child_pid, child_created)
                if state[0] == "unresolved":
                    if not (claimed or self._claims(child_pid)):
                        self._foreign_unresolved(child_pid, child_created)
                        continue
                    bad[(child_pid, child_created)] = dict(pid=child_pid, create_time=child_created, argv=[],
                                                           reason="child of vanished unreadable process")
        return bad, states

    def _claims(self, pid):
        """(a) a tracked pid or (b) the probe session's member (an unreadable session id claims: fail closed)."""
        if any(k[0] == pid for k in self.tracked):
            return True
        try:
            session = self._session_claim(pid)
        except ProcessLookupError:
            return False
        return session is not False

    def _claim_dropped(self, unreadable):
        """X11: a pid the listing could not include (not constructible, or its uids() denied) is decided by ownership, never
        dropped: tracked or a probe-session member (an unreadable session id claims, as §3.2) -> a CLAIMED obligation on
        (pid, None), resolved against the final process table like every other (gone = discharged, else uncertain); else it
        is counted (`unreadable_count`, record only)."""
        for pid in sorted(self._dropped):
            if pid in self.excluded_pids or any(k[0] == pid for k in unreadable):
                continue                                    # already an obligation under some identity
            try:
                claimed = self._claims(pid)
            except OSError:
                claimed = True
            if claimed:
                if len(unreadable) >= 32:
                    self._unreadable_overflow = True
                    return
                unreadable[(pid, None)] = dict(children=set(), root=True, claimed=True, reason="identity unreadable")
            else:
                self._counted.add((pid, None))

    def _foreign_unresolved(self, pid, created):
        """An unclaimed obligation that stays unresolved: `foreign_new` (unreadable) when not provably older, else counted."""
        try:
            process = self.get(pid)
        except (self.psutil.NoSuchProcess, StopIteration):
            return
        except (*self._denied, TransportAbort):
            process = None
        if process is not None:
            try:
                if self._proven_older(process):
                    self._counted.add((pid, created))
                    return
            except (*self._transient, TransportAbort):
                pass
        self._record_foreign(process, (pid, created), path_match=False, unreadable=True, pid=pid)

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
            orphans = {}                    # uncertainty records (claimed but unreadable, unresolved obligations ...)
            escapees = {}                   # S27 §3.5: OURS processes outside `tracked`, killed (verified below)
            killed_ours = {}                # every OURS identity this scan killed: key -> claim
            uncertain = container_failure is not None or order_failure is not None
            with self.lock:
                unreadable = {k: dict(children=set(v["children"]), root=v["root"], claimed=v.get("claimed", False))
                              for k, v in self._unreadable_seen.items()}
            previous, bad, non_converged = {}, {}, False      # C157: reconciled after every full scan
            deadline = None
            while True:         # G1 (round 2 P4): the monotonic deadline, not a round count, bounds this loop
                for attempt in range(3):
                    survivors = []
                    listing = self._processes()
                    edges = self._listing_edges(listing)
                    self._refresh_descendants(unreadable, listing, edges)     # G1 (round 2 P2): readable roots too
                    ancestry = self._ancestry(listing, edges)                 # §3.2: ownership before any denied read
                    self._claim_dropped(unreadable)                           # X11: never dropped before ownership
                    for p in listing:
                        try:
                            verdict = self._classify(p, ancestry)
                        except (self.psutil.NoSuchProcess, ProcessLookupError):
                            continue
                        if verdict[0] == "uncertain":
                            # S27 §3.2: a denied read on a process (a) / (b) claims, or an unreadable session id: a CLAIMED
                            # obligation, resolved against the final process table (gone = discharged), else uncertain
                            rec = verdict[1]
                            ident = (rec["pid"], rec["create_time"])
                            if rec["reason"] is None and any(ident in info["children"] for info in unreadable.values()):
                                continue            # already a descendant obligation of a recorded root
                            self._note_unreadable(unreadable, p, edges, key=ident)
                            if ident in unreadable:
                                unreadable[ident]["claimed"] = True
                                unreadable[ident]["reason"] = rec["reason"]
                            continue
                        if verdict[0] == "count":
                            self._counted.add((p.pid, verdict[1] if len(verdict) > 1 else None))
                            continue
                        if verdict[0] == "foreign_unreadable":
                            # S27 §3.2: unclaimed + a denied read -> `foreign_new` (unreadable), never uncertain; it stays an
                            # UNCLAIMED record so a later state change (exit, pid reuse) still forces a confirming scan (C157)
                            key = verdict[1]
                            if key is None or not any(key in info["children"] for info in unreadable.values()):
                                self._note_unreadable(unreadable, p, edges, key=key or (p.pid, None))
                            self._record_foreign(p, key, path_match=len(verdict) > 2 and verdict[2], unreadable=True)
                            continue
                        if verdict[0] != "ours":
                            continue
                        _, key, claim = verdict
                        try:
                            argv = self._argv(p)
                            p.kill()                       # §3.3: one kill-and-verify loop, tracked and untracked alike
                        except self.psutil.NoSuchProcess:
                            continue
                        except self._denied:
                            # a claimed obligation on the EXACT key, resolved against the final process table
                            self._note_unreadable(unreadable, p, edges, key=key)
                            if key in unreadable:
                                unreadable[key]["claimed"] = True
                                unreadable[key]["reason"] = "access denied"
                            continue
                        survivors.append(p.pid)
                        killed_ours[key] = claim
                        if claim != "tracked" and key not in escapees:
                            escapees[key] = dict(pid=key[0], create_time=key[1], argv=argv, claim=claim)
                    if not survivors:
                        break
                    self._nap(0.05, deadline)
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
                    self._nap(0.05, deadline)
                else:
                    pass
                # C157: every state change (vanished, pid-reused, now readable, readable then gone) needs a full scan
                # AFTER it; a still-present one gets a short settle before it is called uncertain
                confirming = deadline is not None       # any round after the first reconciliation
                if deadline is None:        # G1: one monotonic deadline from the first reconciliation
                    deadline = self._monotonic() + self.reconcile_deadline_s
                while True:
                    bad, states = self._reconcile_unreadable(unreadable)
                    changed = any(state != previous.get(key, ("unresolved", None)) for key, state in states.items())
                    remaining = deadline - self._monotonic()
                    if changed or not bad or remaining <= 0:
                        break
                    self._nap(0.1, deadline)                # never past the deadline
                # G1 (round 3 P9, round 4 P10): a confirming round that ENDS past the deadline, scan AND reconcile,
                # confirmed nothing in time; sampled immediately before the confirmation is accepted
                late = confirming and self._monotonic() >= deadline
                previous = states
                if late or not changed:
                    non_converged = non_converged or late
                    break
                if self._monotonic() >= deadline:
                    non_converged = True    # a change seen at expiry needs a confirming scan there is no time for
                    break
            orphans.update(bad)
            uncertain = uncertain or bool(bad)
            if self._unreadable_overflow:
                uncertain = True
                orphans[(0, "overflow")] = dict(pid=0, create_time=None, argv=[], reason="unreadable records overflowed")
            if non_converged:
                uncertain = True
                orphans[(0, "did not converge")] = dict(pid=0, create_time=None, argv=[], reason="scan did not converge")
            # S27 §3.3: every OURS identity this cleanup killed — the scan's and the tracked audit's last round alike — is
            # verified gone (bounded); X13: a survivor is one that is still alive or not verified gone, never one merely
            # killed in the last round
            to_verify = list(killed_ours) + [k for k in alive if k not in killed_ours]
            unverified, end = [], self._monotonic() + 2.0
            while True:
                unverified = [k for k in to_verify if self._identity_state(*k) != "gone"]
                if not unverified or self._monotonic() >= end:
                    break
                self._nap(0.05, end)
            for key in unverified:
                uncertain = True
                orphans[key] = dict(pid=key[0], create_time=key[1], argv=[], reason="not verified gone")
            survivors = sorted({k[0] for k in unverified})
            if unknown:
                uncertain = True
            verified_escapees = [e for k, e in escapees.items() if k not in unverified]
            self.orphans_unattributed[:] = verified_escapees
            self._uncertain_records = list(orphans.values())
            self._status = dict(
                schema=CLEANUP_SCHEMA,
                survivors=list(survivors), containers_remaining=sorted(self.containers),
                uncertain=bool(uncertain),
                orphans_unattributed=list(self.orphans_unattributed), unknown=unknown, completed=True,
                foreign_new=self._foreign_list(), foreign_new_count=self.foreign_new_count,
                unreadable_count=self.unreadable_count,
            )
            if uncertain:
                self._status["uncertain_records"] = [dict(pid=p["pid"], create_time=p["create_time"], reason=p.get("reason"))
                                                     for p in orphans.values()]
            if container_failure is not None:
                raise container_failure
            if self.failure:           # C157 (P297 U2): a monitor failure is never hidden behind the uncertainty
                raise TransportAbort("process monitor died: " + str(self.failure))
            if survivors:
                raise CleanupUncertain("attributed processes survived cleanup: " + json.dumps(survivors))
            if uncertain:
                raise CleanupUncertain("cleanup uncertain: owned or uninspectable processes remain " + json.dumps(
                    [dict(pid=p["pid"], create_time=p["create_time"], reason=p.get("reason"))
                     for p in orphans.values() if p.get("reason") in UNCERTAIN_REASONS]
                    + [dict(u, reason="tracked identity unknown") for u in unknown]
                ) + (f"; order failure: {order_failure}" if order_failure else ""))
            if survivors:
                raise CleanupUncertain("attributed processes survived cleanup")
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
