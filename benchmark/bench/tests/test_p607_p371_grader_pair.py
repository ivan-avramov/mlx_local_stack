"""P607: the P371 baseline accepts P604's grader bump as exactly one pinned pair per key, and nothing else."""
from bench import structured_grade as sg
from bench.tests.p371_baseline import new_side as ns

GV = "/runs/0/manifest/runtime/policy/grader_version"
UNI = "/runs/0/manifest/runtime/policy/universe_sha256"


def hook():
    return ns.rederive({"_expected": [None]})


def test_the_pinned_new_grader_version_is_the_current_one():
    assert ns.GRADER_VERSION_NEW == sg.VERSION          # a later bump fails here until a reviewed pair replaces this one


def test_exactly_the_pinned_pairs_are_accepted():
    h = hook()
    assert h(GV, ns.GRADER_VERSION_OLD, ns.GRADER_VERSION_NEW)
    assert h(UNI, ns.FIXTURE_UNIVERSE_OLD, ns.FIXTURE_UNIVERSE_NEW)


def test_any_other_value_change_is_refused():
    h = hook()
    assert not h(GV, ns.GRADER_VERSION_NEW, ns.GRADER_VERSION_OLD)
    assert not h(GV, ns.GRADER_VERSION_OLD, "m62-structured-v4")
    assert not h(UNI, ns.FIXTURE_UNIVERSE_OLD, "0" * 64)
    assert not h(UNI, "0" * 64, ns.FIXTURE_UNIVERSE_NEW)
    assert not h("/runs/0/manifest/runtime/policy/grader_timeout_s", ns.GRADER_VERSION_OLD, ns.GRADER_VERSION_NEW)


def test_the_pinned_new_fixture_universe_is_the_current_fixture(tmp_path, monkeypatch):
    """Review r1 P2: the universe pair is guarded directly, not only through the differentials."""
    import importlib
    from bench.tests.test_tg1_integration import tg_fixture
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    monkeypatch.delenv("MLX_SERVE_CONFIG", raising=False)
    tg_fixture(importlib.import_module("run_tg1_probe"), monkeypatch, tmp_path)
    assert (tmp_path / "universe.json.sha256").read_text().strip() == ns.FIXTURE_UNIVERSE_NEW
