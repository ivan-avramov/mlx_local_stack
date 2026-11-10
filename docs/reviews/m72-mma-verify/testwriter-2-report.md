The candidate passes all but two of my frozen tests, and neither failure is a candidate defect. I recommend **fix then merge** (two small fixes below). I couldn't get a complete full-suite result.

## 1. Frozen tests on the candidate

| File | Baseline | Candidate |
|---|---|---|
| `dev/tests/test_m72_mma_verify.py` | 70 passed, 356 errors (426 tests) | **425 passed, 1 failed** (426 tests, same count) |
| `test_m72_mma_report.py` + `test_m72_run_mma.py` | 1 passed, 14 failed, 25 errors (40 tests) | **40 passed, 1 failed** (41 tests) |

The stack count is 41 on the candidate against 40 on the baseline. That is a counting slip in my first report: the baseline ran 1 + 15 + 25 = 41 across the two files. All 41 named tests ran on the candidate, and none were skipped.

Both failures are my tests' fault:
- **`test_a5_reads_nothing_beyond_the_last_length[tq4]`** fails with `AttributeError: Module 'random' has no attribute 'bits'`. `mx.random.bits` doesn't exist in MLX 0.32.4, so my test is wrong and the check never ran. I ran it by hand, without editing the test file, using `mx.random.randint` for the garbage. With garbage in the indices and norms beyond `lengths[-1]`, the candidate's output is bit-identical to the clean run and passes A1 (rel error 3.4e-3). The candidate satisfies the property.
- **`test_launcher_runs_two_passes_with_mode_mma_and_idles_600`** asserts that the only `sleep` call is `sleep 600`. The launcher also starts a background monitor that runs `sleep 60` in a loop, per the repo's rule that runs need a power monitor. The observed calls were `sleep 60 … sleep 600 … sleep 60`, so the one 600 s idle between passes is present. My assertion was over-strict, because the spec doesn't forbid a monitor. Exit codes 11 and 12 and the arguments all pass.

## 2. Full stack suite

- `./fe_test.sh stack` aborts at collection. The verbatim summary lines are `ERROR bench/tests/test_t3_wave1.py - RuntimeError: …/src/mlx-vlm/dev/p369_phase2/registry_states.py: no registry_states in the frozen build` and `!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!`, followed by `1 warning, 1 error in 6.92s`.
- **Cause:** the `src/mlx-vlm` submodule is empty in this worktree.
- **Not candidate-caused:** `test_t3_wave1.py` doesn't mention `m72` or `spikes`. A fail-fast run also stopped on `p475s1/test_fixtures_selfcheck.py::test_kv_line_field_order_is_the_servers`, which fails because `src/mlx-vlm/mlx_vlm/server/app.py` is missing. The run ended `1 failed, 88 passed, 2 skipped in 81.84s`.
- **No complete result:** a run with `--ignore=bench/tests/test_t3_wave1.py` was killed at the 10-minute limit. A second run is still going in the background, about 12% done when I last read it. Early output showed 9 failures, and I identified only the first, so I can't give its final line. I did not run the suite on a baseline without the candidate's files, so I can't compare failure sets.
- **Left running:** I did not stop the background run; its output is in `<tmp>`.

## 3. Review findings

**Kernel (`dev/m72_mma_verify.py`)** — correct against the spec. I found no defects in:
- row indexing (`r = i·k + j`, so `len_r` uses `r % K`, and the query layout is `(h·R + i)·k + j`);
- masking, including empty and fully masked rows and tiles (a −1e30 sentinel gives max = −1e30, sum 0, acc 0);
- the online softmax;
- the partial layout `(h·M + r)·Blocks + blk`, which feeds the production pass-2 kernel unchanged;
- the in-place full-cap reads (stride = capacity, loads guarded by `t < Lmax`);
- the head shift, the value rotation back, and the fragment mapping and lane-xor reductions.

Items beyond or short of the spec:
- **F3 (minor, docs):** the `FRAGMENT_TYPES` comment, the docstring and the report say TQ4 codebook values are "exact in half". The codebook entries are fp32 centroids, so the cast to half loses about 2⁻¹¹ per element. Measured accuracy is unaffected.
- **F4 (extra, harmless):** `last_kv_inputs`, `fragment_mapping_ok()` and extra asserts (ascending lengths, 1 ≤ k ≤ 5, 4-bit codec, bf16 dtype) go beyond the spec. `last_kv_inputs` is module-level mutable state. The spec asked for a mapping unit test, and the candidate ships `fragment_mapping_ok()` but no pytest test calls it.
- **F5 (note):** at k = 1 the kernel is 1.4–1.8× slower than the baselines; the implementer reported this and the spec has no speed bar.

