"""`a7-cursor` (with a FAKE `cursor-agent` executable first on PATH -- never a real judge) and `a7-seal`.

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.

Readings tested:
* `a7-cursor --out <dir> --judge <label>` runs `p426_panel.run_cursor_judge` (retries 0) for that judge: one `cursor-agent`
  call per packet of that judge, a verdict file `<pkt>.verdict.json` per parsed answer, `<pkt>.failed.txt` per failure,
  `<judge>/provenance.json`; an existing verdict is not re-judged.
* `a7-seal --out <dir> --judge <label> --client-version <v>` runs `seal_verdicts` for the judge's bare verdicts.
* both call `check_frozen` first: a changed packet -> no call, no seal, rc != 0.
* the fake agent logs each judging call (not `--version`) as one line `pNNNN` into $FAKE_CURSOR_LOG.
"""
from __future__ import annotations

import json

import pytest

from bench.tests.p613s3 import s3world as S

CUR, CLA = S.CURSOR_JUDGE["label"], S.CLAUDE_JUDGE["label"]


@pytest.fixture
def world(a7, tmp_path):
    out = tmp_path / "panel"
    assert a7.export(out).returncode == 0
    fake = S.install_fake_cursor(tmp_path / "bin")
    return a7, out, fake, tmp_path / "calls.log"


def run_cursor(world, *, mode="A", fail=(), judge=CUR):
    case, out, fake, log = world
    env = {"FAKE_CURSOR_LOG": str(log), "FAKE_CURSOR_MODE": mode, "FAKE_CURSOR_FAIL": ",".join(fail)}
    return S.run_cli("bench.p426_panel", ["a7-cursor", "--out", out, "--judge", judge], path_prefix=str(fake), env_extra=env,
                     home=out.parent)


def calls(log):
    return log.read_text().split() if log.exists() else []


def pkts(out, judge):
    return sorted(p for p in S.packets_of(out) if p.parent.parent.name == judge)


def verdicts(out, judge):
    return sorted((out / judge).glob("batch*/p*.verdict.json"))


# class: new-behaviour (every packet of the Cursor judge is judged once; verdicts carry their provenance)
def test_cursor_judges_every_packet_once_and_seals_provenance(world, panel):
    case, out, _, log = world
    proc = run_cursor(world)
    assert proc.returncode == 0, proc.stderr
    mine = pkts(out, CUR)
    assert len(mine) == 28 and len(verdicts(out, CUR)) == 28
    assert sorted(calls(log)) == sorted(p.stem for p in mine)           # retries 0: exactly one call per packet
    v = json.loads(verdicts(out, CUR)[0].read_text())
    pkt = verdicts(out, CUR)[0].name.split(".")[0]
    packet = next(p for p in mine if p.stem == pkt)
    assert v["choice"] == "A" and v["judge"] == CUR and v["family"] == "openai" and v["client"] == "cursor-agent"
    assert v["model"] == "gpt-5.6-sol-high" and v["client_version"] == "9.9.9-fake"
    assert v["packet_sha"] == S.sha_file(packet) and v["prompt_sha"] == panel.rubric_sha("code")
    prov = json.loads((out / CUR / "provenance.json").read_text())
    assert prov["client_version"] == "9.9.9-fake" and prov["model"] == "gpt-5.6-sol-high"


# class: invariant (the other judge's directory is untouched)
def test_cursor_leaves_the_claude_judge_alone(world):
    case, out, _, _ = world
    assert run_cursor(world).returncode == 0
    assert len(verdicts(out, CUR)) == 28                              # control: the Cursor judge did run
    assert verdicts(out, CLA) == [] and not (out / CLA / "provenance.json").exists()


# class: new-behaviour (a failed call is a missing verdict, counted, never retried)
def test_cursor_failed_calls_are_missing_not_retried(world):
    case, out, _, log = world
    manifest = [r for r in S.manifest_of(out) if r["judge"] == CUR]
    bad = [manifest[0]["pkt"], manifest[5]["pkt"]]
    run_cursor(world, fail=bad)
    assert len(verdicts(out, CUR)) == 26
    for pkt in bad:
        assert calls(log).count(pkt) == 1
        assert not list((out / CUR).glob(f"batch*/{pkt}.verdict.json"))
        assert list((out / CUR).glob(f"batch*/{pkt}.failed.txt"))


# class: new-behaviour (an unparseable answer writes no verdict)
def test_cursor_garbage_answers_write_no_verdict(world):
    case, out, _, _ = world
    run_cursor(world, mode="garbage")
    assert verdicts(out, CUR) == []
    assert len(list((out / CUR).glob("batch*/*.failed.txt"))) == 28


