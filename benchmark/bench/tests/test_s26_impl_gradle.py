"""S26 §3 (implementer tests): the bench-owned tg2 Gradle home — `prefill` / `check` with a fake corpus and a fake gradle runner
(both passes, the agent env, refusal on a non-empty folder, `--force`, an offline failure), `check_problems` on the recorded facts,
`OpencodeArm.build_env` (tg2 refuses without a prefilled folder or with a deleted cache file; sets GRADLE_USER_HOME with one; tg1
unchanged), the identity policy (`GenerationPolicy.gradle_user_home` omitted when None; tg2 identity and the real tg2
`--print-identity` carry it)."""
from __future__ import annotations

import hashlib
import importlib
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import arm_adapter as aa
from bench import arm_opencode as ao
from bench import run_config as rc
from bench import schedules
from bench import tg2_gradle_home as gh

REPO = Path(__file__).resolve().parents[3]
UNIVERSE = ("u" * 64, ["java/alpha", "java/beta"])
TOOLCHAIN = dict(lock_sha256="1" * 64, interpreter="3.12.1", grader_image_id="sha256:" + "2" * 64)


@pytest.fixture
def wd(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    return tmp_path


class FakeCorpus:
    def __init__(self):
        self.prepared = []

    def prepare(self, item, dest):
        dest = Path(dest)
        (dest / "gradle/wrapper").mkdir(parents=True)
        (dest / "gradle/wrapper/gradle-wrapper.properties").write_text(
            "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.7-bin.zip\n")
        (dest / "gradlew").write_text("#!/bin/sh\n")
        self.prepared.append(item)
        return SimpleNamespace(work=dest)


class FakeGradle:
    """The gradle runner: the online pass "downloads" into GRADLE_USER_HOME, the offline pass needs it."""

    def __init__(self, offline_rc=None):
        self.calls, self.offline_rc = [], dict(offline_rc or {})

    def __call__(self, argv, *, cwd, env):
        self.calls.append((tuple(argv), Path(cwd).name, dict(env)))
        home = Path(env["GRADLE_USER_HOME"])
        if tuple(argv) == gh.TEST_ARGV:
            dist = home / "wrapper/dists/gradle-8.7-bin/abc/gradle-8.7-bin.zip"
            dist.parent.mkdir(parents=True, exist_ok=True)
            dist.write_bytes(b"z" * 100)
            jar = home / "caches/modules-2/files-2.1/org.junit/junit/5.10/hash" / f"junit-{Path(cwd).name}.jar"
            jar.parent.mkdir(parents=True, exist_ok=True)
            jar.write_bytes(b"j" * 10)
            (home / "caches/other/lock").parent.mkdir(parents=True, exist_ok=True)
            (home / "caches/other/lock").write_text("not in the manifest")
            return 0
        if tuple(argv) == gh.OFFLINE_ARGV:
            return self.offline_rc.get(Path(cwd).name, 0 if (home / "wrapper/dists").is_dir() else 1)
        return 0


def prefill(wd, **kw):
    corpus, run = kw.pop("corpus", FakeCorpus()), kw.pop("run", FakeGradle())
    refs = []
    code = gh.prefill(workdir=wd, universe=kw.pop("universe", UNIVERSE), corpus=corpus,
                      reference=lambda c, slug, work: refs.append(slug), run=run, log=lambda m: None, **kw)
    return code, corpus, run, refs


def test_the_constants():
    assert gh.GRADLE_HOME_REL == "tg2-gradle-home" and gh.PROPERTIES == "org.gradle.daemon=false\n"
    assert gh.POLICY_PATH == "$STACK_WORKDIR/tg2-gradle-home"
    assert gh.TEST_ARGV == ("./gradlew", "test", "--console=plain") and gh.OFFLINE_ARGV == gh.TEST_ARGV + ("--offline",)


def test_prefill_runs_both_passes_under_the_agent_env_and_records_the_facts(wd):
    from bench.opencode_v2_core import SCAFFOLD_ENV_POLICY_V2
    code, corpus, run, refs = prefill(wd)
    assert code == 0 and corpus.prepared == UNIVERSE[1] and refs == ["alpha", "beta"]
    argvs = [(a, cwd) for a, cwd, _ in run.calls]
    assert argvs == [(gh.TEST_ARGV, "alpha"), (gh.TEST_ARGV, "beta"), (gh.STOP_ARGV, "alpha"), (gh.OFFLINE_ARGV, "alpha"),
                     (gh.OFFLINE_ARGV, "beta")]
    root = wd / "tg2-gradle-home"
    for _, _, env in run.calls:
        assert set(env) == set(SCAFFOLD_ENV_POLICY_V2) | {"HOME", "TMPDIR", "GRADLE_USER_HOME"}
        assert all(env[k] == v for k, v in SCAFFOLD_ENV_POLICY_V2.items())
        assert env["GRADLE_USER_HOME"] == str(root)
        assert Path(env["HOME"]).is_relative_to(wd / "scratch") and Path(env["TMPDIR"]).is_relative_to(wd / "scratch")
    assert not any((wd / "scratch").iterdir())                               # the work trees are removed after
    assert (root / "gradle.properties").read_text() == gh.PROPERTIES
    doc = json.loads((root / "PREFILL.json").read_text())
    assert doc["universe_sha256"] == UNIVERSE[0] and doc["gradle_version"] == "8.7"
    assert doc["items"] == [dict(id="java/alpha", online_rc=0, offline_rc=0), dict(id="java/beta", online_rc=0, offline_rc=0)]
    rels = [rel for rel, _ in doc["cache_manifest"]]
    assert rels == sorted(rels) and "wrapper/dists/gradle-8.7-bin/abc/gradle-8.7-bin.zip" in rels
    assert all(r.startswith(gh.MANIFEST_ROOTS) for r in rels) and len(rels) == 3
    assert gh.check_problems(workdir=wd, universe=UNIVERSE) == []
    assert gh.main(["check"], workdir=wd, universe=UNIVERSE) == 0


def test_prefill_refuses_a_non_empty_folder_and_force_removes_it_first(wd):
    root = wd / "tg2-gradle-home"
    root.mkdir()
    (root / "stale").write_text("x")
    code, corpus, run, _ = prefill(wd)
    assert code == 2 and run.calls == [] and (root / "stale").exists()
    code, _, _, _ = prefill(wd, force=True)
    assert code == 0 and not (root / "stale").exists()


def test_an_offline_failure_is_rc_nonzero_and_check_names_it(wd):
    code, _, _, _ = prefill(wd, run=FakeGradle(offline_rc={"beta": 1}))
    assert code == 1
    assert gh.check_problems(workdir=wd, universe=UNIVERSE) == ["the offline pass did not succeed for java/beta"]
    assert gh.main(["check"], workdir=wd, universe=UNIVERSE) == 1


def test_an_item_that_cannot_be_prepared_fails_the_prefill(wd):
    class Broken(FakeCorpus):
        def prepare(self, item, dest):
            if item == "java/beta":
                raise RuntimeError("prepare boom")
            return super().prepare(item, dest)
    code, _, _, _ = prefill(wd, corpus=Broken())
    doc = json.loads((wd / "tg2-gradle-home/PREFILL.json").read_text())
    assert code == 1 and doc["items"][1]["offline_rc"] is None and "prepare boom" in doc["items"][1]["error"]


@pytest.mark.parametrize("damage,want", [
    ("missing", "does not exist"), ("properties", "gradle.properties is not exactly"), ("no-prefill", "never prefilled"),
    ("not-a-record", "is not a prefill record"), ("universe", "another tg2 universe"), ("items", "valid Java items"),
    ("deleted", "is missing"), ("resized", "has size")])
def test_check_problems_verifies_the_recorded_facts(wd, damage, want):
    import shutil
    assert prefill(wd)[0] == 0
    root = wd / "tg2-gradle-home"
    universe = UNIVERSE
    doc = json.loads((root / "PREFILL.json").read_text())
    jar = next(rel for rel, _ in doc["cache_manifest"] if rel.endswith(".jar"))
    if damage == "missing":
        shutil.rmtree(root)
    elif damage == "properties":
        (root / "gradle.properties").write_text("org.gradle.daemon=true\n")
    elif damage == "no-prefill":
        (root / "PREFILL.json").unlink()
    elif damage == "not-a-record":
        (root / "PREFILL.json").write_text(json.dumps([doc]))
    elif damage == "universe":
        universe = ("v" * 64, UNIVERSE[1])
    elif damage == "items":
        universe = (UNIVERSE[0], UNIVERSE[1] + ["java/gamma"])
    elif damage == "deleted":
        (root / jar).unlink()
    elif damage == "resized":
        (root / jar).write_bytes(b"j")
    problems = gh.check_problems(workdir=wd, universe=universe)
    assert problems and want in problems[0], problems


def test_prefill_json_carries_no_self_seal_and_check_needs_none(wd):
    """Erratum 6 (Sol P21): no self-seal; the recorded facts are checked, `prefill_sha256` in the identity binds the file."""
    assert prefill(wd)[0] == 0
    path = wd / "tg2-gradle-home" / "PREFILL.json"
    doc = json.loads(path.read_text())
    assert "sha256" not in doc
    doc["created"] = "2026-01-01T00:00:00Z"                                  # an edited non-fact field: still verifies
    path.write_text(json.dumps(doc))
    assert gh.check_problems(workdir=wd, universe=UNIVERSE) == []
    doc["items"][0]["offline_rc"] = 1                                       # an edited fact: refused
    path.write_text(json.dumps(doc))
    assert gh.check_problems(workdir=wd, universe=UNIVERSE) == ["the offline pass did not succeed for java/alpha"]


def test_the_committed_universe_is_the_pinned_one_with_java_items():
    sha, items = gh.committed_universe()
    assert sha == schedules.TG2_UNIVERSE_SHA256 and items and all(i.startswith("java/") for i in items)
    assert items == sorted(items)


# ----------------------------------------------------------------------------------------------- build_env
def _env_host():
    return SimpleNamespace(_opencode_env=lambda run_dir, scratch, overlay, *, frozen_date=None, receipts=None:
                           {"HOME": str(Path(run_dir) / "home"), "PATH": "/opt/homebrew/bin:/usr/bin:/bin"})


def _build_env(arm, tmp_path):
    return arm.build_env(tmp_path / "run", tmp_path / "scratch", {}, receipts=tmp_path / "r.jsonl", frozen_date="Fri Nov 13 2026")


def _prefill_committed(wd):
    code = gh.prefill(workdir=wd, corpus=FakeCorpus(), reference=lambda c, s, w: None, run=FakeGradle(), log=lambda m: None)
    assert code == 0


def test_build_env_tg2_refuses_without_a_prefilled_folder(wd):
    arm = ao.OpencodeArm(_env_host(), mode="tg1", scaffold="tg2")
    with pytest.raises(aa.ArmContractError, match="^tg2 Gradle home: .*does not exist"):
        _build_env(arm, wd)


def test_build_env_tg2_refuses_with_a_deleted_cache_file_and_sets_gradle_user_home_with_one(wd):
    _prefill_committed(wd)
    arm = ao.OpencodeArm(_env_host(), mode="tg1", scaffold="tg2")
    env = _build_env(arm, wd)
    assert env["GRADLE_USER_HOME"] == str(wd / "tg2-gradle-home")
    doc = json.loads((wd / "tg2-gradle-home/PREFILL.json").read_text())
    (wd / "tg2-gradle-home" / doc["cache_manifest"][0][0]).unlink()
    with pytest.raises(aa.ArmContractError, match="^tg2 Gradle home: the cache file .* is missing"):
        _build_env(arm, wd)


def test_the_gradle_home_is_bound_to_tg2_only_and_never_enters_the_shared_closures():
    from bench import identity_closure as ic
    assert ao.OpencodeArm(None, mode="tg1", scaffold="tg2").gradle_home is gh
    assert ao.OpencodeArm(None, mode="tg1").gradle_home is None and ao.OpencodeArm(None, mode="m64").gradle_home is None
    with pytest.raises(aa.ArmContractError):
        ao.OpencodeArm(None, mode="tg1", gradle_home=gh)
    for entry in ("benchmark/run_tg1_probe.py", "benchmark/run_oc_probe.py"):
        got = {p.resolve().relative_to(REPO.resolve()).as_posix() for p in ic.python_closure(REPO / entry, REPO)}
        assert not [f for f in got if "/tg2_" in f or f.endswith(("/host_env.py", "/schedules.py"))], entry


def test_the_gradle_home_source_enters_tg2s_probe_identity_only(wd, monkeypatch):
    """Erratum 5 (Sol P18): `bench/tg2_gradle_home.py`'s bytes enter tg2's `probe_code_sha256` (as identity data); tg1's data
    and closure are unchanged; `generation_data` (B4b-1) is unchanged."""
    from bench import identity_closure as ic
    assert ao.TG2_GRADLE_HOME_SOURCE == "benchmark/bench/tg2_gradle_home.py" and (REPO / ao.TG2_GRADLE_HOME_SOURCE).is_file()
    tg2, tg1 = ao.OpencodeArm(None, mode="tg1", scaffold="tg2"), ao.OpencodeArm(None, mode="tg1")
    assert tg2.generation_data == ao.TG2_GENERATION_DATA and tg1.generation_data == ao.GENERATION_DATA
    assert tg2.identity_data == ao.TG2_GENERATION_DATA + (ao.TG2_GRADLE_HOME_SOURCE,)
    assert tg1.identity_data == ao.GENERATION_DATA and ao.OpencodeArm(None, mode="m64").identity_data == tuple(
        ao.OpencodeArm(None, mode="m64").generation_data)
    seen = []
    monkeypatch.setattr(ic, "closure_sha256", lambda entry, repo, data=(): seen.append((entry, tuple(data))) or "c" * 64)
    from bench import toolchain
    monkeypatch.setattr(toolchain, "current", lambda: dict(TOOLCHAIN))
    kw = dict(selection={"fields": {"opencode_bench_config_sha256": "b" * 64}}, universe_sha="u" * 64, version="2.0.20",
              binary=Path("/nonexistent/opencode"))
    ao.OpencodeArm(_identity_host("benchmark/run_tg1_probe.py"), mode="tg1").identity(**kw)
    ao.OpencodeArm(_identity_host("benchmark/run_tg2_probe.py"), mode="tg1", scaffold="tg2").identity(**kw)
    assert seen == [("benchmark/run_tg1_probe.py", ao.GENERATION_DATA),
                    ("benchmark/run_tg2_probe.py", ao.TG2_GENERATION_DATA + (ao.TG2_GRADLE_HOME_SOURCE,))]


def test_the_gradle_home_source_is_in_tg2s_campaign_core_only(tmp_path):
    """Erratum 12 (Sol P3, round 2): `bench/tg2_gradle_home.py` is in tg2's campaign-core `probe_data`; a change to it changes
    tg2's campaign-core closure and leaves tg1's unchanged."""
    import shutil
    from bench import campaign_core
    from chains.c147 import run_tg1_chain as R1
    from chains.c147 import run_tg2_chain as R2
    assert ao.TG2_GRADLE_HOME_SOURCE in R2.CORE_SPECS["probe_data"]
    assert ao.TG2_GRADLE_HOME_SOURCE not in R1.CORE_SPECS["probe_data"]
    specs = {"tg1": dict(R1.CORE_SPECS), "tg2": dict(R2.CORE_SPECS)}
    files = set()
    for spec in specs.values():
        files |= set(campaign_core.members(REPO, spec["probe_entry"], spec["probe_data"]))
        files |= set(campaign_core.members(REPO, spec["chain_entry"], spec["chain_data"]))
    files.add(ao.TG2_GRADLE_HOME_SOURCE)
    for rel in files:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, tmp_path / rel)
    before = {k: campaign_core.closure_shas(tmp_path, **s) for k, s in specs.items()}
    with open(tmp_path / ao.TG2_GRADLE_HOME_SOURCE, "a") as fh:
        fh.write("\n# changed\n")
    after = {k: campaign_core.closure_shas(tmp_path, **s) for k, s in specs.items()}
    assert after["tg2"]["probe_closure_sha256"] != before["tg2"]["probe_closure_sha256"]
    assert after["tg1"] == before["tg1"]


