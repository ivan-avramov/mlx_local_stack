P1 — Resolved. A8 now uses separate `B8-A8.json`; A1–A7 remain bound to byte-identical `B8.json`.

P2 — Resolved. The pinned polyglot checkout is an explicit input, validated against `polyglot_sha` and `inputs_sha256`; reconstructed prompts must match recorded prompts.

P3 — Resolved. §6.2 correctly separates the main-branch manifest from evidence-branch objects/events.

P4 — Resolved. §3.3 validates every non-DNF row, rejects duplicate/orphan manifests, and exempts DNF slots.

P5 — Resolved. The sealed `exec_latency.json` is B8-A8-bound with required fields and per-leg-window reporting.

P6 — Resolved. §5 reuses `check_recheck_doc`, binds selected attempts and simulation report, and implements the full s1 acknowledgement rule.

P7 — Resolved. §7 preserves byte identity without A8 and permits only the specified A8-present projections, including Holm adjustment.

P8 — Resolved. Reload comparisons are restricted to same-seed s1 items, with explicit seed equality.

P9 — Resolved. Per-language intervals now use `m76_rule.loss_bound` at `PER_SESSION_ALPHA`.

P10 — Resolved by the driver’s adapted disposition. Grader-accepted `Cargo.toml` changes remain visible in the panel diff rather than being silently treated as permitted.

S1 — Resolved. §3.6 requires `check_tg2_p426`, matching `chain.tg2_leg`, and the v8 frozen-record SHA.

S2 — Resolved. §3.6 binds reload to the first five s1 items per language.

P11

- Location: `docs/specs/m76-b4b2-a8-consumers.md` §3.7.
- Severity: major.
- Evidence: confirmed.
- Problem: Eligibility does not establish that `package-lock.json` was the sole cause of `tampered`. `protected_manifest` contains prepared non-solution files, not forbidden new files. Meanwhile `tg2_grade.tamper_reasons` rejects any forbidden new file, and `accepted_files` removes it from the harvested final tree. Thus an install plus `touch notes.txt`, or `npm install <package>` implicitly modifying `package.json`, can satisfy (a)–(c) and be regraded after the additional violation is discarded.
- Concrete failure scenario: An agent edits its solution, runs `npm install`, then creates a forbidden root file. The final grade is `tampered`; the events satisfy the specified test because the extra path is not in `protected_manifest`; regrading only accepted files produces a passing result and incorrectly changes A8.
- Proposed change: Define a strict event classifier that permits writes only to accepted final-tree paths plus package-manager creation of root `package-lock.json`. Reject all other state-changing shell calls; restrict install syntax to forms that cannot alter `package.json`, and reject redirections, compound commands, variables, or package arguments that defeat path inspection.

P12

- Location: §3.7 “signals read the regraded `passed`” and §6.2 `_a8_packet` selection.
- Severity: major.
- Evidence: confirmed.
- Problem: Only signals are required to consume the regraded result. Panel selection still says “both arms `passed`”, which literally reads the original rows where eligible lock-file cases remain `passed: false`.
- Concrete failure scenario: Both arms are originally `tampered` solely by package-lock creation and both regrade PASS. Signals score the item as 1/1, but the A8 panel excludes it as not both passing, omitting execution-passing outputs from the subjective family.
- Proposed change: Define one B8-A8 effective-passed value per row and require every downstream consumer, including A8 panel selection, to use it. Preserve the original outcome and regrade provenance separately.
