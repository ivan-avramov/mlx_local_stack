All the amended and new tests pass on candidate 2. I recommend **merge**. The one thing I'd still raise is a minor cosmetic point (finding 1 below). I did not fix anything in the candidate, and I did not run the full stack suite.

## Commands (verbatim) and results on candidate 2
- `./fe_test.sh fork dev/tests/test_m72_mma_verify.py`: **427 passed**.
- `./fe_test.sh stack bench/tests/test_m72_mma_report.py bench/tests/test_m72_run_mma.py`: **81 passed** (63 report, 18 launcher and argparse).
- `./fe_test.sh stack-gpu bench/tests/test_m72_mma_probe_gpu.py`: **30 passed**.
- `./fe_test.sh stack bench/tests/test_m72_mma_report.py bench/tests/test_m72_run_mma.py bench/tests/test_m72_mma_probe_gpu.py bench/tests/test_m72_gpu_idle_gate.py -rs`: 92 passed, 1 skipped. The skip is the whole GPU probe file under the stack venv.

## Baseline
I could not remove the candidate's files, so the baseline column is by reasoning only. It was not run.
- The new modules and scripts don't exist at baseline: `m72_mma_verify.py`, `m72_mma_report.py`, `m72_run_mma.sh`.
- The baseline probe has no `--arm-order`, no mma mode and no `tq_production`.
- So every test that touches them would fail or error there. The instrument-only tests (about 70 in the fork file) pass either way.
- The baseline v1.1 candidate did show the bug that the production-reference test targets (rel error 1.74 at k=1). I replayed it again today: 50.3 at k=1 versus 3.1e-3 on candidate 2.

## Amendments to the frozen tests
- **`test_a5_reads_nothing_beyond_the_last_length[tq4]`:** the garbage is now int32 random bits viewed as uint32. It runs and passes on candidate 2; before, it never ran.
- **`test_launcher_runs_two_passes_with_mode_mma_and_idles_600`:** it now asserts exactly one `sleep 600`, between `uv mma-1.json` and `uv mma-2.json`, in a shared sequence log. The monitor's `sleep 60` calls are allowed. The fake `uv` and `sleep` now also write to `seq.log`.
- **A1 floor:** the judge helper uses 2⁻¹² (spec v1.2). All 427 fork tests still pass with it.

## New tests, all passing on candidate 2
| Item | Tests | Class |
|---|---|---|
| 1. Production reads exactly [0, lengths[j]) | 5 TQ4 (k=1…5), 2 native16, 2 bait-visible instrument checks, 2 probe-reference checks, 2 recorded-row checks, all on the T+1 planted layout (8,193 tokens). The k=1 TQ4 case reproduces the defect. | fix / invariant |
| A1 floor in the probe | 8 (floor value, 2⁻¹² bound, bound scaling with production error) | new |
| 2. Launcher | exit 10 for `mma-1.json`, `mma-2.json` or both (nothing run, nothing overwritten); unrelated files don't refuse; pass 1 `--arm-order forward`, pass 2 `reverse`; mode 755; runs directly and refuses directly | new |
| 3. `--arm-order` | AST test (flag exists, default forward); real parser choices `{forward,reverse}` / `{full,mq,mma}`; invalid choice exits 2; JSON `meta.arm_order` recorded for default, forward and reverse; the five timed arms really run in forward/reverse order at every k | new |
| 4. Exit 6 | `main --mode mma` exits 6 with the mapping check forced False and the sweep, the checkpoint measurement and cache creation set to raise; no JSON written; the gate is specific to mma mode; `meta.mma_kernel.fragment_mapping_ok` is True on this GPU | new |
| 5. Report | refusal for each differing field (`fork.head`, `mlx`, `device.architecture`, two checkpoint-T variants) in both passes; refusal names the field; identical provenance and a single pass combine; each pass's arm order printed in order; "A3 holds" stated once per good pass and not for six bad variants (missing, duplicated twice, one passing, extra, none) | new |
| 6. Fork | `fragment_mapping_ok()` is True | new |

For item 4 the power gate and idle-GPU gate are replaced in the test (`power_state` returns 140 W / 28 V / 80 %, `gpu_idle_ok` returns True). So those tests don't depend on box state or another helper on the GPU. The real `fragment_mapping_ok` is patched only in the exit-6 tests.

## Findings on candidate 2 against spec v1.2
No defects found. All eight fix-round items are in place:
- **Production slice:** `m72_tq4_probe.py:447-454` slices the TQ4 state for real.
- **Floor:** `A1_FLOOR` is 2⁻¹² (`:407`), the report heading says 2⁻¹², and `last_kv_inputs` is gone.
- **Arm order:** `ARM_ORDERS` (`:408`) and the per-arm functions run in order (`:606-609`).
- **Mapping gate:** `main()` exits 6 (`:664-667`) after the idle gate and before `fork_sha` and the sweep.
- **Report:** `provenance_mismatch` and `a3_verdict` (`m72_mma_report.py:59-91`).
- **Launcher:** it is `-rwxr-xr-x` and refuses with exit 10 before creating anything.

Minor points, none blocking:
1. A cosmetic point: `--arm-order` is accepted with `--mode full` or `mq` and silently ignored; it only matters for mma.
2. `trap "kill $mpid" EXIT` in the launcher can leave the monitor's `sleep 60` child alive for up to 60 s.
3. `ARM_ORDERS` sits between the A1 constants (`:408`), which is style only.
4. Each JSON key order now follows the run order, which is harmless.
5. The fix report's observation that the kernel and production rel errors are equal to four digits on planted k=1 rows is real: both outputs round to the same bf16 values. The metric can't separate the two paths there.

## Verdict
**Merge.** Open points:
- I did not run `zsh -n` on the launcher (blocked by the permission check). It ran correctly under fake `uv`/`sleep`/`pmset`, both via `zsh <file>` and directly.
- The probe's real checkpoint loop was exercised in the test only at T=4096 with stubs elsewhere. The full A7 smoke (`--max-t 32768`) is the implementer's, and I did not re-run it.
- The designer's full stack suite is still outstanding.

Files are in `../mlx-vlm/dev/tests/` and `benchmark/bench/tests/`:
- test_m72_mma_verify.py
- test_m72_mma_report.py
- test_m72_run_mma.py
- test_m72_mma_probe_gpu.py