def test_build_env_tg1_is_unchanged(wd, monkeypatch):
    monkeypatch.setattr(gh, "check_problems", lambda **kw: pytest.fail("tg1 never checks the tg2 Gradle home"))
    host = _env_host()
    env = _build_env(ao.OpencodeArm(host, mode="tg1"), wd)
    assert env == host._opencode_env(wd / "run", wd / "scratch", {}) and "GRADLE_USER_HOME" not in env


# ----------------------------------------------------------------------------------------------- identity
def test_generation_policy_omits_gradle_user_home_when_none():
    kw = dict(config_id="tg2", scaffold="s", corpus_id="tg2", corpus_identity={}, langs=("java",), toolbounds_sha256="t",
              noretry_sha256="n", datefreeze_sha256="d", carrier_sha256="c", universe_sha256="u", env={}, toolchain={},
              gate={}, hygiene={}, grader_version="g", grader_timeout_s={"java": 1})
    plain = rc.tg1_generation_policy(**kw)
    assert "gradle_user_home" not in plain.as_dict()
    assert plain.sha256() == hashlib.sha256(json.dumps(plain.as_dict(), sort_keys=True).encode()).hexdigest()
    block = dict(path=gh.POLICY_PATH, properties_sha256="p" * 64, prefill_sha256="q" * 64)
    with_home = rc.tg1_generation_policy(**kw, gradle_user_home=block)
    assert with_home.as_dict()["gradle_user_home"] == block and with_home.sha256() != plain.sha256()
    assert rc.PolicyTemplate(config_id="tg2", langs=("java",)).build(
        **{k: v for k, v in kw.items() if k not in ("config_id", "langs")}, gradle_user_home=block).as_dict() == with_home.as_dict()


