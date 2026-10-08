# M61 — audited web access for the v2 bench (C141) and the system-prompt A/B (C140)

Status: APPROVED 2026-10-08 (operator: P191 "proceed", P192 "agreed"). Discussion ids P193–P200.
Inputs: C140/C141 (`docs/open-questions.md`), `$STACK_WORKDIR/m59_debug/` (RCA, mock captures, `codex_rca.md`), opencode
v2.0.20 source (`$STACK_WORKDIR/m59_research/src/opencode-v2.0.20`), the M59 spec (`m59-opencode-v2-probe.md`, P148–P162).

## P193 — scope

- Two features in `benchmark/run_opencode_probe_v2.py`, one build: a selectable bench carrier (`--scaffold`) with an audited-web
  carrier (C141), and an optional base-system-prompt replacement (`--agent-system-file`) for the A/B (C140).
- Defaults after the build: `--scaffold opencode-v2-web`, no system file. `--scaffold opencode-v2` reproduces the M59 scaffold
  byte-for-byte (same carrier sha, same `scaffold_policy_sha256`); a regression test pins it.
- Out of scope: websearch (stays denied), MCP, any 1.18 change, any serving change.

## P194 — the audited-web carrier (configgen)

- New BENCH target `opencode-bench-v2-web` → `benchmark/opencode_bench_v2_web.json`, emitted by `emit_opencode_bench_v2_web`
  = `emit_opencode_bench_v2` with the `permissions` array changed to (order matters; the LAST matching rule wins; matching is
  case-sensitive `Wildcard.match` over the full URL for `webfetch` and over each parsed command for `shell`):

  ```
  {"action":"external_directory","resource":"*","effect":"deny"},
  {"action":"question","resource":"*","effect":"deny"},
  {"action":"websearch","resource":"*","effect":"deny"},
  {"action":"execute","resource":"*","effect":"deny"},
  {"action":"webfetch","resource":"*","effect":"allow"},
  {"action":"webfetch","resource":"*xercism*","effect":"deny"},
  {"action":"webfetch","resource":"*problem-specifications*","effect":"deny"},
  {"action":"shell","resource":"*xercism*","effect":"deny"},
  {"action":"shell","resource":"*problem-specifications*","effect":"deny"}
  ```

  `*xercism*` covers both capitalisations. The denylist is a deterrent, not the guarantee; P196 is the guarantee.
- The M59 carrier `benchmark/opencode_bench_v2.json` is unchanged. Both carriers are generated; `configgen check` covers both.
- Rows: `scaffold: "opencode-v2-web"`. Never pooled with `opencode-v2` rows (scaffold change).

## P195 — `--scaffold` and `--agent-system-file` (probe)

- `--scaffold {opencode-v2-web, opencode-v2}` selects the carrier source file. The run's `cfg/opencode/opencode.json` is written
  from it; the M50 env check (`provenance.opencode_v2_env_check`) is unchanged and receives the expected sha of the file actually
  written.
- `--agent-system-file PATH` (repo-relative file under `benchmark/opencode_prompts/`; anything else refuses): the written carrier
  is the source carrier plus `agents.build.system = <file text>` (deep-merged; `agents.title.disabled` kept), serialised
  deterministically (`json.dumps(sort_keys=True, indent=2)`). opencode 2.0.20 then uses that text INSTEAD of its base prompt and
  keeps the initial instructions (env block, skills, date) (`session/model-request.ts:110-113`).
