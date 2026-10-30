"""B2 (P426) chain hooks (spec 4.2, 4.5, 16.1, 16.2): at an item's `ready` barrier the ready record is written before `.go`;
at its `done` barrier the item is settled, reconciled (`p426_reconcile`), its engagement judged and the item record
written before the barrier answer. Any failed check is `invalidate` (systemic); an unreadable /metrics or a record that
cannot be written is a `HookInfrastructureError` (systemic in P426 mode, never a `pre_spawn_incident`)."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from . import chain_hooks as ch
from . import chain_rows as cr
from . import p426_reconcile as pr

ITEMS_DIR = "items"
INJECTED_MISMATCH = "reconciliation mismatch (injected)"        # spec 16.8: the exact `invalidate` reason of R2
LOG_BOUNDS = "log_bounds.json"


# -- records
def canonical(doc) -> bytes:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def seal(doc: dict) -> dict:
    """`doc` + its `sha256` (the canonical JSON of the record without that field, spec 16)."""
    body = {k: v for k, v in doc.items() if k != "sha256"}
    return dict(body, sha256=hashlib.sha256(canonical(body)).hexdigest())


def sealed_ok(doc) -> bool:
    return isinstance(doc, dict) and doc.get("sha256") == seal(doc)["sha256"]


def write_exclusive(path, doc: dict) -> dict:
    """Exclusive-create the sealed record; an existing file is a refusal (never overwritten)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sealed = seal(doc)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(sealed, indent=1, sort_keys=True) + "\n")
    return sealed


def log_stat(path) -> dict:
    st = os.stat(path)
    return dict(path=str(path), device=st.st_dev, inode=st.st_ino, offset=st.st_size)


def same_identity(ops, pid, start) -> bool:
    """True while `pid` is still the process that started at `start`, read through `ChainOps.create_time(pid)` (spec 16.6);
    a pid the clock cannot read is gone."""
    try:
        return ops.create_time(pid) == start
    except Exception:  # noqa: BLE001  (psutil.NoSuchProcess and friends: the process is not there)
        return False


def portable_log(path) -> str:
    """`log_bounds.json` is a `main` record (spec 16.7): its paths are `<WT>/logs/<name>`, never absolute."""
    return f"<WT>/logs/{Path(path).name}"


def log_bounds_problems(out_root, path) -> list:
    """The file at `path` is still the one `log_bounds.json` recorded: same device / inode, not truncated below the start."""
    f = Path(out_root) / LOG_BOUNDS
    try:
        doc = json.loads(f.read_text())
    except (OSError, ValueError):
        return [f"{LOG_BOUNDS} is missing or unreadable"]
    entry = next((e for e in doc.get("files") or [] if e.get("path") == portable_log(path)), None)
    if entry is None:
        return [f"{LOG_BOUNDS} does not record {path}"]
    try:
        st = os.stat(path)
    except OSError as exc:
        return [f"{path} is gone: {exc}"]
    if (st.st_dev, st.st_ino) != (entry["device"], entry["inode"]):
        return [f"{path} was replaced (device/inode differ from {LOG_BOUNDS})"]
    if st.st_size < entry["offset_start"]:
        return [f"{path} was truncated below its recorded start"]
    return []


