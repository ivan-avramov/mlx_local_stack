"""P9 first-delivery regressions: historical fixture inputs survive live pin changes.

Real local Git objects, mock gate execution, committed artifacts; no models or network.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from bench.tests import t3_frozen_support as T
from bench.tests import test_m76_b3_impl_golden_mtp as M
from bench.tests import test_t3_frozen_gate as F

ROOT = Path(__file__).resolve().parents[3]
HISTORICAL_VLM = "1c7c8fa166582ac1a1c23ae9063527b2b5215b11"
REGISTRIES = {
    "off": Path("benchmark/bench/tests/fixtures/p426_off/main_models.yaml"),
    "on": Path("benchmark/results/p426/wave1.s2/m1-p426s2-on-b1/m1/overlay-Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed.yaml"),
}
BLOBS = {"off": "98bfdee6ca37cd8444b8bb7daf190026a5a38535", "on": "13a9559cba870b627c5f4cbc4a71aba0e62fd4bd"}


def git(repo, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        check=check,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
    )


def historical_inputs():
    fork = ROOT / "src/mlx-vlm"
    return tuple(git(fork, "show", f"{HISTORICAL_VLM}:{rel}").stdout.decode()
                 for rel in ("dev/ci.py", ".upstream-sync-ref"))


@pytest.fixture
def changed_live_fork(tmp_path, monkeypatch):
    """Keep authentic S2 objects, but give the checked fork a different live tree."""
    source = ROOT / "src/mlx-vlm"
    root = tmp_path / "source-stack"
    fork = root / "src/mlx-vlm"
    fork.parent.mkdir(parents=True)
    git(source, "clone", "--shared", "--no-checkout", str(source), str(fork))
    assert git(fork, "rev-parse", "HEAD").stdout.decode().strip() != HISTORICAL_VLM
    ci, ref = historical_inputs()
    (fork / "dev").mkdir()
    (fork / "dev/ci.py").write_text(T.ci_py([("check_changed_live_tree.py", ())]))
    (fork / ".upstream-sync-ref").write_text(T.sync_ref_file("v9.9.9"))
    assert (fork / "dev/ci.py").read_text() != ci
    assert (fork / ".upstream-sync-ref").read_text() != ref
    before = git(fork, "rev-parse", "HEAD").stdout
    monkeypatch.setattr(T, "REPO", root)
    yield fork
    assert git(fork, "rev-parse", "HEAD").stdout == before
    assert (fork / ".upstream-sync-ref").read_text() == T.sync_ref_file("v9.9.9")


def test_s2_inputs_are_verbatim_historical_objects(changed_live_fork):
    assert T.s2_inputs() == historical_inputs()


def test_s2_layout_gates_original_nine_audits_with_new_live_fork(changed_live_fork, tmp_path):
    repo, sha = T.s2_layout(tmp_path / "fixture/mlx-vlm")
    ci, ref = historical_inputs()
    assert git(repo, "show", f"{sha}:dev/ci.py").stdout == ci.encode()
    assert git(repo, "show", f"{sha}:.upstream-sync-ref").stdout == ref.encode()
    doc, runner = T.gate_run(tmp_path / "gate-run", repo, sha)
    assert doc["verdict"] == "PASS", doc["problems"]
    assert doc["parity_ref"] == "2ceff4c1"
    assert runner.audits() == [(name, "2ceff4c1", extra) for name, extra in T.S2_AUDITS]
    assert len(runner.audits()) == 9


def test_existing_per_sha_assertions_survive_changed_live_fork(changed_live_fork, tmp_path):
    F.test_audits_and_ref_are_derived_per_sha_not_from_the_live_tree(tmp_path)


def test_existing_old_workflow_assertions_survive_changed_live_fork(changed_live_fork, tmp_path):
    F.test_the_old_layout_keeps_the_workflow_ref_and_its_eight_audits(tmp_path)


def test_s2_inputs_refuse_missing_objects_despite_usable_live_files(tmp_path, monkeypatch):
    root = tmp_path / "without-history"
    fork = root / "src/mlx-vlm"
    fork.mkdir(parents=True)
    git(fork, "init", "-q")
    (fork / "dev").mkdir()
    ci, ref = historical_inputs()
    (fork / "dev/ci.py").write_text(ci)
    (fork / ".upstream-sync-ref").write_text(ref)
    assert git(fork, "cat-file", "-e", f"{HISTORICAL_VLM}^{{commit}}", check=False).returncode != 0
    monkeypatch.setattr(T, "REPO", root)
    with pytest.raises((subprocess.CalledProcessError, RuntimeError, AssertionError, ValueError)):
        T.s2_inputs()


@pytest.fixture
def registry_world(tmp_path, monkeypatch):
    """An ordinary local repository with the artifacts and no orphaned ON commit."""
    root = tmp_path / "artifact-stack"
    root.mkdir()
    git(root, "init", "-q")
    relatives = list(REGISTRIES.values()) + [Path("benchmark/results/p426/wave1.s2/run/frozen.s2.json")]
    for leg in ("math500-p426s2-off-b1", "math500-p426s2-on-b1", "vision-p426s2-on-b2", "reasoning-p426s2-off-b2"):
        relatives.append(Path(f"benchmark/results/p426/wave1.s2/{leg}/{leg}.receipt.json"))
    for relative in relatives:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    frozen = json.loads((root / relatives[2]).read_text())
    assert git(root, "cat-file", "-e", f"{frozen['stack_head_on']}^{{commit}}", check=False).returncode != 0
    monkeypatch.setattr(M, "REPO", root)
    monkeypatch.setattr(M, "BENCH", root / "benchmark")
    monkeypatch.setattr(M, "P426", root / "benchmark/results/p426")
    return root, frozen


@pytest.mark.parametrize("arm", ["off", "on"])
def test_committed_registry_artifacts_are_the_proven_blobs(arm):
    raw = (ROOT / REGISTRIES[arm]).read_bytes()
    frozen = json.loads((ROOT / "benchmark/results/p426/wave1.s2/run/frozen.s2.json").read_text())
    assert hashlib.sha256(raw).hexdigest() == frozen[f"registry_{arm}_sha"]
    assert hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest() == BLOBS[arm]


@pytest.mark.parametrize("arm", ["off", "on"])
def test_frozen_registry_text_reads_committed_bytes_without_on_commit(registry_world, arm):
    root, frozen = registry_world
    assert M._frozen_registry_text(frozen, arm) == (root / REGISTRIES[arm]).read_bytes().decode()


def test_leg_checks_keep_existing_golden_without_historical_on_commit(registry_world):
    checks = M.leg_checks()
    assert checks["delta"] == [] and checks["delta_strict"] and checks["reverse"]
    assert checks["math500-p426s2-on-b1"]["argv"] == []
    assert checks["math500-p426s2-off-b1"]["argv"] == []
    assert M._sha(checks) == "51b5be7800f20d63109048623a3b6ba5154a7a1404756474650f0530ed1e8c05"


@pytest.mark.parametrize("arm", ["off", "on"])
@pytest.mark.parametrize("corruption", ["digest", "bytes", "invalid-utf8"])
def test_registry_corruption_fails_before_decode_and_golden(registry_world, monkeypatch, arm, corruption):
    root, frozen = registry_world
    path = root / REGISTRIES[arm]
    if corruption == "digest":
        frozen[f"registry_{arm}_sha"] = "0" * 64
        (M.P426 / "wave1.s2/run/frozen.s2.json").write_text(json.dumps(frozen))
    else:
        path.write_bytes(path.read_bytes() + (b"\xff" if corruption == "invalid-utf8" else b"\n# altered frozen artifact\n"))
    # Keep the old Git-only implementation executable: an unrelated missing-object
    # error must not make a corruption test pass on the baseline.
    def original_registry(ref, relative):
        assert relative == "main_models.yaml"
        selected = "on" if ref == frozen["stack_head_on"] else "off"
        return (ROOT / REGISTRIES[selected]).read_bytes()

    monkeypatch.setattr(M, "_git_show", original_registry, raising=False)
    calls = []

    def no_golden(*args, **kwargs):
        calls.append(True)
        pytest.fail("golden computation ran before the frozen input digest was checked")

    monkeypatch.setattr(M.L, "registry_delta_problems", no_golden)
    with pytest.raises((subprocess.CalledProcessError, RuntimeError, AssertionError, ValueError)) as error:
        M.leg_checks()
    assert not isinstance(error.value, UnicodeDecodeError), "digest validation must precede decoding"
    assert calls == []
