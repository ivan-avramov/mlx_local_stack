Cold CODE review — ROUND 1 OF 3 (at most 3 rounds, then the operator decides open findings). Fork `../mlx-vlm` (read-only), three
DEV-only builds off `494aea2c` (production diff empty in all three; review each with `git -C ../mlx-vlm diff 494aea2c <head>`):
(1) B4 / C203 `p426-b4-settings-match` (`5f2e4177` red, `bb064586` green): `dev/p369_phase2/registry_states.py` classifies the stack
registry on SETTINGS (strict parse: no CR, duplicate keys refuse; equal to the pinned fixture except each of four entries has all
or none of its MTP keys), `overlay_on` rewrites the LIVE text (commented MTP lines → the fixture's exact lines; a historical
`# draft_kind: suffix` note is disambiguated by value; ambiguity / unknown entry / wrong result refuses). Consumers:
`orchestrate.overlay_registry` / `Campaign.prepare`, `qualify`, `p400_perf_probe`, the opt-in live test, and the STACK's
`benchmark/bench/p426_overlay.py` (this workspace). The operator ruled C203 (`docs/open-questions.md`): comments must never
block a run; settings must. (2) B7 `p426-b7-qualify-off` (`df4bd719` red, `df5ebb38` green): `qualify.py --predictor {on,off}`
(`arm_for`), so the P426 M1 memory axis measures the MTP-certified entry OFF (committed registry; refused unless it holds the
entry MTP-OFF) and ON. (3) P429 `p429-leg-exit` (`e8ac5d94` red, `d3feb734` green): `p400_perf_probe` leg `os._exit(0)` after
the result is written (an interpreter-finalization segfault in a thread-local MLX compile-cache destructor, `docs/open-questions.md`
P429). Spec: `docs/specs/p426-fable-mtp-recert.md` §2 / §5 / §9 in this STACK repo. Gate: integration head `p426-s` `505f58f7`
fork suite ×2 6802 / 17, eight audits green.

Review adversarially: (1) B4 — can a settings change be classified as a valid state (YAML features: anchors / aliases, merge
keys, tags, types like `0.40` vs `0.4`, key order, list order, top-level keys), can the overlay restore anything but the fixture's
settings, can it refuse a legitimate comment-only edit, does every consumer still fail closed; (2) B7 — can an OFF leg measure an
MTP-ON worker or the ON overlay, gate / refusal gaps; (3) P429 — can `os._exit` lose the result or mask a failure (buffers,
partially written files, a failing leg exiting 0); (4) test gaps. Findings ids F1 onward (or say none), each: severity,
file:line, problem, failure scenario, fix. End with exactly one line: `VERDICT: AGREE` or `VERDICT: DISAGREE <ids>`. OUTPUT RULE:
your FINAL message must contain EVERY finding in full, then the VERDICT line.
