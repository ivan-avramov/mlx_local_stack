"""M65 tg2 grader: a timeout kill keeps its start evidence (spec docs/specs/m65-tg2-grade-timeout-evidence.md v1,
acceptance 1; C355 (1)). Fake-docker behaviour tests, no docker needed.

THE BOX FACT the fake reproduces (spec Goal): when `subprocess.run` times out it kills the docker CLI, and the step's
host-side stdout file is EMPTY, nonce marker included (the bounded-output pipe `| head -c` only flushes at exit). The
marker FILE in the report volume exists iff the script got past its marker line before the kill.

Each test carries its class from the baseline run:
  (a) red on the baseline (fails until the fix),
  (b) green on the baseline (guards behaviour the spec says is unchanged; also stays green after the fix),
  (c) depends on a seam the spec leaves open (named in the docstring).

Seams the spec fixes (binding, used here): marker file `/report/.tg2-marker-<step>-<nonce>` holding the line
"<TAG> <nonce>"; bounded-output file `/report/.tg2-out-<step>-<nonce>`; read-back = ONE extra launched step on the same
volumes after a step whose stdout lacks the marker; `<step>.marker` / `<step>.out` stored beside the step's outputs;
`VERSION == "m65-tg2-v3"`. Seams the spec leaves open (the fake does NOT assume them): the read-back script and its
marker tag, how the read-back returns the file contents, the phase-record key names for the two sha256.
The fake therefore EXECUTES the read-back script on the host (with the container paths /report and /work/<slug> mapped
to the volume directories) instead of interpreting it."""

import hashlib
import json
import re
import subprocess

import pytest

from bench import tg2_grade as tg
from bench.token_turn_gate import TransportAbort
from bench.tests import test_tg2_grade as base      # module object: its test_* functions are not collected twice
from bench.tests.test_tg2_grade import (FakeGuard, Plan, basic_plan, do_grade, labels_of, mounts, step_of,  # noqa: F401
                                        tree)

TEST_ROOT = base.TEST_ROOT
tmp_path = base.tmp_path                              # same non-TMPDIR tree root fixture (P361 / P445)

LANGS = sorted(base.EXPECTED)
STEP_TAG = {"compile": "TG2_COMPILE_START", "execute": "TG2_RUNNER_START", "collect": "TG2_COLLECT_START"}
PARTIAL = "partial output before the kill\n"


