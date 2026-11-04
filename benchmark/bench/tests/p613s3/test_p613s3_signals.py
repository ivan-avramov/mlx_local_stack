"""`p426_signals all --panel <dir>`: the §4.5 subjective section on hand-computed verdict fixtures.

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.

World (module-scoped, no rejected key): A7 s1 has 6 packet items, s2 8; Wave 1 pairs are all C217-identical (as in the committed
data). Verdicts are written by the test (sealed shape), 4 per item in the order (claude AB, claude BA, cursor AB, cursor BA).

Scenarios (hand computation; the permutation p is a 10,000-draw Monte-Carlo of the exact sign-flip test, so each is compared to the
EXACT enumeration within a Monte-Carlo tolerance; Holm is exact algebra):

* S1  s1 per-item scores {1, .875, .5, .5, .625, 1} -> minus .5 = {.5, .375, 0, 0, .125, .5}; exact p = 2/16 = .125.
      s2 eight items, every verdict OFF -> score 0 each; exact p = 2/256 = .0078125. Holm m = 2: s2 adj = 2 x p_s2 (< .05, favours
      OFF -> flag), s1 adj = max(adj_s2, p_s1) = p_s1.
* S2  s1 as S1; s2 every verdict ON -> same p, favours ON: no flag.
* S3  gaps: s1 loses one verdict of `python/alpha` (judged 5; scores {.875,.5,.5,.625,1}; exact p = 2/8 = .25; missing 1, excluded 1);
      s2 loses one verdict of each of four items (judged 4 < 5: reported, not tested; missing 4, excluded 4) -> m = 1, Holm p = raw p.

Readings tested: see sigview.py (JSON key names are searched, not fixed); the sheet text strings quoted in the contract.
"""
from __future__ import annotations

import itertools
import json
import shutil

import pytest

from bench.tests.p613s3 import s3world as S
from bench.tests.p613s3 import sigview as V


def exact_p(diffs):
    d = [x for x in diffs]
    t = abs(sum(d))
    hits = sum(1 for signs in itertools.product((-1, 1), repeat=len(d)) if abs(sum(s * x for s, x in zip(signs, d))) >= t - 1e-12)
    return hits / 2 ** len(d)


@pytest.fixture(scope="module")
def case(tmp_path_factory):
    return S.A7Case(tmp_path_factory.mktemp("sigcase"), with_rejected=False)


def build(case, tmp_path_factory, name, plan, panel, **kw):
    out = tmp_path_factory.mktemp(name) / "panel"
    proc = case.export(out)
    assert proc.returncode == 0, proc.stderr
    V.write_verdicts(out, plan, panel, **kw)
    return out


@pytest.fixture(scope="module")
def panel_mod():
    import importlib
    return importlib.import_module("bench.p426_panel")


@pytest.fixture(scope="module")
def s1(case, tmp_path_factory, panel_mod):
    out = build(case, tmp_path_factory, "s1", {**V.PLAN_S1, **V.PLAN_S2_OFF}, panel_mod)
    runs = []
    for i in range(2):
        proc, md, js = V.run_all(case, tmp_path_factory.mktemp(f"s1out{i}"), out)
        assert proc.returncode == 0, proc.stderr
        runs.append((md, js))
    return case, out, runs


@pytest.fixture(scope="module")
def s2(case, tmp_path_factory, panel_mod):
    out = build(case, tmp_path_factory, "s2", {**V.PLAN_S1, **V.PLAN_S2_ON}, panel_mod)
    proc, md, js = V.run_all(case, tmp_path_factory.mktemp("s2out"), out)
    assert proc.returncode == 0, proc.stderr
    return md, js


@pytest.fixture(scope="module")
def s3(case, tmp_path_factory, panel_mod):
    drop = {("python/alpha", V.CLA, "AB")} | {(r, V.CUR, "BA") for r in S.S2_SEL[:4]}
    out = build(case, tmp_path_factory, "s3", {**V.PLAN_S1, **V.PLAN_S2_OFF}, panel_mod, drop=drop)
    proc, md, js = V.run_all(case, tmp_path_factory.mktemp("s3out"), out)
    assert proc.returncode == 0, proc.stderr
    return md, js


# ------------------------------------------------------------------------------------------------------------------ S1
# class: new-behaviour (status line: no longer "subjective panel pending"; the sheet is final-review pending)
def test_status_line(s1):
    _, _, runs = s1
    md, js = runs[0]
    sig = V.load(js)
    assert sig["header"]["status"] == V.STATUS
    assert md.read_text().splitlines()[0] == f"# P426 signals — {V.STATUS}"
    assert "subjective panel pending" not in md.read_text()


