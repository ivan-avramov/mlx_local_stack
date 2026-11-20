"""S27 (spec v1.4, section 7, acceptance 10.1) -- blind test-writer, delivery 1: the harvest of a run's private links (D3) and the
tg2 work-tree view of a JavaScript lock file (C368 (1)).

Class of each test: (a) reproduces a failure the spec fixes, (b) preserves an invariant, (c) exercises new behaviour.

Interface assumptions:
  V1  `p426_harvest._inventory(leg_root, workdir, problems)` returns `(inv, roots)`; an excluded link is
      `Entry(dest="excluded", reason="symlink", link=<recorded target>)` (the baseline's own shape for a final-tree link) and
      appends nothing to `problems`;
  V2  the recorded target never carries the box path: either the portable form (`$STACK_WORKDIR/...`) or, when the portable form
      still carries a box path, the target's basename plus a sha256 (the test accepts either, and refuses the box path);
  V3  the npx cache lives under the run's `home` (`home/.npm/_npx/<hash>/node_modules/...`), one of the five private dirs.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from bench import corpus_tg2 as ct
from bench import p426_harvest as H

RUN_ID = "20261119T180000-aaaaaaaaaaaa"


# ------------------------------------------------------------------------------------------------ the harvest inventory (7.1)
@pytest.fixture
def world(tmp_path):
    wd = tmp_path / "wd"
    run = wd / "opencode-probe" / f"run-{RUN_ID}"
    run.mkdir(parents=True)
    leg = tmp_path / "leg.a1"
    (leg / "s1").mkdir(parents=True)
    (leg / "s1" / "x.manifest.json").write_text(json.dumps(dict(run_id=RUN_ID)))
    return dict(wd=wd, run=run, leg=leg, tmp=tmp_path)


def inventory(w):
    problems = []
    inv, _roots = H._inventory(w["leg"], w["wd"], problems)
    return inv, problems


def link(path, target, *, directory=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target, target_is_directory=directory)


def entry_of(inv, rel):
    return inv.get(f"run:{RUN_ID}/{rel}")


def test_an_npx_cache_link_under_the_run_home_is_an_excluded_entry_not_a_refusal(world):
    """(a) The baseline appends `a symlink outside a final tree (never followed)` to the problems and the harvest fails."""
    pkg = world["run"] / "home/.npm/_npx/abc123/node_modules/pkg/bin/cli.js"
    pkg.parent.mkdir(parents=True)
    pkg.write_text("#!/usr/bin/env node\n")
    rel = "home/.npm/_npx/abc123/node_modules/.bin/pkg"
    link(world["run"] / rel, "../pkg/bin/cli.js")
    inv, problems = inventory(world)
    assert problems == [], problems
    e = entry_of(inv, rel)
    assert e is not None and e.dest == "excluded" and e.reason == "symlink" and e.reason != "private_state"


@pytest.mark.parametrize("private", ["home", "data", "state", "cache", "tmp"])
def test_every_private_dir_of_a_run_may_hold_links(world, private):
    """(c) spec 7.1: home, data, state, cache, tmp."""
    outside = world["tmp"] / "elsewhere"
    outside.mkdir()
    rel = f"{private}/x/link"
    link(world["run"] / rel, outside / "file")
    inv, problems = inventory(world)
    assert problems == [] and entry_of(inv, rel).reason == "symlink"


def test_the_recorded_target_never_carries_the_box_path(world):
    """(a) V2, a target inside the workdir: the portable scrubber's form."""
    target = world["run"] / "home/.npm/_npx/abc123/node_modules/pkg/bin/cli.js"
    rel = "home/.npm/_npx/abc123/node_modules/.bin/pkg"
    link(world["run"] / rel, str(target))                                   # an absolute target, as npx writes it
    inv, problems = inventory(world)
    e = entry_of(inv, rel)
    assert problems == [] and e.link                                      # (the scrub itself runs at publication)
    recorded = H.portable_link(e.link, world["wd"])                       # v2: the candidate's helper for the recorded form
    assert isinstance(recorded, str) and recorded.startswith("$STACK_WORKDIR/")
    assert str(world["wd"]) not in recorded and str(world["tmp"]) not in recorded


def test_a_target_outside_the_workdir_is_recorded_as_basename_and_sha256(world):
    """(a) V2: a box path the portable scrubber cannot express -> basename + sha256 of the raw target, never the path."""
    outside = world["tmp"] / "elsewhere" / "nested" / "cli.js"
    rel = "home/.npm/_npx/abc123/node_modules/.bin/pkg"
    link(world["run"] / rel, str(outside))
    inv, problems = inventory(world)
    e = entry_of(inv, rel)
    assert problems == [] and e.link
    recorded = H.portable_link(e.link, world["wd"])
    # a target outside the workdir: a portable `$HOME/...` form when it lies under the box's home (as this scratch does), else
    # the basename + sha256 of the raw target; never an absolute box path
    if isinstance(recorded, dict):
        assert recorded == dict(basename="cli.js", sha256=hashlib.sha256(str(outside).encode()).hexdigest())
    else:
        assert recorded.startswith("$")
    assert str(world["tmp"]) not in json.dumps(recorded)


def test_a_directory_link_is_listed_and_never_followed(world):
    """(b) The target directory's files never enter the inventory."""
    secret_dir = world["tmp"] / "elsewhere"
    secret_dir.mkdir()
    (secret_dir / "secret.txt").write_text("do not publish")
    rel = "home/.npm/_npx/abc123/node_modules/pkg"
    link(world["run"] / rel, str(secret_dir), directory=True)
    inv, problems = inventory(world)
    assert problems == [] and entry_of(inv, rel).reason == "symlink"
    assert not [s for s in inv if "secret.txt" in s]


