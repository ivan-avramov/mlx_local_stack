# Open questions & judgement calls — the operator's decision queue

Created 2026-08-13 at operator request. **Purpose:** one place for things that need the operator's
judgement, plus decisions already made so they are not re-litigated. Companions:
`docs/PLAN.md` (the plan + work queue), `docs/campaign-results.md` (results), `AGENTS.md` (rules),
`docs/handoff.md` (last session).

**Rules for this file.** An item is added the moment a judgement call is identified, not when it
becomes urgent. An item is either **OPEN** (needs the operator), **CLOSED** (with the decision and
its date), or **CLOSED-BY-MEASUREMENT** (the question dissolved because data answered it — record
the data, because "we decided" and "we measured" age differently). Nothing is deleted; a closed item
is the record that stops it being re-asked.

---

## OPEN — needs operator judgement

### O38 — CLOSED 2026-08-23 — provisional C picks recorded before C is instrumented

Operator decision 2026-08-23: record `Ornith-1.0-35B-mlx-uniform-4bit` +
`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` as PROVISIONAL C 1st/2nd in `main_models.yaml`,
explicitly labelled provisional, to be revisited when M18 BFCL + the judge panel land. The
session's dissent, recorded for the revisit: on today's C-relevant evidence
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` has the better claim than `Ornith-1.0-35B-mlx-uniform-4bit`
— math500 at matched budget splits `acc_strict` 81.5% vs 60.0% (`Ornith-1.0-35B-mlx-uniform-4bit` hits the thinking
budget on 9/30 items), IFEval is a tie — but that split is n=30/27 unmatched at MDE ±23pp
(suggestive, not a verdict), and model-diversity across B/C favors the operator's pair.
`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` is uncontested as the other pick (ties every
measured capability axis at 26.0 GB peak; its tune is NOT laddered — flagged in the registry).
Uploads: `caslca/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` mirror +
`caslca/Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` (circulation model) launched 2026-08-23.
**REVISED same day: the operator adopted the session recommendation** ("mine was based on
vibes") — provisional C picks are now `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` +
`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`; `Ornith-1.0-35B-mlx-uniform-4bit` stands down
to B-only. Both picks were already public on HF, so no new upload was triggered.

### O37 — CLOSED 2026-08-23 (ratified) — certify t0.55 as the tune for `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit`?

Filed 2026-08-23. The M20 deployed ladder completed the full sequence (capped scan →
DNF-first → n=15 rung → gate-3 2×50), every command `--sampling-profile deployed` explicit.
Gate-3 vs the t0.6 baseline (paired items/seeds, budget 81920): humanevalplus t0.55
`acc` 83.7% [73.5, 93.9] / `acc_strict` **82.0%** / **1 DNF** vs t0.6 88.4% [79.1, 97.7] /
76.0% / **7 DNFs**; mbppplus t0.55 77.8% [64.4, 88.9] / **70.0%** / 5 DNFs vs t0.6 79.1%
[67.4, 90.7] / 68.0% / 7 DNFs. The ranking key (`acc_strict@81920`) favors t0.55 on BOTH
benches (+6.0pp hep, +2.0pp mbpp); DNF total 14→6 (hep 7→1; mbpp keeps hard core
{306,620,739}, fixes 4, mints {793,806}); exclusive solves crossed 7 vs 3 favoring t0.55;
zero loops either arm; conv 100% on all generated rows. `acc` over generated items has
lower t0.55 point estimates (−4.7pp hep, −1.3pp mbpp, MDE ±18pp) but that comparison is
denominator-skewed: t0.6's `acc` excludes its 7 DNFs — the hard items — from the
denominator, which is exactly the conditioning pathology `acc_strict` exists to avoid.
**Recommendation: certify t0.55** — it is the ladder's own decision rule (highest temp that
converges without a pass@1 regression: the rung held 13/15 vs 13/15 paired; gate-3 shows no
resolvable regression and a strict win). **CLOSED 2026-08-23 — operator RATIFIED: t0.55
certified.** Fan-out audit: the model appears in NO client carrier (not a shipped model), so
the certification is registry-only — `main_models.yaml` `generation_defaults` now records
`temperature: 0.55` with the certification note. Same pass recorded the M19-certified t0.6
for `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` and the 2026-08-17-certified t0.6 for
`Qwen3.8-27B-mlx-uniform-4bit` (both had carried the checkpoint-default 1.0).

### O36 — `run.py generate` defaults to the RETIRED `production` sampling profile; should `deployed` be the default (or the flag REQUIRED)?

Filed 2026-08-22 after it burned a full pipeline: every M19/M20 t0.5 command (scan, DNF-first
probes, both n=15 rungs, both gate-3 2×50 arms — ~20 h of GPU) omitted `--sampling-profile
deployed`, so all of it silently ran at `production` (min_p 0.03, presence_penalty 0.3,
max_tokens 81920 → resolved thinking_budget 49152) — four knobs moved at once instead of a
temperature OFAT, and a nonzero presence_penalty also changes the serving path. **The
fingerprint guard caught it** (compare REFUSED across thinking_budget) — the rows are
quarantined under tune `t0.5prod` and the pipeline re-run at `deployed`. The footgun: the
default profile is the one AGENTS.md says is kept only for historical rows and has DRIFTED
from what we ship. Options: (a) default to `deployed`; (b) no default — make the flag
required so every run states its profile; (c) keep `production` default (compat) + a loud
warning. (b) is the safest against silent drift; (a) matches "served config == measured
config". Needs a ruling before any code change (TDD once ruled).

**1 item (O36).** (O24, O26, O27, O28 and O29 were closed on 2026-08-16 (old driver box),
O25 and O30 on 2026-08-17 (this box; merged 2026-08-18), O15 on 2026-08-18, O34/O35 on
2026-08-20; nothing was deleted.)

### ~~O34~~ → RULED (operator, 2026-08-20): **approved as proposed — shipped same day (TDD).** `provenance._home_normalized` emits `$HOME`-form `hf_path` at manifest-write time; committed manifests (already hand-sanitized to that form) now match by construction. The four live-chain manifests stamped pre-fix were sed-sanitized in place. Original text:

O34 — manifest writer should emit `$HOME`-form `hf_path` (recurring PII restamp + false STALE)

Manifests for models with local `hf_path` record the absolute path. The committed copies are
hand-sanitized to `$HOME`, so every resume restamps the live absolute path back in: (a) PII sits in
the working tree until someone re-sanitizes before commit (the hook is the only backstop), and
(b) the provenance string-compare sees `$HOME/...` vs `/Users/.../...` as a CONFIG CHANGE — on
2026-08-20 this flagged `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit`/humanevalplus STALE and
restamped both `Qwen3.8-27B` distill manifests <!-- allow-shorthand --> on a config that was
byte-identical (verified: only timestamp/stack_head/hf_path-form differed; the run was killed,
verified benign, relaunched). Proposed fix (small, TDD): normalize `hf_path` under `$HOME` at
manifest-write time; existing sanitized manifests then match by construction. Needs approval —
it touches provenance strings mid-corpus (committed manifests already use `$HOME`-form, so the
normalization CLOSES the gap rather than widening it).

### ~~O35~~ → RULED (operator, 2026-08-20): **approved as proposed — shipped same day (TDD).** Classification happens at WRITE time, where the context exists: error rows now record `wall_s`, and `generate.error_kind` stamps `error_kind: probe_timeout` when elapsed ≥ 0.9× the configured probe timeout. `done_keys`/`done_ids` count such rows as DONE (a DNF); fast failures (connect refused, transient network) carry no `error_kind` and stay retryable, as do all pre-existing error rows (no `error_kind` field — the field is the opt-in). `--samples k` fresh-seed draws unaffected. Original text:

O35 — resume rule: skip retrying an error row whose failure was a probe-timeout (deterministic runaway)

`generate` resume treats error rows as not-done and retries them. Seeds derive from (item, sample),
so a probe-timeout runaway retries BYTE-IDENTICALLY: measured on `Mbpp/306`
(`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` t0.3, 2026-08-20) — the retry burned a second full 3600s
probe-timeout, plus ~13 min of server-side drain after EACH client abandonment (the server decodes
to budget exhaustion; 82,123 tokens at 73 min for the first occurrence), ~2.4 GPU-hours total for
one item, and left a duplicate error row (deduped by hand, backup in `$STACK_WORKDIR/status/`).
Proposed rule: on resume, an existing error row whose kind is probe-timeout at the SAME
(seed, sampling, cap) fingerprint counts as DONE (a DNF), not retryable; `--samples k` draws with
fresh seeds are unaffected. Needs a ruling because it changes what a resume measures (a transient
infra timeout would also stop being retried — possibly gate on `wall_s >= probe_timeout`).

### O33 → RULED AT CREATION (operator, 2026-08-18): **the `Qwen3.8-27B` family <!-- allow-shorthand --> is characterized at `reasoning_effort` xhigh — its best performance and how it ships.** Context: the checkpoint chat template defaults `reasoning_effort|default('xhigh')` whenever thinking is on, no carrier/bench request ever sets the variable, and the fork forwards it only when set — so the entire existing corpus is ALREADY xhigh and stays admissible unchanged (lab notebook 2026-08-18). Consequences: (1) no medium/low arms for ranking/characterization — the floated "effort as a runaway-tax lever" OFAT is NOT queued (the >1h runaways happen at xhigh and are handled by the temperature recipe + probe-timeout DNF accounting); (2) if effort is EVER varied for any future serving experiment it changes the rendered prompt and must join the provenance fingerprint first; (3) clients ship with no `reasoning_effort` set, so served config == measured config holds by default.

### ~~O31~~ → RULED (operator, 2026-08-18): **(a) — error rows count as FAILURES in acc_strict's denominator.** Shipped same day: `grade._postprocess` appends every error row as a 0-score strict item (TDD, `test_error_rows_count_as_FAILURES_in_acc_strict_never_exclusions`); the comparability audit found ALL 7 affected corpus score files had used the old exclusion consistently, so one re-grade pass restored comparability (`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` ifeval 0.9014→0.8649, math500 0.8148→0.7333, mbppplus 0.8283→0.82, aime 1.0→0.8; `gemma-4-31B-it-qat-6bit` humanevalplus strict →0.7692; `Qwen3.8-27B-mlx-uniform-4bit` t0.7 diagnostic →0.6); scoresheet regenerated under the new definition. `acc` keeps its historical generated-only meaning. Original text retained:

### O31 (original text, retained). A harness-error row (client timeout, no text) is EXCLUDED from acc_strict's denominator — is that the right reading of the DNF rule?
Raised 2026-08-18, from the ifeval cap pilot. `grade` counts error-stub rows in a separate
`errors` field and drops them from `n` (pilot: n=142 of 148, acc_strict 0.9014). The
acc_strict ruling says a DNF counts as a FAILURE in the denominator, never an exclusion — and
a row that decoded for 3600 s without self-terminating is behaviorally a DNF even though no
text was persisted. Honest-denominator read of the same run: 128/148 = 0.8649. The
counter-argument: an error stub is RETRYABLE harness state (a resume regenerates it), so
scoring it as a model failure conflates harness availability with capability. Needs a ruling:
(a) error rows count as failures in acc_strict (matches the DNF ruling's letter), or (b) they
stay excluded but every published acc_strict must also quote the error count (status quo,
made explicit). Either way the pilot's two numbers are both recorded in the results commit.

### ~~O32~~ → CLOSED (operator, 2026-08-19): **NVSY is UNTRACKED — out of the campaign queue entirely.** The operator will revisit after the campaign establishes the local models; `docs/switchyard-plan.md` remains the ready-made plan for that day. Original text: Expand scope to a weak/strong ROUTER system (NVIDIA switchyard: local pick + cloud frontier)?
Raised 2026-08-18 by the operator: test a routing layer that fronts the local B pick (weak/cheap)
and a frontier cloud model (strong/expensive), routing per request — a way to make the SYSTEM
(the daily coder) meaningfully better at small $ cost, usable as a daily option.

**Architect assessment (recommendation: YES, in scope as a new SYSTEM track — parked behind the
current B queue, entered via a cheap spike):**
- **The harness points at it almost for free** if the router speaks OpenAI-compatible HTTP: our
  axes drive an endpoint, so a router is just a new base URL. Provenance already separates it —
  a router row is a different `client`/serving path, and `compare` refuses pooling with model rows;
  it becomes a SYSTEM entry in the ledger under a (system, config) extension of the (model, tune)
  taxonomy (config = routing policy + budget).
- **The decisive instrument already exists**: matched-item paired runs + EXCLUSIVE-SOLVE SETS.
  Three arms on the same seeded items — local-alone, router(local+frontier), frontier-alone —
  answer the router's whole value question: does the composed system recover the items the local
  pick misses, at what routed share, at what $ per task? Report quality + $/task + route-share;
  rank on capability per the standing rule.
- **New metrics needed (small)**: cost-per-task and route-share per row; a `system` ledger section.
- **Real dollars enter** (frontier API on routed items) — bounded: n=100 coding at ~30% routed is
  a few $ of Sonnet-class usage per arm. Pilot rule applies.
- **Scope guard**: does NOT displace the current queue (Stage-2 screens, M11/M12, opencode Runs
  A/B). Proposed entry: **S1 spike** — stand switchyard up, point the T1-style smoke at it (n=15),
  record route-share/cost/latency mechanics; design the real three-arm eval only if the spike is
  clean. Needs an operator go + which frontier arm (claude-sonnet vs claude-opus class) + an API budget cap. <!-- allow-shorthand -->

**UPDATE 2026-08-18 (discussion held; still OPEN pending the operator's go):** the track now has
its own plan — **`docs/switchyard-plan.md`** — capturing the full design: Switchyard co-released
with `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` making it the natural weak-tier candidate;
escalation routing re-weighting weak-tier selection toward count/rate axes (convergence,
malformed-edit rate) over pass@1; the operator's tune-certification prerequisite (certified tunes
before any pairing — the M3/M4/BFCL block doubles as that certification); sequencing as a reorder
(S1 spike + M3/M4/BFCL pulled ahead of M11/M12), not a queue-jump; and the four pending operator
decisions with standing recommendations (go, Sonnet-class frontier arm, $10 spike cap, prebuilt
binary under `$STACK_WORKDIR/switchyard/`).

### ~~O15~~ → CLOSED-BY-POLICY (operator, 2026-08-18)
The operator confirmed the protection hypothesis from their OWN original measurement: they ran an
actual prefill test and OBSERVED the OOM when realloc-based cache growth was used — that observation
is what prompted adding `kv_prealloc_tokens` alongside the cap config in `main_models.yaml` in the
first place. So both halves are now settled: **inflation excluded by measurement** (the 2026-08-14
depth datum below: peak did not rise when prealloc doubled with the cache genuinely grown to 131K),
**protection confirmed by the operator's observed OOM**. The discriminating re-test (a prealloc-OFF
arm at 262144) would deliberately OOM the daily-driver box to re-demonstrate something already
observed once, for zero actionable payoff — the rule (prealloc = cap) costs nothing at peak and
stays. Closed; the two sections below are the record.

### O15 — NEW DATUM 2026-08-14 (superseded by the closure above; one wrong reading excluded)
A DEPTH test at last, from the `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` ladder. Same model, same item set, **same context
`ctx=131072`**, only `kv_prealloc_tokens` differing — and unlike my invalid probe, the cache genuinely
grew to 131K:

| prealloc | `mx.get_peak_memory` at ctx=131072 |
|---|---|
| 131072 | 25.5 GB |
| 262144 | **23.7 GB** |

**Peak did NOT rise when prealloc doubled — it fell 1.8 GB.** So "prealloc inflates peak memory" is
EXCLUDED: peak is set by the prefill spike, not by the reservation. Two readings survive and this datum
does not separate them: (1) the reservation genuinely costs nothing at peak, making prealloc free
insurance; (2) the 1.8 GB is run-to-run variance — the two ladders had different idle baselines
(32.39 vs 12.50 GB) and a fresh process.

⚠️ **This does NOT answer what O15 actually asks** — whether prealloc PREVENTS the growth OOM — because
prealloc was ON in both arms. That needs a prealloc-OFF arm at 262144, i.e. deliberately walking into the
known OOM path, which the operator has ruled against. **So O15 stays open by design**, with the
inflation hypothesis eliminated and the protection hypothesis untested.

### O15 (original). Does prealloc actually reserve RAM? — MY EVIDENCE WAS INVALID; the question needs a DEPTH test
⚠️ **I raised this on a measurement that cannot support it, and the operator caught it.** I compared
`mx.get_peak_memory` across prealloc arms (25.35 / 25.50 / 28.18 GB) and inferred the reservation was
"lazy or unwired". **But the probe item generated only ~2,868 tokens, so the KV cache never grew past
~3K of a 131072/262144 capacity.** A virtual allocation that is never touched costs no resident pages,
so those peaks measured weights-plus-a-tiny-cache in all three arms. The ~2.8 GB delta is not evidence
of anything about the reservation.

**Operator datum that outranks my inference: an actual OOM was hit in testing.** So the double-buffer
growth spike is real and the protection matters in practice.

**The test that would actually answer it** — and the only one that should be cited on this — is a
LONG-CONTEXT run that grows the cache to the full cap:
- drive a prompt/generation to >128K so the 128K→256K growth boundary is crossed;
- sample `mx.get_peak_memory` AND resident memory as it grows, prealloc ON vs OFF;
- expect, if prealloc works: a large step at LOAD (or first touch) and NO spike at the boundary; if it
  does not: a small load footprint and a ~1.5× spike at the boundary, i.e. the OOM path.
**Recommendation: do NOT change prealloc, and do not cite peak-memory numbers from short-generation
probes for anything memory-related.** The 46GB gate is defined on the prefill spike for exactly this
reason — a short probe cannot see it.

**Standing lesson: a memory measurement is only valid at the depth it claims.** Every arm of my OFAT
was ~3K tokens deep, so it was a fair test of "is the shipped config slow on a short item" (which is
what the retracted claim was about, and it answered it) and NOT a test of anything at capacity.


---

---

## CLOSED — decisions and rulings, newest first

**Nothing here needs action.** Kept verbatim, including the "original text retained" blocks, because
the record of *why* something was decided is what stops it being re-litigated. (The OPEN/CLOSED split
dates from the 2026-08-16 fold: 25 of the 37 blocks were already closed, so the decision queue had
become two-thirds archive. Nothing was deleted.)

### RENUMBERING NOTE (2026-08-18, merge of the two driver boxes' parallel sessions)
Both boxes independently allocated **O28** on adjacent days: the old driver box for the
presence_penalty/suffix gate (below, closed 2026-08-16), this box for the inert-seeds finding
(raised 2026-08-17). First allocation keeps the number; the seeds item is **renumbered O30**.
Citations of "O28" in code/commits from 2026-08-17 (the `run.py --samples` guard, the M1 row,
the lab notebook) refer to **O30**.

### ~~O30~~ → RULED (2026-08-17): operator took the recommendation — (b) now, (a) when the fork is next opened.
`run.py generate` now REFUSES `--samples > 1` with an O28 citation (guard + test landed same day). The fork fix (thread each request's seed into its rows' keys in the batched decode) is queued for the next fork-opening; the guard comes out when a 2-seed byte-difference probe passes.

**O30 UPDATE 2026-08-18 — THE FORK FIX IS BUILT, COMMITTED IN THE FORK (`ab5273f`), NOT YET
DEPLOYED.** Sonnet worker, architect-verified (697 fork tests re-run green): per-request seeds
now thread through `BatchGenerator.insert()` → `GenerationBatch`/`PromptProcessingBatch` →
`_position_keys`, defaulting to the old single-shared-seed behavior when omitted; speculative
path untouched. ⚠️ **Deployment is a deliberate decision, not a routine bump**: for seeded
harness runs the fix is OUTPUT-DETERMINING (pre-fix, every row after the first decoded under
the FIRST request's seed — so the entire seeded k=1 corpus was generated under first-request
seeds), meaning the submodule bump splits the corpus at that sha exactly like the 8b7100b8 →
0c1c8b17 split. Bump at a corpus boundary (e.g. after the current Stage-2/M3/M4 block), then
`--samples` designs become valid.

### O30 (original text, retained — the ruling above supersedes the question).
Raised 2026-08-17, from the M1 re-draw probe (full evidence in `docs/lab-notebook.md`, same date).

Measured: two draws of HumanEval/71 (`Ornith-1.0-35B-mlx-uniform-4bit`, deployed profile,
suffix-OFF) with different declared seeds came back **byte-identical over 82,169 tokens**.
Mechanism: the fork's batched decode keys draws by `(batch-generator seed, row 0, position)` —
one sampler per `BatchGenerator`, built from the FIRST request's args, `row_ids` always
`[0]*B` — so `rowschema.sample_seed` is recorded per row and never in force. The 2026-08-11
"seeds work" measurement certified the SUFFIX path, which the campaign no longer serves.

No existing corpus row is invalidated (k=1 everywhere outside the OFAT, whose ON/OFF pairing
is unaffected), but every multi-sample design (`--samples k`, pass^k, reliability) is void
until one of:
- **(a) Fix the fork** — thread each request's seed into its rows' keys in the batched decode;
  submodule bump; re-verify with a 2-seed byte-difference probe. Real fork surgery on the
  batching hot path.
- **(b) Accept single-sample designs** — remove/refuse `--samples > 1` on this serving path so
  the harness stops silently producing copies, and spend on ITEMS (which the power doctrine
  prefers anyway).
Recommendation: **(b) now** (one guard clause, honest immediately) **+ (a) when the fork is
next opened** — multi-sample reliability is a stated future endpoint and (a) is the only route
to it.

### ~~O28~~ → CLOSED-BY-CODE-READING (2026-08-16): **the gate EXISTS and AGENTS.md was RIGHT.** But the interesting finding is that the lever is not worth using anyway.
`_suffix_structured_fallback` — `src/mlx-vlm/mlx_vlm/generate/ar.py:163`, called at `:648` to decide
whether to enter `run_speculative_rounds` at all. Its docstring names the case outright: *"sampling
penalties (repetition / presence / frequency / `logit_bias`) … would otherwise be silently dropped on
the speculative path, changing the distribution."* Suffix's verify samples raw target logits over a
whole draft block and can apply no processor, so the code chooses correctness over speed. **A better
reason than the folklore version:** it is not that the penalty breaks suffix, it is that suffix cannot
apply penalties. Missed previously because the function reads as structured-output-only while handling
both cases through a generic `processors` list — searching near `presence_penalty` never reaches it.
So `presence_penalty: 0.0` in all four carriers is load-bearing **while suffix is on**, and the two are
STRICTLY MUTUALLY EXCLUSIVE per request.

**AND THE LEVER IS A NO-GO ON ITS MERITS — measured, not argued** (full analysis in
`docs/lab-notebook.md`):
- **`make_presence_penalty` has `context_size` 20** (additive, binary-on-presence). It can only reach
  verbatim cycles of period ≤ ~20 tokens; beyond that the prior occurrence is outside the window and the
  penalty is not weakened but **exactly zero**.
- **Of 54 classifiable nonconverged rows, 17 are reachable — and ALL 17 are on ifeval. ZERO on
  humanevalplus or mbppplus**, where every measured cycle is 40–262 tokens per period.
- **Crossing reachability against pass/fail leaves 6 items on ONE model** (`Ornith-1.0-35B-mlx-uniform-4bit`
  ifeval) and **0 on the other**. A perfect fix is **1.1pp** of `acc_strict` against that arm's own MDE
  of **±5.4pp** — while changing the sampling of 11 currently-PASSING rows too, so the expected accuracy
  effect is plausibly negative.
- **Loops cost TIME, not accuracy** (verified independently): **6 of 10** degenerate coding rows still
  PASSED their plus-tests, and 18/29 and 7/10 of the nonconverged ifeval rows passed. The budget clamp
  injects `</think>`, the model then writes a correct answer. The loop burned the budget, not the answer.
- **The natural experiment has already run and is negative:** `gemma-4-31B-it-qat-6bit` and
  `gemma-4-26B-A4B-it-OptiQ-4bit` ship `repetition_penalty: 1.08` and hold the corpus's **two worst**
  convergence rates (0.727 / 0.833 vs ≥0.90 everywhere else), still producing 71- and 262-token cycles.
- **The vendor pins 0.0 for THINKING mode specifically** (1.5 for non-thinking) and warns of "language
  mixing and a slight decrease in model performance". Mechanism: chain-of-thought is structurally
  re-entrant — it restates, re-derives, enumerates, checks — so a 20-token window taxes the working
  vocabulary of a re-derivation. Under the lexicographic rule (pass@1 hard, convergence strictly within
  it), a lever with a ≤1.1pp ceiling and a documented performance cost fails on its face.

**Consequence recorded, not acted on:** with suffix OFF, `presence_penalty` is currently a FREE knob —
it is just not a useful one for this failure mode. The lever this campaign has PROVEN for it is
temperature. Original text retained:

### O28 (original text, retained). `AGENTS.md` asserts that a nonzero `presence_penalty` disables suffix decoding — and nobody has found the gate
Raised 2026-08-16 while retiring the handoff docs (the observation itself dates from the O11 work).

`AGENTS.md` states this **three times**, and it is the stated REASON all four sampling carriers ship
`presence_penalty: 0.0`. But a read of the fork found **no such gate** — only the structured-output one.
So one of two things is true, and they have different consequences:

- **The claim is right and the gate is somewhere we did not look.** Then `presence_penalty 0.0` is
  load-bearing and must stay, and the gate should be cited by file:line so it stops being folklore.
- **The claim is wrong.** Then `presence_penalty` is a free sampling knob we have been holding at 0.0 for
  an imaginary reason — and since a nonzero penalty is one of the few untried levers against the runaway
  tax (the campaign's largest measured cost), that is a real opportunity, not just a doc fix.

Note this is now **lower stakes but not moot**: suffix is OFF everywhere as of 2026-08-16, so nothing is
being disabled today. It matters for the O25 return condition and for any penalty cell.
**Cheap to settle:** grep the fork for the gate; if absent, run one paired probe at
`presence_penalty` 0.0 vs 0.3 with suffix ON and compare accepted-draft counts.
**Needs a ruling only on whether to spend the probe** — the grep is free and should happen either way.

### ~~O27~~ → CLOSED (operator, 2026-08-16): **WAIT for GitHub's own gc.** No Support request, no repo
recreation. The leaked string is a username in a home path — real PII and correctly scrubbed from the
branch-reachable history, but not credential-grade — and the unreachable objects expire on GitHub's own
schedule. Accepted risk: until then the pre-scrub commit remains fetchable by anyone who knows the sha.
Recurrence is already blocked by `bench.piicheck` in `githooks/pre-commit`. Original text retained:

### O27 (original text, retained). Does the GitHub remote still need a `gc` to finish the PII scrub?

Raised 2026-08-16, during the scrub itself.

11 tracked files carried an absolute home path with a real username into this PUBLIC repo (the
`hf_path` field of 10 provenance manifests plus one `bfcl.json` traceback), all introduced by the
bulk import of 286 result files. History was rewritten with `git filter-repo --replace-text` and
force-pushed; a mirror clone confirms the branch-reachable history is clean.

**But the pre-scrub commit is STILL FETCHABLE from the remote by explicit sha** — `git fetch --depth=1
origin <old-sha>` returns rc=0 and the old tree. Unreachable objects survive a force-push until
GitHub garbage-collects, so the leaked blobs remain retrievable by anyone holding the sha.

**Two ways to finish it:** (a) a GitHub Support request asking them to run `gc` on the repository —
cheap, non-destructive, and the standard remedy; or (b) delete and recreate the remote repository —
instant and total, but discards stars/watchers/issues. **Recommendation: (a).**
**RULED (operator, 2026-08-17): option (b) — delete/recreate — if anything is worth keeping.
LATER THAT DAY: operator dropped the item from tracking entirely ("don't care"). Not tracked
anywhere; this entry is the record.**
Guard against recurrence is already in place: `bench.piicheck` in `githooks/pre-commit`, validated
end-to-end against a staged leak, plus a corpus-wide test asserting every tracked file is clean.

### ~~O29~~ → CLOSED (operator, 2026-08-16): **WARN, do not refuse — and track the cap so failed cases can be re-run.** Shipped: `compare` warns and reports both RESOLVED budgets, and `compare.cap_partition()` names the rows the cap could have touched. The operator's reasoning is what made it useful: the cap is a ceiling enforced OUTSIDE the model, so it cannot have affected a row that finished well under it. Measured consequence — only **39 of 889** draws across the three IFEval arms are cap-sensitive (29 / 10 / 0), so the re-run is 22.8x cheaper than the axis re-run originally planned. Original text retained:

### O29 (original text, retained). `compare` does not refuse across a KV-CAP mismatch — the same class of gap as the suffix one, and it bites the published three-way IFEval verdicts
Raised 2026-08-16 while auditing per-model coverage.

`max_kv_cache_size` is OUTPUT-DETERMINING and AGENTS.md says so explicitly: it sets the **resolved
thinking budget** via the server's silent `0.8 × (cap − prompt)` clamp. It is in the provenance
fingerprint, so `--clean-stale` and resume both see it. **But `compare` does not check it** —
`_MUST_MATCH_SAMPLING` is `("thinking_budget", "max_tokens")`, i.e. the DECLARED values, which are
identical across these runs while the RESOLVED ones are not.

Measured on the rows we actually published:

| arm | cap | resolved thinking budget |
|---|---|---|
| `Ornith-1.0-35B-mlx-uniform-4bit` ifeval (n=541) | 65536 | **~52,268** |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` ifeval (n=148) | 65536 | **~52,268** |
| `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` ifeval (n=200) | 262144 | **81,920** |

