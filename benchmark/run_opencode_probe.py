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
import getpass
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
from bench import provenance  # noqa: E402
from bench import progress_gate  # noqa: E402 — needs the sys.path insert above

# The scaffold is part of the serving path (the suffix lesson): an unpinned client version is an
# unrecorded output-determining knob. Bump this deliberately, never implicitly.
PINNED_OPENCODE_VERSION = "1.18.30"  # bumped 2026-09-29 (P88); 1.18.15 rows do not pool
# C123 (2026-10-06): do NOT re-pin to the brew-installed 2.0.20 (C121 proposal AC6 is REPLACED by
# this note). v2.0.20 has no `--dir`/`--pure`, routes `debug config`/`run` through a shared
# background service, and forwards NO model `options` (temperature, top_p, seed ...) into the
# request body -- measured against a mock endpoint 2026-10-06. The pinned v1 binary lives OUTSIDE
# the repo and the brew install is never used by the probe:
#   npm install --prefix "$STACK_WORKDIR/opencode-1.18.30" opencode-ai@1.18.30
OPENCODE_BIN_RELPATH = "opencode-1.18.30/node_modules/.bin/opencode"


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


def _opencode_bin() -> Path:
    """The pinned opencode binary: `$OPENCODE_PROBE_BIN`, else `$STACK_WORKDIR/<OPENCODE_BIN_RELPATH>`."""
    env = os.environ.get("OPENCODE_PROBE_BIN")
    if env:
        return Path(env)
    return _stack_workdir() / OPENCODE_BIN_RELPATH


def _require_opencode_bin() -> str:
    """C121 B1, fail-closed: the EXACT absolute pinned executable, validated here and then passed to
    every spawn (run, session list, export, M50 discovery, the overlay check, `--version`). A bare or
    relative OPENCODE_PROBE_BIN would be a PATH lookup, so it is refused; a missing or non-executable
    file is refused naming the path. Nothing ever falls back to a `opencode` on PATH."""
    b = _opencode_bin()
    if not b.is_absolute():
        sys.exit(f"REFUSED: the pinned opencode path must be absolute (got {str(b)!r}); a relative or bare "
                 f"name would resolve through PATH")
    if not b.is_file():
        sys.exit(f"REFUSED: pinned opencode binary missing at {_portable(b)}; install: npm install --prefix "
                 f"\"$STACK_WORKDIR/opencode-{PINNED_OPENCODE_VERSION}\" opencode-ai@{PINNED_OPENCODE_VERSION}, "
                 f"or set OPENCODE_PROBE_BIN")
    if not os.access(b, os.X_OK):
        sys.exit(f"REFUSED: pinned opencode binary at {_portable(b)} is not executable")
    return str(b)


def _opencode_version(binary: Path | None = None, env: dict | None = None) -> str:
    binary = Path(binary) if binary is not None else _opencode_bin()
    if not binary.is_file():
        sys.exit(f"pinned opencode binary missing at {binary.name!r} ({_portable(binary)}); install: "
                 f"npm install --prefix \"$STACK_WORKDIR/opencode-{PINNED_OPENCODE_VERSION}\" "
                 f"opencode-ai@{PINNED_OPENCODE_VERSION}, or set OPENCODE_PROBE_BIN")
    try:
        return subprocess.check_output([str(binary), "--version"], text=True, timeout=30, env=env).strip()
    except Exception as e:  # noqa: BLE001
        sys.exit(f"cannot determine opencode version ({e}); refusing to run unversioned")


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


def _run_opencode(model: str, cwd: Path, prompt: str, sol: Path, test: Path, grade,
                  before_sol: str, *, tick_s: int, hard_ceiling_s: int, poll_s: float,
                  stall_ticks: int, loop_repeats: int,
                  pure: bool, env: dict | None = None,
                  opencode_bin: str) -> tuple[int, str, float, "progress_gate.GateResult"]:
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
    cmd = [str(opencode_bin), "run", "--dir", str(cwd), "--model", f"mlx-local/{model}"]
    if pure:
        # opencode's own flag for "no external plugins". The shipped config references a plugin
        # fetched over git; loading it adds a network dependency that is not part of the model's
        # capability, and a probe that can hang on a fetch measures the network.
        cmd.append("--pure")
    cmd.append(prompt)

    log_path = cwd / ".opencode_probe_log.txt"
    with log_path.open("w") as log_f:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=log_f, stderr=subprocess.STDOUT, text=True,
                                env=env)
        snapshot_fn = _tick_snapshot_fn(cwd, sol, test, before_sol, grade, log_path,
                                        tmp_dir=(env or {}).get("TMPDIR"))
        result = progress_gate.run_progress_gated(
            proc, snapshot_fn, tick_s=tick_s, hard_ceiling_s=hard_ceiling_s, poll_s=poll_s,
            stall_ticks=stall_ticks, loop_repeats=loop_repeats)
    log = log_path.read_text(errors="replace") if log_path.exists() else ""
    return proc.returncode, log, result.elapsed_s, result


# ----------------------------------------------------------------------------- M46 (2026-09-23)
# Transcript retention + loop metric. The rows used to keep only a 500-char `log_tail`, so the
# poisoned-tool-call / loop rate (the dominant failure in the 30-day community run of the
# Qwen3.8-27B family <!-- allow-shorthand -->) could not be re-analysed from existing rows. Every
# item now runs opencode with an ISOLATED `XDG_DATA_HOME` (opencode 1.18.x honours it; verified
# 2026-09-23), so the item's store holds exactly one session; `opencode export` of that session
# is PII-scrubbed and written under `$STACK_WORKDIR/opencode_transcripts/` (outside the public
# repo — transcripts are tens to hundreds of KB per item), and the row carries `transcript_path`
# (placeholder form) + `loop_metrics`.

