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
measures nothing.

Usage:
  run_opencode_probe.py --model <served-name> --items affine-cipher,beer-song [--lang python]
                        [--timeout 900] [--out benchmark/results/<model>/opencode.jsonl]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _polyglot_root() -> Path:
    for c in (Path.home() / "ws/polyglot-benchmark", Path.home() / "polyglot-benchmark"):
        if c.is_dir():
            return c
    sys.exit("polyglot exercises not found (set POLYGLOT_DIR)")


def _prepare(src: Path, dst: Path) -> None:
    """Copy an exercise WITHOUT .meta (which holds the reference solution)."""
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".meta"), dirs_exist_ok=True)


def _solution_and_test(d: Path, lang: str) -> tuple[Path, Path]:
    ext = {"python": ".py", "javascript": ".js", "go": ".go", "rust": ".rs", "java": ".java"}[lang]
    tests = sorted(p for p in d.rglob(f"*_test{ext}")) + sorted(d.rglob(f"*test*{ext}"))
    test = tests[0] if tests else None
    sols = [p for p in sorted(d.glob(f"*{ext}")) if p != test and not p.name.startswith("test")]
    if not sols or test is None:
        sys.exit(f"could not identify solution/test in {d}")
    return sols[0], test


def _run_opencode(model: str, cwd: Path, prompt: str, timeout: int, pure: bool) -> tuple[int, str, float]:
    cmd = ["opencode", "run", "--model", f"mlx-local/{model}"]
    if pure:
        # opencode's own flag for "no external plugins". The shipped config references a plugin
        # fetched over git; loading it adds a network dependency that is not part of the model's
        # capability, and a probe that can hang on a fetch measures the network.
        cmd.append("--pure")
    cmd.append(prompt)
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or ""), time.time() - t0
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return 124, out + f"\n[TIMEOUT after {timeout}s]", time.time() - t0


def _grade_python(cwd: Path, test: Path) -> tuple[bool, str]:
    py = REPO / ".venv-bench/bin/python"
    if not py.exists():
        return False, "no .venv-bench python for grading"
    p = subprocess.run([str(py), "-m", "pytest", test.name, "-q", "--no-header"],
                       cwd=cwd, capture_output=True, text=True, timeout=300)
    return p.returncode == 0, (p.stdout or "")[-600:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--items", required=True, help="comma list of exercise names")
    ap.add_argument("--lang", default="python")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-pure", action="store_true", help="load external plugins too")
    a = ap.parse_args()

    if a.lang != "python":
        sys.exit(f"grading for {a.lang} is not wired (needs its toolchain); only python for now")

    root = _polyglot_root() / a.lang / "exercises/practice"
    out = Path(a.out) if a.out else REPO / "benchmark/results" / a.model / "opencode.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    for name in [s.strip() for s in a.items.split(",") if s.strip()]:
        src = root / name
        if not src.is_dir():
            print(f"!! {name}: no such exercise at {src}", flush=True)
            continue
        with tempfile.TemporaryDirectory(prefix=f"oc-{name}-") as tmp:
            work = Path(tmp) / name
            _prepare(src, work)
            sol, test = _solution_and_test(work, a.lang)
            before = sol.read_text(errors="replace")
            prompt = (
                f"Implement the solution in {sol.name} so that the tests in {test.name} pass. "
                f"The specification is in .docs/instructions.md — read it first. "
                f"Do NOT modify {test.name}. Do not create new files unless required by the spec."
            )
            rc, log, dur = _run_opencode(a.model, work, prompt, a.timeout, not a.no_pure)
            after = sol.read_text(errors="replace")
            changed = after != before
            passed, tail = (False, "solution file untouched")
            if changed:
                passed, tail = _grade_python(work, test)
            row = {
                "bench": "opencode", "id": f"{a.lang}/{name}", "model": a.model, "sample": 0,
                "schema_version": 2, "scaffold": "opencode", "attempts": 1,
                "passed": passed, "file_changed": changed, "opencode_rc": rc,
                "wall_s": round(dur, 1), "timed_out": rc == 124,
                "note": "FIRST-ATTEMPT only — not comparable to aider `final`, which allows a "
                        "second test-informed attempt",
                "grade_tail": tail[-300:], "log_tail": log[-500:],
            }
            with out.open("a") as f:
                f.write(json.dumps(row) + "\n")
            print(f"[{time.strftime('%H:%M:%S')}] {name:16s} changed={changed} passed={passed} "
                  f"rc={rc} {dur:.0f}s", flush=True)
    print(f"rows -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
