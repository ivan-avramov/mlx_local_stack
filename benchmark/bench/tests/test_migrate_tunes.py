"""bench.migrate_tunes — migrates the six tune-fused pseudo-model result directories (and stamps
the already-correctly-encoded `.suffixon.*` files) into the ratified tune encoding
(docs/superpowers/specs/2026-08-17-tune-encoding-migration-design.md). Idempotent, dry-run by
default. All tests run against a mocked `tmp_path` tree — never `benchmark/results/`.
"""
import json

import pytest

import bench.migrate_tunes as M


def _write(root, model_dir, fname, content="row\n"):
    p = root / model_dir / fname
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _manifest(model):
    return json.dumps({"model": model, "sampling": {"temperature": 0.4}})


# --------------------------------------------------------------------------- planning / dry-run
def test_plan_renames_the_expected_set_for_a_clean_pseudo_dir(tmp_path):
    _write(tmp_path, "Ornith-1.0-35B-mlx-uniform-4bit-kv4", "aime.score.json", '{"acc":1}')
    _write(tmp_path, "Ornith-1.0-35B-mlx-uniform-4bit-kv4", "humanevalplus.jsonl", "row\n")
    _write(tmp_path, "Ornith-1.0-35B-mlx-uniform-4bit-kv4", "humanevalplus.manifest.json",
          _manifest("Ornith-1.0-35B-mlx-uniform-4bit-kv4"))

    actions = M.plan(tmp_path)
    moves = {(a["src"].name, a["dst"]) for a in actions if a["type"] == "move"}
    assert moves == {
        ("aime.score.json", tmp_path / "Ornith-1.0-35B-mlx-uniform-4bit" / "aime.kv4.score.json"),
        ("humanevalplus.jsonl",
         tmp_path / "Ornith-1.0-35B-mlx-uniform-4bit" / "humanevalplus.kv4.jsonl"),
        ("humanevalplus.manifest.json",
         tmp_path / "Ornith-1.0-35B-mlx-uniform-4bit" / "humanevalplus.kv4.manifest.json"),
    }
    rmdirs = [a for a in actions if a["type"] == "rmdir"]
    assert len(rmdirs) == 1 and rmdirs[0]["eligible"] is True


def test_dry_run_touches_nothing_on_disk(tmp_path):
    src = _write(tmp_path, "Qwen3.6-27B-MLX-8bit-kv16", "aime.jsonl", "row\n")
    M.plan(tmp_path)                                   # planning alone must never touch disk
    assert src.exists()
    assert not (tmp_path / "Qwen3.6-27B-MLX-8bit" / "aime.kv16.jsonl").exists()

    actions = M.plan(tmp_path)
    M.print_plan(actions, apply=False)                 # printing the dry-run plan is also inert
    assert src.exists()
    assert not (tmp_path / "Qwen3.6-27B-MLX-8bit" / "aime.kv16.jsonl").exists()
    assert (tmp_path / "Qwen3.6-27B-MLX-8bit-kv16").is_dir()


def test_dry_run_is_idempotent_with_itself(tmp_path):
    _write(tmp_path, "gemma-4-31b-it-6bit-kv16", "mbppplus.score.json", "{}")
    a1 = M.plan(tmp_path)
    a2 = M.plan(tmp_path)
    assert a1 == a2


# --------------------------------------------------------------------------- --apply / renames
def test_apply_moves_files_and_deletes_the_emptied_dir(tmp_path):
    _write(tmp_path, "Qwen3.6-27B-Opus-Distill-OptiQ-4bit-kv3", "mbppplus.jsonl", "row-bytes\n")
    _write(tmp_path, "Qwen3.6-27B-Opus-Distill-OptiQ-4bit-kv3", "mbppplus.score.json", '{"acc":0.9}')

    actions = M.plan(tmp_path)
    M.apply_plan(tmp_path, actions)

    dst_dir = tmp_path / "Qwen3.6-27B-Opus-Distill-OptiQ-4bit"
    assert (dst_dir / "mbppplus.kv3.jsonl").read_text() == "row-bytes\n"    # BYTE-IDENTICAL
    assert json.loads((dst_dir / "mbppplus.kv3.score.json").read_text()) == {"acc": 0.9}
    assert not (tmp_path / "Qwen3.6-27B-Opus-Distill-OptiQ-4bit-kv3").exists(), \
        "the emptied pseudo-model dir must be deleted"


