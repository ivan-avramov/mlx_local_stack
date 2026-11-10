#!/usr/bin/env python3
"""M72 spike F3 (S20-P13 design de-risk): TQ4 keys unpacked straight into Neural Accelerator fragments.

Premise to test before a verify / prefill kernel is specified on it: with MLX's NAX fragment (16 x 16, a lane holds rows
fm, fm + 8 and four consecutive columns fn..fn + 3, fn in {0, 4, 8, 12}), a K fragment (tokens x head dims) needs exactly one
16-bit half of a packed TurboQuant word per token row, so a lane can read and unpack its own elements into registers (codebook
lookup by simd_shuffle) with no threadgroup tile, no barrier and no cooperative load, and feed matmul2d directly.

Kernel: S = Q . K^T for 32 query rows (2 row fragments) over N tokens, D = 256, one KV head, keys from a real
TurboQuantKVCache (4-bit MSE, rotated space; key norm applied to S's columns). Each simdgroup owns a contiguous token range;
4 simdgroups per threadgroup; no threadgroup memory. Checked against S from the codec's own dequantization; timed against the
same kernel on bf16 keys (direct fragment loads, MLX's attention_nax pattern) and against the K-bytes read ceilings.
Run (quiet box): PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/spike_f3_tq4_nax_scores.py [--n 260096]
"""

import argparse
import sys
from pathlib import Path

import mlx.core as mx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spike_f2_nax_matmul import HEADER, timeit  # noqa: E402

TOK_PER_SG = 512  # tokens per simdgroup (default; --tps overrides)

COMMON = """
    using F = BaseNAXFrag;
    typedef F::dtype_frag_t<half> HF;
    typedef F::dtype_frag_t<QT> QF;
    typedef F::dtype_frag_t<float> FF;
    uint lane = thread_index_in_simdgroup;
    uint sgi = simdgroup_index_in_threadgroup;
    uint sg = threadgroup_position_in_grid.x * 4 + sgi;
    uint t_begin = sg * TPS;
#ifdef TG_CODEBOOK
    threadgroup half cbs[16];
    threadgroup half2 lut[256];                 // byte -> (codebook[lo nibble], codebook[hi nibble])
    uint tid = thread_position_in_threadgroup.x;
    if (tid < 16) cbs[tid] = static_cast<half>(codebook[tid]);
    for (uint b = tid; b < 256; b += 128) lut[b] = half2(static_cast<half>(codebook[b & 15]), static_cast<half>(codebook[b >> 4]));
    threadgroup_barrier(mem_flags::mem_threadgroup);
#endif
#ifdef STAGE
    threadgroup uint stage_all[4 * 32 * 32];  // per simdgroup: 32 tokens x 32 packed words (4 KB)
    threadgroup uint* stage = stage_all + sgi * 1024;
#endif
    if (t_begin >= N) return;
    uint t_end = min(t_begin + (uint)TPS, (uint)N);
    short2 sc = F::get_coord();            // (col fn, row fm) of this lane's first element
    short fn = sc.x, fm = sc.y;
    QF qa[16][2];                          // Q fragments, all 16 head-dim steps x 2 row fragments (registers)
    for (short dk = 0; dk < 16; dk++) {
        F::load(qa[dk][0], Q + dk * 16, Int<256>{}, Int<1>{});
        F::load(qa[dk][1], Q + 16 * 256 + dk * 16, Int<256>{}, Int<1>{});
    }
    float rowacc = 0;
"""

KFRAG_TQ4 = """
            // K fragment j (16 tokens) for head-dim step dk: lane rows = tokens fm, fm + 8; cols = dims dk*16+fn..+3
            QF kb[2];
            for (short j = 0; j < 2; j++) {
                for (short rr = 0; rr < 2; rr++) {
                    uint t = ts + j * 16 + fm + rr * 8;
                    uint w = packed[(ulong)t * 32 + dk * 2 + (fn >> 3)];
                    uint bits = (w >> ((fn & 7) * 4)) & 0xFFFFu;
                    for (short c = 0; c < 4; c++) {
                        kb[j][rr * 4 + c] = static_cast<QT>(simd_shuffle(cbl, ushort((bits >> (4 * c)) & 15u)));
                    }
                }
            }
"""

