"""M63 (C155, spec docs/specs/m63-mtp-on-tg1-arm.md): the tg1 chain runner's `--predictor mtp` arm.

The OFF arm stays byte-for-byte the C147 runner; the ON arm serves the shipped registry verbatim (MTP drafter and
verify scan kept) from its own out-root, and every draft-state check expects the arm's predictor."""
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from bench import chain_ops as co
from bench.tests.test_c147_chain_runner import (  # noqa: F401  (fixture)
    CHAIN, R, chain_json, env, log_has, pinned_off_registry, run)
from bench.tests.test_chain_ops import _codes, _mut_man, _router, _worker_ps, leg_env, ops  # noqa: F401

PICK1, PICK2 = co.PICK1, co.PICK2
SHIPPED = (f"mlx_port: 8091\nmodels:\n- name: {PICK1}\n  hf_path: caslca/{PICK1}\n  type: vision\n"
           f"  mtp_verify_scan: joint_v1\n  draft_kind: mtp\n"
           f"  draft_model: caslca/{PICK1}-mtp-drafter\n  keep: 1\n- name: {PICK2}\n  hf_path: caslca/{PICK2}\n"
           f"  type: vision\n  draft_kind: mtp\n  draft_model: caslca/{PICK2}-mtp-drafter\n")


def _committed_mtp_registry(path):
    """C221: an arm worktree's committed registry: both entries carry all three C177 keys (SHIPPED's second entry predates
    the verify-scan key)."""
    path.write_text(SHIPPED.replace(f"  type: vision\n  draft_kind: mtp\n  draft_model: caslca/{PICK2}-mtp-drafter\n",
                                    f"  type: vision\n  mtp_verify_scan: joint_v1\n  draft_kind: mtp\n"
                                    f"  draft_model: caslca/{PICK2}-mtp-drafter\n"))
    return path


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
    pair = [PICK1, PICK2]
    assert {x["draft_kind"] for b in R.schedule("chain", ["s1"], names, "/o", models=pair) for x in b["legs"]} == {"off"}
    on = R.schedule("chain", ["s1", "s2", "reload"], names, "/o", models=pair, predictor="mtp")
    assert {x["draft_kind"] for b in on for x in b["legs"]} == {"mtp"}
    off = R.schedule("chain", ["s1", "s2", "reload"], names, "/o", models=pair)
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
    assert d["models"][0] == {"name": PICK1, "hf_path": f"caslca/{PICK1}", "type": "vision", "keep": 1}
    assert d["models"][1] == {"name": PICK2, "hf_path": f"caslca/{PICK2}", "type": "vision"}


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
@pytest.mark.parametrize("extra,why", [("", "predictor"), ("--draft-kind off", "predictor"),
                                      ("--draft-kind suffix", "predictor"),
                                      ("--draft-kind mtp", "draft-model")])     # M4: the kind alone is not enough
def test_mtp_load_requires_the_mtp_worker(ops, tmp_path, extra, why):
    _mtp_ops(ops, tmp_path)
    ops._sh.ps = _worker_ps(PICK1, extra)
    with pytest.raises(co.ChainAbort, match=why):
        ops.load(PICK1)


def test_mtp_load_with_an_unreadable_overlay_is_a_chain_abort(ops, tmp_path):
    _mtp_ops(ops, tmp_path)
    ops._sh.ps = _worker_ps(PICK1, SHIPPED_FLAGS[PICK1])
    Path(ops.overlay).unlink()
    with pytest.raises(co.ChainAbort, match="overlay"):
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
    ov = Path(env["wd"]) / "served_overlay.yaml"                  # what the (fake) worker reports serving
    ov.write_text(SHIPPED.replace("draft_kind: mtp", f"draft_kind: {served}"))
    env["ops"].extra_env["FAKE_SERVED_REGISTRY"] = str(ov)
    env["registry"] = _committed_mtp_registry(Path(env["wd"]) / "committed_main_models.yaml")   # C221: what `--predictor mtp` asserts
    env["out"] = Path(env["wd"]) / "m63"
    Path(env["out"]).mkdir(parents=True, exist_ok=True)


def test_mtp_chain_runs_end_to_end_against_the_fake_probe(env):
    _on_env(env)
    assert run(env, CHAIN + ["--predictor", "mtp"], registry=env["registry"]) == 0
    doc = chain_json(env)
    assert doc["predictor"] == "mtp" and doc["status"] == "finished"
    assert log_has(env, "predictor=mtp")


