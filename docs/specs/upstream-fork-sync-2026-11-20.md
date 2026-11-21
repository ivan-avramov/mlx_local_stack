# Upstream fork sync and stack pins

Integrate the two upstream main snapshots fetched on 2026-11-20 into their published forks. Preserve stack serving behavior and frozen benchmark provenance, then publish reachable fork commits before publishing the updated stack pins.

## Baselines and targets

- Stack published main `9abef6a6959e1caf936ec6f01154d940d47759e4`; current pins `34a212080d28953406ae446ab86505a964677a8d` and `3b02e4cbd669b2f4ecb2cb8dabac4ef906e70afc`.
- MLX-VLM fork published main `babb0c9d2f149435ee84faf5617a6ebe651c5d23`; upstream target `fd6404fb3261102600541127d59103dac65c2756`. Merge upstream main in first-parent batches, using upstream releases and shared serving refactors as boundaries. Advance `.upstream-sync-ref` with each merge. Do not rebase published history.
- MLX-Serve fork published main `0555b2fe9637f6b01b2bd5acc834add79841aab7` already contains upstream `754d8d5a07e82ea65efc47a8bd503f1dda2676c8`. Use the published fork tip without creating a merge or adding unrelated changes.

## Compatibility and scope

- Retire a fork customization only when upstream covers the behavior and regression evidence supports equivalence. Otherwise adapt at a narrow extension point or retain the fork behavior. Record the disposition and evidence for every substantial overlap.
- Preserve router-to-worker arguments and request fields, deterministic sampling/thinking controls, structural KV allocation, cache reuse/reset/cancellation, single-sequence cache behavior, TQ4 attention modes with MTP on and off, and fork verifier exactness. Do not implicitly enable APC or adopt a new draft path for existing entries.
- Integrate upstream changes and the minimum compatibility work this merge introduces. Separate newly discovered baseline defects. Keep registry values, model picks, benchmark worktrees and receipts fixed. Keep the existing dependency locks unless a demonstrated compatibility requirement warrants a separate scope decision.
- Protect the operator checkouts during candidate preparation. No push before operator acceptance and in-turn authorization. Publication branch is main; verify both fork pins from the remote and run the full exact-tip stack gate before its push.

## Acceptance

- Fork candidate descends from published fork main and the entire pinned upstream target. The merge review records the staged history, intentional overlap resolutions, and any upstream feature that cannot be offered through the supported stack.
- All fork parity audits pass for their pinned upstream sync reference. Examine the wide dropped-hunk and untested-fork-code reports for new actionable gaps. Preserve regression tests; new failing cases discovered during sync are covered before the fix.
- The MLX-Serve gate and the candidate's MLX-VLM gate pass at the exact proposed pair (pass every requires_mlx_serve case). Verify pinned dependency compatibility and exercise the supported caching, sampling, TQ4, and MTP contracts independently against the pre-merge baseline and candidate. Document skips individually where material.
- The final stack commit contains the intended gitlinks and minimal review records, passes its exact-tip full gate, and resolves both gitlinks from public fork main histories. Verify the published stack main and locally synchronized gitlinks after the push.

## Acceptance additions from design review, round 1 of 3

- P4 (adopted): Pause and release a fake worker preload. Verify the exact MLX-Serve readiness rule waits until the worker can accept inference and handles preload failure as the baseline did. Preserve upstream progress reporting where it can coexist with this contract.
- P5 (adopted): Exercise normal chat with the router's request shape, omitted context management, streaming and nonstreaming, and both anonymous and explicit sessions. Expect default-off chat compaction, intact cache-state delivery to the decoder, existing cancellation, and zero continuation checkpoints for ordinary streams.
- P6 (adapted): Exercise the outer router's supported route surface and verify loopback worker binding. Verify that managed single-box defaults leave cluster and internal management inaccessible and generate no peer or registry activity. Retain explicitly configured standalone distributed operation. The upstream standalone API key's management capabilities need to be documented where the stack runs alongside a locally reachable worker.
- P7 (adopted): Verify that the outer router has no mesh route and its ordinary startup and chat do not create mesh output. Document upstream standalone mesh persistence as outside the managed stack route set.
