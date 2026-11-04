I amended the frozen tests as the dispositions list and added `test_p613s3_fixround.py`. I edited only `benchmark/bench/tests/p613s3/`, and committed nothing. Against the unfixed candidate, every fix test fails except one. The whole directory gives 19 failed, 115 passed in 265 s.

## Amended frozen tests
- **W1:** the world's rows carry `final_tree.manifest`, with the run directory in the path.
- **W2 (E2):** `HARVEST.json` has one `evidence` record per events file, `sha256` being the raw row value. The evidence branch holds the scrubbed copy. `test_world_hashes_are_consistent` now checks that binding.
- **R1:** the helpers read manifest paths relative to the panel directory.
- **R2:** `excluded` is read as `{n, ids}`.
- **R3:** the select tests that edit rows call `case.reverify()` (a new B8 run). A new test checks that a stale B8 is refused.
- **R4:** the family tests read `tested` and `m`; `members` is the whole family.
- **R5:** the Wave 1 tests read `score_identical`, and the slot test uses each item's own `sol.go` or `sol.py`.
- **E1:** `test_panel_option_is_optional` replaces the old "required" test. Without `--panel`, rc is 0, the status is `subjective panel pending (step 3)`, and there is no subjective section. With `--panel` and a missing `FROZEN.json`, it refuses (the existing test).
- **E3:** the golden asserts 162, 96 and "not both correct". The hermetic export asserts the eligible count from `case.a1_eligible()`.
- **Dropped:** the identical-item `a7_packet` refusal.
- **Kept:** the model-name leak test.
- **Fix 7 world change:** B8.json and universe.json now sit at committed repo paths, and the world commits them so the tree is clean.
- **Verdict writing:** verdicts come from the code under test. `a7-seal` seals the Claude judge's bare verdicts, and `a7-cursor` runs with a fake `cursor-agent` that answers from a plan file. No test hand-writes provenance or a FROZEN binding.

## Fix tests, each failing on the unfixed candidate

| Test | First error line |
|---|---|
| fix 3 ×3 (`len_on`, `on_slot`, `judge_model` edited in `FROZEN.json` after verdicts) | `rc 0: nothing was refused` |
| fix 4 (forged provenance in a sealed verdict) | `'forged-model' not in <sheet>` fails |
| fix 4 (pre-sealed forged verdict) | `'forged-model' == 'claude-opus-5-5'` fails |
| fix 5 (second `a7-cursor` run) | `a failed packet was called again on the second invocation` |
| fix 6 (exact diff) | `claude-opus-5-5 AB: the diff in the packet differs from the exact diff` |
| fix 7 ×4 (committed-path copy outside the repo, and edited committed file; B8 and universe) | `rc 0: nothing was refused` |
| fix 8 (malformed and invalid-choice Claude verdicts) | `sealing aborted: json.decoder.JSONDecodeError` |
| fix 9 (`a7_packet` signature) | list equality fails on the extra `_ctx` and `_top_ref` |
| fix 10 (duplicate manifest row) | `A7-s1: negative missing_verdicts -1` |
| fix 11 (stray file) | `'.DS_Store' not in FROZEN.json` fails |
| fix 12 (A4 row) | `no member 'A4' in the subjective section` |

**Fix 6 length test does not reproduce.** `test_fix6_judged_length_is_the_rendered_text` passes on the unfixed candidate. It only requires length to match either the exact diff or the rendered section, and the candidate's raw-diff length equals the exact diff here. The exact-diff test is the reproducer.

## Whole-directory run
`19 failed, 115 passed in 265.07s`. The 19 failures:
- 16 fix-round tests (the table above, 17 cases, minus the passing fix 6 length test).
- The model-name leak variant of `test_export_refuses_a_leak` (fix 6).
- `test_panel_option_is_optional` (`REFUSED: --panel <dir> is required`, fix 1).
- `test_golden_export_84_verdicts_planned` (162 not in the FROZEN numbers, fix 2).

## Caveats
- **Fix 10 and fix 11:** both need constructed inputs. Fix 10 hand-edits `manifest.jsonl` and re-freezes it. Fix 11 calls `freeze()` directly with the previous `FROZEN.json` as `packets_meta`. If a fixed `freeze` needs a different metadata shape, fix 11 will error, not fail.
- **Fix 3 on-slot case:** it skips if `FROZEN.json` items carry no `on_slot` key.
- **Fix 7:** this reads "committed repository paths" as the paths under `--repo`, with bytes equal to HEAD. A copy outside the repo is refused even when the bytes are identical.
