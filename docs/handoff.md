# Handoff — 2026-10-06 (late): C121 seeded opencode BUILT+MERGED; M58 BUILT (3 branches, reviewed to closure, live smoke + gate 1 owed); C116/C117/C122/C123 ruled; stack UP (daily driver), nothing pushed

THE one handoff (AGENTS.md: rewritten in place each session). Read this, then `docs/PLAN.md` (M58, M59 rows) and
`docs/open-questions.md` (C116–C125). Earlier narrative of this same day (M57 start verification, STEP 1 result): `git show dbc546c:docs/handoff.md`.

## State of the world

- Stack `main` = `28bb7ed`+ (local only; `origin/main` is still `d92c741` — NOTHING PUSHED this session; push needs the operator's go).
- Forks: `../mlx-vlm` branch `m58-joint-verify` @ 664c2ead and `../mlx-serve` branch `m58-joint-verify` @ 3f2c87c — NOT merged, NOT
  pushed, submodules NOT bumped, registry unchanged. Stack branch `m58-provenance` @ e4d3652 lives in worktree `.claude/worktrees/m58`
  (fingerprint v8, compare tools, parity_replay AC11, row persistence) — NOT merged into main (merge together with the submodule bump).
- Worktree `.claude/worktrees/c121` (merged; can be removed). Two stale agent worktrees under `.claude/worktrees/agent-*` can be removed.
- Daily driver is UP (operator started it; verified under M57, see `dbc546c` handoff). The box also runs opencode v2.0.20 (brew); the
  bench pins 1.18.30 at `$STACK_WORKDIR/opencode-1.18.30/` (C123). `~/.config/opencode/service.json` was created by a v2 probe (harmless).

## Done this session (chronological)

1. Harness gaps (`64bea61`): portable manifest paths, C116 provenance preflight + no publish on failed gather, `sdpa` on capacity rows,
   content/reasoning digests on generate rows. dsh runner FROZEN (C117).
2. ReviewBench DEFERRED (C122) — reasons at the top of `docs/proposal-reviewbench.md`.
3. M58: spec v3.x (`docs/specs/m58-joint-verification-scan.md`), STEP 1 PASSED (`$STACK_WORKDIR/m58/verify_microbench.run1.json`),
   BUILD (C118 go) on three branches, four review rounds each (Codex `gpt-6-astra`, Claude), all closed. Caught regression worth
   remembering: a router rule would have refused the shipped first pick (`kv_quant_scheme: turboquant` + `kv_bits: 0`) — golden tests
   now load the real registry in fork and router.
4. C121 seeded opencode sessions: finding (R1 of the ReviewBench review) → proposal `docs/proposal-opencode-seeding.md` → v2 blocker
   (C123: v2.0.20 forwards no model options; pinned 1.18.30 under the workdir) → 7 fix rounds → merged `28bb7ed`. Design as built:
   bench-owned HOME + per-run config home seeded from `benchmark/opencode_bench.json`, `--pure` everywhere, env stripped of
   `OPENCODE_*` then two switches, per-item seed overlay (+ title/snapshot off), per-item `debug config` checks, full resume identity,
   effective-inputs scaffold hash, receipt bound to exe/carrier/test (STAMPED today). Past opencode rows: unseeded (server default seed)
   and their system prompts carried the operator's private `~/.claude/CLAUDE.md` / `~/AGENTS.md` (recorded; rows annotated, no rerun).
5. Rulings: C116, C117, C118 (STEP 1 + build go), C120 (fold length-2 into M58), C122, C123 (option a; M59 queued for v2 migration).

## Open items, in priority order

1. **M58 live smoke + gate 1 + latency arms** (operator session; stack STOPPED; lean router). Steps: build a qualification worktree
   under `$STACK_WORKDIR/m58/wt-<sha>` whose `src/mlx-vlm` / `src/mlx-serve` point at 664c2ead / 3f2c87c and whose stack code is
   `m58-provenance`; live smoke (worker starts under `--mtp-verify-scan joint_v1`, self-test line, counters on a request; then
   `--mtp-verify-ab`); seeded pilot (5 prompts at 8K and 128K under AB); gate 1 per spec §P94 (G1a incl. straddle requests at
   T−64 and `verify_ab_invalid == 0`; G1b parity replay with the per_query→per_query reload control); then arms A/B k=2 order-balanced
   with the sustained-decode runner (`$STACK_WORKDIR/m58/decode_probe.py` — NOT yet written) and the mechanism session. Adoption per spec.
2. **C125 — operator rulings owed:** AgentBench base-0 schedule; `session_cache_probe.py` bare `opencode`; ratify the probe's pre-M50
   actions and the shared `~/.cache/opencode` write (not in the AGENTS.md exception list).
3. **C124** `run_opencode_probe.py` transport-abort gap (inherited); **C119** `generate` transport error rows — own proposals.
4. **M57 certification debt** (judge panel + Math500) on the FINAL state — after M58 adoption or rejection.
5. **M59** opencode v2 scaffold migration (queued).
6. Docker `.git` known-positive grades: see the C121 lab-notebook line (run at the end of this session).
7. `$STACK_WORKDIR/m55/m55_report.py` fixed for `passed: null` rows (workdir only, uncommitted — it is out-of-repo).

## Rules learned this session

- Validation changes must be tested against the REAL registry (golden tests), not synthetic entries — a review-driven "tightening"
  would have taken the daily driver down.
- Codex replays a prior review verbatim if the prompt points it at the prior review file — make review prompts self-contained.
- Cold reviewers that MEASURE (5-second GPU checks, mock request captures) found every load-bearing defect this session; ask for
  known positives in every brief.
- Isolation beats equality checks: give the bench its own HOME/config/state/tmp instead of asserting the operator's files match.
- Never rename/move the main checkout from an agent; use monkeypatch for path tests.
- `--pure` on EVERY opencode spawn — discovery without it installs npm packages and runs a GitHub plugin before the router check.

Next decision id C126; discussion ids continue from P110.
