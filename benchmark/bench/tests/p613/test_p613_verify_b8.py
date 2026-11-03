"""B8 (bench.p426_verify): which A7 ON / OFF pairs are comparable. Fail closed; every rejection carries a reason.

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.
Rejected pair = returned with accepted False and reasons; refusal = RefusalError / CLI rc 2 (structural problems only).
"""
from __future__ import annotations

import json
import re

import pytest

from bench.tests.p613 import a7world as W
from bench.tests.p613.sigview import run_cli

HEX64 = re.compile(r"^[0-9a-f]{64}$")


def pair(b8, session):
    hits = [p for p in b8["pairs"] if p["pair"] == session]
    assert len(hits) == 1, f"expected one entry for {session}, got {len(hits)}"
    return hits[0]


def outcome(verify, root):
    """('refused', msg) | ('rejected', pair_dict_by_session) | ('accepted', ...) for tests where the contract allows either a
    rejected pair or a refusal (a missing / unreadable required file)."""
    try:
        b8 = verify.verify_a7(root)
    except verify.RefusalError as e:
        return "refused", str(e)
    return "returned", b8


# ----------------------------------------------------------------------------------------------- fixtures sanity
# class: invariant (the synthetic tree is well formed: row counts == planned slots, seals verify, hashes match bytes)
def test_world_is_well_formed(make_world):
    w = make_world()
    for arm in ("off", "on"):
        for s in W.SESSIONS + W.DIAG:
            rows = w.rows_of(arm, s)
            sched = w.load("wave2", W.attempt_name(arm, s), "schedule.json")
            planned = sum(len(i["names"]) for b in sched["blocks"] for l in b["legs"] for i in l["invocations"])
            assert len(rows) == planned == len(W.DEFAULT_IDS[s])
            leg = w.load("wave2", W.attempt_name(arm, s), "leg.json")
            assert leg["sha256"] == W.canon_sha(leg)
    d = w.load("wave2", "pairs", "s1__off-a1__on-a1.json")
    assert d["sha256"] == W.canon_sha(d) and d["verdict"] == "PASS"
    h = (w.apath("off", "s1", "HARVEST.json")).read_bytes()
    assert d["arms"]["off"]["harvest_sha256"] == W.sha_bytes(h)


# ----------------------------------------------------------------------------------------------- success path
# class: new-behaviour
def test_accepts_both_clean_pairs_with_full_key_set(verify, make_world):
    w = make_world()
    b8 = verify.verify_a7(w.root)
    assert b8["axis"] == "A7"
    for s in ("s1", "s2"):
        p = pair(b8, s)
        assert p["accepted"] is True and p["reasons"] == []
        assert p["off"] == f"tg1-p426-off-{s}.a1" and p["on"] == f"tg1-p426-on-{s}.a1"
        assert p["keys_accepted"] == 8 and p["keys_rejected"] == []
        assert p["speed_valid"] is True


# class: new-behaviour (rows of one session live in several files incl. the L0.pilot.a1 invocation file; all count)
def test_rows_from_every_invocation_file_are_read(verify, make_world):
    w = make_world()
    files = sorted(w.apath("off", "s1", "s1").glob("*.jsonl"))
    assert len(files) >= 3
    assert pair(verify.verify_a7(w.root), "s1")["keys_accepted"] == 8


# class: new-behaviour
def test_pilot_and_reload_are_listed_as_diagnostic(verify, make_world):
    b8 = verify.verify_a7(make_world().root)
    for s in ("pilot", "reload"):
        p = pair(b8, s)
        assert p.get("role") == "diagnostic"
    assert pair(b8, "s1").get("role") != "diagnostic" and pair(b8, "s2").get("role") != "diagnostic"


# class: new-behaviour (inputs: repo-relative to results_root, sha256 of the file bytes now, no absolute path)
def test_inputs_are_relative_paths_with_current_file_hashes(verify, make_world):
    w = make_world()
    b8 = verify.verify_a7(w.root)
    inputs = b8["inputs"]
    assert inputs
    for rel, sha in inputs.items():
        assert not rel.startswith("/") and ".." not in rel.split("/")
        assert HEX64.match(sha)
        assert W.sha_bytes((w.root / rel).read_bytes()) == sha, rel
    rels = " ".join(inputs)
    for needle in ("v8_base.json", "s1__off-a1__on-a1.json", "leg.json", "chain.json", "schedule.json", "HARVEST.json",
                   ".jsonl", "/items/"):
        assert needle in rels, f"{needle} is an input of the pair verdict and must be hashed"
    assert ".ready.json" not in rels


