"""M76 B5: the committed ID sets of stage 3 / 4 (`docs/specs/m76-b3-b5-p426-kv-lever.md` v1.1, M76 spec §5 B5, §7).

  python -m bench.m76_ids [--math500-ids FILE]      (from `benchmark/`; writes benchmark/results/m76/ids.json)

- math500: 300 nested items = P426's 100 (`p426_ids`, blocks unchanged) then 200 drawn by `random.Random(7601)` from the remaining
  Math500 ids (the universe: `--math500-ids` (a JSON list or one id per line) or the `HuggingFaceH4/MATH-500` test split), split
  into two blocks by `random.Random(426)` as P426 B9. Tier 1 = the first 100, tier 2 = the rest.
- cjudge, vision, reasoning: P426's, unchanged.
- longctx (A5): n items per tier (a multiple of 6 in 42 … 120: two tasks × three rungs, equal cells), the sizes from B7's
  plan (v1.4 below); refused when the plan has none. Each item
  `{id, task, rung, task_seed, request_seed}` (seed 7605); blocks split per cell by seed 426; two smoke items outside the set.
  v1.2: every item's actual prompt token count (the offline tokenizer count of its exact prompt) and its resolved
  `max_tokens` = min(deployed, 262,144 − prompt tokens) are frozen per item; B8 requires each served row to match them.
- v1.4 (C339): A5's tiers are the looks of `m76_rule.axis_plan("A5")` (cumulative look sizes, never constants; today 72 / 120):
  tier 1 = the first look's items (the v1.1 draw, unchanged), tier 2 = the continuation of the same seed-7605 generator after
  tier 1 and the smoke items, the same task × rung cells extended (ids `<task>-<rung>-<k>` continue k), split per cell by
  seed 426 into `tier2.block1` / `tier2.block2`. Tier prefixes are nested, never a redraw.
- v1.5: the offline counter counts token ids (`input_ids` of a `BatchEncoding`, or a list), refuses a non-positive count and a
  calibration outside 1 … 10 chars / token, and records the transformers version.
- v1.5a: every generated A5 prompt's frozen count lies within [−3 %, 0 %] of its rung target, never above it (the generator
  refuses otherwise); the measured deviation per cell (task × rung; smoke items their own cells) is recorded in `longctx`.
"""

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

from bench import p426_ids
from bench.rowschema import sample_seed

ENTRY = p426_ids.ENTRY
OUT = "benchmark/results/m76/ids.json"
REPORT = "benchmark/results/m76/b7-simulation/report.json"
MATH500_SEED = 7601
MATH500_N = 300
MATH500_TIER1 = 100
A5_SEED = 7605
SPLIT_SEED = p426_ids.SEED
A5_TASKS = ("retrieval", "reasoning")
A5_RUNGS = (131072, 159744, 196608)
A5_N_MIN, A5_N_MAX = 42, 120
A5_CHAIN_LEN = 4
A5_SMOKE_RUNG = 131072
CONTEXT_CAP = 262144
THINKING_CLAMP = 0.8           # bench.convergence.THINKING_BUDGET_CLAMP_RATIO
SEED_SPACE = 2 ** 31 - 1
CAL_REPEAT = 200               # the runners' chars-per-token calibration: `_CAL_FILLER * 200` (run_retrieval / run_reasoning)
CPT_MIN, CPT_MAX = 1.0, 10.0   # v1.5: a sane chars-per-token calibration
PROMPT_BAND = (-0.03, 0.0)     # v1.5a: (frozen count − rung) / rung, never above the rung


class IdsError(ValueError):
    pass


def check_a5_n(n):
    if not isinstance(n, int) or isinstance(n, bool) or n % 6 or not A5_N_MIN <= n <= A5_N_MAX:
        raise IdsError(f"A5 n {n!r} is not a multiple of 6 in {A5_N_MIN} … {A5_N_MAX}")
    return n


PLAN_SOURCE = "m76_rule.axis_plan(A5)"


