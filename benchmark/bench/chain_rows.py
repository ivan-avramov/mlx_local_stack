"""P371 (plan 4 A8 / A9, R6 R7 R18 R19 R24 R25): THE chain-row loader (the only reader of chain out-root rows once the
consumers below are migrated). Pure file reading: no writer, no client, no process module.

Layout. One IMMUTABLE rows file per leg INVOCATION: `<session>/<stem>.L<leg>.<phase>.a<n>.jsonl` (+ `.manifest.json`),
phase in pilot / full / block / rerun / retry. `chain.json.progress` is the inventory (fsync'ed by the chain before any
next action); an unregistered rows file is an error. Record shapes (`validate_progress`):

    progress.loads[]        {load, status pending|running|done|archived, load_gen, workers[], cursor{leg_index, phase}}
    progress.invocations[]  {leg_key, phase, attempt, worker_n, file, manifest, status, expected_slots, accepted_slots,
                             sha256, load_gen, slot_base, [rerun_index], [hook_stop], [status archived after restart_load]}
                            status running | validated | partial_incident | hook_stopped | quarantined | archived
    progress.slot_attempts[] {slot, rerun_index, disposition accepted|cheat|unclear|exhausted, load_gen,
                             [output_tokens], [status archived]}        (persisted BEFORE `.stop`, so cheat tokens survive)
    progress.pre_spawn[]    {slot, disposition pre_spawn_incident, cause, load_gen, [status archived]}
    dnf[]                   chain.json copy of the synthetic transport_dnf rows (sidecar `<stem>.dnf.jsonl` must equal it)

A slot is `slot_for(slot_base, row id)` = `epoch|arm|pick|session|lang|item` (the M64 slot key). Counted records
(validated / partial_incident / hook_stopped) are sha256-re-checked and their rows must equal `accepted_slots`; running /
quarantined / archived records are never counted (an archived record's moved file is not re-hashed, R24). Per slot the
scored attempt is the LATEST attempt (by re-run index): `accepted` / `exhausted` -> scored (exhausted = strict FAIL,
P201); `cheat` -> a re-run is pending (at most 2, P202; the attempt's row and tokens stay attempt records and are never
scored); `unclear` -> blocked for the operator. A hook-stopped record's prefix BEFORE the stopped slot is accepted and
never re-run. `legacy(root, layout)` is the read-only mode for stored chains (c147 / m63: `<session>/<stem>.jsonl`; m64:
base + `.w<n>` segments + `.dnf.jsonl`).

Consumers to migrate (phase 3) -- every module under benchmark/ (tests excluded) that reads or lays out chain out-root
rows today; none is migrated by phase 1:
 - benchmark/bench/chain_ops.py  `ChainOps.rows` and `validate_leg` read the probe's rows file (`pg.load_rows`)
 - benchmark/chains/c147/run_tg1_chain.py  `session_dir`, `archive_block`, `archive_stopped`, per-step `<stem>.jsonl`, resume
 - benchmark/chains/m64/run_m64_chain.py  `scored_ids`, `segment_out`, `archive_load`, the `.dnf.jsonl` sidecar, `.w<n>`
 - benchmark/chains/c147/fake_probe.py  writer fake of the probe's rows contract (follows the new layout)
 - benchmark/chains/m64/fake_arm_probe.py  writer fake of the M64 probe's rows contract
 - benchmark/chains/c147/run_inject.py  inject attempt rows (a non-chain probe run: allow-list candidate)
 - benchmark/m62/inject_verify.py  reads `<kind>.attempt<n>.jsonl` of inject runs (allow-list candidate)
 - benchmark/chains/c147/drive_chain.sh  launcher: out-root `c147/` and its `chain.json`
 - benchmark/chains/c147/drive_m63.sh  launcher: out-root `m63/` and its `chain.json`
 - benchmark/chains/c147/launchers/launch_tg1.sh  launcher: out-root and `chain.json`
 - benchmark/results/p223_tg1/tg1_report.py  reads the copied P223 chain rows (legacy layout)
 - benchmark/results/m63_mtp/m63_report.py  reads the copied M63 chain rows (legacy layout)
 - benchmark/results/c144_base/c144base_report.py  reads the copied c144-base chain rows (legacy layout)
 - benchmark/results/m61_rr/rr_report.py  reads `<model>.rr.<session>.opencode_<lang>.jsonl` of the M61 rerun chain
 - benchmark/chains/m59/m59_report.py  reads the M59 chain out-root (`<session>/<model>.opencode_<lang>.jsonl`)
Non-chain readers that stay as they are: benchmark/chains/m62/run_m62_live.py (its own live rows), benchmark/m1/*
(per-model results rows), the frozen M55 / M59 / M61 runners (their own dirs, legacy).
Probe-level resume readers (phase 2, removed with probe-level resume): benchmark/bench/tg1_runner.py and
benchmark/bench/arm_runner.py (`pg.load_rows(out)`)."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

PHASES = ("pilot", "full", "block", "rerun", "retry")
INVOCATION_STATUSES = ("running", "validated", "partial_incident", "hook_stopped", "quarantined", "archived")
COUNTED_STATUSES = ("validated", "partial_incident", "hook_stopped")
LOAD_STATUSES = ("pending", "running", "done", "archived")
SLOT_DISPOSITIONS = ("accepted", "cheat", "unclear", "exhausted")
MAX_RERUNS = 2                                               # P202
FILE_RE = re.compile(r"\.L\d+\.(?:pilot|full|block|rerun|retry)\.a\d+\.jsonl$")
INV_KEYS = ("leg_key", "phase", "attempt", "worker_n", "file", "manifest", "status", "expected_slots",
            "accepted_slots", "sha256", "load_gen", "slot_base")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
LEGACY_LAYOUTS = ("c147", "m63", "m64")
LEGACY_SKIP_DIRS = ("a4", "incomplete", "stopped", "quarantine", "archive")


class ChainRowsError(RuntimeError):
    """The chain's rows or progress records cannot support scoring (the chain aborts)."""


