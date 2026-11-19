"""S26 frozen tests, the tg2 arm's Gradle home and the identity policy (spec §3; acceptance 1: `build_env` tg2 refuses without a
prefilled folder (and with a deleted cache file) and sets `GRADLE_USER_HOME` with one; the real tg2 `--print-identity` carries the
Gradle policy; tg1 identity, argv and env unchanged (the B4b-1 tg1 golden passes unmodified)).

Classes: [FIX] reproduces a failure the spec fixes (a tg2 item started with the operator's real `~/.gradle`); [INV] preserves an
invariant (tg1 / M64 env, tg1 policy hash); [NEW] new behaviour. The prefilled folder comes from the prefill itself over the fake
`./gradlew` (`s26_support.GradleWorld`) - these tests therefore also need `bench.tg2_gradle_home.prefill`. On the baseline the
[INV] tests pass (nothing changed yet) and the rest fail.

NOT run here (Phase B): `test_m76_b4b1_impl_golden_tg1.py` must pass UNMODIFIED on the candidate."""
from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import arm_adapter as aa
from bench import arm_opencode as ao
from bench import run_config as rc
from bench.tests.s26_frozen import s26_support as X


@pytest.fixture
def gw(tmp_path, monkeypatch):
    return X.GradleWorld(tmp_path, monkeypatch)


@pytest.fixture
def prefilled(gw):
    assert gw.prefill() == 0
    return gw


def tg2_arm():
    return ao.OpencodeArm(importlib.import_module("run_tg2_probe"), mode="tg1", scaffold="tg2")


def tg1_arm():
    return ao.OpencodeArm(importlib.import_module("run_tg1_probe"), mode="tg1")


def env_of(arm, tmp_path):
    run_dir = Path(tmp_path) / "runs" / "run-1"
    run_dir.mkdir(parents=True, exist_ok=True)
    scratch = run_dir.parent / "scratch" / "item"
    scratch.mkdir(parents=True, exist_ok=True)
    return arm.build_env(run_dir, scratch, {"providers": {}}, receipts=None, frozen_date=None)


# ---------------------------------------------------------------------------------------------------- build_env
def test_fix_a_tg2_item_without_a_prefilled_folder_never_starts(tmp_path, gw):
    """[FIX] §3: `check_problems()` non-empty -> `ArmContractError("tg2 Gradle home: <problem>")`."""
    with pytest.raises(aa.ArmContractError, match="tg2 Gradle home: "):
        env_of(tg2_arm(), tmp_path)


def test_new_a_prefilled_folder_is_handed_to_the_agent_as_gradle_user_home(tmp_path, prefilled):
    """[NEW] §3: `env["GRADLE_USER_HOME"] = <folder>`; every other field is the tg1 hermetic env's (HOME stays the run's)."""
    tg2 = env_of(tg2_arm(), tmp_path)
    assert tg2["GRADLE_USER_HOME"] == str(prefilled.folder)
    tg1 = env_of(tg1_arm(), tmp_path)
    assert {k: v for k, v in tg2.items() if k != "GRADLE_USER_HOME"} == tg1


@pytest.mark.parametrize("damage", [
    pytest.param(lambda gw: (gw.folder / X.dep_rel(X.universe_java_items()[0])).unlink(), id="cache-file-deleted"),
    pytest.param(lambda gw: (gw.folder / X.GRADLE_JAR).unlink(), id="distribution-deleted"),
    pytest.param(lambda gw: (gw.folder / "PREFILL.json").unlink(), id="prefill-record-deleted"),
    pytest.param(lambda gw: (gw.folder / "gradle.properties").write_text("org.gradle.daemon=true\n"), id="daemon-switched-on"),
])
def test_fix_a_damaged_folder_stops_the_item_before_it_starts(tmp_path, prefilled, damage):
    """[FIX] the check runs at every `build_env` (every item), not once: damage after the prefill is caught before the item."""
    env_of(tg2_arm(), tmp_path)                                    # healthy: fine
    damage(prefilled)
    with pytest.raises(aa.ArmContractError, match="tg2 Gradle home: "):
        env_of(tg2_arm(), tmp_path)


