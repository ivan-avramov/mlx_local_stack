# S27 robustness design review — ledger (round 1 of 3)

Members (read-only, `checkout` = a scratch clone of `main` at `46aeb7d9`): Sol (`gpt-5.6-sol-high`, cursor-agent `--mode ask`) 7;
GLM (`glm-5.2-high`, same) 7 + scope request S1; Claude Sonnet (`claude-sonnet-5-5`, `claude -p`, session `88a8a519`) 12. All exit 0.
Raw: `design-opinion-{sol,glm,sonnet}-r1.md`. §12 (push binding) was added after the clone; it is reviewed in round 2.

| R | finding (raised by) | disposition | change in v1.1 |
|---|---|---|---|
| R1 | a retry of post-outcome faults is outcome-correlated and arm-dependent (kills happen on failing items; race rates differ by arm) (Sol P3, GLM F2, Sonnet P2) | OPERATOR → C372 | §5.1 / §5.2: rerun only PRE-outcome faults; post-outcome accounting faults keep the outcome, flagged, tokens / latency descriptive; per-arm counts + missing-in-both sensitivity. |
| R2 | reconciliation failures are too broad a harness-fault class; genuine accounting mismatches must not be retried away (Sol P1) | ADOPTED via R1 | §5.2 / §5.4: no rerun after an outcome; unexplained worker / receipt / backend inconsistency = integrity. |
| R3 | an uncertain owned cleanup followed by an immediate rerun removes a protection; the abort route is unspecified (Sol P2, Sonnet P3) | ADOPTED | §5.1 / §5.3: rerun only after a second independent scan proves certain + worker settled; else HOLD, never continue. |
| R4 | the late-record offset proof is too narrow / wrong direction; trailing-failed variant; `signal_offset None` (Sol P4, Sonnet P4, GLM F5) | ADOPTED | §4.1–4.2: `events_size_at_count` and END offsets; the trailing-failed variant; the order field incl. `no_signal`; the sgf-parsing events checked before the freeze. |
| R5 | `foreign_new` and the cleanup record are lost on a successful item (Sol P5, Sonnet P7) | ADOPTED | §3.6: `row.cleanup_status` per item. |
| R6 | the CPU alert cannot tell owned from foreign processes (Sol P6) | ADOPTED | §8.1: pid / sid / start / argv + ownership class; `unknown` never treated as foreign. |
| R7 | the 4th-DNF pause has no race-free path; no PAUSED leg state (Sol P7, GLM F3) | ADOPTED | §5.5 synchronous in the chain at the barrier; §5.6 `PAUSED` in `LEG_STATES` / `classify_leg` / the harvest table. |
| R8 | the P426 chain has no rerun machinery; dispositions, `slot_table`, ledger, cache reset, settle (GLM F4, Sonnet P1) | ADOPTED | §5.6 names every site; §5.1 cache reset + settle before a rerun. |
| R9 | the order-tolerant positives rule must keep the loop descendant check and use strict conditions + a distinct verdict (GLM F1, Sonnet P6) | ADOPTED | §4.3 `PASS_NO_INFLIGHT` with the conditions; descendant kill kept. |
| R10 | a denied environ / cwd read on a foreign daemon still makes cleanup uncertain (GLM F6, Sonnet P8) | ADOPTED | §3.2 test order; unclaimed + denied → `foreign_new unreadable`. |
| R11 | session-id ownership kills unrelated processes when the probe is not a session leader; path-only kills (Sonnet P5) | ADOPTED | §3.1 leader-only; §3.2 corroboration; §3.3 one kill-and-verify loop. |
| R12 | HOLD vs the outer `Sequencer.supervise` deadline; re-verify on resume; reuse PAUSE (GLM F7, Sonnet P9) | ADOPTED | §8.2. |
| R13 | the cleanup receipt change breaks existing records and validators (Sonnet P10) | ADOPTED | §3.5 schema v2, schema-1 rule kept, `unknown` kept, `foreign_new` capped. |
| R14 | C365: the cancel must clear the queue, apply only with a primary exception, bound the join (Sonnet P11) | ADOPTED | §6. |
| R15 | symlink targets may carry a box path; nested lock files (Sonnet P12) | ADOPTED | §7. |
| R16 | an escaped `setsid` agent child is never killed (GLM S1, scope request) | OPERATOR → C372 | accepted residual, §3.7. |
