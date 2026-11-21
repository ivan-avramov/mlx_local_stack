"""M76 B4b-2 §7.1 / §7.2 / §7.3 on `main`'s committed records: `B8.json` regenerates byte-identically in every state; with no
`B8-A8.json` the signals sheets (`SIGNALS.md`, `SIGNALS-partial.md` and their JSON) regenerate byte-identically; with the
`B8-A8.json` of the harvested tg2 pilot pair (new identity; a shape check) `B8.json` is unchanged and the sheet differs only in
the A8 section and its header line; the pilot is accepted, s1 / s2 incomplete, final-tree identities matched, provenance
passing."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from bench import p426_signals as S
from bench import p426_verify as V

BENCH = Path(__file__).resolve().parents[2]
REPO = BENCH.parent
ROWS = BENCH / "results"
M76 = ROWS / "m76"


def _b8(tmp_path):
    out = tmp_path / "B8.json"
    rc = V.main(["--lever", "kv", "all", "--results-root", str(M76), "--rows-root", str(ROWS), "--repo", str(REPO),
                 "--pair", "n16,x", "--out", str(out)])
    assert rc == 0
    return out


@pytest.fixture(scope="module")
def regenerated(tmp_path_factory):
    return _b8(tmp_path_factory.mktemp("b8"))


# §7.1 / §7.2: B8.json is byte-identical in every state (here: with the pilot's B8-A8.json written beside it)
def test_b8_regenerates_byte_identical(regenerated):
    assert regenerated.read_bytes() == (M76 / "B8.json").read_bytes()


def test_the_cli_writes_b8_a8_beside_b8_bound_to_it(regenerated):
    a8 = json.loads(regenerated.with_name("B8-A8.json").read_text())
    assert a8["base_b8_sha256"] == hashlib.sha256((M76 / "B8.json").read_bytes()).hexdigest()
    assert a8["axis"] == "A8" and a8["corpus"] == "tg2" and a8["pair"] == ["n16", "x"]
    assert not any(k.startswith("m76/wave2.tg2/") for k in json.loads(regenerated.read_text())["inputs"])   # §3.5


def _signals(tmp_path, partial=False, b8_a8=None):
    args = ["all", "--lever", "kv", "--results-root", str(M76), "--rows-root", str(ROWS), "--b8", str(M76 / "B8.json"),
            "--out-md", str(tmp_path / "S.md"), "--out-json", str(tmp_path / "S.json"), "--panel", str(M76 / "panel")]
    if partial:
        args.append("--partial")
    if b8_a8 is not None:
        args += ["--b8-a8", str(b8_a8)]
    assert S.main(args) == 0
    return (tmp_path / "S.md").read_text(), (tmp_path / "S.json").read_text()


@pytest.mark.parametrize("partial,name", [(False, "SIGNALS"), (True, "SIGNALS-partial")])
def test_signals_without_b8_a8_are_byte_identical(tmp_path, partial, name):
    md, js = _signals(tmp_path, partial=partial)
    assert md == (M76 / f"{name}.md").read_text()
    assert js == (M76 / f"{name}.json").read_text()


# §7.3 (new-identity pilot pair, decider incomplete; a shape check)
def test_pilot_pair_b8_a8_shape(regenerated):
    a8 = json.loads(regenerated.with_name("B8-A8.json").read_text())
    by = {p["pair"]: p for p in a8["pairs"]}
    assert a8["status"] == "incomplete" and a8["sessions"] == ["s1", "s2"]
    assert by["pilot"]["accepted"] is True and by["pilot"]["status"] == "accepted", by["pilot"]["reasons"]
    assert by["s1"]["status"] == by["s2"]["status"] == "incomplete" and by["reload"]["status"] == "incomplete"
    keys = by["pilot"]["keys"]
    assert len(keys) == 4 and all(k["manifest_sha256"]["n16"] and k["manifest_sha256"]["x"] for k in keys)   # no null sha
    assert a8["latency"]["status"] == "incomplete"
    assert {g: r["status"] for g, r in a8["recheck"].items()} == {"s1": "incomplete", "s2": "incomplete"}
    # §9.1: tampered rows are listed per arm; the new-identity pilot has none (the old pilot's javascript lock-file row lives
    # only in `wave2.tg2-old-identity/`)
    assert {arm: set(v) for arm, v in by["pilot"]["tampered"].items()} == {"n16": set(), "x": set()}


def test_with_b8_a8_the_sheet_differs_only_in_the_a8_section(tmp_path, regenerated):
    """§7.2 projection on the real records: the A1–A7 sections, panel and coverage are unchanged; only the A8 section and the
    B8-A8 header line are added (here A8 is incomplete: no verdict, no flag, no A8 panel member)."""
    md, js = _signals(tmp_path, b8_a8=regenerated.with_name("B8-A8.json"))
    base = (M76 / "SIGNALS.md").read_text()
    lines = md.split("\n")
    assert any(line.startswith("- B8-A8.json sha256: `") for line in lines)
    start = lines.index(next(x for x in lines if x.startswith("## A8 tg2")))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("## "))
    projected = [x for x in lines[:start] + lines[end:] if not x.startswith("- B8-A8.json sha256: `")]
    assert "\n".join(projected) == base
    sig, committed = json.loads(js), json.loads((M76 / "SIGNALS.json").read_text())
    for k in ("A1", "A5", "A7", "A2", "A3", "A4", "M1"):
        assert sig["axes"][k] == committed["axes"][k]
    assert sig["panel"] == committed["panel"] and sig["flags"] == committed["flags"]
    assert sig["axes"]["A8"]["status"].startswith("incomplete")


def test_provenance_passes_on_the_real_tg2_pilot_manifests():
    """§3.4: the corpus-neutral provenance check passes on the real tg2 pilot pair, and every key that differs between the arms
    is in the documented KV allowance (no tg2-only key is allowed)."""
    reader = V.Reader(M76)
    atts = {arm: V._a8_load_attempt(reader, f"tg2-m76-{arm}-pilot.a1", "pilot", arm) for arm in ("n16", "x")}
    assert V.kv_provenance_reasons(reader, "pilot", atts, "n16", "x", V.KV_AXES["A8"]["worktrees"]) == []
    for name in sorted((M76 / "wave2.tg2/tg2-m76-n16-pilot.a1/pilot").glob("*.manifest.json")):
        a = json.loads(name.read_text())
        b = json.loads((M76 / "wave2.tg2/tg2-m76-x-pilot.a1/pilot" / name.name).read_text())
        pa = V._kv_own_paths(V.kv_provenance(V.kv_normalise(a)), "n16", ("m76-g2",))
        pb = V._kv_own_paths(V.kv_provenance(V.kv_normalise(b)), "x", ("m76-g2",))
        diffs = {tuple(p) for p, _x, _y in V._leaf_diffs(pa, pb)}
        assert diffs and diffs <= V.KV_PROVENANCE_WHITELIST, sorted(diffs - V.KV_PROVENANCE_WHITELIST)


def test_pilot_export_prompt_check():
    """§6.2 / §7.3: the rebuilt tg2 prompt equals the first user message of the HARVEST-bound pilot export (needs the polyglot
    checkout and the pilot export on the evidence ref)."""
    from bench import p426_panel as P

    root = Path(os.environ.get("POLYGLOT_DIR") or str(Path(os.environ.get("STACK_WORKDIR", "")) / "polyglot-benchmark"))
    if not (root / "rust").is_dir():
        pytest.skip("polyglot corpus not found (set POLYGLOT_DIR / STACK_WORKDIR)")
    top = V.repo_top(REPO)
    try:
        V.git_bytes(top, ["cat-file", "-e", "origin/evidence:benchmark/results/m76/wave2.tg2/tg2-m76-n16-pilot.a1/evidence"],
                    "evidence")
        sha = V.git_bytes(top, ["rev-parse", "--verify", "origin/evidence^{commit}"], "evidence").decode().strip()
    except V.RefusalError:
        pytest.skip("the tg2 pilot pair's evidence objects are not on origin/evidence in this clone")
    top_ref = (top, V.resolve_commit(top, sha, "--evidence-ref"))
    reader = V.Reader(M76)
    pinned = json.loads((BENCH / "m65" / "tg2_universe.json").read_text())["polyglot_sha"]   # as the B4b-1 support does
    corpus = P.a8_corpus(root, polyglot_sha=lambda r: pinned)
    n = 0
    for arm in ("n16", "x"):
        att = V._a8_load_attempt(reader, f"tg2-m76-{arm}-pilot.a1", "pilot", arm)
        for rid, row in sorted(att["rows"].items()):
            P.a8_prompt_check(dict(root=M76, prefix=V.KV_REPO_PREFIX, namespace=V.A8_NS), att, row, rid, corpus, top_ref)
            n += 1
    assert n == 8
