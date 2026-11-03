"""Fix-round tests (P613 step 1): one `test_fix<N>_...` per adopted finding 1-16, each a REPRODUCES-FAILURE case: it fails on
the first candidate and passes on the fixed one. They read the sheet by its (now known) JSON layout, e.g.
`sig["sessions"]["s1"]["speed"]["primary"]`, `sig["noise_floor"]`, `sig["coverage"]["A7"]`, `sig["flags"][i]["items"]`.

Class of every test: reproduces-failure (unless the comment says otherwise).
"""
from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from bench.tests.p613 import a7world as W
from bench.tests.p613.sigview import run_cli
from bench.tests.p613.test_p613_signals_tax_speed_noise import old_ns

IDS8 = W.DEFAULT_IDS["s1"]


def go(w, verify, signals):
    b8 = verify.verify_a7(w.root)
    return b8, signals.compute_a7(w.root, b8)


def pair(b8, s):
    return [p for p in b8["pairs"] if p["pair"] == s][0]


def item_path(w, arm, session, rid):
    lang, item = W.split_item(rid)
    return next(p for p in w.apath(arm, session, "items").glob(f"*__{session}__{lang}__{item}.json")
                if not p.name.endswith(".ready.json"))


def edit_plain(path, fn):
    doc = json.loads(path.read_text())
    out = fn(doc)
    path.write_text(W.dumps(doc if out is None else out))


def flag_names(sig):
    return [f["flag"] for f in sig["flags"]]


# ---------------------------------------------------------------------------------------------------------------- 1
# fix 1: every row needs exactly one matching item record
def test_fix1_missing_item_record_refuses(make_world, verify):
    w = make_world()
    item_path(w, "on", "s1", "python/a3").unlink()
    with pytest.raises(verify.RefusalError, match="item record"):
        verify.verify_a7(w.root)


def test_fix1_mis_slotted_item_record_refuses(make_world, verify):
    w = make_world()
    edit_plain(item_path(w, "on", "s1", "python/a1"), lambda d: d.update(slot=d["slot"].replace("|s1|", "|s2|")))
    with pytest.raises(verify.RefusalError):
        verify.verify_a7(w.root)


def test_fix1_dnf_slot_gets_no_speed_rate(make_world, verify, signals):
    w = make_world(dnf={("on", "s1"): ["go/g3"]})
    shutil.copy(item_path(w, "off", "s1", "go/g3"), w.apath("on", "s1", "items") / item_path(w, "off", "s1", "go/g3").name)
    _, sig = go(w, verify, signals)
    prim = sig["sessions"]["s1"]["speed"]["primary"]
    assert prim["n"] == 7
    assert [d["id"] for d in prim["dropped"]] == ["go/g3"] and "DNF" in prim["dropped"][0]["reason"]


# ---------------------------------------------------------------------------------------------------------------- 2
def split_schedule_edit(w, arm, session, fn):
    edit_plain(w.apath(arm, session, "schedule.json"), fn)


# fix 2: schedules that differ beyond the arm fields reject the pair
def test_fix2_schedule_difference_rejects_the_pair(make_world, verify):
    w = make_world()
    split_schedule_edit(w, "on", "s1", lambda d: d.update(note="a different plan"))
    p = pair(verify.verify_a7(w.root), "s1")
    assert p["accepted"] is False and any("rule 3: schedules differ" in r for r in p["reasons"])


# class: invariant on the fixed candidate (the arm fields `predictor` / draft_kind do not count as a plan difference)
def test_fix2_arm_fields_are_not_a_plan_difference(make_world, verify):
    w = make_world()

    def arm_fields(arm, pred, kind):
        def fn(d):
            d["predictor"] = pred
            for b in d["blocks"]:
                for leg in b["legs"]:
                    leg["draft_kind"] = kind
        split_schedule_edit(w, arm, "s1", fn)
    arm_fields("off", "off", "off")
    arm_fields("on", "mtp", "mtp")
    p = pair(verify.verify_a7(w.root), "s1")
    assert p["accepted"] is True, p["reasons"]


