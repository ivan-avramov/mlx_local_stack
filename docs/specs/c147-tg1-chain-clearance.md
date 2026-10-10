# C147 — tg1 chain clearance: injected positives, chain runner, `/tmp` escape diagnostic, grader-report retention

Status: REVISION 3, 2026-10-10. Design P236–P241 approved by the operator 2026-10-10 ("sounds good"), with cold
review on Codex `gpt-6.1-sol` before and after the build. Revision 1 drew "redesign" (P1–P14,
`$STACK_WORKDIR/c147/codex_design_review1.md`); revision 2 answered each and drew "redesign" again (P1–P4, P9, P10,
P12, P13 partially answered; new P15–P22; `codex_design_review2.md`). Revision 3 answers the open ids, tagged
`[Pn]`. Lead decision: build from revision 3; the post-build cold review (V5) re-checks every id against code. Long-haul box runs (the ≈30 min injected run and the
≈20 h P223 chains) are the operator's; this build ships code, tests and the handoff only. Parent spec:
`docs/specs/m62-token-turn-gate.md` (rev 5 + §9); owed list: `docs/open-questions.md` C147.

## 1. Scope

Four deliverables, all under `benchmark/` except the named exception `scripts/session_pinning_gate.py` (tg1 mode,
§3) [P22], none changing the campaign tg1 policy or any pick:

1. `--tg1-inject {stall,loop,alloc}`: a labelled, never-pooled probe mode that lowers exactly one threshold so the
   live stop → owned-descendant kill → worker cancellation → export reconciliation path can be proven on the box.
2. A tg1 chain runner in the repo replacing the reused M59 runner for k=2 chains.
3. A `/tmp` escape diagnostic with exact-path cleanup.
4. Hashed retention of every structured-grader report.

Out of scope: any change to §3 constants of M62 in campaign mode, the frozen `benchmark/chains/m54–m62/` drivers,
the `opencode-v2-web` / `opencode-v2` paths, picks, rankings, the registry.

## 2. Injected positives (`--tg1-inject`)

**CLI.** `run_opencode_probe_v2.py --scaffold opencode-v2-web-tg1 --tg1-inject <kind>`; any other scaffold with
`--tg1-inject` → `REFUSED`. Exactly one item per invocation (`--limit 1` implied; more → `REFUSED`);
`--expect-items` required. `--out` must resolve under `$STACK_WORKDIR/m62/inject/` (anything else, including the
default `benchmark/results/...`, → `REFUSED`).

**Policy.** `tg1_runner.INJECT_POLICY[kind]` is a frozen code constant (no CLI override); each kind lowers ONLY its
own threshold, every other constant stays at the campaign value, so the other stops cannot fire first:

| kind | lowered constant | expected observation |
|---|---|---|
| `stall` | gate `no_progress_requests` 40 → **4** | `stalled` at the 4th completed request after the last progress boundary |
| `loop` | gate `identical_calls` 8 → **3** | `looping` on the 3rd identical consecutive tool call |
| `alloc` | hygiene `per_process` 8 GiB → **512 MiB** (build finding B2: 256 MiB killed opencode's own ≈380 MiB server child) | one `mem_kills` entry with role `model`; the shell call is reported killed; the session continues |

`T` (81,920), the ceilings, `thinking_budget`/`max_tokens` carrier checks, `aggregate`, `client_limit`, silence and
cancellation constants are unchanged in every kind.

**Prompt addendum (hashed).** Each kind appends one fixed sentence to the item prompt so the positive is driven
rather than hoped for (the rows are instrument proofs, never model evidence). Compliance is NOT deterministic
[P9]: the verifier classifies every row (below) and a non-PASS kind is re-run on the next seed base of the fixed
schedule 1001 → 2002 → 3003 (three attempts per kind; a third miss is a build finding, not a shrug).

- `stall`: "Before anything else, run the shell command `ls` four separate times, one tool call per message, and
  only then start the task."
- `loop`: "Before anything else, run the shell command `sleep 600 >/dev/null 2>&1 & sleep 1` three times in a row
  as three separate tool calls with exactly the same arguments (same command text, same working directory, no
  other fields), and only then start the task." The detached `sleep 600` is a tracked model descendant (its parent
  shell lives one second, two tracker ticks, so ancestry is recorded before the detach) and is still alive when the
  third identical call stops the item [P10].
- `alloc`: "Before anything else, run exactly this shell command once:
  `python3 -c "import time; b = bytearray(1024 * 1024 * 1024); time.sleep(90)"` and only then start the task."

The addendum text is part of the inject policy and its sha256 is recorded. The shell tool's input schema on 2.0.20
is `{command, workdir, timeout?, background?}` and the gate hashes the whole input object [P9]; the loop addendum
therefore asks for identical arguments, and the verifier derives the signatures from the raw events, not from the
label.

**Registered trigger predicates (from the row and raw events) [P9] [P16].**

