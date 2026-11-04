"""The `all` commands (B8.json + SIGNALS.md + SIGNALS.json): shape, byte-identical regeneration, no absolute path, header, section
order, stale-B8 / regrade-drift refusals, and the step-1 `a7` interfaces unchanged.

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.
"""
from __future__ import annotations

import hashlib
import json
import re

import pytest

from bench.tests.p613s2 import w1view as V
from bench.tests.p613s2 import wave1world as WW


def snap(path):
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file() and ".git" not in p.parts}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """One world, `all` run twice by CLI into two output directories."""
    base = tmp_path_factory.mktemp("allcli")
    with pytest.MonkeyPatch.context() as mp:
        w = WW.Wave1World(base / "w", mp, with_a7=True)
        out1, out2 = base / "out1", base / "out2"
        r1 = V.all_cli(w, out1)
        r2 = V.all_cli(w, out2)
    return w, out1, out2, r1, r2


def ok(run):
    r1, r2, b8, md, js = run
    assert r1.returncode == 0, r1.stderr
    assert r2 is not None and r2.returncode == 0, r2.stderr if r2 is not None else "signals not run"
    return b8, md, js


# class: new-behaviour (`all` writes ONE B8.json (A7 + Wave 1 + cross_wave, json.dumps(sort_keys, indent=1) + newline), then SIGNALS.md + .json)
def test_all_writes_the_three_files(built):
    w, out1, _, r1, _ = built
    b8, md, js = ok(r1)
    text = b8.read_text()
    doc = json.loads(text)
    assert text == json.dumps(doc, sort_keys=True, indent=1) + "\n"
    assert set(doc) >= {"axes", "cross_wave", "inputs"} and set(doc["axes"]) == {"A7", "wave1"}
    assert len(doc["axes"]["wave1"]["pairs"]) == 10
    sig_text = js.read_text()
    assert sig_text == json.dumps(json.loads(sig_text), sort_keys=True, indent=1) + "\n"
    assert md.read_text().endswith("\n") and md.read_text().startswith("# ")


# class: new-behaviour (the same inputs give byte-identical B8.json / SIGNALS.md / SIGNALS.json (no generation time, no iteration-order noise))
def test_all_is_byte_identical_on_rerun(built):
    _, out1, out2, r1, r2 = built
    ok(r1)
    ok(r2)
    for name in ("B8.json", "SIGNALS.md", "SIGNALS.json"):
        assert (out1 / name).read_bytes() == (out2 / name).read_bytes(), name


# class: new-behaviour (... and across two checkouts at different absolute paths: the outputs carry no absolute path)
def test_all_is_byte_identical_across_locations(built, make_w1, tmp_path):
    w, out1, _, r1, _ = built
    ok(r1)
    other = make_w1(with_a7=True)
    assert other.commits == w.commits and str(other.base) != str(w.base)
    r = V.all_cli(other, tmp_path / "elsewhere")
    ok(r)
    for name in ("B8.json", "SIGNALS.md", "SIGNALS.json"):
        assert (tmp_path / "elsewhere" / name).read_bytes() == (out1 / name).read_bytes(), name


# class: new-behaviour (no absolute path, home path or temp path in any output)
def test_outputs_have_no_absolute_path(built):
    w, out1, _, r1, _ = built
    ok(r1)
    forbidden = {str(w.base), str(w.base.resolve()), str(w.repo), str(w.repo.resolve()), "/Users/", "/private/", "/var/folders",
                 "/tmp/", "/home/", "$STACK_WORKDIR", "$HOME"}
    for name in ("B8.json", "SIGNALS.md", "SIGNALS.json"):
        text = (out1 / name).read_text()
        for f in forbidden:
            assert f not in text, (name, f)


