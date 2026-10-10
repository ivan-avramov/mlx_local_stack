# C147 — tg1 chain clearance: injected positives, chain runner, `/tmp` escape diagnostic, grader-report retention

Status: REVISION 2, 2026-10-10. Design P236–P241 approved by the operator 2026-10-10 ("sounds good"), with cold
review on Codex `gpt-6.1-sol` before and after the build. Revision 1 drew "redesign" (findings P1–P14,
`$STACK_WORKDIR/c147/codex_design_review1.md`); revision 2 answers each, tagged `[Pn]` where the answer lives. Long-haul box runs (the ≈30 min injected run and the
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
rather than hoped for (the rows are instrument proofs, never model evidence). Compliance is NOT deterministic
[P9]: the verifier classifies every row (below) and a non-firing kind is re-run on the next seed base of the fixed
schedule 1001 → 2002 → 3003 (three attempts per kind; a third miss is a build finding, not a shrug).

- `stall`: "Before anything else, run the shell command `ls` four separate times, one tool call per message, and
  only then start the task."
- `loop`: "Before anything else, run the shell command `ls` three times in a row as three separate tool calls with
  exactly the same command text and working directory, and only then start the task." (On opencode 2.0.20 the
  shell input is exactly `{command, workdir}` — verified from a recorded export — so an identical command in the
  same directory is an identical gate signature.)
- `alloc`: "Before anything else, run exactly this shell command once:
  `python3 -c "import time; b = bytearray(400 * 1024 * 1024); time.sleep(90)"` and only then start the task."

The addendum text is part of the inject policy and its sha256 is recorded.

**Registered trigger predicates (from the row and raw events, not from the label) [P9].**

| kind | PASS predicate | other outcomes |
|---|---|---|
| `stall` | `gate.stop_reason == "stalled"` and (`no_progress_requests ≥ 4` or `no_progress_tokens ≥ 81,920`); the verifier records which clause held | a different stop → `competing_trigger:<reason>`; no stop → `not_observed` |
| `loop` | `gate.stop_reason == "looping"` and `max_identical_run_live ≥ 3`; the three identical signatures are re-derived from the events file | as above |
| `alloc` | one `mem_kills` entry with `role == "model"`, whose recorded `argv` contains `bytearray(`, whose `request_index` is the request carrying the `bytearray(` shell part, that part's state is `error`, and `gate.requests_completed > request_index` (the session continued) | kill absent → `not_observed`; kill of an unrelated process → `FAIL` |

**Causal evidence of the live path [P10].** Rows gain `termination.killed` = `[{pid, create_time, role}]` from
`kill_role` (every tracked process it signalled), `termination.cancel_wait_s` (elapsed until worker
`summary.in_flight == 0`, `wait_cancel` returns it), `termination.in_flight_at_kill` (the `/metrics` value sampled
immediately before the kill) and `gate.inflight_s_at_stop` (already recorded). `mem_kills` entries gain `role`,
`rss`, `argv` (PII-scrubbed) and `request_index` (completed requests at the kill). For `stall` and `loop` the
verifier requires `termination.killed` to include the client pid, `termination.reason` to equal the stop,
`reconciliation.trailing ∈ {interrupted, unpublished}` and `cancel_wait_s` to be a number within the cancel bound.
Across the stall and loop rows together at least one must show `in_flight_at_kill ≥ 1` (a request was in flight
when the kill landed, so `cancel_wait_s` measured a real cancellation); otherwise the verifier reports
`not_observed:cancellation` and the operator re-runs the stall kind on the next seed. The `alloc` kind proves the
tracked-descendant kill: the allocating process is alive and tracked when the per-process threshold fires.

**Verifier** `benchmark/m62/inject_verify.py <rows.jsonl>...` prints one line per row (`PASS`, `FAIL`,
`not_observed[:what]`, `competing_trigger:<reason>`) and exits nonzero unless every row is `PASS`. Per row it
checks the label and `runtime.inject.kind`, the predicate table, the causal evidence above, `worker_before ==
worker_after`, every `evidence_sha256` and every `grade_reports` artifact sha against the file on disk [P12], and
prints `orphans_unattributed` (never fails on it). Live checks: `docker ps -a --filter name=mlxbench-<run_id>-` is
empty for the row's run_id (exact registered prefix, never all `mlxbench-*` [P3]) and no same-uid process has
cwd/argv under that run's scratch root (listed, never killed by the verifier).

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
alloc; items = three seeded-random Python items from the universe, each kind a different item; seed base from the
retry schedule, attempt n uses 1001/2002/3003 and the same item), `inject_verify.py` after each leg (a non-PASS
re-runs that kind on the next seed, up to three attempts), unload, `stack_stop.sh`. Output `$STACK_WORKDIR/m62/inject/`; RUNLOG, rc
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

**A4 gate for tg1 [P8].** `scripts/session_pinning_gate.py` gains `--scaffold opencode-v2-web-tg1`: carrier source
`benchmark/opencode_bench_v2_web_tg1.json` through the same `_carrier_selection`, both `noretry.js` and
`toolbounds.js` copied by sha into the gate's bench-owned `OPENCODE_CONFIG_DIR/plugins/`, receipt
`carrier_sha256` = the tg1 selection's `opencode_bench_config_sha256`. The existing scaffold paths are byte-for-byte
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
  `--cancel-file <leg>.CANCEL` (below).