class BoxFakeGuard(FakeGuard):
    """FakeGuard that reproduces the box fact for compile / execute / collect, and executes the read-back step.

    Plan keys on a marked step (compile / execute / collect):
      timeout=True      the step is killed: stdout empty (box fact); the marker file exists iff the script reached its
                        marker line (default) -- `no_marker=True` means it never did; `partial=` text reaches the
                        out-file only if the script writes it.
      file_marker_only  the step completes, but its stdout lacks the marker (stream lost) while the file has it.
      forge_file        the marker FILE holds a line with a wrong nonce.
    Plan key `readback` (the extra step): timeout=True | launch_error=True | no_marker=True | rc=<n>.
    """

    def __init__(self, plan, **kw):
        super().__init__(plan, **kw)
        self.readbacks = []
        self.marker_files = {}

    @staticmethod
    def _is_readback(cmd, script):
        """Delivery 2: decided on the script text only (the candidate's harness edit also tags it, with a tag the spec
        leaves open): a launched step that is none of stage / preflight / compile / execute / collect / lockfile."""
        known = ("TG2_RUNNER_START", "TG2_COMPILE_START", "TG2_COLLECT_START", "TG2_STAGE", "TG2_PREFLIGHT",
                 "generate-lockfile")
        return (cmd[:2] == ["docker", "run"] and "--name" in cmd and cmd[:3] != ["docker", "run", "-d"]
                and not any(k in script for k in known))

    def run_grader(self, cmd, **kw):
        script = cmd[-1] if cmd and isinstance(cmd[-1], str) else ""
        if cmd[:2] == ["docker", "run"] and "--name" in cmd and cmd[:3] != ["docker", "run", "-d"]:
            if self._is_readback(cmd, script):
                return self._box_readback(cmd, script, kw)
            step = step_of(cmd)
            if step in ("compile", "execute", "collect"):
                return self._box_marked(step, cmd, script, kw)
        return super().run_grader(cmd, **kw)

    # -------------------------------------------------------------------------------------------- compile/execute/collect
    def _box_marked(self, step, cmd, script, kw):
        spec = self.plan.get(step)
        tag = STEP_TAG[step]
        nonce = re.search(tag + r" (\w+)", script).group(1)
        report = self.vol(mounts(cmd)["/report"])
        marker_file = report / (".tg2-marker-%s-%s" % (step, nonce))
        out_file = report / (".tg2-out-%s-%s" % (step, nonce))
        writes_marker = ("/report/.tg2-marker-%s-%s" % (step, nonce)) in script      # the script, not the fake, decides
        writes_out = ("/report/.tg2-out-%s-%s" % (step, nonce)) in script
        reached = not spec.get("no_marker")
        if reached and writes_marker:
            marker_file.write_text("%s %s\n" % (tag, nonce))
        if spec.get("forge_file"):
            marker_file.write_text("%s deadbeef\n" % tag)
        self.marker_files[step] = marker_file.read_text() if marker_file.exists() else None   # volumes vanish at cleanup
        if spec.get("unlink_marker") and marker_file.exists():       # G7: solution code deletes the file after the echo
            marker_file.unlink()
        if spec.get("timeout"):
            cname = cmd[cmd.index("--name") + 1]
            self.step_by_name[cname] = step
            self.holder_names[cname] = labels_of(cmd)
            self.calls.append((step, cmd))
            if reached and writes_out:
                out_file.write_text("%s %s\n%s" % (tag, nonce, spec.get("partial", "")))
            if spec.get("mem_kill"):
                self.grader_mem_kill = True
            if spec.get("stream_marker"):                  # delivery 2: a timeout whose stream DID keep the marker
                kw["stdout"].write("%s %s\n" % (tag, nonce))
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout") or 1)                # else stdout stays EMPTY (box fact)
        saved = self.plan.steps.get(step)
        if spec.get("file_marker_only"):
            self.plan.steps[step] = dict(spec, no_marker=True)                            # stream lacks the marker
        try:
            done = super().run_grader(cmd, **kw)
        finally:
            if saved is not None:
                self.plan.steps[step] = saved
        if reached and writes_out:
            out_file.write_text("%s %s\n%s" % (tag, nonce, spec.get("stdout", "")))
        return done

    # --------------------------------------------------------------------------------------------------- the read-back step
    def _box_readback(self, cmd, script, kw):
        spec = self.plan.get("readback")
        cname = cmd[cmd.index("--name") + 1]
        self.step_by_name[cname] = "readback"
        self.holder_names[cname] = labels_of(cmd)
        self.calls.append(("readback", cmd))
        self.readbacks.append(cmd)
        if spec.get("mem_kill"):
            self.grader_mem_kill = True
        if spec.get("launch_error"):
            return subprocess.CompletedProcess(cmd, 125, None, None)
        if spec.get("timeout"):
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout") or 1)
        m = mounts(cmd)
        host = script
        for dst in sorted(m, key=len, reverse=True):
            host = host.replace(dst, str(self.vol(m[dst])))
        import os
        run = subprocess.run(["bash", "-c", host], capture_output=True, cwd=str(self.vol(m["/report"])), timeout=60,
                             stdin=subprocess.DEVNULL, env=dict(os.environ, COPYFILE_DISABLE="1"))   # no macOS ._ members
        kw["stdout"].buffer.write(run.stdout)
        kw["stdout"].flush()
        err = run.stderr.decode(errors="replace")
        if spec.get("no_marker"):                                       # the read-back never printed its own marker
            err = "".join(l for l in err.splitlines(True) if not re.match(r"TG2_[A-Z0-9_]+ [0-9a-f]{16}\s*$", l))
        kw["stderr"].write(err)
        return subprocess.CompletedProcess(cmd, spec.get("rc", run.returncode), None, None)


def grade_box(lang, tree, plan, **kw):
    guard = BoxFakeGuard(plan)
    result, _ = do_grade(lang, tree, plan, guard=guard, **kw)
    return result, guard


def scripts(guard):
    return {step: cmd[-1] for step, cmd in guard.calls if step in STEP_TAG}


