"""P627 (`docs/specs/p627-gate-absent-skips.md` v1): a baseline-listed test whose test FILE is absent from the gated tree but
present in the policy (live) tree is recorded in `baseline_skips_absent`, not a failure; every other skip difference fails as
before (C277 included). The runner is mocked (the JunitRunner fake of test_local_gate_ran_skips); the real gate is never run.
The gated tree is the clone at `sha`; the live tree is the repo directory (a later commit adds the file there)."""

import json
import subprocess
from pathlib import Path

import pytest

from bench import local_gate as G
from bench.tests.test_local_gate import _repo
from bench.tests.test_local_gate_ran_skips import LIVE_ORIGIN, JunitRunner, _id

BASE_FILES = {"pyproject.toml": "[project]\nname='x'\n", "uv.lock": "x\n"}
A = ("pkg.tests.test_a", "test_one")  # file pkg/tests/test_a.py
B = ("pkg.tests.test_b", "test_two")  # file pkg/tests/test_b.py
B2 = ("pkg.tests.test_b", "test_three")  # same file as B
K = ("pkg.tests.test_k.TestKlass", "test_m")  # class method -> pkg/tests/test_k.py
N = ("pkg.tests.test_k.TestKlass.Inner", "test_n")  # nested class -> pkg/tests/test_k.py
REAL = ("benchmark.bench.tests.test_b2_frozen_s0_support", "test_x")  # the P627 motivating shape
FILE = {A: "pkg/tests/test_a.py", B: "pkg/tests/test_b.py", B2: "pkg/tests/test_b.py", K: "pkg/tests/test_k.py",
        N: "pkg/tests/test_k.py", REAL: "benchmark/bench/tests/test_b2_frozen_s0_support.py"}


def _git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True).stdout.strip()


def _world(tmp_path, in_gated=(), in_live=()):
    """A live repo whose commit `sha` holds the `in_gated` files; afterwards a commit (and so the working tree) adds the
    `in_live` files. A file in both is committed in `sha` and stays in live."""
    live = tmp_path / "live" / "mlx-serve"
    files = dict(BASE_FILES)
    files.update({FILE[c]: "def test(): pass\n" for c in in_gated})
    sha = _repo(live, files, origin=LIVE_ORIGIN)
    later = {FILE[c] for c in in_live} - {FILE[c] for c in in_gated}
    for rel in later:
        (live / rel).parent.mkdir(parents=True, exist_ok=True)
        (live / rel).write_text("def test(): pass\n")
    if later:
        _git(live, "add", "-A")
        _git(live, "commit", "-q", "-m", "later: add test files")
    baselines = tmp_path / "baselines"
    baselines.mkdir()
    return dict(tmp=tmp_path, live=live, sha=sha, gate=tmp_path / "gate", baselines=baselines)


def _gate(env, baseline, runner_cls=JunitRunner, **runner_kw):
    """baseline: list of cases / raw id strings, or None for no file."""
    path = env["baselines"] / "mlx-serve.skips.txt"
    if baseline is not None:
        path.write_text("".join(f"{c if isinstance(c, str) else _id(c)}\n" for c in baseline))
    r = runner_cls(**runner_kw)
    receipt = G.run("mlx-serve", env["sha"], live=env["live"], gate_dir=env["gate"], baselines=env["baselines"], runner=r,
                    busy=lambda: [], dirty=r.dirty, artifacts=lambda d: True)
    return json.loads(Path(receipt).read_text())


def _problems(doc):
    return " | ".join(doc["problems"])


NEITHER = "baseline skip neither skipped nor passed: "


# ------------------------------------------------------------------ absent in gated, present in live -> recorded
# reproduces-failure: at the baseline this is FAIL ("neither skipped nor passed"); after the change a PASS
def test_a_baseline_entry_whose_file_is_absent_in_gated_and_present_in_live_passes(tmp_path):
    doc = _gate(_world(tmp_path, in_gated=[], in_live=[A]), [A], skipped=[], passed=[])
    assert doc["verdict"] == "PASS" and doc["problems"] == []


