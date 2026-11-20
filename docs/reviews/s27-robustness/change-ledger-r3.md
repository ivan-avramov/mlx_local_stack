# S27 robustness bundle — change review round 3 of 3 (LAST; panel verify of fix round 2, candidate 3): ledger

Candidate 3 = `out/candidate-3.patch` (71 files) = candidate 2 + `fix-2.patch` (12 files). Frozen tests v4 (17:27:23Z): 288 pass
on candidate 3; `test_s27_impl_*` 245 pass. Panel: Claude Sonnet 5.5 (`32fe10fd…`) Y1–Y6 resolved, 2 minors; GLM 5.2 High
NOTHING OF SUBSTANCE (2 optional nits); GPT-5.6 Sol High 6 majors. Test-writer delivery 4: merge (its finding 1 = Sol P3).
Review budget exhausted (3 rounds) → the open findings go to the operator (S28-P10).

| id | finding (raised by) | designer judgement | why |
|---|---|---|---|
| Z1 | `structured_grade._grade`'s `finally: remove_container()` can replace the typed fault (Y2) with a cleanup `OSError` / plain abort (Sol P1) | real, fail-closed | traced (`structured_grade.py` finally). Docker loss aborts the leg (pre-S27 behaviour) instead of regrading; no wrong data. tg1 Go only. |
| Z2 | Reuse race in `owned_scan`: leader checked before the process snapshot; a pid reused in between as a new session leader is claimed and killed (Sol P3 → P2 here; Sonnet F1 related) | real, very rare, foreign-kill class | needs the session already empty AND the pid reused within the scan; the consequence is the cardinal threat. Snapshot first, validate the leader inside it. |
| Z3 | Y4's "no item record" exception is authorized by ANY recorded accounting entry, not only a done-hook failure that prevented the record (Sol P3, test-writer finding 1) | real, harness-only | only the harness writes sidecars; simplest intent: null allowed iff the item record does not exist. |
| Z4 | `_ancestry` seeds ownership by bare pid when a tracked identity's start is unreadable; a reused pid read later is killed as ancestry (Sol P4) | real, very rare, foreign-kill class | transient read failure + pid reuse within one scan; keep identity in the ancestry closure, mismatch → foreign / uncertain. |
| Z5 | `foreign_new` / `path_only` identity comes from `cmdline()[0]`, which a process can set to free text (titles); a 64-char cap is not identity (Sol P5) | real, data boundary, normal conditions | use the executable (`Process.exe()`) basename + argc; unknown when unreadable. |
| Z6 | The watcher's `BoxSampler` writes the top-CPU processes' arguments (scrubbed of paths / user only) into `watch.jsonl`, a `main` record the harvest requires (Sol P6) | real, data boundary + operational, normal conditions | traced (`bench_watch.py` BoxSampler, `p426_harvest.py:223/1048`). Any high-CPU foreign process with a secret / email in its args either leaks or makes the harvest refuse the leg (a D3-class loss). Spec §8.1 says "scrubbed argv" — amend to executable identity + argc. |
| Z7 | A reused session leaves unreadable would-be members unflagged (`certain` stays True) (Sonnet F1) | merged into Z2 | the same fix covers it. |
| Z8 | `finish()` discharges only the grading capture; a capture queued after the worker died stays pending (Sonnet F2) | minor, real | one line. |
| Z9 | Docstring: the reuse branch rests on the kernel's sid reservation; item-record read not `lstat`-guarded (GLM nits); float-equality start compare (test-writer 2) | nits | document; `lstat` for symmetry; compare as recorded (fails closed today). |
