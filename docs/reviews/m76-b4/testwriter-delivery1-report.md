The tests are written and have run on the baseline: 71 collected, 32 passed, 39 failed. The 39 failures are the new tg2 behaviour, as expected on a baseline with no implementation. Five of my interface guesses are not pinned by the spec, and the grader-to-record mapping criterion has no test (see below).

I created only `test_m76_b4_fe_*.py` files (support, plan, golden_tg1, verdict) and `fixtures/m76_b4_fe/golden_tg1_surface.json`. I did not commit or push. The golden was computed by running the baseline and holds no home paths. The "sha-pinned" fixture requirement is met only by the draw's own sha check, since I added no `SHA256SUMS`.

## Results on the baseline

**Passed (32), class (b), preserved invariants:**
- **Golden:** the tg1 plan, schedule shas, leg names, chain argv and CLI namespace for both the mtp and kv levers, plus the frozen tg1 schedule bytes in the hermetic world (arm off).
- **Draw:** the committed draw matches its sha and has the sizes the legs need.
- **A8 verdict and HOLD:**
  - Identical arms PASS at α 0.001 over 80 items and 2 sessions.
  - Total harm is a LOSS and blocks.
  - −20 pp exactly does not fire the HOLD, through both `axis_verdict` and `a8_hold`.
  - One more cell (−22.5 pp) does fire it.
  - One language's harm holds even when the macro average is mild.
- **Grader and convergence:** `Tg2Grade.failing` pass semantics and `convergence.is_converged`.
- **Table:** the tg1 kv leg table without `--corpus`.

**Failed (39), class (c), new behaviour, red for the stated reason:** every one fails with `unrecognized arguments: --corpus …` or `unexpected keyword argument 'corpus'`. They cover:
- **CLI:** the tier flags.
- **Tiers and order:** the screen prefix (10 × 4, s1 only), the decider prefix (20 × 4, nested), s2 with languages reversed, and reload as the first 5 of s1's first language.
- **Frozen schedule:** it names the draw sha and the tier.
- **Draw refusal:** 8 modified-draw cases and a missing draw.
- **Sequencer:** the leg names `tg2-m76-<arm>-{smoke,screen,s1,s2,reload}` and the decider always scheduled after the screen with no trigger.
- **Paths:** the `wave2-tg2` results path and the flat out-root.

I added a positive control to each refusal test, because argparse's "unrecognized arguments" message made them pass falsely on the baseline at first.

## Gaps

- **Grader-result mapping to item records has no test.** The spec names no function or file for it. The grader/convergence invariants that mapping must use are pinned, but the mapping itself is not. I need a seam name from the implementer or designer. The same gap affects the 4-item smoke leg's contents.
- **Interface guesses.** The spec gives `--corpus`, `--tier`, the leg names and the results path. The rest is my guess, recorded in `test_m76_b4_fe_support.py`:
  - the chain's draw flag `--tg2-draw`
  - the sequencer's `--corpus` flag and `Sequencer.table`
  - `BoxSeqOps(..., corpus="tg2")`

  A different spelling fails those tests with a message, not silently.
- **Observation seam.** I check the chain through the `schedule.json` it freezes before its first launch. This needs tg2 to run under `--p426`, with `--predictor off` and the mtp-lever world. If the implementer restricts tg2 to `--lever kv`, those tests need a one-line change.
- **Missing fork submodule.** This clone has no `src/mlx-vlm` submodule, so the existing B2 hermetic-world tests fail here as well (I checked `test_b2_frozen_add_sequencer.py`). My `freeze` helper writes a stand-in `pins.json` when the file is missing, so the world runs. On a box with the submodule it uses the real file.
- **Not covered:** the wiring of the sequencer's screen-to-decider flow, since the kv sequencer has no `main`-level fake-ops harness. I tested the leg table and order instead.