# new-behaviour
def test_the_absent_entry_is_listed_in_baseline_skips_absent_and_not_in_the_other_lists(tmp_path):
    doc = _gate(_world(tmp_path, in_live=[A]), [A], skipped=[], passed=[])
    assert doc["baseline_skips_absent"] == [_id(A)]
    assert doc["baseline_skips_ran"] == [] and doc["skipped_tests"] == []


# new-behaviour: two entries of one absent file (the 8055b219 shape), listed sorted
def test_two_entries_of_one_absent_file_are_listed_sorted(tmp_path):
    doc = _gate(_world(tmp_path, in_live=[B]), [B, B2], skipped=[], passed=[])
    assert doc["verdict"] == "PASS"
    assert doc["baseline_skips_absent"] == sorted([_id(B), _id(B2)])


# new-behaviour: the repo-top-relative path under benchmark/ resolves from the dotted module
def test_the_motivating_benchmark_bench_tests_shape_resolves(tmp_path):
    doc = _gate(_world(tmp_path, in_live=[REAL]), [REAL], skipped=[], passed=[])
    assert doc["verdict"] == "PASS" and doc["baseline_skips_absent"] == [_id(REAL)]


# new-behaviour
def test_entries_from_several_absent_files_are_all_listed_sorted(tmp_path):
    doc = _gate(_world(tmp_path, in_live=[B, A]), [B, A], skipped=[], passed=[])
    assert doc["verdict"] == "PASS" and doc["baseline_skips_absent"] == [_id(A), _id(B)]


# ------------------------------------------------------------------ the key is always present
# new-behaviour
def test_the_key_is_an_empty_list_on_a_plain_pass(tmp_path):
    doc = _gate(_world(tmp_path, in_gated=[A], in_live=[A]), [A], skipped=[A])
    assert doc["verdict"] == "PASS" and doc["baseline_skips_absent"] == []


# new-behaviour
def test_the_key_is_an_empty_list_on_a_fail(tmp_path):
    doc = _gate(_world(tmp_path), [], skipped=[A])
    assert doc["verdict"] == "FAIL" and doc["baseline_skips_absent"] == []


# new-behaviour: even when a failed earlier step stops the run before the skip rule
def test_the_key_is_present_when_an_earlier_step_fails(tmp_path):
    doc = _gate(_world(tmp_path, in_live=[A]), [A], rcs={"junitxml": 1}, skipped=[], passed=[])
    assert doc["verdict"] == "FAIL" and doc["baseline_skips_absent"] == []


# ------------------------------------------------------------------ absent in both / present in gated -> FAIL as today
# invariant
def test_absent_in_both_trees_fails_with_todays_problem(tmp_path):
    doc = _gate(_world(tmp_path), [A], skipped=[], passed=[])
    assert doc["verdict"] == "FAIL"
    assert f"{NEITHER}['{_id(A)}']" in _problems(doc)
    assert doc["baseline_skips_absent"] == []


# invariant: present in gated but not collected (not skipped, not passed) still fails
def test_present_in_gated_and_not_collected_fails(tmp_path):
    doc = _gate(_world(tmp_path, in_gated=[A], in_live=[A]), [A], skipped=[], passed=[])
    assert doc["verdict"] == "FAIL"
    assert f"{NEITHER}['{_id(A)}']" in _problems(doc)
    assert doc["baseline_skips_absent"] == []


# invariant: present in gated, absent from live (removed since) is not the allowed direction
def test_present_in_gated_and_absent_from_live_fails(tmp_path):
    env = _world(tmp_path, in_gated=[A])
    _git(env["live"], "rm", "-q", FILE[A])
    _git(env["live"], "commit", "-q", "-m", "remove")
    doc = _gate(env, [A], skipped=[], passed=[])
    assert doc["verdict"] == "FAIL" and f"{NEITHER}['{_id(A)}']" in _problems(doc)
    assert doc["baseline_skips_absent"] == []


