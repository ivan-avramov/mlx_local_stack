# Handoff — 2026-09-27: C102(a) DONE (session ids reach the worker; cold-reviewed; live gate PASS); C101 closed on the pilot; C103 filed

Read this first, then `docs/PLAN.md` and `docs/open-questions.md`. Reports: lab-notebook entries 2026-09-23
(M45) and 2026-09-27 (C102(a)); spec `docs/specs/c102a-session-headers.md`; switchyard doc §8.

## Operator rulings

- 2026-09-24: C101 → (b) close on the pilot (M47 CLOSED: t0.5/medium stands, validity temperature-insensitive).
  C102(a) approved with a client survey; C102(b) explained (stack fix for big-first-user-turn chats).
- 2026-09-27: "Go" on C102(a); "cold review with codex astra" → done (Codex `gpt-6-astra`, read-only).

## Runtime state

**Daily-driver stack is UP** (started detached by this session: `nohup ./runserver.sh`, pid in
`logs/runserver.nohup`; router `main_models.yaml`, sessions 2, APC absent; task model :8092; OWUI :3000
recreated with `ENABLE_FORWARD_USER_INFO_HEADERS=true`). Worker: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`
on the bumped submodules. Stop with `kill -TERM <runserver pid>` (its trap tears compose down) or leave it.

## Done this session (committed, NOT pushed — forks included)

- **C102(a)**: mlx-serve `6602ae5` forwards nine session headers; mlx-vlm `b5fdf113` resolves them (+
  `metadata.session_id`, Claude Code `metadata.user_id.session_id`, `prompt_cache_key` last) with value
  validation; stack `84f4540` bumps both + compose flag + spec + gate. Cold review PASS-WITH-GAPS, four
  findings fixed/qualified (notebook). Live gate PASS: opencode pinned, OWUI chat id = worker session with
  turn-2 reuse 5142/5179, anonymous fallback intact. Row `session_pinning_gate.c102a.json`.
- **C101 / M47**: closed on the pilot (`bfcl_fc.m47_pilot.json`).
- **Finding → C103**: every new `opencode run` process re-prefills its ~12.6K system prefix because the
  Claude Code synced-skills dir names rotate and opencode embeds skill paths in its system prompt; divergence
  lands before the only DeltaNet snapshot. Not caused by C102(a); costs 17–19 s per invocation.

## Open for the operator

- **Push**: forks `../mlx-serve` (`6602ae5`) and `../mlx-vlm` (`b5fdf113`) must be pushed BEFORE the stack
  (`84f4540` records their shas); stack commits since `3205052` are local only.
- **C103**: (a) opencode-side exclusion/prune of the synced skills dir (recommend now); (b) periodic
  DeltaNet snapshots in the worker, merged with **C102(b)** (needs a go; C85-certified path).
- Deferred composition (switchyard §8); S1 parked.

## Git

Stack HEAD `see git log` (docs + gate + results after `84f4540`). Forks: local commits on `main`, unpushed.
Push only on explicit in-turn instruction; forks first, then the stack.

## Resume discipline

One resident model; APC absent; retained sessions 2; full active preallocation; deployed sampling; explicit
served-overlay environment on every driver. `opencode run` from a harness: give it a FILE for stdout (pipes
stall it at init). Never alter source/config during a live run. Commit coherent units; push only on explicit
current-turn instruction. Next decision id C104; discussion ids continue from P36.
