"""P426 B2 frozen tests, delivery 1d: the per-item realized ledger (spec v3.2 §7, §16.5 `chain.json` `p426_ledger` /
`p426_dnf` / `p426_invalid`).

Classes: [FIX] reproduces a failure the spec fixes; [INV] preserves an invariant; [NEW] exercises new behaviour (all NEW here).
Hermetic `--p426` pilot legs (`b2_frozen_add_support.world`); entries are `{slot, kind: "row"|"dnf", invocation, index}`."""
from __future__ import annotations

import json
from pathlib import Path

from bench.tests import b2_frozen_add_support as A
from bench.tests import b2_frozen_support as S

PILOT = S.p426_order([f"p{i}" for i in range(1, 7)], 1001)[:5]


def run(tmp_path, monkeypatch, probe_env=None):
    env = A.world(tmp_path, monkeypatch)
    env["ops"].extra_env.update(probe_env or {})
    argv, r = S.p426_argv(env, ("pilot",))
    try:
        rc = S.run_p426(env, argv, rfd=r)
    finally:
        env["ops"].cancel()
    cj = Path(env["out"]) / "chain.json"
    return rc, (json.loads(cj.read_text()) if cj.exists() else {}), env


def items_of(ledger):
    return [e["slot"].rsplit("|", 1)[-1] for e in ledger]


def consecutive(xs):
    return xs == list(range(xs[0], xs[0] + len(xs))) if xs else True


def test_new_a_valid_leg_ledgers_every_planned_slot_in_order_as_a_row(tmp_path, monkeypatch):
    rc, cj, env = run(tmp_path, monkeypatch)
    assert rc == 0
    led = cj["p426_ledger"]
    assert items_of(led) == PILOT and [e["kind"] for e in led] == ["row"] * 5
    assert len({e["invocation"] for e in led}) == 1 and consecutive([e["index"] for e in led])
    assert cj.get("p426_dnf", []) == [] and cj.get("p426_invalid", []) == []


def test_new_a_dnf_is_ledgered_in_its_place_and_the_rest_in_the_next_invocation(tmp_path, monkeypatch):
    rc, cj, env = run(tmp_path, monkeypatch, {"B2_ABORTS": json.dumps({PILOT[1]: "boundary"})})
    assert rc == 0
    led = cj["p426_ledger"]
    assert items_of(led) == PILOT and [e["kind"] for e in led] == ["row", "dnf", "row", "row", "row"]
    inv = [e["invocation"] for e in led]
    assert inv[0] == inv[1] and inv[2] == inv[3] == inv[4] and inv[2] != inv[1]
    assert consecutive([e["index"] for e in led])
    assert [d["slot"] for d in cj["p426_dnf"]] == [led[1]["slot"]]


def test_new_an_invalidated_item_is_recorded_and_ends_the_ledger(tmp_path, monkeypatch):
    rc, cj, env = run(tmp_path, monkeypatch, {"B2_SKEW_ITEMS": PILOT[2]})
    assert rc == 2
    invalid = cj.get("p426_invalid")
    assert invalid and any(PILOT[2] in json.dumps(x) for x in invalid)
    assert items_of(cj.get("p426_ledger", []))[:2] == PILOT[:2] and PILOT[3] not in items_of(cj["p426_ledger"])
