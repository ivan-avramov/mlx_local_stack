## Round 1 disposition

- **R1 — OPEN.** Per-arm names are specified, but freshness is not enforced as claimed. `generate.py` resumes compatible rows through `done_keys`; `run_reasoning.py` only refuses existing partial state and can replace a completed result. No build adds the universal pre-leg destination refusal required by §4.
- **R2 — CLOSED.** B9 commits and hashes the exact A1 IDs, verifies uniqueness/equality with M40, and records the seeded block split. The proposed `--ids math500=<colon-list>` with `--limit math500=0` is supported.
- **R3 — OPEN.** The correct qualification harness and ABBA design are identified, but the M1 command cannot run as written. Current `qualify.py` requires `--stack-root`, `--fork-root`, `--out`, and `--reviewed-head`; it has no `--predictor`, and Fable is forced ON. B7 must specify four fresh ABBA outputs and the complete invocation/refusals.
- **R4 — CLOSED.** The router capacity ladder is removed, lifetime `peak_mem_gb` is explicitly demoted, and qualification resets MLX peak memory at the prefill/decode/retire phase boundaries.
- **R5 — CLOSED.** B1 now covers the response envelopes and endpoint call sites needed for draft counters and no longer promises an unsupported memory field.
- **R6 — OPEN.** The desired dual-arm schedule is clear, but B2 understates the implementation. Current chains have one scalar predictor and separate ON/OFF chain families; a single-entry interleaved OFF/ON schedule also requires changes in `run_config.py`, `chain_core.py`, scheduling, records, roots, and resume validation—not only `LEGS`, schedules, and `ensure_overlay`.
- **R7 — OPEN.** The intended no-restart transport policy is stated, but current policies are only `abort_restart` and `incident_retry`; `abort_restart` archives and reruns once. B2 does not explicitly add and test a new invalidate-without-restart core policy.
- **R8 — OPEN.** Current `compare_predictor.py` handles ordinary benchmark rows/manifests, expects one must-differ key, and invokes mechanical grading. B8 does not define adapters for vision, reasoning, qualification, and chain records, nor the exact registry/runtime checks needed for the atomic three-key delta and `draft_model`.
- **R9 — CLOSED.** A7 reports s1 and s2 separately, keeps reload diagnostic-only, and limits pooled tax to descriptive reporting.
- **R10 — OPEN.** The panel remains under-scoped. Existing tooling is cjudge/text oriented; A4 does not persist completion text, A3 needs multimodal packets, and A7 needs transcript/final-tree extraction. B3 lands after Wave 1 begins, too late to preserve missing A4 artifacts. Allowing a labelled single-provider A3 result also conflicts with mandatory C166 two-provider judging; it must remain pending or be explicitly waived by the operator.
- **R11 — OPEN.** B4 modifies the fork during Wave 1, while §2 requires the same `src/mlx-vlm` SHA in both waves. Landing fork B4 necessarily changes that pin. Move fork B4 before S, keep it out of the Wave-2 submodule, or obtain an explicit serving-path carry-over ruling.
- **R12 — OPEN.** B5 mentions new files and power fields but does not require token-distribution, convergence/error, ETA/correction, and sticky watcher receipts for every smoke and leg. A4’s repeated seeds also require explicit duplicate-load treatment; see S5.
- **R13 — OPEN.** Pins and worker argv are operational assertions without a common Wave-1 pre-arm verifier. Existing provenance omits `draft_model`, and the chain’s worker tripwire covers A7 only. A1–A4 could therefore start without proving the exact ON/OFF argv.
- **R14 — CLOSED.** A3 now has an external blind image-plus-caption review, reported separately from the self-verdict. The implementation/provider deficiencies remain under R10.
- **R15 — CLOSED.** The full-leg and idle arithmetic is now internally credible at approximately 25 hours, or 33 hours with allowance. Missing smoke costs are a new protocol issue under S2.

## New findings

### S1 — BLOCKER — §4 A3, B9
**Problem:** `vision_gate.py --limit` accepts an integer prefix, not a block ID list. `--limit <block>` either fails argument parsing or, if replaced by `10`, runs the same first ten images in both blocks. B9’s A3 split cannot currently be consumed.

**Failure scenario:** Both loads evaluate duplicate images while the signals sheet reports 20-image coverage and AB/BA order balance.

**Fix:** Add reviewed `--ids` or committed block-fixture support to `vision_gate.py`; refuse unknown, duplicate, missing, or wrong-block IDs before the first request and record exact membership in the manifest.

### S2 — BLOCKER — §§4, 8–9
**Problem:** Wave 1 has only a naming convention for `-smoke`; it defines no smoke ID sets, launch order, gates, receipts, or cost. AGENTS requires a smoke first and five seeded-random corpus items before any queue of at least 40 items.

