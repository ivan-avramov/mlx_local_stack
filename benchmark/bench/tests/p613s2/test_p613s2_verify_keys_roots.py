"""B8 Wave 1 rules 3 (keys), 7 (C217 identity), the deny-list / excluded members, the root-equality refusals, structural refusals.

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.
"""
from __future__ import annotations

import shutil

import pytest

from bench.tests.p613s2 import w1view as V
from bench.tests.p613s2 import wave1world as WW

ROW_KINDS = ("math500", "cjudge", "vision", "reasoning")
BLOCK_NAME = {"b1": "block1", "b2": "block2"}


# ======================================================================================================== deny-list / excluded
def replace_with_symlink(path, target):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()
    path.symlink_to(target)


# class: new-behaviour (a pair member resolving to a *-smoke leg refuses; nothing of the smoke is scored)
@pytest.mark.parametrize("kind", ("math500", "m1"))
def test_leg_dir_resolving_to_a_smoke_leg_refuses(verify, make_w1, kind):
    w = make_w1()
    replace_with_symlink(w.leg_dir(kind, "on", "b1"), w.w1 / f"{kind}-p426s2-on-smoke")
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426, w.rows_root, w.repo)


# class: new-behaviour (a leg resolving to archive/ refuses)
def test_leg_dir_resolving_to_archive_refuses(verify, make_w1):
    w = make_w1()
    replace_with_symlink(w.leg_dir("m1", "off", "b2"), w.w1 / "archive" / "m1-p426s2-off-smoke.attempt1-fork-venv")
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426, w.rows_root, w.repo)


# class: new-behaviour (a leg resolving to the S build wave1/ refuses)
def test_leg_dir_resolving_to_the_s_build_refuses(verify, make_w1):
    w = make_w1()
    replace_with_symlink(w.leg_dir("cjudge", "off", "b1"), w.p426 / "wave1")
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426, w.rows_root, w.repo)


# class: new-behaviour (a row file resolving to a smoke tune or to an S-build tune p426-<arm>-* refuses)
@pytest.mark.parametrize("target", ["math500.p426s2-on-smoke.jsonl", "math500.p426-on-b1.jsonl"])
def test_rows_file_resolving_to_a_deny_listed_tune_refuses(verify, make_w1, target):
    w = make_w1()
    replace_with_symlink(w.path_of("math500", "on", "b1", "rows"), w.edir / target)
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426, w.rows_root, w.repo)


# class: invariant (smokes, archive/ and the S build sit in the tree and are never members, never inputs)
def test_excluded_members_are_present_and_ignored(wave1):
    w, b8 = wave1()
    assert (w.w1 / "math500-p426s2-on-smoke").is_dir() and (w.edir / "math500.p426-on-b1.jsonl").is_file()
    legs = {p["off"] for p in b8["pairs"]} | {p["on"] for p in b8["pairs"]}
    assert not [x for x in legs if "smoke" in x] and len(legs) == 20
    assert not [k for k in b8["inputs"] if "smoke" in k or "archive" in k or "/wave1/" in k]


# ================================================================================================================= rule 3: keys
# class: new-behaviour (a row count != the ids.json block size refuses)
@pytest.mark.parametrize("kind", ROW_KINDS)
def test_row_count_below_block_size_refuses(verify, make_w1, kind):
    w = make_w1()
    w.edit_rows(kind, "on", "b1", lambda rows: rows[:-1])
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426, w.rows_root, w.repo)


# class: new-behaviour (an extra row refuses: count != block size)
def test_row_count_above_block_size_refuses(verify, make_w1):
    w = make_w1()
    w.edit_rows("math500", "off", "b2", lambda rows: rows + [dict(rows[0], id="test/algebra/777.json")])
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426, w.rows_root, w.repo)


# class: new-behaviour (a duplicate row key refuses)
@pytest.mark.parametrize("kind", ("math500", "cjudge", "vision"))
def test_duplicate_row_key_refuses(verify, make_w1, kind):
    w = make_w1()
    w.edit_rows(kind, "on", "b1", lambda rows: rows[:-1] + [copy_row(rows[0])])
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426, w.rows_root, w.repo)


def copy_row(r):
    return dict(r)


