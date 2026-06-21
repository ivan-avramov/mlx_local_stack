"""NoLiMa-STYLE latent-association reasoning probe (self-authored; NOT the official NoLiMa
dataset — see the plan's Global Constraints re: the Adobe Research License). One needle
stating a fact about a named character is hidden in filler; the question refers to that fact
with NO lexical overlap, so answering requires a 1-hop world-knowledge inference (latent
reasoning), not a string match. Measures RELATIVE latent-reasoning depth across models."""
import random
import re

from .instrument import MemorySampler

FILLER = "The committee reviewed the quarterly figures and adjourned until the next session. "
LATENT_GRID = (8000, 16000, 24000, 32000, 48000, 64000)

# (needle template with {n} for the character name, question). The needle and question share
# NO content words; the link is world knowledge (landmark->country, symptom->profession, ...).
ASSOCIATIONS = [
    ("{n} has lived a block from the Colosseum for over a decade.", "Which character has spent time in Italy?"),
    ("{n} trains on the grass courts of southwest London every July.", "Which character likely plays at Wimbledon?"),
    ("{n} spends each shift checking patients' blood pressure and changing IV bags.", "Which character works in healthcare?"),
    ("{n} studies the rings and dozens of moons of the sixth planet from the sun.", "Which character researches Saturn?"),
    ("{n} replaces brake pads and timing belts on customers' cars all day.", "Which character works as a mechanic?"),
    ("{n} watched the sun circle the sky without ever setting last June.", "Which character was inside the Arctic Circle?"),
    ("{n} can recite the digits after the decimal point of pi to a hundred places.", "Which character is gifted at mathematics?"),
    ("{n} sailed past the green torch-bearing statue into the harbor at dawn.", "Which character arrived in New York?"),
    ("{n} tends the vines all summer and bottles the pressed harvest each autumn.", "Which character makes wine?"),
    ("{n} lands triple axels at the rink before most people are awake.", "Which character is a figure skater?"),
    ("{n} dusts the fossils and labels the assembled bones in the east gallery.", "Which character works at a museum?"),
    ("{n} reached the final camp below the world's highest summit last spring.", "Which character traveled to Nepal?"),
    ("{n} kneads dough at four in the morning and pulls warm loaves from the oven.", "Which character is a baker?"),
    ("{n} plots the probe's trajectory and watches the re-entry burn from mission control.", "Which character works in aerospace?"),
    ("{n} lectures on supply curves and elasticity to first-year students.", "Which character teaches economics?"),
    ("{n} hauls in crab pots off the coast in freezing pre-dawn swells.", "Which character is a fisher?"),
    ("{n} files the appellate brief the night before oral arguments.", "Which character is a lawyer?"),
    ("{n} tunes the timpani and counts rests at the back of the orchestra.", "Which character is a percussionist?"),
]

NAMES = ["Mara", "Theo", "Lena", "Bruno", "Cassia", "Idris", "Petra", "Soren", "Dario",
         "Nadia", "Olwen", "Tamsin", "Kiran", "Esme", "Rafe", "Zofia", "Hugo", "Ingrid"]


def build_latent(target_tokens: int, chars_per_token: float,
                 seed: int = 0) -> tuple[str, str, str]:
    """Embed one latent needle at ~mid-depth in filler. Returns (context, answer_name,
    question). The filler is fixed prose that contains none of the candidate NAMES, so the
    answer name is the only character in the context (unambiguous)."""
    rng = random.Random(seed)
    needle_tpl, question = ASSOCIATIONS[rng.randrange(len(ASSOCIATIONS))]
    name = NAMES[rng.randrange(len(NAMES))]
    needle = needle_tpl.format(n=name)

    target_chars = int(target_tokens * chars_per_token)
    filler = FILLER * (target_chars // len(FILLER) + 2)
    chars = list(filler[:target_chars])
    pos = min(int(target_chars * 0.5), len(chars) - 1)   # mid-depth
    chars[pos:pos] = list(f" {needle} ")
    context = "".join(chars)

    q = (f"{question} Use only the document above. "
         f"End your answer with 'ANSWER: <first name>'.")
    return context, name, q


def score_latent(response: str, answer_name: str) -> float:
    """1.0 if the answer name is returned. Prefer an 'ANSWER: <name>' tag; else whole-word,
    case-insensitive match anywhere in the response."""
    if not response:
        return 0.0
    m = re.search(r"ANSWER:\s*([A-Za-z]+)", response, re.IGNORECASE)
    if m:
        return 1.0 if m.group(1).lower() == answer_name.lower() else 0.0
    return 1.0 if re.search(rf"\b{re.escape(answer_name)}\b", response, re.IGNORECASE) else 0.0


def run_latent_ladder(driver, model, chars_per_token, model_pid, params,
                      grid=LATENT_GRID, threshold: float = 0.85, samples: int = 5,
                      extend_step: int = 8000, max_ctx: int = 131072,
                      sampler_factory=MemorySampler) -> list[dict]:
    """CLIMB-TO-CLIFF + AUTO-EXTEND (same control flow as run_aggregation_ladder). Each trial
    draws a distinct (association, name) by seed. `params` forwarded verbatim. Returns per-rung
    dicts {ctx, accuracy, samples, errors}."""
    records: list[dict] = []
    ladder = list(grid)
    i = 0
    while i < len(ladder):
        ctx_len = ladder[i]
        scores, errors = [], 0
        for trial in range(samples):
            seed = ctx_len * 1000 + trial
            context, name, question = build_latent(ctx_len, chars_per_token, seed=seed)
            messages = [{"role": "user", "content": context + "\n\n" + question}]
            with sampler_factory(pid=model_pid):
                try:
                    result = driver.complete(model, messages, params)
                    scores.append(score_latent(result.get("content", ""), name))
                except Exception:  # noqa: BLE001
                    scores.append(0.0)
                    errors += 1
        accuracy = sum(scores) / len(scores) if scores else 0.0
        records.append({"ctx": ctx_len, "accuracy": round(accuracy, 3),
                        "samples": samples, "errors": errors})
        if accuracy < threshold:
            break
        if i == len(ladder) - 1 and ctx_len + extend_step <= max_ctx:
            ladder.append(ctx_len + extend_step)
        i += 1
    return records