def _opencode_env(data_home: Path, config_home: Path | None = None, state_home: Path | None = None,
                  tmp_dir: Path | None = None, bench_home: Path | None = None) -> dict:
    """opencode's child env, built from a CLEAN base: the parent env minus EVERY `OPENCODE_*` variable
    (so a stray operator switch cannot leak in), then exactly the policy switches (`SCAFFOLD_ENV_POLICY`).
    With the bench dirs given: its own HOME (`~/.opencode`, `~/.claude`, `~/AGENTS.md`, `~/.npm` become
    unreachable), config, data, state and tmp homes; the cache home is pointed EXPLICITLY at the real
    default cache dir (operator rule: the cache stays shared; its `bin` tool content is hashed into the
    run identity because ripgrep/LSP executables shape tool feedback)."""
    real_cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    env = {k: v for k, v in os.environ.items() if not k.startswith("OPENCODE_")}
    env["XDG_DATA_HOME"] = str(data_home)
    if config_home is not None:
        # Operator ruling 2026-10-06 (C121): the bench owns its opencode config home; the personal
        # `~/.config/opencode` is never read, hashed or modified.
        env["XDG_CONFIG_HOME"] = str(config_home)
    if state_home is not None:
        env["XDG_STATE_HOME"] = str(state_home)
    if tmp_dir is not None:
        env["TMPDIR"] = str(tmp_dir)
    if bench_home is not None:
        env["HOME"] = str(bench_home)
        env["XDG_CACHE_HOME"] = real_cache
    # C103 (2026-09-27): opencode embeds every skill it discovers under ~/.claude/skills and
    # ~/.agents/skills in its system prompt; C121/R8: the policy lives in SCAFFOLD_ENV_POLICY (one source
    # for the env AND the recorded hash). The binary is NOT selected through PATH (C121 B1).
    env.update(SCAFFOLD_ENV_POLICY)
    return env


# R8 (C121, evidence 2026-10-06, opencode 1.18.30 binary strings): opencode builds
# `disableClaudeCodePrompt = OPENCODE_DISABLE_CLAUDE_CODE || OPENCODE_DISABLE_CLAUDE_CODE_PROMPT`
# and `disableClaudeCodeSkills = OPENCODE_DISABLE_CLAUDE_CODE || OPENCODE_DISABLE_CLAUDE_CODE_SKILLS`;
# `OPENCODE_DISABLE_EXTERNAL_SKILLS` (C103) is also present. The targeted `_PROMPT` switch stops
# `~/.claude/CLAUDE.md` entering the system prompt (the file EXISTS on this box as of 2026-10-06);
# external skills stay disabled by C103's switch. Both are folded into the scaffold-policy hash.
SCAFFOLD_ENV_POLICY = {"OPENCODE_DISABLE_EXTERNAL_SKILLS": "true",
                       "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT": "true"}


# ----------------------------------------------------------------------------- C121 seeded sessions
# Per-item PROJECT config `<cwd>/opencode.json` carrying ONLY the seed for the served model;
# opencode deep-merges it over the global/shipped config (verified 2026-10-06 against a mock
# endpoint on 1.18.30, in a NON-git dir: request body carried `seed` plus every shipped option).
OVERLAY_SCHEMA = "provider.mlx-local.models.<model>.options.seed + agent.title.disable + snapshot:false"


def _seed_overlay(model: str, seed: int) -> dict:
    # `agent.title.disable`: 1.18.30's session-title request would otherwise go UN-SEEDED to the small_model
    # provider (the task model, max_tokens 2048); a mock capture on 2026-10-06 showed the switch removes it.
    return {"provider": {"mlx-local": {"models": {model: {"options": {"seed": int(seed)}}}}},
            "agent": {"title": {"disable": True}},
            # `snapshot: false` (valid 1.18.30 key): `git init` would otherwise turn on snapshot tracking
            "snapshot": False}


def _write_seed_overlay(cwd: Path, model: str, seed: int) -> str:
    """Write the overlay into the item's scratch dir; return its sha256."""
    import hashlib
    raw = (json.dumps(_seed_overlay(model, seed), indent=2, sort_keys=True) + "\n").encode()
    (Path(cwd) / "opencode.json").write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _item_seed(item_id: str, seed_base: int) -> int:
    from bench import rowschema
    return rowschema.sample_seed(item_id, 0, base=seed_base)


def _seed_row_fields(item_id: str, seed_base: int, overlay_sha256: str) -> dict:
    return {"sampler_seed": _item_seed(item_id, seed_base), "seed_base": seed_base,
            "overlay_sha256": overlay_sha256}


SEED_TEST_FILE = REPO / "benchmark" / "bench" / "tests" / "test_opencode_probe_seeding.py"


def _sha_of(path) -> str | None:
    import hashlib
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _seed_marker_path(binary: Path | None = None) -> Path:
    override = os.environ.get("OPENCODE_PROBE_RECEIPT")      # tests / operator: receipt destination
    if override:
        return Path(override)
    b = Path(binary) if binary is not None else _opencode_bin()
    return (b.parents[2] if b.parent.name == ".bin" else b.parent) / "seed_propagation_verified"


def _receipt_now(binary: Path) -> dict:
    return {"version": PINNED_OPENCODE_VERSION, "exe_sha256": _sha_of(binary),
            "bench_config_sha256": _sha_of(BENCH_OPENCODE_CONFIG), "test_sha256": _sha_of(SEED_TEST_FILE),
            }


def _record_seed_propagation_verified(binary: Path | None = None) -> None:
    """Called by the integration test (only when OPENCODE_PROBE_RECORD_VERIFIED=1) after it proved
    seed + deployed fields reach the endpoint: stamps a receipt bound to the sha256 of the executable,
    the bench carrier and the integration test file (C121 B5)."""
    b = Path(binary) if binary is not None else _opencode_bin()
    m = _seed_marker_path(b)
    if m.parent.is_dir():
        m.write_text(json.dumps(_receipt_now(b), indent=2))