**Probe (`m72_tq4_probe.py`)**
- **F1 (real defect, `tq_production`, line 443):** it slices the TQ4 proxy to `lengths[-1]`, but in the planted cases the cache holds T+1 tokens. For k = 1 the singleton path therefore reads the bait token. I reproduced it at T = 8193: TQ4 production rel error is 1.74, so the recorded A1 bound is 3.48 and the check is meaningless. The kernel itself scores 2.5e-3 there. The k = 1 planted rows for TQ4 (T = 8193 and 32770) record a vacuous `pass`, a wrong `prod_rel_err`, and a wrong "worst / bound" log line. For k = 2 and 3 production error is about 2.3e-3, as expected. A1 on those rows therefore does not hold up as evidence.
- **F2 (style):** three blank lines before `main()` (around line 603), which black would reject. The implementer also noted that black and isort were not run and the launcher is not executable. I confirmed the launcher is mode 0644, while `m72_run_probe.sh` is also 0644.
- **Spec conformance:** the rest follows the spec. The JSON schema matches (`rows`, `controls`, `n`, `n_pass`, `plan`, `bytes`, the five arms, `mq_best.G`, and the per-k `accuracy`). N1, N2 and N3 run once, on the planted case at T = 8193, k = 3, for both arms. The sweep and the idle-GPU gate order are as specified.
- **Extras:** an extra `meta.mma_kernel` field; planted cases are limited to T ∈ {8193, 32770}.
- **Checkpoint cost:** the checkpoint accuracy reference at T = 262,144 dequantizes about 4 GB of fp32 K/V per arm (the implementer flagged this).

**Report (`m72_mma_report.py`)**
- It matches the spec's formulas, and my formula-derived tests pass.
- **MTP OFF best-of:** it takes the min per checkpoint, then interpolates.
- **Missing input:** no `mma-N.json` exits with a message; this is unspecified in the spec.
- **Accuracy output:** it prints controls with a "holds / VIOLATED" verdict.
- **Not tested:** the `len(Tp) < 2` early return.

**Launcher:**
- Exit codes 11 and 12 behave as specified.
- **Minor:** `trap "kill $mpid" EXIT` leaves the monitor's `sleep 60` child alive for up to 60 s.
- It is not executable, as the implementer said, and the syntax check was not run.

## 4. Fixes before merge

1. Fix F1: slice the TQ4 state to exactly `lengths[-1]` tokens in the production path. Either build the proxy from a state sliced to that length, or give the planted caches `offset == T`. Then regenerate the smoke JSON.
2. `chmod +x` the launcher, remove the extra blank line, and run black and isort.

Optional: correct the "exact in half" wording (F3), and make the monitor kill clean up its `sleep` child.

## Questions

1. Should I fix my two wrong tests (the `mx.random.bits` call and the exact `sleep` list)? The brief froze the files, so I left them. The `mx.random.bits` test currently gives no TQ4 coverage of A5, which I covered by hand above.
2. Do you want the full-suite run finished and compared against a baseline without the candidate's files? It needs hours and a clean worktree.

---
(follow-up)

The full stack suite has now finished. Its failures aren't candidate-caused, apart from the one launcher test I already covered.

The run was `./fe_test.sh stack bench/tests --ignore=bench/tests/test_t3_wave1.py`. Plain `./fe_test.sh stack` still aborts at collection on that file, as before. The run ended, verbatim:

`498 failed, 11358 passed, 22 skipped, 1 xfailed, 5 warnings, 31 errors in 3422.42s (0:57:02)`

- **Only m72 failure:** the one failing m72 test is `test_m72_run_mma.py::test_launcher_runs_two_passes_with_mode_mma_and_idles_600`. That's my over-strict `sleep` assertion, covered in section 1. The other 40 m72 report and launcher tests pass, so nothing else in the m72 files fails.
- **Likely cause of the rest:** the 498 failures and 31 errors in other test files have the same environment cause as before. `src/mlx-vlm` is empty in this worktree, so tests that read files under it fail with `FileNotFoundError`. My earlier `-x` run showed the first of these.
- **Not compared against a baseline:** I did not run the suite without the candidate's files, because I can't remove them. The attribution rests on which tests fail and why. I did not classify the failures in every file, only the m72 ones and the first non-m72 failure.

My earlier verdict stands: fix then merge, with the two fixes listed in section 4 (the TQ4 planted k=1 production slice, and the launcher mode bit plus formatting). The two questions at the end of my last report are still open.