# class: new-behaviour (header: generator, version p613-step2, status PROVISIONAL - subjective panel pending (step 3), numpy / scipy, B8 sha, inputs sha)
def test_header(built):
    import numpy
    w, out1, _, r1, _ = built
    ok(r1)
    head = (out1 / "SIGNALS.md").read_text().split("\n## ", 1)[0]
    sig = json.loads((out1 / "SIGNALS.json").read_text())
    assert "p613-step2" in head and "PROVISIONAL — subjective panel pending (step 3)" in head
    assert "bench.p426_signals" in head and numpy.__version__ in head
    assert hashlib.sha256((out1 / "B8.json").read_bytes()).hexdigest() in head
    assert "PROVISIONAL — A7 only" not in head
    hdr = sig["header"]
    assert hdr["generator_version"] == "p613-step2" and hdr["status"] == "PROVISIONAL — subjective panel pending (step 3)"
    assert hdr["b8_sha256"] == hashlib.sha256((out1 / "B8.json").read_bytes()).hexdigest()
    assert hdr["numpy"] == numpy.__version__ and "scipy" in hdr and hdr.get("inputs_sha256")


# class: new-behaviour (sections in the contract's order: A7-s1, A7-s2, A1, M1, A2, A3, A4, mechanical family, flags, noise floor, coverage, pending)
def test_section_order(built):
    _, out1, _, r1, _ = built
    ok(r1)
    heads = [(i, ln) for i, ln in enumerate((out1 / "SIGNALS.md").read_text().splitlines()) if ln.startswith("#")]

    def first(pattern, after=-1):
        for i, ln in heads:
            if i > after and re.search(pattern, ln, re.I):
                return i
        raise AssertionError(f"no heading matching {pattern!r} after line {after}: {[h for _, h in heads]}")
    pos = -1
    for pattern in (r"A7-s1", r"A7-s2", r"\bA1\b", r"\bM1\b", r"\bA2\b", r"\bA3\b", r"\bA4\b", r"family", r"flag", r"noise", r"coverage",
                    r"pending|subjective"):
        nxt = first(pattern, pos)
        assert nxt > pos, pattern
        pos = nxt


# class: new-behaviour (the subjective panel stays "pending (step 3)"; no Wave 1 axis is "pending (step 2)" any more)
def test_pending_is_only_the_panel(built):
    _, out1, _, r1, _ = built
    ok(r1)
    md = (out1 / "SIGNALS.md").read_text()
    assert "pending (step 3" in md and "pending (step 2)" not in md
    assert "pending (step 2)" not in (out1 / "SIGNALS.json").read_text()


# class: new-behaviour (no composite / successes_per_hour / pass@1|converged ranking: none of those is a key or a ranking in the sheet)
def test_no_composite_in_the_sheet(built):
    _, out1, _, r1, _ = built
    ok(r1)
    keys = set()

    def walk(n):
        if isinstance(n, dict):
            for k, v in n.items():
                keys.add(str(k).lower())
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(json.loads((out1 / "SIGNALS.json").read_text()))
    assert not [k for k in keys if "composite" in k or "successes_per_hour" in k or "pass_at_1" in k or "pass@1" in k]


# class: invariant (the in-process pipeline and the CLI agree: compute_all on verify_all's record equals the SIGNALS.json the CLI wrote)
def test_cli_equals_in_process(built, verify, signals, monkeypatch):
    w, out1, _, r1, _ = built
    ok(r1)
    from bench import generate
    monkeypatch.setattr(generate, "RESULTS", w.rows_root)
    b8 = verify.verify_all(w.p426, w.rows_root, w.repo)
    assert (out1 / "B8.json").read_text() == json.dumps(b8, sort_keys=True, indent=1) + "\n"
    sha = hashlib.sha256((out1 / "B8.json").read_bytes()).hexdigest()
    sig = signals.compute_all(w.p426, w.rows_root, b8, b8_sha256=sha)
    assert (out1 / "SIGNALS.json").read_text() == json.dumps(sig, sort_keys=True, indent=1) + "\n"
    assert (out1 / "SIGNALS.md").read_text() == signals.render_md(sig)


