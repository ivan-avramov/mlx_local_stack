"""Adapter that drives the official Aider polyglot benchmark against our mlx-serve
OpenAI-compatible endpoint and normalizes its pass-rate. Aider's harness does its own
edit loop + per-exercise test execution; we only orchestrate + parse. The harness +
exercises install/clone only where this runs (optional); detected lazily, graceful-degrade."""
import os
import re
import subprocess
import sys

AXIS = "agentic_coding"


def aider_available(aider_repo: str) -> bool:
    """The aider benchmark harness lives in the aider REPO (not the pip package)."""
    return bool(aider_repo) and os.path.isfile(os.path.join(aider_repo, "benchmark", "benchmark.py"))


def parse_pass_rate(stdout: str) -> dict:
    """Extract pass_rate_1 / pass_rate_2 (percentages) from aider benchmark stdout."""
    out = {}
    for k in ("pass_rate_1", "pass_rate_2"):
        m = re.search(rf"{k}\s*[:=]\s*([0-9.]+)", stdout or "")
        out[k] = float(m.group(1)) if m else None
    return out


def run_aider(model, exercises_dir, aider_repo, edit_format="whole", num_tests=None,
              endpoint="http://localhost:8000/v1", run_name="bake",
              runner=subprocess.run) -> dict:
    """Drive the aider polyglot benchmark against the local mlx-serve endpoint and normalize
    the pass-rate. `runner` is injectable for tests. Never raises; graceful-degrade."""
    base = {"model": model, "axis": AXIS, "tool": "aider_polyglot", "edit_format": edit_format}
    if not aider_available(aider_repo):
        return {**base, "acc": None, "skipped": True,
                "note": f"aider harness not found under {aider_repo!r}; "
                        f"clone Aider-AI/aider + polyglot-benchmark (see README)"}
    # AIDER_DOCKER: aider's benchmark.py refuses to run (prints a warning + returns, no exercises)
    # unless this is set — a guard against running unvetted model code outside a container. We run
    # on the host (all polyglot toolchains present + a controlled benchmark), so set it explicitly.
    env = {**os.environ, "OPENAI_API_BASE": endpoint, "OPENAI_API_KEY": "sk-local",
           "AIDER_DOCKER": "1"}
    # The polyglot python exercises run `pytest` via subprocess; it lives in the aider venv
    # (== the python running benchmark.py). Prepend that bindir so the test-runner finds it
    # (other langs — cargo/go/npm/javac/g++ — resolve from the inherited PATH).
    env["PATH"] = os.path.dirname(sys.executable) + os.pathsep + env.get("PATH", "")
    # benchmark.py asserts BENCHMARK_DNAME (default relative "tmp.benchmarks") exists; we run from
    # an arbitrary CWD, so pin it to an absolute dir under the aider repo (and create it).
    bench_workdir = os.path.join(aider_repo, "benchmark", "tmp.benchmarks")
    try:
        os.makedirs(bench_workdir, exist_ok=True)
    except OSError:
        pass
    env["AIDER_BENCHMARK_DIR"] = bench_workdir
    cmd = [sys.executable, os.path.join(aider_repo, "benchmark", "benchmark.py"), run_name,
           "--model", f"openai/{model}", "--edit-format", edit_format,
           "--threads", "1", "--exercises-dir", exercises_dir, "--new"]
    if num_tests is not None:
        cmd += ["--num-tests", str(num_tests)]
    try:
        proc = runner(cmd, env=env, capture_output=True, text=True)
    except Exception as e:  # noqa: BLE001 — harness/python launch failure; degrade
        return {**base, "acc": None, "skipped": False,
                "note": f"aider runner raised: {type(e).__name__}: {str(e)[:120]}"}
    rc = getattr(proc, "returncode", 1)
    if rc != 0:
        return {**base, "acc": None, "skipped": False,
                "note": f"aider benchmark failed rc={rc}: {(getattr(proc, 'stderr', '') or '')[:160]}"}
    rates = parse_pass_rate(getattr(proc, "stdout", "") or "")
    pr = rates.get("pass_rate_2")
    if pr is None:
        pr = rates.get("pass_rate_1")
    if pr is None:  # ran (rc=0) but no pass_rate parsed -> likely an output-format mismatch
        return {**base, **rates, "acc": None, "skipped": False,
                "note": "aider ran (rc=0) but no pass_rate_# parsed from stdout — check aider output format"}
    acc = pr / 100.0 if pr > 1.0 else pr   # aider prints percentages (0-100) -> 0-1 fraction
    return {**base, **rates, "acc": acc, "skipped": False}
