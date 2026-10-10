"""C147 §5: every structured-grader report is retained, hashed and indexed (also on early returns)."""

import hashlib
import json
from pathlib import Path
import subprocess
import pytest
from bench import structured_grade as sg
from bench import tg1_runner as runner
from bench.token_turn_gate import TransportAbort

JUNIT = (b'<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest" tests="2">'
         b'<testcase classname="t" name="ok" file="a_test.py"/>'
         b'<testcase classname="t" name="bad" file="a_test.py"><failure message="x">\xc3\xa9 raw</failure></testcase>'
         b'</testsuite></testsuites>')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def junit_run(report_bytes=JUNIT, rc=1, out="py stdout\n", err="py stderr\n"):
    def run(cmd, **kw):
        report = Path(next(x.split("=", 1)[1] for x in cmd if x.startswith("--junitxml=")))
        if report_bytes is not None:
            report.write_bytes(report_bytes)
        kw["stdout"].write(out)
        kw["stderr"].write(err)
        assert "capture_output" not in kw
        return subprocess.CompletedProcess(cmd, rc, None, None)
    return run


class Guard:
    grader_mem_kill = False

    def __init__(self, oom=False):
        self.oom = oom
        self.removed = []

    def container_name(self):
        return "mlxbench-fixture-item-1"

    def register_container(self, name):
        pass

    def container_oom(self, name):
        return self.oom

    def remove_container(self, name):
        self.removed.append(name)


@pytest.fixture
def dirs(tmp_path):
    work, private, keep = tmp_path / "work", tmp_path / "private", tmp_path / "item.grades"
    for d in (work, private):
        d.mkdir()
    keep.mkdir()
    return work, private, keep


def index_of(keep, seq):
    return json.loads((keep / f"seq-{seq:04d}" / "index.json").read_text())


def test_python_report_preserved_byte_for_byte_and_indexed(dirs):
    work, private, keep = dirs
    g = sg.grade("python", work, "a_test.py", private, run=junit_run(), keep=keep, seq=1, boundary=7, final=False)
    idx = index_of(keep, 1)
    assert g.outcome == "parsed" and g.artifacts == idx["artifacts"]
    assert (idx["boundary"], idx["seq"], idx["final"], idx["outcome"]) == (7, 1, False, "parsed")
    assert set(idx["artifacts"]) == {"report.xml", "stdout.txt", "stderr.txt"}
    assert (keep / "seq-0001/report.xml").read_bytes() == JUNIT
    for name, meta in idx["artifacts"].items():
        assert sha(keep / meta["path"]) == meta["sha256"]
    assert (keep / "seq-0001/stdout.txt").read_text() == "py stdout\n"
    assert not [p for p in (keep / "seq-0001").iterdir() if p.name.startswith(".")]


def test_go_artifacts_indexed(dirs):
    work, private, keep = dirs
    g = Guard()

    def run(cmd, **kw):
        kw["stdout"].write(json.dumps(dict(Action="pass", Package="p", Test="TestA")) + "\n")
        kw["stderr"].write("go stderr\n")
        return subprocess.CompletedProcess(cmd, 0, None, None)
    out = sg.grade("go", work, "a_test.go", private, run=run, guard=g, keep=keep, seq=2, boundary=3, final=True)
    idx = index_of(keep, 2)
    assert out.outcome == "parsed" and idx["final"] is True
    assert set(idx["artifacts"]) == {"go.jsonl", "go.stderr"} and out.artifacts == idx["artifacts"]
    assert (keep / "seq-0002/go.stderr").read_text() == "go stderr\n"


def test_python_timeout_early_return_keeps_partial_output(dirs):
    work, private, keep = dirs

    def run(cmd, **kw):
        kw["stdout"].write("partial\n")
        raise subprocess.TimeoutExpired(cmd, 300)
    out = sg.grade("python", work, "a_test.py", private, run=run, keep=keep, seq=1, boundary=1)
    assert out.timed_out and out.outcome == "timeout"
    assert index_of(keep, 1)["outcome"] == "timeout"
    assert (keep / "seq-0001/stdout.txt").read_text() == "partial\n"


@pytest.mark.parametrize("flag,outcome", [("oom", "oom"), ("mem", "mem_kill")])
def test_go_oom_and_grader_memory_kill_retain_artifacts(dirs, flag, outcome):
    work, private, keep = dirs
    g = Guard(oom=flag == "oom")

    def run(cmd, **kw):
        kw["stdout"].write('{"Action":"run"}\n')
        g.grader_mem_kill = flag == "mem"
        return subprocess.CompletedProcess(cmd, 137, None, None)
    out = sg.grade("go", work, "a_test.go", private, run=run, guard=g, keep=keep, seq=4, boundary=2)
    assert out.outcome == outcome and (out.grader_oom or out.grader_mem_kill)
    idx = index_of(keep, 4)
    assert idx["outcome"] == outcome and "go.jsonl" in idx["artifacts"]
    assert g.removed == ["mlxbench-fixture-item-1"]


def test_python_collection_error_is_missing_report_not_abort(dirs):
    work, private, keep = dirs
    out = sg.grade("python", work, "a_test.py", private, keep=keep, seq=1, boundary=1,
                   run=junit_run(None, rc=2, err="ERROR collecting a_test.py\nImportError\n"))
    assert out.outcome == "missing_report" and not out.passing
    idx = index_of(keep, 1)
    assert idx["outcome"] == "missing_report" and "report.xml" not in idx["artifacts"]
    assert "stderr.txt" in idx["artifacts"]


