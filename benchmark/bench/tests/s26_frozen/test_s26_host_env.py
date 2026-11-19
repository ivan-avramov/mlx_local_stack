"""S26 frozen tests, `bench/host_env.py` (spec §1; acceptance 1: fingerprint determinism and each `diff` kind, an unreadable entry).

Classes: [FIX] reproduces a failure the spec fixes (a host change a leg made went unseen); [INV] preserves an invariant;
[NEW] new behaviour. The module is new, so every test here fails on the baseline (ImportError) - the [FIX] ones are the
host-mutation kinds: before the change nothing could see them. Temp trees only (`s26_support.HostWorld`); no subprocess runs."""
from __future__ import annotations

import json
import os
import subprocess

import pytest

from bench.tests.s26_frozen import s26_support as X

TOOLS = ("cargo", "rustc", "java", "javac", "gradle", "node", "npm", "g++", "clang++", "cmake", "make", "python3", "go", "docker")


@pytest.fixture
def host(tmp_path):
    return X.HostWorld(tmp_path / "host")


def H():
    from bench import host_env
    return host_env


def changes(before, after):
    return H().diff(before, after)


# ---------------------------------------------------------------------------------------------------- shape / determinism
def test_new_tools_list_is_the_spec_set():
    """[NEW] §1: `TOOLS` is exactly the fourteen names the agent's shell may reach."""
    assert tuple(H().TOOLS) == TOOLS or set(H().TOOLS) == set(TOOLS)


def test_new_fingerprint_is_deterministic_json_and_has_every_section(host):
    """[NEW] §1: deterministic for an unchanged host, JSON-serialisable, one section per concern."""
    a, b = host.fingerprint(), host.fingerprint()
    assert a == b and json.loads(json.dumps(a)) == a
    assert {"tools", "cellar", "bin_dirs", "npm_global", "home_toolchains", "files"} <= set(a)
    assert set(a["tools"]) == set(TOOLS)
    assert changes(a, b) == []


def test_new_tool_entry_is_absent_or_realpath_plus_sha_of_the_resolved_file(host, tmp_path):
    """[NEW] §1 `tools`: `"absent"`, or `{path: realpath, sha256: sha256 of the resolved file}` (symlinks resolved)."""
    fp = host.fingerprint()
    assert fp["tools"]["cargo"] == "absent"
    real = host.real / "java"
    assert fp["tools"]["java"] == {"path": os.path.realpath(host.bin / "java"), "sha256": X.sha256_file(real)}
    assert fp["tools"]["java"]["path"] == str(real.resolve())


def test_new_fingerprint_never_runs_a_tool(host, tmp_path, monkeypatch):
    """[FIX] S26-P9 r1 P3: no `--version` call. A tool that would leave a marker if executed, and every process-spawning entry
    point made to fail, prove the fingerprint only reads files."""
    marker = tmp_path / "ran.marker"
    host.tool("cargo", f"#!/bin/sh\ntouch {marker}\n".encode())

    def boom(*a, **k):
        raise AssertionError("the fingerprint started a process")
    for name in ("run", "Popen", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, boom)
    for name in ("system", "popen", "execv", "execvp", "spawnv"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, boom)
    fp = host.fingerprint()
    assert fp["tools"]["cargo"] != "absent" and not marker.exists()


# ---------------------------------------------------------------------------------------------------- diff: tools
def test_fix_a_tool_that_appears_is_a_named_change(host):
    """[FIX] C360: a leg installing a toolchain (`brew install rust` puts `cargo` on the agent PATH) is a `tool cargo` change."""
    before = host.fingerprint()
    real = host.tool("cargo", b"cargo-1\n")
    after = host.fingerprint()
    lines = changes(before, after)
    assert len(lines) == 1 and lines[0].startswith("tool cargo: absent -> ") and os.path.realpath(real) in lines[0]


