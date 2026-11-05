"""P475 stage 1 (implementer tests): preflight (R15), run control (R13, R14, R16), resume (R18, R19), matrix (R20)."""
from __future__ import annotations

import json

import pytest

from bench import p475_kv as K
from bench.tests.test_p475_impl_support import BASE, FakeOps, make_cfg


@pytest.fixture
def world(tmp_path):
    ops, cfg = FakeOps(tmp_path), make_cfg(tmp_path)
    ops.add_all(cfg)
    return ops, cfg


def args_for(cfg, *extra, cmd="run"):
    return K.parse_args(["--workdir", str(cfg.workdir), "--repo", str(cfg.repo), "--base", BASE, cmd, *extra])


def legs_run(ops):
    """The leg names in launch order (from the driver argv)."""
    out = []
    for s in ops.spawned:
        tag = s["argv"][s["argv"].index("--out-tag") + 1]
        out.append(tag[len("p475-"):])
    return out


# ------------------------------------------------------------------------------------------------ preflight (R15)
def test_preflight_argv_is_the_p426_qualify_argv_plus_kv_arm(world):
    ops, cfg = world
    rec = K.preflight("AF8", ops, cfg)
    assert rec["status"] == "PASS" or K.read_preflight(cfg, "AF8")["status"] == "PASS"
    cfg.preflight_record("TQ8").unlink()
    rec = K.preflight("TQ8", ops, cfg)
    argv = next(c[1] for c in ops.calls if c[0] == "run")
    wt = cfg.worktree("TQ8")
    assert argv[:2] == [str(wt / ".venv/bin/python"), str(wt / "src/mlx-vlm/dev/p369_phase2/qualify.py")]
    for flag, value in (("--stack-root", str(wt)), ("--fork-root", str(wt / "src/mlx-vlm")), ("--entry", K.PICK),
                        ("--predictor", "off"), ("--reviewed-head", ops.arms["TQ8"]["gitlinks"]["src/mlx-vlm"])):
        assert argv[argv.index(flag) + 1] == value
    assert argv[-1] == "--kv-arm" and rec["status"] == "PASS"
    assert json.loads(cfg.preflight_record("TQ8").read_text())["status"] == "PASS"


def test_a_refusing_preflight_is_retried_at_most_the_cap_then_refused(world):
    ops, cfg = world
    cfg.preflight_record("AF4").unlink()
    ops.qualify["AF4"] = ["FAILED", "INVALID", "FAILED", "COMPLETED"]
    rec = K.preflight("AF4", ops, cfg, max_retries=2)
    assert rec["status"] == "REFUSED" and len(rec["attempts"]) == 3
    assert K.preflight("AF4", ops, cfg)["status"] == "REFUSED"                       # a final record is never redone
    assert sum(1 for c in ops.calls if c[0] == "run") == 3


def test_a_preflight_passes_on_a_retry(world):
    ops, cfg = world
    cfg.preflight_record("AF4").unlink()
    ops.qualify["AF4"] = ["FAILED", "COMPLETED"]
    rec = K.preflight("AF4", ops, cfg)
    assert rec["status"] == "PASS" and len(rec["attempts"]) == 2


def test_preflight_requires_the_kv_arm_entry(world):
    assert K.preflight_report_problems(dict(entries={K.PICK: dict(status="COMPLETED")}), K.PICK)
    assert K.preflight_report_problems(dict(entries={K.PICK: dict(status="COMPLETED")}, kv_arm=dict(entry="x")), K.PICK)
    assert K.preflight_report_problems(dict(entries={K.PICK: dict(status="COMPLETED")}, kv_arm=dict(entry=K.PICK)), K.PICK) == []


def test_a_refused_arm_is_skipped_and_the_run_exits_nonzero(world):
    ops, cfg = world
    cfg.preflight_record("TQ8").unlink()
    ops.qualify["TQ8"] = ["FAILED"]
    rc = K.run(args_for(cfg, "--max-preflight", "0"), ops)
    assert rc == 1
    assert not any(n.startswith("u4-tq8-") for n in legs_run(ops))
    assert len(legs_run(ops)) == 10
    assert cfg.results.joinpath(f"MATRIX.{K.PICK}.PARTIAL.md").exists()
    assert "refused arms (preflight): ['TQ8']" in cfg.results.joinpath(f"MATRIX.{K.PICK}.PARTIAL.md").read_text()