**So the two `--intersect` verdicts against the candidate compared models allowed 1.57× more thinking
than the winners were** — on top of the suffix-state mismatch already recorded. Both verdicts are
INCONCLUSIVE so nothing flips, but this is the second output-determining knob found unguarded in one
day, by the same method: ask what differs between the rows rather than trusting the guard list.

**Recommendation: fix the guard (cheap, driver-side, mirrors the `draft_kind` refusal added today) and
re-run the winners' IFEval suffix-OFF at a MATCHED cap** — which is already queued as `docs/PLAN.md`
§3 item #5, and should now specify the cap, not just the suffix state. **Needs a ruling only on
whether the guard should refuse or warn** for a cap mismatch: refusing is stricter and correct in
principle, but it will retroactively block some existing comparisons, so it is the same
non-destructiveness question the v3 fingerprint had to answer.

left a durable RULE, that rule has been copied into `AGENTS.md` — a rule buried in a closed decision
is a rule nobody finds.


### ~~O26~~ → CLOSED-BY-IMPLEMENTATION (2026-08-16): the columns are RENAMED and both are published.
"degenerate wall-share" named **three** different quantities. My original entry (retained below) got two
of them wrong, so the corrected measurement is here at the top:

| pair | `degenAllWall%` (published; every row whose trace loops) | `degenEosedWall%` (persisted; SELF-TERMINATING loops only) |
|---|---|---|
| `Ornith-1.0-35B-mlx-uniform-4bit` humanevalplus | **39.66%** (4 rows) | **4.77%** (2 rows) |
| `Ornith-1.0-35B-mlx-uniform-4bit` mbppplus | **63.07%** (4) | **0.00%** (0) |
| `Ornith-1.0-35B-mlx-uniform-4bit` ifeval | **41.82%** (30) | **0.32%** (1) |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` humanevalplus | **41.08%** (1) | **0.00%** (0) |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` mbppplus | **70.44%** (2) | **0.00%** (0) |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` ifeval | **56.79%** (10) | **0.00%** (0) |

**TWO CORRECTIONS TO MY OWN ENTRY BELOW, both found by measuring instead of inferring:**
1. I reported the broad figure for `Ornith-1.0-35B-mlx-uniform-4bit` humanevalplus as 34.9% and called
   the published 40% "a loose rounding". **It is 39.66%, so the published figure was EXACT.** I had
   filtered on `nonconv_kind == degenerate_repetition` (2 rows) — a THIRD definition that misses the
   self-terminating loops, which score as CONVERGED and so carry no `nonconv_kind` at all. 2 + 2 = the 4
   rows the scoreboard counts.
2. I wrote that the scoreboard is generated from the score files and would therefore print values "~10x
   smaller" than the prose. **Backwards.** The scoreboard DERIVES the broad share from the rows, so it
   reproduces the published figures exactly; what is unrecoverable from the table is the PERSISTED narrow
   number. And the narrow one is itself budget-dependent — without the manifest backfill of the resolved
   thinking budget, `Ornith-1.0-35B-mlx-uniform-4bit` ifeval reports 26 self-terminating degenerate rows
   instead of 1.

**Implemented rather than ruled on**, because naming two measured quantities distinctly is not a
judgement call: `benchmark/m1/scoreboard.py` now emits `degenAll` / `degenAllWall%` (derived) beside
`degenEosedWall%` (persisted), with a legend stating that the two are NOT interchangeable.
⚠️ **Residual, and it is real:** `benchmark/run.py`'s own summary still prints the NARROW quantity under
the bare name `degen`, so the same ambiguity survives there.

### O26 (original text, retained — see the corrections above before using any number in it). "degenerate wall-share" NAMES TWO DIFFERENT QUANTITIES that differ by up to ~10x
Raised 2026-08-16 from the score files, not from the doc.

`grade.py:122` persists `degenerate_wall_share` from `traces.summarize`, computed over the **EOS'd
degenerate rows only**. The published scoreboard row in `docs/campaign-results.md` uses a **broader**
definition — every row with `nonconv_kind == degenerate_repetition`. Both are defensible; the
collision is the hazard. Measured on the same rows:

| model | bench | narrow (persisted) | broad (published) |
|---|---|---|---|
| `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` | humanevalplus | 0.0% | 24.6% |
| `Ornith-1.0-35B-mlx-uniform-4bit` | humanevalplus | 4.8% | 34.9% |
| `Ornith-1.0-35B-mlx-uniform-4bit` | mbppplus | **0.0%** | **63.1%** |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` | humanevalplus | 0.0% | 41.1% |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` | mbppplus | 0.0% | 70.4% |

The published figures are right under the broad definition (the doc's "40%" for
`Ornith-1.0-35B-mlx-uniform-4bit` humanevalplus is 34.9%, a loose rounding). **The problem is that
the scoreboard is generated from the score files, which carry only the NARROW number** — so
regenerating that row yields values ~10x smaller than the prose, with no warning.
**Needs a ruling: rename one of them** (e.g. `degenerate_eosed_wall_share` for the narrow one), or
persist both. `benchmark/m1/suffix_ofat.py` already reports both, labelled, as an interim measure.

### ~~O25~~ → RULED + MEASURED (2026-08-17): condition set by the operator; the n=100 OFAT does NOT pass it — suffix stays OFF.
**The ruling (operator, 2026-08-17):** re-enable for SERVING ONLY if the paired ON/OFF accuracy
delta CI fits inside ±5pp on BOTH winners and BOTH benches; a measured `p_d` of 0 reads
**UNDEMONSTRABLE, not passed**. Measurement stays suffix-OFF permanently.

**The measurement (2026-08-17, all four OFF arms n=100 graded via docker evalplus, paired against
the git-HEAD ON verdicts on the intersection of real completions; `p_d` FIRST per the standing
rule):**

| cell | p_d | n_disc | Δ acc (ON−OFF) | 95% CI | verdict | n for 5pp @ measured p_d |
|---|---|---|---|---|---|---|
| `Ornith-1.0-35B-mlx-uniform-4bit` / humanevalplus | 0.05 | 5 | −1.0pp | [−5, +3] | inconclusive | 157 |
| `Ornith-1.0-35B-mlx-uniform-4bit` / mbppplus | 0.04 | 4 | 0.0pp | [−4, +4] | **equivalent** | 126 |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` / humanevalplus | 0.06 | 6 | +2.0pp | [−3, +7] | inconclusive | 189 |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` / mbppplus (n=99: `Mbpp/430` timed out in the OFF arm, regen queued) | 0.061 | 6 | +2.0pp | [−3, +7] | inconclusive | 191 |

**Outcome: 3 of 4 CIs poke past ±5pp → the ruled condition is NOT met at n=100. Suffix stays OFF
for serving.** `p_d` is 0.04–0.06 (not 0), so the gate is *demonstrable* — a powered test needs
~126–191 items per cell (humanevalplus has 164 total, mbppplus 378, so full-bench arms would do
it). **Extension DECLINED (architect decision, operator-delegated, 2026-08-17):** ~6–8 h of worker
time to certify a serving-only 1.27× lever fails quality-over-speed, and fresh suffix-ON arms
would re-churn the serving path. Suffix stays OFF; revisit only on an operator latency complaint. Note also the direction: the point deltas are
tiny and two lean ON-better — there is no evidence of ON harming accuracy, only insufficient
precision to certify ±5pp. Analyser artifacts: `$STACK_WORKDIR/status/suffix_ofat_*.json`,
`$STACK_WORKDIR/scratch/paired_accuracy.py`.

### O25 (original text, retained — the ruling above supersedes the "needs a ruling" line).
Raised 2026-08-16. **The withdrawal itself is CLOSED** (operator, 2026-08-16): suffix is OFF for all
five models, verified at the worker command line, and `compare` now refuses across draft state
(fingerprint v3). What is open is the return condition.

Suffix was ON for exactly `Ornith-1.0-35B-mlx-uniform-4bit` and
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` and OFF for every other candidate, on a "quality-neutral"
claim that the campaign's own ≤5% gate never supported — those arms resolve ±12.5pp (n=100) and
±32pp (n=15). Measured cost of removal on `Ornith-1.0-35B-mlx-uniform-4bit`: decode ~100 → 77 tok/s,
wall 23.8 → 30.3 s on a matched prompt. That is a real daily-driver loss, so the return condition
matters.

