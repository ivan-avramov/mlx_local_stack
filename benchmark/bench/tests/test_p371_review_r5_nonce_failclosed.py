"""P371 nonce check FAILS CLOSED (lead correction to P384): the barrier and the final-manifest binding require a well-formed nonce
on the invocation record AND an equal one in the manifest; a record without one is refused with an explicit reason."""
from __future__ import annotations

import pytest

from bench import chain_core
from bench.tests.m64_support import SMOKE, chain_json, env, log_has, run      # noqa: F401  (fixture: env)
from bench.tests.test_p371_review_r3_f16 import build, hydrate


@pytest.mark.parametrize("record_nonce", [None, "", "short", "A" * 64])
def test_a_record_without_a_well_formed_nonce_refuses_an_otherwise_matching_manifest(tmp_path, record_nonce):
    chain, out, view, worker, good = build(tmp_path)
    good["runtime"]["invocation_nonce"] = record_nonce or "a" * 64
    att = hydrate(chain, out, view, worker, good, nonce=record_nonce)
    assert att["manifest_problem"] == "invocation record has no nonce" and att["cleanup_status"] is None


def test_a_missing_record_is_refused_too(tmp_path):
    chain, out, view, worker, good = build(tmp_path)
    good["runtime"]["invocation_nonce"] = "a" * 64
    out.with_suffix(".manifest.json").write_text(__import__("json").dumps(good))
    att = dict(attempt=1, run_id=None, worker=worker, transport_abort=None, cancelled_item=None, cleanup_status=None)
    chain.hydrate_from_manifest(att, view, out, None)
    assert att["manifest_problem"] == "invocation record has no nonce"


def test_the_barrier_refuses_a_nonce_less_invocation(env, monkeypatch):
    monkeypatch.setattr(chain_core.secrets, "token_hex", lambda n: "")
    assert run(env, SMOKE) == 2
    assert log_has(env, "invocation record has no nonce")
