"""M76 B8 kv planned Wave 1 kinds (spec `docs/specs/m76-b8-kv-planned-kinds.md` v1, C354): behaviour tests for acceptance 1 and
every interface the spec names, on the REAL committed `benchmark/results/m76/ids.json` (copied byte for byte into the synthetic
rows root, never mocked) and a synthetic harvested stage-3a (build s3) Wave 1 tree of the real record shapes B8 reads: every
planned leg (math500, cjudge, vision, reasoning, longctx at tier 1, both arms), no M1 leg.

Class of every test (stated above it):
  (a) acceptance: fails on the baseline, passes once the spec is implemented (the red-first set);
  (b) preserved behaviour: passes on the baseline and must keep passing (mtp golden, refusals, unknown kinds, shapes);
  (c) interpretation of an under-specified point: a reading of the spec, flagged so a reviewer can overrule it.

The mtp golden is `fixtures/m76_b8_kinds_fe/mtp_b8_golden.json` (sha256 of `p426_verify.dumps` of `verify_all` on the committed
p426 data, plus counts), computed on the baseline; regenerate only on purpose by creating the empty file `WRITE_GOLDEN` beside it.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from bench import p426_plan as P
from bench import p426_verify as V

BENCH = Path(__file__).resolve().parents[2]
REPO = BENCH.parent
REAL_IDS = BENCH / "results" / "m76" / "ids.json"
FIX = Path(__file__).resolve().parent / "fixtures"
GOLDEN = FIX / "m76_b8_kinds_fe" / "mtp_b8_golden.json"
REGISTRIES = FIX / "m76_b3_fe"
ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
ENGAGED = dict(draft_kind="mtp", draft_rounds=5, draft_n=10, draft_n_accepted=7)
PLANNED = ("math500", "cjudge", "vision", "reasoning", "longctx")
M1_REASON = "C352: M1 dropped from stage 3a (stage 1's matrix certifies memory)"
T2_NOT_RUN = {f"{k}/{t}" for k in ("math500", "longctx") for t in ("t2-b1", "t2-b2")}
GIT_ENV = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=GIT_ENV).stdout.strip()


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


class World:
    """A git repo with the REAL N16 / X registries at two commits, the real `m76/ids.json`, the frozen s3 record and the legs."""

    def __init__(self, tmp, monkeypatch, kinds=PLANNED):
        self.repo, self.rows = tmp / "repo", tmp / "results"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        self.text, self.head = {}, {}
        for arm in ("n16", "x"):
            self.text[arm] = (REGISTRIES / f"{arm}_main_models.yaml").read_bytes()
            (self.repo / "main_models.yaml").write_bytes(self.text[arm])
            git(self.repo, "add", "main_models.yaml")
            git(self.repo, "commit", "-q", "-m", arm)
            self.head[arm] = git(self.repo, "rev-parse", "HEAD")
        monkeypatch.setattr("bench.generate.results_root", lambda: str(self.rows))
        (self.rows / "m76").mkdir(parents=True)
        shutil.copyfile(REAL_IDS, self.rows / "m76" / "ids.json")         # the REAL committed ids, byte for byte
        self.ids = json.loads(REAL_IDS.read_text())
        self.axes = self.ids["axes"]
        venvs = {v: {p: "0.32.4" if p in ("mlx", "mlx-metal") else "1" for p in P.VENV_PACKAGES} for v in P.VENVS}
        self.frozen = dict(build="s3", lever="kv", arms=["n16", "x"], uv_lock_sha256="a" * 64, bench_lock_sha256="b" * 64,
                           venvs={a: venvs for a in ("n16", "x")},
                           **{k: P.EXPECTED_BUILDS["s3"][k] for k in ("mlx_vlm", "mlx_serve", "production_ref")},
                           **{f"stack_head_{a}": self.head[a] for a in ("n16", "x")},
                           **{f"stack_clean_{a}": True for a in ("n16", "x")},
                           **{f"registry_{a}_sha": sha(self.text[a]) for a in ("n16", "x")})
        fb = json.dumps(self.frozen).encode()
        self._write(self.rows / "m76" / "wave1" / "run" / "frozen.s3.json", fb)
        self.frozen_sha = sha(fb)
        for kind in kinds:
            self.leg_pair(kind)

    def _write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())

    def argv(self, arm):
        from bench.tests.test_m76_b3_impl_lever import worker_argv

        return worker_argv(arm, wt=f"$STACK_WORKDIR/worktrees/m76-f45-{arm}")

    def manifest(self, arm):
        return dict(model=ENTRY, box="box-1", fingerprint_version=9, sampling_profile="deployed", timestamp=100 + len(arm),
                    tune=f"m76-{arm}-b1", sampling=dict(temperature=0.5, top_p=0.95, max_tokens=102400, thinking_budget=81920),
                    registry=dict(sha256=sha(self.text[arm])), router=dict(pid=1000 + len(arm), config=f"/wt/{arm}"),
                    git=dict(stack_head=self.head[arm], submodules={"src/mlx-vlm": "v" * 40},
                             serving_path={"src/mlx-vlm": "t" * 40, "src/mlx-serve": "u" * 40}),
                    quant=dict(effective_bits=4.5),
                    runtime=dict(apc_enabled=False, draft_kind="mtp", mtp_verify_scan="joint_v1",
                                 tq4_attention="off" if arm == "n16" else "m72_exact", session_retain_prompt_end=True),
                    kv=dict(kv_bits=0 if arm == "n16" else 4, kv_quant_scheme="uniform" if arm == "n16" else "turboquant",
                            max_kv_cache_size=262144, prefill_step_size=4096, hf_path="caslca/x"))

    def leg_pair(self, kind, labels=("b1", "b2")):
        for label in labels:
            for arm in ("n16", "x"):
                self.leg(kind, arm, label)

    def drop_leg(self, kind, arm, label):
        shutil.rmtree(self.rows / "m76" / "wave1" / V.kv_leg_of(kind, arm, label))

    @staticmethod
    def _stamped(man, name, res):
        """Designer merge amendment (B8 R1): stamp a reasoning / A5 manifest with its result file's name and sha256."""
        return json.dumps(dict(json.loads(man), result_file=name, result_sha256=sha(res.encode())))

    def leg(self, kind, arm, label):
        leg, tune = V.kv_leg_of(kind, arm, label), V.kv_tune_of(arm, label, kind)
        receipt = dict(verdict="VALID", problems=[], name=leg, arm=arm, kind="qualify" if kind == "m1" else kind, speed_valid=True,
                       speed_problems=[], pins=dict(self.frozen, frozen_sha=self.frozen_sha),
                       state=dict(stack_head=self.head[arm], frozen_sha=self.frozen_sha),
                       worker=dict(cmdline="202 " + " ".join(self.argv(arm)).replace('", "', '","')), log={})
        ldir = self.rows / "m76" / "wave1" / leg
        self._write(ldir / f"{leg}.receipt.json", json.dumps(receipt))
        self._write(ldir / "SCRUB_MANIFEST.json", json.dumps(dict(leg=leg, files={})))
        edir = self.rows / ENTRY
        man = json.dumps(self.manifest(arm))
        if kind == "m1":          # a qualify leg: no items, no ids axis
            mdir = ldir / "m1"
            self._write(mdir / ENTRY / "result.json", json.dumps(dict(
                status="ok", served=dict(draft_kind="mtp", kv_bits=0 if arm == "n16" else 4), snapshots={"--draft-model": "d"},
                requests=[dict(qualify=dict(generate_seed=5, prompt=dict(sized=1000)))])))
            self._write(mdir / ENTRY / "job.json", json.dumps(dict(argv=self.argv(arm))))
            self._write(mdir / "report.json", json.dumps(dict(registry_sha256=sha(self.text[arm]), reviewed_head="h",
                                                              production="p", versions={})))
        elif kind == "longctx":
            lc = self.axes["longctx"]
            by = {i["id"]: i for i in lc["items"]}
            for iid in lc[f"block{label[-1]}"]:
                item = by[iid]
                row = dict(trial=0, seed=item["task_seed"], sampler_seed=lc["sampler_seeds"][iid], content=f"codes {iid}",
                           prompt_tokens=lc["budget"][iid]["prompt_tokens"], finish_reason="stop", draft=ENGAGED,
                           completion_tokens=100, hits=[True] * 5, score=1.0, budget_hit=False)
                stem = f"{'retrieval' if item['task'] == 'retrieval' else 'reasoning'}.{tune}.{iid}"
                res = json.dumps(dict(records=[dict(ctx=item["rung"], rows=[row])]))
                self._write(edir / f"{stem}.json", res)
                self._write(edir / f"{stem}.manifest.json", self._stamped(man, f"{stem}.json", res))      # as the runners (B8 R1)
        elif kind == "reasoning":
            ax = self.axes["reasoning"]
            rows = [dict(seed=x, sampler_seed=ax["request_seeds"][str(x)], content=f"answer {x}", draft=ENGAGED, score=1.0,
                         budget_hit=False, finish_reason="stop") for x in ax[f"block{label[-1]}"]]
            res = json.dumps(dict(params=dict(thinking_budget=81920), records=[dict(rows=rows)]))
            self._write(edir / V.W1_ROWS[kind].format(tune=tune), res)
            self._write(edir / V.W1_MANIFEST[kind].format(tune=tune),
                        self._stamped(man, V.W1_ROWS[kind].format(tune=tune).split("/")[-1], res))      # as run_reasoning (B8 R1)
        else:
            rows = []
            for i in self.axes[kind][f"block{label[-1]}"]:
                if kind == "vision":
                    rows.append(dict(id=i, seed=5, description=f"desc {i}", draft=ENGAGED, turn2=dict(draft=ENGAGED), verdict="PASS"))
                else:
                    content = f"answer {i}"
                    rows.append(dict(id=i, sampler_seed=7, content=content, content_sha256=sha(content), thinking_budget=81920,
                                     draft=ENGAGED, decode_tps=30.0 if arm == "n16" else 25.0))
            self._write(edir / V.W1_ROWS[kind].format(tune=tune), "".join(json.dumps(r) + "\n" for r in rows))
            self._write(edir / V.W1_MANIFEST[kind].format(tune=tune), man)
            if kind == "math500":
                self._write(edir / f"math500.{tune}.score.json", json.dumps(dict(correct=len(rows))))
        return leg

    def all_kv(self, **kw):
        return V.verify_all_kv(self.rows, self.repo, ("n16", "x"), **kw)

    def wave1(self, **kw):
        return V.verify_wave1_kv(self.rows, self.repo, ("n16", "x"), **kw)


