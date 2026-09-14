"""Capacity-specific daemon assessments; no model calls or generic smoke verdicts."""
import json
import statistics
import threading
import time

from .scorecard import completed


def assess(rows, expected, *, total, previous, stage, stage_elapsed):
    successful = [r for r in rows if completed(r)]
    durations = [r["elapsed_s"] for r in successful if r.get("elapsed_s") is not None]
    errors = len(rows) - len(successful)
    ratio = remaining = None
    if expected:
        measured = [(i, r["elapsed_s"]) for i, r in enumerate(rows)
                    if completed(r) and r.get("elapsed_s") is not None]
        ratio = (sum(d for _, d in measured) / sum(expected[i] for i, _ in measured)
                 if measured else None)
        remaining = sum(expected[len(rows):]) * (ratio if ratio is not None else 1)
        if stage.startswith("rung ") and len(rows) < total:
            remaining = max(0, remaining - stage_elapsed)
        rate_note = "Matched-rung baseline scaled by observed total/expected total; estimate, not a deadline."
    else:
        rate_note = "Baseline unavailable; growing contexts make a short-rung extrapolation unreliable."
    if errors:
        remaining = None
    unknown = sum(r.get("converged") is None for r in successful)
    limited = sum(r.get("converged") is False for r in successful)
    weak = sum(r.get("retrieval_acc") is not None and r["retrieval_acc"] < .85 for r in successful)
    overdue = bool(expected and stage.startswith("rung ") and len(rows) < total
                   and stage_elapsed > expected[len(rows)] * (ratio or 1))
    if overdue:
        remaining = None
    if errors:
        correction = "STOP: request failed; preserve evidence, inspect transport/worker before resuming."
    elif limited or weak:
        correction = "REVIEW: bounded probe has limited output or weak retrieval; do not claim depth certification."
    elif overdue:
        correction = "REVIEW: current rung exceeds forecast; inspect worker state before deciding whether correction beats completion. No automatic kill."
    else:
        correction = "Continue the approved capacity grid; numeric target flags alone do not require correction."
    return {
        "completed_rungs": len(successful), "attempted_rungs": len(rows), "total_rungs": total,
        "progress_delta": len(successful) - previous, "stage": stage,
        "stage_elapsed_s": round(stage_elapsed, 2),
        "progress_note": "Rung completions measure progress; non-streaming prefill may have no new completions between assessments.",
        "mean_rung_s": statistics.mean(durations) if durations else None,
        "max_rung_s": max(durations, default=None),
        "observed_to_baseline_ratio": ratio, "remaining_s_estimate": remaining,
        "rate_note": rate_note, "errors": errors,
        "nonconverged": limited, "convergence_unknown": unknown,
        "completion_tokens": [r.get("completion_tokens") for r in successful],
        "retrieval_coscores": [r.get("retrieval_acc") for r in successful],
        "within_memory_target": [r.get("within_memory_target") for r in successful],
        "correction": correction,
    }


def _print(event):
    print("[capacity-monitor] " + json.dumps(event, allow_nan=False), flush=True)


class CapacityMonitor:
    """Runs inside the detached capacity driver; emits every 300s and on exit."""
    def __init__(self, total, expected=None, *, emit=_print, interval=300, clock=time.monotonic):
        self.total, self.expected = total, expected
        self.emit, self.interval, self.clock = emit, interval, clock
        self.rows, self.previous = [], 0
        self.label, self.since = "setup", clock()
        self.exit_code = 1
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.failed = threading.Event()
        self.failure = None
        self.thread = threading.Thread(target=self._run, daemon=True, name="capacity-monitor")

    def check_health(self):
        if self.failed.is_set():
            raise RuntimeError("capacity monitor failed") from self.failure

    def stage(self, label):
        self.check_health()
        with self.lock:
            self.label, self.since = label, self.clock()

    def record(self, row):
        self.check_health()
        with self.lock:
            self.rows.append(dict(row))
            self.label, self.since = "between rungs", self.clock()

    def report(self, event, **extra):
        with self.lock:
            result = assess(self.rows, self.expected, total=self.total, previous=self.previous,
                            stage=self.label, stage_elapsed=self.clock() - self.since)
            self.previous = sum(completed(r) for r in self.rows)
        if event == "runner-exit":
            result["correction"] = ("Complete: review the recorded capacity observations and limitations."
                                    if extra.get("exit_code") == 0 else
                                    "STOP: runner failed or grid incomplete; inspect persisted rows, provenance and monitor health.")
        self.emit({"event": event, **result, **extra})

    def _run(self):
        try:
            while not self.stop.wait(self.interval):
                self.report("periodic")
        except Exception as exc:
            self.failure = exc
            self.failed.set()

    def __enter__(self):
        # Exercise the actual assessment and output sink with labelled synthetic data.
        positive = assess([{"execution_status": "completed", "elapsed_s": 2,
                            "retrieval_acc": 1.0}], [2], total=1, previous=0,
                          stage="selftest", stage_elapsed=0)
        if positive["completed_rungs"] != 1 or positive["observed_to_baseline_ratio"] != 1:
            raise RuntimeError("capacity monitor selftest failed")
        self.emit({"event": "SELFTEST", "synthetic": True, "known_positive": positive})
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop.set()
        self.thread.join()
        self.report("runner-exit", exit_code=self.exit_code if exc_type is None and not self.failed.is_set() else 1,
                    exception_type=exc_type.__name__ if exc_type else None)
        self.check_health()
