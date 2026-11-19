# B4b-2 design review — ledger (round 2 of 3, verify)

Members as round 1: Sol and GLM fresh sessions (cursor-agent cannot resume; told this is a verify of their own r1), Sonnet resumed
(`213d11f6`, `claude-sonnet-5-5`); all exit 0, read-only, checkout at `f1740a19` (spec v1.2). Raw: `design-verify-{sol,glm,sonnet}-r2.md`.
r1 status: Sol P1–P10, S1, S2 resolved; GLM F1–F9, Q1–Q5 resolved; Sonnet 14 resolved, F5 / F14 partly (folded into G7). This is a
check of the diff, not independent discovery.

| M | finding (raised by) | disposition | change in v1.3 |
|---|---|---|---|
| M1 | §3.7 eligibility cannot prove the lock file was the sole tamper cause: `npm install <pkg>` edits `package.json` unnamed; a new denied file (e.g. `babel.config.js`) is outside `protected_manifest`; shell commands unparsed (redirects, pipes, heredocs, `jest -u`) (Sol P11, GLM N1 / N2, Sonnet G1) | ADOPTED | one pure `a8_regrade_eligibility`: tool writes only to accepted final-tree paths; every shell call parsed into a closed allowlist of simple commands (harmless redirections `>/dev/null`, `2>/dev/null`, `2>&1` only; no substitution / heredoc / variables); a bare flags-only install required; anything else stays tampered and is listed. The pilot's two real commands stay eligible. |
| M2 | panel selection reads the raw `passed` (Sol P12, Sonnet G3) | ADOPTED | one effective accessor `a8_passed` for signals, B8-A8 counts, panel selection and packets. |
| M3 | B8-A8 cannot tell a missing regrade record from a non-eligible row; re-derivation; non-scored outcomes; order (Sonnet G2) | ADOPTED | a sealed record for EVERY final-tampered javascript row; B8-A8 enumerates them (missing → incomplete), re-derives eligibility from the events on the evidence ref (mismatch → refuse); a non-scored regrade outcome aborts; §7.5 order. |
| M4 | accepted-files list from `main`, bytes from `evidence` (GLM N3) | ADOPTED | wording. |
| M5 | `passed` / `converged` wording (GLM N4) | ADOPTED | `converged` is the row's; `regraded_passed` the regrade's. |
| M6 | "both counts" undefined (GLM N5) | ADOPTED | per arm: tampered, eligible, regraded to passed, stays tampered (listed). |
| M7 | the draw (and evidence ref, image) are unnamed inputs; `check_tg2_p426` raises `TransportAbort`; `v8.arms` (GLM N6, Sonnet G6) | ADOPTED | §1 inputs list; the abort caught → a REASON; `v8.arms == ["n16","x"]`. |
| M8 | a harvested attempt missing `schedule.json` / `chain.json` (GLM N7) | ADOPTED | contradictory → refuse (a missing attempt stays incomplete). |
| M9 | the orphan-manifest clause may reject a rerun / DNF slot's manifest (Sonnet G4, hypothesis) | ADOPTED (scoped) | orphan = a manifest for an item with a row that names another run id, unless the chain records that run id as a discarded DNF / rerun slot. |
| M10 | `check_recheck_doc` is a sequencer method; missing recheck-s2 (Sonnet G5) | ADOPTED | re-implemented over the same fields (no runner edit), tested against the sealed shape; a missing recheck-s2 → only the label incomplete. |
| M11 | base-sha / inputs verification, signatures, latency seal and absence, final-tree stem (Sonnet G7) | ADOPTED | §4.4 `compute_kv(…, b8_a8, b8_a8_sha256)` with base-sha + input re-hash; latency sealed with `ph.seal`, absent → `latency: incomplete`; the `wave2.tg2` stem stated. |
| M12 | Sol P10 (the narrower Cargo rule) — Sol r2 accepts the adapted disposition | CLOSED | — |