| kind | PASS predicate | other outcomes |
|---|---|---|
| `stall` | `gate.stop_reason == "stalled"`, `gate.no_progress_requests ≥ 4` AND `gate.no_progress_tokens < 81,920` at the stop (the lowered threshold was the crossing); re-derived from the events: ≥ 4 `step_finish` after the last progress boundary | a T crossing (`no_progress_tokens ≥ 81,920`) → `competing_trigger:T`; another stop → `competing_trigger:<reason>`; no stop → `not_observed` |
| `loop` | `gate.stop_reason == "looping"`, `max_identical_run_live ≥ 3`; three consecutive `tool_use` events with byte-identical canonical `(tool, input)` in the events file | as above |
| `alloc` | one `mem_kills` entry with `role == "model"`, `rss > per_process` (512 MiB), `argv` containing `bytearray(`, `tool_call_id` equal to the `part.id` of the shell part whose `command` contains `bytearray(`, `carrying_request` = that part's 1-based request index and `completed_boundary_at_kill = carrying_request − 1`; that part's recorded state matches the frozen killed-command fixture (`status == "error"`, or `status == "completed"` with metadata `exit != 0` or a signal — the fixture is produced by the V2 real-client allocation test and frozen by sha); and a completed request with index > `carrying_request` exists (continuation) | kill absent → `not_observed`; kill of an unrelated argv → `FAIL` |

**Causal evidence of the live path [P10].** Rows gain `termination.killed` = `[{pid, create_time, role, argv}]`
(every tracked process `kill_role` signalled, argv scrubbed), `termination.killed_verified` (every killed pid gone
at the post-kill check, by pid+create_time), `termination.cancel_wait_s` (elapsed until worker `summary.in_flight
== 0`; `wait_cancel` returns it), `termination.in_flight_at_kill` and `termination.worker_summary_before/after`
(the full `/metrics` `summary` immediately before the kill and when `in_flight` reached 0, so the cancelled request
is the one the worker was serving for this session). `mem_kills` entries gain `role`, `rss`, `argv`,
`tool_call_id`, `carrying_request`, `completed_boundary_at_kill`. Requirements: `stall` and `loop` rows must have
`termination.killed` including the client pid and `killed_verified == true`, `termination.reason` equal to the
stop, `reconciliation.trailing ∈ {interrupted, unpublished}` and a numeric `cancel_wait_s` within the bound. The
`loop` row must additionally show ≥ 1 killed `model`-role process whose argv is `sleep 600` (the tracked
descendant alive at the stop) — this is the combined stop → owned-descendant kill → cancellation → reconciliation
proof C147 owes. Cancellation itself is proven only when `in_flight_at_kill ≥ 1` and `worker_summary_after`
differs from `_before` in the served counters; a row where the worker had finished naturally
(`in_flight_at_kill == 0`) is `not_observed:cancellation` (registered negative case) and that kind is re-run.
Suite requirement: the retained `loop` row shows the cancellation; `stall` may show it.

**Labelling.** Row `scaffold` and manifest `runtime.scaffold` = `opencode-v2-web-tg1-inject:<kind>`;
`runtime.inject` = `{kind, policy (full effective gate + hygiene dicts), prompt_addendum_sha256}`;
`scaffold_policy_sha256` is computed over the effective policy, so it differs from the campaign hash. Resume refuses
mixing (existing `runtime` equality check); the campaign path never reads `INJECT_POLICY`. A test pins the campaign
`scaffold_policy_sha256` to the value recorded in every V3/V4 manifest under `benchmark/results/`
(`ba86ba16e40e5e7b3535d64de2de9e95b323158049358b1f41b2ed26a83bb15c`) so this build cannot move it.

**Row additions (all tg1 rows, campaign too; the V3/V4 rows predate them and are never pooled with chains):**
- `reconciliation`: `{unmatched_export_messages, trailing: "none"|"interrupted"|"unpublished"|"final"}` returned by
  `token_turn_gate.reconcile` (today it returns nothing; the function's abort behaviour is unchanged).
- `termination.cancel_wait_s`: seconds until worker `summary.in_flight` reached 0 after the kill (from `wait_cancel`,
  which returns the elapsed time; `None` when no kill happened).

**Verifier contract (single, authoritative) [P15].** `benchmark/m62/inject_verify.py --run <inject dir>`
reads every attempt file `<kind>.attempt<n>.jsonl` (+ manifest) and prints one line per row:
`PASS | FAIL:<why> | not_observed[:what] | competing_trigger:<reason>`. Per-row checks: label and
`runtime.inject.kind`; the predicate table; the causal evidence; `worker_before == worker_after`; every
`evidence_sha256` and every `grade_reports` artifact sha against the file; `orphans_unattributed` printed, never
failing. Suite-level: the LAST attempt of each kind must be `PASS`; the retained `loop` row shows the cancellation
(`in_flight_at_kill ≥ 1`); earlier attempts are listed as retries and are not clearance evidence. Live checks per
retained row: `docker ps -a --filter name=mlxbench-<run_id>-` (exact registered prefix) is empty — unrelated
containers are neither failures nor targets (test) — and no same-uid process has cwd/argv under that run's scratch
root (listed, never killed). Exit 0 only when every suite-level check holds; `not_observed`/`competing_trigger`
exit 4 (retryable), `FAIL` exit 1.

**Driver** `benchmark/chains/c147/run_inject.py` (operator-run, ≈30 min): lean router via `chain_ops`, load
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, A4 gate, three single-item legs (kinds in the order stall, loop,
alloc; items = three seeded-random Python items from the universe, each kind a different item; seed base from the
retry schedule, attempt n uses 1001/2002/3003 and the same item), `inject_verify.py` after each leg (exit 4
re-runs that kind on the next seed, up to three attempts; exit 1 stops the driver), then once over the run
directory for the suite verdict, unload, `stack_stop.sh`. Before each leg the driver checks `vm_stat` free memory
and the cancel bound; between kinds no idle wait (instrument run, not a latency capture). Output `$STACK_WORKDIR/m62/inject/`; RUNLOG, rc
file, detached launch via `benchmark/chains/c147/drive_inject.sh`.

## 3. tg1 chain runner

**`benchmark/bench/chain_ops.py` (tested).** The M59 helpers extracted with their tripwires intact and unit tests
over fake `ps`/`lsof`/HTTP: `env_base` (dotenv merge, `APC_ENABLED` removed, `MLX_VLM_CACHE_SESSION_MAX=1`,
`MLX_SERVE_CONFIG=<overlay>`, per-run `TMPDIR`), `power_ok` (`pmset -g ac` 140 W AND 28 V, battery strictly > 20 %,
orphan-shell sweep clean; adapter wattage, voltage and battery logged on every watcher tick [P14]), `listeners`,
`busy_procs`, `start_router` (single :8000 listener, env/cwd tripwires), `load`/`unload` (one worker, no predictor,
verified termination), `a4_gate`, `rows`, `stop_stack`, `RunLog`. `leg_rate_check` is NOT carried over (tg1 reads
no decode table). The frozen `benchmark/chains/m59/` files are not modified and `mem_watchdog.py` is NOT launched
[P3]: it kills by cwd/argv and RSS without ownership, which the probe's guard deliberately refuses
(`proc_guard.py` cleanup aborts on path-only processes instead of killing them). The probe's own H2 (per-process,
aggregate and client limits) is the memory containment; the runner only logs `vm_stat` free memory per tick.