def _fail(msg):
    raise ChainRowsError(msg)


# ---------------------------------------------------------------- names
def rows_name(stem, leg, phase, attempt):
    if not (type(leg) is int and leg >= 0 and phase in PHASES and type(attempt) is int and attempt >= 1):
        raise ValueError(f"bad leg-attempt file coordinates ({leg!r}, {phase!r}, {attempt!r})")
    return f"{stem}.L{leg}.{phase}.a{attempt}.jsonl"


def manifest_name(stem, leg, phase, attempt):
    return rows_name(stem, leg, phase, attempt)[:-len(".jsonl")] + ".manifest.json"


def slot_for(base, row_id):
    """`base` = `epoch|arm|pick|session|lang`; the slot is that + the bare item name (M64 spec 8.3)."""
    item = row_id.split("/", 1)[1] if "/" in row_id else row_id
    return f"{base}|{item}"


def legacy_slot(session, stem, row_id):
    return f"legacy|{session}|{stem}|{row_id}"


# ---------------------------------------------------------------- reading
def read_rows(path):
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ChainRowsError(f"rows file {path.name} missing or unreadable: {exc}") from exc
    if raw and not raw.endswith(b"\n"):
        _fail(f"torn rows file {path.name}")
    try:
        rows = [json.loads(line) for line in raw.splitlines()]
    except (ValueError, UnicodeError):
        _fail(f"torn/invalid rows file {path.name}")
    if any(not isinstance(r, dict) or "id" not in r for r in rows):
        _fail(f"invalid rows in {path.name}: every row must be an object with an id")
    return rows


# ---------------------------------------------------------------- records
def _is_int(v, minimum=0):
    return type(v) is int and v >= minimum


