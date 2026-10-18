"""P371 review r1 F1: `campaign_core.at_ref` computes the closures INSIDE its extracted temp tree. The REAL git path (no
monkeypatched `at_ref`, no fake `Campaign`): a throw-away repo with a real tag, the closure recipe asked where the tree
must still exist, and the repository's own tg1 / M64 core specs at HEAD."""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
from pathlib import Path

import pytest

from bench import campaign_core as cc
from bench import identity_closure as ic

REPO = Path(__file__).resolve().parents[3]
GIT_ENV = dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.invalid")


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, env={**os.environ, **GIT_ENV}, capture_output=True, text=True,
                          check=True).stdout.strip()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, REPO / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_closures_are_computed_while_the_extracted_tree_exists(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "benchmark").mkdir(parents=True)
    (repo / "benchmark/probe.py").write_text("import json\n")
    (repo / "benchmark/chain.py").write_text("import json\n")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "core")
    git(repo, "tag", "t1")
    seen = []
    real = ic.closure_sha256

    def spy(entry, root, data=()):
        seen.append((Path(root).is_dir(), (Path(root) / entry).is_file()))
        return real(entry, root, data=data)

    monkeypatch.setattr(ic, "closure_sha256", spy)
    at = cc.Campaign(repo, probe_entry="benchmark/probe.py", chain_entry="benchmark/chain.py").at_ref("t1")
    assert seen == [(True, True), (True, True)] and at["commit"] == git(repo, "rev-parse", "t1^{commit}")


@pytest.mark.parametrize("entry,name", [("benchmark/chains/c147/run_tg1_chain.py", "tg1"),
                                        ("benchmark/chains/m64/run_m64_chain.py", "m64")])
def test_the_repositorys_own_core_specs_resolve_at_head_through_real_git(entry, name):
    mod = load(entry, "r1_" + name)
    specs = mod.CORE_SPECS if name == "tg1" else mod.core_specs(["oc"])
    at = cc.Campaign(REPO, **specs).at_ref("HEAD")
    assert at["commit"] == git(REPO, "rev-parse", "HEAD")
    assert re.fullmatch("[0-9a-f]{64}", at["chain_closure_sha256"])
    probes = at.get("probe_closures") or {"probe": at["probe_closure_sha256"]}
    assert probes and all(re.fullmatch("[0-9a-f]{64}", v) for v in probes.values())
