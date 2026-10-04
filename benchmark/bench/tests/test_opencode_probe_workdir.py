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


def test_scratch_dir_is_fully_resolved(tmp_path, monkeypatch):
    # The scratch root may be reached through a symlink (an alias, or /var -> /private/var);
    # the yielded path must be the canonical form or opencode's project-boundary check
    # auto-rejects every absolute tool path. Since 2026-10-04 the root comes from
    # OPENCODE_PROBE_SCRATCH / <workdir>/scratch/octmp.noindex, not TMPDIR.
    link = tmp_path / "alias"
    real = tmp_path / "real"
    real.mkdir()
    link.symlink_to(real)
    monkeypatch.setenv("OPENCODE_PROBE_SCRATCH", str(link))
    with _scratch_dir("beer-song") as work_root:
        p = Path(work_root)
        assert p.exists()
        assert str(p) == os.path.realpath(p), (
            f"scratch dir {p} contains symlinked components; opencode's "
            "project-boundary check breaks on the alias"
        )
        assert str(p).startswith(str(real)), "OPENCODE_PROBE_SCRATCH redirection was not honored"


def test_scratch_dir_resolved_under_default_tmp(monkeypatch):
    # No override and no resolvable workdir -> tempfile's default (TMPDIR), which on macOS
    # lives under /var -> /private/var; the returned scratch dir must already be canonical.
    import run_opencode_probe as p
    monkeypatch.delenv("OPENCODE_PROBE_SCRATCH", raising=False)
    monkeypatch.setattr(p, "_stack_workdir", lambda required=False: None)
    with _scratch_dir("x") as work_root:
        assert str(work_root) == os.path.realpath(work_root)


def test_scratch_dir_defaults_under_workdir_noindex(tmp_path, monkeypatch):
    """2026-10-04 (M55): Spotlight indexed the per-item node_modules trees under the scratch dir
    (load 12 storms). macOS skips directories whose name ends in `.noindex`, so the probe's scratch
    root defaults to `<STACK_WORKDIR>/scratch/octmp.noindex` (created on demand) and no longer
    depends on the launcher exporting TMPDIR. `OPENCODE_PROBE_SCRATCH` overrides it explicitly."""
    import run_opencode_probe as p
    wd = tmp_path / "wd"; wd.mkdir()
    monkeypatch.setattr(p, "_stack_workdir", lambda required=False: wd)
    monkeypatch.delenv("OPENCODE_PROBE_SCRATCH", raising=False)
    monkeypatch.setenv("TMPDIR", str(tmp_path / "elsewhere"))
    with p._scratch_dir("beer-song") as root:
        assert str(root).startswith(str((wd / "scratch" / "octmp.noindex").resolve()))
        assert root.name.startswith("oc-beer-song-")
    override = tmp_path / "ovr.noindex"; override.mkdir()
    monkeypatch.setenv("OPENCODE_PROBE_SCRATCH", str(override))
    with p._scratch_dir("beer-song") as root:
        assert str(root).startswith(str(override.resolve()))