# class: new-behaviour (no absolute path anywhere in the verdict)
def test_b8_document_has_no_absolute_paths(verify, make_world):
    w = make_world()
    blob = json.dumps(verify.verify_a7(w.root))
    assert str(w.base) not in blob and "/private/" not in blob and "/Users/" not in blob


# class: new-behaviour (deterministic)
def test_verify_is_deterministic(verify, make_world):
    w = make_world()
    assert json.dumps(verify.verify_a7(w.root), sort_keys=True) == json.dumps(verify.verify_a7(w.root), sort_keys=True)


# ----------------------------------------------------------------------------------------------- rule 1 (validity)
# class: new-behaviour
@pytest.mark.parametrize("arm", ["off", "on"])
@pytest.mark.parametrize("state", ["INVALID", "SUPERSEDED"])
def test_rule1_not_valid_leg_rejects_only_that_pair(verify, make_world, arm, state):
    w = make_world()
    w.edit_leg(arm, "s1", state=state)
    b8 = verify.verify_a7(w.root)
    p = pair(b8, "s1")
    assert p["accepted"] is False
    assert p["reasons"] and any(state in r or "VALID" in r for r in p["reasons"])
    assert any(W.attempt_name(arm, "s1") in r for r in p["reasons"]), "the reason names the offending attempt"
    assert pair(b8, "s2")["accepted"] is True


# class: new-behaviour (a missing attempt is structural: refusal)
def test_rule1_missing_attempt_refuses(verify, make_world):
    import shutil
    w = make_world()
    shutil.rmtree(w.apath("on", "s2", ""))
    with pytest.raises(verify.RefusalError):
        verify.verify_a7(w.root)