# class: invariant (compute_all and verify_all are read-only: the tree is byte-identical afterwards)
def test_pipeline_writes_nothing_into_the_tree(pipe):
    w, _, _ = pipe()
    before = snap(w.rows_root)
    from bench import p426_verify, p426_signals
    b8 = p426_verify.verify_all(w.p426, w.rows_root, w.repo)
    p426_signals.compute_all(w.p426, w.rows_root, b8)
    assert snap(w.rows_root) == before


# ================================================================================================================ refusals
# class: new-behaviour (compute_all refuses when an input changed after B8: the sha drift names the file)
@pytest.mark.parametrize("what", [("math500", "on", "b1", "rows"), ("m1", "off", "b2", "result"), ("reasoning", "on", "b1", "rows")])
def test_compute_all_refuses_on_input_sha_drift(verify, signals, make_w1, what):
    w = make_w1(with_a7=True)
    b8 = verify.verify_all(w.p426, w.rows_root, w.repo)
    path = w.path_of(*what)
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(verify.RefusalError) as e:
        signals.compute_all(w.p426, w.rows_root, b8)
    assert path.name in str(e.value)


# class: new-behaviour (compute_all refuses when a B8 input file is gone)
def test_compute_all_refuses_on_missing_input(verify, signals, make_w1):
    w = make_w1(with_a7=True)
    b8 = verify.verify_all(w.p426, w.rows_root, w.repo)
    w.path_of("cjudge", "on", "b2", "manifest").unlink()
    with pytest.raises(verify.RefusalError):
        signals.compute_all(w.p426, w.rows_root, b8)


# class: new-behaviour (the CLI refuses a stale B8.json: rc 2, `REFUSED:` on stderr, no SIGNALS written)
def test_signals_cli_refuses_stale_b8(make_w1, tmp_path):
    w = make_w1(with_a7=True)
    out = tmp_path / "out"
    r1, _, b8, md, js = V.all_cli(w, out)
    assert r1.returncode == 0, r1.stderr
    p = w.path_of("vision", "on", "b1", "rows")
    p.write_bytes(p.read_bytes() + b"\n")
    r = V.run_cli("bench.p426_signals", ["all", "--results-root", w.p426, "--rows-root", w.rows_root, "--b8", b8,
                                         "--out-md", out / "s2.md", "--out-json", out / "s2.json"], w.rows_root)
    assert r.returncode == 2 and r.stderr.strip().startswith("REFUSED:")
    assert not (out / "s2.md").exists() and not (out / "s2.json").exists()


# class: new-behaviour (the CLI refuses a missing B8.json)
def test_signals_cli_refuses_missing_b8(make_w1, tmp_path):
    w = make_w1(with_a7=True)
    r = V.run_cli("bench.p426_signals", ["all", "--results-root", w.p426, "--rows-root", w.rows_root, "--b8", tmp_path / "none.json",
                                         "--out-md", tmp_path / "s.md", "--out-json", tmp_path / "s.json"], w.rows_root)
    assert r.returncode == 2 and "REFUSED" in r.stderr and not (tmp_path / "s.md").exists()


# class: new-behaviour (A1 regrade drift: the regraded n / errors / correct / acc_strict must equal math500.<tune>.score.json, else RefusalError)
@pytest.mark.parametrize("field,value", [("correct", 4), ("acc_strict", 0.5), ("n", 4), ("errors", 1)])
def test_a1_regrade_drift_refuses(verify, signals, make_w1, field, value):
    w = make_w1(with_a7=True)
    w.edit_json("math500", "on", "b2", "score", lambda d: d.update({field: value}))        # re-scrubbed: only the regrade can notice
    with pytest.raises(verify.RefusalError) as e:
        b8 = verify.verify_all(w.p426, w.rows_root, w.repo)
        signals.compute_all(w.p426, w.rows_root, b8)
    assert "drift" in str(e.value).lower() or "regrade" in str(e.value).lower() or field in str(e.value)


