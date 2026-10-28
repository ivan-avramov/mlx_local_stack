"""P426 T3 frozen tests — the panel's tunes per label (spec §4 "The panel", §6): `bench.p426_panel` takes the label; its OFF /
ON tunes are `p426<b>-off` / `p426<b>-on` (`s` unchanged). The label reaches the panel as `build=` (the closest named
interface: the tooling's `--build`).

Classes: [N] exercises new behaviour; [I] preserves an invariant; [R] reproduces a failure the specification fixes."""

from pathlib import Path

from bench import p426_panel as P
from bench.tests import t3_frozen_support as T

ITEMS = [(f"q{i}", f"off text {i}", f"on text {i}") for i in range(10)]


def _keys(pairs):
    return {k.split("::", 1)[0] for p in pairs for k in (p["a_key"], p["b_key"])}


def test_the_default_tunes_are_s():
    """[I] `s` unchanged: `p426-off` / `p426-on`."""
    assert (P.OFF_TUNE, P.ON_TUNE) == ("p426-off", "p426-on")
    assert _keys(P.make_pairs(T.ENTRY, ITEMS)) == {f"{T.ENTRY}@p426-off", f"{T.ENTRY}@p426-on"}


def test_build_s_is_the_default():
    """[I] `build="s"` gives exactly today's pairs (keys, slots, ids)."""
    assert P.make_pairs(T.ENTRY, ITEMS, build="s") == P.make_pairs(T.ENTRY, ITEMS)


def test_s2_pairs_carry_the_s2_tunes_and_stay_balanced():
    """[N] `p426s2-off` / `p426s2-on`; exactly half the items show ON as A."""
    pairs = P.make_pairs(T.ENTRY, ITEMS, build="s2")
    assert _keys(pairs) == {f"{T.ENTRY}@p426s2-off", f"{T.ENTRY}@p426s2-on"}
    assert sum(1 for p in pairs if "@p426s2-on::" in p["a_key"]) == 5


def test_s2_row_pairs_carry_the_s2_tunes():
    """[N] `pairs` (rows from both arms) under `s2`."""
    rows = lambda texts: [{"id": i, "content": t, "converged": True} for i, t in texts.items()]  # noqa: E731
    pairs = P.pairs(T.ENTRY, rows({"q1": "off", "q2": "off2"}), rows({"q1": "on", "q2": "on2"}), build="s2")
    assert pairs and _keys(pairs) == {f"{T.ENTRY}@p426s2-off", f"{T.ENTRY}@p426s2-on"}


def test_s2_scores_count_the_s2_on_tune():
    """[N] `item_scores` under `s2`: a verdict for `p426s2-on` is an ON win, across shown orders."""
    rows = [T.verdict("q1", "AB", "j1", "A", "p426s2-on", "p426s2-off"),
            T.verdict("q1", "BA", "j1", "B", "p426s2-on", "p426s2-off"),
            T.verdict("q1", "AB", "j2", "B", "p426s2-on", "p426s2-off"),
            T.verdict("q1", "BA", "j2", "A", "p426s2-on", "p426s2-off", on_is_a=False)]
    assert P.item_scores(rows, build="s2")["q1"] == {"score": 0.75, "n": 4, "missing": 0}


def test_s2_packets_export_blind(tmp_path):
    """[N] an `s2` packet set exports (no tune leaks into a packet)."""
    rows = P.export("cjudge", P.make_pairs(T.ENTRY, ITEMS[:2], build="s2"), ["claude-opus-5-5"], {}, tmp_path / "pk")
    assert len(rows) == 4
    assert all("p426" not in Path(r["path"]).read_text() for r in rows)
