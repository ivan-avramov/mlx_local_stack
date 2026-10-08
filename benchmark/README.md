# Model benchmark harness

Reasoning + coding benchmarks for the local models served by **mlx-serve** (`:8000`).
Everything runs over HTTP against the router — no in-process MLX. Grading is mechanical
(no LLM judge), so you can run it unsupervised.

## How it works

Two phases, deliberately separated:

| Phase | Cost | Resumable | What it does |
|-------|------|-----------|--------------|
| `generate` | slow (model inference) | **yes** | For each (model, benchmark, item) it calls `:8000`, strips the thinking trace, and appends the completion to `results/<model>/<bench>.jsonl`. |
| `grade` | fast (seconds) | n/a | Reads the saved completions and scores them: integer/MC exact-match, math equivalence, or running the official coding test suites. No model calls. |

Because every completed item is written to disk immediately, generation is **safe to
interrupt** — Ctrl+C, close the laptop, change locations — and rerunning the same command
resumes where it left off (already-done items are skipped; errored items are retried).

`generate` classifies failures with a fail-closed allowlist (C119):

| Class | Definition | Action |
|-------|------------|--------|
| Generation outcome | Valid server response, including model budget hits | Append a row; grade; continue. |
| Probe-timeout DNF (O35) | Raw client read `TimeoutError` (including `socket.timeout`) from the item’s first probe request, whose own elapsed time is ≥ 0.9 × the probe timeout | Append a `probe_timeout` error row; strict failure (O31); continue; skip on resume. |
| Transport / harness failure | Every other exception, including every `URLError`, HTTP errors of any status, early timeouts, malformed responses, row-building errors, and restart / recovery-preload / second-probe failures | No row for the in-flight item; stamp existing manifests for pairs with pending items in this run; raise `TransportAbort`; CLI exits 1 with a traceback whose last line names the item. No further generation request. |
| Served-config refusal (M50/C106) | `ServedConfigError` | Propagate unchanged; never convert to a DNF or transport-abort stamp. |

Transport-abort stamps include the item, sample, benchmark, model, scrubbed cause, elapsed
time, per-file row count, timestamp, and best-effort C106 exit-check result. Only pairs with
pending items at the start of the aborted run are stamped. A pair whose manifest does not
exist gets no stamp; stderr is then its only record. Per-manifest failures print a stderr
warning and appear under `transport_abort.stamp_errors` on manifests that can be written;
they never mask the original abort.

Resume retries the aborted draw with the same seed. A previous `transport_abort` stamp moves
to `transport_abort_history` as soon as a later run starts on that pair with pending items,
including when its manifest is restamped. Completion also archives old stamps for selected
pairs, but only after the C106 exit check passes; archival failures warn and continue.
A probe-timeout DNF's `wall_s` measures only its first request, excluding message preparation
and recovery. Initial preload failures always abort. Legacy error rows without `error_kind`
remain retryable on resume and strict failures when graded. The opencode probe's classification
is separate (C124).

### Chunks and overnight runway

Generation runs in time-boxed **chunks** (default 30 min). At each breakpoint it prints
progress + ETA and either continues or stops:

```bash
# Run one ~30-min chunk, then stop (good for a quick session before moving):
uv run python benchmark/run.py generate --tier light --chunks 1

# Auto-run 8 chunks (~4h of runway) overnight, then stop:
uv run python benchmark/run.py generate --tier light --chunks 8

# Run to completion:
uv run python benchmark/run.py generate --tier light --chunks all
```

Only one model is resident in the router at a time. How items interleave across models is set by `--order` (see Ordering).

## Quick start

```bash
# 0. (once) install grading deps into the stack venv
uv pip install -r benchmark/requirements.txt
uv pip install "git+https://github.com/LiveCodeBench/LiveCodeBench.git"   # lcb_runner (grading)

# 1. see which benchmarks load and which models are served
uv run python benchmark/run.py list

# 2. generate (chunked, resumable). Defaults to ALL served models.
uv run python benchmark/run.py generate --tier light --chunks all

# 3. check progress anytime
uv run python benchmark/run.py status --tier light

# 4. grade (mechanical, no model)
uv run python benchmark/run.py grade --tier light
```

## Benchmarking a NEW model

1. Add the model to `main_models.yaml` (so the router serves it) and restart the stack
   (`./runserver.sh`) — or just ensure it appears in `GET /v1/models`.
2. Generate only that model (others are untouched; results are per-model):
   ```bash
   uv run python benchmark/run.py generate --models <new-model-name> --tier light --chunks all
   uv run python benchmark/run.py grade   --models <new-model-name> --tier light
   ```
   Once light looks reasonable, escalate the same model to `--tier mid`.
The harness reads the roster from `/v1/models`, so no code change is needed for new models. A new model with no entry in `model_params.PARAMS` inherits the Gemma-4 parameter set (see Generation parameters).

## Benchmarks

| Name | Kind | Grading | Notes |
|------|------|---------|-------|
| `aime` | reasoning (math) | integer exact-match | AIME 2024+2025, 60 problems. Fully mechanical, ungated. |
| `math500` | reasoning (math) | `math_verify` equivalence | MATH-500. Falls back to normalized string match if `math-verify` absent. |
| `gpqa` | reasoning (science) | MC letter exact-match | GPQA-Diamond, 198. **Gated** — needs `HF_TOKEN` + accepting terms at huggingface.co/datasets/Idavidrein/gpqa. |
| `humanevalplus` | coding | official `evalplus` (pass@1) | HumanEval+ (164). |
| `mbppplus` | coding | official `evalplus` (pass@1) | MBPP+ (~378). |
| `livecodebench` | coding | official `lcb_runner` | Contamination-resistant; pin a release window. |
| `ifeval` | instruction-following | official vendored verifiers (programmatic, no judge) | Optional/lazy deps; missing → `acc: null` + note. Reports prompt/instruction-level strict & loose. |

### LiveCodeBench grading

`lcb_runner` is an optional, lazy-imported dependency. Install it where you run `grade`:

```bash
uv pip install "git+https://github.com/LiveCodeBench/LiveCodeBench.git"
```

Generation and grading both use the pinned release `benchmarks.LCB_RELEASE` for contamination
control. `grade` reports pass@1 as a 0–1 fraction in `acc` (raw `pass@1` recorded alongside). If
`lcb_runner` is absent, the row degrades to `acc: null` with a note rather than failing the batch.

### IFEval (instruction-following)

