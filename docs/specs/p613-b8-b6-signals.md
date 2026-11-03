# P613 — B8 pair verifier + B6 signals sheet for P426 — SPEC v0 (2026-11-03, for operator approval)

Authority: `docs/specs/p426-fable-mtp-recert.md` v4 §1 (attention flags), §3 (order balance / validity), §5–§8, §9 (B8, B6);
`docs/specs/p426-b2-tg1-wave2.md` §12 (contract to B8 / B6); C172, C173, C204, C217, C235 G1, C269, C273. Where this spec and
those disagree, those win; record the conflict here.

## 1. Scope

- **B8** `benchmark/bench/p426_verify.py`: decides which ON / OFF pairs are comparable. Fail closed. No statistics.
- **B6** `benchmark/bench/p426_signals.py`: generates `benchmark/results/p426/SIGNALS.md` + `SIGNALS.json` from committed files only,
  for B8-accepted pairs only. Deterministic (same inputs → byte-identical outputs). Never hand-edited.
- **Panel run** (uses the existing B3 `bench/p426_panel.py`, C207 judges): packet export + verdict collection for the subjective
  family. B6 reads verdicts; missing verdicts are counted, never imputed.
- Non-goals: new runs, regrading, changing any harvested byte, the ship decision (C204: the operator decides from the sheet).

## 2. Inputs (committed paths only; `$STACK_WORKDIR` never read)

| Axis | Legs / pairs | Rows / results | Receipts / records |
|---|---|---|---|
| A1 math500 | `p426s2-{off,on}-b{1,2}` | `benchmark/results/<entry>/math500.<tune>.jsonl` + `.score.json` | `benchmark/results/p426/wave1.s2/<leg>/<leg>.receipt.json`, `run/frozen.s2.json` |
| A2 cjudge | same tunes | `cjudge.<tune>.jsonl` (acc null: panel only) | same |
| A3 vision | same tunes | `vision_gate.<tune>.jsonl` | same |
| A4 reasoning | same tunes | `reasoning.<tune>.json` | same (descriptive axis) |
| M1 memory | `m1-p426s2-{off,on}-b{1,2}` | `wave1.s2/<leg>/m1/<entry>/result.json` | same |
| A7 tg1 | `wave2/` attempts pilot, s1, s2, reload | `<attempt>/<session>/*.jsonl` rows, `items/*.json` (totals, requests) | `<attempt>/{leg,receipt,chain,HARVEST}.json`, `pairs/*.json`, `run/v8_base.json` |

Smoke legs and every `wave2.v8-*` / `archive` namespace are excluded by name; B6 lists them under coverage only.

## 3. B8 — rules (each failure names the pair, the rule and both values)

Generic, every axis:
1. Both legs present, self-hash / receipt verdict VALID; a superseded or INVALID attempt is never a pair member.
2. Arm identity: OFF and ON differ by exactly the restore delta (Wave 1: the three C177 registry lines, the receipt worker argv
   `--draft-kind mtp --draft-model … --mtp-verify-scan joint_v1` present on ON, absent on OFF; Wave 2: `v8_base` arms, dossier
   `differences` ⊆ the allowed list). Everything else equal: sampling, budgets, KV, serving pins, item set, seed set, box.
3. Item / seed sets equal per pair key (A7: session, language, item, seed; Wave 1: tune block, item id, sample seed).
4. Speed eligibility separate from quality (§3 of the recert spec): a leg with `speed_valid != true` drops the block from speed
   inference only; one valid block → speed descriptive, labelled "not order-balanced".
5. A7 only: the pair's dossier exists, self-hashes and reads PASS, and names exactly the two attempts used; HARVEST.json of each
   attempt re-verifies (every published sha256).
6. C217 (panel only): a pair whose two output texts are byte-identical is excluded from judging and counted as a tie.

Output `benchmark/results/p426/B8.json`: per axis / session the accepted pairs, the rejected pairs with reasons, and the input
file sha256 set. B6 refuses if `B8.json` is stale against those shas.

## 4. B6 — signals (per axis; A7 per session s1 / s2, never pooled across sessions; reload diagnostic only)

- **Quality (mechanical):** `acc_strict@budget` per arm over ALL planned slots (DNF = non-success, labelled `transport_dnf`;
  budget-hit = fail), conv %, `nonconv_kinds`; paired ON − OFF with a two-stage cluster bootstrap 95 % interval (items, then
  draws; 10,000 resamples, seed 426) and the axis MDE. Mechanical family {A1, A7-s1, A7-s2}: paired sign-flip permutation test
  (10,000, seed 426, two-sided, zero differences contribute zero), Holm across the family.
- **Labels (C172 / C173):** interval excludes 0 → a shown difference; includes 0 → WASH, point estimate labelled "directional
  (not a shown difference)", plus the loss bound for a lossy lever (−CI lower bound; zero-discordance cells: the exact
  discordance bound) and "loss not ruled out above X pp" when > 10 pp.
