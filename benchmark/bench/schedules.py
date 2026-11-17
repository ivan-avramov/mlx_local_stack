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
# M76 (erratum v1.2, S22-P8): tg1 session s3 (seed 3003) exists ONLY under the M76 KV lever (`s3=True`); s3 is s1's shape (the
# picks in order, Python before Go), so the three sessions alternate the language order. Without the flag nothing changes.
TG1_SEEDS_M76 = dict(TG1_SEEDS, s3=3003)
PILOT_N = 5
SMOKE_PILOT_N, SMOKE_FULL_N = 1, 2
# ---- tg2
TG2_SEED = 6501
TG2_TIERS = {"screen": 10, "decider": 20}
TG2_SESSIONS = {"screen": ("s1",), "decider": ("s1", "s2", "reload")}
TG2_RELOAD_ITEMS = 5
# M76 B4b-1 (spec m76-b4b-tg2-runner v5): the committed draw / universe the tg2 P426 legs run; the draw file, its sidecar and the
# draw's universe sha must equal them (a consistent redraw refuses).
TG2_DRAW_SHA256 = "82875e1d3da7ce71bd7750ff5729874eefc2e5a40772e1bf4f82e71d3cf444e3"
TG2_UNIVERSE_SHA256 = "2bf6add47237d2f1f4135013e47eae07f35e1e668b935e18ec2768b7baadc3e9"
TG2_LANGS = ("rust", "javascript", "java", "cpp")
# leg -> (session dir, seed base, language order, items per language): the table of spec §2 (rehearsals r2 / r3 run s1's slot)
TG2_P426_LEGS = {
    "pilot": ("pilot", 1001, TG2_LANGS, 1),
    "s1": ("s1", 1001, TG2_LANGS, 20),
    "s2": ("s2", 2002, tuple(reversed(TG2_LANGS)), 20),
    "reload": ("reload", 1001, TG2_LANGS, 5),
    "r2": ("s1", 1001, ("rust",), 1),
    "r3": ("s1", 1001, ("rust",), 1),
}


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
def tg1_legs_table(picks, langs, p426=False, s3=False):
    """Per session the (model, language) legs: s1 the picks in the given order, s2 the picks reversed, reload the first pick's
    first language (any number of picks >= 1). P426 mode (spec 7): s2 also reverses the LANGUAGE order (Go before Python).
    `s3=True` (M76 only, P426 mode): s3 = s1's legs (the key exists only then)."""
    picks, langs = tuple(picks), tuple(langs)
    if not picks or len(set(picks)) != len(picks):
        raise ValueError(f"picks must be a nonempty list of distinct models, got {picks!r}")
    if s3 and not p426:
        raise ValueError("session s3 is an M76 (P426-mode) session")
    s2_langs = tuple(reversed(langs)) if p426 else langs
    table = {"s1": [(p, l) for p in picks for l in langs],
             "s2": [(p, l) for p in reversed(picks) for l in s2_langs],
             "reload": [(picks[0], langs[0])]}
    if s3:
        table["s3"] = list(table["s1"])
    return table


REHEARSAL_PILOT_N, REHEARSAL_FULL_N = 1, 3        # spec 16.3: one pilot item, then two full items (the smoke shape of the P426 order)
REHEARSAL_GO_N = 2                                # P589: then the first two items of s1's seeded Go order, one `full` invocation


def _tg1_leg(session, model, lang, seed_base, names, *, reload_ctl, smoke, predictor, first_leg, pilot_only, p426=False,
             rehearsal=False):
    pool = sorted(names[lang])
    if p426:
        # C223: the seeded order IS the run order (no later sort); the pilot phase and the reload are its first 5
        full = random.Random(seed_base).sample(pool, len(pool))
        pilot = full[:PILOT_N]
        if rehearsal:
            pilot, full = full[:REHEARSAL_PILOT_N], full[:REHEARSAL_FULL_N if first_leg else REHEARSAL_GO_N]
        elif reload_ctl:
            full = list(pilot)
    else:
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


