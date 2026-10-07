"""Shared opencode probe mechanics. Legacy bodies are retained apart from statement-layout cleanup."""
from __future__ import annotations
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import FunctionType
from bench import provenance, progress_gate

REPO = Path(__file__).resolve().parents[2]

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


def _portable(path: Path) -> str:
    """Manifest-safe form: `$STACK_WORKDIR/...` / `~/...`, never an absolute home path."""
    p = str(path)
    for var in ("STACK_WORKDIR",):
        root = os.environ.get(var)
        if root and (p == root or p.startswith(root.rstrip("/") + "/")):
            return "$" + var + p[len(root.rstrip("/")):]
    home = str(Path.home())
    if p.startswith(home.rstrip("/") + "/"):
        return "~" + p[len(home.rstrip("/")):]
    return p


def _polyglot_sha(root: Path) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:  # noqa: BLE001
        return None


def _stack_workdir(*, required: bool = True) -> Path | None:
    """M53/P89: `bench.paths.stack_workdir` (env, else config.sh parsed, else refuse) — resolved at
    entry before the M50 guard; a hand launch from a fresh terminal needs no export."""
    from bench import paths
    try:
        return paths.stack_workdir(required=required)
    except paths.MissingWorkdirError as e:
        raise SystemExit(f"{e} Transcripts must live under it.") from None


def _scrub_pii(s: str) -> str:
    # The repo is PUBLIC: persisted rows must not carry absolute home paths. opencode's
    # transcript echoes tool-call paths under the scratch workdir, so scrub the workdir
    # first (keeps the more specific placeholder), then any remaining home prefix.
    workdir = _stack_workdir(required=False)
    if workdir:
        s = s.replace(str(workdir), "$STACK_WORKDIR")
    home = os.path.expanduser("~")
    if home and home != "~":
        s = s.replace(home, "$HOME")
    # `ls -l` output echoed into log tails carries the login name in the owner column
    # ("drwxr-xr-x@ 7 <user>  staff ..."); 6 landed M55 rows leaked it (2026-10-04). Whole-word only.
    name = _login_name()
    if name and len(name) >= 3:
        s = re.sub(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", "$USER", s)
    return s


def _login_name() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return os.path.basename(os.path.expanduser("~"))


def _scrub_error(msg, limit: int | None = None) -> str:
    """Persisted error text: the COMPLETE message goes through `_scrub_pii` (workdir/home/login name) and
    `portable_path` BEFORE any truncation, so a cut can never leave half a home prefix."""
    out = provenance.portable_path(_scrub_pii(str(msg)))
    return out[:limit] if limit else out


def _scrub_then_tail(s: str, n: int) -> str:
    """Scrub PII from the WHOLE string, then take the tail — never the reverse. Slicing first can
    cut a `/Users/<name>/...` boundary in half, leaving a fragment `_scrub_pii` no longer
    recognizes as a home path (measured 2026-09-05 by the M35 verifier: 21 of 399 slice widths
    leaked the real username this way). Shared by both agentic probes (opencode, dsh) so the fix
    lives in exactly one place."""
    return _scrub_pii(s)[-n:]


def _scratch_root() -> str | None:
    root = os.environ.get("OPENCODE_PROBE_SCRATCH")
    if not root:
        workdir = _stack_workdir(required=False)
        if workdir:
            root = str(Path(workdir) / "scratch" / "octmp.noindex")
    return root



@contextmanager
def _scratch_dir(name: str):
    # macOS tempdirs live under /var -> /private/var; opencode registers the --dir project
    # root by the given path STRING while its tools canonicalize, so a symlinked component
    # makes every absolute tool path fail the project-boundary prefix check and auto-reject
    # in non-interactive `run` mode (sessions "complete" in seconds with no edits).
    # 2026-10-04 (M55): Spotlight indexes the per-item node_modules trees and storms the box
    # (load 12). macOS skips `*.noindex` directories, so the scratch root defaults to
    # `<STACK_WORKDIR>/scratch/octmp.noindex` (created on demand); `OPENCODE_PROBE_SCRATCH`
    # overrides it. TMPDIR is no longer load-bearing for the probe.
    root = _scratch_root()
    if root:
        os.makedirs(root, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"oc-{name}-", dir=root) as tmp:
        yield Path(os.path.realpath(tmp))


def _prepare(src: Path, dst: Path) -> None:
    """Copy an exercise WITHOUT .meta (which holds the reference solution)."""
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".meta"), dirs_exist_ok=True)



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


