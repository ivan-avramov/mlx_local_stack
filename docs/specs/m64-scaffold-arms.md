# M64 — scaffold arms: opencode vs Pi vs dsh on the tg1 corpus (C159, C161, C165; PLAN M64)

Status: DRAFT v3 2026-10-16 (Cursor `gpt-5.6-sol-high` spec reviews: round 1 DISAGREE (16), round 2 AGREE WITH
CHANGES (P17–P21 + owner/watchdog/D1–D2) — all addressed; `docs/reviews/m64-spec/`). Approval authorizes the BUILD only; the chain needs its own go after power
simulation and smokes. Design record: `docs/reviews/m64-plan-2026-10-16/plan_final.md` (E1/E2) and C165 (1) (2) (2a)
(2b) (3) (4). **Pending operator rulings: D1, D2 (§2.1).**

## 1. Question and estimand

Which coding-agent scaffold gets the most out of the two B picks (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`,
`Qwen3.8-27B-mlx-uniform-4bit`) on the tg1 corpus (22 Python + 21 Go; `go/counter` excluded, C145), each scaffold as
it is expected to be used?

**Primary estimand: operational scaffold performance under common configured ceilings** (E2.1): each scaffold with
its normal default tools, prompt, loop and compaction (C165 2a/2b); server, model, sampling and token ceilings fixed.
Client cuts and transport DNFs count as failures. Arm-specific effective cuts (opencode 2.0.20's fixed 60-min
inactivity TTL, C154; any analogue found in Pi/dsh) are TREATMENT — unequal effective opportunity, disclosed — unless
the adopted release proves the cut configurable. Matched-budget capability is out of scope. A PASS opens an operator
decision; it does not change the primary scaffold.

## 2. Arms and treatment

| arm | client | native capability = treatment | adapter |
|---|---|---|---|
| `oc` | opencode, Homebrew bottle in the M64 snapshot | built-in tools incl. webfetch + shell; compaction `auto: true`; native prompt | existing tg1 path wrapped unchanged; compaction-on carrier |
| `pi` | Pi `@earendil-works/pi-coding-agent`, vanilla default install | read / bash / edit / write; web via shell only; compaction on; native prompt | new `run_pi_probe.py` |
| `dsh` | DeepSeek Harness `@deepseek-ai/dsh`, release adopted for the epoch | its default tool set per §5.3 inventory; native prompt; compaction default | new `run_dsh_probe_tg1.py`; M35 `run_dsh_probe.py` stays frozen |

dsh is an arm from the start (C161). If a dsh snapshot cannot meet a REQUIRED contract (§6: accounting, retries off,
gate events), the snapshot is REJECTED and the build HOLDS for an operator decision — dsh is never silently dropped.

### 2.1 Pending operator rulings — explicit C165 (2a) amendments
- **D1 — parallel LLM fan-out tools. Proposed amendment C165 (2c):** "Tools that start concurrent model sessions —
  opencode `subagent` and code-mode `execute`; dsh `subagent`, `subagent_fork`, `ralph` (and any such tool found in the
  §5.3 inventory) — are removed in every arm, a disclosed measurement exception: one worker, one cache session, a
  single-stream gate and per-task accounting cannot attribute concurrent sub-sessions." Applies only to tools actually
  present in the adopted snapshot. Rejecting D1 means redesigning the gate and accounting, not a config toggle.
- **D2 — hosted web-search tools** (opencode `websearch`, dsh `web_search`). Three distinct treatments: (a) remove the
  tool; (b) leave it visible as installed, with NO credentials supplied — it works if the vendor serves it
  anonymously, else the call fails, exactly as for a local user without that account; (c) supply credentials.
  **Recommendation (b)** (closest to C165 2a "as normally used"): effective tool surface = default minus D1; any
  search call is audited by P201 like a fetch. `web_fetch` / webfetch and shell networking remain enabled in every arm
  (C165 2). Proposed amendment C165 (2d) records the choice.

Treatment = native system prompt + native tool schemas (default minus D1) + loop logic + compaction behaviour, hashed into
the snapshot. `developer`-role / thinking-history behaviour is treatment; the server must accept it (§6).

## 3. Controls and proof matrix

Every invariant is proven PER REQUEST where it is a request property (receipts, §7), else at its lifecycle point.

| invariant | value | enforcement | evidence |
|---|---|---|---|
| model / registry / predictor | the two picks, deployed registry, predictor OFF | lean router `MLX_VLM_CACHE_SESSION_MAX=1`; one worker per (pick, session) | M50 entry/exit, worker identity + cmdline, `registry.sha256` |
| sampling, seed, budgets, roles | `params_for(model,"deployed")`; paired `sampler_seed`; thinking 81,920; max 102,400 | per-arm generated config | **every request's receipt** (effective sampling, seed, `thinking_budget`, `max_tokens`, role set) reconciled before a row is accepted; first-request wire capture in contract tests |
| context | 262,144 declared to every client | carrier / Pi `contextWindow` / dsh config | config hash; `/health configured_context_limit` |
| ceilings | M62 gate: stall T 81,920 tok or N 40 requests w/o progress; loop K 8; hard 327,680 output tok / 150 requests | unchanged `TokenTurnGate`, fed by normalized events + runner-owned grade boundaries (§5) | row `gate` block; opencode replay parity |
| retries | client retries OFF | opencode noretry plugin; Pi `retry.enabled:false`; dsh: must be disablable, else snapshot REJECTED | contract test: injected 500 → abort, no second request |
| transport failures | counted (C165 2b), §8.3 | runner | incident records in `chain.json` + RUNLOG |
| client timeout | derived; arm-specific unconfigurable cuts = treatment | Pi `httpIdleTimeoutMs`; dsh equivalent if any | config hash; accelerated-timeout contract test |
| shell deadline | 600 s, equal | **adapter watchdog** (§5.4) | contract positives incl. a detached child; detached escape = G2 residual, disclosed |
| ambient instructions | none | hermetic HOME/config; Pi `-nc -ne -ns -np --no-mcp`; dsh equivalents | config hash + extension inventory |
| telemetry / updates | off | Pi `--offline`, `PI_TELEMETRY=0`; opencode disables; dsh `DSH_TELEMETRY_MODE=DISABLED` | socket observation in smokes (observation only) |
| corpus / grader | tg1 universe; `structured_grade` | shared | universe sha, grader version, hashed reports |
| web | per arm native capability (C165 2, D2) | P201 audit made arm-neutral (§9) | audit sidecars; cheat → re-run |
| cleanup | ProcessGuard with G1 | shared | `cleanup_status` |

## 4. Epoch, identity and adoption (E1, P311)

- Snapshots `$STACK_WORKDIR/harness/<tool>/<sha>`; sha over version, tarball integrity / bottle sha, resolved
  dependency tree (`npm ls --all --json`, canonical), node version, extension + plugin inventory, generated config,
  system prompt, tool schemas. `epoch_id` = sha256 of canonical JSON `{schema_version, tools:[{tool, snapshot_sha}]
  sorted by tool}`.
- `chain.json` freezes `epoch_id` and `arm_id → generation_identity_sha256`; entry, every leg (incl. resume) and exit
  verify each arm against its registered identity. **P311:** `scoring_code_sha256` is recorded per row but is NOT a
  pairing key; reports re-derive scoring with current code and print the scoring hash used; comparisons pair on
  generation identity only. Acceptance test: a scoring-only change leaves generation pairing valid; a generation
  change refuses it. The in-probe `answer_key` use (cheat → re-run decision) moves to the chain level (§9).
- **Adoption gate (E1.6, complete):** (a) offline contract tests on the exact snapshot (§6) — any failure → REJECT.
  (b) Bridge: old vs new snapshot on the same loaded instance and seeds, 2 models, 8–12 pre-registered sensitive
  anchors (long request, many turns, tool-heavy, timeout-prone, known C154 items, an injected provider error); red
  flags: any new nonconv kind; a client cut where the old snapshot converged; a pass→fail flip on ≥ 2 anchors; per
  model, summed completion tokens over the anchor set new/old outside 0.67–1.5; any censored or incomplete accounting
  in either snapshot (not evaluable) — any red flag → HOLD + investigate; else ADOPT for new families only. The bridge
  writes a hashed artifact; an epoch is registered only with a passing contract-test artifact per tool and, for a tool
  with a previous adopted snapshot, a passing bridge artifact. M64's epoch is the first for Pi and dsh (no previous
  snapshot: contract tests + smoke only); opencode's previous snapshot is 2.0.20 → bridge required if it moved.

## 5. ArmAdapter contract

Per arm: `snapshot()`; `build_env(item, seed)` (hermetic HOME/config, generated config, cwd = fixed scratch);
`command(item)`; `preflight()` (A4-equivalent: session routing proof + server cache-session behaviour);
`events()` → normalized `{request_seq, usage{input, cache_read, cache_write, output, reasoning}, tool{name, inputs,
status, start, end}, compaction, error, terminal}`; **grading stays runner-owned**: the runner's `GradeWorker`
emits the capture/grade boundaries the gate needs (as `tg1_runner.py` does today) on each completed request;
`transcript()`; `reconcile(stream, transcript, receipts, rc)` — exit code never establishes success, only registered
terminal shapes accepted, else abort; `web_evidence()` (tool calls + shell networking, under
`$STACK_WORKDIR/transcripts/<arm>/…`); `cancel()` (cancel file + SIGTERM-first); manifest (`runtime.arm`, snapshot,
identities, ack wait, `m62_watch` heartbeat). The chain runner is arm-aware only through this contract: stems
`{model}.{session}.{arm}_{lang}`, evidence roots, per-arm RUNTIME_PINNED, A4-equivalent; out-root
`$STACK_WORKDIR/m64[-smoke]`; P340 first. **Parity:** an opencode replay through the adapter yields identical
`TokenTurnGate` decisions and rows to the current tg1 path.

### 5.4 Shell watchdog (attribution)
The adapter keeps a tool-execution window per tool call (from its start/end events). Every descendant of the client
process (ancestry tracked by the ProcessGuard tick, exact (pid, start_time) identities) whose start time falls inside
an open tool window is attributed to that window; client helper processes spawned outside any window (LSP servers,
indexers) are not. Any attributed process older than 600 s is terminated (SIGTERM, then SIGKILL after 5 s) with its
attributed descendants; the row gets an `exec_timeout` flag and the client sees the tool fail. With parallel tool
calls a process is attributed to the earliest open window containing its start time. A descendant that detaches
before the guard's next tick escapes attribution (G2 residual) and is disclosed.

### 5.1 opencode
Existing tg1 path unchanged except a compaction-on carrier (`compaction.auto: true`, label `opencode-v2-web-tg1c`).
Old carrier reproduces the old path byte-for-byte; the new carrier differs only in `compaction.auto`.

### 5.2 Pi
`pi --mode json -p <task> --provider mlx-local --model <served name> --session-dir <run> --session-id <item-attempt>
--offline -nc -ne -ns -np --no-mcp`, `PI_CODING_AGENT_DIR=<run>/agent`. `models.json`: `api: openai-completions`,
router `baseUrl`, dummy key, `contextWindow: 262144`, `maxTokens: 102400`, `samplingParams` = deployed sampling +
seed + `thinking_budget`; `compat` (`supportsDeveloperRole`, `supportsStore`, thinking format) set to what the server
accepts — decided by the contract test and recorded. `settings.json`: `retry.enabled:false`, compaction default (on),
`httpIdleTimeoutMs` = derived client timeout. Events (source-read): `message_end` (usage, `stopReason`),
`tool_execution_start/end`, `compaction_*`, `auto_retry_*` (must never appear), `agent_settled`; json mode may exit 0
on a provider error → `reconcile` decides. `max_completion_tokens` is clamped by Pi to `contextWindow − context −
4096` (recorded per request via receipts). No turn cap in Pi: the M62 gate is the only stop.

### 5.3 dsh
Research step, before its adapter: for the adopted release, inventory every default tool (incl. `web_search`,
`web_fetch`, `subagent`, `subagent_fork`, `ralph`), headless/JSON mode, session format, per-request usage, config
isolation, compaction, retries (M35 saw five transport retries) and timeouts. Apply D1/D2; any other removal needs a
C165 amendment. Retries must be disablable and per-request usage obtainable from client events or receipts, else
REJECT + HOLD (§2).

## 6. Contract tests (offline, per arm, per snapshot; red first)

Mock provider + wire capture: sampling/seed/budgets/roles/tools on every request; retries off; accelerated timeout;
compaction at a reduced window (event recorded, tokens counted); terminal shapes (stop, length, error, cancel, client
cut); shell watchdog positives (foreground, background, detached child); D1 tools absent and D2 tools present but uncredentialed (per the ruling); injected stall, loop,
hard-ceiling positives through each arm's events; P201 cheat → re-run through each arm (§9).

## 7. Receipts and token accounting

**Owner: the `../mlx-vlm` fork worker** (it generates tokens and sees client disconnects; the `mlx-serve` router only
proxies and cannot count tokens produced after a disconnect). This corrects E2.4's wording ("mlx-serve fork"); the
fork change follows the fork rules (AGENTS.md: edit `../mlx-vlm`, test-first, bump the submodule). One receipt per generation request, including client-disconnected
ones: worker identity, monotonic receive/finish times, request sequence number on the worker, effective sampling,
seed, `thinking_budget`, `max_tokens`, roles present, prompt / cache / completion / reasoning tokens generated (incl.
tokens produced before a disconnect), terminal reason. **Correlation:** the runner runs exactly one item attempt at a
time on one worker with D1 in force, so every receipt between an item attempt's start and end marks belongs to it;
the runner writes start/end marks to the worker (a control endpoint) and the adapter ALSO sends an `X-Bench-Attempt`
header where the client supports custom headers (Pi `headers`, opencode provider headers); receipts are hashed into
the item's evidence. Tests: client cut, auxiliary/title requests, compaction requests, a missing receipt, a duplicate
receipt. Primary token quantity: completion tokens per assigned task over all task-attributable requests, failures and
failed attempts included (§8.3). Without complete receipts token superiority is "not established" and joint PASS is
impossible.

## 8. Schedule, attempts and transport incidents

### 8.1 Blocks
Per pick, per session (s1 seed 1001, s2 seed 2002 — distinct paired schedules), per language: items in a seeded order,
blocks of 3 items (Python 7 blocks + 1 residual item, Go 7 blocks); each block runs all three arms on its items in one
of the six permutations; **permutations balanced within each pick × session × language cell** by a seeded allocation
(7 blocks over 6 permutations: each once + one drawn; residual item: permutation drawn by the same seed); schedules
hashed into `schedule.json` before launch, realized order checked after. Per arm switch: cache-session reset, then one
warm-up request (not scored). Reload control: per arm, pick 1, Python, the same 5 seeded items and seeds as s1 on a
fresh worker load.
### 8.2 Worker
One worker load per (pick, session) shared by its three arms; fresh session id per item attempt; no cross-arm resume.
### 8.3 Attempts and transport incidents (C165 2b)
Slot identity = (epoch, arm, pick, session, language, item); attempt identity = slot + attempt n (+ cheat re-run
index, §9). A transport failure (cause taxonomy: worker crash, router error, server timeout, client timeout, dropped
stream) aborts the attempt and records an incident. Recovery protocol before attempt 2 of the same slot: unload +
reload the worker (new identity recorded), M50 + worker-identity checks, cache-session reset, warm-up request,
receipt start mark; then the same slot is re-run with the same seed before the schedule continues. Tokens of the
failed attempt count toward that task. A second transport failure in the same SLOT → synthetic strict-fail row
`nonconv_kind: transport_dnf` with both incidents; the schedule continues. Per-arm transport-DNF incidence is a
reported endpoint. Tests: first-failure recovery, second-failure row, token carry-over, slot keying.

## 9. P201 audit, arm-neutral

Evidence confinement generalized to `$STACK_WORKDIR/transcripts/<arm>/` (opencode's `opencode_transcripts` kept);
re-run eligibility registered per scaffold identity, not the `opencode-v2-web` prefix. **Lifecycle (synchronous):**
after each item attempt that produced web evidence (any web tool call or shell networking), the runner runs the P201
auditor (Cursor `gpt-5.6-sol-high` on this box, C158) before the next item; a cheat verdict re-runs the SAME slot
immediately (same seed, re-run index 1, at most 2, P202) with cache-session reset + warm-up + receipt marks; an
`unclear`/`audit_error` blocks the schedule for operator resolution (P201 procedure). Every cheat attempt's tokens
count toward the task; the scored attempt is the latest non-cheat (exhausted cheating = strict FAIL, P201). opencode
deny patterns: equivalent per arm where the client supports one (opencode carrier; Pi/dsh: the shell watchdog
screens shell commands against the same patterns if feasible, else disclosed "no client-side deny"); the post-hoc
audit applies to every arm. Tests: Pi and dsh cheat → audit → same-slot re-run; token accounting across re-runs.

## 10. Endpoints and inference (pre-registered)

- Accuracy `acc_strict@budget` per (arm, pick, session, language), paired by item and seed. **Cell test:** paired
  difference Δ = mean over the cell's items of (challenger strict − oc strict); TOST H0: Δ ≤ −0.05 or Δ ≥ +0.05;
  p_lower, p_upper from an item bootstrap (B = 10,000) by the shift method; cell p = max(p_lower, p_upper).
- **Accuracy claims (4):** pick × {pi−oc, dsh−oc}; TOST ±5pp in each of the 4 cells (2 sessions × 2 languages);
  claim p = max of the 4 cell p values (intersection-union).
- **Token claims (4):** same contrasts; estimand = mean over tasks of challenger − oc completion tokens per task
  (paired); H1: difference < 0; one-sided p from the two-stage cluster bootstrap (sessions, items within sessions);
  only with complete receipts.
- **Subjective claims (4):** same contrasts; confirmatory estimand = the LENGTH-ADJUSTED two-judge preference (§11);
  TOST H0: adjusted − 0.5 ≤ −0.05 or ≥ +0.05; p from the two-stage (session, item) cluster bootstrap, shift method.
- **Unavailable claims** (incomplete receipts; subjective coverage below the floor; arm REJECTED): p = 1 — the family
  stays at 12.
- **One Holm family over the 12 claims.** Joint PASS for an arm on a pick = its accuracy, token and subjective claims
  all pass after Holm.
- Method validated by simulation BEFORE any build (§12 step 2): coverage and TOST error under sparse/zero
  discordance, plausible unseen discordance, shared loaded-instance effects; inputs P223 / M63 / c144-base. Simulated
  power < 80% at this N → M64 is an estimation screen (no PASS; estimates + intervals), unless the operator approves a
  larger N first.
- Pre-registered sensitivity: primary scoring over all items; paired sensitivity excluding items where either arm had
  a client cut. Descriptive: client-cut, transport-DNF, compaction incidence; nonconv kinds; runaway tax; wall-clock;
  exclusive solves.

## 11. Subjective panel (C161)

Judges codex `gpt-6.1-sol` (on m5max — a judge, not a reviewer) and Claude Fable 5.1 `claude-fable-5-1`; versions and
prompt shas recorded per verdict (P299). **Artifacts:** at each strict-graded attempt the runner snapshots the final
solution files of the scratch dir (the exact bytes graded) into `final_code/<slot>/<attempt>/` with a sha256 manifest;
packets are built only from these, with a packet manifest (pair → both code shas, blinding version, order). New M64
path (not M38's `judge_pairwise` rubric/aggregation): pairs = items where both arms passed strict in that (pick,
session); blinded (names stripped); M64 code-quality rubric (correctness beyond tests, clarity, idiom, minimality,
robustness); both orders. Per judge and pair: order-consistent choice, else tie; a missing order or judge → pair
UNSCORED for that judge. Pair score y = mean of the two judges' scores (win 1, tie 0.5, loss 0) over pairs scored by
both. **Confirmatory estimator:** regress (y − 0.5) on x = log(challenger code length / oc code length) by OLS;
adjusted preference = 0.5 + intercept (preference at equal length); inference by the two-stage cluster bootstrap
(§10). The raw mean and each judge's preference are reported alongside. **Coverage floor:** per contrast and pick ≥ 20
pairs scored by both judges AND ≥ 50% of items; below → claim unavailable (p = 1). **M64 reliability gate** (before
scoring; thresholds from `judge_gate.py`): code anchors — degraded solution must lose (≥ 0.85), identical code on both
sides → tie (≥ 0.80), padded/verbose variant must not win (≤ 0.10), order flip ≤ 0.30; a judge failing the gate is
excluded and the claim is unavailable. Tests: synthetic missing judge, order disagreement, length adjustment, anchors.

## 12. Work order, acceptance, cost (E2.8 order kept; power first)

1. This spec → Cursor cold review rounds → operator go (BUILD).
2. **Power simulation** (needs c144-base attempt 2's rows) → PASS rule or estimation screen fixed.
3. P311 split; P340; G1.
4. ArmAdapter contract + arm-aware runner; opencode wrapped + parity; mlx-vlm receipts.
5. Pi adapter; dsh research + adapter; per-arm injected positives; arm-neutral P201.
6. Snapshot + adoption tooling; M64 epoch registered (contract artifacts; opencode bridge if it moved).
7. Seeded-random 5-item smoke per arm (+ socket observation) → cost estimate with heavy-tail and C154 allowance.
8. Operator go for the chain.

Acceptance (build): §6 per arm, §3 proofs, parity tests, P311/P340/G1 tests, §8.3 and §9 tests, full suite green,
cold review cleared. Cost guess: build several days; chain ≈ 3 arms × 2 picks × (s1 + s2) + reload ≈ 40 h GPU plus
transport re-runs and heavy tail.

## 13. Provenance

- Pi: npm `https://registry.npmjs.org/@earendil-works%2fpi-coding-agent` (read 2026-10-15/16: latest 1.3.0, 15
  releases since 2026-09-15); source `github.com/earendil-works/pi` @ `4954d76` (2026-10-15): docs `cli.md`,
  `json.md`, `message-types.md`, `models.md`, `settings.md`, `compaction.md`, `sessions.md`; src `main.ts`,
  `modes/print-mode.ts`, `core/provider-composer.ts`, `api/openai-completions.ts`.
- dsh: npm `https://registry.npmjs.org/@deepseek-ai%2fdsh` (read 2026-10-16: 0.2.0-rc.2 / 0.2.1-alpha.4; 13 releases
  since 2026-09-15); M35 notes `benchmark/run_dsh_probe.py:80-92`.
- opencode: Homebrew bottle, `scripts/install_bench_opencode.sh`; 2.0.20 exe sha `OPENCODE_V2_EXE_SHA256`.
- Lockfile rule: snapshots record `npm ls --all --json` and the package-lock of the install dir; snapshot shas filled
  at adoption.
