"""P613 B8 — the P426 pair verifier (step 1: axis A7, the Wave 2c tg1 pairs).

Decides which ON / OFF attempt pairs under `<results_root>/wave2/` are comparable. Fail closed: a structural problem raises
`RefusalError` (nothing is written); a pair that breaks a rule is listed with `accepted: false` and every reason.

Rules (spec `docs/specs/p613-b8-b6-signals.md` v2 §3, step-1 contract `docs/specs/p613-step1-contract.md`):
  1  `leg.json` state VALID (self-hash, leg name); a deny-listed or missing attempt refuses.
  2  dossier `differences` fields within ALLOWED_DIFFERENCES; `chain.json` campaign_core commit == `v8_base` off / on commit.
  3  pair keys (session, id) present in both arms with equal `sampler_seed` (a DNF slot without a row carries no seed);
     a one-sided or seed-mismatched key is rejected alone; differing schedules (schedule.json sha256 with the
     arm-identity fields ARM_SCHEDULE_FIELDS removed) reject the pair.
  4  `speed_valid` on both legs (a power-invalid pair stays a quality pair, labelled "power-invalid").
  5  dossier present, self-hash OK, verdict PASS, names exactly the two attempts (and their HARVEST / receipt file shas);
     every HARVEST `main` file re-verifies against `results_root`.
  7  identity key = the row's `final_tree.manifest_sha256` when it equals the item's HARVEST "main" final-tree manifest
     published_sha256 (else null); ON == OFF (both non-null) marks the key `identical: true`.
Every row needs exactly one item record (`items/*.json`, not `*.ready.json` / `*.dnf.*`) slotted to it.

CLI: `python -m bench.p426_verify a7 --results-root <dir> --out <B8.json>`; rc 0 written, rc 2 `REFUSED: <reason>`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from bench.p426_harvest import _canon_sha

AXIS = "A7"
SESSIONS_PAIRED = ("s1", "s2")
SESSIONS_DIAGNOSTIC = ("pilot", "reload")
SESSIONS = SESSIONS_PAIRED + SESSIONS_DIAGNOSTIC
ALLOWED_DIFFERENCES = ("snapshots.drafter", "argv.worker")
WAVE = "wave2"
REPO_PREFIX = "benchmark/results/p426/"           # HARVEST `published` paths are repo-relative; results_root mirrors this dir
ATTEMPT_RE = re.compile(r"^tg1-p426-(off|on)-(pilot|s1|s2|reload)\.a(\d+)$")
DENY_PATTERNS = (
    (re.compile(r"smoke"), "a smoke member"),
    (re.compile(r"(^|/)archive(/|$)"), "an archive/ member"),
    (re.compile(r"(^|/)wave2\.v8-"), "a superseded wave2.v8-* member"),
    (re.compile(r"(^|/)wave1(/|$)"), "a wave1/ (S build) member"),
    (re.compile(r"(^|/)p426-(off|on)-"), "an S-build p426-{off,on}-* tune"),
)


class RefusalError(Exception):
    """A structural problem: missing / unreadable required file, duplicate row key, row count != planned slots, deny-listed
    member. A rejected pair is NOT a refusal."""


# ------------------------------------------------------------------------------------------------------------ file access
class Reader:
    """Reads files under `results_root`, recording `{relpath: sha256}` of every byte string read."""

    def __init__(self, results_root):
        self.root = Path(results_root)
        self.inputs = {}

    def rel(self, path):
        return Path(path).relative_to(self.root).as_posix()

    def read_bytes(self, path, what):
        path = Path(path)
        try:
            data = path.read_bytes()
        except (OSError, ValueError) as exc:
            raise RefusalError(f"{what}: required file {self._safe_rel(path)} is missing or unreadable "
                               f"({type(exc).__name__})") from None
        self.inputs[self.rel(path)] = hashlib.sha256(data).hexdigest()
        return data

    def try_read_bytes(self, path):
        """None when the file is absent (a rule, not a refusal, decides what that means)."""
        path = Path(path)
        if not path.is_file():
            return None
        return self.read_bytes(path, self._safe_rel(path))

    def read_json(self, path, what):
        data = self.read_bytes(path, what)
        return _parse_json(data, f"{what} ({self._safe_rel(path)})")

    def _safe_rel(self, path):
        try:
            return self.rel(path)
        except ValueError:
            return Path(path).name


def _parse_json(data, what):
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise RefusalError(f"{what}: unreadable JSON") from None


def _parse_jsonl(data, what):
    rows = []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise RefusalError(f"{what}: unreadable (not UTF-8)") from None
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            raise RefusalError(f"{what}: line {n} is not JSON") from None
        if not isinstance(row, dict):
            raise RefusalError(f"{what}: line {n} is not an object")
        rows.append(row)
    return rows


def self_hash_ok(doc):
    return isinstance(doc, dict) and isinstance(doc.get("sha256"), str) and doc["sha256"] == _canon_sha(doc)


# ----------------------------------------------------------------------------------------------------------- members
def check_member_name(name, where):
    """Refuse a pair member that is not a plain Wave 2 attempt name or that matches the deny-list."""
    if not isinstance(name, str) or not name:
        raise RefusalError(f"{where}: attempt name {name!r} is not a string")
    for pattern, what in DENY_PATTERNS:
        if pattern.search(name):
            raise RefusalError(f"{where}: {name} is deny-listed ({what})")
    if "/" in name or "\\" in name or name.startswith(".") or not ATTEMPT_RE.match(name):
        raise RefusalError(f"{where}: {name!r} is not a wave2 tg1-p426-{{off,on}}-<session>.a<k> attempt name")
    return ATTEMPT_RE.match(name)


def attempt_dir(results_root, name, where):
    root = Path(results_root)
    check_member_name(name, where)
    path = root / WAVE / name
    if not path.is_dir():
        raise RefusalError(f"{where}: attempt {WAVE}/{name} is missing")
    try:
        resolved_parent = path.resolve().parent
    except OSError:
        raise RefusalError(f"{where}: attempt {WAVE}/{name} is unreadable") from None
    if resolved_parent != (root / WAVE).resolve():
        raise RefusalError(f"{where}: attempt {WAVE}/{name} resolves outside {WAVE}/ (deny-listed)")
    return path


def leg_name(attempt):
    return attempt.rsplit(".a", 1)[0]


def attempt_no(attempt):
    return int(attempt.rsplit(".a", 1)[1])


# ------------------------------------------------------------------------------------------------------------- loading
def planned_slots(schedule, where):
    """(count, [ids]) — count = Σ len(names) over blocks[].legs[].invocations[]; ids from `expect` (else lang/name).
    An invocation whose `expect` (an id list or a count, when present) disagrees with len(names) refuses."""
    try:
        count, ids = 0, []
        for block in schedule["blocks"]:
            for leg in block["legs"]:
                for inv in leg["invocations"]:
                    names = list(inv["names"])
                    count += len(names)
                    expect = inv.get("expect")
                    if expect is None:
                        ids.extend(f"{leg['lang']}/{n}" for n in names)
                        continue
                    if isinstance(expect, bool) or not isinstance(expect, (int, list)):
                        raise RefusalError(f"{where}: schedule.json invocation expect {expect!r} is neither a count "
                                           f"nor an id list")
                    n_expect = expect if isinstance(expect, int) else len(expect)
                    if n_expect != len(names):
                        raise RefusalError(f"{where}: schedule.json invocation expect {n_expect} != len(names) "
                                           f"{len(names)}")
                    ids.extend(list(expect) if isinstance(expect, list) else [f"{leg['lang']}/{n}" for n in names])
    except (KeyError, TypeError):
        raise RefusalError(f"{where}: schedule.json has no blocks[].legs[].invocations[].names") from None
    return count, ids


def _is_dnf_file(path):
    return ".dnf." in Path(path).name


def load_rows(reader, sdir, session, where):
    """{id: row} from `<sdir>/*.jsonl` (excluding `*.dnf.*`); refuses on a missing directory, a bad row, a duplicate key."""
    if not sdir.is_dir():
        raise RefusalError(f"{where}: session directory {reader._safe_rel(sdir)} is missing")
    files = [f for f in sorted(sdir.glob("*.jsonl")) if not _is_dnf_file(f)]
    if not files:
        raise RefusalError(f"{where}: no row files in {reader._safe_rel(sdir)}")
    rows = {}
    for f in files:
        rel = reader.rel(f)
        for row in _parse_jsonl(reader.read_bytes(f, f"{where} rows"), rel):
            rid = row.get("id")
            if not isinstance(rid, str) or "/" not in rid:
                raise RefusalError(f"{where}: {rel}: a row has no `<language>/<item>` id ({rid!r})")
            seed = row.get("sampler_seed")
            if not isinstance(seed, int) or isinstance(seed, bool):
                raise RefusalError(f"{where}: {rel}: row {rid} has no integer sampler_seed")
            if rid in rows:
                raise RefusalError(f"{where}: duplicate row key ({session}, {rid})")
            rows[rid] = row
    return rows


def load_dnf(chain, rows, session, where):
    """{id: record} of this session's `chain.json` `p426_dnf` slots that have no row."""
    dnf_records = chain.get("p426_dnf") or []
    if not isinstance(dnf_records, list):
        raise RefusalError(f"{where}: chain.json p426_dnf is not a list")
    dnf = {}
    for rec in dnf_records:
        if not isinstance(rec, dict):
            raise RefusalError(f"{where}: chain.json p426_dnf holds a non-object")
        if rec.get("session", session) != session:
            continue
        did = _dnf_id(rec, where)
        if did not in rows:
            dnf[did] = rec
    return dnf


