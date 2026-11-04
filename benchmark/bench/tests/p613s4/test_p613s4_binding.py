"""The events-file HARVEST binding (step-3 erratum E2) for the divergence section: refusals, and what must NOT refuse.

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.

Binding rule (contract): the events file is read from the `evidence` ref with `git show <ref>:<path>`; the attempt's
`HARVEST.json` record for that file must have `sha256` == the row's `evidence_sha256.events` and `published_sha256` == the sha256
of the bytes read; else `RefusalError`.

Delivery 3: HARVEST.json is hash-pinned by B8 rule 5 (a dossier `harvest_sha256`), so editing it on disk makes B8 REJECT the pair
and the binding is never reached that way (the delivery-2 defect of the 11 on-disk HARVEST tests). The HARVEST / row refusals are
therefore tested at the `_events` level on an in-memory copy of the verified attempt record and row.
"""
from __future__ import annotations

import copy
import json

import pytest

from bench.tests.p613 import a7world
from bench.tests.p613s3 import s3world as S
from bench.tests.p613s4 import dview as D
from bench.tests.p613s4 import s4world as W

ITEMS = [("on", "s1", "python/alpha"), ("off", "s1", "go/zeta"), ("on", "s2", "go/xi"), ("off", "s2", "go/phi")]


# class: invariant (control: the unmodified world is accepted, so every refusal below is the binding's)
def test_control_accepted(divmod_, world_a):
    assert D.a7_div(divmod_, world_a)


# class: new-behaviour (the published bytes on the evidence ref differ from HARVEST published_sha256 -> RefusalError)
@pytest.mark.parametrize("arm,session,rid", ITEMS)
def test_altered_published_bytes_refused(divmod_, clone_a, arm, session, rid):
    case = clone_a()
    rel = f"{W.events_rel(case, arm, session, rid)}"
    ref = case.tamper_evidence(lambda files: files.__setitem__(rel, files[rel] + b"\n"))
    D.refuses_as_refusal(D.a7_div, divmod_, case, ref=ref)


# class: new-behaviour (an events file missing from the evidence ref -> RefusalError, never a skipped item)
def test_missing_events_file_refused(divmod_, clone_a):
    case = clone_a()
    rel = W.events_rel(case, "on", "s2", "go/omicron")
    ref = case.tamper_evidence(lambda files: files.pop(rel))
    D.refuses_as_refusal(D.a7_div, divmod_, case, ref=ref)


# class: new-behaviour (an evidence ref that does not resolve / is not a sha -> RefusalError)
@pytest.mark.parametrize("ref", ["0" * 40, "not-a-sha", ""])
def test_bad_ref_refused(divmod_, world_a, ref):
    D.refuses_as_refusal(D.a7_div, divmod_, world_a, ref=ref)


# ---------------------------------------------------------------------------------------------------- `_events` level
@pytest.fixture(scope="module")
def bound(cli_a, divmod_):
    from bench import p426_panel as P
    from bench import p426_verify as V

    top = V.repo_top(cli_a.repo)
    ref = V.resolve_commit(top, cli_a.evidence_ref, "ref")
    ctx = P._a7_context(cli_a.results_root, cli_a.b8)
    att = ctx["atts"]["s1"]["on"]
    rid = "python/alpha"
    return dict(att=att, row=att["rows"][rid], rid=rid, top=top, ref=ref, rel=W.events_rel(cli_a, "on", "s1", rid), mod=divmod_)


def _call(bound, att=None, row=None):
    return bound["mod"]._events(att or bound["att"], row or bound["row"], bound["rid"], bound["top"], bound["ref"])