# ------------------------------------------------------------------------------------------------ the full run, ABBA, idle
def test_a_full_run_is_abba_ordered_idle_spaced_and_writes_the_matrix(world):
    ops, cfg = world
    rc = K.run(args_for(cfg), ops)
    assert rc == 0
    names = legs_run(ops)
    assert names == [f"u4-{a.lower()}-b1.a1" for a in K.ARMS] + [f"u4-{a.lower()}-b2.a1" for a in reversed(K.ARMS)]
    # every leg after the first waited out the 600 s since the previous harvest
    launches = [c for c in ops.spawned]
    assert len(launches) == 12 and ops.slept.count(600.0) >= 11
    m = cfg.results / f"MATRIX.{K.PICK}.md"
    text = m.read_text()
    assert "one pick (partial matrix, P475 v4)" in text and "descriptive (two order-balanced speed-valid legs per arm" in text.lower()
    assert "GENERATED" in text and "| TQ4-OFF | 8192 |" in text
    assert not (cfg.results / f"MATRIX.{K.PICK}.PARTIAL.md").exists()


def test_the_idle_wait_counts_from_the_harvest_end(world):
    ops, cfg = world
    name, r = K.leg_name("N16", 1, 1), None
    r = K.run_leg(name, "N16", ops, cfg)
    end = float((cfg.p475 / "LAST_LEG_END").read_text())
    assert end == ops.t
    ops.t += 100
    r2 = K.run_leg(K.leg_name("AF8", 1, 1), "AF8", ops, cfg)
    assert r2["verdict"] == "NOT_STARTED" and any("since LAST_LEG_END" in p for p in r2["problems"])
    K._wait_idle(ops, cfg)
    assert ops.slept[-1] == pytest.approx(500.0)


# ------------------------------------------------------------------------------------------------ replacements (R13)
def test_a_speed_invalid_leg_is_replaced_after_the_blocks_ordered_legs(world):
    ops, cfg = world
    ops.leg_script["u4-af8-b1.a1"] = dict(watch_mode="power_fail")
    ops.leg_script["u4-tq8-b1.a1"] = dict(watch_mode="gap")
    assert K.run(args_for(cfg), ops) == 0
    names = legs_run(ops)
    b1 = [f"u4-{a.lower()}-b1.a1" for a in K.ARMS]
    assert names[:6] == b1 and names[6:8] == ["u4-af8-b1.a2", "u4-tq8-b1.a2"]      # block order kept
    assert names[8] == "u4-tq4-off-b2.a1"
    state = json.loads(cfg.state_path.read_text())
    assert state["used"]["replacements"] == 2
    text = (cfg.results / f"MATRIX.{K.PICK}.md").read_text()
    assert "replaced (speed-invalid): ['u4-af8-b1.a1', 'u4-tq8-b1.a1']" in text


def test_the_replacement_cap_leaves_the_matrix_partial(world):
    ops, cfg = world
    for n in range(1, 4):
        ops.leg_script[f"u4-af8-b1.a{n}"] = dict(watch_mode="absent")
    assert K.run(args_for(cfg, "--max-replacements", "1"), ops) == 1
    assert "u4-af8-b1.a3" not in legs_run(ops) and "u4-af8-b1.a2" in legs_run(ops)
    assert (cfg.results / f"MATRIX.{K.PICK}.PARTIAL.md").exists()


# ------------------------------------------------------------------------------------------------ NOT_STARTED (R14), INVALID
def test_not_started_is_retried_after_its_own_idle_and_bounded(world):
    ops, cfg = world
    ops.busy_list.append("4242 opencode run x")
    real_sleep = ops.sleep

    def sleep(s):
        real_sleep(s)
        if len(ops.slept) >= 3:
            ops.busy_list.clear()
    ops.sleep = sleep
    assert K.run(args_for(cfg, "--blocks", "1"), ops) in (0, 1)
    recs = [K.read_receipt(d) for d in sorted((cfg.p475 / "legs").iterdir())]
    not_started = [r for r in recs if r["verdict"] == "NOT_STARTED"]
    assert not_started and all(r["leg"].startswith("u4-n16-b1.a") for r in not_started)
    assert legs_run(ops)[0] == f"u4-n16-b1.a{len(not_started) + 1}"
    assert 600.0 in ops.slept


