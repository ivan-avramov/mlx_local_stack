# Handoff — 2026-10-21 (session 5, checkpoint 20:55): P426 Wave-1 builds green, B1 reviewed, R5 Qwen3.6 rerun running

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P428, C206, C205, P426, C204, C203, P422,
C202 …), then `docs/specs/p426-fable-mtp-recert.md` (v4, accepted C205) — the Fable MTP-ON re-certification plan.
Model names: FULL registry names only, always.

## State of the world (checkpoint 20:55)

- **Box `m5max-128`**, AC 140 W / 28 V. ALWAYS `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"` first.
- **GPU: P405 R5 for `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` RERUN running** (started 20:52, ≈ 4.75 h): `scratchpad/chain_r5_qwen36b.sh`,
  out `$STACK_WORKDIR/p400/perf/20261021-r5-d3feb734-qwen36` (+ `.monitor.log`), tree worktree `mlx-vlm-p369` detached at `d3feb734`
  (P429 leg-exit fix; restored to `p369-mtp` at exit). The first attempt (`…-494aea2c-qwen36`) aborted at 2 / 8 (P429). No pytest
  until it ends.
- **Fork `mlx-vlm` (local only, NOT pushed):** `p426-s` `98106e2e` = the build-S candidate (P422 fixture + B1 + B4 + B7 + P429), fork
  suite ×2 6813 / 17 + 8 audits green. Branches: `p426-b1-draft-log` `be9424f1` (code review: rounds 1–3 done, all B1 findings
  CLOSED; G1–G3 were stack-side, fixed), `p426-b4-settings-match` `adba582f` (dev review round 2 RUNNING), `p426-b7-qualify-off`
  `df5ebb38`, `p429-leg-exit` `d3feb734`. B1 worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p426-b1`.
- **Stack `main`** (local, NOT pushed): P426 Wave-1 builds B5 / B9 / B10 / B11 / B12 / B13 / B4-stack committed green (74 P426 tests);
  stack suite on `cb2084a9` 7006 / 27 / 1 xfailed / 0 failed; later B10 fixes (E1, G1–G3) not yet in a full stack suite.
- Registry unchanged; daily driver not restarted.

## Results this session

- **P422 / C203:** fork pinned registry fixture regenerated (comments-only vs 7021bdbb); operator chose settings-level matching (B4).
- **P405 R5 `Qwen3.8-27B-mlx-uniform-4bit` (P428):** 261K — TurboQuant decode 9.98 vs affine 6.67 tok/s, single-session prefill peak
  25.34 vs 31.50 GB, prefill 129 vs 251 tok/s; 8K within ≈ 1 %. A retained 256K session adds ≈ 7.5 GB. README + campaign-results.
- **C204 / C206:** predictor ships on speed with no / negligible downside, operator judges on signals (AGENTS.md amended); panel =
  two model FAMILIES via any client (Cursor offers GPT-5.6, Gemini 3.1 Pro, GLM 5.2, Grok, Claude …).
- **P426 plan v4 accepted (C205)** after 3 Cursor rounds; ≈ 30 h GPU [39 h], 13 builds B1–B13, DAG §9.

## Next work, in order

0. **Parked for the next test window (after R5):** dev round 2 left F3 (overlay: YAML-structure spans, inert duplicate markers), H1 (`p426_overlay` loads the frozen file under a unique module name), H2 (B10 strict, type-aware delta check with pinned ON values and exact line identity). Red tests are UNCOMMITTED in the trees (fork branch `p426-b4-settings-match`: `test_p369_phase2_registry_states.py`; stack: `test_p426_leg.py`, `test_p426_overlay.py`); green patches `scratchpad/p426-b4r2-green.patch` (fork) and `scratchpad/p426-h1h2-green.patch` (stack). Run red → commit → apply → green → commit → merge B4 into `p426-s` → fork suites ×2 + audits → dev review round 3 (last) → stack review round 1.
1. Cursor reviews one at a time: fork dev builds round 3 (after the parked fixes) → stack builds round 1 (B5 B9 B10 B11 B12 B13 B4-stack incl.
   the G1–G3 / E1 fixes). ≤ 3 rounds each, then the operator.
2. When R5 Qwen3.6 ends: record it (README row, campaign-results, open-questions, as P428). Stack suite on the final stack head.
3. Fork push of `p426-s` (ASK the operator) → stack submodule bump = S (+ suites) → frozen worktree `$STACK_WORKDIR/worktrees/stack-p426`
   (`uv sync`, `.env`) → B4-stack overlay → Wave 1 smokes (B10 leg specs per §4–§5) → full axes.
4. During Wave 1: B8 (pair verifier), B2 (tg1 single-entry + invalidate + sequencer), B6 (signals), B3 = P427 (panel; pick the
   second judge family among Cursor's models after checking image input).
5. P429 production side (thread-local MLX compile cache at exit) — own proposal when it matters.

## Rules learned (session 5)

- `uv run` in a dir without `.venv` creates an EMPTY venv silently; the fork suite needs `../mlx-vlm/.venv` with the test extra.
- Byte-level registry matching made every comment edit block GPU runs → C203 (settings-level, B4).
- Cursor's model list is long (131); grep the full `cursor-agent models` output before saying a model is missing.
- R5 / R7 DryRun 500s in leg logs are the probe's own prompt sizing — benign.
- cached_session requests run inline on the model-owning daemon thread: drafter counters are exact under HTTP overlap;
  continuous_batching shares rounds (B1 D1).
- `pgrep -f <path>` misses a script started as `./x.sh`; wait on the PID.
- An existing test (`test_completions_endpoint` patched `record_success`) leaks `in_flight` into the shared store; use a fresh
  `ServerMetricsStore` in tests that read it.

Next decision id C207; discussion ids continue from P430.
