#!/usr/bin/env python3
"""M64 contract artifact (P371 phase 4, A13): run an arm's contract suite on REAL core runs and write its artifact.

    contract_artifact.py --arm oc [--out PATH]

`oc`: the real pinned opencode 2.0.20 against the scripted mock provider (no GPU, no router, no model), driven through the
shared item core with wire capture (`bench/tests/test_m64_arm_oc_contract.py::TestOpencodeArmContract`). The artifact
(`bench/contract_artifact.py`) lists one status per spec 6 check; the checks that need services that do not exist yet are
`OWED` (never faked) with the build step that owes them, so the verdict is `incomplete` until D2 and P201 exist.

Exit codes: 0 verdict pass or incomplete (artifact written), 1 a check failed (artifact written, verdict fail), 2 the arm
or the pinned binary is unavailable (nothing written; never a skip). Default output:
`$STACK_WORKDIR/m64/contract/<arm>.json`."""
import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "benchmark"))
from bench import contract_artifact as ca  # noqa: E402

SUITES = {"oc": "bench/tests/test_m64_arm_oc_contract.py::TestOpencodeArmContract"}


def outcomes_of(reports):
    """`{check: (status, detail)}` from `{suite test method: (pytest outcome, text)}`. A check that did not run, or that was
    skipped for any reason but being owed, FAILS: the artifact never passes what it did not see pass."""
    out = {}
    for name, method in ca.CHECKS.items():
        outcome, text = reports.get(method, ("missing", ""))
        if outcome == "passed":
            out[name] = ("pass", "")
        elif outcome == "skipped" and text.startswith("owed:"):
            out[name] = ("OWED", text)
        elif outcome == "skipped":
            out[name] = ("fail", "skipped: " + text)
        elif outcome == "missing":
            out[name] = ("fail", "not run")
        else:
            out[name] = ("fail", text or outcome)
    return out


class Collector:
    """pytest plugin: the outcome of each suite test (the call phase, or the setup phase that prevented it)."""

    def __init__(self):
        self.reports = {}

    def pytest_runtest_logreport(self, report):
        method = report.nodeid.rsplit("::", 1)[-1]
        if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
            self.reports[method] = (report.outcome if report.outcome != "failed" or report.when == "call" else "error",
                                    self._text(report))
        elif report.when == "teardown" and report.outcome == "failed":
            self.reports[method] = ("failed", "teardown: " + self._text(report))

    @staticmethod
    def _text(report):
        if report.outcome == "passed":
            return ""
        if report.skipped:
            lr = report.longrepr
            text = lr[2] if isinstance(lr, tuple) and len(lr) == 3 else str(lr)
            return text.removeprefix("Skipped: ")
        crash = getattr(report.longrepr, "reprcrash", None)
        return (crash.message if crash is not None else str(report.longrepr)).strip()


def binary_path(run_oc_probe):
    return Path(os.environ.get("OPENCODE_PROBE_BIN") or run_oc_probe._default_opencode_bin())


def run_suite(arm):
    """Run the arm's suite for real; returns `(reports, snapshot_sha256, client_version)`. Missing binary: exit 2."""
    import pytest
    import run_oc_probe
    from bench import arm_opencode as ao
    binary = binary_path(run_oc_probe)
    if not binary.is_file():
        print("contract artifact: the pinned opencode binary is missing; install it with scripts/install_bench_opencode.sh "
              "(OPENCODE_PROBE_BIN or the bench-owned install path); nothing was written", file=sys.stderr)
        raise SystemExit(2)
    os.environ["OPENCODE_PROBE_BIN"] = str(binary)
    adapter = ao.OpencodeArm(run_oc_probe, mode="m64", search=ao.OfflineTestSearchService())
    snapshot = adapter.snapshot().sha256
    collector = Collector()
    os.chdir(REPO / "benchmark")
    pytest.main(["-q", "-p", "no:cacheprovider", "-o", "faulthandler_timeout=600", "--no-header", "-rN",
                 str(REPO / "benchmark" / SUITES[arm].split("::")[0]) + "::" + SUITES[arm].split("::", 1)[1]],
                plugins=[collector])
    return collector.reports, snapshot, run_oc_probe.PINNED_OPENCODE_VERSION_V2


def main(argv=None, runner=run_suite):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    if a.arm not in SUITES:
        print(f"contract artifact: arm {a.arm!r} has no contract suite yet (built: {sorted(SUITES)})", file=sys.stderr)
        raise SystemExit(2)
    reports, snapshot, version = runner(a.arm)
    doc = ca.build(a.arm, snapshot, version, outcomes_of(reports))
    out = Path(a.out) if a.out else Path(os.environ["STACK_WORKDIR"]) / "m64/contract" / (a.arm + ".json")
    sha = ca.write(out, doc)
    for name, status in doc["checks"].items():
        note = doc["owed_by"].get(name) or doc["details"].get(name) or ""
        print(f"  {status:5s} {name}" + (f"  ({note})" if note else ""))
    shown = str(out)
    workdir = os.environ.get("STACK_WORKDIR")
    if workdir and shown.startswith(workdir):
        shown = "$STACK_WORKDIR" + shown[len(workdir):]
    print(f"contract artifact {a.arm}: verdict {doc['verdict']}, snapshot {doc['snapshot_sha256'][:12]}, file sha256 {sha} -> {shown}")
    return 1 if doc["verdict"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
