# Handoff — 2026-10-15 (sync): both boxes' work merged; picks re-record chain LIVE on m5max-128 (pre-merge identity); C164 ruled; next: M64 spec, then post-chain verification + P311

THE one handoff. Read this, then `docs/open-questions.md` (top entries: C163, C162, C161, C160, C159, P299, P308,
P288, P306, C157), `docs/campaign-results.md` (2026-10-13 P223, 2026-10-14 M63), `docs/PLAN.md` (M62–M64 rows),
`README.md` B ladder.

## State of the world

- **Two boxes.** `m5max` (64 GB: codex CLI, no cursor-agent) and `m5max-128` (128 GB, the chain box: cursor-agent, no
  codex). Quality rows pair across them (C153); latency/thermal/capacity rows never do. The P201 web auditor is
  whichever declared CLI the box has (`benchmark/web_audit.py` codex `gpt-6-astra`, `benchmark/web_audit_cursor.py`
  Cursor `gpt-5.6-sol-high`; `scripts/bootstrap_machine.sh` reports which). Cold reviewer likewise — codex:
  `codex exec --ephemeral --ignore-user-config -m gpt-6-astra -s read-only --skip-git-repo-check -o <out> - < <prompt>`
  (writable `TMPDIR` under `$STACK_WORKDIR`; it cannot run pytest, give it the author's results); Cursor:
  `cursor-agent -p --output-format text --model gpt-5.6-sol-high --mode plan --sandbox enabled --force --trust
  --workspace <repo> "<prompt>"` (empty or one-newline output happens: re-run until the report contains "Verdict").
- **Sync 2026-10-15 (m5max-128):** branch `sync-upstream-1015` (worktree `$STACK_WORKDIR/worktrees/sync-1015`) merges
  `origin/main` (m5max: P299, C159–C163, M64 queued) into this box's `main` (C157, P306, P288/P308, smoke, bootstrap
  note). Audit code resolved to m5max's reviewed P299 + C163 version; this box's parallel P299 build is superseded
  (merge note in open-questions P299), its two extra review fixes ported as P309 (`f76eaa4b` + `041ec610`, Cursor "cleared after fixes P1–P4"). Merged-tree probe identity `ebcfe6fb…`; targeted audit/guard/runner tests green (full suite owed after the chain), P223/M63 reports regenerate unchanged. The main checkout stays on the
  pre-merge `main` until the live chain exits (probe-identity files differ). Forks: `../mlx-serve` fast-forwarded to
  `86921f0` (= the stack's pin); `../mlx-vlm` current; submodule pins unchanged.
- **LIVE (m5max-128, since 2026-10-15 16:09Z): picks re-record chain** `chain s1 s2 reload --probe-code-sha
  d4319705…`, out-root `$STACK_WORKDIR/c144-base` (`driver.chain.out`/`.rc`, `RUNLOG.md`), ≈18 h. Launched via a
  scratch launcher (`run_tg1_chain.py ... --out-root`, `$HOME/.orbstack/bin` on PATH — the agent shell has no docker
  on PATH; `drive_chain.sh` would overwrite P223's `c147/chain.out`). Identity `d4319705…` = C157 + P306 + this box's
  P299, WITHOUT C163/m5max-P299: rows on it never pair with rows on the merged identity (P310 open). Do not edit
  runner/probe/scoring files in the main checkout or run the full suite until it exits.
- **Smoke chain PASSED** (2026-10-15 14:33Z → 15:48Z, `$STACK_WORKDIR/c144-smoke`, probe `d4319705…`): 9/9 rows
  passed + converged, 0 `client_inactivity`, no uncertain cleanup. Rehearsal evidence only.
- **Done this week:** P299 (audit acceptance by recorded version), C163 (audit identity carries `context_sha256`;
  legacy records counted as `legacy_audits`), C157 (guard: vanished unreadable processes; five Cursor rounds), P306
  (tick prunes dead roots), P288 (repro harness; three real-client members do not reproduce) + P308 (runner: STOP
  before the first manifest is a STOP, not a barrier abort), bootstrap auditor note. Rulings: C159 Pi = M64 arm, C160
  closed, C161 dsh = third M64 arm + two-judge subjective mean on every comparison (AGENTS.md), C162 dropped.
- **Records (final):** P223 tg1 OFF (`benchmark/results/p223_tg1/P223_REPORT.md`) 84/86 vs 83/86; M63 MTP-ON
  (`benchmark/results/m63_mtp/M63_REPORT.md`) 85/86 and 84/86, both ship MTP ON. README B ladder current.
- **Operator direction 2026-10-15 (m5max-128 session):** keep working and keep the GPU busy with the planned run
  (fresh OFF rows of both picks); merge to main as work completes; do not delete branches yet. The m5max session
  recorded "GPU deferred, operator launches chains" earlier the same day — superseded for this box by the above.
- **Parked branches (keep):** `p297-uncertain-gone`, `c152-alloc-tool-scope-wip`.
- **Not pushed:** this box's `main` (16 commits) and `sync-upstream-1015`. Push needs explicit operator approval.

## Next work, in order (C164, operator 2026-10-16: all recommendations taken)

1. **Live chain runs to completion** (C164/P310: its rows are the M64 opencode baseline despite the pre-merge identity).
2. **M64 spec** (C164/P313, now, docs only): `docs/specs/m64-scaffold-arms.md` → Cursor cold review → operator go → build.
3. **After the chain exits** (C164/P312): fast-forward `main` to `origin/main`, full suite (owed for the pushed merge),
   P223/M63 reports unchanged, c144-base report + README evidence (list web-fetch rows per C164), push on approval.
4. **P311 identity split** (C164, approved): proposal + test-first + cold review in a worktree; merge after the chain.
5. **M64 build** after its go; then its smoke = the next GPU job. No filler chains (C164/P314).

## Rules learned (2026-10-11 → 15)

- Never edit runner/probe/scoring files in the main checkout while a chain runs (`chain.json` re-hashes runner files;
  probe-identity files abort the next leg) — build in `$STACK_WORKDIR/worktrees/`, merge after. Never run the full
  suite under a live chain (real-client tests spawn opencode). Run it from `benchmark/` as
  `../.venv-bench/bin/python -m pytest bench/tests -q` (~11 min).
- Fetch and diff before syncing during a live chain; merge in a worktree.
- Launch chains with a command line that names no watched process (the busy-process gate refused its own launcher).
- After a reboot: `docker info` before any Go leg (P290 gate enforces it).
- A cold-review prompt names the commit hash, never HEAD; give the reviewer the code and earlier rounds, not the conclusion.
- Scoring accepts a recorded audit from a declared auditor whatever CLI version is installed now (P299); a changed
  prompt sha still invalidates.
- Test the guard's cleanup scan with `kill_role` stubbed: `kill_role()` runs `tick()` first and consumes a scripted vanish.
- A review finding that is an inherited bug gets its own open question (C163), not a scope expansion.
- opencode 2.0.20 cuts a single request at 60 min without a durable event (C154).
- Pushes need explicit operator approval each time.

Next decision id C164; discussion ids continue from P310 (P300–P305 were also chat labels on m5max-128; the docs
entries P306/P308/P309 are unique).
