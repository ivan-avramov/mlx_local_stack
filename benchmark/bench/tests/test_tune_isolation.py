"""Isolation invariant (D3 spec item 6): loading rows for (model, bench) WITHOUT a tune must
NEVER pick up `<bench>.<tune>.jsonl` files. A `.kv4` row silently pooled into the deployed
baseline is the exact defect class the tune-encoding migration exists to end.

Covers the two seams that read rows by (model, bench): `generate.done_ids`/`done_keys` (resume)
and `grade._rows` (grading). Both resolve through `generate.result_path`, which is a single
deterministic join — never a glob — so a tune infix cannot leak in as long as that stays true.
"""
import json

import bench.generate as G
import bench.grade as GR


def _write(tmp_path, model, bench, tune, rows):
    p = G.result_path(model, bench, tune=tune)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def test_done_ids_without_tune_ignores_a_tuned_sibling_file(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    _write(tmp_path, "m", "humanevalplus", None, [{"id": "HumanEval/0"}])
    _write(tmp_path, "m", "humanevalplus", "kv4", [{"id": "HumanEval/0"},
                                                    {"id": "HumanEval/1"},
                                                    {"id": "HumanEval/2"}])
    assert G.done_ids("m", "humanevalplus") == {"HumanEval/0"}


def test_done_ids_with_tune_ignores_the_deployed_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    _write(tmp_path, "m", "humanevalplus", None, [{"id": "HumanEval/0"}, {"id": "HumanEval/1"}])
    _write(tmp_path, "m", "humanevalplus", "kv4", [{"id": "HumanEval/9"}])
    assert G.done_ids("m", "humanevalplus", tune="kv4") == {"HumanEval/9"}


def test_done_keys_isolation_holds_too(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    _write(tmp_path, "m", "aime", None, [{"id": "1", "sample": 0}])
    _write(tmp_path, "m", "aime", "t0.3", [{"id": "1", "sample": 0}, {"id": "2", "sample": 0}])
    assert G.done_keys("m", "aime") == {("1", 0)}
    assert G.done_keys("m", "aime", tune="t0.3") == {("1", 0), ("2", 0)}


def test_grade_rows_without_tune_ignores_a_tuned_sibling_file(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    _write(tmp_path, "m", "humanevalplus", None, [{"id": "HumanEval/0", "sample": 0}])
    _write(tmp_path, "m", "humanevalplus", "kv4",
           [{"id": "HumanEval/0", "sample": 0}, {"id": "HumanEval/1", "sample": 0}])
    rows = GR._rows("m", "humanevalplus")
    assert {r["id"] for r in rows} == {"HumanEval/0"}


def test_grade_rows_with_tune_ignores_the_deployed_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    _write(tmp_path, "m", "humanevalplus", None, [{"id": "HumanEval/0", "sample": 0}])
    _write(tmp_path, "m", "humanevalplus", "kv4",
           [{"id": "HumanEval/7", "sample": 0}])
    rows = GR._rows("m", "humanevalplus", tune="kv4")
    assert {r["id"] for r in rows} == {"HumanEval/7"}


def test_build_queue_resume_never_pools_a_tuned_sibling(tmp_path, monkeypatch):
    """build_queue's `done` lookup must key off the SAME (model, bench, tune) result_path as the
    generation loop appends to, or a resumed deployed-tune run would skip items it never actually
    generated (they only exist under a tune infix)."""
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    _write(tmp_path, "m", "aime", "kv4", [{"id": "1", "sample": 0}])
    monkeypatch.setattr("bench.benchmarks.load",
                        lambda name, limit, seed: [{"id": "1"}, {"id": "2"}])
    queue, counts = G.build_queue(["m"], ["aime"], {}, seed=0)
    ids_queued = {it["id"] for _m, _b, it, _s in queue}
    assert ids_queued == {"1", "2"}, "the .kv4.jsonl row must not be read as already-done"


def test_build_queue_with_a_tune_resumes_against_the_tuned_file_not_the_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    _write(tmp_path, "m", "aime", None, [{"id": "1", "sample": 0}])           # deployed baseline
    _write(tmp_path, "m", "aime", "kv4", [{"id": "1", "sample": 0}])          # kv4 already did item 1
    monkeypatch.setattr("bench.benchmarks.load",
                        lambda name, limit, seed: [{"id": "1"}, {"id": "2"}])
    queue, counts = G.build_queue(["m"], ["aime"], {}, seed=0, tune="kv4")
    ids_queued = {it["id"] for _m, _b, it, _s in queue}
    assert ids_queued == {"2"}, "resume under a tune must consult the TUNED file, not the baseline"
