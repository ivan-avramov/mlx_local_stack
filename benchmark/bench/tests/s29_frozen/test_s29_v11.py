"""S29 frozen tests, amendments for spec v1.1 (docs/specs/s29-record-not-block.md v1.1): H5's committed-harvest window, the atomic kept
original and the harvest's supersession-link check; H3b (the end-of-run host record reflects the latest final check); P6b's scrubbed
listed path never refusing and a reference to an unrecognised file from ANY harvested record, with a match boolean.

Classes: [FIX] reproduces a failure the spec fixes; [INV] preserves an invariant; [NEW] new behaviour. Written against the baseline
and candidate 1 (not against any v1.1 implementation).

ASSUMPTIONS (mechanism free): (1) the C384-superseded `leg.json` is obtained from the sequencer's own H5 flow (never hand-written):
it is grafted onto a harvest-test leg root (leg name / attempt rewritten and resealed; every other field, the supersession block
included, untouched), and the kept original is found by its bytes; (2) "installed atomically" is observed as a rename / link whose
destination is the kept file (a temp file renamed into place), and a failure injected at that step leaves `leg.json` unreplaced
and the next resume completing; (3) H3b: the field `host_env_after_last_leg` (the name C360 introduced and the sequence record has
carried since) is present and `[]` after a clean final check that follows a changed one."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from bench import p426_harvest as H
from bench import p426_hooks as ph
from bench.tests import test_b2_s9_harvest as T
from bench.tests.s26_frozen import s26_support as X
from bench.tests.s29_frozen import s29_support as S
from bench.tests.s29_frozen import test_s29_harvest as HV

OFF_PILOT, ON_PILOT = S.OFF_PILOT, S.ON_PILOT


# ---------------------------------------------------------------------------------------------------- H5: committed harvest
def test_fix_h5_a_leg_whose_harvest_is_published_but_not_recorded_is_left_as_recorded(tmp_path, monkeypatch):
    """[FIX] v1.1: the attempt's `HARVEST.json` is published but `sequence.json` does not show the harvest (the process died between):
    the leg is NOT re-derived (its published harvest names the old state); `leg.json` and every file of the leg root stay
    byte-identical, nothing launches, the operator decides; the stop is on the leg, not on the host."""
    a3 = S.make_a3(tmp_path, monkeypatch, committed_harvest=True)
    assert (a3["r1"]["ops"].harvest_path(f"{OFF_PILOT}.a1") / "HARVEST.json").is_file()
    before = {k: p.read_bytes() for k, p in S.files_under(a3["root"]).items()}
    r = S.resume(tmp_path, monkeypatch, a3)
    assert r["rc"] == 1 and X.legs_run(r) == []
    assert {k: p.read_bytes() for k, p in S.files_under(a3["root"]).items()} == before
    assert (a3["root"] / "leg.json").read_bytes() == a3["orig_bytes"]
    assert S.entry_of(r, OFF_PILOT)["state"] == "INVALID"
    log = X.seq_log(r)
    assert f"{OFF_PILOT}.a1" in log and "STOP: the host environment differs" not in log


def test_inv_h5_without_a_published_harvest_the_same_leg_is_rederived(tmp_path, monkeypatch):
    """[INV] control of the test above: the same box state with the published harvest absent is re-derived (VALID)."""
    a3 = S.make_a3(tmp_path, monkeypatch)
    assert not (a3["r1"]["ops"].harvest_path(f"{OFF_PILOT}.a1") / "HARVEST.json").exists()
    r = S.resume(tmp_path, monkeypatch, a3)
    assert r["rc"] == 0, r["err"]
    assert json.loads((a3["root"] / "leg.json").read_text())["state"] == "VALID"


# ---------------------------------------------------------------------------------------------------- H5: the kept original
def test_new_h5_the_kept_original_is_installed_by_rename_and_a_failed_install_changes_nothing(tmp_path, monkeypatch):
    """[NEW] v1.1: "installed atomically (a crash never leaves a partial file at its final path)". The install of the kept original is
    a rename / link of a complete temp file onto the kept path; a crash injected at that step leaves `leg.json` unreplaced and the
    sequence entry INVALID, and the next resume completes with the kept original byte-identical."""
    a3 = S.make_a3(tmp_path, monkeypatch)
    root, orig = a3["root"], a3["orig_bytes"]
    state = dict(crash=True, installs=[])

    def wrap(real):
        def call(src, dst, *a, **kw):
            try:
                is_orig = os.path.isfile(src) and Path(src).read_bytes() == orig
            except OSError:
                is_orig = False
            if is_orig and Path(dst).parent == root and Path(dst).name != "leg.json":
                state["installs"].append(Path(dst).name)
                if state["crash"]:
                    raise OSError("injected crash at the kept-original install")
            return real(src, dst, *a, **kw)
        return call
    for name in ("replace", "rename", "link"):
        monkeypatch.setattr(os, name, wrap(getattr(os, name)))
    crashed = False
    try:
        S.resume(tmp_path, monkeypatch, a3)
    except OSError as exc:
        crashed = "injected crash" in str(exc)
    assert state["installs"], "the kept original is not installed by rename / link (not atomic)"
    assert crashed
    assert (root / "leg.json").read_bytes() == orig
    kept_name = state["installs"][0]
    assert not (root / kept_name).exists() or (root / kept_name).read_bytes() == orig        # never a partial file at the final path
    state["crash"] = False
    r2 = S.resume(tmp_path, monkeypatch, a3)
    assert r2["rc"] == 0, r2["err"]
    assert (root / kept_name).read_bytes() == orig
    assert json.loads((root / "leg.json").read_text())["state"] == "VALID"


# ---------------------------------------------------------------------------------------------------- the harvest's link check
def superseded_leg(tmp_path, monkeypatch):
    """A leg root of the harvest-test `World` that carries the C384 `leg.json` of the sequencer's own H5 flow (grafted: leg /
    attempt rewritten and resealed, nothing else touched) and its kept original. Returns (world, kept relative name, orig bytes)."""
    a3 = S.make_a3(tmp_path / "seq", monkeypatch)
    assert S.resume(tmp_path / "seq", monkeypatch, a3)["rc"] == 0
    new = json.loads((a3["root"] / "leg.json").read_text())
    kept = [rel for rel, p in S.files_under(a3["root"]).items() if rel != "leg.json" and p.read_bytes() == a3["orig_bytes"]]
    assert len(kept) == 1, sorted(S.files_under(a3["root"]))
    w = T.World(tmp_path / "h")
    body = {k: v for k, v in new.items() if k != "sha256"}
    body.update(leg=T.LEG, attempt=T.N)
    (w.root / "leg.json").write_text(json.dumps(ph.seal(body), indent=1, sort_keys=True) + "\n")
    return w, kept[0], a3["orig_bytes"]


def test_new_harvest_publishes_a_c384_leg_json_with_its_kept_original(tmp_path, monkeypatch):
    """[NEW] v1.1 control: the superseding `leg.json` + the kept original that hashes to the recorded value harvest, and the kept
    original is published."""
    w, kept, orig = superseded_leg(tmp_path, monkeypatch)
    (w.root / kept).write_bytes(orig)
    doc = w.harvest()
    e = T.entry(doc, f"leg:{kept}")
    assert e["destination"] in ("main", "evidence") and e["sha256"] == T.sha(orig)


@pytest.mark.parametrize("how", ["missing", "differs", "symlink"])
def test_new_harvest_refuses_a_c384_leg_json_whose_kept_original_is_missing_differs_or_is_a_link(tmp_path, monkeypatch, how):
    """[NEW] v1.1: "a `leg.json` carrying the C384 supersession publishes only with a kept original that exists and hashes to the
    recorded value; otherwise the harvest refuses" (nothing published)."""
    w, kept, orig = superseded_leg(tmp_path, monkeypatch)
    if how == "differs":                                  # a different, perfectly well-sealed record under the kept name
        other = {k: v for k, v in json.loads(orig).items() if k != "sha256"}
        other["reason"] = other["reason"] + " (altered)"
        (w.root / kept).write_text(json.dumps(ph.seal(other), indent=1, sort_keys=True) + "\n")
    elif how == "symlink":                                # the right bytes, reached through a link
        real = tmp_path / "elsewhere.json"
        real.write_bytes(orig)
        (w.root / kept).symlink_to(real)
    with pytest.raises(H.HarvestError):
        w.harvest()
    T.nothing_published(w)


