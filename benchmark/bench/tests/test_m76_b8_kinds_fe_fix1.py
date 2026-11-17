"""M76 B8 kv fix round 1 (spec v1.1 + erratum v1.1a), test-writer delivery 3: one behaviour test group per fix F1–F5 on the REAL
committed `benchmark/results/m76/ids.json`, independent of the implementer's `test_m76_b8_kinds_impl_fixround1.py` (own world, own
oracles; it reuses only my delivery-1 `World`).

Class: (a) fails on candidate 1 / passes on candidate 2; (b) holds on both; (c) a reading of an under-specified point.
NOTE: candidate 1 is no longer applied in this copy, so the (a)/(b) split below is by construction (which behaviour candidate 1
lacked), stated per test; it was not re-run on candidate 1.
"""
from __future__ import annotations

import glob
import hashlib
import inspect
import json
from pathlib import Path

import pytest

from bench import m76_ids as M
from bench import p426_plan as P
from bench import p426_signals as S
from bench import p426_verify as V
from bench.tests.test_m76_b8_kinds_fe_wave1 import ENTRY, PLANNED, REAL_IDS, M1_REASON, World, by_key

BENCH = Path(__file__).resolve().parents[2]
DEPLOYED_KW = {"enable_thinking": True, "reasoning_effort": "medium"}
PAIR = ("n16", "x")


def sha_b(b):
    return hashlib.sha256(b).hexdigest()


@pytest.fixture
def w(tmp_path, monkeypatch):
    world = World(tmp_path, monkeypatch)
    # the signals regrade Math500 through bench.grade (a Path results root) and refuse drift: write each leg's real regrade
    monkeypatch.setattr("bench.generate.results_root", lambda: world.rows)
    from bench import grade

    for label in ("b1", "b2"):
        for arm in PAIR:
            tune = V.kv_tune_of(arm, label, "math500")
            s = grade.grade("math500", ENTRY, tune=tune)
            (world.rows / ENTRY / f"math500.{tune}.score.json").write_text(
                json.dumps({f: s.get(f) for f in ("n", "errors", "correct", "acc_strict")}))
    return world


def rewrite_legs(world, kind, manifest_of):
    orig = world.manifest
    world.manifest = manifest_of(orig)
    for label in ("b1", "b2"):
        for arm in PAIR:
            world.leg(kind, arm, label)
    world.manifest = orig


# =================================================================================================== F1: per-arm facts per arm
# class (a): an arm-local worktree path in a manifest leaf ($STACK_WORKDIR/worktrees/m76-f45-<arm>/…) no longer splits the pair
@pytest.mark.parametrize("template", ["$STACK_WORKDIR/worktrees/m76-f45-{arm}/benchmark/data/vg", "/w/m76-q-{arm}/benchmark/data/vg"])
def test_f1_arm_local_corpus_path_is_accepted(w, template):
    def mk(orig):
        def manifest(arm):
            m = orig(arm)
            m["runtime"] = dict(m["runtime"], corpus=template.format(arm=arm), corpus_sha256="c" * 64)
            return m
        return manifest
    rewrite_legs(w, "vision", mk)
    got = by_key(w.wave1(kinds=("vision",)))
    assert all(got[("vision", b)]["accepted"] for b in ("b1", "b2")), [got[("vision", b)]["reasons"] for b in ("b1", "b2")]


# class (a): a leaf naming the OTHER arm's worktree is a rule-2d reason that names the offending arm
def test_f1_a_path_naming_the_other_arm_is_rejected_naming_the_arm(w):
    def mk(orig):
        def manifest(arm):
            m = orig(arm)
            m["runtime"] = dict(m["runtime"], corpus="/w/m76-f45-n16/benchmark/data/vg", corpus_sha256="c" * 64)
            return m
        return manifest
    rewrite_legs(w, "vision", mk)
    p = by_key(w.wave1(kinds=("vision",)))[("vision", "b1")]
    assert not p["accepted"]
    hits = [r for r in p["reasons"] if "rule 2d" in r and "another arm" in r]
    assert hits and all(" x " in f" {r} " for r in hits), p["reasons"]
    assert not any(r for r in hits if "n16 manifest names" in r)


