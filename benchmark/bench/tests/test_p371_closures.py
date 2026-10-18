"""P371 phase 4 (plan 3.1 dependency rule, plan 5 "P311 closure tests extended per probe entry"): the static import closure of
EACH probe entry (`run_tg1_probe.py`, `run_oc_probe.py`) holds the shared core and none of what belongs to the chain, to the
scoring path, to another corpus or to another client:

  excluded from both   tg2_* modules, chain_hooks, web_evidence, chain_core, chain_incident, chain_rows, chain_ops,
                       schedules, campaign_core, every scoring module (answer_key, web_audit*, web_scan, tg1_score,
                       row_scores, generate), the Pi / dsh modules;
  excluded from tg1    m64_search (the D2 search service injection point; run_oc_probe injects it, so ONLY the oc closure
                       may hold it).

The exclusion check is validated against a planted violation (a tree whose entry imports each forbidden module is flagged),
the `sys.modules` of a fake end-to-end item is a subset of the entry's closure (tg1: the existing closure test; oc: here), and
the modules reachable only through configuration that is OFF for the entry (tg1: watchdog, worker receipts, item barrier,
compaction) are named deliberate inputs of the closure, never accidents. Every assertion of `test_p311_closure.py` and
`test_m64_arm_closure.py` stays."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bench import arm_opencode as ao
from bench import identity_closure as ic
from bench import run_config as rc
from bench import tg1_runner

REPO = Path(__file__).resolve().parents[3]
TG1, OC = "benchmark/run_tg1_probe.py", "benchmark/run_oc_probe.py"

# basenames (without .py) no probe closure may hold
CHAIN_SIDE = ("chain_hooks", "web_evidence", "chain_core", "chain_incident", "chain_rows", "chain_ops", "schedules",
              "campaign_core", "contract_artifact")
SCORING = ("answer_key", "web_scan", "tg1_score", "row_scores", "generate")
PREFIXES = ("tg2_", "web_audit")                       # the tg2 corpus / grader, the web auditors
CLIENT_TOKENS = ("pi", "dsh")                          # Pi / dsh adapters, probes and helpers: any `_`-separated token


def closure(entry, root=REPO):
    return {p.resolve().relative_to(Path(root).resolve()).as_posix() for p in ic.python_closure(Path(root) / entry, root)}


def violations(files, *, allow=()):
    """The members of `files` (repo-relative paths) a probe closure must not hold."""
    bad = []
    for rel in sorted(files):
        stem = Path(rel).stem
        tokens = stem.split("_")
        if stem in allow:
            continue
        if (stem in CHAIN_SIDE or stem in SCORING or stem == "m64_search" or stem.startswith(PREFIXES)
                or any(t in CLIENT_TOKENS for t in tokens)):
            bad.append(rel)
    return bad


# ---------------------------------------------------------------- the exclusions, per entry
def test_the_tg1_probe_closure_excludes_everything_that_is_not_the_shared_generation_core():
    got = closure(TG1)
    assert not violations(got), violations(got)
    assert "benchmark/bench/arm_runner.py" in got and "benchmark/bench/tg1_runner.py" in got


def test_the_oc_probe_closure_excludes_the_same_and_holds_the_search_injection_point_only_here():
    got = closure(OC)
    assert not violations(got, allow=("m64_search",)), violations(got, allow=("m64_search",))
    assert "benchmark/bench/m64_search.py" in got and "benchmark/bench/m64_search.py" not in closure(TG1)
    assert not [f for f in got if "/tg2_" in f]


def test_every_forbidden_module_is_a_real_module_so_the_exclusions_are_not_vacuous():
    existing = {p.stem for p in (REPO / "benchmark/bench").glob("*.py")}
    assert {"chain_hooks", "web_evidence", "chain_core", "chain_incident", "chain_rows", "chain_ops", "schedules",
            "campaign_core", "contract_artifact", "answer_key", "web_scan", "tg1_score", "row_scores", "generate",
            "m64_search"} <= existing
    assert any(p.stem.startswith("web_audit") for p in (REPO / "benchmark/bench").glob("*.py")) or \
        any(p.stem.startswith("web_audit") for p in (REPO / "benchmark").glob("*.py"))


def test_the_exclusion_check_flags_a_planted_import_of_each_forbidden_module(tmp_path):
    """Validate the instrument on known positives: a tree whose probe entry imports one forbidden module is flagged."""
    names = list(CHAIN_SIDE) + list(SCORING) + ["tg2_corpus", "web_audit", "arm_pi", "pi_adapter", "dsh_probe", "m64_search"]
    for name in names:
        root = tmp_path / name
        for rel, text in {"benchmark/bench/__init__.py": "", f"benchmark/bench/{name}.py": "X = 1\n",
                          "benchmark/bench/core.py": "Y = 1\n",
                          "benchmark/probe.py": f"from bench import core\nfrom bench import {name}\n"}.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text)
        got = closure("benchmark/probe.py", root)
        assert violations(got) == [f"benchmark/bench/{name}.py"], (name, got)
    assert violations({"benchmark/bench/arm_runner.py", "benchmark/bench/api_client.py", "benchmark/bench/opencode_v2_core.py"}) == []


def test_the_oc_closure_holds_the_tg1_core_the_tg1_closure_holds():
    tg1 = closure(TG1) - {TG1, "benchmark/bench/tg1_runner.py"}
    assert tg1 <= closure(OC)


# ---------------------------------------------------------------- what a fake item really loads
def loaded_modules(tmp_path, node):
    out = tmp_path / "modules.json"
    env = {**os.environ, "P311_REPO": str(REPO), "P311_MODULES_OUT": str(out)}
    run = subprocess.run([sys.executable, "-m", "pytest", "--noconftest", "-p", "bench.tests.p311_modules_plugin",
                          "-p", "no:cacheprovider", "-q", node], cwd=REPO / "benchmark", env=env, capture_output=True,
                         text=True, timeout=300)
    assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-2000:]
    return {m for m in json.loads(out.read_text()) if not m.startswith("benchmark/bench/tests/") and "/__pycache__/" not in m}


# `provenance.gather`'s `router is None` branch; the probe entries always pass the verified router (test_p311_closure)
NEVER_LOADED = {"benchmark/bench/client.py"}


def test_the_modules_a_fake_oc_item_loads_are_inside_the_oc_closure_and_none_is_forbidden(tmp_path):
    loaded = loaded_modules(tmp_path, "bench/tests/test_p371_oc_fake_item.py::test_a_fake_item_runs_through_the_oc_entry")
    assert {"benchmark/run_oc_probe.py", "benchmark/bench/arm_runner.py", "benchmark/bench/arm_opencode.py",
            "benchmark/bench/m64_search.py"} <= loaded
    assert not (loaded - closure(OC)), sorted(loaded - closure(OC))
    assert not violations(loaded, allow=("m64_search",)), violations(loaded, allow=("m64_search",))
    assert not (closure(OC) - loaded - NEVER_LOADED), sorted(closure(OC) - loaded - NEVER_LOADED)


def test_the_modules_a_fake_tg1_item_loads_hold_no_forbidden_module(tmp_path):
    loaded = loaded_modules(tmp_path, "bench/tests/test_tg1_integration.py::test_mocked_tg1_rows_evidence_resume_and_worker_drift")
    assert not violations(loaded), violations(loaded)
    assert not (loaded - closure(TG1)), sorted(loaded - closure(TG1))


# ---------------------------------------------------------------- config-off branches are deliberate closure inputs
# A module only an OFF configuration branch of the entry would use is nevertheless part of the closure: the shared core imports
# it unconditionally, so the identity moves when it changes (C178). Each is named here with the policy that switches it off.
OFF_BRANCHES = {
    "benchmark/bench/arm_watchdog.py": "watchdog off (tg1)",
    "benchmark/bench/toolwindows.py": "watchdog off (tg1): no tool-window receipts",
    "benchmark/bench/worker_receipts.py": "worker_receipts absent (tg1, and m64 until the fork endpoint P372)",
    "benchmark/bench/item_barrier.py": "item_barrier off (tg1; a direct item run)",
}


def test_the_config_off_branches_of_tg1_are_named_deliberate_closure_inputs():
    pol, ev = tg1_runner.TG1_POLICY, tg1_runner.TG1_EVIDENCE
    assert pol.watchdog == rc.WATCHDOG_OFF and pol.compaction == "off"
    assert ev.worker_receipts == "absent" and ev.item_barrier == "off"
    got, reached = closure(TG1), set(ic.reachable_modules(REPO / TG1, REPO))
    for rel, why in OFF_BRANCHES.items():
        assert rel in got and rel in reached, (rel, why)


def test_the_oc_entry_turns_the_watchdog_and_compaction_on_and_keeps_the_same_off_branch_modules():
    tmpl = ao.m64_template()
    assert tmpl.watchdog["mode"] == "on" and tmpl.compaction == "on_accounted"
    assert set(OFF_BRANCHES) <= closure(OC)


def test_every_oc_closure_module_is_reachable_from_the_oc_entry():
    reached = set(ic.reachable_modules(REPO / OC, REPO))
    assert not (closure(OC) - reached), sorted(closure(OC) - reached)


@pytest.mark.parametrize("entry", [TG1, OC])
def test_the_entry_is_not_in_any_other_entrys_closure(entry):
    other = OC if entry == TG1 else TG1
    assert entry not in closure(other) and entry not in closure("benchmark/chains/m64/run_m64_chain.py")
