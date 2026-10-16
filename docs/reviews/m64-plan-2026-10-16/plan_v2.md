# Plan v2 (2026-10-16) — revised after round-1 reviews (codex gpt-6.1-sol: AGREE WITH CHANGES; Cursor gpt-5.6-sol-high: DISAGREE)

Context and facts are as in v1 (repo at the reviewed commit; key files tg1_runner.py, run_opencode_probe_v2.py,
run_dsh_probe.py, chains/c147/run_tg1_chain.py, chain_ops.py, proc_guard.py; PLAN M64; C154, C161, C164, P299, P311).
Corrections accepted from round 1: opencode's distribution is the SHA-pinned Homebrew bottle
(`scripts/install_bench_opencode.sh`); release counts and Pi facts get dated source URLs + package metadata in the
M64 spec (they were gathered from the npm registry and a source read of earendil-works/pi at 4954d76); the reload
leg is a seeded 5-item Python pilot of pick 1, not a full session. Operator constraint: harness pins cannot be held
for long — "these get updated often and we need to be able to move on."

## E1 (replaces P315) — Decision epochs, not long-lived pins and not free floating
1. **Epoch** = one immutable harness snapshot vector: per harness tool, version, npm tarball integrity + resolved
   dependency lock/tree hash (or the Homebrew bottle sha for opencode), executable sha, runtime (node) version,
   generated config + system-prompt + tool-schema hashes. Installed immutably under `$STACK_WORKDIR/<tool>-<ver>`,
   recorded in `chain.json`, verified at chain entry, before every leg (including resume) and at exit.
2. **Decision family** = all arms and models of one decision (e.g. M64's scaffold decision; one model-selection
   round incl. its follow-up confirmations). A family runs within ONE epoch, contemporaneously. No stored baselines
   reused across epochs.
3. **Between families we move to the latest releases** (answers the operator: no long pin). Adoption gate per new
   snapshot: (a) offline contract tests for that EXACT snapshot (mock provider, recorded event fixtures, first-request
   wire capture of sampling fields, roles, max-tokens, tool/extension surface, no egress) — an exact allow-list, never
   a "supported range"; (b) a bridge: old vs new snapshot interleaved on the same loaded instance and seeds, two
   models, 8–12 pre-registered sensitive anchors (long request, many turns, tool-heavy, timeout-prone, known C154
   items, provider error). The bridge detects gross drift only and is labelled so; it never certifies equivalence.
   Outcomes: adopt / fix adapter / hold the old snapshot.
4. **Never pool across epochs; no transitive rankings across epochs without bridge evidence** (overlap arms).
   README evidence carries its epoch label; older evidence is not deleted, it is "as of epoch E".
5. Harness snapshot is part of the GENERATION identity (P311): `generation_identity_sha256` = adapter code + snapshot
   vector + config/prompt/tool-schema hashes; `scoring_code_sha256` separate. Not a statistical covariate.
Cost: a bridge ≈ 1–2 h GPU per adoption instead of an ≈18 h re-baseline; every decision family re-runs its own
reference arm.

## E2 (replaces P316) — M64 design
1. **Estimand: controlled-loop scaffold comparison.** Held fixed across arms (verified on the wire per request):
   deployed server sampling (`params_for(model, "deployed")`), paired `sampler_seed` schedule, thinking ON with
   resolved budget 81,920 and max 102,400, context allowance, M62 token/turn ceilings, ONE logical attempt (client
   retries off), auto-compaction off, no ambient instruction files (Pi `-nc`, hermetic HOME/config), shell-tool
   deadline equal across arms (enforced by the harness, not by trusting the client), the same web policy for all arms
   (recommend: NO web for every arm — Pi has no fetch tool natively, dsh's web tool was disabled in M35; the opencode
   arm then uses a tg1 carrier with webfetch denied, i.e. a new opencode scaffold label; operator decision), egress =
   loopback only (C160 socket sampling in every smoke). **Treatment** = each scaffold's native system prompt, native
   tool schemas and loop logic — hashed and disclosed. The `developer` role / thinking-history echo behaviour is
   recorded per arm (it affects templates and the server session cache).
