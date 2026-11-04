"""`a7-export`, `freeze`, `check_frozen` (contract "Interfaces"): the frozen packet set, A / B balance, leak refusals.

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.

Readings tested:
* `a7-export` writes judge directories `<out>/<judge label>/batchNN/pNNNN.md` + `manifest.jsonl` (the repository's
  `judge_pairwise.export_packets` layout) + `FROZEN.json`; rc 0 on success; a refusal exits rc 2 with `REFUSED:` on stderr (the
  repository's CLI convention) -- tests assert rc != 0 unless stated.
* `FROZEN.json` keys are not fixed by the contract: tests look for the recorded values anywhere in the document (text / numbers).
* hermetic numbers: 14 packets (s1 6, s2 8), 2 judges x 2 orders -> 56 planned verdicts; Wave 1 identical over the ELIGIBLE keys
  (E3: A1 keys where both arms are correct; `case.a1_eligible()`; 24 B8 keys in the synthetic world).
"""
from __future__ import annotations

import hashlib
import inspect
import json
import shutil

import pytest

from bench.p426_verify import RefusalError
from bench.tests.p613s3 import s3world as S
from bench.tests.p613s3.test_p613s3_packet import FORBIDDEN

PLANNED = 14 * 2 * 2
SEL = [("s1", r) for r in S.S1_SEL] + [("s2", r) for r in S.S2_SEL]
ALL_IDS = S.S1_SEL + S.S2_SEL


def numbers(doc):
    if isinstance(doc, bool):
        return
    if isinstance(doc, (int, float)):
        yield doc
    elif isinstance(doc, dict):
        for v in doc.values():
            yield from numbers(v)
    elif isinstance(doc, list):
        for v in doc:
            yield from numbers(v)


def frozen_of(out):
    return json.loads((out / "FROZEN.json").read_text())


def fresh(a7, tmp_path, name="panel"):
    out = tmp_path / name
    proc = a7.export(out)
    assert proc.returncode == 0, proc.stderr
    return out


# class: new-behaviour (a successful export: rc 0, packets + manifest + FROZEN.json)
def test_export_writes_packets_and_frozen(exported):
    case, out, proc = exported
    assert proc.returncode == 0, proc.stderr
    assert (out / "FROZEN.json").is_file() and (out / "manifest.jsonl").is_file()
    assert len(S.packets_of(out)) == PLANNED
    assert {p.parent.parent.name for p in S.packets_of(out)} == {S.CLAUDE_JUDGE["label"], S.CURSOR_JUDGE["label"]}


# class: new-behaviour (every item gets one packet per judge x order: 14 items x 2 judges x 2 orders, orders in separate batches)
def test_export_manifest_covers_every_item_judge_order(exported):
    _, out, _ = exported
    rows = S.manifest_of(out)
    assert len(rows) == PLANNED
    seen = {}
    for r in rows:
        seen.setdefault(S.short_id(r["item_id"], ALL_IDS), set()).add((r["judge"], r["order"]))
    assert set(seen) == set(ALL_IDS)
    want = {(j["label"], o) for j in (S.CLAUDE_JUDGE, S.CURSOR_JUDGE) for o in ("AB", "BA")}
    assert all(v == want for v in seen.values())


# class: new-behaviour (FROZEN.json records every packet's sha256, the judges, the rubric sha, the evidence ref, the B8.json sha)
def test_frozen_records_what_the_contract_lists(exported, panel):
    case, out, _ = exported
    text = (out / "FROZEN.json").read_text()
    for packet in S.packets_of(out):
        assert S.sha_file(packet) in text, packet.name
    assert panel.rubric_sha("code") in text
    assert case.evidence_ref in text
    assert S.sha_file(case.b8_path) in text
    for j in (S.CLAUDE_JUDGE, S.CURSOR_JUDGE):
        for key in ("label", "family", "client", "model"):
            assert j[key] in text, (j["label"], key)
    for rid in ALL_IDS:
        assert rid in text, rid


# class: new-behaviour (the counts: planned verdicts, Wave 1 identical, A7 excluded per kind)
def test_frozen_records_the_counts(exported):
    case, out, _ = exported
    nums = list(numbers(frozen_of(out)))
    assert PLANNED in nums
    elig, bad = case.a1_eligible()                       # E3: Wave 1 identical over the panel-ELIGIBLE keys
    assert elig + bad == 24 and elig in nums
    text = (out / "FROZEN.json").read_text()
    if bad:
        assert "not both correct" in text
    for kind in ("identical", "one-arm-pass", "neither-pass", "rejected key"):
        assert kind in text, kind


# class: invariant (FROZEN.json and the packets carry no absolute path, home path or temp path)
def test_export_has_no_absolute_path(exported):
    case, out, _ = exported
    for needle in (str(case.base), str(out), "/Users/", "/private/", "/var/folders"):
        assert needle not in (out / "FROZEN.json").read_text(), needle
        for packet in S.packets_of(out):
            assert needle not in packet.read_text(), (needle, packet.name)


