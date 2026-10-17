"""P311-lite (v), spec test 9: the report scripts on the committed P223 / M63 / c144-base rows (legacy in-row fields)
produce byte-identical reports after the switch to the fail-closed join."""
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
REPORTS = [("p223_tg1", "tg1_report.py", "P223_REPORT.md"),
           ("m63_mtp", "m63_report.py", "M63_REPORT.md"),
           ("c144_base", "c144base_report.py", "C144BASE_REPORT.md")]


@pytest.mark.parametrize("folder,script,report", REPORTS)
def test_report_script_output_is_byte_identical_on_legacy_rows(folder, script, report):
    directory = REPO / "benchmark/results" / folder
    target = directory / report
    committed = subprocess.run(["git", "-C", str(REPO), "show", f"HEAD:benchmark/results/{folder}/{report}"],
                               capture_output=True).stdout
    before = target.read_bytes()
    try:
        run = subprocess.run([sys.executable, str(directory / script)], capture_output=True, text=True, timeout=600,
                             cwd=REPO)
        assert run.returncode == 0, run.stderr[-1500:]
        assert target.read_bytes() == before
        assert before == committed or not committed       # the worktree report is the committed one
    finally:
        target.write_bytes(before)
