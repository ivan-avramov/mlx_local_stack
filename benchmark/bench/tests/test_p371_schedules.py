"""P371 phase 1: `bench.schedules` (plan 3.1, 4 A1 / A8, P376): pure hashed builders absorbing `m64_schedule`."""
from __future__ import annotations

import collections
import hashlib
import importlib.util
import itertools
import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

from bench import arm_adapter as aa
from bench import chain_ops as co
from bench import schedules as sch
from bench.token_turn_gate import TransportAbort

REPO = Path(__file__).resolve().parents[3]
PICK1, PICK2 = co.PICK1, co.PICK2
ARMS3 = ("oc", "pi", "dsh")
NAMES = {"python": [f"p{i:02d}" for i in range(22)], "go": [f"g{i:02d}" for i in range(21)]}
LANGS4 = ("rust", "java", "javascript", "cpp")


def load_chain(name, rel):
    spec = importlib.util.spec_from_file_location(name + "_p371", REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(REPO / "benchmark"))
    spec.loader.exec_module(mod)
    return mod


C147 = load_chain("run_tg1_chain", "benchmark/chains/c147/run_tg1_chain.py")


# ---------------------------------------------------------------- constants copied from today's modules
def test_the_constants_equal_the_modules_they_absorb():
    assert (sch.SESSION_SEEDS, sch.RELOAD_SEED, sch.RELOAD_ITEMS, sch.BLOCK_SIZE, sch.SMOKE_ITEMS) == (
        {"s1": 1001, "s2": 2002}, 1001, 5, 3, 4)
    assert sch.DERIVATION == ("order=Random(sha256('m64-order|seed|pick|lang')).shuffle(sorted(names)); "
                              "perms=Random(sha256('m64-perm|seed|pick|lang'))")
    assert sch.ARM_IDS == aa.ARM_IDS and (sch.PICK1, sch.PICK2) == (PICK1, PICK2)
    assert sch.TG1_SEEDS == C147.SEEDS and sch.PILOT_N == C147.PILOT_N
    assert (sch.SMOKE_PILOT_N, sch.SMOKE_FULL_N) == (C147.SMOKE_PILOT_N, C147.SMOKE_FULL_N)


def test_the_module_is_pure():
    code = ("import sys; import bench.schedules; print([m for m in sys.modules if m in ('bench.arm_adapter',"
            "'bench.chain_ops','bench.corpus_tg1','bench.proc_guard','bench.arm_opencode')])")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO / "benchmark", capture_output=True, text=True)
    assert out.stdout.strip() == "[]", out.stderr


# ---------------------------------------------------------------- blocks == the pre-3b m64_schedule.build (pinned golden)
GOLDEN = json.loads((REPO / "benchmark/bench/tests/fixtures/p371_blocks_golden.json").read_text())["cases"]
CASES = {"default": dict(), "smoke": dict(smoke=True), "no_reload": dict(reload_control=False),
         "s1_only": dict(sessions=("s1",)), "arms_oc_pi": dict(arms=("oc", "pi")), "arms_oc": dict(arms=("oc",))}


@pytest.mark.parametrize("case", sorted(CASES))
def test_blocks_reproduces_the_retired_m64_schedule_build_exactly_for_the_tg1_corpus(case):
    kw = dict(CASES[case])
    arms = kw.pop("arms", ARMS3)
    new = sch.blocks(arms, NAMES, picks=(PICK1, PICK2), **kw)
    legs = sch.legs(new)
    want = GOLDEN[case]
    assert sch.schedule_sha256(new) == want["schedule_sha256"] and len(legs) == want["legs"]
    assert hashlib.sha256(json.dumps([sch.leg_key(l) for l in legs], sort_keys=True).encode()).hexdigest() == want["leg_keys_sha256"]
    assert hashlib.sha256(json.dumps(legs, sort_keys=True).encode()).hexdigest() == want["legs_sha256"]


def test_m64_schedule_is_retired_no_module_imports_it():
    assert not (REPO / "benchmark/bench/m64_schedule.py").exists()
    for path in (REPO / "benchmark").rglob("*.py"):
        if "/tests/" in str(path) or ".venv" in str(path):
            continue
        assert "m64_schedule" not in path.read_text(), path


