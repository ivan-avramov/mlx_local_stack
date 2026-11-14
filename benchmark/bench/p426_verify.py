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

Step 2 (`docs/specs/p613-step2-contract.md`): `verify_wave1` (A1 math500, A2 cjudge, A3 vision, A4 reasoning, M1; rules
1-4 and 7 per (kind, block)), `cross_wave` (rule 6) and `verify_all` (one record: A7 + Wave 1 + rule 6).
CLI: `python -m bench.p426_verify all --results-root <p426 dir> --rows-root <results dir> --repo <git top> --out <B8.json>`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from bench import chain_rows as cr
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
    (re.compile(r"(^|[/.])p426-(off|on)-"), "an S-build p426-{off,on}-* tune"),
)
# Fix 12: absolute / home-relative path tokens in a rejection reason are masked (public repo).
PATH_TOKEN_RE = re.compile(r"(?<![\w.\-/~$])(?:~[\w.\-]*|\$\{?HOME\}?)?/[^\s'\"`,;()\[\]{}<>]+")


def mask_paths(text):
    """The one masking helper for Wave 1 rejection reasons: every absolute or home-relative path token → `<path>`."""
    return PATH_TOKEN_RE.sub("<path>", str(text))


class RefusalError(Exception):
    """A structural problem: missing / unreadable required file, duplicate row key, row count != planned slots, deny-listed
    member. A rejected pair is NOT a refusal."""


# ------------------------------------------------------------------------------------------------------------ file access
class Reader:
    """Reads files under `results_root`, recording `{relpath: sha256}` of every byte string read."""

    def __init__(self, results_root, confine=False):
        """`confine` (Wave 1, fix 5): every input must resolve (symlinks followed) under the resolved root, else
        refusal (committed-only inputs). The step-1 A7 reader keeps confine=False (unchanged)."""
        self.root = Path(results_root)
        self.inputs = {}
        self.confine = confine

    def rel(self, path):
        return Path(path).relative_to(self.root).as_posix()

    def check_confined(self, path, what):
        if not self.confine:
            return
        try:
            Path(path).resolve().relative_to(self.root.resolve())
        except (OSError, ValueError, RuntimeError):
            raise RefusalError(f"{what}: input {self._safe_rel(path)} resolves outside rows_root") from None

    def read_bytes(self, path, what):
        path = Path(path)
        self.check_confined(path, what)
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


def session_rows(reader, sdir, session, where):
    """{id: row} from `<sdir>/*.jsonl` (excluding `*.dnf.*`), parsed by `bench.chain_rows.read_rows` (the one chain-row reader:
    torn-file and row-shape rules, P617); refuses on a missing directory, a bad row, a duplicate key."""
    if not sdir.is_dir():
        raise RefusalError(f"{where}: session directory {reader._safe_rel(sdir)} is missing")
    files = [f for f in sorted(sdir.glob("*.jsonl")) if not _is_dnf_file(f)]
    if not files:
        raise RefusalError(f"{where}: no row files in {reader._safe_rel(sdir)}")
    rows = {}
    for f in files:
        rel = reader.rel(f)
        reader.read_bytes(f, f"{where} rows")                 # records the input sha256 (B8 staleness)
        try:
            parsed = cr.read_rows(f)
        except cr.ChainRowsError as exc:
            raise RefusalError(f"{where}: {rel}: {exc}") from None
        for row in parsed:
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
    rows = session_rows(reader, path / session, session, where)
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


