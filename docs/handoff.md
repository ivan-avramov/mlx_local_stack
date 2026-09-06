# Handoff — 2026-09-06 09:55 (C48 + C49 RULED; M32b B-contest chain RUNNING: go leg → hep n=164 ×2 → MTP probe; ~17 h)

Single box (M5 Max 64 GB). **M32b RUNNING** (chain `$STACK_WORKDIR/m32b/m32b_chain.py`, pid in `m32b/m32b.pid`, log `m32b/m32b.log`, launched 09:48; legs: go 22 → hep n=164 `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` @t0.5 (~4 h) → hep n=164 `Qwen3.8-27B-mlx-uniform-4bit` @t0.6 (~10 h) → compare → MTP speed probe with `scratch/m6a/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter` (built 09:55 from the sidecar; probe stops the router and leaves it DOWN) → `=== M32B DONE ===`). Bench opencode carrier is swapped in during the go leg only. **C48 RULED: C 1st `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`, 2nd `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (provisional; registry comments flipped). C49 RULED: contest legs first.** Router UP on `$STACK_WORKDIR/m32/bench_overlay_m32.yaml` (generated from HEAD `main_models.yaml` +
the seven local-path overrides, draft-OFF; SESSION_MAX=2, APC absent; pid in `m32/router.pid`), worker for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` resident/idle.
Submodules BUMPED (`a08f933`): `src/mlx-vlm` 420c01e1, `src/mlx-serve` 0ccc6842 — every row from here carries the new serving-path hash; rows
before it (`920efc38`) do not `compare` across (C47 by design). Working tree: SEVEN intentional `main_models.yaml` local-path overrides — NEVER
commit (committed registry edits go via the HEAD blob; the C-pick comment restatement was done that way in `e4d3782`).
UNPUSHED: `a08f933`, `e4d3782`, plus this session's M32 landing commit. Push only on in-turn approval.

## Closed this session (details: campaign-results 2026-09-06 ×2, lab-notebook 2026-09-06)
- **M33 CLOSED** — math500 n=100 `acc_strict@81920`: `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` 89 / `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` 88 / `Ornith-1.0-35B-mlx-uniform-4bit` 86, every pair
  inconclusive (MDE ±12.5pp), nothing Holm-surviving, zero exclusive solves; July 81.5-vs-60.0 was pre-C28. No reorder on the key; C stays
  PROVISIONAL. Runaway tax 0.81 h / 16.4 h / 4.7 h per 100 → **C48 (swap C 1st/2nd on usability at tied quality? rec: yes, provisional).**
- **M32 CLOSED** — `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` @t0.5 opencode python **21/22, 1 stall** (B 3rd 20/22, sibling 13/22; 8:0 vs the sibling on its stall items, p=.008).
  Pre-registered read FIRES → B contest. Legs needed (each a proposal + seeded pilot + go): opencode go leg, humanevalplus n=164 @t0.5, M6d-style
  predictor probe of its MTP sidecar. **C49: run them before M24 (rec) or after?**

## Resume checklist (new session)
1. `lsof -nP -iTCP:8000 -sTCP:LISTEN` → router on the m32 overlay (verify `MLX_SERVE_CONFIG` on the pid with `ps -Eww`); no drivers live
   (`pgrep -fl 'run.py generate|run_opencode_probe|run_dsh_probe'`). If the router is down: start it on the m32 overlay (AGENTS.md recipe with
   `MLX_SERVE_CONFIG=$STACK_WORKDIR/m32/bench_overlay_m32.yaml`).
2. Read the C48/C49 rulings (open-questions), then the queue below. New arms need an overlay entry only for M34 (`moe_expand:` on a SEPARATE
   overlay — `compare` refuses across moe_expand, so the OFAT arm is its own row set under its own tune).
3. Chains to copy from: `m32/m32_chain.py` (opencode leg pattern: pinned binary, bench-carrier swap with the `_installed` guard, C35 with
   temperature readback, 5-min WATCH, paired McNemar), `m33/m33_chain.py` (generate/grade/compare pattern via `m21/arms_chain.py` helpers).

