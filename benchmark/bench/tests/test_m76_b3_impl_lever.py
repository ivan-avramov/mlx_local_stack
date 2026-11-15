"""M76 B3 / B5 acceptance 1 (lever kv): the KV registry and argv deltas on the REAL registry texts of the M76 arms, both arms MTP
ON, the `s3` pins, the `m76` names and paths, the Math500 300 nested ids, the A5 items and their offline token-budget check, and
the KV leg planner. Mocked ops only (no router, no model)."""
from __future__ import annotations

import json
import random
import subprocess
from pathlib import Path

import pytest

from bench import m76_ids as M
from bench import p426_ids
from bench import p426_plan as P

BENCH = Path(__file__).resolve().parents[2]
REPO = BENCH.parent
ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
DRAFTER = f"caslca/{ENTRY}-mtp-drafter"
REFS = {"n16": "89205085", "x": "origin/m76-f45-x", "v": "origin/m76-f45-v", "xo": "origin/m76-f45-xo"}


_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "m76_b3_fe"
_FIXTURE_ARM = {"89205085": "n16", "origin/m76-f45-x": "x", "origin/m76-f45-v": "v", "origin/m76-f45-xo": "xo"}


def _show(ref, path="main_models.yaml"):
    """The arm's committed registry: the sha256-pinned fixture copy (`fixtures/m76_b3_fe/`, checked against its source revision by
    `test_m76_b3_registry_fixtures_pinned.py`) — so the test runs on any clone, not only where the local `m76-f45-*` branches exist
    (S23-P93); any other ref / path from git."""
    arm = _FIXTURE_ARM.get(ref)
    if arm and path == "main_models.yaml":
        data = (_FIXTURES / f"{arm}_main_models.yaml").read_bytes()
        return data.decode()
    r = subprocess.run(["git", "-C", str(REPO), "show", f"{ref}:{path}"], capture_output=True)
    if r.returncode:
        pytest.skip(f"{ref} is not in this repository's objects")
    data = r.stdout
    return data.decode()


@pytest.fixture(scope="module")
def reg():
    return {arm: _show(ref) for arm, ref in REFS.items()}


def worker_argv(arm, wt="/wd/worktrees/m76-f45-x"):
    """The worker argv mlx-serve builds for an M76 arm (the spelling of `test_m76_b1_impl_support.worker_argv45`)."""
    argv = [f"{wt}/.venv/bin/mlx_vlm.server", "--model", f"caslca/{ENTRY}", "--host", "127.0.0.1", "--port", "8091",
            "--max-kv-size", "262144", "--kv-prealloc-tokens", "262144"]
    if arm != "n16":
        argv += ["--kv-bits", "4"]
    argv += ["--kv-quant-scheme", "turboquant", "--prefill-step-size", "512", "--attention-policy", "fused_v1"]
    if arm != "n16":
        argv += ["--tq4-attention", {"x": "m72_exact", "v": "m72_v1"}[arm]]
    argv += ["--generation-defaults", json.dumps({"temperature": 0.5, "top_p": 0.95})]
    argv += ["--mtp-verify-scan", "joint_v1", "--draft-kind", "mtp", "--draft-model", DRAFTER]
    return argv


# ------------------------------------------------------------------------------------------------ registry delta
@pytest.mark.parametrize("pair", P.KV_PAIRS)
def test_kv_registry_delta_accepted_on_the_real_arm_texts(reg, pair):
    a, b = pair
    assert P.kv_registry_delta_problems(reg[a], reg[b], ENTRY, a, b) == []
    assert P.kv_registry_delta_problems(reg[b], reg[a], ENTRY, b, a) == []


@pytest.mark.parametrize("arm", ["n16", "x", "v"])
def test_each_real_arm_is_its_label_and_mtp_on(reg, arm):
    assert P.kv_registry_problems(reg[arm], ENTRY, arm) == []
    other = {"n16": "x", "x": "v", "v": "n16"}[arm]
    assert P.kv_registry_problems(reg[arm], ENTRY, other)             # a mislabelled arm refuses


