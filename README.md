# Local model recommendations

Updated 2026-09-09. Rankings are operator-approved, provisional choices based on quality and observed trends, not claims of statistically proven superiority. B is agentic coding; C is research, brainstorming and design. Models ship as a model/tune/predictor combination. Confidence intervals and limitations remain part of the evidence. [Full results](docs/campaign-results.md), [queue](docs/PLAN.md), [decisions](docs/open-questions.md).

## B: top four for agentic coding

| Rank | Model | Recommended configuration | Best for — and why |
|---|---|---|---|
| 1 | Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | t0.5, medium effort, predictor OFF | Python/Go agentic work: strongest recorded completion and stall trends. Other languages remain unmeasured. |
| 2 | Qwen3.8-27B-mlx-uniform-4bit | t0.6, medium effort, certified MTP | Broad coding coverage, especially Python/JavaScript: favorable repeat-session results; medium cuts token use substantially. |
| 3 | Ornith-1.0-35B-mlx-uniform-4bit | t0.4, native expert routing, certified MTP | Rust and interactive coding: highest observed Rust score and short task latency. |
| 4 | Qwen3.6-27B-Opus-Distill-OptiQ-4bit | deployed t0.3, certified MTP | Repair-oriented fallback: strong older multi-attempt repair evidence; retain despite weaker current agentic trends. |

C57 approved this order on 2026-09-09. C51's medium predictor probe passed at 1.644x decode speed, 84.8% acceptance. Live benchmarks keep their immutable overlays; registry changes take effect at the next router transition. No expanded-routing configuration is promoted.

### B evidence

Passes out of 22 per language/session. Commas indicate distinct sessions, not pooled scores. These are historical configurations, not one matched comparison of all current recommended triples.

| Model | Python | Go | Rust | Java | JavaScript | Best for — evidence and limits |
|---|---|---|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 21; **22 at medium** | **20**, historical effort | Not measured | Not measured | Not measured | Python/Go: medium Python had zero stalls; missing three-language coverage limits generalization. |
| Qwen3.8-27B-mlx-uniform-4bit | 20, 18; **19 at medium** | 16, historical effort | 13 | 12 | **19, 18** | Broad coverage: favorable Python/JavaScript repeats; Rust is weaker. |
| Ornith-1.0-35B-mlx-uniform-4bit | 19, 18 | 11 | **17** | 12 | 12, 17 | Rust/latency: Rust leads; JavaScript varies markedly by session. |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | 12, 18 | 12 | 15 | **13** | 17, 16 | Repair fallback: the 12-pass Python session did not repeat; do not rank from that outlier alone. |

Medium-effort Go arms are running for the first two entries; no prefix is a final result. Individual 22-case sessions have shown swings of 5–6 cases. Some comparisons cross serving-path revisions. Missing results are not zeros. The leader's Python advantage over the base at medium is directional (3:0 discordant cases, exact p=.25). Medium-vs-medium pooled standalone coding strict difference is +0.8pp, 95% CI [-1.2,+3.0], n=214, nominal MDE 8.6pp; its smaller token count does not produce a wall-time advantage there. These limitations qualify the recommendation without erasing the observed trends.

## C: approved picks and evaluation shortlist (up to four)

Only ranks 1–2 are approved C picks. The remaining two entries are a research shortlist, not promotions; their placement does not imply measured superiority in subjective research/design quality.

| Rank/status | Model | Recommended configuration | Best for — and why |
|---|---|---|---|
| 1, provisional pick | NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit | t1.0, native routing, predictor OFF | Text-only reasoning and rapid iteration: small token count, fast decode, no non-convergence in the matched Math500 run. |
| 2, provisional pick | Qwen3.6-27B-Opus-Distill-OptiQ-4bit | deployed t0.3, certified MTP | Research/design requiring vision or a repair-oriented alternative; slower reasoning in the recorded run. |
| Shortlist, not ranked | Ornith-1.0-35B-mlx-uniform-4bit | t0.4, native routing, certified MTP | Fast vision-capable exploration; reasoning runs retain a larger runaway tax. |
| Shortlist, not ranked | Qwen3.8-27B-mlx-uniform-4bit | t0.6, medium effort, certified MTP | Evaluate whether efficient medium-effort coding behavior transfers to C tasks; matched medium C evidence is still owed. |

### C evidence

Math500: same 100 cases, deployed tune, predictor OFF, budget 81920. **2026-09-09 scorer correction:** extracted LaTeX expressions are now parsed as math; earlier 89/88/86 strict scores were undercounts. Saved responses were regraded, not regenerated. Updated paired bootstrap intervals are below; do not reuse the old accuracy intervals. Timing/token measurements are unchanged.

| Model | Ordinary / strict correct | Non-converged | Mean output tokens/task | Generation time /100 | Best for — evidence and limits |
|---|---|---|---|---|---|
| NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit | **99 / 99** | **0** | **3,849** | **0.81 h** | Fast text reasoning: favorable quality point estimate and lowest measured token/time cost. |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | 99 / 97 | 2 | 12,842 | 16.4 h | Vision-capable alternative; some correct answers incurred non-convergence. |
| Ornith-1.0-35B-mlx-uniform-4bit | 99 / 93 | 6 | 15,788 | 4.7 h | Fast decoding, but more tokens and non-convergence on reasoning. |
| Qwen3.8-27B-mlx-uniform-4bit | Matched medium run not measured | — | — | — | C evaluation candidate; do not substitute its coding scores for research/design evidence. |

Corrected paired strict deltas: `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` versus `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`: **+2pp, 95% CI [-2,+6]**; versus `Ornith-1.0-35B-mlx-uniform-4bit`: **+6pp, CI [+1,+12]**. These are descriptive pairwise intervals before family multiplicity adjustment; n=100 nominal axis MDE is 12.5pp. The recommendation rests on favorable strict-quality and token/time trends, not a blanket superiority claim.

Math500 measures mathematical correctness, not brainstorming/design quality. BFCL has prior results (M18); subjective judge-panel work remains incomplete. C stays provisional. M34c's five-case Math500 pilot also regrades from 1/5 to **5/5 in both routing arms** after the parser correction. Its MBPPPlus pilot is native 4/5 vs expanded 5/5 at greater token/time cost: a candidate tradeoff, not a promotion. Expansion audits and resolution arms are tracked in PLAN.


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
