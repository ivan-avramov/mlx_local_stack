**Verdict: fix, then merge.** There is one real defect (F1) that breaks the C338 sequencing. I did not fix the candidate.

## Tests

On the candidate, 130 of 131 tests ran and passed. The one failure is a post-reveal test that found F1 and is expected to fail until that is fixed.

| File | Class | Baseline | Candidate |
|---|---|---|---|
| `test_m76_b4_fe_verdict.py` (20) | blind v1, (b) | 20 pass | 20 pass |
| `test_m76_b4_fe_golden_tg1.py` (17) | blind v1, (b) golden and (c) corpus flag; **amended** | 10 pass, 7 fail | 17 pass |
| `test_m76_b4_fe_plan.py` (34) | blind v1, (c) tiers, order, reload, draw refusal, legs and paths; **amended** | 2 pass, 32 fail | 34 pass |
| `test_m76_b4_fe_postreveal_mapping.py` (33) | post-reveal, (c) | not run | 33 pass |
| `test_m76_b4_fe_postreveal_pairs.py` (5) | post-reveal, (c) | not run | 4 pass, 1 fail (screen pair, F1) |
| `test_m76_b4_impl_golden_tg1.py` and `test_m76_b4_impl_tg2.py` (26) | the implementer's tests | not present | 26 pass |

The same 71 v1 tests were collected on both trees (32 passed and 39 failed on baseline). The post-reveal files and the amended copies exist only in `tw/stack`; `base` is read-only to me and has no `run_tg2_chain`. For the two post-reveal files, "not run" on baseline is therefore a fact about the copy, not an expected outcome I observed.

The post-reveal mapping and A8 tests cover:
- **Grader mapping:**
  - The grader mapping cases from the brief: pass, not converged, each non-`parsed` outcome, and a failing, missing or out-of-universe leaf.
  - A DNF record has `passed` None, not a fail.
  - A row for another language, or a graded record without its grade, is refused.
- **A8 inputs:** s1 and s2 only, DNF, duplicate and non-boolean refusals, and agreement with `m76_rule.axis_verdict`.

## v1 to amended

- **`test_m76_b4_fe_support.py`:**
  - Tg2 runs in the hermetic world under `--lever kv --kv-arm x`, MTP on, with a lever-kv frozen record (corpus tg2, draw sha, tiers) derived from the world's own records. The out-root is `tg2-m76-x-<kind>.a1` under `m76/p426/wave2-tg2/`.
  - The fake probe file the world already passes serves as the stub probe.
  - The `--tg2-draw` flag is removed: the candidate has no such flag, because `getattr(a, "tg2_draw", None)` is never set (`run_tg1_chain.py:162` and `:308`). A modified or missing draw is now a temporary repo root patched into `run_tg2_chain.REPO`, holding the modified draw beside the original sidecar sha.
- **`test_m76_b4_fe_plan.py`:** `CHAIN_BASE` now uses `--predictor mtp` with `--lever kv --kv-arm x`.
- **`test_m76_b4_fe_golden_tg1.py`:** added `CHAIN_BASE_KV`, used only in the `--tier` control inside `test_tg1_refuses_a_tier`.
- **One assertion changed:** in `test_screen_items_are_the_draw_screen_prefix_per_language`, v1 required session `== {"s1"}`. The candidate freezes the screen's session as `"screen"`. The assertion is now "one value, in `{s1, screen}`". The spec does not fix this label.
- **Residual weak case:** the `bad2` case of `test_tg2_needs_a_valid_tier` still passes by argparse rejecting the nonexistent `--tg2-draw`, so it is vacuous.

## Suite comparison

I could not compare failure sets, and I did not rerun the full suite.
- `suite-cand.txt` stopped at one collection error, in `test_t3_wave1.py` (`registry_states.py: no registry_states in the frozen build`). So it has no failure set. That file now passes on both trees (`../fe_test.sh stack` and `base`, 31 tests, no failures), so the error looks like it predates the submodules being populated.
- `suite-base.txt` was still being written when I read it. It had reached about 7%, all dots.

## Findings

- **F1 (blocking): the screen pair cannot get a dossier.** The `screen` leg's pair is `"screen"` (`p426_wave2.py:171-172`), but `p426_receipt.write_kv_dossier` accepts only `r1, pilot, s1, s2, reload, makeup, s3` (`p426_receipt.py:323-324`, `:488`). After the screen's second leg the sequencer would raise an uncaught `ValueError`, and the DECIDER legs would not be scheduled (C338). The implementer's tests don't reach this. My `test_m76_b4_fe_postreveal_pairs.py::…[screen]` fails on it. The fix would also have to cover `p426_receipt.PAIRS`.
- **F2: DNFs and tg2.** `a8_decider_inputs` (`p426_signals.py:1972`) refuses any DNF, and `Sequencer` allows legs that finish VALID_WITH_DNF (up to 2 DNFs). tg2 has no make-up legs (`check_args` refuses them), so such a leg cannot reach A8. tg1's P426 flow resolves DNFs through make-up. This needs a rule before B4b: score them, or add make-up.
- **F3: no tool writes a tg2 frozen record.** Every tg2 leg refuses unless the v8 base names `corpus: tg2`, `tg2_draw_sha256` and `tg2_tiers`. The freeze tooling (`p426_freeze`) writes none of these.
- **F4: the sequencer stops after the smoke pair.** `p426_wave2.py:892` requires the operator or designer to write `amendment.json` by hand (Q2). Nothing past the smoke is automated.
- **F5: dead code.** The `tg2_draw` lookups mean the draw's sha is checked only against the committed sidecar plus the record's `tg2_draw_sha256`. That is sound, but the spec's "draw path" has no CLI.
- **F6 (observation):** `item_record` requires `row["converged"] is True`. A row lacking that key is a fail. This is fail-closed, but it depends on the future probe emitting the key.

## Deviations from the specification

- **Language order:** rust, javascript, java, cpp. The spec lists languages in that order but does not fix the run order. `schedules.tg2_tier` uses sorted order, so the two now differ.
- **Smoke:** 1 item per language (4 total), taken from the screen tier.
- **Tg2 tier:** `tier: screen` is also the smoke's tier.
- **Make-up and rehearsal:** none for tg2. The spec does not mention them.
- **Deadline:** the formula is 1.5 × Σ items × `w_<lang>_s` + 1800 s, with no default wall. It stops before launch if the walls are absent.

## What B4b must change

1. Fix F1 (pair names, plus the dossier and verify allow-lists).
2. Decide the DNF rule for tg2 (F2).
3. Write the tg2 freeze and record tooling and the amendment writer (F3, F4).
4. Build `run_tg2_probe.py` (C342).
5. Test whether the harvest accepts tg2 grade receipts (Q4).
6. Extend the A7 verifier's attempt-name patterns only if tg2 legs ever need them. They are tg1-only today.