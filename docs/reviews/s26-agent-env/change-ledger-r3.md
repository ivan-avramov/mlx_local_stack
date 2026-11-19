# S26 agent-env — change verify round 3 of 3 (strict, final), dispositions

Panel: Sol (`gpt-5.6-sol-high`) and GLM (`glm-5.2-high`) on candidate 3 (fix round 2) + frozen tests v3 + the test-writer's run.

| Finding | Disposition |
|---|---|
| Sol P2 (v8 DECLINED row hash) | resolved (both members) |
| Sol P3 (tg2 campaign-core closure) | resolved (both members) |
| GLM R2-1 (`not_declined` documented) | resolved |
| GLM R2-2 (flat Stop wording) | resolved |
| GLM R2-3 (tg1 `probe_code_sha256`) | measured by the designer: rotates e9c487c1… → 8a456ade…, `scaffold_policy_sha256` unchanged f56705f9… (C178) |
| New findings | none — both members: NOTHING OF SUBSTANCE |

Test-writer on candidate 3: full suite 15227 passed, 9 skipped, 1 xfailed, 0 failed; frozen tests 202 / 202; verdict merge.
Residuals (recorded once): content inside existing home toolchain dirs is not hashed (C360 light design); the kv first-run baseline write
and post-leg INVALID path have mocked tests only (no frozen kv chain fakes); the cache-manifest size check (P11) is verified on the
first real prefill.
