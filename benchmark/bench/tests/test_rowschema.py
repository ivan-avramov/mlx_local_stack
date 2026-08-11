"""Row schema v2 — per-sample rows, with v1 rows still readable.

v1 rows have no `sample` and no `schema_version`. They are the ONLY rows that exist on either
box today, and they must keep grading identically, so v1 is defined as "sample 0 of an otherwise
v2 row" rather than a separate code path.

`sample_seed` is the other half of multi-sampling, and it is load-bearing for a reason measured
against the live server (2026-08-11): with NO seed in the request, three draws at temperature 0.8
came back BYTE-IDENTICAL. The serving path keys its sampler deterministically per request
(DEFAULT_SEED = 0), and the suffix-decoding path shipped on both winners keys off
(seed, row_id, position). So `--samples k` without distinct per-sample seeds would have produced
k identical rows — pass^k would equal pass@1, reliability would read as trivially perfect, and
the entire multi-sample apparatus would measure nothing while appearing to work.
"""
import bench.rowschema as RS


def test_v1_row_migrates_to_sample_zero():
    row = {"id": "aime24-3", "content": "x", "completion_tokens": 10}
    m = RS.migrate(row)
    assert m["sample"] == 0
    assert m["schema_version"] == RS.SCHEMA_VERSION
    assert m["content"] == "x"          # payload untouched


def test_migrate_does_not_mutate_the_input():
    row = {"id": "a"}
    RS.migrate(row)
    assert "sample" not in row, "migrate must return a new dict, not edit the caller's row"


def test_migrate_preserves_an_existing_sample_index():
    assert RS.migrate({"id": "a", "sample": 2, "schema_version": 2})["sample"] == 2


def test_row_key_pairs_id_and_sample():
    assert RS.row_key({"id": "a", "sample": 1}) == ("a", 1)
    assert RS.row_key({"id": "a"}) == ("a", 0)          # v1 row


def test_key_helper_matches_row_key():
    assert RS.key("a", 1) == RS.row_key({"id": "a", "sample": 1})


def test_display_key_is_readable():
    assert RS.display_key({"id": "Mbpp/610", "sample": 2}) == "Mbpp/610#2"


# --------------------------------------------------------------------- seeds
def test_sample_seed_is_deterministic_across_processes():
    """Must NOT use Python's hash(): it is salted per process (PYTHONHASHSEED), so a resume in a
    new process would silently re-draw with different seeds instead of reproducing."""
    a = RS.sample_seed("HumanEval/97", 0)
    b = RS.sample_seed("HumanEval/97", 0)
    assert a == b
    # Pin the actual derivation. A vacuous `or isinstance(a, int)` here would let any change to
    # the hash silently repartition every future run's draws.
    assert a == 1557022099
    import subprocess
    import sys
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, 'benchmark');"
         "import bench.rowschema as RS; print(RS.sample_seed('HumanEval/97', 0))"],
        capture_output=True, text=True, env={"PYTHONHASHSEED": "1", "PATH": "/usr/bin:/bin"})
    assert out.stdout.strip() == str(a), \
        f"seed changed under PYTHONHASHSEED=1 ({out.stdout.strip()} != {a}); stderr={out.stderr[-200:]}"


def test_distinct_samples_get_distinct_seeds():
    seeds = {RS.sample_seed("x", s) for s in range(8)}
    assert len(seeds) == 8


def test_distinct_items_get_distinct_seeds():
    seeds = {RS.sample_seed(f"item-{i}", 0) for i in range(64)}
    assert len(seeds) == 64


def test_seed_is_a_positive_32_bit_int():
    """mlx-vlm takes an int seed; keep it in a range every layer accepts."""
    for i in range(50):
        s = RS.sample_seed(f"i{i}", i % 3)
        assert isinstance(s, int) and 0 <= s < 2**31


def test_seed_is_item_and_sample_ordered_not_positional():
    """The seed must depend on the item ID, not on queue position — otherwise reordering the
    queue (or a different --limit) silently changes which draws you get."""
    assert RS.sample_seed("a", 0) != RS.sample_seed("b", 0)
    assert RS.sample_seed("a", 0) == RS.sample_seed("a", 0)


def test_same_seed_across_models_for_a_given_item_and_sample():
    """Deliberate: seeds are derived from (item, sample) only, so every model draws sample s of
    item i under the same seed. That is the paired/common-random-numbers choice — it removes one
    nuisance source from cross-model comparison."""
    assert RS.sample_seed("HumanEval/1", 2) == RS.sample_seed("HumanEval/1", 2)
