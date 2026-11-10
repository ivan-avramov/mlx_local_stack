#!/usr/bin/env python3
"""M72 1.2 tuning step 1 (S20-P13): block-plan sweep of the matrix-unit verify kernel, no kernel change.

Question: is the kernel (``dev/m72_mma_verify.py``, 128 token blocks per KV head by default) short of threadgroups
in flight? Varies only ``block_tokens`` (tokens per block -> Blocks = ceil(T / block_tokens)) at the pick's attention
shapes, through the probe's own timing, gates and module loader, against native16 SDPA / joint on the same full-cap
buffers. Each setting's output is compared with the default plan's (block split changes only fp32 summation order).

Run (two passes, opposite setting order, 600 s idle between; quiet box):
  PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/m72_mma_sweep.py --out <dir>/sweep-1.json --order forward
  PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/m72_mma_sweep.py --out <dir>/sweep-2.json --order reverse
Report (generated; never hand-edit):
  python benchmark/spikes/m72_mma_sweep.py --report <dir> > benchmark/results/m72/SWEEP.md
"""

import argparse
import json
import sys
import time
from pathlib import Path

SWEEP_T = (131072, 260096)
SWEEP_K = (1, 3, 5)
BLOCK_TOKENS = (None, 1024, 512, 256, 128, 64, 32)  # None = the kernel's default plan


