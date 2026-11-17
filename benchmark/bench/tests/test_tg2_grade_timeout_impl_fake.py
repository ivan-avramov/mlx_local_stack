"""M65 tg2 grader, a timeout kill keeps its start evidence (spec docs/specs/m65-tg2-grade-timeout-evidence.md v1),
acceptance 1 on the fake docker harness of `test_tg2_grade.py`, which reproduces the box fact: a timed-out step leaves its
host-side streams EMPTY, and the marker file exists in the report volume iff the script got past its marker line."""

import hashlib
import json
import re
import subprocess

import pytest

from bench import tg2_grade as tg
from bench.tests.test_tg2_grade import (FakeGuard, IMG, Plan, basic_plan, do_grade, make_tar, mounts,  # noqa: F401
                                        tmp_path, tree)
from bench.token_turn_gate import TransportAbort

LANGS = ("rust", "java", "javascript", "cpp")
TAG = dict(compile="TG2_COMPILE_START", execute="TG2_RUNNER_START", collect="TG2_COLLECT_START")


def _graded(lang, tree, plan, tmp_path):
    keep = tmp_path / "keep"
    result, guard = do_grade(lang, tree, plan, keep=keep, seq=1, boundary=0, final=True)
    return result, guard, keep / "seq-0001"


def _nonce(guard, step):
    cmd = next(c for s, c in guard.calls if s == step)
    return re.search(TAG[step] + r" ([0-9a-f]{16})", cmd[-1]).group(1)


# ------------------------------------------------------------------------------------------------ the box fact
def test_fake_reproduces_the_box_fact_empty_streams_and_a_marker_file_iff_past_the_marker(tmp_path):
    guard = FakeGuard(Plan(execute=dict(timeout=True, stdout="running 20 tests\n")))
    report = tmp_path / "rep"
    report.mkdir()
    guard.volumes["vol-r"] = report
    script = ('echo "TG2_RUNNER_START 00112233aabbccdd" > /report/.tg2-marker-execute-00112233aabbccdd; '
              'echo "TG2_RUNNER_START 00112233aabbccdd"; { spin; } 2>&1 | head -c 9 | '
              'tee /report/.tg2-out-execute-00112233aabbccdd; exit ${PIPESTATUS[0]}')
    cmd = ["docker", "run", "--name", "s1", "--mount", "type=volume,src=vol-r,dst=/report", IMG, "bash", "-c", script]
    out, err = tmp_path / "o", tmp_path / "e"
    with out.open("w") as o, err.open("w") as e:
        with pytest.raises(subprocess.TimeoutExpired):
            guard.run_grader(cmd, stdout=o, stderr=e, timeout=1)
    assert out.read_bytes() == b"" and err.read_bytes() == b""
    assert (report / ".tg2-marker-execute-00112233aabbccdd").read_text() == "TG2_RUNNER_START 00112233aabbccdd\n"
    assert "running 20 tests" in (report / ".tg2-out-execute-00112233aabbccdd").read_text()
    guard = FakeGuard(Plan(execute=dict(timeout=True, no_marker=True)))       # never reached the marker line
    guard.volumes["vol-r"] = report
    for f in report.iterdir():
        f.unlink()
    with out.open("w") as o, err.open("w") as e:
        with pytest.raises(subprocess.TimeoutExpired):
            guard.run_grader(cmd, stdout=o, stderr=e, timeout=1)
    assert list(report.iterdir()) == [] and out.read_bytes() == b""


# ------------------------------------------------------------------------------------- timeouts are model outcomes
@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("step", ["compile", "execute"])
def test_a_timed_out_step_with_its_marker_only_in_the_file_is_a_timeout(tree, tmp_path, lang, step):
    plan = basic_plan(lang, **{step: dict(timeout=True, stdout="partial-%s-output\n" % step)})
    result, guard, d = _graded(lang, tree, plan, tmp_path)
    assert result.outcome == "timeout" and result.all_failed and result.passing == set()
    assert result.failing({"a", "b"}) == 2
    nonce = _nonce(guard, step)
    assert (d / (step + ".stdout")).read_bytes() == b""                      # the box fact: nothing on the stream
    assert (d / (step + ".marker")).read_text() == "%s %s\n" % (TAG[step], nonce)
    out = (d / (step + ".out")).read_text()
    assert out.startswith("%s %s\n" % (TAG[step], nonce)) and "partial-%s-output" % step in out
    rec = [p for p in result.phases if p["step"] == step][-1]
    assert rec["timed_out"] and rec["marker_source"] == "file"
    assert rec["marker_sha256"] == hashlib.sha256((d / (step + ".marker")).read_bytes()).hexdigest()
    assert rec["out_sha256"] == hashlib.sha256((d / (step + ".out")).read_bytes()).hexdigest()
    assert [p["step"] for p in result.phases][-1] == step + "-readback"
    index = json.loads((d / "index.json").read_text())
    assert index["outcome"] == "timeout" and {step + ".marker", step + ".out"} <= set(index["artifacts"])
    assert guard.holder_names == {} and guard.volumes == {}                  # cleanup unchanged