# class (b): a content hash beside the path stays compared across arms (held on candidate 1 as well)
def test_f1_a_differing_content_hash_beside_the_path_still_rejects(w):
    def mk(orig):
        def manifest(arm):
            m = orig(arm)
            m["runtime"] = dict(m["runtime"], corpus=f"/w/m76-f45-{arm}/d", corpus_sha256=("c" if arm == "n16" else "d") * 64)
            return m
        return manifest
    rewrite_legs(w, "vision", mk)
    p = by_key(w.wave1(kinds=("vision",)))[("vision", "b2")]
    assert not p["accepted"] and any("corpus_sha256" in r for r in p["reasons"]), p["reasons"]


def stamp(world, kind, label, arm, extra_for_x=None):
    """What the runners write: manifest.result_file / result_sha256 of the result file's own bytes (A4: one file per leg; A5: one per
    item). `extra_for_x` makes X's result bytes differ from N16's (equal content) so the stamps cannot be equal across arms."""
    edir = world.rows / ENTRY
    tune = V.kv_tune_of(arm, label, kind)
    if kind == "reasoning":
        stems = [f"reasoning.{tune}"]
    else:
        items = {i["id"]: i for i in world.axes["longctx"]["items"]}
        stems = [f"{'retrieval' if items[i]['task'] == 'retrieval' else 'reasoning'}.{tune}.{i}"
                 for i in world.axes["longctx"][f"block{label[-1]}"]]
    for stem in stems:
        res, mp = edir / f"{stem}.json", edir / f"{stem}.manifest.json"
        if arm == "x" and extra_for_x:
            doc = json.loads(res.read_text())
            doc["records"][0]["rows"][0]["decode_tps"] = extra_for_x
            res.write_text(json.dumps(doc))
        man = json.loads(mp.read_text())
        man.update(result_file=res.name, result_sha256=sha_b(res.read_bytes()))
        mp.write_text(json.dumps(man))
    return stems


@pytest.fixture
def stamped(w):
    for kind in ("reasoning", "longctx"):
        for label in ("b1", "b2"):
            for arm in PAIR:
                stamp(w, kind, label, arm, extra_for_x=21.5)
    return w


# class (a): per-arm result_file / result_sha256 (different bytes per arm, hence different stamps) are accepted
def test_f1_per_arm_result_stamps_are_not_compared_across_arms(stamped):
    got = by_key(stamped.wave1(kinds=("reasoning", "longctx")))
    for kind in ("reasoning", "longctx"):
        for label in ("b1", "b2"):
            assert got[(kind, label)]["accepted"], (kind, label, got[(kind, label)]["reasons"][:3])


# class (a): one arm's result bytes altered after stamping → that pair rejected, the reason names that arm; the other block stays accepted
@pytest.mark.parametrize("kind", ["reasoning", "longctx"])
@pytest.mark.parametrize("arm", ["n16", "x"])
def test_f1_altered_result_bytes_reject_naming_the_arm(stamped, kind, arm):
    stem = stamp(stamped, kind, "b1", arm)[0]                       # re-stamp b1 from the current bytes, then alter one file
    res = stamped.rows / ENTRY / f"{stem}.json"
    res.write_bytes(res.read_bytes() + b" ")
    got = by_key(stamped.wave1(kinds=("reasoning", "longctx")))
    p = got[(kind, "b1")]
    assert not p["accepted"]
    bad = [r for r in p["reasons"] if "result_sha256" in r]
    other = "x" if arm == "n16" else "n16"
    assert bad and all("rule 2d" in r and f" {arm} " in f" {r} " and f" {other} " not in f" {r.split('!=')[0]} " for r in bad), bad
    assert got[(kind, "b2")]["accepted"]


# class (a): a stamp present on one arm and missing on the other → rejected, naming the arm without it
def test_f1_a_missing_stamp_on_one_arm_rejects_naming_it(stamped):
    mp = stamped.rows / ENTRY / f"reasoning.{V.kv_tune_of('x', 'b1', 'reasoning')}.manifest.json"
    man = json.loads(mp.read_text())
    del man["result_sha256"]
    mp.write_text(json.dumps(man))
    p = by_key(stamped.wave1(kinds=("reasoning",)))[("reasoning", "b1")]
    assert not p["accepted"] and any("result_sha256" in r and " x " in f" {r} " for r in p["reasons"]), p["reasons"]