def check_a5_sizes(sizes):
    """A5's cumulative tier sizes: one or two looks, each a multiple of 6 in 42 … 120, strictly increasing."""
    if isinstance(sizes, int) and not isinstance(sizes, bool):
        sizes = (sizes,)
    if not isinstance(sizes, (list, tuple)) or not 1 <= len(sizes) <= 2:
        raise IdsError(f"A5 sizes {sizes!r}: one or two looks")
    for n in sizes:
        check_a5_n(n)
    if any(b <= a for a, b in zip(sizes, sizes[1:])):
        raise IdsError(f"A5 sizes {list(sizes)} are not strictly increasing (nested tiers)")
    return tuple(sizes)


def a5_sizes_from(plan=None):
    """(sizes, source): A5's cumulative tier sizes = the looks' `size` of B7's `m76_rule.axis_plan("A5")` (v1.4) and the
    report sha the plan read; refused when the plan has no sized look."""
    if plan is None:
        from bench import m76_rule

        try:
            plan = m76_rule.axis_plan("A5")
        except (ValueError, KeyError, TypeError) as exc:
            raise IdsError(f"m76_rule.axis_plan('A5') refused: {exc}") from None
    sizes = [lk.get("size") for lk in (plan or {}).get("looks") or []]
    if not sizes or any(n is None for n in sizes):
        raise IdsError(f"m76_rule.axis_plan('A5') has no sized looks ({sizes}): B7's committed report sizes A5")
    return check_a5_sizes(tuple(sizes)), dict(source=PLAN_SOURCE, report_sha256=plan.get("report_sha256"))


def universe_sha(ids):
    return hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()


def read_universe(path=None):
    """The Math500 id universe: a JSON list or one id per line from `path`, else the dataset's `unique_id`s (lazy import)."""
    if path is not None:
        text = Path(path).read_text()
        try:
            ids = json.loads(text)
        except ValueError:
            ids = [x.strip() for x in text.splitlines() if x.strip()]
    else:
        from bench import benchmarks

        ids = [it["id"] for it in benchmarks.load("math500")]
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise IdsError("the Math500 universe is not a list of string ids")
    if len(set(ids)) != len(ids):
        raise IdsError("the Math500 universe repeats an id")
    return sorted(ids)


def _split(order, rng):
    order = list(order)
    rng.shuffle(order)
    half = len(order) // 2
    return sorted(order[:half]), sorted(order[half:])


def math500(p426, universe):
    universe = sorted(universe)
    if len(set(universe)) != len(universe):
        raise IdsError("the Math500 universe repeats an id")
    tier1_blocks = p426["axes"]["math500"]
    tier1 = sorted(tier1_blocks["block1"] + tier1_blocks["block2"])
    missing = sorted(set(tier1) - set(universe))
    if len(tier1) != MATH500_TIER1 or missing:
        raise IdsError(f"P426's math500 ids are not {MATH500_TIER1} universe ids (missing {missing[:5]})")
    remaining = sorted(set(universe) - set(tier1))
    need = MATH500_N - MATH500_TIER1
    if len(remaining) < need:
        raise IdsError(f"the Math500 universe leaves {len(remaining)} ids beyond P426's, {need} needed")
    drawn = random.Random(MATH500_SEED).sample(remaining, need)
    b1, b2 = _split(sorted(drawn), random.Random(SPLIT_SEED))
    return dict(block1=list(tier1_blocks["block1"]), block2=list(tier1_blocks["block2"]), smoke=list(tier1_blocks["smoke"]),
                order=tier1 + drawn, tier1=tier1, tier2=dict(block1=b1, block2=b2, drawn=drawn),
                universe=list(universe), universe_n=len(universe), universe_sha256=universe_sha(universe))


def request_key(task, task_seed):
    """The per-row sampler seed key of one A5 item (`sample_seed(key, 0, request_seed)`), as each runner derives it."""
    return f"{task}:{task_seed}"


def row_sampler_seed(item):
    return sample_seed(request_key(item["task"], item["task_seed"]), 0, item["request_seed"])