ENV_POLICY = {
    "OPENCODE_*": "every parent OPENCODE_* variable dropped, then exactly SCAFFOLD_ENV_POLICY applied",
    "HOME": "$STACK_WORKDIR/opencode-probe/home (bench-owned, persistent; ~/.opencode, ~/.claude, ~/AGENTS.md, ~/.npm unreachable)",
    "XDG_CONFIG_HOME": "$STACK_WORKDIR/opencode-probe/config-<run-id> (bench carrier copy; personal config never read)",
    "XDG_DATA_HOME": "per-item scratch dir (discovery: $STACK_WORKDIR/scratch/m50-discovery-xdg-data-<run-id>)",
    "XDG_STATE_HOME": "<bench home>/.local/state",
    "TMPDIR": "$STACK_WORKDIR/opencode-probe/tmp-<run-id>",
    "XDG_CACHE_HOME": "the real default cache dir (shared; its opencode/bin tool content is hashed into the run identity; the one permitted initialisation write outside the workdir)",
}
BENCH_HOME_ISOLATION = True


BENCH_HOME_FORBIDDEN = (".opencode", "AGENTS.md", "CLAUDE.md", ".claude")


def _assert_bench_home_clean(bench_home: Path) -> None:
    """The bench HOME is LOAD-BEARING and persistent (and writable by the model): with `--pure`,
    1.18.30 still merges `$HOME/.opencode/opencode.json` and `$HOME/.opencode/agent/*.md` (a sentinel
    `agent.build.prompt` replaced the system prompt in the cold review), and it reads HOME-level
    `AGENTS.md` / `CLAUDE.md` / `.claude`. Refuse if any exists (checked at run start and before each item)."""
    for name in BENCH_HOME_FORBIDDEN:
        if (Path(bench_home) / name).exists():
            sys.exit(f"REFUSED: the bench HOME holds {name!r} ({_portable(Path(bench_home) / name)}); opencode "
                     f"would load it as instructions/config. Remove it and rerun.")


def _make_run_dirs(workdir: Path, run_id: str) -> tuple:
    """(config home, state home, tmp dir, bench HOME) under `<workdir>/opencode-probe/`; the bench HOME
    and its state dir are persistent across runs, the config home and tmp dir are per run."""
    cfg_dir = Path(workdir) / "opencode-probe" / f"config-{run_id}"
    tmp_dir = Path(workdir) / "opencode-probe" / f"tmp-{run_id}"
    bench_home = Path(workdir) / "opencode-probe" / "home"
    state_home = bench_home / ".local" / "state"
    try:
        cfg_home = _make_bench_config_home(workdir, run_id)
        state_home.mkdir(parents=True, exist_ok=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)
    except BaseException:
        _cleanup_run_dirs([cfg_dir, tmp_dir])       # no partial initialisation survives a failure
        raise
    return cfg_home, state_home, tmp_dir, bench_home


def _cleanup_run_dirs(dirs) -> None:
    for d in dirs:
        shutil.rmtree(d, ignore_errors=True)


def _probe_code_sha256() -> str:
    """sha256 over this probe's own source and the progress gate's: the harness code is part of the identity."""
    import hashlib
    h = hashlib.sha256()
    for f in (Path(__file__), Path(progress_gate.__file__)):
        h.update(f.name.encode()); h.update(f.read_bytes())
    return h.hexdigest()


def _real_cache_home() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))


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


def _run_identity(*, lang, pure, poly_sha, tick_s, hard_ceiling_s, stall_ticks, loop_repeats, seed_base,
                  oc_bin, oc_version, poll_s, cache_sha) -> dict:
    """The output-determining identity of a run (recorded in the manifest runtime, compared on resume).
    The instruction-file inventory is NOT part of it (observation only; git init blocks those files)."""
    exe = _sha_of(oc_bin)
    return {**_scaffold_runtime(opencode_version=oc_version, exe_sha=exe), **_seed_runtime(seed_base),
            "opencode_version": oc_version,
            "lang": lang, "pure": pure, "polyglot_sha": poly_sha, "tick_s": tick_s,
            "hard_ceiling_s": hard_ceiling_s, "stall_ticks": stall_ticks, "loop_repeats": loop_repeats,
            "poll_s": poll_s, "cache_bin_inventory_sha256": cache_sha,
            "probe_code_sha256": _probe_code_sha256(),
            "opencode_exe_sha256": exe, "env_policy": ENV_POLICY}


def _make_bench_config_home(workdir: Path, run_id: str, source: Path | None = None) -> Path:
    """Operator ruling 2026-10-06 (C121): `<workdir>/opencode-probe/config-<run-id>/opencode/opencode.json`
    is a VERBATIM copy of the shipped opencode config and the only file there (no global AGENTS.md).
    Returns the XDG_CONFIG_HOME root. Refuses if the copy's sha differs from the source's.
    (`source` exists for the integration test, which must point the baseURL at a mock.)"""
    src = Path(source) if source is not None else BENCH_OPENCODE_CONFIG
    home = Path(workdir) / "opencode-probe" / f"config-{run_id}"
    d = home / "opencode"
    d.mkdir(parents=True, exist_ok=True)
    raw = src.read_bytes()
    (d / "opencode.json").write_bytes(raw)
    if _sha_of(d / "opencode.json") != _sha_of(src):
        sys.exit(f"REFUSED: the bench opencode config copy differs from {src.name}")
    return home


def _instruction_sources(start: Path) -> dict:
    """`effective_instruction_sources`: {portable path: sha256} of every AGENTS.md / CLAUDE.md /
    CONTEXT.md in the ancestor chain of `start` plus `~/.claude/CLAUDE.md`. The bench config home
    holds no AGENTS.md and the personal opencode config dir is not read, so these are the sources left."""
    return _ancestor_instruction_files(start)


def _instruction_sources_sha256(src: dict) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(src, sort_keys=True).encode()).hexdigest()


def _seed_runtime(seed_base: int) -> dict:
    b = _opencode_bin()
    try:
        rec = json.loads(_seed_marker_path(b).read_text())
        verified = (isinstance(rec, dict) and None not in rec.values()
                    and rec == _receipt_now(b))
    except (OSError, ValueError):
        verified = False
    return {"seed_base": seed_base, "overlay_schema": OVERLAY_SCHEMA,
            "seed_propagation": "verified-by-test" if verified else "unverified",
            "opencode_bin": _portable(b)}


