"""Non-convergence TRIAGE: how a thinking trace failed, and a compact form worth persisting.

`convergence.py` answers WHETHER a generation converged. It cannot say WHY, and the `generate`
path stores only the post-`</think>` answer — so the campaign's first DNF triage
(`Qwen3.6-27B-MLX-8bit light`) needed a bespoke capped-budget live re-probe just to learn which
KIND of failure it was. Persisting `trace_stats` + a head/tail excerpt per item makes the whole
corpus retroactively classifiable instead.

The distinction is decision-grade because the two documented classes have DIFFERENT fixes:
  - `degenerate_repetition` — gemma at temp 1.0: one line repeated 34-78x, unique-line ratio
    ~44%. A sampling/quant defect (and, per generate.py, worth a router-restart retry).
  - `meander` — Qwen3.6-27B-MLX-8bit on aime24-72: coherent step-by-step reasoning with 8-gram
    AND 20-gram uniqueness ~1.00, backtracking markers ("wait"x7, "actually"x3), re-deriving at
    length without concluding. It saturates the budget with genuinely NOVEL text, so no
    restart helps; the fix is the AGENTS.md temperature-ladder recipe (proven on the
    Opus-Distill, whose LCB "DNF" at t0.6 converged 15/15 at t0.3).

Nothing here is a knob for the model: the thinking budget is external truncation, so a class is
a DIAGNOSIS to act on, never something to "tune away" by raising the budget.
"""
import collections
import re

from . import convergence

# Repetition thresholds are convergence.looks_like_loop's, restated so this module can judge a
# PERSISTED trace_stats dict (no text in hand). Calibrated on campaign data: gemma loops had
# max-repeat 34-78 with ~44% unique; genuine Qwen traces had max-repeat <=23 with >=84% unique.
# Keep in lockstep with convergence.looks_like_loop (a test pins them to its signature defaults).
REPEAT_MIN_LINES = 20
REPEAT_MAX_REPEAT = 20
REPEAT_MIN_UNIQUE_RATIO = 0.6

# Meander = high novelty. The measured signature was ~1.00 8-gram uniqueness; 0.8 leaves room for
# a trace that genuinely re-quotes the problem statement while still exploring. The line-repeat
# half is belt-and-braces: both signals must agree before an operator is sent to the temp ladder.
MEANDER_MIN_NGRAM8_UNIQUE = 0.8

# "waiting" is not "wait" — \b keeps these whole words, and \s+ lets a phrase straddle a newline.
_MARKERS = {
    "wait": r"\bwait\b",
    "actually": r"\bactually\b",
    "hmm": r"\bhmm\b",
    "let me reconsider": r"\blet\s+me\s+reconsider\b",
}


def _lines(text) -> list:
    """Non-trivial lines only (>20 stripped chars) — convergence.looks_like_loop's convention, so
    the two modules never disagree about what a 'line' is."""
    return [ln.strip() for ln in (text or "").splitlines() if len(ln.strip()) > 20]


def _ngram_unique_ratio(words: list, n: int):
    """distinct/total n-grams over whitespace-split words. None when there are fewer than n words:
    'no data' must not be reported as 1.0, which would read as perfect novelty (i.e. meander)."""
    if len(words) < n:
        return None
    grams = [tuple(words[i:i + n]) for i in range(len(words) - n + 1)]
    return len(set(grams)) / len(grams)


def trace_stats(text) -> dict:
    """Compact, storable fingerprint of a thinking trace — the numbers the campaign's DNF probe
    had to measure by hand (line repetition, 8/20-gram uniqueness, backtracking markers).

    Line stats separate a verbatim loop from novel text; the two n-gram scales together catch
    loops that are longer than a line (8-gram) as well as long-range paraphrase cycling
    (20-gram). Empty/None text yields zeros with None ratios and never raises, so it can be
    called unconditionally on every generated row."""
    text = text or ""
    lines = _lines(text)
    counts = collections.Counter(lines)
    words = text.split()
    low = text.lower()
    return {
        "chars": len(text),
        "lines": len(lines),
        "unique_line_ratio": len(counts) / len(lines) if lines else None,
        "max_line_repeat": max(counts.values()) if lines else 0,
        "ngram8_unique": _ngram_unique_ratio(words, 8),
        "ngram20_unique": _ngram_unique_ratio(words, 20),
        "backtrack_markers": {k: len(re.findall(p, low)) for k, p in _MARKERS.items()},
    }


def compress_trace(text, head=4096, tail=4096) -> dict:
    """Head + tail excerpt of the reasoning, with the FULL length recorded.

    Traces are kept because losing them cost the campaign a re-run, but keeping them whole is not
    an option: an 82,000-token meander (the Qwen DNF's median) would bloat a results jsonl ~40x.
    Head and tail are the two informative ends — the head shows how the model set the problem up,
    the tail shows what it was doing when it ran out. When the text fits, BOTH fields are the
    whole text (not two overlapping slices), so a reader never has to reassemble it. Never raises
    on None."""
    text = text or ""
    if len(text) <= head + tail:
        return {"reasoning_chars": len(text), "reasoning_head": text,
                "reasoning_tail": text, "truncated": False}
    return {"reasoning_chars": len(text), "reasoning_head": text[:head],
            "reasoning_tail": text[-tail:] if tail else "", "truncated": True}


