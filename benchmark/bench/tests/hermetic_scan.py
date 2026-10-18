"""Test-only hermetic process scan (P371 deterministic real-guard tests). Stdlib + psutil only (copied verbatim into the A14
bundle, which imports no repository module from here).

`proc_guard.ProcessGuard`'s cleanup sweep lists EVERY same-uid live process; a launchd-parented (ppid 1) process in another
session that starts during an item window and is not tracked (macOS Spotlight's `mdworker_shared` / `MDSImporterWorker`) is
recorded in `orphans_unattributed`, so a real-guard test's exact `cleanup_status` depended on box activity. `FamilyScan(root_pid)`
is a callable usable as `ProcessGuard(scan=...)`: each call lists `psutil.process_iter()` and returns only

  (a) live descendants of `root_pid` (the ppid chain is walked, bounded),
  (b) members of a session in which a descendant was observed in this or any EARLIER call of this scan (accumulated sids), and
  (c) members of `os.getsid(root_pid)`'s session (the probe session; the sweep excludes it and tracking is unchanged).

Everything else (Spotlight, applications, other agents' setsid'd jobs) is invisible. LIMIT: a leak that setsid's and whose parent
dies before any call observed it is invisible too, so a test that deliberately detects such a leak on the real box must opt out
(`@pytest.mark.real_process_scan`); every scenario without a setsid'd leak is deterministic.

`install(target, root_pid)` patches `target.__init__` (a class) or `target.ProcessGuard.__init__` (a module) so a guard built
without `scan=` gets its own `FamilyScan(root_pid)`; it returns the undo callable."""
from __future__ import annotations

import os

MAX_DEPTH = 64


class FamilyScan:
    def __init__(self, root_pid, max_depth=MAX_DEPTH):
        self.root = int(root_pid)
        self.max_depth = max_depth
        self.sids = set()
        sid = _sid(self.root)
        if sid is not None:
            self.sids.add(sid)

    def __call__(self):
        import psutil
        procs, ppid = [], {}
        for p in psutil.process_iter():
            try:
                ppid[p.pid] = p.ppid()
            except (psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError):
                continue
            procs.append(p)
        family = set()
        for pid in ppid:
            chain, cur = [], pid
            for _ in range(self.max_depth):
                if cur == self.root or cur in family:
                    family.update(chain + [pid])
                    break
                chain.append(cur)
                cur = ppid.get(cur)
                if cur is None or cur <= 1:
                    break
        for pid in family:
            if pid != self.root:
                sid = _sid(pid)
                if sid is not None:
                    self.sids.add(sid)
        out = []
        for p in procs:
            if p.pid in family or p.pid == self.root:
                out.append(p)
                continue
            sid = _sid(p.pid)
            if sid is not None and sid in self.sids:
                out.append(p)
        return out


def _sid(pid):
    try:
        return os.getsid(pid)
    except (ProcessLookupError, PermissionError, OSError):
        return None


def install(target, root_pid):
    cls = target if isinstance(target, type) else target.ProcessGuard
    original = cls.__init__

    def __init__(self, *args, scan=None, **kwargs):
        original(self, *args, scan=scan if scan is not None else FamilyScan(root_pid), **kwargs)

    cls.__init__ = __init__
    return lambda: setattr(cls, "__init__", original)


# a subprocess that runs a script with the hermetic scan installed (root = that subprocess), for test helpers that launch a
# real probe: `[sys.executable, "-c", BOOTSTRAP, script, *args]`; never through an environment variable read by production code
BOOTSTRAP = (
    "import os, runpy, sys\n"
    "sys.path.insert(0, %(tests)r)\n"
    "import hermetic_scan\n"
    "from bench import proc_guard\n"
    "hermetic_scan.install(proc_guard, os.getpid())\n"
    "script = sys.argv[1]\n"
    "sys.argv = sys.argv[1:]\n"
    "runpy.run_path(script, run_name='__main__')\n"
)


def subprocess_command(script, *args):
    import sys
    return [sys.executable, "-c", BOOTSTRAP % dict(tests=os.path.dirname(os.path.abspath(__file__))), str(script), *args]