def test_the_not_started_cap_stops_the_run(world):
    ops, cfg = world
    ops.busy_list.append("4242 opencode run x")
    assert K.run(args_for(cfg, "--max-not-started", "2"), ops) == 1
    recs = [K.read_receipt(d) for d in sorted((cfg.p475 / "legs").iterdir())]
    assert len(recs) == 3 and all(r["verdict"] == "NOT_STARTED" for r in recs)
    assert not ops.spawned


def test_an_invalid_leg_stops_the_run(world):
    ops, cfg = world
    ops.leg_script["u4-af8-b1.a1"] = dict(driver_rc=1)
    assert K.run(args_for(cfg), ops) == 1
    assert legs_run(ops) == ["u4-n16-b1.a1", "u4-af8-b1.a1"]
    assert cfg.dossier("u4-af8-b1.a1").is_dir()                                     # kept as evidence
    # a resume does not run past the standing INVALID leg
    assert K.run(args_for(cfg), ops) == 1 and len(legs_run(ops)) == 2


# ------------------------------------------------------------------------------------------------ instability -> deciding block (R16)
def _unstable(arm, block, ctx):
    if arm == "AF8" and ctx == 8192:
        return dict(decode=33.0 if block == 1 else 27.0)                          # ratio 1.1 then 0.9 vs N16's 30
    return {}


def test_instability_rule():
    vals = {("N16", 1): {8192: dict(decode=30.0)}, ("N16", 2): {8192: dict(decode=30.0)},
            ("AF8", 1): {8192: dict(decode=33.0)}, ("AF8", 2): {8192: dict(decode=27.0)}}
    f = K.instability(vals)[("AF8", 8192, "decode")]
    assert f["reversal"] and f["flag"]
    vals[("AF8", 2)] = {8192: dict(decode=34.5)}                                     # 1.10 / 1.15: |0.05| > 0.0625? no
    assert not K.instability(vals)[("AF8", 8192, "decode")]["flag"]
    vals[("AF8", 2)] = {8192: dict(decode=39.0)}                                     # 1.10 / 1.30: |0.2| > 0.1 -> spread
    f = K.instability(vals)[("AF8", 8192, "decode")]
    assert f["spread"] and not f["reversal"]


def test_an_unstable_pair_triggers_one_deciding_block_in_its_own_column(world):
    ops, cfg = world
    ops.metric = _unstable
    assert K.run(args_for(cfg), ops) == 0
    names = legs_run(ops)
    assert names[12:] == [f"u4-{a.lower()}-b3.a1" for a in K.ARMS]                   # block-1 order
    state = json.loads(cfg.state_path.read_text())
    assert state["used"]["deciding"] == 1
    text = (cfg.results / f"MATRIX.{K.PICK}.md").read_text()
    assert "b3 (deciding)" in text and "REVERSAL" in text
    row = next(ln for ln in text.splitlines() if ln.startswith("| AF8 | 8192 |") and "REVERSAL" in ln)
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[2:5] == ["33.00", "27.00", "30.00"]                                 # b1, b2, the two-block mean
    # a resume does not start a second deciding block (cap 1)
    assert K.run(args_for(cfg), ops) == 0 and len(legs_run(ops)) == 18


def test_no_deciding_block_under_a_zero_cap(world):
    ops, cfg = world
    ops.metric = _unstable
    assert K.run(args_for(cfg, "--max-deciding", "0"), ops) == 1          # v1.2 (TW F6): the flag stays unresolved -> nonzero
    assert len(legs_run(ops)) == 12


