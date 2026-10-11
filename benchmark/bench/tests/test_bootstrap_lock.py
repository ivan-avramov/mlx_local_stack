"""P259-P262 (2026-10-10): everything a fresh box needs lives in the repo.

`benchmark/requirements-bench.lock` is the exact pin set of the bench venv; `scripts/bootstrap_machine.sh`
rebuilds config, workdir inputs and the venv from it. These tests keep the lock portable (no machine
paths, editable forks by relative path), aligned with `uv.lock` on the mlx pair that must match the
serving venv, and the bootstrap script parseable with the pins it advertises."""
import re
import subprocess
from pathlib import Path

import pytest

from bench import paths

REPO = paths.repo_root()
LOCK = REPO / "benchmark" / "requirements-bench.lock"
BOOTSTRAP = REPO / "scripts" / "bootstrap_machine.sh"


def _pins(text):
    out = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)==(\S+)$", line.strip())
        if m:
            out[m.group(1).lower()] = m.group(2)
    return out


def _uv_lock_version(name):
    txt = (REPO / "uv.lock").read_text()
    m = re.search(rf'^name = "{re.escape(name)}"\nversion = "([^"]+)"', txt, re.M)
    assert m, f"{name} not in uv.lock"
    return m.group(1)


def test_lock_has_no_machine_paths_or_file_urls():
    txt = LOCK.read_text()
    assert "file://" not in txt
    assert "/Users/" not in txt and "/home/" not in txt


def test_lock_installs_both_forks_editable_by_relative_path():
    lines = {l.strip() for l in LOCK.read_text().splitlines()}
    assert "-e ./src/mlx-vlm" in lines
    assert "-e ./src/mlx-serve" in lines


@pytest.mark.parametrize("name", ["mlx", "mlx-metal", "mlx-lm"])
def test_lock_mlx_pair_matches_the_serving_lock(name):
    # mlx core and mlx-metal must move together (a split pair fails at import with a missing
    # symbol in libmlx.dylib, seen 2026-10-10 while pinning), and both must equal the serving
    # venv's resolution so bench and server exercise the same kernels.
    assert _pins(LOCK.read_text())[name] == _uv_lock_version(name)


def test_lock_pins_every_line_exactly():
    for line in LOCK.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("-e "):
            continue
        assert re.match(r"^[A-Za-z0-9_.-]+==\S+$", s), f"unpinned line: {s!r}"


def test_bootstrap_script_parses_and_pins_the_recorded_corpus_sha():
    subprocess.run(["bash", "-n", str(BOOTSTRAP)], check=True)
    txt = BOOTSTRAP.read_text()
    assert "POLYGLOT_SHA=7e0611e" in txt            # rows record polyglot_sha; README "Fresh machine"
    assert "requirements-bench.lock" in txt
    assert "install_bench_opencode.sh" in txt
    assert "MLX_BOX" in txt                         # provenance label is mandatory on a new box
    assert "/Users/" not in txt and "/home/" not in txt


def test_bootstrap_refuses_without_a_box_label(tmp_path):
    # No config, no --box: must refuse before touching anything (exit 1, nothing created).
    r = subprocess.run([str(BOOTSTRAP), "--workdir", str(tmp_path / "wd"),
                        "--config-dir", str(tmp_path / "xdg"), "--skip-venv"],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "box" in (r.stderr + r.stdout).lower()
    assert not (tmp_path / "xdg").exists() and not (tmp_path / "wd").exists()
