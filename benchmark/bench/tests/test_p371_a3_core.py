"""P371 phase 2b, plan 4 A3 (runner side) THROUGH THE CORE: the M64-style configuration (`worker_receipts: required`)
with the neutral adapter and a `FakeReceiptSource` that plays the worker. The per-item order is
AttemptContext -> env -> (barrier ready) -> receipts.start -> spawn -> client exit -> receipts.fence -> classes ->
one-to-one join; every failure aborts the chain's attempt (no row); `WorkerMismatch` carries the `worker_crash` cause."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bench import arm_runner
from bench import rowschema
from bench import worker_receipts as wr
from bench.tests.arm_neutral import NeutralArm, NeutralCorpus
from bench.tests.p371_world import evidence, manifest, rows, run_core, world      # noqa: F401  (fixture)

SEED = rowschema.sample_seed("fake/one", 0, 77)
TOOLS = "ab" * 32


class Played(wr.FakeReceiptSource):
    """The test plays the worker: the scripted receipts are admitted when the runner fences (after the client exit)."""

    def __init__(self, worker, admits=None, *, before=None):
        super().__init__(worker)
        self.admits = admits
        self.before = before
        self.sizes_at_start = None
        self.evidence_dir = None

    def start(self, ctx):
        if self.evidence_dir is not None:
            self.sizes_at_start = [p.stat().st_size for p in self.evidence_dir.rglob("*.events.jsonl")]
        return super().start(ctx)

    def fence(self, ctx):
        seed = rowschema.sample_seed(ctx.slot, 0, 77)
        admits = [dict(cls="task", seed=seed)] * 2 if self.admits is None else self.admits
        for kw in admits:
            self.admit(**kw)
        if self.before:
            self.before(self)
        return super().fence(ctx)


def source(world, admits=None, **kw):
    s = Played(dict(pid=world.worker["pid"], create_time=world.worker["create_time"]), admits, **kw)
    s.evidence_dir = world.tmp / "neutral_evidence"
    return s


REQUIRED = dict(worker_receipts="required")


def go(world, src, adapter=None, **kw):
    return run_core(world, adapter=adapter, receipts=src, evidence_=evidence(**REQUIRED), **kw)


def resolve(world, portable):
    return Path(portable.replace("$STACK_WORKDIR", str(world.tmp)))


class Classed(NeutralArm):
    """A neutral client that classifies its requests however the test wants (task / compaction / auxiliary)."""

    def __init__(self, p, classes):
        super().__init__(p)
        self.classes = classes

    def request_classes(self, stream, transcript):
        return [dict(c) for c in self.classes]


class Headed(NeutralArm):
    supports_attempt_header = True


# ---------------------------------------------------------------- the happy path and its evidence
def test_required_receipts_run_through_the_core_and_write_the_receipt_file(world):
    src = source(world)
    assert go(world, src)[0] == 0
    (row,) = rows(world)
    assert row["token_accounting"] == "receipts" and row["passed"] is True
    path = resolve(world, row["receipts"]["path"])
    assert path.is_file() and path.name.endswith(".receipts.json") and path.parent.name.startswith("rows.")
    assert row["receipts"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    doc = json.loads(path.read_bytes())
    assert doc["attempt_id"] == "fake/one#a1.r0" and len(doc["fence"]["receipts"]) == 2
    assert manifest(world)["runtime"]["evidence_policy"]["worker_receipts"] == "required"


def test_start_precedes_the_spawn_and_the_fence_follows_the_client_exit(world):
    src = source(world)
    go(world, src)
    assert [c[0] for c in src.calls] == ["start", "admit", "admit", "fence"]
    assert src.sizes_at_start == [0]                       # the client had written nothing when the mark was taken
    assert src.calls[0][1] == src.calls[-1][1] == "fake/one#a1.r0"
    (events,) = (world.tmp / "neutral_evidence").rglob("*.events.jsonl")
    assert events.stat().st_size > 0                       # ... and it had by the time the fence ran


def test_task_totals_come_from_the_join_including_a_disconnected_generation(world):
    admits = [dict(cls="task", seed=SEED, completion_tokens=100, prompt_tokens=1000),
              dict(cls="task", seed=SEED, completion_tokens=4000, prompt_tokens=1200, disconnected=True,
                   terminal="client_disconnect")]
    go(world, source(world, admits))
    (row,) = rows(world)
    t = row["task_tokens"]
    assert t["accounting"] == "receipts" and t["receipts"]["completion_tokens"] == 4100
    assert t["receipts"]["prompt_tokens"] == 2200 and t["receipts"]["requests"] == 2
    assert t["gate_completion_tokens"] == row["gate"]["output_tokens_completed"] == 20           # what the client saw
    assert t["completion_tokens"] == 20 and t["compaction_completion_tokens"] == 0


def test_compaction_counts_to_the_task_and_auxiliary_is_reported_apart(world):
    classes = [dict(cls="task"), dict(cls="compaction"), dict(cls="task"), dict(cls="auxiliary")]
    admits = [dict(cls="task", seed=SEED), dict(cls="compaction", seed=SEED, completion_tokens=300),
              dict(cls="task", seed=SEED), dict(cls="auxiliary", seed=SEED, completion_tokens=7)]
    go(world, source(world, admits), adapter=Classed(world.host, classes))
    (row,) = rows(world)
    receipts = row["task_tokens"]["receipts"]
    assert receipts["requests"] == 3 and receipts["completion_tokens"] == 100 + 300 + 100
    assert receipts["by_class"]["auxiliary"]["completion_tokens"] == 7 and receipts["by_class"]["compaction"]["requests"] == 1


def test_a_headerless_adapter_joins_by_fence_and_order(world):
    adapter = NeutralArm(world.host)
    assert adapter.supports_attempt_header is False
    assert go(world, source(world), adapter=adapter)[0] == 0
    assert adapter.overlay_attempts == [None, None]        # discovery + item: no header asked of a headerless client


def test_a_header_supporting_adapter_gets_the_attempt_in_its_overlay_and_must_match(world):
    adapter = Headed(world.host)
    admits = [dict(cls="task", seed=SEED, header="fake/one#a1.r0"), dict(cls="task", seed=SEED, header="fake/one#a1.r0")]
    assert go(world, source(world, admits), adapter=adapter)[0] == 0
    ctx = adapter.overlay_attempts[-1]
    assert ctx.attempt_id == "fake/one#a1.r0" and adapter.env_attempts[-1] == ctx
    assert adapter.overlay_attempts[0] is None                   # discovery runs no attempt


def test_the_header_is_asked_only_when_receipts_are_required(world):
    adapter = Headed(world.host)
    assert run_core(world, adapter=adapter)[0] == 0                         # evidence policy: absent
    assert adapter.overlay_attempts == [None, None] and adapter.env_attempts[-1].attempt_id == "fake/one#a1.r0"


def test_the_attempt_number_and_rerun_index_come_from_the_probe_arguments(world):
    adapter = NeutralArm(world.host)
    run_core(world, adapter=adapter, receipts=source(world), evidence_=evidence(**REQUIRED),
             a=dict(attempt=3, attempt_rerun_index=1))
    assert adapter.env_attempts[-1].attempt_id == "fake/one#a3.r1"


def test_every_item_attempt_gets_its_own_context_marks_and_receipt_file(world):
    adapter = NeutralArm(world.host)
    src = source(world)
    assert run_core(world, adapter=adapter, receipts=src, evidence_=evidence(**REQUIRED),
                    a=dict(items="one,two"))[0] == 0
    assert [c.attempt_id for c in adapter.env_attempts if c.slot != "discovery"] == ["fake/one#a1.r0", "fake/two#a1.r0"]
    assert [c[0] for c in src.calls] == ["start", "admit", "admit", "fence"] * 2
    assert [r["receipts"]["path"].rsplit("/", 1)[1] for r in rows(world)] == ["fake__one.receipts.json",
                                                                              "fake__two.receipts.json"]


# ---------------------------------------------------------------- the join aborts (no row, nothing scored)
def abort_of(world, src, adapter=None, **kw):
    with pytest.raises(SystemExit, match="REFUSED") as exc:
        go(world, src, adapter=adapter, **kw)
    assert rows(world) == []
    return str(exc.value), manifest(world)["transport_abort"]


def test_a_missing_receipt_aborts(world):
    msg, stamp = abort_of(world, source(world, [dict(cls="task", seed=SEED)]))
    assert "only 1 receipts" in msg and "cause" not in stamp
    assert list((world.tmp / "neutral_evidence").rglob("*.receipts.json")), "the fenced evidence stays for diagnosis"


def test_a_duplicate_receipt_aborts(world):
    src = source(world)
    src.duplicate_seqs = {1}
    assert "duplicate" in abort_of(world, src)[0]


def test_a_receipt_finalized_after_the_fence_aborts(world):
    src = source(world)
    src.late_after_fence = 1
    assert "after the fence" in abort_of(world, src)[0]


def test_an_ambiguous_join_aborts(world):
    def tie(s):
        s._receipts[1]["received_mono"] = s._receipts[0]["received_mono"]

    assert "not ordered by timestamp" in abort_of(world, source(world, before=tie))[0]


def test_an_unmatched_extra_receipt_aborts(world):
    src = source(world, [dict(cls="task", seed=SEED)] * 3)
    assert "3 receipts but only 2 requests" in abort_of(world, src)[0]


@pytest.mark.parametrize("classes,admits,why", [
    (None, [dict(cls="task", seed=SEED, tools=False), dict(cls="task", seed=SEED)], "must carry tools"),
    ([dict(cls="task"), dict(cls="compaction")], [dict(cls="task", seed=SEED), dict(cls="task", seed=SEED)],
     "must be tool-less"),
    ([dict(cls="task", tools_sha256=TOOLS), dict(cls="task")], [dict(cls="task", seed=SEED, tools_sha256="cd" * 32),
                                                                 dict(cls="task", seed=SEED)], "tool-set hash"),
])
def test_a_tools_mismatch_per_class_aborts(world, classes, admits, why):
    adapter = Classed(world.host, classes) if classes else None
    assert why in abort_of(world, source(world, admits), adapter=adapter)[0]


def test_a_header_mismatch_or_absence_aborts_for_a_header_supporting_client(world):
    bad = [dict(cls="task", seed=SEED, header="fake/one#a9.r0"), dict(cls="task", seed=SEED, header="fake/one#a1.r0")]
    assert "is not this attempt's" in abort_of(world, source(world, bad), adapter=Headed(world.host))[0]
    none = [dict(cls="task", seed=SEED), dict(cls="task", seed=SEED)]
    assert "carries no X-Bench-Attempt" in abort_of(world, source(world, none), adapter=Headed(world.host))[0]


def test_a_wrong_header_aborts_even_for_a_headerless_adapter(world):
    admits = [dict(cls="task", seed=SEED, header="other#a1.r0"), dict(cls="task", seed=SEED)]
    assert "is not this attempt's" in abort_of(world, source(world, admits))[0]


@pytest.mark.parametrize("fault", ["foreign_receipt", "fence_worker", "start_worker", "receipt_worker"])
def test_another_worker_is_a_worker_crash_incident(world, fault):
    other = dict(pid=999, create_time=5.0)
    src = source(world)
    if fault == "foreign_receipt":
        src.foreign_worker = {2: other}
    elif fault == "fence_worker":
        src.fence_worker = other
    elif fault == "start_worker":
        src.start_worker = other
    else:
        src.fence_receipt_worker = other
    msg, stamp = abort_of(world, src)
    assert stamp["cause"] == "worker_crash"


def test_receipts_from_a_worker_the_probe_did_not_observe_are_a_worker_crash(world):
    other = dict(pid=world.worker["pid"] + 1, create_time=world.worker["create_time"])
    src = Played(other, [dict(cls="task", seed=SEED)] * 2)
    msg, stamp = abort_of(world, src)
    assert stamp["cause"] == "worker_crash"


@pytest.mark.parametrize("override,why", [
    (dict(seed=SEED + 1), "seed"), (dict(thinking_budget=1), "thinking_budget"), (dict(max_tokens=10 ** 7), "max_tokens"),
    (dict(sampling=dict(temperature=0.1, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=1.5)), "sampling"),
])
def test_the_effective_controls_must_equal_the_declared_ones(world, override, why):
    admits = [dict(dict(cls="task", seed=SEED), **override), dict(cls="task", seed=SEED)]
    assert why in abort_of(world, source(world, admits))[0]


def test_the_roles_of_a_request_must_be_the_classes_expected_roles(world):
    src = source(world)
    src.before = lambda s: s._receipts[0].update(roles=["system", "developer"])
    assert "roles" in abort_of(world, src)[0]


def test_join_always_receives_the_mark_and_the_fence(world, monkeypatch):
    seen = {}
    real = wr.join

    def spy(receipts, classified, **kw):
        seen.update(kw)
        return real(receipts, classified, **kw)

    monkeypatch.setattr(wr, "join", spy)
    go(world, source(world))
    assert isinstance(seen["mark"], wr.StartMark) and isinstance(seen["fence"], wr.Fence)
    assert seen["supports_header"] is False and seen["ctx"].attempt_id == "fake/one#a1.r0"
    assert set(seen["controls"]) >= {"task", "compaction", "auxiliary"}
    assert seen["controls"]["task"]["seed"] == SEED and seen["controls"]["task"]["thinking_budget"] == 81920


def test_a_worker_unavailable_mid_item_aborts_without_a_row(world):
    class Down(Played):
        def fence(self, ctx):
            raise wr.ReceiptTransportError("worker receipt endpoint /bench/attempt/fence failed: URLError")

    msg, stamp = abort_of(world, Down(dict(pid=1234, create_time=100)))
    assert "fence failed" in msg


# ---------------------------------------------------------------- absent: unchanged
def test_absent_receipts_leave_the_row_and_the_source_untouched(world):
    src = source(world)
    assert run_core(world, receipts=src)[0] == 0
    (row,) = rows(world)
    assert src.calls == [] and "receipts" not in row and "task_tokens" not in row and row["token_accounting"] == "client"
    assert not list((world.tmp / "neutral_evidence").rglob("*.receipts.json"))


def test_the_row_names_no_opencode_with_receipts_on(world):
    go(world, source(world))
    text = (world.tmp / "rows.jsonl").read_text() + (world.tmp / "rows.manifest.json").read_text()
    assert "opencode" not in text.lower()
    _ = arm_runner