def validate_progress(doc):
    """Shape checks of the progress document; returns it with the optional sections defaulted."""
    if not isinstance(doc, dict) or not isinstance(doc.get("progress"), dict):
        _fail("chain.json has no progress inventory")
    progress = doc["progress"]
    for name in ("loads", "invocations", "slot_attempts", "pre_spawn"):
        progress.setdefault(name, [])
        if not isinstance(progress[name], list):
            _fail(f"progress.{name} must be a list")
    for load in progress["loads"]:
        if not (isinstance(load, dict) and load.get("status") in LOAD_STATUSES):
            _fail(f"load record malformed: {load!r}")
    for rec in progress["invocations"]:
        if not isinstance(rec, dict) or any(k not in rec for k in INV_KEYS):
            _fail("invocation record lacks " + ", ".join(k for k in INV_KEYS if not isinstance(rec, dict) or k not in rec))
        if rec["phase"] not in PHASES or rec["status"] not in INVOCATION_STATUSES:
            _fail(f"invocation record phase/status invalid: {rec['phase']!r} / {rec['status']!r}")
        if not (_is_int(rec["attempt"], 1) and _is_int(rec["load_gen"]) and _is_int(rec["worker_n"])):
            _fail("invocation record attempt / load_gen / worker_n invalid")
        if not (isinstance(rec["expected_slots"], list) and rec["expected_slots"]
                and isinstance(rec["accepted_slots"], list) and isinstance(rec["file"], str)
                and isinstance(rec["slot_base"], str)):
            _fail("invocation record slots / file / slot_base invalid")
        if rec["sha256"] is not None and not (isinstance(rec["sha256"], str) and HEX64.match(rec["sha256"])):
            _fail("invocation record sha256 must be 64 hex characters or null")
    for rec in progress["slot_attempts"]:
        if not (isinstance(rec, dict) and isinstance(rec.get("slot"), str) and _is_int(rec.get("rerun_index"))
                and rec.get("disposition") in SLOT_DISPOSITIONS and _is_int(rec.get("load_gen"))):
            _fail(f"slot attempt record malformed: {rec!r}")
        if rec["rerun_index"] > MAX_RERUNS:
            _fail(f"slot attempt re-run index {rec['rerun_index']} exceeds the re-run bound {MAX_RERUNS} (P202)")
        if rec["disposition"] == "exhausted" and rec["rerun_index"] != MAX_RERUNS:
            _fail("an exhausted disposition belongs to the last permitted attempt only")
    for rec in progress["pre_spawn"]:
        if not (isinstance(rec, dict) and isinstance(rec.get("slot"), str) and rec.get("disposition") ==
                "pre_spawn_incident" and isinstance(rec.get("cause"), str) and rec["cause"]):
            _fail(f"pre-spawn record malformed: {rec!r}")
    if not isinstance(doc.get("dnf", []), list):
        _fail("chain.json dnf must be a list")
    return doc


@dataclass
class AttemptRow:
    rerun_index: int
    row: dict | None
    file: str | None
    disposition: str
    output_tokens: int | None = None


@dataclass
class ScoredSlot:
    slot: str
    row: dict
    source: str                      # row | dnf
    file: str | None
    rerun_index: int = 0
    disposition: str = "accepted"
    strict_fail: bool = False
    segment: int = 0                 # legacy m64 `.w<n>`


@dataclass
class SlotTable:
    scored: dict = field(default_factory=dict)
    attempts: dict = field(default_factory=dict)             # slot -> [AttemptRow] by re-run index
    pending_reruns: list = field(default_factory=list)       # [(slot, next re-run index)]
    blocked: list = field(default_factory=list)              # slots whose latest attempt is `unclear`
    open_pre_spawn: list = field(default_factory=list)       # pre-spawn records whose retry is not registered yet
    running: list = field(default_factory=list)              # invocation records never validated
    legacy: bool = False

    def unscored(self, expected_slots):
        return [s for s in expected_slots if s not in self.scored]

    def cell_complete(self, expected_slots):
        return not self.unscored(expected_slots)

    def slot_tokens(self, slot):
        """Output tokens of every attempt of the slot whose count is known (cheat attempts included)."""
        return sum(a.output_tokens or 0 for a in self.attempts.get(slot, []))


# ---------------------------------------------------------------- loading
def _resolve(root, file):
    p = Path(file)
    return p if p.is_absolute() else Path(root) / p


def _rel(root, file):
    p = Path(file)
    if p.is_absolute():
        try:
            return p.relative_to(Path(root)).as_posix()
        except ValueError:
            return p.as_posix()
    return p.as_posix()


def _check_hook_stop(rec):
    hs = rec.get("hook_stop")
    if not (isinstance(hs, dict) and (isinstance(hs.get("before_slot"), str) or
                                      (isinstance(hs.get("after_slot"), str) and hs.get("disposition")))):
        _fail(f"hook-stopped record {rec['file']} carries no hook_stop (before_slot, or after_slot + disposition)")


