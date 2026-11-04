"""Hermetic A7 divergence world for the P613 step-4 tests (built on the step-3 `A7Case`).

The step-3 case supplies the results root, B8.json, the fake polyglot tree and an `evidence` commit; this module only swaps the
SYNTHETIC EVENTS (`s3world.events_text`) for scenario transcripts, one per item, so that every divergence kind exists:

    identical    plain; parallel tool calls in a different completion order; tool-input key order; interleaved message events
    environment  a tool OUTPUT differs while every `gen` is equal (first differing tool name recorded)
    generation   a text differs / a tool input differs / a tool call is duplicated (multiset)
    cutoff       one message list is a strict prefix of the other

Two worlds: A (`generation` items present -> flag raised) and B (none -> flag not raised; the rejected key still carries a
generation difference, which must NOT count). Item -> expected (kind, k, tool) tables are `EXPECT_A` / `EXPECT_B`.
Everything an implementation must ignore differs between the arms: message ids, session ids, timestamps, step events,
reasoning events, tokens, `state.metadata` / `title` / `time`.
"""
from __future__ import annotations

import json
from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch

from bench.tests.p613s3 import s3world as S

KINDS = ("identical", "environment", "generation", "cutoff")
IDT = ("identical", None, None)


# ------------------------------------------------------------------------------------------------------------- builders
def T(text):
    return ("text", text)


def X(name, inp, out="ok"):
    return ("tool", name, inp, out)


def contiguous(msgs):
    return [(mi, part) for mi, parts in enumerate(msgs) for part in parts]


def events_for(arm, session, rid, order):
    """`order` = [(message index, part)] in COMPLETION order. Message ids / session id / timestamps are arm-specific."""
    skew = 1 if arm == "on" else 2
    sid = f"ses_{arm}_{session}_{rid.replace('/', '_')}"

    def mid(i):
        return f"msg_{arm}{skew}{i:03d}zz{session}"

    lines, n = [], 0

    def ev(kind, part):
        nonlocal n
        n += 1
        part = dict(part, sessionID=sid)
        lines.append(json.dumps({"type": kind, "timestamp": S.TS0 + skew * 100000 + n * 977, "sessionID": sid, "part": part}))

    seen = []
    for mi, part in order:
        if mi not in seen:
            seen.append(mi)
            ev("step_start", {"messageID": mid(mi), "type": "step-start", "snapshot": f"snap{arm}{n}"})
            ev("reasoning", {"messageID": mid(mi), "type": "reasoning", "text": f"private thoughts {arm} {n}"})
        if part[0] == "text":
            ev("text", {"messageID": mid(mi), "type": "text", "text": part[1], "time": {"start": n * skew}})
        else:
            _, name, inp, out = part
            ev("tool_use", {"messageID": mid(mi), "type": "tool", "tool": name, "id": f"call-{arm}-{n}",
                            "state": {"status": "completed", "input": inp, "output": out,
                                      "metadata": {"arm": arm, "n": n}, "title": f"{name} {arm}{n}",
                                      "time": {"start": n * skew, "end": n * skew + 5}}})
    for mi in seen:
        ev("step_finish", {"messageID": mid(mi), "type": "step-finish",
                           "tokens": {"input": 100 * skew + mi, "output": 7 * skew}, "cost": 0})
    return "\n".join(lines) + "\n"


def P(path="$STACK_WORKDIR/scratch/oc/x"):
    return {"path": path}


def _base(tag):
    """Three plain messages: read / write / shell (a common prefix for most scenarios)."""
    return [[T(f"look at {tag}"), X("read", P(f"$STACK_WORKDIR/scratch/{tag}/a.py"), "read-out")],
            [X("write", {"path": f"$STACK_WORKDIR/scratch/{tag}/sol.py", "content": "x = 1\n"}, "wrote")],
            [T("run the tests"), X("shell", {"command": "pytest -q"}, "1 passed")]]


def _copy(msgs):
    return [list(m) for m in msgs]


