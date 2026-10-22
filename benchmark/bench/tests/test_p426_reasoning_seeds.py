"""P426 B13 / B12: the reasoning ladder takes a task-seed base and an explicit per-draw request seed, both persisted, and
keeps each draw's completion text (the panel's packet). Defaults are unchanged (task seed = ctx * 1000 + trial, no request
seed), so every existing journal's design key and rows stay valid.
"""

import bench.reasoning as R
from bench import run_reasoning
from bench.rowschema import sample_seed

from bench.tests.test_reasoning import FakeSampler


class RecordingDriver:
    def __init__(self):
        self.params = []

    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        self.params.append(dict(params))
        return {
            "content": f"ANSWER: none ({len(self.params)})",
            "completion_tokens": 10,
            "finish_reason": "stop",
            "decode_tps": 50.0,
            "wall_s": 1.0,
        }


def _ladder(driver, **kw):
    return R.run_reasoning_ladder(
        driver,
        "m",
        4.0,
        model_pid=None,
        params=dict(temperature=0.5, thinking_budget=1000),
        grid=(2000,),
        threshold=0.0,
        samples=3,
        chain_len=2,
        sampler_factory=FakeSampler,
        **kw,
    )


def test_the_task_and_request_seeds_are_explicit_and_persisted():
    driver = RecordingDriver()
    rows = _ladder(driver, task_seed_base=128000003, request_seed_base=426)[0]["rows"]
    assert [r["seed"] for r in rows] == [128000003, 128000004, 128000005]
    want = [sample_seed(f"reasoning:{s}", 0, 426) for s in (128000003, 128000004, 128000005)]
    assert [p["seed"] for p in driver.params] == want
    assert [r["sampler_seed"] for r in rows] == want
    assert [r["content"] for r in rows] == [f"ANSWER: none ({i})" for i in (1, 2, 3)]


def test_the_defaults_are_unchanged():
    driver = RecordingDriver()
    rows = _ladder(driver)[0]["rows"]
    assert [r["seed"] for r in rows] == [2000000, 2000001, 2000002]
    assert all("seed" not in p for p in driver.params)
    assert all(r["sampler_seed"] is None for r in rows)


def test_the_cli_takes_both_bases_into_the_design_key():
    args = run_reasoning.build_parser().parse_args(
        ["--model", "m", "--sampling-profile", "deployed", "--task-seed-base", "128000003",
         "--request-seed-base", "426"]
    )
    assert (args.task_seed_base, args.request_seed_base) == (128000003, 426)
    design = run_reasoning.base_design_of(args, (128000,), dict(temperature=0.5))
    assert design["task_seed_base"] == 128000003 and design["request_seed_base"] == 426
    plain = run_reasoning.build_parser().parse_args(["--model", "m", "--sampling-profile", "deployed"])
    assert "task_seed_base" not in run_reasoning.base_design_of(plain, (128000,), {})
