# Handoff — 2026-10-22 (session 5 END checkpoint): P426 Wave-1 builds reviewed + accepted, fork + stack pushed; next = the S bump and Wave 1

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C209, C208, P433, P432, P431, C207, P427, P430,
P429, P428, C206, C205, P426, C204, C203, P422 …), then `docs/specs/p426-fable-mtp-recert.md` (v4 + the §2 / §6 attribution rule).
Model names: FULL registry names only, always.

## State of the world

- **Box `m5max-128`**, AC 140 W / 28 V, GPU IDLE (since 01:41). ALWAYS `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`.
- **Fork `mlx-vlm` `main` = `0b603d03`, PUSHED** (= the `p426-s` integration of P422 fixture + B1 draft counters in the
  `Request completed` line [the only production change, log / metrics only] + B4 settings-level registry matching (C203) + B7
  `qualify --predictor` + P429 leg-exit `os._exit`). Fork suites ×2 6815 / 17, eight audits green (`--upstream-ref 952d4f6b`).
  Topic branches (`p426-b1-draft-log`, `p426-b4-settings-match`, `p426-b7-qualify-off`, `p429-leg-exit`, `p422-registry-fixture`)
  are local only. B1 worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p426-b1` can be removed.
- **Stack `main` PUSHED** (P426 Wave-1 bench builds: `bench/p426_ids.py` + `benchmark/results/p426/ids.json`, `p426_plan.py`,
  `p426_leg.py`, `p426_overlay.py`, `p426_panel.py`; client session ids; vision `--ids` / seeds / counters; reasoning seed bases;
  bench_watch power). `src/mlx-vlm` STILL `2e66d89d` (the S bump is next); `src/mlx-serve` `86921f02` (unchanged, C202).
  Last stack suite (`c74b0fb6`): 7130 passed / 28 skipped / 1 xfailed / 1 failed = the P433 flake (root-caused, fix approved C209).
- Registry unchanged (all four MTP entries OFF; uniform + Qwen3.6 PROVISIONAL on TurboQuant); daily driver not restarted.
- Machine-local: `${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/judges.json` (C207 panel judges) created.

## Results this session

- P422 / C203 fixture + settings-level registry matching; C204 predictor shipping by operator judgement on signals (AGENTS.md
  amended; C206 panel = two model families via any client).
- P405 R5 both picks (P428 uniform, P431 Qwen3.6): at 256K TurboQuant decodes +40–50 % and peaks ≈ 6 GB lower (single session) but
  prefills ≈ 1.9× slower; at 8K uniform +1 %, Qwen3.6 −6 %. README rows + campaign-results. Codec decision waits for R6 (quality).
- P426 plan v4 accepted (C205) after 3 Cursor rounds; builds B1 (3 rounds, all closed), B4 / B7 / P429 (3 rounds + I1, C208), the
  leg wrapper (3 rounds + fixes, C208), B9 / B13 / B11 / B12 / B5 green; the panel B3 (C207) built and continues as its own review
  track (P432: its K8–K11 / L2 / L3 are the starting findings of panel round 1).
- P429: an exit segfault (thread-local MLX compile cache at interpreter finalization) — harness fixed; production exposure recorded.
- P430: cached_session drafter counters are exact under HTTP overlap (serial model-thread path); the wrapper requires
  `backend=cached_session` + session-id reconciliation.

## Next work, in order

1. **S bump** (local commit; its push needs a fresh ask): stack `src/mlx-vlm` → `0b603d03`; stack suite + one fork suite. Then
   the K3 integration test (`test_p426_plan.py::test_k3_round3_…`) must RUN (not skip).
2. **Frozen worktree** `$STACK_WORKDIR/worktrees/stack-p426` at S (`git worktree add`, `git submodule update --init`, `uv sync`,
   `.venv-bench` per `benchmark/requirements-bench.lock`, copy `.env`); `$STACK_WORKDIR/p426/frozen.json` (exclusive create:
   stack_head, stack_clean, mlx_vlm, mlx_serve, registry_off_sha, registry_on_sha); ON overlay via `bench.p426_overlay`.
3. **Wave 1 sequencer** (small, test-first; the operator may ask for a Cursor round): the §3 / §4 order — 10 smokes then 20 legs,
   OFF→ON block 1, ON→OFF block 2 per axis, 600 s idle, stop on the first INVALID smoke; each leg =
   `python -m bench.p426_leg --axis … --arm … --block|--smoke --stack-root <frozen> --workdir $STACK_WORKDIR --registry-on … --receipt-dir …`.
4. During Wave 1 (tests only in windows between legs, ≥ 10 min idle after): B8 pair verifier, B6 signals sheet, the panel review
   track (P432, round 1), the P433 fix, B2 (tg1 for Wave 2).
5. Later: the R6 plan (codec quality); mlx-serve v0.3.0 bump; P383, P385, tg2, M64; remove stale worktrees (`mlx-vlm-p369-r2`,
   `mlx-vlm-p426-b1`, `/private/tmp/mlx-vlm-review-*`); `docs/README.md` index additions.

## Rules learned (session 5)

- `uv run` in a dir without `.venv` creates an EMPTY venv silently; the fork suite needs `../mlx-vlm/.venv` (test extra +
  pytest-subtests, pytest-asyncio, cryptography); audits need `--upstream-ref 952d4f6b`.
- Never edit or test a tree while its suite runs (broken once this session: test files added during a stack suite).
- A test path literal under a home directory fails the repo PII scan — build such strings at runtime.
- cached_session requests run inline on the model-owning daemon thread (exact drafter counters); continuous_batching shares rounds.
- `pgrep -f <path>` misses a script started as `./x.sh`; wait on the PID.
- An existing test (`test_completions_endpoint`) leaks `in_flight` into the shared metrics store; tests reading it use a fresh store.
- Cursor lists 131 models (incl. GLM 5.2, Gemini 3.1 Pro); Gemini 3.1 Pro read a test image correctly, GPT-5.6 Sol High did not.

Next decision id C210; discussion ids continue from P433.
