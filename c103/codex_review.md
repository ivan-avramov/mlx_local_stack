## Verdict

**P1 — Ship a verified client-side fix first. Reject B as specified.** The observed prefix drift is real. A1 is supported by upstream source but remains **UNVERIFIED on the installed binary with its effective configuration**. B’s sizing is approximately correct; its replay guarantee, snapshot lifecycle, and promised M45 fix are not.

Read-only review; no files changed or inference workloads run.

## Diagnosis check

**P2 — Only four system-prompt location lines differ.** Comparing parsed [req_001.json:1]($STACK_WORKDIR/c102a/capture/req_001.json:1) and [req_004.json:1]($STACK_WORKDIR/c102a/capture/req_004.json:1):

- Both system strings are 28,538 characters. Removing `<location>…</location>` differences makes them identical.
- Changed locations: `docs`, `import-memory`, `pptx`, and `vnote`.
- All non-message fields—including tools and sampling parameters—and the first user message match.
- **Role lists are not identical:** request 001 has two messages; request 004 has eight, including conversation history and another user turn. Correct [proposal:13]($STACK_REPO/docs/specs/c103-prefix-drift.md:13).
- The first character difference is at offset 21,262. The notebook says approximately **2K tokens before the system prompt ends**, not 2K tokens into it. [Notebook:3963]($STACK_REPO/docs/lab-notebook.md:3963)

**P3 — Full re-prefill follows from the guard; increasing the existing ring cannot fix this capture gap.** Dispatch finds the token LCP, selects the nearest snapshot at or before it, and sets reuse to zero if none exists; it then clears the unusable session cache. [dispatch.py:996]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:996), [dispatch.py:1015]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:1015), [dispatch.py:1078]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:1078)

The earliest user anchor follows the system prompt, hence follows these changed locations. Keeping more such anchors cannot create an earlier checkpoint. At the logged divergence around 10–12K, a periodic checkpoint at 8192 could help.

The proposal also conflates two paths: mid-prefill anchor capture is **asymmetric-only**; afterward that state is restored and `update()` captures the resulting boundary. Symmetric requests instead save end-of-generation state. These are not universally two ring insertions per request. [dispatch.py:1195]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:1195), [dispatch.py:1380]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:1380), [common.py:984]($HOME/ws/mlx-vlm/mlx_vlm/generate/common.py:984)

The measurements rule out session-ID loss in this sample: the same pinned ID has 12,604 cached tokens within process 1 and zero on process 2’s first request. [Gate:24]($STACK_REPO/benchmark/results/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/session_pinning_gate.c102a.json:24) The longer leg reproduces this pattern. [Leg B:75]($STACK_REPO/benchmark/results/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/session_cache.c102a_legb.json:75)

## A1 assessment

