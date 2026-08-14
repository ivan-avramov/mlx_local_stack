# Open questions & judgement calls — the operator's decision queue

Created 2026-08-13 at operator request. **Purpose:** one place for things that need the operator's
judgement, plus decisions already made so they are not re-litigated. Companions:
`docs/campaign-queue.md` (work state), `docs/campaign-results.md` (results), `AGENTS.md` (rules).

**Rules for this file.** An item is added the moment a judgement call is identified, not when it
becomes urgent. An item is either **OPEN** (needs the operator), **CLOSED** (with the decision and
its date), or **CLOSED-BY-MEASUREMENT** (the question dissolved because data answered it — record
the data, because "we decided" and "we measured" age differently). Nothing is deleted; a closed item
is the record that stops it being re-asked.

---

## OPEN — needs operator judgement

### O10. Should a budget-exceeded / externally-truncated row be EXCLUDED from `acc`, not just marked?
Raised by the operator's instruction to "call it DNF and **not grade it**" (2026-08-13). Half of that is
implemented, half is not:
- `converged: False` ✓ — the row IS marked, and a budget hit already fails the ratified formula.
- **but `acc` still includes it.** AGENTS.md fixes `acc` as "correctness over generated items
  (historical meaning)". The metric that zeroes truncated draws is `acc_strict` — and AGENTS.md
  explicitly forbids `acc_strict` as the ranking key, because it rises monotonically with
  `thinking_budget`, so a 5× budget spread would masquerade as capability.

So "don't grade it" collides with a ratified rule, and there are three coherent options:
1. **Status quo:** `acc` includes it, `acc_strict` zeroes it, both reported. (What AGENTS.md says now.)
2. **Drop from the denominator:** exclude non-converged rows from `acc` entirely. Cleanest reading of
   the operator's principle — but it makes `acc` non-comparable with every historical row, and a model
   that truncates often would be scored on a smaller, easier subset (the same bias that the nltk
   `punkt_tab` skip produced: 21% dropped moved acc 93.3% → 90.2%).
3. **Report `acc` over converged items only, as a NAMED metric** (`pass@1|converged` already exists and
   is computed), keeping `acc` historical.
**Recommendation: option 3.** It gives the operator's semantics an honest name without silently
redefining a metric that historical rows are published under, and it avoids option 2's
smaller-easier-subset bias. **NOTE:** no row in the IFEval run exceeded the thinking budget (0 of 220),
so this is currently a rule-hygiene question rather than one affecting a live number.


### ~~O1~~ → CLOSED, see C10
Not a design question so much as "may I fix these", but both mislead a reader on every run:
- **`grade.py` prints a retracted decision rule.** `CONV_GATE = 0.90` is still live and the scoreboard
  footer prints *"DECISION RULE (pre-registered): conv% >= 90 is a GATE; pass@1|conv RANKS within it."*
  AGENTS.md records that gate as **WITHDRAWN — unratified and unsound** (quantized in n; a point
  estimate against a hard threshold; ~10× too lenient on cost grounds). So every run prints a
  withdrawn rule while calling it pre-registered, and `conv_gate_pass` is still computed from it.
- **`run.py` mislabels its own sampling.** It prints `[params] using per-model production params
  (model_params.py)` immediately before `[generate] sampling profile = deployed`. The manifest proves
  `deployed` is what is used, so this is a stale log line — but "production" vs "deployed" is exactly
  the distinction that decides whether a run measured what we ship, so it is a dangerous thing to
  print wrongly.
**Recommendation:** fix both; replace the footer with the vector-reporting language AGENTS.md
actually ratifies. **Cost:** small, TDD-able, no model time.

### ~~O2~~ → CLOSED, see C11
P3 asks whether the cheap convergence screen predicts the agentic axis. Two measured problems:
- **`conv%` has no variance to correlate.** Tier-0 rev A: 33/33 converged. Rev B: 66/66. Spearman ρ on
  a constant vector is *undefined*, not weak.
- **The other half of the correlation does not exist.** P3 correlates the screen against per-config
  *agentic* results, and P4 has not run.
A ρ on median reasoning tokens is still computable — but see O3.
**Recommendation:** cancel P3 as specified; if a proxy is wanted, re-specify it on reasoning-token
cost and run it *after* P4 produces the other half. **Needs:** operator ruling, since P3 is in the
ratified plan.

