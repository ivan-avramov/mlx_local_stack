# P426 — `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` MTP-ON router-chain re-certification — PLAN v4, 2026-10-21

Authority: P369 v13 §3.1 Restore + §6, C177, C203 (settings-level registry matching, bundled here), C204 (ship a predictor that
speeds up with no or negligible quality / memory downside; operator judgement on ongoing quality / memory / speed signals, no
strict thresholds; opencode ON vs OFF as a primary workload; GPU cost no constraint). P369 phase 2 passed for this entry (E1c 5
cells, E2; C188 carry-over + smoke 15 on production `7207179b`).

Reviews: `docs/reviews/p426/plan-round{1,2}.*`. v2 applied R1–R15; v3 applies round 2 (open R1 R3 R6 R7 R8 R10 R11 R12 R13, new
S1–S8): one leg wrapper enforces freshness, receipts, pins, argv and engagement on every leg (B10: R1 R12 R13 S3 S8); the full M1
invocation (R3); B2 reduced to the existing chain driver run per leg under an outer sequencer + an invalidate policy (R6 R7); a
P426 pair verifier with per-axis adapters (R8); generation-side artifact persistence before Wave 1 and A3 two-provider-or-pending
(R10); fork B4 before S (R11); vision ids (S1); smoke sets (S2); A2 panel-only (S4); A4 distinct seeds (S5); block-level power
validity (S6); pre-registered tests and Holm families (S7). v4 applies round 3 (the last; open R6 R8 S2 S5 S7 S8, new
T1–T3) without a fourth review round, pending the operator: executable tg1 invocations + overlay validation for one entry +
reversed s2 order (R6), an M1-specific verifier adapter (R8), M1 smokes both arms (S2), reasoning task / sampler seeds (S5), A4
out of Holm (S7), fail-closed power rule (S8), the A2 command (T1), the decode-rate estimator (T2), the leg-by-leg estimate (T3).

## 1. What this decides

Whether the entry ships MTP-ON again: its three C177 lines restored (`mtp_verify_scan: joint_v1`, `draft_kind: mtp`,
`draft_model: caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter`). The run produces per-axis SIGNALS (§8); the
operator makes the call (C204). No automatic pass / fail.

**Attention flags** (to the operator with a recommendation; never an automatic veto): a mechanical axis / session with ON − OFF
point < −5 pp, or Holm-adjusted p < .05 with OFF better (§8); a subjective item family member with Holm-adjusted p < .05 favouring
OFF; ON 256K prefill peak > OFF + 2 GB or ON > ≈ 48 GB; decode ratio ON / OFF < 1.3× on A1 or A7; pooled acceptance (within an
axis / session) < 0.70 (context: M40 Math500 0.78 on TQ4 KV, M42 native16 0.78–0.82); a non-convergence kind or runaway-tax flag
present in ON and absent in OFF.

## 2. Build, arms, provenance

- **One serving build** (R11): stack commit S = the bump carrying fork B1 + B4 + B7 (§9); `src/mlx-vlm` = production `7207179b` +
  B1's logging only (+ dev-only B4 / B7), `src/mlx-serve` `86921f02`, `main_models.yaml`. Every leg asserts these three pins
  (submodule SHAs + registry sha256). Driver code may differ between waves (recorded per leg); no fork change after S.
- **Frozen worktree** (R11): every leg runs router AND driver from `$STACK_WORKDIR/worktrees/stack-p426` at S (submodules checked
  out, own `.venv` via `uv sync`, `.env` copied). Wave 2 moves it to the stack commit carrying B2 / B6 only after asserting the
  serving pins unchanged.
- **Arms.** OFF = `main_models.yaml` at S. ON = OFF with exactly the three C177 lines uncommented by the B4 rule (cross-checked
  equal to `registry_states.overlay_on`); `$STACK_WORKDIR/p426/registry-{on,off}.yaml`, both sha256 in every receipt; the
  three-line unified diff asserted before every ON leg.