# invariant: present in gated and failed there still fails
def test_present_in_gated_and_failed_fails(tmp_path):
    doc = _gate(_world(tmp_path, in_gated=[A], in_live=[A]), [A], skipped=[], failed=[A])
    assert doc["verdict"] == "FAIL" and f"{NEITHER}['{_id(A)}']" in _problems(doc)


# ------------------------------------------------------------------ entry -> file derivation
# new-behaviour
def test_a_class_method_entry_resolves_to_the_module_file(tmp_path):
    doc = _gate(_world(tmp_path, in_live=[K]), [K], skipped=[], passed=[])
    assert doc["verdict"] == "PASS" and doc["baseline_skips_absent"] == [_id(K)]


# new-behaviour
def test_a_nested_class_entry_resolves_to_the_module_file(tmp_path):
    doc = _gate(_world(tmp_path, in_live=[N]), [N], skipped=[], passed=[])
    assert doc["verdict"] == "PASS" and doc["baseline_skips_absent"] == [_id(N)]


# invariant: a class-method entry whose module file is absent in both still fails
def test_a_class_method_entry_with_the_module_absent_in_both_fails(tmp_path):
    doc = _gate(_world(tmp_path), [K], skipped=[], passed=[])
    assert doc["verdict"] == "FAIL" and f"{NEITHER}['{_id(K)}']" in _problems(doc)


def _add_live_class_named_file(env):
    (env["live"] / "pkg/tests/test_k").mkdir(parents=True)
    (env["live"] / "pkg/tests/test_k/TestKlass.py").write_text("")
    _git(env["live"], "add", "-A")
    _git(env["live"], "commit", "-q", "-m", "later: file named after the class")


# new-behaviour. World 1: the gated tree has NO dotted prefix of the entry as a `.py` file. Junit classname cannot tell a class
# from a module, so a live-only file named after the class is a valid prefix and the entry is allowed (spec v1.1).
def test_a_live_only_file_named_after_the_class_allows_the_entry_when_the_gated_tree_has_no_prefix_file(tmp_path):
    env = _world(tmp_path)
    _add_live_class_named_file(env)
    doc = _gate(env, [K], skipped=[], passed=[])
    assert doc["verdict"] == "PASS" and doc["baseline_skips_absent"] == [_id(K)]


# reproduces-failure (F1). World 2: the gated tree HAS the module file pkg/tests/test_k.py and the entry was not collected (a
# real missing test); a live-only pkg/tests/test_k/TestKlass.py must not turn it into an allowed absence (gated tree first).
def test_a_live_only_class_named_file_does_not_allow_an_entry_whose_module_file_is_in_the_gated_tree(tmp_path):
    env = _world(tmp_path, in_gated=[K], in_live=[K])
    _add_live_class_named_file(env)
    doc = _gate(env, [K], skipped=[], passed=[])
    assert doc["verdict"] == "FAIL"
    assert f"{NEITHER}['{_id(K)}']" in _problems(doc)
    assert doc["baseline_skips_absent"] == []


# new-behaviour: an entry with no `::` has no derivable path; fails even when a matching file is live-only
def test_an_entry_without_double_colon_fails(tmp_path):
    entry = "pkg.tests.test_a"
    doc = _gate(_world(tmp_path, in_live=[A]), [entry], skipped=[], passed=[])
    assert doc["verdict"] == "FAIL"
    assert f"{NEITHER}['{entry}']" in _problems(doc)
    assert doc["baseline_skips_absent"] == []


# new-behaviour: a malformed entry with no module part fails and does not crash the gate
@pytest.mark.parametrize("entry", ["::test_x", "..::test_x", "pkg/tests/test_a::test_one"])
def test_an_entry_whose_path_cannot_be_derived_fails_cleanly(tmp_path, entry):
    doc = _gate(_world(tmp_path, in_live=[A]), [entry], skipped=[], passed=[])
    assert doc["verdict"] == "FAIL" and f"{NEITHER}['{entry}']" in _problems(doc)
    assert doc["baseline_skips_absent"] == []