`ifeval` measures programmatic instruction-following (e.g. "use no commas", "exactly 3 bullet
points", "respond in JSON") — scored by the **official google-research verifiers**, vendored
under `bench/vendor/instruction_following_eval` (pinned commit, Apache-2.0); there is no model
judge. Verifier deps (`absl-py`, `langdetect`, `nltk` + punkt, `immutabledict`) are optional and
lazy-imported — install `benchmark/requirements.txt` where you run `grade`; if absent, IFEval
degrades to `acc: null` with a note instead of failing the batch. Grading reports four numbers —
`prompt_strict` (the headline `acc`: fraction of prompts following all their instructions),
`inst_strict`, `prompt_loose`, `inst_loose` — over the `google/IFEval` set (541 prompts; `mid`
tier samples 30, `heavy` runs all 541).

### BFCL (tool-calling)

`bench/run_bfcl.py` measures single-turn function-calling by driving the official Berkeley
Function Calling Leaderboard harness against the running mlx-serve endpoint. `bfcl-eval` is an
optional dependency — install it where you run the probe:

```bash
pip install bfcl-eval==2025.12.17
```

It is a **standalone probe**, not part of the `generate`/`grade` tier pipeline. Run it with:

```bash
# mlx-serve serving <model> at :8000, bfcl-eval installed:
cd benchmark && uv run python -m bench.run_bfcl --model Qwen3.6-27B-UD-MLX-6bit
```

The probe runs the four AST single-turn categories — `simple`, `multiple`, `parallel`,
`parallel_multiple` — via `--skip-server-setup` against `localhost:8000`. The BFCL AST checker
scores calls structurally; no tool execution happens. Results go to
`results/<model>/bfcl.json` with per-category accuracy and a count-weighted overall `acc`.

If `bfcl-eval` is not installed, the probe writes `skipped: true` with a note and exits cleanly
— it never crashes the broader harness. The `--model` handler (which controls prompt format and
decode settings) is resolved on the box where `bfcl-eval` runs; confirm the handler mapping on
first real run.

### opencode 1.18 probe — FROZEN

**FROZEN 2026-10-07 (M59).** `run_opencode_probe.py` refuses before any I/O with `REFUSED: the opencode 1.18 probe is frozen (M59, 2026-10-07); rows are retained; use run_opencode_probe_v2.py`. Rows are retained under `benchmark/results/*/opencode*.jsonl`; rows with `scaffold: "opencode"` / 1.18.x versions are never pooled with v2. The carrier `benchmark/opencode_bench.json` stays generated and drift-checked for provenance.

### opencode v2 probe (M59)

**Progress gate (C136, 2026-10-07).** The first-write allowance is denominated in tokens: `--first-write-tokens` (default 48000 since C139, 2026-10-08; M59 chain rows ran at 16000 and never pool with 48K rows) is converted per model from the documented draft-OFF decode rate in `benchmark/decode_rates.json` (`tick_s = ceil(tokens / (2 × rate))`; stall after two flat ticks; loop detection at three identical ticks; hard ceiling 3600 s). Every model gets the same tokens before a stall can fire, not the same seconds. A model without a rate entry refuses unless `--tick-s` is explicit (recorded as `manual:--tick-s`). The manifest records `first_write_tokens`, `decode_tok_s`, `decode_tok_s_source`, `first_write_window_s`; rows killed by the rule stay misses (`nonconv_kind: stalled`). Rows also record `prompt_date` (opencode prints the local date into every prompt, so same-seed identity holds only within one day; C135).

The M59 scaffold uses opencode **2.0.20**, `scaffold: "opencode-v2"`, and `schema_version: 3`; never pool its rows with 1.18 rows. The implementation contract is [P149–P153](../docs/specs/m59-opencode-v2-probe.md). The v2 probe and bench carrier are separate M59 deliverables; this section documents their required behavior.

**Hermetic recipe.** Per run, `<R> = $STACK_WORKDIR/opencode-probe-v2/run-<run_id>`; each exercise `<S>` is a git-initialized scratch directory outside `<R>/home`, with no AGENTS.md. Build the environment from an empty dictionary:

```text
PATH=/opt/homebrew/bin:/usr/bin:/bin
HOME=<R>/home
XDG_CONFIG_HOME=<R>/cfg
XDG_DATA_HOME=<R>/data
XDG_STATE_HOME=<R>/state
XDG_CACHE_HOME=<R>/cache
TMPDIR=$STACK_WORKDIR/opencode-probe-v2/tmp/<exercise>/   (stable per item, cleared before the item's first spawn: it reaches the prompt)
OPENCODE_CONFIG_DIR=<R>/cfg/opencode
OPENCODE_DISABLE_PROJECT_CONFIG=1
OPENCODE_DISABLE_MODELS_FETCH=1
OPENCODE_DISABLE_AUTOUPDATE=1
OPENCODE_DISABLE_FILEWATCHER=1
OPENCODE_CONFIG_CONTENT={"providers":{"mlx-local":{"models":{"<model>":{"body":{"seed":N}}}}}}
PWD=<S>
TERM=dumb
NO_COLOR=1
```

Copy the generated `benchmark/opencode_bench_v2.json` verbatim to `<R>/cfg/opencode/opencode.json` and `benchmark/opencode_plugins/noretry.js` to its `plugins/` subdirectory; record both hashes. Seed the per-run cache with the box's `rg`. `N = rowschema.sample_seed(item, 0, base=seed_base)` is constant across the item's requests. Resolve `/opt/homebrew/bin/opencode` (or absolute `OPENCODE_PROBE_BIN`) and record its executable SHA and version; even `--version` must run in this environment.

```text
opencode run --standalone --model mlx-local/<model> --format json --title probe "<prompt>"
opencode session export <sessionID> --standalone
```

Both commands use cwd and PWD `<S>` and stdin DEVNULL. Save stdout events and stderr separately. Read `sessionID` from the first JSON event; export using the same environment. `--standalone` avoids the operator's shared service; `--title` suppresses title requests. The carrier also disables the title agent, removes the vllm/ollama/lmstudio/compatibility plugins, denies external_directory/question/websearch/webfetch/execute, and puts the vllm discovery URL on `http://127.0.0.1:9/v1`. Native per-model `body` carries registry sampling plus `max_tokens`; `compatibility.maxTokensField: "max_tokens"` selects the field the fork honors. `noretry.js` vetoes retries; the preflight must see its `bench.noretry` loading log line.

**M50 v2 rules (P151).** Entry-time clauses refuse with the M50 tripwire. A per-item destination-check failure (timeout, malformed list, or document mismatch) is a resumable `transport_abort` with signature `destination_check`. Only `assert_served_config_unchanged` raising stamps `served_config_drift`; the 1.18 policy is unchanged.

| Check | Required proof |
|---|---|
| Environment and files | `OPENCODE_CONFIG` absent; config-dir realpath equals `<R>/cfg/opencode`; exactly the generated `opencode.json` and `plugins/noretry.js`, matching repository SHAs. CONTENT equals exactly the expected one-provider, one-model `body.seed` integer overlay, with no extra keys. Project config disabled with `"1"`; HOME and every XDG path under `<R>`. |
| Destination from v2 | `api GET /api/config --standalone` with item env/cwd/PWD returns exactly the file document, config-directory entry, and null-path CONTENT document. The null-path CONTENT document must EQUAL the per-item overlay, and the file document's `path` must equal `<R>/cfg/opencode/opencode.json`. No project document. At least one document declares `providers.mlx-local.settings.baseURL`; all such declarations equal the carrier URL, and no document declares another mlx-local settings key. File plugins equal the carrier list. Raw documents, not a merged view, are the proof. |
| Router ownership | Pass the verified URL through `assert_served_config`: sole local owner is mlx-serve, using the driver's registry and entry PID; no proxy or remote destination. |
| Exit | `assert_served_config_unchanged` rechecks PID/hash; drift stamps `served_config_drift`, exits nonzero, and refuses later reuse. |
| A4 prerequisite | Every run requires a valid A4 v2 receipt unless `--limit` ≤ 5. The gate's `pass` must be true, `run_id` nonempty, and `router.pid`, `router_pid`, `model`, `opencode_version`, `exe_sha256`, and `carrier_sha256` must match the run. When both are present, receipt `router.config_sha256` must match the entry router's `config_sha256`. Manifest records `a4_v2_pass` and gate run ID. |

A4 runs with `scripts/session_pinning_gate.py --opencode v2`; `v2` is the default and choosing `1.18` refuses. It creates a temporary root under `$STACK_WORKDIR/session_gate/`, copies the v2 bench carrier (or warns and copies the client config verbatim if absent), then runs two standalone turns with `--title gate`, resuming the first event's explicit `--session <id>`. PASS requires rc 0 and worker-log requests on both turns, all carrying that one `ses_…` ID. `cross_process_reuse` is reported, not gated. `$STACK_WORKDIR/session_gate/a4_v2_latest.json` records the result, model, router PID, executable SHA, `carrier_sha256`, version, and run ID; a drifted router cannot publish PASS. The v2 leg uses the same base URL validated by `main()` (`MLX_SERVE_BASE`, default `http://localhost:8000/v1`). It waits five seconds before the final worker-log read after turn 2. PASS removes the per-run `tmp/` directory (including bun dylibs); FAIL retains it for diagnosis.

**Transport classification (P152).**

| Observed outcome | Class | Action |
|---|---|---|
| rc 0, completed, no error event, starts = finishes or finishes + 1 (the final step_finish is optional: absent in the captures, present in one real run), no assistant error/retry in export | Generation outcome | Write and grade row. |
| Consecutive step_start events, including on gate kills | Transport: silently recovered provider error/re-sample | ABORT, ungraded. |
| rc 1 plus provider.transport/internal/invalid-output error | Transport | ABORT. |
| rc 1, provider.invalid-request status 400 with the fork's context-length message | Context overflow | Row with `nonconv_kind: "context_overflow"`, `passed: false`; budget-class strict miss. |
| rc 1 without error event | Harness failure | ABORT. |
| rc 130 / gate kill for stalled, looping, hard_ceiling; router verified unchanged immediately after kill | Gate outcome | An error of type `aborted` ("Step interrupted") on the final assistant message in the export is the expected gate-kill signature. Write and grade row with `nonconv_kind` = stop reason. An `aborted` error on an earlier assistant message or any other provider error aborts; consecutive step_start events abort on kills too. |
| Gate kill with failed router check | Transport | ABORT with drift stamp. |
| Export missing or unparsable | Harness failure | ABORT. |

ABORT means no item row, no next item, nonzero exit, and PII-scrubbed logs/stderr/export under `$STACK_WORKDIR/opencode-probe-v2/aborted/<run>/<item>/`; stamp `transport_abort: {item, rc, stop_reason, signature, error}` with scrubbed `error` in the manifest. A transport-abort stamp permits continuation; served-config drift does not.

**Rows and progress (P153).** Each row carries `bench: "opencode"`, `scaffold: "opencode-v2"`, `schema_version: 3`, `id`, `model`, `sample: 0`, `passed`, `acc`, `file_changed`, `test_modified`, `opencode_rc`, `opencode_version`, `polyglot_sha`, `wall_s`, `stop_reason`, `timed_out`, existing `gate_*`, `nonconv_kind` (null/context_overflow/stalled/looping/hard_ceiling), `session_id`, `requests_observed` (step_start count), `events_path`, `transcript_path`, `loop_metrics`, `traffic`, `sampler_seed`, `seed_base`, `overlay_sha256`, `max_tokens_semantics`, `grade_tail`, and scrubbed `log_tail`. Traffic tokens come from the export, including the final turn. The progress gate retains tick 300 s, ceiling 3600 s, stall 2, loop 3, reading solution/test files and the events tail.

Manifest runtime records client/scaffold, scaffold identity, config-dir, retry-plugin SHA, A4 result/run ID, `compaction: "off"`, disabled title generation, the hermetic switch set, and observed instruction sources (expected empty). The policy hash covers carrier/plugin SHAs, overlay schema, env switches, git initialization, standalone mode, binary version/SHA, and per-run cache policy; client-config SHA is observational. The cache inventory SHA is recorded after item one.

**Compaction split.** Daily-driver `opencode_config/opencode.json` deliberately enables compaction to handle a human session's overflow. The v2 benchmark carrier disables it so overflow is measured as non-convergence, never hidden by summarization and never a DNF. `acc_strict@budget` remains the ranking key. Rows and manifest runtime record `max_tokens_semantics: "fixed-by-carrier"` and `max_tokens_evidence: "mock-capture:test_real_wire_seed_sampling_title_headers_and_export"`. That capture test verifies both facts at `limit.output=512`: `max_tokens=102400` is sent when the body cap is present, and `max_tokens=512` is sent without it.

### Aider polyglot (agentic edit)

`bench/run_aider.py` measures agentic edit-via-instruction by driving Aider's own polyglot
benchmark harness against the running mlx-serve endpoint. The harness is optional — install it
where you run the probe:

```bash
pip install aider-chat
git clone https://github.com/Aider-AI/aider             # provides benchmark/benchmark.py
git clone https://github.com/Aider-AI/polyglot-benchmark  # the exercises (--exercises-dir)
```

It is a **standalone probe**, not part of the `generate`/`grade` tier pipeline. Run it with:

```bash
# mlx-serve serving <model> at :8000; aider + polyglot-benchmark cloned:
cd benchmark && uv run python -m bench.run_aider --model Qwen3.6-27B-UD-MLX-6bit \
    --aider-repo ../aider --exercises-dir ../polyglot-benchmark
```

The probe sets `OPENAI_API_BASE` to the mlx-serve endpoint and invokes aider's harness with
`--model openai/<served>` and `--edit-format whole`. Aider runs each exercise in its own
sandbox; no edit loop is reimplemented here. Results go to `results/<model>/aider.json` with
`pass_rate_1`, `pass_rate_2`, and a 0–1 `acc` (= `pass_rate_2`, aider's second-attempt rate;
falls back to `pass_rate_1` if the second rate is absent).

If the harness isn't found, the probe writes `skipped: true` with a note and exits cleanly. If
aider runs but no `pass_rate_#` parses from stdout, it records `acc: null` with a note — check
the aider output format. The `openai/<name>` model mapping and sandbox execution mode (docker vs
local) are confirmed on the first real run.

### SWE-bench-Verified (agentic)

`bench/run_swebench.py` measures agentic repo-issue resolution. A minimal explore-and-patch
agent — built on three reusable primitives introduced here: `exec_sandbox` (run code or tests
in an isolated temp dir with a timeout), `agent_loop` (a bounded tool-calling loop over the
Driver), and the driver's new optional `tools`/`tool_calls` pass-through — generates a unified-diff
`model_patch` per instance over a stratified 40-instance subset of
`princeton-nlp/SWE-bench_Verified`. The official `swebench` harness then applies each patch and
runs the repo's test suite inside docker. The harness is optional:

```bash
pip install swebench    # + a running docker daemon
```

It is a **standalone probe**, not part of the `generate`/`grade` tier pipeline. Run it with:

```bash
# mlx-serve serving <model> at :8000; swebench + docker available:
cd benchmark && uv run python -m bench.run_swebench --model Qwen3.6-27B-UD-MLX-6bit --n 40
```

Results go to `results/<model>/swebench.json` with `resolved`, `total`, `resolve_rate` (= `acc`,
0–1), and `subset_ids` (the 40 instance IDs, logged so the subset is never silent).

If `swebench`, docker, or the dataset are absent, the probe writes `skipped: true` with a note
and exits cleanly — it never crashes the broader harness.

The agent, per-instance repo checkout (`repo_provider`), docker harness flags, and the exact
report path/keys are wired and validated at the first real run. Start with `--n 2`.

### AgentBench OS (agentic)

`bench/run_agentbench_os.py` (M54) measures multi-step shell-tool agency: the upstream
`THUDM/AgentBench` `os-std` split, 144 Linux-sysadmin tasks, Apache-2.0, pinned commit
`d1e4a10db08c87075c78972e48ecc182be03e2d5` (`benchmark/corpora/agentbench_os_v1.manifest.json`).
Unlike SWE-bench above, the tool loop is OUR OWN — `bench.agent_loop.run_agent` over the three
upstream tools (`bash_action`, `finish_action`, `answer_action`, upstream system prompt verbatim,
`round_limit` 8) — with one docker container per task. `start` and every `bash_action` share a
SINGLE persistent `docker exec -i <name> /bin/bash --login` process (`PersistentShell`) for the
life of the task: each command is written to that shell's stdin VERBATIM (no `bash -c`, no
in-container `timeout` wrapper) followed by `printf '\n%s%d\n' <fresh-uuid-sentinel> $?`, and
output is read until a line ending in that sentinel+exit-code appears — the printf's leading `\n`
guarantees the sentinel always starts a fresh line even when the command's own output had none, so
exactly that one injected newline (never the command's real output) is stripped. This is why a
`start` script's `cd`/`var=...`/`su - jack` genuinely persists into later `bash_action` calls (a
fresh `docker exec` per command cannot do this at all): the next command is simply read by
whichever shell currently owns stdin. The ONE no-op round run right after the shell starts (`true`)
eats login-shell banner/profile noise before anything else is read, and its result is VALIDATED
before any model call is ever made — a shell that doesn't come up cleanly (dead, times out, or
exits nonzero) is a `setup_error` row with no model call. Matching is done on raw BYTES with an
incrementally-advancing `bytearray.find()` (never a regex re-scanned over the whole buffer after
every chunk — that was O(n²): measured 20KB→9.4s, 50KB→116s, ≥100KB effectively hangs; the current
scan handles 1MB in ~0.03s and 4MB in ~0.15s), and the exit-code digits must themselves be
newline-terminated before a round is considered complete (a chunk boundary landing mid-digit never
misreads a shorter code). A command that reads stdin (e.g. a bare `read`) hangs until the timeout
fires, exactly as it would upstream — there is no special-casing for that.

