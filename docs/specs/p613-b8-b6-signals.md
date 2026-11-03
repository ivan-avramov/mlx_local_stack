# P613 — B8 pair verifier + B6 signals sheet for P426 — SPEC v2 (2026-11-03; C274 approved the §8 choices)

Authority: `docs/specs/p426-fable-mtp-recert.md` v4 §1, §3, §5–§9; `docs/specs/p426-b2-tg1-wave2.md` §12; AGENTS.md "Benchmark
validity" / "Analysis and reporting"; `docs/metrics.md`; C161, C166, C172, C173, C204, C206, C207, C217, C235 G1, C269, C273. On
conflict those win; record it here. v1 applied cold review round 1 (`docs/reviews/p613/r1.md`, 15 findings); v2 applies round 2 (`docs/reviews/p613/r2.md`, 4 partial
+ 10 new, all adopted).

## 1. Scope

- **B8** `benchmark/bench/p426_verify.py`: which ON / OFF pairs are comparable. Fail closed. No statistics.
- **B6** `benchmark/bench/p426_signals.py`: generates `benchmark/results/p426/SIGNALS.md` + `SIGNALS.json` from committed files, for
  B8-accepted pairs only. Deterministic (same inputs → byte-identical outputs; no wall-clock time, no absolute paths in the output).
  Never hand-edited.
- **Panel run**: B3 `bench/p426_panel.py` EXTENDED: every call passes `build="s2"` (its default `"s"` keys `@p426-on::` and would
  score every S′ ON win 0); a new A7 key mapping (attempt → arm) and A7 packet builder (§5). Packets + verdicts for the subjective members. B6 reads verdicts; a missing
  verdict is counted, never imputed.
- Non-goals: new runs, regrading, changing any harvested byte, the ship decision (C204).

## 2. Inputs (committed only; `$STACK_WORKDIR` never read)

Allow-list: `benchmark/results/p426/wave1.s2/`, `benchmark/results/p426/wave2/`, and in `benchmark/results/<entry>/` only tunes
`p426s2-{off,on}-b{1,2}`. Deny-list (refuse if requested as a pair member): `benchmark/results/p426/wave1/`, tunes `p426-{off,on}-*`
(the S build, never pooled with S′), every `*-smoke`, `archive/`, `wave2.v8-*`. Noise-floor inputs are separate (§4.9).

| Axis | Pair members | Rows / results | Validity |
|---|---|---|---|
| A1 math500 | tunes `p426s2-{off,on}-b{1,2}` | `<entry>/math500.<tune>.jsonl` + `.score.json` | receipt `wave1.s2/<leg>/<leg>.receipt.json`: `verdict` VALID, `speed_valid`; `run/frozen.s2.json` |
| A2 cjudge | same | `<entry>/cjudge.<tune>.jsonl` (`acc` null → panel only) | same |
| A3 vision | same | `<entry>/vision_gate.<tune>.jsonl` | same |
| A4 reasoning | same | `<entry>/reasoning.<tune>.json` | same; descriptive |
| M1 memory | legs `m1-p426s2-{off,on}-b{1,2}` | `wave1.s2/<leg>/m1/<entry>/result.json` | same |
| A7 tg1 | attempts `wave2/tg1-p426-{off,on}-{s1,s2}.a1` (pairs); `-pilot.a1`, `-reload.a1` (diagnostic) | rows: every `<attempt>/<session>/*.jsonl` (incl. the `L0.pilot.a1` invocation file inside `s1` / `s2`); key (session, `id`, `sampler_seed`), language = the `id` prefix; duplicates refuse; row count == planned slots = Σ `blocks[].legs[].invocations[].expect` of `<attempt>/schedule.json` (43); item records `<attempt>/items/*.json` excluding `*.ready.json` | `<attempt>/leg.json` `state` VALID, `speed_valid`; `receipt.json`; `HARVEST.json`; `pairs/<session>__off-a1__on-a1.json`; `run/v8_base.json` |

