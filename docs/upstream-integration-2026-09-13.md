# M43 upstream integration — 2026-09-13

Status: source merge and independent code review complete in isolation; paired compatibility smokes pass. Numerical attribution and capacity validation remain pending. Production pointers and environment remain on the prior runtime. Nothing has been pushed.

## Source and environment

MLX-VLM merges `45d6e125` (0.7.0) into baseline `420c01e1`, producing local integration commit `c5a6f97b`. The incoming history contains 171 commits, 127 excluding merges. MLX-Serve already contains upstream `a6f80eb`; local commit `f8f1df4` adds the standing integration-quality rule without changing serving code. Both forks' `AGENTS.md` now require disposition of local customizations, preference for upstream extension points, regression evidence before retirement, and maintainability over execution speed.

The experimental serving environment changes MLX/MLX-Metal 0.32.0 to 0.32.2 and MLX-VLM source to the integration commit. It preserves the original Transformers 5.15.0, mlx-audio 0.4.8, NumPy 2.3.5, FastAPI 0.136.3 and Pydantic 2.13.3 pins. Historical M40/M41 rows remain evidence on the original runtime.

## Maintenance disposition

- Retired the dedicated speculative server loop, duplicate server sampler, manual APC materialization, and model-local Qwen verifier in favor of upstream implementations. Cached-session MTP still owns session rewind and remains distinct from batching.
- Consolidated TurboQuant attention helpers and storage ownership; adapted EpiCache snapshots to upstream checkpoint interfaces. Regression tests cover allocation floors through restore, merge, extraction and metadata updates.
- Retained the certified hybrid MTP verifier and repaired sidecar normalization. Their hidden-state and rollback contracts differ from upstream DFlash; replacing them without matched evidence would change the shipped behavior.
- Preserved full-cap preallocation, bounded prefill, native tool routing and deployed sampling. APC remains OFF and retained sessions remain limited to two.

This is not a claim that every diff count shrank. Excluding tests, the runtime patch changes from 43 files / 10,553 added / 698 deleted lines against the previous upstream base to 45 files / 10,765 added / 1,082 deleted against the new base. Those different bases make counts descriptive, not an isolated refactor effect. Duplicate execution paths were removed; cache compatibility and regression coverage also grew. The fork's `docs/upstream-sync-2026-09-13.md` records the detailed disposition.

## Validation

- Full MLX-VLM suite in both isolated environments: **5357 passed, 10 skipped, 149 passing subtests**. MLX-Serve: **75 passed**.
- Eight source audits pass. Dropped-hunk and untested-fork leads were reviewed; these reports are search leads, not coverage guarantees.
- Independent code/cache reviews completed. Destination allocation-floor loss found during review was reproduced and repaired before the final full suites.
- Five fixed compatibility cases per model/runtime cover arithmetic, executable Python, exact JSON, native tool continuation and one existing vision fixture. All cases pass with final convergence and positive MTP counters on both approved models. The tool case uses two requests, so each arm contains six requests. The runner has 73 fake-only tests and an independent protocol review.
- An explicit third conversation turn on `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` reused **1839 tokens** with a correct answer and active MTP. Earlier zero-cache probes were explained by conservative anchoring before the latest user message and by a changed tool prompt prefix; old/new anchoring and persistence logic were independently verified unchanged.

Both models change reasoning text on the JSON case while preserving the exact correct final answer. The other five request reasoning texts match. Restarting the original runtime reproduces all six original responses for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`. An old-source/new-MLX control is pending to separate dependency effects from source changes. These fixed cases do not establish statistical quality equivalence or justify a ladder change. [Paired smoke evidence](../benchmark/results/upstream_2026-09-13_smokes.json)

Next: resolve numerical attribution; run the approved, separately tagged capacity measurements; propose any affected quality remeasurement before activation. M44, the full published Hugging Face artifact/card audit, is queued separately in PLAN.

Raw evidence and private runners: `$STACK_WORKDIR/upstream/2026-09-13/`. [Approved specification](specs/upstream-2026-09-13.md)