def _assert_overlay_resolved(cwd: Path, env: dict, model: str, seed: int, expected_base: str, *,
                             opencode_bin: str, pure: bool = True) -> None:
    """AC4: what opencode ITSELF resolves for this item must keep the verified baseURL and carry
    the seed in the served model's options. Refuses (M50 shape) otherwise; a nonzero exit, a
    timeout or malformed JSON is a refusal, never a parse of whatever stdout held (C121 B6)."""
    try:
        r = subprocess.run([str(opencode_bin), "debug", "config", *(["--pure"] if pure else [])],
                           cwd=str(cwd), env=env, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired as e:
        raise provenance.ServedConfigError(f"M50 tripwire: `opencode debug config` timeout after "
                                           f"{e.timeout}s while resolving the seeded overlay.")
    except Exception as e:  # noqa: BLE001
        raise provenance.ServedConfigError(f"M50 tripwire: cannot run `opencode debug config`: "
                                           f"{type(e).__name__}: {e}")
    if r.returncode != 0:
        raise provenance.ServedConfigError(f"M50 tripwire: `opencode debug config` exit {r.returncode} "
                                           f"while resolving the seeded overlay; stderr {provenance.scrub_tail(_scrub_pii(r.stderr or ''), 200)!r}")
    out = r.stdout or ""
    try:
        data = json.loads(out[out.index("{"):])
    except Exception as e:  # noqa: BLE001
        raise provenance.ServedConfigError(f"M50 tripwire: `opencode debug config` gave malformed JSON: "
                                           f"{type(e).__name__}: {e}")
    try:
        prov = data["provider"]["mlx-local"]
        base = prov["options"]["baseURL"]
        opts = prov["models"][model]["options"]
    except Exception as e:  # noqa: BLE001
        raise provenance.ServedConfigError(f"M50 tripwire: resolved config lacks mlx-local/{model} "
                                           f"options: {type(e).__name__}: {e}")
    if base != expected_base:
        raise provenance.ServedConfigError(f"M50 tripwire: the seed overlay changed opencode's resolved "
                                           f"baseURL ({expected_base!r} -> {base!r}).")
    if opts.get("seed") != seed:
        raise provenance.ServedConfigError(f"M50 tripwire: opencode's resolved options for {model!r} do not "
                                           f"carry the overlay seed {seed} (got {opts.get('seed')!r}).")
    # The bench's OWN config home holds the bench carrier verbatim, so the resolved options minus
    # `seed` and the `limit` must EQUAL the carrier's block for this model; a difference is an opencode
    # merge bug (or a model missing from the carrier) and refuses (C121 B2/C7, operator ruling 2026-10-06).
    try:
        blk = json.loads(BENCH_OPENCODE_CONFIG.read_text())["provider"]["mlx-local"]["models"][model]
        expected = blk["options"]
    except Exception as e:  # noqa: BLE001
        raise provenance.ServedConfigError(f"M50 tripwire: the bench opencode config has no deployed "
                                           f"options for {model!r}: {type(e).__name__}: {e}")
    if data.get("snapshot") is not False:
        raise provenance.ServedConfigError("M50 tripwire: opencode's resolved config does not disable "
                                           "snapshot tracking (snapshot:false).")
    if (data.get("agent") or {}).get("title", {}).get("disable") is not True:
        raise provenance.ServedConfigError("M50 tripwire: opencode's resolved config does not disable title "
                                           "generation (agent.title.disable); the un-seeded title request "
                                           "would reach the task provider.")
    if data.get("instructions"):
        raise provenance.ServedConfigError(f"M50 tripwire: opencode's resolved config has a non-empty "
                                           f"`instructions` key {data['instructions']!r} (extra instruction files).")
    got = {k: v for k, v in opts.items() if k != "seed"}
    bad = [f"{k} (resolved {got.get(k, '<missing>')!r}, deployed {expected.get(k, '<absent>')!r})"
           for k in sorted(set(expected) | set(got)) if got.get(k, object()) != expected.get(k, object())]
    if bad:
        raise provenance.ServedConfigError(f"M50 tripwire: opencode's resolved options for {model!r} differ "
                                           f"from the deployed sampling fields: {'; '.join(bad)}.")
    if prov["models"][model].get("limit") != blk.get("limit") or not blk.get("limit"):
        raise provenance.ServedConfigError(f"M50 tripwire: opencode's resolved `limit` for {model!r} "
                                           f"({prov['models'][model].get('limit')!r}) != the bench carrier's "
                                           f"({blk.get('limit')!r}).")


SHIPPED_OPENCODE_CONFIG = REPO / "opencode_config" / "opencode.json"     # the CLIENT config (7 models)
# The bench carrier (superset: includes `role: candidate` models the client config excludes; see
# docs/box-notes.md "A bench harness that mounts a CLIENT config silently excludes ..."). The bench-owned
# opencode config home is a verbatim copy of THIS file.
BENCH_OPENCODE_CONFIG = REPO / "benchmark" / "opencode_bench.json"

# C121 B3: opencode 1.18.30 searches UPWARD from a non-git project dir for AGENTS.md (no switch
# disables that; verified by the cold review's mock capture), so the operator's `~/AGENTS.md` would
# enter every system prompt. `git init` in each item scratch dir makes it a repo root and stops the
# search while the seed overlay still merges. Part of the scaffold-policy hash.
SCRATCH_GIT_INIT = True
# Side effect of `git init` (C121 review C6): opencode treats the dir as a git repo ("git repo: yes" in its
# prompt) and turns on snapshot tracking in its data dir (which M46 isolates per item). Docker grading of
# go/rust/java/javascript with a `.git` dir present is UNVERIFIED: check one known-positive grade per
# language before relying on those legs.


def _git_init_scratch(work: Path) -> None:
    subprocess.run(["git", "init", "-q", str(work)], check=True, capture_output=True, timeout=60,
                   stdin=subprocess.DEVNULL)


def _ancestor_instruction_files(start: Path) -> dict:
    """{portable path: sha256} of every AGENTS.md / CLAUDE.md / CONTEXT.md from `start` up to `/`,
    plus `~/.claude/CLAUDE.md` -- the instruction files opencode could pick up, so exposure is observable."""
    import hashlib

    def digest(p: Path) -> str | None:
        try:
            if p.is_file():
                return hashlib.sha256(p.read_bytes()).hexdigest()
            if p.is_dir():
                h = hashlib.sha256()
                for f in sorted(x for x in p.rglob("*") if x.is_file()):
                    h.update(str(f.relative_to(p)).encode()); h.update(f.read_bytes())
                return h.hexdigest()
        except OSError:
            return None
        return None
    found = {}
    start = Path(os.path.realpath(start))
    cands = []
    for d in [start, *start.parents]:
        cands += [d / "AGENTS.md", d / "CLAUDE.md", d / "CONTEXT.md"]
    cands.append(Path.home() / ".claude" / "CLAUDE.md")
    for c in cands:
        h = digest(c)
        if h:
            found[_portable(c)] = h
    return found


def _scaffold_runtime(*, opencode_version: str | None = None, exe_sha: str | None = None) -> dict:
    """Scaffold identity fields for the manifest (C103). `scaffold_policy_sha256` hashes ONLY effective
    inputs: the bench carrier sha, the overlay schema, the applied env switches, `scratch_git_init`, the
    bench-HOME isolation flag, the opencode version and executable sha, and the rule that the resolved
    `instructions` key is empty. Observations (the client config sha, `claude_md_present`, the
    instruction-file inventory) are recorded elsewhere and never hashed."""
    import hashlib
    policy = ",".join(f"{k}={v}" for k, v in sorted(SCAFFOLD_ENV_POLICY.items()))
    bench_sha = _sha_of(BENCH_OPENCODE_CONFIG)
    full = "|".join([f"bench_config={bench_sha}", f"overlay={OVERLAY_SCHEMA}", f"switches={policy}",
                     f"scratch_git_init={str(SCRATCH_GIT_INIT).lower()}",
                     f"bench_home_isolation={str(BENCH_HOME_ISOLATION).lower()}",
                     f"opencode_version={opencode_version}", f"exe={exe_sha}", "instructions_key=empty"])
    return {"skill_policy": policy, "env_switches": dict(SCAFFOLD_ENV_POLICY),
            "scratch_git_init": SCRATCH_GIT_INIT, "bench_home_isolation": BENCH_HOME_ISOLATION,
            "scaffold_policy_sha256": hashlib.sha256(full.encode()).hexdigest(),
            "claude_md_present": (Path.home() / ".claude" / "CLAUDE.md").exists(),
            "opencode_config": "opencode_config/opencode.json",
            "opencode_config_sha256": _sha_of(SHIPPED_OPENCODE_CONFIG),
            "opencode_bench_config": "benchmark/opencode_bench.json",
            "opencode_bench_config_sha256": bench_sha}


def _export_latest_session(env: dict, *, cwd: Path, opencode_bin: str) -> dict | None:
    """`opencode session list` → newest session id → `opencode export <id>` → dict. Degrades to
    None (never raises): a missing transcript is a note on the row, not a dead batch."""
    try:
        listing = subprocess.check_output([str(opencode_bin), "session", "list"], env=env, cwd=cwd,
                                          text=True, stderr=subprocess.DEVNULL, timeout=60)
        ids = re.findall(r"\bses_[A-Za-z0-9]+", listing)
        if not ids:
            return None
        raw = subprocess.check_output([str(opencode_bin), "export", ids[0]], env=env, cwd=cwd,
                                      text=True, stderr=subprocess.DEVNULL, timeout=120)
        return json.loads(raw)
    except Exception:  # noqa: BLE001 — graceful-degrade per bench tooling rule
        return None


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
    repeats = 0; run = 1; max_run = 1 if calls else 0
    after_err = 0; errored_sigs: set[str] = set(); errors = 0
    prev = None
    for sig, _tool, err in calls:
        if prev is not None and sig == prev:
            repeats += 1; run += 1; max_run = max(max_run, run)
        else:
            run = 1
        if sig in errored_sigs:
            after_err += 1
        if err:
            errors += 1; errored_sigs.add(sig)
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
    turns = 0; inc = 0; cum = 0; out = 0; ctx = 0
    for m in (export or {}).get("messages") or []:
        info = m.get("info") or {}
        if info.get("role") != "assistant":
            continue
        turns += 1
        tok = info.get("tokens") or {}
        i = int(tok.get("input") or 0); o = int(tok.get("output") or 0)
        inc += i; ctx += i; cum += ctx; out += o
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
    ctx = {"dirs": [], "ran": False}
    try:
        return _main(ctx)
    finally:
        if not ctx["ran"]:      # a refusal before any item ran leaves no per-run dirs behind
            _cleanup_run_dirs(ctx["dirs"])


def _main(ctx: dict) -> int:
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
    ap.add_argument("--seed-base", type=int, required=True,
                    help="C121: per-session sampler seed base (no default). Item seed = "
                         "rowschema.sample_seed(item, 0, base=); two sessions use distinct bases, a "
                         "reload control reuses one.")
    ap.add_argument("--allow-version-drift", action="store_true",
                    help=f"run even if opencode != {PINNED_OPENCODE_VERSION} (drift is recorded)")
    a = ap.parse_args()
    # `--timeout` is a deprecated alias kept for old invocations; it now maps onto the
    # PROGRESS-GATE's hard ceiling (a backstop), never a flat kill.
    hard_ceiling_s = a.timeout if a.timeout is not None else a.hard_ceiling_s

    SUPPORTED_LANGS = {"python", "go", "rust", "java", "javascript"}
    if a.lang not in SUPPORTED_LANGS:
        sys.exit(f"unsupported --lang {a.lang!r}; supported: {sorted(SUPPORTED_LANGS)}")

    # M53: STACK_WORKDIR resolves HERE (env / config.sh, a read the M50 check needs), before the
    # guard and before any request. (2026-09-29: a missing STACK_WORKDIR surfaced only in the
    # transcript writer, after item 1 ran.)
    workdir = _stack_workdir()
    os.environ.setdefault("STACK_WORKDIR", str(workdir))   # pinned-binary lookup + portable paths

    # M50: refuse before anything is read, written or requested unless :port serves this registry.
    # The ONLY I/O allowed before this check is what the check itself needs: resolving the
    # configuration and ONE `opencode debug config` discovery call. Docker, `opencode --version`,
    # the polyglot checkout and every output path come AFTER it.
    # Discovery runs with cwd = the EXISTING $STACK_WORKDIR so opencode's upward config discovery
    # sees the same ancestry as the item directories (`<STACK_WORKDIR>/scratch/...`); we create no
    # directory. The one remaining pre-check side effect is opencode's OWN data-home write during
    # `debug config`: its XDG_DATA_HOME points under the workdir scratch (never the real one) and
    # opencode creates that directory itself. That write is the ONE operator-approved exception to
    # "no write before the check" (C114, 2026-10-05; AGENTS.md M50); see
    # test_..._passes_a_workdir_data_home_to_discovery.
    if not workdir.is_dir():
        sys.exit(f"REFUSED: M50 STACK_WORKDIR {str(workdir)!r} does not exist; discovery needs an "
                 f"existing directory (nothing is created before the router check).")
    oc_bin = _require_opencode_bin()    # C121 B1: stat only; the exact executable is used for EVERY spawn
    # Operator ruling 2026-10-06 + review E1: the bench owns the opencode config, state and tmp homes,
    # created right after the workdir check; EVERY spawn (including the pre-M50 `--version`) runs under
    # this env, so opencode's initialisation writes land inside the workdir (the cache home stays default:
    # the shared cache, whose `bin` content is hashed into the identity; see ENV_POLICY). The personal
    # ~/.config/opencode is never read.
    run_id = f"{time.strftime('%Y%m%dT%H%M%S')}-{os.getpid()}"
    disc_data = workdir / "scratch" / f"m50-discovery-xdg-data-{run_id}"
    ctx["dirs"] = [workdir / "opencode-probe" / f"config-{run_id}", workdir / "opencode-probe" / f"tmp-{run_id}",
                   disc_data]                          # registered BEFORE creation; the bench HOME is persistent
    cfg_home, state_home, tmp_dir, bench_home = _make_run_dirs(workdir, run_id)
    _assert_bench_home_clean(bench_home)             # before the first spawn under it
    boot_env = _opencode_env(disc_data, cfg_home, state_home, tmp_dir, bench_home)
    # C121 C1 / C125: the pinned binary's read-only `--version` runs BEFORE discovery, so an override
    # pointing at another version (brew v2 ...) never executes `debug config`.
    oc_version = _opencode_version(oc_bin, boot_env)
    if oc_version != PINNED_OPENCODE_VERSION and not a.allow_version_drift:
        sys.exit(f"REFUSED: opencode {oc_version} != pinned {PINNED_OPENCODE_VERSION}; a scaffold version "
                 f"is output-determining. Bump PINNED_OPENCODE_VERSION deliberately or pass "
                 f"--allow-version-drift to record the drift.")
    try:  # opencode sends to what ITS resolved config says (never MLX_SERVE_BASE): verify THAT.
        oc_base = provenance.opencode_router_base(workdir, boot_env, opencode_bin=oc_bin, pure=True)
        router = provenance.assert_served_config(oc_base)
    except (RuntimeError, OSError, KeyError, ValueError) as e:
        sys.exit(f"REFUSED: M50 {type(e).__name__}: {e}")
    print(f"M50 served-config OK: opencode -> {oc_base}: router pid {router['pid']} serves "
          f"{router['config']}", flush=True)

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

    # C121 B5/B3: the instruction-file inventory (observation only), after the M50 check.
    scratch_start = Path(_scratch_root() or (workdir / "scratch"))
    ancestors = _ancestor_instruction_files(scratch_start)
    instr_sources = _instruction_sources(scratch_start)
    instr_sha = _instruction_sources_sha256(instr_sources)
    if instr_sources:
        print(f"!! instruction files opencode may load (recorded in the manifest): {sorted(instr_sources)}",
              flush=True)

    polyglot = _polyglot_root()
    poly_sha = _polyglot_sha(polyglot)
    root = polyglot / a.lang / "exercises/practice"
    out = Path(a.out) if a.out else REPO / "benchmark/results" / a.model / "opencode.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    # Manifest beside the rows, same machinery as the two-phase harness, so compare/clean-stale
    # see the sampling + code shas this run inherited — plus the scaffold identity in `runtime`.
    # M50: (a) an existing manifest's router attribution is PRESERVED — a different served config
    # refuses the continuation, a different pid goes to `router_history`; (b) it is written only
    # right before the first item actually RUNS, so a per-item destination refusal records nothing.
    mp = out.with_suffix(".manifest.json")
    history = []
    prev_doc = None
    overlay_map: dict = {}
    if mp.exists():
        try:
            prev_doc = json.loads(mp.read_text())
        except Exception as e:  # noqa: BLE001
            sys.exit(f"REFUSED: M50 unreadable existing manifest {mp}: {e}")
        prev = prev_doc.get("router"); history = list(prev_doc.get("router_history") or [])
        if isinstance(prev, dict) and prev.get("config") and prev.get("config") != router["config"]:
            sys.exit(f"REFUSED: M50 {out} was produced under served config {prev['config']!r}; this "
                     f"router serves {router['config']!r}. Use a different --out.")
        if isinstance(prev, dict) and prev.get("pid") is not None and prev.get("pid") != router["pid"]:
            history.append(prev)
        overlay_map = dict(prev_doc.get("overlay_sha256_by_item") or {})
    # C121 B2: continuation. Rows already on disk fix the identity of this run: same seed base, same
    # scaffold policy, same binary and version -- else refuse; recorded (id, sample) keys are skipped.
    done = _load_rows(out)
    continuation: list = []
    identity = _run_identity(lang=a.lang, pure=True, poly_sha=poly_sha, tick_s=a.tick_s,
                             hard_ceiling_s=hard_ceiling_s, stall_ticks=a.stall_ticks,
                             loop_repeats=a.loop_repeats, seed_base=a.seed_base, oc_bin=oc_bin,
                             oc_version=oc_version, poll_s=a.poll_s,
                             cache_sha=_cache_bin_inventory_sha256(Path(boot_env["XDG_CACHE_HOME"])))
    if done or prev_doc is not None:        # the identity check runs whenever a manifest exists
        git_now = provenance._git_shas()
        _check_resume(prev_doc, identity, out, router, model=a.model, git_now=git_now)
        continuation = list(prev_doc.get("continuation_history") or []) + [
            {"timestamp": prev_doc.get("timestamp"), "model": prev_doc.get("model"),
             "git": prev_doc.get("git"), "router": prev_doc.get("router"),
             "router_exit": prev_doc.get("router_exit"), "runtime": prev_doc.get("runtime")}]
    manifest_written = False

    def _write_manifest():
        nonlocal manifest_written
        if manifest_written:
            return
        from bench import provenance
        man = provenance.gather(a.model, profile="deployed",
                                runtime={"client": "opencode", "edit_format": "tools",
                                         **identity,
                                         "opencode_config_home": _portable(cfg_home),
                                         "opencode_bench_home": _portable(bench_home),
                                         "bench_home_clean": True,
                                         "instruction_sources_sha256": instr_sha,
                                         "opencode_config_copy_sha256": _sha_of(cfg_home / "opencode" / "opencode.json"),
                                         "ancestor_instruction_files": ancestors,
                                         "effective_instruction_sources": instr_sources,
                                         "instruction_files_blocked_by_git_init": SCRATCH_GIT_INIT,
                                         "title_generation": "disabled (overlay agent.title.disable; 1.18.30, "
                                                             "mock-verified 2026-10-06)",
                                         "title_request_provider": None},
                                router=router)
        if history:
            man["router_history"] = history
        if overlay_map:
            man["overlay_sha256_by_item"] = dict(overlay_map)
        if continuation:        # C121 C2: the original attribution survives a continuation
            man["continuation_history"] = continuation
        tmp = mp.with_suffix(mp.suffix + ".tmp")
        tmp.write_text(json.dumps(man, indent=2))
        os.replace(tmp, mp)
        manifest_written = True
        ctx["ran"] = True

    for name in dict.fromkeys(s.strip() for s in a.items.split(",") if s.strip()):
        if (f"{a.lang}/{name}", 0) in done:
            print(f"[resume] {a.lang}/{name} already recorded in {out.name}; skipped", flush=True)
            continue
        _assert_bench_home_clean(bench_home)
        if _sha_of(cfg_home / "opencode" / "opencode.json") != _sha_of(BENCH_OPENCODE_CONFIG):
            sys.exit(f"REFUSED: the per-run config copy changed since it was seeded ({_portable(cfg_home)}); "
                     f"it must stay a verbatim copy of {BENCH_OPENCODE_CONFIG.name}.")
        src = root / name
        if not src.is_dir():
            print(f"!! {name}: no such exercise at {src}", flush=True)
            continue
        with _scratch_dir(name) as tmp:
            work = Path(tmp) / name
            _prepare(src, work)
            if SCRATCH_GIT_INIT:
                _git_init_scratch(work)         # C121 B3: repo root stops opencode's upward AGENTS.md search
            oc_env = _opencode_env(Path(tmp) / "xdg-data", cfg_home, state_home, tmp_dir, bench_home)   # M46 + bench homes
            # M50: the destination opencode resolves from INSIDE this item's project must be the
            # router verified at entry (a project-level config in the exercise would win otherwise).
            item_id = f"{a.lang}/{name}"
            item_seed = _item_seed(item_id, a.seed_base)
            overlay_sha = _write_seed_overlay(work, a.model, item_seed)   # C121: per-item seed overlay
            # Two `opencode debug config` spawns per item (destination + overlay), ~0.7 s total
            # (cold review E4); accepted. A refusal at item k leaves the C106 drift stamp on the
            # manifest of items 1..k-1.
            def _drift_stamp(e):
                if not manifest_written:        # a refusal before THIS session wrote anything must not
                    return                      # mark a previous (clean) session's rows as drifted
                _stamp_manifest(mp, {"served_config_drift": {"entry_sha256": router.get("config_sha256"),
                                                             "exit_sha256": _exit_sha(oc_base),
                                                             "error": _scrub_error(e),
                                                             "item": item_id}})
            try:
                provenance.assert_opencode_destination(work, oc_env, router["pid"], opencode_bin=oc_bin,
                                                       pure=True)
            except provenance.ServedConfigError as e:
                _drift_stamp(e)
                raise
            try:
                _assert_overlay_resolved(work, oc_env, a.model, item_seed, oc_base, opencode_bin=oc_bin,
                                         pure=True)
            except provenance.ServedConfigError as e:
                _drift_stamp(e)
                sys.exit(f"REFUSED: {e}")
            try:
                _write_manifest()           # first RUNNING item: attribution on disk before traffic
            except Exception as e:  # noqa: BLE001
                sys.exit(f"REFUSED: M50 cannot write the manifest {mp}: {e}")
            overlay_map[item_id] = overlay_sha      # C121 B9: per-item overlay hash on the manifest too
            _stamp_manifest(mp, {"overlay_sha256_by_item": overlay_map})
            sol, test = _solution_and_test(work, src, a.lang)
            before = sol.read_text(errors="replace")
            test_before = test.read_text(errors="replace")
            prompt = (
                f"Implement the solution in {sol.name} so that the tests in {test.name} pass. "
                f"The specification is in .docs/instructions.md — read it first. "
                f"Do NOT modify {test.name}. Do not create new files unless required by the spec."
            )
            cache_entry = identity["cache_bin_inventory_sha256"]
            rc, log, dur, gate_result = _run_opencode(
                a.model, work, prompt, sol, test, grade, before,
                tick_s=a.tick_s, hard_ceiling_s=hard_ceiling_s, poll_s=a.poll_s,
                stall_ticks=a.stall_ticks, loop_repeats=a.loop_repeats, pure=True,
                env=oc_env, opencode_bin=oc_bin)
            # C121 B7: the overlay sits in the model's edit surface. Re-hash, flag a rewrite, and
            # restore the original bytes BEFORE the session export so it never runs under a rewritten file.
            try:
                overlay_after = _sha_of(work / "opencode.json")
            except Exception:  # noqa: BLE001
                overlay_after = None
            overlay_rewritten = overlay_after != overlay_sha
            if overlay_rewritten:
                _write_seed_overlay(work, a.model, item_seed)
            # E3: tools (ripgrep/LSP) can be installed lazily into the shared cache during an item. Recompute
            # after every item; a difference from the entry inventory flags this row (kept, not refused: a
            # first-use install is legitimate) and stamps the manifest once.
            cache_obs = _cache_bin_inventory_sha256(Path(boot_env["XDG_CACHE_HOME"]))
            cache_drift = cache_obs != cache_entry
            if cache_drift:
                _stamp_manifest(mp, {"cache_bin_inventory_drift": (
                    json.loads(mp.read_text()).get("cache_bin_inventory_drift")
                    if mp.exists() and "cache_bin_inventory_drift" in json.loads(mp.read_text())
                    else {"entry": cache_entry, "observed": cache_obs, "item": item_id})})
            export = _export_latest_session(oc_env, cwd=work, opencode_bin=oc_bin)
            transcript_rel = None
            if export is not None:
                t_abs, transcript_rel = _transcript_target(a.model, a.lang, name, tag=out.stem)
                t_abs.parent.mkdir(parents=True, exist_ok=True)
                t_abs.write_text(_scrub_pii(json.dumps(export, indent=1)))
            metrics = loop_metrics(export or {})
            traffic = traffic_metrics(export or {})      # D12
            after = sol.read_text(errors="replace")
            changed = after != before
            # A rewritten test file invalidates the grade: the model can make any suite pass by
            # replacing it. Observed for real on the first run, which overwrote the test file
            # despite the prompt forbidding it — so this is a measured hazard, not a precaution.
            passed, tail, test_modified = _grade_result(work, test, test_before, changed, grade)
            excluded_reason = None
            if overlay_rewritten:       # C121 C10: the seed for later turns is unproven -> never graded
                passed, excluded_reason = None, "overlay_rewritten_by_model: the sampler seed for later turns is unproven"
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
                "grade_tail": _scrub_then_tail(tail, 300), "log_tail": _scrub_then_tail(log, 500),
                # M46: full transcript outside the repo + the loop metric on the row.
                "transcript_path": transcript_rel, "loop_metrics": metrics,
                # D12: harness traffic (turns, incremental + cumulative input, output, max context).
                "traffic": traffic,
                **_seed_row_fields(item_id, a.seed_base, overlay_sha),
                "overlay_sha256_after": overlay_after, "overlay_rewritten_by_model": overlay_rewritten,
                "cache_drift": cache_drift,
                **({"acc": None, "grade_excluded_reason": excluded_reason} if excluded_reason else {}),
            }
            with out.open("a") as f:
                f.write(json.dumps(row) + "\n")
            done.add((item_id, 0))
            print(f"[{time.strftime('%H:%M:%S')}] {name:16s} changed={changed} passed={passed} "
                  f"rc={rc} {dur:.0f}s turns={traffic['turns']} in_inc={traffic['input_tokens_incremental']} "
                  f"in_cum={traffic['input_tokens_cumulative']} out={traffic['output_tokens']} "
                  f"ctx={traffic['max_context']}", flush=True)
    # C106: refuse to declare the run complete if the served runtime changed since entry; the
    # drift is stamped into the manifest so the rows are never mistaken for clean. When nothing ran
    # (an all-skipped resume) the manifest describes only earlier sessions and is left untouched.
    try:
        exit_blk = provenance.assert_served_config_unchanged(router, oc_base)
    except provenance.ServedConfigError as e:
        if manifest_written:
            _stamp_manifest(mp, {"served_config_drift": {"entry_sha256": router.get("config_sha256"),
                                                         "exit_sha256": _exit_sha(oc_base),
                                                         "error": _scrub_error(e)}})
        sys.exit(f"REFUSED: {e}")
    if manifest_written:
        _stamp_manifest(mp, {"router_exit": exit_blk})
    print(f"rows -> {out}", flush=True)
    return 0


