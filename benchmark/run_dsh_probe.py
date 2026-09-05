#!/usr/bin/env python3
"""Agentic-edit probe through DSH (DeepSeek Harness), a second scaffold beside opencode (M35).

WHY THIS EXISTS. `docs/campaign-results.md` already carries opencode agentic evidence as a
scaffold-sensitivity check on the B recommendation (`run_opencode_probe.py`), but the community
ranks dsh first on n=1 vibe tasks WITHOUT ever testing opencode. This probe answers the same
question a second way: does a completely different agentic scaffold (different tool set, different
loop implementation, a different vendor's harness) move the picture. It is a DROP-IN SIBLING of
`run_opencode_probe.py` and reuses its grading/progress-gate/PII machinery verbatim by import
(python_polyglot solution/test resolution, the five-language graders including the docker sandbox,
`_grade_result`'s tamper/untouched priority, `_tick_snapshot_fn`, `_scrub_pii`) rather than forking
it, since none of that logic is opencode-specific.

DISCOVERY (2026-09-05, against the REAL pinned `@deepseek-ai/dsh@0.1.2-rc.1`, never against a real
model -- every finding below came from `--help`, `--dump-config`, reading the installed package
tree, and one real headless run against a throwaway fake OpenAI-compatible server):

  CLI SURFACE. `dsh [--profile <name>] [--patch <overlay.yml> ...] [--dump-config] task...`.
  `dsh --profile headless "<task>"` answers ONE task, streams reasoning to STDERR under a
  `dsh: reasoning:` heading, prints the FINAL ANSWER on STDOUT, and exits: 0 on a completed
  `turn/end`, 1 on abort/error (also prints `dsh: <code>: <message>` to stderr). `-V`/`--version`
  print the exact installed version string (verified: `0.1.2-rc.1`, matches the npm package
  version -- no separate internal version scheme to track).

  HEADLESS HAS REAL FILE-EDIT AND BASH TOOLS -- the spec's worst-case ("no tools without the web
  runtime") did NOT happen. `--dump-config` shows the headless profile mounts `dsh-tool-fs`
  (`read`, `write`, `edit` -- args `{file_path, content?}`), `dsh-tool-bash`, and
  `dsh-tool-str-replace-editor` alongside the ordinary agent loop; a real headless run against the
  fake server below drove `read` then `write` and the target file was actually modified on disk.
  `write`/`edit` are gated by `dsh-fs-observation-policy`: a write to a file the session has not
  `read` in this turn is REFUSED (`FS_NOT_OBSERVED`/create-only) -- an exercise's solution file
  already exists, so a scripted responder (or a real model) MUST `read` it before it can `write`.

  PROVIDER / MODEL SELECTION. `DEEPSEEK_BASE_URL` and `DEEPSEEK_API_KEY` are real and effective
  (verified in `dsh-llm-deepseek`'s source: `baseURL: config.baseURL ?? $DEEPSEEK_BASE_URL ??
  "https://api.deepseek.com"`, `apiKeyEnv` defaults to `DEEPSEEK_API_KEY`) and the wire format is
  plain OpenAI-compatible chat-completions SSE (`POST {baseURL}/chat/completions`, `stream: true`,
  `tools: [{type:"function", function:{name,description,parameters}}]`, tool-call deltas keyed by
  `index`) -- confirmed by a real request/response cycle against the fake server. There is NO
  `DSH_MODEL` env var (checked: absent from the entire installed package tree) -- the third-party
  guides that named it are wrong. Model selection is the `agent-default-model` plugin's composition
  entry (`provider`/`model`), which `dsh --patch <overlay.yml>` can override without touching the
  redirected home's settings file (`_write_model_patch` below); `baseURL`/`apiKey` need no patch
  entry since the env vars already win.

  NO `--dir`-STYLE PROJECT ROOT. Unlike opencode (which takes `--dir <path>` as a STRING it later
  canonicizes, the documented symlinked-TMPDIR trap), dsh has no such flag -- the sandboxed
  workspace root is simply the subprocess's OS-level `cwd` (Node's `process.cwd()` resolves via
  `getcwd(3)`, which is already symlink-free), so the opencode symlink hazard does not apply here
  and this probe does not need its own `_scratch_dir`-alike hardening beyond reusing opencode's.

  HOME / TELEMETRY / PERMISSION discovery, each independently necessary to avoid a silent failure
  mode or real-$HOME writes:
    - `dsh` writes ONLY under `$HOME` (verified: `find $HOME -newer <marker>` before/after a full
      headless run showed nothing new outside `$HOME/.dsh/**`) -- no separate cache/data dir
      outside `$HOME` exists to redirect. `HOME` + `XDG_CONFIG_HOME`/`XDG_DATA_HOME`/
      `XDG_CACHE_HOME` all point under the caller-supplied `dsh_home` (production: `$STACK_WORKDIR/
      dsh/home`, mirroring the spec's Install section).
    - Telemetry: `dsh-session-telemetry-otel`'s OWN package default is `DISABLED`, but the shipped
      headless composition raises that to `FEEDBACK_ONLY` (`dsh --profile headless --dump-config`
      shows `mode: process.env.DSH_TELEMETRY_MODE || 'FEEDBACK_ONLY'`) -- `FEEDBACK_ONLY` only
      exports on an explicit `feedback/record` event, which headless one-shot runs never emit, so
      it is very unlikely to phone home either way. This probe sets `DSH_TELEMETRY_MODE=DISABLED`
      explicitly regardless, matching the campaign's "APC IS OFF EVERYWHERE"-style discipline of
      never trusting an unlikely-to-fire default over an explicit one.
    - Permission/approval: the default `sandbox-policy` mode is `workspace-write` with
      `dsh-user-approval` policy `ask` for anything needing MORE than that. Headless mounts NO
      answerer, so an `ask` that actually fires resolves `unavailable` (fail-CLOSED, never hangs on
      stdin) -- but the package's own docs name `danger-full-access` (-> approval policy `never`)
      as "the strict headless stance for CI and unattended runs", and it removes the escalation
      category entirely rather than relying on fail-closed-not-hang. This probe sets
      `DSH_PERMISSION_MODE=danger-full-access`.

  VERIFIER FIXES (2026-09-05, against the same real pinned binary — see the functions named below
  for the full reasoning): (H1) a closed port/unreachable router made dsh exit 1 with a
  `TRANSPORT:` log line that main() graded as an ordinary failed row; `_escalate_transport_failure`
  now aborts the whole run instead, per AGENTS.md's "transport failures escalate, never graded".
  (H2) dsh writes nothing to stdout/stderr until it finishes, so the stock opencode tick signature
  (a hash of the log tail) is CONSTANT and the loop-detector killed every unfinished dsh session at
  tick 3 (900s) regardless of real progress; `_dsh_snapshot_fn`/`_dsh_session_log_signature` key
  the signature off dsh's own growing session-log file instead. (M1) headless mounts `web_search`/
  `web_fetch`/`subagent`/`subagent_fork`/`ralph` by default — network egress and parallel LLM
  fan-out this probe never wants; `_DISABLED_TOOL_IDS` turns them off in the same patch overlay
  that sets the model, plus `DEEPSEEK_SEARCH_BASE_URL` is independently redirected since it is a
  separate hard default NOT covered by `DEEPSEEK_BASE_URL`.

  ROW/MANIFEST COMPARABILITY. `bench/compare.py`'s `_MUST_MATCH_RUNTIME` already includes `client`
  and REFUSES any comparison where the two sides' `runtime.client` differ (proved by the existing
  aider-vs-opencode test, `test_refuses_across_differing_agentic_scaffold_knobs`). Recording
  `runtime={"client": "dsh", ...}` in this probe's manifest (mirroring opencode's `"client":
  "opencode"`) is therefore SUFFICIENT for the harness-comparability requirement -- no change to
  `compare.py` was needed or made.

Usage:
  run_dsh_probe.py --model <served-name> --tune t0.5 --items affine-cipher,beer-song [--lang python]
                   [--base-url http://127.0.0.1:8000/v1] [--dsh-home $STACK_WORKDIR/dsh/home]
                   [--tick-s 300] [--hard-ceiling-s 3600]
                   [--out benchmark/results/<model>/dsh.<tune>.jsonl]
"""
from __future__ import annotations