**Proposed condition:** re-enable for SERVING ONLY (never for measurement, where per-model uniformity
outranks 1.27×) if the paired ON/OFF OFAT puts the accuracy delta inside ±5pp. **Why that is now
affordable:** the "628 items" figure that made the gate look unreachable comes from `stats.mde`'s
DEFAULT `p_d = 0.20`, a between-MODELS guess. Within-model paired, at p_d = 0.05 the gate needs 157
items and at 0.02 it needs 63. The OFAT measures p_d first and sizes itself on the measurement.
**Needs a ruling on the return condition**, not on the withdrawal.

### ~~O24~~ → CLOSED-BY-IMPLEMENTATION (2026-08-16): the hook is built, installed on the driver, and
has blocked real commits. `githooks/pre-commit` runs `bench.modelnames` over ADDED lines plus
`bench.piicheck`; `githooks/commit-msg` checks the message; enable per clone with
`git config core.hooksPath githooks`. **Residual work, not a ruling:** install it on the worker, and
two known gaps — it cannot see chat prose (where the rule actually failed), and its FAMILY-reference
allowance does not fire when the model prefix sits inside backticks. One live defect was found BY
being blocked: the checker treated the mandatory `Co-Authored-By:` trailer as prose, because that
name collides with a registry segment, so it blocked EVERY commit until attribution trailers were
exempted. The one-time fix of the normative docs proposed below was done for AGENTS.md on the same
day. Original text retained:

