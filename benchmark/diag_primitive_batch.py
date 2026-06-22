"""Primitive batch-dependence test: which gemma4 op makes a multi-token (verify)
forward differ from single-token (decode)?  NO model load — random tensors only,
so it isolates the *primitive*, not accumulated drift.

The two batch-size-dependent suspects (per gemma-4-26b-A4B config: KV-share OFF,
per-layer-input OFF) are:
  (1) mx.fast.scaled_dot_product_attention  — L>1 "prefill" (mask="causal") vs
      L==1 "decode" (mask=None) use different Metal kernels.
  (2) SwitchGLU / gather_mm(/gather_qmm)     — batched-K vs per-token expert gather.

For each: process K positions BATCHED, then process the SAME positions ONE AT A
TIME, and compare. >1e-3 maxdiff => that primitive is batch-dependent (the inherent
source of suffix non-losslessness); ~0 => innocent.
"""
import mlx.core as mx
import mlx.nn as nn
from mlx_lm.models.switch_layers import SwitchGLU
from mlx_vlm.models.gemma4.language import GeGLU

mx.random.seed(0)

# gemma-4-26b-a4b-it-8bit dims
H = 2816
MOE_I = 704
E = 128
TOPK = 8
GS, BITS = 64, 8
P = 80   # "prompt"/cache prefix length
K = 90   # generated/verify block length


def sep(t):
    print(f"\n========== {t} ==========", flush=True)


def sdpa_test(name, n_heads, n_kv, hd, dtype):
    """Compare L>1 causal forward vs per-position L==1 forward, same K/V."""
    scale = hd ** -0.5
    q = mx.random.normal((1, n_heads, P + K, hd)).astype(dtype)
    k = mx.random.normal((1, n_kv, P + K, hd)).astype(dtype)
    v = mx.random.normal((1, n_kv, P + K, hd)).astype(dtype)
    qb = q[:, :, P:P + K, :]                       # the K "verify" queries
    # multi-query: mask="causal" aligns query j to key pos P+j (offset = klen-qlen)
    out_multi = mx.fast.scaled_dot_product_attention(qb, k, v, scale=scale, mask="causal")
    outs = []
    for j in range(K):                             # single-query decode, mask=None
        oj = mx.fast.scaled_dot_product_attention(
            qb[:, :, j:j + 1, :], k[:, :, :P + j + 1, :], v[:, :, :P + j + 1, :],
            scale=scale, mask=None)
        outs.append(oj)
    out_single = mx.concatenate(outs, axis=2)
    mx.eval(out_multi, out_single)
    perpos = mx.max(mx.abs(out_multi - out_single), axis=(0, 1, 3))  # [K]
    mx.eval(perpos)
    dl = perpos.tolist()
    mxd = max(dl)
    nbad = sum(1 for x in dl if x > 1e-3)
    first = next((i for i, x in enumerate(dl) if x > 1e-3), None)
    print(f"  SDPA {name:8s} heads={n_heads} kv={n_kv} hd={hd} {str(dtype):>14s}: "
          f"maxdiff={mxd:.5f}  #pos>1e-3={nbad}/{K} first@{first}", flush=True)
    return mxd


def switchglu_test(dtype, quantize):
    sg = SwitchGLU(input_dims=H, hidden_dims=MOE_I, num_experts=E,
                   activation=GeGLU(), bias=False)
    sg.set_dtype(dtype)
    label = f"SwitchGLU {'q8' if quantize else 'fp':>3s} {str(dtype):>14s}"
    if quantize:
        nn.quantize(sg, group_size=GS, bits=BITS)
    x = mx.random.normal((1, K, H)).astype(dtype)
    # random top-k expert indices per token (distinct within a token)
    idx = mx.stack([mx.random.permutation(E)[:TOPK] for _ in range(K)])[None]  # [1,K,TOPK]
    idx = idx.astype(mx.uint32)
    y_multi = sg(x, idx)                           # [1,K,TOPK,H]
    outs = [sg(x[:, j:j + 1, :], idx[:, j:j + 1, :]) for j in range(K)]
    y_single = mx.concatenate(outs, axis=1)
    mx.eval(y_multi, y_single)
    perpos = mx.max(mx.abs(y_multi - y_single), axis=(0, 2, 3))  # [K]
    mx.eval(perpos)
    dl = perpos.tolist()
    mxd = max(dl)
    nbad = sum(1 for x in dl if x > 1e-3)
    first = next((i for i, x in enumerate(dl) if x > 1e-3), None)
    print(f"  {label}: maxdiff={mxd:.5f}  #pos>1e-3={nbad}/{K} first@{first}", flush=True)
    return mxd


def main():
    for dt in (mx.bfloat16, mx.float16, mx.float32):
        sep(f"SDPA  dtype={dt}")
        sdpa_test("full", 16, 2, 512, dt)
        sdpa_test("sliding", 16, 8, 256, dt)

    for dt in (mx.bfloat16, mx.float16, mx.float32):
        sep(f"SwitchGLU dtype={dt}")
        switchglu_test(dt, quantize=False)
        switchglu_test(dt, quantize=True)

    print("\nINTERPRETATION: any primitive with maxdiff >~1e-3 is batch-size-dependent "
          "=> verify(multi) != decode(single) => inherent suffix non-losslessness source.",
          flush=True)


if __name__ == "__main__":
    main()
