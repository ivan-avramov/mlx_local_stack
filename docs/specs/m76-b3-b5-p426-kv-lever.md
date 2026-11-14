# M76 B3 + B5 — P426 lever `kv`, build label `s3`, and the Wave 1 extensions (Math500 300, A5 `longctx`) — SPEC v1.4, 2026-11-14 (four-eyes light; C325; v1.1 = B7 v1.1 / C331, §Erratum; v1.2 = change-review dispositions; v1.3 = verify dispositions; v1.4 = C339)

## Goal

M76 stage 3 / 4 (`docs/specs/m76-tq4-certification.md` v1.2 §7) compares `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` arms that
differ in the KV format — N16 (shipped) vs X (`kv_bits: 4` + `tq4_attention: m72_exact`), and V (`m72_v1`) vs X / N16 — with MTP ON
in every arm, through the P426 machinery (Wave 1 sequencer + leg wrapper + pair verifier B8 + signals B6 + panel; Wave 2 tg1
chain). That machinery hard-codes the arm delta to the three MTP (C177) lines, pins the S′ build (label `s2`: fork `1c7c8fa1`,
mlx-serve `1ddf6f84`), and has no long-context retrieval axis and no 300-item Math500. Solving it means: a `lever` parameter whose
`kv` value lets every P426 tool run, verify, pair, sign and panel exactly an arm pair that differs in `{kv_bits, tq4_attention}` with
both arms MTP ON, on a new build label `s3` (the current serving build), with Math500 extended to 300 nested items and a new Wave 1
axis `longctx` (A5) — while `lever=mtp` and the `s` / `s2` labels stay byte-identical to today.

## Scope (files)

Stack only: `benchmark/bench/p426_{leg,receipt,freeze,verify,wave1,wave2,plan,panel,signals,signals_wave1,harvest,ids}.py`,
`benchmark/chains/c147/run_tg1_chain.py` (P426 mode), `benchmark/bench/run_retrieval.py` (+ `bench/retrieval.py` only for seeding),
new `benchmark/results/m76/ids.json` (+ its generator `benchmark/bench/m76_ids.py`); tests `benchmark/bench/tests/test_m76_b3_*.py`.
Read-only: the forks, `main_models.yaml`, every committed P426 result.

## Settled constraints

- (C218 / C233 / C325) arms are stack commits in worktrees served as committed; both arms MTP ON; the M76 arm worktrees are the ones
  `bench.p475_kv --campaign f45 prepare` made (`$STACK_WORKDIR/worktrees/m76-f45-{n16,x,v}`), or equivalent `m76-q-<arm>` branches
  off the stage-3 base (designer's choice at run time).
- (C323 / C324) tiers, looks and statistics are B7's; B3 records and pairs, B6-style signals call B7 (`bench.m76_rule`,
  `bench.stats.paired_session_delta`).
- (P426) every existing guarantee (M50, receipts, engagement, reconciliation, harvest scrub, power rule, idle, pair gate) holds
  under `lever=kv` with the KV delta in place of the MTP delta.

## Interfaces

**Lever.** `--lever mtp|kv` (default `mtp` = today, byte-identical) on `p426_wave1`, `p426_wave2`, `p426_leg`, the tg1 chain's P426
mode, `p426_verify`, `p426_signals*`, `p426_panel`. Under `kv`:
- registry delta between the arms' entries ⊆ `{kv_bits, tq4_attention}` + the arm comment line; every other key equal; MTP keys
  present and equal in both (`p426_leg.py:110-150` generalised; the `P426_ON` pin and seeding hunk do not apply);
- worker argv delta = exactly `--kv-bits <b>` / `--tq4-attention <mode>` (present / absent) (`p426_leg.py:285-305`,
  `p426_receipt.py:23-25`, `:248-249`, `p426_freeze.py:91-100`, `p426_verify.py:41`, `:474-476`, `:579`);
- both arms predictor `mtp`: every request has drafter counters (`p426_verify.py:956` per arm; `p426_wave2.py:97` maps both arms to
  `mtp`);
- arms are named by their KV label (`n16`, `x`, `v`) in tunes, namespaces and paths: `m76-<arm>-b<k>` tunes, results under
  `benchmark/results/m76/{wave1,wave2,panel}/`, scratch under `$STACK_WORKDIR/m76/p426/` — never the `p426`/`p426s2` names;
- the pair verifier B8 accepts a pair only when the deltas above hold and everything else (sampling, budgets, items, seeds, box,
  M50, receipts VALID, fingerprints except the KV / mode fields) is equal; a stage-4 pair (V vs X, or V vs N16) is a `kv` pair too.

