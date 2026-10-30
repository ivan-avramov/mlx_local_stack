# Delivery 1i (same session): fix your three remaining fixture defects; then the set is frozen again

Rulings (spec §16.7 tail, the copy's spec updated): `log_bounds.json` paths are portable (your fixture is right); the receipt's probe environment is the chain's probe launch environment with per-invocation keys by name only; a missing seam in P426 mode is systemic; identities use `ChainOps.create_time(pid)`; the worker argv is exact.

Fix the three class-(c) defects you listed: `arm_receipt_doc`'s snapshot shape (`{hf_path, revision, files}` as `pins.json`), re-sealing every mutated receipt in s5 (remove the false passes; each test must fail or pass for the difference under test), `mlx.metallib` in the world's `loaded_images`. Align any test with the rulings above (e.g. a world without a needed seam must make the leg systemic, not skip). Run on the baseline (support checks must pass). List every test touched. Do not run the candidates.