KFRAG_TGCB = """
            QF kb[2];
            for (short j = 0; j < 2; j++) {
                for (short rr = 0; rr < 2; rr++) {
                    uint t = ts + j * 16 + fm + rr * 8;
                    uint w = packed[(ulong)t * 32 + dk * 2 + (fn >> 3)];
                    uint bits = (w >> ((fn & 7) * 4)) & 0xFFFFu;
                    for (short c = 0; c < 4; c++) kb[j][rr * 4 + c] = static_cast<QT>(cbs[(bits >> (4 * c)) & 15u]);
                }
            }
"""

KFRAG_STAGE = """
            QF kb[2];
            for (short j = 0; j < 2; j++) {
                for (short rr = 0; rr < 2; rr++) {
                    uint tt = j * 16 + fm + rr * 8;
                    uint w = stage[tt * 32 + dk * 2 + (fn >> 3)];
                    uint bits = (w >> ((fn & 7) * 4)) & 0xFFFFu;
#ifdef LUT
                    half2 lo = lut[bits & 0xFFu], hi = lut[bits >> 8];
                    kb[j][rr * 4 + 0] = static_cast<QT>(lo.x); kb[j][rr * 4 + 1] = static_cast<QT>(lo.y);
                    kb[j][rr * 4 + 2] = static_cast<QT>(hi.x); kb[j][rr * 4 + 3] = static_cast<QT>(hi.y);
#else
                    for (short c = 0; c < 4; c++) kb[j][rr * 4 + c] = static_cast<QT>(cbs[(bits >> (4 * c)) & 15u]);
#endif
                }
            }
"""

KFRAG_ALU = """
            QF kb[2];
            for (short j = 0; j < 2; j++) {
                for (short rr = 0; rr < 2; rr++) {
                    uint t = ts + j * 16 + fm + rr * 8;
                    uint w = packed[(ulong)t * 32 + dk * 2 + (fn >> 3)];
                    uint bits = (w >> ((fn & 7) * 4)) & 0xFFFFu;
                    for (short c = 0; c < 4; c++) kb[j][rr * 4 + c] = static_cast<QT>(cb_select((bits >> (4 * c)) & 15u));
                }
            }
"""


def alu_codebook_fn(cb):
    """Metal function selecting codebook[i] by a 4-level select tree over the index bits (values baked in as literals)."""
    v = [f"{float(x):.9e}h" for x in cb]
    lines = ["inline half cb_select(uint i) {", "    bool x0 = i & 1u, x1 = i & 2u, x2 = i & 4u, x3 = i & 8u;"]
    l1 = [f"    half a{k} = select({v[2 * k]}, {v[2 * k + 1]}, x0);" for k in range(8)]
    l2 = [f"    half b{k} = select(a{2 * k}, a{2 * k + 1}, x1);" for k in range(4)]
    l3 = [f"    half c{k} = select(b{2 * k}, b{2 * k + 1}, x2);" for k in range(2)]
    return "\n".join(lines + l1 + l2 + l3 + ["    return select(c0, c1, x3);", "}"]) + "\n"


STAGE_LOAD = """
        // coalesced: the simdgroup copies the tile's 32 tokens x 32 words (lane l takes words l, l + 32, ...)
        for (uint i = 0; i < 32; i++) stage[i * 32 + lane] = packed[(ulong)(ts + i) * 32 + lane];
        simdgroup_barrier(mem_flags::mem_threadgroup);
"""

KFRAG_BF16 = """
            QF kb[2];
            F::load(kb[0], K + (ulong)ts * 256 + dk * 16, Int<256>{}, Int<1>{});
            F::load(kb[1], K + (ulong)(ts + 16) * 256 + dk * 16, Int<256>{}, Int<1>{});
"""