def test_kv_delta_refused_when_an_mtp_key_differs(reg):
    # the real XO arm (MTP commented out) is not an MTP-ON KV arm
    got = P.kv_registry_delta_problems(reg["x"], reg["xo"], ENTRY, "x", "x")
    assert got and "one KV state" in got[0]
    got = P.kv_registry_delta_problems(reg["n16"], reg["xo"], ENTRY, "n16", "x")
    assert any("MTP ON" in p for p in got) and any("an MTP key" in p for p in got)
    changed = reg["x"].replace("    mtp_verify_scan: joint_v1\n", "    mtp_verify_scan: per_query\n", 1)
    assert changed != reg["x"]
    got = P.kv_registry_delta_problems(reg["n16"], changed, ENTRY, "n16", "x")
    assert any("mtp_verify_scan differs" in p and "an MTP key" in p for p in got)


def _in_entry(text, old, new):
    """Replace `old` once inside the entry's block only."""
    at = text.index(f"  - name: {ENTRY}\n")
    head, tail = text[:at], text[at:]
    assert old in tail
    return head + tail.replace(old, new, 1)


def test_kv_delta_refused_when_a_non_kv_key_differs(reg):
    changed = _in_entry(reg["x"], "    kv_quant_scheme: turboquant\n", "    kv_quant_scheme: uniform\n")
    got = P.kv_registry_delta_problems(reg["n16"], changed, ENTRY, "n16", "x")
    assert any("kv_quant_scheme differs" in p and "a non-KV key" in p for p in got)
    other = _in_entry(reg["x"], "max_kv_cache_size: 262144", "max_kv_cache_size: 131072")
    assert any("max_kv_cache_size differs" in p for p in P.kv_registry_delta_problems(reg["n16"], other, ENTRY, "n16", "x"))
    elsewhere = reg["x"].replace("    kv_quant_scheme: turboquant\n", "    kv_quant_scheme: uniform\n", 1)
    if elsewhere.index("kv_quant_scheme: uniform") < elsewhere.index(f"  - name: {ENTRY}\n"):
        assert any("settings differ between the arms" in p
                   for p in P.kv_registry_delta_problems(reg["n16"], elsewhere, ENTRY, "n16", "x"))


def test_kv_delta_refused_for_a_stray_comment_or_a_second_note(reg):
    stray = reg["x"].replace("    type: vision\n", "    type: vision\n    # a stray comment\n", 1)
    assert any("neither a KV key nor the arm note" in p for p in P.kv_registry_delta_problems(reg["n16"], stray, ENTRY, "n16", "x"))
    twice = reg["x"].replace("    # PROVISIONAL M76 arm X\n", "    # PROVISIONAL M76 arm X\n    # PROVISIONAL M76 arm X\n", 1)
    assert P.kv_registry_delta_problems(reg["n16"], twice, ENTRY, "n16", "x")


# ------------------------------------------------------------------------------------------------ worker argv delta
@pytest.mark.parametrize("pair", P.KV_PAIRS)
def test_kv_argv_delta_accepted(pair):
    a, b = pair
    assert P.kv_argv_problems(worker_argv(a), worker_argv(b), a, b) == []


def test_kv_argv_refused_beyond_the_two_flags():
    x = worker_argv("x")
    bad = list(x)
    bad[bad.index("--prefill-step-size") + 1] = "2048"
    assert any("differ beyond" in p for p in P.kv_argv_problems(worker_argv("n16"), bad, "n16", "x"))
    extra = x + ["--quantized-kv-start", "128"]
    assert any("differ beyond" in p for p in P.kv_argv_problems(worker_argv("n16"), extra, "n16", "x"))
    wrong_mode = worker_argv("v")
    assert P.kv_argv_problems(worker_argv("n16"), wrong_mode, "n16", "x")     # V's mode on the X arm
    n16_with_bits = worker_argv("n16")[:9] + ["--kv-bits", "4"] + worker_argv("n16")[9:]
    assert any("--kv-bits" in p for p in P.kv_argv_problems(n16_with_bits, x, "n16", "x"))