# ---------------------------------------------------------------------------------------------------- H3b
def test_fix_h3b_a_clean_final_check_after_a_changed_one_leaves_an_empty_final_diff(tmp_path, monkeypatch):
    """[FIX] H3b: run 1 ends clean; the host changes and run 2 ends on a changed host (final diff = the change); the host returns to the
    baseline and run 3 ends clean: the end-of-run record reflects the LATEST final check (present, and empty), and the published
    `sequence.json` of run 3 says the same. (The change stays findable in the history of run 2: `host_env_events` / the logs.)"""
    r1 = X.drive(tmp_path, monkeypatch, "run", "--through", OFF_PILOT)
    assert r1["rc"] == 0, r1["err"]
    S.add_jdk(r1["world"])
    r2 = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT, world=r1["world"], records=False)
    assert r2["rc"] == 0, r2["err"]
    assert S.JDK in json.dumps(X.sequence(r2).get("host_env_after_last_leg"))
    r1["world"].rm_formula("openjdk@17", "17.0.9")
    r3 = X.drive(tmp_path, monkeypatch, "run", "--through", ON_PILOT, world=r1["world"], records=False)
    assert r3["rc"] == 0, r3["err"]
    assert X.sequence(r3).get("host_env_after_last_leg") == []
    last = json.loads(r3["ops"].publishes[-1])
    assert last.get("host_env_after_last_leg") == []