# class: new-behaviour (ASSUMPTION: the pair members are the ones sequence.json / the dossier name; naming a deny-listed
# path, here a smoke attempt, as a member is a refusal — spec §2)
@pytest.mark.parametrize("bad", ["tg1-p426-on-s1-smoke.a1", "archive/tg1-p426-on-s1.a1"])
def test_deny_listed_member_refuses(verify, make_world, bad):
    w = make_world()
    target = w.p("wave2", *bad.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copytree(w.apath("on", "s1", ""), target)

    def retarget(d):
        d["arms"]["on"]["attempt"] = bad
    w.edit_dossier("s1", retarget)
    seq = w.load("wave2", "run", "sequence.json")
    for p in seq["pairs"]:
        if p["pair"] == "s1":
            p["on"] = bad
    w.save(seq, "wave2", "run", "sequence.json", seal=False)
    with pytest.raises(verify.RefusalError):
        verify.verify_a7(w.root)


# ----------------------------------------------------------------------------------------------- rule 2 (arm identity)
# class: new-behaviour
def test_rule2_extra_difference_field_rejects_pair(verify, make_world):
    w = make_world()
    w.edit_dossier("s1", lambda d: d["differences"].append({"field": "argv.router", "off": "x", "on": "y", "process": "r"}))
    p = pair(verify.verify_a7(w.root), "s1")
    assert p["accepted"] is False and any("argv.router" in r for r in p["reasons"])
    assert pair(verify.verify_a7(w.root), "s2")["accepted"] is True


# class: new-behaviour (subset of the allowed list is fine)
def test_rule2_difference_subset_is_accepted(verify, make_world):
    w = make_world()
    w.edit_dossier("s1", lambda d: d.update(differences=[x for x in d["differences"] if x["field"] == "argv.worker"]))
    assert pair(verify.verify_a7(w.root), "s1")["accepted"] is True


# class: new-behaviour
@pytest.mark.parametrize("arm,want", [("off", W.OFF_COMMIT), ("on", W.ON_COMMIT)])
def test_rule2_chain_commit_must_equal_v8_base(verify, make_world, arm, want):
    w = make_world()
    wrong = "0" * 40
    w.edit_chain(arm, "s1", lambda c: c["artifacts"]["campaign_core"].update(commit=wrong))
    p = pair(verify.verify_a7(w.root), "s1")
    assert p["accepted"] is False
    assert any(wrong in r or want in r for r in p["reasons"]), "the reason carries the differing value"


# class: new-behaviour (an arm running the OTHER arm's commit is a mismatch too)
def test_rule2_swapped_commits_reject(verify, make_world):
    w = make_world()
    w.edit_chain("off", "s2", lambda c: c["artifacts"]["campaign_core"].update(commit=W.ON_COMMIT))
    assert pair(verify.verify_a7(w.root), "s2")["accepted"] is False


# ----------------------------------------------------------------------------------------------- rule 3 (keys)
# class: new-behaviour (ASSUMPTION: a rejected key does not reject the pair; keys_accepted / keys_rejected report it)
def test_rule3_seed_mismatch_rejects_the_key_only(verify, make_world):
    w = make_world()

    def bump(rows):
        for r in rows:
            if r["id"] == "python/a3":
                r["sampler_seed"] += 1
        return rows
    w.edit_rows("on", "s1", bump)
    p = pair(verify.verify_a7(w.root), "s1")
    assert p["keys_accepted"] == 7
    assert [k["key"] for k in p["keys_rejected"]] == [["s1", "python/a3"]]
    assert p["keys_rejected"][0]["reason"]
    assert p["accepted"] is True
    assert pair(verify.verify_a7(w.root), "s2")["keys_rejected"] == []


# class: new-behaviour (amended, delivery 3: a row renamed to an id its own schedule does not plan, with no item record, is a
# structural problem of that attempt: refusal. The one-sided-key rejection is tested in test_p613_fix_round.py.)
def test_rule3_row_outside_the_planned_slots_refuses(verify, make_world):
    w = make_world()

    def rename(rows):
        for r in rows:
            if r["id"] == "go/g2":
                r["id"] = "go/g2x"
        return rows
    w.edit_rows("on", "s1", rename)
    with pytest.raises(verify.RefusalError, match="go/g2x"):
        verify.verify_a7(w.root)


# class: new-behaviour (a DNF slot has no row but is accounted for: rows + p426_dnf == planned; not a refusal, key stays)
def test_dnf_slot_without_row_is_not_a_refusal(verify, make_world):
    w = make_world(dnf={("on", "s1"): ["go/g3"]})
    p = pair(verify.verify_a7(w.root), "s1")
    assert p["accepted"] is True
    assert p["keys_accepted"] == 8 and p["keys_rejected"] == []


# ----------------------------------------------------------------------------------------------- rule 4 (speed)
# class: new-behaviour (power-invalid stays a quality member)
@pytest.mark.parametrize("arm", ["off", "on"])
def test_rule4_speed_invalid_leg_keeps_quality_member(verify, make_world, arm):
    w = make_world()
    w.edit_leg(arm, "s1", speed_valid=False, speed_reason="power")
    b8 = verify.verify_a7(w.root)
    assert pair(b8, "s1")["accepted"] is True and pair(b8, "s1")["speed_valid"] is False
    assert pair(b8, "s2")["speed_valid"] is True


# ----------------------------------------------------------------------------------------------- rule 5 (dossier / harvest)
# class: new-behaviour
def test_rule5_dossier_verdict_not_pass_rejects(verify, make_world):
    w = make_world()
    w.edit_dossier("s1", lambda d: d.update(verdict="FAIL"))
    p = pair(verify.verify_a7(w.root), "s1")
    assert p["accepted"] is False and any("FAIL" in r or "verdict" in r for r in p["reasons"])


# class: new-behaviour (a dossier whose recorded self-hash is wrong)
def test_rule5_dossier_self_hash_mismatch_rejects(verify, make_world):
    w = make_world()
    w.edit_dossier("s1", lambda d: d.update(at="2030-01-01T00:00:00Z"), seal=False)     # edited, NOT re-sealed
    p = pair(verify.verify_a7(w.root), "s1")
    assert p["accepted"] is False and any("hash" in r.lower() or "sha" in r.lower() for r in p["reasons"])


# class: new-behaviour (dossier must name exactly the two attempts)
@pytest.mark.parametrize("arm", ["off", "on"])
def test_rule5_dossier_names_wrong_attempt_rejects(verify, make_world, arm):
    w = make_world()
    w.edit_dossier("s1", lambda d: d["arms"][arm].update(attempt=W.attempt_name(arm, "s2")))
    p = pair(verify.verify_a7(w.root), "s1")
    assert p["accepted"] is False and any("attempt" in r.lower() or "dossier" in r.lower() for r in p["reasons"])


# class: new-behaviour (a dossier file that is absent: a rejected pair or a refusal — the contract allows either; never accepted)
def test_rule5_dossier_missing_is_never_accepted(verify, make_world):
    w = make_world()
    w.p("wave2", "pairs", "s1__off-a1__on-a1.json").unlink()
    kind, res = outcome(verify, w.root)
    if kind == "returned":
        p = pair(res, "s1")
        assert p["accepted"] is False and any("dossier" in r.lower() for r in p["reasons"])


# class: new-behaviour
def test_rule5_published_main_file_altered_after_harvest_rejects(verify, make_world):
    w = make_world()
    target = next(w.apath("on", "s1", "evidence").rglob("manifest.json"))
    target.write_text(target.read_text() + " ")
    kind, res = outcome(verify, w.root)
    assert kind == "returned"
    p = pair(res, "s1")
    assert p["accepted"] is False and any("manifest.json" in r or "published" in r.lower() for r in p["reasons"])
    assert pair(res, "s2")["accepted"] is True


# class: new-behaviour (a main file listed in HARVEST but absent: never accepted)
def test_rule5_published_main_file_missing_is_never_accepted(verify, make_world):
    w = make_world()
    next(w.apath("off", "s2", "evidence").rglob("manifest.json")).unlink()
    kind, res = outcome(verify, w.root)
    if kind == "returned":
        assert pair(res, "s2")["accepted"] is False


# class: invariant (only `main` files are verified; an `evidence`-destination file need not exist under results_root)
def test_rule5_evidence_destination_files_are_not_required(verify, make_world):
    w = make_world()
    h = w.load("wave2", W.attempt_name("on", "s2"), "HARVEST.json")
    assert any(f["destination"] == "evidence" for f in h["files"])
    assert not any((w.repo / f["published"]).exists() for f in h["files"] if f["destination"] == "evidence")
    assert pair(verify.verify_a7(w.root), "s2")["accepted"] is True


# class: new-behaviour (HARVEST self-hash)
def test_rule5_harvest_self_hash_mismatch_rejects(verify, make_world):
    w = make_world()
    w.edit_json(("wave2", W.attempt_name("off", "s1"), "HARVEST.json"), lambda d: d.update(created="2030-01-01T00:00:00Z"),
                seal=False)
    w.refresh("s1")                                          # the dossier agrees with the new bytes; only the self-hash is off
    kind, res = outcome(verify, w.root)
    if kind == "returned":
        assert pair(res, "s1")["accepted"] is False


# ----------------------------------------------------------------------------------------------- rule 7 (C217 identity)
# class: new-behaviour (identical final trees: key marked identical, still an accepted key)
def test_rule7_identical_final_tree_is_marked(verify, make_world):
    w = make_world(identical={("s1", "python/a2")})
    b8 = verify.verify_a7(w.root)
    p = pair(b8, "s1")
    assert p["keys_accepted"] == 8 and p["accepted"] is True
    blob = p
    marked = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("identical") is True:
                marked.append(json.dumps(n, sort_keys=True))
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(blob)
    assert marked and all("python/a2" in m for m in marked), marked
    assert not any("python/a1" in m for m in marked)


# class: new-behaviour (no identical key anywhere when every final tree differs)
def test_rule7_no_identical_marks_when_trees_differ(verify, make_world):
    b8 = verify.verify_a7(make_world().root)
    assert '"identical": true' not in json.dumps(b8)


# ----------------------------------------------------------------------------------------------- structural refusals
# class: new-behaviour
def test_duplicate_row_key_refuses(verify, make_world):
    w = make_world()

    def dup(rows):
        return rows + [dict(rows[0])]
    w.edit_rows("off", "s1", dup)
    with pytest.raises(verify.RefusalError):
        verify.verify_a7(w.root)


# class: new-behaviour (duplicate across two invocation files of one session)
def test_duplicate_row_key_across_files_refuses(verify, make_world):
    w = make_world()
    files = sorted(w.apath("on", "s2", "s2").glob("*.jsonl"))
    first = files[0].read_text().splitlines()[0]
    files[-1].write_text(files[-1].read_text() + first + "\n")
    with pytest.raises(verify.RefusalError):
        verify.verify_a7(w.root)


# class: new-behaviour (row count != planned slots, no DNF to account for it)
def test_row_count_below_planned_refuses(verify, make_world):
    w = make_world()
    w.edit_rows("on", "s1", lambda rows: rows[:-1])
    with pytest.raises(verify.RefusalError):
        verify.verify_a7(w.root)


# class: new-behaviour
def test_row_count_above_planned_refuses(verify, make_world):
    w = make_world()
    w.edit_rows("off", "s2", lambda rows: rows + [dict(rows[0], id="python/zz")])
    with pytest.raises(verify.RefusalError):
        verify.verify_a7(w.root)


# class: new-behaviour
@pytest.mark.parametrize("victim", ["schedule.json", "leg.json", "chain.json"])
def test_missing_required_file_refuses(verify, make_world, victim):
    w = make_world()
    w.apath("on", "s1", victim).unlink()
    with pytest.raises(verify.RefusalError):
        verify.verify_a7(w.root)


# class: new-behaviour
def test_unreadable_leg_record_refuses(verify, make_world):
    w = make_world()
    w.apath("off", "s2", "leg.json").write_text("{not json")
    with pytest.raises(verify.RefusalError):
        verify.verify_a7(w.root)


# class: new-behaviour
def test_missing_v8_base_refuses(verify, make_world):
    w = make_world()
    w.p("wave2", "run", "v8_base.json").unlink()
    with pytest.raises(verify.RefusalError):
        verify.verify_a7(w.root)


# class: invariant (RefusalError is an Exception; a rejected pair is not one)
def test_refusal_error_is_an_exception(verify):
    assert issubclass(verify.RefusalError, Exception)


# ----------------------------------------------------------------------------------------------- CLI
# class: new-behaviour (rc 0, file == json.dumps(sort_keys, indent=1) + "\n" of the verdict, deterministic)
def test_cli_writes_canonical_json(make_world, tmp_path):
    w = make_world()
    out = tmp_path / "B8.json"
    r = run_cli("bench.p426_verify", ["a7", "--results-root", w.root, "--out", out])
    assert r.returncode == 0, r.stderr
    doc = json.loads(out.read_text())
    assert out.read_text() == json.dumps(doc, sort_keys=True, indent=1) + "\n"
    assert doc["axis"] == "A7"
    out2 = tmp_path / "B8b.json"
    assert run_cli("bench.p426_verify", ["a7", "--results-root", w.root, "--out", out2]).returncode == 0
    assert out.read_bytes() == out2.read_bytes()


# class: new-behaviour (a rejected pair still exits 0)
def test_cli_rc0_with_a_rejected_pair(make_world, tmp_path):
    w = make_world()
    w.edit_leg("on", "s1", state="INVALID")
    out = tmp_path / "B8.json"
    r = run_cli("bench.p426_verify", ["a7", "--results-root", w.root, "--out", out])
    assert r.returncode == 0, r.stderr
    assert [p["accepted"] for p in json.loads(out.read_text())["pairs"] if p["pair"] == "s1"] == [False]


# class: new-behaviour (rc 2, exactly one REFUSED line, nothing written)
def test_cli_refusal_rc2_one_line_nothing_written(make_world, tmp_path):
    w = make_world()
    w.edit_rows("on", "s1", lambda rows: rows[:-1])
    out = tmp_path / "B8.json"
    r = run_cli("bench.p426_verify", ["a7", "--results-root", w.root, "--out", out])
    assert r.returncode == 2
    lines = [l for l in r.stderr.splitlines() if l.strip()]
    assert len(lines) == 1 and lines[0].startswith("REFUSED: ") and len(lines[0]) > len("REFUSED: ")
    assert not out.exists()