def test_fix_a_tool_that_vanishes_is_a_named_change(host):
    before = (host.tool("cargo", b"cargo-1\n"), host.fingerprint())[1]
    host.rm_tool("cargo")
    lines = changes(before, host.fingerprint())
    assert len(lines) == 1 and lines[0].startswith("tool cargo") and "absent" in lines[0]


def test_fix_a_tool_whose_file_changed_in_place_is_a_change(host):
    """[FIX] same path, new bytes (`brew upgrade` rewriting the binary): only the file hash can see it."""
    host.tool("cargo", b"cargo-1\n")
    before = host.fingerprint()
    host.tool("cargo", b"cargo-2\n")                         # same name, same symlink, new content
    lines = changes(before, host.fingerprint())
    assert len(lines) == 1 and lines[0].startswith("tool cargo")


def test_fix_a_tool_relinked_to_another_file_is_a_change(host):
    """[FIX] the symlink retargeted (path differs, bytes may not): the realpath is part of the entry."""
    host.tool("cargo", b"cargo-1\n")
    host.tool("cargo-other", b"cargo-1\n")                  # identical bytes, other file
    before = host.fingerprint()
    (host.bin / "cargo").unlink()
    (host.bin / "cargo").symlink_to(host.real / "cargo-other")
    lines = changes(before, host.fingerprint())
    assert any(line.startswith("tool cargo") for line in lines)


def test_inv_an_unchanged_tool_set_has_no_diff_whatever_else_changed(host):
    before = host.fingerprint()
    host.formula("x", "1")
    assert not [line for line in changes(before, host.fingerprint()) if line.startswith("tool ")]


# ---------------------------------------------------------------------------------------------------- diff: Cellar
def test_fix_cellar_is_sorted_formula_slash_version(host):
    host.formula("openjdk@21", "21.0.2")
    host.formula("cmake", "3.30.1")
    assert host.fingerprint()["cellar"] == sorted(["cmake/3.30.1", "openjdk@21/21.0.2", "rust/1.80.0"])


def test_fix_a_formula_added_is_named(host):
    """[FIX] C360 / the spec's traced case: a leg runs `brew install openjdk@17`."""
    before = host.fingerprint()
    host.formula("openjdk@17", "17.0.9")
    assert changes(before, host.fingerprint()) == ["Homebrew Cellar: added openjdk@17/17.0.9"]


def test_fix_a_formula_removed_and_a_version_bumped_are_named(host):
    before = host.fingerprint()
    host.rm_formula("rust", "1.80.0")
    host.formula("rust", "1.81.0")
    lines = changes(before, host.fingerprint())
    assert len(lines) == 2 and all(line.startswith("Homebrew Cellar: ") for line in lines)
    assert any("added rust/1.81.0" in line for line in lines) and any("rust/1.80.0" in line and "removed" in line for line in lines)


# ---------------------------------------------------------------------------------------------------- diff: bin dirs
def test_fix_bin_dirs_hold_name_or_name_arrow_target(host):
    host.bin_link(host.brewbin, "python3", "../Cellar/python/3.12/bin/python3")
    entries = list(host.fingerprint()["bin_dirs"].values())
    flat = [e for v in entries for e in v]
    assert "brew-tool" in flat and "python3 -> ../Cellar/python/3.12/bin/python3" in flat
    assert all(v == sorted(v) for v in entries)


def test_fix_a_bin_entry_added_and_removed_is_named(host):
    before = host.fingerprint()
    host.bin_file(host.usrbin, "newtool")
    added = changes(before, host.fingerprint())
    assert len(added) == 1 and "newtool" in added[0]
    mid = host.fingerprint()
    (host.brewbin / "brew-tool").unlink()
    removed = changes(mid, host.fingerprint())
    assert len(removed) == 1 and "brew-tool" in removed[0]


