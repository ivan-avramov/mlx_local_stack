#!/usr/bin/env python3
"""Agentic-edit probe through OPENCODE, the scaffold this stack actually ships.

WHY THIS EXISTS. The B recommendation rests entirely on aider polyglot, and `docs/campaign-results.md`
lists "opencode agentic evidence" as its top unresolved caveat: a scaffold change can plausibly move
a repair-driven result. It became urgent when `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` was
measured at 3.75 malformed responses PER CASE under aider's `diff` protocol (vs 0.036 and 0.009 for
the two winners) and then 0 malformed under `whole` — proving the failure is the EDIT PROTOCOL, not
code generation. opencode drives edits through TOOL CALLS rather than text diffs, so it is a
different protocol and the weakness may not transfer. That is the question this answers.

WHAT IT MEASURES, and what it deliberately does not. Per case: whether the target file was actually
modified, whether the provided tests then pass, and how long it took. `file_changed == False` is the
opencode analogue of aider's `malformed` — the model failed to operate the edit protocol at all. It
does NOT attempt aider's two-attempt repair loop, so its pass rate is NOT comparable to aider's
`final`; it is a first-attempt number and is labelled as such in the row.

INTEGRITY. `.meta/` is excluded from the scratch copy, because it contains `example.py` — the
reference solution. aider excludes it the same way. A probe that leaves the answer in the workspace
measures nothing. A rewritten test file is the second integrity hole (the model can make any suite
pass by replacing it) — detected by diffing the test file's content before/after, scored as a
failure, never graded.

GRADING SANDBOX. python grades directly against `.venv-bench` (no toolchain needed). go, rust,
java, javascript grade INSIDE the `aider-benchmark` docker image, the only place all five polyglot
toolchains exist at pinned versions (go 1.21.5, node 20.20.2, cargo 1.97.1, javac 21.0.11, python
3.11.15) — see `_docker_grade`. If docker is unavailable, those rows degrade to skipped/acc:null
with a note rather than crashing the batch.

SESSION BOUND. A session is bounded by `bench/progress_gate.py`'s PROGRESS-GATED policy, not a flat
wall-clock timeout: every `--tick-s` (default 300) the workdir is snapshot to a copy and graded; a
stalled or looping session is killed early, and `--hard-ceiling-s` (default 3600) is a generous
backstop only. See that module's docstring for the recovered design and rationale.

Usage:
  run_opencode_probe.py --model <served-name> --items affine-cipher,beer-song [--lang python]
                        [--tick-s 300] [--hard-ceiling-s 3600] [--out benchmark/results/<model>/opencode.jsonl]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "benchmark"))
from bench import progress_gate  # noqa: E402 — needs the sys.path insert above

# The scaffold is part of the serving path (the suffix lesson): an unpinned client version is an
# unrecorded output-determining knob. Bump this deliberately, never implicitly.
PINNED_OPENCODE_VERSION = "1.18.15"


def _polyglot_root() -> Path:
    env = os.environ.get("POLYGLOT_DIR")
    candidates = ([Path(env)] if env else []) + [
        Path.home() / "ws/mlx_local_stack_workdir/polyglot-benchmark",
        Path.home() / "ws/polyglot-benchmark",
        Path.home() / "polyglot-benchmark",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    sys.exit("polyglot exercises not found (set POLYGLOT_DIR — see config.sh)")


def _opencode_version() -> str:
    try:
        return subprocess.check_output(["opencode", "--version"], text=True, timeout=30).strip()
    except Exception as e:  # noqa: BLE001
        sys.exit(f"cannot determine opencode version ({e}); refusing to run unversioned")


def _polyglot_sha(root: Path) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:  # noqa: BLE001
        return None


def _scrub_pii(s: str) -> str:
    # The repo is PUBLIC: persisted rows must not carry absolute home paths. opencode's
    # transcript echoes tool-call paths under the scratch workdir, so scrub the workdir
    # first (keeps the more specific placeholder), then any remaining home prefix.
    workdir = os.environ.get("STACK_WORKDIR")
    if workdir:
        s = s.replace(workdir, "$STACK_WORKDIR")
    home = os.path.expanduser("~")
    if home and home != "~":
        s = s.replace(home, "$HOME")
    return s


@contextmanager
def _scratch_dir(name: str):
    # macOS tempdirs live under /var -> /private/var; opencode registers the --dir project
    # root by the given path STRING while its tools canonicalize, so a symlinked component
    # makes every absolute tool path fail the project-boundary prefix check and auto-reject
    # in non-interactive `run` mode (sessions "complete" in seconds with no edits).
    with tempfile.TemporaryDirectory(prefix=f"oc-{name}-") as tmp:
        yield Path(os.path.realpath(tmp))


def _prepare(src: Path, dst: Path) -> None:
    """Copy an exercise WITHOUT .meta (which holds the reference solution)."""
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".meta"), dirs_exist_ok=True)


# Listed in a `.meta/config.json`'s "solution" array but not actually part of what the model
# should edit — exercism/aider both treat these as build manifests, not solution source. aider's
# own benchmark.py (run_unit_tests / the solution-file filter) carries the same exclusion set.
_IGNORE_SOLUTION_FILES = {"Cargo.toml", "CMakeLists.txt", "build.gradle"}


def _solution_and_test(d: Path, src: Path, lang: str) -> tuple[Path, Path]:
    """Resolve the exercise's solution/test files.

    Prefers `.meta/config.json`'s `files.solution` / `files.test` — the exercism/aider source of
    truth (the same field `aider`'s own `benchmark.py` reads) — because the filename-heuristic
    fallback below only holds for python/go, where the solution sits at the exercise root and its
    name contains "test" nowhere. It breaks for java (`src/main/java/Series.java` vs
    `src/test/java/SeriesTest.java`, both nested), rust (`src/lib.rs` vs `tests/decimal.rs`, a
    non-recursive glob misses the nested solution entirely) and javascript (a non-test `*.js` file
    picked alphabetically can be `babel.config.js` instead of the real solution).

    Reads config.json from `src`, the UNCOPIED original exercise dir — `_prepare` strips `.meta`
    from the staged copy `d` on purpose (it holds the reference solution), so it is gone by the
    time this runs on `d`. Only relative filenames are taken from it; no solution content is read.
    """
    config_file = src / ".meta/config.json"
    if config_file.exists():
        try:
            files = json.loads(config_file.read_text()).get("files", {})
            solutions = [f for f in files.get("solution", []) if f not in _IGNORE_SOLUTION_FILES]
            tests = files.get("test", [])
            if solutions and tests:
                sol, test = d / solutions[0], d / tests[0]
                if sol.exists() and test.exists():
                    return sol, test
        except (json.JSONDecodeError, OSError):
            pass  # fall through to the heuristic below
    ext = {"python": ".py", "javascript": ".js", "go": ".go", "rust": ".rs", "java": ".java"}[lang]
    tests = sorted(p for p in d.rglob(f"*_test{ext}")) + sorted(d.rglob(f"*test*{ext}"))
    test = tests[0] if tests else None
    sols = [p for p in sorted(d.rglob(f"*{ext}")) if p != test and not p.name.startswith("test")]
    if not sols or test is None:
        sys.exit(f"could not identify solution/test in {d}")
    return sols[0], test


def _tick_snapshot_fn(cwd: Path, sol: Path, test: Path, before_sol: str, grade, log_path: Path):
    """Build the progress-gate's per-tick `snapshot_fn`.

    NEVER grades or hashes the LIVE `cwd` in place — a still-running opencode session can be
    mid-write on any file. Each tick copies the whole workdir into a throwaway temp dir first
    (`shutil.copytree`) and only ever touches that copy; this also protects the live session from
    `_grade_java`'s in-place test-file mutation, which would otherwise corrupt an in-progress run.

    Only re-grades (potentially an expensive docker invocation) when the solution file's hash
    actually changed since the previous tick — if nothing changed, the previous grade still holds,
    so `n_failing=None` is returned and the gate simply carries the last known count forward
    (`ProgressGate` only updates its tracked failing-count on a non-None reading).
    """
    rel_sol = sol.relative_to(cwd)
    rel_test = test.relative_to(cwd)
    prev_hash = {"h": progress_gate.solution_hash(before_sol)}

    def _snapshot(elapsed_s: float) -> progress_gate.Tick:
        log_text = log_path.read_text(errors="replace") if log_path.exists() else ""
        signature = progress_gate.tail_signature(log_text)
        try:
            with tempfile.TemporaryDirectory(prefix="oc-tick-") as tickdir:
                snap = Path(tickdir) / "snap"
                shutil.copytree(cwd, snap)
                snap_sol = snap / rel_sol
                sol_text = snap_sol.read_text(errors="replace") if snap_sol.exists() else None
                if sol_text is None:
                    return progress_gate.Tick(elapsed_s=elapsed_s, n_failing=None,
                                              solution_hash=prev_hash["h"], signature=signature,
                                              file_changed=False)
                h = progress_gate.solution_hash(sol_text)
                changed = h != prev_hash["h"]
                prev_hash["h"] = h
                n_failing = None
                if changed:
                    try:
                        ok, _tail = grade(snap, snap / rel_test)
                        n_failing = 0 if ok else 1
                    except Exception:  # noqa: BLE001 — an ungradeable tick is neutral, not fatal
                        n_failing = None
                return progress_gate.Tick(elapsed_s=elapsed_s, n_failing=n_failing,
                                          solution_hash=h, signature=signature, file_changed=changed)
        except OSError:
            # Copying a directory a live process is writing to can race (a file created/removed
            # mid-copy). A missed tick is NEUTRAL (no signal), not a crash -- see the module
            # docstring's "undeterminable" handling in ProgressGate.
            return progress_gate.Tick(elapsed_s=elapsed_s, n_failing=None,
                                      solution_hash=prev_hash["h"], signature=signature,
                                      file_changed=False)

    return _snapshot


def _run_opencode(model: str, cwd: Path, prompt: str, sol: Path, test: Path, grade,
                  before_sol: str, *, tick_s: int, hard_ceiling_s: int, poll_s: float,
                  stall_ticks: int, loop_repeats: int,
                  pure: bool) -> tuple[int, str, float, "progress_gate.GateResult"]:
    """Run opencode under the PROGRESS-GATED bound (`bench/progress_gate.py`), not a flat
    wall-clock timeout. A wedged session is killed on a stall/loop diagnosis well before
    `hard_ceiling_s`; a healthy long session is never killed just for being slow. The policy is
    IDENTICAL across models — only the diagnosis timing can differ, never the compute budget.
    """
    # `--dir` is REQUIRED, not a nicety: subprocess cwd does NOT set opencode's project root. The
    # first run of this probe passed cwd=<scratch> and opencode resolved its project to the STACK
    # REPO instead, wrote affine_cipher.py and affine_cipher_test.py into the repo root, and ran the
    # tests there. The row said file_changed=False (true of the scratch copy) and would have been
    # read as "the model cannot operate the edit protocol" — the exact opposite of what happened,
    # since the log shows it wrote the file and self-verified successfully.
    cmd = ["opencode", "run", "--dir", str(cwd), "--model", f"mlx-local/{model}"]
    if pure:
        # opencode's own flag for "no external plugins". The shipped config references a plugin
        # fetched over git; loading it adds a network dependency that is not part of the model's
        # capability, and a probe that can hang on a fetch measures the network.
        cmd.append("--pure")
    cmd.append(prompt)

    log_path = cwd / ".opencode_probe_log.txt"
    with log_path.open("w") as log_f:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=log_f, stderr=subprocess.STDOUT, text=True)
        snapshot_fn = _tick_snapshot_fn(cwd, sol, test, before_sol, grade, log_path)
        result = progress_gate.run_progress_gated(
            proc, snapshot_fn, tick_s=tick_s, hard_ceiling_s=hard_ceiling_s, poll_s=poll_s,
            stall_ticks=stall_ticks, loop_repeats=loop_repeats)
    log = log_path.read_text(errors="replace") if log_path.exists() else ""
    return proc.returncode, log, result.elapsed_s, result


def _grade_python(cwd: Path, test: Path) -> tuple[bool, str]:
    py = REPO / ".venv-bench/bin/python"
    if not py.exists():
        return False, "no .venv-bench python for grading"
    p = subprocess.run([str(py), "-m", "pytest", test.name, "-q", "--no-header"],
                       cwd=cwd, capture_output=True, text=True, timeout=300)
    return p.returncode == 0, (p.stdout or "")[-600:]


# --------------------------------------------------------------------------------- docker sandbox
# go/rust/java/javascript grade INSIDE the `aider-benchmark` image (see module docstring): it is
# the only place all four toolchains exist at pinned versions, and it is a real sandbox for
# untrusted model-written code, unlike shelling out to a host toolchain.
_AIDER_IMAGE = "aider-benchmark"


def _docker_available() -> bool:
    """Best-effort probe for a reachable docker daemon. Never raises — an unreachable/missing
    docker degrades grading to skipped/acc:null (requirement: never crash the batch), it does not
    abort the run."""
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=15, check=True)
        return True
    except Exception:  # noqa: BLE001 — daemon down, docker missing, anything: same outcome
        return False


def _docker_grade(work: Path, cmd: list[str], *, docker_ok: bool, timeout: int = 300) -> tuple[bool, str]:
    """Run `cmd` for one staged exercise inside the aider-benchmark image, cwd `/work`.

    `work` MUST be an absolute path. A relative `-v` mount does not error — it silently becomes an
    empty NAMED VOLUME instead of a bind mount, so the container sees an empty directory and every
    test "fails" for a reason that has nothing to do with the model (a documented trap in this
    codebase's git-history). `tempfile.TemporaryDirectory` already yields absolute paths, so this
    assertion should never fire in normal use; it exists so a future caller trips it loudly instead
    of quietly grading against nothing.

    The gradle/cargo named volumes cache toolchain state across per-exercise `docker run --rm`
    invocations, which are otherwise a cold start every time (no shared filesystem between runs) —
    without them, a full java batch would re-download the gradle distribution per exercise.
    """
    if not work.is_absolute():
        return False, f"internal error: staged dir must be absolute for a docker -v mount, got {work}"
    if not docker_ok:
        return False, "docker unavailable — grading skipped (acc:null)"
    docker_cmd = [
        "docker", "run", "--rm",
        "-v", f"{work}:/work",
        "-v", "mlx-bench-gradle-cache:/root/.gradle",
        "-v", "mlx-bench-cargo-registry:/root/.cargo/registry",
        "-w", "/work",
        _AIDER_IMAGE,
    ] + cmd
    try:
        p = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"docker grading timed out after {timeout}s"
    except FileNotFoundError:
        return False, "docker not installed"
    return p.returncode == 0, ((p.stdout or "") + (p.stderr or ""))[-600:]


def _grade_go(work: Path, test: Path, *, docker_ok: bool) -> tuple[bool, str]:
    return _docker_grade(work, ["go", "test", "./..."], docker_ok=docker_ok, timeout=180)


def _grade_rust(work: Path, test: Path, *, docker_ok: bool) -> tuple[bool, str]:
    # `--include-ignored`: exercism rust exercises ship extra-credit cases marked #[ignore] that
    # the reference solution is still expected to pass — the same flag aider's own
    # benchmark.py:TEST_COMMANDS uses. Generous timeout: a cold cargo registry cache fetches and
    # compiles the crate graph, not just this one exercise's code.
    return _docker_grade(work, ["cargo", "test", "--", "--include-ignored"],
                         docker_ok=docker_ok, timeout=600)


def _grade_javascript(work: Path, test: Path, *, docker_ok: bool) -> tuple[bool, str]:
    # The aider image ships /aider/benchmark/npm-test.sh: symlinks a pre-installed node_modules
    # (jest + the exercism babel preset, pinned in the image's own Dockerfile) into the exercise
    # dir, un-skips any `xtest(` left in the spec file, then `npm run test`. Reusing it (rather
    # than reimplementing) keeps this grader on the exact recipe the campaign already trusts.
    return _docker_grade(work, ["bash", "/aider/benchmark/npm-test.sh"],
                         docker_ok=docker_ok, timeout=180)


_DISABLED_RE = re.compile(r"@Disabled\([^)]*\)\s*\n")


def _grade_java(work: Path, test: Path, *, docker_ok: bool) -> tuple[bool, str]:
    # Exercism ships java tests with every case but the first `@Disabled` — aider's own harness
    # (benchmark/benchmark.py:run_unit_tests) strips this before running, else the suite "passes"
    # trivially on a single enabled test. Safe to mutate `test` here: this only ever runs AFTER
    # the test-tamper check in main() (_grade_result), which already compared against the
    # pre-grading content — mutating it now cannot manufacture a false tamper verdict.
    try:
        test.write_text(_DISABLED_RE.sub("", test.read_text()))
    except OSError as e:
        return False, f"could not prepare java test file: {e}"
    return _docker_grade(work, ["bash", "-lc", "chmod +x gradlew && ./gradlew test --no-daemon"],
                         docker_ok=docker_ok, timeout=600)


def _grade_result(work: Path, test: Path, test_before: str, changed: bool,
                  grade) -> tuple[bool, str, bool]:
    """Decide pass/fail/tamper for one exercise, in priority order: a rewritten test file
    invalidates the grade outright (the opencode analogue of aider's `malformed` — the model can
    make any suite pass by replacing it, measured for real on this probe's first run); an
    untouched solution file means the model never attempted the edit; only then does the exercise
    actually get graded. Returns (passed, tail, test_modified) — test_modified is surfaced
    separately so the row can report it even though the outcome collapses to `passed=False`.
    """
    test_modified = test.read_text(errors="replace") != test_before
    if test_modified:
        return False, "TEST FILE MODIFIED — grade invalid, scored as a failure", True
    if not changed:
        return False, "solution file untouched", False
    passed, tail = grade(work, test)
    return passed, tail, False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--items", required=True, help="comma list of exercise names")
    ap.add_argument("--lang", default="python")
    ap.add_argument("--tick-s", type=int, default=progress_gate.DEFAULT_TICK_S,
                    help="progress-gate soft-budget interval, seconds (default "
                         f"{progress_gate.DEFAULT_TICK_S})")
    ap.add_argument("--hard-ceiling-s", type=int, default=progress_gate.DEFAULT_HARD_CEILING_S,
                    help="generous backstop total wall-clock cap, seconds (default "
                         f"{progress_gate.DEFAULT_HARD_CEILING_S}); the progress gate is expected "
                         f"to fire first on any wedged session")
    ap.add_argument("--stall-ticks", type=int, default=progress_gate.DEFAULT_STALL_TICKS,
                    help="consecutive flat ticks before stopping as stalled (default "
                         f"{progress_gate.DEFAULT_STALL_TICKS})")
    ap.add_argument("--loop-repeats", type=int, default=progress_gate.DEFAULT_LOOP_REPEATS,
                    help="repeated identical tick signature before stopping as looping (default "
                         f"{progress_gate.DEFAULT_LOOP_REPEATS})")
    ap.add_argument("--poll-s", type=float, default=5.0, help="liveness poll interval between ticks")
    ap.add_argument("--timeout", type=int, default=None,
                    help="DEPRECATED alias for --hard-ceiling-s, kept for old invocations. There "
                         "is no longer a flat kill timeout -- see bench/progress_gate.py.")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-pure", action="store_true", help="load external plugins too")
    ap.add_argument("--allow-version-drift", action="store_true",
                    help=f"run even if opencode != {PINNED_OPENCODE_VERSION} (drift is recorded)")
    a = ap.parse_args()
    # `--timeout` is a deprecated alias kept for old invocations; it now maps onto the
    # PROGRESS-GATE's hard ceiling (a backstop), never a flat kill.
    hard_ceiling_s = a.timeout if a.timeout is not None else a.hard_ceiling_s

    SUPPORTED_LANGS = {"python", "go", "rust", "java", "javascript"}
    if a.lang not in SUPPORTED_LANGS:
        sys.exit(f"unsupported --lang {a.lang!r}; supported: {sorted(SUPPORTED_LANGS)}")

    # go/rust/java/javascript grade inside docker; probe availability ONCE per run rather than
    # per-item, so a down daemon degrades to skipped/acc:null rows instead of a `docker info`
    # timeout on every single exercise.
    docker_ok = True
    if a.lang != "python":
        docker_ok = _docker_available()
        if not docker_ok:
            print(f"!! docker unavailable — every {a.lang} row in this run will be skipped "
                 f"(acc:null); see module docstring (GRADING SANDBOX)", flush=True)
    graders = {
        "python": _grade_python,
        "go": lambda w, t: _grade_go(w, t, docker_ok=docker_ok),
        "rust": lambda w, t: _grade_rust(w, t, docker_ok=docker_ok),
        "java": lambda w, t: _grade_java(w, t, docker_ok=docker_ok),
        "javascript": lambda w, t: _grade_javascript(w, t, docker_ok=docker_ok),
    }
    grade = graders[a.lang]

    oc_version = _opencode_version()
    if oc_version != PINNED_OPENCODE_VERSION and not a.allow_version_drift:
        sys.exit(f"opencode {oc_version} != pinned {PINNED_OPENCODE_VERSION}; a scaffold version "
                 f"is output-determining. Bump PINNED_OPENCODE_VERSION deliberately or pass "
                 f"--allow-version-drift to record the drift.")

    polyglot = _polyglot_root()
    poly_sha = _polyglot_sha(polyglot)
    root = polyglot / a.lang / "exercises/practice"
    out = Path(a.out) if a.out else REPO / "benchmark/results" / a.model / "opencode.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    # Manifest beside the rows, same machinery as the two-phase harness, so compare/clean-stale
    # see the sampling + code shas this run inherited — plus the scaffold identity in `runtime`.
    try:
        from bench import provenance
        man = provenance.gather(a.model, profile="deployed",
                                runtime={"client": "opencode", "edit_format": "tools",
                                         "opencode_version": oc_version,
                                         "polyglot_sha": poly_sha,
                                         "tick_s": a.tick_s, "hard_ceiling_s": hard_ceiling_s,
                                         "stall_ticks": a.stall_ticks,
                                         "loop_repeats": a.loop_repeats})
        out.with_suffix(".manifest.json").write_text(json.dumps(man, indent=2))
    except Exception as e:  # noqa: BLE001 — never block a run on provenance, but say so loudly
        print(f"!! manifest not written: {e}", flush=True)

    for name in [s.strip() for s in a.items.split(",") if s.strip()]:
        src = root / name
        if not src.is_dir():
            print(f"!! {name}: no such exercise at {src}", flush=True)
            continue
        with _scratch_dir(name) as tmp:
            work = Path(tmp) / name
            _prepare(src, work)
            sol, test = _solution_and_test(work, src, a.lang)
            before = sol.read_text(errors="replace")
            test_before = test.read_text(errors="replace")
            prompt = (
                f"Implement the solution in {sol.name} so that the tests in {test.name} pass. "
                f"The specification is in .docs/instructions.md — read it first. "
                f"Do NOT modify {test.name}. Do not create new files unless required by the spec."
            )
            rc, log, dur, gate_result = _run_opencode(
                a.model, work, prompt, sol, test, grade, before,
                tick_s=a.tick_s, hard_ceiling_s=hard_ceiling_s, poll_s=a.poll_s,
                stall_ticks=a.stall_ticks, loop_repeats=a.loop_repeats, pure=not a.no_pure)
            after = sol.read_text(errors="replace")
            changed = after != before
            # A rewritten test file invalidates the grade: the model can make any suite pass by
            # replacing it. Observed for real on the first run, which overwrote the test file
            # despite the prompt forbidding it — so this is a measured hazard, not a precaution.
            passed, tail, test_modified = _grade_result(work, test, test_before, changed, grade)
            row = {
                "bench": "opencode", "id": f"{a.lang}/{name}", "model": a.model, "sample": 0,
                "schema_version": 2, "scaffold": "opencode", "attempts": 1,
                "passed": passed, "file_changed": changed, "test_modified": test_modified,
                "opencode_rc": rc, "opencode_version": oc_version, "polyglot_sha": poly_sha,
                "wall_s": round(dur, 1),
                # PROGRESS-GATED bound (bench/progress_gate.py), not a flat timeout:
                # stop_reason in {completed, stalled, looping, hard_ceiling}; timed_out is True for
                # any non-"completed" stop (kept for callers that only care about the binary).
                "stop_reason": gate_result.stop_reason,
                "timed_out": gate_result.stop_reason != "completed",
                "gate_ticks": len(gate_result.ticks),
                "gate_failure_trajectory": [t.n_failing for t in gate_result.ticks],
                "gate_effective_bound_s": round(gate_result.elapsed_s, 1),
                "note": "FIRST-ATTEMPT only — not comparable to aider `final`, which allows a "
                        "second test-informed attempt",
                "grade_tail": _scrub_pii(tail[-300:]), "log_tail": _scrub_pii(log[-500:]),
            }
            with out.open("a") as f:
                f.write(json.dumps(row) + "\n")
            print(f"[{time.strftime('%H:%M:%S')}] {name:16s} changed={changed} passed={passed} "
                  f"rc={rc} {dur:.0f}s", flush=True)
    print(f"rows -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
