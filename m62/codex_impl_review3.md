**Verdict: cleared after fixes—P1 and P2 must be closed before chains; address the concrete cleanup leak in P3.** The ten live rows show no accounting or scoring discrepancy. V4 completed its descriptive experiment but supplied **zero observations of the >41K single-request tail**.

Reviewed HEAD `90cf34f`. No edits, commits, servers, inference, or grading executions. I independently reran the read-only V2 replay: **8/8 criteria pass**.

1. **P1 — MAJOR: V3 is incomplete against its pre-registration.**

   The required seven-item smoke completed successfully, with the correct seeded-random selection. However, [§6 explicitly requires three injected positives]($STACK_REPO/docs/specs/m62-token-turn-gate.md:247): an allocation kill, a no-progress stop, and a K stop. Every live row has null gate stop, empty `mem_kills`, and zero tool-bound rejections.

   **V1/V2 provide substantial coverage, but do not fully compensate.** V1 includes real host-allocation/descendant tests and pinned-client plugin feedback; V2 confirms both historical K fixtures and leaves all 374 valid historical passes unstopped. These do not establish the live worker’s complete **stop → descendant cleanup → cancellation → export reconciliation** path. That distinction matters given the previous cancellation-path defects.

   **Required:** complete the three lowered-threshold positives and retain evidence of the expected outcome, worker cancellation, reconciliation, and cleanup. The seven successful smoke items need not be rerun.

2. **P2 — MAJOR: the current launcher must not be reused unchanged for a chain.**

   [The M62 driver delegates to the M59 runner]($STACK_WORKDIR/m62/run_m62_live.py:52), which retains:

   - A fixed [six-hour leg timeout]($STACK_WORKDIR/m59/run_m59.py:30).
   - [`subprocess.run(..., timeout=...)`]($STACK_WORKDIR/m59/run_m59.py:229), whose timeout kills the probe itself, bypassing its Python cleanup.
   - A [row-count-only “complete” shortcut]($STACK_WORKDIR/m59/run_m59.py:209), without checking exact IDs, manifest validity, or terminal provenance.

   `stack_stop.sh` stops serving processes and compose; it does not replace tg1’s owned-client/grader cleanup. None of these paths fired during V3/V4, so **this does not invalidate their rows**.

   **Required before chains:** a runner with deliberate timeout/cancellation handling, verified descendant/container cleanup, exact-item and manifest validation, and the [specified incomplete-leg archival/fresh-instance restart]($STACK_REPO/docs/specs/m62-token-turn-gate.md:269). Derive scheduling estimates from the pilots with explicit heavy-tail allowance; their short successful attempts cannot justify a tight tail bound.

3. **P3 — MINOR: process cleanup is clean, but one model-created file escaped cleanup.**

   `Qwen3.8-27B-mlx-uniform-4bit`, `go/alphametics`, seed 2002, request 10 wrote `/tmp/bench199_test.go`, copied it into the exercise, then removed only the exercise copy. [The original file remains](/tmp/bench199_test.go), matching the transcript’s content and timestamp. SHA-256: `4fed72eb64b141ccd660bbda95461cbe1bc5b7787caa54bbf32401cefee5fc1d`.

   This is a real artifact-location/cleanup gap: setting `TMPDIR` does not contain hard-coded `/tmp` writes. It is **not evidence of a surviving process or incorrect grade**. Arrange targeted cleanup and explicitly address this escape before chains; do not introduce a blanket `/tmp` sweep.

   The process evidence otherwise checks out:

   - `orphans_unattributed`: **108 distinct identities**—106 `mdworker_shared`, one `com.apple.iCloudHelper`, one Zoom updater. These are consistent with unrelated system/application activity; none has path-only attribution.
   - Current identity-aware inspection found **zero benchmark process matches**, zero `mlxbench-*` containers, and no listeners on ports 8000/8091.
   - The [run log]($STACK_WORKDIR/m62/RUNLOG.md) records successful unloads and final stack shutdown; `live.rc` is zero.

   Retain the orphan diagnostics. They are noise here, not proof that best-effort tracking can never miss an escape.

4. **P4 — MINOR: accounting is independently reproducible; exact intermediate grades have weaker retained evidence.**

   Every row passed these checks:

   - **69 requests** matched row usage, export message IDs, event finishes, and server completion records by session/order. There were 59 `step_finish` events plus ten final export-only completions, each charged once.
   - Output, cache-aware prompt totals, and resolved budgets match. Every budget is **81,920**; zero budget hits is correct. Final server/export finishes are `stop`.
   - **All 30 evidence SHA-256 values match.**
   - All five manifests match current code identity `a2e319f0…`, policy identity `ba86ba16…`, carrier/plugins/universe, and the pinned executable.
   - Retained client logs show **both plugins loading for every live item**; copied plugin/carrier hashes match.
   - Worker identities match before/after each item. V3 shares PID 66567; V4 uses distinct fresh workers 68527, 69158, and 69906. Router/config identity remains unchanged.
   - Zero tool-bound rejections agrees with the exported calls.
   - Changed solutions, untampered final grades, passing tool-test output, and convergence evidence support all ten `passed=true`, `converged=true` results.

   Progress accounting also matches the transcripts. For example, `go/forth` records **48 → 17 → 9 → 11 → ungradeable → 0**: the regression earns no credit. `python/food-chain`’s equal-count rewrite earns none; `python/book-store`’s first write still fails all 20 tests and earns none.

   **Limitation:** [structured grader reports are deleted with their temporary directory]($STACK_REPO/benchmark/bench/structured_grade.py:245). Thus exact intermediate failing counts are not independently recoverable from retained grader reports, although their arithmetic and transcript consistency check out. Retaining hashed grader reports/snapshot manifests would improve auditability; this is **not a demonstrated scoring defect or an additional clearance gate**.

5. **P5 — NIT: V4’s summary omitted first-write timing; the evidence supports only a short-path descriptive result.**

   The prescribed items, seeds, and fresh loads were used. Recovered first-write timing below is measured from the first assistant message’s creation.

   The first two rows used `Qwen3.8-27B-mlx-uniform-4bit`; the third used `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`.

   | Item / seed | Requests | Total output | Max request | First write | Wall |
   |---|---:|---:|---:|---:|---:|
   | go/alphametics / 1001 | 6 | 6,000 | 5,079 | request 4; 213.4 s | 249.3 s |
   | go/alphametics / 2002 | 12 | 14,037 | 10,666 | request 6; 513.2 s | 591.9 s |
   | python/book-store / 2002 | 7 | 11,608 | 10,794 | request 3; 456.1 s | 502.5 s |

   All three are strict passes, with **zero budget hits and zero requests crossing 41K**. [Server completion evidence]($STACK_REPO/logs/mlx_vlm.log:95342) agrees with these totals.

   V4 shows that these fresh attempts solved the selected items through much shorter trajectories. It does **not** show that the censored M61 streams would have recovered, estimate success conditional on reaching 41K, measure long-stream cancellation, or establish tail cost. **M61 remains the record.** V4 meets the experiment’s descriptive scope once the missing first-write reporting is supplied; lack of tail exposure is not grounds for claiming tail certification.