# M76 B1 — test-writer delivery 2 + change review (four-eyes light, opinion) — ledger

Test-writer: Claude Sonnet `claude -p`, session `810e8ad3-e9e5-475e-a7d8-f8496cc60d8a` (continued); verdict fix then merge.
Panel: Sol (`gpt-5.6-sol-high`) and GLM (`glm-5.2-high`) via `cursor-agent --mode ask`, read-only snapshot (candidate applied, spec v1
+ errata v1.1, both reports, frozen tests); user instructions unconfirmed. Both exit 0, valid. Raw: `opinion-change-{sol,glm}.md`.
GLM answered the isolation / validity / edit-model questions: `u4` ↔ `f45` isolation holds; the edit model produces exactly the
specified registry text from the real entry.

| # | raised by | finding | disposition |
|---|---|---|---|
| 1 | implementer pt 1, TW F1, Sol P1, GLM F1 (blocker) | the mode proof's exit − creation deltas are ≈ 0 on a real leg (`run_capacity` gathers after the ladder) | **adopt** (errata v1.1 item 1: absolute exit counters; fix round) |
| 2 | Sol P2, GLM F2 (major) | `MLX_VLM_DRAFT_KIND` / `MLX_VLM_DRAFT_MODEL` neither stripped nor checked on XO | **adopt** (errata v1.1 item 4, from the M77 review; fix round) |
| 3 | TW F3, Sol P6, GLM F3 | trigger line bolds the whole phrase | **adopt** (errata item 3; fix round) |
| 4 | TW F2, GLM F4 | preflight records campaign-checked beyond spec v1 | **adopt into the spec** (errata item 2); the frozen fixtures stamp them (test-writer) |
| 5 | TW F4 | trigger scope ambiguous | **spec clarified** (errata item 3: V / X decode flags at 131,072 / 260,096) |
| 6 | TW F5, GLM F6 | `f45` wall estimates are guesses; 40 min would time out a 76-min leg | **adopt**: defaults N16 25 / X, V, XO 76 min; the smoke sets `--expected-rung-seconds` |
| 7 | TW F6, Sol P8, GLM F5 | `u4` edit model now refuses a missing key on every edit | **accept, documented** (reachable only with a malformed registry; `u4` golden unchanged) |
| 8 | TW F7 | missing self-test line on X / V / XO recorded, not failed | **accept** (secondary record by spec) |
| 9 | Sol P5, TW cause A | frozen fixtures write preflight records without `campaign` | test-writer amends its fixtures (delivery 3) |
| 10 | Sol P7, TW cause B | frozen registry test searches the first `kv_bits: 4` in the file (the `u4` entry); other cause-B defects (argparse exit, mkdir, trigger regex) | test-writer amends (delivery 3) |
| 11 | Sol P3 (major) | `prepare` not idempotent across an interruption between `worktree add` and the arm commit | **decline here — pre-existing** (same code path ran for `u4`); fails closed (refuses as divergent); own proposal S22-P16 |
| 12 | Sol P4 (major) | a SIGINT between the dossier rename and `LAST_LEG_END` lets a resumed leg skip the 600 s idle | **decline here — pre-existing**; own proposal S22-P16; operating rule until fixed: after any interrupted run, wait 600 s from the interruption before resuming |
