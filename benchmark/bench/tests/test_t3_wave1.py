"""P426 T3 §4: the Wave-1 rerun on S′ — a build label (`s2`) so the same reviewed sequencer runs Wave 1 again from two committed
arm worktrees into names that cannot overwrite or be confused with S's. Under `s` nothing changes (the existing P426 tests are
the proof); these tests cover the label's names, expected build, frozen record, arms as commits, `--out` marker, check order,
isolation, harvest paths, the naming exemption and the panel tunes. Fixtures are tiny local git repos; nothing starts a process."""

import hashlib
import json
import os
import subprocess
import types
from pathlib import Path

import pytest

from bench import modelnames, p426_harvest as H, p426_ids, p426_leg as L, p426_overlay, p426_panel as P, p426_plan as PL, p426_wave1 as W
from bench.tests import test_p426_leg as TL

REPO = Path(__file__).resolve().parents[3]
ENTRY = p426_ids.ENTRY
AXES = ("math500", "cjudge", "vision", "reasoning", "m1")


# ------------------------------------------------------------------ the label and its names
@pytest.mark.parametrize("label", ["s", "s2", "a", "abcdefgh", "x1y2z3"])
def test_a_valid_label(label):
    assert PL.check_build(label) == label


@pytest.mark.parametrize("label", ["", "S2", "2s", "s_2", "s-2", "abcdefghi", "s2/", "../s", "s 2", None])
def test_an_invalid_label_refuses(label):
    with pytest.raises(ValueError, match="build label"):
        PL.check_build(label)


@pytest.mark.parametrize("axis", AXES)
@pytest.mark.parametrize("arm", ["off", "on"])
def test_s2_names_for_every_axis(axis, arm, tmp_path):
    for block, smoke in ((None, True), (1, False), (2, False)):
        leg = PL.plan_leg(REPO, axis, arm, block, smoke=smoke, workdir=tmp_path, reviewed_head="v" * 40,
                          production_ref="p" * 40, build="s2")
        tune = f"p426s2-{arm}-{'smoke' if smoke else f'b{block}'}"
        assert leg["tune"] == tune
        old = PL.plan_leg(REPO, axis, arm, block, smoke=smoke, workdir=tmp_path, reviewed_head="v" * 40, production_ref="p" * 40)
        assert old["tune"] == tune.replace("p426s2", "p426")  # `s` keeps today's names
        if axis == "m1":
            assert leg["out_dir"] == tmp_path / "p426" / "s2" / "m1" / tune
            assert old["out_dir"] == tmp_path / "p426" / "m1" / old["tune"]
        else:
            assert leg["stem"].endswith(tune) and leg["rows_path"].name.startswith(leg["stem"])
            assert tune in leg["driver_argv"] or tune in " ".join(leg["driver_argv"])


def test_the_leg_name_and_the_frozen_record_path_per_label(tmp_path):
    assert W.leg_name("math500", "off", "smoke") == "math500-p426-off-smoke"
    assert W.leg_name("math500", "off", "smoke", build="s") == "math500-p426-off-smoke"
    assert W.leg_name("m1", "on", 2, build="s2") == "m1-p426s2-on-b2"
    assert PL.leg_name("vision", "off", 1, "s2") == "vision-p426s2-off-b1"
    assert PL.frozen_path(tmp_path) == tmp_path / "p426" / "frozen.json"
    assert PL.frozen_path(tmp_path, "s") == tmp_path / "p426" / "frozen.json"
    assert PL.frozen_path(tmp_path, "s2") == tmp_path / "p426" / "frozen.s2.json"


def test_s_argv_is_byte_identical_and_a_label_argv_is_the_arms(tmp_path):
    root, wd, on, rd = tmp_path / "frozen", tmp_path / "wd", tmp_path / "on.yaml", tmp_path / "r"
    want = [str(root / ".venv-bench" / "bin" / "python"), "-m", "bench.p426_leg", "--axis", "vision", "--arm", "on", "--block", "1",
            "--stack-root", str(root), "--workdir", str(wd), "--registry-on", str(on), "--receipt-dir", str(rd)]
    assert W.leg_argv(root, wd, on, rd, "vision", "on", 1) == want
    assert W.leg_argv(root, wd, on, rd, "vision", "on", 1, build="s", stack_root_off=tmp_path / "off") == want
    off_wt, on_wt = tmp_path / "off", tmp_path / "on"
    on_argv = W.leg_argv(on_wt, wd, None, rd, "vision", "on", 1, build="s2", stack_root_off=off_wt)
    assert on_argv == [str(on_wt / ".venv-bench" / "bin" / "python"), "-m", "bench.p426_leg", "--axis", "vision", "--arm", "on",
                       "--block", "1", "--stack-root", str(on_wt), "--workdir", str(wd), "--receipt-dir", str(rd), "--build", "s2",
                       "--stack-root-off", str(off_wt)]
    off_argv = W.leg_argv(off_wt, wd, None, rd, "m1", "off", "smoke", build="s2", stack_root_off=off_wt)
    assert "--registry-on" not in off_argv and "--stack-root-off" not in off_argv and "--smoke" in off_argv
    assert off_argv[0] == str(off_wt / ".venv-bench" / "bin" / "python")


def test_isolation_a_labels_stems_never_match_another_labels_outputs(tmp_path):
    for axis, arm, block in (("math500", "off", 1), ("vision", "on", 2), ("reasoning", "off", 1)):
        s_leg = PL.plan_leg(REPO, axis, arm, block, results_root=tmp_path)
        s2_leg = PL.plan_leg(REPO, axis, arm, block, results_root=tmp_path, build="s2")
        tmp_path.joinpath(s_leg["tune"]).write_text("")  # keep tmp dir non-empty
        entry_dir = tmp_path / ENTRY
        entry_dir.mkdir(exist_ok=True)
        (entry_dir / f"{s_leg['stem']}.jsonl").write_text("{}\n")  # S's output sits where S′'s would be
        assert PL.existing_outputs(s2_leg) == []
        assert [p.name for p in PL.existing_outputs(s_leg)] == [f"{s_leg['stem']}.jsonl"]


