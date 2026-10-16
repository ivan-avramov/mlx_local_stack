You are a cold, adversarial methodology and design reviewer (round 3 of 3). Repository = current directory, branch m64-plan-review, read-only; never edit or run benchmarks. In docs/reviews/m64-plan-2026-10-16/ read: plan_v2.md, both round-2 reviews (round2.codex-gpt-6.1-sol.md, round2.cursor-gpt-5.6-sol-high.md), and plan_v3.md (below). Verify claims against code where possible.

Answer: (1) for each round-2 finding of BOTH reviewers: addressed by v3? (yes/partly/no, one line); (2) new problems in v3; (3) is G2's separation from G1 (the readable untracked ppid-1 owned-orphan residual, pre-existing) acceptable, or must it block G1? argue from benchmark/bench/proc_guard.py; (4) the minimum edits for you to AGREE that the operator can approve E1 (methodology), E2 (as a spec to write, not a build), G1 (proposal) and R1 (conditional). Be concrete; do not re-litigate settled points.
End with exactly one verdict line: "AGREE", "AGREE WITH CHANGES: <list>", or "DISAGREE: <reason>".

==== PLAN v3 ====
# Plan v3 (2026-10-16) — after round 2 (codex gpt-6.1-sol: AGREE WITH CHANGES; Cursor gpt-5.6-sol-high: DISAGREE)

v3 asks the operator to approve: E1 as methodology, E2 as a SPECIFICATION TO WRITE (no build or launch approval),
G1 as a proposal, R1 conditionally. Everything below is a requirement the respective spec must satisfy.

## E1 — Decision epochs (methodology)
1. Epoch = a set of content-addressed harness snapshots: per tool a directory `$STACK_WORKDIR/harness/<tool>/<sha>`
   whose sha covers version, tarball integrity / bottle sha, resolved dependency tree, runtime version, extension and
   plugin inventory, generated config, system prompt and tool schemas. `epoch_id` = hash of the per-tool snapshot
   shas. `generation_identity_sha256` = adapter generation code + snapshot sha (P311); `scoring_code_sha256` separate.
2. A chain resolves its snapshots ONCE into `chain.json`; entry, every leg (incl. resume) and exit verify them;
   `validate_leg` and every comparison/report refuse a generation-identity or epoch mismatch inside one family.
   Adoption is atomic (write a new snapshot dir + pointer) and never retargets an active chain.
3. Decision family = all arms and models of one decision, incl. its confirmations; it runs in ONE epoch.
4. **Cross-epoch results are descriptive. Adoption anchors never authorize transitive rankings. A selection decision
   requires all finalists under one epoch, or a separately approved, adequately powered transport design.**
5. Adoption gate for a new snapshot, objective outcomes: offline contract tests (exact snapshot; mock provider,
   recorded events, first-request wire capture, tool/extension surface, accelerated client-timeout contract test)
   — any failure → REJECT; bridge (old vs new snapshot, same loaded instance and seeds, 2 models, 8–12 pre-registered
   sensitive anchors incl. long-request and timeout-prone items) with pre-registered red flags (any new nonconv kind,
   a client cut where the old snapshot converged, a pass→fail flip on ≥ 2 anchors, a tokens/task ratio outside
   0.67–1.5) — any red flag → HOLD + investigate; otherwise ADOPT for NEW families only. Never an equivalence claim.
   Bridge cost: unmeasured until the first bridge runs (C154-prone anchors can take ~1 h each).

## E2 — M64 specification requirements (spec to write; then its own cold review and operator go)
1. **Primary estimand: operational scaffold performance under common configured ceilings.** Client cuts (C154 and
   any analogue) count as failures; unequal effective opportunity is disclosed per arm (cut incidence, censored
   requests). Matched-budget capability is OUT of scope unless every arm passes an accelerated timeout contract and
   release-specific long-request evidence shows it delivers the prescribed opportunity.
2. **Controls held fixed and verified per request on the wire:** deployed sampling, paired seeds, thinking budget
   81,920 / max 102,400 and resolved headroom, context, M62 ceilings, client retries off, compaction off, no ambient
   instructions, equal harness-enforced shell deadline, one web policy, M50 entry/exit, registry/model/predictor/worker
   identity, corpus/grader integrity, session routing and cancellation reconciliation. **Treatment:** native system
   prompt, native tool schemas, loop logic (hashed). `developer` role and thinking-history echo: each arm's native
   behaviour is treatment, but the server must accept it (verified in the contract test).
3. **Web policy — operator decision before the spec freezes. Lead recommendation: no web for every arm**, ENFORCED at a
   boundary (client processes run under a macOS sandbox profile allowing only loopback to the router port; shell tool
   children inherit it), with socket sampling kept as observation only. Parity: the old opencode tg1 carrier still
   reproduces the old path; the new deny-web opencode carrier differs only by the approved restriction.
