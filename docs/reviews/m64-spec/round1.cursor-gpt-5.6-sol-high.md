## Findings

P1 — blocker — The `ArmAdapter` event contract cannot drive the unchanged gate.  
Evidence: `docs/specs/m64-scaffold-arms.md:63-71` normalizes requests/tools/compaction/errors/terminal, but `benchmark/bench/token_turn_gate.py:146-203` requires capture and grade events to determine progress. Existing orchestration supplies them through `GradeWorker` at `benchmark/bench/tg1_runner.py:149-232,490-493`.  
Fix: include normalized capture/grade boundaries, or keep grading runner-owned. Add parity tests proving identical `TokenTurnGate` decisions from an opencode replay.

P2 — blocker — The promised cross-arm P201 audit/rerun path is currently opencode-only.  
Evidence: the spec requires per-arm evidence roots and cheat reruns (`docs/specs/m64-scaffold-arms.md:49,63-73`), but `benchmark/web_audit.py:134-141` accepts evidence only under `opencode_transcripts`, and `benchmark/bench/answer_key.py:397-451` marks only `opencode-v2-web*` rows rerun-eligible. C165 also requires deny-pattern equivalents where supported (`docs/open-questions.md:18`), omitted from the proof matrix.  
Fix: make evidence confinement arm-neutral; register eligible scaffold identities; preserve item/seed/session across at most two reruns; add deny-pattern support/disclosure per arm and Pi/dsh cheat-rerun tests.

P3 — blocker — Dropping dsh is contrary to the ruled design.  
Evidence: `docs/specs/m64-scaffold-arms.md:92-96` permits dropping dsh if live usage is unavailable; C161 requires dsh as a third arm from the start (`docs/open-questions.md:34`), and E2 orders a new adapter (`docs/reviews/m64-plan-2026-10-16/plan_final.md:70-73`).  
Fix: inability to account must REJECT/HOLD the build and return for operator decision, not silently produce a two-arm M64.

P4 — blocker — The dsh treatment boundary is unresolved.  
Evidence: C165 says nothing in the default tool set is removed (`docs/open-questions.md:18`). Existing source notes headless dsh includes web, subagent, subagent-fork and ralph, which were disabled because they permit parallel LLM fan-out (`benchmark/run_dsh_probe.py:84-90,171-179`). It also documents five transport retries (`benchmark/run_dsh_probe.py:365-372`). The draft mentions only web and shell and assumes an unspecified retry-off equivalent (`docs/specs/m64-scaffold-arms.md:22-27,42`).  
Fix: inventory the adopted release before approval. Specify accounting/concurrency for every default tool and REJECT snapshots whose retries cannot be disabled. Any tool removal needs a C165 amendment.

P5 — blocker — Complete receipt reconciliation is not implementable as specified.  
Evidence: §7 merely says receipts are keyed by request ID/session (`docs/specs/m64-scaffold-arms.md:107-112`), while client-cut requests may never expose a response ID; current reconciliation uses client message IDs only (`benchmark/bench/token_turn_gate.py:337-367`, `benchmark/bench/tg1_runner.py:726-733`). The draft also assigns the build to `../mlx-vlm`, whereas E2.4 names the mlx-serve fork (`plan_final.md:53-56`).  
Fix: define a benchmark correlation key—epoch, arm, item attempt, request sequence—propagated or assigned before generation; persist and hash receipts into item evidence; test cuts, auxiliary requests, compaction and duplicate/missing receipts. Resolve the fork ownership explicitly.

P6 — blocker — E1’s adoption gate was reduced to an untestable slogan.  
Evidence: `docs/specs/m64-scaffold-arms.md:60-61` omits E1.6’s required two-model 8–12-anchor bridge, pass→fail/new-nonconv/client-cut red flags, 0.67–1.5 token-ratio bounds, and incomplete-accounting HOLD (`plan_final.md:22-28`). §11 does not require a successful bridge before freezing the epoch.  
Fix: reproduce the complete REJECT/HOLD/ADOPT algorithm and require a hashed bridge artifact before epoch registration.

P7 — blocker — The subjective claim lacks its mandatory coverage floor and cannot use the existing judge path.  
Evidence: E2.6 requires minimum coverage (`plan_final.md:63-65`); §10 only says coverage is reported (`docs/specs/m64-scaffold-arms.md:142-151`). Existing code treats missing orders/judges as ties (`benchmark/bench/judge_pairwise.py:319-325`, `benchmark/bench/judge_gate.py:61-70`) and aggregates a panel majority rather than the ruled two-judge mean (`judge_gate.py:428-436`). Its rubric and default judges are also M38-specific (`judge_pairwise.py:47-55,389-419`).  
Fix: specify an absolute and fractional pair-specific both-strict-pass floor, with estimation-only fallback. Build an M64 rubric/config and aggregation path where missing judges are unscored, order disagreement is a tie, and the confirmatory estimator is the mean of the two judge-specific rates. Add synthetic missingness, order and length-adjustment tests.

