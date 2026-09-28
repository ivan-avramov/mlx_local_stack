# Handoff — 2026-09-27 (later session): upstream sync of ../mlx-vlm IN FLIGHT, then M48 (C102(b)) — go given for both

THE one handoff (AGENTS.md: rewritten in place each session; there is no per-feature handoff). Read this,
then `docs/PLAN.md` (the only queue) and `docs/open-questions.md` (decisions). Specs for queued work live in
`docs/specs/`; history in `docs/lab-notebook.md`.

## State of the world

- **Git: all three repos pushed and clean** (2026-09-27, operator "go ahead with full push"): mlx-serve
  `6602ae5`, mlx-vlm `b5fdf113`, stack `ec4a01c`+. Forks first, then the stack, always.
- **Stack is UP** as the daily driver (started detached by the last session: `nohup ./runserver.sh`, router on
  `main_models.yaml`, sessions 2, APC absent, task model :8092, OWUI :3000 with
  `ENABLE_FORWARD_USER_INFO_HEADERS=true`). Stop with `kill -TERM <runserver pid>` (trap tears compose down).
- **Picks unchanged** (README/registry): B/C 1st `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` t0.5 medium,
  native16 KV (C81 provisional), repaired MTP. No pick or tune changed this session.
- Shell: `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=true` is exported in `~/.zshrc` (new shells only).

## Done since the 2026-09-21 handoff (all recorded in PLAN / open-questions / notebook)

| item | outcome |
|---|---|
| Thread review (2026-09-23) | Switchyard escalation = struggle detector, not a quality gate; frontier-driver + local-executor composition DEFERRED (switchyard doc §8, A1–A4 sketch); same-model subagent roles REJECTED on memory |
| M45 session-cache mechanics | DONE: opencode reuse ≈99%/request; eviction = one cold prefill; two mechanisms found → C102 |
| M46 opencode transcripts + loop metric | DONE in code (not yet exercised live) |
| M47 / C101 joint tune validity | CLOSED on the pilot: t0.5/medium stands; validity temperature-insensitive |
| C102(a) session ids reach the worker | DONE, cold-reviewed (Codex), live gate PASS, pushed |
| C103 opencode skill-tree drift | RULED + DONE: daily driver excludes the Claude tree; probes exclude both external trees + manifest scaffold fields |
| Periodic DeltaNet checkpoints (old C102(b)) | REJECTED in review; withdrawn |

## IN FLIGHT 2026-09-27 (later session): upstream sync of `../mlx-vlm`, then M48 — operator go given for both

Operator ruled: sync the fork with upstream FIRST, then execute M48 on top (P48). Order and state:

1. **Sync** — `git merge upstream/main` in `../mlx-vlm` (merge-base `434afb1a` 2026-09-14; upstream tip `967bf90b`
   v0.7.3, 107 commits). Dry run conflicts in 18 files: `generate/ar.py` (3 hunks), `generate/dispatch.py` (1),
   `server/{app,cli,generation,openai,responses_state}.py`, `turboquant.py`, `models/gemma4/language.py`, 10 test
   files. Resolve keeping fork semantics (session cache, prealloc, TurboQuant, MTP, thinking budget); take upstream
   for `clamp_temperature`/`top_p_sampling`, `logits_to_keep` unconditional, decode-loop periodic `mx.eval`
   (ece7a9dd), think-close newline strip (c36708d3), Chat/Responses parity (b1a85530), quantized-KV packed width
   (768ad7db), APC layout in cache classes. Do NOT pull the unmerged `pc/*` WIP branches.
   Gates after the merge: full fork suites (`../mlx-vlm/.venv`), C85 smokes, fresh `runserver.sh`, then a
   **40-pair output parity BASELINE at the deployed profile, MTP ON and OFF, on the post-sync fork** — upstream
   changed sampling, so the pre-sync fork is not the A5 baseline. Commit `merge: upstream 0.7.3 …`; bump
   `src/mlx-vlm` in the stack. If the sync is interrupted: `git merge --abort` in `../mlx-vlm` restores `b5fdf113`.