def test_the_naming_exemption_covers_every_labelled_wave1_dossier():
    def violations(path):
        return modelnames.diff_violations(f"+++ b/{path}\n@@ -0,0 +1,1 @@\n+Nemotron Ornith gemma\n")  # allow-shorthand: the fixture feeds shorthands to the hook on purpose

    for path in ("benchmark/results/p426/wave1/x/leg.stdout", "benchmark/results/p426/wave1.s2/run/frozen.s2.json",
                 "benchmark/results/p426/wave1.abcdefgh/m/leg.stdout"):
        assert violations(path) == [], path
    for path in ("benchmark/results/p426/wave1.S2/x.txt", "benchmark/results/p426/wave1.toolong123/x.txt",
                 "benchmark/results/p426/wave1x/x.txt", "benchmark/results/p426/wave2.s2/x.txt", "docs/wave1.s2/x.md"):
        assert violations(path) != [], path


def test_the_panel_tunes_per_label():
    assert P.tunes() == ("p426-off", "p426-on") == (P.OFF_TUNE, P.ON_TUNE)
    assert P.tunes("s") == ("p426-off", "p426-on")
    assert P.tunes("s2") == ("p426s2-off", "p426s2-on")
    items = [("q1", "off text", "on text"), ("q2", "o2", "n2")]
    pairs = P.make_pairs(ENTRY, items, build="s2")
    assert all("@p426s2-on::" in p["a_key"] + p["b_key"] and "@p426s2-off::" in p["a_key"] + p["b_key"] for p in pairs)
    assert pairs == [dict(p) for p in P.make_pairs(ENTRY, items, build="s2")]
    old = P.make_pairs(ENTRY, items)
    assert all("@p426-on::" in p["a_key"] + p["b_key"] for p in old)
    on = f"{ENTRY}@p426s2-on::q1"
    off = f"{ENTRY}@p426s2-off::q1"
    rows = [dict(item_id="q1", choice="A", order="AB", a_key=on, b_key=off)]
    assert P.item_scores(rows, build="s2")["q1"]["score"] == 1.0
    assert P.item_scores(rows)["q1"]["score"] == 0.0  # S's panel does not read S′'s tunes as ON


# ------------------------------------------------------------------ harvest paths per label
def test_harvest_dossiers_and_run_files_per_label(tmp_path):
    home = tmp_path / "home" / "someuser"
    workdir, main = home / "wd", home / "repo"
    frozen, receipts = workdir / "wt", workdir / "r"
    res = frozen / "benchmark" / "results" / ENTRY
    for d in (res, main / "benchmark" / "results", receipts):
        d.mkdir(parents=True)
    scrub = H.Scrub(workdir=workdir, repo=main, home=home, user="someuser", hosts=("somebox",))
    name, stem = "math500-p426s2-off-smoke", "math500.p426s2-off-smoke"
    (res / f"{stem}.jsonl").write_text('{"id": "a"}\n')
    (receipts / f"{name}.receipt.json").write_text('{"verdict": "VALID"}')
    plan = dict(kind="rows", entry=ENTRY, stem=stem, results_dir=res)
    H.harvest(name, plan, main_root=main, receipts=receipts, stdout=b"", log_slice=b"x", scrub=scrub, build="s2")
    assert (main / "benchmark/results/p426/wave1.s2" / name / "SCRUB_MANIFEST.json").is_file()
    assert (main / "benchmark/results" / ENTRY / f"{stem}.jsonl").is_file()
    assert not (main / "benchmark/results/p426/wave1").exists()  # S's directory is never created or touched
    rec = workdir / "p426" / "frozen.s2.json"
    rec.parent.mkdir(parents=True)
    rec.write_text('{"build": "s2"}')
    H.harvest_run_files([rec], main_root=main, scrub=scrub, build="s2")
    assert (main / "benchmark/results/p426/wave1.s2/run/frozen.s2.json").read_text() == '{"build": "s2"}'
    assert not (main / "benchmark/results/p426/wave1").exists()
    assert H.wave1_dir("s") == H.WAVE1 and H.wave1_dir("s2") == H.WAVE1.with_name("wave1.s2")
    with pytest.raises(ValueError):
        H.wave1_dir("S2")


# ------------------------------------------------------------------ the sequencer: arguments, marker, resume per label
def _main(tmp_path, monkeypatch, *args, workdir=None):
    wd = workdir or tmp_path / "wd"
    wd.mkdir(exist_ok=True)
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    return W.main(["--main-root", str(tmp_path / "main"), "--workdir", str(wd), "--out", str(tmp_path / "out"), *map(str, args)])


def test_the_sequencer_requires_a_build(tmp_path, monkeypatch, capsys):
    rc = _main(tmp_path, monkeypatch, "--stack-root", tmp_path / "s", "--registry-on", tmp_path / "on.yaml")
    assert rc == 2 and "--build" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "extra, why",
    [(("--build", "S2"), "build label"),
     (("--build", "s2", "--stack-root-off", "o", "--stack-root-on", "n", "--registry-on", "x.yaml"), "not allowed ['--registry-on']"),
     (("--build", "s2", "--stack-root-off", "o"), "missing ['--stack-root-on']"),
     (("--build", "s2", "--stack-root", "r", "--stack-root-off", "o", "--stack-root-on", "n"), "not allowed ['--stack-root']"),
     (("--build", "s", "--stack-root", "r"), "missing ['--registry-on']"),
     (("--build", "s", "--stack-root", "r", "--registry-on", "x", "--stack-root-off", "o"), "not allowed ['--stack-root-off']")],
)
def test_the_sequencers_argument_rules(tmp_path, monkeypatch, capsys, extra, why):
    assert _main(tmp_path, monkeypatch, *extra) == 2
    assert why in capsys.readouterr().err
    assert not (tmp_path / "out").exists()  # refused before anything is created


def test_the_out_marker(tmp_path):
    out = tmp_path / "o"
    assert W.claim_out(out, "s2") is None and (out / ".build").read_text().strip() == "s2"  # a first start writes it
    assert W.claim_out(out, "s2") is None  # and a restart accepts it
    assert "belongs to build 's2'" in W.claim_out(out, "s3")
    assert "belongs to build 's2'" in W.claim_out(out, "s")  # S never adopts a label's directory
    s_out = tmp_path / "s_out"
    (s_out / "receipts").mkdir(parents=True)
    (s_out / "receipts" / "math500-p426-off-smoke.receipt.json").write_text("{}")
    assert "no .build marker" in W.claim_out(s_out, "s2")  # S's receipts without a marker refuse
    assert not (s_out / ".build").exists()
    log_only = tmp_path / "log_only"
    log_only.mkdir()
    (log_only / "sequence.log").write_text("x\n")
    assert "no .build marker" in W.claim_out(log_only, "s2")
    assert W.claim_out(s_out, "s") is None and not (s_out / ".build").exists()  # `s` is as today: no marker, no refusal
    empty = tmp_path / "empty"
    empty.mkdir()
    assert W.claim_out(empty, "s2") is None


