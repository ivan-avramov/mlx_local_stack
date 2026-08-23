"""The opencode probe's per-item scratch dir must be symlink-free (fully resolved).

Root cause (2026-08-23, invalidated a full 3-arm M3 run): `tempfile.TemporaryDirectory`
on macOS returns paths under `/var/folders/...`, and `/var` is a symlink to
`/private/var`. opencode registers the `--dir` project root by the path STRING it was
given, while its tools canonicalize file paths — so every absolute-path tool call
resolves under `/private/var/...`, fails the project-boundary prefix check, and is
auto-rejected in non-interactive `run` mode. Sessions then "complete" in seconds with
no edits. 12/22 Qwen3.6-27B-Opus-Distill-OptiQ-4bit sessions and 6/22
Ornith-1.0-35B-mlx-uniform-4bit sessions died this way; the same items pass with a
symlink-free TMPDIR (A/B verified).
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from run_opencode_probe import _scratch_dir


def test_scratch_dir_is_fully_resolved(tmp_path):
    link = tmp_path / "alias"
    real = tmp_path / "real"
    real.mkdir()
    link.symlink_to(real)
    old = os.environ.get("TMPDIR")
    os.environ["TMPDIR"] = str(link)
    tempfile.tempdir = None  # force re-read of TMPDIR
    try:
        with _scratch_dir("beer-song") as work_root:
            p = Path(work_root)
            assert p.exists()
            assert str(p) == os.path.realpath(p), (
                f"scratch dir {p} contains symlinked components; opencode's "
                "project-boundary check breaks on the alias"
            )
            assert str(p).startswith(str(real)), "TMPDIR redirection was not honored"
    finally:
        if old is None:
            os.environ.pop("TMPDIR", None)
        else:
            os.environ["TMPDIR"] = old
        tempfile.tempdir = None


def test_scratch_dir_resolved_under_default_tmp():
    # On macOS the default TMPDIR lives under /var -> /private/var; the returned
    # scratch dir must already be the canonical form on any platform.
    with _scratch_dir("x") as work_root:
        assert str(work_root) == os.path.realpath(work_root)
