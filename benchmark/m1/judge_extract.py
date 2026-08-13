#!/usr/bin/env python3
"""Extract BOTH-SOLVE paired solutions and build blind judge packets (panel v3).

Design decisions, each with its reason:

* BOTH-SOLVE ONLY. AGENTS.md restricts the judge to execution-PASSING outputs and forbids using
  it as a correctness oracle. Judging a passing solution against a failing one smuggles
  correctness back into a "quality" score; holding correctness constant is the point.
* RAN-FILTERED. aider writes a .aider.results.json for every exercise it SETS UP, with
  tests_outcomes: [] until the case executes. A file-count filter reported 22 for a batch that
  ran 1 (distill/java, m1f). Only non-empty tests_outcomes count.
* REFERENCE-GUIDED. Every exercise ships .meta/example* (or proof*). Supplying it as a
  calibration anchor raised order-consistency from 55% (v1, no reference) to 71% (v2, Opus
  holistic). It is passed with an explicit instruction NOT to reward similarity to it.
* BLIND + COUNTERBALANCED. A/B assignment per exercise from a blake2b of the exercise name
  (reproducible, no RNG). Every packet is emitted in both orders; position bias is the
  best-documented failure mode of pairwise LLM judging (MT-Bench: 10-15pp winrate swing), so it
  is measured rather than assumed.
* ROLE PROMPTS ARE NOT THE DEFAULT. v2 measured narrow role prompts as WORSE than holistic
  (maintainability 42% order-consistency vs holistic 71%). Roles are kept only as evidence
  GATHERERS for the meta-judge, never as voters in a flat majority.

Usage:
  judge_extract.py --tag m1f --out /tmp/judge3            # extract + Sonnet role packets
  judge_extract.py --tag m1f --out /tmp/judge3 --meta     # + Opus meta packet from verdicts
"""
import argparse
import glob
import hashlib
import json
import os

ROLES = {
    "maintainability": (
        "maintainability reviewer",
        "You care ONLY about the cost of living with this code six months from now: can a new\n"
        "engineer read it, locate behaviour, and change it safely? Ignore cleverness and performance.",
        ["naming", "readability", "cognitive_load", "ease_of_safe_change"],
    ),
    "architecture": (
        "architecture / design reviewer",
        "You care ONLY about structure: decomposition, cohesion and coupling, where invariants and\n"
        "error handling live, and whether the code uses the language's proper affordances.",
        ["decomposition", "cohesion_coupling", "error_handling_structure", "idiom_api_fit"],
    ),
}

HDR = """# Blind code-quality comparison ({role})

{n} programming exercises. Each has TWO independent solutions (A and B) plus the exercise's
OFFICIAL REFERENCE SOLUTION.

GROUND RULES
- Both A and B ALREADY PASS the exercise's complete official test suite. Correctness is settled.
  Do NOT re-verify it, do NOT hunt for hypothetical bugs, do NOT reward defensive-looking code.
- The REFERENCE is a calibration anchor only. It is one idiomatic solution, not a target: a
  solution may legitimately be better than the reference. Do NOT reward similarity to it.
- Length is not quality. Do not prefer a solution for being longer or shorter.
- You do not know who or what wrote A or B. Do not speculate about authorship or tooling.
- A and B are equally likely to be better. Ties are legitimate and expected when genuinely close.

YOUR ROLE: {desc}

SCORE EACH SOLUTION on these dimensions, 1-5 (1 = seriously deficient, 3 = acceptable,
5 = exemplary):
{dims}
"""


def _ran(exdir):
    try:
        t = json.load(open(f"{exdir}/.aider.results.json")).get("tests_outcomes") or []
    except Exception:
        return None
    return bool(t[-1]) if t else None          # None = never ran


def _solution(exdir):
    try:
        names = json.load(open(f"{exdir}/.meta/config.json"))["files"]["solution"]
    except Exception:
        return None
    out = []
    for f in names:
        p = os.path.join(exdir, f)
        if not os.path.exists(p):
            return None
        out.append((f, open(p, errors="replace").read()))
    return out