class Box:
    def __init__(self, tmp_path, build):
        self.build, self.dir, self.t, self.launched, self.harvested = build, tmp_path / "receipts", 0.0, [], []

    def launch(self, leg):
        name = W.leg_name(*leg, build=self.build)
        self.launched.append(name)
        self.t += 1800
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{name}.receipt.json").write_text(json.dumps(dict(name=name, verdict="VALID")))
        return 0

    def run(self, legs=None):
        legs = legs or W.schedule()
        self.log = []
        return W.run(legs, launch=self.launch, read_verdict=lambda n: W.receipt_verdict(self.dir, n), sleep=lambda s: setattr(self, "t", self.t + s),
                     clock=lambda: self.t, paused=lambda: False, log=self.log.append, idle_s=600.0,
                     harvest=lambda leg: self.harvested.append(W.leg_name(*leg, build=self.build)),
                     harvested=lambda n: n in self.harvested, build=self.build)


def test_resume_reads_only_its_own_labels_receipts(tmp_path):
    s2 = Box(tmp_path, "s2")
    s_names = [W.leg_name(*leg) for leg in W.schedule()]
    s2.dir.mkdir(parents=True)
    for n in s_names:  # S's receipts (VALID and not) sit in the same directory and are never read
        (s2.dir / f"{n}.receipt.json").write_text(json.dumps(dict(name=n, verdict="INVALID")))
        (s2.dir / f"{n}.refused-1.receipt.json").write_text(json.dumps(dict(name=n, verdict="NOT_STARTED")))
    assert s2.run() == 0
    assert s2.launched == [W.leg_name(*leg, build="s2") for leg in W.schedule()] and len(s2.launched) == 30
    assert all("p426s2" in n for n in s2.launched)
    resumed = Box(tmp_path, "s2")  # a second sequencer under the label resumes: VALID + harvested legs skip, others stop
    resumed.harvested = list(s2.harvested[:5])
    (resumed.dir / f"{W.leg_name(*W.schedule()[5], build='s2')}.receipt.json").write_text(
        json.dumps(dict(verdict="INVALID")))
    assert resumed.run() == 1 and resumed.launched == []


# ------------------------------------------------------------------ expected build and the frozen record
def _venv(root, venv, mlx="0.32.4", **versions):
    pk = dict(mlx=mlx, mlx_metal=mlx, transformers="5.15.0", huggingface_hub="1.12.0", datasets="5.0.1", mlx_audio="0.6.2", **versions)
    site = Path(root) / venv / "lib" / "python3.12" / "site-packages"
    for old in site.glob("*.dist-info") if site.exists() else ():
        old.rmdir()
    for name, version in pk.items():
        (site / f"{name}-{version}.dist-info").mkdir(parents=True, exist_ok=True)


def _git(cwd, *args, check=True):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.invalid", GIT_AUTHOR_DATE="2026-10-27T00:00:00", GIT_COMMITTER_DATE="2026-10-27T00:00:00")
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env=env)
    assert not check or r.returncode == 0, r.stderr
    return r.stdout.strip()


SEEDING = "benchmark/bench/tests/test_opencode_probe_seeding.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "p426_off"  # copies of commit 10014b4a's files (C246), never the live tree
REG_OFF_SHA256 = "7739900f0f7ffe501af1e0b7c6a6b517265c2761f45420c7e9e7133f7c1cf572"
SEED_OFF_SHA256 = "8f8d25f444c465f25b408e1c872cf4beb3d705356d817240748f511e3e7713c6"


def _pinned(name, sha256):
    data = (FIXTURE / name).read_bytes()
    got = hashlib.sha256(data).hexdigest()
    assert got == sha256, f"pinned OFF fixture {name} changed: sha256 {got}, expected {sha256}"
    return data.decode()


REG_OFF = _pinned("main_models.yaml", REG_OFF_SHA256)  # the fork's overlay rule accepts only its real states
SEED_OFF = _pinned("test_opencode_probe_seeding.py.txt", SEED_OFF_SHA256)
NOTE = "      # PROVISIONAL P426 2026-10-27: MTP ON restored for the Wave-1 rerun on S2 (C236)"
C177_COMMENT = ("    # C177 / P369 interim: the daily-driver registry runs the picks MTP-OFF, so the real registry resolves the default\n"
                "    # scan; restore `joint_v1` + source \"registry\" when MTP is re-certified and switched back on.\n")
SEED_PER_QUERY = '    assert man["runtime"]["mtp_verify_scan"] == "per_query"\n'
SEED_RESTORED = ('    assert man["runtime"]["mtp_verify_scan"] == "joint_v1"\n'
                 '    assert man["runtime"]["mtp_verify_scan_source"] == "registry"\n')
FORK_FILES = ("dev/p369_phase2/registry_states.py", "mlx_vlm/tests/fixtures/stack_registry_golden.yaml")


def expected_on_registry(off_text, note=NOTE):
    """The fork's overlay rule (the B4 rule, from the fork checkout) + `note` as the first child of the entry's generation_defaults."""
    rs = p426_overlay.load_registry_states(REPO)
    on_text, _ = rs.overlay_on(off_text, rs.fixture_text(REPO / "src/mlx-vlm/mlx_vlm/tests/fixtures"), ENTRY)
    lines = on_text.split("\n")
    start = next(i for i, line in enumerate(lines) if line == f"  - name: {ENTRY}")
    gd = next(i for i in range(start, len(lines)) if lines[i] == "    generation_defaults:")
    lines.insert(gd + 1, note)
    return "\n".join(lines)


def expected_on_seeding(off_text):
    assert off_text.count(C177_COMMENT + SEED_PER_QUERY) == 1
    return off_text.replace(C177_COMMENT + SEED_PER_QUERY, SEED_RESTORED)


REG_ON = expected_on_registry(REG_OFF)
SEED_ON = expected_on_seeding(SEED_OFF)


def _write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


@pytest.fixture
def arms(tmp_path, monkeypatch):
    return _arms_with(tmp_path, monkeypatch)


