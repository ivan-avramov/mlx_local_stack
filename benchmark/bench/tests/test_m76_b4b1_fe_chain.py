"""M76 B4b-1 (spec v5 §2 + acceptance 1): the tg2 P426 schedule builder and its readers, the pins, the run configuration, the chain
entry's `--leg` / `--rehearsal` mapping and record kinds, the plan, the docker / hooks wiring, R2 / R3 on Rust. The real draw is
used throughout; only the router / worker / agent are absent (no leg is launched here). Class of each test is in the comment
above it: (a) reproduces a failure the spec fixes, (b) preserves an invariant, (c) new behaviour.
Name guesses: `test_m76_b4b1_fe_support.GUESSES`."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench.tests import test_m76_b4b1_fe_support as S

MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
D = S.draw_doc()
# spec §2 table: leg -> (session dir, seed base, language order, items per language)
TABLE = {
    "pilot": ("pilot", 1001, ("rust", "javascript", "java", "cpp"), 1),
    "s1": ("s1", 1001, ("rust", "javascript", "java", "cpp"), 20),
    "s2": ("s2", 2002, ("cpp", "java", "javascript", "rust"), 20),
    "reload": ("reload", 1001, ("rust", "javascript", "java", "cpp"), 5),
}
REHEARSAL = {"r2": ("s1", 1001, ("rust",), 1), "r3": ("s1", 1001, ("rust",), 1)}


def build(leg, doc=None, predictor="mtp"):
    from bench import schedules
    fn = S.attr(schedules, "tg2_p426", "schedule")
    return fn(D if doc is None else doc, leg, MODEL, predictor)


def prefix(lang, n):
    return D["languages"][lang]["permutation"][:n]


# ------------------------------------------------------------------------------------------------ the schedule (golden table)
# (c) tg1's P426 document shape, ONE block, ONE schedule leg per (session, language) in the table's language order, each with one
# invocation of that language's first n items of the frozen permutation, at the table's seed
@pytest.mark.parametrize("leg", sorted(TABLE))
def test_schedule_table(leg):
    session, seed, langs, n = TABLE[leg]
    sched = build(leg)
    assert sched["builder"] == "tg2_p426" and sched["p426"] is True and sched["predictor"] == "mtp"
    (block,) = sched["blocks"]
    assert block["session"] == session and block["model"] == MODEL and block["seed_base"] == seed
    assert [l["lang"] for l in block["legs"]] == list(langs)
    for l in block["legs"]:
        (inv,) = l["invocations"]
        want = prefix(l["lang"], n)
        assert l["seed_base"] == seed and l["session"] == session and l["model"] == MODEL
        assert inv["expect"] == want and [f"{l['lang']}/{x}" for x in inv["names"]] == want
        assert len(inv["names"]) == n


# (c) rehearsals: s1, seed 1001, rust only, the first item
def rehearsal_schedule(kind):
    """GUESS (`schedule`): the rehearsal's schedule is `tg2_p426(draw, "r2"|"r3", ...)` or `tg2_p426(draw, "s1", ..., rehearsal=True)`."""
    from bench import schedules
    fn = S.attr(schedules, "tg2_p426", "schedule")
    try:
        return fn(D, kind, MODEL, "mtp")
    except Exception:
        try:
            return fn(D, "s1", MODEL, "mtp", rehearsal=True)
        except TypeError as exc:
            pytest.fail(f"SPELLING GUESS schedule: no accepted spelling of the rehearsal schedule ({exc})", pytrace=False)


@pytest.mark.parametrize("kind", sorted(REHEARSAL))
def test_rehearsal_schedule(kind):
    sched = rehearsal_schedule(kind)
    (block,) = sched["blocks"]
    (l,) = block["legs"]
    assert (block["session"], l["lang"], l["seed_base"]) == ("s1", "rust", 1001)
    assert l["invocations"][0]["expect"] == prefix("rust", 1)


# (c) the schedule document is the planned-slot source of the readers: p426_verify.planned_slots counts and names the slots
@pytest.mark.parametrize("leg", sorted(TABLE))
def test_planned_slots_of_the_schedule(leg):
    from bench import p426_verify
    session, _, langs, n = TABLE[leg]
    count, ids = p426_verify.planned_slots(build(leg), leg)
    assert count == n * len(langs)
    assert ids == [i for lang in langs for i in prefix(lang, n)]