# class: new-behaviour (the pending list no longer promises the panel)
def test_pending_no_longer_lists_the_panel(s1):
    sig = V.load(s1[2][0][1])
    pending = sig["pending"]
    assert not any("subjective" in k and "step 3" in str(v) for k, v in pending.items())
    assert "final sheet + recommendation" in pending


# class: new-behaviour (raw per-item scores: mean over judges x orders, ON win 1 / tie .5 / OFF win 0, from the verdict choices)
def test_raw_item_scores_s1(s1):
    m = V.member(V.load(s1[2][0][1]), "A7-s1")
    got = V.item_scores(m, S.S1_SEL)
    assert got == pytest.approx(V.SCORES_S1, abs=1e-12)


# class: new-behaviour (s2 all OFF: every item scores 0)
def test_raw_item_scores_s2_all_off(s1):
    m = V.member(V.load(s1[2][0][1]), "A7-s2")
    assert V.item_scores(m, S.S2_SEL) == pytest.approx({r: 0.0 for r in S.S2_SEL}, abs=1e-12)


# class: new-behaviour (judged n, raw mean, permutation p vs the exact enumeration, on score - .5)
def test_permutation_p_s1(s1):
    m = V.member(V.load(s1[2][0][1]), "A7-s1")
    assert V.judged_n(m) == 6
    assert V.field(m, "raw") == pytest.approx(0.75, abs=1e-9)
    want = exact_p([V.SCORES_S1[r] - 0.5 for r in S.S1_SEL])
    assert want == 0.125
    assert V.raw_p(m) == pytest.approx(want, abs=0.02)


# class: new-behaviour (s2: eight items all -.5 -> exact p 2/256; Monte-Carlo (1 + hits) / 10001)
def test_permutation_p_s2(s1):
    m = V.member(V.load(s1[2][0][1]), "A7-s2")
    assert V.judged_n(m) == 8
    assert V.raw_p(m) == pytest.approx(exact_p([-0.5] * 8), abs=0.004)
    assert abs(V.raw_p(m) * 10001 - round(V.raw_p(m) * 10001)) < 1e-6          # p = (1 + hits) / 10,001


# class: new-behaviour (the family: the tested members only, m fixed by the < 5 rule = 2; Holm algebra exact)
def test_family_and_holm_s1(s1):
    sig = V.load(s1[2][0][1])
    fam = V.family(sig)
    assert sorted(fam["tested"]) == ["A7-s1", "A7-s2"] and fam["m"] == 2          # R4: `members` is the whole family
    p1, p2 = V.raw_p(V.member(sig, "A7-s1")), V.raw_p(V.member(sig, "A7-s2"))
    h1, h2 = V.holm_p(V.member(sig, "A7-s1")), V.holm_p(V.member(sig, "A7-s2"))
    assert h2 == pytest.approx(min(1.0, 2 * p2), abs=1e-12)
    assert h1 == pytest.approx(min(1.0, max(h2, p1)), abs=1e-12)
    assert h2 < 0.05 < h1


# class: new-behaviour (headline: the length-adjusted P(ON preferred at equal length), beside the raw mean)
def test_length_adjusted_headline(s1):
    sig = V.load(s1[2][0][1])
    m1, m2 = V.member(sig, "A7-s1"), V.member(sig, "A7-s2")
    a1, a2 = V.field(m1, "adjusted"), V.field(m2, "adjusted")
    assert 0.5 < a1 < 1.0 and 0.0 <= a2 < 0.2
    ci = V.field(m1, "ci")
    assert len(ci) == 2 and ci[0] <= a1 <= ci[1]
    assert V.field(m1, "n_items", "n_clusters") == 6 or V.judged_n(m1) == 6


# class: new-behaviour (flag: a tested member with Holm p < .05 favouring OFF is flagged with its number; s1 is not)
def test_flag_raised_for_s2_off(s1):
    sig = V.load(s1[2][0][1])
    flags = V.subjective_flags(sig)
    assert len(flags) == 1 and "A7-s2" in flags[0]["text"] and "A7-s1" not in flags[0]["text"]
    assert "A7-s2" in s1[2][0][0].read_text().split("## Flags")[1]


