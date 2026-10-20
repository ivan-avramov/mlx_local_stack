# Handoff — 2026-10-20 (session 3, in progress): P405 reviewed (`64afc7dd`, C195) — TurboQuant engages live, E1c / E2 PASS on it; `Qwen3.8-27B-mlx-uniform-4bit` TurboQuant full run next (C193, no wall cap C194); P369 v13 (four campaigns, C193) accepted

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P409, P407 / P408 deferred, P406 → C191,
P405, C195, C194, C193, C192, C191, C190, C189 …), then `docs/specs/p369-phase2-run-plan.md` (v13, accepted C193; V17 withdrawn
C194), `docs/specs/p405-kv-scheme-precedence.md` (v4, accepted C192). Model names: FULL registry names only, always.

## State of the world

- **Box `m5max-128`**, 140 W / 28 V. **No `.env`**. Machine config: `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`.
- **Fork `p405-kv-scheme`** (worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p405`, local only) HEAD **`64afc7dd` = the reviewed
  P405 head** (C195; code rounds 1–3 `docs/reviews/p405/`), on top of `p400-tq-width2` `abbbfc84` (reviewed P400 head, C192).
  Production pin `7207179b` (P400 + P401 + P405 F1 / F2 / K6). Includes: `dev/p369_phase2/kvmanifest.py` (argv codec, resolved
  KV fields, exact per-layer + drafter manifests), the perf probe's `codec` mode (R5) with live-cache checks, the C193
  `--projection-ruling` (lifts only `fits`, no cap), `--wall-limit-s` finite > 0. Suites ×2 + audits on `64afc7dd`: see below.
- **Live evidence:** smoke 11 (affine, today's serving) SMOKE_PASS; smoke 12b / 12c (TurboQuant on P400 + P405): TurboQuant
  ENGAGES (`KV cache resolved: … turboquant … 'mse'`; 15 TurboQuant + 1 exempt native leaves; manifest clean), **E1c / E2 PASS**;
  12c: all positives fired, only `fits` open (12,894 s > 12,600 s) → C193.
- **Registry:** C191 interim MTP-OFF for `Ornith-1.0-35B-mlx-uniform-4bit` + `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (marker
  `P406 INTERIM (C191 2026-10-20)`), on top of C177 (the two Qwen3.8-27B picks). All four MTP-certified entries are MTP-OFF.
- `p369-mtp` = `3a92943d` (= origin); its worktree is on the branch between smokes (the waiters restore it).
- **Stack `main`** ≈ 110 commits ahead of origin. Pushes need the operator's in-turn go ("no push yet").
- Stack suite: run it with the machine config sourced (P409 closed: the 4 failed + 9 errors were an unsourced-config artifact).

- **Fork `p369-v13`** (P405 worktree, local only) HEAD `5f407d5d` on `64afc7dd`: the P369 v13 harness build — 16-state
  registry generator (`dev/p369_phase2/registry_states.py`), four-entry `PICKS` + one-entry campaigns + argv scan check,
  `pins.json` (Hub-verified identical to the certification uploads), loaded-drafter assertions, borrowed panel +
  `--phase panel`, phase-based projection, MoE telemetry (routed banks, drafter draft-scope inventory, smoke-gate
  requirement), split-path characterization (adversarial nested `qwen3_next` refused by strict load), V3 (d) MoE bitwise
  test. Code review round 1 of 3 NOT CLEARED M1–M10 → all fixed (M1 / M2 / M3 / M9 / M10 tested on CPU; M4–M8 + V3 tests
  written, **Metal-only — run after the GPU campaign**, then code round 2).
- **GPU: the `Qwen3.8-27B-mlx-uniform-4bit` TurboQuant FULL RUN** (started 2026-10-20 11:27, ≈ 3.5–4 h;
  `$STACK_WORKDIR/p369/phase2/20261020-64afc7dd-full-uniform-tq-2`, manifest: reviewed head `64afc7dd`, production
  `7207179b`, `--projection-ruling C193`, no wall cap C194), bound to smoke 14 (`…-smoke14-uniform-tq-bound`: gate pass,
  only `fits` open, 12,942 s). Chain `$S/chain_uniform_tq.sh` (pid at launch 4004) restores the p369 worktree after — verify.
  Smoke 13 (unbound: run without `--reviewed-head`) could not authorize; the first full attempt `…-full-uniform-tq` refused.
- **Fork `p404-arm-a`** (worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p404a`) `e12780d0` = `p369-mtp` + the P405 production commits
  (F1 / F2 + the K6 hunk): the R4 ABBA arm A; production-differs from `64afc7dd` by P400 + P401 only.

## Waiting on the operator

- Nothing blocking. Pushes (`p400-tq-width2`, `p405-kv-scheme`, stack `main`) when wanted. P409 fix proposal (small).

## Smoke-found bugs (fixed test-first; P394: smoke iterations need no review round)

- Smoke 1: requests carried the registry name; mlx-serve's router rewrites `body["model"] = hf_path` (`router.py:483`) → the
  worker unloaded its target and tried an offline load. Fix: `routed()` in `post` / `prompt_ids` (`f0bfce29`).
- Smoke 2: the dry-run `DryRun(BaseException)` unwound through `@app.middleware("http")` as a `BaseExceptionGroup` and killed the
  TestClient portal (reproduced on CPU). Fix: plain `Exception`, ids recorded on the side (`7b87192e`).
- Smoke 3: **P398** — E1c compared a stale ON row at a thinking-budget forced position (E1c `max_tokens` 160 → budget 128 →
  forced `\n</think>`). Fix: rows cut at each block's emission decision, forced positions proven and excluded (`8d1cf115`).
- Smoke 4: P399 (rejected attempts' evidence dropped) and P400 (production defect) — open-questions.
- Observed, not a bug: Fable T = 1,024 seed a0 had no observed key-length straddle (a block boundary landed on 1,024) while the
  production counter read 16 → that cell retries the next seed (by design). T = 65,536 E1c cell > 11 min (hash cost).

## Next work, in order

1. Smoke 13 bound to `64afc7dd` → the `Qwen3.8-27B-mlx-uniform-4bit` TurboQuant full run (`--reviewed-head 64afc7dd
   --smoke-summary <smoke 13> --projection-ruling C193`, no `--wall-limit-s`, C194); 5-min monitor; record in P369 / P405.
2. During it (CPU only, no suites): the P369 v13 harness build (test-first): 16-state byte generator; `pins.json`; borrowed
   panel fixture; `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` + `Ornith-1.0-35B-mlx-uniform-4bit` PICKS; tiny `qwen3_5_moe` +
   `qwen3_next` split tests (V3 / V12 / V14 / V15); phase-based projection (V13). Then Cursor code review (≤ 3 rounds).
3. GPU after: Fable regression smoke on `7207179b` (C188 carry-over); R4 P404 ABBA (P405 both arms: arm A = `p369-mtp` + the
   P405 commits on a dev branch); R5 codec ABBA (`p400_perf_probe.py codec`); R7 six-entry 256K qualification; then the
   Qwen3.6 / Ornith campaigns. R6 (matched quality arms) + router re-certification: own plans + operator GPU go.
4. Then: fork main merge (P400 → P405) → candidate stack worktree bump → re-certification → per-entry MTP-ON restore.
   P409; P383, P385, tg2, M64. Remove the stale `mlx-vlm-p369-r2` worktree.

## Known gaps / owed

- Residuals (disclosed): a helper that spawns and escapes between two ps polls; pid reuse within one lstart second; a cache
  symlink swap during model load restored before the re-hash; H37 (total ps failure after a setsid helper); H12 (CI oracle
  `fetch-depth: 0` + `MLX_REQUIRE_P369_ORACLE=1`) with the fork main merge. E2/E7 link to the original C84 runs is count-only.
  `tq_norm` positive and the kernel coverage set unproven on real weights until the smoke. E7 tool-session exposure not measured.
- `docs/README.md` index additions (P311 v4, P364, P369, P371, m65 tg2, M65 pilot, `docs/reviews/p371/`, `docs/reviews/p369-harness/`,
  `docs/reviews/p369-c185/`, `docs/reviews/p387/`, the phase-2 plan, the P387 note); one pre-existing pyflakes note in
  `test_mtp_verify_scan.py` (`harness`).

## Rules learned

- Suites: fork `(cd mlx_vlm && ../.venv/bin/python -m pytest -q ./tests --ignore=tests/test_smoke.py -rs -p no:cacheprovider)` ≈ 2.5 min;
  stack from `benchmark/` AFTER sourcing the machine config (P409: without it docker is off PATH and the tg2 test root
  falls inside the repo): `../.venv-bench/bin/python -m pytest bench/tests -q -p no:cacheprovider -o faulthandler_timeout=600 -rs`.
  Never two suites at once; never edit a worktree while its suite runs. Audits: the 8 `dev/check_*.py --upstream-ref 952d4f6b`
  (`--strict` for deletions) from the worktree with `.venv/bin/python`.
- **Cursor:** `cursor-agent -p --output-format stream-json --model gpt-5.6-sol-high --mode ask --sandbox enabled --force --trust
  --workspace ~/ws/mlx-vlm "<prompt>" > out.jsonl`, review text = the `type=="result"` event's `result`. One run at a time; state
  "round k of 3".
- Formatting: `uvx --offline black@26.3.1` (its "Python 3.12 cannot parse" warning is harmless), `isort@5.13.2 --profile=black`,
  `pyflakes`. BSD sed chokes on the em dash — use Python for exact-line edits.
- A deadline-capped `ps` (H33) needs a margin wherever a loop's own deadline bounds it (P396); a test that flakes is a bug report.
- Tests that start processes own them in fixtures that kill the PGID and any self-recorded child pid at teardown.
- Zero flakes; red-first honesty (say "helper absent" vs behavioural); check `git show --stat` after every commit.

Next decision id C196; discussion ids continue from P410.