def _leg_root(tmp_path, leg, ledger=None, **chain_kw):
    from bench import schedules
    root = tmp_path / ("tg2-m76-n16-%s.a1" % leg)
    root.mkdir()
    sched = build(leg)
    (root / "schedule.json").write_text(json.dumps(sched))
    chain = dict(schedule_sha256=schedules.schedule_sha256(sched), status="finished", p426_dnf=[],
                 p426_ledger=[dict(slot="tg2-p426|n16|%s|%s|%s" % (MODEL, TABLE[leg][0], i), kind="row") for i in (ledger or [])],
                 progress=dict(invocations=[]), **chain_kw)
    (root / "chain.json").write_text(json.dumps(chain))
    return root


# (c) `p426_freeze.planned_slots` / `p426_wave2.planned_slots` read the frozen tg2 schedule (never a constant)
@pytest.mark.parametrize("leg", sorted(TABLE))
def test_planned_slots_readers_over_a_leg_root(leg, tmp_path):
    from bench import p426_freeze, p426_wave2
    root = _leg_root(tmp_path, leg)
    want = TABLE[leg][3] * len(TABLE[leg][2])
    assert p426_freeze.planned_slots(root) == p426_wave2.planned_slots(root) == want


# (c) classify_leg judges the realized ledger against the tg2 schedule: a pilot's four slots are not a session leg's eighty
def test_classify_leg_uses_the_tg2_plan(tmp_path):
    from bench import p426_wave2
    four = [i for lang in TABLE["pilot"][2] for i in prefix(lang, 1)]
    (tmp_path / "p").mkdir()
    (tmp_path / "s").mkdir()
    ok = p426_wave2.classify_leg(_leg_root(tmp_path / "p", "pilot", four), 0, arm="n16")
    assert "frozen schedule" not in ok["reason"]
    root = _leg_root(tmp_path / "s", "s1", four)
    bad = p426_wave2.classify_leg(root, 0, arm="n16")
    assert bad["state"] == "INVALID" and "4 slots" in bad["reason"] and "80" in bad["reason"]


# (c) a changed / missing schedule is refused by the reader (the frozen sha256 in chain.json)
def test_planned_slots_refuses_a_schedule_that_is_not_the_frozen_one(tmp_path):
    from bench import p426_freeze
    root = _leg_root(tmp_path, "pilot")
    sched = json.loads((root / "schedule.json").read_text())
    sched["blocks"][0]["legs"][0]["invocations"][0]["names"] = ["other"]
    (root / "schedule.json").write_text(json.dumps(sched))
    with pytest.raises(ValueError):
        p426_freeze.planned_slots(root)


# (c) `check_tg2_p426` accepts the builder's own schedule for every leg and refuses each way a schedule can differ from the
# table / the draw prefix (item swapped / reordered / dropped, language order, seed, another leg's schedule)
@pytest.mark.parametrize("leg", sorted(TABLE))
def test_check_tg2_p426_accepts_its_own_schedule(leg):
    from bench import schedules
    S.attr(schedules, "check_tg2_p426", "schedule")(build(leg), D, leg)


def _mutations(leg):
    base = build(leg)
    out = {}
    for name in ("swap", "drop", "language_order", "seed", "extra"):
        sched = json.loads(json.dumps(base))
        legs = sched["blocks"][0]["legs"]
        inv = legs[0]["invocations"][0]
        if name == "swap":
            if len(inv["names"]) < 2:
                inv["names"][0], inv["expect"][0] = "not-in-the-draw", legs[0]["lang"] + "/not-in-the-draw"
            else:
                inv["names"][0], inv["names"][1] = inv["names"][1], inv["names"][0]
                inv["expect"][0], inv["expect"][1] = inv["expect"][1], inv["expect"][0]
        elif name == "drop":
            inv["names"].pop()
            inv["expect"].pop()
        elif name == "language_order":
            legs.reverse()
        elif name == "seed":
            legs[0]["seed_base"] += 1
        else:
            inv["names"].append("zzz")
            inv["expect"].append(legs[0]["lang"] + "/zzz")
        out[name] = sched
    return out