def nonce_of(script):
    return re.search(r"TG2_[A-Z]+_START ([0-9a-f]{16})", script).group(1)


# ------------------------------------------------------------------------------------- 1. the fake reproduces the box fact
@pytest.mark.parametrize("step", ["compile", "execute"])
def test_fake_box_fact_timed_out_step_leaves_empty_stdout_and_a_marker_file_iff_the_script_reached_it(tree, step):
    """(c) validates the instrument, on the fixed script only: needs the script to write the spec'd marker file, so on the
    baseline it fails at the marker-file assertion (no file is ever written there)."""
    plan = basic_plan("rust", **{step: dict(timeout=True)})
    guard = BoxFakeGuard(plan)
    try:
        do_grade("rust", tree, plan, guard=guard)
    except TransportAbort:                               # the baseline aborts here; only the evidence is inspected
        pass
    sc = scripts(guard)[step]
    nonce = nonce_of(sc)
    assert guard.marker_files[step] == "%s %s\n" % (STEP_TAG[step], nonce)


# --------------------------------------------------------------------------------- 2. acceptance 1: timeout with file only
@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("step", ["compile", "execute"])
def test_a1_timeout_with_the_marker_only_in_the_file_is_a_model_outcome(tree, lang, step):
    """(a) red on the baseline: TransportAbort('... marker absent') because the stream is empty. After the fix: timeout."""
    plan = basic_plan(lang, **{step: dict(timeout=True, partial=PARTIAL)})
    result, guard = grade_box(lang, tree, plan)
    assert result.outcome == "timeout" and result.all_failed and result.passing == set()
    assert result.failing({"a", "b"}) == 2
    assert guard.holder_names == {}                                    # killed container and the read-back container removed
    steps = [s for s, _ in guard.calls]
    assert steps[-1] == "readback" and steps.count("readback") == 1
    assert steps[:-1] == (["image", "launch", "preflight", "compile"] if step == "compile"
                          else ["image", "launch", "preflight", "compile", "execute"])    # nothing runs after the timeout


@pytest.mark.parametrize("lang", ["java", "javascript", "cpp"])
def test_a1_collect_timeout_with_the_marker_only_in_the_file_is_a_model_outcome(tree, lang):
    """(c) the spec names collect among the marked steps but its read-back wording is about 'stdout'; collect's own marker
    lives on STDERR. Expectation taken: same rule as compile / execute -> timeout. Red on the baseline."""
    plan = basic_plan(lang, collect=dict(timeout=True))
    result, guard = grade_box(lang, tree, plan)
    assert result.outcome == "timeout" and result.all_failed
    assert [s for s, _ in guard.calls][-1] == "readback"


def test_a1_timeout_after_a_real_marker_in_the_stream_is_unchanged_and_needs_no_readback(tree):
    """(c) an ordinary timeout whose stream DID carry the marker (nothing killed the buffer): classified as before; the
    spec reads back only 'after a step whose stdout lacks the marker'. Baseline: green for the outcome."""
    plan = basic_plan("rust", execute=dict(timeout=True, stream_marker=True))
    guard = BoxFakeGuard(plan)          # delivery 2: the candidate's harness no longer leaves a marker on a timed-out stream
    result, _ = do_grade("rust", tree, plan, guard=guard)
    assert result.outcome == "timeout" and result.all_failed
    assert "readback" not in [s for s, _ in guard.calls]


# -------------------------------------------------------------------------------------- 3. G13 stays green, unchanged
@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("step", ["compile", "execute"])
def test_g13_timeout_before_the_marker_line_is_infrastructure(tree, lang, step):
    """(b) green on the baseline (no marker anywhere -> TransportAbort); stays green: the file does not exist because
    the script was killed before the marker line, and the read-back finds nothing."""
    plan = basic_plan(lang, **{step: dict(timeout=True, no_marker=True)})
    with pytest.raises(TransportAbort, match="marker"):
        grade_box(lang, tree, plan)


@pytest.mark.parametrize("step", ["compile", "execute"])
def test_g13_nonzero_exit_without_any_marker_is_infrastructure(tree, step):
    """(b) docker-level failure (rc 125 / 127 style): no marker in stream, no file."""
    plan = basic_plan("rust", **{step: dict(rc=125, no_marker=True, stderr="docker: Error response from daemon")})
    with pytest.raises(TransportAbort, match="marker"):
        grade_box("rust", tree, plan)


