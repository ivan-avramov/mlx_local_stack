"""M62 best-effort process attribution, memory monitoring and durable artifacts.

A fork that detaches and leaves scratch between samples can escape attribution.
New same-uid orphans are diagnostic only and are never killed without attribution.
"""

from __future__ import annotations
from contextlib import contextmanager
import json
import os
from pathlib import Path
import posixpath
import re
import shlex
import signal
import stat
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
        self._status = None

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

    def _same_identity(self, pid, created):
        try:
            return self.get(pid).create_time() == created
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
            for p in processes:
                try:
                    if not self._protected(p):
                        # ppid() re-validates identity; a stale cached entry (pid reused, psutil keeps the old
                        # create_time) raises here and must never become an ancestry authority (V5a P13).
                        ppids[p.pid] = p.ppid()
                        alive[p.pid] = (p, p.create_time())
                except self._transient:
                    ppids.pop(p.pid, None)
                    alive.pop(p.pid, None)
            # Follow ancestry until its transitive closure; detachments retain recorded ownership.
            changed = True
            while changed:
                changed = False
                for pid, (p, created) in alive.items():
                    key = (pid, created)
                    parent = alive.get(ppids[pid])
                    if parent and parent[1] > created:
                        parent = None   # a parent cannot be younger than its child: pid reuse
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
        if self._protected(p) or p.create_time() != key[1]:
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
                            argv = self._argv(p)
                            p.kill()
                            killed.append(dict(pid=pid, create_time=created, role=actual, argv=argv))
                    except self.psutil.NoSuchProcess:
                        pass
            self.killed.extend(killed)
        return killed

    def graceful_stop(self, role, wait):
        """SIGTERM every tracked live process of `role` and wait up to `wait` seconds for them to exit.

        Returns [{pid, create_time, role, argv}] of the processes signalled; survivors are the caller's to
        SIGKILL (`kill_role`). Ancestry is sampled first, as in `kill_role` (C147)."""
        signalled = []
        with self.lock:
            self.tick()
            for (pid, created), actual in list(self.tracked.items()):
                if actual != role:
                    continue
                try:
                    p = self.get(pid)
                    if not self._protected(p) and p.create_time() == created and self._live(p):
                        argv = self._argv(p)
                        p.terminate()
                        signalled.append(dict(pid=pid, create_time=created, role=actual, argv=argv))
                except self._transient:
                    pass
        self.verify_gone(signalled, wait=wait)
        return signalled

    def verify_gone(self, killed, wait=0.0):
        """True when no killed (pid, create_time) is still a live process (polled up to `wait` seconds)."""
        deadline = time.monotonic() + wait
        while True:
            alive = False
            for entry in killed:
                if self._same_identity(entry["pid"], entry["create_time"]):
                    try:
                        alive = alive or self._live(self.get(entry["pid"]))
                    except self._transient:
                        continue
            if not alive:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    def status(self):
        """Cleanup outcome for abort manifests; `uncertain` until cleanup() has completed (C147)."""
        if self._status is None:
            return dict(survivors=[], containers_remaining=sorted(self.containers),
                        uncertain=True, orphans_unattributed=list(self.orphans_unattributed),
                        completed=False)
        return dict(self._status)

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
            container_failure = None
            for name in list(self.containers):
                try:
                    self.remove_container(name)
                except TransportAbort as exc:
                    container_failure = container_failure or exc
            survivors = []
            orphans = {}
            uncertain = container_failure is not None
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
            self._status = dict(
                survivors=list(survivors), containers_remaining=sorted(self.containers),
                uncertain=bool(uncertain),
                orphans_unattributed=list(self.orphans_unattributed), completed=True,
            )
            if container_failure is not None:
                raise container_failure
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


# ---------------------------------------------------------------------------------------------------------------
# C147 §4: /tmp escape diagnostic and exact-path cleanup.
# ---------------------------------------------------------------------------------------------------------------