def test_mtp_chain_aborts_at_the_barrier_when_the_worker_serves_off(env):
    _on_env(env, served="off")
    assert run(env, CHAIN + ["--predictor", "mtp"], registry=env["registry"]) == 2
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


# --------------------------------------------------------------------------- review round 1 (M1-M3)
def test_m1_reused_overlay_with_a_tampered_body_is_refused(tmp_path):
    o, reg = _ops(tmp_path, tmp_path / "m63/overlay_m63_mtp.yaml", "mtp")
    o.ensure_overlay()
    path = Path(o.overlay)
    head, body = path.read_text().split("\n", 1)
    path.write_text(head + "\n" + body.replace("draft_kind: mtp", "draft_kind: suffix", 1))
    with pytest.raises(co.ChainAbort, match="stale"):
        o.ensure_overlay()


def test_m1_reused_overlay_of_a_registry_without_the_predictor_is_refused(tmp_path):
    o, reg = _ops(tmp_path, tmp_path / "m63/overlay_m63_mtp.yaml", "mtp")
    bad = SHIPPED.replace(f"  draft_model: caslca/{PICK2}-mtp-drafter\n", "")
    reg.write_text(bad)
    Path(o.overlay).parent.mkdir(parents=True)
    Path(o.overlay).write_text(co.overlay_header("mtp", bad) + bad)     # a well-formed overlay of an invalid registry
    with pytest.raises(co.ChainAbort, match="predictor"):
        o.ensure_overlay()


@pytest.mark.parametrize("predictor,rel", [("mtp", "c147/m63"), ("mtp", "c147-smoke/x"), ("off", "m63/c147"),
                                           ("off", "m63-smoke/deep/x")])
def test_m2_nested_roots_inside_the_other_arm_are_refused(tmp_path, predictor, rel):
    a = R.parse_args(CHAIN + ["--predictor", predictor, "--out-root", str(tmp_path / rel)])
    with pytest.raises(SystemExit, match="REFUSED"):
        R.resolve_out_root(a, tmp_path)


def test_m2_symlinked_root_into_the_other_arm_is_refused(tmp_path):
    (tmp_path / "c147").mkdir()
    (tmp_path / "elsewhere").symlink_to(tmp_path / "c147")
    a = R.parse_args(CHAIN + ["--predictor", "mtp", "--out-root", str(tmp_path / "elsewhere/run")])
    with pytest.raises(SystemExit, match="REFUSED"):
        R.resolve_out_root(a, tmp_path)


@pytest.mark.parametrize("predictor,rel", [("mtp", "c147/overlay_c147_draft_off.yaml"), ("off", "m63/overlay_m63_mtp.yaml")])
def test_m2_overlay_override_inside_the_other_arm_is_refused(tmp_path, monkeypatch, predictor, rel):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    monkeypatch.setenv("C147_OVERLAY", str(tmp_path / rel))
    built = []
    monkeypatch.setattr(R.co, "ChainOps", lambda *a, **k: built.append((a, k)) or pytest.fail("ChainOps built"))
    with pytest.raises(SystemExit, match="REFUSED"):
        R.main(CHAIN + ["--predictor", predictor])
    assert not built