def rename_planned_slot(w, arm, session, old, new):
    """Make `arm` plan (and run) `new` instead of `old`: schedule names / expect, the row id, the item record."""
    (ol, oi), (nl, ni) = W.split_item(old), W.split_item(new)

    def sched(d):
        for b in d["blocks"]:
            for leg in b["legs"]:
                for inv in leg["invocations"]:
                    inv["names"] = [ni if n == oi else n for n in inv["names"]]
                    inv["expect"] = [new if e == old else e for e in inv["expect"]]
    split_schedule_edit(w, arm, session, sched)
    w.edit_rows(arm, session, lambda rows: [dict(r, id=new) if r["id"] == old else r for r in rows])
    p = item_path(w, arm, session, old)
    edit_plain(p, lambda d: d.update(slot=d["slot"].replace(f"|{oi}", f"|{ni}")))
    p.rename(p.with_name(p.name.replace(f"__{ol}__{oi}.json", f"__{nl}__{ni}.json")))


# fix 2: the one-sided keys of two differing schedules are listed alone, with the schedule reason on the pair
def test_fix2_one_sided_keys_listed_with_schedule_reason(make_world, verify):
    w = make_world()
    rename_planned_slot(w, "on", "s1", "go/g2", "go/g2x")
    p = pair(verify.verify_a7(w.root), "s1")
    assert p["accepted"] is False and any("schedules differ" in r for r in p["reasons"])
    assert sorted(k["key"][1] for k in p["keys_rejected"]) == ["go/g2", "go/g2x"] and p["keys_accepted"] == 7


# fix 2: a seed-mismatched key is rejected alone; the pair stays accepted (candidate 1 rejected the pair)
def test_fix2_seed_mismatch_rejects_only_the_key(make_world, verify):
    w = make_world()
    w.edit_rows("on", "s1", lambda rows: [dict(r, sampler_seed=r["sampler_seed"] + 1) if r["id"] == "go/g1" else r
                                          for r in rows])
    p = pair(verify.verify_a7(w.root), "s1")
    assert p["accepted"] is True and p["reasons"] == []
    assert [k["key"] for k in p["keys_rejected"]] == [["s1", "go/g1"]] and p["keys_accepted"] == 7


# ---------------------------------------------------------------------------------------------------------------- 3
# fix 3: a make-up record refuses (never a pending number)
def test_fix3_makeup_record_refuses(make_world, verify, signals):
    w = make_world()
    seq = w.load("wave2", "run", "sequence.json")
    seq["makeup"] = [{"leg": "tg1-p426-on-s1", "attempt": 2}]
    w.save(seq, "wave2", "run", "sequence.json", seal=False)
    b8 = verify.verify_a7(w.root)
    with pytest.raises(verify.RefusalError, match="make-up legs present"):
        signals.compute_a7(w.root, b8)


# ---------------------------------------------------------------------------------------------------------------- 4
# fix 4: same-epoch noise floor only when both diagnostic pairs are accepted
def test_fix4_rejected_diagnostic_pair_blocks_the_same_epoch_floor(make_world, verify, signals):
    w = make_world()
    w.edit_leg("on", "reload", state="INVALID")
    b8, sig = go(w, verify, signals)
    assert pair(b8, "reload")["accepted"] is False
    same = sig["noise_floor"]["same_epoch"]
    assert same["status"].startswith("not computed: diagnostic pair rejected")
    assert "off" not in same and "on" not in same


# ---------------------------------------------------------------------------------------------------------------- 5
# fix 5: noise-floor comparisons run over the planned slots; a DNF slot is a non-success
def test_fix5_dnf_slot_is_a_flip_over_planned_slots(make_world, verify, signals):
    w = make_world(dnf={("on", "pilot"): ["python/a5"]})
    _, sig = go(w, verify, signals)
    on = sig["noise_floor"]["same_epoch"]["on"]
    assert (on["flips"], on["common"], on["flip_items"]) == (1, 5, ["python/a5"])
    off = sig["noise_floor"]["same_epoch"]["off"]
    assert (off["flips"], off["common"]) == (0, 5)