@pytest.mark.parametrize("name", ["swap", "drop", "language_order", "seed", "extra"])
@pytest.mark.parametrize("leg", ["pilot", "s1", "s2", "reload"])
def test_check_tg2_p426_refuses_a_changed_schedule(leg, name):
    from bench import schedules
    check = S.attr(schedules, "check_tg2_p426", "schedule")
    if name == "language_order" and len(TABLE[leg][2]) < 2:
        pytest.skip("single language")
    with pytest.raises(Exception):
        check(_mutations(leg)[name], D, leg)


def test_check_tg2_p426_refuses_another_legs_schedule():
    from bench import schedules
    check = S.attr(schedules, "check_tg2_p426", "schedule")
    with pytest.raises(Exception):
        check(build("s1"), D, "s2")
    with pytest.raises(Exception):
        check(build("pilot"), D, "reload")


# (a) the pins: a CONSISTENT redraw (self-consistent draw document, own sha) refuses — only the committed draw is the draw
def test_a_consistent_redraw_is_refused():
    from bench import schedules
    redrawn = json.loads(json.dumps(D))
    for entry in redrawn["languages"].values():
        entry["permutation"] = list(reversed(entry["permutation"]))
        for tier in ("screen", "decider"):
            n = len(entry[tier])
            entry[tier] = entry["permutation"][:n]
    assert schedules.draw_sha256_of(redrawn) != S.TG2_DRAW_SHA256
    with pytest.raises(Exception):
        build("pilot", redrawn)
    check = S.attr(schedules, "check_tg2_p426", "schedule")
    with pytest.raises(Exception):
        check(build("pilot"), redrawn, "pilot")


# (b) the committed draw still builds the committed shape (hash of the file bytes is the pin)
def test_the_committed_draw_is_the_pinned_one():
    from bench import schedules
    assert schedules.draw_sha256_of(D) == S.TG2_DRAW_SHA256


# ------------------------------------------------------------------------------------------------ configuration
# (c) P426_CONFIG_IDS and the tg2-p426 config: builder tg2_p426, p426, one model, transport p426_continue
def test_p426_config_ids_and_chainconfig_rules():
    from bench import run_config as rc
    ids = S.attr(rc, "P426_CONFIG_IDS", "chain-entry")
    assert tuple(ids) == ("tg1-p426", "tg2-p426") and rc.P426_CONFIG_ID == "tg1-p426"
    R = S.chain_entry()
    a = R.parse_args(_argv("--leg", "pilot"))
    cfg = R.tg2_config(a)
    assert cfg.config_id == "tg2-p426" and cfg.transport_policy == "p426_continue"
    assert cfg.schedule["builder"] == "tg2_p426" and cfg.schedule["params"]["p426"] is True
    assert list(cfg.schedule["params"]["models"]) == [MODEL]
    (arm,) = cfg.arms
    assert arm.label == S.SCAFFOLD and arm.probe == "benchmark/run_tg2_probe.py"
    for bad in (dict(models=[MODEL, "other"]), dict(builder="tg1")):
        params = dict(cfg.schedule["params"], **({"models": bad["models"]} if "models" in bad else {}))
        with pytest.raises(ValueError):
            rc.ChainConfig(config_id="tg2-p426", arms=cfg.arms, schedule=dict(builder=bad.get("builder", "tg2_p426"), params=params),
                           out_root_family="m63", predictor="mtp", arm_switch_ops=(), transport_policy="p426_continue",
                           resume_policy="restart_load", snapshot_complete_required=False)


# (b) `p426_continue` stays the transport policy of the P426 configs only; tg1-p426's rules are unchanged
def test_p426_continue_only_for_p426_configs():
    from bench import run_config as rc
    R1 = S.tg1_chain_entry()
    a = R1.parse_args(["chain", "s1", "--p426", "--models", MODEL, "--probe-code-sha", "x", "--predictor", "mtp",
                       "--out-root", "o.a1", "--policy-sha", "a" * 64, "--frozen-prompt-date", "Sat Oct 17 2026",
                       "--campaign-core", "t", "--frozen-record", "r.json"])
    cfg = R1.tg1_config(a)
    assert cfg.config_id == "tg1-p426" and cfg.transport_policy == "p426_continue"
    with pytest.raises(ValueError):
        rc.ChainConfig(config_id="tg1", arms=cfg.arms, schedule=cfg.schedule, out_root_family="c147", predictor="off",
                       arm_switch_ops=(), transport_policy="p426_continue", resume_policy="restart_load",
                       snapshot_complete_required=False)


