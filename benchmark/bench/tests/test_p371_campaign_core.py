"""P371 phase 3a (plan 5 "Campaign freeze (P377)", C179): `bench.campaign_core` computes the CORE closures (the probe
entry's and the chain entry's static import closures, `identity_closure`) at a git ref and at the working tree, and a
chain refuses unless they are equal. Real `git` over a throw-away repository; no network, no GPU."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from bench import campaign_core as cc

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
SPECS = dict(probe_entry="benchmark/probe.py", probe_data=("benchmark/data.json",),
             chain_entry="benchmark/chains/chain_entry.py", chain_data=())


def git(repo, *args):
    got = subprocess.run(["git", *args], cwd=repo, env={**os.environ, **GIT_ENV}, capture_output=True, text=True)
    assert got.returncode == 0, got.stderr
    return got.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "r"
    for rel, text in {
            "benchmark/bench/__init__.py": "",
            "benchmark/bench/core.py": "VALUE = 1\n",
            "benchmark/bench/chain.py": "from bench import core\nVALUE = core.VALUE\n",
            "benchmark/bench/unrelated.py": "X = 1\n",
            "benchmark/probe.py": "import sys\nsys.path.insert(0, 'benchmark')\nfrom bench import core\n",
            "benchmark/chains/chain_entry.py": "from bench import chain\n",
            "benchmark/data.json": "{}\n", "README.md": "hello\n"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    git(root, "init", "-q", "-b", "main") if root.exists() else None
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "core")
    git(root, "tag", "campaign-1")
    return root


def test_the_closures_at_a_matching_tag_equal_the_current_ones(repo):
    now = cc.closure_shas(repo, **SPECS)
    at = cc.at_ref("campaign-1", repo, **SPECS)
    assert set(at) == {"tag", "commit", "probe_closure_sha256", "chain_closure_sha256"}
    assert at["tag"] == "campaign-1" and at["commit"] == git(repo, "rev-parse", "campaign-1^{commit}")
    assert at["probe_closure_sha256"] == now["probe_closure_sha256"] and at["chain_closure_sha256"] == now["chain_closure_sha256"]
    cc.require_equal(at, now)                                         # no exception


def test_a_probe_closure_member_changed_after_the_tag_refuses_and_names_it(repo):
    (repo / "benchmark/bench/core.py").write_text("VALUE = 2\n")
    at, now = cc.at_ref("campaign-1", repo, **SPECS), cc.closure_shas(repo, **SPECS)
    assert at["probe_closure_sha256"] != now["probe_closure_sha256"] and at["chain_closure_sha256"] != now["chain_closure_sha256"]
    with pytest.raises(cc.CampaignCoreMismatch, match=r"benchmark/bench/core\.py"):
        cc.require_equal(at, now, repo=repo, **SPECS)


def test_a_chain_only_member_changed_moves_only_the_chain_closure(repo):
    (repo / "benchmark/bench/chain.py").write_text("from bench import core\nVALUE = 9\n")
    at, now = cc.at_ref("campaign-1", repo, **SPECS), cc.closure_shas(repo, **SPECS)
    assert at["probe_closure_sha256"] == now["probe_closure_sha256"] and at["chain_closure_sha256"] != now["chain_closure_sha256"]
    with pytest.raises(cc.CampaignCoreMismatch, match="chain"):
        cc.require_equal(at, now)


def test_a_probe_data_file_is_part_of_the_probe_closure(repo):
    (repo / "benchmark/data.json").write_text('{"x": 1}\n')
    at, now = cc.at_ref("campaign-1", repo, **SPECS), cc.closure_shas(repo, **SPECS)
    assert at["probe_closure_sha256"] != now["probe_closure_sha256"]


def test_files_outside_both_closures_do_not_matter(repo):
    (repo / "benchmark/bench/unrelated.py").write_text("X = 2\n")
    (repo / "README.md").write_text("changed\n")
    cc.require_equal(cc.at_ref("campaign-1", repo, **SPECS), cc.closure_shas(repo, **SPECS))


def test_a_ref_that_does_not_resolve_is_an_error_not_a_pass(repo):
    with pytest.raises(cc.CampaignError, match="does not resolve"):
        cc.at_ref("no-such-tag", repo, **SPECS)


def test_the_recorded_shas_are_the_comparison_for_a_resumed_chain(repo):
    recorded = cc.at_ref("campaign-1", repo, **SPECS)
    cc.require_equal(recorded, cc.closure_shas(repo, **SPECS))
    (repo / "benchmark/bench/core.py").write_text("VALUE = 3\n")
    with pytest.raises(cc.CampaignCoreMismatch):
        cc.require_equal(recorded, cc.closure_shas(repo, **SPECS))