import argparse
import dataclasses
import glob
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "benchmark"))
from bench import progress_gate  # noqa: E402 — needs the sys.path insert above

# Reused verbatim from the opencode probe (none of this is opencode-specific): scratch-dir
# hygiene, .meta exclusion, solution/test resolution, the five-language graders (including the
# docker sandbox), tamper/untouched grading priority, the progress-gate tick snapshot, and the
# PII scrub for persisted rows.
import run_opencode_probe as _oc  # noqa: E402

_scratch_dir = _oc._scratch_dir
_prepare = _oc._prepare
_solution_and_test = _oc._solution_and_test
_tick_snapshot_fn = _oc._tick_snapshot_fn
_grade_result = _oc._grade_result
_scrub_pii = _oc._scrub_pii
_scrub_then_tail = _oc._scrub_then_tail
_polyglot_root = _oc._polyglot_root
_polyglot_sha = _oc._polyglot_sha
_docker_available = _oc._docker_available
_grade_python = _oc._grade_python
_grade_go = _oc._grade_go
_grade_rust = _oc._grade_rust
_grade_java = _oc._grade_java
_grade_javascript = _oc._grade_javascript

# The scaffold is part of the serving path (the suffix lesson): an unpinned client version is an
# unrecorded output-determining knob. Bump this deliberately, never implicitly.
PINNED_DSH_VERSION = "0.1.2-rc.1"