### O24 (original text, retained). Should the model-naming rule be enforced on CHANGED LINES by a pre-commit hook?
Raised 2026-08-16, after the operator had to give the same correction twice in one session.

The rule ("full registry name, in reports, results, docs AND commits") is now explicit in AGENTS.md
with the banned shorthands enumerated. **What is missing is enforcement.** Measured that day:
`test_docs_full_model_names.py` covers only `docs/*.md` and only ONE two-word shorthand for
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (the one its own assertion names) — not AGENTS.md, not commit
messages, not `Nemotron` / `Ornith` / `gemma` / `the MoE` / `the OptiQ`. Bare
shorthand appeared in **4 of 5 commit messages** and throughout the agent's replies.

A repo-wide assertion is not viable: bare-shorthand counts are AGENTS.md 23, `lab-notebook` 156,
`campaign-queue` 86, `open-questions` 30, `campaign-results` 11 — ~300 sites, so it would fail
instantly and be disabled.

**Proposal:** a pre-commit hook checking (a) added/changed lines in the staged diff and (b) the
commit message, against all six shorthands; plus a one-time fix of the two NORMATIVE docs only
(AGENTS.md, `campaign-results.md`, ~34 sites), leaving the narrative history alone.
**Needs a ruling** — it is the only part that makes the rule mechanical rather than agent-carried.

