"""P371 (plan 3.1, 4 A1 / A8): pure, hashed schedule builders. Absorbed the retired M64 block-schedule module (its callers moved
here in phase 3b; pinned golden values in `tests/fixtures/p371_blocks_golden.json`). No corpus, adapter, client or
process import; entries inject the item lists.

- `blocks(arms, names, ...)`: M64 spec 8.1 (seeded order, blocks of 3, balanced arm permutations, reload control) over
  ANY language list; for the tg1 corpus it reproduces the retired M64 builder EXACTLY (same dict, same sha256).
- `tg1(mode, sessions, names, ...)`: `run_tg1_chain.schedule` / `make_leg` / `steps_for` semantics, but every leg carries
  DISJOINT invocations (P376): a leg's pilot invocation runs the 5 seeded pilot items and its full invocation the
  cell's REMAINING items (today's full step re-launches all items and the probe skips the pilot rows). The seeded pilot
  draw and the item order are unchanged. Phase shapes: pilot only (`pilot` mode, `reload`, smoke when pilot == full),
  pilot + full (first leg of a block), full only (later legs of a block).
- `tg2_tier(draw_doc, draw_sha256, tier, ...)`: consumes the frozen seed-6501 tg2 draw artifact's nested prefixes (never
  redraws, R14): screen = s1 only, 10 per language (C168 k = 1); decider = s1 + s2 + same-seed reload, 20 per language
  (reload: the first 5). The draw's sha256 (the sha of its canonical file bytes) and tier are recorded in the schedule
  and re-verified by `check_tg2_membership` at every leg.

A schedule holds no paths (it is hashed before launch and checked after: `schedule_sha256`, `require_frozen`,
`check_realized`)."""
from __future__ import annotations

import hashlib
import itertools
import json
import random

from .token_turn_gate import TransportAbort

SCHEMA = 1
# ---- blocks (the retired M64 builder's constants; pinned by the golden fixture)
BLOCK_SIZE = 3
SESSION_SEEDS = {"s1": 1001, "s2": 2002}
RELOAD_SEED = 1001
RELOAD_ITEMS = 5
SMOKE_ITEMS = 4                 # a full block and a residual item
ARM_IDS = ("oc", "pi", "dsh")   # = arm_adapter.ARM_IDS (this module imports no adapter module)
PICK1 = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
PICK2 = "Qwen3.8-27B-mlx-uniform-4bit"
DERIVATION = "order=Random(sha256('m64-order|seed|pick|lang')).shuffle(sorted(names)); perms=Random(sha256('m64-perm|seed|pick|lang'))"
# ---- tg1 (copies of run_tg1_chain's constants)
TG1_SEEDS = {"s1": 1001, "s2": 2002, "reload": 1001}
PILOT_N = 5
SMOKE_PILOT_N, SMOKE_FULL_N = 1, 2
# ---- tg2
TG2_SEED = 6501
TG2_TIERS = {"screen": 10, "decider": 20}
TG2_SESSIONS = {"screen": ("s1",), "decider": ("s1", "s2", "reload")}
TG2_RELOAD_ITEMS = 5


def flat_stem(model, session, lang):
    """The leg stem of the flat (tg1 / tg2) layout: `<model>.<session>.opencode_<lang>` (rows files are `<stem>.L<leg>...`)."""
    return f"{model}.{session}.opencode_{lang}"


def _rng(kind, seed, pick, lang):
    return random.Random(int(hashlib.sha256(f"m64-{kind}|{seed}|{pick}|{lang}".encode()).hexdigest(), 16))


def item_order(names, seed, pick, lang):
    order = sorted(names)
    _rng("order", seed, pick, lang).shuffle(order)
    return order


def _chunks(order):
    return [order[i:i + BLOCK_SIZE] for i in range(0, len(order), BLOCK_SIZE)]


def allocate(arms, n_full, residual, rng):
    """Permutations for `n_full` blocks (each once per round, the remainder drawn) and the residual's own draw."""
    perms = list(itertools.permutations(arms))
    rounds, rem = divmod(n_full, len(perms))
    seq = perms * rounds + rng.sample(perms, rem)
    rng.shuffle(seq)
    return seq, (rng.choice(perms) if residual else None)