# ---------------------------------------------------------------------------------------------------------------- 6
# fix 6: totals count only when decode_rate_source names completed requests
def test_fix6_other_decode_rate_source_is_dropped_with_reason(make_world, verify, signals):
    w = make_world()
    edit_plain(item_path(w, "on", "s1", "python/a1"), lambda d: d["totals"].update(decode_rate_source="all requests"))
    _, sig = go(w, verify, signals)
    sp = sig["sessions"]["s1"]["speed"]
    assert sp["primary"]["n"] == 7 and sp["sensitivity"]["n"] == 8
    d = sp["primary"]["dropped"]
    assert [x["id"] for x in d] == ["python/a1"] and "decode_rate_source" in d[0]["reason"]


# ---------------------------------------------------------------------------------------------------------------- 7
# fix 7: identity counts only when the row's manifest sha equals the HARVEST main file's published sha
def test_fix7_row_sha_not_in_harvest_is_never_identical(make_world, verify):
    w = make_world()
    bogus = "ab" * 32
    for arm in ("off", "on"):
        w.edit_rows(arm, "s1", lambda rows: [dict(r, final_tree=dict(r["final_tree"], manifest_sha256=bogus))
                                             if r["id"] == "python/a2" else r for r in rows])
    p = pair(verify.verify_a7(w.root), "s1")
    key = [k for k in p["keys"] if k["key"][1] == "python/a2"][0]
    assert key["identical"] is False and key["off_manifest_sha256"] is None and key["on_manifest_sha256"] is None
    assert p["accepted"] is True


# ---------------------------------------------------------------------------------------------------------------- 8
# fix 8: no pooled cross-epoch headline; per arm, each matched attempt with flips / common
def test_fix8_cross_epoch_is_per_arm(make_world, verify, signals):
    w = make_world(old_namespace=old_ns())
    _, sig = go(w, verify, signals)
    cross = sig["noise_floor"]["cross_epoch"]
    assert "flips" not in cross and "common" not in cross
    assert cross["per_arm"]["off"]["flips"] == 1 and cross["per_arm"]["off"]["common"] == 13
    assert cross["per_arm"]["on"]["flips"] == 6 and cross["per_arm"]["on"]["common"] == 8
    assert {(m["arm"], m["superseded"], m["flips"], m["common"]) for m in cross["matches"]} == {
        ("off", "tg1-p426-off-s1.a1", 1, 8), ("off", "tg1-p426-off-pilot.a1", 0, 5), ("on", "tg1-p426-on-s1.a2", 6, 8)}


# ---------------------------------------------------------------------------------------------------------------- 9
# fix 9: exactly -5 pp (n = 20, one loss) is not "< -5 pp"
def test_fix9_exactly_minus_5pp_is_not_flagged(make_world, verify, signals):
    ids = [f"python/p{i}" for i in range(1, 21)]
    w = make_world(ids={"s1": ids}, rows={("on", "s1"): {"python/p1": {"passed": False}}})
    _, sig = go(w, verify, signals)
    assert sig["sessions"]["s1"]["paired_strict"]["delta"] == pytest.approx(-0.05)
    assert "strict_point_below_-5pp" not in flag_names(sig)


# ---------------------------------------------------------------------------------------------------------------- 10
# fix 10: the header's B8 sha is the sha256 of the B8 FILE bytes passed to the CLI
def test_fix10_header_sha_is_the_file_bytes(make_world, tmp_path):
    w = make_world()
    b8, md, js = tmp_path / "B8.json", tmp_path / "S.md", tmp_path / "S.json"
    assert run_cli("bench.p426_verify", ["a7", "--results-root", w.root, "--out", b8]).returncode == 0
    b8.write_text(json.dumps(json.loads(b8.read_text()), indent=4, sort_keys=False) + "\n")      # not the canonical form
    r = run_cli("bench.p426_signals", ["a7", "--results-root", w.root, "--b8", b8, "--out-md", md, "--out-json", js])
    assert r.returncode == 0, r.stderr
    want = hashlib.sha256(b8.read_bytes()).hexdigest()
    assert json.loads(js.read_text())["header"]["b8_sha256"] == want and want in md.read_text()


