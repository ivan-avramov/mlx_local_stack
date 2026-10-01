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
import re
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


class MissingWorkdirError(RuntimeError):
    """`STACK_WORKDIR` is neither exported nor declared in the machine-local config.sh."""


_CONFIG_SH_WORKDIR = re.compile(r'^\s*(?:export\s+)?STACK_WORKDIR=["\']?([^"\'\n#]+)["\']?\s*(?:#.*)?$', re.M)


def stack_workdir(*, required: bool = True) -> Path | None:
    """The out-of-repo artifact home (AGENTS.md: NO FILESYSTEM POLLUTION OUTSIDE $STACK_WORKDIR).

    `STACK_WORKDIR` in the environment wins; otherwise `${XDG_CONFIG_HOME:-~/.config}/mlx_local_stack/
    config.sh` is PARSED for the same assignment (no shell is executed; `$HOME`/`~` are expanded).
    Missing everywhere: `MissingWorkdirError`, or None with `required=False` for callers that degrade
    to a pre-approved cache location. P89 (2026-09-29): one resolver for the opencode probe (M53), the
    `vision_gate` image cache and the visionqa loader — a hand launch from a fresh terminal (which does
    not source config.sh) no longer refuses late or silently falls back.
    """
    env = os.environ.get("STACK_WORKDIR")
    if env:
        return Path(os.path.expanduser(env))
    cfg = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "mlx_local_stack/config.sh"
    if cfg.is_file():
        m = _CONFIG_SH_WORKDIR.search(cfg.read_text(errors="replace"))
        if m:
            return Path(os.path.expanduser(os.path.expandvars(m.group(1).strip())))
    if required:
        raise MissingWorkdirError(
            "STACK_WORKDIR is not set and no `mlx_local_stack/config.sh` declares it (AGENTS.md: no "
            "filesystem pollution outside $STACK_WORKDIR). Export STACK_WORKDIR or source config.sh.")
    return None


def confine_path(path, *, what: str = "path") -> str | None:
    """5th cold review P19 (AGENTS.md: NO FILESYSTEM POLLUTION OUTSIDE $STACK_WORKDIR): None if
    `path` (resolved) is under the repo root OR the configured STACK_WORKDIR; else a human-readable
    refusal reason. STACK_WORKDIR is consulted only if actually configured (`required=False`) -- an
    unset STACK_WORKDIR is not itself a confinement failure for a repo-relative path."""
    p = Path(path).resolve()
    roots = [repo_root().resolve()]
    wd = stack_workdir(required=False)
    if wd is not None:
        roots.append(Path(wd).resolve())
    for root in roots:
        try:
            p.relative_to(root)
            return None
        except ValueError:
            continue
    allowed = ", ".join(str(r) for r in roots)
    return (f"{what} {p} is outside the repo and outside STACK_WORKDIR ({allowed}) -- refusing "
           "(AGENTS.md: no filesystem pollution outside STACK_WORKDIR)")