### ~~O3~~ → CLOSED (delegated), see C14
Rev A's Ornith arm used `aggregation`@8K; rev B used `vartrack` (the swap that made a cell 2m04s
instead of >2h). Rev B is internally consistent across both models, which is what P2 needed, but the
two revisions cannot be pooled.
**Recommendation:** accept rev B as the record and leave rev A as a superseded row — its answer ("no
knee for Ornith") is unchanged by the task swap. Re-running rev A on vartrack costs ~4 min if you want
strict comparability. **Needs:** a ruling on whether the campaign record keeps both.

### ~~O4~~ → CLOSED (delegated), see C15
40 matches your stated failure ("turn 40, 180K context"). Session cost is O(turns) — measured, since
the session cache prefills only new tokens — so 40 turns is ~6 min/session on Ornith and ~21 min on
Qwen3.6-27B-Opus-Distill-OptiQ-4bit.
**Recommendation:** pilot at 12 turns, measure, then choose from data rather than from the prior.

### ~~O5~~ → CLOSED (delegated), see C16
The dependent-task sequence keeps a **mechanical** oracle (accumulated tests re-run every turn). One
realistic feature is more lifelike but partial credit becomes a judgement call, and the judge panel is
already recorded as not reliable enough to rank.
**Recommendation:** dependent-task sequence, for the mechanical oracle.

### ~~O6~~ → CLOSED, see C12
The fused GQA tile-reuse decode kernel is on by default and its precondition holds for both winners
(even `n_repeats`), but `_decode_2pass_use_legacy` occurs in exactly **one** place in the fork — the
`getattr` that reads it. Nothing sets it, so the claimed "1.3× over legacy TQ, +2–7% end-to-end"
**cannot be A/B'd at runtime**.
**Recommendation:** add the hook (parent fork + submodule bump). It is the only way this lever is ever
auditable, and the APC episode is the argument for doing it. **Cost:** small fork change, needs a
submodule bump and a redeploy.

### ~~O7~~ → CLOSED (delegated), see C17
`configgen/emitters/vscode.py:11` emits `_generated` into a JSON **array element** for a different
consumer (VS Code Copilot BYOK / Roo Code). The opencode case was fatal; this one is untested. Not
assumed broken.
**Recommendation:** verify against the actual consumer before touching it — a needless change to a
working carrier is its own risk.

### ~~O8~~ → CLOSED, see C13
All ready, none run: **judge panel v3** (`judge_extract.py`, dry-run clean at 43 both-solve pairs),
**BFCL live smoke** (request fix landed; whether `<think>` appears needs verifying, since that path
posts a pre-formatted prompt to `/v1/completions` and bypasses the chat template), **SWE-bench**
(built, never run). Plus P4/Tier-1 agentic tuning.
**Recommendation:** BFCL live smoke first — cheapest, and it is the only powered axis the campaign owns
(0.94 vs 0.749 at n=1000 is ~12σ). Then judge panel v3. SWE-bench last; it is the largest build.

### O9. Does the judge panel rate looped-then-correct answers differently? — HELD (delegated), see C18
Falls out of M1. Four rows on the IFEval run are execution-passing but reached the answer through a
degenerate loop (ids 2849, 279, 3608 line/content-level; 3188 also truncated). They are eligible for
the judge panel by the campaign's own rule — execution-passing outputs — and `is_degenerate` marks them
for attention.
**Why it is worth asking:** a 2,071x loop plausibly correlates with a worse ANSWER even when the
verifier passes; if it does not, that is equally informative, because it would mean reasoning-trace
pathology is invisible in output quality and is therefore purely a cost concern after all.
**Blocked on:** the panel's reliability (recorded as "NOT RELIABLE ENOUGH TO RANK" at v2), so this needs
the panel-reliability work first — or it can only ever be suggestive.
**Recommendation:** hold until the panel is trustworthy; do not spend model time on a comparison whose
instrument cannot carry it.

---

## CLOSED-BY-MEASUREMENT

### M1. Should `converged` absorb self-terminating repetition loops? — **NO** (2026-08-13, operator-confirmed)
**Operator ruling: this is NOT a DNF. It is a valid converged response — converged as determined by the
MODEL — and it is recorded and evaluated for quality like any other row: correctness AND subjective
quality.**

The operator's principle — *exhausting the thinking budget is a failed run, because we interrupted the
model rather than it deciding it was done* — is correct **and already the implemented rule**:
`converged = finish_reason=="stop" AND completion_tokens < thinking_budget`, so a budget hit is already
not converged, and AGENTS.md already calls it a fail signal. (Terminology: **EOS = end-of-SEQUENCE**,
the model's own stop token — not end-of-session. My jargon caused the confusion.)

Item 2849 was **not** a budget exhaustion: 52,503 tokens at **64% of budget** with `finish_reason
"stop"`, i.e. the model stopped itself, and its answer **PASSED both strict and loose** verifiers
(`benchmark/m1/inspect_item.py`) — a valid 276-char answer. The work was complete by the model's own
decision, so marking it DNF would **discard a valid result**, the opposite error to the one the budget
rule guards against.

⚠️ **REFINEMENT (2026-08-13, correcting my own framing).** I called this "a COST defect, not a
correctness one". That is accurate but INCOMPLETE, and the incompleteness matters: what was actually
measured is only the cost half (271 s and 52,503 tokens for 276 chars). Whether a model that loops
2,071 times before answering produced *good work* is a question the instrumentation cannot answer, and
"correctness passed, so it is fine apart from the tokens" must not stand in for it. Per the campaign's
instrumentation rule, subjective quality belongs to the blind mixed-family JUDGE PANEL over
execution-PASSING outputs — and this row is exactly such an output, so it is **eligible, not exempt**.

**So `is_degenerate` is a FLAG FOR THE JUDGE PANEL'S ATTENTION, not a verdict.** Consequences:
- These rows stay in `acc` and in the item set. **No exclusion, no reweighting, no DNF.**
- `degenerate_wall_share` / `degenerate_token_share` remain reasoning-token COST, reported beside
  capability and never folded into it.
- The open question becomes **O9** below: does the panel rate looped-then-correct answers differently
  from directly-correct ones? Better question, and answerable.
- ⚠️ Caveat: the judge panel is on record as **"NOT RELIABLE ENOUGH TO RANK"** (v2, two runs). It can
  raise a signal here; it cannot settle it, and a panel result on this must not be presented as
  decisive.

### M2. How do APC and session caching compose? — **THEY DON'T** (2026-08-13)
Mutually exclusive per request: `generation.py:2455-2464` dispatches any request with a
`prompt_cache_state` to `_process_cached_request` and `continue`s past the BatchGenerator, the only
site passed `apc_manager`. Anonymous requests resolve to a session by chained message hashes, so all
of our traffic takes the session path and APC is never consulted (measured: 0 lookups, 0 stores, 0
resident bytes; peak memory bit-identical to APC-absent). Session caching is what makes multi-turn
cheap (measured: cost per NEW token flat, cost per TOTAL token −17×).

### M3. Does APC cost memory that could disqualify a candidate? — **NO** (2026-08-13)
It consumes nothing because it does nothing (see M2). Constraint satisfied, for the wrong reason.

---

## CLOSED — operator decisions

| # | question | decision | date |
|---|---|---|---|
| C1 | Push the local commits, and how to keep boxes in sync | **Push; git is the ONLY cross-box transport** (rule in AGENTS.md; scp banned except throwaway `/tmp` diagnostics) | 2026-08-13 |
| C2 | Keep APC enabled for the daily driver? | **No — off everywhere**, including `runserver.sh`. Guarded by a test | 2026-08-13 |
| C3 | Drop the `_generated` key from opencode's config? | **Yes** — done TDD-first; the unmodified generated config now loads on M5 | 2026-08-13 |
| C4 | Fix `run.py`'s CWD fragility? | **Yes** — `bench/paths.py`, same absolute paths as before, verified from the wrong CWD | 2026-08-13 |
| C5 | Derive the request timeout from the decode rate? | **Yes**, with a hard ceiling and loop/meander detection | 2026-08-13 |
| C6 | Re-verify Phase-2 suffix / GQA claims? | **Yes** — suffix confirmed real (1.27×); GQA on-by-default but unfalsifiable (see O6) | 2026-08-13 |
| C7 | Trim the IFEval distill arm for time? | **No — run it full**; timing is not a constraint | 2026-08-13 |
| C8 | Cadence for benchmark runs | **Report AND critically evaluate every 5 min** (rule in AGENTS.md, four required questions) | 2026-08-13 |
| C9 | Multi-turn eval: one benchmark or two? | **Two targeted benchmarks**, coder + daily driver, one shared spine | 2026-08-13 |
| C10 | Fix the two stale outputs (O1)? | **Yes** — DONE. Footer now states AGENTS.md's ratified four-number rule; conv% labelled a DIAGNOSTIC; the `gate PASS/FAIL` COLUMN removed (it contradicted the footer above it); `run.py` now names the actual sampling profile | 2026-08-13 |
| C11 | Cancel P3, the ρ proxy validation (O2)? | **CANCELLED.** ρ on `conv%` is undefined (66/66 converged = a constant vector), and the agentic half does not exist until P4 runs. If a proxy is wanted later, re-specify on reasoning-token cost AFTER P4 | 2026-08-13 |
| C12 | Add the `TQ_DECODE_2PASS_LEGACY` hook (O6)? | **Yes** — DONE. Fork `8b7100b8` + submodule bump `3f85279`, deployed and verified live on M5 (default False, env=1 True). Default behaviour unchanged; the A/B itself is separate worker time and not yet run | 2026-08-13 |
| C13 | Axis sequencing after IFEval (O8)? | **P4 → BFCL → judge panel → SWE-bench** | 2026-08-13 |
| C14 | Tier-0 rev A vs rev B record (O3)? | Delegated → **accept rev B as the record, rev A marked superseded.** Its answer ("no knee for Ornith") is unchanged by the task swap, so a 4-min re-run buys only strict poolability | 2026-08-13 |
| C15 | Multi-turn B depth: 40 or 24 (O4)? | Delegated → **pilot at 12 turns, choose from measured cost.** Sizing from a prior is what killed Tier-0 rev A | 2026-08-13 |
| C16 | Multi-turn A construct (O5)? | Delegated → **dependent-task sequence**, to keep a mechanical oracle; one realistic feature makes partial credit a judgement call the judge panel cannot yet carry | 2026-08-13 |
| C17 | `vscode.py` `_generated` (O7)? | Delegated → **verify against the real consumer before changing anything.** A needless change to a working carrier is its own risk | 2026-08-13 |
| C18 | Judge panel on looped answers (O9)? | Delegated → **HELD** until the panel is reliable ("NOT RELIABLE ENOUGH TO RANK" at v2). Do not spend model time on a comparison whose instrument cannot carry it | 2026-08-13 |
