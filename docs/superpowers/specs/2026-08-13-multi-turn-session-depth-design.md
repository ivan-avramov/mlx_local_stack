# Multi-turn session depth — design for TWO targeted benchmarks (2026-08-13)

Status: **DESIGN, not built.** Operator asked for both roles covered by *separate targeted*
benchmarks rather than one construct trying to serve both.

Companion: `docs/superpowers/plans/2026-08-12-campaign-v3-two-role-selection.md` (campaign v3, the
two-role framing), `docs/campaign-results.md` (results), `AGENTS.md` (measurement discipline).

---

## 0. Why this axis exists, and why one benchmark can't cover both roles

Every axis the campaign owns — old and new — is **single-task and fresh-context**. `campaign-queue.md`
records the gap as follow-on #1: *"the daily driver fails at turn 40 with 180K of accumulated
context."* Nothing we have measured would detect that. M1 measured 2 attempts inside one case; the
agentic axis measured 284 turns but **each case starts from a clean context**.

The two roles fail differently, which is why they need different instruments:

| | CODER | DAILY DRIVER |
|---|---|---|
| what accumulates | code state, failed diffs, test output | conversation, pasted docs, topic switches |
| what "failing at depth" looks like | edits stop applying; re-breaks fixed code; loops | forgets constraints; contradicts itself; ignores earlier instructions |
| is there a mechanical oracle? | **yes** — tests pass/fail, diff applies/doesn't | **no** — needs constraint checking or a judge |
| turn count that matters | 10–30 (a feature's worth of edits) | 40+ (a working day) |

A single benchmark would have to pick one oracle, and the honest ones differ. So: **two benchmarks,
one shared instrumentation spine.**

---

## 1. Shared spine (build ONCE, both benchmarks consume it)

Today's Tier-0 result is the reason this spine comes first. **`conv%` was pinned at 1.0 across 66/66
draws while the underlying cost varied 47×** — a metric saturated by construction told us nothing,
and only per-draw token/wall instrumentation revealed the real behaviour. A session benchmark scored
only by an end-of-session number would repeat that mistake at 40× the cost.

**Per-turn record** (the unit of analysis; one row per turn, not per session):

```
session_id, turn_idx, model, config_fingerprint,
prompt_tokens, completion_tokens, reasoning_tokens,
context_tokens_total,          # accumulated, the independent variable
finish_reason, converged, nonconv_kind,
ttft_s, decode_tps, wall_s,
peak_mem_gb,                   # gate metric; catches KV growth blowing the budget
outcome,                       # benchmark-specific (see §2, §3)
sample_seed                    # rowschema.sample_seed((session_id, turn_idx), sample)
```

Four spine requirements, each earned by a defect already paid for:

1. **Seeds per turn.** Unseeded requests are byte-identical replays, so k sessions would be k copies.
   Seeds derive from `(session_id, turn_idx, sample)` only, so they are **identical across models**
   (common random numbers → paired comparison).
2. **Deployed truncation, always.** `top_p 0.95 / top_k 20`. The untruncated tail is
   nondeterministic under suffix decoding (3 identical requests → 3 outputs, 1.6× length spread), and
   a 40-turn session would compound that into noise.
3. **Turn-indexed, not session-aggregated.** The endpoint is *degradation vs depth* — a curve, not a
   scalar. A session score cannot distinguish "bad throughout" from "fine until turn 25".
4. **A per-request timeout derived from `thinking_budget ÷ measured decode rate`.** Today's defect:
   the 3600 s default is below the 85–136 min the distill needs to reach an 81,920 budget, so the
   client abandons and the worker keeps generating. In a 40-turn session that orphans the whole
   session, not one cell.

### 1.1 COST — defined, and MEASURED (this replaces an earlier wrong claim in this doc)

**"Cost" is two different things and they must never be merged into one number:**

| | what it is | units | property |
|---|---|---|---|
| **token cost** | tokens the model CHOOSES to generate (completion, of which reasoning is the bulk) | tokens | **model behaviour**; hardware-independent; transfers to H200/B200 |
| **wall cost** | what a user waits | seconds = prefill + (completion tokens ÷ decode rate) | **deployment reality**; box-specific; NOT transferable |

They diverge badly. Today's Tier-0 blowup was **47× in tokens** (1,122 → 52,833) but **24× in wall**
(41 s → 999 s) — same event, different multipliers, because prefill and decode rate differ per turn.
Report both, always, and keep prefill and decode split (AGENTS.md already requires this). Token cost
is the one that says something about the *model*; wall cost is the one that says whether we can
afford the run.

**MEASURED 2026-08-13 — a growing conversation gets INCREMENTAL prefill, so session cost is
O(turns), NOT O(turns²).** An earlier draft of this doc asserted the opposite and called APC repair a
prerequisite for 40+ turns. **That was wrong.** The fork's own session cache (`PromptCacheState`,
`server/session_manager.py:get_or_create_prompt_cache_state`) holds KV + token history across turns
and prefills only the tokens after the common prefix. It needs **no `chat_id` from the client** —
`_find_session_by_hash_prefix` routes anonymous requests to their session by chained per-message
sha256s, which is exactly what a plain OpenAI-compatible client (aider, opencode) sends.

