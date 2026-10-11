"""P273: bounded retry of an opencode standalone session export on a logged SQLite lock.

`opencode session export --standalone` starts a private `opencode serve`, which dies with SQLite "database is locked"
while the stopped client's own server is still writing its interrupted message. Only that LOGGED cause is retried
(the readiness error alone does not say why), within a short bound; every other export failure still aborts."""
from __future__ import annotations

import time

EXPORT_LOCK_DEADLINE_S = 10.0
EXPORT_LOCK_PAUSE_S = 0.5


def export_lock_contended(result):
    return bool(result.returncode) and "database is locked" in (result.stderr or "")


def run_export(attempt, env, *, timeout=120, deadline_s=EXPORT_LOCK_DEADLINE_S, pause_s=EXPORT_LOCK_PAUSE_S,
               sleep=None, clock=None):
    """(result, attempts): `attempt(env, timeout)` with OPENCODE_PRINT_LOGS=1 on a copy of `env`, repeated only while
    it fails on a logged SQLite lock. The bound is strict: no pause crosses the deadline and every retry's timeout is
    capped to the time left (the first attempt keeps the caller's full `timeout`)."""
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    logged = dict(env, OPENCODE_PRINT_LOGS="1")
    end = clock() + deadline_s
    attempts, budget = 0, timeout
    while True:
        attempts += 1
        result = attempt(logged, budget)
        if not export_lock_contended(result) or clock() + pause_s >= end:
            return result, attempts
        sleep(pause_s)
        budget = max(1.0, min(timeout, end - clock()))


def export_failure_tail(stderr, limit=600):
    """The end of an export's stderr: with OPENCODE_PRINT_LOGS=1 the cause follows many INFO lines."""
    return (stderr or "")[-limit:]
