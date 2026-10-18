"""P371 phase 1b: the explicit `Host` seam (plan 3.1 "Host seam"): client-neutral process helpers only, checked at entry."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import host as hostmod
from bench.tests.test_opencode_v2_probe import tg1_probe as probe  # noqa: F401  (fixture)

BENCH = Path(__file__).resolve().parents[1]

EXPECTED = ("_scrub_pii", "_scrub_error", "_portable", "_sha_of", "_stack_workdir", "_prompt_date", "_scratch_dir",
            "_item_scratch_dir", "_fresh_tmpdir", "_git_init_scratch", "_freeze_mtimes")


def stub(**drop):
    ns = SimpleNamespace(**{name: (lambda *a, **k: None) for name in EXPECTED})
    for name in drop:
        delattr(ns, name)
    return ns


def test_the_host_helper_list_is_exactly_the_plan_seam():
    assert hostmod.HOST_HELPERS == EXPECTED
    assert set(hostmod.Host.__annotations__ if hasattr(hostmod.Host, "__annotations__") else ()) <= set(EXPECTED)
    for name in EXPECTED:
        assert hasattr(hostmod.Host, name), name


def test_the_tg1_entry_bound_to_opencode_v2_core_satisfies_host(probe):
    assert hostmod.require_host(probe) is probe
    assert isinstance(probe, hostmod.Host)


def test_a_complete_stub_satisfies_host():
    ns = stub()
    assert hostmod.require_host(ns) is ns


@pytest.mark.parametrize("missing", EXPECTED)
def test_a_stub_missing_one_helper_is_refused_naming_it(missing):
    with pytest.raises(hostmod.HostSeamError, match=missing):
        hostmod.require_host(stub(**{missing: None}))


def test_all_missing_helpers_are_listed_together():
    with pytest.raises(hostmod.HostSeamError) as e:
        hostmod.require_host(SimpleNamespace())
    assert all(name in str(e.value) for name in EXPECTED)


def test_a_non_callable_helper_is_refused():
    ns = stub()
    ns._sha_of = "not callable"
    with pytest.raises(hostmod.HostSeamError, match="_sha_of"):
        hostmod.require_host(ns)


def test_the_host_module_imports_no_corpus_adapter_or_client_module():
    tree = ast.parse((BENCH / "host.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(((node.module or "").split(".")[0]) or "." + ",".join(a.name for a in node.names))
    banned = ("corpus", "arm_", "opencode", "tg1", "tg2", "m64", "answer_key", "web_")
    assert not [m for m in imported if any(b in m for b in banned)], imported


def test_every_tg1_runner_host_call_that_is_client_neutral_is_in_the_seam():
    """Drift guard: the `p.<name>` helpers `tg1_runner` calls are either in the seam or on the documented
    corpus / opencode-specific list; a new unclassified call fails here."""
    src = (BENCH / "tg1_runner.py").read_text()
    called = {n.attr for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "p"}
    non_seam = set(hostmod.NON_SEAM_HOST_USES)
    unclassified = called - set(EXPECTED) - non_seam
    assert not unclassified, sorted(unclassified)
    assert not (non_seam & set(EXPECTED))


def test_every_core_host_call_is_in_the_seam_or_classified():
    """The shared core (`arm_runner`) is held to the same drift guard as the thinned tg1 runner."""
    src = (BENCH / "arm_runner.py").read_text()
    called = {n.attr for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "p"}
    unclassified = called - set(EXPECTED) - set(hostmod.NON_SEAM_HOST_USES)
    assert not unclassified, sorted(unclassified)