# fix 10: a direct call passes the sha through; without it the header names the canonical-dump basis
def test_fix10_compute_takes_the_sha_argument(make_world, verify, signals):
    w = make_world()
    b8 = verify.verify_a7(w.root)
    sig = signals.compute_a7(w.root, b8, "cd" * 32)
    assert sig["header"]["b8_sha256"] == "cd" * 32 and "file bytes" in sig["header"]["b8_sha256_basis"]
    assert "canonical" in signals.compute_a7(w.root, b8)["header"]["b8_sha256_basis"]


# ---------------------------------------------------------------------------------------------------------------- 11
# fix 11: coverage state = the verified leg.json state; a disagreement with sequence.json is listed
def test_fix11_coverage_follows_leg_json(make_world, verify, signals):
    w = make_world()
    w.edit_leg("on", "s1", state="INVALID")
    _, sig = go(w, verify, signals)
    a7 = sig["coverage"]["A7"]
    assert [(d["leg"], d["attempt"]) for d in a7["invalid"]] == [("tg1-p426-on-s1", 1)]
    assert [(m["leg"], m["leg_json"], m["sequence"]) for m in a7["state_mismatch"]] == [("tg1-p426-on-s1.a1", "INVALID", "VALID")]
    assert [d["leg"] for d in a7["rejected"]] == ["tg1-p426-off-s1"]          # valid leg, its pair rejected by B8


# ---------------------------------------------------------------------------------------------------------------- 12
# fix 12: a missing --out directory is rc 2 + REFUSED (no traceback)
def test_fix12_verify_missing_out_dir(make_world, tmp_path):
    w = make_world()
    r = run_cli("bench.p426_verify", ["a7", "--results-root", w.root, "--out", tmp_path / "nodir" / "B8.json"])
    assert r.returncode == 2 and r.stderr.startswith("REFUSED: ") and "Traceback" not in r.stderr


def test_fix12_signals_missing_out_dir_writes_nothing(make_world, tmp_path):
    w = make_world()
    b8, md = tmp_path / "B8.json", tmp_path / "S.md"
    assert run_cli("bench.p426_verify", ["a7", "--results-root", w.root, "--out", b8]).returncode == 0
    r = run_cli("bench.p426_signals", ["a7", "--results-root", w.root, "--b8", b8, "--out-md", md,
                                       "--out-json", tmp_path / "nodir" / "S.json"])
    assert r.returncode == 2 and r.stderr.startswith("REFUSED: ") and "Traceback" not in r.stderr
    assert not md.exists()
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_file()) == ["B8.json"], "no temporaries left behind"


# ---------------------------------------------------------------------------------------------------------------- 13
def fail_g1(on_kind, on_flags=()):
    on = {"passed": False, "converged": False, "nonconv_kind": on_kind, "nonconv_flags": list(on_flags)}
    off = {"passed": False, "converged": True, "nonconv_kind": None, "nonconv_flags": []}
    return {("on", "s1"): {"go/g1": on}, ("off", "s1"): {"go/g1": off}}


# fix 13: any nonconv_kind present in ON and absent in OFF is flagged, not only the six tax categories
def test_fix13_other_nonconv_kind_on_only_is_flagged(make_world, verify, signals):
    w = make_world(rows=fail_g1("weird_kind"))
    _, sig = go(w, verify, signals)
    hits = [f for f in sig["flags"] if f["flag"] == "nonconv_kind_on_only"]
    assert len(hits) == 1 and hits[0]["category"] == "weird_kind" and hits[0]["member"] == "A7-s1"


# a tax category is flagged once (as tax), not twice
def test_fix13_tax_category_is_not_flagged_twice(make_world, verify, signals):
    w = make_world(rows=fail_g1("looping"))
    _, sig = go(w, verify, signals)
    assert flag_names(sig) == ["tax_on_only"]


