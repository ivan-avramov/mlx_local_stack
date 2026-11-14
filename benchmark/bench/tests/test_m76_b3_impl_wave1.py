"""M76 B3: the Wave 1 sequencer and the harvest under `lever=kv` — the order-balanced schedule over a KV pair (block 1 ref → test,
block 2 test → ref), the Math500 tier-2 legs, the leg argv, the `m76` result / scratch paths, the frozen-record and arm-commit
checks; nothing launched (mocked)."""
from __future__ import annotations

from pathlib import Path

import pytest

from bench import p426_harvest as H
from bench import p426_plan as P
from bench import p426_wave1 as W1


def test_kv_schedule_is_order_balanced():
    legs = W1.schedule_kv(("math500", "longctx"), ("n16", "x"))
    assert legs[:4] == [("math500", "n16", "smoke", 1), ("math500", "x", "smoke", 1), ("longctx", "n16", "smoke", 1),
                        ("longctx", "x", "smoke", 1)]
    assert legs[4:8] == [("math500", "n16", 1, 1), ("math500", "x", 1, 1), ("math500", "x", 2, 1), ("math500", "n16", 2, 1)]
    assert legs[8:] == [("longctx", "n16", 1, 1), ("longctx", "x", 1, 1), ("longctx", "x", 2, 1), ("longctx", "n16", 2, 1)]
    assert "longctx" in W1.KV_AXES and set(W1.AXES) < set(W1.KV_AXES)


def test_kv_schedule_tier2_and_only_arm():
    t2 = W1.schedule_kv(("math500",), ("n16", "x"), tier=2)
    assert t2 == [("math500", "n16", 1, 2), ("math500", "x", 1, 2), ("math500", "x", 2, 2), ("math500", "n16", 2, 2)]
    with pytest.raises(ValueError):
        W1.schedule_kv(("cjudge",), ("n16", "x"), tier=2)
    v_only = W1.schedule_kv(("cjudge",), ("x", "v"), only="v")
    assert v_only == [("cjudge", "v", "smoke", 1), ("cjudge", "v", 1, 1), ("cjudge", "v", 2, 1)]
    with pytest.raises(ValueError):
        W1.schedule_kv(("cjudge",), ("x", "n16"))                # (reference, treatment) only
    with pytest.raises(ValueError):
        W1.schedule_kv(("tg9",), ("n16", "x"))


def test_kv_schedule_a5_tier2():
    """v1.4: A5 has a tier 2 (its second look), scheduled as Math500's: no smoke, ref → test, test → ref."""
    t2 = W1.schedule_kv(("longctx",), ("n16", "x"), tier=2)
    assert t2 == [("longctx", "n16", 1, 2), ("longctx", "x", 1, 2), ("longctx", "x", 2, 2), ("longctx", "n16", 2, 2)]
    assert [W1.kv_name(leg) for leg in t2] == ["longctx-m76-n16-lc-t2-b1", "longctx-m76-x-lc-t2-b1", "longctx-m76-x-lc-t2-b2",
                                               "longctx-m76-n16-lc-t2-b2"]
    assert W1.schedule_kv(("math500", "longctx"), ("n16", "x"), tier=2)[4:] == t2
    for axis in ("cjudge", "vision", "reasoning", "m1"):
        with pytest.raises(ValueError):
            W1.schedule_kv((axis, "longctx"), ("n16", "x"), tier=2)
    argv = W1.leg_argv_kv(Path("/wt/x"), Path("/wd"), Path("/r"), "longctx", "x", 1, 2, "s3")
    assert argv[argv.index("--axis") + 1] == "longctx" and argv[argv.index("--tier") + 1] == "2"


def test_kv_leg_names_never_p426():
    for leg in W1.schedule_kv(W1.KV_AXES, ("n16", "x")) + W1.schedule_kv(("math500",), ("x", "v"), tier=2):
        name = W1.kv_name(leg)
        assert "-m76-" in name and "p426" not in name


