# Handoff — 2026-10-14: P223 (OFF) + M63 (MTP-ON) complete and written up; C158 done; box idle; next: C157 guard fix → P288 flaky tests → C144 candidates

THE one handoff. Read this, then `docs/open-questions.md` (top entries: C158, P298, P288, C157, C156, C155, C154),
`docs/campaign-results.md` (2026-10-13 P223, 2026-10-14 M63), `docs/PLAN.md` (M62, M63 rows), `README.md` B ladder.

## State of the world

- **Box `m5max-128`, idle**: no router, no chain, :8000 free. Docker (OrbStack, start-at-login ON) 29.4.0.
  No codex CLI (cannot be installed); the P201 web auditor here is Cursor `gpt-5.6-sol-high`
  (`benchmark/web_audit_cursor.py`, C158). `cursor-agent` is also the cold reviewer
  (`cursor-agent -p --output-format text --model gpt-5.6-sol-high --mode plan --sandbox enabled --force --trust
  --workspace <repo>`; it sometimes returns empty output — re-run once).
- **Identities moved (2026-10-14), so new rows never pair with P223/M63 rows:**
  serving — `src/mlx-serve` at the operator's `86921f0` (editable install, live);
  probe — C158 changed `answer_key.py`, `web_audit.py` and added `web_audit_cursor.py` to the tg1 code identity
  (`run_opencode_probe_v2.py --print-identity` gives the new `probe_code_sha256`).
- **Records (final, committed, pushed):**
  - P223 tg1 OFF (`benchmark/results/p223_tg1/P223_REPORT.md`): `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`
    84/86 strict, `Qwen3.8-27B-mlx-uniform-4bit` 83/86; B order holds; 2 `client_inactivity` rows each, counted
    as recorded (P293 ruled 2026-10-14).
  - M63 MTP-ON (`benchmark/results/m63_mtp/M63_REPORT.md`): 85/86 and 84/86; no OFF advantage beyond ±5 pp →
    both keep shipping MTP ON (C71); 1.4–2.35× faster; all four OFF 60-min cuts converge ON.
  - README B-ladder evidence updated (ranks unchanged; pick/order changes need the operator).
- **Parked branches:** `p297-uncertain-gone` (runner-side workaround, not cleared — superseded by C157),
  `c152-alloc-tool-scope-wip`.

## Next work, in order (each: proposal to the operator if not yet approved → test-first → cold review → full suite)

0. **P299 — tool versions churn daily (operator 2026-10-14):** stop gating audit acceptance on the auditor CLI's
   CURRENTLY installed version (`answer_key.declared_auditors`/`accepted_audits` + `audit_states`); a recorded audit
   stays valid by (auditor, recorded version, prompt sha, evidence). Otherwise any Cursor update silently returns the
   P223 s1 Python cells to provisional. Same principle for scaffold tools: keep the per-chain sha pin, treat each
   release as a planned identity boundary with a cheap re-baseline. Ask the operator what "dsh" refers to.
1. **C157 — probe guard: a vanished unreadable process is not "uncertain"** (cause of the M63 s2 abort and of
   P288's worst flake). In `benchmark/bench/proc_guard.py` `cleanup()`: when a same-uid process's start order
   cannot be read, re-check existence with the guard's own tracking state — a process that no longer exists and
   left no tracked or attributable descendant is not uncertain; one that still exists stays uncertain (C151 R10).
   Also move the process-monitor failure check before the uncertainty raise (P297 review U2: a monitor failure is
   currently hidden behind it). Fixture: `benchmark/bench/tests/fixtures/p297_real_uncertain_vanished_manifest.json`.
   Review record of why the runner-side version failed: `p297-uncertain-gone` branch,
   `benchmark/chains/c147/reviews/p297/round1.cursor-gpt-5.6-sol-high.md` (U1 reparented descendants, U2).
2. **P288 — make the four load-sensitive tests deterministic** (list in open-questions P288; needs operator go).
3. **C144 — new candidates under tg1** (new probe + serving identity: fresh OFF rows for every comparison, including
   re-recording the two picks if they are to be compared against). Run a `--smoke` chain first.
4. **Docs:** per-box P201 auditor (codex vs Cursor) in `benchmark/README.md` and `scripts/bootstrap_machine.sh`
   notes (C158 owed).

## Rules learned (2026-10-11 → 14)

- Never edit runner/probe/scoring files in the main checkout while a chain runs (`chain.json` re-hashes runner files;
  probe-identity files abort the next leg) — build in `$STACK_WORKDIR/worktrees/`, merge after. Never run the full
  suite under a live chain (real-client tests spawn opencode).
- Launch chains with a command line that names no watched process (the busy-process gate refused its own launcher).
- After a reboot: `docker info` before any Go leg (P290 gate enforces it).
- A cold-review prompt names the commit hash, never HEAD.
- opencode 2.0.20 cuts a single request at 60 min without a durable event (C154); tokenize the trailing reasoning
  to tell a loop from genuine thinking.
- Scoring accepts an audit only from a declared auditor with a current installed version (C158).
- Pushes need explicit operator approval each time.

Next decision id C159; discussion ids continue from P299.
