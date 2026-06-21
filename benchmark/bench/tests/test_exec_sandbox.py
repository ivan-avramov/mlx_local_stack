import sys

import bench.exec_sandbox as S


def test_passing_command():
    r = S.run_in_sandbox({"t.py": "print('ok')"}, [sys.executable, "t.py"])
    assert r["passed"] is True and r["returncode"] == 0
    assert "ok" in r["stdout"]


def test_failing_command():
    r = S.run_in_sandbox({"t.py": "raise SystemExit(3)"}, [sys.executable, "t.py"])
    assert r["passed"] is False and r["returncode"] == 3


def test_timeout():
    r = S.run_in_sandbox({"t.py": "import time; time.sleep(5)"}, [sys.executable, "t.py"], timeout=0.5)
    assert r["timed_out"] is True and r["passed"] is False


def test_files_written_and_isolated():
    # A second file is importable from the cwd of the command.
    r = S.run_in_sandbox({"m.py": "VALUE=42", "t.py": "import m; print(m.VALUE)"},
                         [sys.executable, "t.py"])
    assert r["passed"] and "42" in r["stdout"]