def _stack_workdir() -> Path:
    env = os.environ.get("STACK_WORKDIR")
    if not env:
        sys.exit("STACK_WORKDIR not set (source config.sh) — required to confine dsh's npm "
                 "install, node_modules, and redirected HOME under $STACK_WORKDIR/dsh")
    return Path(env)


def _dsh_bin() -> Path:
    override = os.environ.get("DSH_BIN")
    if override:
        return Path(override)
    return _stack_workdir() / "dsh/node_modules/.bin/dsh"


def _dsh_version(dsh_bin: Path) -> str:
    try:
        return subprocess.check_output([str(dsh_bin), "--version"], text=True, timeout=30).strip()
    except Exception as e:  # noqa: BLE001
        sys.exit(f"cannot determine dsh version ({e}); refusing to run unversioned")


# M1 (verifier, 2026-09-05): headless dsh ships tools this probe never wants to fire — web_search /
# web_fetch (the polyglot exercises are public; unrestricted outbound HTTP is a contamination and
# egress risk this probe has no business taking) and subagent / subagent_fork / ralph (parallel
# LLM fan-out against our single-worker router, which the "ONE resident model, always" rule and
# the MLX_VLM_CACHE_SESSION_MAX=2 discipline both assume never happens). Disabling by `id` in the
# SAME `--patch` overlay that sets the model (verified: the model override still lands alongside
# these) removes the category entirely rather than trusting the model not to reach for it.
_DISABLED_TOOL_IDS = ("tool-web", "tool-subagent", "tool-subagent-fork", "tool-ralph")


