Cold adversarial CODE review of ONE commit. Read-only: modify nothing, no model loads, no servers, no GPU. If your sandbox cannot
run pytest, review by reading and say so once.

Commit `396319a` on `main` of this repo (`git show 396319a`): the retrieval and reasoning benchmark drivers
(benchmark/bench/run_retrieval.py, run_reasoning.py) stage their result and manifest under `.pending-<pid>` names and publish
them back to back via `provenance.publish_pair` (result first, manifest second); the manifest records `result_file` and
`result_sha256`; `provenance.manifest_matches_result` detects a mixed pair. It answers a previous finding: a manifest published
before its result could, on interruption, leave an OLD result beside a NEW manifest.
Context: docs/specs/m57-attention-policy.md (Stack section + Amendments); the commit before it, `89e609a`, introduced the staging
and the `.refused-<utc>` quarantine on a late `ServedConfigError`.

QUESTIONS: (a) Is the original defect really closed — enumerate every interruption point from the start of result writing to the
end of publication and state what is left on disk under canonical names at each, with and without a pre-existing pair. (b) Did the
commit change what a SUCCESSFUL run writes other than the two manifest keys, or what `--resume` in run_reasoning reads? (c) When the
end-of-run `provenance.gather` fails with an ordinary exception the result is published alone and an older manifest may remain —
is that mixed pair detectable by `manifest_matches_result`, and does anything downstream (graders, compare, scorecards — grep for
readers of these manifests/results) silently consume it? (d) Are the tests in benchmark/bench/tests/test_pair_publication.py
exercising the real driver code paths or re-implementing them? (e) Any other defect in the touched lines.

DELIVER (markdown, ids B1, B2, ... most severe first, file:line): what is wrong, concrete scenario, consequence, fix; classify
BLOCKING / RESIDUAL. Verdict: SHIP / SHIP-WITH-RESIDUALS / FIX-THEN-SHIP. Under 500 words. No praise.
