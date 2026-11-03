"""Synthetic A7 (tg1 / Wave 2c) results tree for the P613 step-1 tests.

The layout, field names and hash relations copy the committed `benchmark/results/p426/wave2/` (the format reference):

    <repo>/benchmark/results/p426/                 <- `World.root` (the `results_root` handed to the code under test)
        wave2/run/{v8_base,sequence}.json          (v8_base is self-sealed with `bench.p426_harvest._canon_sha`)
        wave2/pairs/<session>__off-a1__on-a1.json  (dossier, self-sealed; arm hashes = sha256 of the file BYTES)
        wave2/tg1-p426-<arm>-<session>.a1/         leg.json chain.json receipt.json HARVEST.json schedule.json
            <session>/*.jsonl  items/*.json (+ decoy *.ready.json)  evidence/<run>/<lang>__<item>.final_tree/manifest.json
        wave2.v8-4104c7fc/                         (optional; the superseded namespace, noise floor only)

Nothing here reads the real data. `published` paths in HARVEST are repo-relative (`benchmark/results/p426/...`) exactly as in
the committed records.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
OFF_COMMIT = "a1" * 20
ON_COMMIT = "b2" * 20
GITLINKS = {"mlx_serve": "c3" * 20, "mlx_vlm": "d4" * 20}
SESSIONS = ("s1", "s2")
DIAG = ("pilot", "reload")
OLD_NS = "wave2.v8-4104c7fc"
REPO_PREFIX = "benchmark/results/p426"

DIFFS = [
    {"field": "snapshots.drafter", "off": None, "on": "0caad904fdd7706310f42f342226e7ae9b2d55dc", "process": "-"},
    {"field": "argv.worker", "off": None, "on": "--draft-kind mtp --draft-model caslca/x-mtp-drafter --mtp-verify-scan joint_v1",
     "process": "worker"},
]

DEFAULT_IDS = {
    "s1": ["python/a1", "python/a2", "python/a3", "python/a4", "python/a5", "go/g1", "go/g2", "go/g3"],
    "s2": ["python/b1", "python/b2", "python/b3", "python/b4", "python/b5", "go/h1", "go/h2", "go/h3"],
    "pilot": ["python/a1", "python/a2", "python/a3", "python/a4", "python/a5"],
    "reload": ["python/a1", "python/a2", "python/a3", "python/a4", "python/a5"],
}
SEED_BASE = {"s1": 1001, "s2": 2002, "pilot": 1001, "reload": 1001}
DEFAULT_RATE = {"off": 20.0, "on": 30.0}
DEFAULT_ACC = {"off": (0, 0), "on": (80, 100)}


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_text(s: str) -> str:
    return sha_bytes(s.encode("utf-8"))


def dumps(doc) -> str:
    return json.dumps(doc, sort_keys=True, indent=1) + "\n"


def canon_sha(doc) -> str:
    from bench.p426_harvest import _canon_sha         # the repository's own helper (never reimplemented)
    return _canon_sha(doc)


def sealed(doc: dict) -> dict:
    doc = dict(doc)
    doc.pop("sha256", None)
    doc["sha256"] = canon_sha(doc)
    return doc


def seed_of(session: str, idx: int) -> int:
    return SEED_BASE[session] * 1000 + idx * 7 + 3


def split_item(rid: str):
    lang, item = rid.split("/", 1)
    return lang, item


def attempt_name(arm: str, session: str, n: int = 1) -> str:
    return f"tg1-p426-{arm}-{session}.a{n}"


class World:
    """Build with `World(base, ...)`; mutate through `edit_*`; `refresh()` re-seals what a mutation must keep consistent."""

    def __init__(self, base: Path, *, ids=None, rows=None, speed=None, legs=None, dnf=None, identical=None,
                 old_namespace=None, sessions=SESSIONS + DIAG):
        self.base = Path(base)
        self.repo = self.base / "repo"
        self.root = self.repo / REPO_PREFIX
        self.ids = {k: list(v) for k, v in DEFAULT_IDS.items()}
        for k, v in (ids or {}).items():
            self.ids[k] = list(v)
        self.rows = rows or {}              # {(arm, session): {id: patch}}
        self.speed = speed or {}            # {(arm, session): {id: {rate, requests, decode_s, accepted, proposed}}}
        self.legs = legs or {}              # {(arm, session): {state, speed_valid, started, ended}}
        self.dnf = dnf or {}                # {(arm, session): [id, ...]}  (slot without a row; recorded in chain p426_dnf)
        self.identical = set(identical or ())   # {(session, id)}: ON final tree == OFF final tree
        self.sessions = tuple(sessions)
        self.root.mkdir(parents=True, exist_ok=True)
        self._build_namespace("wave2", self.sessions, attempt_no=1)
        if old_namespace is not None:
            self._build_old(old_namespace)

    # ------------------------------------------------------------------ paths
    def p(self, *rel) -> Path:
        return self.root.joinpath(*rel)

    def apath(self, arm, session, *rel, ns="wave2", n=1) -> Path:
        return self.p(ns, attempt_name(arm, session, n), *rel)

    def rel(self, path: Path) -> str:
        return str(Path(path).relative_to(self.root))

    # ------------------------------------------------------------------ build
    def _legs_of(self, ids):
        out = []
        for rid in ids:
            lang, _ = split_item(rid)
            if not out or out[-1][0] != lang:
                out.append((lang, []))
            out[-1][1].append(rid)
        return out

    def _invocations(self, session, ids):
        """[(lang, leg_index, phase, attempt_no, [ids])] — the first leg starts with a 3-slot `pilot` invocation (as the
        real files do), so rows of one session live in several files."""
        inv = []
        for k, (lang, members) in enumerate(self._legs_of(ids)):
            if k == 0 and len(members) > 3:
                inv.append((lang, k, "pilot", 1, members[:3]))
                inv.append((lang, k, "full", 2, members[3:]))
            elif k == 0:
                inv.append((lang, k, "pilot", 1, members))
            else:
                inv.append((lang, k, "full", 1, members))
        return inv

    def schedule(self, session, ids):
        legs = []
        for lang, k, phase, _, members in self._invocations(session, ids):
            if not legs or legs[-1]["lang"] != lang:
                legs.append({"session": session, "model": MODEL, "lang": lang, "seed_base": SEED_BASE[session],
                             "invocations": []})
            legs[-1]["invocations"].append(
                {"phase": phase, "names": [split_item(m)[1] for m in members], "limit": None,
                 "expect": list(members)})
        return {"schema": 1, "builder": "tg1", "mode": "chain", "smoke": False, "p426": True, "picks": [MODEL],
                "blocks": [{"session": session, "model": MODEL, "seed_base": SEED_BASE[session], "legs": legs,
                            "pilot_only": session in DIAG}]}

    def default_row(self, arm, session, rid, idx):
        lang, item = split_item(rid)
        manifest = self._manifest_doc(arm, session, rid)
        return {
            "bench": "opencode", "schema_version": 3, "scaffold": "opencode-v2-web-tg1", "id": rid, "model": MODEL,
            "sample": 0, "passed": True, "acc": 1, "converged": True, "nonconv_kind": None, "nonconv_flags": [],
            "file_changed": True, "test_modified": False, "tool_bounds_rejections": 0, "wall_s": 60.0 + idx,
            "sampler_seed": seed_of(session, idx), "seed_base": SEED_BASE[session],
            "final_tree": {"manifest_sha256": sha_text(dumps(manifest)), "files": {f"{item}.x": "0" * 64}, "missing": []},
        }

    def _manifest_doc(self, arm, session, rid):
        owner = "same" if (session, rid) in self.identical else arm
        return {"files": {"sol.txt": sha_text(f"{owner}|{session}|{rid}")}, "item": rid}

    def _row(self, arm, session, rid, idx, ns_rows):
        row = self.default_row(arm, session, rid, idx)
        row.update(copy.deepcopy((ns_rows.get((arm, session)) or {}).get(rid, {})))
        if "passed" in (ns_rows.get((arm, session)) or {}).get(rid, {}) and "acc" not in ns_rows[(arm, session)][rid]:
            row["acc"] = 1 if row["passed"] else 0
        return row

    def _item_record(self, arm, session, rid, ns_speed):
        spec = (ns_speed.get((arm, session)) or {}).get(rid, {})
        rate = spec.get("rate", DEFAULT_RATE[arm])
        decode_s = spec.get("decode_s", 10.0)
        acc, prop = spec.get("accepted", DEFAULT_ACC[arm][0]), spec.get("proposed", DEFAULT_ACC[arm][1])
        if "requests" in spec:
            reqs = copy.deepcopy(spec["requests"])
            gen = spec.get("generated_tokens", sum(r["generated_tokens"] for r in reqs))
            nreq = len(reqs)
        else:
            gen = int(round(2 + rate * decode_s))
            half = (gen - 0) // 2
            reqs = [{"generated_tokens": half, "decode_tok_s": rate, "draft_n": None, "draft_n_accepted": None,
                     "error": None},
                    {"generated_tokens": gen - half, "decode_tok_s": rate, "draft_n": None, "draft_n_accepted": None,
                     "error": None}]
            nreq = 2
            # make the sensitivity (sum(g-1) / sum((g-1)/tps)) equal `rate` too: every tps is `rate`
        lang, item = split_item(rid)
        return {
            "case": "completed", "verdict": "reconciled", "slot": f"tg1-p426|oc|{MODEL}|{session}|{lang}|{item}",
            "totals": {"requests": spec.get("n_requests", nreq), "generated_tokens": gen, "decode_s": decode_s,
                       "accepted": acc, "proposed": prop, "prompt_tokens": 1000,
                       "decode_rate_source": "completed requests (spec 8)"},
            "requests": reqs,
        }

    def _build_namespace(self, ns, sessions, attempt_no, only=None):
        ns_dir = self.p(ns)
        (ns_dir / "run").mkdir(parents=True, exist_ok=True)
        (ns_dir / "pairs").mkdir(parents=True, exist_ok=True)
        v8 = sealed({"kind": "p426_v8_base", "build": "s2", "off_commit": OFF_COMMIT, "on_commit": ON_COMMIT,
                     "gitlinks": GITLINKS, "r1_env_difference": DIFFS, "created": "2026-11-03T01:58:24Z"})
        (ns_dir / "run" / "v8_base.json").write_text(dumps(v8))
        for session in sessions:
            for arm in ("off", "on"):
                if only is None or (arm, session) in only:
                    self._build_attempt(ns, arm, session, attempt_no)
            if only is None:
                self._write_dossier(ns, session, attempt_no)
        self._write_sequence(ns, sessions)

    def _write_sequence(self, ns, sessions):
        legs = [{"leg": attempt_name(a, s)[:-3], "attempt": 1, "state": "VALID"} for s in sessions for a in ("off", "on")]
        pairs = [{"pair": s, "off": attempt_name("off", s), "on": attempt_name("on", s),
                  "dossier": f"pairs/{s}__off-a1__on-a1.json", "verdict": "PASS", "published": True} for s in sessions]
        self.p(ns, "run", "sequence.json").write_text(dumps({"legs": legs, "pairs": pairs}))

    def _build_attempt(self, ns, arm, session, n, ids=None, rows=None, speed=None, legs=None, dnf=None, schedule_note=None):
        ids = list(ids if ids is not None else self.ids[session])
        rows = self.rows if rows is None else rows
        speed = self.speed if speed is None else speed
        legs = self.legs if legs is None else legs
        dnf_ids = list((dnf if dnf is not None else self.dnf).get((arm, session), []))
        att = self.p(ns, attempt_name(arm, session, n))
        (att / session).mkdir(parents=True, exist_ok=True)
        (att / "items").mkdir(exist_ok=True)
        sched = self.schedule(session, ids)
        if schedule_note:
            sched["note"] = schedule_note
        (att / "schedule.json").write_text(dumps(sched))
        row_idx = {rid: i for i, rid in enumerate(ids)}
        harvest_files = []
        run_id = "20261102T190300-45a138b82165"
        for lang, k, phase, an, members in self._invocations(session, ids):
            lines = []
            for rid in members:
                if rid in dnf_ids:
                    continue
                row = self._row(arm, session, rid, row_idx[rid], rows)
                lines.append(json.dumps(row, sort_keys=True))
                _, item = split_item(rid)
                mdoc = self._manifest_doc(arm, session, rid)
                mrel = f"{ns}/{attempt_name(arm, session, n)}/evidence/{run_id}/{lang}__{item}.final_tree/manifest.json"
                mpath = self.p(*mrel.split("/"))
                mpath.parent.mkdir(parents=True, exist_ok=True)
                mpath.write_text(dumps(mdoc))
                row["final_tree"]["manifest_sha256"] = sha_bytes(mpath.read_bytes()) \
                    if "final_tree" not in (rows.get((arm, session)) or {}).get(rid, {}) else row["final_tree"].get(
                        "manifest_sha256")
                lines[-1] = json.dumps(row, sort_keys=True)
                harvest_files.append({"destination": "main", "published": f"{REPO_PREFIX}/{mrel}",
                                      "published_sha256": sha_bytes(mpath.read_bytes()),
                                      "sha256": sha_bytes(mpath.read_bytes()), "source": f"evidence:{run_id}/x",
                                      "compression": None, "exclusion_reason": None})
                rec = self._item_record(arm, session, rid, speed)
                stem = f"tg1-p426__oc__{MODEL}__{session}__{lang}__{item}"
                (att / "items" / f"{stem}.json").write_text(dumps(rec))
                decoy = copy.deepcopy(rec)
                decoy["totals"].update(generated_tokens=9_999_999, decode_s=0.001, accepted=1, proposed=1)
                (att / "items" / f"{stem}.ready.json").write_text(dumps(decoy))
            fname = f"{MODEL}.{session}.opencode_{lang}.L{k}.{phase}.a{an}.jsonl"
            (att / session / fname).write_text("".join(line + "\n" for line in lines))
        harvest_files.append({"destination": "evidence", "published": f"{REPO_PREFIX}/{ns}/{attempt_name(arm, session, n)}"
                              f"/evidence/{run_id}/x.events.jsonl", "published_sha256": "e" * 64, "sha256": "f" * 64,
                              "source": "evidence:x", "compression": None, "exclusion_reason": None})
        harvest = sealed({"attempt": n, "leg": attempt_name(arm, session, n)[:-3], "state": "VALID",
                          "files": harvest_files, "created": "2026-11-03T06:52:45Z"})
        (att / "HARVEST.json").write_text(dumps(harvest))
        (att / "receipt.json").write_text(dumps(sealed({"argv": [], "env": {}, "probe_entry": "x"})))
        leg = {"attempt": n, "leg": attempt_name(arm, session, n)[:-3], "state": "VALID", "speed_valid": True,
               "started": "2026-11-03T03:00:00Z", "ended": "2026-11-03T04:30:15Z", "class": "valid", "reason": "",
               "speed_reason": "ok", "chain_rc": 0, "overrun": False}
        leg.update((legs.get((arm, session)) or {}))
        (att / "leg.json").write_text(dumps(sealed(leg)))
        dnf_records = [{"slot": f"tg1-p426|oc|{MODEL}|{session}|{split_item(rid)[0]}|{split_item(rid)[1]}",
                        "item": split_item(rid)[1], "session": session, "language": split_item(rid)[0],
                        "seed": SEED_BASE[session], "arm": arm, "pick": MODEL, "attempt": n,
                        "abort": {"cause": "transport", "error": "x", "evidence": None}} for rid in dnf_ids]
        chain = {"status": "finished", "mode": "chain", "rc": 0, "predictor": arm,
                 "artifacts": {"campaign_core": {"commit": OFF_COMMIT if arm == "off" else ON_COMMIT}},
                 "p426_dnf": dnf_records, "p426_ledger": []}
        (att / "chain.json").write_text(dumps(chain))

    def _write_dossier(self, ns, session, n):
        arms = {}
        for arm in ("off", "on"):
            att = self.p(ns, attempt_name(arm, session, n))
            arms[arm] = {"attempt": attempt_name(arm, session, n),
                         "harvest_sha256": sha_bytes((att / "HARVEST.json").read_bytes()),
                         "receipt_sha256": sha_bytes((att / "receipt.json").read_bytes())}
        doc = sealed({"pair": session, "verdict": "PASS", "arms": arms, "differences": copy.deepcopy(DIFFS),
                      "at": "2026-11-03T09:30:20Z"})
        (self.p(ns, "pairs") / f"{session}__off-a1__on-a1.json").write_text(dumps(doc))

    def _build_old(self, old):
        """`old` = {"v8_sha_note": str, "attempts": [dict(arm, session, n=1, state="VALID", rows={id: patch}, note=None)]}.
        Written as `wave2.v8-4104c7fc/` with its own `run/v8_base.json` (different commits => a different self-hash)."""
        ns = OLD_NS
        (self.p(ns) / "run").mkdir(parents=True, exist_ok=True)
        v8 = sealed({"kind": "p426_v8_base", "build": "s2", "off_commit": "9f" * 20, "on_commit": "8e" * 20,
                     "gitlinks": GITLINKS, "created": "2026-11-02T01:00:00Z", "note": old.get("v8_sha_note", "old")})
        (self.p(ns, "run") / "v8_base.json").write_text(dumps(v8))
        for spec in old["attempts"]:
            arm, session, n = spec["arm"], spec["session"], spec.get("n", 1)
            self._build_attempt(ns, arm, session, n, rows={(arm, session): spec.get("rows", {})},
                                legs={(arm, session): {"state": spec.get("state", "VALID")}}, speed={}, dnf={},
                                schedule_note=spec.get("note"))

    # ------------------------------------------------------------------ views
    def load(self, *rel):
        return json.loads(self.p(*rel).read_text())

    def save(self, doc, *rel, seal=True):
        self.p(*rel).write_text(dumps(sealed(doc) if seal else doc))

    def rows_of(self, arm, session):
        out = []
        for f in sorted((self.apath(arm, session, session)).glob("*.jsonl")):
            out += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        return out

    def edit_rows(self, arm, session, fn):
        """fn(list_of_row_dicts) -> list; rewritten across the same files (new rows go to the LAST file)."""
        files = sorted(self.apath(arm, session, session).glob("*.jsonl"))
        per = [[json.loads(l) for l in f.read_text().splitlines() if l.strip()] for f in files]
        flat = [r for rows in per for r in rows]
        new = fn(copy.deepcopy(flat))
        cursor = 0
        for i, f in enumerate(files):
            take = len(per[i]) if i < len(files) - 1 else len(new) - cursor
            chunk = new[cursor:cursor + take]
            cursor += take
            f.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in chunk))

    def edit_json(self, rel_parts, fn, seal=True):
        doc = self.load(*rel_parts)
        out = fn(doc)
        doc = doc if out is None else out
        self.save(doc, *rel_parts, seal=seal)

    def edit_leg(self, arm, session, **kw):
        rel = (("wave2", attempt_name(arm, session), "leg.json"))
        self.edit_json(rel, lambda d: d.update(kw))
        self.refresh(session)

    def edit_chain(self, arm, session, fn):
        self.edit_json(("wave2", attempt_name(arm, session), "chain.json"), fn, seal=False)

    def edit_dossier(self, session, fn, seal=True):
        self.edit_json(("wave2", "pairs", f"{session}__off-a1__on-a1.json"), fn, seal=seal)

    def refresh(self, session):
        """Recompute the dossier's arm hashes (and seal) after a mutation of HARVEST / receipt."""
        for arm in ("off", "on"):
            att = self.p("wave2", attempt_name(arm, session))
            d = self.load("wave2", "pairs", f"{session}__off-a1__on-a1.json")
            d["arms"][arm]["harvest_sha256"] = sha_bytes((att / "HARVEST.json").read_bytes())
            d["arms"][arm]["receipt_sha256"] = sha_bytes((att / "receipt.json").read_bytes())
            self.save(d, "wave2", "pairs", f"{session}__off-a1__on-a1.json")


def outcomes(pass_ids=(), *, converged_false=(), all_ids=None):
    """Row patches: ids in `pass_ids` pass, every other id of `all_ids` fails (converged unless listed)."""
    patch = {}
    for rid in all_ids or []:
        patch[rid] = {"passed": rid in pass_ids, "converged": rid not in converged_false}
    return patch