def test_kv_argv_both_arms_mtp_on():
    off = [t for t in worker_argv("x")]
    i = off.index("--draft-kind")
    del off[i:i + 2]
    got = P.kv_argv_problems(worker_argv("n16"), off, "n16", "x")
    assert any("--draft-kind x0" in p for p in got)
    scan = worker_argv("x")
    scan[scan.index("--mtp-verify-scan") + 1] = "per_query"
    assert any("--mtp-verify-scan" in p for p in P.kv_argv_problems(worker_argv("n16"), scan, "n16", "x"))


def test_both_kv_arms_predictor_mtp():
    for arm in P.KV_ARMS:
        assert P.predictor_of("kv", arm) == "mtp" and P.role_of("kv", arm) == "on"
    assert (P.predictor_of("mtp", "off"), P.predictor_of("mtp", "on")) == ("off", "mtp")
    with pytest.raises(ValueError):
        P.check_arm("kv", "on")
    with pytest.raises(ValueError):
        P.check_lever("tq4")


# ------------------------------------------------------------------------------------------------ s3 and names
def test_s3_pins_and_s_s2_untouched():
    assert P.EXPECTED_BUILDS["s3"] == dict(mlx_vlm="34a212080d28953406ae446ab86505a964677a8d",
                                           mlx_serve="3b02e4cbd669b2f4ecb2cb8dabac4ef906e70afc",
                                           production_ref="f9bf743f284f45ce8d8a3c9902f0701de92c0931", mlx="0.32.4")
    assert P.EXPECTED_BUILDS["s2"] == dict(mlx_vlm="1c7c8fa166582ac1a1c23ae9063527b2b5215b11",
                                           mlx_serve="1ddf6f842f159a62d240f3ac6965fc33cbdb0b0d",
                                           production_ref="b26fa7c9faf23bc3167db3419504ef0b2b82a8e6", mlx="0.32.4")
    assert "s" not in P.EXPECTED_BUILDS and P.DEFAULT_BUILD == "s" and P.DEFAULT_LEVER == "mtp"
    with pytest.raises(ValueError):
        P.check_kv_build("s2")


def test_s3_gitlinks_are_the_stage3_base():
    out = subprocess.run(["git", "-C", str(REPO), "diff", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", "89205085", "--",
                          "src/mlx-vlm", "src/mlx-serve"], capture_output=True, text=True).stdout
    assert P.EXPECTED_BUILDS["s3"]["mlx_vlm"] in out and P.EXPECTED_BUILDS["s3"]["mlx_serve"] in out


def test_kv_names_and_paths_are_m76():
    assert P.kv_tune("x", 1, False) == "m76-x-b1"
    assert P.kv_tune("n16", None, True) == "m76-n16-smoke"
    assert P.kv_tune("v", 2, False, tier=2) == "m76-v-t2-b2"
    assert P.kv_leg_name("math500", "x", 1) == "math500-m76-x-b1"
    assert P.kv_leg_name("longctx", "n16", "smoke") == "longctx-m76-n16-lc-smoke"      # v1.2: A5's own tune
    assert P.kv_leg_name("longctx", "x", 1) == "longctx-m76-x-lc-b1"
    wd = Path("/wd")
    assert P.kv_frozen_path(wd, "s3") == wd / "m76" / "p426" / "frozen.s3.json"
    assert P.kv_m1_out_dir(wd, "m76-x-b1", "s3") == wd / "m76" / "p426" / "s3" / "m1" / "m76-x-b1"
    for arm in P.KV_ARMS:
        for sel in ("smoke", 1, 2):
            assert "p426" not in P.kv_leg_name("cjudge", arm, sel)
    assert P.pair_label("n16", "x") == "X − N16" and P.pair_label("x", "v") == "V − X" and P.pair_label("n16", "v") == "V − N16"
    with pytest.raises(ValueError):
        P.pair_label("x", "n16")


# ------------------------------------------------------------------------------------------------ the frozen record
def _venvs():
    one = {p: "0.32.4" if p in ("mlx", "mlx-metal") else "1.0" for p in P.VENV_PACKAGES}
    return {v: dict(one) for v in P.VENVS}


