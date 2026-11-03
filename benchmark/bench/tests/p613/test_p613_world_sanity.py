"""The synthetic trees themselves: every builder option yields a tree in the committed shape (no code under test involved).

Class of every test is stated in the comment above it: all are `invariant` — they pin the fixtures the other modules rely on.
"""
from __future__ import annotations

import json

import pytest

from bench.tests.p613 import a7world as W


def planned(w, arm, session, ns="wave2", n=1):
    sched = json.loads(w.p(ns, W.attempt_name(arm, session, n), "schedule.json").read_text())
    return sum(len(i["names"]) for b in sched["blocks"] for l in b["legs"] for i in l["invocations"])


def read_rows(w, arm, session, ns="wave2", n=1):
    rows = []
    for f in sorted(w.p(ns, W.attempt_name(arm, session, n), session).glob("*.jsonl")):
        rows += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return rows


# class: invariant (row patches land, `acc` follows `passed`, seeds are paired and the ids are unique)
def test_row_patches_and_seeds(make_world):
    w = make_world(rows={("on", "s1"): {"python/a2": {"passed": False, "converged": False, "nonconv_kind": "budget_hit"}}})
    on = {r["id"]: r for r in read_rows(w, "on", "s1")}
    off = {r["id"]: r for r in read_rows(w, "off", "s1")}
    assert on["python/a2"]["passed"] is False and on["python/a2"]["acc"] == 0 and on["python/a2"]["nonconv_kind"] == "budget_hit"
    assert off["python/a2"]["passed"] is True
    assert {k: v["sampler_seed"] for k, v in on.items()} == {k: v["sampler_seed"] for k, v in off.items()}
    assert len(on) == len(off) == 8


# class: invariant (a DNF slot has no row, is recorded in chain.json, and rows + dnf == planned)
def test_dnf_option(make_world):
    w = make_world(dnf={("on", "s1"): ["go/g3"]})
    rows = read_rows(w, "on", "s1")
    chain = json.loads(w.apath("on", "s1", "chain.json").read_text())
    assert len(rows) == 7 and len(chain["p426_dnf"]) == 1 and planned(w, "on", "s1") == 8
    assert chain["p426_dnf"][0]["item"] == "g3" and chain["p426_dnf"][0]["language"] == "go"
    assert not list(w.apath("on", "s1", "items").glob("*go__g3*"))
    assert json.loads(w.apath("off", "s1", "chain.json").read_text())["p426_dnf"] == []


# class: invariant (identical option: both arms publish the same final tree for that key, others differ)
def test_identical_option(make_world):
    w = make_world(identical={("s1", "python/a2")})
    on = {r["id"]: r["final_tree"]["manifest_sha256"] for r in read_rows(w, "on", "s1")}
    off = {r["id"]: r["final_tree"]["manifest_sha256"] for r in read_rows(w, "off", "s1")}
    assert on["python/a2"] == off["python/a2"]
    assert all(on[k] != off[k] for k in on if k != "python/a2")


# class: invariant (HARVEST main files exist, hash to published_sha256, equal the row's manifest sha; evidence entry has no file)
def test_harvest_matches_files_and_rows(make_world):
    w = make_world()
    h = json.loads(w.apath("on", "s2", "HARVEST.json").read_text())
    assert h["sha256"] == W.canon_sha(h)
    shas = {r["final_tree"]["manifest_sha256"] for r in read_rows(w, "on", "s2")}
    main = [f for f in h["files"] if f["destination"] == "main"]
    assert len(main) == 8 and {f["published_sha256"] for f in main} == shas
    for f in main:
        path = w.repo / f["published"]
        assert W.sha_bytes(path.read_bytes()) == f["published_sha256"]
    assert [f for f in h["files"] if f["destination"] == "evidence"]


# class: invariant (item records: one real + one decoy .ready.json per row; totals follow the rate; sensitivity == rate by default)
def test_item_records_and_decoys(make_world):
    w = make_world(speed={("on", "s1"): {"python/a1": {"rate": 40.0}}})
    items = w.apath("on", "s1", "items")
    real = sorted(p for p in items.glob("*.json") if not p.name.endswith(".ready.json"))
    ready = sorted(items.glob("*.ready.json"))
    assert len(real) == len(ready) == 8
    rec = json.loads(next(p for p in real if p.name.endswith("__python__a1.json")).read_text())
    t = rec["totals"]
    assert (t["generated_tokens"] - t["requests"]) / t["decode_s"] == pytest.approx(40.0)
    reqs = rec["requests"]
    assert sum(r["generated_tokens"] - 1 for r in reqs) / sum((r["generated_tokens"] - 1) / r["decode_tok_s"] for r in reqs) \
        == pytest.approx(40.0)
    assert (t["accepted"], t["proposed"]) == (80, 100)
    assert json.loads(next(p for p in ready if "__python__a1" in p.name).read_text())["totals"]["generated_tokens"] > 1e6