def _dsh_env(dsh_home: Path, base_url: str) -> dict:
    """Every dsh write lands under `$HOME` (DISCOVERY above), so redirecting HOME plus the three
    XDG roots under it is sufficient — there is no separate cache/data dir to chase down.
    DEEPSEEK_BASE_URL points the `deepseek-official` route at the fake or real OpenAI-compatible
    endpoint; DEEPSEEK_SEARCH_BASE_URL is a SEPARATE hard default
    (`https://api.deepseek.com/anthropic/v1`, NOT redirected by DEEPSEEK_BASE_URL — verified in the
    installed `dsh-web-search-deepseek` source) that `dsh-tool-web`'s search provider would
    otherwise reach even with the base chat route redirected; it is pointed at an unused local
    port as a second line of defense alongside disabling `tool-web` in the patch overlay.
    DEEPSEEK_API_KEY is hard-coded to the literal "local" — this probe only ever talks to a fake
    or local router, never DeepSeek's real API, so a real key must never be picked up from the
    caller's environment and forwarded into a subprocess log. DSH_TELEMETRY_MODE/
    DSH_PERMISSION_MODE are the two knobs DISCOVERY found necessary to avoid a silent network call
    or an approval-driven dead end. Inherits the caller's full environment (PATH etc — dsh's bash
    tool needs a real PATH to do anything useful) and overrides only these keys.
    """
    dsh_home = Path(dsh_home)
    dsh_home.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({
        "HOME": str(dsh_home),
        "XDG_CONFIG_HOME": str(dsh_home / ".config"),
        "XDG_DATA_HOME": str(dsh_home / ".local/share"),
        "XDG_CACHE_HOME": str(dsh_home / ".cache"),
        "DEEPSEEK_BASE_URL": base_url,
        "DEEPSEEK_SEARCH_BASE_URL": "http://127.0.0.1:1/disabled",
        "DEEPSEEK_API_KEY": "local",
        "DSH_TELEMETRY_MODE": "DISABLED",
        "DSH_PERMISSION_MODE": "danger-full-access",
    })
    return env


def _write_model_patch(tmp_dir: Path, model: str) -> Path:
    """No `DSH_MODEL` env var exists (DISCOVERY above) — the served model name is pushed through
    a `--patch` overlay on the `agent-default-model` composition entry instead. YAML has no
    special characters to escape for a registry model name (alnum, `-`, `.`); this stays a plain
    string substitution rather than pulling in a YAML writer for one field. The same overlay
    disables `_DISABLED_TOOL_IDS` (M1) — web/subagent/ralph — so the model override and the tool
    lockdown always travel together.
    """
    lines = [
        "- id: agent-default-model\n",
        "  config:\n",
        "    provider: deepseek-official\n",
        f"    model: {model}\n",
    ]
    for tool_id in _DISABLED_TOOL_IDS:
        lines.append(f"- id: {tool_id}\n")
        lines.append("  disabled: true\n")
    patch = Path(tmp_dir) / "dsh-model-patch.yml"
    patch.write_text("".join(lines))
    return patch