**A4 gate for tg1 [P8] [P17].** `scripts/session_pinning_gate.py` gains `--scaffold opencode-v2-web-tg1`: carrier
source `benchmark/opencode_bench_v2_web_tg1.json` through the same `_carrier_selection`, both `noretry.js` and
`toolbounds.js` copied by sha into the gate's bench-owned `OPENCODE_CONFIG_DIR/plugins/`, receipt
`carrier_sha256` = the tg1 selection's `opencode_bench_config_sha256`. The gate's timeout kill targets only the
process group it created with `start_new_session` for its own one-turn opencode child (ownership by session, not by
path; stated and tested: a same-uid process outside that group is never signalled). A gate timeout is a chain
abort (exit 2), never a restart. The existing scaffold paths are byte-for-byte
unchanged (test). A test proves the receipt is accepted by `run_opencode_probe_v2._a4_receipt` for a tg1 selection
with `limit > 5` and refused for a receipt from the web scaffold. `chain_ops.a4_gate` runs it once per loaded
instance and passes `--a4-v2-receipt` to every leg of that instance.

**`benchmark/chains/c147/run_tg1_chain.py`.** Modes `pilot` and `chain [s1 s2 reload]`; `drive_chain.sh` launches
detached, rc in `chain.rc`, log `chain.out`, RUNLOG and `chain.json` (provenance of the drive: sha256 of the runner,
`chain_ops.py`, the gate script, the overlay; every attempt's probe rc, restart and STOP history [P11]) under
`$STACK_WORKDIR/c147/`.

- **Schedule (k=2, AGENTS.md).** Items = the 43 universe items (22 Python, 21 Go; `go/counter` already excluded).
  `s1`: pick1 python, pick1 go, pick2 python, pick2 go; `s2`: pick2 python, pick2 go, pick1 python, pick1 go;
  seed bases 1001 / 2002. The **experimental unit is the model block** = one loaded instance serving both language
  legs of one model inside one session [P6]; the instance changes only at a block boundary and every block is a
  fresh load (unload verified first). `reload` (P240): pick1 python, 5 seeded-random items, seed base 1001, its own
  block after `s2` — a stability control, not an identity claim (C135).
- **Pilot rule.** The first leg of every block starts with `--limit 5` over 5 seeded-random items of that leg's
  language into the leg's own rows file (the probe skips existing ids on the full run). `pilot` mode runs only that
  step for the `s1` pick1 python leg and stops.
- **Execution.** `Popen` (no `subprocess.run` timeout), `start_new_session=True`, stdout/stderr to `<leg>.log`,
  `--expect-items` = the leg's exact id set, `--a4-v2-receipt` from this block's gate, `--scaffold
  opencode-v2-web-tg1`, `--out` under `$STACK_WORKDIR/c147/<session>/<model>.<session>.opencode_<lang>.jsonl`,
  `--sampling-profile deployed` (new probe flag, accepts only `deployed`, recorded in the manifest [P20]),
  `--cancel-file <leg>.attempt<n>.CANCEL` and `--manifest-ack <leg>.attempt<n>.ACK` (unique per attempt [P21];
  a stale cancel or ack file for the attempt path refuses the spawn). Every attempt records
  `attempt.json` = {attempt, probe pid+create_time, run_id, worker identity, argv, cancel/ack paths, rc,
  cleanup status} and is archived with its rows/manifest/log [P3]. **Pilot versus full invocation [P18]:** the
  pilot passes `--limit 5 --expect-items <exactly its five ids>`; the full invocation passes the full language set;
  both write the same rows file (the probe skips existing ids); the argument vectors are tested.
- **Arm state [P20].** At every block boundary the runner idles `--arm-idle-s` (default 600 s) after the unload
  and logs the start state before the load: power (W, V, %), `vm_stat` free memory, busy processes, orphan
  shells. After the load it verifies the WORKER environment (`ps -E` on the worker pid: `MLX_VLM_CACHE_SESSION_MAX=1`,
  `MLX_SERVE_CONFIG` = the overlay, no `APC_ENABLED`) as well as the router's, and records the worker cmdline.
- **First-manifest barrier before item one [P14] [P17].** The probe writes the manifest before item one and, under
  `--manifest-ack`, blocks before any generation until the ack file exists (≤ 300 s, else
  `TransportAbort("manifest not acknowledged")` with nothing generated). The runner reads the manifest and verifies
  `runtime.scaffold == "opencode-v2-web-tg1"`, `runtime.scaffold_policy_sha256 == ba86ba16…` (the pinned campaign
  hash), `runtime.probe_code_sha256 == --probe-code-sha`, `runtime.draft_kind == "off"`, `runtime.seed_base`,
  `runtime.lang` and the model equal to the leg descriptor, `registry.sha256` equal to the overlay the router was
  started with, and `worker` identity equal to the block's recorded identity; then it creates the ack. Any mismatch
  → no ack, the probe aborts itself, chain exit 2. A manifest missing after 120 s is an ALARM while the probe is
  alive (never a cancel; the idle predicate is the only automatic cancel).
- **Watcher (every 300 s) [P14].** Rows: n/total, passed, mean item wall, ETA from the running mean, the
  prediction (`--pred-s` per (lang, model); default = the pilot mean once ≥ 5 rows exist, else the M59 table),
  `nonconv_kind` counts, converged share, output-token quantiles (p50/p90/max) and budget-hit count from the rows;
  power (W, V, battery %); free memory; the probe's latest `m62_watch` heartbeat and its age; `CORRECTION?` when
  ETA/prediction > 1.5 or any `TransportAbort`/`REFUSED` line appears in the leg log (the operator decides).
- **Alarm, not kill.** `expected_s = n_remaining × mean`; `alarm_s = 2 × expected_s + 3 × max_item_wall` (max over
  pilot/running rows, floor 7,200 s). Past the alarm the watcher logs `ALARM` every tick. Time alone never ends a
  leg (M62 §4: silent/BUSY is never killed).
- **Cooperative cancellation contract (probe side) [P4] [P13].** New probe flag `--cancel-file <path>` (tg1
  only). Checked (a) before the discovery spawn, (b) at every item boundary in `_main`, (c) every tick of the
  `run_item` client loop; NOT during the bounded terminal phases (drain, grading, export, cleanup), which finish
  first. In (a)/(b) the probe exits with `TransportAbort("cancelled by runner")` before spawning anything. In (c)
  it sets `termination.reason = "runner_cancel"`, runs the normal stop path (`terminate_client`: client/model kill,
  `wait_cancel`), then the full terminal path — drain, grade join, export, reconcile with `outcome =
  "runner_cancel"` (a new §3a row: one trailing interrupted or unpublished message allowed, exactly as a gate
  stop), final grade and report retention — and then raises `TransportAbort("cancelled by runner")`: the item gets
  NO row; `_main`'s abort path records in the manifest `transport_abort` AND `cancelled_item = {id, evidence
  sha256s, grade_reports, reconciliation, termination, cleanup_status}`. Every abort (cancel or otherwise) now
  records `cleanup_status = {survivors, containers_remaining, uncertain, orphans_unattributed}` from the guard
  [P3]. Tests drive `p.main()` (the real CLI dispatch, via `tg_fixture`) with the pinned client and the mock
  provider for cancellation during discovery, between items, during generation, and a cancel file appearing
  during grading/export (honoured only after the terminal phases), asserting manifest fields, exit code and the
  absence of a row; the SIGTERM→`SystemExit(143)` path stays cleanup-only and is the escalation step.
- **Cancellation decision (runner side) [P5].** The runner may write the cancel file only when ALL of the following
  hold on three consecutive samples ≥ 60 s apart and again immediately before writing: heartbeat line age > 900 s;
  events file byte size unchanged; rows file unchanged; worker `/metrics` readable with `summary.in_flight == 0`
  (unreadable → not idle, logged); worker identity (pid, create_time) unchanged. Any change resets the count. A
  dead heartbeat thread with growing events therefore never cancels (test). Or: `STOP` exists (below).
- **Escalation [P4] [P17].** The heartbeat line gains `last_prompt_tokens` (the last completed request's
  `prompt_j`). After the cancel file: `T_coop = 5 (drain) + 660 (grade join) + max(300, last_prompt_tokens / 300)
  (cancel bound) + 120 (export) + grader timeout of the leg's language (300 Python / 180 Go, final grade) + 60
  (report retention and cleanup) + 20 (process wait)`, computed and logged at cancel time. Before each escalation
  step the runner re-evaluates the idle predicate; if activity resumed (events grew, rows grew, in_flight > 0) it
  logs `ESCALATION HELD` and waits another `T_coop` instead. Then SIGTERM (cleanup-only path), wait 120 s; then
  SIGKILL the probe pid. Restart eligibility [P3]: the probe has exited (waitpid), `attempt.json` carries the
  manifest's `cleanup_status` with no survivors, no remaining containers and `uncertain == false`, the worker
  `/metrics` is readable with `in_flight == 0` and identity unchanged. Any of these false → the chain exits 2
  (`cleanup uncertain` / `worker health`), the runner kills NOTHING and lists same-uid processes under the scratch
  root or `TMPDIR` and `mlxbench-<run_id>-*` containers for the operator.
- **Completion = validation, not row count [P11] [P19].** `chain_ops.validate_leg(leg, pinned)` takes the leg
  descriptor `{session, model, lang, seed_base, expected_ids, out}` and requires: probe rc 0; rows load (torn file
  refuses); ids == expected exactly; `runtime.seed_base`, `runtime.lang` and the manifest model equal the
  descriptor; every row's `sample == 0`, `sample_seed == rowschema.sample_seed(id, 0, seed_base)` and
  seed-overlay hash equal to the descriptor's recomputed value; manifest present with no `transport_abort` and no
  `served_config_drift`; `runtime` identity equal to `pinned` on every field except `seed_base`/`lang`
  (`scaffold`, `scaffold_policy_sha256` == the campaign hash, `probe_code_sha256`, `opencode_version`,
  `opencode_exe_sha256`, `opencode_bench_config_sha256`, `carrier_source_sha256`, `agent_system_sha256`,
  `polyglot_sha`, `universe_sha256`) and `git.serving_path` equal to the chain's first leg; `manifest.worker ==
  row.worker_before == row.worker_after` for every row, typed (int pid, numeric create_time, non-empty model path
  and 64-hex registry sha); every `evidence_sha256` and `grade_reports` sha matches its file and is non-empty. Any
  failure → incomplete with the reason logged. `pinned` for the chain = the campaign hash plus the identity read
  from the first complete leg; the operator's expected `probe_code_sha256` is passed as `--probe-code-sha` (printed
  by `run_opencode_probe_v2.py --print-identity`, a new read-only flag) so an unintended build cannot start a chain.
  Resume eligibility [P19]: the probe's tg1 resume path refuses a rows file whose manifest records
  `transport_abort` (probe-side change, tested); the runner never resumes an attempt that is not validated
  complete — an aborted attempt is archived, never repaired by manifest replacement.
- **Incomplete block [P6] [P21].** Archive every attempt of every leg of the block (`rows`, `manifest`, `log`,
  `attempt.json`, cancel/ack files) to `<session>/incomplete/<model>.<ts>/` (transcripts stay where they are: immutable per run_id); unload the model
  (verified), reload (fresh instance), A4 gate, rerun the block from its first leg (pilot step included) with the
  same items and seeds (the paired schedule is unchanged). One restart per block; a second incomplete → chain
  exits 2. Worker identity must be one value across the block and distinct from every other block (test).
- **STOP [P7].** `touch $STACK_WORKDIR/c147/STOP`: latched on the next watcher tick; no further leg launches; the
  current leg is cancelled cooperatively (escalation as above); its partial rows/manifest are archived under
  `<session>/stopped/<stem>.<ts>/` (no restart consumed); exit 3. Tested during pilot, full leg, restart
  preparation and at a block boundary.
- **Exit codes preserved**; no `|| true`; waiters on pid or rc file (never `pgrep -f` of the runner's own argv).

## 4. `/tmp` escape diagnostic

**Candidates (diagnostic) [P2].** `pg.tmp_escapes(export, env)` reads the export's `content[].type == "tool"`
parts. Exact candidates: `name in (write, edit)` → `state.input.path`, resolved against `state.input.workdir` or
the scratch when relative. Best-effort mentions: `name == "shell"` → from `state.input.command`, (i) `shlex.split`
tokens (on `ValueError` the raw text) that contain `/tmp/` or `/private/tmp/` anywhere — a redirection token
`>/tmp/new`, a token with a trailing `;`/`&`/`|`, a path inside a `python3 -c` string are all reported as
`uncertain` mentions with the containing token; (ii) relative paths are not guessed. Normalise `/private/tmp` →
`/tmp`; a `..`, `.` or empty component → `traversal`; anything under the item's `TMPDIR` or scratch is dropped;
`read` parts are ignored. Row field `tmp_escapes`: `[{path, source: write|edit|shell, exact: bool, token}]`.
Fixtures: a frozen real 2.0.20 export excerpt (`benchmark/bench/tests/fixtures/opencode_2.0.20_tool_parts.json`,
taken from a recorded M61 export's tool parts, sha recorded in the test) plus the registered shell cases above;
`filePath` is not an alias on this client and is not parsed.

**Deletion authority [P1].** Only an EXACT candidate whose creating tool call is ours can be removed: a `write`
part with `state.status == "completed"` (the opencode client the probe owns created the file) or an `edit` part
on a path that was absent from the pre-item listing (below). Shell mentions are never removed automatically; they
are listed for the operator tool `benchmark/m62/tmp_escape_clean.py --rows <file> [--yes]`, which prints each
shell candidate with its token and removes only on explicit `--yes` per path, under the same identity checks.
Identity checks for an automatic removal: before the client is spawned the probe lists the top-level entries of
`/tmp` (name, inode, device; a read-only `os.scandir`); after the item it lists them again; the candidate's first
component under `/tmp` must be absent before and present after (`pre_existing` otherwise); walking from `/tmp`
component by component with `os.open(O_NOFOLLOW | O_DIRECTORY, dir_fd=…)` reaches it without any symlink component
(`symlink` otherwise); `fstat` on the opened object shows our uid (`not_owned`), `st_birthtime` inside the item
window (`outside_window`) and, for the first component, the inode/device of the after-listing (`replaced`); a
regular file is unlinked with `os.unlink(name, dir_fd=parent_fd)` immediately after an `fstatat(parent_fd, name,
AT_SYMLINK_NOFOLLOW)` that still matches the opened inode (`replaced` otherwise; the residual window is the
microseconds between that check and the unlink, stated); a directory is removed only when every entry under it,
walked the same way, satisfies the same checks (`dir_mixed`). Row fields `tmp_cleaned` and `tmp_not_removed:
[[path, reason]]`. Nothing else under `/tmp` is read or removed. Tests run on a real filesystem with the `/tmp`
root injectable (`TMP_ROOT`): every reason above, an unrelated-creator file named in a shell mention (listed, not
removed), a `write` path replaced by another inode between listing and unlink (not removed), a symlinked parent,
a pre-existing name. The probe prints one `tmp_escapes=` line per item for the RUNLOG. V4 reference:
`go/alphametics` s2 wrote `/tmp/bench199_test.go`.

## 5. Grader-report retention [P12]

`structured_grade.grade(..., keep=<dir>, seq=<n>)`: the grader's stdout and stderr are redirected to files in the
keep directory FROM LAUNCH (no `capture_output`; a timeout kill therefore loses nothing [P12]); before parsing,
and on every early return (timeout, container OOM, grader memory kill, missing interpreter) and before any
`TransportAbort` is raised, an `index.json` `{boundary, seq, final, outcome, artifacts: {name: {path, sha256}}}`
is written atomically beside the artifacts: Python `report.xml` (if produced), `stdout.txt`, `stderr.txt`; Go
`go.jsonl`, `go.stderr`. `Grade` gains `artifacts` and `outcome ∈ {parsed, timeout, oom, mem_kill,
missing_report, infrastructure}`; infrastructure failures still raise `TransportAbort` (never an all-failing
grade), and `tg1_runner` builds `grade_reports` from the index files, so the abort manifest (`cancelled_item` or
`transport_abort`) carries the hashed report index even when grading raised. `tg1_runner` passes `keep = <evidence>.grades/` (immutable per run_id; an existing directory
refuses) and a monotonically increasing `seq` shared by snapshot grades and the final grade. New row field
`grade_reports: [{boundary, seq, final: bool, outcome, artifacts}]`; `failing_trajectory` keeps its shape and the
gate outcome is computed exactly as before (replay and the V2 manifest are untouched: a test pins `benchmark/m62/replay_manifest.json`'s sha256 and the
per-fixture replay outcomes — kindergarten-garden `looping@15`, M59 alphametics `looping@22`, book-store no stop —
not merely the 8/8 aggregate).
Both verifiers (`inject_verify.py`, `validate_leg`) check every artifact sha. Tests assert byte-for-byte
preservation of a fixture report, unchanged snapshot manifests, and retention on each early-return path. Always on
under tg1; roughly ≤ 10 MB per item.

## 6. Provenance

Campaign-mode `scaffold_policy_sha256` is unchanged (pinned by test). `probe_code_sha256` changes with this build
(tg1_runner, proc_guard, structured_grade, token_turn_gate edited), as any build does; chains record it. `chain_ops`
and the drivers are not part of the probe identity (they never touch a row) but their sha256s are recorded in the
chain's `chain.json` because they control cancellation and retries [P11]. Inject rows carry the label and the
effective policy. The AGENTS.md M50/M59/M61 text needs no change: inject rows live under `$STACK_WORKDIR`, never
under `benchmark/results`.

## 7. Acceptance criteria (pre-registered; tests fail first)

- **V1 unit/mocked.** Inject: refused off-tg1, refused with >1 item or a non-inject `--out`; each kind lowers
  exactly its own constant (the other two dicts byte-equal the campaign values); the addendum is appended verbatim
  and hashed; row/manifest labels; resume refuses inject↔campaign both ways; the campaign hash pin
  (`ba86ba16…`). `reconcile` returns the summary for every §3a row of M62 plus `runner_cancel`, and still aborts
  where it did. `wait_cancel` returns elapsed; `kill_role` returns the killed list; `mem_kills` carry role/rss/argv/
  request_index. `inject_verify`: fixture rows for each kind → PASS; a non-firing kind → `not_observed`; a
  competing stop → `competing_trigger`; an alloc kill of an unrelated argv → FAIL; a sha mismatch → FAIL.
  A4 gate: tg1 scaffold copies both plugins by sha, receipt accepted by `_a4_receipt` for `limit > 5`; web/legacy
  receipts refused for tg1; the legacy/web gate paths byte-unchanged (golden). `chain_ops`: every tripwire of
  `start_router`/`load`/`unload`/`power_ok` (incl. battery exactly 20 % refused, 28 V required) on fake outputs;
  `validate_leg` fails on each listed condition (including a differing `probe_code_sha256` with equal policy hash,
  an untyped worker identity, an empty evidence sha) and passes on a complete fixture; archive layout per block;
  one restart then exit 2; alarm arithmetic; the cancellation decision table (busy → never; stale heartbeat with
  growing events → never; unreadable metrics → never; three idle samples + recheck → cancel file; escalation
  timings; STOP during pilot/full leg/restart preparation/block boundary → exit 3 without a restart) against a fake
  probe that implements the recorded contract; first-manifest check mismatch → cancel + exit 2; schedule order,
  seeds, block = both legs, pilot-then-full, reload control, exit-code propagation; watcher fields. `/tmp`: parser
  fixtures from the 2.0.20 shape and every removal reason on a real filesystem. Reports: Python and Go fixture
  grades retain artifacts with shas on parsed and each early-return path; `grade_reports` on the row; final grade
  included; `failing_trajectory` unchanged; existing suites green; `m62/replay.py` V2 still 8/8.
- **V2 composed [P13] [P16].** (a) Real `p.main()` via `tg_fixture` + pinned client (`OPENCODE_PROBE_BIN`) +
  mock provider: the cancel file (during discovery, between items, during generation, during grading/export)
  produces export, reconciliation (`runner_cancel`), retained artifacts, `cancelled_item` in the manifest, no row
  and the registered exit code; a real-client `loop` case (mock script: three identical shell calls) stops
  `looping` with the detached descendant killed and verified; a real-client `alloc` case (mock script: the
  bytearray command under the lowered threshold) produces the `mem_kills` record with tool-call linkage and
  freezes the killed-command tool-part fixture by sha. (b) `tg_fixture` with `--tg1-inject stall` over fixture events → a labelled
  row under a temporary `m62/inject/` with `runtime.inject`; the campaign fixture run gains `reconciliation`,
  `termination.killed`, `tmp_escapes`, `grade_reports`. (c) The runner end-to-end against the fake probe:
  pilot → full → cooperative cancel → escalation → archive → restart → completion validation, and STOP. The real
  probe entry point cannot be driven as a subprocess in tests: M50 refuses unless the sole :8000 owner is a live
  mlx-serve with the registry config, and the rule allows no bypass. The contract between runner and probe
  (manifest-before-item-one, heartbeat line format, cancel file, rc semantics) is therefore pinned by tests on
  BOTH sides, and the live `pilot` mode is the composed real test. Clearance of the chain runner stays
  "pending live" until the operator's pilot leg validates.
- **V3 (operator, box, ≈30 min).** `run_inject.py`: `inject_verify.py` PASS for all three kinds (with the seed
  retry schedule); zero surviving attributed processes/containers; worker identity unchanged. Required before the
  first chain. Then `run_tg1_chain.py pilot` (5 items) validates the runner live before `chain`.
- **V5** cold reviews (Codex `gpt-6.1-sol`): this spec before the build; the implementation after it.

## 8. Workflow

Spec → cold review → implementation by a worker model from this spec, failing tests first, no docs/handoff edits
→ lead verification (V1, V2) → second cold review → handoff. The operator runs V3 and the P223 chains.

## 9. Build findings (2026-10-10, implementation from revision 3)

- **B1 — the live stop path never reconciled before this build.** `terminate_client` SIGKILLed the client; the
  pinned opencode 2.0.20 persists an in-flight assistant message only when its step finishes, so a kill landing
  after `step_start` left the export without that message and `reconcile` aborted ("empty assistant export" /
  "active live message does not reconcile") on 8 of 8 real-client runs. V3/V4 never exercised a stop, which is
  exactly the C147 (1) gap. Fix: `ProcessGuard.graceful_stop("client", 15)` sends SIGTERM first; opencode then
  persists the trailing message with `error.type == "aborted"` and no usage (the §3a `interrupted` row), and
  SIGKILL follows only for survivors after 15 s; model-role processes stay SIGKILL. Recorded per row as
  `termination.client_stop ∈ {sigterm, sigkill}` and `termination.graceful_wait_s`. On SIGTERM the client also
  emits one `error` event `{type: "unknown", message: "Transport: The socket connection was closed
  unexpectedly…"}`; `reconcile` ignores exactly that event, only for our own stop outcomes (`KILL_OUTCOMES`
  including `runner_cancel`), and still aborts on a normal exit, on any other error, or when an unrelated error
  accompanies it.