def _counted_rows(root, rec):
    """The validated rows of one counted invocation record, or raise."""
    accepted = rec["accepted_slots"]
    if not set(accepted) <= set(rec["expected_slots"]) or len(set(accepted)) != len(accepted):
        _fail(f"{rec['file']}: accepted slots are not a duplicate-free subset of the expected slots")
    if rec["status"] == "validated" and accepted != rec["expected_slots"]:
        _fail(f"{rec['file']}: a validated invocation must have accepted exactly its expected slots")
    if rec["status"] == "hook_stopped":
        _check_hook_stop(rec)
    path = _resolve(root, rec["file"])
    if not accepted and rec["sha256"] is None and not path.exists():
        return []
    if not path.exists():
        _fail(f"{rec['file']}: validated rows file missing")
    if rec["sha256"] is None or hashlib.sha256(path.read_bytes()).hexdigest() != rec["sha256"]:
        _fail(f"{rec['file']}: sha256 differs from the validated record (the file changed after validation)")
    rows = read_rows(path)
    got = [slot_for(rec["slot_base"], r["id"]) for r in rows]
    if len(set(got)) != len(got) or set(got) != set(accepted):
        _fail(f"{rec['file']}: rows do not match the accepted slots")
    return rows


def _dnf_rows(doc, root):
    chain_rows_ = doc.get("dnf", [])
    by_slot, sidecars = {}, {}
    for r in chain_rows_:
        parts = r.get("slot", "").split("|") if isinstance(r, dict) else []
        if len(parts) != 6 or r.get("nonconv_kind") != "transport_dnf":
            _fail(f"chain.json dnf row malformed: {r!r}")
        epoch, arm, pick, session, lang, item = parts
        if r["slot"] in by_slot:
            _fail(f"duplicate dnf row for slot {r['slot']}")
        by_slot[r["slot"]] = r
        sidecars.setdefault(Path(root) / session / f"{pick}.{session}.{arm}_{lang}.dnf.jsonl", {})
    root_ = Path(root)
    for extra in sorted(root_.glob("*/*.dnf.jsonl")) if root_.is_dir() else []:
        sidecars.setdefault(extra, {})
    for path in sidecars:
        if path.exists():
            for r in read_rows(path):
                sidecars[path][r.get("slot")] = r
    side_all = {}
    for path, rows in sidecars.items():
        if any(s is None for s in rows):
            _fail(f"{path.name}: a sidecar row has no slot")
        for s, r in rows.items():
            side_all[s] = r
    for s, r in by_slot.items():
        parts = s.split("|")
        path = root_ / parts[3] / f"{parts[2]}.{parts[3]}.{parts[1]}_{parts[4]}.dnf.jsonl"
        if s not in sidecars.get(path, {}):
            _fail(f"dnf row {s} has no sidecar record in {path.name}")
        if json.dumps(sidecars[path][s], sort_keys=True) != json.dumps(r, sort_keys=True):
            _fail(f"dnf row {s}: the sidecar differs from the chain.json copy")
    for s in side_all:
        if s not in by_slot:
            _fail(f"dnf sidecar row {s} is missing from chain.json")
    return by_slot


