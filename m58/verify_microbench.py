#!/usr/bin/env python3
"""M58 STEP 1 microbench (spec v3.1, P92): no model, synthetic bf16 arrays at the first pick's attention shape
(24 query / 4 KV heads, head dim 256). Per cell: per-query sliced calls (today's verifier pattern) vs ONE joint
call with the 4-D boolean step mask (the proposed path) vs joint with "causal" (reference). Records ms, BITWISE
equality per query position (uint16 view), and whether the fork's plan mirror predicts every mismatch.

Decision rule (spec): build only if (a) the mirror predicts EXACTLY the mismatching cells and (b) the boolean-mask
joint call is faster at >= 65536 keys.

  cd $STACK_REPO && .venv/bin/python $STACK_WORKDIR/m58/verify_microbench.py --out $STACK_WORKDIR/m58/verify_microbench.run1.json
"""
import argparse, json, os, statistics, subprocess, sys, time
import mlx.core as mx

HQ, HKV, D = 24, 4, 256
GQA = HQ // HKV
SCALE = D ** -0.5
GIB = 1024 ** 3
KMAX = 262144
THRESHOLD_SWEEP = [range(1018, 1031), range(8188, 8201), range(32764, 32777), range(65532, 65545)]
MAIN_KEYS = (8192, 65536, 131072, 262144)
MAIN_QL = (2, 3, 4, 5, 6)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def power():
    try:
        out = subprocess.run(["pmset", "-g", "ac"], capture_output=True, text=True, timeout=5).stdout
        bat = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5).stdout
        return {"ac": " ".join(out.split())[:160], "batt": " ".join(bat.split())[:160]}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:100]}


def timeit(fn, reps=5, warm=2):
    for _ in range(warm):
        mx.eval(fn())
    ts = []
    for _ in range(reps):
        t = time.perf_counter()
        mx.eval(fn())
        ts.append(time.perf_counter() - t)
    return {"min_ms": round(min(ts) * 1e3, 3), "med_ms": round(statistics.median(ts) * 1e3, 3), "reps": reps}


# --- the fork's plan mirror, copied verbatim from mlx_vlm/models/qwen3_5/language.py (fbe2775e) so this script
# has no fork import; the live check below asserts the copy matches the fork when PYTHONPATH exposes it.
def _device_arch_suffix():
    arch = (mx.device_info() or {}).get("architecture", "")
    return arch[-1] if arch else ""


def _blocks(seq_len, gqa_factor):
    devc = _device_arch_suffix(); n_simds = gqa_factor
    if devc == "s":
        blocks = 64
        if seq_len > 1024 and n_simds > 4:
            if seq_len <= 8192: blocks = 128
            elif seq_len <= 32768: blocks = 256
            elif seq_len <= 65536: blocks = 512
            else: blocks = 1024
        return blocks
    if devc == "d":
        blocks = 128
        if n_simds <= 2 and seq_len > 8192: blocks = 256
        elif n_simds >= 6:
            if 16384 <= seq_len < 65536: blocks = 512
            elif seq_len >= 65536: blocks = 1024
        return blocks
    return 64 if n_simds >= 4 else 32