def item_budget(prompt_tokens, max_tokens=None, thinking_budget=None):
    """One A5 item's frozen budget (erratum v1.2): its actual prompt token count (the offline count of the exact prompt), the
    resolved `max_tokens` = min(deployed, 262,144 − prompt tokens) (the server's rule) and the resolved thinking budget it implies
    (`bench.convergence.resolved_thinking_budget`); refused when nothing is left to generate."""
    if not isinstance(prompt_tokens, int) or isinstance(prompt_tokens, bool) or prompt_tokens <= 0:
        raise IdsError(f"prompt token count {prompt_tokens!r} is not a positive int")
    resolved = min(max_tokens, CONTEXT_CAP - prompt_tokens) if max_tokens is not None else CONTEXT_CAP - prompt_tokens
    if resolved <= 0 or prompt_tokens + resolved > CONTEXT_CAP:
        raise IdsError(f"prompt {prompt_tokens} + resolved budget {resolved} exceeds {CONTEXT_CAP}")
    thinking = min(thinking_budget, max(1, int(resolved * THINKING_CLAMP))) if thinking_budget is not None else None
    return dict(prompt_tokens=prompt_tokens, resolved_max_tokens=resolved, resolved_thinking_budget=thinking,
                total=prompt_tokens + resolved)


def budget(items, prompt_tokens, max_tokens=None, thinking_budget=None):
    """Per item id: `item_budget` of its frozen prompt token count; refused when an item has no count."""
    missing = sorted(i["id"] for i in items if i["id"] not in (prompt_tokens or {}))
    if missing:
        raise IdsError(f"A5 items without a frozen prompt token count: {missing[:5]} (the planner counts every prompt offline)")
    out = {}
    for i in items:
        try:
            out[i["id"]] = item_budget(prompt_tokens[i["id"]], max_tokens, thinking_budget)
        except IdsError as exc:
            raise IdsError(f"{i['id']}: {exc}") from None
    return out


def budget_problems(longctx, rows=None):
    """The offline check of the committed record (`longctx.budget` = the rebuild from its own inputs, every item covered, prompt +
    resolved budget ≤ 262,144) and, given rows ({item id: prompt_tokens}), each row's prompt EQUAL to its frozen count."""
    b = longctx.get("budget") or {}
    inputs = longctx.get("budget_inputs") or {}
    everything = (longctx.get("items") or []) + (longctx.get("smoke_items") or [])
    try:
        want = budget(everything, inputs.get("prompt_tokens"), inputs.get("max_tokens"), inputs.get("thinking_budget"))
    except (IdsError, ValueError, TypeError, KeyError) as exc:
        return [f"longctx budget: {exc}"]
    problems = [] if b == want else ["longctx budget: the recorded budget is not the rebuild from its inputs"]
    for item in everything:
        cell = b.get(item.get("id"))
        if not cell:
            problems.append(f"{item.get('id')}: no budget record")
        elif cell["prompt_tokens"] + cell["resolved_max_tokens"] > CONTEXT_CAP:
            problems.append(f"{item.get('id')}: prompt + resolved budget > {CONTEXT_CAP}")
    for iid, prompt in sorted((rows or {}).items()):
        cell = b.get(iid)
        if cell is None:
            problems.append(f"{iid}: not an A5 item")
        elif prompt != cell["prompt_tokens"] or not isinstance(prompt, int):
            problems.append(f"{iid}: prompt_tokens {prompt!r} != the frozen count {cell['prompt_tokens']}")
    return problems


def resolved_of(row, max_tokens, context_limit=CONTEXT_CAP, thinking_budget=None):
    """(resolved max_tokens, resolved thinking budget) of a served A5 row from its OWN facts: its `prompt_tokens`, the leg's
    `sampling.max_tokens` / `thinking_budget` and the served context limit (`kv.max_kv_cache_size`); None when unknown."""
    from bench import convergence

    prompt = row.get("prompt_tokens") if isinstance(row, dict) else None
    if not isinstance(prompt, int) or isinstance(prompt, bool) or not isinstance(max_tokens, int) or not context_limit:
        return None, None
    resolved = min(max_tokens, int(context_limit) - prompt)
    if resolved <= 0:
        return None, None
    thinking = convergence.resolved_thinking_budget(dict(row, thinking_budget=thinking_budget), context_limit=context_limit,
                                                    max_tokens=max_tokens) if thinking_budget is not None else None
    return resolved, thinking


