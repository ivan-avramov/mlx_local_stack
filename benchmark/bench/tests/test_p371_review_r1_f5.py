"""P371 review r1 F5: A7's exact cleanup validator (`cleanup_problems`) runs before EVERY retry / restart path: the incident
retry, the fallback restart (`restart_load`, an unclassified failure), a hook re-run and a pre-spawn retry. A receipt with
`completed: false`, a nonempty `unknown` or an extra key refuses the retry; nothing is archived and no new invocation starts."""
from __future__ import annotations

import pytest

from bench import chain_hooks as ch
from bench.tests.m64_support import (  # noqa: F401  (fixture: env)
    FAP, PICK1, SMOKE, calls, chain_json, env, invocations, log_has, run, schedule)
from bench.tests.test_p371_m64_hooks import Script, cell_items, cheat_on, pre_spawn_on, slot

BAD = ["incomplete", "unknown", "extra", "orphans"]


def refused(env, rc, before):
    assert rc == 2 and log_has(env, "cleanup")
    assert len(invocations(env)) == before                                     # no retry / restart invocation started
    cj = chain_json(env)
    assert not any(l["archives"] for l in cj["progress"]["loads"]) and not (env["out"] / "s1" / "incomplete").exists()
    assert len(calls(env, "load")) == 1                                        # the worker was neither reloaded nor replaced


@pytest.mark.parametrize("variant", BAD)
def test_the_fallback_restart_path_requires_the_exact_cleanup_receipt(env, variant):
    plan = {"oc": [{"abort_after": 1, "cause": None, "tokens": 1, "cleanup": variant}, "normal"]}
    rc = run(env, SMOKE, plan=plan)
    refused(env, rc, 1)
    assert log_has(env, "restart refused")


@pytest.mark.parametrize("variant", BAD)
def test_a_hook_rerun_requires_the_exact_cleanup_receipt(env, variant):
    target = slot(cell_items(env)[1])
    plan = {"oc": [{"cleanup": variant}, "normal"]}
    rc = run(env, SMOKE, plan=plan, hooks=Script(after=cheat_on(target, 1)))
    refused(env, rc, 1)
    assert log_has(env, "retry refused")


@pytest.mark.parametrize("variant", BAD)
def test_a_pre_spawn_retry_requires_the_exact_cleanup_receipt(env, variant):
    target = slot(cell_items(env)[1])
    plan = {"oc": [{"cleanup": variant}, "normal"]}
    rc = run(env, SMOKE, plan=plan, hooks=Script(before=pre_spawn_on(target, 1)))
    refused(env, rc, 1)
    assert log_has(env, "retry refused")


# ---------------------------------------------------------------- restart_load (tg1): the same validator, unit level
@pytest.mark.parametrize("variant", BAD)
def test_the_tg1_restart_eligibility_requires_the_exact_cleanup_receipt(variant):
    from bench import chain_ops as co
    from bench.tests import test_c147_chain_runner as t
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        ops = t.FakeOps(tmp)
        chain = t.R.Chain(t.R.parse_args(t.CHAIN + ["--probe", str(t.C147 / "fake_probe.py"), "--out-root", tmp + "/o"]),
                          ops, t.R.Timers(), lambda m: None, t.R.load_universe(), Path(tmp) / "o", {})
        ops.load(t.PICK1)
        block = {"worker": {"pid": ops.ident["pid"], "create_time": ops.ident["create_time"]}}
        receipt = FAP.cleanup_status(variant)
        with pytest.raises(co.ChainAbort, match="restart refused.*cleanup"):
            chain.check_restart_eligible(dict(cleanup_status=receipt, rc=1, outcome="exited"), {"model": t.PICK1}, block)
        chain.check_restart_eligible(dict(cleanup_status=FAP.cleanup_status(), rc=1, outcome="exited"), {"model": t.PICK1}, block)