# class: invariant (custom request records: totals follow the explicit values)
def test_custom_request_records(make_world):
    reqs = [{"generated_tokens": 11, "decode_tok_s": 5.0, "draft_n": None, "draft_n_accepted": None, "error": None}]
    w = make_world(speed={("off", "s1"): {"go/g1": {"requests": reqs, "generated_tokens": 12, "n_requests": 1,
                                                    "decode_s": 4.0}}})
    rec = json.loads(next(w.apath("off", "s1", "items").glob("*__go__g1.json")).read_text())
    assert rec["totals"] == {"requests": 1, "generated_tokens": 12, "decode_s": 4.0, "accepted": 0, "proposed": 0,
                             "prompt_tokens": 1000, "decode_rate_source": "completed requests (spec 8)"}


# class: invariant (leg overrides re-seal the leg record; the dossier hashes follow the bytes after `refresh`)
def test_leg_override_and_refresh(make_world):
    w = make_world(legs={("on", "s1"): {"speed_valid": False}})
    leg = json.loads(w.apath("on", "s1", "leg.json").read_text())
    assert leg["speed_valid"] is False and leg["sha256"] == W.canon_sha(leg)
    w.edit_leg("off", "s1", state="INVALID")
    assert json.loads(w.apath("off", "s1", "leg.json").read_text())["state"] == "INVALID"
    d = json.loads(w.p("wave2", "pairs", "s1__off-a1__on-a1.json").read_text())
    assert d["sha256"] == W.canon_sha(d)
    assert d["arms"]["on"]["harvest_sha256"] == W.sha_bytes(w.apath("on", "s1", "HARVEST.json").read_bytes())


# class: invariant (diagnostic sessions: five slots in one file)
def test_pilot_and_reload_shape(make_world):
    w = make_world()
    for s in ("pilot", "reload"):
        for arm in ("off", "on"):
            assert planned(w, arm, s) == 5 and len(read_rows(w, arm, s)) == 5


# class: invariant (superseded namespace: own v8_base (different sha), attempts by name, state and schedule honoured)
def test_old_namespace_option(make_world):
    old = {"v8_sha_note": "old", "attempts": [
        {"arm": "off", "session": "s1", "n": 1, "rows": {"python/a2": {"passed": False}}},
        {"arm": "on", "session": "s1", "n": 1, "state": "INVALID", "rows": {}},
        {"arm": "on", "session": "pilot", "n": 1, "note": "different schedule", "rows": {}},
        {"arm": "on", "session": "s1", "n": 2, "rows": {}},
    ]}
    w = make_world(old_namespace=old)
    assert json.loads(w.p("wave2", "run", "v8_base.json").read_text())["sha256"] != \
        json.loads(w.p(W.OLD_NS, "run", "v8_base.json").read_text())["sha256"]
    off_new = w.p("wave2", W.attempt_name("off", "s1"), "schedule.json").read_bytes()
    off_old = w.p(W.OLD_NS, W.attempt_name("off", "s1"), "schedule.json").read_bytes()
    assert off_new == off_old
    assert w.p("wave2", W.attempt_name("on", "pilot"), "schedule.json").read_bytes() != \
        w.p(W.OLD_NS, W.attempt_name("on", "pilot"), "schedule.json").read_bytes()
    assert json.loads(w.p(W.OLD_NS, W.attempt_name("on", "s1"), "leg.json").read_text())["state"] == "INVALID"
    assert w.p(W.OLD_NS, W.attempt_name("on", "s1", 2), "leg.json").exists()
    assert not w.p("wave2", W.attempt_name("on", "s1", 2)).exists()
    old_off = {r["id"]: r["passed"] for r in read_rows(w, "off", "s1", ns=W.OLD_NS)}
    assert old_off["python/a2"] is False and old_off["python/a1"] is True


# class: invariant (custom id lists change the schedule: 40 slots over python + go legs)
def test_custom_ids(make_world):
    ids = [f"python/p{i}" for i in range(1, 26)] + [f"go/q{i}" for i in range(1, 16)]
    w = make_world(ids={"s1": ids})
    assert planned(w, "on", "s1") == 40 and len(read_rows(w, "on", "s1")) == 40
    assert len(list(w.apath("on", "s1", "s1").glob("*.jsonl"))) == 3


# class: invariant (no absolute path inside any record the builder writes)
def test_no_absolute_paths_in_the_tree(make_world):
    w = make_world()
    for path in w.root.rglob("*.json*"):
        text = path.read_text()
        assert str(w.base) not in text, path