def prompt_messages(item, chars_per_token, chain_len=A5_CHAIN_LEN):
    """The exact messages the item's runner sends (`bench.retrieval` / `bench.reasoning` builders, the item's task seed, one
    trial) at a chars-per-token calibration."""
    if item["task"] == "retrieval":
        from bench.retrieval import build_context, make_question

        context, needles = build_context(item["rung"], chars_per_token, seed=item["task_seed"])
        return [{"role": "user", "content": context + "\n\n" + make_question(needles)}]
    from bench.reasoning import build_vartrack

    context, _answer, question = build_vartrack(item["rung"], chars_per_token, chain_len=chain_len, seed=item["task_seed"])
    return [{"role": "user", "content": context + "\n\n" + question}]


def token_count(encoded):
    """The token-id count of an `apply_chat_template(..., tokenize=True)` result (v1.5): a list of ids, or a mapping
    (`BatchEncoding`, transformers ≥ 5) whose `input_ids` are counted; a single-row batch is unwrapped. Anything else, or a
    count that is not a positive integer, is refused."""
    ids = encoded
    if not isinstance(encoded, (list, tuple)) and hasattr(encoded, "keys"):
        if "input_ids" not in encoded.keys():
            raise IdsError(f"token count: a {type(encoded).__name__} without input_ids")
        ids = encoded["input_ids"]
    if hasattr(ids, "tolist"):
        ids = ids.tolist()
    if isinstance(ids, (list, tuple)) and len(ids) == 1 and isinstance(ids[0], (list, tuple)):
        ids = ids[0]
    if not isinstance(ids, (list, tuple)) or not all(isinstance(t, int) and not isinstance(t, bool) for t in ids):
        raise IdsError(f"token count: not a sequence of token ids ({type(ids).__name__})")
    return positive_count(len(ids))


def positive_count(n):
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
        raise IdsError(f"token count {n!r} is not a positive integer")
    return n


def check_calibration(cpt):
    if not isinstance(cpt, (int, float)) or isinstance(cpt, bool) or not CPT_MIN <= cpt <= CPT_MAX:
        raise IdsError(f"chars-per-token calibration {cpt!r} is outside {CPT_MIN} … {CPT_MAX}")
    return cpt


def _transformers_version():
    from importlib import metadata

    try:
        return metadata.version("transformers")
    except metadata.PackageNotFoundError:
        return None


def offline_counter(entry=ENTRY, tokenizer=None):
    """(count(messages) -> int, chars_per_token, meta): the entry's tokenizer from the local HF cache (lazy import; `tokenizer`
    = an already-loaded one), the chat template with the generation prompt, and the runners' calibration recomputed offline
    (`_CAL_FILLER * 200`). v1.5: counts the token ids whatever the return type, refuses a non-positive count and a calibration
    outside 1 … 10 chars / token; meta names the transformers version (run it in the arm worktree's venv, as the worker). The
    designer runs it on the box; B8 then requires every served row's `prompt_tokens` to equal the frozen count (a server that
    counts otherwise is refused, never re-planned)."""
    from bench.model_params import _registry_models
    from bench.run_retrieval import _CAL_FILLER

    hf = (_registry_models().get(entry) or {}).get("hf_path") or entry
    kw = deployed_template_kwargs(entry)
    tok = tokenizer
    if tok is None:
        from transformers import AutoTokenizer

        tok = AutoTokenizer.from_pretrained(hf, local_files_only=True)

    def count(messages):
        return token_count(tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=True, **kw))

    cal = _CAL_FILLER * CAL_REPEAT
    cpt = check_calibration(len(cal) / count([{"role": "user", "content": cal}]))
    return count, cpt, dict(tokenizer=hf, chat_template_sha256=hashlib.sha256(str(tok.chat_template).encode()).hexdigest(),
                            chars_per_token=cpt, transformers_version=_transformers_version(), template_kwargs=dict(kw))