### ~~O23~~ → CLOSED (operator, 2026-08-16): **do NOT buy the ~35 h.** The mechanism is already significant; only a confirmatory accuracy number was missing.
Decided on the arithmetic below plus one measurement made while scoping it: the DNF-rate difference
that DRIVES the 21pp `acc_strict` split is **already statistically established at n=30** —
`Ornith-1.0-35B-mlx-uniform-4bit` **9/30** budget-hits vs `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`
**0/27**, Fisher exact two-sided **p = 0.00211**. A count endpoint carries far more information per
item than a binary pass, which is why n=30 resolves it while `acc_strict` needs ~100.

So the 35 h would have bought a confirmatory accuracy figure for a mechanism already significant, and
whose accuracy COST is already measured at n=100 on two other benches (Ornith-1.0-35B-mlx-uniform-4bit
forfeits 2.0pp and 3.0pp to truncation on humanevalplus and mbppplus). **Report the DNF-rate result as
the finding; leave the reasoning axis at its July-config numbers, labelled with that config.**
Also corrected while scoping: the 21.5pp figure is computed across DIFFERENT item sets (30 vs 27) and
**2 of the 3 excluded items are ones Ornith-1.0-35B-mlx-uniform-4bit also DNF'd**, so on the matched
27 the gap is ≈**14.8pp**, not 21.5pp.

### O23 (original text, retained). `math500` at the current config costs ~35 h and CANNOT reuse the existing 30 rows
Raised 2026-08-16 from the manifests, not from the doc.

