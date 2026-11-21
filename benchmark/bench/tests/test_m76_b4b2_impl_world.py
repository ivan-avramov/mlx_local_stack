"""M76 B4b-2: a synthetic `benchmark/results/m76/wave2.tg2/` of the tg2 KV pair (N16, X) for the B8-A8 / signals / panel tests.

The layout copies the harvested tg2 pilot pair (old identity; real shapes) and the S27 records (harness DNFs, reruns, accounting
faults): v8 base, sequence (legs, pairs, rechecks), dossiers, per attempt leg / chain / HARVEST / schedule / receipt, rows and
invocation manifests per language, item records keyed by rerun index, the final-tree manifests HARVEST publishes. The schedules
are `schedules.tg2_p426` of the real pinned draw (so the plan binding is checked for real). Nothing here reads the real rows."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bench import chain_rows as cr
from bench import m76_rule
from bench import p426_hooks as ph
from bench import p426_verify as V
from bench import rowschema
from bench import schedules

BENCH = Path(__file__).resolve().parents[2]
MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
PREFIX = "benchmark/results/m76"
NS = "wave2.tg2"
ARMS = ("n16", "x")
COMMIT = {"n16": "a1" * 20, "x": "b2" * 20}
DRAW = json.loads((BENCH / "m65" / "tg2_draw.json").read_text())
ALL_SESSIONS = ("s1", "s2", "pilot", "reload")
SEED = {"s1": 1001, "s2": 2002, "pilot": 1001, "reload": 1001}
WINDOW = {"s1": ("2026-11-20T01:00:00Z", "2026-11-20T09:00:00Z"), "s2": ("2026-11-20T10:00:00Z", "2026-11-20T18:00:00Z"),
          "pilot": ("2026-11-19T20:00:00Z", "2026-11-19T21:00:00Z"), "reload": ("2026-11-20T19:00:00Z", "2026-11-20T22:00:00Z")}
# change review r1 B4: the v8 identity every invocation manifest carries (the real records' shape: runtime + policy)
IDENTITY = dict(probe_code_sha256="9" * 64, scaffold_policy_sha256="c" * 64, generation_identity_sha256="e" * 64,
                tg2_draw_sha256=schedules.TG2_DRAW_SHA256, tg2_universe_sha256=schedules.TG2_UNIVERSE_SHA256,
                tg2_image_id="sha256:" + "5" * 64, grader_image_id="sha256:" + "6" * 64)


def row_seed(s, rid):
    """r1 B10: the plan's seed of a row (`rowschema.sample_seed(id, 0, TG2_P426_LEGS[session] seed)`, as the runner draws it)."""
    return rowschema.sample_seed(rid, 0, SEED[s])


def dumps(doc):
    return json.dumps(doc, sort_keys=True, indent=1) + "\n"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sealed(doc):
    """`p426_hooks.seal` (the same canonical JSON as `p426_harvest._canon_sha`, which B8's self-hash checks use)."""
    return ph.seal({k: v for k, v in doc.items() if k != "sha256"})


def attempt(arm, s, n=1):
    return f"tg2-m76-{arm}-{s}.a{n}"


def slot_of(s, rid):
    lang, item = rid.split("/", 1)
    return f"tg2-p426|oc|{MODEL}|{s}|{lang}|{item}"


def position(rid):
    lang = rid.split("/", 1)[0]
    return DRAW["languages"][lang]["permutation"].index(rid)


