# Handoff — 2026-10-14: P223 (OFF) and M63 (MTP-ON) tg1 chains COMPLETE and written up; C158 cold review in progress; box idle

THE one handoff. Read this, then `docs/open-questions.md` (C154–C158 at the top), `docs/campaign-results.md`
(2026-10-13 P223, 2026-10-14 M63), `docs/specs/m63-mtp-on-tg1-arm.md`, `docs/PLAN.md` (M62, M63 rows).

## State of the world

- **Box `m5max-128`, idle.** No router, no chain. Docker (OrbStack, start-at-login ON) 29.4.0. No codex CLI (cannot
  be installed); the P201 web auditor here is Cursor `gpt-5.6-sol-high` (C158, `benchmark/web_audit_cursor.py`).
- **Serving identity changed 2026-10-14:** `src/mlx-serve` synced to the operator's pushed `86921f0` ("reap a worker
  that exits after READY"; editable install, live). Rows recorded from now on do not pair with P223/M63 rows.
- **Probe identity changed** (C158 added `web_audit_cursor.py` to it and changed `answer_key.py`): the next chain gets a
  new `probe_code_sha256`. P223 and M63 rows all carry `8d1b4c84…` and pair with each other.
- **P223 (OFF) record:** pick 1 `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` 84/86 strict, pick 2
  `Qwen3.8-27B-mlx-uniform-4bit` 83/86; order holds. Report `benchmark/results/p223_tg1/P223_REPORT.md` (final).
- **M63 (MTP ON) certified on the agentic axis:** pick 1 85/86, pick 2 84/86; every paired ON−OFF cell equivalent or
  inconclusive, no OFF advantage beyond ±5 pp → both keep shipping ON (C71); 1.4–2.35× faster. All four OFF 60-min
  `client_inactivity` cuts converged ON (P293 answered). Report `benchmark/results/m63_mtp/M63_REPORT.md`.
- **README B ladder evidence updated** (ranks unchanged; changes to picks/order need the operator).
- Branches parked: `p297-uncertain-gone` (not cleared; see C157), `c152-alloc-tool-scope-wip`.

## Queue, in order

1. **C158 cold review** (Cursor `gpt-5.6-sol-high`, `benchmark/chains/c147/reviews/c158/`) of the declared-auditor
   scoring change; fix findings, re-run the full suite, regenerate both reports if scoring changes.
2. **P293 decision (operator, after M63 — now due):** how OFF `client_inactivity` rows count. Evidence: all four
   converge ON; strict ranking unaffected either way. Options in C154/P293.
3. **C157 probe guard fix** (vanished unreadable process ≠ uncertain; monitor-failure check before the uncertainty
   raise) — next probe-identity change, i.e. now is fine; test-first + cold review.
4. **C144 candidates under tg1** (new probe + serving identity; fresh OFF rows for any comparison).
5. Bootstrap/README: document the per-box P201 auditor (C158).

## Rules learned (this session)

- Build in a worktree under `$STACK_WORKDIR/worktrees/` while a chain runs; never edit runner/probe files under a
  live chain; never run the full suite under a live chain.
- Launch chains from a shell whose command line names no watched process (busy-process gate refuses its own launcher).
- A review prompt must name the commit, not HEAD, once the prompt itself is committed.
- opencode 2.0.20: 60-min single-request inactivity cut (C154); long thinks can be loops or genuine — tokenize.
- `answer_key` needs a current auditor CLI version to accept any audit; boxes without codex use Cursor (C158).
- Pushes need explicit operator approval each time.

Next decision id C159; discussion ids continue from P298.
