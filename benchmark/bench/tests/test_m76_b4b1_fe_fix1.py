"""M76 B4b-1 fix round 1 (change review rows L1-L6, `candidate/change-review-ledger-report.md`): one behaviour test per adopted
disposition, written from the ledger, independent of the implementer's tests. Class of each test: (a) red on candidate 1,
(b) green on candidate 1 (a guard of behaviour the fix must not break), (c) new behaviour of a widened surface."""
from __future__ import annotations

import io
import contextlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench.tests import test_m76_b4b1_fe_support as S
from bench.tests.test_m76_b4b1_fe_chain import MODEL, _argv, prefix
from bench.tests.test_m76_b4b1_fe_wave2 import _planned, harvested, strict

DATE = "Sat Oct 17 2026"


# ------------------------------------------------------------------------------------------------ L1
def _iv():
    from m62 import inject_verify
    return inject_verify


def _v2_row(tmp_path, *, toolwindows=False):
    """A real-shaped v2 inject row: the artifacts `OpencodeArm.row_fields` records (events / export / stderr / datefreeze, plus
    toolwindows when present), each path present with its sha256, and the grade reports of the recorded real rust/say grade."""
    from bench import arm_runner
    files = {"events": ("x.events.jsonl", "events_path"), "export": ("x.json", "transcript_path"),
             "stderr": ("x.stderr.txt", "stderr_path"), "datefreeze": ("x.datefreeze.jsonl", "datefreeze_path")}
    if toolwindows:
        files["toolwindows"] = ("x.toolwindows.jsonl", "toolwindows_path")
    row = dict(id="rust/say", test_modified=False, scaffold=S.SCAFFOLD + "-inject:stall", evidence_sha256={})
    for name, (fname, field) in files.items():
        path = tmp_path / fname
        path.write_text('{"k": "%s"}\n' % name)
        row[field] = str(path)
        row["evidence_sha256"][name] = S.sha256_file(path)
    reports = arm_runner.grade_reports(S.grades_dir("rust", "reference"))
    row["grade_reports"] = [dict(r, boundary=0) for r in reports]
    return row


def _files(row, workdir, scaffold="opencode-v2-web-tg2"):
    return _iv().check_files(row, {}, workdir, scaffold=scaffold)


# (a) a real-shaped date-frozen tg2 row verifies (candidate 1: `FAIL:evidence_sha256_keys` on every real tg2 positive)
@pytest.mark.parametrize("toolwindows", [False, True])
def test_l1_real_shaped_v2_row_verifies(tmp_path, toolwindows):
    assert _files(_v2_row(tmp_path, toolwindows=toolwindows), tmp_path) is None


def _mut_missing_key(row):
    row["evidence_sha256"].pop("datefreeze")


def _mut_extra_key(row):
    row["evidence_sha256"]["bogus"] = "a" * 64


def _mut_bad_sha(row):
    row["evidence_sha256"]["datefreeze"] = "0" * 64


def _mut_toolwindows_key_without_path(row):
    row["evidence_sha256"]["toolwindows"] = "a" * 64


def _mut_toolwindows_path_without_key(row):
    row.pop("toolwindows_path", None)
    row["toolwindows_path"] = row["datefreeze_path"]


def _mut_no_datefreeze_at_all(row):
    row.pop("datefreeze_path")
    row["evidence_sha256"].pop("datefreeze")


def _mut_datefreeze_file_gone(row):
    Path(row["datefreeze_path"]).unlink()


MUTANTS = [(_mut_missing_key, "FAIL:evidence_sha256_keys"), (_mut_extra_key, "FAIL:evidence_sha256_keys"),
           (_mut_bad_sha, "FAIL:evidence_sha:datefreeze"), (_mut_toolwindows_key_without_path, "FAIL:evidence_sha256_keys"),
           (_mut_toolwindows_path_without_key, "FAIL:evidence_sha256_keys"),
           (_mut_no_datefreeze_at_all, "FAIL:evidence_sha256_keys"), (_mut_datefreeze_file_gone, "FAIL:evidence_sha:datefreeze")]