# ------------------------------------------------------------------ v1.2 hardening
# Every allowed-case world above (`_world(..., in_live=[X])` with X not in `in_gated`) already satisfies v1.2: the live file is a
# regular file committed at the live HEAD in a commit made AFTER the gated sha (`_world`'s "later" commit), the entry has exactly
# one live prefix file, and the id is absent from the junit (skipped=[], passed=[]).
def _later_commit(env, msg="later"):
    _git(env["live"], "add", "-A")
    _git(env["live"], "commit", "-q", "-m", msg)


def _assert_refused(doc, entry):
    assert doc["verdict"] == "FAIL"
    assert f"{NEITHER}['{_id(entry)}']" in _problems(doc)
    assert doc["baseline_skips_absent"] == []


# new-behaviour: the allowed world's file is a regular file; an executable regular file (mode 100755) is allowed too
def test_an_executable_regular_live_file_is_allowed(tmp_path):
    env = _world(tmp_path)
    f = env["live"] / FILE[A]
    f.parent.mkdir(parents=True)
    f.write_text("def test(): pass\n")
    f.chmod(0o755)
    _later_commit(env)
    assert _git(env["live"], "ls-tree", "HEAD", "--", FILE[A]).startswith("100755")
    doc = _gate(env, [A], skipped=[], passed=[])
    assert doc["verdict"] == "PASS" and doc["baseline_skips_absent"] == [_id(A)]


# reproduces-failure (v1.2): a live file on disk but not tracked at the live HEAD (untracked) is not "added after the gated sha"
def test_an_untracked_live_file_does_not_allow_the_entry(tmp_path):
    env = _world(tmp_path)
    (env["live"] / FILE[A]).parent.mkdir(parents=True)
    (env["live"] / FILE[A]).write_text("def test(): pass\n")  # on disk only
    assert _git(env["live"], "ls-tree", "HEAD", "--", FILE[A]) == ""
    _assert_refused(_gate(env, [A], skipped=[], passed=[]), A)


# reproduces-failure (v1.2): staged but not committed is still not at the live HEAD
def test_a_staged_but_uncommitted_live_file_does_not_allow_the_entry(tmp_path):
    env = _world(tmp_path)
    (env["live"] / FILE[A]).parent.mkdir(parents=True)
    (env["live"] / FILE[A]).write_text("def test(): pass\n")
    _git(env["live"], "add", "-A")
    _assert_refused(_gate(env, [A], skipped=[], passed=[]), A)


# reproduces-failure (v1.2): the live HEAD is on a history unrelated to the gated sha (the adding commit has no gated ancestor)
def test_a_live_file_added_on_an_unrelated_history_does_not_allow_the_entry(tmp_path):
    env = _world(tmp_path)
    _git(env["live"], "checkout", "-q", "--orphan", "unrelated")
    (env["live"] / FILE[A]).parent.mkdir(parents=True)
    (env["live"] / FILE[A]).write_text("def test(): pass\n")
    for rel, text in BASE_FILES.items():
        (env["live"] / rel).write_text(text)
    _later_commit(env, "orphan root with the file")
    assert subprocess.run(["git", "-C", str(env["live"]), "merge-base", "--is-ancestor", env["sha"], "HEAD"]).returncode != 0
    _assert_refused(_gate(env, [A], skipped=[], passed=[]), A)


# reproduces-failure (v1.2): the live HEAD is BEHIND the gated sha: the file was added in an ancestor of the gated sha, which
# then deleted it (the adding commit is not after the gated sha)
def test_a_live_file_added_before_the_gated_sha_and_deleted_by_it_does_not_allow_the_entry(tmp_path):
    live = tmp_path / "live" / "mlx-serve"
    c0 = _repo(live, {**BASE_FILES, FILE[A]: "def test(): pass\n"}, origin=LIVE_ORIGIN)
    _git(live, "rm", "-q", FILE[A])
    _git(live, "commit", "-q", "-m", "gated sha deletes the file")
    sha = _git(live, "rev-parse", "HEAD")
    _git(live, "checkout", "-q", "--detach", c0)  # the live HEAD holds the file, as an ancestor of the gated sha
    assert _git(live, "ls-tree", "HEAD", "--", FILE[A]).startswith("100644")
    baselines = tmp_path / "baselines"
    baselines.mkdir()
    env = dict(tmp=tmp_path, live=live, sha=sha, gate=tmp_path / "gate", baselines=baselines)
    _assert_refused(_gate(env, [A], skipped=[], passed=[]), A)


