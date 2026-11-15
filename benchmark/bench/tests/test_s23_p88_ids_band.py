"""S23-P88 (C334 light path; fail-closed): `m76_ids.load()` re-checks the A5 prompt band on the committed record, not only at
generation — a record rebuilt consistently from out-of-band counts is refused. Class (a): reproduces the gap."""
from __future__ import annotations

import json

import pytest

from bench import m76_ids as M
from bench.tests import test_m76_b3_fe_fix_v15 as V
from bench.tests import test_m76_b3_fe_surface as G


def _text(counts):
    universe, _ = V.synthetic()
    source = dict(source=M.PLAN_SOURCE, report_sha256="a" * 64)
    doc = M.build(G.REPO, a5_sizes=V.SIZES, universe=universe, max_tokens=81920, thinking_budget=4096, a5_source=source,
                  prompt_tokens=counts)
    return json.dumps(doc, indent=1, sort_keys=True)


def test_in_band_record_loads(two_looks):
    _, counts = V.synthetic()
    text = _text(counts)
    assert M.load(G.REPO, text, plan=V.PLAN2) == json.loads(text)


@pytest.mark.parametrize("which", ["items", "smoke"])
@pytest.mark.parametrize("pos", [0, -1])
@pytest.mark.parametrize("delta", [+1, -0.0301])         # just above the rung; just below −3 % (band −3 % … 0 %)
def test_out_of_band_record_is_refused(two_looks, which, pos, delta):
    _, counts = V.synthetic()
    item = M.longctx_draw(V.SIZES)[which][pos]
    counts[item["id"]] = item["rung"] + (delta if isinstance(delta, int) else int(delta * item["rung"]) - 1)
    with pytest.raises(ValueError, match="band"):
        M.load(G.REPO, _text(counts), plan=V.PLAN2)


@pytest.mark.parametrize("which", ["items", "smoke"])
def test_band_edges_load(two_looks, which):
    _, counts = V.synthetic()
    d = M.longctx_draw(V.SIZES)
    first, last = d[which][0], d[which][-1]
    counts[first["id"]] = first["rung"]                                   # exactly the rung (0 %)
    counts[last["id"]] = last["rung"] - int(0.03 * last["rung"])          # within −3 %
    M.load(G.REPO, _text(counts), plan=V.PLAN2)


def test_out_of_band_does_not_mask_a_plan_refusal(two_looks):
    _, counts = V.synthetic()
    item = M.longctx_draw(V.SIZES)["items"][0]
    counts[item["id"]] = item["rung"] + 1
    with pytest.raises(ValueError, match="plan"):
        M.load(G.REPO, _text(counts), plan=dict(V.PLAN2, report_sha256="b" * 64))


def test_the_committed_record_loads_under_its_current_plan():
    doc = M.load(G.REPO)
    assert doc["axes"]["longctx"]["budget_inputs"]["prompt_tokens"]


two_looks = V.two_looks