- **Fixed:** weights, tune (t0.5, medium), native16 KV, cap / preallocation 262,144, prefill step 512, budgets (`max_tokens`
  102,400, thinking 81,920), `--sampling-profile deployed`.
- **Router per leg:** lean start, `MLX_VLM_CACHE_SESSION_MAX=1`, `APC_ENABLED` absent, no OWUI / docker, `MLX_SERVE_CONFIG=<arm
  registry>` exported to router AND driver, fresh start (`scripts/stack_stop.sh`, :8000 free, new ownership, M50, PID + config
  hash re-verified at exit). M1 runs in-process (no router).
- **Leg wrapper (B10), every leg incl. smokes:** pre-leg receipt — destinations absent (R1; refuse otherwise, no resume), pins,
  registry shas, worker argv exact (ON: `--model <hf_path> --draft-kind mtp --draft-model caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter
  --mtp-verify-scan joint_v1`; OFF: same `--model`, none of the three), target + (ON) drafter snapshot files hashed against fork
  `dev/p369_phase2/pins.json`, `scripts/sweep_orphan_shells.sh` run, zero `session_cache_probe` / `opencode run` survivors, no
  other MLX worker, process census, load average, uptime, AC / voltage / battery (S8). Exit receipt — the same re-checked, plus
  the engagement gate (S3): every eligible ON request has `draft_kind=mtp`, rounds > 0, proposed > 0, 0 ≤ accepted ≤ proposed;
  every OFF request has no draft activity; rows / log records reconcile exactly (missing, duplicate, zero or contradictory
  telemetry → leg INVALID). Drift between receipts → the leg's speed block INVALID. **Power rule (S8), fail closed:** at entry and at every watcher
  tick, `pmset -g ac` must read 140 W and 28 V and battery > 20 %; any other or unreadable value, or any on-battery interval in
  `pmset -g log` overlapping the leg window, marks the leg's speed block INVALID (entry failure: the leg does not start).
- **Watcher (B5), every leg incl. smokes:** 5-min ticks with item progress, mean-based ETA vs prediction, errors, convergence,
  token distribution, correction-vs-finish note, watts / volts / battery, sticky failure; `pmset -g log` checked against the leg
  window (P418).

## 3. Order balance and validity (R12, S6)

Each axis runs two blocks: block 1 OFF → ON, block 2 ON → OFF; every leg a fresh load; ≥ 10 min idle between all legs. Items
split into blocks by a seeded shuffle (seed 426), committed with the ID sets (B9). Quality pairs per item across arms; within an
arm the two loads hold disjoint items (no item pooled across loads). **Speed validity is per block:** if either leg of a block is
power- or receipt-invalid, both legs leave speed inference; with one valid block the ratio is reported descriptive, "not
order-balanced". Quality survives a power-invalid leg (labelled) but not a receipt- or transport-invalid one.

## 4. Smokes (S2)

Before each full axis: a smoke per arm on committed seeded-random IDs (B9; same IDs both arms): A1 5, A2 5, A3 5 images, A4 1
draw (task seed 128000006, outside the full set), M1 one OFF and one ON leg (fresh outputs, full B10 / B7 checks); A7's pilot (§6). Gate to launch the full axis: both smoke legs VALID (B10
receipts, engagement, zero transport errors), estimate recalibrated from smoke walls. Smoke rows never enter signals.

## 5. Wave 1 axes (namespaces fresh per leg; tune / tag labels `p426-{off,on}-b{1,2}`, smokes `-smoke`)

