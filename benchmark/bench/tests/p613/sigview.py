"""Accessors and oracles for the P613 step-1 tests.

The contract pins the *functions* and the *definitions* of the signals but NOT the key names of `SIGNALS.json`. These helpers
therefore read the sheet structurally: a value is "under session s1" when it sits below a dict key `s1` or inside a dict whose
`session` / `pair` field is `s1`. Numbers are matched by value (a fraction or its percent form), never by a guessed key name.
If the implementation's layout makes one of these lookups wrong, fix it HERE, once.

Oracles compute the expected numbers from the repository's own functions (`bench.stats`, `bench.compare_predictor`) applied to
hand-built per-item vectors; the definitions are the contract's.
"""
from __future__ import annotations

import itertools
import json
import math
import re
import subprocess
import sys
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parents[3]          # .../benchmark  (cwd for the CLIs; `bench` resolves from here)
LABEL_SHOWN = "shown difference"
LABEL_WASH = "WASH — directional (not a shown difference)"
HOLM_NOTE = "PROVISIONAL: family incomplete (A1 pending)"


# ------------------------------------------------------------------------------------------------ tree reading
def leaves(doc, path=()):
    if isinstance(doc, dict):
        for k, v in doc.items():
            yield from leaves(v, path + (str(k),))
    elif isinstance(doc, (list, tuple)):
        for i, v in enumerate(doc):
            yield from leaves(v, path + (str(i),))
    else:
        yield path, doc


def scope(doc, session):
    """Every subtree that belongs to `session` (a dict value under key == session, or a dict whose session/pair == it)."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == session:
                    found.append(v)
                walk(v)
            if node.get("session") == session or node.get("pair") == session:
                found.append(node)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(doc)
    return found


def numbers(trees):
    out = []
    for t in trees:
        for _, v in leaves(t):
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                out.append(float(v))
            elif isinstance(v, str):
                out += [float(x.replace("−", "-")) for x in re.findall(r"[-−]?\d+(?:\.\d+)?", v)]
    return out


def strings(trees):
    return [v for t in trees for _, v in leaves(t) if isinstance(v, str)]


def text(trees) -> str:
    return json.dumps(trees, sort_keys=True, default=str)


def close(a, b, tol=1e-9):
    return abs(a - b) <= tol


def has_num(doc, session, x, *, tol=1e-9, pct=True, sess_tree=None):
    """Some number under `session` equals x (or 100*x when pct, to tolerance 100*tol)."""
    pool = numbers(sess_tree if sess_tree is not None else scope(doc, session))
    return any(close(v, x, tol) or (pct and close(v, 100.0 * x, 100.0 * tol)) for v in pool)


def has_num_loose(pool, x, tol=6e-3):
    """Rounded-for-display tolerance: |v - x| <= tol or |v - 100x| <= 100 tol, sign-insensitive."""
    return any(abs(abs(v) - abs(x)) <= tol or abs(abs(v) - abs(100.0 * x)) <= 100.0 * tol for v in pool)


def id_lists(trees):
    """Every list value in the trees whose elements normalise to ids; returns a list of frozensets."""
    out = []

    def norm(e):
        if isinstance(e, str):
            return e
        if isinstance(e, dict):
            return e.get("id")
        if isinstance(e, (list, tuple)) and e:
            return e[-1] if isinstance(e[-1], str) else None
        return None

    def walk(node):
        if isinstance(node, list):
            vals = [norm(e) for e in node]
            if node and all(v is not None for v in vals):
                out.append(frozenset(vals))
            elif not node:
                out.append(frozenset())
            for e in node:
                walk(e)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
    for t in trees:
        walk(t)
    return out


TAG_FIELDS = ("arm", "category", "name", "kind", "cause", "metric", "measure")


def tagged_leaves(doc, tags=frozenset(), path=()):
    """(path, tags, value): tags = lower-cased path elements plus the string value of arm/category/name/kind/cause/... fields
    of every enclosing dict, so `{"arm": "on", "category": "looping", "count": 2}` and `{"on": {"looping": 2}}` read alike."""
    if isinstance(doc, dict):
        own = {str(doc[f]).lower() for f in TAG_FIELDS if isinstance(doc.get(f), str)}
        for k, v in doc.items():
            yield from tagged_leaves(v, tags | own | {str(k).lower()}, path + (str(k),))
    elif isinstance(doc, (list, tuple)):
        for i, v in enumerate(doc):
            yield from tagged_leaves(v, tags, path + (str(i),))
    else:
        yield path, tags, doc


def counts_at(trees, *want):
    """Numeric leaves whose tags include every word in `want` (lower-cased)."""
    want = {w.lower() for w in want}
    return [v for t in trees for _, tags, v in tagged_leaves(t) if want <= tags and isinstance(v, (int, float))
            and not isinstance(v, bool)]


def subtree(sig, word):
    """Subtree(s) under a key whose name contains `word` (case-insensitive)."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if word in str(k).lower():
                    found.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(sig)
    return found


