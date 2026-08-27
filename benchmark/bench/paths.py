"""ONE place that resolves repo paths, independent of the current working directory.

WHY THIS MODULE EXISTS. Two harness paths were bare relative literals — `Path("benchmark/results")`
in `generate.py` and the string `"main_models.yaml"` as the default `registry_path` across
`provenance.py` / `model_params.py`. Both silently resolve against the CWD, so the harness only
worked from the repo root, and failed in a way that LOOKED like success.

Measured 2026-08-13: `run.py generate --benches ifeval` invoked from `benchmark/`
  - wrote every row to `benchmark/benchmark/results/` (a second, invisible results tree), and
  - failed EVERY row with `cannot read the model registry 'main_models.yaml'`,
while still printing "COMPLETE - 5 items generated. Run grade next." The provenance precheck was
also skipped, so those rows carried no sampling/APC fingerprint at all and `--clean-stale` could not
have detected config drift.

`run_convergence.py` had already been fixed for exactly this defect (its `_registry_path()` resolves
from the module location, added after making `deployed` the default broke the tool from its own
documented CWD). The shared seams had not been, so the same bug was still reachable from every other
entry point.

Resolving from the module location yields the SAME absolute paths that a repo-root invocation
produced, so existing result trees and manifests are untouched — adopting this cannot orphan results
or a run in flight.

Layout assumption, asserted at import: this file is `<repo>/benchmark/bench/paths.py`.
"""
import os
from pathlib import Path

# <repo>/benchmark/bench/paths.py -> parents[0]=bench, [1]=benchmark, [2]=<repo>
_BENCH_PKG = Path(__file__).resolve().parent
BENCHMARK_DIR = _BENCH_PKG.parent
REPO_ROOT = BENCHMARK_DIR.parent


def repo_root() -> Path:
    """Absolute path to the stack repo root."""
    return REPO_ROOT


def registry_path() -> Path:
    """Absolute path to `main_models.yaml`.

    This is the FU-2 source of truth that the `deployed` sampling profile reads, so a wrong answer
    here does not merely fail to find a file — it decides whether a run measures the sampling we
    actually ship.

    C35 (2026-08-26): honors `MLX_SERVE_CONFIG` when set — the SAME variable the router reads —
    so a bench driver launched with the draft-stripped overlay fingerprints (and samples) the
    config actually SERVED. Without this, a bench run of a draft-certified pick recorded the
    registry's `draft_kind` while the worker verifiably served draft-OFF. Relative values resolve
    against the repo root, matching the router launch convention (`MLX_SERVE_CONFIG=main_models.yaml`).
    """
    env = os.environ.get("MLX_SERVE_CONFIG")
    if env:
        p = Path(env).expanduser()
        return p if p.is_absolute() else REPO_ROOT / p
    return REPO_ROOT / "main_models.yaml"


def default_results_root() -> Path:
    """Absolute path to the shipped results tree (`<repo>/benchmark/results`)."""
    return BENCHMARK_DIR / "results"
