The prototype and its measurement code are in place, and the smoke passes. `./fe_test.sh smoke` exits 0: 120/120 sweep rows pass A1 on both arms, all six negative controls fail A1 as they must, and nothing came out NaN or Inf. Three things didn't get done, all listed at the end: the launcher isn't executable yet, its syntax check didn't run, and black/isort couldn't run.

## Files
- `../mlx-vlm/dev/m72_mma_verify.py` (new): the kernel generator (`mma_kernel`), plus `plan_blocks`, `mma_verify_tq4`, `mma_verify_native16`, `fragment_mapping_ok()`, and a record of the K/V input ids and shapes for the A5 check (`last_kv_inputs`).
- `benchmark/spikes/m72_tq4_probe.py` (changed): adds `--mode mma` (accuracy sweep, planted cases, controls N1–N3, per-checkpoint timings and accuracy, JSON keys per the spec's schema). The `full` and `mq` paths are unchanged apart from the extra branch.
- `benchmark/spikes/m72_mma_report.py` (new): writes the Markdown report from `mma-1.json` / `mma-2.json`.
- `benchmark/spikes/m72_run_mma.sh` (new, zsh): runs two passes with a 600 s idle between, exits 11 or 12 for the first failing pass, and never masks the code.

## Commands and results
- **`./fe_test.sh smoke`:** exit 0, run twice; the second run is on the final, reformatted code.
  - Sweep: 120/120 pass A1 (10 sweep T × k 1–5 × 2 arms, plus planted T 8193 / 32770 × k 1–5 × 2 arms). The worst error is 0.49 × the A1 bound for TQ4 and 0.44 × for native16.
  - Checkpoints: 20/20 pass.
  - Controls (relative error): N1 1.22 / 1.18, N2 1.11 / 1.07, N3 1.37 / 1.36 (TQ4 / native16), all `pass False`.
  - The fragment mapping check returned True.
- **k = 3 at T = 32768 (ms):**

  | arm | time |
  |---|---|
  | native16 (joint) | 0.807 |
  | TQ4 production | 1.254 |
  | mq best (G = 1) | 0.878 |
  | mma TQ4 | 0.604 |
  | mma native16 | 0.761 |

  The plan was 128 blocks × 256 tokens.
- **Report:** `./fe_py.sh benchmark/spikes/m72_mma_report.py ../smoke` exits 0 on a copy named `mma-1.json`; the original `mma-smoke.json` is kept. The smoke only has the 8K and 32K checkpoints, so its 131K and 260K projections are extrapolated and mean nothing yet.
- **Scratch checks in `../scratch/`:**
  - Both arms match an fp32 CPU reference at about 2–3.5e-3, tracking the production paths' error.
  - Edge cases are finite and accurate: lengths `[1]`, tile and block edges, and explicit `block_tokens` values of 16, 48 and 64.
  - A5: the kernel's K/V inputs are the full-cap buffers themselves (same ids, shapes = cap).
- No other GPU measurement runs; no pytest runs (no tests of mine).

## Tiling choices
- **Tile size:** 16 tokens. The query tile is held in registers (32 fragments), so threadgroup memory only holds K, V and the norms: about 17 KB for TQ4 and 25 KB for native16, whose V tile is fp32. A 32-token tile with its fp32 P.V would not fit in 32 KB.
- **Block policy:** tokens per block = max(128, ⌈T/128⌉), rounded up to a whole tile, so there are at most 128 blocks per KV head. This keeps the combine step's partial traffic small at short T and gives 512 threadgroups at long T. I didn't tune it.
- **Fragment types:**
  - TQ4 uses half throughout. Codebook values and the bf16 rotated queries are exact in half.
  - native16 uses bfloat for Q.K (an exact copy of bf16 K, with the scale applied to S in fp32). P.V runs in fp32 (P unrounded, V widened from bf16).
  - All accumulators are fp32.
- **Softmax:** uses a finite −1e30 sentinel instead of −inf, because of fast-math. A fully masked row or block yields max −1e30, sum 0, acc 0, and the production combine kernel is used unchanged.
- **Planted case:** the cache holds T + 1 tokens, so the N2 leak stays in range. Because lengths[0] = lengths[1] − 1 for k ≥ 2, the key at lengths[0] is twice the planted norm and aligned with queries 0 and 1. That way a leak into query 0 is large and query 1 still sees a dominant key.

## Not done, or worth knowing
- **Launcher not executable:** `chmod +x` needed approval it didn't get, and so did `zsh -n`, so its syntax is unchecked.
- **Formatting not machine-checked:** black and isort aren't installed in the fork venv. I wrapped the fork file's code lines to 88 columns by hand; strings and the docstring stay long, as in `m72_mq_decode.py`. The stack files' new lines are ≤ 120.
- **k = 1 is slower:** mma is 1.4–1.8× slower than the baselines at k = 1 (32768: mma TQ4 0.841 ms vs mq best 0.420 ms). With 6 rows padded to 8 there is one simdgroup per threadgroup. The MTP OFF projection takes the faster arm per checkpoint, as the spec says.
- **Long-T accuracy reference is slow:** checkpoint accuracy uses an fp32 reference on the CPU stream. At 262,144 tokens it costs about 4 GB of fp32 K/V and some CPU seconds per k, outside the timed regions.
