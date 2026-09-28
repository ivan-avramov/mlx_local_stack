# Handoff — 2026-09-27 (end of session): everything pushed; next work = M48 (C102(b) prompt-end retention), needs a go

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
