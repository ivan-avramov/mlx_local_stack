"""P588 (criterion 5): the leg-3 shape through the chain with fake ops. A Go invocation of two items: `beer-song` accepted at
its barrier, `crypto-square` invalidated at its `done` barrier AFTER the barrier extracted its web evidence (the real export,
the real OPENCODE rules). The hook-stopped invocation is then accepted for its prefix (`accept_invocation` ->
`after_invocation`) and, separately, run through `abandoned_web_evidence`.

Expected: the `p426_invalid` entry is a tombstone `web_evidence = {slot, rerun_index, path, sha256}` of the barrier's own
extraction; both re-extraction paths skip the tombstoned slot after checking the file's sha256; the leg ends `LegInvalid`
(rc 2) — never another `ChainAbort` — with no `slot_attempts` entry for the slot; a changed or missing file -> `ChainAbort`.

Classes: [R] reproduces the failure the spec fixes, [I] preserves an invariant, [N] exercises new behaviour."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bench import chain_core as core
from bench import chain_hooks as ch
from bench import chain_ops as co
from bench import web_evidence as we

MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
BASE = f"tg1-p426|oc|{MODEL}|s1|go"
SLOT_A, SLOT_B = f"{BASE}|beer-song", f"{BASE}|crypto-square"
RUN = "20261101T011412-208bb8c553d2"
EVDIR = f"opencode_transcripts/{MODEL}/{MODEL}.s1.opencode_go.L1.full.a1.{RUN}"
REASON = "client_abort_provenance: (the done check failed)"


class GoLeg(ch.ChainHooks):
    """Accepts every `ready` and the first `done`; invalidates `crypto-square` at `done` (what B2 did to leg 3)."""

    def before_attempt(self, slot, context=None):
        return ch.Disposition.accept()

    def after_attempt(self, slot, done, context=None):
        return ch.Disposition.invalidate(REASON) if slot == SLOT_B else ch.Disposition.accept()


def _world(tmp_path, kit, monkeypatch):
    wd = Path(tmp_path) / "wd"
    ev = wd / EVDIR
    small = json.dumps({"info": {"id": "ses_a"}, "messages": []}).encode()
    kit.put(ev / "go__beer-song.json", small)
    kit.put(ev / "go__crypto-square.json", kit.export_bytes())
    rows = []
    for name, body in (("beer-song", small), ("crypto-square", kit.export_bytes())):
        r = kit.row() if name == "crypto-square" else dict(id="go/beer-song", gate=dict(output_tokens_completed=10))
        r["id"] = f"go/{name}"
        r["transcript_path"] = f"$STACK_WORKDIR/{EVDIR}/go__{name}.json"
        r.setdefault("evidence_sha256", {})["export"] = hashlib.sha256(body).hexdigest()
        rows.append(r)
    c = kit.bare_chain(tmp_path / "leg")
    c.wd = wd
    c.web_rules = lambda arm: we.OPENCODE_RULES
    c.hooks = GoLeg()
    c.require_certain_cleanup = lambda *a, **k: None
    monkeypatch.setattr(core.cr, "read_rows", lambda p: list(rows))
    monkeypatch.setattr(core.cr, "rows_if_present", lambda p: list(rows))
    out = Path(tmp_path) / "leg" / "s1" / "rows.jsonl"
    rec = dict(file="s1/rows.jsonl", load_gen=0, manifest="s1/rows.manifest.json", slot_base=BASE, status="running",
               accepted_slots=[], expected_slots=[SLOT_A, SLOT_B], rerun_index=0)
    view = dict(slot_base=BASE, lang="go", arm="oc", model=MODEL, session="s1", out=str(out), seed_base=1001, stem="x")
    load = dict(idx=0, rec=dict(load_gen=0), worker=dict(kit.WORKER))
    inv = dict(phase="full", names=["beer-song", "crypto-square"], expect=["go/beer-song", "go/crypto-square"])
    c.progress["invocations"].append(rec)
    bar = c.new_barrier(rec, inv, Path(tmp_path) / "leg" / "s1" / "rows", view, load)
    return c, bar, dict(wd=wd, ev=ev, rec=rec, view=view, load=load, inv=inv, out=out, rows=rows)


def _drive(c, bar, tmp_path):
    """Both items through the item barrier: ready -> go, done -> (web evidence) -> accept / invalidate."""
    base = Path(tmp_path) / "leg" / "s1" / "rows"
    base.parent.mkdir(parents=True, exist_ok=True)
    for k, name in enumerate(("beer-song", "crypto-square")):
        Path(f"{base}.item{k}.ready").write_text("{}")
        c.pump_barrier(bar)
        assert Path(f"{base}.item{k}.go").exists()
        Path(f"{base}.item{k}.done").write_text(json.dumps({"id": f"go/{name}"}))
        c.pump_barrier(bar)
    assert bar["stage"] == "stopped" and bar["stop"]["disposition"] == "invalidate"


HOOK = dict(kind="after", k=1, name="crypto-square", slot=SLOT_B, disposition="invalidate", reason=REASON)


def _accept(c, w):
    return c.accept_invocation(w["load"], w["view"], w["inv"], w["rec"], w["out"], dict(HOOK), att=dict(cleanup_status=kit_cleanup()),
                               view=w["view"])


def kit_cleanup():
    return dict(survivors=[], containers_remaining=[], uncertain=False, orphans_unattributed=[], unknown=[], completed=True)


def test_the_invalid_entry_is_a_tombstone_of_the_barriers_extraction(tmp_path, kit, monkeypatch):
    """[N] `p426_invalid[-1].web_evidence == {slot, rerun_index, path, sha256}` of the file the barrier wrote."""
    c, bar, w = _world(tmp_path, kit, monkeypatch)
    _drive(c, bar, tmp_path)
    entry = c.p426_invalid[-1]
    assert entry["slot"] == SLOT_B and entry["stage"] == "done"
    tomb = entry["web_evidence"]
    assert set(tomb) == {"slot", "rerun_index", "path", "sha256"}
    assert tomb["slot"] == SLOT_B and tomb["rerun_index"] == 0
    dest = w["ev"] / "go__crypto-square.web.jsonl"
    assert dest.exists()
    assert co.resolve_portable(tomb["path"], w["wd"]) == dest
    assert tomb["sha256"] == hashlib.sha256(dest.read_bytes()).hexdigest()
    assert [a["slot"] for a in c.progress["slot_attempts"]] == [SLOT_A]


def test_the_leg3_shape_ends_invalid_rc_2_not_a_chain_abort(tmp_path, kit, monkeypatch):
    """[R] criterion 5: accepting the hook-stopped invocation re-runs `after_invocation`; it skips the tombstoned slot and
    the leg ends `LegInvalid` (rc 2) — baseline: the re-extraction finds the barrier's `.web.jsonl` and raises
    `ChainAbort("web evidence: ... exists")`. No accepted `slot_attempts` entry for the slot."""
    c, bar, w = _world(tmp_path, kit, monkeypatch)
    _drive(c, bar, tmp_path)
    with pytest.raises(co.ChainAbort) as exc:
        _accept(c, w)
    assert type(exc.value) is core.LegInvalid, f"{type(exc.value).__name__}: {exc.value}"
    assert exc.value.code == 2
    assert [a for a in c.progress["slot_attempts"] if a["slot"] == SLOT_B] == []
    assert [a["slot"] for a in c.progress["slot_attempts"]] == [SLOT_A]
    assert w["rec"]["status"] == "hook_stopped"


@pytest.mark.parametrize("how", ["changed", "missing"])
def test_a_tombstone_whose_file_differs_or_is_gone_is_a_chain_abort(tmp_path, kit, monkeypatch, how):
    """[N] criterion 5: the tombstone's sha256 is checked; a different or missing file -> `ChainAbort` (not `LegInvalid`).
    (Baseline: `changed` raises a ChainAbort for another reason — the immutable-file refusal — so it passes vacuously there;
    `missing` is red: the baseline silently re-extracts the deleted file and ends `LegInvalid`.)"""
    c, bar, w = _world(tmp_path, kit, monkeypatch)
    _drive(c, bar, tmp_path)
    dest = w["ev"] / "go__crypto-square.web.jsonl"
    if how == "changed":
        dest.write_bytes(dest.read_bytes() + b"{}\n")
    else:
        dest.unlink()
    with pytest.raises(co.ChainAbort) as exc:
        _accept(c, w)
    assert type(exc.value) is not core.LegInvalid
    assert [a for a in c.progress["slot_attempts"] if a["slot"] == SLOT_B] == []


def test_abandoned_web_evidence_skips_the_tombstoned_slot(tmp_path, kit, monkeypatch):
    """[R] `abandoned_web_evidence` (an invocation that did not validate) skips the tombstoned slot after the sha check:
    no exception, no second extraction (baseline: `ChainAbort`, the file exists)."""
    c, bar, w = _world(tmp_path, kit, monkeypatch)
    _drive(c, bar, tmp_path)
    dest = w["ev"] / "go__crypto-square.web.jsonl"
    before = dest.read_bytes()
    c.abandoned_web_evidence(w["rec"], w["out"])
    assert SLOT_B not in (w["rec"].get("web_evidence") or {})
    assert dest.read_bytes() == before
    assert [a for a in c.progress["slot_attempts"] if a["slot"] == SLOT_B] == []


def test_abandoned_web_evidence_with_a_changed_tombstoned_file_is_a_chain_abort(tmp_path, kit, monkeypatch):
    """[N] the same path with the file changed after the barrier -> `ChainAbort`."""
    c, bar, w = _world(tmp_path, kit, monkeypatch)
    _drive(c, bar, tmp_path)
    dest = w["ev"] / "go__crypto-square.web.jsonl"
    dest.write_bytes(b"tampered\n")
    with pytest.raises(co.ChainAbort):
        c.abandoned_web_evidence(w["rec"], w["out"])


def test_a_done_invalidation_that_extracted_nothing_records_none_and_still_gets_no_slot_attempt(tmp_path, kit, monkeypatch):
    """[R] the invalidated row has no transcript (the barrier's extraction is `unavailable`, no file): the tombstone's
    `web_evidence` is None, the leg ends `LegInvalid` and the slot gets NO `slot_attempts` entry (baseline: `after_invocation`
    appends an `accepted` attempt for the invalidated slot)."""
    c, bar, w = _world(tmp_path, kit, monkeypatch)
    w["rows"][1]["transcript_path"] = None
    _drive(c, bar, tmp_path)
    assert c.p426_invalid[-1]["slot"] == SLOT_B
    assert "web_evidence" in c.p426_invalid[-1] and c.p426_invalid[-1]["web_evidence"] is None
    with pytest.raises(co.ChainAbort) as exc:
        _accept(c, w)
    assert type(exc.value) is core.LegInvalid, f"{type(exc.value).__name__}: {exc.value}"
    assert [a for a in c.progress["slot_attempts"] if a["slot"] == SLOT_B] == []


def test_an_accepted_slot_is_still_not_extracted_twice(tmp_path, kit, monkeypatch):
    """[I] the accepted `beer-song` keeps its barrier record: exactly one slot attempt, its web evidence the barrier's."""
    c, bar, w = _world(tmp_path, kit, monkeypatch)
    _drive(c, bar, tmp_path)
    (att,) = c.progress["slot_attempts"]
    assert att["slot"] == SLOT_A and att["disposition"] == "accepted"
    assert att["web_evidence"]["sha256"] == hashlib.sha256((w["ev"] / "go__beer-song.web.jsonl").read_bytes()).hexdigest()
