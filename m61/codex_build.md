**P201 — Provenance clarification required.** P195 says all new provenance fields enter `scaffold_policy_sha256`; P193/P197 require the M59 hash unchanged. Also, literal manifest-identity equality cannot survive edits because `probe_code_sha256` hashes the implementation.

May I apply this interpretation?

- Preserve the exact M59 carrier bytes and policy-hash recipe for `opencode-v2` without a system file.
- Record and resume-check the new fields for every scaffold; include them in the policy hash for web/system variants.
- Pin M59 carrier/policy hashes, while allowing `probe_code_sha256` to change normally.

Stopped per your ambiguity rule. No files changed or commits created; existing untracked `ts.md` untouched. Captures, detector measurements, suites, and `configgen check` have not run.