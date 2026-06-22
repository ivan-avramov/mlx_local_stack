#!/usr/bin/env python3
"""Batch-dependence micro-benchmark for MLX speculative verify primitives.

No model is loaded.  The test feeds the same random tensors through:

  1. mx.fast.scaled_dot_product_attention with K verify positions in one call
     versus K one-position decode-style calls.
  2. mlx_lm.models.switch_layers.SwitchGLU with [1, K, H] input versus K
     one-token calls, both dense fp16 and 8-bit quantized.

Run from benchmark/ with:

  PYTHONPATH=../mlx-vlm:. \
    $STACK_REPO/.venv/bin/python \
    codex_primitive_batch.py
"""

from __future__ import annotations

import argparse
import gc
import random
from dataclasses import dataclass
from typing import Iterable

import mlx.core as mx


P = 80
K = 90

MODEL_HIDDEN = 2816
MOE_HIDDEN = 704
NUM_EXPERTS = 128
TOP_K = 8
Q_GROUP_SIZE = 64
Q_BITS = 8

BAD_THRESHOLD = 1e-3


class GeGLU:
    def __call__(self, x: mx.array, gate: mx.array) -> mx.array:
        import mlx.nn as nn

        return nn.gelu_approx(gate) * x


@dataclass(frozen=True)
class Result:
    name: str
    primitive: str
    dtype: str
    maxdiffs: list[float]

    @property
    def maxdiff(self) -> float:
        return max(self.maxdiffs) if self.maxdiffs else 0.0

    @property
    def first_bad(self) -> int | None:
        return next((i for i, d in enumerate(self.maxdiffs) if d > BAD_THRESHOLD), None)

    @property
    def bad_count(self) -> int:
        return sum(1 for d in self.maxdiffs if d > BAD_THRESHOLD)


def dtype_name(dtype: mx.Dtype) -> str:
    return str(dtype).replace("mlx.core.", "")


def fmt(x: float) -> str:
    return f"{x:.6g}"


def materialize_per_position(diff: mx.array) -> list[float]:
    mx.eval(diff)
    return [float(x) for x in diff.tolist()]


def sdpa_result(label: str, n_heads: int, n_kv_heads: int, head_dim: int, dtype: mx.Dtype) -> Result:
    scale = head_dim**-0.5

    q = mx.random.normal((1, n_heads, P + K, head_dim)).astype(dtype)
    k = mx.random.normal((1, n_kv_heads, P + K, head_dim)).astype(dtype)
    v = mx.random.normal((1, n_kv_heads, P + K, head_dim)).astype(dtype)
    q_verify = q[:, :, P : P + K, :]

    batched = mx.fast.scaled_dot_product_attention(
        q_verify,
        k,
        v,
        scale=scale,
        mask="causal",
    )
    single = mx.concatenate(
        [
            mx.fast.scaled_dot_product_attention(
                q_verify[:, :, j : j + 1, :],
                k[:, :, : P + j + 1, :],
                v[:, :, : P + j + 1, :],
                scale=scale,
                mask=None,
            )
            for j in range(K)
        ],
        axis=2,
    )

    diff = mx.max(mx.abs(batched - single), axis=(0, 1, 3))
    maxdiffs = materialize_per_position(diff)

    del q, k, v, q_verify, batched, single, diff
    gc.collect()
    mx.clear_cache()

    return Result(
        name=f"sdpa_{label}_{dtype_name(dtype)}",
        primitive=f"SDPA {label}",
        dtype=dtype_name(dtype),
        maxdiffs=maxdiffs,
    )


def random_topk_indices(seed: int) -> mx.array:
    rng = random.Random(seed)
    return mx.array(
        [[rng.sample(range(NUM_EXPERTS), TOP_K) for _ in range(K)]],
        dtype=mx.uint32,
    )


