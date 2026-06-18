"""
Spike G — is long-context TQ decode compute-bound or latency-bound?

Spike E: production decode @200K reads ~0.154GB of 3-bit K+V in 7.45ms = ~21 GB/s
(7% of the ~310 GB/s peak), so it is NOT bandwidth-bound. Is the bottleneck the
per-token COMPUTE (dequant + simd_sum + exp online-softmax) — fixable — or memory
LATENCY of the strided packed reads — not fixable by faster compute?

Three kernels, identical DRAM traffic (read packed K+V once per token, G=2 GQA
tile-reuse, block-split for occupancy), varying only the per-token compute:
  full     : dequant K + score + simd_sum + exp online-softmax + dequant V + accumulate
  noexp    : dequant K + score + simd_sum + accumulate  (drops exp/softmax; wrong math, same mem+reduce)
  readonly : read packed K+V words + checksum only       (the access-pattern bandwidth ceiling)

If readonly >> full -> compute-bound (headroom). If readonly ~= full -> latency-bound.
Run: PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/spike_g_decode_compute.py
"""
import time
import numpy as np
import mlx.core as mx

D = 256; BITS = 3; N_KV = 4; R = 6; N_Q = N_KV * R; EPT = D // 32; NB = 512
G = 2; GROUPS = R // G
MASK = (1 << BITS) - 1
PWv = (D * BITS + 31) // 32


def bench(fn, it=20, wu=6):
    for _ in range(wu): mx.eval(fn())
    mx.synchronize(); t = time.perf_counter()
    for _ in range(it): mx.eval(fn())
    mx.synchronize(); return (time.perf_counter() - t) / it


def make_kv(T, seed=0):
    rng = np.random.default_rng(seed)
    cb = np.linspace(-1.0, 1.0, 1 << BITS).astype(np.float32)
    def pack(unit):
        idx = np.abs(unit[..., None] - cb).argmin(-1).astype(np.uint64)
        p = np.zeros((N_KV, T, PWv), dtype=np.uint64)
        for d in range(D):
            bit = d * BITS; w = bit // 32; off = bit % 32
            p[:, :, w] |= idx[:, :, d] << off
            if off + BITS > 32: p[:, :, w + 1] |= idx[:, :, d] >> (32 - off)
        return mx.array(p.astype(np.uint32))
    ku = rng.standard_normal((N_KV, T, D)).astype(np.float32); ku /= np.linalg.norm(ku, axis=-1, keepdims=True)
    vu = rng.standard_normal((N_KV, T, D)).astype(np.float32); vu /= np.linalg.norm(vu, axis=-1, keepdims=True)
    knm = mx.array((np.abs(rng.standard_normal((N_KV, T))) + 0.5).astype(np.float16))
    vnm = mx.array((np.abs(rng.standard_normal((N_KV, T))) + 0.5).astype(np.float16))
    q = mx.array(rng.standard_normal((N_Q, D)).astype(np.float16))
    return pack(ku), knm, pack(vu), vnm, q, mx.array(cb)


_DEQ_K = """{ const device uint* kp=kpk+t*PW;
   for(int i=0;i<EPT;i++){uint d=lane*EPT+i;uint bit=d*BITS;uint w=bit>>5,off=bit&31;uint v=kp[w]>>off;if(off+BITS>32)v|=kp[w+1]<<(32-off);v&=MSK;kd[i]=cb[v];} }"""
_DEQ_V = """{ const device uint* vp=vpk+t*PW;
   for(int i=0;i<EPT;i++){uint d=lane*EPT+i;uint bit=d*BITS;uint w=bit>>5,off=bit&31;uint v=vp[w]>>off;if(off+BITS>32)v|=vp[w+1]<<(32-off);v&=MSK;vd[i]=cb[v];} }"""

_HEAD = f"""
    constexpr int EPT={EPT},BITS={BITS},G={G},GROUPS={GROUPS},R={R},DD={D},NB={NB};constexpr uint MSK={MASK}u;
    uint gid=threadgroup_position_in_grid.x; uint block=gid%NB; uint ug=gid/NB;
    uint bh=ug/GROUPS; uint grp=ug%GROUPS; uint qbase=bh*R+grp*G;
    uint lane=thread_index_in_simdgroup;
    const device uint* kpk=Kpacked+bh*T*PW; const device half* knm=Knorms+bh*T;
    const device uint* vpk=Vpacked+bh*T*PW; const device half* vnm=Vnorms+bh*T;
    float qreg[G][EPT];
    for(int r=0;r<G;r++)for(int i=0;i<EPT;i++)qreg[r][i]=(float)Q[(qbase+r)*DD+lane*EPT+i];
    uint tpb=(T+NB-1)/NB; uint t0=block*tpb; uint t1=min(t0+tpb,(uint)T);
"""

