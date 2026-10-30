"""P426 B2 frozen tests, delivery 1d: the `RECORD` re-verification (spec v3.2 §6.4, §16.5
`ChainOps.interpreter_inventory(pid, site_packages=<path>)`).

Classes: [FIX] reproduces a failure the spec fixes; [INV] preserves an invariant; [NEW] exercises new behaviour (all NEW here).
A real `ChainOps` with inert shell / process seams (`b2_frozen_add_support.chain_ops`) over a fixture `site-packages`
(`site_tree`: one installed distribution with a pip-format RECORD, one editable with the venv's `direct_url.json` shape)."""
from __future__ import annotations

import os
import re

import pytest

from bench.tests import b2_frozen_add_support as A


def inventory(tmp_path, tree):
    ops = A.chain_ops(tmp_path)
    assert hasattr(ops, "interpreter_inventory"), "ChainOps.interpreter_inventory (§16.2) is missing"
    return ops.interpreter_inventory(os.getpid(), site_packages=tree)


def test_new_an_intact_tree_yields_a_stable_inventory_hash(tmp_path):
    tree = A.site_tree(tmp_path / "sp", worktree=tmp_path / "WT")
    a, b = inventory(tmp_path, tree), inventory(tmp_path, tree)
    assert re.fullmatch(r"[0-9a-f]{64}", a["inventory_sha256"]) and a["inventory_sha256"] == b["inventory_sha256"]


def test_fix_an_installed_file_mutated_without_its_record_refuses(tmp_path):
    tree = A.site_tree(tmp_path / "sp", worktree=tmp_path / "WT")
    inventory(tmp_path, tree)
    (tree / "fakepkg/core.py").write_bytes(b"def f():\n    return 3\n")
    with pytest.raises(Exception) as e:
        inventory(tmp_path, tree)
    assert not isinstance(e.value, (AssertionError, TypeError, AttributeError))


def test_new_a_changed_installed_file_with_a_matching_record_changes_the_hash(tmp_path):
    a = inventory(tmp_path, A.site_tree(tmp_path / "a", worktree=tmp_path / "WT"))["inventory_sha256"]
    b = inventory(tmp_path, A.site_tree(tmp_path / "b", worktree=tmp_path / "WT",
                                        files={"fakepkg/__init__.py": b"VALUE = 2\n",
                                               "fakepkg/core.py": b"def f():\n    return 2\n"}))["inventory_sha256"]
    assert a != b


def test_new_editable_metadata_differing_only_in_worktree_path_gives_the_same_hash(tmp_path):
    a = inventory(tmp_path, A.site_tree(tmp_path / "a", worktree="/Users/x/stack-p426-off"))  # allow-pii-pattern
    b = inventory(tmp_path, A.site_tree(tmp_path / "b", worktree="/Users/x/stack-p426-on"))  # allow-pii-pattern
    assert a["inventory_sha256"] == b["inventory_sha256"]