def harvest_manifests(att, prefix=REPO_PREFIX):
    """{id: [(run_id, published_sha256)]} of the attempt's HARVEST destination-"main" final-tree manifests
    (`<REPO_PREFIX>wave2/<attempt>/evidence/<run_id>/<language>__<item>.final_tree/manifest.json`; M76 lever kv:
    `prefix` = `KV_REPO_PREFIX`)."""
    pat = re.compile(r"^" + re.escape(f"{prefix}{WAVE}/{att['name']}/evidence/")
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


def pair_keys(session, off, on, prefix=REPO_PREFIX):
    """Rule 3 + rule 7. Returns (accepted [{key, identical, off_manifest_sha256, on_manifest_sha256}], rejected)."""
    accepted, rejected = [], []
    man_off, man_on = harvest_manifests(off, prefix), harvest_manifests(on, prefix)
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


# ===================================================================================================== Wave 1 (step 2)
# Contract `docs/specs/p613-step2-contract.md`: Wave 1 adapters (A1 math500, A2 cjudge, A3 vision, A4 reasoning, M1),
# rules 1-4 and 7 per (kind, block) pair, the rule-6 cross-wave code check, and one `all` record (A7 + Wave 1).
ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
W1 = "wave1.s2"
W1_KINDS = ("math500", "cjudge", "vision", "reasoning", "m1")
W1_AXIS = {"math500": "A1", "cjudge": "A2", "vision": "A3", "reasoning": "A4", "m1": "M1"}
W1_BLOCKS = ("b1", "b2")
W1_IDS_BLOCK = {"b1": "block1", "b2": "block2"}
W1_ROWS = {"math500": "math500.{tune}.jsonl", "cjudge": "cjudge.{tune}.jsonl", "vision": "vision_gate.{tune}.jsonl",
           "reasoning": "reasoning.{tune}.json"}
W1_MANIFEST = {"math500": "math500.{tune}.manifest.json", "cjudge": "cjudge.{tune}.manifest.json",
               "vision": "vision_gate.{tune}.manifest.json", "reasoning": "reasoning.{tune}.manifest.json"}
RESTORE_DELTA = ("--draft-kind mtp", f"--draft-model caslca/{ENTRY}-mtp-drafter", "--mtp-verify-scan joint_v1")
M1_SERVED_ARM_FIELDS = ("draft_kind", "drafter_loaded", "verify_policy")
M1_REPORT_EQUAL = ("reviewed_head", "production", "versions")
SCRUB_PREFIX = "benchmark/results/"
def _arm_path_re(arm):
    """Fix 3: only the leg's OWN arm worktree component normalises; the other arm's stays and shows in the delta."""
    return re.compile(rf"stack-p426-s2-{re.escape(arm)}(?=/|$)")
CROSS_WAVE_ENTRIES = ("benchmark/run.py", "benchmark/vision_gate.py", "benchmark/bench/run_reasoning.py")
CROSS_WAVE_FIXED = ("main_models.yaml", "src/mlx-vlm", "src/mlx-serve")
GITLINKS = ("src/mlx-vlm", "src/mlx-serve")
QUALIFY_ENTRY = "src/mlx-vlm/dev/p369_phase2/qualify.py"


def leg_of(kind, arm, block):
    return f"{kind}-p426s2-{arm}-{block}"


def tune_of(arm, block):
    return f"p426s2-{arm}-{block}"


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if isinstance(text, str) else None


def check_roots(results_root, rows_root):
    """rows_root must resolve equal to `bench.generate.results_root()` (A1 regrades through `bench.grade`), and
    results_root to `rows_root / "p426"`; else refusal."""
    from bench import generate

    try:
        rr, gr = Path(rows_root).resolve(), Path(generate.results_root()).resolve()
        pr, want = Path(results_root).resolve(), (Path(rows_root) / "p426").resolve()
    except OSError:
        raise RefusalError("rows_root / results_root is unresolvable") from None
    if rr != gr:
        raise RefusalError("rows_root does not resolve to bench.generate.results_root() (A1 regrades through "
                           "bench.grade, which reads generate.results_root())")
    if pr != want:
        raise RefusalError("results_root does not resolve to rows_root/p426")


def _w1_member(rows_root, path, where, want_dir=False):
    """Refuse a Wave 1 pair member path that is missing, resolves outside rows_root, or resolves to a deny-listed
    location (p426/wave1/, S-build p426-* tunes, smokes, archive/, wave2.v8-*)."""
    path = Path(path)
    ok = path.is_dir() if want_dir else path.is_file()
    if not ok:
        raise RefusalError(f"{where}: required {'directory' if want_dir else 'file'} "
                           f"{_rel_or_name(rows_root, path)} is missing")
    try:
        rel = path.resolve().relative_to(Path(rows_root).resolve()).as_posix()
    except (OSError, ValueError):
        raise RefusalError(f"{where}: {path.name} resolves outside rows_root (deny-listed)") from None
    for pattern, what in DENY_PATTERNS:
        if pattern.search(rel):
            raise RefusalError(f"{where}: {rel} is deny-listed ({what})")
    return path


def _rel_or_name(root, path):
    try:
        return Path(path).relative_to(Path(root)).as_posix()
    except ValueError:
        return Path(path).name


# ---------------------------------------------------------------------------------------------- Wave 1 loading
def _w1_rows(reader, kind, path, where):
    """Normalised rows of one leg: [{"id", "seed", "row"}] (A4: id = task seed, seed = sampler_seed)."""
    if kind in ("math500", "cjudge", "vision"):
        reader.read_bytes(path, f"{where} rows")                 # records the input sha256 (B8 staleness)
        try:
            rows = cr.read_rows(path)
        except cr.ChainRowsError as exc:
            raise RefusalError(f"{where}: {reader.rel(path)}: {exc}") from None
        seed_field = "seed" if kind == "vision" else "sampler_seed"
        out = []
        for row in rows:
            seed = row.get(seed_field)
            if not isinstance(seed, int) or isinstance(seed, bool):
                raise RefusalError(f"{where}: {reader.rel(path)}: row {row.get('id')} has no integer {seed_field}")
            out.append(dict(id=row["id"], seed=seed, row=row))
        return out, None, None
    doc = reader.read_json(path, f"{where} reasoning result")
    try:
        rec = doc["records"][0]
        rows = rec["rows"]
    except (KeyError, IndexError, TypeError):
        raise RefusalError(f"{where}: {reader.rel(path)} has no records[0].rows") from None
    if not isinstance(rows, list) or not isinstance(rec, dict):
        raise RefusalError(f"{where}: {reader.rel(path)} records[0].rows is not a list")
    out = []
    for row in rows:
        if not isinstance(row, dict):
            raise RefusalError(f"{where}: {reader.rel(path)} holds a non-object row")
        task, seed = row.get("seed"), row.get("sampler_seed")
        for v, name in ((task, "seed"), (seed, "sampler_seed")):
            if not isinstance(v, int) or isinstance(v, bool):
                raise RefusalError(f"{where}: {reader.rel(path)}: a row has no integer {name}")
        out.append(dict(id=task, seed=seed, row=row))
    return out, rec, doc


def load_w1_leg(reader, kind, arm, block):
    """Read one Wave 1 leg (receipt, SCRUB manifest and its result files). Refuses on a missing / unreadable /
    deny-listed required file."""
    root = reader.root
    leg, tune = leg_of(kind, arm, block), tune_of(arm, block)
    where = f"pair {kind} {block} {arm} {leg}"
    ldir = _w1_member(root, root / "p426" / W1 / leg, where, want_dir=True)
    receipt = reader.read_json(_w1_member(root, ldir / f"{leg}.receipt.json", where), f"{where} receipt")
    scrub = reader.read_json(_w1_member(root, ldir / "SCRUB_MANIFEST.json", where), f"{where} SCRUB_MANIFEST.json")
    for doc, what in ((receipt, "receipt"), (scrub, "SCRUB_MANIFEST.json")):
        if not isinstance(doc, dict):
            raise RefusalError(f"{where}: {what} is not an object")
    out = dict(kind=kind, arm=arm, block=block, leg=leg, tune=tune, dir=ldir, receipt=receipt, scrub=scrub)
    if kind == "m1":
        mdir = ldir / "m1" / ENTRY
        out["result"] = reader.read_json(_w1_member(root, mdir / "result.json", where), f"{where} result.json")
        out["job"] = reader.read_json(_w1_member(root, mdir / "job.json", where), f"{where} job.json")
        out["report"] = reader.read_json(_w1_member(root, ldir / "m1" / "report.json", where), f"{where} report.json")
        for what in ("result", "job", "report"):
            if not isinstance(out[what], dict):
                raise RefusalError(f"{where}: {what}.json is not an object")
        return out
    edir = root / ENTRY
    rows_path = _w1_member(root, edir / W1_ROWS[kind].format(tune=tune), where)
    out["rows_rel"] = reader.rel(rows_path)
    out["rows"], out["record"], out["doc"] = _w1_rows(reader, kind, rows_path, where)
    out["manifest"] = reader.read_json(_w1_member(root, edir / W1_MANIFEST[kind].format(tune=tune), where),
                                       f"{where} manifest")
    if not isinstance(out["manifest"], dict):
        raise RefusalError(f"{where}: manifest is not an object")
    if kind == "math500":
        out["score"] = reader.read_json(_w1_member(root, edir / f"math500.{tune}.score.json", where),
                                        f"{where} score.json")
        if not isinstance(out["score"], dict):
            raise RefusalError(f"{where}: score.json is not an object")
    return out


def load_ids(reader):
    ids = reader.read_json(reader.root / "p426" / "ids.json", "p426/ids.json")
    axes = ids.get("axes") if isinstance(ids, dict) else None
    if not isinstance(axes, dict):
        raise RefusalError("p426/ids.json has no axes")
    out = {}
    for kind in ("math500", "cjudge", "vision", "reasoning"):
        ax = axes.get(kind)
        if not isinstance(ax, dict):
            raise RefusalError(f"p426/ids.json has no axes.{kind}")
        blocks = {}
        for b, key in W1_IDS_BLOCK.items():
            lst = ax.get(key)
            if not isinstance(lst, list) or not lst:
                raise RefusalError(f"p426/ids.json axes.{kind}.{key} is not a non-empty list")
            if len(set(map(json.dumps, lst))) != len(lst):
                raise RefusalError(f"p426/ids.json axes.{kind}.{key} lists an item twice")
            blocks[b] = list(lst)
        overlap = sorted(set(map(json.dumps, blocks["b1"])) & set(map(json.dumps, blocks["b2"])))
        if overlap:
            raise RefusalError(f"p426/ids.json axes.{kind}: blocks overlap ({overlap[:5]})")
        out[kind] = blocks
        if kind == "reasoning":
            rs = ax.get("request_seeds")
            if not isinstance(rs, dict):
                raise RefusalError("p426/ids.json axes.reasoning has no request_seeds")
            out["request_seeds"] = rs
    return out


# ------------------------------------------------------------------------------------------------ Wave 1 rules
def _w1_receipt_reasons(kind, m):
    r, leg, arm = m["receipt"], m["leg"], m["arm"]
    want_kind = "qualify" if kind == "m1" else kind
    reasons = []
    if r.get("verdict") != "VALID":
        reasons.append(f"rule 1: {arm} {leg} receipt verdict {r.get('verdict')!r} != 'VALID'")
    if r.get("problems") != []:
        reasons.append(f"rule 1: {arm} {leg} receipt problems {r.get('problems')!r} != []")
    for field, want in (("name", leg), ("arm", arm), ("kind", want_kind)):
        if r.get(field) != want:
            reasons.append(f"rule 1: {arm} {leg} receipt {field} {r.get(field)!r} != {want!r}")
    if kind == "m1" and m["result"].get("status") != "ok":
        reasons.append(f"rule 1: {arm} {leg} m1 result.json status {m['result'].get('status')!r} != 'ok'")
    return reasons


def _w1_scrub_reasons(reader, m, soft=False):
    """Every SCRUB_MANIFEST path under benchmark/results/ re-verifies against rows_root. Returns (reasons, n_ok, n).
    `soft` (smokes, coverage only): an unreadable / out-of-root file is a recorded problem, not a refusal."""
    files = m["scrub"].get("files")
    leg, arm = m["leg"], m["arm"]
    if not isinstance(files, dict):
        return [f"rule 1: {arm} {leg} SCRUB_MANIFEST.json has no files map"], 0, 0
    reasons, ok, n = [], 0, 0
    for path in sorted(files):
        rec = files[path]
        if not isinstance(path, str) or not path.startswith(SCRUB_PREFIX):
            continue
        n += 1
        rel = path[len(SCRUB_PREFIX):]
        want = rec.get("published_sha256") if isinstance(rec, dict) else None
        if ".." in rel.split("/") or rel.startswith("/"):
            reasons.append(f"rule 1: {arm} {leg} SCRUB path {path!r} is not under {SCRUB_PREFIX}")
            continue
        try:
            data = reader.try_read_bytes(reader.root / rel)
        except RefusalError as exc:
            if not soft:
                raise
            reasons.append(f"rule 1: {arm} {leg} SCRUB file {rel}: {exc}")
            continue
        if data is None:
            reasons.append(f"rule 1: {arm} {leg} SCRUB file {rel} is missing")
            continue
        got = hashlib.sha256(data).hexdigest()
        if got != want:
            reasons.append(f"rule 1: {arm} {leg} SCRUB file {rel} sha256 {got} != published_sha256 {want}")
            continue
        ok += 1
    return reasons, ok, n


def _strip_frozen_sha(pins):
    return {k: v for k, v in pins.items() if k != "frozen_sha"} if isinstance(pins, dict) else pins


def _diff_values(a, b, la="off", lb="on"):
    """`field: <la> X <lb> Y` for each top-level field that differs (both values named; fix 13)."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return f"{la} {a!r} {lb} {b!r}"
    missing = object()
    parts = []
    for k in sorted(set(a) | set(b), key=str):
        va, vb = a.get(k, missing), b.get(k, missing)
        if va != vb:
            parts.append(f"{k}: {la} {'(absent)' if va is missing else repr(va)} {lb} "
                         f"{'(absent)' if vb is missing else repr(vb)}")
    return "; ".join(parts)


def _w1_pins_reasons(frozen, frozen_sha, off, on):
    reasons = []
    po, pn = off["receipt"].get("pins"), on["receipt"].get("pins")
    if _strip_frozen_sha(po) != _strip_frozen_sha(pn):
        reasons.append(f"rule 2a: receipt pins (without frozen_sha) differ between "
                       f"off and on: {_diff_values(_strip_frozen_sha(po), _strip_frozen_sha(pn))}")
    for m in (off, on):
        r, arm, leg = m["receipt"], m["arm"], m["leg"]
        pins = r.get("pins") if isinstance(r.get("pins"), dict) else {}
        state = r.get("state") if isinstance(r.get("state"), dict) else {}
        if _strip_frozen_sha(pins) != frozen:
            reasons.append(f"rule 2a: {arm} {leg} receipt pins (without frozen_sha) != run/frozen.s2.json: "
                           f"{_diff_values(_strip_frozen_sha(pins), frozen, arm, 'frozen')}")
        if pins.get("frozen_sha") != frozen_sha:
            reasons.append(f"rule 2a: {arm} {leg} pins.frozen_sha {pins.get('frozen_sha')!r} != sha256 of "
                           f"frozen.s2.json {frozen_sha}")
        if state.get("frozen_sha") != frozen_sha:
            reasons.append(f"rule 2a: {arm} {leg} state.frozen_sha {state.get('frozen_sha')!r} != sha256 of "
                           f"frozen.s2.json {frozen_sha}")
        want = frozen.get(f"stack_head_{arm}")
        if state.get("stack_head") != want:
            reasons.append(f"rule 2a: {arm} {leg} state.stack_head {state.get('stack_head')!r} != "
                           f"frozen stack_head_{arm} {want!r}")
    return reasons


def _w1_registry_reasons(kind, frozen, registry_git, off, on):
    reasons = []
    for m in (off, on):
        arm, leg = m["arm"], m["leg"]
        want = frozen.get(f"registry_{arm}_sha")
        got_git = registry_git[arm]
        if got_git != want:
            reasons.append(f"rule 2b: {arm} sha256 of git show stack_head_{arm}:main_models.yaml {got_git} != "
                           f"frozen registry_{arm}_sha {want!r}")
        if kind == "m1":
            got = m["report"].get("registry_sha256")
            if got != want:
                reasons.append(f"rule 2b: {arm} {leg} m1 report.registry_sha256 {got!r} != registry_{arm}_sha {want!r}")
        else:
            reg = m["manifest"].get("registry")
            got = reg.get("sha256") if isinstance(reg, dict) else None
            if got != want:
                reasons.append(f"rule 2b: {arm} {leg} manifest registry.sha256 {got!r} != registry_{arm}_sha {want!r}")
    return reasons


def worker_argv(cmdline, arm):
    """Receipt `worker.cmdline` → normalised multiset items: split on " --" after dropping the PID token; the leg's
    own arm worktree path component `stack-p426-s2-<arm>` → `stack-p426-s2-ARM` (the other arm's is left as is)."""
    from collections import Counter

    if not isinstance(cmdline, str) or not cmdline.strip():
        return None
    first, _, rest = cmdline.strip().partition(" ")
    if not first.isdigit():
        return None
    parts = rest.split(" --")
    items = [parts[0]] + ["--" + p for p in parts[1:]]
    own = _arm_path_re(arm)
    return Counter(own.sub("stack-p426-s2-ARM", p) for p in items)


def _foreign_arm_items(items, arm):
    """argv items naming the OTHER arm's worktree component (fix 3)."""
    other = _arm_path_re("on" if arm == "off" else "off")
    return sorted(p for p in (items or {}) if other.search(p))


def job_argv(argv, arm):
    """M1 `job.json` argv list → multiset of "flag value" / "flag" items (paths normalised as for the worker)."""
    from collections import Counter

    if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
        return None
    own = _arm_path_re(arm)
    items, i = [], 0
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("--") and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            items.append(f"{tok} {argv[i + 1]}")
            i += 2
        else:
            items.append(tok)
            i += 1
    return Counter(own.sub("stack-p426-s2-ARM", p) for p in items)


def _w1_argv_reasons(kind, off, on):
    from collections import Counter

    if kind == "m1":
        a, b = job_argv(off["job"].get("argv"), "off"), job_argv(on["job"].get("argv"), "on")
        what = "job.json argv"
    else:
        a = worker_argv((off["receipt"].get("worker") or {}).get("cmdline")
                        if isinstance(off["receipt"].get("worker"), dict) else None, "off")
        b = worker_argv((on["receipt"].get("worker") or {}).get("cmdline")
                        if isinstance(on["receipt"].get("worker"), dict) else None, "on")
        what = "receipt worker.cmdline"
    if a is None or b is None:
        return [f"rule 2c: {what} missing or unparsable ({'off' if a is None else 'on'})"]
    reasons = []
    for arm, items, m in (("off", a, off), ("on", b, on)):
        foreign = _foreign_arm_items(items, arm)
        if foreign:
            reasons.append(f"rule 2c: {arm} {m['leg']} {what} names the other arm's worktree "
                           f"(stack-p426-s2-{'on' if arm == 'off' else 'off'}): {foreign}")
    on_extra, off_extra = sorted((b - a).elements()), sorted((a - b).elements())
    if Counter(on_extra) != Counter(RESTORE_DELTA):
        reasons.append(f"rule 2c: {what} ON − OFF {on_extra} != the restore delta {sorted(RESTORE_DELTA)}")
    if off_extra:
        reasons.append(f"rule 2c: {what} OFF − ON {off_extra} != []")
    return reasons


def _drafts(kind, row):
    """[(label, draft dict)] of one row: turn 1 (and A3 turn 2)."""
    out = [("draft", row.get("draft"))]
    if kind == "vision":
        t2 = row.get("turn2")
        out.append(("turn2.draft", t2.get("draft") if isinstance(t2, dict) else None))
    return out


def _draft_problem(arm, d):
    if arm == "off" and d is None:
        return None                                   # A4 OFF rows carry `draft: null`: every draft value null
    if not isinstance(d, dict):
        return "no draft object"
    if arm == "off":
        bad = sorted(k for k, v in d.items() if v is not None)
        return f"non-null {bad}" if bad else None
    n, a = d.get("draft_n"), d.get("draft_n_accepted")
    if d.get("draft_kind") != "mtp":
        return f"draft_kind {d.get('draft_kind')!r} != 'mtp'"
    if not (isinstance(n, int) and not isinstance(n, bool) and n > 0):
        return f"draft_n {n!r} not > 0"
    if not (isinstance(a, int) and not isinstance(a, bool) and 0 <= a <= n):
        return f"draft_n_accepted {a!r} not in [0, draft_n]"
    return None


def _w1_equal_reasons(kind, off, on):
    """Rule 2d: everything else equal, and the per-row draft state matches the arm."""
    reasons = []
    if kind == "m1":
        ro, rn = off["result"], on["result"]
        so = {k: v for k, v in (ro.get("served") or {}).items() if k not in M1_SERVED_ARM_FIELDS}
        sn = {k: v for k, v in (rn.get("served") or {}).items() if k not in M1_SERVED_ARM_FIELDS}
        if so != sn:
            reasons.append(f"rule 2d: m1 served (except {list(M1_SERVED_ARM_FIELDS)}) differs: off {so} on {sn}")
        po = {k: v for k, v in (ro.get("snapshots") or {}).items() if k != "--draft-model"}
        pn = {k: v for k, v in (rn.get("snapshots") or {}).items() if k != "--draft-model"}
        if po != pn:
            reasons.append(f"rule 2d: m1 snapshots (except --draft-model) differ: off {po} on {pn}")
        for f in M1_REPORT_EQUAL:
            if off["report"].get(f) != on["report"].get(f):
                reasons.append(f"rule 2d: m1 report.{f} differs: off {off['report'].get(f)!r} on "
                               f"{on['report'].get(f)!r}")
        qo, qn = m1_qualify(off), m1_qualify(on)
        for f in ("generate_seed",):
            if qo.get(f) != qn.get(f):
                reasons.append(f"rule 2d: m1 qualify.{f} differs: off {qo.get(f)!r} on {qn.get(f)!r}")
        szo, szn = (qo.get("prompt") or {}).get("sized"), (qn.get("prompt") or {}).get("sized")
        if szo != szn or szo is None:
            reasons.append(f"rule 2d: m1 qualify.prompt.sized differs or is missing: off {szo!r} on {szn!r}")
        return reasons
    for f in ("sampling", "kv"):
        if off["manifest"].get(f) != on["manifest"].get(f):
            reasons.append(f"rule 2d: manifest {f} differs between off and on: "
                           f"{_diff_values(off['manifest'].get(f), on['manifest'].get(f))}")
    reasons += _w1_budget_reasons(kind, off, on)
    for m in (off, on):
        bad = []
        for r in m["rows"]:
            for label, d in _drafts(kind, r["row"]):
                why = _draft_problem(m["arm"], d)
                if why:
                    bad.append(f"{r['id']} {label}: {why}")
        if bad:
            reasons.append(f"rule 2d: {m['arm']} rows' draft state does not match the arm ({len(bad)}): {bad[:5]}")
    return reasons


SHA256_RE = re.compile(r"[0-9a-f]{64}")
THINKING_BUDGET = 81920
BUDGET_ROW_KINDS = ("math500", "cjudge")


def _w1_budget_reasons(kind, off, on):
    """Fix 2: the thinking budget is 81920 everywhere the pair records it — every row manifest's
    `sampling.thinking_budget`, the A4 file's `params.thinking_budget`, and (A1 / A2) every row's `thinking_budget`,
    equal per key across the pair; else the pair is rejected with both values."""
    reasons = []
    for m in (off, on):
        samp = m["manifest"].get("sampling")
        got = samp.get("thinking_budget") if isinstance(samp, dict) else None
        if got != THINKING_BUDGET:
            reasons.append(f"rule 2d: {m['arm']} {m['leg']} manifest sampling.thinking_budget {got!r} != "
                           f"{THINKING_BUDGET}")
        if kind == "reasoning":
            params = (m.get("doc") or {}).get("params")
            got = params.get("thinking_budget") if isinstance(params, dict) else None
            if got != THINKING_BUDGET:
                reasons.append(f"rule 2d: {m['arm']} {m['leg']} reasoning params.thinking_budget {got!r} != "
                               f"{THINKING_BUDGET}")
    if kind in BUDGET_ROW_KINDS:
        bo = {json.dumps(r["id"]): r["row"].get("thinking_budget") for r in off["rows"]}
        bn = {json.dumps(r["id"]): r["row"].get("thinking_budget") for r in on["rows"]}
        bad = []
        for k in sorted(set(bo) | set(bn)):
            vo, vn = bo.get(k), bn.get(k)
            if vo != vn or vo != THINKING_BUDGET:
                bad.append(f"{json.loads(k)}: off {vo!r} on {vn!r}")
        if bad:
            reasons.append(f"rule 2d: row thinking_budget differs across the pair or != {THINKING_BUDGET} per key "
                           f"({len(bad)}): {bad[:5]}")
    return reasons


def m1_qualify(m):
    try:
        q = m["result"]["requests"][0]["qualify"]
    except (KeyError, IndexError, TypeError):
        return {}
    return q if isinstance(q, dict) else {}


def _identity_sha(kind, row):
    """Rule 7 identity value; A1 / A2 recompute `content_sha256` and refuse a mismatch."""
    field = "description" if kind == "vision" else "content"
    text = row.get(field)
    if not isinstance(text, str):                                  # fix 4: identity text must be a string
        raise RefusalError(f"rule 7: {kind} row {row.get('id')}: identity text `{field}` is "
                           f"{type(text).__name__}, not a string")
    got = sha256_text(text)
    if kind in ("math500", "cjudge"):
        want = row.get("content_sha256")
        if not (isinstance(want, str) and SHA256_RE.fullmatch(want)):
            raise RefusalError(f"rule 7: {kind} row {row.get('id')}: content_sha256 {want!r} is not a 64-hex sha256")
        if got != want:
            raise RefusalError(f"rule 7: {kind} row {row.get('id')}: content_sha256 {want!r} != "
                               f"sha256(content) {got}")
    return got


def _w1_keys(kind, block, ids, off, on):
    """Rule 3 + rule 7. Returns (accepted keys, rejected keys, content_sha256 verified count)."""
    planned = ids[kind][block]
    verified = 0
    by_arm = {}
    for m in (off, on):
        where = f"pair {kind} {block} {m['arm']} {m['leg']}"
        rows = m["rows"]
        seen = {}
        for r in rows:
            k = json.dumps(r["id"])
            if k in seen:
                raise RefusalError(f"{where}: duplicate row key ({block}, {r['id']})")
            seen[k] = r
        if len(rows) != len(planned):
            raise RefusalError(f"{where}: row count {len(rows)} != block size {len(planned)}")
        if set(seen) != {json.dumps(x) for x in planned}:
            stray = sorted(set(seen) - {json.dumps(x) for x in planned})
            raise RefusalError(f"{where}: row ids != the ids.json {W1_IDS_BLOCK[block]} list (outside: {stray[:5]})")
        for r in rows:
            r["identity"] = _identity_sha(kind, r["row"])
            if kind in ("math500", "cjudge"):
                verified += 1
        by_arm[m["arm"]] = seen
    accepted, rejected = [], []
    for x in planned:
        k = json.dumps(x)
        ro, rn = by_arm["off"][k], by_arm["on"][k]
        key = [block, x, ro["seed"]]
        if kind == "reasoning":
            want = ids["request_seeds"].get(str(x))
            bad = [f"{arm} sampler_seed {r['seed']} != request_seeds[{x}] {want!r}"
                   for arm, r in (("off", ro), ("on", rn)) if r["seed"] != want]
            if bad:
                rejected.append(dict(key=key, reason="seed mismatch: " + "; ".join(bad)))
                continue
        if ro["seed"] != rn["seed"]:                   # fix 16: one key shape per axis, accepted or rejected
            rejected.append(dict(key=key, reason=f"seed mismatch: off {ro['seed']} on {rn['seed']} "
                                                 f"(the key is in one arm only; key seed = the OFF seed)"))
            continue
        accepted.append(dict(key=key, identical=ro["identity"] is not None and ro["identity"] == rn["identity"],
                             off_sha256=ro["identity"], on_sha256=rn["identity"]))
    return accepted, rejected, verified


SMOKE_LEG_RE = re.compile(r"^(math500|cjudge|vision|reasoning|m1)-p426s2-(off|on)-smoke$")


def _pair_reason(kind, block, off, on, reason):
    """Fixes 12 / 13: every rejection names the pair (`rule N: pair <kind> <block>: …`) and passes `mask_paths`."""
    rule, sep, rest = reason.partition(": ")
    tag = f"pair {kind} {block}"
    if sep and rule.startswith("rule ") and tag not in rest:
        reason = f"{rule}: {tag}: {rest}"
    return mask_paths(reason)


def _w1_smoke_scrub(rows_root):
    """Coverage only (fix 1; never a pair member, never scored, never a refusal): each smoke leg's SCRUB_MANIFEST
    re-verified through its own reader. A missing / unreadable / mismatched smoke file is recorded in `problems`;
    the files read stay out of B8 `inputs` and are listed here with their sha256 (`read`)."""
    base = Path(rows_root) / "p426" / W1
    out = {}
    for d in sorted(p for p in base.iterdir() if p.is_dir() and SMOKE_LEG_RE.match(p.name)):
        sreader = Reader(rows_root, confine=True)
        problems, ok, n = [], 0, 0
        try:
            if not (d / "SCRUB_MANIFEST.json").is_file():
                problems.append(f"smoke {d.name}: SCRUB_MANIFEST.json is missing")
            else:
                scrub = sreader.read_json(d / "SCRUB_MANIFEST.json", f"smoke {d.name} SCRUB_MANIFEST.json")
                if not isinstance(scrub, dict):
                    problems.append(f"smoke {d.name}: SCRUB_MANIFEST.json is not an object")
                else:
                    r, ok, n = _w1_scrub_reasons(sreader, dict(scrub=scrub, leg=d.name,
                                                               arm=SMOKE_LEG_RE.match(d.name).group(2)), soft=True)
                    problems += r
        except RefusalError as exc:
            problems.append(f"smoke {d.name}: {exc}")
        out[d.name] = dict(verified=ok, files=n, problems=[mask_paths(p) for p in problems],
                           read=dict(sorted(sreader.inputs.items())))
    return out


def verify_wave1(results_root, rows_root, repo):
    """B8 for Wave 1: one record per (kind, block), kinds math500 / cjudge / vision / reasoning / m1."""
    check_roots(results_root, rows_root)
    reader = Reader(rows_root, confine=True)
    run = reader.root / "p426" / W1 / "run" / "frozen.s2.json"
    frozen_bytes = reader.read_bytes(_w1_member(reader.root, run, "wave1.s2/run/frozen.s2.json"),
                                     "wave1.s2/run/frozen.s2.json")
    frozen = _parse_json(frozen_bytes, "wave1.s2/run/frozen.s2.json")
    if not isinstance(frozen, dict):
        raise RefusalError("wave1.s2/run/frozen.s2.json is not an object")
    frozen_sha = hashlib.sha256(frozen_bytes).hexdigest()
    ids = load_ids(reader)
    top = repo_top(repo)
    registry_git = {}
    for arm in ("off", "on"):
        head = frozen.get(f"stack_head_{arm}")
        commit = resolve_commit(top, head, f"frozen stack_head_{arm}")
        registry_git[arm] = hashlib.sha256(git_bytes(top, ["show", f"{commit}:main_models.yaml"],
                                                     f"git show stack_head_{arm}:main_models.yaml")).hexdigest()
    pairs = []
    for kind in W1_KINDS:
        for block in W1_BLOCKS:
            off, on = (load_w1_leg(reader, kind, arm, block) for arm in ("off", "on"))
            reasons, scrub_ok, scrub_n = [], 0, 0
            for m in (off, on):
                reasons += _w1_receipt_reasons(kind, m)
            for m in (off, on):
                r, ok, n = _w1_scrub_reasons(reader, m)
                reasons += r
                scrub_ok += ok
                scrub_n += n
            reasons += _w1_pins_reasons(frozen, frozen_sha, off, on)
            reasons += _w1_registry_reasons(kind, frozen, registry_git, off, on)
            reasons += _w1_argv_reasons(kind, off, on)
            reasons += _w1_equal_reasons(kind, off, on)
            reasons = [_pair_reason(kind, block, off, on, r) for r in reasons]
            if kind == "m1":
                keys, rejected, verified = [dict(key=[block], identical=False, identity="none (M1)")], [], 0
            else:
                keys, rejected, verified = _w1_keys(kind, block, ids, off, on)
                rejected = [dict(k, reason=mask_paths(k["reason"])) for k in rejected]
            speed_valid = off["receipt"].get("speed_valid") is True and on["receipt"].get("speed_valid") is True
            n_ident = sum(1 for k in keys if k["identical"])
            pairs.append(dict(
                kind=kind, axis=W1_AXIS[kind], block=block, off=off["leg"], on=on["leg"], tune_off=off["tune"],
                tune_on=on["tune"], accepted=not reasons, reasons=reasons, speed_valid=speed_valid,
                labels=[] if speed_valid else ["power-invalid"], keys_accepted=len(keys), keys_rejected=rejected,
                keys=keys, identical=dict(n=n_ident, of=0 if kind == "m1" else len(keys)),
                identity_basis={"math500": "content_sha256 (recomputed)", "cjudge": "content_sha256 (recomputed)",
                                "vision": "sha256(description)", "reasoning": "sha256(content)",
                                "m1": "none"}[kind],
                scrub=dict(verified=scrub_ok, files=scrub_n), content_sha256_verified=verified,
                speed_problems=dict(off=off["receipt"].get("speed_problems"), on=on["receipt"].get("speed_problems")),
                log=dict(off=off["receipt"].get("log"), on=on["receipt"].get("log"))))
    smokes = _w1_smoke_scrub(rows_root)
    full_ok, full_n = sum(p["scrub"]["verified"] for p in pairs), sum(p["scrub"]["files"] for p in pairs)
    scrub_cov = dict(full_legs=dict(verified=full_ok, files=full_n), smokes=smokes,
                     smoke_total=dict(verified=sum(s["verified"] for s in smokes.values()),
                                      files=sum(s["files"] for s in smokes.values())),
                     note="full legs gate their pair (rule 1); smoke legs are re-verified for coverage only, never "
                          "scored")
    scrub_cov["total"] = dict(verified=full_ok + scrub_cov["smoke_total"]["verified"],
                              files=full_n + scrub_cov["smoke_total"]["files"])
    return dict(axis="wave1", generator="bench.p426_verify", inputs=dict(sorted(reader.inputs.items())), pairs=pairs,
                scrub_coverage=scrub_cov,
                frozen=dict(sha256=frozen_sha, stack_head_off=frozen.get("stack_head_off"),
                            stack_head_on=frozen.get("stack_head_on"), registry_off_sha=frozen.get("registry_off_sha"),
                            registry_on_sha=frozen.get("registry_on_sha")),
                registry_git_sha256=registry_git, restore_delta=sorted(RESTORE_DELTA))


# -------------------------------------------------------------------------------------------------------- git
def repo_top(repo):
    import subprocess

    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], check=True, cwd=Path(repo), capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        raise RefusalError("--repo is not a git work tree") from None
    return Path(out.stdout.decode("utf-8").strip())


def git_bytes(top, args, what):
    import subprocess

    try:
        return subprocess.run(["git", *args], check=True, cwd=top, capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError):
        raise RefusalError(f"{what}: git {args[0]} failed") from None


def resolve_commit(top, sha, what):
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{7,64}", sha):
        raise RefusalError(f"{what}: {sha!r} is not a commit sha")
    out = git_bytes(top, ["rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"], f"{what} {sha} does not resolve")
    return out.decode("utf-8").strip()


def _closure_at(top, commit, tmp):
    """Repo-relative files of the python_closure of CROSS_WAVE_ENTRIES at `commit` (its `*.py` tree only)."""
    import io
    import tarfile

    from bench.identity_closure import python_closure

    data = git_bytes(top, ["archive", "--format=tar", commit, "--", ":(glob)**/*.py"], f"git archive {commit}")
    dest = Path(tmp) / commit
    dest.mkdir()
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(dest, filter="data")
    dres = dest.resolve()
    files = set()
    for entry in CROSS_WAVE_ENTRIES:
        path = dest / entry
        if not path.is_file():
            raise RefusalError(f"rule 6: {entry} is missing at {commit}")
        try:
            closure = python_closure(path, dest)
        except (SyntaxError, OSError, ValueError) as exc:
            raise RefusalError(f"rule 6: python_closure({entry}) at {commit} failed ({type(exc).__name__})") from None
        files |= {p.resolve().relative_to(dres).as_posix() for p in closure}
    return files


def _registry_doc(top, commit):
    import yaml

    try:
        doc = yaml.safe_load(git_bytes(top, ["show", f"{commit}:main_models.yaml"], f"git show {commit}:main_models.yaml"))
    except yaml.YAMLError:
        raise RefusalError(f"rule 6: main_models.yaml at {commit} is not YAML") from None
    if not isinstance(doc, dict):
        raise RefusalError(f"rule 6: main_models.yaml at {commit} is not a mapping")
    return doc


def _registry_entry(doc):
    models = doc.get("models")
    hits = [m for m in models if isinstance(m, dict) and m.get("name") == ENTRY] if isinstance(models, list) else []
    return hits[0] if len(hits) == 1 else None


def _gitlinks(top, commit):
    out = git_bytes(top, ["ls-tree", commit, "--", *GITLINKS], f"git ls-tree {commit}").decode("utf-8")
    links = {}
    for line in out.splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "commit":
            links[path] = parts[2]
    return dict(sorted(links.items()))


def cross_wave(repo, wave1_off, wave2_off):
    """Rule 6: the generation-path file list of `git diff --name-only <wave1_off> <wave2_off>`; non-empty → flag."""
    import tempfile

    top = repo_top(repo)
    c1 = resolve_commit(top, wave1_off, "rule 6 wave1_off")
    c2 = resolve_commit(top, wave2_off, "rule 6 wave2_off")
    closure = set()
    with tempfile.TemporaryDirectory(prefix="p426-rule6-") as tmp:
        for c in (c1, c2) if c1 != c2 else (c1,):
            closure |= _closure_at(top, c, tmp)
    closure_files = sorted(closure)
    paths = list(CROSS_WAVE_FIXED) + [p for p in closure_files if p not in CROSS_WAVE_FIXED]
    out = git_bytes(top, ["diff", "--name-only", c1, c2, "--", *paths], "rule 6 git diff").decode("utf-8")
    files = sorted(line for line in out.splitlines() if line)
    d1, d2 = _registry_doc(top, c1), _registry_doc(top, c2)
    e1, e2 = _registry_entry(d1), _registry_entry(d2)
    g1, g2 = _gitlinks(top, c1), _gitlinks(top, c2)
    return dict(wave1_off=c1, wave2_off=c2, paths=paths, closure_files=closure_files, files=files, flag=bool(files),
                entry_equal=e1 is not None and e1 == e2, entry_present=dict(wave1_off=e1 is not None,
                                                                            wave2_off=e2 is not None),
                globals_equal={k: v for k, v in d1.items() if k != "models"} == {k: v for k, v in d2.items()
                                                                                 if k != "models"},
                gitlinks=dict(wave1_off=g1, wave2_off=g2), gitlinks_equal=g1 == g2,
                qualify=f"covered by gitlink {GITLINKS[0]}", qualify_entry=QUALIFY_ENTRY)


def verify_all(results_root, rows_root, repo):
    """One B8 record: A7 (step 1, unchanged) + Wave 1 + the rule-6 cross-wave check. `inputs` = the union keyed
    rows_root-relative (A7 inputs are results_root-relative inside `axes.A7` and carry the `p426/` prefix here)."""
    check_roots(results_root, rows_root)
    a7 = verify_a7(results_root)
    w1 = verify_wave1(results_root, rows_root, repo)
    reader = Reader(rows_root, confine=True)
    v8 = reader.read_json(Path(rows_root) / "p426" / WAVE / "run" / "v8_base.json", "wave2/run/v8_base.json")
    if not isinstance(v8, dict):
        raise RefusalError("wave2/run/v8_base.json is not an object")
    cw = cross_wave(repo, w1["frozen"]["stack_head_off"], v8.get("off_commit"))
    union = {f"p426/{k}": v for k, v in a7["inputs"].items()}
    for src in (w1["inputs"], reader.inputs):
        for k, v in src.items():
            if union.get(k, v) != v:
                raise RefusalError(f"input {k} changed while B8 read it")
            union[k] = v
    for k in union:                                   # fix 5: committed-only inputs, A7 included under `all`
        reader.check_confined(Path(rows_root) / k, "B8 all")
    return dict(generator="bench.p426_verify", version="p613-step2", axes=dict(A7=a7, wave1=w1), cross_wave=cw,
                inputs=dict(sorted(union.items())))


# ===================================================================================================== M76 B3: lever kv
# `docs/specs/m76-b3-b5-p426-kv-lever.md`: a pair is two M76 KV arms (`p426_plan.KV_PAIRS`, reference → treatment), both MTP ON,
# whose legs differ ONLY in `{kv_bits, tq4_attention}` (registry), `--kv-bits` / `--tq4-attention` (worker argv) and the KV
# fields of the manifests; everything else (sampling, budgets, items, seeds, box, M50, receipts VALID, drafter) equal.
KV_ROOT = "m76"
KV_REPO_PREFIX = "benchmark/results/m76/"          # the KV lever's HARVEST `published` prefix (results_root = <rows>/m76)
KV_W1 = "m76/wave1"
KV_W2 = "wave2"
KV_W1_KINDS = ("math500", "cjudge", "vision", "reasoning", "m1", "longctx")
KV_W1_AXIS = dict(W1_AXIS, longctx="A5")
KV_BLOCKS = {"b1": (1, 1), "b2": (2, 1), "t2-b1": (1, 2), "t2-b2": (2, 2)}      # block label -> (block, tier)
KV_TIER2 = ("t2-b1", "t2-b2")
KV_TIERED_KINDS = ("math500", "longctx")            # v1.4: A5 has a tier 2 (its second look), as Math500
KV_MANIFEST_KV_FIELDS = ("kv_bits", "tq4_attention")
KV_M1_SERVED_FIELDS = ("kv_bits", "tq4_attention", "kv", "kv_arm")
KV_DENY_PATTERNS = (
    (re.compile(r"smoke"), "a smoke member"),
    (re.compile(r"(^|/)archive(/|$)"), "an archive/ member"),
    (re.compile(r"(^|[/.-])p426"), "a P426 (mtp lever) member"),
)
KV_ATTEMPT_RE = re.compile(r"^tg1-m76-(n16|x|v)-(pilot|s1|s2|s3|reload)\.a(\d+)$")
KV_ALLOWED_DIFFERENCES = ("argv.worker",)


def _kv_path_re(arm):
    """The leg's OWN arm worktree component (`m76-f45-<arm>` from `p475_kv prepare`, or `m76-q-<arm>`) normalises."""
    return re.compile(rf"(?:m76-f45|m76-q)-{re.escape(arm)}(?=/|$)")


def _kv_foreign(tokens, arm):
    others = [a for a in ("n16", "x", "v") if a != arm]
    return sorted(t for t in tokens if any(_kv_path_re(o).search(t) for o in others))


def kv_leg_of(kind, arm, label):
    block, tier = KV_BLOCKS[label]
    from bench.p426_plan import kv_leg_name

    return kv_leg_name(kind, arm, block, tier)


def kv_tune_of(arm, label, kind=None):
    """The leg's tune; A5 (`kind="longctx"`) has its own (`m76-<arm>-lc-b<k>`, erratum v1.2)."""
    block, tier = KV_BLOCKS[label]
    from bench.p426_plan import kv_tune

    return kv_tune(arm, block, False, tier, axis=kind)


def _kv_member(rows_root, path, where, want_dir=False):
    """A KV Wave 1 member path: present, under rows_root, never a smoke / archive / P426 (mtp) location."""
    path = Path(path)
    ok = path.is_dir() if want_dir else path.is_file()
    if not ok:
        raise RefusalError(f"{where}: required {'directory' if want_dir else 'file'} {_rel_or_name(rows_root, path)} is missing")
    try:
        rel = path.resolve().relative_to(Path(rows_root).resolve()).as_posix()
    except (OSError, ValueError):
        raise RefusalError(f"{where}: {path.name} resolves outside rows_root (deny-listed)") from None
    for pattern, what in KV_DENY_PATTERNS:
        if pattern.search(rel):
            raise RefusalError(f"{where}: {rel} is deny-listed ({what})")
    return path


def load_kv_ids(reader):
    """`m76/ids.json` read structurally (the planner rebuilds it; B8 reads the committed file): per kind its block lists, none
    overlapping; A5's items, per-row sampler seeds and token budget; A4's request seeds. v1.4: A5's tier-2 blocks
    (`axes.longctx.tier2`) when the plan has a second look; A5's `items` are tier 1 then tier 2 (nested)."""
    doc = reader.read_json(reader.root / KV_ROOT / "ids.json", "m76/ids.json")
    axes = doc.get("axes") if isinstance(doc, dict) else None
    if not isinstance(axes, dict):
        raise RefusalError("m76/ids.json has no axes")
    out = {}
    for kind in ("math500", "cjudge", "vision", "reasoning", "longctx"):
        ax = axes.get(kind)
        if not isinstance(ax, dict):
            raise RefusalError(f"m76/ids.json has no axes.{kind}")
        blocks = {"b1": ax.get("block1"), "b2": ax.get("block2")}
        if kind == "math500" or (kind == "longctx" and "tier2" in ax):
            t2 = ax.get("tier2") if isinstance(ax.get("tier2"), dict) else {}
            blocks.update({"t2-b1": t2.get("block1"), "t2-b2": t2.get("block2")})
        seen = set()
        for label, lst in blocks.items():
            if not isinstance(lst, list) or not lst:
                raise RefusalError(f"m76/ids.json axes.{kind}.{label} is not a non-empty list")
            keys = [json.dumps(x) for x in lst]
            if len(set(keys)) != len(keys) or seen & set(keys):
                raise RefusalError(f"m76/ids.json axes.{kind}: {label} repeats an item or overlaps another block")
            seen |= set(keys)
        out[kind] = blocks
    rs = axes["reasoning"].get("request_seeds")
    lc = axes["longctx"]
    if not isinstance(rs, dict) or not isinstance(lc.get("sampler_seeds"), dict) or not isinstance(lc.get("items"), list):
        raise RefusalError("m76/ids.json lacks the A4 request seeds or the A5 items / sampler seeds")
    out["request_seeds"], out["longctx_seeds"] = rs, lc["sampler_seeds"]
    out["longctx_items"] = {i["id"]: i for i in lc["items"]}
    out["longctx_chain_len"] = lc.get("chain_len")
    out["longctx_budget"] = lc.get("budget") or {}
    lc_t1 = sorted(i for label in ("b1", "b2") for i in out["longctx"][label])
    lc_t2 = sorted(i for label in KV_TIER2 for i in out["longctx"].get(label) or [])
    lc_order = [i.get("id") for i in lc["items"] if isinstance(i, dict)]
    if (sorted(lc_order[:len(lc_t1)]) != lc_t1 or sorted(lc_order[len(lc_t1):]) != lc_t2
            or (lc.get("tier1") is not None and sorted(lc["tier1"]) != lc_t1)
            or ("tier2" in lc and sorted((lc["tier2"] or {}).get("items") or []) != lc_t2)):
        raise RefusalError("m76/ids.json axes.longctx.items are not tier 1 then tier 2 (nested) or its tier lists disagree")
    out["longctx_order"] = lc_order
    order = axes["math500"].get("order")
    t1 = [i for label in ("b1", "b2") for i in out["math500"][label]]
    t2 = [i for label in ("t2-b1", "t2-b2") for i in out["math500"][label]]
    if not isinstance(order, list) or sorted(order[:len(t1)]) != sorted(t1) or sorted(order[len(t1):]) != sorted(t2):
        raise RefusalError("m76/ids.json axes.math500.order is not tier 1 then tier 2 (nested)")
    out["math500_order"] = order
    return out


def _kv_longctx(reader, ldir, tune, ids, label, where, entry_dir):
    """A5's per-item results: `retrieval.<tune>.<id>.json` / `reasoning.<tune>.<id>.json` (records[0].rows, one row) and their
    manifests; rows `{id: item id, seed: sampler_seed, row}`."""
    rows, manifests = [], {}
    for iid in ids["longctx"][label]:
        item = ids["longctx_items"].get(iid)
        if item is None:
            raise RefusalError(f"{where}: {iid} is not an A5 item")
        stem = f"{'retrieval' if item['task'] == 'retrieval' else 'reasoning'}.{tune}.{iid}"
        doc = reader.read_json(_kv_member(reader.root, entry_dir / f"{stem}.json", where), f"{where} {iid} result")
        try:
            got = [r for rec in doc["records"] for r in rec["rows"]]
        except (KeyError, TypeError):
            raise RefusalError(f"{where}: {stem}.json has no records[].rows") from None
        if len(got) != 1 or not isinstance(got[0], dict):
            raise RefusalError(f"{where}: {stem}.json holds {len(got)} rows (one draw per A5 item)")
        seed = got[0].get("sampler_seed")
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise RefusalError(f"{where}: {stem}.json: the row has no integer sampler_seed")
        manifests[iid] = reader.read_json(_kv_member(reader.root, entry_dir / f"{stem}.manifest.json", where),
                                          f"{where} {iid} manifest")
        man = manifests[iid] if isinstance(manifests[iid], dict) else {}
        samp = man.get("sampling") if isinstance(man.get("sampling"), dict) else {}
        limit = (man.get("kv") or {}).get("max_kv_cache_size") if isinstance(man.get("kv"), dict) else None
        from bench.m76_ids import resolved_of

        # erratum v1.2: the row's OWN resolved budget — its prompt tokens, the leg's max_tokens / thinking budget, the served cap
        resolved, thinking = resolved_of(got[0], samp.get("max_tokens"), limit, samp.get("thinking_budget"))
        rows.append(dict(id=iid, seed=seed, row=dict(got[0], task=item["task"], rung=item["rung"], resolved_max_tokens=resolved,
                                                    resolved_thinking_budget=thinking,
                                                    thinking_budget=samp.get("thinking_budget"))))
    return rows, manifests


def load_kv_leg(reader, kind, arm, label, ids=None):
    """One KV Wave 1 leg (receipt, SCRUB manifest, its result files) from `m76/wave1/<leg>/` and `<entry>/<stem>…`."""
    root = reader.root
    leg, tune = kv_leg_of(kind, arm, label), kv_tune_of(arm, label, kind)
    where = f"pair {kind} {label} {arm} {leg}"
    ldir = _kv_member(root, root / KV_W1 / leg, where, want_dir=True)
    receipt = reader.read_json(_kv_member(root, ldir / f"{leg}.receipt.json", where), f"{where} receipt")
    scrub = reader.read_json(_kv_member(root, ldir / "SCRUB_MANIFEST.json", where), f"{where} SCRUB_MANIFEST.json")
    for doc, what in ((receipt, "receipt"), (scrub, "SCRUB_MANIFEST.json")):
        if not isinstance(doc, dict):
            raise RefusalError(f"{where}: {what} is not an object")
    out = dict(kind=kind, arm=arm, block=label, leg=leg, tune=tune, dir=ldir, receipt=receipt, scrub=scrub)
    if kind == "m1":
        mdir = ldir / "m1" / ENTRY
        for what, path in (("result", mdir / "result.json"), ("job", mdir / "job.json"), ("report", ldir / "m1" / "report.json")):
            out[what] = reader.read_json(_kv_member(root, path, where), f"{where} {what}.json")
            if not isinstance(out[what], dict):
                raise RefusalError(f"{where}: {what}.json is not an object")
        return out
    edir = root / ENTRY
    if kind == "longctx":
        out["rows"], out["manifests"] = _kv_longctx(reader, ldir, tune, ids, label, where, edir)
        out["manifest"] = next(iter(out["manifests"].values()), {})
        return out
    rows_path = _kv_member(root, edir / W1_ROWS[kind].format(tune=tune), where)
    out["rows_rel"] = reader.rel(rows_path)
    out["rows"], out["record"], out["doc"] = _w1_rows(reader, kind, rows_path, where)
    out["manifest"] = reader.read_json(_kv_member(root, edir / W1_MANIFEST[kind].format(tune=tune), where), f"{where} manifest")
    if not isinstance(out["manifest"], dict):
        raise RefusalError(f"{where}: manifest is not an object")
    if kind == "math500":
        out["score"] = reader.read_json(_kv_member(root, edir / f"math500.{tune}.score.json", where), f"{where} score.json")
    return out


def _kv_receipt_reasons(kind, m):
    r, leg, arm = m["receipt"], m["leg"], m["arm"]
    reasons = []
    if r.get("verdict") != "VALID":
        reasons.append(f"rule 1: {arm} {leg} receipt verdict {r.get('verdict')!r} != 'VALID'")
    if r.get("problems") != []:
        reasons.append(f"rule 1: {arm} {leg} receipt problems {r.get('problems')!r} != []")
    for field, want in (("name", leg), ("arm", arm), ("kind", "qualify" if kind == "m1" else kind)):
        if r.get(field) != want:
            reasons.append(f"rule 1: {arm} {leg} receipt {field} {r.get(field)!r} != {want!r}")
    if kind == "m1" and m["result"].get("status") != "ok":
        reasons.append(f"rule 1: {arm} {leg} m1 result.json status {m['result'].get('status')!r} != 'ok'")
    return reasons


def _kv_pins_reasons(frozen, frozen_sha, a, b, label):
    reasons = []
    pa, pb = a["receipt"].get("pins"), b["receipt"].get("pins")
    if _strip_frozen_sha(pa) != _strip_frozen_sha(pb):
        reasons.append(f"rule 2a: receipt pins (without frozen_sha) differ between {a['arm']} and {b['arm']}: "
                       f"{_diff_values(_strip_frozen_sha(pa), _strip_frozen_sha(pb), a['arm'], b['arm'])}")
    for m in (a, b):
        r, arm, leg = m["receipt"], m["arm"], m["leg"]
        pins = r.get("pins") if isinstance(r.get("pins"), dict) else {}
        state = r.get("state") if isinstance(r.get("state"), dict) else {}
        if _strip_frozen_sha(pins) != frozen:
            reasons.append(f"rule 2a: {arm} {leg} receipt pins (without frozen_sha) != run/{label}: "
                           f"{_diff_values(_strip_frozen_sha(pins), frozen, arm, 'frozen')}")
        for what, got in (("pins.frozen_sha", pins.get("frozen_sha")), ("state.frozen_sha", state.get("frozen_sha"))):
            if got != frozen_sha:
                reasons.append(f"rule 2a: {arm} {leg} {what} {got!r} != sha256 of {label} {frozen_sha}")
        if state.get("stack_head") != frozen.get(f"stack_head_{arm}"):
            reasons.append(f"rule 2a: {arm} {leg} state.stack_head {state.get('stack_head')!r} != frozen stack_head_{arm} "
                           f"{frozen.get(f'stack_head_{arm}')!r}")
    return reasons


def _kv_registry_reasons(kind, frozen, registry_git, texts, a, b):
    from bench.p426_plan import kv_registry_delta_problems

    reasons = []
    for m in (a, b):
        arm, leg = m["arm"], m["leg"]
        want = frozen.get(f"registry_{arm}_sha")
        if registry_git[arm] != want:
            reasons.append(f"rule 2b: {arm} sha256 of git show stack_head_{arm}:main_models.yaml {registry_git[arm]} != "
                           f"frozen registry_{arm}_sha {want!r}")
        if kind == "m1":
            got = m["report"].get("registry_sha256")
        elif kind == "longctx":
            got = sorted({(man.get("registry") or {}).get("sha256") for man in m["manifests"].values()}, key=str)
            got = got[0] if len(got) == 1 else got
        else:
            reg = m["manifest"].get("registry")
            got = reg.get("sha256") if isinstance(reg, dict) else None
        if got != want:
            reasons.append(f"rule 2b: {arm} {leg} recorded registry sha256 {got!r} != registry_{arm}_sha {want!r}")
    reasons += [f"rule 2b: {p}" for p in kv_registry_delta_problems(texts[a["arm"]], texts[b["arm"]], ENTRY, a["arm"], b["arm"])]
    return reasons


def _kv_tokens(m, kind):
    """The leg's worker argv tokens (receipt `worker.cmdline`, PID dropped; M1: job.json argv) with its own worktree component
    normalised; None when missing."""
    if kind == "m1":
        argv = m["job"].get("argv")
        toks = list(argv) if isinstance(argv, list) and all(isinstance(t, str) for t in argv) else None
    else:
        w = m["receipt"].get("worker")
        cmd = w.get("cmdline") if isinstance(w, dict) else None
        first, _, rest = (cmd or "").strip().partition(" ")
        toks = rest.split() if cmd and first.isdigit() else None
    if toks is None:
        return None
    own = _kv_path_re(m["arm"])
    return [own.sub("m76-ARM", t) for t in toks]


def _kv_argv_reasons(kind, a, b):
    from bench.p426_plan import kv_argv_problems

    what = "job.json argv" if kind == "m1" else "receipt worker.cmdline"
    ta, tb = _kv_tokens(a, kind), _kv_tokens(b, kind)
    if ta is None or tb is None:
        return [f"rule 2c: {what} missing or unparsable ({a['arm'] if ta is None else b['arm']})"]
    reasons = [f"rule 2c: {m['arm']} {m['leg']} {what} names another arm's worktree: {f}"
               for m, t in ((a, ta), (b, tb)) for f in [_kv_foreign(t, m["arm"])] if f]
    return reasons + [f"rule 2c: {what}: {p}" for p in kv_argv_problems(ta, tb, a["arm"], b["arm"], where="worker")]


# volatile per run (timestamp, the router's / its exit block's pids) / checked by rule 2b (registry sha) / the arm's own tune KEY
# (`gather(tune=)`: a key, never provenance) / M72's descriptive TQ4 route counts (present only under a TQ4 mode)
KV_PROVENANCE_EXCLUDED = ("timestamp", "router", "router_exit", "registry", "tune", "tq4_route_counts_at_creation",
                          "tq4_route_counts_at_exit")
KV_PROVENANCE_WHITELIST = frozenset({                            # the KV / mode keys (+ the arm commit) that may differ
    ("kv", "kv_bits"), ("kv", "tq4_attention"), ("kv", "kv_quant_scheme"),
    ("runtime", "tq4_attention"), ("runtime", "kv_bits"),
    ("fingerprint", "kv_bits"), ("fingerprint", "runtime", "tq4_attention"), ("fingerprint", "kv_extra", "kv_quant_scheme"),
    ("git", "stack_head"),
})


def kv_provenance(manifest):
    """The complete normalized provenance of a manifest (erratum v1.2): every recorded block (sampling profile and sampling,
    kv, quant, runtime controls, git incl. the serving-path hashes, box, model, fingerprint version) plus
    `bench.provenance.config_fingerprint` at the manifest's own version; only the volatile `timestamp` / `router` and the
    rule-2b `registry` block are left out."""
    from bench import provenance

    m = manifest if isinstance(manifest, dict) else {}
    out = {k: v for k, v in m.items() if k not in KV_PROVENANCE_EXCLUDED}
    out["fingerprint"] = provenance.config_fingerprint(m) if m else None
    out["fingerprint_version"] = m.get("fingerprint_version")
    return out


def _leaf_diffs(a, b, path=()):
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append((path + (k,), a.get(k, "<absent>"), b.get(k, "<absent>")))
            else:
                out += _leaf_diffs(a[k], b[k], path + (k,))
        return out
    return [] if a == b and type(a) is type(b) else [(path, a, b)]


def kv_provenance_problems(ma, mb, a, b):
    """Every difference between the two arms' normalized provenance outside the whitelist (the KV / mode keys, the arm commit)."""
    pa, pb = kv_provenance(ma), kv_provenance(mb)
    if pa.get("fingerprint_version") is None:
        return [f"{a}: manifest has no fingerprint_version"]
    return [f"{'.'.join(map(str, p))} differs ({a} {x!r}, {b} {y!r})" for p, x, y in _leaf_diffs(pa, pb)
            if tuple(p) not in KV_PROVENANCE_WHITELIST]


# erratum v1.3 (A7): per-invocation identity of a tg1 manifest (the probe run id, the worker process, the chain's binding nonce,
# the stamps written after the run) — never provenance; on top of KV_PROVENANCE_EXCLUDED
KV_A7_INVOCATION_KEYS = ("run_id", "worker", "cleanup_status", "continuation_history", "router_history")
KV_A7_INVOCATION_RUNTIME_KEYS = ("invocation_nonce",)
# the observed worker fingerprint (`bench.arm_identity`) carries the KV delta: compared with only these removed
KV_A7_ARM_IDENTITY_FLAGS = ("--kv-bits", "--tq4-attention", "--kv-quant-scheme")
KV_A7_ARM_IDENTITY_ENTRY = ("kv_bits", "tq4_attention")


def kv_a7_normalise(manifest):
    """A tg1 invocation manifest with its per-invocation identity removed and its arm fingerprint reduced to the non-KV part
    (`arm_identity_sha256` is that fingerprint's hash, so it is dropped and the reduced fingerprint compared instead)."""
    m = json.loads(json.dumps(manifest)) if isinstance(manifest, dict) else {}
    for k in KV_A7_INVOCATION_KEYS:
        m.pop(k, None)
    rt = m.get("runtime")
    if isinstance(rt, dict):
        for k in KV_A7_INVOCATION_RUNTIME_KEYS:
            rt.pop(k, None)
        rt.pop("arm_identity_sha256", None)
        ident = rt.get("arm_identity")
        if isinstance(ident, dict):
            if isinstance(ident.get("flags"), dict):
                ident["flags"] = {k: v for k, v in ident["flags"].items() if k not in KV_A7_ARM_IDENTITY_FLAGS}
            if isinstance(ident.get("entry"), dict):
                ident["entry"] = {k: v for k, v in ident["entry"].items() if k not in KV_A7_ARM_IDENTITY_ENTRY}
    return m


def _kv_a7_manifests(reader, att, session, where):
    """{rows file name: manifest} of one attempt's session directory (every non-DNF rows file needs its `.manifest.json`;
    None marks a missing / unreadable one)."""
    sdir = att["path"] / session
    out = {}
    for f in sorted(sdir.glob("*.jsonl")):
        if _is_dnf_file(f):
            continue
        mp = f.with_suffix(".manifest.json")
        data = reader.try_read_bytes(mp) if mp.is_file() else None
        try:
            doc = json.loads(data) if data is not None else None
        except ValueError:
            doc = None
        out[f.name] = doc if isinstance(doc, dict) else None
    return out


def kv_a7_provenance_reasons(reader, session, atts, ref, test):
    """Erratum v1.3: both arms' per-invocation provenance manifests, compared per language with `kv_provenance_problems` (the
    Wave 1 normalisation and whitelist, after `kv_a7_normalise`); any other difference rejects the session pair."""
    reasons, by_lang = [], {}
    for arm in (ref, test):
        mans = _kv_a7_manifests(reader, atts[arm], session, f"pair {session} {arm}")
        for name, man in mans.items():
            if man is None:
                reasons.append(f"rule 2d: {arm} {atts[arm]['name']} {session}/{name} has no readable provenance manifest")
                continue
            lang = (man.get("runtime") or {}).get("lang") if isinstance(man.get("runtime"), dict) else None
            by_lang.setdefault(lang, {}).setdefault(arm, []).append((name, man))
    seen = set()
    for lang in sorted(by_lang, key=str):
        cell = by_lang[lang]
        for arm in (ref, test):
            if arm not in cell:
                reasons.append(f"rule 2d: {arm} {session} has no provenance manifest for language {lang!r}")
        for na, ma in cell.get(ref, []):
            for nb, mb in cell.get(test, []):
                for p in kv_provenance_problems(kv_a7_normalise(ma), kv_a7_normalise(mb), ref, test):
                    if p not in seen:
                        seen.add(p)
                        reasons.append(f"rule 2d: {session} manifest provenance ({lang}: {na} / {nb}): {p}")
    return reasons


def _kv_manifest_reasons(ma, mb, a, b, where=""):
    reasons = [f"rule 2d: manifest{where} provenance: {p}" for p in kv_provenance_problems(ma, mb, a, b)]
    for m, arm in ((ma, a), (mb, b)):
        samp = m.get("sampling") if isinstance(m.get("sampling"), dict) else {}
        if samp.get("thinking_budget") != THINKING_BUDGET:
            reasons.append(f"rule 2d: {arm} manifest{where} sampling.thinking_budget {samp.get('thinking_budget')!r} != "
                           f"{THINKING_BUDGET}")
    return reasons


def _kv_equal_reasons(kind, a, b):
    """Rule 2d under kv: everything but the KV fields equal (the drafter included: both arms MTP ON), every row of both arms
    engaged."""
    reasons = []
    if kind == "m1":
        sa = {k: v for k, v in (a["result"].get("served") or {}).items() if k not in KV_M1_SERVED_FIELDS}
        sb = {k: v for k, v in (b["result"].get("served") or {}).items() if k not in KV_M1_SERVED_FIELDS}
        if sa != sb:
            reasons.append(f"rule 2d: m1 served (except {list(KV_M1_SERVED_FIELDS)}) differs: {_diff_values(sa, sb, a['arm'], b['arm'])}")
        if (a["result"].get("snapshots") or {}) != (b["result"].get("snapshots") or {}):
            reasons.append("rule 2d: m1 snapshots differ (target and drafter: both arms MTP ON)")
        for f in M1_REPORT_EQUAL:
            if a["report"].get(f) != b["report"].get(f):
                reasons.append(f"rule 2d: m1 report.{f} differs: {a['arm']} {a['report'].get(f)!r} {b['arm']} {b['report'].get(f)!r}")
        qa, qb = m1_qualify(a), m1_qualify(b)
        if qa.get("generate_seed") != qb.get("generate_seed"):
            reasons.append(f"rule 2d: m1 qualify.generate_seed differs: {qa.get('generate_seed')!r} {qb.get('generate_seed')!r}")
        za, zb = (qa.get("prompt") or {}).get("sized"), (qb.get("prompt") or {}).get("sized")
        if za != zb or za is None:
            reasons.append(f"rule 2d: m1 qualify.prompt.sized differs or is missing: {za!r} {zb!r}")
        return reasons
    if kind == "longctx":
        for iid in sorted(set(a["manifests"]) | set(b["manifests"])):
            reasons += _kv_manifest_reasons(a["manifests"].get(iid) or {}, b["manifests"].get(iid) or {}, a["arm"], b["arm"],
                                            where=f" {iid}")
    else:
        reasons += _kv_manifest_reasons(a["manifest"], b["manifest"], a["arm"], b["arm"])
        if kind == "reasoning":
            for m in (a, b):
                params = (m.get("doc") or {}).get("params")
                got = params.get("thinking_budget") if isinstance(params, dict) else None
                if got != THINKING_BUDGET:
                    reasons.append(f"rule 2d: {m['arm']} {m['leg']} reasoning params.thinking_budget {got!r} != {THINKING_BUDGET}")
        if kind in BUDGET_ROW_KINDS:
            ba = {json.dumps(r["id"]): r["row"].get("thinking_budget") for r in a["rows"]}
            bb = {json.dumps(r["id"]): r["row"].get("thinking_budget") for r in b["rows"]}
            bad = [f"{json.loads(k)}: {ba.get(k)!r} / {bb.get(k)!r}" for k in sorted(set(ba) | set(bb))
                   if ba.get(k) != bb.get(k) or ba.get(k) != THINKING_BUDGET]
            if bad:
                reasons.append(f"rule 2d: row thinking_budget differs across the pair or != {THINKING_BUDGET} ({len(bad)}): {bad[:5]}")
    for m in (a, b):
        bad = [f"{r['id']} {label}: {why}" for r in m["rows"] for label, d in _drafts(kind, r["row"])
               for why in [_draft_problem("on", d)] if why]
        if bad:
            reasons.append(f"rule 2d: {m['arm']} rows are not engaged (both KV arms are MTP ON) ({len(bad)}): {bad[:5]}")
    return reasons


def _kv_budget_mismatch(iid, frozen, arm_rows):
    """Erratum v1.2: each arm's A5 row carries the item's frozen prompt token count and its own resolved budget equals the frozen
    one (so both arms are equal); the differences, or [] when they hold."""
    if not isinstance(frozen, dict):
        return [f"{iid} has no frozen budget in m76/ids.json"]
    bad = []
    for arm, row in arm_rows:
        if row.get("prompt_tokens") != frozen.get("prompt_tokens"):
            bad.append(f"{arm} prompt_tokens {row.get('prompt_tokens')!r} != frozen {frozen.get('prompt_tokens')!r}")
        if row.get("resolved_max_tokens") != frozen.get("resolved_max_tokens"):
            bad.append(f"{arm} resolved max_tokens {row.get('resolved_max_tokens')!r} != frozen "
                       f"{frozen.get('resolved_max_tokens')!r}")
        if row.get("resolved_thinking_budget") != frozen.get("resolved_thinking_budget"):
            bad.append(f"{arm} resolved thinking budget {row.get('resolved_thinking_budget')!r} != frozen "
                       f"{frozen.get('resolved_thinking_budget')!r}")
    return bad


def _kv_keys(kind, label, ids, a, b):
    """Rule 3 + rule 7 under kv: the planned items in both arms, equal seeds (A4: the request seeds; A5: the planned per-row
    sampler seeds), the identity hash per arm."""
    planned = ids[kind][label]
    verified, by_arm = 0, {}
    for m in (a, b):
        where = f"pair {kind} {label} {m['arm']} {m['leg']}"
        seen = {}
        for r in m["rows"]:
            k = json.dumps(r["id"])
            if k in seen:
                raise RefusalError(f"{where}: duplicate row key ({label}, {r['id']})")
            seen[k] = r
        if set(seen) != {json.dumps(x) for x in planned} or len(m["rows"]) != len(planned):
            raise RefusalError(f"{where}: row ids != the ids.json {kind} {label} list")
        for r in m["rows"]:
            r["identity"] = _identity_sha(kind, r["row"])
            verified += kind in ("math500", "cjudge")
        by_arm[m["arm"]] = seen
    accepted, rejected = [], []
    for x in planned:
        k = json.dumps(x)
        ra, rb = by_arm[a["arm"]][k], by_arm[b["arm"]][k]
        key = [label, x, ra["seed"]]
        want = (ids["request_seeds"].get(str(x)) if kind == "reasoning" else
                ids["longctx_seeds"].get(x) if kind == "longctx" else None)
        if want is not None or kind in ("reasoning", "longctx"):
            bad = [f"{m['arm']} sampler_seed {r['seed']} != planned {want!r}" for m, r in ((a, ra), (b, rb)) if r["seed"] != want]
            if bad:
                rejected.append(dict(key=key, reason="seed mismatch: " + "; ".join(bad)))
                continue
        if ra["seed"] != rb["seed"]:
            rejected.append(dict(key=key, reason=f"seed mismatch: {a['arm']} {ra['seed']} {b['arm']} {rb['seed']}"))
            continue
        if kind == "longctx":
            bad = _kv_budget_mismatch(x, ids["longctx_budget"].get(x), ((a["arm"], ra["row"]), (b["arm"], rb["row"])))
            if bad:
                rejected.append(dict(key=key, reason="budget mismatch: " + "; ".join(bad)))
                continue
        accepted.append(dict(key=key, identical=ra["identity"] == rb["identity"],
                             sha256={a["arm"]: ra["identity"], b["arm"]: rb["identity"]}))
    return accepted, rejected, verified


def kv_check_roots(rows_root):
    from bench import generate

    try:
        if Path(rows_root).resolve() != Path(generate.results_root()).resolve():
            raise RefusalError("rows_root does not resolve to bench.generate.results_root() (A1 regrades through bench.grade)")
    except OSError:
        raise RefusalError("rows_root is unresolvable") from None


def _kv_frozen(reader, pair, build="s3"):
    from bench.p426_plan import kv_record_problems

    rel = f"{KV_W1}/run/frozen.{build}.json"
    data = reader.read_bytes(_kv_member(reader.root, reader.root / rel, rel), rel)
    frozen = _parse_json(data, rel)
    if not isinstance(frozen, dict):
        raise RefusalError(f"{rel} is not an object")
    problems = kv_record_problems(frozen, build, pair)
    if problems:
        raise RefusalError(f"{rel}: not the KV record of the pair {list(pair)}: " + "; ".join(problems)[:600])
    return frozen, hashlib.sha256(data).hexdigest(), rel


def verify_wave1_kv(rows_root, repo, pair, kinds=KV_W1_KINDS, build="s3"):
    """B8 Wave 1 under kv: one record per (kind, block label) of the pair; Math500's and A5's (v1.4) tier-2 blocks are
    `not_run` (not refused) when neither arm has the leg; an A5 tier-2 leg without a tier 2 in m76/ids.json refuses."""
    from bench.p426_plan import check_kv_pair, pair_label

    ref, test = check_kv_pair(*pair)
    kv_check_roots(rows_root)
    reader = Reader(rows_root, confine=True)
    frozen, frozen_sha, frozen_rel = _kv_frozen(reader, (ref, test), build)
    ids = load_kv_ids(reader)
    top = repo_top(repo)
    texts, registry_git = {}, {}
    for arm in (ref, test):
        commit = resolve_commit(top, frozen.get(f"stack_head_{arm}"), f"frozen stack_head_{arm}")
        data = git_bytes(top, ["show", f"{commit}:main_models.yaml"], f"git show stack_head_{arm}:main_models.yaml")
        texts[arm], registry_git[arm] = data.decode("utf-8", errors="replace"), hashlib.sha256(data).hexdigest()
    pairs, not_run = [], []
    for kind in kinds:
        if kind not in KV_W1_KINDS:
            raise RefusalError(f"unknown Wave 1 kind {kind!r}")
        for label in (list(KV_BLOCKS) if kind in KV_TIERED_KINDS else ["b1", "b2"]):
            if label in KV_TIER2 and not any((reader.root / KV_W1 / kv_leg_of(kind, arm, label)).exists() for arm in (ref, test)):
                not_run.append(f"{kind}/{label}")
                continue
            if label not in ids[kind]:
                raise RefusalError(f"{kind}/{label}: a tier-2 leg exists but m76/ids.json has no {kind} tier 2")
            a, b = (load_kv_leg(reader, kind, arm, label, ids) for arm in (ref, test))
            reasons, scrub_ok, scrub_n = [], 0, 0
            for m in (a, b):
                reasons += _kv_receipt_reasons(kind, m)
                r, ok, n = _w1_scrub_reasons(reader, m)
                reasons, scrub_ok, scrub_n = reasons + r, scrub_ok + ok, scrub_n + n
            reasons += _kv_pins_reasons(frozen, frozen_sha, a, b, Path(frozen_rel).name)
            reasons += _kv_registry_reasons(kind, frozen, registry_git, texts, a, b)
            reasons += _kv_argv_reasons(kind, a, b)
            reasons += _kv_equal_reasons(kind, a, b)
            reasons = [_pair_reason(kind, label, a, b, r) for r in reasons]
            if kind == "m1":
                keys, rejected, verified = [dict(key=[label], identical=False, identity="none (M1)")], [], 0
            else:
                keys, rejected, verified = _kv_keys(kind, label, ids, a, b)
                rejected = [dict(k, reason=mask_paths(k["reason"])) for k in rejected]
            if rejected:  # erratum v1.2: any rejected planned key rejects the pair (an incomplete pair is never verdicted)
                reasons = reasons + [f"rule 3: {len(rejected)} planned key(s) rejected — the pair is incomplete: "
                                     + "; ".join(f"{k['key'][1]}: {k['reason']}" for k in rejected[:5])]
            speed_valid = a["receipt"].get("speed_valid") is True and b["receipt"].get("speed_valid") is True
            pairs.append(dict(
                kind=kind, axis=KV_W1_AXIS[kind], block=label, tier=KV_BLOCKS[label][1], arms=[ref, test],
                legs={ref: a["leg"], test: b["leg"]}, tunes={ref: a["tune"], test: b["tune"]}, accepted=not reasons,
                reasons=reasons, speed_valid=speed_valid, labels=[] if speed_valid else ["power-invalid"],
                keys_accepted=len(keys), keys_rejected=rejected, keys=keys,
                identical=dict(n=sum(1 for k in keys if k["identical"]), of=0 if kind == "m1" else len(keys)),
                identity_basis={"math500": "content_sha256 (recomputed)", "cjudge": "content_sha256 (recomputed)",
                                "vision": "sha256(description)", "reasoning": "sha256(content)", "longctx": "sha256(content)",
                                "m1": "none"}[kind],
                scrub=dict(verified=scrub_ok, files=scrub_n), content_sha256_verified=verified,
                speed_problems={m["arm"]: m["receipt"].get("speed_problems") for m in (a, b)},
                log={m["arm"]: m["receipt"].get("log") for m in (a, b)}))
    return dict(axis="wave1", lever="kv", pair=[ref, test], label=pair_label(ref, test), generator="bench.p426_verify",
                inputs=dict(sorted(reader.inputs.items())), pairs=pairs, not_run=not_run,
                frozen=dict(sha256=frozen_sha, path=frozen_rel, **{f"stack_head_{a}": frozen.get(f"stack_head_{a}") for a in (ref, test)},
                            **{f"registry_{a}_sha": frozen.get(f"registry_{a}_sha") for a in (ref, test)}),
                registry_git_sha256=registry_git, allowed_delta=dict(registry=["kv_bits", "tq4_attention", "arm note"],
                                                                     argv=["--kv-bits", "--tq4-attention"]))


# ---------------------------------------------------------------------------------------------------------- A7 (kv)
def kv_sessions():
    """A7's paired sessions (`p426_plan.kv_a7_sessions`, B7's plan), or a refusal."""
    from bench.p426_plan import kv_a7_sessions

    try:
        return kv_a7_sessions()
    except ValueError as exc:
        raise RefusalError(f"A7 plan: {exc}") from None


def _kv_check_member(name, where, arms):
    if not isinstance(name, str) or "/" in name or name.startswith(".") or not KV_ATTEMPT_RE.match(name):
        raise RefusalError(f"{where}: {name!r} is not a tg1-m76-<arm>-<session>.a<k> attempt name")
    for pattern, what in KV_DENY_PATTERNS:
        if pattern.search(name):
            raise RefusalError(f"{where}: {name} is deny-listed ({what})")
    m = KV_ATTEMPT_RE.match(name)
    if m.group(1) not in arms:
        raise RefusalError(f"{where}: {name} is not an attempt of the pair's arms {list(arms)}")
    return m


def verify_a7_kv(results_root, pair):
    """B8 A7 under kv (`<results_root>` = `benchmark/results/m76`): one record per session of the pair (s1 / s2 paired; pilot /
    reload diagnostic); the attempt names, v8 commits, dossiers, schedules, keys and harvests as `verify_a7`, the arms named by
    their KV label; the dossier's differences only the worker argv (the KV flags) and closed-list volatile keys."""
    from bench.p426_plan import check_kv_pair, pair_label

    ref, test = check_kv_pair(*pair)
    reader = Reader(results_root)
    run = reader.root / WAVE / "run"
    v8 = reader.read_json(run / "v8_base.json", "wave2/run/v8_base.json")
    seq = reader.read_json(run / "sequence.json", "wave2/run/sequence.json")
    if not isinstance(v8, dict) or not isinstance(seq, dict):
        raise RefusalError("wave2/run/v8_base.json or sequence.json is not an object")
    v8_reasons = [] if self_hash_ok(v8) else [f"rule 2: v8_base.json self-hash {v8.get('sha256')!r} != {_canon_sha(v8)}"]
    if v8.get("lever") != "kv":
        v8_reasons.append(f"rule 2: v8_base.json lever {v8.get('lever')!r} != 'kv'")
    out_pairs = []
    paired = kv_sessions()           # erratum v1.2: the sessions of B7's A7 plan; a missing planned session refuses
    for session in paired + SESSIONS_DIAGNOSTIC:
        sp = _sequence_pair(seq, session)
        names, atts = {}, {}
        for arm in (ref, test):
            m = _kv_check_member(sp.get(arm), f"pair {session} {arm}", (ref, test))
            if m.group(1) != arm or m.group(2) != session:
                raise RefusalError(f"pair {session} {arm}: attempt {sp.get(arm)} is not a {arm}-{session} attempt")
            names[arm] = sp[arm]
            path = reader.root / WAVE / names[arm]
            if not path.is_dir() or path.resolve().parent != (reader.root / WAVE).resolve():
                raise RefusalError(f"pair {session} {arm}: attempt {WAVE}/{names[arm]} is missing or outside {WAVE}/")
            atts[arm] = _kv_load_attempt(reader, names[arm], session, f"pair {session} {arm} {names[arm]}")
        reasons = list(v8_reasons)
        for arm in (ref, test):
            reasons += _leg_reasons(arm, atts[arm]) + _sequence_leg_reasons(seq, arm, names[arm])
            reasons += _commit_reasons(v8, arm, atts[arm])
            reasons += _harvest_reasons_kv(reader, arm, atts[arm])
        dossier_rel = sp.get("dossier") or f"pairs/{session}__{ref}-a1__{test}-a1.json"
        if not isinstance(dossier_rel, str) or not dossier_rel.startswith("pairs/") or ".." in dossier_rel.split("/"):
            raise RefusalError(f"pair {session}: sequence dossier path {dossier_rel!r} is not under wave2/pairs/")
        reasons += _kv_dossier_reasons(reader, session, dossier_rel, ref, test, atts)
        reasons += kv_a7_provenance_reasons(reader, session, atts, ref, test)
        plans ={arm: schedule_plan_sha(atts[arm]["schedule"]) for arm in (ref, test)}
        if plans[ref] != plans[test]:
            reasons.append(f"rule 3: schedules differ ({ref} plan {plans[ref]}, {test} plan {plans[test]})")
        keys, keys_rejected = pair_keys(session, atts[ref], atts[test], prefix=KV_REPO_PREFIX)
        keys = [dict(key=k["key"], identical=k["identical"], manifest_sha256={ref: k["off_manifest_sha256"],
                                                                              test: k["on_manifest_sha256"]}) for k in keys]
        keys_rejected = [dict(k, reason=k["reason"].replace("absent in off", f"absent in {ref}")
                              .replace("absent in on", f"absent in {test}")) for k in keys_rejected]
        if keys_rejected:   # erratum v1.2: any rejected planned key rejects the session pair
            reasons.append(f"rule 3: {len(keys_rejected)} planned key(s) rejected — the session pair is incomplete: "
                           + "; ".join(f"{k['key'][1]}: {k['reason']}" for k in keys_rejected[:5]))
        speed_valid = all(atts[a]["leg"].get("speed_valid") is True for a in (ref, test))
        out_pairs.append(dict(pair=session, arms=[ref, test], attempts=names, accepted=not reasons, reasons=reasons,
                              keys_accepted=len(keys), keys_rejected=keys_rejected, keys=keys,
                              identical=sum(1 for k in keys if k["identical"]), speed_valid=speed_valid,
                              labels=[] if speed_valid else ["power-invalid"], dossier=f"{WAVE}/{dossier_rel}",
                              role="diagnostic" if session in SESSIONS_DIAGNOSTIC else "pair",
                              speed_reason={a: atts[a]["leg"].get("speed_reason") for a in (ref, test)}))
    return dict(axis=AXIS, lever="kv", pair=[ref, test], label=pair_label(ref, test), generator="bench.p426_verify",
                inputs=dict(sorted(reader.inputs.items())), pairs=out_pairs, sessions=list(paired),
                v8_base=dict(sha256=v8.get("sha256"), **{f"{a}_commit": v8.get(f"{a}_commit") for a in (ref, test)},
                             gitlinks=v8.get("gitlinks")), allowed_differences=list(KV_ALLOWED_DIFFERENCES))


def _kv_load_attempt(reader, name, session, where):
    path = reader.root / WAVE / name
    leg = reader.read_json(path / "leg.json", f"{where} leg.json")
    chain = reader.read_json(path / "chain.json", f"{where} chain.json")
    harvest = reader.read_json(path / "HARVEST.json", f"{where} HARVEST.json")
    schedule = reader.read_json(path / "schedule.json", f"{where} schedule.json")
    for doc, what in ((leg, "leg.json"), (chain, "chain.json"), (harvest, "HARVEST.json"), (schedule, "schedule.json")):
        if not isinstance(doc, dict):
            raise RefusalError(f"{where}: {what} is not an object")
    rows = session_rows(reader, path / session, session, where)
    dnf = load_dnf(chain, rows, session, where)
    count, ids = check_planned(rows, dnf, schedule, where)
    items = load_items(reader, path / "items", session, rows, dnf, where)
    return dict(name=name, path=path, leg=leg, chain=chain, harvest=harvest, schedule=schedule, rows=rows, dnf=dnf, items=items,
                planned=count, planned_ids=ids, schedule_sha256=reader.inputs[reader.rel(path / "schedule.json")])


def _harvest_reasons_kv(reader, arm, att):
    """Rule 5 under kv: as `_harvest_reasons`, the `main` files published under `benchmark/results/m76/`."""
    h, name = att["harvest"], att["name"]
    prefix = f"benchmark/results/{KV_ROOT}/"
    reasons = [] if self_hash_ok(h) else [f"rule 5: {arm} {name} HARVEST.json self-hash {h.get('sha256')!r} != {_canon_sha(h)}"]
    files = h.get("files")
    if not isinstance(files, list):
        return reasons + [f"rule 5: {arm} {name} HARVEST.json has no files list"]
    for f in files:
        if not isinstance(f, dict) or f.get("destination") != "main":
            continue
        pub = f.get("published")
        if not isinstance(pub, str) or not pub.startswith(prefix) or ".." in pub.split("/"):
            reasons.append(f"rule 5: {arm} {name} HARVEST main file {pub!r} is not under {prefix}")
            continue
        data = reader.try_read_bytes(reader.root / pub[len(prefix):])
        if data is None or hashlib.sha256(data).hexdigest() != f.get("published_sha256"):
            reasons.append(f"rule 5: {arm} {name} HARVEST main file {pub[len(prefix):]} is missing or does not verify")
    return reasons


def _kv_dossier_reasons(reader, session, dossier_rel, ref, test, atts):
    path = reader.root / WAVE / dossier_rel
    data = reader.try_read_bytes(path)
    if data is None:
        return [f"rule 5: dossier {WAVE}/{dossier_rel} is missing"]
    doc = _parse_json(data, f"dossier {WAVE}/{dossier_rel}")
    if not isinstance(doc, dict):
        return [f"rule 5: dossier {WAVE}/{dossier_rel} is not an object"]
    reasons = []
    if not self_hash_ok(doc):
        reasons.append(f"rule 5: dossier self-hash {doc.get('sha256')!r} != {_canon_sha(doc)}")
    for field, want in (("verdict", "PASS"), ("pair", session), ("lever", "kv"), ("ref", ref), ("test", test)):
        if doc.get(field) != want:
            reasons.append(f"rule 5: dossier {field} {doc.get(field)!r} != {want!r}")
    arms = doc.get("arms") if isinstance(doc.get("arms"), dict) else {}
    if sorted(arms) != sorted((ref, test)):
        reasons.append(f"rule 5: dossier arms {sorted(arms)} != {sorted((ref, test))}")
    for arm in (ref, test):
        rec = arms.get(arm) if isinstance(arms.get(arm), dict) else {}
        att = atts[arm]
        if rec.get("attempt") != att["name"]:
            reasons.append(f"rule 5: dossier arms.{arm}.attempt {rec.get('attempt')!r} != {att['name']!r}")
        if rec.get("harvest_sha256") != reader.inputs.get(reader.rel(att["path"] / "HARVEST.json")):
            reasons.append(f"rule 5: dossier arms.{arm}.harvest_sha256 is not {att['name']}/HARVEST.json's")
        r_data = reader.try_read_bytes(att["path"] / "receipt.json")
        if rec.get("receipt_sha256") != (hashlib.sha256(r_data).hexdigest() if r_data is not None else None):
            reasons.append(f"rule 5: dossier arms.{arm}.receipt_sha256 is not {att['name']}/receipt.json's")
    diffs = doc.get("differences")
    if not isinstance(diffs, list):
        reasons.append("rule 2: dossier differences is not a list")
    else:
        from bench import p426_receipt as pr

        reasons += [f"rule 2: {p}" for p in pr.kv_difference_problems([d for d in diffs if isinstance(d, dict)])]
    return reasons


def verify_all_kv(rows_root, repo, pair, kinds=KV_W1_KINDS):
    """One B8 record under kv: Wave 1 (+ A5) and, when `m76/wave2/run/` exists, A7."""
    w1 = verify_wave1_kv(rows_root, repo, pair, kinds=kinds)
    axes = dict(wave1=w1)
    union = dict(w1["inputs"])
    if (Path(rows_root) / KV_ROOT / WAVE / "run").is_dir():
        a7 = verify_a7_kv(Path(rows_root) / KV_ROOT, pair)
        axes["A7"] = a7
        for k, v in a7["inputs"].items():
            key = f"{KV_ROOT}/{k}"
            if union.get(key, v) != v:
                raise RefusalError(f"input {key} changed while B8 read it")
            union[key] = v
    return dict(generator="bench.p426_verify", version="m76-b3", lever="kv", pair=list(pair), label=w1["label"], axes=axes,
                inputs=dict(sorted(union.items())))


def dumps(doc):
    return json.dumps(doc, sort_keys=True, indent=1) + "\n"


def _one_line(text):
    return " ".join(str(text).split())


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m bench.p426_verify")
    ap.add_argument("--lever", default="mtp", choices=("mtp", "kv"),
                    help="M76 B3: mtp (default) = P426; kv = an M76 KV pair (`all --pair <ref>,<test>`; --results-root <rows>/m76)")
    sub = ap.add_subparsers(dest="axis", required=True)
    a7 = sub.add_parser("a7")
    a7.add_argument("--results-root", required=True, type=Path)
    a7.add_argument("--out", required=True, type=Path)
    al = sub.add_parser("all")
    al.add_argument("--results-root", required=True, type=Path)
    al.add_argument("--rows-root", required=True, type=Path)
    al.add_argument("--repo", required=True, type=Path)
    al.add_argument("--out", required=True, type=Path)
    al.add_argument("--lever", default=argparse.SUPPRESS, choices=("mtp", "kv"),
                    help="M76 B3: as the top-level --lever (either place)")
    al.add_argument("--pair", default=None, help="lever kv: <reference>,<treatment> (n16,x | x,v | n16,v)")
    args = ap.parse_args(argv)
    try:
        check_out_dirs([args.out])
        if args.axis == "a7" and args.lever == "kv":
            raise RefusalError("lever kv verifies A7 through `all --pair <ref>,<test>` (one record per KV pair)")
        if args.axis == "all" and args.lever == "kv":
            if not args.pair or "," not in args.pair:
                raise RefusalError("--lever kv needs --pair <reference>,<treatment>")
            if Path(args.results_root).resolve() != (Path(args.rows_root) / KV_ROOT).resolve():
                raise RefusalError("results_root does not resolve to rows_root/m76 (lever kv)")
            try:
                pair = tuple(args.pair.split(",", 1))
                from bench.p426_plan import check_kv_pair

                check_kv_pair(*pair)
            except ValueError as exc:
                raise RefusalError(str(exc)) from None
            doc = verify_all_kv(args.rows_root, args.repo, pair)
        elif args.axis == "all" and args.pair:
            raise RefusalError("--pair is a lever kv flag")
        elif args.axis == "all":
            doc = verify_all(args.results_root, args.rows_root, args.repo)
        else:
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