def manifest(arm, s, lang):
    """A tg2 invocation manifest of `provenance.gather` + `arm_runner`'s shape: the arms differ only in the KV / mode fields, the
    arm commit, the observed worker fingerprint's KV flags / entry keys, and the per-invocation identity."""
    tq4 = arm != "n16"
    flags = {"--model": "caslca/x", "--draft-kind": "mtp", "--max-kv-size": "262144"}
    entry = dict(hf_path="caslca/x", draft_kind="mtp", max_kv_cache_size=262144)
    if tq4:
        flags.update({"--kv-bits": "4", "--tq4-attention": "m72_exact"})
        entry.update(kv_bits=4, tq4_attention="m72_exact")
    ident = dict(flags=flags, entry=entry, apc=dict(router="0", worker="0"))
    return dict(
        model=MODEL, box="box-1", fingerprint_version=9, sampling_profile="deployed", timestamp=f"t-{arm}-{s}-{lang}",
        sampling=dict(temperature=0.5, top_p=0.95, max_tokens=102400, thinking_budget=81920),
        registry=dict(sha256=("r" if tq4 else "q") * 64), router=dict(pid=1000, config=f"<WT>/m76-g2-{arm}/main_models.yaml"),
        git=dict(stack_head=COMMIT[arm], serving_path={"src/mlx-vlm": "t" * 40}), quant=dict(effective_bits=4.5),
        kv=dict(kv_bits=4 if tq4 else 0, kv_quant_scheme="turboquant", max_kv_cache_size=262144),
        runtime=dict(apc_enabled="0", draft_kind="mtp", tq4_attention="m72_exact" if tq4 else "off", lang=lang,
                     seed_base=SEED[s], probe_code_sha256=IDENTITY["probe_code_sha256"],
                     scaffold_policy_sha256=IDENTITY["scaffold_policy_sha256"],
                     generation_identity_sha256=IDENTITY["generation_identity_sha256"],
                     policy=dict(corpus_identity=dict(draw_sha256=IDENTITY["tg2_draw_sha256"],
                                                      universe_sha256=IDENTITY["tg2_universe_sha256"], image=IDENTITY["tg2_image_id"]),
                                 toolchain=dict(grader_image_id=IDENTITY["grader_image_id"])),
                     invocation_nonce=f"n-{arm}-{s}-{lang}", arm_identity=ident,
                     arm_identity_sha256=sha(json.dumps(ident, sort_keys=True).encode()),
                     worktree=f"$STACK_WORKDIR/worktrees/m76-g2-{arm}"),
        worker=dict(pid=2000, create_time=1.5), run_id=f"run-{arm}-{s}-{lang}")


