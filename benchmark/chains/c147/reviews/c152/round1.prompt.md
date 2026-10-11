You are a cold adversarial implementation reviewer (read-only) for a benchmarking repository. Do not edit files.

Context: C147 (docs/specs/c147-tg1-chain-clearance.md) clears tg1 agentic chains with three live injected positives
(stall, loop, alloc). On the live box the model refused the alloc addendum (a purposeless 1 GiB `bytearray`
allocation) on all three seeds, so alloc was never observed (campaign-results 2026-10-11; open-questions C152).
The operator ruled: trigger it on what the model already runs, with a lower threshold.

Change under review: the uncommitted working tree (`git diff` plus the new file
benchmark/bench/tests/test_c152_tool_scope.py). Two parts:
1. C152 — benchmark/bench/tg1_runner.py: INJECT_POLICY["alloc"] = hygiene {tool_per_process: 24 MiB, tracker_s: 0.1};
   no alloc addendum (prompt = campaign prompt; prompt_addendum_sha256 None); run_item passes tool_per_process and
   interval=hygiene["tracker_s"] to ProcessGuard (campaign: tool_per_process None, interval 0.5 as before).
   benchmark/bench/proc_guard.py: `tool_descendants` (sticky) = tracked model-role processes whose tracked parent is
   model-role; for those the limit is min(per_process, tool_per_process) with mem_kills scope "tool" (else "process";
   aggregate kills "aggregate"). Measured on the box: opencode 2.0.20 runs a simple shell command as a DIRECT child of
   `opencode serve` (no shell in between); serve's other children were only `git` at ~3 MiB; no LSP started after a
   .py write; pytest on a python item peaks ~40 MiB for ~0.2 s; a guard tick costs ~13 ms over ~520 processes.
   benchmark/m62/inject_verify.py: alloc PASS = >= 1 kill, all role model and scope tool, first kill rss > tool limit,
   linked by tool_call_id to exactly one shell call, request linkage, killed part shape, continuation.
2. P273 — new benchmark/bench/opencode_export.py run_export() (added to BOTH code-identity module lists: the M61 probe digest in run_opencode_probe_v2.py and the tg1 `modules` list): both export paths (the M61 `_export_session` and the tg1
   terminal-path export in tg1_runner) run `opencode session export --standalone` with OPENCODE_PRINT_LOGS=1 on a
   copy of the env and retry ONLY when the export failed and its stderr contains "database is locked" (0.5 s pause,
   10 s bound); every other failure aborts as before; the abort message carries the stderr tail. Root cause: the
   export's private `serve` dies on SQLite "database is locked" while the stopped client's server is still writing.

You may run: `cd benchmark && env -u STACK_WORKDIR TMPDIR=$STACK_WORKDIR/c152/tmp ../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/test_c152_tool_scope.py bench/tests/test_c147_inject.py bench/tests/test_c147_inject_verify.py bench/tests/test_proc_guard.py`

Lens: (a) can the tool limit kill anything that is not a model tool process (opencode serve, its git, the client,
the worker, the router) or kill under the campaign scaffold; (b) can alloc PASS without a real tool-process kill
linked to a shell call, or FAIL on a legitimate one (multiple kills, reparented tool processes, compound commands
through a shell); (c) is the campaign policy hash and every campaign behaviour unchanged (tool_per_process absent
from pg.POLICY; interval 0.5); (d) P273: can the retry mask anything other than the lock (e.g. a crashing export,
a hung export, a wrong session), loop unboundedly, or change export stdout parsing; is OPENCODE_PRINT_LOGS=1 on the
export env safe for M50/hermetic-env checks; (e) tests: do they bite on the old code. Numbered findings T1, T2, ...
(severity, file:line, concrete change). Final line: "cleared", "cleared after fixes" (ids), or "not cleared".
