"""Run the B4b-2 golden CLI with the archived S3 Wave 1 X registry."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from bench import p426_verify as V

_REPO = Path(__file__).resolve().parents[3]
_X_COMMIT = "d4c44a9d0fc8a93a8ef1d9364650595d403edb9e"
_X_REGISTRY_SHA = "534532bb7dc0553fcafb2e33735f581e1a5f5cbcbdab42930e093e61c53711db"
_FROZEN = _REPO / "benchmark/results/m76/wave1/run/frozen.s3.json"
_X_REGISTRY = Path(__file__).with_name("fixtures") / "m76_b3_fe/x_main_models.yaml"


def _registry_bytes():
    try:
        frozen = json.loads(_FROZEN.read_bytes())
        registry = _X_REGISTRY.read_bytes()
    except (OSError, ValueError):
        raise V.RefusalError("cannot read the frozen S3 X registry fixture or record") from None
    if not isinstance(frozen, dict) or frozen.get("stack_head_x") != _X_COMMIT:
        raise V.RefusalError("frozen.s3.json does not name the archived S3 X commit")
    if hashlib.sha256(registry).hexdigest() != _X_REGISTRY_SHA or frozen.get("registry_x_sha") != _X_REGISTRY_SHA:
        raise V.RefusalError("S3 X registry fixture does not match frozen.s3.json registry_x_sha")
    return registry


def main(argv=None):
    git_bytes = V.git_bytes

    def frozen_git_bytes(top, args, what):
        if top == _REPO:
            if args == ["rev-parse", "--verify", "--quiet", f"{_X_COMMIT}^{{commit}}"] and (
                what == f"frozen stack_head_x {_X_COMMIT} does not resolve"
            ):
                return f"{_X_COMMIT}\n".encode("ascii")
            if args == ["show", f"{_X_COMMIT}:main_models.yaml"] and what == "git show stack_head_x:main_models.yaml":
                return _registry_bytes()
        return git_bytes(top, args, what)

    with patch.object(V, "git_bytes", frozen_git_bytes):
        return V.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
