"""M76 B1 (test-writer): acceptance 2 — `u4` byte-identity golden, written against the BASELINE and green on it.

(b) tests pin today's behaviour for `Qwen3.8-27B-mlx-uniform-4bit`: the regenerated `MATRIX.<pick>.md` from the committed
`benchmark/results/p475/` dossiers, and the argv / paths / receipt keys / registry bytes of a mocked leg and of `prepare`.
(c) tests assert that the new `--campaign u4` spelling gives the same bytes.
"""
from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from bench import p475_kv as K
from bench.tests.test_m76_b1_fe_support import REPO_ROOT, PrepOps, cli
from bench.tests.test_p475_impl_support import BASE, FakeOps, base_registry, make_cfg

U4_PICK = "Qwen3.8-27B-mlx-uniform-4bit"
U4_ARMS = ("N16", "AF8", "TQ8", "AF4", "TQ4", "TQ4-OFF")
COMMITTED = REPO_ROOT / "benchmark" / "results" / "p475"
MATRIX = f"MATRIX.{U4_PICK}.md"


class GitOnly:
    """The only Ops call `matrix` needs: resolving `--base` (`rev-parse --verify <rev>^{commit}`)."""

    def __init__(self, base):
        self.base = base

    def git(self, wt, *args):
        return self.base + "\n"


def _u4_world(tmp_path):
    """Workdir + repo reconstructed from the committed dossiers: the dossiers under `benchmark/results/p475`, the canonical receipts
    under `$STACK_WORKDIR/p475/legs`, and the state `run` recorded (2 measured blocks, deciding block b3 started and complete)."""
    repo, wd = tmp_path / "repo", tmp_path / "wd"
    results = repo / "benchmark" / "results" / "p475"
    shutil.copytree(COMMITTED, results, ignore=shutil.ignore_patterns("archive", "MATRIX*"))
    base = None
    for d in sorted(results.iterdir()):
        if d.is_dir() and d.name.startswith("u4-"):
            leg = wd / "p475" / "legs" / d.name
            leg.mkdir(parents=True)
            shutil.copy(d / "receipt.json", leg / "receipt.json")
            base = base or json.loads((d / "receipt.json").read_text())["base"]
    state = dict(version=1, model=U4_PICK, base=base, plan=dict(blocks=2, deciding_block=3),
                 deciding=dict(block=3, started=True, complete=True), used=dict(replacements=0, not_started=0, deciding=1),
                 refused_arms=[], legs=[])
    (wd / "p475" / "state.json").write_text(json.dumps(state))
    return repo, wd, base, results


def _matrix_argv(repo, wd, base, *top):
    return ["--workdir", str(wd), "--repo", str(repo), "--base", base, *top, "matrix"]


# ================================================================================================ the matrix golden
@pytest.mark.parametrize("top", [(), ("--campaign", "u4")], ids=["default", "explicit-campaign-u4"])
def test_the_u4_matrix_regenerates_byte_identically_from_the_committed_dossiers(tmp_path, top):
    """(b) default spelling [green on the baseline]; (c) with `--campaign u4` [red until the flag exists]. Acceptance 2."""
    repo, wd, base, results = _u4_world(tmp_path)
    rc = cli(_matrix_argv(repo, wd, base, *top), GitOnly(base))
    assert rc == 0
    assert (results / MATRIX).read_bytes() == (COMMITTED / MATRIX).read_bytes()
    assert not (results / f"MATRIX.{U4_PICK}.PARTIAL.md").exists()


def test_a_u4_dossier_dir_set_is_the_one_the_golden_is_built_from():
    """(b) Guard of the golden's own input: 21 finalized `u4-*` dossiers incl. the b3 deciding block and the replaced b3.a1."""
    names = sorted(d.name for d in COMMITTED.iterdir() if d.is_dir() and d.name.startswith("u4-"))
    assert len(names) == 21 and "u4-tq4-off-b3.a1" in names and "u4-tq4-off-b3.a2" in names and "u4-tq4-smoke.a1" in names


# ================================================================================================ a mocked u4 leg, pinned
def _norm(value, cfg):
    s = json.dumps(value, sort_keys=True)
    return json.loads(s.replace(str(cfg.workdir), "<WD>").replace(str(cfg.repo), "<REPO>"))


