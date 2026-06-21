"""Multi-needle retrieval probe: one unique code per depth, a single query asking
for all of them (multi-key NIAH). Generalizes needle_256k.py so one prefill scores
retrieval across the whole context. Score = fraction of codes returned.

Two consumers:
- capacity_ladder.py uses build_context/make_question/score for the rough memory-probe
  co-signal (bounded generation, thinking-starved by design).
- run_retrieval.py drives the dedicated retrieval CURVE at production params (full
  thinking) via run_retrieval_ladder — the authoritative retrieval-effective-length.
"""
import random
import string

FILLER = "The quick brown fox jumps over the lazy dog near the riverbank at sunset. "
DEPTHS = (0.1, 0.3, 0.5, 0.7, 0.9)

_NEEDLE_LEN = 8
_ALPHABET = string.ascii_uppercase + string.digits  # never appears in the lowercase filler


def _make_needles(rng: random.Random, n: int) -> list[str]:
    """n distinct fixed-length uppercase/digit tokens. Equal length => none is a
    substring of another; uppercase/digit => never collides with the lowercase filler."""
    needles: list[str] = []
    used: set[str] = set()
    while len(needles) < n:
        cand = "".join(rng.choice(_ALPHABET) for _ in range(_NEEDLE_LEN))
        if cand not in used:
            used.add(cand)
            needles.append(cand)
    return needles


def build_context(target_tokens: int, chars_per_token: float,
                  depths=DEPTHS, seed: int = 0) -> tuple[str, list[str]]:
    """Build a multi-needle context. `seed` randomizes the needle tokens so repeated
    trials at one context length are not degenerate; depths are fixed (the positional
    curve is the measurement). Needles are returned in ascending-depth order and
    inserted deepest-first so earlier inserts don't shift later offsets."""
    rng = random.Random(seed)
    target_chars = int(target_tokens * chars_per_token)
    filler = FILLER * (target_chars // len(FILLER) + 2)
    needles = _make_needles(rng, len(depths))
    chars = list(filler[:target_chars])
    for i in sorted(range(len(depths)), key=lambda k: depths[k], reverse=True):
        pos = min(int(target_chars * depths[i]), len(chars) - 1)
        sentence = f" The secret code number {i} is {needles[i]}. "
        chars[pos:pos] = list(sentence)
    return "".join(chars), needles


def make_question(needles: list[str]) -> str:
    return (f"The document above contains {len(needles)} secret codes, each stated once. "
            f"List all {len(needles)} codes, separated by commas. Output only the codes.")


def hits(response_text: str, needles: list[str]) -> list[bool]:
    """Per-needle presence (substring match), in needle order."""
    text = response_text or ""
    return [n in text for n in needles]


def score(response_text: str, needles: list[str]) -> float:
    if not needles:
        return 0.0
    return sum(hits(response_text, needles)) / len(needles)