def scenario(world, session, rid):
    """(off order, on order, expected (kind, k, tool|None)); an item without a scenario is a plain identical pair."""
    tag = rid.replace("/", "_")
    b = _base(tag)
    gen_off = world == "B"                      # world B: the would-be `generation` items are plain identical
    key = (session, rid)

    def same():
        return contiguous(b), contiguous(b), IDT

    if key == ("s1", "python/beta"):            # parallel tool calls, other completion order, text after / before the tools
        off = [[X("read", P("$STACK_WORKDIR/a"), "A"), X("read", P("$STACK_WORKDIR/b"), "B"), T("two reads")]]
        on = [[T("two reads"), X("read", P("$STACK_WORKDIR/b"), "B"), X("read", P("$STACK_WORKDIR/a"), "A")]]
        return contiguous(off), contiguous(on), IDT
    if key == ("s1", "python/gamma"):           # tool input key order
        off = [[X("edit", {"path": "$STACK_WORKDIR/f", "old": "a", "new": "b"}, "done")]]
        on = [[X("edit", {"new": "b", "old": "a", "path": "$STACK_WORKDIR/f"}, "done")]]
        return contiguous(off), contiguous(on), IDT
    if key == ("s1", "python/epsilon"):         # message events interleaved in the OFF file only (group by messageID)
        off = [(0, T("first")), (1, T("second")), (0, X("read", P(), "r"))]
        on = contiguous([[T("first"), X("read", P(), "r")], [T("second")]])
        return off, on, IDT
    if key == ("s1", "python/book-store"):      # environment k=1, tool shell
        off, on = _copy(b), _copy(b)
        off[1] = [X("write", {"path": "p", "content": "1"}, "wrote"), X("shell", {"command": "pytest"}, "FAILED 3")]
        on[1] = [X("write", {"path": "p", "content": "1"}, "wrote"), X("shell", {"command": "pytest"}, "3 passed")]
        return contiguous(off), contiguous(on), ("environment", 1, "shell")
    if key == ("s1", "python/delta"):           # environment k=0 (read); a generation difference LATER is not the first
        off, on = _copy(b), _copy(b)
        on[0] = [b[0][0], X("read", P(f"$STACK_WORKDIR/scratch/{tag}/a.py"), "read-out CHANGED")]
        on[1] = [T("a different narrative"), *b[1]]
        return contiguous(off), contiguous(on), ("environment", 0, "read")
    if key == ("s1", "go/theta"):               # environment k=2 (edit); messages 0 and 1 equal
        off = [*b[:2], [X("edit", {"path": "q", "old": "1", "new": "2"}, "edited")]]
        on = [*b[:2], [X("edit", {"path": "q", "old": "1", "new": "2"}, "edit REFUSED")]]
        return contiguous(off), contiguous(on), ("environment", 2, "edit")
    if key == ("s1", "go/two-fer"):             # generation k=0 (a text differs)
        if gen_off:
            return same()
        off, on = _copy(b), _copy(b)
        on[0] = [T("look at it differently"), b[0][1]]
        return contiguous(off), contiguous(on), ("generation", 0, None)
    if key == ("s1", "go/eta"):                 # generation k=2 (a tool input differs); messages 0, 1 equal
        if gen_off:
            return same()
        off, on = _copy(b), _copy(b)
        on[2] = [b[2][0], X("shell", {"command": "pytest -x"}, "1 passed")]
        return contiguous(off), contiguous(on), ("generation", 2, None)
    if key == ("s1", "go/zeta"):                # cutoff: OFF is the strict 2-message prefix of ON
        return contiguous(b[:2]), contiguous(b), ("cutoff", None, None)
    if key == ("s1", "go/psi"):                 # the REJECTED key: a generation difference that must never be counted
        off, on = _copy(b), _copy(b)
        on[0] = [T("psi differs"), b[0][1]]
        return contiguous(off), contiguous(on), ("generation", 0, None)
    if key == ("s2", "python/kappa"):           # generation k=1: an extra text part in ON
        if gen_off:
            return same()
        off, on = _copy(b), _copy(b)
        on[1] = [T("let me write it"), *b[1]]
        return contiguous(off), contiguous(on), ("generation", 1, None)
    if key == ("s2", "python/mu"):              # environment k=0 (read)
        off, on = _copy(b), _copy(b)
        on[0] = [b[0][0], X("read", P(f"$STACK_WORKDIR/scratch/{tag}/a.py"), "other file content")]
        return contiguous(off), contiguous(on), ("environment", 0, "read")
    if key == ("s2", "python/nu"):              # cutoff: ON is the strict prefix (OFF longer)
        return contiguous(b), contiguous(b[:1]), ("cutoff", None, None)
    if key == ("s2", "go/xi"):                  # parallel calls whose OUTPUTS differ per call, completion order swapped
        off = [[X("read", P("$STACK_WORKDIR/a"), "A-out"), X("shell", {"command": "ls"}, "S-out")], *b[1:]]
        on = [[X("shell", {"command": "ls"}, "S-out"), X("read", P("$STACK_WORKDIR/a"), "A-out")], *b[1:]]
        return contiguous(off), contiguous(on), IDT
    if key == ("s2", "go/omicron"):             # environment k=1; message 1 has two tools, only shell's output differs
        off, on = _copy(b), _copy(b)
        off[1] = [X("edit", {"path": "e", "old": "a", "new": "b"}, "ok"), X("shell", {"command": "go test"}, "FAIL")]
        on[1] = [X("shell", {"command": "go test"}, "ok"), X("edit", {"path": "e", "old": "a", "new": "b"}, "ok")]
        return contiguous(off), contiguous(on), ("environment", 1, "shell")
    if key == ("s2", "go/rho"):                 # generation k=0: the ON multiset holds one tool call more
        if gen_off:
            return same()
        off, on = _copy(b), _copy(b)
        on[0] = [*b[0], b[0][1]]
        return contiguous(off), contiguous(on), ("generation", 0, None)
    return same()                               # plain identical: alpha, iota, pi, sigma, tau, upsilon, phi