# class: new-behaviour (same count, but the id set != the block list: refused or the pair rejected; never accepted)
@pytest.mark.parametrize("kind", ("math500", "cjudge", "vision"))
def test_id_set_differs_from_the_block_list(verify, make_w1, kind):
    w = make_w1()
    w.edit_rows(kind, "on", "b1", lambda rows: rows[:-1] + [dict(rows[-1], id="not-in-the-plan")])
    assert V.refused_or_rejected(lambda: verify.verify_wave1(w.p426, w.rows_root, w.repo),
                                 lambda b8: not V.pair(b8, kind, "b1")["accepted"])


# class: new-behaviour (A4 task seeds != the ids.json block list: refused or rejected)
def test_a4_task_seeds_differ_from_the_block_list(verify, make_w1):
    w = make_w1()
    w.edit_rows("reasoning", "on", "b1", lambda rows: rows[0].update(seed=128000009))
    assert V.refused_or_rejected(lambda: verify.verify_wave1(w.p426, w.rows_root, w.repo),
                                 lambda b8: not V.pair(b8, "reasoning", "b1")["accepted"])


# class: new-behaviour (a seed mismatch rejects THAT key; the pair stays, keys_accepted = n - 1; the key is named)
@pytest.mark.parametrize("kind,field", [("math500", "sampler_seed"), ("cjudge", "sampler_seed"), ("vision", "seed")])
def test_seed_mismatch_rejects_the_key_only(verify, make_w1, kind, field):
    w = make_w1()
    rid = w.ids[kind]["block1"][0]
    w.edit_rows(kind, "on", "b1", lambda rows: [r.update({field: 4242}) for r in rows if r["id"] == rid])
    b8 = verify.verify_wave1(w.p426, w.rows_root, w.repo)
    p = V.pair(b8, kind, "b1")
    assert p["accepted"] is True and p["keys_accepted"] == len(w.ids[kind]["block1"]) - 1
    assert len(p["keys_rejected"]) == 1 and rid in str(p["keys_rejected"][0]["key"])
    assert "seed" in p["keys_rejected"][0]["reason"].lower()
    assert V.accepted_all(b8)


# class: new-behaviour (A4: a sampler_seed that is not request_seeds[str(task seed)] rejects that key; the pair stays)
def test_a4_sampler_seed_must_match_request_seeds(verify, make_w1):
    w = make_w1()
    task = w.ids["reasoning"]["block2"][1]
    w.edit_rows("reasoning", "on", "b2", lambda rows: [r.update(sampler_seed=5) for r in rows if r["seed"] == task])
    b8 = verify.verify_wave1(w.p426, w.rows_root, w.repo)
    p = V.pair(b8, "reasoning", "b2")
    assert p["accepted"] is True and p["keys_accepted"] == 1
    assert len(p["keys_rejected"]) == 1 and str(task) in str(p["keys_rejected"][0]["key"])


# class: new-behaviour (A4: the same wrong sampler_seed in BOTH arms is still a request_seeds mismatch)
def test_a4_sampler_seed_wrong_in_both_arms(verify, make_w1):
    w = make_w1()
    task = w.ids["reasoning"]["block1"][0]
    for arm in WW.ARMS:
        w.edit_rows("reasoning", arm, "b1", lambda rows: [r.update(sampler_seed=5) for r in rows if r["seed"] == task])
    b8 = verify.verify_wave1(w.p426, w.rows_root, w.repo)
    p = V.pair(b8, "reasoning", "b1")
    assert p["keys_accepted"] == 1 and len(p["keys_rejected"]) == 1


# class: new-behaviour (blocks of one kind must be disjoint: an id (or task seed) in both blocks refuses)
@pytest.mark.parametrize("kind", ROW_KINDS)
def test_overlapping_blocks_refuse(verify, make_w1, kind):
    w = make_w1()

    def overlap(doc):
        axes = doc["axes"][kind]
        axes["block2"] = [axes["block1"][0]] + list(axes["block2"][1:])
    w.edit_ids(overlap)
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426, w.rows_root, w.repo)


