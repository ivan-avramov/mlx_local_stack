"""P409: unit tests never talk to docker — including fixtures of module / class scope.

`conftest._fixed_grader_image` replaced `toolchain.grader_image_id` per FUNCTION, but pytest builds higher-scoped
fixtures first, so a module-scoped fixture (e.g. `test_p371_isolation.both_orders`) reached the real docker daemon: with
OrbStack down it raised `cannot inspect grader image … FileNotFoundError` and errored 8 tests.
"""

import pytest

from bench import toolchain

FAKE = "sha256:" + "f" * 64


@pytest.fixture(scope="module")
def module_scoped_image():
    return toolchain.grader_image_id()


def test_a_module_scoped_fixture_sees_the_fixed_grader_image(module_scoped_image):
    assert module_scoped_image == FAKE


def test_a_test_can_still_override_it(monkeypatch):
    monkeypatch.setattr(toolchain, "grader_image_id", lambda: "sha256:" + "a" * 64)
    assert toolchain.grader_image_id() == "sha256:" + "a" * 64