2. **Endpoints, pre-registered:** primary contrasts Pi−opencode and dsh−opencode per pick (Pi−dsh exploratory);
   per session and per language paired `acc_strict@budget`, two-stage cluster bootstrap, TOST ±5pp, explicit
   "inconclusive"; Holm over 2 picks × 2 contrasts. Tokens over ALL assigned tasks (input / cache / output / reasoning
   separately; failures and auxiliary requests included), superiority CI excluding 0 (no minimum effect unless the
   operator sets one). Censoring (C154 and any client cut): incidence as its own endpoint per arm; union-exclusion
   sensitivity for accuracy AND tokens; censored-token lower bounds from server-side accounting. Power simulation
   from the observed paired discordance (P223, M63, c144-base) BEFORE launch; if ±5pp TOST is unreachable the spec says
   so up front. Subjective (C161): two-judge blind pairwise over PAIR-SPECIFIC both-pass items, judge-specific results
   + their mean, both orders, length adjustment pre-specified (logistic regression of preference on log length ratio;
   adjusted intercept), ties as 0.5, coverage and exclusive solves reported.
3. **Schedule:** one loaded worker per (pick, session) shared by its three arms; arm order counterbalanced with a
   three-arm Williams design across item blocks × sessions × picks; identical item order and seeds; fresh session IDs,
   no cross-arm resume; `MLX_VLM_CACHE_SESSION_MAX=1` verified; per-arm start state logged. Wall time descriptive;
   latency, if ever a decision axis, gets its own order-balanced capture under the power/idle rules.
4. **Architecture and order of work:** (1) M64 spec with estimand, fairness matrix, acceptance and power; cold review
   → operator go. (2) P311 identity split. (3) `ArmAdapter` contract: command construction, identity fields, preflight
   (A4-equivalent per client), event normalization into one accounting contract reconciled against server usage,
   transport classification (exit 0 never means success), evidence/transcript validation, cancellation/cleanup
   semantics. (4) Wrap the UNCHANGED opencode generation path in a thin adapter; prove parity with the existing chain,
   replay and injected-positive tests. (5) Pi adapter. (6) New `run_dsh_probe_tg1.py`; M35 `run_dsh_probe.py` stays
   frozen for historical reproduction. (7) Per-arm injected positives (stall, loop, hard ceiling). (8) Snapshot +
   adoption tooling (E1.3). (9) Seeded-random 5-item smoke per arm → cost estimate with heavy-tail and C154 allowance.
   (10) The M64 chain.
5. **Cost:** the round-1 estimate (27 h) was low; current best guess 38–42 h GPU before heavy tail for 3 arms × 2
   picks × (s1, s2) + reload; the smokes fix it.

## G1 (replaces P317) — guard residual, fail-closed kept
P317 is WITHDRAWN (both reviewers: an unreadable-order process can be ours and untracked/path-negative — e.g. a
helper whose order read failed before ancestry propagation, or a descendant spawned after the last tick). New, smaller
proposal for later (never mid-chain): keep every live eligible unreadable-order process uncertain, but extend the final
reconciliation with a bounded delayed re-check (e.g. up to 10 s) because the observed offenders (mdworker / XPC
services) exit within seconds; match tracked identities by (pid, start_time), never pid alone; add the
unreadable-untracked-owned-descendant regression test. Own open question; test-first; cold review.

## R1 (replaces P318) — resume the aborted c144-base chain now, unchanged
The GPU is idle for the whole E2 build (≈2+ days), so resuming costs no decision time. Archive the failed attempt
(M63 precedent: chain.json/out/rc/RUNLOG/s2 → `archive.attempt1-c157-residual`), relaunch `chain s2 reload` on the
unchanged identity `d4319705…` (≈10 h; s2 re-runs from scratch). Gains: the second loaded-instance session, the reload
control, a complete repeat of P223's design on a new identity, and the paired discordance estimates the E2 power
simulation needs. Status: descriptive / power-input evidence, NOT the M64 baseline (C164's P310 is superseded by E1/E2:
M64 runs its own opencode arm contemporaneously). Risk: another guard-residual abort (≈1 per 16 legs observed); G1
waits so all legs share one identity.