def test_apply_rewrites_the_manifest_model_and_tune(tmp_path):
    _write(tmp_path, "Ornith-1.0-35B-mlx-uniform-4bit-suffix", "livecodebench.manifest.json",
          _manifest("Ornith-1.0-35B-mlx-uniform-4bit-suffix"))

    actions = M.plan(tmp_path)
    M.apply_plan(tmp_path, actions)

    man = json.loads((tmp_path / "Ornith-1.0-35B-mlx-uniform-4bit" /
                      "livecodebench.suffixon-phase2.manifest.json").read_text())
    assert man["model"] == "Ornith-1.0-35B-mlx-uniform-4bit"    # rewritten to the PURE name
    assert man["tune"] == "suffixon-phase2"
    assert man["sampling"] == {"temperature": 0.4}               # rest of the manifest preserved


def test_apply_is_idempotent(tmp_path):
    _write(tmp_path, "Qwen3.6-27B-UD-MLX-6bit-kv16", "aime.jsonl", "row\n")
    M.apply_plan(tmp_path, M.plan(tmp_path))
    assert not (tmp_path / "Qwen3.6-27B-UD-MLX-6bit-kv16").exists()
    # second run: the pseudo dir is gone, so there is nothing left to plan or apply
    actions2 = M.plan(tmp_path)
    assert actions2 == []
    M.apply_plan(tmp_path, actions2)      # must not raise
    assert (tmp_path / "Qwen3.6-27B-UD-MLX-6bit" / "aime.kv16.jsonl").read_text() == "row\n"


# --------------------------------------------------------------------------- collision refusal
def test_collision_is_refused_loudly_and_other_files_still_migrate(tmp_path):
    """A pseudo-dir row file whose target name already exists must be refused, never
    overwritten. (The historical instance -- `-suffix` vs the `.suffixon` keepers -- was
    RESOLVED 2026-08-17 by giving that dir its own `suffixon-phase2` label, so this test
    manufactures the same shape with a kv4 collision.)"""
    _write(tmp_path, "Ornith-1.0-35B-mlx-uniform-4bit-kv4", "humanevalplus.jsonl", "OLD-DATA\n")
    _write(tmp_path, "Ornith-1.0-35B-mlx-uniform-4bit-kv4", "aime.score.json", '{"acc":1}')
    _write(tmp_path, "Ornith-1.0-35B-mlx-uniform-4bit", "humanevalplus.kv4.jsonl", "KEEPER-DATA\n")

    actions = M.plan(tmp_path)
    collisions = [a for a in actions if a["type"] == "collision"]
    assert len(collisions) == 1
    assert collisions[0]["dst"].name == "humanevalplus.kv4.jsonl"

    M.apply_plan(tmp_path, actions)

    # the pre-existing file must be UNCHANGED (never overwritten)
    assert (tmp_path / "Ornith-1.0-35B-mlx-uniform-4bit" /
           "humanevalplus.kv4.jsonl").read_text() == "KEEPER-DATA\n"
    # the source file must NOT have been deleted either -- a refused move leaves the source alone
    assert (tmp_path / "Ornith-1.0-35B-mlx-uniform-4bit-kv4" / "humanevalplus.jsonl").exists()
    # the OTHER (non-colliding) file in the same pseudo dir still migrates
    assert (tmp_path / "Ornith-1.0-35B-mlx-uniform-4bit" / "aime.kv4.score.json").exists()
    # a dir with a refused file is NOT deleted -- data must never be silently dropped
    assert (tmp_path / "Ornith-1.0-35B-mlx-uniform-4bit-kv4").is_dir()


