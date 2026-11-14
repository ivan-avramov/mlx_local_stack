"""M76 B5 (A5): `bench.run_retrieval` takes `--task-seed-base` / `--request-seed-base` (mirroring `run_reasoning`'s P426 B13
seeding): the same seeds give the same prompts and the same explicit per-draw request seed; without them every request, row and
the CLI's design are exactly today's."""

import pytest

import bench.retrieval as R
from bench import run_retrieval
from bench.rowschema import sample_seed

from bench.tests.test_reasoning import FakeSampler


class RecordingDriver:
    def __init__(self, session=True):
        self.calls = []
        self.session = session

    def complete(self, model, messages, params, timeout=3600):
        self.calls.append((messages[0]["content"], dict(params), params))
        out = {"content": "codes", "prompt_tokens": 100 + len(self.calls), "completion_tokens": 9, "finish_reason": "stop",
               "prefill_s": 1.0, "prefill_tps": 1.0, "decode_tps": 2.0, "wall_s": 3.0, "raw_timings": {}}
        if self.session:
            out["session_id"] = f"sid-{len(self.calls)}"
        return out


def _ladder(driver, params=None, **kw):
    return R.run_retrieval_ladder(driver, "m", 4.0, model_pid=None, params=params if params is not None else dict(temperature=0.5),
                                  grid=(2000,), samples=2, sampler_factory=FakeSampler, **kw)


def test_seeded_draws_are_explicit_and_recorded():
    d = RecordingDriver()
    rows = _ladder(d, task_seed_base=777, request_seed_base=7605)[0]["rows"]
    assert [r["seed"] for r in rows] == [777, 778]
    want = [sample_seed(f"retrieval:{s}", 0, 7605) for s in (777, 778)]
    assert [c[1]["seed"] for c in d.calls] == want
    assert [r["sampler_seed"] for r in rows] == want
    assert [r["session_id"] for r in rows] == ["sid-1", "sid-2"]
    assert [r["content"] for r in rows] == ["codes", "codes"]


def test_same_seeds_same_prompts_and_other_seeds_differ():
    a, b, c = RecordingDriver(), RecordingDriver(), RecordingDriver()
    _ladder(a, task_seed_base=5, request_seed_base=1)
    _ladder(b, task_seed_base=5, request_seed_base=1)
    _ladder(c, task_seed_base=6, request_seed_base=1)
    assert [x[0] for x in a.calls] == [x[0] for x in b.calls]
    assert [x[1] for x in a.calls] == [x[1] for x in b.calls]
    assert a.calls[0][0] != c.calls[0][0]


def test_task_seed_base_alone_seeds_the_needles_only():
    d = RecordingDriver()
    rows = _ladder(d, task_seed_base=9)[0]["rows"]
    assert [r["seed"] for r in rows] == [9, 10]
    assert all("seed" not in c[1] for c in d.calls)
    assert all(r["sampler_seed"] is None for r in rows)


def test_defaults_unchanged():
    d = RecordingDriver()
    params = dict(temperature=0.5)
    rec = _ladder(d, params=params)[0]
    rows = rec["rows"]
    assert [r["seed"] for r in rows] == [2000000, 2000001]
    assert all(c[2] is params for c in d.calls)                   # the profile params object itself, as today
    assert all(set(r) == {"trial", "seed", "hits", "prompt_tokens", "completion_tokens", "finish_reason", "prefill_s",
                          "prefill_tps", "decode_tps", "wall_s", "draft", "error"} for r in rows)
    ctx, _ = R.build_context(2000, 4.0, seed=2000000)
    assert d.calls[0][0].startswith(ctx)


def test_cli_flags_and_defaults():
    ap = run_retrieval.build_parser()
    args = ap.parse_args(["--model", "m", "--sampling-profile", "deployed", "--grid", "131072", "--samples", "1",
                          "--task-seed-base", "11", "--request-seed-base", "22"])
    assert (args.task_seed_base, args.request_seed_base) == (11, 22)
    assert run_retrieval.ladder_seeds(args) == dict(task_seed_base=11, request_seed_base=22)
    plain = ap.parse_args(["--model", "m", "--sampling-profile", "deployed"])
    assert (plain.task_seed_base, plain.request_seed_base) == (None, None)
    assert run_retrieval.ladder_seeds(plain) == {}
    assert run_retrieval.seeded_runtime(plain) == {}
    assert run_retrieval.seeded_runtime(args) == dict(task_seed_base=11, request_seed_base=22)


def test_cli_refuses_task_seed_base_on_a_multi_rung_grid():
    with pytest.raises(SystemExit):
        run_retrieval.main(["--model", "m", "--sampling-profile", "deployed", "--grid", "131072,159744",
                            "--task-seed-base", "1"])
