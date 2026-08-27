# Campaign results — RECOMMENDATIONS + the SCORESHEET

**Structure of this doc, and why.** The top section is **my recommendations** — judgement, hand-written,
for the two picks the campaign exists to make. Below it is **the scoresheet** — pure measurement,
**generated from the persisted rows by a command**, never hand-maintained. The narrative record (every
retraction, defect, mechanism and process lesson) moved to **`docs/lab-notebook.md`** on 2026-08-14;
nothing was deleted.

The split exists because the two layers have different failure modes and must be auditable separately:
a recommendation can be wrong because I reasoned badly, a scoresheet cell can be wrong because the
measurement was bad. When they live in one hand-written narrative, every corrected number becomes a new
`RETRACTED` / `SUPERSEDES` section and ordinary measurement corrections read as churn.

**The harness (goal A) measures. It does not pick.** The picks below are mine, derived from the table,
and they are point-in-time: when a new model is run through the same suite, the table changes and these
paragraphs get rewritten.

---

# ⭐ RECOMMENDATIONS

## B — coding across a repo-sized context

> ### Pick: `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`
> **Runner-up:** `Ornith-1.0-35B-mlx-uniform-4bit` — and pick the runner-up instead if turn latency
> matters to you more than task success rate.

**What it rests on.** The one powered capability result in the entire corpus: aider polyglot at
**n=110 matched**, `final` **73.6% vs 50.0%**, McNemar **p=1.3e-05**. The mechanism is identified and it
is not raw generation ability — it is **repair**: 60.8% vs 33.7% success on the second, test-informed
attempt. That is exactly the ability an agentic coding loop consumes.

**Single-shot coding now agrees in DIRECTION but cannot resolve the gap** — n=100 matched, `deployed`,
same box/session, on the current `mlx-vlm` sha:

| n=100 | humanevalplus | mbppplus |
|---|---|---|
| `Ornith-1.0-35B-mlx-uniform-4bit` `acc` / `acc_strict` | 92.0% / **90.0%** | 83.0% / **80.0%** |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` `acc` / `acc_strict` | **93.0%** / **93.0%** | **84.0%** / **84.0%** |
| `compare` paired verdict on `acc` | −1.0pp, CI [−5.0,+3.0] **INCONCLUSIVE** | −1.0pp, CI [−6.0,+4.0] **INCONCLUSIVE** |

**Raw `acc` is unresolved on both** (628 matched items would be needed) — so this is NOT independent
confirmation of the agentic result. **What it does show, replicated on two benches, is the mechanism:**
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`'s `acc` and `acc_strict` are IDENTICAL — it forfeits nothing to
truncation — while `Ornith-1.0-35B-mlx-uniform-4bit` loses **2.0pp** and **3.0pp** to turns that never
self-terminate. At a matched budget that is capability the runner-up gives away, and it is the same
pattern the earlier single-bench run showed.

**Confidence: HIGH on capability. Two caveats that are not small:**
1. **It is aider-scaffold-specific.** There is **zero** evidence from opencode, which is the primary
   agentic driver we actually ship. A scaffold change can plausibly move a repair-driven result.
2. **`Ornith-1.0-35B-mlx-uniform-4bit` wins every latency statistic** — median 18 s vs 21 s, p95 106 s
   vs 126 s, decode **107.6 vs 28.6 tok/s** (3.8×). It emits 3.1× more tokens per item and still
   finishes first. For an interactive edit loop that is a real, measured argument for the runner-up.

**On the "256K" part of B — NOT MEASURED as a task, and the shipped config cannot do 256K anyway.**
Both models clear the memory gate at 262K context (32.4 GB / 37.6 GB peak — the previously published 43.3 GB was REFUTED under adversarial verification 2026-08-17: no artifact carries it; the on-disk capacity ladder says 37.58 GB `server_peak_gb` @262144, and 43.38 belongs to the DIFFERENT model `Qwen3.6-27B-OptiQ-4bit`), and retrieval ladders pass.
But **no coding or reasoning quality has ever been measured at depth**, and the config imposes a
ceiling well below 256K: `max_tokens` 102400 with a `0.8 × (cap − prompt)` thinking-budget clamp means
the **designed maximum prompt is ~159,744 tokens** for `Ornith-1.0-35B-mlx-uniform-4bit`, and lower for
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` which wants a larger thinking budget. Above that the model silently
gets less room to think. So B's context requirement is currently satisfied *by assumption*, and the
measurement that would settle it is the depth condition listed under "what would change these picks".

### 2026-08-20 — the `Qwen3.8-27B` challenger does NOT displace the pick <!-- allow-shorthand -->

First admissible head-to-head at each model's own tuned operating point, fresh same-cap (262144)
arms, n=50, `--intersect`, `compare` refusals all clear:

| paired vs `Qwen3.8-27B-OptiQ-4.5bpw-mixed@t0.6` | humanevalplus | mbppplus |
|---|---|---|
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit@t0.3` acc | 95.7% vs 91.3% | 81.6% vs 81.6% |
| delta (95% CI) | +4.3pp [−4.3,+13.0] | +0.0pp [−6.1,+6.1] |
| verdict | **INCONCLUSIVE** | **INCONCLUSIVE** |

At n=50 (axis MDE ±18pp) the challenger cannot be separated from the incumbent — and the point
estimates lean toward the incumbent on humanevalplus. **The B pick stands.** The incumbent's
fresh-cap rows: humanevalplus `acc` 93.75% / `acc_strict@81920` 90.0% (DNFs `HumanEval/32`,
`HumanEval/132`); mbppplus 81.6% / 80.0% (DNF `Mbpp/306`).

