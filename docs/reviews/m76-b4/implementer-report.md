## B4 report: tg2 legs in P426 lever `kv` (A8)

Criteria 1 and 3 are met in the CPU copy, with red-first evidence and a byte-identical tg1 golden. But no tg2 leg can run on the GPU yet: the tg2 probe and corpus don't exist (Q1), so criterion 2 stays blocked even after this lands.

### Files changed
- `benchmark/chains/c147/run_tg1_chain.py`: I chose a corpus selector plus a sibling module. New flags `--corpus tg1|tg2` (default tg1) and `--tier screen|decider`. tg2 requires `--p426 --lever kv` and refuses `--tier` without tg2, rehearsal and make-up mode. Under tg2:
  - Leg kinds: `pilot` is the 4-item smoke; `chain s1` at `--tier screen` is the screen; `chain s1|s2|reload` at `--tier decider` are the decider legs.
  - `tg2_config` keeps the `tg1-p426` config id and the `p426_continue` transport policy.
  - At entry: the draw is verified, the out-root must be named `tg2-m76-<arm>-<kind>.a<n>`, and the leg refuses if the tg2 probe entry is missing.
  - `check_frozen_record` needs `corpus: tg2`, a matching `tg2_draw_sha256`, and the tier listed in `tg2_tiers`; a tg2 record never runs a tg1 leg.
  - Chain hooks: the schedule comes from the draw, the draw is re-verified before every language leg's launch, and every language needs docker.
- `benchmark/chains/c147/run_tg2_chain.py` (new, pure, no box access):
  - **Draw:** checked against the committed `.sha256` file next to it, canonical bytes, seed 6501, the four languages, tier prefixes.
  - **Items and schedule:** in tg1 P426 shape. Language order is rust, javascript, java, cpp; s2 reverses it. Seeds are 1001/2002; the reload is the first 5 rust items at 1001.
  - **Grader mapping:** a `tg2_grade` result becomes a `GradeOutcome` and an item record. `passed` = parsed with zero failing leaves AND converged; a DNF gets `passed=None`.
  - **C169 positives:** per language the smoke item's stub must grade FAIL and its reference PASS; `run_positives` drives the materializer and grader, injectable for tests.
- `benchmark/bench/p426_wave2.py`:
  - **Leg table:** `kv_tg2_legs` runs the smoke pair, then the positives gate, then screen, s1, s2, reload, always (C338). The first arm alternates: screen ref, s1 test, s2 ref, reload test.
  - **Deadlines:** a tg2 deadline is 1.5 × Σ items × `w_<lang>_s` + 1800 s, with walls taken from the amendment and no default; it is checked before launch.
  - **Gates:** `ensure_tg2_positives` is re-judged on resume and recorded in `sequence.json`. If `amendment.json` is absent after the smoke pair, the sequence stops (Q2).
  - **CLI and harvest:** `--corpus` (run, lever kv only); `BoxSeqOps` publishes under `benchmark/results/m76/wave2-tg2/`.
- `benchmark/bench/p426_harvest.py`: `namespace_root` accepts `wave2-tg2` under lever kv only. The spec path needs it, though the brief only allowed harvest edits where tg2's grader output differs.
- `benchmark/bench/p426_signals.py`: adds `a8_decider_inputs` and `a8_decider_verdict`. They build s1/s2 rows plus per-item languages (screen and reload excluded; DNFs and duplicates refused) and call `m76_rule.axis_verdict("A8", 1, a, b, languages=…)`, which applies α* and the C339 HOLD. `p426_verify.py` is unchanged.
- Tests: `bench/tests/test_m76_b4_impl_golden_tg1.py` and `bench/tests/test_m76_b4_impl_tg2.py`.

### Commands and results
- **Golden first:** I wrote `test_m76_b4_impl_golden_tg1.py` and pinned it on the unchanged code: 3 passed. It hashes tg1 `parse_args`, `ChainConfig` and schedule (mtp and kv, all sessions), plus the Wave 2 leg tables, argv, deadlines and out-roots. It is still green after the change.
- **Red first:** on a pristine HEAD copy (`scratch/pristine`), `test_m76_b4_impl_tg2.py` gave 23 failed; the golden passed 3.
- **After the change:** `../fe_test.sh stack` on both new files gave 26 passed. The final rerun of the two new files, the two consumer guards and `test_m76_b3_impl_wave2.py` passed with no failures.

### Per criterion
1. **Met.** Tests cover:
   - tier prefixes and nesting (40/80/4), with s2 reversed;
   - reload = first 5 rust items at seed 1001;
   - sha refusal for a byte change, an item swap, and a re-pinned `.sha256` over a redrawn draw, plus a mid-leg change caught before the next launch;
   - grader outcome to item record mapping, including the strict convergence rule;
   - leg names, argv the chain accepts, out-roots, `wave2-tg2` paths;
   - the positives verdict and gate;
   - A8 inputs;
   - `--corpus tg1` byte-identical (golden).
2. **Not run.** It needs the GPU, and the tg2 probe it depends on doesn't exist (Q1).
3. **Met, with caveats.** I ran the `-k "m76_b3 or p426 or tg1 or tg2 or chain_core or chain_rows or closures or campaign_core or m76_b4"` selection on both trees:
   - The modified tree went through `fe_test.sh`; pristine HEAD ran via the venv python directly. Their environments differ: pristine fails 85, modified 50.
   - The modified tree shares 48 failures with pristine; these come from the copy itself (empty `src/`, no `.venv-bench`).
   - Only two failures were new: `test_p371_chain_rows::test_the_consumer_enumeration…` and `test_p371_r7_consumers::test_no_module_reads_chain_rows…`. Both were tripped by path or stem string patterns in my code. I fixed them (`CHAIN_ENTRY` parts, `schedules.flat_stem`) and both pass now.
   - An earlier broader baseline run was stopped at the 10-minute background limit and isn't counted; I also edited files while it ran.

### Not satisfied / questions
- **Q1:** No `benchmark/run_tg2_probe.py` or `bench/corpus_tg2.py` exists (M65 build step 3), and neither is in B4's scope. So every `--corpus tg2` leg refuses at entry, before anything is written. My mapping helpers are what a tg2 corpus would call. That probe/corpus is a prerequisite for criterion 2 and needs its own scope. `probe_data` is tg1's for now.
- **Q2:** tg1's pilot gate (`fz.write_amendment`) doesn't fit a 4-item tg2 smoke, and `p426_freeze` is outside scope. So the sequencer stops after the smoke pair until someone writes `amendment.json` with `w_rust_s`, `w_javascript_s`, `w_java_s` and `w_cpp_s`. Who writes it?
- **Q3:** These are my own calls; please confirm or change:
  - language order rust, javascript, java, cpp (the spec's listing; `schedules.tg2_tier` uses sorted order);
  - the smoke is the first item per language at `--tier screen`;
  - the first arm alternates across screen, s1, s2, reload;
  - a tg2 DNF is refused in A8 rather than scored, and tg2 has no make-up or rehearsal legs.
- **Q4:** Whether the harvest accepts tg2 grade-receipt files (`seq-NNNN/phases.json` and others) is untested; it needs real output.
- Nothing is committed. No background waiters are left. The `scratch/pristine` copy and the run logs are still in scratch.