# P369 phase-2 — Cursor gpt-5.6-sol-high confirming review, OPERATOR-ORDERED round 5 (E8 / E9 fix; fork `p369-mtp` `0d06bb0c..f0b41d44`, 2026-10-19)

Prompt: `round5-e8.prompt-head.md` + the round-4 output + `git diff 0d06bb0c..f0b41d44`; `--mode ask`, stream-json — the `result` text verbatim:

P1 — Production isolation is confirmed: `git diff --exit-code 4e6d0e03 f0b41d44 -- mlx_vlm ':(exclude)mlx_vlm/tests'` returned 0. The schedule counter is per criteria object, so MTP’s shallow simulation copies do not advance the real instance’s recorded position; I’m tracing the terminal-token and cross-load paths before deciding clearance.P2 — E8: RESOLVED

- OFF consumes the real pending pop, records `(next_position, token)`, and returns `None`, preserving ON replay tokens (`dev/p369_phase2/observe.py:339-351`).
- ON/OFF schedules are compared below the emitted length (`dev/p369_phase2/compare.py:108-113`).
- ON/OFF1 mismatch becomes neutrality FAIL; OFF1/OFF2 mismatch becomes C1 ABORT (`dev/p369_phase2/worker.py:1152-1172`, `dev/p369_phase2/orchestrate.py:914-923,483-490`).
- C2 compares its OFF schedule against persisted OFF1 evidence (`dev/p369_phase2/worker.py:1177-1199`, `dev/p369_phase2/orchestrate.py:1905-1923`).

P3 — E9: RESOLVED

Exact cross-load/triple name equality is required before comparison (`dev/p369_phase2/orchestrate.py:559-564`). Extra or missing names raise `MalformedEvidence`.

P4 — Adversarial edge cases

- The counter represents the next intended output position: after processing the first token it is `1`. First-token forcing is therefore recorded correctly.
- MTP’s shallow criteria copies have distinct identities, so simulated calls cannot advance the real instance’s counter (`mlx_vlm/speculative/mtp.py:617-625`, `dev/p369_phase2/observe.py:337-356`).
- Ignoring positions `>= len(tokens)` is correct: those pops cannot emit. ON bookkeeping separately rejects anything except one position exactly at the length boundary under a length finish (`dev/p369_phase2/compare.py:86-105`).
- A stop-terminal pop likewise cannot affect output. On the inline path, stopping prevents the generator from resuming to pop; any backend that pops before terminal filtering records position `n`, which is correctly excluded.
- Missing or malformed C2 forced evidence cannot pass: worker failure or `exact_bool` aborts evidence processing.

P5 — E10 onward: no findings. I found no new path allowing PASS without the claim.

Production isolation is verified: `4e6d0e03..f0b41d44` is empty under `mlx_vlm` excluding tests. Checkout HEAD is `24551869`; reviewed object is `f0b41d44`.

VERDICT: CLEARED
---

Lead: `f0b41d44` is the `--reviewed-head` (fork suite 6418 / 17 / 0 twice, eight audits green, production diff empty).