def load_slots(chain_doc, root, *, check_unregistered=True):
    """Every slot's scored attempt from the progress inventory (see the module docstring). Raises `ChainRowsError`."""
    doc = validate_progress(chain_doc)
    progress, root = doc["progress"], Path(root)
    invocations = progress["invocations"]
    if check_unregistered and root.is_dir():
        registered = {_rel(root, r["file"]) for r in invocations}
        for path in sorted(root.glob("*/*.jsonl")):
            rel = path.relative_to(root).as_posix()
            if FILE_RE.search(path.name) and rel not in registered:
                _fail(f"unregistered rows file {rel}: no progress record names it")
    table = SlotTable()
    attempts = {}                                      # (slot, rerun_index) -> AttemptRow
    for rec in invocations:
        if rec["status"] == "running":
            table.running.append(rec)
        if rec["status"] not in COUNTED_STATUSES:
            continue
        rindex = rec.get("rerun_index", 0)
        for r in _counted_rows(root, rec):
            slot = slot_for(rec["slot_base"], r["id"])
            if (slot, rindex) in attempts:
                _fail(f"duplicate slot {slot} (re-run index {rindex}) across invocations")
            attempts[(slot, rindex)] = AttemptRow(rindex, r, rec["file"], "accepted",
                                                  r.get("output_tokens") if _is_int(r.get("output_tokens")) else None)
    seen = set()
    for rec in progress["slot_attempts"]:
        if rec.get("status") == "archived":
            continue
        key = (rec["slot"], rec["rerun_index"])
        if key in seen:
            _fail(f"duplicate slot attempt record for {key[0]} (re-run index {key[1]})")
        seen.add(key)
        att = attempts.get(key)
        if att is None:
            att = attempts[key] = AttemptRow(key[1], None, None, rec["disposition"])
        att.disposition = rec["disposition"]
        if _is_int(rec.get("output_tokens")):
            att.output_tokens = rec["output_tokens"]
    for (slot, _), att in sorted(attempts.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        table.attempts.setdefault(slot, []).append(att)
    dnf = _dnf_rows(doc, root)
    for slot, atts in table.attempts.items():
        last = max(atts, key=lambda a: a.rerun_index)
        if last.disposition in ("accepted", "exhausted"):
            if last.row is None:
                _fail(f"slot {slot}: disposition {last.disposition} names no row (the attempt's row is missing)")
            if slot in dnf:
                _fail(f"duplicate slot {slot}: both a row and a transport_dnf record")
            table.scored[slot] = ScoredSlot(slot=slot, row=last.row, source="row", file=last.file,
                                            rerun_index=last.rerun_index, disposition=last.disposition,
                                            strict_fail=last.disposition == "exhausted")
        elif last.disposition == "cheat":
            if last.rerun_index >= MAX_RERUNS:
                _fail(f"slot {slot}: a cheat at the last permitted attempt must be recorded as exhausted")
            table.pending_reruns.append((slot, last.rerun_index + 1))
        else:
            table.blocked.append(slot)
    for slot, row_ in dnf.items():
        if slot in table.scored:
            _fail(f"duplicate slot {slot}: both a row and a transport_dnf record")
        table.scored[slot] = ScoredSlot(slot=slot, row=row_, source="dnf", file=None)
    table.pending_reruns.sort()
    table.blocked.sort()
    table.open_pre_spawn = _open_pre_spawn(progress)
    return table


def _open_pre_spawn(progress):
    invocations = progress["invocations"]
    out = []
    for rec in progress["pre_spawn"]:
        if rec.get("status") == "archived":
            continue
        stop_at = next((i for i, inv in enumerate(invocations) if inv["status"] != "archived"
                        and isinstance(inv.get("hook_stop"), dict) and inv["hook_stop"].get("before_slot") == rec["slot"]),
                       -1)
        later = invocations[stop_at + 1:]
        if not any(inv["status"] != "archived" and rec["slot"] in inv["expected_slots"] for inv in later):
            out.append(rec)
    return out


# ---------------------------------------------------------------- legacy (read-only)
_M64_NAME = re.compile(r"^(?P<stem>.+?)(?:\.w(?P<n>\d+))?\.jsonl$")


def legacy(root, layout):
    """Load today's stored layouts without touching them. `c147` / `m63`: `<session>/<stem>.jsonl`; `m64`: base +
    `.w<n>` segments + the `.dnf.jsonl` sidecar. Each slot (`legacy_slot`) must occur once."""
    if layout not in LEGACY_LAYOUTS:
        raise ValueError(f"layout must be one of {LEGACY_LAYOUTS}")
    root = Path(root)
    table = SlotTable(legacy=True)
    if not root.is_dir():
        return table
    for sdir in sorted(d for d in root.iterdir() if d.is_dir() and d.name not in LEGACY_SKIP_DIRS):
        for path in sorted(sdir.glob("*.jsonl")):
            name = path.name
            if name.endswith((".score.jsonl", ".webaudit.jsonl")):
                continue
            is_dnf = name.endswith(".dnf.jsonl")
            if layout in ("c147", "m63"):
                if is_dnf:
                    continue
                stem, segment = name[:-len(".jsonl")], 0
            elif is_dnf:
                stem, segment = name[:-len(".dnf.jsonl")], 0
            else:
                m = _M64_NAME.match(name)
                stem, segment = m.group("stem"), int(m.group("n") or 0)
            for r in read_rows(path):
                slot = legacy_slot(sdir.name, stem, r["id"])
                if slot in table.scored:
                    _fail(f"duplicate slot {slot} ({name})")
                table.scored[slot] = ScoredSlot(slot=slot, row=r, source="dnf" if is_dnf else "row",
                                                file=path.relative_to(root).as_posix(), segment=segment)
    return table