def test_fix_a_symlink_retarget_in_a_bin_dir_is_a_change(host):
    """[FIX] `brew link --force openjdk@21` repoints `/opt/homebrew/bin/java`: the entry's text changes with the target."""
    host.bin_link(host.brewbin, "java", "../Cellar/openjdk@17/17.0.9/bin/java")
    before = host.fingerprint()
    host.bin_link(host.brewbin, "java", "../Cellar/openjdk@21/21.0.2/bin/java")
    lines = changes(before, host.fingerprint())
    assert len(lines) == 1 and "java" in lines[0] and "openjdk@21" in lines[0]


# ---------------------------------------------------------------------------------------------------- diff: npm -g
def test_fix_npm_global_is_package_to_version_and_none_when_the_dir_is_absent(host, tmp_path):
    host.npm_pkg("jest", "29.7.0")
    host.npm_pkg("@scope/pkg", "1.2.3")                     # a scoped package sits one level deeper
    fp = host.fingerprint()["npm_global"]
    assert fp["jest"] == "29.7.0"
    assert "1.2.3" in fp.values() and any(k.endswith("pkg") for k in fp)
    from bench import host_env
    missing = host_env.fingerprint(path=str(host.bin), cellar=host.cellar, bin_dirs=(host.brewbin,), npm_global=tmp_path / "nope",
                                   home=host.home, files=())
    assert missing["npm_global"] is None


def test_fix_npm_global_install_and_version_change_are_named(host):
    before = host.fingerprint()
    host.npm_pkg("jest", "29.7.0")
    assert changes(before, host.fingerprint()) == ["npm -g jest: absent -> 29.7.0"]
    mid = host.fingerprint()
    host.npm_pkg("jest", "30.0.0")
    lines = changes(mid, host.fingerprint())
    assert len(lines) == 1 and lines[0].startswith("npm -g jest") and "29.7.0" in lines[0] and "30.0.0" in lines[0]


# ---------------------------------------------------------------------------------------------------- diff: home toolchains
@pytest.mark.parametrize("rel", [".cargo", ".rustup", ".sdkman", ".gradle", ".m2", ".npm-global", "Library/Python"])
def test_fix_each_home_toolchain_dir_appearing_is_named(host, rel):
    """[FIX] S26-P5 / P6: the seven per-user toolchain homes, `Library/Python` included."""
    before = host.fingerprint()
    assert set(before["home_toolchains"]) == {".cargo", ".rustup", ".sdkman", ".gradle", ".m2", ".npm-global", "Library/Python"}
    host.home_dir(rel)
    assert changes(before, host.fingerprint()) == [f"~/{rel}: absent -> present"]
    assert changes(host.fingerprint(), before) == [f"~/{rel}: present -> absent"]


def test_inv_contents_of_an_existing_toolchain_dir_are_not_hashed(host):
    """[INV] non-goal §: a change INSIDE an already-present `~/.gradle` is residual, not seen."""
    host.home_dir(".gradle")
    before = host.fingerprint()
    (host.home / ".gradle" / "caches.txt").write_text("downloaded")
    assert changes(before, host.fingerprint()) == []


# ---------------------------------------------------------------------------------------------------- files
def test_new_files_record_sha_or_absent_and_diff_names_the_label(host, tmp_path):
    """[NEW] §1 `files`: `{label: sha256 | "absent"}` for the (label, path) pairs the caller passes."""
    props = tmp_path / "gradle.properties"
    label = "tg2 gradle.properties"
    absent = host.fingerprint(files=((label, props),))
    assert absent["files"] == {label: "absent"}
    props.write_text("org.gradle.daemon=false\n")
    present = host.fingerprint(files=((label, props),))
    assert present["files"] == {label: X.sha256_bytes(b"org.gradle.daemon=false\n")}
    lines = changes(absent, present)
    assert len(lines) == 1 and label in lines[0]
    props.write_text("org.gradle.daemon=true\n")
    assert len(changes(present, host.fingerprint(files=((label, props),)))) == 1


