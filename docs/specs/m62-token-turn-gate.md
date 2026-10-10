# M62 — token/turn progress gate for the v2 probe (C146) + probe hygiene (C138)

Status: REVISION 5, 2026-10-09 — revision 4 (`f73cd6a`) cold review by claude-fable-5-1 (F1–F14, verdict "approve with
changes") folded in (tagged F-ids); F12 (strict new-minimum progress) awaits operator sign-off. Implemented in `c67769e`;
build findings recorded in §9. Revision 4 history: — passive design per operator rulings (C146, P219/P220). Revision 3 (`e98aef6`) cold
review (`$STACK_WORKDIR/m62/codex_design_review3.md`, findings P28–P39) kept the architecture and constants and asked
for observation-based silence states, cache-aware budgets, one live tool-call order, no overshoot promise, a terminal
transition contract, harness artifacts out of the exercise tree, a trusted grading boundary, best-effort containment
stated as such, host-grader memory, immutable evidence and more oracles; revision 4 answers each (tagged). Revisions 1–2
(proxy) drew "redesign" twice; the two-stage cap (P220) was rejected. Rulings: passive gate, no proxy; constants in §3;
tool-bounding plugin only in the bench-owned config dir; single pass per (item, session).

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

## 2. Mechanism — passive gate on completed requests

The probe runs opencode with its event log, stderr and export written to a per-item evidence directory OUTSIDE the
exercise tree (P33). An **ingestion thread** parses the `--format json` log as it grows; a **grading worker** grades
snapshots; the **gate** consumes both. Ingestion never blocks on grading (P31).

- **Events (F4).** Complete lines only; a partial trailing line waits for its newline. After a probe kill a partial
  trailing line is dropped and recorded (`torn_tail`); after a normal exit it is malformed. Malformed instances of
  `step_start`, `step_finish`, `tool_use` or `error` → `TransportAbort`. Duplicate = identical `(type, part.id)` →
  `TransportAbort`. Other event types (`text`, `reasoning`, unknown) are ignored and counted (`event_types_seen`). The
  legacy `_events` parser is not reused.
- **Request completion.** Request j is complete at its `step_finish` (opencode settles step j's foreground tool fibers
  before publishing it; P28). Usage (F7): charged output `output_j = tokens.output + tokens.reasoning` (opencode's `output`
  is visible output minus reasoning; the fork reports no reasoning split today, so `reasoning` = 0 in all 3,603 logged
  finishes and thinking sits in `output`); `tokens.input`, `tokens.cache.read`, `tokens.cache.write`, `tokens.reasoning`
  — non-negative ints, booleans rejected; anything missing → `TransportAbort` (P1). A second
  `step_start` without an intervening `step_finish` is the retry signature → `TransportAbort`.
- **Tool calls** enter the K run in live **completion-event order** (`tool_use` events); replay and the reported live
  loop metric use the same order; the legacy export-order `loop_metrics` stays a diagnostic (P30). A request with no
  tool calls leaves the run unchanged. Identity (F8) = (tool name, canonical JSON of `state.input` with sorted keys);
  errored calls count; calls count as their events arrive, so K can fire mid-request.
- **Per-request resolved budget (P29).** `prompt_j = input_j + cache.read_j + cache.write_j`;
  `b_j = convergence.resolved_thinking_budget({"thinking_budget": 81920, "prompt_tokens": prompt_j},
  context_limit=L, max_tokens=102400)` where `L` = the worker's `configured_context_limit` (the limit the server
  clamps with), read at preflight and required to equal the carrier's `limit.context`. `output_j ≥ b_j` → flag
  `budget_hit` (conservative stand-in for an unobservable forced closure, P16). A budget hit never stops the item.
- **Snapshots (P33).** Input manifest = every regular file under the exercise tree except `.git/`, `__pycache__/`,
  `.pytest_cache/`, `*.pyc`. A symlink or other non-regular file → ungradeable. Capture: manifest A (path → sha256),
  copy, manifest of the copy, manifest B; accept only if all three are equal, retry ≤ 3 times, else ungradeable. Each
  snapshot records `boundary` = the number of completed requests when capture began. Snapshots are consistency-checked
  observations, not atomic request-boundary states.
