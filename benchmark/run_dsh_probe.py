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

  ROW/MANIFEST COMPARABILITY. `bench/compare.py`'s `_MUST_MATCH_RUNTIME` already includes `client`
  and REFUSES any comparison where the two sides' `runtime.client` differ (proved by the existing
  aider-vs-opencode test, `test_refuses_across_differing_agentic_scaffold_knobs`). Recording
  `runtime={"client": "dsh", ...}` in this probe's manifest (mirroring opencode's `"client":
  "opencode"`) is therefore SUFFICIENT for the harness-comparability requirement -- no change to
  `compare.py` was needed or made.

Usage:
  run_dsh_probe.py --model <served-name> --items affine-cipher,beer-song [--lang python]
                   [--base-url http://127.0.0.1:8000/v1] [--dsh-home $STACK_WORKDIR/dsh/home]
                   [--tick-s 300] [--hard-ceiling-s 3600] [--out benchmark/results/<model>/dsh.jsonl]
"""
from __future__ import annotations

import argparse
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


def _dsh_env(dsh_home: Path, base_url: str) -> dict:
    """Every dsh write lands under `$HOME` (DISCOVERY above), so redirecting HOME plus the three
    XDG roots under it is sufficient — there is no separate cache/data dir to chase down.
    DEEPSEEK_BASE_URL/DEEPSEEK_API_KEY point the `deepseek-official` route at the fake or real
    OpenAI-compatible endpoint; DSH_TELEMETRY_MODE/DSH_PERMISSION_MODE are the two knobs DISCOVERY
    found necessary to avoid a silent network call or an approval-driven dead end. Inherits the
    caller's full environment (PATH etc — dsh's bash tool needs a real PATH to do anything useful)
    and overrides only these keys.
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
        "DEEPSEEK_API_KEY": os.environ.get("DEEPSEEK_API_KEY", "local"),
        "DSH_TELEMETRY_MODE": "DISABLED",
        "DSH_PERMISSION_MODE": "danger-full-access",
    })
    return env


def _write_model_patch(tmp_dir: Path, model: str) -> Path:
    """No `DSH_MODEL` env var exists (DISCOVERY above) — the served model name is pushed through
    a `--patch` overlay on the `agent-default-model` composition entry instead. YAML has no
    special characters to escape for a registry model name (alnum, `-`, `.`); this stays a plain
    string substitution rather than pulling in a YAML writer for one field.
    """
    patch = Path(tmp_dir) / "dsh-model-patch.yml"
    patch.write_text(
        "- id: agent-default-model\n"
        "  config:\n"
        "    provider: deepseek-official\n"
        f"    model: {model}\n"
    )
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


def _run_dsh(dsh_bin: Path, model: str, cwd: Path, prompt: str, sol: Path, test: Path, grade,
            before_sol: str, *, base_url: str, dsh_home: Path, tick_s: int, hard_ceiling_s: int,
            poll_s: float, stall_ticks: int, loop_repeats: int
            ) -> tuple[int, str, float, "progress_gate.GateResult"]:
    """Run dsh headless under the SAME progress-gated bound as opencode (`bench/progress_gate.py`)
    — see that module's docstring. The policy is IDENTICAL across harnesses and models; only the
    diagnosis timing can differ, never the compute budget.
    """
    patch = _write_model_patch(cwd.parent, model)
    cmd = [str(dsh_bin), "--profile", "headless", "--patch", str(patch), prompt]
    env = _dsh_env(dsh_home, base_url)

    log_path = cwd / ".dsh_probe_log.txt"
    with log_path.open("w") as log_f:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=log_f, stderr=subprocess.STDOUT,
                                text=True, start_new_session=True)
        wrapped = _ProcGroup(proc)
        snapshot_fn = _tick_snapshot_fn(cwd, sol, test, before_sol, grade, log_path)
        result = progress_gate.run_progress_gated(
            wrapped, snapshot_fn, tick_s=tick_s, hard_ceiling_s=hard_ceiling_s, poll_s=poll_s,
            stall_ticks=stall_ticks, loop_repeats=loop_repeats)
    log = log_path.read_text(errors="replace") if log_path.exists() else ""
    return proc.returncode, log, result.elapsed_s, result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
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
    out = Path(a.out) if a.out else REPO / "benchmark/results" / a.model / "dsh.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

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
            rc, log, dur, gate_result = _run_dsh(
                dsh_bin, a.model, work, prompt, sol, test, grade, before,
                base_url=a.base_url, dsh_home=dsh_home, tick_s=a.tick_s,
                hard_ceiling_s=a.hard_ceiling_s, poll_s=a.poll_s,
                stall_ticks=a.stall_ticks, loop_repeats=a.loop_repeats)
            after = sol.read_text(errors="replace")
            changed = after != before
            passed, tail, test_modified = _grade_result(work, test, test_before, changed, grade)
            row = {
                "bench": "dsh", "id": f"{a.lang}/{name}", "model": a.model, "sample": 0,
                "schema_version": 2, "scaffold": "dsh", "harness": "dsh",
                "harness_version": dsh_version, "harness_profile": "headless", "attempts": 1,
                "passed": passed, "file_changed": changed, "test_modified": test_modified,
                "dsh_rc": rc, "polyglot_sha": poly_sha,
                "wall_s": round(dur, 1),
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