**P4 — A1 is source-supported, conditional on effective permissions.** Tagged opencode 1.18.30 converts `tools.skill=false` into `permission.skill=deny`; explicit permissions take precedence. System-prompt construction returns before rendering skills when that permission disables the tool. Thus **A3 is a direct alternative, not an inferior unverified mechanism**. [Upstream config.ts:525–535](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/config/config.ts#L525), [system.ts:100–109](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/session/system.ts#L100)

Offline inspection found an installed Homebrew 1.18.30 executable, not inspectable local TypeScript. Actual suppression under merged global/project/agent settings remains **UNVERIFIED**; the proposed capture gate is necessary.

Both generated configurations share `_emit()`, so one emitter change can cover them. The existing top-level-key test must also change deliberately. [Emitter:5]($STACK_REPO/configgen/emitters/opencode.py:5), [test_opencode.py:33]($STACK_REPO/configgen/tests/test_opencode.py:33)

**P5 — Prefer discovery isolation when retaining skills matters.** Tagged source provides:

- `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=true`: excludes `.claude` discovery while retaining `.agents`; directly addresses the captured collisions.
- `OPENCODE_DISABLE_EXTERNAL_SKILLS=true`: excludes both external trees; keep curated opencode-native skills.
- `skills.paths`: **additive**, not an allowlist or exclusion mechanism. An empty list does not suppress default discovery.
- Avoid the broader `OPENCODE_DISABLE_CLAUDE_CODE` merely to fix skills: it also disables Claude prompt loading.

[Runtime flags:18–27](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/effect/runtime-flags.ts#L18), [skill/index.ts:173–205](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/skill/index.ts#L173)

Pruning UUID directories is temporary housekeeping. Deterministic duplicate resolution upstream would preserve discovery, but is a larger client change.

**P6 — “Benchmarks unaffected” is too broad.** Fresh per-item sessions avoid this particular cross-process reuse failure. They do not make removal of system instructions and a tool output-neutral. The harness isolates only `XDG_DATA_HOME`, inherits the remaining environment, and normally uses `--pure` to suppress plugins—not a demonstrated skill-discovery isolation policy. [Harness:237]($STACK_REPO/benchmark/run_opencode_probe.py:237), [Harness:267]($STACK_REPO/benchmark/run_opencode_probe.py:267), [Harness:546]($STACK_REPO/benchmark/run_opencode_probe.py:546)

Record a new scaffold identity: effective skill policy, client version, configuration hash, and captured system/tool hashes. Preserve old results as historical; do not pool them silently. The harness still pins **1.18.15**, and its recorded runtime fields omit skill policy. [Harness:57]($STACK_REPO/benchmark/run_opencode_probe.py:57), [Harness:529]($STACK_REPO/benchmark/run_opencode_probe.py:529)

## B assessment (sizing, design, hooks, risks)

**P7 — Sizing: approximately correct, with units and exclusions clarified.**

The config has 64 layers, every fourth full attention: **48 linear layers**. Each recurrent state is `(1,48,128,128)` fp32:

| Storage | Calculated payload |
|---|---:|
| One layer | 3,145,728 bytes |
| 48 recurrent states | 150,994,944 bytes = 151 MB = 144 MiB |
| Convolution states, assuming bf16 | approximately 2.95 MB |
| One complete snapshot | approximately 154 MB |
| Three snapshots | approximately 462 MB |
| Four additional periodic snapshots | approximately 616 MB |

Evidence: [config:4017]($STACK_WORKDIR/optiq_out/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/optiq_mixed/config.json:4017), [config:4089]($STACK_WORKDIR/optiq_out/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/optiq_mixed/config.json:4089), [gated_delta.py:435]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/gated_delta.py:435), [language.py:1132]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:1132).

These are tensor payload estimates, not measured incremental footprint. Aliasing, temporary state, allocation behavior, and additional retained KV require measurement.

**P8 — Design: the stated thinning guarantee is false.**

For new prompt length \(N\), divergence \(d\), restored checkpoint \(s\):

\[
\text{prefill work}=N-s=(d-s)+(N-d).
\]

Only **extra replay of unchanged tokens**, \(d-s\), can be bounded by checkpoint spacing. The changed suffix \(N-d\) must always be processed. At a midpoint edit of a 64K prompt, at least 32K tokens require processing; acceptance’s total-prefill bound of 16K is impossible.

Nor does “drop every other checkpoint” prove spacing ≤ prefix/K. With K=4, checkpoints at 4K/8K/12K/16K become 8K apart after thinning, while prefix/K near the next insertion is only about 5K. Thinning also temporarily leaves fewer than K entries. Specify the retained parity, endpoints, next-capture schedule, maximum gap—including zero and the tail—and an honest bound. [Proposal:46]($STACK_REPO/docs/specs/c103-prefix-drift.md:46)

**P9 — Design: divergence handling must precede new captures.** Existing `update()` compares old/new token histories and drops snapshots beyond divergence **after generation**. That works for its current boundary capture but is unsafe to reuse unchanged for eager periodic insertion:

- Old later entries can obstruct earlier captures because capture requires monotonically increasing offsets.
- End-of-request invalidation can delete newly captured, valid checkpoints beyond the old divergence.
- Selecting between two rings must choose the greatest valid offset across both.
- Clear, truncation, cold fallback, eviction, and failure paths must retire both rings and reset/rebase the thinning schedule.

Use explicit request/prefix ownership: invalidate stale history before capturing the new branch, then commit its checkpoints consistently. [common.py:743]($HOME/ws/mlx-vlm/mlx_vlm/generate/common.py:743), [snapshot.py:79]($HOME/ws/mlx-vlm/mlx_vlm/snapshot.py:79), [snapshot.py:125]($HOME/ws/mlx-vlm/mlx_vlm/snapshot.py:125)

**P10 — B1 is useful, but capture alone does not fix M45.** The measured first follow-up reuses only 12 tokens. [M45:41]($STACK_REPO/benchmark/results/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/session_cache.m45c2.json:41)

The asymmetric path explicitly restores the earlier anchor, trims KV, and saves only tokens preceding the latest user message. A later DeltaNet-only snapshot cannot reconstruct discarded KV or extend prefix matching beyond saved token IDs. Therefore **“anchors unchanged” conflicts with the claimed fix**. Design how prompt-end KV, token history, and recurrent state remain jointly reusable, while preserving fallback for re-rendered user content. [dispatch.py:1386]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:1386), [common.py:716]($HOME/ws/mlx-vlm/mlx_vlm/generate/common.py:716)

