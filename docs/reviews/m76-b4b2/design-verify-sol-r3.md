P1 — Resolved. Separate `B8-A8.json` preserves `B8.json`.

P2 — Resolved. Polyglot inputs and reconstructed prompts are bound.

P3 — Resolved. Main manifests and evidence objects/events are distinguished.

P4 — Resolved. Non-DNF final-tree identity is fail-closed.

P5 — Resolved. Latency is sealed, bound, and optional only descriptively.

P6 — Resolved. Re-check documents bind attempts, simulation, seal, and acknowledgement.

P7 — Resolved. No-A8 byte identity and A8 projections are specified.

P8 — Resolved. Reload comparisons require equal seeds.

P9 — Resolved. Per-language bounds use `loss_bound` at `PER_SESSION_ALPHA`.

P10 — Resolved. Accepted `Cargo.toml` changes remain visible.

S1 — Resolved. Attempts bind schedule, leg, and frozen record.

S2 — Resolved. Reload keys bind to the first five s1 items per language.

P11 — Not resolved.

- Location: `docs/specs/m76-b4b2-a8-consumers.md` §3.7(b).
- Severity: major.
- Evidence: confirmed.
- Problem: The direct bypasses from round 2 are closed, but the allowlist still permits commands that execute arbitrary model-authored code: `node <accepted file>`, `npx jest`, and `npm test`. Command-name classification cannot prove their filesystem side effects. `tg2_grade.grade_item` checks tampering before executing tests and performs no post-execution tree check; the accepted-files manifest omits rejected paths.
- Concrete failure scenario: The model creates an accepted helper that writes `babel.config.js`, runs `node helper.js`, then runs bare `npm install` and tests. Every event satisfies §3.7, but the original row is genuinely tampered by the denied config file. Regrading only accepted files omits that file and can return PASS.
- Proposed change: Remove `node` from eligibility and require bound evidence of the unfiltered final-tree delta or original tamper reasons. Eligibility must prove the only rejected delta is root `package-lock.json`; otherwise the row stays tampered. Test-command names alone are insufficient proof.

P12 — Resolved. `a8_passed` is required for signals, counts, panel selection, and packets.

P13

- Location: `docs/specs/m76-b4b2-a8-consumers.md` §3.7(b) and §7.6.
- Severity: major.
- Evidence: confirmed from the recorded N16 pilot events.
- Problem: The allowlist permits `npx jest` without “extra script arguments,” but both N16 pilot shell calls invoke `npx jest ./*`. Thus the literal classifier refuses the pilot while §7.6 requires its real commands to be eligible.
- Concrete failure scenario: N16 `javascript/word-search` runs `npm install --no-audit --no-fund … && npx jest ./* …`. An implementation following §3.7 marks it `stays_tampered`, failing the real-record acceptance test and potentially rejecting the same pattern in confirmatory sessions.
- Proposed change: Define the permitted Jest arguments explicitly, including the recorded `./*` selector, while continuing to reject update/configuration flags and arbitrary selectors. Clarify that “extra script arguments” applies separately to `npm test`.
