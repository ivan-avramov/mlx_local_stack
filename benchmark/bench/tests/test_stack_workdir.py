"""P89 (2026-09-29): ONE resolver for the out-of-repo artifact home (`bench.paths.stack_workdir`).

`STACK_WORKDIR` in the env wins; otherwise the machine-local `config.sh` is PARSED (never executed);
otherwise `MissingWorkdirError` (or None when the caller degrades). Shared by the opencode probe (M53),
`vision_gate`'s image cache and the visionqa loader, which each used to read the env on their own and
either refused late or fell back to the HF cache with a warning."""
from pathlib import Path

import pytest

from bench import paths


def _config_sh(tmp_path, monkeypatch, body):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    d = tmp_path / "xdg" / "mlx_local_stack"
    d.mkdir(parents=True)
    (d / "config.sh").write_text(body)


def test_env_wins_over_config_sh(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "env"))
    _config_sh(tmp_path, monkeypatch, 'export STACK_WORKDIR="/nope"\n')
    assert paths.stack_workdir() == tmp_path / "env"


def test_config_sh_fallback_expands_home_and_ignores_comments(monkeypatch, tmp_path):
    monkeypatch.delenv("STACK_WORKDIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _config_sh(tmp_path, monkeypatch,
               '# export STACK_WORKDIR="/commented-out"\nexport STACK_REPO="$HOME/ws/repo"\n'
               'export STACK_WORKDIR="$HOME/ws/wd"   # trailing comment\n')
    assert paths.stack_workdir() == tmp_path / "home" / "ws" / "wd"


def test_missing_everywhere_raises_or_returns_none(monkeypatch, tmp_path):
    monkeypatch.delenv("STACK_WORKDIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    with pytest.raises(paths.MissingWorkdirError) as ei:
        paths.stack_workdir()
    assert "STACK_WORKDIR" in str(ei.value)
    assert paths.stack_workdir(required=False) is None


def test_vision_gate_image_cache_uses_config_sh_without_a_warning(monkeypatch, tmp_path, capsys):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import vision_gate as VG
    monkeypatch.delenv("STACK_WORKDIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _config_sh(tmp_path, monkeypatch, 'export STACK_WORKDIR="$HOME/wd"\n')
    assert VG._image_cache_dir() == str(tmp_path / "home" / "wd" / "vision_gate_images")
    assert "WARNING" not in capsys.readouterr().err


def test_visionqa_image_cache_uses_config_sh_without_a_warning(monkeypatch, tmp_path, capsys):
    from bench import benchmarks as B
    monkeypatch.delenv("STACK_WORKDIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _config_sh(tmp_path, monkeypatch, 'export STACK_WORKDIR="$HOME/wd"\n')
    assert B._visionqa_image_cache_dir() == str(tmp_path / "home" / "wd" / "visionqa_images")
    assert "STACK_WORKDIR" not in capsys.readouterr().err


# --------------------------------------------------------------------------- confine_path (P19)
def test_confine_path_accepts_a_path_under_the_repo():
    p = paths.repo_root() / "benchmark" / "results" / "x.jsonl"
    assert paths.confine_path(p) is None


def test_confine_path_accepts_a_path_under_stack_workdir(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "wd"))
    p = tmp_path / "wd" / "m54" / "transcripts" / "model" / "t1.json"
    assert paths.confine_path(p) is None


def test_confine_path_refuses_a_path_outside_both(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "wd"))
    reason = paths.confine_path(tmp_path / "elsewhere" / "x.jsonl", what="--out")
    assert reason and "--out" in reason and "outside" in reason


def test_confine_path_refuses_outside_repo_when_workdir_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("STACK_WORKDIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-xdg"))
    reason = paths.confine_path(tmp_path / "elsewhere" / "x.jsonl")
    assert reason is not None