# (a) a missing / extra / mismatched key fails (red on candidate 1 in the sense that the unmutated row fails there with the
# same verdict; the mutants pin that the fix did not loosen the check)
@pytest.mark.parametrize("mutate,want", MUTANTS, ids=[m.__name__ for m, _ in MUTANTS])
def test_l1_a_missing_extra_or_mismatched_key_fails(tmp_path, mutate, want):
    row = _v2_row(tmp_path, toolwindows=mutate not in (_mut_toolwindows_key_without_path, _mut_toolwindows_path_without_key))
    mutate(row)
    assert _files(row, tmp_path) == want


# (b) tg1's three-key row (no date-freeze recorded) is checked as before
def test_l1_tg1_three_key_row_unchanged(tmp_path):
    row = _v2_row(tmp_path)
    row.pop("datefreeze_path")
    row["evidence_sha256"].pop("datefreeze")
    assert _files(row, tmp_path, scaffold="opencode-v2-web-tg1") is None
    row["evidence_sha256"]["bogus"] = "a" * 64
    assert _files(row, tmp_path, scaffold="opencode-v2-web-tg1") == "FAIL:evidence_sha256_keys"


# (c) WIDENING (implementer deviation 1): a tg1 row that records `datefreeze_path` with a matching digest now verifies
# (candidate 1: FAIL:evidence_sha256_keys). The real tg1 probe writes exactly such rows (`row_fields`), so this is the intended
# repair; a tg1 row with a datefreeze path but no key (or a bad digest) still fails
def test_l1_tg1_row_with_recorded_datefreeze(tmp_path):
    row = _v2_row(tmp_path)
    assert _files(row, tmp_path, scaffold="opencode-v2-web-tg1") is None
    row["evidence_sha256"].pop("datefreeze")
    assert _files(row, tmp_path, scaffold="opencode-v2-web-tg1") == "FAIL:evidence_sha256_keys"
    row = _v2_row(tmp_path)
    row["evidence_sha256"]["datefreeze"] = "0" * 64
    assert _files(row, tmp_path, scaffold="opencode-v2-web-tg1") == "FAIL:evidence_sha:datefreeze"


# ------------------------------------------------------------------------------------------------ L2
def _corpus_at(root, sha=S.POLYGLOT_SHA):
    from bench import corpus_tg2
    c = corpus_tg2.Tg2Corpus(S.UNIVERSE_PATH, polyglot_root=root, polyglot_sha=lambda r: sha)
    c.load_universe()
    return c


def _copy_exercise(tmp_path, lang="rust", slug="say"):
    root = tmp_path / "polyglot"
    src = S.polyglot() / lang / "exercises/practice" / slug
    shutil.copytree(src, root / lang / "exercises/practice" / slug)
    return root


# (b) a checkout of the pinned sha and unchanged inputs prepares (a guard: the refusals below are not blanket)
def test_l2_an_unchanged_copy_prepares(tmp_path):
    root = _copy_exercise(tmp_path)
    prepared = _corpus_at(root).prepare("rust/say", tmp_path / "work")
    assert prepared.item_id == "rust/say"


# (a) a drifted checkout sha refuses before anything is materialised
@pytest.mark.parametrize("sha", ["1" * 40, None, ""])
def test_l2_a_drifted_checkout_sha_refuses_before_materialisation(tmp_path, sha):
    from bench.token_turn_gate import TransportAbort
    root = _copy_exercise(tmp_path)
    dest = tmp_path / "work"
    with pytest.raises(TransportAbort):
        _corpus_at(root, sha).prepare("rust/say", dest)
    assert not dest.exists()


# (a) a drifted item `inputs_sha256` (the instructions changed under the pinned sha) refuses before materialisation
def test_l2_a_drifted_item_input_refuses_before_materialisation(tmp_path):
    from bench.token_turn_gate import TransportAbort
    root = _copy_exercise(tmp_path)
    docs = root / "rust/exercises/practice/say/.docs/instructions.md"
    docs.write_text(docs.read_text() + "\nA different task.\n")
    dest = tmp_path / "work"
    with pytest.raises(TransportAbort):
        _corpus_at(root).prepare("rust/say", dest)
    assert not dest.exists()


