"""P445: without STACK_WORKDIR the tg2 test root is never the repo-local `.tg2-test-tmp` (inside the stack's git tree, where
the tracked-lock guard refuses the fixtures) — the modules skip with the reason instead; the advertised full-suite commands
keep STACK_WORKDIR (C148's reason to unset it is gone)."""

import subprocess

import pytest

from bench import paths
from bench.tests import tg2_test_root as T

REPO = paths.repo_root()


def test_unset_workdir_skips_with_the_reason(monkeypatch):
    monkeypatch.delenv("STACK_WORKDIR", raising=False)
    with pytest.raises(pytest.skip.Exception, match="P445"):
        T.tg2_root()


def test_the_root_is_outside_any_git_work_tree(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    root = T.tg2_root()
    inside = subprocess.run(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
    assert inside.stdout.strip() != "true"


@pytest.mark.parametrize("name", ["test_tg2_grade.py", "test_tg2_materialize.py", "test_tg2_universe.py"])
def test_no_tg2_test_module_falls_back_into_the_repo(name):
    text = (REPO / "benchmark" / "bench" / "tests" / name).read_text()
    assert ".tg2-test-tmp" not in text and "tg2_test_root" in text


@pytest.mark.parametrize("doc", ["scripts/bootstrap_machine.sh", "benchmark/README.md"])
def test_the_advertised_full_suite_command_keeps_stack_workdir(doc):
    text = (REPO / doc).read_text().replace("\\\n", " ")
    cmds = [l for l in text.splitlines() if "bench/tests/" in l and "pytest" in l]
    assert cmds and not any("env -u STACK_WORKDIR" in l for l in cmds), cmds
