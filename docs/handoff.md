# Handoff — 2026-10-10 (night, final): C147 built and pushed; next is the operator's live V3 injected run, then the chain pilot, then P223

THE one handoff. Read this, then `docs/open-questions.md` C147, `docs/specs/c147-tg1-chain-clearance.md` (rev 3 + §9
build findings), `benchmark/chains/c147/README.md`, `docs/PLAN.md` (M62 row) and `benchmark/chains/README.md`.

## State of the world

- **Forks synced 2026-10-10 (pushed).** mlx-serve `3cb9351` = upstream v0.2.0 merged (`extra_body` adapted beside
  `generation_defaults`; permanent `upstream` remote). mlx-vlm `24551869` = upstream `952d4f6b` (28 commits past
  v0.7.6; AGENTS.md there scrubbed and re-baselined). Stack `8f2d1085` bumped both submodules; `uv lock` moved
  `mlx` 0.32.2 → 0.32.3 (forced by upstream mlx-vlm), which is in the serving-path hash: rows recorded after the
  bump do not pair with earlier rows. Known, not fixed: the mlx-serve fork's golden registry test fails against
  this stack's live `main_models.yaml` (fixture predates `mtp_verify_scan joint_v1`); refresh owed in the fork.
- **C147 BUILT and pushed (`df601223` + this handoff), nothing live yet.** Spec rev 3 + §9 (B1–B8). Two Codex `gpt-6.1-sol` design
  reviews (both "redesign"; every id answered), then post-build reviews: round 1 "not cleared" Q1–Q11 (fixed,
  `84d6e5a8`), round 2 "not cleared" Q12–Q18 (fixed, `20e41354`; two lead decisions recorded in §9 B8: write-only
  `/tmp` deletion with content match; `cancellation_consistent` accepted, worker-side receipt proposed as C149),
  round 3 "not cleared" Q19–Q25 (fixed, `6bb4cefe`; §9 B9), round 4 "not cleared" Q26–Q28 (three boundary
  cases the reviewer judged not to invalidate a live positive run; fixed in the final commit; §9 B10). Lead
  decision: the review loop stops here — the operator's live V3 run and the chain pilot are the clearance. All
  four rounds are under `$STACK_WORKDIR/c147/codex_impl_review{1..4}.md`. Code: `--tg1-inject {stall,loop,alloc}` (probe), `--cancel-file`, `--manifest-ack`,
  `--sampling-profile deployed`, `--print-identity`; `benchmark/m62/inject_verify.py`,
  `benchmark/m62/tmp_escape_clean.py`; `benchmark/bench/chain_ops.py`; `benchmark/chains/c147/{run_tg1_chain.py,
  run_inject.py, drive_chain.sh, drive_inject.sh, fake_probe.py}`; `scripts/session_pinning_gate.py --scaffold
  opencode-v2-web-tg1`; `structured_grade.validate_reports`. Whole `benchmark/bench/tests/` from `benchmark/`:
  4367 passed, 2 skipped, 1 xfailed (`env -u STACK_WORKDIR`, `OPENCODE_PROBE_BIN` set for the real-client tests).
- **Build finding B1 — the M62 live stop path had never reconciled** (SIGKILL before the client persisted the
  in-flight message; 8/8 real-client failures). Fixed: SIGTERM-first `graceful_stop`, two named transport errors
  tolerated for our own stops only, aborted trailing message with usage charged (`interrupted_charged`). V3/V4
  rows are unaffected (no stop ever fired in them). The campaign `scaffold_policy_sha256` is pinned unchanged.
- **Workdir inputs rebuilt:** `$STACK_WORKDIR/{polyglot-benchmark (7e0611e), nltk_data, opencode-2.0.20, c147/}`.
  Evidence branch not restored (optional). Daily driver NOT started; stack stopped.

## Queue, in order

1. **C147 V3 — live injected positives (operator, ≈30 min, box quiet, 140 W/28 V, battery > 20 %):**
   `nohup benchmark/chains/c147/drive_inject.sh &` → `$STACK_WORKDIR/m62/inject/{inject.out,inject.rc,RUNLOG.md}`;
   the driver re-runs a non-PASS kind on seeds 2002/3003 and ends with the suite verdict of
   `benchmark/m62/inject_verify.py --run $STACK_WORKDIR/m62/inject`. Required PASS for all three kinds, the retained
   `loop` row showing `in_flight_at_kill ≥ 1`. Record the outcome in open-questions C147 and campaign-results.
2. **Chain pilot:** `benchmark/run_opencode_probe_v2.py --print-identity` → `probe_code_sha256`; then
   `nohup benchmark/chains/c147/drive_chain.sh pilot &` (5 items, pick 1, `$STACK_WORKDIR/c147/pilot/`). The pilot
   is the composed real test of the runner (M50 forbids a subprocess probe in tests).
3. **P223 chains:** `nohup benchmark/chains/c147/drive_chain.sh chain s1 s2 reload --probe-code-sha <sha> &`
   (≈20 h + pilots + 10-min arm idles). Stop cleanly with `touch $STACK_WORKDIR/c147/STOP` (exit 3). Watch
   `RUNLOG.md` every 5 min (`WATCH`, `ALARM`, `CORRECTION?`). Never pool tg1 with the M61 `opencode-v2-web` rows.
4. Then C144 candidates under tg1; README/ranking updates need the operator.

Ordering is deliberate (P245–P248): do not skip the pilot to save time — it is the only step that runs
`chain_ops` against a real router (everything else was mocked or `fake_probe.py`); a teardown bug 10 h into
a 20 h chain costs far more than the pilot. If any inject leg exits 1 or 4, stop and treat it as a gate bug,
not a model finding; hand the run dir to the next session.

## Work a session can do while the box is busy (no serving impact)

- mlx-serve fork golden fixture refresh (fork-only; fixture predates `mtp_verify_scan joint_v1`).
- C149 spec (worker-side `requests_cancelled` receipt) once the operator decides yes/no; the current
  `cancellation_consistent` acceptance is a stopgap.
- Never start the daily driver; never touch :8000 while a chain runs.

## Rules learned (2026-10-10, this session)

- SIGKILL on opencode 2.0.20 loses the in-flight assistant message; SIGTERM makes it persist an `aborted` one.
  Stop the client with SIGTERM first, always.
- On 2.0.20 the write/edit tool input is `path` (not `filePath`); shell is `{command, workdir[, timeout, background]}`;
  a SIGKILLed shell call exports as `completed` + `metadata.signal`.
- Lowering a per-process memory limit below ≈ 400 MiB kills opencode's own server child (a client descendant).
- Codex: `-m gpt-6.1-sol` is the account default now; `benchmark/chains/c147/run_codex.sh <name> ro|write [model]`.
- Fork syncs: mlx-vlm's AGENTS.md audit procedure works; bump `UPSTREAM_SYNC_REF` in the merge commit; re-pin
  fork-owned test blobs in `.fork-marker-allowlist`; `uv lock` from upstream's lock after resolving.

Next decision id C150 (C149 open, awaiting operator); discussion ids continue from P249.
