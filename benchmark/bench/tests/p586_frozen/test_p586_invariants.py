"""Criterion 3 (the part this directory can hold): rows WITHOUT `client_inactivity` reconcile exactly as on the baseline.

`test_p586_golden_data.GOLDEN` holds the baseline's (a09a5a7e) `dataclasses.asdict(ItemReport)` of each case in
`kit.invariant_cases()` (completed, token mismatch, a stray failed line, budget kill at a boundary and with a count mismatch,
probe kill with a request in flight, without in-flight evidence, completed-unaccounted, a worker-delta mismatch), all in the
real worker-log format of the leg-3 window. One key is tolerated as new: `totals.decode_rate_source` (P593 puts it on every
item RECORD; if the build puts it in `ItemReport.totals` the report is otherwise unchanged — the spec's "byte-identical
reports" and P593's "every item record gains" overlap on that one key).

The existing B2 / T3 / M64 / M62 / guard suites are the rest of criterion 3; they are not run in this delivery.

Delivery 2c (designer's ruling): comparing the WHOLE dataclass constrained structure, not behaviour. The invariant is: every field
the baseline's `ItemReport` has is identical, and the new optional `client_abort` (if the build adds it) is None; at the hook, the
item record of these rows is the baseline's apart from the spec's new `totals.decode_rate_source`. The goldens are unchanged.

Classes: [I] preserves an invariant, [N] exercises new behaviour."""
from __future__ import annotations

import copy
import dataclasses

import pytest

from bench import p426_reconcile as pr

NEW_TOTALS_KEYS = {"decode_rate_source"}
# the keys of the baseline's (a09a5a7e) sealed item record (`P426Hooks._item_record` + `seal`)
BASELINE_RECORD_KEYS = {"slot", "ready_sha256", "log_range", "worker_before", "worker_after", "case", "requests", "totals", "checks",
                        "verdict", "problems", "sha256"}
HOOK_EXTRA_CHECKS = {"engagement", "settle"}      # the hook's own checks beside the report's (baseline behaviour)


def _norm(d):
    d = dict(d)
    d["totals"] = {k: v for k, v in (d.get("totals") or {}).items() if k not in NEW_TOTALS_KEYS}
    return d


def _same_as_golden(report, golden):
    """Every pre-existing field identical (`totals` without the P593 key); the new optional `client_abort` None."""
    got = _norm(dataclasses.asdict(report))
    want = _norm(golden)
    assert {k: got.get(k) for k in want} == want
    assert getattr(report, "client_abort", None) is None


CASES = ["completed", "completed_token_mismatch", "completed_with_a_failed_line", "budget_kill_boundary",
         "budget_kill_boundary_count_mismatch", "probe_kill_inflight_failed", "probe_kill_failed_without_inflight_evidence",
         "probe_kill_completed_unaccounted", "probe_kill_worker_delta_mismatch"]


@pytest.mark.parametrize("name", CASES)
def test_non_client_inactivity_rows_reconcile_exactly_as_on_the_baseline(kit, name):
    """[I] the same report fields (case, ok, problems, checks, requests, totals) as the baseline, called as the baseline calls it;
    a new `client_abort` field, if any, is None."""
    r, lines, b, a = kit.invariant_cases()[name]
    _same_as_golden(pr.reconcile_item(r, lines, b, a), kit.golden()[name])


@pytest.mark.parametrize("name", CASES)
def test_an_explicit_client_none_changes_nothing(kit, name):
    """[N] the new keyword with its default (`client=None`, what the hook passes for a non-`client_inactivity` row) gives the
    baseline report fields too."""
    r, lines, b, a = kit.invariant_cases()[name]
    _same_as_golden(pr.reconcile_item(r, lines, b, a, client=None), kit.golden()[name])


def _window_of(kit, name):
    """The window bytes each invariant case was parsed from (see `conftest.invariant_cases`)."""
    if name in ("completed", "completed_token_mismatch", "budget_kill_boundary", "budget_kill_boundary_count_mismatch"):
        return kit._w12()
    if name == "probe_kill_completed_unaccounted":
        return kit.completed_variant_window()
    return kit.window_bytes()


@pytest.mark.parametrize("name", CASES)
def test_the_hooks_item_record_of_these_rows_is_the_baselines_apart_from_decode_rate_source(tmp_path, kit, name):
    """[I] delivery 2c: the same rows through `P426Hooks.after_attempt` (OFF arm): the record has exactly the baseline's keys
    (no `client_abort`), its case / requests / report checks / problems / verdict follow the golden report, its totals are the
    golden totals plus at most the spec's `decode_rate_source`, and the disposition is the one the baseline gives."""
    r, _lines, b, a = kit.invariant_cases()[name]
    g = kit.golden()[name]
    ops, hooks, out = kit.make_hooks(tmp_path)
    ops.summary = copy.deepcopy(b)
    assert hooks.before_attempt(kit.SLOT, kit.ctx()).kind == "accept"
    ops.append(_window_of(kit, name))
    ops.summary = copy.deepcopy(a)
    disp = hooks.after_attempt(kit.SLOT, dict(id=r["id"]), kit.ctx(r))
    rec = kit.item_record(out)
    assert set(rec) == BASELINE_RECORD_KEYS, sorted(set(rec) ^ BASELINE_RECORD_KEYS)
    assert rec["case"] == g["case"] and rec["requests"] == g["requests"]
    assert {k: rec["checks"][k] for k in g["checks"]} == g["checks"]
    assert set(rec["checks"]) - set(g["checks"]) <= HOOK_EXTRA_CHECKS
    assert all(rec["checks"][k]["ok"] for k in HOOK_EXTRA_CHECKS & set(rec["checks"]))
    assert set(rec["totals"]) - set(g["totals"]) <= NEW_TOTALS_KEYS
    assert {k: rec["totals"][k] for k in g["totals"]} == g["totals"]
    assert rec["problems"] == g["problems"]
    assert rec["verdict"] == ("reconciled" if g["ok"] else "invalid")
    assert disp.kind == ("accept" if g["ok"] else "invalidate")


def test_non_client_inactivity_reports_carry_no_client_abort_checks(kit):
    """[I] no `client_abort_*` check appears outside `client_inactivity` rows."""
    for name, (r, lines, b, a) in kit.invariant_cases().items():
        rep = pr.reconcile_item(r, lines, b, a)
        assert not [k for k in rep.checks if k.startswith("client_abort_")], name


def test_the_goldens_cover_every_case_and_the_kill_cases(kit):
    """[I] sanity of the golden data itself: every case present, both accepted and refused shapes, all three old kill cases."""
    g = kit.golden()
    assert sorted(g) == sorted(CASES)
    assert {g[n]["case"] for n in CASES} >= {"completed", "kill_boundary", "kill_inflight_failed", "kill_completed_unaccounted"}
    assert any(g[n]["ok"] for n in CASES) and not all(g[n]["ok"] for n in CASES)
