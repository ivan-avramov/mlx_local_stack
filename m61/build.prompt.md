You are the implementer for PLAN M61 in this repository (cwd = repo root, branch `m61-web-audit`). Read, in order: `AGENTS.md`,
`docs/specs/m61-web-audit-and-prompt-ab.md` (THE spec, P193–P200; implement P194–P197 only — P198/P199 are run by others),
`docs/specs/m59-opencode-v2-probe.md` (context: P148–P162), then the code: `benchmark/run_opencode_probe_v2.py`,
`benchmark/bench/provenance.py` (`opencode_v2_env_check`, `opencode_v2_destination`), `configgen/emitters/opencode.py`,
`configgen/targets.py`, `benchmark/bench/tests/opencode_v2_mock.py`, `benchmark/bench/tests/test_opencode_v2_probe.py` (real-binary
fixtures `real_fixture`/`run_real`), `benchmark/bench/modelnames.py::GENERATED_PATHS`.

Inputs outside the repo (read-only):
- opencode v2.0.20 source: $STACK_WORKDIR/m59_research/src/opencode-v2.0.20 (permissions:
  packages/core/src/permission.ts, util/wildcard.ts; webfetch: packages/core/src/tool/plugin/webfetch.ts; shell: tool/plugin/shell.ts;
  agent system prompt: session/model-request.ts:100-120, schema/src/agent.ts).
- opencode v1.18.15 tag clone (commit d7b115f623760e68a4749d16508a9eca350f246f, MIT, LICENSE at root):
  $STACK_WORKDIR/m59_debug/research/oc-1.18.15 — copy `packages/opencode/src/session/prompt/default.txt`
  VERBATIM to `benchmark/opencode_prompts/opencode-1.18.15-default.txt`; README there records source repo, tag, commit, path, licence line.
- Known-positive detector fixture: $STACK_WORKDIR/m61/known_positive_go_matrix_fetch.txt (the text a 1.18 session
  fetched from https://raw.githubusercontent.com/exercism/go/main/exercises/practice/matrix/.meta/example.go). Commit a copy under
  `benchmark/bench/tests/fixtures/`. Polyglot corpus: $STACK_WORKDIR/polyglot-benchmark (go/exercises/practice/matrix/.meta/example.go
  is the reference it must flag against).

Rules: failing tests first, then minimal code. Real-binary tests use `/opt/homebrew/bin/opencode` 2.0.20 against local mock servers
only — never contact :8000, never the internet (the "allowed URL" test uses a second local HTTP server). The denied-fetch export
shape must come from a real capture against the mock, not from assumption; record what you observed in your report. Keep
`--scaffold opencode-v2` byte-identical to the M59 path (carrier sha and `scaffold_policy_sha256` unchanged — pin with a test).
Do not touch `src/*`, the 1.18 probe, results, or the operator's home config. Do not commit. No absolute home paths/usernames in
committed files (use `$STACK_WORKDIR`/placeholders). Use full registry model names.

Commands: `cd benchmark && env -u STACK_WORKDIR ../.venv-bench/bin/python -m pytest bench/tests -q -p no:cacheprovider` (target 0 failed),
`env -u STACK_WORKDIR .venv-bench/bin/python -m pytest configgen/tests -q -p no:cacheprovider`, `uv run python -m configgen generate`
then `uv run python -m configgen check` (if `uv run` rewrites `uv.lock`, restore it with `git checkout -- uv.lock`).

If the spec is ambiguous or wrong against the source, STOP and ask in your report (state the question and your proposed answer)
rather than guessing on anything that changes provenance, M50 checks or row semantics.

Report (terse): files changed (one line each); the observed export shapes for completed / denied webfetch and denied shell
(exact JSON excerpts); detector numbers on the known positive and the negatives; final summary lines of both suites and
`configgen check`; open questions.
