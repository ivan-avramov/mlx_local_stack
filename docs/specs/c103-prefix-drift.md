# C103 — per-process re-prefill of opencode's system prefix; C102(b) periodic DeltaNet snapshots (PROPOSAL, 2026-09-27)

Status: REVIEWED 2026-09-27 (Codex `gpt-6-astra`, read-only design review, ~6 min; report under
`$STACK_WORKDIR/c103/codex_review.md`) and MEASURED; awaiting operator go on A. Nothing shipped.

## Review outcome + measurements (2026-09-27)

- Diagnosis CONFIRMED from the captured bodies (only the four `<location>` lines differ; first difference at
  char 21,262 of 28,538) and from `dispatch.py` (no snapshot ≤ divergence → full re-prefill). A larger
  turn-boundary ring cannot help: every anchor lies after the system prompt.
- **A, verified live (two processes each, capture proxy + worker log):**

  | variant | system prompt chars | skills block | `skill` tool | process-2 first request cached/prompt |
  |---|---:|---|---|---:|
  | baseline (today) | 28,538 | present, volatile paths | yes | 0 / 12,922 |
  | `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=true` (env) | 14,898 | present, stable (`~/.agents` only) | yes | 8,858 / 8,986 |
  | `permission.skill: "deny"` (config) | 13,906 | absent | no | 8,455 / 8,583 |
  | `tools: {skill: false}` (config) | 13,906 | absent | no | 8,455 / 8,583 |

  Both config forms are equivalent in 1.18.30 (`tools.skill=false` → `permission.skill=deny`). The Claude
  synced-skills listing was ~4K tokens of EVERY request; removing it also cuts per-request prefill.
- Reviewer's ranking: (1) narrow discovery isolation (env flag) if skills matter; (2) `permission.skill: deny`
  if running without skills — ship only with capture verification (done above) and a versioned scaffold
  (record the skill policy + client version + config hash in the probe manifest; never pool with old rows
  silently); (3) B1 needs a redesign (the asymmetric path trims KV to the anchor and keeps only tokens
  before the latest user message, so a prompt-end DeltaNet snapshot alone cannot restore the M45 case);
  (4) periodic checkpoints only opt-in after specifying lifecycle, spacing and memory bounds.
- **B REJECTED as written.** My thinning bound was wrong: prefill work = (d − s) + (N − d); only the replay
  of unchanged tokens (d − s) is bounded by checkpoint spacing, the changed suffix is always processed.
  Lifecycle problems: eager captures conflict with `capture()`'s monotonic-offset rule and with
  `update()`'s post-generation `drop_after`; two rings need a joint nearest-≤d selection; shrink-on-retire
  skips DeltaNet state; the memory gate must be full-stack pressure/swap, not a worker-only ceiling (the box
  already logged 90.6% used / 1.9 GB swap with two sessions). Sizing confirmed: ~154 MB per snapshot.
  Hook points if ever pursued: `generate/ar.py` after each prompt chunk (periodic) and after the final
  prompt step before decode (prompt end).

## Evidence (lab notebook 2026-09-27; rows `session_pinning_gate.c102a.json`, `session_cache.c102a_legb.json`)

- Every new `opencode run` process on the pinned session re-prefills its whole ~12.6K-token prefix
  (worker: `Hybrid-Cache Rewind Guard: no snapshot available for rewind to 10430…12125`, `cached_tokens=0`,
  17–19 s). Within a process (tool round trips) reuse is 98–99%.
- Captured request bodies (logging proxy): the system prompt differs between processes ONLY in the
  `<location>` lines of opencode's discovered-skills block: `~/.claude/skills/synced/<uuid>_<uuid>/…/SKILL.md`
  (two synced copies exist, 09-24 and 09-27; opencode lists a different one per process) and
  `~/.agents/skills/vnote` vs `~/.claude/skills/vnote`. Tools, first user message, roles: identical.
- Worker mechanics (`generate/common.py` `PromptCacheState.update`, `snapshot.py`, `generate/dispatch.py`):
  DeltaNet snapshots are captured (i) mid-prefill at the anchor BEFORE the latest user message and (ii) at the
  end of each generation; ring FIFO size 3; on a new request, snapshots past the token divergence are dropped
  and the nearest snapshot ≤ divergence is restored, else full re-prefill. A divergence ~2K tokens inside the
  system prompt has no snapshot below it → everything is re-prefilled.
