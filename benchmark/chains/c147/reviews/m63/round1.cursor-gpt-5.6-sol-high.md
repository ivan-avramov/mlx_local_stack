M1 — blocker — `benchmark/bench/chain_ops.py:254-263`: reused MTP overlays validate only the 16-hex header. A modified body with the original header can serve non-shipped configuration, and reused overlays bypass the required-pick checks. Compare the entire file to `overlay_header(...) + registry_bytes` and always validate both picks’ `draft_kind`/`draft_model`; add tampered-body and reused-invalid-registry tests.

M2 — should-fix — `benchmark/chains/c147/run_tg1_chain.py:737-764`: isolation rejects only exact opposite-arm roots. Nested roots such as `$STACK_WORKDIR/c147/m63` are accepted, and `C147_OVERLAY` can read or create overlays inside the opposite arm. Reject roots and overlay paths contained within the opposite arm’s directories; test nested and symlink-resolved paths.

M3 — should-fix — `benchmark/bench/tests/test_m63_predictor.py:132-154`, `benchmark/chains/c147/fake_probe.py:48-56`: the fake end-to-end test injects `FakeOps` and independently supplies `FAKE_SERVED_REGISTRY`, bypassing production propagation of `predictor`, `out_root`, and `MLX_SERVE_CONFIG` into M50/C35 provenance. Add a production-wiring test asserting the constructed `ChainOps` and child environment use the selected overlay.

The authorized suites passed: 250 tests. The new tests do bite on the parent commit, but miss M1–M3.

cleared after fixes (M1, M2, M3)
