# P8 — pre-push exceptions for reviewed upstream findings

Preserve normal pre-push verification while admitting the exact reviewed findings from the 335 public upstream commits through `fd6404fb3261102600541127d59103dac65c2756` in the current MLX-VLM sync. The published fork baseline is `babb0c9d2f149435ee84faf5617a6ebe651c5d23`. The preflight reproduced 119 diff naming and 13 message naming findings, and 19 PII-pattern findings, across 37 commits. The PII matches are the seven documented example paths and twelve Python attribute expressions in upstream `3d58bac9`. No token-shaped findings are approved.

## Supported behavior and interface

- Put the approved commit fingerprints in the gate module beside existing policy. Use a mapping keyed by full 40-character upstream commit SHA, with one SHA-256 of the exact ordered list of existing formatted finding strings. Hash UTF-8 encoded `json.dumps(findings, ensure_ascii=True, separators=(",", ":"))`. Include no literal finding content in the committed table. The initial mapping must have 37 entries; recount from the two pinned commits with the published scanner and verify the category totals above before generation.
- `check_lines(..., remote_url=None)` receives the push URL from the pre-push hook's existing command-line argument. Enable the mapping only for repo identity `mlx-vlm`, remote name `origin`, a canonical MLX-VLM origin SSH or HTTPS push URL, and remote ref `refs/heads/main`. An omitted URL, another remote, or a different destination applies the original checks.
- Compute the original findings for each introduced commit. If the full SHA and fingerprint both match the active table, clear that exact set for that commit. Any fingerprint difference means original reporting for the entire current set. No ancestry-based exemptions, token classes, path globs, new config, environment override, or user input to the table.
- Preserve all other gate checks and error behavior including full exact-tip receipts, fork pairing, model naming, PII, and every nonmatching introduced commit. Scope is taking a narrow exception from the current scanner's output. Changing the scanner's diff representation and adding broad future-sync policy are separate work.

## Acceptance

- Behavior tests verify a matching sha and exact finding list on the intended ref passes the scan, even with local copy names that differ, and still requires a current exact-tip PASS receipt.
- Tests prove refusal with no canonical URL, another remote, another repo or ref, a different full commit with the same finding text, a missing approved finding with another remaining, an extra or changed finding, and a second introduced commit with its own violation. Existing gate tests remain green.
- The built-in table matches exactly the pinned published scanner findings. Run the candidate scanner against the real pinned history in a scratch clone, once with and once without the exception. Verify original scanners still detect fork-authored findings in a synthetic descendant (no actual push). The next push gate receipt uses the new policy digest.
- Report design and candidate review findings. Operator acceptance and explicit in-turn publication are still required.

## Design review disposition

Round 1 of 3, Codex GPT-6.2 Astra.

- Adopted destination validation. The existing repository identity helper recognizes a GitHub-shaped suffix. Adopt exact full URL matching for the exception, and verify CLI forwarding plus refusal for a similarly named mirror. Leave legacy identity behavior for the ordinary checks.
- Adopted independent finding inventory. The commit with all PII flags was checked separately. Exactly seven match paths in the marked example documentation, 11 match Python attribute expressions in production, and one matches a test attribute expression. Zero token findings. The published scan reproduced all original counts and generated `approved-findings.json`, the read-only implementation input.