P8 — should-fix — “Equal shell deadline” is not enforced by ProcessGuard.  
Evidence: `docs/specs/m64-scaffold-arms.md:45` claims process supervision enforces equality. ProcessGuard is explicitly best-effort (`benchmark/bench/proc_guard.py:1-4`), and G2 documents an escaping detached process (`docs/open-questions.md:22`). The opencode plugin only rejects explicit background or excessive timeout values; it does not supply a missing timeout (`benchmark/opencode_plugins/toolbounds.js:1-11`). Pi’s bash has no default timeout.  
Fix: define a common arm-level shell wrapper or verified native hook with a mandatory 600-second deadline, including detached-child positives. Guard observation alone is insufficient evidence.

P9 — should-fix — The client-timeout control contradicts C154.  
Evidence: §3 claims derived opencode/dsh equivalents (`docs/specs/m64-scaffold-arms.md:44`), but opencode 2.0.20’s 60-minute inactivity TTL is hard-coded and unconfigurable (`docs/open-questions.md:58`; `benchmark/bench/token_turn_gate.py:30-37`).  
Fix: describe arm-specific effective cuts as treatment/unequal opportunity unless the adopted release proves configurability. Keep all-item primary scoring and pre-register a paired sensitivity excluding either arm’s analogous client cut.

P10 — should-fix — Request controls are proven only on the first request.  
Evidence: E2 requires per-request wire evidence (`plan_final.md:35-40`); the draft uses first-request capture plus usage-only receipts (`docs/specs/m64-scaffold-arms.md:35-39,100-102,107-112`). Compaction, auxiliary and subagent requests could silently use different sampling, roles or budgets.  
Fix: capture or receipt the effective request parameters for every request and reconcile them before accepting a row.

P11 — blocker — Transport retries are not statistically or operationally defined.  
Evidence: `docs/specs/m64-scaffold-arms.md:43` says restart and rerun the item, but §7 requires all failures and retries to count toward task tokens. Existing C147 restarts an entire block once (`benchmark/chains/c147/run_tg1_chain.py:282-297`), not an item.  
Fix: define attempt identity, schedule position, worker/session replacement, cause taxonomy, cumulative tokens across failed plus replacement attempts, and the synthetic second-failure row. Test first-failure recovery and second-failure `transport_dnf`.

P12 — should-fix — Counterbalancing can remain confounded within primary cells.  
Evidence: §8 allocates permutations per pick×session (`docs/specs/m64-scaffold-arms.md:114-121`), while claims are language×session cells (`:124-137`). It also omits the required distinct s1/s2 paired schedules and exact same-seed fresh-load reload control.  
Fix: balance permutations separately within pick×session×language; hash distinct s1/s2 schedules; specify reload’s same items/seeds and fresh worker; define warm-up-before-reset order and retry-slot handling.

P13 — should-fix — The confirmatory tests are underspecified.  
Evidence: §9 calls accuracy “TOST” but defines only `max cell p`; a four-cell TOST has eight one-sided components. Token “superiority” is defined by a two-sided CI yet must yield Holm-compatible p-values (`docs/specs/m64-scaffold-arms.md:124-137`).  
Fix: define accuracy claim p as the maximum of both TOST-bound p-values across all four cells; define token sign, estimator, one-sided hypothesis/p-value and bootstrap hierarchy; state explicitly that incomplete receipts make joint PASS impossible.

P14 — should-fix — P311 reporting semantics were dropped.  
Evidence: §4 freezes scoring hashes (`docs/specs/m64-scaffold-arms.md:56-59`), but C164 requires scoring identity to be re-derived at report time and in-probe `answer_key` use moved or recorded (`docs/open-questions.md:26`).  
Fix: add report-time scoring-hash verification, generation-only pairing, and an acceptance test proving scoring-only changes do not invalidate generation pairing.

P15 — should-fix — Work order and provenance contradict E2.  
Evidence: agreed order is adapter/parity/adapters/positives before snapshot tooling (`plan_final.md:70-73`); §11 snapshots first (`docs/specs/m64-scaffold-arms.md:153-161`). §12 defers URLs/package metadata despite E2 requiring them in the specification (`:168-172`).  
Fix: restore the agreed order or obtain an amendment; include dated registry/source URLs and lockfile rules now, leaving only generated snapshot SHAs to fill later.

P16 — should-fix, cheaper design — Power analysis is scheduled too late.  
Evidence: §11 spends several build stages and smokes before simulation (`docs/specs/m64-scaffold-arms.md:153-164`). Each primary cell has only 21–22 items, so ±5pp equivalence under plausible unseen discordance is likely to become an estimation screen.  
Fix: run the pre-registered simulation from P223/M63/c144-base inputs before adapters, receipt plumbing and judge calls. If power is below 80%, freeze M64 as an estimation screen immediately. Receipts, epoching and the subjective axis are ruled requirements—not removable scope creep—but their confirmatory machinery can then be simplified and labelled honestly.

DISAGREE: P1–P7 and P11 must be resolved before build approval; the current draft drops ruled requirements and cannot support its stated claims.