# (c) TG2_POLICY / evidence of the tg2 runner
def test_tg2_runner_policy():
    from bench import run_config as rc, tg1_runner
    runner = S.bench_mod("tg2_runner")
    # S27 §4.5 (C373): the tg2 template also allows the deterministic interrupt positive
    assert runner.TG2_POLICY == rc.PolicyTemplate(config_id="tg2", langs=("rust", "javascript", "java", "cpp"),
                                                  inject_allowed=rc.ALL_INJECT_KINDS)
    assert runner.TG1_P426_EVIDENCE == tg1_runner.TG1_P426_EVIDENCE


# (c) the chain entry's frozen pieces name the tg2 probe, the tg2 generation data and itself
def test_chain_core_specs_and_languages():
    R = S.chain_entry()
    assert tuple(R.LANGS) == S.LANGS
    spec = R.CORE_SPECS
    assert spec["probe_entry"] == "benchmark/run_tg2_probe.py" and spec["chain_entry"] == "benchmark/chains/c147/run_tg2_chain.py"
    data = set(spec["probe_data"])
    assert "benchmark/opencode_bench_v2_web_tg2.json" in data and "benchmark/opencode_bench_v2_web_tg1.json" not in data
    for plugin in ("toolbounds.js", "noretry.js", "datefreeze.js"):
        assert "benchmark/opencode_plugins/" + plugin in data
    assert all((S.REPO / rel).is_file() for rel in [spec["probe_entry"], spec["chain_entry"], *data])


# ------------------------------------------------------------------------------------------------ the entry's argv
def _argv(*extra, out="tg2-m76-n16-pilot.a1", arm=None):
    # AMENDED (delivery 2): spec §3 — R2 runs on X (`tg2-m76-x-rehearsal-r2`), R3 on N16; the chain refuses the other arm
    if arm is None:
        arm = "x" if ("--rehearsal", "r2") in list(zip(extra, extra[1:])) else "n16"
    return ["--p426", "--lever", "kv", "--kv-arm", arm, "--models", MODEL, "--predictor", "mtp", "--out-root", out,
            "--probe-code-sha", "a" * 64, "--policy-sha", "b" * 64, "--frozen-prompt-date", "Sat Oct 17 2026",
            "--campaign-core", "tag", "--frozen-record", "record.json", *extra]


# (c) E2: `--leg` -> shared-core mapping; `chain.json` records both the normalised mode / sessions and `tg2_leg`
@pytest.mark.parametrize("leg,mode,sessions", [("pilot", "pilot", []), ("s1", "chain", ["s1"]), ("s2", "chain", ["s2"]),
                                               ("reload", "chain", ["reload"])])
def test_leg_mapping(leg, mode, sessions):
    a = S.chain_entry().parse_args(_argv("--leg", leg))
    assert a.mode == mode and list(a.sessions) == sessions and not a.rehearsal
    assert S.attr(a, "tg2_leg", "chain-argv") == leg


@pytest.mark.parametrize("kind,inject", [("r2", "reconcile-mismatch"), ("r3", "stall-kill")])
def test_rehearsal_mapping(kind, inject):
    a = S.chain_entry().parse_args(_argv("--rehearsal", kind, out="tg2-m76-x-rehearsal-%s.a1" % kind))
    assert a.mode == "chain" and list(a.sessions) == ["s1"] and a.rehearsal is True and a.inject == inject