def _u4_leg(tmp_path, arm="AF8"):
    ops, cfg = FakeOps(tmp_path), make_cfg(tmp_path)
    ops.add_all(cfg)
    name = K.leg_name(arm, 1, 1)
    receipt = K.run_leg(name, arm, ops, cfg)
    return ops, cfg, name, receipt


def test_a_u4_leg_keeps_its_paths_argv_and_receipt_keys(tmp_path):
    """(b) Acceptance 2: the u4 argv / paths / receipt keys of a mocked leg."""
    ops, cfg, name, receipt = _u4_leg(tmp_path)
    assert receipt["verdict"] == "VALID" and name == "u4-af8-b1.a1"
    wt = cfg.workdir / "worktrees" / "p475-u4-af8"
    assert cfg.worktree("AF8") == wt and cfg.registry("AF8") == wt / "main_models.yaml"
    assert cfg.p475 == cfg.workdir / "p475" and cfg.state_path == cfg.workdir / "p475" / "state.json"
    assert cfg.leg_dir(name) == cfg.workdir / "p475" / "legs" / name
    assert cfg.results == cfg.repo / "benchmark" / "results" / "p475" and cfg.dossier(name) == cfg.results / name
    assert cfg.preflight_record("AF8") == cfg.workdir / "p475" / "preflight" / "AF8.json"
    assert cfg.preflight_record("AF8", "engagement") == cfg.workdir / "p475" / "engagement" / "AF8.json"
    assert K.branch_name("AF8") == "p475-u4-af8" and cfg.out_tag(name) == f"p475-{name}"
    on_disk = json.loads(cfg.receipt_path(name).read_text())
    assert sorted(on_disk) == sorted(RECEIPT_KEYS) and "campaign" not in on_disk
    assert _norm(on_disk["paths"], cfg) == {
        "worktree": "<WD>/worktrees/p475-u4-af8", "registry": "<WD>/worktrees/p475-u4-af8/main_models.yaml",
        "rows": f"<WD>/p475/legs/{name}/capacity/capacity_ladder.p475-{name}.jsonl",
        "manifest": f"<WD>/p475/legs/{name}/capacity/capacity_ladder.p475-{name}.manifest.json",
        "watch": f"<WD>/p475/legs/{name}/watch.jsonl", "worker_log": "<WD>/worktrees/p475-u4-af8/logs/mlx_vlm.log",
        "router_log": "<WD>/worktrees/p475-u4-af8/logs/main_model.log"}
    expected = ",".join(f"{x:g}" for x in cfg.expected_for("AF8", 1))
    assert expected == AF8_EXPECTED
    assert _norm(on_disk["driver_argv"], cfg) == [
        "<WD>/worktrees/p475-u4-af8/.venv-bench/bin/python", "-m", "bench.run_capacity", "--model", U4_PICK,
        "--grid", "8192,131072,196608,260096", "--sampling-profile", "deployed", "--seed", "0", "--out-tag", f"p475-{name}",
        "--out-dir", f"<WD>/p475/legs/{name}/capacity", "--p475-strict", "--expected-rung-seconds", expected]
    assert _norm(on_disk["watcher_argv"], cfg) == [
        "<WD>/worktrees/p475-u4-af8/.venv-bench/bin/python", "<WD>/worktrees/p475-u4-af8/benchmark/m1/bench_watch.py",
        "--driver-pid", "301", "--driver-create-time", "4.0", "--capacity-rows",
        f"<WD>/p475/legs/{name}/capacity/capacity_ladder.p475-{name}.jsonl", "--expected-rung-seconds", expected,
        "--out", f"<WD>/p475/legs/{name}/watch.jsonl", "--interval", "300"]
    sp = ops.spawned[0]
    assert sp["cwd"] == str(wt / "benchmark") and sp["session"] is True
    assert sp["env"]["MLX_SERVE_CONFIG"] == str(wt / "main_models.yaml") and sp["env"]["MLX_BENCH_SESSION_PREFIX"] == f"p475-{name}"
    assert ("stack", str(wt), str(wt / "main_models.yaml"), "mtp") in ops.calls
    assert sorted(p.name for p in cfg.dossier(name).iterdir()) == sorted(
        ["receipt.json", "watch.jsonl", f"capacity_ladder.p475-{name}.jsonl", f"capacity_ladder.p475-{name}.manifest.json",
         "kv_line.json", "worker_argv.json", "SCRUB_MANIFEST.json"])
    assert float((cfg.p475 / "LAST_LEG_END").read_text()) == ops.t


