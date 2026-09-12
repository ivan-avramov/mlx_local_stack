"""Benchmark registry: load items + build prompts. Grading lives in grade.py.

Reasoning benchmarks need only `datasets`. Coding benchmarks need the official
evaluators (`evalplus`, `lcb_runner`) — imported lazily so reasoning works without them.
An Item is: {"id", "prompt", "answer"?, "options"?, "meta"?}.
"""
import base64
import json
import os
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
    "cjudge":        {"kind": "open", "answer_type": "none", "gated": False},
    "visionqa":      {"kind": "vision", "answer_type": "visionqa", "gated": False},
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


# ----------------------------------------------------------------- open (judge-panel) loader
_CJUDGE_PATH = os.path.join(os.path.dirname(__file__), "..", "corpora", "cjudge_v1.jsonl")


def _load_cjudge(limit, seed):
    """Role-C judge-panel corpus (docs/judge-panel-c.md 'Corpus cjudge'): 40 committed rows
    (30 public arena-hard-auto prompts + 10 verbatim domain prompts), read from the repo — no
    network, no HF dataset. `kind: open` has no gold answer; grading is a no-op (see grade.py)."""
    items = []
    with open(_CJUDGE_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            items.append({"id": row["id"], "prompt": row["prompt"],
                          "meta": {"source": row.get("source"), "source_id": row.get("source_id"),
                                   "category": row.get("category")},
                          "source": row.get("source"), "category": row.get("category")})
    return _subsample(items, limit, seed)


# ----------------------------------------------------------------- vision (visionqa) loader
_VISIONQA_PATH = os.path.join(os.path.dirname(__file__), "..", "corpora", "visionqa_v1.jsonl")
# Pre-workdir-rule fallback ONLY (AGENTS.md "NO FILESYSTEM POLLUTION OUTSIDE $STACK_WORKDIR"):
# ~/.cache/huggingface is a listed exception, but a NEW artifact tree belongs under
# $STACK_WORKDIR, not in it -- see `_visionqa_image_cache_dir`.
_VISIONQA_IMAGE_CACHE_FALLBACK = os.path.expanduser(
    "~/.cache/huggingface/mlx_local_stack_visionqa_images")


def _visionqa_image_cache_dir() -> str:
    """`$STACK_WORKDIR/visionqa_images` (the out-of-repo workdir rule). Falls back to the
    pre-workdir-rule `~/.cache/huggingface` location ONLY when STACK_WORKDIR is unset, with a
    loud warning -- that fallback is a pre-approved CACHE exception, not a home for new
    artifacts, so this should never be the steady state."""
    workdir = os.environ.get("STACK_WORKDIR")
    if workdir:
        return os.path.join(workdir, "visionqa_images")
    import sys
    print("WARNING: STACK_WORKDIR is not set; visionqa image cache falls back to "
          f"{_VISIONQA_IMAGE_CACHE_FALLBACK} (set STACK_WORKDIR per the workdir rule, AGENTS.md)",
          file=sys.stderr)
    return _VISIONQA_IMAGE_CACHE_FALLBACK


def _visionqa_image_cache_path(row: dict) -> str:
    ext = row["meta"]["image_format"].lower()
    return os.path.join(_visionqa_image_cache_dir(), f"{row['id']}.{ext}")


def _resolve_visionqa_images(rows: list) -> None:
    """Materialize each row's image to a local file (mutates row["meta"]["image_path"] in place),
    grouping by (dataset, split, revision) so each source dataset loads at most once per call.

    Graceful-degrade with a CLEAR error (not a raw huggingface_hub stack trace) when a dataset is
    neither locally cached nor reachable -- this is the one place visionqa needs the network.
    Generation-time ONLY: `grade_visionqa` (bench/grade.py) reads the committed corpus directly
    via `load_visionqa_meta` below and must never call this."""
    needed = [r for r in rows if not os.path.exists(_visionqa_image_cache_path(r))]
    for r in rows:
        r["meta"]["image_path"] = _visionqa_image_cache_path(r)
    if not needed:
        return
    try:
        from datasets import load_dataset
    except ImportError as e:
        raise RuntimeError(
            "benchmark 'visionqa' needs the `datasets` package to resolve images") from e
    os.makedirs(_visionqa_image_cache_dir(), exist_ok=True)
    ds_cache: dict = {}
    for r in needed:
        ref = r["image_ref"]
        key = (ref["dataset"], ref["split"], ref["revision"])
        if key not in ds_cache:
            try:
                ds_cache[key] = load_dataset(ref["dataset"], split=ref["split"],
                                             revision=ref["revision"])
            except Exception as e:  # noqa: BLE001 -- turn an opaque HF error into an actionable one
                raise RuntimeError(
                    f"visionqa: dataset {ref['dataset']!r} (split={ref['split']!r}, "
                    f"revision={ref['revision']!r}) is not in the local HF cache and could not be "
                    "fetched (offline / no network?). Run benchmark/corpora/build_visionqa_v1.py "
                    "once with network access to populate ~/.cache/huggingface, or unset "
                    f"HF_HUB_OFFLINE. ({type(e).__name__}: {str(e)[:200]})") from e
        img = ds_cache[key][ref["index"]]["image"]
        path = _visionqa_image_cache_path(r)
        tmp = path + ".tmp"
        img.save(tmp, format=r["meta"]["image_format"])
        os.replace(tmp, path)


def _read_visionqa_rows() -> list:
    """Raw committed-jsonl rows, verbatim -- the one place both `_load_visionqa` (generation) and
    `load_visionqa_meta` (grading) read from, so they can never drift on row shape."""
    rows = []
    with open(_VISIONQA_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_visionqa_meta(limit=None, seed=0) -> list:
    """Grading-time metadata ONLY: id/question/answer/choices/source_kind straight from the
    committed jsonl. Deliberately NEVER calls `_resolve_visionqa_images` -- grading must not need
    the network or the HF cache (bench/grade.py::grade_visionqa is the only caller)."""
    return _subsample(_read_visionqa_rows(), limit, seed)


def _load_visionqa(limit, seed):
    """visionqa_v1 (docs/vision-smoke-m39.md): 40 committed rows across four vision-QA sources
    (ChartQA/RICO-ScreenQA-Short/AI2D/TextVQA). Images are never committed -- resolved here to a
    local file via the HF cache (see `_resolve_visionqa_images`). Generation-time loader; grading
    uses `load_visionqa_meta` instead."""
    rows = _subsample(_read_visionqa_rows(), limit, seed)
    _resolve_visionqa_images(rows)
    items = []
    for row in rows:
        items.append({
            "id": row["id"], "prompt": row["question"], "answer": row["answer"],
            "options": row.get("choices"),
            "meta": {"source": row["source"], "source_kind": row["source_kind"],
                     "source_id": row["source_id"], "answer_numeric": row.get("answer_numeric"),
                     "image_path": row["meta"]["image_path"],
                     "image_format": row["meta"]["image_format"]},
        })
    return items


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
    if name == "cjudge":
        return _load_cjudge(limit, seed)
    if name == "visionqa":
        return _load_visionqa(limit, seed)
    raise ValueError(f"unknown benchmark {name!r}; known: {list(SPECS)}")


# ----------------------------------------------------------------- prompt builders
_REASON_SUFFIX = {
    "aime": "\n\nSolve step by step. Give the final integer answer (an integer from 0 to 999) in \\boxed{}.",
    "math500": "\n\nSolve step by step. Put your final answer in \\boxed{}.",
}

# Official LiveCodeBench code-generation prompt, transcribed verbatim from
# lcb_runner/prompts/code_generation.py (SYSTEM_MESSAGE_GENERIC +
# get_generic_question_template_answer). Qwen3.6 was officially evaluated with this template;
# its thinking-mode variant intentionally DROPS the "return only the program" restriction
# (our old prompt's "no explanation after it" made thinking models diverge). We reproduce the
# strings here rather than import lcb_runner so generation stays free of that heavy dependency
# (the prompt-only cache means generation never loads it). AtCoder/Codeforces problems (no
# starter code) get the explicit stdin framing; LeetCode functional problems get the starter
# code. The code extractor takes the last ```python fence, so trailing prose is fine.
_LCB_SYSTEM = ("You are an expert Python programmer. You will be given a question (problem "
               "specification) and will generate a correct Python program that matches the "
               "specification and passes all tests.")
_LCB_FMT_WITH_STARTER = ("You will use the following starter code to write the solution to "
                         "the problem and enclose your code within delimiters.")
_LCB_FMT_STDIN = ("Read the inputs from stdin solve the problem and write the answer to "
                  "stdout (do not directly test on the sample inputs). Enclose your code "
                  "within delimiters as follows. Ensure that when the python program runs, "
                  "it reads the inputs, runs the algorithm and writes output to STDOUT.")


def _lcb_messages(item: dict) -> list:
    # Raw question/starter from meta (the prompt-only cache preserves both); fall back to
    # item["prompt"] (treated as a stdin problem) for hand-built smoke items without meta.
    meta = item.get("meta") or {}
    question = meta.get("question_content") or item["prompt"]
    starter = meta.get("starter_code") or ""
    body = f"### Question:\n{question}\n\n"
    if starter:
        body += f"### Format: {_LCB_FMT_WITH_STARTER}\n```python\n{starter}\n```\n\n"
    else:
        body += f"### Format: {_LCB_FMT_STDIN}\n```python\n# YOUR CODE HERE\n```\n\n"
    body += "### Answer: (use the provided format with backticks)\n\n"
    return [{"role": "system", "content": _LCB_SYSTEM},
            {"role": "user", "content": body}]


_VISIONQA_SUFFIX = "\n\nAnswer with the final answer only, inside \\boxed{}."
_VISIONQA_AI2D_LETTER_INSTRUCTION = " Answer with the option letter (A, B, C or D)."


def _visionqa_messages(item: dict) -> list:
    """OpenAI content-list message: text part + a base64 `image_url` data URL, mirroring
    `benchmark/probe_vision.py`. AI2D appends a letter-answer instruction to the question, THEN
    lists the options as `A) ... D) ...` (positional labels over the row's own choice order --
    the source's `answer` letter already matches that order), THEN the shared \\boxed{} suffix."""
    text = item["prompt"]
    if item["meta"]["source_kind"] == "ai2d" and item.get("options"):
        text += _VISIONQA_AI2D_LETTER_INSTRUCTION
        opts = "\n".join(f"{'ABCD'[i]}) {o}" for i, o in enumerate(item["options"]))
        text = f"{text}\n\n{opts}"
    text += _VISIONQA_SUFFIX
    if os.environ.get("VISIONQA_TEXT_ONLY"):
        # M39 text-only CONTROL arm (tune m39txt): same prompt, image part dropped, so the
        # vision signal = vision-arm accuracy minus this floor. Driver-env switch, never default.
        return [{"role": "user", "content": text}]
    with open(item["meta"]["image_path"], "rb") as f:
        raw = f.read()
    mime = "image/jpeg" if item["meta"]["image_format"].upper() == "JPEG" else "image/png"
    data_url = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
    return [{"role": "user", "content": [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]}]


def build_messages(name: str, item: dict) -> list:
    if name in ("aime", "math500"):
        return [{"role": "user", "content": item["prompt"] + _REASON_SUFFIX[name]}]
    if name == "gpqa":
        opts = "\n".join(f"({'ABCD'[i]}) {o}" for i, o in enumerate(item["options"]))
        body = (f"{item['prompt']}\n\n{opts}\n\nThink carefully, then give the letter of the "
                f"correct option in \\boxed{{}}.")
        return [{"role": "user", "content": body}]
    if name == "livecodebench":
        return _lcb_messages(item)
    if name in ("humanevalplus", "mbppplus"):
        return [{"role": "user", "content":
                 "Complete the following task. Return the complete solution as a single "
                 "self-contained ```python code block, no explanation after it.\n\n" + item["prompt"]}]
    if name in ("ifeval", "cjudge"):
        return [{"role": "user", "content": item["prompt"]}]
    if name == "visionqa":
        return _visionqa_messages(item)
    raise ValueError(name)
