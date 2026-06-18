"""
Spike H — decode compute optimization prototype (Task 1 gate).

Spike G proved decode is compute-bound (readonly >> full). This tests whether a
concrete optimization of the per-token compute closes the gap toward readonly:
  full : current-style — device-memory codebook gathers, per-head simd_sum in-loop
  opt  : codebook staged in THREADGROUP memory + unrolled dims + grouped simd_sums
  readonly : the access-pattern ceiling (from spike G)

Gate: opt must beat full meaningfully on BOTH M2 and M5 (>=30% of full->readonly
gap, or >=1.15x) to justify productionizing. Else keep the current kernel.
Run: PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/spike_h_decode_opt.py [--check]
"""
import sys
import time
import numpy as np
import mlx.core as mx

D = 256; BITS = 3; N_KV = 4; R = 6; N_Q = N_KV * R; EPT = D // 32; NB = 512
G = 2; GROUPS = R // G; MASK = (1 << BITS) - 1; PWv = (D * BITS + 31) // 32


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

# current-style: device cb gathers, per-head simd_sum inside the head loop
FULL = _HEAD + f"""
    float o[G][EPT]; float msc[G],sm[G];
    for(int r=0;r<G;r++){{msc[r]=-INFINITY;sm[r]=0;for(int i=0;i<EPT;i++)o[r][i]=0;}}
    for(uint t=t0;t<t1;t++){{
        float kd[EPT]; {{ const device uint* kp=kpk+t*PW;
          for(int i=0;i<EPT;i++){{uint d=lane*EPT+i;uint bit=d*BITS;uint w=bit>>5,off=bit&31;uint v=kp[w]>>off;if(off+BITS>32)v|=kp[w+1]<<(32-off);v&=MSK;kd[i]=cb[v];}} }}
        float kn=(float)knm[t];
        float vd[EPT]; {{ const device uint* vp=vpk+t*PW;
          for(int i=0;i<EPT;i++){{uint d=lane*EPT+i;uint bit=d*BITS;uint w=bit>>5,off=bit&31;uint v=vp[w]>>off;if(off+BITS>32)v|=vp[w+1]<<(32-off);v&=MSK;vd[i]=cb[v];}} }}
        float vnn=(float)vnm[t];
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
"""

# opt: codebook in threadgroup memory, unrolled dims, G partial-dots then grouped simd_sums
OPT = _HEAD + f"""
    threadgroup float cbsh[1<<BITS];
    if (lane < (1<<BITS)) cbsh[lane]=cb[lane];
    threadgroup_barrier(mem_flags::mem_threadgroup);
    float o[G][EPT]; float msc[G],sm[G];
    for(int r=0;r<G;r++){{msc[r]=-INFINITY;sm[r]=0;for(int i=0;i<EPT;i++)o[r][i]=0;}}
    for(uint t=t0;t<t1;t++){{
        float kd[EPT];
        {{ const device uint* kp=kpk+t*PW;
           #pragma unroll
           for(int i=0;i<EPT;i++){{uint d=lane*EPT+i;uint bit=d*BITS;uint w=bit>>5,off=bit&31;uint v=kp[w]>>off;if(off+BITS>32)v|=kp[w+1]<<(32-off);v&=MSK;kd[i]=cbsh[v];}} }}
        float kn=(float)knm[t];
        float vd[EPT];
        {{ const device uint* vp=vpk+t*PW;
           #pragma unroll
           for(int i=0;i<EPT;i++){{uint d=lane*EPT+i;uint bit=d*BITS;uint w=bit>>5,off=bit&31;uint v=vp[w]>>off;if(off+BITS>32)v|=vp[w+1]<<(32-off);v&=MSK;vd[i]=cbsh[v];}} }}
        float vnn=(float)vnm[t];
        // G partial dots first, then grouped simd_sums (overlap the reductions)
        float part[G];
        #pragma unroll
        for(int r=0;r<G;r++){{ float sc=0; for(int i=0;i<EPT;i++)sc+=qreg[r][i]*kd[i]; part[r]=sc; }}
        #pragma unroll
        for(int r=0;r<G;r++){{
            float sc=simd_sum(part[r])*kn;
            float nm=max(msc[r],sc),corr=fast::exp(msc[r]-nm),es=fast::exp(sc-nm);
            msc[r]=nm; sm[r]=sm[r]*corr+es;
            for(int i=0;i<EPT;i++)o[r][i]=o[r][i]*corr+es*vnn*vd[i];
        }}
    }}
    for(int r=0;r<G;r++){{uint h=qbase+r; for(int i=0;i<EPT;i++)po[(h*NB+block)*DD+lane*EPT+i]=o[r][i];
        if(lane==0){{lmax[h*NB+block]=msc[r];lsum[h*NB+block]=sm[r];}}}}
"""