@pytest.fixture
def world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)


def by_key(rec):
    return {(p["kind"], p["block"]): p for p in rec["pairs"]}


# ------------------------------------------------------------------------------------------------ preconditions (the real ids)
# class (b): the committed ids.json is what the spec says it is — no m1 axis, every planned kind has items, the synthetic tree copies it
def test_real_ids_has_items_for_planned_kinds_and_none_for_m1(world):
    assert "m1" not in world.axes
    for kind in PLANNED:
        assert world.axes[kind]["block1"] and world.axes[kind]["block2"], kind
    assert (world.rows / "m76" / "ids.json").read_bytes() == REAL_IDS.read_bytes()


# class (b): the synthetic planned-kinds tree is itself valid: every planned pair verifies when asked for exactly those kinds
# (passes on the baseline: the fixture is sound and only the default kinds / m1 handling is wrong)
def test_fixture_tree_verifies_with_explicit_planned_kinds(world):
    rec = world.wave1(kinds=PLANNED)
    got = by_key(rec)
    assert set(got) == {(k, b) for k in PLANNED for b in ("b1", "b2")}
    for p in got.values():
        assert p["accepted"], (p["kind"], p["block"], p["reasons"])
        assert not p["keys_rejected"]
    assert set(rec["not_run"]) == T2_NOT_RUN