# ============================================================================================ required files (structural refusals)
# class: new-behaviour (a missing required input refuses: ids.json, frozen.s2.json, a receipt, a row file, an M1 result)
@pytest.mark.parametrize("what", ["ids", "frozen", "receipt", "rows", "manifest", "m1_result", "m1_job", "m1_report"])
def test_missing_required_file_refuses(verify, make_w1, what):
    w = make_w1()
    target = {"ids": w.p426 / "ids.json", "frozen": w.w1 / "run" / "frozen.s2.json",
              "receipt": w.path_of("cjudge", "on", "b1", "receipt"), "rows": w.path_of("vision", "off", "b2", "rows"),
              "manifest": w.path_of("math500", "on", "b2", "manifest"), "m1_result": w.path_of("m1", "on", "b1", "result"),
              "m1_job": w.path_of("m1", "off", "b1", "job"), "m1_report": w.path_of("m1", "on", "b2", "report")}[what]
    target.unlink()
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426, w.rows_root, w.repo)


# class: new-behaviour (unreadable JSON in a required input refuses)
@pytest.mark.parametrize("what", ["ids", "frozen", "receipt", "m1_result"])
def test_unreadable_json_refuses(verify, make_w1, what):
    w = make_w1()
    target = {"ids": w.p426 / "ids.json", "frozen": w.w1 / "run" / "frozen.s2.json",
              "receipt": w.path_of("math500", "off", "b1", "receipt"), "m1_result": w.path_of("m1", "off", "b2", "result")}[what]
    target.write_text("{not json")
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426, w.rows_root, w.repo)


# class: new-behaviour (a missing SCRUB_MANIFEST: refused or the pair rejected; never silently accepted)
def test_missing_scrub_manifest_is_not_accepted(verify, make_w1):
    w = make_w1()
    w.path_of("math500", "on", "b1", "scrub").unlink()
    assert V.refused_or_rejected(lambda: verify.verify_wave1(w.p426, w.rows_root, w.repo),
                                 lambda b8: not V.pair(b8, "math500", "b1")["accepted"])


# class: new-behaviour (a refusal writes nothing: the CLI leaves no B8.json and exits 2 with `REFUSED: <reason>`)
def test_cli_all_refuses_with_rc2_and_writes_nothing(make_w1, tmp_path):
    w = make_w1()
    w.path_of("math500", "on", "b1", "rows").unlink()
    r1, r2, b8, md, js = V.all_cli(w, tmp_path / "out")
    assert r1.returncode == 2 and r1.stderr.strip().startswith("REFUSED:") and "\n" not in r1.stderr.strip()
    assert not b8.exists() and r2 is None


# ============================================================================================================== root equality
# class: new-behaviour (rows_root must equal bench.generate.results_root() (A1 regrades through it), else RefusalError)
def test_rows_root_must_equal_generate_results_root(verify, make_w1, monkeypatch, tmp_path):
    w = make_w1()
    from bench import generate
    other = tmp_path / "other_results"
    other.mkdir()
    monkeypatch.setattr(generate, "RESULTS", other)
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426, w.rows_root, w.repo)
    with pytest.raises(verify.RefusalError):
        verify.verify_all(w.p426, w.rows_root, w.repo)


# class: new-behaviour (results_root must equal rows_root / "p426")
def test_results_root_must_be_rows_root_p426(verify, make_w1, tmp_path):
    w = make_w1()
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426 / "wave1.s2", w.rows_root, w.repo)
    clone = tmp_path / "clone"
    shutil.copytree(w.p426, clone)
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(clone, w.rows_root, w.repo)


# class: invariant (equality is on resolved paths: a symlinked spelling of the same directories is accepted)
def test_root_equality_uses_resolved_paths(verify, make_w1, tmp_path):
    w = make_w1()
    link = tmp_path / "results_link"
    link.symlink_to(w.rows_root)
    b8 = verify.verify_wave1(link / "p426", link, w.repo)
    assert V.accepted_all(b8)


# class: new-behaviour (verify_all enforces the same root rules as verify_wave1)
def test_verify_all_results_root_mismatch_refuses(verify, make_w1, tmp_path):
    w = make_w1(with_a7=True)
    clone = tmp_path / "clone"
    shutil.copytree(w.p426, clone)
    with pytest.raises(verify.RefusalError):
        verify.verify_all(clone, w.rows_root, w.repo)


