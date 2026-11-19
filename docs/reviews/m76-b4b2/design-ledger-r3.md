# B4b-2 design review — ledger (round 3 of 3, final verify)

Members as round 2 (Sol / GLM fresh, Sonnet resumed `213d11f6`); all exit 0, read-only, checkout at `7c7a4bc2` (v1.3). Raw:
`design-verify-{sol,glm,sonnet}-r3.md`. Round-2 items: Sol all resolved except P11 (residual, N1 below); GLM N1–N7 resolved; Sonnet 13
resolved, G1 / G4 partly (N2–N5), G7 a literal mismatch (N6). GLM and Sol read the pilot's real javascript events (scratch copy);
Sonnet could not (evidence-only).

| N | finding (raised by) | disposition | change in v1.4 |
|---|---|---|---|
| N1 | jest / `npm test` / `node <file>` execute model-authored code that can write a denied file no event shows; eligibility cannot prove the only rejected delta is the lock file (Sol P11, GLM F2) | OPEN → operator (round 3 of 3) | v1.4 removes `node <file>` and narrows jest to an allowlist (N3); the remaining residual (solution code run by the tests writing files) is documented in §3.7; see the escalation table. |
| N2 | the pilot's real `npx jest ./*` would be refused by "extra script arguments" (Sol P13, GLM F1, Sonnet H3) | ADOPTED | positional test paths / globs matching only prepared or accepted files are allowed; both pilot commands quoted verbatim and tested. |
| N3 | jest flags are a denylist (`--coverage`, `--outputFile` write files) (Sonnet H1) | ADOPTED | an allowlist: `--silent`, `--verbose`, `--runInBand`, `--no-cache`; install flags allowlisted too; `CI=true` assignment stays refused. |
| N4 | the write-tool list is open (Sonnet H2) | ADOPTED | a tool allowlist; any other tool name → stays tampered. |
| N5 | the work root and path normalisation are unnamed (Sonnet H3) | ADOPTED | the `…/oc-<slug>/<slug>/` prefix of the scrubbed paths; a path outside it → stays tampered. |
| N6 | the regrade-record enumeration contradicts the pilot-only acceptance (GLM F3) | ADOPTED | records for every session; required for confirmatory sessions (missing → incomplete); a diagnostic session's missing record → `regrade pending`. |
| N7 | literal mismatches: `compute_kv` signature, the chain fields for the orphan exemption, item order, `ph.seal` (Sonnet H4) | ADOPTED | fixed. |

## Escalation (round 3 of 3)

| finding | recommendation |
|---|---|
| **N1 — the regrade's proof is evidence, not certainty.** The final tamper receipt records no reasons and no file list, so eligibility rests on the recorded tool calls. The tests themselves run the model's solution code, and that code could create a forbidden file (for example a config) that no recorded event shows. An eligible row regraded on its accepted files would then hide a real tamper. | **Accept the documented residual and regrade (C368 as ruled, with v1.4's narrowing).** A model whose solution writes a forbidden config file at test time is exotic, both arms run the same procedure, and a regraded pass still means the model's own files pass the original tests on a clean tree. *Counterpoint:* the residual can only turn 0s into 1s, never the reverse, and it is invisible in the data. The clean alternative, rerunning the javascript items with the forward fix, is not available within this campaign: it rotates the tg2 probe identity, and the rules forbid pooling it with the other languages, so it would mean rerunning the whole decider (≈ 13–20 h). |