def check_planned(rows, dnf, schedule, where):
    """(count, ids); refuses unless rows + DNF slots are exactly the planned slots."""
    count, ids = planned_slots(schedule, where)
    if len(set(ids)) != len(ids):
        raise RefusalError(f"{where}: schedule.json plans a slot twice")
    if len(rows) + len(dnf) != count:
        raise RefusalError(f"{where}: row count {len(rows)} (+{len(dnf)} DNF) != planned slots {count}")
    stray = sorted((set(rows) | set(dnf)) - set(ids))
    if stray:
        raise RefusalError(f"{where}: rows outside the planned slots: {stray}")
    return count, ids


def load_items(reader, idir, session, rows, dnf, where):
    """{id: item record}. Every row needs exactly one record whose `slot` names (session, language, item) and whose file
    name ends `__<session>__<language>__<item>.json`; a missing, duplicate or mis-slotted record refuses. A DNF slot needs
    none."""
    items = {}
    files = []
    if idir.is_dir():
        files = [f for f in sorted(idir.glob("*.json")) if not f.name.endswith(".ready.json") and not _is_dnf_file(f)]
    for f in files:
        rel = reader.rel(f)
        rec = reader.read_json(f, f"{where} item record")
        slot = rec.get("slot") if isinstance(rec, dict) else None
        if not isinstance(slot, str) or slot.count("|") < 2:
            raise RefusalError(f"{where}: item record {rel} has no slot")
        s_session, s_lang, s_item = slot.split("|")[-3:]
        iid = f"{s_lang}/{s_item}"
        if s_session != session:
            raise RefusalError(f"{where}: item record {rel} is mis-slotted: slot session {s_session!r} != {session!r}")
        if not f.name.endswith(f"__{s_session}__{s_lang}__{s_item}.json"):
            raise RefusalError(f"{where}: item record {rel} is mis-slotted: file name does not match slot {slot!r}")
        if iid not in rows and iid not in dnf:
            raise RefusalError(f"{where}: item record {rel} is mis-slotted: ({session}, {iid}) is not a planned slot")
        if iid in items:
            raise RefusalError(f"{where}: duplicate item record for ({session}, {iid})")
        items[iid] = rec
    missing = sorted(set(rows) - set(items))
    if missing:
        raise RefusalError(f"{where}: no item record for row(s) {missing}")
    return items