# ------------------------------------------------------------------------------------------------ p426_plan interfaces
# class (a): kv_w1_kinds("s3") is the five planned kinds, in the Wave 1 order
def test_kv_w1_kinds_s3():
    assert tuple(P.kv_w1_kinds("s3")) == PLANNED


# class (a): kv_w1_dropped("s3") names M1 with its ruling, nothing else
def test_kv_w1_dropped_s3():
    assert P.kv_w1_dropped("s3") == {"m1": M1_REASON}


# class (a): the planned and dropped kinds partition KV_W1_KINDS
def test_kv_w1_kinds_and_dropped_partition_the_kv_kinds():
    assert sorted(set(P.kv_w1_kinds("s3")) | set(P.kv_w1_dropped("s3"))) == sorted(V.KV_W1_KINDS)
    assert not set(P.kv_w1_kinds("s3")) & set(P.kv_w1_dropped("s3"))


# class (a): kv_w1_kinds returns a tuple (spec: `-> tuple`)
def test_kv_w1_kinds_is_a_tuple():
    assert isinstance(P.kv_w1_kinds("s3"), tuple)


# class (a): an unknown build refuses (ValueError as every p426_plan build check, or the verifier's RefusalError)
@pytest.mark.parametrize("fn", ["kv_w1_kinds", "kv_w1_dropped"])
def test_unknown_build_refuses(fn):
    with pytest.raises((ValueError, V.RefusalError)):
        getattr(P, fn)("s9")