TEMPLATE_KWARGS = ("enable_thinking", "reasoning_effort")


def deployed_template_kwargs(entry=ENTRY):
    """v1.1 F3 (C355 (3), S25-P1): the chat-template kwargs the server renders the entry's deployed request with
    (`params_for(entry, profile="deployed")`: `enable_thinking`, `reasoning_effort`, each only when set)."""
    from bench.model_params import params_for

    p = params_for(entry, profile="deployed")
    return {k: p[k] for k in TEMPLATE_KWARGS if p.get(k) is not None}


def count_prompts(items, count, chars_per_token, chain_len=A5_CHAIN_LEN):
    return {i["id"]: positive_count(count(prompt_messages(i, chars_per_token, chain_len))) for i in items}


def cell_of(item):
    """An A5 item's cell key: `<task>-<rung>`; a smoke item is its own cell `smoke-<task>-<rung>`."""
    key = f"{item['task']}-{item['rung']}"
    return f"smoke-{key}" if str(item["id"]).startswith("smoke-") else key


def deviation(item, prompt_tokens):
    """(frozen count − rung target) / rung target of one A5 item."""
    return (prompt_tokens[item["id"]] - item["rung"]) / item["rung"]


def prompt_deviation(items, prompt_tokens):
    """v1.5a: per cell {n, min, max, mean} of the items' measured deviation from the rung target."""
    by = {}
    for item in items:
        by.setdefault(cell_of(item), []).append(deviation(item, prompt_tokens))
    return {k: dict(n=len(v), min=min(v), max=max(v), mean=sum(v) / len(v)) for k, v in sorted(by.items())}


def prompt_band_problems(items, prompt_tokens, band=PROMPT_BAND):
    """v1.5a: the items whose frozen prompt count lies outside [−3 %, 0 %] of the rung target (never above it)."""
    lo, hi = band
    out = []
    for item in items:
        n = (prompt_tokens or {}).get(item["id"])
        if not isinstance(n, int) or isinstance(n, bool):
            out.append(f"{item['id']}: no frozen prompt count")
            continue
        d = deviation(item, prompt_tokens)
        if not lo <= d <= hi:
            out.append(f"{item['id']}: prompt {n} is {d:+.3%} of rung {item['rung']} (band {lo:+.0%} … {hi:+.0%})")
    return out


def check_prompt_band(items, prompt_tokens, band=PROMPT_BAND):
    problems = prompt_band_problems(items, prompt_tokens, band)
    if problems:
        raise IdsError(f"A5 prompt sizes outside the rung band ({len(problems)}): {problems[:5]}")


def _split_cells(cells):
    """Per cell (task × rung) by seed 426; an odd cell's extra item alternates between the blocks."""
    split = random.Random(SPLIT_SEED)
    b1, b2, odd = [], [], 0
    for key in sorted(cells):
        x, y = _split(cells[key], split)
        if len(x) != len(y):
            x, y = (y, x) if odd % 2 else (x, y)
            odd += 1
        b1 += x
        b2 += y
    return sorted(b1), sorted(b2)


def longctx_items(n):
    """(items, smoke items, blocks) of A5's tier 1 — the draw only (seed 7605; per-cell split by seed 426)."""
    d = longctx_draw((n,))
    return d["items"], d["smoke"], d["block1"], d["block2"], d["per_cell"]


