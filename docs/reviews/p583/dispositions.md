# P583 — cold review (opinion, round 1 of 1; C264)

Member: `sol`, cursor-agent, `gpt-5.6-sol-high`, context `briefed` (the change diff, the receipt consumer), user instructions unconfirmed; exit 0.

| # | Finding (sol) | Severity / evidence | Disposition |
|---|---|---|---|
| P1 | The metallib is hashed by path after the fact; an atomic replacement mid-leg would hash other bytes than Metal read | major / confirmed | **Declined — no supported trigger**: the venv lives in a frozen clean worktree, its RECORD content is re-verified each leg, and `libmlx.dylib` has always been hashed by path the same way. |
| P2 | `lsof -Fn` parsing ignores fd number, access and type: an inherited / unrelated metallib descriptor would satisfy the presence gate | major / confirmed | **Adopted (adapted)**: `lsof -Ffatn`; only a numbered descriptor, opened for reading (`r` / `u`), of a regular file, ending `/mlx.metallib`; exactly one, in the directory of the mapped `libmlx.dylib` (MLX loads its colocated metallib); else systemic; red-first tests for each rejection and for two candidates. |
| P3 | Point-in-time descriptor sampling: another MLX version may close it after loading | major / hypothesis | **Declined (rest)**: that fails closed (systemic stop), never a false pass; the masking variant needs P2's inherited descriptor, now rejected; loader instrumentation is a fork change outside this fix. |

Driver addition (an existing spec pin, `test_b2_s5_receipt.py::test_loaded_images_come_from_vmmap_not_lsof…`): `vmmap` stays the first source — when it lists a metallib, that one is used and no descriptor is consulted; `lsof` only fills the metallib `vmmap` cannot show.

After the fixes: a real MLX process yields `libmlx.dylib` + `mlx.metallib`; B2 test files 1530 passed, 2 skipped.