# class: new-behaviour (every member is labelled "conditional on both-pass", with n and the one-arm-pass count left out)
def test_conditional_on_both_pass_and_one_arm_left_out(s1):
    sig = V.load(s1[2][0][1])
    md = s1[2][0][0].read_text()
    assert "conditional on both-pass" in md
    assert V.one_arm_left_out(V.member(sig, "A7-s1")) == 2 and V.one_arm_left_out(V.member(sig, "A7-s2")) == 1
    assert "conditional on both-pass" in json.dumps(V.member(sig, "A7-s1")).lower() or "conditional" in json.dumps(V.member(sig, "A7-s1"))


# class: new-behaviour (Wave 1 members: identical outputs score .5, judged 0, reported not tested)
@pytest.mark.parametrize("name", ["A1", "A2", "A3"])
def test_wave1_members_identical_not_run(s1, name):
    sig = V.load(s1[2][0][1])
    m = V.member(sig, name)
    assert V.judged_n(m) == 0
    assert V.field(m, "score_identical", "raw", "score", "mean_score") == 0.5
    assert "identical outputs; panel not run" in json.dumps(m)
    assert name not in V.family(sig)["tested"]
    md = s1[2][0][0].read_text()
    assert "identical outputs; panel not run" in md and "reported, not tested" in md


# class: new-behaviour (A4: descriptive, never tested -- not a family member)
def test_a4_is_never_tested(s1):
    sig = V.load(s1[2][0][1])
    assert "A4" not in V.family(sig)["tested"]


# class: new-behaviour (per-verdict provenance: judge model ids, client versions, prompt sha, families)
def test_provenance_summary(s1, panel_mod):
    sig = V.load(s1[2][0][1])
    text = json.dumps(V.member(sig, "A7-s1")) + json.dumps(V.subjective(sig))
    for needle in ("claude-opus-5-5", "gpt-5.6-sol-high", "2.3.4", "9.9.9-fake", panel_mod.rubric_sha("code"),
                   "anthropic", "openai"):
        assert needle in text, needle


# class: invariant (the mechanical sections and the mechanical family are unchanged by the panel)
def test_mechanical_family_unchanged(s1):
    sig = V.load(s1[2][0][1])
    assert sig["family"]["m"] == 3 and sig["family"]["label"] == "complete"
    assert sorted(sig["family"]["members"]) == ["A1", "A7-s1", "A7-s2"]


# class: new-behaviour (byte-identical regeneration from the same inputs)
def test_regeneration_is_byte_identical(s1):
    (md1, js1), (md2, js2) = s1[2]
    assert md1.read_bytes() == md2.read_bytes() and js1.read_bytes() == js2.read_bytes()


# class: invariant (no absolute path in the outputs)
def test_outputs_have_no_absolute_path(s1):
    case, out, runs = s1
    for f in runs[0]:
        text = f.read_text()
        for needle in (str(case.base), str(out), "/Users/", "/private/", "/var/folders"):
            assert needle not in text, (needle, f.name)


# ------------------------------------------------------------------------------------------------------------------ S2
# class: new-behaviour (favours ON: the same p and Holm p, no subjective flag)
def test_flag_not_raised_when_on_is_favoured(s2):
    sig = V.load(s2[1])
    m = V.member(sig, "A7-s2")
    assert V.item_scores(m, S.S2_SEL) == pytest.approx({r: 1.0 for r in S.S2_SEL}, abs=1e-12)
    assert V.holm_p(m) < 0.05
    assert V.subjective_flags(sig) == []


# ------------------------------------------------------------------------------------------------------------------ S3
# class: new-behaviour (a missing verdict excludes the item and is counted; s1 still has 5 judged items and is tested)
def test_missing_verdict_counted_and_item_excluded(s3):
    sig = V.load(s3[1])
    m = V.member(sig, "A7-s1")
    assert V.judged_n(m) == 5
    assert V.count(V.field(m, "missing", "n_missing", "missing_verdicts")) == 1
    assert V.count(V.field(m, "excluded", "n_excluded", "excluded_items")) == 1
    got = V.item_scores(m, [r for r in S.S1_SEL if r != "python/alpha"])
    assert got == pytest.approx({r: v for r, v in V.SCORES_S1.items() if r != "python/alpha"}, abs=1e-12)
    want = exact_p([V.SCORES_S1[r] - 0.5 for r in S.S1_SEL if r != "python/alpha"])
    assert want == 0.25
    assert V.raw_p(m) == pytest.approx(want, abs=0.03)


