Findings:

- **L4 — High — unresolved.** `record_problem()` accepts `policy_sha256: null` and permits missing/mismatched `pinned.scaffold_policy_sha256`. A failed policy derivation can produce this state; resume then re-derives and overwrites it instead of requiring a new out-root.
- **L5 — High — unresolved.** `pair_identity()` includes both arm hashes but is unused. `gate_items()` flattens all generation/date-compatible items into one delta, allowing multiple arm-identity tuples to be pooled.
- **L10 — Medium — new.** Effective `--cache-session-retain-prompt-end` is absent from arm identity when omitted by mlx-serve. The worker’s environment/default can change cache boundaries without changing either identity hash.

Confirmed resolved:

- **L1:** Every pinned `_build_command` flag is classified. The three named flags are token-output-inert: memory/cache limits govern allocation, while session shrink acts only during idle retirement and has byte-identical evidence. They can affect availability, not successful output.
- **L2:** Router and worker APC states are hashed; unreadable environments refuse.
- **L3:** Both lifecycle launchers are frozen.
- **L6:** Static reachability plus runtime coverage and the sole `client.py` allow-list close the dead-import path.
- **L7:** Complete-schema/no-current-identity discriminator prevents partial and sidecar-merged rows becoming legacy.
- **L8:** Unscored counters render unknown.
- **L9:** Policy is derived per box, frozen, and reverified; assertion semantics and P351 coupling removal are correct.
- AGENTS.md probe-line edit is correct.
- G1 `proc_guard.py` and P359 production helpers are byte-identical to merged main; no regression found.

VERDICT: CLEARED AFTER FIXES L4 L5 L10
