# M76 B3 + B5 — P426 lever `kv`, build label `s3`, and the Wave 1 extensions (Math500 300, A5 `longctx`) — SPEC v1, 2026-11-13 (four-eyes light; C325)

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