# reproduces-failure (v1.2): a symlink (git mode 120000) at the live HEAD is not a regular test file
def test_a_live_symlink_does_not_allow_the_entry(tmp_path):
    env = _world(tmp_path)
    f = env["live"] / FILE[A]
    f.parent.mkdir(parents=True)
    (f.parent / "real_a.py").write_text("def test(): pass\n")
    f.symlink_to("real_a.py")
    _later_commit(env)
    assert _git(env["live"], "ls-tree", "HEAD", "--", FILE[A]).startswith("120000")
    _assert_refused(_gate(env, [A], skipped=[], passed=[]), A)


# reproduces-failure (v1.2): module file AND class-named file both live (ambiguous) -> not allowed
def test_two_live_prefix_files_make_the_entry_ambiguous_and_refused(tmp_path):
    env = _world(tmp_path, in_live=[K])  # pkg/tests/test_k.py, committed after the gated sha
    _add_live_class_named_file(env)  # + pkg/tests/test_k/TestKlass.py
    assert (env["live"] / "pkg/tests/test_k.py").is_file() and (env["live"] / "pkg/tests/test_k/TestKlass.py").is_file()
    _assert_refused(_gate(env, [K], skipped=[], passed=[]), K)


# reproduces-failure (v1.2): the id appears in the junit as failed / errored -> never reclassified as absent
@pytest.mark.parametrize("kind", ["failed", "errored"])
def test_an_id_that_failed_or_errored_in_the_junit_is_not_absent_allowed(tmp_path, kind):
    doc = _gate(_world(tmp_path, in_live=[A]), [A], skipped=[], passed=[], **{kind: [A]})
    _assert_refused(doc, A)


# ------------------------------------------------------------------ v1.3 divergent history
def _commit(live, rel, text, msg):
    f = live / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)
    _git(live, "add", "-A")
    _git(live, "commit", "-q", "-m", msg)
    return _git(live, "rev-parse", "HEAD")


def _env_for(tmp_path, live, sha):
    baselines = tmp_path / "baselines"
    baselines.mkdir()
    return dict(tmp=tmp_path, live=live, sha=sha, gate=tmp_path / "gate", baselines=baselines)


# reproduces-failure (round 3 refused it): the REAL divergent shape of the motivating re-gate. Base B has no test file; the gated
# sha is the tip of branch G (from B); the live HEAD is on branch L (from B), which adds the file. The adding commit is on the live
# side after the histories diverged: it is neither an ancestor of the gated sha nor required to descend from it.
def test_a_file_added_on_the_live_branch_after_the_histories_diverged_is_allowed(tmp_path):
    live = tmp_path / "live" / "mlx-serve"
    base = _repo(live, BASE_FILES, origin=LIVE_ORIGIN)
    _git(live, "checkout", "-q", "-b", "G")
    sha = _commit(live, "g_only.txt", "g\n", "G: the gated side")
    _git(live, "checkout", "-q", "-b", "L", base)
    added = _commit(live, FILE[A], "def test(): pass\n", "L: adds the test file")
    assert subprocess.run(["git", "-C", str(live), "merge-base", "--is-ancestor", sha, added]).returncode != 0  # diverged
    assert _git(live, "merge-base", sha, "HEAD") == base
    doc = _gate(_env_for(tmp_path, live, sha), [A], skipped=[], passed=[])
    assert doc["verdict"] == "PASS" and doc["problems"] == []
    assert doc["baseline_skips_absent"] == [_id(A)]


