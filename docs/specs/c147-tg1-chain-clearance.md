# C147 — tg1 chain clearance: injected positives, chain runner, `/tmp` escape diagnostic, grader-report retention

Status: REVISION 1, 2026-10-10. Design P236–P241 approved by the operator 2026-10-10 ("sounds good"), with cold
review on Codex `gpt-6.1-sol` before and after the build. Long-haul box runs (the ≈30 min injected run and the
≈20 h P223 chains) are the operator's; this build ships code, tests and the handoff only. Parent spec:
`docs/specs/m62-token-turn-gate.md` (rev 5 + §9); owed list: `docs/open-questions.md` C147.

## 1. Scope

Four deliverables, all under `benchmark/`, none changing the campaign tg1 policy or any pick:

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
| `alloc` | hygiene `per_process` 8 GiB → **256 MiB** | one `mem_kills` entry with role `model`; the shell call errors; the session continues |

`T` (81,920), the ceilings, `thinking_budget`/`max_tokens` carrier checks, `aggregate`, `client_limit`, silence and
cancellation constants are unchanged in every kind.

**Prompt addendum (hashed).** Each kind appends one fixed sentence to the item prompt so the positive is driven
deterministically rather than hoped for (the rows are instrument proofs, never model evidence):

- `stall`: "Before anything else, run the shell command `ls` four separate times, one tool call per message, and
  only then start the task."
- `loop`: "Before anything else, run the shell command `ls` three times in a row as three separate tool calls, and
  only then start the task."
- `alloc`: "Before anything else, run exactly this shell command once:
  `python3 -c "import time; b = bytearray(400 * 1024 * 1024); time.sleep(90)"` and only then start the task."

The addendum text is part of the inject policy and its sha256 is recorded. A kind whose expected observation does
not occur (the model did not comply) is reported by the verifier as `not_observed`, never as a pass; the operator
re-runs that kind with the next seed. Two consecutive `not_observed` for one kind → the kind is a build finding,
not a shrug.

**Labelling.** Row `scaffold` and manifest `runtime.scaffold` = `opencode-v2-web-tg1-inject:<kind>`;
`runtime.inject` = `{kind, policy (full effective gate + hygiene dicts), prompt_addendum_sha256}`;
`scaffold_policy_sha256` is computed over the effective policy, so it differs from the campaign hash. Resume refuses
mixing (existing `runtime` equality check); the campaign path never reads `INJECT_POLICY`. A test pins the campaign
`scaffold_policy_sha256` to the value recorded in the V3 manifest (`$STACK_WORKDIR/m62/v3/*.manifest.json`, copied
into the test as a constant) so this build cannot move it.