def _arms_with(tmp_path, monkeypatch, reg_on=REG_ON, seed_on=SEED_ON):
    """OFF worktree (a repo with the committed registry, locks, two nested fork repos, both venvs) and ON = OFF + the restore
    commit in a linked worktree; the label's expected fork pins are monkeypatched to the nested repos' heads."""
    off, on = tmp_path / "wt-off", tmp_path / "wt-on"
    off.mkdir()
    _git(off, "init", "-q", "-b", "main")
    (off / ".git" / "info").mkdir(exist_ok=True)
    (off / ".git" / "info" / "exclude").write_text("src/\n.venv/\n.venv-bench/\n")
    _write(off, "main_models.yaml", REG_OFF)
    _write(off, SEEDING, SEED_OFF)
    _write(off, "uv.lock", "lock\n")
    _write(off, "benchmark/requirements-bench.lock", "bench lock\n")
    _write(off, "README.md", "readme\n")
    _git(off, "add", "-A")
    _git(off, "commit", "-q", "-m", "off")
    for fork in ("mlx-vlm", "mlx-serve"):
        nested = off / "src" / fork
        nested.mkdir(parents=True)
        _git(nested, "init", "-q")
        _write(nested, "f", fork)
        if fork == "mlx-vlm":
            for rel in FORK_FILES:
                _write(nested, rel, (REPO / "src" / "mlx-vlm" / rel).read_text())
        _git(nested, "add", "-A")
        _git(nested, "commit", "-q", "-m", fork)
    _git(off, "worktree", "add", "-q", "-b", "p426-on-test", str(on))
    for fork in ("mlx-vlm", "mlx-serve"):
        subprocess.run(["git", "clone", "-q", str(off / "src" / fork), str(on / "src" / fork)], check=True, capture_output=True)
    _write(on, "main_models.yaml", reg_on)
    _write(on, SEEDING, seed_on)
    _git(on, "add", "-A")
    _git(on, "commit", "-q", "-m", "restore")
    for root in (off, on):
        for venv in PL.VENVS:
            _venv(root, venv)
    expected = dict(PL.EXPECTED_BUILDS["s2"], mlx_vlm=_git(off / "src/mlx-vlm", "rev-parse", "HEAD"),
                    mlx_serve=_git(off / "src/mlx-serve", "rev-parse", "HEAD"))
    monkeypatch.setitem(PL.EXPECTED_BUILDS, "s2", expected)
    return off, on


def _record(off, on, **override):
    so, sn = PL.arm_state(off), PL.arm_state(on)
    exp = PL.EXPECTED_BUILDS["s2"]
    rec = dict(build="s2", stack_head_off=so["stack_head"], stack_head_on=sn["stack_head"], stack_clean_off=so["stack_clean"],
               stack_clean_on=sn["stack_clean"], mlx_vlm=exp["mlx_vlm"], mlx_serve=exp["mlx_serve"],
               production_ref=exp["production_ref"], registry_off_sha=so["registry_sha"], registry_on_sha=sn["registry_sha"],
               uv_lock_sha256=so["uv_lock_sha256"], bench_lock_sha256=so["bench_lock_sha256"],
               venvs=dict(off=so["venvs"], on=sn["venvs"]))
    return dict(rec, **override)


def test_the_real_expected_build_of_s2_is_in_code():
    exp = PL.EXPECTED_BUILDS["s2"]
    assert exp == dict(mlx_vlm="1c7c8fa166582ac1a1c23ae9063527b2b5215b11", mlx_serve="1ddf6f842f159a62d240f3ac6965fc33cbdb0b0d",
                       production_ref="b26fa7c9faf23bc3167db3419504ef0b2b82a8e6", mlx="0.32.4")
    assert "s" not in PL.EXPECTED_BUILDS  # S's record is its own truth (no new check)


def test_a_complete_record_of_the_build_has_no_problems(arms):
    assert PL.record_problems(_record(*arms), "s2") == []
    assert W.label_problems("s2", Path("/nonexistent-wd"), *arms)  # (the record file is missing: reported, not raised)


@pytest.mark.parametrize(
    "override, why",
    [(dict(mlx_vlm="a" * 40), "mlx_vlm"), (dict(mlx_serve="a" * 40), "mlx_serve"), (dict(production_ref="a" * 40), "production_ref"),
     (dict(build="s"), "record build"), (dict(stack_clean_on=False), "stack_clean_on"), (dict(stack_head_on="short"), "stack_head_on"),
     (dict(uv_lock_sha256=None), "uv_lock_sha256"), (dict(registry_on_sha=None), "registry_on_sha")],
)
def test_a_self_consistent_record_of_another_build_refuses(arms, override, why):
    """The record is consistent with the trees (made from them), yet its pins are not the label's expected build."""
    problems = PL.record_problems(_record(*arms, **override), "s2")
    assert problems and any(why in p for p in problems), problems


def test_an_unknown_label_has_no_expected_build(arms):
    assert any("no expected build" in p for p in PL.record_problems(_record(*arms), "s9"))


@pytest.mark.parametrize("arm, venv, pkg, version", [("on", ".venv", "mlx", "0.32.3"), ("off", ".venv-bench", "mlx-metal", "0.32.3")])
def test_a_venv_with_the_wrong_mlx_refuses(arms, arm, venv, pkg, version):
    rec = _record(*arms)
    rec["venvs"][arm][venv][pkg] = version
    assert any(f"venvs.{arm}.{venv}.{pkg}" in p for p in PL.record_problems(rec, "s2"))


def test_a_missing_venv_package_refuses(arms):
    rec = _record(*arms)
    rec["venvs"]["off"][".venv"]["datasets"] = None
    assert any("venvs.off..venv.datasets missing" in p for p in PL.record_problems(rec, "s2"))


def test_the_live_worktrees_match_a_record_made_from_them(arms):
    off, on = arms
    rec = _record(off, on)
    assert PL.arm_problems(rec, "off", off) == [] and PL.arm_problems(rec, "on", on) == []
    assert PL.arm_problems(rec, "on", off), "the OFF worktree is not the ON arm"
    state = PL.arm_state(on)
    assert state["venvs"][".venv"]["mlx-metal"] == "0.32.4" and state["venvs"][".venv-bench"]["mlx-audio"] == "0.6.2"


