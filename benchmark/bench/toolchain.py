"""Runtime toolchain identity of a tg1 process (P311-lite, P23): what the closure hash cannot see.

The probe's code identity is its static import closure (`bench.identity_closure`); the interpreter, the locked
third-party packages and the grader container image also determine what a row means (graders run in the image).
`current()` is recorded in the scaffold policy; a missing image or a changed lock / interpreter / image refuses."""
from __future__ import annotations

import hashlib
import platform
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOCK = REPO / "benchmark/requirements-bench.lock"
GRADER_IMAGE = "aider-benchmark"      # as structured_grade / opencode_common run it
IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")


class ToolchainError(ValueError):
    """The toolchain is missing or differs from the one recorded."""


def lock_sha256():
    try:
        return hashlib.sha256(LOCK.read_bytes()).hexdigest()
    except OSError as exc:
        raise ToolchainError(f"bench lock {LOCK.name} unreadable: {exc}") from exc


def interpreter_version():
    return f"{platform.python_implementation()} {platform.python_version()}"


def docker_image_id(image=GRADER_IMAGE, run=subprocess.run):
    """The local image id (`sha256:<64 hex>`); a missing docker binary, daemon, image or malformed answer refuses."""
    try:
        got = run(["docker", "image", "inspect", image, "--format", "{{.Id}}"],
                  capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolchainError(f"cannot inspect grader image {image}: {type(exc).__name__}") from exc
    out = (got.stdout or "").strip()
    if got.returncode != 0 or not IMAGE_ID.match(out):
        raise ToolchainError(f"grader image {image} is missing or unreadable (rc {got.returncode})")
    return out


def grader_image_id():
    return docker_image_id()


def current():
    return {"lock_sha256": lock_sha256(), "interpreter": interpreter_version(), "grader_image_id": grader_image_id()}


def verify(expected):
    """Refuse unless the toolchain now equals `expected` (the dict recorded in the scaffold policy)."""
    now = current()
    drifted = sorted(k for k in set(now) | set(expected or {}) if now.get(k) != (expected or {}).get(k))
    if drifted:
        raise ToolchainError("toolchain drift: " + ", ".join(drifted))
    return now