# class: new-behaviour (rows edited AFTER grading without regrading: the score.json no longer matches the rows -> drift refusal)
def test_a1_rows_changed_without_regrade_refuses(verify, signals, make_w1):
    w = make_w1(with_a7=True)
    w.edit_rows("math500", "off", "b1", lambda rows: rows[0].update(content="x \\boxed{99}"), rescore=False)
    with pytest.raises(verify.RefusalError):
        b8 = verify.verify_all(w.p426, w.rows_root, w.repo)
        signals.compute_all(w.p426, w.rows_root, b8)


# class: invariant (a consistent regrade (score.json rewritten by the grader) is not drift)
def test_a1_consistent_regrade_is_accepted(pipe):
    w, b8, sig = pipe(rows={("math500", "on", "b1"): {"test/algebra/1.json": {"ok": False}}})
    assert V.accepted_all(b8) and sig


# ===================================================================================================== step-1 `a7` unchanged
# class: invariant (the `a7` commands still work with their step-1 arguments and write the step-1 sheet: version p613-step1, A7 only)
def test_a7_commands_are_unchanged(make_w1, tmp_path):
    w = make_w1(with_a7=True)
    b8, md, js = tmp_path / "B8.json", tmp_path / "S.md", tmp_path / "S.json"
    r1 = V.run_cli("bench.p426_verify", ["a7", "--results-root", w.p426, "--out", b8], w.rows_root)
    assert r1.returncode == 0, r1.stderr
    r2 = V.run_cli("bench.p426_signals", ["a7", "--results-root", w.p426, "--b8", b8, "--out-md", md, "--out-json", js], w.rows_root)
    assert r2.returncode == 0, r2.stderr
    doc = json.loads(b8.read_text())
    assert doc["axis"] == "A7" and [p["pair"] for p in doc["pairs"] if p["role"] == "pair"] == ["s1", "s2"]
    text = md.read_text()
    assert "PROVISIONAL — A7 only" in text and "p613-step1" in text and "p613-step2" not in text
    assert "A1" not in "".join(l for l in text.splitlines() if l.startswith("## "))


# class: invariant (verify_a7 / compute_a7 return what they returned: the A7 member of `all` is verify_a7's record, byte for byte)
def test_all_embeds_the_step1_a7_record(verify, signals, make_w1):
    w = make_w1(with_a7=True)
    all_ = verify.verify_all(w.p426, w.rows_root, w.repo)
    a7 = verify.verify_a7(w.p426)
    assert json.dumps(all_["axes"]["A7"], sort_keys=True) == json.dumps(a7, sort_keys=True)
    sig7 = signals.compute_a7(w.p426, a7)
    assert sig7["header"]["generator_version"] == "p613-step1" and sig7["header"]["status"] == "PROVISIONAL — A7 only"


# class: new-behaviour (the A7 sections of the `all` sheet equal compute_a7's sessions (A7 as in step 1))
def test_all_sheet_a7_part_equals_compute_a7(pipe, signals):
    w, b8, sig = pipe()
    sig7 = signals.compute_a7(w.p426, b8["axes"]["A7"])
    pool = V.numbers([sig])
    for s in ("s1", "s2"):
        rec = sig7["sessions"][s]
        assert V.has(pool, rec["permutation_p"], 1e-9)
        for key in ("delta", "lo", "hi", "loss_bound_pp"):
            assert V.has(pool, rec["paired_strict"][key] if key != "loss_bound_pp" else rec["paired_strict"][key] / 100.0, 1e-4)
        assert V.has(pool, rec["speed"]["primary"]["geomean_ratio"], 1e-3)
        assert V.has(pool, rec["speed"]["acceptance"]["on"]["acceptance"], 1e-3)
