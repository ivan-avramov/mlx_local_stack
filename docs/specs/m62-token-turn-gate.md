# M62 — token/turn progress gate for the v2 probe (C146) + probe hygiene (C138)

Status: REVISION 3, 2026-10-09 — passive design per operator rulings (C146, P219/P220). Revision 2 (proxy; last present
at `ac1903c`) drew "redesign" twice from cold review (`$STACK_WORKDIR/m62/codex_design_review{,2}.md`); the two-stage
short-cap variant (P220) was rejected after cold review (`$STACK_WORKDIR/m62/codex_twostage.md`). Rulings: passive gate,
no proxy; constants in §3; tool-bounding plugin installed only in the bench-owned config dir; single pass per
(item, session). R-ids below map to review findings P1–P27.

## 1. Problem

The v2 probe stops items with the Phase H progress gate (`bench/progress_gate.py`): every `tick_s` it snapshots and
grades the workdir; progress = failing count fell, or the solution changed without failures rising; 2 flat ticks →
`stalled`; 3 identical transcript-tail hashes → `looping`; 3600 s → `hard_ceiling`. C136 sets `tick_s` from a token
allowance and a per-model decode-rate table. Measured defects:

1. **Time, not tokens.** "48K" became 1984 s / 1890 s; decode slows within a stream (25 → 18.7 tok/s by 40K). M61
   thinking stalls closed at ≈ 40.5K / 41K / 43.5K tokens, unequally across models, below the 81,920 thinking budget.
2. **Loop detector inert on v2:** the hashed log tail carries timestamps/ids; 0 of 454 v2 rows `looping`; a
   358-repeat loop (go/kindergarten-garden, M61 s2; 8th identical call at request 15) ran 31 min to `stalled`.
3. **Progress is gameable:** grades are binary, an ungradeable tick or any changed hash counts as progress, and the
   snapshot path skips the tamper check.
4. **No per-request convergence signal:** a forced thinking closure that then passes would score strict.
5. **C138:** no memory containment (117 GB incident); opencode's detached shells are not reaped; non-atomic row
   writes; one-instance-per-leg not enforced.

## 2. Mechanism — passive request-boundary gate

The probe tails opencode's `--format json` event log. Decision point `D_j`: the `step_start` of request j+1 (request j
and all of its tool calls are complete; opencode sends the next request only after tool results). At `D_j` the probe
reads request j's `step_finish` usage and tool calls, grades a snapshot if the tree changed, and decides. On a stop it
kills everything in flight (§4 H1); the in-flight request j+1 is abandoned. Every stop is a strict fail, so the
abandoned request changes no score; its wall time is recorded (`inflight_s_at_stop`), its tokens are unknown (stated).
At process exit no decision is made; the final request's usage comes from the export.

- **Usage (R1).** `step_finish.part.tokens.output` (thinking included; verified on M59/M61 logs against the export).
  A `step_start` not preceded by request j's `step_finish` is the existing retry signature → `TransportAbort`. Missing
  or non-integer usage → `TransportAbort` (never zero). At exit, per-request usage (live + final from export) must equal
  the export's assistant messages exactly, matched by message id where both carry it, else by ordinal; any mismatch,
  extra or missing message → `TransportAbort`. A stopped item reconciles only completed requests.
- **Per-request resolved budget (R7, P16).** For request j: `ctx_j` = running sum of incremental input tokens through j;
  `b_j = convergence.resolved_thinking_budget({"thinking_budget": 81920, "prompt_tokens": ctx_j},
  context_limit=<worker effective_context_limit from /health>, max_tokens=102400)`. A request with
  `completion_j ≥ b_j` is a **budget hit** (the server cannot report a forced closure; the threshold rule is the
  conservative stand-in). Any budget hit → `nonconv_flags` gets `budget_hit`; if the item otherwise completed,
  `nonconv_kind = "budget_hit"` → strict fail even if tests pass. A budget hit does not stop the item.
- **Snapshot consistency.** Copy the tree, hash every file before and after the copy; on any difference retry up to 3
  times, else the snapshot is ungradeable (never progress). `.git/` is excluded from copy-hashing.
- **Kill latency.** Decision lag (from `D_j` to kill) and grading time are recorded per decision.

## 3. Gate policy (`TokenTurnGate`, new module; `ProgressGate` unchanged for the frozen 1.18 probe, the
`opencode-v2-web` path and `run_dsh_probe.py`)

Campaign constants, identical for every arm, frozen in the scaffold policy and hashed. The probe refuses a model whose
carrier `thinking_budget` ≠ 81,920 or `max_tokens` ≠ 102,400 under tg1.

| Constant | Value | Stop | Basis |
|---|---|---|---|
| `T` no-progress output tokens | `≥ 81,920` | `stalled` | one full-budget think; a forced closure strict-fails anyway |
| `N` no-progress requests | `≥ 40` | `stalled` | passing max 26 requests total |
| `K` identical consecutive tool calls | `≥ 8` | `looping` | passing max run 2; kindergarten-garden stops at request 15 |
| item output tokens | `≥ 327,680` | `hard_ceiling` | passing max 39,142 |
| item requests | `≥ 150` | `hard_ceiling` | |

