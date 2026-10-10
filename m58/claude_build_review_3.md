# M58 build review round 3 (Claude, cold) — 2026-10-05

Heads moved DURING this review (implementer committing round-3 fixes concurrently). Reviewed:
fork `m58-joint-verify` c0ab3270 → re-checked at **7267d0e5**; router `m58-joint-verify` 9b5d308 → re-checked at
**3b8f96f**; stack `m58-provenance` 68db1c4 → re-checked at **649fb51** (E-findings re-verified against the newer heads;
statuses below are at the newer heads). Read-only; CPU only; no servers, no :8000, no loads. Prior review files not read.

## Verdicts
- Fork (mlx-vlm): **SHIP**. No blocking or major findings. Only minor test gaps and one spec-level note (E1).
- Router (mlx-serve): **SHIP**.
- Stack (worktree m58): **FIX-THEN-SHIP**. E6 (exit-code conflation) is a ~5-line fix. The rest are NITs or pre-existing.

## Evidence run
- Fork: M58 files 156 passed / 0 skipped at 7267d0e5. Full suite at c0ab3270: 5464 passed, 6 skipped (none M58).
  Mutation testing on a copy (`$STACK_WORKDIR/m58/tmp/claude_r3_fork/`): 33 mutants, 28 killed, 5 survived.
  Two survivors are equivalent mutants; three are real gaps (E2).
- Default-path response bytes: branch `schemas.py` serializers vs `git show main:` copy. GenerationTimings and
  StreamingTimings, 3 metric states: byte-identical (VERIFIED).
