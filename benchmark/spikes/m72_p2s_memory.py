#!/usr/bin/env python3
"""M72 P2' stage 1 memory spike (C314; operator: measure the process's actual allocation spikes, separately from the perf run).

Question: does a prefill path that dequantizes one layer's TQ4 K / V into a bf16 scratch (~1.07 GB at 256K) keep the process's
peak at about one scratch above the caches when a whole 16-layer chunk forward runs as MLX runs a model — one lazy graph, each
layer's queries depending on the previous layer's output — or can the scheduler hold several layers' scratches at once (up to
the whole KV cache, which would erase TQ4's memory saving)?

Instruments (both per process, never system memfree):
  os    the kernel's physical-footprint ledger (proc_pid_rusage RUSAGE_INFO_V4: ri_interval_max_phys_footprint after
        proc_reset_footprint_interval) — a per-page high-water of what the OS charges this process, net of buffer reuse;
  mlx   MLX's allocator high-water (mx.get_peak_memory, updated at every allocation; reset after setup) and active bytes.
Each scenario runs in a fresh process: build the caches, clear MLX's buffer cache, reset both peaks, run, read the peaks.

Scenarios: noop (control); kp_one (known positive: one layer's scratch); kp_whole (known positive: every layer's scratch alive at
once); fwd_lazy (16 chained layers, one eval — as a model forward); fwd_eval (eval after each layer); fwd_dep (one eval, each
layer's dequant inputs tied to its queries with mx.depends). Implementations of the per-layer prefill: standin (a shape-faithful
stand-in: one Metal kernel writing the two bf16 scratch arrays from the cache state, then MLX's fused SDPA and the inverse
rotation — the same allocations and lifetimes as stage 1, not its values), p1 (the probe's generic-op rotated dequantize), p2s
(the stage-1 kernel, `dev/m72_scratch_prefill.py`, once it exists).

Run: PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/m72_p2s_memory.py --all --impl standin --out <dir>/memory-standin.json
"""

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path

NQ, NKV, D, CHUNK = 24, 4, 256, 512
SCALE = 1.0 / 16.0
SCENARIOS = ("noop", "kp_one", "kp_whole", "fwd_lazy", "fwd_eval", "fwd_dep", "fwd_resident", "grow")

_F = [
    "ri_user_time",
    "ri_system_time",
    "ri_pkg_idle_wkups",
    "ri_interrupt_wkups",
    "ri_pageins",
    "ri_wired_size",
    "ri_resident_size",
    "ri_phys_footprint",
    "ri_proc_start_abstime",
    "ri_proc_exit_abstime",
    "ri_child_user_time",
    "ri_child_system_time",
    "ri_child_pkg_idle_wkups",
    "ri_child_interrupt_wkups",
    "ri_child_pageins",
    "ri_child_elapsed_abstime",
    "ri_diskio_bytesread",
    "ri_diskio_byteswritten",
    "ri_cpu_time_qos_default",
    "ri_cpu_time_qos_maintenance",
    "ri_cpu_time_qos_background",
    "ri_cpu_time_qos_utility",
    "ri_cpu_time_qos_legacy",
    "ri_cpu_time_qos_user_initiated",
    "ri_cpu_time_qos_user_interactive",
    "ri_billed_system_time",
    "ri_serviced_system_time",
    "ri_logical_writes",
    "ri_lifetime_max_phys_footprint",
    "ri_instructions",
    "ri_cycles",
    "ri_billed_energy",
    "ri_serviced_energy",
    "ri_interval_max_phys_footprint",
    "ri_runnable_time",
]


class _RU4(ctypes.Structure):
    _fields_ = [("ri_uuid", ctypes.c_uint8 * 16)] + [(n, ctypes.c_uint64) for n in _F]


_LIB = ctypes.CDLL("/usr/lib/libproc.dylib")
_LIB.proc_reset_footprint_interval.argtypes = [ctypes.c_int]