@pytest.mark.parametrize("step", ["compile", "execute"])
def test_g13_forged_marker_in_the_stream_without_the_nonce_is_still_infrastructure(tree, step):
    """(b) forged stream marker, real marker nowhere (and killed before the real one)."""
    plan = basic_plan("rust", **{step: dict(no_marker=True, fake_marker=True)})
    with pytest.raises(TransportAbort, match="marker"):
        grade_box("rust", tree, plan)


@pytest.mark.parametrize("step", ["compile", "execute"])
def test_g13_forged_marker_file_with_a_wrong_nonce_does_not_count(tree, step):
    """(b) green on the baseline (no file is read there); after the fix it guards 'the exact nonce only' for the file."""
    plan = basic_plan("rust", **{step: dict(timeout=True, no_marker=True, forge_file=True)})
    with pytest.raises(TransportAbort, match="marker"):
        grade_box("rust", tree, plan)


def test_g13_a_marker_file_of_another_step_or_nonce_does_not_count(tree):
    """(c) seam: the fake plants the compile marker file's line under the EXECUTE step's file name. 'exact nonce only'
    plus the per-step file name => the execute step has no marker. Baseline: green (never read)."""
    plan = basic_plan("rust", execute=dict(timeout=True, no_marker=True))

    class Cross(BoxFakeGuard):
        def _box_marked(self, step, cmd, script, kw):
            if step == "execute":
                report = self.vol(mounts(cmd)["/report"])
                other = nonce_of(scripts(self)["compile"])
                (report / (".tg2-marker-execute-%s" % nonce_of(script))).write_text("TG2_COMPILE_START %s\n" % other)
            return super()._box_marked(step, cmd, script, kw)

    guard = Cross(plan)
    with pytest.raises(TransportAbort, match="marker"):
        do_grade("rust", tree, plan, guard=guard)


# --------------------------------------------------------------------------------- 4. a failed read-back is infrastructure
@pytest.mark.parametrize("step", ["compile", "execute"])
@pytest.mark.parametrize("fail", [dict(launch_error=True), dict(timeout=True), dict(no_marker=True)],
                         ids=["launch-error", "own-timeout", "missing-readback-marker"])
def test_a1_failed_readback_is_infrastructure_never_a_model_outcome(tree, step, fail):
    """(b) vacuously green on the baseline (it aborts on the empty stream before any read-back). After the fix the marker
    FILE exists and only the failing read-back keeps this a TransportAbort: it must not become `timeout` / `crash`."""
    plan = basic_plan("rust", **{step: dict(timeout=True), "readback": fail})
    with pytest.raises(TransportAbort):
        grade_box("rust", tree, plan)


@pytest.mark.parametrize("fail", [dict(launch_error=True), dict(timeout=True), dict(no_marker=True)],
                         ids=["launch-error", "own-timeout", "missing-readback-marker"])
def test_a1_failed_readback_still_removes_its_container(tree, fail):
    """(b) vacuous on the baseline; after the fix: 'container and volume cleanup unchanged' even when the read-back fails."""
    plan = basic_plan("rust", execute=dict(timeout=True), readback=fail)
    guard = BoxFakeGuard(plan)
    with pytest.raises(TransportAbort):
        do_grade("rust", tree, plan, guard=guard)
    assert guard.holder_names == {} and guard.volumes == {}


# --------------------------------------------------------------------- 5. the read-back step itself (shape, evidence kept)
def test_a1_readback_is_one_bounded_step_on_the_same_volumes_with_no_host_bind(tree):
    """(a) red on the baseline (no read-back step)."""
    plan = basic_plan("rust", execute=dict(timeout=True))
    result, guard = grade_box("rust", tree, plan)
    assert result.outcome == "timeout"
    (rb,) = guard.readbacks
    ex = next(c for s, c in guard.calls if s == "execute")
    assert mounts(rb)["/report"] == mounts(ex)["/report"] and mounts(rb)["/work/slug"] == mounts(ex)["/work/slug"]
    assert set(mounts(rb)) == {"/work/slug", "/report"}                  # volumes only, no host bind (like compile / execute)
    text = " ".join(rb)
    for flag in ("--pull=never", "--network none", "--memory", "--name"):
        assert flag in text, flag
    assert base.IMG in rb and "--rm" not in rb