Both winners' math500 rows are `sampling_profile: **official**`, `max_kv_cache_size: **262144**`,
`fingerprint_version: None`, generated ~2026-07-05 from local model paths — and
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`'s rows come from a **different quantization** of the weights
(effective_bits 4.9701 vs today's 4.9835). They are internally consistent with EACH OTHER, so the
21pp `acc_strict` split is a valid comparison **at a config we no longer serve**; they are not
extendable at `deployed`.

Consequences: the cheap fix (retry the 3 timed-out rows) is **unavailable** — the provenance guard
correctly blocked it as mixing. A current-config n=100 is ~100 × (499 s + 756 s) ≈ **35 h**, from
scratch. Mechanism worth noting: Ornith-1.0-35B-mlx-uniform-4bit has 0 errors but **9/30
budget-hits**, while Qwen3.6-27B-Opus-Distill-OptiQ-4bit has 0 budget-hits but 3 timeouts — and two
of those timed-out items are ones Ornith also DNF'd, so the 21pp gap is computed on sets that
exclude two Ornith failures and the true matched gap is likely SMALLER.
**Needs a ruling: spend ~35 h, or leave the reasoning axis at its July-config result?**

### ~~O22~~ → CLOSED (agent proposal WITHDRAWN by its author, 2026-08-16): a "config epoch freeze"
Proposed after math500 turned out unextendable: declare the current fingerprint frozen and finish
every axis inside it. **Withdrawn the same day, before any ruling, because the evidence did not
support it.** The operator's challenge was the right one — does this help the goal, or is it
ceremony against the *appearance* of tail-chasing?

Tally: the campaign IS progressing (ifeval n=200 completed + graded; two head-to-head verdicts
recovered that were previously impossible; coding cells graded 21 → 3; the aider item-set defect
fixed — `--num-tests` is an unseeded sample, so **every aider arm before 2026-08-16 was unpairable
by construction**). The thrash was the AGENT's execution hygiene: three bugs in one runner, two
reports made from run prefixes. And math500's invalidation is July config debt already paid, not an
ongoing pattern. **A freeze would not have prevented any of it.** The rule that would — "size every
job from a pilot, precondition-check before launching" — already existed in the retired campaign-queue.md; it is now in AGENTS.md as the 5-item pilot rule.
Recorded as CLOSED rather than deleted so it is not re-proposed as if new.

### ~~O21~~ → CLOSED (operator, 2026-08-16): **no interim prompt-mode BFCL number.** Build the vendored handler.
An interim run with a borrowed handler, labelled "prompt-mode, borrowed template", was offered and
declined. Rationale accepted: it is inadmissible under the campaign's own tool-calling rule, and a
labelled-inadmissible number in the corpus is exactly the thing that later gets quoted without its
label. The vendored handler (raw `messages` + `tools` to `/v1/chat/completions`, registered under our
served names) is DRIVER work and does not compete for worker time.
⚠️ Note before starting it: `bfcl_eval` is installed on the **worker only** (2026.3.23), not the
driver, despite AGENTS.md claiming both boxes.

### ~~O20~~ → CLOSED (operator, 2026-08-16): gemma coding job DROPPED, gemma ifeval DEFERRED behind math500.
The O18(b) ruling. `gemma-4-26B-A4B-it-OptiQ-4bit evalplus n=100` is dropped — the coding axis's open
question is a 2–5pp gap between the winners, which an unpairable ±20pp row cannot inform.
`ifeval n=200 gemma-4-31B-it-qat-6bit` is KEPT as ABSOLUTE-ONLY but deferred behind math500: ~10 h of
a single worker for an absolute row on the one axis where the two winners already returned a clean
`equivalent`.

### ~~O19~~ → CLOSED-BY-ARITHMETIC (2026-08-14): the Nemotron 4→6-bit ceiling probe cannot answer its own question
**Pre-registered design** (operator, 2026-08-14): 4-bit as baseline → uniform 6-bit as CEILING → and only
if the 4→6 gain is significant, evaluate OptiQ ("~6-bit quality at ~5-bit perf") as the cheaper way to
capture it. Decision rule fixed in advance: **a paired 4→6 delta under ~10pp = "no gain worth buying"**,
since 6-bit costs ~8 GB and ~30% of decode speed.

**The baseline landed before the ceiling was run, and it closes the question:**
`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` scores `acc` 89.0% (humanevalplus) / 81.0% (mbppplus)
against the best measured model's 93.0% / 84.0%. **So the ENTIRE headroom to the leader is ~4pp.** A 4→6
delta clearing the 10pp bar would put it at ~99% / ~91%, far above every model in the corpus. **The rule
we agreed therefore guarantees the verdict before the run: "no gain worth buying."**

And resolving the effect that DOES matter (~4pp) needs **n≈628** matched items per the MDE table — for
three models — which is unaffordable on one worker. At n=100 the probe can only return a fifth
INCONCLUSIVE row.

⚠️ **The honest counter-argument, recorded rather than buried:** 4pp is not negligible *here*, because
closing it would make Nemotron competitive with the winner while being ~2× faster per item and using
26.0 GB at 256K vs `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`'s 37.6 GB (corrected 2026-08-17; the 43.3 cited here originally was refuted). But that is exactly the effect size
n=100 cannot see, so the
probe cannot settle it in either direction. **The instrument's resolution (±12.5pp at n=100) is larger
than the entire remaining headroom (~4pp).**

**Decision: skip the 6-bit arm; spend the worker on the AGENTIC axis instead** — the only axis where this
campaign has ever resolved an effect (aider polyglot, +23.6pp, p=1.3e-05), and the one this model is
explicitly built for. A 20pp-scale effect is decidable at feasible n; a 4pp one is not.
**Generalisable rule: before running a probe, check that the effect it could plausibly find is larger
than the instrument's MDE. If it is not, the probe is theatre.**

### ~~O17~~ → PARTLY CLOSED (operator, 2026-08-14): **drop the n=40 evalplus job — DONE.** But my scoping was WRONG and the residue is bigger; see O18.
The approved job is removed from `docs/work-queue.json`. ⚠️ **I described it as "the last queued job".
It was not.** The runtime state file only lists jobs the runner has already touched (5 of them), while
the PLAN had 10 — so three gemma jobs and two very large winner jobs were invisible to the check I ran.
Reading runtime state and calling it the backlog is the same class of error as reading a run prefix and
calling it the run. **Lesson: the plan is the backlog; the state file is only what has been attempted.**

### ~~O18 (a)~~ → CLOSED (operator, 2026-08-14): **`gemma-4-26B-A4B-it-OptiQ-4bit evalplus n=100` STOPPED.** Measured 201 s/item ⇒ ~11.2 h for an unpairable row, while blocking free grading. 11 rows kept; resumes via `done_ids`. Requeue at n=40 (~2.2 h) only if second-architecture-class coverage is wanted.
⚠️ **My "it might be cheap, it's a fast MoE" caveat was WRONG, and measuring cost 17 minutes.** The plan
entry carried no ETA, unlike its neighbours; the queue's own rule is SIZE EVERY JOB FROM A 5-ITEM PILOT,
and this job had never been sized. 5 items in 16m47s ⇒ 201 s/item ⇒ ~11.2 h. **The runner was stopped
too, not just the job** — otherwise it would have advanced straight into `ifeval n=200 gemma` (~10 h) and
blocked grading all over again. `O18 (b)` below (the remaining queue) is still OPEN.

### ~~O18 (b)~~ → CLOSED (operator, 2026-08-16); see O20 above for the ruling. Original text retained below.
### O18 (b). gemma CANNOT be compared to the winners at a matched budget — it is ARITHMETICALLY impossible
Raised 2026-08-14 while executing O17, from the registry rather than from old rows:

| model | `thinking_budget` | `max_tokens` | `max_kv_cache_size` |
|---|---|---|---|
| `Ornith-1.0-35B-mlx-uniform-4bit` | 81920 | 102400 | 131072 |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` | 81920 | 102400 | 131072 |
| `gemma-4-31B-it-qat-6bit` | **16384** | 32768 | **49152** |
| `gemma-4-26B-A4B-it-OptiQ-4bit` | **32768** | 49152 | **65536** |

`compare` refuses any comparison differing in `thinking_budget` or `max_tokens`.

⚠️⚠️ **CORRECTION 2026-08-14 — MY "ARITHMETICALLY IMPOSSIBLE" CLAIM WAS WRONG, AND THE TABLE ABOVE READS
A DIRTY FILE.** I wrote that `gemma-4-31B-it-qat-6bit`'s ceiling is `0.8 × 49152 ≈ 39,300`, less than half
the winners' budget, so matching was impossible without changing what we ship. **49152 is M5's LOCAL DIRT,
not the shipped value.** The committed registry has **196608**, whose ceiling is
`0.8 × 196608 ≈ 157,286` — comfortably ABOVE 81,920.

**Measured while merging the Nemotron entry** (`git diff -- main_models.yaml` on the worker): **all four**
model entries are locally modified, not two —

