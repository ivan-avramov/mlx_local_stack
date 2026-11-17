"""M76 B8 kv planned kinds (spec `docs/specs/m76-b8-kv-planned-kinds.md` v1, C354): on the REAL committed
`benchmark/results/m76/ids.json` (no m1 items), B8 verifies exactly the kinds build s3 planned, records the dropped m1 as
`not_run` with its ruling, still refuses a missing planned leg, and never indexes ids for an item-less kind."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from bench import p426_plan as P
from bench import p426_verify as V
from bench import p426_wave1 as W1
from bench.tests.test_m76_b3_impl_verify import ENTRY, REPO, World, sha

REAL_IDS = REPO / "benchmark" / "results" / "m76" / "ids.json"
PLANNED = ("math500", "cjudge", "vision", "reasoning", "longctx")
M1_REASON = "C352: M1 dropped from stage 3a (stage 1's matrix certifies memory)"
PAIR = ("n16", "x")


class RealWorld(World):
    """The B3 world on the committed ids.json, with legs of every Wave 1 kind (m1 a qualify leg without items)."""

    def __init__(self, tmp, monkeypatch, kinds=PLANNED):
        super().__init__(tmp, monkeypatch, kinds=())
        data = REAL_IDS.read_bytes()
        self.ids = json.loads(data)
        self.budget = self.ids["axes"]["longctx"]["budget"]
        self._write(self.rows / "m76" / "ids.json", data)
        assert "m1" not in self.ids["axes"]
        for kind in kinds:
            for label in ("b1", "b2"):
                for arm in PAIR:
                    self.leg(kind, arm, label)

    def leg(self, kind, arm, label, **kw):
        leg = self._leg(kind, arm, label, **kw)
        if kind in ("reasoning", "longctx"):
            self.stamp(kind, arm, label)
        return leg

    def stamp(self, kind, arm, label):
        """As run_reasoning / run_retrieval: each manifest's result_file / result_sha256 describe its result file's bytes."""
        edir, tune = self.rows / ENTRY, V.kv_tune_of(arm, label, kind)
        if kind == "reasoning":
            stems = [f"reasoning.{tune}"]
        else:
            items = {i["id"]: i for i in self.ids["axes"]["longctx"]["items"]}
            stems = [f"{'retrieval' if items[i]['task'] == 'retrieval' else 'reasoning'}.{tune}.{i}"
                     for i in self.ids["axes"]["longctx"][f"block{label[-1]}"]]
        for stem in stems:
            res, mp = edir / f"{stem}.json", edir / f"{stem}.manifest.json"
            man = json.loads(mp.read_text())
            man.update(result_file=res.name, result_sha256=sha(res.read_bytes()))
            mp.write_text(json.dumps(man))
        return stems

    def _leg(self, kind, arm, label, **kw):
        if kind in ("cjudge", "longctx"):
            return super().leg(kind, arm, label, **kw)
        leg, tune = V.kv_leg_of(kind, arm, label), V.kv_tune_of(arm, label, kind)
        receipt = dict(verdict="VALID", problems=[], name=leg, arm=arm, kind="qualify" if kind == "m1" else kind,
                       speed_valid=True, speed_problems=[], pins=dict(self.frozen, frozen_sha=self.frozen_sha),
                       state=dict(stack_head=self.head[arm], frozen_sha=self.frozen_sha),
                       worker=dict(cmdline="202 " + " ".join(self.argv(arm)).replace('", "', '","')), log={})
        ldir = self.rows / "m76" / "wave1" / leg
        self._write(ldir / f"{leg}.receipt.json", json.dumps(receipt))
        self._write(ldir / "SCRUB_MANIFEST.json", json.dumps(dict(leg=leg, files={})))
        if kind == "m1":
            mdir = ldir / "m1" / ENTRY
            self._write(mdir / "result.json", json.dumps(dict(
                status="ok", served=dict(model=ENTRY, kv_bits=0 if arm == "n16" else 4), snapshots={"--model": "s" * 40},
                requests=[dict(qualify=dict(generate_seed=11, prompt=dict(sized=262144)))])))
            self._write(mdir / "job.json", json.dumps(dict(argv=self.argv(arm))))
            self._write(ldir / "m1" / "report.json", json.dumps(dict(
                registry_sha256=sha(self.text[arm]), reviewed_head="r" * 40, production="p" * 40, versions={"mlx": "0.32.4"})))
            return leg
        edir = self.rows / ENTRY
        draft = dict(draft_kind="mtp", draft_rounds=5, draft_n=10, draft_n_accepted=7)
        planned = self.ids["axes"][kind][f"block{label[-1]}"]
        if kind == "math500":
            rows = [dict(id=i, sampler_seed=7, content=f"a {i}", content_sha256=sha(f"a {i}"), thinking_budget=81920, draft=draft)
                    for i in planned]
            self._write(edir / f"math500.{tune}.jsonl", "".join(json.dumps(r) + "\n" for r in rows))
            self._write(edir / f"math500.{tune}.manifest.json", json.dumps(self.manifest(arm)))
            self._write(edir / f"math500.{tune}.score.json", json.dumps(dict(n=len(rows))))
        elif kind == "vision":
            rows = [dict(id=i, seed=5, description=f"d {i}", draft=draft, turn2=dict(draft=draft)) for i in planned]
            self._write(edir / f"vision_gate.{tune}.jsonl", "".join(json.dumps(r) + "\n" for r in rows))
            self._write(edir / f"vision_gate.{tune}.manifest.json", json.dumps(self.manifest(arm)))
        else:
            seeds = self.ids["axes"]["reasoning"]["request_seeds"]
            rows = [dict(seed=t, sampler_seed=seeds[str(t)], content=f"r {t}", draft=draft) for t in planned]
            self._write(edir / f"reasoning.{tune}.json", json.dumps(dict(params=dict(thinking_budget=81920),
                                                                         records=[dict(rows=rows)])))
            self._write(edir / f"reasoning.{tune}.manifest.json", json.dumps(self.manifest(arm)))
        return leg


@pytest.fixture
def real(tmp_path, monkeypatch):
    return RealWorld(tmp_path, monkeypatch)


def test_plan_names_the_s3_kinds_and_the_dropped_m1():
    assert P.kv_w1_kinds("s3") == PLANNED
    assert P.kv_w1_dropped("s3") == {"m1": M1_REASON}
    for bad in ("s2", "zz", "S3"):
        with pytest.raises(ValueError):
            P.kv_w1_kinds(bad)
        with pytest.raises(ValueError):
            P.kv_w1_dropped(bad)


def _check_default_record(w1):
    got = {(p["kind"], p["block"]): p for p in w1["pairs"]}
    assert set(got) == {(k, b) for k in PLANNED for b in ("b1", "b2")}
    for p in got.values():
        assert p["accepted"], (p["kind"], p["block"], p["reasons"])
        assert not p["keys_rejected"]
    assert {"m1/b1", "m1/b2"} <= set(w1["not_run"])
    assert w1["dropped"] == {"m1": M1_REASON}
    assert not any("/wave1/m1-" in k for k in w1["inputs"])


def test_the_fixture_is_valid_under_explicit_planned_kinds(real):
    """Green on the baseline too: the tree itself verifies; the default's failure is the m1 handling alone."""
    rec = V.verify_wave1_kv(real.rows, real.repo, PAIR, kinds=PLANNED)
    assert all(p["accepted"] for p in rec["pairs"]), [(p["kind"], p["block"], p["reasons"]) for p in rec["pairs"]]
    assert len(rec["pairs"]) == 10