@pytest.mark.parametrize("step", ["compile", "execute"])
def test_a1_marker_and_partial_output_are_stored_beside_the_step_outputs_with_sha256(tree, tmp_path, step):
    """(c) seams: the phase-record key names for the two sha256 are open -> the test looks for the digests as VALUES of
    that step's phase record. Red on the baseline."""
    keep = tmp_path / "keep"
    plan = basic_plan("rust", **{step: dict(timeout=True, partial=PARTIAL)})
    result, guard = grade_box("rust", tree, plan, keep=keep, seq=0, boundary=0)
    d = keep / "seq-0000"
    nonce = nonce_of(scripts(guard)[step])
    marker, out = d / (step + ".marker"), d / (step + ".out")
    assert marker.read_text().splitlines() == ["%s %s" % (STEP_TAG[step], nonce)]
    assert PARTIAL in out.read_text()                                    # partial output retained as evidence
    assert (d / (step + ".stdout")).read_text() == ""                    # the box fact held in the retained receipt too
    phase = next(p for p in json.loads((d / "phases.json").read_text())["phases"] if p["step"] == step)
    values = {str(v) for v in phase.values()}
    assert hashlib.sha256(marker.read_bytes()).hexdigest() in values
    assert hashlib.sha256(out.read_bytes()).hexdigest() in values
    index = json.loads((d / "index.json").read_text())
    assert index["outcome"] == "timeout"
    for name in (step + ".marker", step + ".out"):                      # retained artifacts carry their sha256
        meta = index["artifacts"][name]
        assert hashlib.sha256((keep / meta["path"]).read_bytes()).hexdigest() == meta["sha256"]


def test_a1_out_file_is_capped_like_the_stream(tree, tmp_path):
    """(c) the spec says the out-file has 'the same cap' as `_bounded`; the fake cannot cap, so the test checks the SCRIPT:
    the out-file write sits behind the same OUTPUT_CAP bound. Red on the baseline (no out-file in the script)."""
    plan = basic_plan("rust")
    _, guard = grade_box("rust", tree, plan)
    sc = scripts(guard)["execute"]
    nonce = nonce_of(sc)
    assert "/report/.tg2-out-execute-%s" % nonce in sc
    out_at = sc.index("/report/.tg2-out-execute-%s" % nonce)
    assert "head -c %d" % tg.OUTPUT_CAP in sc[max(0, out_at - 400):out_at + 400]   # the write sits beside a same-cap bound


# --------------------------------------------------------- 6. stream-or-file; read-back only when the stream lacks marker
def test_a1_marker_seen_from_the_file_when_a_completed_steps_stream_lacks_it(tree):
    """(a) red on the baseline: spec 'decides marker seen from the stream OR the file'."""
    plan = basic_plan("rust")
    plan.steps["execute"]["file_marker_only"] = True        # (delivery 2: keep the plan's own passing test lines)
    result, guard = grade_box("rust", tree, plan)
    assert result.outcome == "parsed" and len(result.passing) == 2
    assert [s for s, _ in guard.calls].count("readback") == 1


@pytest.mark.parametrize("lang", LANGS)
def test_b_ordinary_grade_makes_no_readback_and_keeps_its_step_sequence(tree, lang):
    """(b) green on the baseline: the read-back runs only when the stream lacks the marker."""
    result, guard = grade_box(lang, tree, basic_plan(lang))
    assert result.outcome == "parsed" and guard.readbacks == []
    assert [s for s, _ in guard.calls] == ["image", "launch", "preflight", "compile", "execute"] + (
        [] if lang == "rust" else ["collect"])


