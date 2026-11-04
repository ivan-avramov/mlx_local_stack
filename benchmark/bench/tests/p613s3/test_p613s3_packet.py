"""`bench.p426_panel.a7_packet`: text, diff, tool counts, hash refusals, leaks (contract "A7 packet").

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.

Readings tested (contract is silent on the exact rendering):
* `packet["off"]` / `packet["on"]` hold, per solution, the unified diff and the tool-use line (and may hold the grader line);
  `packet["task"]` holds the shared task text; the grader sentence ("both solutions pass every test") is searched in the
  concatenation of the three.
* the diff is `difflib.unified_diff(start.splitlines(keepends=True), final.splitlines(keepends=True), "a/<rel>", "b/<rel>", n=3)`
  joined, tested on files that end with a newline; `len_off` / `len_on` are the character counts of those diffs.
* tool-use line: `name count` pairs sorted by name, separated by ", ".
"""
from __future__ import annotations

import re

import pytest

from bench.p426_verify import RefusalError
from bench.tests.p613 import a7world
from bench.tests.p613s3 import s3world as S

ALPHA = ("s1", "python/alpha")
BOOK = ("s1", "python/book-store")
FORBIDDEN = [a7world.MODEL, "p426", "mtp", "drafter", "draft_kind", "joint_v1", "caslca/", "/Users/", "/private/", "/home/",
             S.MARKERS["text"], S.MARKERS["ref"], "ses_", str(S.TS0)[:7], "5678", "1234", "scratch", "tg1-", "wave2", "evidence"]


def whole(p):
    return "\n".join([p["task"], p["off"], p["on"]])


@pytest.fixture(scope="module")
def alpha(a7, panel):
    return a7.packet(panel, ALPHA)


# class: new-behaviour (the packet is {task, off, on, len_off, len_on})
def test_packet_has_the_contract_fields(alpha):
    assert {"task", "off", "on", "len_off", "len_on"} <= set(alpha)
    assert all(isinstance(alpha[k], str) and alpha[k] for k in ("task", "off", "on"))


# class: new-behaviour (the diff text on a known case, OFF and ON, every hunk line)
def test_packet_diff_text_on_a_known_case(alpha):
    off = S.expected_diff(S.START, S.OFF_SOLUTION, "sol.py")
    on = S.expected_diff(S.START, S.ON_SOLUTION, "sol.py")
    assert off in alpha["off"] and on in alpha["on"]
    assert "--- a/sol.py" in alpha["off"] and "+++ b/sol.py" in alpha["off"]
    assert "+    return x + 1" in alpha["off"] and "-    raise NotImplementedError" in alpha["off"]
    assert "+    total = x" in alpha["on"] and "+    total = x" not in alpha["off"]


# class: new-behaviour (the judged length = characters of the solution's diff text)
def test_packet_lengths_are_the_diff_character_counts(alpha):
    assert alpha["len_off"] == len(S.expected_diff(S.START, S.OFF_SOLUTION, "sol.py"))
    assert alpha["len_on"] == len(S.expected_diff(S.START, S.ON_SOLUTION, "sol.py"))
    assert alpha["len_off"] != alpha["len_on"]


# class: new-behaviour (tool-call names and counts from the events file, sorted by name, on a known case)
def test_packet_tool_counts_on_a_known_case(alpha):
    assert "edit 2, read 3, shell 2, write 1" in alpha["off"]
    assert "read 1" in alpha["on"] and "edit" not in alpha["on"].split("read 1")[0].splitlines()[-1]
    assert "edit 2, read 3" not in alpha["on"]


# class: new-behaviour (another item: the default counts, so the counts come from that item's events)
def test_packet_tool_counts_follow_the_item(a7, panel):
    p = a7.packet(panel, ("s1", "python/beta"))
    assert "read 2, edit 1" not in p["off"] and "edit 1, read 2" in p["off"]
    assert "edit 2, read 1, shell 1" in p["on"]