def _cell(arms, order, seed, pick, lang):
    chunks = _chunks(order)
    full = [c for c in chunks if len(c) == BLOCK_SIZE]
    rest = [c for c in chunks if len(c) < BLOCK_SIZE]
    seq, residual_perm = allocate(arms, len(full), bool(rest), _rng("perm", seed, pick, lang))
    blocks_ = [dict(i=i, items=c, arms=list(p)) for i, (c, p) in enumerate(zip(full, seq))]
    blocks_ += [dict(i=len(blocks_) + j, items=c, arms=list(residual_perm)) for j, c in enumerate(rest)]
    return dict(lang=lang, order=list(order), blocks=blocks_)


def blocks(arms, names, *, picks=(PICK1, PICK2), sessions=("s1", "s2"), langs=("python", "go"), reload_control=True,
           reload_langs=("python",), smoke=False):
    arms = tuple(arms)
    if not arms or len(set(arms)) != len(arms):
        raise ValueError(f"arms must be a nonempty list of distinct arms, got {arms!r}")
    for arm in arms:
        if arm not in ARM_IDS:
            raise ValueError(f"unknown arm {arm!r}")
    langs, reload_langs = tuple(langs), tuple(reload_langs)
    missing = [lang for lang in langs if lang not in names]
    if missing:
        raise ValueError(f"no items for languages {missing}")
    if reload_control and not set(reload_langs) <= set(langs):
        raise ValueError(f"reload languages {reload_langs} are not all scheduled ({langs})")
    loads, first = [], {}
    for session in sessions:
        seed = SESSION_SEEDS[session]
        for pick in (picks if session == "s1" else tuple(reversed(picks))):
            cells = []
            for lang in langs:
                order = item_order(names[lang], seed, pick, lang)
                if smoke:
                    order = order[:SMOKE_ITEMS]
                cells.append(_cell(arms, order, seed, pick, lang))
                first[(session, pick, lang)] = cells[-1]["order"]
            loads.append(dict(session=session, pick=pick, seed_base=seed, cells=cells))
    if reload_control:
        cells = [_cell(arms, first[("s1", picks[0], lang)][:RELOAD_ITEMS], RELOAD_SEED, picks[0], lang)
                 for lang in reload_langs]
        loads.append(dict(session="reload", pick=picks[0], seed_base=RELOAD_SEED, cells=cells))
    return dict(schema=SCHEMA, arms=list(arms), block_size=BLOCK_SIZE, seeds=dict(SESSION_SEEDS, reload=RELOAD_SEED),
                derivation=DERIVATION, smoke=bool(smoke), loads=loads)


# ---------------------------------------------------------------- tg1
def _tg1_legs_table(picks, langs):
    p1, p2 = picks
    return {"s1": [(p, l) for p in (p1, p2) for l in langs],
            "s2": [(p, l) for p in (p2, p1) for l in langs],
            "reload": [(p1, langs[0])]}


def _tg1_leg(session, model, lang, seed_base, names, *, reload_ctl, smoke, predictor, first_leg, pilot_only):
    pool = sorted(names[lang])
    pilot = random.Random(seed_base).sample(pool, SMOKE_PILOT_N if smoke else PILOT_N)
    if reload_ctl:
        full = sorted(pilot)
    elif smoke:
        rest = [x for x in pool if x not in pilot]
        full = sorted(pilot + random.Random(seed_base).sample(rest, SMOKE_FULL_N - len(pilot)))
    else:
        full = pool
    pilot = sorted(pilot)
    stem = f"{model}.{session}.opencode_{lang}"

    def inv(phase, items):
        return dict(phase=phase, names=list(items), limit=len(items) if phase == "pilot" else None,
                    expect=[f"{lang}/{n}" for n in items])
    if pilot_only:
        invocations = [inv("pilot", pilot)]
    elif not first_leg:
        invocations = [inv("full", full)]
    elif pilot == full:
        invocations = [inv("pilot", pilot)]
    else:
        invocations = [inv("pilot", pilot), inv("full", [n for n in full if n not in set(pilot)])]
    return dict(session=session, model=model, lang=lang, seed_base=seed_base, stem=stem, pilot_names=pilot,
                full_names=full, draft_kind=predictor, invocations=invocations)


