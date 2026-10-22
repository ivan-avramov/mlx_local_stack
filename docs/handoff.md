# Handoff — 2026-10-21 (session 5, checkpoint 19:05): P422 fixture done, R5 uniform done, R5 Qwen3.6 running, P426 plan v4 accepted, B1 in code review

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P428, C206, C205, P426, C204, C203, P422,
C202 …), then `docs/specs/p426-fable-mtp-recert.md` (v4, accepted C205) — the Fable MTP-ON re-certification plan.
Model names: FULL registry names only, always.

## State of the world

- **Box `m5max-128`**, AC 140 W / 28 V. ALWAYS `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"` first.
- **GPU: P405 R5 for `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` RUNNING** (started 18:55, ≈ 4.75 h): chain
  `$TMPDIR/…/scratchpad/chain_r5_qwen36.sh` (pid in `chain_r5_qwen36.pid`), out `$STACK_WORKDIR/p400/perf/20261021-r5-494aea2c-qwen36`
  (+ `.monitor.log`), tree = worktree `mlx-vlm-p369` detached at `494aea2c` (restored to `p369-mtp` at exit). No pytest until it ends.
- **Fork `mlx-vlm` (local only, NOT pushed):**
  - `p422-registry-fixture` `494aea2c` (= `main` `2e66d89d` + P422 fixture). Suites ×2 6755 / 17, audits green.
  - `p426-b1-draft-log` `c37a7d5e` (B1 red `1b52d3a8`, green `c37a7d5e`; suites ×2 6775 / 17, audits green). Code review round 1:
    DISAGREE D1 (counters are drafter-global diffs — exact only with one request in flight) / D2 (tests via a fake generator).
    Round-2 changes written, UNTESTED, uncommitted in worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p426-b1`: docstring + 5 new
    end-to-end tests; plan §2 got the `in_flight = 1` rule. Next: run them (verify the byte-exact OFF-line test also passes on
    `494aea2c`), commit, review round 2.
  - `p426-b7-qualify-off`: red test stashed (`git stash list`: "p426-b7-red-test"); green patch parked at
    `scratchpad/p426-b7-green.patch`.
  - `p426-b4-settings-match` (checked out in `../mlx-vlm`): red test edits UNCOMMITTED in the tree
    (`test_p369_phase2_registry_states.py`, `test_mtp_verify_scan.py`); green patch `scratchpad/p426-b4-green.patch`.
  - `../mlx-vlm/.venv` rebuilt this session (box-notes); audits need `--upstream-ref 952d4f6b`.
- **Stack `main`** ahead of origin by ~15 commits (docs + AGENTS.md C206), NOT pushed. Uncommitted: B9 `benchmark/bench/p426_ids.py`
  + `tests/test_p426_ids.py`, B13 test `tests/test_p426_reasoning_seeds.py` (green patch `scratchpad/p426-b13-green.patch`).
- Registry unchanged; daily driver not restarted.

## Results this session

- **P422 / C203:** fork pinned registry fixture regenerated (comments-only vs 7021bdbb); operator chose settings-level matching (B4).
- **P405 R5 `Qwen3.8-27B-mlx-uniform-4bit` (P428):** 261K — TurboQuant decode 9.98 vs affine 6.67 tok/s, single-session prefill peak
  25.34 vs 31.50 GB, prefill 129 vs 251 tok/s; 8K within ≈ 1 %. A retained 256K session adds ≈ 7.5 GB. README + campaign-results.
- **C204 / C206:** predictor ships on speed with no / negligible downside, operator judges on signals (AGENTS.md amended); panel =
  two model FAMILIES via any client (Cursor offers GPT-5.6, Gemini 3.1 Pro, GLM 5.2, Grok, Claude …).
- **P426 plan v4 accepted (C205)** after 3 Cursor rounds; ≈ 30 h GPU [39 h], 13 builds B1–B13, DAG §9.

## Next work, in order

1. When R5 Qwen3.6 ends: record it (P428 style: README row, campaign-results, open-questions). Then a TEST WINDOW: B1 round-2 tests
   → commit → Cursor B1 code round 2; B7 red (pop stash) → green (apply patch); B4 red → green; B9 / B13 red → green (`python -m
   bench.p426_ids` writes `benchmark/results/p426/ids.json`); fork suites ×2 + audits; stack suite (≈ 31 min). Then Cursor code
   reviews for B4, B7, B9 + B13.
2. Remaining pre-Wave-1 builds: B10 leg wrapper, B5 watcher (power fail-closed), B11 `vision_gate.py --ids`, B12 (A3 description
   + image path per row, A7 artifacts), B4-stack overlay builder. Then fork push (ASK the operator) → stack bump = S → frozen worktree
   → Wave 1 smokes.
3. GPU filler while builds review: nothing else approved is queued — ask before inventing runs.

## Rules learned (session 5)

- `uv run` in a dir without `.venv` creates an EMPTY venv silently; the fork suite needs `../mlx-vlm/.venv` with the test extra.
- Byte-level registry matching made every comment edit block GPU runs → C203 (settings-level, B4).
- Cursor's model list is long (131); grep the full `cursor-agent models` output before saying a model is missing.
- R5 / R7 DryRun 500s in leg logs are the probe's own prompt sizing — benign.

Next decision id C207; discussion ids continue from P428.