Evaluation at each `D_j`, in order: (1) add `completion_j` to the item total; (2) extend the tool-call run with
request j's calls in order (signature = tool name + canonical JSON input, as `opencode_common._tool_calls`); (3) if the
tree hash changed, grade; progress iff the snapshot is gradeable, untampered and `failing < best` (then `best = failing`
and both no-progress counters reset to 0 **after** request j); otherwise add `completion_j` and 1 to the no-progress
counters; (4) check `looping` > `hard_ceiling` > `stalled`, all with `≥`. Realized allowances are soft: overshoot is
at most the in-flight request (≤ 102,400 output tokens), recorded.

**Progress measure (R8, P21).**
- **Test universe** per item, computed before spawn in a run-temp dir the model never sees: copy the exercise with the
  reference solution (`.meta/config.json` `files.example`) in place of the solution, grade with structured output, and
  take the set of passing leaf test ids. Python: pytest `--junitxml`, id = classname + name. Go: `go test -json ./...`,
  leaf = a test with no reported subtests. The reference must pass every collected test, else the item is refused
  before spawn (no row). `go/counter` (C145) is refused under tg1.
- **Failing count** of a snapshot = |universe \ passing leaf ids in that snapshot|. A panic, build error, collection
  error or grader timeout therefore counts every unreported test as failing. Grader infrastructure failure (Docker
  daemon/image errors, missing interpreter) → `TransportAbort`, never a count.
- **Baseline** `best` = failing count of the untouched stub, graded before spawn.
- **Protected set** = every prepared file except the solution files (`files.solution`), `.docs/` and `.git/`; hashed
  before spawn. A snapshot that modifies or deletes any protected file is tampered: never progress, and the row's
  `test_modified` uses the same set at final grading (the final binary grade itself is unchanged: `_grade_result` with
  the existing graders, so `passed` keeps the M59/M61 definition).
- Grade only when the tree hash (all files except `.git/`) is new.

## 4. Tool bounds and hygiene (C138; R9–R12, P15, P17, P20, P22)