- Recorded in the manifest runtime and every row: `scaffold`, `carrier_source`, `carrier_source_sha256`, `agent_system_file`,
  `agent_system_sha256` (null when absent), `opencode_bench_config_sha256` (= the written file). All are recorded and
  resume-checked for every scaffold; they enter `scaffold_policy_sha256` only for `opencode-v2-web` and for runs with a system
  file, so `opencode-v2` without one keeps the exact M59 policy hash (ruling 2026-10-08 on the implementer's question). With a system file the row's `scaffold` label is `<scaffold>+sys:<sha8>`.
- `benchmark/opencode_prompts/opencode-1.18.15-default.txt` = `packages/opencode/src/session/prompt/default.txt` at opencode tag
  `v1.18.15`, verbatim (MIT; source commit and licence line recorded in `benchmark/opencode_prompts/README.md`).
- AGENTS.md M50 sentence is amended: the bench-owned config dir holds exactly one generated v2 carrier (optionally with the
  recorded `agents.build.system` overlay from `benchmark/opencode_prompts/`) and `noretry.js`, by sha.

## P196 — web audit and answer-key detector (rows)

- From the session export, every row records:
  - `web_fetches`: `[{url, status, bytes}]` for each `webfetch` tool part (status `completed` / `error` / `denied`; `denied` when the
    tool error is the permission rejection — the exact export shape is taken from a mock capture, not assumed);
  - `net_shell`: shell commands matching `\b(curl|wget|git\s+clone|go\s+get|pip\s+(download|install)|npm\s+(view|install)|https?://)`;
  - `web_denied`: count of denied fetch or shell attempts.
- `benchmark/bench/answer_key.py: contact(item_dir, texts) -> {flag, evidence}`. Reference = the polyglot item's `.meta/` files
  named `example*`, `exemplar*`, `proof*` (recursively). Normalise lines (strip; drop blank, comment-only and < 12-char lines).
  `flag` when any fetched or network-shell output text contains ≥ 5 consecutive reference lines or ≥ 40 % of the reference
  lines. Evidence = matched-line count, run length, source URL/command.
- Row field `answer_key_contact` (bool) + `answer_key_evidence`. Flagged rows stay in the file, are graded, and are excluded from
  `acc_strict` in reports (reported separately as "flagged: answer-key contact"). The probe prints a line per flagged item.
- Known positive (test fixture, committed): the 1.18 `go/matrix` fetch text (exercism `.meta/example.go`, 31 of 32 normalised
  lines of the polyglot reference) must flag; the item's own stub and its test file must not; a random other item's reference
  must not.

## P197 — tests (failing first; CPU only; never :8000)

Mock-server tests with the real 2.0.20 binary (skipped with explanation elsewhere), plus fake-binary unit tests:
1. `--scaffold opencode-v2` writes the M59 carrier byte-for-byte; manifest identity equals a fixture computed from the M59 code
   path.
2. `opencode-v2-web`: a scripted `webfetch` call to an allowed URL served by a second local mock HTTP server reaches it and is
   recorded `completed` with bytes; a `webfetch` to `http://127.0.0.1:<port>/exercism/x` is denied (no request reaches the mock)
   and is recorded `denied`; a scripted shell `curl …exercism…` is denied and recorded in `net_shell`.
3. `--agent-system-file`: the first chat request's system message starts with the file text, contains the env block, and does
   NOT contain the 2.x base prompt's first line; a file outside `benchmark/opencode_prompts/` refuses before any spawn.
4. Detector known positive/negatives (P196); a flagged row is excluded by the report helper and counted separately.
5. Resume refuses on any identity change (scaffold, system sha, carrier sha).
6. Full `benchmark` and `configgen` suites green with the stack down and without `STACK_WORKDIR` exported.

## P198 — the system-prompt A/B (C140; run after P197 passes)

- Arms: A = `--scaffold opencode-v2` (M59 base prompt); B = A + `--agent-system-file benchmark/opencode_prompts/opencode-1.18.15-default.txt`.
  Webfetch stays denied in both (no web variance); 48K-token allowance; draft OFF; lean router `MLX_VLM_CACHE_SESSION_MAX=1`;
  `mem_watchdog.py` armed; a 5-minute daemon.
- Items (pre-registered 2026-10-08: the five highest mean v2 output-token items among the 34 that both picks passed in both M59
  sessions): `go/forth`, `python/connect`, `python/pov`, `python/bowling`, `python/hangman`.
- Models: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, `Qwen3.8-27B-mlx-uniform-4bit`. Two sessions per model, a fresh loaded
  instance each (seed bases 6101, 6202). Within a session both arms use the same per-item seeds; arm order A→B in s1, B→A in s2.
  40 episodes; estimate 4–5 box-hours (mean ≈ 8K tokens at 24–25 tok/s plus loads), reserve 8.
- Outputs `benchmark/results/<model>/opencode_v2_{lang}.m61ab.{s1,s2}.{A,B}.jsonl`.
- Primary measure: per model, the geometric mean of per-(session, item) output-token ratios B/A with a two-stage cluster
  bootstrap 95 % CI (items as clusters). Secondary: first-write tokens, visible-text characters, passes (any B-only miss listed).
- Pre-registered reading: **prompt-causal** if the CI upper bound < 1.0 and the point estimate ≤ 0.85 for a model; **null** if the
  CI includes 1.0 (then the next screen is tools, not run here); anything else **inconclusive**. A mechanism screen, never an
  accuracy certification; no pick/order change follows from it.

## P199 — build and verification

- Implementer: Codex `gpt-6-astra` (workspace-write) from this spec, tests first. Cold verifier: a fresh Claude Opus 5.5 (allow-shorthand)
  subagent checks every P197 item against the diff and runs the suites. Findings fixed before merge.
- Then a `--limit 5` real-model smoke of `opencode-v2-web` on `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (seeded-random
  Python items), then P198.

## P200 — what follows

- The C139(b) re-record (k=2 chain of both picks, Python + Go, 48K) runs under `opencode-v2-web` — needs its own operator go.
- If P198 reads prompt-causal, a proposal for a daily-client instruction file (brevity/verification) with its own quality check.
