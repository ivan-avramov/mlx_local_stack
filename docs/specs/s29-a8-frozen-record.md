# S29 — B8-A8 rule 3.6 accepts the decider legs' frozen record (the amendment)

v1.2, 2026-11-23 (v1.2: a decider attempt must name the amendment — naming the v8 base is a reason (Sol P1); v1.1: R1 binds the amendment to the pilot dossier the sequencer recorded, not to B8-A8's pilot acceptance — D1, frozen test). four-eyes light (the A8 verdict's input path; a consumer fix, no runner change). Lead call S29-P21 under C388.

## Goal (verbatim in every brief)

B8-A8 (`bench.p426_verify`, `verify_a8_kv`) decides which tg2 pairs feed the A8 verdict. Its rule 3.6 requires every attempt's
`chain.json` `frozen_record.sha256` to equal the v8 base's sha256 (spec `m76-b4b2-a8-consumers.md` §3.6, line 59). By the runner's
design (B4b-1 sequencer `record_path`), only the pilot legs run on `v8_base.json`; every decider leg (s1, s2, reload) runs on
`amendment.json` — the sealed post-pilot record that binds the v8 base (`v8_base_sha256`) and the accepted pilot dossier
(`pilot_dossier_sha256`) and adds the leg deadlines. On the real decider records rule 3.6 therefore rejects all three decider
pairs and B8-A8 is `incomplete`. Solving it means: rule 3.6 accepts an attempt that ran on this campaign's frozen identity — the
pilot on the v8 base, a decider leg on the amendment that provably extends this v8 base and this campaign's accepted pilot — and
still rejects anything else, so the A8 verdict reads the real decider.

## Scope

`benchmark/bench/p426_verify.py` (rule 3.6 in the A8 path and what it needs to read the amendment) and its tests. Nothing in the
runner, sequencer, harvest, signals or panel code; `B8.json` and the no-A8 sheet byte-identical.

## Settled constraints

- (designer) The amendment is read from the published run records (`<results>/m76/wave2.tg2/run/amendment.json`), verified as a
  sealed record (`p426_hooks.sealed_ok`), and becomes a hashed B8-A8 input like `v8_base.json`.
- (designer) The pilot session keeps requiring the v8 base itself.
- (AGENTS) Fail closed on anything unverifiable; no hand-edited records.

## Required behaviour (intent; mechanism free)

R1. A decider-session attempt (s1, s2, reload) whose `frozen_record.sha256` is the amendment's sha256 passes rule 3.6 when the
    amendment is sealed and valid, names this v8 base (`v8_base_sha256` == the v8 base's sha256), and names this campaign's pilot
    dossier (`pilot_dossier_sha256` == the byte sha256 of the pilot pair's dossier file the sequencer recorded in `sequence.json`,
    read through B8-A8's reader), whether or not B8-A8 accepts the pilot pair itself; the pilot session's attempts still need the
    v8 base's sha256. A missing pilot record / dossier, or a sha that differs, is a rule-3.6 reason for the decider attempts.
R2. Anything else is a rule-3.6 REASON (the pair is rejected, never a crash): no amendment published while a decider attempt names
    one; an unsealed / tampered amendment; an amendment naming another v8 base or another pilot dossier; a decider attempt naming a
    sha that is neither; a decider attempt naming the v8 base (it would have run without the pilot gate's amendment); a pilot
    attempt naming the amendment.
R3. B8-A8 records the amendment it used (path + sha) among its inputs, so a later change to it is detected the way the v8 base's is.
R4. On the real records (`benchmark/results/m76/`, current `main`): B8-A8 is `complete`, all four pairs accepted; `B8.json`
    byte-identical to the committed one.

## Acceptance

1. R1–R3 as tests on the real record shapes (the real `amendment.json` / `v8_base.json` / chain `frozen_record` blocks; tampered
   copies for R2), including the pilot-names-amendment case.
2. R4 on the real records.
3. The A8 / B8 test modules pass (`test_m76_b4b2_*`); nothing that passed on the baseline fails.

## Non-goals

Any change to how the amendment is written, to the other A8 rules, or to the verdict.
