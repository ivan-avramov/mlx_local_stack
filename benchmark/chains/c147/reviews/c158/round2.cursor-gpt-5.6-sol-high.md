A4. blocker — `benchmark/bench/answer_key.py:238-274` — C158 widens A1 from Codex-only to Cursor records. On a no-Codex box, malformed/fabricated Cursor records can now enter `strict_n`; previously scoring failed closed. Land P298’s shared schema and resolution-provenance validation before accepting Cursor records.

A5. should-fix — `benchmark/bench/tests/test_m61_round4.py:193-197` — A3 remains in offline tests: these parameterized cases call real `codex --version` and `cursor-agent --version`. The 98 passing tests miss this because Cursor is installed. Stub every declared version probe centrally; make the test fail on any unstubbed subprocess.

not clearedRequested suite passed: 98 tests in 55.30s. No further action taken; A4–A5 remain.
