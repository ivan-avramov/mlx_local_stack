# M76 (M72 1.4) — certify `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` on TurboQuant 4 KV + `tq4_attention` + MTP ON — SPEC v1, 2026-11-11

Authority: C322 (Go, stages 1–4, memory is the accepted gain), C319 (`m72_exact` beside `m72_v1`; `m72_v1` certified as a lossy
lever), C318, C321 (1.3 accepted), C204 / C206 (predictor and panel rules), C172 / C173 (wash and loss-bound rule), C218 (arms are
stack commits), C233 (measure in the shipped MTP-ON state), C258 (the P369 exactness basis for a TQ4 MTP-ON pick), C291 (the shipped
N16 pick), C168 / C109 (k = 2 loaded instances), S20-P18 / C316 (real-data A1 carried here), S21-P2, S21-P10, AGENTS.md.
Cold design review (strict): round 1 of 3 pending. Harness adapters: four-eyes light (C322).

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
  accepts a `tq4_attention` arm today. `bench.arm_identity` already hashes `--tq4-attention` (`28235601`).
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
| S22-P3 | stage 4 runs only `m72_v1` legs, paired against stage 3's `m72_exact` legs (same arm commit, items, seeds, build, fingerprint; any mismatch → `m72_exact` rerun); `m72_exact` ON ≡ TQ4 OFF in tokens, so stage 4 is `m72_v1` MTP ON vs OFF, the C319 lossy-lever certification |
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
`joint_v1` without `draft_kind: mtp`). Red tests: the refusal today (both repos), then served OFF argv carries `--tq4-attention`
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
`run_capacity --p475-strict` needs no change. Preflight: B2's `qualify --kv-arm`.

**B2 — fork dev tools (fork commit, push ask, gitlink bump; no production change).** `dev/p369_phase2/qualify.py:30-50` `SERVING`
gains `tq4_attention` (`--tq4-attention`, non-empty); `registry_states.py:266` `KV_ARM_KEYS` + the mode, `:271-277` `KV_ARM_ROWS`
gains `TQ4X` / `TQ4V` (kv_bits 4, turboquant, mode) for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` only; `classify_kv_arm`
restores the mode key; the OFF derivation (`qualify.py:60`, `:108`) strips the three MTP keys and keeps the mode (servable after B0);
`fingerprint_of` (`:1709-1720`) and the report record the mode. P369: `orchestrate.py:43-44` `PICKS` gains a TQ4 tuple for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`
(`kv=tq4`, `joint_v1`, mode) selecting its own item bundle; `prepare` (`:2177-2182`, `:596-603`) accepts an M76 arm commit as the
stack root; `worker.py:1143-1149` also asserts the `tq4_attention` hook objects unchanged across the triple; the production pin
(`orchestrate.PRODUCTION`, `:33`) re-resolved to the B0 fork commit. `kvmanifest.expected_manifest` already keeps the last
full-attention layer native (`:153-165`). Fork suite ×2, audits.

**B3 — P426 lever mode + build label `s3` (stack).** A `lever` parameter, `mtp` (today, byte-identical, tests unchanged) or `kv`:
the allowed registry delta `{kv_bits, tq4_attention}` + the arm comment, the allowed argv delta `{--kv-bits, --tq4-attention}`,
both arms predictor `mtp` — `p426_leg.py:29`, `:58-64`, `:110-150`, `:285-305`; `p426_receipt.py:23-25`, `:248-249`;
`p426_freeze.py:91-100`; `p426_verify.py:41`, `:474-476`, `:579`, `:956`; `p426_wave2.py:97`; `p426_plan.py:30-35`
(no seeding hunk under `kv`); `registry_states.overlay_on` bypassed (arms are commits). `EXPECTED_BUILDS` (`p426_plan.py:21-24`)
gains `s3` = the B0 / B2 fork commit, mlx-serve commit, production ref, mlx 0.32.4; `p426_verify.py:587` arm-path regex,
`p426_panel.py:339` `A7_BUILD`, `p426_freeze.py:358`, `:569-576` follow the label. Namespaces `m76-<arm>-…`, results
`benchmark/results/m76/`. Signals (B6 / `p426_signals*`): §8's rule, looks and noise floor; labels "TQ4 − N16" / "V − X".
`bench.arm_identity`: no change (verified).

**B4 — tg2 legs in P426 lever mode.** The P426 chain (`run_tg1_chain.py --p426`, B2 of P426) runs the tg2 universe
(`benchmark/m65/tg2_draw.json`, sha-verified, nested tier prefixes; screen 10 / language, decider 20 / language) with the tg2
graders (`tg2_grade`, `tg2_materialize`); C169's injected positives and a tg2 smoke (N16, 4 items, one per language) VALID before
any measured leg.

