"""B2 (P426) exclusion locks (spec 9, C227) and the idle gap (spec 1).

Locks are `flock(LOCK_EX | LOCK_NB)` on files under `$STACK_WORKDIR`, fds close-on-exec, held for the holder's lifetime. Acquisition is
serialized by an arbiter: every actor takes `locks/ARBITER.lock` (blocking, bounded 30 s, held only for the acquisition step), then
tries the opposing locks, then takes its OWN lock, then releases the arbiter; an opposing lock held -> the arbiter is released and
the actor refuses. So of two simultaneous starters exactly one runs.

  gate      own `gate/RUNNING`           opposing `p426/SEQUENCER.lock`, `p426/LEG.lock`
  sequencer own `p426/SEQUENCER.lock`    opposing `gate/RUNNING`   (it never takes `LEG.lock`)
  chain     own `p426/LEG.lock`          opposing `gate/RUNNING`   (each chain the sequencer launches takes its own)

Standard library only: the gate imports this before any heavy dependency."""
from __future__ import annotations

import fcntl
import os
import time
from pathlib import Path

ARBITER = "locks/ARBITER.lock"
RUNNING = "gate/RUNNING"
SEQUENCER = "p426/SEQUENCER.lock"
LEG = "p426/LEG.lock"
ARBITER_TIMEOUT_S = 30.0
ARBITER_POLL_S = 0.01
IDLE_GAP_S = 600.0                      # spec 1: a chain refuses to start before 600 s have passed since `p426/LAST_LEG_END`
LAST_LEG_END = "p426/LAST_LEG_END"

OWN = {"gate": RUNNING, "sequencer": SEQUENCER, "chain": LEG}
OPPOSING = {"gate": (SEQUENCER, LEG), "sequencer": (RUNNING,), "chain": (RUNNING,)}
HOLDER = {RUNNING: "a local gate run", SEQUENCER: "the Wave-2 sequencer", LEG: "a P426 chain leg"}


class LockRefused(RuntimeError):
    """The actor must not start: an opposing lock (or its own) is held, or the arbiter could not be taken in time."""


def _open(path):
    """Open (create) a lock file close-on-exec: never inherited by a spawned child (`O_CLOEXEC`, and not inheritable for
    `pass_fds`-less `subprocess` alike)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o644)
    os.set_inheritable(fd, False)
    return fd


def _probe_free(path):
    """Is the opponent's lock free? Opened WITHOUT `O_CREAT` (a probe never creates the opponent's file or directory): a missing file
    is free, nothing holds it; any other open error is a refusal, never "free" (the holder cannot be ruled out)."""
    try:
        fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)
    except FileNotFoundError:
        return True
    except OSError as exc:
        raise LockRefused(f"{Path(path).relative_to(Path(path).parents[1])} cannot be probed ({type(exc).__name__}: {exc.strerror})") from None
    free = _try_lock(fd)
    _unlock(fd)                                                        # only a probe: nothing of the opponent's is kept
    return free


def _try_lock(fd):
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _unlock(fd):
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


class Held:
    """An own lock held until `release()` (idempotent) or the process ends; also a context manager."""

    def __init__(self, actor, path, fd):
        self.actor, self.path, self.fd = actor, Path(path), fd

    def release(self):
        fd, self.fd = self.fd, None
        if fd is not None:
            _unlock(fd)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


def _take_arbiter(wd, timeout_s, clock, sleep):
    fd = _open(Path(wd) / ARBITER)
    deadline = clock() + timeout_s
    while not _try_lock(fd):
        if clock() >= deadline:
            os.close(fd)
            raise LockRefused(f"the acquisition arbiter {ARBITER} could not be taken within {timeout_s:g} s")
        sleep(ARBITER_POLL_S)
    return fd


def acquire(actor, wd, *, arbiter_timeout_s=ARBITER_TIMEOUT_S, clock=time.monotonic, sleep=time.sleep) -> Held:
    """Take `actor`'s own lock under the arbiter (module doc) or raise `LockRefused`; the arbiter is released on every path."""
    if actor not in OWN:
        raise ValueError(f"unknown lock actor {actor!r} (gate, sequencer or chain)")
    wd = Path(wd)
    arbiter = _take_arbiter(wd, arbiter_timeout_s, clock, sleep)
    try:
        for name in OPPOSING[actor]:
            if not _probe_free(wd / name):
                raise LockRefused(f"{name} is held ({HOLDER[name]} is running)")
        fd = _open(wd / OWN[actor])
        if not _try_lock(fd):
            os.close(fd)
            raise LockRefused(f"{OWN[actor]} is held (another {HOLDER[OWN[actor]]} is running)")
        return Held(actor, wd / OWN[actor], fd)
    finally:
        _unlock(arbiter)


def idle_gap_problem(last_leg_end, now, gap_s=IDLE_GAP_S):
    """Spec 1 / 3: None when no leg ended yet or at least `gap_s` seconds passed since `LAST_LEG_END`; else the refusal reason
    (a `LAST_LEG_END` in the future is a gap < gap_s)."""
    if last_leg_end is None:
        return None
    since = now - last_leg_end
    if since >= gap_s:
        return None
    return f"only {since:.0f} s since LAST_LEG_END; a leg waits {gap_s:g} s after the previous one"


def read_last_leg_end(wd):
    """The epoch seconds in `$STACK_WORKDIR/p426/LAST_LEG_END` (one decimal number, as the sequencer writes it), or None when the
    file does not exist; anything else raises ValueError (an unreadable gap record is never read as "no previous leg")."""
    path = Path(wd) / LAST_LEG_END
    try:
        text = path.read_text()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError(f"{LAST_LEG_END} is unreadable ({type(exc).__name__})") from None
    try:
        value = float(text.strip())
    except ValueError:
        raise ValueError(f"{LAST_LEG_END} does not hold a number of seconds") from None
    if not (value >= 0 and value != float("inf")):
        raise ValueError(f"{LAST_LEG_END} does not hold a valid time")
    return value
