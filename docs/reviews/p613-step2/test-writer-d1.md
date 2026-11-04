I wrote the P613 step 2 test suite in `benchmark/bench/tests/p613s2/`: 342 tests, each with its class in a comment above it. At the baseline, 327 fail, 14 pass and 1 skips. Nothing outside that directory was touched. I did not run the step-1 suite or any git write.

## Files

- `__init__.py`, `conftest.py` (registers `p613s2_golden`, defines the fixtures).
- `wave1world.py` builds a synthetic `rows_root` with `p426/` and `<entry>/`, plus a tiny git repo with fixed identities. It uses the committed formats and the step-1 `a7world`, and regrades `score.json` with the repo's own `bench.grade`.
- `w1view.py` holds structural accessors and oracles.
- `test_p613s2_world_sanity.py`
- `test_p613s2_verify_rules.py`
- `test_p613s2_verify_keys_roots.py`
- `test_p613s2_cross_wave.py`
- `test_p613s2_signals_stats.py`
- `test_p613s2_signals_flags.py`
- `test_p613s2_all_cli.py`
- `test_p613s2_golden.py`

## Tests

- **`world_sanity` (10, invariant):** the fixture itself.
  - Layout, SCRUB and frozen consistency, the three-flag cmdline delta, and the grader's `score.json` output.
  - Git repo commits, determinism across base directories, and the hand numbers of the scenarios.
- **`verify_rules` (141):**
  - Accepted baseline of 10 pairs, key shapes, and `inputs` covering every file read (new-behaviour).
  - Read-only verification (invariant).
  - Rule 1:
    - Invalid verdict, per kind and arm.
    - Problems, and receipt name, arm and kind mismatches.
    - Power-invalid pairs stay and are labelled.
    - SCRUB mismatch (both shas named), missing SCRUB file, and SCRUB path traversal.
  - Rule 2a: pins across the pair and against frozen, `frozen_sha`, frozen bytes changed, and `stack_head`.
  - Rule 2b:
    - Registry sha recomputed from git, unresolvable head refuses, wrong repo refuses.
    - Manifest and M1 report registry sha.
  - Rule 2c:
    - 12 argv variants × 2 router kinds, 6 variants on the M1 `job.json`.
    - Order does not matter, PID and worktree normalisation, and a foreign worktree path is a difference.
  - Rule 2d:
    - Manifest sampling and kv.
    - Row `thinking_budget`.
    - M1 `served`, snapshots, report and qualify.
    - OFF and ON draft rules, with inclusive boundaries.
  - Rule 4: speed validity per pair.
- **`verify_keys_roots` (57):**
  - Deny-list by symlink resolution to smoke, `archive/`, the S build, and the deny-listed tunes.
  - Excluded members ignored.
  - Rule 3: count, duplicate and id-set errors, seed mismatch rejecting one key, A4 `request_seeds`, and overlapping blocks refuse.
  - Missing or unreadable required files refuse, and the CLI exits rc 2 and writes nothing.
  - Root-equality refusals, including resolved paths.
  - Rule 7: tampered `content_sha256` refuses; `identical` counts per kind (A3 and A4 identity from text sha); non-ASCII content.
- **`cross_wave` (26):**
  - No change gives no flag.
  - Registry change flags, with `entry_equal` and `globals_equal` for four combinations.
  - A closure-file change, each of the three entry files, and gitlink changes flag.
  - A change outside the paths gives no flag.
  - The closure is the union over both commits (both directions), deletion flags, and a function-level import is followed.
  - The working tree is ignored and the cwd does not matter.
  - Unresolvable commits refuse, the repo is untouched, and the record is JSON with no absolute path.
  - `verify_all` carries the check, its members equal their verifiers, and rejected pairs are carried.
- **`signals_stats` (46):**
  - A1: strict versus lenient, paired delta, labels, loss bound, MDE, exclusive solves, and the permutation p against the step-1 `permutation_p`.
  - Family: Holm with m = 3, label "complete", only three members, and the A7 raw p.
  - Speed and acceptance:
    - Geomean CI with dropped keys listed.
    - Acceptance as a ratio of sums.
    - Leg wall, A3 acceptance counting turn 1 only, and A4 acceptance and speed.
  - A2 panel-only, A3 self-check and A4 never tested.
  - M1 peaks, ON − OFF, and decode ratio.
  - Identity counts, rejected pairs excluded, coverage, and power-invalid labelling.
