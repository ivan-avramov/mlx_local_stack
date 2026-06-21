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

from .instrument import MemorySampler

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


def hits(response_text: str | None, needles: list[str]) -> list[bool]:
    """Per-needle presence (substring match), in needle order."""
    text = response_text or ""
    return [n in text for n in needles]


def score(response_text: str, needles: list[str]) -> float:
    if not needles:
        return 0.0
    return sum(hits(response_text, needles)) / len(needles)


RETRIEVAL_GRID = (8000, 32000, 64000, 128000, 192000, 256000)


def run_retrieval_ladder(driver, model, chars_per_token, model_pid, params,
                         grid=RETRIEVAL_GRID, threshold: float = 0.85, samples: int = 5,
                         depths=DEPTHS, sampler_factory=MemorySampler) -> list[dict]:
    """FULL CURVE (not climb-to-cliff): run multi-needle retrieval at every context
    length in `grid`. Retrieval can be non-monotonic (a model may dip mid-context and
    recover), so — unlike run_reasoning_ladder — a rung below threshold does NOT stop
    the ladder. Only a HARD failure (every trial at a rung raises => errors == samples,
    which at long context means OOM/disconnect) stops it, because larger contexts will
    also fail.

    For each rung, runs `samples` trials with distinct needle seeds (seed = ctx*1000 +
    trial). `params` is forwarded verbatim to driver.complete — this is a quality
    measurement, so full production params (incl. thinking_budget) are used unbounded.

    Returns per-rung dicts: {"ctx", "accuracy", "per_depth_acc", "samples", "needles",
    "errors"} where accuracy is the mean fraction of needles returned across trials and
    per_depth_acc[d] is the hit rate at depth d across trials.
    """
    records: list[dict] = []
    n_dep = len(depths)
    for ctx_len in grid:
        trial_hits: list[list[bool]] = []
        errors = 0
        for trial in range(samples):
            seed = ctx_len * 1000 + trial
            context, needles = build_context(ctx_len, chars_per_token,
                                             depths=depths, seed=seed)
            messages = [{"role": "user",
                         "content": context + "\n\n" + make_question(needles)}]
            with sampler_factory(pid=model_pid):
                try:
                    result = driver.complete(model, messages, params)
                    trial_hits.append(hits(result.get("content", ""), needles))
                except Exception:  # noqa: BLE001 — OOM/disconnect at this ctx
                    trial_hits.append([False] * n_dep)
                    errors += 1
        accuracy = sum(sum(h) / n_dep for h in trial_hits) / len(trial_hits)
        per_depth_acc = [round(sum(h[d] for h in trial_hits) / len(trial_hits), 3)
                         for d in range(n_dep)]
        records.append({"ctx": ctx_len, "accuracy": round(accuracy, 3),
                        "per_depth_acc": per_depth_acc, "samples": samples,
                        "needles": n_dep, "errors": errors})
        # NB: threshold is NOT a stop condition here — full curve by design (the CLI uses it for effective_ctx).
        if errors == samples:  # hard failure (OOM) at this ctx; larger will also fail
            break
    return records