# invariant (v1.3 keeps the linear case): the file added by a descendant of the gated sha is still allowed
def test_a_file_added_on_a_linear_descendant_of_the_gated_sha_is_still_allowed(tmp_path):
    doc = _gate(_world(tmp_path, in_live=[A]), [A], skipped=[], passed=[])
    assert doc["verdict"] == "PASS" and doc["baseline_skips_absent"] == [_id(A)]


# reproduces-failure (v1.3 refusal): the file was added on G's OWN history (an ancestor of the gated sha), the gated sha deleted it
# on G, and the live HEAD is on a branch L that forked after the add and still holds it. The adding commit is not "after the
# divergence" (it is an ancestor of the gated sha), so the entry is not an absence of a later file.
def test_a_file_added_on_the_gated_history_and_deleted_there_does_not_allow_the_entry(tmp_path):
    live = tmp_path / "live" / "mlx-serve"
    _repo(live, BASE_FILES, origin=LIVE_ORIGIN)
    added = _commit(live, FILE[A], "def test(): pass\n", "G1: adds the test file")
    _git(live, "checkout", "-q", "-b", "L", added)
    _commit(live, "l_only.txt", "l\n", "L: forks after the add, keeps the file")
    _git(live, "checkout", "-q", "main")
    _git(live, "rm", "-q", FILE[A])
    _git(live, "commit", "-q", "-m", "G2: deletes the file on the gated side")
    sha = _git(live, "rev-parse", "HEAD")
    _git(live, "checkout", "-q", "L")
    assert _git(live, "ls-tree", "HEAD", "--", FILE[A]).startswith("100644")
    assert subprocess.run(["git", "-C", str(live), "merge-base", "--is-ancestor", added, sha]).returncode == 0
    _assert_refused(_gate(_env_for(tmp_path, live, sha), [A], skipped=[], passed=[]), A)


# ------------------------------------------------------------------ live_head in every receipt
# new-behaviour
@pytest.mark.parametrize("world", ["pass_absent", "plain_pass", "fail_extra_skip", "earlier_step_fails"])
def test_every_receipt_carries_live_head_equal_to_the_live_head_sha(tmp_path, world):
    if world == "pass_absent":
        env, args, kw = _world(tmp_path, in_live=[A]), [A], dict(skipped=[], passed=[])
    elif world == "plain_pass":
        env, args, kw = _world(tmp_path, in_gated=[A], in_live=[A]), [A], dict(skipped=[A])
    elif world == "fail_extra_skip":
        env, args, kw = _world(tmp_path), [], dict(skipped=[A])
    else:
        env, args, kw = _world(tmp_path, in_live=[A]), [A], dict(rcs={"junitxml": 1}, skipped=[], passed=[])
    head = _git(env["live"], "rev-parse", "HEAD")
    assert head != env["sha"] or world != "pass_absent"
    doc = _gate(env, args, **kw)
    assert doc["live_head"] == head


# new-behaviour: live_head is the live HEAD, not the gated sha (they differ in the divergent shape)
def test_live_head_is_the_live_branch_tip_not_the_gated_sha(tmp_path):
    live = tmp_path / "live" / "mlx-serve"
    base = _repo(live, BASE_FILES, origin=LIVE_ORIGIN)
    _git(live, "checkout", "-q", "-b", "G")
    sha = _commit(live, "g_only.txt", "g\n", "G")
    _git(live, "checkout", "-q", "-b", "L", base)
    head = _commit(live, "l_only.txt", "l\n", "L")
    doc = _gate(_env_for(tmp_path, live, sha), [], skipped=[])
    assert doc["live_head"] == head and doc["live_head"] != sha


# ------------------------------------------------------------------ mixed with other rules
# new-behaviour: one allowed + one unexplained: FAIL naming only the unexplained one; the allowed one is still recorded
def test_a_mixed_baseline_fails_naming_only_the_unexplained_entry(tmp_path):
    doc = _gate(_world(tmp_path, in_live=[A]), [A, B], skipped=[], passed=[])
    assert doc["verdict"] == "FAIL"
    assert f"{NEITHER}['{_id(B)}']" in _problems(doc)
    assert _id(A) not in _problems(doc).split(NEITHER)[1]
    assert doc["baseline_skips_absent"] == [_id(A)]


