**Verdict: SHIP-WITH-RESIDUALS.** No BLOCKING finding for this commit’s narrow fix. Pytest requires temporary writes unavailable in this read-only sandbox; review was by reading.

Paths below are relative to `benchmark/bench/`.

**B1 — RESIDUAL: mixed-pair detection is conditional.** `provenance.py:677–694`, `run_retrieval.py:130–142`, `run_reasoning.py:205–217`.

Interruption between renames—or an ordinary `gather` exception followed by result-only publication—leaves NEW result/OLD manifest. The checker returns:

- `False` when the old manifest has a digest and result bytes differ.
- `None` for a legacy manifest without a digest.
- `True` if result bytes are identical, even if the runs’ provenance differs.

Thus the specific OLD-result/NEW-manifest defect is closed for process interruption, but the helper’s unconditional “reports as False” claim is wrong. Consequence: content equality cannot establish run identity. Fix: qualify that claim; preserve staged output on `gather` failure; use a shared run identifier or atomically selected generation directory if run identity must be guaranteed.

Canonical-file interruption audit (`R/M` = result/manifest; individual renames are atomic):

| Interruption point | Pre-existing pair | No prior pair |
|---|---|---|
| Result-stage open, write, flush/close | OLD R/M | Neither |
| `gather`, digest calculation, manifest-stage open/write/flush/close; before first rename | OLD R/M | Neither |
| First rename, before/after its atomic transition | OLD R/M → NEW R/OLD M | Neither → NEW R only |
| Between renames; second rename fails | NEW R/OLD M | NEW R only |
| Second rename completes; subsequent interruption | NEW R/M | NEW R/M |

A late `ServedConfigError`, including interruption during quarantine, leaves canonical R/M unchanged; reasoning’s journal is separately quarantined. Ordinary `gather` failure terminates publication at the result-only state. These are process-interruption guarantees; no `fsync` establishes power-loss durability.

**B2 — RESIDUAL: malformed manifests can appear merely legacy.** `provenance.py:677–679`.

Valid JSON such as `[]` returns `None`, not the documented damaged-manifest `False`; a digestless manifest also returns `None` without checking result readability. Consequence: callers cannot distinguish these failures from legacy provenance. Fix: validate manifest shape and result existence before the legacy return; add tests.

**B3 — RESIDUAL: incomplete fault coverage, not reimplemented drivers.** `tests/test_pair_publication.py:32–103`.

Tests call both real `main()` functions and real publication code, mocking model activity and injecting rename/digest failures. They omit ordinary `gather` failure, fresh-output interruption, manifest-write failure, and identical-result/different-provenance cases. Add those cases; the “any exception” test name overstates coverage.

**B4 — Compatibility and downstream audit.** Successful result content, filenames, journal writes, and manifest fields are unchanged except the two added keys. `--resume` still reads matching records from `reasoning[.<tag>].partial.jsonl` (`run_reasoning.py:123–130`).

No production caller invokes the checker. No repository consumer found silently consumes these ladder pairs: graders/comparators use `.jsonl` results (`generate.py:95`, `grade.py:66`, `compare.py:139`); the scoreboard also selects JSONL, and `scorecard.py:20` accepts capacity records directly.