**Failure scenario:** A1 or A2 enters its full queue after no valid smoke, or after an easy prefix smoke that does not exercise the committed paired corpus.

**Fix:** Commit five-item seeded-random smoke sets per applicable axis, pair the same IDs across arms, require successful transport/provenance/engagement receipts before full launch, define freshness and invalidation semantics, and add all smoke loads and idle periods to the estimate. A7’s existing pilot may satisfy this only after B2 proves equivalent receipts.

### S3 — BLOCKER — §§2, 5, 7; B1/B6/B8
**Problem:** Only the pilot checks predictor engagement. Full legs do not require eligible ON requests to show positive MTP counters or OFF requests to show no drafter. Configuration equality is insufficient because runtime can silently fall back.

**Failure scenario:** An ON worker starts with MTP argv but emits plain-decode responses. Quality and speed are then compared as ON versus OFF while acceptance is missing or selectively calculated from the few requests that engaged.

**Fix:** Make per-request engagement a leg-validity gate on every axis: ON requires `draft_kind=mtp`, positive rounds and proposed tokens, and valid accepted-token bounds for every eligible request; OFF requires absent/null draft activity. Reconcile all rows/log records exactly, calculate acceptance within each axis/session only, and invalidate the leg on missing, duplicate, zero, or contradictory telemetry.

### S4 — HIGH — §§4 A2, 7
**Problem:** cjudge has no mechanical accuracy: its grader returns `acc: null`. Nevertheless, §7 requires an ON/OFF quality delta, bootstrap interval, and MDE for every axis in addition to the panel.

**Failure scenario:** B6 either refuses a valid cjudge bundle, presents `null` as zero, or invents a mechanical score that was not preregistered.

**Fix:** Declare A2 mechanical quality `N/A` and make the preregistered two-provider panel its sole quality signal, with a panel-specific effect estimate, interval/MDE, and attention rule.

### S5 — HIGH — §§3–4 A4, 7
**Problem:** Both A4 loads repeat the same three seeds. These are same-seed reload controls, not six independent draws; with one synthetic context, a generic two-stage item-cluster bootstrap and axis MDE are not identified.

**Failure scenario:** Six duplicated observations are pooled, understating uncertainty and creating a misleadingly narrow ON−OFF interval.

**Fix:** Either use distinct paired seed sets across blocks and retain a separate same-seed reload control, or report each load separately and treat the repeat only as agreement evidence. Preregister the valid sampling/cluster unit; if only three unique draws remain, label A4 descriptive rather than emitting a pseudo-powered interval.

### S6 — HIGH — §§2–3, 7
**Problem:** §7 excludes individual power-invalid legs. Doing that can retain the unmatched partner or leave only one order, defeating the AB/BA speed design.

**Failure scenario:** Block 1 OFF is valid and ON is power-invalid; the report compares that OFF leg with a different block’s ON leg and calls the result paired/order-balanced.

**Fix:** Power validity applies to the whole ON/OFF block for speed. Exclude both legs from speed inference if either is invalid; with only one valid block, report the paired ratio as descriptive and explicitly not order-balanced certification.

### S7 — HIGH — §§1, 6–7
**Problem:** “Holm p < .05” and “Holm across quality axes” are not operationally defined. The plan does not preregister the hypothesis families, raw test, tie handling, treatment of two judges/orders, or whether A7 sessions are separate hypotheses. Bootstrap intervals do not themselves supply Holm p-values.

**Failure scenario:** B6 chooses a convenient family or test after seeing results, changing which negative panel or quality signal receives an attention flag.

**Fix:** Preregister separate mechanical and subjective families, every included hypothesis, the paired test or permutation procedure, tie and missing-verdict rules, judge/order aggregation, and Holm application. Remove Holm-based flags where a valid test cannot be defined.

### S8 — HIGH — §2 machine state; B5
**Problem:** “Quiet box” is not an executable fail-closed machine-state gate. The plan omits the required zero-survivor checks for `session_cache_probe`/`opencode run`, the orphan-shell sweep used by the chain, and recorded process/load state for Wave-1 speed legs.

**Failure scenario:** An orphan shell or probe survives `stack_stop.sh`, consumes CPU or holds work state, and depresses one arm’s decode rate while AC and battery checks still pass.

**Fix:** Before every speed leg, sweep and verify orphan processes, assert zero prohibited survivors and no other GPU worker, and record process census, load state, uptime, AC, voltage, and battery in a pre-leg receipt. Recheck at exit and invalidate the speed block on drift.

VERDICT: DISAGREE R1,R3,R6,R7,R8,R10,R11,R12,R13,S1,S2,S3,S4,S5,S6,S7,S8