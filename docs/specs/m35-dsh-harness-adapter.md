# M35 — DeepSeek Harness (dsh) adapter: a second agentic scaffold beside opencode

Operator GO 2026-09-05. Purpose: scaffold-sensitivity check of the B evidence (opencode is the primary harness; the
community ranks dsh first on n=1 vibe tasks without ever testing opencode). Deliverable: `benchmark/run_dsh_probe.py`, a
drop-in sibling of `benchmark/run_opencode_probe.py` (read its docstring and code first: `.meta` exclusion, test-file
integrity check, progress gate 300/3600 via `bench/progress_gate.py`, docker grading for non-python, manifest beside rows).

## Install (pinned, no global install, no home-dir pollution)
- `npm_config_cache=$STACK_WORKDIR/dsh/npm-cache npm install --prefix $STACK_WORKDIR/dsh @deepseek-ai/dsh@0.1.2-rc.1`
  → binary `$STACK_WORKDIR/dsh/node_modules/.bin/dsh`. Record the exact version in every row (`harness_version`) and refuse
  to run unversioned (mirror the opencode probe's version check).
- dsh must not write under `$HOME`: run it with `HOME=$STACK_WORKDIR/dsh/home` AND `XDG_CONFIG_HOME`/`XDG_DATA_HOME`/
  `XDG_CACHE_HOME` under that dir; verify with a dry run (`find $HOME -newer <marker>` before/after). A knob-less write
  into the real home is a BLOCKER to report, not to work around.

## Provider and invocation
- Env: `DEEPSEEK_BASE_URL=http://127.0.0.1:8000/v1`, `DSH_MODEL=<served registry name>`, `DEEPSEEK_API_KEY=local`
  (whatever config file dsh needs beyond env goes under the redirected home; discover it with `dsh --profile headless
  --dump-config` and document the keys).
- Headless run: `dsh --profile headless "<task prompt>"` with cwd = the scratch workspace (same prompt text and workspace
  construction as the opencode probe), stdout/stderr captured to the run log, no TTY. Any `--no-open`/non-interactive flags
  needed are discovered and documented. Kill by process group on gate-kill.
- Progress gate identical to the opencode probe (tick 300 s snapshot+grade, hard ceiling 3600 s, stall/loop kill).

## Rows
`benchmark/results/<model>/dsh.<tune>.jsonl` + manifest, same fields as the opencode rows plus `harness: "dsh"`,
`harness_version`, `harness_profile: "headless"`. `file_changed`, `tests_pass`, `wall_s`, gate outcome as in opencode.
`compare` must refuse across harness (harness is output-determining): add `harness` to the agentic comparability check if
it is not already keyed by the results filename.

## Tests (TDD; box-free — the router is busy, NEVER send a request to :8000 from tests)
- Unit: provider env construction, home redirection, version pin refusal, row schema, integrity check reuse.
- Integration (network-free): start a tiny fake OpenAI-compatible server on a random localhost port that answers
  `/v1/models` and `/v1/chat/completions` with a scripted sequence (a tool call that writes the solution file, then a final
  message); run the REAL pinned dsh headless against it in a temp workspace; assert the file landed, the row is written, the
  gate did not fire, and nothing was written under the real `$HOME`. If dsh's headless mode cannot drive its tools without
  the web runtime, that is the headline finding — report it with evidence and stop.
- Do not run the real smoke against :8000 (box slot after the M34 OFAT; `--items affine-cipher --lang python`).

## Commits
`feat(bench): run_dsh_probe.py — DeepSeek Harness headless adapter (M35), pinned 0.1.2-rc.1, fake-endpoint integration test`.
Stage by path only; never touch `main_models.yaml`. Full registry model names in code comments and messages.

## Report
What headless dsh actually exposes (tools, config keys, flags), home-dir behaviour, test commands + counts, deviations.