def kv_record(arms=("n16", "x"), **over):
    rec = dict(build="s3", lever="kv", arms=list(arms), uv_lock_sha256="a" * 64, bench_lock_sha256="b" * 64, venvs={},
               **{k: P.EXPECTED_BUILDS["s3"][k] for k in ("mlx_vlm", "mlx_serve", "production_ref")})
    for i, arm in enumerate(arms):
        rec.update({f"stack_head_{arm}": f"{i + 1:x}" * 40, f"stack_clean_{arm}": True, f"registry_{arm}_sha": f"{i + 3:x}" * 64})
        rec["venvs"][arm] = _venvs()
    rec.update(over)
    return rec


def test_kv_record_accepted_and_refused():
    assert P.kv_record_problems(kv_record(), "s3", ("n16", "x")) == []
    assert P.kv_record_problems(kv_record(("n16", "x", "v")), "s3", ("x", "v")) == []
    assert P.kv_record_problems(kv_record(mlx_vlm="0" * 40), "s3", ("n16", "x"))
    assert P.kv_record_problems(kv_record(lever="mtp"), "s3", ("n16", "x"))
    assert P.kv_record_problems(kv_record(("x", "v")), "s3", ("x", "v"))              # the base n16 is always recorded
    assert P.kv_record_problems(kv_record(), "s3", ("n16", "v"))
    assert P.kv_record_problems(kv_record(stack_head_x="1" * 40), "s3", ("n16", "x"))  # two arms, one commit
    assert P.kv_record_problems(kv_record(), "s2", ("n16", "x"))


# ------------------------------------------------------------------------------------------------ ids (B5)
def _universe():
    p = p426_ids.build(REPO)["axes"]["math500"]
    return sorted(p["block1"] + p["block2"] + [f"test/synthetic/{i:03d}.json" for i in range(400)])


PLAN_SHA = "e" * 64


def fake_plan(*sizes, sha=PLAN_SHA):
    """A stand-in for B7.1's `m76_rule.axis_plan("A5")` (v1.4 two looks 72 / 120 at α 0.003808 / 0.021192)."""
    alphas = (0.003808, 0.021192) if len(sizes) == 2 else (0.025,)
    return dict(axis="A5", looks=[dict(look=k + 1, size=n, unit="items", alpha=a, exact_alpha=a)
                                  for k, (n, a) in enumerate(zip(sizes, alphas))], report_sha256=sha)


def fake_counts(n):
    """A stand-in for the planner's offline tokenizer count: every A5 prompt's frozen token count (rung − a seeded shortfall;
    v1.5a band −3 % … 0 %, re-checked by `load()` since S23-P88)."""
    d = M.longctx_draw(n if isinstance(n, tuple) else (n,))
    return {i["id"]: i["rung"] - 200 - (i["task_seed"] % 300) for i in d["items"] + d["smoke"]}


def build_ids(n=42, universe=None, sizes=None):
    sizes = tuple(sizes) if sizes else (n,)
    return M.build(REPO, a5_sizes=sizes, universe=universe or _universe(), max_tokens=102400, thinking_budget=81920,
                   prompt_tokens=fake_counts(sizes), counter=dict(tokenizer="test", chars_per_token=3.5),
                   a5_source=dict(source=M.PLAN_SOURCE, report_sha256=PLAN_SHA))


@pytest.fixture(scope="module")
def ids():
    return build_ids()


def test_math500_300_nested_and_deterministic(ids):
    m = ids["axes"]["math500"]
    p = p426_ids.build(REPO)["axes"]["math500"]
    assert len(m["order"]) == 300 and len(set(m["order"])) == 300
    assert m["order"][:100] == sorted(p["block1"] + p["block2"]) == m["tier1"]
    assert (m["block1"], m["block2"], m["smoke"]) == (p["block1"], p["block2"], p["smoke"])
    t2 = m["tier2"]
    assert sorted(t2["block1"] + t2["block2"]) == sorted(m["order"][100:]) and not set(t2["block1"]) & set(t2["block2"])
    assert len(t2["block1"]) == len(t2["block2"]) == 100
    remaining = sorted(set(_universe()) - set(m["tier1"]))
    assert m["order"][100:] == random.Random(7601).sample(remaining, 200)
    again = build_ids(universe=list(reversed(_universe())))
    assert again == ids
    for axis in ("cjudge", "vision", "reasoning"):
        assert ids["axes"][axis] == p426_ids.build(REPO)["axes"][axis]