**Row additions (all tg1 rows, campaign too; the V3/V4 rows predate them and are never pooled with chains):**
- `reconciliation`: `{unmatched_export_messages, trailing: "none"|"interrupted"|"unpublished"|"final"}` returned by
  `token_turn_gate.reconcile` (today it returns nothing; the function's abort behaviour is unchanged).
- `termination.cancel_wait_s`: seconds until worker `summary.in_flight` reached 0 after the kill (from `wait_cancel`,
  which returns the elapsed time; `None` when no kill happened).

**Verifier** `benchmark/m62/inject_verify.py <rows.jsonl>...` prints one line per row and exits nonzero on any
`FAIL`; `not_observed` exits nonzero too, with its own label. Per row it checks: `scaffold` label and
`runtime.inject.kind` match the file; the kind's expected observation (table above) from `nonconv_kind`,
`gate.stop_reason`, `gate.no_progress_requests` / `gate.max_identical_run_live` / `mem_kills`; for `stall` and
`loop`: `termination.reason` equals the stop, `termination.cancel_wait_s` is a number within the cancel bound,
`reconciliation.trailing ∈ {interrupted, unpublished}`; for `alloc`: the export (from `transcript_path`) has a
`shell` part whose `command` contains `bytearray(` with status `error`; for every row: `worker_before ==
worker_after`, every `evidence_sha256` matches the file on disk, `orphans_unattributed` is printed (never fails),
and the live checks `docker ps -a --filter name=mlxbench-` is empty and no same-uid process has cwd/argv under the
run's scratch root.

**Driver** `benchmark/chains/c147/run_inject.py` (operator-run, ≈30 min): lean router via `chain_ops`, load
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, A4 gate, three single-item legs (kinds in the order stall, loop,
alloc; items = three seeded-random Python items from the universe, seed base 1001, each kind a different item),
`inject_verify.py` over the three rows, unload, `stack_stop.sh`. Output `$STACK_WORKDIR/m62/inject/`; RUNLOG, rc
file, detached launch via `benchmark/chains/c147/drive_inject.sh`.

## 3. tg1 chain runner

**`benchmark/bench/chain_ops.py` (tested).** The M59 helpers extracted with their tripwires intact and unit tests
over fake `ps`/`lsof`/HTTP: `env_base` (dotenv merge, `APC_ENABLED` removed, `MLX_VLM_CACHE_SESSION_MAX=1`,
`MLX_SERVE_CONFIG=<overlay>`, per-run `TMPDIR`), `power_ok` (140 W, battery ≥ 20 %, orphan-shell sweep clean),
`listeners`, `busy_procs`, `start_router` (single :8000 listener, env/cwd tripwires), `load`/`unload` (one worker,
no predictor, verified termination), `a4_gate` (per loaded instance; receipt passed to every leg so `limit > 5`
legs are admissible), `rows`, `stop_stack`, `RunLog`. `leg_rate_check` is NOT carried over (tg1 reads no decode
table). The frozen `benchmark/chains/m59/run_m59.py` is not modified; `mem_watchdog.py` there is launched as-is
(`--limit-gb 12`) as the backstop above the probe's own H2.

**`benchmark/chains/c147/run_tg1_chain.py`.** Modes `pilot` and `chain [s1 s2 reload]`; `drive_chain.sh` launches
detached, rc in `chain.rc`, log `chain.out`, RUNLOG under `$STACK_WORKDIR/c147/`. Operator stop: touch
`$STACK_WORKDIR/c147/STOP` (checked by the watcher; cancels the current leg through the §3 cancellation path and
exits 3).

- **Schedule (k=2, AGENTS.md).** Items = the 43 universe items (22 Python, 21 Go; `go/counter` already excluded).
  `s1`: pick1 python, pick1 go, pick2 python, pick2 go; `s2`: pick2 python, pick2 go, pick1 python, pick1 go;
  seed bases 1001 / 2002. Each session is a fresh loaded instance (unload at the boundary, verified); within a
  session the instance changes only at the pick boundary. `reload` (P240): pick1 python, 5 seeded-random items,
  seed base 1001, a fresh instance after `s2` — a stability control, not an identity claim (C135).
- **Pilot rule.** The first leg of every loaded instance starts with `--limit 5` over 5 seeded-random items of
  that leg's language into the leg's own rows file (the probe skips existing ids on the full run). `pilot` mode
  runs only that step for pick1 python and stops.
- **Execution.** `Popen` (no `subprocess.run` timeout), `start_new_session=True`, stdout/stderr to
  `<leg>.log`, `--expect-items` = the leg's exact id set, `--a4-v2-receipt` from this instance's gate,
  `--scaffold opencode-v2-web-tg1`, `--out` under `$STACK_WORKDIR/c147/<session>/<model>.<session>.opencode_<lang>.jsonl`.
- **Watcher (every 300 s).** Rows: n/total, passed, mean item wall, ETA from the running mean, the prediction
  (`--pred-s` per (lang, model); default = the pilot mean once ≥ 5 rows exist, else the M59 table), nonconv
  kinds, power; the probe's latest `m62_watch` heartbeat and its age; `CORRECTION?` flag when ETA/prediction >
  1.5 or any `TransportAbort`/`REFUSED` line appears in the leg log (the operator decides; the runner does not).
- **Alarm, not kill.** `expected_s = n_remaining × mean`; `alarm_s = 2 × expected_s + 3 × max_item_wall` (max over
  pilot/running rows, floor 7,200 s). Past the alarm the watcher logs `ALARM` every tick. Time alone never ends a
  leg (M62 §4: silent/BUSY is never killed).
- **Cancellation (the only runner-initiated stop).** Conditions: the heartbeat line is older than 900 s AND three
  worker `/metrics` samples ≥ 60 s apart show `summary.in_flight == 0`; or `STOP` exists. Action: SIGTERM to the
  probe pid (its `defer_signals` cleanup kills owned descendants, exports, reconciles, writes the manifest
  `transport_abort`); wait up to `660 + max(300, cancel bound) + 120` s; then SIGKILL the probe pid; then list and
  kill same-uid processes whose cwd/argv lies under the leg's scratch root or `TMPDIR` (excluding the router,
  worker and the runner's own session), remove `mlxbench-*` containers, and log everything killed. The leg is then
  incomplete.
- **Completion = validation, not row count.** `chain_ops.validate_leg(out, expected_ids)` requires: rc 0; rows
  load (torn file refuses); ids == expected exactly; manifest present with no `transport_abort` and no
  `served_config_drift`; `runtime.scaffold == "opencode-v2-web-tg1"`; `runtime.scaffold_policy_sha256` equal
  across every leg of the chain (first leg sets it); `manifest.worker == row.worker_before == row.worker_after`
  for every row; every `evidence_sha256` matches its file. Any failure → incomplete, with the reason logged.
- **Incomplete leg.** Archive `rows`, `manifest`, `log` to `<session>/incomplete/<stem>.<ts>/` (transcripts stay
  where they are: immutable per run_id); unload the model (verified), reload (fresh instance), A4 gate, rerun the
  leg from item one (pilot step included). One restart per leg; a second incomplete → chain exits 2.
- **Exit codes preserved**; no `|| true`; waiters on pid or rc file (never `pgrep -f` of the runner's own argv).

## 4. `/tmp` escape diagnostic

`tg1_runner` after every item (campaign and inject): `pg.tmp_escapes(export)` collects candidate paths from the
export's tool parts — `write`/`edit`: `state.input.filePath`; `shell`: every match of
`(?<![\w./-])(/private)?/tmp/[^\s'"\x60;|&()<>]+` in `state.input.command` — normalises `/private/tmp` to `/tmp`,
deduplicates, and drops anything under the item's own `TMPDIR` or scratch. Row fields: `tmp_escapes` (all
candidates), `tmp_cleaned` (removed), `tmp_not_removed` (`[path, reason]` with reasons `missing`, `symlink`,
`not_owned`, `outside_window`, `dir_mixed_window`, `not_regular`). Removal rule, per listed path only: `lstat`
(no symlink following); owner uid == ours; `st_birthtime ≥ item_start − 1 s`; a regular file is unlinked; a
directory is removed only if every entry under it (walked without following symlinks) also has an in-window birth
time. Nothing else under `/tmp` is listed, read or removed. The probe prints one `tmp_escapes=` line per item for
the RUNLOG. V4 reference: `go/alphametics` s2 wrote `/tmp/bench199_test.go`.

## 5. Grader-report retention

`structured_grade.grade(..., keep=<dir>)`: after parsing, the report (`report.xml` for Python; `go.jsonl` and
`go.stderr` for Go) is copied to `<keep>/<boundary>.<seq>.<ext>` and `Grade` gains `report_sha256` and
`report_path`. `tg1_runner` passes `keep = <evidence>.grades/` (the item's immutable evidence directory; an
existing path refuses like the other evidence files) for every snapshot grade and the final grade. New row field
`grade_reports: [[boundary, seq, sha256, portable_path]]`; `failing_trajectory` keeps its shape (replay and the
V2 manifest are untouched). Always on under tg1; roughly ≤ 10 MB per item.

## 6. Provenance

Campaign-mode `scaffold_policy_sha256` is unchanged (pinned by test). `probe_code_sha256` changes with this build
(tg1_runner, proc_guard, structured_grade, token_turn_gate edited), as any build does; chains record it. `chain_ops`
and the drivers are not part of the probe identity (they never touch a row). Inject rows carry the label and the
effective policy. The AGENTS.md M50/M59/M61 text needs no change: inject rows live under `$STACK_WORKDIR`, never
under `benchmark/results`.

## 7. Acceptance criteria (pre-registered; tests fail first)

- **V1 unit/mocked.** Inject: refused off-tg1, refused with >1 item or a non-inject `--out`; each kind lowers
  exactly its own constant (the other two dicts byte-equal the campaign values); the addendum is appended verbatim
  and hashed; row/manifest labels; resume refuses inject↔campaign both ways; the campaign hash pin. `reconcile`
  returns the summary for every §3a row of M62 and still aborts where it did. `wait_cancel` returns elapsed.
  `inject_verify`: fixture rows for each kind → PASS; a non-firing kind → `not_observed` nonzero; a row whose
  evidence sha mismatches → FAIL. `chain_ops`: every tripwire of `start_router`/`load`/`unload`/`power_ok` on fake
  outputs; `validate_leg` fails on each listed condition and passes on a complete fixture; archive layout; one
  restart then exit 2; alarm arithmetic; cancellation table (busy → never; stale+idle 3 samples → SIGTERM →
  escalation after the bound; STOP file) with a fake probe process; schedule order, seeds, pilot-then-full, reload
  control, exit-code propagation. `/tmp`: parser fixtures (write/edit `filePath`, shell with `/private/tmp`,
  quoted, several in one command, under-TMPDIR excluded); every removal branch with a fake stat. Reports: Python
  and Go fixture grades write files with the recorded sha; `grade_reports` on the row; final grade included;
  `failing_trajectory` unchanged; existing suites green; `m62/replay.py` V2 still 8/8.
- **V2 mocked end-to-end.** `tg_fixture` with `--tg1-inject stall` over fixture events → a labelled row under a
  temporary `m62/inject/` with `runtime.inject`; the campaign `tg_fixture` run gains `reconciliation`,
  `tmp_escapes`, `grade_reports`.
- **V3 (operator, box, ≈30 min).** `run_inject.py`: `inject_verify.py` PASS for all three kinds; zero surviving
  attributed processes/containers; worker identity unchanged. Required before the first chain.
- **V5** cold reviews (Codex `gpt-6.1-sol`): this spec before the build; the implementation after it.

## 8. Workflow

Spec → cold review → implementation by a worker model from this spec, failing tests first, no docs/handoff edits
→ lead verification (V1, V2) → second cold review → handoff. The operator runs V3 and the P223 chains.