def test_default_kinds_verify_the_planned_wave1_on_the_real_ids(real):
    """Red today: the default loops m1 and indexes ids['m1'] (KeyError) / refuses its missing legs."""
    _check_default_record(V.verify_wave1_kv(real.rows, real.repo, PAIR))


def test_verify_all_kv_default_records_the_dropped_kind(real):
    b8 = V.verify_all_kv(real.rows, real.repo, PAIR)
    _check_default_record(b8["axes"]["wave1"])
    assert set(b8["axes"]) == {"wave1"}


def test_cli_kv_all_emits_b8_with_the_planned_kinds(real, tmp_path):
    out = tmp_path / "B8.json"
    rc = V.main(["all", "--lever", "kv", "--pair", "n16,x", "--results-root", str(real.rows / "m76"),
                 "--rows-root", str(real.rows), "--repo", str(real.repo), "--out", str(out)])
    assert rc == 0
    _check_default_record(json.loads(out.read_text())["axes"]["wave1"])


@pytest.mark.parametrize("kind,arm,label", [("cjudge", "x", "b2"), ("math500", "n16", "b1"), ("longctx", "x", "b1"),
                                            ("vision", "n16", "b2"), ("reasoning", "x", "b1")])
def test_a_missing_planned_leg_still_refuses(real, kind, arm, label):
    shutil.rmtree(real.rows / "m76" / "wave1" / V.kv_leg_of(kind, arm, label))
    with pytest.raises(V.RefusalError, match=V.kv_leg_of(kind, arm, label)):
        V.verify_wave1_kv(real.rows, real.repo, PAIR)


