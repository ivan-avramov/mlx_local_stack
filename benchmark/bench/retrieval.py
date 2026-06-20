"""Multi-needle retrieval probe: one unique code per depth, a single query asking
for all of them (multi-key NIAH). Generalizes needle_256k.py so one prefill scores
retrieval across the whole context. Score = fraction of codes returned."""
FILLER = "The quick brown fox jumps over the lazy dog near the riverbank at sunset. "
DEPTHS = (0.1, 0.3, 0.5, 0.7, 0.9)


def _needle(i: int) -> str:
    # Non-natural tokens that won't appear in filler; distinct per depth.
    return f"XKRZ{i}{'ABCDEFGHJK'[i]}7Q"


def build_context(target_tokens: int, chars_per_token: float,
                  depths=DEPTHS) -> tuple[str, list[str]]:
    target_chars = int(target_tokens * chars_per_token)
    filler = FILLER * (target_chars // len(FILLER) + 2)
    needles = [_needle(i) for i in range(len(depths))]
    # Insert from deepest to shallowest so earlier inserts don't shift later offsets.
    chars = list(filler[:target_chars])
    for i in sorted(range(len(depths)), key=lambda k: depths[k], reverse=True):
        pos = min(int(target_chars * depths[i]), len(chars) - 1)
        sentence = f" The secret code number {i} is {needles[i]}. "
        chars[pos:pos] = list(sentence)
    return "".join(chars), needles


def make_question(needles: list[str]) -> str:
    return (f"The document above contains {len(needles)} secret codes, each stated once. "
            f"List all {len(needles)} codes, separated by commas. Output only the codes.")


def score(response_text: str, needles: list[str]) -> float:
    if not needles:
        return 0.0
    return sum(1 for n in needles if n in (response_text or "")) / len(needles)
