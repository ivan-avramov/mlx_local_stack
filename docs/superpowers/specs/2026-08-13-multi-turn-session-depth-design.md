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

**Cost control — the thing that makes this affordable.** A 40-turn session re-prefills the whole
transcript every turn, so naive cost is O(turns²). At the distill's measured ~15 tok/s on long
prompts this is the dominant risk. Mitigations, in order of preference:
- **Report TTFT separately and expect it to dominate** (AGENTS.md already requires prefill/decode
  split); do not let prefill cost masquerade as model quality.
- **This is the one axis where APC would matter enormously** — and APC is currently **inert**
  (measured 2026-08-13: 0 lookups, 0 stores, no reuse). Fixing APC is a *prerequisite for
  affordability at 40+ turns*, not a nice-to-have. Until then, budget full re-prefill per turn.
- Pilot at **n=3 sessions × 1 model** before committing; measure, don't extrapolate (rev A was sized
  from the wrong model's timing and lost an hour).

---

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

**Primary metric: regression rate vs turn index** — `P(a previously-passing test fails at turn t)`.
This is the "re-breaks fixed code" failure, it needs no judge, and it is invisible to every axis we
own. Secondary: cumulative tasks-green, well-formed-diff rate vs depth, context tokens at first
regression.

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

**Primary metric: constraint retention vs depth** — `P(constraint honoured | turns since it was
given, context tokens)`. Mechanical, cheap, per-turn, model-agnostic, no judge.

**Secondary:**
- **Self-contradiction:** re-ask a factual question answered at turn 5; does the answer still match?
  (Mechanical: compare to its own earlier answer, not to ground truth.)
- **Instruction recency bias:** plant two *compatible* constraints far apart; is only the recent one
  honoured?
- **Cost curve:** TTFT and context tokens vs turn — the practical "unusable by turn 40" number, and
  the one that decides whether APC repair is mandatory for this role.
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
- **Don't run either at 40+ turns before APC is understood.** Full re-prefill per turn is O(turns²);
  this axis is where the inert-APC finding actually bites.

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
3. **Does repairing APC get priority over building this?** For the daily-driver role it is close to a
   prerequisite: without prefix reuse, a 40-turn session is dominated by re-prefill, and TTFT is the
   very thing the role is judged on.