def longctx_draw(sizes):
    """A5's nested draw over the cumulative tier sizes (v1.4): tier 1 (seed 7605: the cells' items, then the two smoke items) as
    v1.1; tier 2 continues the SAME generator after the smoke items, appending `(sizes[1] − sizes[0]) / 6` items to every cell
    (ids continue the cell's index). Returns {items (tier 1 then tier 2), smoke, block1, block2, per_cell, tier1, tier2}; tier2
    is None for a one-look plan."""
    sizes = check_a5_sizes(sizes)
    n = sizes[0]
    rng = random.Random(A5_SEED)
    used = set()

    def draw():
        while True:
            s = rng.randrange(1, SEED_SPACE)
            if s not in used:
                used.add(s)
                return s

    per = n // (len(A5_TASKS) * len(A5_RUNGS))
    items, cells = [], {}
    for task in A5_TASKS:
        for rung in A5_RUNGS:
            for k in range(per):
                item = dict(id=f"{task}-{rung}-{k:02d}", task=task, rung=rung, task_seed=draw(), request_seed=draw())
                items.append(item)
                cells.setdefault((task, rung), []).append(item["id"])
    smoke = [dict(id=f"smoke-{task}-{A5_SMOKE_RUNG}", task=task, rung=A5_SMOKE_RUNG, task_seed=draw(), request_seed=draw())
             for task in A5_TASKS]
    b1, b2 = _split_cells(cells)
    out = dict(items=items, smoke=smoke, block1=b1, block2=b2, per_cell=per, tier1=[i["id"] for i in items], tier2=None)
    if len(sizes) == 2:
        more = (sizes[1] - sizes[0]) // (len(A5_TASKS) * len(A5_RUNGS))
        added, cells2 = [], {}
        for task in A5_TASKS:
            for rung in A5_RUNGS:
                for k in range(per, per + more):
                    item = dict(id=f"{task}-{rung}-{k:02d}", task=task, rung=rung, task_seed=draw(), request_seed=draw())
                    added.append(item)
                    cells2.setdefault((task, rung), []).append(item["id"])
        t2b1, t2b2 = _split_cells(cells2)
        out["items"] = items + added
        out["tier2"] = dict(block1=t2b1, block2=t2b2, per_cell=more, items=[i["id"] for i in added])
    return out


def longctx(sizes, max_tokens=None, thinking_budget=None, prompt_tokens=None, counter=None):
    """A5's record: the nested draw (`longctx_draw`; `sizes` = the plan's cumulative look sizes, an int = one tier), every
    item's frozen prompt token count (`prompt_tokens` {id: int}, the planner's offline count of the exact prompt; `counter` = its
    tokenizer / calibration metadata) and its resolved budget. `n` = all items; `tier1` = the first look's ids; `tier2` (two
    looks only) = {block1, block2, per_cell, items}."""
    sizes = check_a5_sizes(sizes)
    d = longctx_draw(sizes)
    items, smoke = d["items"], d["smoke"]
    rec = dict(n=sizes[-1], sizes=list(sizes), tasks=list(A5_TASKS), rungs=list(A5_RUNGS), per_cell=d["per_cell"],
               chain_len=A5_CHAIN_LEN, items=items, block1=d["block1"], block2=d["block2"], tier1=d["tier1"],
               smoke=[s["id"] for s in smoke], smoke_items=smoke,
               budget=budget(items + smoke, prompt_tokens, max_tokens, thinking_budget),
               budget_inputs=dict(max_tokens=max_tokens, thinking_budget=thinking_budget, context_cap=CONTEXT_CAP,
                                  thinking_clamp=THINKING_CLAMP, prompt_tokens=dict(sorted((prompt_tokens or {}).items())),
                                  counter=counter))
    if d["tier2"] is not None:
        rec["tier2"] = d["tier2"]
    rec["prompt_deviation"] = dict(band=list(PROMPT_BAND), cells=prompt_deviation(items + smoke, prompt_tokens))
    rec["sampler_seeds"] = {i["id"]: row_sampler_seed(i) for i in items + smoke}
    return rec


def deployed_budget():
    """(max_tokens, thinking_budget) of the entry's deployed profile (the registry; no request)."""
    from bench.model_params import params_for

    p = params_for(ENTRY, profile="deployed")
    return p.get("max_tokens"), p.get("thinking_budget")