# (a) ... and before the prompt: a prepared item of the real checkout, a corpus whose checkout drifted afterwards
def test_l2_a_drifted_checkout_never_produces_a_prompt(tmp_path):
    from bench.token_turn_gate import TransportAbort
    prepared = S.make_corpus().prepare("rust/say", tmp_path / "work")
    root = _copy_exercise(tmp_path)
    docs = root / "rust/exercises/practice/say/.docs/instructions.md"
    docs.write_text(docs.read_text() + "\nA different task.\n")
    with pytest.raises(TransportAbort):
        _corpus_at(root).prompt(prepared)
    with pytest.raises(TransportAbort):
        _corpus_at(root, "2" * 40).prompt(prepared)


# (b) identity-only callers still work without a checkout check (the implementer's deviation 2: load_universe stays checkout-free)
def test_l2_identity_without_a_checkout(tmp_path):
    from bench import corpus_tg2
    c = corpus_tg2.Tg2Corpus(S.UNIVERSE_PATH, polyglot_root=tmp_path / "nowhere", polyglot_sha=lambda r: "3" * 40)
    assert c.identity()["universe_sha256"] == S.TG2_UNIVERSE_SHA256


# ------------------------------------------------------------------------------------------------ L3
def _recheck_modules():
    from bench import p426_hooks as ph, p426_wave2 as W
    return W, ph


class _Ops:
    def __init__(self, roots):
        self.roots = roots

    def harvest_path(self, attempt):
        return self.roots[attempt]

    def publish_run_files(self, paths, *, emails):
        pass


def _roots(tmp_path, n16_fail, x_fail):
    items = _planned("s1")
    out = {}
    for arm, fails in (("n16", n16_fail), ("x", x_fail)):
        (tmp_path / arm).mkdir(exist_ok=True)
        out[f"tg2-m76-{arm}-s1.a1"] = harvested(tmp_path / arm, "s1", {i: (False, True) for i in fails}, name=f"tg2-m76-{arm}-s1.a1")
    return out


def _inside_sets():
    items = _planned("s1")
    n16_fail = set(items[40:])
    x_fail = (n16_fail | set(items[0:8])) - set(items[40:48])
    return n16_fail, x_fail


def _sequencer(tmp_path, roots, ack=None):
    W, _ = _recheck_modules()
    a = SimpleNamespace(cmd="run", lever="kv", corpus="tg2", arms=("n16", "x"), worktrees={"n16": tmp_path, "x": tmp_path},
                        out_base=str(tmp_path / "ob"), pause_file=None, record_dir=str(tmp_path / "ob" / "run"), rerun=[],
                        rerun_reason=None, through=None, recheck_ack=ack,
                        recheck_ack_by="operator" if ack else None, recheck_ack_ruling="test ruling" if ack else None)   # S29 K2
    seq = W.Sequencer(a, _Ops(roots), lambda: 0.0, lambda s: None, tmp_path)
    for arm in ("n16", "x"):
        seq.seq["legs"].append(dict(leg=f"tg2-m76-{arm}-s1", attempt=1, state="VALID"))
        seq.seq["harvested"].append(dict(attempt=f"tg2-m76-{arm}-s1.a1", harvest_sha256="h"))
    return seq


def _no_rerun(monkeypatch):
    from bench import m76_sim

    def boom(*a, **k):
        raise AssertionError("the re-check was computed again")
    monkeypatch.setattr(m76_sim, "recheck", boom)


# (b) state 0 — neither file nor record: computed, sealed, recorded; a second call re-verifies (never re-runs)
def test_l3_state_neither_computes_once(tmp_path, monkeypatch):
    W, ph = _recheck_modules()
    roots = _roots(tmp_path, *_inside_sets())
    _sequencer(tmp_path, roots).ensure_recheck("s1")
    path = tmp_path / "ob" / "run" / "recheck-s1.json"
    doc = json.loads(path.read_text())
    assert ph.sealed_ok(doc) and W.read_sequence(tmp_path / "ob")["rechecks"]["s1"]["sha256"] == doc["sha256"]
    _no_rerun(monkeypatch)
    _sequencer(tmp_path, roots).ensure_recheck("s1")


