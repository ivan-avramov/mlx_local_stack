"""
Spike F (M5-only) — GATING: can mx.fast.metal_kernel (runtime JIT) emit Metal 4
TensorOps / Metal Performance Primitives (matmul2d) to reach the M5 Neural
Accelerators?  The example_matmul_metal4 author warns <metal_tensor>/MPP headers
"don't seem provided at runtime" — so JIT may not see them. Confirm on THIS box.

Incremental: (1) does <metal_tensor> compile via JIT? (2) +MPP header? (3) full
matmul2d kernel compile+run? Each isolated so we know header-availability vs
syntax. Run on M5: .venv/bin/python benchmark/spikes/spike_f_tensorops.py
"""
import mlx.core as mx

print("=" * 72)
print(f"SPIKE F — Metal 4 TensorOps via mx.fast.metal_kernel  ({mx.device_info()['device_name']})")
print(f"mlx {mx.__version__}")
print("=" * 72)


def probe(name, header, body, inputs, out_shape, grid, tg, in_names, out_dtype=mx.float16):
    try:
        k = mx.fast.metal_kernel(name=name, input_names=in_names, output_names=["out"],
                                 source=body, header=header)
        o = k(inputs=inputs, grid=grid, threadgroup=tg,
              output_shapes=[out_shape], output_dtypes=[out_dtype])[0]
        mx.eval(o)
        s = mx.sum(mx.abs(o.astype(mx.float32))).item()
        print(f"  [{name}] OK — compiled+ran (|out| sum={s:.2f})")
        return True
    except Exception as e:  # noqa
        print(f"  [{name}] FAIL:\n      {str(e)[:2000].replace(chr(10), chr(10)+'      ')}")
        return False


A = mx.ones((16,), dtype=mx.float16)

# (1) <metal_tensor> header available to the runtime JIT compiler?
probe("metal_tensor_include",
      header="#include <metal_tensor>\nusing namespace metal;",
      body="uint i=thread_position_in_grid.x; if(i<16) out[i]=A[i];",
      inputs=[A], out_shape=(16,), grid=(16,1,1), tg=(16,1,1), in_names=["A"])

# (2) + MetalPerformancePrimitives header?
probe("mpp_include",
      header="#include <metal_tensor>\n#include <MetalPerformancePrimitives/MetalPerformancePrimitives.h>\nusing namespace metal;",
      body="uint i=thread_position_in_grid.x; if(i<16) out[i]=A[i];",
      inputs=[A], out_shape=(16,), grid=(16,1,1), tg=(16,1,1), in_names=["A"])

# (3) full matmul2d kernel (exact syntax from liuliu/example_matmul_metal4)
mm_header = """
#include <metal_stdlib>
#include <metal_tensor>
#include <MetalPerformancePrimitives/MetalPerformancePrimitives.h>
using namespace metal;
using namespace mpp::tensor_ops;
"""
mm_body = """
    uint2 tgid = uint2(threadgroup_position_in_grid.x, threadgroup_position_in_grid.y);
    auto Amat = tensor<const device half, extents<int32_t,256,128>, tensor_inline>(A_buf, extents<int32_t,256,128>());
    auto Bmat = tensor<const device half, extents<int32_t,64,256>, tensor_inline>(B_buf, extents<int32_t,64,256>());
    auto Cmat = tensor<device float, extents<int32_t,128,64>, tensor_inline>(out, extents<int32_t,128,64>());
    constexpr auto desc0 = matmul2d_descriptor(64, 32, 32, false, false, false, matmul2d_descriptor::mode::multiply);
    constexpr auto descA = matmul2d_descriptor(64, 32, 32, false, false, false, matmul2d_descriptor::mode::multiply_accumulate);
    matmul2d<desc0, execution_simdgroups<4>> op0;
    matmul2d<descA, execution_simdgroups<4>> opA;
    for (int k = 0; k < 256; k += 32) {
        auto mA = Amat.slice<32,64>(k, tgid.y * 64);
        auto mB = Bmat.slice<32,32>(tgid.x * 32, k);
        auto mC = Cmat.slice<32,64>(tgid.x * 32, tgid.y * 64);
        if (k == 0) op0.run(mA, mB, mC); else opA.run(mA, mB, mC);
    }
"""
Abuf = mx.ones((256 * 128,), dtype=mx.float16)
Bbuf = mx.ones((64 * 256,), dtype=mx.float16)
probe("matmul2d_full", header=mm_header, body=mm_body,
      inputs=[Abuf, Bbuf], out_shape=(128 * 64,),
      grid=(2 * 128, 2, 1), tg=(128, 1, 1), in_names=["A_buf", "B_buf"], out_dtype=mx.float32)

print("\nVERDICT: if (1) already FAILs, the JIT path cannot reach Metal 4 tensors ->")
print("the M5 NA must be reached via MLX built-in ops (mx.matmul / decomposed), not")
print("a hand-written mx.fast.metal_kernel. If (3) runs, a fused TensorOps kernel is viable.")
print("DONE")