The round's deadline is set BEFORE the command is even written to stdin, and the write itself
happens in an INDEPENDENT background thread that `run()` never awaits synchronously — it starts
the write and immediately begins draining the reader queue in the SAME loop, both bounded by the
same deadline. (6th cold review round 6 P22, HIGH: the EARLIER write-then-drain design deadlocked
— `head -c 20MB /dev/zero` followed by a 300 KiB comment on one stdin write wedged solid, because
bash floods its own stdout executing the first line while the reader thread fills the bounded
queue and blocks on `put()`, and `run()` was still parked awaiting the FULL write before it ever
drained that queue. `close()` had the identical defect against a descendant still holding the pipe
open, e.g. a backgrounded `sleep 30 &`.) Reader-side memory is bounded too: the reader thread's
queue has `maxsize=256` (backpressure against a chatty background process, e.g. `while :; do echo
tick; done &`), and the SENTINEL-SEARCH buffer (raw bytes only, never decoded) is capped at ~1 MiB
(head 512 KiB + tail 512 KiB + a `[... N bytes dropped ...]` marker) — `raw_output_len` on the
row/transcript always reports the TRUE pre-cap length regardless. The DISPLAY text is decoded
INCREMENTALLY per original chunk (`codecs.getincrementaldecoder`, never by re-decoding an
arbitrary byte-offset slice of the capped buffer, which can split a multibyte UTF-8 character and
falsely report the WHOLE output as undecodable — P28, reproduced with 1.2 MB of valid `€`
characters) and capped separately by CHARACTER count, which can never split a codepoint. A
genuinely invalid-UTF-8 output still reproduces upstream's own `_execute_bash_command` behavior
exactly: the WHOLE output becomes the literal string `"OS Environment output cannot be decoded as
UTF-8"`, not per-byte mojibake. Timeout is enforced ONLY on
the Python side (killing the process, plus a best-effort `docker exec <name> pkill -KILL -f "bash
--login"` — deliberately simple; the container is removed at task end regardless, and process-group
semantics inside an arbitrary image are unverified); exit code 137 (SIGKILL) is NEVER treated as a
timeout — there is no in-container timeout wrapper any more, so 137 is most likely the container's
own 1 GiB memory cap OOM-killing the process, and mis-scoring that as `exec_timeout` would hide a
real memory failure behind the wrong label. The model running `exit` ends the shell the same way it
would upstream, reported as `shell_died`; a death during `start()` (before the model ever acted) is
a `setup_error` row, but a death caused by the MODEL's own `bash_action` is a SCORED FAIL
(`outcome=failed_tests`, IN the acc denominator — upstream's equivalent is "later reads return
empty and the task fails"). Grading itself still runs via FRESH one-shot `docker exec` calls
(mirrors upstream `execute_independent`); a DOCKER EXECUTION failure during grading is
distinguished from the checker's own legitimate verdict by EXPLICIT EVIDENCE ONLY (6th cold review
round 6 P23: an exit code or a timeout alone is never sufficient — 127 alone can be the MODEL's own
"command not found", and a checker timeout alone can be the model's own program hanging): a docker
exit in {125,126,127} TOGETHER WITH stderr text naming an actual docker/daemon/container/runtime
problem ("Error response from daemon", "Cannot connect to the Docker daemon", "is not running", "No
such container", "OCI runtime"), or a checker timeout where a live `docker exec <container> true`
health check run immediately afterward ALSO fails (addendum C: std-005-0/1/2 time out because the
model's own installed binary hangs, which is `failed_tests`, not infra). Any other nonzero exit —
including 127 by itself — stays `failed_tests`, IN the denominator; the matched `setup_error` row
carries `infra_evidence` (rc + stderr excerpt). `docker rm -f` always runs in a `finally` (success,
failure, timeout, KeyboardInterrupt, SIGTERM) and is VERIFIED fail-closed: `docker ps -a` must
itself SUCCEED (rc 0) with empty stdout (P26 — a verification command that itself failed used to
be indistinguishable from "confirmed empty"); the verdict is independent of `docker rm -f`'s own rc
(a `docker run` that never created the container makes `rm -f` legitimately report nonzero, which
is not a cleanup failure). An unverified removal stops the run (`AB.ContainerCleanupError`, after
the task's own row is durably written) rather than silently creating another container on a box
that may be accumulating live ones — the same fail-closed gate applies to D2 prepare's per-probe
cleanup and the startup stale-container sweep. It is a **standalone probe**, not part of the
`generate`/`grade` tier pipeline.

Corpus: `benchmark/corpora/agentbench_os_v1.jsonl` (144 tasks, upstream fields verbatim + our
`id`/`group`/`index_in_file`) + `benchmark/corpora/agentbench_os_v1/scripts/{1..7}/...` (referenced
init/check/example scripts) + `LICENSE-AgentBench`. Build the three task images first (native
aarch64, digest-pinned base; never built against upstream's third-party mirror — see the script's
header):

```bash
UBUNTU_DIGEST=sha256:... scripts/build_agentbench_images.sh
    # clones the pinned sha into $STACK_WORKDIR/agentbench, builds local-os/{default,packages,ubuntu}
```

**D2 exclusion is a CORPUS-level artifact and is mandatory**: a `check`-type task whose check list
contains a "gold slot" (a `None` entry — the live grading chain runs `evaluation.example.code`
there, fed the model's REAL answer) is probed with TWO plausible-looking but different placeholder
answers (`"1"`, `"2"`) run TWICE **inside ONE already-set-up fresh container** (one `docker run`,
init + start once, then `example` run twice with each placeholder in turn) — **rule v2, operator
2026-09-30**: the ORIGINAL design ran the two probes in two SEPARATE fresh containers, and the
first live `--prepare` found 11 of its 13 exclusions were false positives purely because a
randomized init script ($RANDOM/shuf) legitimately produces different state across two DIFFERENT
containers, even though upstream's real grading always reuses the SAME container for the whole
task. Disagreement between the two in-container runs (`gold_mismatch` — EXPECTED, not necessarily
an error, for a randomized-init task; still covers a genuinely answer-reading example script too,
since neither case makes the value usable as a cached gold) or an empty/failed run (`no_gold`,
with the failing step — `create`/`init`/`start`/`example` — recorded) excludes it, with full
diagnostic detail (exit codes, stdout/stderr snippets, timed_out) attached to every exclusion
entry. A check list with NO gold slot (every position a self-contained checker script — grading
never runs `example` with the answer) only needs its reference solution to actually run once in its
own fresh container (`reference_failed` if init/start/example don't all exit 0); no placeholder
probe, no gold is cached. `match`-type tasks are checked FIRST and are never examined by anything
below, manual exclusions included. A hand-curated
`benchmark/corpora/agentbench_os_v1.manual_exclusions.json` (`{id: reason}`) covers probe blind
spots found by inspection rather than mechanically — e.g. `std-007-84`, whose example script reads
a numeric user id that the generic `"1"`/`"2"` probe doesn't happen to trigger for its specific log
fixture; `--prepare` merges it in with reason `manual`, never re-probing those tasks. `--prepare`
writes `agentbench_os_v1.exclusions.json` beside the corpus jsonl: `rule_version` (2; an artifact
produced under the old two-container rule is refused outright, never silently reused), corpus
sha256, the three `local-os` image ids, a sha256 over every vendored script file under
`scripts-root` (an edited check/example/init script invalidates the artifact too), the
manual-exclusions file's sha256, per-task golds, exclusions, a full per-task `disposition` map
(`match`/`kept`/`excluded:<reason>` for EVERY corpus id — a missing entry refuses), and `complete:
true` (refused with `--limit`, since `complete` must mean the WHOLE corpus). Generate mode refuses
to start unless that file exists, is `complete`, has the current `rule_version`, and the corpus
sha256, image ids, scripts sha256, manual-exclusions sha256, AND disposition completeness all still
match what is live. Every row's `gold_prepare` field is the D2-prepare-time value (null for tasks
with no gold slot); `gold_live` is the gold-slot stdout actually observed when THIS run's check
chain graded the answer (the chain already executes it) — a `gold_prepare != gold_live` row is
counted as `gold_prepare_differs` in the summary (renamed from `gold_drift`), since the environment
may have changed since `--prepare` ran, and for a randomized-init task this is EXPECTED rather than
a defect:

```bash
# docker running, images built, mlx-serve serving <model> at :8000:
cd benchmark && uv run python -m bench.run_agentbench_os --model <full-registry-name> --prepare
cd benchmark && uv run python -m bench.run_agentbench_os --model <full-registry-name> \
    --seed-base B --pilot-seed 1 --pilot-n 5   # seeded random pilot, EXECUTED in sampled order
cd benchmark && uv run python -m bench.run_agentbench_os --model <full-registry-name> \
    --seed-base B --resume
```

`--seed-base` (C125) is required in generate mode (not for `--prepare`): item seed
`rowschema.sample_seed(item, 0, base=B)`. Use a distinct base per independent session; the
same-seed reload control reuses that session's base; the model arms of one session share one base.
Rows whose manifest has no `runtime.seed_base` are base 0. `--prepare` / `--migrate-exclusions`
ignore `--seed-base`. It is a resume-identity key, and `agentbench_compare` refuses arms (manifest
or row level) with different bases (an absent manifest key counts as 0; an invalid one refuses).

Same M50/C106 served-config discipline as `vision_gate.py`: refuses before the first request if
the router at `--url` isn't serving this driver's registry, and refuses to declare the run
complete if the served file or router pid changed underneath it; an EXCEPTIONAL exit (a transport
failure, `ContainerCleanupError`, KeyboardInterrupt, or the SIGTERM handler's own exit) still gets
a best-effort C106 exit stamp on the manifest, without ever masking the original exception.
`--resume` REFUSES (rc 2, before touching a single task) unless a FRESHLY gathered candidate
manifest's full identity matches the previous one's: the flat runtime keys (model, round_limit,
exec_timeout_s, sampling_profile, image_ids, corpus_sha256, exclusions_sha256) AND the served-file
hash (`router.config_sha256`), the complete EFFECTIVE sampling dict actually used (temperature/
top_p/top_k/min_p/max_tokens/thinking_budget), and predictor/context/scaffold identity
(`kv.draft_kind`/`kv.kv_bits`/`kv.max_kv_cache_size`) — a manifest missing any of these fields
STRUCTURALLY (not merely a legitimately-None leaf value) refuses outright, and so does a manifest
that already recorded a `served_config_drift` from a prior exit. `llm_timeout_s`/`deadline_s`
are deliberately NOT compared as identity (they are DERIVED numbers that legitimately drift as
more rows accumulate on this axis) — a resume REUSES the previous manifest's values for them
outright. Each process start appends a `{started_at, router_pid, rows_before, identity}` entry to
the manifest's persistent `segments` list. `--limit` and `--pilot-seed` are mutually exclusive
(the corpus is ordered easy-first, so `--limit` would bias any pilot drawn from its
already-truncated head), and the pilot runs in `pilot_draw`'s own SAMPLED order, never re-sorted
back to corpus order. `--sampling-profile` defaults to (and is refused off) `deployed`, and the
manifest records whichever profile actually ran; thinking stays ON.

The per-turn LLM timeout is `max_generation_tokens / floor_tps + 300s` headroom (UNCAPPED — the
shared `budget_timeout.py` 7200s ceiling exists for the convergence benchmark's own,
differently-justified axis and can legitimately be exceeded here): `max_generation_tokens` is the
LARGER of the deployed `max_tokens` and `thinking_budget + 4096`; `floor_tps` is the TRUE per-turn
MINIMUM decode rate (flattened across every row's `per_turn_decode_tps`, never an episode-averaged
or percentile-smoothed rate — a turn's prompt grows across the episode, so later turns decode
slower, and that slow tail is exactly what must be covered), falling back to the minimum
per-row `decode_tps` on `math500`/`convergence` rows (the manifest's `timeout_source` names only
the benches that actually contributed rows) until this axis has rows of its own. The manifest
records a `timeout_derivation` block (`max_generation_tokens`, `floor_decode_tps`, `headroom_s`,
`source`, `observable`, `reason`); if the value can't be SIZED at all (no measured rate anywhere)
the run refuses to start unless `--llm-timeout` was given explicitly — an explicit override is
recorded as `observable: "override"` (distinct from `true`: it is NOT thereby validated). The
per-episode deadline defaults to 8x the per-turn timeout, UNCAPPED (`--deadline-s` to override —
AGENTS.md: the thinking budget is external truncation and is never tuned down for convenience, so
there is no hardcoded ceiling here either) so a looping episode reaches `deadline` rather than
running unbounded — reachable even on an episode stuck re-prompting with no tool calls at all, not
only after a tool-call turn.

A `driver.complete` transport failure (HTTP error/timeout/connection error, OR an HTTP 200 whose
body is an error envelope, has neither `content` nor `tool_calls`, is missing `finish_reason`, or
is missing `usage.prompt_tokens`/`usage.completion_tokens` — `bench.client.MalformedResponseError`,
never a silently empty/under-specified completion; the mlx-serve router always returns all of
these, so their absence is a serving anomaly, never a model score) ESCALATES — the run aborts
nonzero with the task id in the message and writes no row for that task; it is never graded. A
malformed tool-call argument payload (invalid JSON) is NEVER silently treated as `{}` and
dispatched — including when it claims to BE the submit tool — the model gets back a parse-error
tool response (mirroring upstream AgentBench task.py's own corrective mechanism) and the episode
continues; only a WELL-FORMED submit call ends it. A stale `.skipped.json` from an earlier
degraded attempt is removed once a run completes successfully. SIGTERM removes the in-flight
task's container, VERIFIES the removal and warns on stderr if unverified (prepare mode sweeps its
own container prefix, also verified), and exits 143. `--out`, the resolved transcripts dir, and
the exclusions artifact (including the one derived from a `--corpus` outside approved roots) are
all confined to the repo or `$STACK_WORKDIR` (refused otherwise — AGENTS.md: no filesystem
pollution outside STACK_WORKDIR).

Per-task transcripts (quality inspection, turn-by-turn LLM + tool detail) are written to
`--transcripts-dir` (default `$STACK_WORKDIR/m54/transcripts/<model>/<run_id>/`, `run_id` a
per-invocation timestamp recorded in the manifest and REUSED by `--resume`, so two different runs
of the same model never share `<model>/<task>.json` and overwrite each other's evidence) as one
JSON file per task, right after that task's row is appended — including a grading-infra-failure
row, which still carries the episode's ACTUAL completed turns (never reset to empty) plus
`setup_error`/`error`/`infra_evidence`. `bench/agentbench_watch.py` is the M54 run-watcher daemon
(AGENTS.md: every run is reported and critically evaluated every 5 minutes) — read-only, polls the
rows file and manifest, and answers the standing four questions. It never conflates "healthy" with
"not looking": a missing rows file, missing manifest, or missing router log is reported as
`UNKNOWN (evidence missing: ...)`, never silently read as "not stalled" or idle; driver-pid
liveness is checked on EVERY tick, independent of the stall threshold, and the daemon exits right
after reporting a dead driver regardless of row count; busy-vs-idle during a stall is an
ATTRIBUTABLE signal (the mlx_vlm WORKER process, excluding the :8092 task model, sampled via `ps
-o %cpu=` twice 3s apart — BUSY over 20%, UNKNOWN if no worker process is found at all; the
router-log completion marker is a supporting diagnostic only, never the classifier). Its self-test
exercises the real file-reading/classification path against known-positive AND known-negative
fixtures (progressing, stalled-busy, stalled-idle, driver-dead, evidence-missing) and refuses to
start if any of them misclassifies.

Rows (`results/<model>/agentbench_os.v1.jsonl`) carry `id`, `group`, `labels`, `image`,
`gold_prepare`/`gold_live` (see above), `passed`, `outcome` (`bench.agent_outcomes` taxonomy —
`turn_cap`/`no_submit`/`deadline`/a model-caused `shell_died` are scored FAIL rows, never dropped;
`no_submit` is reserved for an episode that never made a single tool call — a dispatched submit
only ever comes from the FIRST tool call of its turn, matching what actually runs), `turns`,
`submitted_via` (`answer`/`finish`/none), `answer`, `per_turn_completion_tokens`,
`completion_tokens_total`, `per_turn_finish_reasons` (includes `tool_calls`, which the server
returns on every tool-calling turn), `converged` (all turns converged against their own RESOLVED
thinking budget), `per_turn_resolved_budget`, `nonconv_kinds` (`budget_hit`/`bad_finish_reason`),
`budget_hits`, `decode_tps`/`per_turn_decode_tps`, `wall_s` (the agent loop only) and
`wall_total_s` (container create -> VERIFIED removal, the full per-task cost -- the basis for the
watcher's ETA and `.summary.json`'s `wall_total_s_mean`/`_max`), `tool_calls`, `tool_timeouts`,
`repeat_calls` (the loop guard is disabled for this axis — the round cap is the bound — so
identical repeats are counted, not aborted), `exec_timeout`, `shell_died` (true whether the death
was model- or start-caused; see `setup_error` for which), `setup_error` (true ONLY for a
start-phase or GRADING-INFRA failure — distinguished from a legitimate checker nonzero exit by
EXPLICIT evidence only: a docker exit in {125,126,127} together with daemon/container error text
in stderr, or a checker timeout where a live `docker exec <container> true` health check ALSO
fails; any other nonzero exit, including 127 from a model-broken dependency, stays `failed_tests`
IN the denominator — EXCLUDED from `.summary.json`'s `acc`/`acc_strict`/`conv_rate` denominator
and reported separately as `setup_error_count`/`setup_error_ids`, with `infra_evidence`
(rc + stderr excerpt) attached), and `container_removed_verified`. `.summary.json` reports `acc`
(raw pass rate), **`acc_strict`** (passed AND converged, same denominator — AGENTS.md's RANKING
KEY), `conv_rate`, `nonconv_kind_counts`, `graded_ids` (the exact id set in the denominator, so two
arms — or a rerun of the same arm — can be intersected before their accuracies are compared),
alongside `exec_timeout_count`/`shell_died_count`/`gold_prepare_differs_count`/
`gold_prepare_differs_ids`.

If docker, the local-os images, or the corpus are missing, the probe writes `<out
stem>.skipped.json` (never the rows file itself) with a note and exits 0 — it never crashes the
broader harness.

### GPQA auth
GPQA is gated. Put `HF_TOKEN=hf_...` in `.env` (the stack already sources it) and accept the
dataset terms once on the Hub. Until then `list` shows it UNAVAILABLE and it is skipped.

## Vision gate (`benchmark/vision_gate.py`)

Purpose: a pass/fail check of "can this model do some vision" — not a ranked benchmark. Per
photo, two turns at the deployed tune with thinking ON: (1) "Describe this image in detail." with
the image; (2) shown the ground-truth captions, self-grade PASS/FAIL. It is a **standalone probe**,
not part of the `generate`/`grade` tier pipeline.

Corpus: `benchmark/corpora/vision_gate_v1.jsonl` (20 COCO val2017 photo ids + 5 human captions
each; images fetched at run time, never committed), built by
`benchmark/corpora/build_vision_gate_v1.py`.

Run it per model — `probe_vision.py` first as a known-positive "sees" check, then the gate,
resumable by design (already-graded ids are skipped on rerun):

```bash
.venv-bench/bin/python benchmark/probe_vision.py --model <name>
.venv-bench/bin/python benchmark/vision_gate.py --model <name> --resume
```

Outputs: `results/<model>/vision_gate.v1.jsonl` (per-item transcript + self-grade) and
`.summary.json` (n, pass, fail, null, pass_rate, mean turn-1 tokens/wall, `fail_or_null_ids`).

Gate rule: ≥16/20 self-PASS = "can do some vision". Self-grades are lenient by construction — the
counts are floors on failure — so always pair the count with a by-eye read of a few descriptions
against the ground-truth captions before trusting a pass.

To add a model to a chain runner, follow the `$STACK_WORKDIR/queue/m39_vision_gate/run.py`
pattern: per model, fresh draft-OFF overlay, start the router, `probe_vision.py --model` as the
SEES precheck, then `vision_gate.py --model <name> --resume`, log the RESULT line, stop the router.

**Retained, not run**: `visionqa` is a mechanically graded (no judge), 40-item visual-QA bench
(ChartQA/ScreenQA/AI2D/TextVQA) wired into the normal two-phase harness for the four seeing
contenders, meant to let vision RANK rather than gate — the operator re-scoped M39 to the gate
above instead (2026-09-12). It stays in the repo, unrun, for if/when ranking is wanted:

```bash
uv run python benchmark/run.py generate --models <name> --benches visionqa --chunks all
uv run python benchmark/run.py grade    --models <name> --benches visionqa
```

## Retrieval probe (dedicated)

`bench/run_retrieval.py` measures multi-needle NIAH retrieval as an
accuracy-vs-context curve at full production params — distinct from the capacity
probe, whose retrieval number is a thinking-starved co-signal (256-token answer budget).
Five distinct codes are planted at depths {0.1, 0.3, 0.5, 0.7, 0.9}; the model is asked
to list all of them; accuracy = fraction returned, with a per-depth breakdown.

```bash
cd benchmark && uv run python -m bench.run_retrieval --model Qwen3.6-27B-UD-MLX-6bit --sampling-profile deployed
```

Writes `results/<model>/retrieval.json` with per-rung `accuracy` + `per_depth_acc` and a
headline `retrieval_effective_ctx` (largest context length with accuracy ≥ 0.85). It is a
full curve, not climb-to-cliff: a mid-context dip does not stop the ladder (retrieval can
recover). CORRECTED 2026-09-13 (O41, M41 tooling): any transport failure (timeout / refused /
OOM-disconnect) at a trial aborts the run with a traceback and no output file — never graded as a
miss. `--sampling-profile` is REQUIRED (O36); `--out-tag` and `--request-timeout` (default 9600 s)
exist. Per-trial rows now carry prefill_s / decode_tps / draft counters. Run 192K/256K rungs on a
quiet box.

## Capacity reporting

`bench.run_capacity` writes schema2: request completion, a rough48GB memory-target
flag and bounded retrieval co-score are separate. Above-target rungs continue;
request failures are unscored and exit nonzero. Use a fresh `--out-tag` and supply
matched `--expected-rung-seconds` for the built-in five-minute daemon's rate/ETA
assessment. Historical results are never overwritten; `rescore.py` is retired.
[Schema, monitoring and compatibility](../docs/specs/c83-capacity-reporting.md).

## Heavy reasoning (aggregation + latent)

Two standalone probes for reasoning ceiling, both at production params, climb-to-cliff and
auto-extending past 64K in 8K steps until the model fails:

- **Aggregation** (`run_aggregation`) — RULER-style common-words extraction: a long word
  stream where a few target words are most frequent; the model must aggregate counts across
  the *whole* context and return them. Tests aggregation, not single-needle retrieval.
  → `results/<model>/aggregation.json`.
- **Latent** (`run_latent`) — a NoLiMa-*style* probe: one needle states a fact about a named
  character; the question refers to it with no lexical overlap, so answering needs a 1-hop
  world-knowledge inference. This is a **self-authored curated set**, not the official NoLiMa
  dataset (which is under the Adobe Research License) — it measures *relative* latent-reasoning
  depth, not leaderboard parity. → `results/<model>/latent.json`.

```bash
cd benchmark && uv run python -m bench.run_aggregation --model Qwen3.6-27B-UD-MLX-6bit
cd benchmark && uv run python -m bench.run_latent      --model Qwen3.6-27B-UD-MLX-6bit
```

Both use exact-match grading (no judge). Each writes per-rung accuracy and a headline
`reasoning_effective_ctx` — the largest context length with accuracy ≥ 0.85.

## Judge panel (subjective code quality)

`bench/run_judge.py` scores execution-passing coding outputs on a 10-axis subjective rubric using
a mixed-family panel: `claude-sonnet-4-6` and `claude-opus-4-8` via the Anthropic API, plus
GPT-5.5 via the `codex` CLI. It is not a correctness oracle — correctness is execution-gated by
LCB/Aider/SWE. The panel only sees outputs that already passed. The `reasoning` axis is advisory.

The judge prompt is blind: it never names the model that produced the candidate output.

Aggregation: per-axis **median** across the judges that returned valid scores, with **per-judge
scores retained** in the output. A `low_confidence` flag is set when fewer than 2 judges return
scores, or when there is a large Anthropic-vs-OpenAI family split (≥2 on the 1–5 scale on any axis).

Backends are optional, lazy, and graceful-degrade. Install what you need where you run the judge
(grade-time, off the measurement box — no model load required):

```bash
uv pip install anthropic    # Sonnet + Opus; also set ANTHROPIC_API_KEY
# codex CLI on PATH         # GPT-5.5 (one-shot invocation)
```

A missing backend is skipped; the panel never crashes. Run it with:

```bash
# passing.jsonl: one {task, output, reference?} per execution-passing solution
cd benchmark && uv run python -m bench.run_judge --model <model> --records passing.jsonl
```

Writes `results/<model>/judge.json` with `overall`, `per_axis`, `low_confidence`, and the full
per-record per-judge breakdown. The real API calls and JSON adherence are validated on the first
real run.

## Tiers (escalating scope)

Pick scope with `--tier light|mid|heavy`. The three tiers nest: light's item set is a
prefix of mid's, which is a prefix of heavy's (the subsampling is seeded and prefix-stable),
and light's benchmarks are a subset of mid's, which are a subset of heavy's. So you can run
`light`, then `mid`, then `heavy` and each step regenerates only the items the previous tier
didn't cover — resume reuses everything already on disk.

| Tier | Coding | Reasoning |
|------|--------|-----------|
| `light` | humanevalplus 15, mbppplus 15 | aime 5 |
| `mid` | humanevalplus 15, mbppplus 15, livecodebench 15 | aime 30, math500 30 |
| `heavy` | humanevalplus 164, mbppplus 378, livecodebench 100 | aime 60, math500 200, gpqa 198 |

Light is coding-led on purpose: it gives a fast first read across all 7 models and calibrates
the real per-item cost of coding before you commit to anything larger. Mid adds livecodebench
and math500 and widens aime. Heavy is the full sets plus gpqa.

Recommended workflow: run `--tier light` across every model, grade, and see where you stand.
Then `--tier mid`. Then decide whether `--tier heavy` is worth it — and if some models are too
slow to be worth the full run, drop them with `--models`.

Cost: at production parameters, reasoning items run roughly 5 h/item across all 7 models, with
the dense Gemma-4 and Qwen3.6-27B as the bottleneck; coding is much cheaper. That's why light
is the cheap first read. Tune scope with `--limit` and `--models`, e.g.
`--benches aime,gpqa --limit aime=10,gpqa=10 --models A,B`.

## Generation parameters

The harness sends each model its production parameters from `bench/model_params.py`, sourced
from your `opencode.json` and `aider` configs — not neutral eval defaults. Two parameter sets:

- Gemma-4 family (every dense and MoE quant): temperature 0.7, top_p 0.95, top_k 64,
  repetition_penalty 1.08, max_tokens 32768, enable_thinking true, thinking_budget 16384.
- Qwen3.6-27B: temperature 0.7, top_p 0.95, top_k 20, min_p 0.03, presence_penalty 0.3,
  max_tokens 81920, enable_thinking true, thinking_budget 49152.

Override globally with `--thinking-budget`, `--temp`, and `--max-tokens` — useful to bound
eval time. A new model with no entry in `model_params.PARAMS` inherits the Gemma-4 set; add it
to `PARAMS` if it needs its own.

## Ordering

`--order roundrobin` (default) interleaves models item by item, so any stopping point is a
balanced comparison across all models — grade incrementally and the partial numbers stay fair.
`--order model` runs each model to completion before the next, which minimizes model swaps.

## Convergence (sat%)

`grade` reports `sat%` alongside accuracy: the share of items where the model spent ~all of its
`thinking_budget` (it did not self-converge and leaned on the budget to stop). A model near
100% sat% is reasoning inefficiently; one that finishes well under budget converges on its own.

## Reproducibility

Subsampling is seeded (`--seed`, default 0) and prefix-nested, so the same tier always selects
the same items and tiers escalate cleanly. Parameters are fixed per model at production values
(see Generation parameters), not greedy. Because temperature is 0.7, single-sample runs carry
some run-to-run variance — use these numbers for relative model comparison, not absolute
leaderboard parity.

## Output layout

```
benchmark/results/
  <model>/<bench>.jsonl        # one line per item: completion + token/timing telemetry
  <model>/<bench>_samples.jsonl # coding: official-format samples for the grader
  scores.json                   # written by `grade`
```