def test_regular_files_of_the_private_dirs_stay_excluded_as_private_state(world):
    """(b) unchanged: a regular file under `home` is `private_state`."""
    f = world["run"] / "home/.npm/_logs/x.log"
    f.parent.mkdir(parents=True)
    f.write_text("log")
    inv, problems = inventory(world)
    assert problems == []
    e = entry_of(inv, "home/.npm/_logs/x.log")
    assert e.dest == "excluded" and e.reason == "private_state"


def test_a_link_outside_the_private_dirs_is_still_a_refusal(world):
    """(b) `grading-private`, `cfg` and the evidence roots keep the baseline rule: a symlink there fails the harvest."""
    link(world["run"] / "grading-private/x/report.json", str(world["tmp"] / "elsewhere"))
    inv, problems = inventory(world)
    assert any("symlink" in p for p in problems)


def test_a_link_in_the_leg_root_is_still_a_refusal(world):
    """(b)"""
    link(world["leg"] / "s1" / "linked.log", str(world["tmp"] / "elsewhere"))
    inv, problems = inventory(world)
    assert any("symlink" in p for p in problems)


def test_the_excluded_link_is_recorded_with_its_target_in_the_entry_record(world):
    """(c) The published record of the entry (`Entry.record()`) carries `link_target` and the exclusion reason."""
    rel = "home/.npm/_npx/abc123/node_modules/.bin/pkg"
    link(world["run"] / rel, "../pkg/bin/cli.js")
    inv, _ = inventory(world)
    rec = entry_of(inv, rel).record()
    assert rec["destination"] == "excluded" and rec["exclusion_reason"] == "symlink" and rec["link_target"]


# ------------------------------------------------------------------------------------------------ the tg2 view of a JavaScript tree (7.2)
def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def tree(tmp_path):
    work = tmp_path / "work"
    (work / "src").mkdir(parents=True)
    (work / "package.json").write_text("{}")
    (work / "src" / "a.js").write_text("a")
    prepared = {"package.json": sha("{}"), "src/a.js": sha("a")}
    return work, prepared


def test_a_top_level_lock_absent_from_the_prepared_tree_is_omitted_for_javascript(tree):
    """(a) The baseline hands `package-lock.json` (written by `npm install`) to the manifest and the snapshot, so the model's own
    build breaks the snapshot / tamper comparison."""
    work, prepared = tree
    (work / "package-lock.json").write_text('{"lockfileVersion": 3}')
    view = ct.view_manifest(work, prepared, "javascript")
    assert "package-lock.json" not in view
    assert set(view) == {"package.json", "src/a.js"}


def test_a_nested_lock_absent_from_the_prepared_tree_is_omitted_too(tree):
    """(a) 'every package-lock.json absent from the prepared tree': a nested one included."""
    work, prepared = tree
    (work / "src" / "package-lock.json").write_text("{}")
    (work / "sub" / "deep").mkdir(parents=True)
    (work / "sub" / "deep" / "package-lock.json").write_text("{}")
    (work / "sub" / "deep" / "b.js").write_text("b")
    view = ct.view_manifest(work, prepared, "javascript")
    assert not [r for r in view if r.endswith("package-lock.json")]
    assert "sub/deep/b.js" in view and "src/a.js" in view


def test_a_lock_that_the_prepared_tree_holds_stays_in_the_view(tree):
    """(b) only locks ABSENT from the prepared tree are omitted: the prepared lock is a protected input."""
    work, prepared = tree
    (work / "package-lock.json").write_text("{}")
    prepared = dict(prepared, **{"package-lock.json": sha("{}")})
    assert "package-lock.json" in ct.view_manifest(work, prepared, "javascript")


def test_the_view_still_names_a_changed_prepared_lock(tree):
    """(b) a prepared lock the model edited is a difference the tamper check must still see (content hash differs)."""
    work, prepared = tree
    (work / "package-lock.json").write_text('{"edited": true}')
    prepared = dict(prepared, **{"package-lock.json": sha("{}")})
    view = ct.view_manifest(work, prepared, "javascript")
    assert view["package-lock.json"] != prepared["package-lock.json"]


@pytest.mark.parametrize("lang", ["java", "cpp", "rust"])
def test_other_languages_keep_a_package_lock_in_the_view(tree, lang):
    """(b) the rule is JavaScript's: another language's stray `package-lock.json` is still the model's file."""
    work, prepared = tree
    (work / "package-lock.json").write_text("{}")
    assert "package-lock.json" in ct.view_manifest(work, prepared, lang)


def test_rust_still_omits_a_cargo_lock_absent_from_the_prepared_tree(tmp_path):
    """(b) the analogue the spec cites is unchanged."""
    work = tmp_path / "w"
    work.mkdir()
    (work / "Cargo.toml").write_text("[package]")
    (work / "Cargo.lock").write_text("lock")
    view = ct.view_manifest(work, {"Cargo.toml": sha("[package]")}, "rust")
    assert "Cargo.lock" not in view and "Cargo.toml" in view


def test_javascript_still_refuses_a_symlink_in_the_work_tree(tree):
    """(b) the view's refusals are not loosened by the lock rule."""
    work, prepared = tree
    os.symlink(work / "src" / "a.js", work / "link.js")
    with pytest.raises(ValueError):
        ct.view_manifest(work, prepared, "javascript")


# ------------------------------------------------------------------------------------------------ the PAUSED leg state (5.7)
def test_a_paused_leg_state_is_added_to_the_harvest_rule_table():
    """(c) 'a PAUSED leg state (held, not finished) is added to LEG_STATES' (the harvest's rule table)."""
    assert "PAUSED" in H.LEG_STATES
    assert set(H.LEG_STATES) >= {"VALID", "VALID_WITH_DNF", "INVALID", "NOT_STARTED", "OVERRUN"}
