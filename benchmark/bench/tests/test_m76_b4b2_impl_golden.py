"""M76 B4b-2 §7.1 / §7.2 / §7.3 on `main`'s committed records: `B8.json` regenerates byte-identically in every state; the committed
signals sheets (`SIGNALS.md`, `SIGNALS-partial.md` and their JSON) regenerate byte-identically (S29: with the committed
`B8-A8.json` once the A8 readout is published); with the
`B8-A8.json` of the harvested tg2 pilot pair and decider (new identity; S29: decider legs on the amendment; a shape check)
`B8.json` is unchanged and the sheet differs only in A8 content; the pilot and the decider pairs are accepted, final-tree
identities matched, provenance passing."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from bench import p426_signals as S
from bench import p426_verify as V
from bench.tests import m76_b4b2_frozen_cli

BENCH = Path(__file__).resolve().parents[2]
REPO = BENCH.parent
ROWS = BENCH / "results"
M76 = ROWS / "m76"


def _b8(tmp_path):
    out = tmp_path / "B8.json"
    rc = m76_b4b2_frozen_cli.main(
        ["--lever", "kv", "all", "--results-root", str(M76), "--rows-root", str(ROWS), "--repo", str(REPO),
         "--pair", "n16,x", "--out", str(out)]
    )
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


A8_FREE = Path(__file__).resolve().parent / "fixtures" / "m76_signals_without_a8"


@pytest.mark.parametrize("partial,name", [(False, "SIGNALS"), (True, "SIGNALS-partial")])
def test_signals_without_b8_a8_are_byte_identical_to_the_a8_free_golden(tmp_path, partial, name):
    """S29 (Sol cold read): the A8-free path keeps an independent byte golden — the sheets as committed before the A8 readout
    (`fixtures/m76_signals_without_a8/`); with no B8-A8 the sheets regenerate byte-identically to them."""
    md, js = _signals(tmp_path, partial=partial)
    assert md == (A8_FREE / f"{name}.md").read_text()
    assert js == (A8_FREE / f"{name}.json").read_text()


@pytest.mark.parametrize("partial,name", [(False, "SIGNALS"), (True, "SIGNALS-partial")])
def test_committed_signals_regenerate_byte_identically(tmp_path, partial, name):
    """S29: the committed sheets regenerate from main's inputs — with the committed B8-A8.json once the A8 readout is published."""
    published = M76 / "B8-A8.json"
    md, js = _signals(tmp_path, partial=partial, b8_a8=published if published.is_file() else None)
    assert md == (M76 / f"{name}.md").read_text()
    assert js == (M76 / f"{name}.json").read_text()


# §7.3 (new-identity pilot pair and the harvested decider, run on the S29 amendment; a shape check)
def test_real_b8_a8_shape_with_the_decider(regenerated):
    a8 = json.loads(regenerated.with_name("B8-A8.json").read_text())
    by = {p["pair"]: p for p in a8["pairs"]}
    assert a8["status"] == "complete" and a8["sessions"] == ["s1", "s2"]
    for s in ("pilot", "s1", "s2", "reload"):
        assert by[s]["accepted"] is True and by[s]["status"] == "accepted" and by[s]["reasons"] == [], (s, by[s]["reasons"])
    for s in ("pilot", "s1", "s2", "reload"):
        keys = by[s]["keys"]
        assert keys and all(k["manifest_sha256"]["n16"] and k["manifest_sha256"]["x"] for k in keys), s   # no null sha
    assert len(by["pilot"]["keys"]) == 4
    assert "m76/wave2.tg2/run/amendment.json" in a8["inputs"]
    assert a8["latency"]["status"] == "present"
    assert {g: r["status"] for g, r in a8["recheck"].items()} == {"s1": "ok", "s2": "ok"}
    # §9.1: tampered rows are listed per arm; the new-identity pilot has none (the old pilot's javascript lock-file row lives
    # only in `wave2.tg2-old-identity/`)
    assert {arm: set(v) for arm, v in by["pilot"]["tampered"].items()} == {"n16": set(), "x": set()}


def _a8_members_added(sig, committed):
    """B8-A8's `A8-<session>` panel members: what the sheet's panel completeness expects beyond the committed sheet."""
    got, base = sig["panel"]["completeness"]["expected"], committed["panel"]["completeness"]["expected"]
    assert got[:len(base)] == base
    added = got[len(base):]
    assert added and all(m.startswith("A8-") for m in added)
    return added


def _without_a8_members(value, members):
    """`value` (a panel / flag record) with the A8 members taken out of its completeness lists and panel_incomplete items/text."""
    value = json.loads(json.dumps(value))
    comp = value.get("completeness") if isinstance(value, dict) else None
    if isinstance(comp, dict):
        for k in ("expected", "missing_members"):
            comp[k] = [m for m in comp.get(k) or [] if m not in members]
    if isinstance(value, dict) and value.get("flag") == "panel_incomplete":
        items = list(value.get("items") or [])
        kept = [m for m in items if m not in members]
        value["text"] = value["text"].replace(f"missing members {items}", f"missing members {kept}")
        value["items"] = kept
    return value


def test_with_b8_a8_the_sheet_differs_only_in_a8_content(tmp_path, regenerated):
    """§7.2 projection on the real records: the A1–A7 sections, panel and coverage are unchanged except for A8 content — the A8
    section, the B8-A8 header line, the A8 decode lines, A8 flags, and the panel completeness now also expecting B8-A8's
    `A8-<session>` members (missing: none is judged in the frozen panel)."""
    md, js = _signals(tmp_path, b8_a8=regenerated.with_name("B8-A8.json"))
    (tmp_path / "base").mkdir()
    base_md, base_js = _signals(tmp_path / "base")     # S29: the A8-free reference is generated, not the committed sheet
    sig, committed = json.loads(js), json.loads(base_js)
    assert "A8" not in committed["axes"]
    members = _a8_members_added(sig, committed)
    assert members == ["A8-s1", "A8-s2"]
    base = base_md.split("\n")
    c_comp, g_comp = committed["panel"]["completeness"], sig["panel"]["completeness"]
    want = [x.replace(f"expected members {c_comp['expected']}, missing {c_comp['missing_members']}",
                      f"expected members {g_comp['expected']}, missing {g_comp['missing_members']}")
             .replace(f"panel incomplete: missing members {c_comp['missing_members']}",
                      f"panel incomplete: missing members {g_comp['missing_members']}") for x in base]
    lines = md.split("\n")
    assert any(line.startswith("- B8-A8.json sha256: `") for line in lines)
    start = lines.index(next(x for x in lines if x.startswith("## A8 tg2")))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("## "))
    projected, section = [], None
    for x in lines[:start] + lines[end:]:
        if x.startswith("## "):
            section = x
        if x.startswith("- B8-A8.json sha256: `"):
            continue
        if section and section.startswith(("## Decode per item", "## Flags")) and x.startswith("- A8"):
            continue                                     # A8 decode lines / A8 flags
        projected.append(x)
    assert projected == want
    for k in ("A1", "A5", "A7", "A2", "A3", "A4", "M1"):
        assert sig["axes"][k] == committed["axes"][k]
    assert _without_a8_members(sig["panel"], members) == committed["panel"]
    assert ([_without_a8_members(f, members) for f in sig["flags"] if f.get("member") != "A8"]
            == [_without_a8_members(f, members) for f in committed["flags"]])
    assert not str(sig["axes"]["A8"].get("status", "")).startswith("incomplete")      # the decider feeds the A8 section


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
