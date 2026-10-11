You are a cold adversarial implementation reviewer (read-only) for a benchmarking repository. Do not edit files.

Review round 2 of C152 + P273. Read your round-1 review first: $STACK_WORKDIR/c152/cursor_review1.md ("not cleared",
T1-T5). The working tree (uncommitted, `git diff` + new files benchmark/bench/opencode_export.py and
benchmark/bench/tests/test_c152_tool_scope.py) holds the fixes:
- T1/T2: tg1_runner._link_mem_kills always requires an argv token (>= 6 chars) to appear in the shell command, even
  for a single candidate; inject_verify checks EVERY kill (rss > tool limit, linked, its own shell call exists, request
  linkage, part shown killed); any kill with tool_call_id None -> FAIL:unlinked_kill (a collateral git/LSP kill fails
  visibly rather than passing); continuation is measured from the earliest linked kill. Tests: two linked kills PASS;
  an unlinked kill beside a complete one FAILs (either position); single-candidate linkage without a token match
  stays unlinked; the real pytest argv (Homebrew framework Python.app argv[0]) links by its other tokens.
- T3: run_export(attempt, env, *, timeout=120): attempt(env, timeout); no pause that would cross the 10 s deadline;
  every retry's timeout capped to the time left (min 1 s); first attempt keeps the caller's 120 s. Tests for both.
- T4: spec §2 predicate row and §7 V1 acceptance text rewritten to the C152 contract.
- T5: open-questions C152 records the operator ruling.

You may run: `cd benchmark && env -u STACK_WORKDIR TMPDIR=$STACK_WORKDIR/c152/tmp ../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/test_c152_tool_scope.py bench/tests/test_c147_inject.py bench/tests/test_c147_inject_verify.py bench/tests/test_opencode_v2_probe.py -k "alloc or link or run_export or export_session or tool"`

For T1-T5: answered / partial / not answered with file:line. Then only real new defects: a tool-limit kill of
something that is not a model tool process; an alloc PASS without a real linked tool-process kill; a legitimate
live run that would now FAIL (e.g. the stricter linkage missing a real pytest kill — think about `cd x && python3 -m
pytest`, `python -m pytest`, `pytest -q`, Go `go test ./...` whose killed process is a compiled test binary); P273
masking anything but the lock or exceeding its bound. Findings T6, ... . Final line: "cleared", "cleared after fixes"
(ids), or "not cleared".