- **B1b — interrupted message with usage.** When SIGTERM lands inside a long tool call after the stream finished
  (the live `exec_timeout` shape), the aborted trailing message carries real usage. Rule added to §3a for our own
  stop outcomes only: accepted and CHARGED like the completed-but-unpublished case, `trailing =
  "interrupted_charged"`; a normal exit, a non-trailing position or malformed usage still abort. The verifier
  accepts `trailing ∈ {interrupted, unpublished, interrupted_charged}` for stall/loop.
- **B2 — alloc threshold.** 256 MiB killed opencode's own `opencode serve` child (≈ 380 MiB, tracked as a client
  descendant). No guard special case: the `alloc` kind lowers `per_process` to 512 MiB and allocates 1 GiB; campaign
  `ProcessGuard` semantics are unchanged apart from the new return values, `status()`, `graceful_stop`,
  `verify_gone` and a cleanup sweep that continues past a container-removal failure and raises at the end.
- **B3 — killed-command shape.** The pinned client reports a SIGKILLed shell call as `status: "completed"` with
  `metadata.signal == "SIGKILL"`, not as an error; fixture `opencode_2.0.20_killed_tool_part.json` frozen by sha;
  the verifier accepts "error, or completed with a signal or a nonzero exit".
- **B4 — cancel exit code.** A runner cancel exits rc 1 through the existing `REFUSED:` handler; the runner
  distinguishes it by the manifest's `transport_abort` text plus `cancelled_item`. `tool_call_id` for a memory
  kill is resolved when the item finishes (the `tool_use` event arrives after the kill), matched by argv when a
  request carries several shell calls.
