P1  
- Location: `dev/m72_mma_verify.py`, online-softmax sentinel.
- Severity: major.
- Evidence: confirmed, source-traced and mathematically reproduced.
- Problem: `-1e30` participates as a real maximum. Valid scores below it are treated as masked; `empty = m_run == NEG` then discards the row.
- Scenario: native16 bf16 Q/K around ±2⁵⁰ produce finite scores near −2×10³¹. True attention is valid, but the kernel returns zero.
- Proposed change: track whether a row has any valid token; use `-INFINITY` for reduction and emit `-1e30` only for genuinely empty partials.

P2  
- Location: `dev/m72_mma_verify.py`, `FRAGMENT_TYPES["tq4"]` and Q-fragment initialization.
- Severity: major.
- Evidence: confirmed, source-traced range proof.
- Problem: rotated bf16 queries are cast to half. Legal bf16 inputs can overflow half while remaining finite in production.
- Scenario: every query component is 2²⁰. After scaling and an orthogonal 256-D rotation, at least one component is ≥65,536, exceeding half’s 65,504 maximum and creating Inf/NaN.
- Proposed change: use float Q/K fragments for TQ4, which still fits the stated threadgroup-memory budget, or explicitly restrict and validate query range. Add a high-magnitude test.

P3  
- Location: `benchmark/spikes/m72_tq4_probe.py`, `tq_production()`.
- Severity: major.
- Evidence: confirmed by source trace and the supplied GPU reproduction.
- Problem: the k=1 planted TQ4 production comparison can read the hidden T+1 bait token. Its error rises to about 1.74, inflating A1’s relative-error allowance to about 3.48.
- Scenario: planted T=8193 or 32770, k=1; a seriously wrong kernel can receive `pass=True`.
- Proposed change: use genuinely sliced states and the explicit per-query production path, not `singleton_reference` with only proxy metadata. Regenerate results.

P4  
- Location: `m72_run_mma.sh` and `m72_mma_report.py:load()/t()`.
- Severity: major.
- Evidence: confirmed, source-traced.
- Problem: the launcher leaves old JSON files in reused output directories, while the report averages any files named `mma-1.json` and `mma-2.json` without checking provenance or compatibility.
- Scenario: a rerun writes new `mma-1.json` but pass two fails, leaving an old `mma-2.json`; the report averages different kernels or devices and labels everything with pass-one metadata.
- Proposed change: remove or atomically replace each intended output before running; add a run ID and reject mismatched fork SHA, dirty state, device, MLX version, kernel configuration, checkpoints, and plans.

P5  
- Location: `m72_tq4_probe.py:measure_checkpoint_mma()`, `tq_bytes` and `eff_GBps`.
- Severity: major.
- Evidence: confirmed, source-traced.
- Problem: TQ4 byte accounting uses full-cap raw states, while the kernel reads only T tokens. Native16 correctly uses T.
- Scenario: at T=8192 with cap=262144, TQ4 effective bandwidth is overstated by roughly 32×.
- Proposed change: compute logical bytes for the first T rows of norms and indices, or use sliced-state byte counts.

P6  
- Location: `m72_tq4_probe.py:measure_checkpoint_mma()`.
- Severity: major.
- Evidence: hypothesis; fixed ordering is confirmed, magnitude is unmeasured.
- Problem: every checkpoint measures native16, TQ4 production, two MQ variants, MMA TQ4, then MMA native16. Both passes repeat this order, so thermal/frequency drift is confounded with implementation.
- Scenario: long-context measurements heat or throttle the GPU before either MMA arm, systematically worsening their reported ratios.
- Proposed change: counterbalance or randomize arm order between passes and reapply the idle gate after the accuracy sweep.

P7  
- Location: `test_m72_mma_verify.py:test_a5_reads_nothing_beyond_the_last_length`.
- Severity: major.
- Evidence: confirmed by the supplied test run.
- Problem: `mx.random.bits` does not exist in MLX 0.32.4. The frozen suite fails and TQ4’s beyond-length masking test never executes.
- Scenario: a future loader reads packed words beyond `lengths[-1]`; the intended A5 regression test provides no protection.
- Proposed change: generate uint32 garbage with supported `mx.random.randint` calls.

P8  
- Location: `fragment_mapping_ok()` and `test_m72_mma_verify.py`.
- Severity: minor.
- Evidence: confirmed, source-traced.
- Problem: no test invokes the mapping diagnostic, and the probe merely records `False` rather than stopping. The diagnostic also covers only a non-transposed float load, not the transposed half/bfloat loads and MMAs relied upon.
- Scenario: an MLX/Metal change alters transpose or typed-fragment behavior; the probe continues with an invalid kernel.
- Proposed change: test known matrix products for every operand type and transpose mode, and abort the probe if verification fails.

P9  
- Location: `m72_mma_report.py:accuracy_lines()`.
- Severity: minor.
- Evidence: confirmed, source-traced.
- Problem: A3 is declared to hold for any nonempty control list whose included rows fail. It does not require all six unique N1–N3 × two-arm controls.
- Scenario: JSON containing only one failed control is reported as “A3 holds.”
- Proposed change: validate the exact six `(name, arm)` pairs before certifying A3; add truncated/duplicate-control tests.

P10  
- Location: `benchmark/spikes/m72_run_mma.sh`, file mode.
- Severity: minor.
- Evidence: confirmed; the diff creates it as mode `100644`.
- Problem: the documented direct invocation fails with permission denied. Tests conceal this by invoking `zsh script`.
- Scenario: `benchmark/spikes/m72_run_mma.sh out` cannot start.
- Proposed change: set mode `100755` and test executability.

P11  
- Location: `test_m72_run_mma.py:test_launcher_runs_two_passes_with_mode_mma_and_idles_600`.
- Severity: minor.
- Evidence: confirmed by source and supplied test run.
- Problem: the frozen test requires the complete sleep list to equal `["sleep 600"]`, but the candidate’s extra monitor sleeps for 60 seconds. This creates a false A6 failure.
- Scenario: the correct 600-second inter-pass idle occurs, yet the test fails.
- Proposed change: assert exactly one inter-pass `sleep 600` while allowing monitor sleeps, or remove the beyond-spec monitor.

P12  
- Location: `dev/m72_mma_verify.py`, `FRAGMENT_TYPES` comment/docstring.
- Severity: minor.
- Evidence: confirmed, source-traced.
- Problem: fp32 codebook centroids are explicitly cast to half and therefore are not “exact in half.”
- Scenario: reviewers infer lossless operands when the kernel actually introduces centroid rounding.
- Proposed change: describe the conversion accurately and justify it through measured A1 accuracy.No follow-up needed; its findings were already incorporated.