# class (a): a result_file naming another file is rejected, naming the arm
def test_f1_a_result_file_naming_another_file_rejects(stamped):
    mp = stamped.rows / ENTRY / f"reasoning.{V.kv_tune_of('n16', 'b2', 'reasoning')}.manifest.json"
    man = json.loads(mp.read_text())
    man["result_file"] = "reasoning.other.json"
    mp.write_text(json.dumps(man))
    p = by_key(stamped.wave1(kinds=("reasoning",)))[("reasoning", "b2")]
    assert not p["accepted"] and any("result_file" in r and "n16" in r for r in p["reasons"]), p["reasons"]


# class (b): kinds whose runners write no stamps (Math500 / cjudge / vision) verify as before (candidate 2's D1; flagged in the report)
def test_f1_unstamped_kinds_still_verify(w):
    got = by_key(w.wave1(kinds=("math500", "cjudge", "vision")))
    assert all(p["accepted"] for p in got.values()), [p["reasons"] for p in got.values() if not p["accepted"]]


# class (b): the provenance difference outside the whitelist still rejects (sampling)
def test_f1_other_provenance_differences_still_reject(w):
    def mk(orig):
        def manifest(arm):
            m = orig(arm)
            if arm == "x":
                m["sampling"] = dict(m["sampling"], temperature=0.6)
            return m
        return manifest
    rewrite_legs(w, "cjudge", mk)
    p = by_key(w.wave1(kinds=("cjudge",)))[("cjudge", "b1")]
    assert not p["accepted"] and any("sampling.temperature differs" in r for r in p["reasons"])


# =================================================================================================== F2: compute_kv reads completeness
def flags(sig, name="wave1_incomplete"):
    return {f["member"]: f for f in sig["flags"] if f["flag"] == name}


# class (a): a complete planned record raises no wave1_incomplete; M1 is `not_run` with the ruling (never `missing`); tier-2 not flagged
def test_f2_complete_record_has_no_incomplete_flag_and_m1_is_not_run(w):
    sig = S.compute_kv(w.rows, V.verify_all_kv(w.rows, w.repo, PAIR))
    assert flags(sig) == {}
    assert sig["axes"]["M1"]["blocks"] == {b: {"status": "not_run", "ruling": M1_REASON} for b in ("b1", "b2")}
    assert not any("t2" in f.get("member", "") for f in sig["flags"])
    assert all("missing" not in json.dumps(sig["axes"][a]) for a in ("M1",))


# class (a): one rejected planned pair → exactly one blocking flag for it, member "<kind>/<label>", the reason in its text
def test_f2_a_rejected_planned_pair_is_a_blocking_flag(w):
    argv = w.argv("x")
    argv[argv.index("--prefill-step-size") + 1] = "2048"
    w.leg("cjudge", "x", "b2")                        # rebuild, then break the argv by rewriting the receipt
    rp = w.rows / "m76" / "wave1" / V.kv_leg_of("cjudge", "x", "b2") / f"{V.kv_leg_of('cjudge', 'x', 'b2')}.receipt.json"
    rec = json.loads(rp.read_text())
    rec["worker"]["cmdline"] = "202 " + " ".join(argv)
    rp.write_text(json.dumps(rec))
    b8 = V.verify_all_kv(w.rows, w.repo, PAIR)
    assert not by_key(b8["axes"]["wave1"])[("cjudge", "b2")]["accepted"]
    fl = flags(S.compute_kv(w.rows, b8))
    assert set(fl) == {"cjudge/b2"}
    assert fl["cjudge/b2"]["blocking"] is True and "rule 2c" in fl["cjudge/b2"]["text"]


# class (a): an absent planned pair (record lacks it) → a blocking flag for it
def test_f2_an_absent_planned_pair_is_a_blocking_flag(w):
    b8 = V.verify_all_kv(w.rows, w.repo, PAIR)
    b8["axes"]["wave1"]["pairs"] = [p for p in b8["axes"]["wave1"]["pairs"] if (p["kind"], p["block"]) != ("vision", "b1")]
    fl = flags(S.compute_kv(w.rows, b8))
    assert set(fl) == {"vision/b1"} and fl["vision/b1"]["blocking"] is True


