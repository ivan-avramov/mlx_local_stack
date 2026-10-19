# Handoff — 2026-10-18 (night): resume in a FRESH session with the P369 fork fix round 7 (F23)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C181, C180, P385, P384, P383, P382, P381,
P380, P379, C179, P378, P377, P376, P375, P374, P373, P372, C178, P371, P370, C177, P369 …), then
`docs/specs/p369-mtp-certification.md` (v3), `docs/specs/p371-shared-runner-core.md` (PLAN v6, the new code layout),
`docs/specs/m65-tg2-corpus.md` (v5, T14 amended) and `docs/specs/m64-scaffold-arms.md` §4–§8, §12 (amended §5.6, §7, §8.2a).

## State of the world

- **Box `m5max-128`, idle:** no router (:8000 free), no chain, no test run, no Cursor run, no subagent. Docker (OrbStack) up; the agent
  shell needs `export PATH="$HOME/.orbstack/bin:$PATH"` and the machine config sourced
  (`. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`) or docker-backed tests skip.
- **Daily driver MTP-OFF (C177)** until P369 ships and is re-certified; then restore the three registry lines in `main_models.yaml`
  (`draft_kind` / `draft_model` for both B picks, Fable's `mtp_verify_scan: joint_v1`) + the `test_opencode_probe_seeding.py` expectation.
- **Branches / pushes:**
  - stack `main` pushed to origin through `4fde8482` (operator go 2026-10-18); later local commits need a new go.
  - `m64-build` and `tg2-step2` were fully merged (0 commits outside main) and DELETED locally and on origin (operator go 2026-10-18).
  - fork `../mlx-vlm` branch **`p369-mtp` at `e6d2c32c`, local only** in `$STACK_WORKDIR/worktrees/mlx-vlm-p369` — **push needs the operator**.
  - **Branch inventory (2026-10-18; operator: keep both parked branches):** `c152-alloc-tool-scope-wip` — 1 unmerged commit `a1e9901e`: the C152 tool-scope
    redesign + P273 variant the operator did NOT choose (waiver A won; P273 landed separately) — nothing to merge, kept as a record.
    `p297-uncertain-gone` — 3 unmerged commits (`510ad800` restart-after-uncertain-cleanup in the tg1 chain + fixture, `4e3a107a` /
    `fe626427` Cursor round 1 NOT CLEARED U1–U3) — rejected approach, nothing to merge; BUT its fixture (an M63 abort from a vanished
    Spotlight `mdworker`) is the P383 ambient-process root cause on the tg1 side, which C180 does not cover (see Next work 3).
    `evidence` — orphan branch of irreproducible evidence, keep.
  - Push rule (C176): WIP build branches may be pushed after each commit batch, privacy-scanned; `main`, the fork, tags, PRs need an
    explicit in-turn go (one go = one push).

## Next work, in order

1. **P369 fork fix round 7 — NEXT.** Cursor code reviews of `git diff 24551869...p369-mtp`: rounds 1–7 in `docs/reviews/p369-code-round{1..7}…`.
   Round 7 (narrow, on `9820e61c..e6d2c32c`) is **NOT CLEARED F23 only** (merge-blocking: `mlx_vlm/generate/dispatch.py:902-906` — an
   explicit `is_asymmetric_rendering=False` falls back to the session's legacy `True`; use a `None` sentinel so explicit `False` wins).
   F23 is WORK, not an operator call: today `is_asymmetric_rendering = bool(kwargs.pop("is_asymmetric_rendering", False))` and then,
   when False, falls back to `prompt_cache_state.is_asymmetric_rendering` — so the per-request `False` that round 6 (F23 residual) now
   passes is overridden by a stale session `True`, reopening the cross-request leak. Fix: pop with default `None`; an explicit
   True/False is authoritative; fall back to the session only when `None`; red test = request with explicit False on a session whose
   legacy flag is True must publish symmetric.
   Residual (cheap, fix in the same round): F27 (`dispatch.py:1630-1641` — breaking after the terminal chunk without closing leaves
   `_inflight_epoch` set, so the next request clears a valid published cache; clear the epoch before yielding terminal), F28
   (`dispatch.py:1619-1631` — stateless streams delay terminal delivery through APC cleanup; restrict pre-terminal draining to
   session-backed streams), F29 (`server/generation.py:2618-2639` — zero-budget requests log "Prefill started"), F30
   (`tests/conftest.py:85-87` — use `request.scope`, not the declared `fixturedef.scope`). Then a narrow confirmation round.
   - Fork rules: work in `$STACK_WORKDIR/worktrees/mlx-vlm-p369`; read its own `AGENTS.md` / `CLAUDE.md`; suite =
     `(cd mlx_vlm && ../.venv/bin/python -m pytest -q ./tests --ignore=tests/test_smoke.py)` from the worktree root, alone, twice back to
     back (identical counts required — last: 6107 passed / 16 skipped / 0 failed); `git add -A` BEFORE the six fork audits
     (`--upstream-ref 952d4f6b`; the worktree has no `upstream/main`); pinned black 26.3.1 / isort 5.13.2 (profile black) /
     autoflake 2.2.1 over touched files; **mlx stays 0.32.3** (0.32.4 breaks the verifier exactness tests).
   - Fork reviews: Cursor workspace `~/ws/mlx-vlm` (checked out at the base `24551869`) with the diff INLINE in the prompt; Cursor
     returns empty about every other run — re-run alone until a `VERDICT` line appears; never two Cursor runs at once (kill a stale one
     AND its shell before relaunching, or its `EXIT` line lands in the new `.err` file).
   - What the fix rounds changed (all test-first): batched MTP always decodes plainly (`mtp_batched`, counted + logged), lockstep B>1
     refuses, public batched entry points refuse MTP; abnormal exits of cached requests retire the session (all draft kinds); terminal
     chunk held until publication; per-session epochs; zero-budget requests emit nothing (all paths); logprobs/APC kept for batched MTP;
     DFlash/Eagle fallback discards prefill captures; per-test seeds from `sha256(nodeid)` + fixture-setup seeding. **B==1 cached MTP
     (the bench / opencode path) is cleared as equal to plain decoding.** Documented perf change: a single UNCACHED request on the
     batched path now decodes at plain speed (record in the re-certification).
2. **P369 phase 2 (GPU, ≈ 1 h; covered by C175):** write a short run plan + Cursor plan review first; E1c per-pick real-weight
   conformance (Fable native KV `joint_v1` with straddle counters; uniform TurboQuant `per_query`), E2 greedy ON vs OFF identity, E7
   M3 / M4 firing rates. Then **fork push (operator)** → stack submodule bump → per-pick re-certification ON vs OFF (real GPU chains:
   own plan, Cursor review, operator go) → restore MTP-ON (C177) → P368 layers 2–3.
3. **P383 build (C180, option a):** M64's exact cleanup check before an incident retry no longer blocks on `orphans_unattributed`
   (recorded in the incident; survivors / containers / `unknown` / `uncertain` still block). Test-first in a stack worktree, Cursor code
   review, full suite, merge. Never while the fork suite runs (one suite at a time).
   **tg1 side, still open (needs its own proposal):** an ambient process (Spotlight) can make a tg1 probe cleanup `uncertain`
   (path-only / access denied / unreadable identity of a process that is NOT ours), which refuses the one block restart and aborts the
   chain (C147 rule; the M63 abort in `p297-uncertain-gone`'s fixture). P297's chain-side approach was rejected (U1–U3); its review put
   the fix probe-side (P296) at the next identity boundary — P371 was that boundary and did not take it. Propose it together with the
   P383 build (likely: classify session-foreign, never-observed processes as ambient in the probe's cleanup record instead of
   `uncertain`, recorded as evidence), Cursor-reviewed, as a tg1 epoch change.
4. **P385 investigation (C181) — with Cursor:** MLX 0.32.3 quantized sorted-dispatch MoE prefill nondeterminism incl. NaN (evidence in
   the P385 entry; fork commits `bbffeec1`, `1f0e6b40`). (1) minimal standalone repro at the real MoE models' expert count / group size,
   many fresh processes, bitwise; check whether an isolated MLX upgrade changes it; (2) if it reproduces: one real quantized MoE model
   (`gemma-4-26B-A4B-it-OptiQ-4bit` or `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`), same prompt, greedy, ~10 fresh processes — GPU:
   **ask the operator first**; (3) upstream MLX report, disclosure on affected models' results, workaround decision. Cursor
   `gpt-5.6-sol-high` designs the repro with you, reads the kernel, cold-reviews the conclusion. The B picks are dense — unaffected.
5. **tg2 steps 3–4 on the P371 core:** `run_tg2_probe.py` + `corpus_tg2.py` (config `tg2`, label `opencode-v2-web-tg2`; schedule
   `schedules.tg2_tier` over draw `8eb9d8ef…`), injected positives per language, four-language smoke (GPU go given, C175), sizing
   report; then the M64 spec amendment to the tg2 screen (C175 D3; config `m64-oc-tg2`).
6. **M64 remaining:** fork receipt endpoint (P372 — must pass the A3 protocol fixture `benchmark/bench/tests/fixtures/p371_receipt_protocol.json`),
   D2 SearXNG + MCP service, Pi / dsh adapters, snapshot / adoption tooling, arm-neutral P201 auditor at the item barrier, two-judge
   panel (C166), contract artifacts without OWED checks, smokes, the operator's chain go.

## Done this session (2026-10-17 → 18)

- **P371 (C178) merged `7915bccc`:** ONE item core `benchmark/bench/arm_runner.py`, ONE chain core `benchmark/bench/chain_core.py`;
  tg1 and M64-oc are configurations; contracts `run_config`, `corpus` / `corpus_tg1`, `worker_receipts`, `item_barrier`, `chain_hooks`,
  `web_evidence`, `schedules`, `chain_rows` (the ONLY chain-row reader), `campaign_core` (C179 `--campaign-core`), `contract_artifact`,
  `atomic_publish`. Plan rounds 1–4 + code rounds 1–7 (`docs/reviews/p371/`). Full suite 6536 passed / 0 failed.
  **New tg1 epoch** (no rows): `probe_code_sha256` `5a4a9df8875c1e43c28d0acd4fb92f55258400ceb24c2ba39fe2e6b2de8688a9`,
  `generation_identity_sha256` `1c2e748b8e97b386a7719e37d988eb74e0e01bc94bcd2eb8da76dc6e67bb5ad5`; `m64-oc-tg1` `probe_code_sha256`
  `e7733c413689c7b295fe0a189816f32af10d6b4ed5893a9fe85e642efe04ef22`. Any generation-path core change rotates all of them (P377 / C179:
  freeze the core per campaign). Contract artifact `--arm oc`: `incomplete` (13 pass, 3 OWED: D2 search, infra classification, P201).
- **tg2 step 2 merged `436acd11`:** Cursor rounds 1–4 cleared S1–S16; universe `ff76573b…` (149 valid, unchanged items / leaves; five
  items lost `.approaches`), draw `8eb9d8ef…` (permutations unchanged); fingerprinted freeze cache `$STACK_WORKDIR/m65/tg2-freeze-s16`;
  old artifacts archived with a manifest in `$STACK_WORKDIR/m65/stale-universe-pre-s16`. Full suite from the tg2 worktree 6861 / 0 failed.
- **Test flakes root-caused and fixed (P383):** the process guard's sweep records ambient box processes (Spotlight `mdworker_shared`)
  as unattributed orphans; real-guard tests are hermetic (`benchmark/bench/tests/hermetic_scan.py`, autouse; opt-out marker
  `real_process_scan`); stress regression test with an ambient-process generator. P381: the date-hard-coded P364 test fixed.
- **P369 fork:** code-review rounds 1–7, fix rounds through F26 (see item 1); a nondeterministic fork test exposed P385.
- **Rulings:** C179 (push + `--campaign-core`), C180 (P383 option a), C181 (P385 in a fresh session with Cursor); lead calls
  P372–P384 recorded.

## Known gaps / owed

- G2, G3 (guard races; structural fix = per-item containment at an M64 epoch).
- MTP-ON arm-identity flag table check folds into the first MTP-ON smoke (C175).
- C154: re-check opencode's 60-min inactivity TTL and the datefreeze + toolwindows hooks on every opencode release.
- `docs/README.md` index: add the new specs/reports (P311 v4, P364, P369, P371, m65 tg2, M65 pilot, `docs/reviews/p371/`, P369 rounds).
- P371 receipt fence on abort paths is exercised only against `FakeReceiptSource` (the real HTTP source lands with P372).
- Fork: the quantized length-17 MoE precision cases are a structural smoke only until P385 is root-caused.
- Fork: dynamic fallbacks of non-MTP drafter kinds still lose logprobs (pre-existing).

## Rules learned (2026-10-11 → 18)

- Never edit runner/probe/scoring files in the main checkout while a chain runs; build in worktrees. Never run the full suite under a
  live chain, and **never two full suites concurrently** (load flakes timing tests). Stack suite: from `benchmark/`,
  `../.venv-bench/bin/python -m pytest bench/tests -q -p no:cacheprovider -o faulthandler_timeout=600 -rs > <file>`; read the summary
  line from the file. Run the FULL suite from a branch's worktree before merging.
- **Zero flakes (operator):** a test that passes on rerun is a bug to root-cause, never a rerun-until-green; check every
  nondeterministic count (xfail / skip totals that vary between runs). Seed every randomized test; tests must not see box state.
- **Watch long jobs and subagents yourself:** subagents leave orphaned pytest runs and `sleep` waiter loops behind — check `ps`
  ancestry after each agent report and kill leftovers by PID (orphans may ignore SIGTERM). zsh does not word-split unquoted variables:
  kill a PID list with an array (`P=(1 2 3); kill $P`), and verify each PID gone.
- Monitors: macOS `awk` has no `match(…, arr)` — test a filter on a sample line before arming; monitors expire after 30 min — re-arm.
- Long freezes: move a tracked output the freezer refuses to overwrite aside (archived with a sha256 manifest) BEFORE launching.
- Subagent briefs must forbid literal usernames / emails / home paths even in privacy-check regexes.
- Privacy scans: filter `grep -E '^\+'` then the PII alternation; never a pipeline whose failing stage hides matches.
- Edit-then-commit scripts must stop on failure; check `git show --stat` before trusting a commit; shell-assembled review prompts must
  be checked for empty substitutions before launching.
- Archive a failed chain attempt with a sha256 manifest BEFORE moving anything.
- Decision epochs: cross-epoch results descriptive (C165 E1); one shared core ⇒ core fixes rotate every identity (P377, C179).
- Never select items by which items the picks fail; pre-register draws.
- OrbStack bind mounts under `$TMPDIR` serve stale file sizes after in-place overwrites (P361).
- `--print-identity` needs docker on PATH (grader image id; fails closed).

Next decision id C182; discussion ids continue from P386.