# class: new-behaviour (< 5 judged items: reported, not tested; m = 1 fixed by that rule; Holm p of the one tested member = its raw p)
def test_fewer_than_five_judged_items_is_not_tested(s3):
    sig = V.load(s3[1])
    m = V.member(sig, "A7-s2")
    assert V.judged_n(m) == 4
    assert V.count(V.field(m, "missing", "n_missing", "missing_verdicts")) == 4
    assert V.count(V.field(m, "excluded", "n_excluded", "excluded_items")) == 4
    assert V.field(m, "permutation_p", "raw_p", "p", default=None) is None
    fam = V.family(sig)
    assert fam["tested"] == ["A7-s1"] and fam["m"] == 1
    m1 = V.member(sig, "A7-s1")
    assert V.holm_p(m1) == V.raw_p(m1)
    assert V.subjective_flags(sig) == []
    assert "not tested" in s3[0].read_text()


# class: new-behaviour (the sheet shows the missing / excluded counts)
def test_sheet_shows_missing_counts(s3):
    md = s3[0].read_text()
    assert "missing" in md.lower()


# ------------------------------------------------------------------------------------------------------------ refusals
def refused(proc, md, js):
    assert proc.returncode != 0 and proc.stderr.strip()
    assert not md.exists() and not js.exists()


# class: new-behaviour (E1: `--panel` is OPTIONAL; absent -> the step-2 record, rc 0, status "subjective panel pending (step 3)")
def test_panel_option_is_optional(case, tmp_path):
    proc, md, js = V.run_all(case, tmp_path, None, with_panel=False)
    assert proc.returncode == 0, proc.stderr
    sig = V.load(js)
    assert sig["header"]["status"] == "PROVISIONAL — subjective panel pending (step 3)"
    assert sig["header"]["generator_version"] == "p613-step2"
    assert not [k for k in sig if "subjective" in k.lower()]
    assert "4.5 subjective" in sig["pending"]
    assert md.read_text().splitlines()[0] == "# P426 signals — PROVISIONAL — subjective panel pending (step 3)"


# class: new-behaviour (a panel directory without FROZEN.json refuses: rc 2 + REFUSED, nothing written)
def test_missing_frozen_json_refuses(case, tmp_path, panel_mod):
    out = tmp_path / "panel"
    assert case.export(out).returncode == 0
    (out / "FROZEN.json").unlink()
    proc, md, js = V.run_all(case, tmp_path / "o", out)
    refused(proc, md, js)
    assert proc.returncode == 2 and "REFUSED" in proc.stderr


# class: new-behaviour (a packet changed after the freeze refuses the sheet: verdicts are never ingested against it)
def test_changed_packet_refuses_the_sheet(case, tmp_path, panel_mod):
    out = tmp_path / "panel"
    assert case.export(out).returncode == 0
    V.write_verdicts(out, {**V.PLAN_S1, **V.PLAN_S2_OFF}, panel_mod)
    p = S.packets_of(out)[0]
    p.write_text(p.read_text() + "\nchanged\n")
    proc, md, js = V.run_all(case, tmp_path / "o", out)
    refused(proc, md, js)
    assert proc.returncode == 2 and "REFUSED" in proc.stderr


# class: new-behaviour (a verdict bound to another packet sha is unbound: never admitted -> the item is excluded, not scored)
def test_unbound_verdict_is_not_admitted(case, tmp_path, panel_mod):
    out = tmp_path / "panel"
    assert case.export(out).returncode == 0
    V.write_verdicts(out, {**V.PLAN_S1, **V.PLAN_S2_OFF}, panel_mod, unbound={("go/zeta", V.CUR, "AB")})
    proc, md, js = V.run_all(case, tmp_path / "o", out)
    assert proc.returncode == 0, proc.stderr
    m = V.member(V.load(js), "A7-s1")
    assert V.judged_n(m) == 5
    assert "go/zeta" not in json.dumps(V.field(m, "scores", "items", "per_item", default={}))


# class: new-behaviour (B8.json changed since the freeze: the frozen packet set no longer matches the record -> refusal)
def test_b8_changed_since_freeze_refuses(case, tmp_path, panel_mod):
    out = tmp_path / "panel"
    assert case.export(out).returncode == 0
    V.write_verdicts(out, {**V.PLAN_S1, **V.PLAN_S2_OFF}, panel_mod)
    other = tmp_path / "B8.json"
    other.write_text(case.b8_path.read_text() + "\n")
    proc, md, js = V.run_all(case, tmp_path / "o", out, b8=other)
    S.refused_cli(proc)
    assert not md.exists()
    shutil.rmtree(tmp_path / "o", ignore_errors=True)