# new-behaviour: C277 ran-and-passed and absent-allowed entries land in their own lists, disjoint
def test_ran_and_passed_and_absent_entries_are_recorded_in_separate_lists(tmp_path):
    doc = _gate(_world(tmp_path, in_gated=[B], in_live=[A, B]), [A, B, K], skipped=[K], passed=[B])
    assert doc["verdict"] == "PASS" and doc["problems"] == []
    assert doc["baseline_skips_ran"] == [_id(B)]
    assert doc["baseline_skips_absent"] == [_id(A)]
    assert doc["skipped_tests"] == [_id(K)]


# invariant: an entry that ran and passed is C277's, never listed as absent
def test_an_entry_that_ran_and_passed_is_not_listed_as_absent(tmp_path):
    doc = _gate(_world(tmp_path, in_live=[A]), [A], skipped=[], passed=[A])
    assert doc["verdict"] == "PASS"
    assert doc["baseline_skips_ran"] == [_id(A)] and doc["baseline_skips_absent"] == []


# invariant: an absent-allowed entry does not excuse an unbaselined skip
def test_an_absent_entry_does_not_excuse_an_extra_skip(tmp_path):
    doc = _gate(_world(tmp_path, in_live=[A]), [A], skipped=[B])
    assert doc["verdict"] == "FAIL"
    assert f"skip list != baseline: +['{_id(B)}']" in _problems(doc)


# invariant: the duplicate-entry rule still fires for an absent-allowed entry
def test_a_duplicated_absent_entry_still_fails_on_the_duplicate_rule(tmp_path):
    doc = _gate(_world(tmp_path, in_live=[A]), [A, A], skipped=[], passed=[])
    assert doc["verdict"] == "FAIL"
    assert f"skip baseline lists an entry more than once: ['{_id(A)}']" in _problems(doc)


class _NoJunit(JunitRunner):
    def __call__(self, argv, cwd, env):
        rc, out = super().__call__(argv, cwd, env)
        for a in argv:
            if a.startswith("--junitxml="):
                Path(a.split("=", 1)[1]).unlink(missing_ok=True)
        return rc, out


# invariant: a missing junit still fails
def test_a_missing_junit_still_fails(tmp_path):
    doc = _gate(_world(tmp_path, in_live=[A]), [A], runner_cls=_NoJunit, skipped=[], passed=[])
    assert doc["verdict"] == "FAIL" and "pytest junit not written" in _problems(doc)
    assert doc["baseline_skips_absent"] == []


# invariant: no baseline file keeps today's problem
def test_no_baseline_file_keeps_todays_problem(tmp_path):
    doc = _gate(_world(tmp_path, in_live=[A]), None, skipped=[], passed=[])
    assert doc["verdict"] == "FAIL" and "no skip baseline" in _problems(doc)
    assert NEITHER not in _problems(doc)


# invariant: the receipt of an absent-allowed PASS keeps the six steps and the scratch is removed
def test_an_absent_pass_keeps_the_six_steps_and_removes_the_scratch(tmp_path):
    env = _world(tmp_path, in_live=[A])
    doc = _gate(env, [A], skipped=[], passed=[])
    assert [s["name"] for s in doc["steps"]] == ["clone", "sync", "ruff-check", "ruff-format", "pytest", "build"]
    assert not list((env["gate"] / "scratch").glob("*"))


# invariant: the policy digest does not depend on which trees hold the file
def test_the_policy_digest_does_not_depend_on_the_absent_rule(tmp_path):
    d1 = _gate(_world(tmp_path / "x", in_gated=[A], in_live=[A]), [A], skipped=[A])["policy_digest"]
    d2 = _gate(_world(tmp_path / "y", in_live=[A]), [A], skipped=[], passed=[])["policy_digest"]
    assert d1 == d2