def _dnf_id(rec, where):
    lang, item = rec.get("language"), rec.get("item")
    if isinstance(lang, str) and isinstance(item, str):
        return f"{lang}/{item}"
    slot = rec.get("slot")
    if isinstance(slot, str) and slot.count("|") >= 2:
        parts = slot.split("|")
        return f"{parts[-2]}/{parts[-1]}"
    raise RefusalError(f"{where}: a p426_dnf record names no language / item / slot")


def load_attempt(reader, name, session, where):
    """Read one attempt. Returns a dict with its records, rows by id, DNF-only ids, item records by id. Refuses on a
    missing / unreadable required file, a duplicate row key, or a row set != the planned slots."""
    path = attempt_dir(reader.root, name, where)
    leg = reader.read_json(path / "leg.json", f"{where} leg.json")
    chain = reader.read_json(path / "chain.json", f"{where} chain.json")
    harvest = reader.read_json(path / "HARVEST.json", f"{where} HARVEST.json")
    schedule = reader.read_json(path / "schedule.json", f"{where} schedule.json")
    for doc, what in ((leg, "leg.json"), (chain, "chain.json"), (harvest, "HARVEST.json"), (schedule, "schedule.json")):
        if not isinstance(doc, dict):
            raise RefusalError(f"{where}: {what} is not an object")
    rows = load_rows(reader, path / session, session, where)
    dnf = load_dnf(chain, rows, session, where)
    count, ids = check_planned(rows, dnf, schedule, where)
    items = load_items(reader, path / "items", session, rows, dnf, where)
    schedule_sha = reader.inputs[reader.rel(path / "schedule.json")]
    return dict(name=name, path=path, leg=leg, chain=chain, harvest=harvest, schedule=schedule, rows=rows, dnf=dnf,
                items=items, planned=count, planned_ids=ids, schedule_sha256=schedule_sha)


