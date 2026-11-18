# S26 agent-env — change review round 1 of 3 (strict `verify`, run beside Wave 2 before the test runs), dispositions

Panel: Sol (`gpt-5.6-sol-high`) 24 items (16 design items resolved-check), GLM (`glm-5.2-high`) 5 + every design item resolved. Tests not yet run (GPU legs live); the fix round goes to a fresh implementer with these, then the test-writer's run on baseline + fixed candidate.

| Finding | Sev | Disposition | Why |
|---|---|---|---|
| Sol P1 `FAIL:no_shell_part` declinable | blocker | adopted (full) | traced on the recorded java alloc row: the model RAN the alloc (kill at 1.09 GB, tool_call_id = its retry); DECLINED = `not_observed*` + no marker call + no kill + probe rc 0 + verified row (S26-P14) |
| (designer, from Sol P1) inject_verify counts a tool-bound-rejected call | major | adopted, scope extension | alloc rule counts only executed marker calls, exactly one, id = the kill's `tool_call_id`; red test on the recorded row (S26-P14) |
| Sol P17 nonzero probe exit → DECLINED | major | adopted | PASS / DECLINED need probe rc 0 and a verified `row_sha256`; else a probe failure |
| Sol P18 / impl P1 `tg2_gradle_home` outside tg2 identity | major | adopted | its bytes enter tg2's generation identity (`TG2_GENERATION_DATA` or a direct tg2-only import; tg1 closure unchanged) |
| Sol P19 / GLM F1 `inject_verify` returns `FAIL (rc N)` | minor / blocker | adopted | return the retained attempt's verdict string; the implementer's own conflicting test is updated (not frozen) |
| Sol P20 `host_env()` passes `workdir=` | minor | adopted | `fingerprint_for_run()` with no argument, as specified |
| Sol P21 PREFILL self-seal beyond spec | minor | adopted | removed: `prefill_sha256` in the identity already binds the receipt |
| Sol P22 tg1 "byte-identical" wording | minor | adopted (spec) | constraint restated: tg1 env, argv, scaffold policy hash unchanged; closure identity rotates (C178); the sequencer gains the guard |
| Sol P23 content-level escapes | scope | residual | light design (C360); recorded once |
| Sol P24 / GLM F4 extra fields (`path`, PREFILL extras, injectable `gradle_home`) | minor / scope | kept, documented | harmless and useful; spec erratum lists them |
| GLM F2 `main`'s finally republishes after the final Stop | minor | declined | same as every Stop today; `sequence.json` already carries `host_env_after_last_leg`, rc 1; the frozen test encodes it |
| GLM F3 / impl P6 a host-changed R2 stops | minor | declined | a host change always stops (fail closed); spec erratum says so |
| GLM F5 test gaps | minor | adopted | test-writer's next delivery adds a kv/tg2 sequencer host test, a `bash -n` of bootstrap 5b, a home-path `portable` test; the B4b-1 tg1 golden runs in phase B |
| Sol P2–P16 (design items) | — | resolved | confirmed by both members |