# class (a): several rejected pairs → one flag per pair
def test_f2_each_rejected_pair_is_flagged_once(w):
    def mk(orig):
        def manifest(arm):
            m = orig(arm)
            m["runtime"] = dict(m["runtime"], corpus="/w/m76-f45-n16/d", corpus_sha256="c" * 64)
            return m
        return manifest
    rewrite_legs(w, "vision", mk)
    fl = flags(S.compute_kv(w.rows, V.verify_all_kv(w.rows, w.repo, PAIR)))
    assert set(fl) == {"vision/b1", "vision/b2"} and all(f["blocking"] for f in fl.values())


# class (a): the empty subset never reads clean — every planned pair (10) is flagged; a subset records `dropped` (erratum v1.1a, F4 / K2)
def test_f2_f4_a_subset_record_reads_incomplete(w):
    b8 = V.verify_all_kv(w.rows, w.repo, PAIR, kinds=("cjudge",))
    assert b8["axes"]["wave1"]["dropped"] == {"m1": M1_REASON}
    assert set(flags(S.compute_kv(w.rows, b8))) == {f"{k}/{b}" for k in PLANNED if k != "cjudge" for b in ("b1", "b2")}
    assert len(flags(S.compute_kv(w.rows, V.verify_all_kv(w.rows, w.repo, PAIR, kinds=())))) == 10


# class (c): a B8 record that names no parsable build (frozen.path) refuses in the signals rather than guessing the planned kinds
def test_f2_a_record_without_a_build_refuses(w):
    b8 = V.verify_all_kv(w.rows, w.repo, PAIR)
    b8["axes"]["wave1"]["frozen"]["path"] = "somewhere/else.json"
    with pytest.raises(S.RefusalError):
        S.compute_kv(w.rows, b8)


# =================================================================================================== F3: the counter's template kwargs
class Tok:
    """Renders `reasoning_effort` / `enable_thinking` into the prompt length, so a counter that omits them counts fewer tokens."""
    chat_template = "{{ t }}"

    def __init__(self):
        self.calls = []

    def apply_chat_template(self, messages, add_generation_prompt=False, tokenize=False, **kw):
        self.calls.append(dict(kw))
        n = sum(len(m["content"]) for m in messages) // 4 + 7 + (40 if kw.get("reasoning_effort") else 0) + (3 if kw.get("enable_thinking") else 0)
        return list(range(n))


def deployed(monkeypatch, **p):
    from bench import model_params

    monkeypatch.setattr(model_params, "params_for", lambda entry, profile=None: dict(p) if profile == "deployed" else {})


# class (a): every apply_chat_template call (calibration included) carries the deployed kwargs; meta records them
def test_f3_every_call_carries_the_deployed_kwargs(monkeypatch):
    deployed(monkeypatch, enable_thinking=True, reasoning_effort="medium", temperature=0.6, thinking_budget=81920)
    tok = Tok()
    count, _cpt, meta = M.offline_counter(tokenizer=tok)
    assert tok.calls and all(c == DEPLOYED_KW for c in tok.calls)
    assert count([{"role": "user", "content": "y" * 400}]) == 100 + 7 + 40 + 3
    assert meta["template_kwargs"] == DEPLOYED_KW


# class (a): kwargs that are not set are omitted (never sent as None)
def test_f3_unset_kwargs_are_omitted(monkeypatch):
    deployed(monkeypatch, enable_thinking=True, reasoning_effort=None)
    tok = Tok()
    _c, _p, meta = M.offline_counter(tokenizer=tok)
    assert all(c == {"enable_thinking": True} for c in tok.calls) and meta["template_kwargs"] == {"enable_thinking": True}


# class (a): the committed ids.json records the served template kwargs and passes the loader
def test_f3_committed_ids_records_the_kwargs_and_loads():
    doc = M.load(BENCH.parent)
    assert doc["axes"]["longctx"]["budget_inputs"]["counter"]["template_kwargs"] == DEPLOYED_KW