class A8World:
    """`benchmark/results/m76/wave2.tg2/` of (N16, X). `rows` {(arm, session): {id: patch}}: a patch updates the row; the keys
    `_dnf` ("transport" / "harness"), `_rerun` (accepted at rerun index 1 after one harness fault) and `_accounting` (an
    accounting-fault row with its sealed sidecar) make S27 slots. `pairs` = the sessions with a pair record (default: all)."""

    def __init__(self, base, sessions=ALL_SESSIONS, rows=None, rechecks=True, pairs=None):
        self.base = Path(base)
        self.root = self.base / "repo" / PREFIX
        self.ns = self.root / NS
        self.rows = rows or {}
        (self.ns / "run").mkdir(parents=True)
        (self.ns / "pairs").mkdir(parents=True)
        draw = self.base / "repo" / V.TG2_DRAW_REL                        # the repo's pinned draw (B8-A8 `repo_inputs`)
        draw.parent.mkdir(parents=True)
        draw.write_bytes((BENCH / "m65" / "tg2_draw.json").read_bytes())
        self.v8 = sealed(dict(kind="p426_v8_base", lever="kv", corpus="tg2", arms=["n16", "x"], build="s3",
                                    n16_commit=COMMIT["n16"], x_commit=COMMIT["x"], gitlinks={}, created="2026-11-19T22:06:52Z",
                                    **IDENTITY))
        (self.ns / "run" / "v8_base.json").write_text(dumps(self.v8))
        self.sessions = tuple(sessions)
        for s in self.sessions:
            for arm in ARMS:
                self.build_attempt(arm, s)
        self.pairs = tuple(pairs) if pairs is not None else self.sessions
        for s in self.pairs:
            self.dossier(s)
        self.seq = dict(legs=[dict(leg=attempt(a, s)[:-3], attempt=1, state="VALID") for s in self.sessions for a in ARMS],
                        pairs=[dict(pair=s, n16=attempt("n16", s), x=attempt("x", s), dossier=f"pairs/{s}__n16-a1__x-a1.json",
                                    verdict="PASS", published=True) for s in self.pairs],
                        harvested=[], rechecks={}, reruns=[])
        if rechecks:
            for gate, need in (("s1", ("s1",)), ("s2", ("s1", "s2"))):
                if all(s in self.pairs for s in need):
                    self.recheck(gate)
        self.save_seq()

    # -- paths
    def att(self, arm, s):
        return self.ns / attempt(arm, s)

    def save_seq(self):
        (self.ns / "run" / "sequence.json").write_text(dumps(self.seq))

    def chain(self, arm, s):
        return json.loads((self.att(arm, s) / "chain.json").read_text())

    def put_chain(self, arm, s, doc):
        (self.att(arm, s) / "chain.json").write_text(dumps(doc))

    def schedule(self, s):
        return schedules.tg2_p426(DRAW, s, MODEL, "mtp")

    def ids(self, s):
        return [i for leg in self.schedule(s)["blocks"][0]["legs"] for i in leg["invocations"][0]["expect"]]

    # -- one attempt
    def build_attempt(self, arm, s):
        att = self.att(arm, s)
        (att / s).mkdir(parents=True)
        (att / "items").mkdir()
        sched = self.schedule(s)
        (att / "schedule.json").write_text(dumps(sched))
        patches = self.rows.get((arm, s)) or {}
        files, attempts, ledger, dnf, hdnf, seen, invocations = [], [], [], [], [], [], []
        start, end = WINDOW[s]
        for li, leg in enumerate(sched["blocks"][0]["legs"]):
            lang, stem = leg["lang"], leg["stem"]
            lines, rerun_lines = [], []
            full = f"{stem}.L{li}.full.a1.jsonl"
            rerun_file = f"{stem}.L{li}.rerun.a1.jsonl"
            for rid in leg["invocations"][0]["expect"]:
                patch = dict(patches.get(rid) or {})
                kind, rerun, acct = patch.pop("_dnf", None), patch.pop("_rerun", False), patch.pop("_accounting", False)
                slot = slot_of(s, rid)
                lang_, item = rid.split("/", 1)
                if kind == "transport":
                    dnf.append(dict(slot=slot, session=s, language=lang_, item=item, abort=dict(cause="transport")))
                    ledger.append(dict(slot=slot, kind="dnf", invocation=f"{s}/{full}", index=len(ledger)))
                    continue
                if kind == "harness":
                    rec = ph.seal(dict(slot=slot, kind="harness_fault_dnf", reason="hook_infra at ready: twice", stage="ready",
                                       rerun_index=1))
                    hdnf.append(rec)
                    (att / "items" / f"{cr.slot_file(slot)}.harness_dnf.json").write_text(dumps(rec))
                    attempts += [dict(slot=slot, rerun_index=k, disposition="harness_fault", reason=f"hook_infra at ready ({k})",
                                      stage="ready", load=0, load_gen=0, invocation=f"{s}/{full}") for k in (0, 1)]
                    ledger.append(dict(slot=slot, kind="dnf", invocation=f"{s}/{full}", index=len(ledger)))
                    continue
                k = 1 if rerun else 0
                run = f"20261120T{position(rid):06d}-{arm}{s}{lang_}{'r' if rerun else ''}"
                seen.append(run)
                inv = f"{s}/{rerun_file if rerun else full}"
                stemdir = f"{stem}.L{li}.{'rerun' if rerun else 'full'}.a1.{run}"
                mrel = f"{NS}/{attempt(arm, s)}/evidence/{run}/{lang_}__{item}.final_tree/manifest.json"
                mp = self.root / mrel
                mp.parent.mkdir(parents=True, exist_ok=True)
                mp.write_text(dumps(dict(files={"sol.txt": sha(f"{arm}|{s}|{rid}".encode())}, missing=[])))
                files.append(dict(destination="main", published=f"{PREFIX}/{mrel}", published_sha256=sha(mp.read_bytes()),
                                  sha256=sha(mp.read_bytes()), source="x", compression=None, exclusion_reason=None))
                row = dict(bench="opencode", schema_version=3, id=rid, model=MODEL, sample=0, passed=True, acc=1, converged=True,
                           nonconv_kind=None, nonconv_flags=[], sampler_seed=row_seed(s, rid), seed_base=SEED[s],
                           wall_s=100.0, final_tree=dict(manifest=f"$STACK_WORKDIR/opencode_transcripts/{MODEL}/{stemdir}/"
                                                                  f"{lang_}__{item}.final_tree/manifest.json",
                                                         manifest_sha256=sha(mp.read_bytes()), files={}),
                           grade_reports=[dict(final=True, outcome="parsed", seq=1, boundary=1, artifacts={})])
                row.update(patch)
                if acct:                                  # r1 B5: the row carries its accounting-fault marker (S27 §5.3)
                    row["accounting_fault"] = True
                (rerun_lines if rerun else lines).append(json.dumps(row, sort_keys=True))
                rec = ph.seal(dict(case="completed", verdict="reconciled", slot=slot, ready_sha256="0" * 64,
                                   totals=dict(requests=2, generated_tokens=302, decode_s=10.0, accepted=80, proposed=100,
                                               prompt_tokens=1000, decode_rate_source="completed requests (spec 8)"),
                                   requests=[dict(generated_tokens=151, decode_tok_s=30.0, error=None)] * 2))
                (att / "items" / ph.record_name(slot, k, "json")).write_text(dumps(rec))
                if rerun:
                    attempts.append(dict(slot=slot, rerun_index=0, disposition="harness_fault", reason="grader_infra at generation",
                                         stage="generation", load=0, load_gen=0, invocation=f"{s}/{full}"))
                    seen.append(f"run-{arm}-{s}-{lang_}")      # r1 B3: the faulted attempt's run = its invocation manifest's
                a = dict(slot=slot, rerun_index=k, disposition="accepted", load=0, load_gen=0, invocation=inv)
                e = dict(slot=slot, kind="row", invocation=inv, index=len(ledger), **({"rerun_index": k} if k else {}))
                if acct:
                    a["accounting_fault"] = e["accounting_fault"] = True
                    ph.write_accounting(att, slot, k, json.loads(json.dumps(row, sort_keys=True)), rec, ["boundary_count"])
                attempts.append(a)
                ledger.append(e)
            for name, these, k in ((full, lines, 0), (rerun_file, rerun_lines, 1)):
                if these or name == full:
                    (att / s / name).write_text("".join(x + "\n" for x in these))
                    (att / s / name.replace(".jsonl", ".manifest.json")).write_text(dumps(manifest(arm, s, lang)))
                if these or name == full:                 # r1 B2: the invocation record `chain_rows.load_slots` reads
                    got = [slot_of(s, json.loads(x)["id"]) for x in these]
                    want = got if k else [slot_of(s, i) for i in leg["invocations"][0]["expect"]]
                    invocations.append(dict(leg_key=[0, lang, li], phase="rerun" if k else "full", attempt=1, worker_n=0,
                                            file=f"{s}/{name}", manifest=f"{s}/{name.replace('.jsonl', '.manifest.json')}",
                                            status="validated" if got == want else "partial_incident", expected_slots=want,
                                            accepted_slots=got, sha256=sha((att / s / name).read_bytes()), load_gen=0,
                                            slot_base=f"tg2-p426|oc|{MODEL}|{s}|{lang}", rerun_index=k))
        (att / "HARVEST.json").write_text(dumps(sealed(dict(attempt=1, leg=attempt(arm, s)[:-3], state="VALID",
                                                                   files=files))))
        (att / "receipt.json").write_text(dumps(sealed(dict(argv=[], env={}))))
        (att / "leg.json").write_text(dumps(sealed(dict(attempt=1, leg=attempt(arm, s)[:-3], state="VALID",
                                                               speed_valid=True, speed_reason="ok", started=start, ended=end))))
        self.put_chain(arm, s, dict(status="finished", artifacts=dict(campaign_core=dict(commit=COMMIT[arm])), tg2_leg=s,
                                    corpus="tg2", frozen_record=dict(path="$STACK_WORKDIR/x", sha256=self.v8["sha256"]),
                                    p426_dnf=dnf, p426_harness_dnf=hdnf, p426_ledger=ledger, p426_holds=[],
                                    progress=dict(slot_attempts=attempts, seen_run_ids=seen, invocations=invocations, loads=[],
                                                  pre_spawn=[])))

    def reseal(self, arm, s):
        """Re-seal HARVEST.json after an edit and rebind the session's dossier."""
        p = self.att(arm, s) / "HARVEST.json"
        p.write_text(dumps(sealed(json.loads(p.read_text()))))
        if s in self.pairs:
            self.dossier(s)

    def harvest(self, arm, s):
        return json.loads((self.att(arm, s) / "HARVEST.json").read_text())

    def put_harvest(self, arm, s, doc):
        (self.att(arm, s) / "HARVEST.json").write_text(dumps(doc))
        self.reseal(arm, s)

    def dossier(self, s):
        arms = {arm: dict(attempt=attempt(arm, s), harvest_sha256=sha((self.att(arm, s) / "HARVEST.json").read_bytes()),
                          receipt_sha256=sha((self.att(arm, s) / "receipt.json").read_bytes())) for arm in ARMS}
        doc = sealed(dict(pair=s, lever="kv", ref="n16", test="x", verdict="PASS", arms=arms,
                                differences=[dict(process="worker", field="argv.worker", n16="",
                                                  x="--kv-bits 4 --tq4-attention m72_exact")]))
        (self.ns / "pairs" / f"{s}__n16-a1__x-a1.json").write_text(dumps(doc))

    def recheck(self, gate, *, inside=True, review=False, attempts=None, report_sha=None, ack=None):
        sessions = {"s1": ["s1"], "s2": ["s1", "s2"]}[gate]
        _rep, rsha = m76_rule.load_report()
        doc = ph.seal(dict(gate=gate, axis="A8", sessions=sessions, ref="n16", test="x",
                           attempts=attempts or {arm: [attempt(arm, s) for s in sessions] for arm in ARMS},
                           recheck=dict(inside=inside, operator_review=review, report_sha256=report_sha or rsha,
                                        alpha_star_applied=0.001), at="2026-11-20T09:30:00Z"))
        (self.ns / "run" / f"recheck-{gate}.json").write_text(dumps(doc))
        rec = dict(sha256=doc["sha256"], path=f"run/recheck-{gate}.json", inside=inside, operator_review=review)
        if ack:
            rec["ack"] = dict(sha256=doc["sha256"] if ack is True else ack, at="2026-11-20T09:40:00Z")
        self.seq.setdefault("rechecks", {})[gate] = rec
        return doc

    def latency(self, rows=None, seal=True):
        rows = rows if rows is not None else [dict(t="2026-11-20T02:00:00Z", fresh_ms=120.0, repeat_ms=40.0, true_ms=30.0,
                                                   threatlocker_cpu=3.0)]
        doc = dict(kind="exec_latency", rows=rows)
        (self.ns / "run" / "exec_latency.json").write_text(dumps(ph.seal(doc) if seal else dict(doc, sha256="0" * 64)))

    # -- verify
    def b8_a8(self, base="b" * 64):
        return V.verify_a8_kv(self.root, base)

    def by(self, base="b" * 64):
        doc = self.b8_a8(base)
        return doc, {p["pair"]: p for p in doc["pairs"]}


def test_the_clean_world_verifies_complete(tmp_path):
    w = A8World(tmp_path)
    doc, by = w.by()
    assert doc["status"] == "complete" and doc["sessions"] == ["s1", "s2"]
    for s in ALL_SESSIONS:
        assert by[s]["accepted"] is True, (s, by[s]["reasons"])
        assert by[s]["keys_accepted"] == {"s1": 80, "s2": 80, "pilot": 4, "reload": 20}[s]
    assert {g: r["status"] for g, r in doc["recheck"].items()} == {"s1": "ok", "s2": "ok"}
    assert all(k.startswith("m76/wave2.tg2/") for k in doc["inputs"]) and list(doc["repo_inputs"]) == [V.TG2_DRAW_REL]
