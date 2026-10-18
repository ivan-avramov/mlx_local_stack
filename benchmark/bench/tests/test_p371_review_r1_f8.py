"""P371 review r1 F8: the A14 baseline harness no longer hides toolchain changes (`interpreter` is compared exactly) and accepts
no new policy key / lifecycle member by PREFIX: every new policy key is named in the table, every new lifecycle member is
accepted only when the independent hook re-derives its value (the file's sha256 now, the chain config's canonical sha256)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bench import toolchain
from bench.tests.p371_baseline import compare as cmp_mod
from bench.tests.p371_baseline import new_side, normalize, runner
from bench.tests.test_p371_baseline import chain_sample, sample

REPO = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def esc(rel):
    return rel.replace("/", "~1")


def test_the_normalizer_keeps_the_interpreter_identity():
    doc = {"toolchain": {"interpreter": "CPython 3.12.15", "lock_sha256": "a" * 64}}
    assert normalize.Normalizer().apply(doc) == doc
    assert "interpreter" not in normalize.VOLATILE_KEYS


def test_the_goldens_pin_the_interpreter_this_box_runs():
    for name in runner.scenario_names():
        golden = runner.load_golden(name)
        if golden["kind"] != "item":
            continue
        got = golden["runs"][0]["manifest"]["runtime"]["policy"]["toolchain"]["interpreter"]
        assert got == toolchain.interpreter_version(), f"{name}: regenerate the goldens (`runner regen`) on this interpreter"


def test_a_changed_interpreter_between_the_sides_is_a_difference():
    old, new = sample(), sample()
    for side, value in ((old, "CPython 3.12.15"), (new, "CPython 3.13.0")):
        side["runs"][0]["manifest"]["runtime"]["policy"]["toolchain"] = {"interpreter": value}
    res = cmp_mod.compare(old, new, cmp_mod.TABLE, rederive=lambda *a: True)
    assert not res.ok and any("toolchain/interpreter" in f for f in res.failures)


def test_no_policy_key_or_lifecycle_member_is_accepted_by_prefix():
    assert cmp_mod.TABLE["manifest_addition_prefixes"] == [] and cmp_mod.TABLE["chain_addition_prefixes"] == []
    old, new = sample(), sample()
    new["runs"][0]["manifest"]["runtime"]["policy"]["surprise"] = {"x": 1}
    res = cmp_mod.compare(old, new, cmp_mod.TABLE, rederive=lambda *a: True)
    assert not res.ok and any("/runtime/policy/surprise" in f for f in res.failures)


def test_a_new_lifecycle_member_needs_the_hook_to_rederive_it():
    old, new = chain_sample(), chain_sample()
    new["chain_json"]["lifecycle"]["benchmark/bench/chain_core.py"] = "z"
    assert not cmp_mod.compare(old, new, cmp_mod.TABLE).ok                                       # no hook: refused
    seen = []
    ok = cmp_mod.compare(old, new, cmp_mod.TABLE, rederive=lambda p, o, n: seen.append((p, o, n)) or True)
    assert ok.ok and seen == [("/chain_json/lifecycle/benchmark~1bench~1chain_core.py", None, "z")]
    assert not cmp_mod.compare(old, new, cmp_mod.TABLE, rederive=lambda *a: False).ok


def test_the_chain_hook_rederives_closure_members_and_the_chain_config():
    result = {"chain_json": {"chain_config": {"config_id": "tg1", "arms": []}}}
    hook = new_side.chain_rederive(result)
    member = "benchmark/bench/chain_core.py"
    assert hook("/chain_json/lifecycle/" + esc(member), None, sha(REPO / member))
    assert not hook("/chain_json/lifecycle/" + esc(member), None, "f" * 64)
    assert not hook("/chain_json/lifecycle/" + esc("benchmark/bench/not_in_the_closure.py"), None, sha(REPO / member))
    cfg = hashlib.sha256(json.dumps(result["chain_json"]["chain_config"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert hook("/chain_json/lifecycle/chain_config", None, cfg) and not hook("/chain_json/lifecycle/chain_config", None, "f" * 64)