The pilot / reload attempts are never pooled with s1 / s2. Arm registry shas come from the receipts / frozen records
(`registry_off_sha`, `registry_on_sha`), never re-derived from git.

## 3. B8 — rules (each refusal names the pair, the rule and both values)

1. Both members present and valid per the table's validity column; superseded, INVALID or smoke members refuse. A
   power-invalid (`speed_valid` false) leg stays a quality member, labelled "power-invalid"; a receipt- or transport-invalid one
   does not (recert §3).
2. Arm identity: OFF and ON differ by exactly the restore delta — Wave 1: the frozen record's two registry shas and the receipt
   worker argv (`--draft-kind mtp --draft-model caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter --mtp-verify-scan
   joint_v1` on ON only); Wave 2: `v8_base.json` `off_commit` / `on_commit` / `gitlinks` and the dossier `arms` / `differences` (⊆ the allowed list:
   today `snapshots.drafter`, `argv.worker`). Everything else equal (sampling,
   budgets, KV, serving pins, item set, seed set, box).
3. Pair keys equal: A7 (session, language, item, seed); Wave 1 (tune block, item id, sample seed).
4. Speed: a block / session with either member `speed_valid` false leaves speed inference; one valid block → descriptive, "not
   order-balanced".
5. A7: the dossier exists, self-hashes, reads PASS and names exactly the two attempts; each attempt's HARVEST.json re-verifies
   (every published sha256).
6. Cross-wave code check (Q3): the file list of `git diff <wave1.s2 stack_head_off> <wave2 off_commit>` restricted to
   `main_models.yaml`, the `src/*` gitlinks and the `identity_closure.python_closure` of `benchmark/run.py`,
   `benchmark/vision_gate.py`, `benchmark/bench/run_reasoning.py` and the M1 `qualify` entry; non-empty → a flag in the sheet with the
   list (not a refusal). Both commits must resolve (`f2b61127`, the Wave 1 ON head, has no branch: archive it, P606-style).
7. C217 identity: A1 / A2 / A4 the content sha (`content_sha256`), A3 the description text sha, A7 the final-tree manifest sha.

Output `benchmark/results/p426/B8.json` (accepted / rejected pairs with reasons, the cross-wave flag, the sha256 of every input).
B6 refuses when any input sha differs from `B8.json`.

## 4. B6 — signals (A7 per session s1 / s2, never pooled across sessions; Wave 1 per block and both blocks)

Statistics reuse `bench/stats.py` and `bench/compare_predictor.py`; never `stats.verdict_label`; of `paired_delta`'s return only
`delta`, `lo`, `hi`, `degenerate`, `discordance_upper95` are read (its `verdict` / `directional` never reach the sheet). RNG: the
bootstrap is `stats.paired_delta(..., iters=10000, seed=426)` (stdlib `random`); `numpy.random.default_rng(426)` for the
permutation tests and `length_adjusted`. numpy (2.3.5) and scipy (1.17.1) versions from the bench lock are printed in the header.

1. **Quality, mechanical.** Per arm `acc` (lenient), `acc_strict@budget` over ALL planned slots (a DNF and a budget-hit are
   non-successes; denominator = planned slots), conv %, `nonconv_kinds`. Paired ON − OFF: `stats.paired_delta` (`delta`, `lo`,
   `hi` only; two-stage percentile bootstrap, 10,000; stage 2 is a no-op at k = 1). MDE: `stats.mde(n, p_d)` with `p_d` = the
   observed discordance fraction (both reported when it is 0: the default 0.20 row). Mechanical family {A1 (both blocks, items disjoint by construction — asserted), A7-s1, A7-s2}:
   paired sign-flip permutation test on per-item strict differences, T = mean difference, 10,000 sign vectors, two-sided,
   p = (1 + #{|T*| ≥ |T| − 1e-12}) ÷ 10,001, zero differences contribute zero; `stats.holm` over the family.
2. **Labels (C172 / C173).** CI excludes 0 → shown difference; includes 0 → WASH, point labelled "directional (not a shown
   difference)"; lossy-lever loss bound = `compare_predictor._loss_bound` (−CI lower bound; a zero-discordance cell uses the exact
   one-sided 95 % discordance bound 1 − 0.05^(1/n), n = paired items, in pp of items); > 10 pp → "loss not ruled out above X pp".
