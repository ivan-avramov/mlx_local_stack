# THE PLAN — current and authoritative

**Last updated: 2026-08-16.** This file is the plan. It is deliberately SHORT and describes only what
is true now; when something completes, its row changes and the narrative goes elsewhere.

| file | role | rule |
|---|---|---|
| **`docs/PLAN.md`** (this) | the plan: goals, model field, ordered queue | keep CURRENT; never let it grow into a narrative |
| `docs/open-questions.md` | the operator's decision queue | nothing is ever deleted |
| `docs/campaign-results.md` | recommendations + the GENERATED scoresheet | scoresheet is generated, never hand-edited |
| `docs/campaign-queue.md` | HISTORY: per-session state, superseded plans | append-only narrative; `[RUNNING]` markers there are historical |
| `docs/lab-notebook.md` | HISTORY: every retraction, defect, mechanism | append-only |
| `docs/work-queue.json` | the EXECUTABLE form of §3 (commands) | regenerate from §3 when §3 changes — **currently stale (2026-08-14)** |

---

## 1. The two decisions this campaign exists to make

### B — coding across a repo-sized context (the 256K agentic-coding goal)

**Pick: `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`.** Runner-up `Ornith-1.0-35B-mlx-uniform-4bit` — take the
runner-up if turn latency matters more to you than task success rate.

**What it rests on, stated precisely:** one harness. aider polyglot n=110 matched, `final` **73.6% vs
50.0%**, McNemar **p=1.3e-05**. The mechanism is REPAIR, not raw generation: matched on the 65 items
*both* models failed at attempt 1, repair is **29.2% vs 56.9%, McNemar exact p=0.00053**. Attempt 1
alone is **inconclusive** (27/110 vs 36/110, p=0.12), so the entire pick is a repair result.

**Confidence: high on capability, single-instrument.** aider is retired as a harness (rows kept, no new
arms), so this evidence base is frozen until the opencode axis replaces it. The protocol-conflation
objection that retired aider does NOT undermine this particular comparison — both winners are fluent
under `diff` (0.036 and 0.009 malformed per case, and **0 malformed across all 22 go items each**), so
protocol fluency is not what separates them.

**On the "256K" part: NOT measured as a task.** Both clear the memory gate at 262K (32.4 / 43.3 GB
peak) and retrieval ladders pass, but no coding or reasoning quality has ever been measured at depth,
and the shipped config caps the designed maximum prompt near ~159,744 tokens anyway. B's context
requirement is currently satisfied *by assumption*.

### C — everyday driver for research, brainstorming, design

**No recommendation is supported by the evidence.** Provisional lean only:
`Ornith-1.0-35B-mlx-uniform-4bit` for interactive feel, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` for
reasoning-heavy sessions.

**C is blocked on INSTRUMENTATION, not worker time.** That is the single most important fact on this
page, and it is why no amount of running models promotes anyone to C:
- The only instrument that can measure C's construct — the blind mixed-family judge panel — is on
  record as **not reliable enough to rank** (order consistency 71/42/62%, Krippendorff α=0.517;
  score-based aggregation was tested and FALSIFIED, locating the instability in the judgement, not the
  readout).
- **BFCL has never been run at n** for any model, and the blocker is a template confound, not
  infrastructure: none of our registry names exist in bfcl's `MODEL_CONFIG_MAPPING`, so every stock run
  borrows a foreign handler. Needs the vendored handler posting raw `messages` + `tools`.
- IFEval, the one axis with a real verdict (`equivalent`), measures compliance with short mechanical
  constraints. It is a poor proxy for a research or design partner.
- **No deep-research axis exists at all.**

---

## 2. The model field

| model | role | state |
|---|---|---|
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` | **B pick** | measured: he+/mbpp+ n=100, aider n=110, ifeval n=148, math500 n=30, lcb n=15 |
| `Ornith-1.0-35B-mlx-uniform-4bit` | **B runner-up** | measured: he+/mbpp+ n=100, aider n=110, ifeval n=541, math500 n=30, lcb n=15 |
| `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` | candidate, **not a pick** | he+/mbpp+ n=100, ifeval n=200, opencode n=4. Ties on every capability axis measured while using **26.0 GB vs 32.4/43.3** and running ~2× faster. No reasoning row, no BFCL. |
| `Qwen3.8-27B` (three self-converted recipes) | **highest-upside untested candidate** | see §2.1 |
| `gemma-4-31B-it-qat-6bit` | effectively out | **cannot be compared at all**: runs `thinking_budget` 16384 vs the winners' 81920, and `compare` mechanically refuses cross-budget comparisons |
| `gemma-4-26B-A4B-it-OptiQ-4bit` | effectively out | he+ n=11 only; evalplus dropped by ruling (O18a) |