def test_live_drift_is_found_per_arm(arms):
    off, on = arms
    rec = _record(off, on)
    _venv(on, ".venv", mlx="0.32.3")
    assert any("venvs" in p for p in PL.arm_problems(rec, "on", on)) and PL.arm_problems(rec, "off", off) == []
    _venv(on, ".venv")
    (on / ".venv" / "lib" / "python3.12" / "site-packages" / "mlx-0.32.3.dist-info").mkdir()  # V4: two dist-infos of mlx
    ambiguous = PL.arm_problems(rec, "on", on)
    assert any("venvs" in p and "more than one dist-info" in p for p in ambiguous), ambiguous
    _venv(on, ".venv")
    _write(off, "README.md", "dirty\n")  # a tracked change
    assert any("stack_clean" in p for p in PL.arm_problems(rec, "off", off))
    _git(off, "checkout", "--", "README.md")
    _write(off, "uv.lock", "another lock\n")
    assert any("uv_lock_sha256" in p for p in PL.arm_problems(rec, "off", off))
    _git(off, "checkout", "--", "uv.lock")
    _write(off, "untracked-output.txt", "generated\n")  # untracked files are the stem refusal's, not the tree check's
    assert PL.arm_problems(rec, "off", off) == []


# ------------------------------------------------------------------ arms as commits: the restore diff, at patch level
def test_the_restore_commit_diff_is_accepted(arms):
    assert PL.restore_diff_problems(*arms, ENTRY) == []


@pytest.mark.parametrize("note", ["      # PROVISIONAL P426", "      # PROVISIONAL P426 any free text: 2026-10-27, C236"])
def test_the_note_may_carry_free_text_or_none(tmp_path, monkeypatch, note):
    off, on = _arms_with(tmp_path, monkeypatch, reg_on=expected_on_registry(REG_OFF, note))
    assert PL.restore_diff_problems(off, on, ENTRY) == []


def _amend(on, rel, text):
    _write(on, rel, text)
    _git(on, "add", "-A")
    _git(on, "commit", "-q", "--amend", "--no-edit")


def _first_diff_line(a, b):
    """1-based number of the first line where two texts differ."""
    x, y = a.split("\n"), b.split("\n")
    return next(i + 1 for i in range(max(len(x), len(y))) if i >= len(x) or i >= len(y) or x[i] != y[i])


def _lines_edit(text, fn):
    lines = text.split("\n")
    fn(lines)
    return "\n".join(lines)


def _entry_line(lines, wanted):
    start = next(i for i, line in enumerate(lines) if line == f"  - name: {ENTRY}")
    return next(i for i in range(start, len(lines)) if lines[i].startswith(wanted))


def _note_idx(lines):
    return next(i for i, line in enumerate(lines) if "PROVISIONAL P426" in line)


def _trailing_comment(lines):
    lines[_entry_line(lines, "    draft_kind: mtp")] += "  # a trailing comment"


def _move_restored_line(lines):
    i, j = _entry_line(lines, "    mtp_verify_scan: joint_v1"), _entry_line(lines, "    draft_model: caslca")
    lines.insert(j, lines.pop(i))


def _second_note(lines):
    i = _note_idx(lines)
    lines.insert(i + 1, lines[i])


def _note_after_the_restored_lines(lines):
    i = _note_idx(lines)
    lines.insert(_entry_line(lines, "    draft_kind: mtp"), lines.pop(i))


def _note_above_generation_defaults(lines):
    i = _note_idx(lines)
    lines.insert(_entry_line(lines, "    generation_defaults:"), lines.pop(i))


def _note_wrong_indent(lines):
    i = _note_idx(lines)
    lines[i] = "    " + lines[i].lstrip()


def _note_other_text(lines):
    lines[_note_idx(lines)] = "      # NOTE P426 restored"


def _no_note(lines):
    del lines[_note_idx(lines)]


def _changed_setting(lines):
    lines[next(i for i, line in enumerate(lines) if line.startswith("mlx_port:"))] += " "


REGISTRY_CASES = [
    ("a trailing comment on a restored line", _trailing_comment),
    ("a restored line moved", _move_restored_line),
    ("two notes", _second_note),
    ("a note after the restored lines", _note_after_the_restored_lines),
    ("a note above generation_defaults", _note_above_generation_defaults),
    ("a note at the wrong indentation", _note_wrong_indent),
    ("a note without the PROVISIONAL P426 text", _note_other_text),
    ("no note", _no_note),
    ("an unrelated line changed", _changed_setting),
]


@pytest.mark.parametrize("why, edit", REGISTRY_CASES, ids=[c[0] for c in REGISTRY_CASES])
def test_the_registry_restore_must_be_exact_bytes(arms, why, edit):
    off, on = arms
    changed = _lines_edit(REG_ON, edit)
    assert changed != REG_ON
    _amend(on, "main_models.yaml", changed)
    problems = PL.restore_diff_problems(off, on, ENTRY)
    n = _first_diff_line(changed, REG_ON)
    assert any("main_models.yaml" in p and f"line {n}:" in p for p in problems), (n, problems)


def _seed_comment_added(t):
    return t + "    # one more comment\n"


def _seed_comment_removed(t):
    return t.replace("    # No fake_model_mtp_scan fixture: the real resolver must leave this model unresolved.\n", "")


def _seed_extra_joint_v1(t):
    return t + '    assert "joint_v1" is not None\n'


def _seed_comment_kept(t):
    return t.replace(SEED_RESTORED, C177_COMMENT + SEED_RESTORED)


def _seed_other_source(t):
    return t.replace('_source"] == "registry"', '_source"] == "other"')


def _seed_tuple_form(t):
    return t.replace(SEED_RESTORED, '    assert (man["runtime"]["mtp_verify_scan"], man["runtime"]["mtp_verify_scan_source"]) == ("joint_v1", "registry")\n')


SEED_CASES = [
    ("a comment hunk added", _seed_comment_added),
    ("a comment hunk removed", _seed_comment_removed),
    ("an extra added code line containing joint_v1", _seed_extra_joint_v1),
    ("the C177 comment kept", _seed_comment_kept),
    ("another source", _seed_other_source),
    ("the assertions as one tuple", _seed_tuple_form),
]


@pytest.mark.parametrize("why, edit", SEED_CASES, ids=[c[0] for c in SEED_CASES])
def test_the_seeding_test_restore_must_be_exact_bytes(arms, why, edit):
    off, on = arms
    changed = edit(SEED_ON)
    assert changed != SEED_ON
    _amend(on, SEEDING, changed)
    problems = PL.restore_diff_problems(off, on, ENTRY)
    n = _first_diff_line(changed, SEED_ON)
    assert any(SEEDING in p and f"line {n}:" in p for p in problems), (n, problems)


