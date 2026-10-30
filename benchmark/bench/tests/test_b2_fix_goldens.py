"""B2 fix pass (R7): the legacy tg1 chain goldens stay pristine for the base-commit bundle test; the C221 refresh (no
`ensure_overlay` call) is a recorded old -> new (`p371_baseline/golden_refresh_c221.json`), applied by a loader that checks both
hashes, never filtered in test code."""
import hashlib
import json
from pathlib import Path

import pytest

from bench.tests.p371_baseline import runner

BASE = Path(__file__).resolve().parent / "p371_baseline"
REFRESH = json.loads((BASE / "golden_refresh_c221.json").read_text())


def test_the_old_goldens_are_unchanged_and_hash_to_the_recorded_old_value():
    assert REFRESH["goldens"]
    for name, shas in REFRESH["goldens"].items():
        assert hashlib.sha256((BASE / "golden" / name).read_bytes()).hexdigest() == shas["old_sha256"], name


@pytest.mark.parametrize("name", sorted(REFRESH["goldens"]))
def test_the_refreshed_golden_hashes_to_the_recorded_new_value_and_lost_only_the_overlay_call(name):
    stem = name[:-len(".json")]
    old, new = runner.load_golden(stem), runner.load_refreshed_golden(stem)
    assert REFRESH["removed_ops_call"] in old["ops_calls"] and REFRESH["removed_ops_call"] not in new["ops_calls"]
    assert [c for c in old["ops_calls"] if c != REFRESH["removed_ops_call"]] == new["ops_calls"]
    assert {k: v for k, v in old.items() if k != "ops_calls"} == {k: v for k, v in new.items() if k != "ops_calls"}
    assert hashlib.sha256(runner.golden_text(new).encode()).hexdigest() == REFRESH["goldens"][name]["new_sha256"]


def test_a_golden_that_drifted_from_its_recorded_old_hash_is_refused(monkeypatch, tmp_path):
    stem = sorted(REFRESH["goldens"])[0][:-len(".json")]
    (tmp_path / f"{stem}.json").write_text((BASE / "golden" / f"{stem}.json").read_text() + " ")
    monkeypatch.setattr(runner, "GOLDEN_DIR", tmp_path)
    with pytest.raises(AssertionError, match="old hash"):
        runner.load_refreshed_golden(stem)


def test_the_chain_differential_no_longer_filters_the_golden_in_test_code():
    src = (Path(__file__).resolve().parent / "test_p371_baseline.py").read_text()
    assert 'c != ["ensure_overlay"]' not in src and "load_refreshed_golden" in src