# class: new-behaviour (the task: instructions + the solution / test file names, shared once, not repeated per solution)
def test_packet_task_text(alpha):
    assert "INSTR-MARK-alpha" in alpha["task"]
    assert "sol.py" in alpha["task"] and "sol_test.py" in alpha["task"]
    assert "INSTR-MARK" not in alpha["off"] and "INSTR-MARK" not in alpha["on"]
    assert "APPEND-MARK" not in alpha["task"]


# class: new-behaviour (`.docs/instructions.append.md` is part of the task when the exercise has one)
def test_packet_task_includes_the_append_file(a7, panel):
    p = a7.packet(panel, BOOK)
    assert "INSTR-MARK-book-store" in p["task"] and "APPEND-MARK-book-store" in p["task"]
    assert p["task"].index("INSTR-MARK") < p["task"].index("APPEND-MARK")


# class: new-behaviour (the grader statement: both solutions pass every test)
def test_packet_states_the_grader_result(alpha):
    assert "both solutions pass every test" in whole(alpha).lower()


# class: invariant (no timestamp, token count, session id, narrative text, model / arm name, reference solution or path in a packet)
@pytest.mark.parametrize("item", [ALPHA, BOOK, ("s2", "go/xi")])
def test_packet_has_no_identity_or_transcript_leak(a7, panel, item):
    text = whole(a7.packet(panel, item))
    for needle in FORBIDDEN + [str(a7.base)]:
        assert needle not in text, needle
    assert not re.search(r"\b1[0-9]{12}\b", text)                 # no epoch-ms timestamp


# class: invariant (identical structure for A and B: both solutions are rendered by the same template)
def test_packet_solutions_share_a_structure(alpha):
    def skeleton(t):
        return [re.sub(r"[0-9]+", "N", l)[:3] for l in t.splitlines() if l.startswith(("---", "+++", "@@"))]
    assert skeleton(alpha["off"])[:2] == skeleton(alpha["on"])[:2]
    assert alpha["off"].count("\n") > 3 and alpha["on"].count("\n") > 3


@pytest.fixture(scope="module")
def extra_case(tmp_path_factory):
    return S.A7Case(tmp_path_factory.mktemp("extra"), extra={
        ("on", "s1", "python/alpha"): {"notes.md": "hello\n", "sol_test.py": S.TEST_TEXT}})


# class: new-behaviour (a new file appears in the diff as an addition; a file equal to its start version does not; paths sorted)
def test_packet_new_file_and_unchanged_file(extra_case, panel):
    p = extra_case.packet(panel, ALPHA)
    assert S.expected_diff("", "hello\n", "notes.md") in p["on"]
    assert p["on"].index("a/notes.md") < p["on"].index("a/sol.py")
    assert "sol_test.py" not in p["on"] and "notes.md" not in p["off"]
    assert p["len_on"] == len(S.expected_diff("", "hello\n", "notes.md")) + len(S.expected_diff(S.START, S.ON_SOLUTION, "sol.py"))


# class: new-behaviour (test files are protected: a final tree whose test file differs from the start is refused)
def test_packet_refuses_a_modified_test_file(tmp_path, panel):
    case = S.A7Case(tmp_path / "tm", extra={("off", "s1", "python/alpha"): {"sol_test.py": "def test_f():\n    pass\n"}})
    with pytest.raises((AssertionError, RefusalError)):
        case.packet(panel, ALPHA)


# ---------------------------------------------------------------------------------------------------- hash refusals
def alter(files, pred, fn):
    hit = [p for p in files if pred(p)]
    assert hit
    for p in hit:
        files[p] = fn(files[p])


def drop(files, pred):
    hit = [p for p in files if pred(p)]
    assert hit
    for p in hit:
        del files[p]


# class: new-behaviour (an evidence object whose bytes do not hash to its name -> RefusalError)
def test_refuses_an_object_that_does_not_hash_to_its_name(clone, panel):
    case = clone()
    sha = S.sha_text(S.OFF_SOLUTION)
    ref = case.tamper_evidence(lambda f: alter(
        f, lambda p: "tg1-p426-off-s1.a1" in p and "python__alpha.final_tree/objects/" in p and p.endswith(sha),
        lambda b: b"tampered\n"))
    with pytest.raises(RefusalError):
        case.packet(panel, ALPHA, evidence_ref=ref)