ARM_SCHEDULE_FIELDS = ("predictor", "blocks[].legs[].draft_kind")


def schedule_plan_sha(schedule):
    """sha256 of schedule.json with the arm-identity fields (ARM_SCHEDULE_FIELDS) removed; equal plans → equal shas."""
    doc = json.loads(json.dumps(schedule))
    doc.pop("predictor", None)
    for block in doc.get("blocks") or []:
        for leg in (block.get("legs") or []) if isinstance(block, dict) else []:
            if isinstance(leg, dict):
                leg.pop("draft_kind", None)
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def harvest_manifests(att):
    """{id: [(run_id, published_sha256)]} of the attempt's HARVEST destination-"main" final-tree manifests
    (`<REPO_PREFIX>wave2/<attempt>/evidence/<run_id>/<language>__<item>.final_tree/manifest.json`)."""
    pat = re.compile(r"^" + re.escape(f"{REPO_PREFIX}{WAVE}/{att['name']}/evidence/")
                     + r"([^/]+)/([^/]+?)__([^/]+)\.final_tree/manifest\.json$")
    out = {}
    files = att["harvest"].get("files") if isinstance(att["harvest"], dict) else None
    for f in files if isinstance(files, list) else []:
        if not isinstance(f, dict) or f.get("destination") != "main" or not isinstance(f.get("published"), str):
            continue
        m = pat.match(f["published"])
        if m:
            out.setdefault(f"{m.group(2)}/{m.group(3)}", []).append((m.group(1), f.get("published_sha256")))
    return out


def manifest_sha(row, rid=None, manifests=None):
    """Rule 7 identity: the row's `final_tree.manifest_sha256`, counted only when it equals the published_sha256 of the
    HARVEST destination-"main" final-tree manifest for that item (the row's run id when its manifest path names one);
    otherwise None. With `manifests` None the raw row value is returned."""
    tree = row.get("final_tree") if row is not None else None
    if not (isinstance(tree, dict) and isinstance(tree.get("manifest_sha256"), str)):
        return None
    sha = tree["manifest_sha256"]
    if manifests is None:
        return sha
    cands = list(manifests.get(rid, []))
    lang, _, item = (rid or "").partition("/")
    mpath = tree.get("manifest")
    if isinstance(mpath, str):
        p = Path(mpath)
        if p.name == "manifest.json" and p.parent.name == f"{lang}__{item}.final_tree" and "." in p.parent.parent.name:
            run_id = p.parent.parent.name.rsplit(".", 1)[1]
            cands = [c for c in cands if c[0] == run_id]
    if len(cands) != 1 or cands[0][1] != sha:
        return None
    return sha


