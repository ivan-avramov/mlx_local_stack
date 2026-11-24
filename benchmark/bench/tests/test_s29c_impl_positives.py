"""S29 acceptance 6: the tg2 positives record gains, per language, an "the agent ran the full suite" record (read from that
language's positives sessions, decided by the worktree carrier's matcher) and a lookup-denied record (every lookup probe of
every deny class on the worktree's carrier). Recorded, never a problem: the positives' verdict stays their own."""
from __future__ import annotations

import shutil
from pathlib import Path

from bench import tg2_testable as tt
from bench.tests.test_s26_impl_positives import run_pos, step, tool, v8_problems, wd  # noqa: F401  (fixture)

BENCH = Path(__file__).resolve().parents[1].parent
LANGS = ("rust", "javascript", "java", "cpp")
SUITE = {"rust": "cargo test 2>&1 | tail -30", "javascript": "npm install && npm test", "java": "./gradlew test",
         "cpp": "cmake -S . -B build -DEXERCISM_RUN_ALL_TESTS=ON && cmake --build build"}


def _worktree(wd, carrier="opencode_bench_v2_web_tg2.json"):
    dest = wd / "wt-n16" / "benchmark" / "opencode_bench_v2_web_tg2.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BENCH / carrier, dest)


def test_the_record_holds_the_full_suite_runs_and_the_lookup_denies(wd):
    _worktree(wd)
    events = {(lang, "loop"): [*step(1), tool("ls -la", n=1), tool(SUITE[lang], n=2)] for lang in LANGS}
    rc, doc, _ = run_pos(wd, events=events)
    assert rc == 0 and doc["verdict"] == "PASS" and v8_problems(doc) == []
    t = doc["testable"]
    assert t["lookup"]["all_denied"] is True and t["lookup"]["local_allowed"] is True
    assert set(t["lookup"]["shell"]) == set(tt.LOOKUP_SHELL) and set(t["lookup"]["webfetch"]) == set(tt.LOOKUP_WEB)
    for lang in LANGS:
        rec = t["full_suite"][lang]
        assert rec["ran"] is True and rec["denied"] == 0
        assert [(c["command"], c["kind"], c["status"], c["decision"]) for c in rec["calls"]] == [
            (SUITE[lang], "loop", "completed", "allow")]
        assert {s["kind"] for s in rec["sources"]} >= {"stall", "loop", "alloc"} and all(s["read"] for s in rec["sources"])


def test_a_session_that_never_ran_the_suite_is_recorded_as_such_and_is_no_problem(wd):
    _worktree(wd)
    rc, doc, _ = run_pos(wd)
    assert rc == 0 and doc["verdict"] == "PASS"
    assert all(doc["testable"]["full_suite"][lang]["ran"] is False for lang in LANGS)


def test_on_the_old_carrier_the_cpp_build_is_recorded_denied(wd):
    _worktree(wd, carrier="opencode_bench_v2_web_tg1.json")       # the pre-S29 tg2 carrier (tg1's bytes)
    events = {("cpp", "loop"): [*step(1), tool(SUITE["cpp"], n=1)]}
    rc, doc, _ = run_pos(wd, events=events)
    rec = doc["testable"]["full_suite"]["cpp"]
    assert rec["ran"] is False and rec["denied"] == 1 and rec["calls"][0]["decision"] == "deny"
    assert doc["testable"]["lookup"]["local_allowed"] is False
    assert rc == 0 and doc["verdict"] == "PASS"                     # recorded only


def test_a_missing_carrier_is_recorded_not_raised(wd):
    rc, doc, _ = run_pos(wd)
    assert rc == 0 and doc["testable"]["lookup"]["all_denied"] is False and "error" in doc["testable"]["lookup"]
