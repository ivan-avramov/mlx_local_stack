**Verdict: merge.** Every test passes on the fixed candidate, all 16 fixes are resolved, and I found nothing a fix broke. Two minor mask gaps and one coverage note follow.

## Results (fixed candidate, from `benchmark/`)

```
$ ../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/p613s2 -rs --tb=short
388 passed, 1 skipped in 261.69s (0:04:21)

$ ../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/p613 bench/tests/test_p371_r7_consumers.py bench/tests/test_p426_wave1.py
274 passed in 89.17s (0:01:29)
```

- **Same tests ran:** 388 passed plus 1 skipped is 389, the same count as in delivery 3, and the 274 neighbours are the same count as in delivery 2.
- **The one skip:** `test_golden_committed_outputs_are_the_all_outputs`, because the committed `SIGNALS.md` is still the step-1 sheet. It binds only once step 2 commits its outputs, so the "`all` reproduces the committed files" check has not run yet.
- **Frozen tests untouched:** `diff -rq .p613-material/frozen-d3/p613s2 benchmark/bench/tests/p613s2` shows no differences, apart from `__pycache__`.
- **Failing tests:** there are none. The fix report says 9 tests failed for the implementer, but those are the delivery-1 tests I amended in delivery 3, and they pass now. The amendments, not the candidate, were what resolved them.

## Fixes against the dispositions

| Fix | Resolved | Evidence |
|---|---|---|
| 1 | yes | The default world now accepts all 10 pairs. Smoke manifest problems are recorded under `scrub_coverage`, never refused, and smoke files are out of `inputs` (`fix01` tests pass; `inputs` 979→886). |
| 2 | yes | `_w1_budget_reasons` (`p426_verify.py:1012`) compares per key and requires 81920 on every manifest, A4 params and A1/A2 row. It goes slightly beyond the contract by also checking manifests and A4 params; that is consistent with the `@81920` label. |
| 3 | yes | Only the leg's own `stack-p426-s2-<arm>` component is normalised; a swapped arm is rejected. |
| 4 | yes | Identity text must be a string and, for A1/A2, `content_sha256` must be 64-hex, else refusal. |
| 5 | yes | `Reader(confine=True)` refuses an input that resolves outside `rows_root` (`:80`). The A7 reader keeps `confine=False`, so step 1 is unchanged (neighbours 274 pass). |
| 6 | yes | `A1.both.quality`; the golden 0.96 is present. |
| 7 | yes | The family is labelled INCOMPLETE when one A1 block is rejected. |
| 8 | yes | Acceptance is summed over all ON rows of an accepted block (320/500 and 720/1000 in the fix08 test). |
| 9 | yes | Keys are sorted by (block, key), and the CI matches the oracle exactly. |
| 10 | yes | Walls and identity come from accepted pairs only. |
| 11 | yes | Every flag lists its keys or legs with both arms' values. |
| 12 | yes | `mask_paths` turns paths into `<path>` (see below). |
| 13 | yes | Reasons read `rule N: pair <kind> <block>: …` and name both values. |
| 14 | yes | The deny pattern is `(^|[/.])p426-(off|on)-`. |
| 15 | yes | `render_md` dispatches on `generator_version`; the A7 output is byte-identical. |
| 16 | yes | A rejected key has 3 elements, like an accepted one. |

## Findings (probed with `mask_paths`)

1. **Minor: the mask leaks past a space.** `'--model /Users/zed/My Docs/x.py'` becomes `'--model <path> Docs/x.py'`, and `--cfg="/opt/a b/c"` becomes `--cfg="<path> b/c"`. The part after a space survives. The leaked fragment names no user or host, but not the whole path is masked. The fix report acknowledges the narrow rule. A tighter pattern or a note is optional. <!-- allow-pii-pattern -->
2. **Minor: the mask is narrower than "any path".**
   - Windows paths such as `C:\Users\zed\x` are not masked.
   - `$STACK_WORKDIR/…` placeholders are left as they are, which is the implementer's documented choice.
   - Over-masking is harmless: `/v1/models` becomes `<path>`, and `file:///Users/zed/x` becomes `file:<path>`. <!-- allow-pii-pattern -->
3. **Note: the committed outputs do not exist yet.** The golden numbers (96/100, 249 SCRUB files including the smokes, flags) are verified through the frozen golden tests and the byte-identical `all` CLI run on the committed data. The step-2 outputs are not committed, so the skipped test is the last gate that the committed files equal the `all` outputs.
4. **Checked, no regression:**
   - Neighbours: `p613`, `test_p371_r7_consumers.py` and `test_p426_wave1.py` all pass (274).
   - Step-1 `a7` is unchanged: the `a7` commands, the embedded A7 record and the `compute_a7` header all pass their tests.
   - Output hygiene: no absolute path in the outputs, and the `all` outputs are byte-identical on rerun.
   - Flags: the unflagged cells are correct, and no flag is raised on the committed data other than A2×3, A3×3 and cross-wave.