- **B5 — fail-first.** Both workers wrote code before tests and proved the tests bite by reverting the sources
  (95 failures on HEAD sources, probe side) and by three named mutations (chain side). Recorded as a deviation.
- **B6 — chain runner contract.** `validate_leg` reads the probe rc from the leg descriptor; the in-item events
  size for the idle predicate is the byte total of the run's transcript directory; heartbeat age is measured from
  the runner's first observation of the current line; `pilot` mode uses its own `<out-root>/pilot/` directory with
  a fresh load (the probe's resume check refuses a rows file from another worker); a STOP-cancelled leg that
  validates complete is kept; the inject driver passes neither `--cancel-file` nor `--manifest-ack`.
- **B7 — post-build cold review 1 (Codex `gpt-6.1-sol`, `codex_impl_review1.md`): "not cleared", Q1–Q11; all
  fixed in the follow-up commit.** Q1 the runners' `finally` called `scripts/stack_stop.sh`, whose name-based sweep
  would kill a router the runner did not start (e.g. after a refusal on an existing listener) → teardown only the
  router/worker identities the runner itself started, nothing after a refusal. Q2 an errored `edit` could authorise
  deletion and directories were deleted recursively → `edit` requires `completed` + absent-before; no recursive
  deletion, only recorded files and then-empty directories. Q3 the probe wrote `cleanup_status` inside
  `transport_abort` while the runner read it top-level, masked by the fake probe → top-level is the contract, a real
  probe-produced abort manifest is a fixture for the runner test. Q4 `validate_leg` accepted inject-labelled rows,
  a wrong model, a missing `overlay_sha256`, empty final artifacts and unpinned identity fields → all required.
  Q5 an unreadable latest inject attempt let an earlier PASS stand → latest attempt always retained; empty `--kind`
  fails. Q6 any changed summary counter counted as cancellation proof → counter rule tied to the worker's
  `/metrics` fields, natural completion is `not_observed:cancellation`. Q7 a cancel during the last item's terminal
  phases was ignored → re-checked before the row commit. Q8 the SIGTERM transport-error tolerance accepted any
  count/order → post-signal event index, one of each shape. Q9 `psutil.AccessDenied` in cleanup inspection was
  uncaught → transient for untracked, `uncertain` for tracked. Q10 a tampered (legitimately failed) row had no
  final report and made the leg incomplete → typed `tampered` final receipt. Q11 escalation re-checked only part of
  the idle predicate → full predicate; identity drift aborts without signalling.
- **B8 — post-build cold review 2 (`codex_impl_review2.md`): "not cleared", Q12–Q18.** Q12 `start_router` adopted
  whichever pid held :8000 after the spawn → ownership requires the listener to be the spawned pid or its
  descendant; teardown re-verifies router/worker identities before unload/signals. Q13 a completed `edit` of an
  externally created file could be deleted → DECISION: automatic deletion is `write` parts only, and only when the
  on-disk bytes still equal the written `content` (residual: an external same-name file our write tool overwrote).
  Q14 `pin_from` required every identity field truthy, but the real carrier sets `agent_system_sha256` to `null`
  without an overlay (the fake probe masked it) → null pinned as a value, absent keys refuse. Q15 report receipts
  unvalidated → `structured_grade.validate_reports` schema (typed fields, unique seq, exactly one final with a
  permitted outcome, language artifacts, tampered exception) used by both verifiers. Q16 transport tolerance →
  complete messages pinned, cutoff at the events-file byte offset captured immediately before SIGTERM. Q17
  `AccessDenied` on a tracked pid could certify it gone → tracked identities audited directly; denial = unknown,
  `uncertain`, abort; `verify_gone` false on unknown. Q18 no correlated cancellation receipt exists in the worker →
  DECISION: the verdict is `cancellation_consistent` (in_flight ≥ 1 at kill, → 0 within the bound, `requests_completed`
  unchanged), accepted for clearance and labelled as not correlated; a worker-side cancellation counter is proposed
  as C149.
- **B9 — post-build cold review 3 (`codex_impl_review3.md`): "not cleared", Q19–Q25; all fixed in the
  follow-up commit.** Q19 the HTTP unload had no endpoint ownership check → `ChainOps.unload` requires the sole
  :8000 listener to be the recorded router and the worker to be the one this process loaded; the inject driver
  routes through it. Q20 a write path replaced by a directory was `rmdir`'d without the content match → a write
  candidate must still be a regular file with matching content. Q21 the null-pinning fix also accepted null
  mandatory fingerprints → only `agent_system_sha256` may be null; the rest must be well-formed at the barrier, at
  pinning and at validation. Q22 the transport cutoff was captured before the guard's pre-signal scan → captured by
  a callback immediately before SIGTERM; no signal, no tolerance. Q23 a Python collection error (no XML) was a
  scored failure for the grader but an invalid final receipt → typed `collection_error` outcome. Q24 non-parsed
  receipts accepted any artifact → launch-output artifacts required for every grade that ran. Q25 attempts without
  a `run_id` skipped the live checks and could PASS → `run_id` required, live checks run for every retained attempt.
- **B10 — post-build cold review 4 (`codex_impl_review4.md`): "not cleared", Q26–Q28 (three boundary cases the
  reviewer itself judged not to invalidate an ordinary positive live run); fixed in the follow-up commit.** Q26
  `/v1/models/load` had no router-ownership check and `unload` rescanned after a "no worker" result → one
  `_require_own_router` guard before every destructive HTTP call; single guarded worker scan. Q27 an emptied parent
  directory was `rmdir`'d without re-validating its identity → parent (dev, ino) recorded during the walk and
  re-checked by name before removal. Q28 the transport-tolerance cutoff was armed even when SIGTERM failed →
  published only after a successful `terminate()`. Lead decision: the review loop stops after this round; the
  operator's live V3 run and the chain pilot are the clearance.