# ------------------------------------------------------------------------------------------------ acceptance 1: verify_all_kv
# class (a): the default kinds verify a harvested s3 tree with every planned leg and no m1 leg: five planned kinds x b1,b2, accepted
def test_default_kinds_verify_the_planned_wave1(world):
    w1 = world.all_kv()["axes"]["wave1"]
    got = by_key(w1)
    assert set(got) == {(k, b) for k in PLANNED for b in ("b1", "b2")}
    for p in got.values():
        assert p["accepted"], (p["kind"], p["block"], p["reasons"])
    assert not [p for p in w1["pairs"] if p["kind"] == "m1"]


# class (a): m1/b1, m1/b2 are recorded not_run, with the existing tier-2 not_run entries kept, nothing else
def test_unplanned_m1_blocks_are_not_run(world):
    w1 = world.all_kv()["axes"]["wave1"]
    assert set(w1["not_run"]) == T2_NOT_RUN | {"m1/b1", "m1/b2"}
    assert len(w1["not_run"]) == len(set(w1["not_run"]))                     # no duplicates
    assert not any(n.startswith("m1/t2") for n in w1["not_run"])             # m1 has no tier 2


# class (a): wave1.dropped = {kind: reason}
def test_dropped_records_m1_with_its_ruling(world):
    assert world.all_kv()["axes"]["wave1"]["dropped"] == {"m1": M1_REASON}


# class (a): the record still has the shape the signals read (axes.wave1, lever, pair, label, inputs) — and ids.json is among the inputs
def test_record_shape_is_kept(world):
    b8 = world.all_kv()
    assert b8["lever"] == "kv" and b8["pair"] == ["n16", "x"] and b8["label"] == "X − N16" and set(b8["axes"]) == {"wave1"}
    w1 = b8["axes"]["wave1"]
    assert w1["axis"] == "wave1" and w1["lever"] == "kv" and w1["pair"] == ["n16", "x"]
    assert any(k.endswith("ids.json") for k in w1["inputs"])
    assert not any("/m1/" in k or k.startswith("m1") for k in w1["inputs"])      # no m1 leg evidence was read


# class (a): the kinds default is the build's planned kinds, whether spelled None or left out; an explicit equal tuple gives the same
def test_kinds_none_equals_default_equals_planned(world):
    a = world.all_kv()
    b = world.all_kv(kinds=None)
    c = world.all_kv(kinds=P.kv_w1_kinds("s3"))
    assert V.dumps(a) == V.dumps(b)
    assert by_key(a["axes"]["wave1"]).keys() == by_key(c["axes"]["wave1"]).keys()


