"""M76 B1 acceptance 2 (implementer goldens, written and green BEFORE the campaign change): `--campaign u4` (the default) stays
byte-identical — the committed `MATRIX.Qwen3.8-27B-mlx-uniform-4bit.md` regenerates byte-for-byte from the committed
`benchmark/results/p475/` dossiers, and a mocked `u4` leg keeps its argv, paths, receipt keys and dossier inventory."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from bench import p475_kv as K
from bench.tests.p475s1 import helpers as H

REPO = Path(__file__).resolve().parents[3]
RESULTS = REPO / "benchmark" / "results" / "p475"
MATRIX = RESULTS / "MATRIX.Qwen3.8-27B-mlx-uniform-4bit.md"


def _committed_legs():
    return sorted(d for d in RESULTS.iterdir() if d.is_dir() and K.LEG_RE.match(d.name))


def _rebuild(tmp_path):
    """A repo / workdir pair holding copies of the committed dossiers and, as the run's scratch, their receipts and the
    recorded plan (two blocks, deciding block 3 started) — what `matrix` reads."""
    legs = _committed_legs()
    if not MATRIX.is_file() or not legs:
        pytest.skip("the committed P475 dossiers are not in this checkout")
    repo, wd = tmp_path / "repo", tmp_path / "wd"
    dst = repo / "benchmark" / "results" / "p475"
    dst.mkdir(parents=True)
    for d in legs:
        shutil.copytree(d, dst / d.name)
        leg = wd / "p475" / "legs" / d.name
        leg.mkdir(parents=True)
        shutil.copy2(d / "receipt.json", leg / "receipt.json")
    base = json.loads((legs[0] / "receipt.json").read_text())["base"]
    state = dict(version=1, model=K.PICK, base=base, plan=dict(blocks=2, deciding_block=3),
                 deciding=dict(block=3, started=True, complete=True))
    (wd / "p475" / "state.json").write_text(json.dumps(state))
    return repo, wd, base


def test_u4_matrix_regenerates_byte_identically(tmp_path):
    repo, wd, base = _rebuild(tmp_path)
    cfg = K.Config(repo=repo, workdir=wd, base=base)
    rc, path = K.matrix(cfg)
    assert path == repo / "benchmark" / "results" / "p475" / MATRIX.name
    assert path.read_bytes() == MATRIX.read_bytes()
    assert rc == 0


def test_u4_matrix_through_the_cli_is_byte_identical(tmp_path):
    repo, wd, base = _rebuild(tmp_path)
    rc = K.main(["--workdir", str(wd), "--repo", str(repo), "--base", base, "matrix"], ops=_NoOps())
    assert rc == 0
    assert (repo / "benchmark" / "results" / "p475" / MATRIX.name).read_bytes() == MATRIX.read_bytes()


class _NoOps:
    def git(self, wt, *args):                       # `--base` is already a full sha: resolve_base asks git to verify it
        return f"{args[-1].split('^')[0]}\n"


# ---------------------------------------------------------------------------------------------- a mocked u4 leg, pinned
KEYS_ON = ["arm", "attempt", "base", "block", "drafter_keys", "driver", "driver_argv", "driver_timeout_s", "engagement",
           "expected_rung_seconds", "expected_worker_argv", "grid", "identity_entry", "identity_exit", "idle", "instrument",
           "kv_line", "lease", "leg", "model", "paths", "power", "predictor", "preflight", "problems", "router", "router_pid",
           "speed_problems", "speed_valid", "teardown", "telemetry", "verdict", "watcher", "watcher_argv", "worker",
           "worker_argv", "worker_env"]
KEYS_OFF = [k for k in KEYS_ON if k != "engagement"]
DOSSIER = ["SCRUB_MANIFEST.json", "capacity_ladder.p475-{leg}.jsonl", "capacity_ladder.p475-{leg}.manifest.json",
           "kv_line.json", "receipt.json", "watch.jsonl", "worker_argv.json"]


def _rel(x, w):
    return json.loads(json.dumps(x, default=str).replace(str(w.wd), "<WD>").replace(str(w.main), "<REPO>"))


def _drop_pids(argv):
    out = list(argv)
    for flag in ("--driver-pid", "--driver-create-time"):
        if flag in out:
            out[out.index(flag) + 1] = "<…>"
    return out


@pytest.mark.parametrize("arm,arm_l,keys", [("TQ4", "tq4", KEYS_ON), ("TQ4-OFF", "tq4-off", KEYS_OFF)])
def test_u4_leg_argv_paths_receipt_keys_are_pinned(tmp_path, monkeypatch, arm, arm_l, keys):
    w = H.world(tmp_path, monkeypatch)
    ops = H.ready(w)
    r = H.run_leg(w, arm, block=1, ops=ops)
    leg = f"u4-{arm_l}-b1.a1"
    assert r["leg"] == leg and r["verdict"] == "VALID" and r["problems"] == [] and r["_harvest"] == "harvested"
    assert sorted(k for k in r if not k.startswith("_")) == keys
    assert _rel(r["_receipt_path"], w) == f"<WD>/p475/legs/{leg}/receipt.json"
    wt = f"<WD>/worktrees/p475-u4-{arm_l}"
    cap = f"<WD>/p475/legs/{leg}/capacity"
    assert _rel(r["paths"], w) == {
        "worktree": wt, "registry": f"{wt}/main_models.yaml",
        "rows": f"{cap}/capacity_ladder.p475-{leg}.jsonl", "manifest": f"{cap}/capacity_ladder.p475-{leg}.manifest.json",
        "watch": f"<WD>/p475/legs/{leg}/watch.jsonl", "worker_log": f"{wt}/logs/mlx_vlm.log",
        "router_log": f"{wt}/logs/main_model.log"}
    assert _rel(r["driver_argv"], w) == [
        f"{wt}/.venv-bench/bin/python", "-m", "bench.run_capacity", "--model", "Qwen3.8-27B-mlx-uniform-4bit",
        "--grid", "8192,131072,196608,260096", "--sampling-profile", "deployed", "--seed", "0", "--out-tag", f"p475-{leg}",
        "--out-dir", cap, "--p475-strict", "--expected-rung-seconds", "60,400,800,1500"]
    assert _drop_pids(_rel(r["watcher_argv"], w)) == [
        f"{wt}/.venv-bench/bin/python", f"{wt}/benchmark/m1/bench_watch.py", "--driver-pid", "<…>",
        "--driver-create-time", "<…>", "--capacity-rows", f"{cap}/capacity_ladder.p475-{leg}.jsonl",
        "--expected-rung-seconds", "60,400,800,1500", "--out", f"<WD>/p475/legs/{leg}/watch.jsonl", "--interval", "300"]
    dossier = w.main / "benchmark" / "results" / "p475" / leg
    assert sorted(p.name for p in dossier.iterdir()) == sorted(n.format(leg=leg) for n in DOSSIER)
    stored = json.loads((dossier / "receipt.json").read_text())
    assert "campaign" not in stored                              # a u4 record carries no campaign field (reads as u4)
    assert (w.wd / "p475" / "LAST_LEG_END").is_file()


def test_u4_names_and_order_are_pinned():
    assert K.PICK == "Qwen3.8-27B-mlx-uniform-4bit" and K.BASE_ARM == "TQ4"
    assert K.ARMS == ("N16", "AF8", "TQ8", "AF4", "TQ4", "TQ4-OFF")
    assert K.LEG_RE.pattern == r"^u4-(n16|af8|tq8|af4|tq4|tq4-off)-(b[1-9][0-9]*|smoke)\.a([1-9][0-9]*)$"
    assert K.branch_name("TQ4-OFF") == "p475-u4-tq4-off"
    assert K.leg_name("AF8", 2, 3) == "u4-af8-b2.a3" and K.leg_name("N16", "smoke", 1) == "u4-n16-smoke.a1"
    assert K.block_order(1) == K.ARMS and K.block_order(2) == tuple(reversed(K.ARMS))
    assert K.predictor_of("TQ4-OFF") == "off" and K.predictor_of("TQ4") == "on"
