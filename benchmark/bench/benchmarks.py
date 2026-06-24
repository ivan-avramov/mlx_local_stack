"""Benchmark registry: load items + build prompts. Grading lives in grade.py.

Reasoning benchmarks need only `datasets`. Coding benchmarks need the official
evaluators (`evalplus`, `lcb_runner`) — imported lazily so reasoning works without them.
An Item is: {"id", "prompt", "answer"?, "options"?, "meta"?}.
"""
import random

# Per-benchmark spec: kind, answer type, gated? Sampling/thinking params come from the
# model's production config (see model_params.py), NOT from here.
SPECS = {
    "aime":          {"kind": "reasoning", "answer_type": "int",  "gated": False},
    "math500":       {"kind": "reasoning", "answer_type": "math", "gated": False},
    "gpqa":          {"kind": "reasoning", "answer_type": "mc",   "gated": True},
    "humanevalplus": {"kind": "coding",    "answer_type": "code", "gated": False},
    "mbppplus":      {"kind": "coding",    "answer_type": "code", "gated": False},
    "livecodebench": {"kind": "coding",    "answer_type": "code", "gated": False},
    "ifeval":        {"kind": "instruction", "answer_type": "programmatic", "gated": False},
}

# Pinned LiveCodeBench release window for contamination control + reproducibility.
# Generation and grading MUST use the same release; the id is recorded in the grade output.
LCB_RELEASE = "release_v5"


def _subsample(items: list, limit: int | None, seed: int) -> list:
    """Deterministic, PREFIX-NESTED subset: shuffle once by seed, take the first `limit`.
    So limit=8 is a prefix of limit=30 — escalating tiers (light->mid->heavy) only add new
    items and reuse everything already generated."""
    if not limit or limit >= len(items):
        idx = list(range(len(items)))
        random.Random(seed).shuffle(idx)
        return [items[i] for i in idx]
    idx = list(range(len(items)))
    random.Random(seed).shuffle(idx)
    return [items[i] for i in idx[:limit]]


# ----------------------------------------------------------------- reasoning loaders
def _load_aime(limit, seed):
    from datasets import load_dataset
    items = []
    for tag, ds_id in [("aime24", "HuggingFaceH4/aime_2024"), ("aime25", "yentinglin/aime_2025")]:
        for row in load_dataset(ds_id, split="train"):
            prob = row.get("problem") or row.get("Problem")
            ans = str(row.get("answer") or row.get("Answer")).strip()
            rid = f"{tag}-{row.get('id', row.get('ID'))}"
            items.append({"id": rid, "prompt": prob, "answer": ans})
    return _subsample(items, limit, seed)


def _load_math500(limit, seed):
    from datasets import load_dataset
    ds = load_dataset("HuggingFaceH4/MATH-500", split="test")
    items = [{"id": row.get("unique_id", f"math500-{i}"), "prompt": row["problem"], "answer": row["answer"]}
             for i, row in enumerate(ds)]
    return _subsample(items, limit, seed)


def _load_gpqa(limit, seed):
    from datasets import load_dataset
    ds = load_dataset("Idavidrein/gpqa", "gpqa_diamond", split="train")

    def pick(row, *names):
        for n in names:
            if n in row and row[n] is not None:
                return row[n]
        raise KeyError(f"none of {names} in GPQA row cols={list(row.keys())}")

    items = []
    for i, row in enumerate(ds):
        correct = str(pick(row, "Correct Answer")).strip()
        incorrect = [str(pick(row, f"Incorrect Answer {k}")).strip() for k in (1, 2, 3)]
        opts = [correct] + incorrect
        order = list(range(4))
        random.Random(f"{seed}-{i}").shuffle(order)
        shuffled = [opts[j] for j in order]
        gold = "ABCD"[order.index(0)]
        items.append({"id": f"gpqa-{i}", "prompt": str(pick(row, "Question")).strip(),
                      "options": shuffled, "answer": gold})
    return _subsample(items, limit, seed)


# ----------------------------------------------------------------- coding loaders
def _load_evalplus(which, limit, seed):
    if which == "humanevalplus":
        from evalplus.data import get_human_eval_plus
        data = get_human_eval_plus()
    else:
        from evalplus.data import get_mbpp_plus
        data = get_mbpp_plus()
    items = [{"id": tid, "prompt": p["prompt"], "meta": {"entry_point": p.get("entry_point")}}
             for tid, p in data.items()]
    return _subsample(items, limit, seed)