def test_explicit_kinds_with_m1_legs_still_verify_m1(tmp_path, monkeypatch):
    w = RealWorld(tmp_path, monkeypatch, kinds=PLANNED + ("m1",))
    rec = V.verify_wave1_kv(w.rows, w.repo, PAIR, kinds=V.KV_W1_KINDS)
    got = {(p["kind"], p["block"]): p for p in rec["pairs"]}
    assert set(got) == {(k, b) for k in V.KV_W1_KINDS for b in ("b1", "b2")}
    for b in ("b1", "b2"):
        assert got[("m1", b)]["accepted"], got[("m1", b)]["reasons"]
        assert got[("m1", b)]["identity_basis"] == "none"
    assert not any(x.startswith("m1/") for x in rec["not_run"])


def test_explicit_m1_without_its_legs_refuses_never_keyerror(real):
    with pytest.raises(V.RefusalError, match="m1"):
        V.verify_wave1_kv(real.rows, real.repo, PAIR, kinds=("m1",))


def test_unknown_build_refuses(real):
    with pytest.raises(V.RefusalError):
        V.verify_wave1_kv(real.rows, real.repo, PAIR, build="zz")


def test_wave1_kv_default_axes_are_the_planned_kinds(tmp_path, monkeypatch):
    seen = {}

    def fake(axes, pair, tier=1, only=None):
        seen["axes"] = axes
        raise ValueError("stop")

    monkeypatch.setattr(W1, "schedule_kv", fake)
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    (tmp_path / "n").mkdir()
    (tmp_path / "x").mkdir()
    rc = W1.main(["--lever", "kv", "--build", "s3", "--pair", "n16,x", "--arm-root", f"n16={tmp_path / 'n'}",
                  "--arm-root", f"x={tmp_path / 'x'}", "--main-root", str(tmp_path / "main"), "--workdir", str(tmp_path),
                  "--out", str(tmp_path / "out")])
    assert rc == 2
    assert seen["axes"] == PLANNED
    monkeypatch.setattr(W1, "schedule_kv", fake)
    W1.main(["--lever", "kv", "--build", "s3", "--pair", "n16,x", "--arm-root", f"n16={tmp_path / 'n'}", "--axes", "m1,cjudge",
             "--arm-root", f"x={tmp_path / 'x'}", "--main-root", str(tmp_path / "main"), "--workdir", str(tmp_path),
             "--out", str(tmp_path / "out")])
    assert seen["axes"] == ("m1", "cjudge")
