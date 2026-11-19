"""S26 §1 (implementer tests): `bench.host_env` — the fingerprint over temp trees (a temp agent PATH, Cellar, bin dirs, global
npm, HOME, files): determinism, no subprocess, every `diff` kind, unreadable entries, `[]` iff equal, the box defaults."""
from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import host_env as he


def _exe(path, body="#!/bin/sh\necho one\n", mode=0o755):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(mode)
    return path


def _pkg(root, name, version):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "package.json").write_text(json.dumps({"name": name, "version": version}))


@pytest.fixture
def host(tmp_path):
    t = SimpleNamespace(root=tmp_path)
    t.bin = tmp_path / "agentbin"
    t.bin.mkdir()
    _exe(t.bin / "node")
    t.cellar = tmp_path / "Cellar"
    (t.cellar / "rust" / "1.80.0").mkdir(parents=True)
    (t.cellar / "openjdk@21" / "21.0.4").mkdir(parents=True)
    t.b1, t.b2 = tmp_path / "hb-bin", tmp_path / "usr-local-bin"
    t.b1.mkdir()
    t.b2.mkdir()
    os.symlink("../Cellar/rust/1.80.0/bin/cargo", t.b1 / "cargo")
    (t.b2 / "plain").write_text("x")
    t.npm = tmp_path / "node_modules"
    _pkg(t.npm, "jest", "29.7.0")
    _pkg(t.npm / "@types", "node", "20.1.0")
    (t.npm / ".package-lock.json").write_text("{}")
    t.home = tmp_path / "home"
    (t.home / ".cargo").mkdir(parents=True)
    t.props = tmp_path / "gh" / "gradle.properties"
    return t


def fp(t, **kw):
    return he.fingerprint(**dict(dict(path=str(t.bin), cellar=t.cellar, bin_dirs=(t.b1, t.b2), npm_global=t.npm, home=t.home,
                                      files=(("tg2 gradle.properties", t.props),)), **kw))