- **Per-`step_finish` order (F2).** (1) charge usage and tool calls; (2) if manifest A differs from the last
  successfully graded manifest, enqueue a capture with `boundary = j` (an ungradeable snapshot never becomes "last
  graded"; the next `step_finish` retries); (3) run the §3 checks. One grade runs at a time; a newer change queues at
  most one further capture. Grading-worker death → `TransportAbort`. Grader timeouts: Python 300 s, Go 180 s (the
  legacy values; F13).
- **Interface (shared by live and replay).** `on_tool_call(sig)`, `on_request(j, output_j, prompt_j, b_j)`,
  `on_capture(boundary)`, `on_grade(boundary, failing, gradeable, tampered)`, `decision()`,
  `terminal(final_request, final_grade)`.

## 3. Gate policy (`TokenTurnGate`, new module; `ProgressGate` unchanged for the frozen 1.18 probe, the
`opencode-v2-web` path and `run_dsh_probe.py`)

Campaign constants, identical for every arm, frozen in the scaffold policy and hashed. The probe refuses a model whose
carrier `thinking_budget` ≠ 81,920 or `max_tokens` ≠ 102,400 under tg1.

| Constant | Value | Stop | Basis |
|---|---|---|---|
| `T` no-progress output tokens | `≥ 81,920` | `stalled` | one full-budget think; a forced closure strict-fails anyway |
| `N` no-progress requests | `≥ 40` | `stalled` | passing max 26 requests total |
| `K` identical consecutive tool calls | `≥ 8` | `looping` | passing max run 2; kindergarten-garden stops at request 15 |
| item output tokens | `≥ 327,680` | `hard_ceiling` | passing max 39,142 (incl. the final message from the export) |
| item requests | `≥ 150` | `hard_ceiling` | |

- **Counters.** Item totals add every completed request. No-progress counters = output tokens and request count of
  completed requests with index > `last_progress_boundary` (initially 0).
- **Progress** = a graded snapshot that is gradeable, untampered (§3 protected inputs) and has `failing < best`; then
  `best = failing` and `last_progress_boundary = max(last_progress_boundary, snapshot.boundary)`. Consequence (F12,
  operator sign-off pending): stricter than Phase H ("fewer failing, or the file changed without more failures") —
  equal-count rewrites earn nothing, and a regress-then-recover sequence earns credit only below the previous best.
- **Checks** run on every ingested `step_finish` (after steps 1–2 above), on every tool call (K) and after every
  grade: `looping` (K) and `hard_ceiling` fire immediately (no grade needed, P39); `stalled` (T or N) fires only when
  no capture with `boundary > last_progress_boundary` is pending (F11: pending = enqueued or grading; it waits for
  those, ≤ the grader timeout; once they complete it fires if T/N still hold, even if a newer capture has been queued
  since, so slow grading cannot defer `stalled` to the ceiling). Precedence when
  several hold at once: `looping` > `hard_ceiling` > `stalled`; all comparisons `≥`.
- **Stops are sticky** (P31): once decided, later progress, events or process exit cannot clear it. The stop kills the
  item (§4). Overshoot is NOT bounded by one request: recorded are the first threshold-crossing request, the completed
  request count at kill, decision backlog, post-threshold known output tokens, and whether a request was in flight
  (`inflight_s_at_stop`; its tokens are unknown and stated as such).
- **Terminal evaluation (P32).** On process exit the probe drains the log, awaits any running grade, exports,
  reconciles (§3a), grades the final tree as one more snapshot, then runs the same checks once with the final request included. An item that crossed K
  or a ceiling on its final request keeps the flag (`nonconv_flags`) and fails strict.

