"""M76 B8 kv — fix round 1 (spec `docs/specs/m76-b8-kv-planned-kinds.md` v1.1, C355 (2)(3), C356): F1 rule 2d compares
per-arm facts per arm; F2 `compute_kv` reads the record's completeness; F3 the A5 counter renders the served template; F4
`verify_all_kv` has no `kinds`; F5 one `KV_W1_KINDS`. On the REAL committed `benchmark/results/m76/ids.json`."""
from __future__ import annotations

import hashlib
import inspect
import json

import pytest

from bench import m76_ids as M
from bench import p426_plan as P
from bench import p426_signals as S
from bench import p426_verify as V
from bench.tests.test_m76_b3_impl_verify import ENTRY, REPO
from bench.tests.test_m76_b8_kinds_impl_planned import M1_REASON, PAIR, PLANNED, RealWorld

DEPLOYED_KW = {"enable_thinking": True, "reasoning_effort": "medium"}


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _pairs(rec):
    return {(p["kind"], p["block"]): p for p in rec["pairs"]}


@pytest.fixture
def real(tmp_path, monkeypatch):
    w = RealWorld(tmp_path, monkeypatch)
    monkeypatch.setattr("bench.generate.results_root", lambda: w.rows)    # a Path: A1 regrades Math500 through bench.grade
    from bench import grade

    for label in ("b1", "b2"):                     # each Math500 leg's score.json = its regrade (the signals refuse drift)
        for arm in PAIR:
            tune = V.kv_tune_of(arm, label, "math500")
            s = grade.grade("math500", ENTRY, tune=tune)
            (w.rows / ENTRY / f"math500.{tune}.score.json").write_text(
                json.dumps({f: s.get(f) for f in ("n", "errors", "correct", "acc_strict")}))
    return w


# ---------------------------------------------------------------------------------- F1: per-arm facts per arm (rule 2d)
def _vision_with(world, corpus):
    """Rewrite every vision leg with `runtime.corpus` = corpus(arm) and an equal content hash beside it."""
    orig = world.manifest

    def manifest(arm):
        m = orig(arm)
        m["runtime"] = dict(m["runtime"], corpus=corpus(arm), corpus_sha256="c" * 64)
        return m

    world.manifest = manifest
    for label in ("b1", "b2"):
        for arm in PAIR:
            world.leg("vision", arm, label)
    world.manifest = orig


def test_f1_arm_local_corpus_path_is_accepted(real):
    _vision_with(real, lambda arm: f"$STACK_WORKDIR/worktrees/m76-f45-{arm}/benchmark/data/vision_gate")
    got = _pairs(V.verify_wave1_kv(real.rows, real.repo, PAIR))
    for label in ("b1", "b2"):
        assert got[("vision", label)]["accepted"], got[("vision", label)]["reasons"]


def test_f1_arm_local_q_worktree_path_is_accepted(real):
    _vision_with(real, lambda arm: f"/w/m76-q-{arm}/benchmark/data/vision_gate")
    assert _pairs(V.verify_wave1_kv(real.rows, real.repo, PAIR))[("vision", "b1")]["accepted"]


def test_f1_a_corpus_path_naming_the_other_arm_is_rejected(real):
    _vision_with(real, lambda arm: "$STACK_WORKDIR/worktrees/m76-f45-n16/benchmark/data/vision_gate")
    p = _pairs(V.verify_wave1_kv(real.rows, real.repo, PAIR))[("vision", "b1")]
    assert not p["accepted"]
    assert any("rule 2d" in r and "x" in r and "another arm" in r for r in p["reasons"]), p["reasons"]


def test_f1_a_content_hash_beside_the_path_stays_compared(real):
    orig = real.manifest

    def manifest(arm):
        m = orig(arm)
        m["runtime"] = dict(m["runtime"], corpus=f"/w/m76-f45-{arm}/d", corpus_sha256=("c" if arm == "n16" else "d") * 64)
        return m

    real.manifest = manifest
    for arm in PAIR:
        real.leg("vision", arm, "b2")
    real.manifest = orig
    p = _pairs(V.verify_wave1_kv(real.rows, real.repo, PAIR))[("vision", "b2")]
    assert not p["accepted"] and any("corpus_sha256" in r for r in p["reasons"]), p["reasons"]