def test_inv_tg1_and_m64_env_never_carry_a_gradle_home(tmp_path, prefilled, monkeypatch):
    """[INV] tg1 / M64 unchanged: no `GRADLE_USER_HOME`, even with a prefilled folder and one in the process environment."""
    monkeypatch.setenv("GRADLE_USER_HOME", "/operator/.gradle")
    tg1 = env_of(tg1_arm(), tmp_path)
    assert "GRADLE_USER_HOME" not in tg1
    m64 = ao.OpencodeArm(importlib.import_module("run_tg1_probe"), mode="m64", search=ao.OfflineTestSearchService())
    assert "GRADLE_USER_HOME" not in env_of(m64, tmp_path)


def test_inv_tg1_env_is_exactly_the_core_hermetic_env(tmp_path):
    """[INV] tg1 env == `opencode_v2_core._opencode_env` (byte-for-byte the baseline's recipe)."""
    from bench import opencode_v2_core as core
    run_dir = Path(tmp_path) / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    scratch = run_dir.parent / "scratch" / "item"
    scratch.mkdir(parents=True)
    got = tg1_arm().build_env(run_dir, scratch, {"a": 1}, receipts=None, frozen_date=None)
    assert got == core._opencode_env(run_dir, scratch, {"a": 1}, frozen_date=None, receipts=None)


# ---------------------------------------------------------------------------------------------------- GenerationPolicy
def policy_kwargs(**extra):
    return dict(scaffold="opencode-v2-web-tg2", corpus_id="tg2", corpus_identity={"c": 1}, toolbounds_sha256="1" * 64,
                noretry_sha256="2" * 64, datefreeze_sha256="3" * 64, carrier_sha256="4" * 64, universe_sha256="5" * 64,
                env={"PATH": "/usr/bin"}, toolchain={"t": 1}, gate={"g": 1}, hygiene={"h": 1}, grader_version="v",
                grader_timeout_s={"rust": 1}, grade_join_timeout_s=62, **extra)


GRADLE = {"path": "$STACK_WORKDIR/tg2-gradle-home", "properties_sha256": "a" * 64, "prefill_sha256": "b" * 64}


def build(**extra):
    return rc.PolicyTemplate(config_id="tg2", langs=("rust", "java")).build(**policy_kwargs(**extra))


def test_inv_a_policy_without_a_gradle_home_is_byte_for_byte_the_old_one():
    """[INV] §3 (Sol P2): `gradle_user_home` is OMITTED from `as_dict()` and the hash when None - tg1's hash is unchanged."""
    plain, explicit = build(), build(gradle_user_home=None)
    assert "gradle_user_home" not in plain.as_dict() and plain.as_dict() == explicit.as_dict()
    assert plain.sha256() == explicit.sha256() == hashlib.sha256(json.dumps(plain.as_dict(), sort_keys=True).encode()).hexdigest()
    assert plain.canonical_json() == explicit.canonical_json() and "gradle" not in plain.canonical_json()


def test_new_a_policy_with_a_gradle_home_carries_it_and_changes_the_hash():
    plain, with_home = build(), build(gradle_user_home=GRADLE)
    assert with_home.as_dict()["gradle_user_home"] == GRADLE and with_home.sha256() != plain.sha256()
    assert {k: v for k, v in with_home.as_dict().items() if k != "gradle_user_home"} == plain.as_dict()
    for field in GRADLE:
        other = build(gradle_user_home=dict(GRADLE, **{field: "c" * 64}))
        assert other.sha256() not in (with_home.sha256(), plain.sha256())


def test_new_the_gradle_home_is_isolated_from_the_callers_dict():
    mine = dict(GRADLE)
    policy = build(gradle_user_home=mine)
    mine["prefill_sha256"] = "z"
    assert policy.as_dict()["gradle_user_home"] == GRADLE