# The full output-determining identity (everything `_run_identity` records except per-run observations:
# seed_propagation; the model and the serving-code identity are checked separately from the manifest top).
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


def _recorded_keys(out: Path) -> set:
    """`(id, sample)` of every row already in `out` (malformed lines are ignored)."""
    keys = set()
    try:
        for line in out.read_text().splitlines():
            try:
                r = json.loads(line)
                keys.add((r["id"], int(r.get("sample", 0))))
            except (ValueError, KeyError, TypeError):
                continue
    except OSError:
        pass
    return keys


def _check_resume(prev_doc: dict | None, now: dict, out: Path, router_now: dict | None = None, *,
                  model: str | None = None, git_now: dict | None = None) -> None:
    """C121 B2: refuse to continue `out` under a different run identity. A pre-C121 manifest (no
    seed_base / scaffold hash) or a missing one cannot be continued with seeded rows."""
    if prev_doc is None:
        sys.exit(f"REFUSED: {out.name} has rows but no manifest; unknown provenance cannot be continued. "
                 f"Use a different --out.")
    if prev_doc.get("served_config_drift"):
        sys.exit(f"REFUSED: {out.name}'s manifest carries served_config_drift from a previous session; its "
                 f"rows are not clean and must not be pooled with a continuation. Use a different --out.")
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


def _exit_sha(base: str) -> str | None:
    try:
        return provenance.assert_served_config(base).get("config_sha256")
    except Exception:  # noqa: BLE001 — best effort for the drift record
        return None


def _stamp_manifest(mp: Path, fields: dict) -> None:
    """Merge `fields` into an existing manifest atomically; no manifest (no item ran) → no-op."""
    if not mp.exists():
        return
    doc = json.loads(mp.read_text())
    doc.update(fields)
    tmp = mp.with_suffix(mp.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2))
    os.replace(tmp, mp)


if __name__ == "__main__":
    raise SystemExit(main())