# (a) state 1 — a record without its sealed file: Stop rc 1, never re-run, the record untouched, no file recreated
def test_l3_state_record_without_file_stops(tmp_path, monkeypatch):
    W, _ = _recheck_modules()
    roots = _roots(tmp_path, *_inside_sets())
    _sequencer(tmp_path, roots).ensure_recheck("s1")
    path = tmp_path / "ob" / "run" / "recheck-s1.json"
    before = W.read_sequence(tmp_path / "ob")["rechecks"]["s1"]
    path.unlink()
    _no_rerun(monkeypatch)
    with pytest.raises(W.Stop) as stop:
        _sequencer(tmp_path, roots).ensure_recheck("s1")
    assert stop.value.rc == 1 and not path.exists()
    assert W.read_sequence(tmp_path / "ob")["rechecks"]["s1"] == before


def _crash_window(tmp_path, n16_fail, x_fail):
    """The crash between the seal and the save: the sealed file exists, `sequence.json` has no record of it."""
    W, _ = _recheck_modules()
    roots = _roots(tmp_path, n16_fail, x_fail)
    try:
        _sequencer(tmp_path, roots).ensure_recheck("s1")
    except W.Stop:
        pass
    doc = W.read_sequence(tmp_path / "ob")
    rec = doc["rechecks"].pop("s1")
    W.write_sequence(tmp_path / "ob", doc)
    return roots, rec


# (a) state 2 — a sealed-OK file without a record: re-verified and recorded from the file (inside: continues), not re-run
def test_l3_state_file_without_record_is_recorded_from_the_file(tmp_path, monkeypatch):
    W, _ = _recheck_modules()
    roots, rec = _crash_window(tmp_path, *_inside_sets())
    _no_rerun(monkeypatch)
    _sequencer(tmp_path, roots).ensure_recheck("s1")
    got = W.read_sequence(tmp_path / "ob")["rechecks"]["s1"]
    assert got["sha256"] == rec["sha256"] and got["inside"] is True


# (a) ... and an OUTSIDE one still stops rc 5 until the ack of that sha256
def test_l3_state_file_without_record_outside_still_needs_the_ack(tmp_path, monkeypatch):
    W, _ = _recheck_modules()
    items = _planned("s1")
    roots, rec = _crash_window(tmp_path, set(items), set(items))
    _no_rerun(monkeypatch)
    with pytest.raises(W.Stop) as stop:
        _sequencer(tmp_path, roots).ensure_recheck("s1")
    assert stop.value.rc == 5
    _sequencer(tmp_path, roots, ack=rec["sha256"]).ensure_recheck("s1")


# (b) a file that does not verify (changed after sealing), with or without a record, stops rc 1 and never re-runs
@pytest.mark.parametrize("with_record", [True, False])
def test_l3_a_changed_sealed_file_stops(tmp_path, monkeypatch, with_record):
    W, _ = _recheck_modules()
    if with_record:
        roots = _roots(tmp_path, *_inside_sets())
        _sequencer(tmp_path, roots).ensure_recheck("s1")
    else:
        roots, _ = _crash_window(tmp_path, *_inside_sets())
    path = tmp_path / "ob" / "run" / "recheck-s1.json"
    doc = json.loads(path.read_text())
    doc["recheck"]["inside"] = not doc["recheck"]["inside"]
    path.write_text(json.dumps(doc))
    _no_rerun(monkeypatch)
    with pytest.raises(W.Stop) as stop:
        _sequencer(tmp_path, roots).ensure_recheck("s1")
    assert stop.value.rc == 1


