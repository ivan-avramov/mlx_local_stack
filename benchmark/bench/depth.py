"""Coding-at-depth: embed an execution-gated task at the end of N tokens of repo context.

The axis (D9): same items, same grader, one added condition — the prompt arrives at DEPTH,
preceded by `depth_tokens` worth of deterministic, realistic-looking Python modules. Because
the padding is a pure function of (item id, target), the shallow and depth arms are paired
row-for-row and every model sees identical context (common random numbers).

V1 measures generation quality under a long attention window ONLY: the padding is inert
background the task never references, so retrieval demand stays on its own axis (the
methodology's retrieval-depth / reasoning-depth separation). A planned v2 places helpers
the solution must actually use at controlled depths — do not bolt that on here without a
design pass, it changes what the number means.

`depth_tokens` is PROVENANCE (fingerprint sampling slice + compare must-match): two runs at
different depths answered different questions and must never pool or resume together.
"""
import hashlib
import random

# Estimation only. The authoritative depth of a row is its measured prompt_tokens; this
# constant just aims the builder. ~3.5 chars/token is typical for dense Python under the
# Qwen-family tokenizers this campaign serves.
CHARS_PER_TOKEN = 3.5

_WORDS = ("batch", "cache", "chunk", "config", "cursor", "delta", "digest", "entry",
          "frame", "graph", "handle", "index", "job", "key", "layer", "merge", "node",
          "offset", "page", "pool", "queue", "record", "route", "schema", "shard",
          "slot", "state", "stream", "table", "token", "trace", "value", "window")


def _module(rng: random.Random, mod_i: int) -> str:
    """One plausible Python module: header comment, a few functions with docstrings."""
    name = f"{rng.choice(_WORDS)}_{rng.choice(_WORDS)}"
    lines = [f"# ---- repo file {mod_i}: {name}.py ----",
             f'"""Utilities for {name.replace("_", " ")} management."""', ""]
    for _ in range(rng.randint(3, 6)):
        fn = f"{rng.choice(_WORDS)}_{rng.choice(_WORDS)}"
        a, b = rng.choice(_WORDS), rng.choice(_WORDS)
        thresh, scale = rng.randint(2, 97), rng.randint(2, 9)
        lines += [
            f"def {fn}({a}, {b}=None):",
            f'    """Combine {a} with {b}, clamping at {thresh}."""',
            f"    if {b} is None:",
            f"        {b} = {a} * {scale} % {thresh}",
            f"    total = sum(({a}, {b})) if isinstance({a}, int) else len(str({a})) + {b}",
            f"    return min(total, {thresh})",
            "",
        ]
    return "\n".join(lines)


def padding(target_tokens: int, item_id: str) -> str:
    """Deterministic repo-like Python source of ~target_tokens (estimated)."""
    seed = int.from_bytes(hashlib.sha256(f"depth:{item_id}".encode()).digest()[:8], "big")
    rng = random.Random(seed)
    target_chars = int(target_tokens * CHARS_PER_TOKEN)
    parts, size, mod_i = [], 0, 0
    while size < target_chars:
        m = _module(rng, mod_i)
        parts.append(m)
        size += len(m) + 2
        mod_i += 1
    return "\n\n".join(parts)[:target_chars]


_HEADER = ("You are working inside a large repository. The files below are repository "
           "context: read them as background only — the actual task follows after them.\n\n")
_FOOTER = ("\n\n---- end of repository context ----\n"
           "The task now follows. Ignore the context files above unless the task itself "
           "refers to them.\n\n")


def wrap_messages(messages: list, depth_tokens, item_id: str) -> list:
    """Prepend padding to the (single) user message; identity when depth is falsy."""
    if not depth_tokens:
        return messages
    out = [dict(m) for m in messages]
    for m in out:
        if m.get("role") == "user":
            m["content"] = _HEADER + padding(depth_tokens, item_id) + _FOOTER + m["content"]
            break
    return out