def test_collision_refusal_is_reported_in_print_plan(tmp_path, capsys):
    _write(tmp_path, "Ornith-1.0-35B-mlx-uniform-4bit-kv4", "humanevalplus.jsonl", "OLD-DATA\n")
    _write(tmp_path, "Ornith-1.0-35B-mlx-uniform-4bit", "humanevalplus.kv4.jsonl", "KEEPER\n")
    actions = M.plan(tmp_path)
    M.print_plan(actions, apply=False)
    out = capsys.readouterr().out
    assert "REFUSED" in out and "humanevalplus.kv4.jsonl" in out


# --------------------------------------------------------------------------- unrecognized (leftover) files
def test_files_that_are_not_a_recognized_bench_artifact_are_left_in_place(tmp_path):
    """capacity_ladder.jsonl / capacity_retrieval.json are fixed-name, per-model capacity-probe
    artifacts (bench/run_capacity.py), not `<bench>.*` rows -- the migration must not guess."""
    _write(tmp_path, "gemma-4-31b-it-6bit-kv16", "capacity_ladder.jsonl", "ladder\n")
    _write(tmp_path, "gemma-4-31b-it-6bit-kv16", "aime.score.json", '{"acc":1}')

    actions = M.plan(tmp_path)
    M.apply_plan(tmp_path, actions)

    assert (tmp_path / "gemma-4-31b-it-6bit-kv16" / "capacity_ladder.jsonl").exists()
    assert (tmp_path / "gemma-4-31b-it-6bit" / "aime.kv16.score.json").exists()
    # not fully emptied -> the pseudo dir must survive
    assert (tmp_path / "gemma-4-31b-it-6bit-kv16").is_dir()


# --------------------------------------------------------------------------- .suffixon.* stamping
def test_existing_suffixon_manifests_are_stamped_with_tune_only(tmp_path):
    """`.suffixon.*` files are ALREADY in the target encoding -- only the manifest gains a `tune`
    field; nothing is renamed."""
    p = _write(tmp_path, "m", "humanevalplus.suffixon.manifest.json", _manifest("m"))
    actions = M.plan(tmp_path)
    stamps = [a for a in actions if a["type"] == "stamp"]
    assert len(stamps) == 1 and stamps[0]["path"] == p and stamps[0]["tune"] == "suffixon"

    M.apply_plan(tmp_path, actions)
    man = json.loads(p.read_text())
    assert man["tune"] == "suffixon"
    assert man["model"] == "m"          # untouched -- already the pure name


def test_suffixon_stamping_is_idempotent(tmp_path):
    p = _write(tmp_path, "m", "humanevalplus.suffixon.manifest.json", _manifest("m"))
    M.apply_plan(tmp_path, M.plan(tmp_path))
    assert json.loads(p.read_text())["tune"] == "suffixon"
    actions2 = M.plan(tmp_path)
    assert not [a for a in actions2 if a["type"] == "stamp"], \
        "an already-stamped manifest must not be re-planned"


def test_suffixon_stamping_skips_a_pseudo_model_dir(tmp_path):
    """A `-kv4`/`-suffix`-style pseudo dir is handled entirely by the move pass; the stamp pass
    must not also treat it as an already-correct model dir."""
    _write(tmp_path, "Ornith-1.0-35B-mlx-uniform-4bit-suffix", "humanevalplus.suffixon.manifest.json",
          _manifest("x"))
    actions = M.plan(tmp_path)
    assert not [a for a in actions if a["type"] == "stamp"]


# --------------------------------------------------------------------------- --apply CLI end to end
def test_main_dry_run_by_default(tmp_path, capsys):
    _write(tmp_path, "gemma-4-31b-it-6bit-kv16", "aime.score.json", '{"acc":1}')
    M.main(["--root", str(tmp_path)])
    assert not (tmp_path / "gemma-4-31b-it-6bit" / "aime.kv16.score.json").exists()
    out = capsys.readouterr().out
    assert "DRY-RUN" in out


def test_main_apply_executes(tmp_path, capsys):
    _write(tmp_path, "gemma-4-31b-it-6bit-kv16", "aime.score.json", '{"acc":1}')
    M.main(["--root", str(tmp_path), "--apply"])
    assert (tmp_path / "gemma-4-31b-it-6bit" / "aime.kv16.score.json").exists()
    out = capsys.readouterr().out
    assert "APPLIED" in out
