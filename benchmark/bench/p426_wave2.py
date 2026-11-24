"""B2 (P426) Wave-2 sequencer (docs/specs/p426-b2-tg1-wave2.md sections 1, 5.5, 6.7, 8, 9, 10, 16.5, 16.6):

  python -m bench.p426_wave2 run      --record-dir D --worktree-off W --worktree-on W --out-base B [--through LEG] [--pause-file F]
  python -m bench.p426_wave2 makeup   --record-dir D --worktree-off W --worktree-on W --out-base B --occurrences FILE
  python -m bench.p426_wave2 rehearsal --manifest M  --worktree-off W --worktree-on W --out-base B

`run` launches legs 1-8 in order (pilot pair, the pilot gate, s1 off/on, s2 on/off, reload on/off) and stops after leg 8; each leg is
ONE `run_tg1_chain.py --p426` invocation from its arm's worktree on a fresh out-root `<out-base>/<leg>.a<n>`. The sequencer owns
`SEQUENCER.lock` for the whole sequence (never `LEG.lock`; each chain takes its own), writes `LAST_LEG_END` when a leg ends and waits
600 s before the next, supervises the chain and its watcher without ever killing either, writes `OVERRUN_PAUSED` at the leg's
deadline, classifies and harvests every leg (any state), writes one immutable pair dossier per pair attempt and publishes it. A
systemic failure stops the sequence; a rerun is the operator's decision (`--rerun LEG --rerun-reason TEXT`: a new attempt on a fresh
out-root). `<out-base>/sequence.json` is the state file: resume = the same command. `ops` supplies everything that touches the box:
`launch`, `alive`, `wait`, `power`, `harvest`, `harvest_path`, `publish_dossier`, `publish_run_files`, `operator_emails`, and
(delegated to `bench.p426_freeze`) `worktree_state`, `identity`, `historical_walls`. Process identity is the start time the ops report
(`ChainOps.create_time`, C151)."""
from __future__ import annotations

import argparse
import datetime
import getpass
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from types import SimpleNamespace

from . import chain_ops as co
from . import datefreeze
from . import p426_freeze as fz
from . import p426_hooks as ph
from . import p426_ids
from . import p426_locks as pl
from . import p426_receipt as pr
from . import p426_record

ENTRY = p426_ids.ENTRY
POLL_S = 30.0                                        # the supervision tick: chain, watcher and deadline
WATCH_INTERVAL_S = 300.0                             # the watcher's own interval (spec 8)
WATCHER_GRACE_S = 3 * WATCH_INTERVAL_S               # how long after the chain's exit a watcher may take to finalize
REHEARSAL_DEADLINE_S = 6 * 3600.0                    # rehearsal legs are not in a frozen record: a generous fixed supervision bound
POWER = dict(watts=140, volts=28, battery_above=20)  # spec 8 / AGENTS: checked before a launch (the chain checks it again at entry)
VALID_STATES = ("VALID", "VALID_WITH_DNF")
MAX_DNF = 2                                          # spec 5.1: more than 2 DNF in a leg is systemic
MAX_HARNESS_DNF = 3                                  # S27 §5.6: harness_fault_dnf + grade_fault DNFs per leg
SESSIONS = ("s1", "s2", "reload", "pilot", "makeup")
KV_SESSIONS = SESSIONS + ("s3",)                     # M76 (lever kv): tg1 session s3 (seed 3003), erratum v1.2
SESSION_ORDER = ("s1", "s2")
LANG_ORDER = {"s1": ("python", "go"), "s2": ("go", "python")}      # spec 7: s2 reverses the language order
SESSION_SEED = {"s1": 1001, "s2": 2002}
OVERRUN_FILE, SEQUENCE_FILE, LOG_FILE = "OVERRUN_PAUSED", "sequence.json", "sequence.log"
HOST_ENV_FILE = "host_env.json"                      # C360 / S26 §2: the run's host-environment baseline (`bench.host_env`)
HOST_ENV_REASON = "host environment changed during the leg"      # the C360 reason (S29 H5 reads it; C384 never writes it)
C384_SUPERSEDED = "leg.c360.json"                    # S29 H5: a C360 host-INVALID leg.json, kept byte-identical beside its successor
C384_BEFORE_BASIS = "C360 refused a launch on any difference from the run baseline"
WAVE2_DIR, REHEARSAL_DIR = "p426/wave2", "p426/rehearsal"
CHAIN_ENTRY = ("benchmark", "chains", "c147", "run_tg1_chain.py")          # in parts: this module reads no chain rows (test_p371_chain_rows)
SEAMS = ("launch", "alive", "wait", "power", "harvest", "harvest_path", "publish_dossier", "publish_run_files", "operator_emails",
         "worktree_state", "identity")                 # `notify` is optional; `historical_walls` is needed by `run` only (the amendment)


def c360_changes(reason) -> list:
    """S29 H5: the host changes a C360 reason `host environment changed during the leg: <c1>; <c2>…` names (no `(prior: …)`)."""
    return str(reason)[len(HOST_ENV_REASON) + 2:].split("; ")


def kept_temp(kept) -> Path:
    """The same-directory temporary file `install_kept` writes before installing `kept`."""
    kept = Path(kept)
    return kept.with_name(f".{kept.name}.tmp")


