Commit `ddcd5b7d` — `fix(bench): P340 — an OFF tg1 chain with its own --out-root keeps A4 logs and router TMPDIR under it (no longer P223's c147/); default OFF and MTP arms unchanged`

P1 — Medium — `benchmark/chains/c147/run_tg1_chain.py:757,778-782`

Relative `--out-root` remains relative. `ChainOps.env_base()` creates it relative to the launch directory, but router/A4 subprocesses run with `cwd=REPO`, so their relative `TMPDIR` points elsewhere and may not exist. This violates P340 and can break MLX JIT.

Fix: normalize `root` to an absolute path in `resolve_out_root()` before returning it.

P2 — Low — `benchmark/bench/tests/test_c147_chain_runner.py:1083-1100`

The tests call `make_ops()` with absolute paths, so they miss P1 and do not cover symlink aliases or default smoke resolution to `c147-smoke`.

Fix: add tests composing `parse_args()` → `resolve_out_root()` → `make_ops()` for:
- relative custom root from a cwd outside the repo;
- custom/default symlink aliases;
- default OFF `--smoke` yielding `c147-smoke`.

P3 — Nit — `benchmark/bench/chain_ops.py:231`

The comment still says all OFF arms keep C147 paths, contradicting P340. Update it to distinguish default OFF from custom OFF roots.

No other `ChainOps` behavior is directly keyed on `out_root`: it selects `a4_log_dir`, derived `tmpdir`, subprocess `TMPDIR`, and leftover scanning. Default OFF, MTP, and smoke behavior are otherwise correct. Tests were inspected statically, not executed.

cleared after fixes P1, P2, P3
