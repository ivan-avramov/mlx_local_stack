"""P426 T3 fix round (strict-verify V3, V4): the p371 differential's lock-sha exception is one pinned pair, and a venv with two
dist-infos of a checked package is never read as a version. (V1 / V2, the exact-bytes restore, are in test_t3_wave1.py.)"""

from pathlib import Path

import pytest

from bench import p426_plan as PL
from bench.tests.p371_baseline import new_side

POINTER = "/runs/0/manifest/runtime/policy/toolchain/lock_sha256"
GOLDEN_LOCK = "ecd97da3ba64b482fda9e8bc91e36794231d34d9bfe63af84b1c2f7f20e73bcf"
S2_LOCK = "46612efe44cdbf4563479cfedadcd943d2320a97a7c4fe2801d253335adfb380"


# ------------------------------------------------------------------ V3 / P507: one pinned pair, never a self-comparison
def test_the_pinned_lock_sha_pair_is_accepted():
    assert new_side.rederive({})(POINTER, GOLDEN_LOCK, S2_LOCK) is True


@pytest.mark.parametrize("old, new", [
    (GOLDEN_LOCK, "0" * 64),                    # another new value
    (GOLDEN_LOCK, GOLDEN_LOCK),                 # unchanged is not a difference the hook is asked about, and is not the pair
    ("0" * 64, S2_LOCK),                        # another old value, the pinned new one
    ("ecd97da3", S2_LOCK),                      # the abbreviation is not the value
    (GOLDEN_LOCK, S2_LOCK[:-1] + "1"),
])
def test_any_other_lock_sha_pair_is_a_difference(old, new):
    assert new_side.rederive({})(POINTER, old, new) is False


def test_the_exception_is_not_a_comparison_with_the_live_lock(tmp_path, monkeypatch):
    """A lock changed after the pin is still the pinned pair's business: the live file is never read."""
    copy = tmp_path / "repo"
    (copy / "benchmark").mkdir(parents=True)
    (copy / "benchmark" / "requirements-bench.lock").write_text("a later lock\n")
    monkeypatch.setattr(new_side, "REPO", copy)
    later = new_side._sha((copy / "benchmark" / "requirements-bench.lock").read_bytes())
    assert new_side.rederive({})(POINTER, GOLDEN_LOCK, later) is False
    assert new_side.rederive({})(POINTER, GOLDEN_LOCK, S2_LOCK) is True


def test_the_docstring_names_the_exception_and_its_pair():
    doc = new_side.rederive.__doc__
    assert "ecd97da3" in doc and S2_LOCK[:8] in doc


# ------------------------------------------------------------------ V4: two dist-infos of one package
def _site(root, venv):
    site = Path(root) / venv / "lib" / "python3.12" / "site-packages"
    site.mkdir(parents=True, exist_ok=True)
    return site


def _fake_venv(root, venv, *dist_infos):
    site = _site(root, venv)
    for name in dist_infos:
        (site / f"{name}.dist-info").mkdir()


GOOD = ("mlx-0.32.4", "mlx_metal-0.32.4", "transformers-5.15.0", "huggingface_hub-1.12.0", "datasets-5.0.1", "mlx_audio-0.6.2")


def test_one_dist_info_per_package_reads_as_before(tmp_path):
    _fake_venv(tmp_path, ".venv", *GOOD)
    got = PL.venv_versions(tmp_path, ".venv")
    assert got == {"mlx": "0.32.4", "mlx-metal": "0.32.4", "transformers": "5.15.0", "huggingface-hub": "1.12.0",
                   "datasets": "5.0.1", "mlx-audio": "0.6.2"}


@pytest.mark.parametrize("extra, package", [("mlx-0.32.3", "mlx"), ("mlx_metal-0.32.3", "mlx-metal"), ("MLX_Audio-0.6.1", "mlx-audio")])
def test_two_dist_infos_of_a_package_are_a_problem_never_a_pick(tmp_path, extra, package):
    _fake_venv(tmp_path, ".venv", *GOOD, extra)
    got = PL.venv_versions(tmp_path, ".venv")
    value = got[package]
    assert value is not None and value.startswith(PL.AMBIGUOUS) and extra.rpartition("-")[2] in value
    assert all(got[p] and not got[p].startswith(PL.AMBIGUOUS) for p in got if p != package)


def test_a_record_taken_from_an_ambiguous_venv_is_refused(tmp_path):
    """The marker is never a recorded version, so a record made from such a venv cannot match the venv it came from."""
    _fake_venv(tmp_path, ".venv", *GOOD, "transformers-5.14.0")
    _fake_venv(tmp_path, ".venv-bench", *GOOD)
    live = {v: PL.venv_versions(tmp_path, v) for v in PL.VENVS}
    problems = PL.record_problems(dict(venvs=dict(off=live, on=live)), "s2")
    assert any("venvs.off..venv.transformers" in p and "more than one" in p for p in problems), problems
    assert not any(".venv-bench" in p and "more than one" in p for p in problems)
