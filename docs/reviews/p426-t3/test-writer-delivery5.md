The pin move checks out: with the new S′ pins, my set passes all 158 tests on the candidate, and the baseline outcome is unchanged. **Verdict: accept.**

## Amendments
All are tagged `# POST-REVEAL tw-5: C242 pin move`.
- **`t3_frozen_support.py`, `S2_PINS`:** mlx-vlm is now `1c7c8fa166582ac1a1c23ae9063527b2b5215b11` and mlx-serve `1ddf6f842f159a62d240f3ac6965fc33cbdb0b0d`. `production_ref` stays `b26fa7c9…` and mlx stays 0.32.4. Every S′ world and record takes its pins from `S2_PINS`, so all record, arms, names and out tests follow the move.
- **`t3_frozen_support.py`, `s2_layout` docstring:** it no longer names `c688e722` as S′. The layout bytes are read from the running tree's `src/mlx-vlm`: `c688e722` in this copy, `1c7c8fa1` in the candidate.
- **`test_t3_frozen_record.py`:** the expected-build test's docstring now names the new pins.
- **Kept as historical:** `test_t3_frozen_gate.py:22`, which describes the original gate failure for `c688e722`.

## Fork files at the new pin
I could not run `git -C src/mlx-vlm diff c688e722 1c7c8fa1 --stat`. This copy's fork doesn't hold `1c7c8fa1` (`git cat-file` fails), and I have no way to run git in the candidate copy.

There is indirect evidence that the files didn't change:
- In the candidate run, the fake forks copy `registry_states.py` and `stack_registry_golden.yaml`, and the S′ layout reads `dev/ci.py` and `.upstream-sync-ref`. All of these come from that copy's `src/mlx-vlm`, now at `1c7c8fa1`.
- `fixture_text` enforces the golden fixture's pinned sha256, so a changed fixture would refuse.
- The ON bytes must equal the B4 rule's output.
- `dev/ci.py` must list the nine audits.
- The sync ref must be `2ceff4c1`.

All of those checks passed on the candidate.

## Runs

| file | tests | baseline pass / fail | candidate |
|---|---|---|---|
| support_check | 32 | 32 / 0 | 32 / 0 |
| label | 15 | 0 / 15 | 15 / 0 |
| names | 9 | 0 / 9 | 9 / 0 |
| arms | 38 | 0 / 38 | 38 / 0 |
| record | 17 | 0 / 17 | 17 / 0 |
| out | 7 | 0 / 7 | 7 / 0 |
| harvest | 20 | 12 / 8 | 20 / 0 |
| panel | 6 | 1 / 5 | 6 / 0 |
| gate | 5 | 1 / 4 | 5 / 0 |
| fix | 9 | 1 / 8 | 9 / 0 |

- **Baseline:** `../bin/run_stack_tests.sh <10 files> -rA --tb=short` → `111 failed, 47 passed in 76.55s (0:01:16)`.
- **Candidate,** after `../bin/sync_to_candidate.sh` (11 files): `../bin/run_candidate_tests.sh <10 files> -rA --tb=short` → `158 passed in 274.22s (0:04:34)`.

## Failure classes
- **Baseline:** all 111 are (b), behaviour the spec adds, with the same first lines as delivery 4. Those are the argparse usage errors on the S′ options, `unrecognized arguments: --build s`, `TypeError … 'build'` in the panel, `GateError … upstream-parity.yml does not exist`, the naming exemption, V3's control twin, and the V4 usage error. The pin move doesn't affect the baseline: B0 has no `s2` path, so its outcome is the same as in delivery 4.
- **Candidate:** nothing fails.

## Verdict on the pin move
The two changed literals in `EXPECTED_BUILDS["s2"]` (`p426_plan.py`) match C242. My expected-build tests use S's pins as the "other build" case, and they still refuse. Their control twins now run at the new pins, so the binding refuses the S record and accepts the new S′ record.

The pin diff touches nothing else in code. Its plan-text change also keeps `c688e722` and `e6a7a5a` as named history.
