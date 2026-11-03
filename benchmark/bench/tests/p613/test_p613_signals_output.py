"""B6 outputs: SIGNALS.md / SIGNALS.json header, determinism, no absolute paths, staleness refusal, CLI return codes.

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.
"""
from __future__ import annotations

import hashlib
import json
import re

import pytest

from bench.tests.p613 import a7world as W
from bench.tests.p613 import sigview as V
from bench.tests.p613.sigview import run_cli


def cli_sig(w, tmp_path, b8_name="B8.json", tag=""):
    """Run both CLIs on world `w`; returns (rc_b8, rc_sig, paths)."""
    b8 = tmp_path / f"{tag}{b8_name}"
    md, js = tmp_path / f"{tag}SIGNALS.md", tmp_path / f"{tag}SIGNALS.json"
    r1 = run_cli("bench.p426_verify", ["a7", "--results-root", w.root, "--out", b8])
    r2 = run_cli("bench.p426_signals", ["a7", "--results-root", w.root, "--b8", b8, "--out-md", md, "--out-json", js])
    return r1, r2, (b8, md, js)


# ===================================================================================================== function level
# class: new-behaviour (compute_a7 is deterministic)
def test_compute_is_deterministic(make_world, verify, signals):
    w = make_world()
    b8 = verify.verify_a7(w.root)
    a, b = signals.compute_a7(w.root, b8), signals.compute_a7(w.root, b8)
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
    assert signals.render_md(a) == signals.render_md(b)


# class: new-behaviour (the document is JSON-serialisable with only native types)
def test_signals_are_json_native(pipeline):
    _, _, sig = pipeline()
    json.dumps(sig, sort_keys=True)


# class: new-behaviour (header: generator name, PROVISIONAL A7 only, numpy and scipy versions, inputs sha set)
def test_header_in_md_and_json(pipeline, signals):
    import numpy
    import scipy
    w, b8, sig = pipeline()
    md = signals.render_md(sig)
    head = md[:3000]
    assert "p426_signals" in head
    assert "PROVISIONAL — A7 only" in head
    assert numpy.__version__ in head and scipy.__version__ in head
    blob = json.dumps(sig, sort_keys=True)
    assert "PROVISIONAL — A7 only" in json.dumps(sig, ensure_ascii=False)
    assert numpy.__version__ in blob and scipy.__version__ in blob
    for sha in b8["inputs"].values():
        assert sha in blob, "the inputs sha set is in the sheet"


# class: new-behaviour (the sheet lists the pending sections instead of omitting them)
def test_md_lists_pending_sections(pipeline, signals):
    _, _, sig = pipeline()
    md = signals.render_md(sig).lower()
    assert "pending" in md and "subjective" in md and "memory" in md


# class: new-behaviour (layout: A7-s1, A7-s2, flags, noise floor, coverage)
def test_md_sections(pipeline, signals):
    _, _, sig = pipeline()
    md = signals.render_md(sig)
    for needle in ("A7-s1", "A7-s2"):
        assert needle in md
    lowered = md.lower()
    for needle in ("flags", "noise floor", "coverage"):
        assert needle in lowered, needle


# class: new-behaviour (the md carries the labels the JSON carries)
def test_md_carries_labels(pipeline, signals):
    _, _, sig = pipeline(rows={("off", "s1"): {i: {"passed": False} for i in W.DEFAULT_IDS["s1"]}})
    md = signals.render_md(sig)
    assert "shown difference" in md and "WASH — directional (not a shown difference)" in md


# class: new-behaviour (never a composite or a ranking by pass@1|converged)
def test_md_has_no_composite_or_hours_metric(pipeline, signals):
    _, _, sig = pipeline()
    # amended (delivery 3): the sheet's own disclaimer line names the forbidden metrics; everything else must not
    lines = [l for l in signals.render_md(sig).lower().splitlines() if not l.startswith("- no composite")]
    md = "\n".join(lines)
    assert "successes_per_hour" not in md and "composite" not in md and "pass@1|converged" not in md
    assert "successes_per_hour" not in V.text(sig).lower() and "composite" not in V.text(sig).lower()


