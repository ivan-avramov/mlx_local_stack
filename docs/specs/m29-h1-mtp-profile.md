# M29 H1 — MTP round profile for `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` (spec, 2026-08-31)

Status after K (`dd2a2dcb`, merged to fork main): re-probe 1.18× (OFF 138.0 / ON 163.2 tok/s), one
draft per round, acceptance 0.85–0.91. Round ≈ 11.5 ms for ~1.88 tokens vs a 7.25 ms target step:
verify ≈ 8 ms (one forward, 2 tokens), remainder ≈ 3.5 ms = drafter forward + per-round syncs +
Python. Gate to beat: 1.3× (M6a). Deeper drafting is pointless until the remainder is < ~2 ms.

## Deliverable H1 — env-gated round profiler in the fork
- Branch `nemotron-h-mtp-profile` from fork `main`. Fork only; stack untouched until the bump.
- In `mlx_vlm/speculative/mtp.py` `_mtp_rounds` (and `_mtp_rounds_batch` if trivially shared):
  when `MLX_VLM_MTP_PROFILE=1`, time each phase per round with `mx.synchronize()` fences:
  `draft` (draft_block incl. lm_head+argmax), `verify` (`_mtp_verify_target`), `walk`
  (`_mtp_acceptance_walk`), `rollback` (when called), `other` (round wall − sum). Also record
  `accepted`, `n_draft`. Every 200 rounds and at end: one stderr line
  `[mtp_profile] rounds=N draft=ms/rd verify=ms/rd walk=ms/rd rollback=ms/rd other=ms/rd emitted/rd=x`.
- Unset env → zero extra calls (no `synchronize`, no timers). Test both (CPU-pinned).
- Second switch `MLX_VLM_MTP_PROFILE_HEAD=1`: inside `NemotronHMTPDraftModel.draft_block`, split
  `eh_proj+layers`, `lm_head`, `argmax/sampler`, `eval` per draft token. Same reporting shape.
- Tests: `mlx_vlm/tests/test_mtp_profile.py` — with env set, a 3-round fake run emits the summary
  line with all fields; with env unset, `mx.synchronize` is never called (monkeypatch counter).
- black 88. Commit. Do not push without approval.

## Run (server path only — NO bare-process model loads)
- `cd benchmark && PYTHONPATH=$FORK:$PWD MLX_VLM_MTP_PROFILE=1 MLX_VLM_MTP_PROFILE_HEAD=1
  ../.venv-bench/bin/python -m m1.mtp_probe --model NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit
  --arm on --draft-model $STACK_WORKDIR/scratch/m6a/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit-mtp-drafter
  --workdir $STACK_WORKDIR/m29/profile_k1` — the probe starts its own router; stop the campaign
  router by pid first (verify 0 listeners on :8000), restart it on the draft-OFF overlay after.
- The worker's stderr goes to the probe's worker log under `--workdir`; read the `[mtp_profile]`
  lines from there. One run, ~10 min. Watch memory as `active+cache`, never `ps` RSS.

## Decision rule (pre-registered)
- `other + draft` share ≥ 50 % of the non-verify remainder attributable to syncs/Python/eval →
  H2: remove per-draft `mx.eval`, `async_eval` the head step, `mx.compile` the head forward;
  re-probe (M6a, k=1). Then, only if head cost < 2 ms/round, probe k=2 and k=3 (`--draft-block-size`
  via the temp registry or a probe flag).
- Any re-probe ≥ 1.3× → M6d-protocol quality OFAT (5-item seeded pilot → n=164 paired) → registry
  flip on PASS. < 1.3× after H2 → close M29 at its measured ratio, registry stays draft-OFF, next
  is M12. Report: campaign-results entry, PLAN M29 status, C44 line.
