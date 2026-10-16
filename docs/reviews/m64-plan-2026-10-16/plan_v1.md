# Plan under review (v1, 2026-10-16) — harness versioning, M64 shape, guard residual, aborted chain

Context: repo mlx_local_stack (selects local LLMs for 256K agentic coding on an M5 Max; a tg1 "chain" runs each
model through the opencode v2 coding agent on 22 Python + 21 Go Exercism-style items, k=2 sessions (s1, s2) + a
reload control, scored by execution, ranking key acc_strict@budget, deltas by two-stage cluster bootstrap with TOST
±5pp). Two boxes: m5max (64 GB, has codex) and m5max-128 (128 GB, the chain box, has cursor-agent). origin/main =
170af9c0. Key files: benchmark/bench/tg1_runner.py (the tg1 probe body; computes probe_code_sha256 at :319-342 and
scaffold_policy_sha256 at :303-316, which must equal a hard-coded CAMPAIGN_POLICY_SHA256 at :36 and in
benchmark/bench/chain_ops.py:20), benchmark/run_opencode_probe_v2.py (pins PINNED_OPENCODE_VERSION_V2="2.0.20" and
OPENCODE_V2_EXE_SHA256), benchmark/run_dsh_probe.py (frozen, pins 0.1.2-rc.1), benchmark/chains/c147/run_tg1_chain.py
(chain runner; hard-wired to the two picks and to opencode: LEGS/PICK1/PICK2, RUNTIME_PINNED in chain_ops.py:717-719,
verify_manifest :487-520, A4 gate opencode-only), benchmark/bench/proc_guard.py (ProcessGuard; cleanup() and the C157
unreadable-process reconcile), docs/PLAN.md row M64, docs/open-questions.md C159/C161/C164/P299/C157.

Facts:
- Harness release rate, last 30 days (npm): Pi `@earendil-works/pi-coding-agent` 15 releases (1.3.0 on 2026-10-15);
  dsh `@deepseek-ai/dsh` 13 (0.2.0-rc.2 / 0.2.1-alpha.4; we pin 0.1.2-rc.1); opencode: the benchmarked binary is
  2.0.20 under $STACK_WORKDIR/opencode-2.0.20 (distribution line not yet re-checked; npm `opencode-ai` shows 1.19.2 +
  daily dev builds). Operator 2026-10-16: "pinning harnesses won't work ... these get updated often and we need to be
  able to move on."
- Current policy (P299 part 2): sha-pin the harness per chain; each release = a planned identity boundary with a
  "cheap re-baseline". In practice the re-baseline is a full k=2 chain of both picks ≈ 18 h.
- C164 (operator 2026-10-16): the m5max-128 picks re-record chain (`$STACK_WORKDIR/c144-base`, probe d4319705…) was
  to be the M64 opencode baseline; P311 (split probe identity into generation_code_sha256 vs scoring_code_sha256)
  approved; M64 spec to start; no filler chains.
- M64 (PLAN): add Pi and dsh as scaffold arms of the tg1 chain on the same items/seeds/budgets; PASS = strict
  accuracy TOST ±5pp per pick AND lower tokens/task; subjective axis = mean of a two-judge blind pairwise panel (codex
  gpt-6.1-sol + Claude Fable 5.1) over both-pass items, both orders, length-adjusted (C161, AGENTS.md).
- Pi adapter facts (source-read): no max-turns setting; json mode can exit 0 on provider error; retries on (3) by
  default; auto-compaction on by default; contextWindow default 128000; bash tool has no default timeout; sends the
  `developer` role + `store:false` to unknown OpenAI-compatible URLs; `--offline`/PI_TELEMETRY=0; PI_CODING_AGENT_DIR,
  `-ne -ns -np -nc --no-mcp`; `samplingParams` merged into the body; session jsonl per run; JSONL events with
  message_end usage, tool_execution_end, agent_settled.
