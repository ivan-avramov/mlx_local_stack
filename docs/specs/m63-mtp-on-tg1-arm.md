# M63 — MTP-ON tg1 agentic arm (C155; PLAN M63)

Operator go 2026-10-12. Certifies the shipped predictor state on the agentic axis (C71). Runs after the
predictor-OFF P223 chain; pairs with it session by session.

## Build (P289)

1. `run_tg1_chain.py --predictor {off,mtp}`, default `off`. `off` behaviour is byte-for-byte the C147 runner.
2. Overlay:
   - `off`: unchanged (`make_overlay`, draft-OFF, `$STACK_WORKDIR/c147/overlay_c147_draft_off.yaml`).
   - `mtp`: the registry VERBATIM (shipped state: `draft_kind`, `draft_model`, `mtp_verify_scan` kept) behind a
     generated header, at `<out-root>/overlay_m63_mtp.yaml`. Refuse unless every scheduled model declares
     `draft_kind: mtp` and a `draft_model`.
   - `C147_OVERLAY` keeps overriding both.
3. Out-root: `mtp` → `$STACK_WORKDIR/m63` (`--smoke` → `m63-smoke`). Refuse `mtp` into `c147`/`c147-smoke`
   and `off` into `m63`/`m63-smoke`. Router TMPDIR and A4 logs live under the out-root for `mtp`
   (`off` keeps `c147/tmp` and `c147/a4_*.log`).
4. Expected predictor everywhere a draft state is checked:
   - `ChainOps.load` worker tripwire: `off` → no `--draft-kind` other than none/off; `mtp` → exactly
     `--draft-kind mtp`, else abort.
   - `verify_manifest` and `validate_leg`: `runtime.draft_kind == predictor`.
5. `chain.json` records `predictor`. RUNLOG `START` line names it.
6. `drive_m63.sh`: detached launcher, `--predictor mtp --out-root $STACK_WORKDIR/m63[-smoke]`, writes
   `chain.out`/`chain.rc` there.
7. `fake_probe.py` reads the overlay's `draft_kind` for the manifest (mirrors the real probe's C35 record).
8. Probe code unchanged (the probe already records and C35-checks the served `draft_kind`): ON and OFF rows carry
   the same `probe_code_sha256` and `scaffold_policy_sha256`; they differ in `runtime.draft_kind` and
   `registry.sha256`. Never pool ON with OFF.

## Run

1. `--smoke --predictor mtp` rehearsal (`drive_m63.sh chain s1 reload --smoke --probe-code-sha <sha>`).
2. `drive_m63.sh chain s1 s2 reload --probe-code-sha <sha>`, same seeds/schedule as the OFF chain.
   Same preflight as C147: 140 W / 28 V, `sudo purge`, `caffeinate -ims -w <pid>`, watch `RUNLOG.md`.

## Pre-registered read

Per session, paired ON−OFF on `acc_strict@budget`; two-stage cluster bootstrap; TOST ±5pp. Report with all rows
AND excluding items where either arm ended `client_inactivity` (C154). Runaway tax in tokens, never wall share.
OFF better beyond ±5pp on the agentic axis → that pick ships OFF (C71); a pick change needs the operator.
