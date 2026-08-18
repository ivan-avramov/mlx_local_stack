"""Migrate the tune-fused pseudo-model result directories, and the ad-hoc `.suffixon.*` files,
into the ratified tune encoding (docs/superpowers/specs/2026-08-17-tune-encoding-migration-
design.md, operator ruling 6, 2026-08-17): result directories stay PURE registry model names, and
a `tune` travels as a `<bench>.<tune>.<ext>` filename infix plus a top-level `manifest["tune"]`
field.

Two migrations, both idempotent:

1. Six pseudo-model directories fuse a tune into the model NAME
   (`Ornith-1.0-35B-mlx-uniform-4bit-kv4`, `Ornith-1.0-35B-mlx-uniform-4bit-suffix`,
   `Qwen3.6-27B-Opus-Distill-OptiQ-4bit-kv3`, `Qwen3.6-27B-MLX-8bit-kv16`,
   `Qwen3.6-27B-UD-MLX-6bit-kv16`, `gemma-4-31b-it-6bit-kv16`) — a category error under the
   ratified taxonomy (KV bits / suffix state are TUNE, not model identity). Every recognized
   `<bench>.*` artifact (rows, manifest, score, evalplus sidecars) moves into the PURE model
   directory, relabelled `<bench>.<tune>.*`; the manifest's `model` is rewritten to the pure name
   and gains `tune: <label>`; the source directory is deleted once (and only once) fully emptied.
2. The already-correctly-encoded `.suffixon.*` files (produced ad-hoc, by literally passing a
   dotted bench name like `"humanevalplus.suffixon"` through the pre-D3 harness) need no
   renaming — only their manifests gain `tune: "suffixon"`.

DRY-RUN BY DEFAULT. `--apply` executes. Every move is printed as `old -> new`. NEVER overwrites:
a target that already exists is a REFUSED collision, reported loudly, and migration continues
with the rest of that directory's files — the operator resolves collisions by hand. A directory
with any refused collision or any file this script does not recognize as a bench artifact
(e.g. `capacity_ladder.jsonl`, a fixed-name per-model artifact from `run_capacity.py`, not a
`<bench>.*` row) is left on disk rather than partially deleted.

    PYTHONPATH=benchmark .venv-bench/bin/python -m bench.migrate_tunes            # dry-run
    PYTHONPATH=benchmark .venv-bench/bin/python -m bench.migrate_tunes --apply    # execute
"""
import argparse
import json
from pathlib import Path

from . import benchmarks, paths

# Source pseudo-model dir -> (pure registry model name, canonical tune label). Hardcoded rather
# than derived from the dir name: the dir-suffix -> label mapping is NOT a mechanical strip (
# "-suffix" becomes "suffixon", not "suffix"), and an explicit table is auditable in a way a
# regex rule is not.
PSEUDO_MODEL_DIRS = {
    "Ornith-1.0-35B-mlx-uniform-4bit-kv4": ("Ornith-1.0-35B-mlx-uniform-4bit", "kv4"),
    "Ornith-1.0-35B-mlx-uniform-4bit-suffix": ("Ornith-1.0-35B-mlx-uniform-4bit", "suffixon"),
    "Qwen3.6-27B-Opus-Distill-OptiQ-4bit-kv3": ("Qwen3.6-27B-Opus-Distill-OptiQ-4bit", "kv3"),
    "Qwen3.6-27B-MLX-8bit-kv16": ("Qwen3.6-27B-MLX-8bit", "kv16"),
    "Qwen3.6-27B-UD-MLX-6bit-kv16": ("Qwen3.6-27B-UD-MLX-6bit", "kv16"),
    "gemma-4-31b-it-6bit-kv16": ("gemma-4-31b-it-6bit", "kv16"),
}


def _bench_names():
    return tuple(benchmarks.SPECS.keys())


def _split_bench_file(fname: str, benches) -> tuple[str, str] | None:
    """If `fname` is a per-bench artifact — `<bench>.jsonl`, `<bench>.manifest.json`,
    `<bench>.score.json`, `<bench>_samples.jsonl`, `<bench>_samples_eval_results.json`, or any
    other `<bench>{.|_}...` file — return `(bench, rest)` where `rest` is everything after the
    bench name (e.g. `.jsonl`, `_samples.jsonl`). `None` for anything else: the caller must never
    guess at a file it does not recognize."""
    for b in sorted(benches, key=len, reverse=True):   # longest first: no bench name here is a
        if fname == b:                                 # prefix of another, but stay defensive
            return b, ""
        if fname.startswith(b + ".") or fname.startswith(b + "_"):
            return b, fname[len(b):]
    return None