KERNELS = {
"full": _HEAD + f"""
    float o[G][EPT]; float msc[G],sm[G];
    for(int r=0;r<G;r++){{msc[r]=-INFINITY;sm[r]=0;for(int i=0;i<EPT;i++)o[r][i]=0;}}
    for(uint t=t0;t<t1;t++){{
        float kd[EPT]; {_DEQ_K} float kn=(float)knm[t];
        float vd[EPT]; {_DEQ_V} float vnn=(float)vnm[t];
        for(int r=0;r<G;r++){{
            float sc=0; for(int i=0;i<EPT;i++)sc+=qreg[r][i]*kd[i];
            sc=simd_sum(sc)*kn;
            float nm=max(msc[r],sc),corr=fast::exp(msc[r]-nm),es=fast::exp(sc-nm);
            msc[r]=nm; sm[r]=sm[r]*corr+es;
            for(int i=0;i<EPT;i++)o[r][i]=o[r][i]*corr+es*vnn*vd[i];
        }}
    }}
    for(int r=0;r<G;r++){{uint h=qbase+r; for(int i=0;i<EPT;i++)po[(h*NB+block)*DD+lane*EPT+i]=o[r][i];
        if(lane==0){{lmax[h*NB+block]=msc[r];lsum[h*NB+block]=sm[r];}}}}
""",
"noexp": _HEAD + f"""
    float o[G][EPT]; for(int r=0;r<G;r++)for(int i=0;i<EPT;i++)o[r][i]=0;
    for(uint t=t0;t<t1;t++){{
        float kd[EPT]; {_DEQ_K} float kn=(float)knm[t];
        float vd[EPT]; {_DEQ_V} float vnn=(float)vnm[t];
        for(int r=0;r<G;r++){{
            float sc=0; for(int i=0;i<EPT;i++)sc+=qreg[r][i]*kd[i];
            sc=simd_sum(sc)*kn;
            for(int i=0;i<EPT;i++)o[r][i]+=sc*vnn*vd[i];   // no exp/online-softmax
        }}
    }}
    for(int r=0;r<G;r++){{uint h=qbase+r; for(int i=0;i<EPT;i++)po[(h*NB+block)*DD+lane*EPT+i]=o[r][i];
        if(lane==0){{lmax[h*NB+block]=0;lsum[h*NB+block]=0;}}}}
""",
"readonly": _HEAD + f"""
    float acc=0;
    for(uint t=t0;t<t1;t++){{
        const device uint* kp=kpk+t*PW; const device uint* vp=vpk+t*PW;
        for(int w=0;w<PW;w++) acc += (float)(kp[w]^vp[w]);   // touch same bytes, trivial op
        acc += (float)knm[t] + (float)vnm[t];
    }}
    acc=simd_sum(acc);
    for(int r=0;r<G;r++){{uint h=qbase+r; po[(h*NB+block)*DD+lane*EPT]=acc;
        if(lane==0){{lmax[h*NB+block]=0;lsum[h*NB+block]=0;}}}}
""",
}

BUILT = {n: mx.fast.metal_kernel(name=f"dec_{n}", input_names=["Q","Kpacked","Knorms","Vpacked","Vnorms","cb"],
                                 output_names=["po","lmax","lsum"], source=s) for n, s in KERNELS.items()}


def run(T):
    kpk, knm, vpk, vnm, q, cb = make_kv(T)
    ins = [q, kpk, knm, vpk, vnm, cb]; tmpl = [("T", T), ("PW", PWv)]
    kv_gb = (N_KV * GROUPS * T * PWv * 4 * 2) / 1e9   # packed K+V read once per (kv,group,block-set)
    print(f"  T={T:>7} (K+V read ~{kv_gb:.3f} GB):")
    for name in ("readonly", "noexp", "full"):
        k = BUILT[name]
        def call():
            return k(inputs=ins, template=tmpl, grid=(N_KV*GROUPS*NB*32,1,1), threadgroup=(32,1,1),
                     output_shapes=[(N_Q,NB,D),(N_Q,NB),(N_Q,NB)],
                     output_dtypes=[mx.float32,mx.float32,mx.float32])[0]
        mx.eval(call()); s = bench(call)
        print(f"      {name:9s} {s*1e3:8.3f} ms   {kv_gb/s:7.1f} GB/s")


if __name__ == "__main__":
    print("=" * 70)
    print(f"SPIKE G — decode compute-bound vs latency-bound  ({mx.device_info()['device_name']})")
    print(f"  G={G} (tile-reuse), NB={NB}, peak~310 GB/s (M2) / ~558 (M5)")
    print("=" * 70)
    for T in (65536, 131072, 200000):
        run(T)
    print("\nreadonly>>full => compute-bound (headroom in per-token compute);"
          "\nreadonly~=full => latency-bound (faster compute won't help).")
    print("DONE")
