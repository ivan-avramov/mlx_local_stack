# Handoff — 2026-10-20 (session 3, END): `Qwen3.8-27B-mlx-uniform-4bit` P369 phase 2 FULL RUN PASS on TurboQuant; P405 reviewed + merged-ready; P369 v13 harness built (code round 1 fixed, round 2 next)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P410 → C193, P409 closed, P408 / P407
deferred C190, P406 → C191, P405, C195, C194, C193, C192, C191, C190, C189), then `docs/specs/p369-phase2-run-plan.md` (v13,
accepted C193; V17 wall cap withdrawn C194) and `docs/specs/p405-kv-scheme-precedence.md` (v4, accepted C192).
Model names: FULL registry names only, always.

## State of the world (2026-10-20 13:40)

- **Box `m5max-128`**, 140 W / 28 V, GPU IDLE. **No `.env`**. ALWAYS `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`
  first (P409: without it the stack suite fails — docker off PATH, tg2 test root inside the repo).
- **Results today:** P369 phase 2 FULL RUN PASS for `Qwen3.8-27B-mlx-uniform-4bit` on TurboQuant (fork `64afc7dd`, run
  `$STACK_WORKDIR/p369/phase2/20261020-64afc7dd-full-uniform-tq-2`; E1c 5 / 5, E2, E7a M4a 6 / 20 M4b 11 / 20 M3 0 / 20, E7b 5 / 5;
  15 TurboQuant + 1 native KV leaves) — open-questions P369 + campaign-results. `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`
  PASS (2026-10-19, carries by C188 with a regression smoke on `7207179b` still owed).
- **Fork branches (all LOCAL, unpushed; operator: "no push yet"):**
  - `p369-mtp` `3a92943d` (= origin) — its worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p369` is the GPU runs' fork root (detached
    to the run head by the chain scripts, restored after).
  - `p400-tq-width2` `abbbfc84` — reviewed P400 head (C192).
  - `p405-kv-scheme` `64afc7dd` — reviewed P405 head (C195); production pin `7207179b` (P400 + P401 + P405 F1 / F2 / K6).
  - `p369-v13` `3e3cec09` (worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p405`, on `64afc7dd`; production unchanged): the v13 harness
    — `registry_states.py` (16 byte states), four-entry `PICKS` + one-entry campaigns + argv scan check, `pins.json`
    (Hub-verified identical to the certification uploads), loaded-drafter identity, borrowed panel + `--phase panel`,
    phase-based projection, MoE telemetry (routed banks, drafter draft-scope inventory), split-path characterization, V3 (d)
    served-shape MoE bitwise test (PASSES: no MoE P400 analogue at fixture level). **Code round 1 of 3 NOT CLEARED M1–M10 → all
    fixed** (`docs/reviews/p369-v13/`); all MoE Metal tests green (16). **Fork suites ×2 + 8 audits NOT yet run on `3e3cec09`;
    code round 2 not yet launched.**
  - `p404-arm-a` `e12780d0` (worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p404a`) = `p369-mtp` + P405 production only: R4 arm A.
- **Registry (`main_models.yaml`):** all four MTP-certified entries MTP-OFF — C177 (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`,
  `Qwen3.8-27B-mlx-uniform-4bit`) + C191 (`Ornith-1.0-35B-mlx-uniform-4bit`, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, marker
  `P406 INTERIM (C191 2026-10-20)`). Stack suite with config: 6941 / 6 / 0.
- **Stack `main`** ≈ 125 commits ahead of origin (docs + C191 registry). Pushes need an in-turn go.

## Waiting on the operator

- Nothing blocking. Pushes when wanted.

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

1. `p369-v13` `3e3cec09`: fork suites ×2 + 8 audits (`--upstream-ref 952d4f6b`, deletions `--strict`; PYTHONPATH = the p405
   worktree, p369 venv) → Cursor code round 2 of 3 on `5f407d5d..HEAD` (note: the `--phase panel` count-only boot loads weights,
   a declared refinement of V4) → ≤ 3 rounds, then operator table.
2. GPU (one at a time; launch detached with a chain script like `$S/chain_uniform_tq.sh`; a SMOKE THAT AUTHORIZES A FULL RUN must
   run with `--reviewed-head <same head>`; no `pytest` may run at a campaign's preflight):
   a. Fable regression smoke on the P405 head (C188 carry-over to `7207179b`).
   b. R4 — P404 TurboQuant ABBA: `dev/p400_perf_probe.py drive --old-tree <p404a wt> --old-ref e12780d0 --new-tree <p405 wt at
      64afc7dd> --new-ref 64afc7dd --pick Qwen3.8-27B-mlx-uniform-4bit --python <fork venv>`; then decide P404 with the operator.
   c. R5 — codec ABBA: `p400_perf_probe.py codec --tree … --ref …` (both schedules; long = 261,120-token prompts).
   d. R7 — six-entry 256K qualification (needs a small tool; plan v4 §5 R7).
   e. After v13 is reviewed: `--phase panel` for `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` and `Ornith-1.0-35B-mlx-uniform-4bit` →
      review + commit `dev/p369_phase2/borrowed_panel.json` → their campaigns (smoke bound, then full).
3. R6 (matched affine-vs-TurboQuant quality arms) and the router-chain re-certification: own plans, Cursor review, operator GPU go.
4. Then: fork main merge (P400 → P405 → v13) + candidate stack worktree bump → re-certification → per-entry MTP-ON restore
   (exact C177 / P406 pairs via `registry_states`). Then P383, P385, tg2, M64; remove stale worktree `mlx-vlm-p369-r2`.

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