def _tick_snapshot_fn(cwd: Path, sol: Path, test: Path, before_sol: str, grade, log_path: Path,
                      tmp_dir: str | Path | None = None):
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
            with tempfile.TemporaryDirectory(prefix="oc-tick-", dir=tmp_dir) as tickdir:   # run temp dir, not /tmp
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


def _item_seed(item_id: str, seed_base: int) -> int:
    from bench import rowschema
    return rowschema.sample_seed(item_id, 0, base=seed_base)


def _seed_row_fields(item_id: str, seed_base: int, overlay_sha256: str) -> dict:
    return {"sampler_seed": _item_seed(item_id, seed_base), "seed_base": seed_base,
            "overlay_sha256": overlay_sha256}


def _sha_of(path) -> str | None:
    import hashlib
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _cache_bin_inventory_sha256(cache_home: Path) -> str:
    """sha256 over the sorted (relative path, size, sha256) list of every file under
    `<cache>/opencode/bin` (and `packages` if present). The shared cache is NOT catalogue-only: `bin`
    holds ripgrep / LSP executables that shape tool feedback, so its content is observed and part of the
    run identity (the models.dev catalogue file itself is deliberately not inventoried)."""
    import hashlib
    entries = []
    for sub in ("bin", "packages"):
        root = Path(cache_home) / "opencode" / sub
        if not root.is_dir():
            continue
        for f in sorted(x for x in root.rglob("*") if x.is_file()):
            try:
                entries.append([f"{sub}/{f.relative_to(root)}", f.stat().st_size, _sha_of(f)])
            except OSError:
                entries.append([f"{sub}/{f.relative_to(root)}", None, None])
    return hashlib.sha256(json.dumps(entries).encode()).hexdigest()


def _git_init_scratch(work: Path) -> None:
    subprocess.run(["git", "init", "-q", str(work)], check=True, capture_output=True, timeout=60,
                   stdin=subprocess.DEVNULL)


def _tool_calls(export: dict) -> list[tuple[str, str, bool]]:
    """(signature, tool, errored) per tool part, in transcript order."""
    calls = []
    for m in (export or {}).get("messages") or []:
        for part in m.get("parts") or []:
            if part.get("type") != "tool":
                continue
            state = part.get("state") or {}
            sig = (part.get("tool") or "?") + " " + json.dumps(state.get("input"), sort_keys=True, default=str)
            out = state.get("output")
            errored = state.get("status") == "error" or (isinstance(out, str) and out.startswith("Error"))
            calls.append((sig, part.get("tool") or "?", bool(errored)))
    return calls


def loop_metrics(export: dict) -> dict:
    """Per-row loop metric from the exported transcript.
    - repeat_identical_calls: calls identical (tool + input) to the IMMEDIATELY preceding call.
    - max_identical_run: longest run of identical consecutive calls.
    - calls_repeated_after_error: calls identical to an EARLIER call that errored (the poisoned
      tool call re-issued — the thread-1 mechanism), consecutive or not.
    """
    calls = _tool_calls(export)
    repeats = 0
    run = 1
    max_run = 1 if calls else 0
    after_err = 0
    errored_sigs: set[str] = set()
    errors = 0
    prev = None
    for sig, _tool, err in calls:
        if prev is not None and sig == prev:
            repeats += 1
            run += 1
            max_run = max(max_run, run)
        else:
            run = 1
        if sig in errored_sigs:
            after_err += 1
        if err:
            errors += 1
            errored_sigs.add(sig)
        prev = sig
    return {"tool_calls": len(calls), "error_calls": errors, "repeat_identical_calls": repeats,
            "max_identical_run": max_run, "calls_repeated_after_error": after_err}