def test_m3_production_wiring_selects_the_mtp_overlay_out_root_and_child_env(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    monkeypatch.delenv("C147_OVERLAY", raising=False)
    served = tmp_path / "arm/main_models.yaml"                       # an arm worktree's registry that ships the MTP entries
    served.parent.mkdir()
    _committed_mtp_registry(served)
    built = {}
    real = co.ChainOps

    class Stop(Exception):
        pass

    def capture(*a, **k):
        built["ops"] = real(*a, **k)
        raise Stop

    monkeypatch.setattr(R.co, "ChainOps", capture)
    with pytest.raises(Stop):
        R.main(CHAIN + ["--predictor", "mtp"], registry=served)
    o = built["ops"]
    # C221: no overlay file; the served (committed) registry itself is the router's config
    assert o.predictor == "mtp" and o.overlay == str(served)
    assert o.a4_log_dir == tmp_path / "m63" and o.tmpdir == tmp_path / "m63/tmp"
    env = o.env_base()                                   # what every probe child and the router inherit (M50/C35)
    assert env["MLX_SERVE_CONFIG"] == o.overlay and env["TMPDIR"] == str(tmp_path / "m63/tmp")


def test_m3_production_wiring_off_is_the_c147_layout(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    monkeypatch.delenv("C147_OVERLAY", raising=False)
    built = {}
    real = co.ChainOps

    class Stop(Exception):
        pass

    def capture(*a, **k):
        built["ops"] = real(*a, **k)
        raise Stop

    monkeypatch.setattr(R.co, "ChainOps", capture)
    with pytest.raises(Stop):
        R.main(CHAIN, registry=pinned_off_registry())
    o = built["ops"]
    # C221: the served registry (the pinned OFF copy, standing for the committed OFF state) is served verbatim; no overlay is generated
    assert o.predictor == "off" and o.overlay == str(pinned_off_registry())
    assert o.tmpdir == tmp_path / "c147/tmp" and o.env_base()["MLX_SERVE_CONFIG"] == o.overlay


# --------------------------------------------------------------------------- review round 2 (M4-M6)
def _mtp_ops(ops, tmp_path):
    """The chain_ops `ops` fixture switched to the ON arm, serving an overlay that is the shipped registry."""
    ov = tmp_path / "served.yaml"
    ov.write_text(SHIPPED)
    ops.predictor, ops.overlay = "mtp", str(ov)
    ops._sh.env = f"/usr/bin/mlx-serve start MLX_SERVE_CONFIG={ov} MLX_VLM_CACHE_SESSION_MAX=1 HOME=/x"
    _router(ops, tmp_path)
    return ops


SHIPPED_FLAGS = {PICK1: f"--mtp-verify-scan joint_v1 --draft-kind mtp --draft-model caslca/{PICK1}-mtp-drafter",
                 PICK2: f"--draft-kind mtp --draft-model caslca/{PICK2}-mtp-drafter"}


@pytest.mark.parametrize("model", [PICK1, PICK2])
def test_m4_mtp_load_accepts_exactly_the_shipped_predictor_flags(ops, tmp_path, model):
    _mtp_ops(ops, tmp_path)
    ops._sh.ps = _worker_ps(model, SHIPPED_FLAGS[model])
    assert ops.load(model)["pid"] == 501


@pytest.mark.parametrize("model,flags,why", [
    (PICK1, "--mtp-verify-scan joint_v1 --draft-kind mtp", "draft-model"),                           # sidecar missing
    (PICK1, f"--mtp-verify-scan joint_v1 --draft-kind mtp --draft-model caslca/{PICK2}-mtp-drafter", "draft-model"),
    (PICK1, f"--draft-kind mtp --draft-model caslca/{PICK1}-mtp-drafter", "mtp-verify-scan"),       # scan missing
    (PICK1, f"--mtp-verify-scan per_query --draft-kind mtp --draft-model caslca/{PICK1}-mtp-drafter", "mtp-verify-scan"),
    (PICK2, f"--mtp-verify-scan joint_v1 --draft-kind mtp --draft-model caslca/{PICK2}-mtp-drafter", "mtp-verify-scan"),
])
def test_m4_mtp_load_refuses_a_worker_that_is_not_the_shipped_predictor(ops, tmp_path, model, flags, why):
    _mtp_ops(ops, tmp_path)
    ops._sh.ps = _worker_ps(model, flags)
    with pytest.raises(co.ChainAbort, match=why):
        ops.load(model)


@pytest.mark.parametrize("flags,ok", [
    (f"--mtp-verify-scan=joint_v1 --draft-kind=mtp --draft-model=caslca/{PICK1}-mtp-drafter", True),   # = form
    (f"--draft-kind off {SHIPPED_FLAGS[PICK1]}", False),                       # duplicated flag, either order
    (f"{SHIPPED_FLAGS[PICK1]} --draft-kind off", False),
    (f"{SHIPPED_FLAGS[PICK1]} --draft-kind=mtp", False),
])
def test_m5_flags_parse_both_forms_and_refuse_duplicates(ops, tmp_path, flags, ok):
    _mtp_ops(ops, tmp_path)
    ops._sh.ps = _worker_ps(PICK1, flags)
    if ok:
        assert ops.load(PICK1)["pid"] == 501
    else:
        with pytest.raises(co.ChainAbort, match="duplicate|predictor"):
            ops.load(PICK1)


@pytest.mark.parametrize("flags", ["--draft-kind=mtp", "--draft-kind off --draft-kind mtp", "--draft-kind none --draft-kind none"])
def test_m5_off_tripwire_sees_equals_form_and_duplicates(ops, tmp_path, flags):
    _router(ops, tmp_path)
    ops._sh.ps = _worker_ps(PICK1, flags)
    with pytest.raises(co.ChainAbort, match="predictor|duplicate"):
        ops.load(PICK1)


@pytest.mark.parametrize("predictor,rel", [("mtp", "c147/overlay_c147_draft_off.yaml"), ("off", "m63/overlay_m63_mtp.yaml")])
def test_m6_overlay_refusal_happens_before_any_filesystem_write_and_exits_2(tmp_path, monkeypatch, predictor, rel):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    monkeypatch.setenv("C147_OVERLAY", str(tmp_path / rel))
    with pytest.raises(SystemExit) as ei:
        R.main(CHAIN + ["--predictor", predictor])
    assert ei.value.code == 2 and "REFUSED" in str(ei.value)
    assert not (tmp_path / ("m63" if predictor == "mtp" else "c147")).exists()


@pytest.mark.parametrize("argv", [CHAIN + ["--predictor", "mtp", "--out-root", "{wd}/c147/x"],
                                  CHAIN + ["--smoke", "--out-root", "{wd}/c147"]])
def test_m6_out_root_refusals_exit_2(tmp_path, monkeypatch, argv):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    with pytest.raises(SystemExit) as ei:
        R.main([a.replace("{wd}", str(tmp_path)) for a in argv])
    assert ei.value.code == 2


# --------------------------------------------------------------------------- review round 3 (M7-M8)
def _wrong_main_ps(main_model, drafter_of, flags_of):
    flags = SHIPPED_FLAGS[flags_of]
    return (f"501 /py -m mlx_vlm.server --model caslca/{main_model} --port 8091 {flags}\n"
            f"77 uv run mlx_vlm.server {drafter_of}\n")


@pytest.mark.parametrize("want", [PICK1, PICK2])
def test_m7_a_worker_with_other_weights_but_the_expected_drafter_is_refused(ops, tmp_path, want):
    _mtp_ops(ops, tmp_path)
    ops._sh.ps = _wrong_main_ps("Some-Other-27B", want, want)
    with pytest.raises(co.ChainAbort, match="found 0|--model"):
        ops.load(want)


def test_m7_duplicate_model_flag_is_refused(ops, tmp_path):
    _mtp_ops(ops, tmp_path)
    ops._sh.ps = _worker_ps(PICK1, f"--model caslca/Some-Other-27B {SHIPPED_FLAGS[PICK1]}")
    with pytest.raises(co.ChainAbort, match="--model"):
        ops.load(PICK1)


def test_m7_off_worker_selection_matches_the_model_flag_not_a_substring(ops, tmp_path):
    _router(ops, tmp_path)
    ops._sh.ps = f"501 /py -m mlx_vlm.server --model caslca/Some-Other-27B --port 8091 --note {PICK1}\n"
    with pytest.raises(co.ChainAbort, match="found 0"):
        ops.load(PICK1)
    assert ops.worker_ident(PICK1) is None


def test_m7_mtp_main_model_must_equal_the_registry_hf_path(ops, tmp_path):
    _mtp_ops(ops, tmp_path)
    ops._sh.ps = f"501 /py -m mlx_vlm.server --model elsewhere/{PICK1} --port 8091 {SHIPPED_FLAGS[PICK1]}\n"
    with pytest.raises(co.ChainAbort, match="--model"):
        ops.load(PICK1)


@pytest.mark.parametrize("extra", ["--mtp-verify-ab", "--draft-block-size 4", "--suffix-min-match 2",
                                   "--draft-cooldown 2"])
def test_m8_unshipped_predictor_flags_are_refused(ops, tmp_path, extra):
    _mtp_ops(ops, tmp_path)
    ops._sh.ps = _worker_ps(PICK1, f"{SHIPPED_FLAGS[PICK1]} {extra}")
    with pytest.raises(co.ChainAbort, match=extra.split()[0]):
        ops.load(PICK1)


def test_m8_flags_the_registry_sets_are_required(ops, tmp_path):
    _mtp_ops(ops, tmp_path)
    Path(ops.overlay).write_text(SHIPPED.replace("  mtp_verify_scan: joint_v1\n",
                                                 "  mtp_verify_scan: joint_v1\n  mtp_verify_ab: true\n  draft_block_size: 3\n"))
    ops._sh.ps = _worker_ps(PICK1, SHIPPED_FLAGS[PICK1])
    with pytest.raises(co.ChainAbort, match="--mtp-verify-ab|--draft-block-size"):
        ops.load(PICK1)
    ops._sh.ps = _worker_ps(PICK1, f"{SHIPPED_FLAGS[PICK1]} --mtp-verify-ab --draft-block-size 3")
    assert ops.load(PICK1)["pid"] == 501
