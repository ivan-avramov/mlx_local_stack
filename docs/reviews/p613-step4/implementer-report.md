# P613 step 4 — implementer report

All three done criteria are met on the committed data. Nothing was committed or pushed.

## Files changed
- `benchmark/bench/p426_signals_divergence.py` (new; I checked the name was unused first): `a7_divergence(results_root, b8, evidence_ref, repo)`, plus `parse_messages`, `first_divergence`, `flags` and `render_md`.
- `benchmark/bench/p426_signals.py`: `compute_all` gains `evidence_ref` / `repo`. It also gains the `STEP4_VERSION` / `FINAL_STATUS` constants, a `_final_ready` check, the header lines for the evidence ref and final state, and the section rendered right after §4.5. The CLI gains `--evidence-ref` and an optional `--repo`. The Pending list renders `- none` when it is empty.

## Commands (from `benchmark/`) and their results
- `../.venv-bench/bin/python -m bench.p426_verify all --results-root results/p426 --rows-root results --repo .. --out ../.p613-material/out/B8.json` → `verify rc=0`; `B8 identical to committed`
- `… -m bench.p426_signals all --results-root results/p426 --rows-root results --b8 results/p426/B8.json --panel results/p426/panel --evidence-ref b6ec7819 --out-md ../.p613-material/out/r{1,2}/SIGNALS.md --out-json …/SIGNALS.json` → `signals r1 rc=0`, `signals r2 rc=0`; `r1 == r2 byte-identical (md + json)`
- The same command without `--evidence-ref` (writing to `out/noref/`) → `signals noref rc=0`; `noref == committed byte-identical (md + json)`
- No `/Users/` or `/home/` string appears in either output (grep count 0 / 0).
- Status line: `# P426 signals — FINAL — P426 certification evidence`. `header.evidence_ref` = `b6ec781939f970987b449d329aed1d46596c3da5`; `header.final` = `{ready: true, missing: []}`.
- Test command: `825 passed, 1 skipped in 637.63s (0:10:37)`, exit 0. I did not check which test was skipped. `bench/tests/p613s4/` doesn't exist yet, so the golden test marked `p613s4_golden` has not run.

## Golden table

| session | kind | contract | got |
|---|---|---|---|
| s1 | identical / environment / cutoff / generation | 18 / 24 / 1 / 0 | 18 / 24 / 1 / 0 |
| s2 | identical / environment / cutoff / generation | 17 / 25 / 1 / 0 | 17 / 25 / 1 / 0 |
| both | items | 86 | 86 |

- The two cutoffs are s1 `go/crypto-square` (k=2) and s2 `python/book-store` (k=1).
- The generation flag is not raised.
- 172 evidence inputs were added, so the sheet's `inputs` now has 1083 entries.

## Ambiguities and how I read them
- **P1 — events binding:** every events file must be bound through `HARVEST.json`: raw `sha256` equal to the row's value, and `published_sha256` equal to the bytes read. Step 3's code first accepts a direct hash match; I dropped that shortcut because the contract says "through HARVEST … else RefusalError".
- **P2 — events path:** the run id comes from the row's `final_tree.manifest`, using step 3's `_run_id`.
- **P3 — B8 key with no row (a DNF slot):** this refuses. The contract says "every planned key" but defines no kind for a key with no row. No such key exists in the current data.
- **P4 — what counts as "present" for FINAL:** every block of A1 / M1 / A2 / A3 / A4 is `accepted`, A7-s1 / s2 are `accepted`, `subjective` exists, and the divergence section is complete. If any is missing, the step-3 status stays and `header.final.missing` lists what is missing.
- **P5 — Pending section:** when the sheet is FINAL, I remove the `final sheet + recommendation` entry, so Pending shows `- none`. The MTP call is the operator's (C204) and is not generated, so I left it out of the sheet rather than keep it listed as pending.
- **P6 — the evidence ref:** I record the resolved full commit sha, both in the header and in the `evidence:<ref>:` input keys, not the short `b6ec7819` that was passed in.
- **P7 — first differing tool for `environment`:** I take it from the first differing entry of the two sorted env lists. When `gen` is equal, both lists have the same sorted (tool, input) order, so that entry names the same tool on both sides.
- **P8 — the generation flag:** besides `divergence.flag`, it is also added to the sheet-level `flags` list as `a7_divergence_generation` (listed, never a veto). It is empty on this data.
- **P9 — `--repo`:** this is an extra, optional flag not in the contract. It defaults to the git tree that contains `--results-root`, so the contract's command works as written.