def measure(args):
    import mlx.core as mx

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import m72_gates
    import m72_tq4_probe as P

    mx.set_cache_limit(4 << 30)
    mx.set_memory_limit(60 << 30)
    p0 = P.power_state()
    if not P.power_ok(p0):
        P.log(f"REFUSED: power state {p0}")
        sys.exit(3)
    one = mx.ones((16,))
    mx.eval(one)
    g0 = {
        "device_utilization_pct": m72_gates.gpu_utilization(),
        "tiny_op_floor_ms": m72_gates.tiny_op_floor_ms(lambda: (mx.eval(one + 1), mx.synchronize())),
    }
    if not m72_gates.gpu_idle_ok(g0):
        P.log(f"REFUSED: GPU not idle {g0}")
        sys.exit(5)
    mv = P.fork_mma_module()
    if not mv.fragment_mapping_ok():
        P.log("REFUSED: fragment mapping")
        sys.exit(6)
    order = list(BLOCK_TOKENS) if args.order == "forward" else list(reversed(BLOCK_TOKENS))
    meta = {
        "probe": "m72_mma_sweep",
        "mlx": mx.__version__,
        "device": mx.device_info(),
        "fork": P.fork_sha(),
        "power_start": p0,
        "gpu_idle_start": g0,
        "order": args.order,
        "block_tokens_order": order,
        "tile_tokens": mv.TILE_TOKENS,
        "default_target_blocks": mv.TARGET_BLOCKS,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    P.log(f"sweep start order {args.order} {order}")
    mx.random.seed(72)
    tq = P.TurboQuantKVCache(bits=4, max_kv_size=P.CAP, prealloc_tokens=P.CAP)
    K = mx.zeros((1, P.NKV, P.CAP, P.D), dtype=P.DT)
    V = mx.zeros((1, P.NKV, P.CAP, P.D), dtype=P.DT)
    mx.eval(K, V)
    rows, off = [], 0
    while off < SWEEP_T[-1]:
        kc = mx.random.normal((1, P.NKV, P.CHUNK, P.D)).astype(P.DT)
        vc = mx.random.normal((1, P.NKV, P.CHUNK, P.D)).astype(P.DT)
        tq.update_and_fetch(kc, vc)
        K[:, :, off : off + P.CHUNK, :] = kc
        V[:, :, off : off + P.CHUNK, :] = vc
        mx.eval(tq.keys, tq.values, K, V)
        off += P.CHUNK
        if off not in SWEEP_T:
            continue
        T = off
        p = P.power_state()
        if not P.power_ok(p):
            P.log(f"ABORT: power state {p}")
            sys.exit(4)
        Kt, Vt = K[:, :, :T, :], V[:, :, :T, :]
        for k in SWEEP_K:
            q = mx.random.normal((1, P.NQ, k, P.D)).astype(P.DT)
            lens = [T - k + 1 + j for j in range(k)]
            if k == 1:
                n16 = P.timeit(
                    lambda: P.scaled_dot_product_attention(
                        q, Kt, Vt, cache=None, scale=P.SCALE, mask=None, policy=P.FusedV1Policy()
                    )
                )
            else:
                n16 = P.timeit(lambda: P.joint_attention(q, Kt, Vt, cache=None, scale=P.SCALE, mask="causal"))
            ref_tq = mv.mma_verify_tq4(tq, q, P.SCALE, lens).astype(mx.float32)
            ref_16 = mv.mma_verify_native16(K, V, q, P.SCALE, lens).astype(mx.float32)
            for bt in order:
                plan = mv.plan_blocks(T, bt)
                r = {
                    "T": T,
                    "k": k,
                    "block_tokens": bt,
                    "blocks": plan[0],
                    "tokens_per_block": plan[1],
                    "native16": n16,
                    "power": p,
                }
                for arm, fn, ref in (
                    ("mma_tq4", lambda bt=bt: mv.mma_verify_tq4(tq, q, P.SCALE, lens, block_tokens=bt), ref_tq),
                    ("mma_n16", lambda bt=bt: mv.mma_verify_native16(K, V, q, P.SCALE, lens, block_tokens=bt), ref_16),
                ):
                    out = fn().astype(mx.float32)
                    r[arm] = P.timeit(fn)
                    r[arm]["vs_default_rel"] = mx.max(mx.abs(out - ref)).item() / mx.max(mx.abs(ref)).item()
                rows.append(r)
                P.log(
                    f"T={T} k={k} bt={bt} blocks={plan[0]}: tq4 {r['mma_tq4']['median_ms']:.3f} n16 "
                    f"{r['mma_n16']['median_ms']:.3f} (native16 {n16['median_ms']:.3f}) ms"
                )
            mx.clear_cache()
    meta["power_end"] = P.power_state()
    Path(args.out).write_text(json.dumps({"meta": meta, "rows": rows}, indent=1))
    P.log(f"DONE -> {args.out}")


def report(d):
    runs = [
        json.loads((Path(d) / f"sweep-{i}.json").read_text()) for i in (1, 2) if (Path(d) / f"sweep-{i}.json").exists()
    ]
    if not runs:
        sys.exit(f"no sweep-N.json in {d}")
    heads = {(r["meta"]["fork"].get("head"), r["meta"]["mlx"], r["meta"]["device"]["architecture"]) for r in runs}
    if len(heads) > 1:
        sys.exit(f"REFUSED: passes not combinable {heads}")
    key = lambda r: (r["T"], r["k"], str(r["block_tokens"]))
    tab = {}
    for run in runs:
        for r in run["rows"]:
            tab.setdefault(key(r), []).append(r)
    P = print
    m = runs[0]["meta"]
    P(
        "# M72 1.2 tuning step 1 — matrix-unit verify block-plan sweep (GENERATED by "
        "`benchmark/spikes/m72_mma_sweep.py --report`; never hand-edit)\n"
    )
    P(
        f"MLX {m['mlx']}, {m['device']['device_name']} `{m['device']['architecture']}`; "
        f"fork `{m['fork'].get('head', '?')[:8]}`; tile {m['tile_tokens']} tokens, default "
        f"{m['default_target_blocks']} blocks per KV head; passes {', '.join(r['meta']['order'] for r in runs)} "
        "(opposite setting order); medians, mean over passes. Per layer, 24 q / 4 kv heads, head dim 256, bf16, caches "
        "preallocated to 262,144. `vs default` = max |out − out(default plan)| / max |out(default)| (summation order "
        "only).\n"
    )
    P(
        "| T | k | block tokens | blocks | mma TQ4 (ms) | mma native16 (ms) | native16 SDPA / joint (ms) | "
        "TQ4 / native16 | native16 mma / native16 | max vs default |"
    )
    P("|---|---|---|---|---|---|---|---|---|---|")
    mean = lambda rs, f: sum(f(r) for r in rs) / len(rs)
    for T in SWEEP_T:
        for k in SWEEP_K:
            for bt in BLOCK_TOKENS:
                rs = tab.get((T, k, str(bt)))
                if not rs:
                    continue
                tq = mean(rs, lambda r: r["mma_tq4"]["median_ms"])
                n = mean(rs, lambda r: r["mma_n16"]["median_ms"])
                b = mean(rs, lambda r: r["native16"]["median_ms"])
                dv = max(max(r["mma_tq4"]["vs_default_rel"], r["mma_n16"]["vs_default_rel"]) for r in rs)
                P(
                    f"| {T} | {k} | {bt or 'default'} | {rs[0]['blocks']} | {tq:.3f} | {n:.3f} | {b:.3f} | "
                    f"{tq / b:.2f} | {n / b:.2f} | {dv:.1e} |"
                )
    if len(runs) == 2:
        P(
            "\nPass-to-pass drift (sweep-2 / sweep-1, mma TQ4 median): "
            + ", ".join(
                f"T={k_[0]} k={k_[1]} bt={k_[2]} {v[1]['mma_tq4']['median_ms'] / v[0]['mma_tq4']['median_ms']:.3f}"
                for k_, v in tab.items()
                if len(v) == 2 and k_[2] in ("None", "128")
            )
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--order", choices=("forward", "reverse"), default="forward")
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