# class (a): `build="s3"` is accepted as a keyword (the new signature)
def test_build_keyword_is_accepted(world):
    assert world.all_kv(build="s3")["axes"]["wave1"]["dropped"] == {"m1": M1_REASON}


# class (a): the record verifies end to end through the public CLI (default kinds, no m1 legs) and writes B8 json with dropped / not_run
def test_cli_emits_the_record(world, tmp_path):
    out = tmp_path / "B8.json"
    rc = V.main(["all", "--results-root", str(world.rows / "m76"), "--rows-root", str(world.rows), "--repo", str(world.repo),
                 "--out", str(out), "--lever", "kv", "--pair", "n16,x"])
    assert rc == 0
    w1 = json.loads(out.read_text())["axes"]["wave1"]
    assert w1["dropped"] == {"m1": M1_REASON} and {"m1/b1", "m1/b2"} <= set(w1["not_run"])
    assert all(p["accepted"] for p in w1["pairs"])


# ------------------------------------------------------------------------------------------------ acceptance 1: verify_wave1_kv
# class (a): verify_wave1_kv with its default kinds no longer raises KeyError on the real ids; it verifies the planned kinds only
def test_wave1_default_kinds_do_not_index_ids_for_m1(world):
    rec = world.wave1()
    assert {p["kind"] for p in rec["pairs"]} == set(PLANNED)
    assert all(p["accepted"] for p in rec["pairs"])


# class (a): verify_wave1_kv records the unplanned m1 blocks as not_run itself too (verify_all_kv only adds `dropped`'s transport)
# [class (c) on WHERE the not_run entry is produced: the spec places it in the record `wave1`; verify_wave1_kv IS that record]
def test_wave1_record_lists_m1_not_run(world):
    rec = world.wave1()
    assert {"m1/b1", "m1/b2"} <= set(rec["not_run"])


# class (a): a missing leg of a planned kind still refuses — cjudge b2 of the arm X; the refusal names the leg
def test_missing_planned_leg_refuses(world):
    world.drop_leg("cjudge", "x", "b2")
    with pytest.raises(V.RefusalError) as exc:
        world.all_kv()
    assert "cjudge" in str(exc.value) and "missing" in str(exc.value)


# class (a): the same through the public CLI: exit 2 (REFUSED), nothing written
def test_missing_planned_leg_refuses_through_the_cli(world, tmp_path, capsys):
    world.drop_leg("cjudge", "x", "b2")
    out = tmp_path / "B8.json"
    rc = V.main(["all", "--results-root", str(world.rows / "m76"), "--rows-root", str(world.rows), "--repo", str(world.repo),
                 "--out", str(out), "--lever", "kv", "--pair", "n16,x"])
    assert rc == 2 and not out.exists()
    assert "REFUSED" in capsys.readouterr().err


# class (a): every planned kind's missing leg refuses (either arm, either block, each kind) — never a verdict on incomplete evidence
@pytest.mark.parametrize("kind", PLANNED)
@pytest.mark.parametrize("arm,label", [("n16", "b1"), ("x", "b2")])
def test_each_planned_kind_refuses_on_a_missing_leg(tmp_path, monkeypatch, kind, arm, label):
    w = World(tmp_path, monkeypatch)
    w.drop_leg(kind, arm, label)
    with pytest.raises(V.RefusalError) as exc:
        w.all_kv()
    assert kind in str(exc.value)


# class (a): an unplanned kind's leg that is absent never refuses (it is not_run), whichever arm lacks it — m1 legs from ONE arm only
# are ignored under the default kinds (the planned kinds decide)
def test_a_lone_unplanned_m1_leg_does_not_refuse_the_default(world):
    world.leg("m1", "n16", "b1")
    w1 = world.all_kv()["axes"]["wave1"]
    assert {"m1/b1", "m1/b2"} <= set(w1["not_run"]) and not [p for p in w1["pairs"] if p["kind"] == "m1"]