def tg1(mode, sessions, names, *, picks, smoke=False, predictor="off", langs=("python", "go"), p426=False, rehearsal=False,
        s3=False):
    """The tg1 chain schedule (blocks of one model within one session, legs = languages) with disjoint invocations. `picks`
    (the chain's required `--models`, C221) has no default. `p426=True` (spec 7): each language's items in the seeded
    `random.Random(seed).sample(sorted(pool), len(pool))` order, s2 Go before Python; never with `smoke`. `rehearsal=True`
    (spec 16.3, P426 only): Python one pilot item then two full items, then Go's first `REHEARSAL_GO_N` items (one `full`
    invocation) of s1's seeded order (P589)."""
    langs, picks = tuple(langs), tuple(picks)
    if p426 and smoke:
        raise ValueError("a P426 schedule has no smoke shape")
    if rehearsal:
        if not p426 or smoke or mode != "chain" or list(sessions) != ["s1"]:
            raise ValueError("the rehearsal shape is one P426 `chain s1` leg (no smoke, no other session)")
    table = tg1_legs_table(picks, langs, p426, s3=s3)
    seeds = TG1_SEEDS_M76 if s3 else TG1_SEEDS
    if s3 and mode != "pilot":
        unknown = [s for s in sessions if s not in table]
        if unknown:
            raise ValueError(f"unknown tg1 session(s) {unknown}")
    out = []
    if mode == "pilot":
        leg = _tg1_leg("pilot", picks[0], langs[0], TG1_SEEDS["s1"], names, reload_ctl=False, smoke=False,
                       predictor=predictor, first_leg=True, pilot_only=True, p426=p426)
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
                legs_ = [_tg1_leg(s, model, lang, seeds[s], names, reload_ctl=(s == "reload"), smoke=smoke,
                                  predictor=predictor, first_leg=(i == 0), pilot_only=False, p426=p426, rehearsal=rehearsal)
                         for i, lang in enumerate(ls)]
                out.append(dict(session=s, model=model, seed_base=seeds[s], legs=legs_, pilot_only=False))
    doc = dict(schema=SCHEMA, builder="tg1", mode=mode, smoke=bool(smoke), predictor=predictor,
               picks=list(picks), blocks=out)
    if p426:
        doc["p426"] = True                       # only P426 schedules carry the key: the legacy dict (and its sha) is unchanged
    if rehearsal:
        doc["rehearsal"] = True
    if s3:
        doc["m76_s3"] = True                     # only M76 schedules carry the key (P426's dict and sha unchanged)
    return doc


# ---------------------------------------------------------------- the P426 make-up plan (spec 5.5, 16.8)
MAKEUP_SESSION_ORDER = ("s1", "s2")
MAKEUP_LANG_ORDER = {"s1": ("python", "go"), "s2": ("go", "python")}      # spec 7: s2 reverses the language order
MAKEUP_SESSION_ORDER_M76 = ("s1", "s2", "s3")                              # M76: s3 = s1's language order
MAKEUP_LANG_ORDER_M76 = dict(MAKEUP_LANG_ORDER, s3=("python", "go"))


def makeup_canonical(occurrences, s3=False):
    """The union of the occurrences, one record per (session, language, item, seed) with the DNF'd arms merged into a sorted list,
    in the canonical order: s1 then s2, the session's language order, `occurrence` (the item's 0-based position in its
    (session, language) order of that leg's frozen schedule), item. `s3=True` (M76): s1, s2, s3."""
    order, langs = (MAKEUP_SESSION_ORDER_M76, MAKEUP_LANG_ORDER_M76) if s3 else (MAKEUP_SESSION_ORDER, MAKEUP_LANG_ORDER)
    merged = {}
    for o in occurrences:
        session, lang = o["session"], o["language"]
        if session not in order or lang not in langs[session]:
            raise ValueError(f"occurrence {o!r}: unknown session / language")
        arms = [o["arm_of_dnf"]] if isinstance(o["arm_of_dnf"], str) else list(o["arm_of_dnf"])
        m = merged.setdefault((session, lang, o["item"], o["seed"]),
                              dict(session=session, language=lang, item=o["item"], seed=o["seed"], arm_of_dnf=set(),
                                   occurrence=o["occurrence"]))
        m["arm_of_dnf"].update(arms)
        m["occurrence"] = min(m["occurrence"], o["occurrence"])
    out = sorted(merged.values(), key=lambda m: (order.index(m["session"]),
                                                 langs[m["session"]].index(m["language"]), m["occurrence"], m["item"]))
    return [dict(m, arm_of_dnf=sorted(m["arm_of_dnf"])) for m in out]


def tg1_makeup(occurrences, names, *, picks, predictor="off", s3=False):
    """The make-up leg's schedule: ONE load of the entry (a fresh-load leg); inside it one leg (= one probe invocation) per
    (session, seed, language) group in the canonical order, the items in `occurrence` order. The plan is the union. `s3=True`
    (M76): s3 occurrences are allowed (the schedule then carries `m76_s3`)."""
    picks = tuple(picks)
    if len(picks) != 1:
        raise ValueError("a make-up leg runs exactly one model")
    canon = makeup_canonical(occurrences, s3=s3)
    if not canon:
        raise ValueError("a make-up leg needs at least one occurrence")
    groups = {}
    for m in canon:
        if m["item"] not in set(names.get(m["language"], ())):
            raise ValueError(f"occurrence item {m['language']}/{m['item']} is not in the corpus")
        groups.setdefault((m["session"], m["seed"], m["language"]), []).append(m["item"])
    model = picks[0]
    legs = []
    for (session, seed, lang), items in groups.items():
        legs.append(dict(session=session, model=model, lang=lang, seed_base=seed, stem=f"{model}.makeup.opencode_{session}_{lang}",
                         pilot_names=[], full_names=list(items), draft_kind=predictor,
                         invocations=[dict(phase="full", names=list(items), limit=None, expect=[f"{lang}/{n}" for n in items])]))
    block = dict(session="makeup", model=model, seed_base=legs[0]["seed_base"], legs=legs, pilot_only=False)
    doc = dict(schema=SCHEMA, builder="tg1", mode="makeup", smoke=False, predictor=predictor, picks=list(picks), blocks=[block],
               p426=True, makeup=True)
    if s3:
        doc["m76_s3"] = True
    return doc


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