# (c) record kinds follow the mapping: pilot -> p426_v8_base, s1 / s2 / reload -> p426_timeout_amendment, rehearsal -> p426_rehearsal
@pytest.mark.parametrize("argv,kind", [(("--leg", "pilot"), "p426_v8_base"), (("--leg", "s1"), "p426_timeout_amendment"),
                                       (("--leg", "s2"), "p426_timeout_amendment"), (("--leg", "reload"), "p426_timeout_amendment"),
                                       (("--rehearsal", "r2"), "p426_rehearsal"), (("--rehearsal", "r3"), "p426_rehearsal")])
def test_record_kinds(argv, kind):
    from bench import p426_record
    a = S.chain_entry().parse_args(_argv(*argv))
    assert p426_record.KINDS[p426_record.mode_key(a.mode, bool(a.rehearsal))] == kind


# (c) `--leg` and `--rehearsal` are exclusive; one is required; unknown values are refused (exit 2, `REFUSED:` on stderr)
@pytest.mark.parametrize("extra", [(), ("--leg", "s1", "--rehearsal", "r2"), ("--leg", "makeup"), ("--leg", "s3"), ("--leg", "r1"),
                                   ("--rehearsal", "r1"), ("--rehearsal", "s1")])
def test_leg_and_rehearsal_refusals(extra, capsys):
    with pytest.raises(SystemExit) as exc:
        S.chain_entry().parse_args(_argv(*extra))
    assert exc.value.code == 2 and "REFUSED" in capsys.readouterr().err


# (c) delivery 2: the rehearsal assignment is part of the spec (R2 on X, R3 on N16): the other arm is refused
@pytest.mark.parametrize("kind,arm", [("r2", "n16"), ("r3", "x")])
def test_rehearsal_on_the_wrong_arm_is_refused(kind, arm, capsys):
    with pytest.raises(SystemExit) as exc:
        S.chain_entry().parse_args(_argv("--rehearsal", kind, arm=arm, out="tg2-m76-%s-rehearsal-%s.a1" % (arm, kind)))
    assert exc.value.code == 2 and "REFUSED" in capsys.readouterr().err


# (c) `--tg2-draw` defaults to the committed draw
def test_tg2_draw_default():
    a = S.chain_entry().parse_args(_argv("--leg", "pilot"))
    assert Path(a.tg2_draw) == S.DRAW_PATH


# (b) tg1's chain argument surface is unchanged: `chain s1 --p426 --lever kv` still parses to tg1's session / mode
def test_tg1_entry_argv_unchanged():
    a = S.tg1_chain_entry().parse_args(["chain", "s1", "--p426", "--lever", "kv", "--kv-arm", "n16", "--models", MODEL,
                                        "--predictor", "mtp", "--out-root", "o.a1", "--probe-code-sha", "a" * 64,
                                        "--policy-sha", "b" * 64, "--frozen-prompt-date", "Sat Oct 17 2026", "--campaign-core", "t",
                                        "--frozen-record", "r.json"])
    assert a.mode == "chain" and a.sessions == ["s1"] and a.rehearsal is False


# ------------------------------------------------------------------------------------------------ the chain object
class _Ops:
    """A minimal ops stand-in (the real chain constructor reads only `wd`)."""

    def __init__(self, wd):
        self.wd = wd


def _tg2_chain(tmp_path, *extra, leg_args=("--leg", "pilot"), ops=None, out=None):
    R = S.chain_entry()
    a = R.parse_args(_argv(*leg_args, *extra, out=str(tmp_path / "tg2-m76-n16-pilot.a1")))
    a.frozen_record = None                       # no record on disk here: the hooks fall back to the 900 s settle floor
    ops = ops or _Ops(tmp_path)
    return R.Chain(a, ops, None, lambda *_: None, {}, Path(out) if out else tmp_path / "o", campaign=SimpleNamespace()), a


# (c) docker is needed for EVERY tg2 language (the corpus decides); tg1's chain keeps "go only"
@pytest.mark.parametrize("lang", S.LANGS)
def test_tg2_chain_needs_docker_for_every_language(lang, tmp_path):
    chain, _ = _tg2_chain(tmp_path)
    assert chain.needs_docker(lang) is True