def tg1(mode, sessions, names, *, smoke=False, predictor="off", picks=(PICK1, PICK2), langs=("python", "go")):
    """The tg1 chain schedule (blocks of one model within one session, legs = languages) with disjoint invocations."""
    langs = tuple(langs)
    table = _tg1_legs_table(picks, langs)
    out = []
    if mode == "pilot":
        leg = _tg1_leg("pilot", picks[0], langs[0], TG1_SEEDS["s1"], names, reload_ctl=False, smoke=False,
                       predictor=predictor, first_leg=True, pilot_only=True)
        out.append(dict(session="pilot", model=picks[0], seed_base=TG1_SEEDS["s1"], legs=[leg], pilot_only=True))
    else:
        for s in sessions:
            grouped = []
            for model, lang in table[s]:
                if grouped and grouped[-1][0] == model:
                    grouped[-1][1].append(lang)
                else:
                    grouped.append((model, [lang]))
            for model, ls in grouped:
                legs_ = [_tg1_leg(s, model, lang, TG1_SEEDS[s], names, reload_ctl=(s == "reload"), smoke=smoke,
                                  predictor=predictor, first_leg=(i == 0), pilot_only=False)
                         for i, lang in enumerate(ls)]
                out.append(dict(session=s, model=model, seed_base=TG1_SEEDS[s], legs=legs_, pilot_only=False))
    return dict(schema=SCHEMA, builder="tg1", mode=mode, smoke=bool(smoke), predictor=predictor,
                picks=list(picks), blocks=out)


# ---------------------------------------------------------------- tg2
def draw_sha256_of(doc):
    """sha256 of the draw's canonical file bytes (`tg2_draw.freeze`: sort_keys, indent 1, trailing newline)."""
    return hashlib.sha256((json.dumps(doc, sort_keys=True, indent=1) + "\n").encode()).hexdigest()


def _tg2_check_draw(doc, sha, tier):
    if tier not in TG2_TIERS:
        raise TransportAbort("unknown tg2 tier %r" % (tier,))
    if draw_sha256_of(doc) != sha:
        raise TransportAbort("the tg2 draw artifact differs from its frozen sha256 (never redrawn)")
    if doc.get("seed") != TG2_SEED or not isinstance(doc.get("languages"), dict):
        raise TransportAbort("tg2 draw seed / shape")


def _tg2_items(entry, lang, tier):
    perm, items = entry["permutation"], entry[tier]
    if (len(perm) != entry["N_actual"] or items != perm[:len(items)]
            or len(items) != min(TG2_TIERS[tier], entry["N_actual"])
            or any(not i.startswith(lang + "/") for i in perm)):
        raise TransportAbort("tg2 %s tier of %s is not the frozen permutation prefix" % (tier, lang))
    return list(items)


def tg2_tier(draw_doc, draw_sha256, tier, *, sessions=None, acknowledged=()):
    _tg2_check_draw(draw_doc, draw_sha256, tier)
    want = TG2_SESSIONS[tier]
    if sessions is not None and tuple(sessions) != want:
        raise TransportAbort("tg2 tier %s runs sessions %s, not %s" % (tier, want, tuple(sessions)))
    cells = {}
    for lang in sorted(draw_doc["languages"]):
        entry = draw_doc["languages"][lang]
        items = _tg2_items(entry, lang, tier)
        if entry["N_actual"] < TG2_TIERS[tier] and lang not in acknowledged:
            raise TransportAbort("tg2 %s: %s has N_actual=%d < %d and needs operator acknowledgement"
                                 % (tier, lang, entry["N_actual"], TG2_TIERS[tier]))
        cells[lang] = items
    seeds = TG1_SEEDS
    out = [dict(session=s, seed_base=seeds[s],
                cells=[dict(lang=lang, items=(items[:TG2_RELOAD_ITEMS] if s == "reload" else list(items)))
                       for lang, items in cells.items()])
           for s in want]
    return dict(schema=SCHEMA, builder="tg2_tier", tier=tier, draw_sha256=draw_sha256, seed=TG2_SEED, sessions=out)


