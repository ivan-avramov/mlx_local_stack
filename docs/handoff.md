# Handoff — 2026-10-20 (session 4, evening): R4 done (P404 closed), v13 accepted (C199), Qwen3.6 campaign running, P415 R7 tool in code review round 2

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P417, C199, C198, P416, C197, C196, P415,
P414, P413, P412, P411, P404 closed), then `docs/specs/p369-phase2-run-plan.md` (v13), `docs/specs/p405-kv-scheme-precedence.md` (v4)
and `docs/specs/p415-r7-qualification.md` (v5 = the build spec; §2.5 wins). Model names: FULL registry names only, always.

## State of the world (2026-10-20 ~18:00)

- **Box `m5max-128`**, AC back (140 W / 28 V). ALWAYS `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"` first.
- **GPU RUNNING:** the `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` P369 campaign — smoke 17 then full, chain `$S/chain_qwen36b.sh`
  (session `060ea786…` scratchpad), runs `…/p369/phase2/20261020-a45f369d-{smoke17,full}-qwen36`, `--reviewed-head a45f369d`. No
  pytest while it runs.
- **Results today (session 4):** Fable regression smoke 15 PASS on `7207179b` (C188 carries); **R4 done → P404 CLOSED-BY-MEASUREMENT**:
  on TurboQuant fix A is within bounds and faster (`Qwen3.8-27B-mlx-uniform-4bit` 23.28 → 39.83 tok/s, Fable +0.28 %); panels for
  Qwen3.6 / Ornith written and committed (`a7c65f48`); smoke 16 found **P417** (drafter gate counted the bound target's 8-bit
  embedding / head) → fixed `a45f369d`.
- **Fork branches (LOCAL, unpushed):** `p369-mtp` `3a92943d` (GPU worktree `mlx-vlm-p369`, restored by chains);
  `p400-tq-width2` `abbbfc84`; `p405-kv-scheme` `64afc7dd`; **`p369-v13-panel` `a45f369d`** (worktree `mlx-vlm-panel`) = reviewed v13
  `3ae8770e` (C199) + panel data + P417 — THE campaign head; **`p369-v13` `bbe7a8cd`** (worktree `mlx-vlm-p405`) = `a45f369d` + P415
  (`5ccfe62c` red / `c112b09d` green) + P415 code-round-1 fixes; `p404-arm-a` `e12780d0`.
- **Registry:** unchanged (four MTP-certified entries MTP-OFF, C177 / C191).

## In flight

- P415 Cursor CODE review **round 2 of 3** on `bbe7a8cd` (round 1: NOT CLEARED D1–D13, all fixed test-first; D4 partly by design —
  the stack venv's mlx-vlm is the pre-bump submodule). Then the R7 smoke `--entry Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`
  (needs `--reviewed-head <cleared head>`), then the full R7 (all seven; Qwen3.6 needs its P369 full PASS summary).

## Next work, in order (convergence path, agreed with the operator 2026-10-20)

1. Qwen3.6 campaign result → P369 entry + campaign-results; if PASS, Ornith's campaign (same chain shape on `a45f369d`).
2. P415 review to clearance (≤ 3 rounds, then operator) → R7 smoke (Fable) → R7 full.
3. Fork merge P400 → P405 → v13 (+ panel + P417) → P415 into fork main — **needs the operator's push approval**.
4. Candidate stack bump (own worktree, both suites) → router-chain re-certification of Fable MTP-ON (own plan, review, GPU go) →
   restore Fable's C177 lines (Fable ships MTP-ON).
5. Off the critical path: R5 for `Qwen3.8-27B-mlx-uniform-4bit` (then Qwen3.6, P411 / C197), R6 (own plan).

## Rules learned (this session)

- A `run_in_background` shell is not detached: GPU chains go through `nohup … &` + a separate waiter; `chmod +x` first.
- `SwitchGLU`'s exact fused path is inference-only (`.eval()` in fixtures); a bound drafter carries the target's embedding / head
  as module children (P413 / P417) — anything that walks `drafter.modules()` must exclude them.
- The server refuses a request leaving < `MIN_OUTPUT_TOKENS` 2,048 of context: the largest accepted prompt at 262,144 is 260,096.
- Data-only fixtures for a campaign go on a branch off the reviewed head (code diff provably empty), never onto a branch carrying
  unreviewed code.
- isort / black disagree on wrapped-import `# noqa`; black last. Python string replacement of black-formatted code: anchor on
  unique text or index ranges; re-check after each formatter run.

Next decision id C200; discussion ids continue from P417.
