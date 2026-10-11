# C147 chain drivers

Spec: `docs/specs/c147-tg1-chain-clearance.md` (rev 3). Library: `benchmark/bench/chain_ops.py`.
Everything detached: `nohup <script> ... &`; rc files hold the exit code. Stack stays stopped afterwards.

| File | Use |
|---|---|
| `drive_inject.sh` -> `run_inject.py` | Injected positives (~30 min). Output `$STACK_WORKDIR/m62/inject/` (`inject.out`, `inject.rc`, `RUNLOG.md`). rc 0 cleared, 1 verifier FAIL, 2 abort, 4 not cleared after three seeds. |
| `drive_chain.sh` -> `run_tg1_chain.py` | `pilot` (5 items, pick 1 python) then `chain [s1 s2 reload] --probe-code-sha <sha>`. Output `$STACK_WORKDIR/c147/` (`chain.out`, `chain.rc`, `RUNLOG.md`, `chain.json`, `<session>/`). rc 0 done, 2 abort, 3 STOP. |
| `fake_probe.py` | Contract implementation for tests only (`FAKE_PROBE_BEHAVIOUR`). |
| `reviews/` | Codex `gpt-6.1-sol` cold reviews: two design rounds, four post-build rounds, with the prompts (scrubbed copies of the workdir originals). |
| `run_codex.sh` | `run_codex.sh <name> ro\|write [model]`; prompt on stdin, output under `$STACK_WORKDIR/c147/`. |

Order: `drive_inject.sh` -> `drive_chain.sh pilot` -> `drive_chain.sh chain ...`.

```
# probe identity for --probe-code-sha
.venv-bench/bin/python benchmark/run_opencode_probe_v2.py --print-identity
nohup benchmark/chains/c147/drive_chain.sh pilot &
nohup benchmark/chains/c147/drive_chain.sh chain s1 s2 reload --probe-code-sha <sha> &
touch "$STACK_WORKDIR/c147/STOP"      # latch: no new legs, current leg cancelled cooperatively, exit 3
```

Runner options: `--pred-s LANG:MODEL=SECONDS` (repeatable), `--arm-idle-s` (default 600), `--out-root`,
`--probe`, `--python`. Draft-OFF overlay: `$C147_OVERLAY` (default `$STACK_WORKDIR/c147/overlay_c147_draft_off.yaml`,
generated from `main_models.yaml` on first use).

Cancellation is cooperative only (idle predicate or STOP). The runner never kills a probe without
a prior cancel file and `T_coop` expiry; on a refused restart it lists leftovers and kills nothing.
Tests: `env -u STACK_WORKDIR .venv-bench/bin/python -m pytest -q -p no:cacheprovider
benchmark/bench/tests/test_chain_ops.py benchmark/bench/tests/test_c147_chain_runner.py`.