## THE BOX QUEUE
1. **M32b RUNNING** (above). After it: if the MTP gate ≥1.3× → predictor quality OFAT (hep n=164 mtp-ON vs the `m32b` rows, draft-ON overlay entry, ~4 h); the B-contest read (go + hep + predictor vs the B 3rd choice's cells) → B-menu decision (C38 standard: Holm-surviving to DISPLACE; a menu slot is the pressure valve).
2. **M24 medium arm**: `Qwen3.8-27B-mlx-uniform-4bit` @t0.6 `reasoning_effort=medium`, tune `t0.6-effmed`, M21b recipe + opencode python leg; pre-registered read + the
   truncation confound in PLAN (~12 h).
3. **M34 OFAT** on `Ornith-1.0-35B-mlx-uniform-4bit` (bumps DONE; needs its own overlay with `moe_expand: 27-39:20:0.8:0.5`; ~15–20 h).
4. **M35** dsh smoke + one python leg (~3 h): smoke = `run_dsh_probe.py --model Qwen3.8-27B-mlx-uniform-4bit --items affine-cipher --lang python --tune m35` with `MLX_SERVE_CONFIG` on the driver, then a 5-item SEEDED pilot before the 22-item leg; must confirm: model name on the wire, file_changed via read→write, no FS_NOT_OBSERVED refusals, gate ticks vary on a long item, no web/subagent tools on the wire (8-point checklist in the PLAN M35 row / verifier report).
5. M17 / D11 / M18 read; `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` temperature ladder if C48 promotes it (its t1.0 was never laddered).

## Standing rules that bit this session
- A chain's "another driver is live" pgrep must match PYTHON drivers only — a Monitor shell whose command line quotes the chain's name is not a driver
  (M32's first launch refused itself on `pgrep -f m33_chain`).
- An exit handler that restores/removes a third-party config must act ONLY if this run installed it (`_installed` guard) — the first M32 launch's
  FATAL removed the operator's daily-driver opencode config.
- `~/.config/opencode/opencode.json` is the file opencode actually reads; brew upgrades re-initialise that directory (2026-09-01 wiped it). Bench
  legs swap the bench carrier in and restore after; verify with the pinned binary's `opencode models`.
- A bench overlay is a FINGERPRINT INPUT: the `deployed` profile reads `MLX_SERVE_CONFIG`, so an overlay entry at the wrong temperature records a
  wrong manifest even when the client sends the right value. Regenerate overlays from HEAD after every registry edit.
- `compare` reports `acc`, not `acc_strict`; the ranking-key intervals were computed in `m33/review_strict.log` (a `--strict` switch is a small harness item).

## M21b CLOSED 2026-09-03 (campaign-results entry; PLAN row DONE)
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` @t0.5 vs `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` @t0.6-r2, k=3 on
hep (`c4216b9`) and mbpp (`e7810e8`): strict EQUIVALENT pooled n=100 (+0.7pp CI [−2.7, +4.3]); tokens-per-task ratio
0.66 / 0.64 per bench, pooled **0.650 CI [0.455, 0.880]**; P28 met on both benches (mbpp on all three conditions).
Operator ruled CARRY: uploaded `caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (public, 15 files, sha-verified,
card with the paired results), registry entry @t0.5 `# CERTIFIED M21b 2026-09-03`, candidate role, draft-OFF (triple
rule applies only on promotion; the artifact carries an MTP head sidecar, untested). Bench carriers regenerated
(`configgen`), check clean. Mechanism: the recipe trims the verbose/bimodal tail, not the chronic failures.

## Landed 2026-09-02 evening → 2026-09-03
- **C47 SHIPPED (`19e6fbb`)**: fingerprint v5 = serving-path tree hash beside the commit sha; `compare` refuses only on a
  serving-path change; older manifests derive it. Spec `docs/specs/c47-serving-path-fingerprint.md`. Live: `57177a21`
  ≡ `7330d3a6` ≡ `f5fff9b5`; `ab5708a` differs.
- **Docs reorganized (`6ae5772`)**: `docs/superpowers/`, `docs/sketches/`, `docs/work-queue.json` DELETED (git history
  is the archive, last present at `b723bde`); `docs/specs/` for design docs; `docs/README.md` index; PLAN.md is the ONLY queue.
- Community thread + JetBrains review (P43–P48) → **M31** ifeval arm for `Qwen3.8-27B-mlx-uniform-4bit` queued.
- Pre-session untracked rows committed (`5b8f4de`, `3ea3d9c`); C46 filed.

## M34 BUILT 2026-09-03 (forks pushed; submodule bumps landed 2026-09-06 `a08f933`)
Layer-scoped expert-budget expansion (spec `docs/specs/m34-moe-expert-expansion.md`). Fork `../mlx-vlm` main: `b95130c9` (feature)
+ `420c01e1` (verifier fixes) — 2 ahead of origin. `../mlx-serve` main: `0ccc684` — 1 ahead. Stack: `674499c`, `0e1a29b`, `3493c34`
(PARAMS drift-guard fix). NOT YET: fork pushes → `chore(stack): bump src/mlx-vlm` + `src/mlx-serve`; registry `moe_expand:` field on an
M34 overlay entry; the OFAT (after M33). Verifier scripts kept at `$TMPDIR/m34verify/` (re-run `v3_identity.py` after any routing edit).

## Artifacts
`$STACK_WORKDIR/m33/` (chain, waiter, `m33.log`; empty until the waiter fires).
`$STACK_WORKDIR/m31/` (chain, `m31.log`, driver + `watch_*` logs, grade + compare logs).
`$STACK_WORKDIR/c46/` (chain, `c46.log`, per-run driver + `watch_*` logs, `mem_arms.log`, pilot/full pids, grade + compare logs).
`$STACK_WORKDIR/m21/` (chains, logs, `k3_analysis.py --bench`, analyses, card draft, overlay);
`$STACK_WORKDIR/optiq_out/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/optiq_mixed` (18 GB, the served local copy of the
uploaded repo — KEEP, it is the registry override target). HF cache: the `TeichAI/Qwen3.8-27B-Fable-Distill` bf16 source <!-- allow-shorthand -->
(52 GB) was DELETED 2026-09-03 18:20 (operator); re-download only if a new conversion is ever planned.

- Old-vs-new `compare` on C46 rows REFUSES by design: the old rows sit at serving path `17e0e5a7` (fork `0c1c8b17`), HEAD is `920efc38`; the verdict is new-vs-new plus the DNF follow-up. Item sets are identical (seed-0 draw), so the follow-up is paired.

**Order of resumption: this file → `docs/PLAN.md` (C46 row in open-questions, M31) → `docs/open-questions.md`.**