**The runaway tax is CROSS-FAMILY and item-anchored, not model-specific.** At cap 262144 the
incumbent `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` DNF'd 3/100 items across the pair — including
`HumanEval/32`, the same item `Qwen3.8-27B-mlx-uniform-4bit` ran away on — rate-matched to the
challenger's 2/100. Each DNF is a deterministic runaway (seeded draws reproduce byte-identically:
`Mbpp/306` burned its full 3600s probe-timeout twice, then ~13 min of server-side drain after each
client abandonment — ~73 min of GPU per runaway occurrence, an argument for a skip-known-timeout
resume rule). Meanwhile the Stage-1 rungs of `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`,
`Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit` and `Qwen3.6-35B-A3B-Fable-5-Distill-mlx-uniform-4bit`
all sit at **zero DNFs, conv 15/15** — the distillation-fixes-runaways hypothesis survives another
contact; their n=50 Stage-2 screens are in flight.

> ### No recommendation is supported by the evidence. Provisional lean only.
> **If you want one today:** `Ornith-1.0-35B-mlx-uniform-4bit` for interactive feel (3.8× faster decode,
> and the two are equivalent on the only axis measured); `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` for
> reasoning-heavy sessions, where it does not burn its budget.

### 2026-08-22 — 🚨 the "t0.5 knee" results are RETRACTED as shipped-config evidence (O36); deployed-profile redo in flight

Every M19/M20 "t0.5" command (scans, DNF-first probes, n=15 rungs, and the full gate-3 2×50
re-screens) omitted `--sampling-profile deployed` and silently ran the RETIRED `production`
profile (`min_p 0.03`, `presence_penalty 0.3`, resolved `thinking_budget 49152`) — four knobs
moved at once, not a temperature OFAT. The fingerprint guard caught it (`compare` refused
across the profile mismatch). The rows are quarantined under tune **`t0.5prod`** — real,
graded measurements of a config we do not ship: `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`
humanevalplus `acc` 92.0% / `acc_strict@49152` 88.0% (conv 96%), mbppplus 85.7% / 84.0%
(conv 100%, 1 DNF `Mbpp/440`); `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit` humanevalplus
78.0% / **56.0%** (conv 66%, 17 `degenerate_repetition`), mbppplus 77.5% / **58.0%** (conv
67%, 16 loops + 1 DNF). The t0.6 arms are clean deployed rows and their story stands. What
survives config-independently: (1) gate 3 works — the n=15 rung passed 15/15 where the n=50
arm collapsed, so small rungs under-sample loop floors; (2) the runaway class is
CONFIG-SENSITIVE — some lever in {temp, min_p, presence_penalty, budget} collapses it, and the
deployed-profile redo (only temp moving) is the attribution instrument; (3) probe-set
amendments: DNF-first-only probing has a non-monotonic blind spot (a lower temp converted 3
old failures and minted 13 new loopers), so probes now carry ~5 previously-clean SENTINEL
items, and capped-probe verdicts split "non-stop WITH a repetition signature" (trustworthy)
from "without" (indeterminate — `HumanEval/32`/`Mbpp/306` failed the cap yet converged at
full budget). Redo ladder (all rungs `--sampling-profile deployed`, explicit): capped scan
DONE (`HumanEval/2` converges at t0.5 in 1,693 tokens; the t0.4/t0.3 rows are clamp
false-passes by their own flag, treated indeterminate) → DNF-first probe in flight →
sentinel probe → n=15 rung → gate-3 2×50. `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit`
follows with t0.55 as an operator-approved rung candidate. D13 (zero-GPU corpus sweep,
`benchmark/m1/dnf_sweep.py`): family-matched cells on the same base weights at t0.6 —
`Qwen3.8-27B-mlx-uniform-4bit` mbppplus 7/51 DNF vs `Qwen3.8-27B-OptiQ-4.5bpw-mixed` 0/50 —
support precision-drives-runaways; pooled rollups are flagged non-evidential in the tool
itself; M21 remains the causal test.

### 2026-08-22 (late) — M19 deployed redo COMPLETE: **t0.6 STANDS on both benches**; the "t0.5 knee" is closed as a production-profile artifact

Gate-3 2×50 for `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`, all arms
`--sampling-profile deployed` explicit, paired items/seeds, budget 81920, same deployed sha:

- **humanevalplus**: t0.5 `acc` 89.1% [78.3, 97.8] / `acc_strict@81920` 82.0% / 4 DNFs
  {`HumanEval/108`,`/32`,`/99`,`/132`} vs t0.6 `acc` 95.6% [89, 100] / 86.0% / 5 DNFs
  {`/2`,`/82`,`/32`,`/99`,`/39`}.
- **mbppplus**: t0.5 `acc` 82.6% [69.6, 93.5] / 76.0% / 4 DNFs
  {`Mbpp/620`,`/306`,`/440`,`/472`} vs t0.6 `acc` 86.7% [75.6, 95.6] / 78.0% / 5 DNFs
  {`/306`,`/593`,`/129`,`/440`,`/124`}. Both t0.6 mbpp grades re-certified zero-GPU
  (evalplus flake pattern did not recur); t0.5 graded clean first pass.

**Verdict: t0.6 stands as the certified tune.** At MDE ~±18–19pp per leg no single delta
resolves, but t0.5 shows no advantage on ANY endpoint — `acc` point estimates sit 6.5pp
(hep) and 4.1pp (mbpp) BELOW t0.6, `acc_strict` likewise (82.0<86.0, 76.0<78.0), DNF rate
flat (4 vs 5 per leg), conv 100% on all four arms. The DNF sets churn non-monotonically on
both benches (mbpp: kept hard core {`Mbpp/306`,`/440`}, fixed 3, minted 2 — same shape as
hep), i.e. lowering temp reshuffles rather than removes the runaway set. **Attribution
sealed:** the t0.5prod loop plague (17+16 `degenerate_repetition`/50) reproduces NOWHERE at
deployed t0.5 — zero loops across all 96 generated rows both benches (one self-terminating
degenerate each side, `Mbpp/265` t0.5 / `Mbpp/620` t0.6, scored converged per policy) — so
the loops were production-knob effects (clamped 49152 budget and/or `min_p 0.03` /
`presence_penalty 0.3`), not temperature. M19 CLOSED; M20 (`Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit`
deployed ladder, t0.55 rung candidate) is next and expectation transfers: its loop
catastrophe should likewise evaporate at the deployed config.

