"""The results tree needs ONE resolvable root.

Today every consumer hardcodes its own: `generate.RESULTS` is CWD-relative
(`Path("benchmark/results")`), `grade.grade_all` re-hardcodes the same literal, and a dozen
`run_*.py` modules define file-relative constants. A reporting pass (and any test that wants
to write results into tmp_path) needs a single seam.

The COMPAT CONTRACT this locks in: eight existing tests do
`monkeypatch.setattr(generate, "RESULTS", tmp_path)`. That must keep working, and it must win
over the environment — otherwise an operator with MLX_BENCH_RESULTS exported in their shell
would silently redirect every test's writes into the real results tree. So precedence is:

    explicitly-overridden module RESULTS  >  $MLX_BENCH_RESULTS  >  the default

"Explicitly overridden" means "differs from the shipped default", which is exactly what a
monkeypatch does and what normal operation never does.
"""
from pathlib import Path

import bench.generate as G


def test_default_root_is_the_shipped_tree(monkeypatch):
    """The default is still `<repo>/benchmark/results` — but ABSOLUTE now, not the relative literal.

    This test used to assert `== Path("benchmark/results")`, which encoded the CWD-relative defect:
    running from `benchmark/` silently produced a second results tree at
    `benchmark/benchmark/results/`. The contract it was protecting (the default is the shipped tree,
    and the env var / monkeypatch seams still override it) is unchanged and asserted below.
    """
    monkeypatch.delenv("MLX_BENCH_RESULTS", raising=False)
    import bench.paths as P
    assert G.results_root() == P.default_results_root()
    assert G.results_root() == P.repo_root() / "benchmark" / "results"


def test_env_override_is_honoured(monkeypatch):
    monkeypatch.setenv("MLX_BENCH_RESULTS", "/tmp/somewhere-else")
    assert G.results_root() == Path("/tmp/somewhere-else")


def test_monkeypatched_module_constant_wins_over_env(tmp_path, monkeypatch):
    """The compat contract: a test's monkeypatch must not be defeated by a stray env var."""
    monkeypatch.setenv("MLX_BENCH_RESULTS", "/tmp/should-be-ignored")
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    assert G.results_root() == tmp_path
    assert G.result_path("m", "aime") == tmp_path / "m" / "aime.jsonl"


def test_result_path_still_escapes_slashes_in_model_names(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    assert G.result_path("org/model", "aime") == tmp_path / "org__model" / "aime.jsonl"


def test_grade_all_writes_scores_under_the_same_root(tmp_path, monkeypatch):
    """grade.grade_all hardcoded Path("benchmark/results") — so `grade` ignored the seam and
    wrote scores.json into the real tree even when results came from elsewhere."""
    import bench.grade as GR
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    monkeypatch.setattr(GR, "grade", lambda b, m: {"benchmark": b, "model": m, "acc": None,
                                                   "items": [{"id": "x"}]})
    GR.grade_all(["m"], ["aime"])
    scores = tmp_path / "scores.json"
    assert scores.exists(), "grade_all must write scores.json under results_root()"
    assert "items" not in scores.read_text(), "per-item detail must stay out of scores.json"


# ------------------------------------------------------------------ CWD independence
def test_default_root_is_CWD_INDEPENDENT(monkeypatch, tmp_path):
    """THE regression: the default was the RELATIVE literal `Path("benchmark/results")`.

    Measured 2026-08-13: `run.py generate` invoked from `benchmark/` wrote every row to
    `benchmark/benchmark/results/`, and because `main_models.yaml` was equally CWD-relative it also
    failed EVERY row with "cannot read the model registry" — while still printing
    "COMPLETE — 5 items generated. Run `grade` next.". `run_convergence` had already been fixed for
    exactly this defect via a module-relative `_registry_path()`; the shared seam had not.

    Resolving from the module location gives the SAME absolute path a repo-root invocation gave, so
    existing result trees are untouched — this cannot orphan a run in flight.
    """
    monkeypatch.delenv("MLX_BENCH_RESULTS", raising=False)
    from_root = G.results_root()
    monkeypatch.chdir(tmp_path)                       # any other CWD
    assert G.results_root() == from_root, "results root moved when the CWD changed"
    assert G.results_root().is_absolute()


def test_default_root_still_ends_at_benchmark_results(monkeypatch):
    """It must be the same tree as before, not merely a stable one."""
    monkeypatch.delenv("MLX_BENCH_RESULTS", raising=False)
    assert G.results_root().parts[-2:] == ("benchmark", "results")


def test_registry_default_is_CWD_INDEPENDENT(monkeypatch, tmp_path):
    """Same defect, second site: provenance/model_params defaulted to the bare string
    "main_models.yaml", so provenance was SKIPPED from any CWD but the repo root — meaning rows
    carried no sampling/APC fingerprint and --clean-stale could not detect config drift."""
    import bench.paths as P
    from_root = P.registry_path()
    monkeypatch.chdir(tmp_path)
    assert P.registry_path() == from_root
    assert P.registry_path().is_absolute()
    assert P.registry_path().name == "main_models.yaml"


def test_registry_default_actually_exists_in_the_repo():
    """A path that resolves but points nowhere would fail just as silently."""
    import bench.paths as P
    assert P.registry_path().exists(), f"{P.registry_path()} does not exist"