# class: new-behaviour (no absolute path, no tmp path, no home path: dict and md)
def test_no_absolute_paths_in_outputs(pipeline, signals):
    w, _, sig = pipeline()
    for blob in (json.dumps(sig, sort_keys=True, ensure_ascii=False), signals.render_md(sig)):
        assert str(w.base) not in blob and str(w.root) not in blob
        for bad in ("/Users/", "/private/", "/var/folders", "/tmp/", "$STACK_WORKDIR"):
            assert bad not in blob, bad


# class: new-behaviour (byte-identical from the same inputs located elsewhere: no path or clock leaks in)
def test_identical_outputs_from_two_locations(make_world, verify, signals):
    a, b = make_world(), make_world()
    sa = signals.compute_a7(a.root, verify.verify_a7(a.root))
    sb = signals.compute_a7(b.root, verify.verify_a7(b.root))
    assert json.dumps(sa, sort_keys=True, default=str) == json.dumps(sb, sort_keys=True, default=str)
    assert signals.render_md(sa) == signals.render_md(sb)


# ===================================================================================================== staleness (B8 vs files now)
def mutate_an_input(w, b8, suffix):
    rel = next(r for r in sorted(b8["inputs"]) if r.endswith(suffix))
    path = w.root / rel
    path.write_bytes(path.read_bytes() + b"\n")
    return rel


# class: new-behaviour (any input sha that differs from the file now refuses)
@pytest.mark.parametrize("suffix", [".jsonl", "leg.json", "schedule.json", "chain.json", "HARVEST.json"])
def test_stale_b8_refuses(make_world, verify, signals, suffix):
    w = make_world()
    b8 = verify.verify_a7(w.root)
    mutate_an_input(w, b8, suffix)
    with pytest.raises(verify.RefusalError):
        signals.compute_a7(w.root, b8)


# class: new-behaviour (an item record is an input too: editing it after B8 refuses)
def test_stale_item_record_refuses(make_world, verify, signals):
    w = make_world()
    b8 = verify.verify_a7(w.root)
    rel = next(r for r in sorted(b8["inputs"]) if "/items/" in r)
    p = w.root / rel
    p.write_bytes(p.read_bytes() + b" ")
    with pytest.raises(verify.RefusalError):
        signals.compute_a7(w.root, b8)


# class: new-behaviour (a required input missing now refuses)
def test_missing_input_refuses(make_world, verify, signals):
    w = make_world()
    b8 = verify.verify_a7(w.root)
    rel = next(r for r in sorted(b8["inputs"]) if r.endswith("leg.json"))
    (w.root / rel).unlink()
    with pytest.raises(verify.RefusalError):
        signals.compute_a7(w.root, b8)


# class: new-behaviour (a hand-edited sha in B8.json itself refuses)
def test_forged_input_sha_refuses(make_world, verify, signals):
    w = make_world()
    b8 = verify.verify_a7(w.root)
    key = sorted(b8["inputs"])[0]
    b8["inputs"][key] = "0" * 64
    with pytest.raises(verify.RefusalError):
        signals.compute_a7(w.root, b8)


# class: invariant (an untouched B8 does not refuse)
def test_fresh_b8_does_not_refuse(make_world, verify, signals):
    w = make_world()
    signals.compute_a7(w.root, verify.verify_a7(w.root))


# ===================================================================================================== CLI
# class: new-behaviour (rc 0; both files written; header sha == sha256 of the B8.json bytes passed in)
def test_cli_writes_md_and_json(make_world, tmp_path):
    w = make_world()
    r1, r2, (b8, md, js) = cli_sig(w, tmp_path)
    assert r1.returncode == 0, r1.stderr
    assert r2.returncode == 0, r2.stderr
    doc = json.loads(js.read_text())
    sha = hashlib.sha256(b8.read_bytes()).hexdigest()
    assert sha in md.read_text()[:4000] and sha in json.dumps(doc)
    assert "PROVISIONAL — A7 only" in md.read_text()