def _lcb_prompt_cache_path():
    """Machine-local prompt-only cache (never committed). Lets generation skip loading the
    full LCB dataset (880 problems + large private test cases ~10GB) — only prompts are
    needed to generate; test cases load at grade time."""
    import os
    return os.path.expanduser("~/.cache/livecodebench/lcb_%s_prompts.json" % LCB_RELEASE)


def _lcb_item(p):
    qc = p.question_content if hasattr(p, "question_content") else str(p)
    sc = getattr(p, "starter_code", "") or ""
    prompt = qc + ("\n\nStarter code:\n```python\n" + sc + "\n```" if sc else "")
    plat = getattr(p, "platform", None)
    return {"id": getattr(p, "question_id", None), "prompt": prompt,
            "meta": {"platform": str(plat) if plat is not None else None,
                     "question_content": qc, "starter_code": sc}}


def _load_lcb(limit, seed):
    # Pinned to LCB_RELEASE for contamination control (see module constant + README).
    # Prompt-only cache avoids holding the full dataset (incl. private test cases) in RAM
    # alongside the model during generation — the dataset (test cases) is only loaded at
    # grade time. Build the cache once on a miss, then every generation run is light.
    import json
    import os
    cache = _lcb_prompt_cache_path()
    if os.path.exists(cache):
        with open(cache) as f:
            items = json.load(f)
    else:
        from lcb_runner.benchmarks.code_generation import load_code_generation_dataset
        probs = load_code_generation_dataset(release_version=LCB_RELEASE)
        items = [_lcb_item(p) for p in probs]
        del probs
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        tmp = cache + ".tmp"          # atomic write: a failed dump never leaves a corrupt cache
        with open(tmp, "w") as f:
            json.dump(items, f)
        os.replace(tmp, cache)
    return _subsample(items, limit, seed)


# ----------------------------------------------------------------- instruction-following loader
def _ifeval_item(row: dict) -> dict:
    """Shape one google/IFEval row -> harness item. The HF schema pads every kwargs dict
    with all-possible-keys = None; the verifiers' build_description breaks on None, so each
    per-instruction kwargs dict is filtered to its non-None entries."""
    kwargs = [{k: v for k, v in (kw or {}).items() if v is not None} for kw in row["kwargs"]]
    return {"id": row["key"], "prompt": row["prompt"],
            "meta": {"instruction_id_list": list(row["instruction_id_list"]), "kwargs": kwargs}}


def _load_ifeval(limit, seed):
    from datasets import load_dataset
    ds = load_dataset("google/IFEval", split="train")
    items = [_ifeval_item(row) for row in ds]
    return _subsample(items, limit, seed)


def load(name: str, limit: int | None = None, seed: int = 0) -> list:
    if name == "aime":
        return _load_aime(limit, seed)
    if name == "math500":
        return _load_math500(limit, seed)
    if name == "gpqa":
        return _load_gpqa(limit, seed)
    if name in ("humanevalplus", "mbppplus"):
        return _load_evalplus(name, limit, seed)
    if name == "livecodebench":
        return _load_lcb(limit, seed)
    if name == "ifeval":
        return _load_ifeval(limit, seed)
    raise ValueError(f"unknown benchmark {name!r}; known: {list(SPECS)}")


# ----------------------------------------------------------------- prompt builders
_REASON_SUFFIX = {
    "aime": "\n\nSolve step by step. Give the final integer answer (an integer from 0 to 999) in \\boxed{}.",
    "math500": "\n\nSolve step by step. Put your final answer in \\boxed{}.",
}


def build_messages(name: str, item: dict) -> list:
    if name in ("aime", "math500"):
        return [{"role": "user", "content": item["prompt"] + _REASON_SUFFIX[name]}]
    if name == "gpqa":
        opts = "\n".join(f"({'ABCD'[i]}) {o}" for i, o in enumerate(item["options"]))
        body = (f"{item['prompt']}\n\n{opts}\n\nThink carefully, then give the letter of the "
                f"correct option in \\boxed{{}}.")
        return [{"role": "user", "content": body}]
    if name in ("humanevalplus", "mbppplus", "livecodebench"):
        return [{"role": "user", "content":
                 "Complete the following task. Return the complete solution as a single "
                 "self-contained ```python code block, no explanation after it.\n\n" + item["prompt"]}]
    if name == "ifeval":
        return [{"role": "user", "content": item["prompt"]}]
    raise ValueError(name)
