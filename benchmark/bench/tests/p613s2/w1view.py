"""Accessors and oracles for the P613 step-2 tests.

The contract pins the functions, the B8 shapes and the definitions, NOT the key names of `SIGNALS.json`. As in step 1, the sheet
is read structurally: a subtree belongs to an axis when it sits below a dict key named after the axis (`A1`, `A2`, `A3`, `A4`,
`M1`, `family`, `flags` ...); numbers are matched by value (fraction or percent form), never by a guessed key name. Fixtures give
the blocks distinct numbers so a value found in an axis subtree identifies its cell. If the implementation's layout makes one
lookup wrong, fix it HERE, once.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from bench.tests.p613 import sigview as SV
from bench.tests.p613.sigview import (close, flag_numbers, flag_text, flags_tree, has_num_loose, numbers, strings,  # noqa: F401
                                      subtree, text)

BENCH_DIR = SV.BENCH_DIR


def digit(x) -> str:
    return re.sub(r"\D", "", str(x))


def wave1(b8):
    """The Wave 1 record of a `verify_all` result (or the record itself)."""
    return b8["axes"]["wave1"] if "axes" in b8 else b8


def pairs_of(b8, kind):
    return sorted((p for p in wave1(b8)["pairs"] if p["kind"] == kind), key=lambda p: digit(p["block"]))


def pair(b8, kind, block):
    hits = [p for p in wave1(b8)["pairs"] if p["kind"] == kind and digit(p["block"]) == digit(block)]
    assert len(hits) == 1, (kind, block, [(p["kind"], p["block"]) for p in wave1(b8)["pairs"]])
    return hits[0]


def accepted_all(b8):
    return all(p["accepted"] for p in wave1(b8)["pairs"])


def rejected(b8):
    return [p for p in wave1(b8)["pairs"] if not p["accepted"]]


def reason_text(p) -> str:
    return " | ".join(p["reasons"]).lower()


def axis_tree(sig, axis):
    """Subtrees under a key equal to `axis` (case-insensitive) or `axis_*` / `axis *`."""
    found = []
    a = axis.lower()

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                key = str(k).lower()
                if key == a or key.startswith(a + "_") or key.startswith(a + " "):
                    found.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(sig)
    return found


def has(pool, x, tol=1e-3):
    """Some number in `pool` equals x (fraction form) or 100 x (percent form), to display rounding; sign-sensitive."""
    return any(abs(v - x) <= tol or abs(v - 100.0 * x) <= 100.0 * tol for v in pool)


def axis_has(sig, axis, x, tol=1e-3):
    return has(numbers(axis_tree(sig, axis)), x, tol)


def axis_pool(sig, axis):
    return numbers(axis_tree(sig, axis))


def axis_text(sig, axis) -> str:
    return text(axis_tree(sig, axis))


def refused_or_rejected(fn, check):
    """Run `fn()`; True when it refuses (RefusalError) or `check(result)` holds (a rejected pair)."""
    from bench.p426_verify import RefusalError
    try:
        out = fn()
    except RefusalError:
        return True
    return bool(check(out))


def run_cli(module, args, rows_root, *, cwd=BENCH_DIR):
    env = {"PYTHONPATH": str(cwd), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "MLX_BENCH_RESULTS": str(rows_root),
           "HOME": str(rows_root), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    return subprocess.run([sys.executable, "-m", module, *map(str, args)], cwd=cwd, capture_output=True, text=True,
                          timeout=1800, env=env)


def all_cli(world, out_dir, *, b8_name="B8.json"):
    """Run `p426_verify all` then `p426_signals all` into `out_dir`; returns (r_verify, r_signals, b8, md, js)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    b8, md, js = out_dir / b8_name, out_dir / "SIGNALS.md", out_dir / "SIGNALS.json"
    r1 = run_cli("bench.p426_verify", ["all", "--results-root", world.p426, "--rows-root", world.rows_root, "--repo",
                                       world.repo, "--out", b8], world.rows_root)
    r2 = run_cli("bench.p426_signals", ["all", "--results-root", world.p426, "--rows-root", world.rows_root, "--b8", b8,
                                        "--out-md", md, "--out-json", js], world.rows_root) if r1.returncode == 0 else None
    return r1, r2, b8, md, js


def a1_vectors(on, off):
    """{id: score} dicts -> (ids, on_vals, off_vals) in sorted id order."""
    ids = sorted(on)
    return ids, [on[i] for i in ids], [off[i] for i in ids]


def a1_strict_diffs(w):
    """Both-block strict ON - OFF differences of A1, sorted by (block, id), derived from the world's own rows."""
    out = []
    for block in ("b1", "b2"):
        per = {}
        for arm in ("on", "off"):
            for r in w.read_rows("math500", arm, block):
                m = re.search(r"\\boxed\{([^}]*)\}", r["content"])
                ok = m is not None and m.group(1) == r["answer_gold"]
                per.setdefault(r["id"], {})[arm] = 1.0 if ok and r["converged"] is True else 0.0
        out += [per[i]["on"] - per[i]["off"] for i in sorted(per)]
    return out


def holm(ps):
    from bench import stats
    return stats.holm(list(ps))


def perm_p(diffs):
    from bench import p426_signals
    return p426_signals.permutation_p(list(diffs))


def sheet_text(sig) -> str:
    return json.dumps(sig, sort_keys=True, default=str)