### 2026-08-23 — M20 deployed ladder COMPLETE: t0.55 beats t0.6 on the ranking key for `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit` (certification = O37, awaiting ruling)

Full ladder at `--sampling-profile deployed` explicit throughout. Capped scan (t0.55, 8192
cap): sentinels 5/5 CONV, 9/14 old t0.6 DNFs convert, zero repetition signatures — the
t0.5prod loop catastrophe (17+16/50) does NOT exist at the deployed config, confirming the
M19 production-knob attribution on the second model. DNF-first (full 81920 budget): 10/14
convert (incl. `Mbpp/440`, 7,920 tok); holdouts {`HumanEval/86`,`Mbpp/306`,`/620`,`/739`}.
n=15 rung: pass@1 HOLDS — paired 13/15 vs 13/15. Gate-3 2×50 (resume pooled the ladder's
same-tune rows; the 4 known runaways did not re-burn):

- **humanevalplus**: t0.55 `acc` 83.7% [73.5, 93.9] / `acc_strict@81920` **82.0%** / **1 DNF**
  vs t0.6 88.4% [79.1, 97.7] / 76.0% / 7 DNFs.
- **mbppplus**: t0.55 77.8% [64.4, 88.9] / **70.0%** / 5 DNFs
  ({`306`,`620`,`739`} kept, {`793`,`806`} minted) vs t0.6 79.1% [67.4, 90.7] / 68.0% /
  7 DNFs. (mbpp t0.55 first grade returned null — the evalplus late-file flake, third
  occurrence — zero-GPU re-grade certified.)

**Unlike the M19 sibling, t0.55 genuinely SHRINKS the runaway set (14→6 total) instead of
churning it**, and `acc_strict` — the ranking key — favors t0.55 on both benches (+6.0pp
hep, +2.0pp mbpp). Exclusive solves crossed 7 vs 3 favoring t0.55 (not resolvable at 10
discordants). `acc`-on-generated dips are inside MDE and denominator-skewed (t0.6's `acc`
excludes its own 7 hard DNF items). Zero loops in all 129 deployed-t0.55 rows across the
ladder. **Recommendation: certify t0.55 (O37).** Scan/probe artifacts live at
`$STACK_WORKDIR/status/m20_scan/`, never in `results/`.

### 2026-08-26 — M23 CLOSED BY CONSTRUCTION: the two `Qwen3.8-27B` 4-bit arms are the SAME MODEL <!-- allow-shorthand -->

A full-tensor md5 sweep proved `Qwen3.8-27B-mlx-uniform-4bit` and the official
`mlx-community/Qwen3.8-27B-4bit` identical on 2179/2180 tensors — the sole delta is the
bf16-grafted vision tower, which text benches never touch. MLX uniform 4-bit gs64
quantization is deterministic; our conversion reproduced the official quant byte-for-byte.
`caslca/Qwen3.8-27B-mlx-uniform-4bit` is canonical (C33); the `Qwen3.8-27B-4bit` registry
entry is retired.

**Consequently every m23/m23b "cross-arm difference" ever reported — the 94.1%-vs-87.5%
humanevalplus split, the "10× more verbose at a matched seed" contrast, the DNF asymmetry —
was SESSION NOISE between identical models.** Those rows are re-purposed as same-model
session replicates for C30 (the session-variance bound); they must never again be cited as
model evidence. Conversion bias for this family is exactly zero, by construction.

**m23c clean-session grades** (post-C26 fork fix, seeds honored, pinned probe-timeout;
recorded under the retired dir name, pooling per C33 ruling 3): humanevalplus n=20 `acc`
**100%** / `acc_strict@81920` **100%**, conv 100%; mbppplus n=20 **80% / 80%**, conv 100%
— **zero runaways**, where the unseeded m23b session of the same model had 2 budget-hits.
Whether honored seeds systematically avoid runaway trajectories is an open C30
sub-question (n=1 session). The 5+5-item pilot under the canonical name (hep 100/100,
mbpp 60/60, conv 100%) produced 10/10 byte-identical outputs vs the "other" arm — the
observation that exposed the identity.

⚠️ The generated scoresheet below does NOT yet display the m23c grades: tune-suffixed
`*_samples.jsonl` evalplus sidecars (padded full-corpus, scoreless) shadow graded variants
via the largest-n selection — root-caused 2026-08-26, fix pending approval (C34). The
affected cells read `164 ungraded` / `378 ungraded` for pairs that DO have graded rows.

**I am not going to dress this up: C's construct has never been measured.** What exists:

- **IFEval, n=148 paired: `equivalent`** (89.9% vs 89.9%, CI inside the ±5pp TOST margin). This is a
  legitimate equivalence verdict — but IFEval measures compliance with *short mechanical constraints*
  ("all caps", "exactly 3 bullets", "use word X four times"). It is close to worthless as a proxy for
  whether a model is a good research or design partner. **Reporting it as C's basis overstates what is
  known**, which earlier revisions of this doc did at MEDIUM confidence.
  ✅ Its grader was non-deterministic until 2026-08-14 and is now reproducible; the verdict did not
  change (see defect note 2 on the scoresheet).
- **math500** (supporting, reasoning): at a matched 81,920 budget, `acc` is a tie (83.3% vs 81.5%) but
  **`acc_strict` splits 60.0% vs 81.5%**, because `Ornith-1.0-35B-mlx-uniform-4bit` hits the thinking
  budget on **9 of 30** items. Suggestive and mechanistically attributable — but n=30/27, unmatched
  items, MDE ±23pp, so the 21pp gap is at the edge of resolvable. Not a verdict.