def _reference(exdir):
    for pat in ("example*", "proof*"):
        for p in sorted(glob.glob(f"{exdir}/.meta/{pat}")):
            if os.path.isfile(p) and not p.endswith(".json"):
                return (os.path.basename(p), open(p, errors="replace").read())
    return None


def extract(bm, tag, arms=("ornith", "distill"),
            langs=("python", "javascript", "go", "rust", "java")):
    pairs, key = [], {}
    for lang in langs:
        dirs = {}
        for arm in arms:
            dirs[arm] = {os.path.basename(d): d
                         for d in glob.glob(f"{bm}/*{tag}-{arm}-{lang}/{lang}/exercises/practice/*")}
        for name in sorted(set(dirs[arms[0]]) & set(dirs[arms[1]])):
            a, b = dirs[arms[0]][name], dirs[arms[1]][name]
            if not (_ran(a) and _ran(b)):        # both must have RUN and PASSED
                continue
            sa, sb, ref = _solution(a), _solution(b), _reference(a)
            if not sa or not sb:
                continue
            first_is_arm0 = bool(hashlib.blake2b(f"{lang}/{name}".encode(),
                                                digest_size=8).digest()[0] & 1)
            pairs.append(dict(lang=lang, exercise=name, ref=ref,
                              A=sa if first_is_arm0 else sb,
                              B=sb if first_is_arm0 else sa))
            key[f"{lang}/{name}"] = dict(
                A=arms[0] if first_is_arm0 else arms[1],
                B=arms[1] if first_is_arm0 else arms[0],
                len_A=sum(len(c) for _, c in (sa if first_is_arm0 else sb)),
                len_B=sum(len(c) for _, c in (sb if first_is_arm0 else sa)))
    return pairs, key


def write_role_packets(pairs, out):
    for role, (short, desc, dims) in ROLES.items():
        for tag, swap in (("fwd", False), ("rev", True)):
            L = [HDR.format(role=short, n=len(pairs), desc=desc,
                            dims="\n".join(f"- {d}" for d in dims))]
            for i, p in enumerate(pairs, 1):
                a, b = (p["B"], p["A"]) if swap else (p["A"], p["B"])
                L.append(f"\n\n---\n\n## Item {i} — id `{p['lang']}/{p['exercise']}`\n")
                if p["ref"]:
                    fn, code = p["ref"]
                    L.append(f"\n### REFERENCE (anchor, not a target)\n`{fn}`\n"
                             f"```\n{code.rstrip()}\n```\n")
                for lbl, sol in (("A", a), ("B", b)):
                    L.append(f"\n### Solution {lbl}\n")
                    for fname, code in sol:
                        ext = fname.rsplit(".", 1)[-1]
                        L.append(f"\n`{fname}`\n```{ext}\n{code.rstrip()}\n```\n")
            path = f"{out}/packet_{role}_{tag}.md"
            open(path, "w").write("\n".join(L))
            print(f"  {path}  items={len(pairs)} dims={dims}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bm", default=os.path.expanduser("~/ws/aider/benchmark/tmp.benchmarks"))
    ap.add_argument("--tag", default="m1f")
    ap.add_argument("--out", default="/tmp/judge3")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    pairs, key = extract(a.bm, a.tag)
    json.dump(key, open(f"{a.out}/KEY.json", "w"), indent=2)
    json.dump(pairs, open(f"{a.out}/pairs.json", "w"), indent=2)
    n_a = sum(1 for v in key.values() if v["A"] == "ornith")
    print(f"both-solve pairs: {len(pairs)}   blind balance: A=ornith on {n_a}/{len(key)}")
    print(f"  with reference: {sum(1 for p in pairs if p['ref'])}/{len(pairs)}")
    write_role_packets(pairs, a.out)
    print(f"  KEY.json written to {a.out} and is NOT in any packet")


if __name__ == "__main__":
    main()
