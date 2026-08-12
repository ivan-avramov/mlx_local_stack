# Campaign v3 — two-role selection under measured constraints

Rev 2, after adversarial review by three independent reviewers (statistics / feasibility / goal
alignment). Every rev-1 claim they falsified is marked **[FIXED]** with what changed and why.

APC is OFF everywhere, is not an axis, and is out of scope. Not discussed further.

## Goals

| # | Goal | Type |
|---|---|---|
| G1 | Evaluate models — incl. quant technique, bit-level, distillation | **INPUT** (changes over time) |
| G2 | Per-model best sampling config, found tractably | **INPUT**, searched |
| G3 | KV quant technique + level: squeeze until meaningful impact | **INPUT**, searched |
| G4 | Context reach under ~48GB; 256K desirable, NOT a mandate | **MEASURED** |
| G5 | Speed | **MEASURED**, never an input |
| G6 | Useful performance paired with real harnesses | **MEASURED** |
| G7 | Always propose TWO models: **coder** + **interactive daily driver** | **OUTPUT** |

## R1 — Collapse the sampling space by mechanism, but TEST the collapse **[FIXED]**

top_p / top_k / min_p are all tail-truncation knobs. Keep **min_p** (scale-free, so it behaves
consistently across temperatures where fixed top_k does not); set `top_k=0`, `top_p=1.0`. Fix
`presence_penalty=0.0` permanently — nonzero disables suffix decoding, changing the serving path.

**Rev-1 asserted this collapse while the next section preached "don't guess, measure" — a
self-contradiction the statistics reviewer caught.** So the collapse is now *tested*: two grid cells
run full-3-knob vs min_p-only at fixed temp. If they differ beyond noise, the collapse is void and
the space reopens.

## R2 — Proxy validation folded into the Tier-0 grid **[FIXED]**

Rev 1 proposed Spearman ρ on **4 configs** with a ρ≥0.7 threshold. Verified by computation, that was
close to worthless:

| n configs | P(ρ≥0.7 \| null) | min achievable two-sided p |
|---|---|---|
| 4 (rev 1) | **16.7%** | **0.083** — cannot reach significance even at perfect agreement |
| 8 | 2.9% | <0.0001 |

ρ at n=4 is discrete in steps of 0.2, so "≥0.7" silently meant "≥0.8", and 1-in-6 of pure noise
would have licensed the whole cheap-screening pipeline. **Fix: no separate probe. Reuse the Tier-0
9-config grid** — evaluate those same 9 on the expensive target for a subset, compute ρ over 9 points,
and **report the exact permutation p-value beside it**. `ρ high but p>0.3` = inconclusive, not
validated. This removes a step *and* fixes the power problem.

## R3 — Successive halving with stated n, provisional survivors **[FIXED]**

| tier | eval | configs | items | MDE |
|---|---|---|---|---|
| 0 | cheap screen | 9 (3 temp × 3 min_p) | 30 | ±23pp |
| 1 | agentic tune-set @ `tries=4` | top 3 | 44 | ±19pp |
| 2 | **held-out exercises** | top 1 vs shipped | 60+ | ±16pp |

Rev 1 gave no item counts, so no MDE was computable. Selecting extremes from noisy rates invites
winner's curse, so **tier survivors are provisional until re-confirmed, never settled winners**.
Temperature is swept first and most finely (established dominant knob); min_p refined only if
temperature shows structure.

## R4 — Held-out **exercises**, not languages **[FIXED]**

The feasibility reviewer found that rev 1's step 4 *could not run*: `m1f` already consumed all five
usable languages (cpp is excluded as a g++ toolchain confound), so no held-out language exists.

Measured availability — and the fix is **better** than the original design:

| lang | total | used by m1f | **held out** |
|---|---|---|---|
| python | 34 | 22 | 12 |
| javascript | 49 | 22 | 27 |
| go | 39 | 22 | 17 |
| rust | 30 | 22 | 8 |
| java | 47 | 22 | 25 |
| **total** | | 110 | **89** |

89 unused exercises in the *same* language mix. Holding out **items** rather than languages keeps
language difficulty constant by construction, whereas held-out languages would have confounded the
split with language difficulty. Claim label: *same-language, disjoint-items*.

## R5 — "Meaningful impact" for KV = TOST with a THREE-state rule **[FIXED]**

Not a σ-threshold: σ conflates *significance* with *meaningfulness* (at large n a 1pp drop is "3σ"
and irrelevant; at small n a 15pp drop is invisible). Use equivalence testing against a
pre-registered indifference margin **δ = 5 percentage points, ABSOLUTE**.