2. **M48 = B1 first, B2 second (P50/P51; operator to confirm the split when B1 lands)**. Spec:
   `docs/specs/c102b-prompt-end-retention.md`. Code facts established 2026-09-27 (P49) that the spec lacks:
   - Hook: after the final `_step()` in `generate_step` (`ar.py` ≈707, before `run_speculative_rounds`) — covers
     MTP ON/OFF. The dispatch `n == 0` "end-of-prefill" capture is one decode token late (decode loop steps before
     the first yield) and rotating-only; not a usable hook.
   - Divergence rewind = `snapshot_ring.find_nearest(prefix_len)` (`dispatch.py` ≈1008), fed ONLY by
     `PromptCacheState.update()`; `capture()` refuses non-monotonic offsets; served ring size 3
     (`--deltanet-ring-size`). B1 needs an explicit ring entry at the before-user anchor BEFORE the prompt_end
     entry → 2 snapshots at rest under B1, 3 under B2 (~154 MB each on the pick; A6 must count them).
   - Canonical assistant form is client-dependent: sessions render with `preserve_thinking=True`
     (`prompt_utils.CACHE_ALIGNMENT_KWARGS`), so the pick's template emits
     `<|im_start|>assistant\n<think>\n{reasoning_content|trim}\n</think>\n\n{content}<|im_end|>\n` for every
     history turn; the bytes depend on whether the client echoes `reasoning_content`. B2 must be validated live per
     client (opencode, OpenWebUI) via next-request `cached_tokens` and rewind-to-prompt_end log events.
   - B1 files: `ar.py` new `prompt_end_capture` kwarg + `_capture_anchor_state` at the hook (`mx.eval` the arrays);
     `dispatch.py` asymmetric branch (≈1385) restores prompt_end, trims KV to it, ring-captures the anchor states,
     `update(token_ids[:prompt_end])`; `snapshot.py` `DeltaNetSnapshotRing.capture_states(offset, states)`;
     `server/cli.py`+`session_manager` flag `--session-retain-prompt-end` default 1; fingerprint version bump in the
     stack. Tests in `tests/test_rewind_guard.py` style (fake caches): retire offset == prompt_end; ring order
     (anchor, prompt_end); edited user turn → anchor; edited assistant echo → prompt_end; flag off → today; pure
     attention → KV trim only.
   - B2 files: `server/openai.py` renders `messages + [assistant(content, no reasoning)] + [dummy user]` with the
     same template kwargs, requires `ids[:prompt_end]` == prompt ids, slices canonical; skips on tool calls or
     prefix mismatch. `dispatch.py` prefills canonical ids via `generate_step(max_tokens=0, draft_model=None)` on
     the retired cache, then `update(token_ids[:prompt_end+canonical_len])`.
   - Gates unchanged from the spec (A1–A7); A1/A4 get a B1-only pass criterion (per-turn prefill ≈ new user turn +
     assistant answer). Codex cold review before the fork commit lands.

## Pending (reconciled)

1. **M48 — C102(b) prompt-end retention** (`docs/specs/c102b-prompt-end-retention.md`): the only new
   GPU-adjacent work queued. Needs an explicit go. Mechanism: every request re-prefills its last user
   message once; big pasted turns / big tool results pay a full prefill of that turn.
2. **M46 live check**: the next opencode probe run must show one transcript per row and populated
   `loop_metrics` (and the new manifest `skill_policy` fields). Lands together with **D12** (harness-traffic
   accounting) on that run.
3. **Deferred**: frontier-driver composition (switchyard doc §8); S1 NVSY (parked, no go); C77/C78/C87 (deferred
   diagnostics, no GPU work armed); C96 search-engine policy (C97 resolved the shipped config).
4. **D7** (opencode in scoreboard roles) and **D5** (queue runner PAUSE/STOP) remain driver-side backlog.

## Rules learned this session (already in AGENTS.md / box-notes)

- `opencode run` from a harness: give it a FILE for stdout; a captured pipe stalls it at `init`.
- opencode embeds discovered skill paths in its system prompt; a resumed session forks silently if they
  change. Probes: `OPENCODE_DISABLE_EXTERNAL_SKILLS=true` (set by the probe). Daily driver: the Claude tree
  only.
- Session identity through the router: nine headers forwarded; the worker also reads `chat_id`,
  `metadata.chat_id`, `metadata.session_id`, Claude Code's `metadata.user_id` session id, `prompt_cache_key`
  (last). The anonymous hash chain stays the fallback.
- Cold review recipe: `codex exec --skip-git-repo-check --sandbox read-only -C $STACK_REPO/..
  --output-last-message <file> "<prompt>"` (default model `gpt-6-astra`), prompt = spec criteria + file
  pointers; runs 4–6 min; not inside a git repo → the skip flag is required.

## Resume discipline

One resident model; APC absent; retained sessions 2; full active preallocation; deployed sampling; explicit
served-overlay environment on every driver. Never alter source/config during a live run. Commit coherent
units; push only on explicit current-turn instruction (forks before stack). Next decision id C104;
discussion ids continue from P47.
