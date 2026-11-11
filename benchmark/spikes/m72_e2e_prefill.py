#!/usr/bin/env python3
"""M72 P2' end-to-end prefill harness (C315): the real model, in-process, one fresh process per leg.

`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` prefills a real N-token prompt (repository Python sources) in 512-token chunks
with one evaluation per chunk, as the serving prefill loop does. Variants of its 16 full-attention layers:
  native16   PreallocKVCache(prealloc = N) + the shipped `fused_v1` attention policy (the baseline, lazy within a chunk)
  tq4_prod   TurboQuantKVCache(4 bits, prealloc = N), today's TQ4 prefill path
  tq4_p2s    TurboQuantKVCache + P2' stage 1 (`scratch_prefill_tq4`, fp16) for prefill chunks, with an evaluation policy:
               --eval layer    evaluate each full-attention layer's output (one scratch alive; stage 1's contract)
               --eval pipe2    async_eval each layer's output, then block on the previous one (<= 2 scratches)
               --eval every2   evaluate every second full-attention layer (<= 2 scratches)
               --eval none     no extra evaluation (the lazy graph; memory control only)
  tq4_m72    the production TQ4 attention mode (M72 1.3, `tq4_attention` m72_v1) as served: `make_cache` +
             `maybe_quantize_kv_cache` + `maybe_preallocate_kv_cache` (the last layer, 63, stays native16), the
             `fused_v1` / `joint_v1` stamps and the mode stamped by the fork's own loaders; the per-layer evaluation
             is the mode's (--eval is ignored); records the R1 range values and the route counters
--capacity C (default = --tokens) preallocates every variant's caches to C tokens (A5 matches capacity 262,144).
Per leg: wall time of the prefill loop, tokens/s, and two process-level memory instruments — the OS footprint ledger
(proc_pid_rusage interval max, reset after the model and caches exist) and MLX's allocator high-water — plus absolute peaks.
Driver: --legs runs the given variant:eval legs in order, each in a fresh process, with --idle seconds between and the power /
idle-GPU gates before each.
Run: PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/m72_e2e_prefill.py --tokens 131072 \
       --legs native16 tq4_p2s:layer tq4_p2s:layer native16 --idle 600 --out <dir>/e2e-131072.json
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m72_p2s_memory import _LIB, footprint  # noqa: E402

MODEL = "caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
CHUNK = 512


def prompt_ids(tokenizer, n):
    import mlx_vlm

    roots = [Path(mlx_vlm.__file__).resolve().parent, Path(__file__).resolve().parents[2] / "benchmark"]
    text = ""
    for root in roots:
        for f in sorted(root.rglob("*.py")):
            text += f"\n# ==== {f.name} ====\n" + f.read_text(errors="replace")
    ids = tokenizer.encode(text)
    reps = 1
    while len(ids) < n:  # repeat the corpus if it is shorter than n (recorded)
        ids = ids + ids
        reps *= 2
    return ids[:n], {"corpus_tokens": len(tokenizer.encode(text)), "repeats": reps}


def run_leg(a):
    import mlx.core as mx

    from mlx_vlm.attention_policy import FusedV1Policy
    from mlx_vlm.models.cache import PreallocKVCache
    from mlx_vlm.models.qwen3_5 import language as lang
    from mlx_vlm.turboquant import TurboQuantKVCache
    from mlx_vlm.utils import load

    N = a.tokens - a.tokens % CHUNK
    C = a.capacity or N  # cache capacity (preallocation); default = the prompt
    if C < N:
        raise SystemExit(f"--capacity {C} < prompt {N}")
    model, processor = load(MODEL)
    tok = getattr(processor, "tokenizer", processor)
    lm = model.language_model
    full = [i for i, layer in enumerate(lm.layers) if not layer.is_linear]
    caches = lm.make_cache()
    extra = {}
    if a.variant == "tq4_m72":
        extra = _production_mode(model, caches, C)
    else:
        for i in full:
            if a.variant == "native16":
                caches[i] = PreallocKVCache(prealloc_tokens=C)
                lm.layers[i].self_attn.attention_policy = FusedV1Policy()
            else:
                caches[i] = TurboQuantKVCache(bits=4, max_kv_size=C, prealloc_tokens=C)
    ids, corpus = prompt_ids(tok, N)
    ids = mx.array(ids)[None]
    orig = lang.scaled_dot_product_attention
    state = {"n": 0, "prev": None}
    if a.variant == "tq4_p2s":
        sys.path.insert(0, str(Path(lang.__file__).resolve().parents[3] / "dev"))
        import m72_scratch_prefill as m

        def hook(queries, keys, values, cache=None, scale=None, mask=None, **kw):
            if not (isinstance(cache, TurboQuantKVCache) and queries.shape[2] > 1):
                return orig(queries, keys, values, cache=cache, scale=scale, mask=mask, **kw)
            out = m.scratch_prefill_tq4(cache, queries, scale)
            state["n"] += 1
            if a.eval == "layer":
                mx.eval(out)
            elif a.eval == "every2" and state["n"] % 2 == 0:
                mx.eval(out)
            elif a.eval == "pipe2":
                mx.async_eval(out)
                if state["prev"] is not None:
                    mx.eval(state["prev"])
                state["prev"] = out
            return out

        lang.scaled_dot_product_attention = hook
    mx.synchronize()
    mx.clear_cache()
    time.sleep(1.0)
    f0 = footprint()
    _LIB.proc_reset_footprint_interval(os.getpid())
    mx.reset_peak_memory()
    a0 = mx.get_active_memory()
    t0 = time.perf_counter()
    for s in range(0, N, CHUNK):
        out = lm(ids[:, s : s + CHUNK], cache=caches)
        mx.eval(getattr(out, "logits", out))
        state["prev"] = None
    mx.synchronize()
    dt = time.perf_counter() - t0
    f1 = footprint()
    logits_tail = getattr(out, "logits", out)[0, -1].astype(mx.float32)
    if a.variant == "tq4_m72":
        from mlx_vlm import tq4_fast

        after = tq4_fast.route_counts()
        before = extra.pop("_counts_before")
        extra["route_counts"] = {k: v - before.get(k, 0) for k, v in after.items() if v != before.get(k, 0)}
        extra.update(_layer_bytes(caches, extra["tq4_layers"], extra["native_layers"]))
    res = {
        "variant": a.variant,
        "eval": a.eval if a.variant == "tq4_p2s" else ("production" if a.variant == "tq4_m72" else None),
        "tokens": N,
        "capacity": C,
        **extra,
        "prefill_s": dt,
        "tok_per_s": N / dt,
        "corpus": corpus,
        "os_footprint_before_GB": f0["current"] / 1e9,
        "os_peak_GB": f1["interval_max"] / 1e9,
        "os_peak_delta_GB": (f1["interval_max"] - f0["current"]) / 1e9,
        "mlx_peak_GB": mx.get_peak_memory() / 1e9,
        "mlx_peak_delta_GB": (mx.get_peak_memory() - a0) / 1e9,
        "last_logit_top5": [int(x) for x in mx.argsort(-logits_tail)[:5].tolist()],
    }
    print(json.dumps(res), flush=True)


def _production_mode(model, caches, capacity):
    """The served TQ4 arm's caches and stamps (fork loaders, server load order): returns the records for the leg."""
    from mlx_vlm import attention_policy as ap
    from mlx_vlm import mtp_verify_scan as mv
    from mlx_vlm import tq4_attention as t4
    from mlx_vlm import tq4_fast
    from mlx_vlm.generate.common import maybe_preallocate_kv_cache, maybe_quantize_kv_cache
    from mlx_vlm.turboquant import TurboQuantKVCache

    maybe_quantize_kv_cache(
        caches,
        quantized_kv_start=0,
        kv_group_size=64,
        kv_bits=4,
        kv_quant_scheme="turboquant",
        max_kv_size=capacity,
        kv_prealloc_tokens=capacity,
    )
    maybe_preallocate_kv_cache(caches, kv_prealloc_tokens=capacity)
    lm = model.language_model
    full = [i for i, layer in enumerate(lm.layers) if not layer.is_linear]
    kinds = {i: type(caches[i]).__name__ for i in full}
    tq4_layers = [i for i in full if isinstance(caches[i], TurboQuantKVCache)]
    ap.apply_to_model(model, ap.FusedV1Policy())
    mv.apply_to_model(model, mv.JointV1Policy())
    t4.require_policy_stamps(model)
    rng = t4.check_fp16_range(model)
    t4.apply_to_model(model, "m72_v1")
    st = t4.self_test_model(model, "m72_v1")
    return {
        "mode": "m72_v1",
        "cache_classes": kinds,
        "tq4_layers": tq4_layers,
        "native_layers": [i for i in full if i not in tq4_layers],
        "r1_max_q_bound": rng["max_q_bound"],
        "r1_max_codebook": rng["max_codebook"],
        "self_test_cells": st["cells"],
        "_counts_before": tq4_fast.route_counts(),
    }