class _ProcGroup:
    """Wraps a `Popen` started with `start_new_session=True` so the progress gate's `proc.kill()`
    reaches dsh's whole process group, not just the Node parent — dsh spawns child processes for
    its bash-sandbox and code-runtime-worker-thread tools, which a plain SIGKILL to the parent pid
    would not necessarily reach. Implements only the `poll/kill/wait/returncode` surface
    `bench/progress_gate.py` needs.
    """

    def __init__(self, proc: subprocess.Popen):
        self._proc = proc

    def poll(self):
        return self._proc.poll()

    def wait(self, *a, **kw):
        return self._proc.wait(*a, **kw)

    @property
    def returncode(self):
        return self._proc.returncode

    def kill(self):
        try:
            os.killpg(os.getpgid(self._proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception:  # noqa: BLE001 — never let a kill-time error mask the real stop reason
            try:
                self._proc.kill()
            except Exception:  # noqa: BLE001
                pass


def _dsh_session_log_signature(dsh_home: Path) -> str:
    """H2 (verifier, 2026-09-05): dsh headless writes ZERO bytes to stdout/stderr until the whole
    task completes (measured: 0 bytes over 32s of live streaming), so
    `progress_gate.tail_signature` on that constant log tail is CONSTANT across every tick — and
    `ProgressGate.observe()` checks the LOOP rule (identical signature `loop_repeats` times)
    BEFORE the stall rule, so a session that is genuinely progressing (the file keeps changing,
    which resets the STALL counter) still gets killed as "looping" at exactly tick `loop_repeats`
    (900s at defaults) because its SIGNATURE never moves. That silently caps every unfinished dsh
    session at a fraction of `hard_ceiling_s`, an unrecorded (harness x compute-budget) composite
    against opencode (whose tool-call transcript DOES change the tail every tick).

    dsh's own durable session log (`$HOME/.dsh/sessions/**/session.jsonl*`, its append-only event
    log) DOES grow while a session streams (~2.5 KB / 4s measured) — hashing the (relative path,
    size) of every `session.jsonl*` file under `dsh_home` gives a liveness signature that reflects
    actual progress instead of dsh's stdout cadence. A session log that stops growing (a real
    stall) still hashes to a repeated signature, so a genuinely wedged session is unaffected.
    """
    root = Path(dsh_home) / ".dsh" / "sessions"
    if not root.is_dir():
        return "no-session-dir"
    entries = []
    for name in sorted(glob.glob(str(root / "**" / "session.jsonl*"), recursive=True)):
        try:
            entries.append((os.path.relpath(name, root), os.path.getsize(name)))
        except OSError:
            continue
    return hashlib.sha256(repr(entries).encode()).hexdigest()[:16]


def _find_session_log(dsh_home: Path, before: set) -> str | None:
    """Best-effort discovery of THIS run's session log (L2), for post-hoc diagnosis in the row.
    `before` is the set of `session.jsonl*` paths that already existed when the run started;
    picks the newest file among whatever is new, or (if nothing looks new — e.g. a resumed
    session) the most recently modified file overall, so a row always names its best guess rather
    than nothing."""
    root = Path(dsh_home) / ".dsh" / "sessions"
    if not root.is_dir():
        return None
    after = set(glob.glob(str(root / "**" / "session.jsonl*"), recursive=True))
    candidates = (after - before) or after
    if not candidates:
        return None
    try:
        return max(candidates, key=lambda p: os.path.getmtime(p))
    except OSError:
        return None


def _dsh_snapshot_fn(cwd: Path, sol: Path, test: Path, before_sol: str, grade, log_path: Path,
                     dsh_home: Path):
    """Wraps `_tick_snapshot_fn` (opencode's, reused verbatim) and overrides the tick's
    `signature` with `_dsh_session_log_signature` (H2) — every OTHER field (file-changed
    detection, grading, the neutral-on-race handling) stays exactly opencode's implementation.
    `dataclasses.replace` keeps this a pure wrapper rather than a fork of `Tick` construction.
    """
    inner = _tick_snapshot_fn(cwd, sol, test, before_sol, grade, log_path)

    def _snapshot(elapsed_s: float) -> "progress_gate.Tick":
        tick = inner(elapsed_s)
        return dataclasses.replace(tick, signature=_dsh_session_log_signature(dsh_home))

    return _snapshot


def _run_dsh(dsh_bin: Path, model: str, cwd: Path, prompt: str, sol: Path, test: Path, grade,
            before_sol: str, *, base_url: str, dsh_home: Path, tick_s: int, hard_ceiling_s: int,
            poll_s: float, stall_ticks: int, loop_repeats: int
            ) -> tuple[int, str, float, "progress_gate.GateResult", str | None]:
    """Run dsh headless under the SAME progress-gated bound as opencode (`bench/progress_gate.py`)
    — see that module's docstring. The policy is IDENTICAL across harnesses and models; only the
    diagnosis timing can differ, never the compute budget. Returns the session log path (L2) as a
    5th element, best-effort, for post-hoc diagnosis.
    """
    patch = _write_model_patch(cwd.parent, model)
    cmd = [str(dsh_bin), "--profile", "headless", "--patch", str(patch), prompt]
    env = _dsh_env(dsh_home, base_url)

    sessions_root = Path(dsh_home) / ".dsh" / "sessions"
    before_sessions = (set(glob.glob(str(sessions_root / "**" / "session.jsonl*"), recursive=True))
                       if sessions_root.is_dir() else set())

    log_path = cwd / ".dsh_probe_log.txt"
    with log_path.open("w") as log_f:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=log_f, stderr=subprocess.STDOUT,
                                text=True, start_new_session=True)
        wrapped = _ProcGroup(proc)
        snapshot_fn = _dsh_snapshot_fn(cwd, sol, test, before_sol, grade, log_path, dsh_home)
        result = progress_gate.run_progress_gated(
            wrapped, snapshot_fn, tick_s=tick_s, hard_ceiling_s=hard_ceiling_s, poll_s=poll_s,
            stall_ticks=stall_ticks, loop_repeats=loop_repeats)
    log = log_path.read_text(errors="replace") if log_path.exists() else ""
    session_log = _find_session_log(dsh_home, before_sessions)
    return proc.returncode, log, result.elapsed_s, result, session_log


def _escalate_transport_failure(rc: int, log: str, base_url: str) -> None:
    """H1 (verifier, 2026-09-05): a closed port / unreachable router exits dsh with rc=1 and a
    `dsh: TRANSPORT: ...` log line (dsh-llm-deepseek, thrown after its 5-retry exponential backoff
    is exhausted — measured: ~15s wall for a closed port). AGENTS.md is explicit: "Transport/HTTP
    failures ESCALATE (abort, nonzero exit), they are NEVER graded" — grading this as
    passed=False/file_changed=False would silently launder a router-down condition into a quality
    result indistinguishable from the model actually failing the task. This must run BEFORE any
    grading or row-write for the item.
    """
    if rc != 0 and "TRANSPORT:" in log:
        sys.exit(f"dsh transport failure talking to {base_url} — ESCALATING, never graded "
                 f"(AGENTS.md: transport failures escalate, are never graded). rc={rc}. "
                 f"Log tail:\n{log[-800:]}")


def _existing_row_ids(out: Path) -> set:
    """L1: a retried/resumed invocation must not silently duplicate an item's row. Reads whatever
    is already on disk (malformed lines are skipped, never fatal — this is a guard, not a parser)."""
    ids = set()
    if not out.exists():
        return ids
    for line in out.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "id" in row:
            ids.add(row["id"])
    return ids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--tune", required=True,
                    help="tune label folded into the default --out path "
                         "(benchmark/results/<model>/dsh.<tune>.jsonl), per the M35 spec's Rows section")
    ap.add_argument("--items", required=True, help="comma list of exercise names")
    ap.add_argument("--lang", default="python")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000/v1",
                    help="OpenAI-compatible endpoint dsh's deepseek-official route targets "
                         "(the mlx-serve router by default; point at a fake server for tests)")
    ap.add_argument("--dsh-home", default=None,
                    help="redirected $HOME for dsh (default: $STACK_WORKDIR/dsh/home)")
    ap.add_argument("--tick-s", type=int, default=progress_gate.DEFAULT_TICK_S)
    ap.add_argument("--hard-ceiling-s", type=int, default=progress_gate.DEFAULT_HARD_CEILING_S)
    ap.add_argument("--stall-ticks", type=int, default=progress_gate.DEFAULT_STALL_TICKS)
    ap.add_argument("--loop-repeats", type=int, default=progress_gate.DEFAULT_LOOP_REPEATS)
    ap.add_argument("--poll-s", type=float, default=5.0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--allow-version-drift", action="store_true",
                    help=f"run even if dsh != {PINNED_DSH_VERSION} (drift is recorded)")
    a = ap.parse_args()

    SUPPORTED_LANGS = {"python", "go", "rust", "java", "javascript"}
    if a.lang not in SUPPORTED_LANGS:
        sys.exit(f"unsupported --lang {a.lang!r}; supported: {sorted(SUPPORTED_LANGS)}")

    docker_ok = True
    if a.lang != "python":
        docker_ok = _docker_available()
        if not docker_ok:
            print(f"!! docker unavailable — every {a.lang} row in this run will be skipped "
                 f"(acc:null); see run_opencode_probe.py's module docstring (GRADING SANDBOX)",
                 flush=True)
    graders = {
        "python": _grade_python,
        "go": lambda w, t: _grade_go(w, t, docker_ok=docker_ok),
        "rust": lambda w, t: _grade_rust(w, t, docker_ok=docker_ok),
        "java": lambda w, t: _grade_java(w, t, docker_ok=docker_ok),
        "javascript": lambda w, t: _grade_javascript(w, t, docker_ok=docker_ok),
    }
    grade = graders[a.lang]

    dsh_bin = _dsh_bin()
    dsh_version = _dsh_version(dsh_bin)
    if dsh_version != PINNED_DSH_VERSION and not a.allow_version_drift:
        sys.exit(f"dsh {dsh_version} != pinned {PINNED_DSH_VERSION}; a scaffold version is "
                 f"output-determining. Bump PINNED_DSH_VERSION deliberately or pass "
                 f"--allow-version-drift to record the drift.")

    dsh_home = Path(a.dsh_home) if a.dsh_home else _stack_workdir() / "dsh/home"

    polyglot = _polyglot_root()
    poly_sha = _polyglot_sha(polyglot)
    root = polyglot / a.lang / "exercises/practice"
    out = Path(a.out) if a.out else REPO / "benchmark/results" / a.model / f"dsh.{a.tune}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    existing_ids = _existing_row_ids(out)

    try:
        from bench import provenance
        man = provenance.gather(a.model, profile="deployed",
                                runtime={"client": "dsh", "edit_format": "tools",
                                         "dsh_version": dsh_version,
                                         "harness_profile": "headless",
                                         "polyglot_sha": poly_sha,
                                         "tick_s": a.tick_s, "hard_ceiling_s": a.hard_ceiling_s,
                                         "stall_ticks": a.stall_ticks,
                                         "loop_repeats": a.loop_repeats})
        out.with_suffix(".manifest.json").write_text(json.dumps(man, indent=2))
    except Exception as e:  # noqa: BLE001 — never block a run on provenance, but say so loudly
        print(f"!! manifest not written: {e}", flush=True)

    for name in [s.strip() for s in a.items.split(",") if s.strip()]:
        item_id = f"{a.lang}/{name}"
        if item_id in existing_ids:
            print(f"!! {item_id}: already in {out}, skipping (no duplicate row written)", flush=True)
            continue
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
            rc, log, dur, gate_result, session_log = _run_dsh(
                dsh_bin, a.model, work, prompt, sol, test, grade, before,
                base_url=a.base_url, dsh_home=dsh_home, tick_s=a.tick_s,
                hard_ceiling_s=a.hard_ceiling_s, poll_s=a.poll_s,
                stall_ticks=a.stall_ticks, loop_repeats=a.loop_repeats)
            _escalate_transport_failure(rc, log, a.base_url)
            after = sol.read_text(errors="replace")
            changed = after != before
            passed, tail, test_modified = _grade_result(work, test, test_before, changed, grade)
            row = {
                "bench": "dsh", "id": item_id, "model": a.model, "sample": 0,
                "schema_version": 2, "scaffold": "dsh", "harness": "dsh",
                "harness_version": dsh_version, "harness_profile": "headless", "attempts": 1,
                "passed": passed, "file_changed": changed, "test_modified": test_modified,
                "dsh_rc": rc, "polyglot_sha": poly_sha,
                "dsh_session_log": _scrub_pii(session_log) if session_log else None,
                "wall_s": round(dur, 1),
                "stop_reason": gate_result.stop_reason,
                "timed_out": gate_result.stop_reason != "completed",
                "gate_ticks": len(gate_result.ticks),
                "gate_failure_trajectory": [t.n_failing for t in gate_result.ticks],
                "gate_effective_bound_s": round(gate_result.elapsed_s, 1),
                "note": "FIRST-ATTEMPT only — not comparable to aider `final`, which allows a "
                        "second test-informed attempt",
                "grade_tail": _scrub_then_tail(tail, 300), "log_tail": _scrub_then_tail(log, 500),
            }
            with out.open("a") as f:
                f.write(json.dumps(row) + "\n")
            existing_ids.add(item_id)
            print(f"[{time.strftime('%H:%M:%S')}] {name:16s} changed={changed} passed={passed} "
                  f"rc={rc} {dur:.0f}s", flush=True)
    print(f"rows -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
