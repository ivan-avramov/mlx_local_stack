"""Loop-shape measurement: the minimal repeating suffix of a trace, and a language-mixing guard.

WHY THIS EXISTS. The queued `presence_penalty` diagnostic asks ONE question — does the penalty break the
verbatim cycle? — and pass@1 cannot answer it: degenerate rows PASS more often than they fail (measured
2026-08-16: 6 of 10 degenerate coding rows still passed their plus-tests). So the endpoint has to be the
loop itself, measured, not eyeballed from a trace tail.

It also decides REACHABILITY in advance. `make_presence_penalty` has `context_size` 20 and is
binary-on-presence, so it can only suppress a cycle whose period is <= ~20 tokens: beyond that the prior
occurrence has fallen out of the window and the penalty on the next token is EXACTLY ZERO, not merely
smaller. A cycle's period in TOKENS is therefore the single number that says whether the lever can touch
a given row at all — and it must be counted with the model's own tokenizer, because character length is
not proportional to token count on repeated punctuation (a 3-character `' g,'` cycle is 2 tokens).

Measured on the corpus with this module: of 54 classifiable non-converged rows, 17 have a period <= 20
tokens and ALL 17 are on ifeval — zero on humanevalplus or mbppplus, where periods run 40-262.

The language-mixing guard is here because it is the vendor's documented failure mode for this knob
("using a higher value may occasionally result in language mixing and a slight decrease in model
performance"), and the corpus already contains its end state — a `gemma-4-31B-it-qat-6bit` row that is
multilingual token salad, produced with NO penalty at all. So the guard measures the rate rather than
assuming the penalty caused any instance of it.
"""
from __future__ import annotations

import unicodedata


def minimal_repeating_suffix(text: str, min_reps: int = 3, max_period_chars: int = 4000) -> dict:
    """The shortest string whose repetition forms the tail of `text`, or None.

    Returns {"period_chars", "reps", "cycle"} for the SHORTEST period that repeats at least
    `min_reps` times at the very end of the text. Shortest-first matters: a 2-character cycle also
    repeats as a 4-character one, and the shortest is the one the penalty window is compared against.

    FAILURE MODE, stated because it bounds what this can conclude: this finds only EXACT cycles. A loop
    that varies — a template with an incrementing counter, or a re-derivation that restates in different
    words — has no exact repeating suffix and returns None. That is not a measurement error, it is the
    distinction that matters: such a loop is unreachable by ANY presence penalty, because every token is
    novel at the moment of emission. Measured on the corpus: 19 of 54 non-converged rows are in this
    class.
    """
    if not text:
        return {"period_chars": None, "reps": 0, "cycle": None}
    n = len(text)
    for period in range(1, min(max_period_chars, n // min_reps) + 1):
        cycle = text[n - period:]
        reps = 1
        while (n - (reps + 1) * period) >= 0 and text[n - (reps + 1) * period: n - reps * period] == cycle:
            reps += 1
        if reps >= min_reps:
            return {"period_chars": period, "reps": reps, "cycle": cycle}
    return {"period_chars": None, "reps": 0, "cycle": None}


def period_tokens(cycle: str, tokenizer=None, copies: int = 8) -> int | None:
    """Token length of one cycle, measured by tokenising `copies` concatenated copies and dividing.

    Tokenising ONE copy overstates short cycles: leading-space and BOS handling make `' g,'` look like
    3 tokens in isolation when it costs 2 per iteration in a stream. Dividing a long concatenation
    recovers the steady-state cost, which is what the 20-token window is actually compared against.

    Returns None when no tokenizer is available, rather than guessing from characters — the whole point
    of this function is that characters are not proportional to tokens here.
    """
    if not cycle or tokenizer is None:
        return None
    ids = tokenizer.encode(cycle * copies, add_special_tokens=False) \
        if hasattr(tokenizer, "encode") else None
    if not ids:
        return None
    return max(1, round(len(ids) / copies))


def reachable_by_presence_penalty(period_tok: int | None, context_size: int = 20) -> bool | None:
    """Whether a presence penalty with this window can see the cycle at all.

    None = unknowable (no exact cycle, or no tokenizer), which is NOT the same as False and must not be
    reported as such: an unmeasured row is not an unreachable one.
    """
    if period_tok is None:
        return None
    return period_tok <= context_size


def non_latin_rate(text: str) -> float:
    """Fraction of alphabetic characters outside the Latin script — the language-mixing guard.

    Counts only letters, so code punctuation and digits do not dilute it. A degenerate-but-monolingual
    loop scores ~0; the observed token-salad failure scores high. Report the RATE and compare arms;
    never treat a nonzero value as proof the penalty caused it, since the corpus contains an instance
    produced with no penalty at all.
    """
    letters = [c for c in (text or "") if c.isalpha()]
    if not letters:
        return 0.0
    non_latin = sum(1 for c in letters if "LATIN" not in unicodedata.name(c, ""))
    return non_latin / len(letters)


def describe(text: str, tokenizer=None, context_size: int = 20) -> dict:
    """Full loop-shape record for one trace — the per-row endpoint of the penalty diagnostic."""
    m = minimal_repeating_suffix(text)
    ptok = period_tokens(m["cycle"], tokenizer) if m["cycle"] else None
    return {
        "period_chars": m["period_chars"], "reps": m["reps"],
        "cycle_preview": (m["cycle"] or "")[:60],
        "period_tokens": ptok,
        "reachable": reachable_by_presence_penalty(ptok, context_size),
        "non_latin_rate": round(non_latin_rate(text), 4),
        "chars": len(text or ""),
    }
