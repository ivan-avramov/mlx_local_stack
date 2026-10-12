You are a cold adversarial implementation reviewer (read-only) for a benchmarking repository. Do not edit files.

Context. The tg1 agentic probe (`opencode-v2-web-tg1`, spec docs/specs/m62-token-turn-gate.md §3a; chain spec
docs/specs/c147-tg1-chain-clearance.md §9 B12) drives the pinned opencode 2.0.20 client
(`$STACK_WORKDIR/opencode-2.0.20/bin/opencode`, a bun-compiled binary; `strings` works on it). On 2026-10-11 a leg
aborted: one request streamed for 60.6 min and the client interrupted it. Diagnosis (docs/open-questions.md C154):
the `@opencode/LocationActivity` layer is built as `dEd()` with no arguments, so `timeToLive ?? "60 minutes"` is
fixed; its listener refreshes only on `Session.Event.Durable` events; the sweeper calls
`interrupt(id, {reason: "inactivity"})`. The `run` command, on `session.execution.interrupted` with reason != "user",
sets `process.exitCode = 1` and emits `{type: "aborted", message: "Session interrupted: <reason>"}`. The real
events + export are in benchmark/bench/tests/fixtures/opencode_2.0.20_inactivity_interrupt.json (scrubbed, trimmed).

Ruling (operator): record exactly that shape as a scored non-converged row, `nonconv_kind: client_inactivity`,
with uncharged size evidence; any other interrupt reason still aborts; no time-based cut of our own.

The change under review is the HEAD commit (`git show HEAD`): benchmark/bench/token_turn_gate.py (`reconcile`,
`PRECEDENCE`, `INACTIVITY_ERROR`, `uncharged_trailing`), benchmark/bench/tg1_runner.py (reconciliation dict),
tests in benchmark/bench/tests/test_token_turn_gate.py and test_tg1_integration.py. You may run:
`cd benchmark && env -u STACK_WORKDIR ../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/test_token_turn_gate.py bench/tests/test_tg1_integration.py`
(no router, no model).

Lens:
1. Diagnosis: read the binary's strings around `timeToLive`, `LocationActivity`, `session.execution.interrupted`
   and the `run` event handler. Is the TTL really unconfigurable in 2.0.20? Which events refresh it? Is rc 1 and the
   exact error dict the only shape for reason "inactivity"? Could the same interrupt arrive with a different
   export shape (e.g. usage present, finish other than "error", the interrupt landing between steps or inside a
   tool call, or after our own SIGTERM)?
2. Predicate strictness: can anything other than the pinned inactivity interrupt be scored as `client_inactivity`
   (other reasons, extra errors, our own stop, an aborted trailing message that is not the live active message,
   a missing trailing message)? Conversely, is any genuine inactivity shape still a transport abort that should not be?
3. Accounting: the interrupted request carries no usage, so its tokens are uncharged. Does anything downstream
   (gate checks, `budget_hit`, `nonconv_flags`, final grade boundary in tg1_runner `final_boundary`,
   acc_strict@budget scoring, chain validation in benchmark/chains/c147/run_tg1_chain.py and
   benchmark/bench/chain_ops.py, benchmark/m62/inject_verify.py) mis-handle this row? Is `uncharged_trailing`
   sufficient evidence, and is `streamed_s` (export `time.streamed - time.created`) the right measure?
4. Precedence placement after `context_overflow` and before `budget_hit`; interaction with flags already set.
5. Provenance: the policy hash (`scaffold_policy_sha256`, from the gate/hygiene POLICY) is unchanged and the
   probe code sha changes. Is that the correct identity boundary, given rows before and after must never pool?
6. Tests: do they bite on the pre-fix code; is the real fixture used faithfully; anything missing.

Output numbered findings R1, R2, ... (severity blocker / should-fix / nit, file:line, concrete change), then a
one-line verdict: "cleared", "cleared after fixes" (list the ids), or "not cleared".
