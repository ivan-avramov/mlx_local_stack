# Handoff — 2026-08-28 (M9 go + python legs COMPLETE; C36 landed; NO run live)

Single box (M5 Max 64 GB). **No run is in flight.** `caslca/Qwen3.8-27B-mlx-uniform-4bit`
is the resident model (router :8000 up, worker idle); unload before serving anything else.

## THE HEADLINE

**M9's first two legs are done, and `Qwen3.8-27B-mlx-uniform-4bit` leads the agentic axis —
decisively on python.** One session per arm, O39 protocol throughout (opencode 1.18.15
pinned, TMPDIR `$STACK_WORKDIR/scratch/octmp`, draft-OFF overlay served AND fingerprinted,
`deployed` profile, progress gate 300/3600/2), paired against the existing winner arms by
construction:

| opencode n=22/lang | go (O39 set) | python (M3 set) |
|---|---|---|
| `Qwen3.8-27B-mlx-uniform-4bit` | **16/22** | **20/22** |
| `Ornith-1.0-35B-mlx-uniform-4bit` | 11/22 | 19/22 |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` | 12/22 | 12/22 |
| `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` | — | 13/22 |

- **Python vs the B pick: discordant 8:0, McNemar exact p=0.0078** — a strict superset of
  the pick's solves, survives Bonferroni across the session's five pairwise tests, and the
  +36.4pp delta clears the n=22 MDE (~±27pp). The campaign's strongest agentic result.
- **Go: leads both winners directionally, not significantly** (6:1 p=0.125 vs the
  runner-up; 5:1 p=0.219 vs the pick).
- **Failure mode is honest**: every fail on both legs is a `stalled` gate-kill with zero
  file edits (the xhigh think-forever class) — no fast give-ups, no path-infidelity, no
  test tampering — and it stalls almost only where the winners fail too (`ledger` in go is
  the sole winner-passed miss). This is NOT the `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`
  pattern (its 9 python fails were all stalls, several on items others pass).
- Caveats: single-session arms (C30 order ±1–2 items). Python rows committed `1f6137a`;
  go rows at `$STACK_WORKDIR/m9/Qwen3.8-27B-mlx-uniform-4bit.opencode_go.jsonl` beside the
  winners' O39 arms. Dated entry: campaign-results 2026-08-28; mechanics: lab-notebook
  2026-08-28.

## C36 — found and fixed this session (RATIFICATION OWED)

Landing the handoff-directed durable config fix (registry `presentation: role: candidate`
for `Qwen3.8-27B-mlx-uniform-4bit` → configgen re-emit, verified reproducing the hand-edit)
exposed that the re-emit **silently dropped `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`**
from `benchmark/opencode_bench.json`: its carrier entry was hand-written in `bcc6d37` with
no registry presentation block — pre-existing drift. Fixed with the identical candidate-role
treatment (emission byte-reproduces the committed entry; client configs untouched; configgen
37/37); both blocks landed together in `bbbe365`. **The fix was applied without prior
proposal — the propose-before-fixing rule was knowingly stretched because both alternatives
(commit the drop / leave `configgen check` red) were worse; operator ratification is owed**
(open-questions C36; revert instructions there if rejected).

The `main_models.yaml` working tree still carries EXACTLY the four intentional local-path
overrides (drafter path + three local model paths) — verified re-applied after the clean
commit; `configgen check` passes on the working tree. The draft-OFF overlay
(`$STACK_WORKDIR/m6b/bench_overlay_draft_off.yaml`) was regenerated from the restored
working registry (2026-08-28 header, 0 active draft keys). The live
`~/.config/opencode/opencode.json` still carries the BENCH config (daily backup:
`$STACK_WORKDIR/opencode.json.probe-backup`) — restore it when M9 fully closes.

## NEXT SESSION

1. **M9 rust/java/javascript legs — BLOCKED on the operator's seeded-draw rule** (which
   items per language, how drawn; O39's 22-item go set was the C21 replication set, but the
   remaining languages have no pre-registered draw). Decide, then ~3×22 items × up to 4
   models under the same protocol.
2. **The M12 d128k-vs-more-M9 scope call** (operator): a d128k block costs ~25 h at
   observed rates; mind the `0.8 × (cap − prompt)` clamp window.
3. C30 (session-variance bound) and C31 (deferred medium arm) unchanged.
4. If the operator wants power on the python 8:0 result: a second session per arm
   (ABBA) is the cheap extension — C30's material doubles as the design input.

## Standing state

- **PUSHED through `027dd38` (2026-08-27, operator-approved). LOCAL since (not
  push-approved):** `75ebd63` (prev handoff), `bbbe365` (C36 + presentation blocks),
  `1f6137a` (M9 python data), and this session's docs commit. Never push without in-turn
  approval.
- Working tree: the four intentional `main_models.yaml` local overrides (NEVER commit) +
  older untracked m23-era result files + `transcript.md`.
- Bench-router invariants unchanged and enforced: draft-OFF overlay + fingerprint
  cross-check (C35), `MLX_VLM_CACHE_SESSION_MAX=2`, APC absent, verified at the worker.
- Open operator items: **C36 ratification**, C30, C31, the M9 draw rule, the M12 scope
  call. Next O/C number: **C37**.

**Order of resumption: this file → `docs/PLAN.md` → `docs/open-questions.md`.**