def _stamp_results(world, kind, label, arm):
    """The runners' integrity stamps: each manifest's result_file / result_sha256 describe its result file's bytes."""
    edir = world.rows / ENTRY
    tune = V.kv_tune_of(arm, label, kind)
    if kind == "reasoning":
        stems = [f"reasoning.{tune}"]
    else:
        items = {i["id"]: i for i in world.ids["axes"]["longctx"]["items"]}
        stems = [f"{'retrieval' if items[i]['task'] == 'retrieval' else 'reasoning'}.{tune}.{i}"
                 for i in world.ids["axes"]["longctx"][f"block{label[-1]}"]]
    for stem in stems:
        res, mp = edir / f"{stem}.json", edir / f"{stem}.manifest.json"
        man = json.loads(mp.read_text())
        man.update(result_file=res.name, result_sha256=_sha(res.read_bytes()))
        mp.write_text(json.dumps(man))
    return stems


@pytest.fixture
def stamped(real):
    for kind in ("reasoning", "longctx"):
        for label in ("b1", "b2"):
            for arm in PAIR:
                _stamp_results(real, kind, label, arm)
    return real


def test_f1_per_arm_result_file_and_sha_are_accepted(stamped):
    got = _pairs(V.verify_wave1_kv(stamped.rows, stamped.repo, PAIR))
    for kind in ("reasoning", "longctx"):
        for label in ("b1", "b2"):
            assert got[(kind, label)]["accepted"], (kind, label, got[(kind, label)]["reasons"][:3])


@pytest.mark.parametrize("kind", ["reasoning", "longctx"])
def test_f1_one_arms_altered_result_bytes_reject_naming_that_arm(stamped, kind):
    stem = _stamp_results(stamped, kind, "b1", "x")[0]
    res = stamped.rows / ENTRY / f"{stem}.json"
    res.write_bytes(res.read_bytes() + b" ")                 # still parseable; its recorded sha no longer describes it
    got = _pairs(V.verify_wave1_kv(stamped.rows, stamped.repo, PAIR))
    p = got[(kind, "b1")]
    assert not p["accepted"]
    bad = [r for r in p["reasons"] if "result_sha256" in r]
    assert bad and all("rule 2d" in r and " x " in f" {r} " for r in bad), p["reasons"]
    assert not any("n16" in r.split("result_sha256")[0].split(":")[-1] for r in bad)
    assert got[(kind, "b2")]["accepted"]


def test_f1_a_result_file_naming_another_file_is_rejected(stamped):
    mp = stamped.rows / ENTRY / f"reasoning.{V.kv_tune_of('n16', 'b2', 'reasoning')}.manifest.json"
    man = json.loads(mp.read_text())
    man["result_file"] = "reasoning.other.json"
    mp.write_text(json.dumps(man))
    p = _pairs(V.verify_wave1_kv(stamped.rows, stamped.repo, PAIR))[("reasoning", "b2")]
    assert not p["accepted"] and any("result_file" in r and "n16" in r for r in p["reasons"]), p["reasons"]


def test_f1_a_stamp_absent_on_one_arm_is_rejected_naming_it(stamped):
    mp = stamped.rows / ENTRY / f"reasoning.{V.kv_tune_of('x', 'b1', 'reasoning')}.manifest.json"
    man = json.loads(mp.read_text())
    del man["result_sha256"]
    mp.write_text(json.dumps(man))
    p = _pairs(V.verify_wave1_kv(stamped.rows, stamped.repo, PAIR))[("reasoning", "b1")]
    assert not p["accepted"] and any("result_sha256" in r and "x" in r for r in p["reasons"]), p["reasons"]


@pytest.mark.parametrize("kind", ["reasoning", "longctx"])
def test_r1_both_arms_stripped_of_their_stamps_are_rejected(stamped, kind):
    """Round 2 (R1): A4 / A5 manifests always carry both stamps; stripping both arms never silences the integrity check."""
    for arm in PAIR:
        for stem in _stamp_results(stamped, kind, "b2", arm):
            mp = stamped.rows / ENTRY / f"{stem}.manifest.json"
            man = json.loads(mp.read_text())
            for k in ("result_file", "result_sha256"):
                man.pop(k)
            mp.write_text(json.dumps(man))
    got = _pairs(V.verify_wave1_kv(stamped.rows, stamped.repo, PAIR))
    p = got[(kind, "b2")]
    assert not p["accepted"]
    for arm in PAIR:
        for k in ("result_file", "result_sha256"):
            assert any("rule 2d" in r and f" {arm} " in f" {r} " and k in r for r in p["reasons"]), (arm, k, p["reasons"][:4])
    assert got[(kind, "b1")]["accepted"]


