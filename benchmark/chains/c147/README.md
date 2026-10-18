# C147 chain drivers

Spec: `docs/specs/c147-tg1-chain-clearance.md` (rev 3). Library: `benchmark/bench/chain_ops.py`; P371 phase 3a: the chain itself is `benchmark/bench/chain_core.py` (`run_tg1_chain.py` is the thin entry: CLI, out-root rules, the tg1 `ChainConfig`).
Everything detached: `nohup <script> ... &`; rc files hold the exit code. Stack stays stopped afterwards.

| File | Use |
|---|---|
| `drive_inject.sh` -> `run_inject.py` | Injected positives (~30 min). Output `$STACK_WORKDIR/m62/inject/` (`inject.out`, `inject.rc`, `RUNLOG.md`). rc 0 cleared, 1 verifier FAIL, 2 abort, 4 not cleared after three seeds. |
| `drive_chain.sh` -> `run_tg1_chain.py` | `pilot` (5 items, pick 1 python) then `chain [s1 s2 reload] --probe-code-sha <sha>`. Output `$STACK_WORKDIR/c147/` (`chain.out`, `chain.rc`, `RUNLOG.md`, `chain.json`, `<session>/`). rc 0 done, 2 abort, 3 STOP. |
| `fake_probe.py` | Contract implementation for tests only (`FAKE_PROBE_BEHAVIOUR`). |
| `reviews/` | Codex `gpt-6.1-sol` cold reviews: two design rounds, four post-build rounds, with the prompts (scrubbed copies of the workdir originals). `reviews/c151/`: C151 Cursor `gpt-5.6-sol-high` rounds 1–8. `reviews/c152/`: C152/P273 rounds 1–2 (combined, superseded by ruling A) and the P273-only confirmation. |
| `run_codex.sh` | `run_codex.sh <name> ro\|write [model]`; prompt on stdin, output under `$STACK_WORKDIR/c147/`. |

Order: `drive_inject.sh` -> `drive_chain.sh pilot` -> `drive_chain.sh chain ...`.

```
# probe identity for --probe-code-sha (P311-lite: the tg1 probe is run_tg1_probe.py; the value is the static import
# closure of that file plus its plugins/carrier; it also prints generation_identity_sha256 and scoring_code_sha256)
.venv-bench/bin/python benchmark/run_tg1_probe.py --print-identity
nohup benchmark/chains/c147/drive_chain.sh pilot &
nohup benchmark/chains/c147/drive_chain.sh chain s1 s2 reload --probe-code-sha <sha> &
touch "$STACK_WORKDIR/c147/STOP"      # latch: no new legs, current leg cancelled cooperatively, exit 3
```

Runner options: `--pred-s LANG:MODEL=SECONDS` (repeatable), `--arm-idle-s` (default 600), `--out-root`,
`--probe`, `--python`, `--universe` (forwarded to every probe step, P351), `--policy-sha` (expected
`scaffold_policy_sha256`; it embeds the universe sha, so a non-tg1 universe needs the value its
`run_tg1_probe.py --print-identity --universe <file>` prints; the policy also embeds the bench lock sha, the interpreter
and the local grader image id, so each box passes its own value). `--generation-sha` optionally pins the shared composite
up front (otherwise it is pinned from the first manifest); one arm identity per (model, predictor) is frozen at the
arm's first manifest. The chain's lifecycle (P24, R15) is the entry's static import closure (`identity_closure`: `chain_core`,
`chain_ops`, `chain_rows`, `schedules`, `run_config`, `web_evidence`, `campaign_core` ...) + the serialized `ChainConfig` + the
A4 gate + the launchers; it is hashed into `chain.json` (`lifecycle`, `chain_config`) at chain creation and re-verified before
every launch, barrier, validation, resume and at exit: drift aborts with rc 2 (a changed chain needs a new out-root).
`--campaign-core <tag>` (C179 / P377) additionally refuses unless the probe and chain entry closures equal their closures at
that git tag (`chain.json` `artifacts.campaign_core`; enforced at the same points; absent = recorded null). Draft-OFF overlay:
`$C147_OVERLAY` (default `$STACK_WORKDIR/c147/overlay_c147_draft_off.yaml`, generated from `main_models.yaml` on first use).

Rows layout (P371 A8 / P376): every pilot / full invocation writes its own immutable `<session>/<stem>.L<leg>.<phase>.a<n>.jsonl`
(+ `.manifest.json`, `.log`, `.json`, `.CANCEL`, `.ACK`; `a<n>` counts the stem's invocations); the full invocation runs the cell
minus the pilot's items. `chain.json.progress` (the `bench/chain_rows.py` schema) is the inventory: scored slots come only from
`chain_rows.load_slots`. A restarted load is archived under `<session>/incomplete/` with its sha manifest recorded first; a
resumed chain quarantines never-validated files under `quarantine/<ts>/MANIFEST.json` and reruns the interrupted load. Web
evidence per row is extracted chain-side to `<evidence>.web.jsonl` (sha in `progress`). Stored pre-P371 chains are read only
through `chain_rows.legacy` / `legacy_path`.

Cancellation is cooperative only (idle predicate or STOP). The runner never kills a probe without
a prior cancel file and `T_coop` expiry; on a refused restart it lists leftovers and kills nothing.
Tests: `env -u STACK_WORKDIR .venv-bench/bin/python -m pytest -q -p no:cacheprovider
benchmark/bench/tests/test_chain_ops.py benchmark/bench/tests/test_c147_chain_runner.py`.