def test_blocks_refuses_what_the_old_builder_refused():
    for arms in ((), ("oc", "oc"), ("oc", "bogus")):
        with pytest.raises(ValueError):
            sch.blocks(arms, NAMES, picks=(PICK1, PICK2))
    with pytest.raises(ValueError):
        sch.blocks(ARMS3, {"python": NAMES["python"]}, picks=(PICK1, PICK2))           # no names for `go`
    with pytest.raises(ValueError):
        sch.blocks(ARMS3, NAMES, picks=(PICK1, PICK2), reload_langs=("rust",))          # reload lang not scheduled


# ---------------------------------------------------------------- generalized: any language list
def names4(n=10):
    return {lang: [f"{lang[:2]}{i:02d}" for i in range(n)] for lang in LANGS4}


def test_four_language_corpus_cells_are_sized_from_the_data():
    s = sch.blocks(ARMS3, names4(10), picks=(PICK1, PICK2), sessions=("s1",), langs=LANGS4, reload_control=False)
    assert [l["session"] for l in s["loads"]] == ["s1", "s1"]
    for load in s["loads"]:
        assert [c["lang"] for c in load["cells"]] == list(LANGS4)
        for cell in load["cells"]:
            assert [len(b["items"]) for b in cell["blocks"]] == [3, 3, 3, 1]          # 10 = 3 blocks + 1 residual
            assert sorted(i for b in cell["blocks"] for i in b["items"]) == sorted(names4()[cell["lang"]])


def test_four_language_permutations_are_balanced_per_cell_and_hashes_stable():
    s1 = sch.blocks(ARMS3, names4(), picks=(PICK1, PICK2), sessions=("s1", "s2"), langs=LANGS4, reload_langs=LANGS4)
    s2 = sch.blocks(ARMS3, names4(), picks=(PICK1, PICK2), sessions=("s1", "s2"), langs=LANGS4, reload_langs=LANGS4)
    assert sch.schedule_sha256(s1) == sch.schedule_sha256(s2)
    perms = set(itertools.permutations(ARMS3))
    for load in s1["loads"]:
        for cell in load["cells"]:
            full = [tuple(b["arms"]) for b in cell["blocks"] if len(b["items"]) == 3]
            assert len(set(full)) == len(full)                                        # 3 blocks over 6 perms: distinct
            assert set(full) <= perms
    reload = s1["loads"][-1]
    assert reload["session"] == "reload" and [c["lang"] for c in reload["cells"]] == list(LANGS4)
    assert all(len(c["order"]) == 5 for c in reload["cells"])
    for cell in reload["cells"]:                                                      # first five of the s1 pick-1 order
        first = s1["loads"][0]["cells"][LANGS4.index(cell["lang"])]
        assert cell["order"] == first["order"][:5]


def test_a_changed_input_changes_the_hash_and_realized_order_is_checked():
    base = sch.blocks(ARMS3, names4(), picks=(PICK1, PICK2), sessions=("s1",), langs=LANGS4, reload_control=False)
    other = sch.blocks(ARMS3, names4(11), picks=(PICK1, PICK2), sessions=("s1",), langs=LANGS4, reload_control=False)
    assert sch.schedule_sha256(base) != sch.schedule_sha256(other)
    sch.require_frozen(base, sch.schedule_sha256(base))
    with pytest.raises(ValueError):
        sch.require_frozen(other, sch.schedule_sha256(base))
    realized = [sch.leg_key(l) for l in sch.legs(base)]
    sch.check_realized(base, realized)
    for broken in (realized[:-1], realized[::-1], [realized[0]] + realized[2:]):
        with pytest.raises(ValueError):
            sch.check_realized(base, broken)


# ---------------------------------------------------------------- tg1 builder (semantics of run_tg1_chain, disjoint invocations)
TG1_NAMES = {"python": [f"p{i:02d}" for i in range(22)], "go": [f"g{i:02d}" for i in range(21)]}
PAIR = (PICK1, PICK2)                     # C221: the tg1 builder / runner schedule take their models (no default pair)


@pytest.mark.parametrize("mode,sessions,smoke", [("chain", ("s1", "s2", "reload"), False),
                                                 ("chain", ("s1", "reload"), True), ("pilot", ("s1",), False),
                                                 ("chain", ("s2",), False)])
