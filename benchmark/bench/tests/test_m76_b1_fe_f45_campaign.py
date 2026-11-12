"""M76 B1 (test-writer): the `f45` campaign table, CLI, names, paths, order, idle sources, preflight and campaign isolation.

Class per test: (a) reproduces a failure the specification fixes, (b) preserves an invariant, (c) new behaviour.
Everything goes through public entries: `main([... "--campaign", "f45", ...], ops)`, `K.run_leg` with a fake ops object, the
`CAMPAIGNS` table the specification names.
"""
from __future__ import annotations

import dataclasses
import json

import pytest

from bench import p475_kv as K
from bench.tests.test_m76_b1_fe_golden_u4 import _u4_world
from bench.tests.test_m76_b1_fe_support import (BASE, F45_ARMS, F45_PICK, GRID, World, cli, find_dicts, prepare_f45,  # noqa: F401
                                                prepared_texts, resign, world)
from bench.tests.test_p475_impl_support import FakeOps, make_cfg


def listing(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")) if root.exists() else []


# ================================================================================================ the campaign table
def test_the_campaign_table_holds_u4_and_f45():
    """(c) Interfaces: a frozen dataclass `Campaign`, `CAMPAIGNS = {"u4": …, "f45": …}`, the table's fields."""
    assert dataclasses.is_dataclass(K.Campaign) and set(K.CAMPAIGNS) == {"u4", "f45"}
    u4, f45 = K.CAMPAIGNS["u4"], K.CAMPAIGNS["f45"]
    assert isinstance(u4, K.Campaign) and isinstance(f45, K.Campaign)
    assert (u4.pick, u4.short, tuple(u4.arms), u4.base_arm, u4.reference_arm, tuple(u4.off_arms), tuple(u4.smoke_arms)) == (
        "Qwen3.8-27B-mlx-uniform-4bit", "u4", ("N16", "AF8", "TQ8", "AF4", "TQ4", "TQ4-OFF"), "TQ4", "N16", ("TQ4-OFF",),
        ("N16", "TQ4"))
    assert (f45.pick, f45.short, tuple(f45.arms), f45.base_arm, f45.reference_arm, tuple(f45.off_arms), tuple(f45.smoke_arms)) == (
        F45_PICK, "f45", ("N16", "X", "V", "XO"), "N16", "N16", ("XO",), ("N16", "X"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        f45.pick = "other"


def test_the_u4_module_constants_are_today_s():
    """(b) The u4 constants the existing tests import stay (u4 is byte-identical, acceptance 3)."""
    assert K.PICK == "Qwen3.8-27B-mlx-uniform-4bit" and K.PICK_SHORT == "u4"
    assert K.ARMS == ("N16", "AF8", "TQ8", "AF4", "TQ4", "TQ4-OFF") and K.BASE_ARM == "TQ4" and K.REFERENCE_ARM == "N16"
    assert K.SMOKE_ARMS == ("N16", "TQ4") and K.GRID == GRID


def test_campaign_option_defaults_to_u4_and_names_f45():
    """(c) `--campaign` (default u4)."""
    assert K.parse_args(["matrix"]).campaign == "u4"
    assert K.parse_args(["--campaign", "f45", "matrix"]).campaign == "f45"
    assert K.parse_args(["--campaign", "u4", "run"]).campaign == "u4"


def test_an_unknown_campaign_is_refused(tmp_path):
    """(c) Not one of the table's keys: refused (argparse choice or REFUSED rc 2) — while a table key is accepted."""
    assert K.parse_args(["--workdir", str(tmp_path), "--campaign", "f45", "matrix"]).campaign == "f45"
    assert cli(["--workdir", str(tmp_path), "--campaign", "zz9", "matrix"], FakeOps(tmp_path)) == 2


def test_the_default_campaign_equals_u4_for_the_matrix(tmp_path):
    """(c) `--campaign u4` and no flag read the same results (u4 golden world): same bytes, same rc."""
    repo, wd, base, results = _u4_world(tmp_path)
    from bench.tests.test_m76_b1_fe_golden_u4 import GitOnly, _matrix_argv
    assert cli(_matrix_argv(repo, wd, base, "--campaign", "u4"), GitOnly(base)) == cli(_matrix_argv(repo, wd, base), GitOnly(base)) == 0


# ================================================================================================ prepare: names and paths
def test_prepare_f45_makes_its_branches_worktrees_and_scratch_state(tmp_path):
    """(c) branch `m76-f45-<arm>`, worktree under `$STACK_WORKDIR/worktrees`, state under `$STACK_WORKDIR/m76/p475`; nothing under
    the u4 scratch dir."""
    rc, ops, wd = prepare_f45(tmp_path)
    assert rc == 0
    adds = [a for _, a in ops.calls if a[:2] == ("worktree", "add") and "-b" in a]
    assert sorted(a[a.index("-b") + 1] for a in adds) == sorted(f"m76-f45-{x.lower()}" for x in F45_ARMS)
    assert sorted(a[a.index("-b") + 2] for a in adds) == sorted(str(wd / "worktrees" / f"m76-f45-{x.lower()}") for x in F45_ARMS)
    state = json.loads((wd / "m76" / "p475" / "state.json").read_text())
    assert state["base"] == BASE and state["campaign"] == "f45"
    assert not (wd / "p475").exists()


def test_prepare_f45_commits_nothing_on_the_base_arm_and_one_commit_on_each_other(tmp_path):
    """(c) N16 is the base commit itself; X, V, XO each carry exactly one registry commit on top of the base."""
    rc, ops, wd = prepare_f45(tmp_path)
    assert rc == 0
    assert ops.branches["m76-f45-n16"] == BASE and ops.committed("m76-f45-n16") is None
    commits = [a for _, a in ops.calls if a[:1] == ("commit",)]
    assert len(commits) == 3
    for arm in ("x", "v", "xo"):
        assert ops.committed(f"m76-f45-{arm}") is not None and ops.branches[f"m76-f45-{arm}"] != BASE


def test_prepare_u4_is_untouched_by_an_f45_prepare(tmp_path):
    """(b) Isolation: preparing f45 never writes the u4 scratch tree or the u4 results dir."""
    rc, ops, wd = prepare_f45(tmp_path)
    assert rc == 0 and not (wd / "p475").exists() and not (tmp_path / "repo" / "benchmark").exists()


# ================================================================================================ a full f45 run
def test_a_full_f45_run_is_abba_ordered_named_and_isolated(world):
    """(c) leg names `f45-<arm>-b<k>.a<n>`, block 1 N16, X, V, XO and block 2 reversed; everything under the f45 roots."""
    w = world
    assert w.main("run") == 0, w.ops.spawned_legs()
    assert w.ops.spawned_legs() == [f"f45-{a.lower()}-b1.a1" for a in F45_ARMS] + [f"f45-{a.lower()}-b2.a1" for a in reversed(F45_ARMS)]
    assert sorted(p.name for p in w.results.iterdir() if p.is_dir()) == sorted(
        f"f45-{a.lower()}-b{b}.a1" for a in F45_ARMS for b in (1, 2))
    assert (w.results / f"MATRIX.{F45_PICK}.md").is_file() and not (w.results / f"MATRIX.{F45_PICK}.PARTIAL.md").exists()
    for name in ("state.json", "RUNLOG.md", "LAST_LEG_END", "legs"):
        assert (w.scratch / name).exists(), name
    assert not (w.wd / "p475").exists()                                        # the u4 scratch tree is never touched
    assert not (w.repo / "benchmark" / "results" / "p475").exists()            # nor the u4 results dir
    assert sorted(p.name for p in (w.wd / "worktrees").iterdir()) == sorted(f"m76-f45-{a.lower()}" for a in F45_ARMS)
    assert json.loads((w.scratch / "state.json").read_text())["campaign"] == "f45"


def test_the_f45_receipt_and_driver_argv_are_the_campaigns(world):
    """(c) A leg's receipt records the campaign, the f45 pick, the branch; the driver argv names the pick and the f45 scratch."""
    w = world
    name, r = w.run_leg("X")
    assert r["verdict"] == "VALID", r["problems"]
    on_disk = json.loads(w.cfg.receipt_path(name).read_text())
    assert on_disk["campaign"] == "f45" and on_disk["model"] == F45_PICK and on_disk["arm"] == "X"
    assert on_disk["identity_entry"]["branch"] == "m76-f45-x"
    d = on_disk["driver_argv"]
    assert d[d.index("--model") + 1] == F45_PICK and d[d.index("--grid") + 1] == "8192,131072,196608,260096"
    assert str(w.scratch / "legs" / name / "capacity") == d[d.index("--out-dir") + 1]
    assert d[d.index("--out-tag") + 1].endswith(name)
    assert w.ops.spawned[0]["env"]["MLX_SERVE_CONFIG"] == str(w.wd / "worktrees" / "m76-f45-x" / "main_models.yaml")
    assert (w.results / name / "receipt.json").is_file()
    assert float((w.scratch / "LAST_LEG_END").read_text()) == w.ops.t


def test_the_f45_smoke_is_n16_then_x_on_the_8192_rung(world):
    """(c) `smoke_arms` N16, X."""
    w = world
    assert w.main("run", "--smoke") == 0
    assert w.ops.spawned_legs() == ["f45-n16-smoke.a1", "f45-x-smoke.a1"]
    sp = w.ops.spawned[0]["argv"]
    assert sp[sp.index("--grid") + 1] == "8192"


def test_the_predictor_is_off_only_on_xo(world):
    """(c) `off_arms` = XO: the router of XO is started predictor-off, the others on."""
    w = world
    for arm in F45_ARMS:
        _, r = w.run_leg(arm)
        assert r["verdict"] == "VALID", (arm, r["problems"])
        assert r["predictor"] == ("off" if arm == "XO" else "on")
        assert ("stack", str(w.cfg.worktree(arm)), str(w.cfg.registry(arm)), "off" if arm == "XO" else "mtp") in w.ops.calls
        w.ops.t += 700                                                          # the idle between legs
    xo = json.loads(w.cfg.receipt_path("f45-xo-b1.a1").read_text())
    assert "--draft-kind" not in xo["worker_argv"] and "--mtp-verify-scan" not in xo["worker_argv"]
    x = json.loads(w.cfg.receipt_path("f45-x-b1.a1").read_text())
    assert "--tq4-attention" in x["worker_argv"] and x["worker_argv"][x["worker_argv"].index("--tq4-attention") + 1] == "m72_exact"
    v = json.loads(w.cfg.receipt_path("f45-v-b1.a1").read_text())
    assert v["worker_argv"][v["worker_argv"].index("--tq4-attention") + 1] == "m72_v1"


def test_the_arm_tables_of_the_other_campaign_are_refused(world):
    """(c) `--arm AF8` is not an f45 arm; `--arm X` is not a u4 arm. A foreign arm is refused either as rc 2 or as argparse's
    `SystemExit(2)` (`cli` maps it to 2)."""
    w = world
    assert cli(w.argv("preflight", "--arm", "AF8"), w.ops) == 2
    assert cli(w.argv("preflight", "--arm", "X", campaign="u4"), w.ops) == 2


# ================================================================================================ idle sources
@pytest.mark.parametrize("where", ["m76/p475", "p475", "p426"])
def test_an_f45_leg_waits_for_the_latest_of_the_three_idle_sources(world, where):
    """(c) `LAST_LEG_END` of p475, p426 and m76/p475 all count for an f45 leg."""
    w = world
    (w.wd / where).mkdir(parents=True, exist_ok=True)
    (w.wd / where / "LAST_LEG_END").write_text(f"{w.ops.t - 100}\n")
    _, r = w.run_leg("N16")
    assert r["verdict"] == "NOT_STARTED" and any("since LAST_LEG_END" in p for p in r["problems"]), r["problems"]
    assert not w.ops.spawned


def test_a_u4_leg_also_waits_for_the_m76_scratch_idle(tmp_path):
    """(c) "u4's list gains m76/p475"."""
    ops, cfg = FakeOps(tmp_path), make_cfg(tmp_path)
    ops.add_all(cfg)
    (cfg.workdir / "m76" / "p475").mkdir(parents=True)
    (cfg.workdir / "m76" / "p475" / "LAST_LEG_END").write_text(f"{ops.t - 100}\n")
    r = K.run_leg(K.leg_name("N16", 1, 1), "N16", ops, cfg)
    assert r["verdict"] == "NOT_STARTED" and any("since LAST_LEG_END" in p for p in r["problems"]), r["problems"]


def test_an_f45_harvest_writes_the_idle_marker_in_its_own_scratch_only(world):
    """(c) R8 for f45: the marker is `m76/p475/LAST_LEG_END`; the u4 marker is never created."""
    w = world
    _, r = w.run_leg("N16")
    assert r["verdict"] == "VALID" and (w.scratch / "LAST_LEG_END").is_file() and not (w.wd / "p475" / "LAST_LEG_END").exists()


# ================================================================================================ preflight
def _fresh_preflight(w, arm, kind="off"):
    w.cfg.preflight_record(arm, kind).unlink()


def test_the_f45_preflight_runs_qualify_for_the_f45_pick_in_its_own_record(world):
    """(c) `preflight --arm X`: the fork's qualify `--kv-arm --predictor off --entry <f45 pick>` on the X worktree; the record
    lives under `m76/p475/preflight`."""
    w = world
    _fresh_preflight(w, "X")
    assert w.main("preflight", "--arm", "X") == 0
    argv = next(c[1] for c in w.ops.calls if c[0] == "run")
    wt = w.wd / "worktrees" / "m76-f45-x"
    assert argv[argv.index("--entry") + 1] == F45_PICK and argv[argv.index("--predictor") + 1] == "off"
    assert argv[argv.index("--stack-root") + 1] == str(wt) and "--kv-arm" in argv and "--engagement-only" not in argv
    rec = json.loads((w.scratch / "preflight" / "X.json").read_text())
    assert rec["status"] == "PASS" and rec["model"] == F45_PICK


def test_the_f45_engagement_check_is_for_the_mtp_on_arms_only(world):
    """(c) `--engagement` for N16, X, V; XO (predictor OFF) refuses."""
    w = world
    for arm in ("N16", "X", "V"):
        _fresh_preflight(w, arm, "engagement")
        assert w.main("preflight", "--arm", arm, "--engagement") == 0, arm
        argv = [c[1] for c in w.ops.calls if c[0] == "run"][-1]
        assert argv[argv.index("--predictor") + 1] == "on" and "--engagement-only" in argv
        assert (w.scratch / "engagement" / f"{arm}.json").is_file()
    assert w.main("preflight", "--arm", "XO", "--engagement") == 2


def test_an_f45_leg_needs_its_off_preflight_and_the_on_arms_their_engagement_check(world):
    """(c) R15 for f45: no PASS record -> NOT_STARTED, per kind, XO needs only the OFF one."""
    w = world
    _fresh_preflight(w, "V", "engagement")
    _, r = w.run_leg("V")
    assert r["verdict"] == "NOT_STARTED" and any("engagement" in p for p in r["problems"]), r["problems"]
    _fresh_preflight(w, "XO", "off")
    _, r = w.run_leg("XO")
    assert r["verdict"] == "NOT_STARTED" and any("preflight" in p for p in r["problems"]), r["problems"]


# ================================================================================================ campaign isolation
def _finished(w):
    assert w.main("run") == 0
    return w


def test_an_f45_dossier_recorded_for_another_campaign_refuses(world):
    """(c) A dossier whose receipt says `campaign: u4` is refused by the f45 matrix (PARTIAL, nonzero)."""
    w = _finished(world)
    d = w.results / "f45-x-b1.a1"
    receipt = json.loads((d / "receipt.json").read_text())
    receipt["campaign"] = "u4"
    (d / "receipt.json").write_text(json.dumps(receipt))
    resign(d)
    rc = w.main("matrix")
    assert rc != 0 and (w.results / f"MATRIX.{F45_PICK}.PARTIAL.md").is_file() and not (w.results / f"MATRIX.{F45_PICK}.md").exists()
    assert "campaign" in (w.results / f"MATRIX.{F45_PICK}.PARTIAL.md").read_text().lower()


def test_an_f45_dossier_without_a_campaign_field_reads_as_u4_and_refuses(world):
    """(c) "a u4 record without the field reads as u4": under f45 it is refused."""
    w = _finished(world)
    d = w.results / "f45-v-b2.a1"
    receipt = json.loads((d / "receipt.json").read_text())
    assert receipt.get("campaign") == "f45"
    del receipt["campaign"]
    (d / "receipt.json").write_text(json.dumps(receipt))
    resign(d)
    assert w.main("matrix") != 0 and (w.results / f"MATRIX.{F45_PICK}.PARTIAL.md").is_file()


@pytest.mark.parametrize("kind", ["off", "engagement"])
@pytest.mark.parametrize("stamp", ["missing", "u4"])
def test_a_preflight_record_of_another_campaign_does_not_pass_an_f45_leg(world, kind, stamp):
    """(c) Errata v1.1: preflight / engagement records carry `campaign` and are checked like dossiers (a record without the field
    reads as u4): either form under f45 -> NOT_STARTED, nothing starts."""
    w = world
    path = w.cfg.preflight_record("X", kind)
    rec = json.loads(path.read_text())
    assert rec["campaign"] == "f45"
    if stamp == "missing":
        del rec["campaign"]
    else:
        rec["campaign"] = "u4"
    path.write_text(json.dumps(rec))
    _, r = w.run_leg("X")
    assert r["verdict"] == "NOT_STARTED" and any("campaign" in p for p in r["problems"]), r["problems"]
    assert not w.ops.spawned


def test_the_preflight_records_the_f45_command_writes_carry_the_campaign(world):
    """(c) Errata v1.1: the records `preflight` writes under f45 are stamped `campaign: f45` (both kinds)."""
    w = world
    for kind, extra in (("off", ()), ("engagement", ("--engagement",))):
        w.cfg.preflight_record("X", kind).unlink()
        assert w.main("preflight", "--arm", "X", *extra) == 0
        assert json.loads(w.cfg.preflight_record("X", kind).read_text())["campaign"] == "f45"


def test_a_u4_dossier_recorded_for_f45_refuses_under_u4(tmp_path):
    """(c) And vice versa: a u4 dossier whose receipt says `campaign: f45` makes the u4 matrix PARTIAL."""
    repo, wd, base, results = _u4_world(tmp_path)
    d = results / "u4-af8-b1.a1"
    receipt = json.loads((d / "receipt.json").read_text())
    receipt["campaign"] = "f45"
    (d / "receipt.json").write_text(json.dumps(receipt))
    resign(d)
    from bench.tests.test_m76_b1_fe_golden_u4 import GitOnly, _matrix_argv
    rc = cli(_matrix_argv(repo, wd, base), GitOnly(base))
    assert rc != 0 and (results / "MATRIX.Qwen3.8-27B-mlx-uniform-4bit.PARTIAL.md").is_file()
    assert not (results / "MATRIX.Qwen3.8-27B-mlx-uniform-4bit.md").exists()


def test_a_u4_state_file_under_f45_and_an_f45_state_under_u4_refuse(world):
    """(c) State files carry the campaign: a u4 state (no field) at the f45 path and an f45 state at the u4 path both refuse
    (REFUSED, rc 2) for `run` and `matrix`, and nothing is run."""
    w = world
    w.scratch.mkdir(parents=True, exist_ok=True)                  # the fake world already holds the preflight records there
    (w.scratch / "state.json").write_text(json.dumps(dict(version=1, model="Qwen3.8-27B-mlx-uniform-4bit", base=BASE,
                                                          used=dict(replacements=0, not_started=0, deciding=0),
                                                          refused_arms=[], legs=[])))
    assert w.main("run") == 2 and w.main("matrix") == 2 and not w.ops.spawned
    (w.wd / "p475").mkdir()
    (w.wd / "p475" / "state.json").write_text(json.dumps(dict(version=1, campaign="f45", model=F45_PICK, base=BASE,
                                                              used=dict(replacements=0, not_started=0, deciding=0),
                                                              refused_arms=[], legs=[])))
    assert cli(w.argv("run", campaign="u4"), w.ops) == 2 and cli(w.argv("matrix", campaign="u4"), w.ops) == 2
    assert not w.ops.spawned


def test_f45_and_u4_rows_never_share_a_results_root(world):
    """(b) The two campaigns' dossier roots are disjoint directories."""
    w = world
    assert w.cfg.results == w.repo / "benchmark" / "results" / "m76" / "matrix"
    u4 = w.config("run", campaign="u4")
    assert u4.results == w.repo / "benchmark" / "results" / "p475" and u4.p475 == w.wd / "p475"
    assert w.cfg.p475 == w.wd / "m76" / "p475"