def footprint():
    r = _RU4()
    if _LIB.proc_pid_rusage(os.getpid(), 4, ctypes.byref(r)) != 0:
        raise OSError("proc_pid_rusage failed")
    return {
        "current": r.ri_phys_footprint,
        "interval_max": r.ri_interval_max_phys_footprint,
        "lifetime_max": r.ri_lifetime_max_phys_footprint,
    }


def standin_kernel():
    import mlx.core as mx

    src = """
        uint gid = thread_position_in_grid.x;            // one thread per (head, token, 8 dims)
        uint d8 = gid % 32, rest = gid / 32;
        uint t = rest % T, h = rest / T;
        if (h >= NKV) return;
        float kn = static_cast<float>(knorms[h * key_norms_shape_cap + t]);
        float vn = static_cast<float>(vnorms[h * key_norms_shape_cap + t]);
        uint kw = kidx[(h * key_norms_shape_cap + t) * 32 + d8];
        uint vw = vidx[(h * key_norms_shape_cap + t) * 32 + d8];
        for (int n = 0; n < 8; n++) {
            kout[((ulong)h * S + t) * 256 + d8 * 8 + n] = static_cast<half>(kn * float((kw >> (4 * n)) & 15u));
            vout[((ulong)h * S + t) * 256 + d8 * 8 + n] = static_cast<half>(vn * float((vw >> (4 * n)) & 15u));
        }
    """
    return mx.fast.metal_kernel(
        name="m72_mem_standin",
        input_names=["knorms", "kidx", "vnorms", "vidx"],
        output_names=["kout", "vout"],
        source=src,
    )


def make_impl(name, scratch_size="cap"):
    """(dequant, prefill). dequant returns (K, V) whose token axis is T (scratch_size "t") or the state's capacity ("cap",
    only [0, T) written — stage 1's design); prefill slices to T."""
    import mlx.core as mx

    if name == "standin":
        kern = standin_kernel()

        def dequant(cache, T, dep=None):
            ks, vs = cache.keys, cache.values
            ins = [ks.norms, ks.indices, vs.norms, vs.indices]
            if dep is not None:
                ins = mx.depends(ins, dep)
            S = T if scratch_size == "t" else ks.norms.shape[2]
            k, v = kern(
                inputs=ins,
                template=[("T", T), ("S", S), ("NKV", NKV), ("key_norms_shape_cap", ks.norms.shape[2])],
                grid=(NKV * T * 32, 1, 1),
                threadgroup=(256, 1, 1),
                output_shapes=[(1, NKV, S, D), (1, NKV, S, D)],
                output_dtypes=[mx.float16, mx.float16],
            )
            return k, v

    elif name == "p1":
        from mlx_vlm import turboquant as tq_mod

        def dequant(cache, T, dep=None):
            out = []
            for st, codec in ((cache.keys, cache.key_codec), (cache.values, cache.value_codec)):
                idx_src, nrm = st.indices[:, :, :T], st.norms[:, :, :T]
                if dep is not None:
                    idx_src, nrm = mx.depends([idx_src, nrm], dep)
                idx = tq_mod._unpack_lowbit(idx_src, int(codec.bits), D).astype(mx.int32)
                out.append((mx.take(codec.codebook, idx, axis=0) * nrm[..., None]).astype(mx.float16))
            return out

    elif name == "p2s":
        dev = Path(__import__("mlx_vlm").__file__).resolve().parents[1] / "dev"
        sys.path.insert(0, str(dev))
        import m72_scratch_prefill as m

        from types import SimpleNamespace

        from mlx_vlm import turboquant as tq_mod

        def dequant(cache, T, dep=None):
            if (
                dep is not None
            ):  # the state arrays the kernel reads, tied to `dep` (a proxy; the real state is untouched)
                ks, vs = cache.keys, cache.values
                kn, ki, vn, vi = mx.depends([ks.norms, ks.indices, vs.norms, vs.indices], dep)
                cache = SimpleNamespace(
                    keys=tq_mod.TurboQuantMSEState(kn, ki),
                    values=tq_mod.TurboQuantMSEState(vn, vi),
                    key_codec=cache.key_codec,
                    value_codec=cache.value_codec,
                    offset=cache.offset,
                )
            return m.dequant_rotated(cache, T)  # cap-sized, fp16 (spec v1.1)

    else:
        raise ValueError(name)

    def prefill(cache, q, T, dep=None, kv=None):
        k, v = kv if kv is not None else dequant(cache, T, dep)
        if k.shape[2] != T:
            k, v = k[:, :, :T], v[:, :, :T]
        qr = cache.key_codec.prepare_queries(q).astype(k.dtype)
        o = mx.fast.scaled_dot_product_attention(qr, k, v, scale=SCALE, mask="causal", force_fused=True)
        return cache.value_codec._rotate_inverse(o.astype(mx.float32)).astype(mx.bfloat16)

    return dequant, prefill


