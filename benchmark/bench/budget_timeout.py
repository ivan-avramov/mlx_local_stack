"""Derive a per-request timeout from the thinking budget and the model's MEASURED decode rate.

THE DEFECT THIS FIXES (measured 2026-08-13). `run_convergence.run_one` used `driver.complete`'s
default 3600 s timeout while `thinking_budget` is 81,920. On the distill's long-prompt cells decode
runs at 10-16 tok/s, so reaching the budget needs 85-136 min. The client therefore ALWAYS gives up
first, and the worker keeps generating: a genuine `budget_hit` is UNOBSERVABLE on that model, and the
orphaned generation then starves every later cell. Tier-0 rev A died exactly this way — its
aggregation cell ran 3,802 s against the 3,600 s timeout, ~200 s short of finishing, and the next
cell's 120 s `calibrate_cpt` queued behind the orphan and failed.

THE FIX IS NOT "SET A BIGGER NUMBER". A timeout large enough for the worst case (136 min) would let a
genuinely looping model burn over two hours per draw before anyone notices. Operator requirement:
a reasonable ceiling AND a way to tell "still working" from "looping/meandering". So:

  timeout = clamp(thinking_budget / measured_decode_tps * SAFETY, FLOOR, CEILING)

with the rate MEASURED for that model rather than assumed, and a hard CEILING so a pathological model
cannot run unbounded. Crucially the ceiling is chosen so that hitting it means something definite:

  - if the derived budget time is BELOW the ceiling, a timeout means the model exceeded its own
    thinking budget -> that is a `budget_hit`, the FAIL SIGNAL AGENTS.md says to investigate.
  - if the derived budget time is ABOVE the ceiling, the run CANNOT observe a clean budget hit, and
    that is reported as `budget_observable=False` rather than silently producing an ambiguous
    timeout. A number we cannot interpret is worse than a missing one.

WHY NOT JUST RAISE `thinking_budget` OR LOWER IT: AGENTS.md forbids treating the budget as a tuning
knob. It stays at its generous fixed headroom; only the CLIENT's patience is derived here.

PROGRESS / LOOP DETECTION. A timeout alone cannot distinguish "slow but converging" from "looping".
`classify_stall` labels a non-finishing draw using evidence the harness already persists, so the
distinction is recorded rather than guessed:

  - `degenerate_repetition` — the tail of the reasoning repeats a short cycle. This is the gemma
    temp-1.0 pathology and the one true "looping" case.
  - `meander`  — long, non-repeating reasoning that never converges (the qwen3_5-arch pathology).
  - `budget_hit` — reached `thinking_budget`; external truncation, NOT a model knob.
  - `max_tokens` — hit the generation cap.
  - `client_timeout` — WE gave up. Explicitly distinguished, because it is a harness event, not a
    model property, and rev A's cascade came from conflating the two.
"""
from typing import Optional

# Multiplier on the derived budget time: prefill, scheduling and rate variance all sit on top of pure
# decode. 1.5x is generous without approaching the ceiling for well-behaved models.
SAFETY = 1.5
# Never below this: short prompts on a fast model still need room for a cold model load.
FLOOR_S = 300.0
# Hard ceiling. 2h is above the distill's measured worst realistic draw (999 s) by ~7x, and is the
# point past which an unattended draw is costing more than the information it can return.
CEILING_S = 7200.0

# A repeated cycle this long or shorter, occupying at least this fraction of the tail, is degenerate.
_CYCLE_MAX = 200
_TAIL_CHARS = 4000


_MIN_ROWS_FOR_RATE = 5
_FLOOR_PCT = 10


def floor_decode_tps(rows, pct: int = _FLOOR_PCT,
                     min_rows: int = _MIN_ROWS_FOR_RATE) -> Optional[float]:
    """A model's SLOW-TAIL decode rate from its own rows, or None when the evidence is too thin.

    A low percentile, not the mean: the draws at risk of abandonment are precisely the long ones,
    and long draws decode SLOWER (the KV cache grows), so they sit in the bottom tail. Deriving the
    client's patience from the typical rate makes the bound too short exactly where it must hold.
    None means "no derivation" — `derive_timeout` then falls back to its ceiling and reports
    `budget_observable=False` rather than inventing a number (C28).
    """
    tps = sorted(r["decode_tps"] for r in rows
                 if not r.get("error") and isinstance(r.get("decode_tps"), (int, float))
                 and r["decode_tps"] > 0)
    if len(tps) < min_rows:
        return None
    # FLOOR, not nearest: rounding up would pick a FASTER row and shorten the bound, which is the
    # wrong direction for a safety margin.
    idx = max(0, min(len(tps) - 1, int((pct / 100.0) * (len(tps) - 1))))
    return float(tps[idx])


