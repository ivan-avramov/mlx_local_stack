# Handoff — 2026-10-15: P299 (1) and C157 done and cold-reviewed; box idle; next: P288 (ask) → C144 candidates (ask) → docs

THE one handoff. Read this, then `docs/open-questions.md` (top entries: P299 part 2, P288, C156, C155, C154),
`docs/campaign-results.md` (2026-10-13 P223, 2026-10-14 M63), `docs/PLAN.md` (M62, M63 rows), `README.md` B ladder.

## State of the world

- **Box `m5max-128`, idle**: no router, no chain, :8000 free. Docker (OrbStack, start-at-login ON). No codex CLI
  (cannot be installed); the P201 web auditor here is Cursor `gpt-5.6-sol-high` (`benchmark/web_audit_cursor.py`).
  `cursor-agent` is also the cold reviewer (`cursor-agent -p --output-format text --model gpt-5.6-sol-high --mode plan
  --sandbox enabled --force --trust --workspace <repo> "<prompt>"`); it sometimes returns an empty or one-newline
  output — re-run (loop until the report contains "Verdict").
- **Identities moved again (2026-10-15), so new rows never pair with P223/M63 rows:** probe — P299 changed
  `answer_key.py`/`web_audit.py`, C157 changed `proc_guard.py`; `run_opencode_probe_v2.py --print-identity` →
  `probe_code_sha256` `d3be5737…` (serving unchanged since 2026-10-14: `src/mlx-serve` at `86921f0`).
- **Records (final, committed; the unpushed commits are listed below):**
  - P223 tg1 OFF (`benchmark/results/p223_tg1/P223_REPORT.md`) and M63 MTP-ON (`benchmark/results/m63_mtp/M63_REPORT.md`)
    unchanged; both regenerate byte-identical after P299 (reviewer reproduced it too).
  - **P299 (1) DONE** (`06a77fec`, `da269033`): an audit is valid by (declared auditor, prompt sha, evidence identity);
    the recorded `auditor_version` is provenance and the installed CLI version never gates scoring or re-auditing;
    `--retry-errors` retries only unresolved `audit_error`; an unreadable version raises `AuditorVersionError` before
    appending; resolutions must match the base record's version. Cold review: cleared after doc fixes.
  - **C157 DONE** (`b5b4cd53`…`21066227`): see open-questions C157. Five review rounds; the guard is best-effort and
    the residuals are documented there.
  - P299 part 2 stays as policy: scaffold tools (opencode `$STACK_WORKDIR/opencode-2.0.20`, dsh `0.1.2-rc.1`) are
    sha-pinned per chain; each release is a planned identity boundary with a cheap re-baseline (smoke chain, C154 re-check).
- **Parked branches:** `p297-uncertain-gone` (superseded by C157; delete when convenient), `c152-alloc-tool-scope-wip`.
- **Not pushed:** everything from `06a77fec` onward (push needs explicit operator approval).

## Next work, in order

1. **P288 — make the four load-sensitive tests deterministic** (open-questions P288; **ask the operator first**; the
   cancel-race member looks fixed by C157 — six clean full suites).
2. **C144 — new candidates under tg1** (new probe + serving identity: fresh OFF rows for every comparison, including
   re-recording the two picks if they are to be compared against). Run a `--smoke` chain first. **Ask before starting any chain.**
3. **Docs owed:** per-box P201 auditor (codex vs Cursor) note in `scripts/bootstrap_machine.sh` (the benchmark README
   already states it; no codex install in bootstrap).
4. Delete the parked `p297-uncertain-gone` branch (operator OK).

## Rules learned (2026-10-11 → 15)

- Never edit runner/probe/scoring files in the main checkout while a chain runs (`chain.json` re-hashes runner files;
  probe-identity files abort the next leg) — build in `$STACK_WORKDIR/worktrees/`, merge after. Never run the full
  suite under a live chain (real-client tests spawn opencode).
- Run the suite from `benchmark/` as `../.venv-bench/bin/python -m pytest bench/tests -q` (~11 min); never from the repo root.
- Launch chains with a command line that names no watched process (the busy-process gate refused its own launcher).
- After a reboot: `docker info` before any Go leg (P290 gate enforces it).
- A cold-review prompt names the commit hash, never HEAD; give the reviewer the code and earlier rounds' text, not the conclusion.
- Scoring accepts an audit from a declared auditor by its RECORDED version, prompt sha and evidence; the installed CLI
  version is provenance only (C158, P299).
- Test the guard's cleanup scan with `kill_role` stubbed: `kill_role()` runs `tick()` first and consumes a scripted vanish.
- opencode 2.0.20 cuts a single request at 60 min without a durable event (C154); tokenize the trailing reasoning
  to tell a loop from genuine thinking.
- Pushes need explicit operator approval each time.

Next decision id C159; discussion ids continue from P305 (P300–P305 were used this session in chat).
