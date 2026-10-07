"""M59 smoke finding (2026-10-07): opencode's system prompt and every tool path carry the scratch
directory, so a random per-run scratch name (`oc-<item>-<random>`) makes two same-seed sessions see
DIFFERENT prompts and diverge (pilot-twice p1 vs p2 on python/paasio: 6051 vs 10073 output tokens,
same seed, same overlay). The v2 probe therefore uses a FIXED scratch path per item, refuses a stale
one, and removes it afterwards. The 1.18 helper (`opencode_common._scratch_dir`, random) is untouched."""
from __future__ import annotations
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # benchmark/ on sys.path
import run_opencode_probe_v2 as P2  # noqa: E402


def test_item_scratch_path_is_deterministic_and_cleaned(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    with P2._item_scratch_dir("paasio") as a:
        first = a
        assert a.is_dir()
        assert a.name == "oc-paasio"               # no random suffix: identical prompt across passes
        assert a == Path(os.path.realpath(a))     # realpath (opencode compares path strings)
    assert not first.exists()                     # removed on exit
    with P2._item_scratch_dir("paasio") as b:
        assert b == first                         # same path on the second pass


def test_item_scratch_path_refuses_a_stale_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    stale = tmp_path / "scratch/octmp.noindex" / "oc-paasio"
    stale.mkdir(parents=True)
    (stale / "leftover.py").write_text("x = 1\n")
    with pytest.raises(SystemExit, match="REFUSED: stale scratch directory"):
        with P2._item_scratch_dir("paasio"):
            pass
    assert (stale / "leftover.py").exists()       # never silently deleted


def test_item_scratch_path_is_removed_on_error(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    with pytest.raises(RuntimeError):
        with P2._item_scratch_dir("forth") as d:
            (d / "x").write_text("x")
            raise RuntimeError("boom")
    assert not (tmp_path / "scratch/octmp.noindex" / "oc-forth").exists()


def test_hermetic_env_paths_that_reach_the_prompt_are_stable_across_runs(tmp_path):
    """opencode prints `<TMPDIR>/opencode` (and the scratch dir) into its system prompt (capture
    r01, line 48). Smoke attempt 6: the first prompts of two same-seed passes differed by 4 tokens
    because TMPDIR carried the per-run id. Every path the prompt can see must be identical across
    runs; the per-run isolation (HOME, XDG_*, config dir) stays per run."""
    base = tmp_path / "opencode-probe-v2"
    a = base / "run-20261006T220344-e7fac9d70fc2"
    b = base / "run-20261006T223615-2b7a480f3421"
    overlay = P2._seed_overlay("m", 1)
    ea = P2._opencode_env(a, tmp_path / "s", overlay)
    eb = P2._opencode_env(b, tmp_path / "s", overlay)
    assert ea["TMPDIR"] == eb["TMPDIR"]                      # stable, bench-owned, per item name
    assert Path(ea["TMPDIR"]).resolve() == (base / "tmp" / "s").resolve()
    ec = P2._opencode_env(a, tmp_path / "other", overlay)
    assert ec["TMPDIR"] != ea["TMPDIR"]                      # another item: its own dir (no clash)
    P2._fresh_tmpdir(ea)
    (Path(ea["TMPDIR"]) / "opencode").mkdir()
    P2._fresh_tmpdir(ea)
    assert Path(ea["TMPDIR"]).is_dir() and not (Path(ea["TMPDIR"]) / "opencode").exists()
    assert ea["HOME"] != eb["HOME"] and ea["XDG_DATA_HOME"] != eb["XDG_DATA_HOME"]   # isolation kept


def test_prompt_date_is_recorded_in_the_shape_opencode_prints(monkeypatch):
    import time
    assert P2._prompt_date() == time.strftime("%a %b %d %Y")


def test_prepared_tree_gets_fixed_mtimes(tmp_path):
    """Attempt 7 (2026-10-07): with identical prompts the first divergence was the model's `ls -la`
    output showing the prepared files' modification times (23:02 vs 23:27). Every file and dir of the
    prepared tree, `.git` included, gets one fixed mtime so tool output is reproducible."""
    import os
    work = tmp_path / "ex"
    (work / ".docs").mkdir(parents=True)
    (work / "ex.py").write_text("x = 1\n")
    (work / ".docs" / "instructions.md").write_text("spec\n")
    (work / ".git").mkdir()
    (work / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    P2._freeze_mtimes(work)
    stats = {p: os.stat(p).st_mtime for p in [work, *work.rglob("*")]}
    assert len(set(stats.values())) == 1
    assert int(next(iter(stats.values()))) == P2.FIXED_MTIME


def test_classifier_accepts_optional_final_step_finish_and_rejects_extra():
    def ev(*kinds):
        return [{"type": k, "sessionID": "ses_x"} for k in kinds]
    assert P2._classify(ev("step_start", "tool_use", "step_finish", "step_start", "text"), 0, "completed") is None
    assert P2._classify(ev("step_start", "tool_use", "step_finish", "step_start", "text", "step_finish"), 0, "completed") is None
    with pytest.raises(P2.TransportAbort, match="incomplete or unrecognised"):
        P2._classify(ev("step_start", "step_finish", "step_finish", "step_finish"), 0, "completed")
    with pytest.raises(P2.TransportAbort, match="incomplete or unrecognised"):
        P2._classify(ev("text"), 0, "completed")
    with pytest.raises(P2.TransportAbort, match="consecutive step_start"):
        P2._classify(ev("step_start", "step_start", "text"), 0, "completed")


def test_gate_window_honours_stall_ticks():
    w2 = P2._gate_window("Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", 16000, None, stall_ticks=2)
    w4 = P2._gate_window("Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", 16000, None, stall_ticks=4)
    assert w4["tick_s"] * 4 == w4["first_write_window_s"] and w2["tick_s"] * 2 == w2["first_write_window_s"]
    assert abs(w4["first_write_window_s"] - w2["first_write_window_s"]) <= 4   # same tokens either way
