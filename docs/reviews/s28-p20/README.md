# S28-P20 cold read

Brief: the diff of `benchmark/bench/modelnames.py` + `benchmark/bench/tests/test_s28_p20_positives_naming.py` (first version) and the
`benchmark/results/m76/tg2/` layout, sealed, Claude Sonnet via `claude -p` (session `152935a6…`). Output: `cold-read-sonnet.md`.
Dispositions: all three minors adopted (record-shape anchor, label charset, boundary tests). Designer addition after the read: the
sealed root record `positives.json` is data too (it held 2 of the blocking hits).