| Id | Axis | Run (frozen worktree, inside B10) | Signals |
|---|---|---|---|
| A1 | Math500 100 (M40's ids) | `benchmark/run.py generate --models <entry> --benches math500 --limit math500=0 --ids math500=<block ids, colon-separated> --sampling-profile deployed --tune p426-<arm>-b<k> --order roundrobin --seed 0 --seed-base 0 --samples 1`; timeout derived | `acc_strict@81920`, conv%, nonconv kinds; per-row decode, acceptance (`row.draft`); wall |
| A2 | cjudge 40 | `benchmark/run.py generate --models <entry> --benches cjudge --limit cjudge=0 --ids cjudge=<block ids, colon-separated> --sampling-profile deployed --tune p426-<arm>-b<k> --order roundrobin --seed 0 --seed-base 0 --samples 1` | mechanical quality N/A (grader `acc: null`, S4): panel only; conv%; decode; acceptance |
| A3 | Vision gate 20 | `benchmark/vision_gate.py --model <entry> --ids <block ids> --out benchmark/results/<entry>/vision_gate.p426-<arm>-b<k>.jsonl` (`--ids` = B11) | self-pass (lenient, labelled); panel (§7); turn-1 latency + decode |
| A4 | Reasoning depth 128K | `bench.run_reasoning --model <entry> --grid 128000 --samples 3 --chain-len 4 --sampling-profile deployed --out-tag p426-<arm>-b<k> --task-seed-base <b>` (B13); block 1 task seeds 128000000–002, block 2 128000003–005, each draw with an explicit request seed `rowschema.sample_seed` recorded beside the task seed, both paired across arms (S5); completion text persisted (B12) | strict draws, budget hits; DESCRIPTIVE (6 unique draws per arm, one synthetic task; no interval); decode; acceptance |
| M1 | Memory at 256K | fork `dev/p369_phase2/qualify.py --stack-root <worktree> --fork-root <worktree>/src/mlx-vlm --reviewed-head <S's fork sha> --entry Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed --predictor {off,on} --out $STACK_WORKDIR/p426/m1/leg<k>-<arm>` (B7), legs OFF / ON / ON / OFF, four fresh outs; 260,096-token prompt, shipped settings, phase-reset `mx.get_peak_memory` | prefill / decode / retire peaks per leg, ON − OFF; prefill + decode tok/s; acceptance |

Every runner's planned item list is asserted equal to the committed block membership before the first request (B10, T1)
and again from the rows at exit. Row `peak_mem_gb` is reported only as "arm-lifetime high-water". Historical numbers (R7 MTP-ON 38.25 GB, M40, M42) are context
with a fingerprint-labelled delta (C199), never a pair.

## 6. Wave 2 — A7 opencode tg1 (the primary agentic benchmark; R6, R7)

- Corpus tg1 (`benchmark/m62/universe.json`, 43 items: 22 Python + 21 Go), `run_tg1_probe.py` (P311-lite), hermetic v2 env,
  `--sampling-profile deployed`; probe-code sha, skill policy, config hash recorded; never pooled with M63 (C173).
- **Legs:** the existing `benchmark/chains/c147/run_tg1_chain.py`, ONE invocation per leg (`chain <session>` positional,
  `--predictor off|mtp`, single entry via B2's `--model` filter; the exact argv per leg is generated by the sequencer and
  pinned in tests), sequenced by an outer P426 sequencer: pilot OFF, pilot ON (5 seeded-random items) →
  s1 OFF, s1 ON (seed 1001) → s2 ON, s2 OFF (seed 2002, reversed item order — implemented and tested in B2; today's schedule
  sorts) → reload ON, reload OFF (the pilot's 5 Python items at
  seed 1001). Each leg a fresh load, own fresh root; k = 2 loaded instances per arm (s1, s2). The sequencer's frozen record holds
  the stack commit, serving pins, registry shas, probe-code sha, pins.json sha, and refuses a leg on any drift.
- **Fail closed (R7):** a new chain-core policy `invalidate` (B2): the first transport incident (HTTP / connection error,
  timeout, served-config drift) stops the leg and marks it INVALID — no archive-and-rerun, no retry. A rerun is an operator
  decision, labelled. Retries 0.
- **Reporting:** per session (s1, s2) separately: paired `acc_strict@budget` ON − OFF with its two-stage cluster-bootstrap interval
  and MDE, convergence, runaway tax (budget-hit / turn-cap / exec-timeout + per-session union), session wall; never pooled across
  sessions; reload diagnostic only; pooled tax rates descriptive. Speed (T2): per item and arm, decode rate = total generated tokens ÷ summed decode time over the item's B1 log lines
  (attributed by session id + request window); the paired per-item ratio is bootstrapped over items within each session;
  request ordinals are never paired. Acceptance = summed accepted ÷ summed proposed within the session only. A1 / A2 / A4 use the
  same per-item estimator from their rows.

## 7. Subjective quality (R10)

The C161 / C166 panel (B3 = P427): two judges from two model families (C206; configured per box — m5max-128 default: Claude Opus via Claude Code + a
Cursor model of another family), blind pairwise, both orders, length-adjusted, judge model id / client version / prompt sha per verdict,
retries 0. Over execution-passing pairs: A1 (both-correct), A2 (all 40), A4 (strict draws), A7 (both-pass items per session; the
judge packet = task, final diff / tree, transcript summary). A3: image + caption + both descriptions; the second family is a Cursor model that
accepts images (e.g. Gemini) if one does; otherwise a Claude-only result, labelled single-family (C206). **Generation-side artifacts land
before Wave 1 (B12):** A4 completion text; A3 description + image path per row; A7 final tree + transcript per item (verified
present by B10's exit receipt). Judging needs no GPU and may run after the legs.

## 8. Signals sheet and tests (R8, S7)

B6 generates `benchmark/results/p426/SIGNALS.md` from receipts / rows / logs (never hand-copied), regenerated after every leg,
only for pairs the B8 verifier accepts: per axis (A7 per session): quality, panel, memory, speed (paired ratio with a two-stage
bootstrap interval; pooled + per-row acceptance; wall; invalid blocks listed), coverage (legs done / pending / invalid), flags.
Descriptive; no composite.

**Pre-registered tests (S7).** Mechanical family = {A1, A7-s1, A7-s2} (A2 N/A, A4 descriptive): H0 ON − OFF = 0 on per-item
`acc_strict` differences; paired sign-flip permutation test, 10,000 permutations, seed 426, two-sided; zero differences
contribute zero; Holm across the family. Subjective family = {A1, A2, A3, A7-s1, A7-s2} (members with < 5 judged items are
reported, not tested; A4 is reported as its draw distribution only, never tested — S7): per item score = mean over 2 judges × 2 orders of (ON win 1, tie 0.5, OFF win 0), length-adjusted per the
C161 estimator; H0 mean score = 0.5; same permutation procedure; a missing verdict excludes the item from that member (counted);
Holm across the family. Intervals: two-stage cluster bootstrap (items within sessions), 95 %, 10,000 resamples, seed 426.

## 9. Builds and DAG

Each test-first, own Cursor code review ≤ 3 rounds, suites in both repos where touched.

Before S (fork): **B1** (production, log-only): thread `draft_kind / draft_rounds / draft_n / draft_n_accepted` from
`GenerationMetrics` into `_build_metrics_envelope` (a `draft_counters` dict, the M58 `verify_counters` pattern) at every
`record_success` call site that already passes `verify_counters` (OpenAI chat / responses streaming + non-streaming, Anthropic),
and into the `Request completed` line; absent when no drafter ran; red: end-to-end ON / OFF, streamed and not. **B4** (dev, C203):
the settings-level matcher in `registry_states`. **B7** (dev): `qualify.py --predictor {on,off}` for this entry (today forced ON);
OFF serves the committed registry; refusal tests.

Before Wave 1 (stack): **B9** `benchmark/results/p426/ids.json` (A1 = the `math500.m40on.jsonl` 100, asserted unique / equal; A2 40;
A3 20; block split seed 426; smoke sets; A4 seeds; sha256 recorded at commit). **B10** the leg wrapper (§2). **B5** watcher
(§2). **B11** `vision_gate.py --ids` (refuses unknown / duplicate / missing / wrong-block ids before the first request; exact
membership in the manifest). **B12** artifact persistence (§7). **B13** `run_reasoning --task-seed-base` + an explicit
per-draw request seed (`rowschema.sample_seed`), both persisted. **B4-stack** the overlay builder on the same rule (a pinned table
mirrored from `ENTRY_OFF`, cross-checked against the fork module).

During Wave 1 (stack; tests only in scheduled windows between axes, each followed by ≥ 10 min idle): **B8** the P426 pair
verifier: per-axis adapters (rows, vision, reasoning, qualify, chain records) that require exactly the three-key registry delta and
the matching runtime delta (argv incl. `--draft-model`) and equality of everything else (sampling, KV, code, box, budgets, item /
seed sets, timeouts, M50, serving path, receipts VALID). The M1 adapter (R8): M50 / serving path N/A (in-process); instead
equality of the reviewed harness head, registry state (OFF bytes / ON overlay sha), worker argv, artifact pins, environment
(`MLX_*`, `TQ_*`, `KV_*`) and VALID receipts — fail closed on any mismatch. **B2** tg1: `--model` single-entry filter, the `invalidate` policy,
the outer sequencer + frozen record, the MTP overlay validated for the selected entry only against the exact P426 ON registry
(today it requires both historical picks MTP-enabled), the reversed s2 item order; tests for argv, order, fresh roots, drift
refusal, no-restart. **B6** signals (§8). **B3** panel
(P427).

**DAG:** (1) now, while R5 runs: write B1 / B4 / B7 code + red tests (no test runs during R5). (2) R5 ends → test window: red /
green, fork suites ×2 + 8 audits; Cursor code review. (3) Fork commit → **fork push (operator approval)** → stack bump = S + B9 /
B10 / B5 / B11 / B12 / B13 / B4-stack, stack suite. (4) Wave 1 smokes → full axes. (5) During Wave 1: B8 / B2 / B6 / B3. (6) Wave 2.
Panel judging as artifacts land.

## 10. Estimate

GPU lower bounds (M40 / M42 / M63 / R7 walls) [+30 % allowance]: Wave 1 — 30 legs (10 smoke: A1 / A2 / A3 / A4 / M1 × 2 arms; 20 full: A1 / A2 / A3 / A4 / M1 × 4) and 29 idle gaps: smokes
≈ 3.0 h, A1 3.4, A2 2.7, A3 0.3, A4 1.9, M1 1.0, loads 0.3, idle 29 × 10 min = 4.8 → 17.4 h [22.6]. Wave 2 — 8 legs (pilot,
s1, s2, reload × 2 arms), 7 gaps: tg1 ON 3.1 + OFF 7.0, pilots 0.6, reloads 0.6, idle 1.2 → 12.5 h [16.3]. Total ≈ 30 h [39 h]. Not GPU: builds + reviews ≈ 1–2 days before Wave 1;
test windows ≈ 0.75 h each; panel judging (tokens).

## 11. Restore

On the operator's ship-ON call: restore exactly the three C177 lines, `CERTIFIED P426 <date>` (or `PROVISIONAL`) in
`generation_defaults`, `benchmark/bench/tests/test_opencode_probe_seeding.py` (`per_query` → `joint_v1`, source "registry"),
README / campaign-results evidence rows, one commit; under C203 no fixture refresh. No client sampling change. Ship-OFF: signals
recorded, lines stay commented. Then per entry: `Qwen3.8-27B-mlx-uniform-4bit`, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (after
P405 R6, on their codec), `Ornith-1.0-35B-mlx-uniform-4bit` — reusing B1–B12.

## 12. AGENTS.md amendment (operator)

C204 replaces "ship OFF if OFF wins beyond ±5pp on any axis". Proposed Registry-section wording: "Certify the predictor ON vs
OFF on every supporting axis plus memory and speed; ship it when it speeds up with no or negligible quality / memory downside —
the per-axis signals go to the operator for the call; −5 pp on an axis is a flag, not a veto."