def test_math500_universe_must_hold_p426_and_200_more():
    with pytest.raises(M.IdsError):
        build_ids(universe=_universe()[:250])
    with pytest.raises(M.IdsError):
        build_ids(universe=[f"t/{i}" for i in range(500)])


def test_a5_items_counts_seeds_and_blocks(ids):
    lc = ids["axes"]["longctx"]
    assert lc["n"] == 42 and lc["per_cell"] == 7 and len(lc["items"]) == 42
    splits = []
    for task in ("retrieval", "reasoning"):
        for rung in (131072, 159744, 196608):
            cell = [i for i in lc["items"] if i["task"] == task and i["rung"] == rung]
            assert len(cell) == 7
            splits.append((len([i for i in cell if i["id"] in lc["block1"]]), len([i for i in cell if i["id"] in lc["block2"]])))
    assert sorted(splits) == [(3, 4)] * 3 + [(4, 3)] * 3           # an odd cell's extra item alternates: blocks 21 / 21
    assert len(lc["block1"]) == len(lc["block2"]) == 21
    even = M.longctx(48, 102400, 81920, prompt_tokens=fake_counts(48))
    assert len(even["block1"]) == len(even["block2"]) == 24
    assert all(set(i) == {"id", "task", "rung", "task_seed", "request_seed"} for i in lc["items"])
    seeds = [s for i in lc["items"] + lc["smoke_items"] for s in (i["task_seed"], i["request_seed"])]
    assert len(set(seeds)) == len(seeds)
    assert sorted(lc["block1"] + lc["block2"]) == sorted(i["id"] for i in lc["items"])
    assert not set(lc["smoke"]) & {i["id"] for i in lc["items"]} and len(lc["smoke"]) == 2
    assert M.longctx(42, 102400, 81920, prompt_tokens=fake_counts(42),
                     counter=dict(tokenizer="test", chars_per_token=3.5)) == lc   # seed 7605: deterministic
    first = random.Random(7605).randrange(1, M.SEED_SPACE)
    assert lc["items"][0]["task_seed"] == first
    for i in lc["items"]:
        assert lc["sampler_seeds"][i["id"]] == M.row_sampler_seed(i)


@pytest.mark.parametrize("n", [40, 41, 44, 126, 0, 6])
def test_a5_n_refused_outside_the_range(n):
    with pytest.raises(M.IdsError):
        M.check_a5_n(n)


def test_a5_sizes_come_from_b7s_plan(monkeypatch):
    """v1.4: the A5 tier sizes are `m76_rule.axis_plan("A5")`'s look sizes (never constants); the plan is called by default."""
    from bench import m76_rule

    assert M.a5_sizes_from(fake_plan(72, 120)) == ((72, 120), dict(source=M.PLAN_SOURCE, report_sha256=PLAN_SHA))
    assert M.a5_sizes_from(fake_plan(72))[0] == (72,)
    calls = []
    monkeypatch.setattr(m76_rule, "axis_plan", lambda axis, **kw: calls.append(axis) or fake_plan(66, 114))
    assert M.a5_sizes_from() == ((66, 114), dict(source=M.PLAN_SOURCE, report_sha256=PLAN_SHA)) and calls == ["A5"]
    for bad in (fake_plan(72, 72), fake_plan(120, 72), fake_plan(72, 125), dict(looks=[dict(look=1, size=None)]),
                dict(looks=[])):
        with pytest.raises(M.IdsError):
            M.a5_sizes_from(bad)
    monkeypatch.setattr(m76_rule, "axis_plan", lambda axis, **kw: (_ for _ in ()).throw(ValueError("no report")))
    with pytest.raises(M.IdsError, match="refused"):
        M.a5_sizes_from()
    assert "--a5-n" not in Path(M.__file__).read_text()                     # no constant / flag override


