# Agreed plan (2026-10-16) — v3 + round-3 edits of both reviewers

Round 3: codex `gpt-6.1-sol` AGREE WITH CHANGES; Cursor `gpt-5.6-sol-high` AGREE WITH CHANGES. Every requested edit is
applied below (marked ▲); loop closed by lead verification against both round-3 reports. The operator approves:
E1 (methodology), E2 (a SPECIFICATION TO WRITE — no build/launch approval), G1 (proposal), R1 (conditional), and
the doc amendments named in each.

## E1 — Decision epochs (methodology)
1. Snapshot per harness: content-addressed directory `$STACK_WORKDIR/harness/<tool>/<sha>`; the sha covers version,
   tarball integrity / bottle sha, resolved dependency tree, runtime version, extension + plugin inventory, generated
   config, system prompt and tool schemas.
2. ▲ `epoch_id` = sha256 of a canonical manifest: JSON with `schema_version`, tools sorted by name, each
   `{tool, snapshot_sha}`, sort_keys, no whitespace. One `epoch_id` per decision family.
3. ▲ Identity is enforced PER ARM: each family freezes a mapping `arm_id → generation_identity_sha256` (adapter
   generation code + that arm's snapshot; P311) plus its `scoring_code_sha256`. `chain.json` resolves snapshots once;
   entry, every leg (incl. resume) and exit verify each arm against ITS registered identity; `validate_leg` and every
   comparison refuse a deviation from the registered mapping (registered treatment differences between arms are
   explicit and allowed). Adoption is atomic and never retargets an active chain.
4. Decision family = all arms and models of one decision incl. confirmations; ONE epoch.
5. Cross-epoch results are descriptive. Adoption anchors never authorize transitive rankings. A selection decision
   requires all finalists under one epoch, or a separately approved, adequately powered transport design.
6. Adoption gate: offline contract tests on the exact snapshot (mock provider, recorded events, first-request wire
   capture, tool/extension surface, accelerated client-timeout contract) — failure → REJECT. Bridge: old vs new on the
   same loaded instance and seeds, 2 models, 8–12 pre-registered sensitive anchors; red flags: a new nonconv kind, a
   client cut where old converged, a pass→fail flip on ≥ 2 anchors, ▲ per model the ratio of summed completion tokens
   over the anchor set outside 0.67–1.5, ▲ any censored/incomplete accounting in either snapshot (not evaluable) —
   any red flag → HOLD + investigate; else ADOPT for new families only. Never an equivalence claim. Bridge cost
   unmeasured until the first one runs.

## E2 — M64 specification requirements (spec to write → its own cold review → operator go)
1. Primary estimand: operational scaffold performance under common configured ceilings; client cuts count as failures;
   unequal effective opportunity disclosed per arm. Matched-budget capability out of scope unless every arm passes an
   accelerated timeout contract and release-specific long-request evidence.
2. Controls (deployed sampling, paired seeds, thinking 81,920 / max 102,400 + resolved headroom, context, M62 ceilings,
   client retries off with every transport failure counted (C165 2b), ▲▲ compaction ON + recorded (C165 2b; was "off"), no ambient instructions, equal harness-enforced shell deadline, one web policy,
   M50 entry/exit, registry/model/predictor/worker identity, corpus/grader integrity, session routing, cancellation
   reconciliation). ▲ A **proof matrix** assigns each invariant to its enforcement point and evidence boundary — wire
   capture per request (sampling, seeds, budgets, roles), lifecycle checks (M50, worker identity), configuration
   hashes (ambient instructions, carriers), process supervision (shell deadline, sandbox). Treatment = native system
   prompt, tool schemas, loop logic (hashed); native `developer`-role / thinking-history behaviour is treatment, server
   acceptance verified by contract test.
3. ▲▲ **Web policy RULED (C165): web allowed** — an expected capability (C141/M61); every arm keeps its native web
   capability and shell networking; the P201 post-hoc audit covers every arm's web tool calls and shell networking
   (cheat → re-run procedure); opencode's deny patterns get a per-arm equivalent where the client supports one,
   otherwise disclosed. ▲▲ Capability principle (C165 2a): each arm runs its normal default tool set, nothing added
   or removed (Pi: vanilla, web via shell only; opencode: webfetch + shell; dsh: native web + shell); differences are
   treatment, disclosed per arm; loop-hygiene controls of E2.2 unchanged. The sandbox text below is SUPERSEDED (kept for the record): lead had recommended no web,
   enforced by a macOS sandbox profile on the client process tree. ▲ Mandatory conformance positives before the boundary is
   accepted: router port allowed; other loopback ports denied; external hosts denied; proxy/alternate-destination
   attempts denied; inheritance by model-controlled shell children (incl. detached ones) proven. Socket sampling is
   observation only. Parity: old opencode tg1 carrier reproduces the old path; the deny-web carrier differs only by the
   approved restriction.
4. Tokens: primary = completion tokens (visible + reasoning) per assigned task, all tasks, failures included; ▲ every
   task-attributable LLM request counts (auxiliary/title/sub-requests included). Superiority needs complete
   per-request server receipts (build item: mlx-serve fork logs usage for every request incl. client-cut ones) or
   direction-establishing bounds; otherwise "not established". Union-exclusion = sensitivity only.
5. Inference: ▲ ONE confirmatory family — Holm over all named hypotheses: 4 accuracy (pick × {Pi−opencode,
   dsh−opencode}; each an intersection-union test whose p-value is the maximum over its language × session cells),
   4 token, 4 subjective. Joint M64 PASS rule per arm/pick stated in the spec. Interval methods validated by simulation
   (coverage, TOST error) under sparse/zero discordance, unseen discordance and shared loaded-instance effects;
   session-specific inference reported; < 80% simulated power for ±5pp → enlarge N or relabel M64 an estimation screen
   (decided before launch).
6. Subjective (C161): code-quality rubric; pair-specific both-pass items; judge-specific + two-judge mean; both orders
   as repeated measures, disagreement → tie; missing judge → pair unscored, coverage reported; item-clustered,
   tie-compatible length adjustment; ±5pp preference margin; item-cluster bootstrap CI; minimum coverage stated.
7. Schedule: ▲ block sizes chosen and stated; permitted Williams sequences (all six arm permutations) RANDOMLY
   allocated to blocks × sessions × picks with a recorded seed; residual allocation stated; cache reset + warm-up per
   arm switch; realized order artifact; one loaded worker per (pick, session); fresh session IDs;
   `MLX_VLM_CACHE_SESSION_MAX=1` verified.
8. Work order: spec → P311 split → `ArmAdapter` contract (proof-matrix fields mandatory; one accounting contract
   reconciled against server receipts; exit 0 never success) → opencode wrapped unchanged + parity → Pi adapter → new
   `run_dsh_probe_tg1.py` (M35 frozen) → per-arm injected positives → snapshot/adoption tooling → seeded-random 5-item
   smokes → cost estimate → chain. Provenance (dated URLs, package metadata, lockfiles, snapshot shas) in the spec.
9. ▲ Approval of E1/E2 authorizes amending `docs/PLAN.md` M64 (baseline: own contemporaneous opencode arm, not
   c144-base; PASS rule per E2.5) and supersedes C164's P310 ruling.

## G1 — Guard reconciliation (proposal; own open question; built and reviewed off-chain)
1. Every live eligible unreadable-order process stays uncertain (C151 R10, `test_c151_start_time.py:243`).
2. ▲ One monotonic, global deadline (≤ 10 s) starting at cleanup's first reconciliation; anything unresolved at the
   deadline → uncertain.
3. ▲ **Recovered readability alone discharges neither an ownership-unresolved recorded root nor any recorded
   descendant obligation.** Each is resolved as gone, protected/pre-existing, or attributed (tracked/path) and
   reconciled; otherwise uncertain at the deadline. This REVISES shipped C157/P306 behaviour: `tick()` currently
   retires a record once its process reads fine, and `_reconcile_unreadable` skips descendants of a readable
   same-identity root — both must keep the obligations instead.
4. Exact identities (pid, start_time); overflow and unknown-identity stay fail-closed.
5. Tests: ▲ unreadable→readable, reparented, path-negative root (must stay uncertain); descendants of a recorded
   unreadable root spawned after the last tick; vanished parent; pid reuse; retained descendants; deadline expiry.
6. **G2 (separate, pre-existing):** a readable, never-recorded, young, untracked ppid-1 process that is ours is today a
   reasonless orphan (module contract: best-effort attribution). ▲ Closing it requires a separately validated
   ownership mechanism; spawn-time containment/tagging is one candidate, not a demonstrated solution (a descendant can
   `setsid()`). G2 does not block G1 (both reviewers, round 3).

## R1 — Resume the aborted c144-base chain (conditional)
Precondition: the operator explicitly amends C164 (E2.9) and the handoff is reconciled (it still says "live"). A
bounded ≈10 h evidence investment; rows become descriptive / power-input evidence. Checklist:
1. ▲ Verify the abort: `driver.chain.rc` = 2, `chain.json` status finished, no router on :8000, no surviving
   `opencode run` / worker / probe processes (by PID), `RUNLOG.md` CHAIN ABORT line.
2. Verify the checkout: this box's pre-merge main checkout; `run_opencode_probe_v2.py --print-identity` gives the full
   `probe_code_sha256` `d431970599f696d4b79c76e1923524a6a4f982e7f60f023d37fa5e16c36172ea`; carrier/plugin shas,
   registry, runtime provenance unchanged; power and docker gates.
3. ▲ Complete hashed attempt record FIRST: `$STACK_WORKDIR/c144-base.archive/attempt1-guard-residual/` with a sha256
   manifest of every file of the attempt — a COPY of `s1/` (which stays active) and of the referenced transcript /
   evidence paths, plus `chain.json`, `driver.chain.out/.rc`, `RUNLOG.md`, `s2/` (partial s2 JSONL, manifests, ACKs,
   logs, receipts) and the aborted a4 logs. Verify the archive against the manifest; only then MOVE the conflicting
   active outputs (`chain.json`, driver files, `RUNLOG.md`, `s2/`) out of the out-root.
4. ▲ Launch (full invocation): `$STACK_WORKDIR`-relative launcher running
   `.venv-bench/bin/python benchmark/chains/c147/run_tg1_chain.py chain s2 reload --probe-code-sha
   d431970599f696d4b79c76e1923524a6a4f982e7f60f023d37fa5e16c36172ea --out-root $STACK_WORKDIR/c144-base` with
   `$HOME/.orbstack/bin` on PATH, detached; RUNLOG first line records the archive path (links the new s2/reload to s1).