# class (c): m1 legs that ARE present are still not_run under the default (the stage planned five kinds; the dropped kind is
# recorded as not_run with its ruling, never verified) — the spec: "verifies exactly the kinds the stage planned, records every
# unplanned kind as not_run"
def test_present_m1_legs_stay_not_run_under_the_default(world):
    world.leg_pair("m1")
    w1 = world.all_kv()["axes"]["wave1"]
    assert not [p for p in w1["pairs"] if p["kind"] == "m1"]
    assert {"m1/b1", "m1/b2"} <= set(w1["not_run"]) and w1["dropped"] == {"m1": M1_REASON}


# class (a): an explicit `kinds=` including m1 with the m1 legs present verifies them — without indexing ids for m1
def test_explicit_kinds_including_m1_verify_the_m1_legs(world):
    world.leg_pair("m1")
    rec = world.all_kv(kinds=("cjudge", "m1"))["axes"]["wave1"]
    got = by_key(rec)
    assert set(got) == {("cjudge", "b1"), ("cjudge", "b2"), ("m1", "b1"), ("m1", "b2")}
    for p in got.values():
        assert p["accepted"], (p["kind"], p["block"], p["reasons"])
    m1 = got[("m1", "b1")]
    assert m1["axis"] == "M1" and m1["identity_basis"] == "none" and m1["identical"] == dict(n=0, of=0)
    assert m1["legs"] == {"n16": V.kv_leg_of("m1", "n16", "b1"), "x": V.kv_leg_of("m1", "x", "b1")}
    assert "m1/b1" not in rec["not_run"] and "m1/b2" not in rec["not_run"]


# class (b): fixture soundness for the m1 legs, independent of the fix: with the ids index patched to carry an empty m1 entry (the
# baseline's only obstacle), the synthetic m1 legs verify — so the (a) tests above fail only on the behaviour under test
def test_m1_fixture_legs_are_sound_on_their_own(world, monkeypatch):
    world.leg_pair("m1")
    real = V.load_kv_ids

    def with_m1(reader):
        return dict(real(reader), m1={"b1": [], "b2": []})
    monkeypatch.setattr(V, "load_kv_ids", with_m1)
    got = by_key(world.wave1(kinds=("m1",)))
    assert set(got) == {("m1", "b1"), ("m1", "b2")} and all(p["accepted"] for p in got.values()), [p["reasons"] for p in got.values()]


# class (a): the explicit kinds with m1 only (no item kind at all) verify from the leg evidence alone
def test_explicit_m1_only_verifies_from_leg_evidence(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch, kinds=("m1",))
    rec = w.wave1(kinds=("m1",))
    assert [(p["kind"], p["block"], p["accepted"]) for p in rec["pairs"]] == [("m1", "b1", True), ("m1", "b2", True)]
    assert rec["not_run"] == []


# class (a): an explicit kinds including m1 with an m1 leg MISSING still refuses (a missing leg of a planned kind), not KeyError
def test_explicit_m1_with_a_missing_m1_leg_refuses(world):
    world.leg("m1", "n16", "b1")
    world.leg("m1", "x", "b1")
    world.leg("m1", "n16", "b2")              # x b2 absent
    with pytest.raises(V.RefusalError) as exc:
        world.all_kv(kinds=("cjudge", "m1"))
    assert "m1" in str(exc.value) and "missing" in str(exc.value)


# class (a): an explicit kinds with m1 and no m1 legs refuses with a RefusalError (not KeyError)
def test_explicit_m1_without_legs_refuses_not_keyerror(world):
    with pytest.raises(V.RefusalError):
        world.wave1(kinds=("m1",))