def test_b_unchanged_outcome_classes_still_follow_the_marker(tree):
    """(b) compile failure / oom / mem_kill / crash after the marker: as before, with the real marker in the stream."""
    r, _ = grade_box("rust", tree, basic_plan("rust", compile=dict(rc=101, stderr="error[E0425]")))
    assert r.outcome == "compile_failure"
    r, _ = grade_box("java", tree, basic_plan("java", execute=dict(oom=True, rc=137)))
    assert r.outcome == "oom"
    r, _ = grade_box("cpp", tree, basic_plan("cpp", execute=dict(mem_kill=True, rc=137)))
    assert r.outcome == "mem_kill"
    r, _ = grade_box("javascript", tree, basic_plan("javascript", execute=dict(rc=1)))
    assert r.outcome == "crash"


# ------------------------------------------------------------------------- 7. the scripts (binding paths, ordering)
@pytest.mark.parametrize("lang", LANGS)
def test_a1_marked_scripts_write_the_marker_file_and_out_file_for_their_nonce(tree, lang):
    """(a) red on the baseline. Binding: file names from the spec; the marker is also still echoed to the stream."""
    _, guard = grade_box(lang, tree, basic_plan(lang))
    for step, sc in scripts(guard).items():
        nonce = nonce_of(sc)
        tag = STEP_TAG[step]
        assert '"%s %s"' % (tag, nonce) in sc or "%s %s" % (tag, nonce) in sc
        assert "/report/.tg2-marker-%s-%s" % (step, nonce) in sc, step
        if step != "collect":      # delivery 2: the out file is the `_bounded` step output; collect's stdout is a tar stream
            assert "/report/.tg2-out-%s-%s" % (step, nonce) in sc, step


@pytest.mark.parametrize("lang,step,invoker", [
    ("rust", "compile", "cargo test"), ("rust", "execute", "cargo test"),
    ("java", "compile", "bash ./gradlew"), ("java", "execute", "bash ./gradlew"),
    ("javascript", "compile", "jest"), ("javascript", "execute", "jest"),
    ("cpp", "compile", "cmake -S"), ("cpp", "execute", "./build/slug")])
def test_a1_marker_file_is_written_before_the_compiler_or_runner_is_invoked(tree, lang, step, invoker):
    """(a) red on the baseline: 'before invoking the compiler / runner' (spec Fix, first bullet)."""
    _, guard = grade_box(lang, tree, basic_plan(lang))
    sc = scripts(guard)[step]
    nonce = nonce_of(sc)
    first_use = sc.index("/report/.tg2-marker-%s-%s" % (step, nonce))
    assert first_use < sc.index(invoker, sc.index(STEP_TAG[step]))


def test_a1_each_grade_uses_a_fresh_nonce_in_the_file_names(tree):
    """(a) red on the baseline."""
    _, g1 = grade_box("rust", tree, basic_plan("rust"))
    _, g2 = grade_box("rust", tree, basic_plan("rust"))
    s1, s2 = scripts(g1)["execute"], scripts(g2)["execute"]
    assert "/report/.tg2-marker-execute-%s" % nonce_of(s1) in s1 and nonce_of(s1) != nonce_of(s2)
    assert "/report/.tg2-marker-execute-%s" % nonce_of(s1) not in s2


def test_a1_version_is_bumped_because_the_grader_identity_changed():
    """(a) red on the baseline ('m65-tg2-v2'). NOTE: the existing assertion in test_tg2_grade.py
    (`tg.VERSION == "m65-tg2-v2"`, test_raw_outputs_retained_by_sha256_with_phase_records) contradicts the spec's bump and
    cannot stay unchanged with the fix; the designer must reconcile (see the report)."""
    assert tg.VERSION == "m65-tg2-v3"


# -------------------------------------------- 8. the real scripts, executed on the host with stubbed compilers (box fact)
def _host_run(script, report, work, *, kill_after=None):
    """Run a step's real shell script on the host: container /report -> `report`; returns (rc, stdout, killed)."""
    script = script.replace("/report", str(report))
    import os
    import signal
    import time
    # Delivery 2: the box is macOS (BSD head, no GNU `stdbuf -o0` effect). A shim named `stdbuf` stands in for the image's
    # GNU one: `stdbuf -o0 head -c N` -> `dd bs=1 count=N` (unbuffered), so the host reproduces what the container does.
    shim = report.parent / "shim"
    shim.mkdir(exist_ok=True)
    (shim / "stdbuf").write_text('#!/bin/bash\nshift\nif [ "$1" = head ] && [ "$2" = -c ]; then exec dd bs=1 count="$3" 2>/dev/null; fi\n'
                                 'exec "$@"\n')
    (shim / "stdbuf").chmod(0o755)
    env = dict(os.environ, PATH=str(shim) + os.pathsep + os.environ["PATH"])
    proc = subprocess.Popen(["bash", "-c", script], cwd=str(work), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            stdin=subprocess.DEVNULL, start_new_session=True, env=env)
    if kill_after is not None:
        time.sleep(kill_after)
        os.killpg(proc.pid, signal.SIGKILL)
        out, _ = proc.communicate()
        return None, out.decode(errors="replace"), True
    out, _ = proc.communicate(timeout=60)
    return proc.returncode, out.decode(errors="replace"), False


