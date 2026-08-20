"""`--samples k`: queue construction, resume identity, and per-sample seeding.

Three properties, each of which silently breaks the reliability metric if wrong:

1. ORDERING. A run is interruptible at any time, so a stopped prefix must be a BALANCED
   measurement. Samples are therefore the OUTERMOST loop: the queue completes a full sweep of
   every item at sample 0 before any item reaches sample 1. The failure mode of the other
   ordering is a partial run holding 3 samples of item 1 and nothing of items 2..15 — which
   reports a reliability number computed from one item.

2. RESUME IDENTITY. `done_ids` keys on the item id, so with k>1 it would consider an item
   finished after one sample. Resume keys on (id, sample). A v1 row (no `sample`) counts as
   sample 0 and must NOT be regenerated.

3. SEEDS. Measured against the live server: unseeded draws are byte-identical, so each sample
   MUST carry a distinct seed or k rows are k copies. See bench/rowschema.py.
"""
import bench.benchmarks as B
import bench.client as C
import bench.generate as G
import bench.rowschema as RS

from .conftest import probe_result


def _items(n):
    return [{"id": f"i{j}", "prompt": "p"} for j in range(n)]


# --------------------------------------------------------------------- queue construction
def test_queue_emits_one_entry_per_item_and_sample(monkeypatch, tmp_results):
    monkeypatch.setattr(B, "load", lambda b, lim, seed: _items(3))
    queue, counts = G.build_queue(["m"], ["aime"], {}, 0, samples=3)
    assert len(queue) == 9
    assert {(it["id"], s) for _m, _b, it, s in queue} == {(f"i{j}", s) for j in range(3) for s in range(3)}


def test_samples_are_the_outermost_loop_so_a_stopped_prefix_is_balanced(monkeypatch, tmp_results):
    monkeypatch.setattr(B, "load", lambda b, lim, seed: _items(4))
    queue, _ = G.build_queue(["m"], ["aime"], {}, 0, samples=2)
    first_sweep = [s for _m, _b, _it, s in queue[:4]]
    assert first_sweep == [0, 0, 0, 0], \
        "the first N entries must be sample 0 of every item, not k samples of item 1"
    assert [s for _m, _b, _it, s in queue[4:]] == [1, 1, 1, 1]


def test_default_samples_is_one_and_shape_is_unchanged(monkeypatch, tmp_results):
    monkeypatch.setattr(B, "load", lambda b, lim, seed: _items(2))
    queue, _ = G.build_queue(["m"], ["aime"], {}, 0)
    assert [s for _m, _b, _it, s in queue] == [0, 0]


def test_model_order_still_finishes_one_model_at_a_time(monkeypatch, tmp_results):
    monkeypatch.setattr(B, "load", lambda b, lim, seed: _items(2))
    queue, _ = G.build_queue(["m1", "m2"], ["aime"], {}, 0, samples=2, order="model")
    assert [m for m, _b, _it, _s in queue] == ["m1"] * 4 + ["m2"] * 4
    # ...and within a model, samples are still the outer loop.
    assert [s for _m, _b, _it, s in queue[:4]] == [0, 0, 1, 1]


# --------------------------------------------------------------------- resume identity
def test_done_keys_reads_id_and_sample(write_rows):
    write_rows("m", "aime", [{"id": "a", "sample": 0}, {"id": "a", "sample": 2}])
    assert G.done_keys("m", "aime") == {("a", 0), ("a", 2)}


def test_a_v1_row_counts_as_sample_zero_only(write_rows, monkeypatch):
    """THE compat case: existing per-box files are all v1. --samples 3 must add samples 1 and 2
    and leave the already-generated sample 0 alone."""
    write_rows("m", "aime", [{"id": "i0", "content": "old"}])       # no `sample` key
    monkeypatch.setattr(B, "load", lambda b, lim, seed: _items(1))
    queue, _ = G.build_queue(["m"], ["aime"], {}, 0, samples=3)
    assert [s for _m, _b, _it, s in queue] == [1, 2]


def test_errored_rows_are_retried_per_key(write_rows, monkeypatch):
    write_rows("m", "aime", [{"id": "i0", "sample": 0, "error": "boom"},
                             {"id": "i0", "sample": 1}])
    monkeypatch.setattr(B, "load", lambda b, lim, seed: _items(1))
    queue, _ = G.build_queue(["m"], ["aime"], {}, 0, samples=2)
    assert [s for _m, _b, _it, s in queue] == [0], "the errored sample retries, the good one does not"


def test_done_ids_still_works_for_existing_callers(write_rows):
    write_rows("m", "aime", [{"id": "a", "sample": 0}, {"id": "b"}])
    assert G.done_ids("m", "aime") == {"a", "b"}


