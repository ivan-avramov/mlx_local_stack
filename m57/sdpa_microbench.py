"""M57 step-1 no-model SDPA microbench (first pick's attention shape). Synthetic arrays only."""
import argparse, json, os, statistics, subprocess, sys, time
import mlx.core as mx

HQ, HKV, D = 24, 4, 256
SCALE = D ** -0.5
GIB = 1024 ** 3
KMAX = 262144
SCRATCH_CAP = 14e9  # never build an unfused score tensor pair beyond this
sdpa = mx.fast.scaled_dot_product_attention


def log(*a):
    print(*a, flush=True)


def power():
    try:
        ac = subprocess.run(["pmset", "-g", "ac"], capture_output=True, text=True).stdout
        bt = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True).stdout
        w = [l.strip() for l in ac.splitlines() if "Wattage" in l or "Voltage" in l]
        b = [l.strip() for l in bt.splitlines() if "%" in l]
        return {"ac": w, "batt": b[0][:60] if b else None}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def timeit(fn, reps=5, warm=2):
    for _ in range(warm):
        mx.eval(fn())
    ts = []
    for _ in range(reps):
        t = time.perf_counter()
        mx.eval(fn())
        ts.append(time.perf_counter() - t)
    return {"min_ms": round(min(ts) * 1e3, 3), "med_ms": round(statistics.median(ts) * 1e3, 3), "reps": reps}


def attempt(fn, reps=5, warm=2):
    try:
        return timeit(fn, reps, warm)
    except Exception as e:  # noqa: BLE001
        return {"raised": type(e).__name__, "msg": str(e)[:300]}


def peak_of(fn):
    mx.eval(fn())  # compile kernels first
    mx.clear_cache()
    base = mx.get_active_memory()
    mx.reset_peak_memory()
    out = fn()
    mx.eval(out)
    peak = mx.get_peak_memory()
    del out
    mx.clear_cache()
    return round((peak - base) / 1e9, 3)