TMP_ROOT = "/tmp"           # injectable for tests (`root=` arguments default to this)
_PRE_UNLINK_HOOK = None     # test seam: runs between the final identity check and the unlink
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

    def add(path, source, exact, token, status):
        if any(_under(_tmp_norm(posixpath.normpath(path)), _tmp_norm(posixpath.normpath(d))) for d in own):
            return
        key = (path, source, token)
        if key in seen:
            return
        seen.add(key)
        found.append(dict(path=path, source=source, exact=exact, token=token, status=status))

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
                    add(path, name, True, raw, status)
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


def _tree_qualifies(fd, window, uid):
    """Every entry under the directory fd is a regular file or directory we own, born inside the window."""
    for name in os.listdir(fd):
        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
        try:
            _qualify(st, window, uid)
        except _Refuse:
            return False
        if stat.S_ISDIR(st.st_mode):
            child = _open_dir_nofollow(name, fd)
            try:
                if not _tree_qualifies(child, window, uid):
                    return False
            finally:
                os.close(child)
        elif not stat.S_ISREG(st.st_mode):
            return False
    return True


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


def _remove_tree(fd, window, uid):
    for name in os.listdir(fd):
        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if stat.S_ISDIR(st.st_mode):
            child = _open_dir_nofollow(name, fd)
            try:
                if (os.fstat(child).st_ino, os.fstat(child).st_dev) != (st.st_ino, st.st_dev):
                    raise _Refuse("replaced")
                _remove_tree(child, window, uid)
            finally:
                os.close(child)
            os.rmdir(name, dir_fd=fd)
        else:
            _unlink_checked(name, fd, (st.st_ino, st.st_dev))


def _clean_one(path, before, after, window, root, uid):
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
                continue
            if stat.S_ISDIR(st.st_mode):
                child = _open_dir_nofollow(name, cursor)
                opened.append(child)
                if (os.fstat(child).st_ino, os.fstat(child).st_dev) != (st.st_ino, st.st_dev):
                    raise _Refuse("replaced")
                if not _tree_qualifies(child, window, uid):
                    raise _Refuse("dir_mixed")
                _remove_tree(child, window, uid)
                os.rmdir(name, dir_fd=cursor)
            elif stat.S_ISREG(st.st_mode):
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=cursor)
                try:
                    if (os.fstat(fd).st_ino, os.fstat(fd).st_dev) != (st.st_ino, st.st_dev):
                        raise _Refuse("replaced")
                finally:
                    os.close(fd)
                _unlink_checked(name, cursor, (st.st_ino, st.st_dev))
            else:
                raise _Refuse("not_regular")
    finally:
        for fd in opened:
            os.close(fd)


def tmp_clean(candidates, before, after, window, *, root=None, uid=None, allow_shell=False):
    """Remove only what the deletion authority of spec §4 allows; return (cleaned, [[path, reason], ...]).

    Automatic mode removes an EXACT `write` part with status completed, or an `edit` part on a name absent from the
    pre-item listing. Shell mentions are skipped unless `allow_shell` (the operator tool, explicit --yes), which
    still applies every identity check. `before`/`after` of None (operator tool: no listings) skip the listing
    checks; the birthtime window and ownership checks always apply. Residual: the microseconds between the final
    fstatat and the unlink."""
    root = TMP_ROOT if root is None else str(root)
    uid = os.getuid() if uid is None else uid
    cleaned, kept, done = [], [], set()
    for candidate in candidates:
        path = candidate["path"]
        if path in done:
            continue
        if not candidate.get("exact") and not allow_shell:
            continue
        done.add(path)
        try:
            if candidate.get("exact"):
                source, status = candidate.get("source"), candidate.get("status")
                if source == "write" and status != "completed":
                    parts = path[len("/tmp/"):].split("/") if path.startswith("/tmp/") else []
                    if any(c in ("", ".", "..") for c in parts):
                        raise _Refuse("traversal")
                    raise _Refuse("ambiguous")
                if source not in ("write", "edit"):
                    raise _Refuse("ambiguous")
            _clean_one(path, before, after, window, root, uid)
            cleaned.append(path)
        except _Refuse as refusal:
            kept.append([path, refusal.reason])
        except OSError:
            kept.append([path, "missing"])
    return cleaned, kept
