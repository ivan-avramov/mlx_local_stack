"""P613 step 4 — the A7 first-divergence section (C284 / P629; `docs/specs/p613-step4-contract.md`).

Per B8-accepted A7 key (s1, s2): both arms' events files from the `evidence` branch at a recorded ref (`git show`, no
checkout), each bound through the attempt's HARVEST.json (step-3 erratum E2); messages = `text` / `tool_use` events grouped
by `part.messageID` in first-appearance order; the first message index where the two arms differ, classified
identical / cutoff / generation / environment. Deterministic; no absolute path.
"""
from __future__ import annotations

import hashlib
import json

KINDS = ("identical", "environment", "cutoff", "generation")
SCOPE_LABEL = "visible text and tool calls only (reasoning tokens are not exported)"
SESSIONS = ("s1", "s2")
FLAG_NAME = "a7_divergence_generation"
METHOD = ("messages = `text` / `tool_use` events grouped by `part.messageID` in first-appearance order; gen = sorted "
          "multiset of (text, part.text) and (tool, part.tool, JSON(state.input, sorted keys)); env = sorted multiset of "
          "(part.tool, JSON(state.input, sorted keys), str(state.output)); first index k where the OFF / ON message lists "
          "differ: generation (gen differs), environment (gen equal, env differs), cutoff (one list a strict prefix of the "
          "other, k = the shorter length), identical (equal lists)")


def _refusal(msg):
    from bench.p426_verify import RefusalError

    return RefusalError(msg)


TERMINAL = ("completed", "error")


def _tool_state(part, where, n):
    """The validated terminal `state` of a retained `tool_use` event: a dict with `status` in TERMINAL and an object
    `input`; `completed` carries `output`, `error` carries a string `error` (opencode writes no `output` for it)."""
    state = part.get("state")
    if not isinstance(state, dict):
        raise _refusal(f"{where}: events line {n} is a tool_use with no part.state object")
    status = state.get("status")
    if status not in TERMINAL:
        raise _refusal(f"{where}: events line {n} is a tool_use whose state.status {status!r} is not terminal "
                       f"({' / '.join(TERMINAL)})")
    if not isinstance(state.get("input"), dict):
        raise _refusal(f"{where}: events line {n} is a tool_use with no state.input object")
    if status == "completed" and state.get("output") is None:
        raise _refusal(f"{where}: events line {n} is a completed tool_use with no state.output")
    if status == "error" and not isinstance(state.get("error"), str):
        raise _refusal(f"{where}: events line {n} is an error tool_use with no state.error string")
    return state


def _input_json(state):
    return json.dumps(state["input"], sort_keys=True)


def parse_messages(events, where):
    """[(gen, env)] per message, in order of the message's first `text` / `tool_use` event."""
    try:
        text = events.decode("utf-8")
    except UnicodeDecodeError:
        raise _refusal(f"{where}: events file is not UTF-8") from None
    order, msgs = [], {}
    for n, line in enumerate(text.split("\n"), 1):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            raise _refusal(f"{where}: events line {n} is not JSON") from None
        if not isinstance(ev, dict) or ev.get("type") not in ("text", "tool_use"):
            continue
        part = ev.get("part")
        mid = part.get("messageID") if isinstance(part, dict) else None
        if not isinstance(mid, str) or not mid:
            raise _refusal(f"{where}: events line {n} ({ev['type']}) has no part.messageID")
        if mid not in msgs:
            order.append(mid)
            msgs[mid] = ([], [])
        gen, env = msgs[mid]
        if ev["type"] == "text":
            t = part.get("text")
            if not isinstance(t, str):
                raise _refusal(f"{where}: events line {n} is a text event with no part.text")
            gen.append(("text", t))
        else:
            tool = part.get("tool")
            if not isinstance(tool, str) or not tool:
                raise _refusal(f"{where}: events line {n} is a tool_use with no part.tool")
            state = _tool_state(part, where, n)
            inp = _input_json(state)
            gen.append(("tool", tool, inp))
            env.append((tool, inp, str(state.get("output"))))
    return [(sorted(msgs[m][0]), sorted(msgs[m][1])) for m in order]


def first_divergence(off, on):
    """{kind, k, tool} for two message lists (`parse_messages` output); tool only for `environment`."""
    for k in range(min(len(off), len(on))):
        (g_off, e_off), (g_on, e_on) = off[k], on[k]
        if g_off != g_on:
            return dict(kind="generation", k=k, tool=None)
        if e_off != e_on:
            # gen equal => the same sorted (tool, input) sequence, same length: the first differing entry names one tool.
            tool = next(a[0] for a, b in zip(e_off, e_on) if a != b)
            return dict(kind="environment", k=k, tool=tool)
    if len(off) == len(on):
        return dict(kind="identical", k=None, tool=None)
    return dict(kind="cutoff", k=min(len(off), len(on)), tool=None)


def _events(att, row, rid, top, ref):
    """(repo-relative published path, bytes) of the item's events file, bound through HARVEST.json (E2)."""
    import re

    from bench import p426_panel as P
    from bench import p426_verify as V

    lang, _, item = rid.partition("/")
    run = P._run_id(row, rid)
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", run):
        raise _refusal(f"row {rid}: run id {run!r} is not a plain name")
    published = f"{V.REPO_PREFIX}{V.WAVE}/{att['name']}/evidence/{run}/{lang}__{item}.events.jsonl"
    data = P._git_show(top, ref, published)
    got = hashlib.sha256(data).hexdigest()
    ev_sha = row.get("evidence_sha256")
    want = ev_sha.get("events") if isinstance(ev_sha, dict) else None
    recs = [f for f in (att["harvest"].get("files") or []) if isinstance(f, dict) and f.get("published") == published
            and f.get("destination") == "evidence"]
    if not isinstance(want, str) or len(recs) != 1 or recs[0].get("sha256") != want or \
            recs[0].get("published_sha256") != got:
        raise _refusal(f"{att['name']} {rid}: events file {published} (sha256 {got}) is not bound by a single HARVEST "
                       f"record (raw sha256 == row evidence_sha256.events {want!r}, published_sha256 == the bytes read)")
    return published, data


