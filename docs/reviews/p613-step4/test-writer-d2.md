**Verdict: merge.** All 12 failing frozen tests fail because my tests are wrong, not because the candidate is. I found no defect in the candidate. Two of its choices are worth the operator's attention (P4 and P5 below).

I applied `candidate.diff` and left my tests untouched (confirmed identical to `frozen-d1/`). I ran no new tests beyond the two commands you listed, except throwaway probe scripts I deleted.

## What ran
- **`bench/tests/p613s4`:** 64 passed, 12 failed, 1 skipped, in 278.62s. The skip is `test_golden_committed_sheet_is_the_final_output`, which skips until the final sheet is committed.
- **Regression set** (`p613`, `p613s2`, `p613s3`, `test_p426_panel.py`, `test_p371_r7_consumers.py`, `test_p426_wave1.py`): 825 passed, 1 skipped, in 625.63s. The skip is the step-2 golden "committed sheet is still the step-1 sheet".

## The 12 failures: all test bugs

**P1 — 11 tests, `test_harvest_binding_refused` (10 cases) and `test_unparseable_events_refused` ("no refusal was raised").**
- My premise was wrong. Editing `HARVEST.json` and re-running B8 does not leave the pair accepted. B8 rule 5 hash-pins HARVEST in the dossier, so B8 rejects the pair: "dossier arms.on.harvest_sha256 … != HARVEST.json …". I reproduced this for all five edit modes.
- The candidate then reports that session as `rejected by B8`, with `complete: False`. That session is never compared, so the section is incomplete and the sheet cannot become FINAL. The contract says "B8-accepted pairs only", and step 3's `a7_select` handles a rejected pair the same way.
- My earlier check only confirmed that re-running B8 did not raise. My reference implementation had ignored B8 acceptance, which is why it passed.
- The binding code is correct. I reached it by editing the attempt in memory and calling `_events` directly. It raises `RefusalError` for each of these:
  - wrong `published_sha256`;
  - wrong raw `sha256`;
  - duplicate record;
  - missing record;
  - raw sha used as published sha;
  - a row `evidence_sha256.events` that disagrees with HARVEST;
  - a record whose `destination` is not `evidence`;
  - a non-JSON line;
  - invalid UTF-8.
- Consequence for coverage: the frozen suite exercises only the "published bytes altered" binding path, not the HARVEST-record refusals. Those need a unit-level test on `_events`.

**P2 — 1 test, `test_golden_cli_final`, two defects in the test.**
- My `divergence_flags` helper matches any flag whose text contains "generation". The committed sheet already carries a `cross_wave` flag: "1 generation-path file(s) differ between Wave 1 OFF … main_models.yaml". The candidate's own flag list is empty (`divergence.flag = {raised: False, items: []}`).
- The test also expects the header ref and the `evidence:<ref>:` input keys to read `b6ec7819`, as passed. The candidate records the resolved full sha, `b6ec781939f9…5da`, in both places (172 inputs). The contract does not say which form to record. The hermetic tests pass because they pass a full sha.

## Review against the contract

| Point | Result |
|---|---|
| Classification | Matches the contract. `gen` and `env` are sorted multisets per message, the input JSON uses sorted keys, and messages are grouped by `messageID` in first-appearance order. Kind precedence is correct. Parallel completion order, key order and interleaving all pass. |
| HARVEST binding | Matches the contract; the direct-hash shortcut from step 3 is dropped, as the contract says. A missing or non-string row sha refuses. The run id comes from the row's manifest path. |
| FINAL rule | Needs every block of A1, M1, A2, A3 and A4 accepted, A7-s1 and A7-s2 accepted, the panel present, and the divergence complete. Otherwise the step-3 status stays and `header.final.missing` lists the gaps. `--evidence-ref` without `--panel` is never FINAL (tested). |
| Determinism | Byte-identical regeneration passes in the hermetic worlds, from a copy of the repo, and on the committed data. Inputs are sorted. |
| No `--evidence-ref` | Byte-identical to the committed step-3 sheet at `e8383713` (golden passes). |
| Golden counts | s1 18/24/1/0, s2 17/25/1/0, 86 items, no generation flag. The CLI on the committed data gives rc 0 and status FINAL. |

## Observations for the operator
- **P3 — most `environment` items are likely output noise.** I probed the committed data: 46 of the 49 `environment` items stop differing if digit runs in tool output are masked. That includes timings and counts, so some could be real count differences. It is the contract's rule working as specified, not a candidate bug. Read the 49 as an upper bound on environment-driven divergence.
- **P4 — the `cutoff` `k`.** The candidate sets it to the shorter list's length (s1 `go/crypto-square` k=2, s2 `python/book-store` k=1). The contract does not fix it, and my tests do not assert it.
- **P5 — the "Pending" section.** When the sheet is FINAL the candidate removes "final sheet + recommendation", so Pending reads `- none`. Whether the generated sheet should still list the MTP call is the operator's decision (C204).
- **P6 — extra flag.** The candidate adds `--repo`, which is not in the contract. It is optional and defaults to the repo containing `--results-root`.

No commits, pushes or resets. No files written outside the copy's `benchmark/bench/tests/p613s4/`; the throwaway scripts I added there are deleted. A `__pycache__/` directory remains there.