def traffic_metrics(export: dict) -> dict:
    """D12 harness-traffic accounting per row, from the exported transcript.

    opencode reports `tokens.input` per assistant message as the INCREMENTAL prompt (verified
    2026-09-29: the sums match the router's session-cache deltas exactly), while the router re-reads
    the whole context on every turn. Both views are kept: `input_tokens_incremental` is what prefill
    actually costs with the session cache; `input_tokens_cumulative` (running-sum total) is what a
    cache-less server would prefill. The gap IS the session-cache saving. `max_context` is the final
    prompt length. Reasoning tokens are not split out (the router reports none; thinking is inside
    `output`).
    """
    turns = 0
    inc = 0
    cum = 0
    out = 0
    ctx = 0
    for m in (export or {}).get("messages") or []:
        info = m.get("info") or {}
        if info.get("role") != "assistant":
            continue
        turns += 1
        tok = info.get("tokens") or {}
        i = int(tok.get("input") or 0)
        o = int(tok.get("output") or 0)
        inc += i
        ctx += i
        cum += ctx
        out += o
    return {"turns": turns, "input_tokens_incremental": inc, "input_tokens_cumulative": cum,
            "output_tokens": out, "max_context": ctx}


def _transcript_target(model: str, lang: str, item: str, *, tag: str) -> tuple[Path, str]:
    """(absolute path, placeholder path) for an item's transcript under $STACK_WORKDIR."""
    workdir = _stack_workdir()
    rel = f"opencode_transcripts/{model}/{tag}/{lang}__{item}.json"
    return workdir / rel, f"$STACK_WORKDIR/{rel}"


def _grade_python(cwd: Path, test: Path) -> tuple[bool, str]:
    py = REPO / ".venv-bench/bin/python"
    if not py.exists():
        return False, "no .venv-bench python for grading"
    p = subprocess.run([str(py), "-m", "pytest", test.name, "-q", "--no-header"],
                       cwd=cwd, capture_output=True, text=True, timeout=300)
    return p.returncode == 0, (p.stdout or "")[-600:]



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



RESUME_IDENTITY_KEYS = ("seed_base", "overlay_schema", "scaffold_policy_sha256", "skill_policy",
                        "scratch_git_init", "env_switches", "bench_home_isolation", "opencode_bin",
                        "opencode_version", "opencode_bench_config", "opencode_bench_config_sha256",
                        "lang", "pure", "polyglot_sha", "tick_s", "hard_ceiling_s", "stall_ticks",
                        "loop_repeats", "poll_s", "cache_bin_inventory_sha256", "probe_code_sha256",
                        "opencode_exe_sha256",
                        "env_policy")


def _load_rows(out: Path) -> set:
    """`(id, sample)` of every row already in `out`. The row file must be intact: a malformed line or an
    unterminated tail refuses (naming the line) instead of being skipped or masked by a newline guard."""
    keys = set()
    try:
        text = out.read_text()
    except OSError:
        return keys
    if text and not text.endswith("\n"):
        sys.exit(f"REFUSED: {out.name} line {len(text.splitlines())} is unterminated (a truncated write); "
                 f"it is never repaired silently. Inspect or move the file.")
    for n, line in enumerate(text.splitlines(), 1):
        try:
            r = json.loads(line)
            keys.add((r["id"], int(r.get("sample", 0))))
        except (ValueError, KeyError, TypeError):
            sys.exit(f"REFUSED: {out.name} line {n} is not a valid row; a corrupt row file is never "
                     f"continued. Inspect or move the file.")
    return keys