def test_tg1_chain_needs_docker_only_for_go(tmp_path):
    R1 = S.tg1_chain_entry()
    a = R1.parse_args(["chain", "s1", "--models", MODEL, "--probe-code-sha", "x"])
    chain = R1.Chain(a, _Ops(tmp_path), None, lambda *_: None, {"python": [], "go": []}, tmp_path / "o", campaign=SimpleNamespace())
    assert chain.needs_docker("go") is True and chain.needs_docker("python") is False


# (c) the tg2 chain freezes its schedule, installs the P426 hooks and plans `tg2-p426` slots: one load, one leg per language in the
# table's order, each with the schedule's single invocation; `verify_schedule` re-derives each leg from the draw
@pytest.mark.parametrize("leg", ["pilot", "s2"])
def test_plan_of_a_frozen_tg2_schedule(leg, tmp_path):
    from bench import p426_hooks
    chain, _ = _tg2_chain(tmp_path, leg_args=("--leg", leg))
    assert chain.freezes_schedule and isinstance(chain.hooks, p426_hooks.P426Hooks)
    chain.schedule = build(leg)
    (load,) = chain.plan()
    langs = TABLE[leg][2]
    assert [l["lang"] for l in load["legs"]] == list(langs) and load["session"] == TABLE[leg][0]
    for l in load["legs"]:
        # AMENDED (delivery 2): tg1's planner keys the slot on the ArmBinding's arm id (`oc`), the spec fixes only the `tg2-p426` prefix
        assert l["slot_base"] == "tg2-p426|oc|%s|%s|%s" % (MODEL, TABLE[leg][0], l["lang"]) and l["label"] == S.SCAFFOLD
        (inv,) = l["invocations"]
        assert inv["expect"] == prefix(l["lang"], TABLE[leg][3])
        chain.verify_schedule(l)


def test_verify_schedule_refuses_a_leg_that_is_not_the_draw_prefix(tmp_path):
    from bench import chain_ops
    chain, _ = _tg2_chain(tmp_path)
    chain.schedule = build("s1")
    (load,) = chain.plan()
    leg = dict(load["legs"][0])
    leg["items"] = list(reversed(leg["items"]))
    with pytest.raises(chain_ops.ChainAbort):
        chain.verify_schedule(leg)


# ------------------------------------------------------------------------------------------------ R2 / R3 on Rust
def _hooked(tmp_path, kind):
    from bench.tests import test_b2_s4_reconcile as T
    ops, _hooks, out = T.make_hooks(tmp_path)
    ops.wd = tmp_path
    R = S.chain_entry()
    a = R.parse_args(_argv("--rehearsal", kind, out=str(tmp_path / ("tg2-m76-x-rehearsal-%s.a1" % kind))))
    a.frozen_record = None
    chain = R.Chain(a, ops, None, lambda *_: None, {}, out, campaign=SimpleNamespace())
    chain.hooks.bind_router(5, 2.0)
    return ops, chain, T


def _serve(T, ops, hooks, slot, item, k):
    from bench.tests.test_p586_impl_rehearsal import serve_item
    return serve_item(ops, hooks, slot, item, k)


# (c) R2: the reconciliation-mismatch injection fires on the first item of the leg's first language — tg2: the first RUST item —
# and invalidates with `INJECTED_MISMATCH` (`R2_REASON`); a later Rust item and a non-Rust first item are not touched
def test_r2_invalidates_the_first_rust_item(tmp_path):
    from bench import p426_hooks as ph
    ops, chain, T = _hooked(tmp_path, "r2")
    slot = "0|A|%s|s1|rust|say" % MODEL
    d = _serve(T, ops, chain.hooks, slot, "rust/say", 0)
    assert d.kind == "invalidate" and d.reason == ph.INJECTED_MISMATCH
    d2 = _serve(T, ops, chain.hooks, "0|A|%s|s1|rust|poker" % MODEL, "rust/poker", 1)
    assert d2.kind == "accept"


def test_r2_does_not_fire_on_a_non_rust_first_item(tmp_path):
    ops, chain, T = _hooked(tmp_path, "r2")
    d = _serve(T, ops, chain.hooks, "0|A|%s|s1|javascript|word-search" % MODEL, "javascript/word-search", 0)
    assert d.kind == "accept"


