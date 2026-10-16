# M64 — scaffold arms: opencode vs Pi vs dsh on the tg1 corpus (C159, C161, C165; PLAN M64)

Status: DRAFT 2026-10-16 for cold review (codex `gpt-6.1-sol` + Cursor `gpt-5.6-sol-high`) → operator go. Approval of
this spec authorizes the BUILD only; the chain needs its own go after the smokes. Design record:
`docs/reviews/m64-plan-2026-10-16/plan_final.md` (E1/E2) and C165 (1), (2), (2a), (2b), (3), (4).

## 1. Question and estimand

Which coding-agent scaffold gets the most out of the two B picks (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`,
`Qwen3.8-27B-mlx-uniform-4bit`) on the tg1 corpus (22 Python + 21 Go items; `go/counter` excluded, C145), as each
scaffold is expected to be used?

**Primary estimand: operational scaffold performance under common configured ceilings** — each scaffold as normally
used (C165 2a: its native tools, prompts, loop, compaction), the server, model, sampling and token ceilings held
fixed. Client cuts (C154 and any analogue) and transport DNFs count as failures; unequal effective opportunity is
disclosed per arm. Matched-budget capability is out of scope (E2.1).

A PASS does not change the primary scaffold by itself; it opens an operator decision (every row re-baselines).

## 2. Arms and treatment

| arm | client | native capability (treatment) | adapter |
|---|---|---|---|
| `oc` | opencode (Homebrew bottle, sha-pinned per snapshot) | built-in tools incl. webfetch + shell; compaction `auto: true`; native prompt | existing tg1 path, wrapped unchanged |
| `pi` | Pi `@earendil-works/pi-coding-agent`, vanilla | read / bash / edit / write; web via shell only; compaction on; native prompt | new `run_pi_probe.py` |
| `dsh` | DeepSeek Harness `@deepseek-ai/dsh` (current release at epoch) | native tools incl. its web tool + shell; compaction as default; native prompt | new `run_dsh_probe_tg1.py` (M35 `run_dsh_probe.py` stays frozen) |

Treatment = native system prompt + native tool schemas + loop logic + compaction behaviour, all hashed into the
snapshot. Differences in web capability are treatment, disclosed. Native `developer`-role / thinking-history behaviour
is treatment; the server must accept it (contract test, §6).

## 3. Controls (held fixed) and the proof matrix

| invariant | value | enforcement | evidence |
|---|---|---|---|
| model, quant, registry | the two picks, deployed registry, predictor OFF | lean router `MLX_VLM_CACHE_SESSION_MAX=1`, one loaded worker per (pick, session) | M50 entry/exit, worker identity + cmdline, `registry.sha256` |
| sampling | `params_for(model, "deployed")` | per-arm config generation | first-request wire capture (contract test) + per-request server receipt |
| seeds | paired `sampler_seed` per (item, sample) | per-item config | wire capture + receipt |
| thinking | ON; budget 81,920; max 102,400; resolved headroom | config + server | receipt (`thinking_budget`, `max_tokens`); `convergence.resolved_thinking_budget` |
| context | 262,144 declared to every client | carrier / `models.json contextWindow` / dsh config | config hash; `/health configured_context_limit` |
| token/turn ceilings | M62: stall T 81,920 tokens or N 40 requests without progress; loop K 8; hard 327,680 output tokens / 150 requests | the M62 gate fed from each arm's normalized events | row `gate` block |
| retries | client retries OFF | config (opencode noretry plugin; Pi `retry.enabled:false`; dsh equivalent) | contract test (injected 500 → no second request) |
| transport failures | counted (C165 2b) | leg aborts; chain re-runs after restart; twice for one (arm, item) → `transport_dnf` | RUNLOG + chain.json incident record |
| client timeout | derived (max generation / floor decode + headroom) | Pi `httpIdleTimeoutMs`, opencode/dsh equivalents | config hash; accelerated-timeout contract test |
| shell deadline | equal across arms | harness-enforced (process supervision of tool children) | guard log |
| ambient instructions | none (no AGENTS.md / CLAUDE.md / skills / extensions / MCP) | hermetic HOME/config; Pi `-nc -ne -ns -np --no-mcp`; dsh equivalents | config hash + extension inventory in snapshot |
| telemetry / update checks | off | Pi `--offline`, `PI_TELEMETRY=0`; opencode disables; dsh `DSH_TELEMETRY_MODE=DISABLED` | socket observation in smokes (observation only) |
| corpus / grader | tg1 universe, `structured_grade` | shared | universe sha, grader version, hashed reports |
| web | allowed per arm's native capability (C165 2) | — | P201 audit of every arm's web tool calls AND shell networking; cheat → re-run procedure |
| cleanup | ProcessGuard (G1 applied) | shared | `cleanup_status` |

## 4. Epoch and identity (E1)

- Snapshots: `$STACK_WORKDIR/harness/<tool>/<sha>`; sha over version, tarball integrity / bottle sha, resolved
  dependency tree (`npm ls --all --json` canonicalized), node/runtime version, extension + plugin inventory, generated
  config, system prompt, tool schemas. `scripts/harness_refresh.py <tool>` builds a snapshot and runs the adoption gate.
- `epoch_id` = sha256 of canonical JSON `{schema_version, tools:[{tool, snapshot_sha}] sorted}`.
- `chain.json` freezes `epoch_id` and `arm_id → {generation_identity_sha256, scoring_code_sha256}` (P311 split is a
  prerequisite); entry, every leg (incl. resume) and exit verify each arm against its registered identity.
- Adoption gate (E1.6): contract tests → REJECT on failure; bridge with pre-registered red flags → HOLD; else ADOPT
  for new families. All three harnesses are snapshotted fresh for M64's epoch.

## 5. ArmAdapter contract (one per arm)

Every adapter implements: `snapshot()`, `build_env(item, seed)` (hermetic HOME/config, generated config, cwd = fixed
scratch), `command(item)`, `preflight()` (A4-equivalent: session routing proof + cache-session behaviour on the server),
`events()` → a normalized stream of `{request_id, usage{input, cache_read, cache_write, output, reasoning}, tool_call
{name, inputs, status}, compaction, error, terminal}` feeding the unchanged `TokenTurnGate`, `transcript()` (durable
post-hoc record), `reconcile(stream, transcript, receipts, rc)` (exit code never establishes success; only registered
terminal shapes accepted; else abort), `web_evidence()` (tool + shell networking for P201), `cancel()` (cooperative
cancel file + SIGTERM-first), manifest fields (`runtime.arm`, snapshot, identities, ack wait, `m62_watch` heartbeat).
The chain runner becomes arm-aware through this contract only: per-arm stems (`{model}.{session}.{arm}_{lang}`),
evidence roots, RUNTIME_PINNED map and A4-equivalent; out-root `$STACK_WORKDIR/m64[-smoke]`; P340 fixed first.

### 5.1 opencode (`oc`)
Existing tg1 path unchanged except the carrier: a compaction-on tg1 carrier (`compaction.auto: true`, new scaffold
label `opencode-v2-web-tg1c`). Parity tests: the old carrier reproduces the old path byte-for-byte (replay +
injected positives); the new carrier differs only in `compaction.auto`.

### 5.2 Pi (`pi`)
`pi --mode json -p <task> --provider mlx-local --model <served name> --session-dir <run> --session-id <item>
--offline -nc -ne -ns -np --no-mcp`, `PI_CODING_AGENT_DIR=<run>/agent`. `models.json`: provider `mlx-local`,
`api: openai-completions`, `baseUrl` = router, dummy key, model `contextWindow: 262144`, `maxTokens: 102400`,
`samplingParams` = deployed sampling + seed + `thinking_budget`; `compat`: `supportsDeveloperRole` and `supportsStore`
set to what the server accepts (contract test decides; record), thinking format per the server's template.
`settings.json`: `retry.enabled: false`, compaction default (on), `httpIdleTimeoutMs` = derived client timeout. Events
(source-read): `message_end` (usage, `stopReason` ∈ stop/length/toolUse/error/aborted), `tool_execution_end`,
`compaction_*`, `auto_retry_*` (must never appear), terminal `agent_settled`; json mode can exit 0 on provider error →
`reconcile` decides. Known risk: `max_completion_tokens` is clamped to `contextWindow − context − 4096` (budget shrinks
near the window; recorded). Pi has no turn cap: the M62 gate is the only stop.

### 5.3 dsh (`dsh`)
Research step first (current release's headless/JSON mode, session format, per-request usage, config isolation,
compaction, retries, web tool). If per-request usage cannot be obtained from the client, server receipts (§7) are the
accounting source; if neither yields per-request usage live, the M62 gate cannot run and dsh is dropped from the
chain with that reason recorded (operator informed before the build continues).

## 6. Contract tests (offline, per arm, per snapshot; tests fail first)

Mock provider: first-request wire capture (sampling, seed, budgets, roles, tools); retries off (injected 500 → abort,
no second request); accelerated timeout; compaction trigger at a reduced window records a compaction event and its
tokens; terminal shapes (stop, length, error, cancel, client cut); tool-call bounds; no egress beyond the router in the
mock run (observation); injected positives for stall, loop, hard ceiling through each arm's normalized events.

## 7. Token accounting and server receipts

Primary token quantity: completion tokens (visible + reasoning) per assigned task, all task-attributable requests
(incl. compaction, title, auxiliary), failures included; input/cache reported as components. **Build item in the
`../mlx-vlm` fork:** a per-request usage receipt for every request, including requests whose client disconnected
(currently no usage is recorded for a cut request), keyed by request id and session, written under the worker's log
dir; the adapters reconcile client events against receipts. Without complete receipts a token-superiority claim is
"not established" (E2.4).

## 8. Schedule

Per pick, per session (s1, s2; reload = seeded 5-item Python pilot of pick 1 per arm): one loaded worker shared by the
three arms; items in fixed seeded order split into blocks of 3 items (Python 22 → 7 blocks + 1 residual; Go 21 → 7);
each block runs all three arms on its items in one of the six arm permutations, permutations allocated by a seeded
balanced randomization (each permutation ≈ equally often per pick × session; residual block: permutation drawn by the
same seed); a warm-up request and server cache-session reset at every arm switch; fresh session id per item; realized
order written to `schedule.json` before launch and checked after. Wall time descriptive only.

## 9. Endpoints and inference (pre-registered)

- Accuracy: `acc_strict@budget` per (arm, pick, session, language), paired by item and seed.
- Primary claims (4): pick × {pi−oc, dsh−oc}; each an intersection-union test over its 2 sessions × 2 languages cells
  (claim p = max cell p), TOST ±5pp.
- Token claims (4): same contrasts, completion tokens per task, superiority (two-sided CI excluding 0 in favour of the
  challenger), only with complete receipts.
- Subjective claims (4): same contrasts, two-judge blind pairwise preference over pair-specific both-pass items, TOST
  ±5pp around 0.5.
- **One Holm family over the 12 claims.** Joint M64 PASS for an arm on a pick = accuracy claim AND token claim AND
  subjective claim all pass after Holm.
- Inference method: two-stage cluster bootstrap (items within sessions), validated by simulation BEFORE launch for
  coverage and TOST type-I/II error under sparse and zero discordance, plausible unseen discordance and shared
  loaded-instance effects, using P223 / M63 / c144-base discordance as inputs. If simulated power for ±5pp at this N
  is < 80%, M64 is relabelled an estimation screen (no PASS; point estimates + intervals) unless the operator approves
  a larger N first.
- Also reported, descriptive: per-arm `client_inactivity` / client-cut incidence, transport DNFs by cause, compaction
  incidence, nonconv kinds, runaway tax, wall-clock, exclusive solves, union-exclusion sensitivity.

## 10. Subjective panel (C161)

Judges: codex `gpt-6.1-sol` (run on m5max) and Claude Fable 5.1 `claude-fable-5-1`; versions and prompt shas recorded
per verdict (P299 rule). Packets: the final code of both arms for an item where both passed, blinded (model/scaffold
names stripped, `bench/judge_pairwise.py` blinding), code-quality rubric (correctness beyond tests, clarity,
idiomatic use, minimality, robustness); both orders; per-pair verdict = order-consistent choice else tie; missing
judge → pair unscored; coverage per contrast reported. Estimator: preference = (wins + 0.5 ties)/n per judge; reported
per judge and as the two-judge mean; length adjustment by a paired-difference regression of preference on log length
ratio with item-clustered errors (adjusted intercept); item-cluster bootstrap CI. Reliability gate (`judge_gate.py`
thresholds) on anchors before scoring.

## 11. Work order, acceptance and cost

1. This spec → cold review → operator go (BUILD only).
2. P311 identity split; P340; G1 — each test-first + cold review.
3. Snapshot + adoption tooling; snapshot all three harnesses (M64 epoch).
4. ArmAdapter contract + arm-aware runner; opencode wrapped + parity tests; mlx-vlm receipts.
5. Pi adapter; dsh research + adapter; contract tests green per arm (red first).
6. Seeded-random 5-item smoke per arm (incl. socket observation) → cost estimate (heavy tail, C154 allowance).
7. Power simulation → PASS rule or estimation screen fixed → operator go for the chain.

Acceptance (build): every §6 contract test and §3 proof passes per arm; parity tests pass; full suite green; cold
review cleared. Cost guess (calibrated by the smokes): build several days; chain ≈ 3 arms × 2 picks × (s1 + s2) +
reload ≈ 40 h GPU before heavy tail.

## 12. Provenance (to fill at snapshot time)

Per tool: package/bottle version, integrity hash, registry metadata URL and fetch date, source tag/commit read,
snapshot sha. Pi facts above were source-read on 2026-10-15 at `earendil-works/pi` `4954d76` (docs: cli.md, json.md,
message-types.md, models.md, settings.md, compaction.md; src: main.ts, print-mode.ts, provider-composer.ts,
openai-completions.ts) and must be re-verified against the adopted snapshot.