def switchglu_result(quantized: bool, seed: int = 1234) -> Result:
    import mlx.nn as nn
    from mlx_lm.models.switch_layers import SwitchGLU

    dtype = mx.float16
    mx.random.seed(seed)

    sg = SwitchGLU(
        input_dims=MODEL_HIDDEN,
        hidden_dims=MOE_HIDDEN,
        num_experts=NUM_EXPERTS,
        activation=GeGLU(),
        bias=False,
    )
    sg.eval()
    sg.set_dtype(dtype)

    if quantized:
        nn.quantize(sg, group_size=Q_GROUP_SIZE, bits=Q_BITS)

    x = mx.random.normal((1, K, MODEL_HIDDEN)).astype(dtype)
    indices = random_topk_indices(seed + 1)

    batched = sg(x, indices)
    single = mx.concatenate(
        [sg(x[:, j : j + 1, :], indices[:, j : j + 1, :]) for j in range(K)],
        axis=1,
    )

    diff = mx.max(mx.abs(batched - single), axis=(0, 2, 3))
    maxdiffs = materialize_per_position(diff)

    del sg, x, indices, batched, single, diff
    gc.collect()
    mx.clear_cache()

    return Result(
        name=f"switchglu_{'q8' if quantized else 'fp16'}",
        primitive=f"SwitchGLU {'q8' if quantized else 'fp16'}",
        dtype="float16",
        maxdiffs=maxdiffs,
    )


def summary_table(results: Iterable[Result]) -> None:
    print("\nSUMMARY")
    print(f"{'case':34s} {'primitive':18s} {'dtype':10s} {'maxdiff':>12s} {'bad>1e-3':>10s} {'first_bad':>9s}")
    print("-" * 101)
    for r in results:
        first = "-" if r.first_bad is None else str(r.first_bad)
        print(
            f"{r.name:34s} {r.primitive:18s} {r.dtype:10s} "
            f"{fmt(r.maxdiff):>12s} {f'{r.bad_count}/{K}':>10s} {first:>9s}"
        )


def per_position_table(results: list[Result]) -> None:
    print("\nPER_POSITION_MAX_ABS_DIFF")
    print(",".join(["pos"] + [r.name for r in results]))
    for pos in range(K):
        print(",".join([str(pos)] + [fmt(r.maxdiffs[pos]) for r in results]))


def verdict(results: Iterable[Result]) -> None:
    bad = [r for r in results if r.maxdiff > BAD_THRESHOLD]
    print("\nVERDICT")
    if not bad:
        print("No tested primitive is batch-dependent above 1e-3.")
        return

    for r in bad:
        print(f"- {r.name}: batch-dependent, maxdiff={fmt(r.maxdiff)}, bad_positions={r.bad_count}/{K}")

    if any(r.primitive.startswith("SDPA") for r in bad):
        print(
            "- SDPA classification: INHERENT prefill-vs-decode Metal kernel "
            "numeric difference. It is not suffix bookkeeping corruption; a "
            "lossless verify path must avoid the multi-token SDPA kernel or use "
            "a kernel that is decode-identical."
        )
    if any(r.primitive.startswith("SwitchGLU") for r in bad):
        print(
            "- SwitchGLU classification: FIXABLE verify-path logic difference. "
            "The standard batched path crosses SwitchGLU's sorted gather branch; "
            "force verify through the same unsorted/token-wise gather_mm/gather_qmm "
            "route as decode."
        )


def run(args: argparse.Namespace) -> list[Result]:
    mx.random.seed(args.seed)
    results: list[Result] = []

    if args.only in ("all", "sdpa"):
        sdpa_cases = (
            ("full", 16, 2, 512),
            ("sliding", 16, 8, 256),
        )
        for dtype in (mx.bfloat16, mx.float16, mx.float32):
            for label, n_heads, n_kv_heads, head_dim in sdpa_cases:
                print(f"running SDPA {label} {dtype_name(dtype)}...", flush=True)
                results.append(sdpa_result(label, n_heads, n_kv_heads, head_dim, dtype))

    if args.only in ("all", "switchglu"):
        print("running SwitchGLU fp16...", flush=True)
        results.append(switchglu_result(quantized=False, seed=args.seed + 100))
        print("running SwitchGLU q8...", flush=True)
        results.append(switchglu_result(quantized=True, seed=args.seed + 200))

    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--only", choices=("all", "sdpa", "switchglu"), default="all")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results = run(args)
    summary_table(results)
    per_position_table(results)
    verdict(results)


if __name__ == "__main__":
    main()
