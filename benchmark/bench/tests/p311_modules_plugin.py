"""pytest plugin for the P311-lite closure test (spec 3b): dump the repo-local modules loaded by a run. TESTS ONLY."""
import json
import os
import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _no_docker(monkeypatch):
    from bench import toolchain
    monkeypatch.setattr(toolchain, "grader_image_id", lambda: "sha256:" + "f" * 64)


def pytest_sessionfinish(session, exitstatus):
    repo = Path(os.environ["P311_REPO"]).resolve()
    found = set()
    for module in list(sys.modules.values()):
        file = getattr(module, "__file__", None)
        if not file:
            continue
        path = Path(file).resolve()
        if path.is_relative_to(repo):
            found.add(path.relative_to(repo).as_posix())
    Path(os.environ["P311_MODULES_OUT"]).write_text(json.dumps(sorted(found)))