def pair_keys(session, off, on):
    """Rule 3 + rule 7. Returns (accepted [{key, identical, off_manifest_sha256, on_manifest_sha256}], rejected)."""
    accepted, rejected = [], []
    man_off, man_on = harvest_manifests(off), harvest_manifests(on)
    ids = sorted(set(off["rows"]) | set(off["dnf"]) | set(on["rows"]) | set(on["dnf"]))
    for rid in ids:
        key = [session, rid]
        in_off = rid in off["rows"] or rid in off["dnf"]
        in_on = rid in on["rows"] or rid in on["dnf"]
        if not in_off or not in_on:
            rejected.append(dict(key=key, reason=f"missing slot: absent in {'off' if not in_off else 'on'}"))
            continue
        ro, rn = off["rows"].get(rid), on["rows"].get(rid)
        if ro is not None and rn is not None and ro["sampler_seed"] != rn["sampler_seed"]:
            rejected.append(dict(key=key, reason=f"seed mismatch: off {ro['sampler_seed']} on {rn['sampler_seed']}"))
            continue
        mo, mn = manifest_sha(ro, rid, man_off), manifest_sha(rn, rid, man_on)
        accepted.append(dict(key=key, identical=mo is not None and mo == mn, off_manifest_sha256=mo,
                             on_manifest_sha256=mn))
    return accepted, rejected


# --------------------------------------------------------------------------------------------------------------- rules
def _leg_reasons(arm, att):
    leg, name = att["leg"], att["name"]
    reasons = []
    if leg.get("state") != "VALID":
        reasons.append(f"rule 1: {arm} {name} leg.json state {leg.get('state')!r} != 'VALID'")
    if not self_hash_ok(leg):
        reasons.append(f"rule 1: {arm} {name} leg.json self-hash {leg.get('sha256')!r} != {_canon_sha(leg)}")
    if "leg" in leg and leg["leg"] != leg_name(name):
        reasons.append(f"rule 1: {arm} {name} leg.json leg {leg['leg']!r} != {leg_name(name)!r}")
    if "attempt" in leg and leg["attempt"] != attempt_no(name):
        reasons.append(f"rule 1: {arm} {name} leg.json attempt {leg['attempt']!r} != {attempt_no(name)}")
    return reasons


def _harvest_reasons(reader, arm, att):
    h, name = att["harvest"], att["name"]
    reasons = []
    if not self_hash_ok(h):
        reasons.append(f"rule 5: {arm} {name} HARVEST.json self-hash {h.get('sha256')!r} != {_canon_sha(h)}")
    if "leg" in h and h["leg"] != leg_name(name):
        reasons.append(f"rule 5: {arm} {name} HARVEST.json leg {h['leg']!r} != {leg_name(name)!r}")
    files = h.get("files")
    if not isinstance(files, list):
        return reasons + [f"rule 5: {arm} {name} HARVEST.json has no files list"]
    for f in files:
        if not isinstance(f, dict) or f.get("destination") != "main":
            continue
        pub, want = f.get("published"), f.get("published_sha256")
        if not isinstance(pub, str) or not pub.startswith(REPO_PREFIX) or ".." in pub.split("/"):
            reasons.append(f"rule 5: {arm} {name} HARVEST main file {pub!r} is not under {REPO_PREFIX}")
            continue
        data = reader.try_read_bytes(reader.root / pub[len(REPO_PREFIX):])
        if data is None:
            reasons.append(f"rule 5: {arm} {name} HARVEST main file {pub[len(REPO_PREFIX):]} is missing")
            continue
        got = hashlib.sha256(data).hexdigest()
        if got != want:
            reasons.append(f"rule 5: {arm} {name} HARVEST main file {pub[len(REPO_PREFIX):]} sha256 {got} != "
                           f"published_sha256 {want}")
    return reasons


