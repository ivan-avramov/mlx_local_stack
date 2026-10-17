"""Adapter shell watchdog (M64 spec 5.4): the 600 s deadline for every OBSERVED tool descendant, equal across arms.

The adapter keeps a tool-execution window per tool call (from its start/end events). Every descendant of the client
process whose start time falls inside a window (open or closed) is attributed to that window; client helpers
started outside any window (LSP servers, indexers) are not. An attributed process older than `limit_s` is sent
SIGTERM, then SIGKILL after `grace_s` if it is still the same live identity, together with its attributed
descendants; the row gets an `exec_timeout` flag. With parallel tool calls a process belongs to the earliest open
window containing its start time. Identity is the exact (pid, start) pair recorded at the first observation, so a
child that detaches AFTER it was observed (reparented to init) is still found and killed; one that detaches BEFORE its
first observation escapes (the disclosed G2 residual, never a pass criterion).

All process effects go through three injectable seams (`listing`, `alive`, `send`); `for_client` builds the real
psutil ones. This module has no client or scoring dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import signal
import time

LIMIT_S = 600.0
GRACE_S = 5.0


@dataclass(frozen=True)
class Proc:
    pid: int
    ident: float          # exact start identity (proc_guard.start_time on the real seam)
    wall_start: float     # wall-clock start, comparable with tool window times
    ppid: int


class ShellWatchdog:
    def __init__(self, *, limit_s=LIMIT_S, grace_s=GRACE_S, clock=time.time, listing, alive, send):
        self.limit_s, self.grace_s, self.clock = float(limit_s), float(grace_s), clock
        self.listing, self.alive, self.send = listing, alive, send
        self.windows = {}              # key -> {key, name, start, end}
        self.observed = {}             # (pid, ident) -> Proc, every descendant ever listed
        self.kills = []                # one record per signalled process
        self._kill_by_key = {}
        self._overrun_seen = set()
        self.window_overruns = []

    # -- windows
    def open_window(self, key, name, start):
        self.windows[key] = dict(key=key, name=name, start=float(start), end=None)

    def close_window(self, key, end):
        if key in self.windows:
            self.windows[key]["end"] = float(end)

    def set_windows(self, windows):
        """Replace the event-derived windows with `[(start, end_or_None, name)]` (keys `ev<n>`); live windows opened
        by `open_window` are kept. For clients that report a tool only when it completes."""
        kept = {k: w for k, w in self.windows.items() if not k.startswith("ev")}
        self.windows = {**kept, **{f"ev{i}": dict(key=f"ev{i}", name=name, start=float(start),
                                                  end=None if end is None else float(end))
                                   for i, (start, end, name) in enumerate(windows)}}

    def _window_of(self, wall_start):
        for w in sorted(self.windows.values(), key=lambda w: (w["start"], w["key"])):
            if w["start"] <= wall_start and (w["end"] is None or wall_start <= w["end"]):
                return w
        return None

    @property
    def exec_timeout(self):
        return bool(self.kills or self.window_overruns)

    # -- one observation tick
    def tick(self, now=None):
        now = self.clock() if now is None else now
        for p in self.listing():
            self.observed[(p.pid, p.ident)] = p
        for key in [k for k in self.observed if not self.alive(*k)]:
            del self.observed[key]
        for w in self.windows.values():
            if w["end"] is not None and w["end"] - w["start"] > self.limit_s and w["key"] not in self._overrun_seen:
                self._overrun_seen.add(w["key"])
                self.window_overruns.append(dict(name=w["name"], start=w["start"], end=w["end"],
                                                 duration_s=w["end"] - w["start"]))
        events = []
        events += self._escalate(now)
        events += self._terminate_overdue(now)
        return events

    def _record(self, p, action, window, now):
        events = dict(pid=p.pid, ident=p.ident, action=action, window=dict(window), at=now,
                      age_s=now - p.wall_start)
        rec = self._kill_by_key.get((p.pid, p.ident))
        if rec is None:
            rec = dict(pid=p.pid, ident=p.ident, window=dict(window), term_at=None, actions=[])
            self._kill_by_key[(p.pid, p.ident)] = rec
            self.kills.append(rec)
        rec["actions"].append(action)
        if action == "SIGTERM":
            rec["term_at"] = now
        return events

    def _attributed(self):
        return {key: (p, w) for key, p in self.observed.items() if (w := self._window_of(p.wall_start)) is not None}

    def _terminate_overdue(self, now):
        events = []
        attributed = self._attributed()
        overdue = sorted((p for key, (p, w) in attributed.items()
                          if now - p.wall_start > self.limit_s and key not in self._kill_by_key),
                         key=lambda p: (p.wall_start, p.pid))
        for p in overdue:
            if (p.pid, p.ident) in self._kill_by_key:             # taken with an older offender of this tick
                continue
            group = [p] + self._attributed_descendants(p, attributed)
            for q in group:
                if (q.pid, q.ident) in self._kill_by_key:
                    continue
                window = attributed[(q.pid, q.ident)][1]
                self.send(q.pid, q.ident, signal.SIGTERM)
                events.append(self._record(q, "SIGTERM", window, now))
        return events

    def _attributed_descendants(self, root, attributed):
        by_parent = {}
        for key, (p, w) in attributed.items():
            by_parent.setdefault(p.ppid, []).append(p)
        out, todo, seen = [], [root.pid], {root.pid}
        while todo:
            for child in by_parent.get(todo.pop(), []):
                if child.pid not in seen and child.wall_start >= root.wall_start:
                    seen.add(child.pid)
                    out.append(child)
                    todo.append(child.pid)
        return out

    def _escalate(self, now):
        events = []
        for key, rec in self._kill_by_key.items():
            if "SIGKILL" in rec["actions"] or rec["term_at"] is None:
                continue
            if not self.alive(*key):
                continue
            if now - rec["term_at"] >= self.grace_s:
                self.send(rec["pid"], rec["ident"], signal.SIGKILL)
                p = self.observed.get(key) or Proc(rec["pid"], rec["ident"], rec["ident"], 0)
                events.append(self._record(p, "SIGKILL", rec["window"], now))
        return events

    # -- the real seams
    @classmethod
    def for_client(cls, root_pid, *, limit_s=LIMIT_S, grace_s=GRACE_S, clock=time.time, only=None):
        """Watch the descendants of `root_pid` with psutil. `only` (a pid set) narrows the listing (tests)."""
        import psutil
        from . import proc_guard

        def listing():
            found = []
            try:
                kids = psutil.Process(root_pid).children(recursive=True)
            except psutil.Error:
                return found
            for p in kids:
                if only is not None and p.pid not in only:
                    continue
                try:
                    found.append(Proc(pid=p.pid, ident=proc_guard.start_time(p), wall_start=p.create_time(),
                                      ppid=p.ppid()))
                except (psutil.Error, proc_guard.TransportAbort):
                    continue
            return found

        def alive(pid, ident):
            try:
                p = psutil.Process(pid)
                return proc_guard.start_time(p) == ident and p.status() not in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD)
            except (psutil.Error, proc_guard.TransportAbort):
                return False

        def send(pid, ident, sig):
            if alive(pid, ident):                                   # never signal a reused pid
                try:
                    os.kill(pid, sig)
                except ProcessLookupError:
                    pass

        return cls(limit_s=limit_s, grace_s=grace_s, clock=clock, listing=listing, alive=alive, send=send)
