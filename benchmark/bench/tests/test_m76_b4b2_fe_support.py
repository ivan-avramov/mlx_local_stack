"""M76 B4b-2 (test-writer, delivery 1): the shared synthetic world of the A8 (tg2) / A7 (tg1) consumers, and its own checks.

Nothing here reads the committed records except `PINS.json`-pinned manifest copies (fixtures/m76_b4b2_fe/pilot_manifests/, copied
byte for byte from the harvested tg2 pilot pair) and the pinned tg2 draw (`benchmark/m65/tg2_draw.json`, sha = `schedules.TG2_DRAW_SHA256`).

`World` writes `<repo>/benchmark/results/m76/<namespace>/` in the committed layout: `run/{v8_base,sequence}.json`, `pairs/*.json`,
`<corpus>-m76-<arm>-<session>.a1/` (leg.json, chain.json with a `progress` inventory valid for `bench.chain_rows.load_slots`, HARVEST.json,
receipt.json, schedule.json, `<session>/*.jsonl` + `.manifest.json`, `items/*`), final-tree manifests published on `main` under
`evidence/<run>/<lang>__<item>.final_tree/manifest.json`. The tg2 schedules are the pinned draw's (`schedules.tg2_p426`), so
`schedules.check_tg2_p426` holds on every session.

Interface assumptions of the A8 entry points (each stated again in the report):
  * `p426_verify.verify_a8_kv(results_root)` -> B8-A8 document; `results_root` = `<rows>/m76`; it finds `B8.json` in `results_root`
    (the world writes a stand-in) and records its sha as `base_b8_sha256`;
  * the document's `pairs` is a list of per-session records (`pair`, `accepted`, `status`, `reasons`, `role`, `keys`, ...) as A7's;
    the document's own `status` is `"complete"` iff every confirmatory session is accepted, else `"incomplete"`.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from bench import chain_rows as cr
from bench import p426_hooks as ph
from bench import schedules
from bench.tests.p613.a7world import dumps, sealed, sha_bytes

BENCH = Path(__file__).resolve().parents[2]
REPO = BENCH.parent
FIX = Path(__file__).resolve().parent / "fixtures" / "m76_b4b2_fe"
MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
COMMIT = {"n16": "a1" * 20, "x": "b2" * 20}
GRADER_IMAGE = "sha256:" + "5" * 64
LANGS = ("rust", "javascript", "java", "cpp")
SEED = {"pilot": 1001, "s1": 1001, "s2": 2002, "reload": 1001, "s3": 3003}
TG1_ITEMS = [f"python/a{i}" for i in range(5)] + [f"go/g{i}" for i in range(3)]
DIFFS = [dict(process="worker", field="argv.worker", ref=None, test="--kv-bits 4 --tq4-attention m72_exact")]


def draw_doc():
    return json.loads((REPO / "benchmark" / "m65" / "tg2_draw.json").read_text())


def tg2_schedule(session):
    return schedules.tg2_p426(draw_doc(), session, MODEL, "mtp")


def schedule_ids(schedule):
    return [i for b in schedule["blocks"] for leg in b["legs"] for inv in leg["invocations"] for i in inv["expect"]]


def lang_of(rid):
    return rid.split("/", 1)[0]


def without_keys(rec):
    """A session record without its `keys` list (which names every item): what remains is the record's own findings."""
    return {k: v for k, v in rec.items() if k != "keys"}


def mentions(obj, text):
    return text in json.dumps(obj, sort_keys=True, default=str)


def pinned_manifest(arm, lang):
    """The real pilot invocation manifest (byte copy, sha256-pinned by PINS.json) of `arm` for `lang`."""
    d = FIX / "pilot_manifests" / arm
    (path,) = [p for p in d.iterdir() if f".opencode_{lang}." in p.name]
    return json.loads(path.read_text())


AMENDMENT_PATH = "$STACK_WORKDIR/run/amendment.json"
TG2_DECIDERS = ("s1", "s2", "reload")


def recorded_pilot_legs():
    """The sequencer's tg2 pilot leg records (`sequence.json` `legs`) of a decider-only world."""
    return [dict(leg=f"tg2-m76-{arm}-pilot", attempt=1, state="VALID") for arm in ("n16", "x")]


def recorded_pilot_pair():
    """The sequencer's tg2 pilot pair record (`sequence.json` `pairs`) of a decider-only world."""
    return dict(pair="pilot", n16="tg2-m76-n16-pilot.a1", x="tg2-m76-x-pilot.a1", dossier="pairs/pilot__n16-a1__x-a1.json",
                verdict="PASS", published=True)