# (c) the implementer's extra check: a sealed-OK file of ANOTHER selection (different attempts) is not adopted
def test_l3_a_sealed_file_of_another_selection_is_not_adopted(tmp_path, monkeypatch):
    W, ph = _recheck_modules()
    roots, rec = _crash_window(tmp_path, *_inside_sets())
    path = tmp_path / "ob" / "run" / "recheck-s1.json"
    doc = json.loads(path.read_text())
    doc.pop("sha256")
    doc["attempts"] = {"tg2-m76-n16-s1": "tg2-m76-n16-s1.a9", "tg2-m76-x-s1": "tg2-m76-x-s1.a9"} \
        if isinstance(doc.get("attempts"), dict) else ["other.a9"]
    path.write_text(json.dumps(ph.seal(doc)))
    _no_rerun(monkeypatch)
    with pytest.raises(W.Stop) as stop:
        _sequencer(tmp_path, roots).ensure_recheck("s1")
    assert stop.value.rc == 1


# ------------------------------------------------------------------------------------------------ L4
def _s1_root(tmp_path, outcomes=None):
    return harvested(tmp_path, "s1", outcomes or {})


# (a) a stray row (restored refusal test)
def test_l4_a_stray_row_refuses(tmp_path):
    root = _s1_root(tmp_path)
    path = next((root / "s1").glob("*opencode_rust*.jsonl"))
    path.write_text(path.read_text() + json.dumps(dict(id="rust/not-planned", sampler_seed=1001, passed=True, converged=True)) + "\n")
    with pytest.raises(Exception):
        strict([root], "s1")


# (a) a stray DNF record of this session
def test_l4_a_stray_dnf_refuses(tmp_path):
    root = _s1_root(tmp_path)
    chain = json.loads((root / "chain.json").read_text())
    chain["p426_dnf"].append(dict(session="s1", language="rust", item="not-planned", slot="x", abort=dict(cause="transport")))
    (root / "chain.json").write_text(json.dumps(chain))
    with pytest.raises(Exception):
        strict([root], "s1")


# (a) a slot with both a row and a DNF record
def test_l4_a_row_and_dnf_overlap_refuses(tmp_path):
    root = _s1_root(tmp_path)
    item = _planned("s1")[3]
    lang, name = item.split("/", 1)
    chain = json.loads((root / "chain.json").read_text())
    chain["p426_dnf"].append(dict(session="s1", language=lang, item=name, slot="x", abort=dict(cause="transport")))
    (root / "chain.json").write_text(json.dumps(chain))
    with pytest.raises(Exception):
        strict([root], "s1")


# (b) a DNF record of ANOTHER session is not this session's (no stray, no overlap); the plain case still scores
def test_l4_other_sessions_dnf_is_ignored_and_the_plain_case_scores(tmp_path):
    root = _s1_root(tmp_path)
    chain = json.loads((root / "chain.json").read_text())
    chain["p426_dnf"].append(dict(session="s2", language="rust", item="not-planned", slot="x", abort=dict(cause="transport")))
    (root / "chain.json").write_text(json.dumps(chain))
    got = strict([root], "s1")
    assert len(got) == 80 and all(v == {"s1": 1} for v in got.values())


# ------------------------------------------------------------------------------------------------ L5 / L6
KV_N16_X = ["--lever", "kv", "--pair", "n16,x", "--arm-worktree", "n16=/w/n16", "--arm-worktree", "x=/w/x"]


def _stub_ops():
    f = lambda *a, **k: {}      # noqa: E731
    return SimpleNamespace(wd="/nonexistent-wd", worktree_state=f, identity=f, build_inputs=f, historical_walls=f)


def _freeze_main(argv):
    from bench import p426_freeze as fz
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        rc = fz.main(argv, ops=_stub_ops())
    return rc, err.getvalue()


_V8 = ["v8", "--corpus", "tg2", "--rehearsal-manifest", "M", "--r2", "L2", "--r3", "L3", "--positives", "P", "--out", "v8.json"]


# (a) tg2 v8 refuses `--r1-off` / `--r1-on` ("no R1"), saying so
@pytest.mark.parametrize("flag", ["--r1-off", "--r1-on"])
def test_l5_tg2_v8_refuses_the_r1_flags(flag):
    rc, err = _freeze_main(["v8", *KV_N16_X, *_V8[1:], flag, "L1"])
    assert rc == 2 and "r1" in err.lower()