- **BFCL native-FC (M18, tool calling): COMPLETE 2026-08-24, n=1000/model, all trees clean.**
  `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` **0.929** vs `Ornith-1.0-35B-mlx-uniform-4bit` **0.914**
  (1.5 pp, INSIDE the ~±4 pp axis MDE — inconclusive on accuracy) vs
  `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` **0.860** (real deficit). **Runaway tax inverts
  the morning read**: 4/1000 at 78–81 min/event (~17 tok/s dense decode) vs 2/1000 at ~21 min vs
  1/1000 at ~12 min — the 4th ranking number favors `Ornith-1.0-35B-mlx-uniform-4bit` over
  `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` despite the identical ~2% parallel-category rate.
  Vendored native-FC handler posting raw `messages`+`tools` to `/v1/chat/completions` (the
  template confound below is RESOLVED); O41 derived timeouts; poison-guarded rescore. Full story:
  lab-notebook 2026-08-24 entries.
  ⚠️ History note (kept): before 2026-08-24 this axis was NOT RUN and an earlier "smoke passed"
  claim was false (a `|| true` masked `unknown benchmark 'bfcl'`); the original blocker was a
  template confound — bfcl's OSS handler posts `/v1/completions` through a foreign registered
  template, none of our registry names in its `MODEL_CONFIG_MAPPING`, stock keys in
  forbidden prompt mode.