| model | committed | M5 local dirt |
|---|---|---|
| `gemma-4-31B-it-qat-6bit` | 196608 | **49152** |
| `gemma-4-26B-A4B-it-OptiQ-4bit` | 262144 | **65536** |
| `Ornith-1.0-35B-mlx-uniform-4bit` | 262144 | 131072 |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` | 262144 | 131072 |

**So the queue doc's claim that "gemma's 196608 and the other 262144 entry are untouched" is FALSE**, and
I built an arithmetic argument on top of it without checking the file. Same error class as the Qwen3.8 KV
estimate: I trusted a recorded description of the config instead of reading the config.

**What is actually true:** gemma is unpairable because its **declared `thinking_budget` is 16384** (a
CONFIG CHOICE in `generation_defaults`), not because of a KV wall. At the committed cap there is headroom
to declare 81920. So the real options are:
(a) leave gemma at its shipped 16384 and accept ABSOLUTE-ONLY rows — measures what we ship, never pairs;
(b) declare 81920 for benchmark runs — pairs with the winners, but then we are no longer measuring gemma's
    deployed config, and its `conv%` is already 83% at the smaller budget so it may simply loop longer.
**Recommendation: (a), and stop describing it as impossible.** But it is now a genuine choice, not a wall.

**Still queued against that constraint: ~34 h** — `gemma-4-26B-A4B-it-OptiQ-4bit` evalplus n=100,
`ifeval n=200 gemma-4-31B-it-qat-6bit` (~10 h). Plus two large winner jobs whose own names flag them:
`math500 n=100 both winners` (~35 h) and `livecodebench n=100 ×4` (~55 h, "LIKELY TOO EXPENSIVE AS
SPECIFIED").

**The counter-argument, which I think is right and which cuts against a blanket drop:** goal A is to
MEASURE models on dimensions, and a gemma row at gemma's own deployed config measures gemma **as it would
actually be used**. That is legitimate, useful data — it just yields an ABSOLUTE capability number and a
usability verdict, never a paired delta. The refusal is a property of paired statistics, not of the
measurement.

**Options:** (a) **keep the gemma jobs, labelled ABSOLUTE-ONLY** — report them in the scoresheet, never
pair them, and size n from a 5-item pilot; (b) **drop gemma from the coding axis** and spend the ~34 h on
the axes that can resolve something (BFCL, judge-panel reliability, an opencode row for the B pick);
(c) re-run the winners at gemma's budget — rejected, it would misrepresent the winners and cost more.
**Recommendation: (a) for `ifeval n=200`, (b) for `gemma-4-26B-A4B-it-OptiQ-4bit evalplus n=100`.** The
daily-driver dimension has only two models and an absolute third is genuinely informative; the coding
dimension already has an unresolved 2–5pp question between the winners that a ±20pp uncomparable row
cannot help with. **Needs your ruling; nothing is dropped beyond the one job you already approved.**

### ~~O17 (original text, retained)~~ `gemma-4-31B-it-qat-6bit` evalplus is queued at n=40 — but it is UNRANKABLE by construction
The last queued job is `gemma-4-31B-it-qat-6bit evalplus n=40`, deferred earlier today with the note
"10.4h projected for a ±20pp row, 83% of wall in runaways, 1 item lost to a 3600s timeout".

**Two problems, and the second is the decisive one:**
1. **±20pp at n=40** cannot resolve anything the campaign cares about. The winners differ by ~2–5pp on
   coding; resolving that needs 628 matched items.
2. **It runs at `thinking_budget` 16384 while both winners sit at 81920**, and `compare` MECHANICALLY
   REFUSES cross-budget comparisons. So 10.4 h of the single worker buys a row that cannot legally be
   compared to anything already measured. It would sit in the scoresheet as an unrankable cell.

**Options:** (a) **drop it** — 10.4 h back for work that can resolve something; (b) **re-run it at a
matched 81920 budget**, making it comparable but costing more than 10.4 h and re-opening whether gemma
converges at that budget (its `conv%` is already 83% on humanevalplus at 16384); (c) run as-is and
accept an uncomparable row.
**Recommendation: (a) drop it now, and if gemma matters, requeue at a matched budget with an n chosen
from a 5-item pilot.** A row that `compare` refuses is not evidence at any n.

### ~~O16~~ → CLOSED (operator, 2026-08-14): **LEAVE IT.** Deterministic, documented, 0.2% of items. Revisit only if a future axis leans on the affected instruction types.
### O16 (original text, retained). IFEval verifiers INVENT the criterion when a kwarg is absent — leave it, or stop grading those items?
Found and partly fixed 2026-08-14 (`b04030c`). 24 sites in the vendored `instructions.py` fabricate an
**absent kwarg** with `random.choice` / `random.randint` (e.g. `:1350`
`self._frequency = random.randint(1, _LETTER_FREQUENCY)`). Seeding made this **reproducible**; it did not
make it **valid** — for those items the grader checks the response against a threshold it made up.

**Measured scope: 1 verdict of 541 (0.2%), `acc` spread 0.18pp across 8 RNG states.** So this is currently
a hygiene question, not a live number — which is exactly when it is cheap to decide.

**Options:** (a) **leave it** — deterministic, documented, 0.2%; (b) **count those items as verifier
skips** so they leave the numerator AND are counted (the harness already counts skips visibly, so n
would not shrink invisibly) — costs a little n and is the most honest reading; (c) supply the upstream
IFEval defaults explicitly instead of drawing them, if upstream defines any.
**Recommendation: (a) leave it, with the note standing in the lab notebook.** At 0.2% the cure costs more
clarity than the disease, and (b) would make our `acc` non-comparable with published IFEval numbers.
**Revisit if a future axis leans on the affected instruction types** (`keywords:letter_frequency`,
`length_constraints:number_sentences`, and the other threshold-bearing ones).

### ~~O14~~ → CLOSED-BY-MEASUREMENT. The throughput concern DID NOT REPRODUCE; the rule stands
I reported a **>47× slowdown** at `262144/262144` (a matched item not completing in 19.5 min vs 24.8 s
at `131072/131072`) and wrote it into `AGENTS.md` as a challenge to the prealloc rule. **A 3-arm OFAT
falsifies it.** Same item (`HumanEval/146`), same model/sampling, router restarted per arm:

| cap / prealloc | wall | decode | peak mem | pressure warns |
|---|---|---|---|---|
| 131072 / 131072 | 24.7 s | 98.5 tok/s | 25.35 GB | 0 |
| 262144 / 131072 | 25.0 s | 103.1 tok/s | 25.50 GB | 0 |
| **262144 / 262144** (shipped) | **27.8 s** | **104.5 tok/s** | 28.18 GB | 1 |

**All three are fast.** The shipped config is not slow, peak memory is far under the 46GB gate, and
the operator's rationale — prealloc is what makes 256K reachable at all, because growing 128K→256K
requires holding 384K of KV during the double-buffer — stands unchallenged.

**The original 19.5-minute non-completion is UNATTRIBUTED and treated as a transient.** Most likely
environmental: that run began with ~21GB already in use by other processes and swap already active
(router logged `System memory: 68.7GB total, 47.8GB available`, then
`memory.pressure.warn ram_percent=76.9`), against a cleaner box now.

**Process lesson, worth more than the result:** one dramatic observation, on ONE item, with TWO
variables moved at once, is a hypothesis. I wrote it up as a finding, put a warning into `AGENTS.md`
against a rule that prevents a known OOM, and reduced the registry on that basis. The OFAT cost 4
minutes and should have come first. (The registry change to 131072 is retained for an unrelated and
VALID reason — it is the tightest cap that keeps the declared 81,920 thinking budget in force with no
clamp — but the evalplus H2H therefore ran at a right-sized benchmark cap, not the shipped one, and
peak memory shows there was never a memory reason to reduce it.)

### ~~O13~~ → CLOSED (operator, 2026-08-14). My framing was WRONG; the config is self-consistent
I claimed `max_tokens: 102400` "exceeds the usable context" because at a 250K prompt the resolved
thinking budget collapses to 9,708. **Operator correction: 256K of context is a TOTAL budget — prompt
+ thinking + output — so a 250K prompt was never a supported configuration.**

Working it through with the shipped numbers: `thinking_budget` 81920 is exactly `0.8 × 102400`, and the
clamp yields the full budget while `0.8 × (262144 − prompt) ≥ 81920`, i.e. **prompt ≤ 159,744**. So
~160K is the DESIGNED maximum prompt, `max_tokens` and the 0.8 ratio agree, and **the clamp firing above
~160K is correct, intended behaviour rather than a defect.** Lowering `max_tokens` or `thinking_budget`
(my options 1 and 2) would have solved a non-problem at the cost of capability.

**What remains genuinely wrong is narrower — documentation and guard-rails, not the values:**
1. **The per-model max prompt is written down nowhere.** 159,744 for
   `Ornith-1.0-35B-mlx-uniform-4bit` is derivable but undocumented, and it is LOWER for
   `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, which wants a bigger thinking budget. Nobody can respect a
   limit they cannot look up. **→ record the derived max prompt per model in the registry.**
