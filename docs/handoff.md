# Handoff — 2026-09-28: upstream sync of ../mlx-vlm DONE (M49, unpushed); next = M48 B1 (go given, split awaiting confirmation)

THE one handoff (AGENTS.md: rewritten in place each session; there is no per-feature handoff). Read this,
then `docs/PLAN.md` (the only queue) and `docs/open-questions.md` (decisions). Specs for queued work live in
`docs/specs/`; history in `docs/lab-notebook.md`.

## State of the world

- **Git: NOTHING PUSHED since the 2026-09-27 push.** `../mlx-vlm` main = `2c276351` (merge of upstream
  v0.7.3 `967bf90b`; parents `b5fdf113` + `967bf90b`); stack HEAD bumps `src/mlx-vlm` to it and adds the smoke
  runner + docs. mlx-serve unchanged (`6602ae5`). Push order when the operator says so: fork first, then stack.
  The stack's `src/mlx-vlm` submodule fetched the merge commit from the LOCAL fork path; a fresh clone cannot
  resolve it until the fork is pushed.
- **Stack is UP** on the merged fork (`nohup ./runserver.sh`, started 2026-09-28 00:0x; router `main_models.yaml`,
  sessions 2, APC absent, task model :8092, OWUI :3000). Resident model after the smokes:
  `Qwen3.8-27B-mlx-uniform-4bit`. Stop with `kill -TERM <runserver pid>` (trap tears compose down).
- **Picks unchanged**: B/C 1st `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` t0.5 medium, native16 KV (C81
  provisional), repaired MTP. No pick/tune/serving-param change in the sync.
- Fork suite on `2c276351`: 5068 passed / 5 skipped / 1 xfailed. Live smokes 6/6 on both deployed models
  (`benchmark/results/upstream_2026-09-28_smokes.json`).

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

## DONE 2026-09-28: M49 upstream sync (details: notebook 2026-09-27→28 entry, PLAN M49, open-questions C104)

Resolutions to remember: fork serving semantics kept everywhere; upstream taken for sampling
(`clamp_temperature`, speculative `top_p_sampling`), unconditional `logits_to_keep`, periodic decode cache eval,
think-close newline strip, tool-call stream parity, Chat/Responses + Anthropic parity, model discovery.
Tests: stale fork copies of changed upstream tests dropped and upstream's ported; 30 serving-path files
restored from the fork; `tests/test_mtp_split.py` holds the fork's MTP-split tests. `bench/stack_smoke.py`
is the reusable live gate (six cases at the deployed profile). **Consequence for M48:** the A5 parity BEFORE
arm is served from fork `2c276351`, never from the pre-sync fork (sampling changed upstream).

## NEXT: M48 = B1 first, B2 second (P50/P51) — operator has given the go for M48; confirm the split

Spec `docs/specs/c102b-prompt-end-retention.md`. Code facts established 2026-09-27 (P49) that the spec lacks:
- Hook: after the final `_step()` in `generate_step` (`ar.py`, before `run_speculative_rounds`) — covers
  MTP ON/OFF. The dispatch `n == 0` "end-of-prefill" capture is one decode token late and rotating-only.
- Divergence rewind = `snapshot_ring.find_nearest(prefix_len)` (`dispatch.py` reuse block), fed ONLY by
  `PromptCacheState.update()`; `capture()` refuses non-monotonic offsets; served ring size 3
  (`--deltanet-ring-size`). B1 needs an explicit ring entry at the before-user anchor BEFORE the prompt_end
  entry → 2 snapshots at rest under B1, 3 under B2 (~154 MB each on the pick; A6 counts them).
- Canonical assistant form is client-dependent: sessions render with `preserve_thinking=True`
  (`prompt_utils.CACHE_ALIGNMENT_KWARGS`), so the pick's template emits
  `<|im_start|>assistant\n<think>\n{reasoning_content|trim}\n</think>\n\n{content}<|im_end|>\n` for every
  history turn; bytes depend on whether the client echoes `reasoning_content`. B2 is validated live per client
  (opencode, OpenWebUI) via next-request `cached_tokens` and rewind-to-prompt_end log events.
- B1 files: `ar.py` new `prompt_end_capture` kwarg + `_capture_anchor_state` at the hook (`mx.eval` the
  arrays); `dispatch.py` asymmetric branch restores prompt_end, trims KV to it, ring-captures the anchor
  states, `update(token_ids[:prompt_end])`; `snapshot.py` `DeltaNetSnapshotRing.capture_states(offset,
  states)`; `server/cli.py` + `session_manager` flag `--session-retain-prompt-end` default 1; fingerprint
  version bump in the stack. Tests in `tests/test_rewind_guard.py` style (fake caches): retire offset ==
  prompt_end; ring order (anchor, prompt_end); edited user turn → anchor; edited assistant echo →
  prompt_end; flag off → today; pure attention → KV trim only.
- B2 files: `server/openai.py` renders `messages + [assistant(content, no reasoning)] + [dummy user]` with
  the same template kwargs, requires `ids[:prompt_end]` == prompt ids, slices canonical; skips on tool
  calls or prefix mismatch. `dispatch.py` prefills canonical ids via `generate_step(max_tokens=0,
  draft_model=None)` on the retired cache, then `update(token_ids[:prompt_end+canonical_len])`.
- Gates unchanged from the spec (A1–A7); A1/A4 get a B1-only pass criterion (per-turn prefill ≈ new user
  turn + assistant answer). Codex cold review before the fork commit lands. Order per the operator's task:
  TDD → cold review → fork commit + bump → live A2–A6 with a fresh `runserver.sh` → notebook/PLAN/OQ/handoff.

## Pending (reconciled)

1. **M48 — C102(b) prompt-end retention**: go given; see NEXT above. Push of the sync (fork then stack) awaits an
   explicit operator instruction.
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
