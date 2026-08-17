"""Every graded (model, bench) result must persist BESIDE ITS ROWS, not only in the last
`scores.json`.

WHY. `grade_all` writes one `scores.json` containing exactly the pairs that invocation covered. So
grading one model OVERWRITES the record for every other model. That is already recorded as the reason
`scoreboard.py` reads per-item rows instead — but reading rows means the scoreboard cannot show `acc`
or `acc_strict`, i.e. **the ranking key is absent from the scoreboard**, because computing it needs the
graders (docker for evalplus, `lcb_runner` for LCB) and the scoreboard deliberately stays cheap and
environment-independent.

Measured 2026-08-14: re-grading `aime`/`math500`/`humanevalplus`/`mbppplus` across 17 model dirs
produced 68 cells; then grading ONE arm of the live run reduced `scores.json` to a single entry. The 68
were not wrong, they were erased — and they cost docker time to produce.

Fix: `grade_all` also writes `results/<model>/<bench>.score.json`. One file per pair, so a later grade
of a different pair cannot clobber it, and the scoreboard can read the ranking key straight off disk.
`scores.json` is still written, unchanged, for existing callers.
"""
import json

import pytest

from bench import generate, grade


def _fake_score(model, bench, acc, strict):
    return {"model": model, "benchmark": bench, "acc": acc, "acc_strict": strict,
            "acc_strict_budget": 81920, "n": 100, "conv_rate": 0.97,
            "items": [{"id": "x", "sample": 0, "score": 1.0}]}


def test_grade_all_writes_a_per_pair_score_file(tmp_path, monkeypatch):
    monkeypatch.setattr(generate, "results_root", lambda: tmp_path)
    monkeypatch.setattr(grade, "grade",
                        lambda b, m: _fake_score(m, b, 0.93, 0.90))

    grade.grade_all(["M"], ["humanevalplus"])

    p = tmp_path / "M" / "humanevalplus.score.json"
    assert p.exists(), "no per-pair score file — a later grade of another pair would erase this result"
    d = json.loads(p.read_text())
    assert d["acc"] == 0.93 and d["acc_strict"] == 0.90


def test_a_later_grade_of_a_DIFFERENT_pair_does_not_clobber(tmp_path, monkeypatch):
    """The actual failure: grading model B must leave model A's record intact."""
    monkeypatch.setattr(generate, "results_root", lambda: tmp_path)
    monkeypatch.setattr(grade, "grade", lambda b, m: _fake_score(m, b, 0.93, 0.90))
    grade.grade_all(["A"], ["humanevalplus"])

    monkeypatch.setattr(grade, "grade", lambda b, m: _fake_score(m, b, 0.60, 0.55))
    grade.grade_all(["B"], ["humanevalplus"])

    a = json.loads((tmp_path / "A" / "humanevalplus.score.json").read_text())
    b = json.loads((tmp_path / "B" / "humanevalplus.score.json").read_text())
    assert a["acc"] == 0.93, "grading B erased A's result — the scores.json defect, reproduced"
    assert b["acc"] == 0.60
    # ...while scores.json still holds only the last call, as before.
    assert [s["model"] for s in json.loads((tmp_path / "scores.json").read_text())] == ["B"]


def test_per_pair_file_excludes_the_bulky_items_list(tmp_path, monkeypatch):
    """`items` is per-draw and can be thousands of rows; it is already recoverable from the jsonl.
    Keeping it here would duplicate the results tree on every grade."""
    monkeypatch.setattr(generate, "results_root", lambda: tmp_path)
    monkeypatch.setattr(grade, "grade", lambda b, m: _fake_score(m, b, 0.93, 0.90))
    grade.grade_all(["M"], ["mbppplus"])
    d = json.loads((tmp_path / "M" / "mbppplus.score.json").read_text())
    assert "items" not in d


def test_scoreboard_reads_acc_and_acc_strict(tmp_path, monkeypatch):
    """The point of the exercise: the RANKING KEY becomes visible in the scoreboard."""
    from bench import paths
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "sb", paths.BENCHMARK_DIR / "m1" / "scoreboard.py")
    sb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sb)

    mdir = tmp_path / "M"
    mdir.mkdir()
    (mdir / "humanevalplus.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"id": i, "sample": 0, "completion_tokens": 1000, "finish_reason": "stop",
         "thinking_budget": 81920, "wall_s": 10} for i in range(12)]))
    (mdir / "humanevalplus.score.json").write_text(json.dumps(
        {"acc": 0.93, "acc_strict": 0.90, "acc_strict_budget": 81920}))
    monkeypatch.setattr(sb.paths, "default_results_root", lambda: tmp_path)

    data = sb.collect()
    rec = data["M"]["humanevalplus"]
    assert rec["acc"] == 0.93
    assert rec["acc_strict"] == 0.90