2. **The clamp is silent** while its sibling `max_tokens` clamp logs a warning. That silence is what let
   33 IFEval rows score as converged. **→ one-line fork fix to log it.**
3. **Benchmarks have no preflight against it.** A long-context axis feeding a 200K prompt would silently
   measure a shrunken thinking budget. **→ assert `prompt ≤ documented_max_prompt(model)`.** Unlike the
   `max_tokens ≤ cap` invariant I withheld, this one does NOT fail against the shipped config, so it can
   land honestly.

### ~~O12~~ → CLOSED (operator, 2026-08-14): **RE-RULED AS BUDGET HITS — these are NOT converged responses.**
M1 (2026-08-13) ruled the degenerate-loop rows "NOT a DNF... a valid converged response — converged as
determined by the MODEL", turning on item 2849 sitting at **"64% of budget"** (52,503 / 81,920) with
`finish_reason "stop"`.
**Against the budget actually in force that row is at 100.2%** — `int((65536 - 42) * 0.8) = 52,395`. It
is a budget hit. The model did not determine it was done; `ThinkingBudgetCriteria` force-injected
`</think>` and the model then wrote its answer, which is exactly why `finish_reason` read `"stop"`.
Reclassified: of 40 flagged loops, **25 + 8 are clamped budget hits, 4 + 2 are `max_tokens`
truncations, and 1 is genuinely self-terminating** (Ornith id 3748, 8,228 tokens).
**What is unchanged:** the answers still verify, so `acc` is unaffected (90.0% / 89.9%), and the IFEval
"the two winners are EQUIVALENT" headline survives — both arms moved the same way.
**What changes:** these rows are non-converged, so AGENTS.md's standing rule applies in full — a
persistent budget hit is a FAIL SIGNAL and the knob is temperature. `acc_strict` drops 89.8% → 86.7%
(Ornith) and 88.5% → 85.1% (distill).
**Recommendation: re-rule them as budget hits** (which the harness now does automatically, `aca967b`),
and keep the M1 *principle* — a genuinely self-terminating loop is not a DNF — since it was correct and
now applies to exactly one row. **This also un-blocks O9 in a smaller form:** the judge-panel question
about looped-but-correct answers now has an n of 1, so it is not worth panel time.

### ~~O11~~ → CLOSED-BY-MEASUREMENT. Premise falsified: the loops do not self-terminate
O11 asked whether to chase the degenerate-loop tax (42% / 57% of IFEval wall-clock) ahead of P4, on the
basis that these were "verbatim repetition loops that SELF-TERMINATE under budget and answer
CORRECTLY", i.e. a pure cost problem fixable by sampling.

**Measured 2026-08-14: 39 of the 40 rows are EXTERNAL TRUNCATIONS, not self-terminations.** The server
silently clamped the declared 81,920 thinking budget to ~52,390, and the harness compared against the
declared value — so a forced `</think>` scored as a clean stop. Genuinely self-terminating share of
wall-clock: **0.3% (Ornith) and 0.0% (distill)**, versus the 42% / 57% the item was raised on.

| | Ornith | distill |
|---|---|---|
| clamped budget-hits | 25 | 8 |
| `max_tokens` truncations | 4 | 2 |
| **genuinely self-terminating** | **1** | **0** |

**The cost is still real** (2.5h and 3.6h of wall-clock) — the *attribution* changed, and with it the
intervention. This is no longer "find the sampling setting that stops a self-verification loop"; it is
AGENTS.md's standing case: a model persistently hitting a generous budget → run the TEMPERATURE LADDER
on the offending items. That is a different experiment with a different success criterion, so O11 as
specified is answered rather than deferred. The design constraints attached to it (vary sampling on the
SAME loop-triggering ids; never the untruncated config; no `min_p` cells below temp 0.4) all still hold
for whatever replaces it. Successor questions: **O12** (the ruling), **O13** (the config), **O14** (the
prealloc rule).
⚠️ **Two blockers remain for any successor probe, both unbuilt:** `generate` has **no id filter**, so
"vary sampling on the SAME items" is not executable; and there is no `presence_penalty` /
`repetition_penalty` override (only `--max-tokens`, `--temp`, `--thinking-budget`). Both small, both
free. Also unverified: AGENTS.md claims a nonzero `presence_penalty` disables suffix decoding — I found
no such gate in the fork, only the structured-output one at `generation.py:1750`. Measure before
designing a penalty cell.

### ~~O11 (original text, retained)~~ Investigate the degenerate-loop tax BEFORE P4? (largest unclaimed speed win on the board)
Measured on IFEval 2026-08-13, and it is not a small effect:

| | `Ornith-1.0-35B-mlx-uniform-4bit` | `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` |
|---|---|---|
| loops | 30/541 (5.5% of items) | 10/148 (6.8%) |
| **share of wall-clock** | **42%** (2.5h of 6.0h) | **57%** (3.6h of 6.3h) |
| healthy → loop, mean wall | 25s → 303s (**12×**) | 71s → 1,283s (**18×**) |
| healthy → loop, mean tokens | 2,655 → 52,911 | 2,028 → 55,274 |
| **recoverable if fixed** | **2.3h of 6.0h (~38%)** | **3.4h of 6.3h (~54%)** |

`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` is worse not because it loops more often (6.8% vs 5.5%) but
because it decodes at **28 tok/s against Ornith's 106**, so the same ~53K-token loop costs ~21 min
instead of ~5.

**For scale:** every Phase-2 speed lever combined was ~1.27× (suffix) plus ~2–7% (GQA kernel). This is
potentially **1.6–2.2× on real workloads** — larger than everything Phase 2 shipped, and the Tier-0
machinery to test it already exists.

**Mechanistic hint, which the test must respect:** loops concentrate on *counting* instructions
(`change_case:capital_word_frequency` **33%** vs a 4.5% base rate) — the model enumerates candidates to
verify its own output. That is the same pathology AGENTS.md records for the synthetic `aggregation`
word-tally task, now seen on a published benchmark. So it may be **prompt-triggered rather than purely a
sampling artifact**, and a temperature sweep alone cannot distinguish those. Design the probe to vary
sampling on the SAME loop-triggering items (the 30 + 10 ids are recorded in `degenerate_eosed_ids`).

⚠️ **Do not conflate with quality.** These answers are CORRECT — item 2849 passed both verifiers after
52,503 tokens of a two-line cycle. This is a COST question; the ruling that they are not DNFs stands (M1).

**Recommendation: yes, ahead of P4.** It is cheap, reuses existing tooling, targets the campaign's
stated speed goal, and P4's own cost estimate (~28h) is inflated by exactly this tax — so fixing it first
makes P4 cheaper too.


### ~~O10~~ → CLOSED (operator, 2026-08-14): **option 3.** `acc` keeps its historical meaning so published rows stay comparable; `acc_strict` carries the don't-grade-a-truncation semantics.
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
(0.94 vs 0.749). ⚠️ **CORRECTED 2026-08-15: that pair is NOT both at n=1000** — `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` scored **0.94 at n=200** and `Ornith-1.0-35B-mlx-uniform-4bit` **0.749 at n=1000**, so the "~12σ" figure conflates two different sample sizes and should not be quoted as-is. The GAP is large enough to be the most resolvable effect the suite owns, which is the real argument; the sigma value is not sound. (The distill's 0.94 is filed under the `Qwen3.6-27B-OptiQ-4bit` HANDLER KEY because bfcl only accepts model names from its own MODEL_CONFIG_MAPPING — the served weights were the distill's. Its own bfcl.json reads acc=null purely from the clobber bug now fixed.) Then judge panel v3. SWE-bench last; it is the largest build.

### ~~O9~~ → CLOSED (operator, 2026-08-14): **DROPPED.** After the O12 reclassification exactly ONE row is genuinely looped-then-correct, so there is nothing to compare and no panel time is warranted.
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

**The verdicts are here; the measured detail lives in `docs/lab-notebook.md`** (the APC work, M2/M3,
is written out at length there — byte-identical peak memory across arms, zero cache hits, and the
session-cache shadowing that explains it). Kept as verdicts rather than re-transcribed, because
"we decided" and "we measured" age differently and the measurement is the part that needs its
full context.

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