# class (a): an m1 leg that is invalid still rejects its pair when verified explicitly (the m1 rules are untouched)
def test_explicit_m1_with_a_bad_receipt_is_rejected(world):
    world.leg_pair("m1")
    rp = world.rows / "m76" / "wave1" / V.kv_leg_of("m1", "x", "b1") / f"{V.kv_leg_of('m1', 'x', 'b1')}.receipt.json"
    rec = json.loads(rp.read_text())
    rec["verdict"] = "INVALID"
    rp.write_text(json.dumps(rec))
    got = by_key(world.wave1(kinds=("m1",)))
    assert not got[("m1", "b1")]["accepted"] and any("rule 1" in r for r in got[("m1", "b1")]["reasons"])
    assert got[("m1", "b2")]["accepted"]


# ------------------------------------------------------------------------------------------------ unchanged B8 behaviour
# class (b): an unknown explicit kind refuses as before
def test_unknown_explicit_kind_refuses(world):
    with pytest.raises(V.RefusalError, match="unknown Wave 1 kind"):
        world.wave1(kinds=("nonsense",))


# class (b): the tier-2 legs of math500 / longctx are not_run when neither arm has them, and verified as their own pairs when both do
# (the real ids hold both tier 2s)
def test_tier2_not_run_unchanged_and_verified_when_present(world):
    assert set(world.wave1(kinds=("math500", "longctx"))["not_run"]) == T2_NOT_RUN
    t2 = world.axes["math500"]["tier2"]
    assert t2["block1"] and t2["block2"]


# class (b): a rejected pair is not a refusal — a draft state that is not engaged rejects the cjudge pair, other pairs stay accepted
def test_a_bad_pair_is_rejected_not_refused(world):
    leg = V.kv_leg_of("cjudge", "x", "b1")
    tune = V.kv_tune_of("x", "b1", "cjudge")
    path = world.rows / ENTRY / f"cjudge.{tune}.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    rows[0]["draft"] = None
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    got = by_key(world.wave1(kinds=PLANNED))
    assert not got[("cjudge", "b1")]["accepted"] and any("not engaged" in r for r in got[("cjudge", "b1")]["reasons"]), leg
    assert got[("cjudge", "b2")]["accepted"] and got[("math500", "b1")]["accepted"]


# class (b): the frozen record must still be the pair's KV record
def test_the_frozen_record_must_be_the_pairs(world):
    (world.rows / "m76" / "wave1" / "run" / "frozen.s3.json").write_text(json.dumps(dict(world.frozen, lever="mtp")))
    with pytest.raises(V.RefusalError, match="KV record"):
        world.all_kv()


# class (b): a P426 (mtp lever) member is still deny-listed under kv
def test_p426_members_still_deny_listed(world):
    p = world.rows / "p426" / "x.json"
    p.parent.mkdir(parents=True)
    p.write_text("{}")
    with pytest.raises(V.RefusalError, match="deny-listed"):
        V._kv_member(world.rows, p, "w")


# ------------------------------------------------------------------------------------------------ p426_wave1 default axes
def _kv_default_axes(monkeypatch, tmp_path, lever_args):
    from bench import p426_wave1 as W

    seen = {}
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    monkeypatch.setattr(W, "main_kv", lambda args: seen.setdefault("axes", args.axes) and 0)
    rc = W.main(["--build", "s3", "--main-root", str(tmp_path), "--workdir", str(tmp_path), "--out", str(tmp_path / "o"), *lever_args])
    return rc, seen


# class (a): `p426_wave1 --lever kv` defaults `--axes` to kv_w1_kinds(build): the five planned kinds, no m1
def test_kv_sequencer_default_axes_are_the_planned_kinds(monkeypatch, tmp_path):
    """v2 amendment (same assertion): the default takes effect inside `main_kv` (the build is only checked there), so it is
    observed where it is consumed — the axes `schedule_kv` is asked for — not on the argparse namespace handed to `main_kv`."""
    from bench import p426_wave1 as W

    seen = {}

    def stop(axes, pair, tier=1, only=None):
        seen["axes"] = axes
        raise ValueError("stop")                     # main_kv answers rc 2 without launching anything

    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    monkeypatch.setattr(W, "schedule_kv", stop)
    (tmp_path / "n").mkdir()
    (tmp_path / "x").mkdir()
    rc = W.main(["--lever", "kv", "--build", "s3", "--pair", "n16,x", "--arm-root", f"n16={tmp_path / 'n'}",
                 "--arm-root", f"x={tmp_path / 'x'}", "--main-root", str(tmp_path / "main"), "--workdir", str(tmp_path),
                 "--out", str(tmp_path / "o")])
    assert rc == 2
    assert tuple(seen["axes"]) == tuple(P.kv_w1_kinds("s3")) == PLANNED


