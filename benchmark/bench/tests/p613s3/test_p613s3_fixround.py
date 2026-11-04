"""Fix round (designer dispositions, fixes 3-12): one `reproduces-failure` test per fix, each a reproducible failing case on the
unfixed candidate. (Fixes 1 and 2 -- E1 `--panel` optional, E3 A1 eligibility -- are tests in test_p613s3_signals.py /
test_p613s3_golden.py / test_p613s3_export.py.)

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.

Readings (the dispositions fix behaviour, not key names): FROZEN.json keeps `items` (with `len_on` / `len_off` / `on_slot` when the
candidate's layout survives), `judges`, `files`; verdicts are produced by the code under test (`a7-seal`, `a7-cursor` with a fake
agent), never hand-written, so any FROZEN binding they carry is the implementation's own.
"""
from __future__ import annotations

import inspect
import json
import shutil

import pytest

from bench.p426_verify import RefusalError
from bench.tests.p613s3 import s3world as S
from bench.tests.p613s3 import sigview as V

PLAN = {**V.PLAN_S1, **V.PLAN_S2_OFF}
ALPHA_SESSION = "s1"


@pytest.fixture(scope="module")
def panel():
    import importlib
    return importlib.import_module("bench.p426_panel")


@pytest.fixture(scope="module")
def case(tmp_path_factory):
    return S.A7Case(tmp_path_factory.mktemp("fixcase"), with_rejected=False)


@pytest.fixture(scope="module")
def run1(case, panel, tmp_path_factory):
    """One complete panel (S1 plan) + one successful `all --panel` run: (panel dir, md, json)."""
    out = tmp_path_factory.mktemp("fix1") / "panel"
    assert case.export(out).returncode == 0
    V.write_verdicts(out, PLAN, panel)
    proc, md, js = V.run_all(case, tmp_path_factory.mktemp("fix1out"), out)
    assert proc.returncode == 0, proc.stderr[-600:]
    return out, md, js


def packet_text(out, rid, judge=V.CLA, order="AB"):
    for r in S.manifest_of(out):
        if S.short_id(r["item_id"], V.ALL_IDS) == rid and r["judge"] == judge and r["order"] == order:
            return r, V.packet_of(out, r).read_text()
    raise KeyError(rid)


# ------------------------------------------------------------------------------------------------------------------ fix 3
# class: reproduces-failure (FROZEN.json edited after the verdicts: lengths, slots or judge fields are not sealed -> the sheet must refuse)
@pytest.mark.parametrize("what", ["len_on", "on_slot", "judge_model"])
def test_fix3_frozen_json_tampered_after_verdicts_refuses_the_sheet(case, run1, tmp_path, what):
    out, _, _ = run1
    copy = tmp_path / "panel"
    shutil.copytree(out, copy)
    path = copy / "FROZEN.json"
    doc = json.loads(path.read_text())
    if what == "len_on":
        doc["items"][0]["len_on"] += 7
    elif what == "on_slot":
        if "on_slot" not in doc["items"][0]:
            pytest.skip("FROZEN.json items carry no on_slot key")
        doc["items"][0]["on_slot"] = "A" if doc["items"][0]["on_slot"] == "B" else "B"
    else:
        doc["judges"][1]["model"] = "some-other-model"
    path.write_text(json.dumps(doc, sort_keys=True, indent=1) + "\n")
    proc, md, js = V.run_all(case, tmp_path / "o", copy)
    S.refused_cli(proc)
    assert not md.exists() and not js.exists()


# ------------------------------------------------------------------------------------------------------------------ fix 4
# class: reproduces-failure (a verdict whose provenance disagrees with FROZEN's judge list is rejected, never reported)
def test_fix4_forged_provenance_in_a_verdict_is_not_reported(case, run1, tmp_path):
    out, _, _ = run1
    copy = tmp_path / "panel"
    shutil.copytree(out, copy)
    forged = next(p for p in sorted(copy.glob(f"{V.CLA}/batch*/p*.verdict.json")))
    doc = json.loads(forged.read_text())
    doc.update(model="forged-model", family="openai", client="forged-client", client_version="forged-9")
    forged.write_text(json.dumps(doc) + "\n")
    proc, md, js = V.run_all(case, tmp_path / "o", copy)
    if proc.returncode == 0:
        text = js.read_text() + md.read_text()
        assert "forged-model" not in text and "forged-9" not in text and "forged-client" not in text
        assert V.subjective(V.load(js))["families"] == ["anthropic", "openai"]
    else:
        S.refused_cli(proc)