def _is_repetition(stats: dict) -> bool:
    """Degenerate verbatim loop: one line repeats a lot AND overall uniqueness is low (BOTH, so a
    long genuine trace that merely repeats a transitional phrase is not flagged). Needs enough
    lines to judge."""
    ratio = stats.get("unique_line_ratio")
    return (stats.get("lines", 0) >= REPEAT_MIN_LINES
            and stats.get("max_line_repeat", 0) >= REPEAT_MAX_REPEAT
            and ratio is not None and ratio < REPEAT_MIN_UNIQUE_RATIO)


def _is_novel(stats: dict) -> bool:
    """Over-exploration: the trace keeps producing new text (high n-gram uniqueness) and is not
    looping on a line. None uniqueness (too-short trace) is inconclusive, never novel."""
    n8 = stats.get("ngram8_unique")
    return (n8 is not None and n8 >= MEANDER_MIN_NGRAM8_UNIQUE
            and stats.get("max_line_repeat", 0) < REPEAT_MAX_REPEAT)


def is_degenerate(row: dict, *, trace_text=None) -> bool:
    """Does this row's trace show a degenerate verbatim loop — REGARDLESS of how it ended?

    `classify` cannot answer this, by design: it early-returns None for anything
    `convergence.is_converged` accepts, so a loop that self-terminates UNDER the thinking budget is
    never examined. Measured on IFEval 2026-08-13: one Ornith row emitted 52,503 tokens of a two-line
    alternating loop (unique_line_ratio 0.0093, max_line_repeat 2071, ngram8_unique 0.0123) with
    finish_reason "stop" at 64% of budget — scored `converged: True, nonconv_kind: None`. It was 4%
    of rows but 32% of wall-clock and 45% of tokens.

    The ratified convergence formula (`finish_reason == "stop" AND completion_tokens < budget`) is
    deliberately NOT changed here: that rule exists to stop a budget-hit's forced EOS from
    false-passing, and it still does. This is a SEPARATE, additive diagnostic for a third case the
    rule never covered — a loop cheap enough to finish on its own.
    """
    if row.get("error"):
        return False
    stats = row.get("reasoning_stats") or (trace_stats(trace_text) if trace_text else None)
    return bool(stats and _is_repetition(stats))


def classify(row: dict, *, trace_text=None):
    """Name the non-convergence MECHANISM for one generation row, or None if it converged.

    Returns None for an error row or a converged one (`convergence.is_converged`), then, in
    precedence order:
      - `degenerate_repetition` — EVEN IF finish_reason == "length". We act on the mechanism, not
        the stop reason: a repetition loop that also hit max_tokens is still a repetition loop,
        and calling it "max_tokens" would hide the sampling/quant defect.
      - `max_tokens` — truncated by the output cap with no loop signature.
      - `meander` — budget-saturated with a high-novelty trace: the temperature-ladder case.
      - `budget_hit` — budget-saturated, trace unavailable or inconclusive. An HONEST UNKNOWN,
        not a third mechanism: we know it did not self-terminate but cannot say why without a
        trace. Rows classified this way are exactly the ones a re-probe would resolve.
      - `unknown` — non-converged for some other reason (e.g. an unexpected finish_reason).

    The trace signal comes from a persisted `row["reasoning_stats"]` when present (so old runs
    stay classifiable), else from `trace_text`, else there is none."""
    if row.get("error"):
        return None
    if convergence.is_converged(row) is not False:
        return None                       # converged, or not a usable generation

    stats = row.get("reasoning_stats") or (trace_stats(trace_text) if trace_text else None)
    if stats and _is_repetition(stats):
        return "degenerate_repetition"
    if row.get("finish_reason") == "length":
        return "max_tokens"
    tb, ct = row.get("thinking_budget"), row.get("completion_tokens")
    if tb is not None and ct is not None and ct >= tb:
        return "meander" if stats and _is_novel(stats) else "budget_hit"
    return "unknown"


def summarize(rows) -> dict:
    """Tally non-convergence classes over a run's rows — the `nonconv_kinds` grading field.

    Converged and error rows are skipped, so `n` is the number of non-convergences EXPLAINED
    here and should equal convergence.audit's loop count. Ids are kept per kind because the
    follow-up differs by kind (restart-retry vs temperature ladder vs re-probe)."""
    kinds, ids = collections.Counter(), {}
    for row in rows:
        kind = classify(row)
        if kind is None:
            continue
        kinds[kind] += 1
        ids.setdefault(kind, []).append(row.get("id"))

    # EOS'd degenerate loops: rows the ratified formula counts as CONVERGED whose trace is a
    # verbatim loop. Reported by COST share, not row count — the IFEval case was 1 row in 28 (4%)
    # but 32% of wall-clock, so a count alone understates it by ~8x. This is the number that
    # revises "the runaway tax has nothing to charge": that claim was measured on budget-hits and
    # max_tokens truncations only, which this class is neither.
    live = [r for r in rows if not r.get("error")]
    eosed = [r for r in live if classify(r) is None and is_degenerate(r)]
    tot_w = sum(r.get("wall_s") or 0 for r in live)
    tot_t = sum(r.get("completion_tokens") or 0 for r in live)
    return {"n": sum(kinds.values()), "kinds": dict(kinds), "ids_by_kind": ids,
            "n_degenerate_eosed": len(eosed),
            "degenerate_eosed_ids": [r.get("id") for r in eosed],
            "degenerate_wall_share": round(sum(r.get("wall_s") or 0 for r in eosed) / tot_w, 4) if tot_w else 0.0,
            "degenerate_token_share": round(sum(r.get("completion_tokens") or 0 for r in eosed) / tot_t, 4) if tot_t else 0.0}