# class (b): an explicit --axes (including m1) still wins over the default
def test_kv_sequencer_explicit_axes_win(monkeypatch, tmp_path):
    rc, seen = _kv_default_axes(monkeypatch, tmp_path, ["--lever", "kv", "--pair", "n16,x", "--axes", "m1,cjudge"])
    assert seen["axes"] == "m1,cjudge"


# class (b): the mtp lever's default axes are unchanged (every axis of the lever)
def test_mtp_axes_constants_unchanged():
    from bench import p426_wave1 as W

    assert tuple(W.AXES) == ("math500", "cjudge", "vision", "reasoning", "m1")
    assert tuple(W.KV_AXES) == tuple(W.AXES) + ("longctx",)


# ------------------------------------------------------------------------------------------------ the mtp lever golden
def _mtp_b8():
    from bench import generate

    results = BENCH / "results"
    p426 = results / "p426"
    frozen = json.loads((p426 / "wave1.s2" / "run" / "frozen.s2.json").read_text())
    v8 = json.loads((p426 / "wave2" / "run" / "v8_base.json").read_text())
    for c in (frozen["stack_head_off"], frozen["stack_head_on"], v8["off_commit"]):
        if subprocess.run(["git", "cat-file", "-e", f"{c}^{{commit}}"], cwd=REPO, capture_output=True).returncode:
            pytest.skip(f"commit {c} is not in this checkout's object store (the mtp B8 needs it)")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(generate, "RESULTS", results)
        return V.verify_all(p426, results, REPO)


def _digest(b8):
    w1 = b8["axes"]["wave1"]
    return dict(sha256=sha(V.dumps(b8)), wave1_pairs=len(w1["pairs"]), accepted=sum(1 for p in w1["pairs"] if p["accepted"]),
                kinds=sorted({p["kind"] for p in w1["pairs"]}), a7_pairs=len(b8["axes"]["A7"]["pairs"]), keys=sorted(b8),
                wave1_keys=sorted(w1), has_dropped="dropped" in w1)


# class (b): the mtp lever's B8 over the committed p426 data is byte-identical to the golden computed on the baseline
# (skips, naming the commit, when the object store lacks it; fails when the golden is absent)
def test_mtp_b8_golden_unchanged():
    b8 = _mtp_b8()
    got = _digest(b8)
    sentinel = GOLDEN.with_name("WRITE_GOLDEN")                 # present only while regenerating on purpose; consumed here
    if sentinel.exists():
        GOLDEN.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n")
        sentinel.unlink()
    want = json.loads(GOLDEN.read_text())
    assert got == want
    assert got["has_dropped"] is False                                              # no kv-only key leaks into the mtp record


# class (b): the mtp lever's CLI is unchanged: `all` without --pair, and --pair without --lever kv, still behave as before
def test_mtp_cli_refusals_unchanged(world, tmp_path, capsys):
    out = tmp_path / "B8.json"
    assert V.main(["all", "--results-root", str(world.rows / "p426"), "--rows-root", str(world.rows), "--repo", str(world.repo),
                   "--out", str(out), "--pair", "n16,x"]) == 2
    assert V.main(["all", "--results-root", str(world.rows / "m76"), "--rows-root", str(world.rows), "--repo", str(world.repo),
                   "--out", str(out), "--lever", "kv"]) == 2
    assert not out.exists()