**Progress measure (P34).**
- **Universe preflight** (V1b, before any model run): for every eligible item, map `files.example[0]` →
  `files.solution[0]` (exactly one of each, else the item is refused), grade the reference in a probe-private
  directory under the run dir (removed after preflight; never under the model's TMPDIR or scratch), and freeze
  `benchmark/m62/universe.json`: per item the passing leaf ids, the protected-input manifest and the grader version.
  The reference must pass every collected test. `go/counter` (C145) is refused under tg1. The probe verifies the frozen
  file's hash and refuses items absent from it.
- **Structured graders** (new module; legacy graders untouched). Python: host pytest on the official test file only,
  `--rootdir=<snapshot> -p no:cacheprovider --junitxml=<outside snapshot>`, id = (file, classname, name). Go: Docker,
  snapshot bind-mounted at `/work`, `go test -json ./...` captured in full to a file, id = (package, full test name);
  leaves = ids with no child in the reference results. Failing count = |universe \ passing leaf ids reported|; a panic,
  build error, collection error or grader timeout counts every unreported universe test as failing.
- **Grader infrastructure failure** (Docker exit 125/126/127 or daemon/image errors, missing interpreter, unreadable
  report with no test events and no build/collection error) → `TransportAbort`, never a count.
- **Baseline** `best` = failing count of the untouched stub (graded in preflight; recorded).
- **Protected inputs** = every prepared file except `files.solution` and `.docs/`; plus **forbidden additions** that
  alter official discovery/execution (F5): Python `conftest.py`, `pytest.ini`, `pyproject.toml`, `setup.cfg`,
  `tox.ini`, `sitecustomize.py`, `usercustomize.py`, `*.pth` anywhere in the tree; Go any file in the exercise package
  defining `TestMain`, and `go.mod`/`go.work`/`vendor/` at the exercise root. Model-authored test files and nested
  modules are allowed: their ids are outside the universe and cannot raise the count (observed: models write scratch
  `*_test.go`; a passing go/markdown row created a nested `go.mod`). A snapshot with a modified/deleted protected file
  or a forbidden addition is tampered: never progress.
- **Final grade (F6).** Under tg1 `passed = (failing == 0) and not tampered`, from the structured grader on the final
  tree; `test_modified = tampered`. The legacy pass/fail graders are not called under tg1 (tg1 never pools with M59/M61).
  Residual (F14): `go test -json` trusts the test binary's output; model code could print fake PASS lines — the same
  exposure as any execution-graded benchmark.

### 3a. Terminal states and reconciliation (P32)

Reconcile BEFORE `_metric_export` normalisation (it drops ids), by message id only (export `messages[].id` ↔ event
`part.messageID`; no ordinal fallback). Every live `step_finish` must match an export assistant message with equal
usage; every export assistant message must be matched or be one of the explicit exceptions below.

| Terminal state | Detection | Unmatched export messages allowed | Outcome |
|---|---|---|---|
| normal exit | rc 0, ordered events | the final assistant message (all 381 historical passes omit its `step_finish`); its usage is charged once from the export | graded; terminal checks |
| gate stop | probe kill | messages completed during the backlog (charged); exactly one trailing message that is either interrupted (`error.type == "aborted"`, no usage) or completed but unpublished (usage + finish, no error — killed between provider finish and the CLI write; charged, included in terminal checks; F3) | `nonconv_kind` = stop reason |
| context overflow | existing `_context_overflow` signature, rc 1 | the rejected request (no usage) | `context_overflow`, scored |
| resource / silence outcomes | §4 | as for gate stop | `client_resource` / `exec_timeout`, scored; `client_exit_hang` → graded normally (§4) |
| anything else (Step.Failed, retry, malformed stream, unexpected exit, mismatch) | — | none | `TransportAbort` |

`nonconv_flags` keeps every condition seen; `nonconv_kind` (primary) precedence: `looping` > `hard_ceiling` > `stalled`
> `exec_timeout` > `client_resource` > `context_overflow` > `budget_hit`. Any non-null value fails `acc_strict@budget`.

## 4. Tool bounds, silence and hygiene (C138)

- **Tool-bounding plugin** `benchmark/opencode_plugins/toolbounds.js`, copied by sha into the run's bench-owned
  `OPENCODE_CONFIG_DIR/plugins/` only under tg1 (never into `opencode_config/`, the generated daily config or the
  operator's `~/.config/opencode`). Promise-API `ctx.tool.hook("execute.before", …)` on tool name `shell` rejects
  `background: true`, `timeout: 0` and `timeout > 600000` with model-visible text naming the bound (source: the
  promise adapter turns a rejection into failed-tool feedback; P38). Rejections are counted from the export
  (`tool_bounds_rejections`). The tg1 carrier inherits the web carrier's `execute` (Code Mode) deny; asserted.
- **Carrier** `benchmark/opencode_bench_v2_web_tg1.json`, a configgen target = the web carrier + `subagent` deny.
  The probe asserts title generation and compaction disabled and that both plugins load (`opencode_v2_destination`).
- **Silence — observations, not causes (P28).** Preflight requires a readable worker `/metrics` with integer
  `summary.in_flight` (refuse otherwise). Once no new event has arrived for 1,200 s (> the 600 s shell bound + margin),
  the probe samples every 60 s (F1). **Idle** = three consecutive samples ≥ 30 s apart with `in_flight == 0` and no
  event-log growth in bytes; any busy sample or growth resets the count. Classification:
  - worker busy: never killed for time (AGENTS: silent/BUSY); the watch daemon alerts; generation is bounded by
    `max_tokens`;
  - idle and a tracked descendant of an opencode shell call alive: stop, `exec_timeout` (scored);
  - idle and none alive: kill and run the terminal path; if the export reconciles as a normal exit (session finished,
    process hung on exit) grade normally with diagnostic `client_exit_hang`, else `TransportAbort("client silent,
    worker idle")`.
  Every case records the observations. No other time limit exists (R_max removed).
- **Server cancellation (F9).** After any kill, poll `summary.in_flight` until 0 within
  max(300 s, last `prompt_j` / 300 tok/s prefill floor), else `TransportAbort("worker health: did not cancel")` — the
  worker notices a disconnect only between tokens, so a kill during a long prefill is seen at its first token.
- **H1 Process tracking — best effort (P35).** Ownership is registered before resources go live (tracker started
  before spawn; container names registered before `docker run`). A 0.5 s tracker records descendants of opencode and of
  probe graders as (pid, create_time), following session/process-group changes while ancestry is visible. Stop =
  SIGKILL every tracked entry still matching its create_time, then sweep processes of the same uid whose cwd or argv
  lies under the scratch or item TMPDIR and kill those too, excluding the probe itself, its ancestors and its session
  (an operator shell `cd`'d into scratch is never killed; F13). Guarantee is limited to tracked or swept processes; a
  process that forks, detaches and leaves the scratch between samples can escape (stated residual risk). After the
  sweep, any surviving attributed process → abort the leg (cleanup uncertain); unattributed same-uid orphans created
  during the item (ppid 1) are listed in diagnostics, never killed. Cleanup is idempotent, runs on normal exit,
  exception, timeout and signals, and defers further SIGTERM/SIGINT until it completes. Grader containers:
  `--name mlxbench-<run>-<item>-<n> --memory 4g --memory-swap 4g`, removed by name (also when `docker run` never
  started); zero remaining verified.
- **H2 Memory watchdog — best effort (P36).** Accounting covers tracked model-spawned processes AND probe graders with
  their descendants. Per process > 8 GiB RSS → kill; tracked aggregate > 16 GiB → kill the largest, repeat until
  below. A killed model process: its command fails (`mem_kills`). A killed grader: that grade counts as all failing
  (`grader_mem_kill`). opencode itself > 16 GiB → kill, `client_resource` (scored). Container OOM → all failing
  (`grader_oom`). Monitor-thread death → abort. Thresholds are policy constants (tests lower them).
- **H3 Writes.** Rows and manifests: whole-file replacement (tmp, fsync, rename, fsync dir), results checked; loader
  refuses torn files.
- **H4 Instance identity.** Worker pid + create_time + model path + registry sha, checked before and after every item
  within a leg; missing → refuse; drift → abort (item invalid). A rows file whose recorded worker identity differs
  refuses append. `--expect-items a,b,…` (exact id set): exit nonzero on missing or duplicate ids.

## 5. Provenance and scaffold (P37)

`--scaffold opencode-v2-web-tg1`. The scaffold policy hash covers the §3 constants, plugin sha, tg1 carrier sha,
silence/memory/container settings, `universe.json` sha and the structured-grader version. Code identity hashes every
new module. Under tg1 the probe refuses `--tick-s`, `--first-write-tokens`, `--hard-ceiling-s`, `--stall-ticks`,
`--loop-repeats` and `--poll-s`, and does not read `decode_rates.json`. `opencode_v2_env_check` accepts
`toolbounds.js` by sha only under tg1. Evidence is immutable per attempt: tg1 transcripts, events, stderr and exports go
to `opencode_transcripts/<model>/<rows stem>.<run_id>/<lang>__<item>.*`; the row stores their sha256; an existing path
refuses. tg1 never pools with M59/M61 rows. The `opencode-v2-web` and `opencode-v2` paths keep their behaviour
(existing tests unchanged; a test asserts they never construct tg1 components). AGENTS.md M50 text names
`toolbounds.js` alongside `noretry.js` (operator-approved plugin).

Row additions (tg1 only): `gate` {stop_reason, first_crossing_request, requests_completed, output_tokens_completed,
no_progress_tokens, no_progress_requests, max_identical_run_live, universe_size, baseline_failing, best_failing,
failing_trajectory [(boundary, failing, tampered)], decision_backlog_max, post_threshold_tokens_known,
inflight_s_at_stop}; `request_usage` [(message_id, output, prompt, b_j)]; `nonconv_flags`; `tool_bounds_rejections`;
`mem_kills`; `grader_mem_kill`; `orphans_unattributed`; `worker_before`, `worker_after`; evidence sha256s.

## 6. Acceptance criteria (pre-registered)

- **V1 tests, failing first.** Gate: each threshold at exactly T/N/K/ceilings with `≥`; precedence; sticky stops;
  boundary-based reset; `stalled` waiting on a pending grade; K/ceilings without grading. Ingestion: fragmented
  UTF-8/JSON lines, duplicate and malformed complete lines, terminal draining, parallel tools in permuted order.
  Scheduling: slow grading while several requests complete; process exit during grading; final-request crossings of
  K and the ceiling. Usage: cache-read/cache-write prompt reconstruction, `b_j` at exactly the boundary with a clamped
  budget, missing usage, bool/negative values, id mismatch. Terminal table: every row of §3a. Progress: Go panic
  mid-suite, build error, Python collection error, grader timeout, equal-count refactor, alternating drafts,
  ungradeable/inconsistent snapshot, protected-file edit (incl. Go `cases_test.go`), each forbidden addition,
  infrastructure failure → abort. Silence: busy (no kill), idle+descendant (`exec_timeout`), idle+none (abort);
  cancellation via `summary.in_flight`. H1: long-lived detached shell, rapid fork/detach/chdir (detected or listed as
  unattributed — never silently ignored), cleanup interrupted by a second signal, container never started. H2: host
  grader allocation, several small children over the aggregate, monitor death, container OOM (lowered thresholds).
  H3 interrupted writes; H4 drift and `--expect-items`; immutable evidence refusal. Real pinned opencode
  (`OPENCODE_PROBE_BIN`, mock model server): the plugin rejects background / timeout 0 / timeout over bound, the model
  sees the bound text, the session continues and the rejection count is exact; `subagent` denied; Code Mode denied;
  title/compaction off; plugin absent from the generated daily config and from non-tg1 runs.
  Revision 5 additions: an edit on the T-crossing request is graded before `stalled` fires (F2); a completed but
  unpublished trailing message after a kill is charged (F3); torn tail after kill vs after normal exit, ignored
  `reasoning`/unknown event types, duplicate `(type, part.id)` (F4); model-authored `*_test.go` and a nested `go.mod`
  do not tamper, a root `go.mod` or a package `TestMain` does (F5); `passed` from the structured final grade, with a
  failing helper package outside the exercise package not failing the item (F6); usage with `reasoning > 0` (F7);
  slow grading with edits every request still stalls (F11); silence: transient idle samples do not classify, three do,
  `client_exit_hang` grades normally (F1); cancellation bound (F9). Existing suites green.
- **V1b universe preflight** (no model; Docker for Go): all 43 eligible Python/Go items produce a reference universe
  and stub baseline; `benchmark/m62/universe.json` frozen and hashed before any live run.
- **V2 offline replay** against the frozen `benchmark/m62/replay_manifest.json` (re-frozen in revision 5 and after the §9 correction, sha256 `c5312f4e…`, with event-log
  AND export sha256 per entry; 454 rows, 400 identity-matched, 381 historical passes, 374 valid after C145; the seven
  `go/counter` passes are parser fixtures only): the implemented ingestion and gate, charging every request as
  no-progress and the final request from the export, stop 0 of the 374. Fixtures (exact, F10): go/kindergarten-garden
  (M61 s2) → `(looping, request 15)` at its 8th identical call; the M59 go/alphametics row (483 step_starts, 482
  completed requests) → `(looping, request 22)` (pre-registered as `(stalled, completed request 40)`; corrected in §9); the M61 go/book-store 37.5K-token failing stretch → no
  stop. Retrospective screen only; it cannot validate uncensored long attempts.
- **V3 live smoke** (box, lean router, `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`): five seeded-random Python
  items and two Go items complete with tg1 provenance; usage reconciles; zero surviving attributed processes and
  containers; injected known positives with lowered thresholds (an over-threshold allocation killed; a no-progress
  stop; a K stop).
- **V5a** cold review (Codex) of the implementation against V1, V1b and V2, before V3 runs on the box.
- **V4 = P214** (descriptive; M61 stays the record): `Qwen3.8-27B-mlx-uniform-4bit` go/alphametics seeds 1001 and
  2002, `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` python/book-store seed 2002, each on a fresh loaded instance.
  Report per item: max single-request output, whether any request crossed 41K, first write, strict outcome, budget
  hits, wall. Three runs size further measurement; they cannot certify the >41K tail.
- **V5b** cold review after V4, before any chain uses tg1.

## 7. Cost (conditional, not promises)

No wall-time bound is claimed (passive overshoot is unbounded in requests; P31). Arithmetic for orientation only: at
≈ 19.5 tok/s, T plus two maximal requests ≈ 4.1 h of generation; the item ceiling plus two ≈ 7.6 h; tools, prefill
and grading excluded. V4 is expected ≈ 3–5 h.
Chain cost is estimated from V3/V4 means plus a heavy-tail allowance before any chain is queued.

## 8. Out of scope / consequences

- Not a gate on thinking content; no mid-stream token visibility. A later option (Astra P6): stop a request once live
  usage reaches its resolved budget (strict fail already certain) — needs new instrumentation; revisit after V4.
- Chain runners (workdir scripts) are written when a chain is queued; they archive an incomplete leg and rerun it from
  item one on a fresh instance, with leg timeouts from pilot means.
- When C144's first candidate arrives: re-record both picks under tg1 or run the candidate on the frozen path —
  operator decision then.
- 54 of 454 v2 rows reference another session's event log (re-runs overwrote transcript paths): recorded in C140.
- Workflow: this spec → Codex implementer (failing tests first; no docs/handoff edits, no commits) → lead
  verification → V1, V1b, V2 → V5a → operator: V3, V4 on the box → V5b.

## 9. Build findings (2026-10-10, implementation `c67769e`)

- **Plugin load proof.** `GET /api/config` returns before plugins finish activating, so only `noretry.js` was proven.
  tg1 proves both plugins from `GET /api/integration --standalone`, whose handler awaits `Plugin.awaitActivation`
  (pinned source `server/src/handlers/integration.ts:33`); item runs are unchanged.
- **Grade wait bound.** Grader timeouts are per grade (Python 300 s, Go 180 s); a terminal drain may hold the active
  grade plus one queued capture, so the join bound is 2 × 300 + 60 = 660 s (hashed in the policy).
- **Go build failures.** go1.21 in the grading image prints `FAIL\t<pkg> [build failed]` as plain text on stdout under
  `-json`; the parser accepts exactly that line (and `[setup failed]`) as a build error.
- **Official test.** `files.test[0]` is the official test (python/paasio also lists the helper `test_utils.py`, which
  stays protected like every prepared file).
- **Untouched solution still fails.** go/ledger and go/markdown are refactoring exercises whose stubs pass every test
  (baseline 0): under tg1 `passed` also requires the solution file to have changed (the M59/M61 rule; F6 removed only
  the second grader). For these two items progress can never register, so only T/N/K/ceilings bound them (historical
  passes stay far below T and N). Coarse universes: go/octal 1 leaf, go/hexadecimal 2.
- **V1b PASS:** `benchmark/m62/universe.json` sha256 `4e3d88b6…`, 43 items, `m62-structured-v2`.
- **V2 PASS** on manifest sha256 `c5312f4e…` (all 8 criteria). Pre-registration correction, stated openly: revision 5
  expected the M59 go/alphametics fixture to stop `(stalled, completed request 40)`, derived from N alone (F10). The
  replay stopped it as `(looping, request 22)`; an independent count confirms an identical-`edit` loop whose 8th call
  is in request 22, and K precedes N. The fixture is now `looping@request22` — a second K known positive. The 54
  misattributed rows are sha-verified and never ingested.
- **Live (2026-10-10):** V5a findings fixed (`1c1626d`, `90cf34f`); V3 7/7 and V4 3/3 (campaign-results 2026-10-10); V3 ran
  without live injected positives (no lowered-threshold mode exists) — V5b "cleared after fixes", owed items in C147.

