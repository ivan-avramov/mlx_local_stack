F14 — resolved.  
F15 — resolved.  
F17 — resolved.  
F18 — resolved.  
F20 — resolved.  
F21 — resolved.  
F23 — resolved.  
F24 — resolved.  
F25 — resolved.

F26 — low, `benchmark/bench/atomic_publish.py:17-18` — PID-only temp names collide between same-process publishers or after PID reuse; `O_TRUNC` can corrupt a linked destination. Use random `O_EXCL` temps. Residual hardening.

F27 — low, `benchmark/bench/atomic_publish.py:10,40`; `benchmark/bench/chain_core.py:1672-1674` — broad `.*.tmp.*` sweep can delete unrelated matching dotfiles. Strictly parse publisher-owned names. Residual hardening.

F28 — medium, `benchmark/bench/chain_core.py:2207` — the new language check can raise during hook-stop salvage, aborting resume instead of quarantining a wrong-language row. Catch `ChainRowsError` and leave the invocation unsalvaged. Residual hardening.

F29 — low, `benchmark/bench/chain_core.py:1052-1055` — when `run_id` exists only in the manifest, first-resume recursive temp cleanup is skipped. Derive the evidence root from the manifest before sweeping. Residual hardening.

APFS same-directory fsync-plus-hard-link publication is atomic and non-replacing. No new live cross-process collision exists on macOS because host PIDs are unique. Merge blockers: none; F26–F29 can be tracked.

VERDICT: CLEARED

[exited with code 0]