- **Tool-bounding plugin** `benchmark/opencode_plugins/toolbounds.js`, copied by sha into the run's bench-owned
  `OPENCODE_CONFIG_DIR/plugins/` only under tg1 (never into `opencode_config/`, the generated daily config or the
  operator's `~/.config/opencode`). `tool` hook `execute.before` on the shell tool rejects `background: true`,
  `timeout: 0` and `timeout > 600000` with a message naming the bound (0 of 1,486 v2 shell calls used any of these).
  If the pinned promise-plugin API cannot reject, the implementer stops and reports; no silent input rewriting.
  The probe counts rejections from the export (`tool_bounds_rejections`).
- **Carrier** `benchmark/opencode_bench_v2_web_tg1.json`, a configgen target = the web carrier + `subagent` deny. The
  probe asserts title generation and compaction stay disabled and that `opencode_v2_destination` reports both
  plugins loaded.
- **Silence (transport backstops, never score gates).** In flight (step_start j seen, no step_finish j) longer than
  `R_max = 1.25 × (102,400 / 10 + 262,144 / 300) s ≈ 3.9 h` → `TransportAbort`. Idle (no request in flight, opencode
  alive) longer than 900 s: a tracked model-spawned descendant alive → kill, `nonconv_kind = "exec_timeout"` (scored
  miss); none alive → `TransportAbort`. Process tree and timings go to the diagnostics either way.
- **H1 Process tracking.** A 1 s tracker records every descendant of opencode and of the probe's graders as
  (pid, create_time), including detached shells (re-scan by session/process-group and by cwd under the scratch). Stop
  = SIGKILL every tracked entry still matching its create_time; verify zero survivors twice before deleting scratch,
  else abort. Descendants alive after the shell call that spawned them completed are counted (`orphan_procs`).
  Go grader containers get `--name mlxbench-<run>-<item>-<n>` and `--memory 4g`; removed by name; zero remaining
  verified.
- **Server cancellation.** After a stop, poll the worker `/metrics` `in_flight` until 0 (≤ 120 s), else
  `TransportAbort("server did not cancel")`.
- **H2 Memory watchdog (best effort, not a cap).** Kill any tracked model-spawned process > 8 GB RSS, and the largest
  when the tracked aggregate > 16 GB (`mem_kills`; the model sees its command fail). opencode itself > 16 GB →
  kill, `nonconv_kind = "client_resource"` (scored miss). Container OOM → that grade counts as all failing
  (`grader_oom`). Monitor-thread death → abort. Thresholds are policy constants (tests lower them).
- **H3 Writes.** Rows and manifests: whole-file replacement (tmp, fsync, rename, fsync dir), results checked; loader
  refuses torn files.
- **H4 Instance identity.** Worker pid + create_time + model path + registry sha, checked before and after every item;
  missing → refuse; drift → abort (item invalid). A rows file whose recorded worker identity differs refuses append.
  `--expect-items a,b,…` (exact id set): exit nonzero on missing or duplicate ids at exit.

## 5. Provenance and scaffold (R14)

`--scaffold opencode-v2-web-tg1`. The scaffold policy hash covers the §3 constants, the plugin sha, the tg1 carrier
sha, silence limits, memory limits, grader container settings and the progress-measure version. Under tg1 the probe
refuses `--tick-s`, `--first-write-tokens`, `--hard-ceiling-s`, `--stall-ticks`, `--loop-repeats` and `--poll-s`, and
does not read `decode_rates.json`. tg1 never pools with M59/M61 rows. The `opencode-v2-web` and `opencode-v2` code paths
keep their behaviour (existing tests unchanged; a test asserts they never construct tg1 components). AGENTS.md M50 text
names `toolbounds.js` alongside `noretry.js` (operator-approved plugin).

Row additions (tg1 only): `gate` {stop_reason, decisions, requests_completed, output_tokens_completed,
no_progress_tokens, no_progress_requests, max_identical_run, universe_size, baseline_failing, best_failing,
failing_trajectory, inflight_at_stop, inflight_s_at_stop, decision_lag_s_max}; `request_usage` (per request: output,
ctx, resolved budget); `nonconv_flags`; `tool_bounds_rejections`; `mem_kills`; `orphan_procs`; `worker_before`,
`worker_after`. `nonconv_kind` ∈ {null, stalled, looping, hard_ceiling, budget_hit, exec_timeout, client_resource,
context_overflow}; any non-null value fails `acc_strict@budget`.

## 6. Acceptance criteria (pre-registered)

- **V1 tests, failing first.** Gate: each threshold at exactly T/N/K/ceilings with `≥`, precedence, reset-after-j
  semantics. Progress: universe from reference, Go panic mid-suite, build error, Python collection error, grader
  timeout, refactor at equal count, alternating drafts, ungradeable snapshot, protected-file edit (incl. a Go
  `cases_test.go`), infrastructure failure → abort. Usage: missing usage → abort, live/export mismatch → abort, final
  request from export, budget hit at exactly `b_j` with a clamped `b_j`. Silence three ways. H1 detached-shell reaping,
  H2 lowered-threshold kills, H3 interrupted-write faults, H4 drift and `--expect-items`. Real pinned opencode
  (`OPENCODE_PROBE_BIN`, mock model server): plugin rejects background/timeout-0/timeout-over-bound shell calls and the
  model receives the rejection; `subagent` denied; title/compaction off; plugin absent from the generated daily config
  and from non-tg1 runs. Existing suites green.
- **V2 offline replay**, frozen hashed manifest (`benchmark/m62/replay_manifest.json`) of the 381 identity-matched
  passing v2 rows (the 54 misattributed rows listed and excluded): the implemented event parser and gate, with every
  request charged as no-progress, stop 0 passing rows; kindergarten-garden (M61 s2) → `looping` at request 15; the
  M59 482-request go/alphametics row stops by request 150; the M61 37.5K-token go/book-store failing stretch is not
  stopped (documented: indistinguishable from passing no-write stretches).
- **V3 live smoke** (box, lean router, `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`): five seeded-random Python
  items and two Go items complete with tg1 provenance; usage reconciles; zero surviving processes/containers;
  injected known positives with lowered thresholds (a > threshold allocation killed; a no-progress stop; a K stop).
- **V5a** cold review (Codex) of the implementation against V1–V2, before V3 runs on the box.
- **V4 = P214** (descriptive, M61 stays the record): `Qwen3.8-27B-mlx-uniform-4bit` go/alphametics seeds 1001 and
  2002, `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` python/book-store seed 2002, each on a fresh loaded instance.
  Report per item: max single-request output, whether any request crossed 41K, first write, strict outcome, budget
  hits, wall. Three runs size further measurement; they cannot certify the >41K tail.
- **V5b** cold review after V4, before any chain uses tg1.

## 7. Cost (conditional, not promises)

At ≈ 19.5 tok/s late-stream decode a no-progress stop costs < (T + 102,400) / 19.5 ≈ 2.6 h of generation plus tools
and grading; a churning item can reach ≈ 6 h before the item ceiling. V4 is expected ≈ 3–5 h with no worst-case claim.
Chain cost is estimated from V3/V4 means plus a heavy-tail allowance before any chain is queued.

## 8. Out of scope / consequences

- Not a gate on thinking content; no mid-stream token visibility. A later option (Astra P6): stop a request once live
  usage reaches its resolved budget (strict fail already certain) — needs new instrumentation; revisit after V4.
- Chain runners (workdir scripts) are written when a chain is queued; they archive an incomplete leg and rerun it from
  item one on a fresh instance, with leg timeouts from pilot means.
- When C144's first candidate arrives: re-record both picks under tg1 or run the candidate on the frozen path —
  operator decision then.
- 54 of 454 v2 rows reference another session's event log (re-runs overwrote transcript paths): recorded in C140.
- Workflow: this spec → cold review → Codex implementer (failing tests first; no docs/handoff edits, no commits) →
  lead verification → V1, V2 → V5a → operator: V3, V4 on the box → V5b.
