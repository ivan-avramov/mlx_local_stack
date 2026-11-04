"""Delivery 3: tests for the designer's fixes 1-4 and the two GLM test gaps (F2, and F4 which lives in the golden module).

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.
`reproduces-failure` = fails on the unfixed candidate and must pass once the fix is applied.

* fix 1  a `tool_use` event without `state.input` / `state.output` (or without `state`) -> RefusalError naming the item;
* fix 2  `_final_ready`: FINAL needs `set(blocks) == {b1, b2}` with every block accepted, for A1 / M1 / A2 / A3 / A4;
* fix 3  `header.evidence_ref` = the resolved FULL sha, the `evidence:<full sha>:` prefix, `evidence_ref_given` = the string as passed;
* fix 4  `--evidence-ref` without `--panel` refuses (rc 2, nothing written);
* F2     a B8-rejected A7 session -> not FINAL and `header.final.missing` names it.
"""
from __future__ import annotations

import copy
import json

import pytest

from bench.tests.p613s3 import s3world as S
from bench.tests.p613s3 import sigview as SV
from bench.tests.p613s4 import dview as D
from bench.tests.p613s4 import s4world as W

AXES = ("A1", "M1", "A2", "A3", "A4")


# ------------------------------------------------------------------------------------------------------------ fix 1
@pytest.fixture(scope="module", params=["no_input", "no_output", "no_state"])
def damaged(request, tmp_path_factory):
    return request.param, W.build_case(tmp_path_factory.mktemp("s4damaged" + request.param), "C:" + request.param,
                                       with_rejected=False)


# class: reproduces-failure (fix 1: a retained tool event lacking state.input / state.output / state -> RefusalError naming the item;
# the file is HARVEST-bound and hash-correct, so the refusal is the parser's)
def test_tool_event_without_required_state_refused(divmod_, damaged):
    variant, case = damaged
    exc = D.refuses_as_refusal(D.a7_div, divmod_, case)
    assert "python/alpha" in str(exc), f"{variant}: the refusal does not name the item: {exc}"


# class: reproduces-failure (fix 1 at the parser: the same three damages, no I/O)
@pytest.mark.parametrize("variant", ["no_input", "no_output", "no_state"])
def test_parse_messages_refuses_damaged_tool_event(divmod_, variant):
    text = W.damage(W.events_for("off", "s1", "python/alpha", W.contiguous(W._base("x"))), variant)
    D.refuses_as_refusal(divmod_.parse_messages, text.encode(), "where python/alpha")


# class: invariant (the undamaged transcript of the same item parses; and an `output` that is an EMPTY string is a real output)
def test_parse_messages_accepts_complete_events(divmod_):
    order = W.contiguous([[W.T("t"), W.X("shell", {"command": "true"}, "")]])
    assert len(divmod_.parse_messages(W.events_for("on", "s1", "python/alpha", order).encode(), "w")) == 1


# ------------------------------------------------------------------------------------------------------------ fix 2
@pytest.fixture(scope="module")
def final_rec(cli_a, panel_a, tmp_path_factory):
    md, js = D.must_run(cli_a, tmp_path_factory.mktemp("fix2"), panel_a)
    return json.loads(js.read_text())


# class: invariant (control: the complete hermetic record is ready, every axis has exactly {b1, b2})
def test_final_ready_control(final_rec):
    from bench import p426_signals as PS

    for ax in AXES:
        assert set(final_rec[ax]["blocks"]) == {"b1", "b2"}, ax
    assert PS._final_ready(final_rec) == {"ready": True, "missing": []}


# class: reproduces-failure (fix 2: an axis whose blocks lack b2 (or b1) is not FINAL and the axis is named)
@pytest.mark.parametrize("block", ["b1", "b2"])
@pytest.mark.parametrize("axis", AXES)
def test_axis_missing_a_block_is_not_final(final_rec, axis, block):
    from bench import p426_signals as PS

    rec = copy.deepcopy(final_rec)
    del rec[axis]["blocks"][block]
    got = PS._final_ready(rec)
    assert got["ready"] is False and axis in got["missing"], got


# class: invariant (a block that is present but not accepted is not FINAL either — the pre-fix behaviour, kept)
@pytest.mark.parametrize("axis", AXES)
def test_axis_unaccepted_block_is_not_final(final_rec, axis):
    from bench import p426_signals as PS

    rec = copy.deepcopy(final_rec)
    rec[axis]["blocks"]["b2"]["status"] = "rejected"
    got = PS._final_ready(rec)
    assert got["ready"] is False and axis in got["missing"], got


# class: invariant (a missing panel / an incomplete divergence section / a non-accepted A7 session each block FINAL and are named)
def test_final_ready_names_other_missing_parts(final_rec):
    from bench import p426_signals as PS

    r1 = copy.deepcopy(final_rec)
    del r1["subjective"]
    assert PS._final_ready(r1)["missing"] == ["panel"]
    r2 = copy.deepcopy(final_rec)
    r2["divergence"]["complete"] = False
    assert PS._final_ready(r2)["missing"] == ["divergence"]
    r3 = copy.deepcopy(final_rec)
    r3["A7"]["sessions"]["s2"]["status"] = "rejected"
    assert PS._final_ready(r3)["missing"] == ["A7-s2"]