Rev 1 had two states, leaving CIs like (−3pp, +8pp) unnamed — and since the plan itself admits
screens will be wide, *that is the modal outcome*, which would have read as "not rejected → accepted".
Three states now, matching `paired_delta`'s verdict space:

- **REJECT** — CI excludes 0 in the harmful direction.
- **ACCEPT-PROVISIONAL** — CI lies entirely within ±5pp.
- **INCONCLUSIVE** — neither. **Action: do not ship; needs a targeted higher-n follow-up.** Not a
  synonym for accept.

Never claim "proven equivalent": certifying |Δ|≤5pp needs n≈628 paired items (and that figure rests
on a generic `p_d=0.20` never validated for this axis, so treat it as an order of magnitude).

Screen where low-bit KV degrades loudest, per the campaign's own parked kv3 analysis: **multi-needle
retrieval at depth** and **multi-step math**. Short-chain coding is ceiling'd and was already
identified as too weak a gate.

**And [FIXED]: if a squeezed KV is accepted, the coder verdict must be re-confirmed under it**
(cheap aider re-run, n≈30). Rev 1 would have shipped a coder measured at one KV and served at another
— an OFAT violation the plan enforces everywhere else.

## R6 — Repo-level means a REPO, not a big context window **[FIXED]**

Rev 1 operationalised "repo-level" as a padded token budget with an unnamed task. The goal-alignment
reviewer correctly called that the same substitution the operator warned against, one level removed
from a needle.

**`benchmark/bench/run_swebench.py` and `swebench_adapter.py` already exist and have never run.**
That is the campaign's own designated repo-level axis: real multi-file repos with genuine cross-file
coupling. It replaces the synthetic padded task as the repo-level probe.

Context reach is still measured separately as a curve (it answers G4, not G6):

| component | tokens |
|---|---|
| repo map / skeleton | 10–30K |
| 5–15 open files | 20–60K |
| conversation by ~turn 40 | 50–100K |
| **total** | **~80–190K** |

So **128K is the practical repo-level floor, 256K comfortable headroom**. Report the curve; eliminate
early only if a model is file-level only (<32K effective). Keep retrieval-depth and reasoning-depth
curves separate.

## R7 — Harnesses as a gradient, gated on a go/no-go smoke **[FIXED]**

**pi** (minimal: 4 tools, <1K-token system prompt) → **aider** (mid) → **opencode** (heavy, declared
primary driver). Ordered by scaffold weight this turns the harness confound into a measured axis: a
model that collapses on the minimal harness is scaffold-dependent; one that holds is intrinsically
capable.

Rev 1 costed this as ~20 compute-hours. **It is mostly unbudgeted ENGINEERING**, and one blocker is
documented in our own repo:

- `opencode_config/README.md` records **opencode#5674** — the bundled `@ai-sdk/openai-compatible`
  provider "doesn't forward the `options` block (including `baseURL`)", calling custom endpoints
  "currently unusable" (version-dependent). Sampling/thinking forwarding is flagged
  **"best-effort, verify"**, with a documented 2048-truncation trap.
  **If options don't forward, opencode silently ignores the tuned sampling we are testing** — which
  would invalidate any tuned comparison run through it.
- **pi has zero footprint in this repo.** No clone, no venv, no emitter, no confirmed
  non-interactive mode.
- Neither has an equivalent of aider's `benchmark.py` (setup → prompt → apply → test → score).
  Precedent: aider, a mature integration, burned five void run-tags before a clean baseline.

**Gate: a 1–2h go/no-go per harness BEFORE any scaffold work**, verifying (a) the request reaches
:8000, (b) the tuned sampling actually lands — read back from the worker log, not assumed — and
(c) a genuinely scriptable non-interactive mode exists. No pass, no spend.

## R8 — The daily role needs its own axes **[FIXED]**

Rev 1 was 8-of-10 coding work wearing a two-role label, and it named the Ornith convergence issue
"critical path" while scheduling no row for it. Both fixed.

| role | primary axes | status |
|---|---|---|
| **CODER** | terminal solve rate through harnesses, repair rate, edit-format reliability, repo-level (SWE) | mostly built |
| **DAILY** | TTFT + decode, convergence, reasoning, **instruction-following**, retrieval, **multi-turn chat** | two gaps below |

- **IFEval is broken** (`datasets` "Feature type 'List' not found") and rev 1 had no repair item. Now
  scheduled. It is a named daily axis with no working harness.