@pytest.mark.parametrize("lang,step", [("rust", "compile"), ("rust", "execute"), ("java", "compile"), ("java", "execute")])
def test_c_real_script_keeps_marker_and_partial_output_after_the_whole_process_group_is_killed(tree, tmp_path, lang, step):
    """(c) seam: the harness maps /report to a host dir and replaces the compiler with a stub that prints a line then
    hangs (rust: a shell function `cargo`; java: a stub ./gradlew file). Reproduces the box fact on real script text:
    kill -9 of the process group leaves NO bytes on the stream, the marker FILE exists, the out-file keeps the partial line.
    Red on the baseline (no file written)."""
    _, guard = grade_box(lang, tree, basic_plan(lang))
    sc = scripts(guard)[step]
    nonce = nonce_of(sc)
    work, report = tmp_path / "w", tmp_path / "rep"
    work.mkdir()
    report.mkdir()
    stub = 'echo "STUB-PARTIAL-LINE"; sleep 60'
    if lang == "rust":
        sc = 'cargo() { %s; }; %s' % (stub, sc)
    else:
        (work / "gradlew").write_text(stub + "\n")
    rc, out, killed = _host_run(sc, report, work, kill_after=3)
    assert killed
    marker = report / (".tg2-marker-%s-%s" % (step, nonce))
    assert marker.read_text().splitlines() == ["%s %s" % (STEP_TAG[step], nonce)]
    assert "STUB-PARTIAL-LINE" in (report / (".tg2-out-%s-%s" % (step, nonce))).read_text()


@pytest.mark.parametrize("lang,step", [("rust", "compile"), ("rust", "execute"), ("java", "execute")])
def test_c_real_script_completed_run_keeps_stream_marker_and_exit_status(tree, tmp_path, lang, step):
    """(c) the same host harness with a stub that prints and exits 7: the stream still carries the marker line
    (unchanged), the marker file exists, and the step's own exit status survives the new plumbing ('unchanged')."""
    _, guard = grade_box(lang, tree, basic_plan(lang))
    sc = scripts(guard)[step]
    nonce = nonce_of(sc)
    work, report = tmp_path / "w", tmp_path / "rep"
    work.mkdir()
    report.mkdir()
    stub = 'echo "STUB-LINE"; exit 7'
    if lang == "rust":
        sc = 'cargo() { %s; }; %s' % (stub, sc)
    else:
        (work / "gradlew").write_text(stub + "\n")
    rc, out, killed = _host_run(sc, report, work)
    assert rc == 7 and "%s %s" % (STEP_TAG[step], nonce) in out.splitlines() and "STUB-LINE" in out
    assert (report / (".tg2-marker-%s-%s" % (step, nonce))).read_text().splitlines() == ["%s %s" % (STEP_TAG[step], nonce)]
    assert "STUB-LINE" in (report / (".tg2-out-%s-%s" % (step, nonce))).read_text()


# ======================================================================================== delivery 3 (fix round 1)
# G2 ------------------------------------------------------------------------------------------------------------
def _gnu_tar_len(sizes):
    """Length of a GNU-format tar of regular files of these sizes, built by the stdlib (independent of the candidate)."""
    import io
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tf:
        for i, n in enumerate(sizes):
            info = tarfile.TarInfo(".tg2-x-%d-0123456789abcdef" % i)
            info.size = n
            tf.addfile(info, io.BytesIO(b"x" * n))
    return len(buf.getvalue())