# ------------------------------------------------------------------------------------------------------------ fix 3
def _given(sig):
    for holder in (sig["header"], sig.get("divergence") or {}):
        if "evidence_ref_given" in holder:
            return holder["evidence_ref_given"]
    raise AssertionError("no `evidence_ref_given` in header or divergence")


# class: reproduces-failure (fix 3: `evidence_ref_given` is present and is the string as passed; `evidence_ref` stays the full sha)
@pytest.mark.parametrize("form", ["short", "full"])
def test_evidence_ref_given_is_as_passed(cli_a, panel_a, tmp_path, form):
    full = cli_a.evidence_ref
    passed = full[:12] if form == "short" else full
    md, js = D.must_run(cli_a, tmp_path / "o", panel_a, ref=passed)
    sig = json.loads(js.read_text())
    assert _given(sig) == passed
    assert sig["header"]["evidence_ref"] == full
    assert sum(1 for k in sig["inputs"] if k.startswith(f"evidence:{full}:")) == 44
    assert not any(k.startswith(f"evidence:{passed}:") for k in sig["inputs"] if passed != full)


# class: invariant (the sheet text records the resolved full sha, whichever form was passed)
def test_sheet_records_full_sha_when_short_passed(cli_a, panel_a, tmp_path):
    md, js = D.must_run(cli_a, tmp_path / "o", panel_a, ref=cli_a.evidence_ref[:12])
    assert cli_a.evidence_ref in "\n".join(md.read_text().splitlines()[:20])


# class: invariant (short and full form of the same ref differ ONLY in `evidence_ref_given`)
def test_short_and_full_ref_differ_only_in_given(cli_a, panel_a, tmp_path):
    a = json.loads(D.must_run(cli_a, tmp_path / "a", panel_a, ref=cli_a.evidence_ref[:12])[1].read_text())
    b = json.loads(D.must_run(cli_a, tmp_path / "b", panel_a, ref=cli_a.evidence_ref)[1].read_text())
    for rec in (a, b):
        rec["header"].pop("evidence_ref_given", None)
        rec["divergence"].pop("evidence_ref_given", None)
    assert a == b


# ------------------------------------------------------------------------------------------------------------ fix 4
# class: reproduces-failure (fix 4: `--evidence-ref` without `--panel` refuses with rc 2 and writes nothing)
def test_ref_without_panel_refuses_rc2(cli_a, panel_a, tmp_path):
    proc, md, js = D.run_all(cli_a, tmp_path / "np", panel_a, with_panel=False)
    assert proc.returncode == 2, (proc.returncode, proc.stderr[-300:])
    S.refused_cli(proc)
    assert "REFUSED" in proc.stderr and "--panel" in proc.stderr
    assert not md.exists() and not js.exists()


# ------------------------------------------------------------------------------------------------------------ GLM F2
@pytest.fixture(scope="module")
def rejected_s1(cli_a, tmp_path_factory):
    """A copy of the CLI world whose s1 ON attempt has an edited HARVEST.json: B8 rule 5 rejects pair s1 (the hermetic way to a
    B8-rejected A7 session); B8 is re-verified and committed, a fresh panel is exported and judged on it."""
    import shutil

    from bench.tests.p613 import a7world
    from bench import p426_panel

    base = tmp_path_factory.mktemp("s4rej")
    dst = base / "copy"
    shutil.copytree(cli_a.base, dst, symlinks=True)
    case = S.A7Case.attach(dst)
    att = case.attempt("on", "s1")
    h = json.loads((att / "HARVEST.json").read_text())
    rel = W.events_rel(case, "on", "s1", "python/alpha")
    [f for f in h["files"] if f.get("published") == rel][0]["published_sha256"] = "0" * 64
    (att / "HARVEST.json").write_text(a7world.dumps(a7world.sealed({k: v for k, v in h.items() if k != "sha256"})))
    b8 = case.reverify()
    S.git(case.repo, "add", "-A")
    S.git(case.repo, "commit", "-q", "-m", "world: s1 rejected")
    pair = {p["pair"]: p for p in b8["axes"]["A7"]["pairs"] if p["role"] == "pair"}
    assert pair["s1"]["accepted"] is False and pair["s2"]["accepted"] is True, "the hermetic edit must reject s1 only"
    out = base / "panel"
    proc = case.export(out)
    assert proc.returncode == 0, proc.stderr[-600:]
    SV.write_verdicts(out, {**SV.PLAN_S1, **SV.PLAN_S2_ON}, p426_panel)
    return case, out


# class: invariant (GLM F2: with a B8-rejected A7 session the sheet is generated but NOT final, and `missing` names the session)
def test_b8_rejected_a7_session_blocks_final(rejected_s1, tmp_path):
    case, panel = rejected_s1
    proc, md, js = D.run_all(case, tmp_path / "o", panel)
    assert proc.returncode == 0, proc.stderr[-800:]
    sig, text = json.loads(js.read_text()), md.read_text()
    assert sig["header"]["status"] != D.FINAL and D.FINAL not in text
    assert "A7-s1" in sig["header"]["final"]["missing"] and sig["header"]["final"]["ready"] is False
    assert sig["divergence"]["complete"] is False
    assert sig["divergence"]["sessions"]["s1"]["status"] != "accepted"
    assert "A7-s1" in text[: text.index("## ")] or "A7-s1" in text           # named on the sheet too