def run_scenario(args):
    import mlx.core as mx
    from mlx_vlm.turboquant import TurboQuantKVCache

    mx.set_cache_limit(64 << 30)
    T, L = args.t, args.layers
    mx.random.seed(7)
    caches = []
    for _ in range(L):
        c = TurboQuantKVCache(bits=4, max_kv_size=T, prealloc_tokens=T)
        for off in range(0, T, 4096):
            n = min(4096, T - off)
            kv = mx.random.normal((1, NKV, n, D)).astype(mx.bfloat16)
            c.update_and_fetch(kv, kv)
            mx.eval(c.keys, c.values)
        caches.append(c)
    qs = [mx.random.normal((1, NQ, CHUNK, D)).astype(mx.bfloat16) for _ in range(L)]
    mx.eval(qs)
    dequant, prefill = make_impl(args.impl, args.scratch)
    resident = None
    if args.scenario == "fwd_resident":  # SDPA-only baseline: every layer's scratch made resident before the reset
        resident = []
        for c in caches:
            k, v = dequant(c, T)
            resident.append((mx.contiguous(k[:, :, :T]), mx.contiguous(v[:, :, :T])))
            mx.eval(resident[-1])
    grow_caches = None
    if args.scenario == "grow":  # chunked prefill from the first chunk to T; caches preallocated by their first append
        grow_caches = []
        for _ in range(L):
            c = TurboQuantKVCache(bits=4, max_kv_size=T, prealloc_tokens=T)
            kv = mx.random.normal((1, NKV, CHUNK, D)).astype(mx.bfloat16)
            c.update_and_fetch(kv, kv)
            mx.eval(c.keys, c.values)
            grow_caches.append(c)
        del caches[:]
    mx.synchronize()
    mx.clear_cache()
    time.sleep(1.0)
    f0 = footprint()
    _LIB.proc_reset_footprint_interval(os.getpid())
    mx.reset_peak_memory()
    a0 = mx.get_active_memory()
    sc = args.scenario
    if sc == "kp_one":
        mx.eval(dequant(caches[0], T))
    elif sc == "kp_whole":
        allkv = [dequant(c, T) for c in caches]
        mx.eval(allkv)
        del allkv
    elif sc == "fwd_resident":
        h = mx.zeros((1, NQ, CHUNK, D), dtype=mx.bfloat16)
        for i, c in enumerate(caches):
            q = qs[i] * (1 + 0 * mx.mean(h.astype(mx.float32))).astype(mx.bfloat16)
            h = prefill(c, q, T, kv=resident[i])
            mx.eval(h)
    elif sc == "grow":
        h = mx.zeros((1, NQ, CHUNK, D), dtype=mx.bfloat16)
        n_chunks = T // CHUNK
        for j in range(1, n_chunks):  # chunk 0 was appended before the reset
            Tj = (j + 1) * CHUNK
            for i, c in enumerate(grow_caches):
                kv = mx.random.normal((1, NKV, CHUNK, D)).astype(mx.bfloat16)
                c.update_and_fetch(kv, kv)
                if j % args.grow_stride == 0 or j == n_chunks - 1:
                    q = qs[i] * (1 + 0 * mx.mean(h.astype(mx.float32))).astype(mx.bfloat16)
                    h = prefill(c, q, Tj)
                mx.eval(h, c.keys, c.values)
    elif sc in ("fwd_lazy", "fwd_eval", "fwd_dep"):
        h = mx.zeros((1, NQ, CHUNK, D), dtype=mx.bfloat16)
        for i, c in enumerate(caches):
            q = qs[i] * (1 + 0 * mx.mean(h.astype(mx.float32))).astype(mx.bfloat16)  # real data dependency on layer i-1
            h = prefill(c, q, T, dep=q if sc == "fwd_dep" else None)
            if sc == "fwd_eval":
                mx.eval(h)
        mx.eval(h)
    mx.synchronize()
    f1 = footprint()
    scratch = 2 * NKV * T * D * 2
    res = {
        "scenario": sc,
        "impl": args.impl,
        "T": T,
        "layers": L,
        "scratch_GB": scratch / 1e9,
        "scratch_size": args.scratch,
        "grow_stride": args.grow_stride if sc == "grow" else None,
        "caches_GB": sum(
            c.keys.norms.nbytes + c.keys.indices.nbytes + c.values.norms.nbytes + c.values.indices.nbytes
            for c in (grow_caches or caches)
        )
        / 1e9,
        "os_footprint_at_reset_GB": f0["current"] / 1e9,
        "os_interval_peak_GB": f1["interval_max"] / 1e9,
        "os_peak_delta_GB": (f1["interval_max"] - f0["current"]) / 1e9,
        "mlx_peak_delta_GB": (mx.get_peak_memory() - a0) / 1e9,
        "mlx_active_before_GB": a0 / 1e9,
    }
    res["os_peak_delta_scratches"] = res["os_peak_delta_GB"] / res["scratch_GB"]
    res["mlx_peak_delta_scratches"] = res["mlx_peak_delta_GB"] / res["scratch_GB"]
    print(json.dumps(res), flush=True)