# ---------------------------------------------------------------------------------------------------- P6b, v1.1
def test_fix_p6b_a_reference_with_a_wrong_recorded_digest_is_listed_with_a_false_match_and_not_refused(tmp_path):
    """[FIX] v1.1: a reference to an unrecognised file keeps a boolean of whether the recorded digest matches; a wrong digest is
    `false` (and the harvest goes on): the record names both the referencing file and the unrecognised one, with a `false`."""
    w = T.World(tmp_path)
    data = b"a grader product no rule knows\n"
    path = T.put(w.ev / f"{HV.SEQ}/execute.unknown", data)
    rows = w.root / "s1" / "rows.jsonl"
    docs = [json.loads(line) for line in rows.read_text().splitlines() if line.strip()]
    docs[0]["grade_extra"] = dict(path=w.p(path), sha256="0" * 64)
    rows.write_text("".join(json.dumps(d) + "\n" for d in docs))
    doc = w.harvest()
    refs = [n for n in HV.nodes_mentioning(doc, "execute.unknown") if any("rows.jsonl" in t for _, t in S.leaves(n))]
    assert refs and any(v is False for n in refs for v in n.values()), refs
    assert HV.published_copies(w, data) == []


def test_fix_p6b_a_reference_with_the_right_digest_is_listed_with_a_true_match(tmp_path):
    """[FIX] the same with the right digest: `true`."""
    w = T.World(tmp_path)
    data = b"a grader product no rule knows\n"
    path = T.put(w.ev / f"{HV.SEQ}/execute.unknown", data)
    HV.reference(w, path, key="grade_extra")
    doc = w.harvest()
    refs = [n for n in HV.nodes_mentioning(doc, "execute.unknown") if any("rows.jsonl" in t for _, t in S.leaves(n))]
    assert refs and any(v is True for n in refs for v in n.values()), refs


def test_fix_p6b_a_reference_from_a_manifest_to_an_unrecognised_file_is_listed_and_not_refused(tmp_path):
    """[FIX] v1.1 "from any harvested record": the reference sits in the probe manifest (`s1/rows.manifest.json`), not in a row."""
    w = T.World(tmp_path)
    data = b"referenced from a manifest\n"
    path = T.put(w.ev / f"{HV.SEQ}/execute.unknown", data)
    man = w.root / "s1" / "rows.manifest.json"
    doc = json.loads(man.read_text())
    doc["grader_extra"] = dict(path=w.p(path), sha256=T.sha(data))
    man.write_text(json.dumps(doc, indent=1, sort_keys=True))
    out = w.harvest()
    both = [n for n in HV.nodes_mentioning(out, "execute.unknown") if any("rows.manifest.json" in t for _, t in S.leaves(n))]
    assert both, "the manifest's reference to the unrecognised file is not listed"
    assert HV.published_copies(w, data) == []


@pytest.mark.parametrize("where", ["leg", "evidence", "run"])
def test_fix_p6b_a_path_the_scrub_would_change_is_listed_scrubbed_and_never_refuses(tmp_path, where):
    """[FIX] v1.1: "A path the scrub would change is listed in its scrubbed form, never refusing the harvest": a directory named
    after the account in each root; the listing has the size, the file name, and not the account name."""
    w = T.World(tmp_path)
    data = b"notes of the account\n"
    base = {"leg": w.root, "evidence": w.ev, "run": w.run}[where]
    T.put(base / "b2opuser" / "notes.dat", data)
    doc = w.harvest()
    text = json.dumps(doc)
    assert "b2opuser" not in text
    assert HV.listing(doc, "notes.dat", data), text
    assert HV.published_copies(w, data) == []


def test_fix_p6b_the_listing_has_no_digest_of_the_files_bytes(tmp_path):
    """[FIX] v1.1: nothing derived from the unscanned bytes: no sha256 of them (whole or as a 16-character prefix) anywhere in
    `HARVEST.json`; the size is there."""
    w = T.World(tmp_path)
    data = b"unscanned bytes, never hashed\n"
    T.put(w.ev / f"{HV.SEQ}/odd.dat", data)
    doc = w.harvest()
    text = json.dumps(doc)
    assert T.sha(data) not in text and T.sha(data)[:16] not in text
    assert HV.listing(doc, "odd.dat", data)