READONLY = _HEAD + f"""
    float acc=0;
    for(uint t=t0;t<t1;t++){{
        const device uint* kp=kpk+t*PW; const device uint* vp=vpk+t*PW;
        for(int w=0;w<PW;w++) acc += (float)(kp[w]^vp[w]);
        acc += (float)knm[t]+(float)vnm[t];
    }}
    acc=simd_sum(acc);
    for(int r=0;r<G;r++){{uint h=qbase+r; po[(h*NB+block)*DD+lane*EPT]=acc;
        if(lane==0){{lmax[h*NB+block]=0;lsum[h*NB+block]=0;}}}}
"""

BUILT = {n: mx.fast.metal_kernel(name=f"dech_{n}", input_names=["Q","Kpacked","Knorms","Vpacked","Vnorms","cb"],
                                 output_names=["po","lmax","lsum"], source=s)
         for n, s in {"full": FULL, "opt": OPT, "readonly": READONLY}.items()}


def call_kernel(name, ins, T):
    return BUILT[name](inputs=ins, template=[("T", T), ("PW", PWv)],
                       grid=(N_KV*GROUPS*NB*32, 1, 1), threadgroup=(32, 1, 1),
                       output_shapes=[(N_Q, NB, D), (N_Q, NB), (N_Q, NB)],
                       output_dtypes=[mx.float32, mx.float32, mx.float32])


def merge(po, lmax, lsum):
    gmax = mx.max(lmax, axis=1, keepdims=True); corr = mx.exp(lmax - gmax)
    gsum = mx.sum(lsum * corr, axis=1, keepdims=True)
    return mx.sum(po * corr[:, :, None], axis=1) / gsum


if __name__ == "__main__":
    print("=" * 72)
    print(f"SPIKE H — decode compute opt  ({mx.device_info()['device_name']})  G={G} NB={NB}")
    print("=" * 72)
    if "--check" in sys.argv:
        kpk, knm, vpk, vnm, q, cb = make_kv(2048, seed=1)
        ins = [q, kpk, knm, vpk, vnm, cb]
        pf = call_kernel("full", ins, 2048); po = call_kernel("opt", ins, 2048)
        of = merge(*pf); oo = merge(*po); mx.eval(of, oo)
        print("opt vs full max-abs-diff:", mx.max(mx.abs(of - oo)).item(), "(want < 1e-4)")
        sys.exit(0)
    for T in (65536, 131072, 200000):
        kpk, knm, vpk, vnm, q, cb = make_kv(T)
        ins = [q, kpk, knm, vpk, vnm, cb]
        kv_gb = (N_KV * GROUPS * T * PWv * 4 * 2) / 1e9
        res = {}
        for name in ("readonly", "full", "opt"):
            sec = bench(lambda n=name: call_kernel(n, ins, T)[0])
            res[name] = (sec, kv_gb / sec)
        gap = (res["opt"][1] - res["full"][1]) / max(res["readonly"][1] - res["full"][1], 1e-9)
        sp = res["full"][0] / res["opt"][0]
        print(f"  T={T:>7}: readonly {res['readonly'][1]:6.1f}  full {res['full'][1]:6.1f}  "
              f"opt {res['opt'][1]:6.1f} GB/s | opt {sp:.2f}x vs full | gap-closed {gap*100:4.0f}%")
    print("\nGATE: opt >= 1.15x vs full (or >=30% gap-closed) on BOTH boxes -> productionize.")
    print("DONE")
