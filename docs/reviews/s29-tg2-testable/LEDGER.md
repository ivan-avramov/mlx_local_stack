# S29 tg2 testable — four-eyes record (PLAN M85 phase 1; C389, C390)

```
[four-eyes 0.7.0] outcome: completed; mode: strict (relaxes an anti-cheat guard; new tg2 identity)
designer, implementer, fixes: Claude Code: claude-opus-5-5 (designer); claude -p claude-opus-5-5 1bf38129 (implementer); fresh claude-opus-5-5 sessions for fix rounds 1–2
test-writer: claude -p claude-sonnet-5-5 ee762fe9; continued (deliveries 1–3); frozen 2026-11-23T22:36:46Z, candidate revealed after; amended + refrozen 2026-11-24T07:42:19Z (5 invalid tests, adopted-defect tests)
panel: design opinion r1, change verify r2, verify r3 — sol: cursor-agent gpt-5.6-sol-high, briefed, fresh sessions (runtime cannot resume); review budget used (3 of 3)
shared: implementer, fixes, test-writer, designer are Anthropic; not covered: their shared blind spots beyond the three Sol rounds
go / accept: the designer (C390); commit: the merge commit; push: the operator's word
```

Spec `docs/specs/s29-tg2-testable.md` v1.1. Baseline `cd334f773`.

## Findings

| id | source | finding | disposition |
|---|---|---|---|
| D-P1 | Sol design r1 | "none skipped" vs the grader's frozen JS optional leaves | adopted (graded-leaf parity) |
| D-P2 | Sol design r1 | lookup denies by glob are evadable | adapted: any case a cooperative agent writes, compound commands; no network sandbox |
| D-P3 | Sol design r1 | no acceptance for the new identity | adopted (I1) |
| D-P4 | Sol design r1 | zero-token proof unavailable | adapted (K1 = accounting class) |
| D-P5 | Sol design r1 | "protected files unchanged" ≠ no tamper | adopted (the production tamper check) |
| D-P6 | Sol design r1 | K2 / V1 beyond scope | adopted (split to `s29-main-small.md`) |
| D-P7 | Sol design r1 | per-item stub failures unsatisfiable | adopted (compilable known negative per language) |
| C-P8 / TW F-A | Sol r2, test-writer | degit / npm `github:` / org API lookups open | adopted (fix 1) |
| TW F-B | test-writer | anchored CLI denies miss chained commands | adopted (fix 1) |
| C-P10 / TW F-C | Sol r2, test-writer | over-match on local names | adopted (fix 1) |
| C-P9 | Sol r2 | K1 must bind the failure to the item's request | adopted; fix 2 binds by uid or, on today's uid-less worker log, by the serial in-flight evidence (proven on the real S29-P16 window) |
| TW §1 | test-writer | 5 frozen tests invalid (JS docker without network, rust cfg-feature counts, cpp comment lines) | amended by the test-writer, refrozen |
| V3-P1 | Sol r3 | arbitrary mixed case (`ExErCiSm`) not denied | **open after r3 → operator**: rec residual (obfuscation is outside the cooperative-agent threat; opencode's matcher is case-sensitive, a fix needs a normalising plugin) |
| V3-P3 | Sol r3 | rare harmless commands still denied (`curl -o problem-specifications.json <docs>`, `cat exercism.org.txt`) | **open after r3 → operator**: rec residual (false denials, rephrasable, never a build or test command) |

## Acceptance

- Frozen tests: 720 / 720 on candidate 3 (baseline 305 / 720).
- Related modules: 4629 / 4632 (2 = a cross-copy docker collision, root-caused, pass alone; 1 env skip).
- Real record: the S29-P16 window → `accounting` (serial in-flight binding).
- Whole universe (designer, docker): 149 / 149 items run exactly the graded leaves locally with the reference (javascript's two frozen optional leaves stay skipped, as specified); the real grader grades 147 clean — `rust/alphametics` and `rust/poker`'s Exercism reference solutions add crates outside the offline allowlist (a reference artifact; local parity held). `universe-acceptance.json`.
- Not yet: a real opencode session (no binary in the copies) — pre-registered as a phase 2 positives acceptance before any decider leg (S29-P29).


Note (2026-11-24): after the final freeze, the repo hooks' exception markers (`allow-shorthand` for the C++ / English word "static", `allow-pii-pattern` for the example local name `exercism.local`) were appended to 6 lines of the frozen tests, in comments / docstrings / list lines only; the frozen tests were re-run after it (no behaviour change).