**Build label `s3`.** `EXPECTED_BUILDS["s3"]` (`p426_plan.py:21-24`) = the stage-3 base's fork gitlink (`34a21208…` or later), its
mlx-serve gitlink, the production ref `f9bf743f…`, mlx 0.32.4; every place that reads a label (`p426_freeze.py:358`, `:569-576`,
`p426_verify.py:587`, `p426_panel.py:339`) follows it; `s` / `s2` untouched.

**Wave 1 axes under `kv`.** `math500` (ids from `benchmark/results/m76/ids.json`: 300 = P426's 100 then 200 drawn by
`random.Random(7601)` from the remaining Math500 ids, the block split by seed 426 as P426 B9; tier 1 = the first 100, tier 2 = the
rest — a leg names its tier), `cjudge`, `vision`, `reasoning` (A4) and `m1` as today (M1: both arms `--predictor on`; the X / V arm
binds `qualify --certified-by <stage-2 summary>` + `--production-ref f9bf743f…` per B2), and new `longctx` (A5).

**A5 `longctx`.** Items in `ids.json`: n prompts (40 ≤ n ≤ 80; the value B7's simulation reports — default 40), half retrieval and
half chain-4, spread over rungs 131,072 / 159,744 / 196,608, each item `{id, task: retrieval|reasoning, rung, task_seed,
request_seed}` (seed 7605); runners: `bench.run_retrieval --grid <rung> --samples 1 --task-seed-base <s> --request-seed-base <r>`
(new flags, mirroring `run_reasoning`'s B13 seeding; without them behaviour unchanged) and `bench.run_reasoning --grid <rung>
--samples 1 --chain-len 4 --task-seed-base … --request-seed-base …`; deployed sampling, full budgets (the 196,608 rung resolves
`max_tokens` to 65,536, equal in both arms); strict scoring: retrieval PASS only if all five codes are recovered AND converged;
chain-4 exact AND converged. Plan / verifier / signals / panel adapters as the other Wave 1 axes (the panel over both-correct
pairs). Every item's prompt token count is checked offline before the leg (prompt + resolved budget ≤ 262,144).

**Signals (B6-style, under `kv`).** `benchmark/results/m76/SIGNALS.md`, generated: per axis the verdict of `bench.m76_rule` at its
look(s), the paired deltas (A1 `paired_delta` at the look's alphas; A7 / A8 `paired_session_delta`), per-session results, the
session-disagreement flag, the N16 s1-vs-s2 noise floor (A7), A5's per-task gates (each arm ≥ 0.85, per-task point ≥ −5 pp), the
panel (Holm), decode per item (P426 T2 estimator) with acceptance, coverage. Labels "X − N16", "V − X", "V − N16".

## Acceptance criteria

1. Red-first tests (mocked ops, real registry texts of the three M76 arms, real argv spelling): the `kv` delta accepted for N16 / X,
   X / V, N16 / V; refused when an MTP key differs, a non-KV key differs, or the argv differs beyond the two flags; both arms
   predictor `mtp`; `s3` pins; names and paths under `m76`; Math500 300 ids nested and deterministic; A5 items (counts per task /
   rung, seeds, token-budget check); `run_retrieval` seeding (same seeds → same prompts; default unchanged); signals calling B7.
2. `lever=mtp` byte-identical: a golden of today's P426 Wave 1 / Wave 2 plans, argv, receipts and the regenerated
   `benchmark/results/p426/SIGNALS.md` from the committed P426 evidence (green before the change).
3. The existing P426 / tg1 suites pass unchanged; the stack suite passes or fails only as on the baseline.

## Non-goals

tg2 legs (B4); B7's statistics; running anything on the GPU (the designer runs the smokes).

## Erratum v1.1 (C331; follows B7 spec v1.1, `docs/specs/m76-b7-statistics.md` §Amendment v1.1)

- A5 n: the value B7's report states, a multiple of 6 in 42 … 120 (two tasks × three rungs, equal cells); `m76_ids.py` reads it from
  `benchmark/results/m76/b7-simulation/report.json` (`a5.n`) or takes `--a5-n` (must be a multiple of 6 in range; default: the report's
  value; refuse when neither exists). Items split equally per task × rung.
- Signals: A5's verdict and loss bound come from `bench.m76_rule.verdict_a5(b, c, n)` (exact test), not a bootstrap; A7 / A8's loss
  bound is `paired_session_delta` at the calibrated α* that `bench.m76_rule.axis_plan(axis)` returns; the session-disagreement flag
  is replaced by `bench.m76_rule.session_interaction(a, b)` (`flag`, `pvalue`), still blocking; per-session results stay descriptive.
- B7 is built in parallel: code against these names; tests mock `bench.m76_rule` / `bench.stats` B7 functions where they are absent
  from the copy (an import shim in the test, never in the product code); the designer re-runs the signals tests after B7 lands.

## Erratum v1.2 (2026-11-14, designer; the B3 change review's adopted dispositions)

- **Scope (designer correction):** A7's s3 (seed 3003) needs `benchmark/bench/schedules.py` and `benchmark/bench/chain_core.py`;
  both join the scope. The lever's sessions and looks come from B7's `axis_plan("A7")`; incomplete evidence (a planned session
  missing) is refused, never verdicted.
- **Signals call B7's final entry point:** every mechanical verdict comes from `bench.m76_rule.axis_verdict(axis, look, a, b)` (A5
  through it to `verdict_a5`), keeping its α, bound, verdict, per-session results, interaction flag and `size_warnings`; any size
  warning is a blocking flag (→ the operator). `paired_delta` / `paired_session_delta` appear only as descriptive columns.
- **A5 budgets:** the planner freezes each item's actual prompt token count (offline tokenizer count of the exact prompt) and its
  resolved `max_tokens` = min(deployed budget, 262,144 − prompt tokens); B8 requires both arms' rows to carry the same prompt token
  count and resolved budget per item; strict convergence uses the row's own resolved budget (`convergence.resolved_thinking_budget`
  and the resolved `max_tokens`), never a planner constant. (The v1 "65,536 at 196,608" is the cap before the prompt's own tokens.)
- **A5 / A4 outputs never collide:** axis-specific tunes / stems; a test runs A4 then A5 into one populated results directory.
- **B8 completeness and provenance:** any rejected planned key (seed mismatch, missing row) rejects the pair; the pair compares the
  complete normalized provenance fingerprint (runtime controls, sampling profile, serving-path hashes, fingerprint version) with an
  explicit whitelist for the KV / mode keys and the arm commit.
- **Panel, end to end for `kv`:** export → freeze (bound to B8 and the packet hashes) → judge → seal, as the `mtp` lever's panel;
  two judge families required (a single-family set refused unless the operator labels it, C166 / C206); signals verify the frozen
  record. A5's panel: chain-4 both-correct pairs under the reasoning rubric; retrieval both-correct pairs are identical strings and
  excluded (stated in the sheet).
- **Decode per item:** P426's T2 estimator (descriptive).
- **Lever surface as specified:** the existing functions take `lever=` (`registry_delta_problems`, `model_argv_problems`, `leg_name`,
  `frozen_path`, `schedule`, `leg_argv`; dispatching to the `kv_*` implementations); `--lever mtp|kv` (default `mtp`) at the top level
  of `p426_verify` and `p426_panel`.
- **Stage 4 (V) is not in B3:** the V-only / X-reuse / sentinel workflow and V's M1 binding are a stage-4 item (planned before stage 4,
  S23-P49). Until then a `kv` sequence naming V refuses at preflight, before any leg runs.

## Erratum v1.3 (2026-11-14, designer; the B3 verify's adopted findings)

- **A7 provenance:** each A7 session pair loads both arms' per-invocation provenance manifests and compares them with
  `kv_provenance_problems` (same normalisation and whitelist as Wave 1); any other difference rejects the session pair.
- **Panel inputs bound to B8's items:** packet prompts / attachments are derived by the tool from the benchmark inputs of the items
  B8 covers (Math500 problem text, cjudge prompt, vision image + question, A4 / A5 question only — never the long context), with a
  per-item input sha frozen in `FROZEN.json` and checked against the item id; a `--prompts` file, if kept, is validated against those
  shas. No caller-supplied mapping enters a packet unvalidated.
- **Incomplete panel blocks:** signals require every B8-expected member and every frozen judge × order verdict slot; otherwise a
  blocking `panel_incomplete` flag (→ the operator). Partial ingestion only under an explicit `--partial` mode, labelled.
- **Exclusion accounting:** a rejected pair's panel exclusions include its rejected keys (deduplicated).

## Amendment v1.4 (C339, 2026-11-14: A5 two looks)

- **A5 tier 2:** `ids.json` holds A5's 120 items: tier 1 = the first 72 (as today), tier 2 = 48 more, drawn by the same seeded
  generator (seed 7605) as the continuation of the same per-task × rung cells (8 more per cell; tier prefixes nested, never a redraw);
  each item's frozen prompt count and resolved budget as v1.2. A leg names its A5 tier (`--tier 1|2`, as Math500).
- **A5 signals per look:** like A1 — the looks and their α come from `m76_rule.axis_plan("A5")` (B7.1 v1.4); look 1 on tier 1, look 2
  on tier 1 + tier 2 only when look 1 is UNDECIDED; a look-1 LOSS stops; the per-task point gates at the deciding look.
- The A5 sizes come from the plan (`axis_plan("A5")` looks' `n`), never constants.