# (b) tg1's R2 is unchanged: Go fires, Python does not
def test_tg1_r2_still_fires_on_go(tmp_path):
    from bench import p426_hooks as ph
    from bench.tests import test_p586_impl_rehearsal as P
    ops, hooks = P.injected_hooks(tmp_path)
    assert P.serve_item(ops, hooks, P.SLOT_PY, "python/a", 0).kind == "accept"
    assert P.serve_item(ops, hooks, P.SLOT_GO, "go/b", 1).reason == ph.INJECTED_MISMATCH


# (c) R3: the probe kill (`--inject-stall-item`) goes to the ONE invocation holding the first RUST item of the rehearsal schedule
def test_r3_stall_target_is_the_first_rust_item(tmp_path):
    chain, a = _tg2_chain(tmp_path, leg_args=("--rehearsal", "r3"))
    chain.schedule = rehearsal_schedule("r3")
    (load,) = chain.plan()
    (leg,) = load["legs"]
    step = leg["invocations"][0]
    first = prefix("rust", 1)[0]
    got = chain.p426_inject_stall(leg, step)
    assert got is not None and got[0] == first and got[1] == 30
    assert chain.p426_inject_stall(dict(leg, lang="javascript"), step) is None


def test_tg1_stall_target_is_still_python(tmp_path):
    from bench import chain_core as core
    R1 = S.tg1_chain_entry()
    a = R1.parse_args(["chain", "s1", "--p426", "--rehearsal", "--inject", "stall-kill", "--models", MODEL, "--probe-code-sha", "x",
                       "--predictor", "mtp", "--out-root", "o.a1", "--policy-sha", "a" * 64, "--frozen-prompt-date",
                       "Sat Oct 17 2026", "--campaign-core", "t", "--frozen-record", "r.json"])
    cfg = R1.tg1_config(a)
    a.frozen_record = None
    chain = core.Chain(cfg, a, _Ops(tmp_path), None, lambda *_: None, repo=tmp_path, out_root=tmp_path / "o", names={},
                       lifecycle_files={})
    from bench import schedules
    chain.schedule = schedules.tg1("chain", ["s1"], {"python": ["a", "b", "c"], "go": ["g1", "g2"]}, picks=(MODEL,), p426=True,
                                   rehearsal=True)
    leg = chain.schedule["blocks"][0]["legs"][0]
    step = leg["invocations"][0]
    assert chain.p426_inject_stall(dict(leg, lang="python"), step)[0].startswith("python/")
    assert chain.p426_inject_stall(dict(leg, lang="go"), step) is None


# ------------------------------------------------------------------------------------------------ the carrier
# (c) the tg2 carrier is tg1's, with the tg2 label: it differs from tg1's only in strings that name the scaffold
def test_carrier_is_tg1s_with_the_tg2_label():
    tg1 = json.loads((S.BENCH / "opencode_bench_v2_web_tg1.json").read_text())
    path = S.BENCH / "opencode_bench_v2_web_tg2.json"
    assert path.is_file(), "benchmark/opencode_bench_v2_web_tg2.json is missing"
    tg2 = json.loads(path.read_text())

    def flat(o, p=()):
        if isinstance(o, dict):
            for k, v in o.items():
                yield from flat(v, p + (k,))
        elif isinstance(o, list):
            for i, v in enumerate(o):
                yield from flat(v, p + (i,))
        else:
            yield p, o
    a, b = dict(flat(tg1)), dict(flat(tg2))
    assert set(a) == set(b)
    diff = {k: (a[k], b[k]) for k in a if a[k] != b[k]}
    assert all("tg1" in str(x) and str(x).replace("tg1", "tg2") == str(y) for x, y in diff.values()), diff


def test_configgen_target_and_generated_paths(monkeypatch):
    monkeypatch.syspath_prepend(str(S.REPO))
    from bench import modelnames
    from configgen import targets
    names = {n: p for n, _, p in targets.BENCH_TARGETS}
    assert names.get("opencode-bench-v2-web-tg2") == "benchmark/opencode_bench_v2_web_tg2.json"
    assert "benchmark/opencode_bench_v2_web_tg2.json" in modelnames.GENERATED_PATHS
    assert names["opencode-bench-v2-web-tg1"] == "benchmark/opencode_bench_v2_web_tg1.json"