@pytest.mark.parametrize("rel, change", [("README.md", lambda t: t + "x\n"), ("benchmark/new_file.py", lambda t: "x = 1\n")])
def test_any_other_file_in_the_restore_commit_refuses(arms, rel, change):
    off, on = arms
    path = on / rel
    _amend(on, rel, change(path.read_text() if path.exists() else ""))
    assert any("changes" in p for p in PL.restore_diff_problems(off, on, ENTRY))


def test_the_restore_must_be_exactly_one_commit_above_the_off_head(arms):
    off, on = arms
    _write(on, "README.md", "another commit\n")
    _git(on, "add", "-A")
    _git(on, "commit", "-q", "-m", "extra")
    assert any("exactly one commit" in p for p in PL.restore_diff_problems(off, on, ENTRY))


def test_a_mode_change_in_the_restore_commit_refuses(arms):
    off, on = arms
    _git(on, "update-index", "--chmod=+x", "main_models.yaml")
    _git(on, "commit", "-q", "--amend", "--no-edit")
    assert any("mode" in p for p in PL.restore_diff_problems(off, on, ENTRY))


def test_the_restore_with_the_three_lines_missing_refuses(arms):
    off, on = arms
    only_note = _lines_edit(REG_OFF, lambda lines: lines.insert(_entry_line(lines, "    generation_defaults:") + 1, NOTE))
    _amend(on, "main_models.yaml", only_note)
    problems = PL.restore_diff_problems(off, on, ENTRY)
    assert any("main_models.yaml" in p and "line " in p for p in problems), problems


# ------------------------------------------------------------------ the sequencer end to end (no process is started)
def _frozen_record(tmp_path, arms_, **override):
    wd = tmp_path / "wd"
    (wd / "p426").mkdir(parents=True, exist_ok=True)
    rec = _record(*arms_, **override)
    (wd / "p426" / "frozen.s2.json").write_text(json.dumps(rec))
    return wd


def _args(tmp_path, off, on, *extra):
    return ["--build", "s2", "--stack-root-off", str(off), "--stack-root-on", str(on), "--main-root", str(tmp_path / "main"),
            "--workdir", str(tmp_path / "wd"), "--out", str(tmp_path / "out"), *extra]


def _main_tree(tmp_path):
    main = tmp_path / "main"
    (main / "benchmark" / "results" / "p426" / "wave1" / "run").mkdir(parents=True)
    (main / "benchmark" / "results" / "p426" / "wave1" / "run" / "frozen.json").write_text('{"S": true}')
    return main


def _tree_snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(Path(root).rglob("*")) if p.is_file()}


def test_a_copied_s_record_is_refused_before_any_harvest_or_launch(tmp_path, monkeypatch, arms):
    """Failure path 1: `frozen.json` copied as `frozen.s2.json` → refused for the expected-build mismatch, nothing harvested or
    launched, rc 1, nothing of S touched."""
    main = _main_tree(tmp_path)
    wd = tmp_path / "wd"
    (wd / "p426").mkdir(parents=True)
    s_record = dict(stack_head="a" * 40, stack_clean=True, mlx_vlm="b" * 40, mlx_serve="c" * 40, production_ref="d" * 40)
    (wd / "p426" / "frozen.s2.json").write_text(json.dumps(s_record))
    (wd / "p426" / "frozen.json").write_text(json.dumps(s_record))
    before = _tree_snapshot(main)
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    launched = []
    monkeypatch.setattr(W, "run", lambda *a, **k: launched.append(1) or 0)
    monkeypatch.setattr(W, "subprocess", types.SimpleNamespace(Popen=lambda *a, **k: launched.append(a),
                                                               TimeoutExpired=subprocess.TimeoutExpired))
    assert W.main(_args(tmp_path, *arms)) == 1
    assert launched == [] and _tree_snapshot(main) == before
    assert not (main / "benchmark/results/p426/wave1.s2").exists()
    log = (tmp_path / "out" / "sequence.log").read_text()
    assert "refused" in log and "expected" in log and (tmp_path / "out" / ".build").read_text().strip() == "s2"
    assert (wd / "p426" / "frozen.json").read_text() == json.dumps(s_record)


def test_a_missing_label_record_refuses_for_the_missing_file(tmp_path, monkeypatch, arms):
    main = _main_tree(tmp_path)
    (tmp_path / "wd" / "p426").mkdir(parents=True)
    (tmp_path / "wd" / "p426" / "frozen.json").write_text("{}")  # S's record exists; it is never read in its place
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "wd"))
    assert W.main(_args(tmp_path, *arms)) == 1
    assert "frozen.s2.json is missing" in (tmp_path / "out" / "sequence.log").read_text()
    assert not (main / "benchmark/results/p426/wave1.s2").exists()


def test_an_on_worktree_with_an_extra_change_refuses_before_the_first_leg(tmp_path, monkeypatch, arms):
    off, on = arms
    _amend(on, "README.md", "an extra change\n")
    wd = _frozen_record(tmp_path, arms)
    main = _main_tree(tmp_path)
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    monkeypatch.setattr(W, "run", lambda *a, **k: pytest.fail("a leg was scheduled"))
    assert W.main(_args(tmp_path, off, on)) == 1
    assert "README.md" in (tmp_path / "out" / "sequence.log").read_text()
    assert not (main / "benchmark/results/p426/wave1.s2").exists()  # validation precedes the run-file harvest


def test_a_worktree_whose_venv_has_the_old_mlx_refuses(tmp_path, monkeypatch, arms):
    off, on = arms
    wd = _frozen_record(tmp_path, arms)
    _venv(off, ".venv", mlx="0.32.3")  # failure path 3 at the sequencer; the leg re-checks it (below)
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    monkeypatch.setattr(W, "run", lambda *a, **k: pytest.fail("a leg was scheduled"))
    assert W.main(_args(tmp_path, off, on)) == 1
    assert "venvs" in (tmp_path / "out" / "sequence.log").read_text()


