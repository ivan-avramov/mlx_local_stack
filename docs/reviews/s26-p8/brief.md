Cold read, round 1 of 3. You are reviewing a small fix in a benchmark harness repo (read-only; do not edit files).

Real failure (first live run of an M76 tg1 "KV lever" rehearsal): the Wave-2 sequencer stopped at the harvest of leg
`tg1-m76-rehearsal-n16.a1` with two problems:
 (a) "log_bounds.json: the arm's worktree cannot be resolved (pass --worktree)" — `p426_harvest._arm_of` returns None for
     `tg1-m76-rehearsal-n16` / `-x`, and P426's `on` / `off` for `-mismatch` / `-kill`, which a KV record does not name.
     The KV leg table (`benchmark/bench/p426_wave2.py`, `kv_legs`) runs R1 on each arm, R2 (mismatch) on the treatment, R3 (kill) on the reference.
 (b) "watch.jsonl: missing" — the watcher `benchmark/m1/bench_watch.py` died: `ModuleNotFoundError: No module named 'bench'`
     (launched by `BoxSeqOps.launch` without PYTHONPATH; Wave 1's `p426_leg._watcher_for` sets PYTHONPATH=<repo>/benchmark).

Files: fix.diff (the change), test_s26_kv_rehearsal_harvest.py (new tests). Repo: benchmark/bench/p426_harvest.py,
benchmark/bench/p426_wave2.py (kv_legs, BoxSeqOps.launch, start_watcher), benchmark/bench/p426_leg.py (_watcher_for).
Constraints: `_arm_of` must stay byte-unchanged (a golden pins its outputs); a wrong worktree must never yield published evidence.

Questions: (1) Is the fix correct for every leg name the KV tg1 and tg2 tables and the P426 mtp table emit? Trace `leg_worktrees` →
`leg_worktree` for each. (2) Can the new mapping ever pick the wrong arm silently (e.g. record arm order, a v8_base beside the record)?
(3) Does setting PYTHONPATH only for bench_watch.py launches change anything else the sequencer launches or records?
(4) Anything missing in the tests? Answer with numbered findings (severity: blocker / major / minor / nit), each with file:line
and a concrete failure scenario; say "no findings" for a question if none.
