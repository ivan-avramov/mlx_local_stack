#!/usr/bin/env python3
"""M72 1.2 tuning step 1b (S20-P13): where the matrix-unit verify kernel's time goes, by ablation. Diagnostic only.

Builds variants of ``dev/m72_mma_verify.py``'s pass-1 kernel from its own generated source (captured at build time) and
times them at the pick's attention shapes, TQ4 and native16, k = 1 / 3 / 5, T = 131,072 / 260,096:
  full       the shipped prototype (pass 1 only)
  load_only  tile loads + unpack + barriers; no S / softmax / P.V (outputs written from the tile so nothing is elided)
  math_only  S / softmax / P.V on a tile filled once (no per-tile global reads or unpack); barriers kept
  no_unpack  TQ4 only: global reads kept, the codebook lookup replaced by a plain cast of each index value
Outputs of the ablated variants are meaningless; only times are recorded. Pass 2 and the rotation are excluded (they are
the production kernels, timed elsewhere).

Run (quiet box): PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/m72_mma_diag.py --out <dir>/diag.json
Report: python benchmark/spikes/m72_mma_diag.py --report <dir>/diag.json
"""

import argparse
import json
import sys
import time
from pathlib import Path

DIAG_T = (131072, 260096)
DIAG_K = (1, 3, 5)
VARIANTS = ("full", "load_only", "math_only", "no_unpack")


def capture_source(mv, arm, rows, k):
    import mlx.core as mx

    seen = {}
    real = mx.fast.metal_kernel

    def spy(**kw):
        seen.update(kw)
        return real(**kw)

    mx.fast.metal_kernel = spy
    try:
        mv.mma_kernel.cache_clear()
        mv.mma_kernel(arm, rows, k)
    finally:
        mx.fast.metal_kernel = real
        mv.mma_kernel.cache_clear()
    return seen


def variant_source(src, arm, variant):
    """Edit the generated source; raises if an anchor is missing (the prototype changed)."""
    if variant == "full":
        return src
    loop_open = "        for (uint ts = t0; ts < t1; ts += Tt) {"
    assert loop_open in src
    head, body = src.split(loop_open, 1)
    loop_body, tail = body.split("\n        }\n        if (row_ok) {", 1)
    tail = "\n        if (row_ok) {" + tail
    first_barrier = "            threadgroup_barrier(mem_flags::mem_threadgroup);"
    parts = loop_body.split(first_barrier)
    assert len(parts) == 3, len(parts)  # [pre, loader, math]
    pre, loader, math = parts
    if variant == "load_only":
        sink = ("            if (sg == 0 && lane == 0) m_run = max(m_run, static_cast<float>(Ks[ts % Tt]) + "
                "static_cast<float>(Vs[(ts + 1) % Tt]) + kfac[0] + vfac[0]);\n")
        new_body = pre + first_barrier + loader + first_barrier + "\n" + sink
        return head + loop_open + new_body + "\n        }" + tail
    if variant == "math_only":
        new_head = head + loop_open.replace("for (uint ts = t0; ts < t1; ts += Tt) {", "{ uint ts = t0;") + \
            pre + first_barrier + loader + first_barrier + "\n        }\n"
        return new_head + loop_open + first_barrier + math + "\n        }" + tail
    if variant == "no_unpack":
        if arm != "tq4":
            return None
        out = loader.replace("cbk[(kw >> (4 * n)) & 15u]", "static_cast<QT>((kw >> (4 * n)) & 15u)")
        out = out.replace("cbv[(vw >> (4 * n)) & 15u]", "static_cast<PT>((vw >> (4 * n)) & 15u)")
        assert out != loader
        return head + loop_open + pre + first_barrier + out + first_barrier + math + "\n        }" + tail
    raise ValueError(variant)