@pytest.mark.parametrize("lang", ["java", "javascript", "cpp"])
def test_a_timed_out_collect_with_its_marker_only_in_the_file_is_a_timeout(tree, tmp_path, lang):
    result, guard, d = _graded(lang, tree, basic_plan(lang, collect=dict(timeout=True)), tmp_path)
    assert result.outcome == "timeout" and result.all_failed
    assert (d / "collect.stderr").read_bytes() == b""
    assert (d / "collect.marker").read_text() == "TG2_COLLECT_START %s\n" % _nonce(guard, "collect")
    rec = [p for p in result.phases if p["step"] == "collect"][-1]
    assert rec["marker_source"] == "file" and rec["out_sha256"] is None      # collect's stdout is the tar stream


def test_the_stream_marker_needs_no_read_back(tree):
    result, guard = do_grade("rust", tree, basic_plan("rust"))
    assert result.outcome == "parsed" and "readback" not in [s for s, _ in guard.calls]
    assert all("marker_source" not in p for p in result.phases)


# ------------------------------------------------------------------------------------- infrastructure stays infra
@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("step", ["compile", "execute"])
def test_no_marker_in_the_stream_or_the_file_stays_transport_abort(tree, lang, step):
    with pytest.raises(TransportAbort, match="marker absent"):
        do_grade(lang, tree, basic_plan(lang, **{step: dict(timeout=True, no_marker=True)}))


@pytest.mark.parametrize("step", ["compile", "execute"])
def test_a_forged_marker_file_is_not_the_marker(tree, step):
    forged = "%s deadbeefdeadbeef\n" % TAG[step]
    with pytest.raises(TransportAbort, match="marker absent"):
        do_grade("rust", tree, basic_plan("rust", **{step: dict(timeout=True, file_marker=forged)}))


@pytest.mark.parametrize("over,match", [
    (dict(timeout=True), "read-back"),
    (dict(rc=125), "read-back"),
    (dict(no_marker=True), "read-back"),
    (dict(raise_os=True), "docker runtime"),
    (dict(tar=b"not a tar archive at all" * 40), "read-back"),
    (dict(tar=make_tar([("../escape", "file", b"x")])), "read-back"),
])
def test_a_failed_read_back_is_transport_abort(tree, over, match):
    plan = basic_plan("rust", execute=dict(timeout=True), readback=over)
    with pytest.raises(TransportAbort, match=match):
        do_grade("rust", tree, plan)


def test_a_read_back_symlink_member_is_transport_abort(tree):
    plan = basic_plan("rust", execute=dict(timeout=True))
    guard = FakeGuard(plan)
    nonce = {}

    def run(cmd, **kw):
        if "TG2_READBACK_START" in cmd[-1]:
            n = re.search(r"\.tg2-marker-execute-(\w+)", cmd[-1]).group(1)
            plan.steps["readback"] = dict(tar=make_tar([(".tg2-marker-execute-" + n, "symlink", "/etc/passwd")]))
            nonce["n"] = n
        return guard.run_grader(cmd, **kw)
    with pytest.raises(TransportAbort, match="read-back"):
        do_grade("rust", tree, plan, guard=guard, run=run)
    assert nonce


# ------------------------------------------------------------------------------------------------ scripts, version
@pytest.mark.parametrize("lang", LANGS)
def test_marked_steps_write_the_marker_file_before_the_stream_marker_and_tee_their_bounded_output(tree, lang):
    _, guard = do_grade(lang, tree, basic_plan(lang))
    for step in ("compile", "execute") + (() if lang == "rust" else ("collect",)):
        script = next(c for s, c in guard.calls if s == step)[-1]
        n = _nonce(guard, step)
        file_write = 'echo "%s %s" > /report/.tg2-marker-%s-%s; ' % (TAG[step], n, step, n)
        stream = 'echo "%s %s"%s' % (TAG[step], n, " >&2" if step == "collect" else "")
        after = script.index(file_write) + len(file_write)
        assert script[after:].startswith(stream), (step, script)              # file first, then the stream marker
        if step != "collect":
            assert ("| stdbuf -o0 head -c %d | tee /report/.tg2-out-%s-%s | head -c %d; exit ${PIPESTATUS[0]}"
                    % (tg.OUTPUT_CAP, step, n, tg.OUTPUT_CAP)) in script