# ---------------------------------------------------------------------------------------------------- the real identities
def identity_inputs(probe, scaffold):
    """`arm_runner._identity_inputs` exactly as `print_identity` calls it, for the real probe entry."""
    from bench import arm_runner, tg1_runner, tg2_runner
    p = importlib.import_module(probe)
    if scaffold == "tg2":
        adapter, template, corpus = ao.OpencodeArm(p, mode="tg1", scaffold="tg2"), tg2_runner.TG2_POLICY, tg2_runner._corpus(p, SimpleNamespace(universe=None))
    else:
        adapter, template, corpus = ao.OpencodeArm(p, mode="tg1"), tg1_runner.TG1_POLICY, tg1_runner._corpus(p, SimpleNamespace(universe=None))
    selection = adapter.selection(None)
    _, universe_sha = corpus.load_universe()
    binary, _ = adapter.identity_binary()
    return arm_runner._identity_inputs(adapter, template, corpus, selection, universe_sha, adapter.pinned_version, binary, None)


def print_identity(probe, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["x", "--print-identity"])
    p = importlib.import_module(probe)
    assert X.rc_of(p.main) == 0
    return json.loads(capsys.readouterr().out)


def test_new_the_tg2_identity_policy_names_the_gradle_home_and_its_prefill(prefilled):
    """[NEW] §3 (Sol P2): `{path: "$STACK_WORKDIR/tg2-gradle-home", properties_sha256, prefill_sha256: sha256 of PREFILL.json}`
    is in the tg2 policy, and `scaffold_policy_sha256` is the hash of that policy."""
    ident, policy = identity_inputs("run_tg2_probe", "tg2")
    want = {"path": "$STACK_WORKDIR/tg2-gradle-home", "properties_sha256": X.sha256_bytes(b"org.gradle.daemon=false\n"),
            "prefill_sha256": X.sha256_file(prefilled.folder / "PREFILL.json")}
    assert ident["policy"]["gradle_user_home"] == want
    assert policy.as_dict()["gradle_user_home"] == want
    assert ident["scaffold_policy_sha256"] == policy.sha256() == hashlib.sha256(json.dumps(ident["policy"], sort_keys=True).encode()).hexdigest()
    assert "/" not in want["path"].split("$STACK_WORKDIR/", 1)[1]            # a workdir-relative name: no absolute home path in the record
    assert str(prefilled.wd) not in json.dumps(ident["policy"]["gradle_user_home"])


def test_new_the_real_tg2_print_identity_carries_the_gradle_policy(prefilled, monkeypatch, capsys):
    """[NEW] acceptance 1: the real tg2 `--print-identity` moves with the prefill (same prefill -> same hash; a new PREFILL.json ->
    another), so two tg2 legs on differently prefilled homes never pool."""
    first = print_identity("run_tg2_probe", monkeypatch, capsys)["scaffold_policy_sha256"]
    again = print_identity("run_tg2_probe", monkeypatch, capsys)["scaffold_policy_sha256"]
    assert first == again
    prefilled.write_prefill_doc(dict(prefilled.prefill_doc(), created="1999-01-01T00:00:00Z"))
    assert prefilled.check() == 0                                       # still a valid folder ...
    capsys.readouterr()                                                 # (`check` prints a line: drain it before the next JSON read)
    assert print_identity("run_tg2_probe", monkeypatch, capsys)["scaffold_policy_sha256"] != first      # ... but another identity


def test_inv_the_tg1_policy_is_untouched_by_the_gradle_home(prefilled, monkeypatch, capsys):
    """[INV] tg1 identity unchanged: no Gradle block in the tg1 policy; its `scaffold_policy_sha256` is its policy's hash and does
    not depend on whether a tg2 Gradle home exists."""
    ident, policy = identity_inputs("run_tg1_probe", "tg1")
    assert "gradle_user_home" not in ident["policy"] and "gradle_user_home" not in policy.as_dict()
    assert ident["scaffold_policy_sha256"] == hashlib.sha256(json.dumps(ident["policy"], sort_keys=True).encode()).hexdigest()
    with_home = print_identity("run_tg1_probe", monkeypatch, capsys)["scaffold_policy_sha256"]
    import shutil
    shutil.rmtree(prefilled.folder)
    assert print_identity("run_tg1_probe", monkeypatch, capsys)["scaffold_policy_sha256"] == with_home == ident["scaffold_policy_sha256"]
