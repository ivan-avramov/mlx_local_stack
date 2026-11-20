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
# S27 X16: the done hook's checks in evaluation order; an infrastructure error names the ones it never reached
DONE_CHECKS = ("preconditions", "ready_checks", "cleanup", "metrics", "settle", "reconciliation", "engagement", "item_record")
DECODE_RATE_SOURCE = "completed requests (spec 8)"        # P593: the worker counts no tokens / decode time for a failed request
CLIENT_STEP_CAP_SOURCE = pr.CLIENT_STEP_CAP_SOURCE


def is_lang(slot, done, lang) -> bool:
    """True when the item of this `done` barrier is a `lang` item: the payload's row id `<lang>/<item>`, else the slot's language
    field."""
    item = (done or {}).get("id") if isinstance(done, dict) else None
    if isinstance(item, str) and "/" in item:
        return item.split("/", 1)[0] == lang
    parts = str(slot).split("|")
    return len(parts) >= 2 and parts[-2] == lang


def _is_go(slot, done) -> bool:
    """True when the item of this `done` barrier is a Go item (tg1's R2 target)."""
    return is_lang(slot, done, "go")


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


def record_name(slot, rindex, suffix) -> str:
    """S27 §5.7: item records are keyed by rerun index — `<slot_file>.<suffix>` for attempt 0, `<slot_file>.r<i>.<suffix>`."""
    return f"{cr.slot_file(slot)}.{suffix}" if not rindex else f"{cr.slot_file(slot)}.r{rindex}.{suffix}"


def row_sha256(row):
    return hashlib.sha256(canonical(row or {})).hexdigest() if row else None


def accounting_path(out_root, slot, rindex) -> Path:
    return Path(out_root) / ITEMS_DIR / record_name(slot, rindex, "accounting.json")


def write_accounting(out_root, slot, rindex, row, item_record, checks, *, not_evaluated=None) -> dict:
    """S27 §5.3: the sealed accounting sidecar `items/<slot>.accounting.json`: slot, the row's sha256 (canonical JSON), the item
    record's self-hash, the failed checks; `not_evaluated` (X16): the done checks a failed hook never reached (the next `ready`
    re-checks). Exclusive-created (FileExistsError when it exists)."""
    doc = dict(slot=slot, rerun_index=int(rindex or 0), row_sha256=row_sha256(row),
               item_record_sha256=(item_record or {}).get("sha256"), failed_checks=list(checks),
               disposition="accounting_fault")
    if not_evaluated is not None:
        doc["not_evaluated"] = list(not_evaluated)
    return write_exclusive(accounting_path(out_root, slot, rindex), doc)


ITEM_RECORD_UNREADABLE = "unreadable"     # S27 Z3: the item record path exists but is not a regular, readable JSON file


def read_item_record(path):
    """S27 Z3 / Z9: the slot attempt's item record at `path` for `accounting_problems`: None when nothing exists at the path,
    the parsed document of a regular file (never followed through a symlink), else `ITEM_RECORD_UNREADABLE`."""
    import stat
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return None
    except OSError:
        return ITEM_RECORD_UNREADABLE
    if not stat.S_ISREG(mode):
        return ITEM_RECORD_UNREADABLE
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return ITEM_RECORD_UNREADABLE