def plan(root: Path) -> list[dict]:
    """Compute the full migration plan against `root`, WITHOUT touching disk. Each action is one
    of:
      {"type": "move", "src": Path, "dst": Path, "rewrite_manifest": bool,
       "model": str, "tune": str}
      {"type": "collision", "src": Path, "dst": Path}
      {"type": "leftover", "path": Path}            -- unrecognized file; left alone
      {"type": "rmdir", "path": Path, "eligible": bool}
      {"type": "stamp", "path": Path, "tune": str}   -- add tune to an already-correct manifest
      {"type": "stamp_error", "path": Path}          -- unparseable .suffixon.manifest.json
    """
    actions = []
    benches = _bench_names()
    for dirname in sorted(PSEUDO_MODEL_DIRS):
        pure_model, label = PSEUDO_MODEL_DIRS[dirname]
        src_dir = root / dirname
        if not src_dir.is_dir():
            continue
        dst_dir = root / pure_model
        dir_actions = []
        emptiable = True
        for f in sorted(src_dir.iterdir()):
            if not f.is_file():
                dir_actions.append({"type": "leftover", "path": f})
                emptiable = False
                continue
            split = _split_bench_file(f.name, benches)
            if split is None:
                dir_actions.append({"type": "leftover", "path": f})
                emptiable = False
                continue
            bench, rest = split
            dst = dst_dir / f"{bench}.{label}{rest}"
            if dst.exists():
                dir_actions.append({"type": "collision", "src": f, "dst": dst})
                emptiable = False
                continue
            dir_actions.append({"type": "move", "src": f, "dst": dst,
                                "rewrite_manifest": dst.name.endswith(".manifest.json"),
                                "model": pure_model, "tune": label})
        dir_actions.append({"type": "rmdir", "path": src_dir, "eligible": emptiable})
        actions.extend(dir_actions)

    # Pass 2: `.suffixon.*` files are already in the target encoding (a `-suffix` pseudo dir is
    # handled entirely by pass 1 above, so skip anything under PSEUDO_MODEL_DIRS here) -- only
    # stamp the manifest.
    if root.is_dir():
        for mdir in sorted(p for p in root.iterdir() if p.is_dir()):
            if mdir.name in PSEUDO_MODEL_DIRS:
                continue
            for mf in sorted(mdir.glob("*.suffixon.manifest.json")):
                try:
                    cur = json.loads(mf.read_text())
                except (OSError, ValueError):
                    actions.append({"type": "stamp_error", "path": mf})
                    continue
                if cur.get("tune") == "suffixon":
                    continue                            # already migrated -> idempotent no-op
                actions.append({"type": "stamp", "path": mf, "tune": "suffixon"})
    return actions


def apply_plan(root: Path, actions: list[dict] | None = None) -> list[dict]:
    """Execute a plan (freshly computed from `root` if not given). `move` renames non-manifest
    files byte-for-byte (never rewrites row/score data); a `.manifest.json` move rewrites `model`
    (to the pure name) and `tune` while relocating. `collision`/`leftover` actions are reports
    only — never touched. A `rmdir` fires only when `eligible` (the directory truly emptied)."""
    if actions is None:
        actions = plan(root)
    for a in actions:
        if a["type"] == "move":
            a["dst"].parent.mkdir(parents=True, exist_ok=True)
            if a["rewrite_manifest"]:
                try:
                    man = json.loads(a["src"].read_text())
                except (OSError, ValueError):
                    man = {}
                man["model"] = a["model"]
                man["tune"] = a["tune"]
                a["dst"].write_text(json.dumps(man, indent=2))
                a["src"].unlink()
            else:
                a["src"].rename(a["dst"])
        elif a["type"] == "stamp":
            man = json.loads(a["path"].read_text())
            man["tune"] = a["tune"]
            a["path"].write_text(json.dumps(man, indent=2))
        elif a["type"] == "rmdir" and a["eligible"]:
            try:
                a["path"].rmdir()
            except OSError:
                pass   # defensive: should be genuinely empty whenever eligible is True
    return actions


def print_plan(actions: list[dict], *, apply: bool) -> None:
    move_verb = "MOVED" if apply else "WOULD MOVE"
    stamp_verb = "STAMPED" if apply else "WOULD STAMP"
    del_verb = "DELETED (emptied)" if apply else "WOULD DELETE (emptied)"
    for a in actions:
        if a["type"] == "move":
            print(f"{move_verb}: {a['src']} -> {a['dst']}")
        elif a["type"] == "collision":
            print(f"REFUSED (target exists, not overwritten): {a['src']} -/-> {a['dst']}")
        elif a["type"] == "leftover":
            print(f"LEFT IN PLACE (not a recognized bench artifact): {a['path']}")
        elif a["type"] == "stamp":
            print(f"{stamp_verb}: tune={a['tune']!r} -> {a['path']}")
        elif a["type"] == "stamp_error":
            print(f"SKIPPED (unparseable manifest, not touched): {a['path']}")
        elif a["type"] == "rmdir":
            print(f"{del_verb}: {a['path']}" if a["eligible"]
                 else f"KEPT (not fully migrated — see above): {a['path']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="execute the migration (default: dry-run, prints the plan only)")
    ap.add_argument("--root", default=None,
                    help="results root override (default: the shipped benchmark/results tree)")
    args = ap.parse_args(argv)
    root = Path(args.root) if args.root else paths.default_results_root()

    actions = plan(root)
    print_plan(actions, apply=args.apply)
    if args.apply:
        apply_plan(root, actions)

    n_move = sum(1 for a in actions if a["type"] == "move")
    n_collision = sum(1 for a in actions if a["type"] == "collision")
    n_leftover = sum(1 for a in actions if a["type"] == "leftover")
    n_stamp = sum(1 for a in actions if a["type"] == "stamp")
    print(f"\n{'APPLIED' if args.apply else 'DRY-RUN'}: {n_move} file(s) to move, "
          f"{n_collision} collision(s) refused, {n_leftover} unrecognized file(s) left in "
          f"place, {n_stamp} manifest(s) to stamp.")
    if not args.apply and (n_move or n_collision or n_stamp):
        print("Re-run with --apply to execute.")


if __name__ == "__main__":
    main()