# =============================================================================================================== rule 7: identity
# class: new-behaviour (a tampered content_sha256 (A1 / A2) is recomputed and refuses, in either arm)
@pytest.mark.parametrize("kind", ("math500", "cjudge"))
@pytest.mark.parametrize("arm", WW.ARMS)
def test_tampered_content_sha256_refuses(verify, make_w1, kind, arm):
    w = make_w1()
    w.edit_rows(kind, arm, "b1", lambda rows: rows[1].update(content_sha256="00" * 32), rescore=False)
    with pytest.raises(verify.RefusalError):
        verify.verify_wave1(w.p426, w.rows_root, w.repo)


# class: new-behaviour (the golden relation: all keys of an unmodified pair are `identical`, counted as {n, of} per pair)
def test_identical_outputs_are_counted(wave1):
    w, b8 = wave1()
    for p in b8["pairs"]:
        if p["kind"] == "m1":
            continue
        assert p["identical"] == {"n": p["keys_accepted"], "of": p["keys_accepted"]}, p["kind"]
        assert all(k["identical"] is True for k in p["keys"])


# class: new-behaviour (A1: a different ON content makes that key not identical; the pair stays accepted)
def test_a1_different_content_is_not_identical(verify, make_w1):
    w = make_w1()
    w.edit_rows("math500", "on", "b2", lambda rows: rows[2].update(content="another derivation \\boxed{7}"))
    b8 = verify.verify_wave1(w.p426, w.rows_root, w.repo)
    p = V.pair(b8, "math500", "b2")
    assert p["accepted"] and p["identical"] == {"n": 4, "of": 5}
    assert [k["identical"] for k in p["keys"]].count(False) == 1


# class: new-behaviour (A2: same)
def test_a2_different_content_is_not_identical(verify, make_w1):
    w = make_w1()
    w.edit_rows("cjudge", "off", "b1", lambda rows: rows[0].update(content="# a different essay"))
    p = V.pair(verify.verify_wave1(w.p426, w.rows_root, w.repo), "cjudge", "b1")
    assert p["accepted"] and p["identical"] == {"n": 2, "of": 3}


# class: new-behaviour (A3: identity is the sha256 of the `description` text (the row carries no sha field))
def test_a3_identity_is_the_description_sha(verify, make_w1):
    w = make_w1()
    w.edit_rows("vision", "on", "b1", lambda rows: rows[0].update(description="A different description."))
    p = V.pair(verify.verify_wave1(w.p426, w.rows_root, w.repo), "vision", "b1")
    assert p["accepted"] and p["identical"] == {"n": 1, "of": 2}


# class: new-behaviour (A3: a different verdict or decode rate with the SAME description stays identical)
def test_a3_identity_ignores_other_fields(verify, make_w1):
    w = make_w1()
    w.edit_rows("vision", "on", "b2", lambda rows: rows[0].update(verdict="FAIL", decode_tps=99.0))
    p = V.pair(verify.verify_wave1(w.p426, w.rows_root, w.repo), "vision", "b2")
    assert p["identical"] == {"n": 2, "of": 2}


# class: new-behaviour (A4: identity is the sha256 of the draw's `content`)
def test_a4_identity_is_the_content_sha(verify, make_w1):
    w = make_w1()
    w.edit_rows("reasoning", "on", "b1", lambda rows: rows[1].update(content="Tracing it differently."))
    p = V.pair(verify.verify_wave1(w.p426, w.rows_root, w.repo), "reasoning", "b1")
    assert p["accepted"] and p["identical"] == {"n": 1, "of": 2}


# class: new-behaviour (the content sha is the sha of the UTF-8 bytes: non-ASCII content with a matching sha is accepted)
def test_non_ascii_content_with_matching_sha_is_accepted(verify, make_w1):
    w = make_w1()
    w.edit_rows("math500", "on", "b1", lambda rows: rows[0].update(content="Antwort: \\boxed{7} — ü ∑"))
    w.edit_rows("math500", "off", "b1", lambda rows: rows[0].update(content="Antwort: \\boxed{7} — ü ∑"))
    p = V.pair(verify.verify_wave1(w.p426, w.rows_root, w.repo), "math500", "b1")
    assert p["accepted"] and p["identical"]["n"] == 5
