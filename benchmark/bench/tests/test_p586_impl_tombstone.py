"""P588 (implementer's red-first tests): an invalidated slot ends as a clean INVALID; its web evidence is a tombstone."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import chain_core as cc
from bench import chain_ops as co
from bench.tests import test_b2_s8c_chain as W

SLOT = "0|A|m|s1|python|a"


PINS = Path(__file__).resolve().parents[3] / "src/mlx-vlm/dev/p369_phase2/pins.json"


# -- the done barrier, directly: an `invalidate` leaves the tombstone
def test_the_done_barrier_invalidates_with_the_barriers_extraction_as_the_tombstone(tmp_path):
    from bench import chain_hooks as ch
    web = dict(path="$STACK_WORKDIR/x.web.jsonl", sha256="a" * 64, count=3)
    chain = chain_with(tmp_path, invalid=[])
    chain.config, chain.per_arm = SimpleNamespace(transport_policy="p426_continue"), False
    chain.out_root = tmp_path
    chain.web_rules = lambda *_a, **_k: {}
    chain.web_record = lambda *_a, **_k: dict(web)
    chain.hooks = SimpleNamespace(run_after=lambda slot, done, context=None: ch.Disposition.invalidate("boom"))
    chain.p426_hook_context = lambda *a, **k: {}
    base = tmp_path / "rows"
    (tmp_path / "rows.jsonl").write_text(json.dumps(dict(id="python/a")) + "\n")
    Path(f"{base}.item0.done").write_text(json.dumps(dict(id="python/a")))
    bar = dict(k=0, stage="done", stop=None, rec={}, inv={}, base=str(base), names=["a"], rindex=0,
               view=dict(slot_base="0|A|m|s1|python", lang="python", arm="A", out=str(tmp_path / "rows.jsonl")),
               load=dict(idx=0, rec=dict(load_gen=0)))
    chain.pump_barrier(bar)
    (entry,) = chain.p426_invalid
    assert entry["stage"] == "done" and entry["slot"] == SLOT and entry["reason"] == "boom"
    assert entry["web_evidence"] == dict(slot=SLOT, rerun_index=0, path=web["path"], sha256=web["sha256"])
    assert bar["stage"] == "stopped" and chain.progress["slot_attempts"] == []


def test_the_done_barrier_tombstone_is_none_when_it_extracted_nothing(tmp_path):
    from bench import chain_hooks as ch
    chain = chain_with(tmp_path, invalid=[])
    chain.config, chain.per_arm, chain.out_root = SimpleNamespace(transport_policy="p426_continue"), False, tmp_path
    chain.web_rules = lambda *_a, **_k: {}
    chain.web_record = lambda *_a, **_k: dict(web_evidence="unavailable", reason="no transcript")
    chain.hooks = SimpleNamespace(run_after=lambda slot, done, context=None: ch.Disposition.invalidate("boom"))
    chain.p426_hook_context = lambda *a, **k: {}
    base = tmp_path / "rows"
    (tmp_path / "rows.jsonl").write_text(json.dumps(dict(id="python/a")) + "\n")
    Path(f"{base}.item0.done").write_text(json.dumps(dict(id="python/a")))
    bar = dict(k=0, stage="done", stop=None, rec={}, inv={}, base=str(base), names=["a"], rindex=0,
               view=dict(slot_base="0|A|m|s1|python", lang="python", arm="A", out=str(tmp_path / "rows.jsonl")),
               load=dict(idx=0, rec=dict(load_gen=0)))
    chain.pump_barrier(bar)
    assert chain.p426_invalid[0]["web_evidence"] is None
    skip, tomb = chain.p426_tombstone(SLOT, 0)
    assert skip and tomb is None


# -- the chain end to end (hermetic world, fake probe): the injected R2 invalidation at a `done` barrier
@pytest.mark.skipif(not PINS.exists(), reason="the world fixtures need the src/mlx-vlm submodule checkout")
def test_an_invalidated_slot_ends_as_a_clean_invalid_with_its_tombstone(tmp_path, monkeypatch):
    rc, env = W.world_leg(tmp_path, monkeypatch, ("chain", "s1", "--rehearsal"), extra=("--inject", "reconcile-mismatch"), rehearsal=True)
    text = W.log_text(env)
    assert rc == 2, text
    doc = W.chain_doc(env)
    (inv,) = doc["p426_invalid"]
    assert inv["stage"] == "done" and inv["reason"] == "reconciliation mismatch (injected)"
    tomb = inv["web_evidence"]
    assert set(tomb) == {"slot", "rerun_index", "path", "sha256"} and tomb["slot"] == inv["slot"] and tomb["rerun_index"] == 0
    assert hashlib.sha256(co.resolve_portable(tomb["path"], env["ops"].wd).read_bytes()).hexdigest() == tomb["sha256"]
    assert [a for a in doc["progress"]["slot_attempts"] if a["slot"] == inv["slot"]] == []
    assert not any("web evidence" in ln for ln in env["lines"]), text
    assert any("leg INVALID at" in ln for ln in env["lines"]), text


# -- the two chain methods, directly
def chain_with(tmp_path, *, invalid, attempts=()):
    chain = object.__new__(cc.Chain)
    chain.wd = tmp_path
    chain.progress = dict(slot_attempts=list(attempts))
    chain.p426_invalid = list(invalid)
    chain.log = lambda *_a, **_k: None
    chain.write_json = lambda *_a, **_k: None
    chain.web_rules = lambda *_a, **_k: dict(never="used")
    chain.web_record = lambda *a, **k: (_ for _ in ()).throw(AssertionError("web_record must not run for a tombstoned slot"))
    return chain


def tombstone(tmp_path, body=b"{}\n", rindex=0):
    f = tmp_path / "x.web.jsonl"
    f.write_bytes(body)
    return dict(slot=SLOT, rerun_index=rindex, path="$STACK_WORKDIR/x.web.jsonl", sha256=hashlib.sha256(body).hexdigest())


def invalid_entry(tomb):
    return dict(stage="done", slot=SLOT, reason="r", at="t", web_evidence=tomb)


def rec_and_rows(tmp_path):
    rec = dict(slot_base="0|A|m|s1|python", file="rows.jsonl", load_gen=0, rerun_index=0)
    row = dict(id="python/a", transcript_path="$STACK_WORKDIR/x.json", evidence_sha256=dict(export="0" * 64))
    return rec, [row]


def test_after_invocation_skips_a_tombstoned_slot_without_a_slot_attempt(tmp_path):
    chain = chain_with(tmp_path, invalid=[invalid_entry(tombstone(tmp_path))])
    rec, rows = rec_and_rows(tmp_path)
    chain.after_invocation(dict(idx=0), {}, {}, rec, rows)
    assert chain.progress["slot_attempts"] == []


def test_after_invocation_aborts_when_the_tombstoned_file_changed_or_is_gone(tmp_path):
    tomb = tombstone(tmp_path)
    (tmp_path / "x.web.jsonl").write_bytes(b"changed\n")
    rec, rows = rec_and_rows(tmp_path)
    with pytest.raises(co.ChainAbort):
        chain_with(tmp_path, invalid=[invalid_entry(tomb)]).after_invocation(dict(idx=0), {}, {}, rec, rows)
    (tmp_path / "x.web.jsonl").unlink()
    with pytest.raises(co.ChainAbort):
        chain_with(tmp_path, invalid=[invalid_entry(tomb)]).after_invocation(dict(idx=0), {}, {}, rec, rows)


def test_abandoned_web_evidence_skips_a_tombstoned_slot_and_checks_its_sha(tmp_path, monkeypatch):
    rec, rows = rec_and_rows(tmp_path)
    out = tmp_path / "rows.jsonl"
    out.write_text(json.dumps(dict(rows[0])) + "\n")
    monkeypatch.setattr(cc.cr, "rows_if_present", lambda _p: rows)
    chain = chain_with(tmp_path, invalid=[invalid_entry(tombstone(tmp_path))])
    chain.abandoned_web_evidence(rec, out)
    assert "web_evidence" not in rec
    (tmp_path / "x.web.jsonl").write_bytes(b"changed\n")
    with pytest.raises(co.ChainAbort):
        chain.abandoned_web_evidence(rec, out)


def test_a_slot_with_no_tombstone_is_extracted_as_before(tmp_path):
    chain = chain_with(tmp_path, invalid=[])
    chain.web_record = lambda *a, **k: dict(path="p", sha256="s", count=0)
    rec, rows = rec_and_rows(tmp_path)
    chain.after_invocation(dict(idx=0), {}, {}, rec, rows)
    assert [a["slot"] for a in chain.progress["slot_attempts"]] == [SLOT]


def test_a_tombstone_of_another_rerun_index_does_not_skip(tmp_path):
    chain = chain_with(tmp_path, invalid=[invalid_entry(tombstone(tmp_path, rindex=1))])
    chain.web_record = lambda *a, **k: dict(path="p", sha256="s", count=0)
    rec, rows = rec_and_rows(tmp_path)
    chain.after_invocation(dict(idx=0), {}, {}, rec, rows)
    assert len(chain.progress["slot_attempts"]) == 1
    _ = SimpleNamespace, Path