def test_a_valid_label_run_serves_each_leg_from_its_arms_worktree(tmp_path, monkeypatch, arms):
    off, on = arms
    wd = _frozen_record(tmp_path, arms)
    main = _main_tree(tmp_path)
    before_s = _tree_snapshot(main / "benchmark/results/p426/wave1")
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    spawned = []

    class Proc:
        pid = 4242

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(W, "subprocess", types.SimpleNamespace(
        Popen=lambda argv, **kw: spawned.append((argv, kw["cwd"])) or Proc(), TimeoutExpired=subprocess.TimeoutExpired,
        DEVNULL=subprocess.DEVNULL, STDOUT=subprocess.STDOUT))

    def fake_run(legs, *, launch, build, **kw):
        assert build == "s2" and len(legs) == 30 and legs[0] == ("math500", "off", "smoke")
        for leg in (("math500", "off", "smoke"), ("math500", "on", "smoke"), ("m1", "on", 2)):
            assert launch(leg) == 0
        return 0

    monkeypatch.setattr(W, "run", fake_run)
    assert W.main(_args(tmp_path, off, on)) == 0
    roots = {"off": off.resolve(), "on": on.resolve()}
    assert [Path(c) for _, c in spawned] == [roots["off"] / "benchmark", roots["on"] / "benchmark", roots["on"] / "benchmark"]
    for (argv, _), arm in zip(spawned, ("off", "on", "on")):
        assert argv[0] == str(roots[arm] / ".venv-bench" / "bin" / "python")
        assert argv[argv.index("--stack-root") + 1] == str(roots[arm]) and argv[argv.index("--build") + 1] == "s2"
        assert "--registry-on" not in argv
    assert spawned[1][0][spawned[1][0].index("--stack-root-off") + 1] == str(roots["off"])
    assert (main / "benchmark/results/p426/wave1.s2/run/frozen.s2.json").is_file()  # the label's own run directory
    assert _tree_snapshot(main / "benchmark/results/p426/wave1") == before_s  # S's evidence is byte-unchanged
    assert (wd / "p426" / "frozen.s2.json").is_file()
    assert (tmp_path / "out" / ".build").read_text().strip() == "s2"
    assert main_tree_has_no_s_names(main)


def main_tree_has_no_s_names(main):
    return not [p for p in (main / "benchmark/results/p426/wave1.s2").rglob("*") if "-p426-" in p.name]


# ------------------------------------------------------------------ the leg under a label
def _label_spec(tmp_path, arms_, arm="on", **kw):
    off, on = arms_
    spec = TL._spec(tmp_path, arm=arm)
    rec = _record(off, on)
    spec.build = "s2"
    spec.name = PL.leg_name("math500", arm, 1, "s2")
    spec.pins = dict(rec, frozen_sha="f" * 64)
    spec.off_registry_text = (off / "main_models.yaml").read_text()
    spec.registry_text = (on if arm == "on" else off).joinpath("main_models.yaml").read_text()
    return spec


def _state(arms_, arm, **override):
    root = arms_[1] if arm == "on" else arms_[0]
    full = PL.arm_state(root)
    state = {k: full[k] for k in ("stack_head", "stack_clean", "mlx_vlm", "mlx_serve", "uv_lock_sha256", "bench_lock_sha256", "venvs")}
    return {**state, "frozen_sha": "f" * 64, **override}


class _CapturingRun:
    """TL._run with the label's registry on the router and the driver's env captured."""

    def __init__(self):
        self.env = None


def _run_leg(tmp_path, spec, arms_, *, states, ops=None):
    ops = ops or TL.FakeOps()
    ops.router_config_sha = L.sha256_text(spec.registry_text)
    seen = {}
    log_lines = TL._log_for(spec._test_rows)
    ops.cmdline = (f"202 python -m mlx_vlm.server --model caslca/{TL.ENTRY} --draft-kind mtp "
                   f"--draft-model caslca/{TL.ENTRY}-mtp-drafter --mtp-verify-scan joint_v1") if spec.arm == "on" else None
    spec.server_log.write_text("")

    def driver(argv, env, timeout, cwd=None):
        seen["env"], seen["cwd"] = env, cwd
        spec.rows_path.write_text("".join(json.dumps(r) + "\n" for r in spec._test_rows))
        with spec.server_log.open("a") as f:
            f.write("\n".join(log_lines) + "\n")
        return 0

    receipt = L.run_leg(spec, ops, run_driver=driver, pins_check=lambda m, a: [], watcher=lambda s: (lambda: dict(
        power_failure=None, exited_early=False, ticks=20)), battery_intervals=lambda s, e: ([], []),
        clock=iter(["2026-10-22 01:00:00", "2026-10-22 02:00:00"]).__next__, repo_state=iter(states).__next__)
    return receipt, seen, ops


@pytest.mark.parametrize("arm", ["on", "off"])
def test_a_label_leg_runs_valid_under_its_names_and_session_prefix(tmp_path, arms, arm):
    spec = _label_spec(tmp_path, arms, arm=arm)
    state = _state(arms, arm)
    receipt, seen, _ = _run_leg(tmp_path, spec, arms, states=[state, state])
    assert receipt["verdict"] == "VALID", receipt["problems"]
    assert spec.name == f"math500-p426s2-{arm}-b1"
    assert seen["env"]["MLX_BENCH_SESSION_PREFIX"] == f"p426-math500-p426s2-{arm}-b1"
    assert Path(receipt["_path"]).name == f"math500-p426s2-{arm}-b1.receipt.json"


def test_a_label_leg_whose_head_is_the_other_arms_refuses(tmp_path, arms):
    """K2 under a label: the ON leg's live head is compared with `stack_head_on`, the OFF leg's with `stack_head_off`."""
    spec = _label_spec(tmp_path, arms, arm="on")
    wrong = _state(arms, "off")  # the OFF worktree presented to the ON leg
    receipt, _, ops = _run_leg(tmp_path, spec, arms, states=[wrong])
    assert receipt["verdict"] == "NOT_STARTED" and "start_router" not in ops.calls
    assert any("stack_head" in p for p in receipt["problems"])


def test_a_label_leg_with_the_old_mlx_in_its_venv_refuses(tmp_path, arms):
    off, on = arms
    spec = _label_spec(tmp_path, arms, arm="on")
    state = _state(arms, "on")
    state["venvs"] = dict(state["venvs"], **{".venv": dict(state["venvs"][".venv"], mlx="0.32.3")})
    receipt, _, ops = _run_leg(tmp_path, spec, arms, states=[state])
    assert receipt["verdict"] == "NOT_STARTED" and "start_router" not in ops.calls
    assert any("venvs" in p for p in receipt["problems"])


@pytest.mark.parametrize("key, value", [("uv_lock_sha256", "0" * 64), ("bench_lock_sha256", "0" * 64), ("stack_clean", False),
                                        ("mlx_vlm", "9" * 40), ("mlx_serve", "9" * 40), ("frozen_sha", "1" * 64)])