def measure(args):
    import mlx.core as mx

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import m72_gates
    import m72_tq4_probe as P

    mx.set_cache_limit(4 << 30)
    mx.set_memory_limit(60 << 30)
    p0 = P.power_state()
    if not P.power_ok(p0):
        sys.exit(3)
    one = mx.ones((16,))
    mx.eval(one)
    g0 = {"device_utilization_pct": m72_gates.gpu_utilization(),
          "tiny_op_floor_ms": m72_gates.tiny_op_floor_ms(lambda: (mx.eval(one + 1), mx.synchronize()))}
    if not m72_gates.gpu_idle_ok(g0):
        P.log(f"REFUSED: GPU not idle {g0}")
        sys.exit(5)
    mv = P.fork_mma_module()
    meta = {"probe": "m72_mma_diag", "mlx": mx.__version__, "device": mx.device_info(), "fork": P.fork_sha(),
            "power_start": p0, "gpu_idle_start": g0, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    mx.random.seed(72)
    tq = P.TurboQuantKVCache(bits=4, max_kv_size=P.CAP, prealloc_tokens=P.CAP)
    K = mx.zeros((1, P.NKV, P.CAP, P.D), dtype=P.DT)
    V = mx.zeros((1, P.NKV, P.CAP, P.D), dtype=P.DT)
    mx.eval(K, V)
    rows_out, off = [], 0
    while off < DIAG_T[-1]:
        kc = mx.random.normal((1, P.NKV, P.CHUNK, P.D)).astype(P.DT)
        vc = mx.random.normal((1, P.NKV, P.CHUNK, P.D)).astype(P.DT)
        tq.update_and_fetch(kc, vc)
        K[:, :, off:off + P.CHUNK, :] = kc
        V[:, :, off:off + P.CHUNK, :] = vc
        mx.eval(tq.keys, tq.values, K, V)
        off += P.CHUNK
        if off not in DIAG_T:
            continue
        T = off
        for k in DIAG_K:
            q = mx.random.normal((1, P.NQ, k, P.D)).astype(P.DT)
            lens = [T - k + 1 + j for j in range(k)]
            n_kv, R = P.NKV, P.NQ // P.NKV
            rows = R * k
            nb, tpb = mv.plan_blocks(T)
            ns = (rows + 7) // 8
            lens_a = mx.array(lens, dtype=mx.int32)
            grouped = (q * P.SCALE).reshape(1, n_kv, R, k, P.D)
            q_tq = tq.key_codec.prepare_queries(grouped).reshape(n_kv * rows, P.D)
            q_16 = q.reshape(n_kv * rows, P.D)
            arms = {
                "tq4": [q_tq, lens_a, tq.keys.norms, tq.keys.indices, tq.key_codec.codebook, tq.values.norms,
                        tq.values.indices, tq.value_codec.codebook],
                "native16": [q_16, lens_a, mx.array([P.SCALE], dtype=mx.float32), K, V],
            }
            for arm, inputs in arms.items():
                spec = capture_source(mv, arm, rows, k)
                template = [("Dim", P.D), ("Tt", mv.TILE_TOKENS), ("TPB", tpb), ("Blocks", nb), ("Shift", 0)]
                if arm == "tq4":
                    template.append(("PW", int(tq.keys.indices.shape[-1])))
                for variant in VARIANTS:
                    src = variant_source(spec["source"], arm, variant)
                    if src is None:
                        continue
                    kern = mx.fast.metal_kernel(name=f"{spec['name']}_{variant}", input_names=spec["input_names"],
                                                output_names=spec["output_names"], source=src)
                    call = lambda kern=kern, inputs=inputs, template=template: kern(
                        inputs=inputs, template=template, grid=(ns * 32 * nb, n_kv, 1), threadgroup=(ns * 32, 1, 1),
                        output_shapes=[(n_kv * rows * nb, P.D), (n_kv * rows * nb,), (n_kv * rows * nb,)],
                        output_dtypes=[mx.float32] * 3)
                    r = P.timeit(call)
                    rows_out.append({"T": T, "k": k, "arm": arm, "variant": variant, "blocks": nb, "time": r})
                    P.log(f"T={T} k={k} {arm} {variant}: {r['median_ms']:.3f} ms")
            mx.clear_cache()
    Path(args.out).write_text(json.dumps({"meta": meta, "rows": rows_out}, indent=1))
    P.log(f"DONE -> {args.out}")


def report(path):
    d = json.loads(Path(path).read_text())
    t = {(r["T"], r["k"], r["arm"], r["variant"]): r["time"]["median_ms"] for r in d["rows"]}
    m = d["meta"]
    print("# M72 1.2 tuning step 1b — matrix-unit verify pass-1 ablation (GENERATED by "
          "`benchmark/spikes/m72_mma_diag.py --report`; never hand-edit)\n")
    print(f"MLX {m['mlx']}, `{m['device']['architecture']}`; fork `{m['fork'].get('head', '?')[:8]}`; pass 1 only, "
          "default block plan; medians (ms). load_only = tile reads + unpack + barriers; math_only = S / softmax / P.V on a "
          "resident tile; no_unpack = TQ4 reads without the codebook lookup.\n")
    print("| T | k | arm | full | load_only | math_only | no_unpack | load / full | math / full |")
    print("|---|---|---|---|---|---|---|---|---|")
    for T in DIAG_T:
        for k in DIAG_K:
            for arm in ("tq4", "native16"):
                f = t.get((T, k, arm, "full"))
                if f is None:
                    continue
                lo, ma, nu = (t.get((T, k, arm, v)) for v in ("load_only", "math_only", "no_unpack"))
                print(f"| {T} | {k} | {arm} | {f:.3f} | {lo:.3f} | {ma:.3f} | {nu if nu is None else f'{nu:.3f}'} | "
                      f"{lo / f:.2f} | {ma / f:.2f} |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--report")
    a = ap.parse_args()
    if a.report:
        report(a.report)
    elif a.out:
        measure(a)
    else:
        ap.error("--out or --report")


if __name__ == "__main__":
    main()