def _tg2_pins(draw_doc):
    """The committed draw: its canonical bytes hash to `TG2_DRAW_SHA256`, it names `TG2_UNIVERSE_SHA256`, seed 6501, the four
    tg2 languages, each tier a prefix of the permutation. A redraw that is self-consistent still refuses (the pins)."""
    if not isinstance(draw_doc, dict):
        raise TransportAbort("the tg2 draw is not a document")
    if draw_sha256_of(draw_doc) != TG2_DRAW_SHA256:
        raise TransportAbort("the tg2 draw differs from the pinned sha256 (TG2_DRAW_SHA256; never redrawn)")
    if draw_doc.get("universe_sha256") != TG2_UNIVERSE_SHA256:
        raise TransportAbort("the tg2 draw names another universe than the pinned TG2_UNIVERSE_SHA256")
    _tg2_check_draw(draw_doc, TG2_DRAW_SHA256, "decider")
    if sorted(draw_doc["languages"]) != sorted(TG2_LANGS):
        raise TransportAbort("the tg2 draw's languages are not %s" % (sorted(TG2_LANGS),))
    for lang, entry in draw_doc["languages"].items():
        for tier in TG2_TIERS:
            _tg2_items(entry, lang, tier)


def tg2_p426(draw_doc, leg, model, predictor):
    """M76 B4b-1 (E12): one tg2 P426 leg in tg1's P426 document shape (`blocks[].legs[].invocations[]`): one block, one schedule
    leg per (session, language) in the table's language order, each with ONE `full` invocation of that language's first `n`
    items in the draw's permutation order (`TG2_P426_LEGS`). The pins are verified first."""
    if leg not in TG2_P426_LEGS:
        raise ValueError(f"unknown tg2 leg {leg!r} (one of {sorted(TG2_P426_LEGS)})")
    _tg2_pins(draw_doc)
    session, seed, order, n = TG2_P426_LEGS[leg]
    legs_ = []
    for lang in order:
        items = list(draw_doc["languages"][lang]["permutation"][:n])
        if len(items) != n:
            raise TransportAbort(f"the tg2 draw has fewer than {n} {lang} items")
        names = [i.split("/", 1)[1] for i in items]
        legs_.append(dict(session=session, model=model, lang=lang, seed_base=seed, stem=flat_stem(model, session, lang),
                          pilot_names=[], full_names=list(names), draft_kind=predictor,
                          invocations=[dict(phase="full", names=list(names), limit=None, expect=list(items))]))
    block = dict(session=session, model=model, seed_base=seed, legs=legs_, pilot_only=False)
    return dict(schema=SCHEMA, builder="tg2_p426", mode="pilot" if leg == "pilot" else "chain", smoke=False,
                predictor=predictor, picks=[model], blocks=[block], p426=True, corpus="tg2", tg2_leg=leg,
                draw_sha256=TG2_DRAW_SHA256, universe_sha256=TG2_UNIVERSE_SHA256)


def check_tg2_p426(schedule, draw_doc, leg):
    """The frozen tg2 leg schedule re-derived from the (pinned) draw: equal, or `TransportAbort` (called before every language
    leg's launch)."""
    try:
        model, predictor = schedule["picks"][0], schedule["predictor"]
    except (KeyError, IndexError, TypeError):
        raise TransportAbort("the tg2 schedule names no model / predictor") from None
    if schedule.get("tg2_leg") != leg:
        raise TransportAbort(f"the tg2 schedule is leg {schedule.get('tg2_leg')!r}, not {leg!r}")
    if tg2_p426(draw_doc, leg, model, predictor) != schedule:
        raise TransportAbort("the tg2 schedule differs from the pinned draw's prefix (table, order or items)")


# ---------------------------------------------------------------- common: hash, legs, keys, checks
def schedule_sha256(schedule):
    return hashlib.sha256(json.dumps(schedule, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def legs(schedule):
    """Every leg of the schedule in launch order (a `blocks` leg is one (block, arm); a tg1 leg one (model, lang) of a
    block; a tg2 leg one (session, lang))."""
    out = []
    if schedule.get("builder") in ("tg1", "tg2_p426"):           # M76 B4b-1: the tg2 P426 leg has tg1's P426 shape
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