def test_r1_unstamped_kinds_stay_unstamped(real):
    """Math500 / cjudge / vision runners write no stamps: unstamped manifests of those kinds stay accepted."""
    got = _pairs(V.verify_wave1_kv(real.rows, real.repo, PAIR, kinds=("math500", "cjudge", "vision")))
    assert all(p["accepted"] for p in got.values()), [(k, p["reasons"][:2]) for k, p in got.items() if not p["accepted"]]


# ------------------------------------------------------------------------------------- F2: compute_kv reads completeness
def _flags(sig, name="wave1_incomplete"):
    return {f["member"]: f for f in sig["flags"] if f["flag"] == name}


def test_f2_a_complete_record_raises_no_wave1_incomplete_and_m1_is_not_run(stamped):
    b8 = V.verify_all_kv(stamped.rows, stamped.repo, PAIR)
    sig = S.compute_kv(stamped.rows, b8)
    assert _flags(sig) == {}
    m1 = sig["axes"]["M1"]["blocks"]
    assert m1 == {"b1": {"status": "not_run", "ruling": M1_REASON}, "b2": {"status": "not_run", "ruling": M1_REASON}}
    assert not any(f["member"].startswith(("math500/t2", "longctx/t2")) for f in sig["flags"])


def test_f2_a_rejected_planned_pair_is_a_blocking_wave1_incomplete(stamped):
    argv = stamped.argv("x")
    argv[argv.index("--prefill-step-size") + 1] = "2048"
    stamped.leg("cjudge", "x", "b2", argv=argv)
    b8 = V.verify_all_kv(stamped.rows, stamped.repo, PAIR)
    assert not _pairs(b8["axes"]["wave1"])[("cjudge", "b2")]["accepted"]
    flags = _flags(S.compute_kv(stamped.rows, b8))
    assert set(flags) == {"cjudge/b2"}
    f = flags["cjudge/b2"]
    assert f["blocking"] is True and "rule 2c" in f["text"]


def test_f2_an_absent_planned_pair_is_a_blocking_wave1_incomplete(stamped):
    b8 = V.verify_all_kv(stamped.rows, stamped.repo, PAIR)
    b8["axes"]["wave1"]["pairs"] = [p for p in b8["axes"]["wave1"]["pairs"] if (p["kind"], p["block"]) != ("vision", "b1")]
    flags = _flags(S.compute_kv(stamped.rows, b8))
    assert set(flags) == {"vision/b1"} and flags["vision/b1"]["blocking"] is True


def test_f2_the_candidate_1_shape_six_rejected_pairs_flag_each(real):
    """The harvest's shape before F1 (unstamped arm-local paths): every rejected planned pair is flagged, one per pair."""
    _vision_with(real, lambda arm: "$STACK_WORKDIR/worktrees/m76-f45-n16/d")
    b8 = V.verify_all_kv(real.rows, real.repo, PAIR)
    flags = _flags(S.compute_kv(real.rows, b8))
    assert {"vision/b1", "vision/b2"} <= set(flags)
    assert all(f["blocking"] for f in flags.values())