def auto_is_unfused(qL, mask):
    if qL <= 8:
        return qL * (HQ // HKV) > 32
    if qL >= 1024 and isinstance(mask, str):
        return False
    return True


def scratch_bytes(qL, kL, itemsize=2):
    return HQ * qL * kL * itemsize * 2


def causal_bool(qL, kL, lo=0, hi=None):
    hi = qL if hi is None else hi
    qi = mx.arange(lo, hi)[:, None] + (kL - qL)
    return mx.arange(kL)[None, :] <= qi


def ref_cpu_fp32(q, k, v, rows=128):
    """Independent reference: fp32, CPU stream, explicit boolean causal mask, query slices."""
    q32, k32, v32 = (a.astype(mx.float32) for a in (q, k, v))
    qL, kL = q.shape[2], k.shape[2]
    outs = []
    for i in range(0, qL, rows):
        j = min(i + rows, qL)
        m = causal_bool(qL, kL, i, j)
        o = sdpa(q32[:, :, i:j], k32, v32, scale=SCALE, mask=m, stream=mx.cpu)
        mx.eval(o)
        outs.append(o)
    return mx.concatenate(outs, axis=2)


def err(a, ref):
    a32 = a.astype(mx.float32)
    d = a32 - ref
    rms_ref = mx.sqrt(mx.mean(ref * ref)).item()
    return {"max_abs": round(mx.max(mx.abs(d)).item(), 6),
            "rel_rms": round(mx.sqrt(mx.mean(d * d)).item() / max(rms_ref, 1e-12), 6),
            "nan": bool(mx.any(mx.isnan(a32)).item())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--parts", default="A,A2,A3,A4,B,C,P")
    args = ap.parse_args()
    parts = set(args.parts.split(","))
    mx.set_cache_limit(4 * GIB)
    mx.set_memory_limit(44 * GIB)
    res = {"mlx": mx.__version__, "device": mx.metal.device_info(), "power_start": power(),
           "shape": {"HQ": HQ, "HKV": HKV, "D": D}, "t0": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    log(json.dumps({k: res[k] for k in ("mlx", "power_start")}))

    def save():
        res["power_end"] = power()
        with open(args.out, "w") as f:
            json.dump(res, f, indent=1)

    def mk(dtype, seed=0):
        mx.random.seed(seed)
        K = mx.random.normal((1, HKV, KMAX, D)).astype(dtype)
        V = mx.random.normal((1, HKV, KMAX, D)).astype(dtype)
        mx.eval(K, V)
        return K, V

    def mkq(qL, dtype, gain=1.0, seed=1):
        mx.random.seed(seed + qL)
        q = (mx.random.normal((1, HQ, qL, D)) * gain).astype(dtype)
        mx.eval(q)
        return q

    bf = mx.bfloat16
    K, V = mk(bf)

    if "A" in parts:
        rows = []
        for qL in (9, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096):
            q = mkq(qL, bf)
            for kL in (1024, 4096, 16384, 65536, 131072, 262144):
                if kL < qL:
                    continue
                k, v = K[:, :, :kL], V[:, :, :kL]
                reps = 3 if qL * kL >= 512 * 131072 else 5
                row = {"qL": qL, "kL": kL}
                if auto_is_unfused(qL, "causal") and scratch_bytes(qL, kL) > SCRATCH_CAP:
                    row["auto"] = {"skipped": "unfused scratch %.1f GB" % (scratch_bytes(qL, kL) / 1e9)}
                else:
                    row["auto"] = attempt(lambda: sdpa(q, k, v, scale=SCALE, mask="causal"), reps)
                row["forced"] = attempt(lambda: sdpa(q, k, v, scale=SCALE, mask="causal", force_fused=True), reps)
                rows.append(row)
                log("A", json.dumps(row))
                mx.clear_cache()
        res["A_crossover_bf16_causal"] = rows
        save()

    if "A2" in parts:
        K16, V16 = K.astype(mx.float16), V.astype(mx.float16)
        mx.eval(K16, V16)
        rows = []
        for qL, kL in ((512, 131072), (1024, 131072)):
            q = mkq(qL, mx.float16)
            k, v = K16[:, :, :kL], V16[:, :, :kL]
            row = {"qL": qL, "kL": kL,
                   "auto": attempt(lambda: sdpa(q, k, v, scale=SCALE, mask="causal"), 3),
                   "forced": attempt(lambda: sdpa(q, k, v, scale=SCALE, mask="causal", force_fused=True), 3)}
            rows.append(row)
            log("A2", json.dumps(row))
        res["A2_fp16_tieback"] = rows
        del K16, V16
        mx.clear_cache()
        save()

    if "A3" in parts:
        rows = []
        qL = 512
        q = mkq(qL, bf)
        for kL in (16384, 131072):
            k, v = K[:, :, :kL], V[:, :, :kL]
            mb = causal_bool(qL, kL)
            ma = mx.where(mb, mx.array(0.0, dtype=bf), mx.array(float("-inf"), dtype=bf))
            mx.eval(mb, ma)
            for name, m in (("none", None), ("causal", "causal"), ("bool_array", mb), ("additive_array", ma)):
                row = {"qL": qL, "kL": kL, "mask": name,
                       "auto": attempt(lambda: sdpa(q, k, v, scale=SCALE, mask=m), 3),
                       "forced": attempt(lambda: sdpa(q, k, v, scale=SCALE, mask=m, force_fused=True), 3)}
                rows.append(row)
                log("A3", json.dumps(row))
                mx.clear_cache()
        res["A3_masks_bf16"] = rows
        save()

    if "A4" in parts:
        rows = []
        # known positive: a tensor the size of one bf16 score matrix at 512 x 131072
        kp = peak_of(lambda: mx.zeros((HQ, 512, 131072), dtype=bf) + mx.array(1.0, dtype=bf))
        res["A4_known_positive_gb"] = {"measured": kp, "expected": round(HQ * 512 * 131072 * 2 / 1e9, 3)}
        log("A4 known-positive", json.dumps(res["A4_known_positive_gb"]))
        q = mkq(512, bf)
        for kL in (65536, 131072, 262144):
            k, v = K[:, :, :kL], V[:, :, :kL]
            row = {"qL": 512, "kL": kL, "one_score_tensor_gb": round(HQ * 512 * kL * 2 / 1e9, 3),
                   "auto_transient_gb": peak_of(lambda: sdpa(q, k, v, scale=SCALE, mask="causal")),
                   "forced_transient_gb": peak_of(lambda: sdpa(q, k, v, scale=SCALE, mask="causal", force_fused=True))}
            rows.append(row)
            log("A4", json.dumps(row))
        q = mkq(1024, bf)
        k, v = K[:, :, :131072], V[:, :, :131072]
        row = {"qL": 1024, "kL": 131072,
               "auto_transient_gb": peak_of(lambda: sdpa(q, k, v, scale=SCALE, mask="causal"))}
        rows.append(row)
        log("A4", json.dumps(row))
        res["A4_transient_peak_bf16"] = rows
        save()

    if "B" in parts:
        rows = []
        kL = 4096
        k, v = K[:, :, :kL], V[:, :, :kL]
        for qL in range(1, 11):
            q = mkq(qL, bf)
            m = "causal" if qL > 1 else None
            row = {"qL": qL, "kL": kL,
                   "auto": attempt(lambda: sdpa(q, k, v, scale=SCALE, mask=m), 3),
                   "forced": attempt(lambda: sdpa(q, k, v, scale=SCALE, mask=m, force_fused=True), 3)}
            rows.append(row)
            log("B", json.dumps(row))
        res["B_raise_boundary_bf16"] = rows
        save()

    if "C" in parts:
        rows = []
        for kL in (65536, 131072, 262144):
            k, v = K[:, :, :kL], V[:, :, :kL]
            floor = attempt(lambda: mx.sum(k.astype(mx.float32)) + mx.sum(v.astype(mx.float32)), 5)
            q1 = mkq(1, bf)
            gemv = attempt(lambda: mx.matmul(k, q1[:, :HKV].swapaxes(-1, -2)), 5)
            rows.append({"kL": kL, "read_floor_sum": floor, "gemv_keys_only": gemv,
                         "kv_bytes_gb": round(2 * HKV * kL * D * 2 / 1e9, 3)})
            log("C", json.dumps(rows[-1]))
            for qL in (1, 2, 3, 4, 5):
                q = mkq(qL, bf)
                m = "causal" if qL > 1 else None
                row = {"kL": kL, "qL": qL,
                       "joint": attempt(lambda: sdpa(q, k, v, scale=SCALE, mask=m), 5)}
                if qL > 1:
                    mb = causal_bool(qL, kL)
                    mx.eval(mb)
                    row["joint_bool_mask"] = attempt(lambda: sdpa(q, k, v, scale=SCALE, mask=mb), 5)

                    def per_query():
                        pre = kL - qL
                        return mx.concatenate(
                            [sdpa(q[:, :, i:i + 1], k[:, :, :pre + i + 1], v[:, :, :pre + i + 1],
                                  scale=SCALE, mask=None) for i in range(qL)], axis=2)
                    row["per_query"] = attempt(per_query, 5)
                rows.append(row)
                log("C", json.dumps(row))
        res["C_vector_kernel_bf16"] = rows
        save()
        rows = []
        kL = 262144
        k, v = K[:, :, :kL], V[:, :, :kL]
        for blocks in (None, 256, 512, 2048, 4096, 8192):
            if blocks is None:
                os.environ.pop("MLX_SDPA_BLOCKS", None)
            else:
                os.environ["MLX_SDPA_BLOCKS"] = str(blocks)
            for qL in (1, 3):
                q = mkq(qL, bf)
                m = "causal" if qL > 1 else None
                row = {"kL": kL, "qL": qL, "MLX_SDPA_BLOCKS": blocks,
                       "joint": attempt(lambda: sdpa(q, k, v, scale=SCALE, mask=m), 5)}
                rows.append(row)
                log("C-blocks", json.dumps(row))
        os.environ.pop("MLX_SDPA_BLOCKS", None)
        res["C_blocks_sweep_bf16"] = rows
        save()

    if "P" in parts:
        rows = []
        cells = [(512, 131072, 1.0), (512, 131072, 4.0), (512, 262144, 1.0), (64, 131072, 1.0),
                 (9, 131072, 1.0), (512, 4096, 1.0)]
        for qL, kL, gain in cells:
            q = mkq(qL, bf, gain)
            k, v = K[:, :, :kL], V[:, :, :kL]
            t = time.perf_counter()
            ref = ref_cpu_fp32(q, k, v)
            mx.eval(ref)
            row = {"qL": qL, "kL": kL, "gain": gain, "ref_s": round(time.perf_counter() - t, 1)}
            if scratch_bytes(qL, kL) <= SCRATCH_CAP:
                a = sdpa(q, k, v, scale=SCALE, mask="causal")
                mx.eval(a)
                row["auto_vs_ref"] = err(a, ref)
            f = sdpa(q, k, v, scale=SCALE, mask="causal", force_fused=True)
            mx.eval(f)
            row["forced_vs_ref"] = err(f, ref)
            if "auto_vs_ref" in row:
                row["forced_vs_auto"] = err(f, a.astype(mx.float32))
            rows.append(row)
            log("P", json.dumps(row))
            mx.clear_cache()
        for qL, gain in ((3, 1.0), (3, 4.0), (5, 1.0)):
            kL = 131072
            q = mkq(qL, bf, gain)
            k, v = K[:, :, :kL], V[:, :, :kL]
            ref = ref_cpu_fp32(q, k, v)
            joint = sdpa(q, k, v, scale=SCALE, mask="causal")
            pre = kL - qL
            perq = mx.concatenate([sdpa(q[:, :, i:i + 1], k[:, :, :pre + i + 1], v[:, :, :pre + i + 1],
                                        scale=SCALE, mask=None) for i in range(qL)], axis=2)
            mx.eval(ref, joint, perq)
            row = {"qL": qL, "kL": kL, "gain": gain, "joint_vs_ref": err(joint, ref),
                   "per_query_vs_ref": err(perq, ref), "joint_vs_per_query": err(joint, perq.astype(mx.float32))}
            rows.append(row)
            log("P", json.dumps(row))
        res["P_parity_bf16"] = rows
        save()
    save()
    log("DONE", args.out)


if __name__ == "__main__":
    sys.exit(main())
