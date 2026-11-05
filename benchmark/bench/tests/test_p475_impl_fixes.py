"""P475 stage 1 fix round (contract v1.2): one red-first test group per adopted finding (dispositions round 1)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import shutil
import signal
import subprocess
from pathlib import Path

import pytest

from bench import capacity_ladder as CL
from bench import p426_harvest
from bench import p475_kv as K
from bench.tests.test_p475_impl_support import BASE, FakeOps, base_registry, ladder_row, make_cfg

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def world(tmp_path):
    ops, cfg = FakeOps(tmp_path), make_cfg(tmp_path)
    ops.add_all(cfg)
    return ops, cfg


def leg(ops, cfg, arm="AF8", block=1, n=1):
    name = K.leg_name(arm, block, n)
    return name, K.run_leg(name, arm, ops, cfg)


def args_for(cfg, *extra, cmd="run"):
    return K.parse_args(["--workdir", str(cfg.workdir), "--repo", str(cfg.repo), "--base", BASE, cmd, *extra])


def legs_run(ops):
    return [s["argv"][s["argv"].index("--out-tag") + 1][len("p475-"):] for s in ops.spawned]


def started(ops):
    return any(c[0] == "stack" for c in ops.calls)


def resign(d):
    man = json.loads((d / "SCRUB_MANIFEST.json").read_text())
    for name in man["files"]:
        man["files"][name]["published_sha256"] = hashlib.sha256((d / name).read_bytes()).hexdigest()
    (d / "SCRUB_MANIFEST.json").write_text(json.dumps(man, indent=1, sort_keys=True) + "\n")


def edit_receipt(d, fn):
    r = json.loads((d / "receipt.json").read_text())
    fn(r)
    (d / "receipt.json").write_text(json.dumps(r, indent=1, sort_keys=True) + "\n")
    resign(d)


# ================================================================== 1. Sol P1 / TW F4: the arm's instrument == the orchestrator's
def test_the_instrument_file_list_is_the_contracts():
    assert K.INSTRUMENT_FILES == ("bench/run_capacity.py", "bench/capacity_ladder.py", "bench/kv_line.py",
                                  "bench/data/p475_decode_carrier.txt", "m1/bench_watch.py")


@pytest.mark.parametrize("rel", ["bench/run_capacity.py", "bench/capacity_ladder.py", "bench/kv_line.py",
                                 "bench/data/p475_decode_carrier.txt", "m1/bench_watch.py"])
def test_an_arm_instrument_file_differing_from_the_orchestrators_is_not_started(world, rel):
    ops, cfg = world
    p = cfg.worktree("AF8") / "benchmark" / rel
    p.write_bytes(p.read_bytes() + b"\n# drift\n")
    _, r = leg(ops, cfg)
    assert r["verdict"] == "NOT_STARTED" and not started(ops)
    assert any(rel in p and "differs" in p for p in r["problems"]), r["problems"]


@pytest.mark.parametrize("side", ["arm", "orchestrator"])
def test_a_missing_instrument_file_on_either_side_is_not_started(world, side):
    ops, cfg = world
    root = cfg.worktree("AF8") if side == "arm" else cfg.repo
    (root / "benchmark" / "m1" / "bench_watch.py").unlink()
    _, r = leg(ops, cfg)
    assert r["verdict"] == "NOT_STARTED" and not started(ops)
    assert any("m1/bench_watch.py" in p for p in r["problems"]), r["problems"]


def test_the_receipt_records_the_instrument_shas(world):
    ops, cfg = world
    _, r = leg(ops, cfg)
    assert r["verdict"] == "VALID", r["problems"]
    want = {rel: hashlib.sha256((cfg.repo / "benchmark" / rel).read_bytes()).hexdigest() for rel in K.INSTRUMENT_FILES}
    assert r["instrument"] == want


# ================================================================== 2. Sol P2: N16 = `kv_bits: 0` only, the scheme line kept
def test_n16_changes_only_kv_bits_and_keeps_the_scheme_line():
    text = base_registry()
    out = K.arm_registry_text(text, "N16")
    assert "    kv_quant_scheme: turboquant\n" in out and "    kv_bits: 0\n" in out
    assert K.registry_diff_problems(text, out, "N16") == []


def test_an_n16_commit_that_removes_the_scheme_line_is_refused():
    text = base_registry()
    removed = K.arm_registry_text(text, "N16").replace("    kv_quant_scheme: turboquant\n", "")
    assert K.registry_diff_problems(text, removed, "N16")


def _fork_gate():
    path = REPO / "src" / "mlx-vlm" / "dev" / "p369_phase2" / "registry_states.py"
    if not path.is_file():
        pytest.skip("the fork submodule is not checked out (registry_states.py absent)")
    spec = importlib.util.spec_from_file_location("p475_fork_registry_states", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("arm", ["N16", "AF8", "TQ8", "AF4", "TQ4"])
def test_every_kv_arm_registry_passes_the_forks_real_kv_arm_gate(arm):
    gate = _fork_gate()
    fixture = (REPO / "main_models.yaml").read_text()
    got = gate.classify_kv_arm(K.arm_registry_text(fixture, arm), fixture, K.PICK)
    assert got is not None, f"{arm}: the fork's --kv-arm gate refuses the arm registry"


def test_the_old_n16_shape_is_what_the_fork_gate_refuses():
    gate = _fork_gate()
    fixture = (REPO / "main_models.yaml").read_text()
    removed = K.arm_registry_text(fixture, "N16").replace("    kv_quant_scheme: turboquant\n", "", 1)
    assert removed != K.arm_registry_text(fixture, "N16")
    assert gate.classify_kv_arm(removed, fixture, K.PICK) is None


# ================================================================== 3. Sol P3: dossiers bound to the run; one usable dossier per slot
@pytest.fixture
def finished(world):
    ops, cfg = world
    assert K.run(args_for(cfg), ops) == 0
    return ops, cfg


@pytest.mark.parametrize("tamper, match", [
    (lambda r: r.update(base="c" * 40), "base"),
    (lambda r: r.update(model="Some-Other-Model"), "model"),
    (lambda r: r.update(leg="u4-af4-b1.a1"), "leg"),
    (lambda r: r.update(block=1), "block"),
    (lambda r: r["identity_entry"].update(arm_commit="d" * 40, head="d" * 40), "arm commit|identity"),
    (lambda r: r["identity_entry"].update(gitlinks={"src/mlx-vlm": "0" * 40, "src/mlx-serve": "1" * 40}), "gitlinks"),
    (lambda r: r["identity_entry"].update(base="c" * 40), "base"),
], ids=["base", "model", "leg", "block", "arm_commit", "gitlinks", "identity_base"])
def test_a_dossier_not_bound_to_this_run_makes_the_matrix_partial(finished, tamper, match):
    import re
    _, cfg = finished
    edit_receipt(cfg.dossier("u4-af8-b2.a1"), tamper)
    rc, path = K.matrix(cfg)
    assert rc == 1 and path.name.endswith(".PARTIAL.md")
    text = path.read_text()
    assert "u4-af8-b2.a1" in text and re.search(match, text), text[:2000]


def test_a_dossier_from_another_base_is_refused_even_without_state(finished):
    _, cfg = finished
    cfg.state_path.unlink()
    cfg2 = K.Config(repo=cfg.repo, workdir=cfg.workdir, base="c" * 40, expected=cfg.expected, scrub=cfg.scrub)
    rc, path = K.matrix(cfg2)
    assert rc == 1 and path.name.endswith(".PARTIAL.md")


def test_arm_commits_disagreeing_across_dossiers_are_refused(finished):
    _, cfg = finished
    edit_receipt(cfg.dossier("u4-af8-b2.a1"), lambda r: (r["identity_entry"].update(arm_commit="9" * 40, head="9" * 40),
                                                         r.update(identity_exit=dict(r["identity_entry"]))))
    cfg.state_path.unlink()                                    # no recorded identity: the cross-dossier check alone
    rc, path = K.matrix(cfg)
    assert rc == 1 and "AF8" in path.read_text() and "arm commit" in path.read_text()


def test_the_run_records_the_arm_commits_and_gitlinks(finished):
    ops, cfg = finished
    st = json.loads(cfg.state_path.read_text())
    assert st["identity"]["arm_commits"] == {a: ops.arms[a]["head"] for a in K.ARMS}
    assert st["identity"]["gitlinks"] == ops.arms["AF8"]["gitlinks"]


def test_an_arm_recommitted_mid_run_is_not_started(world):
    ops, cfg = world
    ops.leg_script["u4-af8-b1.a1"] = dict(driver_rc=1)              # stop after AF8 b1 (INVALID)
    assert K.run(args_for(cfg), ops) == 1
    shutil.rmtree(cfg.p475 / "legs" / "u4-af8-b1.a1")
    shutil.rmtree(cfg.dossier("u4-af8-b1.a1"))
    ops.arms["N16"].update(head="7" * 40, branch_tip="7" * 40)       # N16 re-prepared after its b1 leg ran
    ops.arms["AF8"]["head"] = ops.arms["AF8"]["branch_tip"]
    assert K.run(args_for(cfg), ops) == 1
    recs = [K.read_receipt(d) for d in sorted((cfg.p475 / "legs").iterdir()) if d.name.startswith("u4-n16-b2")]
    assert recs and all(r["verdict"] == "NOT_STARTED" for r in recs)
    assert any("recorded" in p for r in recs for p in r["problems"]), recs[0]["problems"]


def test_a_second_usable_dossier_for_the_same_slot_is_refused(finished):
    _, cfg = finished
    src, dup = cfg.dossier("u4-af8-b2.a1"), cfg.dossier("u4-af8-b2.a2")
    shutil.copytree(src, dup)
    old = "p475-u4-af8-b2.a1"
    (dup / f"capacity_ladder.{old}.jsonl").rename(dup / "capacity_ladder.p475-u4-af8-b2.a2.jsonl")
    (dup / f"capacity_ladder.{old}.manifest.json").rename(dup / "capacity_ladder.p475-u4-af8-b2.a2.manifest.json")
    for p in dup.iterdir():
        if p.name != "SCRUB_MANIFEST.json":
            p.write_text(p.read_text().replace("u4-af8-b2.a1", "u4-af8-b2.a2"))
    man = json.loads((dup / "SCRUB_MANIFEST.json").read_text())
    man["files"] = {k.replace(old, "p475-u4-af8-b2.a2"): v for k, v in man["files"].items()}
    (dup / "SCRUB_MANIFEST.json").write_text(json.dumps(man))
    resign(dup)
    edit_receipt(dup, lambda r: r.update(attempt=2))
    rc, path = K.matrix(cfg)
    assert rc == 1 and path.name.endswith(".PARTIAL.md")
    assert "two usable dossiers" in path.read_text() and "AF8 b2" in path.read_text()


# ================================================================== 4. Sol P4: peak memory and decode rate finite and > 0
@pytest.mark.parametrize("key", ["peak_memory_gb_cumulative", "predicted_per_second"])
@pytest.mark.parametrize("bad", [None, 0, 0.0, -1.0, math.nan, math.inf, "12.5", True])
def test_rung_problems_needs_finite_positive_peak_and_decode(key, bad):
    row = ladder_row(8192, "on", "p475-x")
    assert CL.rung_problems(row, "on") == []
    row[key] = bad
    assert any(key in p for p in CL.rung_problems(row, "on")), CL.rung_problems(row, "on")


def test_rung_problems_refuses_an_absent_peak():
    row = ladder_row(8192, "off", "p475-x")
    del row["peak_memory_gb_cumulative"]
    assert any("peak_memory_gb_cumulative" in p for p in CL.rung_problems(row, "off"))


def test_a_leg_whose_backend_omits_peak_memory_is_invalid(world):
    ops, cfg = world
    ops.row_over = dict(peak_memory_gb_cumulative=None)
    _, r = leg(ops, cfg)
    assert r["verdict"] == "INVALID" and any("peak_memory_gb_cumulative" in p for p in r["problems"])


# ================================================================== 5. Sol P5 / TW F3: the driver and router groups verified empty
def test_a_lingering_driver_child_after_a_normal_exit_is_signalled_and_verified_gone(world):
    ops, cfg = world
    ops.group_members[301] = 1                                     # the driver (pid 301) leaves a child in its group
    _, r = leg(ops, cfg)
    assert r["verdict"] == "VALID", r["problems"]
    assert (301, signal.SIGTERM) in ops.signals and ops.group_members[301] == 0
    assert ("group_alive", 301) in ops.calls


def test_a_driver_group_that_survives_sigkill_is_invalid(world):
    ops, cfg = world
    ops.group_members[301] = 1
    ops.group_ignores[301] = {signal.SIGTERM, signal.SIGKILL}
    _, r = leg(ops, cfg)
    assert r["verdict"] == "INVALID" and any("process group" in p and "301" in p for p in r["problems"])
    assert [s for _, s in ops.signals] == [signal.SIGTERM, signal.SIGKILL]


def test_an_empty_driver_group_after_a_normal_exit_is_not_signalled(world):
    ops, cfg = world
    _, r = leg(ops, cfg)
    assert r["verdict"] == "VALID" and ops.signals == []


def test_an_unreadable_group_state_is_invalid(world):
    ops, cfg = world
    ops.group_raises = True
    _, r = leg(ops, cfg)
    assert r["verdict"] == "INVALID"


def test_a_surviving_router_group_member_is_invalid(world):
    ops, cfg = world
    ops.group_members[99] = 1                                      # the router wrapper's group (pgid 99) keeps a member
    _, r = leg(ops, cfg)
    assert r["verdict"] == "INVALID"
    assert any("router process group 99" in p for p in r["problems"]), r["problems"]


def test_realops_group_alive_reads_ps_and_ignores_zombies(monkeypatch):
    from bench import chain_ops
    out = "  10    10 Ss\n  11    10 Z\n  12    12 S\n"
    monkeypatch.setattr(chain_ops, "default_sh", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, out, ""))
    ops = K.RealOps("/nonexistent-wd")
    assert ops.group_alive(12) is True and ops.group_alive(99) is False
    out = "  11    10 Z\n"
    assert ops.group_alive(10) is False


def test_realops_group_alive_refuses_a_failing_ps(monkeypatch):
    from bench import chain_ops
    monkeypatch.setattr(chain_ops, "default_sh", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "boom"))
    with pytest.raises(RuntimeError):
        K.RealOps("/nonexistent-wd").group_alive(10)


def test_the_ops_protocol_names_group_alive():
    assert hasattr(K.Ops, "group_alive")


# ================================================================== 6. Sol P6: every dossier file through p426_harvest.Gate
def test_a_foreign_email_address_in_a_ladder_row_refuses_the_harvest(world):
    ops, cfg = world
    ops.row_over = dict(note="contact someone@corp-mail.co.uk")      # allow-pii-pattern
    name, r = leg(ops, cfg)
    assert r["_harvest"] and r["_harvest"].startswith("harvest failed") and "email" in r["_harvest"]
    assert not cfg.dossier(name).exists()


def test_a_reserved_example_address_is_allowed(world):
    ops, cfg = world
    ops.row_over = dict(note="see user@example.com")
    name, r = leg(ops, cfg)
    assert r["_harvest"] == "harvested", r["_harvest"]


def test_the_operator_address_in_an_evidence_log_refuses_the_harvest(tmp_path):
    ops, cfg = FakeOps(tmp_path), make_cfg(tmp_path)
    cfg.scrub = p426_harvest.Scrub(workdir=cfg.workdir, repo=cfg.repo, home=tmp_path / "home", user="p475fakeuser",
                                   hosts=("p475fakehost",), emails=("operator@corp.invalid",))
    ops.add_all(cfg)
    log = cfg.worktree("AF8") / "logs" / "main_model.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("router up for operator@corp.invalid\n")
    name, r = leg(ops, cfg)
    assert r["_harvest"].startswith("harvest failed") and "operator_email" in r["_harvest"]
    assert not cfg.dossier(name).exists() and not cfg.evidence_stage(name).exists()


def test_a_credential_in_the_original_bytes_refuses_even_if_scrubbed_away(world):
    ops, cfg = world
    ops.row_over = dict(note="hf_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7")
    name, r = leg(ops, cfg)
    assert r["_harvest"].startswith("harvest failed")
    assert not cfg.dossier(name).exists()


# ================================================================== 7. Sol P7 / GLM F5: the block plan and the deciding block persisted
def _unstable(arm, block, ctx):
    if arm == "AF8" and ctx == 8192:
        return dict(decode=33.0 if block == 1 else 27.0)
    return {}


def test_the_block_plan_is_persisted_and_a_changed_blocks_refuses(world):
    ops, cfg = world
    ops.leg_script["u4-af8-b1.a1"] = dict(driver_rc=1)
    assert K.run(args_for(cfg), ops) == 1
    st = json.loads(cfg.state_path.read_text())
    assert st["plan"] == dict(blocks=2, deciding_block=3)
    n = len(ops.spawned)
    assert K.run(args_for(cfg, "--blocks", "3"), ops) == 2
    assert K.run(args_for(cfg, "--blocks", "1"), ops) == 2
    assert len(ops.spawned) == n


def test_no_plan_is_recorded_before_any_leg(world):
    ops, cfg = world
    for a in K.ARMS:
        cfg.preflight_record(a).unlink()
        ops.qualify[a] = ["FAILED"]
    assert K.run(args_for(cfg, "--max-preflight", "0"), ops) == 1
    assert "plan" not in json.loads(cfg.state_path.read_text())
    assert K.run(args_for(cfg, "--blocks", "3", "--max-preflight", "0"), ops) == 1     # no leg exists: not refused (rc 2)


def test_legs_without_a_recorded_plan_refuse(world):
    ops, cfg = world
    ops.leg_script["u4-af8-b1.a1"] = dict(driver_rc=1)
    K.run(args_for(cfg), ops)
    st = json.loads(cfg.state_path.read_text())
    del st["plan"]
    cfg.state_path.write_text(json.dumps(st))
    assert K.run(args_for(cfg), ops) == 2


def test_a_completed_deciding_block_is_not_re_entered(world, capsys):
    ops, cfg = world
    ops.metric = _unstable
    assert K.run(args_for(cfg), ops) == 0
    st = json.loads(cfg.state_path.read_text())
    assert st["deciding"] == dict(block=3, started=True, complete=True)
    capsys.readouterr()
    assert K.run(args_for(cfg), ops) == 0
    assert "deciding block" not in capsys.readouterr().out
    assert len(ops.spawned) == 18


def test_the_matrix_cli_reads_the_recorded_block_plan(world):
    ops, cfg = world
    ops.metric = _unstable
    assert K.run(args_for(cfg), ops) == 0
    assert K.main(["--workdir", str(cfg.workdir), "--repo", str(cfg.repo), "--base", BASE, "matrix"], ops=ops) == 0
    assert "b3 (deciding)" in (cfg.results / f"MATRIX.{K.PICK}.md").read_text()


# ================================================================== 8. Sol P8: exactly one of canonical / PARTIAL
def test_complete_then_partial_removes_the_canonical(finished):
    _, cfg = finished
    canon, part = cfg.results / f"MATRIX.{K.PICK}.md", cfg.results / f"MATRIX.{K.PICK}.PARTIAL.md"
    assert canon.is_file() and not part.exists()
    shutil.rmtree(cfg.dossier("u4-tq8-b2.a1"))
    assert K.matrix(cfg)[0] == 1
    assert part.is_file() and not canon.exists()


def test_partial_then_complete_removes_the_partial(finished):
    _, cfg = finished
    canon, part = cfg.results / f"MATRIX.{K.PICK}.md", cfg.results / f"MATRIX.{K.PICK}.PARTIAL.md"
    keep = cfg.dossier("u4-tq8-b2.a1").with_name("keep")
    shutil.move(cfg.dossier("u4-tq8-b2.a1"), keep)
    assert K.matrix(cfg)[0] == 1 and part.is_file() and not canon.exists()
    shutil.move(keep, cfg.dossier("u4-tq8-b2.a1"))
    assert K.matrix(cfg)[0] == 0 and canon.is_file() and not part.exists()


# ================================================================== 9. TW F1: an INVALID smoke leg stops the run, also on resume
def test_an_invalid_smoke_leg_stops_on_resume(world):
    ops, cfg = world
    ops.row_over = dict(finish_reason="stop")
    assert K.run(args_for(cfg, "--smoke"), ops) == 1
    assert legs_run(ops) == ["u4-n16-smoke.a1"]
    ops.row_over = {}
    assert K.run(args_for(cfg, "--smoke"), ops) == 1
    assert legs_run(ops) == ["u4-n16-smoke.a1"]


def test_an_invalid_tq4_smoke_leg_stops_on_resume(world):
    ops, cfg = world
    ops.leg_script["u4-tq4-smoke.a1"] = dict(driver_rc=1)
    assert K.run(args_for(cfg, "--smoke"), ops) == 1
    assert K.run(args_for(cfg, "--smoke"), ops) == 1
    assert legs_run(ops) == ["u4-n16-smoke.a1", "u4-tq4-smoke.a1"]


# ================================================================== 10. TW F2: evidence-stage/<leg> is a destination, never overwritten
def test_an_existing_evidence_stage_is_a_destination(world):
    ops, cfg = world
    name = K.leg_name("AF8", 1, 1)
    cfg.evidence_stage(name).mkdir(parents=True)
    _, r = leg(ops, cfg)
    assert r["verdict"] == "NOT_STARTED" and not started(ops)
    assert any("evidence-stage" in p for p in r["problems"])


def test_a_harvest_replay_never_overwrites_differing_evidence(world):
    ops, cfg = world
    name, r = leg(ops, cfg)
    assert r["_harvest"] == "harvested"
    ev = cfg.evidence_stage(name)
    target = next(ev.iterdir())
    target.write_bytes(b"someone else's bytes\n")
    shutil.rmtree(cfg.dossier(name))
    with pytest.raises(K.P475Error, match="evidence"):
        K.harvest(name, ops, cfg)
    assert target.read_bytes() == b"someone else's bytes\n" and not cfg.dossier(name).exists()


def test_a_harvest_replay_accepts_byte_identical_evidence(world):
    ops, cfg = world
    name, r = leg(ops, cfg)
    before = {p.name: p.read_bytes() for p in cfg.evidence_stage(name).iterdir()}
    shutil.rmtree(cfg.dossier(name))                               # a crash after the evidence write, before the rename
    assert K.harvest(name, ops, cfg) == "harvested"
    assert {p.name: p.read_bytes() for p in cfg.evidence_stage(name).iterdir()} == before


# ================================================================== 11. TW F6: an unresolved instability flag exits nonzero, labelled
def test_an_unresolved_instability_under_a_zero_cap_exits_nonzero_and_is_labelled(world):
    ops, cfg = world
    ops.metric = _unstable
    assert K.run(args_for(cfg, "--max-deciding", "0"), ops) == 1
    assert len(legs_run(ops)) == 12
    text = (cfg.results / f"MATRIX.{K.PICK}.md").read_text()
    assert "UNRESOLVED" in text
    row = next(ln for ln in text.splitlines() if ln.startswith("| AF8 | 8192 |") and "REVERSAL" in ln)
    assert "UNRESOLVED" in row


def test_a_resolved_flag_is_not_labelled_unresolved(world):
    ops, cfg = world
    ops.metric = _unstable
    assert K.run(args_for(cfg), ops) == 0
    assert "UNRESOLVED" not in (cfg.results / f"MATRIX.{K.PICK}.md").read_text()


# ================================================================== P651 / C293 (GLM F7): the watcher reads the leg's own rows file
def _watch_rows_problems(r):
    return [p for p in r["speed_problems"] if "--capacity-rows" in p]


def test_the_receipt_carries_the_watcher_argv_and_a_matching_rows_path_is_no_problem(world):
    ops, cfg = world
    name, r = leg(ops, cfg)
    assert r["verdict"] == "VALID" and r["speed_valid"] is True, (r["problems"], r["speed_problems"])
    started_argv = next(c[1] for c in ops.calls if c[0] == "start_watch")
    assert r["watcher_argv"] == started_argv
    rows = str(cfg.capacity_outputs("AF8", name)["rows"])
    assert started_argv[started_argv.index("--capacity-rows") + 1] == rows
    assert _watch_rows_problems(r) == []
    on_disk = json.loads(cfg.receipt_path(name).read_text())
    assert on_disk["watcher_argv"] == started_argv


@pytest.mark.parametrize("swap", [
    lambda argv: [("/elsewhere/capacity_ladder.p475-u4-af8-b1.a0.jsonl" if i and argv[i - 1] == "--capacity-rows" else t)
                  for i, t in enumerate(argv)],
    lambda argv: [t for i, t in enumerate(argv) if t != "--capacity-rows" and not (i and argv[i - 1] == "--capacity-rows")],
], ids=["other_rows_file", "no_capacity_rows"])
def test_a_watcher_on_another_rows_file_is_speed_invalid(world, monkeypatch, swap):
    ops, cfg = world
    real = K.watch_argv
    monkeypatch.setattr(K, "watch_argv", lambda *a, **kw: swap(real(*a, **kw)))
    name, r = leg(ops, cfg)
    assert r["verdict"] == "VALID" and r["speed_valid"] is False                    # a speed problem (R11), never INVALID
    assert _watch_rows_problems(r), r["speed_problems"]
    assert r["watcher_argv"] == next(c[1] for c in ops.calls if c[0] == "start_watch")


def test_a_watcher_on_another_rows_file_is_replaced(world, monkeypatch):
    ops, cfg = world
    real = K.watch_argv

    def argv(arm, leg_, *a, **kw):
        out = real(arm, leg_, *a, **kw)
        if leg_ == "u4-af8-b1.a1":
            out[out.index("--capacity-rows") + 1] = "/elsewhere/rows.jsonl"
        return out
    monkeypatch.setattr(K, "watch_argv", argv)
    assert K.run(args_for(cfg), ops) == 0
    assert "u4-af8-b1.a2" in legs_run(ops)


# ================================================================== 12. smoke: N16 then TQ4, recording env / telemetry / drafter keys
def test_the_smoke_run_is_n16_then_tq4_on_the_8192_grid(world):
    ops, cfg = world
    assert K.run(args_for(cfg, "--smoke"), ops) == 0
    assert legs_run(ops) == ["u4-n16-smoke.a1", "u4-tq4-smoke.a1"]
    for s in ops.spawned:
        assert s["argv"][s["argv"].index("--grid") + 1] == "8192"
    assert not list(cfg.results.glob("MATRIX*"))


def test_the_smoke_leg_names_carry_the_arm():
    assert K.leg_name("TQ4", "smoke", 2) == "u4-tq4-smoke.a2"
    assert K.parse_leg("u4-tq4-smoke.a2") == dict(arm="TQ4", block="smoke", attempt=2)


def test_each_smoke_receipt_records_worker_env_telemetry_and_drafter_keys(world):
    ops, cfg = world
    ops.worker_env = {"PATH": "/usr/bin", "MLX_SERVE_CONFIG": "x", "HF_TOKEN": "hf_secretvalue"}
    assert K.run(args_for(cfg, "--smoke"), ops) == 0
    for arm in ("n16", "tq4"):
        r = K.read_receipt(cfg.p475 / "legs" / f"u4-{arm}-smoke.a1")
        env = r["worker_env"]
        assert env["names"] == ["HF_TOKEN", "MLX_SERVE_CONFIG", "PATH"] and env["kv_tq"] == {}
        assert "hf_secretvalue" not in json.dumps(r)                     # names only, never values
        (t,) = r["telemetry"]
        assert t["ctx"] == 8192 and t["prompt_n"] == t["prompt_tokens"] and t["prompt_n_equals_prompt_tokens"] is True
        assert t["prompt_per_second_derived"] == pytest.approx(t["prompt_n"] / (t["prompt_ms"] / 1000))
        assert t["prompt_per_second_rel_diff"] == pytest.approx(0.0, abs=1e-9)
        assert r["drafter_keys"] == [dict(draft_kind="value", draft_n="value", draft_n_accepted="value", draft_rounds="value")]


def test_the_worker_env_record_keeps_kv_values_for_the_d1_question(world):
    ops, cfg = world
    ops.worker_env = {"PATH": "/usr/bin", "KV_BITS": "4"}
    name, r = leg(ops, cfg, "TQ4", "smoke")
    assert r["verdict"] == "INVALID"                                      # the R2 check is unchanged
    assert r["worker_env"]["kv_tq"] == {"KV_BITS": "4"}
