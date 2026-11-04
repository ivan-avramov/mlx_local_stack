"""Tolerant readers for the `a7_divergence` record and the sheet's divergence section, plus run helpers.

The contract fixes WHAT is reported (per session the counts per kind, every item with its kind and `k`, a session total and
both, the first differing tool name for `environment`, a FLAG with the items when any item is `generation`) but not the JSON key
names. Lookups search the subtree for alias keys; a lookup that finds nothing FAILS the test with the keys tried (a contract
ambiguity to settle, not a pass).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from bench.tests.p613s3 import s3world as S
from bench.tests.p613s3 import sigview as SV
from bench.tests.p613s4 import s4world as W

KINDS = W.KINDS
FINAL = "FINAL — P426 certification evidence"
STEP3_STATUS = "PROVISIONAL — final review pending (step 4)"
STEP2_STATUS = "PROVISIONAL — subjective panel pending (step 3)"
HEADING = "## A7 first divergence (C284; `divergence`)"
LABEL = "visible text and tool calls only (reasoning tokens are not exported)"
ID_KEYS = ("id", "item", "item_id", "key", "name")
TOOL_KEYS = ("tool", "tool_name", "first_tool", "env_tool", "differing_tool", "first_differing_tool", "first_tool_name")
K_KEYS = ("k", "index", "message_index", "first_k", "msg_index")


def walk_path(node, path=()):
    yield path, node
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk_path(v, path + (str(k),))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk_path(v, path + (f"[{i}]",))


def _session_of(path, d):
    for k in ("session", "pair"):
        if isinstance(d.get(k), str) and d[k] in ("s1", "s2"):
            return d[k]
    for p in reversed(path):
        if p in ("s1", "s2"):
            return p
    return None


def _norm_id(v):
    """(session|None, 'lang/name') from 'python/alpha', 's1/python/alpha', ['s1', 'python/alpha']."""
    if isinstance(v, list) and len(v) == 2 and all(isinstance(x, str) for x in v):
        return v[0], v[1]
    if isinstance(v, str):
        m = re.fullmatch(r"(?:(s[12])[/: ])?([a-z]+/[A-Za-z0-9_\-]+)", v)
        if m:
            return m.group(1), m.group(2)
    return None, None


def items(div):
    """{(session, id): (kind, k, tool)} for every item record in the subtree."""
    out = {}
    for path, d in walk_path(div):
        if not (isinstance(d, dict) and d.get("kind") in KINDS):
            continue
        sess, rid = None, None
        for key in ID_KEYS:
            if key in d:
                sess, rid = _norm_id(d[key])
                if rid:
                    break
        if rid is None and path:
            sess, rid = _norm_id(path[-1])
        if rid is None:
            continue
        sess = sess or _session_of(path, d)
        k = next((d[a] for a in K_KEYS if a in d), None)
        tool = next((d[a] for a in TOOL_KEYS if a in d), None)
        assert sess in ("s1", "s2"), f"item {rid}: session not found (path {path}, keys {sorted(d)})"
        out[(sess, rid)] = (d["kind"], k, tool)
    assert out, f"no item record (a dict with `kind` in {KINDS} and an id) found; top-level keys: {sorted(div) if isinstance(div, dict) else div!r}"
    return out


def counts(div):
    """{'s1': {kind: n}, 's2': ..., 'both': ...} from dicts that carry all four kinds as ints."""
    out = {}
    for path, d in walk_path(div):
        if isinstance(d, dict) and all(isinstance(d.get(k), int) and not isinstance(d.get(k), bool) for k in KINDS):
            sess = next((p for p in reversed(path) if p in ("s1", "s2")), None)
            out.setdefault(sess or "both", {k: d[k] for k in KINDS})
    assert out, f"no per-kind count dict found; top-level keys: {sorted(div) if isinstance(div, dict) else div!r}"
    return out


def expected_items(expect):
    return {key: (kind, k, tool) for key, (kind, k, tool) in expect.items()}


def pooled(c):
    return {k: c["s1"][k] + c["s2"][k] for k in KINDS}


def section(md):
    """The text of the divergence section (heading to the next `## `)."""
    i = md.index(HEADING)
    j = md.find("\n## ", i + 1)
    return md[i: j if j >= 0 else len(md)]


# ---------------------------------------------------------------------------------------------------------------- runs
def run_all(case, out_dir, panel_dir, *, ref="<case>", extra=None, with_panel=True):
    """`p426_signals all` (+ `--evidence-ref <ref>`; ref=None omits the flag). Returns (proc, md, json)."""
    args = list(extra or [])
    if ref == "<case>":
        ref = case.evidence_ref
    if ref is not None:
        args += ["--evidence-ref", ref]
    return SV.run_all(case, out_dir, panel_dir, extra=args, with_panel=with_panel)


def must_run(case, out_dir, panel_dir, **kw):
    proc, md, js = run_all(case, out_dir, panel_dir, **kw)
    assert proc.returncode == 0, proc.stderr[-1200:]
    return Path(md), Path(js)


def divergence_flags(sig):
    """The A7 first-divergence flag only. (Delivery 2: the earlier helper also matched any text containing "generation", which
    caught the pre-existing `cross_wave` flag "generation-path file(s) differ" on the committed sheet.)"""
    return [f for f in sig["flags"] if "first divergence" in f["text"].lower() or f.get("flag") == "a7_divergence_generation"]


def a7_div(mod, case, ref=None, repo=None, b8=None, results_root=None):
    return mod.a7_divergence(results_root or case.results_root, b8 or case.b8, case.evidence_ref if ref is None else ref,
                             repo or case.repo)


def evidence_commit_with(case, mutate):
    return case.tamper_evidence(mutate)


def refusal_type():
    from bench.p426_verify import RefusalError
    return RefusalError


def refuses_as_refusal(fn, *a, **kw):
    """The call must raise `RefusalError` exactly (the contract's refusal), not another exception."""
    exc = S.refuses(fn, *a, **kw)
    assert isinstance(exc, refusal_type()), f"{type(exc).__name__}: {exc}"
    return exc


def dumps(doc):
    return json.dumps(doc, sort_keys=True)


def git_bytes(repo, ref, rel):
    """`git show <ref>:<rel>` as raw bytes (S.git strips and decodes)."""
    import subprocess
    return subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{rel}"], capture_output=True, check=True, env=S.GIT_ENV).stdout
