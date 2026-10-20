Cold CODE review — ROUND 2 OF 3 (at most 3 rounds, then the operator decides open findings). Fork `mlx-vlm` branch
`p369-v13` HEAD `d36d33c5`, on top of the reviewed P405 head `64afc7dd`. Workspace `../mlx-vlm` at `24551869`; read with
`git show d36d33c5:<path>` (read-only). Production code is UNCHANGED (`git diff 64afc7dd d36d33c5 -- mlx_vlm ':!mlx_vlm/tests'`
must be empty — verify). Round 1 reviewed `64afc7dd..5f407d5d` and returned `NOT CLEARED M1–M10` (findings inline below).
This round reviews the fixes `5f407d5d..d36d33c5` (diff inline below), then the operator-accepted P369 run plan v13
(`docs/specs/p369-phase2-run-plan.md` in the STACK repo, not the fork — its text is inline below; C193; V17's wall cap
withdrawn by C194).

Fix map (red commit → green commit):
- M1, M2, M9, M10: `4a631d00` red → `e09a3d9b` green. M9 note: no dataset revision id exists for the reconstructed corpora on
  this box; each item now carries its axis's corpus CONTENT hash as the revision proxy, and `source_pick` is checked against
  `items_source(pick)` independently. Judge whether the proxy closes M9.
- M3: `4f6152b0` red → `19399f82` green.
- M4–M8: `34f31591` (M5–M7 harness fixes + M4–M8 tests) and `3e3cec09` (tests moved to the served shape: bf16, hidden 512,
  every linear + routed bank affine int4 / g64; the split-artifact test keeps its own float dims). All 16 MoE Metal tests pass;
  V3 (d) / M8: width-2 / width-3 MoE verify blocks equal sequential singletons bitwise (logits, selected experts, routed
  outputs, every cache leaf).
- `d36d33c5` (not a round-1 finding): the first full suite on `3e3cec09` failed one stale test — v13 V9 refuses a
  pick-less campaign in `Campaign.__init__`, and the H23 construction test still passed `pick=None`; the test now carries one
  pick, and a second test proves the refusal reads nothing.
- On `d36d33c5`: fork suite ×2 identical (6649 passed / 17 skipped, same skip set), 8 audits `--upstream-ref 952d4f6b`
  (deletions `--strict`) all OK.
- Declared refinement of plan V4 (unchanged from round 1): `--phase panel` produces the borrowed-panel counts through a
  count-only worker boot that LOADS weights but generates nothing; the result is reviewed into `borrowed_panel.json` before the
  entry's smoke.

Review adversarially: (1) does each fix close its round-1 finding completely, fail closed and avoid self-reference (expected
derived from the observed); (2) did a fix introduce a new defect or weaken an earlier guarantee; (3) do the new tests fail for
the right reason when the fix is reverted (red-first honesty) and prove their docstrings; (4) anything round 1 missed in the
touched code that would let a smoke or full run pass for the wrong reason.

Report each round-1 finding as CLOSED or OPEN (with why), then new findings N1 onward, each: severity, file:line, problem,
failure scenario, fix. End with exactly one line: `VERDICT: CLEARED` or `VERDICT: NOT CLEARED <ids>`. OUTPUT RULE: your FINAL
message must contain EVERY finding in full, then the VERDICT line.
