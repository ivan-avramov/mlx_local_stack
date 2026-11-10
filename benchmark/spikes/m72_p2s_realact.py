#!/usr/bin/env python3
"""M72 P2' stage 1 real-activation accuracy check (operator, 2026-11-10: the probe's accuracy runs on random data).

Loads `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` in-process, gives its full-attention layers TurboQuant 4 caches, prefills a
real coding prompt (the fork's own Python sources) in 512-token chunks, and captures every full-attention layer's last-chunk
attention call. On each layer and every query head it compares, against an fp32 reference over the same TQ4 state (exact causal
softmax on the codec's dequantized K / V): today's production TQ4 path, P1 (generic-op rotated dequantize, bf16), and stage 1
(`scratch_prefill_tq4`) in fp16 and bf16; and records the real overflow headroom of the fp16 scratch (max |q|, max rotated |q|,
max key / value norm, max scratch value). Accuracy only; no timing.
Run: PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/m72_p2s_realact.py --tokens 32768 --out <dir>/realact.json
"""

import argparse
import json
import sys
import time
from pathlib import Path

import mlx.core as mx

MODEL = "caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
CHUNK = 512


def prompt_tokens(tokenizer, n):
    import mlx_vlm

    root = Path(mlx_vlm.__file__).resolve().parent
    text, ids = "", []
    for f in sorted(root.rglob("*.py")):
        text += f"\n# ==== {f.relative_to(root)} ====\n" + f.read_text(errors="replace")
        if len(text) > n * 6:
            ids = tokenizer.encode(text)
            if len(ids) >= n:
                break
    ids = tokenizer.encode(text)
    assert len(ids) >= n, f"prompt has only {len(ids)} tokens"
    return ids[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokens", type=int, default=32768)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    N = a.tokens - a.tokens % CHUNK

    from mlx_vlm.models.qwen3_5 import language as lang
    from mlx_vlm.turboquant import TurboQuantKVCache, _slice_state
    from mlx_vlm.utils import load

    sys.path.insert(0, str(Path(lang.__file__).resolve().parents[3] / "dev"))
    import m72_scratch_prefill as m

    t0 = time.time()
    model, processor = load(MODEL)
    tok = getattr(processor, "tokenizer", processor)
    lm = model.language_model
    caches = lm.make_cache()
    full = [i for i, layer in enumerate(lm.layers) if not layer.is_linear]
    for i in full:
        caches[i] = TurboQuantKVCache(bits=4, max_kv_size=N, prealloc_tokens=N)
    print(f"loaded in {time.time() - t0:.0f} s; {len(full)} full-attention layers {full}", flush=True)

    captured = {}
    orig = lang.scaled_dot_product_attention

    def hook(queries, keys, values, cache=None, scale=None, mask=None, **kw):
        if isinstance(cache, TurboQuantKVCache) and queries.shape[2] > 1:
            captured[id(cache)] = (queries, keys, values, scale, mask, kw)
        return orig(queries, keys, values, cache=cache, scale=scale, mask=mask, **kw)

    lang.scaled_dot_product_attention = hook
    ids = mx.array(prompt_tokens(tok, N))[None]
    t1 = time.time()
    for s in range(0, N, CHUNK):
        out = lm(ids[:, s : s + CHUNK], cache=caches)
        mx.eval(getattr(out, "logits", out))  # one evaluation per chunk (the captures keep only the last chunk alive)
    lang.scaled_dot_product_attention = orig
    print(f"prefilled {N} tokens in {time.time() - t1:.0f} s", flush=True)

    rows = []
    for i in full:
        cache = caches[i]
        q, keys, values, scale, mask, kw = captured[id(cache)]
        T = int(cache.offset)
        L = q.shape[2]
        prod = orig(q, keys, values, cache=cache, scale=scale, mask=mask, **kw).astype(mx.float32)
        arms = {
            "production": prod,
            "p1_bf16": m.reference_prefill(cache, q, scale, T, mx.bfloat16).astype(mx.float32),
            "p2s_fp16": m.scratch_prefill_tq4(cache, q, scale, dtype=mx.float16).astype(mx.float32),
            "p2s_bf16": m.scratch_prefill_tq4(cache, q, scale, dtype=mx.bfloat16).astype(mx.float32),
        }
        mx.eval(arms)
        ks, vs = _slice_state(cache.keys, T), _slice_state(cache.values, T)
        Kd = cache.key_codec.dequantize(ks).astype(mx.float32)
        Vd = cache.value_codec.dequantize(vs).astype(mx.float32)
        q_rot = cache.key_codec.prepare_queries(q)
        n_q, n_kv = q.shape[1], Kd.shape[1]
        R = n_q // n_kv
        pos = mx.arange(T - L, T)[:, None]
        tokpos = mx.arange(T)[None, :]
        errs = {k: [] for k in arms}
        for h in range(n_q):
            g = h // R
            sc = (q[0, h].astype(mx.float32) @ Kd[0, g].T) * scale
            sc = mx.where(tokpos <= pos, sc, -mx.inf)
            ref = mx.softmax(sc, axis=-1) @ Vd[0, g]
            den = mx.max(mx.abs(ref)).item()
            for k, arr in arms.items():
                d = arr[0, h] - ref
                errs[k].append(
                    {
                        "rel": mx.max(mx.abs(d)).item() / den,
                        "allclose": bool(mx.allclose(arr[0, h], ref, atol=3e-2, rtol=3e-2).item()),
                        "finite": bool(mx.all(mx.isfinite(arr[0, h])).item()),
                    }
                )
            mx.eval(ref)
        kn_max = float(mx.max(ks.norms.astype(mx.float32)).item())
        vn_max = float(mx.max(vs.norms.astype(mx.float32)).item())
        cbmax = float(mx.max(mx.abs(cache.key_codec.codebook)).item())
        row = {
            "layer": i,
            "T": T,
            "L": L,
            "scale": float(scale),
            "q_abs_max": float(mx.max(mx.abs(q.astype(mx.float32))).item()),
            "q_rot_abs_max": float(mx.max(mx.abs(q_rot.astype(mx.float32))).item()),
            "key_norm_max": kn_max,
            "value_norm_max": vn_max,
            "codebook_abs_max": cbmax,
            "scratch_abs_max_bound": max(kn_max, vn_max) * cbmax,
            "fp16_max": 65504.0,
            "arms": {},
        }
        for k, e in errs.items():
            prod_rel = [x["rel"] for x in errs["production"]]
            per_head_pass = [
                x["finite"] and x["allclose"] and x["rel"] <= 2 * max(p, 2**-12) for x, p in zip(e, prod_rel)
            ]
            row["arms"][k] = {
                "rel_max": max(x["rel"] for x in e),
                "rel_median": sorted(x["rel"] for x in e)[len(e) // 2],
                "all_allclose": all(x["allclose"] for x in e),
                "all_finite": all(x["finite"] for x in e),
                "a1_heads_pass": sum(per_head_pass),
                "heads": len(e),
                "ratio_to_production_max": max(x["rel"] / max(p, 2**-12) for x, p in zip(e, prod_rel)),
            }
        rows.append(row)
        print(
            f"layer {i:2d} T={T}: |q| {row['q_abs_max']:.1f} |q_rot| {row['q_rot_abs_max']:.1f} norms k {kn_max:.1f} "
            f"v {vn_max:.1f}; rel max prod {row['arms']['production']['rel_max']:.2e} p1_bf16 "
            f"{row['arms']['p1_bf16']['rel_max']:.2e} p2s_fp16 {row['arms']['p2s_fp16']['rel_max']:.2e} "
            f"(A1 {row['arms']['p2s_fp16']['a1_heads_pass']}/{n_q}) p2s_bf16 {row['arms']['p2s_bf16']['rel_max']:.2e} "
            f"(A1 {row['arms']['p2s_bf16']['a1_heads_pass']}/{n_q})",
            flush=True,
        )
        del Kd, Vd, arms
        mx.clear_cache()
    meta = {
        "spike": "m72_p2s_realact",
        "model": MODEL,
        "tokens": N,
        "prompt": "fork mlx_vlm/*.py sources",
        "mlx": mx.__version__,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    Path(a.out).write_text(json.dumps({"meta": meta, "rows": rows}, indent=1))
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