def recorded_pilot_dossier():
    """The sealed PASS pilot dossier of a decider-only world (its attempts are not in the tree; only its bytes are bound)."""
    arms = {arm: dict(attempt=f"tg2-m76-{arm}-pilot.a1", harvest_sha256="7" * 64, receipt_sha256="8" * 64) for arm in ("n16", "x")}
    return sealed(dict(pair="pilot", lever="kv", ref="n16", test="x", verdict="PASS", arms=arms, differences=copy.deepcopy(DIFFS),
                       at="2026-11-19T21:30:00Z"))


def publish_tg2_amendment(ns_dir, v8, pilot_dossier, previous=None):
    """Write `<ns_dir>/run/amendment.json`: a sealed `p426_timeout_amendment` (the fields `p426_freeze.write_amendment_tg2` writes;
    synthetic walls at the 382 s floor) naming `v8` and the sha256 of `pilot_dossier`'s bytes. Every decider chain under `ns_dir`
    whose `frozen_record.sha256` is the v8 base's or `previous`'s is re-pointed at the new amendment. Returns the amendment."""
    from bench import p426_freeze as fz

    walls = {lang: fz.TG2_WALL_FLOOR_S for lang in fz.TG2_LANGS}
    doc = sealed(dict(kind=fz.KIND_AMENDMENT, v8_base_sha256=v8["sha256"], corpus="tg2",
                      **{f"w_{lang}_s": w for lang, w in walls.items()},
                      leg_deadline_s={leg: fz.tg2_deadline_s(leg, walls) for leg in fz.TG2_ITEM_COUNT},
                      settle_bound_s=float(v8.get("settle_bound_s", 600.0)),
                      pilot_dossier_sha256=sha_bytes(Path(pilot_dossier).read_bytes()), created="2026-11-20T00:30:00Z"))
    ns_dir = Path(ns_dir)
    (ns_dir / "run" / "amendment.json").write_text(dumps(doc))
    old = {v8["sha256"]} | ({previous["sha256"]} if isinstance(previous, dict) else set())
    for path in sorted(ns_dir.glob("tg2-m76-*-*.a*/chain.json")):
        if path.parent.name.split("-")[3].split(".")[0] not in TG2_DECIDERS:
            continue
        chain = json.loads(path.read_text())
        fr = chain.get("frozen_record")
        if isinstance(fr, dict) and fr.get("sha256") in old:
            chain["frozen_record"] = dict(fr, path=AMENDMENT_PATH, sha256=doc["sha256"])
            path.write_text(dumps(chain))
    return doc


