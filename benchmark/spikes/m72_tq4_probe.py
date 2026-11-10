#!/usr/bin/env python3
"""M72 step 1.1 probe: TurboQuant 4 KV vs native16 attention, per full-attention layer.

Shapes of Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed (and Qwen3.8-27B-mlx-uniform-4bit): 24 query heads,
4 KV heads, head dim 256, bf16 activations; 16 of 64 layers are full attention. Synthetic K/V (kernel timing is
data-independent), no model load. Calls the fork's production dispatch (`models.base.scaled_dot_product_attention`,
`mtp_verify_scan.{joint,per_query}_attention`) plus isolated kernels for the split and bandwidth ceilings.

Run (bare process; caps set below per docs/box-notes.md):
  PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/m72_tq4_probe.py --out <json>
NAX-off control: the same with MLX_METAL_GPU_ARCH=applegpu_g16s in the environment.

M72 step 1.2 (D1 + D2): ``--mode mq`` measures the fork's dev prototype ``dev/m72_mq_decode.py`` (stride-aware
multi-query TQ4 decode) against matched in-process baselines (native16 SDPA / joint, TQ4 production decode / per-query
verify) for k = 1..5, after an exactness sweep (per query, bit-identical to the production singleton path) that includes
a negative control. Prefill is not measured in this mode.
"""

import argparse
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

import mlx.core as mx

import mlx_vlm
from mlx_vlm import turboquant as tq_mod
from mlx_vlm.attention_policy import FusedV1Policy
from mlx_vlm.models.base import scaled_dot_product_attention
from mlx_vlm.mtp_verify_scan import joint_attention, per_query_attention
from mlx_vlm.turboquant import TurboQuantKVCache

import m72_gates  # noqa: E402  (sibling module; the script dir is on sys.path)

NQ, NKV, D = 24, 4, 256
R = NQ // NKV
CAP = 262144
CHUNK = 512  # prefill_step_size of the pick
SCALE = 1.0 / math.sqrt(D)
DT = mx.bfloat16
CHECKPOINTS = (8192, 32768, 131072, 196608, 260096, 262144)  # 196608 / 260096 = P475 rungs (below the cap: sliced layout)
VERIFY_LENGTHS = (2, 3, 4, 5)
DECOMPOSED_MAX_T = 131072  # its fp32 score tensor is 24*512*T*4 bytes; skipped above (memory)


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def power_state():
    try:
        ac = subprocess.run(["pmset", "-g", "ac"], capture_output=True, text=True, timeout=10).stdout
        batt = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=10).stdout
    except Exception as exc:  # the probe refuses below if power is unreadable
        return {"error": repr(exc)}
    watts = next((l.split("=")[1].strip() for l in ac.splitlines() if "Wattage" in l), None)
    volts = next((l.split("=")[1].strip() for l in ac.splitlines() if "Voltage" in l), None)
    pct = next((tok for tok in batt.split() if tok.endswith("%;")), None)
    return {"wattage": watts, "voltage": volts, "battery": pct and pct.rstrip(";")}


def power_ok(p):
    try:
        return p.get("wattage") == "140W" and p.get("voltage") == "28000mV" and int(p["battery"].rstrip("%")) > 20
    except Exception:
        return False


def timeit(fn, min_iters=5, min_s=0.5, warmup=2, max_iters=200):
    for _ in range(warmup):
        mx.eval(fn())
    mx.synchronize()
    ts = []
    t_end = time.perf_counter() + min_s
    while len(ts) < min_iters or (time.perf_counter() < t_end and len(ts) < max_iters):
        t0 = time.perf_counter()
        mx.eval(fn())
        mx.synchronize()
        ts.append(time.perf_counter() - t0)
    return {"median_ms": statistics.median(ts) * 1e3, "min_ms": min(ts) * 1e3, "n": len(ts)}


def maxdiff(a, b):
    a32, b32 = a.astype(mx.float32), b.astype(mx.float32)
    num = mx.max(mx.abs(a32 - b32)).item()
    den = mx.max(mx.abs(b32)).item()
    return {"max_abs": num, "rel_to_max": num / den if den else None}


