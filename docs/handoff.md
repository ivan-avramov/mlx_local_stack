# Handoff — 2026-08-31 night (M27 CERTIFIED + EXECUTED — `3a200a9`; B menu = three certified MTP triples; box queue next: M21 → M12 → M17/D11)

Single box (M5 Max 64 GB). **No run is live.** This session was box-free: the M27 flip
package landed in full (operator in-turn go on the outward-facing HF pass). Router :8000 still
serves the draft-OFF bench overlay (`$STACK_WORKDIR/m6b/bench_overlay_draft_off.yaml`,
SESSION_MAX=2, APC absent; router pid in `$STACK_WORKDIR/m27/router_off.pid`) with
`Ornith-1.0-35B-mlx-uniform-4bit` resident from the M27 OFF arm. **Unload before any other
model work (`POST /v1/models/unload` + pgrep-verify); one resident model.** NOTE the bench
overlay predates the flip — it strips draft keys anyway, but regenerate it from the working
registry before the next bench run (procedure: lab-notebook 2026-08-28) so its header is current.

## Done this session (2026-08-31 night; lab-notebook same date)

- **M27 CERTIFIED & EXECUTED**: `caslca/Ornith-1.0-35B-mlx-uniform-4bit-mtp-drafter` public
  (7 files, safetensors sha256 verified vs the local sidecar, card CERTIFIED M27 incl. the
  k=2-served / `block_size: 3`-declared note); `caslca/Qwen3.8-27B-mlx-uniform-4bit-mtp-drafter`
  card PROBE-ONLY → CERTIFIED M6d; registry flip **`3a200a9`** (`draft_kind: mtp` + hub
  `draft_model` + `# CERTIFIED M27 2026-08-31`, B-menu header comment brought current); docs
  (campaign-results, PLAN M27 DONE / M6d row, ledger §1 B predictor paragraph — first time
  M6b/M6d/M27 are all in the ledger — C43 executed, AGENTS.md summary line).
- B menu now ships three certified (model, tune, mtp) triples: 2.06× / 1.56× / 1.60×.
  Measurement stays predictor-OFF by rule. M28 dormant (acceptance 0.778 vs ~0.8 trigger).
- **Working tree now carries SIX intentional `main_models.yaml` local-path overrides**
  (NEVER commit): 3× `draft_model` → `$STACK_WORKDIR/scratch/m6a/<name>-mtp-drafter`
  (`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, `Qwen3.8-27B-mlx-uniform-4bit`,
  `Ornith-1.0-35B-mlx-uniform-4bit`) + 3× `hf_path` → `$STACK_WORKDIR/models/…`
  (`Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`, `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit`,
  and `Qwen3.6-35B-A3B-Fable-5-Distill-mlx-uniform-4bit` — the last still NOT-YET-UPLOADED).
  Commit procedure that worked without stash: build the clean version from `git show
  HEAD:main_models.yaml`, `git hash-object -w` + `git update-index --cacheinfo`, commit,
  `/bin/cp -f` the worktree version back, assert `git diff` = exactly 6 override lines.
- **New box trap:** `cp` is aliased interactive (like `rm`) — scripted `cp` over an existing
  file hangs on the prompt. Use `/bin/cp -f` and verify.

## Operator decisions owed (none blocking the box queue)

- **C40** — strict single-number `reasoning_effective_ctx` (rec: largest passing strict rung
  + runaway rate / wall share reported separately).
- **C41** — fork TDD fix for the qwen3_5 MTP splitter (rec: fix — stacking for separate-expert
  sources, root-`model_type` detection fallback, fail-loud on per-expert keys).
- **C42** — M14 block-size-3 retry (rec: NO). C31 deferred. Next O/C number: **C44**.

## THE BOX QUEUE — updated 2026-08-31 night

1. ~~M27~~ **DONE (certified + executed, `3a200a9`).**
2. **Before ANY ladder rerun:** persist per-sample rows (score, completion_tokens, budget_hit)
   in `bench/reasoning.py` (C39 follow-up). Sizing rule for budget-hitting designs: bound =
   draws × (budget ÷ floor decode), never converged-draw / pilot pace.
3. **M21 int8 causal test** → **M12 d128k cliff check** (pre-registered, PLAN M12) → **M17/D11**.
   Every n≥40 job gets a 5-item SEEDED-RANDOM pilot first; monitors use `/usr/bin/tail -F` +
   `/usr/bin/grep --line-buffered` with a known-positive self-test line.

## Standing state

- **NOT PUSHED**: `3a200a9` (registry flip) + this session's docs commit are local; `git log
  origin/main..HEAD` lists them. Push only on explicit in-turn approval. Fork `../mlx-vlm`
  main = `d1d57955` (pushed); `src/mlx-vlm` submodule bump still deferred to the next natural bump.
- Untracked: M6b/M6d/M27 OFAT rows under `benchmark/results/` (M27:
  `Ornith-1.0-35B-mlx-uniform-4bit/humanevalplus.mtpon.*|mtpoff.*`; M6b storage precedent) +
  old m23-era files. Live `~/.config/opencode/opencode.json` = BENCH carrier on :8000.
- Artifacts: M11 `$STACK_WORKDIR/m11/`; M14 `$STACK_WORKDIR/m14/`; M27 `$STACK_WORKDIR/m27/`
  (overlay_ornith_mtp_on.yaml, ofat_accuracy_n164.json, probe/pilot/full logs, `flip/` = card
  drafts + committed/worktree registry versions); sidecars `$STACK_WORKDIR/scratch/m6a/`;
  pre-flip registry backup `$STACK_WORKDIR/scratch/main_models.local-overrides.backup3.yaml`.
- Bench-router invariants: draft-OFF overlay + SESSION_MAX=2 + APC absent; C35 tripwire live.
  Bench suite last GREEN at 1243 (not re-run this session — no bench code touched). HF cache
  253G + ~20 GB deliberate MTP-source fetches — don't "fix" it.

## Recently closed (2026-08-30/31)

M11 DONE (lenient 156K/156K/156K B menu, 16K `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`);
M14 CLOSED (probe STOP 0.76×); P17 fork merge+push; M6d CERTIFIED (`76dad59`); M6c suffix leg
CLOSED (1.20×); C38 B menu of three; C39 ruled; C43 ruled + executed.

**Order of resumption: this file → `docs/PLAN.md` → `docs/open-questions.md`.**