@pytest.mark.parametrize("lang", LANGS)
def test_preflight_proves_the_unbuffered_head_exists_before_any_marked_step(tree, lang):
    _, guard = do_grade(lang, tree, basic_plan(lang))
    assert "\nstdbuf -o0 true\n" in next(c for s, c in guard.calls if s == "preflight")[-1]


def test_the_read_back_reads_exactly_the_two_named_files_bounded_with_its_own_marker(tree):
    _, guard = do_grade("rust", tree, basic_plan("rust", execute=dict(timeout=True)))
    cmd = next(c for s, c in guard.calls if s == "readback")
    n = _nonce(guard, "execute")
    assert re.search(r'echo "TG2_READBACK_START [0-9a-f]{16}" >&2', cmd[-1])
    assert "for f in .tg2-marker-execute-%s .tg2-out-execute-%s; do" % (n, n) in cmd[-1]
    assert "head -c" in cmd[-1] and "PIPESTATUS" in cmd[-1]
    m = mounts(cmd)
    assert set(m) == {"/work/slug", "/report"} and all(v in guard.volume_names for v in m.values())
    assert "--network" in cmd and "none" in cmd


def test_the_grader_version_records_the_change():
    assert tg.VERSION == "m65-tg2-v3"


# ---------------------------------------------------------------------------- fix round 1: G2 read-back cap invariant
def test_g2_the_read_back_cap_covers_the_tar_of_a_full_out_plus_the_marker_with_margin():
    import io
    import tarfile
    bound = tg.readback_tar_bound(tg.OUTPUT_CAP)
    assert tg.READBACK_CAP >= bound + tg.READBACK_MARGIN
    buf = io.BytesIO()                                    # GNU tar's own layout: 512 B blocks in 10240 B records
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tf:
        for name, size in ((".tg2-marker-execute-" + "a" * 16, 34), (".tg2-out-execute-" + "a" * 16, tg.OUTPUT_CAP)):
            info = tarfile.TarInfo(name)
            info.size = size
            tf.addfile(info, io.BytesIO(b"x" * size))
    assert len(buf.getvalue()) <= bound


def test_g2_the_invariant_refuses_a_read_back_cap_that_cannot_hold_a_full_out():
    tg.check_readback_cap(tg.READBACK_CAP, tg.OUTPUT_CAP)
    with pytest.raises(RuntimeError, match="READBACK_CAP"):
        tg.check_readback_cap(tg.OUTPUT_CAP + 4096, tg.OUTPUT_CAP)
    with pytest.raises(RuntimeError, match="READBACK_CAP"):
        tg.check_readback_cap(tg.READBACK_CAP, tg.READBACK_CAP)        # OUTPUT_CAP raised without the cap following


def test_g2_a_timeout_with_a_full_out_reads_back_and_is_a_timeout(tree, tmp_path):
    line_len = len("TG2_RUNNER_START 0123456789abcdef\n")
    plan = basic_plan("rust", execute=dict(timeout=True, stdout="x" * (tg.OUTPUT_CAP - line_len)))
    result, guard, d = _graded("rust", tree, plan, tmp_path)
    assert result.outcome == "timeout" and (d / "execute.out").stat().st_size == tg.OUTPUT_CAP


# ---------------------------------------------------------------------------- fix round 1: G3 resource cases
@pytest.mark.parametrize("over,outcome", [(dict(oom=True, rc=137), "oom"), (dict(mem_kill=True, rc=137), "mem_kill")])
@pytest.mark.parametrize("step", ["compile", "execute"])
def test_g3_a_killed_step_with_its_marker_only_in_the_file_keeps_its_resource_outcome(tree, tmp_path, step, over, outcome):
    result, guard, d = _graded("java", tree, basic_plan("java", **{step: dict(over, stream_lost=True)}), tmp_path)
    assert result.outcome == outcome and result.all_failed
    rec = [p for p in result.phases if p["step"] == step][-1]
    assert rec["marker_source"] == "file" and (d / (step + ".marker")).is_file()


@pytest.mark.parametrize("step", ["compile", "execute"])
def test_g3_a_mem_kill_without_any_marker_stays_transport_abort(tree, step):
    with pytest.raises(TransportAbort, match="marker absent"):
        do_grade("rust", tree, basic_plan("rust", **{step: dict(mem_kill=True, rc=137, no_marker=True)}))


@pytest.mark.parametrize("over", [dict(oom=True, rc=137), dict(mem_kill=True, rc=137), dict(oom=True)])
def test_g3_a_read_back_killed_by_oom_or_the_memory_guard_is_transport_abort(tree, over):
    plan = basic_plan("rust", execute=dict(timeout=True), readback=over)
    with pytest.raises(TransportAbort, match="read-back failed"):
        do_grade("rust", tree, plan)
