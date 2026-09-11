# Local model recommendations

Updated 2026-09-09 (M24g matched medium Go complete). Rankings are operator-approved, provisional choices based on quality and observed trends, not claims of statistically proven superiority. B is agentic coding; C is research, brainstorming and design. Models ship as a model/tune/predictor combination. Confidence intervals and limitations remain part of the evidence. [Full results](docs/campaign-results.md), [queue](docs/PLAN.md), [decisions](docs/open-questions.md).

## B: top four for agentic coding

| Rank | Model | Recommended configuration | Best for — and why |
|---|---|---|---|
| 1 | Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | t0.5, medium effort, certified repaired MTP | Python/Go agentic work:22/22 at medium on each, with zero stalls; strongest completion trend. Other languages remain unmeasured. |
| 2 | Qwen3.8-27B-mlx-uniform-4bit | t0.6, medium effort, certified MTP | Broad coding coverage, especially Python/JavaScript: favorable repeats and efficient medium effort; Go remains16/22 with six stalls. |
| 3 | Ornith-1.0-35B-mlx-uniform-4bit | t0.4, native expert routing, certified MTP | Rust and interactive coding: highest observed Rust score and short task latency. |
| 4 | Qwen3.6-27B-Opus-Distill-OptiQ-4bit | deployed t0.3, certified MTP | Repair-oriented fallback: strong older multi-attempt repair evidence; retain despite weaker current agentic trends. |