def test_infrastructure_failures_write_the_index_before_raising(dirs):
    work, private, keep = dirs

    def missing(*a, **kw):
        raise FileNotFoundError("interpreter")
    with pytest.raises(TransportAbort):
        sg.grade("python", work, "a_test.py", private, run=missing, keep=keep, seq=1, boundary=1)
    assert index_of(keep, 1)["outcome"] == "infrastructure"

    with pytest.raises(TransportAbort):   # unreadable report, no collection error
        sg.grade("python", work, "a_test.py", private, keep=keep, seq=2, boundary=1,
                 run=junit_run(b"<not xml", rc=1, err="boom"))
    idx = index_of(keep, 2)
    assert idx["outcome"] == "infrastructure" and (keep / "seq-0002/report.xml").read_bytes() == b"<not xml"

    def docker(cmd, **kw):
        kw["stderr"].write("Cannot connect to the Docker daemon\n")
        return subprocess.CompletedProcess(cmd, 125, None, None)
    with pytest.raises(TransportAbort):
        sg.grade("go", work, "a_test.go", private, run=docker, guard=Guard(), keep=keep, seq=3, boundary=1)
    assert index_of(keep, 3)["outcome"] == "infrastructure"
    assert "go.stderr" in index_of(keep, 3)["artifacts"]


def test_existing_seq_directory_refuses(dirs):
    work, private, keep = dirs
    (keep / "seq-0001").mkdir()
    with pytest.raises(TransportAbort, match="immutable"):
        sg.grade("python", work, "a_test.py", private, run=junit_run(), keep=keep, seq=1, boundary=1)


def test_without_keep_behaviour_is_unchanged(dirs):
    work, private, keep = dirs
    out = sg.grade("python", work, "a_test.py", private, run=junit_run())
    assert out.passing == {("a_test.py", "t", "ok")} and out.artifacts == {} and out.outcome == "parsed"
    assert not list(keep.iterdir())


def test_grade_reports_built_from_index_files_in_seq_order(dirs):
    work, private, keep = dirs
    sg.grade("python", work, "a_test.py", private, run=junit_run(), keep=keep, seq=2, boundary=9, final=True)
    sg.grade("python", work, "a_test.py", private, run=junit_run(), keep=keep, seq=1, boundary=4)
    reports = runner.grade_reports(keep, portable=lambda p: "$STACK_WORKDIR/" + Path(p).name)
    assert [(r["seq"], r["boundary"], r["final"], r["outcome"]) for r in reports] == [
        (1, 4, False, "parsed"), (2, 9, True, "parsed")]
    meta = reports[0]["artifacts"]["report.xml"]
    assert meta["sha256"] == sha(keep / "seq-0001/report.xml") and meta["path"].startswith("$STACK_WORKDIR/")


def test_grade_reports_empty_when_directory_absent(tmp_path):
    assert runner.grade_reports(tmp_path / "absent") == []


# ---- replay pins: the gate outcome is computed exactly as before (spec §5) ----

REPLAY_MANIFEST_SHA256 = "c5312f4e8cc2e12f5c62d9770b6fbb206d2a5a85057bc4079435239472ab6ff0"
REPLAY_FIXTURES = {
    "looping@request15": ("looping", 15),    # go/kindergarten-garden, M61 s2
    "looping@request22": ("looping", 22),    # M59 go/alphametics
    "no_stop": (None, None),                 # M61 go/book-store 37.5K-token failing stretch
}


def test_replay_manifest_is_pinned():
    repo = Path(__file__).resolve().parents[3]
    assert sha(repo / "benchmark/m62/replay_manifest.json") == REPLAY_MANIFEST_SHA256


def _evidence(rel, workdir):
    import os
    local = Path(os.environ.get("C147_REPLAY_EVIDENCE", "/nonexistent")) / rel
    target = workdir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if local.is_file():
        target.write_bytes(local.read_bytes())
        return True
    repo = Path(__file__).resolve().parents[3]
    shown = subprocess.run(["git", "-C", str(repo), "show", "origin/evidence:" + rel],
                           capture_output=True)
    if shown.returncode:
        return False
    target.write_bytes(shown.stdout)
    return True


@pytest.mark.parametrize("fixture", sorted(REPLAY_FIXTURES))
def test_replay_fixture_outcomes_are_pinned_not_just_the_aggregate(fixture, tmp_path):
    from m62 import replay
    repo = Path(__file__).resolve().parents[3]
    entry = next(e for e in json.loads((repo / "benchmark/m62/replay_manifest.json").read_text())["entries"]
                 if e.get("fixture") == fixture)
    for key in ("events_path", "transcript_path"):
        if not _evidence(entry[key].replace("$STACK_WORKDIR/", ""), tmp_path):
            pytest.skip("recorded M59/M61 transcripts unavailable (origin/evidence branch not fetched)")
    report = replay.replay_entry(entry, tmp_path)
    assert (report["stop_reason"], report["first_crossing_request"]) == REPLAY_FIXTURES[fixture]
    # The structured grader change must not touch ingestion: the report keeps its exact shape.
    assert {"stop_reason", "first_crossing_request", "failing_trajectory", "terminal_usage_complete"} <= set(report)