def test_identity_inputs_pass_the_block_only_when_the_adapter_names_it():
    from bench import arm_runner
    block = dict(path=gh.POLICY_PATH, properties_sha256=None, prefill_sha256=None)
    seen = []

    class Template:
        def build(self, **kw):
            seen.append(kw)
            return SimpleNamespace(as_dict=lambda: {"k": 1}, sha256=lambda: "s" * 64)

    def adapter(extra):
        pol = dict(toolbounds_sha256="t", noretry_sha256="n", datefreeze_sha256="d", carrier_sha256="c", universe_sha256="u",
                   env={}, toolchain={}, gate={}, hygiene={}, plugin_proof="x", **extra)
        return SimpleNamespace(identity=lambda **kw: dict(scaffold="s", policy=pol))
    corpus = SimpleNamespace(corpus_id="tg2", identity=lambda: dict(grader_timeout_s={"java": 1}, grader_version="g"))
    arm_runner._identity_inputs(adapter({}), Template(), corpus, {}, "u", "2.0.20", Path("/x"), None)
    arm_runner._identity_inputs(adapter(dict(gradle_user_home=block)), Template(), corpus, {}, "u", "2.0.20", Path("/x"), None)
    assert "gradle_user_home" not in seen[0] and seen[1]["gradle_user_home"] == block