ARMS = ("tq4_shuffle", "tq4_tgcb", "tq4_stage", "tq4_alu", "native16")
CODEBOOK = None  # set in main (the ALU variant bakes the values into its source)


def kernel_source(arm, write_s):
    defs = {
        "tq4_tgcb": ["TG_CODEBOOK"],
        "tq4_stage": ["TG_CODEBOOK", "STAGE"],
        "tq4_stage_lut": ["TG_CODEBOOK", "STAGE", "LUT"],
    }.get(arm, [])
    pre = "".join(f"#define {d} 1\n" for d in defs) + COMMON
    if arm == "tq4_shuffle":
        pre += "    half cbl = static_cast<half>(codebook[lane & 15]);\n"
    kfrag = {
        "tq4_shuffle": KFRAG_TQ4,
        "tq4_tgcb": KFRAG_TGCB,
        "tq4_stage": KFRAG_STAGE,
        "tq4_stage_lut": KFRAG_STAGE,
        "tq4_alu": KFRAG_ALU,
        "native16": KFRAG_BF16,
    }[arm]
    body = (
        """
    for (uint ts = t_begin; ts < t_end; ts += 32) {
        FF s00 = FF(0), s01 = FF(0), s10 = FF(0), s11 = FF(0);
"""
        + (STAGE_LOAD if "STAGE" in defs else "")
        + """
        for (short dk = 0; dk < 16; dk++) {
"""
        + kfrag
        + """
            F::mma(s00, s01, qa[dk][0], metal::bool_constant<false>{}, kb[0], kb[1], metal::bool_constant<true>{});
            F::mma(s10, s11, qa[dk][1], metal::bool_constant<false>{}, kb[0], kb[1], metal::bool_constant<true>{});
        }
"""
    )
    if arm != "native16":
        body += """
        for (short i = 0; i < F::kElemsPerFrag; i++) {   // key norm scales S's columns (tokens)
            short col = fn + (i & 3);
            float n0 = static_cast<float>(norms[ts + col]), n1 = static_cast<float>(norms[ts + 16 + col]);
            s00[i] *= n0; s10[i] *= n0; s01[i] *= n1; s11[i] *= n1;
        }
"""
    if "STAGE" in defs:
        body += "        simdgroup_barrier(mem_flags::mem_threadgroup);\n"
    if write_s:
        body += """
        for (short i = 0; i < F::kElemsPerFrag; i++) {
            short2 rc = F::get_coord(i);
            S[(ulong)rc.y * N + ts + rc.x] = s00[i];
            S[(ulong)rc.y * N + ts + 16 + rc.x] = s01[i];
            S[(ulong)(16 + rc.y) * N + ts + rc.x] = s10[i];
            S[(ulong)(16 + rc.y) * N + ts + 16 + rc.x] = s11[i];
        }
    }
"""
    else:
        body += """
        for (short i = 0; i < F::kElemsPerFrag; i++) rowacc += s00[i] + s01[i] + s10[i] + s11[i];
    }
    S[sg * 32 + lane] = rowacc;
"""
    return pre + body


def build(arm, write_s):
    names = ["Q", "packed", "norms", "codebook"] if arm != "native16" else ["Q", "K"]
    header = HEADER + (alu_codebook_fn(CODEBOOK) if arm == "tq4_alu" else "")
    return mx.fast.metal_kernel(
        name=f"f3_{arm}_{'s' if write_s else 'r'}",
        input_names=names,
        output_names=["S"],
        header=header,
        source=kernel_source(arm, write_s),
    )