# class: invariant (leak check on every exported packet: no identity, arm, path, timestamp or transcript text; the rubric is in it)
def test_exported_packets_are_blind(exported, panel):
    _, out, _ = exported
    for packet in S.packets_of(out):
        text = packet.read_text()
        for needle in FORBIDDEN:
            assert needle not in text, (needle, packet.name)
        assert panel.RUBRICS["code"] in text
    assert {r["prompt_sha"] for r in S.manifest_of(out)} == {panel.rubric_sha("code")}


# class: new-behaviour (every packet shows both diffs; A / B order follows the manifest's a_key / b_key)
def test_packet_slot_follows_the_manifest(exported, panel):
    case, out, _ = exported
    on_tune = panel.tunes("s2")[1]
    checked = 0
    for r in S.manifest_of(out):
        rid = S.short_id(r["item_id"], ALL_IDS)
        off_diff = S.expected_diff(S.START, S.OFF_SOLUTION, S.sol_name(rid))
        on_diff = S.expected_diff(S.START, S.ON_SOLUTION, S.sol_name(rid))
        text = next(iter((out / r["judge"]).glob("batch*/" + r["pkt"] + ".md"))).read_text()
        assert off_diff in text and on_diff in text
        first_is_on = text.index(on_diff) < text.index(off_diff)
        shown_first_key = r["a_key"] if r["order"] == "AB" else r["b_key"]
        assert first_is_on == (f"@{on_tune}::" in shown_first_key), (rid, r["order"])
        checked += 1
    assert checked == PLANNED


# class: new-behaviour (slots balanced: exactly half of the 14 items show ON as A in the AB order)
def test_ab_slots_are_balanced(exported, panel):
    _, out, _ = exported
    on_tune = panel.tunes("s2")[1]
    judge = S.CLAUDE_JUDGE["label"]
    on_as_a = {S.short_id(r["item_id"], ALL_IDS) for r in S.manifest_of(out)
               if r["judge"] == judge and r["order"] == "AB" and f"@{on_tune}::" in r["a_key"]}
    assert len(on_as_a) == 7
    judge2 = S.CURSOR_JUDGE["label"]
    assert on_as_a == {S.short_id(r["item_id"], ALL_IDS) for r in S.manifest_of(out)
                       if r["judge"] == judge2 and r["order"] == "AB" and f"@{on_tune}::" in r["a_key"]}


# class: new-behaviour (the same inputs give the same packets and the same FROZEN.json, in another directory)
def test_export_is_byte_identical_on_rerun(exported, tmp_path):
    case, out, _ = exported
    out2 = fresh(case, tmp_path, "again")
    assert (out / "FROZEN.json").read_bytes() == (out2 / "FROZEN.json").read_bytes()
    a = {p.relative_to(out).as_posix(): p.read_bytes() for p in S.packets_of(out)}
    b = {p.relative_to(out2).as_posix(): p.read_bytes() for p in S.packets_of(out2)}
    assert a == b and len(a) == PLANNED


# class: invariant (the recorded interface names)
def test_interface_signatures(panel):
    assert list(inspect.signature(panel.freeze).parameters)[:4] == ["out_dir", "packets_meta", "judges", "rubric"]
    assert list(inspect.signature(panel.check_frozen).parameters)[:1] == ["out_dir"]
    assert list(inspect.signature(panel.a7_select).parameters)[:2] == ["results_root", "b8"]


# ------------------------------------------------------------------------------------------------------ refusals
# class: new-behaviour (a packet that trips `leak_problems` refuses the whole export: rc != 0, no FROZEN.json)
@pytest.mark.parametrize("name,text", [("path", "def f(x):\n    # see /Users/someone/work\n    return x + 2\n"),  # allow-pii-pattern
                                       ("mtp", "def f(x):\n    # the MTP drafter helped\n    return x + 2\n"),
                                       ("model", f"def f(x):\n    # {S.MODEL}\n    return x + 2\n")])
def test_export_refuses_a_leak(tmp_path, name, text):
    case = S.A7Case(tmp_path / f"leak-{name}", texts={("on", "s1", "python/alpha"): text})
    out = tmp_path / "panel"
    proc = case.export(out)
    S.refused_cli(proc)
    assert "leak" in proc.stderr.lower()
    assert not (out / "FROZEN.json").exists()