# class: reproduces-failure (a verdict that arrives pre-sealed with forged fields is not skipped by `a7-seal`: normalised or rejected)
def test_fix4_pre_sealed_forged_verdict_is_not_trusted(case, panel, tmp_path):
    out = tmp_path / "panel"
    assert case.export(out).returncode == 0
    row = next(r for r in S.manifest_of(out) if r["judge"] == V.CLA)
    packet = V.packet_of(out, row)
    verdict = packet.with_name(row["pkt"] + ".verdict.json")
    verdict.write_text(json.dumps(dict(choice="A", rationale="r", judge="claude-opus-5-5", family="openai", client="forged",
                                       model="forged-model", client_version="forged-9", packet_sha=S.sha_file(packet),
                                       attachment_sha=None, prompt_sha="0" * 64)) + "\n")
    proc = S.run_cli("bench.p426_panel", ["a7-seal", "--out", out, "--judge", V.CLA, "--client-version", "2.3.4"], home=tmp_path)
    assert proc.returncode == 0, proc.stderr[-400:]
    marker = packet.with_name(row["pkt"] + ".failed.txt")
    if marker.exists():                         # rejected: a permanent failed marker (the file may stay); ingest counts it `failed`
        pass
    else:                                       # or normalised from FROZEN's judge list
        d = json.loads(verdict.read_text())
        assert d["model"] == "claude-opus-5-5" and d["family"] == "anthropic" and d["client_version"] == "2.3.4"
        assert d["prompt_sha"] == panel.rubric_sha("code")
    _, rows, report = panel.a7_ingest(out)      # either way the forged fields never become a row, and the verdict is counted
    assert not [r for r in rows if r["pkt"] == row["pkt"] and r["model"] != "claude-opus-5-5"]
    assert report["failed"] + report["rejected"] + len(rows) >= 1


# ------------------------------------------------------------------------------------------------------------------ fix 5
# class: reproduces-failure (retries 0 across invocations: a packet whose call failed is never called again by a later `a7-cursor`)
def test_fix5_second_cursor_run_does_not_recall_a_failed_packet(case, tmp_path):
    out = tmp_path / "panel"
    assert case.export(out).returncode == 0
    fake = S.install_fake_cursor(tmp_path / "bin")
    log = tmp_path / "calls.log"
    bad = [r["pkt"] for r in S.manifest_of(out) if r["judge"] == V.CUR][:2]

    def run(fail):
        return S.run_cli("bench.p426_panel", ["a7-cursor", "--out", out, "--judge", V.CUR], path_prefix=str(fake), home=tmp_path,
                         env_extra={"FAKE_CURSOR_LOG": str(log), "FAKE_CURSOR_FAIL": ",".join(fail)})
    assert run(bad).returncode == 0
    first = log.read_text().split()
    assert all(first.count(p) == 1 for p in bad) and len(first) == 28
    run([])                                                                  # the agent would now succeed
    second = log.read_text().split()
    assert all(second.count(p) == 1 for p in bad), "a failed packet was called again on the second invocation"
    assert len(second) == 28


# ------------------------------------------------------------------------------------------------------------------ fix 6
@pytest.fixture(scope="module")
def spaced(tmp_path_factory, panel):
    text = "def f(x):\n    total = x   \n    return total + 1\n"             # a trailing-whitespace line in the ON solution
    c = S.A7Case(tmp_path_factory.mktemp("spaced"), with_rejected=False, texts={("on", "s1", "python/alpha"): text})
    out = tmp_path_factory.mktemp("spacedout") / "panel"
    proc = c.export(out)
    return c, out, proc, text


# class: reproduces-failure (the packet carries the EXACT diff: nothing is rewritten, trailing whitespace included)
def test_fix6_exact_diff_is_never_rewritten(spaced):
    c, out, proc, text = spaced
    assert proc.returncode == 0, proc.stderr[-400:]
    exact = S.expected_diff(S.START, text, "sol.py")
    assert "total = x   \n" in exact
    for judge in (V.CLA, V.CUR):
        for order in ("AB", "BA"):
            _, packet = packet_text(out, "python/alpha", judge, order)
            assert exact in packet, f"{judge} {order}: the diff in the packet differs from the exact diff"


