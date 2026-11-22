"""S29 H4 (C384) implementer tests, the tg2 positives: a host change before / after the positives session is recorded in the
positives record (`host_env_changes`, beside `host_env` / `host_env_after`), never appended to its problems; the verdict is the
positives' own."""
from __future__ import annotations

from bench.tests.test_s26_impl_positives import FP, run_pos, v8_problems, wd  # noqa: F401  (fixture)

JDK17 = "Homebrew Cellar: added openjdk@17/17.0.12"


def test_h4_a_host_change_during_the_positives_is_recorded_not_a_problem(wd):
    rc, doc, _ = run_pos(wd, change_at=("java", "loop"))
    assert rc == 0 and doc["verdict"] == "PASS" and doc["problems"] == []
    assert doc["host_env_changes"] == [JDK17]
    assert doc["host_env"] == FP and "openjdk@17/17.0.12" in doc["host_env_after"]["cellar"]
    assert v8_problems(doc) == []


def test_h4_an_unchanged_host_records_no_change(wd):
    rc, doc, _ = run_pos(wd)
    assert rc == 0 and doc["host_env_changes"] == []


def test_h4_a_failing_positive_still_fails_with_the_host_change_recorded_beside_it(wd):
    rc, doc, _ = run_pos(wd, change_at=("java", "loop"), raise_at=("cpp", "alloc"))
    assert rc == 1 and doc["verdict"] == "FAIL"
    assert "exception: RuntimeError: inject boom" in doc["problems"]
    assert not [p for p in doc["problems"] if "host environment" in p]
    assert doc["host_env_changes"] == [JDK17]