def test_scoreboard_marks_an_UNGRADED_pair_rather_than_blanking_it(tmp_path, monkeypatch):
    """An ungraded pair must read as ungraded, never as a zero or an empty cell — the scoreboard's
    whole purpose is that an unmeasured combination cannot be mistaken for a pass."""
    from bench import paths
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "sb", paths.BENCHMARK_DIR / "m1" / "scoreboard.py")
    sb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sb)

    mdir = tmp_path / "M"
    mdir.mkdir()
    (mdir / "aime.jsonl").write_text(json.dumps(
        {"id": 1, "sample": 0, "completion_tokens": 100, "finish_reason": "stop",
         "thinking_budget": 81920, "wall_s": 5}))
    monkeypatch.setattr(sb.paths, "default_results_root", lambda: tmp_path)

    rec = sb.collect()["M"]["aime"]
    assert rec["acc"] is None and rec["acc_strict"] is None


# --------------------------------------------------------------- the two DEGENERACY definitions
#
# The corpus contains TWO measures of degenerate-loop cost and they collide under one name:
#   * `grade.py` persists `degenerate_wall_share` over the SELF-TERMINATING (EOS'd) degenerate rows
#     ONLY — the class the convergence formula scores as CONVERGED (bench/traces.summarize).
#   * the scoreboard's own column covered EVERY row whose trace shows a verbatim loop.
# Both are defensible; publishing either as `degenWall%` is not. Measured 2026-08-16 on mbppplus:
# `Ornith-1.0-35B-mlx-uniform-4bit` reads 63.1% broad vs 0.0% narrow, and
# `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` 70.4% vs 0.0%. So the column NAMES must say which is which.

def _load_sb():
    from bench import paths
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "sb_degen", paths.BENCHMARK_DIR / "m1" / "scoreboard.py")
    sb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sb)
    return sb


_LOOP_STATS = {"chars": 30000, "lines": 24, "unique_line_ratio": 1.0, "max_line_repeat": 1,
               "ngram8_unique": 0.01, "ngram20_unique": 0.01}   # content-level loop (traces.py)


def _degen_pair(tmp_path):
    """One EOS'd loop (10s), one truncated loop (80s), one clean row (10s), 100s total.
    Broad share = 90%; the narrow, persisted share = 10%."""
    mdir = tmp_path / "M"
    mdir.mkdir(parents=True, exist_ok=True)
    rows = [
        {"id": 1, "sample": 0, "prompt_tokens": 48, "completion_tokens": 2400,
         "finish_reason": "stop", "thinking_budget": 81920, "wall_s": 10.0,
         "reasoning_stats": _LOOP_STATS},
        {"id": 2, "sample": 0, "prompt_tokens": 48, "completion_tokens": 65489,
         "finish_reason": "length", "thinking_budget": 81920, "wall_s": 80.0,
         "reasoning_stats": _LOOP_STATS},
        {"id": 3, "sample": 0, "prompt_tokens": 48, "completion_tokens": 300,
         "finish_reason": "stop", "thinking_budget": 81920, "wall_s": 10.0},
    ]
    (mdir / "mbppplus.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    (mdir / "mbppplus.score.json").write_text(json.dumps({
        "acc": 0.66, "acc_strict": 0.33, "conv_rate": 2 / 3, "loop_ids": [2],
        "n_degenerate_eosed": 1, "degenerate_wall_share": 0.10}))
    return mdir


def test_scoreboard_reports_BOTH_degeneracy_definitions_under_distinct_keys(tmp_path, monkeypatch):
    sb = _load_sb()
    _degen_pair(tmp_path)
    monkeypatch.setattr(sb.paths, "default_results_root", lambda: tmp_path)

    rec = sb.collect()["M"]["mbppplus"]
    assert rec["degen_all"] == 2, "the broad count is every row with a loop trace"
    assert rec["degen_all_wall_pct"] == pytest.approx(90.0)
    assert rec["degen_eosed_wall_pct"] == pytest.approx(10.0), (
        "the narrow, PERSISTED share must be reported as itself, not recomputed or dropped")


def test_scoreboard_COLUMN_NAMES_say_which_degeneracy_definition_they_are(tmp_path, monkeypatch,
                                                                         capsys):
    """A cell is read on its header. `degenWall%` alone gave two ~10x-apart measures one name."""
    sb = _load_sb()
    _degen_pair(tmp_path)
    monkeypatch.setattr(sb.paths, "default_results_root", lambda: tmp_path)

    sb.main(["--md"])
    header = capsys.readouterr().out.splitlines()[0]
    assert "degenAllWall%" in header and "degenEosedWall%" in header
    assert "| degenWall% |" not in header, "the ambiguous name must be gone, not duplicated"


def test_scoreboard_states_what_each_degeneracy_column_MEANS(tmp_path, monkeypatch, capsys):
    """The names are short; the definitions are not. The emitted sheet is pasted into
    `docs/campaign-results.md`, so the legend has to travel with it."""
    sb = _load_sb()
    _degen_pair(tmp_path)
    monkeypatch.setattr(sb.paths, "default_results_root", lambda: tmp_path)

    sb.main(["--md"])
    out = capsys.readouterr().out
    assert "degenAllWall%" in out and "degenEosedWall%" in out
    assert "EOS" in out and "every row" in out.lower()