def test_kv_leg_argv():
    argv = W1.leg_argv_kv(Path("/wt/x"), Path("/wd"), Path("/out/receipts"), "math500", "x", 2, 2, "s3")
    assert argv[:3] == ["/wt/x/.venv-bench/bin/python", "-m", "bench.p426_leg"]
    assert argv[argv.index("--lever") + 1] == "kv" and argv[argv.index("--build") + 1] == "s3"
    assert argv[argv.index("--arm") + 1] == "x" and argv[argv.index("--block") + 1] == "2"
    assert argv[argv.index("--tier") + 1] == "2" and "--registry-on" not in argv and "--stack-root-off" not in argv
    smoke = W1.leg_argv_kv(Path("/wt/n16"), Path("/wd"), Path("/r"), "cjudge", "n16", "smoke", 1, "s3")
    assert "--smoke" in smoke and "--tier" not in smoke
    m1 = W1.leg_argv_kv(Path("/wt/x"), Path("/wd"), Path("/r"), "m1", "x", 1, 1, "s3", certified_by="/wd/m76/s2.json")
    assert m1[m1.index("--certified-by") + 1] == "/wd/m76/s2.json"
    with pytest.raises(ValueError):
        W1.leg_argv_kv(Path("/wt/x"), Path("/wd"), Path("/r"), "m1", "x", 1, 1, "s3")


def test_kv_paths_are_m76():
    assert H.wave1_dir("s3", lever="kv") == Path("benchmark/results/m76/wave1")
    assert H.wave1_dir("s2") == Path("benchmark/results/p426/wave1.s2") and H.wave1_dir() == Path("benchmark/results/p426/wave1")
    assert H.namespace_root("wave2", lever="kv") == Path("benchmark/results/m76/wave2")
    assert H.namespace_root("wave2") == Path("benchmark/results/p426/wave2")
    with pytest.raises(H.HarvestError):
        H.namespace_root("wave1", lever="kv")
    assert H.panel_dir("kv") == Path("benchmark/results/m76/panel")


def test_kv_claim_out_belongs_to_one_lever(tmp_path):
    assert W1.claim_out(tmp_path / "a", "kv:s3") is None
    assert (tmp_path / "a" / ".build").read_text().strip() == "kv:s3"
    assert W1.claim_out(tmp_path / "a", "s3")
    assert W1.claim_out(tmp_path / "a", "kv:s3") is None


def test_kv_label_problems_refuse_a_missing_or_foreign_record(tmp_path):
    got = W1.label_problems_kv("s3", tmp_path, {"n16": tmp_path / "n16", "x": tmp_path / "x"})
    assert got and "missing" in got[0]
    rec = tmp_path / "m76" / "p426" / "frozen.s3.json"
    rec.parent.mkdir(parents=True)
    rec.write_text('{"build": "s3", "lever": "mtp"}')
    got = W1.label_problems_kv("s3", tmp_path, {"n16": tmp_path / "n16", "x": tmp_path / "x"})
    assert any("lever" in p for p in got)


def test_kv_run_names_the_legs_by_kv_label(tmp_path):
    logs, launched = [], []
    legs = W1.schedule_kv(("cjudge",), ("n16", "x"))
    rc = W1.run(legs, launch=lambda leg: launched.append(leg) or 0, read_verdict=lambda n: None if n not in [W1.kv_name(l) for l in launched] else "VALID",
                sleep=lambda s: None, clock=iter(range(0, 10 ** 7, 700)).__next__, paused=lambda: False, log=logs.append,
                harvest=lambda leg: None, harvested=lambda n: False, idle_s=600, name_of=W1.kv_name)
    assert rc == 0 and launched == legs
    assert any("START cjudge-m76-n16-smoke" in line for line in logs)


# ------------------------------------------------------------------------------------------------- fix round 1 (spec v1.2)
def test_the_lever_surface_of_the_existing_functions():
    """v1.2: `leg_name`, `frozen_path`, `schedule`, `leg_argv` take `lever=` and dispatch to the KV implementations; `mtp`
    (the default) is unchanged."""
    assert P.leg_name("math500", "x", 1, "s3", lever="kv") == P.kv_leg_name("math500", "x", 1) == "math500-m76-x-b1"
    assert P.leg_name("math500", "x", 2, "s3", lever="kv", tier=2) == "math500-m76-x-t2-b2"
    assert P.leg_name("math500", "on", 1, "s2") == P.leg_name("math500", "on", 1, "s2", lever="mtp") == "math500-p426s2-on-b1"
    assert P.frozen_path(Path("/wd"), "s3", lever="kv") == Path("/wd/m76/p426/frozen.s3.json")
    assert P.frozen_path(Path("/wd"), "s2") == Path("/wd/p426/frozen.s2.json")
    with pytest.raises(ValueError):
        P.leg_name("math500", "x", 1, "s2", lever="kv")                      # kv runs on s3 only
    with pytest.raises(ValueError):
        P.leg_name("math500", "x", 1, "s3", lever="bogus")
    assert W1.schedule(axes=("cjudge",), lever="kv", arms=("n16", "x")) == W1.schedule_kv(("cjudge",), ("n16", "x"))
    assert W1.schedule(lever="kv", arms=("n16", "x")) == W1.schedule_kv(W1.KV_AXES, ("n16", "x"))
    assert W1.schedule() == W1.schedule(axes=W1.AXES) and W1.schedule(lever="mtp") == W1.schedule()
    with pytest.raises(ValueError):
        W1.schedule(arms=("n16", "x"))                                       # arms are a kv parameter
    kv = W1.leg_argv(Path("/wt/x"), Path("/wd"), None, Path("/r"), "cjudge", "x", 1, "s3", lever="kv")
    assert kv == W1.leg_argv_kv(Path("/wt/x"), Path("/wd"), Path("/r"), "cjudge", "x", 1, 1, "s3")
    assert W1.leg_name("cjudge", "x", 1, "s3", lever="kv") == "cjudge-m76-x-b1"
    with pytest.raises(ValueError):
        W1.leg_argv(Path("/wt/x"), Path("/wd"), Path("/ov.yaml"), Path("/r"), "cjudge", "x", 1, "s3", lever="kv")