def _nbytes(shape, dtype) -> int:
    n = 1
    for s in shape:
        n *= int(s)
    return n * dtype.size


def _layer_bytes(caches, tq4_layers, native_layers):
    """A5's allowance term from the cache shapes at capacity: the native16 last layer's K + V bytes minus one TQ4
    layer's (norms + packed indices, keys and values)."""
    tq = caches[tq4_layers[0]]
    tq_bytes = sum(_nbytes(x.shape, x.dtype) for st in (tq.keys, tq.values) for x in st)
    nat = caches[native_layers[-1]]
    nat_bytes = sum(_nbytes(x.shape, x.dtype) for x in (nat.keys, nat.values))
    return {
        "native_layer_bytes": nat_bytes,
        "native_layer_shape": list(nat.keys.shape),
        "tq4_layer_bytes": tq_bytes,
        "tq4_layer_capacity": int(tq.keys.norms.shape[2]),
        "a5_layer63_allowance_GB": (nat_bytes - tq_bytes) / 1e9,
    }


def gates():
    import mlx.core as mx

    import m72_gates
    from m72_tq4_probe import power_ok, power_state

    p = power_state()
    one = mx.ones((16,))
    mx.eval(one)
    g = {
        "device_utilization_pct": m72_gates.gpu_utilization(),
        "tiny_op_floor_ms": m72_gates.tiny_op_floor_ms(lambda: (mx.eval(one + 1), mx.synchronize())),
    }
    return p, g, power_ok(p) and m72_gates.gpu_idle_ok(g)