### 2.1 `Qwen3.8-27B` — three complete checkpoints exist and NOTHING has been run

Released 2026-08-14, scanned the same day. Self-converted from `unsloth/Qwen3.8-27B` on the M5 Max
worker, finishing 2026-08-15 03:20. **Verified complete 2026-08-16:**

| checkpoint | size | bpw | shards | notes |
|---|---|---|---|---|
| `uniform_4bit` | 14 GB | 4.0 (bits 4, group 64) | 3/3 ✓ | the reference baseline |
| `optiq_mixed` | 18 GB | **4.501** | 5/5 ✓ | + `optiq_vision.safetensors`, `sensitivity.json` |
| `static_mixed` | 13 GB | **3.966** | 3/3 ✓ | static recipe `mixed_3_6`; the one that hits the 4.0 target |

Why it is the highest-upside candidate: **same `qwen3_5` family as both winners** (so the fork is
expected to load it); a **hybrid** architecture (only 16 of 64 layers are full attention, the rest
Gated DeltaNet) giving **~64 KiB/token** of KV, so 262144 context needs ~17.2 GB of KV and clears the
46 GB gate with **no KV quantisation**; and vendor-claimed gains on exactly goal-B axes (QwenSWEBench
79.0 vs 49.3, DeepSWE 1.1 42.2 vs 13.3, SWE-bench Pro 61.7 vs 53.5 against the previous generation — the one
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` derives from). Vendor
claims are a HYPOTHESIS — this campaign's rule is that the suite is the arbiter.

**Blockers, all cheap:** not in `main_models.yaml`; no load smoke; all three recipes ship **MTP
sidecars** (15 tensors, ~300 MB, registered in `config.json`) and Qwen3.8 is MTP-NATIVE rather than
MTP-bolted-on, so whether the fork's `sanitize` renders them inert must be VERIFIED, not assumed.
Also outstanding: the two shortlisted DOWNLOAD arms (`mlx-community/Qwen3.8-27B-4bit`,
`lmstudio-community/Qwen3.8-27B-MLX-6bit`) were never fetched, and a fresh HF variant scan
(incl. UD variants) is in flight.

---

## 3. The ordered work queue

Cost estimates are measured where marked. One worker (M5 Max 64GB); the M4 Pro driver hosts NO models.

| # | work | what it buys | cost | blocked on |
|---|---|---|---|---|
| 1 | **aider `diff` go arm, `Ornith-1.0-35B-mlx-uniform-4bit`, suffix OFF, n=22, cap 65536** | whether suffix explains the edit-protocol contrast. Free ON comparator already on disk | ~40 min (measured) | **RUNNING** |
| 2 | **Paired suffix OFAT** — suffix-OFF arm of he+/mbpp+ n=100 for both winners | gates the lever at the ≤5% threshold AND produces the clean suffix-OFF rows. One job, two purposes | **5.4 h** (1.89 + 3.52, measured from the ON arms) | #1 finishing; cap back to 131072 |
| 3 | **`Qwen3.8-27B` load smoke + capacity ladder** on `static_mixed` and `optiq_mixed` | turns three stranded 45 GB artifacts into a measurable candidate; confirms the KV arithmetic and that MTP is inert | minutes + ~1 h | registry entries |
| 4 | **Run A** — 22 python opencode items × both winners | whether the B pick survives without aider | ~1.7 h | #2 (needs suffix-OFF baseline) |
| 5 | **ifeval suffix-OFF re-run**, both winners, n≥200 | makes the three-way `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` comparison admissible | ~5 h | #2 |
| 6 | **Run B** — 22 python opencode × `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` | third model on the agentic axis | ~0.7 h | #4 |
| 7 | **BFCL vendored handler** (driver work, no worker time) | fills an empty dimension; the cheapest powered axis the suite owns | driver-side | — |
| 8 | **Judge-panel reliability** | the ONLY route to a C answer | needs production changes + model time | — |
| 9 | Run C — 88 items (other 4 languages) × winners | per-language rankings | ~3.5 h/model | #4 |
| 10 | Re-open the `gemma-4-31B-it-qat-6bit` / `gemma-4-26B-A4B-it-OptiQ-4bit` agentic verdicts | undoes two protocol artifacts | ~2 h | #4 |

**Sequencing logic.** #2 comes first because until it lands, every winner-vs-other comparison in the
corpus is a (model × serving-path) composite and nothing new can be compared against the old rows.
#3 is inserted early because it is minutes of worker time against the largest potential upside in the
field. #4 before #9 because if opencode cannot discriminate the two winners on 22 matched python items,
four more languages produce five inconclusive rankings rather than an answer.

⚠️ **Known power problem with #4, recorded so it is not discovered afterwards:** at n=22 the paired MDE
is **±27pp** against an aider `final` gap of 23.6pp. Run A as scoped is underpowered for the question
it is meant to answer. Either accept it as a directional check, or scope it to the n the question needs
(`stats.n_for`: 157 items for 10pp at the default p_d).

---

## 4. Decisions waiting on the operator

Full text in `docs/open-questions.md`. Live items:

- **O27** — the PII scrub is not finished on the remote: the pre-scrub commit is still fetchable by sha,
  because unreachable objects survive a force-push until GitHub garbage-collects. Fix: a Support
  request asking them to `gc`, or delete/recreate the repo.
- **O26** — "degenerate wall-share" names two quantities differing by up to ~10× on the same rows.
  Rename one or persist both.
- **O25** — the suffix RETURN condition. The withdrawal is settled; what earns it back is not.
- **O24** — enforce the model-naming rule on changed lines via a pre-commit hook.

---

## 5. Standing constraints that shape every item above

- **ONE resident model per box, always.** Unload between models.
- **Suffix decoding is OFF for all five models** (2026-08-16). Verify at the WORKER COMMAND LINE — a
  suffix-OFF worker carries no `--draft-*` argument — never from the yaml alone.
- **Match the cap.** `max_kv_cache_size` is output-determining (it sets the resolved thinking budget via
  a silent `0.8 × (cap − prompt)` clamp). Before resuming ANY arm, check the cap its existing rows were
  generated at. The aider rows are at 65536; the he+/mbpp+ n=100 rows are at 131072.
- **Items buy power; samples buy reliability.** Never print a delta without its interval and the axis
  MDE. "Inconclusive" is a valid answer.
- **The MDE depends on the discordant-pair rate `p_d`, which must be MEASURED, not assumed.** The
  standing "628 items to resolve 5pp" figure uses `stats.mde`'s default `p_d = 0.20`, a *between-models*
  guess. Within-model paired levers are far lower — 157 items at p_d 0.05, 63 at 0.02.
- **Capability ranks; throughput is reported beside it.** Never rank on `successes_per_hour`.

---

## 6. How to maintain this file

When an item in §3 completes: change its row (or delete it) and move the narrative to
`docs/campaign-queue.md` or `docs/lab-notebook.md`. When a pick changes: rewrite §1 and say what moved
it. When a decision lands: strike it from §4 and record it in `docs/open-questions.md` with the date.
Regenerate `docs/work-queue.json` from §3 whenever §3 changes.

**Do not add narrative to this file.** The moment it starts recording what happened rather than what is
planned, it stops being usable as a plan — which is exactly how `docs/campaign-queue.md` grew to 1,187
lines with `[RUNNING]` markers from sessions that ended weeks ago.