C57 approved this order on2026-09-09. C61/M36 approved repaired MTP for the first choice on2026-09-10. The [public sidecar](https://huggingface.co/caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter) is uploaded at revision `74bb2bc1feb60dbb8302bc8e6021d0be01f8f18d`; all four files passed anonymous download/checksum verification. Production registry now references it. Existing benchmark overlays remain immutable.

M36 pooled strict accuracy is88.0% ON versus88.33% OFF, difference−0.33pp,95% CI[−3.0,+2.33], n100×3, nominal MDE12.5pp; all600 responses converged. Paired wall-time ratio0.417 CI[0.238,0.603]. HumanEvalPlus alone trends−1.33pp CI[−5.33,+2.0]; MBPPPlus+0.67pp CI[−2.0,+4.67], nominal MDE17.7pp each. The combined evidence supports quality equivalence at±5pp and a substantial time benefit; retain the dataset-specific caveat. Model rankings are unchanged. The base model's M36 positive control passed at1.785x decode and84.8% acceptance. No expanded routing is promoted.

### B evidence

Passes out of 22 per language/session. Commas indicate distinct sessions, not pooled scores. These are historical configurations, not one matched comparison of all current recommended triples.

| Model | Python | Go | Rust | Java | JavaScript | Best for — evidence and limits |
|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 21; **22 at medium** | **20** historical; **22 at medium** | Not measured | Not measured | Not measured | Python/Go: both medium suites finished22/22 with zero stalls. Repaired MTP is approved and registry-enabled after pooled quality equivalence and favorable speed. Three languages remain unmeasured. M37 medium Math50097% strict, all converge; fewer tokens but two fewer solves than the base. |
| Qwen3.8-27B-mlx-uniform-4bit | 20, 18; **19 at medium** | 16 historical; **16 at medium** | 13 | 12 | **19, 18** | Broad coverage: favorable Python/JavaScript repeats; Rust is weaker. |
| Ornith-1.0-35B-mlx-uniform-4bit | 19, 18 | 11 | **17** | 12 | 12, 17 | Rust/latency: Rust leads; JavaScript varies markedly by session. ARM64 regrade confirms M34a MBPPPlus strict80.7% native versus78.7% expanded; native routing remains the recommendation. |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | 12, 18 | 12 | 15 | **13** | 17, 16 | Repair fallback: the 12-pass Python session did not repeat; do not rank from that outlier alone. |

Matched medium-effort Go COMPLETE: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`22/22, zero stalls,1.697h; `Qwen3.8-27B-mlx-uniform-4bit`16/22, six stalls,2.039h. Paired success difference **+27.3pp,95% CI[+9.1,+45.5]**, exclusive solves6:0, exact paired p=.03125 (not campaign-multiplicity adjusted); nominal axis MDE26.7pp. Paired wall-time ratio0.832, CI[0.614,1.064]. This strengthens the approved B first choice for Python/Go; no new promotion. Both measured predictor OFF, medium effort, at their own deployed temperatures. Individual 22-case sessions have shown swings of 5–6 cases. Some comparisons cross serving-path revisions. Missing results are not zeros. The leader's Python advantage over the base at medium is directional (3:0 discordant cases, exact p=.25). Medium-vs-medium pooled standalone coding strict difference is +0.8pp, 95% CI [-1.2,+3.0], n=214, nominal MDE 8.6pp; its smaller token count does not produce a wall-time advantage there. These limitations qualify the recommendation without erasing the observed trends.

M34a MBPPPlus native-evaluator confirmation for `Ornith-1.0-35B-mlx-uniform-4bit`: expanded-minus-native strict **−2.0pp, 95% CI [−6.7,+2.7]**, output-token ratio **1.545, CI [0.867,2.668]**, n=100 k=3 (nominal MDE12.5pp). The poorer MBPPPlus trend conflicts with favorable HumanEvalPlus/Math500 trends. Keep native routing while the queued resolution measures the tradeoff with and without the certified predictor.

M34r four-cell MBPPPlus experiment COMPLETE for `Ornith-1.0-35B-mlx-uniform-4bit`, n100×1 per cell: native OFF81% strict, native MTP78%, expanded OFF77%, expanded MTP78%. With MTP, expansion-minus-native strict0pp CI[−6,+6], ordinary−1pp CI[−5,+3], token ratio0.860 CI[0.425,1.673]; wall1.37/1.47h. Without MTP, expansion strict−4pp CI[−11,+3], token ratio2.106 CI[0.850,5.045]. Nominal MDE12.5pp. Recommend native routing for the better overall quality trend; the modest expanded-MTP speed trend does not establish an overall win across datasets. Native OFF had the best point estimates in this MBPPPlus set; existing MTP certification also includes a larger HumanEvalPlus arm with quality near parity and faster completion, so no global predictor withdrawal from this single set. B/C order unchanged.

## C: approved picks and evaluation shortlist (up to four)

Only ranks 1–2 are approved C picks. The remaining two entries are a research shortlist, not promotions; their placement does not imply measured superiority in subjective research/design quality.

| Rank/status | Model | Recommended configuration | Best for — and why |
|---|---|---|---|
| 1, provisional pick | NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit | t1.0, native routing, predictor OFF | Text-only reasoning and rapid iteration: small token count, fast decode, no non-convergence in the matched Math500 run. |
| 2, provisional pick | Qwen3.6-27B-Opus-Distill-OptiQ-4bit | deployed t0.3, certified MTP | Research/design requiring vision or a repair-oriented alternative; slower reasoning in the recorded run. |
| Shortlist, not ranked | Ornith-1.0-35B-mlx-uniform-4bit | t0.4, native routing, certified MTP | Fast vision-capable exploration; reasoning runs retain a larger runaway tax. |
| Shortlist, not ranked | Qwen3.8-27B-mlx-uniform-4bit | t0.6, medium effort, certified MTP | Accuracy-first reasoning candidate:99/100 on matched medium Math500, fewer tokens but slower decode than the C first choice; broader C assessment pending. |

### C evidence

Math500: M33 rows share one100-case set; M37 uses the newer100-case set shared with the temperature ladder. Do not directly compare scores across these sets. All use deployed tunes, predictor OFF, budget81920. **2026-09-09 scorer correction:** extracted LaTeX expressions are now parsed as math; earlier 89/88/86 strict scores were undercounts. Saved responses were regraded, not regenerated. Updated paired bootstrap intervals are below; do not reuse the old accuracy intervals. Timing/token measurements are unchanged.

| Model | Run / item set | Ordinary / strict correct | Non-converged | Mean output tokens/task | Generation time /100 | Best for — evidence and limits |
|---|---|---|---|---|---|---|
| NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit | M33 | **99 / 99** | **0** | **3,849** | **0.81 h** | Fast text reasoning: favorable quality and token/time trends. M34r MBPPPlus native84% versus expanded82% strict;100% convergence both. Native general default retained. C48 t0.7 MBPPPlus85% versus84% at t1.0; Math50097% versus96% at t1.0 also favors t0.7; C48 complete: Operator prefers t0.5:87% coding/97% math with less runtime/repetition than t0.3. t0.4 completed85% coding/95% math versus t0.5 87%/97%; final recommendation t0.5, activation approval pending. Production remains t1.0. Expansion math/coding tradeoff remains below. |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | M33 | 99 / 97 | 2 | 12,842 | 16.4 h | Vision-capable alternative; some correct answers incurred non-convergence. |
| Ornith-1.0-35B-mlx-uniform-4bit | M33 | 99 / 93 | 6 | 15,788 | 4.7 h | Fast decoding, but more tokens and non-convergence on reasoning. |
| Qwen3.8-27B-mlx-uniform-4bit | M37, newer matched set | 99 / 99 | 0 | 2,423 | 2.62 h | Accuracy-first C candidate: fewer tokens but slower decode; accuracy-first math candidate after M37 pair, no approved C reorder. |

M37 same-item comparison: `Qwen3.8-27B-mlx-uniform-4bit` medium99% strict versus `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` native t1.0 96% (+3pp CI[0,+7]) or t0.5 97% (+2pp CI[0,+5]); n100×1, nominal MDE12.5pp. Output-token ratios0.735 CI[0.534,1.005] and0.634 CI[0.428,0.931], respectively, but wall2.62h versus0.72/0.83h. It gains accuracy-first C consideration; M37 mixed-checkpoint result is97% strict versus this base99%, delta−2pp CI[−5,0], n100×1, nominal MDE12.5pp, all200 converge; mixed/base token ratio0.745 CI[0.582,0.937], wall2.20/2.62h. Recommend the base for accuracy-first math and retain the mixed checkpoint as token-efficient general coding leader; current C order unchanged.

Corrected paired strict deltas: `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` versus `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`: **+2pp, 95% CI [-2,+6]**; versus `Ornith-1.0-35B-mlx-uniform-4bit`: **+6pp, CI [+1,+12]**. These are descriptive pairwise intervals before family multiplicity adjustment; n=100 nominal axis MDE is 12.5pp. The recommendation rests on favorable strict-quality and token/time trends, not a blanket superiority claim.

M34r MBPPPlus expansion-minus-native for `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`:−2pp strict,95% CI[−8,+4], n100×1, nominal MDE12.5pp; output-token ratio1.198 CI[0.890,1.506], generation0.508h expanded versus0.367h native. No non-convergence in either arm. Native has the favorable coding quality and cost point estimates. Math500 expansion instead improves98% versus96%, +2pp CI[0,+5], n100×1, nominal MDE12.5pp; token ratio1.277 CI[1.053,1.591], wall1.023h expanded/0.716h native. Both arms fully converge. Retain native as the general default; keep expansion as a math-oriented candidate for operator review rather than discard its quality trend. No routing change approved.

C48 temperature ladder COMPLETE for `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`, native/predictor OFF, n100×1 per dataset:

| Temperature | MBPPPlus strict | Math500 strict | Non-converged coding / math | Combined generation time |
|---|---:|---:|---:|---:|
| 1.0, current | 84% | 96% | 0 / 0 | 1.083h |
| 0.7 | 85% | 97% | 0 / 0 | 1.210h |
| 0.5, operator-preferred provisional | 87% | 97% | 1 / 0 | 1.408h |
| 0.4 | 85% | 95% | 1 / 0 | 1.439h |
| 0.3 | 87% | 98% | 2 / 0 | 1.868h |

C62 operator decision: prefer t0.5 provisionally and test t0.4 next. The earlier t0.3 recommendation over-weighted its single extra mathematical solve relative to the operator’s preferred repetition/token tradeoff. Versus t0.5, coding difference0pp CI[−4,+4] and math+1pp CI[0,+3]; nominal MDE12.5pp per axis. Versus t1.0, t0.3 coding+3pp CI[−1,+8], math+2pp CI[0,+5]. These are descriptive paired intervals before correction across the temperature search. The gain is small and uncertain; retain the additional repetition/runtime cost explicitly. t0.5 is the preferred balance of quality, token use and repetition; t0.4 is running on the same cases before the final choice. Its coding result is86% ordinary/85% strict versus87% strict t0.5, difference−2pp CI[−7,+3], n100×1, nominal MDE12.5pp. Both have one non-converged response; token ratio0.972 CI[0.540,1.933], wall0.594/0.582h. Math500 also favors t0.5: t0.4 95% versus t0.5 97%, −2pp CI[−5,0], n100×1, nominal MDE12.5pp; both fully converge, token ratio0.957 CI[0.735,1.209], wall0.844/0.826h. Recommend adopting the operator-preferred t0.5 provisional default; no automatic activation. **Production remains t1.0 until operator approval.** Ladder samples differ from the M33 table above; do not compare their raw percentages as matched results.

Math500 measures mathematical correctness, not brainstorming/design quality. BFCL has prior results (M18); subjective judge-panel work remains incomplete. C stays provisional. M34c's five-case Math500 pilot also regrades from 1/5 to **5/5 in both routing arms** after the parser correction. Its MBPPPlus pilot is native 4/5 vs expanded 5/5 at greater token/time cost: a candidate tradeoff, not a promotion. Rosetta evaluation failures were reproduced and removed by native ARM64 regrading of both M34a arms. Expanded ordinary MBPPPlus rose by one success; strict results were unchanged because that answer did not converge. Larger expansion resolution arms are queued in PLAN.


# Getting started
```sh
./runserver
```

or to just initalize the local python env:
```sh
git submodule update --init --recursive
uv sync
```

# update forked deps with
```sh
git submodule update --init --recursive --remote
```

# updating locally-checked-out packages
```sh
uv lock --upgrade    # re-resolves everything, rewrites uv.lock
uv sync              # applies the new lock to your .venv
```

# HuggingFace cache management
## download a model
```sh
uv run hf download mlx-community/gemma-4-31b-it-6bit
```

## run script to update all downloaded models
```sh
uv run hf_sync.py
```

## clean cache from stale versions - the ones we have a more recent version downloaded
```sh
uv run hf cache prune
```
