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


def test_default_root_is_the_shipped_literal(monkeypatch):
    monkeypatch.delenv("MLX_BENCH_RESULTS", raising=False)
    assert G.results_root() == Path("benchmark/results")


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