3. **Exclusive solves and edit competence.** Per pair the ON-only and OFF-only strict solves (lists). A7 edit competence per arm:
   `file_changed`, `test_modified`, `tool_bounds_rejections` counts.
4. **DNF (C235 G1).** Per arm and cause a table from each attempt's `chain.json` `p426_dnf`; a DNF slot is a non-success for its arm
   only, the pair stays. Make-up sensitivity: the strict delta with make-up legs substituted, or "no make-up run".
5. **Subjective.** Items enter only through `p426_panel.admit()` (exactly one verdict per judge × order); the excluded are counted.
   Per item raw score = mean over judges × orders (ON win 1, tie 0.5, OFF win 0; `p426_panel.item_scores(..., build="s2")`; Wave 1
   keyed (block, item)); the permutation test (as 4.1) runs on raw per-item scores − 0.5. Headline beside it:
   `p426_panel.length_adjusted` on rows B6 builds, one per admitted verdict, `{item, score, log_len_ratio}` with
   `log_len_ratio` = ln(len_ON ÷ len_OFF) of the judged text in characters (Wave 1: the axis's `TEXT_FIELD`; A7: the final-tree
   diff text). Family {A1,
   A2, A3, A7-s1, A7-s2}; a member with < 5 judged items is reported, not tested; Holm m = the number of tested members, fixed by
   that rule before any p-value is read. C217-identical pairs score 0.5, stay in the test, are labelled "identical outputs; panel
   not run" and are not counted as judged. A4: draw distribution + panel scores, descriptive, never tested (recert S7). Every
   member is labelled "conditional on both-pass" with n and the count of one-arm-pass items left out. Per verdict: judge model id,
   client version, prompt sha; single-family members labelled (C166 / C206).
6. **Memory (M1).** Prefill / decode / retire `mx.get_peak_memory` peaks per leg; ON − OFF per block and both blocks.
7. **Speed.** Primary (recert T2) — A7 per item: (`totals.generated_tokens` − `totals.requests`) ÷ `totals.decode_s` (the totals
   cover completed requests, `decode_rate_source`); sensitivity: over every request record with `decode_tok_s` > 0, decode time =
   (generated − 1) ÷ `decode_tok_s`. Wave 1 per row (one request): `decode_tps`; no sensitivity. Paired per-item ON / OFF ratio;
   statistic = the geometric mean of per-item ratios with its item bootstrap interval within a session / block; an item with no
   completed request in either arm is dropped and listed. Acceptance = Σ accepted ÷ Σ proposed within the session. Per-leg wall
   from the leg records (clean-box chains), descriptive.
8. **Runaway tax (A7; B2 §12, C269).** Budget-hit, turn-cap, exec-timeout, `client_inactivity` (own category, with each item's
   `client_abort` block), loop kills, stall kills, per arm and session, plus the per-session union; pooled rates descriptive. C269
   sensitivity: the strict delta without the pairs where either arm ends `client_inactivity`.
9. **Noise floor (C273).** Same-epoch: reload vs pilot per arm (5 items each). Cross-epoch, labelled with both `v8_base` shas:
   outcome flips (pass or convergence differs) between `wave2` and `wave2.v8-4104c7fc` over its VALID attempts with the same
   schedule sha (pilots, `off-s1.a1`, `on-s1.a2`; the INVALID `on-s1.a1` / `on-s2.a1` excluded), with the denominator.