def tq_state_bytes(state):
    return int(state.indices.nbytes + state.norms.nbytes)


def decode_split(tq, ks, vs, q):
    """The 2-pass GQA decode as `decode_attention` dispatches it, kernel by kernel (T > 2048)."""
    T = ks.norms.shape[2]
    key_bits, val_bits = int(tq.key_codec.bits), int(tq.value_codec.bits)
    grouped = (q * SCALE).reshape(1, NKV, R, 1, D)
    hpg = 2 if R % 2 == 0 else 1
    nb = 64 if T <= 8192 else 128 if T <= 32768 else 256 if T <= 65536 else 512
    nb *= hpg
    pass1 = tq_mod._fused_mse_decode_2pass_1_kernel(key_bits, val_bits, D, hpg)
    pass2 = tq_mod._fused_mse_decode_2pass_2_kernel()
    BQH = NQ

    def prep():
        return tq.key_codec.prepare_queries(grouped).reshape(BQH, D)

    q_rot = prep()
    mx.eval(q_rot)

    def p1(q_rot=q_rot):
        return pass1(
            inputs=[q_rot, ks.norms, ks.indices, tq.key_codec.codebook, vs.norms, vs.indices, tq.value_codec.codebook],
            template=[("Dim", D), ("RepeatCount", R), ("Blocks", nb),
                      ("KPackedWidth", ks.indices.shape[-1]), ("VPackedWidth", vs.indices.shape[-1])],
            grid=(NKV * (R // hpg) * nb * 32, 1, 1), threadgroup=(32, 1, 1),
            output_shapes=[(BQH * nb, D), (BQH * nb,), (BQH * nb,)],
            output_dtypes=[mx.float32] * 3,
        )

    acc = p1()
    mx.eval(acc)

    def p2(acc=acc):
        return pass2(inputs=list(acc), template=[("Dim", D), ("Blocks", nb)], grid=(BQH * 1024, 1, 1),
                     threadgroup=(1024, 1, 1), output_shapes=[(BQH, D)], output_dtypes=[mx.float32])[0]

    out = p2()
    mx.eval(out)

    def rot(out=out):
        return tq.value_codec._rotate_inverse(out.reshape(1, NKV, R, D))

    full = rot().reshape(1, NQ, 1, D).astype(DT)
    return {"prepare_queries": timeit(prep), "pass1": timeit(p1), "pass2": timeit(p2),
            "rotate_inverse": timeit(rot), "num_blocks": nb}, full


def measure_checkpoint(T, tq, K, V, policy):
    res = {"T": T}
    ks_raw, vs_raw = tq.state
    ks = tq_mod._QuantizedStateProxy(ks_raw, T, NKV)
    vs = tq_mod._QuantizedStateProxy(vs_raw, T, NKV)
    Kt, Vt = K[:, :, :T, :], V[:, :, :T, :]
    tq_bytes = tq_state_bytes(ks_raw) + tq_state_bytes(vs_raw)
    n16_bytes = 2 * NKV * T * D * 2
    res["bytes"] = {"tq4_kv": tq_bytes, "native16_kv": n16_bytes}

    # ---- decode (L = 1) ----
    q1 = mx.random.normal((1, NQ, 1, D)).astype(DT)
    dec = {}
    dec["native16"] = timeit(lambda: scaled_dot_product_attention(q1, Kt, Vt, cache=None, scale=SCALE, mask=None,
                                                                  policy=policy))
    dec["tq4"] = timeit(lambda: scaled_dot_product_attention(q1, ks, vs, cache=tq, scale=SCALE, mask=None))
    tq._decode_2pass_use_legacy = True
    dec["tq4_legacy"] = timeit(lambda: scaled_dot_product_attention(q1, ks, vs, cache=tq, scale=SCALE, mask=None))
    tq._decode_2pass_use_legacy = False
    split, split_out = decode_split(tq, ks_raw, vs_raw, q1)
    dec["tq4_split"] = split
    prod_out = scaled_dot_product_attention(q1, ks, vs, cache=tq, scale=SCALE, mask=None)
    dec["split_vs_production"] = maxdiff(split_out, prod_out)
    # Contiguous controls. Below the cap the shipped state is a time-slice of the full-cap preallocated buffer
    # (non-contiguous across heads); these copies isolate what that layout costs and give clean byte ceilings.
    ks_c_raw = tq_mod.TurboQuantMSEState(mx.contiguous(ks_raw.norms), mx.contiguous(ks_raw.indices))
    vs_c_raw = tq_mod.TurboQuantMSEState(mx.contiguous(vs_raw.norms), mx.contiguous(vs_raw.indices))
    Kc, Vc = mx.contiguous(Kt), mx.contiguous(Vt)
    mx.eval(ks_c_raw, vs_c_raw, Kc, Vc)
    ks_c = tq_mod._QuantizedStateProxy(ks_c_raw, T, NKV)
    vs_c = tq_mod._QuantizedStateProxy(vs_c_raw, T, NKV)
    dec["tq4_contiguous"] = timeit(lambda: scaled_dot_product_attention(q1, ks_c, vs_c, cache=tq, scale=SCALE,
                                                                        mask=None))
    dec["native16_contiguous"] = timeit(lambda: scaled_dot_product_attention(q1, Kc, Vc, cache=None, scale=SCALE,
                                                                             mask=None, policy=policy))
    split_c, split_c_out = decode_split(tq, ks_c_raw, vs_c_raw, q1)
    dec["tq4_split_contiguous"] = split_c
    dec["contiguous_vs_production"] = maxdiff(split_c_out, prod_out)
    # bandwidth ceilings: a plain reduction over exactly the bytes each format must read (contiguous copies)
    ki, vi, kn, vn = ks_c_raw.indices, vs_c_raw.indices, ks_c_raw.norms, vs_c_raw.norms
    dec["read_tq4_bytes"] = timeit(lambda: [mx.sum(ki), mx.sum(vi), mx.sum(kn), mx.sum(vn)])
    dec["read_native16_bytes"] = timeit(lambda: [mx.sum(Kc), mx.sum(Vc)])
    for name in ("native16", "tq4", "tq4_legacy", "tq4_contiguous", "native16_contiguous"):
        b = n16_bytes if name.startswith("native16") else tq_bytes
        dec[name]["eff_GBps"] = b / (dec[name]["median_ms"] * 1e-3) / 1e9
    dec["read_tq4_bytes"]["GBps"] = tq_bytes / (dec["read_tq4_bytes"]["median_ms"] * 1e-3) / 1e9
    dec["read_native16_bytes"]["GBps"] = n16_bytes / (dec["read_native16_bytes"]["median_ms"] * 1e-3) / 1e9
    dec["tq4_vs_native16_out"] = maxdiff(prod_out, scaled_dot_product_attention(q1, Kt, Vt, cache=None, scale=SCALE,
                                                                                 mask=None))
    res["decode"] = dec
    log(f"T={T} decode: n16 {dec['native16']['median_ms']:.3f} ms ({dec['native16']['eff_GBps']:.0f} GB/s), "
        f"tq4 {dec['tq4']['median_ms']:.3f} ms ({dec['tq4']['eff_GBps']:.0f} GB/s), "
        f"tq4 contiguous {dec['tq4_contiguous']['median_ms']:.3f} ms, "
        f"tq4-bytes read ceiling {dec['read_tq4_bytes']['median_ms']:.3f} ms ({dec['read_tq4_bytes']['GBps']:.0f} GB/s)")

    # ---- MTP verify blocks (L = k) ----
    ver = {}
    for k in VERIFY_LENGTHS:
        qk = mx.random.normal((1, NQ, k, D)).astype(DT)
        ver[str(k)] = {
            "native16_joint": timeit(lambda: joint_attention(qk, Kt, Vt, cache=None, scale=SCALE, mask="causal")),
            "native16_per_query": timeit(lambda: per_query_attention(qk, Kt, Vt, cache=None, scale=SCALE,
                                                                     mask="causal")),
            "tq4_per_query": timeit(lambda: per_query_attention(qk, ks, vs, cache=tq, scale=SCALE, mask="causal")),
            "tq4_per_query_contiguous_parent": timeit(lambda: per_query_attention(qk, ks_c, vs_c, cache=tq,
                                                                                  scale=SCALE, mask="causal")),
        }
    res["verify"] = ver
    log(f"T={T} verify k=3: n16 joint {ver['3']['native16_joint']['median_ms']:.3f} ms, "
        f"tq4 per-query {ver['3']['tq4_per_query']['median_ms']:.3f} ms")

    # ---- prefill chunk (L = 512 queries ending at T, causal) ----
    qp = mx.random.normal((1, NQ, CHUNK, D)).astype(DT)
    pre = {}
    pre["native16_auto"] = timeit(lambda: scaled_dot_product_attention(qp, Kt, Vt, cache=None, scale=SCALE,
                                                                       mask="causal", policy=None), min_iters=3)
    pre["native16_fused_v1"] = timeit(lambda: scaled_dot_product_attention(qp, Kt, Vt, cache=None, scale=SCALE,
                                                                           mask="causal", policy=policy), min_iters=3)
    pre["tq4_production"] = timeit(lambda: scaled_dot_product_attention(qp, ks, vs, cache=tq, scale=SCALE,
                                                                        mask="causal"), min_iters=3, warmup=1)
    prod_pre = scaled_dot_product_attention(qp, ks, vs, cache=tq, scale=SCALE, mask="causal")

    def deq():
        k, v = tq.dequantize(ks, vs)
        return k.astype(DT), v.astype(DT)

    def deq_fused():
        k, v = deq()
        return mx.fast.scaled_dot_product_attention(qp, k, v, scale=SCALE, mask="causal", force_fused=True)

    def deq_rot():  # unit vectors stay in the codec's rotated space: unpack + codebook + norm, no inverse rotation
        out = []
        for st, codec in ((ks_raw, tq.key_codec), (vs_raw, tq.value_codec)):
            idx = tq_mod._unpack_lowbit(st.indices, int(codec.bits), D).astype(mx.int32)
            out.append((mx.take(codec.codebook, idx, axis=0) * st.norms[..., None]).astype(DT))
        return out

    def rot_fused():  # exact: q·k = (qR)·(kR); sum_t w_t v_t = (sum_t w_t v_t R) R^T, R orthogonal per codec
        k, v = deq_rot()
        qr = tq.key_codec.prepare_queries(qp).astype(DT)
        o = mx.fast.scaled_dot_product_attention(qr, k, v, scale=SCALE, mask="causal", force_fused=True)
        return tq.value_codec._rotate_inverse(o.astype(mx.float32)).astype(DT)

    pre["tq4_dequant_rotated_only"] = timeit(deq_rot, min_iters=3)
    pre["tq4_rotated_dequant_fused_sdpa"] = timeit(rot_fused, min_iters=3)
    pre["rotated_fused_vs_production"] = maxdiff(rot_fused(), prod_pre)
    pre["tq4_dequant_only"] = timeit(deq, min_iters=3)
    pre["tq4_dequant_fused_sdpa"] = timeit(deq_fused, min_iters=3)
    pre["dequant_fused_vs_production"] = maxdiff(deq_fused(), prod_pre)
    if T <= DECOMPOSED_MAX_T:
        tq._fused_prefill_enabled = True
        try:
            pre["tq4_decomposed"] = timeit(lambda: scaled_dot_product_attention(qp, ks, vs, cache=tq, scale=SCALE,
                                                                                mask="causal"), min_iters=3)
            pre["decomposed_vs_production"] = maxdiff(
                scaled_dot_product_attention(qp, ks, vs, cache=tq, scale=SCALE, mask="causal"), prod_pre)
        finally:
            tq._fused_prefill_enabled = False
    else:
        pre["tq4_decomposed"] = {"skipped": f"memory: fp32 scores {NQ * CHUNK * T * 4 / 1e9:.1f} GB"}
    res["prefill_chunk"] = pre
    log(f"T={T} prefill chunk: n16 auto {pre['native16_auto']['median_ms']:.1f} ms, fused_v1 "
        f"{pre['native16_fused_v1']['median_ms']:.1f} ms, tq4 prod {pre['tq4_production']['median_ms']:.1f} ms, "
        f"tq4 dequant+fused {pre['tq4_dequant_fused_sdpa']['median_ms']:.1f} ms, rotated-space dequant+fused "
        f"{pre['tq4_rotated_dequant_fused_sdpa']['median_ms']:.1f} ms")
    mx.clear_cache()
    return res


# ---------------- M72 1.2: D1 + D2 prototype (--mode mq) ----------------
MQ_LENGTHS = (1, 2, 3, 4, 5)
MQ_SWEEP_CAP = 40960
# lengths crossing the 8192 / 32768 block-count thresholds and tpb boundaries (verify blocks may straddle both)
MQ_SWEEP_T = (4096, 8190, 8193, 8320, 9000, 16385, 32766, 32770, 33025, 40000)


def fork_dev_module():
    dev = Path(mlx_vlm.__file__).resolve().parents[1] / "dev"
    sys.path.insert(0, str(dev))
    import m72_mq_decode

    return m72_mq_decode


def fork_sha():
    root = Path(mlx_vlm.__file__).resolve().parents[1]
    try:
        sha = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
                             timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", "mlx_vlm", "dev"],
                               capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception as exc:
        return {"error": repr(exc)}
    return {"head": sha, "dirty_paths": dirty.splitlines()}


def bits_equal(a, b):
    return a.shape == b.shape and a.dtype == b.dtype and bool(mx.all(a.view(mx.uint16) == b.view(mx.uint16)).item())


def singleton_reference(tq, ks, vs, q):
    k = q.shape[2]
    if k == 1:
        return scaled_dot_product_attention(q, ks, vs, cache=tq, scale=SCALE, mask=None)
    return per_query_attention(q, ks, vs, cache=tq, scale=SCALE, mask="causal")


def mq_exactness_sweep(mqm):
    """Small cache: every sweep length x k x G, bit-compared with the production singleton path per query."""
    tq = TurboQuantKVCache(bits=4, max_kv_size=MQ_SWEEP_CAP, prealloc_tokens=MQ_SWEEP_CAP)
    rows, off = [], 0
    for T in MQ_SWEEP_T:
        kc = mx.random.normal((1, NKV, T - off, D)).astype(DT)
        vc = mx.random.normal((1, NKV, T - off, D)).astype(DT)
        tq.update_and_fetch(kc, vc)
        mx.eval(tq.keys, tq.values)
        off = T
        ksr, vsr = tq.state
        ks, vs = tq_mod._QuantizedStateProxy(ksr, T, NKV), tq_mod._QuantizedStateProxy(vsr, T, NKV)
        for k in MQ_LENGTHS:
            q = mx.random.normal((1, NQ, k, D)).astype(DT)
            ref = singleton_reference(tq, ks, vs, q)
            lens = [T - k + 1 + j for j in range(k)]
            for G in (2, 1):
                got = mqm.mq_decode_attention(tq, q, SCALE, lens, heads_per_group=G)
                rows.append({"T": T, "k": k, "G": G, "classes": len(mqm._classes(lens, R)),
                             "bit_identical": bits_equal(got, ref)})
    # negative controls on the last state: lengths shifted by one token, and the joint (multi-query) TQ path
    T = MQ_SWEEP_T[-1]
    q = mx.random.normal((1, NQ, 3, D)).astype(DT)
    ref = singleton_reference(tq, ks, vs, q)
    shifted = mqm.mq_decode_attention(tq, q, SCALE, [T - 3 + j for j in range(3)])
    joint = joint_attention(q, ks, vs, cache=tq, scale=SCALE, mask="causal")
    neg = {"shifted_lengths_bit_identical": bits_equal(shifted, ref),
           "joint_tq_path_bit_identical": bits_equal(joint.astype(ref.dtype), ref),
           "joint_tq_path_vs_ref": maxdiff(joint, ref)}
    n_ok = sum(r["bit_identical"] for r in rows)
    log(f"mq exactness sweep: {n_ok}/{len(rows)} bit-identical, multi-class cases "
        f"{sum(r['classes'] > 1 for r in rows)}; negative controls {neg}")
    del tq
    mx.clear_cache()
    return {"rows": rows, "n": len(rows), "n_bit_identical": n_ok, "negative_controls": neg}


def measure_checkpoint_mq(T, tq, K, V, policy, mqm):
    res = {"T": T}
    ks_raw, vs_raw = tq.state
    ks = tq_mod._QuantizedStateProxy(ks_raw, T, NKV)
    vs = tq_mod._QuantizedStateProxy(vs_raw, T, NKV)
    Kt, Vt = K[:, :, :T, :], V[:, :, :T, :]
    tq_bytes = tq_state_bytes(ks_raw) + tq_state_bytes(vs_raw)
    res["bytes"] = {"tq4_kv": tq_bytes, "native16_kv": 2 * NKV * T * D * 2}
    ks_c_raw = tq_mod.TurboQuantMSEState(mx.contiguous(ks_raw.norms), mx.contiguous(ks_raw.indices))
    vs_c_raw = tq_mod.TurboQuantMSEState(mx.contiguous(vs_raw.norms), mx.contiguous(vs_raw.indices))
    mx.eval(ks_c_raw, vs_c_raw)
    ki, vi, kn, vn = ks_c_raw.indices, vs_c_raw.indices, ks_c_raw.norms, vs_c_raw.norms
    res["read_tq4_bytes"] = timeit(lambda: [mx.sum(ki), mx.sum(vi), mx.sum(kn), mx.sum(vn)])
    out = {}
    for k in MQ_LENGTHS:
        q = mx.random.normal((1, NQ, k, D)).astype(DT)
        lens = [T - k + 1 + j for j in range(k)]
        ref = singleton_reference(tq, ks, vs, q)
        row = {"lengths": lens, "classes": len(mqm._classes(lens, R))}
        if k == 1:
            row["native16"] = timeit(lambda: scaled_dot_product_attention(q, Kt, Vt, cache=None, scale=SCALE,
                                                                          mask=None, policy=policy))
            row["tq4_production"] = timeit(lambda: scaled_dot_product_attention(q, ks, vs, cache=tq, scale=SCALE,
                                                                                mask=None))
        else:
            row["native16_joint"] = timeit(lambda: joint_attention(q, Kt, Vt, cache=None, scale=SCALE,
                                                                   mask="causal"))
            row["tq4_production"] = timeit(lambda: per_query_attention(q, ks, vs, cache=tq, scale=SCALE,
                                                                       mask="causal"))
        for G in (2, 1):
            row[f"mq_g{G}"] = timeit(lambda G=G: mqm.mq_decode_attention(tq, q, SCALE, lens, heads_per_group=G))
            row[f"mq_g{G}_bit_identical"] = bits_equal(mqm.mq_decode_attention(tq, q, SCALE, lens,
                                                                               heads_per_group=G), ref)
            row[f"mq_g{G}"]["eff_GBps"] = tq_bytes / (row[f"mq_g{G}"]["median_ms"] * 1e-3) / 1e9
        out[str(k)] = row
    res["mq"] = out
    base1 = out["1"]
    log(f"T={T} mq: k=1 n16 {base1['native16']['median_ms']:.3f} / tq4 prod {base1['tq4_production']['median_ms']:.3f}"
        f" / mq g2 {base1['mq_g2']['median_ms']:.3f} ms; k=3 n16 joint {out['3']['native16_joint']['median_ms']:.3f}"
        f" / tq4 per-query {out['3']['tq4_production']['median_ms']:.3f} / mq g2 {out['3']['mq_g2']['median_ms']:.3f}"
        f" / g1 {out['3']['mq_g1']['median_ms']:.3f} ms; exact "
        f"{all(r[f'mq_g{G}_bit_identical'] for r in out.values() for G in (2, 1))}")
    mx.clear_cache()
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-t", type=int, default=CAP)
    ap.add_argument("--mode", choices=("full", "mq"), default="full")
    args = ap.parse_args()

    mx.set_cache_limit(4 << 30)
    mx.set_memory_limit(60 << 30)
    p0 = power_state()
    if not power_ok(p0):
        log(f"REFUSED: power state {p0}")
        sys.exit(3)
    one = mx.ones((16,))
    mx.eval(one)
    g0 = {"device_utilization_pct": m72_gates.gpu_utilization(),
          "tiny_op_floor_ms": m72_gates.tiny_op_floor_ms(lambda: (mx.eval(one + 1), mx.synchronize()))}
    if not m72_gates.gpu_idle_ok(g0):
        log(f"REFUSED: GPU not idle {g0} (limits {m72_gates.MAX_UTIL_PCT} % / {m72_gates.MAX_FLOOR_MS} ms; S20-P1)")
        sys.exit(5)
    meta = {
        "probe": "m72_tq4_probe", "mlx": mx.__version__, "device": mx.device_info(),
        "MLX_METAL_GPU_ARCH": os.environ.get("MLX_METAL_GPU_ARCH"), "python": platform.python_version(),
        "shapes": {"n_q": NQ, "n_kv": NKV, "head_dim": D, "dtype": "bfloat16", "chunk": CHUNK, "cap": CAP},
        "tq": {"bits": 4, "mode": "mse", "seed": tq_mod.DEFAULT_TURBOQUANT_SEED}, "power_start": p0,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "mode": args.mode, "gpu_idle_start": g0,
    }
    log(f"start {meta['device']['architecture']} MLX_METAL_GPU_ARCH={meta['MLX_METAL_GPU_ARCH']} power {p0}")

    mx.random.seed(72)
    policy = FusedV1Policy()
    mqm = None
    if args.mode == "mq":
        mqm = fork_dev_module()
        meta["fork"] = fork_sha()
        meta["mq_exactness"] = mq_exactness_sweep(mqm)
    tq = TurboQuantKVCache(bits=4, max_kv_size=CAP, prealloc_tokens=CAP)
    K = mx.zeros((1, NKV, CAP, D), dtype=DT)
    V = mx.zeros((1, NKV, CAP, D), dtype=DT)
    mx.eval(K, V)
    upd_tq, upd_n16, results = [], [], []
    off = 0
    targets = [t for t in CHECKPOINTS if t <= args.max_t]
    while off < targets[-1]:
        kc = mx.random.normal((1, NKV, CHUNK, D)).astype(DT)
        vc = mx.random.normal((1, NKV, CHUNK, D)).astype(DT)
        mx.eval(kc, vc)
        t0 = time.perf_counter()
        tq.update_and_fetch(kc, vc)
        mx.eval(tq.keys, tq.values)
        mx.synchronize()
        upd_tq.append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        K[:, :, off:off + CHUNK, :] = kc
        V[:, :, off:off + CHUNK, :] = vc
        mx.eval(K, V)
        mx.synchronize()
        upd_n16.append(time.perf_counter() - t0)
        off += CHUNK
        if off in targets:
            p = power_state()
            log(f"checkpoint T={off} power {p} active {mx.get_active_memory() / 1e9:.2f} GB cache "
                f"{mx.get_cache_memory() / 1e9:.2f} GB")
            if not power_ok(p):
                log(f"ABORT: power state {p}")
                sys.exit(4)
            if mqm is not None:
                r = measure_checkpoint_mq(off, tq, K, V, policy, mqm)
            else:
                r = measure_checkpoint(off, tq, K, V, policy)
            r["power"] = p
            r["kv_append_chunk_ms"] = {"tq4_mean_last64": statistics.mean(upd_tq[-64:]) * 1e3,
                                       "native16_mean_last64": statistics.mean(upd_n16[-64:]) * 1e3}
            r["peak_GB"] = mx.get_peak_memory() / 1e9
            results.append(r)
            mx.reset_peak_memory()
            with open(args.out, "w") as f:
                json.dump({"meta": meta, "checkpoints": results}, f, indent=1)
    meta["power_end"] = power_state()
    meta["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with open(args.out, "w") as f:
        json.dump({"meta": meta, "checkpoints": results}, f, indent=1)
    log(f"DONE -> {args.out}")


if __name__ == "__main__":
    main()
