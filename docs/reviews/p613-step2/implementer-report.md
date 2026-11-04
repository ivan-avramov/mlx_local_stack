I've implemented P613 step 2. Both `all` commands exit 0, their outputs are byte-identical on rerun, and the test command passes (257 tests). Every golden number in the contract reproduces except one: the A4 per-draw speed range (1.528–1.656 here, the contract says 1.584–1.656). Two things are still open: the scratch directory is not deleted, because the delete command was denied, and I compared the `a7` outputs against the committed step-1 files rather than re-running the baseline code. Nothing was committed or pushed.

## Files

- `benchmark/bench/p426_verify.py` (changed): adds the Wave 1 checks (`verify_wave1`, `load_w1_leg`, `load_ids`, argv parsing), the rule-6 cross-wave check (`cross_wave`), `verify_all`, `check_roots` and the `all` command. The step-1 functions and the `a7` command are unchanged.
- `benchmark/bench/p426_signals.py` (changed): adds `compute_all`, `render_all` and the `all` command. Step-1 code is refactored but produces the same output:
  - `compute_a7` now wraps a new `_compute_a7_parts`.
  - `_session_md` takes two optional arguments whose defaults give the old output.
  - The noise-floor and A7-coverage rendering moved into helpers that emit the same lines.
- `benchmark/bench/p426_wave1.py` (new, the one extra module the brief allows): the Wave 1 signals for A1, M1, A2, A3 and A4, plus the Wave 1 flags and rendering.
- Outputs: `.p613-material/out/{B8.json,SIGNALS.md,SIGNALS.json}`. Nothing was written under `benchmark/results/`.

## Commands and results

- `p426_verify all --results-root results/p426 --rows-root results --repo .. --out ../.p613-material/out/B8.json`: rc 0.
- `p426_signals all … --out-md … --out-json …`: rc 0.
- A second run of both is byte-identical:
  - B8.json `455ac5ff6e730490da62b0efe4b2603f2c646e219591e20d6bdd5a3644cf8b77`
  - SIGNALS.md `2b556bfa72d72ee4499509ce5d220621e1ae612fe570b7476a9da9a0ef712918`
  - SIGNALS.json `ced2f9bc3474fa7e786b2d7397c603ecbf851dc0d68524b0935b4ff1eeef3ee7`
- The `a7` commands on the current code match the committed step-1 files byte for byte:
  - B8 `b6ceddfb…`
  - SIGNALS.md `50b27b18…`
  - SIGNALS.json `84d8d1a9…`
  - **Caveat:** I could not extract the `5630d8f6` code to run it directly (`git archive` and `tar` into scratch were both denied). I compared against the committed files instead, which commit `afd6d3e9` says regenerate byte-identical at baseline.
- No `/Users`, `/private`, `/tmp`, `$STACK_WORKDIR` or `$HOME` string appears in any output.
- Test command: **257 passed** (`bench/tests/p613` plus `test_p371_r7_consumers.py`, which includes the R7 scan).

## Golden: contract vs got

| Item | Contract | Got |
|---|---|---|
| Wave 1 pairs accepted / speed-valid | 10/10, all | 10/10, all |
| Keys A1/A2/A3/A4/M1 per block | 50, 20, 10, 3, 1 | same |
| Identical outputs | 166/166 | 166/166 (A1 50+50, A2 20+20, A3 10+10, A4 3+3) |
| SCRUB files re-verified | 249/249 | 249/249 (166 full legs + 83 smoke legs, see below) |
| `content_sha256` checked | 280/280 | 280 |
| `frozen_sha` | `3c155062…` | `3c155062…` |
| Rule 6 | `["main_models.yaml"]`, flag true, entry/globals equal, 34 closure files, gitlinks equal | same |
| A1 strict = lenient | b1 49/49, b2 47/47, conv 100 %, no nonconv kinds, no exclusive solves | same |
| A1 paired delta | 0 / 0 / 0, degenerate | same, per block and both |
| A1 loss bound | 5.82 pp (n 50), 2.95 pp (n 100) | 5.8155, 2.9513 |
| A1 MDE | 0.1772, 0.1253 | 0.17719, 0.12529 |
| A1 permutation p; Holm | 1.0; m 3, all 1.0 | 1.0; m 3, all 1.0, "complete" |
| Decode ratio A1 / A2 / A3 | 1.736/1.729, 1.606/1.543, 1.775/1.727 | same |
| **A4 per-draw ratios** | **1.584–1.656** | **1.528–1.656** |
| Acceptance A1 | 0.7490 / 0.8038 / both 0.7666 (106153/138464) | same |
| Acceptance A2 / A3 | 0.5869/0.6128/0.6015; 0.6343/0.5996/0.6168 | same |
| Acceptance A4 | 634/708 = 0.8955, 604/680 = 0.8882 | same, equals `acceptance_pooled` |
| A2 conv; A3 self-PASS; A4 strict draws | 20/20; 10/10; 3/3, 0 budget hits | same |
| M1 peaks, Δ prefill, decode tok/s | as listed in the contract | all byte values identical; Δ +314297660 B (0.314 GB); decode 16.019/13.361, 16.041/13.412 |
| Wave 1 flags | A2 acceptance (b1, b2, both), A3 acceptance (b1, b2, both), cross-wave; nothing else | exactly these |