- Benchmarks are unaffected (each probe item is a fresh session; within-item round trips reuse). Daily-driver
  impact: `opencode run` CLI invocations and subagent processes; a long-lived opencode TUI process is stable.

## Proposal A (client side, zero worker risk): stop opencode from embedding volatile skill paths

A1. Disable opencode's `skill` tool in the SHIPPED config via `configgen` (top-level `"tools": {"skill": false}`
   in `opencode_config/opencode.json` and the bench overlay): removes the tool and its `<available_skills>`
   block (with the `<location>` lines) from the system prompt. We define no opencode skills; the listed ones are
   Claude Code's synced org skills and a personal vault skill, none used by the harness or the daily driver.
   Side effect: the system prompt shrinks (fewer tokens per request, every request). Scaffold note: the
   skills block already varied with the machine's `~/.claude` state (the synced dir did not exist before
   09-23), so historical agentic rows were never byte-stable on it; this makes the scaffold MORE stable.
A2. Alternative/complement: prune stale `~/.claude/skills/synced/*` copies — NOT durable (Claude Code re-syncs
   into a new uuid dir); rejected as the primary fix.
A3. `permission.skill: deny` — unverified whether the block is still rendered; not preferred.

Acceptance (A): capture two consecutive `opencode run` processes through the logging proxy → system prompts
byte-identical; worker log shows `cached_tokens ≥ 10000` on the second process's first request; configgen
tests + `configgen check` clean; opencode probe smoke (2 items) still completes.

## Proposal B (worker side, C102(b) revised): bounded periodic DeltaNet checkpoints + prompt-end snapshot

Sizing: state per linear layer = (1, 48, 128, 128) fp32 = 3.1 MB; 48 linear layers → **~151 MB per snapshot**
(conv state negligible). Today's ring: ≤3 snapshots ≈ 450 MB worst case per session.

B1. Prompt-end snapshot: capture after the suffix prefill completes, before generation (fixes the
   `[system, big-user]` first-follow-up case measured in M45: 9.7 s / 47 s / 126 s at 8K/32K/64K).
B2. Periodic checkpoints during prefill every `snapshot_interval` tokens (default 4096) into a separate
   bounded ring of K entries (default K=4 → ≤ ~600 MB per session): when full, thin by dropping every other
   checkpoint (interval doubles), so the K entries always span the prefix at ~prefix/K spacing (logarithmic
   thinning). On divergence at d, the nearest checkpoint ≤ d bounds the re-prefill to ≤ prefix/K tokens.
B3. Anchors (before-latest-user, end-of-generation) unchanged. Memory accounting: checkpoints count toward
   the session's footprint; `shrink-on-retire` must drop the checkpoint ring for idle sessions beyond the
   most recent M (default 1) to keep two-session peak within the measured 41–42 GB (M45 footprints).
B4. Config: `--deltanet-checkpoint-interval` / `--deltanet-checkpoints` CLI + env, registry `serve_args`;
   default ON only after B-acceptance; 0 disables.

Acceptance (B): (1) fork unit tests: thinning keeps K entries and spacing invariant; nearest-≤d selection;
drop-on-divergence still correct; (2) M45 leg C rerun: r2 reuse ≈ opener length at 8K/32K/64K (B1);
(3) a synthetic mid-prefix divergence test at 64K: re-prefill ≤ 64K/K tokens (B2); (4) output parity: 40
unchanged output pairs vs pre-change (same form as C84); (5) C85 regression suite + three-turn reuse smoke +
tool continuation + vision smoke pass; (6) worker `footprint` with two sessions live ≤ 42 GB + K×0.15 GB.
Risk: touches the C85-certified hybrid rewind path; memory at the edge on this box.

## Recommendation (post-review)

Ship `permission.skill: "deny"` in the shipped and bench opencode configs via `configgen` (we define no
opencode skills; it removes the volatile block AND ~4K tokens per request), record `skill_policy`,
`opencode_version` and the config hash in the opencode probe manifest as a scaffold version, and note the
env flag `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=true` as the alternative for anyone who wants `.agents`
skills. B: not now; if the big-first-user-turn cost matters later, a new spec must design joint KV/token/
state retention to prompt end (B1) before any periodic checkpointing.
