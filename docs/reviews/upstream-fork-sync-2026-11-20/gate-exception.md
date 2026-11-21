# P8 gate verification

Four-eyes strict. Codex GPT-6.2 Sol implemented from the approved specification, GPT-6.1 Sol independently froze the tests before seeing the candidate, and GPT-6.2 Astra reviewed the design and verified the candidate. The roles ran in separate contexts within the same model vendor.

| Review | Disposition |
| --- | --- |
| Round 1 of 3, canonical destination | Adopted. The legacy repository classifier matches by suffix. The exception uses membership in the exact approved SSH and HTTPS URLs. The CLI forwards Git's destination URL and tests cover the similarly named mirror. |
| Round 1 of 3, reviewed finding inventory | Adopted. Independently identified seven example-path matches and twelve Python attribute matches, with zero token findings. Table generation reproduced the original totals for all finding classes. |
| Round 2 of 3, verification | Both findings resolved. No new actionable issues. |

## Checks

- Frozen behavior suite on the published gate: 10 expected failures and 23 passes. On the candidate: 33 passes.
- Existing local gate and push level suites: 177 passes. An initial isolated run had two fixture-launch failures from a missing interpreter link. Creating the link in the disposable test copy cleared both.
- Exact scan of the 335 pinned upstream commits: 151 findings before the exception and zero after. The 37 committed fingerprints match the reviewed input. Synthetic tests preserve findings for a different destination, commit, result list, or later commit and verify exact-tip receipt refusal.
- The gate source change changes the policy digest. Current receipts for both forks and the eventual stack tip are required at publication.
