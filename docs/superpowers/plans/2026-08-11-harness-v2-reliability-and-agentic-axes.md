# Harness v2 — Statistical Power, Failure Taxonomy & Verdict-Relevant Axes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Revision 2 (2026-08-11)** — rev 1 was adversarially reviewed by three independent reviewers
(technical-soundness, measurement-validity, execution-realism). Their findings were spot-checked
against the code; most held. Rev 1's central premise was **wrong** and is reversed here. See
*Appendix A* for the full accept/reject ledger.

**Goal:** make `benchmark/` capable of settling the campaign's one open question and defending its
headline claim, with numbers that have enough power to mean something. Harness-side + two measurement
gates; every phase must produce a committed result row before the next is built.

## What rev 1 got wrong (the reversal)

Rev 1's answer to "n=1 is noise" was **more samples per item**. The variance decomposition says that
is close to worthless. For per-item pass/fail with between-item variance σ²_btw and within-item
E[p(1−p)]:

```
Var(pass@1) = σ²_btw/N  +  E[p(1−p)]/(N·k)
σ²_btw≈0.16, E[pq]≈0.08:
  N=15, k=1 → SD 12.7pp
  N=15, k=5 → SD 10.8pp     (−14% for 5× the model time)
  N=75, k=1 → SD  5.7pp     (−55% for the same 5× model time)
```

**Items, not samples, buy power.** Samples buy exactly one thing rev 1 was right to want —
run-to-run *reliability* — and k=2–3 is enough for that. Minimum detectable effect, paired binary
(α=.05, power .80, discordance p_d≈0.20, n = 7.849·p_d/δ²):

| items N | 15 | 40 | 100 | 164 | 378 |
|---|---|---|---|---|---|
| **MDE (±pp)** | **32** | **20** | **12.5** | **9.8** | **6.4** |
| items needed for δ= | 20pp → 40 | 15pp → 70 | 10pp → 157 | 5pp → 628 | |

So the campaign's live deltas — LCB 86.7 vs 80 (6.7pp), aider 75 vs 61.8 (13pp) — need **N≈100–470
matched items**, not k=5 on N=15. Rev 1 would have spent ~40h of distill time to shrink an interval
by 14%. Rev 2's primary purchase is **items**, plus graded outcomes (test-case pass *fraction*
instead of binary), which cut required N by 2–4× for free.

**Corollary, and it must be stated up front: "indistinguishable" is a valid, likely answer.** If
Ornith and the distill tie on quality within a properly-powered interval, the 4× decode and 5× memory
margins decide and the current pick stands. The harness exists to make that conclusion *defensible*,
not to manufacture a winner.

## Global constraints

- **TDD, strictly.** Failing test → watch it fail for the right reason → minimal implementation.
- **Every phase's DoD is a committed row in `docs/campaign-results.md`**, produced by that phase's
  code, on a real box, provenance-stamped. This repo has four axes *built and never run*
  (`swebench_adapter.py`, `judge.py`, GPQA, IFEval — `campaign-queue.md` backlog 2–5). No new module
  starts until the previous one has produced a row.
- **No new hard dependency** in generate/grade; heavy imports lazy + graceful-degrade to
  `{"acc": null, "note": ...}`.
- **Injectable seams**: `driver`, `runner=subprocess.run`, `clock`, `client` adapters.
- **Backward compatibility is hard.** Existing v1 rows must grade identically; `results_root()` must
  keep `monkeypatch.setattr(G, "RESULTS", tmp_path)` working (**8 existing tests rely on it**).
- **No PII.** Caches machine-local (`~/.cache/mlx_bench/…`), pins committed, artifacts not.
- **Thinking ON everywhere**, and any axis whose generation cap leaves < ~8K tokens after
  `thinking_budget` is invalid by construction (the gemma-MoE whole-format contamination).
- **Budgets are never lowered to force convergence.** Unchanged.
- **APC is provenance, never an axis** (decided 2026-08-11: APC is a serving-layer cache, not a model
  capability, so it is **not benchmarked**). But it must be *recorded*: `runserver.sh:74` sets
  `APC_ENABLED=1` while `AGENTS.md`'s benchmarking router recipe omits it, so benchmark runs have
  silently differed from the daily driver on a knob that changes TTFT by 34–147×. Every result records
  APC state and it enters the provenance fingerprint — purely so speed rows are comparable.

## Decisions (revised)

- **D1 (revised 2026-08-11 by operator decision) — three candidates, none excluded.**
  `Ornith-1.0-35B-mlx-uniform-4bit`, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, and
  `gemma-4-31B-it-qat-6bit`. **256K is a goal, not a mandate** — a model that tops out lower is
  characterised at what it *can* do rather than dropped. Both reviewers argued for cutting gemma
  (capped at 192K by `main_models.yaml:55` — weights ~31GB make 256K trip the RAM backstop; ~56
  min/aider-case ≈ 9× Ornith). Rejected: exclusion would answer "which model wins at 256K" while
  leaving "what can the dense convergence/reasoning leader actually do" unanswered, and gemma is the
  current leader on AIME (100% @ 100% conv) and LCB-dense (86.7%). Handling its two real problems:
  - **Context ceiling → per-candidate rungs, common-rung comparison.** Each candidate's ladder runs to
    *its* registry ceiling (gemma 0/64K/128K/192K; the qwen-arch pair adds 256K). Cross-model deltas
    are computed **only at the common rungs (≤192K)**; the 256K rung is reported for the two that
    reach it, and gemma's row reads `ceiling 192K (config-limited)` — never a blank or a zero.
  - **Cost → sequencing, not exclusion.** gemma enters each axis *after* the two winners, on whichever
    box is free, so it never blocks the M1 verdict question. Wall-clock is stated per axis so the
    operator can defer a specific gemma arm without re-deciding the whole plan.
  - **Edit-format confound → measured first, not assumed.** gemma's SEARCH/REPLACE diffs don't apply
    (documented 2h stuck run) so it has been run at `edit_format: whole`, while the qwen-arch pair runs
    `diff`. That makes any agentic H2H across the two families **format-confounded**. The edit-format
    preflight therefore moves *before* M1 (Task 2.4) and its result decides gemma's format; the
    confound is stated on every cross-family agentic row.