# ------------------------------------------------------------------------------------------------ resume (R13, R18, R19)
def test_resume_continues_where_it_stopped_and_caps_are_monotonic(world):
    ops, cfg = world
    ops.leg_script["u4-tq8-b1.a1"] = dict(driver_rc=1)
    assert K.run(args_for(cfg, "--max-replacements", "3"), ops) == 1
    import shutil
    shutil.rmtree(cfg.p475 / "legs" / "u4-tq8-b1.a1")                               # the operator archived the INVALID leg
    shutil.rmtree(cfg.dossier("u4-tq8-b1.a1"))
    assert K.run(args_for(cfg, "--max-replacements", "2"), ops) == 2                 # lowering a cap is refused
    assert K.run(args_for(cfg, "--max-replacements", "5"), ops) == 0
    names = legs_run(ops)
    assert names.count("u4-n16-b1.a1") == 1 and names.count("u4-af8-b1.a1") == 1  # VALID legs never rerun
    assert json.loads(cfg.state_path.read_text())["caps"]["max_replacements"] == 5


def test_resume_replays_the_harvest_of_a_receipt_without_its_dossier(world):
    ops, cfg = world
    name = K.leg_name("N16", 1, 1)
    K.save_state(cfg, dict(plan=dict(blocks=1, deciding_block=2)))        # the plan `run` records before its first leg (v1.2)
    K.run_leg(name, "N16", ops, cfg)
    import shutil
    shutil.rmtree(cfg.dossier(name))
    assert K.run(args_for(cfg, "--blocks", "1", "--max-deciding", "0"), ops) == 1  # one block: no complete matrix
    assert cfg.dossier(name).is_dir() and legs_run(ops).count("u4-n16-b1.a1") == 1     # replayed, never rerun


def test_metrics_come_only_from_validated_dossiers_with_one_ladder(world):
    ops, cfg = world
    assert K.run(args_for(cfg), ops) == 0
    d = cfg.dossier("u4-af4-b2.a1")
    (d / "capacity_ladder.extra.jsonl").write_text((d / f"capacity_ladder.p475-u4-af4-b2.a1.jsonl").read_text())
    rc, path = K.matrix(cfg)
    assert rc == 1 and path.name == f"MATRIX.{K.PICK}.PARTIAL.md"
    assert "AF4 b2" in path.read_text()
    (d / "capacity_ladder.extra.jsonl").unlink()
    receipt = d / "receipt.json"
    receipt.write_text(receipt.read_text().replace('"speed_valid": true', '"speed_valid": false'))
    rc, path = K.matrix(cfg)
    assert rc == 1                                                                   # the sha no longer matches its manifest


def test_matrix_cli_rc(world):
    ops, cfg = world
    assert K.main(["--workdir", str(cfg.workdir), "--repo", str(cfg.repo), "--base", BASE, "matrix"], ops=ops) == 1
    assert (cfg.results / f"MATRIX.{K.PICK}.PARTIAL.md").exists()


# ------------------------------------------------------------------------------------------------ smoke
def test_the_smoke_legs_run_n16_then_tq4_on_the_8192_rung(world):
    ops, cfg = world
    assert K.run(args_for(cfg, "--smoke"), ops) == 0
    assert legs_run(ops) == ["u4-n16-smoke.a1", "u4-tq4-smoke.a1"]                 # v1.2: both smoke legs
    sp = ops.spawned[0]["argv"]
    assert sp[sp.index("--grid") + 1] == "8192"
    r = K.read_receipt(cfg.p475 / "legs" / "u4-n16-smoke.a1")
    assert r["kv_line"]["kv_bits"] is None and r["drafter_keys"] == [dict(draft_kind="value", draft_n="value",
                                                                          draft_n_accepted="value", draft_rounds="value")]


def test_caps_and_args_are_validated():
    with pytest.raises(SystemExit):
        K.parse_args(["run", "--blocks", "0"])
    with pytest.raises(SystemExit):
        K.parse_args(["run", "--max-replacements", "-1"])
    with pytest.raises(K.P475Error):
        K.resolve_caps(dict(caps=dict(max_replacements=4, max_not_started=3, max_deciding=1, blocks=2)),
                       dict(max_replacements=4, max_not_started=2, max_deciding=1, blocks=2))