def accounting_problems(doc, slot, rindex, *, row, item_record) -> list:
    """S27 X4 / Y4 / Z3: the ONE accounting-sidecar contract (the chain, freeze and harvest). `doc`: the sidecar (None: absent /
    unreadable); `row`: the slot's committed row (None: not found); `item_record`: what `read_item_record` read for this slot
    attempt (None: no item record exists). The sidecar is sealed, an `accounting_fault` of this slot and rerun index and names
    this row; it names no item record exactly when none exists, else the existing one, which is a regular, self-sealed file.
    -> [] | problems."""
    if not isinstance(doc, dict):
        return ["the accounting sidecar is missing, unreadable or not an object"]
    if not sealed_ok(doc):
        return ["the accounting sidecar's sha256 does not verify"]
    problems = []
    if doc.get("disposition") != "accounting_fault":
        problems.append(f"the accounting sidecar's disposition is {doc.get('disposition')!r}")
    if doc.get("slot") != slot:
        problems.append("the accounting sidecar names another slot")
    if type(doc.get("rerun_index")) is not int or doc["rerun_index"] != int(rindex or 0):
        problems.append("the accounting sidecar names another rerun index")
    want = row_sha256(row) if isinstance(row, dict) else None
    if want is None or doc.get("row_sha256") != want:
        problems.append("the accounting sidecar names another row (or the slot's row is not found)")
    named = doc.get("item_record_sha256")
    if item_record is None:
        if named is not None:
            problems.append("the accounting sidecar names an item record that does not exist")
    elif not (isinstance(item_record, dict) and sealed_ok(item_record)):
        problems.append("the slot attempt's item record exists but is not a regular, self-sealed file")
    elif named is None:
        problems.append("the accounting sidecar names no item record although one exists")
    elif named != item_record["sha256"]:
        problems.append("the accounting sidecar names another item record")
    return problems


def ledger_invocation(chain, entry):
    """Y4: the `progress.invocations` record of a ledger entry's `invocation` (None when not found)."""
    return next((i for i in (chain.get("progress") or {}).get("invocations") or []
                 if isinstance(i, dict) and isinstance(i.get("file"), str) and i["file"] == entry.get("invocation")), None)


def row_for_slot(rows, invocation, slot):
    """Y4: the row of `rows` (one invocation's) whose slot (`slot_base` + id) is `slot`; None when absent / unmatchable."""
    for r in rows:
        try:
            if cr.slot_for(invocation.get("slot_base"), r.get("id")) == slot:
                return r
        except cr.ChainRowsError:
            continue
    return None


