"""M64 spec 8.1: the seeded block schedule. Pure, deterministic, hashed before launch and checked after.

Per pick, per session (s1 seed 1001, s2 seed 2002: distinct paired schedules), per language: the cell's items in a seeded
order, split into blocks of 3 (Python 22 = 7 blocks + 1 residual item, Go 21 = 7 blocks); each block runs EVERY arm on its
items, in one permutation of the arms; permutations are balanced within the cell by a seeded allocation (7 blocks over 6
permutations: each once plus one drawn; the residual item draws its own by the same seed). One worker load serves a
(session, pick) with all its arms; the reload control is pick 1, Python, the first five s1 items, the s1 seed, on a fresh
load. A leg is one (block, arm): the unit the chain launches, restarting the shared search service before it.

Judgement calls the spec leaves open (recorded in the schedule so they are hashed): the item order is seeded by
(session seed, pick, language), so the two picks see different orders; the reload items are the first five of the s1
pick-1 Python order."""
from __future__ import annotations

import hashlib
import itertools
import json
import random

from . import arm_adapter as aa

SCHEMA = 1
BLOCK_SIZE = 3
SESSION_SEEDS = {"s1": 1001, "s2": 2002}
RELOAD_SEED = 1001
RELOAD_ITEMS = 5
SMOKE_ITEMS = 4                 # a full block and a residual item
LANGS = ("python", "go")
PICK1 = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
PICK2 = "Qwen3.8-27B-mlx-uniform-4bit"
DERIVATION = "order=Random(sha256('m64-order|seed|pick|lang')).shuffle(sorted(names)); perms=Random(sha256('m64-perm|seed|pick|lang'))"


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
    blocks = [dict(i=i, items=c, arms=list(p)) for i, (c, p) in enumerate(zip(full, seq))]
    blocks += [dict(i=len(blocks) + j, items=c, arms=list(residual_perm)) for j, c in enumerate(rest)]
    return dict(lang=lang, order=list(order), blocks=blocks)


def build(arms, names, *, picks=(PICK1, PICK2), sessions=("s1", "s2"), reload_control=True, smoke=False):
    arms = tuple(arms)
    if not arms or len(set(arms)) != len(arms):
        raise ValueError(f"arms must be a nonempty list of distinct arms, got {arms!r}")
    for arm in arms:
        if not aa.valid_arm_id(arm):
            raise ValueError(f"unknown arm {arm!r}")
    loads, first = [], {}
    for session in sessions:
        seed = SESSION_SEEDS[session]
        for pick in (picks if session == "s1" else tuple(reversed(picks))):
            cells = []
            for lang in LANGS:
                order = item_order(names[lang], seed, pick, lang)
                if smoke:
                    order = order[:SMOKE_ITEMS]
                cells.append(_cell(arms, order, seed, pick, lang))
                first[(session, pick, lang)] = cells[-1]["order"]
            loads.append(dict(session=session, pick=pick, seed_base=seed, cells=cells))
    if reload_control:
        order = first[("s1", picks[0], "python")][:RELOAD_ITEMS]
        loads.append(dict(session="reload", pick=picks[0], seed_base=RELOAD_SEED,
                          cells=[_cell(arms, order, RELOAD_SEED, picks[0], "python")]))
    return dict(schema=SCHEMA, arms=list(arms), block_size=BLOCK_SIZE, seeds=dict(SESSION_SEEDS, reload=RELOAD_SEED),
                derivation=DERIVATION, smoke=bool(smoke), loads=loads)


def schedule_sha256(schedule):
    return hashlib.sha256(json.dumps(schedule, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def legs(schedule):
    """Every (block, arm) of the schedule in launch order."""
    out = []
    for li, load in enumerate(schedule["loads"]):
        for cell in load["cells"]:
            for block in cell["blocks"]:
                for arm in block["arms"]:
                    out.append(dict(index=len(out), load=li, session=load["session"], pick=load["pick"],
                                    seed_base=load["seed_base"], lang=cell["lang"], block=block["i"], arm=arm,
                                    items=list(block["items"]), residual=len(block["items"]) < BLOCK_SIZE))
    return out


def leg_key(leg):
    return [leg["load"], leg["lang"], leg["block"], leg["arm"], list(leg["items"])]


def check_realized(schedule, realized):
    want = [leg_key(leg) for leg in legs(schedule)]
    if [list(r) for r in realized] != want:
        raise ValueError("realized order differs from the frozen schedule "
                         f"({len(realized)} legs run, {len(want)} scheduled)")


def require_frozen(schedule, frozen_sha):
    if schedule_sha256(schedule) != frozen_sha:
        raise ValueError("the regenerated schedule differs from the frozen one (a changed chain needs a new out-root)")