def test_a5_tier2_is_the_nested_continuation_of_the_same_draw():
    """v1.4: 120 items = tier 1 (the first 72, the v1.1 draw unchanged, smoke unchanged) + 48 more drawn by the same seed-7605
    generator as the continuation of the same task × rung cells (8 more per cell), split per cell into two tier-2 blocks."""
    one = M.longctx(72, 102400, 81920, prompt_tokens=fake_counts((72,)))
    two = M.longctx((72, 120), 102400, 81920, prompt_tokens=fake_counts((72, 120)))
    assert two["n"] == 120 and two["sizes"] == [72, 120] and len(two["items"]) == 120
    assert two["items"][:72] == one["items"] and two["tier1"] == [i["id"] for i in one["items"]]
    assert (two["block1"], two["block2"], two["smoke_items"]) == (one["block1"], one["block2"], one["smoke_items"])
    assert "tier2" not in one
    t2 = two["tier2"]
    assert t2["per_cell"] == 8 and t2["items"] == [i["id"] for i in two["items"][72:]]
    assert len(t2["block1"]) == len(t2["block2"]) == 24 and sorted(t2["block1"] + t2["block2"]) == sorted(t2["items"])
    for task in ("retrieval", "reasoning"):
        for rung in (131072, 159744, 196608):
            cell = [i for i in two["items"][72:] if i["task"] == task and i["rung"] == rung]
            assert [i["id"] for i in cell] == [f"{task}-{rung}-{k:02d}" for k in range(12, 20)]
            assert len([i for i in cell if i["id"] in t2["block1"]]) == 4
    # the continuation of ONE generator: tier 1's 144 seeds, the smoke's 4, then tier 2's
    rng = random.Random(7605)
    seeds = [rng.randrange(1, M.SEED_SPACE) for _ in range(2 * 122)]
    got = [s for i in one["items"] + one["smoke_items"] + two["items"][72:] for s in (i["task_seed"], i["request_seed"])]
    assert got == seeds                                                     # (no collision in this stream)
    for i in two["items"]:
        assert two["sampler_seeds"][i["id"]] == M.row_sampler_seed(i)
        cell = two["budget"][i["id"]]
        assert cell["prompt_tokens"] == fake_counts((72, 120))[i["id"]] and cell["total"] <= 262144
    assert M.budget_problems(two) == []
    with pytest.raises(M.IdsError):
        M.longctx((72, 125), 102400, 81920, prompt_tokens=fake_counts((72,)))


def test_ids_load_binds_the_a5_sizes_to_the_current_plan():
    ids = build_ids(sizes=(42, 54))
    text = json.dumps(ids)
    assert ids["a5"] == dict(source=M.PLAN_SOURCE, report_sha256=PLAN_SHA, sizes=[42, 54])
    assert M.load(REPO, text, plan=fake_plan(42, 54)) == ids
    for plan in (fake_plan(42), fake_plan(42, 60), fake_plan(42, 54, sha="f" * 64)):
        with pytest.raises(ValueError, match="plan"):
            M.load(REPO, text, plan=plan)
    other = json.loads(text)
    other["a5"]["source"] = "--a5-n"
    with pytest.raises(ValueError):
        M.load(REPO, json.dumps(other), plan=fake_plan(42, 54))


def test_a5_token_budget_check(ids):
    """v1.2: per item the frozen prompt count and min(deployed, 262,144 − prompt) — no invented overhead."""
    lc = ids["axes"]["longctx"]
    b = lc["budget"]
    counts = fake_counts(42)
    for item in lc["items"] + lc["smoke_items"]:
        cell = b[item["id"]]
        assert cell["prompt_tokens"] == counts[item["id"]]
        assert cell["resolved_max_tokens"] == min(102400, 262144 - counts[item["id"]])
        assert cell["total"] <= 262144
        assert cell["resolved_thinking_budget"] == min(81920, int(cell["resolved_max_tokens"] * 0.8))
    assert M.budget_problems(lc) == []
    first = lc["items"][0]["id"]
    assert M.budget_problems(lc, {first: counts[first]}) == []
    assert M.budget_problems(lc, {first: counts[first] - 1})                 # a row must EQUAL its frozen count
    tampered = json.loads(json.dumps(lc))
    tampered["budget"][first]["resolved_max_tokens"] += 1
    assert M.budget_problems(tampered)
    with pytest.raises(M.IdsError):
        M.item_budget(262144, 102400, 81920)                                 # nothing left to generate