- **First-manifest check before item two [P14].** The probe writes the manifest before item one; the runner waits
  for it (≤ 120 s, else cooperative cancel) and verifies `runtime.scaffold == "opencode-v2-web-tg1"`,
  `runtime.scaffold_policy_sha256 == ba86ba16…` (the pinned campaign hash), `runtime.draft_kind == "off"`,
  `registry.sha256` equal to the overlay the router was started with, and `worker` identity equal to the block's
  recorded identity. Any mismatch → cooperative cancel, chain exit 2.
- **Watcher (every 300 s) [P14].** Rows: n/total, passed, mean item wall, ETA from the running mean, the
  prediction (`--pred-s` per (lang, model); default = the pilot mean once ≥ 5 rows exist, else the M59 table),
  `nonconv_kind` counts, converged share, output-token quantiles (p50/p90/max) and budget-hit count from the rows;
  power (W, V, battery %); free memory; the probe's latest `m62_watch` heartbeat and its age; `CORRECTION?` when
  ETA/prediction > 1.5 or any `TransportAbort`/`REFUSED` line appears in the leg log (the operator decides).
- **Alarm, not kill.** `expected_s = n_remaining × mean`; `alarm_s = 2 × expected_s + 3 × max_item_wall` (max over
  pilot/running rows, floor 7,200 s). Past the alarm the watcher logs `ALARM` every tick. Time alone never ends a
  leg (M62 §4: silent/BUSY is never killed).
- **Cooperative cancellation contract (probe side) [P4].** New probe flag `--cancel-file <path>` (tg1 only). The
  `run_item` loop checks the file every tick; when it appears the probe sets `termination.reason =
  "runner_cancel"`, runs the normal stop path (`terminate_client`: client/model kill, `wait_cancel`), then the full
  terminal path — drain, grade join, export, reconcile with `outcome = "runner_cancel"` (a new row of the §3a
  table: one trailing interrupted or unpublished message allowed, exactly as a gate stop), final grade and report
  retention — and then raises `TransportAbort("cancelled by runner")`: the item gets NO row, the manifest records
  `transport_abort`, and every evidence file (events, stderr, export, grade reports) is retained with its sha in the
  manifest under `cancelled_item`. A test drives this with the real `run_item`, the pinned client and the mock
  provider and asserts the export and reconciliation exist afterwards; the existing SIGTERM→`SystemExit(143)` path
  (cleanup only, no export) is unchanged and remains the escalation step.
- **Cancellation decision (runner side) [P5].** The runner may write the cancel file only when ALL of the following
  hold on three consecutive samples ≥ 60 s apart and again immediately before writing: heartbeat line age > 900 s;
  events file byte size unchanged; rows file unchanged; worker `/metrics` readable with `summary.in_flight == 0`
  (unreadable → not idle, logged); worker identity (pid, create_time) unchanged. Any change resets the count. A
  dead heartbeat thread with growing events therefore never cancels (test). Or: `STOP` exists (below).
