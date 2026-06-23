"""RULER-style aggregation probe: common-words extraction (CWE).

The context is a long shuffled stream of words in which `k` TARGET words each appear
`freq_common` times and many DISTRACTOR words each appear `freq_uncommon` (< freq_common)
times. To answer, the model must AGGREGATE frequencies across the WHOLE context and return
the k most frequent words — this tests aggregation, not single-needle retrieval. Words are
synthetic pronounceable pseudo-tokens so the pool scales to any context length and never
collides with a real-word prior."""
import random
import re

from .instrument import MemorySampler

AGG_GRID = (8000, 16000, 24000, 32000, 48000, 64000)

_CONS = "bcdfghjklmnprstvw"
_VOWELS = "aeiou"


def _word(rng: random.Random) -> str:
    """A 2-3 syllable lowercase pseudo-word (CV/CVC syllables)."""
    syl = rng.randint(2, 3)
    return "".join(rng.choice(_CONS) + rng.choice(_VOWELS) +
                   (rng.choice(_CONS) if rng.random() < 0.4 else "") for _ in range(syl))


def _distinct_words(rng: random.Random, n: int) -> list[str]:
    out, seen = [], set()
    while len(out) < n:
        w = _word(rng)
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def build_cwe(target_tokens: int, chars_per_token: float, k: int = 5,
              freq_common: int = 30, freq_uncommon: int = 3,
              seed: int = 0, n_distractor: int = None) -> tuple[str, list[str], str]:
    """Build a CWE context. Targets appear freq_common times, distractors freq_uncommon
    times; total occurrences fill ~target_tokens. Returns (context, targets, question).

    If ``n_distractor`` is given, the ENUMERATION LOAD (number of distinct distractor words
    to tally) is set directly and ``target_tokens`` is ignored. This is how the graded probe
    dials difficulty — the count of distinct words, which is what blows the thinking budget —
    independently of raw context length, to find each model's enumeration cliff."""
    rng = random.Random(seed)
    if n_distractor is None:
        # Estimate total word slots from the char budget (avg pseudo-word ~5 chars + 1 space).
        total_chars = int(target_tokens * chars_per_token)
        total_words = max(k * freq_common + 1, total_chars // 6)
        n_distractor = max(1, (total_words - k * freq_common) // freq_uncommon)
    pool = _distinct_words(rng, k + n_distractor)
    targets = pool[:k]
    distractors = pool[k:]
    stream = []
    for t in targets:
        stream += [t] * freq_common
    for d in distractors:
        stream += [d] * freq_uncommon
    rng.shuffle(stream)
    context = " ".join(stream)
    question = (f"The text above is a list of words. Identify the {k} words that appear "
                f"MOST frequently. Output only those {k} words, separated by commas.")
    return context, targets, question


def score_cwe(response: str, targets: list[str]) -> float:
    """Fraction of target words present in the response (whole-word, case-insensitive)."""
    if not targets:
        return 0.0
    text = (response or "").lower()
    hits = sum(1 for t in targets if re.search(rf"\b{re.escape(t.lower())}\b", text))
    return hits / len(targets)


def run_aggregation_ladder(driver, model, chars_per_token, model_pid, params,
                           grid=AGG_GRID, threshold: float = 0.85, samples: int = 5,
                           k: int = 5, freq_common: int = 30, freq_uncommon: int = 3,
                           extend_step: int = 8000, max_ctx: int = 131072,
                           sampler_factory=MemorySampler) -> list[dict]:
    """CLIMB-TO-CLIFF + AUTO-EXTEND: run CWE at each context length. Stop at the first rung
    below threshold (the cliff). If the top PLANNED rung still passes, keep extending in
    +extend_step steps until a rung fails or max_ctx is reached. `params` is forwarded
    verbatim (production quality params). Returns per-rung dicts {ctx, accuracy, samples,
    k, errors}."""
    records: list[dict] = []
    ladder = list(grid)
    i = 0
    while i < len(ladder):
        ctx_len = ladder[i]
        scores, errors = [], 0
        for trial in range(samples):
            seed = ctx_len * 1000 + trial
            context, targets, question = build_cwe(ctx_len, chars_per_token, k=k,
                                                    freq_common=freq_common,
                                                    freq_uncommon=freq_uncommon, seed=seed)
            messages = [{"role": "user", "content": context + "\n\n" + question}]
            with sampler_factory(pid=model_pid):
                try:
                    result = driver.complete(model, messages, params)
                    scores.append(score_cwe(result.get("content", ""), targets))
                except Exception:  # noqa: BLE001
                    scores.append(0.0)
                    errors += 1
        accuracy = sum(scores) / len(scores) if scores else 0.0
        records.append({"ctx": ctx_len, "accuracy": round(accuracy, 3),
                        "samples": samples, "k": k, "errors": errors})
        if accuracy < threshold:
            break  # cliff
        if i == len(ladder) - 1 and ctx_len + extend_step <= max_ctx:
            ladder.append(ctx_len + extend_step)  # still passing at the top => extend
        i += 1
    return records
