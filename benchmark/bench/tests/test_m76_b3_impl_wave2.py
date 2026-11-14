"""M76 B3: Wave 2 (tg1) under `lever=kv` — the sequencer's leg table and chain argv (both arms `--predictor mtp`, the KV label
passed as `--kv-arm`), the `m76` out-base, the KV pair dossier name, the freeze helpers (engagement role, live state, pilot gate
names, the R1 difference list) and the tg1 chain's P426 mode (`--kv-arm`: the arm name its record and pair gate use)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from bench import p426_freeze as fz
from bench import p426_hooks as ph
from bench import p426_wave2 as W2

BENCH = Path(__file__).resolve().parents[2]
ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"


def test_kv_leg_table():
    t = W2.kv_legs("n16", "x")
    names = [leg["name"] for leg in t["run"]]
    assert names == ["tg1-m76-n16-pilot", "tg1-m76-x-pilot", "tg1-m76-n16-s1", "tg1-m76-x-s1", "tg1-m76-x-s2", "tg1-m76-n16-s2",
                     "tg1-m76-n16-s3", "tg1-m76-x-s3", "tg1-m76-x-reload", "tg1-m76-n16-reload"]        # v1.2: B7's s1 + s2 + s3
    assert [leg["arm"] for leg in t["run"]] == ["n16", "x", "n16", "x", "x", "n16", "n16", "x", "x", "n16"]
    assert [leg["role"] for leg in t["run"]] == ["first", "second"] * 5
    assert [leg["name"] for leg in t["makeup"]] == ["tg1-m76-n16-makeup", "tg1-m76-x-makeup"]
    assert [leg["name"] for leg in t["rehearsal"]] == ["tg1-m76-rehearsal-n16", "tg1-m76-rehearsal-x", "tg1-m76-rehearsal-mismatch",
                                                       "tg1-m76-rehearsal-kill"]
    assert all("p426" not in leg["name"] for v in t.values() for leg in v)
    with pytest.raises(ValueError):
        W2.kv_legs("x", "n16")
    assert W2.predictor_of("kv", "n16") == W2.predictor_of("kv", "x") == "mtp"
    assert W2.predictor_of("mtp", "off") == "off" and W2.predictor_of("mtp", "on") == "mtp"


def _records(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    v8 = ph.write_exclusive(run / "v8_base.json", dict(kind=fz.KIND_V8, lever="kv", arms=["n16", "x"], build="s3",
                                                        n16_commit="1" * 40, x_commit="2" * 40, probe_code_sha256="a" * 64,
                                                        scaffold_policy_sha256="b" * 64, frozen_prompt_date="Fri Nov 13 2026"))
    ph.write_exclusive(run / "amendment.json", dict(kind=fz.KIND_AMENDMENT, v8_base_sha256=v8["sha256"]))
    return run


def test_kv_chain_argv(tmp_path):
    run = _records(tmp_path)
    t = W2.kv_legs("n16", "x")
    wts = {"n16": tmp_path / "wt-n16", "x": tmp_path / "wt-x"}
    for spec in t["run"]:
        rec = run / ("v8_base.json" if spec["record"] == "v8" else "amendment.json")
        argv = W2.leg_argv(spec, 1, worktrees=wts, record_path=rec, out_base=tmp_path / "out", lever="kv")
        assert argv[0] == str(wts[spec["arm"]] / ".venv-bench/bin/python")
        assert argv[argv.index("--predictor") + 1] == "mtp"
        assert argv[argv.index("--kv-arm") + 1] == spec["arm"] and argv[argv.index("--lever") + 1] == "kv"
        assert argv[argv.index("--campaign-core") + 1] == ("1" * 40 if spec["arm"] == "n16" else "2" * 40)
        assert argv[argv.index("--out-root") + 1] == str(tmp_path / "out" / f"{spec['name']}.a1")


def test_kv_dossier_name():
    assert W2.kv_dossier_name("s1", "n16", 1, "x", 2) == "s1__n16-a1__x-a2.json"


def test_kv_check_args(tmp_path):
    wd = tmp_path
    ok = W2.parse_args(["run", "--lever", "kv", "--pair", "n16,x", "--arm-worktree", f"n16={wd}/a", "--arm-worktree", f"x={wd}/b",
                        "--out-base", str(wd / "m76" / "p426" / "wave2"), "--record-dir", str(wd / "rec")])
    W2.check_args(ok, wd)
    assert ok.worktrees == {"n16": Path(f"{wd}/a"), "x": Path(f"{wd}/b")}
    for bad in (["--out-base", str(wd / "p426" / "wave2")],                          # a P426 out-base under kv
                ["--out-base", str(wd / "m76" / "p426" / "w"), "--worktree-off", str(wd / "a")]):
        a = W2.parse_args(["run", "--lever", "kv", "--pair", "n16,x", "--arm-worktree", f"n16={wd}/a",
                           "--arm-worktree", f"x={wd}/b", "--record-dir", str(wd / "rec"), *bad])
        with pytest.raises(fz.Refusal):
            W2.check_args(a, wd)
    a = W2.parse_args(["run", "--lever", "kv", "--pair", "x,n16", "--arm-worktree", f"n16={wd}/a", "--arm-worktree", f"x={wd}/b",
                       "--out-base", str(wd / "m76" / "p426" / "w"), "--record-dir", str(wd / "rec")])
    with pytest.raises(fz.Refusal):
        W2.check_args(a, wd)
    m = W2.parse_args(["run", "--out-base", str(wd / "p426" / "w"), "--record-dir", str(wd / "rec")])
    with pytest.raises(fz.Refusal, match="worktree"):
        W2.check_args(m, wd)                                                      # mtp still needs both worktrees


def test_freeze_engagement_role_and_kv_names():
    assert fz.engagement_role("x") == "on" and fz.engagement_role("n16") == "on"
    assert fz.engagement_role("off") == "off" and fz.engagement_role("on") == "on"
    assert fz.kv_pilot_leg("n16") == "tg1-m76-n16-pilot"
    assert fz.r1_difference_problems([dict(process="worker", field="argv.worker")], lever="kv") == []
    assert fz.r1_difference_problems([dict(process="-", field="snapshots.drafter")], lever="kv")
    assert fz.r1_difference_problems([dict(process="-", field="snapshots.drafter")]) == []      # mtp unchanged


class Ops:
    def __init__(self, st):
        self.st = st

    def worktree_state(self, path):
        return self.st[Path(path).name]

    def identity(self, path):
        return dict(probe_code_sha256="a" * 64, scaffold_policy_sha256="b" * 64, generation_identity_sha256="c" * 64)


def test_freeze_live_problems_under_kv(tmp_path):
    base = dict(lever="kv", arms=["n16", "x"], n16_commit="1" * 40, x_commit="2" * 40, n16_worktree="$STACK_WORKDIR/n16",
                x_worktree="$STACK_WORKDIR/x", gitlinks=dict(mlx_vlm="v" * 40, mlx_serve="s" * 40),
                probe_code_sha256="a" * 64, scaffold_policy_sha256="b" * 64, generation_identity_sha256="c" * 64)
    links = {"src/mlx-vlm": "v" * 40, "src/mlx-serve": "s" * 40}
    st = {"n16": dict(head="1" * 40, clean=True, gitlinks=links), "x": dict(head="2" * 40, clean=True, gitlinks=links)}
    assert fz.live_problems(base, Ops(st), tmp_path) == []
    st["x"] = dict(st["x"], head="3" * 40)
    assert any("x worktree HEAD" in p for p in fz.live_problems(base, Ops(st), tmp_path))


def test_tg1_chain_kv_arm_flag(monkeypatch):
    sys.path.insert(0, str(BENCH / "chains" / "c147"))
    import run_tg1_chain as C

    base = ["chain", "s1", "--p426", "--models", ENTRY, "--predictor", "mtp", "--out-root", "/wd/m76/p426/wave2/x.a1",
            "--campaign-core", "c", "--frozen-prompt-date", "Fri Nov 13 2026", "--probe-code-sha", "a" * 64,
            "--policy-sha", "b" * 64, "--frozen-record", "/wd/r.json"]
    a = C.parse_args(base + ["--lever", "kv", "--kv-arm", "x"])
    assert a.kv_arm == "x" and a.lever == "kv"
    assert C.parse_args(base).kv_arm is None and C.parse_args(base).lever == "mtp"
    for bad in (base + ["--lever", "kv", "--kv-arm", "on"], base + ["--kv-arm", "x"], base + ["--lever", "kv"],
                [t if t != "mtp" else "off" for t in base] + ["--lever", "kv", "--kv-arm", "x"],
                [t for t in base if t != "--p426"] + ["--lever", "kv", "--kv-arm", "x"]):
        with pytest.raises(SystemExit):
            C.parse_args(bad)

    class A:
        predictor, kv_arm = "mtp", "v"
    chain = C.Chain.__new__(C.Chain)
    chain.a = A()
    assert chain.p426_arm_name() == "v"
    A.kv_arm = None
    assert chain.p426_arm_name() == "on"


def test_tg1_chain_kv_record_must_say_kv(tmp_path):
    sys.path.insert(0, str(BENCH / "chains" / "c147"))
    import run_tg1_chain as C

    run = _records(tmp_path)

    class A:
        frozen_record, mode, rehearsal, kv_arm = str(run / "v8_base.json"), "pilot", False, "x"
    assert C.check_frozen_record(A)["base"]["lever"] == "kv"
    A.kv_arm = "v"                                       # not an arm of the record
    with pytest.raises(C.Refused):
        C.check_frozen_record(A)
    A.kv_arm = None                                      # a KV record never runs as an mtp leg
    with pytest.raises(C.Refused):
        C.check_frozen_record(A)
