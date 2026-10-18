"""P371 review r4 F16 (lead call P384): the chain issues a random 64-hex nonce per invocation (persisted in the invocation record
BEFORE launch), passes `--invocation-nonce` to the probe, which writes `runtime.invocation_nonce` into its manifest; the barrier
and the final-manifest binding require equality, so a fresh-run-id manifest that matches every other field is still refused."""
from __future__ import annotations

import json
import re

import pytest

from bench.tests.m64_support import SMOKE, arg, chain_json, env, invocations, log_has, run      # noqa: F401  (fixture: env)
from bench.tests.test_p371_review_r3_f16 import build, hydrate

HEX = re.compile(r"^[0-9a-f]{64}$")


def test_the_nonce_is_persisted_before_launch_and_reaches_the_probe_and_its_manifest(env):
    assert run(env, SMOKE) == 0
    cj = chain_json(env)
    recs = cj["progress"]["invocations"]
    assert all(HEX.match(r["nonce"]) for r in recs) and len({r["nonce"] for r in recs}) == len(recs)
    for call, rec in zip(invocations(env), recs):
        assert arg(call["argv"], "--invocation-nonce") == rec["nonce"]
    man = json.loads((env["out"] / recs[0]["manifest"]).read_text())
    assert man["runtime"]["invocation_nonce"] == recs[0]["nonce"]


def test_a_fresh_run_id_manifest_with_every_other_field_matching_but_no_or_a_wrong_nonce_is_refused(tmp_path):
    for nonce in (None, "short", "f" * 64):
        chain, out, view, worker, good = build(tmp_path / (nonce or "none")[:5])
        good["runtime"]["invocation_nonce"] = nonce
        if nonce is None:
            del good["runtime"]["invocation_nonce"]
        att = hydrate(chain, out, view, worker, good, nonce="a" * 64)
        assert att["manifest_problem"].startswith("binding differs") and "invocation_nonce" in att["manifest_problem"], nonce
        assert att["cleanup_status"] is None


def test_the_matching_nonce_hydrates(tmp_path):
    chain, out, view, worker, good = build(tmp_path)
    good["runtime"]["invocation_nonce"] = "a" * 64
    att = hydrate(chain, out, view, worker, good, nonce="a" * 64)
    assert att["manifest_problem"] is None and att["cleanup_status"] == {"completed": True}


@pytest.mark.parametrize("bad", ["short", "A" * 64, "g" * 64, "a" * 63])
def test_a_probe_refuses_a_malformed_nonce(bad):
    import run_oc_probe
    ap = run_oc_probe._parser()
    with pytest.raises(SystemExit):
        ap.parse_args(["--model", "m", "--items", "a", "--seed-base", "1", "--invocation-nonce", bad])
    ok = ap.parse_args(["--model", "m", "--items", "a", "--seed-base", "1", "--invocation-nonce", "a" * 64])
    assert ok.invocation_nonce == "a" * 64


def test_the_tg1_probe_parser_refuses_a_malformed_nonce_too():
    import run_tg1_probe
    ap = run_tg1_probe._parser() if hasattr(run_tg1_probe, "_parser") else None
    if ap is None:
        pytest.skip("no _parser")
    with pytest.raises(SystemExit):
        ap.parse_args(["--model", "m", "--items", "a", "--seed-base", "1", "--invocation-nonce", "zz"])
    assert ap.parse_args(["--model", "m", "--items", "a", "--seed-base", "1", "--invocation-nonce", "b" * 64]
                         ).invocation_nonce == "b" * 64


def test_a_resume_keeps_the_binding(env):
    from bench.tests.test_p371_m64_resume import LEG3_SLOT2, CrashAt, crash_run
    crash_run(env, CrashAt(LEG3_SLOT2))
    first = {r["file"]: r["nonce"] for r in chain_json(env)["progress"]["invocations"]}
    assert run(env, SMOKE) == 0
    after = chain_json(env)["progress"]["invocations"]
    assert all(r["nonce"] == first[r["file"]] for r in after if r["file"] in first)
    assert len({r["nonce"] for r in after}) == len(after)


def test_the_a14_argv_rule_drops_exactly_a_64_hex_nonce_pair_and_a_planted_mismatch_stays_visible():
    from bench.tests.p371_baseline import compare as cmp_mod
    argv = ["py", "probe", "--model", "m", "--invocation-nonce", "a" * 64, "--limit", "5"]
    assert cmp_mod.legacy_argv(argv) == ["py", "probe", "--model", "m", "--limit", "5"]
    bad = ["py", "probe", "--invocation-nonce", "nothex", "--limit", "5"]
    assert cmp_mod.legacy_argv(bad) == bad                                      # not a nonce pair: left, so it differs
    assert "/runtime/invocation_nonce" in cmp_mod.TABLE["manifest_additions"]
    old = {"kind": "chain", "invocations": [["py", "--limit", "5"]]}
    new = {"kind": "chain", "invocations": [["py", "--invocation-nonce", "a" * 64, "--limit", "9"]]}
    res = cmp_mod.compare(old, new, cmp_mod.TABLE)
    assert not res.ok and any("/invocations/0" in f for f in res.failures)
