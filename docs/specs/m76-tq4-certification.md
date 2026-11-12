# M76 (M72 1.4) — certify `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` on TurboQuant 4 KV + `tq4_attention` + MTP ON — SPEC v1.2, 2026-11-11 (v1.1 = cold design review round 1 of 3 applied, `docs/reviews/m76-design/round1-ledger-report.md`; v1.2 = the verify, round 2 of 3, applied, `round2-ledger-report.md`)

Authority: C322 (Go, stages 1–4, memory is the accepted gain), C319 (`m72_exact` beside `m72_v1`; `m72_v1` certified as a lossy
lever), C318, C321 (1.3 accepted), C204 / C206 (predictor and panel rules), C172 / C173 (wash and loss-bound rule), C218 (arms are
stack commits), C233 (measure in the shipped MTP-ON state), C258 (the P369 exactness basis for a TQ4 MTP-ON pick), C291 (the shipped
N16 pick), C168 / C109 (k = 2 loaded instances), S20-P18 / C316 (real-data A1 carried here), S21-P2, S21-P10, AGENTS.md.
Cold design review (strict): round 1 of 3 done (Sol, GLM, Sonnet); v1.1 changes marked [r1], v1.2 changes [r2] (not re-reviewed). Harness adapters: four-eyes light (C322).

## 1. Goal

Decide, on evidence the operator can weigh, whether `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` ships TurboQuant 4 KV with
`tq4_attention: m72_exact` (or, conditionally, `m72_v1`) and MTP ON as its default instead of the certified native16 + MTP ON
entry. The accepted gain is memory (≈ −5.4 / −10.9 GB at 131K / 262K, 1.3 A5 + S21-P2); speed is reported, not required. Solving it
means four generated records, each from arms served as committed stack commits on one serving build:

1. a speed / memory matrix (four arms, four rungs, two order-balanced blocks) with the mode proven engaged on every leg;
2. an exactness verdict for `m72_exact` MTP ON vs plain decoding at scale (P369 E1c + E2 on the TQ4 tuple);
3. a quality comparison TQ4 `m72_exact` vs native16 on the P426 axes, read by the pre-registered C172 / C173 rule;
4. conditionally on (1), `m72_v1` vs `m72_exact` on (3)'s axes as a second one-factor lever.

Then a recommendation; the pick changes only on the operator's approval (§10).

## 2. Settled constraints

- C322: stages and arms as listed; the operator accepts memory as the gain; publish only after the operator's pick approval.
- C319: `m72_exact` = TQ4 MTP ON emits exactly what TQ4 MTP OFF emits (greedy); `m72_v1` is not exact (≈ 3e-3 relative in
  attention), certified as a lossy lever with `m72_exact` as the fallback.
- C218 / C233 / AGENTS.md: every arm is a stack commit in its own worktree, served as shipped (mlx-serve → mlx-vlm, committed
  `main_models.yaml`); lean benchmark router (`MLX_VLM_CACHE_SESSION_MAX=1`, no OWUI, `APC_ENABLED` absent); one resident model;
  ≥ 10 min idle between legs; order-balanced arms; 140 W / 28 V / battery > 20 % at entry and every tick; independent 5-minute
  watcher; transport errors abort; retries 0; M50; deployed parameters (`--sampling-profile deployed`); thinking ON, budgets fixed.
- C204: the predictor ships when it speeds up with no or negligible quality / memory downside; per-axis signals to the operator;
  −5 pp is a flag, not a veto.
- C172 / C173: an interval that includes zero is a WASH, picked by point estimate "directional (not a shown difference)"; a lossy
  lever ships on a wash only when the observed loss bound ≤ 10 pp (−CI lower bound; zero-discordance cells: the exact discordance
  bound), else "loss not ruled out above X pp" → operator.
- C161 / C206: subjective quality = two-judge blind pairwise panel, two model families, both orders, length-adjusted, judge model
  id / client version / prompt sha per verdict.
- C109 / C168: agentic chains run k = 2 independent loaded instances with distinct paired seed schedules + a same-seed reload
  control; accuracy paired per session, never pooled.
- Never pool across fingerprints, predictor states or caps; N16 is remeasured on this build (P426's S′ rows are context only).

## 3. Facts (verified 2026-11-11)

- Committed entry (`main_models.yaml`): `kv_quant_scheme: turboquant`, `kv_bits: 0`, `quantized_kv_start: 0`,
  `max_kv_cache_size` = `kv_prealloc_tokens` = 262,144, `cache_session_shrink: true`, `prefill_step_size: 512`,
  `attention_policy: fused_v1`, `lazy_prompt_embeddings: true`, `mtp_verify_scan: joint_v1`, `draft_kind: mtp` + `draft_model`,
  `generation_defaults` CERTIFIED P426 2026-11-04 (C291), temperature 0.5 / top_p 0.95 / top_k 20, `max_tokens` 102,400,
  `thinking_budget` 81,920.
- Serving build (the M76 base): stack `main` (≥ `8c65dac0`), fork `5f83c84f`, mlx-serve `0f2259f`, mlx / mlx-metal 0.32.4.
- 1.3 mode (`docs/specs/m72-1.3-tq4-production.md` v1.1 + errata): `tq4_attention: m72_v1 | m72_exact` requires `kv_bits: 4`,
  `kv_quant_scheme: turboquant`, `attention_policy: fused_v1`, `mtp_verify_scan: joint_v1`; layer 63 stays native16 (`fused_v1`,
  `joint_v1`); route counters per process in the worker's `/health` details and the `bench.provenance` manifest (at creation and
  exit); fingerprint v9 records the mode.