# class: new-behaviour (an events file whose bytes do not match the row's evidence_sha256.events -> RefusalError)
def test_refuses_an_events_file_that_does_not_match_the_row(clone, panel):
    case = clone()
    ref = case.tamper_evidence(lambda f: alter(
        f, lambda p: "tg1-p426-on-s1.a1" in p and p.endswith("python__alpha.events.jsonl"), lambda b: b + b"\n"))
    with pytest.raises(RefusalError):
        case.packet(panel, ALPHA, evidence_ref=ref)


# class: new-behaviour (a missing evidence file or an unresolvable evidence ref is refused, never silently skipped)
def test_refuses_missing_evidence_and_unknown_ref(clone, panel):
    case = clone()
    ref = case.tamper_evidence(lambda f: drop(f, lambda p: "tg1-p426-on-s1.a1" in p and p.endswith("python__alpha.events.jsonl")))
    assert case.packet(panel, ALPHA)                                  # control: the untampered evidence builds
    S.refuses(case.packet, panel, ALPHA, evidence_ref=ref)
    S.refuses(case.packet, panel, ALPHA, evidence_ref="0" * 40)


# class: new-behaviour (a start-tree file that does not hash to the universe's `prepared` entry -> RefusalError)
@pytest.mark.parametrize("rel,item", [("sol.py", ALPHA), (".docs/instructions.md", ALPHA),
                                      (".docs/instructions.append.md", BOOK)])
def test_refuses_a_start_tree_file_that_does_not_hash(clone, panel, rel, item):
    case = clone()
    lang, name = item[1].split("/")
    f = case.polyglot / lang / "exercises" / "practice" / name / rel
    f.write_text(f.read_text() + "# edited\n")
    with pytest.raises(RefusalError):
        case.packet(panel, item)


# class: new-behaviour (a start-tree file that is missing is refused too)
def test_refuses_a_missing_start_tree_file(clone, panel):
    case = clone()
    assert case.packet(panel, ALPHA)                                  # control
    (case.polyglot / "python" / "exercises" / "practice" / "alpha" / "sol.py").unlink()
    S.refuses(case.packet, panel, ALPHA)


# class: new-behaviour (the universe is the authority: a changed `prepared` sha refuses an untouched start tree)
def test_refuses_when_the_universe_disagrees(clone, panel):
    import json
    case = clone()
    doc = json.loads(case.universe.read_text())
    doc["items"]["python/alpha"]["prepared"]["sol.py"] = "0" * 64
    case.universe.write_text(json.dumps(doc))
    with pytest.raises(RefusalError):
        case.packet(panel, ALPHA)


# class: new-behaviour (the main-branch final_tree manifest must hash to the row's `manifest_sha256`)
def test_refuses_a_manifest_that_does_not_match_its_row(clone, panel):
    case = clone()
    m = case.item_dir("on", "s1", "python/alpha") / "manifest.json"
    m.write_text(m.read_text() + " ")
    with pytest.raises(RefusalError):
        case.packet(panel, ALPHA)


# class: new-behaviour (the B8 record's per-key manifest sha must match the manifest read)
def test_refuses_a_manifest_that_does_not_match_b8(clone, panel):
    case = clone()
    for pair in case.b8["axes"]["A7"]["pairs"]:
        for k in pair["keys"]:
            if k["key"] == list(ALPHA):
                k["on_manifest_sha256"] = "0" * 64
    with pytest.raises(RefusalError):
        case.packet(panel, ALPHA)


# class: invariant (an item that is not both-pass -- one-arm-pass, neither-pass -- is not packaged; an identical both-pass item is
# NOT asserted: the contract does not require a refusal there)
@pytest.mark.parametrize("item", [("s1", "python/delta"), ("s2", "go/phi")])
def test_refuses_items_outside_the_packet_set(a7, panel, item):
    assert a7.packet(panel, ALPHA)                                    # control
    S.refuses(a7.packet, panel, item)