- **No conversational eval exists at all.** All three harnesses are coding scaffolds. A lightweight
  judged multi-turn chat/instruction eval is now scheduled — otherwise "daily driver" is asserted,
  not measured.
- **Ornith's convergence claim is narrowed [FIXED].** Rev 1 cited three axes bare. With intervals:

| axis | Ornith | distill | verdict |
|---|---|---|---|
| math500 | 70% [52.1, 83.3] | 100% [87.5, 100] | **non-overlapping — supported** |
| LCB | 80% [54.8, 93.0] | 100% [79.6, 100] | overlapping — not established |
| AIME | 80% [37.6, 96.4] | 100% [51.0, 100] | n=5, worthless |

  So the concern rests on **math500 alone**, not three axes. Still enough to schedule the temp-ladder
  for the daily role, but the honest framing is one resolved axis. **Provenance caveat:** those rows
  were re-graded from files generated under the OLD 256K-KV config, while `m1f` measures 100% agentic
  convergence for both models at the current config. Confirm which config produced them before
  treating them as current.

## Sequenced work — costs derived from MEASURED rates **[FIXED]**

Rev 1 used round numbers. Measured: **Ornith 2.2 min/case, distill 6.3 min/case**. `tries=4` is
assumed 1.5× the 2-attempt cost. Model multiplier stated explicitly everywhere.

| # | Work | Gate | Hours |
|---|---|---|---|
| 0 | `m1f` completes (baseline, shipped sampling) | — | ~6 remaining |
| 1 | **Go/no-go smokes: pi, opencode** (endpoint + sampling landed + scriptable) | — | 2–4 |
| 2 | Port harness-agnostic heartbeat (router/RAM/500s/driver-alive) | — | 1 |
| 3 | Tier-0 grid, 9 configs × 30 items × 2 models + collapse test | 0 | ~13 |
| 4 | ρ + permutation p on the Tier-0 grid vs target subset | 3 | ~6 |
| 5 | Tier-1 agentic tune, 3 configs × 44 × 2 models @ `tries=4` | 4 | ~28 |
| 6 | Tier-2 confirm on held-out exercises, tuned vs shipped | 5 | ~14 |
| 7 | Ornith temp-ladder re-check (daily role, math500 convergence) | 0 | 2 |
| 8 | IFEval repair + run (daily axis, currently broken) | — | 3 |
| 9 | Multi-turn chat/instruction eval (daily axis, missing) | — | 6 |
| 10 | BFCL thinking-ON repair (fixes a broken powered axis) | — | 6 |
| 11 | Harness gradient: pi + opencode on pinned items | 1, 2, 6 | ~24 |
| 12 | SWE-bench repo-level (already built, never run) | 1, 2 | ~20 |
| 13 | Effective-context curves, task-based | 6 | ~12 |
| 14 | KV squeeze TOST screens + coder re-confirm | 13 | ~20 |
| 15 | Judge panel v3 (meta-judge) | 0 | local |

**~185 worker-hours ≈ 8 days continuous on one box.** Rev 1 said ~104; it was ~1.8× optimistic.

## G1 — cost to onboard model N+1 **[FIXED]**

Rev 1 never separated one-time infra from recurring per-model cost, so it was unverifiable whether
this is a pipeline or a bespoke study.

- **One-time infra** (steps 1, 2, 8, 9, 10, 12 scaffolding): ~45h. Paid once.
- **Per new model** (steps 3–7, 11, 13, 14 at single-model scope): **~55–60h ≈ 2.5 days.**
- Reusable free: harness integrations, monitors, pinned item sets, graders, judge pipeline.

If ~2.5 days/model is too expensive, the honest lever is dropping Tier-1 to one language (−12h) and
the harness gradient to two harnesses (−8h), at the cost of a wider MDE.

## Standing discipline

- **Gate every step transition**, not just campaign start: `ps -E` (no APC), `lsof` (single router),
  free-RAM floor, single driver, single heartbeat, registry hash unchanged. Multi-day occupancy is
  the exact window in which this project has previously acquired a co-resident model and a stale env.
- **Declare the test family up front and run every verdict through `stats.holm`.** The family here is
  substantially larger than the ~30 that already implies a 79% chance of one spurious "better".
- **Bump the run tag after any config change.** Results glob by run name.
- **Thinking always on**, verified by token accounting rather than config.
- `tries=4` yields an ordinal turn-of-convergence outcome. Rev 1 called this "the main lever" for
  power; that was unquantified, `stats.py` has no ordinal statistic, and repair attempts are not
  independent (they share prior context). **Downgraded to a hypothesis: derive and validate the power
  formula before relying on it.**