- **The judge panel** — the only instrument that could measure C's actual construct — is on record as
  **NOT RELIABLE ENOUGH TO RANK**. Measured 2026-08-15: order consistency **71% / 42% / 62%** by
  role, Krippendorff **α = 0.517**, panel p = 0.80. **Score-based aggregation was tested and
  FALSIFIED** (identical 58% pooled), which locates the instability in the JUDGEMENT, not in the
  readout — so it cannot be fixed by changing how votes are counted. (An earlier "55%
  self-consistent at v2" is superseded by these figures.)
- **No deep-research axis exists at all.**

**So C is blocked on instrumentation, not on worker time**, and that is the single most important thing
on this page. Building a research/synthesis axis and making the judge panel reliable are prerequisites
to C having an answer at all.

## 🆕 A THIRD CANDIDATE IS NOW IN THE MATCHED COMPARISON — and it is not separable on capability
`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`, registered and measured 2026-08-14, same box, same session,
matched items, `deployed`, budget matched so `compare` pairs rather than refuses.

| paired vs NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit, n=100 | delta | 95% CI | verdict |
|---|---|---|---|
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, humanevalplus | −4.0pp | [−10.0, +2.0] | INCONCLUSIVE |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, mbppplus | −3.0pp | [−10.0, +3.0] | INCONCLUSIVE |
| `Ornith-1.0-35B-mlx-uniform-4bit`, humanevalplus | −3.0pp | [−8.0, +2.0] | INCONCLUSIVE |
| `Ornith-1.0-35B-mlx-uniform-4bit`, mbppplus | −2.0pp | [−7.0, +3.0] | INCONCLUSIVE |
| `Ornith-1.0-35B-mlx-uniform-4bit`, **ifeval** (n=200) | −0.5pp | [−5.5, +4.5] | INCONCLUSIVE |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, **ifeval** (n=148) | +0.0pp | [−5.4, +4.7] | INCONCLUSIVE |

**IFEval added 2026-08-16** (n=200, 200/200 converged, 0 budget-hits, 0 degenerate, 98 min): `acc`
**90.5%**, `acc_strict` **90.5%** — identical, so like `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` it forfeits nothing to truncation,
whereas `Ornith-1.0-35B-mlx-uniform-4bit` loses 3.3pp and `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` 4.8pp on their own ifeval rows. Both pairings needed
`compare --intersect`, because the three ifeval runs cover 541 / 200 / 148 items with each set nested
in the last; the deltas above are on the shared items, dropping 341 Ornith-1.0-35B-mlx-uniform-4bit-only and 52 NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit-only
respectively. This makes **all three models statistically indistinguishable on every capability axis
measured so far** — the daily-driver axis is now a three-way inconclusive, not a two-way one.

**Every interval spans zero: it is not measurably worse than either winner on single-shot coding, and not
measurably better.** Where it IS separable is on the numbers this suite reports beside capability:

| | NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit | Ornith-1.0-35B-mlx-uniform-4bit | Qwen3.6-27B-Opus-Distill-OptiQ-4bit |
|---|---|---|---|
| **`mx.get_peak_memory` @ 262144** | **26.0 GB** | 32.4 GB | 37.6 GB (corrected 2026-08-17; was published as 43.3, refuted — see `docs/lab-notebook.md`) |
| retrieval @ 262144 | **1.00** | — | — |
| decode @ 262144 / short ctx | **70.3 / 146** tok/s | — / ~107 | — / ~28.6 |
| wall per item (hep / mbpp) | **28.8 s / 17.6 s** | 42 s / — | 51 s / — |
| `conv%` (hep / mbpp) | **99 / 100** | 98 / 96 | 99 / 98 |
| degenerate wall-share (hep) | **25%** | 40% | 41% |

### 🆕 AGENTIC 2026-08-16: the EDIT PROTOCOL is the limitation, not agentic coding

One box, one session, `deployed` sampling, cap 65536 (matched to the aider rows):

| `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` | edit-protocol failures | passed |
|---|---|---|
| aider `diff` (byte-exact SEARCH/REPLACE), n=4 go | **3.75 malformed per case** | 0/4 |
| aider `whole` (full-file rewrite), n=4 go | 0 | 1/4 |
| **opencode (tool-call edits), n=4 python** | **0** | **4/4** |

For scale, the winners' malformed rates over all 110 aider cases are **0.036**
(`Ornith-1.0-35B-mlx-uniform-4bit`) and **0.009** (`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`) per case — so
under `diff` this candidate is ~100× worse, and under two other protocols not measurably worse at all.
A temperature OFAT rules sampling out (temp 0.4 made malformed WORSE, 21 vs 15 on the same items).

**Had the original 110-case aider run been allowed to finish it would have produced a near-zero row and
the verdict "unsuitable for agentic work", which is false.** The true statement is narrower: unsuitable
for aider's `diff` protocol.

⚠️ **What the agentic rows do NOT support:** n=4, and both winners pass all four python items, so they
are easy items that do not discriminate; the opencode rows are **first-attempt only** while aider's
`final` allows a second test-informed attempt, so 4/4 must not be set against 50.0% / 73.6%; and the
aider-vs-opencode contrast is **not item-matched** (go vs python), so only the direction is trustworthy.

⚠️ **What this does NOT establish.** It has no reasoning row beyond ifeval, and the B
pick rests on the AGENTIC axis, not on these two benches. A third model that ties on single-shot coding
while costing 17 GB less and running ~2× faster is a strong *candidate*, not a pick. **Next measurement is
aider polyglot**, where the campaign's only powered result lives (+23.6pp, p=1.3e-05) and where effects are
large enough to resolve at feasible n.
⚠️ **The 4→6-bit quant ladder was CANCELLED by arithmetic, not skipped by preference** — the remaining
headroom to the leader (~4pp) is smaller than the axis MDE (±12.5pp at n=100), so the probe could not
answer its own question. See O19.

## What would change these picks, in order of value

1. **Make the judge panel reliable, then run it.** It is the only instrument that can speak to C, and C
   currently has none. ⚠️ **NO LONGER "cheap in model time"** (revised 2026-08-15): score-based
   aggregation was tested and falsified, so the instability is in the judgement rather than the
   readout. Fixing it needs PRODUCTION changes — more than 24 items, more raters/replicates, a less
   position-sensitive protocol — all of which cost model time. The cheap readout fix is spent.
2. **A depth condition on B** — re-run a coding subset with a realistic repo-sized prompt (~128K, inside
   the no-clamp regime for both). Turns B's context requirement from an assumption into a measurement.
3. **opencode agentic evidence.** The B pick is aider-specific and opencode is what we ship.
4. ✅ **BFCL at n — DONE 2026-08-24 (M18, n=1000/model, 3 models).** See the BFCL bullet above.
5. **math500 at n≈100.** The 21pp `acc_strict` split is real-looking and currently unresolvable.
6. **The runaway-tax temperature ladder, measuring pass@1 alongside convergence.** ~40% of wall-clock on
   both models; a 3-item pilot showed temperature moves it, but **pass@1 is unmeasured** and AGENTS.md
   makes pass@1 the hard constraint with convergence strictly secondary.

---

# 📋 THE SCORESHEET — generated, do not hand-edit

**Regenerate with** (runs on EITHER box — `benchmark/results` is tracked in git, so both boxes carry
the rows once synced; the driver is the normal place, since grading is driver-side work):

```bash
PYTHONPATH=benchmark .venv-bench/bin/python benchmark/m1/scoreboard.py --md
```

**Provenance of the table below:** regenerated 2026-08-18 on the **M5 Max** (single box) after the O31 ruling — error rows (harness timeouts) now count as FAILURES in `strict`, never exclusions; 7 affected score files were re-graded in the same pass, so every `strict` cell is under the same definition. Previous generation: 2026-08-16, M4 Pro driver, `64f7883`, 20 result directories. (The previous note said "2026-08-14, worker, `1ce8178`, 19
directories, must run where the rows live" — the must-run-on-worker part was never true.) `acc` / `acc_strict` are read from the per-pair
`results/<model>/<bench>.score.json` written by `grade_all` — one file per (model, bench), so grading one
model can no longer erase another's record.

### ⚠️ TWO THINGS TO KNOW BEFORE READING A CELL

**1. `ungraded` is not a zero and not a blank — it means the grader has not been run for that pair.**
As of 2026-08-14 the two winners' `humanevalplus` and `mbppplus` cells ARE graded (Docker evalplus, run
after the generation finished and the model was unloaded, so no contention with a timed run). Still
`ungraded`, with reasons:
- ✅ **`livecodebench` is GRADED, not blocked** (corrected 2026-08-15). The claim that `lcb_runner`
  "is not installed, pending an env change" described work that was already done: `lcb_runner`
  imports and runs on the DRIVER (from a `third_party/LiveCodeBench` checkout, with a 4.1 GB dataset
  cache), and grading is driver-side work anyway. A re-grade reproduced every cell identically, which
  is also a determinism check. Cells: Ornith-1.0-35B-mlx-uniform-4bit 80.0/60.0, Ornith-1.0-35B-mlx-uniform-4bit-suffix 93.3/80.0, Ornith-1.0-35B-mlx-uniform-6bit
  86.7/40.0, distill 80.0/80.0.
- **every non-winner model dir** (`-suffix`, `-kv4`, `-6bit`, the gemma-4 family) — the 19-dir grading batch
  **hung** on a Rosetta fault (`mmap_anonymous_rw mmap failed`) with 377/378 MBPP problems done and one
  sample (`Mbpp/255`) wedged, which evalplus waits on indefinitely. It is a flake, not deterministic.
  **Docker grading needs a per-run timeout** so one wedged sample cannot block a batch; until then the
  batch was re-scoped to the decision-relevant arm.

**2. ✅ THE IFEVAL GRADER WAS NON-DETERMINISTIC — FOUND AND FIXED 2026-08-14 (`2a27d21`, `b04030c`).**
Re-grades of *identical* rows returned different scores. **Two independent causes, and finding the
first one masked the second:**

| # | mechanism | evidence |
|---|---|---|
| 1 | **`langdetect` unseeded.** Three verifiers call `langdetect.detect()` (`instructions.py:158` `response_language`, `:1416` `english_capital`, `:1448` `english_lowercase`); `DetectorFactory.seed` was set nowhere, so it samples randomly. | distill `acc` 0.8986 / 0.8986 / **0.8919** over 3 re-grades |
| 2 | **`random` unseeded in the verifiers.** 24 sites in `instructions.py` fabricate an **absent kwarg** with `random.choice`/`random.randint` (e.g. `:1350` `self._frequency = random.randint(1, _LETTER_FREQUENCY)`) — so for those items the grader **invents the threshold it checks against**. | after fixing #1, Ornith-1.0-35B-mlx-uniform-4bit began wobbling: 0.9002 / 0.9002 / **0.8983** / **0.9020** |

**Scope of #2, measured over 8 RNG states rather than assumed: 1 verdict of 541 (0.2%), `acc` spread
90.02–90.20% = 0.18pp.** Immaterial to every published verdict; fatal to reproducibility. Ruled out by
measurement: `PYTHONHASHSEED` (pinning to 0 still wobbled) and concurrency (`grade.py` has none).

**Fixes:** langdetect seeded at `_load_ifeval_lib`, the one seam every IFEval grade loads through; and
the verifiers reseeded **per item** from a `crc32` of the item id — not once per batch, because a batch
seed leaves each verdict dependent on how many draws preceded it, so a resume, a different `--limit` or
a reordered queue would silently change verdicts. **Verified: six independent processes, both arms,
bit-identical.**

⚠️ **What this changed about the published numbers: nothing, and that is the point.** The canonical
figures are `Ornith-1.0-35B-mlx-uniform-4bit` **90.0% / 86.7%** and
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` **89.9% / 85.1%** — i.e. exactly what was already published. The
`equivalent` verdict stands. What was broken was not the value but the *guarantee* that reading it twice
gives the same answer.

| model | bench | n | acc | strict | conv% | degenAll | degenAllWall% | degenEosedWall% | budget | kv |
|---|---|---|---|---|---|---|---|---|---|---|
| NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit | capacity_ladder | 2 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit | humanevalplus | 100 | 89.0% | 88.0% | 99 | 1 | 25 | 0 | 81920 | fp16·attn6/52 |
| NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit | ifeval | 200 | 90.5% | 90.5% | 100 | - | - | 0 | 81920 | fp16·attn6/52 |
| NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit | mbppplus | 100 | 81.0% | 81.0% | 100 | - | - | 0 | 81920 | fp16·attn6/52 |
| NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit | opencode | 26 | ungraded | ungraded | n/a | - | - | n/a | - | fp16·attn6/52 |
| Ornith-1.0-35B-mlx-uniform-4bit | aider [diag] | 110 | 50.0% | 50.0% | n/a | - | - | n/a | - | n/a |
| Ornith-1.0-35B-mlx-uniform-4bit | aime | 5 | 80.0% | 60.0% | 80 | - | - | 0 | 81920 | fp16 |
| Ornith-1.0-35B-mlx-uniform-4bit | capacity_ladder | 2 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Ornith-1.0-35B-mlx-uniform-4bit | humanevalplus | 164 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Ornith-1.0-35B-mlx-uniform-4bit | ifeval | 541 | 90.0% | 86.7% | 95 | 30 | 42 | 0 | 81920 | fp16·attn10/40 |
| Ornith-1.0-35B-mlx-uniform-4bit | livecodebench | 15 | 80.0% | 60.0% | 80 | - | - | 0 | 81920 | fp16 |
| Ornith-1.0-35B-mlx-uniform-4bit | math500 | 30 | 83.3% | 60.0% | 70 | - | - | 0 | 81920 | fp16 |
| Ornith-1.0-35B-mlx-uniform-4bit | mbppplus | 378 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Ornith-1.0-35B-mlx-uniform-4bit | opencode | 22 | ungraded | ungraded | n/a | - | - | n/a | - | fp16·attn10/40 |
| Ornith-1.0-35B-mlx-uniform-4bit-kv4 | capacity_ladder | 4 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Ornith-1.0-35B-mlx-uniform-6bit | humanevalplus | 10 | 90.0% | 80.0% | 90 | - | - | 0 | 81920 | fp16 |
| Ornith-1.0-35B-mlx-uniform-6bit | livecodebench | 15 | 86.7% | 40.0% | 47 | - | - | 0 | 81920 | fp16 |
| Ornith-1.0-35B-mlx-uniform-6bit | mbppplus | 10 | 80.0% | 80.0% | 100 | - | - | 0 | 81920 | fp16 |
| Qwen3.6-27B-MLX-8bit | aime | 5 | 80.0% | 60.0% | 80 | - | - | 0 | 81920 | TQ4·attn16/64 |
| Qwen3.6-27B-MLX-8bit | humanevalplus | 6 | 100.0% | 100.0% | 100 | - | - | 0 | 81920 | TQ4·attn16/64 |
| Qwen3.6-27B-MLX-8bit | mbppplus | 6 | 83.3% | 50.0% | 67 | - | - | 0 | 81920 | TQ4·attn16/64 |
| Qwen3.6-27B-OptiQ-4bit | aime | 5 | 80.0% | 80.0% | 80 | - | - | 0 | 81920 | TQ4·attn16/64 |
| Qwen3.6-27B-OptiQ-4bit | capacity_ladder | 1 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.6-27B-OptiQ-4bit | humanevalplus | 10 | 100.0% | 100.0% | 100 | - | - | 0 | 81920 | TQ4·attn16/64 |
| Qwen3.6-27B-OptiQ-4bit | livecodebench | 1 | 100.0% | 0.0% | 0 | - | - | 0 | 49152 | n/a |
| Qwen3.6-27B-OptiQ-4bit | mbppplus | 10 | 80.0% | 80.0% | 100 | - | - | 0 | 81920 | TQ4·attn16/64 |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | aider [diag] | 110 | 73.6% | 73.6% | n/a | - | - | n/a | - | n/a |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | aime | 4 | 100.0% | 80.0% | 100 | - | - | 0 | 81920 | TQ4 |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | capacity_ladder | 4 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | humanevalplus | 164 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | ifeval | 142 | 90.1% | 86.5% | 100 | - | - | 0 | 81920 | TQ4·attn16/64 |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | livecodebench | 15 | 80.0% | 80.0% | 100 | - | - | 0 | 81920 | TQ4 |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | math500 | 27 | 81.5% | 73.3% | 100 | - | - | 0 | 81920 | TQ4 |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | mbppplus | 378 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | opencode | 22 | ungraded | ungraded | n/a | - | - | n/a | - | TQ4·attn16/64 |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit-kv3 | capacity_ladder | 5 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.6-27B-UD-MLX-6bit | aime | 5 | 80.0% | 60.0% | 80 | - | - | 0 | 81920 | fp16·attn16/64 |
| Qwen3.6-27B-UD-MLX-6bit | capacity_ladder | 4 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.6-27B-UD-MLX-6bit | humanevalplus | 164 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.6-27B-UD-MLX-6bit | livecodebench | 3 | 100.0% | 66.7% | 67 | - | - | 0 | 49152 | fp16·attn16/64 |
| Qwen3.6-27B-UD-MLX-6bit | mbppplus | 378 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.6-35B-A3B-Fable-5-Distill-mlx-uniform-4bit | humanevalplus | 164 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.6-35B-A3B-Fable-5-Distill-mlx-uniform-4bit | mbppplus | 378 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.8-27B-4bit | humanevalplus | 164 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.8-27B-4bit | mbppplus | 378 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit | humanevalplus | 164 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit | mbppplus | 378 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit | opencode | 22 | ungraded | ungraded | n/a | - | - | n/a | - | TQ4·attn16/64 |
| Qwen3.8-27B-OptiQ-4.5bpw-mixed | capacity_ladder | 4 | ungraded | ungraded | n/a | - | - | n/a | - | TQ4·attn16/64 |
| Qwen3.8-27B-OptiQ-4.5bpw-mixed | humanevalplus | 164 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.8-27B-OptiQ-4.5bpw-mixed | mbppplus | 378 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit | humanevalplus | 164 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit | mbppplus | 378 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.8-27B-mlx-uniform-4bit | capacity_ladder | 4 | ungraded | ungraded | n/a | - | - | n/a | - | TQ4·attn16/64 |
| Qwen3.8-27B-mlx-uniform-4bit | humanevalplus | 164 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.8-27B-mlx-uniform-4bit | mbppplus | 378 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| Qwen3.8-27B-static-mixed-4bit | capacity_ladder | 4 | ungraded | ungraded | n/a | - | - | n/a | - | TQ4·attn16/64 |
| Qwen3.8-27B-static-mixed-4bit | humanevalplus | 164 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| gemma-4-26B-A4B-it-OptiQ-4bit | aime | 3 | 66.7% | 66.7% | 67 | - | - | 0 | 16384 | n/a |
| gemma-4-26B-A4B-it-OptiQ-4bit | capacity_ladder | 1 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| gemma-4-26B-A4B-it-OptiQ-4bit | humanevalplus | 11 | 100.0% | 72.7% | 73 | 2 | 57 | 0 | 32768 | uniform4·attn5/30 |
| gemma-4-26B-A4B-it-QAT-MLX-4bit | aime | 3 | 66.7% | 33.3% | 33 | - | - | 0 | 16384 | n/a |
| gemma-4-26B-A4B-it-QAT-MLX-4bit | capacity_ladder | 4 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| gemma-4-26B-A4B-it-QAT-MLX-4bit | humanevalplus | 3 | 100.0% | 100.0% | 100 | - | - | 0 | 16384 | n/a |
| gemma-4-26B-A4B-it-QAT-MLX-4bit | mbppplus | 3 | ungraded | ungraded | 100 | - | - | 0 | 16384 | n/a |
| gemma-4-26b-a4b-it-8bit | aime | 3 | 100.0% | 33.3% | 33 | - | - | 0 | 16384 | n/a |
| gemma-4-26b-a4b-it-8bit | capacity_ladder | 4 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| gemma-4-26b-a4b-it-8bit | humanevalplus | 4 | 100.0% | 100.0% | 100 | - | - | 0 | 16384 | n/a |
| gemma-4-26b-a4b-it-8bit | mbppplus | 4 | ungraded | ungraded | 75 | - | - | 0 | 16384 | n/a |
| gemma-4-31B-it-qat-6bit | aime | 5 | 100.0% | 100.0% | 100 | - | - | 0 | 16384 | uniform4·attn10/60 |
| gemma-4-31B-it-qat-6bit | humanevalplus | 12 | 91.7% | 76.9% | 83 | - | - | 0 | 16384 | uniform4·attn10/60 |
| gemma-4-31B-it-qat-6bit | livecodebench | 15 | 80.0% | 73.3% | 93 | - | - | 0 | 16384 | uniform4·attn10/60 |
| gemma-4-31B-it-qat-6bit | math500 | 30 | 83.3% | 83.3% | 100 | - | - | 0 | 16384 | uniform4·attn10/60 |
| gemma-4-31b-it-6bit | aime | 5 | 80.0% | 80.0% | 80 | - | - | 0 | 16384 | uniform4·attn10/60 |
| gemma-4-31b-it-6bit | humanevalplus | 10 | 100.0% | 100.0% | 100 | - | - | 0 | 16384 | uniform4·attn10/60 |
| gemma-4-31b-it-6bit | livecodebench | 20 | 90.0% | 70.0% | 75 | - | - | 0 | 16384 | fp16·attn10/60 |
| gemma-4-31b-it-6bit | mbppplus | 10 | 70.0% | 70.0% | 90 | - | - | 0 | 16384 | uniform4·attn10/60 |
| gemma-4-31b-it-UD-MLX-4bit | aime | 5 | 60.0% | 60.0% | 100 | - | - | 0 | 16384 | uniform4·attn10/60 |
| gemma-4-31b-it-UD-MLX-4bit | capacity_ladder | 1 | ungraded | ungraded | n/a | - | - | n/a | - | n/a |
| gemma-4-31b-it-UD-MLX-4bit | humanevalplus | 10 | 100.0% | 100.0% | 100 | - | - | 0 | 16384 | uniform4·attn10/60 |
| gemma-4-31b-it-UD-MLX-4bit | mbppplus | 10 | 80.0% | 80.0% | 100 | - | - | 0 | 16384 | uniform4·attn10/60 |

conv% = the GRADED convergence rate read from <bench>.score.json (judged against the SERVER-RESOLVED thinking budget); n/a = ungraded or undeterminable. degenAllWall% = wall-clock share of EVERY row whose trace shows a verbatim loop, however it ended (derived here). degenEosedWall% = the persisted `degenerate_wall_share`: the same share over the SELF-TERMINATING (EOS'd) degenerate rows ONLY — the loops the convergence formula counts as CONVERGED. The two are NOT interchangeable. kv = quantization of the GROWING attention-layer KV cache the run was SERVED with, from the run manifest: scheme+bits (TQ = turboquant, uniform = mlx uniform affine), fp16 = unquantized (kv_bits 0), n/a = pre-provenance run (NOT reconstructible from registry history — local overrides never committed). Rows differing in kv are different serving paths — do not pool. The ·attnK/N marker (hybrid/local-attention archs only) counts the K of N layers whose cache the kv scheme can actually quantize; the rest hold state the fork never converts — qwen3_5-family GatedDeltaNet fp32 recurrent state, nemotron_h fp32 Mamba SSM state, gemma4 sliding-window RotatingKVCache (stays UNQUANTIZED even at kv_bits 4). An arch constant looked up from the model config, not a per-run knob; no marker = every layer grows quantizable KV, or the config was unresolvable.

## Dimension coverage — what is measured and what is missing

The suite's dimensions, as encoded in `benchmark/m1/scoreboard.py`:

| dimension | benches |
|---|---|
| **reasoning** | `aime`, `math500`, `gpqa` |
| **coding** | `humanevalplus`, `mbppplus`, `livecodebench`, `aider` |
| **daily** | `ifeval`, `bfcl` |

**Only three of 19 result directories have any dimension above n=40**, and the two winners are the only
models with a `daily` cell at all. Full per-model coverage verdicts come from the same command as the
table above. The headline gaps:

- **`gpqa` has NEVER been run** for any model — reasoning is 2/3 axes at best.
- ✅ **`bfcl` IS now run at n** (M18, 2026-08-24: n=1000/model for `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`,
  `Ornith-1.0-35B-mlx-uniform-4bit`, `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`) — the earlier
  "never been run at n" statement is superseded; `daily` is 2/2 axes for those three.
- ✅ **`aider` IS now in the scoresheet** (fixed 2026-08-15, commit `738e3a9`): both arms appear as
  `aider | 110 | 50.0% / 73.6%`, reproducing the published result exactly. The earlier statement that
  it "is missing from every row" is superseded. Its `conv%` is deliberately `n/a` — aider gives a
  per-CASE view across turns, so there is no per-turn `finish_reason` to judge, and counting `None`
  as converged had printed a fabricated 100%.
  ⚠️ The n=110 set is **`m1f` plus the `m1g` java recovery overlay** for `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, and the rows
  were produced at **`max_kv_cache_size` 65536**, where the resolved thinking budget was ~52,390 and
  NOT the declared 81,920. Any new arm must match that cap to pair.
- **`gemma-4-31B-it-qat-6bit` cannot be compared to the winners at all**: it runs at `thinking_budget`
  16384 vs their 81920, and `compare` mechanically refuses cross-budget comparisons. Its 192K context
  ceiling is a config fact, not a zero.

---

## ⚠️ COMPARABILITY RULES THAT GOVERN EVERY CELL ABOVE

- **BOX TOPOLOGY CHANGED 2026-08-11 — the M2 Max 64GB is GONE**, replaced by an M4 Pro 48GB DRIVER that
  hosts NO models. **All model runs are M5 Max runs.** Every pre-2026-08-11 result in the lab notebook is
  HISTORICAL and NOT re-measurable, so it can inform a hypothesis but never a pick.
- **A pick requires: same box, same session, matched items, matched `thinking_budget`, and the
  `deployed` sampling profile.** `compare` mechanically refuses comparisons differing in
  `thinking_budget` or `max_tokens`.
- **Every delta carries its interval and the axis MDE.** Paired binary, α=.05, power .80:
  **n=15 → ±32pp, n=40 → ±20pp, n=100 → ±12.5pp, n=164 → ±9.8pp, n=378 → ±6.4pp.** Resolving 10pp needs
  157 matched items; 5pp needs 628. **"Inconclusive" is a valid and expected answer, and is NOT evidence
  of a tie.**
- **`acc_strict`@budget is the ranking key** at a matched budget: a truncated draw scores 0 with the
  denominator intact. `acc` keeps its historical meaning so published rows stay comparable.
  `pass@1|converged` is a DIAGNOSTIC and must never rank — it conditions on convergence and shrinks the
  denominator.
- **`conv%` and `nonconv_kinds` are DIAGNOSTICS, not a gate.** The `conv% ≥ 0.90` gate is WITHDRAWN.
- **`acc` measures one thing:** the provided tests pass within the harness's attempt budget. It says
  nothing about maintainability, readability, idiom or review-acceptability — those belong to the judge
  panel, which is not yet reliable enough to rank.

## Where everything else went

| doc | holds |
|---|---|
| **`docs/lab-notebook.md`** | the full chronological record — mechanisms, retractions, defect write-ups, superseded findings, process lessons. Read it to learn WHY a number is what it is. |
| **`docs/open-questions.md`** | the operator's decision queue: OPEN / CLOSED / CLOSED-BY-MEASUREMENT |
| **`docs/PLAN.md`** | the plan: the two decisions, the model field, the ordered work queue |
| **`docs/work-queue.json`** | the executable form of that queue, run by the `bench.workqueue` daemon |
| **`docs/handoff.md`** | the ONE handoff — last session's narrative |
| **`AGENTS.md`** | rules, gates, measurement discipline, traps |
