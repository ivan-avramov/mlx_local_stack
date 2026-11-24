"""Opt-in local image selection for the live tg2 Docker integration tests."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from bench.tg2_grade import IMAGE_ID_FILE


def _expected_labels():
    try:
        lines = IMAGE_ID_FILE.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise RuntimeError("cannot read tg2 image metadata from the committed IMAGE_ID record") from exc
    labels = {"tg2.version": "m65-v1"}
    for key, length in (("polyglot_sha", 40), ("context_sha256", 64)):
        values = [line.partition("=")[2] for line in lines[1:] if line.startswith(key + "=")]
        if len(values) != 1 or not re.fullmatch(rf"[0-9a-f]{{{length}}}", values[0]):
            raise RuntimeError(f"missing or invalid {key} metadata in the committed tg2 IMAGE_ID record")
        labels[f"tg2.{key}"] = values[0]
    return labels


def configured_image() -> str | None:
    """Return the verified local image ID when MLX_STACK_TG2_TEST_IMAGE is set."""
    image_id = os.environ.get("MLX_STACK_TG2_TEST_IMAGE")
    if image_id is None:
        return None
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise RuntimeError("MLX_STACK_TG2_TEST_IMAGE requires a full lowercase sha256:<64 hex> Docker image ID")

    expected_labels = _expected_labels()
    docker = shutil.which("docker") or str(Path.home() / ".orbstack/bin/docker")
    try:
        result = subprocess.run([docker, "image", "inspect", image_id], capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Docker image inspect timed out for MLX_STACK_TG2_TEST_IMAGE={image_id}") from exc
    except OSError as exc:
        raise RuntimeError("cannot run Docker image inspect for MLX_STACK_TG2_TEST_IMAGE") from exc
    except UnicodeError as exc:
        raise RuntimeError("invalid response from Docker image inspect for MLX_STACK_TG2_TEST_IMAGE") from exc
    if result.returncode:
        raise RuntimeError(
            f"Docker image inspect failed for MLX_STACK_TG2_TEST_IMAGE={image_id} (exit {result.returncode}). "
            "Check that Docker is running and the image exists locally."
        )

    try:
        images = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("invalid JSON from Docker image inspect for MLX_STACK_TG2_TEST_IMAGE") from exc
    if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], dict):
        raise RuntimeError("expected one image object from Docker image inspect for MLX_STACK_TG2_TEST_IMAGE")

    image = images[0]
    if image.get("Id") != image_id:
        raise RuntimeError(f"Docker image inspect returned an ID that does not match MLX_STACK_TG2_TEST_IMAGE={image_id}")
    config = image.get("Config")
    labels = config.get("Labels") if isinstance(config, dict) else None
    if not isinstance(labels, dict):
        raise RuntimeError(f"Docker image {image_id} has no valid labels")
    for key, expected in expected_labels.items():
        if labels.get(key) != expected:
            raise RuntimeError(f"Docker image {image_id} is missing label {key} or it does not match {expected}")
    return image_id