def test_ids_load_refuses_a_changed_record(ids, tmp_path):
    text = json.dumps(ids)
    assert M.load(REPO, text, plan=fake_plan(42)) == ids
    bad = json.loads(text)
    bad["axes"]["longctx"]["items"][0]["task_seed"] += 1
    with pytest.raises(ValueError):
        M.load(REPO, json.dumps(bad), plan=fake_plan(42))


# ------------------------------------------------------------------------------------------------ the KV planner
@pytest.fixture
def kvplan(ids, monkeypatch):
    monkeypatch.setattr(P, "load_m76_ids", lambda repo, text=None: ids)

    def plan(axis, arm, sel, **kw):
        return P.plan_leg(REPO, axis, arm, None if sel == "smoke" else sel, smoke=sel == "smoke", workdir="/wd",
                          reviewed_head="r" * 40, production_ref="f" * 40, build="s3", lever="kv", **kw)
    return plan


def test_kv_plan_math500_tiers(kvplan, ids):
    t1 = kvplan("math500", "x", 1)
    assert t1["tune"] == "m76-x-b1" and t1["planned"] == ids["axes"]["math500"]["block1"]
    assert "--tune" in t1["driver_argv"] and t1["driver_argv"][t1["driver_argv"].index("--tune") + 1] == "m76-x-b1"
    t2 = kvplan("math500", "n16", 2, tier=2)
    assert t2["tune"] == "m76-n16-t2-b2" and t2["planned"] == ids["axes"]["math500"]["tier2"]["block2"]
    assert t2["rows_path"].name == "math500.m76-n16-t2-b2.jsonl"
    with pytest.raises(ValueError):
        kvplan("cjudge", "x", 1, tier=2)


def test_kv_plan_longctx(kvplan, ids):
    leg = kvplan("longctx", "v", 1)
    lc = ids["axes"]["longctx"]
    assert leg["planned"] == lc["block1"] and len(leg["driver_argvs"]) == len(lc["block1"])
    assert leg["expected_requests"] == 2 * len(lc["block1"]) and leg["expected_extra"] == len(lc["block1"])
    for iid, argv in zip(leg["planned"], leg["driver_argvs"]):
        item = next(i for i in lc["items"] if i["id"] == iid)
        mod = "bench.run_retrieval" if item["task"] == "retrieval" else "bench.run_reasoning"
        assert argv[1:3] == ["-m", mod]
        assert argv[argv.index("--grid") + 1] == str(item["rung"]) and argv[argv.index("--samples") + 1] == "1"
        assert argv[argv.index("--task-seed-base") + 1] == str(item["task_seed"])
        assert argv[argv.index("--request-seed-base") + 1] == str(item["request_seed"])
        assert argv[argv.index("--sampling-profile") + 1] == "deployed"
        assert argv[argv.index("--out-tag") + 1] == f"m76-v-lc-b1.{iid}"
        assert "--max-tokens" not in argv                                    # deployed sampling verbatim
        if item["task"] == "reasoning":
            assert argv[argv.index("--chain-len") + 1] == "4"
        assert leg["seeds"][iid] == {"sampler_seed": M.row_sampler_seed(item)}
    smoke = kvplan("longctx", "n16", "smoke")
    assert smoke["planned"] == lc["smoke"]