# (b) without them the same command line is not refused for R1 (it is refused later, for its missing files)
def test_l5_the_same_command_without_them_is_not_refused_for_r1():
    rc, err = _freeze_main(["v8", *KV_N16_X, *_V8[1:]])
    assert "r1" not in err.lower()


@pytest.mark.parametrize("pair", ["n16,v", "x,v", "v,x", "x,n16"])
def test_l6_freeze_entry_points_refuse_a_pair_other_than_n16_x(pair):
    ref, test = pair.split(",")
    kv = ["--lever", "kv", "--pair", pair, "--arm-worktree", f"{ref}=/w/a", "--arm-worktree", f"{test}=/w/b"]
    for argv in (["rehearsal", *kv, "--corpus", "tg2", "--frozen-prompt-date", DATE, "--out-root", "/r", "--out", "m.json"],
                 ["v8", *kv, *_V8[1:]]):
        rc, err = _freeze_main(argv)
        assert rc == 2 and "n16" in err, (argv[0], err[-200:])


@pytest.mark.parametrize("pair", [("n16", "v"), ("x", "v"), ("v", "x"), ("x", "n16")])
def test_l6_leg_table_refuses_a_pair_other_than_n16_x(pair):
    from bench import p426_wave2 as W
    with pytest.raises(ValueError):
        W.kv_tg2_legs(*pair)
    assert [l["name"] for l in W.kv_tg2_legs("n16", "x")["run"]][0] == "tg2-m76-n16-pilot"


@pytest.mark.parametrize("arm", ["x", "v"])
def test_l6_positives_refuse_a_reference_arm_other_than_n16(arm, tmp_path):
    from bench import p426_wave2 as W
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("a seam was reached"))   # noqa: E731
    ops = SimpleNamespace(wd=tmp_path, worktree_state=boom, identity=boom, positives_session=boom, positive_grade=boom,
                          positive_inject=boom, inject_verify=boom)
    out = tmp_path / "positives.json"
    rc = W.main(["positives", "--corpus", "tg2", "--lever", "kv", "--arm-worktree", f"{arm}={tmp_path}", "--out", str(out),
                 "--frozen-prompt-date", DATE], ops=ops)
    assert rc == 2 and not out.exists()


@pytest.mark.parametrize("pair", ["n16,v", "x,v", "x,n16"])
def test_l6_sequencer_refuses_a_pair_other_than_n16_x(pair, tmp_path):
    from bench import p426_wave2 as W
    ref, test = pair.split(",")
    rc = W.main(["run", "--corpus", "tg2", "--lever", "kv", "--pair", pair, "--arm-worktree", f"{ref}={tmp_path}",
                 "--arm-worktree", f"{test}={tmp_path}", "--out-base", str(tmp_path / "m76/p426/wave2.tg2/ob"), "--record-dir",
                 str(tmp_path / "run")], ops=SimpleNamespace(wd=tmp_path))
    assert rc == 2


# (a) the tg2 chain entry refuses arm v, and a frozen record of another pair
def test_l6_chain_entry_refuses_arm_v(capsys):
    with pytest.raises(SystemExit) as exc:
        S.chain_entry().parse_args(_argv("--leg", "pilot", arm="v", out="tg2-m76-v-pilot.a1"))
    assert exc.value.code == 2


@pytest.mark.parametrize("arms", [["n16", "v"], ["x", "n16"], ["x", "v"]])
def test_l6_chain_entry_refuses_a_record_of_another_pair(arms, tmp_path):
    from bench import p426_freeze as fz, p426_hooks as ph
    R = S.chain_entry()
    a = R.parse_args(_argv("--leg", "pilot"))
    path = tmp_path / "v8_base.json"
    ph.write_exclusive(path, dict(kind=fz.KIND_V8, lever="kv", arms=arms, corpus="tg2"))
    a.frozen_record = str(path)
    with pytest.raises(SystemExit) as exc:                  # `chain_core.Refused` is a SystemExit (rc 2)
        R.check_frozen_record(a)
    assert exc.value.code in (2, None) or "REFUSED" in str(exc.value)