- **Escalation [P4].** After the cancel file: wait `T_coop = 5 (drain) + 660 (grade join) + cancel bound
  (max(300, prompt/300)) + 120 (export) + 300 (final grade) + 60 = 1,445 s` (+ the Go grader's 180 s when the leg is
  Go) for the probe to exit; then SIGTERM (cleanup-only path), wait 120 s; then SIGKILL the probe pid. After any
  SIGKILL the runner lists same-uid processes whose cwd/argv lies under the leg's scratch root or `TMPDIR` and
  `mlxbench-<run_id>-*` containers, kills NOTHING [P3], and if any exist marks the chain `cleanup uncertain` and
  exits 2 for the operator (the probe's own guard would have aborted on the same evidence).
- **Completion = validation, not row count [P11].** `chain_ops.validate_leg(out, expected_ids, pinned)` requires:
  probe rc 0; rows load (torn file refuses); ids == expected exactly; manifest present with no `transport_abort`
  and no `served_config_drift`; `runtime` identity equal to `pinned` on every field except `seed_base`/`lang`
  (`scaffold`, `scaffold_policy_sha256` == the campaign hash, `probe_code_sha256`, `opencode_version`,
  `opencode_exe_sha256`, `opencode_bench_config_sha256`, `carrier_source_sha256`, `agent_system_sha256`,
  `polyglot_sha`, `universe_sha256`) and `git.serving_path` equal to the chain's first leg; `manifest.worker ==
  row.worker_before == row.worker_after` for every row, typed (int pid, numeric create_time, non-empty model path
  and 64-hex registry sha); every `evidence_sha256` and `grade_reports` sha matches its file and is non-empty. Any
  failure → incomplete with the reason logged. `pinned` for the chain = the campaign hash plus the identity read
  from the first complete leg; the operator's expected `probe_code_sha256` is passed as `--probe-code-sha` (printed
  by `run_opencode_probe_v2.py --print-identity`, a new read-only flag) so an unintended build cannot start a chain.
- **Incomplete block [P6].** Archive every leg of the block (`rows`, `manifest`, `log`) to
  `<session>/incomplete/<model>.<ts>/` (transcripts stay where they are: immutable per run_id); unload the model
  (verified), reload (fresh instance), A4 gate, rerun the block from its first leg (pilot step included) with the
  same items and seeds (the paired schedule is unchanged). One restart per block; a second incomplete → chain
  exits 2. Worker identity must be one value across the block and distinct from every other block (test).
- **STOP [P7].** `touch $STACK_WORKDIR/c147/STOP`: latched on the next watcher tick; no further leg launches; the
  current leg is cancelled cooperatively (escalation as above); its partial rows/manifest are archived under
  `<session>/stopped/<stem>.<ts>/` (no restart consumed); exit 3. Tested during pilot, full leg, restart
  preparation and at a block boundary.
- **Exit codes preserved**; no `|| true`; waiters on pid or rc file (never `pgrep -f` of the runner's own argv).

## 4. `/tmp` escape diagnostic

**Candidates (diagnostic, complete for the recorded interface) [P2].** `pg.tmp_escapes(export, env)` reads the
export's `content[].type == "tool"` parts: `name in (write, edit)` → `state.input.path`; `name == "shell"` →
`shlex.split(state.input.command)` best-effort (on `ValueError` the raw text is scanned and every match is marked
`ambiguous`), each token that starts with `/tmp/` or `/private/tmp/` after normalising the prefix to `/tmp/`;
`read` parts are ignored. Tokens containing a `..` component or any `.`/empty component are rejected as
`traversal`. Everything under the item's own `TMPDIR` or scratch is dropped. Row field `tmp_escapes`:
`[{path, source: write|edit|shell, ambiguous: bool}]`. Fixtures are taken from a recorded 2.0.20 export shape
(`path`, `{command, workdir}`); `filePath` is not an alias on this client and is not parsed.

**Deletion authority (separate from diagnostics) [P1].** Before the client is spawned the probe lists the top-level
entries of `/tmp` (name, inode, device; a read-only `os.scandir`, nothing opened, nothing removed) and after the
item ends lists them again. A candidate is removed only if ALL hold: it is a `write`/`edit` path or an unambiguous
shell token; its first path component under `/tmp` is absent from the before-listing and present in the
after-listing (created during the item); walking from `/tmp` component by component with `os.open(O_NOFOLLOW |
O_DIRECTORY, dir_fd=…)` reaches it without any symlink component (a symlink anywhere → `symlink`, not removed);
`fstat` on the opened object shows our uid, `st_birthtime` inside the item window and the inode/device recorded in
the after-listing (changed → `replaced`, not removed); a regular file is unlinked via `dir_fd`; a directory is
removed only when every entry under it, walked the same way, satisfies the same checks. Row fields `tmp_cleaned`
and `tmp_not_removed: [[path, reason]]` with reasons `missing`, `pre_existing`, `symlink`, `not_owned`,
`outside_window`, `replaced`, `traversal`, `ambiguous`, `dir_mixed`, `not_regular`. Nothing else under `/tmp` is
read or removed. Residual, stated: a file another process creates under `/tmp` during the item with exactly a name
the model also wrote would be removed; the before/after listing plus our-uid plus birth-window makes that a
same-user same-name same-window collision. Tests run on a real filesystem under `tmp_path` with the `/tmp` root
injectable (`TMP_ROOT`), covering every reason above, a symlinked parent, a replaced inode and a pre-existing name.
The probe prints one `tmp_escapes=` line per item for the RUNLOG. V4 reference: `go/alphametics` s2 wrote
`/tmp/bench199_test.go`.

## 5. Grader-report retention [P12]

`structured_grade.grade(..., keep=<dir>, seq=<n>)`: BEFORE parsing, and on every early return (timeout, container
OOM, grader memory kill, missing interpreter), every raw artifact that exists is copied to
`<keep>/<boundary>.<seq>.<name>`: Python `report.xml`, `stdout.txt`, `stderr.txt`; Go `go.jsonl`, `go.stderr`.
`Grade` gains `artifacts: {name: {path, sha256}}` and `outcome ∈ {parsed, timeout, oom, mem_kill, missing_report,
infrastructure}`. `tg1_runner` passes `keep = <evidence>.grades/` (immutable per run_id; an existing directory
refuses) and a monotonically increasing `seq` shared by snapshot grades and the final grade. New row field
`grade_reports: [{boundary, seq, final: bool, outcome, artifacts}]`; `failing_trajectory` keeps its shape and the
gate outcome is computed exactly as before (replay and the V2 manifest are untouched; `m62/replay.py` stays 8/8).
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
- **V2 composed [P13].** (a) Real `run_item` + pinned client (`OPENCODE_PROBE_BIN`) + mock provider: the
  cancel file produces export, reconciliation (`runner_cancel`), retained artifacts and no row; the terminal
  evidence shas are in the manifest. (b) `tg_fixture` with `--tg1-inject stall` over fixture events → a labelled
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