def test_the_fingerprint_is_deterministic_json_native_and_runs_nothing(host, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the fingerprint runs no subprocess")
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    a, b = fp(host), fp(host)
    assert a == b and he.diff(a, b) == []
    assert json.loads(json.dumps(a)) == a                          # survives the baseline's JSON round trip unchanged
    assert set(a) == set(he.SECTIONS)
    assert set(a["tools"]) == set(he.TOOLS) and a["tools"]["cargo"] == "absent"
    node = a["tools"]["node"]
    assert node["path"] == os.path.realpath(host.bin / "node") and len(node["sha256"]) == 64
    assert a["cellar"] == ["openjdk@21/21.0.4", "rust/1.80.0"]
    assert a["bin_dirs"][str(host.b1)] == ["cargo -> ../Cellar/rust/1.80.0/bin/cargo"] and a["bin_dirs"][str(host.b2)] == ["plain"]
    assert a["npm_global"] == {"jest": "29.7.0", "@types/node": "20.1.0"}
    assert a["home_toolchains"][".cargo"] == "present" and a["home_toolchains"]["Library/Python"] == "absent"
    assert a["files"] == {"tg2 gradle.properties": "absent"}


def test_the_box_constants():
    from bench.opencode_v2_core import SCAFFOLD_ENV_POLICY_V2
    assert he.AGENT_PATH == SCAFFOLD_ENV_POLICY_V2["PATH"]
    assert he.TOOLS == ("cargo", "rustc", "java", "javac", "gradle", "node", "npm", "g++", "clang++", "cmake", "make", "python3",
                        "go", "docker")
    assert he.CELLAR == Path("/opt/homebrew/Cellar") and he.NPM_GLOBAL == Path("/opt/homebrew/lib/node_modules")
    assert he.BIN_DIRS == (Path("/opt/homebrew/bin"), Path("/usr/local/bin"))
    assert he.HOME_TOOLCHAINS == (".cargo", ".rustup", ".sdkman", ".gradle", ".m2", ".npm-global", "Library/Python")


def test_diff_names_a_tool_that_appears_and_one_whose_file_changes(host):
    before = fp(host)
    _exe(host.bin / "cargo")
    after = fp(host)
    (line,) = he.diff(before, after)
    assert line.startswith("tool cargo: absent -> ") and os.path.realpath(host.bin / "cargo") in line
    _exe(host.bin / "node", body="#!/bin/sh\necho two\n")              # same path, other bytes
    (line,) = he.diff(after, fp(host))
    assert line.startswith("tool node: ") and line.count("sha256") == 2


def test_diff_names_cellar_additions_and_removals(host):
    before = fp(host)
    (host.cellar / "openjdk@17" / "17.0.12").mkdir(parents=True)
    import shutil
    shutil.rmtree(host.cellar / "rust" / "1.80.0")
    assert he.diff(before, fp(host)) == ["Homebrew Cellar: added openjdk@17/17.0.12", "Homebrew Cellar: removed rust/1.80.0"]


def test_diff_names_a_bin_dir_symlink_retarget_and_new_entries(host):
    before = fp(host)
    (host.b1 / "cargo").unlink()
    os.symlink("../Cellar/rust/1.81.0/bin/cargo", host.b1 / "cargo")
    os.symlink("/opt/x/java", host.b2 / "java")
    lines = he.diff(before, fp(host))
    assert f"{host.b1}: cargo: ../Cellar/rust/1.80.0/bin/cargo -> ../Cellar/rust/1.81.0/bin/cargo" in lines
    assert f"{host.b2}: added java -> /opt/x/java" in lines and len(lines) == 2


def test_diff_names_npm_global_version_changes_scoped_packages_and_an_absent_directory(host, tmp_path):
    before = fp(host)
    _pkg(host.npm, "jest", "29.8.0")
    _pkg(host.npm / "@types", "jest", "29.5.0")
    lines = he.diff(before, fp(host))
    assert lines == ["npm -g @types/jest: absent -> 29.5.0", "npm -g jest: 29.7.0 -> 29.8.0"]
    gone = fp(host, npm_global=tmp_path / "no-node-modules")
    assert gone["npm_global"] is None
    lines = he.diff(gone, fp(host))
    assert lines[0].startswith("npm -g (") and "absent -> present" in lines[0]
    assert "npm -g jest: absent -> 29.8.0" in lines


def test_diff_names_home_toolchains_including_library_python(host):
    before = fp(host)
    (host.home / "Library" / "Python").mkdir(parents=True)
    (host.home / ".gradle").mkdir()
    assert he.diff(before, fp(host)) == ["~/.gradle: absent -> present", "~/Library/Python: absent -> present"]


def test_diff_names_a_watched_file(host):
    before = fp(host)
    host.props.parent.mkdir(parents=True)
    host.props.write_text("org.gradle.daemon=false\n")
    after = fp(host)
    (line,) = he.diff(before, after)
    assert line.startswith("file tg2 gradle.properties: absent -> ") and after["files"]["tg2 gradle.properties"] in line
    host.props.write_text("org.gradle.daemon=true\n")
    assert he.diff(after, fp(host))[0].startswith("file tg2 gradle.properties: ")


def test_an_unreadable_entry_records_its_exception_and_never_raises(host):
    _exe(host.bin / "java", mode=0o111)                                # executable, not readable: which() finds it
    (host.npm / "broken").mkdir()
    (host.npm / "broken" / "package.json").write_text("{not json")
    locked = host.cellar / "rust"
    locked.chmod(0o000)
    try:
        a = fp(host)
    finally:
        locked.chmod(0o755)
        (host.bin / "java").chmod(0o755)
    if os.geteuid() == 0:
        pytest.skip("root reads everything")
    assert a["tools"]["java"] == "error: PermissionError"
    assert a["npm_global"]["broken"] == "error: JSONDecodeError"
    assert "rust/error: PermissionError" in a["cellar"]
    assert he.fingerprint(cellar=host.root / "Cellar-missing", bin_dirs=(), npm_global=host.npm, home=host.home,
                          path=str(host.bin))["cellar"] is None


def test_diff_is_empty_iff_equal_including_unknown_keys_and_section_errors(host):
    a = fp(host)
    b = copy.deepcopy(a)
    assert he.diff(a, b) == []
    b["extra"] = 1
    assert he.diff(a, b) == ["extra: absent -> 1"]
    c = copy.deepcopy(a)
    c["cellar"] = "error: PermissionError"
    assert he.diff(a, c) == [f"Homebrew Cellar: {json.dumps(a['cellar'], sort_keys=True)} -> error: PermissionError"]
    d = copy.deepcopy(a)
    d["path"] = "/usr/bin"
    assert he.diff(a, d) == [f"agent PATH: {a['path']} -> /usr/bin"]


def test_the_real_home_is_written_as_a_tilde(host):
    home = Path(os.path.realpath(host.home))
    inside = home / ".cargo" / "bin"
    _exe(inside / "rustc")
    a = he.fingerprint(path=str(inside), cellar=host.cellar, bin_dirs=(), npm_global=host.npm, home=home)
    assert a["tools"]["rustc"]["path"] == "~/.cargo/bin/rustc"
    assert he.portable(str(home), home) == "~" and he.portable("/opt/x", home) == "/opt/x"


def test_fingerprint_for_run_watches_the_tg2_gradle_properties(host, tmp_path):
    kw = dict(path=str(host.bin), cellar=host.cellar, bin_dirs=(), npm_global=host.npm, home=host.home)
    wd = tmp_path / "wd"
    a = he.fingerprint_for_run(workdir=wd, **kw)
    assert a["files"] == {"tg2 gradle.properties": "absent"}
    (wd / "tg2-gradle-home").mkdir(parents=True)
    (wd / "tg2-gradle-home" / "gradle.properties").write_text("org.gradle.daemon=false\n")
    b = he.fingerprint_for_run(workdir=wd, **kw)
    assert len(b["files"]["tg2 gradle.properties"]) == 64 and he.diff(a, b)[0].startswith("file tg2 gradle.properties")
