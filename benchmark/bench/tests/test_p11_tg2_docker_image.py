"""Unit contract for selecting the tg2 integration-test grader without Docker."""

import builtins
import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest


ENV = "MLX_STACK_TG2_TEST_IMAGE"
IMAGE = "sha256:" + "ab" * 32
RECORD = Path(__file__).resolve().parents[2] / "m65/tg2_image/IMAGE_ID"


@pytest.fixture
def select(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    from bench.tests.tg2_docker_image import configured_image

    return configured_image


@pytest.fixture
def image_info():
    fields = dict(line.split("=", 1) for line in RECORD.read_text().splitlines() if "=" in line)
    return {
        "Id": IMAGE,
        "Config": {"Labels": {
            "tg2.version": "m65-v1",
            "tg2.polyglot_sha": fields["polyglot_sha"],
            "tg2.context_sha256": fields["context_sha256"],
        }},
    }


def unexpected(*args, **kwargs):
    pytest.fail(f"Unexpected side effect: {args[:1]!r}")


def install_inspect(monkeypatch, stdout="", returncode=0, error=None):
    monkeypatch.setenv(ENV, IMAGE)
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    calls = []

    def run(argv, **kwargs):
        assert Path(argv[0]).name == "docker"
        assert "inspect" in argv and argv[-1] == IMAGE
        assert 0 < kwargs["timeout"] <= 60
        calls.append(argv)
        if error is not None:
            raise error
        if returncode and kwargs.get("check"):
            raise subprocess.CalledProcessError(returncode, argv, stderr="image unavailable")
        return subprocess.CompletedProcess(argv, returncode, stdout, "image unavailable" if returncode else "")

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_unconfigured_has_no_side_effects(select, monkeypatch):
    monkeypatch.setattr(subprocess, "run", unexpected)
    monkeypatch.setattr(shutil, "which", unexpected)
    monkeypatch.setattr(builtins, "open", unexpected)
    monkeypatch.setattr(io, "open", unexpected)
    assert select() is None


@pytest.mark.parametrize("value", [
    "", "tg2-grader:latest", "ab" * 32, "sha256:" + "AB" * 32,
    IMAGE[:-1], IMAGE + "0", IMAGE + "\n", " " + IMAGE, IMAGE[:-1] + "g",
])
def test_invalid_override_refused_before_docker(select, monkeypatch, value):
    monkeypatch.setenv(ENV, value)
    monkeypatch.setattr(subprocess, "run", unexpected)
    with pytest.raises(RuntimeError, match=r"\S"):
        select()


def test_valid_local_image_selected(select, monkeypatch, image_info):
    calls = install_inspect(monkeypatch, json.dumps([image_info]))
    assert select() == IMAGE
    assert calls


@pytest.mark.parametrize("label", ["tg2.version", "tg2.polyglot_sha", "tg2.context_sha256"])
@pytest.mark.parametrize("missing", [False, True])
def test_every_label_required(select, monkeypatch, image_info, label, missing):
    labels = image_info["Config"]["Labels"]
    if missing:
        del labels[label]
    else:
        labels[label] = "wrong"
    install_inspect(monkeypatch, json.dumps([image_info]))
    with pytest.raises(RuntimeError, match=r"\S"):
        select()


@pytest.mark.parametrize("key,value", [
    ("Id", None), ("Id", "sha256:" + "cd" * 32), ("Config", None),
    ("Config", {}), ("Config", {"Labels": None}), ("Config", {"Labels": []}),
])
def test_unusable_inspected_identity_refused(select, monkeypatch, image_info, key, value):
    image_info[key] = value
    install_inspect(monkeypatch, json.dumps([image_info]))
    with pytest.raises(RuntimeError, match=r"\S"):
        select()


@pytest.mark.parametrize("stdout", ["", "not json", "[]", "null", "[null]"])
def test_malformed_inspect_refused(select, monkeypatch, stdout):
    install_inspect(monkeypatch, stdout)
    with pytest.raises(RuntimeError, match=r"\S"):
        select()


@pytest.mark.parametrize("error", [None, FileNotFoundError(), subprocess.TimeoutExpired("docker", 5)])
def test_unavailable_local_image_or_daemon_refused(select, monkeypatch, error):
    install_inspect(monkeypatch, returncode=1, error=error)
    with pytest.raises(RuntimeError, match=r"\S"):
        select()


@pytest.mark.parametrize("field", ["polyglot_sha", "context_sha256"])
def test_missing_expected_metadata_refused(select, monkeypatch, image_info, field):
    shortened = "\n".join(line for line in RECORD.read_text().splitlines() if not line.startswith(field + "="))
    real_open = io.open

    def open_record(path, mode="r", *args, **kwargs):
        if Path(path).name == "IMAGE_ID":
            return io.BytesIO(shortened.encode()) if "b" in mode else io.StringIO(shortened)
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(io, "open", open_record)
    monkeypatch.setattr(builtins, "open", open_record)
    install_inspect(monkeypatch, json.dumps([image_info]))
    with pytest.raises(RuntimeError, match=r"\S"):
        select()