# class: reproduces-failure (the judged length equals the rendered packet text: the diff, or its rendered solution section)
def test_fix6_judged_length_is_the_rendered_text(spaced):
    c, out, proc, text = spaced
    exact_on = S.expected_diff(S.START, text, "sol.py")
    exact_off = S.expected_diff(S.START, S.OFF_SOLUTION, "sol.py")
    item = next(i for i in json.loads((out / "FROZEN.json").read_text())["items"] if i["id"] == "python/alpha")
    row, packet = packet_text(out, "python/alpha")
    on_tune = "p426s2-on"
    on_is_a = f"@{on_tune}::" in row["a_key"]
    sections = {k: packet.split(f"## Response {k}\n", 1)[1].split("\n## Response ", 1)[0].split("\nWhich response", 1)[0].strip()
                for k in ("A", "B")}
    on_sec, off_sec = (sections["A"], sections["B"]) if on_is_a else (sections["B"], sections["A"])
    assert item["len_on"] in (len(exact_on), len(on_sec)), (item["len_on"], len(exact_on), len(on_sec))
    assert item["len_off"] in (len(exact_off), len(off_sec)), (item["len_off"], len(exact_off), len(off_sec))


# ------------------------------------------------------------------------------------------------------------------ fix 7
# class: reproduces-failure (the production CLI takes only the COMMITTED B8.json / universe.json, byte-equal to HEAD)
@pytest.mark.parametrize("which", ["b8", "universe"])
def test_fix7_uncommitted_copy_outside_the_repo_is_refused(case, tmp_path, which):
    copy = tmp_path / f"{which}.json"
    src = case.b8_path if which == "b8" else case.universe
    shutil.copyfile(src, copy)                                          # identical bytes, not the committed path
    args = case.export_args(tmp_path / "panel", b8_path=copy if which == "b8" else None)
    if which == "universe":
        args[args.index("--universe") + 1] = copy
    proc = S.run_cli("bench.p426_panel", args)
    S.refused_cli(proc)
    assert not (tmp_path / "panel" / "FROZEN.json").exists()


# class: reproduces-failure (the committed path edited in the work tree no longer equals `git show HEAD:<path>` -> refused)
@pytest.mark.parametrize("which", ["b8", "universe"])
def test_fix7_modified_committed_file_is_refused(clone_case, tmp_path, which):
    c = clone_case()
    f = c.b8_path if which == "b8" else c.universe
    f.write_text(f.read_text() + "\n")
    proc = c.export(tmp_path / "panel")
    S.refused_cli(proc)
    assert not (tmp_path / "panel" / "FROZEN.json").exists()


@pytest.fixture
def clone_case(case, tmp_path_factory):
    def _clone():
        dst = tmp_path_factory.mktemp("fixclone") / "c"
        shutil.copytree(case.base, dst, symlinks=True)
        return S.A7Case.attach(dst)
    return _clone


# ------------------------------------------------------------------------------------------------------------------ fix 8
# class: reproduces-failure (a malformed and an invalid-choice Claude verdict do not abort sealing; both are counted missing)
def test_fix8_bad_claude_verdicts_are_missing_not_fatal(case, panel, tmp_path):
    out = tmp_path / "panel"
    assert case.export(out).returncode == 0
    bad = {("python/alpha", V.CLA, "AB"): "this is {not json",
           ("go/zeta", V.CLA, "BA"): json.dumps({"choice": "C", "rationale": "x"})}
    V.write_verdicts(out, PLAN, panel, bare_override=bad, seal=False)
    proc = S.run_cli("bench.p426_panel", ["a7-seal", "--out", out, "--judge", V.CLA, "--client-version", "2.3.4"], home=tmp_path)
    assert proc.returncode == 0, f"sealing aborted: {proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else proc.stderr}"
    for (rid, judge, order) in bad:
        row = next(r for r in S.manifest_of(out)
                   if S.short_id(r["item_id"], V.ALL_IDS) == rid and r["judge"] == judge and r["order"] == order)
        f = V.packet_of(out, row).with_name(row["pkt"] + ".verdict.json")
        if f.exists():
            try:
                d = json.loads(f.read_text())
            except ValueError:
                continue
            assert not ("packet_sha" in d and d.get("choice") not in ("A", "B", "tie")), "an invalid verdict was sealed"
    good = [r for r in S.manifest_of(out) if r["judge"] == V.CLA and S.short_id(r["item_id"], V.ALL_IDS) == "go/eta"]
    assert all("packet_sha" in json.loads(V.packet_of(out, r).with_name(r["pkt"] + ".verdict.json").read_text()) for r in good)
    proc, md, js = V.run_all(case, tmp_path / "o", out)
    assert proc.returncode == 0, proc.stderr[-400:]
    m = V.member(V.load(js), "A7-s1")
    assert V.judged_n(m) == 4 and V.count(V.field(m, "missing_verdicts")) == 2


