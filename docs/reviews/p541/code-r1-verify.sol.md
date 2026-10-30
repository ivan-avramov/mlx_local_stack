P1 — Resolved. `_git_raw` avoids `.strip()`, uses NUL splitting, and preserves leading/trailing whitespace.

P2 — Resolved. Non-evidence pushes exclude `<remote>/evidence` from the negative revision set.

P3 — Resolved. `push_level` resolves the commit and enforces the evidence orphan rule; `check_lines` no longer duplicates it.

P4 — Resolved. `digest_for` exceptions become per-ref refusal problems, allowing other refs to retain their output.

P5 — Resolved. Level lines are emitted only when `ref_out` is empty.

P6 — Resolved. Tests now cover mismatched receipt content: digest, SHA, and verdict.

P7 — Resolved. Fork-tag tests assert the tagged commit’s exact SHA8.

P8 — Resolved as not a defect. The naming-scan test intentionally exercises the real `modelnames` policy.

P9 — Resolved. `push_level` resolves `<local_sha>^{commit}` itself.

P10 — Resolved/no required action. Stack-tag and gitlink digest propagation remains outside the new level rules; the evidence scanning change is stricter, not weaker.

P11 — Location: `local_gate.py.txt:374-390`; `test_p541_push_level.py.txt:280-292`. Severity: minor. Evidence: confirmed by source trace. Problem: `_git_raw` claims lossless path handling but uses `text=True`, which performs strict locale decoding and universal-newline translation. Git paths are arbitrary byte strings, so an invalid UTF-8 path raises `UnicodeDecodeError`, bypassing `GateError` handling and producing a traceback without per-ref output. Scenario: a pushed commit imported from another system contains a filename with byte `0xff`; `_touched` crashes while classifying it. Proposed change: capture stdout as bytes, split on `b"\0"`, then decode each path with UTF-8 plus `surrogateescape`; add an invalid-UTF-8 path test using Git plumbing.