def run_all(args):
    rows = []
    for sc in args.scenarios:
        cmd = [
            sys.executable,
            __file__,
            "--scenario",
            sc,
            "--impl",
            args.impl,
            "--t",
            str(args.t),
            "--layers",
            str(args.layers),
            "--scratch",
            args.scratch,
            "--grow-stride",
            str(args.grow_stride),
        ]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if p.returncode != 0:
            print(f"{sc}: FAILED rc={p.returncode}\n{p.stderr[-2000:]}", flush=True)
            sys.exit(1)
        r = json.loads(p.stdout.strip().splitlines()[-1])
        rows.append(r)
        print(
            f"{sc:12s} {args.impl:8s} {args.scratch:3s} os peak +{r['os_peak_delta_GB']:7.3f} GB ({r['os_peak_delta_scratches']:5.2f} scratches)"
            f"   mlx peak +{r['mlx_peak_delta_GB']:7.3f} GB ({r['mlx_peak_delta_scratches']:5.2f})",
            flush=True,
        )
    meta = {
        "spike": "m72_p2s_memory",
        "impl": args.impl,
        "scratch_size": args.scratch,
        "grow_stride": args.grow_stride,
        "T": args.t,
        "layers": args.layers,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    if args.out:
        Path(args.out).write_text(json.dumps({"meta": meta, "rows": rows}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--scenario", choices=SCENARIOS)
    ap.add_argument("--scenarios", nargs="+", default=list(SCENARIOS))
    ap.add_argument("--impl", choices=("standin", "p1", "p2s"), default="standin")
    ap.add_argument("--t", type=int, default=262144)
    ap.add_argument("--layers", type=int, default=16)
    ap.add_argument("--scratch", choices=("t", "cap"), default="cap")
    ap.add_argument(
        "--grow-stride", type=int, default=1, help="grow: run the prefill every Nth chunk (appends every chunk)"
    )
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.all:
        run_all(a)
    elif a.scenario:
        run_scenario(a)
    else:
        ap.error("--all or --scenario")


if __name__ == "__main__":
    main()