class P426Hooks(ch.ChainHooks):
    def __init__(self, *, ops, out_root, arm, settle_bound_s, clock=time.time, sleep=time.sleep, inject=None):
        self.ops, self.out_root, self.arm = ops, Path(out_root), str(arm)
        self.settle_bound_s, self.clock, self.sleep = float(settle_bound_s), clock, sleep
        self.inject = inject                                # rehearsal only (spec 16.8): `reconcile-mismatch` perturbs the first item
        self._first_done = True                             # the next `done` is the leg's first item
        self.router = None                                  # {pid, start}: bound by the chain once it owns a router
        self.ready_checks = None                            # () -> [problem]: bound by the chain (spec 3, Item `ready` row)

    def bind_router(self, pid, start):
        """The chain's owned router identity `(pid, ChainOps.create_time(pid))`, compared at every barrier (spec 3)."""
        self.router = dict(pid=pid, start=start)

    def bind_ready_checks(self, checks):
        """The chain's `ready` checks beyond the owned identities (spec 3): registry sha, lifecycle hash, worktree clean. `checks()`
        returns the problems found; a check that cannot run raises and is a `HookInfrastructureError` (systemic)."""
        self.ready_checks = checks

    def _ready_problems(self):
        if self.ready_checks is None:
            return []
        try:
            return list(self.ready_checks())
        except Exception as exc:  # noqa: BLE001
            raise ch.HookInfrastructureError(f"a ready check could not run: {exc}") from None

    # -- paths
    def _record(self, slot, suffix):
        return self.out_root / ITEMS_DIR / f"{cr.slot_file(slot)}.{suffix}"

    def _snapshot(self):
        try:
            metrics = self.ops.worker_metrics()
        except Exception as exc:  # noqa: BLE001
            raise ch.HookInfrastructureError(f"worker /metrics unreadable: {exc}") from None
        summary = pr._summary(metrics) if metrics else None
        if not isinstance(summary, dict) or "in_flight" not in summary:
            raise ch.HookInfrastructureError("worker /metrics unreadable")
        return dict(summary)

    def _snapshot_or_none(self):
        """The `done` side: an unreadable `/metrics` is recorded in the item record, never raised before it is written (P39)."""
        try:
            return self._snapshot()
        except ch.HookInfrastructureError:
            return None

    def _owned(self, context):
        worker = dict((context.get("load") or {}).get("worker") or {})
        return dict(router=dict(self.router) if self.router else None, worker=worker)

    def _identity_problems(self, context):
        """Owned identities by `(pid, create_time(pid))` (spec 3 / 16.6): the worker's from the load context, the router's as
        bound by the chain; a process that is gone or replaced differs."""
        load = context.get("load") or {}
        problems = []
        cur = self.ops.worker_ident(load.get("model"))
        want = load.get("worker") or {}
        if not cur or (cur.get("pid"), cur.get("create_time")) != (want.get("pid"), want.get("create_time")):
            problems.append("owned worker identity changed or the worker is gone")
        if self.router is not None and not same_identity(self.ops, self.router["pid"], self.router["start"]):
            problems.append("owned router identity changed or the router is gone")
        return problems

    # -- ready
    def before_attempt(self, slot, context=None):
        if context is None:
            raise ch.HookInfrastructureError("before_attempt called without the chain's hook context")
        problems = self._identity_problems(context) + self._ready_problems()
        path = self.ops.server_log_path()
        problems += log_bounds_problems(self.out_root, path)
        if problems:
            return ch.Disposition.invalidate("; ".join(problems))
        record = dict(slot=slot, item=context.get("item"), k=context.get("k"), log_cursor=dict(log_stat(path), path=portable_log(path)),
                      worker_snapshot=self._snapshot(), owned=self._owned(context), at=self.clock())
        try:
            write_exclusive(self._record(slot, "ready.json"), record)
        except OSError as exc:
            raise ch.HookInfrastructureError(f"ready record not written: {exc}") from None
        return ch.Disposition.accept()

    # -- done
    def read_ready(self, slot):
        """The slot's sealed ready record, or None (missing / unreadable / bad self-hash)."""
        try:
            doc = json.loads(self._record(slot, "ready.json").read_text())
        except (OSError, ValueError):
            return None
        return doc if sealed_ok(doc) else None

    def _window(self, slot, ready):
        """Settle, then read the window from the ready cursor to the post-settle end. -> (settle, data, end, problems)."""
        cur = ready["log_cursor"]
        path = self.ops.server_log_path()
        problems = log_bounds_problems(self.out_root, path)
        st = log_stat(path)
        if (st["device"], st["inode"]) != (cur["device"], cur["inode"]) or st["offset"] < cur["offset"]:
            problems.append(f"{path} was replaced or truncated since the ready record")
        if problems:
            return None, b"", cur["offset"], problems
        try:
            res = pr.settle(self._snapshot_or_none, lambda _c: self.ops.read_log(path, cur["offset"]), cur,
                            bound_s=self.settle_bound_s, clock=self.clock, sleep=self.sleep)
        except pr.LogParseError as exc:                  # an unparseable worker request line is systemic (spec 4.3)
            return None, b"", cur["offset"], [f"unparseable request line while settling: {exc}"]
        end = log_stat(path)["offset"]
        return res, self.ops.read_log(path, cur["offset"], end), end, []

    def _item_record(self, slot, ready, report, res, data, end, before, after, extra_checks, case=None):
        checks = dict(report.checks) if report else {}
        checks.update(extra_checks)
        problems = (report.problems if report else []) + [f"{n}: {c['detail']}" for n, c in extra_checks.items() if not c["ok"]]
        return dict(slot=slot, ready_sha256=(ready or {}).get("sha256"),         # §4.5: the ready record's self-hash
                    log_range=dict(start=ready["log_cursor"]["offset"] if ready else None, end=end,
                                   sha256=hashlib.sha256(data).hexdigest()),
                    worker_before=before, worker_after=after, case=case or (report.case if report else None),
                    requests=report.requests if report else [], totals=report.totals if report else {},
                    checks=checks, verdict="reconciled" if not problems else "invalid", problems=problems)

    def after_attempt(self, slot, done, context=None):
        """Every `done` outcome writes the item record before the barrier answer, an `invalidate` included (spec 4.5)."""
        if context is None:
            raise ch.HookInfrastructureError("after_attempt called without the chain's hook context")
        ready = self.read_ready(slot)
        pre, res, data, end, extra, report = [], None, b"", None, {}, None
        if ready is None:
            pre.append(f"missing or corrupt ready record for {slot}")
        else:
            pre += self._identity_problems(context)
            res, data, end, wp = self._window(slot, ready)
            pre += wp
        if pre:
            extra["preconditions"] = dict(ok=False, detail="; ".join(pre))
        held = self._ready_problems()                    # spec 3, `done` row: the `ready` checks (registry, lifecycle, worktree) again
        if held:
            extra["ready_checks"] = dict(ok=False, detail="; ".join(held))
        before, after = (ready or {}).get("worker_snapshot"), self._snapshot_or_none()
        if after is None:
            extra["metrics"] = dict(ok=False, detail="worker /metrics unreadable after the item")
        if res is not None:
            extra["settle"] = dict(ok=res.settled, detail=f"in_flight={res.in_flight} waited_s={res.waited_s:.1f}")
        if not pre and res.settled and after is not None:
            try:
                lines = pr.parse_log(data)
            except pr.LogParseError as exc:
                extra["parse"] = dict(ok=False, detail=str(exc))
            else:
                report = pr.reconcile_item(context.get("row") or {}, lines, before, after)
                eng = pr.engagement_problems(report.requests, self.arm, item=True)
                extra["engagement"] = dict(ok=not eng, detail="; ".join(eng) or
                                           f"arm {self.arm}; <=1-token requests listed: {pr.short_requests(report.requests)}")
        elif res is not None and not res.settled:
            extra["settle"]["detail"] += " (not settled within the bound)"
        injected = self.inject == "reconcile-mismatch" and self._first_done
        self._first_done = False
        if injected:                                         # R2 (spec 1 / 16.8): the first item's reconciliation is perturbed
            extra["injected"] = dict(ok=False, detail=INJECTED_MISMATCH)
        record = self._item_record(slot, ready, report, res, data, end, before, after, extra)
        try:
            write_exclusive(self._record(slot, "json"), record)
        except OSError as exc:
            raise ch.HookInfrastructureError(f"item record not written: {exc}") from None
        if injected:
            return ch.Disposition.invalidate(INJECTED_MISMATCH)
        if record["verdict"] != "reconciled":
            return ch.Disposition.invalidate("; ".join(record["problems"])[:600])
        return ch.Disposition.accept()

    # -- DNF (spec 4.3 DNF rows, 5.3): used by the chain's DNF eligibility check
    def dnf_problems(self, slot, abort_manifest):
        """Settle, reconcile the DNF window against the abort manifest and write `items/<slot_file>.dnf.json`.
        -> (problems, item_record). A missing ready record or an unsettled window is a problem (systemic)."""
        ready = self.read_ready(slot)
        if ready is None:
            return [f"no ready record for {slot} (an abort before the slot's .ready is systemic)"], None
        res, data, end, wp = self._window(slot, ready)
        if wp:
            return wp, None
        before, after = ready["worker_snapshot"], self._snapshot()
        extra = dict(settle=dict(ok=res.settled, detail=f"in_flight={res.in_flight} waited_s={res.waited_s:.1f}"))
        report = None
        if res.settled:
            try:
                report = pr.reconcile_dnf(abort_manifest, pr.parse_log(data), before, after)
            except pr.LogParseError as exc:
                extra["parse"] = dict(ok=False, detail=str(exc))
            else:                                            # §4.4 on the DNF item's completed requests too (persisted in the record)
                eng = pr.engagement_problems(report.requests, self.arm)
                extra["engagement"] = dict(ok=not eng, detail="; ".join(eng) or
                                           f"arm {self.arm}; <=1-token requests listed: {pr.short_requests(report.requests)}")
        record = self._item_record(slot, ready, report, res, data, end, before, after, extra)
        try:
            write_exclusive(self._record(slot, "dnf.json"), record)
        except OSError as exc:
            raise ch.HookInfrastructureError(f"DNF item record not written: {exc}") from None
        return (record["problems"] if record["verdict"] != "reconciled" else []), record
