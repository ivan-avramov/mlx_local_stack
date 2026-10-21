# Handoff — 2026-10-21 (session 4 END, checkpoint): P369 v13 campaigns ALL PASS, R7 qualified 7 / 7, fork merged + pushed, stack bumped + pushed

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C202, P421 closed, P420, P419 → C201, P418, P417,
C200, C199, C198, P416, C197, C196, P415 → C196, P414 → C199, P413, P412, P411, P409 closed, P404 closed), then the specs:
`docs/specs/p369-phase2-run-plan.md` (v13), `docs/specs/p405-kv-scheme-precedence.md` (v4), `docs/specs/p415-r7-qualification.md` (v5).
Model names: FULL registry names only, always.

## State of the world (checkpoint, 2026-10-21)

- **Box `m5max-128`**, AC 140 W / 28 V, GPU IDLE, nothing running. OrbStack OFF. ALWAYS
  `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"` first.
- **All repos pushed and consistent:**
  - fork `mlx-vlm` `main` = `2e66d89d` (origin) — P400 + P401 + P405 + v13 harness + borrowed panel + P417 + P415; production code
    = `7207179b`. Fork suites ×2 (6753 / 17) + 8 audits green on the P415 heads.
  - stack `main` (origin) — `src/mlx-vlm` = `2e66d89d`; `src/mlx-serve` = `86921f02` (NOT bumped: origin has an unvalidated upstream
    v0.3.0 merge `e6a7a5a6`, C202); registry: `Qwen3.8-27B-mlx-uniform-4bit` and `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` PROVISIONAL
    (served TurboQuant from the bump, C189 / C202); MTP still OFF for all four MTP-certified entries (C177 / C191).
  - mlx-serve: nothing local.
- **The daily driver is NOT restarted**: the bump takes effect at the next `./runserver.sh` / lean start.

## Results this session

- **P369 phase 2 — all four MTP-certified entries worker-qualified MTP-ON on production `7207179b`:** Fable (C188 carry-over, smoke
  15), `Qwen3.8-27B-mlx-uniform-4bit` (session 3), `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (full PASS, E1c 5 / 5, E2 PASS),
  `Ornith-1.0-35B-mlx-uniform-4bit` (full PASS, drafter MoE inventory 77 invocations).
- **P405 R4 → P404 CLOSED:** on TurboQuant the exact verifier is within bounds and faster (uniform 23.28 → 39.83 tok/s).
- **P405 R7 (P415) — 256K qualification, 7 / 7 COMPLETED** (shipped config, 260,096-token prompt, real settings): Fable MTP-ON
  38.25 GB; Qwen3.6 MTP-ON 30.16; uniform MTP-ON 28.27; served 23.48–28.47 GB. README row + campaign-results table.
- **P409 CLOSED:** stack suite Docker-down 6939 / 27 / 0 failed (session-scoped grader-image fake).

## Next work, in order (Fable → shipping MTP-ON is the critical path)

1. **Regenerate the fork's pinned registry fixture** (`mlx_vlm/tests/fixtures`, the 16-state generator's base) for the new
   registry bytes (C202 edit) — test-first, fork suites ×2 + audits; needed before any further P369 / R7 run.
2. **Router-chain re-certification plan for Fable MTP-ON** (P369 v13 §3.1 Restore; own plan, Cursor plan review ≤ 3 rounds,
   operator GPU go): reproduce the certified predictor (acceptance ≥ certified, decode ≥ 1.3×) on real chains, ON / OFF. Then restore
   Fable's C177 block (Fable ships MTP-ON). Repeat per entry for uniform / Qwen3.6 / Ornith.
3. **P405 R6** (matched affine-vs-TurboQuant quality, own plan) — lifts the two PROVISIONAL marks.
4. **R5** codec ABBA (`Qwen3.8-27B-mlx-uniform-4bit`, then Qwen3.6; C200: fixed lengths, 261,120 long prompt disclosed). Input:
   TurboQuant prefill at 256K ≈ 130 tok/s vs native16 Fable 370.
5. mlx-serve upstream v0.3.0 bump (one stack suite on it, then bump). Then P383, P385, tg2, M64; remove stale worktree
   `mlx-vlm-p369-r2`; `docs/README.md` index additions (P311 v4, P364, P369, P371, P415, review dirs).

## Rules learned (session 4)

- GPU chains: `nohup … &` + separate waiter (a `run_in_background` shell is not detached); `chmod +x` first.
- Never pytest while a campaign / measurement runs (the orchestrator refuses; Metal tests perturb). Stack suite ≈ 31 min, fork
  suite ≈ 3 min; never two at once; never edit a tree (incl. docs) while its suite runs.
- Power: 5-min ticks miss short outages — check `pmset -g log` ("Using Batt") against run windows (P418).
- A bound drafter carries the target's embedding / head as module children (P413 / P417). The cached path's seed lives in the
  sampler (P420); session retention runs a second prompt-only `generate_step` (P420); the drafter-free path lands its chunked
  prefill on a snapshot offset (P421).
- Data-only fixtures for a campaign go on a branch off the reviewed head; smoke-found fixes need no review round (P394).
- The server refuses a request leaving < 2,048 tokens: the largest accepted 256K prompt is 260,096.
- isort / black disagree on wrapped-import `# noqa` — black last; anchor scripted edits on unique text (black reflows).

Next decision id C203; discussion ids continue from P421.