- Router: 186 passed. Real `main` vs branch `_build_command` (both trees extracted with `git archive`) over all 11 entries
  of the live `main_models.yaml`: identical (VERIFIED, real code, not the test's re-implementation).
- Stack: changed/new tests 584 passed / 2 skipped at 68db1c4 (full `bench/tests` 2968 passed / 3 skipped). At 649fb51:
  M58 files 239 passed. 31 mutants, 26 killed.
- Nothing pushed: no remote branch contains any of the three heads. No PII or absolute paths in the diffs.

## Closure table (rounds 1–2)
| Item | Status | Evidence |
|---|---|---|
| Loaded-MTP-drafter guard after resolution | CLOSED | generation.py:1544-1547; TestB6 (M10 killed) |
| Self-test rejects shape/dtype/non-finite; straddle known positive needs finite bit diff | CLOSED | mtp_verify_scan.py:542-557,574-581; TestB7, test_d5_the_straddle_known_positive_is_required (M6 killed) |
| AB counters only in end_block; discard_pending on exception re-raises original | CLOSED | mtp_verify_scan.py:344-378; speculative_verifier.py:406-422; TestB8 (M4, M15, M30 killed) |
| Device discovery fails closed; cached arch suffix == live | CLOSED | mtp_verify_scan.py:88-108,247-254; TestB9 (M3 killed) |
| Threshold tests on REAL `_qwen3_5_sdpa_vector_plan`, device_info only mocked; 44 cells, leading qL−d, length-2 at 1024/1025, blocks 64@1024 / 128@1025 | CLOSED | test_mtp_verify_scan.py STEP1_MISMATCH (44 entries counted), TestB10 (M1 killed) |
| AC8 unmodified drafter + drafter final state; genuine acceptance | CLOSED | test_mtp_verify_scan_generation.py TestAC8, TestD5GenuineAcceptance (new at 7267d0e5) |
| Quantized-KV refusal on kv_bits only; first pick loads (golden, real registry) | CLOSED | mtp_verify_scan.py:464; golden ran (not skipped); matches `kv_quant.from_legacy` (kv_bits None → native) |
| `_step` batching path reports no counters (documented) | CLOSED | generation.py:1810-1811; spec Build status |
| Default path never imports the new module | CLOSED | generation.py:213-217; TestD6 import hook |
| Self-test watchdog os._exit(75) covers probe + cells | CLOSED | mtp_verify_scan.py:208-225,600; TestD7 incl. real subprocess (M23, M34 killed) |
| Golden resolution (env / sibling / now pinned fixture); CI enforcement | CLOSED, see E3 | 7267d0e5 / 3b8f96f: fixture sha-pinned, equals the live registry byte-for-byte (VERIFIED) |
| Domain K/V dtype + head dim; local RNG key; device resolved once | CLOSED | mtp_verify_scan.py:291-303,535; TestRound2Gaps (M18, M28 killed) |
| Router: kv_quant_scheme rule reverted (both policies); golden byte-identical to main | CLOSED | config.py:138-155,156-185; real-code comparison above |
| Stack items (parity_replay compare/resume/auth/C106/_abort; closed-set scan on every path; pin_mtp_scan opt-in; AB non-pooling and re-resolve; null cmdline; compare_predictor AB) | CLOSED, except the PARTIALs below | Sub-agent audit of each path:line + named test; 26/31 mutants killed |
| Stack: serving `code` recorded/compared | CLOSED at 649fb51 (was OPEN at 68db1c4) | resume refuses when a row's code differs (parity_replay.py:149); entry refuses a None code (:241-245); rows require non-null code (:391) |
| Stack: whole post-entry loop finalised via `_abort` | PARTIAL | E10 |
| Stack: re-resolve `expect=entry` in capacity/retrieval/reasoning | PARTIAL (code present, untested) | E8b |

## New findings

### Fork
**E1 MINOR — the length-2 C120 fold-in makes `joint_v1` deliberately differ from `per_query` policy, and G1b does not account for it.** (VERIFIED code path; frequency is an ASSUMPTION)
- Code: speculative_verifier.py:127-143 vs mtp_verify_scan.py:337-338.
- Under `per_query`, a length-2 block whose key range straddles a threshold takes the shipped joint call. Under `joint_v1` the same block is served per-query. That is the intended C120 correction, but it is not bit-identical to the `per_query` policy.
- G1b requires "20/20 identical across policies". No counter separates length-2 straddles from length ≥ 3 ones, so a G1b divergence cannot be attributed.
- Likelihood is low on the first pick: the drafter has `block_size: 3`, and length 2 arises only when the remaining budget is 2 (mtp.py:525).
- Fix: add a `verify_blocks_straddle_len2` counter, OR add a spec note: a G1b difference on a row with a length-2 straddle is C120, not M58.

**E2 MINOR — test gaps (surviving mutants).** (VERIFIED)
- (a) M21: the self-test eligible cell can be moved from the largest eligible length to length 2 undetected (mtp_verify_scan.py:559). The spec requires the largest. Fix: assert the tested length is `V // gqa`.
- (b) M32: the non-finite term in `_differs` can be removed undetected (mtp_verify_scan.py:180). Bit-identical NaN in BOTH outputs is untested. Fix: one AB test with the same NaN on both paths.
- (c) M33: `since()` can ignore the reasons snapshot undetected (mtp_verify_scan.py:416-420). Per-request histogram reset with pre-snapshot reasons is untested. A bug here would make G1a's empty-histogram check fail falsely across requests. Fix: put a reason before the snapshot in test_ac9_request_scoping.

**E3 NIT — `MLX_REQUIRE_STACK_REGISTRY` is now dead, and CI guards a snapshot, not the shipped registry.**
- Files: fork tests.yml, conftest.py:84, test_mtp_verify_scan.py:1515-1531; router ci.yml, conftest.py:59.
- At 7267d0e5 / 3b8f96f the resolver falls back to the pinned fixture and never reads the env var. The CI env line and the marker text describe behaviour that no longer exists.
- Drift between the fixture and the live registry only warns.
- Fix: delete the env var and marker text, or make drift fail when the sibling checkout is present.

**E4 NIT — AB counters diverge after an aborted round.** mtp_verify_scan.py:331 vs 364.
- `verify_blocks_joint_v1` advances at classify time; `verify_ab_blocks` advances only in `end_block`. After `discard_pending`, `verify_ab_blocks < verify_blocks_joint_v1`.
- Harmless, because G1a aborts on any exception. Document it, or count joint blocks in `end_block` under AB.

**E5 NIT — the mismatch log's `layer=` is a shadow ordinal, not the model layer index** (mtp_verify_scan.py:346,395). Rename it to `block=`.

### Router
None beyond E3.

### Stack (statuses at 649fb51)
**E6 MINOR, OPEN — compare crashes on a non-numeric joint counter, and the crash exits 1, the same code as "differing".** (VERIFIED by sub-agent experiment; line still present at 649fb51)
- parity_replay.py:490: `(r.get("verify") or {}).get("verify_blocks_joint_v1", 0) > 0` raises TypeError on `null` or a string.
- Fix: in `_audit`, require `verify_*` block counters to be non-negative ints (report as integrity). Wrap compare so any exception exits 2.

**E7 MINOR, pre-existing, OPEN — `run` without `--resume` silently overwrites an existing journal.** parity_replay.py:259 (`if out.exists() and a.resume`).
- This can overwrite a complete G1b side or erase a `served_config_drift` stamp.
- Fix: refuse when the output exists and `--resume` is not given (as run_reasoning does).

**E8 MINOR — stack test gaps (surviving mutants).** (VERIFIED)
- (a) Removing the AB refusal in `_side_state` goes unnoticed: `joint_v1+ab` vs `joint_v1+ab` then exits 0. Fix: add an AB-vs-AB compare test.
- (b) Dropping `expect=serving_entry` at run_capacity.py:117, run_retrieval.py:84 or run_reasoning.py:165 leaves the suite green. Fix: one test per ladder.
- (c) The pairs==0 guard is redundant (its mutant is equivalent).

**E9 NIT — the side-level code check is skipped when either side's code is None** (parity_replay.py:495-496).
- Now covered by the mandatory per-row `code` and the entry refusal. Simplify to a strict comparison.

**E10 NIT — after the main loop, the run's tail sits outside the finalising try** (parity_replay.py:352-365, ASSUMPTION on reachability).
- An unexpected non-ServedConfigError from the exit check, or an OSError on the final write, leaves the journal at `running` without C106.
- Fix: extend the try over these lines.

**E11 NIT — aborts after a router crash drift-stamp the journal**, so in practice they cannot be resumed. Fails safe; costs regenerated rows.

**E12 NIT — compare output does not record each side's scan or control/cross-policy role; `legacy` is dead code** (always False).

**E13 NIT — AGENTS.md hygiene.**
- Commit 017d1ee uses the prefix `test(bench)`, which is not in the allowed set.
- The branch is behind `main` (docs only); the worktree spec copy lacks the v3.2 amendments. Rebase before merge.
- The worktree carried uncommitted edits mid-review, since committed as 649fb51; that commit's content was reviewed only for E6, E7 and E9.

## Challenge areas, summary
1. Joint path outside rules 1–7 or the domain: none found. Every gate is in `classify` (mtp_verify_scan.py:257-314). Quantized or batched caches are re-checked at runtime. The plan mirror is monotonic in key length on `s`/`d`, so the endpoint check suffices. Default path: an attribute lookup only. VERIFIED.
2. Straddle predicate: same mirror function, per-layer `n_q`/`n_kv`, lru suffix cross-checked against live device_info once at load. VERIFIED.
3. AB: joint output served; one `mx.eval` per verifier call; pending references dropped on exception; counters consistent except E4. VERIFIED.
4. Self-test: GPU-only, double-guarded (require_gpu plus an internal check); 30 s watchdog plus elapsed check; runs inside `_initialize_model` before `_ready`. VERIFIED.
5. Counters: per-request snapshot/since; absent under the default; serializer bytes identical to main; streaming session-cache path tested. VERIFIED.
6. Golden tests: the real registry (or a sha-pinned verbatim fixture that equals it today). Router expectation hand-written, but independently confirmed against real `main` code. E3.
7. Provenance v8: v7 compatibility via per-control introduction versions; `--clean-stale` safe; `unknown` refused; `joint_v1+ab` observed and never pooled. CLOSED (sub-agent).
8. parity_replay: G1b cannot pass on nothing (non-empty equal expected sets, coverage, complete journals, ceil(0.9n) joint rows); auth on every request; failure finalisation. Gaps: E6, E7, E10.
9. Test quality: high mutation kill rate in all three repos; gaps listed in E2 and E8.
10. AGENTS.md: `# Fork (M58)` markers enforced by AC5; `src/*` untouched; nothing pushed; see E13.
