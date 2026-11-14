"""M76 B5: `run_retrieval` seeding (spec v1.1 §A5): `--task-seed-base` / `--request-seed-base`, mirroring `run_reasoning`'s B13 seeding;
without them behaviour is unchanged. Class of each test is in the comment above it: (a) reproduces a failure the spec fixes,
(b) preserves an invariant, (c) exercises new behaviour.

Surface assumed: `bench.retrieval.run_retrieval_ladder(..., task_seed_base=None, request_seed_base=None)` (the kwarg names of
`bench.reasoning.run_reasoning_ladder`), a per-draw request seed in the request params as `seed` and in the row as `sampler_seed`,
and the two argparse flags on `bench.run_retrieval`.
"""
from __future__ import annotations

import contextlib

import pytest

from bench import retrieval
from bench.retrieval import build_context, make_question, run_retrieval_ladder

CPT = 4.0
CTX = 8000
PARAMS = {"temperature": 0.5, "max_tokens": 100}


class FakeDriver:
    def __init__(self):
        self.calls = []

    def complete(self, model, messages, params, timeout=None):
        self.calls.append(dict(messages=messages, params=dict(params)))
        return {"content": "", "prompt_tokens": 1, "completion_tokens": 1, "finish_reason": "stop", "raw_timings": {}}


def run(samples=2, grid=(CTX,), **kw):
    d = FakeDriver()
    recs = run_retrieval_ladder(d, "m", CPT, model_pid=None, params=dict(PARAMS), grid=grid, samples=samples,
                                sampler_factory=lambda pid: contextlib.nullcontext(), **kw)
    return d, recs


# (b) default: seed = ctx * 1000 + trial, the prompt is the one `build_context` makes for it, no request seed
def test_default_seeding_is_unchanged():
    d, recs = run()
    for trial, call in enumerate(d.calls):
        ctx, needles = build_context(CTX, CPT, seed=CTX * 1000 + trial)
        assert call["messages"][0]["content"] == ctx + "\n\n" + make_question(needles)
        assert "seed" not in call["params"]
    assert [r["seed"] for r in recs[0]["rows"]] == [CTX * 1000, CTX * 1000 + 1]
    assert all("sampler_seed" not in r or r["sampler_seed"] is None for r in recs[0]["rows"])


# (b) passing None explicitly is the default
def test_explicit_none_is_the_default():
    a, ra = run()
    b, rb = run(task_seed_base=None, request_seed_base=None)
    assert [c["messages"] for c in a.calls] == [c["messages"] for c in b.calls]
    assert [c["params"] for c in a.calls] == [c["params"] for c in b.calls]


# (c) task_seed_base: the draw's task seed is base + trial, the prompt is built from it
def test_task_seed_base_sets_the_prompt_seed():
    d, recs = run(task_seed_base=777000)
    assert [r["seed"] for r in recs[0]["rows"]] == [777000, 777001]
    for trial, call in enumerate(d.calls):
        ctx, needles = build_context(CTX, CPT, seed=777000 + trial)
        assert call["messages"][0]["content"] == ctx + "\n\n" + make_question(needles)


# (c) same seeds -> same prompts (across runs); other seeds -> other prompts
def test_same_seeds_same_prompts_other_seeds_other_prompts():
    a, _ = run(task_seed_base=5, request_seed_base=9)
    b, _ = run(task_seed_base=5, request_seed_base=9)
    c, _ = run(task_seed_base=6, request_seed_base=9)
    assert [x["messages"] for x in a.calls] == [x["messages"] for x in b.calls]
    assert [x["params"] for x in a.calls] == [x["params"] for x in b.calls]
    assert a.calls[0]["messages"] != c.calls[0]["messages"]
    assert a.calls[1]["messages"] == c.calls[0]["messages"]        # task seed 6 is trial 1 of base 5


# (c) request_seed_base: an explicit sampler seed per draw, deterministic, distinct per draw, recorded as the row's sampler_seed
def test_request_seed_base_seeds_each_draw():
    a, ra = run(samples=3, task_seed_base=5, request_seed_base=9)
    b, rb = run(samples=3, task_seed_base=5, request_seed_base=9)
    seeds = [c["params"]["seed"] for c in a.calls]
    assert all(isinstance(s, int) for s in seeds)
    assert seeds == [c["params"]["seed"] for c in b.calls]
    assert len(set(seeds)) == 3
    assert [r["sampler_seed"] for r in ra[0]["rows"]] == seeds
    other, _ = run(samples=3, task_seed_base=5, request_seed_base=10)
    assert [c["params"]["seed"] for c in other.calls] != seeds


# (c) the other params are forwarded verbatim next to the seed
def test_request_seed_leaves_the_other_params_alone():
    d, _ = run(task_seed_base=5, request_seed_base=9)
    assert {k: v for k, v in d.calls[0]["params"].items() if k != "seed"} == PARAMS


# (c) the request seed depends on the draw's task seed, not on the ladder position: the same task seed gets the same sampler seed
def test_request_seed_follows_the_task_seed():
    a, _ = run(samples=2, task_seed_base=5, request_seed_base=9)
    b, _ = run(samples=1, task_seed_base=6, request_seed_base=9)
    assert a.calls[1]["params"]["seed"] == b.calls[0]["params"]["seed"]


# (c) the CLI exposes both flags
def test_cli_exposes_the_seed_flags(capsys):
    from bench import run_retrieval

    with pytest.raises(SystemExit) as exc:
        run_retrieval.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--task-seed-base" in out and "--request-seed-base" in out


# (c) mirroring run_reasoning: a task-seed base needs a single-rung grid (else seeds repeat across rungs): refused at parse time
def test_cli_task_seed_base_needs_a_single_rung_grid():
    from bench import run_retrieval

    with pytest.raises(SystemExit) as exc:
        run_retrieval.main(["--model", "m", "--sampling-profile", "deployed", "--grid", "8000,32000", "--task-seed-base", "5"])
    assert exc.value.code == 2


# (b) the capacity ladder's consumer of build_context is untouched (seed default 0)
def test_build_context_default_seed_unchanged():
    assert build_context(1000, 4.0)[1] == build_context(1000, 4.0, seed=0)[1]
    assert retrieval.DEPTHS == (0.1, 0.3, 0.5, 0.7, 0.9)
