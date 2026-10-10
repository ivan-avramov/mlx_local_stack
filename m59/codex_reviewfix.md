**Verdict: SOUND-WITH-RESIDUALS.** Continuing uninterrupted is defensible; arbitrary-point SIGTERM safety is not established.

Pick 1 = `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`; pick 2 = `Qwen3.8-27B-mlx-uniform-4bit`.

**P1 — Q1: FAIL for arbitrary interruption; PASS against signal-to-grade conversion.**
- Injected `SystemExit` reproduced scratch/child leaks between creation and entering `try`, and interruption inside child cleanup. Export’s `_capture` catches only timeout; `Popen.__exit__` then waits without a timeout rather than killing. [Probe:208–304]($STACK_REPO/benchmark/run_opencode_probe_v2.py:208).
- `_stamp_manifest` uses tmp+rename, but initial/resume manifest creation directly truncates the destination. I reproduced an empty manifest. Row append is nontransactional; partial-write risk remains, although I did **not** reproduce a torn JSONL line. `_load_rows` correctly refuses one. [Write sites]($STACK_REPO/benchmark/run_opencode_probe_v2.py:771), [atomic stamp]($STACK_REPO/benchmark/bench/opencode_common.py:541).
- `SystemExit` escapes the `except Exception` handlers, including gate classification and `_abort`; it does not become a graded stall. Interrupting `_abort` can lose diagnostic copies/stamps. A row already committed before the signal remains.

**P2 — Q2: CONCERN, with policy compliance PASS.**
- C136 permits a documented draft-OFF rate; I independently reproduced pick 2’s **51 requests, median 25.4**, including **22.5 at ≥15K context**, from archived row session IDs and worker logs.
- Keeping pick 1 at 24.2 versus observed 24.4 is defensible conservative calibration (~0.8%). I counted **55**, not the documented 56, qualifying requests; median unchanged.
- Completed-request medians are context-dependent and potentially censored by stall kills; they are not a decode floor or an exact 16K-token allowance. At 22.5 tok/s, 630 seconds permits only ~14,175 decode tokens before overhead.
- Selecting the correction after observing eight stalls makes s1 adaptive. Preserve the original arm, disclose the calibration, freeze rates for s2, and avoid confirmatory improvement claims. [C136]($STACK_REPO/docs/open-questions.md:20).

**P3 — Q3: PASS for the current chain; CONCERN for generic resume.**
- **(a)** s2 has distinct directories **and stems**; transcript paths include that stem. No current s2→s1 collision. [Runner:316]($STACK_WORKDIR/m59/run_m59.py:316), [transcripts]($STACK_REPO/benchmark/bench/opencode_common.py:350).
- **(b)** Both skip checks agree for valid files. However, raw line counts accept duplicates/wrong items and bypass manifest validation. Existing retained pick-1 legs have exactly the expected 22 unique IDs.
- **(c)** Boundary unload verifies worker disappearance before reloading; s1 pick 2’s fresh router/load is recorded. But restarting a partially completed model-session can append across loaded instances, violating P161’s one-instance requirement. [Runner:304]($STACK_WORKDIR/m59/run_m59.py:304), [RUNLOG:301]($STACK_WORKDIR/m59/RUNLOG.md:301).
- **(d)** Worker timestamps use local logging time; runner boundaries use local `strftime`. Tags distinguish these two picks, but `mlx-uniform-4bit` is not globally unique. Exact model-field matching would be stronger. [Rate check]($STACK_WORKDIR/m59/run_m59.py:245).

**P4 — Q4: CONCERN; no pooling occurs in this runner.**
The 662/630-second windows implement C136’s same nominal token allowance, not identical measured token budgets. Saved manifests confirm different probe hashes across s1 arms. Report each model/language/session separately with window, rate, hash, seed and loaded-instance provenance; retain old 558-second results separately. No pooled accuracy across sessions/fingerprints, no selective retention of rerun successes, and no clean causal scaffold-delta claim for adaptive s1. The SIGTERM-only code change does not itself invalidate uninterrupted old rows.

**P5 — Q5: CONCERN.**
Archived 558-second rows still point to live transcript paths now overwritten by reruns: `python/beer-song` already differs from its archived copy. Archive analysis must resolve the preserved copies. Also, the runner has no ten-minute inter-arm cooldown, so its wall times cannot support the prescribed clean-box latency comparison.

**P6 — Ranked findings:** **Must-fix before uninterrupted continuation:** none demonstrated. **Should-fix:** interruption handling/transactional persistence; resume identity/completeness and instance boundaries; archive transcript resolution; adaptive-analysis disclosure. **Nit:** pick-1 request-count provenance and globally ambiguous rate tag.

**P7 — Tests:** `17 passed, 1 deselected in 0.04s`; scratch-only interruption tests: `7 passed in 0.04s`—these confirm the residual failures above. Required environment and `-k "not real"` used; signal-sending test excluded. No repository changes, service requests, process signals, or opencode/model launches.