# class: new-behaviour (byte-identical regeneration, and from a second copy of the inputs)
def test_cli_regeneration_is_byte_identical(make_world, tmp_path):
    w1, w2 = make_world(), make_world()
    _, rc_a, (b8a, mda, jsa) = cli_sig(w1, tmp_path, tag="a_")
    _, rc_b, (b8b, mdb, jsb) = cli_sig(w1, tmp_path, tag="b_")
    _, rc_c, (b8c, mdc, jsc) = cli_sig(w2, tmp_path, tag="c_")
    assert rc_a.returncode == rc_b.returncode == rc_c.returncode == 0
    assert mda.read_bytes() == mdb.read_bytes() == mdc.read_bytes()
    assert jsa.read_bytes() == jsb.read_bytes() == jsc.read_bytes()
    assert b8a.read_bytes() == b8b.read_bytes() == b8c.read_bytes()


# class: new-behaviour (the CLI outputs contain no absolute path)
def test_cli_outputs_have_no_absolute_path(make_world, tmp_path):
    w = make_world()
    _, r2, (b8, md, js) = cli_sig(w, tmp_path)
    assert r2.returncode == 0, r2.stderr
    for path in (md, js, b8):
        blob = path.read_text()
        assert str(w.base) not in blob and str(tmp_path) not in blob and "/Users/" not in blob


# class: new-behaviour (stale B8: rc 2, exactly one REFUSED line on stderr, nothing written)
def test_cli_stale_b8_refuses(make_world, tmp_path, verify):
    w = make_world()
    r1, _, (b8, md, js) = cli_sig(w, tmp_path)
    assert r1.returncode == 0
    md.unlink()
    js.unlink()
    rel = next(r for r in sorted(json.loads(b8.read_text())["inputs"]) if r.endswith("leg.json"))
    (w.root / rel).write_bytes((w.root / rel).read_bytes() + b"\n")
    r = run_cli("bench.p426_signals", ["a7", "--results-root", w.root, "--b8", b8, "--out-md", md, "--out-json", js])
    assert r.returncode == 2
    lines = [l for l in r.stderr.splitlines() if l.strip()]
    assert len(lines) == 1 and lines[0].startswith("REFUSED: ") and len(lines[0]) > 9
    assert not md.exists() and not js.exists()


# class: new-behaviour (missing B8 file: rc 2 REFUSED, nothing written)
def test_cli_missing_b8_refuses(make_world, tmp_path):
    w = make_world()
    md, js = tmp_path / "S.md", tmp_path / "S.json"
    r = run_cli("bench.p426_signals", ["a7", "--results-root", w.root, "--b8", tmp_path / "nope.json",
                                       "--out-md", md, "--out-json", js])
    assert r.returncode == 2 and r.stderr.strip().startswith("REFUSED: ")
    assert not md.exists() and not js.exists()


# class: new-behaviour (a refusal leaves a previously written sheet untouched)
def test_cli_refusal_does_not_overwrite_existing_sheet(make_world, tmp_path):
    w = make_world()
    _, r2, (b8, md, js) = cli_sig(w, tmp_path)
    assert r2.returncode == 0
    before = (md.read_bytes(), js.read_bytes())
    rel = next(r for r in sorted(json.loads(b8.read_text())["inputs"]) if r.endswith("schedule.json"))
    (w.root / rel).write_bytes((w.root / rel).read_bytes() + b"\n")
    r = run_cli("bench.p426_signals", ["a7", "--results-root", w.root, "--b8", b8, "--out-md", md, "--out-json", js])
    assert r.returncode == 2
    assert (md.read_bytes(), js.read_bytes()) == before