- **`signals_flags` (17):**
  - Clean world with no flag.
  - Zero-discordance bound and MDE default row.
  - A1 point, Holm and decode ratio, acceptance for A2, A3 and A4, M1 two-GB and 48 GB rules, `nonconv_kind`, and cross-wave. Each is raised, and the unflagged cells are checked.
  - Boundaries that must not flag: exactly −5 pp, 0.70, +2 GB and 48 GB, a kind present in both arms, and turn-2 acceptance.
  - An ON gain raises no flag, and A3 uses turn 1 only.
- **`all_cli` (25):**
  - `all` writes the three files and is byte-identical on rerun and across checkout locations.
  - No absolute path, header, section order, only the panel pending, no composite, and CLI equals in-process.
  - `compute_all` and `verify_all` are read-only.
  - Input sha drift, a missing input and a stale or missing B8.json refuse.
  - A1 regrade drift (4 fields, plus rows changed without regrading), and a consistent regrade is accepted.
  - `a7` commands unchanged (class invariant), and the A7 part of `all` equals `compute_a7`.
- **`golden` (20, `p613s2_golden`):**
  - 3 data-only invariants: counts, the A1 rows, and decode, acceptance and M1 numbers (they pass at baseline).
  - 14 reproduces-failure tests on `verify_all` and `compute_all`, covering the contract's B8, rule 6, A1, family, decode, acceptance, A2 to A4, M1 and flag numbers.
  - 3 CLI tests on the committed data.

## Baseline run

```
327 failed, 14 passed, 1 skipped in 140.83s (0:02:20)
```

- **Failure kinds:**
  - Almost all are `AttributeError`: `bench.p426_verify` has no `verify_wave1` (196 first-line occurrences), `verify_all` (94, plus 63 via `conftest.py`) or `cross_wave` (23).
  - The `all` CLI tests fail with argparse usage errors, because only `{a7}` exists.
- **Passed (14):** 10 fixture sanity tests, 3 golden data-only tests, and `test_a7_commands_are_unchanged`.
- **Skipped (1):** `test_golden_committed_outputs_are_the_all_outputs`. The committed `SIGNALS.md` is still the step-1 sheet. The test starts binding once step 2 commits its outputs.
- **Golden commits present:** the golden fixtures got past the commit check at baseline, so the Wave 1 heads and the Wave 2 OFF commit resolve in this checkout.

## Contract ambiguities and the reading I tested

1. **The "249 / 249" SCRUB files.** The committed manifests hold 166 files for the 20 pair legs and 83 for the smoke legs. The 249 is the total including smokes. I pinned both, and require the 166 pair-leg files in B8 `inputs` and none from smokes.
2. **"A4 per draw 1.584–1.656".** The six committed draws are 1.615, 1.623, 1.584, 1.656, 1.634 and 1.528. The quoted range is b1's minimum to b2's maximum. I test all six ratios in the sheet.
3. **Where `request_seeds` lives.** In the committed `ids.json` it is under `axes.reasoning.request_seeds`, not top-level as the contract says. I built and tested the real location.
4. **Block label and key shape.** The label is `b1`, `block1` or `1`; tests compare the digit only. Keys are checked as `[block, id, sampler_seed]` and so on.
5. **Deny-listed member.** The contract leaves open how a member can "resolve" to one, so I model it as a leg dir or row file symlinked to a smoke leg, `archive/`, the S-build `wave1/` or a `p426-*` tune. I expect `RefusalError`.
6. **Id set differs from the block list at equal count.** The contract says "== as sets" without naming the outcome. I accept either a refusal or a rejected pair.
7. **A missing SCRUB_MANIFEST.** I also accept either a refusal or a rejected pair.
8. **`SIGNALS.json` layout.** Key names are not pinned. As in step 1, numbers are located by value in the subtree under a key named `A1`, `A2`, `A3`, `A4`, `M1`, `family`, `flags`, `noise` or `coverage` (case-insensitive prefix). If the layout differs, fix `w1view.py` once.
9. **Order-sensitive numbers.** The permutation p, the Holm inputs, and the geomean CI endpoints (tolerance 2e-3) assume the contract's (block, id) order, with ids sorted as strings.
10. **`verify_all` inputs.** I read "inputs: union" literally: A7 keys relative to `results_root`, Wave 1 keys relative to `rows_root`. I only require the union to contain both sets.
11. **Boundaries.** Exactly −5 pp, 0.70, +2e9 and 48e9 must not flag. The −5 pp case may fail on float noise, which would be an implementation robustness finding.
12. **The CLI and `generate.RESULTS`.** My CLI runner exports `MLX_BENCH_RESULTS=<rows_root>`, so the `all` CLI passes whether or not it sets `generate.RESULTS` itself.
13. **`compute_all` signature.** I call `compute_all(results_root, rows_root, b8, b8_sha256=None)` with an in-memory dict, and rely on `render_md(signals)` still existing from step 1.
