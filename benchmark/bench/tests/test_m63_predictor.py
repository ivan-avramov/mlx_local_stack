"""M63 (C155, spec docs/specs/m63-mtp-on-tg1-arm.md): the tg1 chain runner's `--predictor mtp` arm.

The OFF arm stays byte-for-byte the C147 runner; the ON arm serves the shipped registry verbatim (MTP drafter and
verify scan kept) from its own out-root, and every draft-state check expects the arm's predictor."""
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from bench import chain_ops as co
from bench.tests.test_c147_chain_runner import CHAIN, R, chain_json, env, log_has, run   # noqa: F401  (fixture)
from bench.tests.test_chain_ops import _codes, _mut_man, _router, _worker_ps, leg_env, ops  # noqa: F401

PICK1, PICK2 = co.PICK1, co.PICK2
SHIPPED = (f"mlx_port: 8091\nmodels:\n- name: {PICK1}\n  mtp_verify_scan: joint_v1\n  draft_kind: mtp\n"
           f"  draft_model: caslca/{PICK1}-mtp-drafter\n  keep: 1\n- name: {PICK2}\n  draft_kind: mtp\n"
           f"  draft_model: caslca/{PICK2}-mtp-drafter\n")


# --------------------------------------------------------------------------- arguments / out-root
def test_predictor_defaults_off_and_accepts_mtp():
    assert R.parse_args(CHAIN).predictor == "off"
    assert R.parse_args(CHAIN + ["--predictor", "mtp"]).predictor == "mtp"
    with pytest.raises(SystemExit):
        R.parse_args(CHAIN + ["--predictor", "suffix"])


def test_out_roots_are_separate_per_predictor(tmp_path):
    on = R.parse_args(CHAIN + ["--predictor", "mtp"])
    assert R.resolve_out_root(on, tmp_path) == tmp_path / "m63"
    assert R.resolve_out_root(R.parse_args(CHAIN + ["--predictor", "mtp", "--smoke"]), tmp_path) == tmp_path / "m63-smoke"
    assert R.resolve_out_root(R.parse_args(CHAIN), tmp_path) == tmp_path / "c147"
    for wrong in ("c147", "c147-smoke"):
        with pytest.raises(SystemExit, match="REFUSED"):
            R.resolve_out_root(R.parse_args(CHAIN + ["--predictor", "mtp", "--out-root", str(tmp_path / wrong)]), tmp_path)
    for wrong in ("m63", "m63-smoke"):
        with pytest.raises(SystemExit, match="REFUSED"):
            R.resolve_out_root(R.parse_args(CHAIN + ["--out-root", str(tmp_path / wrong)]), tmp_path)


def test_schedule_legs_carry_the_predictor():
    names = R.load_universe()
    assert {x["draft_kind"] for b in R.schedule("chain", ["s1"], names, "/o") for x in b["legs"]} == {"off"}
    on = R.schedule("chain", ["s1", "s2", "reload"], names, "/o", predictor="mtp")
    assert {x["draft_kind"] for b in on for x in b["legs"]} == {"mtp"}
    off = R.schedule("chain", ["s1", "s2", "reload"], names, "/o")
    strip = lambda bs: [[{k: v for k, v in x.items() if k != "draft_kind"} for x in b["legs"]] for b in bs]  # noqa: E731
    assert strip(on) == strip(off)                       # same items, seeds and order: the arms pair


# --------------------------------------------------------------------------- overlay
def test_mtp_overlay_is_the_registry_verbatim_behind_a_header(tmp_path):
    src = tmp_path / "main_models.yaml"
    src.write_text(SHIPPED)
    dst = co.make_overlay(src, tmp_path / "m63/overlay_m63_mtp.yaml", predictor="mtp", require=(PICK1, PICK2))
    text = Path(dst).read_text()
    head, body = text.split("\n", 1)
    assert head.startswith("# M63 BENCH OVERLAY (predictor mtp)")
    assert hashlib.sha256(SHIPPED.encode()).hexdigest()[:16] in head
    assert body == SHIPPED


@pytest.mark.parametrize("drop", ["draft_kind: mtp", "draft_model"])
def test_mtp_overlay_refuses_a_pick_without_its_predictor(tmp_path, drop):
    lines = SHIPPED.splitlines()
    second = lines.index(f"- name: {PICK2}")
    lines = lines[:second] + [ln for ln in lines[second:] if drop not in ln]
    src = tmp_path / "main_models.yaml"
    src.write_text("\n".join(lines) + "\n")
    with pytest.raises(co.ChainAbort, match="predictor"):
        co.make_overlay(src, tmp_path / "ov.yaml", predictor="mtp", require=(PICK1, PICK2))


def test_off_overlay_unchanged(tmp_path):
    src = tmp_path / "r.yaml"
    src.write_text(SHIPPED)
    d = yaml.safe_load(Path(co.make_overlay(src, tmp_path / "ov.yaml")).read_text())
    assert d["models"][0] == {"name": PICK1, "keep": 1} and d["models"][1] == {"name": PICK2}


