Cold CODE review — ROUND 1 OF 3 (at most 3 rounds, then the operator decides open findings). STACK repo (this workspace), the P426
Wave-1 builds of `docs/specs/p426-fable-mtp-recert.md` (v4 + the §2 / §6 attribution-rule update), at `1bf5ac3e`;
use `git log --oneline -- benchmark/bench/p426_*.py benchmark/vision_gate.py
benchmark/m1/bench_watch.py benchmark/bench/reasoning.py benchmark/bench/run_reasoning.py benchmark/bench/judge_pairwise.py` and read
the files at HEAD. Builds: B9 `bench/p426_ids.py` + `benchmark/results/p426/ids.json`; B13 / B12 `bench/reasoning.py` +
`bench/run_reasoning.py` (task / request seed bases, completion text); B11 / B12 `benchmark/vision_gate.py` (`--ids`, image_ref /
sha, per-turn draft counters); B5 `benchmark/m1/bench_watch.py` (fail-closed power line + receipt, `--rows-file`, `--flat-escalate`);
B10 `bench/p426_leg.py` (pre-leg refusals, ChainOps router / worker tripwires, exit receipt, engagement gate, log reconciliation,
watcher health, teardown, the strict delta check); B4-stack `bench/p426_overlay.py`; B3 / C207 `bench/p426_panel.py` +
`judge_pairwise.export_packets` system / attachments. Already reviewed elsewhere (do not re-litigate unless broken):
B1 code rounds 1–3 (D1 D2 E1 G1–G3 closed — the cached_session attribution rule), fork dev rounds 1–3 (F1–F4 H1 H2 closed).
Gate: 165 P426 + judge tests pass; the stack suite on `cb2084a9` 7006 / 27 / 0 failed (a fresh one runs next).

Review adversarially: (1) can any leg be VALID for the wrong reason (stale / foreign rows, wrong arm served, unengaged ON, a
missed power failure, unreconciled log, a resumed destination), (2) does every error path fail closed and write a receipt,
(3) the panel: blindness (names / tunes / keys leaking into packets), order handling, the estimator's correctness and its
bootstrap, Cursor judge failure handling, (4) the ID / seed sets (determinism, membership, pairing across arms), (5) test gaps,
(6) PII / absolute paths in committed files. Findings ids K1 onward (or say none), each: severity, file:line, problem, failure
scenario, fix. End with exactly one line: `VERDICT: AGREE` or `VERDICT: DISAGREE <ids>`. OUTPUT RULE: your FINAL message must
contain EVERY finding in full, then the VERDICT line.