# the on-disk receipt of a VALID u4 leg today (a new `campaign` key would break "byte-identical receipts"; see the report)
RECEIPT_KEYS = [
    "arm", "attempt", "base", "block", "drafter_keys", "driver", "driver_argv", "driver_timeout_s", "engagement",
    "expected_rung_seconds", "expected_worker_argv", "grid", "identity_entry", "identity_exit", "idle", "instrument", "kv_line",
    "lease", "leg", "model", "paths", "power", "predictor", "preflight", "problems", "router", "router_pid", "speed_problems",
    "speed_valid", "teardown", "telemetry", "verdict", "watcher", "watcher_argv", "worker", "worker_argv", "worker_env"]
AF8_EXPECTED = "28.9,461.9,692.8,916.5"


def test_a_u4_off_leg_and_the_smoke_names_are_unchanged(tmp_path):
    """(b) Names and predictor of the other u4 shapes."""
    assert K.leg_name("TQ4-OFF", 2, 3) == "u4-tq4-off-b2.a3" and K.leg_name("TQ4", "smoke", 1) == "u4-tq4-smoke.a1"
    assert K.block_order(1) == U4_ARMS and K.block_order(2) == tuple(reversed(U4_ARMS))
    assert K.SMOKE_ARMS == ("N16", "TQ4") and K.BASE_ARM == "TQ4" and K.REFERENCE_ARM == "N16"
    ops, cfg, name, receipt = _u4_leg(tmp_path, "TQ4-OFF")
    assert receipt["verdict"] == "VALID" and receipt["predictor"] == "off"
    assert ("stack", str(cfg.worktree("TQ4-OFF")), str(cfg.registry("TQ4-OFF")), "off") in ops.calls


# ================================================================================================ prepare, pinned
ARM_TEXT_SHA = {              # sha256 of each arm's committed registry over `base_registry()`, as `prepare` writes it today
    "N16": "2701976cffe42f61a2eb990afe654c34e0fd028df167649305c4d5cf398b738d",
    "AF8": "c91e0d4e6dcc6d23b06bb85ac51e3ed73f894bb77be8c7df7c7a32627316be55",
    "TQ8": "8e146b0d98df5aab6daf2423dee0974660fdf7b2a3354370481cd9375f95ddd0",
    "AF4": "b05d4749cc702c6944a22bad64c4a30447c0cf16576fb5293af1d635b63f0107",
    "TQ4": "759547d10cd7ff1918b95529cd8606d4820e01dd29fa1ced6c7f625921d0043c",
    "TQ4-OFF": "d7758002ed4aca10e9f1e47b59ca3dda4f8171ae177f31bdeb50892f6b7f67eb",
}


@pytest.mark.parametrize("top", [(), ("--campaign", "u4")], ids=["default", "explicit-campaign-u4"])
def test_u4_prepare_makes_the_same_branches_worktrees_and_registry_bytes(tmp_path, top):
    """(b) default / (c) `--campaign u4`: `prepare` over the synthetic base registry: branch + worktree names and each arm's
    committed registry bytes (sha256) as today."""
    wd, repo = tmp_path / "wd", tmp_path / "repo"
    repo.mkdir()
    wd.mkdir()
    ops = PrepOps(base_registry())
    rc = cli(["--workdir", str(wd), "--repo", str(repo), "--base", BASE, *top, "prepare"], ops)
    assert rc == 0
    adds = [a for _, a in ops.calls if a[:2] == ("worktree", "add")]
    assert sorted(a[3] for a in adds if "-b" in a) == sorted(f"p475-u4-{x.lower()}" for x in U4_ARMS)
    assert sorted(a[4] for a in adds if "-b" in a) == sorted(str(wd / "worktrees" / f"p475-u4-{x.lower()}") for x in U4_ARMS)
    got = {arm: (ops.committed(f"p475-u4-{arm.lower()}") or base_registry()) for arm in U4_ARMS}
    assert got["TQ4"] == base_registry()
    assert {arm: hashlib.sha256(t.encode()).hexdigest() for arm, t in got.items()} == ARM_TEXT_SHA
    assert (wd / "p475" / "state.json").is_file() and json.loads((wd / "p475" / "state.json").read_text())["base"] == BASE
