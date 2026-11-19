"""S26 frozen tests, `bench/tg2_gradle_home.py` (spec §3; acceptance 1: `tg2_gradle_home` prefill / check with a fake runner - both
passes, refusal on a non-empty folder, offline failure -> rc != 0).

Classes: [FIX] reproduces a failure the spec fixes (tg2 Java items shared the operator's real `~/.gradle`, a daemon, and downloaded on
the first item); [INV] preserves an invariant; [NEW] new behaviour. The "fake runner" is a real executable `./gradlew` script in each
fake work tree (`s26_support.GradleWorld`: it logs its argv and environment, fills / reads `$GRADLE_USER_HOME`, exits per script),
behind the real `Tg2Corpus` / `tg2_materialize` seams patched at their class / module attributes. The module is new: every test here
fails on the baseline (ImportError). ASSUMPTION: the CLI is `bench.tg2_gradle_home.main(argv) -> rc` (`prefill [--force]` / `check`)."""
from __future__ import annotations

import json

import pytest

from bench.tests.s26_frozen import s26_support as X

JAVA = X.universe_java_items()


def G():
    from bench import tg2_gradle_home
    return tg2_gradle_home


def policy_keys():
    from bench import opencode_v2_core as core
    return set(core.SCAFFOLD_ENV_POLICY_V2)


@pytest.fixture
def gw(tmp_path, monkeypatch):
    return X.GradleWorld(tmp_path, monkeypatch)


@pytest.fixture
def prefilled(gw):
    assert gw.prefill() == 0
    return gw


def edit_prefill(gw, edit):
    doc = gw.prefill_doc()
    edit(doc)
    gw.write_prefill_doc(doc)


# ---------------------------------------------------------------------------------------------------- constants / universe
def test_new_the_constants_are_the_spec_ones():
    assert G().GRADLE_HOME_REL == "tg2-gradle-home" and G().PROPERTIES == "org.gradle.daemon=false\n"


def test_inv_the_java_item_set_is_not_empty_and_is_only_valid_java():
    assert JAVA and all(i.startswith("java/") for i in JAVA)


# ---------------------------------------------------------------------------------------------------- prefill
def test_new_prefill_builds_the_folder_with_the_properties_and_the_record(gw):
    """[NEW] §3: creates the folder and `gradle.properties`; every VALID Java item prepared + reference applied + two passes;
    `PREFILL.json` with items / gradle_version / java / universe_sha256 / cache_manifest / created; rc 0."""
    from bench import schedules
    assert gw.prefill() == 0
    assert (gw.folder / "gradle.properties").read_bytes() == b"org.gradle.daemon=false\n"
    doc = gw.prefill_doc()
    assert {"items", "gradle_version", "java", "universe_sha256", "cache_manifest", "created"} <= set(doc)
    assert doc["universe_sha256"] == schedules.TG2_UNIVERSE_SHA256
    assert sorted(i["id"] for i in doc["items"]) == JAVA
    for item in doc["items"]:
        rcs = [v for k, v in item.items() if k != "id"]
        assert len(rcs) == 2 and rcs == [0, 0]                       # the online pass and the offline pass
    assert doc["cache_manifest"] == X.expected_manifest(JAVA)       # sorted [relative path, size]: only wrapper/dists + files-2.1
    assert gw.check() == 0 and G().check_problems() == []


def test_new_prefill_covers_exactly_the_valid_java_items_with_reference_applied(gw):
    """[NEW] §3: "for every VALID Java item of the committed tg2 universe (exactly that set)": prepared, reference applied."""
    assert gw.prefill() == 0
    assert sorted(i for i, _ in gw.prepared) == JAVA
    assert sorted(tree for _, tree in gw.references) == sorted(dest for _, dest in gw.prepared)
    assert all(plan[1] == "java" for plan, _ in gw.references)


def test_new_each_item_runs_online_then_stop_then_an_offline_pass(gw):
    """[NEW] §3: `./gradlew test --console=plain`, `./gradlew --stop`, then the second pass per item with `--offline`."""
    assert gw.prefill() == 0
    calls = gw.calls()
    online = [(n, c) for n, c in enumerate(calls) if "--stop" not in c["args"] and "--offline" not in c["args"]]
    offline = [(n, c) for n, c in enumerate(calls) if "--offline" in c["args"]]
    stops = [n for n, c in enumerate(calls) if "--stop" in c["args"]]
    assert sorted(c["item"] for _, c in online) == JAVA and sorted(c["item"] for _, c in offline) == JAVA
    assert all("test" in c["args"] and "--console=plain" in c["args"] for _, c in online + offline)
    first_online = {c["item"]: n for n, c in online}
    assert all(first_online[c["item"]] < n for n, c in offline)       # an item's offline pass follows its online pass
    assert stops and min(stops) > min(first_online.values()) and min(stops) < min(n for n, _ in offline)