- Served path (S21-P10): every request that resolves to a session runs inline (B = 1, MTP, the mode's kernels); continuous batching
  only with the session cache off, anonymous sessions off, or a request without hashable messages (counted `fallback:batch_cache`).
- 1.3 real-model acceptance (`benchmark/results/m72/m72-13/`): production prefill 1.004× the dev p2s path (≈ 0.98× native16);
  production peak delta 7.815 GB at 131,072 within the A5 bound; `m72_exact` greedy MTP ON = OFF at 8K / 32K (A4 (c)); `m72_v1` vs
  `m72_exact` first differing token 31–372 on 10 seeded prompts.
- Projected decode MTP ON vs native16: `m72_v1` 1.10–1.19×, `m72_exact` ≈ 0.95× (`MMA.md`; the projection ran +7…+18 % optimistic).
- Walls for the estimate: P475 `Qwen3.8-27B-mlx-uniform-4bit` legs (driver 1,885 s N16 … 3,936 s TQ4 on the old TQ4 path); P426 S′
  N16 MTP-ON legs: A1 4,518 s, A2 3,691, A3 433, A4 1,659, M1 1,536 (both blocks); A7 pilot 1,111, s1 8,763, s2 9,633, reload 1,081.
- Feasibility of the C173 bound (`bench.stats.paired_delta`, seed 426): tg1 n = 43 with balanced discordance — 2 → bound 7.0 pp,
  4 → 9.3 pp, 6 → 11.6 pp; Math500 n = 100 — 6 → 5 pp, 8 → 6 pp. P426's N16 ON vs OFF had 1 discordant item per session, but those
  arms were byte-identical wherever context matched; TQ4 vs N16 diverges from the first differing logit, so discordance will be
  the per-item stochastic rate (≈ 2·p·(1 − p)·n ≈ 2.5 items at p ≈ 0.97). The rule is attainable but not certain on tg1.

- Code map (2026-11-11, source read at the base; file:line in §5): the P475, qualify, P426 and P369 harnesses hard-code the
  `Qwen3.8-27B-mlx-uniform-4bit` pick, the MTP three-line delta, the S′ build pins or the 16 accepted registry states; none
  accepts a `tq4_attention` arm today. `bench.arm_identity` already classifies `--tq4-attention` (added in companion commit `28235601`).
- **TQ4 MTP OFF with the mode is not servable today (S22-P10):** mlx-serve `config.py:175-178` (`tq4_attention` requires
  `mtp_verify_scan: joint_v1`) + `:256-260` (`joint_v1` requires `draft_kind: mtp`); fork `mlx_vlm/tq4_attention.py:88-90`,
  `mlx_vlm/mtp_verify_scan.py:516-517`. Dropping the mode for OFF falls back to the pre-1.3 TQ4 path (≈ 0.35× prefill), which is
  not the shipped configuration's OFF state. B0 fixes it.
- Prompt allowance: with `max_tokens` 102,400 inside the 262,144 cap, the largest prompt with the full output budget is 159,744
  tokens (C89); above it the server resolves `min(max_tokens, cap − prompt)` and the thinking budget `0.8 ×` that
  (`convergence.resolved_thinking_budget`) — equal in both arms at equal prompt length.
- tg1 is saturated for this pick (P426 N16: 41–42 / 43 strict); tg2 (`docs/specs/m65-tg2-corpus.md` v5, C168 / C169) is built and
  its graders tested, never run on the GPU (C169: no tg2 GPU run without the operator's go — given by C323); planning
  discordance same-config p_d = .182 (M55), decider MDE ≈ 14 pp.

## 4. Decisions folded in (C323, 2026-11-11; S22-P1 … P11)

| id | decision |
|---|---|
| S22-P1 | Wave 1 gains A5, a long-context ladder (retrieval + chain-4 reasoning) — the KV lever's most exposed region |
| S22-P2 | M70 folded into stage 1: the instability rule's absolute floor 0.02 (S18-P13), red tests on the two observed cells |
| S22-P3 | stage 4 runs only `m72_v1` legs, paired against stage 3's `m72_exact` legs (same arm commit, items, seeds, build, fingerprint; any mismatch → `m72_exact` rerun); `m72_exact` ON ≡ TQ4 OFF in tokens at the tested cells, so stage 4 (V MTP ON vs X MTP ON) reads `m72_v1`'s lossy verify against the exact one, the C319 lossy-lever certification; [r1] an X tier-2 leg is added when stage 4 needs paired coverage stage 3 did not collect (the funnel's "extra coverage on older subjects") |
| S22-P4 / P5 / P6 | the comparison stays paired and outcome-graded (`acc_strict@budget`); literal output identity is never required |
| S22-P7 | per mechanical axis: point estimate drop ≤ 5 pp (absolute) AND observed loss bound ≤ 10 pp (C173) |
| S22-P8 | tg1 gains session s3 (seed 3003); the M76 loss-bound statistic for an agentic axis is the two-stage cluster bootstrap over items with the sessions as draws (`bench.stats` clustering; per-session results still reported, never replaced); Math500 grows to 300 items (nested: the first 100 are P426's) |
| S22-P9 | a noise-floor diagnostic: N16 s1 vs N16 s2 discordance on the same items beside every TQ4-vs-N16 discordance; never decides |
| S22-P10 | B0: the production fix that serves `tq4_attention` with MTP OFF (PLAN M77) |
| S22-P11 | tg2 joins as the second agentic axis (hard tasks, not saturated) |

Operator directive (C323): a **funnel** — collect only as much evidence as discriminates the subjects, add coverage (to both arms of a
pair, the incumbent included) only where a look leaves an axis undecided, within reason; every quality leg in the fastest
certified configuration (MTP ON, both arms); GPU time is the binding resource. §8 implements it.

## 5. Builds (test-first; red before green; four-eyes light per C322 unless marked; no GPU leg before its build is accepted)

**B0 — production: `tq4_attention` with MTP OFF (PLAN M77; fork + mlx-serve).** mlx-serve accepts `tq4_attention` with
`mtp_verify_scan` absent and no drafter (still requires `kv_bits: 4`, `turboquant`, `attention_policy: fused_v1`); the fork's
`tq4_attention.require_environment` accepts scan absent (no verify happens; plain decode L = 1 → `d2` / `single_pass`, prefill
`p2s` / `mma_prefill`, layer 63 `fused_v1` / SDPA decode); `mtp_verify_scan.require_environment` unchanged (it still refuses
`joint_v1` without `draft_kind: mtp`); [r1] `tq4_attention.require_policy_stamps` (`:345-357`, every full-attention module must
carry `joint_v1`) accepts an absent verify stamp only when no drafter is loaded, still requiring `fused_v1` on every module; a
served XO load-to-READY test. [r2] Plumbing: the CONFIGURED drafter state (`draft_kind` from the CLI / env) is passed into
`_resolve_tq4_mode_from_env` / `require_environment` and `_apply_tq4_attention_from_env` / `require_policy_stamps`
(`server/generation.py:204-245`, `:1569-1586`; today neither receives it, and an absent scan reads as `per_query`): configured
MTP ON requires `joint_v1` stamps exactly as today; configured OFF requires scan absent (`per_query`) and no verify stamp; the same
invariant is re-asserted after the drafter loads. Red tests: mode + drafter + no scan still refused; mode + drafter + `joint_v1`
unchanged; mode + no drafter + `joint_v1` refused; X and XO load to READY. Red tests: the refusal today (both repos), then served OFF argv carries `--tq4-attention`
without `--mtp-verify-scan` / `--draft-*`; route counters move `p2s`, `d2`, `native:prefill`, `native:decode`, `fallback:*` = 0;
greedy TQ4 OFF with the mode = greedy TQ4 MTP ON `m72_exact` on the A4 (c) prompts (the identity C319 claims, now across
configurations). Fork gate, mlx-serve gate, push ask per repository, gitlink bump with the stack companions (P632
`LIVE_GITLINKS`, `bench.arm_identity` classes — no new flag, skip baseline), stack gate.

**B1 — `bench.p475_kv` for this pick.** `p475_kv.py:27-28` `PICK` / `PICK_SHORT`, `:29` `ARMS`, `:30` `BASE_ARM = "TQ4"`,
`:34` `SMOKE_ARMS`, `:45` `LEG_RE`, `:47` `LEG_ESTIMATE_MIN`, `:56` the OFF edit, `:108` branch names, `:363` the edit regex,
`:378-411` `arm_registry_text` / `_allowed_added` / `removable` become per-pick tables: `u4` byte-identical to today (its tests
unchanged), `f45` new — base arm N16, arms of §6; the edit model may ADD the `tq4_attention` line (R1: the arm diff ⊆ the arm's
keys + the `# PROVISIONAL M76 arm <ARM>` comment) and comment `mtp_verify_scan` on the OFF arm (`:787` already requires no
`--mtp-verify-scan` on OFF). `kv_line.py`: `ARM_FORMATS` gains the mode; the mode is proved from the worker's `/health`
`tq4_attention: {mode, route_counts}` (`mlx_vlm/server/app.py:1241-1244`) read after load and after the driver (absent on N16;
`mode` equal to the arm's; counters moved on the expected routes, `fallback:*` = 0 — any other value INVALID) and from the
self-test stderr line (`server/generation.py:238-243`) as a secondary record. The instability rule (R16) gains S22-P2's floor.
`run_capacity --p475-strict` needs no change. Preflight: B2's `qualify --kv-arm`. [r1] Campaign scoping: scratch / state
(`$STACK_WORKDIR/p475`, `state.json`), dossiers, harvest paths and the matrix output become per-campaign (`p475` for `u4`, `m76`
for `f45`: `$STACK_WORKDIR/m76/p475/…`, `benchmark/results/m76/matrix/…`); golden tests pin the `u4` paths, receipts and
`MATRIX.Qwen3.8-27B-mlx-uniform-4bit.md` byte-identical.

**B2 — fork dev tools (fork commit, push ask, gitlink bump; no production change).** `dev/p369_phase2/qualify.py:30-50` `SERVING`
gains `tq4_attention` (`--tq4-attention`, non-empty); `registry_states.py:266` `KV_ARM_KEYS` + the mode, `:271-277` `KV_ARM_ROWS`
gains `TQ4X` / `TQ4V` (kv_bits 4, turboquant, mode) for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` only; `classify_kv_arm`
restores the mode key; the OFF derivation (`qualify.py:60`, `:108`) strips the three MTP keys and keeps the mode (servable after B0);
`fingerprint_of` (`:1709-1720`) and the report record the mode. P369 [r1]: a campaign-tuple identity beside the model key (`PICKS` stays keyed by model for the existing native16 tuple, unchanged;
a new `TUPLES["m76-x"]` = `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, `kv=tq4`, `joint_v1`, `m72_exact`, own item bundle);
`prepare` (`:2177-2182`, `:596-603`) under that tuple validates the committed X (ON) and XO (OFF) arm commits through
`classify_kv_arm` instead of `classify` / the MTP-OFF-root rule / `overlay_on` (no overlay: ON and OFF are both commits); `worker.py:1143-1149` also asserts the `tq4_attention` hook objects unchanged across the triple; the production pin
(`orchestrate.PRODUCTION`, `:33`) re-resolved to the B0 fork commit. `kvmanifest.expected_manifest` already keeps the last
full-attention layer native (`:153-165`). [r1] M1: `qualify --kv-arm --predictor on` with a non-empty KV delta (refused today,
P475a v4.1) runs a full (certifying) measurement only when bound to the stage-2 PASS record of the same arm commit and its exact
committed argv; otherwise it stays refused. [r1] Existing consumers: `classify`, `classify_kv_arm`, `fingerprint_of` and the
report are byte-identical for every existing pick / arm (golden tests pin today's `Qwen3.8-27B-mlx-uniform-4bit` and native16
fingerprints and report bytes, written and green BEFORE the change so any drift fails them [r2]); the mode field is emitted only when present. Fork suite ×2, audits.

**B3 — P426 lever mode + build label `s3` (stack).** A `lever` parameter, `mtp` (today, byte-identical, tests unchanged) or `kv`:
the allowed registry delta `{kv_bits, tq4_attention}` + the arm comment, the allowed argv delta `{--kv-bits, --tq4-attention}`,
both arms predictor `mtp` — `p426_leg.py:29`, `:58-64`, `:110-150`, `:285-305`; `p426_receipt.py:23-25`, `:248-249`;
`p426_freeze.py:91-100`; `p426_verify.py:41`, `:474-476`, `:579`, `:956`; `p426_wave2.py:97`; `p426_plan.py:30-35`
(no seeding hunk under `kv`); `registry_states.overlay_on` bypassed (arms are commits). `EXPECTED_BUILDS` (`p426_plan.py:21-24`)
gains `s3` = the B0 / B2 fork commit, mlx-serve commit, production ref, mlx 0.32.4; `p426_verify.py:587` arm-path regex,
`p426_panel.py:339` `A7_BUILD`, `p426_freeze.py:358`, `:569-576` follow the label. Namespaces `m76-<arm>-…`, results
`benchmark/results/m76/`. Signals (`p426_signals*`; [r1] not this spec's B6): §8's rule, looks and noise floor; labels "TQ4 − N16" / "V − X".
`bench.arm_identity`: no change (verified).

**B4 — tg2 legs in P426 lever mode.** The P426 chain (`run_tg1_chain.py --p426`, B2 of P426) runs the tg2 universe
(`benchmark/m65/tg2_draw.json`, sha-verified, nested tier prefixes; screen 10 / language, decider 20 / language) with the tg2
graders (`tg2_grade`, `tg2_materialize`); C169's injected positives and a tg2 smoke (N16, 4 items, one per language) VALID before
any measured leg.

**B5 — Wave 1 extensions.** `benchmark/results/m76/ids.json`: Math500 300 (the first 100 = `p426/ids.json` A1, then 200 by
`random.Random(7601)` over the remaining 400, nested blocks by the P426 seed-426 split), A2 / A3 / A4 as P426; A5 (§7). Runner
argv as P426 §5. [r1] A5: the C89 instruments (`docs/specs/native16-depth-qualification.md`: multi-needle retrieval, five codes at
10–90 % depth; chain-4 variable tracking), seeded prompts frozen in `ids.json` (seed 7605) with their token counts checked
offline; a P426 wave-1 axis `longctx` (`p426_wave1.AXES`, `p426_plan.plan_leg`), its pair-verifier adapter, signals section and
panel adapter (both-correct pairs), red tests as the existing axes'. A4 keeps its P426 panel role. B4 adds the A8 panel packet
(task, final tree diff, transcript summary) as tg1's.

**B6 — S21-P10 audit (CPU, no build).** Every shipped client path (OpenWebUI, opencode, aider, VS Code, Zed, Claude Code / Codex
headers) classified `cached_session` vs continuous batching from code + one request each on the lean router at smoke time; any
path that reaches batching is listed for the operator before publish (it serves the pre-1.3 TQ4 batch path, ≈ 0.35× prefill).

**B7 — statistics for §8 [r1, r2].** `bench.stats`, additive (every existing function and output byte-identical; goldens first):
- `paired_delta` gains two independent parameters, `interval_alpha` (two-sided; default 0.05 → the 2.5 / 97.5 percentiles of
  today) and `exact_alpha` (one-sided; default 0.05 → today's `1 − 0.05^(1/n)`); M76 passes the spent one-sided α to both
  (interval_alpha = 2 × spent α).
- A new `paired_session_delta(a, b)` keyed by (item id, session id): both arms must carry the identical session set per item
  (else refused); resamples items, then keeps the item's session-difference vector d_s = X_s − N16_s together (C324);
  per-session paired deltas with 95 % intervals reported beside it. `paired_delta`'s independent within-item resampling is
  untouched (its consumers have independent draws).
- Per-axis Lan–DeMets O'Brien–Fleming spending in code from the pre-registered information fractions.
- A CPU simulation of the whole §8 rule per axis, data model pre-registered: per-item pass probabilities drawn from a beta fitted
  to the axis's stored N16 rows (P426 S′ A1 / A7; M55 for tg2; C89 for A5), a per-session random effect on the logit scale
  (SD 0.25, sensitivity 0 and 0.5), the planning discordance fixed per axis (tg1 0.10, Math500 0.06, A5 0.05, tg2 0.182), true
  loss 0 / 5 / 10 / 12 pp, ≥ 20,000 replications with Monte Carlo 95 % intervals. A look is kept only if (a) the PASS probability
  at loss 0 is ≥ 0.5 and (b) the upper Monte Carlo bound of the false-PASS rate at loss 10 pp is ≤ 0.025 (the one-sided α); a
  look failing (b) is dropped (the axis then runs full size with one look) or recalibrated, never kept as is. The same check
  (b) is asserted for every axis's final look, including A5 and the tg2 decider. Red tests assert (b) on the shipped code for
  each axis; the report (power and error per axis and look, the resulting plan, A5's size per §7) goes to the operator with the
  stage-3 Go.

## 6. Arms (stack commits on base = the stack commit carrying B0–B7; local branches `m76-<arm>`; worktrees under
`$STACK_WORKDIR/worktrees/m76-<arm>`, prepared as P426 arm worktrees; each removed once its legs are harvested)

| arm | entry keys changed from the base | predictor | stages |
|---|---|---|---|
| N16 | none (the base = the shipped entry) | MTP ON | 1, 3 |
| X | `kv_bits: 4`, `tq4_attention: m72_exact` | MTP ON | 1, 2, 3 |
| V | `kv_bits: 4`, `tq4_attention: m72_v1` | MTP ON | 1, 4 |
| XO | X + `draft_kind`, `draft_model`, `mtp_verify_scan` commented | OFF | 1, 2 (C2 cross-load OFF) |

`kv_quant_scheme: turboquant` is already in the entry; `quantized_kv_start` 0; nothing else changes (R1 / B3 verify it).

## 7. Stages

**Stage 0 — preflights and smokes.** Per arm: `qualify --kv-arm` (OFF) and the engagement check (ON arms); P475 smokes N16 and X
(grid 8192); the real-data A1 of S20-P18 rerun on the production path (`benchmark/spikes/m72_p2s_realact.py` through
`maybe_quantize_kv_cache`, layers 3 … 59, 131,072 tokens; descriptive, carried to stage 3's reading per C316); the B6 audit.

**Stage 1 — served speed / memory matrix (`bench.p475_kv`, pick `f45`).** Grid 8,192 / 131,072 / 196,608 / 260,096; block 1
N16 → X → V → XO, block 2 the reverse; each leg a fresh lean router from its arm worktree; ≥ 600 s idle; every P475 v4 / stage-1
contract rule (R1–R22) plus B1's mode proof. Output `benchmark/results/m76/MATRIX.md` (generated): cumulative peak GB, backend
prefill tok/s, decode tok/s, acceptance, route counters per leg; ratios vs N16 and V / X; instability with S22-P2's floor (one
deciding block under the cap). Readings (pre-registered, descriptive): X vs N16 memory / prefill / decode (the accepted gain is
memory); X vs XO = TQ4 MTP ON vs OFF speed and memory (C204); **stage-4 trigger:** V / X decode ≥ 1.05 at 131,072 and at 260,096
in both blocks, no unresolved instability flag (≈ 2.5× the 0.02 floor); else stage 4 is not run and `m72_v1` is reported as "no
in-situ decode gain shown".

**Stage 2 — `m72_exact` exactness at scale (P369 phase 2 E1c + E2 on arm X; the C258 basis).** Same-instance triple (ON, OFF1,
OFF2 with the drafter detached) and control C1 as P369 §2.5; C2 cross-load OFF = arm XO's deployed argv (B0). E1c cells: straddles
at the TQ4 routing thresholds (verify `lengths[0]` around 2,048; the D2 block-count tier above 65,536) and the native layer-63
MLX thresholds (1,024 / 8,192 / 32,768 / 65,536), plus scale cells at 131,072 and 260,096; deployed sampling, fixed seeds,
160 tokens. E2: the 20 C84 items (reconstructed for the TQ4 tuple) at T = 0, 512 tokens, plus the straddle and scale prompts
(160 tokens). Engagement: `d2_verify` > 0 and `fallback:*` = 0 on every ON trajectory. Verdict precedence as P369 (C1 fail →
ABORT; ON ≠ OFF1 → FAIL with the measured bound → operator; else PASS). The smoke calibrates the 260,096-cell hashing cost; if the
revised stage estimate exceeds 8 h, that cell goes to the operator before the full run. [r1] Claim wording: "MTP ON equals plain
decoding on the same loaded instance at the tested cells — transformed target distributions (E1c, 160 tokens) and greedy tokens
(E2, 512 / 160 tokens)"; nothing beyond the tested positions. [r2] **On FAIL**, stage 3 waits for the operator with the measured bound: stage 3 still measures
the candidate in its shipped state (X MTP ON vs N16 MTP ON), but the C258 basis for skipping X's ON-vs-OFF quality certification
(C204) is gone — the options are to run stage 3 as planned and certify X ON vs OFF separately (a spec amendment), or to halt.
**On ABORT** (C1 failed: an instrument failure, not an X result) stage 2 is diagnosed and repeated.

**Stage 3 — quality X vs N16 (both MTP ON; P426 lever `kv`, build `s3`).** Axes:

| id | axis | tier 1 (always) | tier 2 (only if look 1 leaves it undecided) | role |
|---|---|---|---|---|
| A1 | Math500 | 100 items (P426 ids), two blocks — or all 300 if §8's look rule drops look 1 | +200 (to 300) | mechanical |
| A2 | cjudge | 40 | — | panel only |
| A3 | vision gate | 20 | — | self-pass (lenient) + panel |
| A4 | reasoning depth 128K | 6 draws (P426 seeds) | — | descriptive + panel (P426) |
| A5 [r1, r2] | long context: retrieval (5 codes / prompt, all-five exact) + chain-4 (exact) | n prompts (40 ≤ n ≤ 80, set by B7's simulation so that PASS at no loss has probability ≥ 0.8 at p_d 0.05), half retrieval, half chain-4, over rungs 131,072 / 159,744 (full budget) and 196,608 (resolved budget 65,536, equal between arms); task and rung as strata; one look at one-sided α 0.025 (zero discordance at n = 40 → exact bound 8.8 pp) | — | mechanical; gates per task (retrieval, chain-4; pooled over rungs): each arm's accuracy ≥ 0.85 (AGENTS.md effective context) and the per-task point estimate ≥ −5 pp; per rung × task descriptive |
| M1 | memory at 256K (`qualify`, in-process) [r1] | both arms MTP ON, legs N16 / X / X / N16 (B2's binding) | — | memory |
| A7 | tg1 (43) | pilot, s1 (1001), s2 (2002), reload — plus s3 if §8's look rule drops look 1 | s3 (3003) | mechanical, agentic |
| A8 | tg2 | SCREEN 40 (k = 1; C168: diagnostic, not a look) | DECIDER 80 (k = 2 + reload) on a material screen finding; one formal look at 95 % | agentic, hard tasks |

Order and validity as P426 §3 (two blocks, OFF↔ON replaced by N16↔X: block 1 N16 → X, block 2 X → N16; seeded item split 426;
fresh load per leg; ≥ 10 min idle). Panel (C161 / C206): Claude Opus via Claude Code + a Cursor model of another family (default
GPT-5.6 Sol; images: Gemini 3.1 Pro), blind pairwise, both orders, length-adjusted, over execution-passing pairs (A1 both-correct,
A2 all, A3, A4 strict draws, A5 both-correct, A7 / A8 both-pass items per session). Tests and Holm families as P426 §8 with X − N16; A8 screen
outside the families (diagnostic).

**Stage 4 — conditional: V vs X** on stage 3's tiers and axes (A1, A2, A3, A5, A7, A8 screen; M1, A4 descriptive): V legs,
paired with stage 3's X legs (S22-P3; the pair verifier checks everything but the mode key / flag); [r2] where stage 4's tier 2 needs
coverage stage 3 did not collect, the added items run on all three arms (N16, X, V; paired, budgeted in §9). Reuse of stage 3's X
legs is licensed by a sentinel at stage 4's start: (a) equality of every pinned identity (stack / fork / mlx-serve commits, venv
inventories, grader docker image digests, opencode version and config hash, frozen prompt date, fingerprint); (b) one reused item
per axis family re-run on X with its stage-3 seed — single-turn axes (A1, A5) must reproduce the stage-3 output exactly; agentic
axes (A7, A8) by P640's criterion (every assistant message generated before the first context divergence identical; tool-output
timestamps / mtimes are context, not model change). Any (a) or (b) failure → X reruns with V in order-balanced blocks on the
affected axes (budgeted as the worst case). V MTP ON vs OFF exactness is not claimed (S21-P9). [r1] V is read against both X (the lever) and N16
(the incumbent; free, same items): recommend V only when V − X and V − N16 both PASS. Speed for V comes from stage 1; stage 4's
per-axis decode is descriptive (not order-balanced against X).

## 8. Decision rule and the funnel (pre-registered) [r1 rewrite]

- **Statistic per mechanical axis:** paired `acc_strict@budget` difference (X − N16; stage 4 V − X and V − N16), DNF included,
  bootstrap over items (10,000 resamples, seed 426; strata for A5); agentic axes with several sessions use `paired_session_delta`
  (B7; S22-P8 / C324); per-session deltas with their own 95 % intervals reported beside it; [r2] session-disagreement flag:
  for any pair of sessions that ran, the two point estimates have opposite signs AND each session's 95 % interval excludes the
  other's point → flagged to the operator (a PASS keeps the flag beside it).
- **Loss bound:** −(lower bound of the two-sided interval at 1 − 2α); a zero-discordance cell uses the exact bound `1 − α^(1/n)`
  at the same one-sided α (B7) [r2]. Total one-sided α = 0.025 per axis (the 95 % two-sided interval C173 uses; the existing
  code's 0.05 exact bound is not used by M76).
- **Looks:** an axis with a tier 2 has two looks; α is spent per axis by O'Brien–Fleming (Lan–DeMets) at its pre-registered
  information fraction (Math500 t₁ = 1/3 → look-1 interval ≈ 99.9 %; tg1 t₁ = 2/3 → ≈ 98.4 %), computed by B7. **A look is kept only
  if B7's simulation gives it a PASS probability ≥ 0.5 at true loss 0 and keeps the false-PASS rate at a 10 pp loss within α**
  (planning discordance fixed: tg1 0.10, Math500 0.06) [r2];
  otherwise that axis runs its full size in tier 1 (Math500 300; tg1 s1 + s2 + s3) with one look at 95 %. The simulation report
  and the resulting per-axis plan go to the operator with the stage-3 Go. A5 and A8 have one look each.
- **Verdict per axis at a look (mutually exclusive, in this order):** PASS — point estimate ≥ −5 pp AND loss bound ≤ 10 pp (if the
  interval also excludes 0 with N16 better, PASS carries the annotation "loss shown, within tolerance (X pp)"); LOSS — point estimate
  < −5 pp with the interval excluding 0 → flag to the operator, no tier 2; UNDECIDED — anything else → tier 2 at a kept look 1,
  "loss not ruled out above X pp" → operator at the final look. A wash is labelled "directional (not a shown difference)" (C172).
- **A8 tg2:** the screen is a trigger, not a look (C168: diagnostic): a material finding = macro-average point estimate < −5 pp or any
  language < −15 pp → the decider, read by the rule above at 95 %; the decider's large-harm HOLD (m65 spec) stands. A clean screen
  is reported as "no material finding (not safety evidence)". Expected decider resolution: bound ≈ 10–12 pp (p_d .182) — reported as
  measured.
- **Panel:** per family Holm (subjective family: A1, A2, A3, A4, A5, A7 sessions, A8 if the decider runs; members with < 5 judged
  items reported, not tested); Holm-adjusted p < .05 favouring N16 → flag. A2 / A3 / A4 have no mechanical verdict.
- **Noise floor (S22-P9):** for A7 (and A8's decider) the N16 s1-vs-s2 (and s3) discordance on the same items is printed beside
  X-vs-N16's; diagnostic only. (Math500 / A5 blocks hold disjoint items, P426 §3, so they have no within-arm repeat.)
- **Recommendation to the operator:** ship X when every mechanical axis (A1, A5 incl. its per-task gates, A7, and A8's decider if
  run) is PASS, no panel flag, no session-disagreement flag, stage 2 PASS and stage 1 shows the memory gain; otherwise the per-axis signals with the lead's recommendation (C204: the
  operator's call). Stage 4 as §7.
- **Funnel cost rule:** tier 2 runs per axis, both arms (the incumbent gets the same added coverage, paired); nothing beyond tier 2
  without the operator; every quality leg MTP ON (stage 2 PASS supports skipping MTP-OFF quality legs for X at the tested cells,
  the C258 precedent; on stage-2 FAIL see §7).

## 9. GPU budget and ETA (lower bounds from P426 S′ MTP-ON walls and P475 legs; X assumed ≈ 1.05× N16 walls; [+30 %])

| stage | expected path | worst case (all tier 2) |
|---|---|---|
| 0 preflights, smokes, real-data A1 | ≈ 2 h | ≈ 3 h |
| 1 matrix (8 legs + idles; deciding block) | ≈ 7–8 h | ≈ 11 h |
| 2 exactness (P369 ≈ 3.5 h + scale cells) | ≈ 6–7 h | ≈ 8 h (else operator) |
| 3 tier 1 (Wave 1 ≈ 3.3 h + A5 ≈ 4 h [unmeasured], tg1 ≈ 5.7 h, tg2 screen ≈ 3 h [unmeasured] per arm; × 2; smokes, idles) | ≈ 37 h | — |
| 3 dropped looks (§8; likely for Math500 and tg1: Math500 +200 ≈ 2.5 h, tg1 s3 ≈ 2.7 h per arm; × 2) | ≈ 10 h | ≈ 10 h |
| 3 tier 2 (tg2 decider ≈ 12 h per arm [unmeasured]; Math500 / tg1 only where a look is kept and undecided) | 0 h | ≈ 24 h |
| 4 (V; N16 + X added where its tier 2 needs it; sentinel ≈ 1 h; X rerun on sentinel failure) | ≈ 18 h or 0 (trigger) | ≈ 70 h |
| total | ≈ 80–83 h [≈ 105 h] | ≈ 165 h [≈ 215 h] |

CPU [r2]: B0 ≈ 0.5 day, B1 ≈ 1, B2 ≈ 1, B3 ≈ 1.5, B4 ≈ 1, B5 ≈ 1, B7 ≈ 1 (four-eyes light each; gates and push asks between) —
≈ 7 build-days, ≈ 4–5 calendar days with builds in parallel. **Sequencing keeps the GPU busy:** B0 + B1 + B2 first → stages 0, 1
and 2 run on the GPU while B3, B4, B5 and B7 are built (never a gate during a measured leg). Calendar: ≈ 3–4 days of box time
on the expected path after the builds. Estimates are recalibrated from each smoke and reported at each look. [r1] A5 and tg2 walls are unmeasured: a timed smoke (one A5
prompt per rung, one tg2 item per language, both arms) recalibrates them before stage 3's Go.

## 10. Publish (only after the operator's pick approval)

Registry entry `kv_bits: 4` + `tq4_attention: <mode>` with `CERTIFIED M76 <date>` (KV / mode) beside the C291 MTP annotation;
`bench.provenance` fingerprint as served; README ranking / evidence tables (memory, speed, per-axis quality with intervals, coverage
labels); `docs/campaign-results.md`; no client sampling change (structural: registry → worker); client carriers audited for drift;
the B6 batching list; stack gate; push ask.

## 11. Acceptance (of the spec's execution)

1. B0–B7 accepted with their red-first tests (B7's simulation report delivered); gates PASS; pushes approved.
2. Stage 1 `MATRIX.md` complete (two speed-valid legs per arm), the mode proven on every TQ4 leg.
3. Stage 2 verdict recorded (PASS / FAIL with bound / ABORT).
4. Stage 3 (and 4 if triggered) signals generated per §8, every axis with a verdict, coverage labelled.

## 12. Non-goals and residuals

`Qwen3.8-27B-mlx-uniform-4bit` (shipped as is, C309); kernel changes; the daily-driver `MLX_VLM_CACHE_SESSION_MAX=2` memory
(reported from stage 1 by arithmetic only); the 1.3 residuals in the handoff (stale `_TQ4_MANIFESTS` entry per router port, exit
route-counter snapshot only in the manifest-gathering process, the verifier's local rebinding, the dev scratch harness I1 hazard);
M73 (the generic sequential-stopping build; §8 is this run's pre-registered two-look instance, written so M73 can absorb it).