def test_kv_plan_longctx_tier2(kvplan, monkeypatch):
    """v1.4: an A5 leg names its tier (`--tier 2`, as Math500): `m76-<arm>-lc-t2-b<k>` over `tier2.block<k>`."""
    assert P.kv_tune("x", 1, False, tier=2, axis="longctx") == "m76-x-lc-t2-b1"
    assert P.kv_leg_name("longctx", "n16", 2, tier=2) == "longctx-m76-n16-lc-t2-b2"
    for axis in ("cjudge", "vision", "reasoning"):
        with pytest.raises(ValueError):
            P.kv_tune("x", 1, False, tier=2, axis=axis)
    two = build_ids(sizes=(42, 54))
    monkeypatch.setattr(P, "load_m76_ids", lambda repo, text=None: two)
    lc = two["axes"]["longctx"]
    for arm, block in (("x", 1), ("n16", 2)):
        leg = kvplan("longctx", arm, block, tier=2)
        tune = f"m76-{arm}-lc-t2-b{block}"
        assert leg["tune"] == tune and leg["planned"] == lc["tier2"][f"block{block}"] and leg["tier"] == 2
        assert leg["stems"] == [f"retrieval.{tune}", f"reasoning.{tune}"]
        for iid, argv in zip(leg["planned"], leg["driver_argvs"]):
            item = next(i for i in lc["items"] if i["id"] == iid)
            assert argv[argv.index("--task-seed-base") + 1] == str(item["task_seed"])
            assert argv[argv.index("--out-tag") + 1] == f"{tune}.{iid}"
        assert not set(leg["planned"]) & set(lc["block1"] + lc["block2"])
    monkeypatch.setattr(P, "load_m76_ids", lambda repo, text=None: build_ids())     # a one-look plan: no tier 2
    with pytest.raises(ValueError, match="no tier 2"):
        kvplan("longctx", "x", 1, tier=2)


def lc_first(ids):
    return ids["axes"]["longctx"]["items"][0]["id"]


def test_kv_plan_longctx_refuses_a_failed_budget(kvplan, ids, monkeypatch):
    bad = json.loads(json.dumps(ids))
    bad["axes"]["longctx"]["budget"][lc_first(ids)]["resolved_max_tokens"] = 1
    monkeypatch.setattr(P, "load_m76_ids", lambda repo, text=None: bad)
    with pytest.raises(ValueError, match="token budget"):
        kvplan("longctx", "x", 1)


def test_kv_plan_m1_binds_the_stage2_record(kvplan):
    n16 = kvplan("m1", "n16", 1)
    argv = n16["driver_argv"]
    assert argv[argv.index("--predictor") + 1] == "on" and "--kv-arm" not in argv and "--certified-by" not in argv
    assert n16["out_dir"] == Path("/wd/m76/p426/s3/m1/m76-n16-b1")
    with pytest.raises(ValueError, match="stage-2"):
        kvplan("m1", "x", 1)
    x = kvplan("m1", "x", 1, certified_by="/wd/m76/stage2/summary.json")["driver_argv"]
    assert x[x.index("--predictor") + 1] == "on" and "--kv-arm" in x
    assert x[x.index("--certified-by") + 1] == "/wd/m76/stage2/summary.json"
    assert x[x.index("--production-ref") + 1] == "f" * 40


def test_kv_plan_refuses_mtp_arms_and_other_builds(kvplan):
    with pytest.raises(ValueError):
        kvplan("cjudge", "on", 1)
    with pytest.raises(ValueError):
        P.plan_leg(REPO, "cjudge", "x", 1, build="s2", lever="kv")
    with pytest.raises(ValueError):
        P.plan_leg(REPO, "cjudge", "on", 1, build="s2", tier=2)      # mtp has no tier


def test_kv_qualify_problems():
    rep = dict(predictor="on", production="f" * 40, entries={ENTRY: dict(status="COMPLETED", arm="mtp_on")})
    assert P.qualify_problems(rep, ENTRY, "n16", "f" * 40, lever="kv") == []
    assert any("certified_by" in p for p in P.qualify_problems(rep, ENTRY, "x", "f" * 40, lever="kv"))
    ok = dict(rep, certified_by=dict(path="$STACK_WORKDIR/m76/stage2/summary.json", sha256="c" * 64))
    assert P.qualify_problems(ok, ENTRY, "x", "f" * 40, lever="kv") == []
    assert P.qualify_problems(dict(ok, predictor="off"), ENTRY, "x", "f" * 40, lever="kv")