10. **Coverage.** Legs done / pending / invalid / superseded per axis; smokes listed, never scored.
11. **Flags (recert §1), each with its number:** a mechanical axis / session point < −5 pp; Holm p < .05 with OFF better; a
    subjective member Holm p < .05 favouring OFF; ON 256K prefill peak > OFF + 2 GB or > ≈ 48 GB; decode ratio point < 1.3× on A1
    or A7 (CI beside it); pooled acceptance < 0.70; a nonconv kind or tax category present in ON and absent in OFF; the B8
    cross-wave flag. Listed, never vetoes.
12. Never: a composite, `successes_per_hour`, `pass@1|converged` as a ranking (diagnostic column only).

Layout: header (inputs sha set, generator version, numpy version, B8.json sha), sections A7-s1, A7-s2, A1, M1, A2, A3, A4, flags,
noise floor, coverage. Every number has a JSON path in `SIGNALS.json`.

## 5. Panel run (B3; C207, C217)

Frozen before any verdict is read: the packet set (B8-accepted pairs that pass the C217 identity gate — counted AFTER the gate;
the S build found 166 / 166 Wave 1 pairs identical, so Wave 1 may contribute ≈ 0 packets: A1 both-correct, A2 all 40, A3 all 20, A4
strict draws, A7 both-pass per session) and the judge list from `judges.json` (two families per modality; model ids, client
versions, prompt shas recorded). A7 packet = task statement, final-tree diff against the exercise start, the grader result, and a
mechanical transcript extract (tool-call names and counts; no model-written summary); `leak_problems` runs on every packet.
Both orders. Retries 0; a failed call is a missing verdict. Upper bound ≈ 250 items × 2 judges × 2 orders ≈ 1,000 verdicts (A7 ≈ 80
both-pass items if none are identical); the real count is printed when the set is frozen; no GPU.
Verdicts commit under `benchmark/results/p426/panel/`.

## 6. Tests (red first)

- Hermetic (fixtures under `tmp_path`): one per B8 rule (accept + each refusal, incl. deny-list, duplicate row key, row count ≠
  planned, stale B8.json); B6 statistics on hand-computed fixtures (permutation p on a known small case, Holm order and m,
  `paired_delta` reuse at k = 1, the zero-discordance bound), strict scoring with DNF and budget-hit, the C217 0.5 rule, C269,
  C172 / C173 labels, every flag raised and not raised, byte-identical regeneration, no absolute path in outputs; `item_scores` /
  `make_pairs` with `build="s2"` score an S′ ON win 1 (and the default `"s"` refuses S′ keys); a non-empty `p426_dnf` fixture
  in the `chain.json` shape; a make-up leg named by the sequencer's `makeup` record.
- Golden (separate, marked, reads committed data): A7 strict-input pass counts (s1 OFF 42/43, ON 41/43; s2 OFF 41/43, ON 43/43,
  the 5 `L0.pilot.a1` rows included), reload == pilot (5 / 5 each arm), B8 accepts the four Wave 2 pairs.

## 7. Build (four-eyes)

(1) B8 + B6 for A7 → PROVISIONAL `SIGNALS.md` (A7 only); (2) the Wave 1 adapters (A1, M1, A2, A3, A4) + the cross-wave check;
(3) the panel run; (4) the final sheet. Roles: an independent test writer from this spec before seeing code; an implementer; one
cold review per step (≤ 3 rounds). Commits `feat(bench)`; the sheets `data(bench)`; a gate before the code push (level full).

## 8. Operator choices

- **Q1 — order.** Chosen (C274): A7 first (primary workload, data ready), PROVISIONAL label. Alternative: all axes at once.
- **Q2 — panel.** Chosen (C274): the full panel, its packet set and judges frozen before any verdict (≈ 1,000 verdicts: session
  tokens + the Cursor subscription). A staged panel is not offered: choosing later stages after reading earlier ones is a
  look-then-decide path.
- **Q3 — Wave 1 as is.** Chosen (C274): use it, gated by the B8 cross-wave check (§3.6); a non-empty generation-path diff returns to
  the operator before Wave 1 enters the sheet. Alternative: rerun Wave 1 (≈ 20 GPU-h).
