"""P426 B4-stack: write the ON registry for a P426 leg with the fork's own C203 rule (`registry_states.overlay_on`) from the
frozen build's `src/mlx-vlm/dev`, check it independently (`p426_leg.registry_delta_problems`) and record its sha256.

  .venv-bench/bin/python -m bench.p426_overlay --stack-root <frozen worktree> --entry <name> --out <registry-on.yaml>
"""

import argparse
import hashlib
import importlib
import json
import sys
from pathlib import Path

from bench.p426_leg import registry_delta_problems


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_registry_states(stack_root):
    """The frozen build's own module (never the sibling fork checkout); refuses a byte-level (pre-C203) one."""
    dev = str(Path(stack_root) / "src" / "mlx-vlm" / "dev")
    sys.path.insert(0, dev)
    try:
        rs = importlib.import_module("p369_phase2.registry_states")
    finally:
        sys.path.remove(dev)
    if not hasattr(rs, "settings"):
        raise RuntimeError(f"{dev}: registry_states predates the C203 settings-level matcher")
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
    doc = build((root / "main_models.yaml").read_text(), args.entry, rs, root / "src/mlx-vlm/mlx_vlm/tests/fixtures", args.out)
    print(json.dumps(doc, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