- The c144-base chain ABORTED 2026-10-16 05:15Z (rc 2): s2 pick-2 Go leg, `cleanup uncertain`: pid 89820,
  `start order unreadable`, still present at the guard's final reconcile (gone minutes later); neighbours in the
  orphan list are macOS system services (mdworker_shared, NetFS PlugInLibraryService, helpd), all ppid 1. Completed
  and validated: s1 for both picks (43+43 items) and s2 pick-2 Python. Resume = M63 precedent: archive chain.json/
  out/rc/RUNLOG and s2/ into archive.attemptN-<reason>, relaunch `chain s2 reload` (s2 re-runs from scratch) ≈ 10 h.

## P315 — Float the harnesses; fix the version only inside a comparison
1. Snapshot per chain: the runner resolves the current ADOPTED snapshot of each harness (version + exe sha, installed
   under $STACK_WORKDIR/<tool>-<ver>) at chain start, records it, refuses to switch mid-chain.
2. Every comparison runs its arms together in one chain on one snapshot (paired by item and seed, legs interleaved);
   no stored baselines; a release never forces a re-baseline; old conclusions stay "as of version V"; only
   cross-version pooling is lost.
3. Harness version leaves scaffold_policy_sha256 and becomes a per-row `harness` block (tool, version, exe sha) —
   a covariate; rows pair only within a chain; across chains descriptive only; README evidence labelled by version.
4. Adoption by canary, not calendar: `scripts/harness_refresh.py <tool>` installs the latest, runs the adapter's
   offline contract tests (mock provider, recorded event fixtures, first-request wire capture: sampling fields,
   roles, max-tokens; tool/extension surface; no egress), a 2-item live smoke when the box is free (also re-checks
   C154-type client timeouts); on pass writes `$STACK_WORKDIR/harness_current.json`. A failing version is not
   adopted; the last good one stays.
5. Adapters declare a supported range proven by the canary; unknown event shapes fail closed.
Costs: (a) each comparison re-runs its reference arm (≈ +50% GPU per comparison); (b) the canary catches breakage,
not small behavioural drift — only paired same-chain runs can; (c) changes C164 for M64: c144-base becomes a
descriptive P223 repeat; M64 runs opencode + Pi + dsh together on current snapshots, per pick 3 arms ×
(s1 + s2 + reload) ≈ 27 h for both picks.

## P316 — M64 spec follows P315
Core = arm-aware chain runner (interleaved opencode/Pi/dsh legs per session; per-arm scaffold label, policy sha,
RUNTIME_PINNED map, stem/evidence root, A4-equivalent per client) + `harness_refresh.py` + canary contract tests;
adapters target current versions; dsh rebuilt rather than unfrozen (0.1 → 0.2 likely breaking). Leave the opencode
tg1 path itself untouched where possible (regression risk to the reference arm).

## P317 — Guard residual (newly found bug, own proposal)
In ProcessGuard.cleanup(), a same-uid process whose start order is unreadable is today uncertain unless it vanishes
(C157, C151 R10). Start order only decides "older than the guard" (protected → skip). Every outcome that could make
the process OURS is decidable without it: tracked (match by pid) → uncertain; path-attributed (cwd/cmdline under the
run's roots) or attribution unreadable → uncertain; otherwise → record as an orphan with a reason, NOT uncertain —
the same outcome a readable young ppid==1 untracked process gets today. Test-first, cold review; proc_guard.py is
probe identity.

## P318 — The aborted chain
If P315(c) is taken: do not resume c144-base (s1 = k=1 descriptive repeat of both picks on the new identity is
already in hand); build P317 + the M64 spec; the next GPU job is M64's canary/smoke. If C164 stands instead: resume
s2 + reload (≈ 10 h) on the unchanged identity d4319705 (P317 waits so s1/s2 share one identity).

## Lead recommendation
Take P315 + P316; stop the chain as is (P318 first branch); build P317 next; write the M64 spec on the
floating-version design; next GPU job = M64 canary + smoke.
