"""P426 B4-stack: write the ON registry for a P426 leg with the fork's own C203 rule (`registry_states.overlay_on`) from the
frozen build's `src/mlx-vlm/dev`, check it independently (`p426_leg.registry_delta_problems`) and record its sha256.

  .venv-bench/bin/python -m bench.p426_overlay --stack-root <frozen worktree> --entry <name> --out <registry-on.yaml>
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from bench.p426_leg import registry_delta_problems


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_registry_states(stack_root):
    """The frozen build's own module, loaded from its FILE under a unique name (B4 code round 2 H1: never a module already
    cached from another checkout, never the sibling fork); refuses a byte-level (pre-C203) one."""
    import importlib.util

    path = (Path(stack_root) / "src" / "mlx-vlm" / "dev" / "p369_phase2" / "registry_states.py").resolve()
    name = "p426_frozen_registry_states_" + hashlib.sha256(str(path).encode()).hexdigest()[:12]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or not path.is_file():
        raise RuntimeError(f"{path}: no registry_states in the frozen build")
    rs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rs)
    if Path(rs.__file__).resolve() != path:
        raise RuntimeError(f"loaded {rs.__file__}, wanted {path}")
    if not hasattr(rs, "settings"):
        raise RuntimeError(f"{path}: registry_states predates the C203 settings-level matcher")
    return rs


def build(off_text, entry, rs, fixtures_dir, out):
    out = Path(out)
    if out.exists():
        raise FileExistsError(f"{out} exists (an overlay is written once per run)")
    on_text, restored = rs.overlay_on(off_text, rs.fixture_text(fixtures_dir), entry)
    problems = registry_delta_problems(on_text, off_text, entry)
    if problems:
        raise ValueError(f"overlay refused: {problems}")
    out.write_text(on_text)
    doc = dict(entry=entry, sha256=sha256_text(on_text), off_sha256=sha256_text(off_text), restored=restored)
    Path(str(out) + ".json").write_text(json.dumps(doc, indent=1) + "\n")
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stack-root", required=True)
    ap.add_argument("--entry", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    root = Path(args.stack_root)
    rs = load_registry_states(root)
    off_text = (root / "main_models.yaml").read_bytes().decode("utf-8")  # F1: never universal-newline normalized
    doc = build(off_text, args.entry, rs, root / "src/mlx-vlm/mlx_vlm/tests/fixtures", args.out)
    print(json.dumps(doc, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
