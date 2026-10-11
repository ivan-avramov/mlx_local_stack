You are a cold adversarial implementation reviewer (read-only) for a benchmarking repository. Do not edit files.

Context. C147 is the clearance work for tg1 agentic chains (spec docs/specs/c147-tg1-chain-clearance.md). Its live
injected-positives run (V3) aborted on a new box (macOS, M5 Max): at 04:44:15Z the probe refused "worker identity
missing or drifted" (benchmark/bench/proc_guard.py require_identity, called from benchmark/bench/tg1_runner.py) and,
in the same second, the long-lived driver judged its own router "not the recorded router identity"
(benchmark/bench/chain_ops.py _require_own_router/_alive), although PIDs never changed and a fresh process recomputes
the recorded identity exactly. Diagnosis recorded as C151 in docs/open-questions.md and campaign-results 2026-10-11:
psutil 7.2.2 `_psosx.adjust_proc_create_time` adds `INIT_BOOT_TIME - boot_time()` to `create_time()` once they
differ by >= 1 s; `boot_time()` is whole seconds (kern.boottime usec was 43620 on that box). The clock event itself
was not found in the unified log.

The change under review is the HEAD commit (`git show HEAD`): helper `proc_guard.start_time(proc)` (macOS: psutil's
private `_proc.create_time(monotonic=True)`, else `create_time()`; objects without `_proc` fall back), used at every
identity site in chain_ops.py, proc_guard.py, tg1_runner.py; tests benchmark/bench/tests/test_c151_start_time.py.
The installed psutil is under .venv-bench/lib/python3.12/site-packages/psutil (read its source). You may run:
`cd benchmark && env -u STACK_WORKDIR TMPDIR=$STACK_WORKDIR/c151/tmp ../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/test_c151_start_time.py bench/tests/test_proc_guard.py bench/tests/test_chain_ops.py`
(they start no router or model).

Lens:
1. Is the diagnosis sound? Read psutil's macOS create_time/boot_time/adjust code and say whether the claimed
   mechanism is real, whether another mechanism fits the evidence better (both a probe process started 04:37 and a
   driver started 04:26 failing in the same second; fresh processes agreeing with the recorded values), and what
   evidence would distinguish them.
2. Is `_proc.create_time(monotonic=True)` on macOS exactly the unadjusted kernel start time (same value the
   unshifted public call returns, so previously recorded manifest values stay comparable)? Exceptions it raises?
   Caching differences versus Process.create_time()? Stability across psutil versions given the exact pin in
   benchmark/requirements-bench.lock and uv.lock?
3. Completeness: every place in benchmark/ and scripts/ (non-test) where a process start time feeds an identity,
   ownership, kill or survivor decision, including indirect psutil paths (Process.__eq__/__hash__, parents(),
   children(), is_running(), process_iter caching, oneshot) and the serving side (benchmark/bench/provenance.py,
   benchmark/chains/c147/run_tg1_chain.py, benchmark/m62/inject_verify.py). Is anything left on the adjusted path?
4. Semantics: `start_time(p) < self.started` / `>= self.started` compare a kernel start time with a time.time()
   taken at guard start. Is that correct across a wall-clock correction, and was it correct before?
5. Tests: does shifting `_psosx.INIT_BOOT_TIME` faithfully emulate the event? Do the tests bite (would they fail on
   the pre-fix code)? Is the static guard in test_no_raw_create_time_reads_at_identity_sites too narrow or too broad?
6. Anything in this diff that could kill a process the runner does not own, or certify a process gone that is not.

Output numbered findings R1, R2, ... (severity blocker / should-fix / nit, file:line, concrete change), then a
one-line verdict: "cleared", "cleared after fixes" (list the ids), or "not cleared".
