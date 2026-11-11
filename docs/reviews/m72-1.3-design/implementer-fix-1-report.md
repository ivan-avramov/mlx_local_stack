I applied all seven findings, but two things aren't clean. Two more stack tests fail because of the version 9 fingerprint bump; they're outside the scope you gave me, so I left them alone. And `ruff format --check` still flags my mlx-serve test file. Nothing is committed.

## Findings

| # | Done | How |
|---|---|---|
| 1 | Yes | `mlx_vlm/tq4_attention.py`: new `legacy_decode_enabled()` reads `TQ_DECODE_2PASS_LEGACY` exactly the way the `turboquant.py` cache constructor does (`"0"` default, lowercased, in `1`/`true`/`yes`). Other values, including `0`, `false`, `no`, empty and `off`, are accepted. |
| 2 | Yes | `mlx_vlm/tq4_fast.py`: new `_require_cache_class()` asserts `type(cache) is TurboQuantKVCache` and names the class it got. It is the first statement of `dequant_rotated`, `prefill_attention`, `decode_attention`, `verify_attention`, `mma_attention` and `mq_decode_attention`, and it also runs in `_check_cache`. |
| 3 | Yes | No served cache passes `kv_quant_mode`. The constructor reads `TQ_KV_QUANT_MODE`, which `--kv-quant-mode` writes (`cli.py:839`). The old worker check differed from the cache only for an empty value. |
| | | Worker: `tq4_attention.py` gains `effective_kv_quant_mode()` (reads the value off a probe `TurboQuantKVCache(bits=4)`) and `key_codec_is_mse()` (asks `turboquant._build_codec` which codec it builds). `require_environment` with `kv_quant_mode=None` checks the effective value. `server/generation.py` no longer passes its own env read. |
| | | mlx-serve: `config.py` refuses a `tq4_attention` mode with a `kv_quant_mode` other than `""` / `mse`. |
| 4 | Yes | `mlx-serve/src/mlx_serve/config.py`: new `_registry_tq4_attention(entry)`. The value is "absent" only when the key is missing. Any explicit value that isn't the string `m72_v1` or `m72_exact` is refused, including `false`, `0`, `null`, `""`, a list, `{}`, `True` and `1`. |
| 5 | Yes | `benchmark/bench/provenance.py`: the creation field is renamed to `manifest["tq4_route_counts_at_creation"]`. The exit check (`assert_served_config_unchanged`) adds `tq4_route_counts_at_exit` to the block drivers store as `manifest["router_exit"]`, after the router PID and config hash pass. |
| | | It does this only when this process gathered a manifest under a mode for that router port. An exit read failure is recorded as the source, never raised. Mode-off exit blocks are unchanged. `docs/serving-path.md` and the fingerprint comment are updated. |
| 6 | Yes | `test_mtp_verify_scan_provenance.py`: `_is_8` renamed to `_is_9` (now pins 9), and the controls table now includes `tq4_attention: (9, "off")`. `test_provenance_fingerprint.py` and `test_orphaned_manifest.py`: added the `registry_tq4_attention` → `off` mock. |
| 7 | Yes | Removed `pytest.mark.slow` from `test_tq4_impl_kernels.py` (3 uses, plus the alias and the trivial `_d2_rows` helper) and `test_tq4_impl_model.py` (3). The `tq4_fast.py` docstring now lists `mma_attention`, `mq_decode_attention`, `block_tokens` and `_kv_head_shift` as test instruments, not production API. Nothing renamed. |

**Tests I added or changed:**
- `test_tq4_impl_wiring.py`:
  - legacy flag refused when on, accepted when off, and parsed the same as the constructor;
  - the prod codec refused, including `PROD`;
  - the effective codec read from the environment;
  - an end-to-end CLI test: `--kv-quant-mode prod` is refused at load and `mse` is accepted.
- `test_tq4_impl_kernels.py`: all 7 entry points, each against a populated one-row `BatchTurboQuantKVCache` and a subclass.
- `mlx-serve/tests/test_tq4_impl_config.py`: explicit non-mode YAML values refused, and the `kv_quant_mode` rules.
- `test_m72_13_impl_provenance.py`:
  - the renamed fields;
  - the exit snapshot is recorded and stays outside the fingerprint;
  - no exit snapshot without a mode;
  - an exit read failure is recorded, not raised;
  - drift still refuses before any snapshot.

## Test runs

- **Full fork suite:** exit 0. 10,719 passed, 18 skipped, 22 xfailed; no unknown-marker warnings.
- **Full mlx-serve suite:** 321 passed, 1 failed. The failure is the known baseline `test_golden_first_pick_command_is_what_main_builds_for_the_same_registry` (argument mismatch at index 16, nothing to do with tq4).
- **Targeted stack run:** 296 passed, 1 skipped. Files:
  - the four finding-6 test files and the rest of `test_provenance_fingerprint.py` / `test_orphaned_manifest.py`;
  - the frozen `test_m72_13_provenance.py` and `test_m72_13_harness.py`;
  - `test_m72_13_impl_provenance.py` and `test_m72_13_impl_e2e_spike.py`.
- **Full stack suite** (run with `--continue-on-collection-errors`): 394 failed, 23 errors, 11,625 passed, 114 skipped.
  - Almost all failures are in the known layout files: `b2_*`, `t3_frozen_*`, `p475s1/test_fixtures_selfcheck.py`, and the `test_t3_wave1.py` collection error.
  - `test_p426_plan.py::test_k3_round3_…` also fails because it reads the empty `src/mlx-vlm`, so it's layout too.
  - **Two more come from the version 9 bump** (see the first question below):
    - `test_reasoning_persistence.py::test_cli_writes_partial_per_rung_and_resumes`
    - `test_reasoning_deep_design.py::test_cli_shallow_rows_resume_across_a_deep_redesign`

    Both fail with "C1 resume refused: … serving controls … differ".

## Not clean

- **`./fe_test.sh fmt` is not clean.**
  - The fork's black hook can't write the read-only frozen test files (`Permission denied`). It did reformat my three files, and isort and autoflake pass.
  - mlx-serve `ruff check` passes, but `ruff format --check` flags my `tests/test_tq4_impl_config.py` and the frozen `tests/test_tq4_m72_config.py`. Running ruff directly needed approval, so I couldn't see the diff for my file.

## Questions

1. **The two reasoning-resume tests.** I'm inferring the cause from the code; I didn't run a check. Both test files rely on the shared `pin_mtp_scan` fixture in `conftest.py`, which pins only `mtp_verify_scan` from "unknown" to its default. For their unregistered model `M`, `tq4_attention` now resolves to "unknown", and the fingerprint treats that as incompatible with everything. The minimal fix is to have that fixture also pin `tq4_attention` "unknown" → `off`. Should I make that change?
2. **Where the exit snapshot lives.** I put `tq4_route_counts_at_exit` inside the exit block, so every driver that stores `router_exit` picks it up without driver edits. That works only when the manifest was created by `gather` in the same process as the exit check. If you'd rather have a top-level manifest field written by each driver, the driver files would need to be in scope.

No frozen test conflicted with the specification.