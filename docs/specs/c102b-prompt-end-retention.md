# C102(b) — retain the latest user turn across requests (prompt-end anchor) — PROPOSAL for a new session

Status: PROPOSED 2026-09-27, not armed. Prior design (periodic checkpoints) REJECTED by Codex design
review (`docs/specs/c103-prefix-drift.md`, review under `$STACK_WORKDIR/c103/codex_review.md`); this is
the narrowed successor. Needs an operator go in the session that executes it.

## The mechanism (measured M45 2026-09-23, confirmed in code 2026-09-27)

On every request under an asymmetric template (`is_asymmetric_rendering`: Qwen3-style templates render
history differently from the live turn — thinking stripped from prior assistant turns), the worker
(`generate/dispatch.py` ~1195, ~1370–1400): captures a snapshot mid-prefill at the anchor BEFORE the
latest user message, and after generation restores that anchor, trims the KV cache to it and stores
`token_ids[:anchor]` (`prompt_cache_state.update(anchor_token_ids, …)`). The session therefore retires
holding the prefix up to the start of its last user message; the worker log shows
`shrink-on-retire … offset=12` after a `[system, big-user]` opener. The next request re-prefills that
last user message + the re-rendered assistant answer + the new turn. Small last turns hide it (~53
tokens/turn in M45 leg A); a big one costs a full prefill of it once (8K: 9.7 s, 32K: 47 s, 64K: 126 s;
`session_cache.m45c2.json` r2). In opencode, tool results are user-role messages, so a large file read
or test log is re-prefilled once at the following request (leg-B rows: 70–280 tokens/turn on small files).

The policy is keyed on the TEMPLATE, not the architecture: a pure-attention model with the same template
pays the same (UNMEASURED — control below). The DeltaNet hybrid only makes the alternative harder: its
recurrent state cannot be trimmed, so retaining to prompt end needs a snapshot there.

Why not trust the session id and keep the generated tokens: the client's messages are the source of truth
(regenerate, edit, compaction, injected tool results), and the generated response (thinking + answer) is
not the history form the template expects (`preserve_thinking` exists for that trade-off; it costs context
and is off-template). The cache must end up in the shape the client will echo.

## Design (narrowed)

B1. **Prompt-end anchor.** In `generate/ar.py`, after the final prompt step and before decode (reviewer
   hook: after the last `_step()` ≈ line 707, before speculative/MTP lookahead), capture the DeltaNet /
   rotating snapshot at `prompt_end = initial_cache_offset + prompt_len`. Keep the existing
   before-latest-user anchor capture as-is (still needed for edits of the last user turn).
B2. **Retire to prompt end, in canonical form.** After generation, instead of restoring the before-user
   anchor: restore the prompt-end snapshot, trim KV to `prompt_end`, then prefill the CANONICAL history
   rendering of the assistant turn (the template's history form: answer content, no thinking, plus the
   assistant header/footer exactly as the client will echo it) and store `token_ids[:prompt_end +
   canonical_len]` with a snapshot at that end. Cost per turn: one small prefill of the answer text.
   Next request then matches byte-for-byte through the assistant turn and prefills only the new user turn.
   If the canonical rendering cannot be produced (unknown template shape), fall back to B1 alone
   (retire at prompt end: the last user turn is kept, the assistant turn is re-prefilled — still a win).
B3. **Divergence stays authoritative.** `find_prefix_length` + drop-after-divergence unchanged: an edited
   last user turn diverges before `prompt_end` and rewinds to the before-user anchor exactly as today.
B4. **Memory.** Two snapshots per session instead of one at rest (~154 MB each on the pick; reviewer
   sizing); `shrink-on-retire` semantics unchanged. Gate on FULL-STACK pressure (router
   `memory.pressure.*` events, swap), not a worker-only ceiling; the box logged 90.6% used / 1.9 GB swap
   with two sessions live (M45).
B5. **Scope.** Fork `../mlx-vlm` only; no router change; no serving-param change; default ON after
   acceptance, `--session-retain-prompt-end 0` to disable. Provenance: the cached path is already part of
   the serving-path fingerprint (`docs/serving-path.md`); bump its version so rows do not pool across it.

## Pre-registered acceptance criteria

- A1 Unit (fake caches): retire offset == prompt_end + canonical_len; canonical assistant tokens equal the
  template's history rendering for the same content; a diverging last user turn still rewinds to the
  before-user anchor; a diverging assistant echo (client sends different content) rewinds to prompt_end.
- A2 M45 leg C rerun on `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`: r2 `cached_tokens` ≥ opener
  length at 8K/32K/64K (today 12); r3/r5 unchanged; eviction leg unchanged.
- A3 Same leg on a pure-attention control (`Ornith-1.0-35B-mlx-uniform-4bit` or the C pick) before and
  after: quantifies the template-policy cost on dense models and proves the change is architecture-neutral.
- A4 opencode leg B (`session_cache_probe --legs B`, daily-driver flags): per-turn prefilled tokens fall to
  ≈ the new user turn only; a large tool result (add a 20K-token file read) is NOT re-prefilled next turn.
- A5 Output parity: 40 unchanged output pairs vs pre-change at the deployed profile (C84 form), MTP ON and
  OFF; tool-continuation, vision and three-turn reuse smokes (C85 suite) pass; full fork suites pass.
- A6 Memory: worker `footprint` and router pressure events with two sessions live, full stack up: no new
  CRITICAL beyond the M45 baseline count; swap not higher than baseline.
- A7 Cold review (Codex, read-only) against A1–A6 before the fork commit lands; live A2–A6 after the bump.

## Not in scope

Periodic mid-prefix checkpoints (rejected), cross-session reuse (never), `preserve_thinking` changes,
anything on the router.