def in_window(pool, center, half):
    return any(abs(v - center) <= half for v in pool)


def wash(strs):
    """Some string carries the WASH label (C172)."""
    return any("WASH" in s and "directional (not a shown difference)" in s for s in strs)


def shown(strs):
    """Some string carries the shown-difference label and is not the wash label."""
    return any("shown difference" in s and "WASH" not in s and "not a shown" not in s for s in strs)


def flags_tree(sig):
    """The subtree(s) under any key whose name contains 'flag' (case-insensitive)."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if "flag" in str(k).lower():
                    found.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(sig)
    return found


def flag_numbers(sig):
    return numbers(flags_tree(sig))


def flag_text(sig) -> str:
    return text(flags_tree(sig)).lower()


# ------------------------------------------------------------------------------------------------ oracles
def paired(on_vals, off_vals, ids=None):
    """bench.stats.paired_delta at k = 1 on per-item 0/1 vectors (contract: iters=10000, seed=426), read-only fields."""
    from bench import stats
    ids = ids or [f"i{n}" for n in range(len(on_vals))]
    r = stats.paired_delta({i: [float(v)] for i, v in zip(ids, on_vals)}, {i: [float(v)] for i, v in zip(ids, off_vals)},
                           iters=10000, seed=426)
    return {k: r[k] for k in ("delta", "lo", "hi", "degenerate", "discordance_upper95")}


def label_of(r):
    return LABEL_SHOWN if (r["lo"] > 0 or r["hi"] < 0) else LABEL_WASH


def loss_pp(r):
    from bench import compare_predictor
    return 100.0 * compare_predictor._loss_bound(r)


def mde_of(on_vals, off_vals):
    from bench import stats
    n = len(on_vals)
    disc = sum(1 for a, b in zip(on_vals, off_vals) if a != b)
    return (stats.mde(n, disc / n), disc) if disc else (stats.mde(n), 0)


def exact_perm_tail(diffs):
    """Exact P(|mean(s.d)| >= |T| - 1e-12) over all 2^n sign vectors (the quantity `permutation_p` estimates)."""
    n = len(diffs)
    if n == 0:
        return 1.0
    t = abs(sum(diffs) / n)
    hits = 0
    for signs in itertools.product((1, -1), repeat=n):
        if abs(sum(s * d for s, d in zip(signs, diffs)) / n) >= t - 1e-12:
            hits += 1
    return hits / 2 ** n


def perm_tolerance(q, iters=10000):
    """6 sd of the Monte-Carlo estimate (1 + count) / (iters + 1), plus the +1 offset."""
    return 6.0 * math.sqrt(max(q * (1 - q), 1e-12) / iters) + 2.0 / (iters + 1)


# ------------------------------------------------------------------------------------------------ CLIs
def run_cli(module, args, *, cwd=BENCH_DIR):
    return subprocess.run([sys.executable, "-m", module, *map(str, args)], cwd=cwd, capture_output=True, text=True,
                          timeout=900, env={"PYTHONPATH": str(cwd), "PATH": "/usr/bin:/bin"})
