"""LCB generation must NOT hold the full dataset (880 problems + large private test cases,
~10GB RAM co-resident with the model). _load_lcb uses a prompt-only cache (id + prompt +
raw question_content/starter_code, no test cases); on a cache hit it never loads the heavy
dataset. Test cases are only loaded at grade time (off-box).
"""
import json

import bench.benchmarks as B


def test_load_lcb_uses_prompt_cache_without_full_dataset(tmp_path, monkeypatch):
    cache = tmp_path / "lcb_prompts.json"
    cache.write_text(json.dumps([
        {"id": "p1", "prompt": "solve A", "meta": {"platform": "atcoder",
                                                   "question_content": "A", "starter_code": ""}},
        {"id": "p2", "prompt": "solve B", "meta": {"platform": "leetcode",
                                                   "question_content": "B", "starter_code": "class S:"}},
    ]))
    monkeypatch.setattr(B, "_lcb_prompt_cache_path", lambda: str(cache))

    # If the cache is used, the heavy loader is never called. Make it explode to prove it.
    import sys
    boom = type(sys)("lcb_runner.benchmarks.code_generation")
    def _raise(*a, **k):
        raise AssertionError("load_code_generation_dataset must NOT be called on a cache hit")
    boom.load_code_generation_dataset = _raise
    monkeypatch.setitem(sys.modules, "lcb_runner.benchmarks.code_generation", boom)

    items = B._load_lcb(limit=2, seed=0)
    assert {i["id"] for i in items} == {"p1", "p2"}
    # raw fields preserved for building official-template prompts
    p2 = [i for i in items if i["id"] == "p2"][0]
    assert p2["meta"]["starter_code"] == "class S:"