# class (a): the committed ids.json counts equal the prompt_tokens the harvested A5 legs SERVED (both arms, every committed item)
def test_f3_committed_counts_equal_the_served_prompt_tokens():
    lc = json.loads(REAL_IDS.read_text())["axes"]["longctx"]
    res = BENCH / "results" / ENTRY
    checked = 0
    for arm in PAIR:
        for blk in ("1", "2"):
            for iid in lc[f"block{blk}"]:
                task = next(i["task"] for i in lc["items"] if i["id"] == iid)
                f = res / f"{'retrieval' if task == 'retrieval' else 'reasoning'}.m76-{arm}-lc-b{blk}.{iid}.json"
                if not f.exists():
                    continue
                row = json.loads(f.read_text())["records"][0]["rows"][0]
                assert row["prompt_tokens"] == lc["budget"][iid]["prompt_tokens"], (arm, iid)
                checked += 1
    if not checked:
        pytest.skip("no harvested A5 result files in this checkout")
    assert checked == 144 or checked == 72 * 2, checked


# class (a): the ids.json diff is confined: items, seeds and block lists (everything but the budget-derived leaves) are what the generator
# derives from the plan — every kind other than longctx has no budget leaves at all and is untouched by the counter
def test_f3_ids_items_seeds_and_blocks_are_consistent():
    doc = json.loads(REAL_IDS.read_text())
    lc = doc["axes"]["longctx"]
    ids = {i["id"] for i in lc["items"]}
    for table in (lc["sampler_seeds"], lc["budget"]):                  # the items plus the smoke items, nothing else
        assert ids <= set(table) and {k for k in table if k not in ids} <= {"smoke-reasoning-131072", "smoke-retrieval-131072"}
    assert sorted(lc["block1"] + lc["block2"]) == sorted(lc["tier1"])
    for iid, b in lc["budget"].items():
        assert b["resolved_max_tokens"] == min(102400, 262144 - b["prompt_tokens"]), iid


# =================================================================================================== F4: the CLI uses the planned kinds
# class (a): `kinds` defaults to None (= the build's planned kinds) on both entry points
def test_f4_kinds_default_is_none_on_both_entry_points():
    for fn in (V.verify_all_kv, V.verify_wave1_kv):
        assert inspect.signature(fn).parameters["kinds"].default is None


# class (a): the CLI verifies the planned kinds only, with `dropped`, and never passes another set to the Wave 1 verifier
def test_f4_cli_emits_planned_kinds_and_passes_no_kinds(w, tmp_path, monkeypatch):
    seen = []
    real = V.verify_wave1_kv

    def spy(*a, **kw):
        seen.append(kw.get("kinds"))
        return real(*a, **kw)

    monkeypatch.setattr(V, "verify_wave1_kv", spy)
    out = tmp_path / "B8.json"
    rc = V.main(["all", "--lever", "kv", "--pair", "n16,x", "--results-root", str(w.rows / "m76"), "--rows-root", str(w.rows),
                 "--repo", str(w.repo), "--out", str(out)])
    assert rc == 0 and seen == [None]
    w1 = json.loads(out.read_text())["axes"]["wave1"]
    assert {p["kind"] for p in w1["pairs"]} == set(PLANNED) and w1["dropped"] == {"m1": M1_REASON}
    assert {"m1/b1", "m1/b2"} <= set(w1["not_run"])
    assert flags(S.compute_kv(w.rows, json.loads(out.read_text()))) == {}


# =================================================================================================== F5: one KV_W1_KINDS
# class (a): the tuple is defined once, in the plan; the verifier re-exports the same object; the planned kinds derive from it
def test_f5_one_definition_of_the_kinds():
    assert V.KV_W1_KINDS is P.KV_W1_KINDS
    assert P.KV_W1_KINDS == ("math500", "cjudge", "vision", "reasoning", "m1", "longctx")
    assert P.kv_w1_kinds("s3") == tuple(k for k in P.KV_W1_KINDS if k not in P.kv_w1_dropped("s3"))


# class (a): the plan module no longer needs the verifier to answer (no import of p426_verify inside kv_w1_kinds)
def test_f5_the_plan_does_not_import_the_verifier():
    assert "p426_verify" not in inspect.getsource(P.kv_w1_kinds) + inspect.getsource(P.kv_w1_dropped)
