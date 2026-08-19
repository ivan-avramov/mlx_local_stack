"""Progress-gated bound for long-running agentic sessions (opencode), replacing a flat wall-clock
timeout.

WHY. A flat `subprocess.run(..., timeout=N)` has two failure modes and both cost real time: a
wedged session burns the FULL timeout doing nothing, and a healthy-but-slow session gets killed
mid-progress. This is the design recovered from `docs/handoff-2026-08-16.md`'s "Phase H" section
(that file was later folded into the single `docs/handoff.md` and its Phase H text did not survive
the fold -- recovered via `git show f774e88^:docs/handoff-2026-08-16.md`), quoted verbatim:

    Progress-gated bound for opencode sessions, replacing a fixed timeout. Every 300 s: snapshot
    the workdir to a copy (never race a live write), grade it, record (solution_hash,
    n_failing_tests, repeated_tool_call_signature). Progress = failures decreased, or the file
    changed without failures increasing -> continue past the soft budget. Two consecutive flat
    ticks -> stop (stall). Same signature 3x -> stop (loop). Hard ceiling as backstop only.
    Record stop_reason in {completed, stalled, looping, hard_ceiling}, the failure trajectory,
    tick count and the effective bound. The policy must be IDENTICAL across models -- the dynamic
    part buys early exit on stalls, never extra compute for a favoured model, else pass rates
    encode compute.

This module is the POLICY (`ProgressGate` -- pure, feed it ticks, get a stop decision) and the
ORCHESTRATOR (`run_progress_gated` -- drives a live subprocess). Every external effect (the
process, the clock, the sleep, the snapshot+grade step) is an injected callable, so the whole thing
is testable without ever invoking opencode or a model.
"""
from __future__ import annotations

import dataclasses
import hashlib
import time
from typing import Callable, Optional

# Defaults: the 300 s soft-budget tick and the "2 flat / 3 repeated" thresholds are the recovered
# design's own numbers. `DEFAULT_HARD_CEILING_S` is not given a specific figure in the recovered
# text ("Hard ceiling as backstop only") -- 3600 s matches this campaign's existing definition of a
# "runaway" turn (AGENTS.md: items are re-scanned when they run past 3600 s) and is a deliberately
# GENEROUS backstop, since the tick-based rules are expected to fire first on any wedged session.
DEFAULT_TICK_S = 300
DEFAULT_HARD_CEILING_S = 3600
DEFAULT_STALL_TICKS = 2
DEFAULT_LOOP_REPEATS = 3

STOP_REASONS = ("completed", "stalled", "looping", "hard_ceiling")


@dataclasses.dataclass
class Tick:
    """One progress-gate observation, taken every `tick_s` while the session is alive."""
    elapsed_s: float
    n_failing: Optional[int]   # None = could not grade (e.g. solution file untouched, collection error)
    solution_hash: str
    signature: str              # proxy for "what the session is currently doing" -- see tail_signature
    file_changed: bool          # solution differs from the PREVIOUS tick's (or the pre-run) snapshot


@dataclasses.dataclass
class GateResult:
    stop_reason: str            # one of STOP_REASONS
    ticks: list                 # list[Tick] -- the failure trajectory, in tick order
    elapsed_s: float
    returncode: Optional[int]


def tail_signature(text: str, tail_chars: int = 4000) -> str:
    """Hash of the tail of the session transcript -- the proxy this harness uses for "repeated
    tool-call signature" when there is no structured tool-call event stream to key off (opencode's
    captured stdout/stderr is unstructured text, and its exact event schema is not something this
    module should couple to). Two ticks whose tails hash identically mean nothing NEW appeared in
    the transcript between them -- the same shape as a genuinely repeated tool call, without
    parsing opencode's specific format."""
    return hashlib.sha256(text[-tail_chars:].encode("utf-8", "replace")).hexdigest()[:16]


def solution_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