- **Subjective:** from panel verdicts: per item score = mean over 2 judges × 2 orders (ON win 1, tie 0.5, OFF win 0),
  length-adjusted (C161 estimator, `p426_panel.length_adjusted`); family {A1, A2, A3, A7-s1, A7-s2} (members with < 5 judged items
  reported, not tested), same permutation test vs 0.5, Holm; judge model id / client version / prompt sha listed; missing verdicts
  counted per member; single-family members labelled (C166 / C206).
- **Memory (M1):** prefill / decode / retire `mx.get_peak_memory` peaks per leg, ON − OFF per block and both blocks; the 256K
  flags of §1.
- **Speed:** per item decode rate = Σ max(generated − 1, 0) ÷ Σ decode time over completed requests (A7: `items/*.json` totals;
  Wave 1: rows); paired per-item ON / OFF ratio, bootstrapped over items within each session / block; acceptance = Σ accepted ÷
  Σ proposed within the session; per-session wall. Request ordinals are never paired.
- **Runaway tax (A7, B2 §12 / C269):** budget-hit, turn-cap, exec-timeout, `client_inactivity` (own category, with each item's
  `client_abort` block), loop and stall kills, per arm and session, plus the per-session union; pooled rates descriptive. The C269
  sensitivity: the strict delta with and without pairs where either arm has a `client_inactivity` ending.
- **Noise floor (C273):** cross-attempt outcome-flip rate per arm (reload vs pilot; plus any committed repeated attempt of the same
  schedule and seeds, e.g. `wave2.v8-4104c7fc` vs `wave2`), with the counts it rests on.
- **Coverage:** legs done / pending / invalid / superseded per axis; smokes listed, never scored.
- **Flags (§1 of the recert spec), each with the number that raised it:** axis / session ON − OFF point < −5 pp; Holm p < .05 with
  OFF better; subjective member Holm p < .05 favouring OFF; ON 256K prefill peak > OFF + 2 GB or > ≈ 48 GB; decode ratio < 1.3× on
  A1 or A7; pooled acceptance < 0.70; a nonconv kind or tax flag present in ON and absent in OFF. Flags are listed, never vetoes.
- No composite, no `successes_per_hour`, no `pass@1|converged` ranking (diagnostic column only).

`SIGNALS.md` layout: header (inputs sha set, generator version, B8.json sha), one section per axis in the order A7-s1, A7-s2,
A1, M1, A2, A3, A4, then flags, noise floor, coverage. Every number traceable to a JSON path in `SIGNALS.json`.

## 5. Panel run (B3, C207 / C217)

Packets for B8-accepted pairs whose outputs differ: A1 both-correct items, A2 all 40, A3 all 20, A7 both-pass items per session
(final tree + transcript summary). Judges per `judges.json`: Claude Opus 5.5 `blind-judge` (this session) + GPT-5.6 Sol High via
`cursor-agent` for text / code, Gemini 3.1 Pro for A3 images. Both orders. Retries 0; a failed call is a missing verdict.
Estimated ≈ 240 items × 2 judges × 2 orders ≈ 960 verdicts; no GPU. Verdicts commit under `benchmark/results/p426/panel/`.

## 6. Tests (red first; hermetic fixtures; no `$STACK_WORKDIR`)

- B8: one test per rule in §3 (accept + each refusal), stale-B8.json refusal, superseded / smoke exclusion.
- B6: statistics against hand-computed fixtures (bootstrap determinism with seed 426, permutation p on a known small case, Holm
  order, zero-discordance bound); strict scoring (DNF and budget-hit as failures); C269 sensitivity; C172 / C173 labels; flags
  each raised and not raised; byte-identical regeneration; refusal on any missing or unhashed input.
- Golden on the committed data: A7 per-arm pass counts (s1 OFF 42/43, ON 41/43; s2 OFF 41/43, ON 43/43) and the reload
  reproduction (5 / 5 both arms) appear exactly in `SIGNALS.json`.

## 7. Build (four-eyes, this spec as the contract)

Order: (1) B8 + B6 for A7 (the primary workload) → provisional `SIGNALS.md` with A7 only, labelled PROVISIONAL; (2) the Wave 1
adapters (A1, M1, A2, A3, A4); (3) the panel run; (4) the final sheet. Roles: an independent test writer from this spec before
seeing code; an implementer; one cold review per step (≤ 3 rounds). Commits `feat(bench)`; the sheet `data(bench)`. Gate before
the code push (level full).

## 8. Operator choices

- **Q1 — order.** Recommended: A7 first as above (the call's primary workload, data ready). Alternative: all axes at once.
- **Q2 — panel.** Recommended: run it in full (≈ 960 verdicts; Claude-side tokens in this session + the Cursor subscription).
  Alternative: A7 + A1 only first, the rest after the provisional sheet.
- **Q3 — Wave 1 staleness.** Wave 1 ran on S′ arms before P603 / P604 / P607; none of those touch A1–A4 / M1 generation or
  grading (P604 is the Go grader, tg1 only). Recommended: use Wave 1 as is, recorded. Alternative: rerun Wave 1 (≈ 20 GPU-h).