def _identity_host(entry):
    return SimpleNamespace(_sha_of=lambda path: "sha-" + Path(path).name,
                           NORETRY_PLUGIN=REPO / "benchmark/opencode_plugins/noretry.js",
                           SCAFFOLD_ENV_POLICY_V2={"PATH": "/usr/bin", "TERM": "dumb"}, __file__=str(REPO / entry))


def test_the_tg2_identity_carries_the_gradle_policy_and_tg1s_does_not(wd, monkeypatch):
    from bench import identity_closure, toolchain
    monkeypatch.setattr(identity_closure, "closure_sha256", lambda *a, **k: "c" * 64)
    monkeypatch.setattr(toolchain, "current", lambda: dict(TOOLCHAIN))
    sel = {"fields": {"opencode_bench_config_sha256": "b" * 64}}
    kw = dict(selection=sel, universe_sha="u" * 64, version="2.0.20", binary=Path("/nonexistent/opencode"))
    tg1 = ao.OpencodeArm(_identity_host("benchmark/run_tg1_probe.py"), mode="tg1").identity(**kw)
    assert "gradle_user_home" not in tg1["policy"]
    tg2_arm = ao.OpencodeArm(_identity_host("benchmark/run_tg2_probe.py"), mode="tg1", scaffold="tg2")
    before = tg2_arm.identity(**kw)["policy"]["gradle_user_home"]
    assert before == dict(path="$STACK_WORKDIR/tg2-gradle-home", properties_sha256=None, prefill_sha256=None)
    _prefill_committed(wd)
    root = wd / "tg2-gradle-home"
    after = tg2_arm.identity(**kw)["policy"]["gradle_user_home"]
    assert after == dict(path="$STACK_WORKDIR/tg2-gradle-home",
                         properties_sha256=hashlib.sha256(gh.PROPERTIES.encode()).hexdigest(),
                         prefill_sha256=hashlib.sha256((root / "PREFILL.json").read_bytes()).hexdigest())


def test_the_real_tg2_print_identity_carries_the_gradle_policy(wd, monkeypatch):
    from bench import toolchain, tg2_runner
    monkeypatch.setattr(toolchain, "current", lambda: dict(TOOLCHAIN))
    monkeypatch.delenv("OPENCODE_PROBE_BIN", raising=False)
    probe = importlib.import_module("run_tg2_probe")
    args = SimpleNamespace(print_identity=True, universe=None, agent_system_file=None, tg1_inject=None,
                           sampling_profile="deployed")

    def printed():
        buf = io.StringIO()
        with redirect_stdout(buf):
            assert tg2_runner.print_identity(probe, args) == 0
        return json.loads(buf.getvalue().splitlines()[-1])
    empty = printed()
    assert empty["gradle_user_home"] == dict(path=gh.POLICY_PATH, properties_sha256=None, prefill_sha256=None)
    _prefill_committed(wd)
    full = printed()
    assert full["gradle_user_home"]["prefill_sha256"] == hashlib.sha256(
        (wd / "tg2-gradle-home/PREFILL.json").read_bytes()).hexdigest()
    assert full["scaffold_policy_sha256"] != empty["scaffold_policy_sha256"]
    assert os.environ["STACK_WORKDIR"] == str(wd)
