# Handoff — 2026-10-06 (18:00 UTC): M58 ADOPTED+SHIPPED (C126) and verified on the daily driver; C121 merged; queue accepted by the operator (items 1–6 below); stack UP, everything pushed

THE one handoff (AGENTS.md: rewritten in place each session). Read this, then `docs/PLAN.md` (M58 ADOPTED, M59 queued) and
`docs/open-questions.md` (C116–C126, all ruled except C119/C124 which await proposals). Day narrative: `docs/campaign-results.md`
2026-10-06 (two entries), `docs/lab-notebook.md` 2026-10-06, `docs/specs/m58-joint-verification-scan.md` v3.2,
`docs/proposal-opencode-seeding.md`. Artefacts: `$STACK_WORKDIR/m58/` (gate1_summary.md, gate/, g1b/, arms/, mechanism/, overlays/,
decode_probe.py + tests, straddle_probe.py, review logs), `$STACK_WORKDIR/c121/` (reviews, docker known-positives),
`$STACK_WORKDIR/harness-gaps/`, `$STACK_WORKDIR/reviewbench/`.

## State of the world

- Stack `main` = `539315d`+ = `origin/main`; mlx-vlm `main` = 664c2ead, mlx-serve `main` = 3f2c87c, both pushed; submodules match.
- **Daily driver is UP and verified under M58** (18:00 UTC): router `MLX_SERVE_CONFIG=main_models.yaml`, `MLX_VLM_CACHE_SESSION_MAX=2`;
  worker `--attention-policy fused_v1 --lazy-prompt-embeddings --mtp-verify-scan joint_v1 --draft-kind mtp`; log line
  `mtp_verify_scan=joint_v1 self-test: 2 cells`; a 16,745-token request: `verify_blocks_joint_v1=208`, `verify_fallback_reasons={}`,
  `sdpa_forced=528`, decode 44.9 tok/s. Same output and MTP counters as under `per_query` (identity holds on the daily driver too).
- Every manifest from now on is fingerprint v8 (`mtp_verify_scan`); pre-M58 first-pick rows do not pool with post-M58 rows (expected).
- Bench opencode: pinned 1.18.30 at `$STACK_WORKDIR/opencode-1.18.30/` (receipt stamped); the brew v2.0.20 is the operator's daily
  tool only. Bench HOME `$STACK_WORKDIR/opencode-probe/home/`. `benchmark/opencode_bench.json` is the bench carrier (9 models).
- Two stale agent worktrees `.claude/worktrees/agent-*` can be removed. `ts.md` is the operator's untracked note.

## What this day established (headlines)

- M58: a joint MTP verification scan is bitwise identical to the per-query scan EXCEPT across MLX key-length thresholds (1024 / 8192 /
  32768 / 65536 — the two-pass `blocks` count changes with key length); the fork's kernel-plan mirror predicts every exception, so
  `joint_v1` falls back per-query exactly there (rule 7) and the live gate counts those as known positives. Result: decode +14.8 % at
  128K, +19.7 % at 240K, +8.1 % at 64K, unchanged prefill/peak/acceptance; verify 110 → 96 ms per round. The shipped `length == 2`
  branch was already inexact at those thresholds (C120, folded in).
- C121: every opencode bench row before today ran on the server's default seed and carried the operator's private `~/.claude/CLAUDE.md`
  and `~/AGENTS.md` in the system prompt (rows annotated, no rerun). The probe now runs under a bench-owned HOME/config/state/tmp with a
  per-item seed overlay, `--pure` everywhere, and a full resume identity.
- A review-driven router "tightening" would have refused the shipped first pick (`kv_quant_scheme: turboquant` + `kv_bits: 0`) — fork and
  router now carry golden tests against the real registry.

## Queue (operator accepted 2026-10-06), in order

1. **Certification debt on the final shipped state** (native16 + M57 + M58): judge panel (M38/M40 style) and Math500 were never re-run
   under `fused_v1` + lazy embeddings; M58 is identity-gated so one run covers both. Box-evening; stack down; lean router; k per the
   earlier panel design; regrade-first where possible. Closes the "provisional" on the first pick's quality axes.
2. **C125 follow-ups (CPU, small):** required `--seed-base` for `run_agentbench_os.py` (distinct paired schedules; new rows only; M54
   annotated) and pin `benchmark/session_cache_probe.py` to the bench's opencode binary (`OPENCODE_PROBE_BIN` resolution) or freeze it.
   TDD + one cold review each.
3. **C119 + C124 transport-abort proposals:** `generate` records network/OOM exceptions as error rows and continues; the opencode probe
   proceeds to grading on a nonzero opencode exit. Classify transport vs generation vs gate; abort nonzero with nothing graded on
   transport; tests that no further request/item follows. Proposal first (AGENTS.md), then build.
4. **M59 — opencode v2 scaffold migration** (PLAN row): `--standalone`, git-initialised scratch dirs, native `providers/settings` schema,
   a sanctioned route for sampling + seed (v2 forwards NO model options today), verified by request capture; new scaffold version, never
   pools with 1.18.x rows. Spec via the M54 funnel.
5. **First seeded opencode chain** when a B question needs it (after 2): `--seed-base` per session, two bases, reload control; the probe
   is smoke-tested on the real binary but has NOT run a full item against a real model yet — `--limit 5` smoke first.
6. **Candidates not queued:** dense prefill path (≤ −14 % TTFT at chunks ≥ 2048); fused-kernel tuning; the unresolved 1.4–3.6 % `auto`-path
   slowdown for other models under the bumped fork (profiled pair in matched state); P41 watch-list; P42 harder long-context benchmarks.
   M56 PARKED (C110). ReviewBench DEFERRED (C122).

## Rules learned (this day)

- Golden tests against the REAL registry for any validation change in fork or router.
- Self-contained review prompts (Codex replays a prior review verbatim if pointed at its file); ask reviewers for known positives and
  measured checks — those found every load-bearing defect.
- Isolation beats equality checks (bench-owned HOME/config instead of asserting the operator's files match).
- `--pure` on every opencode spawn; discovery without it npm-installs and runs a GitHub plugin before the router check.
- Phase scripts must be self-contained (a `source <(sed …)` lost a function and silently skipped three arm sessions); the decode
  runner's headroom refusal is right — top sustained rung is 245760, not 262144; a straddle probe needs its own filler's chars/token.
- Never rename/move the main checkout from an agent; monkeypatch paths instead.

Next decision id C127; discussion ids continue from P116.
