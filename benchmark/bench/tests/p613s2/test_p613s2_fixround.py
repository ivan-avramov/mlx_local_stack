"""Delivery 3: one test per adopted fix of `.p613-material/dispositions.md` (fixes 1-16) plus the two GLM gaps (G1, G2).

Every test is class `reproduces-failure`: it fails on the candidate of delivery 2 for the stated reason and must pass once the fix is in.
Test names carry the fix number. Flag members are read through the `member` / `flag` keys of the flag records (as the delivery-2 candidate
writes them); everything else goes through the contract's interfaces.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from bench.tests.p613 import sigview as SV
from bench.tests.p613s2 import test_p613s2_signals_flags as FL
from bench.tests.p613s2 import w1view as V
from bench.tests.p613s2 import wave1world as WW

D = WW.draft
_ORIG_EXCLUDED = WW.Wave1World._build_excluded


def _excluded_with_manifests(self):
    """The real smoke legs carry a SCRUB_MANIFEST.json; the default fixture's do not (fix 1 pins that case). The other fix tests build
    worlds whose smoke legs have one, so that a candidate that still refuses a manifest-less smoke leg (fix 1) cannot mask them."""
    _ORIG_EXCLUDED(self)
    for d in sorted(self.w1.iterdir()):
        if d.is_dir() and d.name.endswith("-smoke"):
            files = {}
            for f in sorted(d.glob("*.receipt.json")):
                sha = hashlib.sha256(f.read_bytes()).hexdigest()
                files["benchmark/results/" + self.rel(f)] = {"original_sha256": sha, "published_sha256": sha, "scrubbed_sha256": sha,
                                                              "source": None}
            (d / "SCRUB_MANIFEST.json").write_text(WW.dumps({"files": files}))


@pytest.fixture(scope="module", autouse=True)
def _smoke_manifests_for_this_module():
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(WW.Wave1World, "_build_excluded", _excluded_with_manifests)
        yield


@pytest.fixture
def default_smoke_legs(monkeypatch):
    """The default fixture again: smoke legs WITHOUT a manifest (fix 1)."""
    monkeypatch.setattr(WW.Wave1World, "_build_excluded", _ORIG_EXCLUDED)


def a(i):
    return f"test/algebra/{i}.json"


def only_rejected(b8, kind, block):
    bad = V.rejected(b8)
    assert [(p["kind"], V.digit(p["block"])) for p in bad] == [(kind, V.digit(block))], [(p["kind"], p["block"], p["reasons"]) for p in bad]
    return bad[0]


def named(p, *words):
    t = V.reason_text(p)
    for w in words:
        assert w.lower() in t, (w, p["reasons"])


def flag_dicts(sig):
    out = []

    def walk(n):
        if isinstance(n, dict):
            if "flag" in n:
                out.append(n)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    for t in SV.flags_tree(sig):
        walk(t)
    return out


def flag_of(sig, member, flag):
    hits = [d for d in flag_dicts(sig) if str(d.get("member")).lower() == member.lower() and str(d.get("flag")).lower() == flag.lower()]
    assert hits, (member, flag, [(d.get("member"), d.get("flag")) for d in flag_dicts(sig)])
    return json.dumps(hits[0], sort_keys=True, default=str).lower()


# =========================================================================================================== fix 1: smoke is coverage only
# class: reproduces-failure (a smoke leg without SCRUB_MANIFEST.json (the default world) must not refuse; no smoke file in `inputs`)
def test_fix01_smoke_leg_without_manifest_does_not_refuse(verify, make_w1, default_smoke_legs):
    w = make_w1()
    assert not (w.w1 / "math500-p426s2-on-smoke" / "SCRUB_MANIFEST.json").exists()
    b8 = verify.verify_wave1(w.p426, w.rows_root, w.repo)
    assert V.accepted_all(b8)
    assert not [k for k in b8["inputs"] if "smoke" in k]


# class: reproduces-failure (missing, mismatched and unreadable smoke manifests are recorded in scrub_coverage, never a refusal or a gate)
def test_fix01_bad_smoke_manifests_are_recorded_not_refused(verify, make_w1, default_smoke_legs):
    w = make_w1()
    d1, d2 = w.w1 / "math500-p426s2-on-smoke", w.w1 / "cjudge-p426s2-off-smoke"
    rec = d1 / "math500-p426s2-on-smoke.receipt.json"
    (d1 / "SCRUB_MANIFEST.json").write_text(WW.dumps({"files": {"benchmark/results/" + w.rel(rec): {"published_sha256": "0" * 64}}}))
    (d2 / "SCRUB_MANIFEST.json").write_text("{not json")
    b8 = verify.verify_wave1(w.p426, w.rows_root, w.repo)
    assert V.accepted_all(b8)
    cov = json.dumps(b8.get("scrub_coverage", V.wave1(b8).get("scrub_coverage")), sort_keys=True)
    assert cov != "null" and "math500-p426s2-on-smoke" in cov and "cjudge-p426s2-off-smoke" in cov
    assert not [k for k in b8["inputs"] if "smoke" in k]


# ============================================================================================ fix 2: thinking budgets per key, 81920
# class: reproduces-failure (a compensated swap of two budgets: the multisets are equal, the keys are not -> rejected)
@pytest.mark.parametrize("kind", ("cjudge", "math500"))
def test_fix02_compensated_budget_swap_is_rejected(verify, make_w1, kind):
    w = make_w1()
    w.edit_rows(kind, "off", "b1", lambda rows: (rows[0].update(thinking_budget=40960), rows[1].update(thinking_budget=81920)))
    w.edit_rows(kind, "on", "b1", lambda rows: (rows[0].update(thinking_budget=81920), rows[1].update(thinking_budget=40960)))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), kind, "b1")
    named(p, "rule 2", "thinking_budget")


# class: reproduces-failure (equal budgets in both arms but not 81920 on every row: rejected, the sheet is labelled @81920)
@pytest.mark.parametrize("kind", ("cjudge", "math500"))
def test_fix02_every_budget_must_be_81920(verify, make_w1, kind):
    w = make_w1()
    for arm in WW.ARMS:
        w.edit_rows(kind, arm, "b2", lambda rows: [r.update(thinking_budget=40960) for r in rows])
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), kind, "b2")
    named(p, "rule 2", "81920")


# ======================================================================================================= fix 3: the leg's own worktree
# class: reproduces-failure (an ON receipt naming the OFF worktree (and vice versa) is rejected: only the leg's own arm component is normalised)
@pytest.mark.parametrize("arm", WW.ARMS)
@pytest.mark.parametrize("kind", ("math500", "vision"))
def test_fix03_swapped_arm_worktree_is_rejected(verify, make_w1, arm, kind):
    w = make_w1()
    other = "off" if arm == "on" else "on"
    w.edit_receipt(kind, arm, "b1", lambda d: d["worker"].update(
        cmdline=d["worker"]["cmdline"].replace(f"stack-p426-s2-{arm}", f"stack-p426-s2-{other}")))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), kind, "b1")
    named(p, "rule 2", f"stack-p426-s2-{other}")


# ================================================================================================== fix 4: identity fields are required
# class: reproduces-failure (A1 / A2 rows with no content and no content_sha256 in both arms are a refusal, not `None == None`)
@pytest.mark.parametrize("kind", ("math500", "cjudge"))
def test_fix04_missing_content_and_sha_refuse(verify, make_w1, kind):
    w = make_w1()
    for arm in WW.ARMS:
        w.edit_rows(kind, arm, "b1", lambda rows: (rows[0].pop("content"), rows[0].pop("content_sha256")))
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426, w.rows_root, w.repo)


# class: reproduces-failure (A1 / A2: content present but content_sha256 absent in both arms refuses)
@pytest.mark.parametrize("kind", ("math500", "cjudge"))
def test_fix04_missing_sha_alone_refuses(verify, make_w1, kind):
    w = make_w1()
    for arm in WW.ARMS:
        w.edit_rows(kind, arm, "b2", lambda rows: rows[1].pop("content_sha256"))
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426, w.rows_root, w.repo)


# class: reproduces-failure (A3 without `description`, A4 without `content`, in both arms, refuse)
@pytest.mark.parametrize("kind,field", [("vision", "description"), ("reasoning", "content")])
def test_fix04_missing_identity_text_refuses(verify, make_w1, kind, field):
    w = make_w1()
    for arm in WW.ARMS:
        w.edit_rows(kind, arm, "b1", lambda rows: rows[0].pop(field))
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426, w.rows_root, w.repo)


# =============================================================================================== fix 5: inputs stay under rows_root
# class: reproduces-failure (a SCRUB-covered file, a manifest or ids.json that is a symlink to a file OUTSIDE rows_root refuses (same bytes))
@pytest.mark.parametrize("what", ["manifest", "stdout", "ids"])
def test_fix05_symlink_escaping_rows_root_refuses(verify, make_w1, tmp_path, what):
    w = make_w1()
    target = w.p426 / "ids.json" if what == "ids" else w.path_of("cjudge", "on", "b1", what)
    outside = tmp_path / "outside" / target.name
    outside.parent.mkdir()
    outside.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(outside)
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426, w.rows_root, w.repo)


# class: reproduces-failure (a symlink INSIDE rows_root to a file inside rows_root stays acceptable)
def test_fix05_symlink_inside_rows_root_is_fine(verify, make_w1):
    w = make_w1()
    target = w.path_of("cjudge", "on", "b1", "stdout")
    keep = target.with_name("stdout.real")
    keep.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(keep)
    assert V.accepted_all(verify.verify_wave1(w.p426, w.rows_root, w.repo))


# ================================================================================================= fix 6: A1 per-arm accuracy, both blocks
# class: reproduces-failure (A1 both blocks: per-arm strict accuracy over the 10 planned items, ON .9 and OFF .7, is in the `both` record)
def test_fix06_a1_both_blocks_per_arm_accuracy(pipe):
    rows = {("math500", "on", "b1"): {a(1): {"ok": False}}, ("math500", "off", "b2"): {a(i): {"ok": False} for i in (6, 7, 8)}}
    w, b8, sig = pipe(rows=rows)
    both = SV.subtree(V.axis_tree(sig, "A1"), "both")
    assert both, "A1 has a `both` record"
    pool = SV.numbers(both)
    assert V.has(pool, 0.9, 1e-4) and V.has(pool, 0.7, 1e-4), sorted(set(pool))[:40]


# ============================================================================================ fix 7: the family needs both A1 blocks
# class: reproduces-failure (b2 of A1 rejected: A1 is NOT a family member, the family is labelled incomplete (never "complete"), m < 3)
def test_fix07_family_incomplete_without_both_a1_blocks(pipe):
    w, b8, sig = pipe(legs={("math500", "on", "b2"): {"verdict": "INVALID", "problems": ["x"]}})
    fam = SV.text(SV.subtree(sig, "family")).lower()
    assert "incomplete" in fam, fam
    assert not V.has(SV.numbers(SV.subtree(sig, "family")), 3.0, 1e-9) or "incomplete" in fam


# ====================================================================================== fix 8: acceptance over all ON rows of a block
# class: reproduces-failure (one key rejected for a seed mismatch: its ON draft counters still count: b1 320 / 500 = .64, both 720 / 1000 = .72)
def test_fix08_acceptance_counts_key_rejected_rows(pipe):
    w, b8, sig = pipe(rows={("math500", "on", "b1"): {a(1): {"sampler_seed": 4242, "draft": D("on", 100, 0)}}})
    p = V.pair(b8, "math500", "b1")
    assert p["accepted"] and len(p["keys_rejected"]) == 1
    assert V.axis_has(sig, "A1", 0.64, 1e-4) and V.axis_has(sig, "A1", 0.72, 1e-4)
    assert V.axis_has(sig, "A1", 320.0, 1e-9) and V.axis_has(sig, "A1", 500.0, 1e-9)


# =========================================================================================== fix 9: bootstrap order is sorted (block, key)
# class: reproduces-failure (b2 ids 6..10 sort as 10, 6, 7, 8, 9: the CI of ratios 1.0 3.0 .5 2.0 1.0 differs from the plan order's)
def test_fix09_speed_bootstrap_uses_sorted_keys(pipe, signals):
    ratio = {6: 3.0, 7: 0.5, 8: 2.0, 9: 1.0, 10: 1.0}
    rows = {("math500", "on", "b2"): {a(i): {"decode_tps": 20.0 * r} for i, r in ratio.items()}}
    w, b8, sig = pipe(rows=rows)
    srt = [ratio[i] for i in (10, 6, 7, 8, 9)]
    plan = [ratio[i] for i in (6, 7, 8, 9, 10)]
    want, wrong = signals.geomean_ratio_ci(srt), signals.geomean_ratio_ci(plan)
    assert abs(want["hi"] - wrong["hi"]) > 0.05, "the fixture tells the two orders apart"
    pool = V.axis_pool(sig, "A1")
    assert V.has(pool, want["hi"], 1e-3) and not V.has(pool, wrong["hi"], 1e-3)
    both = signals.geomean_ratio_ci([1.5] * 5 + srt)
    assert V.has(pool, both["hi"], 1e-3) and V.has(pool, both["lo"], 1e-3)


# ================================================================================== fix 10: walls and identity from accepted pairs only
# class: reproduces-failure (a rejected A3 b1 pair contributes neither its leg walls (3000 / 3111 s) nor its identity count)
def test_fix10_rejected_pair_has_no_walls_or_identity(pipe):
    w, b8, sig = pipe(legs={("vision", "on", "b1"): {"verdict": "INVALID", "problems": ["x"]}})
    pool = V.axis_pool(sig, "A3")
    for kind_secs in (WW.wall_seconds("vision", "off", "b1"), WW.wall_seconds("vision", "on", "b1")):
        assert not any(abs(v - kind_secs) < 0.5 for v in pool), kind_secs
    assert any(abs(v - WW.wall_seconds("vision", "off", "b2")) < 0.5 for v in pool), "the accepted b2 wall is there"
    a3_ident = SV.text(V.axis_tree(SV.subtree(sig, "identity"), "A3"))
    assert '"b1"' not in a3_ident, a3_ident


# ============================================================================================================= fix 11: flags carry items
# class: reproduces-failure (every Wave 1 flag lists its keys / legs with both arms' values: acceptance, decode, M1, nonconv_kind)
@pytest.fixture(scope="module")
def Fw(scenario):
    return lambda: scenario("Ffix", **FL.F_SPEC)


def test_fix11_acceptance_flag_lists_keys_with_both_arms(Fw):
    _, _, sig = Fw()
    t = flag_of(sig, "A2-b1", "acceptance_below_0.70")
    assert all(k in t for k in ("dom-01", "dom-02", "pub-aaa")) and "off" in t and "on" in t, t


# class: reproduces-failure (decode-ratio flag: the b1 keys under 1.3 with the OFF and ON rates)
def test_fix11_decode_flag_lists_keys_with_both_arms(Fw):
    _, _, sig = Fw()
    t = flag_of(sig, "A1-b1", "decode_ratio_below_1.3")
    assert a(1).lower() in t and a(10).lower() in t and "off" in t and "on" in t, t


# class: reproduces-failure (M1 flag: the two legs)
def test_fix11_m1_flag_lists_both_legs(Fw):
    _, _, sig = Fw()
    t = flag_of(sig, "M1-b1", "m1_prefill_peak_over_off_plus_2gb")
    assert "m1-p426s2-on-b1" in t and "m1-p426s2-off-b1" in t, t


# class: reproduces-failure (nonconv_kind flags: the ON-only items, with the kind of each arm)
def test_fix11_nonconv_flags_list_the_items(Fw):
    _, _, sig = Fw()
    assert a(11).lower() in flag_of(sig, "A1-b2", "nonconv_kind_on_only")
    t = flag_of(sig, "A2-b2", "nonconv_kind_on_only")
    assert "dom-04" in t and "max_tokens" in t, t


# ================================================================================================================ fix 12: path masking
ABS_CASES = {
    "worker_argv": ("math500", "on", lambda w: w.set_flags("math500", "on", "b1", lambda fl: [(f, "/Users/zed/models/m" if f == "--model" else v)  # allow-pii-pattern
                                                                                         for f, v in fl]), "/Users/zed"),
    "m1_argv": ("m1", "on", lambda w: w.set_flags("m1", "on", "b1", lambda fl: [(f, "/home/zed/models/m" if f == "--model" else v)  # allow-pii-pattern
                                                                             for f, v in fl]), "/home/zed"),
    "home_relative": ("cjudge", "on", lambda w: w.set_flags("cjudge", "on", "b1", lambda fl: [(f, "~/secret/m" if f == "--model" else v)
                                                                                           for f, v in fl]), "~/secret"),
    "receipt_problem": ("vision", "on", lambda w: w.edit_receipt("vision", "on", "b1", lambda d: d.update(problems=["boom in /home/zed/work/x.py"])),  # allow-pii-pattern
                        "/home/zed"),
}


# class: reproduces-failure (a path in a mismatching argv / a receipt problem never reaches a rejection reason: it is masked to <path>)
@pytest.mark.parametrize("case", sorted(ABS_CASES))
def test_fix12_paths_in_reasons_are_masked(verify, make_w1, case):
    kind, _, mutate, leak = ABS_CASES[case]
    w = make_w1()
    mutate(w)
    b8 = verify.verify_wave1(w.p426, w.rows_root, w.repo)
    p = only_rejected(b8, kind, "b1")
    assert leak not in " | ".join(p["reasons"]) and leak not in json.dumps(b8), p["reasons"]
    assert "<path>" in " | ".join(p["reasons"])


# class: reproduces-failure (... and in the sheet: SIGNALS.json / SIGNALS.md carry no raw path from a rejection)
def test_fix12_paths_do_not_reach_the_sheet(verify, signals, make_w1):
    w = make_w1(with_a7=True)
    ABS_CASES["worker_argv"][2](w)
    b8 = verify.verify_all(w.p426, w.rows_root, w.repo)
    sig = signals.compute_all(w.p426, w.rows_root, b8)
    blob = json.dumps(sig, sort_keys=True, default=str)
    assert "/Users/zed" not in blob and "<path>" in blob


# ============================================================================================= fix 13: reasons name pair, rule, both values
# class: reproduces-failure (rule 2d sampling / kv, rule 2a pins: the reason names the pair (kind, block) and BOTH values)
@pytest.mark.parametrize("section,field,on,off", [("sampling", "temperature", 0.7, 0.5), ("kv", "max_kv_cache_size", 131072, 262144)])
def test_fix13_manifest_difference_names_both_values(verify, make_w1, section, field, on, off):
    w = make_w1()
    w.edit_json("math500", "on", "b2", "manifest", lambda d: d[section].update({field: on}))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), "math500", "b2")
    named(p, "rule 2", "math500", "b2", str(on), str(off))


# class: reproduces-failure (rule 2a: the differing pin values of both receipts and the frozen value are named)
def test_fix13_pins_difference_names_both_values(verify, make_w1):
    w = make_w1()
    w.edit_receipt("cjudge", "off", "b1", lambda d: d["pins"].update(mlx_vlm="ee" * 20))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), "cjudge", "b1")
    named(p, "rule 2", "cjudge", "b1", "ee" * 20, WW.GITLINKS["src/mlx-vlm"])


# class: reproduces-failure (rule 2d M1 served / snapshots: pair named, both values named)
def test_fix13_m1_served_difference_names_both_values(verify, make_w1):
    w = make_w1()
    w.edit_json("m1", "on", "b1", "result", lambda d: d["served"].update(session_max=2))
    p = only_rejected(verify.verify_wave1(w.p426, w.rows_root, w.repo), "m1", "b1")
    named(p, "rule 2", "m1", "b1", "session_max", "2", "1")


# ========================================================================================== fix 14: the S-build tune deny pattern
# class: reproduces-failure (a rows file that resolves to `math500.p426-on-b1.jsonl` (S build) with VALID planned ids refuses)
@pytest.mark.parametrize("arm", WW.ARMS)
def test_fix14_s_build_tune_with_valid_rows_refuses(verify, make_w1, arm):
    w = make_w1()
    rows = w.path_of("math500", arm, "b1", "rows")
    s_file = w.edir / f"math500.p426-{arm}-b1.jsonl"
    s_file.write_bytes(rows.read_bytes())
    rows.unlink()
    rows.symlink_to(s_file)
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426, w.rows_root, w.repo)


# ========================================================================================================== fix 15: render_md dispatch
# class: reproduces-failure (render_md accepts the `all` record and equals what the all command renders; the A7 record renders as in step 1)
def test_fix15_render_md_accepts_the_all_record(pipe, signals):
    w, b8, sig = pipe()
    md = signals.render_md(sig)
    assert isinstance(md, str) and "p613-step2" in md and md.endswith("\n")
    a7 = signals.compute_a7(w.p426, b8["axes"]["A7"])
    md7 = signals.render_md(a7)
    assert "p613-step1" in md7 and "PROVISIONAL — A7 only" in md7 and "p613-step2" not in md7


# ============================================================================================================ fix 16: one key shape per axis
# class: reproduces-failure (a rejected key has the same 3-element shape as an accepted key, for every kind)
@pytest.mark.parametrize("kind,field", [("math500", "sampler_seed"), ("cjudge", "sampler_seed"), ("vision", "seed"), ("reasoning", "sampler_seed")])
def test_fix16_rejected_key_shape_equals_accepted_shape(verify, make_w1, kind, field):
    w = make_w1()
    name = "block1"
    first = w.ids[kind][name][0]
    w.edit_rows(kind, "on", "b1", lambda rows: [r.update({field: 4242}) for r in rows if r.get("id", r.get("seed")) == first])
    p = V.pair(verify.verify_wave1(w.p426, w.rows_root, w.repo), kind, "b1")
    assert len(p["keys_rejected"]) == 1 and p["keys"], p
    rk, ak = p["keys_rejected"][0]["key"], p["keys"][0]["key"]
    assert len(rk) == len(ak) == 3 and rk[1] == first, (rk, ak)
    assert isinstance(rk[2], int)


# ======================================================================================================================= G1 / G2
# class: reproduces-failure (G1: a rejected A7 session under `all`: no crash, the family is labelled incomplete, the session is reported rejected)
def test_g1_rejected_a7_session_under_all(verify, signals, make_w1):
    w = make_w1(with_a7=True)
    w.a7.edit_leg("on", "s1", state="INVALID")
    b8 = verify.verify_all(w.p426, w.rows_root, w.repo)
    assert [p["accepted"] for p in b8["axes"]["A7"]["pairs"] if p.get("pair") == "s1"] == [False]
    sig = signals.compute_all(w.p426, w.rows_root, b8)
    fam = SV.text(SV.subtree(sig, "family")).lower()
    assert "incomplete" in fam and "complete" != fam
    blob = V.sheet_text(sig).lower()
    assert "rejected" in blob and "a7-s2" in blob


# class: reproduces-failure (G2: one rejected Wave 1 block, the other accepted: no crash; flags only for the accepted block; the section says rejected)
def test_g2_one_rejected_wave1_block_flags_the_other(pipe):
    rows = {("cjudge", "on", "b2"): {k: {"draft": D("on", 100, 40)} for k in ("dom-03", "dom-04", "pub-bbb")}}
    legs = {("cjudge", "on", "b1"): {"verdict": "INVALID", "problems": ["x"]}}
    w, b8, sig = pipe(rows=rows, legs=legs)
    assert [(p["kind"], V.digit(p["block"])) for p in V.rejected(b8)] == [("cjudge", "1")]
    members = {d.get("member") for d in flag_dicts(sig)}
    assert "A2-b2" in members and "A2-b1" not in members
    assert "rejected" in V.axis_text(sig, "A2").lower()