def test_tg1_blocks_and_legs_match_run_tg1_chain_schedule(mode, sessions, smoke):
    old = C147.schedule(mode, sessions, TG1_NAMES, "/out", models=PAIR, smoke=smoke, predictor="mtp")
    new = sch.tg1(mode, sessions, TG1_NAMES, picks=PAIR, smoke=smoke, predictor="mtp")
    assert new["builder"] == "tg1" and len(new["blocks"]) == len(old)
    for ob, nb in zip(old, new["blocks"]):
        assert (nb["session"], nb["model"], nb["seed_base"], nb["pilot_only"]) == (
            ob["session"], ob["model"], ob["seed_base"], ob["pilot_only"])
        assert len(nb["legs"]) == len(ob["legs"])
        for ol, nl in zip(ob["legs"], nb["legs"]):
            for key in ("session", "model", "lang", "seed_base", "stem", "pilot_names", "full_names", "draft_kind"):
                assert nl[key] == ol[key], key


@pytest.mark.parametrize("mode,sessions,smoke", [("chain", ("s1", "s2", "reload"), False),
                                                 ("chain", ("s1", "reload"), True), ("pilot", ("s1",), False)])
def test_tg1_invocations_are_the_old_steps_made_disjoint(mode, sessions, smoke):
    old = C147.schedule(mode, sessions, TG1_NAMES, "/out", models=PAIR, smoke=smoke)
    new = sch.tg1(mode, sessions, TG1_NAMES, picks=PAIR, smoke=smoke)
    for ob, nb in zip(old, new["blocks"]):
        for i, (ol, nl) in enumerate(zip(ob["legs"], nb["legs"])):
            steps = C147.steps_for(ob, i)
            invs = nl["invocations"]
            assert [s["kind"] for s in steps] == [v["phase"] for v in invs]
            for s, v in zip(steps, invs):
                assert v["limit"] == s["limit"]
                if s["kind"] == "pilot":
                    assert v["names"] == s["names"]
                elif i == 0 and len(steps) == 2:             # a full after a pilot: the cell minus the pilot's items
                    assert v["names"] == [n for n in s["names"] if n not in ol["pilot_names"]]
                else:
                    assert v["names"] == s["names"]
            flat = [n for v in invs for n in v["names"]]
            assert len(flat) == len(set(flat))                # disjoint: no item is run twice
            assert set(flat) == set(steps[-1]["names"])        # and the leg's whole cell is covered
            for v in invs:
                assert v["expect"] == [f"{nl['lang']}/{n}" for n in v["names"]]


def test_tg1_phase_shapes_pilot_only_pilot_plus_full_full_only_and_smoke():
    s = sch.tg1("chain", ("s1", "reload"), TG1_NAMES, picks=PAIR)
    s1p1, s1p2 = s["blocks"][0], s["blocks"][1]
    py, go = s1p1["legs"]
    assert [v["phase"] for v in py["invocations"]] == ["pilot", "full"]                  # (b)
    assert len(py["invocations"][0]["names"]) == 5 and len(py["invocations"][1]["names"]) == 17
    assert [v["phase"] for v in go["invocations"]] == ["full"] and len(go["invocations"][0]["names"]) == 21   # (c)
    reload = s["blocks"][-1]["legs"][0]
    assert [v["phase"] for v in reload["invocations"]] == ["pilot"]                       # (a) pilot == full
    assert sch.tg1("pilot", ("s1",), TG1_NAMES, picks=PAIR)["blocks"][0]["legs"][0]["invocations"][0]["phase"] == "pilot"
    smoke = sch.tg1("chain", ("s1",), TG1_NAMES, picks=PAIR, smoke=True)["blocks"][0]["legs"][0]["invocations"]   # (d)
    assert [(v["phase"], len(v["names"])) for v in smoke] == [("pilot", 1), ("full", 1)]


def test_tg1_keeps_the_seeded_pilot_draw_and_order():
    s = sch.tg1("chain", ("s1",), TG1_NAMES, picks=PAIR)
    leg = s["blocks"][0]["legs"][0]
    assert leg["pilot_names"] == sorted(random.Random(1001).sample(sorted(TG1_NAMES["python"]), 5))
    assert leg["full_names"] == sorted(TG1_NAMES["python"])
    full = leg["invocations"][1]["names"]
    assert full == [n for n in leg["full_names"] if n not in leg["pilot_names"]]          # the old order, minus the pilot