ACCEPTED = {"s1": [r for r in S.ids_for(True)["s1"] if r != "go/psi"], "s2": S.ids_for(True)["s2"]}


def expect(world):
    return {(s, r): scenario(world, s, r)[2] for s in ("s1", "s2") for r in ACCEPTED[s]}


EXPECT_A, EXPECT_B = expect("A"), expect("B")


def counts_of(exp):
    out = {s: dict.fromkeys(KINDS, 0) for s in ("s1", "s2")}
    for (s, _), (kind, _, _) in exp.items():
        out[s][kind] += 1
    return out


# --------------------------------------------------------------------------------------------------------------- the case
_WORLD = {"name": "A"}


DAMAGED = ("s1", "python/alpha", "off")          # the one events file damaged in the `C:<variant>` worlds


def damage(text, variant):
    """Remove a required field from every `tool_use.state` of an events file (fix 1: a retained tool event must carry
    `state.input` and `state.output`)."""
    out = []
    for line in text.splitlines():
        ev = json.loads(line)
        if ev["type"] == "tool_use":
            st = ev["part"]["state"]
            if variant == "no_input":
                st.pop("input", None)
            elif variant == "no_output":
                st.pop("output", None)
            elif variant == "no_state":
                ev["part"].pop("state", None)
            else:
                raise AssertionError(variant)
        out.append(json.dumps(ev))
    return "\n".join(out) + "\n"


def synthetic_events_text(arm, session, rid, counts):
    name = _WORLD["name"]
    off, on, _ = scenario("A" if name.startswith("C:") else name, session, rid)
    text = events_for(arm, session, rid, off if arm == "off" else on)
    if name.startswith("C:") and (session, rid, arm) == DAMAGED:
        text = damage(text, name[2:])
    return text


def build_case(base, world, with_rejected=True):
    """A7Case whose events are the scenario transcripts of `world` ('A' | 'B'). `with_rejected=True` edits B8 to reject `go/psi`
    (what a7_divergence must skip); `p426_signals all` refuses such an edited B8 ("pair keys differ from B8.json", the reason the
    step-3 signals tests use `with_rejected=False`), so the CLI worlds are built without it."""
    _WORLD["name"] = world
    with MonkeyPatch.context() as mp:
        mp.setattr(S, "events_text", synthetic_events_text)
        return S.A7Case(Path(base), with_rejected=with_rejected)


def events_rel(case, arm, session, rid):
    """Repo-relative path of the item's events file on the evidence branch."""
    tree = case.item_dir(arm, session, rid)
    return (tree.parent / (tree.name[: -len(".final_tree")] + ".events.jsonl")).relative_to(case.repo).as_posix()
