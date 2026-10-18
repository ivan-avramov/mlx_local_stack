"""P371 review r3 F18 / F19.
F18: a cancel that lands before the probe wrote any manifest leaves an explicit `unavailable` abort-evidence record for the
invocation's head slot (reason `no manifest (pre-manifest exit)`). F19: a cancel BETWEEN items stamps an explicit boundary
(`evidence: {boundary: true, after: <last committed id>}`), never the previous committed item, and the chain attributes no slot."""
from __future__ import annotations

from pathlib import Path

from bench.tests.m64_support import SMOKE, chain_json, env, run      # noqa: F401  (fixture: env)
from bench.tests.p371_world import manifest, world      # noqa: F401  (fixture)


def test_a_cancel_before_any_manifest_records_unavailable_for_the_head_slot(env):
    ops, real = env["ops"], env["ops"].create_time

    def create_time(pid):
        (env["out"] / "STOP").write_text("stop\n")           # the probe is refused / cancelled before it writes a manifest
        return real(pid)
    ops.create_time = create_time
    assert run(env, SMOKE, timers={"t_coop_scale": 0.05}) == 3
    cj = chain_json(env)
    rec = cj["progress"]["invocations"][0]
    (found,) = cj["progress"]["abort_evidence"]
    assert Path(found["invocation"]).name == Path(rec["file"]).name and found["slot"] == rec["expected_slots"][0]
    assert found["web_evidence"] == dict(web_evidence="unavailable", reason="no manifest (pre-manifest exit)")
    assert rec["manifest_problem"] == "missing"


def test_a_cancel_between_items_stamps_a_boundary_not_the_previous_item(world, tmp_path):
    from bench.tests.arm_neutral import NeutralArm
    cancel = tmp_path / "cancel"

    class Boundary(NeutralArm):
        def row_fields(self, *a, **k):
            cancel.write_text("stop\n")                      # lands after item one's row, before item two starts
            return super().row_fields(*a, **k)

    import pytest
    from bench.tests.p371_world import run_core, rows
    with pytest.raises(SystemExit):
        run_core(world, adapter=Boundary(world.host), a=dict(items="one,two", cancel_file=str(cancel)))
    stamp = manifest(world)["transport_abort"]
    assert [r["id"] for r in rows(world)] == ["fake/one"]
    assert stamp["evidence"] == dict(boundary=True, after="fake/one")
    assert "cancelled_item" not in manifest(world) or manifest(world)["cancelled_item"].get("evidence") in (None, stamp["evidence"])


def test_the_chain_attributes_no_slot_to_a_boundary_cancel(tmp_path):
    from bench.tests.m64_support import FakeOps, M
    a = M.parse_args(SMOKE + ["--out-root", str(tmp_path / "o")])
    chain = M.build_chain(a, FakeOps(tmp_path), M.Timers(), lambda m: None, {"python": ["a"], "go": ["b"]}, tmp_path / "o", {})
    out = tmp_path / "rows.a1.jsonl"
    out.write_text("")
    att = dict(attempt=1, transport_abort=dict(error="cancelled by runner", evidence=dict(boundary=True, after="python/a")),
               cancelled_item=None)
    found = chain.abort_evidence(att, dict(slot_base="e|oc|m|s1|python", arm="oc"), out)
    assert found["slot"] is None and found["boundary"] is True and found["after"] == "python/a" and "covered" not in found
