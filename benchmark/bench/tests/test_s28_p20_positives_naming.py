"""S28-P20 (C380): the harvested tg2 positives records under `benchmark/results/m76/tg2/positives-<date>[-<label>]/run/` are the same
verbatim, sha-bound harness records as the Wave-2 harvest (P437 / P601 / S26-P16): the model directory inventory they carry
(`optiq/metadata.json`) is data, not prose, and so is the sealed record (`positives.json`). Prose and scripts beside them stay checked.  allow-shorthand"""
import pytest

from bench import modelnames as MN

POSITIVE_RECORDS = [
    "benchmark/results/m76/tg2/positives-20261119-fail/run/rust/alloc.attempt1.manifest.json",
    "benchmark/results/m76/tg2/positives-20261119-fail/run/javascript/stall.attempt1.manifest.json",
    "benchmark/results/m76/tg2/positives-20261117/run/cpp/loop.attempt2.manifest.json",
    "benchmark/results/m76/tg2/positives-20261121-rerun.2/run/java/stall.attempt1.jsonl",   # a multi-part label
]


@pytest.mark.parametrize("path", POSITIVE_RECORDS)
def test_harvested_tg2_positives_run_records_are_data_not_prose(path):
    diff = (f"+++ b/{path}\n@@ -0,0 +1 @@\n+\"optiq/metadata.json\": \"bfaba2b30565d2e38b1b54683a7dea35b0d35944\",\n"  # allow-shorthand: the test names the flagged path segment
            "+++ b/benchmark/results/m76/tg2/positives-20261119-fail/README.md\n@@ -0,0 +1 @@\n+optiq regressed\n"  # allow-shorthand: the test names the flagged path segment
            "+++ b/benchmark/results/m76/tg2/positives-20261119-fail/positives.json\n@@ -0,0 +1 @@\n+\"note\": \"optiq\"\n")  # allow-shorthand
    found = MN.diff_violations(diff)
    assert sorted({v.path for v in found}) == ["benchmark/results/m76/tg2/positives-20261119-fail/README.md"]


@pytest.mark.parametrize("path", [
    "benchmark/results/m76/tg2/notes/run/x.manifest.json",          # not a positives directory
    "benchmark/results/m76/tg2/positives-2026111/run/x.manifest.json",   # not a date
    "benchmark/results/m76/tg2/positives-20261119-fail/x.manifest.json",  # outside run/
    "benchmark/results/m76/tg2/positives-20261119-fail/runs/rust/x.manifest.json",  # a near-miss directory
    "benchmark/results/m76/tg2/positives-20261119-fail/run/NOTES.md",     # prose inside run/
    "benchmark/results/m76/tg2/positives-20261119-fail/run/rust/summarize.py",  # a script inside run/
    "benchmark/results/m76/tg2/positives-20261119-fail/run/x.manifest.json",  # no language directory
])
def test_paths_outside_a_positives_run_stay_checked(path):
    diff = f"+++ b/{path}\n@@ -0,0 +1 @@\n+\"optiq/metadata.json\": \"bfaba2b3\"\n"  # allow-shorthand: the test names the flagged path segment
    assert [v.path for v in MN.diff_violations(diff)] == [path]