4. **Tokens:** one primary quantity = completion tokens (visible + reasoning) per assigned task, all tasks, failures
   included; input/cache/reasoning reported as components. A token-superiority claim requires complete per-request
   server receipts (build item: mlx-serve fork logs usage for every request incl. client-cut ones) or bounds that
   establish the direction; otherwise "token superiority not established". Union-exclusion is sensitivity only.
5. **Inference:** four global primary claims (pick × {Pi−opencode, dsh−opencode}); each = intersection over its
   language × session cells (every cell must pass); Holm over the four claims, then separately over the token and
   subjective claims (three families, stated). Interval methods are validated by simulation for coverage and TOST
   error under sparse/zero discordance, plausible unseen discordance and shared loaded-instance effects; session-specific
   inference reported. If simulated power for ±5pp equivalence is < 80% at the planned N, the spec either enlarges N or
   removes equivalence from PASS and labels M64 an estimation screen — decided before launch.
6. **Subjective (C161):** a code-quality rubric; pair-specific both-pass items; judge-specific and two-judge mean; both
   orders as repeated measures, order disagreement → tie; missing judge → that pair unscored, coverage reported;
   item-clustered, tie-compatible length adjustment (cumulative-link or paired-difference model with item random
   effects); equivalence margin ±5pp on preference, CI by item-cluster bootstrap; minimum coverage stated.
7. **Schedule:** concrete constrained Williams schedule (all six arm permutations) over item blocks × sessions ×
   picks, residual allocation stated, cache reset + warm-up request per arm switch, realized order recorded as an
   artifact; one loaded worker per (pick, session); fresh session IDs; `MLX_VLM_CACHE_SESSION_MAX=1` verified.
8. **Architecture / order:** spec → P311 split → `ArmAdapter` contract (the fields of E2.2 as mandatory contract
   proofs; event normalization into one accounting contract reconciled against server receipts; exit 0 never success)
   → opencode wrapped unchanged + parity tests → Pi adapter → new `run_dsh_probe_tg1.py` (M35 frozen) → per-arm
   injected positives → snapshot/adoption tooling → seeded-random 5-item smokes → cost estimate → chain.
9. Provenance: dated source URLs, package metadata, lockfiles and snapshot shas in the spec.

## G1 — Guard bounded re-check (proposal; own open question; never mid-chain)
Keep every live eligible unreadable-order process uncertain (C151 R10, `test_c151_start_time.py:243`). Add ONE
monotonic, globally bounded reconciliation deadline (e.g. ≤ 10 s) for still-present unreadable roots; every recorded
descendant obligation survives root disappearance and is resolved within the same deadline; anything unresolved at the
deadline → uncertain. Exact identities (pid, start_time). Adversarial tests: post-last-tick descendant, reparenting,
vanished parent, pid reuse, retained descendants. No claim about what the offending processes were.
**Out of G1's scope, opened as G2 (pre-existing, separate question):** a READABLE, young, untracked ppid-1 process
that is ours (spawned after the last tick and reparented, cwd/argv outside the roots) is today only a reasonless
orphan, not uncertain. That is the guard's existing best-effort attribution limit (module docstring), independent of
unreadable start order; closing it needs ownership capture at spawn (e.g. process-group/session tagging of every
client/grader descendant). G2 is a design question for its own proposal, not a precondition of G1.

## R1 — Resume the aborted c144-base chain (conditional)
Requires the operator to explicitly amend C164 (its P310 "M64 baseline" ruling is superseded only if E1/E2 are
approved; c144-base then becomes descriptive / power-input evidence). Bounded evidence investment (≈10 h; a long tail
or another residual abort could overlap the next launch window). Checklist before launch:
1. Verified checkout whose `--print-identity` gives exactly `d4319705…` (this box's pre-merge `main`, unchanged
   main checkout), same carrier/plugin shas, registry and runtime provenance; clean :8000, no stray processes, power
   and docker gates.
2. Hashed archive inventory (sha256 per file) of the whole failed attempt moved OUT of the active out-root before
   relaunch (the runner rewrites `chain.json`): `chain.json`, `driver.chain.out/.rc`, `RUNLOG.md`, `s2/` (validated
   partial s2 + failed leg + manifests + logs + ACKs), the aborted a4 logs → `$STACK_WORKDIR/c144-base.archive/
   attempt1-guard-residual/`; s1/ and reload/ (absent) stay; referenced transcript/evidence paths recorded.
3. New invocation `chain s2 reload --probe-code-sha d4319705… --out-root $STACK_WORKDIR/c144-base` (s2 re-runs
   from scratch); RUNLOG records the archive path linking the replacement s2/reload to s1.
