"""P371 phase 1: `bench.chain_rows` (plan 4 A8 / A9, R6 R7 R18 R19 R24 R25): the chain-row loader at the record level."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from bench import chain_rows as cr

REPO = Path(__file__).resolve().parents[3]
BASE = "e1|oc|PICK|s1|python"                 # epoch|arm|pick|session|lang (the M64 slot prefix)
STEM = "PICK.s1.oc_python"


def slot(item, base=BASE):
    return cr.slot_for(base, f"python/{item}")


def row(item, **kw):
    return dict(id=f"python/{item}", passed=True, **kw)


class Chain:
    """A chain.json progress document plus the rows files it names, under `root`."""

    def __init__(self, tmp):
        self.root = tmp / "out"
        self.doc = dict(progress=dict(loads=[], invocations=[], slot_attempts=[], pre_spawn=[]), dnf=[])
        self.n = 0

    def inv(self, rows_items, *, phase="full", attempt=1, status="validated", expected=None, accepted=None, leg=0,
            load_gen=0, rerun_index=None, hook_stop=None, write=True, base=BASE, session="s1", stem=STEM,
            rows=None, sha=True):
        rows = [row(i) for i in rows_items] if rows is None else rows
        rel = f"{session}/{cr.rows_name(stem, leg, phase, attempt)}"
        path = self.root / rel
        sha256 = None
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("".join(json.dumps(r) + "\n" for r in rows))
            sha256 = hashlib.sha256(path.read_bytes()).hexdigest() if sha else None
        got = [slot(r["id"].split("/", 1)[1], base) for r in rows]
        rec = dict(leg_key=[0, "python", leg], phase=phase, attempt=attempt, worker_n=0, file=rel,
                   manifest=rel[:-len(".jsonl")] + ".manifest.json", status=status,
                   expected_slots=got if expected is None else [slot(i, base) for i in expected],
                   accepted_slots=got if accepted is None else [slot(i, base) for i in accepted],
                   sha256=sha256, load_gen=load_gen, slot_base=base)
        if rerun_index is not None:
            rec["rerun_index"] = rerun_index
        if hook_stop is not None:
            rec["hook_stop"] = hook_stop
        self.doc["progress"]["invocations"].append(rec)
        return rec

    def attempt(self, item, rerun_index, disposition, tokens=None, **kw):
        rec = dict(slot=slot(item), rerun_index=rerun_index, disposition=disposition, load_gen=0)
        if tokens is not None:
            rec["output_tokens"] = tokens
        rec.update(kw)
        self.doc["progress"]["slot_attempts"].append(rec)

    def load(self, **kw):
        return cr.load_slots(self.doc, self.root, **kw)


@pytest.fixture
def chain(tmp_path):
    return Chain(tmp_path)


def scored(table):
    return sorted(table.scored)


# ---------------------------------------------------------------- naming and shapes
def test_leg_attempt_file_names():
    assert cr.rows_name("PICK.s1.oc_python", 3, "pilot", 2) == "PICK.s1.oc_python.L3.pilot.a2.jsonl"
    assert cr.manifest_name("PICK.s1.oc_python", 3, "full", 1) == "PICK.s1.oc_python.L3.full.a1.manifest.json"
    assert cr.PHASES == ("pilot", "full", "block", "rerun", "retry")
    assert cr.COUNTED_STATUSES == ("validated", "partial_incident", "hook_stopped")
    for bad in (("s", -1, "pilot", 1), ("s", 0, "bogus", 1), ("s", 0, "pilot", 0)):
        with pytest.raises(ValueError):
            cr.rows_name(*bad)


def test_slot_for_is_the_m64_slot_key():
    from importlib import util
    spec = util.spec_from_file_location("m64chain_p371", REPO / "benchmark/chains/m64/run_m64_chain.py")
    sys.path[:0] = [str(REPO / "benchmark"), str(REPO / "benchmark/chains/c147")]
    mod = util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert cr.slot_for("e|oc|P|s1|python", "python/foo") == mod.slot_key("e", "oc", "P", "s1", "python", "foo")


def test_a_progress_document_with_a_malformed_record_is_refused(chain):
    rec = chain.inv(["a"])
    for mutate in (lambda r: r.pop("sha256"), lambda r: r.update(status="done"), lambda r: r.update(phase="x"),
                   lambda r: r.update(load_gen=-1), lambda r: r.update(accepted_slots="a"),
                   lambda r: r.update(expected_slots=[]), lambda r: r.update(attempt=0)):
        doc = copy.deepcopy(chain.doc)
        mutate(doc["progress"]["invocations"][0])
        with pytest.raises(cr.ChainRowsError):
            cr.load_slots(doc, chain.root)
    doc = copy.deepcopy(chain.doc)
    doc["progress"]["slot_attempts"].append(dict(slot=slot("a"), rerun_index=0, disposition="weird", load_gen=0))
    with pytest.raises(cr.ChainRowsError):
        cr.load_slots(doc, chain.root)
    with pytest.raises(cr.ChainRowsError):
        cr.load_slots({}, chain.root)
    assert rec["status"] == "validated"


# ---------------------------------------------------------------- pilot / full: disjoint invocations
def test_pilot_then_full_each_slot_once_and_the_full_never_reruns_the_pilot(chain):
    chain.inv(["a", "b"], phase="pilot")
    chain.inv(["c", "d", "e"], phase="full")
    t = chain.load()
    assert scored(t) == sorted(slot(i) for i in "abcde")
    assert all(s.disposition == "accepted" and not s.strict_fail and s.source == "row" for s in t.scored.values())
    assert t.cell_complete([slot(i) for i in "abcde"]) and not t.cell_complete([slot(i) for i in "abcdef"])
    assert t.unscored([slot(i) for i in "abcdef"]) == [slot("f")]


def test_a_full_that_repeats_a_pilot_slot_is_a_duplicate_error(chain):
    chain.inv(["a", "b"], phase="pilot")
    chain.inv(["b", "c"], phase="full")
    with pytest.raises(cr.ChainRowsError, match="duplicate"):
        chain.load()


def test_interrupt_in_pilot_then_after_pilot_then_inside_full_resume_without_double_counting(chain):
    p = chain.inv(["a", "b"], phase="pilot", status="running")                # interrupted in the pilot
    t = chain.load()
    assert scored(t) == [] and [r["phase"] for r in t.running] == ["pilot"]
    p["status"] = "quarantined"                                               # resume: the unvalidated file is set aside
    chain.inv(["a", "b"], phase="pilot", attempt=2)
    assert scored(chain.load()) == sorted(slot(i) for i in "ab")
    f1 = chain.inv(["c"], phase="full", status="running", expected=["c", "d", "e"])   # interrupted inside full, 1 row
    assert scored(chain.load()) == sorted(slot(i) for i in "ab")              # the running file is not counted
    f1["status"] = "quarantined"
    f2 = chain.inv(["c", "d"], phase="full", attempt=2, status="running", expected=["c", "d", "e"])  # resumed once
    assert scored(chain.load()) == sorted(slot(i) for i in "ab")
    f2["status"] = "quarantined"                                              # interrupted again, set aside again
    chain.inv(["c", "d", "e"], phase="full", attempt=3)                       # resumed twice: only this one counts
    t = chain.load()
    assert scored(t) == sorted(slot(i) for i in "abcde") and len(t.attempts[slot("c")]) == 1


def test_quarantined_files_are_neither_counted_nor_sha_rechecked(chain):
    rec = chain.inv(["a"], status="quarantined")
    (chain.root / rec["file"]).write_text("garbage that no longer matches\n")
    assert scored(chain.load()) == []


def test_a_validated_file_that_was_modified_is_an_abort(chain):
    rec = chain.inv(["a", "b"])
    path = chain.root / rec["file"]
    path.write_text(path.read_text() + json.dumps(row("c")) + "\n")
    with pytest.raises(cr.ChainRowsError, match="sha256"):
        chain.load()
    chain2 = copy.deepcopy(chain.doc)
    chain2["progress"]["invocations"][0]["sha256"] = None
    with pytest.raises(cr.ChainRowsError):
        cr.load_slots(chain2, chain.root)


def test_a_missing_validated_file_and_torn_or_invalid_rows_are_aborts(chain):
    rec = chain.inv(["a"])
    (chain.root / rec["file"]).unlink()
    with pytest.raises(cr.ChainRowsError, match="missing"):
        chain.load()
    chain.doc["progress"]["invocations"].clear()
    rec = chain.inv(["a"], sha=False, write=True)
    path = chain.root / rec["file"]
    path.write_text(json.dumps(row("a")))                                      # no trailing newline: torn
    rec["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(cr.ChainRowsError, match="torn"):
        chain.load()
    path.write_text("[1]\n")
    rec["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(cr.ChainRowsError):
        chain.load()


def test_rows_must_match_the_accepted_slots(chain):
    chain.inv(["a", "b"], accepted=["a"])
    with pytest.raises(cr.ChainRowsError, match="accepted"):
        chain.load()


def test_a_validated_record_must_have_accepted_all_it_expected(chain):
    chain.inv(["a"], expected=["a", "b"])
    with pytest.raises(cr.ChainRowsError, match="validated"):
        chain.load()


def test_a_row_for_a_slot_the_invocation_never_expected_is_an_error(chain):
    chain.inv(["a", "z"], expected=["a"], accepted=["a", "z"])
    with pytest.raises(cr.ChainRowsError):
        chain.load()


# ---------------------------------------------------------------- incidents, DNF
def test_incident_with_a_validated_prefix_is_a_partial_incident_that_counts(chain):
    chain.inv(["a", "b"], phase="block", status="partial_incident", expected=["a", "b", "c", "d"], accepted=["a", "b"])
    chain.inv(["c", "d"], phase="retry", attempt=2)
    t = chain.load()
    assert scored(t) == sorted(slot(i) for i in "abcd")                        # a and b once; the failing slot c retried


def test_base_plus_recovery_plus_dnf_each_slot_once(chain):
    chain.inv(["a"], phase="block", status="partial_incident", expected=["a", "b", "c"], accepted=["a"])
    chain.inv(["c"], phase="retry", attempt=2)                                 # b failed twice: DNF
    dnf = dict(slot=slot("b"), id="python/b", arm="oc", synthetic=True, nonconv_kind="transport_dnf", passed=False,
               incidents=[dict(slot=slot("b"), attempt=1), dict(slot=slot("b"), attempt=2)])
    chain.doc["dnf"].append(dnf)
    side = chain.root / "s1" / "PICK.s1.oc_python.dnf.jsonl"
    side.write_text(json.dumps(dnf) + "\n")
    t = chain.load()
    assert scored(t) == sorted(slot(i) for i in "abc")
    assert t.scored[slot("b")].source == "dnf" and t.scored[slot("b")].row["nonconv_kind"] == "transport_dnf"
    assert t.cell_complete([slot(i) for i in "abc"])


def test_a_drifted_missing_or_extra_dnf_copy_is_an_error(chain):
    chain.inv(["a"])
    dnf = dict(slot=slot("b"), id="python/b", passed=False, nonconv_kind="transport_dnf")
    chain.doc["dnf"].append(dnf)
    with pytest.raises(cr.ChainRowsError, match="sidecar"):                    # chain.json copy without a sidecar
        chain.load()
    side = chain.root / "s1" / "PICK.s1.oc_python.dnf.jsonl"
    side.write_text(json.dumps(dict(dnf, passed=True)) + "\n")                 # drifted copy
    with pytest.raises(cr.ChainRowsError, match="differs"):
        chain.load()
    side.write_text(json.dumps(dnf) + "\n" + json.dumps(dict(dnf, slot=slot("c"), id="python/c")) + "\n")
    with pytest.raises(cr.ChainRowsError, match="chain.json"):                 # sidecar row the chain.json lacks
        chain.load()


def test_a_dnf_slot_that_also_has_a_row_is_a_duplicate(chain):
    chain.inv(["a", "b"])
    dnf = dict(slot=slot("b"), id="python/b", passed=False, nonconv_kind="transport_dnf")
    chain.doc["dnf"].append(dnf)
    (chain.root / "s1" / "PICK.s1.oc_python.dnf.jsonl").write_text(json.dumps(dnf) + "\n")
    with pytest.raises(cr.ChainRowsError, match="duplicate"):
        chain.load()


def test_a_duplicate_slot_across_invocations_is_an_error_but_distinct_rerun_indexes_are_not(chain):
    chain.inv(["a"], attempt=1)
    chain.inv(["a"], attempt=2)
    with pytest.raises(cr.ChainRowsError, match="duplicate"):
        chain.load()


def test_an_unregistered_rows_file_is_an_error_but_archives_and_sidecars_are_not(chain):
    chain.inv(["a"])
    stray = chain.root / "s1" / cr.rows_name(STEM, 1, "full", 1)
    stray.write_text(json.dumps(row("z")) + "\n")
    with pytest.raises(cr.ChainRowsError, match="unregistered"):
        chain.load()
    assert scored(chain.load(check_unregistered=False)) == [slot("a")]
    stray.unlink()
    (chain.root / "s1" / "incomplete").mkdir()
    (chain.root / "s1" / "incomplete" / cr.rows_name(STEM, 1, "full", 1)).write_text("x\n")
    (chain.root / "s1" / (STEM + ".dnf.jsonl")).write_text("")
    assert scored(chain.load()) == [slot("a")]


# ---------------------------------------------------------------- restart_load archiving (R24)
def test_an_archived_load_generation_is_not_scored_and_its_moved_file_is_not_rechecked(chain):
    pilot = chain.inv(["a", "b"], phase="pilot")
    assert len(scored(chain.load())) == 2
    pilot["status"] = "archived"                                               # restart_load: archived, sha kept
    archive = chain.root / "s1/incomplete/T0"
    archive.mkdir(parents=True)
    (chain.root / pilot["file"]).rename(archive / Path(pilot["file"]).name)
    pilot["file"] = "s1/incomplete/T0/" + Path(pilot["file"]).name
    (chain.root / pilot["file"]).write_text("altered after the move\n")        # NOT re-hashed
    chain.doc["progress"]["loads"].append(dict(load=0, status="archived", load_gen=0, workers=[],
                                               cursor=dict(leg_index=0, phase="pilot")))
    assert scored(chain.load()) == []                                          # the archived pilot is not scored
    chain.inv(["a", "b"], phase="pilot", attempt=1, load_gen=1)                # the rerun pilot is
    t = chain.load()
    assert scored(t) == sorted(slot(i) for i in "ab")
    rerun = chain.doc["progress"]["invocations"][-1]
    (chain.root / rerun["file"]).write_text(json.dumps(row("a")) + "\n")
    with pytest.raises(cr.ChainRowsError):                                     # ... and the rerun IS sha-checked
        chain.load()


# ---------------------------------------------------------------- hook stops, reruns (R25), pre-spawn (R13)
def test_hook_stop_with_cheat_reruns_the_slot_once_and_the_rerun_is_scored(chain):
    chain.inv(["a", "b"], status="hook_stopped", expected=["a", "b", "c"],
              hook_stop=dict(after_slot=slot("b"), disposition="rerun_same_slot"))
    chain.attempt("b", 0, "cheat", tokens=7000)
    chain.inv(["b"], phase="rerun", attempt=2, rerun_index=1)
    chain.inv(["c"], phase="full", attempt=3)
    t = chain.load()
    assert scored(t) == sorted(slot(i) for i in "abc")
    assert t.scored[slot("b")].rerun_index == 1 and t.scored[slot("a")].rerun_index == 0
    assert [a.rerun_index for a in t.attempts[slot("b")]] == [0, 1]            # the cheat attempt stays an attempt record
    assert t.slot_tokens(slot("b")) == 7000 and t.pending_reruns == [] and t.blocked == []


def test_crash_between_the_persisted_disposition_and_the_rerun_resumes_one_rerun_and_keeps_cheat_tokens(chain):
    chain.inv(["a", "b"], status="hook_stopped", expected=["a", "b", "c"],
              hook_stop=dict(after_slot=slot("b"), disposition="rerun_same_slot"))
    chain.attempt("b", 0, "cheat", tokens=7000)
    t = chain.load()
    assert t.pending_reruns == [(slot("b"), 1)]                                # exactly one rerun, index 1
    assert scored(t) == [slot("a")]                                            # slot 1 stays scored, never rerun
    assert t.slot_tokens(slot("b")) == 7000 and t.unscored([slot(i) for i in "abc"]) == [slot("b"), slot("c")]


def test_the_cheat_tokens_survive_even_when_the_attempts_rows_file_was_never_validated(chain):
    chain.inv(["a", "b"], status="running", expected=["a", "b", "c"])          # crash before the record was validated
    chain.attempt("b", 0, "cheat", tokens=7000)
    t = chain.load()
    assert scored(t) == [] and t.pending_reruns == [(slot("b"), 1)] and t.slot_tokens(slot("b")) == 7000
    assert t.attempts[slot("b")][0].row is None


def test_two_further_cheats_end_in_exhausted_and_the_last_attempt_is_a_strict_fail(chain):
    chain.inv(["a", "b"], status="hook_stopped", expected=["a", "b", "c"],
              hook_stop=dict(after_slot=slot("b"), disposition="rerun_same_slot"))
    chain.attempt("b", 0, "cheat", tokens=10)
    chain.inv(["b"], phase="rerun", attempt=2, rerun_index=1, status="hook_stopped",
              hook_stop=dict(after_slot=slot("b"), disposition="rerun_same_slot"))
    chain.attempt("b", 1, "cheat", tokens=20)
    t = chain.load()
    assert t.pending_reruns == [(slot("b"), 2)]
    chain.inv(["b"], phase="rerun", attempt=3, rerun_index=2)
    chain.attempt("b", 2, "exhausted", tokens=30)
    t = chain.load()
    s = t.scored[slot("b")]
    assert s.rerun_index == 2 and s.disposition == "exhausted" and s.strict_fail is True
    assert t.slot_tokens(slot("b")) == 60 and t.pending_reruns == []


def test_rerun_bounds_exhausted_placement_and_an_unmatched_accepted_attempt_are_errors(chain):
    chain.inv(["a"], status="hook_stopped", expected=["a", "b"], hook_stop=dict(after_slot=slot("a"),
                                                                                disposition="rerun_same_slot"))
    chain.attempt("a", 3, "cheat")
    with pytest.raises(cr.ChainRowsError, match="re-run"):
        chain.load()
    chain.doc["progress"]["slot_attempts"].clear()
    chain.attempt("a", 0, "exhausted")
    with pytest.raises(cr.ChainRowsError, match="exhausted"):
        chain.load()
    chain.doc["progress"]["slot_attempts"].clear()
    chain.attempt("a", 0, "cheat")
    chain.attempt("a", 0, "cheat")
    with pytest.raises(cr.ChainRowsError, match="duplicate"):
        chain.load()
    chain.doc["progress"]["slot_attempts"].clear()
    chain.attempt("q", 0, "accepted")                                            # accepted, but no row exists
    with pytest.raises(cr.ChainRowsError, match="row"):
        chain.load()


def test_a_block_disposition_leaves_the_slot_unscored_for_the_operator(chain):
    chain.inv(["a", "b"], status="hook_stopped", expected=["a", "b", "c"],
              hook_stop=dict(after_slot=slot("b"), disposition="block"))
    chain.attempt("b", 0, "unclear", tokens=5)
    t = chain.load()
    assert scored(t) == [slot("a")] and t.blocked == [slot("b")] and t.pending_reruns == []


def test_a_before_attempt_failure_is_a_pre_spawn_incident_replayed_exactly_once(chain):
    chain.inv(["a"], status="hook_stopped", expected=["a", "b", "c"], hook_stop=dict(before_slot=slot("b")))
    chain.doc["progress"]["pre_spawn"].append(dict(slot=slot("b"), disposition="pre_spawn_incident",
                                                   cause="server_error", load_gen=0))
    t = chain.load()
    assert scored(t) == [slot("a")] and [p["slot"] for p in t.open_pre_spawn] == [slot("b")]
    chain.inv(["b", "c"], phase="retry", attempt=2)                             # the replayed retry is registered
    t = chain.load()
    assert t.open_pre_spawn == [] and scored(t) == sorted(slot(i) for i in "abc")


def test_a_hook_stop_record_must_name_its_stop(chain):
    chain.inv(["a"], status="hook_stopped", expected=["a", "b"])
    with pytest.raises(cr.ChainRowsError, match="hook_stop"):
        chain.load()


def test_attempt_dispositions_default_to_accepted_and_an_accepted_record_may_name_a_row(chain):
    chain.inv(["a"])
    chain.attempt("a", 0, "accepted")
    assert chain.load().scored[slot("a")].disposition == "accepted"


# ---------------------------------------------------------------- legacy read-only layouts
def write_rows(path, ids):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(dict(id=i, passed=True)) + "\n" for i in ids))


def test_legacy_c147_layout_session_stem_jsonl(tmp_path):
    for session, stem, ids in (("s1", "P.s1.opencode_python", ["python/a", "python/b"]),
                               ("s1", "P.s1.opencode_go", ["go/x"]), ("reload", "P.reload.opencode_python", ["python/a"]),
                               ("pilot", "P.pilot.opencode_python", ["python/a"])):
        write_rows(tmp_path / session / (stem + ".jsonl"), ids)
    (tmp_path / "s1" / "P.s1.opencode_python.manifest.json").write_text("{}")          # never read as rows
    write_rows(tmp_path / "s1" / "incomplete" / "T" / "P.s1.opencode_python.jsonl", ["python/zz"])
    write_rows(tmp_path / "a4" / "x.jsonl", ["python/zz"])
    before = sorted((p, p.stat().st_mtime_ns) for p in tmp_path.rglob("*") if p.is_file())
    t = cr.legacy(tmp_path, "c147")
    assert t.legacy is True and len(t.scored) == 5
    assert all(s.source == "row" and s.file for s in t.scored.values())
    assert cr.legacy_slot("s1", "P.s1.opencode_python", "python/a") in t.scored
    assert sorted((p, p.stat().st_mtime_ns) for p in tmp_path.rglob("*") if p.is_file()) == before     # read-only
    assert cr.legacy(tmp_path, "m63").scored.keys() == t.scored.keys()


def test_legacy_m64_layout_base_segments_and_dnf_sidecar(tmp_path):
    stem = "P.s1.oc_python"
    write_rows(tmp_path / "s1" / (stem + ".jsonl"), ["python/a", "python/b"])
    write_rows(tmp_path / "s1" / (stem + ".w1.jsonl"), ["python/c"])
    write_rows(tmp_path / "s1" / (stem + ".w2.jsonl"), ["python/d"])
    dnf = dict(slot="e|oc|P|s1|python|e", id="python/e", synthetic=True, nonconv_kind="transport_dnf", passed=False)
    (tmp_path / "s1" / (stem + ".dnf.jsonl")).write_text(json.dumps(dnf) + "\n")
    t = cr.legacy(tmp_path, "m64")
    assert sorted(s.row["id"] for s in t.scored.values()) == [f"python/{c}" for c in "abcde"]
    assert [s.source for s in sorted(t.scored.values(), key=lambda s: s.row["id"])] == ["row"] * 4 + ["dnf"]
    assert {s.segment for s in t.scored.values() if s.source == "row"} == {0, 1, 2}


def test_legacy_duplicates_and_bad_input_are_errors(tmp_path):
    stem = "P.s1.oc_python"
    write_rows(tmp_path / "s1" / (stem + ".jsonl"), ["python/a"])
    write_rows(tmp_path / "s1" / (stem + ".w1.jsonl"), ["python/a"])
    with pytest.raises(cr.ChainRowsError, match="duplicate"):
        cr.legacy(tmp_path, "m64")
    with pytest.raises(ValueError):
        cr.legacy(tmp_path, "nonsense")
    (tmp_path / "s1" / (stem + ".w1.jsonl")).write_text('{"id": "x"')
    with pytest.raises(cr.ChainRowsError, match="torn"):
        cr.legacy(tmp_path, "m64")
    assert cr.legacy(tmp_path / "nothing", "c147").scored == {}


# ---------------------------------------------------------------- R7: the consumers of chain out-root rows
def test_the_consumer_enumeration_is_in_the_module_docstring_and_complete():
    """Phase 3a: the section is now "Consumers (R7, migrated in phase 3a ...)": every listed path exists and every module
    that reads chain rows through today's loaders or layouts is listed or an allow-listed non-chain reader (the stricter,
    pattern-based check is `test_p371_r7_consumers`)."""
    from bench.tests.test_p371_r7_consumers import ALLOW
    doc = cr.__doc__
    assert "Consumers (R7, migrated in phase 3a" in doc
    listed = set(re.findall(r"^\s*-\s+(benchmark/\S+\.(?:py|sh))\b", doc.split("Consumers (R7, migrated in phase 3a")[1],
                            re.M))
    assert len(listed) >= 8
    for path in listed:
        assert (REPO / path).is_file(), path
    inject = {"benchmark/chains/c147/run_inject.py", "benchmark/m62/inject_verify.py"}       # inject runs, not chains
    allowed = {"benchmark/bench/chain_rows.py", "benchmark/bench/proc_guard.py"} | set(ALLOW) | inject
    pattern = re.compile(r"pg\.load_rows\(|\.dnf\.jsonl|chains/c147|/ \"c147\"")
    found = set()
    for path in (REPO / "benchmark").rglob("*.py"):
        rel = path.relative_to(REPO).as_posix()
        if "/tests/" in rel or "/results/" in rel and not rel.endswith("_report.py") or "/.venv" in rel:
            continue
        if pattern.search(path.read_text()):
            found.add(rel)
    missing = {f for f in found - allowed if f not in listed}
    assert not missing, sorted(missing)