- **D2 (revised) — the convergence VECTOR is primary; strict is a derived deployment number.** Rev 1
  proposed `pass@1_strict` (truncated = failed) as the headline. Rejected: strict is weakly monotone
  increasing in `thinking_budget`, and the campaign holds rows at 16384 / 32768 / 81920 — a 5×
  budget spread would masquerade as capability, making the budget a de-facto knob on the headline,
  which AGENTS.md explicitly forbids. It also fuses two mechanisms with different fixes (wrong answer
  = capability; external truncation = config × verbosity) and collapses the temperature-ladder's
  lexicographic rule into one scalar. **New scheme:** report the triple
  `(pass@1 | converged, conv%, nonconv_kinds)` with a pre-registered decision rule — `conv% ≥ 0.90`
  is a **gate**, `pass@1 | converged` **ranks within** it. `acc_strict@<budget>` is reported as a
  derived, budget-annotated deployment number and is never the ranking key. Because
  `pass@1 | converged` conditions on a model-dependent subset, cross-model comparison is **paired on
  the intersection of items both models converged on**. Run-level INVALID is retired; the FAIL-signal
  obligation survives via `conv%` + `nonconv_kind`. ⚠️ Still an AGENTS.md amendment (P1/Task 1.7).
- **D3 (revised) — no greenfield todo-CLI.** A stdlib argparse/JSON CLI is the most over-represented
  pattern in pretraining; all candidates sit at 90–100% on he+/mbpp+ which "separate nothing", the
  SPEC would be <5K input (the same short-context defect the plan exists to fix), and its 8–10
  features are one codebase, one session, one bad design decision → effective N≈1. Spec-to-feature
  becomes a **conditional, brownfield** phase (P6), gated on a cheap saturation probe.
- **D4 (revised) — the primary long-context design is distractor-padding OFAT**, not a haystack
  ladder: take the *same* LCB/agentic items and prepend 0 / 64K / 192K of plausible irrelevant code.
  This isolates length from difficulty, reuses existing graded items, needs no new dataset, and is
  paired by construction. Haystack `trace`/`locate`/`edit_at_depth` become the secondary arm and
  **require a no-context control** (a pinned public repo is in every candidate's training data, so
  "which file handles X" is answerable from memory — without the control the axis measures recall,
  not long-context reading).
- **D5 — router-side invalid-tool logging stays out of scope** (`../mlx-vlm` fork change).
- **D6 (new) — BFCL is kept, not replaced.** At n=1000, 0.94 vs 0.749 is SE≈1.6pp ≈ 12σ: the only
  adequately-powered axis the campaign owns. Rev 1 proposed replacing it with 5 scenarios × k=3 (±25pp
  per rate) — a decisive result traded for a diagnostic. BFCL gets **repaired** (thinking ON, cap
  raised); the new tool probe is explicitly labelled diagnostic and **excluded from ranking tables**.

## What this plan does NOT change

Two-phase generate/grade, chunked resumability, `--order roundrobin`, provenance stamping (extended),
official-evaluator grading, the temperature-ladder recipe, `mx.get_peak_memory` as the capacity
metric, existing bench prompts (changing one invalidates every prior row).

---

# Phase 0 — Bootstrap, seams, and the config drift that would poison every new axis

**Wall-clock: ~1 day. Box: M2. DoD: `pytest` green in `.venv-bench` + a params-audit row in
`campaign-results.md`.**

Rev 1 assumed the test/venv infrastructure existed. It does not: **`.venv-bench` is absent on this
box** (only `.venv`), so rev 1's whole-plan DoD command could never have run. And
`model_params.py` has drifted from the deployed config, which would have silently mis-measured every
new axis in every later phase.

**Files:** add `bench/tests/conftest.py`; modify `bench/generate.py`, `bench/grade.py`,
`bench/model_params.py`, `AGENTS.md`.

### Task 0.1 — Environment bootstrap (no code)

- [x] `.venv-bench` per AGENTS.md (mlx + pytest + json_repair, **no** `mlx_audio`); confirm
      `bench/tests` collects — expect **32** test files (not 33).
- [x] `.venv-lcbgrade` (`uv venv --python 3.11`, `datasets<3`) per the resolved recipe in
      `campaign-queue.md`; verify the LCB dataset loads (880 problems).
- [x] Restore `${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh` — created with
      `STACK_REPO` filled; **the M5 fields still hold the example placeholders and need the
      operator's values** before anything can reach the remote box. from
      `config.example.sh` (absent → `$REMOTE_HOST` unresolvable → M5 unreachable by the documented path).
- [~] **Snapshot M5's `benchmark/results/` off-box before any provenance change.** BLOCKED on
      M5 host details (config.sh placeholders). Risk retired in code instead: fingerprint v2 is
      versioned so v1 manifests compare on the v1 slice, and an unobserved runtime value is a
      wildcard — no existing result can be condemned by the extension. Snapshot still advised
      before the first `--clean-stale` on M5. Results are
      gitignored and unversioned; a `--clean-stale` fingerprint mistake is irrecoverable and would
      destroy months of generation.

### Task 0.2 — `results_root()` with a module fallback (not env-only)

Rev 1 specified an env-based root and claimed nothing breaks. Wrong: **8 tests**
(`test_generate_run.py:26,37,48,65,80`, `test_grade_evalplus.py:20,61,68`) do
`monkeypatch.setattr(G, "RESULTS", tmp_path)`. An env-only root makes those monkeypatches inert — two
`provenance_precheck` tests fail, one passes **vacuously** on `acts == []`, and two write into the
real results tree.

- [x] **Step 1 (test):** `test_results_root.py` — precedence is `$MLX_BENCH_RESULTS` → **module
      `RESULTS`** → default; `monkeypatch.setattr(G, "RESULTS", tmp)` still redirects `result_path()`
      (assert explicitly — this is the compat contract); `result_path("a/b", "aime")` still escapes to
      `a__b`.
