"""Verify an archived convergence result actually used the requested config — ALL knobs.

Supersedes /tmp/tier0_check.py, which verified only temperature and min_p. That was enough for
the first grid but is NOT enough now: the 2026-08-13 re-scope turns on holding top_p/top_k at the
DEPLOYED values, because the untruncated path (top_p 1.0 / top_k 0 / min_p 0.0) is nondeterministic
under suffix decoding (3 identical requests -> 3 different outputs, 1.6x length spread). A checker
blind to top_p/top_k would happily pass a cell that had silently reverted to the untruncated path,
which is precisely the failure it exists to catch.

Also verifies presence_penalty is 0.0: a nonzero value DISABLES suffix decoding, so the cell would
measure a different serving path rather than a different distribution.

  tier0b_check.py <result.json> temp=0.4 min_p=0.05 top_p=0.95 top_k=20
"""
import json
import sys

EXPECT_ALWAYS = {"presence_penalty": 0.0}


def main(argv):
    if len(argv) < 3:
        print("usage: tier0b_check.py <result.json> KEY=VAL ...", file=sys.stderr)
        return 2
    d = json.load(open(argv[1]))
    p = d.get("params") or {}
    want = dict(EXPECT_ALWAYS)
    for kv in argv[2:]:
        k, v = kv.split("=", 1)
        want[k] = float(v)

    print("    output params: " + " ".join(
        f"{k}={p.get(k)}" for k in
        ("temperature", "min_p", "top_p", "top_k", "presence_penalty", "thinking_budget")))

    bad = []
    for k, v in want.items():
        got = p.get(k)
        if got is None or abs(float(got) - v) > 1e-9:
            bad.append(f"{k}: want {v}, got {got}")
    # thinking_budget must stay at its GENEROUS fixed headroom -- AGENTS.md forbids using it as a
    # tuning knob, and a cell that quietly lowered it would manufacture non-convergence.
    if p.get("thinking_budget") != 81920:
        bad.append(f"thinking_budget: want 81920 (fixed headroom), got {p.get('thinking_budget')}")
    if p.get("max_tokens") != 102400:
        bad.append(f"max_tokens: want 102400, got {p.get('max_tokens')}")

    if bad:
        for b in bad:
            print(f"    !!! PARAM MISMATCH {b}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
