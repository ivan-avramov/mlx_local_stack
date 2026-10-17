"""P311-lite (iii): the toolchain is checked before the first spawn and before every item (spec test 4)."""
import json

import pytest

from bench import toolchain
from bench.tests.test_opencode_v2_probe import tg1_probe as probe, MODEL    # noqa: F401
from bench.tests.test_tg1_integration import tg_fixture


def test_missing_grader_image_refuses_before_anything_is_written(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)

    def gone():
        raise toolchain.ToolchainError("grader image aider-benchmark is missing or unreadable (rc 1)")
    monkeypatch.setattr(toolchain, "grader_image_id", gone)
    monkeypatch.setattr(probe, "_scratch_dir", lambda *a: pytest.fail("a discovery spawn happened"))
    with pytest.raises(SystemExit, match="REFUSED.*grader image"):
        f["run"]("one")
    assert not f["out"].exists() and not f["mp"].exists()


def test_toolchain_change_between_items_aborts_the_leg(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    calls = []

    def image():
        calls.append(1)
        return "sha256:" + ("a" if len(calls) < 6 else "b") * 64       # changes while the leg is running
    monkeypatch.setattr(toolchain, "grader_image_id", image)
    with pytest.raises(SystemExit, match="REFUSED.*toolchain drift"):
        f["run"]("one,two")
    man = json.loads(f["mp"].read_text())
    assert "toolchain drift" in man["transport_abort"]["error"]
    assert man["runtime"]["policy"]["toolchain"]["grader_image_id"] == "sha256:" + "a" * 64


def test_the_manifest_records_the_toolchain(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    assert f["run"]("one") == 0
    man = json.loads(f["mp"].read_text())
    assert set(man["runtime"]["policy"]["toolchain"]) == {"lock_sha256", "interpreter", "grader_image_id"}