def _dossier_reasons(reader, session, dossier_rel, off, on):
    path = reader.root / WAVE / dossier_rel
    data = reader.try_read_bytes(path)
    if data is None:
        return [f"rule 5: dossier {WAVE}/{dossier_rel} is missing"], None
    try:
        doc = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return [f"rule 5: dossier {WAVE}/{dossier_rel} is unreadable JSON"], None
    if not isinstance(doc, dict):
        return [f"rule 5: dossier {WAVE}/{dossier_rel} is not an object"], None
    reasons = []
    if not self_hash_ok(doc):
        reasons.append(f"rule 5: dossier self-hash {doc.get('sha256')!r} != {_canon_sha(doc)}")
    if doc.get("verdict") != "PASS":
        reasons.append(f"rule 5: dossier verdict {doc.get('verdict')!r} != 'PASS'")
    if doc.get("pair") != session:
        reasons.append(f"rule 5: dossier pair {doc.get('pair')!r} != {session!r}")
    arms = doc.get("arms") if isinstance(doc.get("arms"), dict) else {}
    if sorted(arms) != ["off", "on"]:
        reasons.append(f"rule 5: dossier arms {sorted(arms)} != ['off', 'on']")
    for arm, att in (("off", off), ("on", on)):
        rec = arms.get(arm) if isinstance(arms.get(arm), dict) else {}
        if rec.get("attempt") != att["name"]:
            reasons.append(f"rule 5: dossier arms.{arm}.attempt {rec.get('attempt')!r} != {att['name']!r}")
        h_sha = reader.inputs.get(reader.rel(att["path"] / "HARVEST.json"))
        if rec.get("harvest_sha256") != h_sha:
            reasons.append(f"rule 5: dossier arms.{arm}.harvest_sha256 {rec.get('harvest_sha256')!r} != "
                           f"{att['name']}/HARVEST.json {h_sha}")
        r_data = reader.try_read_bytes(att["path"] / "receipt.json")
        r_sha = hashlib.sha256(r_data).hexdigest() if r_data is not None else None
        if rec.get("receipt_sha256") != r_sha:
            reasons.append(f"rule 5: dossier arms.{arm}.receipt_sha256 {rec.get('receipt_sha256')!r} != "
                           f"{att['name']}/receipt.json {r_sha}")
    diffs = doc.get("differences")
    if not isinstance(diffs, list):
        reasons.append("rule 2: dossier differences is not a list")
    else:
        fields = [d.get("field") if isinstance(d, dict) else None for d in diffs]
        extra = sorted({str(f) for f in fields if f not in ALLOWED_DIFFERENCES})
        if extra:
            reasons.append(f"rule 2: dossier differences {extra} outside the allowed {list(ALLOWED_DIFFERENCES)}")
    return reasons, doc


def _commit_reasons(v8, arm, att):
    want = v8.get(f"{arm}_commit")
    try:
        got = att["chain"]["artifacts"]["campaign_core"]["commit"]
    except (KeyError, TypeError):
        got = None
    if got is None or got != want:
        return [f"rule 2: {arm} {att['name']} chain.json campaign_core commit {got!r} != v8_base {arm}_commit {want!r}"]
    return []


def _sequence_pair(seq, session):
    pairs = seq.get("pairs") if isinstance(seq, dict) else None
    if not isinstance(pairs, list):
        raise RefusalError("wave2/run/sequence.json has no pairs list")
    hits = [p for p in pairs if isinstance(p, dict) and p.get("pair") == session]
    if len(hits) != 1:
        raise RefusalError(f"wave2/run/sequence.json names {len(hits)} pair records for {session} (need exactly 1)")
    return hits[0]


def _sequence_leg_reasons(seq, arm, name):
    reasons = []
    for leg in seq.get("legs") or []:
        if isinstance(leg, dict) and leg.get("leg") == leg_name(name) and leg.get("attempt") == attempt_no(name):
            if leg.get("state") != "VALID":
                reasons.append(f"rule 1: {arm} {name} sequence.json leg state {leg.get('state')!r} != 'VALID'")
    return reasons


