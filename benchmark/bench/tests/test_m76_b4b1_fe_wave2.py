"""M76 B4b-1 (spec v5 §3 "Strict rows", "Re-checks", §4 "Harvest", the freeze / positives / dossier surface): `tg2_strict_rows` over
harvested tg2 legs, the nuisance re-check on its output, the harvest rules on the RECORDED real `tg2_grade` trees, the sealed run
records, the freeze / positives command line and the per-corpus dossier pairs. No box: files only. Class of each test is in the
comment above it: (a) reproduces a failure the spec fixes, (b) preserves an invariant, (c) new behaviour.
Name guesses: `test_m76_b4b1_fe_support.GUESSES`."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.tests import test_m76_b4b1_fe_support as S
from bench.tests.test_m76_b4b1_fe_chain import MODEL, TABLE, build, prefix

# ------------------------------------------------------------------------------------------------ strict rows
LANG_ORDER = {"s1": TABLE["s1"][2], "s2": TABLE["s2"][2]}


def _planned(session):
    return [i for lang in LANG_ORDER[session] for i in prefix(lang, 20)]


def _row(item, passed, converged, seed):
    return dict(id=item, sampler_seed=seed, passed=passed, converged=converged, nonconv_kind=None if converged else "budget_hit")


def harvested(tmp_path, session, outcomes, name=None):
    """A harvested tg2 attempt root (the leg-root layout `p426_harvest` publishes): `schedule.json`, `chain.json` (with its
    `schedule_sha256`, DNF records) and the session's rows files. `outcomes`: {item: (passed, converged) | "dnf" | "missing"};
    absent items default to a strict pass."""
    from bench import schedules
    root = tmp_path / (name or "tg2-m76-n16-%s.a1" % session)
    (root / session).mkdir(parents=True)
    sched = build(session)
    (root / "schedule.json").write_text(json.dumps(sched))
    seed = TABLE[session][1]
    rows, dnf = [], []
    for item in _planned(session):
        o = outcomes.get(item, (True, True))
        lang, name_ = item.split("/", 1)
        if o == "dnf":
            dnf.append(dict(session=session, language=lang, item=name_, slot="tg2-p426|n16|%s|%s|%s|%s" % (MODEL, session, lang, name_),
                            abort=dict(cause="transport")))
        elif o != "missing":
            rows.append(_row(item, o[0], o[1], seed))
    for lang in LANG_ORDER[session]:
        mine = [r for r in rows if r["id"].startswith(lang + "/")]
        (root / session / ("%s.%s.opencode_%s.L0.full.a1.jsonl" % (MODEL, session, lang))).write_text(
            "".join(json.dumps(r) + "\n" for r in mine))
    (root / "chain.json").write_text(json.dumps(dict(schedule_sha256=schedules.schedule_sha256(sched), p426_dnf=dnf, status="finished")))
    return root


def strict(roots, session):
    from bench import p426_wave2
    return S.attr(p426_wave2, "tg2_strict_rows", "strict-rows")(roots, session)


# (c) 1 iff `passed is True and converged is True`: every other combination (incl. None) is 0; the shape is {item: {session: 0/1}}
@pytest.mark.parametrize("session", ["s1", "s2"])
def test_strict_rows_scoring_and_shape(session, tmp_path):
    items = _planned(session)
    outcomes = {items[0]: (True, False), items[1]: (False, True), items[2]: (False, False), items[3]: (None, True),
                items[4]: (True, None)}
    got = strict([harvested(tmp_path, session, outcomes)], session)
    assert set(got) == set(items) and all(v in ({session: 0}, {session: 1}) for v in got.values())
    assert [got[i][session] for i in items[:5]] == [0, 0, 0, 0, 0]
    assert all(got[i][session] == 1 for i in items[5:])


# (c) a `p426_dnf` slot is a strict fail (0) and the item is still present
def test_strict_rows_dnf_slot_is_zero(tmp_path):
    item = _planned("s1")[7]
    got = strict([harvested(tmp_path, "s1", {item: "dnf"})], "s1")
    assert got[item] == {"s1": 0} and len(got) == 80


# (c) a planned slot with neither a row nor a DNF record refuses (the failure path)
def test_strict_rows_missing_slot_refuses(tmp_path):
    item = _planned("s1")[7]
    with pytest.raises(Exception):
        strict([harvested(tmp_path, "s1", {item: "missing"})], "s1")


# (c) AMENDED (delivery 2): the spec names one refusal (a planned slot with neither row nor DNF); a row outside the planned slots is
# not a planned slot and must not enter the result (the answer is keyed by the frozen plan); a duplicate row refuses
def test_strict_rows_ignores_a_stray_row_and_refuses_a_duplicate(tmp_path):
    root = harvested(tmp_path, "s1", {})
    path = next((root / "s1").glob("*opencode_rust*.jsonl"))
    first = path.read_text().splitlines()[0]
    path.write_text(path.read_text() + json.dumps(_row("rust/not-planned", True, True, 1001)) + "\n")
    with pytest.raises(Exception):                 # delivery 3 (ledger L4): the refusal of delivery 1 is restored
        strict([root], "s1")
    path.write_text("\n".join(path.read_text().splitlines()[:-1]) + "\n" + first + "\n")
    with pytest.raises(Exception):
        strict([root], "s1")


# (c) the two arms' strict rows feed the nuisance re-check (`m76_sim.recheck("A8", n16, x)`): the verdict is a function of rows
def _rows(tmp_path, n16_fail, x_fail, tag):
    for arm in ("a", "b"):
        (tmp_path / (arm + tag)).mkdir()
    a = strict([harvested(tmp_path / ("a" + tag), "s1", {i: (False, True) for i in n16_fail})], "s1")
    b = strict([harvested(tmp_path / ("b" + tag), "s1", {i: (False, True) for i in x_fail}, name="tg2-m76-x-s1.a1")], "s1")
    return a, b


def _recheck(tmp_path, n16_fail, x_fail, tag):
    from bench import m76_sim
    a, b = _rows(tmp_path, n16_fail, x_fail, tag)
    return m76_sim.recheck("A8", a, b, out=tmp_path / ("out" + tag))


def test_recheck_inside_on_mid_rate_rows(tmp_path):
    items = _planned("s1")
    n16_fail = set(items[40:])                              # pass rate 0.5
    x_fail = (n16_fail | set(items[0:8])) - set(items[40:48])          # 8 lose, 8 gain: 16 discordant of 80, D = 0.2
    rec = _recheck(tmp_path, n16_fail, x_fail, "i")
    assert rec["inside"] is True and rec["operator_review"] is False and rec["observed_unrealisable"] is False
    assert (tmp_path / "outi" / "recheck-A8.json").is_file()


def test_recheck_unrealisable_when_nobody_passes(tmp_path):
    items = _planned("s1")
    rec = _recheck(tmp_path, set(items), set(items), "u")
    assert rec["inside"] is False and rec["observed_unrealisable"] is True and rec["operator_review"] is True
    assert rec["recalibration_attempted"] is False and rec["alpha_star_applied"] == rec["committed_alpha_star"]


def test_recheck_outside_the_grid(tmp_path):
    items = _planned("s1")
    n16_fail = set(items[76:])                              # pass rate 0.95 > the grid's 0.9
    x_fail = n16_fail | set(items[0:8])
    rec = _recheck(tmp_path, n16_fail, x_fail, "o")
    assert rec["inside"] is False and rec["outside_reasons"]
    assert rec["operator_review"] == (rec["unsafe_on_extended_grid"] or rec["observed_unrealisable"])


# ------------------------------------------------------------------------------------------------ harvest rules
GRADE_FILE_SUFFIXES = (".out", ".err", ".stdout", ".stderr", ".inspect", ".inspect.err")


def _variant_files(lang, variant):
    base = S.tree_dir(lang, variant)
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file() and p.name != "result.json")


# (c) H5: every file of the recorded real grade-sequence directories is classified; the host-written outputs (`*.out` ... `*.inspect.err`)
# go to evidence; nothing else in a grade directory is left unclassified
@pytest.mark.parametrize("lang,variant", [(l, v) for l in S.LANGS for v in ("reference", "stub", "compile", "tampered")] +
                         [("rust", "alloc"), ("rust", "flood"), ("rust", "spin")])
def test_every_recorded_grade_file_is_classified(lang, variant):
    from bench import p426_harvest as H
    unclassified, wrong, seen = [], [], 0
    for rel in _variant_files(lang, variant):
        if "/seq-" in rel and rel.split("/")[0].endswith(".grades"):
            seen += 1
            got = H.classify("evidence", rel)
            if got is None:
                unclassified.append(rel)
            elif rel.endswith(GRADE_FILE_SUFFIXES) and got[0] != "evidence":
                wrong.append(rel)
        elif rel.startswith("grading-private/"):
            seen += 1
            if H.classify("run", rel) is None:
                unclassified.append(rel)
    assert seen, "no recorded files walked"
    assert not unclassified, unclassified[:10]
    assert not wrong, wrong[:10]


# (a) the baseline's evidence rules know no `*.out` / `*.err` / `*.stdout` / `*.stderr` / `*.inspect` file (only go.stderr and the
# json / log / txt / html / xml suffixes): a tg2 grade directory would fail the harvest
def test_grade_sequence_streams_are_evidence_and_only_there():
    from bench import p426_harvest as H
    base = "rust__say.grades/seq-0001/"
    for name in ("execute.stdout", "execute.stderr", "holder.out", "holder.err", "execute.inspect", "execute.inspect.err",
                 "setup-launch-pre.out", "cl-mlxbench-tg2-0123456789ab-w.err"):
        assert H.classify("evidence", base + name) == ("evidence", None), name
    for rel in ("holder.out", "seq-0001/holder.out", "rust__say.grades/holder.out", "rust__say.grades/seq-0001/sub/holder.out",
                "rust__say.grades/seq-1/holder.out", "rust__say/seq-0001/holder.out", "rust__say.grades/seq-0001/holder.bin",
                "rust__say.grades/seq-0001/holder.out/extra"):
        assert H.classify("evidence", rel) is None, rel
    assert H.classify("leg", "s1/holder.out") is None and H.classify("run", "holder.out") is None


# (b) tg1's go.stderr rule and the old evidence suffixes are untouched
def test_tg1_evidence_rules_unchanged():
    from bench import p426_harvest as H
    assert H.classify("evidence", "go__x.grades/seq-0001/go.stderr") == ("evidence", None)
    assert H.classify("evidence", "go__x.grades/go.stderr") is None
    assert H.classify("evidence", "items/x.json") == ("evidence", None) and H.classify("evidence", "x.xml") == ("evidence", None)
    assert H.classify("evidence", "x.out") is None


# (c) `grading-private/.tg2-registry/*.json` is evidence, ahead of the generic `.json` -> main rule; other grading-private json stays main
def test_tg2_registry_json_is_evidence():
    from bench import p426_harvest as H
    assert H.classify("run", "grading-private/.tg2-registry/mlxbench-tg2-0123456789ab.json") == ("evidence", None)
    assert H.classify("run", "grading-private/result.json") == ("main", None)


# (b) `positives.json` / `recheck-s{1,2}.json` are run records, not classified files: nothing new in the run table
def test_run_records_are_published_not_classified():
    from bench import p426_harvest as H
    for name in ("positives.json", "recheck-s1.json", "recheck-s2.json"):
        assert H.classify("run", name) is None


def _scrub(tmp_path):
    from bench import p426_harvest as H
    return H.Scrub(workdir=tmp_path / "wd", repo=tmp_path / "repo", home=tmp_path / "home", user="someuser", hosts=("somehost",))


# (c) the sealed run records are published to `<main>/benchmark/results/m76/wave2.tg2/run/`; an unsealed record is refused; a
# changed record at the same name is refused (published records are immutable)
@pytest.mark.parametrize("name", ["positives.json", "recheck-s1.json", "recheck-s2.json"])
def test_sealed_run_records_publish_under_wave2_tg2(name, tmp_path):
    from bench import p426_harvest as H, p426_hooks as ph
    src = tmp_path / "run"
    src.mkdir()
    doc = ph.seal(dict(kind="record", name=name, items=[1, 2, 3]))
    (src / name).write_text(json.dumps(doc))
    main = tmp_path / "main"
    out = H.publish_run_files_kv([src / name], main_root=main, scrub=_scrub(tmp_path), namespace="wave2.tg2")
    dest = main / "benchmark/results/m76/wave2.tg2/run" / name
    assert dest.read_bytes() == (src / name).read_bytes() and out["published"][0]["destination"].endswith("wave2.tg2/run/" + name)
    (src / name).write_text(json.dumps(ph.seal(dict(kind="record", name=name, items=[9]))))
    with pytest.raises(H.HarvestError):
        H.publish_run_files_kv([src / name], main_root=main, scrub=_scrub(tmp_path), namespace="wave2.tg2")


def test_an_unsealed_run_record_is_refused(tmp_path):
    from bench import p426_harvest as H
    (tmp_path / "positives.json").write_text(json.dumps(dict(kind="record", items=[1])))
    with pytest.raises(H.HarvestError):
        H.publish_run_files_kv([tmp_path / "positives.json"], main_root=tmp_path / "main", scrub=_scrub(tmp_path), namespace="wave2.tg2")


def test_namespace_wave2_tg2_is_accepted():
    from bench import p426_harvest as H
    assert H.namespace_root("wave2.tg2", "kv").as_posix() == "benchmark/results/m76/wave2.tg2"
    with pytest.raises(H.HarvestError):
        H.namespace_root("wave3.tg2", "kv")


# ------------------------------------------------------------------------------------------------ the freeze / positives surface
KV = ["--lever", "kv", "--pair", "n16,x", "--arm-worktree", "n16=/w/n16", "--arm-worktree", "x=/w/x"]


def _fz_parse(argv):
    from bench import p426_freeze as fz
    return fz.parse_args(argv)


# (c) `--corpus tg2` on rehearsal / v8 / amend; an unknown corpus is refused
def test_freeze_rehearsal_takes_corpus_tg2():
    from bench import p426_freeze as fz
    a = _fz_parse(["rehearsal", *KV, "--corpus", "tg2", "--frozen-prompt-date", "Sat Oct 17 2026", "--out-root", "/r", "--out", "m.json"])
    assert a.corpus == "tg2" and tuple(a.arms) == ("n16", "x")
    with pytest.raises(fz.Refusal):
        _fz_parse(["rehearsal", *KV, "--corpus", "bogus", "--frozen-prompt-date", "Sat Oct 17 2026", "--out-root", "/r", "--out", "m.json"])


# (c) v8 for tg2: no R1 flags (the pilot pair takes R1's role), `--positives P` is required
def test_freeze_v8_for_tg2_needs_positives_and_no_r1():
    from bench import p426_freeze as fz
    base = ["v8", *KV, "--corpus", "tg2", "--rehearsal-manifest", "M", "--r2", "L2", "--r3", "L3", "--out", "v8_base.json"]
    a = _fz_parse([*base, "--positives", "P"])
    assert a.corpus == "tg2" and a.positives == "P"
    # AMENDED (delivery 2): the candidate refuses a missing `--positives` / `--r1-*` in the command (rc 2, `REFUSED:`), not in argparse
    assert "--positives" in _v8_refusal(base)


def _v8_refusal(argv):
    """`p426_freeze.main(argv)` with a minimal ops: the REFUSED text (rc must be 2)."""
    import io
    import contextlib
    from types import SimpleNamespace
    from bench import p426_freeze as fz
    ops = SimpleNamespace(wd="/nonexistent-wd", worktree_state=lambda *a, **k: {}, identity=lambda *a, **k: {},
                          build_inputs=lambda *a, **k: {}, historical_walls=lambda *a, **k: {})
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        rc = fz.main(argv, ops=ops)
    assert rc == 2, err.getvalue()
    return err.getvalue()


# (b) tg1's v8 still needs R1 and takes no positives
def test_freeze_v8_tg1_unchanged():
    a = _fz_parse(["v8", *KV, "--rehearsal-manifest", "M", "--r1-off", "a", "--r1-on", "b", "--r2", "L2", "--r3", "L3", "--out", "v.json"])
    assert a.r1_off == "a"
    assert "--r1-off" in _v8_refusal(["v8", *KV, "--rehearsal-manifest", "M", "--r2", "L2", "--r3", "L3", "--out", "v.json"])


def test_freeze_amend_takes_corpus_tg2():
    a = _fz_parse(["amend", "--v8", "v", "--pilot-off", "a", "--pilot-on", "b", "--out", "o", "--corpus", "tg2"])
    assert a.corpus == "tg2"


# (c) `pilot_gate_problems(..., leg_name=, n=)`: the tg2 pilot is `tg2-m76-<arm>-pilot` with n = 4 reconciled rows each
def test_pilot_gate_takes_leg_name_and_n(tmp_path):
    import inspect
    from bench import p426_freeze as fz
    params = inspect.signature(fz.pilot_gate_problems).parameters
    assert "leg_name" in params and "n" in params
    problems = fz.pilot_gate_problems(tmp_path / "a", tmp_path / "b", ("n16", "x"), leg_name=lambda arm: "tg2-m76-%s-pilot" % arm, n=4)
    assert problems and any("pilot" in p for p in problems)


def test_wave2_positives_command_line():
    from bench import p426_freeze as fz, p426_wave2 as W
    argv = ["positives", "--corpus", "tg2", "--arm-worktree", "n16=/w/n16", "--out", "positives.json", "--frozen-prompt-date",
            "Sat Oct 17 2026", "--out-base", "/o"]
    try:
        a = W.parse_args(argv)
    except fz.Refusal as exc:
        assert str(exc).startswith("the following arguments are required"), str(exc)
        return
    assert a.cmd == "positives" and a.corpus == "tg2" and a.out == "positives.json"


def test_wave2_run_takes_recheck_ack():
    from bench import p426_freeze as fz, p426_wave2 as W
    base = ["run", "--lever", "kv", "--pair", "n16,x", "--arm-worktree", "n16=/a", "--arm-worktree", "x=/b", "--out-base", "/o",
            "--record-dir", "/r", "--corpus", "tg2"]
    try:
        a = W.parse_args([*base, "--recheck-ack", "a" * 64])
    except fz.Refusal as exc:
        pytest.fail(f"SPELLING GUESS freeze-flags: `run ... --corpus tg2 --recheck-ack <sha>` was refused: {exc}", pytrace=False)
    assert a.recheck_ack == "a" * 64


# ------------------------------------------------------------------------------------------------ dossier pairs per corpus
def _dossier(tmp_path, pair, corpus):
    from bench import p426_receipt as pr
    arms = {}
    for arm in ("n16", "x"):
        (tmp_path / arm).mkdir(exist_ok=True)
        (tmp_path / arm / "receipt.json").write_text("{}")
        (tmp_path / arm / "HARVEST.json").write_text("{}")
        arms[arm] = dict(attempt="leg-%s.a1" % arm, receipt=tmp_path / arm / "receipt.json", harvest=tmp_path / arm / "HARVEST.json")
    path = tmp_path / ("%s__n16-a1__x-a1.json" % pair)
    extra = {} if corpus is None else dict(corpus=corpus)
    try:
        return pr.write_kv_dossier(path, pair=pair, ref="n16", test="x", arms=arms, differences=[], verdict="FAIL", **extra)
    except TypeError as exc:
        pytest.fail(f"SPELLING GUESS dossier-corpus: write_kv_dossier(..., corpus=) ({exc})", pytrace=False)


# (c) tg2 pairs: pilot, s1, s2, reload; r1, makeup and s3 are refused for tg2; tg1 keeps all of them
@pytest.mark.parametrize("pair", ["pilot", "s1", "s2", "reload"])
def test_tg2_dossier_pairs_accepted(pair, tmp_path):
    assert _dossier(tmp_path, pair, "tg2")["pair"] == pair


@pytest.mark.parametrize("pair", ["r1", "makeup", "s3"])
def test_tg2_dossier_pairs_refused(pair, tmp_path):
    with pytest.raises(ValueError):
        _dossier(tmp_path, pair, "tg2")


@pytest.mark.parametrize("pair", ["r1", "pilot", "s1", "s2", "reload", "makeup", "s3"])
def test_tg1_dossier_pairs_unchanged(pair, tmp_path):
    assert _dossier(tmp_path, pair, None)["pair"] == pair