class ProgressGate:
    """Pure decision policy. Feed it a `Tick` per poll interval via `observe()`; it returns a stop
    reason ("stalled" / "looping") or None ("keep going").

    IDENTICAL for every model -- no per-model tuning. The dynamic part buys early exit on stalls
    only, never extra compute for a favoured model; otherwise pass rates would encode compute
    budget rather than capability (the recovered design's explicit constraint).
    """

    def __init__(self, stall_ticks: int = DEFAULT_STALL_TICKS,
                 loop_repeats: int = DEFAULT_LOOP_REPEATS):
        self.stall_ticks = stall_ticks
        self.loop_repeats = loop_repeats
        self.history: list[Tick] = []
        self._flat_run = 0
        self._sig_run = 0
        self._last_signature: Optional[str] = None
        self._last_n_failing: Optional[int] = None

    def observe(self, tick: Tick) -> Optional[str]:
        self.history.append(tick)

        failures_decreased = (self._last_n_failing is not None and tick.n_failing is not None
                              and tick.n_failing < self._last_n_failing)
        failures_increased = (self._last_n_failing is not None and tick.n_failing is not None
                              and tick.n_failing > self._last_n_failing)
        # PROGRESS = failures decreased, or the file changed without failures increasing.
        progressed = failures_decreased or (tick.file_changed and not failures_increased)

        self._flat_run = 0 if progressed else self._flat_run + 1
        self._sig_run = self._sig_run + 1 if tick.signature == self._last_signature else 1
        self._last_signature = tick.signature
        if tick.n_failing is not None:
            self._last_n_failing = tick.n_failing

        # Loop check first: it is the more specific diagnosis (identical transcript tail across
        # ticks) and can fire independently of the stall counter (e.g. the file is nominally
        # "changing" every tick without the transcript showing anything new).
        if self._sig_run >= self.loop_repeats:
            return "looping"
        if self._flat_run >= self.stall_ticks:
            return "stalled"
        return None


def run_progress_gated(proc, snapshot_fn: Callable[[float], Tick], *,
                       tick_s: int = DEFAULT_TICK_S,
                       hard_ceiling_s: int = DEFAULT_HARD_CEILING_S,
                       poll_s: float = 5.0,
                       stall_ticks: int = DEFAULT_STALL_TICKS,
                       loop_repeats: int = DEFAULT_LOOP_REPEATS,
                       now_fn: Callable[[], float] = time.time,
                       sleep_fn: Callable[[float], None] = time.sleep) -> GateResult:
    """Drive a live subprocess under the progress-gated bound.

    `proc` needs the `subprocess.Popen` surface: `.poll() -> int | None`, `.kill()`, `.wait()`,
    `.returncode`. `snapshot_fn(elapsed_s) -> Tick` does the actual (workdir snapshot + grade)
    work; it is called at most once per `tick_s`, so a slow grade cannot itself starve the session
    of wall-clock, and it is never called concurrently with the process exiting mid-write (checked
    every `poll_s` between ticks, `proc.poll()` is consulted first each iteration).
    """
    gate = ProgressGate(stall_ticks=stall_ticks, loop_repeats=loop_repeats)
    t0 = now_fn()
    next_tick = t0 + tick_s
    stop_reason = None
    while True:
        rc = proc.poll()
        if rc is not None:
            stop_reason = "completed"
            break
        now = now_fn()
        elapsed = now - t0
        if elapsed >= hard_ceiling_s:
            stop_reason = "hard_ceiling"
            proc.kill()
            break
        if now >= next_tick:
            tick = snapshot_fn(elapsed)
            reason = gate.observe(tick)
            if reason is not None:
                stop_reason = reason
                proc.kill()
                break
            next_tick += tick_s
        else:
            sleep_fn(poll_s)
    proc.wait()
    return GateResult(stop_reason=stop_reason, ticks=gate.history,
                       elapsed_s=now_fn() - t0, returncode=getattr(proc, "returncode", None))