def test_a_v_pair_and_a_missing_m1_binding_refuse_before_any_leg():
    """v1.2: stage 4 (V) is not in B3; Sol P10: a TQ4 arm's M1 binding is checked before ANY leg runs."""
    legs = W1.schedule_kv(W1.KV_AXES, ("x", "v"))
    assert any("names V" in p for p in W1.preflight_kv(("x", "v"), legs, {}))
    legs = W1.schedule_kv(W1.KV_AXES, ("n16", "x"))
    assert any("x m1 leg needs its stage-2 record" in p for p in W1.preflight_kv(("n16", "x"), legs, {}))
    assert any("no such file" in p for p in W1.preflight_kv(("n16", "x"), legs, {"x": "/nonexistent/summary.json"}))
    assert any("not a TQ4 arm" in p for p in W1.preflight_kv(("n16", "x"), legs, {"n16": __file__, "x": __file__}))
    assert W1.preflight_kv(("n16", "x"), legs, {"x": __file__}) == []
    assert W1.preflight_kv(("n16", "x"), W1.schedule_kv(("cjudge",), ("n16", "x")), {}) == []


def test_main_kv_refuses_v_before_anything_runs(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    out = tmp_path / "out"
    rc = W1.main(["--lever", "kv", "--build", "s3", "--pair", "x,v", "--arm-root", f"x={tmp_path}/x", "--arm-root",
                  f"v={tmp_path}/v", "--main-root", str(tmp_path / "main"), "--workdir", str(tmp_path), "--out", str(out)])
    assert rc == 2 and "names V" in capsys.readouterr().err and not out.exists()
    rc = W1.main(["--lever", "kv", "--build", "s3", "--pair", "n16,x", "--arm-root", f"n16={tmp_path}/n", "--arm-root",
                  f"x={tmp_path}/x", "--main-root", str(tmp_path / "main"), "--workdir", str(tmp_path), "--out", str(out)])
    assert rc == 2 and "stage-2 record" in capsys.readouterr().err and not out.exists()


def test_a4_then_a5_into_one_populated_results_directory(tmp_path, monkeypatch):
    """v1.2 (Sol P1): A5 has its own tune / stems; with A4's outputs already in the entry's results directory, A5's leg finds
    no existing output, and neither leg's stems match the other's files."""
    from bench.tests.test_m76_b3_impl_lever import build_ids

    ids = build_ids()
    monkeypatch.setattr(P, "load_m76_ids", lambda repo, text=None: ids)
    repo = Path(__file__).resolve().parents[3]

    def plan(axis, sel):
        return P.plan_leg(repo, axis, "x", None if sel == "smoke" else sel, smoke=sel == "smoke", results_root=tmp_path,
                          workdir="/wd", build="s3", lever="kv")
    for sel in ("smoke", 1):
        a4, a5 = plan("reasoning", sel), plan("longctx", sel)
        assert a4["tune"] != a5["tune"]
        d = Path(a4["results_dir"])
        d.mkdir(parents=True, exist_ok=True)
        for suffix in ("partial.jsonl", "json", "manifest.json", "partial.jsonl.provenance.json"):
            (d / f"{a4['stem']}.{suffix}").write_text("{}")
        assert P.existing_outputs(a5) == []                              # A4 ran first: A5 is not refused at its pre-check
        for p in a5["rows_paths"].values():
            p.write_text("{}")
        a4_files = set(P.existing_outputs(a4))
        a5_files = set(P.existing_outputs(a5))
        assert a4_files and a5_files and not a4_files & a5_files
