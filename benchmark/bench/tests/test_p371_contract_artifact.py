"""P371 phase 4 (A13, R8, P374): the per-arm contract artifact (`bench.contract_artifact`) and its CLI
(`benchmark/m64/contract_artifact.py --arm oc`). Pure artifact semantics offline; the CLI end to end on the real pinned
opencode 2.0.20 against the mock provider (no GPU); without the binary the CLI exits nonzero and writes nothing."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import contract_artifact as ca
from bench.tests import arm_contract_suite as cs
from bench.tests.test_opencode_v2_probe import INSTALLED_BIN

REPO = Path(__file__).resolve().parents[3]
CLI = REPO / "benchmark/m64/contract_artifact.py"
SNAP = "5" * 64


def all_pass(**over):
    out = {n: ("pass", "") for n in ca.CHECKS}
    for n in ca.OWED_BY:
        out[n] = ("OWED", "owed")
    out.update(over)
    return out


def doc_of(**over):
    return ca.build("oc", SNAP, "2.0.20", all_pass(**over))


def full_pass():
    return ca.build("oc", SNAP, "2.0.20", {n: ("pass", "") for n in ca.CHECKS})


# ---------------------------------------------------------------- the check registry is the suite's
def test_the_artifact_checks_are_exactly_the_suites_spec_6_tests():
    methods = sorted(n for n in dir(cs.ArmContractSuite) if n.startswith("test_"))
    assert sorted(ca.CHECKS.values()) == methods and len(ca.CHECKS) == 16
    assert set(ca.OWED_BY) == {"shared_search_tool", "infrastructure_failures", "p201_rerun"}
    assert all("section 12 step 5" in step for step in ca.OWED_BY.values())
    assert "D2" in ca.OWED_BY["shared_search_tool"] and "D2" in ca.OWED_BY["infrastructure_failures"]


def test_the_owed_checks_are_the_ones_the_suite_skips_as_owed():
    for name in ca.OWED_BY:
        method = ca.CHECKS[name]
        with pytest.raises(pytest.skip.Exception, match="owed"):
            getattr(cs.ArmContractSuite(), method)(SimpleNamespace(search_fixture=lambda: None))


# ---------------------------------------------------------------- build / verdict / hash
def test_the_verdict_is_pass_incomplete_or_fail_and_fail_beats_incomplete():
    assert full_pass()["verdict"] == "pass"
    inc = doc_of()
    assert inc["verdict"] == "incomplete" and sorted(inc["owed_by"]) == sorted(ca.OWED_BY) and inc["details"] == {}
    bad = doc_of(wire_controls=("fail", "request 2: seed=1, expected 5"))
    assert bad["verdict"] == "fail" and bad["checks"]["wire_controls"] == "fail" and "seed=1" in bad["details"]["wire_controls"]


def test_the_document_shape_and_the_hash_of_the_rest():
    doc = doc_of()
    assert set(doc) == {"schema", "arm", "snapshot_sha256", "client_version", "checks", "owed_by", "details", "verdict",
                        "sha256"}
    assert doc["arm"] == "oc" and doc["snapshot_sha256"] == SNAP and doc["client_version"] == "2.0.20"
    assert all(v in ("pass", "fail", "OWED") for v in doc["checks"].values())
    rest = {k: v for k, v in doc.items() if k != "sha256"}
    assert doc["sha256"] == hashlib.sha256(json.dumps(rest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert ca.validate(doc, arm="oc") == []


def test_an_outcome_set_that_misses_a_check_is_a_build_error_never_an_implicit_pass():
    short = all_pass()
    del short["compaction"]
    with pytest.raises(ca.ArtifactError, match="compaction"):
        ca.build("oc", SNAP, "2.0.20", short)
    with pytest.raises(ca.ArtifactError, match="mystery"):
        ca.build("oc", SNAP, "2.0.20", {**all_pass(), "mystery": ("pass", "")})


def test_an_owed_status_on_a_check_that_is_not_owed_is_a_failure():
    doc = doc_of(wire_controls=("OWED", "skipped as owed"))
    assert doc["checks"]["wire_controls"] == "fail" and doc["verdict"] == "fail"


def test_failure_details_are_portable_one_line_and_bounded():
    home = os.path.expanduser("~")
    doc = doc_of(compaction=("fail", f"boom at {home}/ws/x.py and /private/var/folders/ab/c/T/pytest-1/run\nsecond line " + "x" * 900))
    text = doc["details"]["compaction"]
    assert home not in text and "/var/folders" not in text and "\n" not in text and len(text) <= ca.MAX_DETAIL
    assert "$HOME" in text and "<tmp>" in text


# ---------------------------------------------------------------- verification
def written(tmp_path, doc, name="oc.json"):
    path = tmp_path / name
    return path, ca.write(path, doc)


def test_a_written_artifact_is_canonical_bytes_with_a_newline_and_round_trips(tmp_path):
    doc = doc_of()
    path, sha = written(tmp_path, doc)
    raw = path.read_bytes()
    assert raw.endswith(b"\n") and sha == hashlib.sha256(raw).hexdigest() == ca.file_sha256(raw)
    assert json.loads(raw) == doc and ca.problems(path, arm="oc", file_sha256_frozen=sha, smoke=True) == []


@pytest.mark.parametrize("smoke,verdict_ok", [(False, False), (True, True)])
def test_an_incomplete_artifact_is_refused_outside_smoke_and_allowed_in_smoke(tmp_path, smoke, verdict_ok):
    path, sha = written(tmp_path, doc_of())
    got = ca.problems(path, arm="oc", file_sha256_frozen=sha, smoke=smoke)
    assert (got == []) is verdict_ok
    if not smoke:
        assert any("incomplete" in g and "shared_search_tool" in g for g in got)


@pytest.mark.parametrize("smoke", [False, True])
def test_a_passing_artifact_is_accepted_everywhere_a_failed_one_nowhere(tmp_path, smoke):
    path, sha = written(tmp_path, full_pass())
    assert ca.problems(path, arm="oc", file_sha256_frozen=sha, smoke=smoke) == []
    fpath, fsha = written(tmp_path, doc_of(compaction=("fail", "x")), "failed.json")
    assert any("FAILED" in g and "compaction" in g for g in ca.problems(fpath, arm="oc", file_sha256_frozen=fsha, smoke=smoke))


@pytest.mark.parametrize("smoke", [False, True])
def test_a_missing_file_is_refused_everywhere(tmp_path, smoke):
    got = ca.problems(tmp_path / "gone.json", arm="oc", file_sha256_frozen="0" * 64, smoke=smoke)
    assert got and "missing" in got[0]


@pytest.mark.parametrize("smoke", [False, True])
def test_a_file_whose_bytes_changed_since_it_was_frozen_is_drift(tmp_path, smoke):
    path, sha = written(tmp_path, doc_of())
    path.write_bytes(path.read_bytes() + b" ")
    got = ca.problems(path, arm="oc", file_sha256_frozen=sha, smoke=smoke)
    assert got and "drift" in got[0]
    other, other_sha = written(tmp_path, full_pass(), "other.json")           # a valid DIFFERENT artifact is drift too
    path.write_bytes(other.read_bytes())
    assert "drift" in ca.problems(path, arm="oc", file_sha256_frozen=sha, smoke=smoke)[0]
    assert ca.problems(path, arm="oc", file_sha256_frozen=other_sha, smoke=smoke) == []


@pytest.mark.parametrize("mutate,expect", [
    (lambda d: d.update(arm="pi"), "names arm"),
    (lambda d: d["checks"].update(wire_controls="fail"), "contradicts"),
    (lambda d: d.update(verdict="pass"), "contradicts"),
    (lambda d: d["checks"].pop("p201_rerun"), "exactly the spec 6 checks"),
    (lambda d: d["checks"].update(mystery="pass"), "exactly the spec 6 checks"),
    (lambda d: d["owed_by"].update(shared_search_tool="somewhere"), "owed"),
    (lambda d: d.update(snapshot_sha256="nope"), "snapshot_sha256"),
    (lambda d: d["checks"].update(wire_controls="maybe"), "unknown status"),
])
def test_a_self_inconsistent_or_hand_edited_artifact_is_refused(tmp_path, mutate, expect):
    doc = doc_of()
    mutate(doc)                                          # edited AFTER hashing (the sha256 inside is now stale too)
    path = tmp_path / "x.json"
    sha = ca.write(path, doc)
    got = ca.problems(path, arm="oc", file_sha256_frozen=sha, smoke=True)
    assert got and any(expect in g for g in got), got


def test_a_re_hashed_edit_is_still_refused_when_it_contradicts_the_checks(tmp_path):
    doc = doc_of()
    doc["verdict"] = "pass"
    doc["sha256"] = ca.sha_of(doc)
    path = tmp_path / "x.json"
    sha = ca.write(path, doc)
    assert any("contradicts" in g for g in ca.problems(path, arm="oc", file_sha256_frozen=sha, smoke=True))


def test_a_stale_inner_hash_is_refused(tmp_path):
    doc = doc_of()
    doc["sha256"] = "0" * 64
    path = tmp_path / "x.json"
    sha = ca.write(path, doc)
    assert any("sha256 does not match" in g for g in ca.problems(path, arm="oc", file_sha256_frozen=sha, smoke=True))


def test_not_json_and_not_an_object_are_refused(tmp_path):
    for raw in (b"not json", b"[1, 2]"):
        path = tmp_path / "x.json"
        path.write_bytes(raw)
        assert ca.problems(path, arm="oc", file_sha256_frozen=ca.file_sha256(raw), smoke=True)


def test_the_artifact_must_be_of_the_snapshot_the_chain_froze(tmp_path):
    path, sha = written(tmp_path, full_pass())
    assert ca.problems(path, arm="oc", file_sha256_frozen=sha, smoke=False, snapshot_sha256=SNAP) == []
    got = ca.problems(path, arm="oc", file_sha256_frozen=sha, smoke=False, snapshot_sha256="6" * 64)
    assert got and "another snapshot" in got[0]


# ---------------------------------------------------------------- the CLI
def load_cli():
    spec = importlib.util.spec_from_file_location("m64_contract_artifact_cli", CLI)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_cli_exists_and_is_arm_gated():
    cli = load_cli()
    with pytest.raises(SystemExit) as exc:
        cli.main(["--arm", "pi"])
    assert exc.value.code != 0


def test_the_cli_without_the_binary_exits_nonzero_writes_nothing_and_never_skips(tmp_path):
    out = tmp_path / "oc_contract.json"
    env = {**os.environ, "OPENCODE_PROBE_BIN": str(tmp_path / "no-such-opencode")}
    got = subprocess.run([sys.executable, str(CLI), "--arm", "oc", "--out", str(out)], env=env, capture_output=True,
                         text=True, timeout=300, cwd=REPO / "benchmark")
    assert got.returncode != 0 and not out.exists()
    assert "binary" in got.stderr and "skip" not in got.stderr.lower()


def test_the_cli_maps_suite_outcomes_to_checks_and_a_failed_or_unrun_check_is_a_fail(tmp_path):
    cli = load_cli()
    methods = dict(ca.CHECKS)
    reports = {m: ("passed", "") for n, m in methods.items() if n not in ca.OWED_BY}
    reports.update({methods[n]: ("skipped", "owed: later step") for n in ca.OWED_BY})
    assert cli.outcomes_of(reports)["wire_controls"] == ("pass", "") and cli.outcomes_of(reports)["p201_rerun"][0] == "OWED"
    reports[methods["compaction"]] = ("failed", "AssertionError: compaction tokens not counted")
    reports.pop(methods["terminal_shapes"])
    reports[methods["tool_windows"]] = ("skipped", "diagnosed sandbox start denial")
    got = cli.outcomes_of(reports)
    assert got["compaction"][0] == "fail" and "not counted" in got["compaction"][1]
    assert got["terminal_shapes"] == ("fail", "not run")
    assert got["tool_windows"][0] == "fail" and "skipped" in got["tool_windows"][1]       # a non-owed skip never passes


def test_the_cli_exit_codes_with_an_injected_suite_runner(tmp_path):
    cli = load_cli()
    ok = {m: ("passed", "") for n, m in ca.CHECKS.items() if n not in ca.OWED_BY}
    ok.update({ca.CHECKS[n]: ("skipped", "owed: x") for n in ca.OWED_BY})
    out = tmp_path / "a.json"
    assert cli.main(["--arm", "oc", "--out", str(out)], runner=lambda arm: (ok, SNAP, "2.0.20")) == 0
    doc = json.loads(out.read_text())
    assert doc["verdict"] == "incomplete" and doc["snapshot_sha256"] == SNAP
    bad = dict(ok, **{ca.CHECKS["wire_controls"]: ("failed", "AssertionError: seed")})
    out2 = tmp_path / "b.json"
    assert cli.main(["--arm", "oc", "--out", str(out2)], runner=lambda arm: (bad, SNAP, "2.0.20")) == 1
    assert json.loads(out2.read_text())["verdict"] == "fail"                # the failure is recorded, and the exit is nonzero


@pytest.mark.skipif(not INSTALLED_BIN.is_file() and not os.environ.get("OPENCODE_PROBE_BIN"),
                    reason="bench opencode 2.0.20 not installed (scripts/install_bench_opencode.sh)")
def test_the_cli_on_the_real_pinned_client_every_non_owed_check_passes_and_the_verdict_is_incomplete(tmp_path):
    out = tmp_path / "oc_contract.json"
    got = subprocess.run([sys.executable, str(CLI), "--arm", "oc", "--out", str(out)], capture_output=True, text=True,
                         timeout=900, cwd=REPO / "benchmark")
    assert got.returncode == 0, got.stdout[-3000:] + got.stderr[-3000:]
    doc = json.loads(out.read_text())
    assert ca.validate(doc, arm="oc") == [] and doc["verdict"] == "incomplete" and doc["client_version"] == "2.0.20"
    assert {n for n, v in doc["checks"].items() if v == "OWED"} == set(ca.OWED_BY)
    assert all(v == "pass" for n, v in doc["checks"].items() if n not in ca.OWED_BY), doc["checks"]
    raw = out.read_text()
    assert os.path.expanduser("~") not in raw and "/Users/" not in raw and "@" not in raw          # portable
    assert ca.problems(out, arm="oc", file_sha256_frozen=ca.file_sha256(out.read_bytes()), smoke=True) == []
    assert any("incomplete" in p for p in ca.problems(out, arm="oc", file_sha256_frozen=ca.file_sha256(out.read_bytes()),
                                                      smoke=False))