def accounting_sealed_for(out_root, slot, rindex, row) -> bool:
    """S27 X4 / Y4 / Z3: True only when the exact sidecar path is a regular file (never a symlink) satisfying
    `accounting_problems` for this slot attempt, its row and its item record (`read_item_record`: the same regular-file
    guard, Z9)."""
    import stat
    path = accounting_path(out_root, slot, rindex)
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return False
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    item = read_item_record(Path(out_root) / ITEMS_DIR / record_name(slot, rindex, "json"))
    return not accounting_problems(doc, slot, rindex, row=row, item_record=item)


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
    def __init__(self, *, ops, out_root, arm, settle_bound_s, clock=time.time, sleep=time.sleep, inject=None, inject_lang="go"):
        self.ops, self.out_root, self.arm = ops, Path(out_root), str(arm)
        self.settle_bound_s, self.clock, self.sleep = float(settle_bound_s), clock, sleep
        self.inject = inject                                # rehearsal only (spec 16.8): `reconcile-mismatch` perturbs the first item
        self.inject_lang = inject_lang                      # ... of this language (tg1: Go; M76 B4b-1 tg2: Rust, from the corpus)
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
    def _record(self, slot, suffix, rindex=0):
        return self.out_root / ITEMS_DIR / record_name(slot, rindex, suffix)

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
        rindex = int(context.get("rerun_index") or 0)
        record = dict(slot=slot, item=context.get("item"), k=context.get("k"), log_cursor=dict(log_stat(path), path=portable_log(path)),
                      worker_snapshot=self._snapshot(), owned=self._owned(context), at=self.clock())
        if rindex:
            record["rerun_index"] = rindex
        try:
            write_exclusive(self._record(slot, "ready.json", rindex), record)
        except OSError as exc:
            raise ch.HookInfrastructureError(f"ready record not written: {exc}") from None
        return ch.Disposition.accept()

    # -- done
    def read_ready(self, slot, rindex=0):
        """The slot's sealed ready record, or None (missing / unreadable / bad self-hash)."""
        try:
            doc = json.loads(self._record(slot, "ready.json", rindex).read_text())
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
        rec = dict(slot=slot, ready_sha256=(ready or {}).get("sha256"),          # §4.5: the ready record's self-hash
                   log_range=dict(start=ready["log_cursor"]["offset"] if ready else None, end=end,
                                  sha256=hashlib.sha256(data).hexdigest()),
                   worker_before=before, worker_after=after, case=case or (report.case if report else None),
                   requests=report.requests if report else [],
                   totals=dict(report.totals if report else {}, decode_rate_source=DECODE_RATE_SOURCE),     # P593
                   checks=checks, verdict="reconciled" if not problems else "invalid", problems=problems)
        if report is not None and report.client_abort is not None:               # P593: the two client-abort cases only
            rec["client_abort"] = report.client_abort
        if report is not None and report.order is not None:                      # S27 §4.2: the order of the kill race
            rec["order"] = report.order
            if report.signal_order is not None:
                rec["signal_order"] = report.signal_order
            if report.late_record is not None:
                rec["late_record"] = report.late_record
        elif report is not None and report.late_record is not None:              # S27 X2: the open-step-at-signal facts
            rec["late_record"] = report.late_record
        if problems:
            rec["fault_class"] = pr.fault_class(checks)                           # S27 §5.9: accounting | integrity
        return rec

    def _client_evidence(self, row, lines, data):
        """P586: the client's side of a `client_inactivity` row (None for any other row): the export read from the row's
        `transcript_path` (resolved like `chain_core.web_record`), its sha256 against `evidence_sha256.export`, and the window's
        telemetry. An unreadable export is a problem (`export=None`, sha not ok), never an exception."""
        if row.get("nonconv_kind") != "client_inactivity":
            return None
        from .chain_ops import resolve_portable
        export, sha_ok = None, False
        tp = row.get("transcript_path")
        try:
            raw = resolve_portable(tp, getattr(self.ops, "wd", None) or ".").read_bytes() if tp else None
            if raw is not None:
                sha_ok = hashlib.sha256(raw).hexdigest() == (row.get("evidence_sha256") or {}).get("export")
                export = json.loads(raw)
        except (OSError, ValueError, TypeError):
            export, sha_ok = None, False
        return pr.client_evidence(export, sha_ok, lines, data)

    def after_attempt(self, slot, done, context=None):
        """Every `done` outcome writes the item record before the barrier answer, an `invalidate` included (spec 4.5)."""
        if context is None:
            raise ch.HookInfrastructureError("after_attempt called without the chain's hook context", not_evaluated=DONE_CHECKS)
        try:
            return self._after_attempt(slot, done, context)
        except ch.HookInfrastructureError as exc:
            if exc.not_evaluated:
                raise
            raise ch.HookInfrastructureError(exc.cause, not_evaluated=DONE_CHECKS[DONE_CHECKS.index(self._at):]) from None

    def _after_attempt(self, slot, done, context):
        self._at = "preconditions"                       # X16: the done check reached when an infrastructure error stops it
        rindex = int(context.get("rerun_index") or 0)
        ready = self.read_ready(slot, rindex)
        pre, res, data, end, extra, report = [], None, b"", None, {}, None
        if ready is None:
            pre.append(f"missing or corrupt ready record for {slot}")
        else:
            pre += self._identity_problems(context)
            res, data, end, wp = self._window(slot, ready)
            pre += wp
        if pre:
            extra["preconditions"] = dict(ok=False, detail="; ".join(pre))
        self._at = "ready_checks"
        held = self._ready_problems()                  # spec 3, `done` row: the `ready` checks (registry, lifecycle, worktree) again
        if held:
            extra["ready_checks"] = dict(ok=False, detail="; ".join(held))
        cs = (context.get("row") or {}).get("cleanup_status")
        if isinstance(cs, dict):
            # S27 §3.6: the item's cleanup receipt is in its row; it must be certain and complete (schema 1 or 2), and its
            # `foreign_new` / killed escapees are recorded here (record only, never a refusal)
            from . import chain_incident as ci
            bad = ci.cleanup_problems(cs)
            extra["cleanup"] = dict(ok=not bad, detail="; ".join(bad) if bad else
                                    f"schema {cs.get('schema', 1)}, foreign_new={cs.get('foreign_new_count', 0)}, "
                                    f"escapees={len(cs.get('orphans_unattributed') or [])}, "
                                    f"unreadable_count={cs.get('unreadable_count', 0)}")
        before, after = (ready or {}).get("worker_snapshot"), self._snapshot_or_none()
        if after is None:
            extra["metrics"] = dict(ok=False, detail="worker /metrics unreadable after the item")
        if res is not None:
            extra["settle"] = dict(ok=res.settled, detail=f"in_flight={res.in_flight} waited_s={res.waited_s:.1f}")
        if not pre and res.settled and after is not None:
            try:
                lines = pr.parse_log(data)
                client = self._client_evidence(context.get("row") or {}, lines, data)
            except pr.LogParseError as exc:
                extra["parse"] = dict(ok=False, detail=str(exc))
            else:
                report = pr.reconcile_item(context.get("row") or {}, lines, before, after, client=client)
                eng = pr.engagement_problems(report.requests, self.arm, item=True)
                extra["engagement"] = dict(ok=not eng, detail="; ".join(eng) or
                                           f"arm {self.arm}; <=1-token requests listed: {pr.short_requests(report.requests)}")
        elif res is not None and not res.settled:
            extra["settle"]["detail"] += " (not settled within the bound)"
        injected = self.inject == "reconcile-mismatch" and self._first_done and is_lang(slot, done, self.inject_lang)
        if injected:
            self._first_done = False
        if injected:                                         # R2 (spec 1 / 16.8, P589): the first Go item's reconciliation is perturbed
            extra["injected"] = dict(ok=False, detail=INJECTED_MISMATCH)
        record = self._item_record(slot, ready, report, res, data, end, before, after, extra)
        self._at = "item_record"
        try:
            sealed = write_exclusive(self._record(slot, "json", rindex), record)
        except OSError as exc:
            raise ch.HookInfrastructureError(f"item record not written: {exc}; verdict {record['verdict']}, failed: "
                                             f"{sorted(n for n, c in record['checks'].items() if not c.get('ok'))}",
                                             not_evaluated=("item_record",)) from None
        if injected:
            return ch.Disposition.invalidate(INJECTED_MISMATCH)
        if record["verdict"] != "reconciled":
            reason = "; ".join(record["problems"])[:600]
            if record.get("fault_class") == "accounting":
                # S27 §5.3 / §5.9: a POST-outcome accounting fault after the §4 order-tolerant cases: the outcome is kept, the
                # sealed sidecar written, no rerun (the chain runs the settle check before `.continue`)
                failed = sorted(n for n, c in record["checks"].items() if not c.get("ok"))
                try:
                    write_accounting(self.out_root, slot, rindex, context.get("row") or {}, sealed, failed)
                except OSError as exc:
                    raise ch.HookInfrastructureError(f"accounting sidecar not written: {exc}",
                                                     not_evaluated=("accounting_sidecar",)) from None
                return ch.Disposition.accounting_fault(reason)
            return ch.Disposition.invalidate(reason)
        return ch.Disposition.accept()

    # -- DNF (spec 4.3 DNF rows, 5.3): used by the chain's DNF eligibility check
    def dnf_problems(self, slot, abort_manifest, rindex=0):
        """Settle, reconcile the DNF window against the abort manifest and write `items/<slot_file>.dnf.json` (keyed by the
        rerun index, S27 §5.7). -> (problems, item_record). A missing ready record or an unsettled window is a problem."""
        ready = self.read_ready(slot, rindex)
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
            write_exclusive(self._record(slot, "dnf.json", rindex), record)
        except OSError as exc:
            raise ch.HookInfrastructureError(f"DNF item record not written: {exc}") from None
        return (record["problems"] if record["verdict"] != "reconciled" else []), record