# ---------------------------------------------------------------------------------------------------------------- 14
# fix 14: *.dnf.* files are not rows and not item records
def test_fix14_dnf_row_sidecar_is_not_read_as_rows(make_world, verify):
    w = make_world()
    first = next(iter(sorted(w.apath("on", "s1", "s1").glob("*.jsonl")))).read_text().splitlines()[0]
    (w.apath("on", "s1", "s1") / "x.dnf.jsonl").write_text(first + "\n")
    assert pair(verify.verify_a7(w.root), "s1")["accepted"] is True


def test_fix14_dnf_item_record_is_not_an_item_record(make_world, verify):
    w = make_world()
    real = item_path(w, "on", "s1", "python/a1")
    (real.parent / real.name.replace(".json", ".dnf.json")).write_text(real.read_text())
    assert pair(verify.verify_a7(w.root), "s1")["accepted"] is True


# ---------------------------------------------------------------------------------------------------------------- 15
# fix 15: an invocation whose `expect` differs from len(names) refuses
def test_fix15_expect_longer_than_names_refuses(make_world, verify):
    w = make_world()
    split_schedule_edit(w, "on", "s1", lambda d: d["blocks"][0]["legs"][0]["invocations"][0]["expect"].append("python/zz"))
    with pytest.raises(verify.RefusalError, match="expect"):
        verify.verify_a7(w.root)


def test_fix15_expect_count_mismatch_refuses(make_world, verify):
    w = make_world()
    split_schedule_edit(w, "off", "s2", lambda d: d["blocks"][0]["legs"][0]["invocations"][0].update(expect=2))
    with pytest.raises(verify.RefusalError, match="expect"):
        verify.verify_a7(w.root)


# ---------------------------------------------------------------------------------------------------------------- 16
def ending(passed, converged, kind=None):
    return {"passed": passed, "converged": converged, "nonconv_kind": kind}


# fix 16: every flag carries its items with both arms' endings; SIGNALS.md prints them under the flag
def test_fix16_strict_point_flag_items_and_md(make_world, verify, signals):
    w = make_world(rows={("on", "s1"): {"python/a3": {"passed": False}}})
    _, sig = go(w, verify, signals)
    (f,) = [x for x in sig["flags"] if x["flag"] == "strict_point_below_-5pp"]
    assert f["items"] == [dict(id="python/a3", arm="on", ending=ending(False, True), other_arm="off",
                               other_ending=ending(True, True))]
    flags_md = signals.render_md(sig).split("## Flags")[1].split("## Noise floor")[0]
    assert "python/a3" in flags_md


def test_fix16_acceptance_flag_items_are_the_low_items(make_world, verify, signals):
    on = {i: {"accepted": 65, "proposed": 100} for i in IDS8}
    on["python/a1"] = {"accepted": 100, "proposed": 100}
    w = make_world(speed={("on", "s1"): on})
    _, sig = go(w, verify, signals)
    (f,) = [x for x in sig["flags"] if x["flag"] == "acceptance_below_0.70"]
    assert sorted(i["id"] for i in f["items"]) == sorted(set(IDS8) - {"python/a1"})
    assert all(i["arm"] == "on" and i["other_arm"] == "off" for i in f["items"])


def test_fix16_decode_flag_items_are_the_slow_items(make_world, verify, signals):
    on = {i: {"rate": 20.0} for i in IDS8}
    on["python/a1"] = {"rate": 40.0}
    on["python/a2"] = {"rate": 40.0}
    w = make_world(speed={("on", "s1"): on})
    _, sig = go(w, verify, signals)
    (f,) = [x for x in sig["flags"] if x["flag"] == "decode_ratio_below_1.3"]
    assert sorted(i["id"] for i in f["items"]) == sorted(set(IDS8) - {"python/a1", "python/a2"})


def test_fix16_tax_flag_items(make_world, verify, signals):
    w = make_world(rows=fail_g1("looping"))
    _, sig = go(w, verify, signals)
    (f,) = sig["flags"]
    assert f["items"] == [dict(id="go/g1", arm="on", ending=ending(False, False, "looping"), other_arm="off",
                               other_ending=ending(False, True))]
