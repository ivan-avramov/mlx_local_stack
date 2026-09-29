# Handoff — 2026-09-28 (end of session): M49 sync and M48 prompt-end retention DONE and PUSHED (fork `1bd249d3`, stack `afb407f`+)

THE one handoff (AGENTS.md: rewritten in place each session; there is no per-feature handoff). Read this,
then `docs/PLAN.md` (the only queue) and `docs/open-questions.md` (decisions). Specs for queued work live in
`docs/specs/`; history in `docs/lab-notebook.md`.

## State of the world

- **Git: all pushed** (operator, 2026-09-28 23:2x): fork `../mlx-vlm` main `1bd249d3`, stack main = this commit; mlx-serve
  unchanged (`6602ae5`). Clean trees.
- **Stack is UP** on the M48 fork (daily driver restarted by the chain at 12:11; router `main_models.yaml`, sessions
  2, APC absent; `--cache-session-retain-prompt-end` default on). Resident model after the last smoke:
  `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (leg B ran last).
- **Picks unchanged**: B/C 1st `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` t0.5 medium, native16 KV (C81
  provisional), repaired MTP. No pick/tune/serving-param change; M48 changes what the session cache keeps, not the
  text (A5: 40/40 identical, MTP on and off).
- Fork suite on `1bd249d3`: 5125 passed / 6 skipped / 1 xfailed. Stack bench tests green (1758 + new).

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

## DONE this session (details: notebook 2026-09-27→28 and 2026-09-28 entries; PLAN M48/M49; OQ C102, C104, C105)

- **M49** upstream sync to v0.7.3 (pushed). **M48** prompt-end retention (B1+B2 together, operator P56.2): four Codex
  cold-review rounds; the retire point became a per-request **retention boundary** (longest token prefix shared with
  the next rendering) because the shipped Qwen thinking-on tail re-tokenises. Live: A2 PASS (turn-2 reuse 12 →
  full opener at 8K/32K/64K; 12.5/55/130 s → 0.7/0.9/1.2 s), A4 PASS (16K opencode tool result retained; next
  request prefilled 27 tokens), A5 PASS (40/40 identical before/after, MTP on and off), A6 bounded PASS, smokes 6/6
  both models, A3 open (C105). Evidence `benchmark/results/m48_c102b_retention_20260928.json`.
- Tools: `benchmark/bench/stack_smoke.py`, `benchmark/bench/parity_replay.py`, probe `--big-file-tokens`,
  provenance **v6** (`runtime.session_retain_prompt_end`; rows at different states never pool).

## Rules learned this session (add to AGENTS.md if the operator agrees — see C105(4))

- `kill -TERM` on `runserver.sh` can leave the shell AND the router alive; a lean router then fails to bind and
  requests silently go to the daily driver. Stop by PID with escalation and verify `:8000` has zero listeners, then
  verify the new router OWNS the port (`lsof`) and read the worker cmdline (`--draft-kind`) as evidence, every arm.
- Probes launched from a tool shell without `nohup … </dev/null &` die on hang-up mid-request; the abandoned
  request then collides with the next one in the worker's tokenizer ("Already borrowed" → 500).
- opencode idles at init on a non-TTY inherited stdin: `stdin=DEVNULL` (probe fixed), stdout a file.
- Kill probes by PID and verify zero `session_cache_probe`/`opencode run` processes before launching another —
  a survivor contaminates log-window attribution and can 500 a concurrent run via a model swap.
- Upstream `uv sync` in `../mlx-vlm` drops pytest; reinstall `pytest pytest-subtests`.

## Pending (reconciled)

1. **C105** decisions: (2) OpenWebUI echo check, (3) template scoping note, (4) promote the PID-verified stop recipe
   into the repo. (1) A3 is CLOSED (pure-attention control on `gemma-4-31B-it-qat-6bit` PASS).
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