def test_every_k2_check_compares_the_live_state_at_entry(tmp_path, arms, key, value):
    spec = _label_spec(tmp_path, arms, arm="off")
    receipt, _, ops = _run_leg(tmp_path, spec, arms, states=[_state(arms, "off", **{key: value})])
    assert receipt["verdict"] == "NOT_STARTED" and any(key in p for p in receipt["problems"])


def test_a_label_leg_invalidates_on_drift_at_exit(tmp_path, arms):
    spec = _label_spec(tmp_path, arms, arm="off")
    drifted = dict(_state(arms, "off"), venvs={v: dict(p, mlx="0.32.3") for v, p in _state(arms, "off")["venvs"].items()})
    receipt, _, _ = _run_leg(tmp_path, spec, arms, states=[_state(arms, "off"), drifted])
    assert receipt["verdict"] == "INVALID" and any("drift" in p for p in receipt["problems"])


def test_the_committed_on_registry_with_its_note_passes_only_under_a_label(tmp_path, arms):
    spec = _label_spec(tmp_path, arms, arm="on")
    assert L.registry_delta_problems(spec.registry_text, spec.off_registry_text, ENTRY, allow_added_comments=True) == []
    assert L.registry_delta_problems(spec.registry_text, spec.off_registry_text, ENTRY)  # under `s` an added note refuses
    spec.build = "s"
    spec.pins = dict(TL.PINS, registry_off_sha=L.sha256_text(spec.off_registry_text), registry_on_sha=L.sha256_text(spec.registry_text))
    receipt, _, _ = _run_leg(tmp_path, spec, arms, states=[dict(TL.PINS)])
    assert receipt["verdict"] == "NOT_STARTED" and any("added lines" in p for p in receipt["problems"])


def test_a_label_on_registry_with_a_foreign_change_refuses(tmp_path, arms):
    spec = _label_spec(tmp_path, arms, arm="on")
    spec.registry_text = spec.registry_text.replace("kv_bits: 0", "kv_bits: 4")
    problems = L.registry_delta_problems(spec.registry_text, spec.off_registry_text, ENTRY, allow_added_comments=True)
    assert any("kv_bits" in p for p in problems)


def test_the_label_leg_cli_refuses_the_retired_overlay_and_a_missing_record(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "wd"))
    (tmp_path / "wd").mkdir()
    base = ["--axis", "math500", "--arm", "on", "--block", "1", "--stack-root", str(tmp_path / "wt"), "--workdir",
            str(tmp_path / "wd"), "--receipt-dir", str(tmp_path / "rc"), "--build", "s2"]
    assert L.main([*base, "--registry-on", str(tmp_path / "on.yaml")]) == 2
    doc = json.loads((tmp_path / "rc" / "math500-p426s2-on-b1.receipt.json").read_text())
    assert doc["verdict"] == "NOT_STARTED" and any("--registry-on is retired" in p for p in doc["problems"])
    assert L.main(base) == 2  # no frozen.s2.json: refused for the missing file
    refused = sorted((tmp_path / "rc").glob("math500-p426s2-on-b1.refused-*.receipt.json"))
    assert refused and any("frozen.s2.json is missing" in p for p in json.loads(refused[-1].read_text())["problems"])
    assert not list((tmp_path / "rc").glob("*p426-on-b1*"))  # no S-named file is written


def test_the_label_leg_cli_refuses_an_s_record_copied_for_the_label(tmp_path, monkeypatch):
    wd = tmp_path / "wd"
    (wd / "p426").mkdir(parents=True)
    (wd / "p426" / "frozen.s2.json").write_text(json.dumps(dict(stack_head="a" * 40, mlx_vlm="b" * 40)))
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    rc = L.main(["--axis", "math500", "--arm", "off", "--smoke", "--stack-root", str(tmp_path / "wt"), "--workdir", str(wd),
                 "--receipt-dir", str(tmp_path / "rc"), "--build", "s2"])
    doc = json.loads((tmp_path / "rc" / "math500-p426s2-off-smoke.receipt.json").read_text())
    assert rc == 2 and doc["verdict"] == "NOT_STARTED" and any("expected" in p for p in doc["problems"])


def test_the_label_leg_cli_refuses_a_bad_label_without_a_receipt(tmp_path, capsys):
    rc = L.main(["--axis", "math500", "--arm", "off", "--smoke", "--stack-root", "x", "--workdir", "y", "--receipt-dir",
                 str(tmp_path / "rc"), "--build", "S2"])
    assert rc == 2 and not (tmp_path / "rc").exists() and "build label" in capsys.readouterr().err


# ------------------------------------------------------------------ M1: qualify's ON registry copy is the committed one
def _qualify_run(tmp_path, arms_, overlay_text):
    spec = _label_spec(tmp_path, arms_, arm="on")
    spec.kind = "qualify"
    spec.model = ENTRY
    out_dir = tmp_path / "m1out"
    out_dir.mkdir()
    (out_dir / "report.json").write_text(json.dumps(dict(
        predictor="on", production=PL.EXPECTED_BUILDS["s2"]["production_ref"],
        entries={ENTRY: dict(status="COMPLETED", arm="mtp_on")})))
    if overlay_text is not None:
        (out_dir / f"overlay-{ENTRY}.yaml").write_text(overlay_text)
    ops = TL.FakeOps()
    state = _state(arms_, "on")
    return L.run_qualify_leg(spec, ops, run_driver=lambda *a: 0, pins_check=lambda m, a: [], battery_intervals=lambda s, e: ([], []),
                             clock=iter(["2026-10-22 01:00:00", "2026-10-22 02:00:00"]).__next__,
                             repo_state=iter([state, state]).__next__, out_dir=out_dir)


def test_m1_asserts_qualifys_overlay_is_the_on_worktrees_registry(tmp_path, arms):
    on_text = (arms[1] / "main_models.yaml").read_text()
    receipt = _qualify_run(tmp_path, arms, on_text)
    assert receipt["verdict"] == "VALID", receipt["problems"]
    assert receipt["overlay"] == dict(file=f"overlay-{ENTRY}.yaml", sha256=L.sha256_text(on_text), registry_on_sha256=L.sha256_text(on_text))


@pytest.mark.parametrize("overlay", [None, "other registry\n"])
def test_m1_refuses_an_overlay_that_is_not_the_committed_on_registry(tmp_path, arms, overlay):
    receipt = _qualify_run(tmp_path, arms, overlay)
    assert receipt["verdict"] == "INVALID" and any("overlay-" in p for p in receipt["problems"])
