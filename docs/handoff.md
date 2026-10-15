# Handoff — 2026-10-15: P299 done (audit acceptance no longer gated on the installed auditor CLI); box idle; next: C157 guard fix → P288 flaky tests → C144 candidates + M64 Pi scaffold arm

THE one handoff. Read this, then `docs/open-questions.md` (top entries: C163, C162, C161, C160, C159, P299, C158, P288, C157),
`docs/campaign-results.md` (2026-10-13 P223, 2026-10-14 M63), `docs/PLAN.md` (M62, M63, M64 rows), `README.md` B ladder.

## State of the world

- **Two boxes, both idle, no router, :8000 free.** `m5max` (64 GB, this session's box: codex CLI present, no
  cursor-agent) and `m5max-128` (128 GB, the P223/M63 chain box: cursor-agent present, no codex). Quality rows pair
  across them (C153); latency/thermal/capacity rows never do. The P201 web auditor is whichever declared CLI the box
  has (`benchmark/web_audit.py` codex `gpt-6-astra`, `benchmark/web_audit_cursor.py` Cursor `gpt-5.6-sol-high`); the
  cold reviewer likewise (codex: `codex exec --ephemeral --ignore-user-config -m gpt-6-astra -s read-only
  --skip-git-repo-check -o <out> - < <prompt>` with a writable `TMPDIR` under `$STACK_WORKDIR` — its read-only sandbox
  cannot run pytest, so give it the author's test results; Cursor: `cursor-agent -p --output-format text --model
  gpt-5.6-sol-high --mode plan --sandbox enabled --force --trust --workspace <repo>`, re-run once on empty output).
- **P299 done 2026-10-15 (this session, no box work):** scoring never probes an auditor CLI; a recorded audit is valid
  by (declared auditor, recorded version, prompt sha, evidence identity); a CLI update neither re-audits nor
  invalidates; `P223_REPORT.md`/`M63_REPORT.md` regenerate byte-identical on a box with no auditor CLI. Probe identity:
  `answer_key.py` and `web_audit.py` are in the tg1 probe code identity, so `run_opencode_probe_v2.py
  --print-identity` gives a NEW `probe_code_sha256` — new rows never pair with P223/M63 rows (C144 already requires
  fresh OFF rows for every comparison).
- **Identities (unchanged since 2026-10-14):** serving `src/mlx-serve` at the operator's `86921f0`; opencode
  `$STACK_WORKDIR/opencode-2.0.20` (sha-pinned); dsh adapter frozen at `0.1.2-rc.1` (C117).
- **Records (final, committed, pushed):** P223 tg1 OFF (`benchmark/results/p223_tg1/P223_REPORT.md`):
  `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` 84/86 strict, `Qwen3.8-27B-mlx-uniform-4bit` 83/86; M63 MTP-ON
  (`benchmark/results/m63_mtp/M63_REPORT.md`): 85/86 and 84/86, both keep shipping MTP ON (C71). README B ladder
  current; pick/order changes need the operator.
- **Rulings this week:** C159 Pi coding agent queued as PLAN M64 (scaffold arm of the C144 chain); C160 opencode
  silent-model-switch and telemetry checks closed by construction + observation; C161 (standalone dsh eval?) OPEN,
  lead says no; C162 `NVIDIA-Nemotron-3.5-Bolt-74B-A9B` DROPPED by the operator; C163 (audit identity omits
  url/command/status, inherited) OPEN, needs a go.
- **Parked branches:** `p297-uncertain-gone` (superseded by C157), `c152-alloc-tool-scope-wip`.

## Next work, in order (each: proposal to the operator if not yet approved → test-first → cold review → full suite)

1. **C157 — probe guard: a vanished unreadable process is not "uncertain"** (cause of the M63 s2 abort and of
   P288's worst flake). In `benchmark/bench/proc_guard.py` `cleanup()`: when a same-uid process's start order
   cannot be read, re-check existence with the guard's own tracking state — a process that no longer exists and
   left no tracked or attributable descendant is not uncertain; one that still exists stays uncertain (C151 R10).
   Also move the process-monitor failure check before the uncertainty raise (P297 review U2). Fixture:
   `benchmark/bench/tests/fixtures/p297_real_uncertain_vanished_manifest.json`. Why the runner-side version failed:
   `p297-uncertain-gone` branch, `benchmark/chains/c147/reviews/p297/round1.cursor-gpt-5.6-sol-high.md` (U1, U2).
   Box-free.
2. **P288 — make the four load-sensitive tests deterministic** (list in open-questions P288; needs operator go).
   Box-free. (This session: `test_m61_p201::test_real_code_search_denied[webfetch-api.github.com/search/code]`
   failed once inside the targeted audit-test run and passed alone — same class.)
3. **C144 — new candidates under tg1 + M64 Pi scaffold arm (C159).** Box-free first: `run_pi_probe.py` on the
   dsh/v2 adapter pattern (print/JSON mode, provider pinned to :8000, npm version + exe sha in the row identity,
   bench-owned HOME/config dir, extensions absent by wire capture, M50 entry/exit, M62 token-turn gate from Pi's JSON
   events, `lsof -i` socket sampling in the smoke per C160), cold review, then **GPU work (operator-run):** a
   `--smoke` chain, fresh OFF rows for both picks on the new probe identity, then the Pi arm on the same items, seeds
   and budgets; pre-registered PASS = strict TOST ±5pp per pick AND lower tokens/task. C161 (updated 2026-10-15): no subjective-quality signal exists for dsh and none is
   recoverable (artifacts gone); proposed M64 subjective axis = blind pairwise code-quality panel over both-pass items;
   operator to say whether dsh is an M64 arm from the start. `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` stays shipped (operator 2026-10-15).
4. **C163 — audit identity digest** (small, box-free, needs a go).
5. **Docs:** per-box P201 auditor (codex vs Cursor) in `benchmark/README.md` and `scripts/bootstrap_machine.sh`
   notes (C158 owed; the README audit paragraph now names both auditors).

## Rules learned (2026-10-11 → 15)

- Never edit runner/probe/scoring files in the main checkout while a chain runs (`chain.json` re-hashes runner files;
  probe-identity files abort the next leg) — build in `$STACK_WORKDIR/worktrees/`, merge after. Never run the full
  suite under a live chain (real-client tests spawn opencode).
- Launch chains with a command line that names no watched process (the busy-process gate refused its own launcher).
- After a reboot: `docker info` before any Go leg (P290 gate enforces it).
- A cold-review prompt names the commit hash, never HEAD (for uncommitted work: the diff file + "working tree").
- opencode 2.0.20 cuts a single request at 60 min without a durable event (C154); tokenize the trailing reasoning
  to tell a loop from genuine thinking.
- Scoring accepts a recorded audit from a declared auditor whatever CLI version is installed now (P299); a changed
  prompt sha still invalidates.
- A review finding that is an inherited bug gets its own open question (C163), not a scope expansion.
- Pushes need explicit operator approval each time.

Next decision id C164; discussion ids continue from P303.