def test_tg1_legs_and_realized_order():
    s = sch.tg1("chain", ("s1", "s2", "reload"), TG1_NAMES, picks=PAIR)
    legs = sch.legs(s)
    assert [l["index"] for l in legs] == list(range(len(legs))) and len(legs) == 9
    assert (legs[0]["session"], legs[0]["lang"], legs[0]["model"]) == ("s1", "python", PICK1)
    sch.check_realized(s, [sch.leg_key(l) for l in legs])
    with pytest.raises(ValueError):
        sch.check_realized(s, [sch.leg_key(l) for l in legs][:-1])
    assert sch.schedule_sha256(s) == sch.schedule_sha256(sch.tg1("chain", ("s1", "s2", "reload"), TG1_NAMES, picks=PAIR))
    assert sch.schedule_sha256(s) != sch.schedule_sha256(sch.tg1("chain", ("s1", "s2", "reload"), TG1_NAMES, picks=PAIR,
                                                               predictor="mtp"))
    assert "/out" not in json.dumps(s)                    # a schedule holds no paths


# ---------------------------------------------------------------- tg2_tier
def make_draw(n_actual=None, seed=6501):
    n_actual = n_actual or {l: 25 for l in LANGS4}
    languages = {}
    for lang in LANGS4:
        valid = sorted(f"{lang}/ex{i:02d}" for i in range(n_actual[lang]))
        perm = random.Random(seed).sample(valid, len(valid))
        languages[lang] = dict(N_actual=len(valid), permutation=perm, screen=perm[:10], decider=perm[:20])
    doc = dict(seed=seed, tiers=dict(screen=10, decider=20), universe_sha256="u" * 64, languages=languages,
               needs_operator_acknowledgement={l: n for l, n in n_actual.items() if n < 20})
    return doc


def draw_sha(doc):
    return hashlib.sha256((json.dumps(doc, sort_keys=True, indent=1) + "\n").encode()).hexdigest()


def test_tg2_screen_is_s1_only_ten_per_language_and_decider_is_s1_s2_reload():
    doc = make_draw()
    sha = draw_sha(doc)
    screen = sch.tg2_tier(doc, sha, "screen")
    assert [s["session"] for s in screen["sessions"]] == ["s1"] and screen["tier"] == "screen"
    assert screen["draw_sha256"] == sha and screen["builder"] == "tg2_tier"
    for cell in screen["sessions"][0]["cells"]:
        assert cell["items"] == doc["languages"][cell["lang"]]["permutation"][:10]
    decider = sch.tg2_tier(doc, sha, "decider")
    assert [(s["session"], s["seed_base"]) for s in decider["sessions"]] == [("s1", 1001), ("s2", 2002), ("reload", 1001)]
    for sess in decider["sessions"]:
        for cell in sess["cells"]:
            perm = doc["languages"][cell["lang"]]["permutation"]
            assert cell["items"] == perm[:5 if sess["session"] == "reload" else 20]
    s1 = {c["lang"]: c["items"] for c in screen["sessions"][0]["cells"]}
    d1 = {c["lang"]: c["items"] for c in decider["sessions"][0]["cells"]}
    assert all(d1[l][:10] == s1[l] for l in LANGS4)                                   # nested prefixes


def test_tg2_never_redraws():
    doc = make_draw()
    sha = draw_sha(doc)
    real = random.Random
    random.Random = lambda *a, **k: (_ for _ in ()).throw(AssertionError("redrew"))
    try:
        sch.tg2_tier(doc, sha, "decider")
    finally:
        random.Random = real


def test_tg2_refuses_a_sha_mismatch_unknown_tier_and_a_broken_prefix():
    doc = make_draw()
    sha = draw_sha(doc)
    with pytest.raises(TransportAbort):
        sch.tg2_tier(doc, "0" * 64, "screen")
    with pytest.raises(TransportAbort):
        sch.tg2_tier(doc, sha, "bogus")
    broken = json.loads(json.dumps(doc))
    broken["languages"]["rust"]["screen"] = list(reversed(broken["languages"]["rust"]["screen"]))
    with pytest.raises(TransportAbort):
        sch.tg2_tier(broken, draw_sha(broken), "screen")
    wrong_seed = make_draw(seed=1)
    with pytest.raises(TransportAbort):
        sch.tg2_tier(wrong_seed, draw_sha(wrong_seed), "screen")