**B5 — Wave 1 extensions.** `benchmark/results/m76/ids.json`: Math500 300 (the first 100 = `p426/ids.json` A1, then 200 by
`random.Random(7601)` over the remaining 400, nested blocks by the P426 seed-426 split), A2 / A3 / A4 as P426; A5 (§7). Runner
argv as P426 §5.

**B6 — S21-P10 audit (CPU, no build).** Every shipped client path (OpenWebUI, opencode, aider, VS Code, Zed, Claude Code / Codex
headers) classified `cached_session` vs continuous batching from code + one request each on the lean router at smoke time; any
path that reaches batching is listed for the operator before publish (it serves the pre-1.3 TQ4 batch path, ≈ 0.35× prefill).

## 6. Arms (stack commits on base = the stack commit carrying B0–B5; local branches `m76-<arm>`; worktrees under
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
revised stage estimate exceeds 8 h, that cell goes to the operator before the full run.

**Stage 3 — quality X vs N16 (both MTP ON; P426 lever `kv`, build `s3`).** Axes:

| id | axis | tier 1 (always) | tier 2 (only if look 1 leaves it undecided) | role |
|---|---|---|---|---|
| A1 | Math500 | 100 items (P426 ids), two blocks | +200 (to 300) | mechanical |
| A2 | cjudge | 40 | — | panel only |
| A3 | vision gate | 20 | — | self-pass (lenient) + panel |
| A4 | reasoning depth 128K | 6 draws (P426 seeds) | — | descriptive |
| A5 | long context: retrieval (5 codes / prompt) + chain-4 | 5 prompts per rung at 131,072 and 159,744 (full budget); 196,608 and 260,096 (resolved budget, equal between arms; reported apart) | +5 prompts per rung | mechanical (per rung, exact-match) |
| M1 | memory at 256K (`qualify`, in-process) | OFF / ON order as P426 | — | memory |
| A7 | tg1 (43) | pilot, s1 (1001), s2 (2002), reload | s3 (3003) | mechanical, agentic |
| A8 | tg2 | SCREEN 40 (k = 1; C168: diagnostic) | DECIDER 80 (k = 2 + reload) on a material screen finding | agentic, hard tasks |

Order and validity as P426 §3 (two blocks, OFF↔ON replaced by N16↔X: block 1 N16 → X, block 2 X → N16; seeded item split 426;
fresh load per leg; ≥ 10 min idle). Panel (C161 / C206): Claude Opus via Claude Code + a Cursor model of another family (default
GPT-5.6 Sol; images: Gemini 3.1 Pro), blind pairwise, both orders, length-adjusted, over execution-passing pairs (A1 both-correct,
A2 all, A3, A5 both-correct, A7 / A8 both-pass items per session). Tests and Holm families as P426 §8 with X − N16; A8 screen
outside the families (diagnostic).

**Stage 4 — conditional: V vs X** on stage 3's tiers and axes (A1, A2, A3, A5, A7, A8 screen; M1, A4 descriptive): V legs only,
paired with stage 3's X legs (S22-P3; the pair verifier checks everything but the mode key / flag). V MTP ON vs OFF exactness is
not claimed (S21-P9); the comparison is the lossy-lever read.

## 8. Decision rule and the funnel (pre-registered)

- **Statistic per mechanical axis:** paired `acc_strict@budget` difference (X − N16; stage 4 V − X), DNF included, two-stage cluster
  bootstrap (items, then draws; 10,000 resamples, seed 426); agentic axes with the sessions as draws (S22-P8); per-session results
  reported beside it, unchanged.
- **Looks:** look 1 after tier 1; look 2 (final) after tier 2, for the axes that entered it. Intervals O'Brien–Fleming for two
  looks: 99.4 % at look 1, 95.2 % at look 2 (z 2.797 / 1.977) — so a second chance to pass does not inflate the 5 % error; an axis
  decided at look 1 is final.
- **Verdict per axis at a look:** PASS — point estimate ≥ −5 pp AND loss bound (−interval lower bound; zero-discordance cells: the
  exact discordance bound) ≤ 10 pp; LOSS SHOWN — the interval excludes 0 with N16 better → flag to the operator, no tier 2 for
  it; UNDECIDED — otherwise → tier 2 at look 1, "loss not ruled out above X pp"
  → operator at look 2. A wash is labelled "directional (not a shown difference)" (C172).
