"""P158: the frozen 1.18 entry point refuses before argument handling or I/O."""
import os
import shlex
import sys

import pytest

import run_opencode_probe as probe


REFUSAL = (
    "REFUSED: the opencode 1.18 probe is frozen (M59, 2026-10-07); "
    "rows are retained; use run_opencode_probe_v2.py"
)


@pytest.mark.parametrize("argv", [
    [], ["--help"], ["--unknown"],
    ["--model", "m", "--items", "x", "--seed-base", "1"],
    ["--model", "m", "--items", "x", "--seed-base", "bad", "--allow-version-drift"],
])
@pytest.mark.parametrize("workdir_set", [False, True])
def test_main_refuses_any_argv_without_io(tmp_path, monkeypatch, argv, workdir_set):
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    calls = tmp_path / "invocations"
    for directory in ("path-bin", "pinned-bin"):
        binary = tmp_path / directory / "opencode"
        binary.parent.mkdir()
        binary.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" >> ' + shlex.quote(str(calls)) + '\necho 1.18.30\n'
        )
        binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path / "path-bin") + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(tmp_path / "pinned-bin/opencode"))
    if workdir_set:
        monkeypatch.setenv("STACK_WORKDIR", str(workdir))
    else:
        monkeypatch.delenv("STACK_WORKDIR", raising=False)
    monkeypatch.setattr(sys, "argv", ["run_opencode_probe.py", *argv])

    def no_io(*args, **kwargs):
        pytest.fail("frozen main attempted I/O")

    # Block resolution and network discovery even during the pre-freeze red run.
    monkeypatch.setattr(probe, "_stack_workdir", no_io)
    monkeypatch.setattr(probe.provenance, "opencode_router_base", no_io)
    monkeypatch.setattr(probe.provenance, "assert_served_config", no_io)
    real_getitem = type(os.environ).__getitem__

    def no_workdir_read(env, key):
        if key == "STACK_WORKDIR":
            no_io()
        return real_getitem(env, key)

    with monkeypatch.context() as guard:
        guard.setattr(type(os.environ), "__getitem__", no_workdir_read)
        with pytest.raises(SystemExit) as error:
            probe.main()
    assert error.value.code == REFUSAL
    assert not calls.exists(), "a PATH or pinned opencode was invoked"
    assert list(workdir.iterdir()) == []


def test_frozen_probe_keeps_its_version_pin():
    assert probe.PINNED_OPENCODE_VERSION == "1.18.30"
