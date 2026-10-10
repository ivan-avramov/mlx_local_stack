# M62 — token/turn progress gate for the v2 probe (C146) + probe hygiene (C138)

Status: REVISION 4, 2026-10-09 — passive design per operator rulings (C146, P219/P220). Revision 3 (`e98aef6`) cold
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

- **Events.** Complete lines only; a partial trailing line waits for its newline; a malformed complete line, a
  duplicate event or an unknown event type the gate depends on → `TransportAbort` (P38). The legacy `_events` parser is
  not reused.
- **Request completion.** Request j is complete at its `step_finish` (opencode settles step j's foreground tool fibers
  before publishing it; P28). Usage: `tokens.output` (thinking included), `tokens.input`, `tokens.cache.read`,
  `tokens.cache.write` — non-negative ints, booleans rejected; anything missing → `TransportAbort` (P1). A second
  `step_start` without an intervening `step_finish` is the retry signature → `TransportAbort`.
- **Tool calls** enter the K run in live **completion-event order** (`tool_use` events); replay and the reported live
  loop metric use the same order; the legacy export-order `loop_metrics` stays a diagnostic (P30). A request with no
  tool calls leaves the run unchanged.
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
- **Grading worker.** After each `step_finish`, if manifest A differs from the last graded snapshot, a snapshot is
  captured and graded (one grade at a time; a newer change queues one further capture).

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

- **Counters.** Item totals add every completed request. No-progress counters = output tokens and request count of
  completed requests with index > `last_progress_boundary` (initially 0).
- **Progress** = a graded snapshot that is gradeable, untampered (§3 protected inputs) and has `failing < best`; then
  `best = failing` and `last_progress_boundary = max(last_progress_boundary, snapshot.boundary)`.
- **Checks** run on every ingested `step_finish` and after every grade: `looping` (K) and `hard_ceiling` fire
  immediately (no grade needed, P39); `stalled` (T or N) fires only when no grade of a snapshot with
  `boundary > last_progress_boundary` is pending (it waits for that grade, ≤ the grader timeout). Precedence when
  several hold at once: `looping` > `hard_ceiling` > `stalled`; all comparisons `≥`.
- **Stops are sticky** (P31): once decided, later progress, events or process exit cannot clear it. The stop kills the
  item (§4). Overshoot is NOT bounded by one request: recorded are the first threshold-crossing request, the completed
  request count at kill, decision backlog, post-threshold known output tokens, and whether a request was in flight
  (`inflight_s_at_stop`; its tokens are unknown and stated as such).
- **Terminal evaluation (P32).** On process exit the probe drains the log, exports, reconciles (§3a), grades the final
  tree as one more snapshot, then runs the same checks once with the final request included. An item that crossed K
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
  alter official discovery/execution: Python `conftest.py`, `pytest.ini`, `pyproject.toml`, `setup.cfg`, `tox.ini`,
  `sitecustomize.py`, `usercustomize.py`, `*.pth`; Go any new `*_test.go`, `go.mod`, `go.work`, `vendor/`, or any `.go`
  file defining `TestMain`. New non-test helper sources are allowed. A snapshot with a modified/deleted protected file
  or a forbidden addition is tampered: never progress. At final grading the same rule sets `test_modified = true` and
  `passed = false` (tg1 extends the M59/M61 single-file tamper rule; the pass/fail grader is otherwise unchanged).

### 3a. Terminal states and reconciliation (P32)

Reconcile BEFORE `_metric_export` normalisation (it drops ids), by message id only (export `messages[].id` ↔ event
`part.messageID`; no ordinal fallback). Every live `step_finish` must match an export assistant message with equal
usage; every export assistant message must be matched or be one of the explicit exceptions below.

| Terminal state | Detection | Unmatched export messages allowed | Outcome |
|---|---|---|---|
| normal exit | rc 0, ordered events | the final assistant message (all 381 historical passes omit its `step_finish`); its usage is charged once from the export | graded; terminal checks |
| gate stop | probe kill | messages completed during the backlog (charged), the interrupted last message (`error.type == "aborted"`, no usage required) | `nonconv_kind` = stop reason |
| context overflow | existing `_context_overflow` signature, rc 1 | the rejected request (no usage) | `context_overflow`, scored |
| resource / silence outcomes | §4 | the interrupted last message | `client_resource` / `exec_timeout`, scored |
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
  `summary.in_flight` (refuse otherwise). With no new event for 1,200 s (> the 600 s shell bound + margin), the probe
  samples `summary.in_flight` and the tracked tree:
  - worker busy (`in_flight > 0`): never killed for time (AGENTS: silent/BUSY); the watch daemon alerts; generation is
    bounded by `max_tokens`;
  - worker idle and a tracked descendant of an opencode shell call alive: stop, `exec_timeout` (scored);
  - worker idle and none alive: `TransportAbort("client silent, worker idle")`.
  Every case records the observations. No other time limit exists (R_max removed).
- **Server cancellation.** After any kill, poll `summary.in_flight` until 0 (≤ 120 s), else
  `TransportAbort("server did not cancel")`.
- **H1 Process tracking — best effort (P35).** Ownership is registered before resources go live (tracker started
  before spawn; container names registered before `docker run`). A 0.5 s tracker records descendants of opencode and of
  probe graders as (pid, create_time), following session/process-group changes while ancestry is visible. Stop =
  SIGKILL every tracked entry still matching its create_time, then sweep processes of the same uid whose cwd or argv
  lies under the scratch or item TMPDIR and kill those too. Guarantee is limited to tracked or swept processes; a
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
  title/compaction off; plugin absent from the generated daily config and from non-tg1 runs. Existing suites green.
- **V1b universe preflight** (no model; Docker for Go): all 43 eligible Python/Go items produce a reference universe
  and stub baseline; `benchmark/m62/universe.json` frozen and hashed before any live run.
- **V2 offline replay** against the frozen `benchmark/m62/replay_manifest.json` (sha256 `55b11014…`; 454 rows, 400
  identity-matched, 381 historical passes, 374 valid after C145; the seven `go/counter` passes are parser fixtures
  only): the implemented ingestion and gate, charging every request as no-progress, stop 0 of the 374; fixtures:
  go/kindergarten-garden (M61 s2) → `looping` at request 15; the M59 482-request go/alphametics → a stop by request
  150; the M61 37.5K-token go/book-store failing stretch → no stop (indistinguishable from passing no-write stretches).
  Retrospective screen only; it cannot validate uncensored long attempts.
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