**The A4 mismatch:** ratio = row `decode_tps` ON / OFF per draw. The six draws are:
- b1: 1.6154, 1.6232, 1.5841
- b2: 1.6555, 1.6343, 1.5278

The 1.5278 draw is b2, task seed 128000005, ON 26.093 vs OFF 17.079 tok/s. The contract's range omits it; it looks like the b1 minimum was paired with the overall maximum. I did not change the code to match.

## Refusal / rejection checks (21 cases on temporary copies)

**Rejected pair or key:**
- **Rejected pairs:** a receipt verdict of INVALID; a SCRUB file mismatch; the worker argv missing `--mtp-verify-scan`; an extra flag in the M1 job argv; a manifest registry sha mismatch.
- **`speed_valid` false:** the pair stays, labelled "power-invalid", and that block's speed becomes descriptive.
- **Rejected keys (pair stays):** a `sampler_seed` mismatch (49 keys left) and an A4 request-seed mismatch (2 keys left).

**Refused (`RefusalError`):**
- **Rule 2b:** a head that does not resolve.
- **Rule 3:** a duplicate row key, a row count different from the block size, overlapping blocks.
- **Rule 7:** a tampered `content_sha256`.
- **Deny-list:** a symlink to a smoke file, a leg directory pointing into `archive/`.
- **Roots:** a rows root that is not `generate.results_root()`.
- **Signals:** regrade drift, and an input that changed after B8 was written.
- **Rule 6:** a commit that does not resolve.
- **CLI:** rc 2, nothing written, one `REFUSED:` line.

Baseline sanity on an unmodified copy: 10/10 accepted.

**Scratch not deleted:** `rm -rf .p613-material/scratch` was denied. It holds 21 copies of committed public data plus my probe scripts. Please delete it.

## Beyond or short of the contract

- **SCRUB 249:** only the 20 full legs (166 files) gate their pairs. The other 83 belong to the smoke legs, which I re-verify separately in `axes.wave1.scrub_coverage`; that record never gates or scores anything.
- **Additions:**
  - An M1 `result.json` status other than `"ok"` is a rule-1 rejection.
  - Rule 2d also checks A3 turn-2 drafts.
  - B8 records `log`, `speed_problems`, `gitlinks` and `entry_present` as evidence only.
- **Under `all`, A7's Holm p uses the m = 3 family**, and the A7 flags are recomputed from it. The `a7` command keeps m = 2.

## Ambiguities and how I resolved them

- **Row ids differ from the `ids.json` list at the right count:** I refuse, as step 1 does for rows outside the planned slots. So "a key in one arm only" can only arise from a seed mismatch.
- **A4 OFF rows have `draft: null`:** I read this as "every draft value null".
- **Key space of the `inputs` union:** everything is keyed relative to the rows root, so A7 keys get a `p426/` prefix. `axes.A7.inputs` stays relative to `results_root`, as in step 1.
- **A3 / A4 nonconv kinds** (the rows have no `nonconv_kind`): A3 uses `finish_reason:<value>` for an unconverged turn 1. A4 uses `budget_hit`, or `finish_reason:<value>` when it is not `stop`. The basis is printed in the sheet.
- **A2 convergence and A1 / A2 nonconv kinds:** these come from `bench.grade` (`grade._rows` plus `convergence.is_converged`), the same path the grader uses.
- **Speed and acceptance flags** fire only on speed-valid scopes, as in step 1. The A1 Holm flag uses the both-block delta.
- **Minor:** when a leg directory points into `archive/`, the refusal reason names the first deny pattern that matches ("a smoke member"), not "archive".