def derive_timeout(thinking_budget: Optional[int], decode_tps: Optional[float],
                   safety: float = SAFETY, floor_s: float = FLOOR_S,
                   ceiling_s: float = CEILING_S) -> dict:
    """Return {timeout_s, budget_time_s, budget_observable, reason}.

    `budget_observable` is the honest part: it says whether a timeout at this setting could be
    interpreted as a budget hit at all.
    """
    if not thinking_budget or not decode_tps or decode_tps <= 0:
        return {"timeout_s": ceiling_s, "budget_time_s": None, "budget_observable": False,
                "reason": "no measured decode rate or no budget — falling back to the ceiling, so a "
                          "timeout here is UNINTERPRETABLE"}
    budget_time = thinking_budget / decode_tps
    want = budget_time * safety
    timeout = max(floor_s, min(want, ceiling_s))
    observable = want <= ceiling_s
    if observable:
        reason = (f"budget {thinking_budget} tok at {decode_tps:.1f} tok/s = {budget_time/60:.0f} min; "
                  f"x{safety} = {want/60:.0f} min, within the {ceiling_s/60:.0f} min ceiling, so a "
                  f"timeout implies the model exceeded its own thinking budget")
    else:
        reason = (f"budget {thinking_budget} tok at {decode_tps:.1f} tok/s = {budget_time/60:.0f} min; "
                  f"x{safety} = {want/60:.0f} min EXCEEDS the {ceiling_s/60:.0f} min ceiling — a clean "
                  f"budget_hit is NOT observable for this model at this prompt length")
    return {"timeout_s": round(timeout, 1), "budget_time_s": round(budget_time, 1),
            "budget_observable": observable, "reason": reason}


def _longest_repeated_tail_cycle(text: str) -> Optional[str]:
    """Shortest cycle whose repetition fills the tail. None when the tail does not cycle."""
    tail = text[-_TAIL_CHARS:]
    if len(tail) < 40:
        return None
    for n in range(8, min(_CYCLE_MAX, len(tail) // 3) + 1):
        cycle = tail[-n:]
        reps, i = 0, len(tail)
        while i >= n and tail[i - n:i] == cycle:
            reps += 1
            i -= n
        # >=3 back-to-back repeats covering most of the tail is degenerate, not stylistic
        if reps >= 3 and reps * n >= 0.6 * len(tail):
            return cycle
    return None


def classify_stall(finish_reason: Optional[str], completion_tokens: Optional[int],
                   thinking_budget: Optional[int], reasoning_text: str = "",
                   timed_out: bool = False) -> dict:
    """Label a draw's non-convergence by MECHANISM. Returns {converged, nonconv_kind, evidence}."""
    ct = completion_tokens or 0
    budget_hit = bool(thinking_budget and ct >= thinking_budget)

    if timed_out:
        cycle = _longest_repeated_tail_cycle(reasoning_text or "")
        # A client timeout is OURS, but the trace still says whether the model was looping.
        kind = "degenerate_repetition" if cycle else "client_timeout"
        return {"converged": False, "nonconv_kind": kind,
                "evidence": {"timed_out": True, "completion_tokens": ct,
                             "repeated_cycle": cycle[:60] if cycle else None,
                             "note": "WE stopped this draw; not a model property unless a cycle was "
                                     "found in the trace"}}
    if budget_hit:
        # A draw can hit BOTH: the budget force-injects </think> at 81,920, the model then writes an
        # answer, and that answer can itself run into max_tokens. `budget_hit` is the primary label
        # because it is the ROOT CAUSE (thinking never self-terminated) and it is what the
        # temperature ladder acts on; the downstream truncation is kept as evidence rather than
        # discarded, so a compound failure is still fully visible in the row.
        return {"converged": False, "nonconv_kind": "budget_hit",
                "evidence": {"completion_tokens": ct, "thinking_budget": thinking_budget,
                             "also_max_tokens": finish_reason == "length"}}
    if finish_reason == "length":
        return {"converged": False, "nonconv_kind": "max_tokens",
                "evidence": {"completion_tokens": ct}}
    if finish_reason == "stop":
        return {"converged": True, "nonconv_kind": None, "evidence": {"completion_tokens": ct}}

    cycle = _longest_repeated_tail_cycle(reasoning_text or "")
    if cycle:
        return {"converged": False, "nonconv_kind": "degenerate_repetition",
                "evidence": {"repeated_cycle": cycle[:60], "completion_tokens": ct}}
    return {"converged": False, "nonconv_kind": "meander",
            "evidence": {"finish_reason": finish_reason, "completion_tokens": ct}}
