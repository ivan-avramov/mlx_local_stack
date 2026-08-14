"""`generate --ids` — restrict a run to named items.

WHY THIS EXISTS. Every targeted probe this campaign wants to run is phrased as "vary ONE knob on the
SAME items", and until now the harness could not express it: item selection was by COUNT only
(`--limit bench=N`), over a seeded shuffle. So the design constraint attached to O11 — "vary sampling
on the SAME loop-triggering items, because the concentration on counting instructions means it may be
prompt-triggered rather than a sampling artifact" — was not executable, and neither was any
temperature ladder aimed at specific failing items.

Selecting by count is not a substitute. The loop-triggering ids are ~5% of IFEval, so a `--limit`
sweep spends 95% of its worker time on items that never exhibited the behaviour under test — on a
single-worker campaign where the ladder is 3+ rungs per model.

Ordering note: the filter preserves the seeded shuffle's ORDER and simply drops non-matching items, so
a filtered run remains a subsequence of the unfiltered one. That keeps `--order roundrobin`'s balanced
-prefix property and means a filtered run's rows are directly comparable to the same items from a full
run.
"""
import pytest

from bench import generate


@pytest.fixture
def fake_bench(monkeypatch, tmp_path):
    """A 5-item bench with no rows on disk."""
    items = [{"id": f"i{n}", "question": "q"} for n in range(5)]
    monkeypatch.setattr(generate.benchmarks, "load", lambda b, limit, seed: list(items))
    monkeypatch.setattr(generate, "results_root", lambda: tmp_path)
    return items


def test_ids_filter_selects_only_named_items(fake_bench):
    q, counts = generate.build_queue(["M"], ["b"], {}, 0, order="model", ids={"b": ["i1", "i3"]})
    assert [it["id"] for _m, _b, it, _s in q] == ["i1", "i3"]
    assert counts["b"] == 2, "counts must reflect the FILTERED set, or the progress total lies"


def test_ids_filter_preserves_shuffle_order(fake_bench):
    """A filtered run must be a SUBSEQUENCE of the unfiltered one, not a re-ordering — otherwise
    rows are not comparable to the same items from a full run."""
    q, _ = generate.build_queue(["M"], ["b"], {}, 0, order="model", ids={"b": ["i3", "i1"]})
    assert [it["id"] for _m, _b, it, _s in q] == ["i1", "i3"], (
        "order must follow the bench's own item order, not the order ids were listed in")


def test_ids_filter_is_per_bench(fake_bench):
    """An id list for one bench must not silently empty another bench in the same run."""
    q, counts = generate.build_queue(["M"], ["b"], {}, 0, order="model", ids={"other": ["i1"]})
    assert len(q) == 5, "a filter naming a DIFFERENT bench must leave this one untouched"
    assert counts["b"] == 5


def test_unknown_id_raises_rather_than_silently_running_nothing(fake_bench):
    """A typo'd id must fail LOUDLY. Silently generating nothing (or, worse, a subset) is how a
    probe comes back 'inconclusive' after burning worker time — and AGENTS.md already records
    `run_convergence` accepting `--set` typos silently as a defect that had to be fixed."""
    with pytest.raises(ValueError) as e:
        generate.build_queue(["M"], ["b"], {}, 0, order="model", ids={"b": ["i1", "nope"]})
    assert "nope" in str(e.value)


def test_ids_filter_works_with_roundrobin(fake_bench):
    q, _ = generate.build_queue(["M", "N"], ["b"], {}, 0, order="roundrobin",
                                ids={"b": ["i0", "i4"]})
    assert [(m, it["id"]) for m, _b, it, _s in q] == [
        ("M", "i0"), ("N", "i0"), ("M", "i4"), ("N", "i4")], (
        "roundrobin must stay item-major within the filtered set")


def test_ids_filter_composes_with_samples(fake_bench):
    q, _ = generate.build_queue(["M"], ["b"], {}, 0, order="model", ids={"b": ["i2"]}, samples=3)
    assert [(it["id"], s) for _m, _b, it, s in q] == [("i2", 0), ("i2", 1), ("i2", 2)]


def test_no_ids_is_unchanged(fake_bench):
    """The default path must be bit-identical to before."""
    q, counts = generate.build_queue(["M"], ["b"], {}, 0, order="model")
    assert [it["id"] for _m, _b, it, _s in q] == ["i0", "i1", "i2", "i3", "i4"]
    assert counts["b"] == 5


def test_cli_parses_ids_per_bench():
    """`--ids ifeval=2849:279:3608` — colon-separated, because ids can contain commas and the
    existing --limit already owns comma as its pair separator."""
    import run as runpy
    ids = runpy._parse_ids("ifeval=2849:279, humanevalplus=HumanEval/94")
    assert ids == {"ifeval": ["2849", "279"], "humanevalplus": ["HumanEval/94"]}


def test_cli_ids_empty_is_none():
    import run as runpy
    assert runpy._parse_ids("") is None
    assert runpy._parse_ids(None) is None
