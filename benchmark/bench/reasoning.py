"""RULER-style variable-tracking task: multi-hop reasoning probe.

The canonical multi-hop test: a chain of variable assignments is hidden in a
long filler context. The model must trace the chain from the final variable back
to the original numeric value. This tests multi-hop reasoning, not just retrieval.
"""
import random
import re

from .instrument import MemorySampler

FILLER = "The quick brown fox jumps over the lazy dog near the riverbank at sunset. "

REASONING_GRID = (8000, 16000, 24000, 32000, 48000, 64000)


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def build_vartrack(
    target_tokens: int,
    chars_per_token: float,
    chain_len: int = 4,
    seed: int = 0,
) -> tuple[str, str, str]:
    """Build a variable-tracking context, answer, and question.

    Returns (context, answer, question):
      - context: filler text with `chain_len` assignment statements embedded at
        evenly-spaced depths (deepest-first insertion so earlier inserts don't
        shift later offsets).
      - answer: str(val) — the numeric value that every variable in the chain
        ultimately resolves to.
      - question: asks the model to trace the assignments and emit the final
        value in the form  "ANSWER: <number>".
    """
    rng = random.Random(seed)

    # Pick the root numeric value
    val = rng.randint(10000, 99999)

    # Generate uniquely-named variables
    names = []
    used = set()
    for i in range(chain_len):
        while True:
            candidate = f"VAR{rng.randint(1000, 9999)}x{i}"
            if candidate not in used:
                used.add(candidate)
                names.append(candidate)
                break

    # Build the assignment statements
    # stmt0: name0 = val
    # stmt_i: name_i = name_{i-1}   (for i >= 1)
    stmts = [f"{names[0]} = {val}."]
    for i in range(1, chain_len):
        stmts.append(f"{names[i]} = {names[i-1]}.")

    # Build filler to the target character count
    target_chars = int(target_tokens * chars_per_token)
    filler = FILLER * (target_chars // len(FILLER) + 2)
    chars = list(filler[:target_chars])

    # Insertion depths: (i+1)/(chain_len+1) for i in 0..chain_len-1
    depths = [(i + 1) / (chain_len + 1) for i in range(chain_len)]

    # Insert deepest-first so earlier inserts don't shift later offsets
    for i in sorted(range(chain_len), key=lambda k: depths[k], reverse=True):
        pos = min(int(target_chars * depths[i]), len(chars) - 1)
        sentence = f" {stmts[i]} "
        chars[pos:pos] = list(sentence)

    context = "".join(chars)
    answer = str(val)
    last_name = names[-1]
    question = (
        f"Trace the variable assignments in the document. "
        f"What is the final numeric value of {last_name}? "
        f"End your answer with 'ANSWER: <number>'."
    )
    return context, answer, question


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

def score_vartrack(response: str, answer: str) -> float:
    """Return 1.0 if response contains the correct answer, else 0.0.

    Strategy:
    1. If "ANSWER:" appears in the response, extract the number immediately
       following it and compare — this takes priority.
    2. Otherwise, check if `answer` appears among the 4+ digit numbers in the
       response body.
    """
    if not response:
        return 0.0

    # Priority: look for "ANSWER: <number>"
    m = re.search(r'ANSWER:\s*(\d+)', response, re.IGNORECASE)
    if m:
        return 1.0 if m.group(1) == answer else 0.0

    # Fallback: scan all 4+ digit numbers in the response
    numbers = re.findall(r'\b(\d{4,})\b', response)
    return 1.0 if answer in numbers else 0.0


# ---------------------------------------------------------------------------
# Ladder runner
# ---------------------------------------------------------------------------

def run_reasoning_ladder(
    driver,
    model: str,
    chars_per_token: float,
    model_pid,
    grid=REASONING_GRID,
    threshold: float = 0.85,
    samples: int = 5,
    chain_len: int = 4,
    max_tokens: int = 4096,
    thinking_budget: int = 2048,
    sampler_factory=MemorySampler,
) -> list[dict]:
    """CLIMB-TO-CLIFF: run the variable-tracking task at increasing context sizes.

    For each length L in grid, runs `samples` independent trials (each with a
    distinct seed = L * 1000 + trial_index). Accuracy = mean of trial scores.
    Stops (breaks) after the first rung with accuracy < threshold.

    Returns a list of per-rung dicts:
      {"ctx": L, "accuracy": float, "samples": N, "chain_len": N, "errors": N}
    """
    records = []
    for ctx_len in grid:
        scores = []
        errors = 0
        for trial in range(samples):
            seed = ctx_len * 1000 + trial
            context, answer, question = build_vartrack(
                ctx_len, chars_per_token, chain_len=chain_len, seed=seed
            )
            messages = [
                {"role": "user", "content": context + "\n\n" + question}
            ]
            params = {
                "max_tokens": max_tokens,
                "temperature": 0.0,
                "thinking_budget": thinking_budget,
            }
            with sampler_factory(pid=model_pid):
                try:
                    result = driver.complete(model, messages, params)
                    content = result.get("content", "")
                    sc = score_vartrack(content, answer)
                except Exception:
                    sc = 0.0
                    errors += 1
            scores.append(sc)

        accuracy = sum(scores) / len(scores) if scores else 0.0
        records.append({
            "ctx": ctx_len,
            "accuracy": round(accuracy, 3),
            "samples": samples,
            "chain_len": chain_len,
            "errors": errors,
        })
        if accuracy < threshold:
            break

    return records