- [x] **Step 2:** Implement with that precedence. Route `grade_all`'s hardcoded
      `Path("benchmark/results")` (`grade.py:328-329`) through it, and the 12 sibling constants in
      `run_*.py` / `diag_agg_reasoning.py` (which resolve **file**-relative while `generate.RESULTS`
      is **CWD**-relative — Phase 7's `report` needs one root).
- [x] **Step 3:** Full suite green, all 8 monkeypatch tests included.

### Task 0.3 — Fix `model_params.py` drift (prerequisite for every later phase)

`model_params.QWEN` = temp 0.7 / min_p 0.03 / presence_penalty 0.3 / max_tokens 81920 / budget 49152.
**None** of that matches the audited deployed config (AGENTS.md: Ornith t0.4, distill t0.3, min_p 0.0,
`presence_penalty 0.0` — required for suffix decoding to engage — max_tokens 102400, budget 81920).
`PARAMS` is family-uniform so per-model op-temps are unrepresentable, and
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` **is not registered at all** (it falls through to name-matching).

- [x] **Step 1 (test):** `test_model_params.py` extension — `params_for(<Ornith>, "deployed")` returns
      exactly the shipped `generation_defaults` from `main_models.yaml` (temp 0.4, presence_penalty
      0.0, …); same for the distill (temp 0.3); an unregistered model raises rather than silently
      falling back; `presence_penalty` is 0.0 on every deployed profile (a nonzero one disables suffix
      decoding, i.e. measures a different serving config than production).
- [x] **Step 2:** Add a `deployed` profile sourced **from `main_models.yaml` `generation_defaults`**
      (single source of truth, per FU-2) with per-model overrides. Keep `production`/`official`/
      `coding` untouched so historical rows stay reproducible.
- [x] **Step 3:** Record a params-audit row in `campaign-results.md`: for each candidate, deployed vs
      what each historical profile actually sent. This tells us which existing rows were measured at
      the deployed config and which were not — a prerequisite for trusting any of them.

### Task 0.4 — APC as recorded provenance (NOT an axis) + fingerprint honesty

APC is a serving-layer cache, not a model capability, so **it is never benchmarked** (operator
decision, 2026-08-11). This task only makes its state visible so runs are comparable.

- [x] **Step 1:** Amend AGENTS.md's router recipe to state APC explicitly, both forms
      (`APC_ENABLED=1` for daily-driver-faithful runs; unset for cold-prefill speed baselines), and
      note that `runserver.sh:74` sets it — so past benchmark runs launched from the AGENTS.md recipe
      had APC **off** while the daily driver had it **on**. This is an apples-to-apples fix for
      *existing speed rows*, not a new measurement.
- [x] **Step 2 (test):** `test_provenance_fingerprint.py` — the fingerprint includes every
      **behaviour-changing** knob: `apc_enabled`, `draft_kind`, `max_turns`, `deadline_s`, loop-guard
      thresholds, `client`, `edit_format`; and **excludes** `samples` (which does not change the
      output distribution — including it would mark every existing result stale). Guard-test both
      directions.
- [x] **Step 3:** Implement. Note the whitelist at `provenance.py:39` already structurally prevents
      `samples` leaking in; the guard test locks that in.

### Task 0.5 — Shared test fakes

- [x] **Step 1 (test):** `test_conftest_fakes.py` — fakes behave as advertised.
- [x] **Step 2:** Implement `conftest.py`. **Two distinct seams, not one** (rev 1 conflated them):
      `FakeProbe` matching `client.probe`'s dict shape *completely* — `generate.py:221-224` indexes
      `prompt_tokens`/`decode_tps`/`peak_mem_gb`/`wall_s` inside a bare `except` (`:229-230`), so an
      under-specified fake silently produces **error rows** and the samples/resume tests would go
      green on zero coverage; and `FakeDriver` matching `driver.Driver.complete` (which has no
      `probe`). Plus `FakeRunner`, `frozen_clock`.
- [x] **Step 3:** Commit: `test(bench): bootstrap, results-root seam, deployed sampling profile`.

---

# Phase 1 — Statistical core: items-first power, honest intervals, per-sample plumbing

**Wall-clock: ~2–3 days. Box: M2. DoD: one bench re-graded end-to-end with the new metric vector,
committed as a row.**

**Files:** add `bench/stats.py`, `bench/rowschema.py`; modify `bench/generate.py`, `bench/grade.py`,
`bench/convergence.py`, `run.py`, `AGENTS.md`.

### Task 1.1 — `stats.py` — cluster bootstrap, not pooled Wilson

Rev 1 specified Wilson intervals over pooled item-mean successes. That **understates variance by
ignoring item-level clustering**: with k=5, ρ≈0.7, the design effect 1+(k−1)ρ ≈ 3.8 makes the true SE
~1.95× larger. Pooling 75 trials at p̂=.8 reports ±9.1pp; the honest item-level interval,
Wilson(12,15), is **(0.548, 0.930) — 38pp wide**. Rev 1 would have shipped intervals ~2× too tight
while advertising that it fixed false precision.

- [ ] **Step 1 (test):** `test_stats.py`, hand-computed:
      - `wilson(8,10)` ≈ `(0.490, 0.943)`; `wilson(0,5)` lower is **clamped** to 0.0 and
        `wilson(5,5)` upper **clamped** to 1.0 (the closed form floats to ±1e-17 without a clamp);
        `wilson(0,0)` → `(None, None)`, not ZeroDivisionError.
      - `cluster_bootstrap(per_item, iters, seed)` — **two-stage**: resample items with replacement,
        then resample the k draws within each selected item; percentile CI. Tests: k=1 reduces to a
        plain item bootstrap and brackets Wilson within ~2pp; identical items give a degenerate
        zero-width CI; seeded → deterministic; unequal sample counts per item (normal after an
        interrupted resume) are handled, not crashed.
      - `reliability(per_item)` returns the **full histogram of c_i** (a sufficient statistic that
        loses nothing) plus **U-statistic estimators** `Σ_i C(c_i,j)/C(k,j)` for j=2,3 — far
        lower-variance than rev 1's all-k indicator, which uses only the extreme order statistic, is
        **non-comparable across k** (p=.9 reads .729 at k=3, .59 at k=5), and at N=15 carries ±25pp.
        `pass_hat_k` is kept as a derived, **k-annotated** display value only.
      - `paired_delta(a_per_item, b_per_item)` — two-stage paired bootstrap; **refuses** on
        non-identical item-id sets; returns `{delta, ci95, verdict}` with **TOST**: `equivalent` iff
        CI ⊂ (−δ_margin, +δ_margin) with δ_margin=5pp, `a_better`/`b_better` iff CI excludes 0,
        else **`inconclusive`** (rev 1's `indistinguishable` reported non-significance as
        equivalence — a different and much stronger claim).
      - `holm(pvalues)` — family-wise correction. 3 models × ~6 axes ≈ 30 tests at α=.05 gives
        P(≥1 false "a_better") = 1−.95³⁰ = **79%**. Without this the harness manufactures winners.
      - `mde(n, p_d=0.20, alpha=.05, power=.80)` and its inverse `n_for(delta)` — so every axis can
        print its own resolution and no one re-litigates sample size. Assert the table above.
      - `time_to_success(t_success, t_fail, p)` = `E[T_s] + ((1−p)/p)·E[T_f]`. Rev 1's
        `median_wall/pass_rate` is **wrong**: the Wald expectation uses the **mean**, not the median,
        and these runs have brutal right tails (14.5 min median vs 2h loop cases) — so median/p
        systematically *flatters* the loop-prone models the metric exists to punish. Test the
        degenerate cases: `p=0` → `inf`; report `successes_per_hour` (bounded) as the primary display
        form because a ratio-to-a-rate has no usable bootstrap (at n=5, p=.2 a replicate has 0
        successes 33% of the time → CI upper = inf).
- [ ] **Step 2:** Implement, stdlib only (no numpy — `stats` must import in every venv).
- [ ] **Step 3:** Each docstring states what the metric answers, its failure mode, and its minimum n.

### Task 1.2 — `--samples k` end-to-end, including the grader that silently drops k−1 of them

**`grade_evalplus` collapses k rows to one.** `grade.py:102` builds `our = {r["id"]: extract_code(...)}`
— keyed by id, so the *last* sample wins; `:115-117` writes one solution per `task_id`; `:138` reads
`res[0]`. Rev 1 shipped `--samples` without touching this: humanevalplus/mbppplus would have graded
**1/k of the data while reporting CIs and reliability over k**. That is a wrong-number bug, not a gap.

- [ ] **Step 1 (test):** `test_samples_resume.py` — `build_queue(..., samples=3)` emits 3 entries per
      item with distinct `sample`; roundrobin interleaves **items before samples** (a stopped prefix
      stays balanced across items); `done_keys()` on a jsonl mixing v1 (no `sample`) and v2 rows
      satisfies `sample=0` from the v1 row and queues only 1 and 2; errored rows retry per key.
- [ ] **Step 2 (test):** `test_grade_evalplus_samples.py` — k rows per task produce **k** lines in the
      samples jsonl and pass@1 is read per `(task_id, sample)` from `eval[tid][i]`; the item's score
      is its **pass fraction across samples**, not the last sample. Same for `grade_lcb`
      (`_lcb_eval_inputs` currently emits `[code]`, one generation per problem — must become k).
- [ ] **Step 3 (test):** every grader returns `items: [{id, sample, ok}]`. Rev 1 promised "one shared
      post-processor" for strict/raw/reliability, but only `grade_reasoning` exposes per-item results
      (`grade.py:72`); `grade_evalplus` (`:145`), `grade_lcb` (`:220`) and `grade_ifeval` (`:299`)
      return aggregates only, so the post-processor was unimplementable as specified. Per-item output
      is the prerequisite, and it comes first.
- [ ] **Step 4:** Implement; `done_keys()` alongside `done_ids()` (other callers exist).
      `run.py --samples N` (default 1), printed in the params banner. **Record the sampler seed per
      row** — without it the k draws aren't reproducible and a resume can't be told from a re-draw.
- [ ] **Step 5 (test):** `test_provenance_samples.py` — an existing single-sample results file stays
      **compatible** and resumes rather than being flagged stale.

### Task 1.3 — Graded outcomes (the cheapest power win in the plan)

Binary pass/fail throws away most of the information in an execution-gated test suite. Test-case pass
*fraction* cuts required N by 2–4× at zero model cost.

- [ ] **Step 1 (test):** per-item `score ∈ [0,1]` from the evaluators' per-test results (evalplus
      `base_status`/`plus_status` per test where available; LCB per-test-case detail), with binary
      `ok` retained for backward compatibility and for the headline.
- [ ] **Step 2:** Implement; `cluster_bootstrap` accepts continuous per-item scores unchanged.
- [ ] **Step 3:** Report both. Continuous is the *powered* comparison; binary stays the reported
      pass@1 for comparability with published numbers.

### Task 1.4 — Trace capture + non-convergence classification

`generate.py:220` stores `strip_thinking(content)` and drops `reasoning`, which is why typing the 8bit
DNF needed a bespoke live probe. Own note in `campaign-results.md`: "capture thinking for future DNF
triage" — still unfixed.

- [ ] **Step 1 (test):** `test_trace_capture.py` — rows carry `reasoning_chars`, `reasoning_head`
      (4096), `reasoning_tail` (4096), `reasoning_stats` = `{lines, unique_line_ratio,
      max_line_repeat, ngram8_unique, ngram20_unique}`; a short trace yields head==tail==whole with no
      truncation marker; total trace storage capped ~8KB/row (an 82K-token meander must not bloat the
      jsonl 40×).
- [ ] **Step 2 (test):** `classify_nonconvergence(row)` → `None` | `max_tokens` | `budget_hit` |
      `degenerate_repetition` | `meander`, with **precedence defined and tested** for the ambiguous
      case (`finish=="length"` **and** `looks_like_loop` → `degenerate_repetition`, because the
      mechanism, not the stop reason, is what we act on). Fixtures transcribed from the two documented
      real cases (gemma repetition: max-repeat 34–78 / ~44% unique; Qwen meander: max-repeat ≤23 /
      ≥84% unique) so thresholds stay calibrated to campaign data.
- [ ] **Step 3:** Implement and wire into the generation row.

### Task 1.5 — Recovery: annotate, don't silently substitute *or* silently score

`probe_with_recovery` (`generate.py:54`) re-probes after a router restart **only for non-converged
items** and returns the second probe as the datum — a second draw granted selectively to failures,
inflating `conv%` for exactly the loop-prone models under investigation. Rev 1's fix (score the
first probe) traded that for a different error: it grades a **known stale-router artifact** as the
model's answer.

- [ ] **Step 1 (test):** `test_recovery_annotation.py` — on a restart-retry the row keeps the
      **first** probe as the convergence datum, nests the second under `recovery_probe`, and sets
      `contaminated: "stale_router"`. Contaminated items are **excluded from pass@1** with a reported
      count, never scored from a known-bad state. `convergence.audit` counts primaries only, so the
      recovery path cannot move `conv%`.
- [ ] **Step 2:** Implement; update `test_loop_recovery.py`.

### Task 1.6 — The metric vector (D2 revised)

- [ ] **Step 1 (test):** `test_grade_vector.py` — for rows {A correct+converged, B correct+budget-hit,
      C wrong+converged}: `conv_rate == 2/3`; `pass_at_1_converged == 1/2` (A,C only);
      `acc_strict == 1/3` reported as `acc_strict@16384`; `nonconv_kinds == {"budget_hit": 1}`;
      **`acc` is unchanged in meaning** and equals the historical raw definition (silently redefining
      `acc` would retroactively change ~40 published rows). `valid` means harness-clean (error rate
      under threshold), not converged.
- [ ] **Step 2 (test):** cross-model comparison of `pass_at_1_converged` **refuses** unless paired on
      the intersection of items both models converged on, and reports that intersection's size —
      conditioning on convergence conditions on a model-dependent, easier subset.
- [ ] **Step 3 (test):** `test_grade_v1_compat.py` — a v1 fixture jsonl in `bench/tests/fixtures/`
      grades to the **same `acc` and `conv_rate`** as before, with the new fields added.
- [ ] **Step 4:** Implement. `convergence.audit`'s field is renamed `all_converged` (leaving `valid`
      to `grade.py`); update `test_convergence.py:44,85` and `run.py:119-134`'s INVALID printing,
      which both assert the old semantics — rev 1 listed neither.

### Task 1.7 — `compare` + the AGENTS.md amendment

- [ ] **Step 1 (test):** `test_compare_cmd.py` — comparability is **same item-id set + same profile
      name + same budget/max_tokens + same box (for speed/memory) + same APC state**, and
      **explicitly tolerates different per-model op-temps** (Ornith t0.4 vs distill t0.3 are the
      *intended* configs; rev 1's fingerprint-equality rule would have refused every comparison the
      campaign needs, since `temperature` is in `_FINGERPRINT_SAMPLING`). Verdicts come from
      `paired_delta` + `holm`. A 6.7pp delta at n=15 returns **`inconclusive`** with the MDE printed.
- [ ] **Step 2:** Implement `run.py compare`. Never print a delta without its CI and the axis MDE.
- [ ] **Step 3:** Amend AGENTS.md — the D2 vector and its pre-registered decision rule; items-first
      power with the MDE table; cluster bootstrap; TOST/`inconclusive`; Holm across the family; the
      APC recording rule; ETTS as `E[T_s] + ((1−p)/p)E[T_f]` / successes-per-hour. Also **backfill**:
      relabel the ~40 historical INVALID rows under the new vector where their jsonls survive, or mark
      them `legacy-INVALID (pre-v2 rule)` where they don't. ⚠️ Standing-rule change — flag in the
      commit message.
- [ ] **Step 4:** Commit: `feat(bench): items-first power, cluster bootstrap, convergence vector`.

---

# Phase 2 — Agentic instrumentation

**Wall-clock: ~1–2 days. Box: M2. DoD: the M1 gate below (this phase's code produces the rows).**

**Files:** add `bench/agent_outcomes.py`; modify `bench/agent_loop.py`, `bench/aider_adapter.py`,
`bench/swebench_adapter.py`.

### Task 2.1 — Counters + loop guard (pure)

- [ ] **Step 1 (test):** `test_agent_outcomes.py` — `Counters.observe()` increments
      `unknown_tool_calls` (name absent from the schema), `arg_schema_violations` (missing required
      arg / wrong type), and tracks `max_identical_repeat` over `(name, canonical_json(args))`;
      `LoopGuard(max_identical=3, max_unknown=5).should_abort()` is False at 2 identical, True at 3,
      True at 5 unknown, reason `tool_error_loop`; `recovered_after_error` / `turns_to_recovery`
      capture a valid call following an invalid one — the corrective-feedback-recovery metric.
- [ ] **Step 2:** Implement as a pure dataclass + guard.

### Task 2.2 — Wire into `agent_loop.run_agent`

`agent_loop.py:63` feeds back `ERROR: unknown tool {name!r}` and counts nothing; `max_turns=12` with
no outcome label; no deadline; no repeat detection. A model that called a nonexistent tool 400 times
while being handed the correct list would appear as `turns=12, submitted=None`.

- [ ] **Step 1 (test):** `test_agent_loop_taxonomy.py`, all via `FakeDriver`:
      - infinite identical invalid call → aborts at 3 repeats, `outcome == "tool_error_loop"`,
        `turns == 3`;
      - one unknown tool then the right one → `recovered_after_error is True`,
        `turns_to_recovery == 1`;
      - `deadline_s=10` with `frozen_clock` at 6s/turn → aborts turn 2, `outcome == "deadline"`,
        partial transcript retained;
      - `max_turns` exhausted → `turn_cap`, distinct from `no_submit` (model ended with prose);
      - driver raising a transport error → `server_error`, never an uncaught exception.
- [ ] **Step 2:** Implement. `max_turns` 12 → 30 (the loop guard, not the turn cap, is now the runaway
      protection). **These are fingerprint-affecting** (Task 0.4) — post-change agentic numbers are
      not comparable to the Ornith n=34 / distill n=16 baselines, so M1 re-baselines both arms in one
      session.
- [ ] **Step 3 (test):** `swebench_adapter.solve_instance` currently returns a **`str`** (`:107`) and
      the injectable `agent_fn` contract (`:120`) + caller (`:139 patch = agent_fn(...)`) +
      `test_swebench.py:59,84,91` all assume that. Return `(patch, outcome, counters)` via a **new**
      function, keeping `solve_instance`'s signature intact — rev 1 called this "a test extension"; it
      is a contract change.

### Task 2.3 — Parse what aider already reports

- [ ] **Step 1 (test):** `test_aider_full_parse.py` — parse aider's **`.aider.results.json`** under
      `AIDER_BENCHMARK_DIR` (`aider_adapter.py:48-53`), **not** stdout: no aider stdout artifact
      exists in this repo, so a transcribed fixture would have guessed field names and a wrong guess
      returns all-`None` while the test still passes. Fields: pass rates, `percent_cases_well_formed`,
      `num_malformed_responses`, `lazy_comments`, `syntax_errors`, `indentation_errors`,
      `test_timeouts`, `exhausted_context_windows`, per-case durations, `num_error_outputs`. Missing
      keys → `None`, never a crash. Keep the stdout parser as a fallback.
- [ ] **Step 2:** Implement (`parse_aider_report`, thin alias for `parse_pass_rate`). Annotate
      `exhausted_context_windows` as aider's **mislabel for output-token-limit hits** so it is never
      re-read as an input-context problem.
- [ ] **Step 3 (test):** `test_time_to_success.py` — per-case durations + success flags →
      `E[T_s] + ((1−p)/p)E[T_f]` and `successes_per_hour`. **No hard-coded Ornith-vs-distill
      expectation**: rev 1's test pinned 384s@61.8%(n=34) vs 870s@75%(n=16) as an expected value,
      cementing a cross-session, cross-N, unmatched-item comparison — an apples-to-apples violation —
      into the test suite. Use synthetic fixtures.
### Task 2.4 — Edit-format preflight (moved earlier: it gates gemma's M1 arm)

Cheap, and it must run **before** M1 because it decides gemma's `edit_format` and therefore whether the
cross-family agentic comparison is format-confounded.

- [ ] **Step 1 (test):** `test_editformat_preflight.py` — `check_edit_format(driver, model)` asks for
      one SEARCH/REPLACE block against a fixture file, applies it with a minimal parser, returns
      `{"diff": bool, "whole": bool}`; a non-applying block reports `diff: False` **with the raw block
      captured** for diagnosis.
- [ ] **Step 2:** Implement. Run it on all three candidates (~5 min each). Record per-model
      `edit_format` in the registry-facing notes; the 2h gemma stuck run is exactly what this prevents.
- [ ] **Step 3:** Commit: `feat(bench): agentic failure taxonomy, loop guard, deadlines, time-to-success, edit-format preflight`.

---

# ▶ MEASUREMENT GATE M1 — the matched agentic H2H

**Wall-clock: ~18h (Ornith, M5) + ~41h (distill, M2) for the verdict pair, overnight × 2; gemma's arm
~32h after, on whichever box frees first. DoD: a committed `campaign-results.md` row (the verdict pair
gates the next phase; gemma's arm can land later).**

This is the campaign's **one open verdict question**: the pick rests on Ornith 61.8% pr2 (n=34) vs the
distill's 75% (n=16) — a 13pp gap *favouring the alternative*, dismissed on unmatched-n
(`campaign-results.md:371-378`).

- [ ] **Step 1:** Same **34** exercises for every arm, same session per box, deployed profile
      (Task 0.3), APC state recorded, k=3 for reliability. `edit_format: diff` for the qwen-arch pair;
      gemma's format comes from the Task 2.4 preflight. If gemma runs `whole` while the pair runs
      `diff`, the cross-family delta is **format-confounded** and must be labelled so on the row —
      gemma-vs-gemma across other axes stays clean, and the Ornith-vs-distill verdict question is
      unaffected (both `diff`).
- [ ] **Step 2:** Report the vector: `pass@1` (binary + graded), cluster-bootstrap CI, reliability
      histogram, `conv%`, outcome histogram, `successes_per_hour`, and the **matched paired delta with
      its MDE**.
- [ ] **Step 3:** Interpret honestly. At n=34 the resolution is **±16pp**, so 13pp will very likely
      come back `inconclusive`. **That is a result**: quality ties within resolution → the 4× decode
      and 5× memory margins decide → the Ornith pick stands, now defensibly. Closing 13pp to
      significance would need ~110 matched exercises ≈ 133 days on the distill — **out of budget, and
      the plan says so rather than pretending otherwise.**
- [ ] **Step 4:** If the distill *does* separate upward beyond the CI, the pick is genuinely in play
      and P4 (long-context) becomes the tiebreak.

---

# Phase 3 — Tool use: repair the powered axis, add a labelled diagnostic

**Wall-clock: ~1 day build + ~6h BFCL/model. Box: M5. DoD: BFCL thinking-ON rows + a toolprobe
diagnostic row.**

- [ ] **Task 3.1 — Repair BFCL (the powered axis).** Existing rows are **no-think** (3/400 traces
      carried `<think>`), violating AGENTS.md, and BFCL hard-caps generation at 4096 which cannot fit
      a thinking model's trace + answer. Re-run n=1000 native-FC with thinking ON and the cap raised;
      add a preflight assertion that `max_tokens − thinking_budget` leaves real answer headroom.
      **Report as a temp-OFAT pair** against the existing no-think rows so the delta is attributable.
      This is the only comparison in the campaign with ~12σ of separation; it deserves to be correct.
- [ ] **Task 3.2 — `toolprobe.py`, five scenarios, explicitly diagnostic.** baseline / lure (invents a
      nonexistent tool?) / recovery (pre-seeded invalid call + canonical error → valid call within 2
      turns) / bad-args repair / **abstention** (tool returns "no results" — does it report absence or
      fabricate?). Pure `check_fn` per scenario, tested against correct / wrong-tool / bad-args /
      prose-only responses; `run_probe` with `FakeDriver` aggregates five rates.
      **At 5 scenarios × k=3 each rate carries ±25pp — the module must print that, label itself
      `diagnostic`, and be excluded from ranking tables.** Scenarios 1 and 4 will likely ceiling; 2
      and 5 are near-binary at n=3. Its value is *mechanism identification* (does this model ignore
      corrective feedback?), never ranking.
- [ ] Commit: `feat(bench): thinking-on BFCL repair + tool-use diagnostic probe`.

---

# Phase 4 — Long context: distractor-padding OFAT (the verdict-relevant design)

**Wall-clock: ~2 days build + ~1–2 days/model. Box: M5 only (M2 ≤192K). DoD: a committed
length-vs-quality curve per candidate.**

The 256K claim currently rests on needle retrieval at n≈5. **That does not clear the campaign's own
0.85 gate:** to certify p ≥ 0.85 you need the interval's *lower* bound ≥ 0.85, i.e. at p̂=1.0,
`n/(n+3.8416) ≥ 0.85` → **n ≥ 22 perfect items per rung**. At n=5 a perfect score supports only
**p ≥ 0.57**. The existing "retrieval 1.00 @256K" is not evidence for the gate it is cited for.

### Task 4.1 — Distractor-padding OFAT (primary, D4)

- [ ] **Step 1 (test):** `pad_item(item, filler_tokens, tokenizer)` prepends plausible **irrelevant**
      code to an existing LCB/agentic item without altering the task; identical padding for both
      models at a rung; **per-model tokenizer** for the budget (a fixed `chars_per_token` gives three
      tokenizers different true lengths at the same nominal rung — an apples-to-apples break on the
      very axis under test); deterministic per seed.
- [ ] **Step 2:** Rungs on the *same* graded items → a length-vs-quality curve that is **paired by
      construction** and isolates length from difficulty. This is the measurement the campaign's
      headline claim needs and has never had. **Rungs run to each candidate's own ceiling** (D1):
      0 / 64K / 128K / 192K for `gemma-4-31B-it-qat-6bit` (config-limited), plus 256K for the qwen-arch
      pair. Cross-model deltas are computed at the **common rungs only**; the 256K rung is reported for
      the two that reach it. A candidate's ceiling is recorded as a fact about its config, never as a
      missing value or a zero.
- [ ] **Step 3:** APC is deliberately **on** here (fixed padding prefix + varying question is exactly
      the prefix-reuse pattern, 54–147× warm TTFT) and recorded. Without it the distill's 124 tps
      prefill makes 192K ≈ 26 min/item *before the first output token*, and the phase is infeasible.

### Task 4.2 — Haystack tasks (secondary, with the control that makes them valid)

- [ ] **Step 1 (test):** `trace` / `locate` / `edit_at_depth` graders (exact-match; patch → apply →
      run authored test; malformed patch is its own outcome; patches outside the allowed target
      rejected, per `swebench_adapter._safe_path`).
- [ ] **Step 2 (test):** **mandatory no-context control arm** — the same question with **no**
      haystack. A pinned public repo is in every candidate's training data, so `locate`/`trace` are
      answerable from memory; any item answered above chance without the haystack is **dropped**.
      Plus systematic identifier/path mutation, and needle **depth as an explicit crossed factor**
      (otherwise cross-model deltas are a position lottery).
- [ ] **Step 3:** `run_ladder` gates on the **bootstrap lower bound ≥ 0.85** and stops only when the
      **upper** bound falls below it, with ≥22 items/rung. Rev 1 stopped on the point estimate — one
      noisy rung fabricates a cliff and *absorbingly* truncates the higher rungs, biasing effective
      context downward.
- [ ] **Step 4:** Add explicit 128K/192K/256K rungs to `REASONING_GRID` (`reasoning.py:14`) and
      `AGG_GRID` (`aggregation.py:14`) — **both top out at 64000**. Rev 1 claimed these were capped at
      131072 and needed a `max_ctx` raise: `reasoning.py` has **no** `max_ctx` and **no** auto-extend
      (it iterates the grid and breaks), and 131072 is only *aggregation's* extend cap
      (`aggregation.py:80`); climbing 64K→256K by `+8000` (`:111`) would have been 24 extra rungs × 5
      samples. Both ladders **already take `samples`** (`reasoning.py:124`, `aggregation.py:78`) — the
      "no repeated sampling" defect is specific to `generate.py`, and rev 1 over-claimed it as
      universal. Keep the three curves **separate** (retrieval / reasoning / coding) per the
      AGENTS.md gate; never average them into one scalar.
- [ ] Commit: `feat(bench): distractor-padding length OFAT + controlled long-context code tasks`.

---

# Phase 5 — Reporting, breakage detection, cheap preflights

**Wall-clock: ~2 days. Box: M2. DoD: `report --markdown` output pasted into `campaign-results.md`.**

- [ ] **Task 5.1 — Scorecard v2.** Per axis: `pass@1` (binary + graded) with cluster-bootstrap CI and
      the axis **MDE**, `conv%` + `nonconv_kinds`, reliability histogram, outcome histogram,
      `successes_per_hour`, provenance (box, profile, APC, KV, submodule shas). `n < 3` renders
      `⚠ n=1` with **no CI**. Cross-box rows grouped separately, never in one comparison table. A
      metric whose CI ⊄ any decision region prints `inconclusive`, not a rank. Emits paste-ready
      markdown so the living doc stops being hand-assembled. Must **not** glob `*.jsonl` blindly —
      `<bench>_samples.jsonl` (`grade.py:114`) and `capacity_ladder.jsonl` (`run_capacity.py:78`) are
      not result files.
- [ ] **Task 5.2 — Breakage detector (renamed, honestly).** ~40 golden items, box-matched bands.
      **It is explicitly NOT the ≤5% quality gate**: at 12 items the MDE is ±36pp, at 40 it is ±20pp,
      and detecting 5pp would need ~628. Rev 1 implied it could gate the lossy-lever rule; it cannot,
      and mislabelling it would let AGENTS.md's ≤5% rule be considered covered when it isn't. Wire
      into the workflow after `chore(stack): bump src/mlx-*`.
- [ ] **Task 5.3 — Canary profile fix.** (The edit-format preflight moved to Task 2.4 — it gates
      gemma's M1 arm.) `run_canary` must use the **run's** sampling profile: `preflight.py:55` calls
      `params_for(model)` with no profile → the `production` default (temp 0.7 for both families), so
      it false-fails models evaluated at 0.6/0.4/0.3. (Precisely: it doesn't *hardcode* 0.7, it
      ignores the profile — outstanding since June, see the harness-issue note in `campaign-queue.md`.)
- [ ] Commit: `feat(bench): scorecard v2, breakage detector, edit-format + canary preflights`.

---

# Phase 6 — CONDITIONAL: brownfield spec-to-feature

**Gated. Do not start unless M1 or P4 shows the candidates actually separate on agentic quality,
AND a 2-hour saturation probe shows the task is not ceiling'd. Wall-clock if run: 3–5 days authoring
+ ~1 day/model.**

Rev 1's greenfield todo-CLI is cut (D3). If this phase runs at all it is **brownfield**: 2+ tasks that
edit into a 50–200K-token existing codebase, so the axis exercises long context *and* agentic editing
together, with ≥6 independent tasks (not 8 features of one codebase, whose effective N is 1).

- [ ] **Step 0 (the gate, ~2h):** hand-run one candidate task against both models. If both complete it
      cleanly, the axis is saturated — **stop, and record that as the finding.**
- [ ] **Step 1:** `clients/` adapters. `clients.opencode` must configure the provider via
      `provider.mlx-local.options.baseURL` in opencode's config — **not** `OPENAI_API_BASE`, which rev
      1 specified and which opencode does not read. Verified on this box: `mlx-local` is **absent**
      from `~/.config/opencode/opencode.jsonc` (the shipped `opencode_config/opencode.json` has never
      been installed), `opencode run` offers `-m provider/model`, `--format json` ("raw JSON events",
      an undocumented internal schema on a weekly-release CLI), and `--pure` is required or every run
      fetches the configured git plugin. Prefer parsing `opencode export <sessionID>` over the event
      stream. `clients.internal` (our own `agent_loop`) is the CI-testable default; opencode is the
      attended-run adapter.
- [ ] **Step 2:** Deterministic gates (short-circuiting, `gate_timeout`, `score=None` on
      short-circuit **counted separately** so an unbuildable submission cannot bias the axis upward by
      dropping out), per-task rubric, judge panel only over test-passing outputs.
- [ ] **Step 3:** Discriminate test — good vs subtly-broken reference solutions must land on different
      outcomes, mirroring the 2026-06-24 evalplus validation. If the harness can't tell them apart it
      measures nothing.

---

# Follow-ons (recorded, out of scope)

1. **Multi-turn session depth.** Every axis here is single-task, fresh-context. The daily driver fails
   at turn 40 with 180K accumulated context. Nothing in this plan measures that. **Highest-value
   remaining gap.**
2. **`mx.get_peak_memory` during agentic sessions at depth** — the ≤46GB gate is verified only on
   capacity ladders, never in the deployment mode being chosen.
3. **Suffix decoding + TQ-KV re-gate at depth** (both shipped on short-chain gates the campaign itself
   calls "too weak"). These *are* model-level levers, unlike APC.
4. **Judge-panel inter-rater reliability** — never run, no agreement statistics; and one author would
   write SPEC, rubric and judge prompts (correlated priors).
5. Router-side invalid-tool logging (fork change); IFEval unblock; LCB `release_v5` contamination-window
   audit; light-tier demotion (policy, not code); thermal-drift sampler.

**Explicitly NOT PURSUED (operator decisions, 2026-08-11 — do not re-raise):**
- **APC quality gate.** APC is a serving-layer cache, not a model capability, so it is out of scope for
  the benchmarks. Its state is still recorded as provenance (Task 0.4) so speed rows stay comparable.
- **Vision axis.** Not a primary focus; no benchmark signal will be gathered. Every registry entry
  advertises `capabilities: [… vision …]` and the 4-bit converts' visual tower is untested — accepted
  as an untested capability rather than a measurement gap.

---

## Sequencing

```
P0 bootstrap+seams ─▶ P1 stats core ─▶ P2 instrumentation ─▶ ▶M1 GATE (matched H2H)◀
                                                                    │
                                              ┌─────────────────────┼──────────────┐
                                              ▼                     ▼              ▼
                                        P3 tool use           P4 long context   P5 reporting
                                                                    │
                                                                    ▼
                                                       P6 CONDITIONAL brownfield
```

**Stop-building rule:** if M1 returns `inconclusive` **and** P4 shows no length-dependent separation,
the campaign's verdict is settled (Ornith on speed + memory margins) — stop building axes and write it
up. Do not build P6 to look for a difference two properly-powered axes failed to find.

## Definition of done

- [ ] `../.venv-bench/bin/pytest bench/tests -q` green (32 existing files + new).
- [ ] v1 fixture jsonl grades to identical `acc` / `conv_rate` (snapshot test).
- [ ] `--samples 5` resumes over v1 rows **and** every grader scores all k (the evalplus/LCB
      per-sample bug is the one that would silently produce wrong numbers).
- [ ] No metric printed without its CI and MDE; no ranking printed without Holm correction.
- [ ] Every phase has produced a committed `campaign-results.md` row.
- [ ] AGENTS.md amended (D2 vector, items-first power, cluster bootstrap, TOST, APC recording) and the
      ~40 legacy INVALID rows backfilled or relabelled.
- [ ] Staged diff grepped for `/Users/`, `/home/`, hostnames, usernames.

---

## Appendix A — adversarial review ledger (rev 1 → rev 2)

**Accepted (verified against the code):**

| Finding | Evidence | Change |
|---|---|---|
| Samples don't buy power; items do | variance decomposition | premise reversed; MDE table added |
| Pooled Wilson understates variance (clustering) | design effect 1+(k−1)ρ | cluster bootstrap |
| `grade_evalplus` collapses k rows by id | `grade.py:102,115,138` | Task 1.2 Step 2 |
| Only `grade_reasoning` exposes per-item results | `grade.py:72` vs `:145,:220,:299` | per-item output first |
| `results_root()` env-only breaks 8 monkeypatch tests | `test_generate_run.py`, `test_grade_evalplus.py` | module fallback |
| `grade_all` hardcodes the results path | `grade.py:328` | routed through `results_root()` |
| `compare` on fingerprint equality refuses everything | `provenance.py:39` incl. `temperature` | comparability redefined |
| `model_params` drift + distill unregistered | `model_params.py:20-29,73-85` | Task 0.3, blocking |
| `solve_instance` returns `str`; contract change | `swebench_adapter.py:107,120,139` | new function, old kept |
| ETTS uses median, should be Wald mean | right-tailed distributions | `E[T_s]+((1−p)/p)E[T_f]` |
| ETTS test cemented an unmatched H2H | rev 1 Task 2.3 Step 3 | test deleted |
| pass^k non-comparable across k, high variance | order-statistic argument | U-statistics + histogram |
| No multiplicity control (79% false-positive) | 30 tests at α=.05 | Holm |
| "indistinguishable" ≠ equivalence | — | TOST + `inconclusive` |
| 0.85 gate needs n≥22/rung; n=5 supports p≥0.57 | Wilson lower bound | Task 4.1/4.2 |
| Ladder stopping on point estimate biases downward | absorbing truncation | gate on bounds |
| Pinned public repo is training data | contamination | mandatory no-context control |
| Fixed `chars_per_token` breaks apples-to-apples | 3 tokenizers | per-model tokenizer |
| Greenfield todo-CLI will saturate; N≈1 | he+/mbpp+ precedent | D3 revised, P6 conditional |
| Replacing BFCL discards the only 12σ axis | SE 1.6pp at n=1000 | D6: repair, don't replace |
| Strict pass@1 makes budget a knob on the headline | AGENTS.md rule | D2 revised to a vector |
| `pass@1\|converged` needs paired intersection | model-dependent subset | Task 1.6 Step 2 |
| Behaviour knobs missing from fingerprint | max_turns/APC/client/… | Task 0.4 |
| Seeds unrecorded → k draws irreproducible | — | Task 1.2 Step 4 |
| `.venv-bench` / `.venv-lcbgrade` / `config.sh` absent | this box | Task 0.1 |
| APC in `runserver.sh:74`, absent from AGENTS.md recipe | apples-to-apples hazard | Task 0.4 |
| `reasoning.py` has no `max_ctx`/auto-extend; grids cap at 64K | `reasoning.py:14,143-175` | Task 4.2 Step 4 |
| Ladders already sample; "no repeated sampling" over-claimed | `reasoning.py:124` | scoped to `generate.py` |
| Phases exit on green tests → graveyard risk | backlog 2–5 | DoD = a committed row; M1 gate |
| samples=5 × n=34 infeasible (41h/159h) | recorded per-case times | k=3 (not k=5) |
| opencode: `OPENAI_API_BASE` is the wrong mechanism; `mlx-local` not installed | `~/.config/opencode/opencode.jsonc`, `opencode_config/opencode.json` | P6 Step 1 |
| `convergence.audit` / `run.py` assert old `valid` semantics | `test_convergence.py:44,85`, `run.py:119-134` | Task 1.6 Step 4 |
| Rev 1's "score the first probe" grades a stale-router artifact | — | annotate + exclude |
| No backfill for ~40 legacy INVALID rows | — | Task 1.7 Step 3 |
| `agent_loop` unknown-tool is line 63, not 56; 32 test files, not 33 | — | corrected |
| Rev 1 cited `campaign-queue.md:167`; the note is now ~:195 | my own queue edit shifted it | cite sections, not lines |
| `judge_one` already takes any string | `judge.py:132` | dropped as a no-op |
| `exec_sandbox` has no `runner` seam, takes files-as-dict | `exec_sandbox.py:9-32` | noted for P4 |

**Rejected / modified:**

- *"Cut `gemma-4-31B-it-qat-6bit` (192K ceiling, `main_models.yaml:55`; ~56 min/aider-case)"* →
  **REJECTED by operator decision.** 256K is a goal, not a mandate; the point is to learn what each
  candidate *can* do. Handled instead via per-candidate rungs + common-rung comparison, sequencing it
  after the winners, and measuring the edit-format confound (D1).
- *"Delete the vision smoke"* → **ACCEPTED and hardened to NOT PURSUED** (operator decision): vision is
  not a primary focus, so no signal will be gathered at all. Recorded so it isn't re-raised.
- *"APC quality gate is the most serious hole"* (my own follow-on #1) → **DROPPED by operator
  decision**: APC is a serving-layer cache, not a model capability, so it is not a benchmark subject.
  Its state remains recorded as provenance for run comparability only.
- *"Score the first probe"* (rev 1's own fix) → replaced by annotate-and-exclude; both variants were
  biased, in opposite directions.
- *"Cut the breakage detector until a bump is pending"* → kept, but resized to ~40 items and
  explicitly relabelled a breakage detector rather than a quality gate.
- *"12 golden items is enough"* → no; MDE ±36pp at n=12.
- Rev 1's `worst_of_k` → dropped (undefined and untested; the reliability histogram subsumes it).