def run_all(a):
    legs = []
    for k, spec in enumerate(a.legs):
        if k and a.idle:
            print(f"[{time.strftime('%H:%M:%S')}] IDLE {a.idle}s", flush=True)
            time.sleep(a.idle)
        variant, _, ev = spec.partition(":")
        p, g, ok = gates()
        if not ok:
            print(f"REFUSED: gates {p} {g}", flush=True)
            sys.exit(3)
        cmd = [
            sys.executable,
            __file__,
            "--leg",
            "--variant",
            variant,
            "--eval",
            ev or "layer",
            "--tokens",
            str(a.tokens),
        ]
        if a.capacity:
            cmd += ["--capacity", str(a.capacity)]
        print(f"[{time.strftime('%H:%M:%S')}] BEGIN leg {k + 1} {spec} power {p} gpu {g}", flush=True)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
        if r.returncode != 0:
            print(f"leg {spec} FAILED rc={r.returncode}\n{r.stderr[-3000:]}", flush=True)
            sys.exit(10 + k + 1)
        row = json.loads(r.stdout.strip().splitlines()[-1])
        row["power_before"], row["gpu_before"] = p, g
        legs.append(row)
        print(
            f"[{time.strftime('%H:%M:%S')}] END leg {k + 1} {spec}: {row['prefill_s']:.1f} s ({row['tok_per_s']:.0f} tok/s), "
            f"os peak {row['os_peak_GB']:.2f} GB (+{row['os_peak_delta_GB']:.2f}), top5 {row['last_logit_top5']}",
            flush=True,
        )
        if a.out:
            Path(a.out).write_text(
                json.dumps(
                    {
                        "meta": {
                            "harness": "m72_e2e_prefill",
                            "model": MODEL,
                            "tokens": a.tokens,
                            "capacity": a.capacity or a.tokens - a.tokens % CHUNK,
                            "legs": a.legs,
                            "idle_s": a.idle,
                        },
                        "legs": legs,
                    },
                    indent=1,
                )
            )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leg", action="store_true")
    ap.add_argument("--variant", choices=("native16", "tq4_prod", "tq4_p2s", "tq4_m72"))
    ap.add_argument("--eval", choices=("layer", "pipe2", "every2", "none"), default="layer")
    ap.add_argument("--tokens", type=int, default=131072)
    ap.add_argument("--capacity", type=int, default=None, help="cache capacity in tokens (default: --tokens)")
    ap.add_argument("--legs", nargs="+")
    ap.add_argument("--idle", type=int, default=600)
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.leg:
        run_leg(a)
    elif a.legs:
        run_all(a)
    else:
        ap.error("--leg or --legs")


if __name__ == "__main__":
    main()
