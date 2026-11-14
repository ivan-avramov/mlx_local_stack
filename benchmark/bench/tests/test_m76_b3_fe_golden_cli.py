"""M76 B3: `lever=mtp` byte-identical golden (acceptance 2) and the `--lever` CLI surface / signals under `kv` (acceptance 1).
Class of each test is in the comment above it: (a) reproduces a failure the spec fixes, (b) preserves an invariant, (c) new behaviour.

The golden `fixtures/m76_b3_fe/golden_mtp_surface.json` is `test_m76_b3_fe_surface.surface()` run on the BASELINE (plans, argv, leg
names, build pins, registry-delta and worker-argv verdicts of today's P426 tooling for builds `s` and `s2`); the signals golden is
the committed `benchmark/results/p426/SIGNALS.{md,json}` regenerated from the committed P426 evidence.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bench.tests import test_m76_b3_fe_surface as G

BENCH = G.REPO / "benchmark"
P426 = BENCH / "results" / "p426"
EVIDENCE_REF = "b6ec7819"
GOLDEN = G.FIX / "golden_mtp_surface.json"
LEVER_MODULES = ["bench.p426_wave1", "bench.p426_wave2", "bench.p426_leg", "bench.p426_verify", "bench.p426_signals",
                 "bench.p426_panel"]


def cli(module, args, tmp_path=None):
    env = {"PYTHONPATH": str(BENCH), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(tmp_path or BENCH),
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "MLX_BENCH_RESULTS": str(BENCH / "results")}
    return subprocess.run([sys.executable, "-m", module, *map(str, args)], cwd=BENCH, capture_output=True, text=True, timeout=1800,
                          env=env)


# ------------------------------------------------------------------------------------------------ golden
# (b) today's plans, argv, names, pins and verdicts, key by key (a failure names the key)
@pytest.mark.parametrize("key", sorted(k for k in json.loads(GOLDEN.read_text()) if k != "expected_builds"))
def test_mtp_surface_is_byte_identical_to_the_baseline(key):
    want = json.loads(GOLDEN.read_text())[key]
    got = json.loads(json.dumps(G.surface()[key], sort_keys=True, default=str))
    assert got == want


# (b) AMENDED (delivery 3: the spec adds `s3`): `s2` is byte-identical to the baseline's, `s` has no expected build
def test_expected_builds_s2_byte_identical_and_s_absent():
    want = json.loads(GOLDEN.read_text())["expected_builds"]
    got = json.loads(json.dumps(G.surface()["expected_builds"], sort_keys=True))
    assert got["s2"] == want["s2"]
    assert "s" not in got


# (b) the explicit `lever="mtp"` equals the default on every function that takes it (no drift between spelling the default and not)
def test_explicit_mtp_lever_equals_the_default():
    from bench import p426_leg, p426_plan, p426_wave1

    for b in ("s", "s2"):
        for axis in G.AXES:
            for arm in ("off", "on"):
                for sel in ("smoke", 1, 2):
                    assert p426_plan.leg_name(axis, arm, sel, b, lever="mtp") == p426_plan.leg_name(axis, arm, sel, b)
                    a = p426_wave1.leg_argv("/WT", "/WD", "/R", "/RC", axis, arm, sel, b, stack_root_off="/O", lever="mtp")
                    assert a == p426_wave1.leg_argv("/WT", "/WD", "/R", "/RC", axis, arm, sel, b, stack_root_off="/O")
    assert p426_leg.registry_delta_problems(G.text("x"), G.text("xo"), G.ENTRY, lever="mtp") == \
        p426_leg.registry_delta_problems(G.text("x"), G.text("xo"), G.ENTRY)


# (b) the Wave 1 schedule under mtp is today's: 5 axes (no longctx), 10 smokes + 20 legs per... (golden `schedule_default`)
def test_mtp_schedule_has_no_longctx():
    from bench import p426_wave1

    assert "longctx" not in p426_wave1.AXES
    assert [leg[0] for leg in p426_wave1.schedule()].count("longctx") == 0


# (b) the regenerated SIGNALS.md / SIGNALS.json equal the committed ones, byte for byte (evidence commit b6ec7819 must be present)
@pytest.fixture(scope="module")
def regenerated(tmp_path_factory):
    probe = subprocess.run(["git", "-C", str(G.REPO), "cat-file", "-e", f"{EVIDENCE_REF}^{{commit}}"], capture_output=True)
    if probe.returncode:
        pytest.skip(f"evidence commit {EVIDENCE_REF} is not in this checkout")
    out = tmp_path_factory.mktemp("signals")
    args = ["all", "--results-root", P426, "--rows-root", BENCH / "results", "--b8", P426 / "B8.json", "--out-md", out / "SIGNALS.md",
            "--out-json", out / "SIGNALS.json", "--panel", P426 / "panel", "--evidence-ref", EVIDENCE_REF]
    return out, args


def test_signals_regenerate_byte_identical_to_the_committed_p426_sheet(regenerated):
    out, args = regenerated
    proc = cli("bench.p426_signals", args, out)
    assert proc.returncode == 0, proc.stderr[-1200:]
    for name in ("SIGNALS.md", "SIGNALS.json"):
        assert (out / name).read_bytes() == (P426 / name).read_bytes(), name


# (b) ... and with the lever spelt out
def test_signals_with_lever_mtp_spelt_out_are_identical(regenerated, tmp_path):
    _, args = regenerated
    args = [a if a not in ("--out-md", "--out-json") else a for a in args]
    md, js = tmp_path / "SIGNALS.md", tmp_path / "SIGNALS.json"
    args[args.index("--out-md") + 1], args[args.index("--out-json") + 1] = md, js
    for placement in (["--lever", "mtp", *args], [*args, "--lever", "mtp"]):
        proc = cli("bench.p426_signals", placement, tmp_path)
        if proc.returncode == 0:
            break
    assert proc.returncode == 0, proc.stderr[-1200:]
    for name in ("SIGNALS.md", "SIGNALS.json"):
        assert (tmp_path / name).read_bytes() == (P426 / name).read_bytes(), name


# ------------------------------------------------------------------------------------------------ the --lever CLI
# (c) every tool named in the spec accepts `--lever` with the choices mtp and kv (top level or on its subcommands)
@pytest.mark.parametrize("module", ["bench.p426_verify", "bench.p426_panel"])   # AMENDED: the spec's top-level surface only
def test_lever_flag_exists_with_mtp_and_kv(module):
    text = cli(module, ["--help"]).stdout
    assert "--lever" in text, module
    assert "mtp" in text and "kv" in text


# (c) the tg1 chain's P426 mode accepts it too
def test_tg1_chain_accepts_lever():
    proc = subprocess.run([sys.executable, str(BENCH / "chains" / "c147" / "run_tg1_chain.py"), "--help"], capture_output=True,
                          text=True, cwd=BENCH, env={"PYTHONPATH": str(BENCH), "PATH": "/usr/bin:/bin", "HOME": str(BENCH)})
    assert "--lever" in proc.stdout + proc.stderr


# (c) an unknown lever value is refused at parse time (argparse exit 2), never defaulted
@pytest.mark.parametrize("module", ["bench.p426_wave1", "bench.p426_leg", "bench.p426_verify"])
def test_unknown_lever_value_is_refused(module):
    proc = cli(module, ["--lever", "bogus"])
    assert proc.returncode == 2          # AMENDED: argparse's quoting of the choices is not the spec's
    assert "invalid choice" in proc.stderr and "kv" in proc.stderr and "mtp" in proc.stderr


# (c) Wave 1 under kv takes the new axis `longctx` and the KV arm names; under mtp it refuses `longctx`
def test_wave1_kv_schedule_has_longctx_and_kv_arms():
    from bench import p426_wave1

    legs = p426_wave1.schedule(axes=("math500", "longctx"), lever="kv", arms=("n16", "x"))
    assert {leg[0] for leg in legs} == {"math500", "longctx"}
    assert {leg[1] for leg in legs} == {"n16", "x"}
    assert not any(leg[1] in ("off", "on") for leg in legs)


# (b) under lever mtp `longctx` is an unknown axis (today's refusal)
def test_wave1_mtp_refuses_longctx():
    from bench import p426_wave1

    with pytest.raises(ValueError):
        p426_wave1.schedule(axes=("longctx",))


# (c) a kv sequencer run with a non-s3 label is refused (the kv levers' build is s3)
def test_wave1_kv_refuses_a_label_other_than_s3(tmp_path):
    env = {"PYTHONPATH": str(BENCH), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(tmp_path),
           "STACK_WORKDIR": str(tmp_path)}          # AMENDED: the sequencer first checks --workdir is $STACK_WORKDIR
    proc = subprocess.run([sys.executable, "-m", "bench.p426_wave1", "--lever", "kv", "--build", "s2", "--main-root", str(tmp_path),
                           "--workdir", str(tmp_path), "--out", str(tmp_path / "o"), "--pair", "n16,x"],
                          cwd=BENCH, capture_output=True, text=True, timeout=300, env=env)
    assert proc.returncode != 0
    assert "s3" in proc.stderr


# ------------------------------------------------------------------------------------------------ signals calling B7 (mocked)
@pytest.fixture
def fake_b7(monkeypatch):
    """The B7 names the spec codes against, as recorded stubs (an import shim in the TEST, never in the product)."""
    import types

    calls = []
    m76_rule = types.ModuleType("bench.m76_rule")

    def rec(name, ret):
        def fn(*a, **kw):
            calls.append((name, a, kw))
            return ret
        return fn

    m76_rule.verdict_a5 = rec("verdict_a5", {"verdict": "PASS", "loss_bound_pp": 0.0})
    m76_rule.axis_verdict = rec("axis_verdict", {"verdict": "PASS"})
    m76_rule.axis_plan = rec("axis_plan", {"alpha_star": 0.01, "looks": [1]})
    m76_rule.session_interaction = rec("session_interaction", {"flag": False, "pvalue": 0.9})
    monkeypatch.setitem(sys.modules, "bench.m76_rule", m76_rule)
    import bench

    monkeypatch.setattr(bench, "m76_rule", m76_rule, raising=False)
    return calls


# (c) the kv signals entry in-process, B7 mocked: on a root with no pair evidence it refuses (rc 2, REFUSED, nothing written), it
# neither crashes nor calls B7 (no verdict is computed from nothing)
def test_kv_signals_refuse_without_evidence_and_write_nothing(tmp_path, fake_b7, capsys):
    from bench import p426_signals as S

    (tmp_path / "results").mkdir()
    out = tmp_path / "out"
    out.mkdir()
    rc = S.main(["all", "--lever", "kv", "--results-root", str(tmp_path / "results"), "--rows-root", str(tmp_path / "results"),
                 "--b8", str(tmp_path / "results" / "B8.json"), "--out-md", str(out / "SIGNALS.md"), "--out-json",
                 str(out / "SIGNALS.json")])      # AMENDED: `--lever` sits on `all`, not at the top level of p426_signals
    assert rc == 2
    assert "REFUSED" in capsys.readouterr().err
    assert not (out / "SIGNALS.md").exists() and not (out / "SIGNALS.json").exists()
    assert fake_b7 == []