def test_tg2_refuses_sessions_that_do_not_belong_to_the_tier():
    doc = make_draw()
    sha = draw_sha(doc)
    with pytest.raises(TransportAbort):
        sch.tg2_tier(doc, sha, "screen", sessions=("s1", "s2"))
    with pytest.raises(TransportAbort):
        sch.tg2_tier(doc, sha, "decider", sessions=("s1",))
    assert sch.tg2_tier(doc, sha, "screen", sessions=("s1",)) == sch.tg2_tier(doc, sha, "screen")


def test_tg2_decider_needs_acknowledgement_for_a_short_language():
    doc = make_draw({"rust": 25, "java": 25, "javascript": 25, "cpp": 12})
    sha = draw_sha(doc)
    with pytest.raises(TransportAbort, match="acknowledg"):
        sch.tg2_tier(doc, sha, "decider")
    out = sch.tg2_tier(doc, sha, "decider", acknowledged=("cpp",))
    cpp = [c for c in out["sessions"][0]["cells"] if c["lang"] == "cpp"][0]
    assert len(cpp["items"]) == 12
    assert all(len(c["items"]) == 10 for c in sch.tg2_tier(doc, sha, "screen")["sessions"][0]["cells"])


def test_tg2_membership_is_verified_at_every_leg():
    doc = make_draw()
    sha = draw_sha(doc)
    s = sch.tg2_tier(doc, sha, "decider")
    sch.check_tg2_membership(s, doc, sha)
    for leg in sch.legs(s):
        sch.check_tg2_membership(s, doc, sha, leg=leg)
    s["sessions"][0]["cells"][0]["items"] = s["sessions"][0]["cells"][0]["items"][::-1]
    with pytest.raises(TransportAbort):
        sch.check_tg2_membership(s, doc, sha)
    with pytest.raises(TransportAbort):
        sch.check_tg2_membership(sch.tg2_tier(doc, sha, "screen"), doc, "f" * 64)


def test_tg2_legs_and_the_m64_oc_tg2_schedule_over_the_screen_prefix():
    doc = make_draw()
    sha = draw_sha(doc)
    legs = sch.legs(sch.tg2_tier(doc, sha, "decider"))
    assert [(l["session"], l["lang"]) for l in legs][:4] == [("s1", l) for l in sorted(LANGS4)]    # sorted: data-derived
    assert len(legs) == 12 and legs[0]["items"] == doc["languages"][legs[0]["lang"]]["permutation"][:20]
    names = sch.tg2_prefix_names(doc, sha, "screen")
    assert set(names) == set(LANGS4) and all(len(v) == 10 for v in names.values())
    assert names["rust"][0] == doc["languages"]["rust"]["permutation"][0].split("/", 1)[1]
    s = sch.blocks(("oc", "pi"), names, picks=(PICK1, PICK2), sessions=("s1",), langs=LANGS4, reload_control=False)
    assert [len(c["blocks"]) for c in s["loads"][0]["cells"]] == [4] * 4
    sch.check_realized(s, [sch.leg_key(l) for l in sch.legs(s)])


def test_the_real_frozen_draw_sha_formula_matches_the_stored_sidecar():
    try:
        raw = subprocess.run(["git", "show", "tg2-step2:benchmark/m65/tg2_draw.json"], cwd=REPO, capture_output=True,
                             check=True).stdout
        side = subprocess.run(["git", "show", "tg2-step2:benchmark/m65/tg2_draw.json.sha256"], cwd=REPO,
                              capture_output=True, check=True).stdout.decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("branch tg2-step2 (the frozen tg2 draw) is not available in this clone")
    doc = json.loads(raw)
    assert draw_sha(doc) == side == hashlib.sha256(raw).hexdigest()
    out = sch.tg2_tier(doc, side, "screen")
    assert [len(c["items"]) for c in out["sessions"][0]["cells"]] == [10, 10, 10, 10]