def install_kept(kept, data):
    """S29 H5: install `data` at `kept` atomically and without replacement: a fsynced same-directory temp file, an exclusive hard
    link to the final path (FileExistsError when one exists; the caller compares it), the temp removed, the directory fsynced.
    A crash leaves the final path absent or complete, never partial."""
    kept = Path(kept)
    tmp = kept_temp(kept)
    if os.path.lexists(tmp):                           # a crash before the link left it: ours, never at the final path
        os.unlink(tmp)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.link(tmp, kept)
    except FileExistsError:
        pass                                           # an existing file is compared by the caller, never replaced
    os.unlink(tmp)
    dfd = os.open(kept.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


class Stop(Exception):
    """The sequence stops here with exit code `rc` (1 a leg / gate / pair / drift, 3 an overrun, 4 a harvest); the reason is logged."""

    def __init__(self, rc, message):
        super().__init__(message)
        self.rc = rc


# ----------------------------------------------------------------------------------------------- the leg table (spec 1)
def _leg(n, name, arm, head, kind, pair=None, role=None, record="amendment", extra=(), expect="VALID"):
    """A leg's plan (how many slots it realizes) is never kept here: it is read from the leg's own frozen schedule (spec 16.8)."""
    return dict(n=n, name=name, arm=arm, head=list(head), kind=kind, pair=pair, role=role, record=record, extra=list(extra), expect=expect)


RUN_LEGS = (
    _leg(1, "tg1-p426-off-pilot", "off", ["pilot"], "pilot", "pilot", "first", "v8"),
    _leg(2, "tg1-p426-on-pilot", "on", ["pilot"], "pilot", "pilot", "second", "v8"),
    _leg(3, "tg1-p426-off-s1", "off", ["chain", "s1"], "s1", "s1", "first"),
    _leg(4, "tg1-p426-on-s1", "on", ["chain", "s1"], "s1", "s1", "second"),
    _leg(5, "tg1-p426-on-s2", "on", ["chain", "s2"], "s2", "s2", "first"),
    _leg(6, "tg1-p426-off-s2", "off", ["chain", "s2"], "s2", "s2", "second"),
    _leg(7, "tg1-p426-on-reload", "on", ["chain", "reload"], "reload", "reload", "first"),
    _leg(8, "tg1-p426-off-reload", "off", ["chain", "reload"], "reload", "reload", "second"),
)
MAKEUP_LEGS = (
    _leg(9, "tg1-p426-off-makeup", "off", ["makeup"], "makeup", "makeup", "first"),
    _leg(10, "tg1-p426-on-makeup", "on", ["makeup"], "makeup", "makeup", "second"),
)
REHEARSAL_LEGS = (
    _leg("R1", "tg1-p426-rehearsal-off", "off", ["chain", "s1"], "rehearsal", "r1", "first", "manifest", extra=["--rehearsal"]),
    _leg("R1", "tg1-p426-rehearsal-on", "on", ["chain", "s1"], "rehearsal", "r1", "second", "manifest", extra=["--rehearsal"]),
    _leg("R2", "tg1-p426-rehearsal-mismatch", "on", ["chain", "s1"], "rehearsal", record="manifest",
         extra=["--rehearsal", "--inject", "reconcile-mismatch"], expect="INVALID"),
    _leg("R3", "tg1-p426-rehearsal-kill", "off", ["chain", "s1"], "rehearsal", record="manifest",
         extra=["--rehearsal", "--inject", "stall-kill"]),
)
BY_NAME = {leg["name"]: leg for leg in (*RUN_LEGS, *MAKEUP_LEGS, *REHEARSAL_LEGS)}
PREDICTOR = {"off": "off", "on": "mtp"}
KV_WAVE2_DIR, KV_REHEARSAL_DIR = "m76/p426/wave2", "m76/p426/rehearsal"     # M76 B3: the KV lever's scratch


def predictor_of(lever, arm):
    """The chain's `--predictor` of an arm: P426 OFF / ON, or `mtp` for every M76 KV arm (both MTP ON)."""
    return "mtp" if lever == "kv" else PREDICTOR[arm]


def kv_a7_sessions(report=None):
    """The paired tg1 sessions of A7's final look (`p426_plan.kv_a7_sessions`, from B7's committed plan; erratum v1.2); refused
    when B7's plan is absent or names another count."""
    from . import p426_plan

    try:
        return p426_plan.kv_a7_sessions(report)
    except ValueError as exc:
        raise fz.Refusal(f"A7's plan (bench.m76_rule.axis_plan): {exc}") from None


def kv_legs(ref, test, sessions=None):
    """M76 B3: the leg table of a KV pair (reference, treatment) — P426's with OFF / ON replaced by the two arms, every name
    `tg1-m76-…`. The paired sessions are A7's plan (`kv_a7_sessions`; erratum v1.2: s1, s2, s3) alternating the first arm
    (s1 ref → test, s2 test → ref, s3 ref → test), then the reload control (test → ref) and the make-up pair."""
    from . import p426_plan

    p426_plan.check_kv_pair(ref, test)
    sessions = tuple(sessions) if sessions is not None else kv_a7_sessions()
    if sessions not in (("s1", "s2"), ("s1", "s2", "s3")):
        raise ValueError(f"A7 sessions {sessions} are not s1, s2[, s3]")

    def n(arm, s):
        return f"tg1-m76-{arm}-{s}"
    run = [_leg(1, n(ref, "pilot"), ref, ["pilot"], "pilot", "pilot", "first", "v8"),
           _leg(2, n(test, "pilot"), test, ["pilot"], "pilot", "pilot", "second", "v8")]
    for i, s in enumerate(sessions):
        first, second = (ref, test) if i % 2 == 0 else (test, ref)
        run += [_leg(len(run) + 1, n(first, s), first, ["chain", s], s, s, "first"),
                _leg(len(run) + 2, n(second, s), second, ["chain", s], s, s, "second")]
    run += [_leg(len(run) + 1, n(test, "reload"), test, ["chain", "reload"], "reload", "reload", "first"),
            _leg(len(run) + 2, n(ref, "reload"), ref, ["chain", "reload"], "reload", "reload", "second")]
    run = tuple(run)
    makeup = (_leg(len(run) + 1, n(ref, "makeup"), ref, ["makeup"], "makeup", "makeup", "first"),
              _leg(len(run) + 2, n(test, "makeup"), test, ["makeup"], "makeup", "makeup", "second"))
    rehearsal = (_leg("R1", f"tg1-m76-rehearsal-{ref}", ref, ["chain", "s1"], "rehearsal", "r1", "first", "manifest",
                      extra=["--rehearsal"]),
                 _leg("R1", f"tg1-m76-rehearsal-{test}", test, ["chain", "s1"], "rehearsal", "r1", "second", "manifest",
                      extra=["--rehearsal"]),
                 _leg("R2", "tg1-m76-rehearsal-mismatch", test, ["chain", "s1"], "rehearsal", record="manifest",
                      extra=["--rehearsal", "--inject", "reconcile-mismatch"], expect="INVALID"),
                 _leg("R3", "tg1-m76-rehearsal-kill", ref, ["chain", "s1"], "rehearsal", record="manifest",
                      extra=["--rehearsal", "--inject", "stall-kill"]))
    return dict(run=run, makeup=makeup, rehearsal=rehearsal)


TG2_LANGS = ("rust", "javascript", "java", "cpp")
TG2_CHAIN_ENTRY = ("benchmark", "chains", "c147", "run_tg2_chain.py")
TG2_NAMESPACE = "wave2.tg2"                              # benchmark/results/m76/wave2.tg2/
TG2_SESSION_SEED = 1001                                  # the positives' seed (the pilot item at s1's seed)
RECHECK_GATES = {"s1": ("s1",), "s2": ("s1", "s2")}       # the two nuisance re-checks and the sessions each pools
POSITIVE_TIMEOUT_S = 2 * 3660.0                          # one inject probe run: twice one P223 maximum item (never retried on time)
POSITIVE_SEAMS = ("worktree_state", "identity", "positives_session", "positive_grade", "positive_inject", "inject_verify")


def positives_plan(draw_doc):
    """{lang: item}: per tg2 language the pilot item (the draw's first; the pins verified)."""
    from . import schedules
    sched = schedules.tg2_p426(draw_doc, "pilot", ENTRY, "mtp")
    return {lg["lang"]: lg["invocations"][0]["expect"][0] for lg in sched["blocks"][0]["legs"]}


def _inject_verify_module():
    """`benchmark/m62/inject_verify.py` (stdlib-only at import), for its evidence-path rules and event reader."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        from m62 import inject_verify
    finally:
        sys.path.pop(0)
    return inject_verify


def _input_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _input_strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _input_strings(v)


def _row_file(run, kind, attempt):
    return Path(run) / (f"{kind}.attempt{attempt}" + ".jsonl")


def verified_row(run, kind, attempt, row_sha256):
    """`(row, None)` when the run's `<kind>.attempt<n>.jsonl` holds one row and hashes to the recorded `row_sha256` (S26
    erratum 1, Sol P17); else `(None, why)`."""
    if not (isinstance(row_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", row_sha256)):
        return None, "the inject run recorded no row_sha256"
    try:
        raw = _row_file(run, kind, attempt).read_bytes()
    except OSError:
        return None, "the run's row file is missing or unreadable"
    if hashlib.sha256(raw).hexdigest() != row_sha256:
        return None, "the run's row file is not the one the inject run recorded (row_sha256)"
    try:
        rows = [json.loads(x) for x in raw.decode().splitlines() if x.strip()]
    except (ValueError, UnicodeDecodeError):
        return None, "the run's row file is unreadable"
    if len(rows) != 1 or not isinstance(rows[0], dict):
        return None, "the run has no single row"
    return rows[0], None


def recorded_kills(row) -> int:
    """The kills the row records: its `mem_kills` plus the processes its termination killed (`termination.killed`); -1 when
    either record is missing or malformed (never 0 without the facts)."""
    term = row.get("termination")
    if not isinstance(term, dict):
        return -1
    n = 0
    for value in (row.get("mem_kills"), term.get("killed")):
        if not isinstance(value, list):
            return -1
        n += len(value)
    return n


def decline_evidence(run, kind, attempt, verify_verdict, wd, row_sha256=None, probe_rc=None):
    """S26 §4 + erratum 1: `(declined_evidence, None)` when the model declined the planted command of `kind` (loop / alloc
    only): the inject_verify verdict is `not_observed*` (`fz.declinable_verify_verdict`), the probe exited rc 0, the run's
    row is the one recorded (`row_sha256`), the row records no kill, its recorded artifacts verify against the row's
    `evidence_sha256` (inject_verify's V3 rule), and its events hold no tool call whose input carries the kind's marker.
    Else `(None, why)`."""
    marker = fz.DECLINE_MARKERS.get(kind)
    if marker is None:
        return None, f"{kind} is never declined"
    if not fz.declinable_verify_verdict(verify_verdict):
        return None, f"the inject_verify verdict {verify_verdict!r} is not a decline"
    if type(probe_rc) is not int or probe_rc != 0:
        return None, f"the probe did not exit rc 0 (rc {probe_rc!r})"
    row, why = verified_row(run, kind, attempt, row_sha256)
    if row is None:
        return None, why
    kills = recorded_kills(row)
    if kills != 0:
        return None, "the row records a kill" if kills > 0 else "the row's kill records are malformed"
    iv = _inject_verify_module()
    shas, paths = row.get("evidence_sha256"), iv.evidence_paths(row, "opencode-v2-web-tg2")
    if not isinstance(shas, dict) or paths is None or set(shas) != set(paths):
        return None, "the row's evidence_sha256 does not name exactly its recorded artifacts"
    for name, field in paths.items():
        p = iv.resolve(row.get(field, ""), wd)
        try:
            ok = bool(shas[name]) and p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == shas[name]
        except OSError:
            ok = False
        if not ok:
            return None, f"the recorded artifact {name} does not verify against evidence_sha256"
    try:
        events = iv.load_events(iv.resolve(row.get("events_path", ""), wd))
    except (OSError, ValueError):
        return None, "the events file is unreadable"
    for e in events:
        part = e.get("part") if isinstance(e, dict) else None
        state = part.get("state") if isinstance(part, dict) else None
        if isinstance(state, dict) and "input" in state:
            if any(marker in s for s in _input_strings(state["input"])) or marker in json.dumps(state["input"]):
                return None, f"a tool call carries {marker!r} (the model ran it)"
    return dict(events_sha256=shas["events"], marker=marker, verify_verdict=verify_verdict, kills=0, probe_rc=0,
                row_sha256=row_sha256), None


def _verify(ops, run, kind):
    """{verdict, result}: the retained attempt's inject_verify verdict string (erratum 3) and, when the ops expose the richer
    `inject_verify_result`, its RESULT line (one inject_verify call either way)."""
    full = getattr(ops, "inject_verify_result", None)
    if callable(full):
        r = dict(full(run, kind))
        return dict(verdict=r.get("verdict"), result=r.get("result"))
    return dict(verdict=ops.inject_verify(run, kind), result=None)


def parse_inject_verify(stdout, kind):
    """(retained attempt's verdict, RESULT line) from `inject_verify --kind <kind>`'s stdout: the attempt lines are
    `<kind>.attempt<n>: <verdict>` (earlier attempts carry the retry tag); a missing attempt prints `<kind>: FAIL:missing …`."""
    row, result = None, None
    for line in (stdout or "").splitlines():
        line = line.rstrip()
        m = re.fullmatch(rf"{re.escape(kind)}(?:\.attempt\d+)?: (\S.*)", line)
        if m and "[retry" not in m.group(1) and not m.group(1).startswith(" "):
            row = m.group(1).split(" ", 1)[0]
        elif line.startswith("RESULT"):
            result = line
    return row, result


# C366 (S27-P6): the reference record the in-flight link transfers from (its sha is v8's constant), as committed on `main`
TRANSFER_REFERENCE = dict(path="$STACK_REPO/benchmark/results/m76/tg2/positives-20261117/positives.json",
                          sha256=fz.TRANSFER_REFERENCE_SHA256,
                          commit="c7c6993ad6556c77804c21120933c2d3fd2d44d2")


def worktree_cancel_path_sha256(worktree):
    """C366: the arm worktree's stop-path digest (`fz.worktree_cancel_path_sha256`; a seam for tests)."""
    return fz.worktree_cancel_path_sha256(worktree)


def _transfer_reference(wd, lang):
    """`(reference stall entry, None)` from the sealed C366 reference record, else `(None, why)`."""
    from . import paths
    path = Path(TRANSFER_REFERENCE["path"].replace("$STACK_WORKDIR", str(wd)).replace("$STACK_REPO", str(paths.repo_root())))
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        return None, "the transfer reference record is missing or unreadable"
    if not ph.sealed_ok(doc) or doc.get("sha256") != TRANSFER_REFERENCE["sha256"]:
        return None, "the transfer reference record is not the sealed C366 reference"
    found = [e for e in doc.get("injects") or [] if isinstance(e, dict) and e.get("language") == lang and e.get("kind") == "stall"]
    if len(found) != 1 or found[0].get("verdict") != "PASS" or \
            found[0].get("row_sha256") != fz.TRANSFER_REFERENCE_STALL_ROWS.get(lang):
        return None, f"the transfer reference holds no {lang} stall PASS with the reference's row"
    return found[0], None


def transfer_evidence(run, kind, attempt, verify_verdict, wd, lang, *, row_sha256=None, probe_rc=None, cancel_path_sha256=None):
    """C366 (a): `(transfer_evidence, None)` when a stall / loop stop fired and its client kill verified with NO request in flight
    (the only unexercised link is the in-flight interrupt / cancellation), the probe exited rc 0, the row is the one recorded, the
    arm's stop path is source-identical to the reference commit's, and the reference record holds this language's stall PASS.
    Else `(None, why)`."""
    want = fz.TRANSFER_KINDS.get(kind)
    if want is None:
        return None, f"{kind} is never transferred"
    if verify_verdict != want[0]:
        return None, f"the inject_verify verdict {verify_verdict!r} is not the in-flight link ({want[0]})"
    if type(probe_rc) is not int or probe_rc != 0:
        return None, f"the probe did not exit rc 0 (rc {probe_rc!r})"
    if cancel_path_sha256 != fz.CANCEL_PATH_SHA256:
        return None, "the arm's stop path differs from the reference commit's (a fresh in-run proof is needed)"
    row, why = verified_row(run, kind, attempt, row_sha256)
    if row is None:
        return None, why
    gate, term = row.get("gate") or {}, row.get("termination")
    if not isinstance(term, dict) or gate.get("stop_reason") != want[1] or term.get("reason") != want[1]:
        return None, f"the {want[1]} stop did not fire"
    if not any(isinstance(k, dict) and k.get("role") == "client" for k in term.get("killed") or []):
        return None, "the row records no client kill"
    if term.get("killed_verified") is not True:
        return None, "the client kill is not verified"
    before = term.get("worker_summary_before")
    if type(term.get("in_flight_at_kill")) is not int or term["in_flight_at_kill"] != 0 or not isinstance(before, dict) \
            or before.get("in_flight") != 0:
        return None, "a request was in flight at the kill (the link is exercised in-run)"
    ref, why = _transfer_reference(wd, lang)
    if ref is None:
        return None, why
    return dict(verify_verdict=verify_verdict, stop_reason=want[1], in_flight_at_kill=0, killed_verified=True, probe_rc=0,
                row_sha256=row_sha256, trailing=(row.get("reconciliation") or {}).get("trailing"),
                reference_sha256=TRANSFER_REFERENCE["sha256"], reference_commit=TRANSFER_REFERENCE["commit"],
                reference_row_sha256=ref["row_sha256"], cancel_path_sha256=cancel_path_sha256), None


def waiver_evidence(run, kind, attempt, verify_verdict, wd, *, row_sha256=None, probe_rc=None, manifest_sha256=None):
    """C366 (b): `(waived_evidence, None)` when the alloc run's one kill is a model-role process that is not the planted command,
    over the inject's per-process limit, no tool call carries the marker, the artifacts verify, probe rc 0. Else `(None, why)`."""
    if kind != "alloc" or verify_verdict != fz.WAIVED_VERIFY_VERDICT:
        return None, f"{kind} {verify_verdict!r} is never waived"
    if type(probe_rc) is not int or probe_rc != 0:
        return None, f"the probe did not exit rc 0 (rc {probe_rc!r})"
    row, why = verified_row(run, kind, attempt, row_sha256)
    if row is None:
        return None, why
    marker = fz.DECLINE_MARKERS["alloc"]
    kills = row.get("mem_kills")
    if not isinstance(kills, list) or len(kills) != 1 or not isinstance(kills[0], dict):
        return None, "the row records not exactly one memory kill"
    kill = kills[0]
    argv = kill.get("argv")
    if kill.get("role") != "model" or not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        return None, "the kill is not a model-role process with a recorded argv"
    if any(marker in a for a in argv):
        return None, "the killed process is the planted command"
    try:                                     # C366 r1 P3: the manifest the probe recorded (its sha), never an edited copy
        raw = Path(str(_row_file(run, kind, attempt))[:-len(".jsonl")] + ".manifest.json").read_bytes()
    except OSError:
        return None, "the run's manifest is missing or unreadable"
    if not (isinstance(manifest_sha256, str) and hashlib.sha256(raw).hexdigest() == manifest_sha256):
        return None, "the run's manifest is not the one the inject run recorded (evidence_sha256)"
    try:
        per_process = json.loads(raw)["runtime"]["inject"]["policy"]["hygiene"]["per_process"]
    except (ValueError, KeyError, TypeError):
        return None, "the run's manifest records no inject per-process limit"
    rss = kill.get("rss")
    if type(rss) is not int or type(per_process) is not int or per_process <= 0 or rss <= per_process:
        return None, "the kill is not over the inject's per-process limit"
    iv = _inject_verify_module()
    shas, paths = row.get("evidence_sha256"), iv.evidence_paths(row, "opencode-v2-web-tg2")
    if not isinstance(shas, dict) or paths is None or set(shas) != set(paths):
        return None, "the row's evidence_sha256 does not name exactly its recorded artifacts"
    for name, field in paths.items():
        f = iv.resolve(row.get(field, ""), wd)
        try:
            ok = bool(shas[name]) and f.is_file() and hashlib.sha256(f.read_bytes()).hexdigest() == shas[name]
        except OSError:
            ok = False
        if not ok:
            return None, f"the recorded artifact {name} does not verify against evidence_sha256"
    try:
        events = iv.load_events(iv.resolve(row.get("events_path", ""), wd))
    except (OSError, ValueError):
        return None, "the events file is unreadable"
    for e in events:
        part = e.get("part") if isinstance(e, dict) else None
        state = part.get("state") if isinstance(part, dict) else None
        if isinstance(state, dict) and "input" in state:
            if any(marker in x for x in _input_strings(state["input"])) or marker in json.dumps(state["input"]):
                return None, f"a tool call carries {marker!r}"
    return dict(verify_verdict=verify_verdict, killed_role="model", killed_argv0=Path(argv[0]).name, marker_in_argv=False,
                marker_in_tool_calls=False, rss=rss, per_process=per_process, probe_rc=0, events_sha256=shas["events"],
                manifest_sha256=manifest_sha256, row_sha256=row_sha256), None


def positive_entry(ops, wd, lang, item, kind, *, cancel_path_sha256=None, runs=None):
    """One inject positive (§4): the run (one retry, only on a transport abort), its inject_verify verdict, and the entry's
    `verdict` — `PASS`, `DECLINED` (loop / alloc, with `declined_evidence`) or the failure. Returns (entry, why-not-declined).
    `runs` (S29 acceptance 6): a list the retained run is appended to as (entry, run dir, attempt)."""
    verdict, res, n, ver = None, {}, 0, None
    for n in (1, 2):                                    # one retry per run, only on a transport abort
        res = dict(ops.positive_inject(lang, item, kind, seed=TG2_SESSION_SEED, attempt=n))
        if res.get("transport_abort"):
            verdict = "TRANSPORT_ABORT"
            continue
        ver = _verify(ops, res["run"], kind)
        verdict = ver["verdict"]
        break
    entry = dict(language=lang, kind=kind, item=item, seed=TG2_SESSION_SEED, attempts=n, verdict=verdict,
                 row_sha256=res.get("row_sha256"), evidence_sha256=res.get("evidence_sha256"))
    if runs is not None and ver is not None:
        runs.append((entry, res["run"], n))
    why = None
    if ver is not None:
        entry.update(verify_verdict=ver["verdict"], verify_result=ver["result"], probe_rc=res.get("rc"))
        rc = res.get("rc")
        if rc is not None and (type(rc) is not int or rc != 0):
            # Sol P17: a nonzero probe exit is a probe failure, never PASS / DECLINED (the verify verdict stays recorded)
            entry["verdict"] = f"FAIL:probe_rc:{rc}"
        elif verdict == "PASS" or (verdict == fz.PASS_NO_INFLIGHT and kind in fz.NO_INFLIGHT_KINDS):    # S27 §4.3
            # X12: a PASS row always exists (inject_verify read it); a missing or changed row fails the entry (any kind)
            _, bad = verified_row(res["run"], kind, n, res.get("row_sha256"))
            if bad:
                entry["verdict"], why = "FAIL:row_sha256", bad
        else:
            if kind in fz.DECLINE_MARKERS:
                evidence, why = decline_evidence(res["run"], kind, n, verdict, wd, row_sha256=res.get("row_sha256"),
                                                 probe_rc=rc)
                if evidence is not None:
                    entry.update(verdict="DECLINED", declined_evidence=evidence)
            if entry["verdict"] == verdict and kind in fz.TRANSFER_KINDS:          # C366 (a)
                evidence, why_t = transfer_evidence(res["run"], kind, n, verdict, wd, lang, row_sha256=res.get("row_sha256"),
                                                    probe_rc=rc, cancel_path_sha256=cancel_path_sha256)
                if evidence is not None:
                    entry.update(verdict="PASS_BY_TRANSFER", transfer_evidence=evidence)
                    why = None
                else:
                    why = why_t if why is None else f"{why}; {why_t}"
            if entry["verdict"] == verdict and kind == "alloc":                    # C366 (b)
                evidence, why_w = waiver_evidence(res["run"], kind, n, verdict, wd, row_sha256=res.get("row_sha256"),
                                                  probe_rc=rc, manifest_sha256=res.get("evidence_sha256"))
                if evidence is not None:
                    entry.update(verdict="WAIVED", waived_evidence=evidence)
                    why = None
                elif verdict == fz.WAIVED_VERIFY_VERDICT:
                    why = why_w if why is None else f"{why}; {why_w}"
    return entry, why


def testable_record(worktree, wd, runs):
    """S29 acceptance 6 (recorded, never a problem): `lookup` — every lookup probe of every deny class decided on the worktree's
    tg2 carrier by opencode's matcher (`tg2_testable.lookup_record`); `full_suite` — per tg2 language, whether the agent ran the
    language's full-suite command, read from the events of that language's positives sessions (each run's recorded row,
    verified by its `row_sha256`). `runs` = [(entry, run dir, attempt)] in run order."""
    from . import host_env as he
    from . import tg2_materialize as mat
    from . import tg2_testable as tt
    try:
        perms = tt.load_permissions(Path(worktree) / "benchmark/opencode_bench_v2_web_tg2.json")
        lookup = tt.lookup_record(perms)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        perms, lookup = [], dict(error=f"{type(exc).__name__}: {str(exc)[:200]}", all_denied=False, local_allowed=False)
    iv = _inject_verify_module()
    full = {}
    for lang in TG2_LANGS:
        calls, sources, ran = [], [], False
        for entry, run, attempt in runs:
            if entry.get("language") != lang:
                continue
            row, why = verified_row(run, entry.get("kind"), attempt, entry.get("row_sha256"))
            if row is None:
                sources.append(dict(kind=entry.get("kind"), read=False, why=why))
                continue
            try:
                events = iv.load_events(iv.resolve(row.get("events_path", ""), wd))
            except (OSError, ValueError):
                sources.append(dict(kind=entry.get("kind"), read=False, why="the events file is unreadable"))
                continue
            rec = tt.full_suite_record(events, lang, perms)
            sources.append(dict(kind=entry.get("kind"), read=True, calls=len(rec["calls"])))
            calls += [dict(c, command=he.portable(str(c["command"]).replace(str(wd), "$STACK_WORKDIR")), kind=entry.get("kind"))
                      for c in rec["calls"]]
            ran = ran or rec["ran"]
        full[lang] = dict(ran=ran, calls=calls, sources=sources, denied=sum(c["decision"] == "deny" for c in calls))
    return dict(version=mat.TESTABLE_VERSION, lookup=lookup, full_suite=full)


def cmd_positives(a, ops, wd, clock=time.time):
    """§3 "Positives record" (E6): per language the pilot item's stub graded FAIL and its reference PASS (`Tg2Corpus.grade`); on
    the reference arm, stall / loop / alloc on the pilot item at seed 1001 (12 `run_tg2_probe.py --tg2-inject` runs), each
    verified by `inject_verify` with that kind's causal predicate, one retry per run only on a transport abort; inside ONE serving
    session (the lean router, the A4 gate, the worker loaded). S26 §4: stall must PASS; loop / alloc PASS or are DECLINED by the
    model (`decline_evidence`). C384 (S29 H4): the host fingerprint before the first grade and after the last inject are recorded
    with their diff (`host_env_changes`), never a problem; an exception inside is recorded. Writes one sealed record (any
    outcome); rc 0 only when all pass."""
    from . import host_env as he
    from . import schedules
    from . import tg2_grade
    fz.need(ops, *POSITIVE_SEAMS)
    (arm, worktree), = a.worktrees.items()
    out = Path(a.out)
    if out.exists():
        raise fz.Refusal(f"--out {out.name} exists (the positives record is exclusive-created, never overwritten)")
    try:
        draw = json.loads((Path(__file__).resolve().parents[1] / "m65" / "tg2_draw.json").read_text())
        plan = positives_plan(draw)
    except (OSError, ValueError, schedules.TransportAbort) as exc:
        raise fz.Refusal(f"the tg2 draw: {exc}") from None
    st, ident = ops.worktree_state(worktree), ops.identity(worktree)
    if st.get("clean") is not True:
        raise fz.Refusal(f"the {arm} worktree is not clean")
    problems, grades, injects, runs = [], [], [], []
    cancel_sha = worktree_cancel_path_sha256(worktree)                         # C366 (a): recorded in each transfer
    probe = getattr(ops, "host_env", None)
    probe = probe if callable(probe) else None
    env0 = json.loads(json.dumps(probe())) if probe else None      # C360: before the first grade
    env1 = None
    try:
        for lang in TG2_LANGS:
            for variant in fz.POSITIVE_VARIANTS:
                g = dict(ops.positive_grade(lang, plan[lang], variant))
                grades.append(dict(language=lang, item=plan[lang], variant=variant, **g))
                if g.get("passed") is not (variant == "reference"):
                    problems.append(f"{lang} {variant}: graded {'PASS' if g.get('passed') else 'FAIL'}, expected "
                                    f"{'PASS' if variant == 'reference' else 'FAIL'}")
        with ops.positives_session(worktree, frozen_prompt_date=a.frozen_prompt_date):
            # S27 §4.5 (C373): FIRST the deterministic interrupt positive on the pilot item (of the first tg2 language): the
            # harness stops it while the worker reports a generation in flight; the record is PASS only with its in-flight PASS
            lang0 = TG2_LANGS[0]
            entry, why = positive_entry(ops, wd, lang0, plan[lang0], fz.INTERRUPT_KIND, runs=runs)
            if why:
                entry["not_declined"] = he.portable(why)
            injects.append(entry)
            if not fz.inject_accepted(entry):
                problems.append(f"{lang0} {fz.INTERRUPT_KIND}: {entry['verdict']}")
            for lang in TG2_LANGS:
                for kind in fz.POSITIVE_KINDS:
                    entry, why = positive_entry(ops, wd, lang, plan[lang], kind, cancel_path_sha256=cancel_sha, runs=runs)
                    if why:
                        entry["not_declined"] = he.portable(why)        # why the run is not PASS / DECLINED (diagnostic)
                    injects.append(entry)
                    if not fz.inject_accepted(entry):
                        problems.append(f"{lang} {kind}: {entry['verdict']}")
            problems += fz.waiver_problems(injects)                               # C366 (b)
    except Exception as exc:  # noqa: BLE001  (S26 §2: recorded, the run continues to its sealed record)
        problems.append(he.portable(f"exception: {type(exc).__name__}: {str(exc)[:300]}"))
    finally:
        env1 = json.loads(json.dumps(probe())) if probe else None  # also when no session opened
    try:
        testable = testable_record(worktree, wd, runs)                # S29 acceptance 6: recorded, never a problem
    except Exception as exc:  # noqa: BLE001  (a record of the failure, the positives' verdict stays their own)
        testable = dict(error=he.portable(f"{type(exc).__name__}: {str(exc)[:300]}"))
    host_changes = he.diff(env0, env1) if env0 is not None else []          # C384: recorded, never a problem
    if host_changes:
        print("host environment changed during the positives: " + "; ".join(host_changes), flush=True)
    doc = dict(kind=fz.KIND_POSITIVES, corpus="tg2", arm=arm, **{f"{arm}_commit": st.get("head")},
               scaffold="opencode-v2-web-tg2", **{k: ident.get(k) for k in fz.IDENTITY_KEYS},
               draw_sha256=schedules.TG2_DRAW_SHA256, universe_sha256=schedules.TG2_UNIVERSE_SHA256,
               image_id=tg2_grade.pinned_image_id(), frozen_prompt_date=a.frozen_prompt_date, grades=grades, injects=injects,
               proofs={f"{e.get('language')}/{e.get('kind')}": fz.proof_of(e) for e in injects},      # S27 §4.5
               testable=testable,
               problems=problems, host_env=env0, host_env_after=env1, host_env_changes=host_changes, verdict="PASS" if not problems else "FAIL",
               created=co.utc_stamp(clock()))
    try:
        sealed = ph.write_exclusive(out, doc)
    except FileExistsError:
        raise fz.Refusal(f"--out {out.name} exists (exclusive-created)") from None
    print(f"{fz.KIND_POSITIVES} {sealed['verdict']} {sealed['sha256']}")
    return 0 if not problems else 1


def kv_tg2_legs(ref, test):
    """M76 B4b-1 (§3, order per pair): the tg2 legs of a KV pair (reference, treatment), every name `tg2-m76-<arm>-<leg>`: the
    pilot pair (v8 base; ref -> test), s1 (ref -> test), s2 (test -> ref), the reload (test -> ref), and the rehearsals R2 on the
    treatment (INVALID expected) and R3 on the reference. Each leg is one `run_tg2_chain.py` invocation (`--leg` / `--rehearsal`).
    No make-up legs (C343 (3))."""
    from . import p426_plan

    p426_plan.check_kv_pair(ref, test)
    if (ref, test) != fz.TG2_PAIR:                               # change review L6: the one tg2 pair
        raise ValueError(f"the tg2 legs run the pair {','.join(fz.TG2_PAIR)} only, not {ref},{test}")

    def leg(n, arm, kind, role, record, head, mode, **kw):
        spec = _leg(n, f"tg2-m76-{arm}-{kind}" if kind != "rehearsal" else kw.pop("name"), arm, head,
                    kind, kw.pop("pair", kind), role, record, expect=kw.pop("expect", "VALID"))
        return dict(spec, corpus="tg2", mode=mode, entry=list(TG2_CHAIN_ENTRY))
    run = [leg(1, ref, "pilot", "first", "v8", ["--leg", "pilot"], "pilot"),
           leg(2, test, "pilot", "second", "v8", ["--leg", "pilot"], "pilot")]
    for s, (first, second) in (("s1", (ref, test)), ("s2", (test, ref)), ("reload", (test, ref))):
        run += [leg(len(run) + 1, first, s, "first", "amendment", ["--leg", s], "chain"),
                leg(len(run) + 2, second, s, "second", "amendment", ["--leg", s], "chain")]
    rehearsal = (leg("R2", test, "rehearsal", None, "manifest", ["--rehearsal", "r2"], "chain", pair=None, expect="INVALID",
                     name=f"tg2-m76-{test}-rehearsal-r2"),
                 leg("R3", ref, "rehearsal", None, "manifest", ["--rehearsal", "r3"], "chain", pair=None,
                     name=f"tg2-m76-{ref}-rehearsal-r3"))
    return dict(run=tuple(run), makeup=(), rehearsal=rehearsal)


def kv_dossier_name(pair, ref, n, test, m):
    return f"{pair}__{ref}-a{n}__{test}-a{m}.json"


def spec_of(leg):
    spec = leg if isinstance(leg, dict) else BY_NAME.get(leg)
    if spec is None:
        raise ValueError(f"unknown leg {leg!r}")
    return spec


def pair_legs(pair):
    """{arm: leg spec} of one pair, from the table."""
    return {leg["arm"]: leg for leg in BY_NAME.values() if leg["pair"] == pair}


def out_root_of(leg, attempt, out_base) -> Path:
    spec = spec_of(leg)
    return Path(out_base) / f"{spec['name']}.a{attempt}"                 # flat for every attempt, make-up included (spec 16.8)


def leg_argv(leg, attempt, *, worktrees, record_path, out_base, pair_receipt=None, occurrences=None, identity=None,
             lever="mtp") -> list:
    """The chain argv of one leg attempt (spec 6.7): the arm's own venv python and `run_tg1_chain.py` from its worktree, the common
    flags, then (second legs) `--pair-receipt`, (make-up) `--occurrences`. `record_path` is the record the leg runs under (v8 base for
    legs 1-2, the timeout amendment for 3-10, the rehearsal manifest for R1-R3); a manifest carries no probe identity, so
    `identity` {probe_code_sha256, scaffold_policy_sha256, frozen_prompt_date} is required for it."""
    spec = spec_of(leg)
    if not (isinstance(attempt, int) and not isinstance(attempt, bool) and attempt >= 1):
        raise ValueError(f"attempt must be an integer >= 1, not {attempt!r}")
    if spec["kind"] == "makeup" and occurrences is None:
        raise ValueError("a make-up leg needs its occurrences file")
    rehearsal = spec["record"] == "manifest"
    mode = spec.get("mode") or ("pilot" if spec["head"] == ["pilot"] else "chain")      # M76 B4b-1: a tg2 spec names its mode
    rec = p426_record.load(record_path, mode=mode, rehearsal=rehearsal)
    base = dict(rec["base"])
    if rehearsal:
        base.update(identity or {})                          # the manifest records the identity and the date (spec 16.8)
        if not all(base.get(k) for k in ("probe_code_sha256", "scaffold_policy_sha256", "frozen_prompt_date")):
            raise ValueError("a rehearsal leg needs the probe identity and the frozen date (the manifest carries none)")
    arm = spec["arm"]
    wt = Path(worktrees[arm])
    entry = tuple(spec.get("entry") or CHAIN_ENTRY)            # M76 B4b-1: the tg2 legs run `run_tg2_chain.py`
    argv = [str(wt / ".venv-bench/bin/python"), str(wt.joinpath(*entry)), *spec["head"], "--p426",
            "--models", ENTRY, "--predictor", predictor_of(lever, arm), "--out-root", str(out_root_of(spec, attempt, out_base)),
            "--probe-code-sha", base["probe_code_sha256"], "--policy-sha", base["scaffold_policy_sha256"],
            "--frozen-prompt-date", base["frozen_prompt_date"], "--campaign-core", base[f"{arm}_commit"],
            "--frozen-record", str(record_path), *spec["extra"]]
    if lever == "kv":                                           # M76: the chain names its arm (record keys, pair gate)
        argv += ["--lever", "kv", "--kv-arm", arm]
    if pair_receipt is not None:
        argv += ["--pair-receipt", str(pair_receipt)]
    if occurrences is not None:
        argv += ["--occurrences", str(occurrences)]
    return argv


# ----------------------------------------------------------------------------------------------- deadlines (spec 10.2)
def deadline_s(session, langs, amendment) -> float:
    """`T = 1.5 x sum_lang n_lang x w_lang + 1800 s` with the amendment's walls; `langs` = {lang: n}."""
    if session not in KV_SESSIONS:
        raise ValueError(f"unknown session {session!r}")
    return fz.deadline_formula(langs, {"python": amendment["w_python_s"], "go": amendment["w_go_s"]})


def leg_deadline(amendment, base, leg, langs=None) -> float:
    """The supervision deadline of one leg: the v8 base's pilot deadline, the amendment's per-session value (one value for both
    arms of a session), a make-up leg's from its occurrences' languages, a rehearsal leg's fixed bound."""
    spec = spec_of(leg)
    kind = spec["kind"]
    if kind == "pilot":
        return float(base["pilot_deadline_s"])
    if kind == "rehearsal":
        return REHEARSAL_DEADLINE_S
    if kind == "makeup":
        return deadline_s("makeup", langs, amendment)
    return float(amendment["leg_deadline_s"][kind])


# ----------------------------------------------------------------------------------------------- make-up (spec 5.5)
def canonical_occurrences(occurrences, s3=False) -> list:
    """The union of the occurrences, one record per (session, language, item, seed) with the DNF'd arms merged, in the section 5.5
    order: s1 then s2, the session's language order, `occurrence` (the 0-based position in the leg's frozen order), item. One
    implementation, shared with the chain's make-up schedule (`schedules.makeup_canonical`). `s3=True`: M76 (lever kv)."""
    from . import schedules
    return schedules.makeup_canonical(occurrences, **({"s3": True} if s3 else {}))


def makeup_groups(occurrences) -> list:
    """One group per (session, seed, language), in the canonical order, items in their original order (a chain invocation each)."""
    groups = {}
    for m in canonical_occurrences(occurrences):
        groups.setdefault((m["session"], m["seed"], m["language"]), []).append(m["item"])
    return [dict(session=s, seed=seed, language=lang, items=items) for (s, seed, lang), items in groups.items()]


def not_run(root, canonical) -> list:
    """The occurrences with no slot in the leg's realized ledger (a row or a DNF both count as run)."""
    try:
        ledger = fz.read_chain(root).get("p426_ledger") or []
    except fz.Refusal:
        ledger = []
    done = {tuple(e["slot"].split("|")[3:6]) for e in ledger}
    return [m for m in canonical if (m["session"], m["language"], m["item"]) not in done]


# ----------------------------------------------------------------------------------------------- classification (spec 5.1)
def planned_slots(root, chain=None) -> int:
    """The leg's plan: the slots of its frozen schedule (`schedule.json`, whose sha256 `chain.json` records), never a constant
    (spec 16.8). ValueError when the schedule is missing, unreadable, malformed or not the frozen one."""
    return fz.planned_slots(root, chain)


def classify_leg(root, rc, *, arm) -> dict:
    """`{state, class, reason}` of an ended leg from the chain's rc and its `chain.json`, the realized ledger against the leg's
    own frozen schedule, and the item records."""
    root = Path(root)
    try:
        chain = fz.read_chain(root)
    except fz.Refusal:
        if rc == 2:
            return dict(state="NOT_STARTED", **{"class": "entry"}, reason="the chain refused before the router started (no chain.json)")
        return dict(state="INVALID", **{"class": "systemic"}, reason=f"chain rc {rc} and no chain.json")

    def invalid(reason):
        return dict(state="INVALID", **{"class": "systemic"}, reason=reason)
    if chain.get("p426_invalid"):
        return invalid(str(chain["p426_invalid"][-1].get("reason")))
    # S27 §5.4 / §5.6 / §8.3: a leg with an open pause / hold episode is PAUSED (held, not finished): the designer resumes or
    # archives it; it is never harvested as a result
    opened = [h for h in chain.get("p426_holds") or [] if isinstance(h, dict) and h.get("end") is None]
    if opened:
        return dict(state="PAUSED", **{"class": "paused"}, reason=str(opened[-1].get("reason")))
    if rc != 0 or chain.get("status") != "finished":
        return invalid(f"chain rc {rc}, status {chain.get('status')!r}")
    open_inv = [i for i in (chain.get("progress") or {}).get("invocations") or [] if i.get("status") in ("running", "quarantined")]
    if open_inv:
        return invalid(f"{len(open_inv)} invocation(s) still {open_inv[0]['status']}")
    ledger = chain.get("p426_ledger") or []
    try:
        planned = planned_slots(root, chain)
    except ValueError as exc:
        return invalid(str(exc))
    if len(ledger) != planned:
        return invalid(f"the realized ledger has {len(ledger)} slots, the frozen schedule {planned}")
    dnf = len(chain.get("p426_dnf") or [])
    if dnf > MAX_DNF:
        return invalid(f"{dnf} DNF in the leg (more than {MAX_DNF})")
    harness = len(chain.get("p426_harness_dnf") or [])
    if harness > MAX_HARNESS_DNF:                     # S27 §5.6: the chain holds at the 4th; a finished leg never carries one
        return invalid(f"{harness} harness DNF in the leg (more than {MAX_HARNESS_DNF})")
    problems = fz.leg_items_problems(root, arm)
    if problems:
        return invalid(problems[0])
    if dnf or harness:
        parts = ([f"{dnf} transport DNF"] if dnf else []) + ([f"{harness} harness DNF"] if harness else [])
        return dict(state="VALID_WITH_DNF", **{"class": "dnf"}, reason=", ".join(parts) + ", settled")
    return dict(state="VALID", **{"class": "valid"}, reason="")


def speed_tiers(chain) -> dict:
    """S27 §8.3 (P14): what a VALID leg carries besides its quality — `speed_invalid` reasons (a hold, an accounting fault: that
    item only) and the reported harness-fault counts (§5.6). Off-AC / watcher gaps / ALERTs come from the watch journal."""
    holds = [h for h in chain.get("p426_holds") or [] if isinstance(h, dict)]
    accounting = [a.get("slot") for a in chain.get("p426_accounting_faults") or [] if isinstance(a, dict)]
    reasons = ([f"{len(holds)} hold episode(s)"] if holds else [])
    return dict(speed_invalid=reasons, speed_invalid_items=accounting,
                harness_counts=chain.get("p426_harness_counts") or {})


def held_s(root, now) -> float:
    """S27 §8.2: the seconds the leg has spent held or paused — every recorded episode of its `chain.json` (`start_t` / `end_t`,
    epoch seconds), an open one up to `now`. 0 when there is none or the record is unreadable."""
    try:
        holds = json.loads((Path(root) / "chain.json").read_text()).get("p426_holds") or []
    except (OSError, ValueError, AttributeError):
        return 0.0
    total = 0.0
    for h in holds:
        start, end = (h.get("start_t"), h.get("end_t")) if isinstance(h, dict) else (None, None)
        if not isinstance(start, (int, float)):
            continue
        stop = end if isinstance(end, (int, float)) else now
        total += max(0.0, float(stop) - float(start))
    return total


def tg2_strict_rows(leg_roots, session) -> dict:
    """§3 "Strict rows": `{item: {session: 0/1}}` over the harvested legs' planned slots of `session` (their frozen schedules):
    1 iff a row has `passed is True and converged is True`; a `p426_dnf` slot is 0; a planned slot with neither a row nor a DNF
    record refuses (`fz.Refusal`), and so does a row or DNF record of an unplanned slot or a slot with both."""
    out = {}
    for root in leg_roots:
        root = Path(root)
        chain = fz.read_chain(root)
        try:
            sched = json.loads((root / "schedule.json").read_text())
        except (OSError, ValueError):
            raise fz.Refusal(f"{root.name}: no readable frozen schedule.json") from None
        from . import schedules
        if chain.get("schedule_sha256") != schedules.schedule_sha256(sched):
            raise fz.Refusal(f"{root.name}: schedule.json is not the schedule chain.json froze")
        planned = [i for block in sched["blocks"] if block["session"] == session for leg in block["legs"]
                   for inv in leg["invocations"] for i in inv["expect"]]
        rows = {}
        for path in sorted((root / session).glob("*.jsonl")) if (root / session).is_dir() else []:
            for line in path.read_text().splitlines():
                if line.strip():
                    r = json.loads(line)
                    if r.get("id") in rows:
                        raise fz.Refusal(f"{root.name}: {r.get('id')} has two rows")
                    rows[r.get("id")] = r
        dnf = {f"{d.get('language')}/{d.get('item')}" for d in chain.get("p426_dnf") or [] if d.get("session") == session}
        # change review L4: rows and DNFs are exactly the planned slots (rows ∪ DNFs == planned, rows ∩ DNFs = ∅)
        planned_set = set(planned)
        for what, stray in (("row", set(rows) - planned_set), ("DNF record", dnf - planned_set)):
            if stray:
                raise fz.Refusal(f"{root.name}: a {what} for {', '.join(sorted(map(str, stray)))} ({session}), which is not a "
                                 "planned slot")
        both = set(rows) & dnf
        if both:
            raise fz.Refusal(f"{root.name}: {', '.join(sorted(both))} ({session}) has both a row and a DNF record")
        for item in planned:
            if item in rows:
                r = rows[item]
                value = int(r.get("passed") is True and r.get("converged") is True)
            elif item in dnf:
                value = 0
            else:
                raise fz.Refusal(f"{root.name}: the planned slot {item} ({session}) has neither a row nor a DNF record")
            if session in out.get(item, {}):
                raise fz.Refusal(f"{item} {session} is planned twice")
            out.setdefault(item, {})[session] = value
    return out


def pilot_gate(off_root, on_root) -> list:
    """Spec 1: both legs VALID, 5 / 5 items reconciled, zero DNF, ON engagement proven on every eligible request, both speed-valid,
    the pair gate passed. Returns the failed conditions (empty = the gate passes)."""
    return fz.pilot_gate_problems(off_root, on_root)          # owned by `write_amendment` (fix round 3, item 6)


# ----------------------------------------------------------------------------------------------- sequence.json (spec 16.7)
def read_sequence(out_base) -> dict:
    path = Path(out_base) / SEQUENCE_FILE
    doc = json.loads(path.read_text()) if path.is_file() else {}
    for key in ("legs", "pairs", "harvested", "reruns"):
        doc.setdefault(key, [])
    return doc


def tg2_sequence_init(doc):
    """M76 B4b-1: the tg2 sequence's re-check record (`rechecks.<gate>`)."""
    doc.setdefault("rechecks", {})
    return doc


def write_sequence(out_base, doc) -> dict:
    """Atomic replace; the new version names the sha256 of the version it replaces (null for the first)."""
    path = Path(out_base) / SEQUENCE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    doc = dict(doc, previous_sha256=previous)
    tmp = path.with_name(SEQUENCE_FILE + ".tmp")
    with open(tmp, "w") as f:
        f.write(json.dumps(doc, indent=1, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return doc


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def speed_of(path) -> dict:
    """`{valid, reason}` of a leg's speed block from its `watch.jsonl` (the watcher's own verdict function)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "m1"))
    try:
        import bench_watch
    finally:
        sys.path.pop(0)
    return bench_watch.speed_verdict(path)


# ----------------------------------------------------------------------------------------------- the sequencer
class Sequencer:
    def __init__(self, a, ops, clock, sleep, wd):
        self.a, self.ops, self.clock, self.sleep, self.wd = a, ops, clock, sleep, Path(wd)
        self.out = Path(a.out_base)
        self.lever = getattr(a, "lever", "mtp")                       # M76 B3: the KV lever names the arms by their KV label
        self.corpus = getattr(a, "corpus", "tg1")                     # M76 B4b-1: the tg2 legs (lever kv)
        if self.lever == "kv":
            self.arms = tuple(a.arms)
            self.worktrees = {arm: Path(p) for arm, p in a.worktrees.items()}
            self.table = kv_tg2_legs(*self.arms) if self.corpus == "tg2" else kv_legs(*self.arms)
        else:
            self.arms = ("off", "on")
            self.worktrees = {"off": Path(a.worktree_off), "on": Path(a.worktree_on)}
            self.table = dict(run=RUN_LEGS, makeup=MAKEUP_LEGS, rehearsal=REHEARSAL_LEGS)
        self.by_name = {leg["name"]: leg for legs in self.table.values() for leg in legs}
        self.pilots = tuple(leg["name"] for leg in self.table["run"] if leg["kind"] == "pilot")
        self.pause = Path(a.pause_file) if a.pause_file else self.out / "PAUSE"
        self.record_dir = Path(a.record_dir) if getattr(a, "record_dir", None) else None
        self.seq = read_sequence(self.out)
        if self.corpus == "tg2":
            tg2_sequence_init(self.seq)
        self.emails = ()
        self.run_files_done = False
        self.run_files_failed = False
        self.identity = None
        self.canon = None

    # -- state and log
    def log(self, message):
        stamp = datetime.datetime.fromtimestamp(self.clock(), datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self.out.mkdir(parents=True, exist_ok=True)
        with (self.out / LOG_FILE).open("a") as f:
            f.write(f"{stamp} {message}\n")
        print(f"{stamp} {message}", flush=True)

    def save(self):
        self.seq = write_sequence(self.out, self.seq)

    def entries(self, name):
        return [e for e in self.seq["legs"] if e["leg"] == name]

    def harvested(self, entry):
        return any(h["attempt"] == f"{entry['leg']}.a{entry['attempt']}" for h in self.seq["harvested"])

    def selected(self, name):
        """The leg's latest VALID attempt that is harvested (the one a pair names)."""
        done = [e for e in self.entries(name) if e["state"] in VALID_STATES and self.harvested(e)]
        return done[-1] if done else None

    def root(self, spec, attempt):
        return out_root_of(spec, attempt, self.out)

    def pair_legs(self, pair):
        """{arm: leg spec} of one pair, from this lever's table."""
        return {leg["arm"]: leg for leg in self.by_name.values() if leg["pair"] == pair}

    # -- records (spec 10.1, 16.1)
    def load_records(self):
        """Read and verify the records this command runs under. A refusal (rc 2) at the start; a Stop (rc 1) between legs."""
        a = self.a
        if a.cmd == "rehearsal":
            try:
                self.record = p426_record.load(a.manifest, mode="chain", rehearsal=True)
            except p426_record.RecordError as exc:
                raise fz.Refusal(f"--manifest {exc}") from None
            self.base, self.amendment = self.record["doc"], None
            if self.base.get("frozen_prompt_date") != a.frozen_prompt_date:
                raise fz.Refusal(f"--frozen-prompt-date {a.frozen_prompt_date!r} is not the manifest's "
                                 f"{self.base.get('frozen_prompt_date')!r} (the date is frozen when the manifest is written)")
            return
        try:
            base = p426_record.read_sealed(self.record_dir / "v8_base.json")
        except p426_record.RecordError as exc:
            raise fz.Refusal(f"v8_base.json: {exc}") from None
        if base.get("kind") != fz.KIND_V8:
            raise fz.Refusal(f"v8_base.json: kind {base.get('kind')!r} is not {fz.KIND_V8}")
        if (base.get("corpus") == "tg2") != (self.corpus == "tg2"):
            raise fz.Refusal(f"v8_base.json is a {base.get('corpus', 'tg1')} record, the command runs --corpus {self.corpus}")
        if self.corpus == "tg2":
            self.verify_positives(base)
        self.base, self.amendment = base, None
        path = self.record_dir / "amendment.json"
        if path.exists():
            try:
                self.amendment = p426_record.load(path, mode="chain")["doc"]
            except p426_record.RecordError as exc:
                raise fz.Refusal(f"amendment.json: {exc}") from None
        elif a.cmd == "makeup":
            raise fz.Refusal(f"{path.name} is missing: the pilot gate has not written the timeout amendment")

    def verify_positives(self, base):
        """M76 B4b-1 (§3): at start and on resume, the sealed positives record beside v8 is the one v8 names (`positives_sha256`)."""
        path = self.record_dir / "positives.json"
        try:
            doc = json.loads(path.read_text())
        except (OSError, ValueError):
            raise fz.Refusal(f"{path.name} (the tg2 positives record v8 names) is missing or unreadable") from None
        if not ph.sealed_ok(doc) or doc.get("sha256") != base.get("positives_sha256"):
            raise fz.Refusal(f"{path.name}: the tg2 positives record is not the sealed record v8 names (positives_sha256)")

    def record_path(self, spec):
        if spec["record"] == "manifest":
            return Path(self.a.manifest)
        return self.record_dir / ("v8_base.json" if spec["record"] == "v8" else "amendment.json")

    def verify_world(self):
        """Before every launch: the records still verify and the live worktrees are the ones they name."""
        try:
            self.load_records()
        except fz.Refusal as exc:
            raise Stop(1, f"STOP: a record changed: {exc}") from None
        if self.a.cmd == "rehearsal":
            problems = []
            for arm in self.arms:
                st = self.ops.worktree_state(self.worktrees[arm])
                if st.get("head") != self.base[f"{arm}_commit"]:
                    problems.append(f"the {arm} worktree HEAD {str(st.get('head'))[:12]} != the manifest's {self.base[f'{arm}_commit'][:12]}")
                if st.get("clean") is not True:
                    problems.append(f"the {arm} worktree is not clean")
        else:
            problems = fz.live_problems(self.base, self.ops, self.wd)
        if problems:
            raise Stop(1, "STOP: drift against the frozen record: " + "; ".join(problems))

    def check_power(self):
        p = self.ops.power() or {}
        ok = (p.get("watts") == POWER["watts"] and p.get("volts") == POWER["volts"]
              and p.get("battery") is not None and p["battery"] > POWER["battery_above"])
        if not ok:
            raise Stop(1, f"STOP: power {p.get('watts')} W / {p.get('volts')} V, battery {p.get('battery')} % before a launch "
                          f"(needs {POWER['watts']} W / {POWER['volts']} V, battery > {POWER['battery_above']} %)")

    # -- C360 / S26 §2: the host environment (`bench.host_env`) against the run's recorded baseline
    def host_probe(self):
        """The ops' `host_env` seam, or None (test fakes may omit it; `BoxSeqOps` always has it)."""
        probe = getattr(self.ops, "host_env", None)
        return probe if callable(probe) else None

    def host_live(self):
        return json.loads(json.dumps(self.host_probe()()))

    def host_baseline(self):
        """The fingerprint `<out-base>/host_env.json` recorded (sealed, kind `host_env`); unreadable -> Stop(1)."""
        path = self.out / HOST_ENV_FILE
        try:
            doc = json.loads(path.read_text())
        except (OSError, ValueError):
            doc = None
        if not (ph.sealed_ok(doc) and doc.get("kind") == "host_env" and isinstance(doc.get("fingerprint"), dict)):
            raise Stop(1, f"STOP: {HOST_ENV_FILE} (the run's host-environment baseline) is unreadable or not a sealed "
                          "baseline")
        return doc["fingerprint"]

    def host_changes(self):
        """[] without the seam or when the live fingerprint equals the baseline; else the changes (`host_env.diff`)."""
        if self.host_probe() is None:
            return []
        from . import host_env
        return host_env.diff(self.host_baseline(), self.host_live())

    def host_at_launch(self, leg):
        """C384 (S29 H1): `(diff against the run baseline, the live fingerprint)` before a launch, the diff logged; `(None, None)`
        without the seam. Never refuses (an unreadable baseline still stops: `host_baseline`)."""
        if self.host_probe() is None:
            return None, None
        from . import host_env
        live = self.host_live()
        changed = host_env.diff(self.host_baseline(), live)
        if changed:
            self.log(f"host environment differs from the baseline before {leg}: " + "; ".join(changed))
        return changed, live

    def host_record(self, where, changed):
        """C384: a host difference is logged and recorded in `sequence.json` (`host_env_events`); it never stops the run."""
        self.log(f"host environment differs from the baseline {where}: " + "; ".join(changed))
        self.seq.setdefault("host_env_events", []).append(dict(at=co.utc_stamp(self.clock()), where=where, changes=list(changed)))
        self.save()

    def host_env_start(self):
        """At `run()` entry: the first run of an out-base records the baseline (exclusive); a resumed run compares and records
        (C384), never rewriting the baseline."""
        if self.host_probe() is None:
            return
        path = self.out / HOST_ENV_FILE
        if not path.exists() and not path.is_symlink():
            now = self.host_live()
            ph.write_exclusive(path, dict(kind="host_env", fingerprint=now, created=co.utc_stamp(self.clock())))
            self.log(f"host environment baseline recorded ({HOST_ENV_FILE})")
            return
        changed = self.host_changes()
        if changed:
            self.host_record(f"at the run's start (next: {self.next_leg_name()})", changed)

    def next_leg_name(self):
        """The leg this command would process next (for the resume refusal)."""
        for spec in self.legs():
            latest = (self.entries(spec["name"]) or [None])[-1]
            if (latest is None or spec["name"] in (getattr(self.a, "rerun", None) or []) or not self.harvested(latest)
                    or latest["state"] not in (*VALID_STATES, spec["expect"])):
                return spec["name"]
        return "the end of the run"

    def host_log_after_exception(self, name):
        """An exception left a leg's launch region: log the host comparison (never raises; the exception propagates)."""
        try:
            if self.host_probe() is None:
                return
            try:
                changed = self.host_changes()
            except Exception as exc:  # noqa: BLE001
                self.log(f"{name}: an exception left the leg; the host environment could not be compared ({type(exc).__name__})")
                return
            self.log(f"{name}: an exception left the leg; the host environment "
                     + ("changed: " + "; ".join(changed) if changed else "is unchanged"))
            if changed:                                  # C384: recorded too
                self.seq.setdefault("host_env_events", []).append(dict(at=co.utc_stamp(self.clock()),
                                                                       where=f"{name}: an exception left the leg",
                                                                       changes=list(changed)))
                self.save()
        except Exception:  # noqa: BLE001  (logging must not replace the original exception)
            pass

    def host_env_final(self):
        """Both exits of `run()`, before the run files are published: a difference from the baseline after the last leg is
        recorded in `sequence.json` (`host_env_after_last_leg`) and logged; the run ends normally (C384). Once recorded, the
        field follows the latest final check, an empty diff included (S29 H3b); a run that never differed keeps no field."""
        changed = self.host_changes()
        if changed or "host_env_after_last_leg" in self.seq:
            self.seq["host_env_after_last_leg"] = list(changed)
            self.save()
        if changed:
            self.log("host environment differs from the baseline after the last leg: " + "; ".join(changed))
        elif "host_env_after_last_leg" in self.seq:
            self.log("host environment equals the baseline after the last leg (the earlier difference is superseded)")

    # -- the boundary: PAUSE and the idle gap (spec 1, 9)
    def last_leg_end(self):
        try:
            return pl.read_last_leg_end(self.wd)
        except ValueError as exc:
            raise Stop(1, f"STOP: {exc}") from None

    def wait_boundary(self):
        held, released = False, None
        while True:
            if self.pause.exists():
                if not held:
                    self.log(f"PAUSE: holding at the leg boundary ({self.pause})")
                    held = True
                self.sleep(POLL_S)
                continue
            if held:
                held, released = False, self.clock()
                self.log("PAUSE removed: the idle gap restarts")
            refs = [t for t in (self.last_leg_end(), released) if t is not None]
            if not refs:
                return
            since = self.clock() - max(refs)
            if since >= pl.IDLE_GAP_S:
                return
            self.sleep(min(pl.IDLE_GAP_S - since, POLL_S))

    # -- one leg
    def next_attempt(self, spec):
        nums = [e["attempt"] for e in self.entries(spec["name"])]
        base = out_root_of(spec, 1, self.out).parent
        if base.is_dir():
            nums += [int(m.group(1)) for p in base.iterdir() if (m := re.fullmatch(re.escape(spec["name"]) + r"\.a([1-9][0-9]*)", p.name))]
        return max(nums + [0]) + 1

    def partner_receipt(self, spec):
        """The first leg's receipt for the second leg of a pair (spec 6.5); a restart between the legs resumes from the persisted file."""
        if spec["role"] != "second":
            return None
        first = self.pair_legs(spec["pair"])
        first = next(s for s in first.values() if s["role"] == "first")
        entry = self.selected(first["name"])
        if entry is None:
            raise Stop(1, f"STOP: no VALID harvested attempt of {first['name']} to pair {spec['name']} with")
        path = self.root(first, entry["attempt"]) / "receipt.json"
        if not path.is_file():
            raise Stop(1, f"STOP: {first['name']}.a{entry['attempt']} left no receipt.json for the pair gate")
        return path

    def deadline(self, spec):
        langs = None
        if spec["kind"] == "makeup":
            langs = {}
            for m in self.canon:
                langs[m["language"]] = langs.get(m["language"], 0) + 1
        return leg_deadline(self.amendment, self.base, spec, langs)

    def start_watcher(self, spec, root, handle):
        wt = self.worktrees[spec["arm"]]
        argv = [str(wt / ".venv-bench/bin/python"), str(wt / "benchmark/m1/bench_watch.py"), "--chain-json", str(root / "chain.json"),
                "--driver-pid", str(handle.pid), "--out", str(root / "watch.jsonl"), "--interval", str(int(WATCH_INTERVAL_S)),
                "--pred-s", str(self.base.get("generic_pred_s", 250))]
        return self.ops.launch(argv, cwd=wt, pass_fds=())

    def supervise(self, spec, attempt, root, handle):
        """Wait for the chain; poll the watcher; write `OVERRUN_PAUSED` at the deadline. Nothing is ever signalled. S27 §8.2: the
        leg's deadline is suspended for its held / paused intervals (the chain's recorded episodes, the open one so far)."""
        deadline, t0 = self.deadline(spec), self.clock()
        watcher, watcher_dead, overrun = None, None, False
        while self.ops.alive(handle.pid, handle.start):
            if watcher is None and root.exists():
                watcher = self.start_watcher(spec, root, handle)
                self.log(f"watcher PID {watcher.pid} bound to chain PID {handle.pid}")
            if watcher is not None and watcher_dead is None and not self.ops.alive(watcher.pid, watcher.start):
                watcher_dead = self.clock()
                self.log(f"{spec['name']}.a{attempt}: the watcher died while the chain was running (the leg is speed-invalid)")
            if not overrun and self.clock() - t0 - held_s(root, self.clock()) >= deadline:
                overrun = True
                atomic_text(self.out / OVERRUN_FILE, json.dumps(dict(leg=spec["name"], attempt=attempt, deadline_s=deadline,
                                                                    at=co.utc_stamp(self.clock())), sort_keys=True) + "\n")
                message = f"OVERRUN_PAUSED: {spec['name']}.a{attempt} passed its {deadline:.0f} s deadline; never killed, the operator decides"
                self.log(message)
                if getattr(self.ops, "notify", None):
                    self.ops.notify(message)
            self.sleep(POLL_S)
        rc = self.ops.wait(handle)
        return rc, t0, watcher, watcher_dead, overrun

    def finish_watcher(self, watcher):
        """After the chain's exit the watcher finalizes its journal; wait for its exit (bounded, never killed)."""
        if watcher is None:
            return True
        since = self.clock()
        while self.ops.alive(watcher.pid, watcher.start):
            if self.clock() - since > WATCHER_GRACE_S:
                return False
            self.sleep(POLL_S)
        return True

    def run_leg(self, spec):
        self.wait_boundary()
        self.verify_world()
        self.check_power()
        before, env_launch = self.host_at_launch(spec["name"])     # C384 (S29 H1): recorded and logged, the leg launches
        if self.corpus == "tg2":                       # M76 B4b-1: the deadline exists before the launch (no default wall)
            try:
                value = float(self.deadline(spec))
            except (ValueError, KeyError, TypeError) as exc:
                raise Stop(1, f"STOP: {spec['name']} has no supervision deadline in its record: {exc} (nothing launched)") from None
            if not value > 0:
                raise Stop(1, f"STOP: {spec['name']}'s supervision deadline {value} is not positive (nothing launched)")
        attempt = self.next_attempt(spec)
        name = f"{spec['name']}.a{attempt}"
        root = self.root(spec, attempt)
        first_receipt = self.partner_receipt(spec)
        occurrences = None
        if spec["kind"] == "makeup":
            occurrences = self.out / "makeup" / f"occurrences.{spec['arm']}.jsonl"
            atomic_text(occurrences, "".join(json.dumps(m, sort_keys=True) + "\n" for m in self.canon))
        argv = leg_argv(spec, attempt, worktrees=self.worktrees, record_path=self.record_path(spec), out_base=self.out,
                        pair_receipt=first_receipt, occurrences=occurrences, identity=self.identity, lever=self.lever)
        argv += ["--pause-file", str(self.pause)]           # S27 §8.2: the chain holds at item boundaries on the same PAUSE file
        entry = dict(leg=spec["name"], attempt=attempt, state="RUNNING")
        if before:
            entry["host_env_before"] = list(before)
        self.seq["legs"].append(entry)
        self.save()
        self.log(f"START {name}: " + json.dumps(argv))
        try:                                           # S26 §2: from the launch to the leg.json write
            handle = self.ops.launch(argv, cwd=self.worktrees[spec["arm"]], pass_fds=())
            self.log(f"chain PID {handle.pid}")
            rc, t0, watcher, watcher_dead, overrun = self.supervise(spec, attempt, root, handle)
            ended = self.clock()
            atomic_text(self.wd / pl.LAST_LEG_END, repr(float(ended)) + "\n")
            cls = classify_leg(root, rc, arm=spec["arm"])
            if overrun and cls["state"] == "INVALID" and not self.finished_cleanly(root):
                cls = dict(cls, state="OVERRUN")
            settled = self.finish_watcher(watcher)
            if watcher is None:
                speed = dict(valid=False, reason="no watcher was started (the leg never created its out-root)")
            elif watcher_dead is not None:
                speed = dict(valid=False, reason="the watcher died before the chain exited")
            elif not settled:
                speed = dict(valid=False, reason="the watcher did not finalize its journal")
            else:
                speed = speed_of(root / "watch.jsonl")
            during = None                              # C384 (S29 H2): what changed between the launch and the end, recorded
            if env_launch is not None:
                from . import host_env
                during = host_env.diff(env_launch, self.host_live())
                if during:
                    self.log(f"host environment changed during {name}: " + "; ".join(during))
            root.mkdir(parents=True, exist_ok=True)
            doc = dict(leg=spec["name"], attempt=attempt, state=cls["state"], reason=cls["reason"], chain_rc=rc,
                       started=co.utc_stamp(t0), ended=co.utc_stamp(ended), speed_valid=bool(speed["valid"]),
                       speed_reason=speed["reason"], overrun=overrun, **{"class": cls["class"]})
            if env_launch is not None:
                doc.update(host_env_before=list(before), host_env_during=list(during))
            if spec["kind"] == "makeup" and cls["state"] not in VALID_STATES:
                doc["not_run"] = not_run(root, self.canon)
            ph.write_exclusive(root / "leg.json", doc)
        except BaseException:
            self.host_log_after_exception(name)
            raise
        entry["state"] = cls["state"]
        if during:
            entry["host_env_during"] = list(during)
        self.save()
        self.log(f"END {name}: rc {rc} state {cls['state']}" + (f" ({cls['reason']})" if cls["reason"] else ""))
        if not settled:
            raise Stop(1, f"STOP: the watcher of {name} is still alive {WATCHER_GRACE_S:.0f} s after the chain exited (not killed)")
        if cls["state"] == "PAUSED":                   # S27 §5.7: held, not finished — the designer resumes or archives it
            raise Stop(3, f"STOP: {name} is PAUSED ({cls['reason']}); the designer resumes or archives it (never harvested)")
        self.harvest(spec, entry)
        if overrun:
            raise Stop(3, f"STOP: {name} overran its deadline (OVERRUN_PAUSED); remove {OVERRUN_FILE} to resume")
        return entry

    @staticmethod
    def finished_cleanly(root):
        try:
            chain = fz.read_chain(root)
        except fz.Refusal:
            return False
        return bool(chain.get("p426_invalid")) or chain.get("status") == "finished"

    def harvest(self, spec, entry):
        name = f"{entry['leg']}.a{entry['attempt']}"
        res = self.ops.harvest(self.root(spec, entry["attempt"]), emails=self.emails)
        if res.get("rc") != 0:
            line = " ".join(str(res.get("message") or "").split())[:600]       # the harvest's own `REFUSED:` / `ERROR:` line (no values)
            if line:
                self.log(f"harvest {name}: {line}")
            raise Stop(4, f"STOP: the harvest of {name} failed (rc {res.get('rc')}); a rerun of the same command retries it")
        self.seq["harvested"].append(dict(attempt=name, harvest_sha256=res["harvest_sha256"]))
        self.save()
        for note in res.get("notes") or []:            # S29 P6b: the unrecognised files HARVEST.json lists (not copied)
            self.log(f"harvest {name}: {' '.join(str(note).split())[:600]}")
        self.log(f"HARVESTED {name}")

    # -- pairs and the pilot gate
    def ensure_dossier(self, spec):
        if self.lever == "kv":
            return self.ensure_kv_dossier(spec)
        legs = self.pair_legs(spec["pair"])
        sel = {arm: self.selected(s["name"]) for arm, s in legs.items()}
        if None in sel.values():
            return
        attempts = {arm: f"{legs[arm]['name']}.a{sel[arm]['attempt']}" for arm in sel}
        path = self.out / "pairs" / f"{spec['pair']}__off-a{sel['off']['attempt']}__on-a{sel['on']['attempt']}.json"
        record = next((p for p in self.seq["pairs"] if p["off"] == attempts["off"] and p["on"] == attempts["on"]), None)
        # the verdict is always recomputed from the current receipts: a stored dossier (or `sequence.json` record) is verified, never trusted
        roots = {arm: self.root(legs[arm], sel[arm]["attempt"]) for arm in sel}
        off, on = fz.read_receipt(roots["off"]), fz.read_receipt(roots["on"])
        problems = pr.pair_problems(off, on)
        differences = pr.observed_differences(off, on) if not problems else [
            dict(process="-", field="pair_gate", off=None, on=p) for p in problems]
        verdict = "PASS" if not problems else "FAIL"
        harvests = {arm: Path(self.ops.harvest_path(attempts[arm])) / "HARVEST.json" for arm in sel}
        if path.exists():
            self.verify_dossier(path, spec["pair"], attempts, roots, harvests, differences, verdict)
        else:
            pr.write_dossier(path, pair=spec["pair"],
                             off=dict(attempt=attempts["off"], receipt=roots["off"] / "receipt.json", harvest=harvests["off"]),
                             on=dict(attempt=attempts["on"], receipt=roots["on"] / "receipt.json", harvest=harvests["on"]),
                             differences=differences, verdict=verdict)
        if record is None:
            record = dict(pair=spec["pair"], off=attempts["off"], on=attempts["on"], dossier=f"pairs/{path.name}", verdict=verdict)
            self.log(f"DOSSIER {path.name}: {verdict}" + ("" if verdict == "PASS" else " — " + "; ".join(problems)[:600]))
            self.publish_dossier_or_stop(path)               # published BEFORE the pair state records it (a failure is exit 4)
            record["published"] = self.a.cmd != "rehearsal"        # a rehearsal publishes nothing
            self.seq["pairs"].append(record)
            self.save()
        elif not record.get("published") and self.a.cmd != "rehearsal":
            self.publish_dossier_or_stop(path)
            record["published"] = True
            self.save()
        if verdict != "PASS":
            raise Stop(1, f"STOP: the pair gate failed for {spec['pair']} (dossier {path.name}); the operator decides")

    def _kv_gate(self, roots):
        ref, test = self.arms
        first, second = fz.read_receipt(roots[ref]), fz.read_receipt(roots[test])
        problems = pr.kv_pair_problems(first, second)
        differences = pr.kv_observed_differences(first, second) if not problems else [
            dict(process="-", field="pair_gate", **{ref: None, test: p}) for p in problems]
        return problems, differences, "PASS" if not problems else "FAIL"

    def ensure_kv_dossier(self, spec):
        """M76 B3: the KV pair's dossier `pairs/<pair>__<ref>-a<n>__<test>-a<m>.json` (the KV pair gate, recomputed every time)."""
        ref, test = self.arms
        legs = self.pair_legs(spec["pair"])
        sel = {arm: self.selected(s["name"]) for arm, s in legs.items()}
        if None in sel.values():
            return
        attempts = {arm: f"{legs[arm]['name']}.a{sel[arm]['attempt']}" for arm in sel}
        path = self.out / "pairs" / kv_dossier_name(spec["pair"], ref, sel[ref]["attempt"], test, sel[test]["attempt"])
        record = next((p for p in self.seq["pairs"] if p.get(ref) == attempts[ref] and p.get(test) == attempts[test]), None)
        roots = {arm: self.root(legs[arm], sel[arm]["attempt"]) for arm in sel}
        problems, differences, verdict = self._kv_gate(roots)
        harvests = {arm: Path(self.ops.harvest_path(attempts[arm])) / "HARVEST.json" for arm in sel}
        if path.exists():
            self.verify_dossier(path, spec["pair"], attempts, roots, harvests, differences, verdict, arms=self.arms)
        else:
            pr.write_kv_dossier(path, pair=spec["pair"], ref=ref, test=test, differences=differences, verdict=verdict,
                                arms={arm: dict(attempt=attempts[arm], receipt=roots[arm] / "receipt.json", harvest=harvests[arm])
                                      for arm in (ref, test)}, **({"corpus": "tg2"} if self.corpus == "tg2" else {}))
        if record is None:
            record = {"pair": spec["pair"], ref: attempts[ref], test: attempts[test], "dossier": f"pairs/{path.name}",
                      "verdict": verdict}
            self.log(f"DOSSIER {path.name}: {verdict}" + ("" if verdict == "PASS" else " — " + "; ".join(problems)[:600]))
            self.publish_dossier_or_stop(path)
            record["published"] = self.a.cmd != "rehearsal"
            self.seq["pairs"].append(record)
            self.save()
        elif not record.get("published") and self.a.cmd != "rehearsal":
            self.publish_dossier_or_stop(path)
            record["published"] = True
            self.save()
        if verdict != "PASS":
            raise Stop(1, f"STOP: the KV pair gate failed for {spec['pair']} (dossier {path.name}); the operator decides")

    def publish_dossier_or_stop(self, path):
        """Publish one pair dossier (idempotent: the same bytes are done); a rehearsal publishes nothing. A failure is exit 4."""
        if self.a.cmd == "rehearsal":
            return
        try:
            self.ops.publish_dossier(path, emails=self.emails)
        except Exception as exc:  # noqa: BLE001
            raise Stop(4, f"STOP: the pair dossier {Path(path).name} was NOT published ({type(exc).__name__}: {exc}); "
                          "a rerun of the same command retries") from None

    def republish_dossiers(self):
        """Resume: every recorded pair dossier not yet published is published now, idempotently (same bytes = done)."""
        for record in self.seq["pairs"]:
            if record.get("published") or self.a.cmd == "rehearsal":
                continue
            self.reverify_recorded_dossier(record)            # never publish a dossier the current receipts no longer back
            self.publish_dossier_or_stop(self.out / record["dossier"])
            record["published"] = True
            self.save()

    def reverify_recorded_dossier(self, record):
        """A recorded pair dossier is re-verified with `verify_dossier` against the CURRENT receipts / harvests of its two attempts
        (verdict recomputed, nothing trusted); a mismatch stops (rc 1). Returns the recomputed verdict."""
        if self.lever == "kv":
            attempts = {arm: record[arm] for arm in self.arms}
            roots = {arm: self.out / attempts[arm] for arm in attempts}
            path = self.out / record["dossier"]
            try:
                problems, differences, verdict = self._kv_gate(roots)
            except fz.Refusal as exc:
                raise Stop(1, f"STOP: the pair dossier {path.name} cannot be re-verified: {exc} (the operator decides)") from None
            harvests = {arm: Path(self.ops.harvest_path(attempts[arm])) / "HARVEST.json" for arm in attempts}
            self.verify_dossier(path, record["pair"], attempts, roots, harvests, differences, verdict, arms=self.arms)
            return verdict
        attempts = dict(off=record["off"], on=record["on"])
        roots = {arm: self.out / attempts[arm] for arm in attempts}
        path = self.out / record["dossier"]
        try:
            off, on = fz.read_receipt(roots["off"]), fz.read_receipt(roots["on"])
        except fz.Refusal as exc:
            raise Stop(1, f"STOP: the pair dossier {path.name} cannot be re-verified: {exc} (the operator decides)") from None
        problems = pr.pair_problems(off, on)
        differences = pr.observed_differences(off, on) if not problems else [
            dict(process="-", field="pair_gate", off=None, on=p) for p in problems]
        verdict = "PASS" if not problems else "FAIL"
        harvests = {arm: Path(self.ops.harvest_path(attempts[arm])) / "HARVEST.json" for arm in attempts}
        self.verify_dossier(path, record["pair"], attempts, roots, harvests, differences, verdict)
        return verdict

    @staticmethod
    def verify_dossier(path, pair, attempts, roots, harvests, differences, verdict, arms=("off", "on")):
        """An existing dossier equals what the current records give (self-hash, pair, arms, receipt / harvest hashes, differences,
        verdict); the first mismatch stops the sequence (rc 1) naming the field."""
        def stop(field):
            raise Stop(1, f"STOP: the pair dossier {Path(path).name} does not match the leg records: {field} "
                          f"(never trusted; the operator decides)")

        def sha(p):
            try:
                return hashlib.sha256(Path(p).read_bytes()).hexdigest()
            except OSError:
                return None
        try:
            doc = json.loads(Path(path).read_text())
        except (OSError, ValueError):
            stop("file (unreadable)")
        if not ph.sealed_ok(doc):
            stop("sha256 (missing or not the self-hash)")
        if doc.get("pair") != pair:
            stop("pair")
        recorded = doc.get("arms") if isinstance(doc.get("arms"), dict) else {}
        for arm in arms:
            got = recorded.get(arm) if isinstance(recorded.get(arm), dict) else {}
            for field, want in (("attempt", attempts[arm]), ("receipt_sha256", sha(roots[arm] / "receipt.json")),
                                ("harvest_sha256", sha(harvests[arm]))):
                if want is None or got.get(field) != want:
                    stop(f"arms.{arm}.{field}")
        if doc.get("differences") != differences:
            stop("differences")
        if doc.get("verdict") != verdict:
            stop("verdict")

    def ensure_amendment(self):
        """After legs 1-2: the pilot gate; all conditions pass -> the timeout amendment is written (once)."""
        path = self.record_dir / "amendment.json"
        off, on = (self.selected(n) for n in self.pilots)
        roots = [self.root(self.by_name[n], e["attempt"]) for n, e in zip(self.pilots, (off, on))]
        if path.exists():
            self.verify_amendment(path, off, on, roots)
            return
        try:                                                  # the pilot gate runs inside `write_amendment`
            fz.write_amendment(self.record_dir / "v8_base.json", roots[0], roots[1], path, self.ops,
                               **({"corpus": "tg2"} if self.corpus == "tg2" else {}))
        except fz.Refusal as exc:
            raise Stop(1, f"STOP: pilot gate FAILED, the operator decides (no timeout amendment written): {exc}"[:1700]) from None
        self.load_records()
        self.log(f"pilot gate PASSED: the timeout amendment is written ({path.name})")

    def verify_existing_amendment(self):
        """Every command that consumes an existing amendment (`run`, `makeup`) re-verifies it against the selected pilots first."""
        path = self.record_dir / "amendment.json"
        if not path.exists():
            return
        off, on = (self.selected(n) for n in self.pilots)
        if off is None or on is None:
            raise Stop(1, f"STOP: the timeout amendment {path.name} exists but the pilots it was gated on are not recorded "
                          "in sequence.json (the operator decides)")
        roots = [self.root(self.by_name[n], e["attempt"]) for n, e in zip(self.pilots, (off, on))]
        self.verify_amendment(path, off, on, roots)

    def verify_amendment(self, path, off, on, roots):
        """An existing amendment is re-verified, never trusted: its self-hash, its kind, the v8 base it links, and that the pilot
        dossier it was gated on is the selected pilots' PASS dossier (the sha256 it records)."""
        def stop(what):
            raise Stop(1, f"STOP: the timeout amendment {path.name} does not verify: {what} (the operator decides)")
        try:
            doc = p426_record.read_sealed(path)
            base = p426_record.read_sealed(self.record_dir / "v8_base.json")
        except p426_record.RecordError as exc:
            stop(str(exc))
        if doc.get("kind") != "p426_timeout_amendment":
            stop(f"kind {doc.get('kind')!r}")
        if doc.get("v8_base_sha256") != base["sha256"]:
            stop("v8_base_sha256 is not the v8 base's sha256")
        names = (f"{self.pilots[0]}.a{off['attempt']}", f"{self.pilots[1]}.a{on['attempt']}")
        pair = next((p for p in self.seq["pairs"] if p["pair"] == "pilot" and (p.get(self.arms[0]), p.get(self.arms[1])) == names),
                    None)
        if pair is None or pair.get("verdict") != "PASS":
            stop("the selected pilots have no PASS pilot dossier")
        if self.reverify_recorded_dossier(pair) != "PASS":    # freshly verified against the current receipts, not the stored verdict
            stop("the pilot dossier no longer verifies as a PASS against the current receipts")
        dossier = fz.pilot_dossier_path(*roots, arms=self.arms)
        try:
            sha = hashlib.sha256(dossier.read_bytes()).hexdigest()
        except OSError:
            stop(f"the pilot dossier {dossier.name} is missing")
        if doc.get("pilot_dossier_sha256") != sha:
            stop("pilot_dossier_sha256 is not the selected pilot dossier's sha256")

    def after_leg(self, spec, entry):
        """What follows a finished, harvested leg (also on resume): its state, its pair dossier, the pilot gate."""
        if entry["state"] not in VALID_STATES:
            if entry["state"] == spec["expect"]:
                self.log(f"{spec['name']}: {entry['state']} as the rehearsal expects")
                return
            raise Stop(1, f"STOP: {spec['name']}.a{entry['attempt']} is {entry['state']} (a rerun is an operator decision)")
        if spec["pair"] and spec["role"] == "second":
            self.ensure_dossier(spec)
        if spec["name"] == self.pilots[1]:
            self.ensure_amendment()
        if self.corpus == "tg2" and spec["role"] == "second" and spec["kind"] in ("s1", "reload"):
            self.ensure_recheck("s1" if spec["kind"] == "s1" else "s2")      # re-check 1 after s1, re-check 2 after the reload

    # -- M76 B4b-1: the two nuisance re-check gates (E4)
    def recheck_path(self, gate):
        return self.out / "run" / f"recheck-{gate}.json"

    def recheck_rows(self, gate):
        """Per arm the strict rows `{item: {session: 0/1}}` of the harvested legs of the gate's sessions; and their attempts."""
        rows, attempts = {arm: {} for arm in self.arms}, {}
        for session in RECHECK_GATES[gate]:
            for arm in self.arms:
                name = f"tg2-m76-{arm}-{session}"
                entry = self.selected(name)
                if entry is None:
                    raise Stop(1, f"STOP: re-check {gate}: no VALID harvested attempt of {name}")
                attempt = f"{name}.a{entry['attempt']}"
                attempts.setdefault(arm, []).append(attempt)
                try:
                    got = tg2_strict_rows([self.ops.harvest_path(attempt)], session)
                except fz.Refusal as exc:
                    raise Stop(1, f"STOP: re-check {gate}: {exc}") from None
                for item, value in got.items():
                    rows[arm].setdefault(item, {}).update(value)
        return rows, attempts

    def ensure_recheck(self, gate):
        """Re-check 1 (`s1`, after both s1 legs are harvested) / re-check 2 (`s2`, over s1 + s2): `m76_sim.recheck("A8", N16, X)`
        on the strict rows, its record sealed into `<out-base>/run/recheck-<gate>.json` and its sha256 in `sequence.json`
        (`rechecks.<gate>`). Re-check 1 outside (or `operator_review`) stops with rc 5 until `--recheck-ack <that sha256>`
        with `--recheck-ack-by` and `--recheck-ack-ruling` (S29 K2: `ack` records actor and ruling; a recorded ack without
        them is kept as recorded and accepted); re-check 2 never stops (B4b-2 labels its verdict). A resume re-verifies the sealed record, never re-runs it (change
        review L3): a record without its sealed file stops (the operator decides); a sealed file without a record (a stop
        between the seal and the save) is re-verified and recorded from the file; only when neither exists is it computed."""
        import tempfile
        from . import m76_sim
        path, rechecks = self.recheck_path(gate), self.seq.setdefault("rechecks", {})
        rec = rechecks.get(gate)
        if path.exists():
            try:
                doc = json.loads(path.read_text())
            except (OSError, ValueError):
                doc = None
            if not ph.sealed_ok(doc):
                raise Stop(1, f"STOP: {path.name} does not verify as a sealed re-check record (the operator decides)")
            self.check_recheck_doc(gate, path, doc)              # V1: every resume, against the current selection
            if rec is None:
                rec = self.recover_recheck(gate, path, doc)
            elif rec.get("sha256") != doc["sha256"]:
                raise Stop(1, f"STOP: {path.name} is not the sealed re-check sequence.json records (the operator decides)")
        elif rec is not None:
            raise Stop(1, f"STOP: sequence.json records re-check {gate} (sha256 {str(rec.get('sha256'))[:16]}) but {path.name} "
                          "is missing; a recorded re-check is never re-run (the operator decides)")
        else:
            rows, attempts = self.recheck_rows(gate)
            ref, test = self.arms
            self.out.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=f".recheck-{gate}-", dir=self.out) as tmp:
                m76_sim.recheck("A8", rows[ref], rows[test], out=tmp)
                result = json.loads((Path(tmp) / "recheck-A8.json").read_text())
            doc = ph.write_exclusive(path, dict(gate=gate, axis="A8", sessions=list(RECHECK_GATES[gate]), ref=ref, test=test,
                                                attempts=attempts, recheck=result, at=co.utc_stamp(self.clock())))
            rec = rechecks[gate] = dict(sha256=doc["sha256"], path=f"run/{path.name}", inside=bool(result.get("inside")),
                                        operator_review=bool(result.get("operator_review")))
            self.save()
            self.log(f"RE-CHECK {gate}: inside={rec['inside']} operator_review={rec['operator_review']} sha256={doc['sha256'][:16]}")
        if (rec["inside"] and not rec["operator_review"]) or gate != "s1":
            return
        ack = getattr(self.a, "recheck_ack", None)
        if rec.get("ack"):
            return                                       # S29 K2: a recorded ack (with or without an actor) stays as recorded
        if ack == rec["sha256"]:
            actor, ruling = recheck_ack_actor(self.a)    # S29 K2: no actor / ruling refuses before anything is recorded
            rec["ack"] = dict(sha256=ack, at=co.utc_stamp(self.clock()), actor=actor, ruling=ruling)
            self.save()
            state = "outside" if not rec["inside"] else "operator review"
            self.log(f"RE-CHECK {gate}: {state}, acknowledged by the {actor} under {ruling} ({ack[:16]})")
            return
        raise Stop(5, f"STOP: re-check {gate} is outside the committed grid or needs operator review ({path.name}, sha256 "
                      f"{rec['sha256']}); resume with --recheck-ack <that sha256> --recheck-ack-by operator|designer "
                      "--recheck-ack-ruling <ruling>")

    def recheck_attempts(self, gate):
        """Per arm the selected (VALID, harvested) attempts of the gate's sessions, as `recheck_rows` names them."""
        attempts = {}
        for session in RECHECK_GATES[gate]:
            for arm in self.arms:
                name = f"tg2-m76-{arm}-{session}"
                entry = self.selected(name)
                if entry is None:
                    raise Stop(1, f"STOP: re-check {gate}: no VALID harvested attempt of {name}")
                attempts.setdefault(arm, []).append(f"{name}.a{entry['attempt']}")
        return attempts

    def check_recheck_doc(self, gate, path, doc):
        """A sealed re-check document (recorded or not, verify round 2 V1) is this gate's over the CURRENT selection: its gate,
        axis, sessions, arms and attempts equal what the sequence selects now; a mismatch (e.g. a rerun selected another
        attempt) stops with rc 1 — the operator decides; it is never recomputed."""
        ref, test = self.arms
        want = dict(gate=gate, axis="A8", sessions=list(RECHECK_GATES[gate]), ref=ref, test=test,
                    attempts=self.recheck_attempts(gate))
        bad = [k for k, v in want.items() if doc.get(k) != v]
        if bad or not isinstance(doc.get("recheck"), dict):
            raise Stop(1, f"STOP: {path.name}: its {', '.join(bad) or 'recheck'} is not this re-check's over the current "
                          "selection (a rerun since?); a sealed re-check is never recomputed (the operator decides)")

    def recover_recheck(self, gate, path, doc):
        """The crash window (change review L3): a sealed re-check file that `sequence.json` never recorded (already checked
        against the current selection by `check_recheck_doc`); it is recorded from the file (never re-run) and logged."""
        result = doc["recheck"]
        rec = self.seq["rechecks"][gate] = dict(sha256=doc["sha256"], path=f"run/{path.name}", inside=bool(result.get("inside")),
                                                operator_review=bool(result.get("operator_review")))
        self.save()
        self.log(f"RE-CHECK {gate}: recorded from the sealed file {path.name} (sealed before a stop, never recorded; not re-run): "
                 f"inside={rec['inside']} operator_review={rec['operator_review']} sha256={doc['sha256'][:16]}")
        return rec

    def run_file_paths(self):
        """The run files published with the sequence: the frozen-record directory's files, the sealed re-checks, `sequence.json`."""
        paths = sorted(p for p in self.record_dir.iterdir() if p.is_file()) if self.record_dir and self.record_dir.is_dir() else []
        run = self.out / "run"
        if self.corpus == "tg2" and run.is_dir():
            paths += [p for p in sorted(run.glob("recheck-s*.json")) if p not in paths]
        return paths + self.host_env_paths() + [self.out / SEQUENCE_FILE]

    def host_env_paths(self):
        """C360 / S26 §2: the run's host-environment baseline, published with the run files when it exists."""
        path = self.out / HOST_ENV_FILE
        return [path] if path.is_file() else []

    # -- S29 H5 (C384): legs the C360 host guard recorded INVALID
    def c384_supersede(self, spec, entry):
        """A resumed leg whose `leg.json` is INVALID with the C360 host reason and no `(prior: …)`, not yet harvested, takes the
        state `classify_leg(root, recorded chain_rc, arm)` gives (+ the OVERRUN rule with the recorded `overrun`). The original
        is kept byte-identical as `leg.c360.json` (harvested beside it); `leg.json` is replaced (atomically) by a sealed record
        with the new state, the host changes and the supersession (`c384`: the original's sha256s); the sequence entry follows.
        A prior reason, an already harvested attempt, or one whose harvest is committed (its `HARVEST.json` exists at
        `ops.harvest_path`, even when `sequence.json` does not say so) is left as recorded (logged). Updates `entry` in place."""
        name = f"{spec['name']}.a{entry['attempt']}"
        root = self.root(spec, entry["attempt"])
        path, kept = root / "leg.json", root / C384_SUPERSEDED
        try:
            raw = path.read_bytes()
            doc = json.loads(raw)
        except (OSError, ValueError):
            return
        if not ph.sealed_ok(doc) or (doc.get("leg"), doc.get("attempt")) != (spec["name"], entry["attempt"]):
            return                                     # not a verifiable record of this attempt: the existing paths decide
        if isinstance(doc.get("c384"), dict):          # superseded already; a stop came before sequence.json followed
            if entry.get("c384") is None:
                self.c384_check_kept(name, kept, doc["c384"].get("superseded_file_sha256"))
                self.c384_entry(entry, doc)
                self.log(f"{name}: C384: the superseding leg.json is recorded in sequence.json (state {doc['state']})")
            return
        reason = str(doc.get("reason") or "")
        if entry.get("state") != "INVALID" or doc.get("state") != "INVALID" or not reason.startswith(HOST_ENV_REASON + ": "):
            return
        if " (prior: " in reason:
            self.log(f"{name}: INVALID by the host change with a prior classification; left as recorded (C384 re-derives only "
                     "a leg with no prior)")
            return
        if self.harvested(entry):
            self.log(f"{name}: INVALID by the host change and already harvested; left as recorded")
            return
        if os.path.lexists(Path(self.ops.harvest_path(name)) / "HARVEST.json"):     # committed; sequence.json not yet saying so
            self.log(f"{name}: INVALID by the host change and its harvest is already committed; left as recorded")
            return
        cls = classify_leg(root, doc.get("chain_rc"), arm=spec["arm"])
        if doc.get("overrun") is True and cls["state"] == "INVALID" and not self.finished_cleanly(root):
            cls = dict(cls, state="OVERRUN")
        file_sha = hashlib.sha256(raw).hexdigest()
        self.c384_check_kept(name, kept, file_sha, create=raw)
        body = {k: v for k, v in doc.items() if k not in ("sha256", "not_run")}
        body.update(state=cls["state"], reason=cls["reason"], host_env_before=[], host_env_during=c360_changes(reason),
                    c384=dict(rule="C384", superseded=C384_SUPERSEDED, superseded_sha256=doc["sha256"],
                              superseded_file_sha256=file_sha, superseded_state=doc["state"], superseded_class=doc.get("class"),
                              superseded_reason=reason, host_env_before_basis=C384_BEFORE_BASIS,
                              at=co.utc_stamp(self.clock())),
                    **{"class": cls["class"]})
        if spec["kind"] == "makeup" and cls["state"] not in VALID_STATES:
            body["not_run"] = not_run(root, self.canon)
        sealed = ph.seal(body)
        atomic_text(path, json.dumps(sealed, indent=1, sort_keys=True) + "\n")
        self.log(f"{name}: C384: the C360 host INVALID is superseded: state {cls['state']}"
                 + (f" ({cls['reason']})" if cls["reason"] else "") + f" from its records; the original is {C384_SUPERSEDED} "
                 f"(sha256 {doc['sha256'][:16]}); host changes during the leg: " + "; ".join(body["host_env_during"]))
        self.c384_entry(entry, sealed)

    def c384_check_kept(self, name, kept, file_sha, create=None):
        """`leg.c360.json` is the original's bytes (`file_sha`); installed from `create` when absent (`install_kept`: never a
        partial file at its path). Anything else stops (rc 1): never overwritten, never followed."""
        if not os.path.lexists(kept):
            if create is None:
                raise Stop(1, f"STOP: {name}/{C384_SUPERSEDED} (the superseded original) is missing")
            install_kept(kept, create)
        tmp = kept_temp(kept)
        if os.path.lexists(tmp):                       # a crash between the link and the temp's removal left it
            os.unlink(tmp)
        try:
            ok = not os.path.islink(kept) and kept.is_file() and hashlib.sha256(kept.read_bytes()).hexdigest() == file_sha
        except OSError:
            ok = False
        if not ok:
            raise Stop(1, f"STOP: {name}/{C384_SUPERSEDED} exists and is not the leg's recorded leg.json (never overwritten)")

    def c384_entry(self, entry, doc):
        """The sequence entry follows the superseding leg record (state, reason, host changes, the supersession)."""
        entry["state"] = doc["state"]
        if doc.get("reason"):
            entry["reason"] = doc["reason"]
        else:
            entry.pop("reason", None)
        if doc.get("host_env_during"):
            entry["host_env_during"] = list(doc["host_env_during"])
        entry["c384"] = dict(superseded_sha256=doc["c384"]["superseded_sha256"], superseded=C384_SUPERSEDED,
                             at=doc["c384"].get("at"))
        self.save()

    def process(self, spec):
        latest = (self.entries(spec["name"]) or [None])[-1]
        replace = getattr(self.a, "rerun_attempt", None)
        if replace is None:                 # a replayed command never reruns an attempt a rerun already created
            rerun = spec["name"] in (self.a.rerun or []) and not any(
                r["leg"] == spec["name"] and latest and r["attempt"] == latest["attempt"] for r in self.seq["reruns"])
        else:                               # S28-P29 (C381): a further rerun names the attempt it replaces, once
            rerun = spec["name"] in (self.a.rerun or []) and bool(latest) and latest["attempt"] == replace and not any(
                r["leg"] == spec["name"] and r["attempt"] == replace + 1 for r in self.seq["reruns"])
        if latest and not rerun:
            if latest["state"] == "RUNNING":
                raise Stop(1, f"STOP: {spec['name']}.a{latest['attempt']} was RUNNING when the sequencer last stopped (the operator decides)")
            self.c384_supersede(spec, latest)          # S29 H5: a C360 host-INVALID leg takes the state its records give
            done = latest["state"] in VALID_STATES or latest["state"] == spec["expect"]
            if not done:
                raise Stop(1, f"STOP: {spec['name']}.a{latest['attempt']} is {latest['state']}; a rerun is an operator decision "
                              f"(--rerun {spec['name']} --rerun-reason TEXT)")
            if not self.harvested(latest):
                self.harvest(spec, latest)
            else:
                self.log(f"{spec['name']}.a{latest['attempt']}: {latest['state']}, harvested, skipped")
            return self.after_leg(spec, latest)
        if rerun and latest:
            self.seq["reruns"].append(dict(leg=spec["name"], attempt=latest["attempt"] + 1, reason=self.a.rerun_reason,
                                           at=co.utc_stamp(self.clock())))
        entry = self.run_leg(spec)
        self.after_leg(spec, entry)

    # -- the command
    def legs(self):
        if self.a.cmd == "rehearsal":
            return list(self.table["rehearsal"])
        if self.a.cmd == "makeup":
            return list(self.table["makeup"])
        return list(self.table["run"])

    def run(self):
        self.load_records()
        if self.a.cmd == "makeup":
            self.canon = canonical_occurrences(read_occurrences(self.a.occurrences, s3=self.lever == "kv"), s3=self.lever == "kv")
        if (self.out / OVERRUN_FILE).exists():
            raise Stop(1, f"STOP: {OVERRUN_FILE} exists: the operator removes it to resume")
        self.host_env_start()                                # C360 / S26 §2: the baseline, before the first leg
        self.emails = tuple(self.ops.operator_emails())
        if not self.emails:                                  # spec 16.8: never "no operator address" (unset user.email, a failing read)
            raise fz.Refusal("the operator email set is empty (the main checkout's `git config user.email` is unset or unreadable): "
                             "the harvest cannot refuse the operator's address")
        if self.a.cmd in ("run", "makeup"):
            self.verify_existing_amendment()
        self.republish_dossiers()
        if self.a.cmd == "rehearsal":
            self.identity = self.rehearsal_identity()
        self.log(f"sequencer {self.a.cmd}: {len(self.legs())} legs, out-base {self.out}")
        for spec in self.legs():
            self.process(spec)
            if getattr(self.a, "through", None) and spec["name"] == self.a.through:
                self.host_env_final()
                self.publish_run_files_or_stop()
                self.log(f"through {spec['name']}: stopping as asked")
                return 0
        self.host_env_final()
        self.publish_run_files_or_stop()
        self.log("DONE: every leg of this command is complete")
        return 0

    def publish_run_files_or_stop(self):
        """The frozen records and `sequence.json` are published before the sequence reports success: a failure is exit code 4."""
        try:
            self.publish_run_files()
        except Exception as exc:  # noqa: BLE001
            self.run_files_done = True                       # not retried (and logged twice) by the exit path
            self.run_files_failed = True
            raise Stop(4, f"STOP: the run files were NOT published ({type(exc).__name__}: {exc}); a rerun of the same command retries") from None

    def rehearsal_identity(self):
        """The manifest's recorded probe identity (flat keys or an `identity` object); one that records none takes
        `ops.identity(off_worktree)` (spec 16.8); the date is the manifest's, checked against `--frozen-prompt-date`."""
        nested = self.base.get("identity") if isinstance(self.base.get("identity"), dict) else {}
        found = {k: self.base.get(k) or nested.get(k) for k in ("probe_code_sha256", "scaffold_policy_sha256")}
        if not all(found.values()):
            live = self.ops.identity(self.worktrees[self.arms[0]])
            found = {k: live[k] for k in found}
        return dict(found, frozen_prompt_date=self.base["frozen_prompt_date"])

    def publish_run_files(self):
        if self.run_files_done or self.a.cmd == "rehearsal" or not self.seq["harvested"]:
            return
        if self.corpus == "tg2":
            paths = self.run_file_paths()
        else:
            paths = sorted(p for p in self.record_dir.iterdir() if p.is_file()) + self.host_env_paths() + [self.out / SEQUENCE_FILE]
        self.ops.publish_run_files(paths, emails=self.emails)
        self.run_files_done = True


def read_occurrences(path, s3=False) -> list:
    try:
        lines = [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
    except (OSError, ValueError):
        raise fz.Refusal(f"--occurrences {Path(path).name} is missing, unreadable or not JSON lines") from None
    if not lines:
        raise fz.Refusal(f"--occurrences {Path(path).name} holds no occurrences")
    try:
        canonical_occurrences(lines, s3=s3)
    except (KeyError, ValueError, TypeError) as exc:
        raise fz.Refusal(f"--occurrences {Path(path).name}: {exc}") from None
    return lines


# ----------------------------------------------------------------------------------------------- the box's ops
class BoxSeqOps(fz.BoxOps):
    """The real `ops`: subprocess launch (nothing inherited: `pass_fds=()`, stdin closed, output to a file), start-time identity
    (`ChainOps.create_time`), `pmset` power, and the harvest / publication of `bench.p426_harvest` (s9)."""

    def __init__(self, workdir, *, main_root, evidence_stage, historical_walls=None, build_inputs=None, lever="mtp", corpus="tg1"):
        super().__init__(workdir, build_inputs, historical_walls, corpus=corpus)
        self.main_root, self.evidence_stage = Path(main_root), Path(evidence_stage)
        self._procs = {}
        self._pos = None                                     # the positives' serving session (M76 B4b-1), when one is open
        self.lever = lever                                   # M76 B3: kv publishes below benchmark/results/m76/
        self.corpus = corpus                                # M76 B4b-1: the tg2 legs publish below benchmark/results/m76/wave2.tg2/
        self.namespace = TG2_NAMESPACE if corpus == "tg2" else "wave2"

    def launch(self, argv, *, cwd, pass_fds):
        if "--out-root" in argv:
            out = Path(argv[argv.index("--out-root") + 1])
            log = out.parent / "logs" / (out.name + ".stdout")             # spec 16.8: never inside the fresh out-root
        else:
            log = Path(argv[argv.index("--out") + 1]).with_name("watcher.stdout")
        log.parent.mkdir(parents=True, exist_ok=True)
        env = None
        if len(argv) > 1 and Path(argv[1]).name == "bench_watch.py":   # S26-P8 / P444: the watcher imports `bench` via PYTHONPATH
            bench_dir = str(Path(cwd).resolve() / "benchmark")
            env = dict(os.environ, PYTHONPATH=os.pathsep.join(p for p in (bench_dir, os.environ.get("PYTHONPATH")) if p))
        with open(log, "ab") as f:
            proc = subprocess.Popen(argv, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT,
                                    pass_fds=tuple(pass_fds), close_fds=True, env=env)
        self._procs[proc.pid] = proc
        return SimpleNamespace(pid=proc.pid, start=co.default_create_time(proc.pid), argv=list(argv))

    def alive(self, pid, start):
        proc = self._procs.get(pid)
        if proc is not None and proc.poll() is not None:
            return False
        try:
            return co.default_create_time(pid) == start
        except Exception:  # noqa: BLE001  (no such process)
            return False

    def wait(self, handle):
        proc = self._procs.get(handle.pid)
        return proc.wait() if proc is not None else 0

    def host_env(self):
        """C360 / S26 §2: the live host-environment fingerprint (`bench.host_env.fingerprint_for_run`)."""
        from . import host_env
        return host_env.fingerprint_for_run()

    def power(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "m1"))
        try:
            import bench_watch
        finally:
            sys.path.pop(0)
        return bench_watch.pmset_power()

    def operator_emails(self):
        """The main checkout's `git config user.email`; unset, empty or unreadable is a refusal, never an empty set (spec 16.8)."""
        try:
            run = subprocess.run(["git", "-C", str(self.main_root), "config", "user.email"], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            raise fz.Refusal("the operator email cannot be read: `git config user.email` failed in the main checkout") from None
        emails = tuple(x for x in run.stdout.split() if x) if run.returncode == 0 else ()
        if not emails:
            raise fz.Refusal("the operator email is unset or unreadable: `git config user.email` of the main checkout gave none")
        return emails

    def harvest_path(self, attempt):
        if self.lever == "kv":
            return self.main_root / "benchmark/results/m76" / getattr(self, "namespace", "wave2") / attempt
        return self.main_root / "benchmark/results/p426/wave2" / attempt                  # the destination directory (spec 16.8)

    def harvest(self, root, *, emails):
        argv = [sys.executable, "-m", "bench.p426_harvest", "wave2", "--leg-root", str(root), "--main-root", str(self.main_root),
                "--evidence-stage", str(self.evidence_stage)]
        if self.lever == "kv":
            argv += ["--lever", "kv"]
        if getattr(self, "corpus", "tg1") == "tg2":
            argv += ["--namespace", TG2_NAMESPACE]
        for e in emails:
            argv += ["--operator-email", e]
        run = subprocess.run(argv, cwd=str(Path(__file__).resolve().parents[1]), capture_output=True, text=True, timeout=3600,
                             stdin=subprocess.DEVNULL)
        path = self.harvest_path(Path(root).name) / "HARVEST.json"
        sha = hashlib.sha256(path.read_bytes()).hexdigest() if run.returncode == 0 and path.is_file() else None
        message = next((ln.strip() for ln in run.stderr.splitlines() if ln.startswith(("REFUSED:", "ERROR:"))), "")
        notes = [ln.strip() for ln in run.stderr.splitlines() if ln.startswith("UNRECOGNISED")]     # S29 P6b
        return dict(rc=run.returncode if sha or run.returncode else 1, harvest_json=str(path), harvest_sha256=sha, message=message,
                    notes=notes)

    def _scrub(self, emails, secrets=None):
        from . import p426_harvest
        host = socket.gethostname()
        return p426_harvest, p426_harvest.Scrub(workdir=self.wd, repo=self.main_root, home=Path.home(), user=getpass.getuser(),
                                                hosts=tuple({host, host.split(".")[0]}), emails=tuple(emails),
                                                secrets=dict(secrets or {}))

    env_files = ()                                       # the arm worktrees' `.env` files (set by `main`), a credential source like the harvest's

    def _credentials(self):
        """The same in-memory credential values the leg harvest scans for (same sources); never logged."""
        from . import p426_harvest
        return p426_harvest.load_credentials(environ=os.environ, home=Path.home(), env_files=self.env_files)

    def publish_dossier(self, path, *, emails):
        mod, scrub = self._scrub(emails, secrets=self._credentials())
        publish = mod.publish_dossier_kv if self.lever == "kv" else mod.publish_dossier
        ns = {"namespace": TG2_NAMESPACE} if getattr(self, "corpus", "tg1") == "tg2" else {}
        return publish(path, main_root=self.main_root, evidence_stage=self.evidence_stage, scrub=scrub, **ns)

    def publish_run_files(self, paths, *, emails):
        mod, scrub = self._scrub(emails, secrets=self._credentials())
        publish = mod.publish_run_files_kv if self.lever == "kv" else mod.publish_run_files
        ns = {"namespace": TG2_NAMESPACE} if getattr(self, "corpus", "tg1") == "tg2" else {}
        return publish(paths, main_root=self.main_root, scrub=scrub, **ns)

    # -- M76 B4b-1: the tg2 positives on the box (E6): one lean serving session on the reference arm's worktree
    def positives_session(self, worktree, *, frozen_prompt_date):
        """The lean router on `worktree`, the A4 gate under the tg2 scaffold and the worker loaded, as for any leg (`ChainOps`,
        MTP ON); torn down (unload, own router stopped) on exit."""
        from contextlib import contextmanager

        @contextmanager
        def session():
            wt = Path(worktree)
            out_root = self.wd / "m65" / "inject" / f"positives-{time.strftime('%Y%m%dT%H%M%S')}"
            out_root.mkdir(parents=True, exist_ok=False)
            log = co.RunLog(out_root / "RUNLOG.md")
            served = wt / "main_models.yaml"
            ops = co.ChainOps(wt, self.wd, served, log, predictor="mtp", out_root=out_root, registry=served)
            self._pos = dict(ops=ops, wt=wt, out_root=out_root, date=frozen_prompt_date)
            try:
                if ops.listeners():
                    raise fz.Refusal(":8000 already has a listener: the positives start their own lean router")
                ops.start_router()
                ops.load(ENTRY)
                self._pos["receipt"] = ops.a4_gate(ENTRY, "positives", scaffold="opencode-v2-web-tg2")
                yield self
            finally:
                try:
                    ops.stop_stack()
                finally:
                    self._pos = None
        return session()

    def positive_grade(self, lang, item, variant):
        """(a) The pilot item's stub or reference graded through `Tg2Corpus.grade` (docker, no GPU), outside TMPDIR."""
        import shutil
        from . import corpus_tg2
        from . import tg2_materialize as mat
        corpus = corpus_tg2.Tg2Corpus()
        slug = item.split("/", 1)[1]
        base = self.wd / "m65" / "positives" / f"{variant}-{lang}-{os.getpid()}-{int(time.time())}"
        prepared = corpus.prepare(item, base / "work" / slug)
        if variant == "reference":
            mat.apply_reference(corpus.polyglot_root(), mat.read_plan(corpus.polyglot_root(), lang, slug), prepared.work)
        private = base / "run" / "grading-private"
        private.mkdir(parents=True)
        try:
            with corpus.snapshot(prepared.work, private, 0) as snap:
                out = corpus.grade(snap, prepared, private, None, base / "keep", 1, 0, True)
        finally:
            shutil.rmtree(base / "work", ignore_errors=True)
        return dict(outcome=out.phases[0]["outcome"], passed=out.passed, failing=out.failing, leaves=len(out.leaves))

    def positive_inject(self, lang, item, kind, *, seed, attempt):
        """(b) One `run_tg2_probe.py --tg2-inject <kind>` run of the pilot item (out under `$STACK_WORKDIR/m65/inject/`, the
        file name `inject_verify` reads: `<kind>.attempt<n>.jsonl`)."""
        pos = self._pos
        if not pos:
            raise fz.Refusal("an inject positive runs only inside the positives' serving session")
        run = pos["out_root"] / lang
        run.mkdir(parents=True, exist_ok=True)
        stem = f"{kind}.attempt{attempt}"                     # an inject run's file (as `run_inject.py` names it), not a chain row
        out = run / (stem + ".jsonl")
        wt = pos["wt"]
        argv = [str(wt / ".venv-bench/bin/python"), str(wt / fz.TG2_PROBE_ENTRY), "--model", ENTRY, "--items",
                item.split("/", 1)[1], "--lang", lang, "--seed-base", str(seed), "--scaffold", "opencode-v2-web-tg2",
                "--expect-items", item, "--a4-v2-receipt", str(pos["receipt"]), "--sampling-profile", "deployed",
                "--frozen-prompt-date", pos["date"], "--tg2-inject", kind, "--out", str(out)]
        done = subprocess.run(argv, cwd=str(wt), env=pos["ops"].env_base(), stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=POSITIVE_TIMEOUT_S)
        try:
            manifest = json.loads(out.with_suffix(".manifest.json").read_text())
        except (OSError, ValueError):
            manifest = {}
        if done.returncode != 0:
            return dict(transport_abort=bool(manifest.get("transport_abort")) or not out.exists(), run=str(run), rc=done.returncode)
        sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest() if Path(p).is_file() else None      # noqa: E731
        return dict(transport_abort=False, run=str(run), rc=0, row_sha256=sha(out),
                    evidence_sha256=sha(out.with_suffix(".manifest.json")))

    def inject_verify(self, run, kind):
        """`m62/inject_verify.py --scaffold opencode-v2-web-tg2 --run <dir> --kind <k>`: the kind's existing causal predicate;
        returns the retained attempt's verdict string (`PASS`, `not_observed:kill`, `FAIL:…`; S26 erratum 3)."""
        return self.inject_verify_result(run, kind)["verdict"]

    def inject_verify_result(self, run, kind):
        """S26 §4: {verdict (the retained attempt's verdict string), result (the RESULT line), rc}. `PASS` needs exit 0; a
        run whose stdout names no verdict is `FAIL:no_verdict:rc<n>`."""
        wt = self._pos["wt"] if self._pos else Path(__file__).resolve().parents[2]
        done = subprocess.run([str(wt / ".venv-bench/bin/python"), str(wt / "benchmark/m62/inject_verify.py"), "--scaffold",
                               "opencode-v2-web-tg2", "--run", str(run), "--kind", kind, "--workdir", str(self.wd)],
                              cwd=str(wt), capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL)
        row, result = parse_inject_verify(done.stdout, kind)
        if row is None:
            verdict = f"FAIL:no_verdict:rc{done.returncode}"
        elif row in ("PASS", fz.PASS_NO_INFLIGHT) and done.returncode != 0:     # S27 §4.3: both need exit 0
            verdict = f"FAIL:inconsistent:{row}:rc{done.returncode}"
        else:
            verdict = row
        return dict(verdict=verdict, result=result, rc=done.returncode)

    def notify(self, message):
        print(message, file=sys.stderr, flush=True)


# ----------------------------------------------------------------------------------------------- CLI
class RefusingParser(argparse.ArgumentParser):
    def error(self, message):
        raise fz.Refusal(message)


def parse_args(argv):
    ap = RefusingParser(prog="bench.p426_wave2", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    pos = sub.add_parser("positives", help="M76 B4b-1: the tg2 positives record (on the reference arm)")
    pos.add_argument("--corpus", required=True, choices=("tg2",))
    pos.add_argument("--lever", required=True, choices=("kv",))
    pos.add_argument("--arm-worktree", action="append", default=[], help="<arm>=<worktree> of the reference arm (once)")
    pos.add_argument("--out", required=True, help="<run>/positives.json (exclusive-created)")
    pos.add_argument("--frozen-prompt-date", required=True, metavar="'Www Mmm DD YYYY'")
    pos.add_argument("--main-root", default=None)
    for name in ("run", "makeup", "rehearsal"):
        p = sub.add_parser(name)
        p.add_argument("--corpus", default="tg1", choices=("tg1", "tg2"),
                       help="M76 B4b-1 (lever kv): tg2 = the tg2 legs (run / rehearsal; no make-up)")
        if name == "run":
            p.add_argument("--recheck-ack", default=None, metavar="SHA256",
                           help="M76 B4b-1: the sealed re-check 1 record's sha256 acknowledged (resume after rc 5)")
            p.add_argument("--recheck-ack-by", default=None, choices=RECHECK_ACK_ACTORS,
                           help="S29 K2: who acknowledges (required with --recheck-ack)")
            p.add_argument("--recheck-ack-ruling", default=None, metavar="RULING",
                           help="S29 K2: the ruling the acknowledgement rests on, e.g. C383 (required with --recheck-ack)")
        p.add_argument("--worktree-off", default=None, help="lever mtp (required)")
        p.add_argument("--worktree-on", default=None, help="lever mtp (required)")
        p.add_argument("--lever", default="mtp", choices=("mtp", "kv"), help="M76 B3: kv = a KV pair, both MTP ON")
        p.add_argument("--pair", default=None, help="lever kv: <reference>,<treatment>")
        p.add_argument("--arm-worktree", action="append", default=[], help="lever kv: <arm>=<worktree> (each arm of the pair)")
        p.add_argument("--out-base", required=True)
        p.add_argument("--pause-file", default=None, help="default <out-base>/PAUSE")
        p.add_argument("--rerun", action="append", default=[], metavar="LEG", help="the operator's labelled rerun: a new attempt of LEG")
        p.add_argument("--rerun-reason", default=None)
        p.add_argument("--rerun-attempt", type=int, default=None, metavar="N",
                       help="S28-P29: a further rerun replaces attempt N of the one --rerun leg (N = its latest attempt)")
        p.add_argument("--main-root", default=None, help="default ops: the checkout the harvest publishes into")
        p.add_argument("--evidence-stage", default=None, help="default ops: the evidence stage directory")
        p.add_argument("--historical-walls", default=None, metavar="JSON", help="default ops: the historical per-item walls")
        if name != "rehearsal":
            p.add_argument("--record-dir", required=True)
        if name == "run":
            p.add_argument("--through", default=None, metavar="LEG")
        if name == "makeup":
            p.add_argument("--occurrences", required=True)
        if name == "rehearsal":
            p.add_argument("--manifest", required=True)
            p.add_argument("--frozen-prompt-date", required=True, metavar="'Www Mmm DD YYYY'",
                           help="must be the date the rehearsal manifest recorded")
    return ap.parse_args(argv)


def _check_lever_args(a):
    """`a.arms` / `a.worktrees` of the lever: mtp `--worktree-off` / `--worktree-on`; kv `--pair` + `--arm-worktree` (M76 B3)."""
    a.lever = getattr(a, "lever", "mtp")
    if a.lever == "mtp":
        if getattr(a, "pair", None) or getattr(a, "arm_worktree", None):
            raise fz.Refusal("--pair / --arm-worktree are lever kv flags")
        if not a.worktree_off or not a.worktree_on:
            raise fz.Refusal("the following arguments are required: --worktree-off, --worktree-on")
        return
    from . import p426_plan

    if a.worktree_off or a.worktree_on:
        raise fz.Refusal("--worktree-off / --worktree-on are lever mtp flags (lever kv: --arm-worktree <arm>=<path>)")
    try:
        pair = p426_plan.check_kv_pair(*(a.pair or "").split(",", 1)) if a.pair and "," in a.pair else None
    except ValueError as exc:
        raise fz.Refusal(str(exc)) from None
    if pair is None:
        raise fz.Refusal("--lever kv needs --pair <reference>,<treatment>")
    if "v" in pair:   # erratum v1.2: stage 4 (V) is not in B3 — refused at preflight, before any leg
        raise fz.Refusal(f"the pair {list(pair)} names V: stage 4 (V vs X / N16) is not in B3 — its V-only / X-reuse / sentinel "
                         "workflow is planned before stage 4 (S23-P49); nothing runs")
    trees = {}
    for v in a.arm_worktree:
        arm, sep, path = v.partition("=")
        if not sep or arm not in pair or arm in trees or not path:
            raise fz.Refusal(f"--arm-worktree {v!r} is not <arm>=<path> for an arm of the pair (once each)")
        trees[arm] = Path(path)
    if set(trees) != set(pair):
        raise fz.Refusal(f"--arm-worktree names {sorted(trees)}, the pair is {list(pair)}")
    a.arms, a.worktrees = pair, trees


def check_positives_args(a):
    """`positives`: lever kv, tg2, exactly one `--arm-worktree <arm>=<path>` of a KV arm."""
    trees = {}
    for v in a.arm_worktree:
        arm, sep, path = v.partition("=")
        if not sep or arm not in fz.KV_ARMS or arm in trees or not path:
            raise fz.Refusal(f"--arm-worktree {v!r} is not <arm>=<path> for a KV arm (once)")
        trees[arm] = Path(path)
    if len(trees) != 1 or set(trees) != {fz.TG2_PAIR[0]}:        # change review L6: the tg2 pair's reference, N16
        raise fz.Refusal(f"positives run on the tg2 pair's reference arm {fz.TG2_PAIR[0]} only: give exactly one "
                         f"--arm-worktree {fz.TG2_PAIR[0]}=<path>")
    if not datefreeze.valid(a.frozen_prompt_date):
        raise fz.Refusal("--frozen-prompt-date must be 'Www Mmm DD YYYY'")
    a.worktrees = trees


RECHECK_ACK_ACTORS = ("operator", "designer")


def recheck_ack_actor(a):
    """S29 K2: `(actor, ruling)` of a re-check acknowledgement; refused unless both are given (actor operator / designer, ruling
    non-empty). Never defaults an actor."""
    actor, ruling = getattr(a, "recheck_ack_by", None), getattr(a, "recheck_ack_ruling", None)
    if actor not in RECHECK_ACK_ACTORS or not isinstance(ruling, str) or not ruling.strip():
        raise fz.Refusal("--recheck-ack needs --recheck-ack-by operator|designer and --recheck-ack-ruling <ruling> "
                         "(an acknowledgement names who gave it and on what ruling)")
    if any(unicodedata.category(c)[0] == "C" or unicodedata.category(c) in ("Zl", "Zp") for c in ruling):
        raise fz.Refusal("--recheck-ack-ruling carries a line break or control character (the ruling is one log line)")
    return actor, ruling.strip()


def _recorded_ack(a):
    """S29 K2 (fix 1): True when `sequence.json` under `--out-base` already records an acknowledgement of `--recheck-ack`'s sha256
    for the gate whose sealed record has that sha256 (the legacy S29-P13 resume); False when it cannot be read."""
    try:
        rechecks = read_sequence(a.out_base).get("rechecks")
    except (OSError, ValueError, TypeError, AttributeError):
        return False
    return isinstance(rechecks, dict) and any(
        isinstance(rec, dict) and rec.get("sha256") == a.recheck_ack and isinstance(rec.get("ack"), dict)
        and rec["ack"].get("sha256") == a.recheck_ack for rec in rechecks.values())


def _check_recheck_ack_args(a):
    """S29 K2: `--recheck-ack`, `--recheck-ack-by` and `--recheck-ack-ruling` come together or not at all; `--recheck-ack` alone
    only resumes an acknowledgement `sequence.json` already records for that gate."""
    given = [getattr(a, k, None) is not None for k in ("recheck_ack", "recheck_ack_by", "recheck_ack_ruling")]
    if any(given) and not given[0]:
        raise fz.Refusal("--recheck-ack-by / --recheck-ack-ruling need --recheck-ack <sha256>")
    if given[0] and not (given == [True, False, False] and _recorded_ack(a)):
        recheck_ack_actor(a)


def check_args(a, wd):
    _check_recheck_ack_args(a)
    _check_lever_args(a)
    kv = a.lever == "kv"
    tg2 = getattr(a, "corpus", "tg1") == "tg2"
    if tg2 and (not kv or a.cmd == "makeup"):
        raise fz.Refusal("--corpus tg2 is for `run` / `rehearsal` of lever kv (the tg2 legs have no make-up)")
    if tg2:
        fz.check_tg2_pair(a.arms)                                # change review L6
    base = Path(a.out_base).resolve()
    reh = fz.TG2_REHEARSAL_DIR if tg2 else KV_REHEARSAL_DIR if kv else REHEARSAL_DIR
    scratch = KV_WAVE2_DIR.rsplit("/", 1)[0] if kv else "p426"
    rehearsal_dir = (Path(wd) / reh).resolve()
    inside = base == rehearsal_dir or rehearsal_dir in base.parents
    if a.cmd == "rehearsal" and not inside:
        raise fz.Refusal(f"--out-base must lie under $STACK_WORKDIR/{reh}/")
    if a.cmd != "rehearsal" and (inside or (Path(wd) / scratch).resolve() not in base.parents):
        raise fz.Refusal(f"--out-base must lie under $STACK_WORKDIR/{scratch}/ and not in {reh}/")
    table = (kv_tg2_legs(*a.arms) if tg2 else kv_legs(*a.arms)) if kv else dict(run=RUN_LEGS, makeup=MAKEUP_LEGS,
                                                                                 rehearsal=REHEARSAL_LEGS)
    names = [s["name"] for s in table[a.cmd]]
    for flag in a.rerun:
        if flag not in names:
            raise fz.Refusal(f"--rerun {flag!r} is not a leg of this command ({', '.join(names)})")
    if a.rerun and not a.rerun_reason:
        raise fz.Refusal("--rerun needs --rerun-reason (a rerun is labelled)")
    if getattr(a, "rerun_attempt", None) is not None and (len(a.rerun or []) != 1 or a.rerun_attempt < 1):
        raise fz.Refusal("--rerun-attempt N names a positive attempt of exactly one --rerun leg")
    if a.cmd == "run" and a.through is not None:
        by_number = {str(s["n"]): s["name"] for s in table["run"]}
        if a.through not in names and a.through not in by_number:
            raise fz.Refusal(f"--through {a.through!r} is neither a leg name nor a number 1-{len(table['run'])}")
        a.through = by_number.get(a.through, a.through)


def frozen_env_files(a, wd):
    """The arm worktrees' `.env` files named by the FROZEN record (`v8_base.json` of `--record-dir`, or the rehearsal manifest) — the
    credential sources of the leg harvest — never the `--worktree-*` arguments. [] when the record cannot be read."""
    try:
        record = Path(a.manifest) if a.cmd == "rehearsal" else Path(a.record_dir) / "v8_base.json"
        doc = json.loads(record.read_text())
        out = []
        for arm in (doc.get("arms") if doc.get("lever") == "kv" else ("off", "on")):     # M76: the KV pair's worktrees
            value = doc.get(f"{arm}_worktree")
            tree = fz.expand(value, wd) if value else None
            if tree:
                env = Path(tree) / ".env"
                if env.exists() or os.path.islink(env):
                    out.append(env)
        return out
    except (OSError, ValueError, AttributeError, TypeError):
        return []


def build_box_ops(a, wd):
    """The real ops of one command: the main checkout, the evidence stage and the credential sources of the frozen record."""
    scratch = Path(a.out_base) / "scratch"
    main_root = Path(a.main_root) if a.main_root else (scratch / "main" if a.cmd == "rehearsal" else Path(__file__).resolve().parents[2])
    ops = BoxSeqOps(wd, main_root=main_root, evidence_stage=a.evidence_stage or scratch / "evidence", historical_walls=a.historical_walls,
                    lever=getattr(a, "lever", "mtp"), corpus=getattr(a, "corpus", "tg1"))
    ops.env_files = tuple(frozen_env_files(a, wd))
    return ops


def main(argv=None, *, ops=None, clock=None, sleep=None):
    clock, sleep = clock or time.time, sleep or time.sleep
    held = None
    try:
        a = parse_args(sys.argv[1:] if argv is None else argv)
        wd = getattr(ops, "wd", None) or os.environ.get("STACK_WORKDIR")
        if not wd:
            raise fz.Refusal("$STACK_WORKDIR is not set")
        if a.cmd == "positives":                             # M76 B4b-1: the tg2 positives record (its own command)
            check_positives_args(a)
            if ops is None:
                ops = BoxSeqOps(wd, main_root=Path(a.main_root) if a.main_root else Path(__file__).resolve().parents[2],
                                evidence_stage=Path(wd) / "m65" / "positives" / "evidence", lever="kv", corpus="tg2")
            try:
                held = pl.acquire("sequencer", wd)
            except pl.LockRefused as exc:
                raise fz.Refusal(str(exc)) from None
            return cmd_positives(a, ops, wd, clock)
        check_args(a, wd)
        if ops is None:
            ops = build_box_ops(a, wd)
        walls = a.cmd == "run" and getattr(a, "corpus", "tg1") != "tg2"     # the tg2 amendment takes the pilot walls only
        fz.need(ops, *SEAMS, *(("historical_walls",) if walls else ()))      # spec 16.8: a refusal, before the lock
        try:
            held = pl.acquire("sequencer", wd)
        except pl.LockRefused as exc:
            raise fz.Refusal(str(exc)) from None
        seq = Sequencer(a, ops, clock, sleep, wd)
        publish_failed = False
        try:
            rc = seq.run()
        except Stop as stop:
            seq.log(str(stop))                               # the original stop reason stays in the log
            rc = stop.rc
        except fz.Refusal:
            raise
        finally:
            try:
                seq.publish_run_files()
            except Exception as exc:  # noqa: BLE001
                publish_failed = True
                seq.log(f"run files NOT published: {type(exc).__name__}: {exc}")
        if publish_failed or seq.run_files_failed:           # an attempted run-file publication that failed is exit 4, whatever stopped
            rc = 4
        return rc
    except fz.Refusal as exc:
        print("REFUSED: " + " ".join(str(exc).split()), file=sys.stderr)
        return 2
    finally:
        if held is not None:
            held.release()


if __name__ == "__main__":
    sys.exit(main())