# --------------------------------------------------------------------- the run loop
def test_run_writes_sample_index_and_seed_on_every_row(monkeypatch, tmp_results):
    monkeypatch.setattr(B, "load", lambda b, lim, seed: _items(2))
    monkeypatch.setattr(C, "preload", lambda m, **k: 0.0)
    seen = []

    def fake_probe(model, messages, params, timeout=3600, tools=None):
        seen.append(params.get("seed"))
        return probe_result()

    monkeypatch.setattr(C, "probe", fake_probe)
    G.run(["m"], ["aime"], {}, samples=2)

    rows = [__import__("json").loads(l) for l in G.result_path("m", "aime").read_text().splitlines()]
    assert len(rows) == 4
    assert {RS.row_key(r) for r in rows} == {("i0", 0), ("i0", 1), ("i1", 0), ("i1", 1)}
    assert all(r["schema_version"] == RS.SCHEMA_VERSION for r in rows)
    # every row records the seed it was drawn under, and they are all distinct
    assert len({r["sampler_seed"] for r in rows}) == 4
    assert all(r["sampler_seed"] == RS.sample_seed(r["id"], r["sample"]) for r in rows)


def test_run_sends_a_distinct_seed_per_sample_to_the_server(monkeypatch, tmp_results):
    """Without this the server returns byte-identical text for every sample (measured), so
    reliability would read as perfect regardless of the model."""
    monkeypatch.setattr(B, "load", lambda b, lim, seed: _items(1))
    monkeypatch.setattr(C, "preload", lambda m, **k: 0.0)
    sent = []

    def fake_probe(model, messages, params, timeout=3600, tools=None):
        sent.append(params.get("seed"))
        return probe_result()

    monkeypatch.setattr(C, "probe", fake_probe)
    G.run(["m"], ["aime"], {}, samples=3)
    assert len(sent) == 3 and len(set(sent)) == 3
    assert None not in sent, "a request without a seed gets a deterministic default -> identical draws"


def test_an_explicit_seed_override_wins_and_is_recorded(monkeypatch, tmp_results):
    """An operator pinning --seed-base must be able to shift the whole draw set (e.g. to get a
    fresh independent replication of an already-generated run)."""
    monkeypatch.setattr(B, "load", lambda b, lim, seed: _items(1))
    monkeypatch.setattr(C, "preload", lambda m, **k: 0.0)
    monkeypatch.setattr(C, "probe", lambda *a, **k: probe_result())
    G.run(["m"], ["aime"], {}, samples=1, seed_base=99)
    row = __import__("json").loads(G.result_path("m", "aime").read_text().splitlines()[0])
    assert row["sampler_seed"] == RS.sample_seed("i0", 0, base=99)
    assert row["seed_base"] == 99


# --- O35 (ruled 2026-08-20): a probe-timeout error row is a DNF, counted DONE on resume ---
# Seeds derive from (item, sample), so a runaway retries byte-identically: Mbpp/306 burned a
# second full 3600s probe-timeout on resume plus ~13 min of server-side drain per abandonment.

def _err_row(id_, sample=0, **extra):
    row = {"id": id_, "sample": sample, "bench": "humanevalplus",
           "model": "m-4bit", "error": "timed out"}
    row.update(extra)
    return row


def test_probe_timeout_error_rows_count_as_done_on_resume(write_rows):
    write_rows("m-4bit", "humanevalplus", [
        _err_row("HumanEval/1"),                                   # plain error -> retried
        _err_row("HumanEval/2", error_kind="probe_timeout", wall_s=3600.1),  # DNF -> done
        {"id": "HumanEval/3", "sample": 0, "content": "ok"},       # normal row -> done
    ])
    keys = G.done_keys("m-4bit", "humanevalplus")
    assert ("HumanEval/2", 0) in keys
    assert ("HumanEval/3", 0) in keys
    assert ("HumanEval/1", 0) not in keys
    ids = G.done_ids("m-4bit", "humanevalplus")
    assert ids == {"HumanEval/2", "HumanEval/3"}


def test_error_kind_classifies_only_a_full_probe_timeout():
    # threshold is 0.9x the configured probe timeout: a fast failure (connect refused,
    # transient network) stays retryable; only an elapsed-to-the-cap probe is a DNF
    assert G.error_kind(3600.0, 3600) == "probe_timeout"
    assert G.error_kind(3240.0, 3600) == "probe_timeout"   # exactly 0.9x
    assert G.error_kind(12.0, 3600) is None
    assert G.error_kind(3600.0, None) is None
    assert G.error_kind(3600.0, 0) is None