def test_g2_the_readback_cap_covers_the_tar_of_a_full_out_file():
    """(b) independent of the candidate's helper: a full `.out` (OUTPUT_CAP) plus the marker line, tarred by the stdlib,
    must pass the read-back's `head -c` cap untouched, else tar takes SIGPIPE and a real timeout becomes TransportAbort."""
    assert _gnu_tar_len([40, tg.OUTPUT_CAP]) <= tg.READBACK_CAP


def test_g2_the_cap_invariant_refuses_a_cap_that_is_too_small():
    """(c) seam: the candidate's named `check_readback_cap(readback_cap, output_cap)` (erratum v1b: asserted at import)."""
    tg.check_readback_cap(tg.READBACK_CAP, tg.OUTPUT_CAP)                       # the shipped values pass
    with pytest.raises(RuntimeError):
        tg.check_readback_cap(tg.OUTPUT_CAP, tg.OUTPUT_CAP)                      # exactly the bare cap cannot hold the tar


def test_g2_a_timeout_with_a_full_out_file_is_read_back_whole(tree, tmp_path):
    """(c) seam: the fake executes the candidate's read-back script on the host (bsdtar). A full-size `.out` (exactly
    OUTPUT_CAP bytes, as the bounded step would leave) must come back whole: outcome `timeout`, not TransportAbort."""
    marker_line = len("TG2_RUNNER_START 0123456789abcdef\n")
    plan = basic_plan("rust", execute=dict(timeout=True, partial="y" * (tg.OUTPUT_CAP - marker_line)))
    result, guard = grade_box("rust", tree, plan, keep=tmp_path / "keep", seq=0, boundary=0)
    assert result.outcome == "timeout" and result.all_failed
    assert (tmp_path / "keep/seq-0000/execute.out").stat().st_size == tg.OUTPUT_CAP


# G3 ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("step", ["compile", "execute"])
@pytest.mark.parametrize("kind", ["oom", "mem_kill"])
def test_g3_a_killed_step_with_its_marker_only_in_the_file_keeps_its_resource_outcome(tree, step, kind):
    """The stream is lost, the marker file survives, the container was OOM-killed / memory-guard killed ->
    `oom` / `mem_kill`, not TransportAbort (vacuously red on the baseline, which aborts on the stream)."""
    plan = basic_plan("java")
    plan.steps.setdefault(step, {}).update({kind: True, "rc": 137, "file_marker_only": True})
    result, guard = grade_box("java", tree, plan)
    assert result.outcome == kind and result.all_failed and result.passing == set()
    assert [s for s, _ in guard.calls].count("readback") == 1


@pytest.mark.parametrize("step", ["compile", "execute"])
def test_g3_a_memory_guard_kill_without_any_marker_stays_infrastructure(tree, step):
    """(b): no marker in the stream or the file -> TransportAbort even though the memory guard fired."""
    plan = basic_plan("java")
    plan.steps.setdefault(step, {}).update({"mem_kill": True, "rc": 137, "no_marker": True})
    with pytest.raises(TransportAbort, match="marker"):
        grade_box("java", tree, plan)


@pytest.mark.parametrize("kill", ["oom", "mem_kill"])
@pytest.mark.parametrize("step", ["compile", "execute"])
def test_g3_a_readback_killed_by_oom_or_the_memory_guard_is_infrastructure(tree, step, kill):
    """The marker file exists, but the READ-BACK step itself was killed -> TransportAbort (vacuous on the baseline)."""
    plan = basic_plan("rust", **{step: dict(timeout=True), "readback": {kill: True}})
    with pytest.raises(TransportAbort):
        grade_box("rust", tree, plan)


# G7 ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("step", ["compile", "execute"])
def test_g7_known_limit_a_solution_that_unlinks_its_marker_file_is_infrastructure(tree, step):
    """(b) documents the recorded KNOWN LIMIT (spec): code that runs after the marker can delete its marker file; with the
    stream lost too, the step has no evidence and the grade is TransportAbort (a runaway becomes a transport DNF). Not a
    model outcome, not hardened (agentic outputs are not adversarial)."""
    plan = basic_plan("rust", **{step: dict(timeout=True, unlink_marker=True)})
    with pytest.raises(TransportAbort, match="marker"):
        grade_box("rust", tree, plan)
