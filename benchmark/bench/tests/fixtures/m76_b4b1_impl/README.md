# M76 B4b-1 implementer fixtures

- `tg2-grade-trees/`: recorded real `bench.tg2_grade` output trees (one per language and terminal outcome: `<lang>/<variant>/`
  holds `<lang>__<slug>.grades/seq-0001/`, `grading-private/` and the recorder's `result.json`). Copied verbatim, except
  `rust/flood/rust__say.grades/seq-0001/execute.stdout`, truncated to its first 4096 bytes (the original is the 16 MB output
  cap; its `index.json` sha256 no longer matches the copy).
- `tg1_golden.json`: the tg1 facts recorded on the unchanged baseline (`test_m76_b4b1_impl_golden_tg1.py`).
