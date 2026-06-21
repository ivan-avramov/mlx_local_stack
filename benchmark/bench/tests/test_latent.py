"""TDD tests for bench.latent — NoLiMa-style latent-association reasoning probe."""
import re

import bench.latent as LT


def test_associations_and_names_nonempty_and_disjoint():
    assert len(LT.ASSOCIATIONS) >= 12
    assert len(LT.NAMES) >= 12
    # each association is (needle_template_with_{n}, question)
    for needle, q in LT.ASSOCIATIONS:
        assert "{n}" in needle and isinstance(q, str) and q


def test_build_latent_embeds_name_and_asks_question():
    ctx, name, q = LT.build_latent(4000, chars_per_token=4.0, seed=2)
    assert name in LT.NAMES
    assert re.search(rf"\b{re.escape(name)}\b", ctx)   # the needle (with the name) is in context
    assert "ANSWER:" in q


def test_build_latent_filler_does_not_leak_other_names():
    ctx, name, _ = LT.build_latent(4000, 4.0, seed=5)
    others = [nm for nm in LT.NAMES if nm != name]
    # the answer name appears; no OTHER candidate name appears (so the answer is unambiguous)
    assert all(not re.search(rf"\b{re.escape(o)}\b", ctx) for o in others)


def test_build_latent_deterministic():
    assert LT.build_latent(3000, 4.0, seed=9) == LT.build_latent(3000, 4.0, seed=9)


def test_score_latent_answer_tag_and_wholeword():
    assert LT.score_latent("ANSWER: Mara", "Mara") == 1.0
    assert LT.score_latent("I think it is Mara.", "Mara") == 1.0
    assert LT.score_latent("ANSWER: Theo", "Mara") == 0.0
    assert LT.score_latent("Marabou stork", "Mara") == 0.0   # whole-word only
    assert LT.score_latent("", "Mara") == 0.0


class _FakeSampler:
    def __init__(self, pid=None, interval=0.2):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class _OKDriver:
    def complete(self, model, messages, params, timeout=3600):
        return {"content": "x", "prompt_tokens": 100, "decode_tps": 1.0, "peak_mem_gb": 1.0,
                "prefill_s": 0.1, "prefill_tps": 1, "wall_s": 0.1}


def test_latent_ladder_stops_at_cliff(monkeypatch):
    calls = {"n": 0}

    def stub(resp, name):
        calls["n"] += 1
        return 1.0 if calls["n"] <= 2 else 0.0

    monkeypatch.setattr(LT, "score_latent", stub)
    recs = LT.run_latent_ladder(_OKDriver(), "m", 4.0, model_pid=1, params={},
                                grid=(1000, 2000, 3000), threshold=0.85, samples=2,
                                sampler_factory=_FakeSampler)
    assert [r["ctx"] for r in recs] == [1000, 2000]
    assert recs[0]["accuracy"] == 1.0 and recs[1]["accuracy"] == 0.0


def test_latent_ladder_auto_extends_past_grid(monkeypatch):
    monkeypatch.setattr(LT, "score_latent", lambda resp, name: 1.0)
    recs = LT.run_latent_ladder(_OKDriver(), "m", 4.0, model_pid=1, params={},
                                grid=(1000,), threshold=0.85, samples=1,
                                extend_step=1000, max_ctx=3000, sampler_factory=_FakeSampler)
    assert [r["ctx"] for r in recs] == [1000, 2000, 3000]