def tg2_prefix_names(draw_doc, draw_sha256, tier):
    """`{lang: [bare item names]}` of a tier's prefix, for `blocks` (the m64-oc-tg2 screen schedule)."""
    _tg2_check_draw(draw_doc, draw_sha256, tier)
    return {lang: [i.split("/", 1)[1] for i in _tg2_items(entry, lang, tier)]
            for lang, entry in sorted(draw_doc["languages"].items())}


def check_tg2_membership(schedule, draw_doc, draw_sha256, *, leg=None):
    """Re-derive the tier from the frozen draw and compare (the whole schedule, or one leg's cell)."""
    if schedule.get("draw_sha256") != draw_sha256:
        raise TransportAbort("the schedule names another tg2 draw than the one presented")
    langs = tuple(c["lang"] for s in schedule["sessions"] for c in s["cells"])
    expect = tg2_tier(draw_doc, draw_sha256, schedule["tier"], acknowledged=langs)
    if leg is None:
        if expect != schedule:
            raise TransportAbort("the schedule's items differ from the frozen tg2 draw prefix")
        return
    for sess in expect["sessions"]:
        for cell in sess["cells"]:
            if (sess["session"], cell["lang"]) == (leg["session"], leg["lang"]):
                if list(leg["items"]) != cell["items"]:
                    raise TransportAbort("leg items differ from the frozen tg2 draw prefix")
                return
    raise TransportAbort("leg is not in the frozen tg2 tier")


# ---------------------------------------------------------------- common: hash, legs, keys, checks
def schedule_sha256(schedule):
    return hashlib.sha256(json.dumps(schedule, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def legs(schedule):
    """Every leg of the schedule in launch order (a `blocks` leg is one (block, arm); a tg1 leg one (model, lang) of a
    block; a tg2 leg one (session, lang))."""
    out = []
    if schedule.get("builder") == "tg1":
        for bi, block in enumerate(schedule["blocks"]):
            for li, leg in enumerate(block["legs"]):
                out.append(dict(index=len(out), block=bi, leg=li, session=block["session"], model=block["model"],
                                seed_base=block["seed_base"], lang=leg["lang"], stem=leg["stem"],
                                items=list(leg["full_names"]), invocations=leg["invocations"],
                                pilot_only=block["pilot_only"]))
    elif schedule.get("builder") == "tg2_tier":
        for sess in schedule["sessions"]:
            for cell in sess["cells"]:
                out.append(dict(index=len(out), session=sess["session"], seed_base=sess["seed_base"],
                                lang=cell["lang"], items=list(cell["items"])))
    else:
        for li, load in enumerate(schedule["loads"]):
            for cell in load["cells"]:
                for block in cell["blocks"]:
                    for arm in block["arms"]:
                        out.append(dict(index=len(out), load=li, session=load["session"], pick=load["pick"],
                                        seed_base=load["seed_base"], lang=cell["lang"], block=block["i"], arm=arm,
                                        items=list(block["items"]), residual=len(block["items"]) < BLOCK_SIZE))
    return out


def leg_key(leg):
    if "arm" in leg:
        return [leg["load"], leg["lang"], leg["block"], leg["arm"], list(leg["items"])]
    if "model" in leg:
        return [leg["block"], leg["lang"], leg["model"], leg["session"], list(leg["items"])]
    return [leg["session"], leg["lang"], list(leg["items"])]


def check_realized(schedule, realized):
    want = [leg_key(leg) for leg in legs(schedule)]
    if [list(r) for r in realized] != want:
        raise ValueError("realized order differs from the frozen schedule "
                         f"({len(realized)} legs run, {len(want)} scheduled)")


def require_frozen(schedule, frozen_sha):
    if schedule_sha256(schedule) != frozen_sha:
        raise ValueError("the regenerated schedule differs from the frozen one (a changed chain needs a new out-root)")
