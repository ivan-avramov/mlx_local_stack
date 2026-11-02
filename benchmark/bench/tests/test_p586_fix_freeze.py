"""P586 fix round 1, X4 (red-first): the freeze's R3 check uses its own probe-kill tuple, never `p426_reconcile.KILL_CASES`."""
from __future__ import annotations

import json
from pathlib import Path

from bench import p426_freeze as fz
from bench.tests import test_b2_s8_freeze as TF
from bench.tests.test_b2_s8_freeze import world  # noqa: F401  (the fixture)

PROBE_KILLS = ("kill_boundary", "kill_inflight_failed", "kill_completed_unaccounted")


def _recase(leg, case):
    n = 0
    for p in sorted((Path(leg) / "items").glob("*.json")):
        if p.name.endswith((".ready.json", ".dnf.json")):
            continue
        doc = json.loads(p.read_text())
        if doc.get("case", "").startswith("kill"):
            doc["case"] = case
            p.write_text(json.dumps(doc))
            n += 1
    assert n, "fixture premise: the R3 tree has a kill item"


def test_x4_the_freeze_has_its_own_probe_kill_tuple():
    assert tuple(fz.KILL_CASES) == PROBE_KILLS


def test_x4_an_r3_tree_whose_only_kill_case_is_a_client_abort_is_refused(world, capsys):  # noqa: F811
    manifest = TF.make_manifest(world, capsys)
    legs = TF.make_rehearsal_legs(world)
    _recase(legs["r3"], "kill_client_aborted")
    rc, err = TF.run(TF.v8_argv(world, manifest, legs, world["rec"] / "v8_base.json"), world["ops"], capsys=capsys)
    assert rc == 2 and "R3" in err and "kill case" in err


def test_x4_a_probe_kill_case_is_accepted(world, capsys):  # noqa: F811
    manifest = TF.make_manifest(world, capsys)
    legs = TF.make_rehearsal_legs(world)
    _recase(legs["r3"], "kill_inflight_failed")
    rc, err = TF.run(TF.v8_argv(world, manifest, legs, world["rec"] / "v8_base.json"), world["ops"], capsys=capsys)
    assert rc == 0, err