def a7_divergence(results_root, b8, evidence_ref, repo):
    """The divergence record (`docs/specs/p613-step4-contract.md`): per session the kind counts and every key with its
    kind and k (sorted by id), totals, the generation FLAG, and `inputs` {`evidence:<ref>:<repo path>`: sha256}."""
    from bench import p426_panel as P
    from bench import p426_verify as V

    top = V.repo_top(repo)
    ref = V.resolve_commit(top, evidence_ref, "--evidence-ref")
    ctx = P._a7_context(results_root, b8)
    inputs, sessions = {}, {}
    for s in SESSIONS:
        rec = ctx["by_session"][s]
        if not rec.get("accepted"):
            sessions[s] = dict(status="rejected by B8", reasons=list(rec.get("reasons") or []), items=[],
                               counts={k: 0 for k in KINDS}, total=0)
            continue
        keys = rec.get("keys")
        if not isinstance(keys, list):
            raise _refusal(f"B8.json pair {s} has no keys list")
        ids = []
        for k in keys:
            key = k.get("key") if isinstance(k, dict) else None
            if not (isinstance(key, list) and len(key) == 2 and key[0] == s and isinstance(key[1], str)):
                raise _refusal(f"B8.json pair {s}: key {key!r} is not [{s!r}, <id>]")
            ids.append(key[1])
        if len(set(ids)) != len(ids):
            raise _refusal(f"B8.json pair {s}: a key is listed twice")
        items = []
        for rid in sorted(ids):
            msgs = {}
            for arm in ("off", "on"):
                att = ctx["atts"][s][arm]
                row = att["rows"].get(rid)
                if row is None:
                    raise _refusal(f"{att['name']} {rid}: no row for a B8-accepted key (no events file to compare)")
                path, data = _events(att, row, rid, top, ref)
                inputs[f"evidence:{ref}:{path}"] = hashlib.sha256(data).hexdigest()
                msgs[arm] = parse_messages(data, f"{att['name']} {rid}")
            d = first_divergence(msgs["off"], msgs["on"])
            items.append(dict(id=rid, kind=d["kind"], k=d["k"], tool=d["tool"], messages_off=len(msgs["off"]),
                              messages_on=len(msgs["on"])))
        counts = {k: sum(1 for it in items if it["kind"] == k) for k in KINDS}
        sessions[s] = dict(status="accepted", off=ctx["atts"][s]["off"]["name"], on=ctx["atts"][s]["on"]["name"],
                           items=items, counts=counts, total=len(items))
    both = {k: sum(sessions[s]["counts"][k] for s in SESSIONS) for k in KINDS}
    gen_items = [f"{s}/{it['id']}" for s in SESSIONS for it in sessions[s]["items"] if it["kind"] == "generation"]
    flag = dict(raised=bool(gen_items), items=gen_items)
    complete = all(sessions[s]["status"] == "accepted" for s in SESSIONS)
    return dict(label=SCOPE_LABEL, method=METHOD, evidence_ref=ref, evidence_ref_given=evidence_ref, sessions=sessions, both=both,
                total=sum(sessions[s]["total"] for s in SESSIONS), flag=flag, complete=complete,
                inputs=dict(sorted(inputs.items())))


def flags(div):
    """The sheet-level flag (listed, never a veto) when any item's kind is `generation`."""
    if not div["flag"]["raised"]:
        return []
    items = div["flag"]["items"]
    return [dict(flag=FLAG_NAME, member="A7", value=len(items), items=list(items),
                 text=f"A7 first divergence: {len(items)} item(s) diverge first in generation ({SCOPE_LABEL})")]


def render_md(div):
    p = "divergence"
    lines = ["## A7 first divergence (C284; `divergence`)", "",
             f"- Scope: {div['label']}; evidence ref `{div['evidence_ref']}`; events bound through each attempt's "
             "HARVEST.json (E2)", f"- Method: {div['method']}", "",
             "| session | identical | environment | cutoff | generation | total |", "|---|---|---|---|---|---|"]
    for s in SESSIONS:
        c = div["sessions"][s]["counts"]
        lines.append(f"| {s} | " + " | ".join(str(c[k]) for k in KINDS) + f" | {div['sessions'][s]['total']} |")
    lines.append("| both | " + " | ".join(str(div["both"][k]) for k in KINDS) + f" | {div['total']} |")
    lines += ["", ("- FLAG (`divergence.flag`): generation-first items " + ", ".join(f"`{i}`" for i in div["flag"]["items"])
                   if div["flag"]["raised"] else "- Flag (`divergence.flag`): none (no generation-first item)"), ""]
    for s in SESSIONS:
        rec = div["sessions"][s]
        lines.append(f"### A7-{s} items (`{p}.sessions.{s}.items`)")
        lines.append("")
        if rec["status"] != "accepted":
            lines += [f"- {rec['status']}: " + "; ".join(rec["reasons"]), ""]
            continue
        lines += [f"- Pair: OFF `{rec['off']}` / ON `{rec['on']}`", "",
                  "| id | kind | k | first differing tool | messages OFF / ON |", "|---|---|---|---|---|"]
        for it in rec["items"]:
            lines.append(f"| `{it['id']}` | {it['kind']} | {'—' if it['k'] is None else it['k']} | "
                         f"{it['tool'] or '—'} | {it['messages_off']} / {it['messages_on']} |")
        lines.append("")
    return lines