def build(repo, *, a5_sizes, universe, max_tokens, thinking_budget, a5_source=None, prompt_tokens=None, counter=None):
    p426 = p426_ids.build(repo)
    axes = dict(math500=math500(p426, universe))
    for axis in ("cjudge", "vision", "reasoning"):
        axes[axis] = p426["axes"][axis]
    a5_sizes = check_a5_sizes(a5_sizes)
    axes["longctx"] = longctx(a5_sizes, max_tokens, thinking_budget, prompt_tokens=prompt_tokens, counter=counter)
    return dict(entry=ENTRY, seed=SPLIT_SEED, seeds=dict(math500=MATH500_SEED, longctx=A5_SEED, split=SPLIT_SEED), axes=axes,
                a5=dict(a5_source or dict(source=None, report_sha256=None), sizes=list(a5_sizes)),
                p426_sources_sha256=p426_ids.source_shas(repo))


def rebuild_of(repo, doc):
    """The rebuild of a committed record from its own recorded inputs (universe, A5 sizes and source, deployed budget)."""
    ax = doc["axes"]
    lc = ax["longctx"]["budget_inputs"]
    return build(repo, a5_sizes=tuple(doc["a5"]["sizes"]), universe=ax["math500"]["universe"], max_tokens=lc["max_tokens"],
                 thinking_budget=lc["thinking_budget"], a5_source={k: v for k, v in doc["a5"].items() if k != "sizes"},
                 prompt_tokens=lc.get("prompt_tokens"), counter=lc.get("counter"))


def load(repo, text=None, plan=None):
    """The committed ids.json, refused unless it equals a rebuild from its own inputs and the current P426 sources, and (v1.4)
    its A5 sizes and report sha are the current `m76_rule.axis_plan("A5")`'s (`plan`: that plan; default B7's)."""
    repo = Path(repo)
    doc = json.loads(text if text is not None else (repo / OUT).read_text())
    try:
        want = rebuild_of(repo, doc)
    except (KeyError, TypeError, IdsError) as exc:
        raise ValueError(f"{OUT}: cannot be rebuilt from its inputs ({exc})") from None
    if doc != want:
        raise ValueError(f"{OUT}: not the committed rebuild of its inputs")
    if doc["a5"].get("source") != PLAN_SOURCE:
        raise ValueError(f"{OUT}: A5 sizes do not come from {PLAN_SOURCE}")
    try:
        sizes, source = a5_sizes_from(plan)
    except IdsError as exc:
        raise ValueError(f"{OUT}: {exc}") from None
    if list(sizes) != doc["a5"]["sizes"] or source["report_sha256"] != doc["a5"].get("report_sha256"):
        raise ValueError(f"{OUT}: A5 sizes {doc['a5']['sizes']} / report sha are not the current plan's {list(sizes)}")
    lc = doc["axes"]["longctx"]
    try:                                                    # S23-P88: the band holds on the record, not only at generation
        check_prompt_band(lc["items"] + lc["smoke_items"], lc["budget_inputs"].get("prompt_tokens"))
    except IdsError as exc:
        raise ValueError(f"{OUT}: {exc}") from None
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--math500-ids", default=None, help="the Math500 id universe (JSON list or lines); default the dataset")
    args = ap.parse_args(argv)
    repo = Path(__file__).resolve().parents[2]
    try:
        sizes, source = a5_sizes_from()
        max_tokens, thinking = deployed_budget()
        count, cpt, meta = offline_counter()
        d = longctx_draw(sizes)
        counts = count_prompts(d["items"] + d["smoke"], count, cpt)
        check_prompt_band(d["items"] + d["smoke"], counts)
        doc = build(repo, a5_sizes=sizes, universe=read_universe(args.math500_ids), max_tokens=max_tokens,
                    thinking_budget=thinking, a5_source=source, prompt_tokens=counts, counter=meta)
    except IdsError as exc:
        print(f"[m76_ids] REFUSED: {exc}", file=sys.stderr)
        return 2
    out = repo / OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    print(out, hashlib.sha256(out.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