# ---------------------------------------------------------------------------------------------------- unreadable entries
@pytest.mark.skipif(os.geteuid() == 0, reason="root reads through mode 000")
def test_new_an_unreadable_file_records_error_and_never_raises(host, tmp_path):
    """[NEW] §1: an unreadable entry records `"error: <ExceptionName>"`."""
    f = tmp_path / "locked"
    f.write_text("x")
    f.chmod(0)
    try:
        fp = host.fingerprint(files=(("locked", f),))
    finally:
        f.chmod(0o600)
    assert fp["files"]["locked"] == "error: PermissionError"


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads through mode 000")
def test_new_an_unreadable_tool_binary_records_error_and_never_raises(host):
    real = host.tool("cargo", b"cargo\n")
    real.chmod(0o111)                                    # executable (so on the agent PATH) but not readable: the hash fails
    try:
        fp = host.fingerprint()
    finally:
        real.chmod(0o755)
    assert "error: PermissionError" in json.dumps(fp["tools"]["cargo"])


def test_new_a_damaged_npm_package_json_records_error_and_never_raises(host):
    host.npm_pkg("jest", "29.7.0")
    (host.npm / "jest" / "package.json").write_text("{not json")
    fp = host.fingerprint()
    assert "error: " in json.dumps(fp["npm_global"])


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads through mode 000")
def test_new_an_unreadable_cellar_records_error_and_never_raises(host):
    host.cellar.chmod(0)
    try:
        fp = host.fingerprint()
    finally:
        host.cellar.chmod(0o755)
    assert "error: " in json.dumps(fp["cellar"])


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads through mode 000")
def test_new_an_error_entry_is_stable_and_differs_from_a_healthy_one(host, tmp_path):
    """[NEW] the same unreadable entry twice diffs to `[]`; against the readable entry it is a change (never a silent equal)."""
    f = tmp_path / "locked"
    f.write_text("x")
    healthy = host.fingerprint(files=(("locked", f),))
    f.chmod(0)
    try:
        e1, e2 = host.fingerprint(files=(("locked", f),)), host.fingerprint(files=(("locked", f),))
    finally:
        f.chmod(0o600)
    assert changes(e1, e2) == [] and len(changes(healthy, e1)) == 1


# ---------------------------------------------------------------------------------------------------- diff itself
def test_inv_diff_is_empty_iff_equal_and_lists_every_changed_key(host):
    """[INV] §1 `diff`: `[]` iff equal; otherwise one human-readable line per changed key."""
    before = host.fingerprint()
    assert changes(before, json.loads(json.dumps(before))) == []
    host.formula("x", "1")
    host.home_dir(".cargo")
    host.npm_pkg("jest", "29.7.0")
    host.tool("cargo", b"c\n")
    lines = changes(before, host.fingerprint())
    assert len(lines) == 4 and all(isinstance(line, str) and line for line in lines)
    assert changes(host.fingerprint(), before) and changes(before, host.fingerprint())


# ---------------------------------------------------------------------------------------------------- the box call
def test_new_fingerprint_for_run_adds_the_tg2_gradle_properties_file(tmp_path, monkeypatch):
    """[NEW] §1: `fingerprint_for_run()` = defaults + `files=(("tg2 gradle.properties", <tg2 Gradle home>/gradle.properties),)`.
    (Real defaults read the box's tools read-only; only structure is asserted.)"""
    wd = tmp_path / "wd"
    (wd / "tg2-gradle-home").mkdir(parents=True)
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    fp = H().fingerprint_for_run()
    assert json.loads(json.dumps(fp)) == fp and set(fp["tools"]) == set(TOOLS)
    assert fp["files"] == {"tg2 gradle.properties": "absent"}
    (wd / "tg2-gradle-home" / "gradle.properties").write_text("org.gradle.daemon=false\n")
    fp2 = H().fingerprint_for_run()
    assert fp2["files"] == {"tg2 gradle.properties": X.sha256_bytes(b"org.gradle.daemon=false\n")}
    assert [line for line in changes(fp, fp2) if "gradle.properties" in line]