# ----------------------------------------------------------------------------------- F3: the counter renders the template
class FakeTok:
    """Renders `reasoning_effort` into the prompt (so a counter without the deployed kwargs counts fewer tokens)."""
    chat_template = "{{ fake }}"

    def __init__(self):
        self.calls = []

    def apply_chat_template(self, messages, add_generation_prompt=False, tokenize=False, **kw):
        self.calls.append(dict(kw))
        text = "".join(m["content"] for m in messages)
        extra = 40 if kw.get("reasoning_effort") else 0
        return list(range(len(text) // 4 + 7 + extra + (3 if kw.get("enable_thinking") else 0)))


def _params(monkeypatch, **p):
    from bench import model_params

    monkeypatch.setattr(model_params, "params_for", lambda entry, profile=None: dict(p) if profile == "deployed" else {})


def test_f3_the_counter_passes_the_deployed_template_kwargs_to_every_call(monkeypatch):
    _params(monkeypatch, enable_thinking=True, reasoning_effort="medium", thinking_budget=81920, temperature=0.6)
    tok = FakeTok()
    count, cpt, meta = M.offline_counter(tokenizer=tok)
    assert tok.calls and all(c == DEPLOYED_KW for c in tok.calls)          # calibration included
    n = count([{"role": "user", "content": "x" * 400}])
    assert n == 100 + 7 + 40 + 3 and tok.calls[-1] == DEPLOYED_KW
    assert meta["template_kwargs"] == DEPLOYED_KW


def test_f3_unset_kwargs_are_omitted(monkeypatch):
    _params(monkeypatch, enable_thinking=None, reasoning_effort=None)
    tok = FakeTok()
    _count, _cpt, meta = M.offline_counter(tokenizer=tok)
    assert all(c == {} for c in tok.calls) and meta["template_kwargs"] == {}


def test_f3_the_committed_ids_records_the_served_template_and_loads():
    doc = M.load(REPO)
    counter = doc["axes"]["longctx"]["budget_inputs"]["counter"]
    assert counter["template_kwargs"] == DEPLOYED_KW


# ------------------------------------------------------------------------------------------ F4 / F5: the B8 entry point
def test_f4_verify_all_kv_default_is_the_planned_kinds(real):
    """Erratum v1.1a: `kinds=None` = the build's planned kinds (+ `dropped`)."""
    assert inspect.signature(V.verify_all_kv).parameters["kinds"].default is None
    w1 = V.verify_all_kv(real.rows, real.repo, PAIR)["axes"]["wave1"]
    assert {p["kind"] for p in w1["pairs"]} == set(PLANNED) and w1["dropped"] == {"m1": M1_REASON}


def test_f4_the_cli_verifies_the_planned_kinds(real, tmp_path, monkeypatch):
    seen = []
    real_fn = V.verify_wave1_kv

    def spy(*a, **kw):
        seen.append(kw.get("kinds"))
        return real_fn(*a, **kw)

    monkeypatch.setattr(V, "verify_wave1_kv", spy)
    out = tmp_path / "B8.json"
    rc = V.main(["all", "--lever", "kv", "--pair", "n16,x", "--results-root", str(real.rows / "m76"),
                 "--rows-root", str(real.rows), "--repo", str(real.repo), "--out", str(out)])
    assert rc == 0 and seen == [None]
    w1 = json.loads(out.read_text())["axes"]["wave1"]
    assert {p["kind"] for p in w1["pairs"]} == set(PLANNED) and w1["dropped"] == {"m1": M1_REASON}


def test_f4_a_subset_record_records_dropped_and_is_flagged_by_compute_kv(stamped):
    """K2 closed at the consumer: a subset B8 record reads incomplete (every absent planned pair blocks)."""
    b8 = V.verify_all_kv(stamped.rows, stamped.repo, PAIR, kinds=("cjudge",))
    assert {p["kind"] for p in b8["axes"]["wave1"]["pairs"]} == {"cjudge"}
    assert b8["axes"]["wave1"]["dropped"] == {"m1": M1_REASON}
    flags = _flags(S.compute_kv(stamped.rows, b8))
    assert set(flags) == {f"{k}/{b}" for k in PLANNED if k != "cjudge" for b in ("b1", "b2")}
    assert all(f["blocking"] for f in flags.values())


def test_f4_an_empty_subset_never_reads_clean(stamped):
    b8 = V.verify_all_kv(stamped.rows, stamped.repo, PAIR, kinds=())
    assert b8["axes"]["wave1"]["pairs"] == []
    assert len(_flags(S.compute_kv(stamped.rows, b8))) == 10


def test_f5_one_definition_of_the_kinds():
    assert P.KV_W1_KINDS == ("math500", "cjudge", "vision", "reasoning", "m1", "longctx")
    assert V.KV_W1_KINDS is P.KV_W1_KINDS
    assert "p426_verify" not in inspect.getsource(P.kv_w1_kinds)
    assert P.kv_w1_kinds("s3") == PLANNED
