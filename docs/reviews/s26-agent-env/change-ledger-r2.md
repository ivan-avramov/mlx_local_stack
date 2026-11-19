# S26 agent-env — change verify round 2 of 3 (strict), dispositions

Panel: Sol (`gpt-5.6-sol-high`), GLM (`glm-5.2-high`), cursor-agent `--mode ask`, checkout with candidate 2 + frozen tests v2.

| Finding | Sev | Disposition | Why |
|---|---|---|---|
| Sol P1 frozen-test defects T1–T3 present | minor | in progress | the test-writer amends them (designer judgement: T1 / T2 test bugs; T3 → sealed baseline, erratum 10) |
| Sol P2 v8 `declined_ok` ignores the row hash | major | adopted | confirmed `p426_freeze.py:81-91`: DECLINED in v8 needs a 64-hex `declined_evidence.row_sha256` equal to the entry's `row_sha256`; red test: an altered / removed row hash in a resealed record is refused |
| Sol P3 tg2 campaign-core closure omits `tg2_gradle_home.py` | major | adopted, scope extension | confirmed `run_tg2_chain.py` `CORE_SPECS["probe_data"]`; add the module (tg2 only); red test: a change to it invalidates tg2's campaign core, tg1's unchanged |
| GLM R2-1 `not_declined` undocumented | minor | adopted (spec) | erratum v1.1d documents the field |
| GLM R2-2 "(the operator decides)" on an automatic stop | minor | adopted | message is a flat fail-closed statement |
| GLM R2-3 tg1 `probe_code_sha256` rotates vs unchanged | — | to measure | the designer compares baseline vs candidate on the real tg1 `--print-identity` before Accept |
| GLM R2-4 `host_env_after_last_leg` only on the two normal exits | — | noted | as specified (erratum 8); the leg-level diff is in `leg.json` / `sequence.json` |
| Every round-1 adopted finding | — | resolved (both members) except Sol P17's v8 half (= Sol P2 above) | |