def test_l6_chain_entry_accepts_the_n16_x_record(tmp_path):
    from bench import p426_freeze as fz, p426_hooks as ph
    R = S.chain_entry()
    a = R.parse_args(_argv("--leg", "pilot"))
    path = tmp_path / "v8_base.json"
    ph.write_exclusive(path, dict(kind=fz.KIND_V8, lever="kv", arms=["n16", "x"], corpus="tg2"))
    a.frozen_record = str(path)
    assert R.check_frozen_record(a)["base"]["arms"] == ["n16", "x"]


# ------------------------------------------------------------------------------------------------ delivery 4: V1 / V2
def _with_rerun(tmp_path, roots, arm):
    """The recorded re-check's selection changes: `arm`'s s1 leg is rerun, attempt 2 is VALID and harvested."""
    items = _planned("s1")
    (tmp_path / f"{arm}-a2").mkdir()
    roots = dict(roots)
    roots[f"tg2-m76-{arm}-s1.a2"] = harvested(tmp_path / f"{arm}-a2", "s1", {}, name=f"tg2-m76-{arm}-s1.a2")
    seq = _sequencer(tmp_path, roots)
    seq.seq["legs"].append(dict(leg=f"tg2-m76-{arm}-s1", attempt=2, state="VALID"))
    seq.seq["harvested"].append(dict(attempt=f"tg2-m76-{arm}-s1.a2", harvest_sha256="h"))
    return seq


# (a) V1: a recorded sealed re-check whose selection (attempts) is no longer the current one stops rc 1; nothing re-runs, the
# record and the sealed file are untouched — for the rerun of either arm
@pytest.mark.parametrize("arm", ["n16", "x"])
def test_v1_a_recorded_recheck_of_another_selection_stops(tmp_path, monkeypatch, arm):
    W, _ = _recheck_modules()
    roots = _roots(tmp_path, *_inside_sets())
    _sequencer(tmp_path, roots).ensure_recheck("s1")
    path = tmp_path / "ob" / "run" / "recheck-s1.json"
    sealed, rec = path.read_bytes(), W.read_sequence(tmp_path / "ob")["rechecks"]["s1"]
    _no_rerun(monkeypatch)
    seq = _with_rerun(tmp_path, roots, arm)
    with pytest.raises(W.Stop) as stop:
        seq.ensure_recheck("s1")
    assert stop.value.rc == 1
    assert path.read_bytes() == sealed and W.read_sequence(tmp_path / "ob")["rechecks"]["s1"] == rec


# (a) V1 without the record (the crash window) behaves the same
@pytest.mark.parametrize("arm", ["n16", "x"])
def test_v1_a_sealed_recheck_without_record_of_another_selection_stops(tmp_path, monkeypatch, arm):
    W, _ = _recheck_modules()
    roots, _ = _crash_window(tmp_path, *_inside_sets())
    _no_rerun(monkeypatch)
    with pytest.raises(W.Stop) as stop:
        _with_rerun(tmp_path, roots, arm).ensure_recheck("s1")
    assert stop.value.rc == 1
    assert "s1" not in W.read_sequence(tmp_path / "ob").get("rechecks", {})


# (b) the current selection still resumes (recorded, and ack'd outside), re-verifying only
def test_v1_the_current_selection_resumes(tmp_path, monkeypatch):
    roots = _roots(tmp_path, *_inside_sets())
    _sequencer(tmp_path, roots).ensure_recheck("s1")
    _no_rerun(monkeypatch)
    _sequencer(tmp_path, roots).ensure_recheck("s1")


# (a) V2: the same item bytes under ANOTHER checkout sha: the prompt refuses (candidate 2 checked only the inputs here)
def test_v2_the_prompt_refuses_another_checkout_sha_on_the_same_bytes(tmp_path):
    from bench.token_turn_gate import TransportAbort
    prepared = S.make_corpus().prepare("rust/say", tmp_path / "work")
    ok = _corpus_at(S.polyglot())
    assert ok.prompt(prepared)                                   # same bytes, the pinned sha: fine
    with pytest.raises(TransportAbort):
        _corpus_at(S.polyglot(), "4" * 40).prompt(prepared)
