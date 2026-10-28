"""P426 T3 frozen tests: every fixture of `t3_frozen_support` exercised against the BASELINE through each path the other
T3 frozen tests use. These pass on B0 (before any T3 change) and must keep passing after it."""

import json
import subprocess

import pytest
import yaml

from bench import modelnames, p426_leg as L, p426_panel as P, p426_plan as PL, p426_wave1 as W
from bench.tests import t3_frozen_support as T
from bench.tests.t3_frozen_support import box  # noqa: F401 — the fake-box fixture


# ------------------------------------------------------------------ checkouts, venvs, registries
def test_a_fake_checkout_reports_its_pinned_head(tmp_path):
    fork = T.make_checkout(tmp_path / "fork", T.S2_PINS["mlx_vlm"], fork=True)
    assert T.git(fork, "rev-parse", "HEAD") == T.S2_PINS["mlx_vlm"]
    assert (fork / "dev" / "p369_phase2" / "orchestrate.py").exists()


def test_a_venv_reports_exactly_its_versions_to_its_own_interpreter(tmp_path):
    venv = T.make_venv(tmp_path / "a" / "b" / "wt" / ".venv", T.S2_VERSIONS)
    code = ("import importlib.metadata as m, json; "
            f"print(json.dumps({{d: m.version(d) for d in {sorted(T.S2_VERSIONS)!r}}}))")
    out = T.REAL_RUN([str(venv / "bin" / "python"), "-c", code], capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == T.S2_VERSIONS
    T.set_version(venv, "mlx", "0.32.3")
    assert T.installed(venv) == dict(T.S2_VERSIONS, mlx="0.32.3")


def test_the_s_overlay_passes_todays_registry_delta_check():
    off = T.off_registry()
    assert L.registry_delta_problems(T.overlay_on(off), off, T.ENTRY) == []


# POST-REVEAL tw-4: the seeding restore is now C241 / P511's exact reverse of C177's hunk (no tuple form, no comment kept).
def test_the_restored_registry_is_the_three_c177_lines_and_the_note():
    off, on = T.off_registry(), T.restored_registry(T.off_registry())
    entry = {m["name"]: m for m in yaml.safe_load(on)["models"]}[T.ENTRY]
    assert {k: entry[k] for k in L.P426_ON[T.ENTRY]} == L.P426_ON[T.ENTRY]
    import difflib

    delta = [d for d in difflib.ndiff(off.split("\n"), on.split("\n")) if d[:2] in ("- ", "+ ")]
    removed = [d[2:] for d in delta if d.startswith("- ")]
    added = [d[2:] for d in delta if d.startswith("+ ")]
    assert len(removed) == 3 and all(x.lstrip().startswith("#") for x in removed)
    assert sorted(added) == sorted(list(T.C177.values()) + [T.PROVISIONAL_NOTE])
    seeding = (T.REPO / T.SEEDING_TEST).read_text()
    restored = T.restored_seeding(seeding)
    assert seeding.count(T.SEEDING_OFF) == 1 and restored.count(T.SEEDING_ON) == 1 and T.SEEDING_OFF not in restored
    assert "C177" not in restored and restored.replace(T.SEEDING_ON, T.SEEDING_OFF) == seeding


# POST-REVEAL tw-4: C241 / P511 — the restore helpers produce the pinned bytes from the fork's own rule, and the fake fork of
# every arm worktree carries that rule so `bench.p426_overlay.load_registry_states` loads it from the worktree.
def test_the_p511_restore_bytes_come_from_the_forks_rule_in_each_worktree(tmp_path):
    from bench import p426_overlay

    off = T.off_registry()
    assert T.fork_overlay_on(off) == T.overlay_on(off)  # the S overlay helper equals the B4 rule on the committed registry
    on = T.restored_registry(off).split("\n")
    gd = on.index("    generation_defaults:", on.index(f"  - name: {T.ENTRY}"))
    assert on[gd + 1] == T.PROVISIONAL_NOTE and on[:gd + 1] + on[gd + 2:] == T.fork_overlay_on(off).split("\n")
    assert sum("PROVISIONAL P426" in x for x in on) == sum("PROVISIONAL P426" in x for x in off.split("\n")) + 1
    w = T.make_arms_world(tmp_path)
    for wt in (w.off, w.on):
        rs = p426_overlay.load_registry_states(wt)
        got, _ = rs.overlay_on((w.off / "main_models.yaml").read_text(),
                               rs.fixture_text(wt / "src" / "mlx-vlm" / "mlx_vlm" / "tests" / "fixtures"), T.ENTRY)
        assert got == T.fork_overlay_on(off)
    assert (w.on / "main_models.yaml").read_text() == T.restored_registry(off)
    assert (w.on / T.SEEDING_TEST).read_text() == T.restored_seeding((w.off / T.SEEDING_TEST).read_text())


# ------------------------------------------------------------------ the S world through today's sequencer (label `s`)
# POST-REVEAL tw-3: (c) adopted — pass `--build s` where the sequencer has it (spec §4: required); B0 has no option.
def test_the_s_world_runs_every_leg_valid_through_todays_sequencer(tmp_path, monkeypatch, box):
    """The whole fake box: today's `bench.p426_wave1.main` launches today's `bench.p426_leg.main` (in-process) for all 30
    legs; every leg VALID; argv, names, session prefixes, the M1 directory and the harvest layout are today's."""
    w = T.make_s_world(tmp_path)
    monkeypatch.setenv("STACK_WORKDIR", str(w.wd))
    rc, text = T.run_main(W.main, T.s_argv(w, build=T.s_build()))
    assert rc == 0, text + "\n".join(r["out"] for r in box.legs_run)
    names = T.s_leg_names()
    assert [r["name"] for r in box.legs_run] == [W.leg_name(*leg) for leg in W.schedule()]
    assert sorted(names) == sorted(r["name"] for r in box.legs_run)
    receipts = w.out / "receipts"
    for n in names:
        assert T.receipt(receipts, n)["verdict"] == "VALID", T.receipt(receipts, n)["problems"]
        assert (w.main / "benchmark/results/p426/wave1" / n / "SCRUB_MANIFEST.json").exists()
    first = box.launches[0]
    assert first["argv"] == W.leg_argv(w.root, str(w.wd), w.overlay, receipts, "math500", "off", "smoke")
    assert first["cwd"] == str(w.root / "benchmark")
    assert {d["prefix"] for d in box.drivers if d["prefix"]} == {f"p426-{n}" for n in names if not n.startswith("m1-")}
    assert sorted(p.name for p in (w.wd / "p426" / "m1").iterdir()) == sorted(
        n.split("-", 1)[1] for n in names if n.startswith("m1-"))
    assert sorted(p.name for p in (w.main / "benchmark/results/p426/wave1/run").iterdir()) == [
        "frozen.json", "registry-on.yaml", "sequence.log"]
    assert all(d["serving"] == str(w.root) for d in box.drivers if d["prefix"])


# POST-REVEAL tw-3: (c) adopted — pass `--build s` where the sequencer has it (spec §4: required).
def test_a_receipt_refused_before_the_first_leg_is_visible_to_the_helpers(tmp_path, monkeypatch, box):
    w = T.make_s_world(tmp_path)
    monkeypatch.setenv("STACK_WORKDIR", str(w.wd))
    box.before_leg["math500-p426-off-smoke"] = lambda: (w.root / "README.md").write_text("dirty\n")
    rc, text = T.run_main(W.main, T.s_argv(w, axes=["math500"], build=T.s_build()))
    assert rc == 1 and len(box.legs_run) == 1
    got = T.receipt(w.out / "receipts", "math500-p426-off-smoke")
    assert got["verdict"] == "NOT_STARTED" and any("stack_clean" in p for p in got["problems"])
    assert "math500-p426-off-smoke" in T.text_of(text, w.out / "sequence.log")


# POST-REVEAL tw-3: (c) adopted — pass `--build s` where the sequencer has it (spec §4: required).
def test_a_driver_hook_mutates_the_world_during_the_leg(tmp_path, monkeypatch, box):
    w = T.make_s_world(tmp_path)
    monkeypatch.setenv("STACK_WORKDIR", str(w.wd))
    box.during_driver["math500-p426-off-smoke"] = lambda: (w.root / "README.md").write_text("dirty\n")
    rc, _ = T.run_main(W.main, T.s_argv(w, axes=["math500"], build=T.s_build()))
    got = T.receipt(w.out / "receipts", "math500-p426-off-smoke")
    assert rc == 1 and got["verdict"] == "INVALID" and any("drift" in p for p in got["problems"])


# ------------------------------------------------------------------ the S′ world (two committed arms)
def test_the_arms_world_is_one_restore_commit_on_the_frozen_commit(tmp_path):
    w = T.make_arms_world(tmp_path)
    off_head, on_head = T.git(w.off, "rev-parse", "HEAD"), T.git(w.on, "rev-parse", "HEAD")
    assert T.git(w.on, "rev-parse", "HEAD^") == off_head
    assert T.git(w.on, "diff", "--name-only", off_head, on_head).split() == ["benchmark/bench/tests/test_opencode_probe_seeding.py",
                                                                             "main_models.yaml"]
    for wt in (w.off, w.on):
        assert T.git(wt, "status", "--porcelain", "--untracked-files=no") == ""
        assert T.git(wt / "src" / "mlx-vlm", "rev-parse", "HEAD") == T.S2_PINS["mlx_vlm"]
        assert T.git(wt / "src" / "mlx-serve", "rev-parse", "HEAD") == T.S2_PINS["mlx_serve"]
        for v in T.VENVS:
            assert T.installed(wt / v) == T.S2_VERSIONS
    doc = json.loads(w.frozen.read_text())
    assert doc["build"] == "s2" and doc["stack_head_off"] == off_head and doc["stack_head_on"] == on_head
    assert doc["registry_on_sha"] == T.sha256_file(w.on / "main_models.yaml") != doc["registry_off_sha"]
    assert doc["venvs"]["on"][".venv-bench"] == T.S2_VERSIONS
    assert w.frozen == w.wd / "p426" / "frozen.s2.json"


# POST-REVEAL tw-3: the record the fixtures write carries exactly the designer-ruled fields, each pinned to the live world.
def test_the_s2_record_carries_exactly_the_ruled_fields(tmp_path):
    w = T.make_arms_world(tmp_path)
    doc = json.loads(w.frozen.read_text())
    assert sorted(doc) == sorted(T.FROZEN_S2_FIELDS)
    assert doc["uv_lock_sha256"] == T.sha256_file(w.off / "uv.lock") == T.sha256_file(w.on / "uv.lock")
    assert doc["bench_lock_sha256"] == T.sha256_file(w.off / "benchmark/requirements-bench.lock")
    assert doc["stack_clean_off"] is True and doc["stack_clean_on"] is True
    assert {k: doc[k] for k in ("mlx_vlm", "mlx_serve", "production_ref")} == T.S2_PINS
    assert doc["registry_off_sha"] == T.sha256_file(w.off / "main_models.yaml")
    assert sorted(doc["venvs"]) == ["off", "on"]
    for arm, wt in (("off", w.off), ("on", w.on)):
        assert sorted(doc["venvs"][arm]) == sorted(T.VENVS)
        for v in T.VENVS:
            assert doc["venvs"][arm][v] == T.installed(wt / v) == T.S2_VERSIONS


@pytest.mark.parametrize("arm", ["off", "on"])
@pytest.mark.parametrize("axis, sel", [("math500", "smoke"), ("cjudge", 1), ("vision", 2), ("reasoning", "smoke")])
def test_the_fake_drivers_pass_todays_leg_checks_from_either_arm(tmp_path, box, axis, sel, arm):
    """Each arm worktree serves its own committed registry; the rows and log lines the fake drivers leave pass today's
    membership / engagement / seed / log / request-match checks for that arm (ON engages, OFF does not)."""
    w = T.make_arms_world(tmp_path)
    wt = w.on if arm == "on" else w.off
    plan, rows, lines = T.drive_once(box, w.wd, wt, axis, arm, sel)
    assert L.membership_problems(plan["planned"], rows, plan["row_key"]) == []
    assert L.engagement_problems(arm, rows, plan["row_key"]) == []
    assert PL.seed_problems(plan["seeds"], rows, plan["row_key"]) == []
    assert L.log_problems(lines, arm, plan["expected_requests"])[0] == []
    spec = L.LegSpec(name="x", arm=arm, kind=axis, model=T.ENTRY, registry_text="", off_registry_text="", driver_argv=[],
                     destinations=[], rows_path=plan["rows_path"], planned=plan["planned"], receipt_dir=tmp_path,
                     server_log=None, expected_extra=plan["expected_extra"])
    extras, problems = L.extra_ids_for(spec)
    assert problems == [] and L.request_match_problems(rows, lines, extras) == []
    ops = T.FakeChainOps(wt, w.wd, wt / "main_models.yaml", None)
    assert L.model_argv_problems(ops.load(T.ENTRY)["cmdline"], (wt / "main_models.yaml").read_text(), T.ENTRY) == []


def test_the_fake_qualify_writes_the_report_and_the_on_overlay(tmp_path, box):
    w = T.make_arms_world(tmp_path)
    plan = PL.plan_leg(w.on, "m1", "on", 1, workdir=w.wd, reviewed_head=T.S2_PINS["mlx_vlm"],
                       production_ref=T.S2_PINS["production_ref"])
    assert box.driver(plan["driver_argv"], {}, plan["cwd"]) == 0
    report = json.loads((plan["out_dir"] / "report.json").read_text())
    assert PL.qualify_problems(report, T.ENTRY, "on", T.S2_PINS["production_ref"]) == []
    assert T.sha256_file(plan["out_dir"] / f"overlay-{T.ENTRY}.yaml") == T.sha256_file(w.on / "main_models.yaml")


def test_arms_and_s_worlds_share_one_workdir_without_colliding(tmp_path):
    s = T.make_s_world(tmp_path)
    a = T.make_arms_world(tmp_path)
    assert s.wd == a.wd and s.main == a.main and s.frozen != a.frozen and s.out != a.out
    assert s.frozen.exists() and a.frozen.exists() and s.root.exists() and a.off.exists()


def test_the_s2_names_helper_lists_thirty_legs():
    names = T.s2_leg_names()
    assert len(names) == len(set(names)) == 30 and names[0] == "math500-p426s2-off-smoke" and "m1-p426s2-on-b2" in names


def test_a_refusal_is_readable_through_run_main():
    rc, text = T.run_main(W.main, ["--nope"])
    assert rc == 2 and "required" in text


# ------------------------------------------------------------------ the local gate's fork layouts
def test_the_old_layout_passes_todays_gate_with_eight_audits_and_the_workflow_ref(tmp_path):
    repo, sha = T.old_layout(tmp_path / "mlx-vlm")
    doc, runner = T.gate_run(tmp_path, repo, sha)
    assert doc["verdict"] == "PASS", doc["problems"]
    assert doc["parity_ref"] == T.OLD_REF
    assert runner.audits() == [(n, T.OLD_REF, extra) for n, extra in T.OLD_AUDITS]


def test_the_s2_layout_carries_the_forks_own_nine_audits_and_sync_ref(tmp_path):
    repo, sha = T.s2_layout(tmp_path / "mlx-vlm")
    assert T.ast_audits(T.git(repo, "show", f"{sha}:dev/ci.py")) == T.S2_AUDITS
    assert T.git(repo, "show", f"{sha}:.upstream-sync-ref").splitlines()[-1] == T.S2_REF
    assert T.git(repo, "ls-tree", "--name-only", sha, ".github/workflows/upstream-parity.yml") == ""
    assert T.ast_audits(T.ci_py(T.OLD_AUDITS)) == T.OLD_AUDITS


# ------------------------------------------------------------------ naming / panel helpers
def test_the_fragment_is_flagged_off_the_exempt_paths_and_exempt_on_s_dossiers(tmp_path):
    root = T.names_root(tmp_path)
    line = f"the {T.fragment()} drafter"
    assert modelnames.diff_violations(T.added_line_diff("docs/x.md", line), root=root)
    assert modelnames.diff_violations(T.added_line_diff("benchmark/results/p426/wave1/math500-p426-on-b1/x.log", line),
                                      root=root) == []


def test_the_verdict_helper_scores_through_todays_panel():
    rows = [T.verdict("q1", o, j, "A", P.ON_TUNE, P.OFF_TUNE) for o in ("AB",) for j in ("j1", "j2")]
    assert P.item_scores(rows)["q1"]["score"] == 1.0


# ------------------------------------------------------------------ the remaining helpers, each through its path
def test_todays_leg_cli_runs_an_m1_leg_valid_in_the_s_world(tmp_path, monkeypatch, box):
    """The direct `bench.p426_leg.main` path (no sequencer) of `test_t3_frozen_label`."""
    w = T.make_s_world(tmp_path)
    monkeypatch.setenv("STACK_WORKDIR", str(w.wd))
    rd = tmp_path / "rd"
    rc, text = T.run_main(L.main, ["--axis", "m1", "--arm", "on", "--block", "1", "--stack-root", str(w.root), "--workdir",
                                   str(w.wd), "--registry-on", str(w.overlay), "--receipt-dir", str(rd)])
    assert rc == 0, text
    doc = T.receipt(rd, "m1-p426-on-b1")
    assert doc["verdict"] == "VALID" and (w.wd / "p426" / "m1" / "p426-on-b1" / "report.json").exists()
    assert set(doc["state"]) == {"stack_head", "stack_clean", "mlx_vlm", "mlx_serve", "frozen_sha"}


def test_recommit_on_rewrites_the_restore_and_a_self_consistent_record(tmp_path):
    w = T.make_arms_world(tmp_path)
    off_head = T.git(w.off, "rev-parse", "HEAD")
    T.recommit_on(w)
    assert T.git(w.on, "rev-parse", "HEAD^") == off_head
    assert T.git(w.on, "diff", "--name-only", off_head, "HEAD").split() == [T.SEEDING_TEST, "main_models.yaml"]
    T.recommit_on(w, files={"README.md": "changed\n"}, chmod=T.SEEDING_TEST, commits=2)
    assert T.git(w.on, "rev-parse", "HEAD~2") == off_head
    assert "README.md" in T.git(w.on, "diff", "--name-only", off_head, "HEAD").split()
    assert "old mode" in T.git(w.on, "diff", off_head, "HEAD", "--", T.SEEDING_TEST)
    doc = json.loads(w.frozen.read_text())
    assert doc["stack_head_on"] == T.git(w.on, "rev-parse", "HEAD") and doc["stack_clean_on"] is True
    assert T.git(w.on, "status", "--porcelain", "--untracked-files=no") == ""


def test_committed_evidence_enters_the_frozen_commit_of_both_arms(tmp_path):
    main = tmp_path / "m"
    rel = "benchmark/results/p426/wave1/math500-p426-off-smoke/leg.stdout"
    (main / rel).parent.mkdir(parents=True)
    (main / rel).write_bytes(b"leg out\n")
    w = T.make_arms_world(tmp_path / "x", extra=T.committed_evidence(main))
    for wt in (w.off, w.on):
        assert (wt / rel).read_bytes() == b"leg out\n" and T.git(wt, "ls-files", rel) == rel


def test_the_qualify_overlay_hook_replaces_the_served_overlay(tmp_path, box):
    w = T.make_arms_world(tmp_path)
    plan = PL.plan_leg(w.on, "m1", "on", 1, workdir=w.wd, reviewed_head="v" * 40, production_ref="p" * 40)
    box.qualify_overlay[str(plan["out_dir"])] = b"other\n"
    box.driver(plan["driver_argv"], {}, plan["cwd"])
    assert (plan["out_dir"] / f"overlay-{T.ENTRY}.yaml").read_bytes() == b"other\n"


def test_a_usage_error_reads_as_refused_before_launch_only_when_allowed(tmp_path, monkeypatch, box):
    w = T.make_arms_world(tmp_path)
    run = T.run_sequencer(w, box, ["--nope"], monkeypatch)
    T.assert_refused_before_launch(run, allow_usage=True)
    with pytest.raises(AssertionError):
        T.assert_refused_before_launch(run)


# POST-REVEAL tw-3: (c) adopted — the sha holding both files no longer pins B0's reading (spec §3: `.upstream-sync-ref` first,
# asserted by `test_t3_frozen_gate`); here only what both sides agree on: the fixture's files per sha, PASS at each sha, and
# the S-layout sha's workflow ref and eight audits.
def test_todays_gate_reads_each_sha_of_a_multi_commit_fork(tmp_path):
    """The repositories of `test_t3_frozen_gate`: each sha holds the layout files the frozen gate tests name, and the gate
    PASSes at each; the S-layout sha gates with the workflow ref and the eight audits."""
    from bench import local_gate as G

    repo, old = T.old_layout(tmp_path / "mlx-vlm")
    both = T.fork_commit(repo, workflow=T.OLD_WORKFLOW, ci=T.ci_py(T.S2_AUDITS), sync_ref=T.sync_ref_file("aaaa1111"))
    later = T.fork_commit(repo, ci=T.ci_py([("check_upstream_parity.py", ())]), sync_ref=T.sync_ref_file("v0.9.9"))
    assert T.git(repo, "ls-tree", "--name-only", later, ".github/workflows/upstream-parity.yml") == ""
    assert G.parity_ref(T.git(repo, "show", f"{both}:.github/workflows/upstream-parity.yml")) == T.OLD_REF
    assert T.git(repo, "show", f"{both}:.upstream-sync-ref").splitlines()[-1] == "aaaa1111"
    assert T.ast_audits(T.git(repo, "show", f"{both}:dev/ci.py")) == T.S2_AUDITS
    doc, runner = T.gate_run(tmp_path / old[:8], repo, old)
    assert doc["verdict"] == "PASS" and doc["parity_ref"] == T.OLD_REF
    assert [a for a, _, _ in runner.audits()] == [n for n, _ in T.OLD_AUDITS]
    doc, _ = T.gate_run(tmp_path / both[:8], repo, both)
    assert doc["verdict"] == "PASS", doc["problems"]