def _check_resume(prev_doc: dict | None, now: dict, out: Path, router_now: dict | None = None, *,
                  model: str | None = None, git_now: dict | None = None) -> None:
    """C121 B2: refuse to continue `out` under a different run identity. A pre-C121 manifest (no
    seed_base / scaffold hash) or a missing one cannot be continued with seeded rows."""
    if prev_doc is None:
        sys.exit(f"REFUSED: {out.name} has rows but no manifest; unknown provenance cannot be continued. "
                 f"Use a different --out.")
    for flag in ("served_config_drift", "cache_bin_inventory_drift"):
        if prev_doc.get(flag):
            sys.exit(f"REFUSED: {out.name}'s manifest carries {flag} from a previous session; its rows are "
                     f"flagged and must not be pooled with a continuation (even if the state was since "
                     f"restored). Use a different --out.")
    prt = prev_doc.get("runtime") or {}
    for key in RESUME_IDENTITY_KEYS:
        pv = prt.get(key)
        if key not in prt:
            sys.exit(f"REFUSED: {out.name} was produced by a pre-C121 probe (manifest runtime has no "
                     f"{key}); never pooled with seeded rows. Use a different --out.")
        if pv != now[key]:
            sys.exit(f"REFUSED: cannot continue {out.name}: {key} differs (manifest {pv!r} vs this run "
                     f"{now[key]!r}). Use the original value or a different --out.")
    if model is not None and prev_doc.get("model") != model:
        sys.exit(f"REFUSED: cannot continue {out.name}: model differs (manifest {prev_doc.get('model')!r} vs "
                 f"this run {model!r}).")
    if git_now is not None:
        ps = (prev_doc.get("git") or {}).get("serving_path")
        if ps != git_now.get("serving_path"):
            sys.exit(f"REFUSED: cannot continue {out.name}: serving-code identity (git.serving_path) differs "
                     f"(manifest {ps!r} vs this run {git_now.get('serving_path')!r}).")
    if router_now and router_now.get("config_sha256"):
        pr = (prev_doc.get("router") or {}).get("config_sha256")
        if pr != router_now["config_sha256"]:
            sys.exit(f"REFUSED: cannot continue {out.name}: router.config_sha256 differs (manifest {pr!r} vs "
                     f"this run {router_now['config_sha256']!r}).")


def _stamp_manifest(mp: Path, fields: dict) -> None:
    """Merge `fields` into an existing manifest atomically; no manifest (no item ran) → no-op."""
    if not mp.exists():
        return
    doc = json.loads(mp.read_text())
    doc.update(fields)
    tmp = mp.with_suffix(mp.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2))
    os.replace(tmp, mp)


SHARED_NAMES = (
    "_polyglot_root",
    "_polyglot_sha",
    "_portable",
    "_stack_workdir",
    "_scrub_pii",
    "_login_name",
    "_scrub_error",
    "_scrub_then_tail",
    "_scratch_root",
    "_scratch_dir",
    "_prepare",
    "_solution_and_test",
    "_tick_snapshot_fn",
    "_item_seed",
    "_seed_row_fields",
    "_sha_of",
    "_cache_bin_inventory_sha256",
    "_git_init_scratch",
    "_tool_calls",
    "loop_metrics",
    "traffic_metrics",
    "_transcript_target",
    "_grade_python",
    "_docker_available",
    "_docker_grade",
    "_grade_go",
    "_grade_rust",
    "_grade_javascript",
    "_grade_java",
    "_grade_result",
    "_load_rows",
    "_check_resume",
    "_stamp_manifest",
    "_IGNORE_SOLUTION_FILES",
    "_AIDER_IMAGE",
    "_DISABLED_RE",
    "RESUME_IDENTITY_KEYS",
)


def reexport(namespace):
    """Bind shared bodies to a caller's globals, retaining legacy monkeypatch/import behavior."""
    for name in SHARED_NAMES:
        value = globals()[name]
        if isinstance(value, FunctionType):
            decorated = hasattr(value, "__wrapped__")
            if decorated:
                value = value.__wrapped__
            fn = FunctionType(
                value.__code__, namespace, name, value.__defaults__, value.__closure__
            )
            fn.__kwdefaults__ = value.__kwdefaults__
            fn.__annotations__ = value.__annotations__
            fn.__doc__ = value.__doc__
            fn.__module__ = namespace["__name__"]
            namespace[name] = contextmanager(fn) if decorated else fn
        else:
            namespace[name] = value