def verify_a7(results_root):
    """B8 for axis A7: one record per session (s1 / s2 paired; pilot / reload diagnostic)."""
    reader = Reader(results_root)
    run = reader.root / WAVE / "run"
    v8 = reader.read_json(run / "v8_base.json", "wave2/run/v8_base.json")
    seq = reader.read_json(run / "sequence.json", "wave2/run/sequence.json")
    if not isinstance(v8, dict) or not isinstance(seq, dict):
        raise RefusalError("wave2/run/v8_base.json or sequence.json is not an object")
    v8_reasons = [] if self_hash_ok(v8) else [f"rule 2: v8_base.json self-hash {v8.get('sha256')!r} != {_canon_sha(v8)}"]
    out_pairs = []
    for session in SESSIONS:
        sp = _sequence_pair(seq, session)
        names = {}
        for arm in ("off", "on"):
            name = sp.get(arm)
            m = check_member_name(name, f"pair {session} {arm}")
            if m.group(1) != arm or m.group(2) != session:
                raise RefusalError(f"pair {session} {arm}: attempt {name} is not a {arm}-{session} attempt")
            names[arm] = name
        off = load_attempt(reader, names["off"], session, f"pair {session} off {names['off']}")
        on = load_attempt(reader, names["on"], session, f"pair {session} on {names['on']}")
        reasons = list(v8_reasons)
        for arm, att in (("off", off), ("on", on)):
            reasons += _leg_reasons(arm, att) + _sequence_leg_reasons(seq, arm, att["name"])
        for arm, att in (("off", off), ("on", on)):
            reasons += _commit_reasons(v8, arm, att)
        dossier_rel = sp.get("dossier") or f"pairs/{session}__off-a1__on-a1.json"
        if not isinstance(dossier_rel, str) or not dossier_rel.startswith("pairs/") or ".." in dossier_rel.split("/"):
            raise RefusalError(f"pair {session}: sequence dossier path {dossier_rel!r} is not under wave2/pairs/")
        d_reasons, _doc = _dossier_reasons(reader, session, dossier_rel, off, on)
        reasons += d_reasons
        for arm, att in (("off", off), ("on", on)):
            reasons += _harvest_reasons(reader, arm, att)
        plan_off, plan_on = schedule_plan_sha(off["schedule"]), schedule_plan_sha(on["schedule"])
        if plan_off != plan_on:
            reasons.append(f"rule 3: schedules differ (off schedule.json sha256 {off['schedule_sha256']} plan "
                           f"{plan_off}, on sha256 {on['schedule_sha256']} plan {plan_on})")
        keys, keys_rejected = pair_keys(session, off, on)
        speed_valid = off["leg"].get("speed_valid") is True and on["leg"].get("speed_valid") is True
        labels = [] if speed_valid else ["power-invalid"]
        rec = dict(pair=session, off=names["off"], on=names["on"], accepted=not reasons, reasons=reasons,
                   keys_accepted=len(keys), keys_rejected=keys_rejected, keys=keys,
                   identical=sum(1 for k in keys if k["identical"]), speed_valid=speed_valid, labels=labels,
                   dossier=f"{WAVE}/{dossier_rel}",
                   speed_reason=dict(off=off["leg"].get("speed_reason"), on=on["leg"].get("speed_reason")))
        if session in SESSIONS_DIAGNOSTIC:
            rec["role"] = "diagnostic"
        else:
            rec["role"] = "pair"
        out_pairs.append(rec)
    return dict(axis=AXIS, generator="bench.p426_verify", inputs=dict(sorted(reader.inputs.items())), pairs=out_pairs,
                v8_base=dict(sha256=v8.get("sha256"), off_commit=v8.get("off_commit"), on_commit=v8.get("on_commit"),
                             gitlinks=v8.get("gitlinks")),
                allowed_differences=list(ALLOWED_DIFFERENCES))


def dumps(doc):
    return json.dumps(doc, sort_keys=True, indent=1) + "\n"


def _one_line(text):
    return " ".join(str(text).split())


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m bench.p426_verify")
    sub = ap.add_subparsers(dest="axis", required=True)
    a7 = sub.add_parser("a7")
    a7.add_argument("--results-root", required=True, type=Path)
    a7.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    try:
        check_out_dirs([args.out])
        doc = verify_a7(args.results_root)
        write_atomic({args.out: dumps(doc)})
    except RefusalError as exc:
        print(f"REFUSED: {_one_line(exc)}", file=sys.stderr)
        return 2
    return 0


def check_out_dirs(paths):
    for p in paths:
        if not Path(p).parent.is_dir():
            raise RefusalError(f"output directory for {Path(p).name} is missing")


def write_atomic(texts):
    """Write every {path: text} to a temporary in its destination directory, then rename all; nothing is left behind
    on failure."""
    import os
    import tempfile

    check_out_dirs(list(texts))
    tmps = []
    try:
        for path, text in texts.items():
            path = Path(path)
            fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
            tmps.append((tmp, path))
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
        for tmp, path in tmps:
            os.replace(tmp, path)
    except OSError as exc:
        for tmp, _ in tmps:
            if os.path.exists(tmp):
                os.unlink(tmp)
        raise RefusalError(f"cannot write outputs ({type(exc).__name__})") from None


if __name__ == "__main__":
    sys.exit(main())