Ornith, M5, 6-turn growing conversation, ~2.1K new tokens per turn:

| turn | total prompt tok | new tok | wall | ms per NEW tok | ms per TOTAL tok |
|---|---|---|---|---|---|
| 1 | 2,102 | 2,102 | 5.35 s | 2.55 | 2.55 |
| 2 | 4,209 | 2,107 | 1.73 s | 0.82 | 0.41 |
| 4 | 8,423 | 2,107 | 1.82 s | 0.86 | 0.22 |
| 6 | 12,637 | 2,107 | 1.92 s | 0.91 | **0.15** |

Cost per *new* token is flat (0.82 → 0.91 ms, an 11% rise over 6 turns = mild attention growth);
cost per *total* token falls **17×**. Only new tokens are prefilled.

**Consequence — this axis is CHEAP, and APC is irrelevant to it.** Per-turn prefill is ~2 s at
12K context, so decode dominates. A 40-turn session at ~800 completion tokens/turn:
Ornith (~140 tok/s) ≈ **6 min/session**; the distill (~28 tok/s) ≈ **21 min/session**. Three sessions
× both winners ≈ **1.5 h**. APC plays no part: it is a separate generic prefix cache, it is excluded
from all benchmarking by standing operator instruction, and it is not what makes this work.

Still pilot before committing (rev A was sized from the wrong model's timing and lost an hour), but
the affordability question is answered.

---

## 1.2 THE BENCHMARK MUST NOT SATURATE — measure a BREAKING POINT, not a fixed-depth score

Operator requirement: hard enough that no model saturates it, so it resolves *between* models. This
is the single most important design constraint, and the campaign has already been burned by ignoring
it — repeatedly:

| axis | result | usable resolution? |
|---|---|---|
| Tier-0 `conv%` | 1.0 in **66/66** draws | **none** — saturated, ρ undefined |
| he+ (distill) | 100% | **none** — ceiling'd |
| LCB @ n=15 | three-way tie at 80% | **none** at that n |
| aider polyglot | 50.0% vs 73.6%, p=1.3e-05 | **yes** — the only axis that ever separated the winners |

**The design rule that makes saturation structurally impossible: make the metric a THRESHOLD, not a
score at a fixed depth.** Instead of "% of constraints retained at turn 40" (which can be 100% for
everyone), measure **the depth at which retention first fails**. If nobody fails by turn 40, the
answer isn't "tie" — it's "run to 80". The metric is unbounded above, so a model can only saturate it
by being unboundedly good.

This is not a new invention: it is exactly how the campaign already handles context
(effective-context = the depth where accuracy crosses 0.85, not pass/fail at one length). Applying
the same shape here keeps it consistent with the one threshold the campaign has ratified.

**Pre-registered escalation ladder** (decided BEFORE looking, so it can't be rationalised after):
1. Run at depth D (B: 40 turns; A: 20 turns).
2. If **both** models are still clean, **double D** and re-run. Session cost is O(turns), so doubling
   depth roughly doubles cost — affordable per §1.1.
3. If **both** models fail immediately (turn < 5), the construct is too hard to resolve anything —
   *reduce* constraint count / task coupling rather than reporting a floor-effect tie.
4. Stop when the two winners' breaking points differ by more than the paired CI, or when depth
   exceeds what the KV budget allows (record the ceiling as a config fact, never as a blank).

**Difficulty knobs, to be turned until separation appears** — enumerated now so escalation is
mechanical rather than improvised:
- **B:** number of simultaneous constraints (4 → 8); constraints that FIGHT the model's default style
  (e.g. "never use bullet points" against a model that loves lists — a genuinely adversarial ask);
  more topic switches between plant and probe; distractor instructions in between; longer pasted
  documents to grow context faster.
- **A:** tighter coupling between tasks (later tasks touching the same functions, not just the same
  files); more turns before re-running the full suite; refactors that *require* touching earlier code.

**And the honest pre-registration:** if a metric still saturates after escalation, it is reported as
**"no resolution at this depth"** — not as a tie, and not quietly dropped. "Inconclusive is a valid
answer" already applies; a saturated metric is a *weaker* statement than inconclusive, because it
means the instrument couldn't have detected a difference at all.

## 2. Benchmark A — CODER session depth ("sustained feature work")

**Question:** as edits accumulate in one context, does the model keep applying correct diffs, or does
it start re-breaking what it already fixed?

**Why this is not M1 with more turns.** M1's repair turn receives the failing test's *source and
expected values*, and each case starts clean. Here the model must hold **its own prior edits** in
context — the failure mode is self-inconsistency across turns, which M1 structurally cannot see.

**Construct.** One repo, one context, a **pinned ordered sequence of 12–20 small feature/bugfix
tasks** over the *same* files, so later tasks genuinely depend on earlier edits. Tests accumulate:
every task's tests are re-run **every turn**.

**The oracle is mechanical and it is the point:**

```
per turn:  new_task_tests_pass    (progress)
           ALL_prior_tests_pass   (REGRESSION — the real signal)
           diff_applied_cleanly    (edit competence at depth)
```

**Primary metric (threshold-shaped, per §1.2): FIRST-REGRESSION DEPTH** — the turn index at which a
previously-passing test first fails, plus the regression rate curve beyond it. This is the
"re-breaks fixed code" failure, it needs no judge, and it is invisible to every axis we own. Reporting
it as a depth rather than a rate at fixed depth is what stops it ceiling'ing. Secondary: cumulative
tasks-green, well-formed-diff rate vs depth, and token/wall cost per turn (§1.1, both units).

**Item source.** Build from the **89 unused polyglot exercises** (M1 used 110 of 199), converted into
dependent sequences — *not* the 110 already used, to keep the held-out set clean for P4/Tier-2.

**Harness.** aider first (mechanical, already wired, `.aider.results.json` parsing exists). Then
opencode — **now unblocked**: gates (a)/(b)/(c) passed today and the tuned sampling verifiably lands.
Budget opencode at **~18K prompt tokens of scaffold per turn** (measured), which at 20 turns is
~360K of prefill *before* any accumulated code.

**Read the result as a curve, and expect two confounds to be named:** context length and task
difficulty both rise with turn index. Control by **shuffling task order across sessions** (same task
set, different positions), so a task's difficulty is decorrelated from its depth.

---

## 3. Benchmark B — DAILY DRIVER session depth ("the working day")

**Question:** across 40+ turns and topic switches, does the model still honour constraints it was
given at turn 3?

**Construct — a scripted session with PLANTED, MECHANICALLY CHECKABLE constraints.** This is the
design choice that avoids depending on a judge for the primary number.

At early turns, plant constraints whose observance is verifiable by string/pattern rules — the same
trick IFEval uses, which is why IFEval is the right precursor (harness functional, never run):

- turn 2: *"Throughout this conversation, always use British spelling."*
- turn 4: *"Refer to the project as PROJECT-X, never by any other name."*
- turn 6: *"Never use bullet points; always write prose."*
- turn 9: *"Always end your answers with the token `<<END>>`."*

Then run 40+ turns of realistic mixed work (explanations, small code, refactor advice, a doc paste,
**deliberate topic switches**, one long pasted document to force context growth). **Probe each
constraint repeatedly at increasing depth** (turns 12, 20, 28, 36, 44).

**Primary metric (threshold-shaped, per §1.2): RETENTION-BREAK DEPTH** — the turn index at which a
constraint is first violated, per constraint, plus the retention curve
`P(honoured | turns since given, context tokens)`. Mechanical, cheap, per-turn, model-agnostic, no
judge. Escalate depth per the ladder if neither model breaks.

**Secondary:**
- **Self-contradiction:** re-ask a factual question answered at turn 5; does the answer still match?
  (Mechanical: compare to its own earlier answer, not to ground truth.)
- **Instruction recency bias:** plant two *compatible* constraints far apart; is only the recent one
  honoured?
- **Cost curve:** token cost and wall cost vs turn, reported separately (§1.1) — the practical
  "unusable by turn 40" number. Measured: prefill is incremental, so decode dominates.
- **Judge panel LAST, and only over sessions that pass the mechanical checks** — per AGENTS.md, the
  judge is for subjective quality (coherence, helpfulness), never as a correctness oracle. It also
  has an unretired reliability problem (judge panel v2: "NOT RELIABLE ENOUGH TO RANK"), so it must
  not carry the headline.

**Why constraint retention rather than a needle test.** We already clear 256K on *needle retrieval*;
the daily-driver failure is **not** "can't find the fact" but "stops obeying the instruction". Those
are different capabilities, and only the second is unmeasured. Keeping them separate also respects
the rule that retrieval-depth and reasoning-depth curves stay separate — this is a third curve,
**instruction-retention depth**, and it should not be pooled with either.

---

## 4. What I recommend NOT doing

- **Don't score a session with one number.** Today's `conv%` result is the argument: saturated
  end-state metrics hid a 47× cost spread.
- **Don't build B on a judge as primary.** The panel is built, run twice, and recorded as not
  reliable enough to rank; a 40-turn session multiplies its variance.
- **Don't use the 110 M1 exercises for A.** It would contaminate the held-out set P4/Tier-2 needs.
- **Don't score at a single fixed depth.** A fixed-depth score can ceiling; a breaking-point depth
  cannot (§1.2). Every axis that ever saturated on this campaign did so by being a fixed-depth or
  fixed-item score.
- **Don't bring APC into this.** It is excluded from all benchmarking by standing operator
  instruction, it is a generic prefix cache rather than session caching, and it is measurably not
  what makes multi-turn affordable — the fork's `PromptCacheState` session cache is (§1.1).

## 5. Sequencing (cheapest informative thing first)

| # | step | why first | worker cost |
|---|---|---|---|
| 1 | **IFEval** (ready now, never run) | validates the mechanical constraint-checking machinery B depends on, at n=541, single-turn | ~1–2 h |
| 2 | **B pilot**, 1 model × 3 sessions × 12 turns | measures the real per-turn cost curve before committing to 40 turns | ~2–3 h |
| 3 | **A pilot**, 1 model × 1 sequence × 8 turns, aider | proves the accumulating-test oracle works | ~2–3 h |
| 4 | decide depth (40 vs 24 turns) and n **from measured cost**, not from a prior | this is exactly where rev A went wrong | — |
| 5 | full A + B, both winners, paired seeds | the actual rows | size at step 4 |

Steps 1–3 are ~6 h total and answer "is this measurable and affordable" before any large commitment.
**Step 1 needs no new code at all.**

---

## 6. Open questions for the operator

1. **Turn depth for B: 40 or 24?** 40 matches the stated failure ("turn 40, 180K context") but at
   full re-prefill costs ~3× a 24-turn session. I would pilot at 12, measure, then choose.
2. **Is A's "same files, dependent tasks" the right coder construct**, or would you rather see
   *one* realistic feature built over 15 turns (more realistic, weaker oracle — partial credit
   becomes a judgement call)? I lean to the dependent-task sequence because the oracle stays
   mechanical.
3. ~~Does repairing APC get priority?~~ **WITHDRAWN — the question was malformed.** APC is excluded
   from benchmarking by standing instruction, and the measurement in §1.1 shows session caching
   already gives incremental prefill, so nothing about this axis depends on APC.