def test_fix_prefill_runs_gradle_in_the_agents_env_with_only_the_gradle_home_added(gw):
    """[FIX] §3 (GLM F12): the spawn env = `SCAFFOLD_ENV_POLICY_V2` fields + `HOME` (a scratch home) + `TMPDIR` (a scratch dir) +
    `GRADLE_USER_HOME` = the folder, nothing else: the operator's environment never reaches Gradle (the JVM ignores `$HOME`,
    so the Gradle home is set explicitly)."""
    from bench import opencode_v2_core as core
    assert gw.prefill() == 0
    calls = gw.calls()
    assert calls
    for c in calls:
        assert c["keys"] == policy_keys() | {"HOME", "TMPDIR", "GRADLE_USER_HOME"}, sorted(c["keys"] ^ (policy_keys() | {"HOME", "TMPDIR", "GRADLE_USER_HOME"}))
        assert c["guh"] == str(gw.folder) and c["path"] == core.SCAFFOLD_ENV_POLICY_V2["PATH"]
        assert c["home"].startswith(str(gw.wd)) and c["tmpdir"].startswith(str(gw.wd))        # scratch, never the operator's
        assert c["home"] != c["tmpdir"]


def test_new_prefill_work_trees_live_under_scratch_and_are_removed(gw):
    assert gw.prefill() == 0
    scratch = gw.wd / "scratch"
    assert gw.prepared and all(dest.is_relative_to(scratch) for _, dest in gw.prepared)
    assert not list(scratch.rglob("gradlew")) and not any(dest.exists() for _, dest in gw.prepared)


def test_new_prefill_writes_the_properties_before_the_first_run_and_manifests_only_dist_and_modules(gw):
    """[NEW] daemon off: `gradle.properties` is in place BEFORE the first Gradle run (the fake exits 9 when it is not, which would
    make the prefill fail), and the manifest holds only `wrapper/dists/` and `caches/modules-2/files-2.1/` files (the daemon dir
    and journal noise the fake writes are not part of it)."""
    assert gw.prefill() == 0
    paths = [p for p, _ in gw.prefill_doc()["cache_manifest"]]
    assert paths and all(p.startswith(("wrapper/dists/", "caches/modules-2/files-2.1/")) for p in paths)


# ---------------------------------------------------------------------------------------------------- refusal / force
def test_new_prefill_refuses_a_non_empty_folder_and_touches_nothing(gw):
    gw.folder.mkdir(parents=True)
    (gw.folder / "stray.txt").write_text("keep me")
    assert gw.prefill() != 0
    assert (gw.folder / "stray.txt").read_text() == "keep me" and not gw.calls() and not (gw.folder / "PREFILL.json").exists()


def test_new_prefill_accepts_an_existing_empty_folder(gw):
    gw.folder.mkdir(parents=True)
    assert gw.prefill() == 0 and gw.check() == 0


def test_new_force_removes_the_folder_first_and_only_the_folder(gw):
    gw.folder.mkdir(parents=True)
    (gw.folder / "stray.txt").write_text("old")
    (gw.wd / "sibling.txt").write_text("keep")
    assert gw.prefill("--force") == 0
    assert not (gw.folder / "stray.txt").exists() and (gw.wd / "sibling.txt").read_text() == "keep"
    assert gw.check() == 0


def test_new_a_second_prefill_refuses_without_force_and_rebuilds_with_it(prefilled):
    assert prefilled.prefill() != 0 and prefilled.check() == 0       # the refusal left the good folder intact
    assert prefilled.prefill("--force") == 0 and prefilled.check() == 0