# class: invariant (a second run re-judges nothing: an existing verdict stands)
def test_cursor_is_resumable_without_rejudging(world):
    case, out, _, log = world
    assert run_cursor(world).returncode == 0
    n = len(calls(log))
    assert n == 28
    before = {p.name: p.read_bytes() for p in verdicts(out, CUR)}
    run_cursor(world, mode="B")
    assert len(calls(log)) == n
    assert {p.name: p.read_bytes() for p in verdicts(out, CUR)} == before


# class: new-behaviour (a changed packet: no judge call at all, rc != 0)
def test_cursor_refuses_against_a_changed_packet(world):
    case, out, _, log = world
    p = pkts(out, CUR)[2]
    p.write_text(p.read_text() + "\nchanged\n")
    proc = run_cursor(world)
    S.refused_cli(proc)
    assert calls(log) == [] and verdicts(out, CUR) == []


# class: new-behaviour (an unknown judge label refuses)
def test_cursor_refuses_an_unknown_judge(world):
    case, out, _, log = world
    proc = run_cursor(world, judge="cursor:nope")
    S.refused_cli(proc)
    assert calls(log) == []


# class: invariant (the judge's own client version check: no `cursor-agent` on PATH -> no verdict)
def test_cursor_without_the_client_writes_nothing(a7, tmp_path):
    out = tmp_path / "panel"
    assert a7.export(out).returncode == 0
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = S.run_cli("bench.p426_panel", ["a7-cursor", "--out", out, "--judge", CUR], path_prefix=None,
                     env_extra={"PATH": str(empty)}, home=tmp_path)
    S.refused_cli(proc)
    assert verdicts(out, CUR) == []


# ------------------------------------------------------------------------------------------------------------- seal
def write_bare(out, judge, n=None, choice="A"):
    paths = pkts(out, judge)[:n]
    for p in paths:
        p.with_name(p.stem + ".verdict.json").write_text(json.dumps({"choice": choice, "rationale": "r"}) + "\n")
    return paths


def seal(out, judge=CLA, version="2.3.4", extra=()):
    return S.run_cli("bench.p426_panel", ["a7-seal", "--out", out, "--judge", judge, "--client-version", version, *extra],
                     home=out.parent)


# class: new-behaviour (a7-seal binds each bare verdict to its packet sha and the judge's provenance)
def test_seal_binds_verdicts_to_packets(world, panel):
    case, out, _, _ = world
    paths = write_bare(out, CLA)
    proc = seal(out)
    assert proc.returncode == 0, proc.stderr
    assert len(paths) == 28
    for p in paths:
        v = json.loads(p.with_name(p.stem + ".verdict.json").read_text())
        assert v["choice"] == "A" and v["judge"] == CLA and v["family"] == "anthropic" and v["model"] == "claude-opus-5-5"
        assert v["client"] == "claude-code:blind-judge" and v["client_version"] == "2.3.4"
        assert v["packet_sha"] == S.sha_file(p) and v["prompt_sha"] == panel.rubric_sha("code")


# class: invariant (sealing twice changes nothing; verdicts that were never written are not invented)
def test_seal_is_idempotent_and_partial(world):
    case, out, _, _ = world
    paths = write_bare(out, CLA, n=5)
    assert seal(out).returncode == 0
    first = {p.name: p.read_bytes() for p in verdicts(out, CLA)}
    assert len(first) == 5
    assert seal(out, version="9.9.9").returncode == 0
    assert {p.name: p.read_bytes() for p in verdicts(out, CLA)} == first


# class: new-behaviour (a packet changed after its verdict was written: never sealed, rc != 0, the bare verdict stays bare)
def test_seal_refuses_against_a_changed_packet(world):
    case, out, _, _ = world
    paths = write_bare(out, CLA, n=6)
    paths[1].write_text(paths[1].read_text() + "\nchanged\n")
    proc = seal(out)
    S.refused_cli(proc)
    for p in paths:
        v = json.loads(p.with_name(p.stem + ".verdict.json").read_text())
        assert "packet_sha" not in v


# class: new-behaviour (unknown judge and a missing client version refuse)
def test_seal_refuses_unknown_judge_and_missing_version(world):
    case, out, _, _ = world
    write_bare(out, CLA, n=2)
    S.refused_cli(seal(out, judge="nobody"))
    proc = S.run_cli("bench.p426_panel", ["a7-seal", "--out", out, "--judge", CLA], home=out.parent)
    assert proc.returncode != 0 and proc.stderr.strip()
    assert all("packet_sha" not in json.loads(p.read_text()) for p in verdicts(out, CLA))