def plan(seq_len, q_heads=HQ, kv_heads=HKV):
    devc = _device_arch_suffix()
    if (devc in {"d", "s"} and seq_len >= 1024) or (kv_heads < q_heads and seq_len >= 4096):
        return ("two_pass", _blocks(seq_len, q_heads // kv_heads))
    return ("one_pass", 0)


def predicted_mismatch_positions(qL, kL):
    """Rule 7: query i (keys = prefix+i+1) differs from the joint call (keys = kL) iff the plans differ."""
    pre = kL - qL
    return [i for i in range(qL) if plan(pre + i + 1) != plan(kL)]


def step_mask(qL, kL):
    pre = kL - qL
    return mx.arange(kL)[None, None, None, :] < (pre + mx.arange(qL) + 1)[None, None, :, None]


def bits(a):
    return a.view(mx.uint16) if a.dtype in (mx.bfloat16, mx.float16) else a.view(mx.uint32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--parts", default="A,B,C")
    ap.add_argument("--reps", type=int, default=5)
    a = ap.parse_args()
    parts = set(a.parts.split(","))
    sdpa = mx.fast.scaled_dot_product_attention
    mx.set_cache_limit(4 * GIB); mx.set_memory_limit(24 * GIB)
    res = {"mlx": mx.__version__, "device": mx.device_info(), "power_start": power(), "MLX_SDPA_BLOCKS": os.environ.get("MLX_SDPA_BLOCKS"),
           "shape": {"HQ": HQ, "HKV": HKV, "D": D}, "t0": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    log(json.dumps({k: res[k] for k in ("mlx", "device", "power_start", "MLX_SDPA_BLOCKS")}))
    try:
        import mlx_vlm.models.qwen3_5.language as L  # only if PYTHONPATH exposes the fork
        res["mirror_matches_fork"] = all(L._qwen3_5_sdpa_vector_plan(n, HQ, HKV) == plan(n) for n in
                                         [1, 512, 1023, 1024, 1025, 4096, 8192, 8193, 32768, 32769, 65536, 65537, 131072, 262144])
    except Exception as e:  # noqa: BLE001
        res["mirror_matches_fork"] = f"not checked: {type(e).__name__}"
    log("mirror_matches_fork", res["mirror_matches_fork"])

    def save():
        res["power_end"] = power(); res["t1"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with open(a.out, "w") as f:
            json.dump(res, f, indent=1)

    mx.random.seed(0)
    K = mx.random.normal((1, HKV, KMAX, D)).astype(mx.bfloat16)
    V = mx.random.normal((1, HKV, KMAX, D)).astype(mx.bfloat16)
    mx.eval(K, V)

    def q_for(qL, seed=1):
        mx.random.seed(seed + qL)
        q = mx.random.normal((1, HQ, qL, D)).astype(mx.bfloat16); mx.eval(q); return q

    def per_query(q, k, v, qL, kL):
        pre = kL - qL
        return mx.concatenate([sdpa(q[:, :, i:i + 1], k[:, :, :pre + i + 1], v[:, :, :pre + i + 1], scale=SCALE, mask=None)
                               for i in range(qL)], axis=2)

    def identity_cell(qL, kL):
        q = q_for(qL); k, v = K[:, :, :kL], V[:, :, :kL]
        m = step_mask(qL, kL)
        pq = per_query(q, k, v, qL, kL)
        jb = sdpa(q, k, v, scale=SCALE, mask=m)
        jc = sdpa(q, k, v, scale=SCALE, mask="causal")
        mx.eval(pq, jb, jc)
        eq_b = [bool(mx.all(bits(pq[:, :, i]) == bits(jb[:, :, i])).item()) for i in range(qL)]
        eq_c = [bool(mx.all(bits(pq[:, :, i]) == bits(jc[:, :, i])).item()) for i in range(qL)]
        finite = bool(mx.all(mx.isfinite(jb.astype(mx.float32))).item())
        pred = predicted_mismatch_positions(qL, kL)
        actual = [i for i, e in enumerate(eq_b) if not e]
        return {"qL": qL, "kL": kL, "plan_joint": plan(kL), "bool_identical": eq_b, "causal_identical": eq_c,
                "finite": finite, "predicted_mismatch": pred, "actual_mismatch": actual, "mirror_exact": pred == actual}

    if "A" in parts:   # identity + timing on the main grid
        rows = []
        for kL in MAIN_KEYS:
            for qL in MAIN_QL:
                row = identity_cell(qL, kL)
                q = q_for(qL); k, v = K[:, :, :kL], V[:, :, :kL]; m = step_mask(qL, kL)
                row["t_per_query"] = timeit(lambda: per_query(q, k, v, qL, kL), a.reps)
                row["t_joint_bool"] = timeit(lambda: sdpa(q, k, v, scale=SCALE, mask=m), a.reps)
                row["t_joint_causal"] = timeit(lambda: sdpa(q, k, v, scale=SCALE, mask="causal"), a.reps)
                row["t_single_query"] = timeit(lambda: sdpa(q[:, :, :1], k, v, scale=SCALE, mask=None), a.reps)
                rows.append(row); log("A", json.dumps(row)); mx.clear_cache()
        res["A_main_grid"] = rows; save()

    if "B" in parts:   # threshold sweep: identity only, rule-7 mirror must predict exactly
        rows = []
        for rng in THRESHOLD_SWEEP:
            for kL in rng:
                for qL in (2, 3, 4, 5):
                    row = identity_cell(qL, kL); rows.append(row)
                    if not row["mirror_exact"]:
                        log("B MIRROR MISS", json.dumps(row))
        exact = sum(r["mirror_exact"] for r in rows)
        res["B_threshold_sweep"] = {"rows": rows, "n": len(rows), "mirror_exact": exact}
        log("B", f"mirror exact on {exact}/{len(rows)} cells"); save(); mx.clear_cache()

    if "C" in parts:   # query-count cliff: does qL 6..9 leave the vector kernel (timing) and stay identical?
        rows = []
        for kL in (65536, 131072):
            for qL in (5, 6, 7, 8, 9):
                q = q_for(qL); k, v = K[:, :, :kL], V[:, :, :kL]; m = step_mask(qL, kL)
                row = {"qL": qL, "kL": kL, "t_joint_bool": timeit(lambda: sdpa(q, k, v, scale=SCALE, mask=m), a.reps),
                       "t_per_query": timeit(lambda: per_query(q, k, v, qL, kL), a.reps)}
                row.update({k_: v_ for k_, v_ in identity_cell(qL, kL).items() if k_ in ("bool_identical", "mirror_exact")})
                rows.append(row); log("C", json.dumps(row)); mx.clear_cache()
        res["C_query_cliff"] = rows; save()
    save(); log("DONE", a.out)


if __name__ == "__main__":
    main()
