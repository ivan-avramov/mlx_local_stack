"""P371 review r2 F15 (lead call P382): the abort stamp's `evidence` is emitted for EVERY configuration (tg1 included), independent
of gate-token reporting; `cancelled_item` carries it too; the A14 table names exactly `/transport_abort/evidence` and
`/cancelled_item/evidence`; the chain records the failing slot's evidence or an explicit `unavailable` for tg1 as well."""
from __future__ import annotations

from bench.tests import test_c147_chain_runner as t
from bench.tests.test_c147_chain_runner import CHAIN, chain_json, env, run      # noqa: F401  (fixture: env)
from bench.tests.test_p371_chain_core import PLAN_RESTART
from bench.tests.p371_baseline import compare as cmp_mod
from bench.tests.p371_world import manifest, world      # noqa: F401  (fixture)


def test_the_neutral_non_reporting_adapter_stamps_the_evidence_too(world):
    from bench.tests.test_p371_a3_core import SEED, abort_of, source
    msg, stamp = abort_of(world, source(world, [dict(cls="task", seed=SEED)]))
    assert stamp["evidence"]["id"] == "fake/one" and "gate" not in stamp and "cause" not in stamp   # gate / cause stay M64-only


def test_the_a14_table_names_exactly_the_two_p382_manifest_additions():
    extra = [p for p in cmp_mod.TABLE["manifest_additions"] if "evidence" in p and "policy" not in p and "evidence_policy" not in p]
    assert sorted(extra) == ["/cancelled_item/evidence", "/transport_abort/evidence"]
    assert cmp_mod.TABLE["manifest_addition_prefixes"] == []


def test_a_tg1_pre_row_transport_abort_records_evidence_or_unavailable(env):
    assert run(env, ["chain", "reload", "--probe-code-sha", "9" * 64], plan=["abort_after_n", "normal"],
               extra_env={"FAKE_N": "2"}) == 0
    recs = chain_json(env)["progress"]["abort_evidence"]
    assert recs and all(r["web_evidence"].get("web_evidence") == "unavailable" or "sha256" in r["web_evidence"] for r in recs)
    assert all("|" in r["slot"] for r in recs)


def test_a_tg1_cancel_records_evidence_or_unavailable(env):
    assert run(env, CHAIN, plan=PLAN_RESTART) == 0
    cj = chain_json(env)
    cancelled = [a for a in cj["attempts"] if a.get("cancelled_item")]
    assert cancelled
    recs = cj["progress"]["abort_evidence"]
    assert len(recs) >= len(cancelled) and all("web_evidence" in r or r.get("covered") for r in recs)