def _ops(tmp_path, overlay, predictor):
    reg = tmp_path / "main_models.yaml"
    reg.write_text(SHIPPED)
    return co.ChainOps("/repo", tmp_path, overlay, co.RunLog(tmp_path / "RUNLOG.md", out=lambda s: None),
                       registry=reg, predictor=predictor, out_root=tmp_path / "m63"), reg


def test_mtp_ensure_overlay_refuses_a_stale_overlay(tmp_path):
    o, reg = _ops(tmp_path, tmp_path / "m63/overlay_m63_mtp.yaml", "mtp")
    o.ensure_overlay()
    first = o.overlay_sha()
    o.ensure_overlay()                                    # same registry: reused
    assert o.overlay_sha() == first
    reg.write_text(SHIPPED + "# registry changed\n")
    with pytest.raises(co.ChainAbort, match="stale"):
        o.ensure_overlay()


def test_mtp_ops_keep_tmp_and_a4_logs_under_the_out_root(tmp_path):
    o, _ = _ops(tmp_path, tmp_path / "m63/ov.yaml", "mtp")
    assert o.tmpdir == tmp_path / "m63/tmp" and o.a4_log_dir == tmp_path / "m63"
    off = co.ChainOps("/repo", tmp_path, tmp_path / "ov.yaml", co.RunLog(tmp_path / "R.md", out=lambda s: None))
    assert off.tmpdir == tmp_path / "c147/tmp" and off.a4_log_dir == tmp_path / "c147"


# --------------------------------------------------------------------------- worker tripwire
@pytest.mark.parametrize("extra,ok", [("--draft-kind mtp", True), ("", False), ("--draft-kind off", False),
                                      ("--draft-kind suffix", False)])
def test_mtp_load_requires_the_mtp_worker(ops, tmp_path, extra, ok):
    ops.predictor = "mtp"
    _router(ops, tmp_path)
    ops._sh.ps = _worker_ps(PICK1, extra)
    if ok:
        assert ops.load(PICK1)["pid"] == 501
    else:
        with pytest.raises(co.ChainAbort, match="predictor"):
            ops.load(PICK1)


# --------------------------------------------------------------------------- leg validation
def test_validate_leg_expects_the_legs_predictor(leg_env):
    leg, pinned, out, fp, wd = leg_env
    assert co.validate_leg(leg, pinned, wd) == []
    assert "runtime_draft_kind" in _codes(co.validate_leg({**leg, "draft_kind": "mtp"}, pinned, wd))
    _mut_man(out, lambda m: m["runtime"].update(draft_kind="mtp"))
    assert "runtime_draft_kind" not in _codes(co.validate_leg({**leg, "draft_kind": "mtp"}, pinned, wd))
    assert "runtime_draft_kind" in _codes(co.validate_leg(leg, pinned, wd))


# --------------------------------------------------------------------------- end to end (fake probe)
def _on_env(env, served="mtp"):
    ov = Path(env["wd"]) / "served_overlay.yaml"
    ov.write_text(SHIPPED.replace("draft_kind: mtp", f"draft_kind: {served}"))
    env["ops"].extra_env["FAKE_SERVED_REGISTRY"] = str(ov)
    env["out"] = Path(env["wd"]) / "m63"
    Path(env["out"]).mkdir(parents=True, exist_ok=True)


def test_mtp_chain_runs_end_to_end_against_the_fake_probe(env):
    _on_env(env)
    assert run(env, CHAIN + ["--predictor", "mtp"]) == 0
    doc = chain_json(env)
    assert doc["predictor"] == "mtp" and doc["status"] == "finished"
    assert log_has(env, "predictor=mtp")


def test_mtp_chain_aborts_at_the_barrier_when_the_worker_serves_off(env):
    _on_env(env, served="off")
    assert run(env, CHAIN + ["--predictor", "mtp"]) == 2
    assert log_has(env, "draft_kind")


def test_off_chain_records_predictor_off(env):
    assert run(env, CHAIN) == 0
    assert chain_json(env)["predictor"] == "off"


# --------------------------------------------------------------------------- launcher
@pytest.mark.parametrize("smoke", [False, True])
def test_drive_m63_passes_the_arm_and_its_own_out_root(tmp_path, smoke):
    import os
    import subprocess
    cfg = tmp_path / "xdg/mlx_local_stack/config.sh"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(f'export STACK_WORKDIR="{tmp_path / "wd"}"\n')
    stub = tmp_path / "py"
    stub.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nexit 3\n')
    stub.chmod(0o755)
    args = ["chain", "s1", "--probe-code-sha", "9" * 64] + (["--smoke"] if smoke else [])
    r = subprocess.run([str(R.REPO / "benchmark/chains/c147/drive_m63.sh"), *args], capture_output=True, text=True,
                       env={**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "xdg"), "C147_PY": str(stub)}, timeout=30)
    d = tmp_path / "wd" / ("m63-smoke" if smoke else "m63")
    assert r.returncode == 3 and (d / "chain.rc").read_text().strip() == "3"
    argv = (d / "chain.out").read_text().splitlines()
    assert argv[0].endswith("run_tg1_chain.py") and argv[1:len(args) + 1] == args
    assert argv[-4:] == ["--predictor", "mtp", "--out-root", str(d)]