# class: new-behaviour (a hash refusal reaches the CLI as rc 2 + REFUSED:, nothing frozen)
def test_export_refuses_tampered_evidence(clone, tmp_path):
    case = clone()
    sha = S.sha_text(S.ON_SOLUTION)
    ref = case.tamper_evidence(lambda f: [f.__setitem__(p, b"x\n") for p in list(f) if p.endswith(sha)])
    out = tmp_path / "panel"
    proc = case.export(out, evidence_ref=ref)
    assert proc.returncode == 2 and "REFUSED" in proc.stderr
    assert not (out / "FROZEN.json").exists()


# class: new-behaviour (freeze refuses when a verdict already exists in the target: nothing is frozen)
def test_export_refuses_a_directory_that_already_holds_a_verdict(a7, tmp_path):
    out = tmp_path / "panel"
    verdict = out / S.CLAUDE_JUDGE["label"] / "batch00" / "p0000.verdict.json"
    verdict.parent.mkdir(parents=True)
    verdict.write_text('{"choice": "A"}\n')
    proc = a7.export(out)
    S.refused_cli(proc)
    assert not (out / "FROZEN.json").exists()
    assert verdict.read_text() == '{"choice": "A"}\n'


# class: new-behaviour (freeze() itself: a verdict file in the directory -> RefusalError)
def test_freeze_refuses_when_a_verdict_exists(a7, panel, tmp_path):
    out = fresh(a7, tmp_path)
    (S.packets_of(out)[0].with_suffix(".verdict.json")).write_text('{"choice": "A"}\n')
    before = (out / "FROZEN.json").read_bytes()
    with pytest.raises(RefusalError):
        panel.freeze(out, [], panel.load_judges(a7.judges, "text"), "code")
    assert (out / "FROZEN.json").read_bytes() == before


# class: new-behaviour (a judges file that does not hold two judges of two families refuses)
def test_export_refuses_bad_judges(a7, tmp_path):
    bad = tmp_path / "judges.json"
    bad.write_text(json.dumps({"text": [S.CLAUDE_JUDGE, dict(S.CURSOR_JUDGE, family="anthropic")]}))
    out = tmp_path / "panel"
    case_args = a7.export_args(out)
    case_args[case_args.index("--judges") + 1] = bad
    proc = S.run_cli("bench.p426_panel", case_args)
    S.refused_cli(proc)
    assert not (out / "FROZEN.json").exists()


# class: new-behaviour (export into an existing directory is refused: packets are exported once into a fresh directory)
def test_export_refuses_an_existing_directory(a7, tmp_path):
    out = fresh(a7, tmp_path)
    before = (out / "FROZEN.json").read_bytes()
    S.refused_cli(a7.export(out))
    assert (out / "FROZEN.json").read_bytes() == before


# --------------------------------------------------------------------------------------------------- check_frozen
# class: new-behaviour (a pristine frozen directory passes and returns the record)
def test_check_frozen_accepts_a_pristine_export(a7, panel, tmp_path):
    out = fresh(a7, tmp_path)
    rec = panel.check_frozen(out)
    assert isinstance(rec, dict) and rec


# class: new-behaviour (a changed packet refuses: verdicts are never sealed or ingested against it)
def test_check_frozen_refuses_a_changed_packet(a7, panel, tmp_path):
    out = fresh(a7, tmp_path)
    p = S.packets_of(out)[3]
    p.write_text(p.read_text() + "\nextra\n")
    with pytest.raises(RefusalError):
        panel.check_frozen(out)


# class: new-behaviour (a missing packet refuses)
def test_check_frozen_refuses_a_missing_packet(a7, panel, tmp_path):
    out = fresh(a7, tmp_path)
    S.packets_of(out)[7].unlink()
    with pytest.raises(RefusalError):
        panel.check_frozen(out)


# class: new-behaviour (no FROZEN.json: nothing to check against -> refusal, not a pass)
def test_check_frozen_refuses_without_frozen_json(a7, panel, tmp_path):
    out = fresh(a7, tmp_path)
    (out / "FROZEN.json").unlink()
    S.refuses(panel.check_frozen, out)


# class: invariant (verdict files added after the freeze do not change the packets: check_frozen still passes)
def test_check_frozen_ignores_verdicts(a7, panel, tmp_path):
    out = fresh(a7, tmp_path)
    for p in S.packets_of(out)[:4]:
        p.with_suffix(".verdict.json").write_text('{"choice": "A"}\n')
    assert panel.check_frozen(out)


# class: invariant (a one-byte change to one packet is seen: the frozen hashes are per packet, not per directory size)
def test_check_frozen_sees_a_one_byte_change(a7, panel, tmp_path):
    out = fresh(a7, tmp_path)
    p = S.packets_of(out)[0]
    data = bytearray(p.read_bytes())
    data[-3] ^= 0x01
    p.write_bytes(bytes(data))
    assert hashlib.sha256(bytes(data)).hexdigest() != S.sha_file(S.packets_of(out)[1])
    with pytest.raises(RefusalError):
        panel.check_frozen(out)
    shutil.rmtree(out)
