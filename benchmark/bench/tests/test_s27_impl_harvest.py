"""S27 §7: the harvest records a link in a run's private state as an excluded entry (never followed, target portable); a PAUSED
leg is never harvested; the tg2 view omits every javascript `package-lock.json` the prepared tree does not hold."""
from __future__ import annotations

import os

from bench import corpus_tg2
from bench import p426_harvest as hv


def run_tree(wd, run_id="20261119T120000-abcdefabcdef"):
    run = wd / "opencode-probe-v2" / f"run-{run_id}"
    bin_dir = run / "home" / ".npm" / "_npx" / "1415fee72ff6294b" / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    (bin_dir.parent / "jest" / "bin").mkdir(parents=True)
    (bin_dir.parent / "jest" / "bin" / "jest.js").write_text("// jest\n")
    os.symlink("../jest/bin/jest.js", bin_dir / "jest")                           # the npx cache's relative link
    os.symlink(str(run / "home" / ".npm"), bin_dir / "abs-link")                  # an absolute link into the run's home
    return run, bin_dir


def test_the_npx_cache_links_are_excluded_entries_with_portable_targets(tmp_path):
    wd = tmp_path / "wd"
    leg = tmp_path / "leg"
    leg.mkdir()
    run, bin_dir = run_tree(wd)
    (leg / "x.manifest.json").write_text('{"run_id": "20261119T120000-abcdefabcdef"}')
    problems = []
    inv, _ = hv._inventory(leg, wd, problems)
    assert not [p for p in problems if "symlink" in p], problems
    links = {e.rel: e for e in inv.values() if e.reason == "symlink"}
    rel = "home/.npm/_npx/1415fee72ff6294b/node_modules/.bin/jest"
    assert links[rel].dest == "excluded" and links[rel].link == "../jest/bin/jest.js"
    assert all(e.reason != "private_state" for e in links.values())                # a link is never private_state
    assert hv.portable_link(os.readlink(bin_dir / "abs-link"), wd).startswith("$STACK_WORKDIR/opencode-probe-v2/")


def test_a_link_target_that_still_names_a_box_path_is_recorded_as_basename_and_sha256(tmp_path):
    out = hv.portable_link("/opt/elsewhere/tool.js", tmp_path / "wd", home=tmp_path / "home")
    assert out["basename"] == "tool.js" and len(out["sha256"]) == 64


def test_a_symlink_outside_the_private_dirs_still_refuses(tmp_path):
    wd = tmp_path / "wd"
    leg = tmp_path / "leg"
    leg.mkdir()
    run, _ = run_tree(wd)
    (run / "grading-private").mkdir()
    os.symlink("/etc/hosts", run / "grading-private" / "link.json")
    (leg / "x.manifest.json").write_text('{"run_id": "20261119T120000-abcdefabcdef"}')
    problems = []
    hv._inventory(leg, wd, problems)
    assert any("grading-private/link.json" in p and "symlink" in p for p in problems)


def test_a_paused_leg_is_a_known_state_that_is_never_harvested():
    assert "PAUSED" in hv.LEG_STATES and "PAUSED" in hv.NEVER_HARVESTED


# -------------------------------------------------------------------------------- §7.2 the tg2 view
def tree(tmp_path, files):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def test_the_recorded_pilot_shape_root_lock_is_omitted(tmp_path):
    work = tree(tmp_path / "w", {"word-search.js": "x", "word-search.spec.js": "t", "package.json": "{}",
                                 "package-lock.json": "{}"})
    view = corpus_tg2.view_manifest(work, {"word-search.js": "a", "word-search.spec.js": "b", "package.json": "c"},
                                    "javascript")
    assert "package-lock.json" not in view and "word-search.js" in view


def test_a_nested_lock_absent_from_the_prepared_tree_is_omitted(tmp_path):
    work = tree(tmp_path / "w", {"a.js": "x", "lib/package-lock.json": "{}", "package-lock.json": "{}"})
    view = corpus_tg2.view_manifest(work, {"a.js": "a", "package-lock.json": "p"}, "javascript")
    assert "lib/package-lock.json" not in view and "package-lock.json" in view          # a prepared lock stays in view


def test_other_languages_keep_a_package_lock(tmp_path):
    work = tree(tmp_path / "w", {"a.rs": "x", "package-lock.json": "{}"})
    assert "package-lock.json" in corpus_tg2.view_manifest(work, {"a.rs": "a"}, "rust")