- **A8 tg2:** the screen is diagnostic (C168): a material finding = macro-average point estimate < −5 pp or any language < −15 pp;
  it triggers the decider (tier 2), read by the rule above; the decider's large-harm HOLD (m65 spec) stands. A clean screen is
  reported as "no material finding (not safety evidence)". Expected resolution at the decider: bound ≈ 10–12 pp (p_d .182) —
  reported as measured.
- **Panel:** per family Holm; Holm-adjusted p < .05 favouring N16 → flag. A2 / A3 have no mechanical verdict; A4 descriptive.
- **Noise floor (S22-P9):** for A7 (and A8 if the decider runs) the N16 s1-vs-s2 discordance on the same items is printed beside
  X-vs-N16's; diagnostic only.
- **Recommendation to the operator:** ship X when every mechanical axis is PASS, no panel flag, stage 2 PASS and stage 1 shows the
  memory gain; otherwise the per-axis signals with the lead's recommendation (C204: the operator's call). Stage 4: recommend V over
  X only when every stage-4 axis is PASS and the stage-1 trigger held.
- **Funnel cost rule:** tier 2 runs per axis, both arms (the incumbent N16 gets the same added coverage, paired); nothing beyond
  tier 2 without the operator; every quality leg MTP ON (stage 2 is what licenses skipping MTP-OFF quality legs: `m72_exact` ON ≡ OFF).

## 9. GPU budget and ETA (lower bounds from P426 S′ MTP-ON walls and P475 legs; X assumed ≈ 1.05× N16 walls; [+30 %])

| stage | expected path | worst case (all tier 2) |
|---|---|---|
| 0 preflights, smokes, real-data A1 | ≈ 2 h | ≈ 3 h |
| 1 matrix (8 legs + idles; deciding block) | ≈ 7–8 h | ≈ 11 h |
| 2 exactness (P369 ≈ 3.5 h + scale cells) | ≈ 6–7 h | ≈ 8 h (else operator) |
| 3 tier 1 (Wave 1 + A5 ≈ 6.3 h, tg1 ≈ 5.7 h, tg2 screen ≈ 3 h per arm; × 2; smokes, idles) | ≈ 35 h | — |
| 3 tier 2 (Math500 +200 ≈ 2.5 h, tg1 s3 ≈ 2.7 h, tg2 decider ≈ 12 h per arm; × 2) | 0 h | ≈ 34 h |
| 4 (V only: tier 1 ≈ 17 h, tier 2 ≤ 17 h) | ≈ 17 h or 0 (trigger) | ≈ 34 h |
| total | ≈ 67–70 h [≈ 90 h] | ≈ 125 h [≈ 160 h] |

CPU before the first measured leg: B0 ≈ 0.5 day (+ gates), B1–B5 ≈ 2 days (four-eyes light), gates. Calendar: ≈ 3–4 days of box time
on the expected path after the builds. Estimates are recalibrated from each smoke and reported at each look.

## 10. Publish (only after the operator's pick approval)

Registry entry `kv_bits: 4` + `tq4_attention: <mode>` with `CERTIFIED M76 <date>` (KV / mode) beside the C291 MTP annotation;
`bench.provenance` fingerprint as served; README ranking / evidence tables (memory, speed, per-axis quality with intervals, coverage
labels); `docs/campaign-results.md`; no client sampling change (structural: registry → worker); client carriers audited for drift;
the B6 batching list; stack gate; push ask.

## 11. Acceptance (of the spec's execution)

1. B0–B5 accepted with their red-first tests; gates PASS; pushes approved.
2. Stage 1 `MATRIX.md` complete (two speed-valid legs per arm), the mode proven on every TQ4 leg.
3. Stage 2 verdict recorded (PASS / FAIL with bound / ABORT).
4. Stage 3 (and 4 if triggered) signals generated per §8, every axis with a verdict, coverage labelled.

## 12. Non-goals and residuals

`Qwen3.8-27B-mlx-uniform-4bit` (shipped as is, C309); kernel changes; the daily-driver `MLX_VLM_CACHE_SESSION_MAX=2` memory
(reported from stage 1 by arithmetic only); the 1.3 residuals in the handoff (stale `_TQ4_MANIFESTS` entry per router port, exit
route-counter snapshot only in the manifest-gathering process, the verifier's local rebinding, the dev scratch harness I1 hazard);
M73 (the generic sequential-stopping build; §8 is this run's pre-registered two-look instance, written so M73 can absorb it).
