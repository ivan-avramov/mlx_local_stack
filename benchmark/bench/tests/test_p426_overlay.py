"""P426 B4-stack: the ON registry is built by the fork's own settings-level rule (`registry_states.overlay_on`, C203) from the
frozen build's submodule — one implementation, no mirrored table — and written with its sha256; the leg wrapper's independent
`registry_delta_problems` must accept the result.
"""

import json
import sys
import types
from pathlib import Path

import pytest

from bench import p426_overlay as O
from bench.p426_leg import registry_delta_problems
from bench.tests.test_p426_leg import ENTRY, OFF, ON

REPO = Path(__file__).resolve().parents[3]


def _fake_rs(on_text):
    calls = []

    def overlay_on(text, fixture, entry):
        calls.append((text, fixture, entry))
        return on_text, ["    draft_kind: mtp"]

    return types.SimpleNamespace(
        overlay_on=overlay_on, fixture_text=lambda d: "FIXTURE", settings=lambda t: {}, calls=calls
    )


def test_the_overlay_comes_from_the_fork_rule_and_is_checked(tmp_path):
    rs = _fake_rs(ON)
    out = tmp_path / "registry-on.yaml"
    doc = O.build(OFF, ENTRY, rs, tmp_path / "fixtures", out)
    assert rs.calls == [(OFF, "FIXTURE", ENTRY)]
    assert out.read_text() == ON
    assert doc["sha256"] == O.sha256_text(ON) and doc["off_sha256"] == O.sha256_text(OFF)
    assert json.loads((tmp_path / "registry-on.yaml.json").read_text()) == doc


def test_an_overlay_the_independent_check_refuses_is_not_written(tmp_path):
    bad = ON.replace("    kv_bits: 0", "    kv_bits: 4")
    assert registry_delta_problems(bad, OFF, ENTRY)
    with pytest.raises(ValueError, match="kv_bits"):
        O.build(OFF, ENTRY, _fake_rs(bad), tmp_path, tmp_path / "registry-on.yaml")
    assert not (tmp_path / "registry-on.yaml").exists()


def test_an_existing_overlay_is_never_overwritten(tmp_path):
    out = tmp_path / "registry-on.yaml"
    out.write_text("old")
    with pytest.raises(FileExistsError):
        O.build(OFF, ENTRY, _fake_rs(ON), tmp_path, out)


def test_the_module_loads_the_frozen_builds_registry_states(tmp_path):
    dev = tmp_path / "src/mlx-vlm/dev/p369_phase2"
    dev.mkdir(parents=True)
    (dev / "__init__.py").write_text("")
    (dev / "registry_states.py").write_text("MARK = 'frozen'\ndef settings(t):\n    return {}\n")
    rs = O.load_registry_states(tmp_path)
    assert rs.MARK == "frozen"
    sys.modules.pop("p369_phase2.registry_states", None)
    sys.modules.pop("p369_phase2", None)


def test_a_byte_level_registry_states_is_refused(tmp_path):
    """Before the C203 fork build (no ``settings``) the overlay would need a fixture refresh for every comment edit."""
    dev = tmp_path / "src/mlx-vlm/dev/p369_phase2"
    dev.mkdir(parents=True)
    (dev / "__init__.py").write_text("")
    (dev / "registry_states.py").write_text("MARK = 'old'\n")
    with pytest.raises(RuntimeError, match="C203"):
        O.load_registry_states(tmp_path)
    sys.modules.pop("p369_phase2.registry_states", None)
    sys.modules.pop("p369_phase2", None)


def test_f1_the_cli_reads_the_registry_as_bytes(tmp_path, monkeypatch):
    """B4 code round 1 F1: a CRLF registry must reach the fork's raw check, not be normalized by read_text()."""
    (tmp_path / "main_models.yaml").write_bytes(OFF.replace("\n", "\r\n").encode())
    seen = {}

    def build(off_text, entry, rs, fixtures, out):
        seen["text"] = off_text
        return {}

    monkeypatch.setattr(O, "load_registry_states", lambda root: object())
    monkeypatch.setattr(O, "build", build)
    O.main(["--stack-root", str(tmp_path), "--entry", ENTRY, "--out", str(tmp_path / "on.yaml")])
    assert "\r\n" in seen["text"]
