"""P371 (plan 3.1, R23): the generation-neutral per-item file barrier in the probe.

Before each item attempt the probe writes `<run>.item<k>.ready` and waits for `.go` (or `.stop`); after the row is
written it writes `<run>.item<k>.done` (the row key, evidence paths + sha256) and waits for `.continue` (or `.stop`).
The chain runs its hooks between the two (`ChainHooks.before_attempt` / `after_attempt`); the probe never imports them.
Files are exclusive-create (written complete, then linked into place, so the chain never reads a partial file); a
`.stop` wins over `.go` / `.continue`. Timeout and cancel behave like the manifest ack (`tg1_runner._wait_for_ack`):
the ack is checked first, then the cancel callable, then the deadline. Disabled (the default for tg1): no files, no
wait."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import token_turn_gate as tg

ACK_TIMEOUT_S = 300                      # = tg1_runner.ACK_TIMEOUT_S (tested equal)
ACK_POLL_S = 0.5


class BarrierError(tg.TransportAbort):
    """A barrier file already exists (a replayed or duplicated item index) or cannot be written."""


class BarrierTimeout(tg.TransportAbort):
    pass


class BarrierCancelled(tg.TransportAbort):
    """The runner's cooperative cancel was honoured while waiting (the core maps it to its own cancel exception)."""


class ItemBarrier:
    def __init__(self, run_stem, enabled, timeout_s=ACK_TIMEOUT_S, cancel=None, *, cancel_exc=None,
                 poll_s=ACK_POLL_S, clock=time.monotonic, sleep=time.sleep):
        self.stem = str(run_stem)
        self.enabled = bool(enabled)
        self.timeout_s = timeout_s
        self.cancel = cancel
        self.cancel_exc = cancel_exc or BarrierCancelled
        self.poll_s, self.clock, self.sleep = poll_s, clock, sleep

    def path(self, k, kind):
        return Path(f"{self.stem}.item{k}.{kind}")

    @staticmethod
    def _check(k):
        if not (type(k) is int and k >= 0):
            raise ValueError(f"item index must be a non-negative integer, got {k!r}")

    def _create(self, path, content=b""):
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "wb") as fp:
                fp.write(content)
                fp.flush()
                os.fsync(fp.fileno())
            try:
                os.link(tmp, path)                    # fails when the file exists: exclusive create
            except FileExistsError:
                raise BarrierError(f"barrier file {path.name} already exists") from None
            except OSError as exc:
                raise BarrierError(f"barrier file {path.name} cannot be created: {exc}") from exc
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass

    def _wait(self, k, accept, stop="stop"):
        accept_path, stop_path = self.path(k, accept), self.path(k, stop)
        deadline = self.clock() + self.timeout_s
        while True:
            if stop_path.exists():
                return "stop"
            if accept_path.exists():
                return accept
            if self.cancel is not None and self.cancel():
                raise self.cancel_exc()
            if self.clock() >= deadline:
                raise BarrierTimeout(f"item barrier {accept} for item {k} not acknowledged")
            self.sleep(self.poll_s)

    def stop_payload(self, k):
        """The JSON object the chain wrote into `.stop` (`{}` when it wrote none or not an object): the disposition the
        probe records in its manifest's `hook_stop`."""
        try:
            doc = json.loads(self.path(k, "stop").read_text() or "{}")
        except (OSError, ValueError):
            return {}
        return doc if isinstance(doc, dict) else {}

    def ready(self, k):
        """Write `.ready`, wait for the chain: returns `go` or `stop`."""
        self._check(k)
        if not self.enabled:
            return "go"
        self._create(self.path(k, "ready"))
        return self._wait(k, "go")

    def done(self, k, record):
        """Write `.done` with `record`, wait for the chain: returns `continue` or `stop`."""
        self._check(k)
        if not self.enabled:
            return "continue"
        self._create(self.path(k, "done"), (json.dumps(record, sort_keys=True) + "\n").encode())
        return self._wait(k, "continue")