def _mutate(bound, mode):
    att, row = copy.deepcopy(bound["att"]), copy.deepcopy(bound["row"])
    files = att["harvest"]["files"]
    recs = [f for f in files if f.get("published") == bound["rel"]]
    assert len(recs) == 1
    if mode == "published_sha":
        recs[0]["published_sha256"] = "0" * 64
    elif mode == "raw_sha":
        recs[0]["sha256"] = "1" * 64
    elif mode == "duplicate":
        files.append(dict(recs[0]))
    elif mode == "missing":
        att["harvest"]["files"] = [f for f in files if f.get("published") != bound["rel"]]
    elif mode == "raw_as_published":                # the record binds the RAW bytes as if published: the scrubbed bytes differ
        recs[0]["published_sha256"] = recs[0]["sha256"]
    elif mode == "row_sha":                         # the row's evidence_sha256.events disagrees with the HARVEST raw sha
        row["evidence_sha256"]["events"] = "2" * 64
    elif mode == "row_no_sha":
        row["evidence_sha256"] = {}
    elif mode == "destination":
        recs[0]["destination"] = "other"
    else:
        raise AssertionError(mode)
    return att, row


# class: invariant (control: the unmodified record binds, so every `_events` refusal below is the binding's)
def test_events_control_binds(bound):
    path, data = _call(bound)
    assert path == bound["rel"] and data


# class: new-behaviour (every HARVEST / row inconsistency -> RefusalError)
@pytest.mark.parametrize("mode", ["published_sha", "raw_sha", "duplicate", "missing", "raw_as_published", "row_sha", "row_no_sha",
                                  "destination"])
def test_harvest_binding_refused(bound, mode):
    att, row = _mutate(bound, mode)
    D.refuses_as_refusal(_call, bound, att, row)


# class: invariant (the on-disk route is closed: an edited HARVEST makes B8 reject the pair, so the section is incomplete
# (never FINAL) and no comparison is made on the unbound file)
def test_edited_harvest_on_disk_rejects_pair(divmod_, clone_a):
    case = clone_a()
    att = case.attempt("on", "s1")
    h = json.loads((att / "HARVEST.json").read_text())
    rel = W.events_rel(case, "on", "s1", "python/alpha")
    [f for f in h["files"] if f.get("published") == rel][0]["published_sha256"] = "0" * 64
    (att / "HARVEST.json").write_text(a7world.dumps(a7world.sealed({k: v for k, v in h.items() if k != "sha256"})))
    case.reverify()
    got = D.a7_div(divmod_, case)
    assert got["complete"] is False
    assert ("s1", "python/alpha") not in D.items(got)


# class: invariant (B8-accepted pairs only: tampering with the REJECTED key's events file changes nothing)
def test_rejected_key_events_never_read(divmod_, clone_a, world_a):
    case = clone_a()
    rel = W.events_rel(case, "off", "s1", "go/psi")
    ref = case.tamper_evidence(lambda files: files.__setitem__(rel, b"this is not events\n"))
    got = D.a7_div(divmod_, case, ref=ref)
    assert ("s1", "go/psi") not in D.items(got)
    assert set(D.items(got)) == set(W.EXPECT_A)


# class: invariant (a file the section does not read - the final-tree objects - may be absent on the ref)
def test_unrelated_evidence_files_not_required(divmod_, clone_a):
    case = clone_a()
    ref = case.tamper_evidence(lambda files: [files.pop(p) for p in [p for p in files if "/objects/" in p]])
    assert D.a7_div(divmod_, case, ref=ref)


# class: new-behaviour (bytes that are not JSONL / not UTF-8 are refused as unreadable, never read as an empty transcript)
@pytest.mark.parametrize("bad", [b"{not json\n", b"\xff\xfe\x00", b'{"type": "text"}\n[1, 2\n'])
def test_unparseable_events_refused(bound, bad):
    D.refuses_as_refusal(bound["mod"].parse_messages, bad, "x")


# class: new-behaviour (CLI: a binding refusal exits non-zero with REFUSED on stderr and writes NO output file)
def test_cli_binding_refusal_writes_nothing(clone_cli_a, panel_a, tmp_path):
    case = clone_cli_a()
    rel = W.events_rel(case, "on", "s1", "python/alpha")
    ref = case.tamper_evidence(lambda files: files.__setitem__(rel, files[rel] + b"\n"))
    proc, md, js = D.run_all(case, tmp_path / "out", panel_a, ref=ref)
    S.refused_cli(proc)
    assert "REFUSED" in proc.stderr
    assert not md.exists() and not js.exists()