# ---------------------------------------------------------------------------------------------------- failure
def test_fix_an_offline_failure_is_a_nonzero_rc_and_not_a_good_folder(tmp_path, monkeypatch):
    """[FIX] §3: "rc 0 only when every offline pass succeeds" - a folder that does not serve an item without network is no folder."""
    gw = X.GradleWorld(tmp_path, monkeypatch, fail_offline={JAVA[-1]})
    assert gw.prefill() != 0
    assert gw.check() != 0 and G().check_problems()
    assert not list((gw.wd / "scratch").rglob("gradlew"))              # the work trees are removed on failure too


# ---------------------------------------------------------------------------------------------------- check
def test_new_check_names_a_missing_folder(gw):
    problems = G().check_problems()
    assert problems and all(isinstance(p, str) and p for p in problems) and gw.check() != 0


def test_new_check_prints_the_first_problem(gw, capsys):
    first = G().check_problems()[0]
    assert gw.check() != 0
    out = capsys.readouterr()
    assert first in out.out + out.err


@pytest.mark.parametrize("damage", [
    pytest.param(lambda gw: (gw.folder / "gradle.properties").unlink(), id="properties-missing"),
    pytest.param(lambda gw: (gw.folder / "gradle.properties").write_text("org.gradle.daemon=true\n"), id="properties-changed"),
    pytest.param(lambda gw: (gw.folder / "gradle.properties").write_text("org.gradle.daemon=false"), id="properties-no-newline"),
    pytest.param(lambda gw: (gw.folder / "PREFILL.json").unlink(), id="prefill-missing"),
    pytest.param(lambda gw: (gw.folder / "PREFILL.json").write_text("{not json"), id="prefill-corrupt"),
    pytest.param(lambda gw: edit_prefill(gw, lambda d: d.update(universe_sha256="0" * 64)), id="other-universe"),
    pytest.param(lambda gw: edit_prefill(gw, lambda d: d["items"].pop()), id="item-missing"),
    pytest.param(lambda gw: edit_prefill(gw, lambda d: d["items"].append(dict(d["items"][0], id="java/ghost"))), id="item-extra"),
    pytest.param(lambda gw: edit_prefill(gw, lambda d: [d["items"][0].update({k: 1 for k, v in d["items"][0].items()
                                                                              if k != "id" and isinstance(v, int)})]),
                 id="a-recorded-rc-is-not-zero"),
    pytest.param(lambda gw: (gw.folder / X.dep_rel(JAVA[0])).unlink(), id="cache-file-deleted"),
    pytest.param(lambda gw: (gw.folder / X.GRADLE_JAR).unlink(), id="distribution-file-deleted"),
    pytest.param(lambda gw: (gw.folder / X.dep_rel(JAVA[0])).write_text("short"), id="cache-file-resized"),
])
def test_fix_check_refuses_every_damage_with_a_named_problem(prefilled, damage):
    """[FIX] §3 `check`: rc 0 iff the folder, its properties, a PREFILL.json for the committed universe's sha with exactly its valid
    Java items, every offline pass rc 0, and the live manifest holding every recorded entry with its size; else rc != 0."""
    assert prefilled.check() == 0
    damage(prefilled)
    problems = G().check_problems()
    assert problems and all(isinstance(p, str) and p for p in problems)
    assert prefilled.check() != 0


def test_fix_a_deleted_cache_file_is_named_in_the_problem(prefilled):
    (prefilled.folder / X.dep_rel(JAVA[0])).unlink()
    assert any(X.dep_rel(JAVA[0]) in p or "dep.jar" in p for p in G().check_problems())


def test_inv_extra_cache_files_are_not_a_problem(prefilled):
    """[INV] §3 (Sol P4): the live manifest must CONTAIN every recorded entry - a dependency downloaded later is not damage."""
    extra = prefilled.folder / "caches/modules-2/files-2.1/new.group/new-artifact/1.0/new.jar"
    extra.parent.mkdir(parents=True)
    extra.write_text("downloaded later")
    (prefilled.folder / "daemon" / "later.log").write_text("noise")
    assert G().check_problems() == [] and prefilled.check() == 0


def test_inv_check_does_not_modify_the_folder(prefilled):
    def snapshot():
        return sorted((str(p.relative_to(prefilled.folder)), p.read_bytes()) for p in prefilled.folder.rglob("*") if p.is_file())
    before, calls = snapshot(), len(prefilled.calls())
    prefilled.check()
    G().check_problems()
    assert snapshot() == before and len(prefilled.calls()) == calls          # read-only, and it never runs Gradle
    json.loads((prefilled.folder / "PREFILL.json").read_text())
