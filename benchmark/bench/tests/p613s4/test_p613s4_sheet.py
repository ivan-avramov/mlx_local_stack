"""`p426_signals all --panel <dir> --evidence-ref <sha>`: the divergence section, the FINAL status, the flag, the inputs,
regeneration, and the path WITHOUT `--evidence-ref` (the step-3 record, unchanged).

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.

Readings tested (contract text; JSON key names are searched, see dview.py):
* SIGNALS.json gains a top-level `divergence` record (the heading names it: "## A7 first divergence (C284; `divergence`)");
* status `FINAL — P426 certification evidence` in the title line and `header.status`; the header records the evidence ref;
* the section sits after the subjective section (§4.5) and before "## Flags";
* `inputs` gains one `evidence:<ref>:<repo-relative path>` entry per events file read (22 accepted keys x 2 arms = 44 in world A);
* a FLAG per generation item (world A: two-fer, eta in s1; kappa, rho in s2); none in world B.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from bench.tests.p613s3 import s3world as S
from bench.tests.p613s4 import dview as D
from bench.tests.p613s4 import s4world as W

GEN_A = sorted(key for key, v in W.EXPECT_A.items() if v[0] == "generation")
ORDINARY_KEYS = ("A7", "A1", "M1", "A2", "A3", "A4", "family", "subjective", "noise_floor", "coverage", "identity", "cross_wave")


@pytest.fixture(scope="module")
def final_a(cli_a, panel_a, tmp_path_factory):
    md, js = D.must_run(cli_a, tmp_path_factory.mktemp("finalA"), panel_a)
    return md.read_text(), json.loads(js.read_text()), md, js


@pytest.fixture(scope="module")
def final_b(cli_b, panel_b, tmp_path_factory):
    md, js = D.must_run(cli_b, tmp_path_factory.mktemp("finalB"), panel_b)
    return md.read_text(), json.loads(js.read_text())


@pytest.fixture(scope="module")
def step3_a(cli_a, panel_a, tmp_path_factory):
    """`all --panel` WITHOUT `--evidence-ref`."""
    md, js = D.must_run(cli_a, tmp_path_factory.mktemp("step3A"), panel_a, ref=None)
    return md.read_text(), json.loads(js.read_text())


# ------------------------------------------------------------------------------------------------------------- status
# class: new-behaviour (FINAL status in the title line and header.status; both worlds)
def test_status_final(final_a, final_b):
    for md, sig in (final_a[:2], final_b):
        assert md.splitlines()[0] == f"# P426 signals — {D.FINAL}"
        assert sig["header"]["status"] == D.FINAL
        assert "PROVISIONAL" not in md.splitlines()[0] and "PROVISIONAL" not in sig["header"]["status"]


# class: new-behaviour (no pending entry still says step 4 / step 3: every pre-registered section is present)
def test_no_pending_step_left(final_a):
    md, sig = final_a[:2]
    assert not any("step 4" in str(v) or "step 3" in str(v) for v in sig["pending"].values()), sig["pending"]
    assert "pending (step 4)" not in md


# class: new-behaviour (the header records the evidence ref, in the JSON header and in the sheet head)
def test_header_records_evidence_ref(cli_a, final_a):
    md, sig = final_a[:2]
    ref = cli_a.evidence_ref
    # header.panel already carries the PANEL's own evidence ref (step 3): the new record must be outside it
    outside = {k: v for k, v in sig["header"].items() if k != "panel"}
    assert ref in [v for _, v in _scalars(outside)], outside
    assert ref in "\n".join(md.splitlines()[:20])


def _scalars(node, path=()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _scalars(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _scalars(v, path + (i,))
    else:
        yield path, node


# ------------------------------------------------------------------------------------------------------------- section
# class: new-behaviour (the section exists with the contract heading, after §4.5 and before the flags)
def test_section_heading_and_position(final_a):
    md = final_a[0]
    assert md.count(D.HEADING) == 1
    i = md.index(D.HEADING)
    assert md.index("## Subjective panel (§4.5; `subjective`)") < i < md.index("## Flags (`flags`")


# class: new-behaviour (the scope label is in the section)
def test_section_label(final_a):
    assert D.LABEL in D.section(final_a[0])


# class: new-behaviour (SIGNALS.json carries the record under `divergence`; items + counts equal the expected tables)
def test_json_record_cli_a(final_a):
    sig = final_a[1]
    assert "divergence" in sig
    assert set(D.items(sig["divergence"])) == set(W.EXPECT_A)
    assert {k: v[0] for k, v in D.items(sig["divergence"]).items()} == {k: v[0] for k, v in W.EXPECT_A.items()}
    c = D.counts(sig["divergence"])
    exp = W.counts_of(W.EXPECT_A)
    assert (c["s1"], c["s2"], c["both"]) == (exp["s1"], exp["s2"], D.pooled(exp))


# class: new-behaviour (the sheet text lists every item with its kind; `environment` also with the tool name; per session)
def test_section_lists_items_with_kind(final_a):
    sec = D.section(final_a[0])
    for (s, rid), (kind, k, tool) in sorted(W.EXPECT_A.items()):
        lines = [l for l in sec.splitlines() if rid in l]
        assert lines, f"{rid} is not listed in the section"
        assert any(kind in l for l in lines), (rid, kind, lines)
        if kind == "environment":
            assert any(tool in l for l in lines), (rid, tool, lines)
    assert "go/psi" not in sec                                   # the rejected key is not in the section


# class: new-behaviour (items sorted by id within a session; s1 block before s2 block)
def test_section_items_sorted_by_id(final_a):
    sec = D.section(final_a[0])
    for s in ("s1", "s2"):
        ids = sorted(rid for (ss, rid) in W.EXPECT_A if ss == s)
        pos = [sec.index(f"`{rid}`") if f"`{rid}`" in sec else sec.index(rid) for rid in ids]
        assert pos == sorted(pos), (s, ids, pos)


# class: new-behaviour (the section's counts appear in the text: per kind per session and pooled)
def test_section_counts_in_text(final_a):
    sec = D.section(final_a[0])
    for kind in W.KINDS:
        assert kind in sec
    exp = W.counts_of(W.EXPECT_A)
    for total in (sum(exp["s1"].values()), sum(exp["s2"].values()), 22):
        assert str(total) in sec, total


# ---------------------------------------------------------------------------------------------------------------- flag
# class: new-behaviour (flag raised when an item is `generation`: the flag lists those items)
def test_flag_raised_cli_a(final_a):
    md, sig = final_a[:2]
    flags = D.divergence_flags(sig)
    assert flags, [f["text"] for f in sig["flags"]]
    blob = json.dumps(flags)
    for s, rid in GEN_A:
        assert rid in blob, (rid, flags)
    flag_section = md[md.index("## Flags (`flags`"):]
    flag_section = flag_section[: flag_section.find("\n## ", 5)] if "\n## " in flag_section[5:] else flag_section
    for s, rid in GEN_A:
        assert rid in flag_section


# class: new-behaviour (flag NOT raised when no accepted item is generation, although the rejected key is)
def test_flag_not_raised_cli_b(final_b):
    md, sig = final_b
    assert D.divergence_flags(sig) == [], D.divergence_flags(sig)
    assert "divergence" in sig and all(v[0] != "generation" for v in D.items(sig["divergence"]).values())
    assert D.LABEL in D.section(md)
    assert "go/psi" not in D.section(md)


# class: invariant (a flag is listed, never a veto: the CLI still exits 0 and the section is present)
def test_flag_is_not_a_veto(final_a):
    assert D.HEADING in final_a[0]


# ---------------------------------------------------------------------------------------------------------------- inputs
# class: new-behaviour (inputs: one `evidence:<ref>:<path>` entry per events file read; sha = the bytes read; accepted keys only)
def test_inputs_record_evidence_reads(cli_a, final_a):
    sig = final_a[1]
    ref = cli_a.evidence_ref
    pre = f"evidence:{ref}:"
    got = {k[len(pre):]: v for k, v in sig["inputs"].items() if k.startswith(pre)}
    want = {}
    for (s, rid) in W.EXPECT_A:
        for arm in ("off", "on"):
            rel = W.events_rel(cli_a, arm, s, rid)
            want[rel] = hashlib.sha256(D.git_bytes(cli_a.repo, ref, rel)).hexdigest()
    assert set(got) == set(want) and len(got) == 44
    assert not any("go__psi" in k for k in got)
    assert sig["header"]["n_inputs"] == len(sig["inputs"])
    for rel in got:
        assert rel.startswith("benchmark/results/p426/wave2/") and rel.endswith(".events.jsonl")


# class: invariant (the pre-existing inputs are untouched by the new entries)
def test_existing_inputs_unchanged(final_a, step3_a):
    inputs_new, inputs_old = final_a[1]["inputs"], step3_a[1]["inputs"]
    assert {k: v for k, v in inputs_new.items() if not k.startswith("evidence:")} == inputs_old


# --------------------------------------------------------------------------------------------------------- regeneration
# class: new-behaviour (byte-identical regeneration into another directory)
def test_regeneration_byte_identical(cli_a, panel_a, final_a, tmp_path):
    md0, js0 = final_a[2], final_a[3]
    md1, js1 = D.must_run(cli_a, tmp_path / "again", panel_a)
    assert md1.read_bytes() == md0.read_bytes()
    assert js1.read_bytes() == js0.read_bytes()


# class: new-behaviour (regeneration from a copy of the repository at another path is byte-identical: no path leaks in)
def test_regeneration_from_a_copy_identical(clone_cli_a, panel_a, final_a, tmp_path):
    case = clone_cli_a()
    md1, js1 = D.must_run(case, tmp_path / "copyrun", panel_a, ref=case.evidence_ref)
    assert md1.read_bytes() == final_a[2].read_bytes()
    assert js1.read_bytes() == final_a[3].read_bytes()


# class: invariant (the divergence record never mentions the timestamp / session id / message id of the synthetic transcripts)
def test_no_transcript_noise_in_outputs(final_a):
    blob = final_a[0] + json.dumps(final_a[1]["divergence"])
    for needle in ("ses_off_", "ses_on_", "msg_off", "msg_on", "private thoughts", "snapoff", "snapon"):
        assert needle not in blob


# ------------------------------------------------------------------------------------------------ the no-ref path (E1-like)
# class: invariant (no `--evidence-ref` -> the step-3 record: status, generator, no divergence section / key / ref)
def test_no_ref_path_is_step3(step3_a, cli_a):
    md, sig = step3_a
    assert sig["header"]["status"] == D.STEP3_STATUS
    assert sig["header"]["generator_version"] == "p613-step3"
    assert md.splitlines()[0] == f"# P426 signals — {D.STEP3_STATUS}"
    assert "divergence" not in sig and "first divergence" not in md
    # (the panel's own evidence ref is already printed by the step-3 sheet: only the new header record / inputs are asserted)
    assert not any(k.startswith("evidence:") for k in sig["inputs"])
    assert cli_a.evidence_ref not in [v for _, v in _scalars({k: v for k, v in sig["header"].items() if k != "panel"})]
    assert "final sheet + recommendation" in sig["pending"]


# class: invariant (adding `--evidence-ref` is additive: every pre-existing top-level record is equal to the no-ref run's)
def test_ref_is_additive(final_a, step3_a):
    new, old = final_a[1], step3_a[1]
    for key in ORDINARY_KEYS:
        assert new[key] == old[key], key
    assert [f for f in new["flags"] if f not in D.divergence_flags(new)] == old["flags"]


# class: invariant (no panel, no ref -> the step-2 record, status "subjective panel pending (step 3)")
def test_no_panel_no_ref_is_step2(cli_a, panel_a, tmp_path):
    md, js = D.must_run(cli_a, tmp_path / "s2", panel_a, ref=None, with_panel=False)
    sig = json.loads(js.read_text())
    assert sig["header"]["status"] == D.STEP2_STATUS and "divergence" not in sig and "subjective" not in sig


# class: new-behaviour (`--evidence-ref` WITHOUT `--panel`: never FINAL — refused, or a non-final status; no panel = no §4.5)
def test_ref_without_panel_is_not_final(cli_a, panel_a, tmp_path):
    proc, md, js = D.run_all(cli_a, tmp_path / "np", panel_a, with_panel=False)
    if proc.returncode != 0:
        S.refused_cli(proc)
        assert not md.exists() and not js.exists()
    else:
        assert json.loads(js.read_text())["header"]["status"] != D.FINAL


# ------------------------------------------------------------------------------------------------------------ refusals
# class: new-behaviour (an unresolvable ref -> exit non-zero, REFUSED on stderr, no output file)
@pytest.mark.parametrize("ref", ["0" * 40, "zzzz"])
def test_cli_bad_ref_refused(cli_a, panel_a, tmp_path, ref):
    proc, md, js = D.run_all(cli_a, tmp_path / "bad", panel_a, ref=ref)
    S.refused_cli(proc)
    assert "REFUSED" in proc.stderr and not md.exists() and not js.exists()


# class: invariant (a refusal does not clobber an existing sheet at the output path)
def test_refusal_keeps_existing_output(cli_a, panel_a, tmp_path):
    out = tmp_path / "keep"
    md, js = D.must_run(cli_a, out, panel_a)
    before = (md.read_bytes(), js.read_bytes())
    proc, md2, js2 = D.run_all(cli_a, out, panel_a, ref="0" * 40)
    assert proc.returncode != 0
    assert (md.read_bytes(), js.read_bytes()) == before