Prompt-end capture is not redundant with periodic sampling: arbitrary prompt ends miss the grid and thinning can remove nearby entries. It can share storage when offsets coincide, but needs an explicit retention policy.

**P11 — Hooks: capture inside `ar.py`, with exact offsets.**

- Periodic capture: after chunk evaluation and absolute-offset advancement at [ar.py:662]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:662), before the next model call. Combine periodic, APC, and anchor landing boundaries when choosing chunk length at [ar.py:630]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:630). Use `initial_cache_offset + processed_tokens`.
- Prompt-end capture: after the final prompt `_step()` at [ar.py:707]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:707), before speculative decoding or ordinary decode lookahead.
- **Do not copy dispatch’s first-yield capture timing blindly.** Ordinary generation calls `_step(y)` before yielding its first token; cache state has already advanced. Its “not yet written” comment is misleading for this path. [ar.py:735]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:735), [dispatch.py:1254]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:1254)

Define behavior when chunking is disabled, the suffix is one token, generation ends immediately, and MTP is enabled.

**P12 — Risks: the memory gate undercounts and uses the wrong safety signal.** Two retained periodic rings add approximately **1.23 GB**, before any separately retained B1 state or extra KV. Keeping only one ring eventually does not bound the transient peak while another session prefills.

Current shrink-on-retire shrinks KV allocations and explicitly skips DeltaNet state; global recency belongs to the session manager. Headroom eviction runs at session lookup and cannot alone prevent subsequent capture growth. [common.py:625]($HOME/ws/mlx-vlm/mlx_vlm/generate/common.py:625), [session_manager.py:393]($HOME/ws/mlx-vlm/mlx_vlm/server/session_manager.py:393)

The baseline already recorded **90.6% system memory use, 6.5 GB available, and 1.9 GB swap**. A worker-only ceiling of 42.6 GB is insufficient. Measure full-stack pressure, swap growth, allocation peaks, and alternating-session latency. [Notebook:3927]($STACK_REPO/docs/lab-notebook.md:3927)

## Ranked recommendation

**P13 — Shipping order:**

1. **Client discovery isolation**, preferably the narrow Claude-skills flag for this captured cause; preserve desired curated skills.
2. **Explicit `permission.skill: deny` or A1**, if intentionally running without skills. Ship only after effective-config and request-capture verification; version the benchmark scaffold.
3. **Separate B1 redesign**, including KV/token retention and exact pre-decode capture. This addresses a measured user-visible cost.
4. **Periodic checkpoints**, initially opt-in, after specifying and proving lifecycle, spacing, and memory bounds.

I would refuse B as written, a larger FIFO as the C103 fix, pruning as the durable solution, and claims that two smoke items establish benchmark comparability.

## Missing criteria

**P14 — Client acceptance:** more than two process starts with both duplicate trees present; assert block/tool absence or canonical locations; test effective agent/project overrides and both shipped/benchmark configurations. Replace fixed `cached_tokens ≥ 10000` with reuse relative to the **new measured token LCP**—removing skills may shrink the prefix below that threshold. [Proposal:35]($STACK_REPO/docs/specs/c103-prefix-drift.md:35)

**P15 — Snapshot correctness:** boundary tests at `s−1/s/s+1`, before the earliest checkpoint, repeated edits, truncation, append-only growth, ring saturation/thinning, cancellation, cold fallback, eviction/recreation, and alternating sessions. Assert matching token prefix, KV offset, recurrent state, and cold-reference continuation—not merely successful generation.

**P16 — Performance and memory:** distinguish unavoidable suffix processing from extra replay; test every gap and thinning transition, not one midpoint. Pre-register capture overhead, TTFT regression limits, retained and transient bytes, full-stack swap/pressure limits, and the loss of reuse when M=1 discards another session’s checkpoints.

**P17 — Numerical and provenance coverage:** MTP on/off, asymmetric thinking/tool continuations, actual RAG re-rendering, chunked/unchunked prefill, vision fallback, and exact prompt-end offset. Changing chunk boundaries can change numerics; the existing provenance code already treats `prefill_step_size` as output-determining. Specify seeds, equality/tolerance rules, and checkpoint-policy fingerprinting. [provenance.py:302]($STACK_REPO/benchmark/bench/provenance.py:302)