# ------------------------------------------------------------------------------------------------------------------ fix 9
# class: reproduces-failure (`a7_packet` has exactly the contract's seven parameters; no private extras in the public signature)
def test_fix9_a7_packet_signature_is_exact(panel):
    assert list(inspect.signature(panel.a7_packet).parameters) == [
        "results_root", "b8", "item", "evidence_ref", "polyglot_root", "universe_path", "repo"]


# ----------------------------------------------------------------------------------------------------------------- fix 10
# class: reproduces-failure (a duplicated manifest row must not drive `missing_verdicts` negative: refusal, or a non-negative count)
def test_fix10_duplicate_verdict_row_gives_no_negative_missing(case, panel, tmp_path):
    out = tmp_path / "panel"
    assert case.export(out).returncode == 0
    mpath = out / "manifest.jsonl"
    old_sha = S.sha_file(mpath)
    rows = mpath.read_text().splitlines()
    first_claude = next(l for l in rows if json.loads(l)["judge"] == V.CLA)
    mpath.write_text("\n".join(rows + [first_claude]) + "\n")                      # the same row listed twice (re-frozen by hand)
    fz = out / "FROZEN.json"
    fz.write_text(fz.read_text().replace(old_sha, S.sha_file(mpath)))
    try:
        V.write_verdicts(out, PLAN, panel)
    except AssertionError as exc:
        assert "REFUSED" in str(exc)                                                  # refused while sealing: nothing to count
        return
    proc, md, js = V.run_all(case, tmp_path / "o", out)
    if proc.returncode != 0:
        S.refused_cli(proc)
        return
    sub = V.subjective(V.load(js))
    for name, m in sub["members"].items():
        assert V.count(m.get("missing_verdicts")) >= 0, f"{name}: negative missing_verdicts {m.get('missing_verdicts')}"


# ----------------------------------------------------------------------------------------------------------------- fix 11
# class: reproduces-failure (a stray file in the panel directory is not part of the frozen set: changing / removing it is ignored)
def test_fix11_stray_file_is_ignored_by_check_frozen(case, panel, tmp_path):
    out = tmp_path / "panel"
    assert case.export(out).returncode == 0
    meta = json.loads((out / "FROZEN.json").read_text())
    (out / "FROZEN.json").unlink()
    (out / ".DS_Store").write_bytes(b"\x00junk")
    (out / "notes.txt").write_text("scratch\n")
    judges = panel.load_judges(case.judges, "text")
    panel.freeze(out, meta, judges, "code")
    frozen_text = (out / "FROZEN.json").read_text()
    assert ".DS_Store" not in frozen_text and "notes.txt" not in frozen_text
    (out / ".DS_Store").write_bytes(b"\x00changed")
    (out / "notes.txt").unlink()
    (out / "later.log").write_text("x\n")
    assert panel.check_frozen(out)


# ----------------------------------------------------------------------------------------------------------------- fix 12
# class: reproduces-failure (spec §4.5: the A4 row is reported -- descriptive, 0.5 identical, judged 0 -- and never tested)
def test_fix12_a4_row_is_descriptive_and_untested(run1):
    _, md, js = run1
    sig = V.load(js)
    m = V.member(sig, "A4")
    assert V.judged_n(m) == 0
    assert V.field(m, "score_identical", "mean_with_identical") == 0.5
    assert "descriptive" in json.dumps(m).lower()
    assert "A4" not in V.family(sig)["tested"] and V.family(sig)["m"] == 2
    assert V.field(m, "permutation_p", default=None) is None and V.field(m, "holm_p", default=None) is None
    assert "- A4 (`subjective.descriptive.A4`)" in md.read_text()        # the rendered A4 line (a bullet, not a table row)