def run(kern, inputs, N, qt, write_s, tps=None):
    tps = tps or TOK_PER_SG
    n_sg = -(-N // tps)
    n_tg = -(-n_sg // 4)
    shape = (32, N) if write_s else (n_tg * 4 * 32,)
    return kern(
        inputs=inputs,
        template=[("N", N), ("TPS", tps), ("QT", mx.float16 if qt == "half" else mx.bfloat16)],
        grid=(n_tg * 128, 1, 1),
        threadgroup=(128, 1, 1),
        output_shapes=[shape],
        output_dtypes=[mx.float32],
    )[0]


def main():
    from mlx_vlm.turboquant import TurboQuantKVCache

    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=260096)
    ap.add_argument("--tps", type=int, nargs="+", default=[512, 256, 128, 64, 32])
    a = ap.parse_args()
    N = a.n - a.n % TOK_PER_SG
    print(f"spike F3 — MLX {mx.__version__}, {mx.device_info().get('architecture')}, N = {N}", flush=True)
    mx.random.seed(3)
    cache = TurboQuantKVCache(bits=4, max_kv_size=N, prealloc_tokens=N)
    for off in range(0, N, 4096):
        kc = mx.random.normal((1, 1, min(4096, N - off), 256)).astype(mx.bfloat16)
        cache.update_and_fetch(kc, kc)
        mx.eval(cache.keys, cache.values)
    ks = cache.keys
    packed = mx.contiguous(ks.indices[0, 0, :N])
    norms = mx.contiguous(ks.norms[0, 0, :N])
    cb = cache.key_codec.codebook.astype(mx.float32)
    global CODEBOOK
    CODEBOOK = np.array(cb).astype(np.float16).tolist()
    q = mx.random.normal((32, 256)).astype(mx.bfloat16)
    q_rot = cache.key_codec.prepare_queries(q.reshape(1, 1, 32, 256)).reshape(32, 256)
    mx.eval(packed, norms, q_rot)
    # reference: dequantized keys in the rotated space (codebook[idx] * norm), fp32
    from mlx_vlm import turboquant as tq

    idx = tq._unpack_lowbit(packed, 4, 256).astype(mx.int32).reshape(N, 256)
    k_rot = mx.take(cb, idx, axis=0) * norms.astype(mx.float32)[:, None]
    k_bf16 = k_rot.astype(mx.bfloat16)  # native16 arm: same values as bf16 keys (timing arm; layout is what matters)
    mx.eval(k_rot, k_bf16)
    ref_tq = q_rot.astype(mx.float32) @ k_rot.T
    ref_16 = q.astype(mx.float32) @ k_bf16.astype(mx.float32).T
    mx.eval(ref_tq, ref_16)
    res = {}
    tq_in = [q_rot.astype(mx.float16), packed, norms, cb]
    cases = [(arm, "half", tq_in, ref_tq) for arm in ARMS if arm != "native16"] + [
        ("native16", "bfloat", [q, k_bf16], ref_16)
    ]
    for arm, qt, inputs, ref in cases:
        try:
            S = run(build(arm, True), inputs, N, qt, True)
            mx.eval(S)
        except Exception as exc:
            print(f"[{arm}] FAIL: {str(exc)[:3000]}")
            return 1
        err = (mx.max(mx.abs(S - ref)) / mx.max(mx.abs(ref))).item()
        kr = build(arm, False)
        kbytes = packed.nbytes + norms.nbytes if arm != "native16" else k_bf16.nbytes
        print(
            f"[{arm}] S = Q.K^T 32 x {N} x 256: rel err vs dequantized reference {err:.2e} "
            f"({'OK' if err < 5e-3 else 'WRONG'}); K bytes {kbytes / 1e6:.0f} MB",
            flush=True,
        )
        for tps in a.tps:
            ms = timeit(lambda kr=kr, inputs=inputs, qt=qt, tps=tps: run(kr, inputs, N, qt, False, tps), n=30)
            res[(arm, tps)] = ms
            print(
                f"[{arm}] tokens/simdgroup {tps}: {ms:.3f} ms, {kbytes / ms / 1e6:.0f} GB/s of K bytes, "
                f"{2 * 32 * N * 256 / ms / 1e9:.1f} TFLOPS",
                flush=True,
            )
    best = {arm: min(v for (a_, _), v in res.items() if a_ == arm) for arm in ARMS}
    for arm in ARMS:
        print(f"[F3] best {arm}: {best[arm]:.3f} ms ({best[arm] / best['native16']:.2f} x native16)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