class World:
    """A synthetic M76 tree for one corpus. `corpus="tg2"` -> `wave2.tg2` (sessions pilot / s1 / s2 / reload, the pinned draw's items);
    `corpus="tg1"` -> `wave2` (sessions s1 / s2 / s3 / pilot / reload, 8 python+go items).

    Per-slot controls (all keyed `(arm, session)` -> ...):
      outcomes   {rid: bool | dict(passed=, converged=)}  (default: every slot passes, converged)
      dnf        [rid]  transport DNF (`chain.p426_dnf`, no row)
      hdnf       {rid: "harness_fault_dnf" | "grade_fault"}  S27 harness DNF (`chain.p426_harness_dnf` + sealed sidecar, no row)
      reruns     [rid]  a harness-fault rerun: attempt 0 `harness_fault` (reason recorded), attempt 1 accepted (the row)
      accounting [rid]  accounting fault: the row keeps its outcome, `accounting_fault: true`, sealed sidecar
      identical  {(session, rid)}  the X final tree equals N16's
    """

    def __init__(self, base, corpus="tg2", sessions=None, outcomes=None, dnf=None, hdnf=None, reruns=None, accounting=None,
                 identical=None, legs=None, root=None, tokens=None, manifest_hook=None):
        self.corpus = corpus
        self.manifest_hook = manifest_hook                  # (arm, session, lang, manifest) -> manifest

        self.ns = "wave2.tg2" if corpus == "tg2" else "wave2"
        self.sessions = tuple(sessions or (("pilot", "s1", "s2", "reload") if corpus == "tg2" else ("s1", "s2", "s3", "pilot", "reload")))
        self.base = Path(base)
        self.root = Path(root) if root is not None else self.base / "repo" / "benchmark" / "results" / "m76"
        self.outcomes, self.dnf, self.hdnf = outcomes or {}, dnf or {}, hdnf or {}
        self.reruns, self.accounting, self.identical = reruns or {}, accounting or {}, set(identical or ())
        self.legs, self.tokens = legs or {}, tokens or {}
        self.ids = {}
        self.runs = {}
        (self.root / self.ns / "run").mkdir(parents=True, exist_ok=True)
        (self.root / self.ns / "pairs").mkdir(parents=True, exist_ok=True)
        self.write_base_b8()
        self.v8 = self._v8()
        self.p(self.ns, "run", "v8_base.json").write_text(dumps(self.v8))
        self.amendment = None
        for s in self.sessions:
            for arm in ("n16", "x"):
                self.build_attempt(arm, s)
            self.write_dossier(s)
        # tg2 decider-only world: the campaign's pilot still ran — its pair record + dossier stand in the sequencer's records (the
        # amendment binds that dossier); its attempts are outside the tree (B8-A8: pilot incomplete, never accepted)
        self.recorded_pilot = (corpus == "tg2" and "pilot" not in self.sessions
                               and bool(set(self.sessions) & set(TG2_DECIDERS)))
        if self.recorded_pilot:
            self._write_json(self.p(self.ns, "pairs", "pilot__n16-a1__x-a1.json"), recorded_pilot_dossier())
        self.write_sequence()
        self.publish_amendment()

    # ------------------------------------------------------------------------------------------------------------- paths
    def p(self, *rel):
        return self.root.joinpath(*rel)

    def att(self, arm, session, n=1):
        return f"{self.corpus}-m76-{arm}-{session}.a{n}"

    def adir(self, arm, session, *rel, n=1):
        return self.p(self.ns, self.att(arm, session, n), *rel)

    def slot(self, session, rid):
        lang, item = rid.split("/", 1)
        return f"{self.corpus}-p426|oc|{MODEL}|{session}|{lang}|{item}"

    def prefix(self):
        return "benchmark/results/m76"

    def write_base_b8(self):
        """The `B8.json` the A8 record accompanies (a stand-in: only its bytes / sha matter to B8-A8)."""
        (self.root / "B8.json").write_text('{"generator": "bench.p426_verify", "stand_in": true}\n')

    def base_b8_sha(self):
        return sha_bytes((self.root / "B8.json").read_bytes())

    # ------------------------------------------------------------------------------------------------------------- records
    def _v8(self):
        doc = dict(kind="p426_v8_base", lever="kv", arms=["n16", "x"], build="s3", n16_commit=COMMIT["n16"], x_commit=COMMIT["x"],
                   gitlinks={}, created="2026-11-20T00:00:00Z")
        if self.corpus == "tg2":
            rt = pinned_manifest("n16", "rust")["runtime"]       # B4: the v8 carries the identity the invocation manifests carry
            doc.update(corpus="tg2", tg2_draw_sha256=schedules.TG2_DRAW_SHA256, tg2_universe_sha256=schedules.TG2_UNIVERSE_SHA256,
                       probe_code_sha256=rt["probe_code_sha256"], scaffold_policy_sha256=rt["scaffold_policy_sha256"],
                       generation_identity_sha256=rt["generation_identity_sha256"],
                       tg2_image_id=rt["policy"]["corpus_identity"]["image"],
                       grader_image_id=rt["policy"]["toolchain"]["grader_image_id"])
        return sealed(doc)

    def schedule(self, session):
        if self.corpus == "tg2":
            return tg2_schedule(session)
        ids = TG1_ITEMS if session not in ("pilot", "reload") else TG1_ITEMS[:5]
        legs = []
        for lang in ("python", "go"):
            members = [i for i in ids if i.startswith(lang + "/")]
            if members:
                legs.append(dict(session=session, model=MODEL, lang=lang, seed_base=SEED[session],
                                 invocations=[dict(phase="full", names=[m.split("/")[1] for m in members], limit=None, expect=members)]))
        return dict(schema=1, builder="tg1", mode="chain", smoke=False, p426=True, picks=[MODEL],
                    blocks=[dict(session=session, model=MODEL, seed_base=SEED[session], legs=legs, pilot_only=session in ("pilot", "reload"))])

    def seed(self, session, rid):
        """B10: `rowschema.sample_seed(id, 0, <the session's plan seed>)`, as the runner writes it (a reload shares s1's seeds)."""
        from bench import rowschema
        return rowschema.sample_seed(rid, 0, SEED[session])

    def _outcome(self, arm, session, rid):
        o = (self.outcomes.get((arm, session)) or {}).get(rid, True)
        o = dict(passed=o) if isinstance(o, bool) else dict(o)
        o.setdefault("passed", True)
        o.setdefault("converged", True)
        return o

    def _manifest_doc(self, arm, session, rid, **kw):
        owner = "same" if (session, rid) in self.identical else arm
        return dict(files={"sol.txt": sha_bytes(f"{owner}|{session}|{rid}".encode())}, item=rid, missing=[], **kw)

    def _run_id(self, arm, session, lang, rerun=False):
        return f"20261120T{SEED[session] % 100:02d}{len(lang):02d}{'99' if rerun else '00'}-{arm}{session}{lang[:3]}{'r' if rerun else 'a'}".replace("_", "")

    def _item_record(self, arm, session, rid, rindex):
        tok = (self.tokens.get((arm, session)) or {}).get(rid, 300)
        slot = self.slot(session, rid)
        rec = ph.seal(dict(case="completed", verdict="reconciled", slot=slot, ready_sha256="0" * 64,
                           totals=dict(requests=2, generated_tokens=tok, decode_s=10.0, accepted=80, proposed=100, prompt_tokens=1000,
                                       decode_rate_source="completed requests (spec 8)"),
                           requests=[dict(generated_tokens=tok // 2, decode_tok_s=30.0, error=None),
                                     dict(generated_tokens=tok - tok // 2, decode_tok_s=30.0, error=None)]))
        return rec

    def _write_json(self, path, doc):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(dumps(doc))

    def build_attempt(self, arm, session):
        n = 1
        att = self.adir(arm, session)
        (att / session).mkdir(parents=True, exist_ok=True)
        (att / "items").mkdir(exist_ok=True)
        sched = self.schedule(session)
        self._write_json(att / "schedule.json", sched)
        ids = schedule_ids(sched)
        self.ids[session] = ids
        dnf = set(self.dnf.get((arm, session), ()))
        hdnf = dict(self.hdnf.get((arm, session), {}))
        reruns = set(self.reruns.get((arm, session), ()))
        acct = set(self.accounting.get((arm, session), ()))
        files, invocations, attempts, ledger, seen, hrecs, drecs = [], [], [], [], [], [], []
        main_file = {}                                       # lang -> the main invocation's rows file (a faulted attempt names it, B3)
        legs = [leg for b in sched["blocks"] for leg in b["legs"]]
        for k, leg in enumerate(legs):
            lang = leg["lang"]
            members = [i for i in ids if lang_of(i) == lang]
            main = [i for i in members if i not in dnf and i not in hdnf and i not in reruns]
            run, rrun = self._run_id(arm, session, lang), self._run_id(arm, session, lang, rerun=True)
            self.runs[(arm, session, lang)] = run
            seen.append(run)
            stem = f"{MODEL}.{session}.opencode_{lang}"
            groups = [(main, run, "full", 0, f"{stem}.L{k}.full.a1")]
            if reruns & set(members):
                seen.append(rrun)
                groups.append(([i for i in members if i in reruns], rrun, "rerun", 1, f"{stem}.L{k}.rerun.a1"))
            for rids, rid_run, phase, rindex, fname in groups:
                lines = []
                for rid in rids:
                    item = rid.split("/", 1)[1]
                    mdoc = self._manifest_doc(arm, session, rid)
                    mrel = f"{self.ns}/{self.att(arm, session)}/evidence/{rid_run}/{lang}__{item}.final_tree/manifest.json"
                    self._write_json(self.p(*mrel.split("/")), mdoc)
                    msha = sha_bytes((self.p(*mrel.split("/"))).read_bytes())
                    o = self._outcome(arm, session, rid)
                    row = dict(bench="opencode", schema_version=3, scaffold=f"opencode-v2-web-{self.corpus}", id=rid, model=MODEL, sample=0,
                               passed=o["passed"], acc=int(o["passed"]), converged=o["converged"], nonconv_kind=o.get("nonconv_kind"),
                               nonconv_flags=[], file_changed=True, test_modified=False, wall_s=60.0 + ids.index(rid),
                               sampler_seed=self.seed(session, rid), seed_base=SEED[session],
                               final_tree=dict(manifest=(f"$STACK_WORKDIR/opencode_transcripts/{MODEL}/{fname}.{rid_run}/"
                                                         f"{lang}__{item}.final_tree/manifest.json"),
                                               manifest_sha256=msha, files={}, missing=[]),
                               grade_reports=[dict(boundary=1, seq=1, final=True, outcome="parsed", artifacts={})])
                    row.update({k2: v for k2, v in o.items() if k2 not in ("passed", "converged", "nonconv_kind")})
                    if rid in acct:
                        row["accounting_fault"] = True
                    lines.append(json.dumps(row, sort_keys=True))
                    files.append(dict(destination="main", published=f"{self.prefix()}/{mrel}", published_sha256=msha, sha256=msha,
                                      source="x", compression=None, exclusion_reason=None))
                    slot = self.slot(session, rid)
                    rec = self._item_record(arm, session, rid, rindex)
                    ready = ph.seal(dict(slot=slot, rerun_index=rindex))
                    rec = ph.seal(dict({k2: v for k2, v in rec.items() if k2 != "sha256"}, ready_sha256=ready["sha256"]))
                    sf = cr.slot_file(slot)
                    sfx = "" if not rindex else f".r{rindex}"
                    self._write_json(att / "items" / f"{sf}{sfx}.json", rec)
                    self._write_json(att / "items" / f"{sf}{sfx}.ready.json", ready)
                    ledger.append(dict(slot=slot, kind="row", invocation=f"{session}/{fname}.jsonl", index=len(ledger), rerun_index=rindex,
                                       **({"accounting_fault": True} if rid in acct else {})))
                    attempts.append(dict(slot=slot, rerun_index=rindex, disposition="accepted", load=0, load_gen=0,
                                         invocation=f"{session}/{fname}.jsonl", output_tokens=rec["totals"]["generated_tokens"],
                                         **({"accounting_fault": True} if rid in acct else {})))
                    if rid in acct:
                        self._write_json(att / "items" / f"{sf}{sfx}.accounting.json",
                                         ph.seal(dict(slot=slot, rerun_index=rindex, row_sha256=ph.row_sha256(json.loads(lines[-1])),
                                                      item_record_sha256=rec["sha256"], failed_checks=["boundary_count"],
                                                      disposition="accounting_fault")))
                    if rindex == 1:                              # the faulted attempt 0: ready record + a harness_fault attempt
                        self._write_json(att / "items" / f"{sf}.ready.json", ph.seal(dict(slot=slot, rerun_index=0)))
                        attempts.append(dict(slot=slot, rerun_index=0, disposition="harness_fault", load=0, load_gen=0,
                                             reason="hook infrastructure error at ready (synthetic)",
                                             **({"invocation": main_file[lang]} if lang in main_file else {})))
                if rids:
                    (att / session).mkdir(exist_ok=True)
                    (att / session / f"{fname}.jsonl").write_text("".join(x + "\n" for x in lines))
                    man = pinned_manifest(arm, lang) if self.corpus == "tg2" else self._tg1_manifest(arm, session, lang, k)
                    if self.manifest_hook:
                        man = self.manifest_hook(arm, session, lang, man)
                    self._write_json(att / session / f"{fname}.manifest.json", man)
                    if rindex == 0:
                        main_file[lang] = f"{session}/{fname}.jsonl"
                        if man.get("run_id") and (reruns | set(hdnf)) & set(members):
                            seen.append(man["run_id"])      # B3: the faulted attempt's run = its invocation manifest's `run_id`
                    if rids:
                        invocations.append(dict(leg_key=[0, lang, k], phase=phase, attempt=1, worker_n=0, file=f"{session}/{fname}.jsonl",
                                                manifest=f"{session}/{fname}.manifest.json", status="validated",
                                                expected_slots=[self.slot(session, i) for i in rids],
                                                accepted_slots=[self.slot(session, i) for i in rids],
                                                sha256=sha_bytes((att / session / f"{fname}.jsonl").read_bytes()), load_gen=0,
                                                slot_base=f"{self.corpus}-p426|oc|{MODEL}|{session}|{lang}", rerun_index=rindex))
            for rid in members:
                slot = self.slot(session, rid)
                sf = cr.slot_file(slot)
                if rid in dnf:
                    drecs.append(dict(slot=slot, item=rid.split("/", 1)[1], session=session, language=lang, arm=arm, pick=MODEL, attempt=n,
                                      abort=dict(cause="transport", error="synthetic", evidence=None)))
                    ledger.append(dict(slot=slot, kind="dnf", invocation=None, index=len(ledger)))
                if rid in hdnf:
                    rec = ph.seal(dict(slot=slot, kind=hdnf[rid], reason="second pre-outcome harness fault (synthetic)", rerun_index=1))
                    hrecs.append(rec)
                    self._write_json(att / "items" / f"{sf}.harness_dnf.json", rec)
                    self._write_json(att / "items" / f"{sf}.ready.json", ph.seal(dict(slot=slot, rerun_index=0)))
                    attempts.append(dict(slot=slot, rerun_index=0, disposition="harness_fault", load=0, load_gen=0, reason="first fault",
                                         **({"invocation": main_file[lang]} if lang in main_file else {})))
                    ledger.append(dict(slot=slot, kind="dnf", invocation=None, index=len(ledger)))
        if not list((att / session).glob("*.jsonl")):             # an all-DNF attempt: an empty rows file + manifest per language leg
            for k, leg in enumerate(legs):
                fname = f"{MODEL}.{session}.opencode_{leg['lang']}.L{k}.full.a1"
                (att / session / f"{fname}.jsonl").write_text("")
                self._write_json(att / session / f"{fname}.manifest.json",
                                 pinned_manifest(arm, leg["lang"]) if self.corpus == "tg2"
                                 else self._tg1_manifest(arm, session, leg["lang"], k))
        chain = dict(status="finished", mode="chain", rc=0, predictor="mtp", p426=True, corpus=self.corpus,
                     artifacts=dict(campaign_core=dict(commit=COMMIT[arm], tag=COMMIT[arm])),
                     progress=dict(loads=[], invocations=invocations, slot_attempts=attempts, pre_spawn=[], txns=[], abort_evidence=[],
                                   seen_run_ids=seen),
                     p426_dnf=drecs, p426_harness_dnf=hrecs, p426_ledger=ledger, p426_invalid=[], sessions=[],
                     frozen_record=dict(path="$STACK_WORKDIR/run/v8_base.json", sha256=self.v8["sha256"]))
        if self.corpus == "tg2":
            chain["tg2_leg"] = session
        self._write_json(att / "chain.json", chain)
        harvest = sealed(dict(attempt=1, leg=self.att(arm, session)[:-3], state="VALID", files=files, created="2026-11-20T00:00:00Z"))
        self._write_json(att / "HARVEST.json", harvest)
        self._write_json(att / "receipt.json", sealed(dict(argv=[], env={})))
        leg = dict(attempt=1, leg=self.att(arm, session)[:-3], state="VALID", speed_valid=True, speed_reason="ok")
        leg.update(self.legs.get((arm, session), {}))
        self._write_json(att / "leg.json", sealed(leg))

    def _tg1_manifest(self, arm, session, lang, k):
        tq4 = arm != "n16"
        flags = {"--model": "caslca/x", "--draft-kind": "mtp", "--max-kv-size": "262144"}
        entry = dict(hf_path="caslca/x", draft_kind="mtp", max_kv_cache_size=262144)
        if tq4:
            flags.update({"--kv-bits": "4", "--tq4-attention": "m72_exact"})
            entry.update(kv_bits=4, tq4_attention="m72_exact")
        ident = dict(flags=flags, entry=entry, target=dict(kind="hf", repo="caslca/x", revision="r1"), draft=None,
                     apc=dict(router="0", worker="0"), retain_prompt_end="on")
        return dict(model=MODEL, box="box-1", fingerprint_version=9, sampling_profile="deployed", timestamp=f"t-{arm}-{session}-{lang}",
                    sampling=dict(temperature=0.6, top_p=0.95, max_tokens=102400, thinking_budget=81920),
                    registry=dict(sha256=("r" if tq4 else "q") * 64), router=dict(pid=1000 + k, config=f"/wt/{arm}"),
                    git=dict(stack_head=COMMIT[arm], serving_path={"src/mlx-vlm": "t" * 40, "src/mlx-serve": "u" * 40}),
                    quant=dict(effective_bits=4.5),
                    kv=dict(kv_bits=4 if tq4 else 0, kv_quant_scheme="turboquant" if tq4 else "uniform", max_kv_cache_size=262144,
                            prefill_step_size=4096, hf_path="caslca/x"),
                    runtime=dict(apc_enabled=False, draft_kind="mtp", mtp_verify_scan="joint_v1", tq4_attention="m72_exact" if tq4 else "off",
                                 lang=lang, seed_base=SEED[session], sampling_profile="deployed", probe_code_sha256="9" * 64,
                                 scaffold_policy_sha256="c" * 64, generation_identity_sha256="g" * 64,
                                 invocation_nonce=f"n-{arm}-{session}-{lang}", arm_identity=ident,
                                 arm_identity_sha256=sha_bytes(json.dumps(ident, sort_keys=True).encode())),
                    worker=dict(pid=2000 + k, create_time=1.5), run_id=f"20261114T00000{k}-{arm}{session}")

    def write_dossier(self, session):
        arms = {arm: dict(attempt=self.att(arm, session),
                          harvest_sha256=sha_bytes(self.adir(arm, session, "HARVEST.json").read_bytes()),
                          receipt_sha256=sha_bytes(self.adir(arm, session, "receipt.json").read_bytes())) for arm in ("n16", "x")}
        self._write_json(self.p(self.ns, "pairs", f"{session}__n16-a1__x-a1.json"),
                         sealed(dict(pair=session, lever="kv", ref="n16", test="x", verdict="PASS", arms=arms,
                                     differences=copy.deepcopy(DIFFS), at="2026-11-20T00:00:00Z")))
        if session == "pilot" and getattr(self, "amendment", None) is not None:
            self.publish_amendment()                         # the amendment binds the pilot dossier's bytes

    def publish_amendment(self):
        """tg2 (S29 rule 3.6): the sealed post-pilot `run/amendment.json` in `p426_freeze.write_amendment_tg2`'s shape, binding this
        v8 base and the pilot dossier's bytes; every decider chain naming the v8 base or a previous amendment is re-pointed at it
        (the runner runs the pilot on the v8 base, every decider leg on the amendment). No pilot dossier -> nothing published."""
        if self.corpus != "tg2":
            return None
        dossier = self.p(self.ns, "pairs", "pilot__n16-a1__x-a1.json")
        if not dossier.is_file():
            return None
        self.amendment = publish_tg2_amendment(self.p(self.ns), self.v8, dossier, self.amendment)
        return self.amendment

    def write_sequence(self, extra=None):
        legs = [dict(leg=self.att(a, s)[:-3], attempt=1, state=(self.legs.get((a, s)) or {}).get("state", "VALID"))
                for s in self.sessions for a in ("n16", "x")]
        pairs = [dict(pair=s, n16=self.att("n16", s), x=self.att("x", s), dossier=f"pairs/{s}__n16-a1__x-a1.json", verdict="PASS",
                      published=True) for s in self.sessions]
        if getattr(self, "recorded_pilot", False):
            legs[:0] = recorded_pilot_legs()
            pairs.insert(0, recorded_pilot_pair())
        seq = dict(legs=legs, pairs=pairs, reruns=[], rechecks={}, harvested=[])
        seq.update(extra or {})
        self._write_json(self.p(self.ns, "run", "sequence.json"), seq)

    def write_rechecks(self, inside=True, operator_review=False, ack=None, s1_attempts=None, gates=("s1", "s2")):
        """The sequencer's sealed `run/recheck-<gate>.json` (`p426_wave2.ensure_recheck`'s document) and its `sequence.json` records."""
        from bench import m76_rule

        _rep, report_sha = m76_rule.load_report()
        seq = self.load(self.ns, "run", "sequence.json")
        gate_sessions = {"s1": ("s1",), "s2": ("s1", "s2")}
        for gate in gates:
            attempts = {arm: [self.att(arm, s) for s in gate_sessions[gate]] for arm in ("n16", "x")}
            if gate == "s1" and s1_attempts:
                attempts = s1_attempts
            result = dict(axis="A8", inside=inside, operator_review=operator_review, outside_reasons=[] if inside else ["synthetic"],
                          report_sha256=report_sha, committed_alpha_star=0.001, alpha_star_applied=0.001)
            doc = ph.seal(dict(gate=gate, axis="A8", sessions=list(gate_sessions[gate]), ref="n16", test="x", attempts=attempts,
                               recheck=result, at="2026-11-20T00:00:00Z"))
            self._write_json(self.p(self.ns, "run", f"recheck-{gate}.json"), doc)
            rec = dict(sha256=doc["sha256"], path=f"run/recheck-{gate}.json", inside=inside, operator_review=operator_review)
            if gate == "s1" and ack:
                rec["ack"] = dict(sha256=doc["sha256"], at="2026-11-20T00:00:00Z")
            seq.setdefault("rechecks", {})[gate] = rec
        self._write_json(self.p(self.ns, "run", "sequence.json"), seq)

    def write_latency(self, rows=None):
        """`run/exec_latency.json`: rows `{t, fresh_ms, repeat_ms, true_ms, threatlocker_cpu}`, sealed with `ph.seal`."""
        rows = rows if rows is not None else [dict(t=f"2026-11-20T0{i}:00:00Z", fresh_ms=120.0 + i, repeat_ms=30.0, true_ms=25.0,
                                                    threatlocker_cpu=1.5) for i in range(6)]
        self._write_json(self.p(self.ns, "run", "exec_latency.json"), ph.seal(dict(rows=rows)))

    # ------------------------------------------------------------------------------------------------------------- mutation
    def load(self, *rel):
        return json.loads(self.p(*rel).read_text())

    def edit_harvest(self, arm, session, fn):
        path = self.adir(arm, session, "HARVEST.json")
        doc = json.loads(path.read_text())
        fn(doc)
        self._write_json(path, sealed(doc))
        self.write_dossier(session)

    def edit_chain(self, arm, session, fn):
        path = self.adir(arm, session, "chain.json")
        doc = json.loads(path.read_text())
        fn(doc)
        self._write_json(path, doc)

    def edit_row(self, arm, session, rid, **patch):
        for f in sorted(self.adir(arm, session, session).glob("*.jsonl")):
            rows = [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
            if any(r["id"] == rid for r in rows):
                for r in rows:
                    if r["id"] == rid:
                        r.update(patch)
                f.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
                self._rehash_invocation(arm, session, f, rid, next(r for r in rows if r["id"] == rid))
                return
        raise KeyError(rid)

    def _rehash_invocation(self, arm, session, rows_file, rid, row):
        """B2: the invocation record that names the changed rows file carries its new sha256; an accounting sidecar of the row is
        re-sealed over the new row."""
        path = self.adir(arm, session, "chain.json")
        chain = json.loads(path.read_text())
        for inv in chain["progress"]["invocations"]:
            if inv["file"] == f"{session}/{rows_file.name}":
                inv["sha256"] = sha_bytes(rows_file.read_bytes())
                side = self.adir(arm, session, "items", ph.record_name(self.slot(session, rid), inv.get("rerun_index", 0),
                                                                        "accounting.json"))
                if side.is_file():
                    side.write_text(dumps(ph.seal(dict(json.loads(side.read_text()), row_sha256=ph.row_sha256(row)))))
        path.write_text(dumps(chain))

    def manifest_rel(self, arm, session, rid, run=None):
        lang, item = rid.split("/", 1)
        run = run or self.runs[(arm, session, lang)]
        return f"{self.ns}/{self.att(arm, session)}/evidence/{run}/{lang}__{item}.final_tree/manifest.json"

    def drop_final_tree_block(self, arm, session, rid):
        self.edit_row(arm, session, rid, final_tree=None)

    def unpublish_manifest(self, arm, session, rid):
        rel = f"{self.prefix()}/{self.manifest_rel(arm, session, rid)}"
        self.edit_harvest(arm, session, lambda d: d.__setitem__("files", [f for f in d["files"] if f.get("published") != rel]))

    def duplicate_harvest_entry(self, arm, session, rid):
        """The same destination-main final-tree manifest listed twice in HARVEST.json (several matches for the row's run id + item)."""
        rel = f"{self.prefix()}/{self.manifest_rel(arm, session, rid)}"

        def dup(d):
            d["files"].append(copy.deepcopy(next(f for f in d["files"] if f.get("published") == rel)))
        self.edit_harvest(arm, session, dup)

    def publish_extra_manifest(self, arm, session, rid, run, content=None):
        """A second HARVEST destination-main final-tree manifest for `rid` (under `run`)."""
        rel = self.manifest_rel(arm, session, rid, run=run)
        doc = content or self._manifest_doc(arm, session, rid, note=f"extra:{run}")
        self._write_json(self.p(*rel.split("/")), doc)
        sha = sha_bytes(self.p(*rel.split("/")).read_bytes())
        self.edit_harvest(arm, session, lambda d: d["files"].append(
            dict(destination="main", published=f"{self.prefix()}/{rel}", published_sha256=sha, sha256=sha, source="x", compression=None,
                 exclusion_reason=None)))
        return sha


# ------------------------------------------------------------------------------------------------------------------ checks
def test_pinned_manifest_fixtures_are_the_committed_pilot_manifests():
    pins = json.loads((FIX / "PINS.json").read_text())
    for rel, want in pins.items():
        if rel.startswith("_"):
            continue
        assert hashlib.sha256((FIX / rel).read_bytes()).hexdigest() == want, rel


def test_the_pinned_draw_is_the_one_the_schedules_name():
    raw = (REPO / "benchmark" / "m65" / "tg2_draw.json").read_bytes()
    assert schedules.draw_sha256_of(json.loads(raw)) == schedules.TG2_DRAW_SHA256


def test_fixtures_carry_no_home_path_user_or_host():
    import re
    import getpass
    import socket
    # the box's username and hostname are read at run time (this file holds neither, nor any home path)
    names = {n for n in (getpass.getuser(), socket.gethostname().split(".")[0]) if len(n) >= 4}
    pat = re.compile("|".join([r"/Users/", r"/home/", r"\.local\b", *(re.escape(n) for n in sorted(names))]))
    for p in FIX.rglob("*"):
        if p.is_file():
            assert not pat.search(p.read_text(errors="replace")), p.name


@pytest.mark.parametrize("session,n", [("pilot", 4), ("s1", 80), ("s2", 80), ("reload", 20)])
def test_tg2_world_sessions_are_the_pinned_draws(session, n):
    sched = tg2_schedule(session)
    schedules.check_tg2_p426(sched, draw_doc(), session)
    assert len(schedule_ids(sched)) == n


def test_the_world_is_valid_for_the_baseline_chain_reader(tmp_path):
    """The world's chain.json / rows are accepted by `chain_rows.load_slots` (reruns, harness DNFs, accounting faults included):
    the fixtures are the S27 record shapes the baseline reader already knows."""
    ids = schedule_ids(tg2_schedule("pilot"))
    w = World(tmp_path, sessions=("pilot",), reruns={("n16", "pilot"): [ids[0]]}, accounting={("x", "pilot"): [ids[1]]},
              hdnf={("x", "pilot"): {ids[2]: "harness_fault_dnf"}})
    for arm in ("n16", "x"):
        chain = json.loads(w.adir(arm, "pilot", "chain.json").read_text())
        table = cr.load_slots(chain, w.adir(arm, "pilot"))
        assert len(table.scored) == 4
    t = cr.load_slots(json.loads(w.adir("x", "pilot", "chain.json").read_text()), w.adir("x", "pilot"))
    assert sum(1 for s in t.scored.values() if s.accounting_fault) == 1
    assert sum(1 for s in t.scored.values() if s.source == "harness_dnf") == 1
